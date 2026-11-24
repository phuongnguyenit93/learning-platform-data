# Cân bằng khả năng thích ứng với tính kỷ luật trong Agile

> **Trọng tâm:** Agile giúp nhóm phát triển phần mềm điều chỉnh hướng đi theo phản hồi thực tế, nhưng chỉ tạo ra giá trị bền vững khi việc thay đổi đi cùng mục tiêu rõ ràng, tiêu chuẩn chất lượng, nhịp phản hồi và trách nhiệm minh bạch.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **thích ứng** và **kỷ luật** bổ trợ cho nhau trong phát triển phần mềm Agile.
2. Phân biệt việc thay đổi dựa trên bằng chứng với việc thay đổi tùy hứng, liên tục phá vỡ cam kết.
3. Thiết lập những nguyên tắc làm việc tối thiểu cho **user story, backlog, Scrum, Kanban, XP** mà vẫn giữ khả năng đáp ứng thay đổi.
4. Đánh giá một yêu cầu mới theo **giá trị, mức khẩn cấp, rủi ro, chi phí thay đổi và tác động lên mục tiêu hiện tại**.
5. Dùng phản hồi sớm và số liệu dòng công việc để cải tiến quy trình thay vì đánh giá con người bằng một con số đơn lẻ.

## 2. Nghịch lý tưởng tượng: Agile có phải là làm việc ít quy tắc hơn?

Hãy xét một nhóm đang phát triển tính năng thanh toán. Khách hàng vừa phản hồi rằng bước xác nhận quá phức tạp. Nhóm muốn sửa ngay để giảm tỷ lệ bỏ dở. Trong khi đó, tính năng phải vượt qua kiểm thử, xử lý lỗi giao dịch, kiểm soát bảo mật và được đội vận hành theo dõi sau khi triển khai.

Nếu nhóm **cứng nhắc**, họ có thể giữ nguyên kế hoạch nhiều tháng dù người dùng đã chỉ ra vấn đề. Sản phẩm được giao đúng một bản kế hoạch nhưng không còn phù hợp. Nếu nhóm **tùy tiện**, họ có thể sửa yêu cầu hằng ngày, bỏ kiểm thử và triển khai gấp; khả năng đáp ứng nhanh trước mắt lại tạo lỗi, nợ kỹ thuật và mất niềm tin.

Agile đề xuất một hướng thực tế hơn: **giữ ổn định mục tiêu và những nguyên tắc bảo đảm chất lượng, đồng thời linh hoạt về cách đạt mục tiêu và thứ tự công việc dựa trên điều học được**.

Hai khái niệm cần phân biệt:

| Khía cạnh | Thích ứng (adaptability) | Kỷ luật (discipline) |
|---|---|---|
| Câu hỏi chính | “Thông tin mới buộc ta điều chỉnh điều gì?” | “Điều gì phải đúng trước khi ta coi công việc đã hoàn thành?” |
| Hành vi điển hình | Kiểm tra giả thuyết, tái ưu tiên backlog, điều chỉnh phạm vi | Nêu mục tiêu, giới hạn công việc đang làm, kiểm thử, minh bạch tiến độ |
| Nguồn bằng chứng | Phản hồi người dùng, kết quả thử nghiệm, thay đổi thị trường | Tiêu chí chấp nhận, Definition of Done, chính sách luồng, dữ liệu chất lượng |
| Khi thiếu vắng | Nhóm có thể giao đúng kế hoạch nhưng sai nhu cầu | Nhóm có thể đổi rất nhanh nhưng không ổn định và khó dự đoán |
| Cách kết hợp | Thay đổi quyết định khi có thông tin mới | Giữ chuẩn chất lượng và công khai tác động của quyết định mới |

**Kỷ luật Agile không đồng nghĩa với nhiều cuộc họp hoặc biểu mẫu.** Đó là những thỏa thuận làm việc giúp nhóm phối hợp, học hỏi và giao phần mềm sử dụng được một cách lặp lại.

## 3. Giá trị Agile: linh hoạt có nguyên tắc

Tuyên ngôn Agile nêu bốn sự ưu tiên:

1. **Cá nhân và tương tác** hơn là quy trình và công cụ.
2. **Phần mềm hoạt động được** hơn là tài liệu toàn diện.
3. **Cộng tác với khách hàng** hơn là thương lượng hợp đồng.
4. **Phản hồi trước thay đổi** hơn là bám sát kế hoạch.

Những yếu tố ở vế sau **vẫn có giá trị**. Agile nhấn mạnh vế trước hơn khi phải đưa ra quyết định. Vì vậy, một nhóm Agile vẫn cần tài liệu vừa đủ để vận hành, vẫn lập kế hoạch, vẫn tôn trọng ràng buộc hợp đồng và vẫn dùng công cụ.

Các nguyên tắc Agile liên quan trực tiếp đến bài toán cân bằng bao gồm:

- **Giao giá trị sớm và thường xuyên:** chia giải pháp thành các phần có thể kiểm chứng, thay vì đợi đến cuối dự án mới biết có đúng nhu cầu hay không.
- **Đón nhận thay đổi, kể cả ở giai đoạn muộn:** cân nhắc thay đổi vì lợi ích của khách hàng, nhưng phải làm rõ chi phí và hệ quả.
- **Hợp tác liên tục giữa người làm nghiệp vụ và người xây dựng:** giảm thời gian chờ xác nhận, tránh quyết định dựa trên giả định không được kiểm tra.
- **Duy trì nhịp phát triển bền vững:** không lấy việc làm thêm giờ kéo dài làm cơ chế mặc định để hấp thụ mọi yêu cầu.
- **Chú trọng sự xuất sắc về kỹ thuật và thiết kế tốt:** kiểm thử và thiết kế có khả năng sửa đổi giúp nhóm thay đổi nhanh hơn ở các vòng sau.
- **Đơn giản hóa:** giảm công việc không cần thiết, đồng thời giữ những biện pháp thực sự giảm rủi ro.
- **Thường xuyên nhìn lại và điều chỉnh cách làm:** chính quy trình cũng phải được cải tiến dựa trên kết quả.

Từ đó rút ra một quy tắc hữu ích: **linh hoạt với giả thuyết về sản phẩm; kiên định với tính minh bạch, chất lượng, an toàn và khả năng học hỏi**.

## 4. Những phần nên ổn định và những phần có thể điều chỉnh

Không phải mọi quyết định đều nên được thay đổi với cùng tốc độ. Hãy phân tầng:

| Đối tượng | Mức ổn định thường mong muốn | Ví dụ điều chỉnh hợp lý |
|---|---|---|
| **Mục tiêu sản phẩm và giá trị cần tạo** | Tương đối ổn định, được xem xét lại khi có bằng chứng quan trọng | Chuyển trọng tâm từ tăng lượt đăng ký sang tăng tỷ lệ kích hoạt khi dữ liệu cho thấy nút thắt |
| **Mục tiêu của vòng làm việc hiện tại** | Bảo vệ tính tập trung trong khoảng thời gian ngắn | Đổi cách triển khai, thương lượng lại phạm vi nếu vẫn giữ được mục tiêu |
| **Thứ tự và chi tiết Product Backlog** | Có thể cập nhật thường xuyên | Đưa lỗi ảnh hưởng nhiều khách hàng lên trước một tính năng ít cấp bách |
| **Thiết kế và giải pháp kỹ thuật** | Có thể tiến hóa bằng thử nghiệm và refactoring | Thay API hoặc luồng giao diện sau kiểm chứng, có kiểm thử hồi quy |
| **Chuẩn hoàn thành, bảo mật và an toàn dữ liệu** | Phải được thực thi nhất quán; thay đổi bằng quyết định có kiểm soát | Bổ sung kiểm tra lỗ hổng mới vào pipeline; không bỏ kiểm thử để đạt hạn |
| **Nhịp họp và chính sách phối hợp** | Có tính dự đoán, nhưng nên cải tiến định kỳ | Rút ngắn họp không hiệu quả, thay chính sách giới hạn WIP sau retrospective |

Một thay đổi quan trọng vẫn có thể làm nhóm cần xem xét lại mục tiêu. Điểm cốt lõi là **ra quyết định công khai dựa trên tác động**, thay vì để nhiều yêu cầu chen ngang mà không ai chịu trách nhiệm sắp xếp.

## 5. Biến nguyên tắc thành thực hành hằng ngày

### 5.1. Nêu mục tiêu trước khi nhận thêm công việc

Trước một đợt triển khai hoặc Sprint, nhóm cần biết **kết quả mong muốn**. Ví dụ: “Người dùng có thể tự đổi địa chỉ giao hàng trước khi đơn được đóng gói, với ít yêu cầu hỗ trợ hơn”. Đây là mục tiêu có thể kiểm chứng, khác với việc chỉ liệt kê “làm API, làm UI, sửa database”.

Mục tiêu không thay thế danh sách việc. Nó là tiêu chí để trả lời: **yêu cầu mới có giúp đạt kết quả này không?** Khi xuất hiện lựa chọn khó, người phụ trách sản phẩm và nhóm phát triển phải cùng làm rõ lợi ích, rủi ro và phần công việc cần đổi.

### 5.2. Dùng user story và tiêu chí chấp nhận để giảm hiểu lầm

Một user story thường mô tả người dùng, nhu cầu và lợi ích:

> **Là** người mua hàng, **tôi muốn** sửa địa chỉ giao hàng trước khi đơn được đóng gói, **để** tránh giao nhầm mà không cần gọi hỗ trợ.

User story là lời mời thảo luận, không phải bản đặc tả đầy đủ. Nhóm có thể bắt đầu bằng các điều kiện chấp nhận cụ thể:

~~~gherkin
Kịch bản: Đổi địa chỉ khi đơn chưa đóng gói
  Cho trước đơn hàng đang ở trạng thái "Chờ đóng gói"
  Khi người mua cập nhật địa chỉ hợp lệ
  Thì hệ thống lưu địa chỉ mới
  Và hiển thị địa chỉ mới trong chi tiết đơn hàng

Kịch bản: Không cho sửa khi đơn đã bàn giao vận chuyển
  Cho trước đơn hàng đang ở trạng thái "Đã bàn giao vận chuyển"
  Khi người mua yêu cầu đổi địa chỉ
  Thì hệ thống không thay đổi địa chỉ giao hàng
  Và giải thích cách liên hệ bộ phận hỗ trợ
~~~

Nếu người dùng phản hồi rằng nhiều đơn đã bị khóa quá sớm, nhóm có cơ sở để thảo luận lại điều kiện nghiệp vụ. Nhưng sau mỗi lần thay đổi, cần cập nhật tiêu chí chấp nhận và kiểm thử tương ứng. **Càng muốn học nhanh từ phản hồi, nhóm càng cần một cách rõ ràng để xác nhận điều vừa học.**

### 5.3. Quản lý backlog như danh sách lựa chọn, không phải lời hứa cố định

Product Backlog là tập hợp công việc được sắp xếp và điều chỉnh khi sản phẩm phát triển. Một mục mới không đương nhiên được làm ngay chỉ vì có người đề xuất.

Khi sắp xếp thứ tự, có thể cân nhắc:

- **Giá trị và đối tượng hưởng lợi:** ai gặp vấn đề, mức ảnh hưởng ra sao?
- **Mức khẩn cấp:** cần xử lý ngay vì sự cố, quy định hoặc cơ hội có thời hạn hay không?
- **Rủi ro và sự bất định:** cần thử nghiệm nhỏ để học trước khi đầu tư lớn không?
- **Chi phí và sự phụ thuộc:** thay đổi có kéo theo thiết kế, dữ liệu, kiểm thử hoặc nhóm khác không?
- **Sức chứa thực tế của nhóm:** thêm việc này sẽ phải hoãn, chia nhỏ hoặc bỏ việc nào?

Mô tả đủ rõ những mục sắp thực hiện; những mục xa hơn có thể giữ ở mức khái quát. Cách này tránh tốn công lập đặc tả chi tiết cho các giả thuyết còn dễ thay đổi.

### 5.4. Dùng Definition of Done để giữ chất lượng ổn định

**Definition of Done (DoD)** là mô tả chung về trạng thái mà một Increment phải đạt để được coi là hoàn thành. Ví dụ, với nhóm phát triển ứng dụng web, thỏa thuận có thể gồm:

~~~text
Definition of Done - ví dụ của nhóm
[ ] Tiêu chí chấp nhận đã được kiểm chứng
[ ] Code được review theo chính sách của nhóm
[ ] Kiểm thử tự động liên quan chạy thành công
[ ] Tích hợp vào nhánh chung, build và pipeline đạt
[ ] Không còn lỗi nghiêm trọng đã biết trong phạm vi thay đổi
[ ] Các yêu cầu bảo mật, quyền riêng tư và log liên quan được đáp ứng
[ ] Tài liệu vận hành hoặc hướng dẫn người dùng được cập nhật khi cần
~~~

Đây là **ví dụ tùy biến**, không phải danh sách chính thức áp dụng cho mọi nhóm. Từng sản phẩm cần quy định DoD phù hợp với rủi ro và chuẩn của tổ chức. Nếu một mục chưa đạt DoD, không nên trình bày nó như phần giá trị đã hoàn thành. Việc cần triển khai khẩn cấp có thể dùng quy trình xử lý sự cố riêng, nhưng vẫn cần xác định và chấp nhận rủi ro một cách minh bạch.

**Definition of Ready (DoR)**, nếu nhóm chọn sử dụng, chỉ nên là thỏa thuận nhẹ về thông tin cần có trước khi bắt đầu. Không nên biến DoR thành cổng phê duyệt cứng nhắc khiến mọi khám phá phải hoàn thành trước khi nhóm được phép làm việc.

### 5.5. Xây dựng khả năng thay đổi bằng kỷ luật kỹ thuật

Việc sửa mã nhanh ở tuần này không có nghĩa là nhóm có thể tiếp tục sửa nhanh trong ba tháng tới. Khả năng thích ứng lâu dài đến từ những thực hành như:

- **Tích hợp liên tục (CI):** tích hợp và kiểm tra thay đổi thường xuyên để phát hiện xung đột sớm.
- **Kiểm thử tự động phù hợp:** kiểm thử đơn vị, tích hợp và hành vi trọng yếu nhằm giảm chi phí kiểm chứng khi sửa yêu cầu.
- **Refactoring:** cải thiện cấu trúc mã mà vẫn giữ hành vi quan sát được, để chi phí sửa đổi không tăng mãi.
- **Phát hành từng phần:** sử dụng triển khai theo đợt, feature flag hoặc rollback khi phù hợp với kiến trúc và rủi ro.
- **Quan sát sau phát hành:** theo dõi lỗi, hiệu năng và tín hiệu trải nghiệm để xác minh giả thuyết.

Không nhất thiết áp dụng mọi kỹ thuật ở cùng mức độ. Ví dụ, một dịch vụ thanh toán cần kiểm soát dữ liệu và hồi quy chặt hơn một thử nghiệm giao diện ít rủi ro. Tuy nhiên, **sức ép tiến độ không tự động là lý do để hạ chuẩn an toàn**.

## 6. Scrum, Kanban và XP cân bằng hai phía như thế nào?

Ba cách tiếp cận có thể bổ trợ nhau, dù không phải là ba biến thể tương đương.

| Cách tiếp cận | Nguồn kỷ luật nổi bật | Cơ chế thích ứng | Tình huống áp dụng |
|---|---|---|---|
| **Scrum** | Vai trò/trách nhiệm rõ; Sprint có thời lượng cố định; Sprint Goal; các sự kiện kiểm tra và thích ứng; Definition of Done | Kiểm tra Increment ở Sprint Review, điều chỉnh Product Backlog; cải tiến tại Sprint Retrospective | Nhóm cần phối hợp để xây dựng sản phẩm phức tạp qua các Increment |
| **Kanban** | Trực quan hóa công việc; kiểm soát WIP; chính sách luồng minh bạch; theo dõi thời gian xử lý | Điều chỉnh luồng theo điểm tắc, tuổi công việc và dữ liệu thời gian hoàn thành | Công việc đến liên tục: bảo trì, hỗ trợ, vận hành, hoặc phát triển có biến động |
| **Extreme Programming (XP)** | TDD, lập trình cặp khi phù hợp, tích hợp liên tục, refactoring, thiết kế đơn giản | Phản hồi kỹ thuật và nghiệp vụ thường xuyên; thay đổi thiết kế an toàn nhờ kiểm thử | Nhóm cần khả năng thay đổi mã liên tục với chất lượng cao |

### Với Scrum: bảo vệ Sprint Goal, thương lượng phạm vi

Sprint là khoảng thời gian cố định, không quá một tháng. Trong Sprint, nhóm vẫn học hỏi và điều chỉnh. Theo Scrum Guide, **không đưa ra thay đổi gây nguy hại cho Sprint Goal**, chất lượng không được suy giảm, và phạm vi có thể được làm rõ hoặc thương lượng lại với Product Owner khi hiểu biết tăng lên.

Điều này không có nghĩa mọi yêu cầu mới đều phải đợi đến Sprint sau. Nhóm cần đánh giá: yêu cầu có giúp Sprint Goal không, có khả thi không, và phải đổi phạm vi thế nào? Nếu Sprint Goal trở nên lỗi thời, Product Owner có quyền hủy Sprint theo Scrum. Đây là quyết định hiếm khi cần dùng, không phải cách quản lý yêu cầu mỗi ngày.

### Với Kanban: cho phép tái ưu tiên nhưng kiểm soát lượng việc đang làm

Một bảng đơn giản có thể có các cột **Cần làm → Đang phát triển → Đang kiểm thử → Hoàn thành**. Giả sử nhóm đặt giới hạn **WIP = 3** cho “Đang phát triển”. Khi ba việc đã ở cột này, việc mới không nên tự động được kéo vào mà không xử lý tắc nghẽn hoặc quyết định rõ việc nào được tạm dừng.

Giới hạn WIP là chính sách vận hành nhóm có thể điều chỉnh theo bằng chứng. Một công việc khẩn cấp có thể có quy tắc ưu tiên riêng, nhưng vẫn phải tính tác động lên các việc đang diễn ra. Kanban giúp hiển thị **chi phí của việc liên tục chuyển ngữ cảnh**.

### Với XP: giữ mã dễ thay đổi

XP nhấn mạnh các vòng phản hồi ngắn và kỷ luật kỹ thuật. Ví dụ, khi sửa quy tắc khóa địa chỉ giao hàng, nhóm viết hoặc cập nhật kiểm thử thể hiện hành vi mong muốn, thay đổi mã, chạy lại kiểm thử, rồi refactor khi cần. Nhờ đó yêu cầu có thể đổi mà nhóm vẫn kiểm soát được lỗi hồi quy.

Một nhóm có thể sử dụng **Scrum để phối hợp**, **thực hành Kanban để quản lý dòng công việc**, và **kỹ thuật XP để giữ chất lượng mã**, miễn là các chính sách nhất quán và có mục đích.

## 7. Quy trình xử lý yêu cầu thay đổi trong thực tế

Khi nhận phản hồi hoặc yêu cầu mới, áp dụng chu trình sau:

1. **Ghi nhận tín hiệu:** yêu cầu đến từ ai, bằng chứng nào hỗ trợ, hậu quả nếu chưa làm là gì?
2. **So với mục tiêu hiện tại:** thay đổi có góp phần vào mục tiêu sản phẩm hoặc mục tiêu của vòng đang làm không?
3. **Ước lượng tác động vừa đủ:** công việc kỹ thuật, kiểm thử, an toàn, phụ thuộc và thời gian xử lý. Với điểm chưa rõ, cân nhắc thử nghiệm nhỏ trước.
4. **Quyết định và nêu đánh đổi:** thực hiện ngay, đưa lên đầu backlog, chia nhỏ thử nghiệm, hoãn hay từ chối; nói rõ phần công việc bị ảnh hưởng.
5. **Cập nhật nguồn thông tin chung:** backlog, tiêu chí chấp nhận, chính sách luồng hoặc kế hoạch phát hành tùy theo quyết định.
6. **Đo kết quả và học tiếp:** sau khi giao, kiểm tra hiệu quả thật, lỗi phát sinh và thời gian hoàn thành.

Một ma trận quyết định đơn giản:

| Loại yêu cầu | Hướng xử lý gợi ý | Kỷ luật cần giữ |
|---|---|---|
| Lỗi gây mất dữ liệu hoặc sự cố nghiêm trọng | Kích hoạt quy trình ứng cứu, tái ưu tiên ngay và thông báo tác động | Truy vết, kiểm chứng bản sửa, giám sát sau khắc phục |
| Thông tin mới giúp đạt mục tiêu hiện tại tốt hơn | Thảo luận với người chịu trách nhiệm sản phẩm và nhóm; điều chỉnh phạm vi nếu cần | Giữ mục tiêu, cập nhật acceptance criteria và DoD |
| Ý tưởng mới có giá trị nhưng chưa cấp bách | Ghi và sắp xếp vào backlog để đánh giá ở điểm thích hợp | Không âm thầm chen việc làm tăng WIP |
| Yêu cầu chưa rõ giá trị hoặc còn rủi ro cao | Tạo hoạt động khám phá/thử nghiệm nhỏ, giới hạn thời gian | Đặt câu hỏi kiểm chứng và điều kiện dừng |
| Đề xuất bỏ bước kiểm thử để kịp hạn | Thu nhỏ phạm vi, điều chỉnh thời điểm hoặc thay cách phát hành an toàn | Không che giấu phần chưa đạt chuẩn chất lượng |

Đây là gợi ý ra quyết định, không phải thuật toán máy móc. Đội ngũ có trách nhiệm cân đối chính sách tổ chức, nghĩa vụ pháp lý và mức rủi ro cụ thể.

## 8. Tình huống xuyên suốt: thay đổi giữa Sprint

**Bối cảnh:** Nhóm phát triển chức năng đổi địa chỉ giao hàng, sử dụng Sprint hai tuần. Sprint Goal là “Người mua có thể tự đổi địa chỉ cho đơn chưa bước sang quy trình giao vận”. Nhóm đã hoàn tất API nền tảng và đang làm giao diện.

**Ngày thứ năm**, bộ phận chăm sóc khách hàng phản hồi: nhiều đơn chuyển sang trạng thái “Đang đóng gói” rất sớm, nhưng trên thực tế vẫn có thể đổi địa chỉ trước lúc dán nhãn. Product Owner đề xuất nới quy tắc khóa địa chỉ.

Nhóm có ba lựa chọn:

| Phương án | Lợi ích | Rủi ro/đánh đổi |
|---|---|---|
| A. Giữ nguyên đặc tả cũ, không thảo luận | Dễ bám danh sách đã lên kế hoạch | Có thể giao tính năng ít hữu ích; bỏ qua phản hồi sớm |
| B. Sửa toàn bộ luồng ngay, bỏ kiểm thử để kịp Sprint | Đáp ứng yêu cầu nhìn thấy trước mắt | Có thể đổi sai địa chỉ sau in nhãn; tăng lỗi và rủi ro vận hành |
| C. Làm rõ ranh giới nghiệp vụ, kiểm tra tác động, chọn lát cắt an toàn | Có cơ hội tăng giá trị mà vẫn kiểm chứng được | Có thể phải bỏ bớt phạm vi phụ hoặc chuyển một phần việc sang sau |

**Nhóm chọn C.** Product Owner cùng chuyên gia vận hành xác định mốc thật sự: “Đơn chưa phát hành nhãn vận chuyển”. Nhóm bổ sung tiêu chí chấp nhận về thời điểm khóa, xử lý tình huống đồng thời và thông báo rõ khi cập nhật thất bại. Sau khi đánh giá rủi ro, nhóm giữ Sprint Goal, đổi một phần công việc giao diện ít quan trọng sang backlog để dành thời gian cho kiểm thử tích hợp. Ở Sprint Review, nhóm trình diễn luồng thực tế cho các bên liên quan và kiểm tra xem chính sách mới có giảm yêu cầu hỗ trợ hay không.

**Điều cần học:** giá trị của sự thay đổi chỉ được khẳng định khi hành vi đã được kiểm chứng. Việc đưa một thay đổi vào Sprint không tự làm nhóm “Agile hơn”; khả năng giải thích quyết định và giao Increment đạt chuẩn mới là bằng chứng rõ ràng hơn.

## 9. Đo lường để nhận biết nhóm có đang mất cân bằng không

Không nên dùng một chỉ số để kết luận nhóm “nhanh” hay “kỷ luật”. Nên xem kết hợp **giá trị sản phẩm, dòng công việc, chất lượng và tính bền vững**.

| Chỉ số/tín hiệu | Câu hỏi nó giúp trả lời | Cách dùng thận trọng |
|---|---|---|
| **Lead time** | Từ lúc công việc được yêu cầu hoặc cam kết đến khi hoàn tất mất bao lâu? | Phải định nghĩa điểm bắt đầu và kết thúc thống nhất |
| **Cycle time** | Sau khi bắt đầu thực hiện, một hạng mục mất bao lâu để hoàn thành? | Xem phân phối và xu hướng, không chỉ trung bình |
| **Throughput** | Nhóm hoàn thành bao nhiêu hạng mục trong một khoảng thời gian? | Kích thước hạng mục phải được hiểu trong bối cảnh |
| **WIP** | Có bao nhiêu việc đang diễn ra cùng lúc? | WIP cao kéo dài có thể báo hiệu chuyển ngữ cảnh hoặc tắc nghẽn |
| **Work item age** | Việc đang mở đã nằm trong luồng bao lâu? | Hữu ích để can thiệp sớm trước khi việc trễ quá lâu |
| **Lỗi lọt ra môi trường sử dụng** | Chất lượng có giảm khi nhóm chạy nhanh hơn không? | Xem mức nghiêm trọng, khả năng phát hiện và nguyên nhân |
| **Kết quả sản phẩm** | Tính năng có cải thiện hành vi hoặc vấn đề người dùng không? | Đặt mục tiêu trước khi phát hành và tránh suy diễn nhân quả quá mức |
| **Phản hồi của nhóm** | Nhịp làm việc có bền vững, rõ trách nhiệm, ít gián đoạn không? | Dùng cho cải tiến hệ thống, không quy lỗi cho cá nhân |

**Ví dụ:** Trong hai tuần, nhóm hoàn tất tám user story nhưng có mười bốn việc đang làm dở và ba lỗi nghiêm trọng sau triển khai. Số hạng mục hoàn tất không đủ để khẳng định nhóm đang tốt lên. Một hành động cải tiến hợp lý có thể là giảm WIP, chia nhỏ user story, củng cố kiểm thử hồi quy và quan sát xu hướng ở những vòng tiếp theo.

Các chỉ số luồng có ý nghĩa khi được đo nhất quán trên cùng định nghĩa. Chúng dùng để phát hiện vấn đề và trao đổi về dự báo, **không nên dùng riêng lẻ làm bảng xếp hạng năng suất cá nhân**.

## 10. Những cách hiểu sai thường gặp

| Cách hiểu sai | Hệ quả | Cách điều chỉnh |
|---|---|---|
| “Agile là không cần kế hoạch.” | Nhóm thiếu định hướng và khó giải thích đánh đổi | Lập kế hoạch theo mức chi tiết phù hợp, cập nhật khi có thông tin mới |
| “Khách hàng yêu cầu gì cũng phải làm ngay.” | Backlog mất ưu tiên, WIP tăng, cam kết không còn ý nghĩa | Phân loại mức khẩn cấp, quyết định rõ công việc nào phải đổi |
| “Có Scrum là đủ bảo đảm chất lượng.” | Vẫn có thể giao mã lỗi hoặc khó bảo trì | Định nghĩa DoD và đầu tư vào kiểm thử, CI, refactoring |
| “Đã vào Sprint thì không được thay đổi.” | Phản hồi có giá trị bị bỏ qua | Bảo vệ Sprint Goal, nhưng điều chỉnh phạm vi khi cần và phù hợp |
| “Việc nào cũng phải có thật nhiều tài liệu trước khi bắt đầu.” | Thời gian chờ kéo dài; nhiều tài liệu nhanh lỗi thời | Chuẩn bị thông tin vừa đủ cho quyết định và rủi ro của từng việc |
| “Velocity hoặc số ticket đóng là năng suất cá nhân.” | Khuyến khích chia việc để đạt điểm hoặc tránh việc khó | Đánh giá khả năng đạt mục tiêu và cải thiện toàn bộ luồng |
| “Retrospective là buổi nêu lỗi của từng người.” | Thành viên ngại chia sẻ; vấn đề hệ thống bị che khuất | Chọn cải tiến nhỏ, có người theo dõi, đo lại kết quả |

## 11. Mẫu thỏa thuận làm việc tối thiểu cho một nhóm

Một nhóm mới có thể bắt đầu với thỏa thuận ngắn sau rồi điều chỉnh qua retrospective:

1. **Mục tiêu chung:** mọi việc ưu tiên cao có liên hệ rõ với vấn đề người dùng, mục tiêu sản phẩm hoặc nghĩa vụ vận hành.
2. **Nguồn công việc duy nhất:** backlog/bảng công việc được cập nhật, có người chịu trách nhiệm quyết định ưu tiên.
3. **Chính sách nhận việc:** làm rõ tiêu chí chấp nhận và phụ thuộc trước khi kéo việc vào; giới hạn WIP theo năng lực thực tế.
4. **Chuẩn hoàn thành:** tất cả Increment phải đáp ứng DoD và ràng buộc an toàn áp dụng.
5. **Kênh xử lý khẩn cấp:** định nghĩa thế nào là khẩn cấp, ai quyết định, cách thông báo tác động và hậu kiểm.
6. **Nhịp phản hồi:** trình diễn sản phẩm sử dụng được, thu thập phản hồi từ người liên quan và cải tiến cách làm định kỳ.
7. **Dữ liệu để học:** theo dõi một vài chỉ số dòng công việc, chất lượng và kết quả sản phẩm trước khi bổ sung thêm số đo.

Đừng cố tối ưu mọi quy tắc ngay từ đầu. Sau mỗi vòng làm việc, hãy hỏi: **quy tắc nào đang giảm rủi ro, quy tắc nào đang tạo thời gian chờ, và ta có bằng chứng gì để thay đổi nó?**

## 12. Bài tập vận dụng

### Bài tập 1 — Quyết định với yêu cầu chen ngang

Nhóm có Sprint Goal “Hoàn tất luồng đăng ký để người dùng mới kích hoạt tài khoản”. Giữa Sprint, một bên liên quan muốn thêm trang thống kê dành cho quản trị viên, dự kiến mất ba ngày. Cùng lúc, thử nghiệm phát hiện 20% email kích hoạt không đến người dùng.

Hãy trả lời:

1. Việc nào cần xem xét ưu tiên trước? Vì sao?
2. Bạn sẽ trao đổi với Product Owner và nhóm phát triển về tác động lên Sprint Goal ra sao?
3. Những tiêu chí chất lượng nào cần giữ trước khi phát hành?

**Gợi ý:** lỗi email ảnh hưởng trực tiếp mục tiêu kích hoạt; trang quản trị có thể đưa vào Product Backlog nếu không cấp bách. Cần đánh giá nguyên nhân, mức độ nghiêm trọng và sửa/kiểm chứng luồng email; không được giả định cứ “20%” là có thể sửa xong trong một ngày.

### Bài tập 2 — Tìm điểm mất cân bằng

Bảng công việc có 18 thẻ “Đang làm”, 3 thẻ “Đang kiểm thử” và 2 thẻ “Hoàn thành” trong tuần. Thành viên liên tục chuyển giữa các việc do yêu cầu mới.

Hãy đề xuất **hai thay đổi nhỏ** có thể thực hiện trong tuần tiếp theo và **hai dấu hiệu** để kiểm tra hiệu quả.

**Gợi ý:** cân nhắc giới hạn WIP ở một công đoạn, ưu tiên hoàn tất việc đã bắt đầu, thống nhất cách xử lý yêu cầu khẩn. Theo dõi tuổi hạng mục đang mở, cycle time hoặc số việc hoàn thành, kết hợp số lỗi và phản hồi của nhóm. Không suy luận chính xác tốc độ chỉ từ số thẻ của một tuần.

### Bài tập 3 — Tự kiểm tra quyết định

Với một tính năng bạn từng phát triển, hãy ghi ngắn gọn:

- Mục tiêu và giả thuyết ban đầu.
- Phản hồi nào khiến bạn muốn đổi phạm vi hoặc giải pháp.
- Ràng buộc nào không thể bỏ qua (chẳng hạn: bảo mật, dữ liệu, khả năng truy vết, DoD).
- Quyết định cuối cùng, phần đánh đổi và kết quả sẽ đo sau khi phát hành.

Nếu không trả lời được mục “đo kết quả”, rất có thể thay đổi của bạn mới chỉ là **ý kiến về giải pháp** mà chưa phải một giả thuyết có thể kiểm chứng.

## 13. Tổng kết

**Khả năng thích ứng** là điều chỉnh sản phẩm và cách làm khi xuất hiện thông tin mới có giá trị. **Tính kỷ luật** là cơ chế làm cho sự điều chỉnh đó có trách nhiệm, đo lường được và không phá hủy khả năng giao hàng lâu dài.

Một nhóm Agile trưởng thành thường:

- Bám **mục tiêu và kết quả người dùng** hơn là bám cứng một danh sách tác vụ.
- Giữ **backlog và phạm vi đủ linh hoạt**, đồng thời duy trì **Definition of Done** và kiểm soát rủi ro.
- Dùng **Scrum, Kanban hoặc XP** vì vấn đề cụ thể chúng giúp giải quyết, không chỉ vì tên gọi.
- Giảm thời gian nhận phản hồi bằng những Increment nhỏ, kiểm thử được và có thể phát hành an toàn.
- Cải tiến dựa trên dữ liệu dòng công việc, chất lượng và hiệu quả sản phẩm, thay vì chỉ tăng tốc độ đóng việc.

**Câu hỏi ghi nhớ:** “Nếu ngày mai có thông tin mới quan trọng, nhóm có thể thay đổi quyết định nhanh đến đâu mà vẫn biết chính xác điều gì đã được kiểm chứng, điều gì đang rủi ro và vì sao?”

### Tài liệu tham khảo gợi ý

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — bốn giá trị và các nguyên tắc Agile.
- [The Scrum Guide](https://scrumguides.org/) — mục tiêu Sprint, các sự kiện, Product Backlog, Increment và Definition of Done.
- [The Kanban Guide](https://kanbanguides.org/) — nguyên tắc quản lý luồng và các phép đo của Kanban.
- [Extreme Programming — Agile Alliance](https://agilealliance.org/glossary/xp/) — khái niệm và các thực hành XP.
