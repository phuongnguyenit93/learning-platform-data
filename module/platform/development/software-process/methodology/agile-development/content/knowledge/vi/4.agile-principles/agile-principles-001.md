# Nguyên tắc Agile 1: Ưu tiên sự hài lòng của khách hàng bằng phần mềm có giá trị được bàn giao sớm và liên tục

Trong **AGILE_DEVELOPMENT**, nền tảng của việc phát triển phần mềm thích ứng là hiểu **mình đang tạo giá trị cho ai**, **làm sao biết giá trị đó đã xuất hiện** và **khi nào người nhận có thể sử dụng hoặc kiểm chứng nó**. Nguyên tắc Agile đầu tiên diễn đạt ưu tiên này rất rõ:

> **Ưu tiên cao nhất của chúng ta là làm hài lòng khách hàng thông qua việc bàn giao sớm và liên tục phần mềm có giá trị.**

Đây là cách diễn đạt tiếng Việt của nguyên tắc số 1 trong 12 nguyên tắc phía sau Agile Manifesto: *“Our highest priority is to satisfy the customer through early and continuous delivery of valuable software.”*

Nguyên tắc không yêu cầu nhóm “làm thật nhiều chức năng thật nhanh” hoặc liên tục đưa mã chưa đủ chất lượng ra sử dụng. Nó yêu cầu nhóm tìm ra điều có ích cho khách hàng, tạo ra phần mềm hoạt động được, đưa phần mềm đến người có thể đánh giá, học từ kết quả và tiếp tục giao giá trị. Bài học này đi sâu vào nguyên tắc thứ nhất; user story, backlog, Scrum, Kanban, XP và các chỉ số dòng công việc được dùng như **phương tiện để thực hiện nguyên tắc**, không phải mục tiêu thay thế sự hài lòng của khách hàng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích bốn thành tố của nguyên tắc: **khách hàng hài lòng**, **phần mềm có giá trị**, **bàn giao sớm**, **bàn giao liên tục**.
2. Phân biệt **đầu ra** (chức năng được xây dựng) với **kết quả** (vấn đề của người dùng được giải quyết) và nhận diện những giả định cần kiểm chứng.
3. Chia một yêu cầu lớn thành các **lát cắt giá trị** có thể kiểm thử, dùng thử và học hỏi theo từng vòng.
4. Phác thảo một chu trình giao nhận gồm mục tiêu, backlog, điều kiện hoàn tất, kiểm thử, bàn giao, phản hồi và điều chỉnh.
5. Chọn tín hiệu phù hợp để đánh giá giá trị, sự hài lòng và tốc độ phản hồi mà không biến số lần phát hành hay số lượng story thành mục tiêu tự thân.

## 2. Hiểu chính xác nguyên tắc thứ nhất

### 2.1. “Khách hàng” là ai?

Trong một sản phẩm, **người trả tiền**, **người quyết định mua**, **người sử dụng**, **người vận hành** và **người chịu tác động** có thể là những người khác nhau. Nhóm cần xác định vai trò của họ trước khi đặt mục tiêu “làm hài lòng khách hàng”.

Ví dụ với ứng dụng đặt lịch bảo dưỡng xe:

| Bên liên quan | Mong muốn tiêu biểu | Cách kiểm chứng |
| --- | --- | --- |
| Chủ gara (người đặt hàng sản phẩm) | Giảm cuộc gọi đặt lịch, sắp xếp khung giờ hiệu quả | Thời gian nhân viên dành cho việc đặt lịch; số lịch cần nhập lại |
| Khách mang xe đi bảo dưỡng (người dùng cuối) | Biết khung giờ còn chỗ, đặt lịch nhanh, nhận xác nhận rõ ràng | Tỷ lệ đặt lịch thành công; trải nghiệm dùng thử |
| Nhân viên tiếp nhận (người vận hành) | Không có hai khách bị xếp cùng một suất, dễ nhận biết lịch mới | Lỗi trùng lịch; số thao tác sửa lịch thủ công |
| Nhóm kỹ thuật và hỗ trợ | Hệ thống dễ vận hành, có khả năng thay đổi mà ít gây lỗi | Tín hiệu lỗi, khả năng kiểm thử và triển khai an toàn |

Không nên chỉ hỏi một người có chức danh “khách hàng” rồi coi đó là toàn bộ sự thật. Chẳng hạn, chủ gara muốn thêm báo cáo doanh thu nhưng khách đặt lịch đang không biết nút xác nhận ở đâu. Nhóm cần trao đổi về ưu tiên, xác định đối tượng đang gặp vấn đề chính và chỉ rõ bằng chứng cho quyết định.

**Sự hài lòng** là cảm nhận và kết quả tích lũy theo thời gian. Việc một bên liên quan nói “ý tưởng này hay” trong cuộc họp chưa chứng minh người dùng có thể hoàn thành tác vụ hoặc sẽ tiếp tục sử dụng sản phẩm. Nhóm cần kết hợp quan sát hành vi, phản hồi trực tiếp và chỉ số kết quả.

### 2.2. Thế nào là “phần mềm có giá trị”?

Một phần mềm có giá trị khi nó **giúp ai đó đạt một kết quả hữu ích** trong điều kiện sử dụng thực tế. Giá trị có thể là tiết kiệm thời gian, giảm lỗi, tăng khả năng tiếp cận, hỗ trợ một quyết định, giảm rủi ro, tăng độ tin cậy hoặc tạo ra dịch vụ mới.

Xét các tình huống:

- Nhóm hoàn thành 12 màn hình nhưng khách chưa thể đặt lịch vì chưa lưu được dữ liệu: **đầu ra nhiều, giá trị sử dụng còn hạn chế**.
- Nhóm hoàn thành một luồng chọn khung giờ → nhập thông tin tối thiểu → xác nhận, đã kiểm thử và cho khách dùng thử: **đầu ra ít hơn nhưng giả định cốt lõi đã có thể được kiểm chứng**.
- Nhóm phát hành chức năng đặt lịch nhưng tạo lịch trùng khiến khách phải chờ tại gara: có chức năng được giao, song **giá trị bị giảm bởi lỗi và trải nghiệm xấu**.

Giá trị phải đi kèm chất lượng đủ để sử dụng trong phạm vi đã thỏa thuận. Một tính năng gây rò rỉ dữ liệu, mất thông tin, hành vi khó hiểu hoặc thường xuyên ngừng hoạt động có thể làm mất lòng tin nhanh hơn lợi ích mà nó mang lại.

### 2.3. “Sớm” nghĩa là sớm có bằng chứng, không phải đẩy rủi ro cho khách

**Bàn giao sớm** là rút ngắn khoảng thời gian từ khi hình thành giả thuyết đến khi có phiên bản phần mềm hữu dụng mà khách hàng hoặc người đại diện có thể dùng và đánh giá. Không bắt buộc sản phẩm phải có mọi tính năng ngay lần đầu.

Phạm vi bàn giao tùy mức rủi ro:

- Một luồng đơn giản có thể cho nhóm khách thử hạn chế ngay trong tuần đầu.
- Tính năng liên quan đến thanh toán, quyền riêng tư hoặc dữ liệu quan trọng có thể phải kiểm tra bảo mật, tính đúng đắn và cơ chế khôi phục trước khi phát hành rộng.
- Khi chưa có khả năng mở cho người dùng thật, một môi trường dùng thử với kịch bản và dữ liệu phù hợp vẫn giúp nhận phản hồi ban đầu; nhóm cần ghi rõ loại bằng chứng này **chưa thay thế** dữ liệu sử dụng thực tế.

“Sớm” là tương đối với bối cảnh và rủi ro, nhưng câu hỏi cần đặt thường xuyên là: **Chúng ta có thể thu được phản hồi đáng tin cậy sớm hơn bằng cách nào?**

### 2.4. “Liên tục” nghĩa là có nhịp giao giá trị và học hỏi

**Bàn giao liên tục** trong nguyên tắc Agile là đưa những phần giá trị tiếp theo đến khách hàng **đều đặn và đủ thường xuyên để thích ứng**. Không có quy định rằng mỗi ngày phải phát hành một phiên bản; nhịp giao tùy sản phẩm, khả năng triển khai và mức rủi ro.

Cần phân biệt:

| Khái niệm | Ý nghĩa | Có đồng nghĩa với việc khách hàng nhận giá trị không? |
| --- | --- | --- |
| Hoàn thành một tác vụ kỹ thuật | Một phần việc lập trình đã xong | Chưa chắc; có thể chưa tạo hành vi dùng được |
| **Increment** | Phần tăng trưởng sản phẩm sử dụng được, đáp ứng tiêu chuẩn chất lượng | Có tiềm năng tạo giá trị và có thể kiểm chứng |
| **Deployment** | Đưa một phiên bản vào môi trường vận hành hoặc kiểm thử | Chưa chắc khách đã được tiếp cận tính năng |
| **Release** | Cho nhóm người dùng mục tiêu sử dụng một khả năng | Là cơ hội nhận giá trị và phản hồi; vẫn cần đo kết quả |
| **Continuous Delivery** (thực hành kỹ thuật) | Giữ phần mềm luôn ở trạng thái có thể phát hành an toàn khi cần | Hỗ trợ bàn giao sớm, nhưng không tự bảo đảm khách hài lòng |
| **Continuous Deployment** (thực hành kỹ thuật) | Tự động phát hành các thay đổi đủ điều kiện vào môi trường sản xuất | Không phải yêu cầu bắt buộc của nguyên tắc Agile |

Một nhóm có thể triển khai mã thường xuyên trong khi vẫn giữ tính năng sau **feature flag** hoặc phát hành cho một nhóm nhỏ. Điều quan trọng là thiết kế nhịp phản hồi đủ nhanh, có kiểm soát và phù hợp với chất lượng mong đợi.

## 3. Vì sao giao sớm và thường xuyên giúp tăng cơ hội làm hài lòng khách hàng?

Phần mềm thường được phát triển trong điều kiện có **bất định**: nhóm không biết chắc yêu cầu nào thực sự cần, thao tác nào gây khó khăn, thời gian phát triển bao lâu hoặc các bộ phận phụ thuộc có phối hợp đúng như dự kiến không.

Khi đợi đến cuối dự án mới đưa toàn bộ sản phẩm cho khách, nhóm có thể phát hiện quá muộn rằng mình đã hiểu sai ưu tiên. Những vòng bàn giao nhỏ giúp:

1. **Kiểm tra nhu cầu:** người dùng phản hồi vào thứ họ nhìn thấy và trải nghiệm được, thay vì chỉ tưởng tượng từ tài liệu.
2. **Giảm chi phí thay đổi:** khi phạm vi đã xây dựng còn nhỏ, việc đổi hướng thường dễ hơn so với sửa toàn bộ hệ thống đã gắn kết chặt.
3. **Nhận diện rủi ro kỹ thuật:** tích hợp, kiểm thử và triển khai lặp lại phát hiện vấn đề dần dần.
4. **Tạo lợi ích trước khi sản phẩm hoàn chỉnh:** khách có thể dùng một khả năng hữu ích trong lúc nhóm tiếp tục xây những khả năng khác.
5. **Duy trì đối thoại có căn cứ:** nhóm và khách cùng kiểm tra kết quả quan sát được, rồi cập nhật thứ tự ưu tiên.

~~~mermaid
flowchart LR
    A[Hiểu vấn đề và giả thuyết giá trị] --> B[Chọn một lát cắt nhỏ]
    B --> C[Xây dựng và kiểm thử]
    C --> D[Bàn giao an toàn để dùng thử]
    D --> E[Quan sát hành vi và hỏi phản hồi]
    E --> F[Đánh giá kết quả, điều chỉnh backlog]
    F --> B
~~~

Vòng lặp này không bảo đảm mỗi lần giao đều làm khách hài lòng. Đôi khi phản hồi cho thấy giả thuyết sai. Phát hiện sớm một giả thuyết sai vẫn có giá trị vì giúp nhóm dừng đầu tư vào hướng ít ích lợi.

## 4. Tình huống xuyên suốt: cải tiến việc đặt lịch bảo dưỡng xe

Một gara nhỏ đang ghi lịch hẹn qua điện thoại và sổ tay. Khách phải gọi trong giờ làm việc, nhân viên đôi khi nhận hai lịch cùng khung giờ. Chủ gara yêu cầu “làm ứng dụng đầy đủ với hồ sơ khách hàng, tích điểm, thanh toán, thông báo, báo cáo và quản lý kho”.

Nếu bắt đầu bằng toàn bộ danh sách trên, nhóm có thể mất nhiều tuần mới xác nhận được liệu người dùng có tự đặt lịch được hay không.

### 4.1. Đặt giả thuyết giá trị, không mặc định giải pháp đã đúng

Nhóm cùng chủ gara phát biểu giả thuyết:

> Nếu khách có thể nhìn thấy khung giờ thực sự còn chỗ và đặt lịch trên điện thoại, họ sẽ cần gọi ít hơn; nhân viên sẽ giảm nhập lịch thủ công và số lịch trùng sẽ giảm.

Giả thuyết dẫn đến các câu hỏi cần khám phá:

- Khách thường biết chính xác dịch vụ cần làm hay cần tư vấn trước?
- Khung giờ được tính theo thời gian cố định hay phụ thuộc dịch vụ, số thợ và thiết bị?
- Khi khách không đến, gara xử lý chỗ trống thế nào?
- Khách cần nhận xác nhận qua màn hình, SMS hay kênh khác?
- Nhân viên có bắt buộc duyệt yêu cầu trước khi xác nhận không?

Không nên thiết kế các quy tắc quan trọng từ giả định của lập trình viên. Trước vòng bàn giao đầu, nhóm phải làm rõ tối thiểu cách gara quản lý sức chứa để tránh cấp chỗ sai.

### 4.2. Chọn hành vi đầu tiên mà khách có thể dùng

Hạng mục đầu tiên có thể là:

> **Là** người muốn bảo dưỡng xe, **tôi muốn** xem các khung giờ còn chỗ và gửi yêu cầu đặt lịch, **để** chủ động chọn thời gian phù hợp mà không phải gọi điện.

Tiêu chí chấp nhận minh họa:

~~~gherkin
Tình huống: Khách đặt được một khung giờ còn chỗ
  Cho trước khung giờ 09:00 thứ Bảy còn 1 suất
  Khi khách chọn khung giờ đó và gửi thông tin hợp lệ
  Thì hệ thống ghi nhận đúng một yêu cầu đặt lịch
  Và hiển thị mã đặt lịch cùng trạng thái xác nhận

Tình huống: Không nhận vượt sức chứa
  Cho trước khung giờ 09:00 thứ Bảy đã hết suất
  Khi khách cố gắng chọn khung giờ đó
  Thì hệ thống không tạo lịch hẹn mới
  Và đề nghị khách chọn khung giờ khác
~~~

Cần thống nhất thêm tính chất nghiệp vụ: lịch được **xác nhận tự động** hay chỉ **ghi nhận yêu cầu chờ duyệt**. Màn hình kết quả phải sử dụng đúng thuật ngữ. Một yêu cầu “đã tiếp nhận” không được hiển thị như “đã xác nhận” nếu gara còn phải kiểm tra lại.

### 4.3. Chia phạm vi để thử và nhận phản hồi

| Vòng giao thử nghiệm | Lát cắt có thể dùng được | Ai tham gia phản hồi? | Câu hỏi trọng tâm |
| --- | --- | --- | --- |
| Vòng 1 | Xem ngày/giờ còn chỗ, gửi yêu cầu và nhận kết quả rõ ràng | Một nhóm khách thử và nhân viên tiếp nhận | Khách có hoàn thành thao tác được không? Dữ liệu có đúng không? |
| Vòng 2 | Tra cứu, đổi hoặc hủy lịch theo chính sách đã thống nhất | Khách đã đặt lịch, nhân viên điều phối | Khách có tự xử lý thay đổi được không? Có giảm cuộc gọi không? |
| Vòng 3 | Thông báo nhắc lịch theo kênh khách đồng ý nhận, nếu nhu cầu được xác nhận | Khách và chủ gara | Thông báo có giúp giảm bỏ hẹn mà không gây phiền không? |
| Các vòng sau | Báo cáo, thanh toán, tích điểm hoặc tính năng khác khi có căn cứ ưu tiên | Chủ gara và các nhóm sử dụng liên quan | Lợi ích có đủ lớn so với chi phí và rủi ro không? |

Đây là **phương án minh họa**, không phải lịch biểu bắt buộc. Nếu vòng 1 cho thấy khách khó hiểu các gói bảo dưỡng, vòng 2 có thể cần cải thiện cách mô tả dịch vụ trước khi làm đổi lịch. Việc thay đổi backlog theo phản hồi chính là hành vi Agile.

## 5. Cách xác định phần giá trị nhỏ nhất nên bàn giao

Đừng hỏi chỉ “Có thể chia công việc thành bao nhiêu task?”. Hãy hỏi **mỗi lát cắt có hoàn chỉnh một hành vi có ích để người khác đánh giá được không?**

### 5.1. Chia theo hành trình người dùng

Một cách chia kém hiệu quả cho bài toán đặt lịch là:

1. Làm toàn bộ cơ sở dữ liệu.
2. Viết mọi API.
3. Làm toàn bộ giao diện.
4. Cuối dự án mới kiểm thử hành vi đặt lịch.

Các bước đó có thể là các tác vụ triển khai cần thiết, nhưng riêng từng bước không trả lời được “khách có đặt lịch thành công không?”.

Thay vào đó, lựa chọn một **vertical slice**: giao diện chọn giờ, kiểm tra sức chứa, ghi nhận lịch và hiển thị kết quả, cùng kiểm thử cần thiết. Lát cắt hẹp hơn về phạm vi nghiệp vụ nhưng hoàn chỉnh theo chiều sử dụng. Lát cắt tiếp theo bổ sung trường hợp mới.

### 5.2. Chọn theo giá trị, rủi ro và khả năng học

Ba câu hỏi giúp sắp thứ tự Product Backlog:

- **Giá trị:** hạng mục nào giải quyết điểm đau quan trọng của người dùng?
- **Rủi ro/bất định:** hạng mục nào chứa giả định nguy hiểm nên kiểm chứng sớm?
- **Quy mô:** hạng mục nào đủ nhỏ để xây, kiểm thử, bàn giao và nhận phản hồi trong một vòng ngắn?

Ví dụ, chức năng thanh toán trước có thể mang doanh thu, nhưng nếu gara chưa rõ khách có chấp nhận đặt lịch trực tuyến, xây thanh toán ngay có thể tạo chi phí không cần thiết. Ngược lại, nếu không kiểm soát được đặt trùng thì chức năng đặt lịch chưa đáng tin: quản lý sức chứa cần đi cùng lát cắt đầu tiên.

Một backlog thử nghiệm có thể sắp như sau:

| Ưu tiên tạm thời | Hạng mục | Giá trị hoặc rủi ro cần xử lý |
| --- | --- | --- |
| 1 | Xem khung giờ phù hợp, gửi yêu cầu và thông báo trạng thái | Kiểm tra hành vi sử dụng cốt lõi |
| 2 | Bảo đảm không đặt quá sức chứa | Tránh phá hỏng lịch và lòng tin |
| 3 | Cho nhân viên xem và xử lý lịch mới | Bảo đảm quy trình của gara thực sự vận hành |
| 4 | Khách tra cứu hoặc hủy lịch theo chính sách | Giảm liên lạc thủ công |
| 5 | Nhắc lịch theo kênh được đồng ý | Kiểm tra khả năng giảm bỏ hẹn |
| 6 | Thống kê chi tiết, tích điểm, thanh toán nâng cao | Chỉ làm khi lợi ích và thứ tự ưu tiên được xác nhận |

Trong thực hành, hạng mục 1–3 có thể cần **cùng xuất hiện trong lần dùng thử đầu** để tạo một luồng hợp lệ. Bảng thể hiện các ưu tiên cần trao đổi, không hàm ý mỗi dòng nhất thiết là một lần phát hành riêng.

### 5.3. MVP, bản dùng thử và Increment không phải cùng một thứ

- **MVP (Minimum Viable Product)** là cách kiểm chứng một giả thuyết sản phẩm với nỗ lực hợp lý nhất và sản phẩm có mức hữu dụng cần thiết; nó không đồng nghĩa bản sơ sài hay bản thiếu các yêu cầu an toàn cốt lõi.
- **Bản dùng thử** có thể giới hạn người tham gia, quy mô hoặc dữ liệu để lấy phản hồi trước khi phát hành rộng.
- **Increment** trong Scrum là phần tăng trưởng sử dụng được, đạt Definition of Done và làm sản phẩm tiến gần Product Goal. Increment có thể đã sẵn sàng để phát hành dù thời điểm công bố cho mọi khách là một quyết định khác.

Nhóm cần gọi đúng tên thứ mình bàn giao và nói rõ phạm vi kiểm chứng. Một prototype chỉ minh họa giao diện giúp kiểm tra cách hiểu của người dùng, nhưng chưa xác minh được các rủi ro như đặt trùng khi có nhiều yêu cầu đồng thời.

## 6. Vận hành chu trình giao hàng và phản hồi

### 6.1. Trước khi phát triển: thống nhất kết quả mong muốn

Một mục tiêu có ích cần liên hệ với vấn đề, nhóm người dùng và tín hiệu đánh giá. Chẳng hạn:

> Trong đợt thử nghiệm có giám sát, khách có thể tự chọn một khung giờ hợp lệ và gửi yêu cầu đặt lịch; nhân viên nhìn thấy yêu cầu với trạng thái đúng và không cần nhập lại thông tin.

Nhóm có thể đặt **mục tiêu tham khảo** như “ít nhất 4 trong 5 người thử hoàn thành thao tác mà không cần hướng dẫn”, nhưng phải coi đây là ngưỡng học tập trong mẫu nhỏ, **không phải bằng chứng thống kê** về toàn bộ khách hàng. Nếu người thử được chọn từ một nhóm rất rành công nghệ, kết quả có thể không đại diện cho khách hàng thực tế.

Trước khi xây dựng, ghi lại:

1. Người dùng mục tiêu và tình huống họ gặp vấn đề.
2. Giả thuyết về thay đổi hành vi hoặc lợi ích.
3. Phần mềm cần hoạt động thế nào để thử giả thuyết.
4. Những điều phải bảo đảm để dùng thử an toàn.
5. Tín hiệu quan sát, người ghi nhận và thời điểm xem kết quả.

### 6.2. Trong khi phát triển: bảo đảm chất lượng ngay từ đầu

Một nhóm muốn giao thường xuyên cần giảm công sức kiểm tra và tích hợp mỗi lần. Các thực hành có thể kết hợp từ **XP** hoặc kỹ thuật hiện đại gồm kiểm thử tự động cho nghiệp vụ quan trọng, lập trình cặp khi phù hợp, review mã, tích hợp thường xuyên, cải tiến cấu trúc mã và quy trình triển khai lặp lại được.

Ví dụ, Definition of Done cho lát cắt đặt lịch có thể yêu cầu:

- Chức năng đáp ứng tiêu chí chấp nhận đã thống nhất.
- Kiểm thử tự động cho đường đi chính, khung giờ hết chỗ và trường hợp gửi trùng theo thiết kế.
- Có kiểm tra truy cập dữ liệu cá nhân, quyền xem lịch và chỉ thu thập thông tin cần thiết.
- Mã đã được kiểm tra, tích hợp; không có lỗi nghiêm trọng đã biết trong phạm vi bàn giao.
- Có cách triển khai và quan sát lỗi phù hợp với môi trường dùng thử.
- Người đại diện nghiệp vụ có thể xem, hiểu và đánh giá kết quả.

**Definition of Done** là chuẩn chất lượng chung của Increment. **Tiêu chí chấp nhận** mô tả hành vi cụ thể của từng user story. Không thể tuyên bố “đã giao giá trị” chỉ vì một lập trình viên chạy được chức năng trên máy mình.

### 6.3. Khi bàn giao: quyết định phạm vi sử dụng và cách quan sát

Với chức năng mới, nhóm có thể phát hành cho vài khách tự nguyện, hướng dẫn nhân viên hỗ trợ, kiểm tra log lỗi, có cơ chế tắt tính năng hoặc quay lại quy trình cũ khi có sự cố. Cách phát hành phụ thuộc rủi ro và điều kiện vận hành.

Mỗi lần bàn giao nên trả lời ngắn gọn:

| Câu hỏi | Ví dụ câu trả lời có thể kiểm chứng |
| --- | --- |
| Khách nhận được khả năng gì? | Khách chọn giờ trống và gửi yêu cầu đặt lịch trên điện thoại |
| Ai đã sử dụng? | Năm khách tham gia đợt thử nghiệm có hướng dẫn ban đầu |
| Chức năng có hoạt động an toàn không? | Không ghi nhận lịch vượt sức chứa trong các tình huống đã kiểm thử |
| Phản hồi lớn nhất là gì? | Một số người không hiểu “đã nhận yêu cầu” khác “đã xác nhận” |
| Nhóm quyết định điều gì tiếp theo? | Làm rõ trạng thái và cách nhân viên xác nhận trước khi thêm thông báo mới |

Không nên che giấu hạn chế của bản dùng thử. Nói rõ tính năng hiện có và điều chưa hỗ trợ giúp duy trì kỳ vọng hợp lý, qua đó hỗ trợ sự hài lòng lâu dài.

### 6.4. Sau bàn giao: ghi nhận phản hồi thành quyết định

Phản hồi nên gắn với **tình huống và bằng chứng**. Câu “khách không thích giao diện” khó hành động hơn “ba trong năm người thử bỏ qua dòng thông báo, rồi hỏi nhân viên lịch đã chắc chắn chưa”.

Một bản ghi ngắn có thể gồm:

| Trường | Ví dụ |
| --- | --- |
| Quan sát | Ba người dùng thử không nhận ra trạng thái “chờ xác nhận” |
| Tác động | Họ không chắc có cần gọi lại gara hay không |
| Giả thuyết nguyên nhân | Tên trạng thái khó hiểu và thiếu bước tiếp theo rõ ràng |
| Thay đổi đề xuất | Đổi thông báo và nêu thời gian gara sẽ phản hồi |
| Cách kiểm tra | Cho một nhóm người thử khác hoàn thành luồng, hỏi họ hiểu trạng thái thế nào |

Nếu người dùng chỉ ra nhu cầu bất ngờ, nhóm thảo luận cùng Product Owner hoặc người chịu trách nhiệm ưu tiên để **cập nhật Product Backlog**. Không mặc định mọi yêu cầu phát sinh đều phải triển khai; cần cân nhắc giá trị, bằng chứng, chi phí và tác động đến người dùng khác.

## 7. Đo thế nào để biết nguyên tắc đang được thực hành?

Không có một chỉ số đơn lẻ nào chứng minh “khách hàng hài lòng”. Nhóm cần kết hợp **tín hiệu từ hành vi**, **phản hồi trực tiếp**, **chất lượng** và **khả năng bàn giao**.

### 7.1. Chỉ số gắn với giá trị người dùng

| Tín hiệu | Câu hỏi nó trả lời | Giới hạn cần nhớ |
| --- | --- | --- |
| Tỷ lệ hoàn tất đặt lịch | Bao nhiêu người bắt đầu và hoàn thành luồng? | Cần phân biệt lỗi kỹ thuật với người dùng cố ý dừng |
| Thời gian hoàn thành tác vụ | Người dùng có mất nhiều công sức không? | Nên quan sát thêm khó khăn, không chỉ nhìn số trung bình |
| Số cuộc gọi phải nhập lịch thủ công | Quy trình có giảm việc cho nhân viên? | Lượng khách hoặc mùa vụ thay đổi có thể ảnh hưởng |
| Tỷ lệ lịch trùng hoặc sai | Hệ thống có đáng tin trong nghiệp vụ cốt lõi? | Cần có định nghĩa thế nào là lỗi và nguồn dữ liệu nhất quán |
| Phản hồi sau khi dùng | Khách có hiểu, tin tưởng và muốn tiếp tục? | Khảo sát chủ quan; câu hỏi phải trung lập và có bối cảnh |

Giả sử **đợt thử minh họa** có 8 người, 6 người đặt được lịch mà không cần trợ giúp. Tỷ lệ quan sát được là **6/8 = 75%**. Đây là dấu hiệu để đặt câu hỏi “hai người còn lại vướng ở đâu?”, chưa đủ cơ sở khẳng định 75% toàn bộ khách hàng đều dùng được. Kết hợp quan sát và phỏng vấn giúp xác định việc cần cải thiện.

### 7.2. Chỉ số về tốc độ nhận phản hồi và dòng công việc

Nhóm có thể theo dõi:

- **Thời gian từ ý tưởng đến phản hồi có ích:** khoảng cách giữa lúc đặt giả thuyết và lúc có bằng chứng để quyết định. Cần thống nhất mốc bắt đầu và kết thúc.
- **Lead time:** thời gian từ khi ghi nhận yêu cầu ở mốc quy ước đến khi hoàn tất theo quy ước.
- **Cycle time:** thời gian xử lý một hạng mục từ khi bắt đầu làm đến khi xong.
- **Throughput:** số hạng mục hoàn tất trong một khoảng thời gian.
- **WIP và work item age:** số việc đang làm dở và thời gian từng việc đã chờ trong luồng.
- **Tần suất phát hành và tỷ lệ phát hành có lỗi:** cho thấy khả năng chuyển phần mềm có chất lượng đến người dùng.

Các chỉ số này giúp nhận ra điểm nghẽn; **không tự chứng minh giá trị người dùng**. Chẳng hạn, phát hành mười lần mỗi ngày nhưng không ai dùng tính năng mới không phải bằng chứng cho sự hài lòng. Ngược lại, có nhiều người dùng nhưng sự cố nghiêm trọng lặp lại cũng không thể coi là thành công bền vững.

### 7.3. Đừng tối ưu một con số bằng mọi giá

Các cách hiểu sai thường gặp:

- Đếm **số tính năng** thay cho khả năng giải quyết vấn đề.
- Đẩy việc qua cột “Hoàn tất” trước khi đáp ứng Definition of Done.
- Tăng số lần release nhưng bỏ qua lỗi và phản hồi.
- Chỉ đo lượt truy cập mà không biết người dùng có đạt mục tiêu hay không.
- Dùng velocity/story points để so sánh các nhóm có ngữ cảnh, cách ước lượng khác nhau.
- Chỉ hỏi người mua sản phẩm mà không quan sát người sử dụng và người vận hành.

Khi thảo luận kết quả, nhóm cần nhìn **số liệu cùng câu chuyện sử dụng thực tế**. Nếu tỷ lệ hoàn tất tăng nhưng số cuộc gọi khiếu nại cũng tăng, cần điều tra trước khi tuyên bố thành công.

## 8. Scrum, Kanban và XP hỗ trợ nguyên tắc này ra sao?

Nguyên tắc Agile số 1 có thể được thực hiện bằng nhiều cách phối hợp. Các framework và thực hành không thay thế việc hiểu khách hàng:

| Cách tiếp cận | Giúp hiện thực hóa nguyên tắc như thế nào? | Cần tránh |
| --- | --- | --- |
| **Product Backlog và user story** | Diễn tả nhu cầu theo giá trị, xếp ưu tiên, chia phần nhỏ để phản hồi sớm | Biến backlog thành danh sách cố định không xét lại |
| **Scrum** | Sprint Goal giữ nhóm tập trung; Increment đáp ứng DoD; Sprint Review tạo cơ hội xem kết quả và điều chỉnh | Chỉ demo slide hoặc công việc chưa dùng được; coi Review là báo cáo thành tích |
| **Kanban** | Trực quan hóa dòng công việc, giới hạn WIP, giải quyết điểm nghẽn để rút ngắn thời gian hoàn tất | Đẩy việc mới vào luồng dù các việc cũ đang mắc kẹt |
| **XP** | Kiểm thử, tích hợp liên tục, refactoring và cộng tác kỹ thuật giúp thay đổi nhanh mà vẫn đáng tin | Hy sinh chất lượng để tăng tốc độ phát hành trước mắt |
| **Khảo sát, dùng thử và quan sát** | Cung cấp bằng chứng về trải nghiệm, giá trị và mức độ hài lòng | Thu thập phản hồi nhưng không thay đổi quyết định |

**Trong Scrum:** Sprint Review là dịp kiểm tra kết quả với bên liên quan và điều chỉnh hướng đi; Scrum không quy định chỉ được release ở cuối Sprint. Một Increment đạt DoD có thể được phát hành sớm hơn nếu phù hợp.

**Trong Kanban:** nhóm có thể áp dụng chính sách kéo việc mới khi còn năng lực, bàn giao theo dòng việc mà không cần cố nhét mọi yêu cầu vào Sprint. Việc giao thường xuyên được hỗ trợ bởi giới hạn WIP và quan sát thời gian chờ.

**Trong XP:** kiểm thử tự động và tích hợp thường xuyên giúp chi phí mỗi lần thay đổi thấp hơn, từ đó dễ thử giả thuyết nhỏ. Một quy trình release nhanh nhưng liên tục làm hỏng tính năng cũ sẽ chống lại mục tiêu thỏa mãn khách hàng.

## 9. Những tình huống khó và cách ra quyết định

### 9.1. Khách hàng muốn mọi tính năng có ngay

**Tình huống:** chủ gara cho rằng ứng dụng chỉ có giá trị nếu có đặt lịch, kho, kế toán, thanh toán và tích điểm cùng lúc.

**Cách tiếp cận:** hỏi mục tiêu kinh doanh ưu tiên nhất, chỉ ra rủi ro chưa biết, cùng mô phỏng hành trình khách hàng và đề xuất thử một lát cắt hoàn chỉnh. Thống nhất trước bằng chứng nào sẽ quyết định có nên đầu tư tiếp. Nếu các tính năng bắt buộc liên quan pháp lý hoặc nghiệp vụ phải đi cùng nhau, không được bỏ chúng chỉ để gọi bản đầu là “MVP”.

### 9.2. Nhu cầu thay đổi ngay sau khi đã phát hành

**Tình huống:** khách thử thấy khung giờ không phản ánh loại dịch vụ; nhiều người phải gọi lại.

**Cách tiếp cận:** ghi nhận vấn đề, đo mức ảnh hưởng, làm rõ quy tắc lịch theo dịch vụ, chia công việc sửa thành lát cắt nhỏ. Ưu tiên việc giải quyết lỗi cốt lõi trước tính năng trang trí. Điều chỉnh kế hoạch có căn cứ không phải dấu hiệu thất bại.

### 9.3. Chưa thể cho người dùng thật trải nghiệm

**Tình huống:** hệ thống liên quan thông tin khách hàng hoặc tích hợp vận hành chưa được phép mở công khai.

**Cách tiếp cận:** nhận phản hồi từ nhân viên nghiệp vụ trên môi trường giới hạn, dùng dữ liệu thử phù hợp, kiểm tra điều kiện bảo mật và chuẩn bị kế hoạch phát hành từng bước. Nhóm phải nói rõ độ tin cậy của bằng chứng và không đánh đồng “đã demo nội bộ” với “người dùng thực đã hài lòng”.

### 9.4. Giao nhanh khiến lỗi tăng

**Tình huống:** mỗi lần ra tính năng lại phát sinh lỗi trùng lịch, người dùng mất niềm tin.

**Cách tiếp cận:** tạm giảm lượng thay đổi, xác định nguyên nhân, bổ sung kiểm thử và quy tắc chất lượng, điều chỉnh giới hạn WIP và cách review. **Tốc độ giao giá trị bền vững** đòi hỏi kiểm soát lỗi, không chỉ rút ngắn lịch phát hành.

### 9.5. Người mua hài lòng nhưng người dùng trực tiếp không hài lòng

**Tình huống:** chủ gara thích báo cáo đẹp, nhưng nhân viên mất gấp đôi thời gian xác nhận lịch.

**Cách tiếp cận:** đo cả tác động đến người vận hành, đặt kết quả của các bên trong cùng cuộc trao đổi ưu tiên và cân nhắc chi phí vận hành. Một phần mềm làm đẹp chỉ số quản lý nhưng tạo gánh nặng lớn ở bước sử dụng có thể không tạo ra giá trị ròng.

## 10. Bài thực hành nhóm: thiết kế vòng bàn giao có thể học hỏi

**Bối cảnh:** một nhóm gồm ba người phát triển, một người đại diện gara và hai người đóng vai khách dùng thử. Nhóm có tối đa một tuần để làm một phiên bản đầu tiên. Đây là khung thời gian của bài tập, không phải thời hạn chuẩn cho mọi sản phẩm.

### Nhiệm vụ 1 — Làm rõ giá trị (15 phút)

Viết ngắn gọn:

1. Ai là người sử dụng chính và họ đang gặp khó khăn gì?
2. Điều gì thay đổi nếu phiên bản đầu tiên có ích?
3. Hai giả thuyết chưa chắc đúng là gì?
4. Cần quan sát bằng chứng nào để kiểm chứng chúng?

**Sản phẩm đầu ra:** một câu mô tả mục tiêu, hai giả thuyết có thể bị bác bỏ và cách đo/quan sát tương ứng.

### Nhiệm vụ 2 — Viết story và chia lát cắt (20 phút)

Viết ít nhất ba user story theo mẫu **“Là [vai trò], tôi muốn [khả năng], để [lợi ích]”**. Chọn một story làm lát cắt đầu tiên với ít nhất hai tiêu chí chấp nhận, trong đó có **một trường hợp lỗi hoặc cạnh biên**. Ghi chú các phụ thuộc thực sự cần cho việc dùng thử.

**Sản phẩm đầu ra:** backlog ngắn được xếp ưu tiên và một lát cắt có thể demo bằng phần mềm hoạt động được.

### Nhiệm vụ 3 — Thiết kế vòng bàn giao và bảo đảm chất lượng (20 phút)

Chọn Scrum hoặc Kanban để phối hợp, sau đó ghi:

- Mục tiêu vòng làm việc và Definition of Done.
- Khi nào có phiên bản để kiểm tra, ai sẽ thử và trong môi trường nào.
- Các kiểm thử quan trọng, cách phát hiện lỗi và kế hoạch xử lý khi tính năng có vấn đề.
- Kênh nhận phản hồi, người tổng hợp và cuộc trao đổi quyết định thứ tự ưu tiên tiếp theo.

**Sản phẩm đầu ra:** kế hoạch từ lúc bắt đầu story đến khi có thể lấy phản hồi, không chỉ kế hoạch lập trình.

### Nhiệm vụ 4 — Đọc phản hồi giả lập và đổi hướng (15 phút)

Giảng viên hoặc một thành viên đưa phản hồi giả định:

> Trong sáu người thử, bốn người hoàn thành đặt lịch, nhưng ba người không biết lịch đã được xác nhận hay mới gửi yêu cầu. Nhân viên tiếp nhận cho biết nhiều khách còn gọi để hỏi lại.

Nhóm cần:

1. Phân biệt **quan sát** với **giả thuyết nguyên nhân**.
2. Đề xuất một cải tiến nhỏ và cách kiểm chứng nó.
3. Giải thích vì sao cần ưu tiên hoặc chưa ưu tiên cải tiến đó so với các story đang chờ.
4. Nêu rõ số người tham gia nhỏ khiến kết luận có giới hạn ra sao.

**Sản phẩm đầu ra:** một quyết định backlog mới có căn cứ và một phép thử phản hồi tiếp theo.

### Nhiệm vụ 5 — Tự đánh giá (10 phút)

Đánh dấu mỗi tiêu chí là **chưa rõ**, **đạt** hoặc **vững**:

| Tiêu chí | Chưa rõ | Đạt | Vững |
| --- | --- | --- | --- |
| Xác định người nhận giá trị | Chỉ nêu “khách hàng” chung chung | Chỉ ra người dùng chính và vấn đề | Xử lý được nhu cầu khác nhau của bên mua, người dùng, vận hành |
| Định nghĩa phần mềm có giá trị | Đếm màn hình và số task | Mô tả hành vi hữu ích có thể dùng | Gắn hành vi với kết quả và rủi ro chất lượng |
| Giao sớm | Chờ làm toàn bộ hệ thống | Có lát cắt đủ nhỏ, đạt DoD | Có cách thử an toàn, giới hạn phạm vi và học từ phản hồi |
| Giao liên tục | Chỉ có một lần demo cuối | Có vòng kiểm chứng và điều chỉnh backlog | Có nhịp giao phù hợp, chính sách xử lý lỗi và cải tiến |
| Đánh giá sự hài lòng | Đếm số release | Theo dõi tín hiệu hành vi và phản hồi | Biết giới hạn dữ liệu, kết hợp giá trị, chất lượng và dòng công việc |

Một nhóm đạt mục tiêu của bài khi có thể **bàn giao một hành vi có ích, biết ai đã thử, hiểu họ gặp khó khăn nào và đưa ra quyết định tiếp theo dựa trên bằng chứng**. Hoàn thành đủ nghi thức Scrum hay có một bảng Kanban đẹp chưa thay thế được năng lực này.

## 11. Checklist áp dụng trong dự án thực tế

- [ ] Nhóm xác định rõ người sử dụng, người ra quyết định và người chịu tác động.
- [ ] Có mục tiêu kết quả cho khách hàng, không chỉ danh sách tính năng.
- [ ] Mỗi hạng mục ưu tiên có giả thuyết giá trị hoặc rủi ro cần giải quyết.
- [ ] Bản đầu đủ nhỏ để nhận phản hồi sớm nhưng đủ hoàn chỉnh và an toàn cho phạm vi thử.
- [ ] User story có tiêu chí chấp nhận; Increment có Definition of Done được hiểu thống nhất.
- [ ] Có nhịp kiểm thử, tích hợp, bàn giao và phản hồi phù hợp với bối cảnh.
- [ ] Nhóm phân biệt deployment, release và giá trị thực sự người dùng nhận.
- [ ] Có cách quan sát việc người dùng hoàn thành mục tiêu và cách ghi nhận vấn đề.
- [ ] Backlog được điều chỉnh sau phản hồi; quyết định có lý do và người chịu trách nhiệm.
- [ ] Nhóm đo chất lượng cùng tốc độ giao việc, tránh đánh đổi lòng tin để tăng số lần release.

Khi áp dụng nguyên tắc thứ nhất, hãy liên tục hỏi: **“Khách hàng đã nhận được lợi ích cụ thể nào từ phần mềm đang chạy, chúng ta biết điều đó bằng chứng nào, và phần hữu ích tiếp theo có thể được giao an toàn sớm đến đâu?”** Câu trả lời cho ba vế này nên dẫn dắt cách viết story, xếp backlog, tổ chức Scrum/Kanban, thực hành XP và cải tiến dòng công việc trong các vòng phát triển sau.
