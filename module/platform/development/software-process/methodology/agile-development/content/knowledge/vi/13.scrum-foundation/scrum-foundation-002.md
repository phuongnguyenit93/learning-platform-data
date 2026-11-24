# Chủ nghĩa kinh nghiệm và tư duy tinh gọn trong Scrum

## 1. Vì sao Scrum dựa trên kinh nghiệm và tư duy tinh gọn?

**Scrum** là một khung làm việc nhẹ giúp con người, nhóm và tổ chức tạo giá trị thông qua những giải pháp thích ứng cho các vấn đề phức tạp. Theo Scrum Guide, nền tảng lý thuyết của Scrum là **chủ nghĩa kinh nghiệm (empiricism)** và **tư duy tinh gọn (lean thinking)**.

Hai nền tảng này bổ sung cho nhau:

- **Chủ nghĩa kinh nghiệm** nhấn mạnh rằng kiến thức đến từ trải nghiệm và quyết định cần dựa trên những điều thực sự quan sát được. Khi không thể dự đoán chắc chắn mọi yêu cầu hoặc kết quả, nhóm làm một phần nhỏ, kiểm tra rồi điều chỉnh.
- **Tư duy tinh gọn** tập trung vào điều thiết yếu và giảm lãng phí. Nhóm hạn chế công việc không tạo giá trị, thời gian chờ, làm lại và những hoạt động khiến phản hồi đến muộn.

Hãy hình dung một đội phát triển nền tảng học trực tuyến nhận yêu cầu: “Hãy tăng tỷ lệ học viên quay lại học”. Nhóm có thể lập kế hoạch xây hệ thống gợi ý khóa học phức tạp trong ba tháng. Nhưng chưa có bằng chứng người học bỏ dở vì không tìm thấy khóa học mới. Họ cũng có thể bỏ dở vì không nhớ mình học đến đâu hoặc phải làm lại nhiều bước.

Với Scrum, nhóm có thể kiểm tra một giả thuyết quan trọng qua một **Increment** nhỏ, ví dụ cho học viên tiếp tục từ bài đang học. Sau khi đưa kết quả cho người dùng phù hợp trải nghiệm và xem phản hồi, nhóm mới quyết định có mở rộng hay thay đổi hướng. Đồng thời, tư duy tinh gọn giúp nhóm tránh xây cả hệ thống đề xuất khi chưa chứng minh rằng nó giải quyết trở ngại ưu tiên.

Điều đó gắn với mục tiêu của module **AGILE_DEVELOPMENT**: thích ứng nhờ phản hồi sớm, giao giá trị tăng dần, cải tiến liên tục; sử dụng user story, backlog, Scrum, Kanban, XP và các thước đo dòng công việc một cách phù hợp. Scrum không thay thế nhu cầu suy nghĩ về sản phẩm hay chất lượng kỹ thuật; nó tạo **khung kiểm tra và thích ứng** để những quyết định đó diễn ra minh bạch.

### Sau bài học, người học có thể

1. Giải thích empiricism và lean thinking, cùng sự khác biệt giữa ra quyết định dựa trên bằng chứng và lập kế hoạch theo giả định.
2. Diễn giải ba trụ cột của Scrum: **Transparency, Inspection, Adaptation**.
3. Liên hệ năm giá trị Scrum, ba trách nhiệm trong Scrum Team, ba artifact và ba commitment với hai nền tảng này.
4. Chỉ ra cách Sprint và các sự kiện Scrum tạo vòng phản hồi có nhịp, không biến chúng thành nghi thức báo cáo hình thức.
5. Áp dụng cách quan sát, giảm lãng phí, kiểm soát WIP và phản hồi để cải thiện kết quả sản phẩm và chất lượng làm việc.

## 2. Chủ nghĩa kinh nghiệm (empiricism) là gì?

**Empiricism** cho rằng việc hiểu hệ thống cần dựa vào **trải nghiệm thực và những gì quan sát được**, thay vì mặc định rằng mọi yếu tố đều có thể được biết hoặc dự báo chính xác ngay từ đầu. Trong phát triển phần mềm, nhóm phải ra quyết định dưới sự bất định: nhu cầu người dùng có thể được hiểu chưa đầy đủ, tích hợp gặp trở ngại, công nghệ có giới hạn chưa biết, hoặc một tính năng được bàn giao nhưng ít người dùng.

Điều đó không có nghĩa **không lập kế hoạch** hoặc **không suy luận trước khi làm**. Nhóm vẫn cần xác định mục tiêu, giả thuyết, rủi ro, phương pháp kiểm tra và một kế hoạch khả thi với thông tin đang có. Phần khác biệt nằm ở việc **kế hoạch luôn có thể được kiểm tra và điều chỉnh dựa trên bằng chứng mới**.

### 2.1. Phân biệt giả định, quan sát, diễn giải và quyết định

| Loại thông tin | Ví dụ với nền tảng học trực tuyến | Cần lưu ý |
|---|---|---|
| **Giả định** | “Học viên không quay lại vì khó tìm khóa học mới.” | Chưa phải sự thật; cần chỉ rõ cách kiểm tra. |
| **Quan sát** | “Nhiều phiên học kết thúc trước khi hoàn thành bài; một số học viên vào lại trang danh sách từ đầu.” | Cần biết nguồn dữ liệu, phạm vi và định nghĩa sự kiện. |
| **Diễn giải** | “Có thể người học gặp khó khi tiếp tục bài dang dở.” | Một quan sát có thể có nhiều nguyên nhân. |
| **Giả thuyết thử nghiệm** | “Nếu cho tiếp tục bài dang dở, nhiều người sẽ quay lại học thuận tiện hơn.” | Phải có hành vi hoặc tín hiệu để đánh giá. |
| **Quyết định tạm thời** | “Ưu tiên thử luồng ‘Tiếp tục học’ trước khi đầu tư vào gợi ý khóa học.” | Quyết định có căn cứ hiện tại và có thể xem xét lại. |

Một nhóm làm việc theo kinh nghiệm không đơn giản là “cứ thử đại rồi xem”. Nhóm cần đặt câu hỏi **đang cố học điều gì**, dữ liệu nào có ý nghĩa và điều gì sẽ khiến nhóm tiếp tục, thay đổi hoặc dừng một cách làm.

### 2.2. Khi nào empiricism đặc biệt hữu ích?

- **Nhu cầu biến động:** người dùng, thị trường hoặc quy định thay đổi và khó đặc tả hoàn toàn từ trước.
- **Giải pháp chưa rõ:** có nhiều phương án thiết kế, cần thử để biết cách nào giúp người dùng.
- **Tích hợp phức tạp:** hành vi thực tế của các hệ thống liên quan chưa thể xác nhận chỉ qua tài liệu.
- **Rủi ro chất lượng:** nhóm cần quan sát phần mềm chạy thật, lỗi, hiệu năng và tác động vận hành.
- **Phản hồi có giá trị:** mỗi phần bàn giao có thể được người dùng hoặc bên liên quan đánh giá để định hướng bước tiếp.

Với công việc có quy trình ổn định, yêu cầu được kiểm chứng tốt và ít bất định, dự báo chi tiết có thể hữu ích. Scrum không yêu cầu phủ nhận những tri thức đã đáng tin; nhóm chỉ không nên **đối xử với giả định chưa kiểm chứng như một sự thật cố định**.

### 2.3. Ra quyết định dựa trên kinh nghiệm không đồng nghĩa chạy theo số liệu

Một chỉ số thay đổi có thể do tính năng mới, mùa vụ, nhóm người dùng, nguồn truy cập hoặc sự cố thu thập dữ liệu. Ví dụ, số lượt nhấp nút “Tiếp tục học” tăng chưa chắc có nghĩa người học hiểu bài hơn hoặc hoàn thành khóa học nhiều hơn.

Vì thế, nhóm cần kết hợp **dữ liệu định lượng, phản hồi định tính và hiểu biết bối cảnh**, đồng thời nhận diện giới hạn của bằng chứng. Empiricism yêu cầu quyết định dựa trên điều quan sát được một cách có trách nhiệm, không biến bảng số liệu thành người ra quyết định tự động.

## 3. Ba trụ cột thực nghiệm của Scrum

Scrum triển khai empiricism qua ba trụ cột **Transparency (Minh bạch)**, **Inspection (Kiểm tra)** và **Adaptation (Thích ứng)**. Chúng hỗ trợ nhau theo một chu trình; thiếu một trụ cột, việc học hỏi dễ trở thành hình thức.

~~~mermaid
flowchart LR
    A["Minh bạch: trạng thái và mục tiêu dễ hiểu"] --> B["Kiểm tra: đối chiếu thực tế"]
    B --> C["Thích ứng: điều chỉnh kế hoạch hoặc cách làm"]
    C --> D["Increment và kết quả mới"]
    D --> A
~~~

### 3.1. Transparency — minh bạch để cùng hiểu thực tế

Minh bạch không đơn giản là mọi người nhìn thấy một bảng tác vụ. **Thông tin quan trọng phải được hiển thị và được những người sử dụng nó hiểu theo cách nhất quán**.

Ví dụ, một nhóm có bảng việc ghi “Done” cho chức năng đăng ký khóa học, nhưng “Done” chỉ có nghĩa lập trình viên đã viết xong mã. Người kiểm thử chưa kiểm tra thanh toán, đội triển khai chưa biết về cấu hình cần thay đổi, Product Owner lại nghĩ người dùng đã có thể sử dụng. Cả nhóm đang nhìn cùng một nhãn nhưng hiểu khác nhau; mức minh bạch thực chất rất thấp.

Một số cách tăng minh bạch:

- Thống nhất **Product Goal**, **Sprint Goal**, thứ tự Product Backlog và lý do ưu tiên.
- Có **Definition of Done** rõ ràng để các bên hiểu khi nào Increment thực sự hoàn thành.
- Cho thấy những hạng mục đang làm, đã hoàn thành, bị chặn, còn rủi ro và điểm chưa chắc chắn.
- Phân biệt kết quả đã thử với người dùng thật, kết quả trong môi trường thử và những giả thuyết chưa kiểm chứng.
- Ghi quyết định quan trọng, thay đổi phạm vi, phụ thuộc và nguyên nhân khi cần.

**Minh bạch không phải giám sát cá nhân.** Mục đích là tạo cái nhìn đúng về sản phẩm và dòng công việc để cùng ra quyết định, không phải tăng số bảng theo dõi hoặc bắt thành viên báo cáo từng phút.

### 3.2. Inspection — kiểm tra thường xuyên để phát hiện sai lệch

**Inspection** là việc kiểm tra các artifact Scrum và tiến độ hướng tới những mục tiêu đã thống nhất nhằm phát hiện biến động hoặc vấn đề không mong muốn. Cần kiểm tra đủ thường xuyên để vấn đề không tích tụ, nhưng không nhiều đến mức cản trở công việc.

Trong một Sprint, nhóm có thể kiểm tra:

- Tiến độ thực tế hướng tới **Sprint Goal**, không chỉ số giờ đã làm.
- Increment có đáp ứng **Definition of Done** và hành vi người dùng mong đợi hay không.
- Product Backlog còn phản ánh ưu tiên, phản hồi và rủi ro hiện tại không.
- Những trở ngại như phụ thuộc, WIP cao, lỗi hồi quy hoặc chờ quyết định có đang gia tăng không.
- Phản hồi của người dùng có ủng hộ giả thuyết giá trị ban đầu không.

Kiểm tra phải đi đôi với khả năng nhìn thấy sự thật. Một cuộc họp mà thành viên chỉ dám báo “mọi việc ổn” để tránh bị trách phạt sẽ khó giúp nhóm phát hiện sai lệch.

### 3.3. Adaptation — điều chỉnh khi học được điều mới

Khi việc kiểm tra cho thấy kết quả hoặc cách làm không đạt kỳ vọng, nhóm cần **thích ứng sớm** để hạn chế sai lệch phát triển thêm.

Ví dụ:

- **Về sản phẩm:** phản hồi cho thấy học viên muốn tiếp tục bài dở hơn là nhận thêm gợi ý khóa học, nên Product Owner đổi thứ tự ưu tiên backlog.
- **Về phạm vi:** tích hợp đăng nhập bên ngoài phức tạp hơn dự kiến; Developers và Product Owner làm rõ hoặc thương lượng phần việc Sprint trong khi bảo vệ Sprint Goal.
- **Về chất lượng:** lỗi xác thực lặp lại; nhóm bổ sung kiểm thử thích hợp, sửa nguyên nhân và cập nhật Definition of Done khi cần.
- **Về cách phối hợp:** nhiều hạng mục chờ kiểm thử; nhóm thử giảm WIP, hỗ trợ kiểm tra sớm và xem lại hiệu quả sau vài chu kỳ.

**Kiểm tra mà không có thích ứng thường chỉ tạo ra báo cáo.** Ngược lại, thay đổi liên tục mà không kiểm tra kết quả cũng không phải empiricism: nhóm cần biết lý do đổi hướng và làm sao đánh giá quyết định mới.

### 3.4. Ví dụ ba trụ cột trên một hạng mục

Giả sử nhóm phát triển tính năng “Tiếp tục học từ bài gần nhất”:

| Trụ cột | Hành động | Kết quả mong đợi |
|---|---|---|
| Minh bạch | Story ghi rõ người dùng, tiêu chí chấp nhận; DoD gồm kiểm thử phục hồi tiến độ, đồng bộ và quyền truy cập. | Cả nhóm hiểu phần nào có thể xem là hoàn thành. |
| Kiểm tra | Cho học viên thử Increment; quan sát khả năng tìm nút, mở đúng bài và tiếp tục khi đổi thiết bị. | Phát hiện giả định đúng/sai và lỗi hành vi. |
| Thích ứng | Nếu nhiều học viên không nhận ra nút, thử cách hiển thị khác; nếu đồng bộ gây lỗi, xử lý trước khi mở rộng. | Quyết định tiếp theo dựa trên vấn đề đã quan sát. |

Ba trụ cột liên tục lặp lại khi sản phẩm phát triển; chúng không phải ba giai đoạn chỉ thực hiện một lần.

## 4. Tư duy tinh gọn (lean thinking) trong Scrum

**Lean thinking** tập trung vào những điều thiết yếu để tạo giá trị và giảm **lãng phí (waste)**. Trong phát triển phần mềm, lãng phí không chỉ là những thao tác vật lý thừa, mà còn là công việc đã bắt đầu nhưng chưa hoàn thành, chức năng không được dùng, chờ đợi, chuyển giao thông tin gây hiểu nhầm, sửa lỗi lặp lại hoặc đầu tư quá sớm vào một phương án chưa chắc có giá trị.

Lean **không có nghĩa cắt giảm con người, bỏ kiểm thử hay ép làm nhiều việc hơn trong một ngày**. Một hoạt động có vẻ không mang tính năng mới — như kiểm thử bảo mật, cải tiến hạ tầng hay trao đổi tiêu chí chấp nhận — vẫn có thể là thiết yếu để bảo vệ giá trị và giảm rủi ro lâu dài.

### 4.1. Nhận diện lãng phí trong dòng phát triển phần mềm

| Dạng lãng phí có thể gặp | Biểu hiện | Câu hỏi cải tiến |
|---|---|---|
| **Xây vượt nhu cầu** | Tạo nhiều màn hình và tùy chọn trước khi xác minh người dùng cần. | Có phần nhỏ nào kiểm chứng giá trị sớm hơn không? |
| **Chờ đợi** | Story chờ phê duyệt, môi trường, kiểm thử hoặc quyết định nghiệp vụ. | Đầu vào nào còn thiếu và có thể làm rõ sớm không? |
| **Công việc dở dang quá nhiều** | Mười story “đang làm” nhưng không story nào đạt Done. | Có thể ngừng bắt việc mới để hoàn thành việc cũ không? |
| **Bàn giao và chuyển ngữ cảnh** | Nhiều nhóm chuyển tài liệu qua lại, mỗi bên hiểu khác nhau. | Ai cần trao đổi trực tiếp và thống nhất ví dụ trước? |
| **Lỗi và làm lại** | Tích hợp muộn làm lộ lỗi nghiệp vụ hoặc thiết kế sai. | Có thể tích hợp, kiểm tra hoặc nhận phản hồi sớm hơn không? |
| **Xử lý không cần thiết** | Nghi thức, báo cáo hoặc tài liệu không hỗ trợ quyết định. | Hoạt động này giúp ai nhận biết hay thay đổi điều gì? |
| **Tri thức không được chia sẻ** | Chỉ một người hiểu thành phần quan trọng, cả nhóm phải chờ. | Có thể làm cặp, rà soát mã hoặc chuẩn hóa thao tác cần thiết không? |

Danh sách trên là các **biểu hiện thực hành**, không phải bộ quy tắc duy nhất để chấm điểm một nhóm. Lãng phí phụ thuộc bối cảnh: tài liệu cần cho vận hành an toàn không nên bị loại bỏ chỉ vì nhìn thấy như công việc gián tiếp.

### 4.2. Giảm kích thước lô công việc (batch size)

Giao một tính năng quá lớn có thể trì hoãn phản hồi nhiều tuần. **Phần tăng trưởng sản phẩm nhỏ nhưng dùng được** thường giúp:

- Kiểm tra hành vi và giá trị sớm hơn.
- Giảm lượng mã phải tích hợp cùng lúc.
- Giới hạn phạm vi lỗi khi một giả định sai.
- Giữ nhiều lựa chọn khi ưu tiên thay đổi.

Ví dụ, thay vì xây toàn bộ hệ thống “cá nhân hóa học tập”, nhóm có thể thử lần lượt: hiển thị bài học gần nhất, cho tiếp tục tiến độ, rồi xem phản hồi về gợi ý bài tiếp theo. Điều quan trọng là **chia theo kết quả có thể kiểm chứng**, không chỉ chia thành các tầng database, API và giao diện mà chưa có luồng người dùng hoàn chỉnh.

### 4.3. Hạn chế WIP và ưu tiên hoàn thành

**Work in Progress (WIP)** là lượng công việc đang được xử lý nhưng chưa hoàn tất theo định nghĩa thống nhất. WIP lớn có thể khiến mọi người bận rộn nhưng công việc liên tục chuyển ngữ cảnh và đợi người khác.

Ví dụ:

~~~text
Sẵn sàng  ->  Đang phát triển  ->  Đang kiểm tra  ->  Hoàn thành
                  WIP: 3              WIP: 2
~~~

Các giới hạn minh họa không phải quy định của Scrum. Nhóm có thể sử dụng **thực hành quản lý luồng của Kanban cùng Scrum** khi thấy phù hợp. Nếu kiểm thử đang nghẽn, việc hỗ trợ đưa story qua Done thường có giá trị hơn mở thêm tính năng mới.

Scrum không quy định WIP limit bắt buộc, nhưng việc chú ý công việc dở dang phù hợp với lean thinking và giúp nhóm duy trì nhịp phát triển bền vững.

### 4.4. Chất lượng ngay trong quá trình làm việc

“Giảm lãng phí” không nên dẫn tới loại bỏ kiểm thử hay bỏ qua nợ kỹ thuật. Khi lỗi được phát hiện muộn, nhóm phải tốn thêm thời gian tìm nguyên nhân, sửa và kiểm tra lại; đó có thể là nguồn lãng phí lớn.

Các thực hành thường giúp giảm việc làm lại gồm kiểm thử tự động phù hợp, tích hợp liên tục, rà soát mã, thiết kế đơn giản, tái cấu trúc và kiểm tra tiêu chí chấp nhận từ sớm. Scrum không bắt buộc một bộ thực hành kỹ thuật cụ thể; nhóm có thể kết hợp các thực hành **XP** để giữ Increment có thể thay đổi an toàn.

## 5. Empiricism và Lean hỗ trợ nhau như thế nào?

Hai nền tảng trả lời những câu hỏi khác nhau nhưng cùng phục vụ giá trị.

| Câu hỏi | Góc nhìn chủ nghĩa kinh nghiệm | Góc nhìn tinh gọn |
|---|---|---|
| **Nên làm gì tiếp?** | Dựa vào giả thuyết, bằng chứng, phản hồi và ưu tiên hiện tại. | Tập trung phần giá trị quan trọng nhất; tránh mở rộng không cần thiết. |
| **Làm ở quy mô nào?** | Chọn phần đủ nhỏ để học sớm và giảm rủi ro giả định sai. | Giảm batch size, WIP và thời gian chờ. |
| **Khi nào biết mình sai?** | Kiểm tra Increment và kết quả thực tế thường xuyên. | Giảm thời gian từ phát hiện vấn đề đến khắc phục. |
| **Đánh giá tiến bộ ra sao?** | Xem sản phẩm dùng được, outcome và bằng chứng. | Xem dòng công việc, chất lượng và phần lãng phí có thể giảm. |
| **Nếu bối cảnh thay đổi?** | Điều chỉnh Product Backlog hoặc kế hoạch dựa trên điều học được. | Tránh đầu tư quá sớm vào khối lượng việc chưa cần, giữ khả năng đổi hướng. |

Có thể hình dung một vòng lặp:

~~~mermaid
flowchart TD
    A["Giả thuyết về giá trị"] --> B["Chọn phần cần thiết nhất"]
    B --> C["Làm một Increment nhỏ, có chất lượng"]
    C --> D["Kiểm tra sản phẩm và dòng công việc"]
    D --> E{"Kết quả có ủng hộ giả thuyết?"}
    E -->|Có| F["Mở rộng hoặc chọn vấn đề kế tiếp"]
    E -->|Chưa hoặc không| G["Thay đổi phạm vi, giải pháp hoặc cách làm"]
    F --> A
    G --> A
~~~

**Lean giúp giảm chi phí của một vòng học hỏi; empiricism giúp xác định vòng học hỏi đó có dẫn tới quyết định đúng hơn không.** Nếu làm thật nhanh nhưng không học từ người dùng, nhóm có thể tạo nhiều sản phẩm sai. Nếu thu thập nhiều dữ liệu nhưng không hoàn thành phần mềm và không điều chỉnh quyết định, nhóm cũng không tạo ra giá trị tương xứng.

## 6. Năm giá trị Scrum tạo điều kiện cho empiricism

Scrum có năm giá trị: **Commitment, Focus, Openness, Respect, Courage**. Đây không chỉ là khẩu hiệu văn hóa; chúng làm tăng khả năng ba trụ cột hoạt động thực chất.

| Giá trị | Hành vi thường thấy | Liên hệ với nền tảng Scrum |
|---|---|---|
| **Commitment — Cam kết** | Cùng theo đuổi mục tiêu, làm rõ chất lượng và chủ động hoàn thành công việc. | Giữ trọng tâm vào Product Goal/Sprint Goal thay vì bảo vệ danh sách tác vụ bất kể giá trị. |
| **Focus — Tập trung** | Tập trung vào công việc cần thiết để đạt mục tiêu hiện tại. | Giảm WIP và chuyển ngữ cảnh không cần thiết. |
| **Openness — Cởi mở** | Nêu tiến độ thật, trở ngại, lỗi và điều chưa biết. | Tạo minh bạch và dữ liệu đủ tin để kiểm tra. |
| **Respect — Tôn trọng** | Lắng nghe các năng lực khác nhau và coi thành viên là người có trách nhiệm. | Hỗ trợ cộng tác, giảm đổ lỗi và tạo điều kiện học hỏi. |
| **Courage — Can đảm** | Dám nêu rủi ro, thách thức giải pháp cũ và thử cách mới có kiểm soát. | Giúp nhóm thích ứng khi bằng chứng trái kỳ vọng. |

Ví dụ, nếu thử nghiệm cho thấy chức năng nhóm vừa xây chưa giúp học viên quay lại nhiều hơn, nhóm cần **cởi mở** báo điều đó, **can đảm** xem lại ý tưởng và **tập trung** vào outcome thay vì cố giữ kế hoạch để chứng minh mình luôn đúng.

Khi các giá trị bị suy yếu, nhóm có thể chỉ báo tin tốt trong Daily Scrum, giấu lỗi trước Sprint Review hoặc biến Retrospective thành nơi quy trách nhiệm cá nhân. Các sự kiện vẫn diễn ra nhưng khả năng học hỏi bị hạn chế.

## 7. Các trách nhiệm trong Scrum Team hỗ trợ sự minh bạch và thích ứng

Scrum Team gồm **Product Owner, Scrum Master và Developers**. Đây là các **accountabilities (trách nhiệm chịu trách nhiệm về kết quả)** trong một đội tự quản và liên chức năng; không nên hiểu thành ba phòng ban bàn giao công việc tuần tự.

| Accountability | Trọng tâm | Cách hỗ trợ empiricism và lean |
|---|---|---|
| **Product Owner** | Tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog. | Làm rõ Product Goal, ưu tiên theo phản hồi và giá trị, giải thích lý do đổi hướng, tránh đầu tư vào chức năng ít cần. |
| **Developers** | Tạo các khía cạnh của Increment dùng được trong mỗi Sprint, lập kế hoạch và thích ứng công việc để đạt Sprint Goal, bảo đảm chất lượng. | Kiểm tra thực tế kỹ thuật, phối hợp để hoàn thành, phát hiện blocker sớm và đưa ra minh chứng về chất lượng. |
| **Scrum Master** | Thiết lập Scrum theo Scrum Guide và chịu trách nhiệm về hiệu quả Scrum Team. | Hỗ trợ các sự kiện có tác dụng kiểm tra–thích ứng, giúp nhóm và tổ chức giải quyết trở ngại, nuôi dưỡng minh bạch. |

Product Owner không phải người duy nhất được phép đặt câu hỏi về giá trị; Developers cũng cần hiểu người dùng, và mọi thành viên đều cần quan tâm chất lượng. Scrum Master không phải thư ký cuộc họp hay người quản lý giao việc hằng ngày. Việc trao đổi giữa các trách nhiệm hướng tới một **Scrum Team chung trách nhiệm tạo Increment có giá trị**.

### 7.1. Tự quản không có nghĩa thiếu cam kết

**Self-management** cho phép Scrum Team quyết định nội bộ ai làm gì, khi nào và như thế nào trong phạm vi trách nhiệm, mục tiêu và ràng buộc đã thống nhất. Nhóm không cần chờ một người ngoài phân công từng tác vụ, nhưng vẫn phải minh bạch kết quả, chất lượng và tiến độ hướng tới mục tiêu.

Một nhóm tự quản tốt có khả năng nói: “Với thông tin mới này, phạm vi dự kiến vượt năng lực; chúng ta đề xuất giữ Sprint Goal bằng cách đổi thứ tự hoặc loại bớt hạng mục ít quan trọng.” Đó là thích ứng có trách nhiệm, không phải né tránh nghĩa vụ bàn giao.

## 8. Artifact và commitment: khiến thực tế có thể kiểm tra

Scrum có ba artifact, mỗi artifact có một commitment tương ứng nhằm tăng minh bạch và tập trung vào điều cần kiểm tra.

| Artifact | Nội dung cốt lõi | Commitment đi kèm | Điều nhóm có thể kiểm tra |
|---|---|---|---|
| **Product Backlog** | Danh sách có thứ tự, liên tục được làm rõ, về những gì cần để cải thiện sản phẩm. | **Product Goal** | Công việc ưu tiên có còn hướng tới mục tiêu sản phẩm và giá trị mong muốn không? |
| **Sprint Backlog** | Sprint Goal, những Product Backlog Item được chọn và kế hoạch để bàn giao Increment. | **Sprint Goal** | Nhóm có tiến tới mục tiêu Sprint không; kế hoạch ngày hôm nay cần điều chỉnh thế nào? |
| **Increment** | Phần tăng trưởng sản phẩm cụ thể, dùng được và được tích hợp với các phần đã có. | **Definition of Done** | Công việc có thật sự hoàn thành theo tiêu chuẩn chất lượng chung không? |

### 8.1. Product Backlog không phải hợp đồng phạm vi bất biến

Product Backlog là một tập hợp **emergent** — có thể phát triển và được làm rõ khi nhóm hiểu thêm về sản phẩm và bối cảnh. Một yêu cầu được đưa vào backlog không đồng nghĩa chắc chắn sẽ được xây.

Ví dụ, sau khi quan sát người học sử dụng tính năng “Tiếp tục học”, Product Owner có thể đưa cải thiện đồng bộ tiến độ lên cao hơn một hệ thống huy hiệu thành tích chưa được kiểm chứng. Đó là thích ứng dựa trên giá trị, không phải thất bại của lập kế hoạch.

### 8.2. Sprint Goal tạo trọng tâm khi công việc thay đổi

Sprint Goal là mục tiêu duy nhất cho Sprint. Nó giúp Developers có sự linh hoạt về **công việc chính xác cần làm** trong khi vẫn theo đuổi một kết quả thống nhất.

Giả sử Sprint Goal là “Học viên có thể tiếp tục bài học dang dở một cách đáng tin cậy”. Nhóm dự kiến làm nút tiếp tục, đồng bộ tiến độ và thông báo hoàn thành. Nếu đồng bộ khó hơn dự kiến, nhóm có thể thương lượng phạm vi với Product Owner để bảo vệ mục tiêu cốt lõi. Không nên mặc định tăng ca hoặc xem một danh sách tác vụ bất biến là quan trọng hơn Sprint Goal.

Scrum không cổ vũ thay đổi tùy tiện làm nguy hiểm Sprint Goal trong Sprint. Khi học được điều mới, phạm vi có thể được làm rõ và thương lượng với Product Owner; chất lượng không được giảm để giữ tiến độ.

### 8.3. Definition of Done ngăn “hoàn thành trên giấy”

**Definition of Done (DoD)** là mô tả chính thức về trạng thái của Increment khi đáp ứng các tiêu chuẩn chất lượng yêu cầu đối với sản phẩm. Nếu một Product Backlog Item chưa đáp ứng DoD, nó không được xem là một phần của Increment hoàn thành.

Với luồng tiếp tục bài học, DoD có thể liên quan đến kiểm thử tích hợp, tính nhất quán tiến độ, quyền truy cập, kiểm tra lỗi quan trọng, khả năng triển khai và tài liệu vận hành phù hợp. Tiêu chí chấp nhận riêng của story (ví dụ “mở đúng bài đang học”) bổ sung cho DoD, nhưng không thay thế tiêu chuẩn chất lượng chung.

**Không nên giảm DoD để bảng công việc trông có nhiều item Done hơn.** Việc đó tạo ra minh bạch giả và có thể dồn lỗi về sau, đi ngược cả empiricism lẫn lean thinking.

## 9. Các sự kiện Scrum tạo nhịp kiểm tra và thích ứng

Scrum có **Sprint** là sự kiện chứa các sự kiện còn lại: Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective. Sprint có độ dài cố định tối đa một tháng; Sprint mới bắt đầu ngay sau khi Sprint trước kết thúc. Các sự kiện là cơ hội chính thức để kiểm tra và thích ứng, nhưng chúng **không cấm nhóm trao đổi hoặc giải quyết vấn đề ngay khi xuất hiện**.

| Sự kiện | Trọng tâm kiểm tra | Khả năng thích ứng |
|---|---|---|
| **Sprint** | Tiến độ hướng tới Product Goal qua một nhịp phát triển ngắn, có mục tiêu. | Xây dựng một hoặc nhiều Increment dùng được, quản lý rủi ro trong khoảng thời gian giới hạn. |
| **Sprint Planning** | Giá trị và ưu tiên hiện tại, năng lực, kết quả Sprint trước, điều kiện kỹ thuật. | Thống nhất **vì sao Sprint có giá trị**, chọn **làm gì**, và lập kế hoạch **làm như thế nào**. |
| **Daily Scrum** | Tiến độ hướng tới **Sprint Goal** và khả năng hoàn thành kế hoạch của Developers. | Developers điều chỉnh Sprint Backlog/kế hoạch công việc hằng ngày. |
| **Sprint Review** | Kết quả Sprint và thay đổi bối cảnh với các bên liên quan. | Hợp tác đánh giá Increment, thảo luận điều cần làm tiếp và điều chỉnh Product Backlog. |
| **Sprint Retrospective** | Con người, tương tác, quy trình, công cụ và chất lượng trong Sprint vừa qua. | Chọn cải tiến thiết thực để tăng hiệu quả và chất lượng. |

### 9.1. Sprint Planning: đưa giả định ra ánh sáng

Ở Sprint Planning, Product Owner bảo đảm người tham gia sẵn sàng thảo luận những Product Backlog Item quan trọng và chúng liên hệ thế nào với Product Goal. Toàn Scrum Team cùng xem vì sao Sprint này có giá trị. Developers chọn các hạng mục và lập kế hoạch thực hiện, dựa trên năng lực, kết quả đã biết và Definition of Done.

**Ví dụ:** thay vì nhận mục tiêu “hoàn thành sáu story”, nhóm thống nhất “người học có thể tìm thấy bài đang học và tiếp tục từ vị trí được lưu”. Mục tiêu giúp nhóm lựa chọn phạm vi, cân nhắc phụ thuộc và kiểm tra xem việc hoàn thành có thực sự tạo ra phần mềm hữu ích.

### 9.2. Daily Scrum: kiểm tra hướng tới mục tiêu, không đọc báo cáo cho quản lý

Daily Scrum là sự kiện **15 phút dành cho Developers** trong mỗi ngày làm việc của Sprint. Nó nhằm kiểm tra tiến độ hướng tới Sprint Goal và điều chỉnh Sprint Backlog/kế hoạch sắp tới.

Không có yêu cầu bắt buộc mỗi người phải trả lời đúng ba câu “hôm qua làm gì, hôm nay làm gì, vướng gì”. Các câu hỏi đó có thể hữu ích, nhưng nếu biến thành báo cáo thành tích cá nhân cho Scrum Master hoặc quản lý, nhóm dễ bỏ qua điều quan trọng: **cách phối hợp để đạt mục tiêu**.

Ví dụ, khi bộ kiểm thử phát hiện tiến độ học không đồng bộ giữa điện thoại và máy tính, Developers có thể cùng ưu tiên sửa rủi ro đó thay vì mỗi người tiếp tục một story mới.

### 9.3. Sprint Review: xem sản phẩm, đối chiếu thị trường và cập nhật ưu tiên

Sprint Review là một **phiên làm việc để kiểm tra kết quả Sprint và quyết định sự điều chỉnh trong tương lai**. Việc trình diễn tính năng có thể hỗ trợ, nhưng đây không chỉ là buổi trình chiếu cho bên liên quan.

Nhóm có thể cùng thảo luận:

- Increment hoàn thành đã tạo cơ hội sử dụng nào?
- Người dùng phản hồi thế nào; điều gì còn chưa được kiểm chứng?
- Bối cảnh kinh doanh, quy định hoặc hành vi người dùng có thay đổi không?
- Product Goal còn phù hợp không; thứ tự backlog nên thay đổi ra sao?

**Sprint Review không phải cổng phê duyệt bắt buộc trước khi phát hành.** Một Increment đủ điều kiện có thể được bàn giao cho bên liên quan trước khi Sprint kết thúc. Việc phát hành cần tuân theo rủi ro và quy trình sản phẩm, không bị buộc chờ buổi Review chỉ vì lịch nghi thức.

### 9.4. Sprint Retrospective: áp dụng lean vào chính hệ thống làm việc

Retrospective giúp Scrum Team kiểm tra các tương tác, quy trình, công cụ và Definition of Done đã hoạt động ra sao; chọn các thay đổi giúp nâng chất lượng và hiệu quả.

Ví dụ:

> “Ba story bị chặn ở khâu kiểm thử tích hợp vì dữ liệu thử chưa sẵn sàng; Sprint sau, nhóm sẽ chuẩn bị dữ liệu và kiểm thử API sớm hơn, đồng thời giảm số story đang mở.”

Đó là một **thử nghiệm cải tiến cụ thể**. Nhóm nên kiểm tra ở kỳ sau xem thời gian chờ có giảm và chất lượng có giữ được không. Nếu Retrospective chỉ tạo danh sách ý tưởng không ai thực hiện, nhóm có kiểm tra nhưng ít thích ứng.

### 9.5. Sơ đồ vòng học hỏi của Sprint

~~~mermaid
flowchart TD
    A["Product Goal và Product Backlog"] --> B["Sprint Planning: Sprint Goal, phạm vi, kế hoạch"]
    B --> C["Developers tạo Increment; kiểm tra chất lượng liên tục"]
    C --> D["Daily Scrum: kiểm tra và điều chỉnh kế hoạch"]
    D --> C
    C --> E["Sprint Review: kiểm tra kết quả và bối cảnh"]
    E --> F["Product Backlog được điều chỉnh"]
    C --> G["Sprint Retrospective: cải tiến cách làm"]
    G --> H["Cải tiến được đưa vào nhịp làm việc"]
    F --> A
    H --> B
~~~

Sơ đồ đơn giản hóa các vòng phản hồi: trong thực tế, trao đổi với người dùng, kiểm thử và điều chỉnh có thể diễn ra **bất kỳ lúc nào trong Sprint** khi phù hợp. Sprint Review là sự kiện gần cuối; Retrospective kết thúc Sprint.

## 10. Ví dụ xuyên suốt: cải thiện trải nghiệm quay lại học

**Tình huống và số liệu sau đây hoàn toàn giả định, chỉ dùng để minh họa cách thực hành Scrum theo chủ nghĩa kinh nghiệm và Lean.**

### 10.1. Vấn đề và giả thuyết ban đầu

Một nhóm phát triển nền tảng học lập trình muốn tăng tỷ lệ học viên quay lại khóa học sau lần truy cập đầu tiên. Ban đầu, một đề xuất là xây “hệ thống AI gợi ý bài học cá nhân hóa”.

Nhóm có một số quan sát từ phản hồi hỗ trợ: học viên phải đi qua danh sách khóa học rồi tìm lại bài đang học, đôi khi trạng thái giữa các thiết bị không nhất quán. Nhóm **chưa biết** đây có phải nguyên nhân chính khiến học viên bỏ dở hay không.

Giả thuyết cần kiểm tra:

> Nếu học viên thấy rõ bài học đang học dở và có thể tiếp tục từ vị trí phù hợp, họ sẽ quay lại học thuận tiện hơn và hoàn thành nhiều phiên học hơn.

Nhóm chọn thử một phần nhỏ thay vì cam kết xây toàn bộ hệ thống gợi ý. Đây là **lean** ở quyết định phạm vi và **empiricism** ở cách định nghĩa điều cần học.

### 10.2. Product Goal, Sprint Goal và backlog

Ví dụ mục tiêu sản phẩm:

> Giúp học viên theo đuổi lộ trình học và quay lại nội dung đang học một cách thuận tiện, đáng tin cậy.

Các Product Backlog Item có thể có:

| Hạng mục | Lý do và giá trị | Cần kiểm chứng |
|---|---|---|
| Hiển thị bài học đang dở trên trang khóa học | Giảm số bước tìm nội dung. | Người dùng có nhận ra và dùng điểm tiếp tục không? |
| Lưu vị trí học an toàn theo tài khoản | Người học tiếp tục trên cùng thiết bị. | Vị trí có chính xác sau khi thoát bất ngờ không? |
| Đồng bộ tiến độ giữa các thiết bị | Giữ trải nghiệm nhất quán. | Khi hai thiết bị cập nhật gần nhau, quy tắc nào thắng? |
| Thông báo nhắc học | Có thể hỗ trợ quay lại, nhưng cũng gây phiền. | Người dùng có muốn nhận và có kiểm soát tần suất không? |
| Gợi ý khóa học mới | Có thể có giá trị về sau. | Người dùng hiện thiếu gợi ý hay thiếu khả năng tiếp tục bài cũ? |

Ở Sprint đầu, nhóm thống nhất **Sprint Goal**: “Học viên có thể tìm lại và mở bài học đang dở trên cùng thiết bị”. Những hạng mục không cần cho mục tiêu được giữ trong Product Backlog, không bị coi là cam kết phải hoàn thành ngay.

### 10.3. Viết user story và tiêu chí chấp nhận

User story minh họa:

> Với vai trò là học viên đang theo một khóa học, tôi muốn thấy bài học gần nhất chưa hoàn thành để có thể tiếp tục mà không phải tìm từ đầu.

Ví dụ tiêu chí chấp nhận:

1. Khi mở trang khóa học đã có tiến độ, học viên thấy bài học phù hợp để tiếp tục.
2. Khi chọn “Tiếp tục”, học viên được chuyển đến đúng nội dung mà mình có quyền truy cập.
3. Nếu chưa có tiến độ, hệ thống cung cấp cách bắt đầu học rõ ràng, không hiển thị vị trí giả.
4. Khi tiến độ chưa lưu được, giao diện không đưa ra xác nhận sai và có cách xử lý phù hợp.
5. Nếu tài khoản không có quyền truy cập bài học, hệ thống không tiết lộ nội dung bị hạn chế.

Các tiêu chí phải được nghiệp vụ, phát triển và kiểm thử làm rõ thêm theo thiết kế và dữ liệu thực tế. Một story đủ đúng khuôn vẫn cần **Conversation và Confirmation** trước khi xem là hoàn thành.

### 10.4. Kiểm tra Increment rồi điều chỉnh

Khi Increment đã đáp ứng Definition of Done, nhóm mời một nhóm người dùng phù hợp thử chức năng và xem dữ liệu sử dụng.

| Tín hiệu giả định | Trước thay đổi | Sau thử nghiệm có giới hạn | Cần thận trọng |
|---|---:|---:|---|
| Tỷ lệ phiên quay lại mở tiếp bài học | 31% | 44% | Hai giai đoạn có thể khác nhau về nhóm người dùng hoặc thời điểm. |
| Tỷ lệ phiên bắt đầu rồi hoàn thành một bài | 38% | 41% | Mức thay đổi nhỏ; cần xem định nghĩa và khoảng biến động. |
| Phản hồi “không tìm lại được bài đang học” | Xuất hiện thường xuyên trong mẫu hỗ trợ | Ít được nhắc hơn trong mẫu thử | Số người phản hồi có thể khác; không tự suy rộng. |
| Lỗi đồng bộ tiến độ giữa thiết bị | Chưa được đo đầy đủ | Có trường hợp phát hiện khi kiểm thử | Chưa thể coi luồng đa thiết bị là sẵn sàng. |

Những số liệu này **không chứng minh quan hệ nhân quả**; nhóm cần xem chất lượng đo, quy mô, sự khác biệt giữa các nhóm và các yếu tố đồng thời.

Từ kết quả, Product Owner có thể ưu tiên thêm việc cải thiện tính nhất quán tiến độ trước tính năng gợi ý nâng cao. Developers chuẩn bị những phần kỹ thuật cần thiết và kiểm thử theo rủi ro. Scrum Master hỗ trợ nhóm giải quyết nút thắt trong cách làm và bảo đảm các cuộc trao đổi tạo điều kiện kiểm tra–thích ứng.

### 10.5. Cải tiến lean sau Sprint

Retrospective ghi nhận hai chuyện:

- Có nhiều hạng mục bị chờ ở bước kiểm thử tích hợp khi đồng bộ tiến độ.
- Một số thành viên bắt đầu tính năng mới trong lúc lỗi hồi quy của phần đang làm còn tồn đọng.

Nhóm thử **giảm WIP**, chuẩn bị các trường hợp kiểm thử tích hợp sớm và hỗ trợ nhau hoàn thành trước khi kéo thêm story mới. Ở Sprint tiếp theo, nhóm kiểm tra số hạng mục bị chặn, cycle time, lỗi sau phát hành và mức đạt Sprint Goal. Việc cải tiến được giữ hoặc sửa tùy kết quả thực.

Qua tình huống này, Scrum không chỉ giúp nhóm “giao một nút mới”, mà tạo cơ chế **chọn giả thuyết, bàn giao Increment, học từ dữ liệu rồi cải tiến cách làm**.

## 11. Đo lường phù hợp với empiricism và lean thinking

Chỉ số hữu ích khi chúng giúp đội trả lời câu hỏi và ra quyết định. Không nên dùng duy nhất story point, số commit, số giờ làm việc hay số story “đóng” để kết luận rằng giá trị đang tăng.

### 11.1. Ba nhóm tín hiệu cần quan sát cùng nhau

| Nhóm | Ví dụ | Câu hỏi hỗ trợ |
|---|---|---|
| **Giá trị/outcome** | Tỷ lệ học viên tiếp tục học, khả năng hoàn thành tác vụ, phản hồi người dùng. | Phần mềm có giải quyết đúng vấn đề không? |
| **Dòng công việc/flow** | WIP, cycle time, lead time, throughput, tuổi hạng mục đang mở. | Giá trị đi qua hệ thống với mức chờ và biến động nào? |
| **Chất lượng và tính bền vững** | Lỗi hồi quy, sự cố, việc làm lại, thời gian khôi phục, quá tải kéo dài. | Nhóm có thể giữ khả năng bàn giao an toàn ở các Sprint tiếp theo không? |

Các nhóm tín hiệu bổ trợ nhau. Throughput tăng có thể do chia hạng mục nhỏ hơn chứ không nhất thiết tăng giá trị. Một chức năng được người dùng thích nhưng thường làm mất dữ liệu cũng không thể xem là thành công bền vững.

### 11.2. Phân biệt những thước đo dòng công việc

- **WIP:** số hạng mục đang được xử lý nhưng chưa hoàn thành theo chính sách nhóm.
- **Cycle time:** thời gian từ khi hạng mục bắt đầu được xử lý đến khi hoàn thành theo định nghĩa.
- **Lead time:** có thể đo từ lúc yêu cầu được tiếp nhận/cam kết đến khi hoàn thành; nhóm phải ghi rõ hai mốc.
- **Throughput:** số hạng mục hoàn thành trong một khoảng thời gian.
- **Work item age:** thời gian một hạng mục đang mở đã nằm trong luồng xử lý.

Ví dụ, nếu WIP tăng từ 5 lên 12, cycle time trung vị kéo dài trong khi throughput gần như không đổi, nhóm có thể đang bắt đầu nhiều việc hơn khả năng hoàn thành. Đó là **tín hiệu cần điều tra**, không phải bằng chứng đủ để quy trách nhiệm cho bất kỳ cá nhân nào.

### 11.3. Đo outcome và guardrail

Để đánh giá chức năng “Tiếp tục học”, nhóm có thể xác định:

~~~text
Tỷ lệ tiếp tục bài học (%)
  = Số phiên quay lại và mở được bài đang dở hợp lệ
    / Số phiên quay lại có bài đang dở
    × 100
~~~

Trước khi sử dụng, cần làm rõ:

- **Đơn vị**: theo phiên, người dùng hay khóa học?
- **Baseline** và kỳ quan sát: dữ liệu trước thay đổi có cùng định nghĩa không?
- **Phân đoạn**: người mới, người học thường xuyên, thiết bị hoặc nhóm khóa học.
- **Guardrail**: lỗi mất tiến độ, hiển thị sai bài, truy cập trái quyền, trải nghiệm chậm.
- **Giới hạn dữ liệu**: sự kiện có bị thu thập thiếu hoặc phân loại sai không?

Nếu tăng tỷ lệ nhấp nút nhưng cũng tăng lỗi mất tiến độ, nhóm phải xem lại giải pháp. **Empiricism bao gồm cả bằng chứng bất lợi**, không chỉ chọn các con số đẹp để trình bày.

### 11.4. Velocity có vai trò giới hạn

Một số nhóm sử dụng **velocity** như thông tin hỗ trợ dự báo trong bối cảnh riêng, nhưng Scrum không bắt buộc dùng velocity hoặc story point. Story point không có đơn vị chuẩn giữa các đội; dùng nó để xếp hạng thành viên, so sánh các đội hoặc ép tăng điểm dễ tạo động cơ làm méo ước lượng.

Một nhóm tăng velocity nhưng bỏ kiểm thử để “Done” nhiều hơn đang làm suy giảm minh bạch và chất lượng. Hãy ưu tiên sản phẩm dùng được, outcome và khả năng thích ứng qua thời gian.

## 12. Những ngộ nhận về Scrum, empiricism và lean

| Ngộ nhận | Vì sao chưa đúng? | Cách hiểu hoặc thực hành phù hợp hơn |
|---|---|---|
| “Agile/Scrum không cần kế hoạch.” | Không có kế hoạch thì không có mục tiêu và giả thuyết để kiểm tra. | Lập kế hoạch với thông tin hiện có và cập nhật dựa trên bằng chứng. |
| “Empiricism là cứ làm đại rồi tính.” | Thử nghiệm vô định khó tạo tri thức đáng tin. | Đặt câu hỏi, giả thuyết, cách đo và điều kiện ra quyết định. |
| “Minh bạch là công khai từng giờ làm của mỗi người.” | Dễ tạo áp lực và che giấu vấn đề thực. | Minh bạch mục tiêu, chất lượng, tiến độ, rủi ro và trạng thái sản phẩm. |
| “Daily Scrum là báo cáo cho Scrum Master.” | Làm mất mục đích kiểm tra và điều chỉnh của Developers. | Developers dùng 15 phút để phối hợp tiến tới Sprint Goal. |
| “Review chỉ để Product Owner duyệt tính năng.” | Phản hồi bị giới hạn thành kiểm tra hình thức. | Kiểm tra Increment và bối cảnh, hợp tác điều chỉnh backlog. |
| “Retro là lúc kể lỗi của từng người.” | Giảm sự cởi mở, làm vấn đề hệ thống bị che khuất. | Cùng nhìn lại quy trình, công cụ, tương tác và thử cải tiến cụ thể. |
| “Lean là làm nhanh hơn bằng cách bỏ test.” | Lỗi và việc làm lại có thể tăng mạnh, giảm giá trị lâu dài. | Giảm lãng phí thật, giữ và cải thiện chất lượng tích hợp. |
| “Scrum bắt buộc WIP limit và một bảng Kanban.” | Scrum không quy định công cụ hay giới hạn WIP cố định. | Có thể kết hợp thực hành Kanban nếu giúp quản lý flow. |
| “Phải chờ Sprint Review mới được release.” | Review không phải cổng phát hành bắt buộc. | Có thể giao Increment đủ chất lượng trước thời điểm Review. |
| “Đã xong code nghĩa là Increment đã Done.” | Chưa chắc đáp ứng tiêu chuẩn chất lượng chung. | Chỉ tính hoàn thành khi đáp ứng Definition of Done. |
| “Sprint Goal là danh sách story bất biến.” | Mục tiêu và công việc dự kiến là hai thứ khác nhau. | Thương lượng phạm vi khi cần mà vẫn bảo vệ Sprint Goal. |
| “Tăng story point là tăng giá trị.” | Điểm ước lượng không trực tiếp đo trải nghiệm người dùng. | Kết hợp outcome, flow, chất lượng và phản hồi thực tế. |
| “Không được thay đổi trong Sprint vì Sprint cố định.” | Sprint cố định về thời lượng, không phải mọi chi tiết phạm vi. | Thích ứng có trách nhiệm; không gây nguy hiểm Sprint Goal và không giảm chất lượng. |

## 13. Cách triển khai một vòng học hỏi Scrum có chất lượng

Một nhóm có thể dùng tiến trình thực hành sau trong vài Sprint đầu; đây là **gợi ý tổ chức học tập**, không phải bộ sự kiện bổ sung bắt buộc của Scrum.

### Bước 1 — Chọn một vấn đề có ý nghĩa

Làm rõ nhóm người dùng, công việc họ muốn hoàn thành và giá trị cần tạo. Ghi **giả định** riêng với **bằng chứng**. Tránh bắt đầu bằng cam kết một công nghệ hoặc một danh sách tính năng chưa có căn cứ.

### Bước 2 — Nêu Product Goal và sắp Product Backlog

Product Owner giúp nhóm hiểu mục tiêu dài hạn, giải thích thứ tự ưu tiên và những rủi ro cần giải quyết. Product Backlog có thể chứa tính năng, thử nghiệm, lỗi và công việc kỹ thuật cần thiết; Scrum không bắt buộc tất cả phải có khuôn user story.

### Bước 3 — Lập Sprint Goal và chọn phần nhỏ, hoàn thành được

Tại Sprint Planning, nhóm dựa trên năng lực thật, tiêu chuẩn chất lượng, phụ thuộc và kết quả đã quan sát để lập kế hoạch. Nếu một story quá lớn, chia thành những phần có thể kiểm tra hoặc bàn giao giá trị.

### Bước 4 — Tạo Increment và kiểm tra liên tục

Developers phối hợp làm việc, tích hợp và kiểm thử sớm. Daily Scrum giúp kiểm tra hướng tới Sprint Goal; những trao đổi kỹ thuật hoặc nghiệp vụ cần thiết có thể diễn ra ngay ngoài sự kiện.

### Bước 5 — Đánh giá kết quả với bên liên quan

Ở Sprint Review, quan sát Increment và điều kiện kinh doanh mới, bàn về dữ liệu sử dụng hoặc thử nghiệm phù hợp. Không coi việc đã trình diễn là bằng chứng duy nhất rằng outcome đã đạt.

### Bước 6 — Cải tiến chính cách nhóm làm việc

Ở Retrospective, chọn một hoặc hai thay đổi có thể thử được: giảm WIP, chuẩn bị dữ liệu thử, làm rõ tiêu chí chấp nhận, tích hợp thường xuyên hơn. Thống nhất cách nhận biết chúng có giúp ích.

### Bước 7 — Lặp lại với bằng chứng mới

Điều chỉnh Product Backlog, cách dự báo hoặc thực hành kỹ thuật dựa trên điều học được. Nếu giả thuyết không được ủng hộ, thay đổi giải pháp hoặc mục tiêu khi có lý do rõ ràng; không cần bảo vệ một quyết định cũ chỉ vì đã đầu tư công sức.

## 14. Tự kiểm tra cách nhóm đang dùng Scrum

Nhóm có thể dùng những câu hỏi sau để thảo luận:

- [ ] Chúng ta có phân biệt **giả thuyết, dữ liệu quan sát và kết luận** hay không?
- [ ] Product Goal và Sprint Goal có được mọi người hiểu theo cùng một nghĩa không?
- [ ] Backlog phản ánh thông tin và ưu tiên mới, hay chỉ giữ nguyên một kế hoạch cũ?
- [ ] Definition of Done đủ rõ để phân biệt mã đã viết và Increment dùng được không?
- [ ] Daily Scrum có giúp Developers điều chỉnh kế hoạch hướng tới Sprint Goal không?
- [ ] Sprint Review có thực sự tạo trao đổi về kết quả và hướng sản phẩm tiếp theo không?
- [ ] Retrospective có dẫn tới cải tiến đã thử và được kiểm tra lại không?
- [ ] Có quá nhiều việc đang mở, thời gian chờ và chuyển ngữ cảnh không?
- [ ] Các thực hành chất lượng có giúp nhận phản hồi và sửa lỗi sớm không?
- [ ] Chúng ta có quan sát outcome người dùng cùng flow metrics và chất lượng không?
- [ ] Mọi người có an toàn để nói về rủi ro, sai lầm và bằng chứng trái kỳ vọng không?
- [ ] Khi thông tin đổi, nhóm có thật sự thay đổi ưu tiên hoặc cách làm không?

Nếu nhiều câu trả lời là “chưa”, nhóm nên chọn một vấn đề có ảnh hưởng lớn, thử thay đổi nhỏ và quan sát kết quả. **Tăng số lượng nghi thức mà không tăng minh bạch hoặc khả năng thích ứng thường không giải quyết nguyên nhân gốc.**

## 15. Kết luận

**Chủ nghĩa kinh nghiệm** giúp Scrum ra quyết định theo trải nghiệm và những điều quan sát được; **tư duy tinh gọn** giúp tập trung vào giá trị, giảm lãng phí và giảm chi phí của vòng phản hồi. Ba trụ cột **Minh bạch – Kiểm tra – Thích ứng** kết nối hai nền tảng này với công việc hằng ngày.

Scrum Team sử dụng năm giá trị Scrum, ba artifact cùng các commitment và nhịp Sprint để làm rõ mục tiêu, tạo Increment có chất lượng, kiểm tra thực tế và điều chỉnh. Những thực hành như chia nhỏ theo lát giá trị, tích hợp sớm, kiểm thử tự động, giới hạn WIP khi phù hợp và đo lường outcome có thể giúp tăng hiệu quả; chúng không thay thế bản chất của Scrum hoặc trở thành công thức cứng cho mọi đội.

Điểm cốt lõi không phải **giữ kế hoạch bằng mọi giá** hay **đóng nhiều story nhất**. Đó là tạo ra **phần mềm hữu ích, học sớm từ kết quả thực và liên tục cải tiến cách tạo giá trị** — đủ kỷ luật để đo được tiến bộ và đủ linh hoạt để đổi hướng khi bằng chứng thay đổi.
