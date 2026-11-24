# Xử lý thay đổi, công việc chưa hoàn tất và điều kiện hủy Sprint

Một Sprint vừa bắt đầu được vài ngày thì người dùng báo lỗi nghiêm trọng, đối tác đổi hợp đồng API và một bên liên quan đề nghị thêm tính năng mới. Đến cuối Sprint, nhóm vẫn còn hai Product Backlog Item chưa hoàn tất. Những tình huống này không hiếm trong phát triển phần mềm; nếu cố giữ kế hoạch ban đầu bằng mọi giá, nhóm sẽ bỏ qua thông tin mới. Nhưng nếu cứ có thay đổi là thay Sprint Goal, bỏ kiểm thử hoặc hủy Sprint, nhóm cũng không thể tạo ra nhịp làm việc ổn định.

**Scrum tạo ra một khung thời gian cố định để tập trung vào mục tiêu và học hỏi, chứ không biến mọi hạng mục được dự kiến thành hợp đồng bất biến.** Trong Sprint, nhóm có thể làm rõ và thương lượng phạm vi khi biết thêm thông tin, nhưng không được thực hiện thay đổi làm nguy hại Sprint Goal và không được hạ chất lượng. Khi Sprint kết thúc, phần chưa đáp ứng Definition of Done phải được thể hiện đúng trạng thái, không được tính thành Increment hoàn chỉnh. Trong một trường hợp đặc biệt, **Product Owner có quyền hủy Sprint nếu Sprint Goal trở nên lỗi thời**.

Bài học thuộc chương **Sự kiện Scrum** trong module **AGILE_DEVELOPMENT**. Nội dung kết nối tinh thần Agile về thích ứng theo phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục với Product Backlog, user story, trách nhiệm Scrum, cách quản lý dòng công việc kiểu Kanban và thực hành chất lượng từ XP. Mục tiêu là biết xử lý thay đổi một cách minh bạch và có trách nhiệm, không chỉ thuộc lòng quy tắc.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Sprint Goal**, **phạm vi Sprint** và **kế hoạch thực hiện**.
2. Giải thích những thay đổi có thể xảy ra trong Sprint và giới hạn bắt buộc phải giữ.
3. Xử lý yêu cầu mới, công việc khẩn và những thông tin bất ngờ mà không tự ý phá Sprint Goal.
4. Quyết định cách xử lý Product Backlog Item chưa đạt Definition of Done khi Sprint kết thúc.
5. Nhận diện đúng điều kiện **Sprint Goal trở nên lỗi thời** và thẩm quyền hủy Sprint.
6. Mô tả trách nhiệm của Product Owner, Developers và Scrum Master trong các tình huống trên.
7. Truyền đạt tác động, dự báo và rủi ro với stakeholder dựa trên bằng chứng.
8. Áp dụng các nguyên tắc qua một tình huống phát triển chức năng đăng ký workshop.

## 2. Nền tảng: Sprint là nhịp tập trung, kiểm tra và thích ứng

Theo [Scrum Guide 2020](https://scrumguides.org/scrum-guide.html), **Sprint** là sự kiện bao trùm các sự kiện Scrum khác, có độ dài **không quá một tháng**. Sprint mới bắt đầu ngay sau Sprint trước kết thúc. Sprint tạo khoảng thời gian đủ ngắn để giới hạn rủi ro, kiểm tra tiến độ tới Product Goal và điều chỉnh hướng đi thường xuyên.

Ba thành phần cần phân biệt ngay từ đầu:

| Thành phần | Câu hỏi trả lời | Ví dụ về đăng ký workshop | Mức độ có thể thay đổi |
| --- | --- | --- | --- |
| **Sprint Goal** | Vì sao Sprint này có giá trị? Điều gì cả nhóm đang hướng tới? | Học viên đăng ký được workshop còn chỗ và biết chính xác kết quả | Là mục tiêu tập trung của Sprint; không thay tùy tiện chỉ để phù hợp với danh sách việc mới |
| **Product Backlog Item được chọn** | Những hạng mục nào được lựa chọn để thực hiện nhằm tiến tới mục tiêu? | Danh sách workshop, đăng ký chỗ, trạng thái xác nhận, thông báo | Có thể được làm rõ và thương lượng phạm vi với Product Owner khi nhóm học thêm |
| **Kế hoạch trong Sprint Backlog** | Developers sẽ làm việc đó thế nào và điều chỉnh ra sao? | Thứ tự tích hợp, thiết kế lưu trữ, kiểm thử cạnh tranh, chia việc giữa thành viên | Developers liên tục điều chỉnh dựa trên tiến độ và điều mới biết |

**Sprint Backlog** gồm Sprint Goal, các Product Backlog Item được chọn cho Sprint và kế hoạch thực hiện của Developers. Developers có trách nhiệm tạo, cập nhật và tự quản Sprint Backlog trong Sprint. **Product Backlog** tiếp tục phát triển và được sắp thứ tự bởi trách nhiệm của Product Owner.

### 2.1. Những quy tắc giữ Sprint có ý nghĩa

Trong Sprint:

- **Không thực hiện thay đổi làm nguy hại Sprint Goal.**
- **Chất lượng không được suy giảm.**
- **Product Backlog có thể được refinement khi cần.**
- **Phạm vi công việc có thể được làm rõ và thương lượng lại với Product Owner khi nhóm học được điều mới.**

Các quy tắc này cùng tồn tại. Scrum không nói rằng **không được thay một dòng kế hoạch nào**; cũng không nói rằng **cứ thay đổi là có quyền hạ tiêu chuẩn chất lượng**.

### 2.2. Sprint Goal không phải phép cộng tất cả hạng mục

Giả sử Sprint Goal là:

> **Học viên đủ điều kiện đăng ký được workshop còn chỗ và nhận trạng thái đáng tin cậy.**

Nhóm đã chọn các việc hiển thị workshop, đăng ký chỗ, cập nhật trạng thái và gửi email xác nhận. Sau vài ngày, nhóm nhận ra tích hợp email phức tạp hơn dự tính. Nếu hệ thống vẫn có thể đáp ứng Sprint Goal bằng **trạng thái trong ứng dụng** và việc gửi email chưa phải điều kiện bắt buộc của mục tiêu, nhóm có thể trao đổi để chuyển phần email sang sau, miễn không vi phạm những cam kết đã thống nhất.

Ngược lại, **không thể bỏ kiểm tra chống đăng ký vượt sức chứa** rồi tuyên bố đạt Sprint Goal, bởi trạng thái không còn đáng tin cậy. Nhóm cần phân biệt:

- **Phương án và phạm vi bổ sung:** Có thể thay khi vẫn đạt mục tiêu và chất lượng.
- **Điều kiện cốt lõi để mục tiêu có ý nghĩa:** Không thể bỏ chỉ để làm đẹp số lượng hoàn tất.

## 3. Điều gì được xem là thay đổi trong Sprint?

Không phải mọi thay đổi đều cùng bản chất hoặc cần cùng cách xử lý.

| Loại thay đổi | Ví dụ | Cách phản ứng phù hợp |
| --- | --- | --- |
| **Làm rõ yêu cầu** | Học viên chỉ được hủy khi chưa qua thời hạn khóa danh sách | Làm rõ tiêu chí chấp nhận; Developers cập nhật kế hoạch và trao đổi với Product Owner |
| **Phát hiện công việc kỹ thuật cần thiết** | Cần kiểm tra cạnh tranh khi chỉ còn một chỗ | Bổ sung vào cách triển khai để đáp ứng chất lượng; xem lại phạm vi và năng lực |
| **Đổi giải pháp** | Thay thiết kế xử lý đồng bộ bằng hàng đợi sau thử nghiệm | Developers lựa chọn trong ranh giới kiến trúc, tham vấn bên liên quan nếu có ảnh hưởng |
| **Đề xuất tính năng mới** | Bộ phận kinh doanh muốn thêm mã giảm giá | Product Owner đánh giá giá trị, sắp thứ tự trong Product Backlog; không tự chen vào Sprint |
| **Lỗi nghiêm trọng hoặc sự cố** | Một học viên xem được đăng ký của người khác | Theo quy trình xử lý sự cố; báo ngay rủi ro và tác động tới Sprint Goal |
| **Phụ thuộc bị thay đổi** | Dịch vụ thông báo bên ngoài đổi API | Xác minh tác động, chọn phương án phù hợp và thương lượng phạm vi khi cần |
| **Mục tiêu sản phẩm bị vô hiệu hóa** | Tổ chức ngừng hoàn toàn dịch vụ workshop mà Sprint đang phục vụ | Product Owner xem xét liệu Sprint Goal đã lỗi thời và có cần hủy Sprint |

Một yêu cầu mới **không tự động trở thành việc của Sprint đang diễn ra**. Nó cũng không tự động bị từ chối: Product Owner cùng nhóm phân tích mức cấp bách và tác động, rồi quyết định cách xử lý theo trách nhiệm tương ứng.

### 3.1. Phân biệt “mới” với “cấp bách”

Stakeholder có thể gửi một yêu cầu hôm nay và gọi đó là “khẩn” vì họ vừa nghĩ ra nó. Nhưng cấp bách thực sự cần căn cứ: người dùng đang bị ảnh hưởng nghiêm trọng, nghĩa vụ sắp có hiệu lực, chi phí trì hoãn lớn, hoặc một cơ hội có hạn.

Khi được đề nghị thêm việc, nên hỏi:

1. **Ai bị ảnh hưởng và mức độ ra sao?**
2. **Điều gì xảy ra nếu xử lý sau Sprint hiện tại?**
3. **Yêu cầu gắn với Product Goal và Sprint Goal nào?**
4. **Có lựa chọn nhỏ hoặc tạm thời an toàn hơn không?**
5. **Nếu nhận việc này, công việc nào sẽ bị dời hoặc rủi ro nào tăng?**
6. **Ai có thẩm quyền quyết định việc ưu tiên và những ràng buộc liên quan?**

Những câu hỏi này tránh cả hai cực đoan: từ chối mọi yêu cầu mới theo khẩu hiệu “Sprint đã đóng”, hoặc nhận mọi việc không xét ảnh hưởng.

## 4. Quy trình xử lý thay đổi khi Sprint Goal vẫn còn giá trị

Nếu mục tiêu Sprint vẫn hữu ích và có thể tiếp tục theo đuổi, nhóm nên **thích ứng phạm vi hoặc cách làm trước khi nghĩ tới hủy Sprint**.

### Bước 1. Ghi nhận và hiểu thông tin mới

Phân biệt sự kiện đã quan sát với giả định. Ví dụ:

- **Sự kiện:** Hai yêu cầu đặt chỗ đồng thời có thể tạo ra hai trạng thái xác nhận cho một chỗ.
- **Giả định:** Lỗi chỉ xảy ra khi tải cao.
- **Điều cần kiểm tra:** Lỗi xuất hiện với điều kiện nào, có ảnh hưởng dữ liệu thật không và bản sửa có yêu cầu thay đổi kiến trúc hay không?

Đối với rủi ro bảo mật, mất dữ liệu hoặc sự cố thật, **không chờ tới Daily Scrum kế tiếp mới thông báo**; sử dụng kênh phản ứng sự cố phù hợp.

### Bước 2. Đối chiếu với Sprint Goal và Definition of Done

Hãy hỏi:

> **Thông tin mới thay đổi cách đạt Sprint Goal, hay làm chính Sprint Goal không còn đáng theo đuổi?**

Nếu chỉ thay đổi cách thực hiện, nhóm có thể xem lại thiết kế và thứ tự công việc. Nếu thông tin mới cho thấy một điều kiện chất lượng thiết yếu chưa đạt, cần xử lý để đạt DoD. Nếu Sprint Goal không còn có giá trị trong bối cảnh sản phẩm hiện tại, đưa vấn đề cho Product Owner xem xét **hủy Sprint**.

### Bước 3. Đánh giá tác động tới năng lực và phụ thuộc

Developers đánh giá:

- Công việc đang làm và chưa bắt đầu.
- Những yêu cầu bổ sung để đạt DoD.
- Năng lực còn lại trong Sprint, bao gồm hỗ trợ và sự cố.
- Phụ thuộc với người hoặc dịch vụ bên ngoài.
- Khả năng chia thành lát cắt nhỏ hơn mà vẫn tạo giá trị.
- Rủi ro khi không đổi kế hoạch.

Không dùng một ước lượng mới để cam kết chắc chắn; cần nêu điều chưa biết và mức tự tin.

### Bước 4. Thương lượng phạm vi phù hợp với trách nhiệm

Developers và Product Owner có thể trao đổi phương án:

- Làm rõ hoặc thu hẹp phạm vi một PBI mà vẫn đáp ứng Sprint Goal.
- Dời hạng mục bổ sung chưa cần thiết.
- Tách một ý tưởng lớn thành phần có thể kiểm chứng trong Sprint.
- Bổ sung công việc kỹ thuật bắt buộc để đáp ứng chất lượng.
- Nếu thật sự cần một hạng mục khẩn, nêu rõ việc nào bị ảnh hưởng và có thể dời.

**Developers quản lý kế hoạch trong Sprint Backlog; Product Owner chịu trách nhiệm thứ tự Product Backlog và phối hợp về giá trị/phạm vi.** Scrum Master hỗ trợ minh bạch, hiểu Scrum và giải quyết trở ngại, không đơn phương viết lại Sprint Goal hoặc giao task.

### Bước 5. Cập nhật trạng thái và truyền đạt quyết định

Thay đổi cần được thấy trong Sprint Backlog và những thông tin có liên quan, không chỉ nói miệng với một người. Nếu dự báo phát hành hoặc phạm vi cam kết với stakeholder thay đổi, Product Owner và nhóm phải truyền đạt sớm với lý do và lựa chọn.

### Bước 6. Kiểm tra tiếp và điều chỉnh

Daily Scrum giúp Developers kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch. Những trao đổi chi tiết bổ sung có thể diễn ra khi cần, không nhất thiết gói trong sự kiện 15 phút. Mục tiêu là **sớm phát hiện rủi ro và đưa hạng mục tới trạng thái thực sự Done**.

~~~mermaid
flowchart TD
    A["Thông tin hoặc yêu cầu mới trong Sprint"] --> B{"Có sự cố cần phản ứng ngay?"}
    B -->|"Có"| C["Bảo vệ người dùng, xử lý theo quy trình sự cố; thông báo tác động"]
    B -->|"Không"| D["Làm rõ nhu cầu, rủi ro và bằng chứng"]
    C --> D
    D --> E{"Sprint Goal còn phù hợp và có giá trị?"}
    E -->|"Có"| F["Developers đánh giá tác động; trao đổi phạm vi với Product Owner"]
    F --> G["Điều chỉnh Sprint Backlog trong quyền hạn; giữ DoD và Sprint Goal"]
    G --> H["Thực hiện, kiểm chứng, cập nhật dự báo"]
    E -->|"Không"| I["Product Owner đánh giá khả năng hủy Sprint"]
    I --> J{"Product Owner quyết định hủy?"}
    J -->|"Không"| F
    J -->|"Có"| K["Kết thúc Sprint bị hủy, minh bạch trạng thái, lập kế hoạch tiếp"]
~~~

Sơ đồ là công cụ suy nghĩ, **không phải thủ tục chính thức bổ sung vào Scrum Guide**. Đối với sự cố thật, các biện pháp bảo vệ dữ liệu và người dùng không bị trì hoãn chỉ vì đang có một Sprint.

## 5. Thay đổi phạm vi không đồng nghĩa thay Sprint Goal

Đây là phân biệt quan trọng nhất khi xử lý thay đổi.

### 5.1. Sprint Goal là định hướng chung

Sprint Goal giúp Scrum Team linh hoạt trong cách làm nhưng vẫn **tập trung vào cùng một kết quả**. Nếu nhóm chỉ có danh sách 12 task rời rạc mà không có mục tiêu, việc một task gặp khó sẽ khiến cả Sprint bị xem là thất bại; nhóm khó biết phần nào cần bảo vệ.

Ví dụ:

> **Sprint Goal:** Học viên tự đăng ký một workshop còn chỗ và nhận trạng thái đúng.

Có thể thay **cách hiển thị kết quả**, **phương án lưu giao dịch** hoặc **thứ tự triển khai** nếu vẫn đạt mục tiêu và chất lượng. Nhưng thay toàn bộ mục tiêu thành “xây dashboard quản trị” chỉ vì có người quản lý mới yêu cầu không phải một điều chỉnh kế hoạch nhỏ.

### 5.2. Ba tình huống đối chiếu

| Tình huống | Sprint Goal còn giá trị? | Cách xử lý |
| --- | --- | --- |
| Email xác nhận mất nhiều thời gian nhưng trạng thái đăng ký trong ứng dụng đáp ứng nhu cầu cốt lõi đã thống nhất | **Có thể còn** | Thương lượng dời email nếu nó không phải điều kiện bắt buộc để đạt mục tiêu |
| Kiểm thử phát hiện lỗi xác nhận vượt số chỗ | **Vẫn còn**; cách thực hiện chưa đạt | Sửa lỗi và kiểm chứng; cân nhắc dời phần tùy chọn, không bỏ chất lượng |
| Tổ chức chính thức hủy toàn bộ dịch vụ workshop do thay đổi chiến lược, chức năng đăng ký không còn được sử dụng | **Có thể đã lỗi thời** | Product Owner xem xét hủy Sprint, đưa ra quyết định và truyền đạt |

**Không tự kết luận từ một tình huống tách rời.** Một email xác nhận có thể là bắt buộc về pháp lý hoặc nghiệp vụ; khi ấy không thể đơn giản bỏ qua. Phạm vi tối thiểu luôn phụ thuộc Product Goal, Sprint Goal và các ràng buộc đã được xác nhận.

### 5.3. Không dùng Sprint Goal như lý do che giấu thông tin xấu

Nếu Sprint Goal vẫn còn giá trị nhưng nhóm phát hiện quá ít năng lực để hoàn tất trong timebox, họ phải **minh bạch dự báo và rủi ro**, điều chỉnh phạm vi khi có thể và cố gắng tạo Increment đúng chất lượng. Sprint không được kéo dài tùy ý; cũng không nên tự tuyên bố đã đạt mục tiêu khi điều kiện thiết yếu chưa hoàn thành.

Không đạt mục tiêu theo dự kiến **không tự động làm mục tiêu lỗi thời**. Đây là khác biệt giữa **mục tiêu còn giá trị nhưng thực hiện khó khăn** và **mục tiêu không còn đáng theo đuổi**.

## 6. Xử lý công việc khẩn ngoài kế hoạch

Sự cố sản xuất, lỗ hổng bảo mật hoặc mất dữ liệu có thể đòi hỏi phản ứng ngay, bất kể nhóm đang trong Sprint. Scrum không phải lý do để bỏ mặc người dùng hoặc vi phạm quy trình phản ứng sự cố.

### 6.1. Quy trình ưu tiên bảo vệ sản phẩm

Giả sử API đăng ký workshop vô tình cho phép người dùng xem đăng ký của người khác:

1. **Đánh giá và ngăn tác động ngay** theo quy trình sự cố: xác minh, hạn chế truy cập hoặc áp dụng biện pháp an toàn trong quyền hạn.
2. **Thông báo tới người chịu trách nhiệm** bảo mật, vận hành, sản phẩm và các bên cần biết.
3. **Làm rõ khối lượng công việc và năng lực bị ảnh hưởng**: ai tham gia xử lý, những PBI Sprint nào có nguy cơ chậm?
4. **Developers điều chỉnh kế hoạch**, phối hợp Product Owner về thứ tự, phạm vi và dự báo.
5. **Kiểm chứng bản sửa và trạng thái dữ liệu**, không bỏ qua DoD hoặc điều kiện phát hành.
6. **Rút kinh nghiệm về nguyên nhân hệ thống** trong kênh đánh giá sự cố và cải tiến phù hợp.

Đây là cách xử lý công việc khẩn **cùng với Scrum**, không phải “mọi sự cố phải đợi Product Owner thêm PBI mới vào ngày Sprint sau”.

### 6.2. Công việc khẩn không luôn dẫn tới hủy Sprint

Một lỗi nghiêm trọng có thể làm giảm năng lực còn lại và khiến Sprint Goal khó đạt, nhưng **tiêu chí hủy Sprint trong Scrum không phải là “có lỗi nghiêm trọng”**. Câu hỏi vẫn là Sprint Goal **có trở nên lỗi thời hay không**. Nếu mục tiêu còn giá trị, Scrum Team có thể ứng phó sự cố, cập nhật Sprint Backlog và minh bạch khả năng hoàn tất.

### 6.3. Tăng khả năng xử lý thay đổi bằng Kanban và XP

Nhóm có thể kết hợp:

- **Chính sách xử lý công việc khẩn:** Khi nào được ngắt luồng bình thường, ai xác nhận và hệ quả đối với công việc đang làm.
- **Giới hạn WIP:** Tránh mở thêm nhiều việc trong khi lỗi quan trọng còn chưa xử lý.
- **Work item age và cycle time:** Phát hiện hạng mục đang bị chờ quá lâu.
- **Kiểm thử tự động và tích hợp liên tục từ XP:** Sửa lỗi, thay đổi phương án và kiểm chứng nhanh hơn mà không hạ chất lượng.

Những thực hành bổ trợ này không làm thay đổi vai trò và quy tắc cốt lõi của Scrum; chúng giúp nhóm **thực hiện Scrum hiệu quả trong bối cảnh thực tế**.

## 7. Công việc chưa hoàn tất: thế nào là Done?

Trong Scrum, một Product Backlog Item chỉ góp phần vào **Increment** khi đáp ứng **Definition of Done (DoD)**. Đây là cam kết của Increment, mô tả trạng thái chất lượng phải đạt.

**Đã code xong, đã merge, đã demo trên máy cá nhân hoặc đã hoàn thành 90% không tự động đồng nghĩa Done.** Tất cả còn phụ thuộc tiêu chuẩn chất lượng đã được thống nhất và áp dụng.

### 7.1. Phân biệt các trạng thái thực tế

| Tình trạng khi Sprint kết thúc | Có được tính là Increment hoàn chỉnh? | Cách xử lý |
| --- | --- | --- |
| Hành vi đã hoàn tất, tích hợp và kiểm thử đáp ứng DoD | **Có** | Là phần của Increment; có thể được phát hành khi điều kiện liên quan phù hợp |
| Đã viết mã nhưng chưa kiểm thử tích hợp bắt buộc | **Không** | Minh bạch trạng thái, tiếp tục công việc nếu còn giá trị |
| Đạt chức năng nhưng phát hiện lỗi bảo mật khiến không đạt DoD | **Không** | Không đánh dấu Done; ưu tiên khắc phục theo rủi ro |
| Một phần story có thể dùng nhưng toàn bộ PBI chưa đạt DoD | **Không đối với PBI ban đầu** | Xem có lát cắt độc lập nào thực sự đạt DoD; không tự hợp thức hóa phần chưa kiểm chứng |
| Cần thêm phản hồi về giá trị người dùng sau phát hành, nhưng Increment đã đạt DoD | **Có**, nếu mọi điều kiện DoD được thỏa mãn | Ghi kế hoạch đo lường và cập nhật backlog khi có dữ liệu |
| Một PBI được dừng vì không còn giá trị trước khi hoàn tất | **Không** đối với phần chưa Done | Minh bạch việc dừng, xem xét bỏ hoặc thay đổi hạng mục trong Product Backlog |

**Sprint Review không phải nơi biến việc chưa đạt DoD thành Done.** Theo Scrum Guide, công việc không đạt Definition of Done không thể được xem là một phần của Increment hoặc được trình bày ở Sprint Review như Increment hoàn chỉnh. Nhóm có thể minh bạch các vấn đề, công việc còn lại và rủi ro trong cuộc trao đổi, nhưng không được tạo ấn tượng phần chưa hoàn tất là sản phẩm đã đạt chất lượng.

### 7.2. Vì sao quy tắc Done đặc biệt quan trọng?

Nếu nhóm tính “code complete” là Done trong ba Sprint và tới Sprint thứ tư mới bắt đầu kiểm thử, tốc độ báo cáo có thể rất cao nhưng sản phẩm vẫn không thể sử dụng an toàn. Công việc dở dang trở thành một **hàng đợi ẩn**, khiến dự báo mất căn cứ và việc giao giá trị bị trì hoãn.

Ngược lại, nếu nhóm chỉ tính Done khi đạt một tiêu chuẩn rõ, số lượng có thể thấp hơn nhưng phản ánh **năng lực tạo Increment thực**. Trong Agile, phần mềm hoạt động được và phản hồi thực tế quan trọng hơn một báo cáo phần trăm hoàn thành thiếu kiểm chứng.

## 8. Điều gì xảy ra với PBI chưa Done khi Sprint kết thúc?

Sprint có timebox cố định. **Không kéo dài Sprint thêm hai ngày chỉ để hoàn thành những việc dự kiến**, vì như vậy sẽ làm mất nhịp kiểm tra và thích ứng của Scrum.

Theo Scrum Guide, công việc chưa đáp ứng DoD **quay lại Product Backlog để được xem xét trong tương lai**, thay vì trở thành Increment. Cách thực hiện cụ thể trên công cụ có thể khác nhau, nhưng nguyên tắc phải giữ:

1. **Nêu rõ trạng thái:** Phần nào đạt DoD, phần nào chưa và còn vấn đề gì.
2. **Phân biệt công việc dở dang với Increment:** Không cộng phần chưa Done vào kết quả hoàn tất của Sprint.
3. **Đưa phần chưa hoàn thành về Product Backlog để xem xét:** Product Owner có trách nhiệm quản lý thứ tự, Developers đóng góp thông tin còn lại và độ khả thi.
4. **Refinement khi cần:** Có thể giữ, chia nhỏ, đổi mô tả, đánh giá lại hoặc bỏ hạng mục nếu không còn giá trị.
5. **Lập kế hoạch Sprint tiếp theo dựa trên ưu tiên và năng lực hiện tại:** Không mặc định tất cả việc chưa xong **phải** được chuyển thẳng sang Sprint kế tiếp.
6. **Học từ nguyên nhân:** Tìm xem PBI quá lớn, phụ thuộc, hiểu sai yêu cầu, chất lượng chưa đủ hay WIP quá cao.

### 8.1. Ví dụ: story “hủy đăng ký workshop” chưa hoàn tất

Đến cuối Sprint, Developers đã triển khai API hủy nhưng chưa qua kiểm thử trường hợp hai yêu cầu hủy đồng thời; phần trạng thái chỗ ngồi còn nguy cơ sai.

**Cách làm sai:** Đánh dấu Done vì “đã hoàn thành 90%”, trình bày luồng hủy là tính năng sẵn sàng ở Sprint Review, rồi mở một bug nhỏ cho 10% còn lại.

**Cách làm phù hợp:** Ghi rõ PBI chưa đạt DoD. Chỉ những Increment khác đã đạt DoD mới được coi là hoàn chỉnh. Product Owner cùng Developers xem xét công việc còn lại, độ ưu tiên và khả năng chia thành phần hoàn chỉnh trong Sprint kế tiếp. Trong Sprint Review, nhóm minh bạch điều đã đạt và giới hạn chưa đạt, không trình bày tính năng hủy chưa hoàn chỉnh như kết quả đã Done.

### 8.2. Có thể chia phần hoàn tất thành một PBI nhỏ hơn không?

Có thể **tái cấu trúc backlog một cách trung thực** khi thực sự tồn tại một lát cắt độc lập, có ích và đã đáp ứng DoD. Ví dụ, PBI lớn “xem và hủy đăng ký” ban đầu gồm hai hành vi độc lập; nếu chức năng **xem đăng ký của chính mình** đã được tích hợp, kiểm thử và đạt DoD, nhóm có thể cùng Product Owner làm rõ cách ghi nhận phần giá trị hoàn chỉnh đó, còn phần hủy trở về Product Backlog để xem xét.

Nhưng **không được chia giả sau sự kiện** để hợp thức hóa một phần chưa an toàn hoặc tính công việc dở dang thành Increment. Việc tái cấu trúc cần minh bạch trạng thái, hành vi thật và tiêu chuẩn chất lượng.

### 8.3. Có được phát hành phần Increment đã Done không?

Scrum không yêu cầu phải chờ Sprint Review mới được phát hành Increment. Nếu một Increment đáp ứng DoD và các điều kiện phát hành phù hợp, nó có thể được giao sớm hơn. Tương tự, nếu một PBI chưa Done thì việc một số hạng mục khác đã Done **không bị vô hiệu hóa**.

Tuy nhiên, **đạt DoD không tự thay thế tất cả nghĩa vụ phát hành** của tổ chức, ví dụ yêu cầu phê duyệt pháp lý hoặc kiểm tra vận hành phù hợp rủi ro. Phải phân biệt sự hoàn chỉnh của Increment với quyết định phát hành cho đối tượng cụ thể.

## 9. Khi nào được hủy Sprint?

Scrum Guide 2020 đưa ra điều kiện trọng tâm:

> **Một Sprint có thể bị hủy nếu Sprint Goal trở nên lỗi thời. Chỉ Product Owner có thẩm quyền hủy Sprint.**

Đây là trường hợp khác biệt căn bản với việc Sprint “đang khó”, “không đạt đủ điểm”, “có thêm yêu cầu”, hoặc “bị chậm tiến độ”.

### 9.1. “Sprint Goal lỗi thời” nghĩa là gì?

**Lỗi thời** (*obsolete*) có nghĩa mục tiêu đã **không còn phù hợp hoặc không còn đáng theo đuổi trong bối cảnh sản phẩm hiện tại**, ngay cả khi Developers có thể hoàn thành công việc kỹ thuật.

Ví dụ:

- Tổ chức chính thức ngừng sản phẩm hoặc dòng dịch vụ mà Sprint Goal đang phục vụ.
- Chính sách hoặc quyết định có hiệu lực làm mục tiêu Sprint mất ý nghĩa; không còn được phép thực hiện mục đích dự kiến.
- Thông tin thị trường/người dùng đáng tin cậy khiến Product Owner xác định mục tiêu Sprint hoàn toàn không còn tạo giá trị và cần chuyển hướng.
- Một phụ thuộc chiến lược bị chấm dứt khiến kết quả Sprint không còn được sử dụng, chứ không chỉ khó triển khai hơn.

**Không phải mọi thay đổi chiến lược hoặc phản hồi tiêu cực đều buộc phải hủy Sprint.** Product Owner phải đánh giá có thể đạt một mục tiêu vẫn có giá trị trong timebox hiện tại thông qua điều chỉnh phạm vi hoặc cách làm hay không.

### 9.2. Những lý do không tự động đủ để hủy Sprint

| Tình huống | Vì sao không tự động đồng nghĩa lỗi thời? | Phản ứng nên xem xét trước |
| --- | --- | --- |
| Một PBI lớn hơn dự kiến | Mục tiêu người dùng có thể vẫn đúng | Chia nhỏ, thương lượng phạm vi, xử lý rủi ro |
| Sprint chỉ còn hai ngày và chưa đạt nhiều PBI | Trễ tiến độ khác với mục tiêu mất giá trị | Minh bạch dự báo, ưu tiên Increment đạt DoD, kết thúc đúng timebox |
| Stakeholder đề nghị một tính năng mới | Yêu cầu mới không nhất thiết làm mục tiêu hiện tại vô ích | Product Owner đánh giá thứ tự backlog và thời điểm |
| Nhà cung cấp API chậm | Kết quả cần đạt có thể vẫn hữu ích | Xem phương án thay thế, phối hợp phụ thuộc, điều chỉnh phạm vi |
| Một sự cố sản xuất phải xử lý ngay | Công việc khẩn có thể làm giảm năng lực nhưng không nhất thiết làm mục tiêu lỗi thời | Phản ứng sự cố, cập nhật kế hoạch, đánh giá lại khả thi |
| Developers bất đồng về giải pháp | Bất đồng là vấn đề quyết định kỹ thuật, không phải mất mục tiêu | Thu thập bằng chứng, thử phương án nhỏ, coaching cộng tác |
| Velocity thấp hơn Sprint trước | Chỉ số không chứng minh mục tiêu mất ý nghĩa | Xem bối cảnh, công việc và rào cản; không chạy theo điểm |

**Mục tiêu khó đạt** và **mục tiêu không còn giá trị** là hai câu hỏi khác nhau. Trong thực tế, Sprint có thể kết thúc mà không đạt Sprint Goal; đó là thông tin quan trọng cho việc học hỏi, không phải lý do tự động hủy Sprint vào phút cuối.

### 9.3. Ai có quyền quyết định?

**Chỉ Product Owner** có thẩm quyền hủy Sprint. Các bên liên quan, Developers, Scrum Master và quản lý có thể nêu bằng chứng, thảo luận tác động và đề nghị xem xét, nhưng không được **đơn phương tuyên bố hủy** theo định nghĩa Scrum.

Scrum Master hỗ trợ hiểu đúng điều kiện và tạo cuộc trao đổi minh bạch; Developers làm rõ trạng thái công việc, rủi ro và những Increment đã đạt DoD. Nếu có ràng buộc tổ chức như chi phí, pháp lý, truyền thông hoặc vận hành, Product Owner cần phối hợp với người có thẩm quyền phù hợp để xử lý tác động thực tế.

### 9.4. Hủy Sprint không phải công cụ quản trị hằng ngày

Hủy Sprint khiến nhịp tập trung bị gián đoạn, công việc dở dang cần được xem lại, các kế hoạch phối hợp thay đổi và người liên quan phải cập nhật kỳ vọng. Vì vậy, Scrum Guide mô tả đây là tình huống khi **Sprint Goal không còn phù hợp**, không phải cách “reset” Sprint mỗi khi tiến độ khó khăn.

Nếu một tổ chức thường xuyên hủy Sprint vì yêu cầu ưu tiên đổi liên tục, cần xem lại Product Goal, cách quản lý Product Backlog, quyền quyết định và sự ổn định của nhịp phản hồi, thay vì coi số Sprint bị hủy là thước đo thích ứng.

## 10. Xử lý minh bạch khi Product Owner quyết định hủy Sprint

Scrum Guide **không quy định một buổi “cancellation ceremony” bắt buộc**. Vì vậy, các bước dưới đây là **gợi ý thực hành nhằm quản lý hệ quả**, không phải các sự kiện Scrum chính thức mới.

### Bước 1. Công bố quyết định và lý do mục tiêu đã lỗi thời

Product Owner giải thích:

- Sprint Goal nào không còn đáng theo đuổi?
- Thông tin hoặc quyết định nào làm mục tiêu mất giá trị?
- Điều gì sẽ thay đổi về định hướng sản phẩm?
- Những stakeholder và phụ thuộc nào cần được thông báo?

Phải phân biệt lý do **lỗi thời của mục tiêu** với một nguyên nhân khác như “hết giờ”, “quản lý bực mình” hoặc “cần thêm việc”.

### Bước 2. Kiểm tra những gì thực sự đã hoàn tất

Developers xem phần nào đạt DoD và có thể trở thành Increment sử dụng được; phần nào còn dở, có vấn đề chất lượng hoặc rủi ro vận hành. Không xóa dấu vết công việc chỉ vì Sprint đã hủy.

Nếu một Increment đã Done và còn giá trị trong định hướng mới, nhóm và Product Owner xem cách sử dụng hoặc phát hành phù hợp. Việc hủy Sprint **không khiến một Increment đã đạt DoD tự động trở nên chưa Done**.

### Bước 3. Xem lại mọi công việc chưa hoàn thành

Những PBI chưa Done không được tính thành Increment; chúng cần được xem xét lại trong Product Backlog. Product Owner quyết định thứ tự dựa trên mục tiêu mới. Có thể giữ, sửa, gộp, chia hoặc loại bỏ; không tự động chuyển nguyên xi sang Sprint kế tiếp.

### Bước 4. Xử lý phụ thuộc, dữ liệu và vận hành

Nếu nhóm đang thực hiện di trú dữ liệu, thay đổi cấu hình hoặc tích hợp bên ngoài, cần:

- Đảm bảo trạng thái hệ thống an toàn và nhất quán.
- Xác định những thay đổi đã triển khai hoặc đang có hiệu lực.
- Quyết định dừng, khôi phục hoặc tiếp tục phần kỹ thuật tối thiểu để bảo vệ dữ liệu.
- Thông báo cho nhóm phụ thuộc và người chịu trách nhiệm vận hành.
- Lưu lại các quyết định và giới hạn chưa xử lý.

**Hủy Sprint không được dùng làm lý do bỏ mặc một hệ thống đang ở trạng thái nguy hiểm**. Nếu có sự cố thật, quy trình xử lý sự cố vẫn phải được thực hiện.

### Bước 5. Cập nhật Product Backlog và bắt đầu nhịp kế hoạch phù hợp

Product Owner làm rõ Product Goal hoặc định hướng mới; Scrum Team dùng Sprint Planning để lập kế hoạch Sprint tiếp theo với Sprint Goal có ý nghĩa. Sprint bị hủy kết thúc sớm, **không kéo dài hoặc biến thành một Sprint không có mục tiêu**.

### Bước 6. Học hỏi từ quyết định

Nhóm có thể trao đổi ngắn về tín hiệu cảnh báo sớm, chất lượng dữ liệu cho ưu tiên sản phẩm và cách truyền đạt thay đổi. Đây là hoạt động cải tiến có ích, nhưng **không cần phát minh một nghi thức chính thức** rồi bắt mọi tình huống hủy Sprint phải theo thủ tục nặng nề.

## 11. Bảng quyết định: điều chỉnh, để kết thúc, hay hủy Sprint?

| Câu hỏi | Điều kiện | Hành động hợp lý |
| --- | --- | --- |
| Sprint Goal còn hữu ích không? | **Có** | Tiếp tục Sprint; kiểm tra phương án thích ứng |
| Công việc có thay đổi nhưng vẫn giữ Sprint Goal và DoD không? | **Có** | Developers điều chỉnh kế hoạch, thương lượng phạm vi với Product Owner |
| Có sự cố gây hại ngay không? | **Có** | Phản ứng sự cố, bảo vệ người dùng; minh bạch tác động tới Sprint |
| Một số PBI có nguy cơ không Done trước timebox? | **Có**, mục tiêu vẫn có giá trị | Tập trung hoàn tất hạng mục quan trọng, không hạ DoD; cập nhật dự báo |
| Sprint đã tới ngày kết thúc mà còn PBI chưa Done? | **Có** | Kết thúc đúng timebox; công việc chưa Done quay về Product Backlog để xem xét |
| Sprint Goal đã không còn đáng theo đuổi? | **Có bằng chứng** | Product Owner đánh giá quyết định hủy; các vai trò khác cung cấp thông tin |
| Product Owner quyết định hủy? | **Có** | Kết thúc sớm, kiểm kê Increment đã Done và công việc dở, cập nhật backlog và lập kế hoạch tiếp |

### Một ví dụ đối chiếu đặc biệt

Nhóm đang phát triển hệ thống đăng ký workshop. Có hai tin mới:

1. **Dịch vụ email hỏng trong ba ngày.** Mục tiêu đăng ký đúng chỗ vẫn hữu ích; có thể dùng thông báo trong ứng dụng, xem phương án gửi email sau và giữ DoD phù hợp. Đây trước hết là vấn đề **thích ứng phạm vi và phụ thuộc**.
2. **Tổ chức chính thức dừng toàn bộ hoạt động workshop, không còn kế hoạch mở lại.** Mục tiêu giúp học viên đăng ký workshop không còn người dùng hoặc giá trị dự kiến. Đây là tình huống **có thể đáp ứng điều kiện hủy Sprint**, và Product Owner là người có thẩm quyền quyết định.

Hai vấn đề đều là “thay đổi lớn”, nhưng chỉ tình huống thứ hai thể hiện rõ **mục tiêu có thể đã lỗi thời**.

## 12. Vai trò Product Owner, Developers và Scrum Master trong thay đổi

Ba nhóm trách nhiệm của Scrum cùng xử lý tình huống nhưng không thay nhau nắm quyền.

| Tình huống | Product Owner | Developers | Scrum Master |
| --- | --- | --- | --- |
| Yêu cầu mới | Đánh giá giá trị, sắp thứ tự Product Backlog, trao đổi ràng buộc và kỳ vọng | Đánh giá khả thi, tác động kỹ thuật, năng lực | Giúp hội thoại minh bạch và hiểu đúng cách vận dụng Scrum |
| Cần đổi phạm vi trong Sprint | Trao đổi và thương lượng phạm vi nhằm giữ Sprint Goal | Tự quản Sprint Backlog, điều chỉnh cách thực hiện | Coaching tự quản, giúp gỡ trở ngại |
| Phát hiện lỗi/việc cần thiết để đạt DoD | Làm rõ giá trị và ưu tiên theo tác động; hỗ trợ quyết định phạm vi | Kiểm chứng, sửa lỗi và không đánh dấu Done khi chưa đạt chuẩn | Bảo vệ sự minh bạch, hỗ trợ loại bỏ trở ngại |
| PBI chưa Done cuối Sprint | Sắp thứ tự lại Product Backlog cho tương lai | Báo trạng thái, rủi ro, phần còn lại, khả năng chia nhỏ | Hỗ trợ đánh giá nguyên nhân và cải tiến |
| Sprint Goal có nguy cơ lỗi thời | Đánh giá mục tiêu sản phẩm và bằng chứng | Cung cấp thông tin Increment, năng lực, chi phí kỹ thuật | Giúp mọi người hiểu điều kiện hủy, hỗ trợ thảo luận |
| Quyết định hủy Sprint | **Người duy nhất có thẩm quyền hủy** | Minh bạch phần đã Done và chưa Done; bảo vệ trạng thái an toàn | Hỗ trợ truyền đạt, cải tiến và cách vận dụng đúng |
| Lập kế hoạch Sprint tiếp theo | Làm rõ mục tiêu và Product Backlog có thứ tự | Chọn công việc, tạo Sprint Backlog và kế hoạch | Giúp Sprint Planning hiệu quả, đúng timebox |

### 12.1. Tránh biến Scrum Master thành người điều hành mọi thay đổi

Scrum Master có trách nhiệm về việc hiểu và vận dụng Scrum hiệu quả, nhưng **không quyết định thay Product Owner về giá trị và hủy Sprint**, cũng **không ra lệnh Developers thay đổi giải pháp kỹ thuật hoặc phân chia task**.

Scrum Master có thể hỏi:

- “Yêu cầu này thực sự làm Sprint Goal lỗi thời, hay chỉ làm cách thực hiện khó hơn?”
- “Những phần nào đã đạt DoD, phần nào vẫn là công việc dở?”
- “Ai có quyền chốt quyết định này và cần những bằng chứng gì?”
- “Nếu vẫn theo Sprint Goal, chúng ta có thể thương lượng phạm vi nào?”
- “Cải tiến nào giúp hạn chế vấn đề lặp lại ở Sprint tiếp theo?”

Đó là **hỗ trợ năng lực ra quyết định**, không phải biến mọi thay đổi thành việc Scrum Master cấp phép.

## 13. Tình huống xuyên suốt: Sprint xây chức năng đăng ký workshop

Một Scrum Team có Sprint hai tuần. Product Goal là giúp học viên **tự tìm, đăng ký và quản lý workshop đáng tin cậy**, giảm công việc thủ công của bộ phận hỗ trợ.

**Sprint Goal:** Học viên đủ điều kiện đăng ký được một workshop còn chỗ và nhận trạng thái chính xác.

Các Product Backlog Item được chọn lúc Sprint Planning:

| PBI | Giá trị mong muốn | Điều kiện quan trọng |
| --- | --- | --- |
| A. Hiển thị workshop còn chỗ | Học viên biết lựa chọn phù hợp | Dữ liệu chỗ trống chính xác với phạm vi đã hỗ trợ |
| B. Đăng ký và xác nhận chỗ | Học viên tự đăng ký được | Không xác nhận vượt sức chứa, kiểm tra quyền |
| C. Xem trạng thái đăng ký của chính mình | Học viên biết kết quả | Không xem được đăng ký của người khác |
| D. Gửi email xác nhận | Giảm việc phải tự kiểm tra lại | Không gửi sai trạng thái; phụ thuộc dịch vụ email |

### Ngày 3: một giả định về giao diện bị bác bỏ

Người dùng thử bản đầu và cho biết họ không cần lịch tháng; chỉ cần danh sách giờ còn chỗ rõ ràng trên điện thoại.

**Cách xử lý:** Product Owner cân nhắc giá trị; Developers điều chỉnh giao diện theo lát cắt đơn giản. Sprint Goal vẫn còn giá trị. Không cần hủy Sprint vì một giả định thiết kế thay đổi.

### Ngày 5: phát hiện lỗi tranh chỗ cuối

Kiểm thử cho thấy hai yêu cầu đồng thời có thể xác nhận cùng một chỗ. PBI B **chưa đạt điều kiện chất lượng cốt lõi**.

**Cách xử lý:** Developers ưu tiên giải quyết tính nhất quán, kiểm chứng qua các kịch bản đồng thời. Nhóm thương lượng dời phần D nếu điều đó không làm mất Sprint Goal và vẫn tuân thủ nghĩa vụ nghiệp vụ. Không đánh dấu PBI B Done khi vấn đề còn tồn tại.

### Ngày 7: đối tác email thông báo đổi API

Việc tích hợp email có thể mất thêm thời gian; Product Owner và Developers xem xét phương án trạng thái trong ứng dụng và bổ sung email sau, nếu đã đáp ứng các yêu cầu thực sự của mục tiêu.

**Cách xử lý:** Điều chỉnh kế hoạch, ghi ảnh hưởng tới PBI D và dự báo. **Thay đổi phạm vi** là biện pháp phù hợp hơn hủy Sprint khi mục tiêu đăng ký đáng tin vẫn có giá trị.

### Ngày 9: một stakeholder muốn thay thành dashboard quản trị

Yêu cầu mới là xây bảng thống kê marketing trước cuộc họp tuần sau. Đây có thể là tính năng có ích nhưng chưa chứng minh rằng Sprint Goal hiện tại đã lỗi thời.

**Cách xử lý:** Product Owner đánh giá giá trị và thứ tự Product Backlog; Developers nêu tác động; Scrum Master tạo điều kiện đối thoại. Không tự thay Sprint Goal bằng việc dashboard chỉ vì người yêu cầu có chức vụ cao.

### Ngày 10: Sprint kết thúc, PBI D vẫn chưa đạt DoD

Giả sử A, B, C đã hoàn chỉnh theo DoD; D chưa kiểm thử trường hợp dịch vụ email thất bại.

**Cách xử lý:**

- A, B, C đủ điều kiện là một phần của Increment.
- D **không được tính Done hoặc trình bày như Increment hoàn chỉnh**.
- D được xem xét lại trong Product Backlog với thứ tự phù hợp; không tự động ép vào Sprint sau.
- Sprint kết thúc đúng timebox. Nhóm kiểm tra kết quả trong Sprint Review và cải tiến trong Retrospective.

### Tình huống thay thế: Product Owner nhận tin dịch vụ workshop bị chấm dứt

Nếu vào ngày 6 tổ chức chính thức quyết định **ngừng toàn bộ sản phẩm workshop**, không còn người dùng mục tiêu hoặc kế hoạch sử dụng chức năng đăng ký, Product Owner có cơ sở xem xét Sprint Goal đã lỗi thời.

Lúc này, Product Owner có thể **hủy Sprint**. Developers xác định phần nào đã Done và bảo vệ trạng thái hệ thống; Product Owner cập nhật Product Backlog theo định hướng mới, còn Scrum Master hỗ trợ mọi người hiểu quyết định và giữ minh bạch. Đây là trường hợp **khác về bản chất** với việc API email chậm.

## 14. Sprint kết thúc: Sprint Review và Sprint Retrospective giúp học gì?

Một Sprint không chỉ được đánh giá bằng “có hoàn tất tất cả PBI hay không”. Scrum còn cần xem **Increment đạt được, giá trị tạo ra, lý do sai lệch và hành động tiếp theo**.

### 14.1. Sprint Review: kiểm tra kết quả và thích ứng Product Backlog

Trong Sprint Review, Scrum Team và stakeholder trao đổi về kết quả Sprint và tiến độ tới Product Goal. Những câu hỏi hữu ích:

- Increment nào đã đạt DoD và có thể sử dụng?
- Kết quả thực tế giúp người dùng làm gì mới hoặc tốt hơn?
- Điều gì trong bối cảnh đã thay đổi?
- Những PBI nào chưa hoàn tất, đang có rủi ro hoặc không còn giá trị?
- Product Backlog và ưu tiên có cần cập nhật không?

**Sprint Review không phải cổng bắt buộc để được phát hành**, và cũng không phải cuộc họp để “nghiệm thu hộ” phần chưa đạt DoD. Nhóm có thể nêu rõ công việc chưa hoàn tất để cùng hiểu tình hình, nhưng không được giới thiệu nó là Increment hoàn chỉnh.

### 14.2. Sprint Retrospective: cải thiện hiệu quả và chất lượng

Nếu PBI dở dang thường xuyên qua nhiều Sprint, hãy xem dữ liệu và nguyên nhân:

| Dấu hiệu | Câu hỏi nên đặt | Thử cải tiến nhỏ |
| --- | --- | --- |
| PBI quá lớn | Có lát cắt người dùng nhỏ hơn mà vẫn đủ chất lượng? | Chia nhỏ trước Sprint Planning hoặc trong refinement |
| Review/kiểm thử bị dồn cuối Sprint | Vì sao kiểm chứng không diễn ra cùng với triển khai? | Tích hợp sớm, kiểm thử theo lát cắt |
| WIP cao, nhiều việc cùng dang dở | Nhóm có mở thêm việc thay vì hoàn tất việc cũ? | Giới hạn WIP và cùng hỗ trợ hạng mục gần Done |
| Yêu cầu mới chen ngang không có quyết định rõ | Có chính sách ưu tiên việc khẩn và vai trò PO chưa? | Thống nhất cách phân loại thay đổi, truyền đạt tác động |
| Phụ thuộc liên nhóm gây chờ đợi | Ai sở hữu phụ thuộc, cần tín hiệu và thời hạn phản hồi gì? | Kết nối sớm, chính sách tích hợp và dự báo phụ thuộc |
| Đánh dấu Done sớm | DoD chưa rõ hoặc đang bị ép số lượng? | Làm rõ tiêu chuẩn, kiểm tra dữ liệu chất lượng và giảm áp lực sai |

Một Retrospective tốt chọn ít nhất một cải tiến có thể thực hiện và kiểm chứng, thay vì chỉ ghi “lần sau cố gắng hơn”.

### 14.3. Không biến phần chưa Done thành “nợ chuyển Sprint”

Chuyển hạng mục chưa Done sang Sprint sau một cách tự động khiến backlog mất thứ tự thực và dễ tạo cam kết giả. Product Owner cần xem lại **giá trị, rủi ro và thời điểm**; Developers xem **phần còn lại, khả năng chia nhỏ và năng lực**. Đôi khi hạng mục tiếp tục được ưu tiên cao; đôi khi một lựa chọn mới đáng làm hơn.

## 15. Quản lý dự báo và truyền thông khi kế hoạch thay đổi

Khi có thay đổi, stakeholder thường quan tâm “Bao giờ xong?” và “Phần nào bị ảnh hưởng?”. Câu trả lời tốt nên có **kết quả, điều đã biết, tác động, lựa chọn và thời điểm cập nhật**, không chỉ một ngày dự báo thiếu điều kiện.

### 15.1. Mẫu thông điệp thay đổi phạm vi

~~~text
SPRINT GOAL:
THÔNG TIN MỚI / BẰNG CHỨNG:
PHẠM VI HOẶC RỦI RO BỊ ẢNH HƯỞNG:
NHỮNG PHẦN ĐÃ ĐẠT DEFINITION OF DONE:
NHỮNG PHẦN CÒN CHƯA ĐẠT:

PHƯƠNG ÁN:
- Giữ mục tiêu, điều chỉnh cách thực hiện:
- Giữ mục tiêu, thương lượng dời hạng mục bổ sung:
- Điều kiện hoặc nghĩa vụ không được bỏ:

QUYẾT ĐỊNH VÀ NGƯỜI CÓ QUYỀN CHỐT:
DỰ BÁO CÓ ĐIỀU KIỆN:
RỦI RO CÒN MỞ / PHỤ THUỘC:
THỜI ĐIỂM XEM LẠI / KÊNH THÔNG BÁO:
~~~

Mẫu này chỉ là gợi ý, **không phải artifact bắt buộc của Scrum**. Với một thay đổi rất nhỏ, cập nhật Sprint Backlog và trao đổi trực tiếp có thể đủ. Với sự cố, ràng buộc pháp lý hoặc cam kết đối tác, cần kênh chính thức phù hợp.

### 15.2. Ví dụ truyền đạt ngắn gọn

> “Sprint Goal đăng ký workshop đáng tin cậy vẫn còn giá trị. Kiểm thử ngày thứ năm phát hiện lỗi tranh chỗ cuối, vì vậy nhóm đang ưu tiên khắc phục và kiểm chứng. Tính năng email có nguy cơ chưa đạt DoD trong Sprint này; Product Owner và Developers đã thống nhất xem xét dời phần email nếu không ảnh hưởng cam kết bắt buộc. Chúng tôi sẽ cập nhật kết quả kiểm thử và phạm vi hoàn chỉnh vào Sprint Review, không tuyên bố email đã Done khi chưa kiểm chứng.”

Thông điệp giúp người nghe thấy **quyết định có căn cứ và trách nhiệm chất lượng**, không phải lời biện hộ vì trễ kế hoạch.

### 15.3. Đo lường nhưng không chạy theo số lượng

Có thể dùng:

- **Work item age** của các PBI đang thực hiện để phát hiện việc bị chặn.
- **Cycle time và throughput** theo định nghĩa Done nhất quán để xem dòng công việc.
- **Lỗi sau phát hành và công việc làm lại** để đánh giá chất lượng.
- **Tỷ lệ hạng mục đạt DoD** và nguyên nhân chưa hoàn tất để cải thiện cách chia nhỏ.
- **Kết quả người dùng** để biết Increment có tạo giá trị hay không.
- **Thời gian chờ phụ thuộc và số lần công việc bị ngắt** để thấy rào cản hệ thống.

Không nên dùng story point, velocity hoặc số PBI hoàn thành làm chỉ tiêu thưởng phạt cho từng người. Những cách đo đó dễ khiến nhóm đánh dấu Done thiếu kiểm chứng, chia việc giả hoặc giấu rủi ro. Số liệu phải **giúp kiểm tra và thích ứng**, không thay thế Sprint Goal và chất lượng.

## 16. Những hiểu lầm và sai lầm thường gặp

| Hiểu lầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Sprint đã bắt đầu thì cấm mọi thay đổi” | Nhóm bỏ qua thông tin mới, phản hồi chậm | Có thể làm rõ và thương lượng phạm vi khi học thêm, nhưng giữ Sprint Goal và chất lượng |
| “Stakeholder có yêu cầu mới thì phải thêm ngay vào Sprint” | Sprint Goal mất tập trung, WIP tăng | Product Owner đánh giá giá trị và thứ tự; Developers nêu tác động |
| “Sprint Goal là hoàn thành 100% PBI đã chọn” | Mục tiêu bị đồng nhất với danh sách việc | Sprint Goal diễn đạt kết quả tập trung; phạm vi là công cụ đạt mục tiêu |
| “Không đủ điểm dự kiến thì cần hủy Sprint” | Dùng hủy Sprint để che sai lệch dự báo | Hủy chỉ khi Sprint Goal lỗi thời, do Product Owner quyết |
| “Scrum Master hoặc trưởng bộ phận có thể tự hủy Sprint” | Sai thẩm quyền Scrum | Chỉ Product Owner có thẩm quyền hủy Sprint |
| “Để giữ lịch, có thể bỏ kiểm thử” | Increment không đủ chất lượng, tăng lỗi người dùng | Chất lượng không được suy giảm; làm rõ hoặc dời phạm vi tùy chọn |
| “Code xong 90% thì tính Done 90%” | Báo cáo sai khả năng giao giá trị | PBI chỉ góp vào Increment khi đáp ứng DoD |
| “Sprint chưa hoàn tất thì kéo dài thêm vài ngày” | Mất timebox và nhịp kiểm tra | Sprint kết thúc đúng thời hạn; xử lý công việc chưa Done minh bạch |
| “PBI chưa Done mặc định sang Sprint kế tiếp” | Tạo ưu tiên và cam kết giả | Đưa về Product Backlog để Product Owner và nhóm xem xét lại |
| “Sprint Review là buổi ký duyệt những gì nhóm code được” | Che việc chưa Done, thiếu phản hồi | Review đánh giá Increment và điều chỉnh hướng đi; không thay DoD |
| “Có sự cố là phải hủy Sprint” | Nhầm ảnh hưởng năng lực với mục tiêu lỗi thời | Phản ứng sự cố; chỉ cân nhắc hủy nếu Sprint Goal thực sự lỗi thời |
| “Hủy Sprint thì xóa toàn bộ mã và quên công việc cũ” | Mất giá trị đã hoàn tất, tăng rủi ro dữ liệu | Kiểm kê Increment đạt DoD, bảo vệ trạng thái, xem lại backlog |
| “Đổi Sprint Goal liên tục để báo cáo luôn thành công” | Không còn mục tiêu tập trung hoặc cam kết đáng tin | Giữ định hướng trong Sprint; nếu mục tiêu lỗi thời, Product Owner cân nhắc hủy |
| “Cứ đưa phần dở vào demo rồi xin stakeholder chấp thuận” | Trình bày chưa đạt DoD như Increment | Minh bạch phần chưa xong mà không gọi là sản phẩm hoàn chỉnh |
| “Càng hủy Sprint nhiều càng Agile” | Nhịp làm việc thiếu ổn định, tổn thất phối hợp | Thích ứng dựa trên bằng chứng; hủy khi có điều kiện đúng, không xem hủy là mục tiêu |

## 17. Quy trình phản ứng ngắn cho Scrum Team

Để dễ nhớ, có thể dùng **sáu câu hỏi** trong mọi tình huống thay đổi hoặc công việc không hoàn tất:

1. **Sự thật mới là gì?** Phân biệt bằng chứng và suy đoán.
2. **Sprint Goal còn giá trị không?** Đừng nhầm khó đạt với lỗi thời.
3. **Điều gì bắt buộc phải đúng để đạt DoD và giữ an toàn?** Không đánh đổi chất lượng để giữ lịch.
4. **Ai có quyền quyết việc nào?** Product Owner về giá trị, thứ tự backlog và hủy Sprint; Developers về kế hoạch Sprint; Scrum Master giúp vận dụng Scrum hiệu quả.
5. **Phạm vi, phụ thuộc và dự báo cần điều chỉnh gì?** Thương lượng rõ và thông báo sớm.
6. **Chúng ta sẽ kiểm tra lại bằng chứng nào và khi nào?** Dùng Increment, phản hồi và dữ liệu dòng công việc để thích ứng.

### Checklist lựa chọn hành động

~~~text
[ ] Đã làm rõ thông tin mới và tác động tới người dùng
[ ] Đã xác nhận Sprint Goal còn giá trị hay đã lỗi thời
[ ] Đã xác định ràng buộc bảo mật, chất lượng và DoD cần giữ
[ ] Developers đã kiểm tra Sprint Backlog và phần công việc còn lại
[ ] Product Owner đã tham gia khi cần thương lượng phạm vi/ưu tiên
[ ] Rủi ro khẩn đã được xử lý theo quy trình phù hợp
[ ] Những phần chưa Done không được tính là Increment
[ ] Nếu Sprint kết thúc, công việc chưa Done được đưa về Product Backlog để xem xét
[ ] Chỉ Product Owner quyết định hủy nếu Sprint Goal lỗi thời
[ ] Các bên chịu ảnh hưởng đã nhận được thông tin và dự báo có điều kiện
[ ] Có thời điểm kiểm tra lại và cơ hội cải tiến cách làm
~~~

Checklist là **công cụ ghi nhớ**, không phải luật bổ sung của Scrum. Hành động cần tương xứng với rủi ro và hoàn cảnh thực tế.

## 18. Bài tập thực hành: quyết định trong Sprint

Một Scrum Team làm Sprint hai tuần cho nền tảng học tập. **Sprint Goal:** “Học viên hoàn thành một bài có thể tiếp tục sang bài phù hợp tiếp theo và tiến độ được lưu đáng tin cậy.”

Nhóm đã chọn các PBI:

| Mã | PBI | Trạng thái vào ngày thứ bảy |
| --- | --- | --- |
| A | Nút “Học bài tiếp theo” | Đã tích hợp và kiểm thử đạt DoD |
| B | Lưu tiến độ khi mạng gián đoạn | Đang sửa lỗi trùng trạng thái |
| C | Thông báo nhắc học hằng ngày | Đã code, chưa kiểm thử quyền riêng tư |
| D | Bảng thống kê tiến độ | Chưa bắt đầu |

Trong ngày thứ bảy xuất hiện bốn thông tin:

1. Một stakeholder muốn ưu tiên bảng xếp hạng điểm của học viên thay cho mọi hạng mục còn lại.
2. Dữ liệu thử nghiệm cho thấy lỗi mất tiến độ của B ảnh hưởng đáng kể tới học viên.
3. Tổ chức thông báo sẽ **ngừng hỗ trợ nền tảng học tập hiện tại**, chuyển toàn bộ người dùng sang sản phẩm khác và mục tiêu lưu tiến độ trên nền tảng cũ không còn sử dụng.
4. Một quản lý đề nghị “bỏ kiểm thử quyền riêng tư của C cho kịp thời hạn”.

### Yêu cầu

Với từng thông tin, hãy trả lời:

1. Sprint Goal có còn giá trị không? Bạn cần thêm bằng chứng nào?
2. Đây là thay đổi phạm vi, rủi ro chất lượng, hay trường hợp có thể hủy Sprint?
3. Product Owner, Developers và Scrum Master làm gì, ai có quyền chốt?
4. Những PBI nào đã có thể là Increment và những PBI nào chưa Done?
5. Nếu Sprint kết thúc bình thường vào ngày thứ mười mà B, C, D vẫn chưa đạt DoD, chúng sẽ được xử lý thế nào?
6. Nếu Product Owner hủy Sprint vì mục tiêu lỗi thời, cần làm gì với A, B, C, D và những dữ liệu đã thay đổi?
7. Bạn sẽ nói gì với stakeholder để vừa minh bạch vừa không tạo cam kết sai?

### Gợi ý hướng giải

**Thông tin 1:** Yêu cầu bảng xếp hạng mới không tự làm Sprint Goal lỗi thời. Product Owner đánh giá giá trị và thứ tự Product Backlog; Developers nêu tác động tới Sprint Goal. Có thể để đề xuất cho giai đoạn sau nếu chưa cấp bách thật.

**Thông tin 2:** Lỗi B ảnh hưởng trực tiếp tới Sprint Goal “tiến độ được lưu đáng tin cậy”. Nhóm ưu tiên kiểm chứng và sửa lỗi; cân nhắc dời D hoặc C nếu đó là phạm vi tùy chọn và không vi phạm điều kiện cốt lõi.

**Thông tin 3:** Nếu quyết định chính thức khiến mục tiêu trên nền tảng cũ không còn giá trị, đây là **ứng viên thực sự cho hủy Sprint**. Product Owner có thẩm quyền quyết định, sau khi làm rõ bối cảnh và tác động. Không tự kết luận chỉ từ một tin đồn chưa được xác nhận.

**Thông tin 4:** Không được tự hạ yêu cầu chất lượng hoặc quyền riêng tư. C **chưa đạt DoD**; nhóm có thể điều chỉnh phạm vi hoặc thời điểm, không giả vờ phần này hoàn chỉnh.

**Nếu Sprint kết thúc bình thường:** A là phần hoàn chỉnh nếu đã đáp ứng DoD. B, C, D chưa Done, không được tính là Increment và trở về Product Backlog để xem xét lại; không có quy tắc bắt buộc chúng phải vào Sprint tiếp.

**Nếu Sprint bị hủy:** Product Owner công bố lý do mục tiêu lỗi thời. Developers giữ minh bạch A đã Done, xử lý trạng thái an toàn của công việc B/C đang dang dở; Product Owner xem lại tất cả hạng mục theo định hướng sản phẩm mới. Việc xử lý dữ liệu và nghĩa vụ quyền riêng tư vẫn phải tuân thủ dù Sprint bị hủy.

Một câu trả lời tốt nêu rõ **tại sao**, **ai có trách nhiệm**, **điều gì đã đạt DoD** và **sự thật nào làm thay đổi quyết định**, chứ không chỉ chọn “hủy” hay “không hủy”.

## 19. Ghi nhớ và tự kiểm tra

Ba nguyên tắc cần giữ là:

1. **Thay đổi trong Sprint được xử lý bằng minh bạch và thích ứng:** Developers có thể điều chỉnh kế hoạch, làm rõ và thương lượng phạm vi với Product Owner khi học thêm, miễn Sprint Goal không bị làm nguy hại và chất lượng không giảm.
2. **Công việc chưa đạt Definition of Done không phải Increment hoàn chỉnh:** Khi Sprint kết thúc, phần chưa Done được xem xét lại trong Product Backlog, không tự động được tính thành kết quả hoặc chuyển thẳng sang Sprint sau.
3. **Chỉ Product Owner có thẩm quyền hủy Sprint, và điều kiện cốt lõi là Sprint Goal trở nên lỗi thời:** Trễ tiến độ, PBI lớn hơn dự kiến hoặc xuất hiện yêu cầu mới không tự đủ để hủy.

Tự kiểm tra:

1. Sprint Goal khác các PBI được chọn và kế hoạch trong Sprint Backlog thế nào?
2. Những thay đổi nào được phép trong Sprint và hai ràng buộc cốt lõi không được vi phạm là gì?
3. Ai chịu trách nhiệm quản lý Sprint Backlog? Ai chịu trách nhiệm thứ tự Product Backlog?
4. Nếu một lỗi bảo mật khẩn xảy ra giữa Sprint, nhóm có phải đợi Sprint Planning tiếp theo mới được xử lý không?
5. Vì sao “đã code xong nhưng chưa qua kiểm thử bắt buộc” không được coi là Done?
6. Điều gì xảy ra với PBI chưa hoàn tất khi Sprint kết thúc đúng timebox?
7. Tại sao không được mặc định chuyển toàn bộ công việc dở sang Sprint kế tiếp?
8. Phân biệt “Sprint Goal khó đạt” và “Sprint Goal lỗi thời” bằng một ví dụ.
9. Ai có thẩm quyền hủy Sprint và Scrum Master đóng vai trò gì trong quyết định?
10. Một Increment đã đạt DoD có bị mất trạng thái hoàn chỉnh chỉ vì Sprint bị hủy không?
11. Sprint Review và Sprint Retrospective giúp nhóm học được gì từ thay đổi và công việc dở dang?
12. Bạn sẽ thông báo với stakeholder ra sao khi phải dời phạm vi nhưng vẫn bảo vệ chất lượng và mục tiêu?

Trước khi quyết định **giữ kế hoạch, điều chỉnh phạm vi, xử lý công việc dở hay hủy Sprint**, hãy hỏi: **“Sprint Goal còn tạo giá trị không, phần mềm nào thực sự đã đạt Definition of Done, và ai có thẩm quyền quyết định bước tiếp theo?”** Ba câu hỏi đó giúp Scrum Team thích ứng trước thay đổi mà vẫn đáng tin cậy, tập trung và có trách nhiệm với người dùng.
