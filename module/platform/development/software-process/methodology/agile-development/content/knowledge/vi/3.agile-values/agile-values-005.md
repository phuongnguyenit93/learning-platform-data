# Hiểu đúng việc coi trọng hai phía trong mỗi cặp giá trị

Trong **Agile Manifesto**, bốn cặp giá trị đều có cùng một cấu trúc: **ưu tiên điều được nêu ở vế trái hơn điều được nêu ở vế phải**, đồng thời khẳng định vế phải **vẫn có giá trị**. Đây là điểm rất dễ bị hiểu sai. Agile không yêu cầu bỏ quy trình, không viết tài liệu, né hợp đồng hay không lập kế hoạch. Agile yêu cầu cân nhắc cách dùng những thứ ấy sao cho phục vụ con người, sản phẩm vận hành được, sự hợp tác và khả năng thích ứng.

Bài thuộc chương **Giá trị Agile** của module **AGILE_DEVELOPMENT**, nơi người học tìm hiểu phát triển phần mềm thích ứng nhờ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. Hiểu đúng hai vế giúp nhóm vận dụng user story, backlog, Scrum, Kanban, XP và các thước đo dòng công việc theo mục tiêu tạo giá trị, thay vì biến phương pháp thành nghi thức.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nêu đúng bốn cặp giá trị của Agile Manifesto và giải thích ý nghĩa của câu kết chung cho cả bốn cặp.
- Chỉ ra giá trị thực tế của **cả vế trái lẫn vế phải** trong mỗi cặp.
- Phân biệt **ưu tiên tương đối khi cần đánh đổi** với việc **loại bỏ tuyệt đối** một phía.
- Nhận diện quyết định cực đoan mang nhãn “Agile” nhưng làm tăng rủi ro, giảm chất lượng hoặc gây mất phối hợp.
- Dùng một khung câu hỏi thực tế để điều chỉnh quy trình, tài liệu, hợp đồng và kế hoạch dựa trên bối cảnh, phản hồi và trách nhiệm.

## 2. Đọc đầy đủ tuyên bố của Agile Manifesto

Agile Manifesto (2001) nêu bốn ưu tiên:

| Vế được coi trọng hơn | Vế vẫn có giá trị |
| --- | --- |
| **Cá nhân và tương tác** (*Individuals and interactions*) | Quy trình và công cụ (*Processes and tools*) |
| **Phần mềm hoạt động được** (*Working software*) | Tài liệu đầy đủ, toàn diện (*Comprehensive documentation*) |
| **Hợp tác với khách hàng** (*Customer collaboration*) | Đàm phán hợp đồng (*Contract negotiation*) |
| **Đáp ứng thay đổi** (*Responding to change*) | Tuân theo kế hoạch (*Following a plan*) |

Ý quan trọng nằm trong câu kết của tuyên bố:

> Dù những điều ở vế phải có giá trị, chúng tôi vẫn coi trọng những điều ở vế trái hơn.

Đây là một **lựa chọn về mức độ ưu tiên**, không phải phép chia giữa “đúng” và “sai”. Khi hai phía cùng hỗ trợ một mục tiêu, hãy tận dụng cả hai. Khi việc làm quá mức ở phía phải cản trở kết quả thiết yếu ở phía trái, cần xem xét giảm hoặc điều chỉnh phần cản trở đó. Ngược lại, không được viện dẫn giá trị phía trái để bỏ qua nghĩa vụ bắt buộc, an toàn, chất lượng hay sự tin cậy.

### Ba tầng cần phân biệt

1. **Giá trị** trả lời “khi phải cân nhắc, điều gì nên được chú trọng hơn?”. Bốn cặp trên thuộc tầng này.
2. **Nguyên tắc** giải thích cách biến giá trị thành hành vi, ví dụ giao phần mềm có giá trị thường xuyên, hợp tác chặt chẽ và chú ý đến sự xuất sắc kỹ thuật.
3. **Thực hành/công cụ** cụ thể hóa trong bối cảnh nhóm: user story, Product Backlog, Sprint Review, bảng Kanban, giới hạn WIP, kiểm thử tự động, CI, tài liệu API, kế hoạch phát hành...

Không có công cụ hay nghi thức nào tự bảo đảm nhóm đã làm việc theo giá trị Agile. Cần xem **cách nhóm ra quyết định** và **kết quả đối với người dùng**, chứ không chỉ việc nhóm đã tổ chức họp hay sử dụng công cụ nào.

## 3. Nguyên tắc chung: “hơn” không có nghĩa “thay cho”

So sánh hai cách diễn đạt:

- **Hiểu sai:** “Agile coi trọng con người nên quy trình không cần thiết”.
- **Hiểu đúng:** “Quy trình cần hỗ trợ con người phối hợp hiệu quả; nếu một quy trình máy móc đang cản trở trao đổi và giải quyết vấn đề, nhóm phải xem lại nó”.

Vế phải thường giải quyết những nhu cầu hoàn toàn chính đáng:

| Nhu cầu cần bảo đảm | Vế phải thường giúp bằng cách nào? |
| --- | --- |
| Phối hợp ổn định giữa nhiều người | Quy trình và công cụ làm rõ trạng thái, trách nhiệm và cách bàn giao |
| Lưu giữ tri thức, vận hành và bảo trì | Tài liệu ghi lại quyết định, giao diện, giới hạn, hướng dẫn xử lý sự cố |
| Rõ quyền lợi, trách nhiệm và giới hạn rủi ro | Hợp đồng xác định phạm vi pháp lý, thanh toán, bảo mật, tiêu chí nghiệm thu |
| Có định hướng sử dụng nguồn lực và thực hiện cam kết | Kế hoạch xác định mục tiêu, thứ tự ưu tiên, ngân sách, mốc thời gian và phụ thuộc |

Nếu thiếu những yếu tố này, công việc có thể phụ thuộc vào vài cá nhân, mất dấu quyết định, gây tranh chấp hoặc không thể phối hợp với đối tác. Mặt khác, **quy trình quá dày, tài liệu tạo cho đủ, hợp đồng quá cứng hoặc kế hoạch không chịu cập nhật** cũng có thể làm nhóm giao sản phẩm chậm và mất phản hồi.

Một cách đọc hữu ích là: **mỗi thứ ở vế phải nên giúp ích cho điều gì ở vế trái, với mức độ vừa đủ cho rủi ro và bối cảnh hiện tại**. “Vừa đủ” không có một con số cố định; hệ thống y tế, ngân hàng và trò chơi thử nghiệm sẽ cần mức kiểm soát khác nhau.

~~~mermaid
flowchart TD
    A["Mục tiêu tạo giá trị và ràng buộc thực tế"] --> B{"Hai phía có thể hỗ trợ nhau?"}
    B -->|"Có"| C["Giữ cơ chế ở vế phải<br/>đang giúp vế trái hiệu quả"]
    B -->|"Có mâu thuẫn"| D["Xác định phần gây chậm,<br/>tốn công hoặc thiếu phản hồi"]
    D --> E["Bảo toàn yêu cầu bắt buộc:<br/>an toàn, pháp lý, chất lượng, cam kết"]
    E --> F["Điều chỉnh quy trình/tài liệu/<br/>hợp đồng/kế hoạch"]
    C --> G["Kiểm tra kết quả, lấy phản hồi"]
    F --> G
    G --> A
~~~

Sơ đồ mô tả **cách cân nhắc**, không phải thuật toán quyết định cứng. Nếu một nghĩa vụ bảo mật là bắt buộc, nhóm không thể lấy lý do muốn giao sớm để bỏ qua nghĩa vụ đó. Nhóm vẫn có thể tìm cách kiểm thử, tự động hóa và phản hồi sớm hơn **trong phạm vi các yêu cầu bắt buộc**.

## 4. Cặp 1 — Cá nhân và tương tác hơn quy trình và công cụ

### Vế trái có giá trị gì?

Phát triển phần mềm đòi hỏi cùng hiểu một vấn đề còn thay đổi. Con người cần trao đổi, làm rõ giả định, chia sẻ kiến thức và phối hợp ra quyết định. Một cuộc nói chuyện đúng người, đúng thời điểm có thể giải quyết điều mơ hồ mà hàng chục bình luận trên ticket chưa làm rõ.

Ví dụ: yêu cầu “học viên tiếp tục bài học ở vị trí cũ” chưa nói rõ trường hợp học trên điện thoại rồi mở máy tính. Developers, người hiểu sản phẩm và người kiểm thử thảo luận trực tiếp để chốt hành vi mong muốn, sau đó ghi lại quyết định cần thiết. Sự tương tác làm giảm hiểu sai trước khi nhóm viết mã.

### Vế phải có giá trị gì?

Quy trình và công cụ giúp phối hợp lặp lại được, đặc biệt khi nhóm lớn, làm việc từ xa, có nhân sự mới hoặc cần truy vết:

- Bảng Kanban và giới hạn WIP cho mọi người thấy công việc đang ở đâu, mục nào bị chặn.
- Product Backlog giúp minh bạch thứ tự ưu tiên và các mục đang chờ làm rõ.
- Quy tắc review mã, kiểm thử CI và tiêu chí hoàn thành ngăn lỗi bị bỏ sót khi nhiều người cùng thay đổi hệ thống.
- Biên bản quyết định ngắn giúp người vắng mặt hiểu vì sao một lựa chọn được đưa ra.

**Lệch về vế phải:** nhóm buộc đi qua sáu cấp duyệt dù thay đổi rất nhỏ; các thành viên chỉ chuyển ticket mà không trao đổi với nhau; công cụ quyết định cách làm dù thực tế đã khác.

**Lệch về vế trái:** mọi quyết định đều nói miệng, không ghi lại, người khác không biết trạng thái; thiếu điểm kiểm soát khiến lỗi nghiêm trọng đi qua; chỉ người dự họp mới biết cần làm gì.

**Cân bằng thực tế:** ưu tiên hội thoại để giải quyết sự mơ hồ và vấn đề phức tạp, sau đó lưu thông tin cần thiết ở chỗ dùng chung. Dùng quy trình tối thiểu nhưng đủ rõ để hỗ trợ trách nhiệm và chất lượng. Một nhóm làm việc phân tán có thể ưu tiên trao đổi không đồng bộ bằng văn bản hơn cuộc họp trực tiếp ở nhiều trường hợp; giá trị vẫn là **tương tác hiệu quả giữa con người**.

### Tình huống quyết định

Một lỗi đăng nhập đang ảnh hưởng nhiều người dùng. Quy trình bình thường yêu cầu tạo ticket, chờ ba cấp xét duyệt rồi mới phân công xử lý. Nhóm có thể mở kênh phối hợp tức thời giữa kỹ thuật, vận hành và người ra quyết định, kích hoạt quy trình xử lý sự cố đã được phê duyệt, ghi nhận thay đổi và làm hậu kiểm. Như vậy, **tương tác nhanh và quy trình an toàn hỗ trợ nhau**.

## 5. Cặp 2 — Phần mềm hoạt động được hơn tài liệu toàn diện

### Vế trái có giá trị gì?

Phần mềm tạo phản hồi đáng tin hơn khi người dùng hoặc bên liên quan **thấy và trải nghiệm hành vi thật**. Một mô tả yêu cầu có thể nghe hợp lý nhưng chỉ khi sử dụng tính năng, người học mới nhận ra nút “Học tiếp” đặt quá xa hoặc tiến độ hiển thị không đúng.

“Hoạt động được” không đồng nghĩa một bản demo tạm bợ chỉ chạy trên máy lập trình viên. Với sản phẩm cụ thể, nhóm cần xác định tiêu chuẩn chất lượng như kiểm thử, khả năng tích hợp, bảo mật, khả năng sử dụng và điều kiện triển khai. Trong Scrum, Increment phải đáp ứng **Definition of Done** trước khi được xem là đã hoàn thành. Một Increment sử dụng được cũng không nhất thiết phải được phát hành ngay.

### Vế phải có giá trị gì?

Tài liệu giúp tri thức sống lâu hơn cuộc trò chuyện và hỗ trợ những người không trực tiếp viết mã:

| Loại tài liệu | Giá trị khi được viết đúng nhu cầu |
| --- | --- |
| User story kèm tiêu chí chấp nhận | Làm rõ hành vi mong đợi và giới hạn phạm vi |
| Hướng dẫn chạy, triển khai, khôi phục | Giúp vận hành và xử lý sự cố |
| Tài liệu API hoặc hợp đồng dữ liệu | Giúp các nhóm tích hợp chính xác |
| Ghi chú quyết định kiến trúc | Giúp người đến sau hiểu lý do và các đánh đổi |
| Hồ sơ kiểm thử, bảo mật, truy vết | Cung cấp bằng chứng khi quy định, hợp đồng hoặc mức rủi ro yêu cầu |
| Hướng dẫn sử dụng | Giúp người dùng thực sự tiếp cận tính năng |

Độ chi tiết hợp lý phụ thuộc vào đối tượng đọc, tuổi thọ kiến thức và mức độ rủi ro. Với dịch vụ tài chính hoặc hệ thống có yêu cầu pháp lý, một số tài liệu và bằng chứng kiểm soát là **điều kiện bắt buộc để sản phẩm có thể sử dụng an toàn**, không phải phần thừa cần bỏ.

**Lệch về vế phải:** nhóm mất nhiều tuần hoàn thiện bộ tài liệu đặc tả chi tiết cho các giả định chưa kiểm chứng, nhưng chưa tạo được một chức năng dùng được để lấy phản hồi.

**Lệch về vế trái:** nhóm giao mã không có hướng dẫn triển khai, tài liệu API sai, thiếu bằng chứng kiểm thử bắt buộc; tính năng chạy trong demo nhưng không thể vận hành hoặc bảo trì.

**Cân bằng thực tế:** viết tài liệu để hỗ trợ hiểu đúng, vận hành và tuân thủ; cập nhật cùng những thay đổi có ý nghĩa của phần mềm. Xem xét dùng ví dụ thực thi, kiểm thử tự động và schema để giữ một phần đặc tả gần với sản phẩm, nhưng vẫn cung cấp phần giải thích cho con người khi cần.

### Tình huống quyết định

Nhóm có yêu cầu xây tính năng “Học tiếp”. Hai phương án được đề xuất:

1. Viết ngay bộ đặc tả 80 trang cho tất cả trường hợp dùng trong một năm.
2. Làm rõ mục tiêu, ghi tiêu chí chấp nhận cho lát cắt đầu tiên, xây phần mềm có thể dùng được, kiểm thử, ghi lại những quyết định quan trọng và lấy phản hồi trước khi thiết kế chi tiết các khả năng chưa chắc cần.

Trong bối cảnh nhu cầu chưa chắc chắn, phương án 2 thường giúp học sớm hơn. Tuy nhiên, nếu ứng dụng phải đáp ứng chuẩn lưu trữ dữ liệu hoặc kiểm toán, phần tài liệu bắt buộc vẫn phải được tạo và xác minh. Agile không biến mọi tài liệu thành tùy chọn.

## 6. Cặp 3 — Hợp tác với khách hàng hơn đàm phán hợp đồng

### Vế trái có giá trị gì?

Người làm sản phẩm cần hiểu vấn đề, kiểm chứng giải pháp và trao đổi khi ưu tiên thay đổi. **Hợp tác với khách hàng** bao gồm làm rõ nhu cầu, cùng quyết định đánh đổi, xem sản phẩm đang chạy, thảo luận phản hồi và điều chỉnh hướng đi.

Ở đây, “khách hàng” có thể là người đặt hàng, người đại diện nhu cầu sản phẩm hoặc các bên liên quan đủ thẩm quyền; nhóm cũng cần tiếp xúc với **người dùng cuối thực tế** khi có thể. Người ký hợp đồng chưa chắc là người trực tiếp sử dụng sản phẩm. Để tránh xung đột, phải làm rõ ai cung cấp phản hồi, ai ưu tiên backlog và ai có quyền quyết định phạm vi, chi phí hoặc nghiệm thu.

### Vế phải có giá trị gì?

Hợp đồng tạo khung hợp tác đáng tin cậy, đặc biệt giữa những tổ chức độc lập. Nó có thể quy định:

- Mục tiêu dịch vụ hoặc phạm vi ban đầu và cách quản lý thay đổi.
- Ngân sách, thanh toán, giới hạn trách nhiệm và quyền sở hữu trí tuệ.
- Bảo mật, bảo vệ dữ liệu, yêu cầu pháp lý, tiêu chuẩn chất lượng.
- Cách nghiệm thu, giải quyết bất đồng, thời hạn và điều kiện chấm dứt.

Không thể bỏ qua các nội dung này chỉ bằng lời nói “chúng ta làm Agile”. Khi có hợp đồng hoặc nghĩa vụ pháp lý, mọi thay đổi phải đi theo **cơ chế được phép và được ghi nhận**. Sự hợp tác liên tục giúp phát hiện sớm thay đổi cần thương lượng, chứ không loại bỏ nhu cầu thương lượng.

**Lệch về vế phải:** hợp đồng được xem như danh sách tính năng cố định bất biến; khách hàng đến cuối dự án mới thấy sản phẩm; việc trao đổi chỉ xảy ra khi có tranh chấp hoặc yêu cầu thay đổi chính thức.

**Lệch về vế trái:** các bên liên tục bổ sung yêu cầu qua cuộc trò chuyện mà không thống nhất ảnh hưởng đến ngân sách, thời gian, dữ liệu và tiêu chí nghiệm thu; cuối cùng không ai rõ đâu là cam kết chính thức.

**Cân bằng thực tế:** thỏa thuận nguyên tắc minh bạch về mục tiêu, trách nhiệm, giới hạn, chất lượng và cơ chế thay đổi; duy trì nhịp xem kết quả thực tế và ra quyết định cùng nhau. Với hợp đồng theo giá cố định, có thể thương lượng **phạm vi ưu tiên trong các giới hạn đã thỏa thuận**, hoặc làm thủ tục thay đổi chính thức khi vượt giới hạn.

### Tình huống quyết định

Một công ty thuê nhà cung cấp phát triển cổng đăng ký khóa học. Sau bản chạy thử đầu tiên, người dùng muốn đăng ký bằng điện thoại thay vì chỉ email. Cách làm có tinh thần Agile là cùng đánh giá lợi ích, rủi ro và chi phí; kiểm tra liệu có thể đổi thứ tự các tính năng trong phạm vi hợp đồng hay không; ghi nhận thỏa thuận và triển khai lát cắt phù hợp. Không có nghĩa nhà cung cấp phải nhận mọi yêu cầu mới miễn phí, hoặc khách hàng không được thay đổi bất cứ điều gì.

## 7. Cặp 4 — Đáp ứng thay đổi hơn tuân theo kế hoạch

### Vế trái có giá trị gì?

Trong sản phẩm phức tạp, giả định ban đầu có thể sai hoặc nhanh chóng lỗi thời. Phản hồi người dùng, lỗi mới phát hiện, biến động kinh doanh và phát hiện kỹ thuật là những đầu vào cần được xem xét. **Đáp ứng thay đổi** nghĩa là có khả năng cập nhật quyết định có chủ đích khi xuất hiện bằng chứng tốt hơn.

Khả năng thay đổi không tự có: sản phẩm chia thành các Increment nhỏ, kiểm thử đáng tin, tích hợp thường xuyên, thiết kế dễ sửa, backlog có thứ tự ưu tiên và các vòng phản hồi ngắn giúp nhóm điều chỉnh với chi phí thấp hơn.

### Vế phải có giá trị gì?

Kế hoạch giúp nhóm:

- Biết mục tiêu, phạm vi đang dự kiến và tiêu chí thành công.
- Sắp xếp ngân sách, năng lực, lịch phát hành và các phụ thuộc giữa nhóm.
- Chủ động chuẩn bị kiểm thử, triển khai, đào tạo, truyền thông và hỗ trợ vận hành.
- Nêu rõ giả định, rủi ro, mốc bắt buộc và thời điểm cần đánh giá lại.

Kế hoạch trong Agile vẫn quan trọng, nhưng cần được **xem như dự báo và cam kết có bối cảnh**, tùy phần nào đã xác định chắc chắn, phần nào chỉ là giả định. Khi thông tin thay đổi, nhóm nên trao đổi tác động và cập nhật kế hoạch một cách minh bạch. Không phải mọi thay đổi được đề xuất đều có giá trị hoặc nên chấp thuận.

**Lệch về vế phải:** vẫn xây tính năng không còn được người dùng cần chỉ vì nó nằm trong kế hoạch quý; biết rủi ro mới nhưng không cập nhật thứ tự ưu tiên.

**Lệch về vế trái:** đổi hướng liên tục theo ý kiến mới nhất, không kiểm chứng lợi ích, liên tục ngắt việc đang làm và không thể bảo đảm bất kỳ mục tiêu hay mốc quan trọng nào.

**Cân bằng thực tế:** giữ mục tiêu và ràng buộc minh bạch, kiểm tra giả định định kỳ, điều chỉnh chi tiết dựa trên bằng chứng. Phân biệt **thay đổi mục tiêu** với **thay đổi phương án để đạt mục tiêu**. Trong Scrum, Sprint Goal tạo trọng tâm; nếu phát hiện điều mới, Developers và Product Owner có thể làm rõ, thương lượng phạm vi Sprint mà không làm suy yếu Sprint Goal. Những thay đổi ảnh hưởng đến cam kết bên ngoài cần được trao đổi với người có thẩm quyền.

### Tình huống quyết định

Kế hoạch dự kiến phát triển chức năng xuất báo cáo PDF sau chức năng “Học tiếp”. Dữ liệu sử dụng bản đầu cho thấy học viên bỏ dở nhiều vì khó xem trên màn hình nhỏ. Nhóm và người quyết định sản phẩm có thể ưu tiên sửa trải nghiệm di động ở đợt tiếp theo, lùi báo cáo PDF và cập nhật dự báo. Nếu báo cáo PDF là nghĩa vụ pháp lý có hạn cố định, nhóm phải bảo vệ hạn đó và tìm phương án phù hợp với năng lực còn lại.

## 8. Bốn cặp hỗ trợ nhau trong cùng một quyết định

Không nên xem từng cặp như một khẩu hiệu riêng lẻ. Chúng thường tác động đồng thời:

| Vấn đề phát sinh | Cặp giá trị cần soi chiếu | Câu hỏi giúp ra quyết định |
| --- | --- | --- |
| Yêu cầu còn mơ hồ, các bên liên tục hiểu khác nhau | Cá nhân & tương tác / Quy trình & công cụ | Ai cần trao đổi trực tiếp? Quyết định nào cần lưu lại? |
| Nhiều tài liệu hoàn thành nhưng chưa có phần mềm trải nghiệm được | Phần mềm hoạt động / Tài liệu toàn diện | Lát cắt nhỏ nhất có thể kiểm chứng là gì? Tài liệu nào giúp làm và dùng lát cắt đó an toàn? |
| Khách hàng chỉ xuất hiện ở buổi nghiệm thu | Hợp tác khách hàng / Đàm phán hợp đồng | Có thể tổ chức phản hồi sớm theo cơ chế hợp đồng nào? |
| Một phản hồi quan trọng trái với dự kiến quý | Đáp ứng thay đổi / Theo kế hoạch | Bằng chứng đủ mạnh chưa? Ai quyết định, chi phí đổi hướng và các cam kết là gì? |

Vì vậy, “coi trọng vế trái hơn” là **hướng ưu tiên cho hành động**. Nó không miễn trách nhiệm quản lý chất lượng, công việc, tài chính hoặc rủi ro. Nếu một lựa chọn được gọi là Agile nhưng khiến người dùng không thể sử dụng sản phẩm, đội ngũ không hiểu nhau hoặc cam kết bị phá vỡ vô cớ, cần xem lại cách diễn giải.

## 9. Ví dụ xuyên suốt: phát triển tính năng “Học tiếp”

Giả sử một nhóm phát triển nền tảng học trực tuyến nhận thấy học viên khó quay lại bài học đang dở. Nhóm có Product Owner, Developers, người kiểm thử, người thiết kế và đại diện hỗ trợ học viên. Mục tiêu là tăng tỷ lệ người học quay lại, nhưng chưa biết giao diện nào hiệu quả.

### Giai đoạn A — Làm rõ vấn đề, chọn Increment đầu tiên

Nhóm mời người hiểu sản phẩm và đại diện hỗ trợ thảo luận cùng Developers. Họ viết một user story:

> **Là** học viên đang học dở, **tôi muốn** vào lại đúng bài và vị trí đang học, **để** tiếp tục mà không cần tìm thủ công.

Họ xác định tiêu chí chấp nhận: hệ thống lưu tiến độ sau thao tác học, hiển thị đúng bài tiếp theo và không làm lộ dữ liệu tiến độ của tài khoản khác. Trường hợp chưa học bài nào phải được xử lý có chủ đích. Các quyết định được ghi ngắn gọn trong backlog để người vắng mặt vẫn hiểu.

- **Cặp 1:** cuộc trao đổi làm rõ giả định; backlog và tiêu chí chấp nhận giúp lưu hiểu biết chung.
- **Cặp 2:** nhóm không chờ hoàn thành bộ tài liệu cho toàn bộ hệ thống gợi ý học tập; họ vẫn ghi đặc tả hành vi, dữ liệu và kiểm thử cần thiết.
- **Cặp 3:** Product Owner xác nhận ưu tiên với khách hàng/bên liên quan; nếu có hợp đồng bên ngoài, nhóm xác nhận phạm vi có thể thực hiện.
- **Cặp 4:** nhóm giữ mục tiêu giúp học viên quay lại học, còn thiết kế chi tiết được phép điều chỉnh khi có dữ liệu.

### Giai đoạn B — Xây và kiểm tra phần mềm thực

Nhóm lấy một lát cắt đủ nhỏ từ Product Backlog, triển khai giao diện và dịch vụ lưu tiến độ. Developers viết kiểm thử phù hợp, tích hợp thay đổi thường xuyên và sử dụng tiêu chí hoàn thành đã thống nhất. Với Scrum, Increment phải đạt Definition of Done; với Kanban, nhóm có thể trực quan hóa và giới hạn công việc đang làm để giảm việc dở dang. Các thực hành như kiểm thử tự động, refactoring của XP giúp giảm chi phí đổi hướng.

Sau bản chạy thử, học viên nhận xét nút “Học tiếp” khó tìm trên di động. Nhóm ghi nhận ý kiến cùng dữ liệu sử dụng thay vì tranh luận dựa vào bản đặc tả ban đầu. Họ sửa giao diện ở đợt tiếp theo và cập nhật những tài liệu có liên quan.

### Giai đoạn C — Điều chỉnh kế hoạch một cách có trách nhiệm

Nếu tăng độ ưu tiên của cải tiến di động làm lùi một tính năng dự kiến khác, Product Owner minh bạch đánh đổi với bên liên quan và cập nhật backlog/dự báo. Nếu tính năng bị lùi gắn với hạn cam kết, nhóm phải đánh giá phụ thuộc, thống nhất thay đổi hoặc tìm phương án giữ hạn. Nhóm đo kết quả thực tế như tỷ lệ quay lại học và lỗi sử dụng, chứ không coi số ticket đóng là bằng chứng đủ về giá trị.

Qua ba giai đoạn, cả bốn vế phải **đều đang được sử dụng**: công cụ backlog, tài liệu hành vi, thỏa thuận trách nhiệm và kế hoạch. Điểm khác biệt là chúng được thiết kế để **hỗ trợ hợp tác, phần mềm hoạt động, phản hồi và thích ứng**.

## 10. Khung câu hỏi khi phải cân nhắc hai phía

Khi có ý kiến “Làm Agile thì bỏ bước này đi”, đừng kết luận ngay. Nhóm có thể dùng sáu câu hỏi:

1. **Giá trị cần tạo là gì?** Ai được lợi, dấu hiệu nào chứng minh kết quả tốt hơn?
2. **Điều gì đang cản trở?** Quy trình, tài liệu, đàm phán hay kế hoạch đang gây chậm ở bước nào? Có dữ liệu hay ví dụ cụ thể không?
3. **Vế phải đang bảo vệ nhu cầu nào?** Tri thức, an toàn, tuân thủ, trách nhiệm, ngân sách, chất lượng hay một phụ thuộc quan trọng?
4. **Điều gì là bắt buộc và điều gì linh hoạt?** Xác định nghĩa vụ pháp lý/hợp đồng và yêu cầu chất lượng; đừng tự xem mọi quy định là tùy ý.
5. **Có thể thay đổi nhỏ như thế nào?** Rút ngắn quy trình, tự động hóa kiểm tra, viết tài liệu sát mục đích, thêm buổi xem sản phẩm, chia nhỏ phạm vi hoặc cập nhật dự báo?
6. **Kiểm chứng bằng gì và khi nào?** Dùng phản hồi khách hàng, sản phẩm chạy được, số lỗi, thời gian hoàn tất, mức đáp ứng cam kết để quyết định giữ hay điều chỉnh thử nghiệm.

Ví dụ áp dụng:

| Quan sát | Không nên kết luận vội | Thử nghiệm hợp lý |
| --- | --- | --- |
| Chờ duyệt thủ công bốn ngày cho mỗi bản sửa nhỏ | “Agile không cần duyệt” | Phân loại theo rủi ro, tự động hóa kiểm thử, áp dụng quy trình duyệt nhanh cho thay đổi đủ điều kiện |
| Tài liệu API luôn sai so với hệ thống thực | “Bỏ viết tài liệu là xong” | Sinh schema/API reference từ mã nguồn khi phù hợp; kiểm tra tài liệu trong CI và bổ sung hướng dẫn sử dụng |
| Khách hàng thường yêu cầu thay đổi cuối dự án | “Khách hàng không biết họ muốn gì” | Tổ chức xem Increment sớm và thường xuyên, nêu quy tắc quyết định, cập nhật các thỏa thuận liên quan |
| Kế hoạch Sprint liên tục xáo trộn | “Chấp nhận thay đổi là phải đổi ngay” | Làm rõ Sprint Goal, chính sách việc khẩn cấp, khả năng xử lý, ưu tiên và chi phí ngắt dòng công việc |

Điều cần đo không chỉ là tốc độ thực thi một bước riêng lẻ. Ví dụ, cắt bỏ toàn bộ bước review có thể giảm thời gian chờ trước mắt nhưng tăng lỗi sau phát hành và thời gian sửa lại. Cần xem **toàn bộ dòng tạo giá trị**, chất lượng và khả năng học từ kết quả.

## 11. Những hiểu nhầm thường gặp

### “Ưu tiên vế trái nghĩa là vế phải không có giá trị”

Sai với câu kết rõ ràng của Agile Manifesto. Bản tuyên ngôn nói hai phía đều có giá trị và chỉ nêu mức độ ưu tiên. Việc loại bỏ hoàn toàn quy trình, tài liệu, hợp đồng hay kế hoạch thường tạo thêm rủi ro.

### “Agile chống quy trình và công cụ”

Không. Scrum có trách nhiệm, sự kiện và artifact; Kanban có chính sách workflow và giới hạn WIP; XP có thực hành kỹ thuật rất kỷ luật. Vấn đề là **quy trình và công cụ có thực sự giúp con người phối hợp và tạo sản phẩm tốt hơn không**.

### “Code chạy được thì không cần viết gì”

Chạy một demo chưa chắc đạt yêu cầu bảo mật, vận hành, kiểm thử hoặc pháp lý. Tài liệu cần thiết có thể là một phần của điều kiện hoàn thành và khả năng sử dụng sản phẩm. Ưu tiên phần mềm hoạt động có nghĩa tài liệu cần phục vụ kết quả thực, không chỉ hoàn thành để đánh dấu.

### “Hợp tác với khách hàng tức là đáp ứng mọi yêu cầu”

Hợp tác bao gồm giải thích ràng buộc, phản biện, trao đổi đánh đổi và cùng ra quyết định. Không phải mọi ý tưởng đều đáng thực hiện; không phải thay đổi nào cũng nằm trong phạm vi thỏa thuận. Hợp tác tốt cần rõ thẩm quyền và kỳ vọng.

### “Làm Agile là không cần kế hoạch”

Không có định hướng, dự báo hay quản lý phụ thuộc thì việc phối hợp rất khó. Agile khuyến khích lập kế hoạch phù hợp, cập nhật khi hiểu biết tăng lên, tránh coi bản dự đoán ban đầu là chân lý bất biến.

### “Vế trái phải luôn thắng trong mọi tình huống”

Câu “coi trọng hơn” không cho phép bỏ yêu cầu bắt buộc. Chất lượng, pháp lý, bảo mật, khả năng tiếp cận, an toàn và nghĩa vụ đã cam kết vẫn phải được xử lý. Nếu có xung đột thật sự, nhóm cần điều chỉnh thiết kế, phạm vi, thời gian hoặc thương lượng có thẩm quyền; không nên tự ý vi phạm ràng buộc.

### “Chỉ cần đọc đúng khẩu hiệu là đã Agile”

Điều quan trọng là hành vi: nhóm có sẵn sàng trao đổi với người cần thiết, giao các Increment dùng được, lấy phản hồi sớm, ra quyết định minh bạch và cải tiến liên tục hay không. Những câu trả lời này phải được chứng minh qua cách làm và kết quả.

## 12. Tự kiểm tra cách hiểu

### Câu 1

Một nhóm dùng bảng Kanban và checklist review mã. Thành viên nói: “Agile ưu tiên cá nhân và tương tác nên nên xóa hết hai thứ này”. Bạn phản hồi thế nào?

**Gợi ý:** Hỏi hai công cụ đang phục vụ việc phối hợp và chất lượng ra sao. Giữ phần có ích, sửa phần gây trở ngại. Giá trị ở vế trái không yêu cầu bỏ vế phải.

### Câu 2

Một nhóm đã viết 100 trang thiết kế nhưng chưa kiểm tra được hành vi chính với người dùng; nhóm khác giao tính năng nhưng không có khả năng khôi phục khi sự cố xảy ra. Hai nhóm lệch ở đâu?

**Gợi ý:** Nhóm thứ nhất có thể quá chú trọng tài liệu trước khi kiểm chứng phần mềm; nhóm thứ hai đang thiếu khả năng vận hành và tri thức cần thiết. Cả hai cần cân bằng việc giao phần mềm hoạt động và tài liệu phục vụ sử dụng, bảo trì, an toàn.

### Câu 3

Khách hàng muốn thêm xác thực hai yếu tố trong khi hợp đồng ban đầu chỉ yêu cầu đăng nhập mật khẩu. Nhà cung cấp nên chấp nhận ngay hay từ chối ngay?

**Gợi ý:** Cùng xem lợi ích bảo mật, nghĩa vụ bắt buộc, chi phí, phạm vi, thời hạn và quyền quyết định; sau đó thống nhất và ghi nhận thay đổi theo cơ chế đã thỏa thuận. Hợp tác và hợp đồng hỗ trợ nhau.

### Câu 4

Kế hoạch quý nêu chức năng A phải làm trước B. Bản thử nghiệm cho thấy B giải quyết vấn đề người dùng cấp thiết hơn, nhưng A có mốc tuân thủ pháp lý. Nhóm nên làm gì?

**Gợi ý:** Kiểm tra dữ liệu về giá trị B, xác định chính xác mốc và phạm vi nghĩa vụ A, đánh giá năng lực và các phương án chia nhỏ. Điều chỉnh phần linh hoạt, bảo vệ phần bắt buộc và công khai dự báo.

### Câu 5

Nhận xét nào đúng nhất?

A. “Agile chọn vế trái nên loại bỏ vế phải.”  
B. “Bốn cặp giá trị cho thấy cả hai vế quan trọng, nhưng vế trái được ưu tiên hơn khi cân nhắc cách làm.”  
C. “Agile bắt buộc dùng Scrum, không cần hợp đồng và kế hoạch.”  
D. “Đã dùng đúng công cụ thì không cần đo kết quả người dùng.”

**Đáp án:** **B**. Các phương án còn lại biến định hướng giá trị thành quy tắc tuyệt đối hoặc đánh đồng phương pháp với kết quả.

## 13. Tóm tắt và áp dụng

| Nếu muốn... | Hãy coi trọng... | Và sử dụng vế phải để... |
| --- | --- | --- |
| Phối hợp nhanh, giảm hiểu sai | **Con người và tương tác** | Quy trình, công cụ giúp minh bạch và duy trì chất lượng |
| Kiểm chứng giá trị sớm | **Phần mềm hoạt động được** | Tài liệu hỗ trợ đúng hành vi, vận hành, bảo trì, tuân thủ |
| Hiểu và đáp ứng nhu cầu có trách nhiệm | **Hợp tác với khách hàng** | Hợp đồng làm rõ ranh giới, trách nhiệm, cơ chế thay đổi |
| Giữ sản phẩm phù hợp khi thông tin đổi | **Đáp ứng thay đổi** | Kế hoạch định hướng, dự báo, phối hợp và quản lý cam kết |

Khi đưa những giá trị này vào thực hành, nhóm có thể dùng **user story và backlog** để làm rõ giá trị, **Scrum** để kiểm tra và thích ứng theo Sprint, **Kanban** để thấy các điểm nghẽn trong dòng công việc, **XP** để xây chất lượng kỹ thuật và những thước đo phù hợp để đánh giá khả năng giao hàng. Không thực hành nào tự thay thế câu hỏi trung tâm: **chúng ta có đang tạo ra phần mềm có ích, học đủ sớm và phối hợp tốt hơn theo thời gian không?**

Nguồn định hướng gốc:

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — bốn cặp giá trị và câu khẳng định vế phải cũng có giá trị.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — các nguyên tắc về giao phần mềm, hợp tác, thay đổi, chất lượng và cải tiến.
- [The Scrum Guide](https://scrumguides.org/) — tham khảo thêm về Scrum Team, Increment, Definition of Done và thích ứng trong Sprint.

**Điểm cần nhớ:** Agile không thay thế một cực đoan bằng cực đoan ngược lại. Agile nhắc nhóm đặt con người, sản phẩm thực, quan hệ hợp tác và khả năng thích ứng **lên trước**, đồng thời tổ chức quy trình, tài liệu, hợp đồng và kế hoạch **đủ tốt để giúp bốn ưu tiên ấy thành hiện thực**.
