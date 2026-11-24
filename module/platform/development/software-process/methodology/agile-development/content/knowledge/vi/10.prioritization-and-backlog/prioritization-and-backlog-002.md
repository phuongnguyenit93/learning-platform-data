# Liên kết hạng mục với mục tiêu sản phẩm trong Agile

> **Trọng tâm:** Product Backlog không chỉ là danh sách những việc có thể làm. Mỗi quyết định ưu tiên cần góp phần đưa sản phẩm tới một kết quả mong muốn, tạo bằng chứng về hướng đi, hoặc bảo vệ khả năng cung cấp giá trị. Khi biết **vì sao một hạng mục đáng làm**, nhóm có thể thay đổi phạm vi linh hoạt mà vẫn giữ được mục tiêu chung.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của **Product Goal** và mối quan hệ với **Product Backlog**, **Sprint Goal**, **Product Backlog Item (PBI)** và **Increment**.
2. Phân biệt **đầu ra công việc (output)** với **kết quả sản phẩm (outcome)** để tránh ưu tiên chỉ theo số lượng tính năng hoặc story point.
3. Liên kết hạng mục với mục tiêu qua **vấn đề người dùng, bằng chứng, giả thuyết tác động và cách kiểm chứng**.
4. Sắp xếp thứ tự PBI dựa trên giá trị kỳ vọng, mức độ chắc chắn, rủi ro, độ khẩn cấp, phụ thuộc và chi phí cơ hội.
5. Giải thích vì sao lỗi, nợ kỹ thuật, bảo mật, công việc khám phá và vận hành vẫn có thể đóng góp cho mục tiêu sản phẩm dù không trực tiếp tạo màn hình mới.
6. Thực hành viết **user story, acceptance criteria** và kế hoạch đo kết quả cho một lát cắt tính năng có giá trị.
7. Dùng Scrum, Kanban và XP để duy trì sự liên kết giữa quyết định ưu tiên, việc thực hiện, phản hồi sớm và cải tiến liên tục.

## 2. Khi backlog có nhiều việc nhưng sản phẩm không tiến tới mục tiêu

Một nhóm phát triển nền tảng học trực tuyến có Product Backlog với hàng chục ý tưởng: thêm giao diện tối, tích điểm, diễn đàn, bảng xếp hạng, AI gợi ý bài học, gửi email nhắc học, sửa lỗi lưu tiến độ và cải thiện tốc độ tải bài.

Mỗi đề xuất đều có thể có lý do hợp lý. Tuy nhiên, nếu mục tiêu ưu tiên hiện tại là **giúp người học mới hoàn thành bài đầu tiên**, việc triển khai nhiều tính năng phụ chưa chắc giải quyết được điểm nghẽn. Người học có thể vẫn không biết nên bắt đầu ở đâu, mất tiến độ khi đổi thiết bị, hoặc chờ trang học quá lâu.

Đội có thể hoàn thành nhiều ticket nhưng **không cải thiện hành vi người dùng**. Điều thiếu sót nằm ở câu hỏi trước khi làm việc:

> “Hạng mục này giúp đạt mục tiêu sản phẩm bằng cơ chế nào, dựa trên bằng chứng gì, và ta sẽ kiểm chứng tác động bằng cách nào?”

Không phải mọi hạng mục đều cần chứng minh tác động tài chính trực tiếp. Một công việc xử lý lỗ hổng bảo mật, sửa lỗi gây mất dữ liệu hoặc cải thiện khả năng triển khai có thể tạo giá trị bằng **giảm rủi ro và bảo vệ độ tin cậy**. Điều quan trọng là lý do được trình bày rõ, được so với các lựa chọn khác và không biến backlog thành danh sách mong muốn không giới hạn.

## 3. Hiểu đúng các tầng mục tiêu và công việc

### 3.1. Product Goal trong Scrum

**Product Goal** mô tả trạng thái tương lai của sản phẩm mà Scrum Team hướng tới. Trong Scrum, Product Goal là cam kết gắn với **Product Backlog**; các hạng mục còn lại trong backlog xuất hiện để mô tả những gì có thể giúp hoàn thành Product Goal.

Product Goal tạo định hướng tương đối dài hạn để các bên biết tại sao phải sắp xếp công việc theo một thứ tự nhất định. Nó khác với lịch giao từng tính năng và cũng không nhất thiết là một con số KPI đứng riêng.

Ví dụ:

> **Product Goal minh họa:** “Người học mới có thể tìm được lộ trình phù hợp và hoàn thành bài học đầu tiên thuận lợi trong tuần đầu sau đăng ký.”

Nhóm có thể đặt chỉ báo như **tỷ lệ người học mới hoàn thành bài đầu trong bảy ngày**, nhưng con số chỉ giúp quan sát kết quả. Muốn quyết định đúng, cần làm rõ đối tượng, hành vi, giới hạn đo và phản hồi của người học.

Theo Scrum Guide, Scrum Team tập trung vào **một Product Goal tại một thời điểm** cho đến khi hoàn thành hoặc từ bỏ nó. Điều này không có nghĩa sản phẩm chỉ có một nhu cầu, một chỉ số hoặc một trách nhiệm. Các nghĩa vụ chất lượng, vận hành và an toàn vẫn cần được đáp ứng trong lúc theo đuổi mục tiêu.

### 3.2. Phân biệt những thuật ngữ dễ lẫn

| Thành phần | Câu hỏi nó trả lời | Ví dụ |
|---|---|---|
| **Tầm nhìn sản phẩm (product vision)** | Sản phẩm muốn tạo giá trị tổng quát nào, cho ai? | “Giúp người học phát triển kỹ năng nghề nghiệp bằng lộ trình phù hợp.” |
| **Product Goal** | Trạng thái tương lai đang được ưu tiên đạt tới là gì? | “Người học mới bắt đầu và hoàn thành bài đầu thuận lợi.” |
| **Chỉ báo outcome** | Ta quan sát mức tiến gần mục tiêu bằng gì? | Tỷ lệ hoàn thành bài đầu trong bảy ngày, phản hồi về khó khăn |
| **Cơ hội/vấn đề người dùng** | Điều gì đang ngăn kết quả mong muốn? | Người mới không biết chọn khóa nào, không tìm thấy nút bắt đầu |
| **Giả thuyết giải pháp** | Thay đổi nào *có thể* cải thiện hành vi? | “Lời mời bắt đầu bài đầu ngay sau đăng ký giúp giảm bỏ dở.” |
| **Product Backlog Item** | Công việc sản phẩm nào cần được làm rõ và sắp xếp thứ tự? | Tạo lời mời bắt đầu bài học đầu tiên |
| **Sprint Goal** | Trong Sprint này, Scrum Team muốn đạt một mục tiêu gắn kết nào? | “Người mới có đường đi rõ từ đăng ký đến khi bắt đầu bài đầu.” |
| **Increment** | Phần sản phẩm tích hợp và đáp ứng Definition of Done nào đã được tạo? | Luồng bắt đầu bài đầu hoạt động, có kiểm thử và lưu tiến độ |
| **Bằng chứng sau phát hành** | Thay đổi có tạo tác động mong muốn không? | Người mới bắt đầu và hoàn thành bài nhiều hơn hay không |

Tầm nhìn, *epic*, *initiative* hoặc bản đồ cơ hội có thể hữu ích trong nhiều nhóm, nhưng **không phải mọi thuật ngữ đó đều là tạo tác chính thức được Scrum quy định**. Scrum yêu cầu Product Backlog, Sprint Backlog và Increment với các cam kết tương ứng; đội có thể tổ chức các tầng bổ sung khi thấy cần.

### 3.3. Một sơ đồ liên kết có vòng phản hồi

~~~mermaid
flowchart TD
    A["Product Goal / kết quả cần đạt"] --> B["Vấn đề, cơ hội và bằng chứng người dùng"]
    B --> C["Giả thuyết tác động cần kiểm chứng"]
    C --> D["PBI được sắp thứ tự trong Product Backlog"]
    D --> E["Lát cắt triển khai / Increment đạt DoD"]
    E --> F["Phản hồi người dùng, dữ liệu chất lượng và outcome"]
    F --> G{"Giả thuyết được hỗ trợ?"}
    G -->|"Có"| H["Tiếp tục hoặc mở rộng có kiểm soát"]
    G -->|"Không/chưa rõ"| I["Điều chỉnh giải pháp, ưu tiên hoặc giả định"]
    H --> B
    I --> B
~~~

Sơ đồ cho thấy **liên kết là một giả thuyết có thể bị sửa**, không phải đường ống một chiều mà nhóm phải đi hết dù dữ liệu thay đổi. Một PBI được làm xong là bằng chứng về **output**; nó chưa tự chứng minh outcome sản phẩm đã cải thiện.

## 4. Chọn outcome trước khi chọn tính năng

### 4.1. Output, outcome và impact

| Cấp độ | Ví dụ trong nền tảng học | Ý nghĩa |
|---|---|---|
| **Output** | Hoàn thành nút “Bắt đầu học”, màn giới thiệu khóa và API ghi tiến độ | Thứ được tạo ra hoặc giao |
| **Outcome** | Người học mới bắt đầu bài nhanh hơn, hoàn thành bài đầu nhiều hơn | Thay đổi trong hành vi/trải nghiệm |
| **Impact** | Người học gắn bó hơn, đạt năng lực mong muốn; sản phẩm giảm lãng phí hỗ trợ | Tác động dài hơn tới người dùng/tổ chức |

Nhóm có thể kiểm soát trực tiếp phần lớn **output**, nhưng outcome và impact còn phụ thuộc người dùng, hoàn cảnh và nhiều yếu tố bên ngoài. Vì vậy, hãy coi tác động từ tính năng tới outcome là **giả thuyết cần kiểm chứng**.

### 4.2. Định nghĩa mục tiêu đủ rõ để lựa chọn

Một câu Product Goal hữu ích cho quyết định thường cho biết:

- **Ai** là nhóm người dùng mục tiêu?
- **Hành vi hoặc trạng thái tương lai** nào mong muốn thay đổi?
- **Vì sao** kết quả đó có giá trị?
- **Bằng chứng nào** cho thấy đã tiến gần hơn?
- **Giới hạn/đánh đổi** nào quan trọng, như an toàn dữ liệu, khả năng tiếp cận hoặc độ ổn định?

Ví dụ số liệu dưới đây **hoàn toàn giả định**:

> “Trong quý tiếp theo, giúp người học đăng ký mới hoàn thành bài học đầu tiên trong bảy ngày dễ dàng hơn; theo dõi tỷ lệ hoàn thành hiện tại khoảng 25% và hướng tới mức cải thiện có ý nghĩa, đồng thời không tăng tỷ lệ lỗi, khiếu nại hoặc thời gian tải bài.”

Mức mục tiêu cụ thể như “40%” chỉ nên được chọn sau khi hiểu dữ liệu nền, điều kiện sản phẩm và mức cải thiện khả thi. **Không lấy một con số đẹp rồi suy ngược một danh sách tính năng để hợp thức hóa.**

### 4.3. Leading indicator và lagging indicator

- **Tín hiệu sớm (leading):** tỷ lệ người học bấm “Bắt đầu bài đầu”, thời gian từ đăng ký tới khi mở bài, số người xem được lộ trình rõ ràng.
- **Tín hiệu kết quả muộn hơn (lagging):** tỷ lệ hoàn thành bài trong bảy ngày, quay lại học sau một khoảng thời gian, mức độ đạt mục tiêu học.

Tín hiệu sớm giúp nhóm nhận phản hồi nhanh, nhưng có thể bị tối ưu sai. Người dùng bấm nút nhiều hơn **không bảo đảm** họ học tốt hơn. Nên xem tín hiệu sớm cùng outcome thực và tín hiệu bảo vệ về chất lượng.

## 5. Nhận diện cơ hội thay vì nhảy thẳng sang giải pháp

Giả sử chỉ 25% người dùng đăng ký mới hoàn thành bài đầu tiên trong bảy ngày. Nhóm có thể đề xuất ngay chatbot, AI tư vấn hay email nhắc. Nhưng trước khi chọn, cần hỏi **vì sao** người học dừng lại.

Nguồn thông tin có thể gồm:

- Quan sát luồng đăng ký → chọn khóa → mở bài → hoàn thành bài.
- Phỏng vấn người đã bỏ dở, xem những thời điểm họ gặp khó.
- Phân tích lỗi tải trang, thất bại khi lưu tiến độ và vấn đề trên thiết bị di động.
- Xem câu hỏi hỗ trợ hoặc phản hồi thực tế.
- Kiểm thử khả dụng trên một số tình huống cụ thể.

Kết quả có thể hình thành **bản đồ cơ hội**, chẳng hạn:

~~~text
Product Goal: Người mới hoàn thành bài học đầu tiên thuận lợi
|
+-- Cơ hội A: Không biết nên chọn khóa học nào
|   +-- Giả thuyết: Đề xuất một lộ trình khởi đầu rõ sẽ giảm bỏ dở
|       +-- PBI: Thẻ "Bắt đầu từ đây" theo lựa chọn của người học
|
+-- Cơ hội B: Mất nhiều bước để mở bài đầu
|   +-- Giả thuyết: Lời mời bắt đầu ngay sau đăng ký sẽ tăng lượt mở bài
|       +-- PBI: Nút bắt đầu bài đầu trên màn chào mừng
|
+-- Cơ hội C: Tiến độ không được lưu ổn định
|   +-- Giả thuyết: Sửa lỗi ghi tiến độ sẽ giảm bỏ học do phải học lại
|       +-- PBI: Khôi phục và xác nhận ghi tiến độ
|
+-- Cơ hội D: Trang học tải chậm trên thiết bị di động
    +-- Giả thuyết: Giảm thời gian tải sẽ tăng số lượt hoàn thành bài
        +-- PBI: Tối ưu tải nội dung bài đầu
~~~

Bản đồ giúp đội nhìn thấy **nhiều cách khác nhau** để tiến tới cùng một mục tiêu. Nó cũng làm rõ rằng một ý tưởng có thể chưa phải việc ưu tiên nhất dù xuất phát từ người có vai trò cao.

Không cần biến mỗi nhánh thành một tài liệu dài. Một bảng liên kết gọn trong backlog hoặc sơ đồ dùng chung thường đủ nếu mọi người có thể kiểm tra nguồn bằng chứng.

## 6. Liên kết hạng mục bằng một lời giải thích có thể kiểm chứng

Một PBI không nhất thiết phải mô tả ngay tất cả cách triển khai. Tuy nhiên, trước khi xếp nó lên đầu, nhóm nên có khả năng trả lời:

1. **Mục tiêu liên quan:** hạng mục này đóng góp cho Product Goal hoặc bảo vệ khả năng đạt mục tiêu ra sao?
2. **Vấn đề/cơ hội:** người dùng hoặc hệ thống đang gặp vấn đề cụ thể nào?
3. **Bằng chứng:** quan sát nào hỗ trợ và điều gì vẫn chưa chắc chắn?
4. **Giả thuyết tác động:** nếu thực hiện, hành vi hay rủi ro nào được kỳ vọng thay đổi?
5. **Cách kiểm chứng:** acceptance criteria xác nhận tính năng hoạt động thế nào, outcome sẽ đo bằng gì?
6. **Chi phí cơ hội:** chọn việc này có nghĩa việc nào phải chờ?

Một câu liên kết ngắn có thể viết:

> “Chúng ta ưu tiên **[PBI]** vì **[vấn đề/bằng chứng]** đang cản **[Product Goal]**. Chúng ta kỳ vọng **[thay đổi hành vi hoặc rủi ro]**, và sẽ kiểm tra bằng **[tín hiệu chính + tín hiệu bảo vệ]**.”

### Mẫu PBI có ngữ cảnh vừa đủ

~~~markdown
Mã: LEARN-124
Tiêu đề: Cho người mới bắt đầu bài học đầu tiên từ màn chào mừng
Product Goal: Người mới hoàn thành bài học đầu trong 7 ngày
Vấn đề: Người vừa đăng ký không rõ bước tiếp theo
Nguồn bằng chứng: Phản hồi hỗ trợ và quan sát hành trình đăng ký
Giả thuyết: Lời mời bắt đầu rõ ràng sẽ giảm bỏ dở trước khi mở bài
Giá trị kỳ vọng: Người học bắt đầu bài nhanh hơn và tiến gần mục tiêu hoàn thành
Phạm vi thử: Người mới đủ điều kiện, một lộ trình khởi đầu đã có
Acceptance criteria: Liên kết tới kịch bản kiểm chứng được
Chất lượng cần giữ: Hiển thị trên di động, truy cập được, lưu trạng thái đúng
Tín hiệu sớm: Tỷ lệ mở bài đầu, thời gian từ đăng ký đến mở bài
Outcome: Tỷ lệ hoàn thành bài đầu trong 7 ngày
Rủi ro/điểm chưa rõ: Người học có thể mở bài nhưng chưa hoàn thành
Quyết định tiếp: Xem dữ liệu sau thời gian quan sát đã thống nhất
~~~

Các mã, trường và nội dung trên chỉ là **ví dụ tùy biến**. Scrum không bắt buộc mỗi PBI phải có mẫu này hay phải dùng cú pháp user story. Với công việc nhỏ, nhiều trường có thể nằm ở epic/chủ đề chung hoặc được liên kết thay vì sao chép lại.

## 7. Hạng mục không trực tiếp tạo tính năng vẫn phải được đánh giá đúng

Đòi hỏi mọi việc đều phải có “tỷ lệ chuyển đổi tăng X%” sẽ khiến nhóm trì hoãn công việc nền tảng, bảo mật và chất lượng. Hãy phân biệt cách một hạng mục tạo giá trị:

| Loại hạng mục | Cách liên kết với mục tiêu | Ví dụ |
|---|---|---|
| **Giá trị người dùng trực tiếp** | Tạo hành vi hoặc khả năng mới phục vụ outcome | Nút bắt đầu bài học đầu trên màn chào mừng |
| **Khắc phục lỗi (bug)** | Khôi phục trải nghiệm cần có; giảm gián đoạn và mất niềm tin | Sửa lỗi làm mất tiến độ sau khi tải lại |
| **Khám phá/giảm bất định** | Tạo bằng chứng giúp chọn hướng ít lãng phí | Phỏng vấn người học mới vì chưa biết nguyên nhân bỏ dở |
| **Năng lực kỹ thuật (enabler)** | Gỡ rào cản để giao giá trị hoặc thay đổi an toàn hơn | Bổ sung kiểm thử tích hợp cho việc lưu tiến độ |
| **Chất lượng/vận hành** | Duy trì hiệu năng, độ ổn định và hỗ trợ đo kết quả | Tối ưu tải bài đầu trên mạng di động |
| **Bảo mật/tuân thủ** | Giảm rủi ro và đáp ứng trách nhiệm bắt buộc của sản phẩm | Sửa kiểm soát truy cập khiến dữ liệu tiến độ có nguy cơ lộ |
| **Bảo trì/nợ kỹ thuật** | Giảm chi phí sửa đổi và rủi ro kéo dài | Tách logic ghi tiến độ đang bị phụ thuộc chéo, có minh chứng lỗi lặp |

Với PBI kỹ thuật, lời giải thích có thể đi qua một **chuỗi đóng góp gián tiếp**:

> “Luồng học phải lưu được tiến độ (điều kiện để hoàn thành bài) → hệ thống hiện lỗi ghi tiến độ trên thiết bị nhất định → cần sửa lưu trạng thái và bổ sung kiểm thử → giảm học lại ngoài ý muốn.”

**Không buộc mọi lỗi khẩn cấp phải đi qua một chiến dịch đo outcome dài hạn.** Nếu xảy ra mất dữ liệu, vi phạm an toàn hoặc sự cố nghiêm trọng, trách nhiệm xử lý có thể tự tạo mức ưu tiên cao. Dấu vết cần nêu rủi ro và căn cứ, không bịa ra con số lợi nhuận để được phép sửa.

Ngược lại, một đề xuất “refactor cho sạch code” vẫn cần thảo luận rủi ro đang có, chi phí đổi mã, công việc nào được hỗ trợ và điều gì khiến nó đáng làm ở thời điểm hiện tại.

## 8. Sắp xếp thứ tự backlog theo mục tiêu và bằng chứng

Product Backlog trong Scrum là **danh sách được sắp thứ tự, thay đổi khi có thông tin mới**. Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog; việc sắp thứ tự cần dựa trên thông tin từ người dùng, bên liên quan và Developers.

### 8.1. Các yếu tố cần cân nhắc

| Yếu tố | Câu hỏi cụ thể | Điều cần thận trọng |
|---|---|---|
| **Giá trị kỳ vọng** | Nếu thành công, ai được lợi và bao nhiêu? | Không gán “giá trị cao” chỉ vì tính năng nổi bật |
| **Bằng chứng/độ chắc chắn** | Vấn đề và giải pháp đã được quan sát tới đâu? | Phân biệt nhu cầu đã xác nhận với đề xuất suy đoán |
| **Rủi ro nếu hoãn** | Không làm lúc này gây mất dữ liệu, thất bại nghiệp vụ hoặc chi phí gì? | Xử lý sự cố/tuân thủ dựa trên hậu quả thực tế |
| **Thời điểm/cơ hội** | Có hạn bên ngoài, mùa vụ hoặc phụ thuộc quyết định khác không? | Tránh gắn “khẩn cấp” cho mọi mong muốn |
| **Chi phí và độ phức tạp** | Ước lượng vừa đủ về nỗ lực, công nghệ, phối hợp, kiểm thử | Ước lượng không phải dữ liệu chính xác |
| **Phụ thuộc và khả năng chia nhỏ** | Có thể thử một lát cắt trước khi làm toàn bộ không? | Không xây nhiều hạ tầng trước khi kiểm chứng giả định đơn giản |
| **Khả năng học hỏi** | Việc nào giúp loại bỏ giả định lớn sớm nhất? | Một thử nghiệm nhỏ có thể quan trọng hơn tính năng lớn |
| **Sức chứa hiện tại** | Công việc đang thực hiện và điểm tắc ra sao? | Nhận thêm việc có thể làm chậm hoàn tất việc đang mở |

Các kỹ thuật như **RICE**, **WSJF**, **MoSCoW** hoặc chấm điểm giá trị–nỗ lực có thể hỗ trợ trao đổi, nhưng **không phải thuật toán thay Product Owner đưa ra quyết định**. Khi đầu vào chỉ là ước lượng chủ quan, điểm số nhiều chữ số không tạo ra sự chính xác thật.

### 8.2. Bảng lựa chọn minh họa

Giả sử nhóm có tín hiệu rằng người học mới bỏ dở trước khi hoàn thành bài đầu. Bảng dưới dùng nhận định **minh họa**, cần được xác minh trong sản phẩm thực tế.

| PBI/đề xuất | Kết nối với mục tiêu | Bằng chứng hiện có | Chi phí/rủi ro | Hướng xử lý |
|---|---|---|---|---|
| Sửa lỗi mất tiến độ bài học | Rất trực tiếp: ngăn học lại và bỏ dở | Lỗi có thể tái hiện | Mức ảnh hưởng đáng kể | Ưu tiên sớm và kiểm thử hồi quy |
| Lời mời bắt đầu bài đầu trên màn chào mừng | Trực tiếp: giúp người mới biết bước tiếp | Phản hồi hỗ trợ, quan sát luồng | Có thể chia lát cắt nhỏ | Thử sớm với phạm vi hạn chế |
| Đo sự kiện mở/hoàn thành bài đầu | Giúp biết tác động của thay đổi | Dữ liệu hiện thiếu | Cần kiểm soát dữ liệu người dùng | Xây đo tối thiểu trước hoặc cùng lúc thử |
| Tối ưu tải trang học đầu | Liên quan tới trải nghiệm và hoàn thành | Cần xác nhận mức chậm và phân khúc | Có thể cần nghiên cứu hiệu năng | Đo mức ảnh hưởng và ưu tiên theo hậu quả |
| AI gợi ý khóa học toàn hệ thống | Có thể giúp chọn khóa, nhưng giả thuyết rộng | Chưa đủ bằng chứng | Công sức và phụ thuộc lớn | Tách thành phép thử gợi ý đơn giản |
| Giao diện tối toàn bộ sản phẩm | Có thể hữu ích cho người học lâu dài | Chưa rõ liên quan điểm nghẽn trước bài đầu | Mức phạm vi rộng | Giữ ở backlog, làm rõ giá trị và thời điểm |

Không cần loại bỏ vĩnh viễn ý tưởng có giá trị về sau. **Ưu tiên là quyết định theo thời điểm**, và có thể thay đổi khi mục tiêu, bằng chứng hoặc rủi ro thay đổi.

### 8.3. Làm rõ sự đánh đổi khi đổi thứ tự

Khi một bên liên quan yêu cầu “làm tính năng X ngay”, câu trả lời hữu ích là:

> “X có thể giải quyết vấn đề nào của người học? Hiện nhóm đang ưu tiên sửa lỗi mất tiến độ và thử luồng bắt đầu bài vì chúng ảnh hưởng trực tiếp Product Goal. Nếu chuyển X lên đầu, ta cần dời hoặc giảm phần nào, và kết quả nào sẽ chứng minh X đáng ưu tiên hơn?”

Cách trao đổi này không bác bỏ người đề xuất; nó **đưa quyết định trở lại giá trị, bằng chứng và chi phí cơ hội**.

## 9. Từ Product Goal đến user story và acceptance criteria

Giả sử nhóm chọn thử một luồng giúp người học mới bắt đầu bài học đầu tiên từ màn chào mừng.

### 9.1. Xác định giả thuyết

> “Với người học vừa đăng ký và đã chọn một lộ trình khởi đầu, nếu màn chào mừng đưa ra hành động **Bắt đầu bài đầu tiên** rõ ràng thì tỷ lệ mở bài trong phiên đầu có thể tăng. Nhóm sẽ quan sát thêm tỷ lệ hoàn thành bài trong bảy ngày để kiểm tra mục tiêu cuối.”

Giả thuyết nêu đối tượng, thay đổi, tín hiệu sớm và outcome sau cùng. Tỷ lệ mở bài tăng **chưa đủ** để khẳng định người dùng học hiệu quả hơn.

### 9.2. Viết user story theo giá trị người học

> **Là** người học vừa đăng ký, **tôi muốn** bắt đầu bài đầu tiên từ màn chào mừng **để** không phải tìm đường qua nhiều menu trước khi học.

Đây là cách viết thuận tiện, **không phải cấu trúc bắt buộc của mọi Product Backlog Item**. Với công việc bảo mật, kiến trúc hoặc khám phá, mô tả vấn đề và kết quả mong muốn có thể phù hợp hơn.

### 9.3. Acceptance criteria kiểm chứng hành vi

~~~gherkin
Tính năng: Bắt đầu bài đầu từ màn chào mừng

Kịch bản: Người học đã có lộ trình khởi đầu hợp lệ
  Cho trước người học vừa hoàn tất đăng ký
  Và có lộ trình khởi đầu hợp lệ
  Khi người học xem màn chào mừng
  Thì hệ thống hiển thị hành động "Bắt đầu bài đầu tiên"
  Và nêu rõ bài học sẽ được mở

Kịch bản: Người học chọn bắt đầu
  Cho trước người học đang xem lời mời bắt đầu bài
  Khi người học chọn "Bắt đầu bài đầu tiên"
  Thì hệ thống mở đúng bài đầu của lộ trình
  Và người học có thể bắt đầu nội dung học

Kịch bản: Chưa có lộ trình hợp lệ
  Cho trước người học chưa chọn được lộ trình khởi đầu
  Khi người học xem màn chào mừng
  Thì hệ thống không đưa liên kết tới bài không tồn tại
  Và hướng dẫn bước lựa chọn phù hợp

Kịch bản: Bài học không thể tải
  Cho trước dịch vụ tải nội dung bài học gặp lỗi
  Khi người học thử mở bài đầu
  Thì hệ thống không hiển thị trạng thái học thành công sai lệch
  Và cung cấp cách thử lại hoặc nhận hỗ trợ phù hợp
~~~

Các tiêu chí này xác định **điều sản phẩm phải làm đúng**. Chúng không tự chứng minh giả thuyết về tỷ lệ hoàn thành bài; kết quả đó cần quan sát sau khi triển khai trong điều kiện phù hợp.

### 9.4. Definition of Done và tín hiệu bảo vệ

Một Increment cần đáp ứng **Definition of Done (DoD)** áp dụng, chẳng hạn:

- Các kịch bản chấp nhận và kiểm thử hồi quy liên quan đạt.
- Luồng truy cập đúng nội dung, xử lý trạng thái lỗi rõ ràng.
- Hành động có thể dùng trên thiết bị mục tiêu và với yêu cầu tiếp cận đã xác định.
- Ghi nhận số liệu đo vừa đủ, tuân thủ quy định về dữ liệu và quyền riêng tư.
- Thay đổi được tích hợp, kiểm tra và vận hành theo tiêu chuẩn của nhóm.

Trong quá trình quan sát, dùng **tín hiệu bảo vệ (guardrails)** như tỷ lệ lỗi mở bài, thời gian tải, phản hồi người học và lỗi mất tiến độ. Không đẩy nhanh một chỉ số bằng cách gây ra tác dụng phụ lớn hơn.

## 10. Giao theo lát cắt tăng dần để nhận phản hồi sớm

Nếu backlog được chia theo từng lớp kỹ thuật như “làm toàn bộ database”, “làm toàn bộ API”, “làm toàn bộ giao diện”, nhóm có thể mất nhiều thời gian trước khi người học trải nghiệm được một luồng hoàn chỉnh.

Một cách cắt **theo giá trị người dùng (vertical slicing)**:

1. **Lát cắt A:** với người đã có lộ trình, mở được bài đầu trực tiếp từ màn chào mừng trên một hành trình đơn giản và đạt DoD.
2. **Lát cắt B:** hỗ trợ người chưa chọn lộ trình với hướng dẫn phù hợp, dựa trên phản hồi từ A.
3. **Lát cắt C:** tiếp tục bài dang dở từ thiết bị khác nếu bằng chứng cho thấy vấn đề này quan trọng và hệ thống đáp ứng được.

Mỗi lát cắt nên có thể tích hợp và kiểm chứng; không bắt buộc mỗi lát cắt phải được phát hành ngay tới tất cả người dùng. Với sản phẩm rủi ro cao, cần quy trình phát hành thử và quản lý tác động phù hợp.

### Kết nối với Product Goal qua Sprint Goal

Trong Scrum, một Sprint Goal khả thi cho lát cắt A có thể là:

> “Người học mới đã chọn lộ trình có thể mở bài đầu từ màn chào mừng trong một luồng hoàn chỉnh, an toàn và đo được.”

**Sprint Goal** giúp Developers tập trung vào kết quả cần giao trong Sprint; **Product Goal** là định hướng dài hơn. Nếu có thông tin mới, nhóm có thể làm rõ hoặc thương lượng phạm vi với Product Owner mà vẫn giữ Sprint Goal và không giảm chất lượng.

Trong Sprint Review, nhóm kiểm tra Increment với các bên liên quan và thảo luận điều vừa học. Nếu cần thêm thời gian để quan sát tỷ lệ hoàn thành bảy ngày, hãy nói rõ **Increment đã giao** và **giả thuyết outcome đang chờ dữ liệu**, không tự kết luận thành công chỉ từ buổi demo.

## 11. Dùng Scrum, Kanban và XP để duy trì sự liên kết

| Cách tiếp cận | Cơ chế giúp giữ liên kết mục tiêu – công việc | Câu hỏi nên hỏi thường xuyên |
|---|---|---|
| **Scrum** | Product Goal định hướng Product Backlog; Sprint Goal tập trung ngắn hạn; Sprint Review kiểm tra kết quả và điều chỉnh backlog | “Sprint này làm gì để tiến gần Product Goal, và đã học được gì từ Increment?” |
| **Kanban** | Nhìn rõ luồng từ yêu cầu tới hoàn thành; kiểm soát WIP, xác định công việc bị chặn và theo dõi thời gian xử lý | “Các PBI có giá trị cao đang bị chờ ở đâu và vì sao?” |
| **XP** | Kiểm thử, TDD khi phù hợp, CI, refactoring và cộng tác kỹ thuật giúp giao lát cắt nhỏ mà vẫn dễ thay đổi | “Có thể sửa giải pháp khi giả thuyết thay đổi mà không phá vỡ chức năng đã đúng không?” |

### 11.1. Với Scrum: Product Owner sắp thứ tự, toàn nhóm làm rõ

Product Owner chịu trách nhiệm bảo đảm Product Backlog hiệu quả, được sắp thứ tự và minh bạch. Các chuyên gia kỹ thuật, QA và bên liên quan cung cấp thông tin để ra quyết định; không nên biến việc ưu tiên thành bảng xếp hạng theo ai yêu cầu nhiều nhất.

**Product Backlog refinement** là hoạt động làm rõ, chia nhỏ và thêm thông tin cho PBI khi cần; không phải một sự kiện Scrum chính thức với lịch bắt buộc. Chỉ nên làm chi tiết những hạng mục có khả năng thực hiện gần, còn những giả định xa hơn có thể giữ ở mức khái quát.

### 11.2. Với Kanban: giảm thời gian từ ý tưởng có giá trị đến bằng chứng

Giả sử nhóm dùng các trạng thái:

~~~text
Chưa rõ vấn đề
    -> Đã có giả thuyết
    -> Sẵn sàng thực hiện
    -> Đang thực hiện
    -> Đang kiểm chứng
    -> Hoàn thành / Có quyết định tiếp
~~~

Đây là workflow minh họa, không phải mẫu cột bắt buộc. Giới hạn **Work in Progress (WIP)** giúp nhóm tránh mở nhiều PBI quan trọng cùng lúc nhưng không có việc nào hoàn tất.

Các phép đo như **cycle time, throughput, WIP và work item age** phản ánh dòng công việc. Chúng giúp phát hiện tắc nghẽn, nhưng **không tự đo giá trị sản phẩm**. Một nhóm có thể đóng ticket nhanh mà vẫn tập trung sai mục tiêu.

### 11.3. Với XP: khả năng thay đổi là tài sản sản phẩm

Nếu nhóm luôn né sửa lỗi lưu tiến độ vì code quá khó thay đổi, Product Goal có thể bị cản bởi **rủi ro kỹ thuật**. Việc đầu tư kiểm thử, CI và refactoring giúp nhóm:

- Kiểm chứng hành vi quan trọng thường xuyên.
- Giảm chi phí sửa đổi khi có phản hồi người dùng.
- Phát hiện lỗi hồi quy trước hoặc sớm sau phát hành.
- Giữ khả năng giao Increment nhỏ, đáng tin.

Kỹ thuật tốt là điều kiện hỗ trợ tốc độ học và giao giá trị; **số kiểm thử hay phần trăm coverage không phải outcome người dùng**.

## 12. Duy trì backlog khi mục tiêu và bằng chứng thay đổi

Product Backlog mang tính **nổi lên và phát triển (emergent)**. Khi có dữ liệu mới, Product Owner có thể sắp lại thứ tự, chỉnh sửa, chia nhỏ hoặc loại bỏ những PBI không còn đáng làm. Không cần giữ mọi ý tưởng mãi trong backlog để chứng minh chúng từng được lắng nghe.

### 12.1. Những dấu hiệu backlog đang mất liên kết

- Nhiều hạng mục chỉ ghi tên tính năng, không ai giải thích được **vấn đề người dùng**.
- PBI ưu tiên cao nhưng không liên quan mục tiêu hiện tại hoặc nghĩa vụ rõ ràng.
- Nhóm dành phần lớn thời gian cho việc được yêu cầu gấp qua tin nhắn cá nhân.
- Story point/velocity tăng nhưng outcome sản phẩm và chất lượng không cải thiện.
- Lỗi nghiêm trọng hoặc dữ liệu sai bị hoãn vì “không có chỗ trong roadmap”.
- Các giả định đã bị bác bỏ vẫn được triển khai vì có kế hoạch cũ.
- Product Goal chỉ xuất hiện trên slide khởi động, không ảnh hưởng quyết định hằng tuần.

### 12.2. Lịch rà soát theo vòng phản hồi

| Thời điểm | Cần kiểm tra | Quyết định có thể phát sinh |
|---|---|---|
| **Khi tiếp nhận phản hồi mới** | Tín hiệu là sự thật quan sát hay một đề xuất giải pháp? | Khám phá thêm, xử lý khẩn, tạo PBI hoặc ghi nhận để xem sau |
| **Khi refinement** | PBI có mục tiêu, giá trị, rủi ro và phạm vi đủ rõ để sắp thứ tự không? | Chia nhỏ, làm thử nghiệm, thêm acceptance criteria |
| **Khi Sprint Planning/nhận việc** | Công việc được chọn có góp phần vào mục tiêu ngắn hạn và năng lực hiện tại không? | Lựa chọn hoặc thương lượng phạm vi |
| **Khi Review và xem dữ liệu** | Increment tạo tín hiệu gì, giả thuyết nào cần sửa? | Đổi thứ tự backlog, mở rộng hoặc dừng giải pháp |
| **Khi Retrospective/cải tiến luồng** | Cách chọn và hoàn tất PBI có tạo thời gian chờ, gián đoạn hay lỗi không? | Điều chỉnh chính sách WIP, tiêu chí làm rõ, kiểm thử |

Không phải tất cả bước trên đều cần một cuộc họp riêng. Chọn kênh phù hợp và cập nhật nguồn thông tin chung để những người liên quan hiểu quyết định.

### 12.3. Khi Product Goal không còn phù hợp

Nếu dữ liệu chứng minh vấn đề ban đầu đã được giải quyết, không còn cấp thiết hoặc hướng đi không còn khả thi, Scrum Team và các bên liên quan cần trao đổi để **hoàn thành hoặc từ bỏ Product Goal**, sau đó xác lập mục tiêu tiếp theo. Đừng tiếp tục triển khai PBI cũ chỉ để giữ lời hứa với một danh sách công việc đã lỗi thời.

Khi một mục tiêu được thay thế, việc lưu ngắn **vì sao**, **bằng chứng nào** và **các PBI nào cần xem lại** giúp tránh lặp lại quyết định cũ. Lịch sử quan trọng, nhưng không cần tạo bộ hồ sơ nặng cho từng thay đổi nhỏ.

## 13. Đo sự tiến gần mục tiêu bằng nhiều tín hiệu

### 13.1. Thiết kế bộ đo nhỏ

Với ví dụ người học mới, nhóm có thể theo dõi:

| Loại | Tín hiệu | Câu hỏi |
|---|---|---|
| **Outcome chính** | Tỷ lệ người đăng ký mới hoàn thành bài đầu trong 7 ngày | Người học có thực sự tiến tới mục tiêu không? |
| **Tín hiệu sớm** | Tỷ lệ mở bài đầu trong phiên đầu; thời gian tới khi mở bài | Có giảm khó khăn ở bước bắt đầu không? |
| **Chất lượng** | Tỷ lệ lỗi mở bài, lỗi lưu tiến độ, thời gian tải | Có tác dụng phụ khiến người học bỏ dở không? |
| **Trải nghiệm** | Phản hồi của người mới và câu hỏi hỗ trợ | Có vấn đề nào số liệu thao tác chưa phản ánh không? |
| **Dòng công việc** | Cycle time, work item age, số PBI bị chặn | Nhóm có đang chậm đưa giả thuyết đến kiểm chứng không? |

Không biến tất cả thành KPI thưởng/phạt. Dữ liệu dùng để nhận biết rủi ro, đặt câu hỏi và lựa chọn bước tiếp theo.

### 13.2. Cần định nghĩa tử số, mẫu số và thời điểm

Ví dụ với tỷ lệ hoàn thành bài đầu trong bảy ngày:

\[
\text{Tỷ lệ hoàn thành} =
\frac{\text{Số người thuộc nhóm đăng ký mới hoàn thành bài đầu trong 7 ngày}}
{\text{Tổng số người đăng ký mới đủ điều kiện trong cùng nhóm}}
\times 100\%
\]

Nhóm phải định nghĩa **“đủ điều kiện”**, **“đăng ký mới”**, **“hoàn thành bài”** và mốc bảy ngày bắt đầu từ đâu. Không so sánh kết quả nếu sau thay đổi cách ghi sự kiện hoặc cách tính mẫu số cũng thay đổi mà không được giải thích.

### 13.3. Đọc dữ liệu mà không suy luận quá mức

Giả sử số liệu **minh họa** cho một nhóm đăng ký mới:

| Giai đoạn | Người đăng ký đủ điều kiện | Hoàn thành bài đầu trong 7 ngày | Tỷ lệ |
|---|---:|---:|---:|
| Trước khi đổi luồng | 400 | 100 | 25% |
| Sau khi đổi luồng | 420 | 130 | Khoảng 31,0% |

Chênh lệch quan sát khoảng **6,0 điểm phần trăm**. Đây có thể là tín hiệu đáng xem tiếp, nhưng chưa chứng minh thay đổi giao diện **là nguyên nhân duy nhất**. Phải xem cơ cấu người dùng, chiến dịch thu hút, nội dung khóa, mùa vụ, lỗi theo dõi và thay đổi đồng thời khác.

Nếu cần bằng chứng tác động mạnh hơn, nhóm có thể cân nhắc thử nghiệm có nhóm so sánh phù hợp hoặc kết hợp phân tích dữ liệu và nghiên cứu định tính. Với ít mẫu, tránh tuyên bố chắc chắn từ một tuần kết quả.

### 13.4. Phân biệt điều đã giao và điều đã học

Một Sprint có thể kết thúc với Increment đạt DoD và luồng mở bài hoạt động đúng. **Điều đó là thành công về giao phần mềm theo phạm vi đã chọn.** Nếu outcome bảy ngày chưa quan sát đủ, hãy ghi “đang theo dõi” thay vì tự khẳng định đã tăng tỷ lệ hoàn thành.

Nếu tỷ lệ hoàn thành không tăng, điều đó **không tự động có nghĩa nhóm đã xây sai code**. Có thể giả thuyết sai, đối tượng thử không phù hợp hoặc vẫn còn điểm tắc khác. Việc học này giúp Product Backlog được điều chỉnh và tránh đầu tư thêm vào một giải pháp kém hiệu quả.

## 14. Tình huống tổng hợp: chọn ba PBI cho mục tiêu kích hoạt học tập

### Bối cảnh

Nhóm có Product Goal **“Người mới hoàn thành bài học đầu tiên thuận lợi trong tuần đầu”**. Có ba đề xuất nổi bật:

1. **PBI-A:** sửa lỗi mất tiến độ sau khi người học chuyển thiết bị.
2. **PBI-B:** tạo lời mời bắt đầu bài đầu rõ trên màn chào mừng.
3. **PBI-C:** xây hệ thống AI gợi ý toàn bộ khóa học.

Giả sử dữ liệu và quan sát ban đầu cho thấy người học thường không tìm thấy bước bắt đầu; có lỗi mất tiến độ tái hiện được; còn hiệu quả của AI gợi ý chưa được kiểm chứng.

### Liên kết từng PBI

| PBI | Cơ chế tạo giá trị | Bằng chứng đang có | Câu hỏi còn mở |
|---|---|---|---|
| **A** | Bảo vệ nỗ lực học tập và giảm buộc học lại | Lỗi tái hiện được trên một số thiết bị | Phạm vi ảnh hưởng và nguyên nhân kỹ thuật? |
| **B** | Giúp người mới đi vào bài học với ít bước hơn | Quan sát người mới lúng túng sau đăng ký | Có tăng tỷ lệ mở và hoàn thành bài không? |
| **C** | Có thể giúp chọn khóa phù hợp | Chủ yếu là giả định | Người học có cần AI, hay chỉ cần hướng dẫn đơn giản? |

### Quyết định ưu tiên có căn cứ

Nhóm ưu tiên đánh giá và sửa **A** theo mức nghiêm trọng vì lỗi có thể gây mất công sức học và làm sai dữ liệu tiến độ. Sau đó hoặc song song trong khả năng hợp lý, nhóm thực hiện lát cắt nhỏ **B** để kiểm tra giả thuyết về bước bắt đầu. Với **C**, nhóm trước tiên có thể thử gợi ý thủ công một số lộ trình hoặc phỏng vấn người mới để xem vấn đề thực sự có nằm ở việc chọn khóa không.

Thứ tự và cách phân chia nguồn lực thực tế phụ thuộc mức ảnh hưởng, năng lực nhóm và các ràng buộc khác. **Không thể suy ra duy nhất một thứ tự đúng từ tên của ba PBI**.

### Sau vòng phản hồi

Nếu B khiến lượt mở bài tăng nhưng tỷ lệ hoàn thành không cải thiện, nhóm có thể:

- Xem người học dừng ở phần nào của bài.
- Kiểm tra tốc độ tải, độ khó nội dung và khả năng lưu tiến độ.
- Điều chỉnh ưu tiên PBI dựa trên điểm nghẽn mới thay vì tiếp tục thêm lời mời bắt đầu.

Nếu A làm giảm lỗi mất tiến độ, đó là kết quả chất lượng quan trọng, ngay cả khi chưa nhìn thấy mức tăng outcome trong một thời gian ngắn. Cách tiếp cận này cho phép ưu tiên cả **giá trị trực tiếp, học hỏi và giảm rủi ro**.

## 15. Những cách hiểu sai cần tránh

| Cách hiểu sai | Hậu quả | Cách điều chỉnh |
|---|---|---|
| “Backlog càng nhiều ý tưởng càng tốt.” | Khó tìm việc quan trọng, tăng chi phí quản lý | Làm rõ, sắp thứ tự, gộp hoặc bỏ ý tưởng không còn phù hợp |
| “Mỗi PBI bắt buộc phải có tăng trưởng KPI trực tiếp.” | Trì hoãn bảo mật, sửa lỗi và kỹ thuật nền | Ghi nhận cả giá trị giảm rủi ro và điều kiện giao sản phẩm |
| “Ưu tiên là chọn việc dễ và nhiều story point.” | Output tăng nhưng outcome có thể đứng yên | Đánh giá giá trị, bằng chứng, rủi ro và chi phí cơ hội |
| “Chỉ Product Owner mới được hỏi vì sao làm việc này.” | Developers, QA thiếu bối cảnh để đề xuất giải pháp tốt | Cả nhóm cùng hiểu mục tiêu; PO chịu trách nhiệm backlog hiệu quả |
| “Product Goal chính là danh sách feature trên roadmap.” | Nhóm không có tiêu chí kiểm chứng giá trị | Phát biểu trạng thái tương lai, đo hành vi và điều chỉnh giải pháp |
| “Sprint Goal phải bằng tổng mọi ticket đã chọn.” | Mất khả năng thương lượng phạm vi khi học được điều mới | Dùng Sprint Goal làm kết quả gắn kết, phân biệt với kế hoạch chi tiết |
| “Demo thành công nghĩa là người dùng sẽ dùng.” | Đánh đồng phần mềm chạy đúng với giá trị thật | Quan sát hành vi người dùng và tín hiệu bảo vệ |
| “PBI càng chi tiết từ đầu càng chuyên nghiệp.” | Tốn công với việc chưa chắc sẽ làm, dễ lỗi thời | Làm rõ theo độ gần và mức rủi ro; chia nhỏ khi cần |
| “Điểm RICE/WSJF cao nhất luôn phải làm trước.” | Bỏ qua sai số ước lượng và ràng buộc khó định lượng | Dùng mô hình như đầu vào cho trao đổi có trách nhiệm |
| “Đã đưa vào backlog thì phải làm cho hết.” | Tiếp tục đầu tư vào giả thuyết đã lỗi thời | Loại bỏ, sắp xếp lại hoặc đổi hướng khi có bằng chứng mới |
| “Cycle time thấp đồng nghĩa khách hàng hài lòng.” | Nhóm có thể hoàn thành nhanh việc ít giá trị | Kết hợp số liệu dòng công việc với outcome và chất lượng |

## 16. Bài tập thực hành

### Bài tập 1 — Từ Product Goal đến PBI

Một ứng dụng quản lý chi tiêu có Product Goal: **“Người dùng mới tạo được ngân sách tháng đầu tiên một cách tự tin và ít lỗi.”**

Nhóm nhận ba phản hồi:

- Người dùng không hiểu sự khác nhau giữa “hạn mức” và “số dư”.
- Một số ngân sách không được lưu khi mất kết nối.
- Bộ phận marketing muốn thêm bảng xếp hạng người chi tiêu tiết kiệm nhất.

**Yêu cầu:** viết hai PBI ưu tiên kèm mục tiêu liên quan, vấn đề, giả thuyết và cách kiểm chứng; giải thích vì sao đề xuất thứ ba có thể cần nghiên cứu thêm.

**Gợi ý:** sửa lỗi mất dữ liệu và làm rõ từ ngữ có liên hệ trực tiếp mục tiêu; bảng xếp hạng có thể hữu ích nhưng chưa được chứng minh giúp người mới tạo ngân sách đúng.

### Bài tập 2 — Phân biệt output và outcome

Một Sprint hoàn thành 15 PBI và tăng velocity từ 30 lên 45 story point. Tỷ lệ người học hoàn thành bài đầu trong bảy ngày vẫn là 25%; lỗi lưu tiến độ tăng.

**Yêu cầu:**

1. Điều gì chắc chắn là **output**?
2. Có bằng chứng nào cho thấy **outcome** đã cải thiện không?
3. Những câu hỏi nào cần kiểm tra trước khi kết luận Sprint thành công hay thất bại?
4. Chọn một PBI nên cân nhắc ưu tiên lại và giải thích.

**Gợi ý:** story point và PBI hoàn thành không phải thước đo trực tiếp giá trị. Cần xem điều nào đã đạt DoD, mức lỗi, phạm vi người dùng, độ tin cậy phép đo và nguyên nhân bỏ dở.

### Bài tập 3 — Viết user story và acceptance criteria

Product Goal: **“Người đặt lịch khám có thể nhận biết và hoàn tất bước xác nhận lịch rõ ràng.”**

Vấn đề: người dùng bấm xác nhận nhưng không biết lịch đã được ghi nhận hay chưa; một số người bấm nhiều lần.

**Yêu cầu:** viết một user story, ba acceptance criteria gồm trường hợp thành công, yêu cầu lặp và khi hệ thống gặp lỗi. Sau đó nêu **một chỉ số outcome** và **hai tín hiệu bảo vệ**.

**Gợi ý:** tiêu chí phải xác định hành vi có thể kiểm chứng; bảo vệ khỏi việc tạo lịch trùng hoặc báo thành công khi chưa có kết quả. Không tự áp đặt chính sách nghiệp vụ chưa được xác nhận.

### Bài tập 4 — Lựa chọn giữa tính năng, nghiên cứu và sửa lỗi

Một nhóm có mục tiêu giảm bỏ dở thanh toán. Có ba đề xuất: thêm ví điện tử mới, phỏng vấn người dùng bỏ dở, sửa lỗi hiển thị tổng tiền trên thiết bị di động.

**Yêu cầu:** lập bảng so sánh về **liên hệ mục tiêu, bằng chứng, rủi ro nếu hoãn, chi phí và thông tin chưa biết**. Đề xuất cách ưu tiên có điều kiện và một phép thử nhỏ.

**Gợi ý:** nếu lỗi hiển thị tổng tiền gây ra giao dịch sai, cần xử lý rủi ro trước; nếu nguyên nhân bỏ dở chưa rõ, nghiên cứu có thể đáng làm trước khi xây kênh thanh toán mới.

### Bài tập 5 — Viết thẻ liên kết mục tiêu cho dự án thực tế

Chọn một PBI trong dự án của bạn và điền mẫu:

~~~text
Product Goal / trạng thái tương lai:
Người dùng hay hệ thống chịu ảnh hưởng:
Vấn đề hoặc cơ hội:
Bằng chứng hiện có và điều chưa biết:
Giả thuyết PBI sẽ tạo giá trị bằng cách:
Phạm vi lát cắt nhỏ nhất hữu ích:
Acceptance criteria / DoD liên quan:
Outcome cần quan sát:
Tín hiệu sớm và tín hiệu bảo vệ:
Chi phí/rủi ro và phụ thuộc:
Việc có thể hoãn nếu chọn PBI này:
Điểm xem lại kết quả và quyết định tiếp theo:
~~~

**Tự đánh giá:** nếu một người mới đọc PBI, họ có thể hiểu **vì sao nó được ưu tiên**, **nó giúp Product Goal như thế nào** và **điều gì sẽ khiến nhóm thay đổi quyết định** hay không?

## 17. Tổng kết

Liên kết hạng mục với mục tiêu sản phẩm giúp Product Backlog trở thành **công cụ định hướng quyết định** thay vì kho tích trữ yêu cầu.

Hãy ghi nhớ:

1. **Bắt đầu từ Product Goal và vấn đề người dùng**, không bắt đầu từ danh sách tính năng muốn xây.
2. **Nối PBI với cơ chế tạo giá trị hoặc giảm rủi ro**: hạng mục phải có lý do đủ rõ, kể cả khi đó là lỗi, khám phá hay công việc kỹ thuật.
3. **Phân biệt output và outcome**: giao Increment đạt DoD là cần thiết; phản hồi và dữ liệu giúp biết giải pháp có hữu ích không.
4. **Ưu tiên dựa trên bằng chứng và đánh đổi**: giá trị kỳ vọng, độ chắc chắn, hậu quả nếu hoãn, phụ thuộc và khả năng hoàn tất đều quan trọng.
5. **Giao theo lát cắt nhỏ để học sớm**: user story, acceptance criteria và kiểm thử giúp tạo phần mềm đáng tin; đo outcome giúp cập nhật backlog.
6. **Dùng Scrum, Kanban và XP theo mục đích**: Scrum liên kết mục tiêu và các vòng kiểm tra; Kanban giúp quản lý luồng; XP hỗ trợ thay đổi kỹ thuật an toàn.
7. **Sẵn sàng sắp xếp lại** khi mục tiêu, bối cảnh hoặc bằng chứng đổi; không coi các PBI đã được ghi vào backlog là lời hứa phải thực hiện tất cả.

> **Câu hỏi ghi nhớ:** “Nếu bỏ hạng mục này khỏi Product Backlog, kết quả quan trọng nào của sản phẩm sẽ khó đạt hơn, rủi ro nào sẽ tăng, hoặc cơ hội học hỏi nào sẽ mất đi?”

### Tài liệu tham khảo

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — giao giá trị sớm, hợp tác với khách hàng, thích ứng và cải tiến liên tục.
- [The Scrum Guide](https://scrumguides.org/scrum-guide.html) — Product Goal, Product Backlog, Product Owner, Sprint Goal, Increment và Definition of Done.
- [The Kanban Guide](https://kanbanguides.org/) — quản lý công việc đang thực hiện, dòng công việc và những phép đo WIP, throughput, work item age, cycle time.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — kỹ thuật hỗ trợ giao phần mềm tăng dần và phản hồi sớm.
