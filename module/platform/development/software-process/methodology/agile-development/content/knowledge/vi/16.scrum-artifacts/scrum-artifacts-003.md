# Increment và cam kết Definition of Done

## 1. “Đã xong” phải có nghĩa là sản phẩm thực sự dùng được

Trong một nhóm phát triển phần mềm, câu “tính năng đã hoàn thành” có thể mang nhiều ý nghĩa:

- Lập trình viên đã viết mã và đẩy lên nhánh làm việc.
- Pull request đã được duyệt và hợp nhất.
- Một số kiểm thử tự động đã chạy thành công.
- Người kiểm thử đã xác minh luồng chính, nhưng vẫn còn lỗi nghiêm trọng.
- Chức năng đã tích hợp, đáp ứng tiêu chuẩn chất lượng và có thể sử dụng.
- Chức năng đã phát hành cho người dùng thật và có dữ liệu phản hồi.

Những trạng thái này **không tương đương**. Nếu mỗi người dùng một định nghĩa khác nhau, nhóm có thể báo cáo “đã xong tám story” trong khi chưa có phần sản phẩm nào đủ an toàn và ổn định để sử dụng.

**Scrum** giải quyết vấn đề minh bạch đó bằng hai khái niệm liên kết:

1. **Increment** là một bước tiến cụ thể của sản phẩm hướng tới **Product Goal**. Mỗi Increment được bổ sung vào các Increment trước đó, được xác minh đầy đủ cùng những phần đã có và phải **dùng được**.
2. **Definition of Done (DoD)** là mô tả chính thức về trạng thái của Increment khi nó đạt những **tiêu chuẩn chất lượng bắt buộc đối với sản phẩm**. DoD là **commitment (cam kết)** gắn với artifact Increment.

Ví dụ, một nhóm phát triển ứng dụng đặt lịch khám hoàn thành màn hình chọn giờ. Nếu nút “Đặt lịch” chỉ hiển thị thông báo thành công mà hệ thống chưa ghi nhận lịch hợp lệ, giao diện có thể chạy được trong buổi demo nhưng **chưa tạo được Increment đặt lịch dùng được**. Nếu thông tin lịch đã được lưu chính xác, quyền truy cập được bảo vệ, không tạo lịch trùng và các kiểm tra thiết yếu hoàn tất, nhóm mới có cơ sở xem phần chức năng đó đạt chất lượng theo DoD đã thống nhất.

Đây là nội dung nền tảng của chương **Tạo tác Scrum** thuộc module **AGILE_DEVELOPMENT**: tạo giá trị theo từng phần nhỏ, nhận phản hồi sớm và cải tiến liên tục. User story và Product Backlog giúp diễn đạt việc cần làm; Scrum cung cấp nhịp kiểm tra–thích ứng; thực hành Kanban và XP có thể hỗ trợ dòng công việc và chất lượng. Tuy nhiên, **không có Increment dùng được thì một Sprint chỉ có thể kết thúc bằng nhiều hoạt động đã thực hiện, chứ chưa chắc có giá trị sản phẩm mới**.

### Kết quả học tập

Sau bài học, người học có thể:

- Giải thích Increment và DoD đúng mối quan hệ artifact–commitment trong Scrum.
- Phân biệt **task hoàn thành**, **Product Backlog Item đạt Done**, **Increment**, **phát hành** và **outcome**.
- Xây dựng, áp dụng và cải tiến DoD phù hợp với chất lượng sản phẩm và tiêu chuẩn tổ chức.
- Phân biệt DoD với tiêu chí chấp nhận, Definition of Ready, kiểm thử người dùng và điều kiện triển khai.
- Xử lý các trường hợp nhiều Increment trong một Sprint, hạng mục chưa đạt DoD, phụ thuộc bên ngoài và nhiều Scrum Team cùng làm một sản phẩm.
- Lựa chọn kiểm tra, tự động hóa và chỉ số để tăng khả năng bàn giao an toàn, không làm sai lệch trạng thái công việc.

## 2. Increment là gì trong Scrum?

Theo **Scrum Guide 2020**, Increment là một **bước tiến cụ thể hướng tới Product Goal**. Mỗi Increment:

1. **Bổ sung** vào các Increment trước.
2. Được **xác minh đầy đủ** để các phần hoạt động cùng nhau.
3. Phải **dùng được (usable)** nhằm mang lại giá trị.

Scrum Team chịu trách nhiệm tạo ra **một Increment có giá trị, hữu ích trong mỗi Sprint**. Có thể tạo **nhiều Increment trong cùng một Sprint**; giá trị có thể được giao cho stakeholder trước khi Sprint kết thúc.

### 2.1. Increment không phải một tập hợp tính năng chưa tích hợp

Giả sử ứng dụng đặt lịch khám đã có các khả năng xem chuyên khoa và xem thông tin bác sĩ. Trong Sprint mới, nhóm bổ sung khả năng xem khung giờ còn trống. Để trở thành một Increment, phần mới phải vận hành nhất quán với phần trước:

- Chọn đúng chuyên khoa và bác sĩ dẫn tới khung giờ phù hợp.
- Dữ liệu hiển thị không làm lộ thông tin không được phép.
- Phản hồi lỗi có thể hiểu được khi dịch vụ lịch tạm thời không sẵn sàng.
- Các luồng hiện có không bị phá vỡ do thay đổi ở API hoặc dữ liệu.
- Các tiêu chuẩn chất lượng trong DoD đã được đáp ứng.

Nếu mỗi phần chỉ chạy riêng trong môi trường của từng lập trình viên, chúng chưa tạo được một bước tiến **tích hợp và dùng được**.

### 2.2. Increment phải bổ sung vào sản phẩm đang tồn tại

“Bổ sung” không nhất thiết chỉ có nghĩa thêm một màn hình hoặc API. Increment có thể:

- Mở rộng một khả năng đang có.
- Giảm thời gian chờ hoặc lỗi trong một hành trình quan trọng.
- Sửa hành vi sai để sản phẩm đáng tin hơn.
- Cải thiện khả năng tiếp cận hoặc an toàn trong phạm vi có thể sử dụng.

Giá trị có thể trực tiếp đối với người dùng hoặc gián tiếp thông qua việc giữ sản phẩm an toàn và dễ thay đổi. Tuy nhiên, **một task riêng lẻ như tạo nhánh mã, viết tài liệu thử hoặc thiết lập một phần cấu hình chưa đủ để tự động gọi là Increment**. Cần nhìn vào kết quả đã được tích hợp và đủ khả năng sử dụng.

### 2.3. Một Increment không nhất thiết phải được phát hành công khai ngay

**Usable** và **released** là hai thuộc tính khác nhau:

- **Dùng được:** chức năng hoặc cải tiến đã ở trạng thái đáp ứng chất lượng theo DoD và có thể được sử dụng trong phạm vi phù hợp.
- **Đã phát hành:** sản phẩm hoặc phần thay đổi đã được cung cấp cho đối tượng nhận theo chiến lược phát hành.

Một Increment có thể đã Done và dùng được nhưng chưa được phát hành rộng vì lịch kinh doanh, yêu cầu triển khai hoặc cách mở dần tính năng. Ngược lại, **mã được đưa lên production không tự chứng minh rằng nó đã đáp ứng DoD**.

Ví dụ, nhóm có thể phát hành tính năng chọn giờ cho một nhóm phòng khám thí điểm trước khi mở cho toàn bộ cơ sở. Việc mở giới hạn cần dựa trên kiểm soát rủi ro phù hợp; không thể lấy chữ “pilot” làm lý do bỏ qua các kiểm soát bắt buộc.

### 2.4. Increment, story, task và release khác nhau

| Khái niệm | Bản chất | Ví dụ đặt lịch khám |
|---|---|---|
| **Task** | Hoạt động cụ thể hỗ trợ thực hiện công việc. | Viết API đọc giờ trống. |
| **Product Backlog Item (PBI)** | Một hạng mục công việc cần thiết để cải thiện sản phẩm. | “Người bệnh xem được khung giờ còn trống”. |
| **PBI đạt Done** | Hạng mục đáp ứng Definition of Done áp dụng. | Luồng xem giờ trống được tích hợp, xác minh, đáp ứng chất lượng. |
| **Increment** | Bước tiến tích hợp, dùng được, cộng vào sản phẩm hiện có. | Sản phẩm có thêm khả năng xem giờ trống hoạt động với chức năng trước đó. |
| **Release** | Hành động đưa một hoặc nhiều Increment đến đối tượng nhận. | Mở luồng xem giờ trống cho phòng khám A. |
| **Outcome** | Sự thay đổi hành vi hoặc kết quả tạo giá trị. | Người bệnh chọn giờ thuận tiện hơn và ít gọi tổng đài hơn. |

Một PBI có thể được tạo ra bằng nhiều task; nhiều PBI Done có thể cùng đóng góp vào một Increment hoặc nhiều Increment. Scrum không yêu cầu một PBI luôn tương ứng chính xác một Increment, và không đòi mỗi Increment phải là một release riêng.

## 3. Definition of Done là cam kết của Increment

Trong Scrum, ba artifact gắn với ba commitment:

| Artifact | Commitment | Câu hỏi trọng tâm |
|---|---|---|
| **Product Backlog** | **Product Goal** | Chúng ta đang hướng tới giá trị dài hạn nào? |
| **Sprint Backlog** | **Sprint Goal** | Sprint hiện tại cần đạt kết quả quan trọng nào? |
| **Increment** | **Definition of Done** | Khi nào phần sản phẩm thực sự đạt tiêu chuẩn chất lượng để được coi là hoàn thành? |

**DoD không phải một bản kế hoạch riêng hoặc một lời hứa hoàn thành đúng ngày.** Nó là tiêu chuẩn minh bạch để biết trạng thái chất lượng của Increment. Không đạt DoD thì một PBI không được coi là đã hoàn thành theo Scrum, dù đã tốn nhiều công sức.

### 3.1. Định nghĩa chính xác

DoD là **mô tả chính thức về trạng thái của Increment khi nó đáp ứng những thước đo chất lượng cần thiết cho sản phẩm**.

Cụm “cho sản phẩm” rất quan trọng: DoD cần phù hợp với đặc điểm và rủi ro của sản phẩm. Một hệ thống đặt lịch liên quan dữ liệu cá nhân có yêu cầu khác với một trang giới thiệu nội bộ không lưu dữ liệu nhạy cảm. Tuy nhiên, nhóm không được tự ý bỏ tiêu chuẩn bảo mật hoặc quy định bắt buộc chỉ để làm DoD dễ đạt.

Khi một Product Backlog Item **đáp ứng DoD**, một Increment được sinh ra theo nghĩa Scrum. Những gì chưa đáp ứng DoD là **công việc chưa Done**, không phải một Increment hoàn thành nhưng “còn vài việc nhỏ”.

### 3.2. Vì sao gọi là “commitment”?

Commitment của artifact giúp tăng **minh bạch và tập trung**:

- Product Goal giúp tập trung vào hướng sản phẩm.
- Sprint Goal giúp Developers điều chỉnh việc làm để đạt mục tiêu Sprint.
- DoD giúp mọi người hiểu thống nhất **mức chất lượng cần có của phần sản phẩm được tuyên bố hoàn thành**.

Nếu DoD chỉ là khẩu hiệu nhưng bị bỏ qua khi thời hạn đến gần, minh bạch về Increment mất đi. Bản báo cáo “Done” có thể khiến Product Owner và stakeholder hiểu sai khả năng sử dụng và rủi ro.

### 3.3. Tiêu chuẩn cấp tổ chức và DoD của Scrum Team

Scrum Guide đặt ra nguyên tắc:

- Nếu DoD là một phần của **tiêu chuẩn tổ chức**, mọi Scrum Team phải tuân theo tiêu chuẩn đó **như mức tối thiểu**.
- Nếu chưa có tiêu chuẩn cấp tổ chức, **Scrum Team** phải tạo một DoD phù hợp với sản phẩm.
- Nếu **nhiều Scrum Team cùng làm một sản phẩm**, họ phải **cùng xác định và tuân theo một DoD chung**.

Một nhóm có thể áp dụng tiêu chuẩn cao hơn mức tối thiểu của tổ chức khi phù hợp, nhưng không được xem tiêu chuẩn bắt buộc như lựa chọn tự do.

**Ví dụ:** tổ chức yêu cầu không đưa thông tin nhạy cảm vào log và mọi thay đổi phải qua rà soát quyền truy cập. Scrum Team có thể bổ sung kiểm thử đồng bộ lịch, kiểm tra kịch bản đặt trùng hoặc giám sát trạng thái đặt lịch. Các yêu cầu bổ sung làm rõ chất lượng của **sản phẩm cụ thể**.

## 4. DoD khác tiêu chí chấp nhận, DoR và điều kiện phát hành

Nhầm lẫn giữa các loại tiêu chí là nguyên nhân phổ biến khiến việc báo “Done” thiếu nhất quán.

| Loại | Phạm vi chính | Ví dụ | Vai trò trong Scrum |
|---|---|---|---|
| **Definition of Done** | Tiêu chuẩn chất lượng chung của Increment. | Tích hợp thành công; kiểm thử cần thiết đạt; quyền truy cập và rủi ro dữ liệu được kiểm tra. | Commitment chính thức của Increment. |
| **Acceptance criteria** | Hành vi cụ thể của một PBI/story. | Không thể đặt hai lịch hợp lệ trùng cùng một slot. | Làm rõ điều kiện đáp ứng yêu cầu; không phải artifact/commitment riêng của Scrum. |
| **Definition of Ready (DoR)** | Tiêu chí hỗ trợ xem một hạng mục đã đủ rõ để bắt đầu chưa. | Đã xác định mục tiêu, ví dụ chính, phụ thuộc cần thiết. | Thực hành tùy chọn; không được Scrum bắt buộc. |
| **Release criteria** | Điều kiện quyết định việc đưa phần mềm tới một đối tượng vào thời điểm cụ thể. | Đã có kế hoạch mở tính năng theo cơ sở, truyền thông vận hành và giám sát mở rộng. | Thuộc quản trị phát hành; khác với DoD. |
| **User Acceptance Testing (UAT)** | Hoạt động xác nhận với người dùng/nghiệp vụ trong bối cảnh phù hợp. | Nhân viên tiếp nhận thử quy trình xác nhận lịch. | Có thể cung cấp bằng chứng cho tiêu chí/DoD tùy bối cảnh; không thay thế mọi kiểm soát chất lượng. |

### 4.1. DoD là mẫu số chung; acceptance criteria là điểm riêng của câu chuyện

Ví dụ story:

> Với vai trò là người bệnh, tôi muốn xem các giờ khám còn trống để chọn lịch phù hợp mà không phải gọi tổng đài.

**Tiêu chí chấp nhận** có thể gồm:

1. Chỉ hiển thị khung giờ đặt được theo chuyên khoa và bác sĩ đã chọn.
2. Khi không còn giờ, giao diện nêu rõ và không cho xác nhận một giờ không hợp lệ.
3. Khi dữ liệu lịch không tải được, giao diện hiển thị lỗi phù hợp, không tạo trạng thái giả.

**DoD chung** còn có thể yêu cầu tích hợp với phiên bản sản phẩm hiện tại, kiểm thử hồi quy liên quan, kiểm soát quyền truy cập, rà soát an toàn dữ liệu, khả năng quan sát khi lỗi xảy ra và các quy trình phát hành thiết yếu. Dù ba tiêu chí chấp nhận trên đã qua, hạng mục vẫn chưa Done nếu còn thiếu yêu cầu DoD bắt buộc.

### 4.2. DoR không phải hàng rào bắt buộc của Scrum

DoR có thể giúp nhóm giảm việc bắt đầu một hạng mục quá mơ hồ. Tuy nhiên, nếu DoR trở thành cổng phê duyệt quá cứng, mọi công việc khám phá đều bị chặn vì chưa thể biết toàn bộ câu trả lời.

Một spike kỹ thuật có thể được thực hiện **để tìm câu trả lời chưa có**. Điều cần rõ trước khi bắt đầu loại việc này là câu hỏi cần học, phạm vi, giới hạn đầu tư và đầu ra mong đợi, không phải mọi chi tiết giải pháp.

### 4.3. Release criteria không được dùng để “hạ” DoD

DoD xác nhận phần sản phẩm đạt tiêu chuẩn chất lượng cần thiết; release criteria quyết định **có nên mở phần đó cho ai và khi nào**. Khi sản phẩm có nghĩa vụ pháp lý hoặc yêu cầu an toàn, những kiểm soát đó cần được xử lý phù hợp ngay trong tiêu chuẩn chất lượng, không được trì hoãn một lỗi nghiêm trọng rồi gọi là “bổ sung sau release”.

Ngược lại, một hoạt động truyền thông ra mắt toàn quốc có thể nằm trong kế hoạch release dù Increment đã đạt DoD và sẵn sàng thử trong phạm vi được phép.

## 5. Những khía cạnh chất lượng nên cân nhắc khi xây DoD

DoD không có một checklist chung phù hợp với mọi sản phẩm. Nhóm cần xét rủi ro, kiến trúc, yêu cầu khách hàng, tiêu chuẩn tổ chức và năng lực vận hành để xác định tiêu chuẩn **có thể kiểm chứng**.

| Khía cạnh | Câu hỏi cần trả lời | Bằng chứng/tiêu chí minh họa |
|---|---|---|
| **Chức năng và nghiệp vụ** | Hành vi mong đợi có đúng với quy tắc đã thống nhất? | Ví dụ cốt lõi và trường hợp biên được xác minh; kết quả đáp ứng tiêu chí chấp nhận. |
| **Tích hợp** | Phần mới có hoạt động cùng các Increment trước? | Kiểm thử tích hợp/hợp đồng ở phạm vi phù hợp, không phá luồng cũ. |
| **Kiểm thử hồi quy** | Thay đổi có làm hỏng hành vi hiện có? | Bộ kiểm thử phù hợp đạt; lỗi chặn sử dụng được xử lý. |
| **Bảo mật và quyền riêng tư** | Dữ liệu và thao tác có được bảo vệ đúng không? | Kiểm tra phân quyền, không lộ thông tin nhạy cảm, tuân tiêu chuẩn áp dụng. |
| **Tính toàn vẹn dữ liệu** | Có thể xuất hiện trạng thái sai khi xử lý lặp hay đồng thời? | Đặt lịch trùng bị ngăn theo quy tắc; kết quả ghi nhận nhất quán. |
| **Khả năng tiếp cận** | Người dùng có nhu cầu hỗ trợ có thực hiện được tác vụ? | Kiểm tra yêu cầu tiếp cận phù hợp với sản phẩm và đối tượng sử dụng. |
| **Hiệu năng và độ tin cậy** | Phản hồi và khả năng hoạt động có phù hợp tải dự kiến? | Kiểm tra ngưỡng chất lượng được xác định có cơ sở trong môi trường đại diện. |
| **Khả năng quan sát** | Có phát hiện và chẩn đoán lỗi quan trọng? | Log/metric phù hợp, cảnh báo hoặc dấu vết cần thiết đã được kiểm tra. |
| **Khả năng vận hành** | Có thể triển khai, cấu hình, hỗ trợ hoặc khôi phục an toàn? | Quy trình triển khai/khôi phục phù hợp được chuẩn bị và kiểm tra. |
| **Khả năng bảo trì** | Mã có thể được thay đổi an toàn ở các Sprint sau? | Tích hợp vào nhánh chung, rà soát mã và kiểm tra cần thiết theo chính sách. |
| **Tài liệu thiết yếu** | Có thông tin cần thiết cho người dùng, hỗ trợ hoặc vận hành? | Hướng dẫn hoặc ghi chú thay đổi bắt buộc được cập nhật tại nơi sử dụng. |

Không nên biến mọi dòng trong bảng thành yêu cầu cùng độ nặng cho mọi câu chuyện. Ví dụ, một thay đổi văn bản giao diện có thể không cần chạy lại một bài kiểm thử tải quy mô lớn nếu có cơ sở đánh giá rủi ro. Nhưng yêu cầu kiểm soát quyền truy cập áp dụng bắt buộc vẫn phải được đáp ứng, dù hạng mục trông nhỏ.

**DoD phải đủ rõ để kiểm tra và đủ phù hợp để sử dụng liên tục.** “Mã tốt”, “trải nghiệm đẹp” hoặc “chạy không lỗi” đều quá mơ hồ nếu không có bằng chứng hoặc giới hạn rõ ràng.

### 5.1. Phân biệt tiêu chuẩn với công cụ

“Chạy kiểm thử bằng công cụ X” là mô tả quy trình/công cụ; “các trường hợp hồi quy bắt buộc đạt” gần với tiêu chuẩn chất lượng hơn. Công cụ có thể thay đổi, trong khi yêu cầu về kết quả nên tiếp tục có hiệu lực.

Nhóm vẫn có thể đưa một công cụ, cấu hình hoặc bước kiểm tra bắt buộc vào cách thể hiện DoD khi tổ chức yêu cầu. Điều quan trọng là biết **bằng chứng nào xác nhận chất lượng**, không chỉ tích đủ ô trong một biểu mẫu.

### 5.2. Ví dụ DoD có cấu trúc

Ví dụ tham khảo cho một sản phẩm web có dữ liệu cá nhân:

~~~text
DEFINITION OF DONE - ví dụ, cần điều chỉnh theo sản phẩm

Khi tuyên bố một Product Backlog Item đã Done:
  [ ] Hành vi cần thiết và tiêu chí chấp nhận liên quan đã được xác minh.
  [ ] Mã, cấu hình và thay đổi dữ liệu đã tích hợp với sản phẩm hiện có.
  [ ] Kiểm tra tự động và thủ công thiết yếu theo mức rủi ro đã đạt.
  [ ] Không có lỗi chưa xử lý làm vi phạm tiêu chuẩn chất lượng bắt buộc.
  [ ] Các kiểm soát phân quyền, dữ liệu cá nhân và bảo mật áp dụng đã đạt.
  [ ] Thay đổi không phá vỡ những luồng sử dụng hiện có trong phạm vi kiểm tra.
  [ ] Cách triển khai, khôi phục và quan sát cần thiết đã sẵn sàng.
  [ ] Hướng dẫn người dùng/vận hành bắt buộc đã được cập nhật.
  [ ] Increment tích hợp và có thể dùng được theo mục đích đã xác định.

Nếu thiếu một điều kiện áp dụng:
  - Không đánh dấu PBI là Done.
  - Minh bạch việc còn thiếu, tác động và phương án xử lý.
  - Điều chỉnh công việc hoặc phạm vi theo đúng accountability.
~~~

Checklist trên là **định dạng thể hiện**, không phải phép thay thế cho việc kiểm tra thật. Các mục cần có cách hiểu chung, ví dụ cụ thể và bằng chứng phù hợp.

## 6. Từ Product Backlog Item đến Increment: luồng kiểm chứng

Một hạng mục trong Product Backlog chưa tự trở thành Increment vì đã được đưa vào Sprint. Cả nhóm cần làm rõ nhu cầu, triển khai và xác minh để chuyển từ một **ý định** thành một **phần sản phẩm dùng được**.

~~~mermaid
flowchart TD
    A["Product Goal và Product Backlog"] --> B["Làm rõ PBI, ví dụ, tiêu chí chấp nhận"]
    B --> C["Developers phối hợp thiết kế, xây dựng, kiểm thử"]
    C --> D["Tích hợp với các Increment trước"]
    D --> E{"Đáp ứng Definition of Done?"}
    E -->|"Chưa"| F["Minh bạch phần còn thiếu, xử lý và kiểm tra lại"]
    F --> C
    E -->|"Đạt"| G["PBI Done; hình thành Increment dùng được"]
    G --> H["Có thể bàn giao khi phù hợp"]
    G --> I["Kiểm tra phản hồi và cập nhật Product Backlog"]
    H --> I
~~~

Sơ đồ là cách nhìn thực hành, không phải quy trình tuần tự cứng. Nghiệp vụ, phát triển và kiểm thử có thể trao đổi, tích hợp và kiểm tra nhiều lần trong lúc tạo ra phần việc. **Kiểm tra sớm làm giảm chi phí của việc phát hiện sai ở cuối Sprint**.

### 6.1. Ai chịu trách nhiệm?

| Accountability | Vai trò trong việc tạo Increment và tuân thủ DoD |
|---|---|
| **Developers** | Tạo các khía cạnh của Increment dùng được trong mỗi Sprint; tuân thủ DoD; phối hợp để tích hợp và kiểm tra; thích ứng kế hoạch hướng tới Sprint Goal. |
| **Product Owner** | Tối đa hóa giá trị sản phẩm; quản lý hiệu quả Product Backlog và làm rõ giá trị, thứ tự ưu tiên, phạm vi; hợp tác khi xuất hiện rủi ro hoặc thông tin mới. |
| **Scrum Master** | Chịu trách nhiệm về hiệu quả Scrum Team và thiết lập Scrum; giúp nhóm và tổ chức hiểu tầm quan trọng của DoD, minh bạch và kiểm tra–thích ứng. |
| **Scrum Team nói chung** | Cùng chịu trách nhiệm tạo Increment có giá trị và hữu ích trong mỗi Sprint, không đẩy kết quả qua ranh giới phòng ban. |

Scrum không chỉ định một “người kiểm thử” riêng là người duy nhất bảo đảm chất lượng, cũng không biến Product Owner thành người phải tự chạy mọi bài kiểm tra. Các năng lực QA, UX, bảo mật và vận hành có thể nằm trong Developers theo nghĩa rộng hoặc phối hợp với chuyên gia bên ngoài khi cần.

### 6.2. Điều gì xảy ra khi PBI chưa đạt DoD?

Theo Scrum Guide, một Product Backlog Item **không đạt DoD** thì **không được phát hành hoặc trình bày như một phần hoàn thành tại Sprint Review**; thay vào đó nó **quay lại Product Backlog để xem xét trong tương lai**.

Điều này khác với việc cấm team thảo luận về trở ngại. Scrum Team vẫn có thể minh bạch lý do một hạng mục chưa Done, tác động tới mục tiêu và những lựa chọn tiếp theo. Nhưng không được dùng một bản demo đang lỗi để khẳng định đó là Increment hoàn thành.

**Ví dụ:** luồng đặt lịch đã cho chọn giờ nhưng còn tạo lịch trùng trong trường hợp hai người đặt đồng thời. Nếu DoD yêu cầu ngăn lỗi này, PBI chưa Done. Team cần báo tình trạng thật, sửa và kiểm tra lại hoặc đưa việc chưa hoàn thành về Product Backlog; không nên gắn nhãn “Done, còn một bug nhỏ” khi lỗi làm sai nghiệp vụ.

### 6.3. Không tùy tiện hạ DoD vào cuối Sprint

Khi phát hiện khó khăn, nhóm có thể thương lượng **phạm vi** công việc với Product Owner để bảo vệ Sprint Goal, nhưng **chất lượng theo DoD không được giảm**.

Ví dụ, nhóm có thể quyết định trước mắt chỉ hỗ trợ đặt lịch tại một cơ sở thay vì năm cơ sở, miễn phần đặt lịch cho cơ sở đó hoàn chỉnh và đạt tiêu chuẩn chất lượng. Không nên bỏ kiểm tra phân quyền hoặc xử lý cạnh tranh vì “chỉ mở một cơ sở”.

## 7. Có thể tạo nhiều Increment trong một Sprint

Một ngộ nhận phổ biến là Sprint kéo dài hai tuần thì chỉ đến ngày cuối mới có Increment. Thực tế, Scrum cho phép **nhiều Increment trong một Sprint**, và phần giá trị có thể được bàn giao trước Sprint Review.

Giả sử Sprint có mục tiêu cải thiện khả năng xem và đặt lịch:

| Thời điểm minh họa | Kết quả tích hợp | Tình trạng |
|---|---|---|
| Đầu Sprint | Luồng xem giờ trống đáp ứng DoD. | Increment A có thể dùng, có thể lấy phản hồi sớm. |
| Giữa Sprint | Luồng chọn giờ và xác nhận đặt lịch đã tích hợp, đạt DoD. | Increment B bổ sung A, có thể bàn giao khi phù hợp. |
| Cuối Sprint | Tính năng đổi lịch chưa vượt qua kiểm tra trạng thái đồng thời. | Chưa Done, không được xem là Increment C hoàn thành. |

Ví dụ chỉ minh họa logic; ngày đạt Done phụ thuộc năng lực, tích hợp và rủi ro thực tế. **Các Increment cần vận hành cùng nhau**, không phải mỗi Increment có một nhánh riêng chưa hợp nhất.

### 7.1. Sprint Review không phải cổng phát hành

Sprint Review giúp Scrum Team và các bên liên quan **kiểm tra kết quả Sprint và thích ứng Product Backlog**. Nó không phải nghi thức phê duyệt bắt buộc trước mỗi lần release.

Nếu Increment A đạt DoD và việc phát hành phù hợp với chiến lược, nhóm có thể phát hành A trước khi Sprint kết thúc. Tại Sprint Review, nhóm có thể đưa dữ liệu sử dụng và phản hồi thực vào thảo luận về hướng tiếp theo.

### 7.2. Phát hành liên tục đòi hỏi chất lượng liên tục

Khi hệ thống thường xuyên tích hợp và triển khai, DoD càng cần được **kiểm chứng trong luồng làm việc**, không chờ một tuần “harden” ở cuối. Kiểm thử tự động, quan sát hệ thống và quy trình triển khai an toàn có thể giúp giảm thời gian từ mã đã viết đến Increment usable.

Scrum không bắt buộc một công cụ CI/CD hoặc phương pháp kiểm thử duy nhất; team lựa chọn kỹ thuật phù hợp. Kỹ thuật làm việc từ **XP** như tích hợp liên tục, kiểm thử tự động, refactoring, lập trình cặp có thể hỗ trợ rõ rệt.

## 8. Phân biệt “tích hợp”, “kiểm tra” và “được người dùng chấp nhận”

Một số nhóm dùng nhãn “đã QA pass” như thể đó là điều kiện duy nhất. Chất lượng thực tế cần có nhiều dạng bằng chứng:

- **Kiểm tra hành vi:** đáp ứng quy tắc và trường hợp biên đã thống nhất?
- **Kiểm tra tích hợp:** phần mới có hoạt động cùng phần cũ, với dịch vụ liên quan?
- **Kiểm tra chất lượng:** dữ liệu, bảo mật, khả năng truy cập, lỗi, hiệu năng trong phạm vi áp dụng?
- **Khả năng triển khai/vận hành:** có thể bật và hỗ trợ tính năng phù hợp không?
- **Phản hồi của người dùng:** họ có hiểu và đạt mục tiêu thực tế không?

DoD tập trung vào **trạng thái chất lượng của Increment**. Phản hồi người dùng giúp nhóm biết liệu **giá trị kỳ vọng** đã được tạo ra hay cần điều chỉnh. Một Increment đạt DoD vẫn có thể không đem lại outcome mong muốn; khi đó Product Backlog cần được thích ứng, không phải sửa ngược định nghĩa “Done” chỉ để khớp kết quả kinh doanh.

### 8.1. Bằng chứng thực và bằng chứng mô phỏng

Một API mock giúp nhóm phát triển và kiểm tra luồng giao diện trước khi bên ngoài cung cấp dịch vụ thật. Nhưng **mock trả về đúng theo kịch bản của chính nhóm không chứng minh tích hợp với dịch vụ thật đã đạt chất lượng**.

Nếu DoD yêu cầu kiểm tra hợp đồng và tích hợp với hệ thống thực hoặc một môi trường được chấp nhận, nhóm cần hoàn thành đúng yêu cầu đó. Có thể chia lại hạng mục để giao một khả năng hữu ích độc lập, nhưng không thể tự ý tuyên bố phụ thuộc đã biến mất.

### 8.2. Lựa chọn kiểm thử theo rủi ro

Không phải mọi hạng mục cần chạy bộ kiểm thử tải quy mô lớn hoặc toàn bộ kịch bản thủ công của sản phẩm. Nhóm nên xác định các **kiểm soát bắt buộc** và chọn kiểm tra tương xứng với tác động thay đổi, đồng thời duy trì mức chất lượng chung.

Đặc biệt, những luồng liên quan tiền, hồ sơ sức khỏe, quyền truy cập, dữ liệu cá nhân hoặc trạng thái không thể đảo ngược cần sự cẩn trọng cao hơn. **“Nhỏ” về số dòng mã không đồng nghĩa “nhỏ” về rủi ro**.

## 9. Case study: từ màn hình đặt lịch đến Increment dùng được

**Tình huống sau hoàn toàn giả định**, nhằm minh họa cách áp dụng Increment và DoD; không phải đặc tả nghiệp vụ thực tế cho một cơ sở y tế.

### 9.1. Product Goal và Sprint Goal

Product Goal:

> Giúp người bệnh tìm và đặt được lịch khám phù hợp mà không phải liên hệ tổng đài cho các thao tác thông thường.

Sprint Goal:

> Người bệnh có thể xem khung giờ còn trống và xác nhận một lịch hẹn hợp lệ cho một nhóm dịch vụ được hỗ trợ.

Team lựa chọn hai PBI chính:

**PBI A — Xem giờ trống**

> Là người bệnh đang chọn lịch khám, tôi muốn xem các khung giờ còn đặt được để chọn buổi khám phù hợp.

**PBI B — Xác nhận lịch**

> Là người bệnh đã chọn một khung giờ, tôi muốn xác nhận lịch hẹn để biết buổi khám đã được đặt thành công.

Nếu PBI A thực sự hữu ích và đáp ứng DoD, nó có thể tạo một Increment riêng để người dùng tra cứu. PBI B cần bổ sung khả năng đặt lịch và xử lý tính nhất quán để tạo Increment tiếp theo.

### 9.2. Acceptance criteria cho PBI B

Ví dụ các tiêu chí chấp nhận:

1. Người bệnh chỉ có thể đặt những giờ còn hợp lệ tại thời điểm hệ thống xử lý yêu cầu.
2. Nếu hai yêu cầu cạnh tranh cùng giờ, hệ thống không xác nhận hai lịch trùng trái quy tắc.
3. Sau khi đặt thành công, người bệnh nhận đúng ngày, giờ, địa điểm và mã lịch.
4. Khi hệ thống không thể ghi nhận lịch, không phát thông báo thành công sai.
5. Người không có quyền không thể xem hoặc sửa lịch của tài khoản khác.

Các tiêu chí này mô tả hành vi của một story, còn DoD có phạm vi **chất lượng của Increment**.

### 9.3. Minh họa bằng Given–When–Then

~~~gherkin
Feature: Xác nhận lịch khám

  Scenario: Đặt thành công một khung giờ còn trống
    Given người bệnh có quyền sử dụng dịch vụ đặt lịch
    And khung giờ 09:00 của bác sĩ A đang còn nhận đặt
    When người bệnh xác nhận chọn khung giờ đó
    Then hệ thống ghi nhận đúng một lịch hẹn hợp lệ
    And người bệnh nhận được mã lịch, ngày, giờ và địa điểm chính xác

  Scenario: Hai yêu cầu cạnh tranh cùng một khung giờ
    Given một khung giờ chỉ còn một chỗ đặt hợp lệ
    When hai yêu cầu đặt lịch được gửi gần đồng thời
    Then hệ thống chỉ xác nhận số lịch không vượt quá chỗ còn lại
    And yêu cầu không thành công nhận thông báo và lựa chọn khác phù hợp

  Scenario: Lưu lịch thất bại
    Given hệ thống chưa ghi nhận được lịch một cách đáng tin cậy
    When người bệnh thực hiện yêu cầu xác nhận
    Then giao diện không thông báo rằng lịch đã được đặt thành công
    And người bệnh nhận hướng dẫn tiếp tục phù hợp
~~~

Given–When–Then giúp ba góc nhìn nghiệp vụ, phát triển và kiểm thử trao đổi ví dụ cụ thể; không bắt buộc dùng một framework tự động hóa duy nhất.

### 9.4. Kiểm tra theo DoD

| Hoạt động/điều kiện | Bằng chứng giả định | Đánh giá theo DoD |
|---|---|---|
| Luồng hiển thị và lưu lịch | Đã tích hợp với trạng thái thực và qua ví dụ thông thường. | Đạt phần yêu cầu chức năng. |
| Kiểm tra đồng thời | Hai yêu cầu có thể tạo hai lịch trùng. | **Chưa đạt** nếu DoD/ràng buộc nghiệp vụ yêu cầu bảo toàn số chỗ. |
| Kiểm tra phân quyền | Đã thử truy cập lịch không thuộc tài khoản và bị từ chối. | Đạt phần kiểm soát đã xác định. |
| Kiểm thử hồi quy liên quan | Bộ kiểm thử cốt lõi đạt, không phá việc tra cứu trước đó. | Đạt phần kiểm tra hồi quy. |
| Xử lý lỗi và ghi nhận sự kiện | Chưa xác định có thông báo sai khi lưu thất bại không. | **Chưa có bằng chứng đạt**. |
| Hướng dẫn vận hành cần thiết | Đã cập nhật cơ chế kiểm tra lịch và phát hiện lỗi. | Đạt nếu đáp ứng tiêu chuẩn tổ chức và team. |

Kết luận: PBI B **chưa Done**. Việc có một số ô đã đạt không bù trừ cho điều kiện bắt buộc còn thiếu. Team cần sửa lỗi cạnh tranh, xác minh hành vi khi lưu thất bại, rồi kiểm tra lại.

### 9.5. Điều chỉnh phạm vi mà không hạ tiêu chuẩn

Giả sử thời gian Sprint còn ít, nhóm có các lựa chọn:

- Tập trung hoàn thiện cơ chế tránh đặt trùng và đường đi thất bại để PBI B có cơ hội đạt DoD.
- Thương lượng với Product Owner giảm phạm vi nhóm dịch vụ hoặc phương thức đặt lịch, miễn phần còn lại tạo giá trị thực và đáp ứng chất lượng.
- Nếu không thể hoàn tất, phản ánh đúng PBI B chưa Done, đưa về Product Backlog để cân nhắc tiếp.

**Lựa chọn không phù hợp** là đánh dấu PBI B Done vì đã có màn hình demo và hứa “sửa lỗi đặt trùng sau khi release”. Đó là hạ chất lượng, làm sai bản chất Increment.

### 9.6. Kết quả sau khi đạt DoD

Khi luồng đặt lịch đã được xác minh và tích hợp đúng, Team có thể cung cấp Increment cho phạm vi thí điểm được phép. Sau đó có thể theo dõi:

- Tỷ lệ người bệnh hoàn tất đặt lịch hợp lệ.
- Thời gian đặt lịch và số lần phải thử lại.
- Số cuộc gọi hỏi giờ trống hoặc yêu cầu trợ giúp.
- Tỷ lệ lỗi đặt trùng, đặt sai giờ, lỗi quyền truy cập và sự cố vận hành.

Các chỉ số outcome **không tự động quyết định DoD**, nhưng giúp Product Owner và Scrum Team đánh giá việc đã chọn đúng vấn đề/giải pháp chưa. Một Increment kỹ thuật đạt chất lượng vẫn có thể cần thay đổi để tạo thêm giá trị cho người dùng.

## 10. Thiết lập DoD theo từng bước

Nhóm có thể dùng phương pháp sau để xây DoD có thể áp dụng, thay vì chép nguyên một checklist chung từ dự án khác.

### Bước 1 — Xác định tiêu chuẩn tổ chức phải tuân thủ

Tập hợp các tiêu chuẩn bắt buộc về bảo mật, dữ liệu, kiểm thử, thay đổi hệ thống, tuân thủ và vận hành. Nếu tổ chức đã có DoD tối thiểu, team không được xây một DoD lỏng hơn để né tiêu chuẩn đó.

### Bước 2 — Xác định sản phẩm và rủi ro đặc thù

Hỏi sản phẩm lưu những dữ liệu gì, ai sử dụng, thao tác nào không thể đảo ngược, hệ thống tích hợp nào quan trọng và lỗi có thể gây hậu quả gì. Với đặt lịch khám, tính toàn vẹn trạng thái lịch, quyền riêng tư và khả năng phát hiện lỗi có thể là mối quan tâm cốt lõi.

### Bước 3 — Diễn đạt tiêu chuẩn bằng điều kiện kiểm chứng

Tránh câu mơ hồ như “mọi kiểm thử đã tốt” nếu không biết thử cái gì và mức nào. Có thể làm rõ bộ kiểm thử bắt buộc, mức rủi ro, yêu cầu xác minh lỗi, tích hợp và bằng chứng chấp nhận được.

### Bước 4 — Thống nhất cách bảo đảm chất lượng trong luồng làm việc

Developers xác định cách đáp ứng DoD từ đầu, như kiểm thử tự động, tích hợp thường xuyên, rà soát thay đổi, kiểm tra quyền và chuẩn bị môi trường. Không chờ đến cuối Sprint mới phát hiện DoD yêu cầu một bước kiểm tra mất nhiều ngày.

### Bước 5 — Minh bạch tình trạng và bằng chứng

Mọi người cần phân biệt **đã làm**, **đang kiểm chứng**, **đã đạt DoD** và **chưa đạt DoD**. Công cụ bảng việc, pipeline và báo cáo kết quả hỗ trợ minh bạch nhưng không thay cho việc đánh giá.

### Bước 6 — Xem lại DoD khi học được điều mới

Qua Sprint Retrospective hoặc khi xuất hiện rủi ro mới, team có thể cải thiện DoD để tăng chất lượng phù hợp. Việc thay đổi tiêu chuẩn phải được trao đổi rõ và tuân thủ tiêu chuẩn tối thiểu của tổ chức, không sửa âm thầm để biến công việc đang lỗi thành Done.

### 10.1. Một DoD ngắn nhưng dùng được tốt hơn một bảng dài hình thức

Một checklist có 70 mục mà không ai hiểu hoặc có thể kiểm chứng có thể làm giảm minh bạch. Ngược lại, một DoD quá ngắn như “code merged và QA ok” có thể bỏ qua các điều kiện quan trọng.

Cần cân bằng độ rõ, rủi ro và khả năng áp dụng. **Mục tiêu là bảo đảm trạng thái thật của Increment**, không đạt một số lượng checkbox nào đó.

## 11. Một sản phẩm có nhiều Scrum Team: cần DoD chung

Khi nhiều Scrum Team cùng làm **một sản phẩm**, họ phải cùng xác định và tuân thủ **một DoD chung**. Nếu mỗi đội dùng một tiêu chuẩn “Done” không tương thích, tích hợp toàn sản phẩm sẽ trở thành giai đoạn chờ đợi và làm lại ở cuối.

Ví dụ ba đội cùng phát triển ứng dụng đặt lịch:

| Đội | Phạm vi công việc | Rủi ro nếu “Done” khác nhau |
|---|---|---|
| Đội giao diện | Luồng chọn dịch vụ, bác sĩ và giờ khám. | Giao diện báo thành công khi backend chưa ghi nhận. |
| Đội lịch hẹn | Quản lý trạng thái lịch và đồng bộ. | Không kiểm tra hai yêu cầu cạnh tranh hoặc tích hợp API cũ. |
| Đội thông báo | Email/SMS xác nhận và nhắc lịch. | Gửi thông báo trước khi giao dịch đã xác nhận đáng tin cậy. |

Nếu một đội chỉ cần code review để Done, đội khác đòi kiểm thử tích hợp còn đội thứ ba không có kiểm tra trạng thái, sản phẩm có thể trông “xanh” ở ba bảng khác nhau nhưng **không có một Increment dùng được chung**.

### 11.1. Các bước phối hợp

1. **Thống nhất DoD chung** có yêu cầu về tích hợp, chất lượng và trách nhiệm phát hiện lỗi xuyên đội.
2. **Làm rõ hợp đồng API và quy tắc trạng thái** cùng các nhóm tiêu thụ/cung cấp.
3. **Tích hợp thường xuyên** để các thay đổi không tạo ra một lô xung đột lớn.
4. **Kiểm tra luồng người dùng từ đầu đến cuối** ở những điểm có rủi ro đáng kể.
5. **Minh bạch PBI chưa đáp ứng DoD**, không chuyển lỗi tích hợp sang một đội “kiểm tra cuối” để giữ số liệu Done.
6. **Dùng phản hồi về Increment chung** để điều chỉnh backlog và phương thức phối hợp.

Nhiều đội có thể có kỹ thuật, công cụ hoặc checklist riêng bổ sung cho công việc chuyên môn, nhưng không được làm suy yếu **một chuẩn Done chung cho sản phẩm**.

### 11.2. Tích hợp muộn không phải “Increment ở Sprint cuối”

Nếu mỗi Sprint chỉ tạo một số component chưa hoạt động cùng nhau, rồi dành một Sprint cuối cho tích hợp toàn hệ thống, nhóm đang làm yếu đi nhịp nhận phản hồi sớm. Cần ưu tiên những lát giá trị xuyên qua các thành phần để tạo **Increment tích hợp và kiểm chứng được** mỗi Sprint.

Không phải mọi phụ thuộc đều dễ xóa; khi cần, nhóm có thể chuẩn bị contract tests, môi trường tích hợp và làm rõ dữ liệu sớm. Nhưng **bằng chứng từ mock hoặc kiểm thử từng thành phần không thay thế kiểm chứng của Increment tổng thể** khi tính năng cần tích hợp thật.

## 12. DoD và phát hành có kiểm soát: feature flag, CI/CD và thử nghiệm

Thực tế phát triển phần mềm thường dùng các kỹ thuật giúp tích hợp và phát hành an toàn:

- **Continuous Integration (CI):** hợp nhất thay đổi thường xuyên, chạy kiểm tra phù hợp và phát hiện sai lệch sớm.
- **Continuous Delivery/Deployment:** chuẩn bị hoặc tự động hóa quá trình đưa phần mềm tới môi trường sử dụng, theo khả năng và rủi ro.
- **Feature flag:** bật/tắt một khả năng cho đối tượng phù hợp mà không cần phụ thuộc tuyệt đối vào thời điểm hợp nhất mã.
- **Contract testing:** kiểm tra kỳ vọng giao tiếp giữa các hệ thống.
- **Automated regression testing:** phát hiện sớm hành vi cũ bị phá.
- **Monitoring/observability:** quan sát lỗi và hành vi quan trọng sau khi sử dụng.

Đây là **các thực hành hỗ trợ** chứ không phải yêu cầu bắt buộc có tên trong Scrum Guide. Một nhóm có thể sử dụng kỹ thuật XP, công cụ DevOps hoặc quản lý luồng kiểu Kanban để giúp mỗi Increment đạt DoD thường xuyên hơn.

### 12.1. Feature flag không biến mã chưa dùng được thành Increment

Nếu mã nằm sau một flag luôn tắt, chưa được tích hợp/kiểm chứng như một khả năng có thể dùng, nhóm không nên tự động gọi đó là Increment hoàn thành chỉ vì pipeline xanh.

Nếu khả năng đó đã hoàn chỉnh, tích hợp, đáp ứng DoD, có thể bật an toàn trong phạm vi đã xác định và thực sự dùng được khi cần, flag có thể hỗ trợ **tách thời điểm triển khai khỏi thời điểm mở rộng phát hành**. Điều quan trọng là đánh giá **trạng thái thực** chứ không chỉ trạng thái của công tắc.

Feature flag cũng tạo thêm trường hợp kiểm thử và công việc dọn dẹp khi hết cần thiết. Không nên kéo dài vô hạn những flag cũ làm hệ thống khó hiểu và khó bảo trì.

### 12.2. Tự động hóa không phải bằng chứng duy nhất

Pipeline xanh là tín hiệu hữu ích, nhưng nếu nó thiếu kiểm tra quyền, luồng lỗi hoặc dữ liệu không nhất quán, nó chưa đủ để bảo đảm DoD. Ngược lại, kiểm thử thủ công phù hợp có thể cần thiết cho tính khả dụng hoặc những hành vi hiếm khó tự động hóa.

Nhóm nên xác định **điều phải chứng minh** trước khi chọn công cụ chứng minh.

## 13. Đo lường mức độ sẵn sàng của Increment

Chỉ số không thay thế DoD, nhưng giúp Scrum Team nhận biết chất lượng và nút thắt trong quá trình tạo Increment.

| Nhóm tín hiệu | Ví dụ | Câu hỏi giúp trả lời |
|---|---|---|
| **Hoàn thành thực chất** | Số PBI đạt DoD; số Increment usable được tạo ra. | Có bước tiến sản phẩm thực hay chỉ có nhiều task đóng? |
| **Chất lượng** | Lỗi hồi quy, lỗi sau phát hành, kiểm tra bảo mật, sự cố dữ liệu. | Phần mềm có duy trì tiêu chuẩn chất lượng không? |
| **Dòng công việc** | WIP, cycle time, work item age, throughput. | Công việc có bị mở quá nhiều hoặc chờ kiểm tra quá lâu? |
| **Thời gian kiểm chứng** | Thời gian chờ môi trường, phản hồi CI, kiểm thử tích hợp. | Điều gì đang làm chậm việc chuyển từ mã sang Increment usable? |
| **Kết quả sản phẩm** | Tỷ lệ hoàn tất tác vụ, giảm hỗ trợ thủ công, phản hồi người dùng. | Increment đạt DoD có đang giúp đạt Product Goal không? |
| **Khả năng duy trì** | Chi phí làm lại, thời gian xử lý lỗi, thời gian phục hồi sự cố. | Chất lượng hiện tại có giúp các Sprint sau thích ứng không? |

### 13.1. Ví dụ số liệu và cách diễn giải

Giả sử một Scrum Team theo dõi ba Sprint minh họa:

| Chỉ số giả định | Sprint 1 | Sprint 2 | Sprint 3 |
|---|---:|---:|---:|
| PBI được chọn | 9 | 10 | 10 |
| PBI đạt DoD | 5 | 6 | 8 |
| PBI gần cuối Sprint mới bắt đầu kiểm thử | 5 | 4 | 2 |
| Lỗi tích hợp quan trọng phát hiện muộn | 4 | 3 | 1 |

Số liệu giả định gợi ý việc kiểm tra sớm hơn có thể giúp tăng khả năng hoàn thành thực chất. Tuy nhiên, **không thể kết luận quan hệ nhân quả** chỉ từ ba dòng dữ liệu: kích thước PBI, độ khó, thay đổi nhân sự và phạm vi kiểm tra có thể khác nhau.

Nhóm nên chọn một thay đổi thực hành cụ thể, chẳng hạn tích hợp API sớm hơn hoặc giới hạn WIP, rồi quan sát kết quả qua nhiều chu kỳ.

### 13.2. Đừng đo thành công bằng cách hạ DoD

Nếu hạng mục được đánh dấu Done nhiều hơn chỉ vì bỏ yêu cầu kiểm thử, chất lượng hoặc bảo mật, số liệu throughput có thể tăng nhưng giá trị bền vững giảm. Đây là ví dụ điển hình của việc **tối ưu chỉ số thay vì tối ưu sản phẩm**.

Scrum không bắt buộc dùng story point hay velocity. Velocity nếu được dùng chỉ có thể hỗ trợ dự báo trong bối cảnh riêng và **không phải thước đo chất lượng Increment hoặc giá trị người dùng**.

## 14. Những tình huống khó thường gặp

### Tình huống A — Đã xong code, chưa có môi trường tích hợp

**Vấn đề:** Hệ thống đối tác chưa cấp sandbox, nhưng phần ứng dụng đã viết xong dựa trên mock.

**Cách xử lý:** Minh bạch rằng tích hợp thật chưa được xác minh. Nếu DoD yêu cầu tích hợp với dịch vụ thực, hạng mục chưa Done. Team có thể chuẩn bị contract tests, môi trường thử, hoặc chia lại phạm vi thành một khả năng độc lập có thể sử dụng và đạt DoD. Không tuyên bố toàn bộ tính năng tích hợp đã hoàn thành chỉ dựa trên mock.

### Tình huống B — Còn lỗi “nhỏ” nhưng ảnh hưởng dữ liệu

**Vấn đề:** Đôi khi yêu cầu đặt lịch lặp tạo hai bản ghi. Tỷ lệ xuất hiện thấp nhưng tác động nghiệp vụ lớn.

**Cách xử lý:** Xem mức độ rủi ro và các tiêu chuẩn bắt buộc. Nếu lỗi vi phạm DoD, PBI không Done. Không dùng tần suất nhỏ làm lý do bỏ qua nguy cơ nghiêm trọng.

### Tình huống C — Product Owner muốn release trước vì hạn kinh doanh

**Vấn đề:** Sự kiện ra mắt đã công bố, Increment chưa đạt DoD.

**Cách xử lý:** Developers và Product Owner trao đổi lựa chọn giảm phạm vi, dùng phần đã Done và đủ an toàn, hoặc đổi kế hoạch phát hành. Scrum Master hỗ trợ minh bạch và phối hợp. Không hạ DoD chỉ để báo đúng hạn. Nếu có nghĩa vụ ngoài Scrum, giải quyết theo thẩm quyền và chính sách áp dụng, không che giấu rủi ro.

### Tình huống D — Story đạt tiêu chí chấp nhận nhưng chưa đạt DoD

**Vấn đề:** Người bệnh xem giờ trống đúng, nhưng chưa có kiểm tra phân quyền bắt buộc.

**Cách xử lý:** Story chưa Done. Nêu rõ thiếu điều kiện nào, ai cần phối hợp, kiểm chứng ra sao. Tiêu chí chấp nhận riêng không thay thế DoD chung.

### Tình huống E — Chức năng đạt DoD nhưng ít người dùng

**Vấn đề:** Increment đặt lịch qua ứng dụng chạy đúng và ổn định, nhưng người bệnh vẫn gọi tổng đài.

**Cách xử lý:** Không phải vì outcome chưa tăng mà tự động kết luận Increment không Done. Team cần kiểm tra khả dụng, nhận thức của người dùng, kênh truyền thông và giả thuyết giá trị; Product Owner điều chỉnh Product Backlog theo bằng chứng.

### Tình huống F — Hai Scrum Team có hai chuẩn Done

**Vấn đề:** Đội backend cho rằng API Done khi unit test đạt; đội frontend chỉ xem Done khi luồng người dùng chạy tích hợp.

**Cách xử lý:** Với một sản phẩm chung, các Scrum Team phải cùng xác định và tuân theo một DoD chung. Những kiểm tra kỹ thuật chuyên biệt có thể bổ sung nhưng không được mâu thuẫn với tiêu chuẩn chất lượng chung của Increment.

### Tình huống G — Increment đã Done nhưng chưa được phát hành

**Vấn đề:** Luồng đặt lịch đạt DoD nhưng chỉ được mở trong đợt thí điểm sau hai tuần.

**Cách xử lý:** Phân biệt **trạng thái Increment** với **quyết định phát hành**. Nếu Increment thực sự usable, tích hợp và đạt DoD, việc chưa mở rộng cho mọi người không tự động biến nó thành chưa Done. Điều kiện phát hành và theo dõi rủi ro vẫn phải được thực hiện.

## 15. Những phản mẫu cần tránh

| Phản mẫu | Vì sao có hại? | Thực hành thay thế |
|---|---|---|
| “Done là developer đã merge code.” | Không bảo đảm hành vi, tích hợp hoặc chất lượng. | Dựa trên DoD của Increment và bằng chứng xác minh. |
| “QA sẽ kiểm tra hết vào Sprint sau.” | Đẩy việc kiểm chứng ra khỏi Increment hiện tại. | Tích hợp và kiểm tra ngay trong quá trình tạo Increment. |
| “Còn bug nghiêm trọng nhưng cứ đóng story.” | Trạng thái Done trở nên sai lệch. | Ghi chưa Done, ưu tiên xử lý theo rủi ro và DoD. |
| “Mọi chuyện phải chờ Sprint Review mới release.” | Phản hồi đến muộn, nhầm Review với phê duyệt. | Bàn giao Increment đủ điều kiện khi phù hợp, vẫn dùng Review để inspect/adapt. |
| “DoD là checklist cố định cho mọi sản phẩm.” | Có thể thiếu kiểm soát quan trọng hoặc áp dụng máy móc. | Dựa trên sản phẩm, rủi ro và tiêu chuẩn tổ chức. |
| “DoD có thể thay đổi lúc nào cũng được để dễ Done.” | Phá vỡ cam kết chất lượng và minh bạch. | Cải tiến tiêu chuẩn có chủ đích, không hạ tùy tiện. |
| “Acceptance criteria đạt nên chắc chắn Done.” | Bỏ qua tiêu chuẩn chất lượng chung. | Cần cả tiêu chí riêng và DoD áp dụng. |
| “Mock pass tức là tích hợp thật đã Done.” | Kỳ vọng giả tạo về dịch vụ hoặc dữ liệu. | Kiểm tra hợp đồng/tích hợp thật theo mức yêu cầu. |
| “Một Increment là một tính năng hoàn chỉnh cỡ lớn.” | Làm chậm phản hồi và dồn rủi ro. | Tạo các bước tiến nhỏ, tích hợp và usable. |
| “Mỗi team có DoD riêng dù cùng làm một sản phẩm.” | Không có chuẩn chất lượng chung cho Increment. | Cùng xác định và tuân theo một DoD. |
| “Mọi PBI phải là user story.” | Ép việc sửa lỗi, bảo mật hoặc nghiên cứu vào mẫu giả. | Dùng định dạng phù hợp, vẫn liên kết mục tiêu sản phẩm. |
| “Số story Done là giá trị tạo ra.” | Lẫn output với outcome và chất lượng. | Kết hợp Increment usable, phản hồi, outcome và guardrail. |
| “DoD là trách nhiệm riêng của tester hoặc Scrum Master.” | Nhóm đổ trách nhiệm chất lượng cho một người. | Developers tuân thủ DoD; Scrum Team cùng chịu trách nhiệm Increment giá trị. |

## 16. Bài thực hành: xác định Increment và DoD cho một Sprint

Một nhóm đang phát triển dịch vụ đặt lịch cho lớp học trực tuyến. Mục tiêu Sprint: **“Học viên có thể đăng ký một buổi học còn chỗ và nhận xác nhận hợp lệ.”**

Các hạng mục được đề xuất:

| Mã | Hạng mục | Tình trạng hiện tại giả định |
|---|---|---|
| A | Hiển thị danh sách buổi còn chỗ. | Đã tích hợp, kiểm tra quyền và lỗi tải dữ liệu; đạt DoD. |
| B | Đăng ký chỗ cho một buổi. | Luồng thường chạy được nhưng khi hai học viên chọn cùng chỗ, số đăng ký vượt sức chứa. |
| C | Gửi email xác nhận. | Email thử nghiệm gửi được; chưa kiểm tra tình huống yêu cầu đăng ký thất bại. |
| D | Cải thiện truy vấn danh sách buổi học. | Đã đo và tối ưu, kiểm thử hồi quy và tích hợp đạt các chuẩn áp dụng. |

**Bài tập 1:** Hạng mục nào có thể được xem là Done? Vì sao?

**Hướng phân tích:** A và D có thể đã Done nếu thực sự đáp ứng toàn bộ DoD áp dụng, chứ không chỉ các thông tin ngắn trong bảng. B chưa Done do vi phạm quy tắc sức chứa. C chưa thể được coi Done nếu còn có thể gửi xác nhận khi đăng ký thất bại và điều đó vi phạm hành vi hoặc tiêu chuẩn chất lượng.

**Bài tập 2:** Có thể tạo Increment nào trước khi B đạt Done?

**Hướng phân tích:** A có thể tạo bước tiến dùng được cho việc tra cứu buổi còn chỗ. D cũng có thể góp phần vào Increment tăng độ tin cậy/hiệu năng của khả năng đã có nếu kiểm chứng phù hợp. Tuy nhiên, team **không được tuyên bố mục tiêu “đăng ký thành công” đã đạt** khi phần đăng ký thực còn lỗi nghiêm trọng.

**Bài tập 3:** Đến cuối Sprint B vẫn chưa Done, nên làm gì?

**Hướng phân tích:** Minh bạch kết quả, không trình bày B như Increment hoàn thành; đưa B trở lại Product Backlog để xem xét tiếp, đồng thời xem vì sao kiểm tra đồng thời được phát hiện muộn. Sprint Review vẫn có thể trao đổi về Increment thực và thông tin mới; Retrospective có thể thử cải tiến cách kiểm tra rủi ro từ sớm.

**Bài tập 4:** Cần thay đổi DoD không?

**Hướng phân tích:** Nếu lỗi vượt sức chứa vốn đã vi phạm tiêu chí và chất lượng bắt buộc, cần **thực hiện DoD hiện có**, không hạ chuẩn. Nếu lần này cho thấy DoD chưa đủ rõ về tính nhất quán dữ liệu, team có thể chủ động làm rõ hoặc nâng tiêu chuẩn cho các Sprint sau, tuân thủ yêu cầu tổ chức.

## 17. Checklist cho Scrum Team

Trước khi tuyên bố một hạng mục Done, nhóm có thể tự hỏi:

- [ ] Hạng mục có đóng góp vào Product Goal hoặc một nhu cầu cải thiện sản phẩm đã được ưu tiên không?
- [ ] Các tiêu chí chấp nhận và quy tắc nghiệp vụ liên quan đã được xác minh chưa?
- [ ] Phần mới đã **tích hợp** và chạy cùng những Increment trước chưa?
- [ ] Những yêu cầu **DoD chung** đang áp dụng cho sản phẩm đã được đáp ứng đầy đủ chưa?
- [ ] Các tiêu chuẩn tối thiểu của tổ chức, bảo mật và tuân thủ đã được giữ nguyên chưa?
- [ ] Kiểm thử, đánh giá rủi ro và bằng chứng chất lượng cần thiết đã sẵn sàng chưa?
- [ ] Các trường hợp lỗi, dữ liệu thiếu, yêu cầu đồng thời hoặc quyền truy cập quan trọng đã được xử lý phù hợp chưa?
- [ ] Increment có thực sự **usable** trong phạm vi dự kiến hay chỉ chạy trên một bản demo giả lập?
- [ ] Nếu có nhiều Scrum Team, mọi đội có cùng hiểu và tuân theo **một DoD chung** không?
- [ ] Có điều kiện phát hành riêng nào cần quản lý mà không làm sai trạng thái Done không?
- [ ] Hạng mục chưa đạt DoD có được ghi đúng trạng thái và đưa về Product Backlog để xem xét không?
- [ ] Team có khả năng lấy phản hồi về giá trị sản phẩm sau khi có Increment không?
- [ ] Thời gian chờ tích hợp, kiểm thử và số việc dở dang có được theo dõi để cải tiến không?

Checklist này là **công cụ hỗ trợ minh bạch**, không phải thủ tục phê duyệt bắt buộc của Scrum. Cách sử dụng cụ thể có thể khác nhau, nhưng trạng thái Done phải phản ánh **đúng chất lượng thực của Increment**.

## 18. Kết luận

**Increment** là bước tiến cụ thể của sản phẩm hướng tới Product Goal, **cộng thêm vào những Increment trước, được xác minh để hoạt động cùng nhau và phải dùng được**. **Definition of Done** là commitment của Increment, mô tả trạng thái chất lượng cần đạt trước khi một Product Backlog Item được coi là hoàn thành.

Nhờ DoD, các thành viên Scrum Team và stakeholder có một ngôn ngữ chung về chữ **“Done”**. Developers phải tuân thủ tiêu chuẩn này khi tạo Increment; Scrum Team cùng chịu trách nhiệm tạo giá trị mỗi Sprint. Tiêu chí chấp nhận, các công cụ kiểm thử, điều kiện phát hành và outcome người dùng đóng vai trò quan trọng nhưng **không thay thế nhau**.

Một Sprint có thể tạo nhiều Increment, có thể bàn giao trước Sprint Review, và cũng có thể kết thúc với một số PBI chưa Done. Sự minh bạch về phần hoàn thành lẫn phần còn thiếu giúp nhóm kiểm tra, thích ứng và cải tiến thay vì đánh đổi chất lượng để báo cáo tiến độ đẹp.

Trong Agile Development, điều quan trọng không phải **bao nhiêu tác vụ đã được đóng**, mà là **mỗi Increment có thể được sử dụng với mức chất lượng đáng tin cậy và góp phần tạo giá trị thực qua phản hồi liên tục**.
