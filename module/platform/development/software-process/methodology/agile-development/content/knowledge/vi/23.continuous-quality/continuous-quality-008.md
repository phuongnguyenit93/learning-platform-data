# Duy trì tiêu chí hoàn tất khi thời hạn gây áp lực

## 1. Một Sprint sắp hết hạn: “gần xong” có thật sự là xong?

Nhóm phát triển nền tảng học trực tuyến chuẩn bị mở đăng ký cho một chương trình học miễn phí. Sprint chỉ còn hai ngày làm việc, trong khi nhóm đã hoàn thành phần lớn giao diện và API. Người phụ trách chiến dịch đề nghị:

> “Ngày khai giảng đã ấn định. Cứ đánh dấu Done và phát hành trước; kiểm thử lỗi đăng ký trùng và kiểm tra phân quyền sẽ làm trong Sprint sau.”

Đề nghị này nghe có vẻ thực dụng, nhưng có thể tạo ra hậu quả trực tiếp: một người học đăng ký hai lần, tài khoản A xem dữ liệu của tài khoản B hoặc giao diện báo thành công dù dịch vụ chưa lưu được. Nếu phần mềm có rủi ro như vậy, việc đổi nhãn từ “đang kiểm thử” sang “Done” **không biến nó thành sản phẩm hoàn tất**.

Trong Scrum, **Definition of Done (DoD)** là mô tả chính thức về trạng thái của **Increment** khi đáp ứng những thước đo chất lượng cần thiết của sản phẩm. DoD là **commitment của Increment**, giúp mọi người hiểu thống nhất thế nào là công việc hoàn tất. Nếu một Product Backlog Item (PBI) chưa đạt DoD thì nó **không được coi là một phần của Increment**.

Áp lực thời hạn đặt ra câu hỏi quan trọng hơn “làm sao đóng hết ticket?”:

> **Phần giá trị nào có thể hoàn tất thật, đủ an toàn và đạt tiêu chí chất lượng trước thời hạn? Nếu không thể, nhóm cần nói rõ điều gì và quyết định lại điều gì?**

Chủ đề thuộc chương **Chất lượng liên tục** của module **AGILE_DEVELOPMENT**. Tư duy Agile không phải chấp nhận thay đổi bằng cách hạ chất lượng, mà là giao kết quả tăng dần, nhận phản hồi sớm, thích ứng kế hoạch và cải tiến dòng công việc. User story, backlog, Scrum, Kanban và các thực hành XP có thể cùng hỗ trợ việc này.

## 2. Phân biệt những khái niệm thường bị trộn lẫn

Khi thời hạn đến gần, tranh luận thường trở nên rối vì “hoàn tất”, “chấp nhận”, “phát hành” và “đạt mục tiêu” bị dùng thay cho nhau.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ về đăng ký khóa học |
| --- | --- | --- |
| **Acceptance criteria** | Một PBI phải thể hiện hành vi cụ thể nào? | Gửi lại yêu cầu không tạo đăng ký đang có hiệu lực trùng |
| **Definition of Done (DoD)** | Những điều kiện chất lượng cần thiết nào phải đạt để công việc là một phần Increment? | Kiểm thử cần thiết đạt, tích hợp đúng, kiểm tra quyền truy cập phù hợp |
| **Sprint Goal** | Vì sao Sprint này có giá trị, toàn nhóm cùng hướng tới kết quả gì? | Người học đăng ký được khóa miễn phí và biết rõ kết quả |
| **Sprint Backlog** | Developers dự định làm gì và làm thế nào để hướng tới Sprint Goal? | Các PBI được chọn và kế hoạch giao Increment |
| **Release criteria / điều kiện phát hành** | Cần thêm điều kiện gì trước khi cho người dùng sử dụng trong bối cảnh thực? | Phê duyệt vận hành, mốc chiến dịch, yêu cầu hợp đồng nếu áp dụng |
| **Deadline / thời hạn** | Thời điểm nào phải có quyết định hoặc kết quả? | Ngày chương trình mở nhận đăng ký |
| **Definition of Ready (DoR)** | Nhóm có thỏa thuận nào để xem một PBI đủ rõ cho bước tiếp theo? | Quy tắc đăng ký và câu hỏi nghiệp vụ đã được làm rõ |

**DoR không phải thành phần bắt buộc của Scrum Guide**, còn **DoD là commitment chính thức của Increment**. Acceptance criteria thường do các bên liên quan làm rõ cho từng PBI, nhưng không thay thế DoD. Release criteria tùy sản phẩm và tổ chức, không mặc định đồng nhất với DoD.

### 2.1. Một PBI đạt acceptance criteria nhưng chưa đạt DoD

Chức năng hiển thị thông báo “Đã đăng ký” có vẻ đúng ở trường hợp thông thường. Tuy nhiên, kiểm thử tích hợp khi dịch vụ lưu dữ liệu lỗi chưa được chạy. Nó có thể đã thỏa một số ví dụ chấp nhận, nhưng **chưa được coi là Done** nếu kiểm thử đó thuộc tiêu chuẩn chất lượng áp dụng.

### 2.2. Một PBI Done chưa có nghĩa Sprint Goal đã đạt

Nhóm có thể hoàn thành ba PBI liên quan đến giao diện, cấu hình và ghi log nhưng luồng đăng ký xuyên hệ thống chưa hoạt động. **Số PBI Done không tự chứng minh Sprint Goal đã đạt**, vì mục tiêu là kết quả chung có giá trị.

### 2.3. Done không đồng nghĩa đã phát hành công khai

Một Increment đáp ứng DoD là **có thể sử dụng được** theo nghĩa chất lượng sản phẩm. Nhóm có thể phát hành khi phù hợp, kể cả trước Sprint Review; Sprint Review không phải cổng bắt buộc để phát hành. Nhưng tổ chức có thể yêu cầu kiểm soát vận hành, phê duyệt hoặc điều kiện triển khai riêng. Vì vậy:

- **Không đạt DoD:** Không gọi là Increment hoàn tất và không phát hành như chức năng đã Done.
- **Đạt DoD:** Có thể là phần Increment hoàn tất, nhưng việc đưa tới người dùng còn phụ thuộc quyết định và chính sách phát hành áp dụng.

## 3. Vì sao DoD quan trọng hơn khi áp lực tăng?

DoD có thể được xem là **ranh giới bảo vệ độ tin cậy của kết quả**. Nó giúp nhóm tránh một hiện tượng phổ biến: mỗi người dùng từ “Done” theo một nghĩa khác nhau.

| Khi thiếu chuẩn hoàn tất chung | Khi DoD rõ và được tôn trọng |
| --- | --- |
| “Developer đã code xong” được hiểu là tính năng đã hoàn tất | Mọi người biết phần nào đã được kiểm chứng và tích hợp |
| Kiểm thử, bảo mật hoặc vận hành bị đẩy sang cuối | Các hoạt động cần thiết được tính trong công việc tới Done |
| Tiến độ báo cáo lạc quan nhưng tồn nhiều việc dở | Sprint Backlog minh bạch phần Done và phần còn rủi ro |
| Các lỗi xuất hiện khi mở cho người dùng | Nhiều rủi ro được phát hiện sớm trong phát triển |
| Sprint sau phải trả chi phí sửa việc Sprint trước | Dòng giao phần tăng dần bền vững hơn |
| Có tranh cãi “ai đã hứa xong?” | Trạng thái hoàn tất dựa trên bằng chứng và tiêu chuẩn chung |

Không có DoD nào bảo đảm phần mềm tuyệt đối không còn lỗi; điều đó không thực tế. DoD là **ngưỡng chất lượng được xác lập cho sản phẩm**, có thể tiến hóa khi nhóm học được rủi ro mới hoặc nâng tiêu chuẩn. Nhưng nó phải được dùng **thành thật và nhất quán**, không trở thành tùy chọn bị xóa đi vào ngày cuối.

### 3.1. Chuyển rủi ro sang tương lai không phải tự động tiết kiệm thời gian

Giả sử nhóm bỏ kiểm thử quyền truy cập để tiết kiệm một buổi. Sau phát hành, một lỗi phân quyền xuất hiện. Nhóm có thể phải:

1. Ứng cứu sự cố và ngăn tác động tiếp diễn.
2. Điều tra dữ liệu và mức ảnh hưởng.
3. Sửa mã, kiểm thử lại, triển khai bản khắc phục.
4. Trao đổi với người dùng hoặc bên có thẩm quyền khi cần.
5. Tạm dừng công việc giá trị khác và khôi phục niềm tin.

**Không thể khẳng định mọi kiểm thử đều tránh được mọi lỗi**, nhưng các kiểm tra quan trọng giúp giảm khả năng để rủi ro đã biết lọt qua. Một quyết định “nhanh hôm nay” có thể làm thời gian giao giá trị những tuần sau dài hơn.

### 3.2. DoD không phải lý do để làm mọi thứ thật cầu kỳ

Ngược lại, DoD cũng không nên trở thành danh sách vô hạn các hoạt động không phù hợp. Nhóm cần dựa trên **rủi ro và tiêu chuẩn cần thiết cho sản phẩm**. Nếu tổ chức có tiêu chuẩn DoD áp dụng, Scrum Team phải tuân thủ tối thiểu tiêu chuẩn đó. Khi chưa có tiêu chuẩn tổ chức, Scrum Team tạo DoD phù hợp. Nhiều Scrum Team làm chung một sản phẩm cần thống nhất và tuân thủ **một DoD chung**.

Việc định nghĩa DoD tốt cần đủ cụ thể để kiểm chứng, nhưng không buộc một cách triển khai duy nhất cho mọi thay đổi. Ví dụ “các kiểm tra bảo mật áp dụng đã đạt” có thể phù hợp hơn quy tắc “mọi thay đổi đều phải chạy một phép thử nặng như nhau”, miễn các nghĩa vụ bắt buộc được giữ.

## 4. Scrum quy định gì khi Sprint gặp áp lực thời hạn?

Trong Sprint, Scrum nêu những giới hạn quan trọng:

- **Không thực hiện thay đổi gây nguy hiểm cho Sprint Goal.**
- **Chất lượng không được giảm.**
- **Product Backlog được làm rõ thêm** khi cần.
- **Phạm vi có thể được làm rõ và thương lượng lại với Product Owner** khi nhóm học được thông tin mới.

Đây không phải yêu cầu “khóa toàn bộ PBI đã chọn”. Scrum Team cùng hướng tới Sprint Goal; Developers điều chỉnh kế hoạch thực hiện và trao đổi với Product Owner về phạm vi. Điều cần tránh là **thay chất lượng bằng tiến độ đẹp trên giấy**.

### 4.1. Ba commitments của Scrum

| Artifact | Commitment | Vai trò khi có áp lực |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Giữ hướng dài hạn cho quyết định ưu tiên |
| **Sprint Backlog** | **Sprint Goal** | Giữ mục tiêu duy nhất để biết điều gì nên làm trước |
| **Increment** | **Definition of Done** | Giữ ngưỡng chất lượng của phần kết quả thật sự hoàn tất |

Một Sprint Backlog có thể thay đổi **How**, sắp xếp lại công việc và làm rõ **What**. Nhưng điều chỉnh không có nghĩa bỏ yêu cầu chất lượng để giữ một danh sách nhiệm vụ đã chọn.

### 4.2. Nếu PBI chưa đạt DoD khi Sprint kết thúc

Theo Scrum Guide, nếu PBI chưa đáp ứng DoD, nó **không thể được phát hành hoặc trình bày như một phần Increment tại Sprint Review**; công việc được trả về Product Backlog để cân nhắc tiếp. Trạng thái cần được trình bày trung thực.

Nhóm có thể trao đổi về công việc chưa hoàn tất, rủi ro hoặc những gì đã học trong Sprint Review. Điều bị cấm về mặt ý nghĩa là **đại diện phần chưa Done như Increment hoàn tất**.

Không nên tự động chuyển nguyên PBI chưa Done sang Sprint sau như một lời hứa bất biến. Product Owner tiếp tục quản lý Product Backlog; ở Sprint Planning tiếp theo Developers lựa chọn công việc qua trao đổi và dự báo năng lực thực tế.

### 4.3. Nếu Sprint Goal thật sự lỗi thời

Nếu Sprint Goal trở nên **không còn giá trị**, Scrum cho phép hủy Sprint và **chỉ Product Owner** có thẩm quyền quyết định việc hủy. Việc PBI bị chậm hoặc ước lượng sai không tự làm Sprint Goal lỗi thời; thông thường nhóm cần kiểm tra, thích ứng và trao đổi phạm vi trước.

### 4.4. Việc phát triển sản phẩm luôn có ràng buộc thực tế

Scrum không xóa các quy định về bảo mật, pháp lý, hợp đồng, vận hành hoặc an toàn. Nếu một thời hạn liên quan nghĩa vụ bắt buộc, nhóm phải đưa vấn đề tới người có thẩm quyền phù hợp thay vì tự diễn giải rằng “Agile cho phép linh hoạt”.

## 5. Đánh đổi đúng: phạm vi, thời gian, năng lực và rủi ro

Khi có deadline, nhóm thường đối diện bốn biến:

1. **Phạm vi:** Có thể giao bao nhiêu hành vi có giá trị?
2. **Thời gian:** Khi nào cần Increment hoặc quyết định phát hành?
3. **Năng lực:** Những chuyên môn, môi trường và quyền truy cập nào khả dụng?
4. **Chất lượng và rủi ro:** Những điều kiện nào không được bỏ qua?

Điều cần nhớ là **chất lượng cần thiết không nên trở thành biến cắt giảm tùy tiện**. Thay vào đó, nhóm có thể chọn **phạm vi nhỏ hơn nhưng hoàn tất thật**, làm rõ thứ tự ưu tiên, giảm WIP và chuyển nguồn lực hợp lý.

| Lựa chọn | Có thể làm gì? | Điều kiện cần giữ |
| --- | --- | --- |
| **Giảm phạm vi tính năng** | Hoãn email phụ, dashboard hoặc bộ lọc nâng cao | Phần còn lại vẫn tạo kết quả có nghĩa, không bỏ điều kiện bắt buộc |
| **Chia PBI theo lát cắt dọc** | Giao một luồng người dùng hoạt động từ UI tới dữ liệu | Mỗi phần được gọi Done phải tự đáp ứng DoD |
| **Thay thứ tự công việc** | Ưu tiên kiểm thử tích hợp và review của phần gần Done | Không làm nguy hiểm Sprint Goal |
| **Điều chỉnh cách phối hợp** | Pair, hỗ trợ gỡ nghẽn, chuyển năng lực khỏi việc chưa thiết yếu | Tôn trọng kỹ năng, quyền truy cập và nhịp làm bền vững |
| **Giảm WIP** | Ngừng mở việc mới, tập trung hoàn tất | Không giấu item đang làm hoặc làm đẹp chỉ số |
| **Thương lượng mốc/phạm vi với bên liên quan** | Minh bạch kết quả khả thi và phương án thay thế | Đúng thẩm quyền, không che rủi ro |
| **Không phát hành phần chưa đủ chất lượng** | Giữ sản phẩm an toàn, chọn phương án vận hành khác | Tuyên bố chính xác điều đạt và chưa đạt |

**Làm thêm giờ** có thể xảy ra trong tình huống đặc biệt theo quy định và lựa chọn có thẩm quyền, nhưng không phải chiến lược mặc định để vá kế hoạch quá tải. Kéo dài làm việc liên tục có thể tăng lỗi, giảm khả năng suy nghĩ và làm nhịp giao hàng kém bền vững.

### 5.1. “Cắt scope” khác “cắt DoD”

Giả sử PBI ban đầu gồm: đăng ký khóa, hiển thị xác nhận trong ứng dụng, gửi email thông báo và tạo thống kê chiến dịch.

- **Cắt phạm vi hợp lệ:** Nếu email và thống kê không thiết yếu cho Sprint Goal hoặc nghĩa vụ đã được thống nhất, trao đổi với Product Owner để ưu tiên luồng đăng ký và xác nhận trong ứng dụng trước.
- **Cắt chất lượng không hợp lệ:** Bỏ kiểm tra phân quyền, bỏ kiểm thử chống đăng ký trùng hoặc cho giao diện báo thành công giả để giảm thời gian.

Phạm vi có thể nhỏ đi **theo giá trị**; DoD vẫn áp dụng **cho phần được gọi là hoàn tất**.

### 5.2. “Cắt test” có phải luôn là cắt DoD?

Không nên suy đơn giản rằng mọi bài test từng tồn tại đều là điều kiện bất biến, cũng không nên lặng lẽ bỏ test vì áp lực. Cần phân biệt:

- Test bắt buộc theo DoD, nghĩa vụ an toàn hoặc chất lượng: **không được bỏ để gọi Done**.
- Test trùng lặp, lỗi thời hoặc không còn kiểm chứng rủi ro nào: có thể được **cải tiến có chủ đích**, với bằng chứng và thống nhất thích hợp.
- Test chưa phù hợp hoặc flaky: phải xử lý để **duy trì độ tin cậy của bằng chứng**; việc rerun cho xanh hoặc cách ly vô thời hạn không giải quyết rủi ro.

Nâng hiệu quả kiểm tra là cải tiến kỹ thuật; **che giấu lỗ hổng kiểm chứng** là giảm chất lượng.

## 6. Một cây quyết định khi thời hạn sắp tới

Nhóm có thể dùng luồng suy nghĩ sau để tránh quyết định bốc đồng:

~~~mermaid
flowchart TD
    A["Còn ít thời gian trước mốc cần giao"] --> B["Kiểm tra Sprint Goal, phần Done và rủi ro"]
    B --> C{"Phần giá trị cốt lõi đã đạt DoD?"}
    C -->|"Có"| D["Đánh giá điều kiện phát hành và phạm vi dùng được"]
    C -->|"Chưa"| E["Xác định điều kiện DoD và hành vi còn thiếu"]
    E --> F{"Có thể hoàn tất lát cắt có giá trị trong năng lực còn lại?"}
    F -->|"Có"| G["Giảm WIP, tập trung làm và kiểm chứng phần đó"]
    F -->|"Không"| H["Trao đổi PO và bên có thẩm quyền về phạm vi/mốc"]
    G --> I{"Đã đạt DoD thực tế?"}
    I -->|"Có"| D
    I -->|"Chưa"| H
    H --> J["Minh bạch phần không Done; chọn phương án tiếp theo"]
    D --> K{"Đạt điều kiện phát hành áp dụng?"}
    K -->|"Có"| L["Phát hành có kiểm soát khi phù hợp"]
    K -->|"Chưa"| M["Giữ Increment Done và xử lý cổng phát hành"]
~~~

Sơ đồ không thay thế đánh giá chuyên môn. Với sự cố an toàn hoặc nghĩa vụ pháp lý nghiêm trọng, cần áp dụng quy trình có thẩm quyền ngay cả khi luồng quyết định thông thường chưa hoàn tất.

### 6.1. Hỏi theo bằng chứng, không theo cảm giác

Tránh câu “chỉ còn vài lỗi nhỏ”. Thay bằng:

> “Luồng đăng ký hiện đã lưu dữ liệu ở trường hợp cơ bản. Kiểm thử hai yêu cầu gửi đồng thời vẫn thất bại: có thể tạo hai bản ghi đang có hiệu lực. Đây là điều kiện chưa đạt để phần đăng ký được coi là Done. Nhóm đang đánh giá sửa lỗi và kiểm chứng trước mốc phát hành.”

Mô tả được hành vi, kiểm tra và ảnh hưởng sẽ hỗ trợ quyết định tốt hơn ước lượng chủ quan như “90% xong”.

## 7. Thiết kế Definition of Done đủ rõ trước khi chịu áp lực

DoD cần được hiểu **từ đầu công việc**, không chỉ được mở ra để xem vào cuối Sprint. Một DoD hữu ích là tiêu chuẩn chất lượng có thể kiểm chứng, áp dụng cho Increment của sản phẩm.

### 7.1. Một DoD minh họa cho nền tảng học trực tuyến

| Nhóm chất lượng | Ví dụ điều kiện cần đạt khi áp dụng | Loại bằng chứng |
| --- | --- | --- |
| **Đúng nghiệp vụ** | Các hành vi quan trọng và trường hợp lỗi đã thống nhất được kiểm chứng | Acceptance tests, review ví dụ nghiệp vụ |
| **Mã và cấu trúc** | Thay đổi được review theo chính sách, không đưa lỗi cấu trúc nghiêm trọng đã biết | Pull request, kiểm tra liên quan |
| **Tích hợp** | Giao diện, API, dữ liệu và các dịch vụ liên quan hoạt động cùng nhau | Integration/contract tests |
| **Hồi quy** | Những luồng cốt lõi không bị phá vỡ theo phạm vi rủi ro | Tập kiểm thử phù hợp |
| **Bảo mật và phân quyền** | Kiểm tra quyền truy cập và các yêu cầu an toàn áp dụng đã đạt | Security review, test phân quyền |
| **Dữ liệu** | Thay đổi schema/migration an toàn theo yêu cầu, không làm sai dữ liệu hiện có | Migration test, kiểm tra tính nhất quán |
| **Khả năng truy cập** | Giao diện đáp ứng yêu cầu accessibility áp dụng | Kiểm tra kỹ thuật và sử dụng |
| **Vận hành** | Có bằng chứng đủ để cấu hình, giám sát và xử lý lỗi theo chuẩn | Smoke test, logs/metrics, hướng dẫn cần thiết |
| **Minh bạch** | Trạng thái và các vấn đề còn lại không bị che giấu | Kết quả pipeline, review, ghi chú rủi ro |

Đây là **bảng ví dụ** để tham khảo, không phải danh sách Scrum bắt buộc cho mọi sản phẩm hoặc từng thay đổi. DoD thực tế phải dựa vào chất lượng cần thiết và tiêu chuẩn tổ chức, không mặc định tất cả dòng trong bảng cần cùng một dạng kiểm tra cho mọi PBI.

### 7.2. “Kiểm thử đã chạy” cần chính xác tới mức nào?

Một tiêu chí mơ hồ như “đã test” dễ bị diễn giải thành “tôi đã bấm thử một lần”. Có thể làm rõ:

- Loại kiểm tra bắt buộc theo rủi ro của hạng mục.
- Môi trường và dữ liệu có tính đại diện phù hợp.
- Cách ghi nhận kết quả và xử lý khi kiểm tra thất bại.
- Trách nhiệm review và xác minh.
- Điều kiện ứng xử khi chưa có môi trường hoặc có test flaky.

Không nhất thiết liệt kê từng câu lệnh công cụ trong DoD. Nhóm có thể lưu chi tiết thực thi tại pipeline hoặc hướng dẫn kỹ thuật, nhưng **nghĩa của tiêu chí cần nhất quán**.

### 7.3. DoD có được thay đổi không?

DoD có thể **được cải tiến** khi nhóm học thêm về rủi ro, công nghệ và chất lượng mong đợi. Ví dụ, sau một sự cố đăng ký trùng, nhóm bổ sung kiểm tra tính đồng thời vào tiêu chuẩn liên quan.

Điều khác hoàn toàn với việc tự ý **hạ chuẩn ngay khi trễ hạn**. Trong Sprint, chất lượng không được giảm. Nếu có đề xuất thay đổi DoD, cần minh bạch lý do, điều kiện tổ chức và tác động; việc sửa mô tả không làm một vấn đề chưa giải quyết biến mất.

## 8. Cắt theo lát cắt dọc để giao ít hơn nhưng hoàn tất thật

Một lỗi lập kế hoạch thường gặp là chia công việc theo thành phần kỹ thuật:

~~~text
PBI 1: Xây toàn bộ giao diện đăng ký.
PBI 2: Xây toàn bộ API đăng ký.
PBI 3: Xây schema và migration.
PBI 4: Cuối Sprint mới kiểm thử xuyên hệ thống.
~~~

Nhìn vào bảng, ba PBI đầu có thể báo “xong” trong khi người học **vẫn chưa đăng ký được**. Cách chia này làm tăng rủi ro tích hợp và dễ đẩy kiểm thử sang cuối kỳ.

Thử chia theo **lát cắt dọc có hành vi người dùng**:

~~~text
Lát cắt A: Người học đã đăng nhập đăng ký một khóa miễn phí
            và thấy trạng thái xác nhận đúng.
Lát cắt B: Người học xem được khóa vừa đăng ký trong danh sách.
Lát cắt C: Người học xử lý trạng thái lỗi hoặc đăng ký lặp rõ ràng.
Lát cắt D: Người học nhận email hoặc thống kê bổ sung nếu có giá trị.
~~~

Việc chia thực tế cần xét **điều kiện bắt buộc**. Ví dụ, nếu chống đăng ký trùng và phân quyền là điều kiện chất lượng của lát cắt A, không được tách chúng thành “làm sau khi đã Done A”. Một lát cắt dọc có thể nhỏ về số tính năng, nhưng vẫn phải **đúng và đủ an toàn cho phạm vi đó**.

### 8.1. Ví dụ cắt bớt phạm vi nhưng không cắt an toàn

Ban đầu Product Owner mong muốn:

1. Đăng ký khóa miễn phí qua giao diện.
2. Xác nhận đúng trạng thái.
3. Email xác nhận.
4. Thống kê lượt đăng ký cho quản trị viên.
5. Bộ lọc hiển thị chiến dịch đăng ký.

Nếu Sprint Goal là “người học đăng ký được khóa miễn phí và biết chắc kết quả”, có thể trao đổi để **ưu tiên 1–2**, với mọi kiểm tra DoD cần thiết. Những phần 3–5 có thể nằm ở Product Backlog để cân nhắc sau **nếu chúng không phải ràng buộc bắt buộc hoặc điều kiện thiết yếu của mục tiêu**.

### 8.2. Cẩn trọng với cụm từ “Minimum Viable”

“Viable” không có nghĩa “thiếu kiểm thử cũng được”. Một phiên bản phạm vi tối thiểu phải đủ giá trị để sử dụng đúng mục đích đã định và **đáp ứng điều kiện chất lượng áp dụng**. Nếu hệ thống có nguy cơ mất dữ liệu hoặc vi phạm quyền tài khoản, giảm tính năng không cho phép bỏ qua rủi ro đó.

### 8.3. Đừng chia nhỏ chỉ để làm đẹp số Done

Nếu một hành vi không sử dụng được độc lập, chia thành mười ticket “API xong”, “UI xong”, “DB xong” rồi cộng mười điểm có thể làm **throughput trông cao** mà giá trị không tăng. Có thể dùng technical task để lập kế hoạch, nhưng **Increment và DoD** mới cho biết phần sản phẩm hoàn tất.

## 9. Ví dụ xuyên suốt: còn hai ngày trước khi mở đăng ký

### 9.1. Bối cảnh giả định

Scrum Team làm Sprint mười ngày làm việc. Mục tiêu Sprint:

> “Người học đã đăng nhập có thể đăng ký khóa miễn phí và nhận xác nhận đáng tin cậy trước đợt khai giảng.”

Đến cuối ngày làm việc thứ tám, còn hai ngày:

| PBI | Trạng thái thực tế | Rủi ro đối với mục tiêu |
| --- | --- | --- |
| **A — Đăng ký và lưu dữ liệu** | Đã chạy trường hợp cơ bản; kiểm thử đồng thời phát hiện đăng ký trùng | **Chưa Done**, lỗi tính nhất quán quan trọng |
| **B — Xác nhận trong ứng dụng** | Giao diện hiện thành công khi API trả thành công; xử lý timeout chưa rõ | **Chưa Done**, có thể thông báo sai |
| **C — Danh sách khóa đã đăng ký** | Đã đạt DoD với những quy tắc đã thống nhất | **Done**, nhưng chưa đủ cho toàn Sprint Goal |
| **D — Email xác nhận** | Chưa bắt đầu; dịch vụ email bên ngoài chưa sẵn | Cần biết có bắt buộc theo giá trị hoặc cam kết không |
| **E — Báo cáo chiến dịch** | Có prototype nhưng chưa tích hợp và kiểm thử | Chưa Done; ít trực tiếp hỗ trợ Sprint Goal |

Một bên liên quan nói “C đã Done, A và B gần xong, vậy cứ phát hành”. Scrum Team cần kiểm tra **những điều kiện cần thiết cho hành vi cốt lõi**, không suy diễn từ số ticket.

### 9.2. Những quyết định Developers có thể chủ động thực hiện

Developers kiểm tra Sprint Goal, Sprint Backlog và trạng thái CI:

1. Tạm **không mở thêm E**; tập trung vào A và B.
2. Hai người phối hợp sửa chống đăng ký trùng và viết kiểm thử tái hiện.
3. Một người xử lý timeout và trạng thái chưa xác nhận của B.
4. Người có chuyên môn phù hợp hỗ trợ review, kiểm thử tích hợp và phân quyền.
5. Cập nhật Sprint Backlog để thể hiện việc bị chặn, rủi ro và hành động tiếp theo.

Tự quản nghĩa là Developers chọn **How** và điều chỉnh kế hoạch; không phải họ tự tuyên bố những điều kiện chất lượng đã đạt dù test vẫn đỏ.

### 9.3. Những câu hỏi cần trao đổi với Product Owner

Product Owner giúp làm rõ:

- Email D có thật sự là điều kiện bắt buộc của đợt đăng ký hay chỉ là giá trị bổ sung?
- Có thể giao luồng đăng ký và xác nhận trong ứng dụng trước, để email cho lần sau không?
- Nếu hệ thống chưa đáp ứng chất lượng trước ngày khai giảng, cần phương án vận hành/kinh doanh nào?
- Người dùng cần kết quả nào để tránh hiểu lầm rằng đã được đăng ký?

Những vấn đề hợp đồng, pháp lý hoặc vận hành vượt quyền Product Owner và Developers cần được đưa tới người có thẩm quyền tương ứng.

### 9.4. Hai khả năng kết quả đúng đắn

**Khả năng 1 — A và B đạt DoD trước hạn:** Scrum Team có thể trình bày Increment cho luồng đăng ký phù hợp; quyết định phát hành còn phụ thuộc những điều kiện phát hành áp dụng. D và E chưa Done không được gọi là Increment hoàn tất. Tình trạng đạt Sprint Goal được đánh giá dựa trên kết quả thực tế.

**Khả năng 2 — A vẫn lỗi đăng ký trùng:** Không gọi A là Done hoặc phát hành như chức năng hoàn tất. Nhóm minh bạch rủi ro, đề xuất phương án khả thi theo thẩm quyền: dời mốc chức năng, dùng quy trình đăng ký thay thế đã được kiểm soát, thu hẹp thông điệp ra mắt hoặc điều chỉnh kế hoạch sản phẩm. **Không đánh đổi dữ liệu người học để giữ hình ảnh tiến độ.**

### 9.5. Gherkin để làm rõ một phần tiêu chí chấp nhận

~~~gherkin
Tính năng: Đăng ký khóa học miễn phí

  Tình huống: Đăng ký thành công và xác nhận đúng
    Cho trước người học đã đăng nhập
    Và khóa "Java nhập môn" đang mở đăng ký miễn phí
    Và người học chưa có đăng ký đang có hiệu lực cho khóa này
    Khi người học đăng ký "Java nhập môn"
    Thì hệ thống ghi nhận một đăng ký hợp lệ
    Và giao diện xác nhận đăng ký thành công

  Tình huống: Gửi hai yêu cầu gần đồng thời
    Cho trước người học đã đăng nhập
    Và khóa "Java nhập môn" đang mở đăng ký
    Khi hai yêu cầu đăng ký cùng khóa đến gần đồng thời
    Thì hệ thống không tạo hai đăng ký đang có hiệu lực trùng nhau
    Và phản hồi tuân theo quy tắc đã được thống nhất

  Tình huống: Không xác nhận được kết quả ghi
    Cho trước dịch vụ không thể xác nhận đã lưu đăng ký
    Khi người học gửi yêu cầu đăng ký
    Thì giao diện không thông báo chắc chắn rằng đăng ký thành công
    Và người học được hướng dẫn kiểm tra hoặc thử lại phù hợp

  Tình huống: Không xem dữ liệu đăng ký của tài khoản khác
    Cho trước người học A đã đăng nhập
    Và một đăng ký thuộc tài khoản B
    Khi A tìm cách xem dữ liệu đăng ký của B
    Thì hệ thống từ chối theo chính sách phân quyền
    Và không tiết lộ dữ liệu riêng của B
~~~

Gherkin là **mô tả hành vi**, không tự trở thành kiểm thử chạy được. Muốn kiểm chứng cần cấu hình dữ liệu, bước thực thi và môi trường phù hợp. Những tình huống này là **ví dụ minh họa**, không thay thế DoD hoặc các nghĩa vụ khác của sản phẩm.

## 10. Cách làm việc hằng ngày để không đẩy chất lượng tới cuối Sprint

DoD chỉ được tôn trọng khi các hoạt động cần thiết nằm **trong dòng công việc**, không phải hàng chờ tách biệt vào cuối kỳ.

### 10.1. Trước khi kéo PBI vào thực hiện

- Làm rõ những ví dụ nghiệp vụ quan trọng và câu hỏi còn thiếu.
- Xem phụ thuộc về API, dữ liệu, quyền, môi trường và con người.
- Xem DoD áp dụng để dự báo công việc **đến Done**, không chỉ thời gian viết mã.
- Chia PBI đủ nhỏ để nhận phản hồi sớm và kiểm thử xuyên hệ thống khi có thể.
- Xác định rủi ro nào cần **spike hoặc thử nghiệm giới hạn** trước khi cam kết sâu.

### 10.2. Trong quá trình thực hiện

- Viết hoặc cập nhật kiểm thử phù hợp khi tạo hành vi mới.
- Tích hợp các thay đổi nhỏ thường xuyên.
- Review và kiểm thử xuyên suốt, không đợi riêng một “ngày QA”.
- Theo dõi các hạng mục chờ review/CI hoặc bị chặn.
- Khi có lỗi, ưu tiên sửa nguyên nhân và kiểm chứng, không tạo báo cáo xanh giả.
- Cộng tác để hoàn tất lát cắt gần Done trước khi kéo nhiều việc mới.

### 10.3. Tại Daily Scrum

Daily Scrum là sự kiện 15 phút của Developers để kiểm tra tiến độ hướng **Sprint Goal** và điều chỉnh **Sprint Backlog**. Một chuỗi câu hỏi có ích:

1. Phần Increment nào đã **thực sự Done**?
2. Điều kiện chất lượng nào đang cản phần giá trị cốt lõi?
3. Công việc đang bị chặn tại review, kiểm thử, dữ liệu hoặc môi trường?
4. Hôm nay nhóm có thể cùng hoàn tất item nào trước khi mở việc mới?
5. Có thay đổi phạm vi nào cần trao đổi với Product Owner?

**Daily Scrum không phải buổi báo cáo cho Scrum Master hoặc quản lý.** Developers chọn cấu trúc trao đổi phù hợp, miễn tạo được kế hoạch hành động hướng Sprint Goal.

### 10.4. Tại Sprint Retrospective

Nếu Sprint nào cũng gặp lỗi “đến ngày cuối mới thấy test thất bại”, nhóm cần tìm vấn đề hệ thống:

- Story quá lớn hoặc phụ thuộc mơ hồ?
- Kiểm thử tích hợp chỉ chạy ở cuối?
- Môi trường thiếu ổn định?
- Review quá lâu vì chỉ một người có quyền?
- DoD không rõ và không được đưa vào ước lượng?
- Quá nhiều WIP khiến không item nào kịp Done?

Retrospective nên kết thúc bằng **cải tiến khả thi**, có cách kiểm tra hiệu quả trong những Sprint tiếp theo.

## 11. Thực hành XP giúp giữ DoD khi thời gian ít

**Extreme Programming (XP)** cung cấp những kỷ luật kỹ thuật giúp thay đổi an toàn ngay cả khi kế hoạch thường xuyên biến động.

| Thực hành | Tác dụng với chất lượng liên tục | Cảnh báo |
| --- | --- | --- |
| **Test-Driven Development (TDD)** | Làm rõ hành vi và nhận phản hồi nhanh khi thay đổi | Không thay thế kiểm thử tích hợp, nghiệp vụ và bảo mật |
| **Continuous Integration (CI)** | Phát hiện sớm lỗi khi mã từ nhiều người được ghép | CI chỉ trên nhánh riêng nhiều tuần vẫn có rủi ro tích hợp muộn |
| **Pair programming** | Chia sẻ hiểu biết, xem xét quyết định và lỗi gần thời điểm tạo ra | Không bắt buộc mọi task phải làm cặp |
| **Refactoring** | Giảm độ phức tạp và chi phí thay đổi mà bảo vệ hành vi | Không đồng nghĩa viết lại toàn bộ vì sở thích kiến trúc |
| **Simple design** | Giảm chức năng và cấu trúc chưa cần thiết | Không phải bỏ ràng buộc dữ liệu hoặc kiểm soát lỗi |
| **Small releases** | Phân phối giá trị nhỏ, nhận phản hồi thường xuyên | Mỗi phần phát hành vẫn phải đáp ứng chất lượng áp dụng |
| **Collective ownership** | Giảm nghẽn khi một người vắng hoặc một phần mã cần hỗ trợ | Vẫn phải giữ quyền hạn và quy tắc bảo mật |

### 11.1. TDD và bài toán đăng ký trùng

Ví dụ, trước khi sửa logic lưu đăng ký, Developers có thể viết một bài kiểm thử mô phỏng hai yêu cầu đồng thời và thấy nó thất bại. Sau khi thêm cơ chế nhất quán phù hợp ở tầng dữ liệu, kiểm thử chạy lại để xác nhận.

Lưu ý: một unit test thuần không kiểm chứng được mọi đặc tính đồng thời của database thật. Cần **integration/concurrency test** cho ranh giới rủi ro nếu có liên quan.

### 11.2. CI không chỉ nhằm “đèn xanh”

Một pipeline xanh chỉ chứng minh **các kiểm tra đã cấu hình** đạt ở điều kiện thử tương ứng. Nếu pipeline không có kiểm thử phân quyền, trạng thái xanh không bảo đảm phân quyền đúng. Nếu test flaky và mọi người rerun tới khi xanh, nhóm mất niềm tin vào phản hồi.

Khi pipeline đỏ:

1. Xác nhận lỗi thuộc mã, dữ liệu, môi trường hay công cụ.
2. Giữ minh bạch về trạng thái chưa đạt.
3. Sửa hoặc hoàn nguyên thay đổi theo chính sách để khôi phục trạng thái chung.
4. Kiểm chứng lại các điều kiện cần thiết.
5. Cải thiện test hoặc quy trình để hạn chế lỗi lặp lại.

### 11.3. Kiểm tra nhiều tầng theo rủi ro

| Tầng | Ví dụ kiểm chứng | Điều chưa bảo đảm |
| --- | --- | --- |
| Unit test | Quy tắc trả trạng thái khi đăng ký trùng | DB không tạo dữ liệu trùng khi concurrent |
| Contract test | Frontend hiểu trạng thái API thực trả | Luồng người dùng từ đầu tới cuối thành công |
| Integration test | API, dữ liệu và môi trường thử hoạt động cùng nhau | Toàn bộ trải nghiệm sản phẩm dễ hiểu |
| Acceptance/end-to-end | Người học đăng ký và thấy kết quả đúng | Không có mọi lỗi bảo mật hoặc vận hành |
| Security test/review | Quyền tài khoản và dữ liệu được bảo vệ trong rủi ro áp dụng | Không tồn tại bất kỳ lỗ hổng nào |
| Observability/smoke test | Sau phát hành phát hiện lỗi quan trọng | Outcome người dùng đã cải thiện |

Không có số lượng test hoặc tỷ lệ coverage “chuẩn Agile” áp dụng cho mọi nhóm. **Chọn bằng chứng theo rủi ro và DoD**, đồng thời duy trì vòng phản hồi đủ nhanh.

## 12. Kanban giúp nhìn thấy phần chất lượng đang bị nghẽn

Trong một Sprint hoặc hệ thống Kanban, nhóm có thể trực quan hóa dòng:

~~~text
Sẵn sàng        Đang phát triển        Review / CI        Kiểm thử        Done
--------------- --------------------- ------------------ ---------------- ---------------
Email bổ sung   Xử lý đăng ký lặp     Sửa trạng thái API  Phân quyền      Danh sách khóa
Báo cáo         Xác nhận lỗi mạng     Migration dữ liệu
~~~

Nếu nhiều item nằm ở **Review/CI** và **Kiểm thử**, Developers tiếp tục kéo thêm việc mới vào phát triển có thể làm tăng WIP mà không tăng Increment Done.

### 12.1. Những tín hiệu nên quan sát

- **WIP:** Có bao nhiêu item đã bắt đầu nhưng chưa Done?
- **Work Item Age:** Mỗi item còn dở đã tồn tại bao lâu từ mốc bắt đầu?
- **Cycle Time:** Các item đã Done mất bao lâu từ bắt đầu đến hoàn tất?
- **Throughput:** Có bao nhiêu item thật sự Done theo khoảng thời gian?
- **Blocked Time:** Thời gian bị chặn ở phụ thuộc nào?
- **Test/review queue:** Hàng chờ chất lượng có phải nút nghẽn?

**Work Item Age không phải phần trăm hoàn thành.** Một item đã ở trong luồng chín ngày không đồng nghĩa 90% Done hoặc chắc sẽ xong ngày mai.

### 12.2. Trực quan hóa để chọn hành động

Ví dụ:

| Item | Tuổi hiện tại | Trạng thái | Hành động có ích |
| --- | ---: | --- | --- |
| A — Chống đăng ký trùng | 7 ngày | Chờ integration test | Ưu tiên môi trường và dữ liệu kiểm thử |
| B — Xác nhận lỗi mạng | 5 ngày | Review | Người phù hợp hỗ trợ review và test |
| C — Email phụ | 1 ngày | Đang phát triển | Xem lại ưu tiên nếu A/B chặn mục tiêu |
| D — Danh sách khóa | Đã Done | Đạt DoD | Giữ bằng chứng; không mở lại vì cần tăng số task |

Một giải pháp phù hợp có thể là **ngừng bắt đầu C và cùng hoàn tất A/B**, tùy mức độ thiết yếu và thẩm quyền quyết định phạm vi. Việc này tốt hơn “đẩy mọi người bận 100%” nếu hàng chờ chất lượng là nút nghẽn.

## 13. Feature flag và phát hành từng phần có giúp giữ chất lượng?

**Có thể**, nếu được dùng để kiểm soát phạm vi tiếp cận hoặc tách thời điểm tích hợp mã khỏi thời điểm bật hành vi cho người dùng. Nhưng flag không biến mã chưa đủ chất lượng thành Done.

### 13.1. Một tình huống hợp lệ

Nhóm đã hoàn tất luồng đăng ký cốt lõi, còn một trải nghiệm email phụ chưa xong. Nếu được phê duyệt theo giá trị và ràng buộc, nhóm có thể phát hành **luồng cốt lõi đã đạt DoD** trong khi giữ email ngoài phạm vi và không khẳng định email đã hoàn tất.

### 13.2. Một tình huống không hợp lệ

Luồng đăng ký còn lỗi làm trùng dữ liệu. Nhóm bật flag cho “một nhóm người dùng nhỏ” nhưng không có cơ chế kiểm soát hậu quả, chỉ để tuyên bố đã giao đúng hạn. **Phát hành giới hạn không tự động làm một lỗi dữ liệu nghiêm trọng trở nên chấp nhận được.**

### 13.3. Rủi ro của flag

- Tạo nhiều tổ hợp bật/tắt khó kiểm thử.
- Cấu hình sai môi trường làm tính năng được bật ngoài dự định.
- Mã cũ và mã mới cùng tồn tại lâu gây khó bảo trì.
- Người dùng nhận trạng thái không nhất quán khi chuyển flag.
- Hệ thống thiếu quan sát hoặc cách rollback phù hợp.

Nhóm cần có chính sách kiểm thử các trạng thái liên quan, phân quyền thay đổi flag và dọn bỏ flag khi không còn cần. Không đánh đồng **feature flag** với **miễn DoD**.

### 13.4. Increment Done và release-ready cần được nói chính xác

Nếu một Increment đã đạt DoD nhưng chưa được phát hành vì chờ lịch kinh doanh, nó vẫn có thể là phần sản phẩm hoàn tất. Nếu chưa đạt DoD, việc để trong nhánh riêng, sau flag hoặc ở môi trường staging **không làm nó thành Done**.

## 14. Chất lượng liên tục trong những thay đổi có rủi ro đặc biệt

Thời hạn thường tạo áp lực lớn nhất tại các vùng có chi phí sai cao.

| Loại thay đổi | Rủi ro điển hình | Bằng chứng và kiểm soát cần cân nhắc |
| --- | --- | --- |
| **Thanh toán** | Thu tiền sai, ghi nhận trùng | Quy tắc giao dịch, idempotency, kiểm thử lỗi, đối soát |
| **Quyền truy cập** | Lộ dữ liệu tài khoản khác | Authorization ở server, test quyền, review bảo mật |
| **Migration dữ liệu** | Mất hoặc sai dữ liệu cũ | Kế hoạch migration/khôi phục, thử dữ liệu đại diện |
| **Tích hợp API** | Hợp đồng giữa client/server lệch | Contract test, chiến lược tương thích |
| **Tính đồng thời** | Ghi đè, trạng thái không nhất quán | Concurrency/integration test, ràng buộc DB khi phù hợp |
| **Khả năng vận hành** | Không phát hiện lỗi sau deploy | Logs/metrics, smoke test, quan sát và xử lý sự cố |
| **Hiệu năng** | Nghẽn khi chiến dịch có nhiều người dùng | Kiểm tra tải theo yêu cầu và năng lực thực tế |
| **Accessibility** | Người dùng không tiếp cận được chức năng | Kiểm tra khả năng tiếp cận theo tiêu chuẩn áp dụng |

Ví dụ, kiểm thử lỗi đăng ký trùng có thể là tiêu chí bắt buộc với luồng ghi dữ liệu, nhưng không nhất thiết áp dụng cùng cách cho một thay đổi màu nền. Cách làm chất lượng liên tục cần **phân loại rủi ro**, không gom mọi thay đổi vào một quy trình cứng không có ý nghĩa.

### 14.1. Khi khẩn cấp thật sự

Nếu đang có sự cố production gây hại, nhóm có thể cần quy trình **ứng cứu/hotfix khẩn cấp** với quyền quyết định và kiểm soát đặc biệt. Điều đó không đồng nghĩa “muốn nhanh thì được tắt mọi kiểm tra”.

Một luồng khẩn cấp an toàn có thể gồm:

1. Xác định mức độ ảnh hưởng và trách nhiệm chỉ huy sự cố.
2. Ưu tiên ngăn tác động tiếp tục, ví dụ tắt khả năng gây hại qua cơ chế đã được phê duyệt.
3. Kiểm chứng thay đổi khắc phục ở mức phù hợp với rủi ro và yêu cầu bắt buộc.
4. Có người phê duyệt, kế hoạch giám sát và khôi phục theo quy định.
5. Sau sự cố, xem lại nguyên nhân và cải tiến DoD/pipeline khi cần.

**Không khẳng định mọi hotfix đều phải có cùng bộ kiểm tra như một thay đổi lớn thông thường**, nhưng cũng không được xem quy trình khẩn là giấy phép bỏ chất lượng hoặc che rủi ro.

## 15. Minh bạch tiến độ bằng bằng chứng thay vì phần trăm cảm tính

Khi thời hạn đến gần, bên liên quan cần biết **có thể quyết định gì**, không chỉ nghe “chúng tôi đã hoàn thành 95%”.

### 15.1. Một bản cập nhật hữu ích

> **Sprint Goal:** Người học đăng ký khóa miễn phí và nhận xác nhận đáng tin cậy.  
> **Increment đã Done:** Danh sách khóa đã đăng ký theo phạm vi đã thống nhất.  
> **Chưa Done:** Đăng ký từ giao diện tới dữ liệu; kiểm thử đồng thời phát hiện đăng ký trùng.  
> **Rủi ro:** Nếu phát hành hiện trạng, một người học có thể tạo nhiều đăng ký đang có hiệu lực.  
> **Hành động:** Developers tập trung sửa và kiểm tra dữ liệu; dừng mở công việc phụ.  
> **Quyết định cần phối hợp:** Xác nhận email phụ có thể để sau không; chuẩn bị phương án vận hành nếu không đủ chất lượng trước ngày khai giảng.  
> **Mốc kiểm tra tiếp:** Sau khi có kết quả integration/concurrency test và review.

Tránh nói “chắc chắn xong ngày mai” khi còn phụ thuộc chưa được kiểm chứng. Nếu cần dự báo, nêu **giả định, mức bất định và điều kiện phải thỏa**.

### 15.2. Tách bốn trạng thái trong báo cáo

| Trạng thái | Diễn giải chính xác |
| --- | --- |
| **Chưa bắt đầu** | Công việc chưa tiêu thụ năng lực thực hiện |
| **Đang làm / đang kiểm chứng** | Có hoạt động hoặc mã, nhưng chưa đạt DoD |
| **Done** | Phần công việc đáp ứng DoD và thuộc Increment |
| **Đã phát hành** | Increment được đưa tới phạm vi người dùng theo chính sách phát hành |

Một item Done có thể chưa phát hành; một item đang làm không nên được đổi sang Done chỉ vì đã merge mã. Những nhãn rõ ràng giúp giảm hiểu lầm giữa Scrum Team và stakeholder.

### 15.3. Truyền đạt quyết định khó mà không đổ lỗi

Thay vì: “QA chưa test xong nên không kịp.”

Nên nói: “Nhóm chưa có bằng chứng đạt tiêu chuẩn chất lượng cho xử lý đăng ký đồng thời. Tình trạng này đe dọa sự tin cậy của dữ liệu, nên chúng tôi chưa thể coi luồng là Done. Developers đang phối hợp xử lý và sẽ báo kết quả kiểm chứng.”

Chất lượng là **trách nhiệm chung**. Khi hàng chờ QA, review hoặc môi trường bị nghẽn, xem nguyên nhân ở **dòng công việc** thay vì quy kết cho cá nhân.

## 16. Dự báo khi có thời hạn: nhìn khả năng Done, không chỉ tốc độ code

Ước lượng và dự báo luôn có bất định. Một số nguồn:

- PBI lớn hơn dự kiến vì điều kiện biên.
- Môi trường tích hợp không sẵn.
- Một dịch vụ ngoài lỗi hoặc thay đổi hợp đồng.
- Dữ liệu cũ chứa tình huống không được dự báo.
- Người có quyền phê duyệt vắng mặt.
- Kiểm thử phát hiện hành vi nghiệp vụ chưa rõ.

**Số story point hoặc thời gian gõ mã đã hoàn tất** không đủ kết luận công việc sẽ đạt DoD trước hạn.

### 16.1. Một cách dự báo có điều kiện

Giả sử vào ngày thứ tám của Sprint mười ngày:

| Công việc còn lại để PBI A đạt Done | Tình trạng | Điều kiện |
| --- | --- | --- |
| Sửa lỗi đăng ký trùng | Đang thực hiện | Cần thống nhất xử lý idempotency |
| Chạy kiểm thử hai yêu cầu gần đồng thời | Chưa đạt | Cần môi trường và dữ liệu kiểm tra |
| Review thay đổi dịch vụ và dữ liệu | Chưa hoàn tất | Người review phù hợp cần sẵn |
| Kiểm tra toàn bộ luồng đăng ký | Chưa hoàn tất | Phụ thuộc các bước trên |

Từ bảng, có thể nói “**có rủi ro không Done trước hạn**” với cơ sở cụ thể. Không nên cộng ước lượng từng task rồi mặc định tất cả hoạt động có thể chạy song song hoặc không gặp lỗi.

### 16.2. Dữ liệu luồng giúp gì?

Trong Kanban hoặc Scrum có dùng quản lý luồng, nhóm có thể nhìn:

- **Throughput:** Số hạng mục thật sự Done theo kỳ.
- **Cycle Time:** Thời gian từ bắt đầu tới Done cho item hoàn tất.
- **Work Item Age:** Tuổi của item đang dở để phát hiện nguy cơ kéo dài.
- **WIP:** Mức công việc đang mở có gây hàng chờ?
- **Service Level Expectation (SLE):** Kỳ vọng thời gian hoàn tất theo một mức xác suất/kỳ vọng đã được diễn đạt rõ cho loại item tương đồng.

SLE là kỳ vọng theo phân bố, **không phải bảo đảm một PBI sẽ xong đúng hạn**. Tuổi item bằng 90% mốc SLE không có nghĩa đã hoàn thành 90% công việc. Dữ liệu có thể giúp nhóm **thấy rủi ro và điều chỉnh**, không thay thế đánh giá các điều kiện chất lượng thực tế.

### 16.3. Không bịa xác suất cho một mốc cố định

Nếu nhóm chưa có dữ liệu hoặc mô hình phù hợp, không nên nói “có 87% khả năng sẽ kịp thứ Sáu”. Nên trình bày **kịch bản, giả định, phụ thuộc và phương án khi không đạt**.

## 17. Trách nhiệm ra quyết định khi cần đánh đổi

Scrum có **một Product Owner, một Scrum Master và Developers** trong Scrum Team. Khi thời hạn gây áp lực, vai trò rõ giúp nhóm tránh vừa đổ lỗi vừa ra quyết định sai thẩm quyền.

| Quyết định | Trách nhiệm phù hợp |
| --- | --- |
| Sắp thứ tự Product Backlog, tối đa hóa giá trị sản phẩm | **Product Owner** |
| Chọn PBI trong Sprint Planning qua trao đổi với Product Owner | **Developers** |
| Tạo và điều chỉnh kế hoạch How trong Sprint | **Developers** |
| Cùng xây và hướng tới Sprint Goal | **Cả Scrum Team** |
| Giữ chất lượng theo Definition of Done | **Developers**, trong trách nhiệm chung của Scrum Team |
| Làm rõ/thương lượng phạm vi khi học thêm | **Developers cộng tác với Product Owner** |
| Hỗ trợ áp dụng Scrum, loại bỏ trở ngại và cải thiện hiệu quả | **Scrum Master** |
| Hủy Sprint khi Sprint Goal lỗi thời | **Chỉ Product Owner** |
| Chấp nhận/điều chỉnh nghĩa vụ pháp lý, hợp đồng, an toàn đặc biệt | **Người có thẩm quyền tương ứng của tổ chức**, không tự suy đoán từ Scrum |

### 17.1. Product Owner không thể “ký cho qua DoD”

Product Owner có thể thương lượng phạm vi và quyết định ưu tiên giá trị, nhưng không được biến phần chưa đạt DoD thành Increment bằng một lời chấp thuận hình thức. Đặc biệt, các chuẩn tổ chức hoặc nghĩa vụ pháp lý vẫn có hiệu lực.

### 17.2. Scrum Master không phải người cưỡng ép đóng ticket

Scrum Master hỗ trợ nhóm cải thiện Scrum, tự quản và xử lý trở ngại. Nếu Scrum Master trở thành người kiểm tra ai “chậm task” rồi yêu cầu hạ kiểm thử để đạt velocity, vai trò đã lệch khỏi mục đích.

### 17.3. Developers có quyền đề xuất đánh đổi kỹ thuật

Developers chọn phương án, chia công việc, hỗ trợ nhau, kiểm thử và tích hợp. Khi một thay đổi ảnh hưởng giá trị/phạm vi, cần trao đổi với Product Owner; khi vượt quyền kỹ thuật hoặc an toàn, cần hỏi đúng người có thẩm quyền. **Tự quản không phải tự miễn trách nhiệm chất lượng**.

## 18. Nợ kỹ thuật phát sinh thế nào khi cố “kịp hạn”?

Không phải mọi lựa chọn ngắn hạn đều là nợ kỹ thuật. Nhưng liên tục bỏ qua các cải tiến cần thiết hoặc để chất lượng chưa hoàn tất tích tụ có thể khiến thay đổi sau này tốn công hơn.

### 18.1. Phân biệt “nợ kỹ thuật” với “việc chưa Done”

- **Việc chưa Done:** Một PBI còn thiếu điều kiện DoD. Không được gọi nó là Increment hoàn tất rồi dán nhãn “nợ kỹ thuật” để hợp thức hóa.
- **Nợ kỹ thuật:** Một cấu trúc hoặc quyết định kỹ thuật có chi phí tương lai đã được nhận diện, trong khi phần công việc hiện tại vẫn **đáp ứng chuẩn chất lượng áp dụng**; có thể cần ghi backlog và quản lý rủi ro.

Ví dụ, chọn một cấu trúc triển khai đơn giản nhưng dễ refactor sau có thể là đánh đổi có trách nhiệm nếu không vi phạm DoD và yêu cầu hiện tại. Bỏ kiểm tra phân quyền bắt buộc thì không.

### 18.2. Làm thế nào để đầu tư vào chất lượng khi backlog luôn đầy?

1. Nêu **hậu quả cụ thể** của nút nghẽn hoặc cấu trúc khó thay đổi.
2. Dùng bằng chứng: lỗi lặp, thời gian chờ, sự cố hoặc chi phí làm lại.
3. Đề xuất một **cải tiến nhỏ** với mục tiêu đo được.
4. Cộng tác với Product Owner về thứ tự ưu tiên và rủi ro sản phẩm.
5. Thực hiện, kiểm chứng và điều chỉnh theo kết quả.

Một câu hỏi như “Có nên xây framework test mới?” nên được nối với vấn đề thật: “Kiểm thử tích hợp đăng ký mất nhiều ngày để chạy, khiến PBI thường không Done vào cuối Sprint.”

### 18.3. Không có tỷ lệ “phải dành X% cho chất lượng” áp dụng chung

Một nhóm có thể thử thỏa thuận dành năng lực cho cải tiến pipeline hoặc xử lý nợ kỹ thuật, nhưng **Scrum không quy định một tỷ lệ cố định**. Các chuẩn an toàn và DoD vẫn phải được đáp ứng ở mọi trường hợp; công việc cải tiến ngoài DoD được ưu tiên theo giá trị và rủi ro thực tế.

## 19. Những hiểu lầm khi thời hạn gây áp lực

**1. “Chất lượng có thể giảm trong Sprint để bảo vệ Sprint Goal.”** Scrum xác định chất lượng không được giảm; cần điều chỉnh kế hoạch và thương lượng phạm vi đúng trách nhiệm.

**2. “Product Owner có thể ký miễn DoD cho một PBI.”** Chấp thuận giá trị không biến phần chưa đạt chuẩn thành Increment.

**3. “Code đã merge tức là Done.”** Merge chỉ là một bước; cần kiểm tra mọi điều kiện DoD áp dụng.

**4. “CI xanh nghĩa là chắc chắn đạt DoD.”** Pipeline chỉ kiểm tra những gì được cấu hình; có thể thiếu bảo mật, nghiệp vụ, tích hợp hoặc vận hành.

**5. “95% task xong tương đương Sprint Goal đạt 95%.”** Task không đại diện trực tiếp cho kết quả người dùng hoặc mức đạt mục tiêu.

**6. “Nếu một kiểm thử thất bại, chỉ cần bỏ test để qua mốc.”** Che lỗi không phải cải tiến chất lượng.

**7. “Tất cả bài test phải chạy giống hệt nhau cho mọi thay đổi.”** Kiểm chứng cần theo rủi ro, nghĩa vụ và DoD; không tạo nghi thức không có giá trị.

**8. “Đến ngày cuối mới cần nghĩ về DoD.”** Tiêu chuẩn hoàn tất phải ảnh hưởng cách chia PBI, thiết kế, kiểm thử, tích hợp và dự báo từ đầu.

**9. “Giảm scope nghĩa là bỏ bảo mật hoặc xử lý lỗi.”** Bỏ chức năng không thiết yếu khác với bỏ điều kiện chất lượng của chức năng còn lại.

**10. “Sprint Backlog là hợp đồng khóa cứng từng PBI.”** Phạm vi có thể được làm rõ và thương lượng với Product Owner khi học thêm; Sprint Goal định hướng các điều chỉnh.

**11. “PBI chưa Done tự động trở thành cam kết của Sprint sau.”** Product Backlog cần được xem xét và chọn lại theo ưu tiên/năng lực.

**12. “Sprint Goal khó đạt thì Developers có thể tự hủy Sprint.”** Chỉ Product Owner có quyền hủy nếu Sprint Goal trở nên lỗi thời.

**13. “Release nhỏ cho ít người thì lỗi dữ liệu nghiêm trọng có thể chấp nhận.”** Phát hành giới hạn không xóa nghĩa vụ chất lượng và an toàn.

**14. “Feature flag cho phép gọi mã chưa kiểm chứng là Done.”** Flag kiểm soát tiếp cận, không tự thay thế DoD.

**15. “Done luôn đồng nghĩa đã triển khai production.”** Increment có thể Done trước khi phát hành; cần phân biệt ranh giới.

**16. “QA chịu trách nhiệm chất lượng, Developers chỉ viết mã.”** Developers cùng chịu trách nhiệm tạo Increment đáp ứng DoD; kiểm thử là năng lực cộng tác.

**17. “Làm thêm giờ là phương án tốt nhất khi deadline sát.”** Đây không phải cách xử lý bền vững cho kế hoạch quá tải và nút nghẽn lặp lại.

**18. “Càng nhiều WIP càng tận dụng được năng lực.”** Hàng chờ review, test và tích hợp có thể tăng; giảm WIP giúp hoàn tất công việc thật.

**19. “Velocity là thước đo giá trị của cá nhân.”** Velocity không phải chỉ số Scrum bắt buộc và không thay thế chất lượng, Increment hay outcome.

**20. “Một lần hotfix khẩn có thể bỏ mọi quy trình kiểm tra.”** Khẩn cấp cần quy trình ứng cứu phù hợp rủi ro và thẩm quyền, không phải miễn kiểm soát.

**21. “DoD không bao giờ được cải tiến.”** DoD có thể phát triển để phản ánh rủi ro và tiêu chuẩn, nhưng không nên bị hạ vì áp lực thời hạn.

**22. “Không phát hành đúng hạn nghĩa là Agile thất bại.”** Có thể có sai lầm kế hoạch cần học, nhưng phát hành phần chưa an toàn để giữ ngày hứa còn có thể gây hại lớn hơn.

**23. “Có thể gọi phần dang dở là technical debt rồi xem như Done.”** Việc chưa đạt DoD vẫn là chưa Done; nợ kỹ thuật không phải nhãn hợp thức hóa công việc chưa hoàn tất.

**24. “Nếu không kịp Sprint, cứ giấu phần test còn thiếu để stakeholder khỏi lo.”** Minh bạch là điều kiện để ra quyết định có trách nhiệm và thích ứng.

## 20. Bài tập tình huống: ngày mở chương trình không thể dời?

Một Scrum Team đang phát triển nền tảng học trực tuyến, Sprint còn **hai ngày làm việc**. Product Owner đã trao đổi với bộ phận kinh doanh về ngày khai giảng; bên kinh doanh nói “không thể thay đổi lịch marketing”.

**Sprint Goal:** Người học mới có thể đăng ký khóa miễn phí và nhận xác nhận đáng tin cậy.

**Tình trạng thực tế:**

| Hạng mục | Trạng thái | Vấn đề |
| --- | --- | --- |
| A — Lưu đăng ký | Integration test đỏ | Hai request gần đồng thời tạo bản ghi trùng |
| B — Hiển thị xác nhận | Chưa đạt DoD | Timeout có thể hiện thông báo thành công sai |
| C — Danh sách khóa | Đạt DoD | Đã dùng được theo phạm vi xác định |
| D — Email xác nhận | Chưa bắt đầu | Chưa rõ có bắt buộc theo chính sách chiến dịch không |
| E — Dashboard chiến dịch | Prototype nội bộ | Chưa có khả năng tích hợp, kiểm thử |

**Áp lực:** Một người quản lý đề nghị đánh dấu A/B “Done có điều kiện”, bỏ concurrency test và triển khai ngay vì có thể sửa sau.

### Câu hỏi

1. Điều gì khiến đề nghị “Done có điều kiện” không phù hợp với ý nghĩa DoD?
2. Những việc nào Developers có thể **chủ động thay đổi kế hoạch** ngay hôm nay?
3. Những quyết định nào cần **Product Owner** hoặc người có thẩm quyền liên quan tham gia?
4. Nêu hai cách **giảm scope hợp lệ**, cùng điều kiện trước khi áp dụng.
5. Nếu A/B chưa đạt DoD khi Sprint kết thúc, phải báo cáo và xử lý backlog thế nào?
6. Có thể phát hành C riêng không? Những điều gì cần xem trước khi quyết định?
7. Nếu mốc marketing cố định nhưng phần đăng ký chưa an toàn, đề xuất một phương án kinh doanh/vận hành thay thế có trách nhiệm.
8. Những chỉ số nào sẽ giúp nhóm phát hiện vấn đề sớm hơn ở Sprint sau?
9. Nếu muốn cải thiện DoD, nhóm nên làm thế nào mà không biến việc này thành hạ chuẩn khi trễ hạn?
10. Viết một thông báo ngắn cho bên kinh doanh về kết quả và quyết định cần đưa ra.

### Gợi ý lời giải

**Câu 1:** A/B còn lỗi quan trọng và chưa đáp ứng chất lượng đã xác định. Dán nhãn “Done có điều kiện” không tạo Increment. Nếu test concurrency hoặc xử lý trạng thái lỗi là điều kiện chất lượng áp dụng, không được bỏ để đạt mốc.

**Câu 2:** Developers có thể giảm WIP, dừng E, cùng sửa A và B, ưu tiên review/kiểm thử xuyên hệ thống, chuẩn bị dữ liệu test và kiểm tra quyền tài khoản. Họ cập nhật Sprint Backlog, minh bạch trở ngại và đánh giá khả năng đạt Sprint Goal.

**Câu 3:** Product Owner cần trao đổi giá trị, thứ tự ưu tiên và việc D/E có thể hoãn. Nếu email D là nghĩa vụ hợp đồng hoặc mốc chiến dịch có điều kiện pháp lý/vận hành, phải tham vấn đúng người có thẩm quyền. Không tự tuyên bố được miễn chuẩn.

**Câu 4:** Có thể hoãn **E** vì không trực tiếp giúp người học đăng ký. Có thể hoãn **D** nếu xác nhận trong ứng dụng đủ đáp ứng Sprint Goal **và** D không phải yêu cầu bắt buộc. Cả hai phải trao đổi đúng trách nhiệm; A/B vẫn cần đạt DoD.

**Câu 5:** A/B không là phần Increment Done và không được giới thiệu như kết quả đã hoàn tất. Minh bạch rủi ro; công việc trở lại Product Backlog để xem xét, làm rõ và sắp thứ tự. Không tự động coi là cam kết bất biến của Sprint kế tiếp.

**Câu 6:** C có thể là một Increment Done nếu đã đạt DoD, nhưng phát hành riêng chỉ hữu ích khi có giá trị và điều kiện vận hành phù hợp. Phải xem phụ thuộc của C vào dữ liệu đăng ký thật, quyền truy cập và rủi ro khiến người dùng hiểu sai trạng thái; không phát hành chỉ vì “đã có một PBI xanh”.

**Câu 7:** Nhóm có thể đề xuất dời thời điểm bật chức năng đăng ký, điều chỉnh thông điệp marketing, mở trang giới thiệu khóa trước hoặc dùng quy trình đăng ký thay thế được kiểm soát **nếu có thiết kế và phê duyệt phù hợp**. Không tự tạo quy trình thu thập dữ liệu người học ngoài kiểm soát.

**Câu 8:** Theo dõi hàng chờ review/test, WIP, work item age, thời gian tới kết quả CI, cycle time tới DoD, tỷ lệ flaky và lỗi tích hợp phát hiện muộn. Xem cùng chất lượng và kết quả người dùng, không dùng làm KPI quy trách nhiệm cá nhân.

**Câu 9:** Xem DoD trong Retrospective hoặc hoạt động cải tiến phù hợp, dùng bằng chứng về lỗi và rủi ro, làm rõ tiêu chí kiểm chứng, thống nhất đúng trách nhiệm và tiêu chuẩn tổ chức. Không hạ DoD chỉ để gọi phần đang lỗi là Done.

**Câu 10 — Thông báo minh họa:**

> “Tính năng đăng ký chưa đáp ứng tiêu chuẩn hoàn tất: kiểm thử ghi nhận trường hợp tạo đăng ký trùng và thông báo thành công không chính xác khi dịch vụ lỗi. Nhóm đang ưu tiên khắc phục hai rủi ro này, không coi chức năng là Done hoặc phát hành như đã an toàn. Danh sách khóa đã hoàn tất theo tiêu chuẩn, nhưng chưa thay thế luồng đăng ký cốt lõi. Chúng tôi cần cùng xác nhận ưu tiên email, phương án cho mốc khai giảng và điều kiện phát hành phù hợp. Kết quả kiểm chứng sẽ là cơ sở cho quyết định tiếp theo.”

## 21. Bài tập nhanh: thiết kế một cuộc trao đổi 15 phút

Hãy dùng cấu trúc sau trong Daily Scrum hoặc một buổi phối hợp ngắn khi Sprint đang có rủi ro. Đây là **gợi ý thực hành**, không phải mẫu ba câu hỏi bắt buộc của Scrum:

| Phút minh họa | Nội dung | Kết quả cần có |
| --- | --- | --- |
| 0–3 | Nhìn Sprint Goal và những Increment thực sự Done | Thống nhất giá trị đã có/chưa có |
| 3–6 | Nhìn các hạng mục chưa đạt DoD và trở ngại | Chọn rủi ro quan trọng nhất |
| 6–10 | Quyết định cùng hoàn tất và giảm WIP | Hành động, người phối hợp, bước kiểm chứng |
| 10–13 | Xác định phạm vi hoặc câu hỏi cần Product Owner làm rõ | Có người trao đổi đúng thẩm quyền |
| 13–15 | Cập nhật Sprint Backlog và mốc kiểm tra lại | Kế hoạch có thể hành động cho ngày tiếp theo |

Thảo luận sâu về lỗi kỹ thuật có thể diễn ra sau Daily Scrum giữa những người cần tham gia. Nếu một vấn đề an toàn nghiêm trọng xuất hiện vào buổi chiều, **không cần chờ Daily Scrum sáng hôm sau** mới xử lý.

### Mẫu working agreement ngắn

> “Chúng tôi chỉ đánh dấu một PBI là Done khi đáp ứng Definition of Done áp dụng. Khi thời hạn có rủi ro, Developers cùng nhìn Sprint Goal, giảm WIP và ưu tiên hoàn tất lát cắt có giá trị. Mọi điều chỉnh phạm vi được trao đổi với Product Owner; nghĩa vụ an toàn, bảo mật và vận hành được xử lý theo đúng thẩm quyền. Kết quả kiểm thử thất bại được minh bạch, không bị xóa để làm đẹp tiến độ. Phần chưa Done được trình bày trung thực và xem xét lại trong Product Backlog.”

## 22. Checklist trước khi nói “đã Done” dưới áp lực deadline

### Về giá trị và phạm vi

1. **Sprint Goal:** Kết quả chung cần đạt có còn rõ ràng không?
2. **Phạm vi:** Những tính năng nào thiết yếu và tính năng nào có thể thương lượng?
3. **Lát cắt:** Phần dự định gọi Done có thể sử dụng có nghĩa, không chỉ là task kỹ thuật rời?
4. **Ưu tiên:** Product Owner đã được trao đổi về thay đổi phạm vi quan trọng?
5. **Ràng buộc:** Những nghĩa vụ pháp lý, hợp đồng, dữ liệu và vận hành có được xác minh?

### Về chất lượng của phần định gọi Done

6. **Acceptance criteria:** Các hành vi và tình huống lỗi quan trọng đã được kiểm chứng?
7. **DoD:** Đã đáp ứng toàn bộ tiêu chuẩn chất lượng áp dụng, không chỉ “code xong”?
8. **Tích hợp:** Các thành phần đã hoạt động cùng nhau theo phạm vi cần thiết?
9. **Bảo mật:** Quyền truy cập và dữ liệu có được bảo vệ theo chuẩn áp dụng?
10. **Dữ liệu:** Có nguy cơ trùng, mất, ghi đè hoặc migration sai chưa xử lý?
11. **Kiểm thử:** Kết quả có đáng tin; test đỏ hoặc flaky chưa bị che giấu?
12. **Review:** Những kiểm tra/chấp thuận chuyên môn cần thiết đã đạt?
13. **Vận hành:** Lỗi có thể quan sát và xử lý theo yêu cầu?
14. **Bằng chứng:** Có cách xem kết quả thay vì chỉ lời nói “chắc ổn”?

### Về kế hoạch và công bố

15. **WIP:** Có đang mở quá nhiều công việc thay vì hoàn tất?
16. **Nút nghẽn:** Đã có hành động gỡ review, test, môi trường hoặc phụ thuộc?
17. **Dự báo:** Mốc hoàn tất có được nêu cùng giả định và bất định?
18. **Phân biệt trạng thái:** Done, chưa Done và đã phát hành có được trình bày chính xác?
19. **Phát hành:** Những điều kiện release riêng có được đánh giá?
20. **Ứng phó:** Nếu không đủ chất lượng đúng hạn, đã có phương án thay thế có thẩm quyền?
21. **Trách nhiệm:** Không dùng cá nhân làm vật chịu lỗi thay cho vấn đề hệ thống?
22. **Cải tiến:** Nhóm có xem lại nguyên nhân gây áp lực vào Retrospective?

## 23. Tổng kết: linh hoạt ở phạm vi, nhất quán ở chất lượng

Khi thời hạn gây áp lực, giữ DoD không có nghĩa nhóm cứng nhắc bám một kế hoạch ban đầu. Điều cần bảo vệ là **ý nghĩa của kết quả hoàn tất**.

| Phản ứng dễ gây hại | Phản ứng thích ứng có trách nhiệm |
| --- | --- |
| Gắn nhãn Done khi kiểm thử còn đỏ | Minh bạch phần chưa đạt DoD và ưu tiên khắc phục |
| Bỏ phân quyền hoặc kiểm tra dữ liệu để giao nhanh | Giữ các điều kiện chất lượng cần thiết |
| Cố làm toàn bộ scope dù không còn khả thi | Thương lượng phạm vi, giao lát cắt có giá trị đã Done |
| Mở thêm nhiều việc để mọi người bận | Giảm WIP, cùng hoàn tất công việc gần Done |
| Chỉ báo % task hoặc story point | Báo bằng Increment thực tế, rủi ro và bước tiếp theo |
| Tuyên bố tính năng “release-ready” vì đã merge | Phân biệt Done, điều kiện phát hành và người dùng đã tiếp cận |
| Che thiếu sót để tránh cuộc trao đổi khó | Nêu bằng chứng và đề xuất quyết định đúng thẩm quyền |
| Dồn kiểm thử sang Sprint sau | Tích hợp, review và kiểm chứng liên tục theo DoD |
| Coi deadline là thất bại cá nhân | Xem lại ước lượng, WIP, phụ thuộc và dòng công việc để cải tiến |

**Ghi nhớ:** **Definition of Done là ngưỡng chất lượng của Increment, không phải công tắc có thể tắt khi sát hạn.** Trong Scrum, chất lượng không được giảm trong Sprint; phạm vi có thể được làm rõ và thương lượng với Product Owner khi học thêm. Kết hợp user story nhỏ, backlog theo giá trị, CI, kiểm thử, refactoring và quản lý WIP giúp nhóm **hoàn tất ít hơn nhưng đúng hơn**, phát hiện rủi ro sớm và giao phần tăng dần đáng tin cậy. Khi một phần chưa đạt DoD, minh bạch điều đó và chọn kế hoạch tiếp theo có trách nhiệm mới thực sự là cách làm Agile thích ứng và bền vững.
