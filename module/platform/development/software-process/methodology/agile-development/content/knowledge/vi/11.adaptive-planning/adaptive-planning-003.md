# Kết nối tầm nhìn, lộ trình, kế hoạch phát hành và công việc hằng ngày

Một nhóm phát triển nền tảng học trực tuyến có thể bắt đầu ngày làm việc bằng rất nhiều việc cụ thể: sửa API lưu tiến độ, bổ sung trạng thái lỗi trên giao diện, review pull request, kiểm tra dữ liệu học tập hoặc giải quyết một lỗi đăng nhập. Những công việc đó chỉ thực sự có ý nghĩa nếu nhóm hiểu chúng phục vụ **kết quả sản phẩm nào**.

Hãy tưởng tượng tổ chức nêu tầm nhìn: *“Người mới học lập trình có thể tiến bộ đều đặn nhờ lộ trình phù hợp và phản hồi kịp thời.”* Nhưng trong backlog, nhóm lại ưu tiên xây bộ tùy chỉnh giao diện nhiều màu sắc vì một yêu cầu mới xuất hiện. Các công việc kỹ thuật có thể được hoàn thành đúng hạn mà chưa chắc đưa sản phẩm gần tầm nhìn hơn.

**Kế hoạch thích ứng (adaptive planning)** giải quyết khoảng cách đó: liên kết định hướng dài hạn với các quyết định ngắn hạn, đồng thời cho phép điều chỉnh khi nhận được phản hồi và thông tin mới. Kế hoạch không phải bản dự đoán chắc chắn về tương lai; nó là **giả thuyết có cấu trúc về cách đạt mục tiêu và cách học để sửa giả thuyết ấy**.

Bài học thuộc chương **Kế hoạch thích ứng** của module **AGILE_DEVELOPMENT**. Module hướng tới phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục, sử dụng những thực hành như user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Trong bài này, những thực hành đó được kết nối với tầm nhìn, lộ trình và quyết định phát hành, thay vì tồn tại như các hoạt động tách rời.

Sau bài học, bạn có thể:

- Phân biệt **tầm nhìn, mục tiêu sản phẩm, lộ trình, kế hoạch phát hành, Product Backlog, kế hoạch ngắn hạn và việc hằng ngày**.
- Truy vết một công việc cụ thể tới kết quả người dùng và giải thích khi nào nên loại, trì hoãn hoặc thay đổi công việc đó.
- Tạo lộ trình định hướng bằng **kết quả và giả thuyết**, thay vì khóa cứng danh sách tính năng theo ngày.
- Lập kế hoạch phát hành có phạm vi, điều kiện chất lượng, rủi ro và mức độ tin cậy được trình bày rõ.
- Kết nối Sprint Goal, Sprint Backlog, Daily Scrum hoặc bảng Kanban với mục tiêu chung mà không biến chúng thành công cụ báo cáo máy móc.
- Dùng phản hồi, throughput, cycle time, WIP và dữ liệu chất lượng để cập nhật dự báo và ưu tiên.
- Thực hành một tình huống thay đổi ưu tiên mà vẫn giữ minh bạch với người liên quan.

## 1. Các tầng kế hoạch giải quyết những câu hỏi khác nhau

Một hệ thống lập kế hoạch hiệu quả không nhất thiết cần nhiều tài liệu, nhưng phải trả lời được các câu hỏi từ chiến lược đến thực hiện.

| Tầng | Câu hỏi chính | Đầu ra thường dùng | Mức ổn định tương đối |
| --- | --- | --- | --- |
| **Tầm nhìn sản phẩm (product vision)** | Vì sao sản phẩm tồn tại, ai được phục vụ và tương lai mong muốn là gì? | Tuyên bố định hướng ngắn, bối cảnh thị trường và người dùng. | Dài hạn; thay đổi khi định hướng căn bản thay đổi. |
| **Mục tiêu sản phẩm/kết quả (product goal/outcome)** | Kết quả quan trọng tiếp theo cần đạt là gì; làm sao biết tiến bộ? | Product Goal, mục tiêu có tín hiệu đo và giả thuyết giá trị. | Trung hạn; được kiểm tra bằng bằng chứng. |
| **Lộ trình (roadmap)** | Những vấn đề hoặc năng lực lớn nào nên được giải quyết trước, sau và vì sao? | Các chủ đề, kết quả kỳ vọng, mốc học hỏi, phụ thuộc. | Có hướng đi, nhưng nội dung và thứ tự có thể điều chỉnh. |
| **Kế hoạch phát hành (release plan)** | Phần gì cần sẵn sàng cho nhóm người dùng nào, vào thời điểm hoặc điều kiện nào? | Dự báo phạm vi, cửa sổ phát hành, điều kiện sẵn sàng, cách triển khai. | Càng gần ngày phát hành càng chi tiết; vẫn được xem lại. |
| **Backlog và kế hoạch ngắn hạn** | Những mục nào đáng thực hiện tiếp và mục tiêu của đợt làm việc hiện tại là gì? | Product Backlog, Sprint Goal/Sprint Backlog hoặc công việc được kéo theo chính sách Kanban. | Ngắn hạn; được làm rõ, chia nhỏ và sắp lại theo thực tế. |
| **Công việc hằng ngày** | Hôm nay nhóm cần hoàn tất, phối hợp hoặc tháo gỡ điều gì để tiến tới mục tiêu? | Task, kiểm thử, review, triển khai, xử lý trở ngại, phản hồi người dùng. | Điều chỉnh thường xuyên theo tiến độ và điểm nghẽn. |

Các mốc thời gian ở đây chỉ có tính tương đối, **không phải quy định Agile rằng lộ trình bắt buộc dài một năm hay Sprint phải kéo dài hai tuần**.

### Một nguyên tắc xuyên suốt

> Mỗi tầng nên trả lời câu hỏi của tầng đó; tầng dưới cụ thể hóa tầng trên, còn bằng chứng từ tầng dưới có quyền làm thay đổi giả thuyết ở tầng trên.

Ví dụ, một lỗi lưu tiến độ được phát hiện hôm nay có thể làm thay đổi thứ tự backlog, phạm vi phát hành và thậm chí giả thuyết rằng việc “Học tiếp” đã đủ để cải thiện kết quả học tập.

### Những thứ không nên đánh đồng

- **Tầm nhìn không phải danh sách chức năng.** “Có chat, AI, bảng xếp hạng” chưa cho biết người dùng được giúp đỡ như thế nào.
- **Lộ trình không phải hợp đồng cam kết mọi tính năng đúng ngày.** Nó thể hiện các lựa chọn và giả thuyết theo thời gian; cam kết thật nếu có phải được nêu riêng.
- **Release plan không giống Sprint Backlog.** Phát hành có thể trải qua nhiều Sprint, hoặc một Sprint có thể tạo nhiều Increment.
- **Task đã xong không đồng nghĩa người dùng đã nhận giá trị.** Cần phân biệt hoàn tất kỹ thuật, phát hành và kết quả sản phẩm.
- **Backlog không phải kho chứa mọi ý tưởng phải xây.** Nó là danh sách công việc được sắp thứ tự, có thể loại bỏ hoặc thay đổi.

## 2. Luồng từ định hướng xuống hành động và ngược lại

Hình dưới thể hiện các mối liên hệ chính. Đường đi xuống làm rõ điều cần tạo ra; đường phản hồi giúp tránh xây tiếp khi giả định không còn đúng.

~~~mermaid
flowchart TD
    A["Tầm nhìn: người dùng cần tương lai nào?"]
    B["Mục tiêu sản phẩm và kết quả cần kiểm chứng"]
    C["Lộ trình: chủ đề, cơ hội, thứ tự tương đối"]
    D["Kế hoạch phát hành: đối tượng, phạm vi, điều kiện sẵn sàng"]
    E["Backlog: lựa chọn công việc theo giá trị và rủi ro"]
    F["Sprint Goal / chính sách kéo việc theo Kanban"]
    G["Việc hằng ngày: xây, kiểm thử, review, phối hợp"]
    H["Increment đã hoàn tất; phát hành khi phù hợp"]
    I["Phản hồi người dùng, chất lượng và số đo dòng công việc"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
    I -->|"Điều chỉnh chiến lược khi có bằng chứng"| B
    I -->|"Xem lại lựa chọn và dự báo"| C
    I -->|"Đổi phạm vi hoặc thời điểm phát hành"| D
    I -->|"Sắp lại thứ tự và làm rõ yêu cầu"| E
~~~

Sơ đồ là mô hình tư duy, **không phải quy trình cứng buộc mọi yêu cầu phải đi qua chín cổng phê duyệt**. Trong thực tế:

- Một sự cố bảo mật cần xử lý ngay có thể được đưa vào luồng khẩn cấp mà không chờ cập nhật toàn bộ lộ trình.
- Một nhóm đã hiểu rõ nhu cầu có thể xây và hoàn tất một lát nhỏ ngay, đồng thời đo tác động.
- Một thử nghiệm nguyên mẫu có thể cung cấp thông tin để thay đổi lộ trình trước khi có tính năng sản phẩm hoàn chỉnh.
- Backlog và lộ trình thường được trao đổi song song; người làm sản phẩm không cần cập nhật tất cả tài liệu sau mỗi chỉnh sửa nhỏ.

Điều cần giữ là **đường giải thích hai chiều**: tại sao việc này đáng làm, và điều học được từ việc đó sẽ ảnh hưởng kế hoạch ra sao.

## 3. Bắt đầu từ tầm nhìn và mục tiêu sản phẩm

### 3.1. Tầm nhìn hướng tới người dùng và giá trị

Một tầm nhìn hữu ích thường trả lời:

1. **Ai** là nhóm người dùng hoặc bên hưởng lợi chính?
2. **Vấn đề** nào đáng giải quyết và vì sao?
3. **Trải nghiệm hoặc kết quả** mong muốn là gì?
4. **Giới hạn, định vị hoặc khác biệt** nào giúp nhóm tránh làm mọi thứ?

Ví dụ chưa rõ:

> “Xây nền tảng học tập hiện đại với AI, gamification và báo cáo.”

Câu này liệt kê lựa chọn công nghệ và tính năng, chưa cho biết người học được giải quyết trở ngại nào.

Một cách diễn đạt tốt hơn:

> “Giúp người mới tự học Java học đều đặn, hiểu được tiến độ và nhận phản hồi đủ sớm để vượt qua những đoạn khó mà không mất phương hướng.”

Câu này không khóa sản phẩm vào một công cụ nhất định. Nhóm vẫn có thể cân nhắc AI hoặc trò chơi hóa, **nếu có bằng chứng chúng giúp người học đạt kết quả**.

### 3.2. Mục tiêu sản phẩm chuyển định hướng thành đích gần hơn

Trong Scrum, **Product Goal** mô tả trạng thái tương lai của sản phẩm mà Scrum Team hướng tới và là cam kết của Product Backlog. Nó tạo đích dài hạn cho các lựa chọn công việc. Nhóm có thể gắn Product Goal với **chỉ số kết quả** để đánh giá tiến bộ, nhưng chỉ số không tự thay thế việc mô tả mục tiêu.

Ví dụ:

> **Product Goal minh họa:** Người mới học Java có thể đi qua một lộ trình nhập môn và tự tiếp tục học trong những tuần đầu, với trải nghiệm theo dõi tiến độ đáng tin cậy.

Các tín hiệu quan sát có thể gồm:

- Tỷ lệ người đăng ký bắt đầu bài học đầu tiên.
- Tỷ lệ quay lại học sau một tuần.
- Tỷ lệ hoàn tất bài thứ hai hoặc một mốc học tập có ý nghĩa.
- Phản hồi về khả năng tìm bài kế tiếp hoặc khôi phục vị trí học.

Nếu đặt mục tiêu số cụ thể, cần có dữ liệu nền và tiêu chí đo thống nhất. Ví dụ, giả sử dữ liệu ban đầu có **28 trong 100** học viên của một nhóm hoàn tất bài thứ hai trong tuần đầu; nhóm có thể đặt **mục tiêu thử** cải thiện lên 40 trong 100 ở giai đoạn tiếp theo. Những con số này chỉ là **ví dụ minh họa**, không phải ngưỡng chuẩn Agile hay dự báo chắc chắn.

### 3.3. Phân biệt output và outcome

| Loại | Ví dụ | Điều nó cho biết |
| --- | --- | --- |
| **Output (đầu ra)** | Có nút “Học tiếp”; ba video; API lưu tiến độ. | Nhóm đã xây hoặc cung cấp những gì. |
| **Outcome (kết quả)** | Người học quay lại dễ hơn, mất ít thời gian tìm bài và hoàn tất các bước học quan trọng hơn. | Hành vi hoặc tình trạng người dùng có thay đổi theo hướng mong muốn không. |
| **Impact (tác động rộng)** | Nhiều người học duy trì kiến thức và đạt mục tiêu đào tạo hơn. | Giá trị dài hạn hơn, có thể chịu nhiều yếu tố ngoài phần mềm. |

Đừng coi mỗi thay đổi về chỉ số là kết quả do một tính năng duy nhất tạo ra. Số người quay lại học còn bị ảnh hưởng bởi nội dung, lịch học, nguồn người dùng và các điều kiện khác. Khi có thể, kết hợp dữ liệu định lượng, phản hồi định tính và phép thử phù hợp để hiểu nguyên nhân.

## 4. Lộ trình: định hướng lựa chọn, không khóa tương lai

**Product roadmap** là cách truyền đạt dự kiến sản phẩm nên tiến theo hướng nào và vì sao. Nó thường hữu ích nhất khi trình bày **vấn đề, kết quả hoặc năng lực cần đạt**, kèm giả thuyết, ràng buộc và mức độ chắc chắn.

### 4.1. Lộ trình thiên về kết quả

Với tầm nhìn hỗ trợ người mới học Java, lộ trình minh họa có thể là:

| Khoảng định hướng | Chủ đề/vấn đề | Kết quả kỳ vọng | Cách học và điều kiện chuyển bước |
| --- | --- | --- | --- |
| **Now – Đang tập trung** | Giúp người học quay lại đúng bài đang dở. | Ít mất công tìm bài, tiến độ được lưu đáng tin. | Thử luồng “Học tiếp” cho nhóm người học mục tiêu; kiểm tra hành vi quay lại. |
| **Next – Có khả năng làm tiếp** | Giúp người học biết mình đã hiểu tới đâu. | Phản hồi sớm sau mỗi phần kiến thức. | Quan sát người học có dùng kết quả bài tập để chọn bước tiếp theo không. |
| **Later – Giả thuyết cần nghiên cứu** | Cá nhân hóa gợi ý học tập. | Đề xuất phù hợp với trở ngại từng người. | Chỉ đầu tư sâu khi có bằng chứng dữ liệu và nhu cầu đủ rõ. |

**Now / Next / Later** là một cách biểu đạt lộ trình, không phải yêu cầu của Scrum. Nhóm cũng có thể chọn lộ trình theo quý, theo giai đoạn hoặc theo những mốc phụ thuộc — miễn là truyền đạt rõ mức độ tin cậy.

### 4.2. Những điều nên ghi trên roadmap

- **Kết quả mong đợi:** người dùng hoặc doanh nghiệp sẽ được lợi gì?
- **Giả thuyết chính:** điều gì chưa biết và cần xác minh?
- **Mốc học hỏi:** demo, thử nghiệm hay dữ liệu nào giúp nhóm quyết định?
- **Phụ thuộc lớn:** tích hợp, dữ liệu, quy định, đối tác hoặc đội khác.
- **Giới hạn nguồn lực:** năng lực đội ngũ và những cam kết không thể bỏ.
- **Mức độ tự tin:** đang nghiên cứu, dự kiến, đã cam kết theo phạm vi cụ thể.

Một lộ trình có thể có mốc ngày khi cần phối hợp thực tế. Điều quan trọng là **không gắn ngày giả chính xác cho các mục chưa rõ giải pháp**. Nếu có deadline bắt buộc, cần làm minh bạch phần nào cố định, phần nào có thể điều chỉnh.

### 4.3. Lộ trình nên chứa lựa chọn, không chỉ chứa tính năng

Nếu chủ đề “phản hồi sớm sau bài tập” có thể được giải bằng nhận xét tự động đơn giản, hướng dẫn của giảng viên hoặc gợi ý từ AI, nhóm chưa cần cam kết một phương án từ đầu. Bằng chứng từ thử nghiệm giúp quyết định **cách đạt kết quả**, tránh biến lộ trình thành danh sách ý tưởng kỹ thuật không thể bỏ.

## 5. Kế hoạch phát hành: chuyển ý định thành dự báo có điều kiện

**Kế hoạch phát hành (release plan)** trả lời câu hỏi người dùng **nào** sẽ nhận được **phần nào** của sản phẩm, theo **mốc hoặc điều kiện** nào, và cần chuẩn bị gì để phát hành đáng tin cậy.

Trong Agile, kế hoạch phát hành thường là **dự báo được cập nhật**, không phải một tài liệu đã ký rồi bất biến. Nó có thể phục vụ truyền thông nội bộ, phối hợp marketing/hỗ trợ, ràng buộc hợp đồng hoặc chuẩn bị vận hành.

### 5.1. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Ý nghĩa | Không được suy ra tự động |
| --- | --- | --- |
| **Increment** | Bước tiến sản phẩm được tích hợp, có thể sử dụng và đạt Definition of Done trong Scrum. | Đã mở cho toàn bộ người dùng. |
| **Build/deployment** | Bản phần mềm được đóng gói hoặc đưa lên môi trường chạy. | Người dùng đã thấy/tương tác với tính năng. |
| **Release** | Chủ động cho một đối tượng người dùng tiếp cận khả năng sản phẩm. | Tính năng chắc chắn đã tạo giá trị hoặc đã đạt mục tiêu kinh doanh. |
| **Release plan** | Dự kiến phạm vi, đối tượng, điều kiện và cách tổ chức phát hành. | Mọi chi tiết và ngày đều được bảo đảm bất chấp thông tin mới. |

Một hệ thống có thể được **deploy** trước nhưng vẫn tắt tính năng bằng feature flag; sau đó chỉ **release** cho nhóm thử nghiệm. Dù dùng cách nào, phần mềm đưa ra sử dụng phải đáp ứng các điều kiện chất lượng, quyền truy cập và vận hành cần thiết.

Trong Scrum, **Sprint Review không phải cổng phê duyệt bắt buộc trước mỗi lần phát hành**. Nhóm có thể tạo nhiều Increment trong một Sprint và phát hành khi phù hợp.

### 5.2. Ba dạng kế hoạch theo ràng buộc

| Tình huống | Phần tương đối cố định | Phần nên thích ứng |
| --- | --- | --- |
| Có sự kiện ra mắt đúng ngày. | Ngày, điều kiện an toàn, trải nghiệm cốt lõi phải hoạt động. | Phạm vi tính năng phụ, mức độ tùy biến và cách triển khai từng bước. |
| Cần đạt kết quả người dùng trước khi mở rộng. | Kết quả kỳ vọng và tiêu chí kiểm chứng. | Ngày mở rộng, giải pháp cụ thể, số lát cần xây. |
| Có quy định hoặc tích hợp bắt buộc. | Yêu cầu tuân thủ và các mốc bên ngoài đã xác nhận. | Cách tổ chức công việc, thứ tự triển khai và phần không bắt buộc. |

Nguyên tắc quan trọng là **không cố định đồng thời phạm vi đầy đủ, ngày chính xác và nguồn lực không đổi khi vẫn còn nhiều bất định**, rồi giải quyết căng thẳng bằng cách cắt kiểm thử hoặc giấu rủi ro. Hãy trình bày đánh đổi minh bạch và thương lượng phần có thể thay đổi.

### 5.3. Điều kiện sẵn sàng phát hành

Một release plan hữu ích không chỉ liệt kê story mà còn xem xét:

- **Giá trị và phạm vi:** người dùng nào cần làm được tác vụ gì ngay sau phát hành?
- **Chất lượng:** Increment liên quan đã đạt DoD và tiêu chí chấp nhận chưa?
- **An toàn:** dữ liệu cá nhân, phân quyền, giao dịch, tuân thủ và bảo mật đã được kiểm tra phù hợp chưa?
- **Vận hành:** có theo dõi lỗi, người hỗ trợ, quy trình xử lý sự cố và phương án khôi phục cần thiết không?
- **Truyền thông:** người dùng, bộ phận hỗ trợ và các bên liên quan có được thông báo phù hợp?
- **Phản hồi:** sau phát hành, đo tín hiệu nào và ai quyết định có mở rộng không?

Việc triển khai theo giai đoạn hoặc dùng feature flag có thể giảm phạm vi ảnh hưởng, nhưng **không thay thế** các điều kiện an toàn cần thiết.

## 6. Từ lộ trình và release plan tới Product Backlog

**Backlog** là nơi nhóm biến mục tiêu thành **những lựa chọn công việc được sắp thứ tự**. Nó cần giữ liên hệ với kết quả sản phẩm, nhưng không nên bắt buộc mỗi task kỹ thuật phải có một sơ đồ truy vết phức tạp.

### 6.1. Một chuỗi liên kết minh họa

~~~mermaid
flowchart TD
    V["Tầm nhìn: người học Java tiến bộ đều đặn"]
    PG["Product Goal: hỗ trợ học viên tiếp tục và hoàn tất lộ trình nhập môn"]
    R["Chủ đề roadmap: quay lại bài đang học dở dễ dàng"]
    RL["Mục tiêu phát hành thử: người học được tiếp tục video đáng tin cậy"]
    P1["PBI A: lưu và khôi phục vị trí trên một thiết bị"]
    P2["PBI B: lối vào Học tiếp rõ ràng"]
    P3["PBI C: theo dõi tín hiệu sử dụng hợp lệ"]
    SG["Sprint Goal: cho phép tiếp tục bài học sau khi quay lại"]
    T["Task: kết nối UI, xử lý dữ liệu, kiểm thử và review"]
    V --> PG --> R --> RL
    RL --> P1
    RL --> P2
    RL --> P3
    P1 --> SG
    P2 --> SG
    SG --> T
~~~

**PBI** là *Product Backlog Item*, một mục trong Product Backlog. “Epic”, “initiative” và “user story” là những cách mô tả hoặc nhóm công việc phổ biến, nhưng không phải các loại hiện vật bắt buộc được Scrum định nghĩa.

### 6.2. Backlog nên phản ánh giá trị và giả thuyết

Ví dụ một nhóm backlog:

| Mục | Người hưởng lợi/kết quả | Vì sao đang được ưu tiên | Cách kiểm chứng |
| --- | --- | --- | --- |
| **PBI-01: Khôi phục vị trí xem** | Người học không phải dò lại đoạn video. | Gắn trực tiếp với trở ngại quan sát được. | Kiểm thử hành vi và thử với người học. |
| **PBI-02: Lối vào “Học tiếp”** | Người học dễ tìm bài đang dở. | Chỉ khôi phục dữ liệu chưa đủ nếu khó tìm đường vào. | Thử thao tác tìm bài và đo lượt tiếp tục học. |
| **PBI-03: Theo dõi lỗi lưu tiến độ** | Nhóm phát hiện thất bại trước khi ảnh hưởng nhiều người. | Điều kiện vận hành và học từ thử nghiệm. | Log/metric phù hợp, không lộ dữ liệu riêng tư. |
| **PBI-04: Đồng bộ đa thiết bị** | Người dùng đổi máy vẫn tiếp tục học. | Giá trị tiềm năng, cần xác minh tỷ lệ người thực sự đổi máy. | Nghiên cứu nhu cầu; quyết định trước khi triển khai lớn. |
| **PBI-05: Bảng xếp hạng** | Có thể thúc đẩy tương tác, nhưng giả thuyết còn yếu. | Chưa phục vụ vấn đề quay lại video rõ ràng. | Tạm hoãn, nghiên cứu riêng khi có cơ sở. |

Không phải cứ nằm trong backlog là phải hoàn thành. Product Owner có thể sắp lại thứ tự, làm rõ, thêm hoặc loại các mục theo mục tiêu và phản hồi. Developers và các chuyên môn liên quan cần góp thông tin về tính khả thi, rủi ro, phụ thuộc và cách chia phần gia tăng.

### 6.3. User story là công cụ giao tiếp, không phải danh sách task

Một user story minh họa:

> **Là** người học đã xem dở video, **tôi muốn** mở lại tại vị trí gần nhất đã lưu, **để** tiếp tục mà không phải dò lại nội dung.

Tiêu chí chấp nhận có thể gồm:

~~~gherkin
Feature: Tiếp tục học video

Scenario: Khôi phục vị trí đã lưu
  Given người học đã đăng nhập và có quyền truy cập "Bài A"
  And vị trí 06:20 đã được lưu thành công cho người học
  When người học mở lại "Bài A"
  Then video có thể tiếp tục tại vị trí đã lưu trong sai số đã thỏa thuận

Scenario: Chưa có tiến độ
  Given người học có quyền truy cập "Bài A"
  And chưa có tiến độ được lưu cho bài này
  When người học mở "Bài A"
  Then video bắt đầu từ đầu
  And không hiển thị xác nhận sai rằng đã khôi phục tiến độ

Scenario: Không có quyền truy cập
  Given một người không có quyền xem dữ liệu tiến độ của học viên khác
  When người đó yêu cầu dữ liệu tiến độ của học viên khác
  Then hệ thống từ chối truy cập theo chính sách
  And không tiết lộ tiến độ riêng tư
~~~

Story mô tả **hành vi người dùng**. Công việc thiết kế dữ liệu, API, giao diện, kiểm thử, bảo mật và triển khai là những **task để hoàn thành story**, không tự động là các user story riêng chỉ vì chúng thuộc những lớp kỹ thuật khác nhau.

Một lát dọc đủ nhỏ nên có kết quả đầu cuối có thể kiểm chứng. Khi story hoàn tất theo DoD, nhóm có thể tạo một Increment có thể sử dụng, thay vì nhiều thành phần “đã code xong” nhưng chưa chạy cùng nhau.

## 7. Kết nối với Scrum: từ Product Goal tới Daily Scrum

Scrum có một số khái niệm đặc biệt hữu ích để tạo liên kết giữa chiến lược và thực thi. **Roadmap và release plan không phải các hiện vật Scrum bắt buộc**, nhưng có thể hỗ trợ Product Goal và Product Backlog.

### 7.1. Các cấp trách nhiệm và cam kết

| Thành phần Scrum | Vai trò trong chuỗi kế hoạch |
| --- | --- |
| **Product Goal** | Đích dài hạn mà Scrum Team hướng tới; là cam kết của Product Backlog. |
| **Product Backlog** | Danh sách có thứ tự của công việc cần thiết để cải thiện sản phẩm, phản ánh học hỏi và ưu tiên hiện tại. |
| **Sprint Goal** | Một mục tiêu thống nhất cho Sprint; tạo lý do và hướng đi cho các Product Backlog Items được chọn. |
| **Sprint Backlog** | Sprint Goal, các Product Backlog Items được chọn và kế hoạch để Developers đưa chúng tới Increment. |
| **Definition of Done** | Mô tả chất lượng và trạng thái hoàn tất của Increment; bảo đảm phần tạo ra có thể sử dụng. |
| **Increment** | Bước tiến được tích hợp với các Increment trước và đáp ứng DoD; có thể tạo nhiều Increment trong Sprint. |

### 7.2. Vai trò của các sự kiện Scrum

**Sprint Planning:** Scrum Team thảo luận vì sao Sprint có giá trị, hình thành Sprint Goal và lập kế hoạch. Một Sprint Goal tốt mô tả kết quả chung, không đơn thuần là “hoàn tất 12 ticket”.

Ví dụ:

> “Người học có thể rời một video và tiếp tục từ vị trí đã lưu khi quay lại, trong phạm vi thử nghiệm được xác định.”

**Daily Scrum:** Developers kiểm tra tiến độ hướng tới Sprint Goal, điều chỉnh Sprint Backlog cho ngày làm việc tiếp theo. Đây là cuộc trao đổi để **phối hợp hướng mục tiêu**, không phải buổi mỗi người lần lượt báo cáo năng suất cho cấp quản lý.

Ví dụ câu hỏi có ích:

- Luồng lưu/đọc tiến độ đã chạy từ đầu đến cuối chưa?
- Có điểm nghẽn tích hợp nào khiến Sprint Goal gặp rủi ro?
- Hôm nay ai cần phối hợp kiểm thử phân quyền và trạng thái lỗi?
- Việc nào nên hoàn tất trước khi nhóm nhận thêm đầu việc mới?

**Sprint Review:** Scrum Team cùng các bên liên quan kiểm tra kết quả và thảo luận bước tiếp theo, có thể điều chỉnh Product Backlog dựa trên phản hồi.

**Sprint Retrospective:** Scrum Team xem cách phối hợp, chất lượng và hiệu quả, rồi chọn thay đổi nhằm cải tiến khả năng giao các phần gia tăng.

### 7.3. Điều chỉnh kế hoạch trong Sprint

Sprint Goal là định hướng có tính cam kết, còn **chi tiết kế hoạch và phạm vi công việc có thể được Developers điều chỉnh khi học thêm thông tin**, trao đổi với Product Owner về tác động khi cần. Không được ngụy tạo rằng mọi mục có thể cắt bỏ vô điều kiện: các yêu cầu chất lượng và Definition of Done vẫn phải được đáp ứng.

Nếu xuất hiện bằng chứng Sprint Goal đã lỗi thời, Scrum có cơ chế hủy Sprint do Product Owner quyết định. Đây là ngoại lệ khi cần thiết, không phải hành động mặc định mỗi lần có yêu cầu mới.

## 8. Kết nối với Kanban: từ mục tiêu tới luồng công việc

Không phải mọi nhóm đều tổ chức theo Sprint. Trong **Kanban**, nhóm có thể giữ cùng một tầm nhìn, mục tiêu, roadmap, release plan và backlog, nhưng lựa chọn công việc theo chính sách luồng và năng lực sẵn có.

Một bảng minh họa:

~~~text
Ready (đã rõ ưu tiên) -> In progress -> Review -> Verify -> Done
                           WIP <= 3     WIP <= 2
~~~

Giới hạn WIP trong ví dụ chỉ là con số minh họa. Nhóm cần quyết định giới hạn phù hợp bằng dữ liệu và khả năng phối hợp thực tế.

### 8.1. Giữ mục tiêu ngay trên bảng công việc

Bảng nên làm rõ **công việc nào phục vụ chủ đề hiện tại**, mục nào là lỗi vận hành, mục nào đang chờ quyết định và tại sao cần xử lý. Không cần đặt tên cột theo tầng chiến lược; có thể dùng liên kết hoặc nhãn gọn để truy vết tới kết quả liên quan.

Ví dụ, nếu release thử nghiệm đang chờ chức năng lưu tiến độ ổn định, nhóm có thể tập trung hoàn tất các mục đang Review/Verify trước khi kéo thêm một story tùy chỉnh giao diện chưa cấp thiết.

### 8.2. Dùng số đo luồng để kiểm tra khả năng giao hàng

- **Lead time:** khoảng thời gian từ khi yêu cầu được ghi nhận đến hoàn tất, theo điểm bắt đầu/kết thúc nhóm quy ước.
- **Cycle time:** thời gian từ khi công việc bắt đầu thực hiện tới khi hoàn tất.
- **Throughput:** số mục hoàn tất trong một đơn vị thời gian.
- **WIP:** số mục đã bắt đầu nhưng chưa hoàn tất.
- **Work item age:** tuổi của một mục đang mở, hữu ích để phát hiện việc có nguy cơ kéo dài.

Số đo không tự quyết định roadmap. Chúng cho biết **mức độ ổn định của luồng thực thi** để đưa ra dự báo và xử lý nút thắt có trách nhiệm.

### 8.3. Có thể kết hợp Scrum và Kanban

Một Scrum Team có thể dùng các kỹ thuật quản lý luồng của Kanban để tăng khả năng dự báo trong Sprint. Ngược lại, nhóm sử dụng Kanban có thể thiết lập các mốc đánh giá mục tiêu và phát hành phù hợp mà không cần áp dụng mọi sự kiện Scrum.

Điểm chung là **tạo minh bạch, quan sát thực tế và thay đổi kế hoạch theo bằng chứng**, chứ không phải chọn một nhãn phương pháp rồi áp dụng nghi thức máy móc.

## 9. Công việc hằng ngày cần kết nối với mục tiêu như thế nào?

Tầng kế hoạch hữu ích nhất là tầng giúp nhóm **chọn hành động tiếp theo đúng hơn**.

### 9.1. Mỗi việc nên trả lời được “vì sao bây giờ?”

Một task ví dụ:

> “Bổ sung kiểm tra quyền truy cập trong API đọc tiến độ.”

Nếu được hỏi tại sao cần làm hôm nay, người thực hiện có thể giải thích:

> “PBI-01 yêu cầu người học khôi phục tiến độ an toàn. Nếu API để lộ tiến độ của tài khoản khác, story chưa đạt tiêu chí chấp nhận và Increment chưa đạt DoD, nên không thể mở thử cho người học.”

Liên kết từ **task → PBI → Sprint Goal hoặc release goal → Product Goal** làm rõ ý nghĩa của công việc kỹ thuật không nhìn thấy trực tiếp trên giao diện.

### 9.2. Khi có hai việc, chọn theo tác động tới mục tiêu và dòng chảy

Giả sử nhóm có thể:

- Bắt đầu thiết kế thêm hình đại diện cho trang cá nhân.
- Hoặc hỗ trợ kiểm thử trường hợp lưu tiến độ lỗi, đang chặn việc phát hành thử.

Nếu mục tiêu hiện tại là cho người học sử dụng “Học tiếp” đáng tin cậy, việc kiểm thử và hoàn tất story đang dở thường cần được ưu tiên. Tuy nhiên, một sự cố khẩn cấp mới xuất hiện có thể đảo thứ tự đó; nhóm phải cập nhật người liên quan về lý do thay đổi.

### 9.3. Không biến truy vết thành thủ tục nặng nề

Nhóm không nhất thiết cần điền 20 trường metadata cho mỗi task. Có thể bắt đầu bằng:

- Một mục tiêu đang được hiển thị rõ cho nhóm.
- Liên kết PBI với mục tiêu/kết quả mà nó hỗ trợ.
- Acceptance criteria và DoD đủ để xác định Done.
- Các quyết định và phụ thuộc quan trọng được ghi ngắn gọn.
- Chính sách rõ khi công việc bị chặn hoặc xuất hiện việc khẩn.

Mục tiêu là để **mọi người biết vì sao chọn việc và khi nào nên đổi**, không phải tạo nhiều giấy tờ hơn số lượng quyết định hữu ích.

## 10. Ví dụ xuyên suốt: sáu tuần cải thiện hành trình học Java

Giả sử một nhóm có **sáu tuần để thử nghiệm** hướng cải thiện việc người học quay lại học. Mốc thời gian, quy mô và dữ liệu sau đây đều là **giả định phục vụ học tập**, không phải lịch trình hoặc kết quả đã được xác nhận của một sản phẩm thật.

### 10.1. Tầng tầm nhìn và Product Goal

**Tầm nhìn:** Người mới học Java có thể theo đuổi lộ trình, biết bước tiếp theo và tiến bộ một cách đều đặn.

**Product Goal minh họa:** Nhóm người học nhập môn có thể tiếp tục các bài đang dở và hoàn thành những cột mốc đầu tiên của lộ trình với trải nghiệm đáng tin cậy.

**Giả thuyết cần kiểm tra:** Khó tìm lại bài và vị trí đã xem là một nguyên nhân đáng kể khiến người học không quay lại.

**Dấu hiệu thành công:** người học tiếp tục bài nhanh, khôi phục tiến độ đúng, tỷ lệ quay lại hoặc hoàn tất bài tăng theo phương pháp đo đã thống nhất.

### 10.2. Tầng roadmap

| Khoảng hướng đi | Trọng tâm | Lý do | Còn chưa biết |
| --- | --- | --- | --- |
| **Now** | Lưu và khôi phục vị trí học; đường “Học tiếp” rõ. | Có giả thuyết về trở ngại quay lại bài. | Người học có thật sự dùng tính năng thường xuyên không? |
| **Next** | Phản hồi sau bài tập, nhắc bước kế tiếp. | Có thể giúp người học tiếp tục khi hoàn thành một đoạn. | Loại phản hồi nào hỗ trợ tốt mà không gây phiền? |
| **Later** | Gợi ý lộ trình cá nhân. | Tiềm năng nhưng đòi hỏi hiểu dữ liệu và nhu cầu. | Có đủ bằng chứng để đầu tư thiết kế phức tạp không? |

Roadmap không cam kết “Later phải xong ở tuần sáu”. Nó chỉ mô tả điều nhóm có thể ưu tiên **sau khi học từ Now**.

### 10.3. Tầng release plan

| Phương án phát hành | Phạm vi dự kiến | Đối tượng | Điều kiện trước khi mở |
| --- | --- | --- | --- |
| **R1 – Thử nghiệm có kiểm soát** | Tiếp tục video ở vị trí đã lưu, trạng thái lỗi rõ, quyền truy cập đúng; theo dõi tín hiệu cần thiết. | Một nhóm người học phù hợp, có thông tin về giới hạn bản thử. | PBI liên quan đạt DoD; luồng học hoạt động; dữ liệu được bảo vệ; có hỗ trợ và phương án khôi phục phù hợp. |
| **R2 – Mở rộng có điều kiện** | Cải thiện lối vào “Học tiếp”, xử lý trở ngại phát hiện ở R1; có thể bổ sung bài tập phản hồi sớm. | Nhóm lớn hơn khi kết quả và vận hành cho phép. | Bằng chứng R1 đủ tin cậy, lỗi nghiêm trọng được giải quyết, năng lực hỗ trợ phù hợp. |

Cửa sổ cho R1 có thể dự kiến vào một giai đoạn đầu của sáu tuần, nhưng **không nên công bố ngày chính xác nếu chưa đánh giá năng lực và phụ thuộc**. Nếu hệ thống chưa an toàn hoặc chưa đạt DoD, đội ngũ cần điều chỉnh phạm vi hoặc lịch, không bỏ qua chất lượng.

### 10.4. Tầng backlog và lập kế hoạch ngắn hạn

Nhóm tách theo những lát đầu cuối:

| Mã | Product Backlog Item | Bằng chứng hoàn tất | Quan hệ với R1 |
| --- | --- | --- | --- |
| **PBI-01** | Người học mở lại video tại vị trí đã lưu. | Demo, kiểm thử đúng vị trí và các trường hợp quan trọng. | Cốt lõi. |
| **PBI-02** | Người học tìm được bài đang xem dở từ nơi dễ thấy. | Kiểm chứng điều hướng, quyền truy cập, trạng thái rỗng. | Cần trong trải nghiệm thử. |
| **PBI-03** | Nhóm biết khi lưu tiến độ thất bại và có hướng xử lý. | Kiểm tra quan sát lỗi và phương án hỗ trợ. | Điều kiện vận hành. |
| **PBI-04** | Người học tiếp tục trên thiết bị khác. | Luồng đa thiết bị và xử lý xung đột được kiểm tra. | Chưa bắt buộc; để nghiên cứu tiếp. |
| **PBI-05** | Người học nhận gợi ý bài kế tiếp bằng mô hình học máy. | Chưa có giả thuyết đủ rõ. | Không nằm trong R1. |

Một **Sprint Goal** cho nhóm dùng Scrum có thể là:

> “Hoàn tất khả năng quay lại một video đang học trên cùng tài khoản, từ giao diện đến dữ liệu, đạt các yêu cầu chất lượng để thử nghiệm có kiểm soát.”

Không nhất thiết chọn cả PBI-01, 02 và 03 nếu năng lực Sprint không đủ; Developers sẽ xem xét phạm vi khả thi, phụ thuộc và điều kiện DoD. Release plan có thể trải qua nhiều Sprint.

Nhóm Kanban có thể sử dụng cùng các PBI và mục tiêu R1, rồi kéo từng lát theo mức ưu tiên và chính sách WIP.

### 10.5. Tầng công việc hằng ngày

Hôm nay, nhóm quan sát PBI-01 đã có giao diện và API, nhưng vẫn thiếu kiểm thử lỗi lưu tiến độ và kiểm tra phân quyền. Một quyết định tốt có thể là **hoàn tất PBI-01 trước** khi mở đồng thời nhiều story khác.

Một cuộc trao đổi ngắn:

> “Mục tiêu là R1 có thể tiếp tục bài an toàn. Hiện PBI-01 còn chặn ở kiểm thử trạng thái lỗi. Hôm nay chúng ta cùng hoàn tất các trường hợp đó và đưa vào bản tích hợp; sau đó mới xem có năng lực nhận PBI-02 hay không.”

Như vậy, thông tin từ tầm nhìn không chỉ xuất hiện trên slide chiến lược; nó **ảnh hưởng việc được chọn và hoàn tất ngay trong ngày**.

### 10.6. Phản hồi có thể đổi roadmap

Giả sử khi R1 được mở cho nhóm thử, đa số người thử có thể khôi phục tiến độ nhưng ít người quay lại học. Phỏng vấn gợi ý nhiều người bỏ dở vì bài học quá dài, không phải vì khó tìm vị trí.

Quyết định thích ứng hợp lý có thể là:

1. Không mở rộng ngay tính năng đồng bộ đa thiết bị.
2. Nghiên cứu khả năng chia nội dung thành phần ngắn và phản hồi sau bài.
3. Điều chỉnh roadmap: đưa chủ đề trải nghiệm nội dung lên cao hơn.
4. Cập nhật Product Backlog và dự báo R2.
5. Giải thích với người liên quan rằng mục tiêu **người học tiếp tục học** không đổi, nhưng giả thuyết giải pháp đã thay đổi do phản hồi.

Một kế hoạch tốt không “thất bại” chỉ vì roadmap thay đổi. **Thất bại lớn hơn là tiếp tục xây theo giả định cũ dù đã có bằng chứng ngược lại.**

## 11. Dự báo phát hành bằng dữ liệu, không bằng chắc chắn giả tạo

Kế hoạch phát hành cần đủ thông tin để phối hợp, nhưng tương lai còn bất định. Thay vì “cam kết chính xác 12 story trong 2 tuần”, nhóm có thể đưa **dự báo có điều kiện** từ dữ liệu lịch sử và mức độ phức tạp hiện tại.

### 11.1. Ví dụ throughput đơn giản

Giả sử trong bốn tuần gần đây nhóm hoàn tất các mục có phạm vi tương đối đồng nhất:

| Tuần | Số mục hoàn tất |
| --- | ---: |
| 1 | 3 |
| 2 | 5 |
| 3 | 4 |
| 4 | 6 |
| **Tổng** | **18** |

Throughput trung bình minh họa:

\[
\frac{3+5+4+6}{4}=4{,}5\ \text{mục/tuần}
\]

Nếu backlog cho một phạm vi phát hành có **12 mục có mức độ tương tự**, phép tính đơn giản \(12/4{,}5 \approx 2{,}7\) tuần chỉ là **ước lượng sơ bộ** trong điều kiện không đổi. Nhìn vào các tuần mẫu từ 3 đến 6 mục/tuần cho khoảng tính tham khảo **khoảng 2–4 tuần** để hoàn tất 12 mục, **không phải khoảng tin cậy thống kê hay lời hứa về ngày phát hành**.

Lý do phải thận trọng:

- Chỉ có bốn tuần dữ liệu; mẫu nhỏ và có thể không đại diện.
- Các mục có thể khác nhau nhiều về kích thước, phụ thuộc và mức rủi ro.
- Một số công việc phát hành như kiểm tra vận hành, hỗ trợ, tuân thủ có thể chưa nằm trong tập mục.
- Nghỉ phép, sự cố và thay đổi ưu tiên có thể ảnh hưởng năng lực.
- Nếu nhóm đổi cách chia story, throughput theo “số mục” không còn dễ so sánh.

Với dữ liệu đủ tốt và nhu cầu dự báo quan trọng, nhóm có thể sử dụng **mô phỏng Monte Carlo từ phân bố throughput/cycle time lịch sử** để ước lượng xác suất hoàn tất theo các mốc khác nhau. Điều đó vẫn phụ thuộc giả định và chất lượng dữ liệu; không nên đưa phần trăm tự tin do cảm giác.

### 11.2. Độ tin cậy giảm khi nhìn xa hơn

Một quy tắc lập kế hoạch thực dụng:

- **Gần hạn:** câu chuyện đã rõ hơn, phụ thuộc và tiêu chí chấp nhận cụ thể hơn.
- **Trung hạn:** chủ đề và các nhóm kết quả rõ, phạm vi còn thay đổi.
- **Xa hạn:** ưu tiên mô tả cơ hội, giả thuyết, giới hạn và điều kiện cần nghiên cứu.

Đây là **lập kế hoạch cuốn chiếu (rolling-wave planning)**: không đầu tư chi tiết như nhau cho mọi thời điểm. Những yêu cầu có rủi ro hoặc phụ thuộc dài hạn vẫn cần được nghiên cứu sớm.

### 11.3. Không dùng velocity làm lời hứa liên nhóm

Trong Scrum, một số nhóm dùng **velocity/story points** để hỗ trợ dự báo nội bộ. Story points là ước lượng tương đối do nhóm xác định; không phải đơn vị đo giá trị người dùng hay năng suất cá nhân. Không nên so velocity giữa hai nhóm như thể đó là một đơn vị chuẩn, hoặc gây áp lực tăng điểm để chứng minh hiệu quả.

Dự báo tốt nên nói rõ **giả định, phạm vi, điều kiện chất lượng, dữ liệu đã dùng và thời điểm cập nhật**.

## 12. Khi kế hoạch thay đổi: quản lý đánh đổi có trách nhiệm

Kế hoạch thích ứng cần một cơ chế rõ để xử lý thông tin mới. Nếu không, “Agile cho phép thay đổi” có thể bị hiểu thành “ai cũng thêm việc vào bất cứ lúc nào”.

### 12.1. Năm câu hỏi khi có yêu cầu mới

1. **Điều gì vừa thay đổi?** Dữ liệu khách hàng, sự cố, quy định, cơ hội thị trường hay chỉ là một ý tưởng?
2. **Ảnh hưởng tới mục tiêu nào?** Product Goal, mốc phát hành, Sprint Goal hay tiêu chuẩn chất lượng?
3. **Mức khẩn và rủi ro thế nào?** Có yêu cầu an toàn, dữ liệu hoặc cam kết bên ngoài bắt buộc không?
4. **Nếu làm ngay, điều gì phải thay đổi?** Phạm vi khác, thứ tự backlog, thời điểm phát hành, nguồn lực hay chi phí?
5. **Ai cần quyết định và ai cần biết?** Product Owner, Developers, vận hành, bảo mật, người liên quan?

### 12.2. Tình huống thay đổi ưu tiên

Giữa lúc nhóm chuẩn bị R1 “Học tiếp”, bộ phận kinh doanh đề nghị thêm bảng xếp hạng người học cho buổi giới thiệu. Đồng thời, nhóm kiểm thử phát hiện một trường hợp người dùng có thể đọc tiến độ của tài khoản khác.

Có ba luồng xử lý khác nhau:

- **Lỗ hổng quyền truy cập:** phải đánh giá mức nghiêm trọng và xử lý theo tiêu chuẩn an toàn; R1 không nên phát hành tính năng liên quan nếu chưa đáp ứng điều kiện cần thiết.
- **Bảng xếp hạng:** Product Owner tìm hiểu giá trị và tính cấp thiết thực tế, cân nhắc với Product Goal và thứ tự Product Backlog.
- **Kế hoạch R1:** nhóm đánh giá ảnh hưởng, cập nhật dự báo và thông báo phạm vi hoặc mốc mới nếu cần.

Không phải tất cả đều giải quyết bằng cách bỏ phiếu. Những yêu cầu bắt buộc cần cơ chế kiểm soát phù hợp; lựa chọn giá trị sản phẩm cần trách nhiệm ưu tiên rõ; kỹ thuật và năng lực thực hiện cần sự tham gia thực chất của Developers.

### 12.3. Đàm phán “ngày – phạm vi – nguồn lực – chất lượng”

Một cách diễn đạt có trách nhiệm:

> “Chúng ta có thể giữ cửa sổ ra mắt dự kiến nếu chỉ cung cấp luồng cốt lõi đã đạt DoD, và chuyển bảng xếp hạng sang đánh giá sau. Nếu bắt buộc có cả hai trong cùng ngày, chúng ta cần xem lại nguồn lực, rủi ro và khả năng thực hiện; không bỏ kiểm soát quyền truy cập để đạt mốc.”

Đây là **đánh đổi minh bạch**, không phải từ chối thay đổi. Người liên quan nhìn thấy các lựa chọn thay vì nhận một lời hứa không có cơ sở.

## 13. Quản lý phụ thuộc, rủi ro và công việc không hiển thị

Kế hoạch từ vision đến daily thường đứt gãy ở những công việc không hiện rõ trên demo.

### 13.1. Phụ thuộc

Ví dụ, tính năng “Học tiếp” cần dịch vụ video cung cấp thông tin vị trí phát, cơ sở dữ liệu hỗ trợ lưu tiến độ và hệ thống xác thực có quyền truy cập đúng.

Nhóm nên làm rõ:

- Phụ thuộc thuộc **cùng nhóm** hay cần nhóm khác/đối tác?
- Điều kiện giao tiếp, định dạng dữ liệu và thời hạn phản hồi đã rõ chưa?
- Có thể thử sớm bằng một lát dọc hoặc mock có giới hạn để phát hiện rủi ro không?
- Nếu phụ thuộc bị trễ, có phương án thay thế hoặc phạm vi nhỏ hơn không?

Kế hoạch phát hành nên phản ánh phụ thuộc có thể làm đổi mốc, thay vì mặc định mọi bên đều đúng hạn.

### 13.2. Công việc chất lượng và vận hành

Những việc như review code, kiểm thử tự động, quan sát lỗi, xử lý tính nhất quán dữ liệu, sao lưu, phân quyền và chuẩn bị hỗ trợ là **một phần của khả năng giao sản phẩm đáng tin**. Chúng không trở thành “việc không tạo giá trị” chỉ vì người dùng không thấy trực tiếp.

Trong XP, **TDD, continuous integration, refactoring và thiết kế đơn giản** có thể giúp nhóm thay đổi phần mềm nhanh mà giữ chất lượng. Nếu tích lũy nợ kỹ thuật nghiêm trọng, các dự báo roadmap sẽ kém tin cậy do lỗi và công việc làm lại tăng.

### 13.3. Rủi ro và điều kiện dừng

Một kế hoạch thích ứng nên biết khi nào cần:

- **Dừng:** giả thuyết giá trị không được ủng hộ, rủi ro vượt mức chấp nhận.
- **Tạm hoãn:** chưa đủ dữ kiện, phụ thuộc chưa sẵn sàng.
- **Thu hẹp:** giữ kết quả cốt lõi, giảm biến thể chưa cần.
- **Mở rộng:** dữ liệu và năng lực vận hành cho phép.
- **Đổi hướng:** vấn đề người dùng thực tế khác với giả định ban đầu.

Những lựa chọn này nên được ghi ở mức vừa đủ để người liên quan hiểu **vì sao kế hoạch thay đổi**.

## 14. Thiết lập nhịp kiểm tra và thích ứng

Nhóm không cần cập nhật từng tầng kế hoạch mỗi ngày. Cách hữu ích là xác định **nhịp đánh giá phù hợp với tốc độ xuất hiện bằng chứng**.

| Tần suất gợi ý | Nội dung nên kiểm tra | Người thường tham gia |
| --- | --- | --- |
| **Hằng ngày hoặc khi có điểm nghẽn** | Công việc nào chặn mục tiêu ngắn hạn? Cần phối hợp gì để hoàn tất? | Người trực tiếp thực hiện; Developers trong Daily Scrum nếu dùng Scrum. |
| **Mỗi Sprint hoặc nhịp review phù hợp** | Increment đã đạt DoD? Mục tiêu ngắn hạn tiến triển ra sao? Cần thay thứ tự backlog? | Scrum Team/bên liên quan ở các sự kiện phù hợp; hoặc nhóm theo Kanban. |
| **Trước mỗi quyết định phát hành** | Phạm vi, chất lượng, an toàn, vận hành và phản hồi đã sẵn sàng? | Người phụ trách sản phẩm, kỹ thuật, vận hành và chuyên môn liên quan. |
| **Khi có dữ liệu kết quả hoặc thay đổi lớn** | Roadmap còn giải đúng vấn đề? Giả thuyết nào bị bác bỏ? | Product Owner, các bên liên quan và nhóm chuyên môn. |
| **Theo chu kỳ chiến lược của tổ chức** | Tầm nhìn và Product Goal có còn phù hợp với nhu cầu? | Người chịu trách nhiệm định hướng sản phẩm và các bên cần tham gia. |

Đây là gợi ý, **không phải bộ lịch họp bắt buộc**. Có những nhóm cần review roadmap hằng tháng; nhóm khác dựa trên mốc thử nghiệm. Nếu tình huống khẩn cấp xuất hiện, đừng chờ đến cuộc họp định kỳ mới xử lý.

### Bộ câu hỏi dùng xuyên suốt các buổi kiểm tra

- **Vì sao:** điều này đang phục vụ người dùng/mục tiêu nào?
- **Chúng ta đã học gì:** có bằng chứng mới nào làm thay đổi giả định?
- **Điều gì đang chặn:** phụ thuộc, lỗi hoặc quyết định chưa rõ?
- **Phần nhỏ nhất có giá trị tiếp theo là gì:** có thể giao an toàn và kiểm chứng không?
- **Ai quyết định và ai cần được thông báo:** quyền hạn, trách nhiệm và mốc xem lại ra sao?

## 15. Vai trò và trách nhiệm để kế hoạch không bị đứt đoạn

Ở mỗi tổ chức, tên vai trò có thể khác nhau. Trong Scrum, một số trách nhiệm được mô tả rõ; ngoài Scrum, tổ chức nên làm rõ người quyết định tương đương.

| Vai trò/trách nhiệm | Đóng góp chính |
| --- | --- |
| **Người định hướng sản phẩm/đơn vị kinh doanh** | Cung cấp bối cảnh chiến lược, nhu cầu thị trường, ràng buộc và mức đầu tư. |
| **Product Owner (trong Scrum)** | Chịu trách nhiệm tối đa hóa giá trị sản phẩm, phát triển và truyền đạt Product Goal, quản lý Product Backlog hiệu quả, bao gồm sắp thứ tự các mục. |
| **Developers (trong Scrum)** | Lựa chọn cách thực hiện, lập kế hoạch Sprint, thích ứng Sprint Backlog và tạo Increment chất lượng đáp ứng DoD. |
| **Scrum Master (trong Scrum)** | Hỗ trợ Scrum Team và tổ chức áp dụng Scrum hiệu quả, cải thiện khả năng phối hợp và xử lý trở ngại. |
| **Người dùng/bên liên quan** | Phản hồi về nhu cầu, kết quả, giá trị; cung cấp yêu cầu và giới hạn thực tế. |
| **Chuyên môn vận hành, an toàn, bảo mật, dữ liệu...** | Làm rõ ràng buộc chất lượng, mức rủi ro, yêu cầu hỗ trợ và tính sẵn sàng phát hành. |

**Không nên biến Product Owner thành người quyết định chi tiết kỹ thuật thay Developers**, cũng không coi Developers chỉ nhận việc mà không được thảo luận về giá trị. Kế hoạch thích ứng cần cộng tác thực chất giữa người hiểu nhu cầu và người hiểu cách xây dựng.

Một **release plan có cam kết với bên ngoài** có thể còn cần quyết định theo thẩm quyền của tổ chức, hợp đồng hoặc quy định. Cần phân biệt điều đó với sự kiện và trách nhiệm do Scrum định nghĩa.

## 16. Các lỗi lập kế hoạch thường gặp

| Dấu hiệu | Vì sao gây hại | Cách cải thiện |
| --- | --- | --- |
| **Roadmap là danh sách tính năng cố định theo quý.** | Không thấy kết quả và giả định; khó đổi hướng khi dữ liệu mới xuất hiện. | Thể hiện chủ đề, outcome và mốc kiểm chứng; phân biệt dự kiến với cam kết. |
| **Mỗi ngày chỉ hỏi “xong bao nhiêu ticket?”.** | Nhóm tối ưu số lượng thay vì hoàn tất hành vi có giá trị. | Nhắc Sprint Goal/release goal; nhìn Done, điểm nghẽn và chất lượng. |
| **Đánh dấu Done khi code xong.** | Tích hợp, kiểm thử và yêu cầu vận hành bị đẩy về cuối. | Sử dụng DoD và acceptance criteria nhất quán, giao lát dọc. |
| **Xem lộ trình như hợp đồng không được sửa.** | Nhóm tiếp tục xây hướng ít giá trị hoặc giấu rủi ro. | Ghi giả thuyết, điều kiện xem lại và cơ chế cập nhật minh bạch. |
| **Thay đổi liên tục mà không nêu lý do.** | Mất tập trung, khó dự báo, giảm niềm tin giữa các bên. | Dùng mục tiêu và dữ kiện để giải thích đổi thứ tự; làm rõ quyền quyết định. |
| **Cố định cả ngày, phạm vi và nguồn lực, rồi cắt kiểm thử.** | Chất lượng và an toàn giảm; chi phí sửa lỗi tăng. | Đàm phán phạm vi, trình bày mức độ chắc chắn và giữ kiểm soát bắt buộc. |
| **Tạo nhiều task ngang nhưng không có kết quả đầu cuối.** | Mỗi nhóm chuyên môn hoàn tất phần mình, luồng sản phẩm vẫn chưa dùng được. | Chia lát dọc nhỏ có hành vi kiểm chứng được. |
| **Dùng velocity làm thước đo năng suất cá nhân.** | Khuyến khích làm đẹp điểm số, giảm minh bạch. | Đo kết quả, chất lượng, dòng công việc; chỉ dùng số đo phù hợp bối cảnh. |
| **Phát hành xong là kết thúc lập kế hoạch.** | Mất cơ hội biết sản phẩm có tạo giá trị thật không. | Theo dõi sử dụng, phản hồi và cập nhật roadmap/backlog sau phát hành. |
| **Mọi yêu cầu mới đều được kéo vào Sprint ngay.** | Sprint Goal và khả năng tập trung bị phá vỡ. | Đánh giá tác động, trao đổi với Product Owner, xử lý ngoại lệ khẩn một cách rõ ràng. |

## 17. Bài tập thực hành: tạo bản đồ liên kết từ chiến lược tới hôm nay

Bạn là thành viên một nhóm xây nền tảng quản lý lịch học trực tuyến. Tổ chức nêu tầm nhìn:

> “Giảng viên và học viên phối hợp lịch học thuận tiện, giảm bỏ lỡ buổi học và biết rõ thay đổi lịch.”

Dữ liệu ban đầu gợi ý học viên thường bỏ lỡ buổi học vì không nhận ra lịch đã được đổi. Các bên liên quan đề xuất cùng lúc:

- Hiển thị lịch học mới nhất cho học viên.
- Gửi thông báo khi giảng viên đổi lịch.
- Thêm 20 màu sắc tùy chỉnh giao diện lịch.
- Xây hệ thống AI đề xuất lịch tối ưu.
- Ghi lịch sử thay đổi và kiểm soát quyền sửa lịch.
- Xuất lịch ra năm định dạng.
- Tạo trang hỗ trợ để xử lý lỗi thông báo không được gửi.

Nhóm có một giai đoạn thử nghiệm ngắn và cần giải thích được việc nào nên làm trước, phần nào có thể trì hoãn.

### Yêu cầu

1. **Tầm nhìn và mục tiêu:** viết một mục tiêu sản phẩm gần hạn phản ánh vấn đề bỏ lỡ buổi học. Chọn một hoặc hai tín hiệu giá trị.
2. **Roadmap:** tạo ba chủ đề Now/Next/Later. Phân biệt kết quả cần đạt với tính năng dự kiến.
3. **Release plan:** đề xuất một bản thử nghiệm nhỏ cho nhóm học viên/giảng viên giới hạn; nêu điều kiện chất lượng và cách thu phản hồi.
4. **Backlog:** chọn ba hoặc bốn PBI ưu tiên đầu, mỗi mục chỉ ra người hưởng lợi và cách kiểm chứng.
5. **Kế hoạch ngắn hạn:** đề xuất một Sprint Goal hoặc mục tiêu luồng Kanban; nêu một lát dọc đầu tiên.
6. **Hằng ngày:** giả sử nhóm đang chờ kiểm thử phân quyền, nhưng có người muốn mở việc AI mới. Nhóm nên ưu tiên hành động nào và vì sao?
7. **Thích ứng:** nếu bản thử cho thấy thông báo đến đủ nhưng học viên vẫn bỏ lỡ lịch vì khó hiểu múi giờ, roadmap/release plan cần thay đổi ra sao?
8. **Dự báo:** nhóm chỉ có dữ liệu throughput bốn tuần, các mục rất khác độ lớn. Bạn sẽ truyền đạt mức độ tin cậy của mốc phát hành thế nào?

### Một hướng giải tham khảo

**Mục tiêu gần hạn:** Học viên và giảng viên thấy cùng một lịch học đang có hiệu lực, các thay đổi quan trọng được truyền đạt rõ để giảm số lần học viên bỏ lỡ vì thông tin sai lệch.

**Tín hiệu giá trị:** tỷ lệ học viên xem lịch mới trước buổi học và số buổi bị bỏ lỡ do hiểu sai thời gian. Cần có cách ghi nhận nguyên nhân bỏ lỡ, không suy mọi buổi vắng mặt là lỗi thông báo.

**Roadmap:**

| Mức | Chủ đề/kết quả | Chưa cam kết |
| --- | --- | --- |
| **Now** | Lịch hiển thị đúng, thay đổi có lịch sử và người liên quan nhận được thông tin cần thiết. | Tùy chỉnh giao diện nhiều màu. |
| **Next** | Học viên hiểu rõ thời gian, múi giờ và xác nhận đã thấy thay đổi. | Mọi kênh thông báo hoặc định dạng xuất. |
| **Later** | Tối ưu cách chọn lịch phù hợp nhu cầu, nếu có bằng chứng. | Mô hình AI phức tạp. |

**R1 thử nghiệm:** Một lớp học với quyền sửa lịch rõ, trang xem lịch hiện tại, cơ chế thông báo một kênh đáng tin, lịch sử thay đổi và hỗ trợ xử lý lỗi. Chỉ mở cho nhóm thử khi kiểm thử phân quyền, dữ liệu thời gian và trạng thái thông báo đạt điều kiện cần thiết.

**Backlog ưu tiên:** xem lịch có hiệu lực, thay đổi lịch có xác thực/phân quyền, thông báo thay đổi và theo dõi lỗi. Các mục có thể chia thành lát đầu cuối thay vì “xây toàn bộ UI / toàn bộ API / toàn bộ database” riêng biệt.

**Hằng ngày:** Hoàn tất kiểm thử phân quyền đang chặn mục tiêu phát hành quan trọng hơn khởi động ngay AI chưa được xác minh nhu cầu. Nếu có sự cố khẩn khác, đánh giá rủi ro và cập nhật ưu tiên minh bạch.

**Khi có bằng chứng múi giờ là vấn đề:** Ưu tiên hiển thị múi giờ và xác nhận thời gian rõ, rồi kiểm tra lại kết quả; chưa cần mở rộng số kênh thông báo. Điều chỉnh roadmap theo vấn đề thật được phát hiện.

**Dự báo:** Nêu khoảng thời gian có điều kiện và nguồn dữ liệu hạn chế, không suy từ throughput của các mục kích thước khác nhau thành ngày chính xác. Tách rõ phần cốt lõi bắt buộc với biến thể có thể lùi.

## 18. Tự kiểm tra kiến thức

**Câu 1.** Một roadmap ghi “Tháng 1: dashboard; tháng 2: AI; tháng 3: báo cáo PDF”. Thiếu điều gì quan trọng nếu muốn dùng làm lộ trình thích ứng?

**Đáp án:** Thiếu vấn đề, kết quả người dùng, giả thuyết, phụ thuộc và điều kiện kiểm chứng; các mốc có thể tạo ấn tượng cam kết cố định dù chưa có bằng chứng.

**Câu 2.** Product Goal và Sprint Goal khác nhau như thế nào?

**Đáp án:** Product Goal là đích dài hạn cho sản phẩm và cam kết của Product Backlog trong Scrum. Sprint Goal là mục tiêu thống nhất, ngắn hạn của Sprint; công việc Sprint được tổ chức để tiến tới mục tiêu đó.

**Câu 3.** Một Increment đã đạt DoD nhưng vẫn tắt bằng feature flag. Đã phát hành cho người dùng chưa?

**Đáp án:** Chưa nhất thiết. Increment có thể sử dụng và hoàn tất; việc mở tính năng cho người dùng là quyết định phát hành riêng.

**Câu 4.** Nhóm hoàn tất nhiều ticket hơn nhưng tỷ lệ người dùng hoàn thành tác vụ không tăng. Có thể kết luận roadmap thành công không?

**Đáp án:** Không. Đầu ra và năng lực giao hàng có thể đã thay đổi, nhưng cần kiểm tra kết quả sản phẩm và giả thuyết giá trị.

**Câu 5.** Vì sao throughput trung bình từ bốn tuần không đủ để cam kết chính xác ngày phát hành?

**Đáp án:** Mẫu nhỏ, kích cỡ công việc thay đổi, phụ thuộc và rủi ro chưa biết, cùng các việc chuẩn bị phát hành có thể làm kết quả khác dự kiến.

**Câu 6.** Công việc kiểm thử phân quyền chưa xong nhưng người quản lý muốn phát hành đúng ngày. Điều gì có thể thay đổi và điều gì không nên bị bỏ?

**Đáp án:** Có thể xem lại phạm vi tính năng, đối tượng hoặc thời điểm phát hành; không nên bỏ các kiểm soát chất lượng, bảo mật và quyền truy cập cần thiết.

**Câu 7.** Trong Daily Scrum, nhóm chỉ đọc trạng thái từng task lên cho Scrum Master. Đã tận dụng tốt sự kiện này chưa?

**Đáp án:** Chưa. Developers nên kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh kế hoạch, nhất là phối hợp giải quyết trở ngại.

**Câu 8.** Một nhóm Kanban không có Sprint có thể liên kết việc hằng ngày với product vision và release plan không?

**Đáp án:** Có. Nhóm có thể sử dụng Product Backlog hoặc hệ thống ưu tiên tương đương, chính sách kéo việc, giới hạn WIP, các mốc review và phản hồi để giữ liên kết.

**Câu 9.** Khi phản hồi cho thấy giải pháp ban đầu không hiệu quả, nên giữ nguyên tính năng trên roadmap vì đã thông báo từ trước không?

**Đáp án:** Không mặc định. Cần làm rõ bằng chứng và cam kết thực tế, trình bày phương án thay đổi với các bên liên quan, giữ mục tiêu giá trị và điều chỉnh hướng giải pháp khi hợp lý.

## 19. Những điều cần ghi nhớ

- **Tầm nhìn chỉ ra “vì sao”; mục tiêu sản phẩm mô tả “đạt kết quả gì”; roadmap định hướng “giải quyết vấn đề nào trước”; release plan dự báo “giao cho ai, trong điều kiện nào”; backlog và việc hằng ngày xác định “làm gì tiếp theo”.**
- **Liên kết hai chiều quan trọng hơn nhiều tài liệu.** Công việc nên giải thích được giá trị phục vụ; phản hồi thực tế có thể thay đổi ưu tiên và giả thuyết cấp trên.
- **Roadmap thiên về outcome và giả thuyết**, không chỉ liệt kê tính năng theo ngày. Cam kết với bên ngoài cần được phân biệt với dự báo.
- **Release plan phải bao gồm chất lượng, an toàn, vận hành và cách học sau phát hành.** Increment đạt DoD không đồng nghĩa đã release hay đã tạo giá trị.
- **Backlog và user story giúp chuyển mục tiêu thành lát dọc có thể kiểm chứng.** Task kỹ thuật là phương tiện để đạt hành vi có ích.
- **Scrum dùng Product Goal, Sprint Goal, Sprint Backlog và Increment để tạo nhịp kiểm tra/thích ứng**; Kanban dùng chính sách luồng, giới hạn WIP và các số đo giao hàng. Có thể kết hợp khi phù hợp.
- **Công việc hằng ngày nên ưu tiên hoàn tất mục đang chặn mục tiêu và giữ chất lượng**, thay vì tăng số việc mới bắt đầu.
- **Dự báo là có điều kiện.** Throughput, cycle time và dữ liệu lịch sử hỗ trợ trao đổi về khả năng giao hàng, không biến tương lai thành chắc chắn.
- **Khi dữ liệu mới xuất hiện, hãy trao đổi và điều chỉnh kế hoạch minh bạch.** Không bảo vệ một danh sách tính năng bằng cách bỏ qua phản hồi, rủi ro hoặc nhu cầu thực.

Một nhóm Agile phối hợp tốt không chỉ biết **hôm nay ai làm việc gì**, mà còn biết **vì sao việc đó quan trọng, bằng chứng nào cho thấy nó hữu ích và điều gì sẽ khiến nhóm đổi kế hoạch**. Khi tầm nhìn, lộ trình, kế hoạch phát hành và công việc hằng ngày được nối thành một vòng học hỏi, phần mềm có thể được giao tăng dần và thích ứng với những điều nhóm thực sự khám phá trong quá trình phát triển.
