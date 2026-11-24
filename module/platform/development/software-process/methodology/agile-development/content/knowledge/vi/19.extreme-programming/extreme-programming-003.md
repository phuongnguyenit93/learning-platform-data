# Khách hàng tham gia thường xuyên và trao đổi về ưu tiên

Một nhóm phát triển nền tảng học trực tuyến nhận yêu cầu: **“Thêm chức năng đăng ký khóa học cho học viên trước đợt khai giảng”**. Người quản lý chuyển tài liệu cho nhóm rồi hẹn xem kết quả sau bốn tuần. Trong quá trình xây dựng, Developers gặp những câu hỏi chưa có lời giải: học viên có được ghi danh khóa miễn phí mà chưa xác minh email không, thanh toán đang xử lý có cấp quyền học chưa, và khi giao dịch bị lặp thì đơn nào được giữ? Không ai có quyền trả lời. Nhóm tự giả định để không chậm tiến độ.

Đến ngày trình diễn, giao diện trông hoàn thiện nhưng nhiều học viên không thể vào bài đầu tiên, trạng thái thanh toán gây nhầm lẫn và tính năng báo cáo nâng cao đã chiếm phần lớn thời gian. Người đặt hàng nói: “Đó không phải điều chúng tôi cần ưu tiên!”. Developers đáp: “Tài liệu ban đầu không đề cập các trường hợp đó”.

**Extreme Programming (XP)** muốn thu hẹp khoảng cách ấy bằng việc **khách hàng tham gia thường xuyên, có khả năng làm rõ nhu cầu và cùng trao đổi ưu tiên với đội kỹ thuật**. Thay vì coi yêu cầu là một bản hợp đồng đóng băng được “ném qua tường”, XP tạo vòng lặp liên tục: thảo luận giá trị → chọn công việc nhỏ → xây và kiểm thử → xem phần mềm chạy thực tế → điều chỉnh quyết định.

Khách hàng trong XP không chỉ xuất hiện ở buổi ký duyệt cuối cùng. Người đại diện phù hợp cần **đủ gần để trả lời câu hỏi nghiệp vụ kịp thời**, **đủ quyền để lựa chọn ưu tiên** và **đủ thông tin để chấp nhận hoặc điều chỉnh những hành vi được giao**. Nhưng sự tham gia đó không thay thế trách nhiệm kỹ thuật của Developers, không cho phép bỏ qua bảo mật và không có nghĩa khách hàng phải ngồi cạnh từng lập trình viên cả ngày.

Bài thuộc chương **Extreme Programming** của module **AGILE_DEVELOPMENT**. Nội dung gắn với mục tiêu hiểu giá trị và nguyên tắc Agile qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để chọn cách phối hợp phù hợp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của thực hành **On-Site Customer**, **Whole Team** và **Planning Game** trong XP, đồng thời tránh hiểu “on-site” chỉ là ngồi cùng một văn phòng.
2. Phân biệt trách nhiệm ra quyết định về **giá trị, phạm vi, thứ tự ưu tiên, mức độ chấp nhận** với trách nhiệm về **ước lượng, cách triển khai, kiểm thử và chất lượng kỹ thuật**.
3. Tổ chức các cuộc trao đổi ngắn, liên tục để chuyển nhu cầu của khách hàng thành user stories và ví dụ kiểm chứng được.
4. Cùng khách hàng lựa chọn phần việc giá trị nhất trong giới hạn năng lực, rủi ro và phụ thuộc; giải thích đánh đổi khi thêm hoặc đổi ưu tiên.
5. Liên kết phản hồi khách hàng với acceptance criteria, acceptance tests, bản giao nhỏ và kết quả sử dụng thực tế.
6. Xử lý tình huống khách hàng bận, nhiều stakeholders có ưu tiên xung đột, yêu cầu thay đổi đột ngột hoặc khách hàng muốn đánh đổi chất lượng để kịp ngày.
7. Vận dụng một kịch bản xuyên suốt, bộ câu hỏi, mẫu ghi nhận quyết định và chỉ số phản hồi để xây cách cộng tác hiệu quả hơn.

## 1. Vì sao XP coi tương tác với khách hàng là một thực hành cốt lõi?

XP là một cách tiếp cận Agile nhấn mạnh **phản hồi nhanh, giao phần mềm nhỏ và thường xuyên, giao tiếp trực tiếp, sự đơn giản và chất lượng kỹ thuật**. Các thực hành thường được liên hệ với XP gồm Planning Game, khách hàng tham gia sát nhóm, phát hành nhỏ, kiểm thử trước hoặc liên tục, tích hợp liên tục, refactoring, lập trình cặp, quyền sở hữu mã chung và nhịp làm việc bền vững. Những thực hành đó hỗ trợ nhau thay vì là những thủ tục tách rời.

Nếu khách hàng chỉ nêu yêu cầu một lần lúc khởi động:

- Nhóm có thể hiểu sai mục đích của một tính năng.
- Các ngoại lệ nghiệp vụ chỉ được phát hiện sau khi đã viết nhiều mã.
- Thứ tự ưu tiên phản ánh giả định cũ, không phải dữ liệu mới.
- Người chịu trách nhiệm sản phẩm không thấy được chi phí kỹ thuật và rủi ro của các lựa chọn.
- Developers thiếu người trả lời khi xuất hiện câu hỏi quan trọng, dẫn đến chờ hoặc tự đoán.
- Phản hồi tới quá muộn, khi thay đổi một quyết định trở nên đắt đỏ.

Ngược lại, khi có người đại diện khách hàng có thể trao đổi nhanh, cả hai bên cùng biết **vấn đề nào cần giải quyết**, **thứ gì phải được giao trước** và **bằng chứng nào sẽ cho biết giải pháp đủ tốt**.

### 1.1. Khách hàng gần gũi là một cơ chế giảm độ trễ phản hồi

Giả sử Developer cần quyết định xem đơn đang chờ thanh toán có cấp quyền học không:

| Cách phối hợp | Hành vi thường thấy | Rủi ro |
|---|---|---|
| Yêu cầu chuyển qua ba cấp quản lý, câu trả lời sau một tuần | Developer chờ, làm việc khác hoặc tự giả định | WIP tăng, làm lại, có thể cấp quyền sai |
| Có đại diện đủ hiểu biết và quyền trả lời trong nhịp làm việc | Developer nêu ví dụ, khách hàng xác nhận quy tắc, kiểm thử ghi nhận | Phát hiện sai khác sớm, quy tắc được kiểm chứng trước khi phát hành |

Sự tham gia thường xuyên không bảo đảm mọi quyết định đều đúng. Nó giúp **rút ngắn thời gian từ câu hỏi đến quyết định có căn cứ**, rồi tiếp tục kiểm tra quyết định bằng phần mềm và phản hồi thật.

### 1.2. Mục đích không phải làm mọi điều khách hàng vừa nghĩ ra

Khách hàng có quyền lựa chọn ưu tiên sản phẩm theo cơ chế đã thống nhất, nhưng có thể:

- Chưa hiểu một hạn chế tích hợp hoặc bảo mật.
- Đề nghị giải pháp thay vì mô tả vấn đề.
- Chịu áp lực từ một stakeholder có tiếng nói lớn.
- Chưa có dữ liệu xác nhận người dùng thực sự cần tính năng đó.

XP không yêu cầu Developers đồng ý với mọi giải pháp tức thời. **Đội kỹ thuật cần nói sự thật về chi phí, bất định và nguy cơ**, đồng thời đề xuất cách làm nhỏ hơn, an toàn hơn hoặc thử nghiệm trước. Khách hàng và Developers cùng thương lượng phạm vi, chứ không đánh tráo ưu tiên kinh doanh thành mệnh lệnh kỹ thuật.

### 1.3. XP và các giá trị Agile

Sự cộng tác này thể hiện trực tiếp những giá trị của Agile Manifesto:

- **Cá nhân và tương tác** được coi trọng hơn việc coi công cụ quản lý yêu cầu là toàn bộ cuộc đối thoại.
- **Phần mềm hoạt động được** giúp các bên kiểm tra giả định, thay vì chỉ ký vào tài liệu.
- **Hợp tác với khách hàng** tiếp diễn trong quá trình phát triển, không kết thúc sau thương lượng phạm vi ban đầu.
- **Phản hồi thay đổi** cho phép đổi thứ tự khi học thêm, thay vì bảo vệ kế hoạch cũ bằng mọi giá.

Điều đó không có nghĩa hợp đồng, tài liệu hoặc kế hoạch vô ích. Chúng vẫn cần thiết ở mức phù hợp; chỉ là **chúng không thay thế sự hiểu biết chung và bằng chứng từ phần mềm**.

## 2. “Khách hàng” trong XP là ai?

Trong ngữ cảnh XP, *customer* là vai trò mang **góc nhìn giá trị và yêu cầu nghiệp vụ** tới nhóm. Người này cần giúp quyết định phần mềm phải làm gì, làm trước cái gì và khi nào hành vi đã đáp ứng kỳ vọng. Khái niệm không nhất thiết chỉ một người cuối cùng trả tiền hoặc một người dùng cuối cụ thể.

### 2.1. Phân biệt các nguồn tiếng nói

| Người tham gia | Có thể đóng góp gì? | Giới hạn cần làm rõ |
|---|---|---|
| **Người dùng cuối** | Trải nghiệm thực, khó khăn, hành vi, ngôn ngữ và các trường hợp sử dụng | Có thể không có quyền quyết định ngân sách hay ưu tiên toàn sản phẩm |
| **Khách hàng mua/đặt hàng** | Mục tiêu kinh doanh, giá trị kỳ vọng, ngân sách và nghĩa vụ hợp đồng | Có thể không trực tiếp dùng sản phẩm hằng ngày |
| **Đại diện sản phẩm/nghiệp vụ** | Tổng hợp phản hồi, làm rõ chính sách, thương lượng thứ tự và phạm vi | Phải có đủ quyền ra quyết định hoặc đường xử lý nhanh khi vượt quyền |
| **Chuyên gia nghiệp vụ** | Các quy tắc phức tạp về thanh toán, tuyển sinh, chứng chỉ, báo cáo | Không tự động có quyền quyết định mọi ưu tiên |
| **Hỗ trợ/vận hành** | Các lỗi thường gặp, công việc thủ công, khả năng triển khai và xử lý sự cố | Có thể nhìn rõ một phần hành trình nhưng không đại diện toàn bộ người dùng |
| **Pháp lý, bảo mật, accessibility** | Điều kiện bắt buộc, rủi ro và tiêu chuẩn chất lượng | Không nên biến quyền kiểm soát chuyên môn thành ưu tiên tính năng tùy ý |

Trong một đội nhỏ, một người có thể đại diện đủ nhiều góc nhìn. Trong sản phẩm lớn, cần nhiều người tham gia, nhưng **cơ chế quyết định cuối cùng về thứ tự phải rõ**, nếu không Developers sẽ nhận các chỉ đạo mâu thuẫn.

### 2.2. “On-Site Customer” không đồng nghĩa phải hiện diện vật lý mọi lúc

Trong các mô tả XP truyền thống, **On-Site Customer** nhấn mạnh có khách hàng làm việc gần nhóm để trả lời câu hỏi và quyết định về tính năng. Khi đội phân tán, mục đích đó có thể được thực hiện qua:

- Khung giờ phản hồi hằng ngày hoặc kênh liên lạc đã thống nhất.
- Phiên trao đổi trực tiếp khi quy tắc phức tạp hoặc dễ hiểu nhầm.
- Ví dụ nghiệp vụ, quyết định và câu hỏi được ghi ở nơi mọi bên tra được.
- Bản phần mềm có thể dùng thử hoặc môi trường trình diễn thật.
- Đường xử lý nhanh cho quyết định cần thẩm quyền bổ sung.
- Quan sát người dùng và đánh giá kết quả sau từng bản giao nhỏ.

**Luôn trực tuyến 24/7 không phải điều kiện bắt buộc của XP**. Mục tiêu là phản hồi đủ nhanh theo nhịp phát triển và độ nghiêm trọng của quyết định, không ép một người phải trả lời mọi tin nhắn ngay lập tức.

### 2.3. Đại diện khách hàng phải có thẩm quyền thực

Một tình huống dễ thất bại: “đại diện khách hàng” có mặt trong mọi buổi họp, nhưng mọi quyết định đều phải gửi đến hội đồng khác và không ai biết khi nào được trả lời.

Trước khi làm việc, nhóm cần thống nhất:

1. Người đại diện được quyết định các quy tắc nghiệp vụ thông thường nào?
2. Họ được sắp xếp, thay đổi hoặc loại bỏ story trong giới hạn nào?
3. Khi có xung đột giữa người mua và người dùng cuối, ai xử lý?
4. Khi ràng buộc pháp lý, bảo mật hoặc hợp đồng bị ảnh hưởng, ai có quyền xác nhận?
5. Nếu người đại diện vắng mặt, ai là người thay thế có quyền phù hợp?
6. Mất bao lâu để nhận phản hồi cho câu hỏi đang chặn công việc?

Không nên trao trách nhiệm “làm khách hàng XP” cho một người rồi không trao quyền quyết định hoặc thông tin cần thiết. Đây là **vấn đề tổ chức**, không thể sửa chỉ bằng thêm một cuộc họp.

## 3. Quyền quyết định: kinh doanh chọn giá trị, kỹ thuật xác định cách làm

Trong XP, **Planning Game** thường phân biệt hai góc nhìn:

- **Góc nhìn kinh doanh/khách hàng:** điều gì có giá trị, thứ tự ưu tiên, kết quả chấp nhận được và các lựa chọn phạm vi.
- **Góc nhìn kỹ thuật/Developers:** độ lớn hoặc chi phí dự kiến, phụ thuộc, rủi ro, cách thiết kế và khả năng thực hiện với chất lượng cần thiết.

Hai bên cùng lập kế hoạch; không bên nào có đủ thông tin để một mình đưa ra mọi quyết định.

### 3.1. Ma trận trách nhiệm thực dụng

| Quyết định | Góc nhìn cần chịu trách nhiệm chính | Ai đóng góp? | Cảnh báo |
|---|---|---|---|
| Xác định vấn đề người dùng và kết quả mong muốn | Khách hàng/đại diện sản phẩm cùng người dùng | Developers, hỗ trợ, nghiên cứu | Tránh coi một yêu cầu tính năng là bằng chứng nhu cầu |
| Sắp thứ tự story theo giá trị | Người có quyền quyết định sản phẩm | Developers cung cấp chi phí, rủi ro và phương án | Không ép Developers tự đoán ưu tiên kinh doanh |
| Ước lượng độ lớn/năng lực thực hiện | Developers | Khách hàng làm rõ phạm vi và cách chia | Không áp sẵn một con số để vừa lịch |
| Quyết định cách triển khai, kiến trúc, kỹ thuật | Developers trong giới hạn đã thống nhất | Chuyên gia kiến trúc, vận hành, bảo mật | Khách hàng có thể nêu ràng buộc thật nhưng không bắt buộc chỉ đạo từng hàm mã |
| Xác định ví dụ nghiệm thu nghiệp vụ | Khách hàng và nhóm cùng làm rõ | Testers/Developers và người dùng phù hợp | Một ví dụ đúng không đủ bao phủ mọi rủi ro |
| Xác định tiêu chuẩn chất lượng kỹ thuật | Đội kỹ thuật và tổ chức có thẩm quyền | Khách hàng được thông tin về hệ quả | Không đổi bảo mật/DoD thành “tùy chọn” để lấy thêm story |
| Quyết định đánh đổi phạm vi và ngày | Người có quyền sản phẩm/hợp đồng, dựa trên dữ liệu kỹ thuật | Developers, vận hành và stakeholders | Không hứa cả phạm vi, ngày và chất lượng khi dữ liệu không đủ |
| Quyết định phát hành có kiểm soát | Các vai trò có thẩm quyền theo sản phẩm/tổ chức | Developers, vận hành, bảo mật | Acceptance test pass chưa thay thế mọi kiểm soát vận hành |

Phân định này là **mô hình làm việc tham khảo**, không phải danh sách chức danh bắt buộc của XP. Một tổ chức cần gắn vai trò thực tế với quyền quyết định rõ ràng.

### 3.2. Ví dụ một cuộc thương lượng đúng vai

> **Khách hàng:** “Chúng ta cần hỗ trợ cả thẻ tín dụng, ví điện tử và chuyển khoản trong đợt mở đăng ký đầu tiên.”
>
> **Developer:** “Chúng tôi đã kiểm chứng được một phương thức trong sandbox. Hai phương thức còn lại chưa có môi trường thử và quy tắc xử lý hoàn tiền. Nếu giữ cả ba, chúng tôi chưa có cơ sở dự báo sẽ hoàn tất an toàn đúng ngày.”
>
> **Khách hàng:** “Mục tiêu là học viên có thể mua khóa đầu tiên. Dữ liệu hiện có cho thấy phần lớn học viên thử dùng phương thức A. Ưu tiên A cho lần phát hành giới hạn; hai phương thức còn lại tiếp tục được làm rõ.”
>
> **Tester:** “Với phương thức A, cần có ví dụ cho thanh toán thành công, đang chờ, thất bại, gửi lại callback và truy cập trái quyền.”
>
> **Nhóm:** “Chúng ta chọn một luồng đầu-cuối kiểm chứng được, ghi rủi ro còn mở và xem lại ưu tiên sau phản hồi thực.”

Kết quả không phải đội kỹ thuật “từ chối khách hàng”; đây là **thương lượng có bằng chứng giữa giá trị và tính khả thi**.

### 3.3. Khách hàng không được mua tiến độ bằng cách bỏ chất lượng bắt buộc

Nếu một story thanh toán chưa chống xử lý trùng hoặc chưa kiểm tra phân quyền, không thể kết luận rằng “khách hàng chấp nhận tạm, cứ Done” là đủ để đưa ra sử dụng.

- Khách hàng có thể **giảm phạm vi**: chỉ hỗ trợ một phương thức, chỉ mở cho một nhóm đủ điều kiện, lùi các tiện ích không thiết yếu.
- Developers có thể **đổi phương án kỹ thuật** để đạt tiêu chuẩn với công sức hợp lý.
- Tổ chức có thể yêu cầu **kiểm soát, phê duyệt hoặc trì hoãn** theo rủi ro.
- Không được **che giấu việc thiếu bằng chứng hoặc hạ tiêu chuẩn an toàn** để giữ biểu đồ tiến độ.

Nếu nhóm sử dụng Scrum song song với các thực hành XP, Increment phải đáp ứng **Definition of Done**. Một acceptance test nghiệp vụ thành công không tự chứng minh Increment đã đạt toàn bộ DoD.

## 4. Planning Game: hai loại thông tin để lựa chọn story

**Planning Game** là một thực hành kinh điển của XP, trong đó khách hàng và Developers cùng xem các story, thảo luận giá trị, ước lượng công sức và chọn phạm vi của đợt phát triển gần nhất. Cách tổ chức có thể thay đổi theo đội; **không phải một công thức điểm số bắt buộc**.

### 4.1. Câu hỏi của phía khách hàng

- Ai sẽ dùng khả năng này, và vấn đề hiện tại nghiêm trọng thế nào?
- Nó góp phần vào mục tiêu sản phẩm hoặc kết quả kinh doanh gì?
- Nếu chưa làm ở đợt tới, người dùng bị ảnh hưởng ra sao?
- Có hạn bắt buộc theo hợp đồng, chính sách hoặc kỳ khai giảng không?
- Những story nào có giá trị cao nhưng có thể giao một phần nhỏ trước?
- Những tính năng nào chỉ là giả thuyết, cần thử nghiệm với người dùng?

### 4.2. Câu hỏi của phía Developers

- Story có đủ rõ để ước lượng và triển khai chưa?
- Cần những thay đổi UI, API, dữ liệu hoặc tích hợp nào?
- Có rủi ro kỹ thuật, bảo mật, hiệu năng, truy cập hoặc vận hành nào?
- Có phụ thuộc vào đội khác, đối tác hoặc môi trường thử không?
- Có thể chia thành lát cắt nhỏ mà vẫn tạo hành vi đúng và kiểm chứng được không?
- Với năng lực và chất lượng hiện tại, khối lượng nào có thể hoàn tất hợp lý?

### 4.3. Một vòng Planning Game thực dụng

~~~mermaid
flowchart TD
    A["Mục tiêu người dùng và thông tin phản hồi"] --> B["Khách hàng đề xuất story và giá trị"]
    B --> C["Developers hỏi, chia nhỏ, nêu rủi ro và ước lượng"]
    C --> D{"Đủ rõ để lựa chọn?"}
    D -->|"Chưa"| E["Thảo luận ví dụ, nghiên cứu hoặc spike"]
    E --> C
    D -->|"Có"| F["Khách hàng trao đổi thứ tự và đánh đổi phạm vi"]
    F --> G["Chọn tập story phù hợp năng lực và chất lượng"]
    G --> H["Xây, kiểm thử, tích hợp và giao phần nhỏ"]
    H --> I["Khách hàng kiểm tra; người dùng phản hồi"]
    I -. "Cập nhật giá trị và ưu tiên" .-> A
~~~

Quá trình lặp lại khi có thông tin mới. Kế hoạch không chỉ được viết một lần rồi để nguyên đến cuối dự án.

### 4.4. Kế hoạch release và kế hoạch vòng lặp

Trong thực hành XP truyền thống, Planning Game thường phân biệt:

| Mức kế hoạch | Câu hỏi chính | Độ chi tiết thích hợp |
|---|---|---|
| **Release planning** | Những khả năng nào nên có trong một đợt giao hoặc giai đoạn sản phẩm? | Định hướng mục tiêu, nhóm story, giá trị, rủi ro, năng lực, mốc kiểm tra |
| **Iteration planning** | Với năng lực gần nhất, story nhỏ nào được chọn và làm thế nào để hoàn tất? | Story đủ rõ, ví dụ nghiệp vụ quan trọng, ước lượng/công sức và kế hoạch kỹ thuật phù hợp |
| **Trong lúc thực hiện** | Thông tin mới có làm thay đổi lựa chọn, điều kiện hoặc rủi ro không? | Trao đổi nhanh, điều chỉnh trong giới hạn mục tiêu và thỏa thuận đang có |

Không nên viết chi tiết mọi story cho sáu tháng khi sản phẩm còn nhiều điều chưa biết. **Phần gần được làm rõ hơn phần xa**; khi học từ release nhỏ, cả hai mức kế hoạch đều được cập nhật.

### 4.5. Ai chọn scope và ai nói điều gì khả thi?

Một nguyên tắc thực dụng của Planning Game là **business quyết định điều gì đáng làm, Developers cung cấp ước lượng và giới hạn kỹ thuật**. Kế hoạch hữu ích xuất hiện khi những lựa chọn giá trị **khớp với năng lực thực và tiêu chuẩn chất lượng**.

Ví dụ, phía khách hàng ưu tiên A, B, C, D. Developers chỉ đánh giá có thể hoàn tất A và B trong vòng lặp này với chất lượng yêu cầu. Thay vì ép A–D thành lời hứa, các bên có thể:

1. Chọn A và B cho vòng lặp gần.
2. Chia C để giao phần có giá trị trước.
3. Giảm một biến thể của B nếu phù hợp.
4. Làm spike ngắn để giảm bất định của D.
5. Cập nhật dự báo và điều kiện lựa chọn sau khi có kết quả.

**Không có nghĩa phía khách hàng quyết định số ngày mà Developers phải làm**, cũng không có nghĩa Developers tự ý thay thứ tự giá trị vì thích công nghệ nào hơn.

## 5. User story là điểm khởi đầu của đối thoại

Một dạng mô tả thường dùng:

> **Là** [người dùng], **tôi muốn** [hành vi/năng lực], **để** [đạt mục đích].

Ví dụ:

> **Là** học viên đã thanh toán, **tôi muốn** biết đơn của mình đã được xác nhận và khi nào có thể vào khóa, **để** không phải liên hệ hỗ trợ.

Story này chưa trả lời:

- Nếu giao dịch “đang chờ”, có nên hiển thị “đã thanh toán” không?
- Khi nào quyền học được cấp?
- Dữ liệu trạng thái lấy từ nguồn đáng tin nào?
- Nếu đối tác gửi sự kiện lặp hoặc muộn, hệ thống xử lý thế nào?
- Người dùng A có thể truy vấn đơn của B không?
- Những thiết bị hoặc kênh nào được hỗ trợ?

**Không nên nhầm viết đúng mẫu với hiểu đúng yêu cầu.** Trong XP, story giúp **điều phối cuộc trò chuyện**, không được kỳ vọng thay thế toàn bộ đối thoại nghiệp vụ hoặc thiết kế kỹ thuật.

### 5.1. Ba chữ C của user story

Một heuristic phổ biến là **Card – Conversation – Confirmation**:

| Thành phần | Vai trò | Minh họa |
|---|---|---|
| **Card** | Ghi ý định ngắn gọn để nhớ và ưu tiên | “Học viên xem trạng thái đơn để biết khi nào được vào học” |
| **Conversation** | Người hiểu nghiệp vụ và Developers trao đổi quy tắc, ví dụ, rủi ro, phạm vi | “Đang chờ xử lý” khác “thành công” thế nào? Ai được xem? |
| **Confirmation** | Xác định những ví dụ hoặc tiêu chí để kiểm tra hành vi | Test giao dịch đang chờ không cấp quyền; khách hàng kiểm tra thông điệp |

Không nhất thiết dùng thẻ giấy; có thể lưu trong backlog tool. Nhưng nếu chỉ còn Card và bỏ Conversation/Confirmation, user story dễ trở thành “mini-specification” đầy khoảng trống.

### 5.2. Lát cắt nhỏ giúp khách hàng có lựa chọn thật

Một story “triển khai toàn bộ thanh toán, hóa đơn, hoàn tiền, mã giảm giá và quản trị giao dịch” không cho khách hàng nhiều lựa chọn hữu ích. Khi Developers đề xuất các lát cắt:

1. Giao dịch một phương thức được hỗ trợ, xác nhận trạng thái đáng tin và cấp quyền đúng.
2. Hiển thị trạng thái đang chờ hoặc thất bại với hướng dẫn rõ ràng.
3. Hỗ trợ xử lý các biến thể giao dịch theo chính sách.
4. Thêm phương thức thanh toán thứ hai nếu dữ liệu cho thấy cần.
5. Mở rộng báo cáo quản trị và hoàn tiền khi các ràng buộc được làm rõ.

Khách hàng có thể xem **điều nào tạo giá trị trước**, quyết định phần nào chưa cần và nhận phản hồi sau từng lát cắt. Những trường hợp an toàn thiết yếu phải nằm trong lát cắt liên quan; không chia nhỏ bằng cách bỏ phân quyền hoặc xử lý sai tiền.

### 5.3. Khi cần nghiên cứu thay vì ước lượng ngay

Nếu cả khách hàng lẫn Developers chưa biết khả năng một API đối tác hoặc người dùng có thực sự cần chức năng, có thể chọn:

- **Thử nghiệm giả thuyết người dùng:** prototype nhỏ, quan sát tác vụ, phỏng vấn hoặc dữ liệu hiện có.
- **Spike kỹ thuật có giới hạn thời gian:** thử tích hợp sandbox, đo một rủi ro hiệu năng hoặc tính nhất quán dữ liệu.
- **Làm rõ chính sách:** hỏi người có thẩm quyền về quy tắc nghiệp vụ, bảo mật hoặc nghĩa vụ hợp đồng.

Kết quả cần là **bằng chứng, giới hạn và quyết định tiếp theo**, không phải một story “nghiên cứu” kéo dài không có câu hỏi cụ thể. Spike hoặc prototype cũng **không tự động là tính năng production đã hoàn tất**.

## 6. Trao đổi ưu tiên: giá trị trước, nhưng không bỏ qua rủi ro

Ưu tiên không chỉ là chọn tính năng có nhiều yêu cầu nhất. Một backlog hữu ích cần phản ánh **giá trị người dùng, tác động kinh doanh, chi phí chậm trễ, rủi ro, phụ thuộc và khả năng giao phần nhỏ**.

### 6.1. Những yếu tố nên được trao đổi minh bạch

| Yếu tố | Câu hỏi cho khách hàng và nhóm | Ví dụ |
|---|---|---|
| **Giá trị người dùng** | Item có giúp người dùng hoàn thành một việc quan trọng không? | Sửa lỗi không thể vào khóa đã mua |
| **Tác động kinh doanh** | Có ảnh hưởng mục tiêu sản phẩm, doanh thu, chi phí hỗ trợ hoặc uy tín không? | Giảm đơn bị bỏ dở do trạng thái mơ hồ |
| **Chi phí chậm trễ** | Trì hoãn một hoặc vài tuần gây thiệt hại gì? | Hạn bắt buộc trước kỳ khai giảng |
| **Rủi ro/chất lượng** | Nếu chưa xử lý, hệ thống có mất dữ liệu, sai quyền hoặc lỗi giao dịch không? | Một người xem được đơn của người khác |
| **Phụ thuộc** | Có mở khóa hay bị chặn bởi công việc/đối tác khác không? | Cần chứng thực callback của nhà cung cấp |
| **Độ lớn và bất định** | Có thể giao lát cắt nhỏ nào trước không? | Một phương thức thanh toán được kiểm chứng |
| **Giá trị học tập** | Cần thử điều gì để tránh đầu tư sai? | Quan sát xem học viên cần ví hay chuyển khoản |

Các yếu tố này có thể được thảo luận định tính. Một tổ chức có thể dùng ma trận giá trị–nỗ lực hoặc các mô hình như Cost of Delay, nhưng **điểm số không tự biến giả định thành dữ liệu chắc chắn**. Cần công khai nguồn thông tin, điều còn mở và quyền quyết định.

### 6.2. Bảng ưu tiên minh họa

Giả sử nhóm có năm yêu cầu (toàn bộ là ví dụ giả định):

| Mã | Story / vấn đề | Giá trị và rủi ro | Tình trạng kỹ thuật | Hướng ưu tiên |
|---|---|---|---|---|
| **ST-01** | Học viên đã trả tiền không mở được bài đầu | Tác động rất lớn đến chức năng cốt lõi; có thể có rủi ro quyền truy cập | Có lỗi tái hiện được, cần kiểm tra hồi quy | Xử lý rất sớm theo mức nghiêm trọng |
| **ST-02** | Trạng thái giao dịch đang chờ bị hiển thị như thành công | Gây hiểu nhầm và yêu cầu hỗ trợ; liên quan tính đúng đắn | Cần làm rõ nguồn trạng thái | Ưu tiên làm rõ và sửa luồng cốt lõi |
| **ST-03** | Gợi ý khóa học theo AI | Giá trị hiện còn là giả thuyết | Kích thước và dữ liệu chưa chắc | Nghiên cứu nhu cầu trước khi xây rộng |
| **ST-04** | Thêm phương thức thanh toán B | Có thể tăng chuyển đổi, nhưng chưa có dữ liệu đủ mạnh | Sandbox đối tác chưa sẵn | Giảm rủi ro tích hợp, xem lại thời điểm chọn |
| **ST-05** | Đổi bố cục trang chủ theo chiến dịch | Có hạn truyền thông nhưng chưa chắc tác động onboarding | Tương đối rõ và nhỏ | Xem chi phí chậm trễ thực; không tự ưu tiên vì dễ |

Bảng không khẳng định **ST-01 luôn đứng đầu trong mọi bối cảnh**. Nếu tổ chức phát hiện một sự cố đang ảnh hưởng an toàn, hoặc một nghĩa vụ hợp đồng khác sắp đến hạn, thứ tự có thể thay đổi. Điều cần giữ là **nguyên tắc ra quyết định được giải thích bằng căn cứ**, không phải bằng chức danh của người gửi yêu cầu.

### 6.3. Quyền chọn thứ tự và quyền từ chối cam kết không khả thi

Khách hàng nên có khả năng nói: “Điều quan trọng nhất là xử lý đăng nhập của người mua”. Developers có trách nhiệm nói: “Để làm đúng điều đó chúng tôi cần kiểm tra phân quyền, nguồn dữ liệu và điều kiện lỗi; với năng lực hiện tại cần chia thành những phần sau”.

Nếu bên kinh doanh yêu cầu mọi item ưu tiên cao phải hoàn tất trong một tuần, Developers không nên bịa ước lượng để giữ hòa khí. Hai bên cần **chọn phạm vi phù hợp, thay đổi phương án hoặc công khai rủi ro**.

### 6.4. Thời hạn cố định không đồng nghĩa toàn bộ phạm vi cố định

Một kỳ khai giảng có ngày không thể dời. Khách hàng và Developers có thể phân loại:

- **Bắt buộc:** luồng đăng ký hợp lệ, đúng quyền, trạng thái đáng tin, kiểm soát an toàn theo nghĩa vụ.
- **Có thể thương lượng:** phương thức thanh toán bổ sung, gợi ý khóa học nâng cao, trang báo cáo tùy biến.
- **Cần kiểm chứng trước:** khả năng tích hợp, dữ liệu migration, điều kiện phê duyệt hoặc vận hành.
- **Phương án dự phòng:** giới hạn đối tượng hoặc kênh triển khai khi phù hợp, không mở tính năng chưa an toàn.

**Không được đánh đổi chất lượng hoặc nghĩa vụ bắt buộc** để đưa thêm story vào một mốc ngày cố định. Khi cả ngày, ngân sách và mọi phạm vi bị khóa trong điều kiện bất định cao, cần thông báo giới hạn và yêu cầu người có thẩm quyền quyết định các phương án khả thi.

## 7. Ví dụ và acceptance tests nối kỳ vọng với phần mềm chạy thật

Khách hàng thường dùng những từ như “nhanh”, “thân thiện”, “đăng ký thành công”, “dễ quản lý”. Những từ đó có thể che nhiều cách hiểu khác nhau. XP khuyến khích xác nhận kỳ vọng bằng **ví dụ cụ thể và kiểm thử chấp nhận**.

### 7.1. Phân biệt điều khách hàng muốn, tiêu chí và bằng chứng

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| Nhu cầu / mục tiêu | Người học cần làm gì và vì sao? | Biết khi nào có thể bắt đầu khóa đã mua |
| User story | Năng lực nào được đề xuất? | Xem trạng thái đơn và quyền truy cập |
| Acceptance criteria | Điều kiện nào phải đúng để chấp nhận hành vi? | Đơn đang chờ không được hiển thị đã thanh toán |
| Acceptance test | Tạo tình huống nào để kiểm tra điều kiện? | Giả lập giao dịch chờ và mở chi tiết đơn |
| Bằng chứng kiểm chứng | Kết quả thực tế trên phiên bản/môi trường nào? | Test tích hợp ghi trạng thái đúng, có link run và dữ liệu thử |
| Outcome | Người dùng thực sự có hiểu trạng thái và tự xử lý được không? | Ít người liên hệ hỗ trợ vì không biết đơn đang chờ |

**Một tiêu chí chấp nhận được viết ra không phải bằng chứng test đã chạy.** Một test pass cũng không chứng minh rằng mọi rủi ro hoặc giá trị người dùng đều được kiểm tra.

### 7.2. Cùng viết acceptance criteria cho một story

**Story ST-02:** Là học viên đang thanh toán, tôi muốn thấy trạng thái giao dịch rõ ràng để biết đã có quyền học hay cần chờ.

| ID | Tiêu chí chấp nhận minh họa |
|---|---|
| **AC-01** | Khi nhà cung cấp chưa xác nhận giao dịch thành công, hệ thống hiển thị trạng thái đang xử lý theo quy tắc đã thống nhất, không khẳng định đã thanh toán. |
| **AC-02** | Chỉ khi có kết quả xác nhận hợp lệ theo chính sách, hệ thống mới đánh dấu giao dịch thành công và cấp quyền học tương ứng. |
| **AC-03** | Sự kiện thanh toán lặp không khiến hệ thống tạo bản ghi hoặc quyền học sai. |
| **AC-04** | Khi giao dịch thất bại, hệ thống hiển thị thông tin phù hợp, không cấp quyền sai và nêu hướng xử lý nếu có. |
| **AC-05** | Học viên A không thể xem hoặc sửa trạng thái đơn của học viên B qua giao diện/API. |
| **AC-06** | Khi dịch vụ phụ thuộc bị lỗi, giao diện không xác nhận thành công giả; dữ liệu nhạy cảm được bảo vệ theo chính sách. |

Các tiêu chí trên chỉ là **mẫu học tập**, chưa phải đặc tả thanh toán hoàn chỉnh. Trong hệ thống thật còn cần quy tắc hoàn tiền, timeout, reconciliation, tính nhất quán, ngưỡng hiệu năng và các nghĩa vụ liên quan.

### 7.3. Given–When–Then để giảm hiểu nhầm

Khi khách hàng nói “thanh toán thành công”, Developers và người kiểm thử có thể hỏi liệu chỉ cần người dùng bấm nút là đủ. Một ví dụ cụ thể giúp sửa ngay cách hiểu:

~~~gherkin
Feature: Hien thi trang thai dang ky khoa hoc

  Scenario: Thanh toan van dang cho
    Given hoc vien A da gui yeu cau thanh toan don D
    And nguon trang thai dang tin chua xac nhan thanh cong
    When A mo chi tiet don D
    Then he thong hien thi trang thai dang xu ly
    And he thong chua cap quyen hoc nhu da thanh toan

  Scenario: Xac nhan thanh toan hop le
    Given don D thuoc hoc vien A dang cho
    When he thong nhan va xac thuc su kien thanh toan thanh cong
    Then don D chuyen sang trang thai phu hop
    And quyen hoc duoc cap theo quy tac da thong nhat

  Scenario: Su kien lap
    Given don D da duoc xac nhan thanh cong
    When he thong nhan lai cung su kien xac nhan
    Then khong co ghi nhan thanh toan hoac quyen hoc trung sai

  Scenario: Khong doc duoc don cua tai khoan khac
    Given hoc vien B da dang nhap
    And don D thuoc tai khoan A
    When B yeu cau doc don D
    Then he thong tu choi theo chinh sach truy cap
    And khong de lo du lieu rieng cua A
~~~

Đây là **đặc tả bằng ví dụ**, không phải test thực thi. Khi dùng công cụ BDD như Cucumber, cần có mã bước chạy đúng logic và môi trường kiểm chứng phù hợp mới tạo bằng chứng. Không nên tự nhận tính năng an toàn chỉ vì một file Gherkin có kịch bản tên “Không đọc được đơn của tài khoản khác”.

### 7.4. Người có kiến thức nghiệp vụ, Developers và testers cùng tham gia

Một trao đổi ngắn theo ba góc nhìn, thường được gọi là **Three Amigos**, có thể hữu ích:

- **Nghiệp vụ/khách hàng:** trạng thái nào có ý nghĩa với người học và quy tắc nào bắt buộc?
- **Phát triển:** nguồn dữ liệu, tích hợp và tình huống lỗi nào quyết định hành vi?
- **Kiểm thử/chất lượng:** có thể tạo dữ liệu, kiểm tra phân quyền và quan sát kết quả bằng cách nào?

Tên gọi không bắt buộc đúng ba người. Với thanh toán, đội cần thêm chuyên gia bảo mật và vận hành. Với người dùng công nghệ hỗ trợ, cần xem khả năng truy cập. Mục tiêu là **hiểu chung điều đúng và điều chưa biết**, không phải tăng số chức danh tham dự.

### 7.5. Acceptance tests và Definition of Done bổ sung cho nhau

Acceptance tests trả lời: **Hành vi nghiệp vụ cụ thể có thỏa yêu cầu đã thống nhất không?**

Definition of Done (nếu đội dùng Scrum hoặc tiêu chuẩn chất lượng tương đương) trả lời: **Increment có đáp ứng những điều kiện chất lượng chung để được xem là hoàn tất không?**

Ví dụ, trang trạng thái đơn có thể qua acceptance tests nhưng chưa được tích hợp đầy đủ, chưa kiểm tra bảo mật áp dụng hoặc có lỗi hồi quy nghiêm trọng. Khi đó **chưa đạt Done theo chuẩn liên quan**, dù khách hàng thấy UI đúng mong muốn.

XP coi chất lượng kỹ thuật là điều kiện để có thể giao phần nhỏ và phản hồi nhanh. Khách hàng giúp chọn **giá trị**, còn đội không được nhầm **sự chấp thuận về nội dung nghiệp vụ** với việc được phép bỏ qua mọi tiêu chuẩn an toàn.

## 8. Nhịp tương tác với khách hàng: liên tục nhưng có trọng tâm

Một nhịp cộng tác hiệu quả không nhất thiết là “mỗi ngày họp hai giờ với khách hàng”. Điều cần thiết là **câu hỏi quan trọng được trả lời đúng lúc** và **quyết định thay đổi có thể được kiểm tra qua phần mềm thường xuyên**.

### 8.1. Những tình huống cần tương tác

| Thời điểm | Câu hỏi cần giải quyết | Hình thức có thể phù hợp |
|---|---|---|
| Khi đề xuất story mới | Ai có vấn đề gì, bằng chứng nào, giá trị kỳ vọng ra sao? | Trao đổi ngắn, phỏng vấn, quan sát tác vụ |
| Khi chuẩn bị lựa chọn story | Phạm vi nhỏ nhất, thứ tự ưu tiên và ngoại lệ quan trọng? | Planning Game, refinement, trao đổi nhóm nhỏ |
| Khi xuất hiện câu hỏi trong lúc viết mã | Quy tắc nào đúng; tác động tới story hiện tại? | Hỏi nhanh trực tiếp hoặc không đồng bộ có ghi quyết định |
| Khi có lát cắt chạy được | Hành vi có đúng kỳ vọng; còn trường hợp khó hiểu không? | Demo phần mềm tích hợp, acceptance tests, thử dùng |
| Khi chuẩn bị release | Phạm vi có hữu ích, an toàn và phù hợp mốc phối hợp không? | Quyết định chung với người có thẩm quyền và dữ liệu kỹ thuật |
| Sau khi người dùng tiếp cận | Tính năng có giải quyết vấn đề; cần ưu tiên gì tiếp? | Quan sát, phỏng vấn, dữ liệu sản phẩm, phản hồi hỗ trợ |

**Không phải mọi câu hỏi đều cần khách hàng ra quyết định.** Lựa chọn cấu trúc hàm, tên biến hoặc thư viện có thể là chuyện kỹ thuật. Đưa tất cả chi tiết kỹ thuật cho khách hàng sẽ khiến vòng phản hồi chậm và làm mờ trách nhiệm.

### 8.2. Cam kết về độ trễ phản hồi cần thực tế

Một thỏa thuận làm việc có thể nêu:

> “Với câu hỏi đang chặn một story đã chọn, đại diện nghiệp vụ sẽ cố gắng phản hồi trong cùng ngày làm việc; nếu vượt quyền, họ nêu người quyết định và mốc trả lời. Với câu hỏi không khẩn về story xa, câu trả lời có thể được gom vào phiên chuẩn bị backlog tiếp theo.”

Đây chỉ là **ví dụ chính sách giữa các bên**, không phải chuẩn thời gian XP. Độ trễ cần phù hợp múi giờ, mức quan trọng, năng lực và quy định. Điều hữu ích là biết **khi nào phải chủ động tháo chặn**, thay vì âm thầm chờ nhiều ngày.

### 8.3. Khách hàng có thể phản hồi không đồng bộ

Một mẫu hỏi ngắn:

~~~text
STORY: ST-02 — Trang thai thanh toan

CAU HOI:
  Khi doi tac chua xac nhan thanh cong, hoc vien co duoc mo bai khong?

VI DU:
  Don D da gui thanh toan, trang thai doi tac = PENDING.

PHUONG AN:
  A: Khong cap quyen, hien dang xu ly.
  B: Cap quyen tam co dieu kien.

RUI RO / HE QUA:
  A: Hoc vien can cho neu phan hoi cham.
  B: Can co quy tac xu ly khi giao dich that bai.

CAN QUYET:
  Quy tac nghiep vu va nguoi co quyen xac nhan.

MOC:
  Truoc khi nhom hoan tat acceptance tests cua story.

KET LUAN:
  [Quyet dinh, ly do, dieu kien, nguoi xac nhan, thoi diem.]
~~~

Một bản ghi như vậy giúp trao đổi rõ hơn qua múi giờ và tránh lần sau phải hỏi lại từ đầu. Khi câu hỏi quá phức tạp, cuộc gọi trực tiếp cùng ví dụ thực tế có thể nhanh hơn mười vòng nhắn tin.

### 8.4. Không đồng nhất phản hồi của một người với mọi người dùng

Khách hàng/đại diện sản phẩm có thể nắm mục tiêu kinh doanh nhưng không biết tất cả khó khăn của học viên. Vì vậy nên kết hợp:

- Quyết định ưu tiên của người có thẩm quyền.
- Thông tin từ người dùng cuối và nhân viên hỗ trợ.
- Bằng chứng định lượng hoặc định tính của hành trình sử dụng.
- Kiểm chứng rủi ro kỹ thuật và tuân thủ.

**Khách hàng có vai trò quan trọng trong quyết định nhưng không phải nguồn sự thật duy nhất về trải nghiệm thực tế.**

## 9. Thay đổi ưu tiên khi đang phát triển: minh bạch đánh đổi

Một điểm mạnh của XP là có thể tiếp nhận thông tin mới ở những vòng lặp ngắn. Nhưng nếu “khách hàng tham gia thường xuyên” bị hiểu thành **liên tục chen việc mới mà không bớt việc cũ**, nhóm sẽ có WIP cao, nhiều story dở dang và chất lượng giảm.

### 9.1. Quy trình xử lý yêu cầu thay đổi

Khi khách hàng muốn đưa một story mới lên trước:

1. **Xác nhận điều mới xuất hiện:** nhu cầu người dùng, sự cố, nghĩa vụ bắt buộc hay chỉ thay đổi sở thích?
2. **Làm rõ phạm vi và mức cấp bách:** trường hợp tối thiểu cần có là gì?
3. **Developers đánh giá tác động:** độ lớn, phụ thuộc, công việc đang mở, kiểm thử và rủi ro.
4. **Đưa ra các lựa chọn:** đổi thứ tự ở vòng lặp tới, thay story chưa bắt đầu, chia lại lát cắt hoặc thực hiện xử lý khẩn theo chính sách.
5. **Khách hàng/người có quyền lựa chọn đánh đổi:** story nào sẽ lùi, thay đổi hoặc dừng?
6. **Cập nhật quyết định và dự báo:** ai cần biết về ngày, phạm vi, chi phí hoặc điều kiện?
7. **Giữ chất lượng:** không gọi một story chưa kiểm chứng là hoàn tất chỉ vì cần chỗ.

### 9.2. Ví dụ thêm yêu cầu khi đội đã đầy năng lực

Trong vòng lặp một tuần, đội dự kiến hoàn tất:

- ST-01: Sửa lỗi cấp quyền sau thanh toán.
- ST-02: Hiển thị chính xác giao dịch đang chờ.
- ST-06: Cải thiện thông báo lỗi khi ghi danh.

Ngày thứ ba, khách hàng đề nghị bổ sung **ST-07: xuất file Excel mọi đơn hàng** vì một quản lý muốn xem dữ liệu.

Trao đổi hợp lý:

> **Developer:** “ST-01 đang kiểm chứng phân quyền, ST-02 đang tích hợp nguồn trạng thái. Nếu thêm ST-07 với phạm vi lớn, chúng tôi có nguy cơ không hoàn tất luồng đang theo đuổi trong tuần.”
>
> **Khách hàng:** “Tôi sẽ xác minh xem file Excel có phải nghĩa vụ trước thứ Sáu không. Nếu không, ưu tiên sửa lỗi truy cập và trạng thái; ST-07 để vòng tới sau khi làm rõ người dùng báo cáo.”

Nếu ST-07 là một nghĩa vụ pháp lý thực sự cần xử lý ngay, quyết định có thể khác; vẫn phải xem quyền hạn, rủi ro và phạm vi tối thiểu phù hợp. **Quan trọng là không biến mọi yêu cầu mới thành công việc tăng thêm miễn phí.**

### 9.3. Hạn chế thay đổi đang dở theo kiểu “đập đi làm lại”

Thông tin mới có thể làm một story đang triển khai không còn giá trị. Không nên cố hoàn tất chỉ vì đã bắt đầu; nhưng cũng không nên liên tục thay đổi mà không xem chi phí.

Hãy hỏi:

- Phần nào của story vẫn có ích và có thể hoàn tất thành lát cắt riêng?
- Những công việc đã làm có được giữ an toàn hoặc loại bỏ rõ ràng không?
- Việc đổi scope có ảnh hưởng phép kiểm thử và dữ liệu không?
- Ai có quyền quyết định dừng/đổi story?
- Những người liên quan có biết thay đổi thời điểm hoặc phạm vi release không?

**Một quyết định dừng có căn cứ có thể tiết kiệm nhiều công sức**, nhưng cần minh bạch hơn câu “khách hàng đổi ý” không kèm lý do.

### 9.4. Kết hợp XP với Scrum mà không nhầm quyền quyết định

Nhiều đội dùng thực hành XP trong Scrum:

| XP nhấn mạnh | Scrum cung cấp | Cách phối hợp |
|---|---|---|
| Khách hàng tham gia thường xuyên, Planning Game | Product Owner, Product Backlog, Sprint Planning | Product Owner làm rõ giá trị và thứ tự; Developers đánh giá kích thước và chọn công việc trong Sprint Planning |
| User stories và acceptance tests | Product Backlog Items, Increment, DoD | Trao đổi yêu cầu, kiểm chứng hành vi và giữ chất lượng |
| Small releases và phản hồi nhanh | Sprint, Sprint Review, Product Goal | Dùng Increment thật để kiểm tra; có thể phát hành trước Sprint Review nếu đủ điều kiện |
| TDD, CI, refactoring, pair programming | Scrum không quy định chi tiết kỹ thuật | Chọn thực hành để tạo Increment đạt DoD đều và an toàn |
| Cập nhật ưu tiên theo học tập | Product Backlog refinement | Điều chỉnh backlog khi có thông tin, giữ Sprint Goal và chất lượng trong Sprint |

**XP customer không đồng nhất về mặt thuật ngữ với Product Owner của Scrum**, dù một Product Owner có thể đảm nhận nhiều chức năng đại diện khách hàng. Nếu kết hợp, giữ rõ accountability Scrum: Product Owner quản lý Product Backlog hiệu quả, Developers quyết định kích thước PBI và cách thực hiện; Sprint Goal không được gây nguy hiểm bởi thay đổi chen ngang.

## 10. Sự tham gia khách hàng chỉ hữu ích khi đội có năng lực phản hồi kỹ thuật

Khách hàng phản hồi mỗi ngày nhưng code phải đợi kiểm thử hai tuần, tích hợp mỗi tháng hoặc không có cách phát hành nhỏ thì vòng phản hồi vẫn chậm. XP kết hợp **tương tác gần** với **các thực hành engineering** để giúp thay đổi yêu cầu có thể được thực hiện an toàn.

### 10.1. Test-Driven Development (TDD)

TDD thường đi theo vòng **Red → Green → Refactor**:

1. Viết một test nhỏ cho hành vi chưa được triển khai (Red).
2. Bổ sung mã tối thiểu để test đạt (Green).
3. Cải thiện cấu trúc mã mà vẫn bảo toàn hành vi (Refactor).

Ví dụ logic “không cấp trùng quyền học khi callback lặp” có thể được kiểm chứng bằng unit tests. Nhưng unit test không thay thế kiểm tra **API, dữ liệu, phân quyền và hành vi người dùng**. Khách hàng xác định quy tắc mong muốn; Developers chọn cách thực hiện và kiểm thử ở các lớp cần thiết.

### 10.2. Continuous Integration (CI)

Tích hợp thường xuyên với build và kiểm thử tự động phù hợp giúp phát hiện sớm thay đổi phá vỡ tính năng khác. Một acceptance test mới hoặc một quy tắc nghiệp vụ đổi cần được kiểm tra trên **phiên bản tích hợp** chứ không chỉ chạy trong máy cá nhân.

Một pipeline “xanh” chưa chắc chứng minh toàn bộ sản phẩm đúng: test có thể bị skip, mock quá nhiều hoặc bỏ qua lỗi quyền truy cập. Cần ghi rõ bằng chứng, giới hạn và các rủi ro còn mở.

### 10.3. Refactoring và thiết kế đơn giản

Nếu mỗi quyết định mới của khách hàng khiến Developers phải sửa hàng chục module, khả năng thích ứng sẽ giảm. Refactoring, thiết kế đơn giản và kiểm thử tin cậy giúp duy trì **chi phí thay đổi hợp lý**. Nhưng “đơn giản” không có nghĩa làm thiếu bảo mật hay bỏ khả năng xử lý lỗi quan trọng.

### 10.4. Pair programming, collective ownership và nhịp bền vững

Lập trình cặp hoặc cùng xem code có thể giúp chia sẻ kiến thức về một quy tắc nghiệp vụ khó. Quyền sở hữu mã chung, nếu được tổ chức có trách nhiệm, giảm việc một người duy nhất có thể sửa một thành phần. Nhịp làm việc bền vững giúp đội giữ khả năng phản hồi nhiều vòng, thay vì kiệt sức sau một đợt giao gấp.

Không có một kỹ thuật nào là “thuốc chữa” cho mọi đội. Cần chọn kỹ thuật từ vấn đề thực và đánh giá tác dụng của nó. **Sự tham gia thường xuyên của khách hàng và năng lực kỹ thuật đáng tin hỗ trợ lẫn nhau**: khách hàng đưa ra phản hồi có ích, Developers có thể đáp lại bằng phần mềm hoạt động được.

### 10.5. Kanban bổ sung thông tin về dòng công việc

Khi khách hàng liên tục cập nhật thứ tự, nhóm vẫn cần biết **khi nào nên bắt đầu thêm việc**. Kanban giúp giới hạn **Work in Progress (WIP)** và đo:

- **Throughput:** số item hoàn tất trong một khoảng thời gian.
- **Cycle time:** thời gian từ bắt đầu đến hoàn tất của item đã Done.
- **Work item age:** tuổi của item đã bắt đầu nhưng chưa Done.
- **WIP:** số item đang ở trong hệ thống chưa hoàn tất.

Các số liệu này hỗ trợ trao đổi năng lực và rủi ro với khách hàng. Ví dụ, một item đứng đầu backlog chưa tự động nên được kéo khi đội đang đầy WIP; có lúc **hoàn tất hoặc tháo chặn item đang làm** tạo giá trị hơn mở thêm.

## 11. Tình huống xuyên suốt: học viên tự đăng ký khóa học

> **Tất cả story, điểm ước lượng, mốc thời gian và kết quả trong tình huống này là giả định để học tập**, không phải dữ liệu vận hành của một sản phẩm có thật hoặc tiêu chuẩn của XP.

Một nhóm gồm bốn Developers, một người có chuyên môn kiểm thử và một đại diện khách hàng được giao nhiệm vụ cải thiện hành trình đăng ký khóa học. Người đại diện có quyền ưu tiên những thay đổi thông thường trong ngân sách đã thống nhất, nhưng các quyết định ảnh hưởng quy định thanh toán phải được xác nhận bởi người có thẩm quyền.

### 11.1. Bắt đầu bằng vấn đề thay vì danh sách chức năng

Khách hàng ban đầu đề nghị:

> “Xây checkout mới, hỗ trợ ba ví điện tử, gửi năm loại email và tạo dashboard báo cáo.”

Trong phiên trao đổi, Developers hỏi: “Học viên hiện đang mắc vấn đề gì? Là không có phương thức thanh toán hay không biết đơn đã được xác nhận?”

Qua phản hồi hỗ trợ và quan sát một số tác vụ, nhóm hình thành **giả thuyết**: nhiều học viên bỏ dở vì không hiểu trạng thái giao dịch và không biết khi nào được vào khóa. Dữ liệu chưa đủ để nói mọi học viên đều như vậy, nhưng đủ để chọn một thử nghiệm nhỏ có ích.

**Mục tiêu sản phẩm cho giai đoạn này:** giúp học viên đủ điều kiện tự hoàn thành đăng ký và vào bài đầu với trạng thái rõ ràng, đúng quyền và ít cần hỗ trợ.

### 11.2. Lập danh sách story ở mức vừa đủ

| Mã | User story / năng lực | Tác dụng kỳ vọng | Rủi ro hoặc phụ thuộc |
|---|---|---|---|
| **ENR-01** | Học viên ghi danh khóa miễn phí hợp lệ và mở bài đầu | Kiểm chứng luồng đăng ký đầu-cuối không phụ thuộc thanh toán | Quyền tài khoản và dữ liệu khóa |
| **ENR-02** | Học viên xem trạng thái đơn trả phí đúng | Giảm nhầm lẫn và yêu cầu hỗ trợ | Nguồn dữ liệu trạng thái và quy tắc chuyển |
| **ENR-03** | Học viên được cấp quyền khi giao dịch xác nhận hợp lệ | Tránh truy cập sai và giảm chờ | API đối tác, bảo mật, dữ liệu, kiểm thử |
| **ENR-04** | Hệ thống xử lý callback lặp hoặc đến muộn | Bảo vệ tính đúng đắn giao dịch | Idempotency, tính nhất quán và kiểm tra tích hợp |
| **ENR-05** | Thêm phương thức thanh toán B | Mở rộng lựa chọn người học | Sandbox chưa sẵn |
| **ENR-06** | Báo cáo quản trị nâng cao | Tối ưu công việc nội bộ về sau | Chưa chắc là trở ngại ưu tiên |
| **ENR-07** | Học viên tự xử lý trường hợp liên kết xác minh email hết hạn | Giảm yêu cầu hỗ trợ và giúp người dùng vào học | Chính sách token, chống lạm dụng |

Nhóm chưa cố viết mọi AC cho cả năm; tập trung làm rõ những story gần, có giá trị cao hoặc chứa rủi ro cần thử.

### 11.3. Developers ước lượng, khách hàng chọn và thương lượng

Giả sử đội dùng điểm tương đối **chỉ để trao đổi nội bộ**, không phải số giờ hoặc KPI. Sau làm rõ ban đầu:

| Story | Ước lượng tương đối giả định | Giá trị/ưu tiên khách hàng | Khả năng được chọn |
|---|---:|---|---|
| ENR-01 | 3 | Có ích để tạo luồng hoàn chỉnh, nhưng lượng người dùng miễn phí cần được xác nhận | Có thể chọn nếu phù hợp đối tượng |
| ENR-02 | 3 | Rất cao vì giảm nhầm lẫn đang quan sát | Ứng viên gần |
| ENR-03 | 5 | Bắt buộc để luồng trả phí hoạt động đúng | Cần kiểm chứng phụ thuộc |
| ENR-04 | 3 | Bắt buộc về tính đúng đắn của thanh toán | Cần phối hợp ENR-03 |
| ENR-05 | Chưa ước lượng tin cậy | Giá trị tiềm năng, chưa có sandbox | Spike trước khi cam kết triển khai |
| ENR-06 | 5 | Chưa phải trở ngại chính | Để sau |
| ENR-07 | 2 | Có thể ưu tiên nếu dữ liệu xác minh là trở ngại | Cần làm rõ chính sách |

Không nên **cộng 3 + 3 + 5 + 3** rồi xem đó là số ngày hoàn tất. Ước lượng tương đối chỉ có ích trong bối cảnh đội dùng nó, với các giả định và dữ liệu năng lực phù hợp. Hơn nữa, những điều bắt buộc cho **tính đúng đắn của cùng một luồng** có thể cần thực hiện cùng nhau; không tách ENR-03 khỏi các điều kiện chống xử lý trùng nếu việc đó tạo kết quả nguy hiểm.

### 11.4. Chọn một lát cắt đầu phù hợp nhu cầu thật

Nếu dữ liệu cho thấy đa số người dùng đang mua **khóa trả phí**, việc ưu tiên ENR-01 chỉ vì dễ hơn không chắc tạo nhiều giá trị. Khách hàng và Developers có thể thống nhất:

> “Lát cắt gần nhất là hiển thị đúng trạng thái giao dịch của đơn đang chờ và đã xác nhận trên một phương thức được hỗ trợ, đồng thời bảo vệ quyền truy cập. Chỉ tuyên bố hoàn tất khi các trường hợp lỗi trọng yếu được kiểm chứng.”

Tùy phụ thuộc, nhóm có thể quyết định triển khai ENR-02 trước để cải thiện **trạng thái hiện có**, hoặc ưu tiên spike cho ENR-03/04 nếu thiếu một nguồn xác nhận đáng tin. Quyết định dựa trên **giá trị, rủi ro và khả năng tạo bằng chứng**, không phải tên story.

### 11.5. Trao đổi ngắn trong lúc triển khai

Ngày đầu, một Developer hỏi:

> “Nếu đối tác trả PENDING và người học tải lại trang, chúng ta hiển thị gì?”

Khách hàng trả lời sau khi xác nhận quy tắc:

> “Hiển thị ‘Đang xử lý’ và giải thích người học chưa được cấp quyền; không báo giao dịch đã hoàn tất.”

Tester đưa ra ví dụ Given–When–Then; Developers cập nhật logic UI/API; bộ kiểm thử tích hợp kiểm tra trạng thái. Quyết định được ghi cùng story để những người làm sau hiểu **vì sao**.

Ngày tiếp, Developers phát hiện callback có thể được gửi hai lần. Đây là rủi ro kỹ thuật quan trọng; nhóm thảo luận để bổ sung tiêu chí tính đúng đắn, chạy kiểm chứng và xem tác động tới phạm vi. **Khách hàng không cần chọn giải pháp database**, nhưng cần biết nếu điều kiện mới ảnh hưởng dự báo hoặc trải nghiệm.

### 11.6. Giao phần mềm nhỏ và lấy phản hồi

Sau khi Increment đáp ứng tiêu chuẩn chất lượng áp dụng, nhóm cho một tập học viên phù hợp thử luồng trạng thái. Phản hồi giả định:

- Giao dịch “Đang xử lý” đã hiển thị đúng nhưng người học không biết khi nào nên kiểm tra lại.
- Một số người học tìm trạng thái ở trang khóa học thay vì trang lịch sử đơn.
- Nhân viên hỗ trợ nhận ít câu hỏi về “Đã thanh toán chưa?” trong nhóm thử nhưng vẫn nhận câu hỏi “Làm gì tiếp theo?”.

Nhóm phân biệt:

| Kết quả quan sát | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Acceptance tests đạt trên build đã kiểm tra | Hành vi theo AC đạt trong điều kiện test | Mọi lỗi tích hợp hoặc trải nghiệm đã được giải quyết |
| Người học trong nhóm thử hiểu trạng thái tốt hơn | Có dấu hiệu giải pháp hữu ích với nhóm này | Chắc chắn mọi học viên đều có cùng kết quả |
| Ít ticket hỗ trợ thuộc một loại câu hỏi | Có tín hiệu cần nghiên cứu thêm | Chính thay đổi này gây ra toàn bộ mức giảm nếu còn nhiều yếu tố khác |

**Verification** (xây đúng theo điều kiện) và **validation** (giải quyết đúng nhu cầu) bổ sung nhau. Khách hàng cùng đội dùng cả hai để điều chỉnh thứ tự.

### 11.7. Khách hàng đổi ưu tiên sau phản hồi

Sau thử nghiệm, người đại diện chọn ưu tiên:

1. Làm rõ thông báo và lối tìm trạng thái đơn.
2. Hoàn thiện xử lý trường hợp lỗi/callback lặp còn thiếu.
3. Xem lại nhu cầu ENR-07 theo dữ liệu hỗ trợ.
4. Giữ ENR-05 cho tới khi có sandbox phù hợp.
5. Lùi ENR-06 nếu không có nghĩa vụ cấp bách.

Đây không phải **thất bại vì kế hoạch ngày đầu thay đổi**. Nếu thay đổi được giải thích bằng dữ liệu và vẫn bảo vệ chất lượng, đội đang sử dụng phản hồi để giảm công việc không cần thiết.

### 11.8. Báo cáo ưu tiên bằng ngôn ngữ hiểu được

> **Mục tiêu:** người học đăng ký và hiểu đúng trạng thái để vào khóa an toàn.  
> **Đã kiểm chứng:** luồng trạng thái của phương thức A trên bản tích hợp, với các giới hạn test được công bố.  
> **Điều vừa học:** người học cần hướng dẫn bước tiếp theo và lối vào trạng thái dễ thấy hơn.  
> **Ưu tiên hiện tại:** hoàn thiện thông báo và tính đúng đắn giao dịch trước dashboard nâng cao.  
> **Rủi ro:** tích hợp phương thức B chưa có sandbox; cần thử nghiệm trước khi dự báo.  
> **Quyết định cần người có thẩm quyền:** phạm vi release đầu và điều kiện mở rộng nhóm sử dụng.  
> **Mốc xem lại:** sau khi có bằng chứng thử tích hợp và phản hồi của nhóm học viên kế tiếp.

Đây là báo cáo dựa trên hành vi và quyết định, không chỉ nói “đã hoàn thành 80% task”.

## 12. Khi việc khách hàng tham gia thường xuyên gặp khó khăn

### 12.1. Khách hàng bận, không trả lời câu hỏi

**Dấu hiệu:** story chờ quy tắc nghiệp vụ nhiều ngày; Developers phải tự chọn phương án.

**Ứng xử:**

1. Tách câu hỏi thật sự chặn công việc khỏi câu hỏi có thể để sau.
2. Viết ví dụ cụ thể và phương án kèm hệ quả, tránh hỏi mơ hồ “nhờ xem giúp”.
3. Thống nhất khung thời gian phản hồi thực tế, có người thay thế.
4. Với quyết định vượt quyền, tìm đường chuyển cấp phù hợp.
5. Hiển thị item bị chặn trên bảng, không lặng lẽ chuyển Done.
6. Nếu không thể nhận quyết định, xem lại thứ tự hoặc lựa chọn một việc khác theo năng lực và rủi ro.

**Không nên** buộc người đại diện làm việc ngoài giờ liên tục để bù cho thiếu phân quyền hoặc thiếu nhân lực sản phẩm.

### 12.2. Có nhiều khách hàng với ưu tiên đối lập

Ví dụ trưởng phòng kinh doanh muốn báo cáo doanh thu, hỗ trợ muốn sửa lỗi thông báo, bảo mật yêu cầu xử lý phân quyền, còn người học muốn tìm bài nhanh hơn.

**Ứng xử:** ghi rõ mục tiêu và nghĩa vụ bắt buộc, tập hợp bằng chứng, công khai chi phí chậm trễ và người có quyền xác định thứ tự. Có thể cần một Product Owner hoặc người đại diện sản phẩm có thẩm quyền thực, nhưng **không nhất thiết loại bỏ sự tham gia của các chuyên gia hoặc người dùng khác**.

### 12.3. Khách hàng thay đổi ý kiến mỗi ngày

Đừng gạt bỏ phản hồi mới; cũng đừng chấp nhận mọi thay đổi như nhiệm vụ bổ sung miễn phí.

**Ứng xử:** phân biệt phát hiện quan trọng với sở thích thay đổi, xem tác động đến phạm vi đang làm, ưu tiên giải quyết điều đe dọa chất lượng hoặc mục tiêu, thương lượng việc lùi/bỏ và ghi các quyết định. Vòng lặp ngắn có thể giúp nhận thay đổi vào thời điểm ít gây gián đoạn hơn.

### 12.4. Khách hàng muốn “nhanh trước, test sau”

Với yêu cầu xử lý tiền hoặc dữ liệu người dùng, thiếu kiểm thử hoặc phân quyền có thể tạo tác động nghiêm trọng. Đội cần nói rõ rủi ro và những điều kiện không được hạ, rồi đề xuất **lát cắt nhỏ hơn nhưng vẫn đúng và an toàn**.

Chấp nhận phạm vi nhỏ khác với chấp nhận sản phẩm chưa đạt chất lượng. Nếu một ngoại lệ cần được xem xét, phải theo cơ chế quản trị rủi ro của tổ chức; không biến yêu cầu của khách hàng thành bằng chứng phần mềm đã đúng.

### 12.5. Đại diện khách hàng hiểu giá trị nhưng không có dữ liệu người dùng

**Ứng xử:** bổ sung nghiên cứu người dùng, quan sát tác vụ, dữ liệu sản phẩm và phản hồi hỗ trợ. Một câu chuyện hấp dẫn của stakeholder vẫn có thể là giả thuyết; chưa nên xem như sự thật về toàn bộ khách hàng.

### 12.6. Khách hàng đòi chi tiết thiết kế kỹ thuật

Khách hàng có thể yêu cầu bảo mật, hiệu năng, giao thức đối tác hoặc tính tương thích bắt buộc. Nhưng các lựa chọn framework, cấu trúc lớp và implementation thường thuộc chuyên môn của Developers.

**Ứng xử:** chuyển cuộc trao đổi từ “phải dùng thư viện X” sang **ràng buộc và kết quả cần đạt** nếu thư viện chỉ là một gợi ý. Khi công nghệ là nghĩa vụ hợp đồng hoặc tiêu chuẩn thật, cần tôn trọng và kiểm chứng điều kiện ấy.

### 12.7. Nhóm làm việc ở nhiều múi giờ

Không nhất thiết đồng bộ thời gian theo một phòng làm việc vật lý. Có thể lập:

- Giờ chồng lấn cho quyết định có nhiều trao đổi.
- Mẫu câu hỏi và quyết định ngắn gọn.
- Môi trường thử chung, kết quả test gắn phiên bản.
- Người thay thế phù hợp khi đại diện vắng.
- Quy tắc cập nhật ưu tiên và thông báo thay đổi.

Chỉ tổ chức thêm cuộc họp không đồng nghĩa giảm thời gian chờ. Hãy đo **từ lúc một câu hỏi chặn công việc xuất hiện đến lúc được giải quyết**.

### 12.8. Khách hàng thuộc môi trường có nhiều quy định

Đối với sản phẩm có yêu cầu pháp lý, kiểm toán, y tế hoặc tài chính, đại diện khách hàng có thể không có quyền thay đổi mọi điều. XP vẫn hữu ích khi chuyên gia liên quan tham gia **sớm và thường xuyên**, nhưng các điều kiện bắt buộc phải được ghi và kiểm chứng theo đúng thẩm quyền.

Không dùng “cá nhân và tương tác” làm lý do bỏ qua chứng cứ, tài liệu hoặc phê duyệt cần thiết. Ngược lại, có thể cải tiến cách lưu bằng chứng, kiểm tra liên tục và chuẩn hóa hoạt động để giảm đợi tới cuối.

## 13. Đo hiệu quả cộng tác bằng tín hiệu có ý nghĩa

Đừng đánh giá khách hàng tham gia tốt chỉ bằng **số cuộc họp**, **số lần gửi tin nhắn**, **số story được ký duyệt** hoặc **số story point đội hoàn tất**.

### 13.1. Nhóm chỉ số cần quan sát

| Tín hiệu | Nó có thể giúp trả lời | Giới hạn |
|---|---|---|
| **Thời gian trả lời câu hỏi nghiệp vụ quan trọng** | Đội có phải chờ quá lâu để tiếp tục story không? | Không nên ép mọi câu hỏi phải trả lời ngay, nhất là khi cần xác minh chuyên môn |
| **Thời gian item bị chặn do thiếu quyết định** | Quy trình phân quyền và trao đổi có gây tắc nghẽn không? | Có thể do chính sách tổ chức ngoài quyền đại diện |
| **Số lần làm lại do hiểu nhầm quy tắc** | Ví dụ/AC có được trao đổi đủ sớm không? | Thay đổi do học được nhu cầu mới không nhất thiết là lãng phí |
| **Cycle time và work item age** | Những item nào đi qua dòng công việc chậm hoặc bị kẹt? | Cần thống nhất định nghĩa bắt đầu/kết thúc, loại item |
| **Increment đạt chuẩn hoàn tất** | Nhóm có giao phần mềm đúng và có thể dùng được không? | Không đủ để kết luận người dùng được lợi |
| **Lỗi phát hiện muộn/sau phát hành** | Ví dụ nghiệp vụ và kỹ thuật có bỏ sót trường hợp quan trọng không? | Cần xét mức nghiêm trọng, rủi ro và thay đổi hệ thống |
| **Thời gian đến phản hồi người dùng hữu ích** | Nhóm học được điều gì đủ sớm để đổi ưu tiên? | Cần phân biệt phản hồi đại diện và dữ liệu người dùng thực |
| **Outcome theo mục tiêu sản phẩm** | Người dùng có thực sự làm việc dễ hơn không? | Các biến động khác có thể ảnh hưởng; không vội gán quan hệ nhân quả |

Chỉ số là công cụ **điều tra hệ thống**, không phải thước đo phạt nhân viên hoặc so sánh các cá nhân có vai trò khác nhau.

### 13.2. Ví dụ tính độ trễ quyết định

Giả sử một đội ghi nhận bốn câu hỏi nghiệp vụ quan trọng trong tuần, được trả lời sau **2, 4, 1 và 5 giờ làm việc**. Độ trễ trung bình minh họa:

\[
\frac{2+4+1+5}{4}=3\ \text{giờ làm việc}
\]

Con số này **không phải chuẩn phải đạt**. Nếu một câu trả lời sau 5 giờ cần tham khảo chuyên gia bảo mật và ngăn rủi ro lớn, đó có thể là thời gian hợp lý. Nếu một câu hỏi nhỏ lặp lại mỗi ngày phải chờ ba ngày, nhóm nên xem cách phân quyền hoặc cập nhật tài liệu quyết định.

Chỉ báo độ trễ nên đọc cùng **độ quan trọng của câu hỏi, mức công việc bị chặn và chất lượng quyết định**.

### 13.3. So sánh trước–sau nhưng không suy luận vội

Giả sử sau khi cử đại diện khách hàng tham gia thường xuyên:

- Thời gian chờ quy tắc nghiệp vụ giảm.
- Số item bị trả về vì hiểu sai AC giảm.
- Thời gian đến bản demo tích hợp rút ngắn.
- Người dùng hoàn thành luồng đăng ký nhiều hơn.

Nhóm cần kiểm tra có thay đổi đồng thời nào khác như môi trường CI, cách chia story hoặc lưu lượng người dùng. Không nên khẳng định **chỉ một thay đổi về tần suất họp gây ra toàn bộ mức cải thiện**. Đánh giá thực dụng là xem **các thay đổi có đang tạo tín hiệu tốt nhất quán không**, rồi tiếp tục điều chỉnh.

## 14. Workshop 90 phút: khách hàng và Developers cùng lựa chọn ưu tiên

Một bài thực hành nhóm có thể tổ chức như sau (thời lượng chỉ minh họa, không phải nghi thức XP bắt buộc):

| Thời gian | Hoạt động | Kết quả cần có |
|---|---|---|
| **0–10 phút** | Giới thiệu mục tiêu sản phẩm và dữ liệu người dùng giả định | Cùng hiểu vấn đề, tránh bắt đầu bằng giải pháp |
| **10–25 phút** | Đóng vai khách hàng, Developer, tester, hỗ trợ; nêu câu hỏi và giả định | Danh sách điều chưa rõ, người cần quyết định |
| **25–40 phút** | Viết user stories và một số acceptance examples | Hành vi, ngoại lệ và điều kiện quan trọng |
| **40–55 phút** | Developers chia lát cắt, đánh giá độ lớn/rủi ro; khách hàng giải thích giá trị | Các lựa chọn có thể so sánh, không ép số chính xác giả |
| **55–70 phút** | Chơi Planning Game: chọn story trong giới hạn năng lực giả định | Phạm vi gần có lý do, những item để sau và phụ thuộc |
| **70–80 phút** | Tiêm tình huống mới: callback lặp hoặc sự cố phân quyền | Nhóm thương lượng thay đổi, giữ chất lượng |
| **80–90 phút** | Tổng kết và phản hồi | Quyết định, cách kiểm chứng, một cải tiến trong cộng tác |

### 14.1. Thẻ tình huống cho người đóng vai khách hàng

> “Tôi muốn học viên đăng ký được trước kỳ khai giảng. Tôi không chắc họ cần ba phương thức thanh toán. Tôi biết có nhiều yêu cầu hỗ trợ vì trạng thái đơn không rõ. Tôi có thể quyết định thứ tự tính năng trong phạm vi ngân sách, nhưng điều kiện về tiền và dữ liệu cần chuyên gia xác nhận.”

### 14.2. Thẻ tình huống cho Developers

> “Chúng tôi có thể triển khai một lát cắt trạng thái đơn nhỏ, nhưng chưa xác minh được callback lặp. Hãy đề xuất hai phương án, ước lượng độ lớn tương đối và nói rõ bằng chứng cần có trước khi gọi Done. Đừng chỉ nói ‘không làm được’.”

### 14.3. Thẻ tình huống cho người kiểm thử

> “Bạn cần yêu cầu khách hàng nêu rõ trạng thái thành công, chờ và thất bại. Hãy hỏi về tài khoản khác, dữ liệu trùng và khi dịch vụ phụ thuộc lỗi. Chỉ coi test là bằng chứng khi có kết quả chạy thực tế.”

### 14.4. Tiêu chí quan sát workshop

- Khách hàng có nêu được **mục tiêu và căn cứ ưu tiên** không?
- Developers có cung cấp **rủi ro và phương án lựa chọn**, thay vì chỉ nêu số giờ?
- Người kiểm thử có làm rõ hành vi quan trọng trước khi chọn story không?
- Khi story mới xuất hiện, nhóm có **thay đổi phạm vi có lý do**, không cộng thêm vô hạn?
- Có thể nói rõ phần nào là **prototype/spike**, phần nào có thể đạt Done không?
- Quyết định được ghi đủ để người vắng mặt hiểu vì sao chọn cách đó không?

## 15. Mẫu làm việc có thể dùng ngay

### 15.1. Mẫu câu chuyện trao đổi với khách hàng

~~~text
STORY / ID:

NGUOI DUNG / VAN DE:
  Ai dang gap kho khan gi?

GIA TRI MONG MUON:
  Hanh vi, ket qua nao can cai thien?
  Bang chung ban dau la gi?

PHAM VI DANG CAN NHAC:
  Bao gom:
  Khong bao gom:

VI DU / ACCEPTANCE CRITERIA:
  AC-01:
  AC-02:
  AC-03:

GOC NHIN DEVELOPERS:
  Uoc luong / do lon:
  Phu thuoc:
  Rui ro ky thuat:
  Phuong an chia nho:

CHAT LUONG BAT BUOC:
  Bao mat / du lieu / DoD / van hanh:

QUYET DINH UU TIEN:
  Chon / de sau / can nghien cuu:
  Ly do va nguoi co tham quyen:

BANG CHUNG CAN THU:
  Test / demo / quan sat nguoi dung:

MOC XEM LAI:
  Khi nao / sau su kien nao?
~~~

Mẫu này chỉ hỗ trợ cuộc trao đổi, không bắt buộc mọi story đều có đủ mọi trường. Với bug nhỏ và rõ, nhóm có thể dùng vài dòng và test. Với giao dịch tiền hoặc dữ liệu nhạy cảm, chi tiết cần tương xứng rủi ro.

### 15.2. Mẫu nhật ký quyết định ưu tiên

| Ngày/mốc | Điều mới học được | Phương án được cân nhắc | Quyết định và người có quyền | Tác động tới phạm vi/kiểm chứng | Mốc xem lại |
|---|---|---|---|---|---|
| Ví dụ: sau thử luồng thanh toán | Người học không hiểu trạng thái PENDING | Sửa thông báo hoặc thêm dashboard | Ưu tiên thông báo; đại diện sản phẩm xác nhận | Dashboard lùi; kiểm chứng trạng thái và khả năng sử dụng | Sau bản thử kế tiếp |
| Ví dụ: sau thử API sandbox | Callback có thể gửi lặp | Chọn thiết kế xử lý lặp và kiểm tra lại | Developers quyết định cách kỹ thuật; khách hàng chấp nhận tác động phạm vi | Bổ sung kiểm chứng idempotency trước khi phát hành | Sau kiểm thử tích hợp |

Nhật ký giúp giải thích **vì sao** backlog đổi, không dùng để khóa mọi quyết định trong quá khứ. Tránh sao chép thông tin qua nhiều bảng nếu công cụ đã có liên kết đáng tin.

### 15.3. Mẫu báo cáo ngắn sau mỗi bản giao nhỏ

~~~text
MUC TIEU:
  [Nguoi dung can lam duoc gi?]

DA HOAN TAT:
  [Hanh vi thuc su da tich hop va dat chuan chat luong]

BANG CHUNG:
  [Test, build, moi truong, demo, gioi han]

PHAN HOI:
  [Nguoi dung/khach hang da quan sat gi?]

NHUNG DIEU CHUA BIET:
  [Gia thuyet, phu thuoc, rui ro]

UU TIEN TIEP:
  [Thu tu, ly do, phuong an de sau]

QUYET DINH CAN XAC NHAN:
  [Ai co tham quyen, han phan hoi]
~~~

Một báo cáo hữu ích làm nổi bật **khả năng đã được giao và quyết định tiếp theo**, không chỉ % task hoàn tất.

## 16. Bài tập vận dụng

### Bài tập A — Phân định quyền quyết định

Trong Planning Game, khách hàng nói “Ưu tiên cao nhất là sửa lỗi cấp quyền sau thanh toán”. Sau đó họ yêu cầu “Developers phải dùng framework X và hoàn thành trong đúng một ngày; không cần kiểm thử vì khách hàng sẽ tự chấp nhận”.

**Yêu cầu:** Những phần nào thuộc quyết định giá trị của khách hàng, phần nào cần Developers quyết định? Nhóm nên phản hồi ra sao?

<details>
<summary>Gợi ý đáp án</summary>

Khách hàng có trách nhiệm xác định mức ưu tiên và giá trị sản phẩm trong phạm vi quyền hạn. Developers đánh giá công sức, rủi ro, cách triển khai và kiểm thử. Có thể hỏi framework X có phải ràng buộc thật hay chỉ là gợi ý. Đội cần nêu các điều kiện chất lượng bắt buộc và đề xuất lát cắt có thể hoàn tất với bằng chứng. Không thể tự nhận một ngày là khả thi hoặc bỏ kiểm chứng chỉ vì khách hàng yêu cầu.

</details>

### Bài tập B — Lựa chọn ba story khi năng lực có hạn

Giả sử một đội chỉ có khả năng hoàn tất **khoảng 6 điểm tương đối** trong vòng lặp tới, theo dữ liệu của chính đội:

| Story | Kích thước minh họa | Bối cảnh |
|---|---:|---|
| A — Sửa trạng thái đang chờ | 3 | Người dùng đang hiểu nhầm giao dịch |
| B — Thêm bộ lọc theo giảng viên | 2 | Có ích nhưng chưa cấp bách |
| C — Sửa lỗi phân quyền đơn | 3 | Có nguy cơ lộ dữ liệu |
| D — Dashboard quản trị tùy biến | 5 | Chưa có dữ liệu giá trị rõ |

**Yêu cầu:** Đề xuất lựa chọn và giải thích ai quyết định gì. Điều gì xảy ra nếu C phức tạp hơn ước lượng ban đầu?

<details>
<summary>Gợi ý đáp án</summary>

Một phương án hợp lý là ưu tiên C và A vì tính đúng đắn, an toàn và trở ngại đang quan sát, tổng kích thước giả định 6 điểm. Khách hàng/người có quyền ưu tiên chọn dựa trên giá trị và rủi ro; Developers xác nhận kích thước, phụ thuộc và khả năng đạt chất lượng. Nếu C lớn hơn dự kiến, nhóm cần minh bạch, làm rõ hoặc chia lại phạm vi nhưng không bỏ yêu cầu an toàn, thương lượng phạm vi còn lại và cập nhật dự báo. Điểm số không phải số giờ bảo đảm.

</details>

### Bài tập C — Một user story mơ hồ

Story: “Là người dùng, tôi muốn thanh toán nhanh và thuận tiện”. Khách hàng nói “Chỉ cần nút bấm hoạt động”.

**Yêu cầu:** Viết ít nhất năm câu hỏi nghiệp vụ và ba acceptance criteria quan sát được.

<details>
<summary>Gợi ý đáp án</summary>

Hỏi ai thanh toán, phương thức nào được hỗ trợ, trạng thái thành công đến từ đâu, khi nào cấp quyền, lỗi/đang chờ xử lý thế nào, callback lặp xử lý ra sao, dữ liệu riêng tư và giao dịch hết hạn theo quy tắc nào. AC có thể gồm: chỉ báo thành công sau xác nhận đáng tin; khi đang chờ không cấp quyền sai; sự kiện lặp không tạo giao dịch hoặc quyền trùng; tài khoản khác không được xem đơn. Nếu cần điều kiện “nhanh”, phải xác định ngưỡng, môi trường và cách đo theo bối cảnh.

</details>

### Bài tập D — Khách hàng vắng mặt

Đại diện nghiệp vụ chỉ tham gia cuộc họp đầu tháng, mọi câu hỏi đều phải đợi phản hồi sau 7–10 ngày. Developers bắt đầu tự quyết định quy tắc nghiệp vụ để giữ lịch.

**Yêu cầu:** Đề xuất một cơ chế thay thế khả thi cho đội phân tán, gồm quyền quyết định, mức ưu tiên câu hỏi và cách theo dõi cải thiện.

<details>
<summary>Gợi ý đáp án</summary>

Thống nhất một đại diện có quyền quyết định trong phạm vi thông thường và người thay thế; dùng khung giờ phản hồi cho câu hỏi đang chặn, mẫu câu hỏi có ví dụ và phương án, đường chuyển cấp cho quyết định vượt quyền. Ghi quyết định cạnh story để dễ tra cứu. Theo dõi thời gian từ câu hỏi quan trọng đến trả lời, work item age bị chặn và làm lại do hiểu nhầm, không chỉ số giờ họp.

</details>

### Bài tập E — Yêu cầu chen ngang khi sắp hoàn tất

Đội đang kiểm chứng hai story ưu tiên cao để phát hành nhỏ. Khách hàng đề nghị thêm báo cáo mới không có hạn bắt buộc và nói “chỉ một thay đổi nhỏ”.

**Yêu cầu:** Trình bày một cuộc thương lượng có trách nhiệm, không biến phản hồi khách hàng thành xung đột.

<details>
<summary>Gợi ý đáp án</summary>

Hỏi mục tiêu, người dùng báo cáo và mức cấp bách. Developers làm rõ độ lớn, phụ thuộc và ảnh hưởng tới những item đang kiểm chứng. Đưa lựa chọn: đưa báo cáo vào vòng tới, chia một lát cắt nhỏ, hoặc nếu thật sự cấp bách thì thay một hạng mục khác có lý do. Khách hàng xác định ưu tiên trong giới hạn quyền; đội giữ chất lượng và công khai dự báo mới. Không cộng thêm scope mặc định mà không thay gì khác.

</details>

### Bài tập F — Acceptance test xanh nhưng người dùng vẫn gặp khó

Nhóm có test xác nhận trạng thái “Đang xử lý” hiển thị đúng khi callback chưa tới. Người dùng vẫn mở nhiều ticket vì không biết cần chờ hay liên hệ hỗ trợ.

**Yêu cầu:** Phân biệt kết luận verification và validation; đề xuất một điều chỉnh và cách lấy bằng chứng.

<details>
<summary>Gợi ý đáp án</summary>

Verification có thể xác nhận trạng thái kỹ thuật đúng theo AC trong phạm vi test. Validation cho thấy trải nghiệm có thể chưa giải quyết nhu cầu hiểu bước tiếp theo. Khách hàng và đội có thể thử thông báo nói rõ việc cần làm và nơi xem lại trạng thái, kiểm tra với người dùng phù hợp, đo tỷ lệ hoàn tất và số yêu cầu hỗ trợ. Vẫn phải giữ kiểm tra trạng thái và quyền học đúng.

</details>

### Bài tập G — Nhiều stakeholders đưa ưu tiên đối lập

Marketing yêu cầu chiến dịch mới, hỗ trợ đề nghị sửa lỗi đăng ký, bảo mật phát hiện quyền truy cập sai, còn khách hàng mua sản phẩm muốn dashboard báo cáo. Developers nhận bốn lệnh “ưu tiên số một”.

**Yêu cầu:** Nêu cách thiết lập quyền quyết định, thứ tự xem xét và dữ liệu cần có trước Planning Game.

<details>
<summary>Gợi ý đáp án</summary>

Trước hết xác định nghĩa vụ an toàn bắt buộc và mức nghiêm trọng của lỗi phân quyền; xử lý theo thẩm quyền phù hợp. Người đại diện có quyền ưu tiên hoặc Product Owner tổng hợp giá trị/chi phí chậm trễ, phản hồi người dùng và ràng buộc thời gian. Developers nêu độ lớn, rủi ro và phương án chia nhỏ. Quyết định cuối cùng cần một cơ chế rõ, không cho các stakeholders áp lệnh trực tiếp mâu thuẫn lên từng Developer.

</details>

### Bài tập H — XP, Scrum và Kanban kết hợp

Một Scrum Team có Sprint Goal rõ, dùng Planning Game để làm rõ user story, TDD và CI để tạo Increment, đặt WIP limit = 2 ở Development. Giữa Sprint, Product Owner nhận thêm một yêu cầu cấp bách.

**Yêu cầu:** Cách tiếp cận nào thuộc XP, điều gì thuộc Scrum, và WIP limit giúp quyết định thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Planning Game, TDD và CI là các thực hành thường gắn với XP; Sprint Goal, accountability của Product Owner/Developers, Sprint Planning và DoD thuộc Scrum; kiểm soát WIP và các flow metrics có thể đến từ Kanban. Nhóm xem yêu cầu cấp bách có đe dọa Sprint Goal và chất lượng không, Developers thương lượng phạm vi với Product Owner khi cần, không mặc định kéo thêm nếu WIP đã đầy. Các khung/thực hành có thể bổ sung nhau khi trách nhiệm và chính sách rõ.

</details>

## 17. Checklist tự đánh giá sự tham gia của khách hàng trong XP

Hãy thử trả lời bằng những trường hợp thật, không chỉ bằng việc đội đã đặt lịch họp:

1. Đội có hiểu rõ **khách hàng/người đại diện** trong bối cảnh hiện tại là ai không?
2. Người đại diện có đủ quyền quyết định thứ tự trong phạm vi đã thống nhất không?
3. Người dùng cuối, hỗ trợ và chuyên gia có kênh cung cấp bằng chứng vào ưu tiên không?
4. Những câu hỏi nghiệp vụ đang chặn công việc có được trả lời đủ nhanh không?
5. Có người thay thế và đường chuyển cấp khi đại diện vắng mặt hoặc thiếu thẩm quyền không?
6. Mỗi story gần được chọn có mục tiêu người dùng và giá trị kỳ vọng rõ không?
7. Developers được tham gia làm rõ, chia nhỏ và đánh giá kích thước hay chỉ nhận task?
8. Khách hàng chọn ưu tiên dựa trên giá trị/rủi ro, hay chỉ theo người yêu cầu có tiếng nói lớn?
9. Các trường hợp thành công, lỗi, biên và ràng buộc quan trọng có được trao đổi trước khi xây không?
10. Có acceptance criteria và ví dụ kiểm chứng phù hợp với story không?
11. Khách hàng có thể xem Increment thật, không chỉ mockup hoặc báo cáo % code không?
12. Bằng chứng kiểm thử có gắn đúng phiên bản, môi trường và điều kiện không?
13. Đội có phân biệt acceptance nghiệp vụ, chất lượng/DoD và outcome người dùng không?
14. Khi một yêu cầu mới xuất hiện, các bên có nói rõ **việc nào sẽ lùi hoặc bỏ** không?
15. Có tôn trọng các giới hạn về bảo mật, dữ liệu, pháp lý và an toàn dù bị áp lực ngày giao không?
16. Các phản hồi quan trọng có làm thay đổi thứ tự backlog hoặc giả thuyết sản phẩm khi phù hợp không?
17. Đội có giao các phần nhỏ, tích hợp và có thể kiểm chứng thường xuyên không?
18. Có quá nhiều work items đang mở hoặc bị chặn vì chờ quyết định không?
19. Thời gian đến phản hồi có được đo và cải tiến, không chỉ số giờ khách hàng ngồi họp không?
20. Có một cách ghi ngắn gọn quyết định và lý do để người không tham gia cuộc trò chuyện vẫn hiểu không?
21. Lãnh đạo có bảo vệ quyền quyết định sản phẩm và hỗ trợ tháo phụ thuộc tổ chức không?
22. Nếu có nhiều customers, xung đột ưu tiên được giải quyết bằng cơ chế rõ thay vì Developers phải tự chọn không?
23. Các khoản đầu tư kỹ thuật cần thiết có được giải thích qua rủi ro và khả năng giao giá trị, thay vì luôn bị xem là “không có giá trị” không?
24. Khi số liệu mới không ủng hộ giả thuyết cũ, đội có đủ sự cởi mở để dừng hoặc đổi hướng không?

Không cần tạo thêm một biểu mẫu bắt buộc cho mọi câu hỏi. Hãy chọn **một điểm yếu đang làm phản hồi đến muộn** — chẳng hạn thiếu người trả lời quy tắc, ưu tiên mâu thuẫn hoặc demo không có Increment thật — và thử một cải tiến có thể quan sát sau vài vòng lặp.

## 18. Ghi nhớ

- **Khách hàng tham gia thường xuyên là thực hành trọng tâm của XP**, giúp rút ngắn khoảng cách giữa nhu cầu, quyết định và phần mềm chạy thực tế. On-Site Customer nhấn mạnh sự gần gũi về phản hồi và thẩm quyền, không bắt buộc cùng một địa điểm vật lý mọi giờ.
- **Planning Game là đối thoại giữa giá trị và khả năng thực hiện.** Khách hàng/đại diện sản phẩm nêu ưu tiên và kết quả mong muốn; Developers nêu kích thước, phương án và rủi ro. Kế hoạch có ích chỉ xuất hiện khi các góc nhìn được trao đổi trung thực.
- **User stories cần conversation và confirmation.** Mẫu story ngắn không thay thế những ví dụ nghiệp vụ, acceptance criteria và bằng chứng kiểm chứng.
- **Ưu tiên có thể đổi khi học thêm**, nhưng cần công khai đánh đổi về phạm vi, năng lực và thời điểm. Không coi mỗi ý kiến mới là công việc cộng thêm miễn phí.
- **Khách hàng không được thay thế trách nhiệm về chất lượng.** Có thể cắt biến thể không thiết yếu, không được bỏ kiểm soát bắt buộc hoặc đánh dấu Done cho phần mềm chưa kiểm chứng.
- **XP kết hợp tương tác với các năng lực kỹ thuật** như TDD, CI, refactoring, small releases và phát triển bền vững để có thể đáp lại phản hồi an toàn và nhanh.
- **Scrum và Kanban có thể bổ trợ:** Scrum cung cấp Product Owner, Sprint Goal, DoD và nhịp kiểm tra; Kanban cung cấp quản lý WIP và dữ liệu dòng công việc, trong khi XP đóng góp kỹ thuật và vòng trao đổi khách hàng.
- **Đừng đo sự cộng tác bằng số giờ họp.** Hãy quan sát độ trễ quyết định, công việc bị chặn, chất lượng Increment, thời gian đến phản hồi và kết quả thực tế của người dùng.

Khi khách hàng nêu một yêu cầu mới, thay vì lập tức hỏi **“Bao giờ chúng ta code xong?”**, hãy hỏi: **“Người dùng cần giải quyết vấn đề gì? So với các việc khác, điều này đáng ưu tiên thế nào? Đội có thể giao lát cắt nhỏ, an toàn và kiểm chứng được nào trước? Sau khi giao, bằng chứng nào sẽ khiến chúng ta giữ hoặc thay đổi quyết định?”** Cuộc trao đổi ấy chính là nền tảng của việc khách hàng tham gia thường xuyên trong XP.

## Tài liệu tham khảo định hướng

- **Kent Beck & Cynthia Andres, _Extreme Programming Explained: Embrace Change_ (ấn bản thứ hai)**: các giá trị, nguyên tắc và thực hành XP, vai trò của phản hồi và nhóm có sự tham gia của khách hàng.
- [Extreme Programming — giới thiệu và thực hành](http://www.extremeprogramming.org/): tài liệu nền về các thực hành XP như Planning Game, On-Site Customer, small releases và testing; đối chiếu bối cảnh trước khi áp dụng.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/): hợp tác với khách hàng, phần mềm hoạt động được và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm sớm, hợp tác thường xuyên giữa người kinh doanh và Developers, chất lượng kỹ thuật.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): Product Owner, Product Backlog, Sprint Goal, Increment và Definition of Done khi kết hợp thực hành XP với Scrum.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, WIP, throughput, work item age, cycle time và quản lý luồng.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): cách viết ví dụ hành vi Given–When–Then, phân biệt đặc tả với kiểm thử thực thi.
