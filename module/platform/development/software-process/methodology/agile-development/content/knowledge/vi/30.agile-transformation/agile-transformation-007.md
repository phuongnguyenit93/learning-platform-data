# Xử lý lo ngại và sự kháng cự thông qua đối thoại cùng bằng chứng

## 1. Khi chuyển đổi Agile gặp câu nói “cách cũ vẫn tốt hơn”

Một công ty xây dựng nền tảng học trực tuyến muốn chuyển từ cách làm theo dự án lớn sang phát triển tăng dần. Ban lãnh đạo đề xuất dùng Scrum cho một số nhóm, giới hạn WIP ở các luồng hỗ trợ và đưa kiểm thử tự động vào CI. Trong cuộc trao đổi, các ý kiến xuất hiện:

- Người quản lý dự án: “Nếu đội tự quản, ai chịu trách nhiệm khi kế hoạch trễ?”
- Người kiểm thử: “Sprint ngắn quá, liệu mọi người có bỏ qua kiểm thử để báo Done?”
- Kỹ sư có kinh nghiệm: “Tôi đang chịu trách nhiệm hệ thống quan trọng; nếu thay quy trình liên tục, ai bảo đảm sự cố không tăng?”
- Product Owner mới: “Tôi có phải quyết định hết mọi thứ dù thiếu thông tin nghiệp vụ?”
- Bộ phận tài chính: “Nếu backlog được thay đổi thường xuyên, chúng ta kiểm soát chi phí và hợp đồng thế nào?”
- Nhân viên ở nhóm phân tán: “Lại thêm Daily Scrum và Review ngoài giờ làm của tôi sao?”

Phản ứng dễ gặp là gắn nhãn những người này **“chống Agile”**, rồi tổ chức thêm khóa đào tạo hoặc yêu cầu tuân thủ biểu mẫu. Nhưng mỗi ý kiến trên có thể chứa **một rủi ro thực tế cần giải quyết**: trách nhiệm ra quyết định, khả năng bảo đảm chất lượng, tải công việc, năng lực chuyên môn, thẩm quyền, hoặc chi phí.

**Xử lý lo ngại và sự kháng cự thông qua đối thoại cùng bằng chứng** không phải kỹ thuật khiến mọi người đồng ý với quyết định đã định sẵn. Đó là quá trình:

1. Hiểu điều người liên quan đang bảo vệ và họ có cơ sở gì.
2. Công khai mục tiêu, giới hạn và những điều chưa chắc của thay đổi.
3. Cùng xác định giả thuyết có thể kiểm chứng.
4. Thử những thay đổi phù hợp, an toàn và có thể điều chỉnh.
5. Xem kết quả cùng nhau, thừa nhận tác dụng phụ và thay đổi kế hoạch khi cần.

Trong chương **Chuyển đổi Agile** của module **AGILE_DEVELOPMENT**, các thực hành user story, backlog, Scrum, Kanban, XP và đo lường flow phải phục vụ **giá trị người dùng, phản hồi sớm và cải tiến liên tục**, không trở thành mục tiêu tuân thủ hình thức. Sự đồng thuận bền vững đến từ **minh bạch, quyền tham gia có ý nghĩa và bằng chứng**, chứ không phải khẩu hiệu “hãy linh hoạt hơn”.

### Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **lo ngại có căn cứ, bất đồng chuyên môn, kháng cự với cách triển khai và hành vi cản trở gây hại** mà không quy chụp động cơ.
2. Tổ chức cuộc đối thoại lắng nghe để tìm **rủi ro, nhu cầu, lợi ích bị ảnh hưởng và điều kiện chấp nhận**.
3. Chuyển phát biểu “Agile không phù hợp” thành **câu hỏi và giả thuyết kiểm chứng được**.
4. Thiết kế thí nghiệm chuyển đổi có phạm vi, quyền quyết định, baseline, outcome, guardrails và cơ chế dừng.
5. Đối thoại phù hợp với Developers, Product Owner, Scrum Master, người quản lý, kiểm thử, vận hành, tài chính và nhóm phân tán.
6. Sử dụng dữ liệu **flow, chất lượng, giá trị và sức khỏe nhóm** mà không lạm dụng metric để gây áp lực cá nhân.
7. Nhận biết khi nào phải **điều chỉnh hoặc dừng hướng chuyển đổi**, thay vì tiếp tục thuyết phục một cách cưỡng ép.

## 2. “Kháng cự” không phải một chẩn đoán về con người

Trong thay đổi tổ chức, cùng một hành vi “không đồng ý” có thể xuất phát từ nhiều lý do. Việc quy về tính cách cá nhân làm mất cơ hội hiểu vấn đề.

| Hiện tượng | Diễn giải cần kiểm tra | Cách phản ứng nên thử |
|---|---|---|
| **Lo ngại** | Người tham gia dự đoán có tác động xấu hoặc chưa hiểu cách bảo vệ quyền lợi. | Hỏi điều gì đáng lo, bằng chứng và điều kiện để giảm rủi ro. |
| **Bất đồng chuyên môn** | Có nhận định khác về cách làm tốt hoặc tiêu chuẩn kỹ thuật. | So sánh giả thuyết, tiêu chí chất lượng và phép thử hợp lệ. |
| **Thiếu thông tin** | Chưa rõ mục tiêu, trách nhiệm, thời hạn hoặc lý do thay đổi. | Minh bạch quyết định và giải thích bằng ví dụ cụ thể. |
| **Thiếu năng lực/nguồn lực** | Người tham gia muốn làm nhưng thiếu thời gian, kỹ năng, công cụ hoặc quyền. | Cấp hỗ trợ, huấn luyện, cải thiện phụ thuộc và giảm WIP. |
| **Không tin vào cách triển khai** | Đã từng có thay đổi công bố rồi bỏ dở hoặc dùng KPI để trừng phạt. | Thừa nhận lịch sử, nhất quán giữa lời nói và quyết định thực tế. |
| **Xung đột lợi ích/quyền quyết định** | Thay đổi vai trò, ngân sách, phân quyền hoặc sự đánh giá thành tích. | Thương lượng minh bạch với người có thẩm quyền, không giả vờ chỉ là thiếu kiến thức. |
| **Không thể đồng ý vì nghĩa vụ** | Cách thay đổi có thể vi phạm an toàn, bảo mật, hợp đồng hoặc quy định. | Dừng điểm rủi ro, tham vấn chuyên gia có quyền, sửa thiết kế. |
| **Hành vi cản trở cụ thể** | Ví dụ cố tình làm sai hoặc phá kiểm soát đã được xác minh. | Xử lý hành vi theo chính sách công bằng, bằng chứng và thẩm quyền; không đánh đồng với phản biện. |

**Không phải mọi ý kiến phản đối đều đúng, nhưng cũng không phải mọi ý kiến ủng hộ đều có bằng chứng.** Cần đánh giá nội dung, tác động và giả định, không phân loại người thành “Agile” và “anti-Agile”.

### 2.1. Phân biệt phản đối mục tiêu và phản đối phương tiện

Ví dụ:

- “Tôi không muốn người dùng phải chờ sáu tháng mới nhận cải tiến” — đồng ý với **mục tiêu phản hồi sớm**.
- “Tôi không đồng ý triển khai Scrum cho dịch vụ có quá nhiều yêu cầu khẩn” — phản đối **một phương tiện cụ thể**.

Người đó có thể ủng hộ Agile nhưng cho rằng **Kanban, một nhịp phối hợp khác hoặc cách xử lý luồng khẩn** phù hợp hơn. Không cần buộc họ chọn Scrum để chứng minh thiện chí.

### 2.2. Sự im lặng cũng cần được tìm hiểu

Không phát biểu trong họp không đồng nghĩa đồng thuận. Người tham gia có thể:

- Không có cơ hội nói vì cấp bậc hoặc ngôn ngữ.
- Sợ bị đánh giá tiêu cực.
- Chưa có đủ dữ liệu để đưa ra ý kiến.
- Đã phản hồi nhiều lần nhưng không thấy thay đổi.
- Không thấy cuộc họp ảnh hưởng tới quyết định thực.

Để biết, có thể mở kênh góp ý riêng tư phù hợp, trao đổi nhóm nhỏ hoặc thu phản hồi trước buổi thảo luận. **Không nên dùng việc không phát biểu làm bằng chứng “100% nhân viên ủng hộ”.**

## 3. Chuyển đổi Agile là thay đổi hệ thống làm việc, không chỉ đổi tên sự kiện

Một tổ chức có thể tổ chức Daily Scrum, Sprint Review và Retrospective nhưng vẫn:

- Giao mọi yêu cầu theo lệnh từ cấp trên mà không thảo luận giá trị.
- Đánh giá thành công chỉ theo số story point hoặc tỷ lệ bận rộn.
- Không cho phép đổi backlog dù phản hồi cho thấy giải pháp sai.
- Đẩy kiểm thử, bảo mật và vận hành xuống cuối chu kỳ.
- Giữ các hàng chờ phê duyệt kéo dài nhiều tuần.
- Trừng phạt người báo lỗi hoặc đặt câu hỏi về kế hoạch.

Đổi nghi thức mà không thay đổi **quyền, luồng quyết định, phản hồi và chất lượng** dễ làm người tham gia mất niềm tin.

### 3.1. Năm lớp của một thay đổi

| Lớp | Điều có thể thay đổi | Câu hỏi lo ngại |
|---|---|---|
| **Mục tiêu** | Từ giao phạm vi cố định sang kiểm chứng outcome. | “Nếu không biết chắc scope, tôi chịu trách nhiệm về gì?” |
| **Dòng công việc** | Chia lát nhỏ, giới hạn WIP, tích hợp thường xuyên. | “Việc của tôi có bị ngắt quãng hoặc thay đổi vô hạn không?” |
| **Vai trò và quyền** | Trách nhiệm Product Owner, Developers, người quản lý, quản trị rủi ro. | “Ai thực sự có quyền quyết định và ai chịu hệ quả?” |
| **Kỹ thuật và chất lượng** | CI, TDD, review, DoD, khả năng vận hành. | “Có đủ hạ tầng và thời gian để làm đúng không?” |
| **Đánh giá và khuyến khích** | Từ chỉ số hoạt động sang flow, outcome và cải tiến. | “KPI mới có bị dùng để xếp hạng hoặc cắt nhân sự không?” |

Một kế hoạch chuyển đổi chỉ nói về lịch sự kiện **bỏ qua phần lớn nguyên nhân lo ngại**. Cần đặt câu hỏi theo từng lớp thay vì “mọi người có muốn Agile không?”.

### 3.2. Xác định điều gì không thay đổi

Minh bạch về những ràng buộc vẫn còn cũng quan trọng:

- Nghĩa vụ bảo vệ dữ liệu và kiểm soát an toàn.
- Quy định hợp đồng và tài chính.
- Trách nhiệm giải trình khi có sự cố.
- Các yêu cầu chất lượng, tính đúng và khả năng truy cập.
- Những chính sách lao động, quyền và nghĩa vụ áp dụng.

Agile không tự xóa các trách nhiệm đó. Nhóm có thể thay đổi **cách đáp ứng và kiểm chứng**, không tự ý bỏ yêu cầu bắt buộc.

## 4. Vì sao lo ngại có thể hoàn toàn hợp lý?

Nếu một tổ chức đang dùng kiểm soát chặt vì từng gặp sự cố mất dữ liệu, lời đề xuất “bỏ phê duyệt để nhanh hơn” cần bị chất vấn. Vấn đề có thể là **cách phê duyệt hiện tại chậm**, nhưng rủi ro mà nó bảo vệ vẫn tồn tại.

### 4.1. Lo ngại về chất lượng

> “Sprint hai tuần khiến chúng tôi không đủ thời gian kiểm thử.”

Điều cần hiểu:

- Thử nghiệm nào đang cần nhiều thời gian?
- Kiểm thử bị đặt cuối Sprint vì kiến trúc hoặc phụ thuộc nào?
- Definition of Done có rõ và thực hiện được không?
- Có cơ chế CI, tự động hóa hoặc chia lát nhỏ giúp kiểm tra sớm không?
- Mốc phát hành có bị nhầm với mốc kết thúc Sprint không?

Giải pháp không phải hứa rằng “làm Agile sẽ hết lỗi”. Có thể cần **giảm phạm vi Sprint, tích hợp sớm và đầu tư chất lượng** trước khi tăng nhịp giao hàng.

### 4.2. Lo ngại về quyền và trách nhiệm

> “Tự quản nghĩa là quản lý không chịu trách nhiệm nữa?”

Điều cần làm rõ:

- Trách nhiệm của Developers, Product Owner và Scrum Master được hiểu ra sao?
- Ai phê duyệt nguồn lực, quyết định an toàn, điều phối nhiều đội?
- Người quản lý còn trách nhiệm tạo điều kiện, phát triển năng lực và gỡ trở ngại gì?
- Có những quyết định nào chưa được ủy quyền thực sự?

Nếu chỉ đổi chức danh mà không đổi quyền, đội sẽ rơi vào **trách nhiệm không đi kèm thẩm quyền**.

### 4.3. Lo ngại về công việc và đánh giá

> “Nếu công ty dùng velocity để đánh giá từng cá nhân, tôi không muốn tham gia.”

Đây là lo ngại có cơ sở: story points và velocity **không phải chỉ số năng suất cá nhân**, và không đáng tin để so sánh trực tiếp giữa các đội.

Tổ chức cần có chính sách rõ rằng dữ liệu phục vụ **học hỏi và dự báo trong ngữ cảnh**, không trở thành bảng xếp hạng gây méo động lực. Nếu quyền lợi, vị trí hoặc thu nhập sẽ bị ảnh hưởng, không thể xử lý bằng một bài thuyết trình truyền cảm hứng; phải có thông tin và đối thoại chính thức phù hợp.

### 4.4. Lo ngại về tải và thời gian

> “Chúng tôi đang thiếu người, chuyển đổi chỉ thêm họp.”

Cần kiểm tra thực tế:

- Có thể bỏ hoặc rút ngắn cuộc họp cũ nào?
- Có thể dùng cập nhật bất đồng bộ thay vì họp đọc trạng thái?
- Có dành năng lực cho học công cụ, thực hành CI và cải tiến không?
- Việc đang làm dở có quá nhiều không?
- Có giờ làm ngoài ca, công việc trực hay sự cố chưa được tính?

**Không nên yêu cầu người lao động làm thêm ngoài giờ không được thỏa thuận chỉ để báo chỉ số chuyển đổi tốt.**

## 5. Bản đồ stakeholder: hiểu ảnh hưởng, quyền và điều kiện tham gia

Đối thoại hiệu quả cần đúng người. Không phải tất cả đều có cùng thông tin, mức ảnh hưởng hoặc quyền quyết định.

| Nhóm liên quan | Điều họ thường cần bảo vệ | Bằng chứng/cách tham gia phù hợp |
|---|---|---|
| **Người dùng/khách hàng** | Tác vụ hoàn thành, độ tin cậy, khả năng tiếp cận. | Quan sát hành trình, phản hồi, số liệu outcome. |
| **Developers** | Chất lượng kỹ thuật, khả năng tập trung, quyền tự quản cách làm. | Flow và lỗi thực, thử CI/TDD, tiếng nói về thiết kế kỹ thuật. |
| **Người làm kiểm thử** | Không giảm kiểm chứng và không đẩy lỗi tới người dùng. | DoD, kiểm tra chất lượng xuyên vòng đời, dữ liệu lỗi thoát. |
| **Product Owner/nghiệp vụ** | Quyết định đúng giá trị, minh bạch ưu tiên và chi phí. | Product Goal, ví dụ user story, kết quả thí điểm. |
| **Scrum Master/coach** | Hiệu quả và khả năng học hỏi của nhóm. | Quan sát hệ thống, blocker, thực nghiệm và phản hồi. |
| **Người quản lý** | Trách nhiệm giải trình, năng lực nhân sự, nguồn lực. | Quyền quyết định, forecast, rủi ro và kết quả. |
| **Bảo mật/vận hành** | Không vi phạm tiêu chuẩn, dịch vụ có thể duy trì. | Quality gates, rủi ro, runbook và tín hiệu production. |
| **Tài chính/pháp lý/mua sắm** | Tuân thủ trần, hợp đồng, truy vết quyết định. | Giới hạn chi, milestone, actual/forecast và hồ sơ. |
| **Đối tác/nhà cung cấp** | Điều khoản cam kết, chi phí thay đổi, phụ thuộc. | Hợp đồng, chính sách change control, nghiệm thu Increment. |

### 5.1. Không dùng stakeholder map để gắn nhãn “người gây khó”

Bản đồ nhằm thiết kế **quyền tham gia, kênh phản hồi và trách nhiệm**, không chia người thành nhóm “ủng hộ cần thưởng” và “chống đối phải vô hiệu hóa”.

### 5.2. Ai có quyền nói và ai có quyền quyết?

Một cuộc trao đổi nên phân biệt:

- **Người cung cấp dữ kiện:** có kinh nghiệm hoặc bị ảnh hưởng.
- **Người thực hiện:** có khả năng làm thay đổi.
- **Người có quyền quyết định:** được tổ chức giao thẩm quyền trong phạm vi.
- **Người bảo đảm kiểm soát bắt buộc:** có quyền/nghĩa vụ chuyên môn phù hợp.
- **Người cần được thông báo:** phải hiểu quyết định để không hành động theo giả định cũ.

Lắng nghe mọi người **không đồng nghĩa mọi quyết định đều phải đạt đồng thuận tuyệt đối**. Nhưng quyền quyết định phải minh bạch, lý do được giải thích, và ý kiến phản biện quan trọng không bị xóa bỏ chỉ vì không được chọn.

## 6. Lắng nghe chủ động trước khi thuyết phục

Khi gặp câu nói “Agile không hiệu quả”, phản ứng đầu tiên không nên là trình bày mười hai nguyên tắc Agile hay trích dẫn một biểu đồ năng suất. Hãy **tìm tình huống cụ thể và điều người nói đang lo mất đi**.

### 6.1. Một chuỗi câu hỏi gợi mở

1. “Điều gì trong cách thay đổi này khiến bạn lo nhất?”
2. “Bạn đã thấy tình huống cụ thể nào dẫn tới lo ngại đó?”
3. “Hậu quả với người dùng, đội hoặc trách nhiệm của bạn là gì?”
4. “Chúng ta đã có bằng chứng nào, điều gì còn đang giả định?”
5. “Điều kiện tối thiểu nào cần giữ để thử thay đổi an toàn?”
6. “Có phiên bản nhỏ, có thể đảo ngược của thay đổi để chúng ta cùng kiểm tra không?”
7. “Nếu dữ liệu cho thấy cách mới tệ hơn, chúng ta cần làm gì?”

Không phải cuộc trao đổi nào cũng cần hỏi đủ bảy câu theo thứ tự. Điều quan trọng là **tò mò về vấn đề**, không tìm cách dẫn dắt người nói tới câu trả lời đã muốn.

### 6.2. Nhắc lại để xác nhận đúng ý

Ví dụ:

> “Tôi hiểu rằng bạn không phản đối việc giao sớm, mà lo khi thời điểm phát hành được coi là deadline bắt buộc, đội sẽ không đủ thời gian kiểm tra quyền truy cập. Tôi hiểu đúng không?”

Nếu người đối thoại sửa lại, hãy **cập nhật cách hiểu**. Một lời nhắc lại không chính xác nhưng được nói rất lịch sự vẫn làm mất tin cậy.

### 6.3. Hỏi về hệ quả, không đoán động cơ

Tránh:

> “Bạn phản đối vì sợ mất quyền kiểm soát.”

Nên hỏi:

> “Những quyết định hoặc trách nhiệm nào của nhóm quản lý sẽ thay đổi? Điều gì bạn cần thấy rõ để vẫn bảo đảm trách nhiệm giải trình?”

Người nói có thể thực sự lo quyền lực, nhưng cũng có thể lo nghĩa vụ pháp lý hoặc tác động tới khách hàng. **Không có dữ liệu thì không nên chẩn đoán động cơ.**

### 6.4. Lắng nghe phải có đầu ra

Nếu người tham gia nhiều lần phản ánh một blocker mà không thấy quyết định, lời mời “hãy chia sẻ thẳng thắn” có thể trở thành nghi thức. Sau đối thoại cần ghi:

- Điều đã hiểu và bằng chứng đang có.
- Điều còn tranh luận hoặc chưa xác nhận.
- Ai sẽ làm việc gì để kiểm chứng.
- Người có thẩm quyền sẽ quyết định khi nào.
- Phản hồi được trả về cho người tham gia bằng cách nào.

## 7. Đối thoại an toàn tâm lý không có nghĩa tránh bất đồng

**An toàn tâm lý (psychological safety)** trong nhóm là khả năng nêu câu hỏi, nhận lỗi, thừa nhận chưa biết và phản biện công việc mà không sợ bị đối xử bất công vì hành vi học hỏi thiện chí.

Nó **không** có nghĩa mọi ý tưởng đều được chấp nhận, không có trách nhiệm chất lượng, hoặc mọi cuộc trò chuyện phải dễ chịu.

### 7.1. Những hành vi hỗ trợ phản biện có ích

- Lãnh đạo nói rõ những điều mình chưa chắc và chấp nhận bị kiểm chứng.
- Người chủ trì mời tiếng nói từ vai trò dễ bị bỏ qua, không ép ai công khai thông tin nhạy cảm.
- Phân biệt **phản đối nội dung** với **công kích cá nhân**.
- Thừa nhận khi một quan ngại đã giúp ngăn rủi ro thực.
- Cho phép thử nghiệm thất bại về giả thuyết nhưng yêu cầu minh bạch và bảo vệ người dùng.
- Có đường báo rủi ro về an toàn, đạo đức hoặc vi phạm chính sách mà không phải qua đúng người bị phản ánh.

### 7.2. Dấu hiệu môi trường thiếu an toàn

| Dấu hiệu | Rủi ro |
|---|---|
| Chỉ người có chức vụ cao phát biểu. | Quyết định thiếu dữ kiện từ người trực tiếp làm việc. |
| Nêu lỗi bị hỏi “Ai làm sai?” trước khi hỏi “Hệ thống nào cho phép lỗi xảy ra?”. | Nhân viên giấu lỗi hoặc báo muộn. |
| Mọi Retrospective đều “không có vấn đề”. | Bằng chứng trái chiều không đi vào cải tiến. |
| Người phản biện bị loại khỏi cuộc họp tiếp theo. | Tổ chức mất khả năng tự điều chỉnh. |
| Các chỉ số bị dùng để so sánh cá nhân bất chấp cảnh báo. | Metric gaming, che dấu WIP và giảm chất lượng. |

### 7.3. Giữ quyền riêng tư và giới hạn bảo mật

Trong một số trường hợp, lo ngại liên quan điều kiện lao động, quyền lợi, sức khỏe hoặc trải nghiệm khó nói công khai. **Không nên yêu cầu kể thông tin cá nhân trước tập thể để chứng minh ý kiến hợp lệ.** Cung cấp kênh phù hợp, bảo vệ dữ liệu và xử lý theo chính sách của tổ chức.

## 8. Một khuôn đối thoại năm bước: Nghe – Làm rõ – Đồng thiết kế – Thử – Xem lại

Khuôn này là **gợi ý thực hành**, không phải một framework chính thức bắt buộc của Scrum.

~~~mermaid
flowchart TD
    A["Nghe: điều gì đang gây lo ngại?"] --> B["Làm rõ: dữ kiện, giả định, tác động, quyền"]
    B --> C["Đồng thiết kế: thay đổi nhỏ và guardrails"]
    C --> D["Thử: đo trước–sau trong phạm vi hợp lệ"]
    D --> E["Xem lại: kết quả, người chịu tác động, chi phí"]
    E --> F{"Quyết định"}
    F -->|Duy trì có điều kiện| G["Cập nhật working agreement / backlog"]
    F -->|Sửa cách thử| C
    F -->|Dừng| H["Ghi bài học và lựa chọn mới"]
    G --> I["Theo dõi lâu dài"]
    I --> A
~~~

### 8.1. Nghe: hiểu quan ngại ở mức có thể thảo luận

Đầu ra nên là một phát biểu cụ thể:

> “Người kiểm thử lo có nhiều PBI chuyển trạng thái Done trước khi integration test hoàn tất, làm lỗi đi tới production.”

Không viết:

> “QA chống thay đổi vì chưa có tư duy Agile.”

### 8.2. Làm rõ: tách dữ kiện khỏi giả định

Ví dụ:

- **Dữ kiện:** trong ba Sprint gần nhất, một số PBI được ghi Done dù kiểm thử tích hợp còn chờ.
- **Giả định:** Sprint ngắn là nguyên nhân chính.
- **Giới hạn:** chưa phân tích WIP, tích hợp cuối chu kỳ, dữ liệu thử hoặc quyền quyết định DoD.

Nếu dữ liệu cho thấy DoD bị hạ để đạt deadline, cần giải quyết **trách nhiệm và tiêu chuẩn chất lượng**, không chỉ huấn luyện người kiểm thử “đón nhận thay đổi”.

### 8.3. Đồng thiết kế: tìm phần có thể thay đổi và phần không thể bỏ

Ví dụ:

- **Không thể bỏ:** kiểm tra phân quyền, tính đúng dữ liệu và các tiêu chuẩn DoD áp dụng.
- **Có thể thử:** chia story nhỏ, thiết lập dữ liệu test sớm, tích hợp thường xuyên, chạy contract test trong CI.
- **Cần hỗ trợ:** thời gian Developers và người kiểm thử hợp tác từ refinement.

### 8.4. Thử: chọn rủi ro nhỏ và phép đo có ý nghĩa

Không nên yêu cầu cả tổ chức đổi quy trình ngay nếu một nhóm có thể thử trong phạm vi an toàn và tạo bằng chứng đủ cho quyết định kế tiếp.

### 8.5. Xem lại: chấp nhận thay đổi quyết định

Một cuộc đối thoại chỉ thực sự có giá trị khi bằng chứng **có khả năng thay đổi phương án**, kể cả chuyển từ Scrum sang Kanban trong phạm vi thích hợp, điều chỉnh cơ chế báo cáo hoặc giữ lại một bước kiểm soát chất lượng đang hoạt động tốt.

## 9. Chuyển nỗi lo thành giả thuyết kiểm chứng được

Những phát biểu tuyệt đối như “Scrum làm mọi người họp nhiều”, “Kanban không có cam kết” hay “CI sẽ khiến đội chậm hơn” nên được làm rõ thành tình huống và phép đo.

| Ý kiến ban đầu | Câu hỏi cần làm rõ | Giả thuyết có thể kiểm chứng |
|---|---|---|
| “Daily Scrum lãng phí thời gian.” | Có bao nhiêu phút họp chỉ để báo cáo, có giúp điều chỉnh kế hoạch? | Nếu cập nhật trạng thái trước và dùng sự kiện để xử lý phụ thuộc hướng tới Sprint Goal, tổng thời gian phối hợp và blocked time có thể giảm. |
| “Sprint khiến kiểm thử bị ép.” | Do timebox hay do chia story/tích hợp muộn/DoD? | Nếu chia lát và chạy integration test sớm, số PBI dồn kiểm thử cuối Sprint giảm mà không hạ DoD. |
| “WIP limit làm đội nhàn rỗi.” | Đội thực sự có ít việc cần làm hay đang mở quá nhiều việc dở? | Nếu giới hạn WIP và hỗ trợ hoàn thành việc đang chặn, cycle time/work item age có thể giảm. |
| “Pair programming tốn gấp đôi nhân lực.” | Lo chi phí giờ hay thời gian sửa lỗi và truyền tri thức? | Trong vùng mã rủi ro cao, pair có thể giảm rework và lỗi sau review với chi phí tổng phù hợp. |
| “Chia user story nhỏ làm rời rạc kiến trúc.” | Phần nhỏ có tạo giá trị tích hợp hay chỉ tách task kỹ thuật? | Nếu chia theo lát hành vi và giữ contract/DoD, nhóm có thể phản hồi sớm mà vẫn bảo toàn kiến trúc. |
| “Product Owner quyết định chủ quan.” | Có thiếu dữ liệu, thiếu quyền hoặc thiếu người hiểu nghiệp vụ? | Nếu ghi Product Goal, tiêu chí ưu tiên và bằng chứng, quyết định backlog sẽ dễ giải thích hơn. |
| “Agile mất kiểm soát chi phí.” | Cần forecast và quyền duyệt ở mức nào? | Nếu có trần theo giai đoạn, forecast cập nhật và checkpoint outcome, tổ chức vẫn kiểm soát vốn và thay đổi giải pháp kịp thời. |

**Mỗi giả thuyết là đề xuất cần thử**, không phải lời hứa chắc chắn rằng mọi chỉ số sẽ tốt hơn.

### 9.1. Phản biện cũng phải chịu kiểm chứng

Nếu người chuyển đổi yêu cầu người phản đối mang bằng chứng, chính đề xuất chuyển đổi cũng phải có **bằng chứng và điều kiện dừng**. Không công bằng khi ý kiến “Agile sẽ cải thiện tất cả” được xem là chân lý còn mọi nghi ngờ đều bị xem là thiếu tư duy.

### 9.2. Nếu không đo được outcome ngay

Một số tác động như khả năng chia sẻ kiến thức hoặc sự tin cậy cần thời gian. Có thể dùng quan sát định tính, khảo sát có bảo vệ riêng tư hoặc chỉ số quá trình hỗ trợ. Phải ghi rằng **đó là proxy**, không báo nó như tác động dài hạn đã chứng minh.

## 10. Bằng chứng nào đáng tin và bằng chứng nào chỉ là tín hiệu?

Đối thoại bằng dữ liệu cần **hiểu dữ liệu đến từ đâu, đo điều gì và có thể kết luận tới mức nào**.

| Loại bằng chứng | Công dụng | Giới hạn quan trọng |
|---|---|---|
| **Lời kể về tình huống cụ thể** | Phát hiện rào cản, hậu quả, niềm tin và nhu cầu. | Không tự đại diện cho toàn tổ chức. |
| **Phỏng vấn và quan sát công việc** | Hiểu cách công việc thực sự diễn ra, nơi có vòng chờ và phối hợp. | Có thể chịu thiên lệch người tham gia và người quan sát. |
| **Dữ liệu flow (WIP, cycle time, throughput, work item age)** | Mô tả dòng công việc và nút thắt. | Không tự chứng minh giá trị người dùng hoặc nguyên nhân thay đổi. |
| **Dữ liệu chất lượng và vận hành** | Xem lỗi hồi quy, sự cố, khôi phục, test và DoD. | Mẫu sự cố hiếm; số lỗi thấp có thể do không phát hiện/báo. |
| **Outcome người dùng** | Xem hành vi hoặc trải nghiệm có tốt hơn. | Cần cohort, định nghĩa, cửa sổ và xem yếu tố ngoài. |
| **Thí điểm trước–sau** | Học về tính khả thi và xu hướng trong phạm vi nhỏ. | Không loại bỏ mọi biến nhiễu hay tự chứng minh nhân quả. |
| **Thử nghiệm kiểm soát phù hợp** | Có thể tăng khả năng ước lượng tác động của một thay đổi. | Cần thiết kế, độ tin cậy, điều kiện đạo đức/an toàn và nguồn lực. |
| **Bằng chứng trách nhiệm/quyền** | Kiểm tra ai quyết định và điều kiện thực thi. | Một sơ đồ vai trò không chứng minh quyền đã được trao trên thực tế. |

### 10.1. Tránh “dùng biểu đồ để kết thúc tranh luận”

Ví dụ, dashboard cho thấy số deployment tăng sau khi áp dụng CI/CD. Điều này có thể chứng minh **năng lực giao thay đổi** tốt hơn. Nhưng chưa chắc người dùng nhận giá trị hơn, và càng không tự chứng minh người phản đối đã sai về tải công việc.

Đội nên đặt cạnh nhau **outcome, chất lượng, năng lực, chi phí và trải nghiệm con người**.

### 10.2. Không đòi bằng chứng định lượng cho mọi vấn đề đạo đức

Nếu một nhân viên phản ánh có cuộc họp bắt buộc ngoài giờ hoặc áp lực công khai dữ liệu cá nhân, không nên yêu cầu họ chứng minh bằng một bộ dữ liệu lớn rồi mới xem xét. Những vấn đề an toàn, quyền lợi và quy định cần được đánh giá **theo nghĩa vụ và thẩm quyền phù hợp**.

## 11. Đặt baseline trước khi tuyên bố chuyển đổi thành công

Nếu không biết tình trạng trước thay đổi, tổ chức dễ đánh giá bằng **số khóa đào tạo, số nhóm đổi tên hay số nghi thức đã triển khai**.

### 11.1. Baseline của hệ thống làm việc

Có thể xem:

- **Flow:** WIP, throughput, phân phối cycle time, work item age và blocked time.
- **Chất lượng:** lỗi hồi quy, hạng mục không đạt DoD, tác động sự cố, kết quả kiểm thử.
- **Giá trị:** thời gian tới phản hồi người dùng, tỷ lệ hoàn thành tác vụ, outcome sản phẩm.
- **Năng lực thay đổi:** thời gian tích hợp, CI, triển khai và phục hồi.
- **Điều kiện con người:** tải họp, thời gian ngoài giờ, khả năng báo blocker, phân phối công việc.
- **Quản trị:** thời gian chờ quyết định, chi phí/forecast và ranh giới thẩm quyền.

Chọn **một số chỉ số gắn với lo ngại quan trọng**, không cần đo mọi thứ trước khi thử.

### 11.2. Định nghĩa nhất quán

Ví dụ “cycle time giảm” chỉ có ý nghĩa khi:

1. Mốc bắt đầu và kết thúc được thống nhất.
2. Đơn vị thời gian rõ: ngày lịch hay ngày làm việc.
3. Cùng loại hạng mục hoặc phân khúc được so sánh.
4. Các trường hợp bị loại trừ có lý do.
5. Nguồn dữ liệu không thay đổi âm thầm giữa hai kỳ.

Nếu một đội đổi chính sách Done hoặc chia story thành các task nhỏ hơn, throughput có thể tăng **mà không phản ánh cải thiện tương ứng của dòng giá trị**.

### 11.3. Đánh giá tác dụng phụ cùng lúc

Một thay đổi làm cycle time giảm nhưng nhân viên phải trực ngoài giờ và lỗi dữ liệu tăng **không phải thành công bền vững**. Hãy đặt guardrails trước thử nghiệm, không bổ sung chỉ khi đã xuất hiện kết quả xấu.

## 12. Thử nghiệm nhỏ, có quyền dừng và điều chỉnh

Không cần biến cả tổ chức thành nơi thử nghiệm một mô hình chưa rõ phù hợp. Có thể bắt đầu với một nhóm có điều kiện hợp lý, trên một loại công việc cụ thể.

### 12.1. Cấu trúc một thí nghiệm “safe-to-try”

~~~text
THÍ NGHIỆM CHUYỂN ĐỔI — KHUNG MINH HỌA

Vấn đề:
  PBI thường chờ phản hồi PR nhiều ngày và dồn tích hợp cuối Sprint.

Quan ngại cần bảo vệ:
  Review sâu và kiểm tra phân quyền không được rút gọn để lấy tốc độ.

Giả thuyết:
  PR nhỏ, người review được chỉ định rõ và tích hợp sớm
  sẽ giảm chờ mà vẫn giữ chất lượng.

Phạm vi:
  Một luồng sản phẩm có cơ chế kiểm soát hiện tại đáp ứng tiêu chuẩn.

Thay đổi được phép:
  Thỏa thuận review, giới hạn WIP, bộ test hợp đồng.

Ràng buộc:
  Không bỏ kiểm tra bắt buộc; không yêu cầu làm ngoài giờ.

Baseline:
  Định nghĩa time-to-first-meaningful-review và mẫu PR trước thử.

Primary process outcome:
  Thời gian chờ review, tuổi PR đang chờ.

Guardrails:
  Lỗi hồi quy, thời gian làm lại, tải người review, DoD.

Thời hạn:
  Bắt đầu thử, kết thúc quan sát và mốc quyết định được ghi rõ.

Owner / decision maker:
  Người theo dõi thử nghiệm và người có quyền thay đổi chính sách.

Quyết định sau thử:
  Duy trì, sửa, thu thêm dữ liệu hoặc dừng/khôi phục cách trước.
~~~

### 12.2. Safe-to-try không có nghĩa bất kỳ rủi ro nào cũng chấp nhận

Một thí nghiệm trong sản phẩm có dữ liệu nhạy cảm **không được** bỏ bảo vệ quyền riêng tư để “xem chuyện gì xảy ra”. Cách thử an toàn có thể dùng:

- Dữ liệu tổng hợp hoặc giả lập phù hợp.
- Môi trường thử được cô lập.
- Lát Increment nhỏ đã đáp ứng tiêu chuẩn chất lượng.
- Phạm vi mở có kiểm soát và cơ chế quan sát/khôi phục đã kiểm chứng.
- Đường phê duyệt cho ràng buộc bắt buộc.

**Rủi ro không đảo ngược hoặc thiệt hại cao** cần kiểm soát mạnh hơn, không thể xử lý chỉ bằng lời hứa “có thể rollback”.

### 12.3. Nêu rõ khả năng dừng trước khi thử

Ví dụ: nếu chính sách review mới khiến lỗi phân quyền chưa được xem xét, hoặc tải ngoài giờ tăng vượt mức chấp nhận, nhóm có quyền **dừng phần thử nghiệm đó** và khôi phục điều kiện an toàn. Điều kiện dừng khiến cuộc đối thoại có sức nặng hơn vì phản biện được đưa vào cơ chế quyết định.

## 13. Không sử dụng kết quả thí điểm để “đánh bại” người phản đối

Sau thử nghiệm, mục tiêu không phải chứng minh người A sai hoặc người B đúng. Kết quả cần được thảo luận cùng những người bị ảnh hưởng:

1. Thay đổi nào đã thực sự được áp dụng?
2. Những người tham gia có làm theo không? Nếu không, vì sao?
3. Chỉ số thay đổi thế nào theo định nghĩa và khoảng đo đã chốt?
4. Độ không chắc chắn và biến bối cảnh là gì?
5. Guardrails có xấu đi không?
6. Điều người phản đối dự đoán có xuất hiện không?
7. Tiếp tục, sửa, dừng hoặc thử giả thuyết khác?

### 13.1. Trường hợp kết quả không như kỳ vọng

Giả sử sau khi giảm WIP, cycle time chưa giảm vì hàng chờ thực nằm ở người duyệt cấu hình production. Dữ liệu cho thấy phản biện “WIP limit không giải quyết phụ thuộc phê duyệt” **đúng trong phạm vi này**.

Đội nên chuyển hướng cải tiến tới quyền duyệt và đường xử lý cấu hình, thay vì yêu cầu mọi người giữ WIP limit như một biểu tượng tuân thủ.

### 13.2. Có bằng chứng tốt vẫn cần xem khả năng mở rộng

Một đội nhỏ có quan hệ tốt có thể thành công với cách phối hợp nhất định, nhưng đội khác có yêu cầu an toàn, cấu trúc khách hàng hoặc quyền khác. **Không sao chép nguyên thí nghiệm sang toàn tổ chức chỉ vì một dashboard xanh.**

### 13.3. Nhận công khai đóng góp của phản biện

Nếu quan ngại về test hoặc phân quyền giúp tránh sự cố, hãy ghi nhận rằng phản biện đó đã cải thiện giải pháp. Đây là hành động củng cố niềm tin thực tế, không phải thủ thuật khen ngợi để lấy thiện cảm.

## 14. Chỉ số chuyển đổi: phân biệt thực hành được dùng và giá trị được tạo

Một chương trình thay đổi có thể có dashboard, nhưng nên phân biệt các tầng:

| Tầng | Chỉ số minh họa | Điều không chứng minh |
|---|---|---|
| **Hoạt động** | Số buổi đào tạo, coaching, workshop. | Người học đã thay đổi cách quyết định hay hành vi. |
| **Đầu ra triển khai** | Số nhóm có working agreement, backlog, DoD hoặc board minh bạch. | Các artifact đó được sử dụng hiệu quả. |
| **Adoption thực hành** | Các PBI thật được chia lát, review/integration được thực hiện theo thỏa thuận. | Outcome sản phẩm đã tăng. |
| **Flow outcome** | Cycle time, blocked time, tuổi hạng mục, tỷ lệ làm lại. | Người dùng nhận đúng giá trị. |
| **Quality outcome** | Lỗi thoát, khả năng phát hiện, độ tin cậy Increment. | Không còn rủi ro hoặc lỗi chưa được phát hiện. |
| **Product outcome** | Tỷ lệ học viên hoàn tất tác vụ hoặc quay lại học có ý nghĩa. | Thay đổi Agile là nguyên nhân duy nhất. |
| **Con người/guardrail** | Tải họp, công việc ngoài giờ, cảm nhận được phép nêu vấn đề. | Chỉ số khảo sát tự nguyện đo đầy đủ mọi trải nghiệm. |
| **Impact** | Khả năng giao giá trị bền vững, trải nghiệm sản phẩm tốt hơn theo thời gian. | Một giai đoạn thí điểm ngắn đủ chứng minh mọi tác động dài hạn. |

### 14.1. Không dùng “maturity score” làm bằng chứng duy nhất

Một tổ chức có thể tự chấm điểm trưởng thành Agile theo bảng, nhưng nếu điểm tăng nhờ có thêm nghi thức trong khi thời gian chờ quyết định và lỗi production không đổi, **điểm đó chỉ phản ánh mức tuân thủ mô hình**, không chứng minh tác động.

### 14.2. Không xếp hạng con người qua metric flow

Story points, commits, số ticket Done hay thời gian online **không phải thước đo năng suất cá nhân hợp lệ một cách tự động**. Khi ép chỉ tiêu, người tham gia có thể thay cách chia ticket hoặc che blocker. Cần xem **hệ thống làm việc và outcome**, không tạo cuộc thi giữa cá nhân hoặc giữa những đội có bối cảnh khác nhau.

### 14.3. Chọn một vài câu hỏi quan trọng

Nếu phản đối chủ yếu là “chuyển đổi sẽ làm tăng lỗi”, chỉ số chính phải liên quan tới **chất lượng và rủi ro**. Nếu phản đối là “thêm họp gây quá tải”, cần đo thời gian phối hợp và phản hồi người tham gia. Đừng công bố cùng một bộ 20 KPI cho mọi lo ngại rồi không dùng số liệu để quyết định.

## 15. Trách nhiệm của lãnh đạo: thay đổi điều kiện, không chỉ thay lời nói

Lãnh đạo có thể nói “chúng tôi trao quyền tự quản”, nhưng nếu vẫn yêu cầu phê duyệt mọi thay đổi nhỏ và hỏi “ai chịu lỗi” sau mỗi thử nghiệm, nhóm sẽ tin vào **hành vi thực tế** hơn tuyên bố.

### 15.1. Các điều lãnh đạo cần làm rõ

- **Mục đích thay đổi:** vấn đề tổ chức muốn cải thiện và vì sao quan trọng.
- **Quyền quyết định:** cái gì được ủy quyền, ranh giới nào còn bắt buộc.
- **Nguồn lực:** thời gian học kỹ năng, CI, kiểm thử, công cụ và năng lực hỗ trợ.
- **Đánh giá:** chỉ số dùng để học, dự báo, chịu trách nhiệm tài chính hay đánh giá nhân sự?
- **Điều được phép phản biện:** ai có thể chất vấn quyết định và kênh phản hồi?
- **Rủi ro:** những kiểm soát nào không thể bỏ để đạt tốc độ.
- **Khi chưa thành công:** cách thử lại, đổi hướng, dừng và báo cáo trung thực.

### 15.2. Quyền tự quản và trách nhiệm giải trình có thể cùng tồn tại

Developers có thể tự quyết định cách thực hiện trong giới hạn mục tiêu và chuẩn chất lượng, trong khi tổ chức vẫn yêu cầu báo cáo kinh phí, tuân thủ bảo mật và giải trình sự cố. **Không cần lựa chọn nhị phân giữa tự quản hoàn toàn vô kiểm soát và quản lý vi mô mọi bước.**

### 15.3. Đừng biến “sponsor” thành người ủng hộ bằng lời

Người bảo trợ chuyển đổi cần gỡ blocker thật:

- Thời gian chờ phê duyệt giữa phòng ban.
- Chỉ tiêu thưởng/phạt tạo hành vi tối ưu sai.
- Thiếu môi trường thử hoặc quyền truy cập.
- Cam kết tính năng quá mức năng lực đội.
- Áp lực bỏ DoD để đúng ngày.

Nếu những cản trở này không thay đổi, việc yêu cầu nhân viên có “Agile mindset” hơn khó mang lại kết quả.

## 16. Scrum: giải thích accountability mà không xóa trách nhiệm hiện có

Một nguồn kháng cự là lời giới thiệu không chính xác: “Scrum loại bỏ quản lý”, “Scrum Master kiểm soát mọi người” hoặc “Product Owner tự quyết tất cả”.

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog.
- **Developers** chịu trách nhiệm tạo kế hoạch thực hiện Sprint và những Increment dùng được theo Definition of Done.
- **Scrum Master** chịu trách nhiệm về hiệu quả của Scrum Team và giúp tổ chức/team áp dụng Scrum tốt hơn.
- **Scrum Team** cùng chịu trách nhiệm tạo Increment có giá trị, hữu ích trong mỗi Sprint.

Những accountability này **không tự quyết định** toàn bộ cơ cấu nhân sự, tiền lương, quyền phê duyệt pháp lý hay cấu trúc quản lý của doanh nghiệp.

### 16.1. Đối thoại với người quản lý dự án

Lo ngại:

> “Tôi từng chịu trách nhiệm lịch và phụ thuộc. Khi Scrum Team tự quản, ai kiểm soát kế hoạch liên đội?”

Các câu hỏi hữu ích:

- Phụ thuộc liên đội nào hiện không có owner?
- Quyền dự báo và phân bổ nguồn lực sẽ thuộc thẩm quyền nào?
- Phần phối hợp nào có thể làm minh bạch qua Product Goal, backlog, Sprint Goal và flow?
- Các hoạt động quản trị rủi ro và báo cáo nào vẫn phải tồn tại?
- Năng lực quản lý nào có thể chuyển sang gỡ trở ngại, phát triển đội hoặc phối hợp danh mục?

Không nên hứa rằng vai trò nghề nghiệp của người đó **chắc chắn không bị tác động** nếu quyết định tổ chức chưa rõ. Thông tin về thay đổi quyền lợi phải do người có thẩm quyền truyền đạt minh bạch theo quy định.

### 16.2. Đối thoại với Product Owner

Lo ngại:

> “Tôi không thể một mình biết mọi nhu cầu khách hàng và các điều kiện kỹ thuật.”

Phản hồi phù hợp:

> “Product Owner chịu trách nhiệm hiệu quả Product Backlog, nhưng không có nghĩa phải tự nghiên cứu, viết mọi câu chuyện hoặc quyết định kỹ thuật một mình. Chúng ta cần cơ chế nhận dữ liệu từ người dùng, Developers và stakeholders, cùng ranh giới quyết định rõ.”

Nếu Product Owner thiếu quyền thay đổi thứ tự backlog hoặc bị năm cấp quản lý can thiệp, cần xử lý **thiết kế quyền và thẩm quyền**, không chỉ dạy họ “prioritize mạnh mẽ hơn”.

### 16.3. Đối thoại với Developers

Lo ngại:

> “Daily Scrum là buổi báo cáo cho người quản lý và chúng tôi bị giao thêm việc giữa Sprint.”

Cần làm rõ Daily Scrum là sự kiện để **Developers kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog**; không phải buổi status report áp đặt. Nếu mục tiêu thay đổi liên tục vì yêu cầu ngoài, phải xử lý **quy tắc ưu tiên và Sprint Goal**, không chỉ rút thời lượng họp.

## 17. Kanban: khi “đổi cách làm” không cần thêm Sprint

Một đội vận hành đang xử lý sự cố, yêu cầu hỗ trợ và thay đổi không định trước có thể lo Scrum timebox làm gián đoạn dịch vụ.

Đối thoại có thể bắt đầu bằng:

> “Chúng ta cần thấy công việc, giới hạn WIP và cải thiện thời gian xử lý. Với đặc điểm có nhiều việc khẩn chen vào, chính sách Kanban có phù hợp hơn cho luồng này không?”

### 17.1. Những câu hỏi khi thử Kanban

- Loại việc nào xuất hiện và có đặc điểm thời gian khác nhau?
- **WIP** thực tế đang ở mức nào, bao nhiêu việc bị bỏ dở?
- Có chính sách xử lý sự cố thật sự khẩn khác công việc thường không?
- **Cycle time, work item age, throughput** hiện tại được định nghĩa ra sao?
- Có thể thử giới hạn WIP mà không làm trì hoãn nghĩa vụ an toàn không?
- Ai có quyền thay đổi thứ tự kéo việc và gỡ blocker?

### 17.2. Không đồng nhất Kanban với “không có kế hoạch”

Kanban không có nghĩa công việc tới đâu làm tới đó mà không có ưu tiên. Một đội cần **chính sách rõ, tín hiệu flow và phản hồi**. Nếu người quản lý lo mất dự báo, có thể thử dùng phân phối cycle time và SLE phù hợp để xây dự báo minh bạch hơn.

### 17.3. Không sử dụng WIP limit như luật trừng phạt

Nếu WIP đã đạt giới hạn, nhóm nên xem hỗ trợ hoàn thành, xử lý blocker và ngoại lệ rủi ro phù hợp. Việc dùng WIP limit để từ chối xử lý lỗi bảo mật khẩn là **hiểu sai mục đích quản lý flow**.

## 18. XP và thực hành kỹ thuật: khi nỗi lo đến từ chất lượng mã

Một số kỹ sư phản đối thay đổi vì đã trải qua những dự án “Agile” mà backlog thay đổi liên tục, nhưng **mã nguồn không được refactor, không có kiểm thử đáng tin và deploy vẫn nguy hiểm**.

Đây là vấn đề kỹ thuật thực sự. Agile không chỉ là tổ chức sự kiện; muốn thay đổi hướng sản phẩm thường xuyên mà không gây hỏng hệ thống, cần năng lực kỹ thuật tương ứng.

### 18.1. Đối thoại theo kiểu “thử và đo”

Ý kiến:

> “Viết test trước làm chậm tôi. TDD không phù hợp dự án này.”

Thay vì yêu cầu toàn đội lập tức dùng TDD cho mọi đoạn mã, hãy hỏi:

- Loại thay đổi nào thường gây lỗi hồi quy?
- Thời gian đang mất cho debug và sửa lại là bao nhiêu?
- Có loại mã nào khó test do phụ thuộc hoặc thiết kế cần cải tiến?
- Nếu thử TDD trong một phần nghiệp vụ có quy tắc rõ, sẽ đo điều gì?
- Có tiêu chí chất lượng hiện tại nào phải giữ nguyên?

Một thí nghiệm có thể:

1. Chọn một tập quy tắc tính số chỗ đăng ký có ví dụ rõ.
2. Pair programming hoặc TDD trên lát nhỏ trong phạm vi được phép.
3. Ghi thời gian thực hiện, lỗi phát hiện sớm và số lần làm lại.
4. So sánh với baseline phù hợp, ghi các khác biệt về độ khó.
5. Xem tác dụng phụ như độ tin cậy bộ test, tải CI và năng lực học.

**Một thí nghiệm vài ngày không chứng minh XP luôn tốt hơn hoặc tệ hơn mọi phương án khác.** Nó giúp tìm cách thực hành thích hợp với rủi ro của đội.

### 18.2. Phản đối pair programming không nhất thiết do thiếu hợp tác

Người tham gia có thể lo:

- Thiếu thời gian tập trung hoặc sự riêng tư.
- Không có giờ chồng lấn do múi giờ.
- Chênh lệch kỹ năng dẫn tới người này bị kéo theo.
- Cảm giác bị giám sát khi người khác nhìn từng thao tác.
- Nhiều ngữ cảnh làm việc không phù hợp ghép cặp liên tục.

Có thể thử **pair có mục tiêu** cho vùng rủi ro cao, thời lượng ngắn và quyền dừng phù hợp, thay vì coi số giờ pair là thước đo văn hóa Agile.

### 18.3. Đảm bảo kỹ thuật là một điều kiện của chuyển đổi

Nếu tổ chức muốn mỗi Sprint có Increment dùng được nhưng chưa có CI, môi trường thử, khả năng tích hợp và thiết kế dữ liệu phù hợp, cần **đầu tư vào năng lực kỹ thuật**. Chỉ yêu cầu “Sprint phải nhanh hơn” không giải quyết khoảng trống.

## 19. Đối thoại với kiểm thử, bảo mật và vận hành: giữ chất lượng không thương lượng

Một chuyển đổi thất bại thường đặt kiểm thử và vận hành vào tình thế “người gác cổng gây chậm”. Nhưng những vai trò này có thể thấy rủi ro mà người khác chưa thấy.

### 19.1. Từ “QA chặn release” thành câu hỏi về dòng chất lượng

Lo ngại:

> “Nếu Developers báo Done trước khi QA kiểm thử, tôi sẽ phải nhận lỗi sau phát hành.”

Đối thoại:

1. Cùng xác định **Definition of Done** áp dụng cho Increment.
2. Làm rõ hạng mục có thể được gọi Done khi nào; phân biệt Done và phát hành.
3. Đưa người có góc nhìn kiểm thử vào trao đổi user story và acceptance criteria sớm hơn.
4. Xây những kiểm tra tự động hoặc hợp đồng phù hợp rủi ro.
5. Phân tích thời gian chờ do môi trường, dữ liệu và phụ thuộc trước khi quy lỗi cho một vai trò.
6. Chọn phép đo lỗi thoát, lỗi tích hợp, thời gian kiểm chứng và tải của người kiểm thử.

**Không giảm tiêu chuẩn chất lượng chỉ vì muốn có biểu đồ velocity đẹp hơn.** Nếu phần việc chưa đạt DoD, cần minh bạch và điều chỉnh phạm vi.

### 19.2. Với bảo mật: phản hồi sớm nhưng không bỏ kiểm soát

Nếu người phụ trách bảo mật hỏi “Ai kiểm tra phân quyền khi mỗi tuần đều release?”, câu trả lời không thể chỉ là “Agile tin tưởng nhóm”.

Cần có:

- Phân loại rủi ro và tiêu chuẩn bảo mật áp dụng.
- Trách nhiệm phân quyền, xử lý dữ liệu và quản lý secrets rõ ràng.
- Kiểm tra trong CI, threat modeling hoặc review chuyên môn theo bối cảnh.
- Quy trình ngoại lệ hợp lệ, không tự bỏ gate bắt buộc.
- Quan sát và ứng phó khi phát hiện lỗ hổng.

Một phần rủi ro có thể được kiểm tra sớm và tự động hóa; phần khác vẫn cần **người có thẩm quyền đánh giá**. Mục tiêu là **kiểm soát hiệu quả hơn**, không tuyên bố mọi gate đều vô ích.

### 19.3. Với vận hành: release nhiều không tự chứng minh vận hành tốt

Người trực có thể lo tần suất thay đổi tăng khiến sự cố và tải trực tăng. Một thí điểm cần xem cả:

- Tần suất và cách triển khai thay đổi.
- Tỷ lệ lỗi gắn với thay đổi theo định nghĩa đã thống nhất.
- Khả năng phát hiện, giảm tác động và khôi phục.
- Tính đúng dữ liệu và trải nghiệm người dùng.
- Chất lượng runbook, cảnh báo và khả năng rollback/roll-forward khi hợp lệ.
- Tải ngoài giờ và số cảnh báo không thể hành động.

Nếu deployment frequency tăng nhưng sự cố gây mất dữ liệu tăng, **cần sửa chính sách phát hành và kiểm chứng**, không coi chỉ số deploy là thắng lợi văn hóa.

## 20. Đối thoại với quản lý, tài chính và người phê duyệt

Những nhóm này thường cần **khả năng dự báo, kiểm soát vốn và trách nhiệm giải trình**, không nhất thiết phản đối việc học hỏi.

### 20.1. Câu hỏi “Agile có nghĩa không thể cam kết deadline?”

Một câu trả lời có trách nhiệm:

> “Chúng ta vẫn có thể cam kết những ràng buộc thực như thời hạn hợp đồng, nghĩa vụ pháp lý hay cửa sổ ra mắt; nhưng phải minh bạch về mức bất định của phạm vi, chất lượng và năng lực. Khi xuất hiện phản hồi mới, cần đưa ra các lựa chọn giảm phạm vi, đổi giải pháp hoặc điều chỉnh nguồn lực theo quyền quyết định đã duyệt.”

Nếu yêu cầu cứng về **ngày, ngân sách, toàn bộ phạm vi và chất lượng** trong điều kiện rủi ro lớn, người làm cần được phép nêu xung đột thay vì che giấu.

### 20.2. Trần ngân sách và quyền đổi backlog

Một thử nghiệm tài trợ theo giai đoạn có thể quy định:

- Trần kinh phí và phạm vi quyết định theo kỳ.
- Giả thuyết giá trị và dữ liệu cần thu.
- Nghĩa vụ chất lượng và tuân thủ bắt buộc.
- Các checkpoint tài chính theo mức chi/rủi ro.
- Quyền thay đổi thứ tự backlog trong trần đã duyệt.
- Điều kiện tăng, giảm hoặc dừng đầu tư.

**Không phải mọi tổ chức đều có thể đổi cơ chế tài chính ngay**, và việc thay đổi hợp đồng cần đúng thẩm quyền. Nhưng có thể giảm vòng chờ phê duyệt trong phạm vi được phép và xem dữ liệu thực tế của thí điểm.

### 20.3. Quản lý cần điều gì từ bằng chứng?

| Nhu cầu quản trị | Bằng chứng có ích | Điều dễ nhầm |
|---|---|---|
| Dự báo ngày hoàn thành | Phân phối cycle time, throughput và độ bất định theo loại việc. | Một velocity được áp như cam kết chính xác tuyệt đối. |
| Kiểm soát kinh phí | Trần, actual, commitment, forecast và quyết định thay đổi. | Mọi khoản chưa chi đều là tiền được tự do sử dụng. |
| Quản lý rủi ro | Trạng thái kiểm soát, dữ liệu lỗi, phụ thuộc và kế hoạch ứng phó. | Không có bug được báo nghĩa là không có rủi ro. |
| Đánh giá giá trị | Product Goal, outcome/cohort và phản hồi người dùng. | Số tính năng hoàn thành là giá trị đã được chứng minh. |
| Năng lực tổ chức | Thời gian chờ quyết định, tải công việc và cải tiến thực hành. | Số người có chứng chỉ Agile là bằng chứng đủ. |

### 20.4. Hỗ trợ người quản lý chuyển vai trò thực tế

Một người quản lý từng trực tiếp giao từng task có thể đóng góp bằng:

- Bảo đảm người làm có năng lực và điều kiện tập trung.
- Gỡ phụ thuộc giữa đội/sản phẩm.
- Làm rõ quyền quyết định, hợp đồng và nghĩa vụ.
- Hỗ trợ phát triển kỹ năng và giải quyết xung đột.
- Giảm chính sách khuyến khích tối ưu sai.
- Cung cấp dữ liệu về rủi ro danh mục và năng lực.

**Không tự hứa bảo toàn chức danh, công việc hay đãi ngộ** nếu tổ chức chưa có quyết định rõ. Đó là chủ đề cần người có thẩm quyền trả lời chính thức, không phải điều một Agile coach tự bảo đảm.

## 21. Nhóm phân tán và đa văn hóa: đừng coi ít phát biểu là ít lo ngại

Trong một nhóm ở Việt Nam, châu Âu và Hoa Kỳ, những người không dự được họp vì múi giờ có thể bị xem là ít hợp tác. Những người không quen tranh luận trực tiếp có thể phản biện qua tài liệu chứ không qua cuộc gọi.

### 21.1. Thiết kế cơ hội phản hồi công bằng

- Gửi mục tiêu thay đổi và câu hỏi trước.
- Cho phép góp ý bất đồng bộ ở artifact chung.
- Có kênh trao đổi một–một khi nội dung nhạy cảm.
- Dùng ví dụ và số liệu rõ thay cho những câu chỉ người trong cuộc hiểu.
- Xoay thời điểm họp toàn nhóm nếu cần, không mặc định một vùng chịu mọi giờ bất tiện.
- Tóm tắt quyết định, lý do, vấn đề chưa giải quyết và người phụ trách.

### 21.2. Không để “async” thành con đường né trách nhiệm

Một câu hỏi về quyền, chất lượng hoặc deadline có thể nằm trên chat hàng ngày mà không ai trả lời vì **không có next actor**. Cần có người nhận, mốc phản hồi và đường quyết định phù hợp, không chỉ một kênh nhắn tin mới.

### 21.3. Đối thoại không đòi mọi người đồng ý công khai

Nếu người tham gia lo về tải ngoài giờ, họ có thể không muốn nói điều đó trước quản lý trực tiếp. Tổ chức có thể dùng phương thức thu phản hồi bảo vệ riêng tư; nhưng **không hứa “ẩn danh tuyệt đối” nếu quy mô nhỏ hoặc hệ thống không bảo đảm điều đó**.

## 22. Khi đối thoại chuyển thành xung đột

Không phải mọi bất đồng có thể giải quyết bằng một cuộc họp thân thiện. Có trường hợp thiếu thẩm quyền, lợi ích mâu thuẫn, hành vi không phù hợp hoặc nghĩa vụ bắt buộc.

### 22.1. Phân biệt tranh luận về phương pháp với xung đột có hệ quả

| Tình huống | Hướng xử lý |
|---|---|
| Hai nhóm bất đồng Scrum hay Kanban phù hợp hơn. | Làm rõ loại công việc, mục tiêu flow, thử có giới hạn nếu đủ quyền. |
| Người kiểm thử từ chối bỏ bước bảo mật bắt buộc. | Tôn trọng kiểm soát, tham vấn người có thẩm quyền; không gọi đó là “kháng cự”. |
| Người quản lý và đội mâu thuẫn về quyền ưu tiên. | Ghi ma trận quyết định và đưa lên cấp có quyền giải quyết. |
| Người tham gia có thái độ công kích hoặc xúc phạm. | Xử lý hành vi cụ thể theo chuẩn làm việc công bằng; không dùng tranh luận kỹ thuật làm cớ cho hành vi gây hại. |
| Có phản ánh về quyền lợi lao động, phân biệt đối xử hoặc trả đũa. | Dùng quy trình nhân sự/pháp lý hoặc kênh báo cáo phù hợp, bảo vệ người báo và bằng chứng. |
| Chuyển đổi buộc nhân viên liên tục làm ngoài giờ không được thỏa thuận. | Xem lại nguồn lực, lịch phối hợp và nghĩa vụ áp dụng; không ép đồng ý bằng KPI. |

### 22.2. Nguyên tắc khi có bất đồng khó

1. **Cụ thể hóa hành vi hoặc quyết định gây tranh chấp.**
2. **Không suy đoán động cơ cá nhân** hoặc gắn nhãn “toxic”, “chống đổi mới” nếu chưa có căn cứ.
3. **Đưa bằng chứng và hậu quả** thay vì tranh luận danh tính của phe.
4. **Tách quyết định được ủy quyền và nghĩa vụ bắt buộc** khỏi mong muốn cá nhân.
5. **Ghi quyết định, người chịu trách nhiệm và quyền khiếu nại/xem lại** theo chính sách.
6. **Không dùng thí nghiệm để né xử lý một vấn đề quyền hoặc an toàn cần giải quyết ngay.**

### 22.3. Đến lúc nào không nên cố “thuyết phục” nữa?

Nếu thay đổi có nguy cơ vi phạm luật, hợp đồng hoặc nguyên tắc bảo vệ người dùng, phải **ngừng hoặc điều chỉnh phần liên quan** và tham vấn đúng thẩm quyền. Nếu một người chưa đồng ý vì thiếu quyết định về quyền lợi, cần trả lời trung thực phần chưa được quyết định, không tạo cảm giác lựa chọn của họ đã được tôn trọng trong khi kết quả bị khóa.

## 23. Ranh giới đạo đức: đối thoại không phải công cụ thao túng

Một chiến dịch chuyển đổi có thể trở nên phản tác dụng nếu dùng kỹ thuật “làm người phản đối đổi ý” mà không cho họ quyền đưa bằng chứng ngược.

### 23.1. Những điều nên tránh

- Gọi một ý kiến chuyên môn là “thiếu tư duy phát triển” để không phải phản hồi nội dung.
- Chỉ mời nhóm ủng hộ tới các buổi tạo đồng thuận, rồi báo tất cả đã đồng ý.
- Chọn số liệu sau khi biết kết quả để chứng minh cách mới luôn đúng.
- Dùng khảo sát “ẩn danh” nhưng tìm danh tính người chấm điểm thấp.
- Đặt người tham gia vào tình huống phải công khai thông tin sức khỏe, hoàn cảnh cá nhân hoặc dự định nghề nghiệp.
- Hứa các chính sách việc làm không thay đổi khi không có quyền bảo đảm.
- Dùng phản hồi cá nhân trong Retro làm căn cứ thưởng/phạt mà không có chính sách và thông báo minh bạch.
- Dùng thử nghiệm trên dữ liệu thật với rủi ro người dùng không chấp nhận được.

### 23.2. Quyền phản biện và trách nhiệm quyết định

Không phải mọi ý kiến phản đối phải được thực hiện, nhưng **mọi phản biện có tác động quan trọng cần có đường được xem xét và phản hồi**. Nếu lãnh đạo vẫn quyết định một phương án gây bất đồng, nên giải thích:

- Mục tiêu và ràng buộc khiến phương án được chọn.
- Bằng chứng nào được cân nhắc.
- Những rủi ro/ý kiến nào chưa giải quyết hoàn toàn.
- Guardrails, người theo dõi và mốc xem lại.
- Kênh tiếp tục phản ánh khi hậu quả không như dự đoán.

### 23.3. Tránh biến “đồng thuận” thành chỉ tiêu

Đo “100% nhân viên ủng hộ Agile” dễ thúc đẩy sự đồng ý xã giao. Một tín hiệu mạnh hơn là **mọi người có thể nêu rủi ro, được trả lời và thấy cách làm được điều chỉnh khi bằng chứng yêu cầu**.

## 24. Case study: chuyển đổi cách làm của đội nền tảng học trực tuyến

**Toàn bộ tổ chức, nhân sự, ngày và số liệu sau đây là giả định phục vụ học tập**, không mô tả một công ty hay kết quả nghiên cứu thực tế.

### 24.1. Bối cảnh trước thay đổi

Một đội phát triển nền tảng học lập trình nhận yêu cầu tính năng từ nhiều phòng ban. Công việc được lập kế hoạch theo gói lớn; frontend, backend và kiểm thử thường bàn giao tuần tự. Người quản lý lo lịch thay đổi khó kiểm soát, Developers thiếu thời gian cải tiến CI, người kiểm thử lo chất lượng giảm.

Tổ chức dự tính áp dụng Scrum trong đội phát triển sản phẩm, đồng thời dùng Kanban cho luồng hỗ trợ thường xuyên. Tuy nhiên, thí điểm chưa có quyền thay đổi cách phê duyệt hay phân bổ năng lực kiểm thử.

### 24.2. Bốn nhóm ý kiến và nhu cầu bên dưới

| Ý kiến nguyên văn minh họa | Điều cần làm rõ | Điều kiện an toàn/phù hợp |
|---|---|---|
| “Scrum chỉ thêm họp.” | Những cuộc họp nào hiện không tạo quyết định? | Bỏ báo cáo trùng lặp, giữ nhịp kiểm tra có ích. |
| “QA sẽ bị ép.” | DoD hiện có gì, kiểm thử thường tới cuối vì sao? | Không bỏ quality gates; có môi trường và kiểm thử sớm. |
| “Không thể hứa deadline với khách hàng.” | Deadline nào là nghĩa vụ thật, phạm vi nào có thể thích ứng? | Forecast theo bằng chứng, thẩm quyền đổi scope và escalation. |
| “Tự quản khiến tôi mất quyền.” | Quyết định nào cần giữ, quyền nào cần ủy quyền? | Ma trận trách nhiệm rõ và hỗ trợ gỡ phụ thuộc. |

Đội tổ chức các cuộc trao đổi nhỏ, bảo đảm cả người ít phát biểu được tham gia. Kết luận ban đầu **không phải “mọi người đã đồng ý với Scrum”**, mà là danh sách rủi ro và các giả thuyết đáng thử.

### 24.3. Baseline trong sáu tuần, giả định

| Tín hiệu | Baseline giả định | Cách hiểu |
|---|---:|---|
| Cycle time trung vị PBI cùng loại | 18 ngày làm việc | Từ bắt đầu thực hiện đến đạt DoD theo quy định hiện tại. |
| Blocked time trung vị | 6 ngày làm việc | Chờ quyết định, review hoặc môi trường thử. |
| PBI có lỗi tích hợp phát hiện gần lúc giao | 9/24 | Bằng chứng về kiểm chứng muộn, không phải lỗi riêng QA. |
| Hạng mục Done nhưng còn thiếu kiểm chứng bắt buộc | 5/24 | Tín hiệu phải làm rõ chính sách Done. |
| Giờ họp phối hợp trung bình | 7 giờ/người/tuần | Cần phân biệt họp có quyết định với báo cáo lặp. |
| Số trường hợp thay đổi scope chưa có quyết định rõ | 8 | Nguy cơ mơ hồ quyền và forecast. |

Con số là ví dụ để học cách **định nghĩa baseline và chọn thí nghiệm**. Hai giai đoạn khác nhau không tự chứng minh nhân quả nếu loại việc, đội hình hoặc môi trường thay đổi.

### 24.4. Thiết kế thử nghiệm cùng người đang lo ngại

Sau đối thoại, nhóm chọn:

1. **Sprint Goal rõ cho một lát giá trị**, thay vì cam kết mọi ticket phải Done.
2. **Refinement bằng ví dụ nghiệp vụ** giữa Product Owner, Developers và người có góc nhìn kiểm thử.
3. **Definition of Done chung** có kiểm tra tích hợp, phân quyền, dữ liệu và khả năng truy cập áp dụng.
4. **Giới hạn WIP và ưu tiên hoàn tất**, không mở thêm nhiều hạng mục khi review/test bị chặn.
5. **CI/contract test** cho luồng đăng ký, hủy và khôi phục tiến độ.
6. **Báo cáo forecast theo khoảng cùng các phụ thuộc**, thay vì hứa một ngày chắc chắn cho mọi giải pháp.
7. **Rút gọn cuộc họp báo cáo trùng**, dùng các sự kiện Scrum đúng mục đích.

Người kiểm thử tham gia định nghĩa các guardrails; người quản lý cùng làm rõ quyền quyết định và forecast; Developers đề xuất cách tích hợp. **Thí điểm không yêu cầu người phản đối từ bỏ tiêu chuẩn họ cần bảo vệ**.

### 24.5. Action card của thí điểm

~~~yaml
experiment_id: "AGILE-CHANGE-07"
problem: "Tích hợp muộn, cycle time dài và trách nhiệm quyết định mơ hồ"
hypothesis: >
  Chia lát giá trị, giảm WIP, kiểm tra sớm và quyền quyết định rõ
  sẽ giúp giao Increment đáng tin hơn mà không tăng tải con người.
scope: "Một đội sản phẩm, một luồng tính năng đăng ký/hủy"
owner: "Người điều phối thay đổi được nhóm và sponsor thống nhất"
executors:
  - "Developers"
  - "Người có góc nhìn kiểm thử"
  - "Product Owner và người nghiệp vụ liên quan"
decision_maker: "Người có thẩm quyền với cách làm và nguồn lực"
baseline_window: "Sáu tuần trước thử, có định nghĩa đo được lưu"
trial_window: "Một khoảng đủ hạng mục và đủ phản hồi, cần xác nhận"
primary_measures:
  - "Cycle time và blocked time theo loại PBI"
  - "Lỗi tích hợp phát hiện muộn"
guardrails:
  - "Không bỏ Definition of Done"
  - "Không tăng lỗi dữ liệu hoặc quyền truy cập"
  - "Không tăng tải làm ngoài giờ hoặc cuộc họp vô ích"
review_decision: "Duy trì, sửa, kéo dài đo hoặc dừng"
~~~

Đây là **mẫu YAML trong nội dung bài học**, không phải metadata thực của bài và không áp dụng trực tiếp vào bất kỳ hệ thống quản trị nào.

### 24.6. Kết quả minh họa sau thí điểm

| Tín hiệu | Trước | Sau |
|---|---:|---:|
| Số PBI đủ điều kiện được quan sát | 24 | 26 |
| Cycle time trung vị (ngày làm việc) | 18 | 12 |
| Blocked time trung vị (ngày làm việc) | 6 | 3,5 |
| PBI có lỗi tích hợp phát hiện muộn | 9/24 | 4/26 |
| Hạng mục đánh dấu Done dù thiếu kiểm chứng bắt buộc | 5/24 | 0/26 |
| Giờ họp phối hợp trung bình (giờ/người/tuần) | 7 | 5,5 |

Phép tính:

~~~text
Cycle time median giảm tuyệt đối = 18 - 12 = 6 ngày làm việc
Mức giảm tương đối = 6 / 18 × 100% ≈ 33,3%

Blocked time median giảm = 6 - 3,5 = 2,5 ngày làm việc
Mức giảm tương đối = 2,5 / 6 × 100% ≈ 41,7%

Lỗi tích hợp phát hiện muộn:
  trước = 9 / 24 = 37,5%
  sau   = 4 / 26 ≈ 15,4%
  giảm khoảng 22,1 điểm phần trăm
~~~

**Các số liệu đều giả định.** Cỡ mẫu còn nhỏ; khó phân biệt tác động của cách làm với việc team được thêm hỗ trợ, quy mô ticket thay đổi, loại tính năng dễ hơn hoặc lỗi ghi nhận chưa đầy đủ.

### 24.7. Vì sao không nên tuyên bố “Scrum giúp tăng năng suất 33,3%”

Con số 33,3% ở trên là **mức giảm tương đối của trung vị cycle time trong hai mẫu giả định**, không phải “năng suất tăng 33,3%”. Những thay đổi đi kèm còn có giới hạn WIP, CI, DoD, làm rõ nghiệp vụ và bỏ họp trùng; không thể gán toàn bộ cho một framework.

Một kết luận có trách nhiệm hơn:

> “Trong phạm vi thí điểm, dòng PBI cho tín hiệu tốt hơn về thời gian chờ và tích hợp, trong khi các guardrails được quan sát chưa xấu đi. Nhóm sẽ kiểm tra thêm về độ ổn định, giá trị người dùng và khả năng áp dụng sang luồng khác trước khi mở rộng.”

### 24.8. Phản biện nào đã cải thiện thí điểm?

- **QA lo bị ép** → team ghi DoD rõ và không đánh dấu Done khi thiếu test.
- **Developers lo thêm họp** → bỏ cuộc họp báo cáo cũ, dành Daily Scrum cho kế hoạch hướng Sprint Goal.
- **Người quản lý lo mất forecast** → báo phân phối cycle time và phụ thuộc rõ hơn.
- **Product Owner lo quá tải** → cùng làm rõ vai trò và hỗ trợ nghiên cứu nhu cầu.

Phản biện không phải chướng ngại cần xóa; nó đã trở thành **đầu vào thiết kế guardrails và cách làm**.

### 24.9. Quyết định sau thí điểm

Tổ chức giữ những thực hành có bằng chứng hữu ích, tiếp tục đầu tư CI và cải thiện quyết định liên đội. Nhưng họ **không bắt luồng hỗ trợ vận hành phải dùng cùng Sprint cadence** nếu dữ liệu cho thấy Kanban phù hợp hơn.

Lựa chọn cách phối hợp được dựa trên **bản chất công việc, rủi ro và kết quả**, không trên mục tiêu “toàn bộ công ty phải giống nhau”.

## 25. Các cuộc đối thoại mẫu trong tình huống khó

Những đoạn hội thoại dưới đây chỉ minh họa **cấu trúc lắng nghe và đồng kiểm chứng**. Người thật có thể phản ứng khác; không nên đọc nguyên văn như một kịch bản thao túng.

### 25.1. “Agile chỉ là chiêu bắt chúng tôi làm nhanh hơn”

**Người phát triển:** “Tôi nghe nói từ Sprint sau phải hoàn thành gấp đôi story. Agile là cách ép deadline mới thôi.”

**Người điều phối:** “Nếu kế hoạch chỉ tăng số story mà không thay điều kiện làm việc, lo ngại của bạn là hợp lý. Bạn đã nhận yêu cầu gấp đôi từ đâu, và nó liên quan cách ước lượng hay khối lượng thực?”

**Người phát triển:** “Bảng mục tiêu mới ghi velocity phải tăng 50%.”

**Người điều phối:** “Chúng ta cần làm rõ ai đặt target và mục đích sử dụng. Velocity không nên là chỉ tiêu năng suất cá nhân. Tôi sẽ đưa việc này tới người có quyền đánh giá thành tích, đồng thời đề nghị xem cycle time, chất lượng và outcome. Trước khi thử nhịp mới, chúng ta sẽ không coi tăng điểm ước lượng là thành công.”

**Điểm cần học:** đối thoại có bước **kiểm tra tính thật của áp lực** và **chuyển vấn đề quyền quyết định tới đúng người**. Không chỉ nói “Agile không phải vậy” rồi bỏ mặc KPI sai.

### 25.2. “Scrum làm mất trách nhiệm của QA”

**Người kiểm thử:** “Nếu cả team cùng chịu trách nhiệm, tôi sợ cuối cùng chẳng ai kiểm tra sâu.”

**Người điều phối:** “Chúng ta cần một DoD có bằng chứng rõ. Những kiểm tra nào hiện chỉ bạn biết hoặc chỉ thực hiện lúc cuối?”

**Người kiểm thử:** “Kiểm tra gửi đăng ký lặp, phân quyền và thông báo khi backend timeout.”

**Người điều phối:** “Chúng ta thử cùng viết ví dụ acceptance criteria và integration tests sớm hơn; bạn vẫn có tiếng nói chuyên môn về rủi ro. Trong hai Sprint, mình xem số lỗi phát hiện muộn, tỷ lệ test đáng tin và tải kiểm thử. Nếu có kiểm soát bị bỏ, ta dừng cách thử đó.”

**Điểm cần học:** **chia sẻ trách nhiệm chất lượng không đồng nghĩa xóa kiến thức chuyên môn**; hành động cần nguồn lực và điều kiện dừng.

### 25.3. “Kanban thiếu cam kết”

**Người quản lý:** “Đội dùng Kanban thì ai biết khi nào xong?”

**Người điều phối:** “Chúng ta có thể định nghĩa lúc việc bắt đầu, Done, loại việc và Service Level Expectation từ dữ liệu. Hiện tại forecast của đội đang lệch ở đâu?”

**Người quản lý:** “Các yêu cầu khẩn thường chen ngang, kế hoạch tháng không giữ được.”

**Người điều phối:** “Vậy thử minh bạch luồng khẩn, WIP, tuổi hạng mục và throughput trong một thời kỳ. Chúng ta xem dự báo có thực tế hơn không, đồng thời giữ trách nhiệm với các mốc cam kết hợp đồng cần báo sớm.”

**Điểm cần học:** không phủ nhận nhu cầu forecast; **đổi phương pháp dự báo và điều tiết dòng việc** theo bối cảnh.

### 25.4. “Tôi sợ mất việc khi đội tự quản”

**Người quản lý:** “Nếu không còn người giao task, vị trí của tôi sẽ ra sao?”

**Người điều phối:** “Đây là câu hỏi về vai trò và quyền lợi thực, không chỉ cách chạy Scrum. Tôi không có thẩm quyền hứa về cơ cấu nhân sự. Chúng ta cần có người lãnh đạo và nhân sự cung cấp thông tin chính thức về điều chưa quyết, mốc cập nhật và cơ hội phát triển phù hợp. Về cách làm, chúng ta có thể cùng xác định các trách nhiệm gỡ phụ thuộc, phát triển năng lực và quản trị rủi ro vẫn rất cần thiết.”

**Điểm cần học:** **không dùng sự đồng cảm để thay thế thông tin nhân sự chính thức**, và không hứa điều vượt thẩm quyền.

### 25.5. “Đội đang bị quá tải bởi các sự kiện Scrum”

**Thành viên phân tán:** “Daily ở 21 giờ của tôi, Review thì sáng sớm. Tôi không thể duy trì như vậy.”

**Người điều phối:** “Chúng ta cần xem lại giờ làm và các sự kiện bắt buộc. Có thể chuẩn bị cập nhật async, dùng giờ chồng lấn cho quyết định, điều chỉnh thời điểm hoặc luân phiên những giờ bất tiện; điều gì phù hợp với quy định và tình trạng thực của đội?”

**Thành viên:** “Nếu bỏ cuộc họp cập nhật cũ và không họp ngoài giờ mỗi ngày thì tôi có thể tham gia tốt hơn.”

**Người điều phối:** “Ta ghi thỏa thuận, thử và xem số giờ ngoài ca, blocked time và chất lượng phối hợp. Không coi việc bạn từ chối họp liên tục ngoài giờ là thiếu cam kết Agile.”

**Điểm cần học:** thiết kế lại **điều kiện tham gia**, không buộc người bị ảnh hưởng tự thích nghi với lịch không bền vững.

## 26. Quy trình xử lý một lo ngại cụ thể từ đầu tới cuối

Giả sử có phát biểu:

> “Sau chuyển đổi, Product Owner đổi ý giữa Sprint và Developers phải làm lại liên tục.”

### Bước 1 — Ghi phát biểu trung tính

> “Trong một số Sprint, ưu tiên thay đổi khi công việc đã bắt đầu, làm phát sinh làm lại. Cần kiểm tra mức độ, nguyên nhân và quyền quyết định.”

Không ghi “Developers không chấp nhận thay đổi” hoặc “PO tùy hứng” khi chưa kiểm chứng.

### Bước 2 — Thu vài tình huống có dữ liệu

Từ một số PBI gần đây, ghi:

- Điều gì đã thay đổi: mục tiêu, tiêu chí hay thứ tự?
- Ai yêu cầu và theo quyền nào?
- Khi nào thay đổi xảy ra?
- Bằng chứng người dùng hoặc rủi ro mới là gì?
- Những phần công việc nào phải làm lại?
- Sprint Goal có còn phù hợp và được bảo vệ không?

### Bước 3 — Đặt giả thuyết nguyên nhân

Ví dụ:

- Quy tắc nghiệp vụ chưa được làm rõ trước khi bắt đầu.
- Không có chính sách xử lý yêu cầu khẩn.
- PO có quá ít thông tin hoặc bị nhiều người ra lệnh.
- Developers chia việc theo lớp kỹ thuật khiến thay đổi nhỏ ở hành vi gây sửa lớn.
- Quản trị dự án yêu cầu thay đổi không qua người có thẩm quyền.

### Bước 4 — Đồng thiết kế thay đổi có giới hạn

Ví dụ, thử trong một Sprint:

- Làm rõ vài tình huống trọng yếu trước khi chọn PBI.
- Ghi câu hỏi còn mở và người có thể quyết định.
- Nêu Sprint Goal và điều kiện thảo luận thay đổi có thể ảnh hưởng Goal.
- Giảm WIP và tránh bắt đầu PBI chưa đủ ngữ cảnh về rủi ro cốt lõi.
- Có đường xử lý sự cố khẩn riêng thay vì gắn nhãn mọi yêu cầu là khẩn.

### Bước 5 — Chọn bằng chứng và guardrails

| Vai trò | Ví dụ |
|---|---|
| **Primary process outcome** | Thời gian/lượng làm lại do thay đổi hiểu biết hoặc quyết định muộn. |
| **Supporting measures** | Số blocker chờ quyết định, tuổi PBI, tỷ lệ câu hỏi còn mở. |
| **Product outcome** | Thời gian nhận Increment dùng được và phản hồi người dùng. |
| **Guardrails** | Không bỏ kiểm tra DoD; không ngăn thay đổi khẩn cần bảo vệ người dùng; không tạo thêm tải họp. |

### Bước 6 — Đặt mốc Check có quyền quyết

Sau cửa sổ đủ quan sát, những người liên quan cùng xem liệu thay đổi có giảm làm lại và bảo vệ Sprint Goal không. Nếu không, xem lại giả thuyết; nếu có, có thể ghi thành working agreement và tiếp tục kiểm tra.

### Bước 7 — Phản hồi lại cho người nêu lo ngại

Thông báo **điều đã thay đổi, điều chưa thay đổi, số liệu và bước tiếp theo**. Không bỏ qua người đã nêu vấn đề sau khi nhận phản hồi.

## 27. Một mẫu “concern-to-evidence” dùng trong workshop

~~~markdown
# Concern card — Ví dụ chuyển đổi Agile

Lo ngại được nêu:
  ...

Người/nhóm chịu tác động:
  ...

Hậu quả nếu lo ngại là đúng:
  ...

Bằng chứng hiện có:
  ...

Điều còn là giả định:
  ...

Nghĩa vụ/guardrail không được vi phạm:
  ...

Giả thuyết thử nghiệm:
  Nếu thay đổi ... trong phạm vi ...
  thì ... có thể cải thiện vì ...

Người cùng thiết kế:
  ...

Owner điều phối và người có quyền quyết:
  ...

Chỉ số trước–sau:
  ...

Nguồn dữ liệu, cửa sổ quan sát và giới hạn:
  ...

Điều kiện dừng hoặc tăng cấp:
  ...

Mốc xem lại:
  ...

Quyết định:
  Duy trì / Sửa / Đo tiếp / Dừng

Phản hồi tới người nêu lo ngại:
  ...
~~~

Không phải mọi góp ý cần thành một thẻ dài. Với câu hỏi đơn giản, có thể trả lời ngay. Với lo ngại ảnh hưởng nhiều người hoặc nghĩa vụ quan trọng, một bản ghi như trên giúp **giữ lời hứa phản hồi và cho phép kiểm tra kết quả**.

### 27.1. Một thẻ đã điền, minh họa

| Trường | Nội dung |
|---|---|
| **Lo ngại** | Sprint ngắn sẽ khiến tích hợp và kiểm thử dồn cuối. |
| **Bằng chứng** | Nhiều PBI ở Sprint trước chỉ được kiểm thử khi backend/frontend đã làm riêng gần xong. |
| **Giả thuyết** | Nếu chia lát giá trị nhỏ và tích hợp mỗi khi có phần dùng được, lỗi tích hợp muộn giảm. |
| **Đầu ra thử** | Contract test cho các trạng thái đăng ký và chính sách kiểm chứng theo DoD. |
| **Primary outcome** | Tỷ lệ PBI có lỗi tích hợp phát hiện sát cuối Sprint. |
| **Guardrails** | Không bỏ phân quyền, test dữ liệu, a11y trong phạm vi áp dụng. |
| **Owner** | Một người điều phối cải tiến được team thống nhất, có người quyết định về nguồn lực. |
| **Mốc Check** | Sau một số PBI đủ so sánh trong khoảng thử đã chốt. |
| **Nếu không đạt** | Xem phụ thuộc môi trường và kiến trúc, điều chỉnh hoặc dừng cách thử. |

### 27.2. Không thu thập mọi lời phàn nàn như hồ sơ nhân sự

Concern card là artifact để **cải tiến hệ thống và quyết định**, không phải hồ sơ xếp loại người có ý kiến. Nếu có nội dung cá nhân nhạy cảm, phải chọn cách xử lý riêng theo thẩm quyền và quyền riêng tư, thay vì đưa nguyên văn vào bảng công khai.

## 28. Đọc dữ liệu chuyển đổi mà không nhầm chỉ số đẹp với kết quả tốt

Một nguyên nhân gây mất tin cậy là tổ chức dùng phép đo thiếu chặt chẽ để tuyên bố thành công trước khi người tham gia nhìn thấy lợi ích thực.

### 28.1. Tách baseline, actual, target và bằng chứng nhân quả

Giả sử trong một thí điểm:

| Chỉ số giả định | Trước | Sau |
|---|---:|---:|
| PBI hoàn thành thuộc loại được đo | 24 | 26 |
| Cycle time trung vị (ngày làm việc) | 18 | 12 |
| Blocked time trung vị (ngày làm việc) | 6 | 3,5 |
| PBI có lỗi tích hợp phát hiện muộn | 9 | 4 |
| Giờ họp trung bình/người/tuần | 7 | 5,5 |

Các phép tính:

~~~text
Cycle time:
  (18 - 12) / 18 × 100% ≈ 33,3% giảm tương đối

Blocked time:
  (6 - 3,5) / 6 × 100% ≈ 41,7% giảm tương đối

Tỷ lệ lỗi tích hợp phát hiện muộn:
  Trước: 9 / 24 = 37,5%
  Sau:   4 / 26 ≈ 15,4%
  Chênh lệch: giảm khoảng 22,1 điểm phần trăm
~~~

**Đây là dữ liệu giả định.** Không thể kết luận những cải thiện này **do Scrum, Kanban hay một chương trình đào tạo duy nhất gây ra**. Việc chia PBI, người tham gia, độ khó, hỗ trợ CI và mức độ đo lỗi có thể đã thay đổi đồng thời.

### 28.2. Câu hỏi của người phản biện cần có chỗ trong buổi đọc số liệu

Ví dụ:

- “Có bao nhiêu hạng mục cũ bị bỏ khỏi mẫu vì đang chờ?”
- “Các story có cùng độ lớn và loại rủi ro không?”
- “Giờ họp giảm nhưng số tin nhắn ngoài giờ có tăng?”
- “Người kiểm thử có thật sự được tham gia sớm hay chỉ đổi tên cột?”
- “Lỗi tích hợp giảm vì tốt hơn hay do nhóm chưa release đủ?”

Đó là **câu hỏi về chất lượng bằng chứng**. Không nên xem việc đặt câu hỏi khiến buổi review “thiếu tinh thần tích cực”.

### 28.3. Biểu đồ phù hợp với câu hỏi

| Câu hỏi | Cách trình bày có thể hữu ích |
|---|---|
| Cycle time có giảm bền vững không? | Biểu đồ từng hạng mục theo thời gian, median và phân vị khi mẫu đủ. |
| Có hàng chờ tích tụ không? | Cumulative flow diagram hoặc tuổi công việc theo trạng thái. |
| WIP có vượt năng lực không? | Biểu đồ WIP theo thời gian với chính sách rõ. |
| Có lỗi nghiêm trọng bị che trong số trung bình? | Tỷ lệ và mức tác động sự cố theo nhóm rủi ro, xem trường hợp cụ thể. |
| Người dùng có được lợi không? | Funnel/cohort outcome kèm guardrails và phản hồi định tính. |
| Cuộc họp có tạo giá trị không? | Thời gian họp, quyết định tạo ra, blocked time được gỡ và phản hồi tham gia. |

Không nên dựng một dashboard đồ sộ nếu đội chưa biết kết quả sẽ dẫn tới **quyết định nào**.

### 28.4. Dữ liệu về con người cần thận trọng hơn

Một khảo sát mức tin cậy có thể bị ảnh hưởng bởi người sợ bị nhận dạng, không trả lời hoặc trả lời theo điều họ nghĩ lãnh đạo muốn nghe. Vì vậy:

- Nêu mục đích, người xem và cách bảo vệ dữ liệu trước khi thu.
- Tránh báo cáo phân khúc quá nhỏ dễ suy ra danh tính.
- Không dùng kết quả khảo sát để chấm điểm từng người.
- Kết hợp quan sát hành vi quản trị và các phản hồi tự nguyện.
- Nếu hứa ẩn danh, cần bảo đảm thật sự đủ điều kiện để làm được.

## 29. Ra quyết định minh bạch khi các bên vẫn không đồng ý

Đối thoại có thể kết thúc với **sự bất đồng còn tồn tại**. Điều đó không tự động làm quyết định vô hiệu. Quan trọng là quyết định được đưa ra **đúng quyền, dựa trên lý do và có cơ chế xem lại**.

### 29.1. Mẫu ghi quyết định chuyển đổi

~~~text
DECISION RECORD — VÍ DỤ

Vấn đề:
  Nhiều PBI chờ review và lỗi tích hợp xuất hiện muộn.

Phương án xem xét:
  A. Giữ quy trình, tăng giờ review.
  B. Thử PR nhỏ, người nhận review rõ và CI hợp đồng.
  C. Thay toàn bộ chuỗi công cụ trong một đợt.

Bằng chứng:
  Flow hiện tại, lỗi tích hợp, tải ngoài giờ, khả năng CI.

Lo ngại được nêu:
  B có thể làm tăng số PR; C tốn kém và khó đảo ngược;
  A có thể làm tăng quá tải.

Quyết định:
  Thử B trong phạm vi một luồng, có giới hạn WIP.

Người có quyền quyết:
  Được tổ chức ủy quyền với phạm vi thử và nguồn lực.

Điều kiện không được bỏ:
  Definition of Done, quyền truy cập, test và giới hạn giờ làm.

Giả thuyết cần kiểm chứng:
  Time to actionable review và lỗi tích hợp muộn giảm.

Mốc xem lại:
  Sau cửa sổ đủ hạng mục; nêu rõ giới hạn dữ liệu.

Điều kiện dừng:
  Chất lượng hoặc tải ngoài giờ suy giảm quá mức chấp nhận.

Phản hồi cho người góp ý:
  Trả lời lý do chọn B, điều chưa giải quyết và lần Check tiếp.
~~~

### 29.2. Phân biệt “đã lắng nghe” với “đã đồng ý”

Nếu một người đề nghị giữ bước review của chuyên gia, tổ chức quyết định chuyển một phần review ít rủi ro sang tự động hóa nhưng giữ review chuyên sâu cho vùng nhạy cảm, cần giải thích:

- Phần quan ngại nào được giữ nguyên dưới dạng guardrail.
- Phần nào được thay đổi và bằng chứng dự kiến.
- Ai có quyền quyết định.
- Cách họ tiếp tục báo sai lệch.

**Không nên viết biên bản “đã thống nhất hoàn toàn” nếu người tham gia vẫn bất đồng thực chất.** Có thể ghi “quyết định được đưa ra sau khi xem các ý kiến; những rủi ro A/B còn phải theo dõi”.

### 29.3. Quyết định tạm cần thời điểm hết hiệu lực hoặc xem lại

Một chính sách thí điểm nếu không có mốc xem lại có thể thành quy định vĩnh viễn theo quán tính. Đặc biệt với ràng buộc mới, hãy ghi **khi nào cần chứng minh còn phù hợp**.

## 30. Mở rộng chuyển đổi theo bằng chứng, không theo số nhóm phải “lên Agile”

Một công ty có mười nhóm có thể muốn tuyên bố thành công khi cả mười dùng chung board và Daily Scrum. Nhưng sự giống nhau về hình thức không đảm bảo các nhóm **đang giải quyết đúng vấn đề hoặc tăng giá trị**.

### 30.1. Chọn luồng thử nghiệm phù hợp

Một nhóm thử nên có:

- Vấn đề rõ và có người chịu ảnh hưởng có thể tham gia.
- Năng lực đo baseline và kiểm chứng kết quả.
- Quyền thay đổi cách làm trong phạm vi hợp lệ.
- Nguồn lực thiết yếu cho chất lượng và vận hành.
- Mức rủi ro có thể kiểm soát.
- Người bảo trợ sẵn sàng gỡ blocker thật.

Nếu chỉ chọn nhóm dễ tuân thủ nhất rồi coi kết quả đại diện cho toàn tổ chức, có **selection bias**. Cần ghi giới hạn khi mở rộng.

### 30.2. Thay đổi theo những gì có thể học chung

Một lộ trình minh họa:

1. **Khám phá:** hiểu hiện trạng, lo ngại và ràng buộc của các luồng công việc.
2. **Thí điểm:** một số thực hành trên phạm vi an toàn, đủ bằng chứng.
3. **Đánh giá:** flow, chất lượng, outcome, quyền và tải con người.
4. **Chuẩn hóa tối thiểu:** chia sẻ nguyên tắc, artifact và kiểm soát đã chứng minh hữu ích.
5. **Điều chỉnh cho từng bối cảnh:** Scrum, Kanban hoặc thực hành kết hợp theo loại việc, không sao chép cứng.
6. **Mở rộng có điều kiện:** đầu tư năng lực lãnh đạo, kỹ thuật, đào tạo, quyền và dữ liệu.
7. **Tiếp tục học:** thay đổi hệ thống đánh giá và quản trị khi thấy động cơ sai.

### 30.3. Bài học phải chuyển được mà không yêu cầu mọi người làm giống nhau

Một nhóm phát triển sản phẩm dùng Scrum có thể chia sẻ với nhóm vận hành cách xác định **blocker, làm rõ Done và phản hồi sớm**. Nhóm vận hành có thể áp dụng Kanban thay vì Sprint. Điều được chuyển giao là **nguyên tắc và bằng chứng**, không nhất thiết tên sự kiện.

### 30.4. Duy trì sau khi coach rời đi

Một chương trình chỉ hoạt động khi có Agile coach nhắc mọi người điền board chưa phải sự thay đổi bền vững. Cần có:

- Quyền quyết định thật trong nhóm.
- Năng lực kỹ thuật để tích hợp/kiểm thử.
- Phản hồi người dùng và dữ liệu đáng tin.
- Thói quen Retrospective hoặc review flow dẫn tới cải tiến.
- Người bảo trợ tiếp tục gỡ trở ngại ở cấp tổ chức.
- Cơ chế xử lý phản biện sau giai đoạn thí điểm.

## 31. Bài tập thực hành: xử lý phản biện mà không áp đặt kết luận

### Tình huống

Một công ty phần mềm muốn chuyển đội sản phẩm từ kế hoạch sáu tháng một lần sang phát triển Increment nhỏ. Trong buổi họp:

1. Kiểm thử: “Không thể có Increment Done mỗi hai tuần với môi trường test hiện tại.”
2. Người quản lý: “Chúng tôi vẫn chịu trách nhiệm ngân sách và deadline hợp đồng.”
3. Developers: “Chúng tôi không có thời gian viết test vì mọi Sprint đều được lấp kín.”
4. Nhân viên làm từ xa: “Review bắt buộc diễn ra ngoài giờ làm của tôi.”
5. Product Owner: “Tôi không được tự ưu tiên backlog dù mọi người yêu cầu tôi chịu trách nhiệm giá trị.”

### Bài tập 1 — Phân loại lo ngại

Hãy phân biệt vấn đề liên quan **chất lượng, năng lực, quyền quyết định, nguồn lực, ràng buộc và điều kiện tham gia**.

**Gợi ý:**

- (1) là rủi ro về môi trường và chất lượng, có thể có cơ sở kỹ thuật.
- (2) là trách nhiệm quản trị thật; cần cơ chế forecast và change control.
- (3) là xung đột giữa cam kết phạm vi và đầu tư năng lực kỹ thuật.
- (4) là vấn đề lịch phối hợp và tính bền vững, không chỉ thái độ.
- (5) là **accountability không đi cùng quyền**, cần giải quyết ở cấp quản trị.

### Bài tập 2 — Đặt câu hỏi lắng nghe

Với trường hợp (1), một câu hỏi tốt:

> “Những bước kiểm thử nào đang cần môi trường chung? Có bao nhiêu PBI bị chặn và giới hạn hiện tại của môi trường là gì? Phần nào có thể kiểm tra sớm mà không bỏ tiêu chuẩn bắt buộc?”

Một câu nên tránh:

> “Bạn có hiểu rằng Agile nghĩa là phải kiểm thử liên tục không?”

**Vì sao?** Câu đầu tìm bằng chứng và khả năng thay đổi; câu sau gắn lỗi vào người đang phản biện mà chưa giải quyết điều kiện kỹ thuật.

### Bài tập 3 — Thiết kế một thí nghiệm

Với vấn đề (3), đề xuất:

> Trong một phạm vi PBI phù hợp, giảm WIP và dành năng lực tích hợp/kiểm thử sớm; theo dõi rework, cycle time và lỗi hồi quy, giữ DoD và không tăng làm ngoài giờ. Sau cửa sổ đủ mẫu, đánh giá có nên duy trì không.

Giả thuyết không phải “ai cũng phải thích TDD”; nó là “năng lực kiểm chứng sớm có thể giúp giảm lỗi và chờ”.

### Bài tập 4 — Tìm người có quyền giải quyết

Với (5), ai cần tham gia?

**Gợi ý:** Product Owner, người có quyền tổ chức/phân bổ ưu tiên và các stakeholder kiểm soát liên quan. Scrum Master có thể hỗ trợ làm minh bạch trở ngại; **không thể tự cấp quyền tài chính hay tự sửa cơ cấu nhân sự** nếu không có thẩm quyền.

### Bài tập 5 — Đặt guardrails

Chọn ít nhất ba:

- Không bỏ kiểm tra dữ liệu và phân quyền cần thiết.
- Không tăng làm ngoài giờ thường xuyên để đạt tỷ lệ hoàn thành Sprint.
- Không dùng velocity làm chỉ tiêu cá nhân.
- Không làm sai nghĩa vụ hợp đồng hoặc báo cáo tài chính.
- Không loại người ở múi giờ khác khỏi quyết định ảnh hưởng họ.

### Bài tập 6 — Khi nào nên dừng?

Giả sử sau thử, cycle time giảm nhưng số lỗi dữ liệu nghiêm trọng tăng và nhân viên báo tải trực vượt mức chấp nhận.

**Gợi ý:** không mở rộng theo chỉ số tốc độ. Cần xử lý rủi ro, có thể dừng phần thử gây hại, tìm nguyên nhân và sửa năng lực kỹ thuật/quy trình. **Đạt chỉ tiêu flow không cho phép bỏ qua an toàn người dùng**.

### Bài tập 7 — Viết lời phản hồi với người bất đồng

Một phản hồi tốt cần:

1. Nhắc lại điều họ lo và tác động.
2. Nói rõ bằng chứng đã kiểm tra.
3. Thừa nhận phần chưa biết.
4. Đưa ra quyết định, quyền và điều kiện.
5. Nêu mốc xem lại, đường phản hồi.

Ví dụ:

> “Lo ngại của bạn là kiểm thử sẽ bị dồn cuối và chất lượng bị giảm. Chúng tôi đã xem dữ liệu PBI gần đây và thấy nhiều lỗi tích hợp phát hiện muộn. Trong thí điểm, đội sẽ giữ DoD, chia lát nhỏ hơn và tích hợp sớm. Sau những PBI đủ quan sát, chúng ta sẽ cùng xem lỗi tích hợp, thời gian chờ và tải kiểm thử. Nếu kiểm soát chất lượng bị bỏ, thử nghiệm đó phải được điều chỉnh hoặc dừng.”

### Bài tập 8 — Chọn Scrum hay Kanban?

Đội hỗ trợ production có yêu cầu khẩn không dự báo được. Một trưởng nhóm đề nghị bắt buộc áp dụng Sprint Goal hai tuần cho mọi việc.

**Gợi ý:** hãy phân tích nguồn nhu cầu, chính sách khẩn, WIP và khả năng dự báo. Có thể dùng Kanban và nhịp phản hồi tương ứng thay vì ép mọi loại việc vào Sprint. **Mục tiêu là phản hồi và giá trị**, không chứng minh một nhãn framework.

## 32. Bộ câu hỏi giúp điều phối workshop

Thay vì hỏi mọi người “bạn thích Agile không?”, người điều phối có thể tổ chức cuộc trao đổi quanh các câu hỏi:

### Về mục tiêu

- Vấn đề hiện tại nào khiến khách hàng hoặc đội mất thời gian/giá trị?
- Điều gì chúng ta muốn cải thiện trong ba tháng tới?
- Nếu cách mới không giúp mục tiêu, có sẵn sàng sửa hoặc dừng không?

### Về hiện trạng

- Một tình huống gần đây cho thấy vấn đề rõ nhất là gì?
- Mắt xích nào gây chờ, làm lại hoặc rủi ro?
- Bằng chứng nào có, bằng chứng nào còn thiếu?
- Ai đang chịu chi phí của vấn đề hiện tại?

### Về quyền và khả năng tham gia

- Ai có thể quyết định đổi thứ tự công việc, phạm vi và nguồn lực?
- Quyền nào cần làm rõ trước khi nhóm tự quản hiệu quả?
- Người nào khó lên tiếng hoặc không dự được cuộc trao đổi?
- Có lo ngại nào cần kênh bảo mật hoặc xử lý nhân sự/pháp lý?

### Về thử nghiệm

- Một thay đổi nhỏ nhất có thể giải quyết điều chưa biết là gì?
- Điều gì không được phép xấu đi?
- Ai điều phối, ai xác minh và ai có quyền dừng?
- Khi nào dữ liệu đủ để quyết định, và ai sẽ nhận phản hồi?

### Về kết quả

- Chúng ta đang đo hoạt động, đầu ra hay outcome?
- Nếu metric chính cải thiện, người dùng hoặc đội có thể vẫn tệ hơn không?
- Có biến bối cảnh nào khiến so sánh trước–sau sai lệch?
- Một ý kiến phản biện đã giúp thay đổi quyết định như thế nào?

Không bắt buộc phải hỏi tất cả các câu trong một buổi. Chọn câu hỏi theo **lo ngại thực, thời gian và quyền có mặt**.

## 33. Những phản mẫu trong xử lý kháng cự

| Phản mẫu | Tác hại | Cách thay thế |
|---|---|---|
| **Dán nhãn “anti-Agile” cho người phản biện.** | Mất thông tin rủi ro và tạo chia phe. | Phân loại vấn đề, bằng chứng và điều kiện thay đổi. |
| **Giảng thêm Agile Manifesto để trả lời mọi lo ngại.** | Không giải quyết quyền, kỹ thuật hoặc tải thực. | Hỏi tình huống và thử giải pháp phù hợp. |
| **Lãnh đạo đã quyết, nhưng gọi cuộc họp là “đồng thiết kế”.** | Tạo cảm giác bị thao túng. | Công khai điều đã chốt và điều có thể góp ý/thay đổi. |
| **Buộc mọi người đồng ý công khai.** | Ý kiến thật bị ẩn, khảo sát thiên lệch. | Kênh phản hồi phù hợp và ghi bất đồng trung thực. |
| **Chỉ mời người ủng hộ vào thí điểm.** | Kết quả selection bias; rủi ro bị bỏ sót. | Đại diện vai trò chịu ảnh hưởng và giới hạn khi tổng quát hóa. |
| **Phản đối kiểm soát an toàn bị gọi là “kháng cự”.** | Vi phạm nghĩa vụ và gây sự cố. | Giữ ràng buộc không thể bỏ; sửa cách kiểm chứng và giao tiếp. |
| **Dùng velocity để ép năng suất cá nhân.** | Đổi ước lượng, giấu lỗi, tăng tải. | Dùng metric flow trong ngữ cảnh để cải tiến hệ thống. |
| **Chỉ đếm số nhóm dùng Scrum.** | Chuyển đổi hình thức, không tăng giá trị. | Xem hành vi, flow, chất lượng và outcome. |
| **Không cấp năng lực CI/kiểm thử nhưng tăng tần suất release.** | Lỗi sản phẩm và nợ kỹ thuật tăng. | Đầu tư kỹ thuật và DoD song song với thay đổi quy trình. |
| **Cho rằng mọi đội phải có cùng cadence.** | Không phù hợp luồng vận hành hoặc nghiên cứu. | Chọn thực hành theo loại việc, mục tiêu và rủi ro. |
| **Thêm họp mà không bỏ họp cũ.** | Tăng gánh nặng và giảm tập trung. | Dùng sự kiện đúng mục đích, loại bỏ báo cáo trùng. |
| **Tuyên bố thành công chỉ qua trước–sau.** | Bỏ qua biến nhiễu và thay đổi mẫu. | Báo giới hạn, guardrails, xu hướng và bằng chứng bổ sung. |
| **Chỉ đưa ra bằng chứng thuận lợi.** | Mất niềm tin, quyết định thiên lệch. | Báo kết quả trái chiều và tác dụng phụ. |
| **Đổ lỗi cho owner khi giả thuyết sai.** | Người làm che tín hiệu thất bại. | Đánh giá chất lượng học hỏi, minh bạch và điều chỉnh. |
| **Lắng nghe nhưng không phản hồi kết quả.** | Người góp ý thấy đối thoại vô nghĩa. | Ghi owner, thời hạn, quyết định và phản hồi lại. |
| **Ép họp ngoài giờ để “tăng cộng tác”.** | Kiệt sức và bất công với nhóm phân tán. | Async-first, overlap công bằng và quy trình trực riêng. |
| **Hứa về việc làm khi không có quyền.** | Xói mòn tin cậy, tạo hiểu lầm nghiêm trọng. | Đưa câu hỏi quyền lợi tới người có thẩm quyền. |
| **Coi im lặng là đồng ý.** | Bỏ qua người ít quyền hoặc chưa có thông tin. | Tạo đường phản hồi đa dạng, không áp lực công khai. |
| **Thay đổi vai trò nhưng không thay quyền và động lực.** | Trách nhiệm mơ hồ, quy trình cũ tái hiện. | Giải quyết governance, nguồn lực và đánh giá. |
| **Không có tiêu chí dừng.** | Thử nghiệm gây hại vẫn mở rộng vì “đã quyết đổi”. | Xác định guardrails và quyền đảo quyết định từ đầu. |
| **Trừng phạt người báo blocker.** | Dữ liệu sai, rủi ro bị che. | Hỗ trợ minh bạch, xử lý hành vi sai cụ thể nếu có bằng chứng. |

## 34. Checklist trước, trong và sau cuộc đối thoại thay đổi

### Trước cuộc đối thoại

- [ ] Có nêu được **vấn đề và giá trị** mà chuyển đổi muốn cải thiện, không chỉ tên framework?
- [ ] Biết phần nào đã quyết và phần nào thực sự còn có thể thay đổi?
- [ ] Đã mời đúng các vai trò chịu ảnh hưởng, kể cả kiểm thử, vận hành và những người ít tiếng nói?
- [ ] Đã xem lịch làm việc/múi giờ và cách đóng góp bất đồng bộ?
- [ ] Có dữ liệu hiện trạng đủ để không chỉ tranh luận bằng cảm giác?
- [ ] Có kênh riêng phù hợp cho nội dung liên quan quyền lợi hoặc thông tin nhạy cảm?

### Trong cuộc đối thoại

- [ ] Đã nghe tình huống cụ thể trước khi giải thích giải pháp?
- [ ] Đã nhắc lại lo ngại để người nói xác nhận cách hiểu?
- [ ] Phân biệt dữ kiện, giả định, dự đoán và quyết định đã có?
- [ ] Có tránh đoán động cơ hoặc gắn nhãn “người chống Agile”?
- [ ] Những kiểm soát an toàn, bảo mật, pháp lý và chất lượng có được nêu rõ?
- [ ] Đã phân biệt ai cung cấp dữ liệu, ai thực hiện và ai có quyền quyết?
- [ ] Có xem phương án khác Scrum/Kanban/XP phù hợp bối cảnh thay vì áp một khuôn?
- [ ] Có thực sự cho phép bằng chứng phản bác thay đổi phương án?

### Khi thiết kế thử nghiệm

- [ ] Lo ngại đã chuyển thành **giả thuyết kiểm chứng được**?
- [ ] Phạm vi đủ nhỏ và phù hợp mức rủi ro?
- [ ] Có baseline, phép đo, nguồn dữ liệu, cửa sổ quan sát và giới hạn?
- [ ] Có guardrails về chất lượng, người dùng, bảo mật và tải con người?
- [ ] Đã nêu owner, người xác minh, quyền dừng và mốc Check?
- [ ] Có năng lực và thời gian để thực hiện, không đẩy thêm việc ngoài giờ?
- [ ] Không tự động thử nghiệm trên người dùng thật nếu rủi ro không được chấp nhận?

### Khi đánh giá và ra quyết định

- [ ] Có phân biệt hoạt động, đầu ra, adoption, flow outcome và product outcome?
- [ ] Đã xem kết quả xấu, biến bối cảnh và dữ liệu chưa chắc, không chỉ số đẹp?
- [ ] Những người từng lo ngại có cơ hội chất vấn kết luận?
- [ ] Đã kiểm tra sự khác biệt giữa nhóm, vai trò và thời gian làm việc?
- [ ] Có quyết định tiếp tục, sửa, đo thêm hoặc dừng theo đúng thẩm quyền?
- [ ] Đã phản hồi lại cho người nêu lo ngại, kể cả khi quyết định không theo đề xuất của họ?
- [ ] Nếu duy trì, đã thay đổi **quyền, công cụ, nguồn lực hoặc working agreement** tương ứng?
- [ ] Có mốc xem lại để tránh nghi thức cũ tái xuất hiện dưới tên mới?

Checklist là **công cụ hỗ trợ đối thoại và tự kiểm tra**, không phải thước đo xếp hạng thái độ của nhân viên hoặc quy trình chứng nhận “Agile mindset”.

## 35. Kết luận

Trong chuyển đổi Agile, **lo ngại và phản biện không nhất thiết là trở ngại cần loại bỏ**. Chúng có thể phản ánh những rủi ro về chất lượng, quyền quyết định, điều kiện lao động, chi phí, an toàn và sự thiếu nhất quán giữa lời nói với hành động. Xử lý tốt đòi hỏi **lắng nghe có thiện chí, nhận diện dữ kiện và giả định, tạo cơ hội tham gia thực chất và công khai giới hạn của thay đổi**.

Đối thoại chỉ có giá trị khi dẫn tới việc **kiểm chứng giả thuyết và thay đổi quyết định**. Một thử nghiệm có phạm vi, owner, baseline, outcome, guardrails và quyền dừng giúp các bên học cùng nhau. Bằng chứng cần được đọc thận trọng: tăng velocity, số Sprint, số khóa đào tạo hoặc số deployment **không tự chứng minh người dùng nhận nhiều giá trị hơn hoặc đội có môi trường làm việc tốt hơn**.

Trong **AGILE_DEVELOPMENT**, Scrum giúp kiểm tra–thích ứng quanh mục tiêu và Increment; Kanban giúp nhìn rõ dòng công việc và nút thắt; XP cùng DevOps tạo năng lực thay đổi an toàn; user story, backlog và phản hồi người dùng hỗ trợ lựa chọn giá trị. Chuyển đổi có ý nghĩa khi tổ chức **sẵn sàng lắng nghe phản biện, giữ kiểm soát thiết yếu, cung cấp điều kiện thực hiện và điều chỉnh chính phương án chuyển đổi dựa trên bằng chứng**, thay vì yêu cầu con người thích nghi với một mô hình được coi là đúng sẵn.
