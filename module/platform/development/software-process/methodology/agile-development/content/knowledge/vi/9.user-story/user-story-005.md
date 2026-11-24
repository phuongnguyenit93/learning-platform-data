# Phân biệt epic, user story, task, bug và spike

## 1. Vì sao cần phân biệt năm loại hạng mục?

Một Product Backlog trong phát triển phần mềm có thể chứa nhu cầu lớn cần nghiên cứu, chức năng đủ nhỏ để giao cho người dùng, việc kỹ thuật cần làm, lỗi phải khắc phục và câu hỏi chưa có lời giải. Nếu tất cả được ghi như nhau dưới tên “task”, nhóm rất dễ đánh mất **giá trị cần đạt**, ước lượng thiếu nhất quán, triển khai nhiều việc cùng lúc nhưng ít kết quả hoàn chỉnh.

Ví dụ, một nền tảng học trực tuyến nhận yêu cầu “Cải thiện việc học viên đăng ký và bắt đầu khóa học”. Trong cuộc họp, nhiều người đề xuất:

- Xây toàn bộ hệ thống đăng ký khóa học.
- Cho học viên đăng ký một khóa miễn phí.
- Tạo API ghi danh và thêm ràng buộc dữ liệu chống đăng ký trùng.
- Sửa lỗi người học được báo đăng ký thành công nhưng chưa có quyền học.
- Thử xem dịch vụ thanh toán đang dùng có hỗ trợ xác nhận giao dịch bất đồng bộ không.

Đó là năm kiểu công việc có mục đích khác nhau. Nhóm cần biết mục nào thể hiện **mục tiêu lớn**, mục nào bàn giao **giá trị sử dụng**, mục nào là **bước triển khai**, mục nào xử lý **sai lệch hiện có**, và mục nào tạo **thông tin cho quyết định**.

Trong phạm vi Agile, việc phân biệt giúp nhóm nối một nhu cầu với user story và các quyết định ưu tiên; phối hợp qua Scrum hoặc Kanban; dùng thực hành kỹ thuật XP để giữ chất lượng; cuối cùng quan sát **phản hồi sớm**, **sản phẩm tăng dần** và **luồng công việc** để cải tiến liên tục.

> **Lưu ý:** Epic, user story, task, bug và spike là các khái niệm/quy ước lập kế hoạch rất phổ biến, **không phải năm loại hạng mục bắt buộc do Scrum Guide định nghĩa**. Trong Scrum, *Product Backlog Item* (PBI) là thuật ngữ bao quát; nhóm có thể dùng nhãn phù hợp để quản lý công việc. Tránh biến cách phân loại của một công cụ quản lý dự án thành “quy định bắt buộc của Agile”.

## 2. Bảng phân biệt nhanh

| Loại hạng mục | Câu hỏi chính | Đầu ra mong đợi | Ví dụ với nền tảng học |
| --- | --- | --- | --- |
| **Epic** | Mục tiêu/nhóm nhu cầu lớn nào cần được giải quyết qua nhiều lát? | Phạm vi giá trị được chia thành các phần có thể ưu tiên và bàn giao | “Học viên có thể ghi danh và quản lý các khóa học của mình” |
| **User story** | Ai cần khả năng nào để đạt lợi ích gì? | Hành vi người dùng có thể kiểm chứng trong increment hoàn chỉnh | “Là học viên, tôi muốn đăng ký khóa miễn phí để bắt đầu học” |
| **Task** | Cần thực hiện bước cụ thể nào để hoàn thành công việc? | Một phần việc triển khai/kiểm thử/thiết kế đã thực hiện | “Tạo ràng buộc duy nhất cho đăng ký hiệu lực” |
| **Bug (defect)** | Hành vi thực tế sai so với điều đã được thống nhất ở đâu? | Sai lệch được sửa và có bằng chứng xác nhận | “Nhấn hai lần tạo hai đăng ký hiệu lực cho cùng khóa” |
| **Spike** | Cần giải đáp bất định nào trước khi cam kết thiết kế hoặc ước lượng? | Kết luận, bằng chứng, khuyến nghị và rủi ro còn lại | “Kiểm tra cách xử lý callback thanh toán gửi lặp” |

Một hạng mục có thể **đổi trạng thái hoặc được phân rã** khi nhóm hiểu rõ hơn. Epic có thể được chia thành story; story có task; một bug có thể phát hiện trong quá trình làm story; một spike có thể dẫn tới story mới hoặc khiến nhóm hủy một phương án. Các mối quan hệ đó hữu ích nhưng không tạo thành cây phân cấp tuyệt đối cho mọi trường hợp.

### Đừng dùng “độ lớn” làm tiêu chí duy nhất

Epic thường lớn hơn một user story, nhưng hai hạng mục cùng tốn ba ngày vẫn có thể khác loại: một story mang lại hành vi sử dụng mới; một spike dùng ba ngày để kiểm tra tính khả thi; một bug dùng ba ngày để phục hồi hành vi đã hứa. **Mục đích và tiêu chí hoàn tất** quan trọng hơn tên gọi và số giờ.

## 3. Epic: phạm vi giá trị lớn cần chia thành những lát nhỏ

**Epic** mô tả một mục tiêu hoặc tập hợp nhu cầu quá rộng để thực hiện, kiểm chứng và bàn giao như một hạng mục nhỏ. Nó thường tồn tại qua nhiều lần lập kế hoạch hoặc nhiều đợt phát hành. Epic giúp liên kết các story với một **kết quả sản phẩm**, tránh để backlog trở thành danh sách chức năng rời rạc.

**Ví dụ epic:**

> “Giúp học viên tự đăng ký, xem và quản lý quyền học đối với các khóa của mình, giảm nhu cầu liên hệ hỗ trợ để xác nhận ghi danh.”

Một epic hữu ích có thể ghi mục tiêu, nhóm người dùng chịu ảnh hưởng, bằng chứng ban đầu, ranh giới và các giả thuyết còn cần kiểm chứng. Epic không nhất thiết là cam kết phải xây tất cả khả năng được liệt kê lúc đầu. Khi hành vi thực tế thay đổi, nội dung hoặc thứ tự các story thuộc epic có thể được điều chỉnh.

### Chia epic theo giá trị sử dụng

Ví dụ các lát giá trị ứng viên cho epic trên:

1. Học viên đã đăng nhập ghi danh được vào **khóa miễn phí đang mở** và mở bài đầu.
2. Học viên xem được **danh sách khóa đã ghi danh** và quay lại học.
3. Học viên đủ điều kiện **hủy ghi danh** và thấy rõ hệ quả theo chính sách.
4. Học viên **đăng ký khóa có phí** sau khi giao dịch được xác nhận hợp lệ.

Các lát này có thể mang lại giá trị riêng và có thể kiểm chứng; không nhất thiết phải phát triển theo đúng thứ tự nêu trên. Product Owner và nhóm dùng mức độ giá trị, rủi ro, phụ thuộc và phản hồi để ưu tiên.

**Cách chia kém hiệu quả:** “Epic đăng ký” được tách thành “Story database”, “Story backend”, “Story frontend”, mỗi story chỉ được xem là xong khi các story khác hoàn thành. Đây thực chất là phân công theo tầng kỹ thuật. Nếu không có người dùng nào sử dụng được sau từng story, nhóm chưa nhận được lợi ích của bàn giao tăng dần.

### Khi nào đóng một epic?

Không nhất thiết chờ hoàn thành 100% các ý tưởng từng được ghi. Một epic có thể được xem là đáp ứng mục tiêu khi các outcome cần thiết đã được kiểm chứng và phần công việc còn lại không còn đáng ưu tiên; hoặc có thể bị dừng do bằng chứng mới. Quy định “đóng epic” là chính sách quản lý của nhóm/tổ chức, cần được diễn đạt minh bạch.

## 4. User story: nhu cầu nhỏ đủ để trao đổi và kiểm chứng giá trị

**User story** mô tả một khả năng từ góc nhìn người nhận giá trị. Mẫu phổ biến:

> Là **[vai trò/người hưởng lợi]**, tôi muốn **[khả năng]**, để **[lợi ích hoặc kết quả mong muốn]**.

Ví dụ:

> “Là học viên đã đăng nhập, tôi muốn ghi danh vào một khóa miễn phí đang mở để có thể bắt đầu học ngay từ trang chi tiết.”

Story nhấn mạnh **ai** và **vì sao**. Câu một dòng không tự động là yêu cầu đầy đủ. Nhóm cần trao đổi các quy tắc và ví dụ quan trọng: điều kiện ghi danh, quyền truy cập, hành vi khi bấm lại, phản hồi khi khóa đã đóng.

### Mô hình 3C giúp hoàn thiện story

- **Card:** mô tả ngắn nhu cầu để tạo điểm bắt đầu.
- **Conversation:** trao đổi giữa người hiểu nghiệp vụ, sản phẩm, thiết kế, lập trình và kiểm thử.
- **Confirmation:** xác định tiêu chí chấp nhận và ví dụ để biết đã đáp ứng đúng nhu cầu.

Một story tốt là **lời mời trao đổi về kết quả**. Nhóm có thể thay đổi cách triển khai nếu tìm ra phương án dễ dùng hơn, an toàn hơn hoặc ít tốn kém hơn, miễn đáp ứng các điều kiện đã thống nhất.

### Ví dụ tiêu chí chấp nhận

Với story ghi danh khóa miễn phí:

~~~gherkin
Feature: Ghi danh khóa học miễn phí

  Scenario: Ghi danh thành công
    Given học viên đã đăng nhập
    And khóa học miễn phí đang nhận ghi danh
    And học viên chưa có đăng ký hiệu lực cho khóa đó
    When học viên xác nhận ghi danh
    Then hệ thống ghi nhận đúng một đăng ký hiệu lực
    And học viên có thể mở nội dung được phép học
    And hệ thống hiển thị xác nhận thành công

  Scenario: Người học gửi yêu cầu lặp lại
    Given học viên đã có đăng ký hiệu lực
    When học viên gửi lại yêu cầu ghi danh cùng khóa
    Then hệ thống không tạo đăng ký hiệu lực trùng
    And hiển thị trạng thái phù hợp

  Scenario: Khóa không còn nhận ghi danh
    Given khóa học đã đóng ghi danh
    When học viên yêu cầu ghi danh
    Then hệ thống từ chối tạo đăng ký mới
    And không cấp thêm quyền học
~~~

Đây là tiêu chí theo một **chính sách minh họa**. Trong dự án thật, Product Owner hoặc người có thẩm quyền nghiệp vụ cần xác nhận các từ “đang nhận”, “đăng ký hiệu lực” và cách xử lý đăng ký lại. Không tự suy quy tắc từ cách đặt tên bảng hay từ trải nghiệm của sản phẩm khác.

### Gợi ý INVEST để rà soát story

| Chữ | Ý nghĩa | Câu hỏi kiểm tra |
| --- | --- | --- |
| **I – Independent** | Ít phụ thuộc | Có thể đưa đến Done mà không phải đợi toàn bộ epic hoàn tất không? |
| **N – Negotiable** | Có thể thương lượng | Nhóm còn lựa chọn được cách triển khai, phạm vi và xử lý chi tiết không? |
| **V – Valuable** | Có giá trị | Ai nhận lợi ích cụ thể khi story hoàn tất? |
| **E – Estimable** | Đủ rõ để ước lượng | Nhóm có hiểu việc cần làm và các rủi ro chính không? |
| **S – Small** | Đủ nhỏ | Có thể hoàn thành trọn vẹn trong nhịp làm việc ngắn phù hợp không? |
| **T – Testable** | Kiểm thử được | Có thể quan sát hành vi thành công và thất bại không? |

INVEST là công cụ gợi ý, không phải bài kiểm tra bắt buộc. Một số phụ thuộc kỹ thuật có thể không tránh được; mục tiêu là làm chúng đủ rõ và giảm phạm vi để có thể giao giá trị sớm.

## 5. Task: bước thực hiện cụ thể để đưa story đến Done

**Task** là công việc mà nhóm cần làm để tạo ra kết quả của một story hoặc đáp ứng một mục tiêu kỹ thuật/vận hành cụ thể. Task thường được diễn đạt bằng hành động: triển khai, cấu hình, thiết kế, kiểm thử, rà soát, cập nhật tài liệu.

Ví dụ, để hoàn thành story “Ghi danh khóa miễn phí”, nhóm có thể tự chia thành:

- Thiết kế thông báo thành công và lỗi phù hợp với hành vi người học.
- Triển khai endpoint ghi danh và kiểm tra quyền phía máy chủ.
- Thêm quy tắc/ràng buộc dữ liệu chống tạo đăng ký hiệu lực trùng.
- Tích hợp nút ghi danh với trạng thái thật của hệ thống.
- Viết kiểm thử cho đăng ký thành công, khóa đóng và yêu cầu gửi lặp.
- Chuẩn bị khả năng theo dõi lỗi ghi danh sau phát hành.

**Điều quan trọng:** đánh dấu từng task “Done” chưa đồng nghĩa story đã hoàn tất. Chỉ khi hành trình sử dụng được tích hợp, thỏa acceptance criteria và Definition of Done phù hợp thì nhóm mới có một increment có thể đánh giá.

### Task có nhất thiết phải nằm dưới user story?

Không. Có thể tồn tại công việc bảo trì, vận hành, nâng cấp công cụ, cải thiện pipeline hoặc chuẩn bị môi trường không gắn trực tiếp vào một story của người dùng. Nhóm nên gắn task với **mục đích cụ thể và điều kiện hoàn tất**, ví dụ “Bổ sung cảnh báo khi hàng đợi sự kiện thanh toán vượt ngưỡng để vận hành kịp xử lý”.

Việc dùng task độc lập hay biến công việc đó thành PBI phụ thuộc mức tác động, cách quản lý backlog và chính sách của nhóm. **Không cần bịa ra vai trò người dùng** cho một nhiệm vụ thuần kỹ thuật để hợp thức hóa nó thành user story.

### Phân biệt task và story qua một câu hỏi

Nếu chỉ hoàn thành hạng mục đó, người dùng hoặc bên nhận giá trị **có thể làm được việc có ý nghĩa nào**? Nếu câu trả lời là “chưa, còn phải hoàn thiện nhiều thành phần khác”, nó có thể là task triển khai hơn là một story có giá trị độc lập.

## 6. Bug: sai lệch giữa hành vi thực tế và kỳ vọng đã xác lập

**Bug (defect)** là lỗi khiến phần mềm hoạt động không đúng với hành vi hoặc chất lượng cần đáp ứng. Căn cứ có thể đến từ acceptance criteria, quy tắc nghiệp vụ, hợp đồng API, yêu cầu bảo mật, ràng buộc dữ liệu hay đặc tính vốn phải có của hệ thống.

Ví dụ:

> Học viên nhấn “Ghi danh” hai lần do mạng chậm. Hệ thống tạo hai bản ghi đăng ký hiệu lực trong khi chính sách chỉ cho phép một đăng ký hiệu lực cho mỗi học viên–khóa.

Đây là bug vì hành vi thực tế **vi phạm quy tắc đã thống nhất**, khác với một đề xuất chức năng mới “Cho phép học viên đăng ký nhiều khóa cùng lúc”.

### Tách bug khỏi thay đổi nhu cầu

| Tình huống | Phân loại thường phù hợp | Vì sao |
| --- | --- | --- |
| Hệ thống đã cam kết chỉ tạo một đăng ký nhưng tạo hai | **Bug** | Hành vi vi phạm kỳ vọng hiện có |
| Người học muốn thêm chức năng hủy đăng ký, trước đây chưa hỗ trợ | **User story mới** | Năng lực/nghiệp vụ mới cần được ưu tiên |
| Người dùng nói “Màu nút chưa đẹp” nhưng chưa có yêu cầu/tiêu chí rõ | **Phản hồi hoặc đề xuất cải tiến** | Chưa đủ căn cứ gọi là defect |
| Trang ghi danh bị lỗi phân quyền, người A thấy dữ liệu người B | **Bug quan trọng về bảo mật** | Vi phạm quyền truy cập cần được khắc phục |
| Chưa biết vì sao endpoint chậm bất thường sau tăng tải | **Điều tra bug/sự cố, có thể cần spike giới hạn** | Có dấu hiệu sai lệch, cần tìm nguyên nhân trước khi chọn cách sửa |
| Cần tăng khả năng tải lên mức kinh doanh mới yêu cầu, hệ thống hiện đạt mức cũ | **Yêu cầu cải tiến/technical work**, tùy cam kết | Thay đổi ngưỡng không luôn là bug của hành vi hiện tại |

Phân loại phụ thuộc **hợp đồng sản phẩm và bối cảnh**, không chỉ vào mức độ khó chịu của người dùng.

### Bug phát hiện khi story chưa Done

Giả sử lập trình viên và kiểm thử đang làm story “Ghi danh khóa miễn phí”, nhưng kiểm thử phát hiện yêu cầu gửi lặp tạo đăng ký trùng. Nếu đây là tiêu chí chấp nhận chưa đạt, story **chưa được xem là Done**. Nhóm sửa sai lệch trong cùng phạm vi story; có thể tạo ticket bug con để tiện theo dõi, nhưng không được đánh dấu story hoàn thành rồi coi lỗi còn lại là việc tương lai nếu nó vi phạm Definition of Done.

### Bug phát hiện sau khi đã bàn giao

Nếu tính năng đã hoàn thành và người dùng gặp lỗi trong vận hành, nhóm nên ghi bug có đủ dữ liệu để tái hiện và đánh giá tác động. Bug này có thể là PBI được Product Owner ưu tiên, hoặc đi qua cơ chế xử lý sự cố riêng nếu khẩn cấp. Không có quy định mọi bug đều phải chờ Sprint sau; sự cố ảnh hưởng bảo mật, dữ liệu hoặc dịch vụ cần xử lý theo mức độ rủi ro và quy trình đã thống nhất.

### Mẫu báo bug có thể hành động

~~~text
Tiêu đề: Bấm Ghi danh lặp tạo hai đăng ký hiệu lực
Bối cảnh: Khóa miễn phí đang mở, học viên đã đăng nhập
Các bước tái hiện:
  1. Mở trang chi tiết khóa chưa ghi danh
  2. Gửi hai yêu cầu ghi danh gần như đồng thời
Kết quả thực tế: Có hai đăng ký hiệu lực cho một học viên–khóa
Kết quả mong đợi: Có tối đa một đăng ký hiệu lực theo quy tắc
Ảnh hưởng: Dữ liệu sai; có thể ảnh hưởng báo cáo/quyền học
Môi trường và phiên bản: <thông tin thực tế>
Bằng chứng: <log hoặc yêu cầu đã được ẩn thông tin nhạy cảm>
Trạng thái/ưu tiên: <do nhóm đánh giá sau khi xác minh>
~~~

Đừng đưa mật khẩu, token, dữ liệu học viên hoặc thông tin nhạy cảm vào ticket để chứng minh lỗi. Cần cung cấp bằng chứng đủ để tái hiện mà vẫn tuân thủ quy tắc bảo vệ dữ liệu.

### Severity khác priority

- **Severity (mức nghiêm trọng):** tác động của lỗi lên chức năng, dữ liệu, an toàn, bảo mật, số người chịu ảnh hưởng.
- **Priority (mức ưu tiên):** lỗi cần được giải quyết sớm đến đâu trong bối cảnh mục tiêu, rủi ro, chi phí và phụ thuộc hiện tại.

Lỗi có tác động nghiêm trọng thường cần ưu tiên cao, nhưng hai khái niệm không phải một. Chẳng hạn, lỗi thẩm mỹ xuất hiện ở trang chủ trước một chiến dịch quan trọng có thể được ưu tiên sửa sớm dù không gây mất dữ liệu; ngược lại, một lỗi hiếm gặp cần được thẩm định mức rủi ro trước khi chọn thứ tự xử lý. Ưu tiên xử lý sự cố có thể được điều chỉnh nhanh khi xuất hiện bằng chứng mới.

## 7. Spike: công việc học hỏi để giảm bất định

**Spike** là hoạt động nghiên cứu, thử nghiệm hoặc chứng minh khái niệm được **giới hạn rõ câu hỏi và thời gian**, nhằm giúp nhóm ra quyết định phát triển. Spike thường xuất hiện khi chưa đủ thông tin để chọn cách triển khai, ước lượng hoặc đánh giá rủi ro.

Ví dụ, trước khi triển khai khóa trả phí, nhóm chưa biết dịch vụ thanh toán hiện có xử lý ra sao nếu callback gửi lặp hoặc đến sai thứ tự. Một spike hợp lý có thể là:

> “Trong tối đa hai ngày làm việc, xác minh hành vi callback lặp/đảo thứ tự của dịch vụ thanh toán trên môi trường thử nghiệm; đối chiếu tài liệu và đưa ra khuyến nghị xử lý tính idempotent kèm rủi ro còn lại.”

**Đầu ra của spike** không nhất thiết là tính năng sản phẩm. Nó có thể là bảng kết quả thử nghiệm, mã mẫu giới hạn, quyết định thiết kế, danh sách rủi ro, một ước lượng được cập nhật hoặc kết luận “chưa đủ dữ liệu, cần đổi phương án”.

### Spike tốt nên có cấu trúc

| Thành phần | Ví dụ |
| --- | --- |
| **Câu hỏi** | Callback giao dịch lặp có thể được xử lý an toàn bằng cơ chế nào? |
| **Lý do quan trọng** | Nếu sai, học viên có thể được cấp quyền nhiều lần hoặc trạng thái thanh toán không nhất quán |
| **Phạm vi** | Thử webhook trên sandbox với sự kiện lặp, thiếu, đến trễ |
| **Giới hạn thời gian** | Tối đa hai ngày; đánh giá lại nếu chưa giải đáp |
| **Đầu ra** | Bằng chứng thử, lựa chọn khuyến nghị, phụ thuộc, rủi ro còn lại |
| **Quyết định sau spike** | Chọn phương án triển khai, chia user story hoặc hoãn tích hợp |

Một spike có thể là **technical spike** (chủ yếu kiểm tra tính khả thi kỹ thuật) hoặc **functional/knowledge spike** (làm rõ nghiệp vụ, quy tắc, dữ liệu hoặc tính khả dụng). Điều quan trọng là câu hỏi chưa rõ và cách biết khi nào đã học đủ.

### Ba điều spike không phải

1. **Không phải cái cớ cho nghiên cứu vô hạn.** Nếu không có câu hỏi và giới hạn, hoạt động dễ kéo dài mà không tạo quyết định.
2. **Không mặc nhiên là user story mang giá trị sử dụng.** Nó giúp giảm rủi ro, nhưng mã thử nghiệm chưa được kiểm thử/tích hợp theo DoD không nên được gọi là increment đã bàn giao.
3. **Không thay thế việc thực hiện story.** Sau khi quyết định phương án, nhóm vẫn cần công việc triển khai, kiểm thử và bàn giao khả năng thật.

Nếu một đoạn mã trong spike hữu ích, nhóm có thể tái sử dụng **sau khi đánh giá và bổ sung chất lượng cần thiết**. Không nên tự động đưa mã thử nghiệm lên production chỉ vì kết quả nghiên cứu đã trả lời câu hỏi.

## 8. Mối quan hệ giữa các loại hạng mục trong một ví dụ

~~~mermaid
flowchart TD
    A["Epic: Học viên tự quản lý việc ghi danh"] --> B["Story 1: Ghi danh khóa miễn phí"]
    A --> C["Story 2: Xem các khóa của tôi"]
    A --> D["Ứng viên story 3: Đăng ký khóa trả phí"]
    B --> E["Task: API + kiểm tra quyền"]
    B --> F["Task: UI + xử lý trạng thái"]
    B --> G["Task: Kiểm thử tích hợp"]
    E -. "Kiểm thử thấy sai lệch" .-> H["Bug: Ghi danh lặp tạo bản ghi trùng"]
    D -. "Chưa rõ hợp đồng thanh toán" .-> I["Spike: Kiểm tra callback lặp"]
    I -. "Kết luận và rủi ro" .-> D
~~~

Sơ đồ mô tả **quan hệ minh họa**, không bắt buộc bug nằm dưới task hoặc spike luôn nằm dưới story. Một bug ảnh hưởng nhiều story có thể được theo dõi độc lập; một spike khám phá có thể thực hiện trước khi nhóm quyết định có tạo story hay không.

### Một backlog có thể ghi năm loại hạng mục ra sao?

| ID minh họa | Loại | Tóm tắt | Tiêu chí hoàn tất phù hợp |
| --- | --- | --- | --- |
| EP-01 | Epic | Học viên tự ghi danh và quản lý khóa | Outcome liên quan được đánh giá; các lát cần thiết được bàn giao hoặc có quyết định dừng |
| US-01 | User story | Học viên ghi danh khóa miễn phí | Chạy luồng thật, thỏa acceptance criteria và DoD |
| TASK-01 | Task | Bổ sung kiểm tra quyền và ràng buộc dữ liệu | Thay đổi được tích hợp, được kiểm tra theo công việc |
| BUG-01 | Bug | Ghi danh lặp tạo dữ liệu trùng | Lỗi được tái hiện, sửa, kiểm thử hồi quy và xác minh |
| SPIKE-01 | Spike | Kiểm tra callback thanh toán gửi lặp | Có bằng chứng, khuyến nghị và quyết định tiếp theo trong timebox |

Không nên so sánh “năm hạng mục Done” trong bảng như năm đơn vị giá trị tương đương. Mỗi loại có bản chất và đầu ra khác nhau.

## 9. Cách quyết định loại hạng mục khi nhận một yêu cầu

Khi một yêu cầu xuất hiện, thử hỏi theo thứ tự:

1. **Có hành vi nào đã thống nhất nhưng hệ thống làm sai không?** Nếu có, ghi nhận và xác minh **bug**; xác định mức tác động/khẩn cấp.
2. **Vấn đề chính là chưa biết điều gì quan trọng để lựa chọn không?** Nếu có, tạo một **spike có giới hạn** hoặc hoạt động discovery tương ứng.
3. **Mục tiêu quá rộng, gồm nhiều hành vi có thể bàn giao độc lập không?** Nếu có, dùng **epic** để gom phạm vi và tách story.
4. **Có một hành vi có giá trị, đủ nhỏ và có thể kiểm chứng từ góc nhìn người hưởng lợi không?** Nếu có, mô tả **user story** cùng tiêu chí chấp nhận.
5. **Đây là bước thực hiện cụ thể để hoàn thành một kết quả đã rõ?** Nếu có, tạo **task** phù hợp.

Các câu hỏi này là **gợi ý phân tích**, không phải thuật toán cứng. Một sự cố có thể đồng thời cần bug để theo dõi sai lệch và spike để tìm nguyên nhân khó; kết quả spike có thể dẫn đến task và kiểm thử mới.

### Ví dụ phân loại những câu thường gặp

| Yêu cầu nhận được | Loại thường phù hợp | Lý do |
| --- | --- | --- |
| “Xây toàn bộ khả năng học viên tự quản lý khóa.” | Epic | Phạm vi lớn, nhiều hành vi người dùng |
| “Là học viên, tôi muốn xem khóa đã đăng ký để quay lại học.” | User story | Có đối tượng, lợi ích và hành vi kiểm chứng được |
| “Viết integration test cho luồng ghi danh.” | Task | Một bước để hoàn thành/đảm bảo chất lượng |
| “Mỗi lần tải lại trang, tiến độ bài học bị mất.” | Bug nếu đã có cam kết lưu tiến độ | Sai hành vi đã mong đợi, cần xác minh |
| “Thử ba phương án cache xem có đáp ứng tải dự kiến không.” | Spike | Trả lời bất định về kỹ thuật |
| “Tăng độ tin cậy và hiệu năng hệ thống.” | Epic/initiative hoặc mục tiêu kỹ thuật cần phân rã | Quá rộng, cần nêu tiêu chí và các lát cụ thể |
| “Tạo bảng mới để hỗ trợ chức năng ghi danh.” | Task | Chi tiết triển khai, không tự nó là lợi ích người dùng |
| “Thêm chức năng đặt lịch học theo múi giờ.” | User story hoặc epic tùy phạm vi | Nhu cầu mới; chia theo kết quả và biến thể |
| “Không biết dịch vụ nhắc học có bị giới hạn tốc độ gửi.” | Spike | Cần đo/tra cứu giới hạn trước khi thiết kế |
| “Lỗi tải trang sau bản phát hành hôm qua.” | Bug/sự cố cần triage | Hệ thống hiện hoạt động sai; mức khẩn cần xác định |
| “Xem học viên muốn điểm thưởng hay nhắc học.” | Hoạt động discovery/spike có câu hỏi rõ | Đang kiểm chứng nhu cầu, chưa đủ căn cứ cam kết tính năng |

**Phản ví dụ:** “Spike xây module thanh toán hoàn chỉnh trong ba tháng” không phải spike tốt vì chưa nêu câu hỏi cần học và phạm vi gần bằng cả dự án. “Story tạo API” có thể hợp lý khi khách hàng sử dụng sản phẩm chính là nhà phát triển tích hợp API, nhưng cần nói rõ hành vi và giá trị đối với họ; chỉ có tên endpoint chưa đủ.

## 10. Sắp xếp ưu tiên và ước lượng: đừng trộn các đơn vị

Product Owner hoặc người chịu trách nhiệm sản phẩm cần xem xét **giá trị, rủi ro, mức khẩn cấp, phụ thuộc và công sức** khi ưu tiên. Không thể suy từ tên loại hạng mục rằng “bug luôn trước story” hoặc “epic có giá trị cao hơn spike”. Ví dụ:

- Bug lộ dữ liệu cá nhân có thể cần xử lý ngay theo quy trình sự cố.
- Spike ngắn giúp tránh cam kết sai một kiến trúc đắt tiền có thể có giá trị thực hiện rất sớm.
- Story có giá trị sử dụng rõ ràng có thể được ưu tiên trước một epic tham vọng nhưng chưa có bằng chứng.
- Task dọn tài liệu nội bộ có thể được gộp vào việc hoàn tất story hoặc đưa vào công việc cải tiến theo mức tác động.

### Ước lượng theo mục đích

**Epic** thường dùng đánh giá tương đối để hiểu phạm vi và quyết định đầu tư; đừng giả vờ có ước lượng chính xác khi các story còn chưa được khám phá. **User story** có thể được ước lượng tương đối hoặc dự báo theo throughput/cycle time của nhóm. **Task** có thể chia để phối hợp và xác định rủi ro; không nhất thiết cần story point riêng. **Bug** cần đánh giá tác động và độ khó sau khi đủ dữ liệu. **Spike** nên có timebox và đầu ra học hỏi trước khi dùng kết quả để lập kế hoạch chi tiết.

Nếu nhóm có dùng story point, không nên coi “1 point của bug = 1 point của story” như một đơn vị giá trị; story point cũng **không phải số giờ cố định** và không phù hợp để xếp hạng năng suất cá nhân giữa nhóm.

### Đo dòng công việc đúng cách

Kanban giúp thấy trạng thái công việc và giới hạn Work in Progress (WIP). Những chỉ số như **throughput**, **cycle time**, **work item age** và **WIP** có ích để tìm tắc nghẽn, nhưng cần biết các loại hạng mục có kích thước và đầu ra khác nhau.

Ví dụ, một tuần nhóm hoàn tất 12 task kỹ thuật nhưng không story nào đạt DoD; con số “12 việc Done” chưa chứng minh đã giao được giá trị mới. Ngược lại, một spike hoàn tất và giúp loại bỏ một giải pháp có nguy cơ cao có thể tạo giá trị ra quyết định dù không phát hành tính năng.

Khi so sánh xu hướng, nhóm có thể phân biệt loại công việc, định nghĩa điểm bắt đầu/kết thúc nhất quán và xem cùng chất lượng/outcome. Các số liệu dùng để cải thiện hệ thống công việc, không phải làm bảng xếp hạng lập trình viên.

## 11. Sử dụng trong Scrum, Kanban và XP

### Scrum: Product Backlog Item không phụ thuộc một hệ thống nhãn cố định

Product Backlog là danh sách công việc cần thiết để cải thiện sản phẩm, do Product Owner chịu trách nhiệm quản lý và sắp xếp thứ tự. Scrum không bắt buộc phần mềm quản lý có đúng năm loại Epic/Story/Task/Bug/Spike. Điều quan trọng là hạng mục đủ minh bạch, có thể được chọn và thực hiện để hướng tới Product Goal.

- **Product Backlog refinement:** làm rõ, chia nhỏ và ước lượng hạng mục cần thiết; xử lý điều chưa biết, xác nhận giá trị và rủi ro.
- **Sprint Planning:** Scrum Team thống nhất Sprint Goal và chọn công việc dựa trên ưu tiên và năng lực hiện có; có thể xem xét story, bug hoặc công việc kỹ thuật cần cho mục tiêu.
- **Sprint Backlog:** Developers có thể phân rã hạng mục đã chọn thành task và thích ứng kế hoạch trong Sprint.
- **Definition of Done:** một PBI góp phần tạo increment chỉ được xem là hoàn tất khi increment đạt mức chất lượng cần thiết. Các tiêu chí chấp nhận của story bổ sung, không thay thế DoD.
- **Sprint Review:** xem increment, phản hồi của stakeholder và điều chỉnh Product Backlog, không chỉ kiểm đếm ticket.

Một bug phát hiện trong story trước khi DoD là vấn đề phải xử lý để hoàn tất story. Với sự cố mới khẩn cấp trong Sprint, nhóm trao đổi về ảnh hưởng tới Sprint Goal và điều chỉnh theo thực tế, thay vì mặc định “Scrum cấm làm bug trong Sprint”.

### Kanban: làm rõ loại việc, chính sách luồng và mức ưu tiên

Một bảng Kanban có thể phân biệt story, bug, spike hoặc các loại dịch vụ khác bằng nhãn và chính sách rõ. Chẳng hạn, nhóm có thể có quy tắc xử lý **expedite** cho sự cố khẩn cấp, hạn chế WIP cho nghiên cứu, và chính sách review trước khi một story được tính là hoàn thành.

Không cần tạo năm bảng riêng nếu điều đó làm mất khả năng nhìn toàn bộ luồng. Điều quan trọng là quan sát **công việc bị chặn, tuổi công việc đang làm và khả năng bàn giao**, rồi điều chỉnh chính sách khi có bằng chứng.

### XP: giữ khả năng phát hiện và sửa lỗi sớm

Các thực hành như kiểm thử tự động, tích hợp liên tục, refactoring, pair programming khi phù hợp và thiết kế đơn giản giúp:

- Story hoàn tất với hành vi có thể kiểm thử.
- Bug được phát hiện sớm và có kiểm thử hồi quy để hạn chế tái diễn.
- Kết quả spike được biến thành thiết kế/triển khai đáng tin cậy nếu được chọn.
- Nhóm có thể tiếp tục chia nhỏ và thay đổi theo phản hồi mà không tích lũy quá nhiều rủi ro kỹ thuật.

**Framework hay công cụ không quyết định được chất lượng phân loại.** Chất lượng đến từ việc nhóm hiểu rõ mục đích của từng hạng mục, cách xác nhận hoàn tất và mối liên hệ với kết quả sản phẩm.

## 12. Những lỗi phân loại thường gặp

| Phản mẫu | Vấn đề | Điều chỉnh |
| --- | --- | --- |
| Gọi mọi ticket là user story | Không phân biệt nhu cầu với việc triển khai hoặc khám phá | Dùng nhãn theo mục đích; giữ rõ outcome của story |
| Epic chỉ là một story viết dài | Không có cách chia và ưu tiên bàn giao | Tách theo hành vi người dùng có thể kiểm chứng |
| Story “Là developer, tôi muốn tạo bảng dữ liệu” khi không ai trực tiếp hưởng lợi từ bảng | Story kỹ thuật giả tạo, giá trị mơ hồ | Xem là task trong story phù hợp hoặc công việc kỹ thuật có lý do rõ |
| Đóng story dù acceptance criteria chưa đạt | Increment chưa thực sự hoàn chỉnh, lỗi bị đẩy về sau | Giữ story chưa Done và sửa lỗi bắt buộc |
| Mọi đề nghị thay đổi đều bị coi là bug | Backlog lỗi phình lên và khó đánh giá sai lệch thật | Kiểm tra hành vi đã cam kết; nhu cầu mới nên được ưu tiên như thay đổi |
| Bug không có bước tái hiện và ảnh hưởng | Tốn thời gian đoán, khó ưu tiên | Ghi bối cảnh, thực tế, mong đợi và bằng chứng phù hợp |
| Spike không có câu hỏi/timebox | Nghiên cứu kéo dài không sinh quyết định | Chỉ rõ bất định, đầu ra và giới hạn |
| Mã prototype của spike được dùng ngay trong production | Bỏ qua chất lượng, vận hành, bảo mật | Chuyển thành công việc delivery và đáp ứng DoD |
| Chia task theo tầng rồi gọi từng task là “increment” | Không có hành vi người dùng hoàn chỉnh để học sớm | Hoàn thiện lát dọc xuyên các tầng |
| Đánh giá hiệu suất theo tổng ticket Done | Khuyến khích chia nhỏ hình thức và né việc khó | Kết hợp outcome, chất lượng và số liệu luồng có bối cảnh |

## 13. Bài thực hành: phân loại và thiết kế backlog

**Tình huống:** Nền tảng học trực tuyến muốn hỗ trợ người học trả phí. Hiện hệ thống chỉ có khóa miễn phí. Đội kỹ thuật chưa biết dịch vụ thanh toán mới hỗ trợ callback gửi lặp hay không. Đồng thời, bản hiện tại có lỗi đôi khi tạo đăng ký trùng cho khóa miễn phí.

Hãy phân loại những mục sau và nêu lý do:

1. “Cho phép học viên mua khóa, theo dõi trạng thái thanh toán và xử lý hoàn tiền theo chính sách.”
2. “Là học viên, tôi muốn biết giao dịch đã được xác nhận trước khi truy cập khóa trả phí.”
3. “Triển khai endpoint nhận webhook thanh toán kèm kiểm tra chữ ký.”
4. “Ghi danh khóa miễn phí tạo hai bản ghi hiệu lực khi gửi đồng thời.”
5. “Trong tối đa một ngày, thử xem dịch vụ thanh toán xử lý callback gửi lặp/đến trễ như thế nào và ghi đề xuất idempotency.”
6. “Thêm chức năng xem lịch sử giao dịch cho học viên ở lần phát hành sau.”

**Gợi ý đáp án:**

| Mục | Loại gợi ý | Giải thích |
| --- | --- | --- |
| 1 | **Epic** | Bao gồm nhiều hành vi và quy tắc nghiệp vụ, khó hoàn tất trong một lát nhỏ |
| 2 | **User story** | Có người hưởng lợi, kết quả và khả năng kiểm chứng; cần làm rõ trạng thái giao dịch |
| 3 | **Task** | Công việc kỹ thuật để hỗ trợ một story/increment đã chọn |
| 4 | **Bug** | Sai lệch so với quy tắc không tạo đăng ký hiệu lực trùng |
| 5 | **Spike** | Mục tiêu là giảm bất định, có thời hạn và đầu ra là bằng chứng/khuyến nghị |
| 6 | **User story ứng viên** | Có thể tạo giá trị sử dụng, nhưng cần mô tả vai trò, lợi ích và tiêu chí chấp nhận trước khi ưu tiên |

Sau khi phân loại, hãy tự làm thêm:

- Viết **ba tiêu chí chấp nhận** cho mục 2, trong đó có trường hợp giao dịch được xác nhận, còn đang chờ và bị từ chối.
- Chia mục 1 thành **hai hoặc ba lát dọc** có thể bàn giao và kiểm chứng độc lập.
- Chọn mức ưu tiên giữa mục 4 và mục 5 dựa trên **tác động lỗi hiện tại**, rủi ro dữ liệu và thời điểm cần quyết định tích hợp; giải thích vì sao không thể chỉ nhìn loại ticket để xếp thứ tự.
- Nêu điều kiện kết thúc mục 5: **bằng chứng nào đủ để chọn thiết kế** và điều gì phải được triển khai/kiểm thử riêng sau đó?

### Ví dụ một cách chia epic thanh toán

**Lát A – Tra cứu trạng thái đơn hàng:** học viên có một đơn đã tạo có thể xem trạng thái có ý nghĩa; hệ thống phân quyền và không báo “đã thanh toán” nếu chưa có xác nhận hợp lệ.

**Lát B – Thanh toán bằng một phương thức:** học viên tạo giao dịch, được ghi nhận theo trạng thái thật, quyền học chỉ cấp sau xác nhận hợp lệ; xử lý retry và callback trùng an toàn.

**Lát C – Lịch sử và xử lý ngoại lệ:** học viên tra cứu giao dịch trước đó; bộ phận hỗ trợ có công cụ xác minh trường hợp cần can thiệp theo quyền được cấp.

Đây chỉ là **các lát ứng viên**; không được xem Lát A đã tạo khả năng mua khóa nếu chưa có phương thức thanh toán vận hành. Thứ tự phát hành phụ thuộc hệ thống hiện có, chính sách tài chính, quy trình đối soát và khả năng thử nghiệm với người dùng. Mỗi lát được chọn để thực hiện phải có tiêu chí chất lượng và tính toàn vẹn phù hợp.

## 14. Checklist trước khi tạo hoặc đổi loại ticket

- [ ] Hạng mục thể hiện **mục tiêu lớn**, **hành vi có giá trị**, **bước triển khai**, **sai lệch** hay **câu hỏi cần học**?
- [ ] Nếu là **epic**, đã mô tả outcome và các lát có thể kiểm chứng?
- [ ] Nếu là **user story**, đã nêu người hưởng lợi, giá trị và ví dụ chấp nhận?
- [ ] Nếu là **task**, đã biết nó phục vụ kết quả nào và điều kiện hoàn tất?
- [ ] Nếu là **bug**, có đủ bối cảnh, hành vi thực tế, mong đợi, ảnh hưởng và bằng chứng?
- [ ] Nếu bug xuất hiện trước khi story Done, đã giữ đúng tiêu chuẩn chất lượng của story?
- [ ] Nếu là **spike**, có câu hỏi cụ thể, timebox, đầu ra và quyết định cần hỗ trợ?
- [ ] Các hạng mục có được **ưu tiên theo giá trị/rủi ro** thay vì chỉ theo tên loại?
- [ ] Nhóm biết khi nào có **increment thực sự hoàn tất** và khi nào mới có **kiến thức mới**?
- [ ] Dữ liệu về flow và phản hồi sản phẩm có được dùng để **cải tiến backlog và cách làm**?

**Ghi nhớ:** Epic giúp nhìn **mục tiêu và phạm vi lớn**; user story giúp mô tả **giá trị có thể bàn giao**; task giúp tổ chức **các bước thực hiện**; bug giúp xử lý **hành vi sai**; spike giúp giảm **điều chưa biết**. Phân biệt đúng năm loại giúp nhóm phối hợp hiệu quả hơn, nhưng mục tiêu cuối vẫn là tạo phần mềm có chất lượng, nhận phản hồi sớm và thích ứng liên tục với nhu cầu thực tế.
