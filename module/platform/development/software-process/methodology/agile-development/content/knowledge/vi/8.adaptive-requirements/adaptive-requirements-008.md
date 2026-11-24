# Phân biệt làm rõ yêu cầu với mở rộng phạm vi

## 1. Vì sao cần phân biệt hai việc này?

Trong phát triển phần mềm Agile, nhóm thường bắt đầu từ một nhu cầu chưa được mô tả hoàn toàn. Khi trao đổi với người dùng, phân tích dữ liệu hoặc chạy thử phần mềm, nhóm phát hiện thêm các quy tắc, tình huống ngoại lệ và cách sử dụng chưa được nói rõ. Một số phát hiện giúp **làm rõ điều nhóm đã định xây dựng**; một số khác lại đề xuất **thêm điều mới vào phạm vi**.

Nếu coi mọi câu hỏi mới là “đổi phạm vi”, nhóm sẽ ngại học hỏi và dễ bàn giao chức năng không đáp ứng nhu cầu thật. Nếu coi mọi đề nghị mới là “chỉ làm rõ”, công việc có thể tăng không giới hạn trong khi thời gian, năng lực và mục tiêu vẫn giữ nguyên. Cả hai đều làm giảm khả năng dự báo và giao giá trị.

**Phân biệt làm rõ yêu cầu với mở rộng phạm vi** giúp nhóm:

- Giữ chung cách hiểu về mục tiêu, hành vi và tiêu chuẩn chấp nhận.
- Tiếp nhận thông tin mới mà không mặc nhiên cam kết làm thêm mọi thứ.
- Minh bạch tác động đến công sức, rủi ro, phụ thuộc và thời gian giao hàng.
- Chủ động trao đổi với Product Owner và người liên quan để sắp xếp lại backlog.
- Giao phần mềm tăng dần, nhận phản hồi sớm và điều chỉnh theo giá trị.

Đây là năng lực cốt lõi của **AGILE_DEVELOPMENT**: yêu cầu được thích ứng qua trao đổi và phản hồi, nhưng những thay đổi có tác động vẫn cần được nhìn nhận, ưu tiên và quản lý rõ ràng.

> **Ý chính:** “Mới được nói ra” không tự động có nghĩa là “mở rộng phạm vi”; ngược lại, “người dùng nói rằng ý họ vốn là vậy” cũng không tự động biến một khả năng mới thành yêu cầu đã thống nhất.

## 2. Định nghĩa: làm rõ, mở rộng và thay đổi phạm vi

### 2.1. Làm rõ yêu cầu (requirement clarification)

**Làm rõ yêu cầu** là bổ sung độ chính xác cho một nhu cầu hoặc hành vi **đã nằm trong mục tiêu và ranh giới công việc được thống nhất**. Nhóm làm rõ thuật ngữ, quy tắc, dữ liệu, trường hợp biên, hành vi lỗi hoặc tiêu chí chấp nhận để biết thế nào là hoàn tất.

Ví dụ, hạng mục đã thống nhất “học viên đã đăng nhập đăng ký một khóa học còn chỗ”. Khi trao đổi, nhóm cần biết **nút Đăng ký bị bấm hai lần thì xử lý ra sao**. Nếu mục tiêu từ đầu là tạo đúng một đăng ký hợp lệ, việc xác nhận “không tạo hai bản ghi cho cùng một học viên” làm rõ tính đúng đắn của hành vi đã thống nhất.

Làm rõ không nhất thiết là một thao tác nhỏ hoặc miễn phí. Một trường hợp cạnh tranh dữ liệu tưởng đơn giản có thể đòi hỏi thay đổi giao dịch cơ sở dữ liệu, viết kiểm thử mới và điều chỉnh thiết kế. **Không mở rộng giá trị chức năng không có nghĩa là không tăng công sức thực hiện.**

### 2.2. Mở rộng phạm vi (scope expansion)

**Mở rộng phạm vi** xảy ra khi nhóm bổ sung một kết quả, khả năng, đối tượng sử dụng, quy trình, kênh, hệ thống tích hợp hoặc ràng buộc mới **vượt ngoài ranh giới đã thống nhất** cho sản phẩm, bản phát hành, Sprint hay một hạng mục cụ thể.

Ví dụ, từ chức năng “học viên đăng ký khóa học còn chỗ”, một bên đề xuất “gửi SMS nhắc lịch học trước 24 giờ”. Đây có thể là ý tưởng mang lại giá trị, nhưng **tạo thêm khả năng khác**: thu thập hoặc sử dụng số điện thoại, tích hợp nhà cung cấp SMS, quản lý lịch gửi, xử lý lỗi và quyền đồng ý nhận tin.

Mở rộng phạm vi **không mặc định là xấu**. Agile khuyến khích phản hồi với thay đổi có giá trị. Vấn đề xuất hiện khi thay đổi được đưa vào mà **không xác định tác động, không sắp xếp ưu tiên và không điều chỉnh cam kết**. Kiểu mở rộng âm thầm, liên tục đó thường được gọi là *scope creep*.

### 2.3. Thay đổi phạm vi rộng hơn việc “làm thêm”

Không phải mọi thay đổi đều là mở rộng:

| Loại thay đổi | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Làm rõ** | Giải thích hành vi đã có, giảm mơ hồ. | Xác nhận thế nào là “đăng ký thành công” và cách xử lý nhấn nút nhiều lần. |
| **Mở rộng** | Thêm khả năng hoặc phạm vi đối tượng chưa thuộc cam kết. | Thêm thanh toán học phí trực tuyến cho luồng đăng ký miễn phí. |
| **Thu hẹp** | Bỏ hoặc hoãn một phần khả năng đã được dự kiến. | Chỉ hỗ trợ một loại khóa học trong lần giao đầu tiên. |
| **Thay thế / đổi hướng** | Đổi giải pháp hoặc nhu cầu ưu tiên theo bằng chứng mới. | Thay bước nhập mã lớp thủ công bằng chọn lớp còn chỗ. |
| **Khắc phục lỗi** | Đưa hành vi trở lại tiêu chí đã thống nhất và chuẩn chất lượng. | Sửa lỗi đăng ký thành công nhưng dữ liệu không được lưu. |
| **Khám phá kỹ thuật** | Làm thêm phân tích, thử nghiệm hoặc thay đổi thiết kế để đáp ứng mục tiêu. | Thực hiện spike để kiểm tra cơ chế xử lý đồng thời. |

Việc thay thế hay thu hẹp có thể hợp lý hơn mở rộng khi nhóm có giới hạn thời gian và muốn giữ mục tiêu chính. Điều quan trọng là mô tả rõ **cái gì thay đổi**, **vì sao** và **ai cần đồng ý**.

## 3. Trước khi phân loại: phải biết đang nói về phạm vi nào

Một yêu cầu có thể thuộc phạm vi **sản phẩm dài hạn** nhưng nằm **ngoài Sprint hiện tại**. Nếu không xác định mốc tham chiếu, hai bên có thể tranh luận “đã nằm trong scope hay chưa” mà thực ra đang nói về hai cấp khác nhau.

| Cấp phạm vi | Câu hỏi đặt ra | Ví dụ |
| --- | --- | --- |
| **Product scope** | Sản phẩm dự định giải quyết những bài toán và nhóm người dùng nào? | Nền tảng hỗ trợ đăng ký và theo dõi khóa học. |
| **Release / milestone scope** | Lần phát hành hoặc mốc giao hàng này nhắm đến những khả năng nào? | Phiên bản đầu cho đăng ký khóa học miễn phí, chưa có thanh toán. |
| **Sprint scope** (nếu dùng Scrum) | Nhóm đang dự kiến làm gì để đạt Sprint Goal trong Sprint? | Hoàn tất luồng xem chỗ trống và xác nhận đăng ký. |
| **Backlog item / user story scope** | Hạng mục cụ thể cam kết hành vi và ranh giới nào? | Một học viên đăng nhập đăng ký một khóa còn chỗ, không trùng. |
| **Acceptance / quality boundary** | Điều kiện chấp nhận và chuẩn chất lượng là gì? | Xử lý đăng ký lặp, kiểm tra quyền truy cập, chạy kiểm thử bắt buộc. |

Ví dụ, gửi thông báo email sau đăng ký có thể nằm trong **Product Backlog** từ đầu nhưng chưa được chọn cho Sprint. Khi ai đó đề nghị thêm email vào user story đang triển khai, đây vẫn là **mở rộng phạm vi của hạng mục hoặc Sprint**, dù không mở rộng tầm nhìn tổng thể của sản phẩm.

Ngược lại, một nhóm có thể phát hiện yêu cầu chống đăng ký trùng đã ngầm gắn với tính đúng đắn của luồng hiện tại. Dù trước đó backlog item chưa viết rõ, nhóm cần kiểm tra bối cảnh và bổ sung tiêu chí chấp nhận thích hợp. Không thể chỉ dựa vào việc “chưa ghi thành chữ” để bỏ qua một hành vi thiết yếu.

### 3.1. Ranh giới được hình thành từ những gì?

Một ranh giới có thể được thể hiện bởi:

- Mục tiêu sản phẩm, nhóm người dùng và kết quả mong muốn.
- User story, mô tả hạng mục, ví dụ nghiệp vụ và tiêu chí chấp nhận.
- Quy tắc nghiệp vụ đã được xác nhận trong trao đổi.
- Các loại công việc hoặc đối tượng **được loại trừ rõ ràng**.
- Hợp đồng API, yêu cầu tích hợp và tiêu chuẩn chất lượng áp dụng.
- Sprint Goal, mục tiêu bản phát hành, phụ thuộc và nguồn lực dự kiến.

Không cần đóng băng một bản đặc tả khổng lồ, nhưng nên giữ **bằng chứng quyết định đủ rõ** để có thể đối chiếu khi phát sinh câu hỏi.

### 3.2. Phân biệt nhu cầu, giải pháp và việc triển khai

Ba tầng này thường bị trộn:

1. **Nhu cầu/kết quả:** “Học viên đăng ký được khóa học còn chỗ mà không cần nhân viên hỗ trợ”.
2. **Hành vi/khả năng sản phẩm:** “Học viên xem chỗ trống, xác nhận đăng ký, thấy kết quả”.
3. **Công việc triển khai:** “Tạo API, thêm ràng buộc dữ liệu, viết test tích hợp”.

Một thay đổi thiết kế từ API A sang API B có thể làm thay đổi công việc triển khai mà **không thêm khả năng sản phẩm**. Ngược lại, yêu cầu bổ sung tính năng “đăng ký hộ người thân” rõ ràng làm đổi nhóm người dùng và hành vi, dù kỹ sư nói chỉ mất vài dòng mã.

Vì vậy, **không phân loại scope bằng số dòng code hay ước lượng nhỏ/lớn**. Hãy xem nó làm thay đổi kết quả và ranh giới nào.

## 4. Sáu câu hỏi phân biệt làm rõ với mở rộng

Khi nhận được một yêu cầu bổ sung, nhóm có thể cùng Product Owner hoặc người có thẩm quyền đi qua sáu câu hỏi:

1. **Mốc tham chiếu là gì?** Đang xét sản phẩm, release, Sprint hay user story nào? Nội dung nào đã được thống nhất?
2. **Mục tiêu và đối tượng có đổi không?** Đề nghị phục vụ cùng nhu cầu, cùng người dùng và cùng kết quả, hay thêm một mục tiêu mới?
3. **Đề nghị làm rõ hành vi bắt buộc hay thêm khả năng tùy chọn?** Nếu không thực hiện, chức năng hiện tại còn đúng tiêu chí chấp nhận và Definition of Done không?
4. **Có thêm luồng, hệ thống, dữ liệu hoặc trách nhiệm mới không?** Ví dụ thêm loại người dùng, kênh thông báo, tích hợp, chế độ vận hành.
5. **Tác động thực tế là gì?** Độ phức tạp, ước lượng, kiểm thử, bảo mật, phụ thuộc, thời hạn và chất lượng có thay đổi đáng kể?
6. **Ai cần quyết định?** Nhóm tự làm rõ trong phạm vi đã thống nhất được không, hay cần Product Owner và bên liên quan thương lượng giá trị, ưu tiên và phạm vi?

Sơ đồ hỗ trợ trao đổi:

~~~mermaid
flowchart TD
    A["Có yêu cầu/thông tin mới"] --> B["Xác định mục tiêu và ranh giới đã thống nhất"]
    B --> C{"Thiếu nó thì hành vi đã cam kết còn đúng không?"}
    C -- "Không" --> D["Làm rõ hành vi hoặc sửa lỗi/đáp ứng chất lượng"]
    C -- "Có" --> E{"Có thêm khả năng, đối tượng, kênh hoặc kết quả mới?"}
    E -- "Có" --> F["Đề xuất thay đổi/mở rộng phạm vi"]
    E -- "Chưa rõ" --> G["Khám phá thêm bằng ví dụ và bằng chứng"]
    E -- "Không" --> G
    G --> B
    D --> H["Đánh giá tác động và điều chỉnh kế hoạch"]
    F --> I["Đánh giá giá trị, chi phí và ưu tiên với người có thẩm quyền"]
    I --> J["Chọn làm ngay, thay thế, chia nhỏ hoặc đưa vào backlog"]
    H --> K["Cập nhật tiêu chí và kiểm chứng"]
    J --> K
~~~

Sơ đồ là **công cụ tư duy**, không phải công thức phân loại tuyệt đối. Một đề nghị có thể vừa phát hiện lỗi trong ranh giới cũ, vừa dẫn tới ý tưởng mới để cải thiện sản phẩm. Khi đó nên **tách riêng phần bắt buộc và phần tùy chọn**, giúp quyết định minh bạch.

### 4.1. Dấu hiệu làm rõ yêu cầu

- Diễn giải thuật ngữ mơ hồ: “đã xác nhận”, “hết chỗ”, “hoàn tất”, “người dùng hợp lệ”.
- Xác nhận quy tắc nghiệp vụ cần thiết để hành vi đã chọn đúng trong tình huống thường gặp.
- Làm rõ dữ liệu đầu vào, đầu ra, trạng thái lỗi và ranh giới quyền truy cập.
- Bổ sung ví dụ hoặc tiêu chí chấp nhận nhằm kiểm chứng một hành vi đã có.
- Sửa sai lệch giữa phần mềm thực tế và hành vi/chuẩn chất lượng đã thống nhất.

Tuy nhiên, một “trường hợp ngoại lệ” rất lớn có thể tiết lộ rằng nhu cầu ban đầu chưa xác định đầy đủ. Khi nó thay đổi mô hình nghiệp vụ hoặc thêm quy trình đáng kể, phải **đánh giá lại phạm vi**, không mặc nhiên ghi vào hạng mục hiện tại.

### 4.2. Dấu hiệu mở rộng phạm vi

- Thêm một nhóm người dùng, vai trò hoặc chính sách đặc thù chưa thuộc đối tượng ban đầu.
- Bổ sung một mục tiêu hoặc lợi ích khác với kết quả đã được ưu tiên.
- Thêm chức năng độc lập có thể trì hoãn mà vẫn đạt mục tiêu cũ.
- Mở rộng kênh hỗ trợ: từ web sang ứng dụng di động riêng, từ email sang SMS.
- Tích hợp thêm nhà cung cấp, hệ thống hoặc một hành trình hoàn toàn mới.
- Thêm phạm vi dữ liệu, vùng hoạt động, ngôn ngữ, báo cáo hoặc quy trình vận hành chưa cam kết.

Đây là **dấu hiệu để hỏi thêm**, không phải kết luận tự động. Nếu sản phẩm ngay từ đầu đã cam kết đa ngôn ngữ hoặc nhiều vai trò, việc hỗ trợ những đối tượng đó có thể là phần làm rõ của cam kết hiện hành.

## 5. Ví dụ xuyên suốt: đăng ký khóa học trực tuyến

Giả sử một nhóm được giao **đưa vào dùng thử luồng đăng ký khóa học miễn phí** cho học viên đã đăng nhập. Giá trị mong muốn là học viên tự đăng ký được mà không phải nhờ nhân viên.

### 5.1. Thỏa thuận ban đầu của hạng mục

**User story:**

> Là học viên đã đăng nhập, tôi muốn đăng ký một khóa học còn chỗ để tự tham gia học mà không cần liên hệ bộ phận hỗ trợ.

**Mục tiêu:** hoàn tất một lượt đăng ký hợp lệ, trả kết quả rõ ràng và ghi nhận đúng vào hệ thống.

**Các tiêu chí chấp nhận ban đầu:**

1. Học viên hợp lệ đăng ký thành công khi khóa còn chỗ.
2. Nếu hết chỗ, hệ thống không xác nhận đăng ký và hiển thị trạng thái rõ.
3. Một học viên không được có hai bản ghi đăng ký hiệu lực trùng nhau cho cùng khóa.
4. Kết quả lưu trữ và thông báo hiển thị phải nhất quán.
5. Người không có quyền không được sửa đăng ký của người khác.

**Ngoài phạm vi của hạng mục trong lần giao này:** thanh toán, hủy đăng ký, SMS nhắc học, danh sách chờ và đăng ký hộ người khác.

Những ranh giới trên là ví dụ minh họa. Trong dự án thật, chúng phải được người có thẩm quyền nghiệp vụ và nhóm thống nhất, không tự suy đoán từ một user story ngắn.

### 5.2. Phân loại các đề nghị phát sinh

| Đề nghị phát sinh | Phân loại tham khảo | Lý do và cách xử lý |
| --- | --- | --- |
| “Đăng ký thành công” nghĩa là tạo đúng một bản ghi và hiển thị mã xác nhận. | **Làm rõ** | Giải thích kết quả đã cam kết; cần xác nhận dữ liệu nào thực sự bắt buộc. |
| Khi bấm Đăng ký hai lần, không tạo đăng ký trùng. | **Làm rõ / chất lượng** | Trực tiếp phục vụ quy tắc chống trùng đã thống nhất; bổ sung test. |
| Hai học viên cùng chọn chỗ cuối không được vượt sức chứa. | **Làm rõ / chất lượng** | Cần thiết để khẳng định “còn chỗ”; có thể tăng đáng kể công sức kiểm soát đồng thời. |
| Hiển thị thông báo có thể hiểu khi khóa đã hết chỗ. | **Làm rõ** | Nằm trong hành vi thất bại đã có; cần trao đổi nội dung và trạng thái. |
| Gửi SMS nhắc học 24 giờ trước giờ bắt đầu. | **Mở rộng** | Thêm kênh, thời điểm, dữ liệu và tích hợp; đã nằm ngoài phạm vi lần giao. |
| Cho phép hủy đăng ký và hoàn lại chỗ. | **Mở rộng** | Thêm luồng nghiệp vụ mới, có thể trở thành user story khác. |
| Thêm thanh toán bằng ví điện tử. | **Mở rộng** | Thay đổi loại giao dịch và các yêu cầu bảo mật, tích hợp, đối soát. |
| Sửa lỗi UI hiện báo “thành công” dù lưu dữ liệu thất bại. | **Sửa lỗi** | Đưa hệ thống về hành vi đã cam kết; không được đánh dấu Done khi còn lỗi này. |
| Cần đổi cấu trúc giao dịch dữ liệu để chống tranh chấp chỗ. | **Thay đổi triển khai** | Không thêm chức năng nhưng có thể đổi ước lượng, thiết kế và rủi ro. |
| Muốn dùng luồng này cho doanh nghiệp đăng ký hàng loạt nhân viên. | **Mở rộng** | Thêm vai trò, dữ liệu và quy trình khác với học viên cá nhân. |
| Học viên dùng màn hình di động muốn nút hiển thị rõ. | **Phụ thuộc ranh giới** | Nếu đã cam kết hỗ trợ web responsive và chuẩn tiếp cận thì làm rõ/chất lượng; nếu bổ sung ứng dụng di động riêng thì mở rộng. |
| Phải bảo vệ dữ liệu cá nhân theo chính sách đã áp dụng. | **Nghĩa vụ chất lượng** | Không thể coi là tính năng tùy chọn để cắt nhằm tiết kiệm công. |

Một trường hợp như **kiểm soát hai yêu cầu đồng thời** có thể không được nhận ra khi lập kế hoạch. Về nghiệp vụ, nó có thể nằm trong yêu cầu chính xác của đăng ký; về triển khai, nó có thể đòi hỏi thiết kế lại cơ chế lưu trữ. Nhóm cần đưa ra **cả hai thông tin**: đây là điều phải làm để đúng hành vi đã nhận, và năng lực/thời gian dự kiến cần được cập nhật.

### 5.3. Minh họa làm rõ bằng ví dụ có thể kiểm chứng

Nhóm có thể dùng kịch bản gần cú pháp Gherkin:

~~~gherkin
Feature: Đăng ký khóa học miễn phí

  Scenario: Đăng ký hợp lệ khi còn chỗ
    Given học viên A đã đăng nhập và chưa đăng ký khóa học X
    And khóa học X còn ít nhất một chỗ
    When học viên A xác nhận đăng ký khóa học X
    Then hệ thống lưu đúng một đăng ký hiệu lực cho A
    And A thấy kết quả xác nhận thành công

  Scenario: Nhấn đăng ký lặp lại
    Given học viên A đã có đăng ký hiệu lực ở khóa học X
    When A gửi lại yêu cầu đăng ký cùng khóa học X
    Then hệ thống không tạo đăng ký hiệu lực thứ hai
    And A nhận trạng thái đăng ký hiện có

  Scenario: Hai học viên tranh chỗ cuối
    Given khóa học X chỉ còn một chỗ
    When hai học viên hợp lệ cùng xác nhận đăng ký X
    Then tối đa một đăng ký mới được xác nhận
    And hệ thống không vượt sức chứa khóa học X
~~~

Những kịch bản này **mô tả hành vi**, chưa tự động trở thành kiểm thử chạy được. Nhóm có thể triển khai test tự động ở tầng thích hợp để kiểm chứng cơ chế lưu trữ, giao diện và tích hợp. Một tiêu chí chấp nhận mới được viết ra có thể giúp làm rõ, nhưng việc nó có thuộc phạm vi ban đầu hay không vẫn cần đối chiếu **mục tiêu và ranh giới đã thống nhất**.

### 5.4. Khi đề nghị mới có giá trị cao thì sao?

Giả sử phản hồi của học viên cho thấy họ thường cần **hủy đăng ký**. Đây có thể là một nhu cầu có giá trị rất cao. Nhóm vẫn nên ghi nhận nó như **một thay đổi phạm vi** rồi cùng Product Owner đánh giá:

- Có nên ưu tiên chức năng hủy trước các báo cáo quản trị dự kiến?
- Có thể giao một Increment hủy đơn giản trước khi hỗ trợ hoàn phí không?
- Những quy tắc về hạn chót, hoàn chỗ và thông báo phải làm rõ trước?
- Điều gì sẽ không được làm trong lần phát hành hiện tại để có năng lực xử lý?

**Gọi đúng là mở rộng phạm vi không có nghĩa là từ chối thay đổi.** Nó giúp tổ chức quyết định thay đổi một cách chủ động và minh bạch.

## 6. Làm rõ yêu cầu hiệu quả bằng trao đổi và ví dụ

Agile không yêu cầu hoàn tất mọi chi tiết từ ngày đầu. Nhóm thường làm rõ yêu cầu **vừa đủ, gần thời điểm thực hiện** thông qua backlog refinement, trao đổi với người dùng và kiểm chứng bằng phần mềm.

### 6.1. Bắt đầu từ giá trị và tình huống sử dụng

Trước khi bàn chi tiết giao diện hoặc API, nhóm nên biết:

- **Ai** sử dụng và gặp khó khăn gì?
- **Vì sao** hạng mục này quan trọng ngay bây giờ?
- **Kết quả tối thiểu** nào chứng minh nhu cầu được giải quyết?
- **Điều kiện bất biến** nào không được vi phạm, ví dụ quyền truy cập hoặc không đăng ký vượt sức chứa?
- **Phạm vi loại trừ** nào cần nói rõ để tránh suy đoán?

Một user story giúp mở cuộc trao đổi, **không phải hợp đồng đủ mọi chi tiết**. Chỉ sao chép khuôn mẫu “Là…, tôi muốn…, để…” mà không trao đổi ví dụ sẽ dễ dẫn đến bất đồng sau khi đã viết mã.

### 6.2. Dùng kỹ thuật Three Amigos hoặc trao đổi đa góc nhìn

Một nhóm có thể mời đại diện **nghiệp vụ/sản phẩm**, **phát triển** và **kiểm thử/chất lượng** cùng xem các kịch bản chính. Đây là cách thực hành thường được gọi là *Three Amigos*, không bắt buộc phải có đúng ba người hay ba chức danh.

Mỗi góc nhìn đóng góp câu hỏi khác nhau:

| Góc nhìn | Câu hỏi hữu ích |
| --- | --- |
| **Nghiệp vụ / Product Owner** | Người dùng cần kết quả nào? Quy tắc và ngoại lệ nào thật sự quan trọng? |
| **Kỹ thuật / Developers** | Dữ liệu nào cần có? Phụ thuộc nào, lựa chọn thiết kế nào, rủi ro nào phải kiểm chứng? |
| **Kiểm thử / chất lượng** | Thế nào là đúng hoặc sai? Có tình huống biên, quyền truy cập hoặc xử lý lỗi nào chưa được nói rõ? |

Nhóm nên biến những câu trả lời thành **ví dụ quan sát được**. Ví dụ, thay vì “hệ thống phải xử lý tốt đăng ký trùng”, hãy viết “khi cùng học viên gửi hai yêu cầu đăng ký cho một khóa, hệ thống chỉ có một đăng ký hiệu lực”.

### 6.3. Ghi lại câu hỏi đang mở

Với yêu cầu chưa rõ, có thể ghi:

| Trường | Ví dụ |
| --- | --- |
| **Câu hỏi** | Học viên có được đăng ký cùng khóa từ hai thiết bị đồng thời không? |
| **Tác động nếu chưa rõ** | Không biết quy tắc chống trùng; có thể thiết kế sai giao dịch. |
| **Giả định tạm thời** | Mỗi học viên tối đa một đăng ký hiệu lực. |
| **Người xác nhận** | Product Owner hoặc chủ sở hữu quy tắc nghiệp vụ. |
| **Cách kiểm chứng** | Ví dụ cạnh tranh được chấp thuận và test tích hợp tương ứng. |
| **Trạng thái** | Đang chờ làm rõ; chưa dùng giả định như quyết định cuối cùng. |

Giả định cần được **đánh dấu là giả định**. Đối với quy tắc quan trọng, nhóm không nên âm thầm biến giả định thành chính sách bằng cách triển khai rồi mặc định Product Owner sẽ đồng ý.

### 6.4. “Definition of Ready” có thể hữu ích nhưng không bắt buộc

Một nhóm có thể tự chọn vài tiêu chí để đánh giá hạng mục đã **đủ rõ để bắt đầu** hay chưa, ví dụ mục tiêu có ích, điều kiện chấp nhận chính, phụ thuộc quan trọng và câu hỏi cần trả lời. Đây thường được gọi là *Definition of Ready (DoR)*.

DoR **không phải thành phần bắt buộc của Scrum Guide** và không nên biến thành cổng phê duyệt cứng nhắc khiến nhóm không thể học bằng thử nghiệm. Tương tự, hạng mục “đủ sẵn sàng” vẫn có thể cần làm rõ thêm khi phát triển.

**Definition of Done (DoD)** là chuyện khác: nó nêu chuẩn chất lượng cần đáp ứng để Increment được coi là hoàn tất. Không thể đổi hoặc giảm DoD chỉ vì phát hiện phạm vi cần làm rõ lớn hơn dự tính.

## 7. Xử lý thay đổi đúng lúc trong Scrum

Trong Scrum, Product Backlog là danh sách công việc nổi lên và được sắp xếp để cải thiện sản phẩm. Product Owner chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog hiệu quả; Developers chịu trách nhiệm tạo Increment đáp ứng DoD và lập kế hoạch kỹ thuật để đạt Sprint Goal.

### 7.1. Trước Sprint: refinement và Sprint Planning

Trong **backlog refinement**, nhóm làm rõ mô tả, thứ tự, kích thước và những câu hỏi của Product Backlog Items. Có thể tách hạng mục lớn thành lát cắt nhỏ, ghi tiêu chí chấp nhận, ranh giới và phụ thuộc.

Trong **Sprint Planning**, Scrum Team tạo Sprint Goal và lựa chọn các hạng mục để hướng đến mục tiêu đó. Developers lập kế hoạch cách thực hiện. Kế hoạch không phải lời tiên tri rằng mọi chi tiết đã biết; Scrum dựa trên kiểm tra và thích ứng.

**Ví dụ:** Sprint Goal là “Học viên có thể tự đăng ký thành công một khóa học miễn phí”. Việc làm rõ chống đăng ký trùng giúp bảo đảm mục tiêu này, còn đề nghị thêm hệ thống SMS có thể được đưa vào Product Backlog để ưu tiên ở thời điểm thích hợp.

### 7.2. Trong Sprint: làm rõ và thương lượng phạm vi

Scrum Guide nêu rằng **phạm vi có thể được làm rõ và thương lượng lại với Product Owner khi nhóm học thêm**, miễn là các thay đổi không làm đe dọa Sprint Goal; chất lượng không được giảm. Vì vậy không đúng khi nói “đã vào Sprint thì tuyệt đối không thay đổi gì”.

Một cách xử lý thực tế:

1. **Nhận diện thông tin mới** và đối chiếu Sprint Goal, hạng mục và tiêu chí hiện tại.
2. **Phân biệt phần cần thiết để đáp ứng hành vi** với khả năng mới tùy chọn.
3. **Để Developers đánh giá công việc còn lại**, phụ thuộc, rủi ro và cách chia lát cắt.
4. **Trao đổi với Product Owner về thay đổi ưu tiên/phạm vi**, đặc biệt nếu ảnh hưởng khả năng đạt Sprint Goal.
5. **Cập nhật Sprint Backlog hoặc Product Backlog một cách minh bạch**, thống nhất hạng mục nào làm ngay, cái nào hoãn, thay thế hay tách ra.
6. **Giữ nguyên chuẩn chất lượng**; chỉ đánh dấu Done khi đáp ứng DoD.

Khi Sprint Goal không còn giá trị do bối cảnh thay đổi, Scrum có quy định về **hủy Sprint** và chỉ Product Owner có thẩm quyền hủy. Đây là trường hợp đặc biệt, không phải cách xử lý mặc định mỗi khi có yêu cầu bổ sung.

### 7.3. Các ví dụ quyết định trong Sprint

| Tình huống | Hành động phù hợp |
| --- | --- |
| Làm rõ “đăng ký thành công” cần lưu dữ liệu và trả kết quả nhất quán. | Bổ sung tiêu chí/test cần thiết; Developers cập nhật kế hoạch, báo tác động. |
| Cần chống đăng ký trùng nhưng thực hiện phức tạp hơn ước tính. | Giữ tiêu chuẩn đúng đắn; phân tích phương án, thương lượng phạm vi khác nếu cần. |
| Stakeholder muốn thêm SMS nhắc học khi Sprint đang triển khai. | Đưa yêu cầu vào backlog để Product Owner đánh giá; chỉ nhận vào Sprint khi phù hợp và được thương lượng, không đánh đổi Sprint Goal/DoD. |
| Một luồng nâng cao đã dự kiến nhưng không cần thiết cho Sprint Goal. | Có thể thương lượng tách/hoãn để bảo vệ mục tiêu chính; công bố thay đổi minh bạch. |
| Vấn đề bảo mật nghiêm trọng mới được phát hiện. | Tuân theo quy trình an toàn phù hợp; điều chỉnh kế hoạch và trao đổi kịp thời, không gọi là “ngoài scope” để bỏ qua. |

### 7.4. Tránh “scope creep” trong Sprint mà vẫn thích ứng

Không nên nhận lời trực tiếp với từng bên liên quan rồi lặng lẽ thêm việc vào Sprint Backlog. Các yêu cầu có giá trị nhưng chưa cấp thiết có thể được ghi vào Product Backlog, so với công việc hiện tại và sắp xếp lại. Nếu cần làm ngay, nên chỉ rõ **điều gì bị thay thế hoặc điều chỉnh** và kết quả mới được kỳ vọng.

Việc **bổ sung công việc cần thiết để đáp ứng DoD** không thể bị biến thành lựa chọn hoãn tùy tiện. Nếu phát hiện Increment chưa an toàn hoặc chưa đúng, nhóm phải xử lý theo chuẩn đã thống nhất hoặc minh bạch rằng hạng mục chưa Done.

## 8. Xử lý yêu cầu mới trong Kanban và cách làm liên tục

Kanban thường hướng đến trực quan hóa công việc và cải thiện luồng, không bắt buộc sử dụng Sprint cố định. Trong bối cảnh đó, ranh giới quan trọng là **cam kết, chính sách nhận việc vào hệ thống và năng lực xử lý hiện tại**.

Một nhóm có thể công bố chính sách:

1. Yêu cầu mới cần ghi rõ mục tiêu và người hưởng lợi.
2. Các đề nghị mở rộng được đưa vào hàng chờ và sắp xếp ưu tiên theo giá trị, rủi ro, mức cấp thiết.
3. Hạng mục đang làm được cập nhật khi phát hiện phần làm rõ cần thiết.
4. Nếu đề nghị là khả năng mới, tạo hạng mục riêng khi phù hợp để tránh làm tăng kích thước công việc đang dở.
5. Chỉ kéo việc mới khi có năng lực theo giới hạn WIP, trừ những ngoại lệ đã được thống nhất.
6. Theo dõi cycle time, tuổi hạng mục, throughput, chất lượng và tác động tới kết quả người dùng.

Ví dụ, khi một thẻ “Đăng ký khóa học” đang ở cột “Kiểm thử”, bên liên quan đề nghị thêm khả năng tải hóa đơn. Thay vì đổi thẻ thành “Đăng ký + hóa đơn” rồi giữ nó ở trạng thái đang làm thêm nhiều ngày, nhóm có thể ghi **“Tải hóa đơn”** thành hạng mục mới để đánh giá và ưu tiên riêng.

Ngược lại, nếu phát hiện trường hợp đăng ký trùng làm sai hành vi đã thống nhất, việc sửa lỗi và kiểm chứng vẫn gắn với chất lượng của chức năng hiện tại. **Không đổi tên hoặc tách thẻ chỉ để làm cho thời gian hoàn thành trông đẹp hơn.**

Kanban giúp **thấy tác động của thay đổi phạm vi lên luồng công việc**. Khi nhiều hạng mục bị mở rộng giữa chừng, work item age và cycle time có thể tăng; nhóm cần kiểm tra chính sách nhận việc, cách chia nhỏ và nguồn gốc yêu cầu phát sinh.

### 8.1. Vai trò của XP và kiểm thử

Các thực hành của Extreme Programming như trao đổi gần với người có hiểu biết nghiệp vụ, kiểm thử tự động, tích hợp liên tục, pairing và refactoring giúp nhóm kiểm chứng cách hiểu yêu cầu.

Ví dụ, một test mô tả “đăng ký lặp không tạo bản ghi thứ hai” giúp phản hồi nhanh khi thay đổi mã. Tuy vậy, test không tự quyết **đây có phải quy tắc nghiệp vụ đúng hay không**. Đầu tiên nhóm cần xác nhận mong đợi với người có thẩm quyền, sau đó dùng test để bảo vệ hành vi đã thống nhất.

## 9. Đánh giá tác động khi phạm vi thay đổi

Một yêu cầu mở rộng nên đi kèm **đánh giá tác động đủ để quyết định**, không nhất thiết cần một bộ hồ sơ lớn. Với thay đổi nhỏ, trao đổi ngắn và cập nhật backlog có thể đủ; thay đổi lớn hoặc rủi ro cao cần phân tích kỹ hơn.

| Chiều tác động | Câu hỏi cần hỏi | Ví dụ khi bổ sung SMS nhắc học |
| --- | --- | --- |
| **Giá trị người dùng** | Mang lại kết quả gì? Có bằng chứng nhu cầu không? | Học viên ít quên buổi học hơn; cần kiểm chứng. |
| **Phạm vi hành vi** | Có thêm kênh, vai trò, trạng thái hoặc luồng không? | Đăng ký, quản lý opt-in, lịch gửi, retry. |
| **Khối lượng và năng lực** | Nhóm cần thêm việc gì, ảnh hưởng hạng mục đang làm ra sao? | UI, backend, cấu hình provider, test và vận hành. |
| **Chất lượng và rủi ro** | Có rủi ro dữ liệu, bảo mật, tin nhắn gửi nhầm hoặc thất bại không? | Quyền đồng ý nhận tin, xử lý số điện thoại. |
| **Phụ thuộc** | Cần người nào, hệ thống nào, quy trình phê duyệt nào? | Nhà cung cấp SMS, chủ sở hữu chính sách dữ liệu. |
| **Thời gian và ưu tiên** | Nếu thêm việc này, điều gì phải hoãn hoặc thay thế? | Hoãn báo cáo thống kê ít quan trọng hơn. |
| **Đo lường** | Sau khi giao, dựa vào đâu biết tính năng có ích? | Tỷ lệ người dùng bật nhắc, tỷ lệ đến lớp. |

Không có quy tắc rằng mọi yêu cầu đều phải được “ước lượng chính xác trước” mới được xem xét. Agile dùng ước lượng và bằng chứng **tương xứng với quyết định cần đưa ra**. Khi chưa chắc chắn, nhóm có thể timebox một spike hoặc giao một thử nghiệm nhỏ để giảm rủi ro.

### 9.1. Trao đổi bằng lựa chọn có đánh đổi

Thay vì nói “không được thêm” hoặc “được thôi” ngay, nhóm có thể trình bày:

| Phương án | Ý nghĩa | Điểm cần cân nhắc |
| --- | --- | --- |
| **Giữ phạm vi hiện tại** | Giao luồng đăng ký hoàn tất rồi mới xem SMS. | Phản hồi về nhu cầu nhắc học đến muộn hơn. |
| **Thay thế một hạng mục ít giá trị** | Ưu tiên SMS thay một tính năng đã dự kiến. | Cần thống nhất mục tiêu và cập nhật kế hoạch. |
| **Chia nhỏ nhu cầu SMS** | Thử thông báo tối thiểu cho một nhóm người dùng phù hợp. | Vẫn cần xử lý dữ liệu/quyền riêng tư và chất lượng bắt buộc. |
| **Hoãn để khám phá** | Phỏng vấn học viên, thử nội dung nhắc không tự động hoặc phân tích dữ liệu. | Có bằng chứng trước khi đầu tư tích hợp. |

**Đánh đổi minh bạch** là điểm khác giữa thích ứng có chủ đích và scope creep.

## 10. Mẫu thực hành: nhật ký làm rõ và thay đổi phạm vi

Một bảng ngắn có thể được lưu ngay trong hệ thống quản lý backlog:

| Trường | Ý nghĩa |
| --- | --- |
| **Yêu cầu phát sinh** | Mô tả hành vi hoặc câu hỏi mới, tránh diễn giải mơ hồ. |
| **Nguồn / bằng chứng** | Ai nêu? Dữ liệu sử dụng, phản hồi hay lỗi nào liên quan? |
| **Mốc tham chiếu** | Hạng mục, Sprint, release hay mục tiêu sản phẩm nào? |
| **Phân loại tạm thời** | Làm rõ, sửa lỗi, mở rộng, thu hẹp, thay thế hoặc cần khám phá thêm. |
| **Giá trị và tác động** | Hành vi cần có, công sức/rủi ro/phụ thuộc ước tính, tính cấp thiết. |
| **Quyết định và người quyết định** | Làm ngay, thay thế, tách backlog hay hoãn; ai chấp thuận trong phạm vi thẩm quyền. |
| **Điều kiện kiểm chứng** | Tiêu chí chấp nhận, test hoặc bằng chứng thành công. |
| **Trạng thái** | Đang chờ rõ, đã thống nhất, đang làm, đã kiểm chứng hoặc hoãn. |

**Ví dụ bản ghi:**

~~~text
ID: REQ-024
Nguồn: Phản hồi từ 8 học viên dùng thử
Mốc tham chiếu: User story đăng ký khóa học miễn phí, Sprint hiện tại
Đề nghị: Gửi SMS nhắc buổi học trước 24 giờ
Phân loại: Mở rộng phạm vi hạng mục và Sprint
Giá trị kỳ vọng: Giảm số học viên quên lịch; chưa có số liệu xác nhận
Tác động: Thêm tích hợp SMS, quản lý đồng ý nhận tin, lịch gửi, kiểm thử
Quyết định: Tạo Product Backlog Item riêng để Product Owner ưu tiên
Hành động tiếp: Làm rõ nhu cầu và rủi ro với đại diện học viên
Điều kiện kiểm chứng: Sẽ xác định khi hạng mục được refinement
~~~

Bảng này là **công cụ hỗ trợ minh bạch**, không bắt buộc mọi trao đổi nhỏ đều phải lập hồ sơ riêng. Với việc chỉnh câu chữ không ảnh hưởng hành vi, cập nhật acceptance criteria và trao đổi trong nhóm có thể đủ.

### 10.1. Mẫu trao đổi ngắn khi phát hiện phạm vi mới

> “Nhóm đã thống nhất luồng đăng ký miễn phí trong lần giao này. Yêu cầu gửi SMS bổ sung một khả năng mới, có thêm tích hợp và quy tắc dữ liệu. Chúng tôi đã ghi đề nghị vào backlog. Đề xuất giữ luồng đăng ký hiện tại để đạt mục tiêu trước; Product Owner có thể quyết định ưu tiên SMS bằng cách thay thế hoặc sắp xếp lại các hạng mục sau khi xem giá trị và tác động.”

Với việc làm rõ:

> “Yêu cầu ban đầu là một học viên không được có đăng ký trùng. Kiểm tra hai yêu cầu gửi gần đồng thời là trường hợp cần xác minh để đáp ứng quy tắc này. Nhóm sẽ bổ sung tiêu chí và test, cập nhật ước lượng phần việc còn lại, đồng thời trao đổi nếu điều đó ảnh hưởng mục tiêu giao hàng.”

Hai cách diễn đạt trên giúp bên liên quan hiểu **vì sao nhóm đưa ra quyết định** và phần nào vẫn cần làm.

## 11. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao không đúng? | Cách xử lý |
| --- | --- | --- |
| “Chưa được ghi trong user story thì chắc chắn ngoài scope.” | User story là điểm khởi đầu trao đổi; hành vi cần thiết có thể được làm rõ sau. | Đối chiếu mục tiêu, quy tắc nghiệp vụ và DoD. |
| “Người dùng vừa yêu cầu thì phải thêm ngay.” | Giá trị cần được cân với công sức, rủi ro và ưu tiên khác. | Product Owner xem xét backlog; thương lượng phạm vi phù hợp. |
| “Chỉ mất một giờ nên không tính thay đổi phạm vi.” | Phạm vi nói về khả năng/kết quả, không phải số giờ. | Ghi nhận nếu thêm hành vi; đánh giá tác động tương xứng. |
| “Làm rõ thì không cần báo thay đổi ước lượng.” | Trường hợp biên hoặc chất lượng ẩn có thể đòi hỏi nhiều công sức. | Cập nhật dự báo và phụ thuộc minh bạch. |
| “Agile cho phép thay đổi mọi thứ vào bất kỳ lúc nào, không cần quản lý.” | Thay đổi không được ưu tiên gây WIP tăng, phân tán và rủi ro. | Có chính sách intake và thương lượng mục tiêu/ưu tiên. |
| “Sprint đã bắt đầu nên không được làm rõ yêu cầu.” | Scrum dựa trên học hỏi; phạm vi có thể làm rõ và thương lượng trong Sprint. | Bảo vệ Sprint Goal và DoD, cập nhật Sprint Backlog. |
| “Cứ hạ tiêu chí chất lượng để giữ thời hạn.” | Increment không đáp ứng DoD thì chưa Done; có thể gây rủi ro lớn. | Đánh đổi phạm vi tùy chọn, không cắt nghĩa vụ bắt buộc. |
| “Tách ticket là đã giải quyết scope creep.” | Nếu vẫn làm thêm mọi yêu cầu không xét ưu tiên thì tổng phạm vi vẫn tăng. | Quản lý giá trị, năng lực và quyết định; tách ticket chỉ hỗ trợ minh bạch. |
| “Chỉ Product Owner mới được đặt câu hỏi làm rõ.” | Developers, người kiểm thử và các bên liên quan cần chủ động phát hiện mơ hồ. | Trao đổi đa góc nhìn; người có thẩm quyền xác nhận quy tắc nghiệp vụ. |
| “Một bug được gọi là feature mới để chuyển sang Sprint sau.” | Nếu hành vi đã cam kết chưa đúng, việc coi là Done sẽ làm sai sự thật. | Phân loại lỗi và tác động tới DoD; công khai trạng thái chưa hoàn tất khi cần. |

### 11.1. Không biến phân loại thành trò tranh luận từ ngữ

Hai người có thể bất đồng liệu một trường hợp là “làm rõ” hay “mở rộng” vì cam kết ban đầu quá mơ hồ. Khi đó, tranh luận tên gọi thường không đủ. Hãy:

1. Tái khẳng định mục tiêu và bằng chứng đã thống nhất.
2. Viết hành vi cụ thể cần có và những phần mới được đề nghị.
3. Đánh giá công sức, rủi ro và giá trị thực tế.
4. Quyết định công khai việc làm ngay hay đưa vào backlog.
5. Cải thiện cách mô tả ranh giới cho những hạng mục sau.

**Tên phân loại phục vụ quyết định**, không phải công cụ để đổ trách nhiệm cho người yêu cầu hay người thực hiện.

## 12. Đo lường khả năng quản lý yêu cầu thích ứng

Không nên đo thành công bằng việc “có ít thay đổi yêu cầu nhất”. Một nhóm gần người dùng và học nhanh có thể ghi nhận nhiều thay đổi hữu ích. Cần nhìn đồng thời **giá trị**, **khả năng giao hàng**, **chất lượng** và **mức minh bạch**.

| Tín hiệu | Câu hỏi | Cách diễn giải |
| --- | --- | --- |
| **Outcome sản phẩm** | Yêu cầu mới có giúp người dùng đạt kết quả tốt hơn không? | Xem tỷ lệ đăng ký thành công, thời gian thao tác, phản hồi thực tế. |
| **Thời gian làm rõ** | Từ khi xuất hiện câu hỏi quan trọng đến lúc có quyết định mất bao lâu? | Thời gian chờ dài có thể là nút thắt phối hợp. |
| **Tần suất thay đổi hạng mục đang làm** | Có nhiều khả năng mới được thêm khi hạng mục đã bắt đầu không? | Xem nguyên nhân: học hỏi có ích, backlog chưa đủ rõ hay ưu tiên bị phân tán? |
| **Work item age / cycle time** | Hạng mục có bị kéo dài do mở rộng liên tục không? | Dùng mốc đo nhất quán; không đổ lỗi tự động cho người nêu yêu cầu. |
| **WIP và throughput** | Có quá nhiều việc đang làm và ít việc Done không? | Hỗ trợ điều chỉnh chính sách intake và chia lát cắt nhỏ. |
| **Lỗi và sửa lại** | Có hành vi bị hiểu sai, thiếu tiêu chí hoặc phải làm lại nhiều lần không? | Cải thiện trao đổi ví dụ và phản hồi sớm. |
| **Thời gian từ ý tưởng đến phản hồi** | Nhóm có kiểm chứng giả thuyết kịp thời không? | Giao phần nhỏ phù hợp thay vì chờ bộ tính năng lớn. |

Ví dụ, một nhóm thường mở rộng user story “đăng ký khóa học” thành đăng ký + thanh toán + thông báo + báo cáo khiến hạng mục tồn tại 30 ngày. Nhóm thử tách các khả năng theo lát cắt có giá trị, đồng thời kiểm tra các trường hợp bắt buộc của từng lát cắt. Nếu cycle time giảm, phần mềm được kiểm chứng sớm hơn và chất lượng không giảm, đây là dấu hiệu cải tiến hữu ích.

Không nên dùng số lượng “change request” hoặc story point để **xếp hạng cá nhân**. Con số dễ bị ảnh hưởng bởi cách chia việc và có thể khiến mọi người ngại báo thông tin mới.

## 13. Bài tập phân loại và ra quyết định

### Bài tập 1 — Phân loại từng đề nghị

Hạng mục hiện tại: **“Khách hàng đã đăng nhập đặt một lịch tư vấn còn trống và nhận xác nhận trên web”**. Đã thống nhất rằng không có đặt trùng giờ, dữ liệu được lưu đúng và giao diện phải sử dụng được trên các màn hình web được hỗ trợ. Chưa bao gồm đổi/hủy lịch, thanh toán, SMS và ứng dụng di động riêng.

Phân loại các đề nghị sau thành **làm rõ**, **mở rộng**, **sửa lỗi/chất lượng** hoặc **cần hỏi thêm**:

1. Khi hai khách bấm giờ trống cuối cùng cùng lúc, chỉ một đặt lịch được xác nhận.
2. Cho phép khách đổi lịch trong vòng 24 giờ trước cuộc hẹn.
3. Một khách bấm nút Xác nhận hai lần nhưng thấy hai lịch giống nhau trong dữ liệu.
4. Nhân viên muốn đặt lịch hộ khách chưa có tài khoản.
5. Thông báo lỗi phải nói rõ khung giờ vừa bị người khác đặt.
6. Sản phẩm cần một ứng dụng iOS riêng cho cùng luồng.
7. Thiết kế cơ sở dữ liệu cần đổi để giữ tính nhất quán của giao dịch.

**Gợi ý đáp án:**

| Tình huống | Phân loại hợp lý | Giải thích |
| --- | --- | --- |
| 1 | Làm rõ/chất lượng | Phục vụ ràng buộc không đặt trùng đã cam kết. |
| 2 | Mở rộng | Thêm luồng thay đổi cuộc hẹn đang ngoài phạm vi. |
| 3 | Sửa lỗi | Hệ thống đang vi phạm ràng buộc; chưa đáp ứng chuẩn hoàn tất. |
| 4 | Mở rộng | Thêm vai trò và cách đăng ký mới. |
| 5 | Làm rõ, cần xác nhận nội dung | Bổ sung cách diễn đạt trạng thái thất bại của luồng hiện tại. |
| 6 | Mở rộng | Thêm kênh và nền tảng triển khai chưa cam kết. |
| 7 | Thay đổi công việc triển khai | Cần đánh giá tác động nhưng không tự nó thêm khả năng người dùng. |

### Bài tập 2 — Thương lượng phạm vi trong Sprint

**Bối cảnh:** nhóm có Sprint Goal “người dùng hoàn tất một lượt đăng ký khóa học miễn phí”. Giữa Sprint, người phụ trách kinh doanh yêu cầu thêm thanh toán và gửi email tự động. Đồng thời QA phát hiện hai yêu cầu đăng ký đồng thời có thể vượt số chỗ.

Hãy xây phương án trao đổi với Product Owner gồm:

1. Việc nào cần làm để đạt Sprint Goal và DoD?
2. Việc nào là yêu cầu bổ sung có thể ưu tiên sau?
3. Developers cần đánh giá tác động kỹ thuật gì?
4. Nếu công sức tăng, có thể thương lượng phần nào của Sprint Backlog?
5. Cần công khai bằng chứng nào để tránh báo sai trạng thái Done?

**Hướng giải quyết tham khảo:** chống vượt số chỗ là điều kiện cần cho đăng ký hợp lệ, phải làm rõ và kiểm chứng. Thanh toán và email là khả năng mới, nên được tách và ưu tiên theo giá trị; không tự động đưa vào Sprint. Nếu việc sửa đồng thời tốn công hơn dự kiến, nhóm trao đổi với Product Owner để điều chỉnh phạm vi phù hợp, giữ Sprint Goal và DoD. Sprint Review cần trình diễn hành vi hoàn tất cùng những giới hạn được công bố.

### Bài tập 3 — Viết ranh giới cho một user story

Chọn user story **“Học viên xem danh sách khóa học phù hợp”** và viết:

- Một kết quả người dùng có thể kiểm chứng.
- Ba tiêu chí chấp nhận (bao gồm ít nhất một trường hợp lỗi hoặc dữ liệu rỗng).
- Hai khả năng nằm **ngoài phạm vi** của hạng mục.
- Một câu hỏi chưa rõ cần Product Owner xác nhận.
- Một dấu hiệu để quyết định rằng yêu cầu phát sinh là **mở rộng**, không chỉ làm rõ.

Sau đó trao đổi với người khác về trường hợp **thêm bộ lọc theo ngôn ngữ**: nếu mục tiêu và tiêu chí ban đầu đã cam kết lọc theo ngôn ngữ thì đó có thể là làm rõ; nếu chỉ cam kết hiển thị danh sách cơ bản thì đây có thể là khả năng mới. Kết luận phải dựa trên **cam kết và ngữ cảnh cụ thể**.

### Bài tập 4 — Tạo chính sách nhận thay đổi trong Kanban

Thiết kế chính sách ngắn cho nhóm có các cột **Sẵn sàng → Đang phát triển → Kiểm thử → Done**:

1. Ai tiếp nhận yêu cầu mới và ghi lại giá trị?
2. Khi nào cập nhật tiêu chí của hạng mục đang làm?
3. Khi nào tạo hạng mục mới cho khả năng bổ sung?
4. Điều gì xảy ra nếu WIP đã đạt giới hạn?
5. Làm sao đảm bảo một blocker hoặc lỗi chưa đạt DoD không bị chuyển thẳng sang Done?

**Gợi ý:** có quy tắc phân loại, người chịu trách nhiệm ưu tiên, giới hạn WIP minh bạch, chính sách cho việc khẩn cấp có tiêu chí rõ và điều kiện Done dựa trên sản phẩm được kiểm chứng.

## 14. Checklist khi một yêu cầu mới xuất hiện

Trước khi nhận việc hoặc thay đổi kế hoạch, nhóm có thể kiểm tra:

- [ ] Đã xác định **mốc phạm vi**: sản phẩm, release, Sprint hay hạng mục.
- [ ] Đã xem lại **mục tiêu người dùng** và kết quả đã thống nhất.
- [ ] Đã mô tả hành vi mới bằng ví dụ hoặc tiêu chí có thể kiểm chứng.
- [ ] Đã tách **điều bắt buộc để đúng/đạt DoD** khỏi **khả năng mới tùy chọn**.
- [ ] Đã kiểm tra tác động lên công sức, phụ thuộc, chất lượng và thời gian.
- [ ] Nếu là thay đổi phạm vi, đã trao đổi với người có thẩm quyền về ưu tiên và đánh đổi.
- [ ] Đã cập nhật Product Backlog/Sprint Backlog hoặc workflow phù hợp.
- [ ] Đã công bố rõ phần sẽ làm ngay, phần hoãn và phần loại trừ.
- [ ] Đã xác định bằng chứng để biết thay đổi đạt kết quả mong muốn.
- [ ] Những yêu cầu bắt buộc về bảo mật, quyền truy cập và chất lượng vẫn được tuân thủ.

Checklist không thay thế trao đổi trực tiếp. Với thay đổi nhỏ, vài câu hỏi là đủ; với thay đổi lớn hoặc rủi ro cao, cần ghi rõ quyết định, người chịu trách nhiệm và kế hoạch kiểm chứng.

## 15. Ghi nhớ

**Làm rõ yêu cầu** giúp nhóm hiểu và kiểm chứng chính xác hành vi đã thống nhất. **Mở rộng phạm vi** bổ sung khả năng, đối tượng, kết quả hoặc ranh giới mới. **Thay đổi công việc triển khai** có thể làm tăng công sức ngay cả khi chức năng không mở rộng. **Khắc phục lỗi và đáp ứng Definition of Done** là trách nhiệm chất lượng, không phải hạng mục tùy chọn để cắt nhằm làm đẹp tiến độ.

Trong Agile, mục tiêu không phải ngăn mọi thay đổi mà là **tiếp nhận thay đổi có căn cứ và quyết định minh bạch**: giữ giá trị người dùng làm trọng tâm, làm rõ bằng ví dụ, quản lý backlog theo ưu tiên, bảo vệ chất lượng và giao Increment nhỏ để học nhanh.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Requirement clarification** | Làm rõ hành vi, quy tắc hoặc tiêu chí của nhu cầu đã nằm trong ranh giới được thống nhất. |
| **Scope expansion** | Thêm khả năng, đối tượng, luồng hay kết quả vượt ranh giới đã thống nhất ở một cấp phạm vi cụ thể. |
| **Scope creep** | Phạm vi tăng dần không được quản lý và điều chỉnh ưu tiên, chi phí hoặc cam kết minh bạch. |
| **Product Backlog** | Danh sách công việc nổi lên, có thứ tự ưu tiên nhằm cải thiện sản phẩm. |
| **Sprint Goal** | Mục tiêu chung của Sprint, giúp Scrum Team lựa chọn và điều chỉnh cách thực hiện. |
| **Acceptance criteria** | Những điều kiện riêng của hạng mục để xác nhận hành vi được mong đợi. |
| **Definition of Done (DoD)** | Chuẩn chất lượng chung xác định Increment đã hoàn tất. |
| **Backlog refinement** | Hoạt động liên tục làm rõ, chia nhỏ và bổ sung hiểu biết cho Product Backlog Items. |
| **Vertical slice** | Lát cắt khả năng sản phẩm đi qua các thành phần cần thiết để tạo hành vi dùng được. |
| **WIP (Work in Progress)** | Số hạng mục đã bắt đầu nhưng chưa hoàn tất. |
| **Cycle time** | Thời gian từ khi bắt đầu xử lý đến khi hoàn tất theo quy ước đo của nhóm. |
| **Spike** | Hoạt động khám phá/kiểm chứng có phạm vi hoặc thời gian giới hạn nhằm giảm bất định trước quyết định. |
