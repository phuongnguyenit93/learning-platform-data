# Thẻ ghi, trao đổi và xác nhận trong mô hình 3C

## 1. Mô hình 3C giải quyết vấn đề gì?

Trong phát triển phần mềm Agile, **user story** là cách ngắn gọn để diễn đạt một nhu cầu có ý nghĩa của người sử dụng hoặc một bên hưởng lợi từ sản phẩm. User story giúp nhóm thảo luận về **ai cần điều gì, vì sao điều đó có giá trị**, rồi cùng tìm cách cung cấp một phần sản phẩm có thể kiểm chứng.

Một câu user story viết tốt **không tự động trở thành yêu cầu đã được hiểu đầy đủ**. Cùng một câu “người học muốn lưu khóa học yêu thích” có thể dẫn đến những cách hiểu rất khác nhau: lưu trên một thiết bị hay nhiều thiết bị, có cần đăng nhập không, có được lưu trùng không, người khác có thấy danh sách không, có cần thông báo xác nhận không?

Mô hình **3C** giúp nhóm xử lý khoảng cách giữa **ý tưởng ban đầu** và **hiểu biết chung đủ để triển khai, kiểm tra**:

1. **Card — Thẻ ghi:** Ghi ngắn gọn nhu cầu và giá trị, đủ để gợi mở cuộc trao đổi.
2. **Conversation — Trao đổi:** Những người liên quan cùng khám phá bối cảnh, quy tắc, lựa chọn, ví dụ và các điểm chưa rõ.
3. **Confirmation — Xác nhận:** Thống nhất những điều kiện và ví dụ có thể kiểm chứng để biết giải pháp đáp ứng nhu cầu đến mức cần thiết.

Ba chữ C là **ba khía cạnh hỗ trợ nhau**, không phải một quy trình cứng bắt buộc xong Card mới được Conversation, rồi hoàn tất Confirmation một lần duy nhất. Cuộc trao đổi có thể khiến thẻ được viết lại; khi tạo ví dụ xác nhận, nhóm có thể phát hiện câu hỏi mới và quay lại thảo luận.

Trong module **AGILE_DEVELOPMENT**, 3C giúp nối các giá trị Agile như cộng tác, phản hồi sớm và thích ứng với thực hành **user story, product backlog, Scrum, Kanban, XP**. Mục đích cuối cùng không phải điền đủ mẫu, mà là giảm hiểu nhầm, giao phần tăng dần có giá trị và tiếp tục học từ sử dụng thực tế.

## 2. Nhìn tổng thể ba chữ C

| Thành phần | Câu hỏi trọng tâm | Dấu vết điển hình | Rủi ro khi thiếu |
| --- | --- | --- | --- |
| **Card — Thẻ ghi** | Ai cần gì và vì sao? | Một câu user story, tiêu đề, bối cảnh và liên kết cần thiết | Không có điểm tham chiếu chung cho nhu cầu |
| **Conversation — Trao đổi** | Tình huống thực tế, ngoại lệ và cách giải quyết là gì? | Cuộc trao đổi, câu hỏi và quyết định được ghi lại | Mỗi người tự suy đoán yêu cầu |
| **Confirmation — Xác nhận** | Dấu hiệu nào chứng minh story đáp ứng điều đã thống nhất? | Tiêu chí chấp nhận, ví dụ cụ thể, kiểm thử chấp nhận | Không rõ khi nào hành vi đúng, dễ nghiệm thu theo cảm tính |

~~~mermaid
flowchart LR
    A["Card: Nhu cầu và giá trị"] --> B["Conversation: Khám phá và hiểu chung"]
    B --> C["Confirmation: Ví dụ và tiêu chí kiểm chứng"]
    C --> D["Triển khai, kiểm thử và nhận phản hồi"]
    C -->|"Phát hiện tình huống chưa rõ"| B
    B -->|"Cần làm rõ hoặc chia nhỏ"| A
    D -->|"Học được điều mới"| A
~~~

Sơ đồ cho thấy thông tin có thể quay lại bất kỳ khía cạnh nào. **Card thường ngắn, Conversation thường phong phú, Confirmation thường cụ thể.** Một thẻ dài vài trang vẫn không thể thay thế hoàn toàn cuộc trao đổi; một cuộc họp sôi nổi cũng chưa bảo đảm hai bên có cùng cách kiểm chứng kết quả.

## 3. C thứ nhất: Card — thẻ ghi nhu cầu

### 3.1. Thẻ ghi là lời nhắc trao đổi

Thẻ user story thường được viết theo dạng:

> **Là** [vai trò/người hưởng lợi], **tôi muốn** [khả năng hoặc kết quả], **để** [mục đích/giá trị].

Ví dụ cho nền tảng học trực tuyến:

> **Là** người học đã đăng nhập, **tôi muốn** lưu một khóa học vào danh sách yêu thích, **để** dễ tìm lại khóa đó khi quyết định đăng ký.

Cấu trúc này giúp làm rõ **người dùng — nhu cầu — lý do**, nhưng **không phải cú pháp bắt buộc**. Nếu một cách viết ngắn khác truyền đạt rõ giá trị hơn, nhóm có thể sử dụng. Cũng không phải tất cả hạng mục backlog đều nhất thiết phải được viết như user story; lỗi kỹ thuật, công việc giảm rủi ro hay nghiên cứu có thể cần mô tả phù hợp mục đích riêng.

Card nên **đủ ngắn để được đọc**, nhưng **đủ thông tin để cả nhóm biết cần thảo luận chuyện gì**. Có thể đính kèm liên kết đến thiết kế, nghiên cứu người dùng, quyết định cũ hoặc dữ liệu sử dụng; không cần nhét toàn bộ nội dung đó vào một câu.

### 3.2. Phân biệt nhu cầu người dùng với giải pháp kỹ thuật

| Cách ghi chưa phù hợp | Vấn đề | Cách hướng đến nhu cầu |
| --- | --- | --- |
| “Tạo bảng favorite_courses và API POST /favorites.” | Mô tả công việc kỹ thuật, chưa nói ai được lợi và vì sao | “Người học muốn lưu khóa để xem lại khi cần.” |
| “Thêm icon trái tim màu đỏ ở góc trên.” | Ấn định thiết kế khi chưa hiểu bối cảnh | “Người học muốn nhận ra cách lưu và trạng thái đã lưu của khóa.” |
| “Làm module bookmark hoàn chỉnh.” | Phạm vi mơ hồ, có thể quá lớn | “Người học đã đăng nhập lưu và tìm lại một khóa quan tâm.” |
| “Cải thiện trải nghiệm người học.” | Quá rộng, khó biết điều gì hoàn thành | “Người học mới phân biệt được trình độ khóa trước khi đăng ký.” |

Điều này không có nghĩa phải cấm nhắc đến giải pháp. Nếu một ràng buộc công nghệ đã được xác nhận hoặc nhóm đang làm công việc hạ tầng, có thể ghi rõ. Nhưng **đối với user story, hãy bắt đầu bằng giá trị và tình huống sử dụng** để không khóa phương án quá sớm.

### 3.3. Những điều nên biết khi đọc Card

Một thẻ có thể có thêm:

- **Tên ngắn:** “Lưu khóa học yêu thích”.
- **Câu story:** Vai trò, khả năng, giá trị.
- **Bối cảnh:** Phản hồi cho thấy người học thường phải tìm lại khóa đã xem.
- **Giới hạn ban đầu:** Chỉ xem xét người học đã đăng nhập, chưa quyết định cách xử lý người dùng khách.
- **Mối liên hệ:** Mục tiêu sản phẩm và hạng mục backlog liên quan.
- **Câu hỏi mở:** Danh sách phải lưu qua các phiên đăng nhập không? Có thể xóa khỏi danh sách không?

Không nên coi mọi thông tin ghi trên thẻ là sự thật đã được xác nhận. Hãy ghi rõ đâu là **giả thuyết**, đâu là **quy tắc đã thống nhất**. Ví dụ “Người học muốn đồng bộ danh sách giữa điện thoại và máy tính” là giả thuyết cần kiểm chứng nếu nhóm chưa có bằng chứng.

### 3.4. Kiểm tra nhanh bằng INVEST

INVEST là gợi ý để đánh giá chất lượng user story, đặc biệt khi cần chọn hạng mục đủ nhỏ cho một đợt thực hiện:

| Chữ | Ý nghĩa | Câu hỏi đối với thẻ “Lưu khóa học” |
| --- | --- | --- |
| **I — Independent** | Tương đối độc lập | Có thể giao giá trị mà không phải hoàn thành nhiều khả năng không liên quan trước không? |
| **N — Negotiable** | Có thể trao đổi, thương lượng | Nhóm còn không gian chọn giải pháp và phạm vi phù hợp không? |
| **V — Valuable** | Có giá trị | Người học được lợi gì khi lưu khóa? |
| **E — Estimable** | Có thể ước lượng ở mức hợp lý | Đã hiểu đủ tình huống chính và phụ thuộc để trao đổi độ phức tạp chưa? |
| **S — Small** | Đủ nhỏ | Có thể tách khả năng cơ bản khỏi thông báo hay sắp xếp danh sách nâng cao không? |
| **T — Testable** | Có thể kiểm chứng | Có thể cho thấy một khóa được lưu và tìm lại thành công không? |

INVEST là công cụ tư duy, không phải danh sách “đạt/không đạt” cứng nhắc. Story có thể có phụ thuộc thực tế; điều quan trọng là **nhìn thấy phụ thuộc và giảm chúng khi khả thi**. Đừng dành quá nhiều thời gian chấm điểm một tấm thẻ mà quên trao đổi về nhu cầu thật.

## 4. C thứ hai: Conversation — cùng khám phá để hiểu đúng

Card tạo điểm bắt đầu; **Conversation mới hình thành hiểu biết chung**. Trao đổi có thể xảy ra khi làm rõ backlog, trước khi bắt đầu thực hiện, trong khi phát triển, lúc kiểm thử hoặc khi xem phản hồi người dùng.

Những người tham gia tùy bối cảnh:

- **Product Owner hoặc đại diện có trách nhiệm về sản phẩm:** Làm rõ giá trị, thứ tự ưu tiên và quy tắc nghiệp vụ hoặc kết nối người có thể trả lời.
- **Người phát triển:** Đặt câu hỏi về luồng chính, ngoại lệ, dữ liệu, tích hợp, tính khả thi và các đánh đổi.
- **Người kiểm thử/chuyên gia chất lượng:** Gợi mở ví dụ phản chứng, điều kiện lỗi, cách quan sát kết quả và rủi ro.
- **Người dùng, đại diện vận hành, thiết kế hoặc chuyên gia lĩnh vực:** Bổ sung bối cảnh, hành vi thực tế và những giới hạn cần tuân thủ.

Một cuộc trao đổi ngắn giữa **nghiệp vụ, phát triển và kiểm thử** thường được gọi là cách cộng tác “Three Amigos”. Không phải lúc nào cũng cần đúng ba người hoặc đúng ba chức danh; cốt lõi là có các góc nhìn cần thiết. Nếu không ai trong nhóm biết quy định liên quan đến dữ liệu cá nhân, cần tìm đúng người có thẩm quyền thay vì tự bịa quy tắc.

### 4.1. Từ một câu story đến những câu hỏi cần giải đáp

Với story “Lưu khóa học yêu thích”, có thể hỏi:

| Nhóm câu hỏi | Câu hỏi minh họa | Ý nghĩa |
| --- | --- | --- |
| **Người dùng** | Có bắt buộc đăng nhập trước khi lưu không? | Xác định người được phép và điều kiện bắt đầu |
| **Hành vi chính** | Sau khi bấm Lưu, người học thấy trạng thái nào? | Kiểm chứng cách người dùng biết thao tác đã thành công |
| **Lưu trữ** | Đăng nhập lại hoặc dùng thiết bị khác có thấy khóa đã lưu không? | Làm rõ độ bền và phạm vi dữ liệu |
| **Trùng lặp** | Bấm Lưu nhiều lần có tạo nhiều mục giống nhau không? | Làm rõ tính nhất quán hành vi |
| **Quyền riêng tư** | Người học A có thể thấy danh sách của người học B không? | Xác định giới hạn truy cập |
| **Ngoại lệ** | Nếu mất kết nối hoặc dịch vụ lưu thất bại, giao diện phải làm gì? | Tránh báo thành công sai |
| **Phạm vi** | Xóa khỏi danh sách, sắp xếp, chia sẻ thuộc story này hay story khác? | Giữ phần giao đủ nhỏ để kiểm chứng |
| **Kết quả cần đạt** | Làm sao biết việc lưu giúp người học quay lại khóa dễ hơn? | Nối hành vi với giá trị sản phẩm |

Thảo luận nên đi từ **tình huống người dùng** đến **quy tắc**, rồi mới đến **chi tiết kỹ thuật**. Một câu hỏi có thể dẫn tới lựa chọn khác nhau tùy mục tiêu sản phẩm. Chẳng hạn, lưu tạm trên trình duyệt không đáp ứng nhu cầu truy cập đa thiết bị; nhưng nếu sản phẩm chỉ chạy cục bộ và không yêu cầu đồng bộ, quy tắc có thể khác.

### 4.2. Minh họa đoạn Conversation

> **Product Owner:** “Nhiều người học xem khóa rồi chưa đăng ký ngay. Họ muốn trở lại khóa đã quan tâm mà không phải tìm lại.”  
> **Developer:** “Người học cần đăng nhập để lưu không? Hay cho khách lưu cục bộ?”  
> **Product Owner:** “Đợt đầu chỉ phục vụ người đã đăng nhập. Trường hợp khách sẽ xem xét sau.”  
> **Tester:** “Nếu người học lưu hai lần, danh sách có hai mục không?”  
> **Product Owner:** “Không. Một khóa chỉ xuất hiện một lần trong danh sách của cùng người học.”  
> **Developer:** “Danh sách được giữ khi người học đăng nhập lại trên thiết bị khác chứ?”  
> **Product Owner:** “Có, đó là mục đích chính. Danh sách gắn với tài khoản.”  
> **Tester:** “Nếu lưu thất bại vì mất mạng, giao diện có đổi sang ‘Đã lưu’ không?”  
> **Product Owner:** “Không. Cần thông báo thất bại và cho phép thử lại.”  
> **Developer:** “Xóa khỏi yêu thích có nằm trong phần giao đầu tiên không?”  
> **Product Owner:** “Có, người học cần bỏ những khóa không còn quan tâm. Nhưng chia sẻ danh sách và sắp xếp tùy chọn để sau.”  

Cuộc trao đổi đã giúp **xác định phạm vi, quy tắc dữ liệu và tình huống lỗi**. Quan trọng hơn, cả nhóm hiểu tại sao phải giữ danh sách qua phiên đăng nhập: đó là một phần giá trị người học cần nhận, không phải chi tiết kỹ thuật tùy chọn.

### 4.3. Ghi lại quyết định có ích sau trao đổi

Không cần lưu nguyên văn mọi cuộc họp. Nên ghi những quyết định ảnh hưởng đến hành vi, phạm vi hoặc kiểm thử:

| Nội dung | Kết luận ví dụ |
| --- | --- |
| Đối tượng | Người học đã xác thực |
| Giá trị | Lưu để xem lại trước khi đăng ký |
| Hành vi chính | Lưu và mở danh sách yêu thích của mình |
| Hành vi điều chỉnh | Có thể bỏ lưu; cùng khóa không xuất hiện nhiều lần |
| Tính bền | Dữ liệu theo tài khoản và còn sau khi đăng nhập lại |
| Quyền truy cập | Người học chỉ thao tác trên danh sách của bản thân |
| Lỗi lưu | Không báo thành công nếu hệ thống chưa xác nhận; có cách thử lại |
| Ngoài phạm vi | Chia sẻ, gắn thẻ hoặc sắp xếp tùy chỉnh |
| Cần xác minh thêm | Cách đo việc người học quay lại khóa đã lưu |

Đây là **quyết định ví dụ trong bài học**, không phải quy tắc chung cho mọi sản phẩm. Nếu bối cảnh khác, các kết luận cần thay đổi theo trao đổi thật.

### 4.4. Kỹ thuật làm Conversation hiệu quả

1. **Dùng ví dụ cụ thể:** “Nếu lưu một khóa hai lần thì sao?” rõ hơn “Hệ thống phải ổn định”.
2. **Hỏi về trường hợp khác biệt:** Người mới, người quay lại, dữ liệu rỗng, mất mạng, thao tác lặp, không đủ quyền.
3. **Tách nhu cầu khỏi đề xuất giải pháp:** “Muốn tìm lại nhanh” khác với “Phải dùng biểu tượng trái tim”.
4. **Hỏi điều không làm:** Chia sẻ danh sách có cần trong đợt này không?
5. **Nêu rủi ro và đánh đổi:** Có cần đồng bộ đa thiết bị ngay hay giao giá trị nhỏ hơn trước?
6. **Ghi lại điều đã quyết và còn mở:** Tránh mỗi thành viên mang về một cách hiểu khác nhau.
7. **Quay lại người dùng khi cần:** Những giả thuyết về hành vi nên được kiểm tra bằng quan sát, phản hồi hoặc dữ liệu thực tế.

Cuộc trao đổi tốt tạo ra **hiểu biết có thể hành động**, không nhất thiết phải kéo dài. Đừng xem story “đã nói qua trong họp” là đủ nếu những quy tắc quan trọng vẫn đang được suy đoán.

## 5. C thứ ba: Confirmation — xác nhận bằng tiêu chí và ví dụ

**Confirmation** thể hiện sự thống nhất về cách nhận biết kết quả đúng. Nó thường gồm **acceptance criteria (tiêu chí chấp nhận)** và **ví dụ chấp nhận** để nhóm cùng triển khai, kiểm thử và kiểm tra hành vi sản phẩm.

Confirmation **không chỉ là chữ ký nghiệm thu cuối dự án**. Những tiêu chí được thảo luận sớm giúp tránh xây sai và làm rõ yêu cầu trong khi còn dễ thay đổi. Confirmation cũng không đồng nghĩa với việc khách hàng chỉ cần nói “trông ổn” sau buổi demo.

### 5.1. Tiêu chí chấp nhận cần cụ thể tới mức nào?

Một tiêu chí tốt nên:

- Gắn với **hành vi có thể quan sát** hoặc quy tắc nghiệp vụ có thể kiểm tra.
- Nêu rõ **điều kiện**, **hành động** và **kết quả** khi có ý nghĩa.
- Có thể cho kết quả đạt/chưa đạt trong một bối cảnh xác định.
- Bao quát luồng chính và những trường hợp lỗi quan trọng đã xác định.
- Không ràng buộc quá mức chi tiết triển khai nội bộ nếu người dùng không cần đến.
- Giữ đủ ngắn để đọc, nhưng bổ sung ví dụ khi câu chữ dễ gây hiểu nhầm.

Ví dụ tiêu chí mơ hồ:

> “Hệ thống lưu yêu thích nhanh, dễ dùng, hoạt động đúng.”

Ví dụ rõ hơn:

> “Khi người học đã đăng nhập lưu một khóa hợp lệ, hệ thống xác nhận kết quả và khóa đó xuất hiện một lần trong danh sách yêu thích của tài khoản; danh sách vẫn có khóa này sau khi đăng xuất và đăng nhập lại.”

Nếu tốc độ phản hồi là yêu cầu quan trọng, cần làm rõ **ngưỡng, điều kiện đo và ai phê duyệt**. Không tự đặt một ngưỡng “dưới 1 giây” rồi coi đó là yêu cầu sản phẩm nếu chưa có bối cảnh hoặc thỏa thuận.

### 5.2. Bộ tiêu chí chấp nhận cho story xuyên suốt

Sau Conversation ở trên, nhóm có thể thống nhất:

| Mã | Tiêu chí | Kết quả cần kiểm chứng |
| --- | --- | --- |
| **AC-01** | Lưu thành công | Người học đã đăng nhập lưu khóa hợp lệ; nhận trạng thái thành công và thấy khóa trong danh sách của mình |
| **AC-02** | Không trùng | Thực hiện lưu nhiều lần cùng khóa không tạo nhiều bản ghi hiển thị cho cùng tài khoản |
| **AC-03** | Giữ qua phiên | Sau khi đăng xuất rồi đăng nhập lại, khóa đã lưu vẫn có trong danh sách tài khoản |
| **AC-04** | Quyền truy cập | Người học khác không xem hoặc sửa được danh sách riêng của chủ tài khoản |
| **AC-05** | Thao tác bỏ lưu | Bỏ lưu một khóa thành công khiến khóa không còn trong danh sách của tài khoản |
| **AC-06** | Xử lý lỗi | Khi hệ thống không lưu được, không hiển thị trạng thái thành công giả và người học được thông báo để thử lại |

Đây là bộ tiêu chí minh họa; sản phẩm thật có thể cần bổ sung điều kiện về khóa đã bị xóa, quyền truy cập vào nội dung khóa, thiết bị mục tiêu, khả năng tiếp cận hoặc các yêu cầu vận hành. Những yêu cầu đó nên được trao đổi và xử lý theo rủi ro, tránh đưa mọi tình huống có thể tưởng tượng vào một story khiến nó quá lớn.

### 5.3. Gherkin: Given – When – Then

Một cách diễn đạt ví dụ chấp nhận là cấu trúc **Given – When – Then**:

- **Given (Cho trước):** Bối cảnh hoặc trạng thái ban đầu.
- **When (Khi):** Hành động hoặc sự kiện.
- **Then (Thì):** Kết quả quan sát được.

Ví dụ các tình huống xác nhận cho **AC-01, AC-02, AC-03, AC-06**:

~~~gherkin
Tính năng: Lưu khóa học yêu thích

  Tình huống: Lưu một khóa học thành công
    Cho trước người học An đã đăng nhập
    Và khóa "Java cơ bản" đang có thể xem
    Và An chưa lưu khóa này
    Khi An chọn lưu khóa "Java cơ bản"
    Thì hệ thống xác nhận lưu thành công
    Và danh sách yêu thích của An có khóa "Java cơ bản"

  Tình huống: Lưu lặp lại không tạo mục trùng
    Cho trước An đã đăng nhập
    Và An đã lưu khóa "Java cơ bản"
    Khi yêu cầu lưu khóa "Java cơ bản" được gửi thêm một lần
    Thì danh sách yêu thích của An chỉ có một mục cho khóa đó

  Tình huống: Khóa đã lưu còn sau khi đăng nhập lại
    Cho trước An đã lưu khóa "Java cơ bản" trong tài khoản
    Khi An đăng xuất rồi đăng nhập lại tài khoản của mình
    Thì An vẫn tìm thấy khóa "Java cơ bản" trong danh sách yêu thích

  Tình huống: Không báo lưu thành công khi lưu thất bại
    Cho trước An đã đăng nhập
    Và yêu cầu lưu hiện không thể hoàn thành do lỗi dịch vụ
    Khi An chọn lưu khóa "Java cơ bản"
    Thì giao diện thông báo rằng chưa thể lưu
    Và không xác nhận khóa đã được lưu thành công
~~~

Trong dự án thực tế, nhóm có thể viết bằng tiếng Việt, tiếng Anh hoặc công cụ khác, miễn ví dụ nhất quán và dễ trao đổi. Gherkin hữu ích để thống nhất hành vi; **viết theo cú pháp Given–When–Then không tự động biến văn bản thành kiểm thử chạy được**. Muốn tự động hóa cần có phần triển khai kiểm thử, dữ liệu, môi trường và cơ chế xác minh phù hợp.

### 5.4. Kiểm tra trường hợp không được phép

Để xác nhận **AC-04**, cần kiểm tra hành vi bảo vệ quyền truy cập chứ không chỉ ẩn nút khỏi giao diện:

~~~gherkin
Tình huống: Người học khác không truy cập được danh sách riêng
  Cho trước An và Bình là hai tài khoản khác nhau
  Và An đã lưu khóa "Java cơ bản" vào danh sách riêng
  Khi Bình cố truy cập dữ liệu yêu thích thuộc tài khoản An
  Thì hệ thống từ chối truy cập theo cơ chế phân quyền đã thống nhất
  Và không tiết lộ danh sách riêng của An
~~~

Tình huống này cần được kiểm tra cả ở nơi thực thi quyền trên máy chủ hoặc tầng dịch vụ liên quan, không chỉ ở việc giao diện có hiển thị nút hay không. Chi tiết phản hồi HTTP, nội dung thông báo và cách ghi log phụ thuộc tiêu chuẩn bảo mật của hệ thống.

### 5.5. Confirmation khác Definition of Done như thế nào?

| Nội dung | Acceptance criteria / Confirmation | Definition of Done (DoD) |
| --- | --- | --- |
| **Mục tiêu** | Xác nhận hành vi riêng của một story đáp ứng nhu cầu | Xác định chuẩn chất lượng chung để công việc trở thành Increment hoàn tất |
| **Phạm vi** | Quy tắc, ví dụ và kết quả đặc thù của story | Chuẩn áp dụng cho các hạng mục/Increment thuộc phạm vi DoD |
| **Ví dụ** | Lưu yêu thích không trùng, chỉ chủ tài khoản truy cập | Kiểm thử cần thiết chạy thành công, tích hợp, đáp ứng chuẩn chất lượng liên quan |
| **Ai tham gia** | Cùng trao đổi giữa người hiểu nghiệp vụ và người xây/kiểm thử | Được xác lập, áp dụng và duy trì theo trách nhiệm của nhóm và tổ chức |
| **Kết quả** | Biết story thể hiện đúng điều đã thống nhất không | Biết công việc có đáp ứng tiêu chuẩn hoàn tất để nằm trong Increment không |

Một story có thể **đạt toàn bộ acceptance criteria nhưng vẫn chưa Done** nếu kiểm thử hồi quy bắt buộc thất bại hoặc chưa tích hợp theo DoD. Ngược lại, không nên tuyên bố story đáp ứng nhu cầu chỉ vì pipeline kỹ thuật xanh trong khi hành vi nghiệp vụ chưa được xác nhận.

Tùy mô hình hợp đồng, còn có hoạt động nghiệm thu thương mại hoặc phê duyệt phát hành với thẩm quyền riêng. Confirmation trong 3C **không mặc định thay thế** các thủ tục đó.

## 6. 3C được vận dụng trong vòng đời một user story ra sao?

3C có thể diễn ra nhiều lần khi nhóm học thêm thông tin:

| Thời điểm | Card | Conversation | Confirmation |
| --- | --- | --- | --- |
| **Khám phá nhu cầu** | Viết ý tưởng và giá trị ban đầu | Trao đổi với người dùng, bên nghiệp vụ về vấn đề | Phác thảo tín hiệu thành công và ví dụ ban đầu |
| **Làm rõ backlog** | Điều chỉnh, chia nhỏ hoặc nối các story | Xác định phạm vi, ngoại lệ, rủi ro, phụ thuộc | Chốt tiêu chí quan trọng đủ để trao đổi độ lớn và ưu tiên |
| **Trước và trong thực hiện** | Giữ story và liên kết liên quan dễ tìm | Hỏi ngay khi gặp tình huống chưa rõ, làm rõ đánh đổi | Bổ sung ví dụ và kiểm thử theo quyết định đã thống nhất |
| **Khi kiểm tra và hoàn tất** | Đối chiếu mục đích ban đầu | Làm rõ sai khác giữa kết quả thực tế và kỳ vọng | Chạy ví dụ kiểm thử, xác nhận tiêu chí và DoD |
| **Sau khi đưa vào sử dụng** | Tạo hoặc cập nhật hạng mục nếu có nhu cầu mới | Cùng xem phản hồi người dùng và kết quả vận hành | Xác nhận mục tiêu sử dụng có đạt không, tạo giả thuyết mới nếu cần |

Ví dụ: Sau khi giao khả năng lưu yêu thích, dữ liệu cho thấy người học vẫn khó tìm lại khóa đã lưu. Nhóm cần trao đổi xem danh sách có khó thấy hay người học chưa biết tính năng tồn tại. Kết quả có thể là **một story cải thiện điều hướng**, thay vì cố thêm vô số acceptance criteria vào story đã hoàn tất.

### 6.1. Xử lý story quá lớn qua Conversation

Một thẻ ban đầu có thể là:

> “Là người học, tôi muốn quản lý danh sách yêu thích để có thể lưu, tìm kiếm, sắp xếp, chia sẻ, nhận thông báo và đăng ký các khóa quan tâm.”

Story này gộp nhiều mục tiêu và dễ kéo dài. Sau trao đổi, có thể tách:

1. **Lưu và xem lại khóa yêu thích** cho người học đã đăng nhập.
2. **Bỏ lưu khóa** nếu cần tách để giữ phần đầu đủ nhỏ, theo quyết định sản phẩm.
3. **Lọc hoặc sắp xếp danh sách** khi số khóa lưu lớn.
4. **Chia sẻ danh sách** với điều kiện quyền riêng tư được xác định.
5. **Nhận thông báo thay đổi của khóa đã lưu**, khi đã có bằng chứng về nhu cầu.

Cách tách phụ thuộc **lát cắt giá trị sử dụng**, không đơn thuần tách giao diện, API và cơ sở dữ liệu. Mỗi phần tăng dần nên được tích hợp, kiểm chứng và mang lại hành vi có ích trong phạm vi phù hợp. Những phụ thuộc bắt buộc cần được làm rõ, không thể loại bỏ bằng cách đổi tên story.

### 6.2. 3C và backlog không phải là bộ hồ sơ bất biến

Product backlog phát triển theo điều nhóm học được. Khi có phản hồi mới, nhóm có thể:

- Viết lại Card để phản ánh đúng nhu cầu đã hiểu.
- Tiếp tục Conversation với người liên quan về rủi ro và khả năng thực hiện.
- Cập nhật Confirmation để phản ánh quyết định hợp lệ.
- Chia, gộp hoặc đổi thứ tự các hạng mục theo giá trị sản phẩm.
- Ghi điều chưa xác định làm giả thuyết hoặc công việc khám phá riêng.

Tuy vậy, nếu thay đổi một tiêu chí khi mã đã được viết, nhóm cần **minh bạch ảnh hưởng tới thời gian, chất lượng và các cam kết hiện hành**. “Agile cho phép thay đổi” không đồng nghĩa với thay đổi âm thầm hoặc hạ chuẩn khi kiểm thử chưa đạt.

## 7. Tổ chức một buổi 3C ngắn và có kết quả

Một cuộc trao đổi 3C có thể diễn ra khi làm rõ Product Backlog Item hoặc ngay trước khi nhóm bắt đầu triển khai. Tùy story, thời lượng có thể từ vài phút đến lâu hơn; đừng áp đặt một định mức cho tất cả.

**Mẫu buổi trao đổi 25 phút cho một story tương đối nhỏ:**

| Phần | Thời lượng gợi ý | Câu hỏi | Kết quả mong muốn |
| --- | ---: | --- | --- |
| **Card** | 3 phút | Người dùng nào, kết quả gì, vì sao quan trọng? | Cùng hiểu mục tiêu |
| **Bối cảnh và luồng chính** | 7 phút | Người dùng bắt đầu từ đâu, làm gì, mong chờ gì? | Phác họa ví dụ thành công |
| **Ngoại lệ và ràng buộc** | 7 phút | Dữ liệu rỗng, lỗi, quyền, trùng, hủy, thiết bị? | Phát hiện giả định và điểm chưa rõ |
| **Confirmation** | 6 phút | Ví dụ nào chứng minh đúng, ví dụ nào chứng minh sai? | Tiêu chí và ví dụ có thể kiểm tra |
| **Kết luận** | 2 phút | Còn câu hỏi mở? Có đủ nhỏ để làm? Ai quyết định? | Ghi rõ hành động tiếp theo |

Đây là ví dụ, không phải Scrum event chính thức hoặc nghĩa vụ họp 25 phút. Với story đơn giản, trao đổi trực tiếp ngắn có thể đủ; với story nhiều rủi ro, nhóm có thể chuẩn bị trước ví dụ, bản mẫu và dữ liệu rồi chia thành nhiều lượt.

### Những câu hỏi hữu ích để dẫn dắt

- **Card:** “Nếu bỏ chức năng này, ai thực sự bị ảnh hưởng và công việc nào khó hơn?”
- **Conversation:** “Có trường hợp nào chúng ta đang hiểu khác nhau không?”
- **Conversation:** “Điều gì xảy ra khi người dùng thực hiện thao tác hai lần hoặc mất kết nối?”
- **Conversation:** “Quy tắc nào là bắt buộc, quy tắc nào mới là giả thuyết?”
- **Confirmation:** “Hãy nêu một ví dụ đầu vào và kết quả đúng.”
- **Confirmation:** “Làm sao nhận ra hành vi sai dù giao diện trông có vẻ đúng?”
- **Kết thúc:** “Điều gì thuộc phần giao này, điều gì để sau, và cần hỏi ai trước khi bắt đầu?”

Sau buổi trao đổi, nhóm chỉ cần ghi lại thông tin **đủ để người tham gia và người vắng mặt cùng hiểu quyết định**, như Card đã sửa, các quy tắc chính, ví dụ chấp nhận, câu hỏi mở và người phụ trách giải đáp. Tránh ghi chép quá mức khiến tài liệu ít ai đọc.

## 8. 3C kết hợp thế nào với Scrum, Kanban và XP?

### 8.1. Trong Scrum

Scrum không quy định mọi Product Backlog Item phải có mẫu user story hoặc mô hình 3C. Tuy nhiên, 3C là cách thực hành hữu ích để làm rõ hạng mục.

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog; cộng tác với các bên liên quan để làm rõ nhu cầu và ưu tiên.
- **Developers** cần hiểu công việc đủ để tạo Increment đáp ứng Definition of Done; họ cùng trao đổi về phạm vi, cách làm, rủi ro và việc chia nhỏ.
- **Product Backlog refinement** là hoạt động liên tục để làm rõ và chia nhỏ các hạng mục; 3C có thể được dùng tại đây.
- **Sprint Planning** giúp chọn công việc và tạo kế hoạch hướng tới Sprint Goal; Conversation có thể tiếp tục nếu cần làm rõ.
- **Sprint Review** là cơ hội kiểm tra kết quả với các bên liên quan và thích ứng Product Backlog; phản hồi có thể dẫn đến story mới hoặc điều chỉnh các hạng mục.

**Confirmation không phải lời hứa rằng mọi kỳ vọng của khách hàng được hoàn thành chỉ vì Sprint kết thúc.** Tiêu chí riêng của hạng mục và Definition of Done đều cần được xem xét; quyết định phát hành và nghiệm thu thương mại có thể thuộc quy trình khác.

### 8.2. Trong Kanban

Kanban chú trọng minh bạch luồng công việc, quản lý WIP và cải tiến dòng chảy. Nhóm có thể dùng 3C trước khi kéo hạng mục vào thực hiện, trong lúc xử lý câu hỏi bị chặn và trước khi kết luận hạng mục hoàn tất.

Ví dụ, một công việc “lưu khóa yêu thích” bị chặn ở cột “Phát triển” vì chưa xác định lưu qua nhiều thiết bị hay không. Conversation ngắn với người chịu trách nhiệm sản phẩm và các vai trò liên quan giúp thống nhất quy tắc; Confirmation cập nhật ví dụ kiểm chứng, rồi công việc tiếp tục. Nhóm có thể theo dõi thời gian bị chặn để cải thiện chính sách làm rõ hạng mục.

Không cần chờ đến ngày cuối Sprint vì Kanban không bắt buộc tổ chức Sprint.

### 8.3. Trong Extreme Programming (XP)

XP khuyến khích phản hồi nhanh, các phần giao nhỏ và chất lượng kỹ thuật cao. User story có thể giúp nhóm hiểu giá trị, việc trao đổi thường xuyên với đại diện khách hàng giúp giải quyết câu hỏi nghiệp vụ, còn ví dụ chấp nhận có thể dẫn tới các **acceptance tests**.

Các thực hành như test-driven development, tích hợp liên tục và tái cấu trúc mã giúp duy trì khả năng đổi hướng khi học thêm. Tuy nhiên, **kiểm thử đơn vị không thay thế xác nhận nhu cầu**; kỹ thuật tốt chỉ phát huy giá trị khi nhóm triển khai đúng hành vi người dùng cần.

## 9. Các lỗi thường gặp khi áp dụng 3C

| Sai lầm | Điều dễ xảy ra | Cách cải thiện |
| --- | --- | --- |
| **Chỉ viết câu “Là... tôi muốn... để...”** | Nhiều trường hợp bị suy đoán, kết quả không đúng kỳ vọng | Đặt câu hỏi, bàn ví dụ và ghi Confirmation |
| **Biến Card thành tài liệu đặc tả dài bất biến** | Mất tính thương lượng, khó theo kịp phản hồi | Giữ nội dung trọng tâm; chi tiết hóa qua cuộc trao đổi và tài liệu liên kết |
| **Conversation chỉ do một vai trò độc thoại** | Bỏ sót góc nhìn kỹ thuật, kiểm thử hoặc người dùng | Mời đủ góc nhìn cần thiết, tạo cơ hội nêu câu hỏi |
| **Chỉ hỏi “khách hàng muốn gì?”** | Chấp nhận giải pháp đề xuất mà chưa hiểu vấn đề | Làm rõ mục tiêu, bối cảnh và giá trị cần đạt |
| **Chỉ xác nhận luồng thành công** | Quên quyền truy cập, trùng dữ liệu, lỗi mạng, dữ liệu rỗng | Bàn thêm trường hợp biên và rủi ro ưu tiên cao |
| **Tiêu chí mơ hồ** | Khó xác định đạt/chưa đạt | Dùng ví dụ đầu vào, hành động, kết quả |
| **Nhầm Confirmation với DoD** | Nghiệp vụ đúng nhưng chất lượng chung chưa đạt | Kiểm tra cả tiêu chí story và Definition of Done |
| **Xem Gherkin là đủ để tự động hóa** | Tài liệu đẹp nhưng thiếu kiểm thử thực thi hoặc không đáng tin | Tạo kiểm thử phù hợp, bảo trì dữ liệu và môi trường |
| **Cố đưa mọi tính năng vào một story** | Phạm vi lớn, khó ước lượng, giao trễ | Chia lát cắt giá trị và làm rõ điều để sau |
| **Không cập nhật khi trao đổi thay đổi quyết định** | Các thành viên dựa vào quy tắc cũ | Ghi lại kết luận và tác động trong backlog item |
| **Hoàn tất story nhưng không kiểm tra giá trị sử dụng** | Có chức năng nhưng không giải quyết vấn đề người dùng | Quan sát phản hồi sau khi giao, tạo hạng mục cải thiện |

Không nhất thiết mọi story phải có cùng số tiêu chí hoặc số buổi trao đổi. Nhóm nên tăng độ chi tiết với story có **rủi ro cao, dữ liệu quan trọng, nhiều ngoại lệ hoặc nhiều bên liên quan**, thay vì máy móc áp dụng một mẫu cho mọi việc.

## 10. Bài tập thực hành: hoàn thiện 3C từ một thẻ mơ hồ

Một nhóm phát triển nền tảng học trực tuyến nhận được thẻ:

> “Người học muốn lọc khóa học tốt hơn.”

Trong buổi quan sát, người học mới thường chọn nhầm khóa nâng cao vì không nhận ra điều kiện tiên quyết. Nhóm có Product Owner, Developers và người kiểm thử, nhưng hiện chưa có tiêu chí chấp nhận.

### Yêu cầu

1. Viết lại **Card** để chỉ rõ vai trò, nhu cầu và giá trị.
2. Nêu ít nhất **sáu câu hỏi Conversation**, trong đó có luồng chính, dữ liệu chưa rõ và ngoại lệ.
3. Viết **ba acceptance criteria** có thể kiểm chứng.
4. Viết một ví dụ **Given–When–Then** cho trường hợp có khóa phù hợp và một ví dụ cho trường hợp không có kết quả.
5. Chỉ ra điều gì nên để ở một story khác và đâu là giả thuyết phải kiểm tra bằng phản hồi người học.

### Gợi ý đối chiếu

**Card có thể là:**

> **Là** người mới học lập trình, **tôi muốn** lọc khóa học theo trình độ và điều kiện đầu vào, **để** nhận biết những khóa có thể bắt đầu với kiến thức hiện tại.

**Conversation có thể hỏi:**

- Trình độ gồm những mức nào và ai chịu trách nhiệm chuẩn hóa?
- Một khóa thiếu thông tin trình độ sẽ được hiển thị hoặc xử lý thế nào?
- Người học có thể chọn nhiều mức một lúc không?
- Bộ lọc áp dụng cùng với từ khóa tìm kiếm như thế nào?
- Nếu không có khóa phù hợp, giao diện thông báo và gợi ý bước tiếp theo ra sao?
- Khi chuyển trang hoặc quay lại kết quả, bộ lọc có cần giữ nguyên không?
- Nhãn trình độ có đủ nghĩa với người mới không, hay cần mô tả điều kiện tiên quyết?
- Người dùng bàn phím hoặc công nghệ hỗ trợ có thao tác được bộ lọc không?

**Confirmation có thể gồm:**

| Mã | Tiêu chí chấp nhận minh họa |
| --- | --- |
| **AC-01** | Khi chọn mức “Cơ bản”, danh sách chỉ hiển thị các khóa được đánh dấu phù hợp mức đó theo quy tắc phân loại đã thống nhất |
| **AC-02** | Khi không có khóa phù hợp, giao diện cho biết không có kết quả và cung cấp cách bỏ hoặc thay bộ lọc |
| **AC-03** | Bộ lọc đã áp dụng được thể hiện rõ, có thể thay đổi hoặc xóa bằng thao tác trên các thiết bị và phương thức nhập liệu mục tiêu |

~~~gherkin
Tính năng: Lọc khóa học theo trình độ

  Tình huống: Có khóa phù hợp mức cơ bản
    Cho trước danh mục có khóa "Java nhập môn" thuộc mức Cơ bản
    Và có khóa "Java nâng cao" thuộc mức Nâng cao
    Khi người học chọn bộ lọc trình độ "Cơ bản"
    Thì kết quả có khóa "Java nhập môn"
    Và không có khóa "Java nâng cao"

  Tình huống: Không có khóa phù hợp
    Cho trước danh mục hiện không có khóa thuộc mức "Nâng cao"
    Khi người học chọn bộ lọc trình độ "Nâng cao"
    Thì hệ thống hiển thị trạng thái không có kết quả phù hợp
    Và cung cấp cách bỏ hoặc thay đổi bộ lọc
~~~

**Điều cần để sau hoặc tiếp tục xác minh:** Gợi ý khóa cá nhân hóa bằng AI, lưu nhiều bộ lọc yêu thích, khuyến nghị lộ trình học có thể là các ý tưởng riêng. Giả thuyết “lọc theo trình độ sẽ giúp người học chọn đúng khóa hơn” cần được kiểm tra qua usability testing, dữ liệu hành trình và phản hồi sử dụng; chỉ đáp ứng AC không tự chứng minh tác động dài hạn.

## 11. Danh sách kiểm tra trước khi đưa story vào thực hiện

Hãy dùng các câu hỏi sau để đánh giá **mức sẵn sàng tương đối** của một story; đây là gợi ý cộng tác, **không phải Definition of Ready bắt buộc trong Scrum**:

1. **Card:** Vai trò hoặc người hưởng lợi và giá trị đã được mô tả đủ rõ chưa?
2. **Conversation:** Những người cần thiết đã cùng thảo luận bối cảnh và luồng chính chưa?
3. **Conversation:** Các giả định quan trọng có được ghi rõ thay vì ngầm cho là đúng không?
4. **Conversation:** Nhóm đã trao đổi ngoại lệ, phân quyền, lỗi và trường hợp dữ liệu đáng chú ý chưa?
5. **Phạm vi:** Story có đủ nhỏ để tạo một kết quả sử dụng được, hay cần chia thành các lát cắt?
6. **Confirmation:** Có ví dụ hoặc tiêu chí đủ cụ thể để kiểm tra hành vi chính và rủi ro ưu tiên cao không?
7. **Confirmation và DoD:** Cả yêu cầu đặc thù và tiêu chuẩn chất lượng chung đã được hiểu chưa?
8. **Quyết định:** Ai có thẩm quyền trả lời các câu hỏi còn mở và ai chịu trách nhiệm ưu tiên backlog?
9. **Phản hồi:** Sau khi giao, nhóm sẽ học gì từ người dùng và kiểm tra giá trị bằng cách nào?

**Ghi nhớ:** **Card** giữ câu chuyện ngắn gọn và hướng tới giá trị; **Conversation** tạo hiểu biết chung, khám phá lựa chọn và ngoại lệ; **Confirmation** biến sự hiểu biết đó thành các ví dụ có thể kiểm chứng. Ba chữ C hoạt động như một vòng trao đổi liên tục, giúp nhóm Agile xây đúng phần mềm, kiểm tra đúng hành vi và thích ứng khi có phản hồi mới.
