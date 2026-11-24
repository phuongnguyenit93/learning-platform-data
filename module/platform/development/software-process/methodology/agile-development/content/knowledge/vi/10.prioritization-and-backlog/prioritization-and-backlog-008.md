# Ưu tiên và backlog: Kiểm soát yêu cầu cũ, trùng lặp và công việc ngoài luồng

Một Product Backlog có thể phát triển rất nhanh: khách hàng gửi thêm tính năng, bộ phận vận hành phản ánh lỗi, đội kỹ thuật đề xuất giảm nợ kỹ thuật, người quản lý chuyển tiếp các yêu cầu từ nhiều kênh. Nếu không thường xuyên làm rõ và ra quyết định, danh sách sẽ lẫn những việc đã lỗi thời, nhiều mục mô tả cùng một vấn đề, và cả những việc đã được thực hiện mà chưa từng xuất hiện trên bảng công việc. Khi đó nhóm khó xác định **việc nào thực sự quan trọng, vì sao phải làm và khả năng giao sản phẩm đáng tin cậy đến đâu**.

Trong mô-đun **AGILE_DEVELOPMENT**, Agile hướng đến phát triển phần mềm thích ứng thông qua phản hồi sớm, giao giá trị tăng dần và cải tiến liên tục. **Quản lý yêu cầu cũ, trùng lặp và công việc ngoài luồng** là một năng lực quan trọng để giữ sự minh bạch và ưu tiên của backlog. User story giúp nêu người dùng, nhu cầu và lợi ích; Scrum giúp kiểm tra, thích ứng với mục tiêu sản phẩm và mục tiêu Sprint; Kanban làm rõ dòng công việc, giới hạn WIP; kỹ thuật XP giúp giữ chất lượng khi cần đáp ứng các thay đổi mới.

Mục tiêu không phải giữ backlog “sạch” bằng cách đóng thật nhiều thẻ hoặc buộc mọi ý tưởng phải lập trình. Mục tiêu là có **một nơi quyết định ưu tiên đáng tin cậy**, giữ lại thông tin có ích, giảm trùng công việc và xử lý thay đổi khẩn cấp mà không che giấu tác động lên cam kết hiện tại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt yêu cầu **cũ**, **không còn phù hợp**, **bị trì hoãn có chủ đích**, **trùng lặp**, **liên quan nhưng khác phạm vi**, và **công việc ngoài luồng**.
2. Đề xuất quy trình tiếp nhận, sàng lọc, xác nhận nhu cầu, liên kết và ra quyết định cho backlog mà không làm mất dấu phản hồi quan trọng.
3. Dùng tiêu chí rõ để giữ, chia nhỏ, kết hợp, đóng hoặc xem lại các yêu cầu cũ.
4. Xử lý yêu cầu khẩn, gián đoạn phát sinh và công việc kỹ thuật bắt buộc bằng chính sách minh bạch.
5. Áp dụng nguyên tắc ưu tiên theo **giá trị, tác động của trì hoãn, rủi ro, công sức và độ chắc chắn của bằng chứng**.
6. Theo dõi các chỉ số thể hiện sức khỏe backlog và tác động của công việc không được lên kế hoạch, đồng thời tránh tối ưu chỉ số hình thức.
7. Thực hành một phiên refinement/triage dựa trên tình huống phát triển sản phẩm thực tế.

## 2. Phân biệt những loại vấn đề thường bị gọi chung là “backlog rác”

Không phải thẻ lâu ngày đều vô ích, không phải hai thẻ giống tên đều là trùng, và không phải yêu cầu đến giữa Sprint đều phải từ chối.

| Tình huống | Dấu hiệu | Câu hỏi cần kiểm tra | Hành động thường phù hợp |
| --- | --- | --- | --- |
| **Yêu cầu cũ (aged item)** | Được tạo từ lâu hoặc chưa được xem lại trong nhiều vòng | Nhu cầu, người yêu cầu và bối cảnh còn đúng không? | Xác nhận lại, giữ hoặc đóng có lý do |
| **Yêu cầu không còn phù hợp (obsolete)** | Nhu cầu đã mất, giải pháp bị thay thế, quy định đã đổi | Có còn giá trị nếu làm ngay hôm nay? | Đóng/loại khỏi danh sách ưu tiên, giữ lịch sử |
| **Cố ý trì hoãn (deferred)** | Có giá trị nhưng chưa đáng làm so với việc khác | Sự kiện hay tín hiệu nào sẽ khiến việc này cần xem lại? | Ghi điều kiện tái đánh giá, không hứa ngày hoàn tất vô căn cứ |
| **Trùng lặp (duplicate)** | Nhiều yêu cầu mô tả cùng một vấn đề hoặc hành vi, cùng nhóm người dùng và điều kiện chấp nhận gần như tương đương | Có thể thỏa mãn các yêu cầu này bằng cùng một kết quả không? | Chọn mục đại diện và liên kết nguồn |
| **Liên quan nhưng không trùng** | Cùng tính năng nhưng khác người dùng, quyền hoặc kịch bản | Có điều kiện chấp nhận hoặc lợi ích riêng không? | Giữ riêng hoặc gom dưới một hạng mục lớn, không xóa thông tin khác biệt |
| **Công việc ngoài luồng (untracked/unplanned work)** | Được yêu cầu hoặc thực hiện qua chat, cuộc gọi, sự cố, giúp đồng nghiệp mà không hiện trên luồng chính | Ai đang làm, tác động đến mục tiêu và năng lực nhóm ra sao? | Ghi nhận ở mức hợp lý, phân loại, điều phối, xem lại |
| **Khẩn cấp thực sự** | Sự cố sản xuất, lỗi an toàn, ràng buộc có hậu quả ngay nếu chậm | Mức tác động, giới hạn thời gian, phương án ứng phó là gì? | Kích hoạt chính sách khẩn, làm rõ việc bị thay thế và đánh giá hậu quả |
| **Nợ kỹ thuật cần thiết** | Rủi ro hoặc chi phí thay đổi tích lũy; có ảnh hưởng đến chất lượng hay dòng giao hàng | Điều gì đang bị ảnh hưởng, làm đến đâu thì đủ? | Ghi rõ mục tiêu, điều kiện hoàn tất và ưu tiên cùng công việc sản phẩm |

Một **nhãn trạng thái** trong công cụ không đủ để xác định bản chất của yêu cầu. Ví dụ, thẻ “Blocked” có thể chờ chuyên gia nghiệp vụ, chờ phụ thuộc kỹ thuật hoặc chờ một quyết định ưu tiên. Mỗi trường hợp cần hành động khác nhau.

### 2.1. “Cũ” là tín hiệu để hỏi, không phải lý do tự động xóa

Yêu cầu được tạo sáu tháng trước có thể còn quan trọng nếu liên quan tuân thủ hoặc hành vi cốt lõi. Ngược lại, một yêu cầu mới gửi hôm qua có thể đã lỗi thời vì sản phẩm vừa thay đổi. **Tuổi yêu cầu** chỉ cho biết nên kiểm tra lại mức độ phù hợp.

### 2.2. Trùng thông tin khác với trùng công việc

Hai khách hàng cùng phản ánh “không thấy trạng thái đơn hàng” có thể là **hai phản hồi độc lập cho cùng một vấn đề**. Nhóm có thể chỉ cần một backlog item để triển khai, nhưng nên giữ cả hai nguồn để biết mức độ phổ biến và các bối cảnh sử dụng.

Ngược lại, yêu cầu “học viên xem trạng thái đăng ký của mình” và “điều phối viên xem mọi đăng ký đang chờ” có thể cùng dùng dữ liệu trạng thái nhưng **khác vai trò, quyền truy cập và lợi ích**. Gộp bừa sẽ làm mất yêu cầu quan trọng.

## 3. Vì sao tồn đọng cũ và công việc ngoài luồng làm giảm khả năng thích ứng?

Khi backlog không được chăm sóc, nhóm có thể gặp những hệ quả sau:

- **Mất tín hiệu ưu tiên:** hạng mục không còn giá trị đứng lẫn với lỗi quan trọng, làm nhóm khó thấy nơi nên đầu tư.
- **Lập kế hoạch thiếu căn cứ:** một hạng mục được chọn vì “đã nằm ở đây lâu” nhưng chưa làm rõ người dùng, lợi ích hoặc cách kiểm chứng.
- **Làm trùng việc:** hai người triển khai hai giải pháp cho cùng vấn đề vì phản hồi được ghi ở hai nơi.
- **WIP và thời gian chờ tăng:** công việc được kéo vào liên tục qua tin nhắn mà không có quyết định bỏ hoặc trì hoãn việc khác.
- **Giảm niềm tin:** người yêu cầu không biết đề xuất được xem xét hay biến mất; người thực hiện không hiểu vì sao ưu tiên đổi liên tục.
- **Che khuất nợ chất lượng:** việc sửa lỗi, xử lý sự cố và hỗ trợ phát sinh không hiện trong thống kê, khiến năng lực Sprint hoặc throughput bị hiểu sai.

Ví dụ: nhóm lên kế hoạch làm năm story trong một tuần nhưng dành ba ngày xử lý lỗi khẩn và yêu cầu hỗ trợ ngoài bảng. Nếu chỉ báo “không hoàn thành kế hoạch vì nhóm làm chậm”, phân tích bỏ qua một nguyên nhân hệ thống quan trọng. Cần nhìn thấy công việc phát sinh cùng những quyết định điều chỉnh.

## 4. Thiết lập một điểm tiếp nhận và vết quyết định đáng tin cậy

Một **single source of truth** ở đây nghĩa là mọi yêu cầu cần ưu tiên đều **có thể được tra cứu và liên kết với một quyết định chung**. Nó không nhất thiết có nghĩa mọi phản hồi chỉ được gửi qua một ứng dụng. Nhóm vẫn có thể nhận từ email, buổi dùng thử, họp khách hàng, công cụ hỗ trợ hay chat.

### 4.1. Dòng xử lý tham khảo

~~~mermaid
flowchart TD
    A[Nhận yêu cầu từ các kênh] --> B[Ghi nguồn, vấn đề và tác động]
    B --> C{Có sự cố cần phản ứng ngay?}
    C -->|Có| D[Kích hoạt chính sách khẩn và ghi quyết định]
    C -->|Không| E[Phân loại và tìm mục liên quan]
    D --> H[Theo dõi việc khẩn trên bảng]
    E --> F{Trùng cùng một kết quả?}
    F -->|Có| G[Liên kết với mục đại diện, giữ phản hồi]
    F -->|Không| I[Kiểm tra nhu cầu và lợi ích]
    I --> J{Còn giá trị và đủ thông tin?}
    J -->|Chưa rõ| K[Yêu cầu làm rõ hoặc đặt mốc xem lại]
    J -->|Có| L[So sánh ưu tiên, chia nhỏ khi cần]
    J -->|Không| M[Đóng có lý do và cách mở lại]
    L --> N[Chọn vào luồng thực hiện theo năng lực]
    H --> O[Kiểm tra kết quả, ghi phản hồi]
    N --> O
    G --> O
    O --> P[Cập nhật quyết định và backlog]
~~~

Đây là **quy trình minh họa**, không phải một workflow cố định do Scrum quy định. Nhóm có thể dùng ít trạng thái hơn miễn câu hỏi **ai đã quyết định, quyết định gì, vì sao, và khi nào cần kiểm tra lại** được trả lời.

### 4.2. Thông tin tối thiểu cho một yêu cầu

| Trường | Để làm gì? | Ví dụ |
| --- | --- | --- |
| Mã hoặc liên kết ổn định | Tra cứu, liên kết phản hồi và tránh tạo thẻ mới không cần thiết | WS-142 |
| Người dùng/vấn đề | Hiểu nhu cầu thay vì chỉ tên tính năng | Học viên không phân biệt đăng ký đã nhận và đã xác nhận |
| Kết quả mong muốn | Đánh giá giá trị và cách kiểm chứng | Giảm hỏi lại tình trạng đăng ký |
| Nguồn và thời điểm | Truy vết hoàn cảnh, tôn trọng phản hồi | Buổi dùng thử ngày X, nhóm học viên Y |
| Tác động và mức khẩn | Phân biệt cơ hội với sự cố | Nhiều người hỏi lại, chưa mất dữ liệu |
| Trạng thái quyết định | Biết có làm, làm rõ, trì hoãn, đóng hay liên kết | Cần làm rõ |
| Người chịu trách nhiệm quyết định | Tránh yêu cầu bị bỏ quên | Product Owner/người được phân công |
| Liên kết liên quan | Tìm trùng, phụ thuộc và lịch sử | WS-121, phản hồi hỗ trợ số 87 |
| Điều kiện xem lại | Tránh thẻ trì hoãn tồn tại vô hạn | Sau 2 đợt dùng thử hoặc khi nhu cầu tăng |

Cần thu thập dữ liệu liên hệ của khách hàng theo quyền và mục đích cần thiết; không sao chép dữ liệu cá nhân vào nhiều thẻ để thuận tiện tìm kiếm.

### 4.3. Vai trò ra quyết định

Trong **Scrum**, **Product Owner** chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog. Công việc refinement có thể được phân chia, nhưng trách nhiệm về thứ tự ưu tiên không biến mất. **Developers** chịu trách nhiệm về Sprint Backlog và cách thực hiện công việc hướng tới Sprint Goal. **Scrum Master** hỗ trợ Scrum được hiểu và thực hiện hiệu quả, giúp nhận diện cản trở.

Ngoài Scrum, nhóm cần chỉ rõ người hoặc nhóm **có thẩm quyền ưu tiên** trong mô hình vận hành của mình. Người báo lỗi hoặc quản lý gửi tin nhắn không mặc nhiên có quyền chen mọi yêu cầu vào công việc đang làm. Các sự cố thực sự khẩn cấp cần một chính sách ứng phó rõ để không phải tranh luận quyền hạn khi sự cố đang diễn ra.

## 5. Kiểm soát yêu cầu cũ bằng tái xác nhận giá trị

### 5.1. Tạo lịch xem lại theo rủi ro, không theo một số ngày thần kỳ

Nhóm có thể xem những mục lâu chưa thay đổi hoặc chưa được xác nhận trong buổi refinement định kỳ. Chọn khoảng thời gian từ thực tế: luồng sản phẩm thay đổi nhanh cần xem thường xuyên hơn công việc hạ tầng dài hạn.

**Ví dụ chính sách khởi đầu:** mỗi hai tuần, xem các mục dự kiến đưa vào hai vòng tiếp theo; mỗi tháng, chọn một số mục trong vùng “đang chờ” có lần xác minh cuối cách đây hơn 60 ngày. Đây là ngưỡng **tự đặt để thử**, không phải chuẩn Agile bắt buộc.

Hai dấu thời gian hữu ích:
- **Ngày tạo:** yêu cầu bắt đầu xuất hiện khi nào.
- **Ngày xác nhận giá trị gần nhất:** lần gần nhất có bằng chứng nhu cầu còn tồn tại và điều kiện chưa thay đổi.

Một yêu cầu được sửa dấu câu hôm qua **không đồng nghĩa** giá trị đã được kiểm tra hôm qua. Nếu chỉ dựa vào ngày cập nhật kỹ thuật, nhóm có thể bỏ sót một yêu cầu đã lỗi thời từ lâu.

### 5.2. Năm câu hỏi để xử lý một mục tồn đọng

1. **Người dùng còn gặp vấn đề này không?** Phản hồi nào gần đây nhất xác nhận?
2. **Kết quả mong muốn có thay đổi không?** Có quy trình mới đã giải quyết phần lớn vấn đề?
3. **Độ khẩn và tác động hiện tại thế nào?** Có rủi ro an toàn, hợp đồng, chất lượng hay vận hành?
4. **Có mục khác đã xử lý hoặc sẽ xử lý cùng kết quả không?** Nếu có, liên kết thay vì triển khai hai lần.
5. **Nếu chưa làm, phải chờ điều kiện nào và ai có thẩm quyền quyết định lại?**

### 5.3. Các quyết định hợp lệ

| Quyết định | Khi dùng | Ghi nhận tối thiểu |
| --- | --- | --- |
| **Giữ và làm rõ** | Vẫn có giá trị nhưng thiếu ví dụ/ngữ cảnh | Câu hỏi mở, người cần trao đổi và mốc xem lại |
| **Giữ, ưu tiên lại** | Giá trị được xác minh và cần so sánh với backlog hiện tại | Lý do thay đổi thứ tự, tác động lên các mục khác |
| **Chia nhỏ** | Yêu cầu quá rộng, chứa nhiều hành vi hoặc khó kiểm chứng | Các lát cắt và liên kết mục gốc |
| **Trì hoãn có điều kiện** | Có giá trị nhưng chưa cần ngay | Điều kiện kích hoạt, người theo dõi, thời điểm xem lại |
| **Liên kết với mục đại diện** | Cùng một vấn đề/hành vi đã được ghi nhận | Mã canonical, nguồn phản hồi và chi tiết cần bảo toàn |
| **Đóng là không còn phù hợp** | Vấn đề biến mất, không còn tạo giá trị, đã bị thay thế | Lý do, bằng chứng và cách mở lại nếu tình huống đổi |
| **Đóng đã được xử lý** | Một chức năng hoặc sửa lỗi hiện tại đã đáp ứng nhu cầu | Liên kết phần bàn giao và cách kiểm chứng |

Đừng tự động xóa vĩnh viễn yêu cầu đã đóng khi chúng còn chứa bối cảnh và phản hồi hữu ích. Có thể **ẩn khỏi danh sách ưu tiên đang hoạt động** nhưng giữ lịch sử theo chính sách lưu trữ dữ liệu của tổ chức.

### 5.4. Đóng yêu cầu cũ một cách có trách nhiệm

Một phản hồi ví dụ:

> “Yêu cầu báo cáo số người đăng ký theo tuần đã được ghi nhận trước đây. Hiện nhu cầu này chưa nằm trong các mục có giá trị ưu tiên cao sau khi nhóm kiểm tra lại với điều phối viên. Chúng tôi lưu lại bối cảnh và sẽ xem xét lại nếu xuất hiện nhu cầu báo cáo định kỳ được xác nhận. Bạn có thể bổ sung tình huống mới vào mục đã lưu.”

Nếu quy trình công ty quy định cần xác nhận với bên yêu cầu trước khi đóng, hãy làm theo. Tránh lời hứa “chắc chắn sẽ làm trong quý tới” khi chưa có cam kết nguồn lực hoặc quyết định ưu tiên thật.

## 6. Nhận diện và xử lý trùng lặp mà không làm mất tín hiệu khách hàng

### 6.1. Phân loại mức độ giống nhau

| Loại | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Trùng hoàn toàn** | Hai thẻ cùng người dùng, hành vi, điều kiện và lỗi | Chọn một mục thực hiện; đóng mục trùng có liên kết hai chiều |
| **Cùng vấn đề, khác lời mô tả** | “Không thấy đăng ký” và “không biết mình đã được nhận” đều do trạng thái không rõ | Xác minh nguyên nhân; nếu cùng nhu cầu thì gom về một vấn đề |
| **Cùng chủ đề, khác đối tượng** | Học viên tra cứu đăng ký của mình; điều phối viên xem tất cả yêu cầu đang chờ | Giữ riêng hoặc tổ chức dưới nhóm lớn để bảo toàn quyền và lợi ích |
| **Một mục là phạm vi con** | “Quản lý đăng ký” và “cho học viên hủy trước hạn” | Liên kết mục cha–con, tránh đếm cả hai như hai lần giao cùng giá trị |
| **Phụ thuộc kỹ thuật** | “Đăng ký chống trùng” cần cơ chế ràng buộc dữ liệu | Liên kết phụ thuộc; chỉ gom nếu việc gom vẫn tạo lát cắt đủ nhỏ |
| **Giải pháp khác cho cùng nhu cầu** | “Thêm SMS” và “thêm email xác nhận” nhằm giúp người dùng biết kết quả | Làm rõ nhu cầu và điều kiện, so sánh giải pháp trước khi tạo hai cam kết |

Tìm trùng qua từ khóa, thành phần hệ thống, vai trò và hành vi là bước đầu. **Hai tiêu đề giống nhau chưa đủ để kết luận trùng**; hai tiêu đề khác nhau cũng chưa chứng minh khác mục tiêu.

### 6.2. Chọn mục đại diện (canonical item)

Một quy trình xử lý đơn giản:

1. Chọn mục thể hiện **vấn đề, người dùng và kết quả mong muốn** rõ nhất làm mục đại diện; không nhất thiết là mục có mã nhỏ nhất.
2. Liên kết các yêu cầu trùng với mục đại diện và ghi nguồn, thời điểm, số người phản hồi cùng những tình huống khác nhau.
3. Chuyển các tiêu chí chấp nhận hoặc điều kiện quan trọng chưa có sang mục đại diện.
4. Đánh dấu các mục trùng là **đã liên kết/đóng trùng**, ghi quyết định để người gửi vẫn tra cứu được.
5. Khi mục đại diện hoàn tất, kiểm tra xem các tình huống của nguồn trùng đã được đáp ứng thật chưa.
6. Nếu sau đó một nguồn bộc lộ nhu cầu riêng chưa được giải quyết, tạo mục bổ sung có liên kết thay vì mặc định nó đã hoàn tất.

Không nên ghép dữ liệu người dùng hoặc xóa các thẻ gốc mà không xem xét quyền truy cập và chính sách lưu trữ. **Gom công việc** không có nghĩa gom mọi dữ liệu riêng tư vào cùng một nơi.

### 6.3. Tránh ưu tiên bằng số phiếu thô

Một vấn đề được năm người gửi báo cáo có thể đáng chú ý hơn vấn đề một người gặp, nhưng:
- Năm phản hồi có thể đến từ cùng một nhóm nhỏ.
- Một lỗi ít người gặp nhưng có thể gây mất dữ liệu phải được ưu tiên theo rủi ro.
- Những người ít nói hoặc không biết kênh góp ý có thể đang gặp vấn đề tương tự.

Vì vậy số nguồn trùng là **một tín hiệu về nhu cầu**, không phải công thức quyết định thứ tự ưu tiên. Kết hợp tần suất với tác động, mức nghiêm trọng, cơ hội kinh doanh và bằng chứng từ người dùng.

### 6.4. Ví dụ gom yêu cầu về trạng thái đăng ký

Giả sử backlog có:
- **WS-101:** “Thêm email xác nhận sau khi đăng ký”.
- **WS-128:** “Học viên hỏi có chắc đã giữ chỗ không”.
- **WS-149:** “Trang gửi yêu cầu phải ghi rõ đang chờ duyệt”.
- **WS-152:** “Điều phối viên cần danh sách chờ để phê duyệt”.

WS-128 và WS-149 có thể cùng phản ánh vấn đề **học viên không hiểu trạng thái**. WS-101 là một **giải pháp được đề xuất** cho cùng vấn đề, cần kiểm chứng liệu email có thực sự giải quyết. WS-152 là nhu cầu **vận hành khác vai trò** và có thể cần giữ riêng. Nhóm nên hỏi người dùng và điều phối viên trước khi kết luận quan hệ giữa các mục.

## 7. Công việc ngoài luồng: đưa chi phí ẩn thành thông tin có thể ra quyết định

Công việc ngoài luồng có thể đi vào nhóm qua:
- Tin nhắn trực tiếp yêu cầu “sửa nhanh một chút”.
- Quản lý đề nghị bổ sung báo cáo trong lúc Sprint đang thực hiện.
- Lỗi production, cảnh báo bảo mật hoặc sự cố tích hợp.
- Hỗ trợ khách hàng, giải đáp nghiệp vụ hoặc giúp một nhóm khác gỡ chặn.
- Công việc kỹ thuật quan trọng mà nhóm tự làm nhưng không ghi vào luồng.
- Cuộc họp, kiểm tra thủ công hoặc thao tác vận hành phát sinh lặp lại.

Không phải mọi cuộc trao đổi ngắn đều cần một thẻ đầy đủ. Mục tiêu là **ghi nhận công việc có ảnh hưởng đáng kể đến năng lực, ưu tiên, chất lượng hoặc khả năng dự báo**. Nhóm có thể thống nhất ngưỡng thực hành, ví dụ công việc kéo dài trên 30 phút, ảnh hưởng Sprint Goal, chặn việc khác hoặc cần theo dõi qua nhiều người. Ngưỡng đó chỉ là chính sách vận hành được nhóm thử và điều chỉnh, không phải chuẩn chung.

### 7.1. Cơ chế xử lý một yêu cầu chen ngang

~~~mermaid
flowchart TD
    A[Có yêu cầu mới giữa vòng làm việc] --> B{Nguy cơ nghiêm trọng cần xử lý ngay?}
    B -->|Có| C[Kích hoạt ứng phó sự cố, ghi người điều phối]
    B -->|Không| D[Đưa vào điểm tiếp nhận và đánh giá]
    D --> E{Có đáng thay đổi ưu tiên hiện tại?}
    E -->|Không| F[Ghi vào backlog, phản hồi thời điểm xem lại]
    E -->|Có| G[Trao đổi người có thẩm quyền và nhóm thực hiện]
    G --> H[Thống nhất việc nào dừng, giảm hoặc lùi]
    C --> I[Hiển thị việc khẩn trên bảng và ảnh hưởng]
    H --> I
    I --> J[Thực hiện, kiểm tra, cập nhật kết quả]
    J --> K[Đánh giá gián đoạn và cải thiện chính sách]
~~~

Ba loại quyết định khác nhau cần được phân biệt:

**Thông thường:** đưa vào backlog, làm rõ người dùng và lợi ích, so sánh ưu tiên trong nhịp refinement kế tiếp.

**Gấp nhưng chưa phải sự cố:** ví dụ một chương trình ra mắt mới được xác nhận, cần thay đổi thứ tự ưu tiên. Người có thẩm quyền cùng nhóm điều chỉnh phạm vi, ghi rõ việc bị ảnh hưởng và thời điểm phản hồi.

**Sự cố khẩn cấp:** lỗi mất dữ liệu, hệ thống ngừng hoạt động ở chức năng trọng yếu hoặc rủi ro bảo mật đang ảnh hưởng người dùng. Kích hoạt quy trình xử lý sự cố thích hợp và ghi lại quyết định; không chờ họp backlog định kỳ nếu sẽ gây hại vì trì hoãn.

### 7.2. Quy định “khẩn” theo tác động, không theo người gửi

Một chính sách có thể dựa vào:
- **Mức độ tác động:** bao nhiêu người hoặc nghiệp vụ quan trọng bị ảnh hưởng?
- **Tính liên tục của sự cố:** đang xảy ra và gia tăng hay chỉ là khả năng tương lai?
- **Mốc thời gian không thể lùi:** có nghĩa vụ pháp lý, an toàn hoặc phụ thuộc thực tế nào?
- **Khả năng giảm thiểu:** có cách tạm thời phục hồi dịch vụ hoặc giới hạn ảnh hưởng?
- **Chi phí trì hoãn:** nếu xử lý muộn một ngày/tuần, hậu quả gì?

Tránh coi “lãnh đạo vừa nhắn” hoặc “khách hàng lớn yêu cầu” tự động tương đương sự cố mức cao nhất. Những yêu cầu đó có thể quan trọng, nhưng vẫn cần xem tác động và đánh đổi với việc đang làm.

### 7.3. Ảnh hưởng lên Scrum Sprint

Trong Scrum, **Sprint Goal** cung cấp định hướng chung. **Sprint Backlog** là kế hoạch do Developers chịu trách nhiệm và được cập nhật khi học thêm. Nếu phát sinh yêu cầu mới, Product Owner và Developers có thể trao đổi để thương lượng phạm vi mà **không làm mất Sprint Goal**. Không đơn phương giao thêm nhiều việc và đồng thời giữ nguyên kỳ vọng ban đầu.

Nếu Sprint Goal không còn phù hợp vì tình hình thay đổi căn bản, **Product Owner có thẩm quyền hủy Sprint** theo Scrum. Đây là quyết định khác với việc thường xuyên bỏ dở Sprint mỗi khi có yêu cầu mới; cần cân nhắc thực tế và tác động tới việc đang làm.

Trong thực hành, nhóm nên ghi:
- Yêu cầu phát sinh và lý do mức khẩn.
- Hạng mục nào bị hoãn, rút phạm vi hoặc đổi người thực hiện.
- Tác động đối với Sprint Goal và cách nhóm điều chỉnh.
- Kết quả xử lý, kiểm thử, phản hồi người dùng.
- Bài học để ước lượng năng lực và chính sách tiếp nhận tốt hơn.

### 7.4. Ảnh hưởng lên Kanban

Kanban hỗ trợ làm lộ công việc qua bảng và **WIP limits**. Nhóm có thể dành một **class of service** cho việc thực sự khẩn hoặc chính sách expedite có điều kiện, nhưng nếu mọi yêu cầu đều được gắn expedite, hàng đợi thường ngày sẽ bị bỏ đói.

Ví dụ chính sách thử:
- Có tối đa **một hạng mục expedite tại một thời điểm**, trừ khi cần huy động khẩn cấp theo quy trình sự cố.
- Mọi hạng mục expedite phải có lý do, người quyết định, giới hạn phạm vi và thời điểm xem lại.
- Nếu WIP đã đầy, nhóm ưu tiên hoàn tất, gỡ chặn hoặc chủ động dừng công việc ít cấp thiết trước khi kéo thêm.
- Sau mỗi sự cố hoặc mỗi chu kỳ, nhóm xem tác động của expedite lên cycle time, throughput, chất lượng và các yêu cầu bị chậm.

Giới hạn một hạng mục chỉ là **ví dụ khởi đầu**, không phải định mức Kanban bắt buộc. Nhóm cần điều chỉnh bằng quan sát dòng công việc thật.

## 8. Ưu tiên lại backlog theo giá trị và rủi ro

Một backlog được sắp thứ tự có nghĩa là nhóm phải **chọn**. Giữ tất cả hạng mục ở mức “cao” không phải ưu tiên.

### 8.1. Các yếu tố quan trọng

| Yếu tố | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Giá trị người dùng** | Ai được lợi, lợi ích lớn thế nào, có bằng chứng nào? | Học viên giảm nhầm lẫn về trạng thái |
| **Rủi ro hoặc mức nghiêm trọng** | Nếu không làm, có mất dữ liệu, mất quyền riêng tư, lỗi nghiệp vụ không? | Hệ thống xác nhận vượt số chỗ |
| **Chi phí trì hoãn** | Chờ thêm một khoảng thời gian sẽ mất gì? | Tính năng cần trước một đợt workshop đã công bố |
| **Độ chắc chắn** | Nhu cầu và giải pháp đã được xác minh đến đâu? | Nhiều nguồn phản hồi và quan sát dùng thử |
| **Công sức, phụ thuộc, năng lực** | Có thể giao giá trị nhỏ trước không, cần người/điều kiện nào? | Chia kiểm tra trạng thái khỏi báo cáo nâng cao |
| **Tác động lên mục tiêu hiện tại** | Có đóng góp vào Product Goal/Sprint Goal không? | Hoàn thiện luồng đăng ký cốt lõi trước tính năng phụ |

Nhóm có thể tham khảo **MoSCoW**, **RICE** hoặc **WSJF** khi cần hỗ trợ thảo luận. Đây là **công cụ hỗ trợ quyết định**, không phải cơ chế thay thế Product Owner, phản hồi người dùng hoặc đánh giá rủi ro.

**WSJF (Weighted Shortest Job First)** trong ngữ cảnh thích hợp so sánh ước lượng chi phí trì hoãn với quy mô công việc; các điểm số tương đối chỉ có ý nghĩa khi cách đánh giá được thống nhất. Nếu một lỗi đang gây sự cố nghiêm trọng, không nên dùng điểm số thiếu dữ liệu để trì hoãn ứng phó cần thiết.

### 8.2. Ví dụ so sánh có giải thích

Giả sử sản phẩm workshop có bốn hạng mục chưa thuộc nhóm khẩn cấp:

| Hạng mục | Tín hiệu giá trị | Rủi ro nếu chờ | Ước lượng phạm vi | Đề xuất |
| --- | --- | --- | --- | --- |
| Làm rõ thông báo đăng ký | Quan sát nhiều học viên hỏi lại trạng thái | Trải nghiệm kém, tăng hỏi hỗ trợ | Nhỏ | Ưu tiên kiểm chứng sớm |
| Tìm kiếm workshop theo ngày | Một số người phải cuộn danh sách dài | Khó tìm buổi phù hợp | Vừa | Xem sau lát cắt xác nhận |
| Báo cáo nâng cao cho ban tổ chức | Chưa có yêu cầu sử dụng rõ | Chi phí cơ hội chưa được chứng minh | Lớn | Xin thêm ví dụ nghiệp vụ, có thể trì hoãn |
| Thêm nhiều mẫu giao diện trang chủ | Chủ yếu là ý tưởng nội bộ | Thấp tại thời điểm hiện tại | Vừa | Chưa ưu tiên |

Nếu xuất hiện lỗi xác nhận vượt số chỗ, ưu tiên có thể đổi ngay do rủi ro nghiệp vụ. Đó là sự thích ứng có căn cứ, không phải dấu hiệu backlog “thiếu kỷ luật”.

### 8.3. Quy tắc trao đổi đánh đổi

Khi một việc mới cần được làm ngay, người ưu tiên nên trả lời: **“Điều gì được đưa lên, điều gì phải lùi xuống, vì sao, ai chịu ảnh hưởng và bằng chứng nào sẽ khiến chúng ta đổi quyết định?”**

Không có sự đánh đổi nào được công bố thì rất dễ xảy ra tình trạng **cộng thêm nhiệm vụ mà không trừ năng lực**. Việc này tạo áp lực, tăng WIP và làm chất lượng giảm ngay cả khi dashboard vẫn hiển thị kế hoạch ban đầu.

## 9. Tình huống xuyên suốt: làm sạch backlog đăng ký workshop

Một nhóm bốn người đang xây tính năng đăng ký workshop. Mục tiêu sản phẩm là giúp học viên chọn buổi còn chỗ, gửi yêu cầu và hiểu trạng thái mà không phải trao đổi thủ công.

### 9.1. Danh sách ban đầu

| Mã | Nội dung ban đầu | Nguồn/thời điểm giả định | Dấu hiệu cần kiểm tra |
| --- | --- | --- | --- |
| WS-011 | Gửi email ngay sau đăng ký | Ý tưởng nội bộ cách đây 5 tháng | Giải pháp cũ, chưa rõ người dùng cần gì |
| WS-034 | Học viên không biết đã được xác nhận chưa | Phỏng vấn 3 tuần trước | Vấn đề thật cần làm rõ |
| WS-041 | Hiển thị dòng “chờ xác nhận” dễ thấy | Học viên dùng thử tuần trước | Có thể cùng vấn đề với WS-034 |
| WS-052 | Báo cáo doanh thu theo từng giảng viên | Yêu cầu 7 tháng trước | Bối cảnh, người dùng và lợi ích cần xác minh lại |
| WS-063 | Xuất danh sách điểm danh | Điều phối viên yêu cầu 2 tuần trước | Nhu cầu vận hành riêng |
| WS-078 | Tự động thêm người vào danh sách chờ khi hết chỗ | Gợi ý sau khi chạy thử | Chưa biết quy tắc nghiệp vụ |
| WS-081 | Không cho hai người giữ cùng một suất cuối | Lỗi được tái hiện trong thử nghiệm | Rủi ro dữ liệu, cần ưu tiên |
| WS-093 | Đổi màu nút đăng ký | Tin nhắn riêng hôm qua | Giải pháp thiếu bằng chứng người dùng |

Đây là **dữ liệu minh họa để thực hành triage**, không phải backlog của một sản phẩm thật.

### 9.2. Phân loại và hành động đề xuất

**WS-034, WS-041 và WS-011:** ba mục có thể xoay quanh vấn đề **học viên không hiểu trạng thái sau khi gửi yêu cầu**. Chọn WS-034 làm mục đại diện mô tả nhu cầu, liên kết WS-041 là đề xuất thiết kế và WS-011 là phương án thông báo cần kiểm chứng. Không tự động triển khai cả email lẫn dòng thông báo nếu thử nghiệm cho thấy chỉ một cách đã đủ.

**WS-052:** đã tạo từ lâu, chưa có bằng chứng gần đây. Cần hỏi người phụ trách tài chính/ban tổ chức còn có tình huống sử dụng cụ thể hay không. Nếu đã có báo cáo ở hệ thống khác, đóng là không còn phù hợp. Nếu thực sự có nghĩa vụ đối soát, giữ lại và xác định rủi ro.

**WS-063:** là nhu cầu có thể độc lập của điều phối viên; không gộp vào story dành cho học viên chỉ vì cùng dùng dữ liệu workshop.

**WS-078:** cần làm rõ ai được vào danh sách chờ, thứ tự ưu tiên và khi một chỗ mở ra sẽ xử lý thế nào. Nếu chưa có cơ sở, ghi câu hỏi và tạm trì hoãn.

**WS-081:** cần kiểm tra sớm vì có thể dẫn đến xác nhận sai. Cần xác minh quy tắc sức chứa, kiểm thử khi nhiều yêu cầu gửi đồng thời và bảo vệ dữ liệu.

**WS-093:** chưa đủ cơ sở làm ngay. Hỏi người gửi vấn đề thực tế (không tìm thấy nút, nhầm trạng thái, khó dùng trên điện thoại?) rồi liên kết với hạng mục giải quyết vấn đề tương ứng nếu có.

### 9.3. Công việc ngoài luồng xuất hiện

Đang trong Sprint, nhóm nhận ba thông tin:

1. **Sự cố:** trong môi trường production, hệ thống có khả năng ghi hai đăng ký cho suất cuối cùng, đã xảy ra ở một buổi thật.
2. **Yêu cầu quản lý:** tạo báo cáo slide trước cuộc họp ngày mai, chưa rõ có thuộc phạm vi nhóm sản phẩm.
3. **Hỗ trợ đồng nghiệp:** một người cần giúp thiết lập môi trường thử trong khoảng một giờ.

Hành động hợp lý:
- Với sự cố đầu tiên, kích hoạt ứng phó theo mức nghiêm trọng, bảo vệ người dùng/dữ liệu, phối hợp với người phụ trách và ghi nhận work item cùng ảnh hưởng lên mục tiêu hiện tại. Khi khắc phục cần kiểm thử trường hợp đồng thời và kiểm chứng kết quả trên môi trường phù hợp.
- Với báo cáo, làm rõ người ra quyết định, mục đích, deadline thực và việc nào sẽ bị trì hoãn. Nếu không có cơ sở ưu tiên cao hơn, đưa vào backlog hoặc chuyển đúng nhóm phụ trách.
- Với hỗ trợ môi trường thử, người trong nhóm có thể giúp theo chính sách cộng tác; nếu ảnh hưởng đáng kể đến năng lực hoặc lặp lại nhiều lần, ghi nhận thời gian/nguyên nhân và cân nhắc cải thiện tài liệu hoặc tự động hóa.

Không có lý do để xếp ba việc vào cùng lớp “khẩn”. Mức độ cần phản ứng phụ thuộc hậu quả và quyền quyết định.

### 9.4. Quyết định sau buổi triage

Một bảng quyết định có thể là:

| Hạng mục | Kết quả triage | Lý do |
| --- | --- | --- |
| WS-081 | Ưu tiên xử lý theo sự cố và kiểm tra lại quy tắc | Dữ liệu thực tế có nguy cơ sai |
| WS-034 | Giữ là nhu cầu chính cần kiểm chứng | Nhiều phản hồi về trạng thái khó hiểu |
| WS-041 | Liên kết WS-034, giữ ví dụ dùng thử | Cùng nhu cầu, là một phương án trình bày |
| WS-011 | Liên kết WS-034 và tạm chưa chốt giải pháp email | Cần xác minh kênh nào giải quyết vấn đề |
| WS-052 | Chờ xác minh giá trị với người phụ trách | Thời điểm yêu cầu đã lâu; chưa rõ kết quả cần đạt |
| WS-063 | Giữ riêng và so sánh thứ tự với mục tiêu hiện tại | Khác vai trò/lợi ích |
| WS-078 | Cần làm rõ, có mốc xem lại | Quy tắc chưa được xác nhận |
| WS-093 | Làm rõ vấn đề hoặc đóng ý tưởng giải pháp | Chưa có bằng chứng cần đổi màu |

Nhóm lưu liên kết và nguồn phản hồi; không xóa dấu vết yêu cầu. Sau khi xử lý sự cố, nhóm trao đổi về các hạng mục đã bị đẩy lùi, kiểm tra tính khả thi của Sprint Goal và cập nhật kế hoạch phù hợp.

## 10. Đo sức khỏe backlog và tác động của việc chen ngang

Các chỉ số dưới đây **không phải KPI Agile bắt buộc**. Chúng giúp nhóm phát hiện nơi cần kiểm tra và đánh giá hiệu quả của chính sách quản lý yêu cầu.

| Chỉ số | Cách định nghĩa minh họa | Câu hỏi cần trả lời |
| --- | --- | --- |
| **Aged items** | Số mục chưa được xác nhận giá trị trong ngưỡng do nhóm chọn | Mục nào đang dùng thông tin cũ để lập kế hoạch? |
| **Tỷ lệ yêu cầu trùng đã xác minh** | Số yêu cầu mới được liên kết là trùng / tổng yêu cầu mới được phân loại trong kỳ | Kênh tiếp nhận có tạo nhiều lần nhập một vấn đề không? |
| **Thời gian đến quyết định triage** | Thời gian từ ghi nhận yêu cầu đến có quyết định ban đầu | Người gửi phải chờ bao lâu để biết yêu cầu được xem xét? |
| **Tỷ lệ công việc phát sinh** | Số hạng mục/giờ công phát sinh sau khi chốt kế hoạch, với mẫu số nhất quán | Việc không dự kiến đang chiếm năng lực đến đâu? |
| **Số gián đoạn ảnh hưởng mục tiêu** | Số lần phải dừng/thay phạm vi công việc đã chọn | Chính sách khẩn có quá dễ bị lạm dụng không? |
| **WIP và work item age** | Số việc đang xử lý và tuổi các việc chưa hoàn tất | Việc chen ngang có khiến nhiều việc bị bỏ dở? |
| **Cycle time và throughput** | Thời gian hoàn tất và số mục hoàn tất theo kỳ | Dòng công việc có trở nên dễ dự báo hơn? |
| **Chất lượng và giá trị** | Lỗi sau phát hành, phàn nàn, tỷ lệ hoàn tất tác vụ người dùng | Nhóm có thật sự giao kết quả có ích, an toàn? |

Đếm số thẻ “đã đóng” không đo trực tiếp hiệu quả làm sạch backlog. Nếu nhóm đóng thẻ chỉ để báo tỷ lệ đẹp, những nhu cầu có thật có thể bị bỏ qua và người dùng mất niềm tin.

### 10.1. Ví dụ tính chỉ số trong một tháng

Giả sử nhóm có **20 yêu cầu mới đã được phân loại** trong tháng; trong đó **5 mục được xác nhận trùng** với nhu cầu đã có. Nhóm xác định:
- **Tỷ lệ trùng:** 5 / 20 = **25%** trong tập yêu cầu đã phân loại.
- **12 mục lâu chưa xác nhận giá trị**, nhưng sau xem lại chỉ 3 mục thực sự không còn phù hợp; 5 mục được trì hoãn có điều kiện và 4 mục vẫn có giá trị cần làm rõ.
- Tổng **80 giờ công phát triển** được phân bổ và theo dõi trong một giai đoạn; **16 giờ** dùng cho việc chen ngang sau khi chốt kế hoạch, tức **16 / 80 = 20%** của thời gian được theo dõi.
- Ba sự cố khẩn gây gián đoạn có thời gian, mức độ và tác động khác nhau; cần xem riêng từng trường hợp, tránh lấy một con số trung bình che sự cố nghiêm trọng.

Đây là các **con số giả định**. Tỷ lệ trùng 25% không đủ để kết luận kênh tiếp nhận kém hiệu quả: một tính năng mới gây nhiều phản hồi giống nhau có thể là tín hiệu rất quan trọng. Tỷ lệ công việc chen ngang 20% cũng không nhất thiết xấu, đặc biệt với nhóm vận hành; điều cần hỏi là việc phát sinh có được phân loại, phản ánh đúng năng lực và xử lý theo giá trị hay không.

### 10.2. Không nhầm điều kiện đo

Muốn so sánh các giai đoạn:
- Thống nhất một **đơn vị đo**: số yêu cầu, số story hay thời gian; không cộng chúng lẫn nhau.
- Giữ định nghĩa **trùng**, **khẩn**, **bắt đầu**, **hoàn tất** ổn định qua kỳ.
- Phân biệt công việc sản phẩm và sự cố khi chúng có phân bố thời gian rất khác nhau.
- Đối chiếu với sản lượng, độ ổn định và giá trị giao thực tế, tránh chỉ tối ưu “giảm số thẻ”.

Nếu rút ngắn thời gian triage nhưng mọi yêu cầu chỉ được gắn trạng thái “đã đọc” mà không có quyết định, chỉ số sẽ đẹp hơn trong khi người gửi vẫn không biết phải chờ gì. Đo **chất lượng quyết định**, không chỉ tốc độ chuyển trạng thái.

## 11. Kết nối với Scrum, Kanban và XP

### 11.1. Scrum: Product Backlog là danh sách có thứ tự, được cập nhật

**Product Backlog** trong Scrum là danh sách được sắp thứ tự về những gì cần để cải thiện sản phẩm; nó phát triển theo điều nhóm học được. **Product Owner** chịu trách nhiệm quản lý hiệu quả backlog; nhóm có thể cộng tác refinement để chia nhỏ và làm rõ Product Backlog items.

Khi yêu cầu cũ không còn giá trị, Product Owner có thể điều chỉnh thứ tự hoặc loại khỏi backlog đang hoạt động. Khi yêu cầu trùng, nhóm thảo luận về một kết quả cần tạo, giữ nguồn phản hồi. Khi có việc mới giữa Sprint, các bên trao đổi tác động lên **Sprint Goal** và kế hoạch của Developers. **Sprint Review** là cơ hội kiểm tra Increment và điều chỉnh hướng phát triển; **Sprint Retrospective** là lúc kiểm tra chính sách làm việc, ví dụ vì sao công việc ngoài luồng lặp lại.

### 11.2. Kanban: hiển thị dòng việc và chính sách rõ ràng

Một bảng Kanban có thể dùng các cột như **Đầu vào → Cần làm rõ → Sẵn sàng → Đang làm → Kiểm tra → Hoàn tất**, kèm trạng thái quyết định **trì hoãn/trùng/đóng** phù hợp. Không cần bắt mọi mục đóng thành cột WIP; điều quan trọng là phân biệt **dòng nhận yêu cầu** với **dòng công việc đang thực hiện**.

Giới hạn WIP và kiểm tra các hạng mục đang già đi hỗ trợ nhóm hoàn thành việc đã bắt đầu. Khi có expedite, chính sách phải làm rõ điều kiện, số việc khẩn có thể đang xử lý và cách tránh các mục khác chờ vô hạn.

### 11.3. XP: giảm công việc phát sinh do lỗi lặp lại

Các thực hành XP như **test-driven development**, **pair programming**, **continuous integration** và **refactoring** giúp giảm lỗi tái diễn, hỗ trợ thay đổi an toàn. Nếu cứ mỗi Sprint có một lỗi đặt chỗ trùng khiến nhóm phải sửa ngoài luồng, cần hỏi vì sao kiểm thử và thiết kế chưa bảo vệ được bất biến nghiệp vụ.

Đưa bài học từ sự cố thành kiểm thử, thay đổi mã và quy trình có thể giảm số việc chen ngang trong tương lai. Nhưng kiểm thử tốt không thay thế việc xác minh nhu cầu người dùng hay ưu tiên sản phẩm.

## 12. Quy ước cộng tác và lãnh đạo để duy trì minh bạch

Chính sách backlog thất bại nếu người trong nhóm sợ nói “không đủ năng lực”, người gửi yêu cầu không có phản hồi, hoặc người có chức danh cao luôn có thể bỏ qua quy trình.

### 12.1. Thống nhất quyền quyết định, cách giao tiếp và mốc phản hồi

Một thỏa thuận nhóm có thể gồm:
- Ai chịu trách nhiệm **đánh giá giá trị và thứ tự** của yêu cầu sản phẩm?
- Ai điều phối **sự cố cần phản ứng ngay**?
- Ai cập nhật kế hoạch công việc sau khi có thay đổi ưu tiên?
- Người gửi cần cung cấp những thông tin tối thiểu nào?
- Trong bao lâu nhóm sẽ **phản hồi quyết định tiếp nhận sơ bộ**? Đây không phải lời hứa hoàn thành tính năng.
- Làm sao người gửi bổ sung bằng chứng, thách thức quyết định hoặc yêu cầu mở lại?

Mốc phản hồi cần phù hợp năng lực. Ví dụ “xem xét yêu cầu thông thường trong buổi triage mỗi tuần” là cam kết về **quy trình xem xét**, không có nghĩa mọi yêu cầu sẽ được xây trong tuần đó.

### 12.2. Một số cách nói minh bạch

Khi phát hiện trùng:

> “Chúng tôi đã ghi nhận tình huống này trong WS-034. Tôi sẽ liên kết phản hồi của bạn và bổ sung trường hợp học viên không thấy trạng thái trên điện thoại để nhóm kiểm tra cùng, tránh làm hai thay đổi không nhất quán.”

Khi không thể làm ngay:

> “Vấn đề này có giá trị nhưng hiện xếp sau việc bảo vệ dữ liệu đăng ký khỏi bị trùng. Chúng tôi lưu yêu cầu cùng điều kiện xem lại; nếu ảnh hưởng tăng hoặc có bằng chứng mới, thứ tự có thể thay đổi.”

Khi nhận việc chen ngang:

> “Việc này có thể cần ưu tiên. Để xử lý trong Sprint hiện tại, nhóm cần thống nhất story nào sẽ lùi hoặc giảm phạm vi, vì tổng năng lực không tăng. Tôi sẽ cùng người phụ trách backlog và Developers xác nhận tác động.”

Khi gặp sự cố:

> “Chúng tôi đang xử lý lỗi ảnh hưởng đăng ký thật theo quy trình sự cố và ghi lại các việc bị gián đoạn. Sau khi hệ thống ổn định, nhóm sẽ xác minh kết quả, cập nhật kế hoạch và xem cách ngăn lỗi lặp lại.”

Những câu trao đổi như vậy giúp bảo vệ sự minh bạch, tránh tạo kỳ vọng mơ hồ và biến bất đồng ưu tiên thành thảo luận có căn cứ.

## 13. Bài thực hành: buổi triage backlog 45–60 phút

### 13.1. Bối cảnh và dữ liệu

Nhóm có Sprint Goal: **“Học viên thử nghiệm có thể tự đăng ký một buổi còn chỗ và hiểu kết quả.”**

Đầu Sprint, backlog đã chọn gồm: hiển thị buổi còn chỗ, gửi yêu cầu, thông báo trạng thái và kiểm thử trường hợp hết chỗ.

Giữa tuần, xuất hiện các thông tin **giả định**:

1. Học viên A báo “đăng ký rồi nhưng không rõ đã có chỗ”; thẻ WS-034 đã mô tả vấn đề tương tự.
2. Học viên B muốn email xác nhận; thẻ WS-011 từ lâu đề xuất điều này.
3. Một người quản lý yêu cầu tính năng xuất biểu đồ doanh thu để họp sáng mai.
4. Nhóm hỗ trợ báo lỗi production: hai học viên có thể cùng được xác nhận một suất cuối.
5. Một bug nhỏ ở màn hình quản trị vừa được báo và không ảnh hưởng luồng đăng ký.
6. WS-052, yêu cầu báo cáo đã có từ bảy tháng trước, vẫn chưa ai xác minh lại.
7. Một kỹ sư dành hai giờ giúp sửa cấu hình môi trường kiểm thử do hướng dẫn bị lỗi thời.

### 13.2. Nhiệm vụ A – Phân loại (10 phút)

Với mỗi thông tin, xác định:
- Mới, trùng, liên quan, cũ cần xác minh hay công việc ngoài luồng?
- Có phải sự cố cần phản ứng ngay không? Căn cứ tác động nào?
- Thông tin nào còn thiếu trước khi ra quyết định?

### 13.3. Nhiệm vụ B – Ra quyết định (15 phút)

Lập bảng có các cột: **mã/nguồn – vấn đề và người dùng – mức tác động – quyết định – mục liên kết – người phụ trách – mốc xem lại**.

Cần chỉ rõ:
- Mục nào cần xử lý khẩn và kiểm tra chất lượng.
- Mục nào nên liên kết với WS-034 thay vì lập trình hai giải pháp cùng lúc.
- Mục nào được giữ/hoãn/đóng sau xác minh, không tự động xóa vì cũ.
- Việc nào phải ghi nhận là gián đoạn hoặc nhu cầu cải tiến môi trường.

### 13.4. Nhiệm vụ C – Điều chỉnh kế hoạch (10 phút)

Nhóm đã lên lịch triển khai ba story nhỏ trong phần còn lại của Sprint. Sự cố xử lý trùng dự kiến cần phần lớn thời gian còn lại của một Developers.

Hãy thảo luận:
1. Hạng mục nào sẽ tạm dừng hoặc giảm phạm vi?
2. Sprint Goal còn có thể giữ được không? Vì sao?
3. Product Owner và Developers cần thương lượng thay đổi nào?
4. Bằng chứng nào cho thấy sự cố đã được khắc phục an toàn?
5. Khi nào nhóm sẽ kiểm tra lại tác động và thông báo cho bên liên quan?

Đừng đáp “cả nhóm làm thêm giờ để giữ nguyên mọi việc” như một giải pháp mặc định. Kế hoạch thích ứng cần dựa trên năng lực và mức rủi ro có thật.

### 13.5. Nhiệm vụ D – Đo lường (10 phút)

Giả sử trong tháng vừa qua:
- Nhóm nhận và phân loại 24 yêu cầu.
- Sáu yêu cầu được xác minh là trùng với mục đã có.
- Tám mục chưa được xem lại hơn 60 ngày; sau xác minh có ba mục vẫn cần giữ, hai mục trì hoãn có điều kiện, ba mục không còn phù hợp.
- Tại thời điểm xem xét, nhóm có năm hạng mục đang làm, trong đó hai hạng mục bị chặn vì chờ làm rõ nghiệp vụ.
- Hai lần xử lý sự cố làm dời lịch kiểm thử một tính năng.

Câu hỏi:
1. Tỷ lệ trùng của tập yêu cầu đã phân loại là bao nhiêu?
2. Có được kết luận cả tám mục cũ đều vô ích không?
3. Những tín hiệu nào cho thấy cần giảm WIP hoặc làm rõ yêu cầu trước khi bắt đầu?
4. Nếu tháng sau tỷ lệ trùng giảm nhưng số lỗi nghiêm trọng tăng, nhóm nên giải thích thế nào?
5. Chọn hai chỉ số vận hành và một tín hiệu giá trị người dùng để kiểm tra tác dụng của chính sách mới.

**Gợi ý tự kiểm tra:** tỷ lệ trùng trong tập phân loại là **6 / 24 = 25%**. Trong tám mục cũ, chỉ ba mục được xác nhận không còn phù hợp; việc đánh dấu cả tám là “không cần làm” sẽ làm mất nhu cầu có giá trị. Hai hạng mục đang bị chặn cần được kiểm tra nguyên nhân, thay vì chỉ kéo thêm việc mới. Nếu lỗi nghiêm trọng tăng, hãy đánh giá chất lượng và mức rủi ro; giảm số yêu cầu trùng không chứng minh cải tiến toàn diện.

### 13.6. Thang đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Phân loại** | Coi tất cả yêu cầu cũ là vô ích, mọi yêu cầu mới là khẩn | Phân biệt cũ, trùng, liên quan và ngoài luồng | Có căn cứ và biết điểm cần xác minh thêm |
| **Bảo toàn bối cảnh** | Xóa trùng không giữ phản hồi | Liên kết nguồn với mục đại diện | Giữ tình huống riêng, quyền và tiêu chí quan trọng |
| **Ưu tiên** | Làm theo người gửi lớn tiếng nhất | Dùng giá trị, rủi ro và chi phí trì hoãn | Nêu rõ đánh đổi, điều kiện đổi quyết định |
| **Cộng tác** | Âm thầm cộng thêm việc vào Sprint | Trao đổi tác động và cập nhật kế hoạch | Giữ minh bạch mục tiêu, phản hồi kịp thời |
| **Kiểm chứng** | Chỉ đếm số thẻ đã đóng | Đo tình trạng backlog, WIP và lỗi | Kết hợp chất lượng, giá trị và xem lại chính sách |

## 14. Mẫu có thể dùng ngay

### 14.1. Mẫu tiếp nhận yêu cầu

~~~text
MÃ/LIÊN KẾT:
Ngày tiếp nhận:
Nguồn phản hồi:
Vai trò/người dùng chịu ảnh hưởng:
Vấn đề quan sát được:
Kết quả mong muốn:
Tình huống minh họa / bằng chứng:
Mức tác động và thời hạn thực (nếu có):
Có sự cố đang xảy ra không? Dấu hiệu:
Mục tương tự hoặc phụ thuộc:
Điều cần làm rõ:
Người phụ trách triage:
Ngày phản hồi quyết định:
~~~

### 14.2. Mẫu quyết định cho mục cũ hoặc trùng

~~~text
Mục:
Ngày xem lại:
Bằng chứng giá trị gần nhất:
Đối tượng còn gặp vấn đề:
Có mục cùng kết quả? Mã:
Chi tiết cần bảo toàn:
Quyết định: giữ / ưu tiên lại / chia / trì hoãn / liên kết / đóng
Lý do và tác động:
Ai ra quyết định:
Điều kiện mở lại / ngày xem lại:
Cách phản hồi cho người gửi:
~~~

### 14.3. Mẫu ghi nhận việc ngoài luồng

~~~text
Ngày và nguồn:
Mô tả việc phát sinh:
Khẩn cấp? Theo tiêu chí nào:
Người điều phối / người thực hiện:
Thời điểm bắt đầu và kết thúc:
Công việc hiện tại bị dừng hoặc thay đổi:
Tác động Sprint Goal / WIP / người dùng:
Kiểm tra chất lượng hoặc xác minh xử lý:
Điều học được:
Cách tránh lặp lại hoặc giảm chi phí lần sau:
~~~

Các mẫu này chỉ cần đủ thông tin để ra quyết định; không nên biến chúng thành thủ tục mất nhiều công hơn bản thân một công việc nhỏ.

## 15. Checklist duy trì backlog khỏe mạnh

- [ ] Có thể tra cứu và liên kết yêu cầu từ các kênh tiếp nhận về một nơi ra quyết định ưu tiên.
- [ ] Mỗi yêu cầu quan trọng nêu rõ người dùng/vấn đề, kết quả mong muốn và nguồn phản hồi.
- [ ] Thứ tự ưu tiên thể hiện lựa chọn thực tế, không phải mọi mục đều gắn “High”.
- [ ] Những mục lâu chưa xác nhận giá trị có chính sách xem lại theo bối cảnh.
- [ ] Không tự động xóa yêu cầu chỉ vì lâu ngày chưa làm.
- [ ] Các yêu cầu trùng được liên kết với một mục đại diện và vẫn giữ tình huống/nguồn phản hồi.
- [ ] Các yêu cầu chỉ giống chủ đề nhưng khác vai trò, quyền hoặc tiêu chí không bị gom bừa.
- [ ] Công việc ngoài luồng có ảnh hưởng đáng kể được ghi nhận và đưa vào điều phối.
- [ ] Có chính sách phân biệt yêu cầu thông thường, yêu cầu gấp và sự cố khẩn cấp.
- [ ] Khi thêm việc gấp, nhóm nói rõ hạng mục nào phải dời, giảm phạm vi hoặc dừng.
- [ ] Sprint Goal hoặc chính sách Kanban được kiểm tra lại khi có thay đổi ưu tiên.
- [ ] Có người chịu trách nhiệm quyết định, phản hồi cho bên yêu cầu và điều kiện xem lại.
- [ ] Chỉ số backlog được giải thích cùng WIP, thời gian chờ, chất lượng và giá trị người dùng.
- [ ] Retrospective hoặc nhịp cải tiến định kỳ xem nguyên nhân việc ngoài luồng lặp lại.
- [ ] Mọi thay đổi chính sách được thử trong phạm vi hợp lý và kiểm tra kết quả thực tế.

**Kiểm soát yêu cầu cũ, trùng lặp và công việc ngoài luồng** là quá trình giữ backlog **đáng tin, có thể ra quyết định và thích ứng được**. Khi nhóm biết yêu cầu nào còn giá trị, nhu cầu nào thực chất là một, việc phát sinh nào thực sự khẩn và điều gì phải thay đổi trong kế hoạch, họ có thể tập trung năng lực vào phần mềm có ích, giao sản phẩm tăng dần và học từ phản hồi thay vì bị cuốn theo một danh sách công việc ngày càng dài.
