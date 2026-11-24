# Phát triển hiểu biết về yêu cầu qua các vòng phản hồi

Trong một dự án phần mềm, yêu cầu ban đầu thường phản ánh **những gì các bên đang hiểu ở thời điểm trao đổi**, chứ chưa phải toàn bộ sự thật về người dùng, quy tắc nghiệp vụ và khả năng kỹ thuật. Khi sản phẩm bắt đầu được xây dựng và sử dụng, nhóm sẽ phát hiện những tình huống chưa dự đoán được: người dùng hiểu khác với người thiết kế, chính sách nghiệp vụ có ngoại lệ, dữ liệu không đầy đủ, hay một tích hợp vận hành chậm hơn dự kiến.

**Yêu cầu thích ứng (adaptive requirements)** là cách tiếp cận coi hiểu biết về yêu cầu như thứ có thể **phát triển dần qua bằng chứng**. Nhóm vẫn cần mục tiêu, thỏa thuận, tiêu chí chấp nhận và khả năng kiểm soát thay đổi; điểm khác biệt là nhóm chủ động kiểm chứng điều chưa biết, cập nhật quyết định và bàn giao giá trị theo từng phần.

Đây là một năng lực quan trọng trong **AGILE_DEVELOPMENT**: phát triển phần mềm thích ứng nhờ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục. User story, Product Backlog, Scrum, Kanban và các thực hành XP giúp chuyển nguyên tắc ấy thành những vòng học hỏi cụ thể.

Sau bài học, người học có thể:

- Phân biệt **nhu cầu, giả định, giải pháp đề xuất, yêu cầu đã thống nhất** và **bằng chứng**.
- Thiết kế vòng phản hồi để làm rõ những điểm chưa chắc chắn của yêu cầu.
- Viết và tinh chỉnh user story, ví dụ nghiệp vụ và tiêu chí chấp nhận theo hiểu biết mới.
- Điều chỉnh Product Backlog, phạm vi bàn giao và ưu tiên mà vẫn hướng tới mục tiêu sản phẩm.
- Xác định khi nào nên làm rõ thêm, khi nào nên kiểm chứng bằng một phần mềm hoạt động và khi nào phải xử lý rủi ro trước khi phát hành.

## 1. Yêu cầu phần mềm không xuất hiện đầy đủ ngay từ đầu

Một câu nói như “khách hàng cần đặt lịch lấy bưu kiện tại nhà” có vẻ rõ ràng nhưng chứa nhiều câu hỏi:

- Khách chọn **một thời điểm chính xác** hay **một khoảng thời gian**?
- Khung giờ có được xác nhận ngay không, hay phải chờ nhân viên điều phối?
- Nếu khu vực không có nhân viên hoặc lưu lượng tăng đột ngột, hệ thống thông báo thế nào?
- Khi khách sửa địa chỉ, lịch đã chọn có còn hợp lệ không?
- Khách muốn **đặt lịch nhanh** hay muốn **biết chắc khi nào nhân viên đến**?

Viết một tài liệu rất dài trước khi thử với người dùng có thể giúp ghi nhận nhiều quy tắc, nhưng không bảo đảm các giả định về nhu cầu và cách sử dụng là đúng. Ngược lại, bắt tay lập trình khi chưa hiểu những quy tắc ảnh hưởng đến tiền, an toàn hoặc tính nhất quán dữ liệu cũng có thể tạo rủi ro lớn.

### Những lớp thông tin khác nhau

| Lớp | Câu hỏi chính | Ví dụ dịch vụ nhận bưu kiện |
| --- | --- | --- |
| **Vấn đề / nhu cầu** | Người dùng đang cố đạt điều gì và gặp khó khăn gì? | Không muốn chờ cả ngày mà không biết lúc nào có người đến |
| **Mục tiêu sản phẩm** | Kết quả nào sẽ cho thấy sản phẩm tạo giá trị? | Người gửi chủ động lên lịch và nhận được xác nhận đáng tin cậy |
| **Giả định** | Điều gì nhóm cho là đúng nhưng chưa kiểm chứng? | Khách muốn chọn khung giờ 30 phút |
| **Phương án** | Có thể giải quyết vấn đề bằng cách nào? | Chọn khoảng hai giờ, gửi thời gian dự kiến, cho phép đổi lịch |
| **Quy tắc / ràng buộc** | Hành vi hoặc điều kiện bắt buộc là gì? | Không xác nhận vượt năng lực nhận hàng của khu vực |
| **Tiêu chí chấp nhận** | Làm sao biết hạng mục hoạt động đúng kỳ vọng? | Khi khung giờ hết chỗ, khách không thể nhận xác nhận cho khung đó |
| **Bằng chứng** | Điều gì quan sát được ủng hộ hoặc bác bỏ giả định? | Trong buổi thử, khách ưu tiên cam kết thời gian hơn độ chi tiết của khung giờ |

Phân biệt các lớp giúp tránh sai lầm phổ biến: **coi giải pháp do stakeholder đề xuất là nhu cầu đã được xác minh**. Nếu người vận hành yêu cầu “thêm nút gọi nhân viên”, nhóm cần tìm hiểu vấn đề đằng sau: có thể khách thiếu thông tin trạng thái, không nhất thiết thiếu nút gọi.

### Thích ứng không đồng nghĩa với thiếu kỷ luật

Yêu cầu phát triển dần không có nghĩa là:

- Không ghi lại quyết định và ngoại lệ quan trọng.
- Liên tục thay đổi công việc mà không đánh giá tác động.
- Bỏ qua chất lượng, bảo mật hoặc quy định bắt buộc.
- Để một ý kiến đơn lẻ lập tức quyết định hướng sản phẩm.
- Không có người chịu trách nhiệm về Product Backlog và ưu tiên.

**Nguyên tắc:** Chấp nhận rằng hiểu biết có thể thay đổi, đồng thời duy trì khả năng giải thích **vì sao** thay đổi, **dựa trên bằng chứng nào** và **ảnh hưởng đến phạm vi, chi phí, rủi ro ra sao**.

## 2. Tư duy thực nghiệm: từ sự chắc chắn giả định đến học hỏi có kiểm chứng

Nhóm thường gặp ba nhóm thông tin:

1. **Đã biết và có căn cứ:** Ví dụ quy định nghiệp vụ đã được phê duyệt, hoặc API có tài liệu và đã được thử tích hợp.
2. **Biết mình chưa biết:** Chẳng hạn chưa rõ người dùng chấp nhận thời gian chờ bao lâu hoặc hệ thống có xử lý được hai lượt đặt cuối cùng cùng lúc không.
3. **Chưa biết mình chưa biết:** Những tình huống chỉ xuất hiện khi người dùng thao tác, khi dữ liệu thực thay đổi hoặc khi hệ thống chạy trong điều kiện đặc biệt.

Không thể loại bỏ mọi bất định trước khi bắt đầu. Mục tiêu là **đưa bất định quan trọng ra ánh sáng sớm**, kiểm chứng với chi phí hợp lý và tránh đầu tư nhiều công việc phụ thuộc vào một giả định chưa đáng tin.

### Phân loại điều chưa biết trước khi quyết định

| Loại bất định | Ví dụ | Phản hồi có ích |
| --- | --- | --- |
| **Giá trị** | Người gửi có thật sự cần chọn giờ chính xác không? | Phỏng vấn theo tình huống, quan sát thao tác, đo hành vi |
| **Khả dụng** | Người dùng có phân biệt “yêu cầu đã gửi” và “lịch đã xác nhận”? | Bản mẫu có thể thử, kiểm thử khả dụng |
| **Nghiệp vụ** | Có thể hủy hoặc đổi lịch khi nhân viên đã nhận tuyến không? | Trao đổi với người có quyền quyết định chính sách, ví dụ ngoại lệ |
| **Kỹ thuật** | Hệ thống có chống được đặt vượt năng lực xử lý? | Thử nghiệm tích hợp, kiểm thử cạnh tranh đồng thời |
| **Vận hành** | Thời gian lấy hàng dự kiến có đáng tin khi trời mưa hoặc giao thông chậm? | Dữ liệu thực, quan sát độ trễ, thông tin điều phối |
| **Phối hợp** | Quyết định về ngoại lệ mất bao lâu? | Theo dõi thời gian chờ, công việc bị chặn và đầu mối chịu trách nhiệm |

Thường nên kiểm chứng trước những giả định **vừa có tác động lớn vừa thiếu bằng chứng**, nhất là khi kết quả có thể làm thay đổi cả giải pháp. Ví dụ, trước khi xây bộ chọn thời gian chính xác từng phút, nhóm nên tìm hiểu liệu khách thực sự cần độ chính xác ấy hay chỉ muốn một khoảng hẹn đáng tin.

## 3. Vòng phản hồi làm thay đổi hiểu biết về yêu cầu như thế nào?

Một vòng học hỏi hữu ích cần có **câu hỏi rõ**, **phép kiểm chứng phù hợp**, **bằng chứng có ngữ cảnh** và **quyết định tiếp theo**.

~~~mermaid
flowchart TD
    A["Hiểu vấn đề và mục tiêu"] --> B["Nêu giả định chưa chắc chắn"]
    B --> C["Chọn phép kiểm chứng nhỏ"]
    C --> D["Tạo bản mẫu / Increment / phép thử"]
    D --> E["Quan sát và thu thập bằng chứng"]
    E --> F{"Bằng chứng nói gì?"}
    F -->|"Ủng hộ"| G["Làm rõ hoặc mở rộng yêu cầu"]
    F -->|"Bác bỏ"| H["Đổi hướng giải pháp / ưu tiên"]
    F -->|"Chưa đủ"| I["Thiết kế lần kiểm chứng tiếp"]
    G --> J["Cập nhật backlog và quyết định"]
    H --> J
    I --> C
    J --> A
~~~

Vòng này có thể kéo dài vài giờ với một bài kiểm thử logic, vài ngày với bản mẫu, hoặc nhiều tuần với kết quả sử dụng cần quan sát theo chu kỳ. **Rút ngắn vòng phản hồi** nghĩa là giảm thời gian chờ không cần thiết để học điều quan trọng, không ép mọi quyết định dựa trên một mẫu quá nhỏ.

### Năm bước để đóng một vòng học hỏi

**Bước 1 — Ghi giả định dưới dạng có thể kiểm chứng.**

Thay vì “cần làm giao diện chọn giờ đẹp hơn”, hãy viết:

> Chúng tôi tin rằng người gửi bưu kiện bỏ dở yêu cầu vì họ không biết liệu khung giờ chọn có được xác nhận. Nếu trạng thái xác nhận được làm rõ, người gửi sẽ hoàn tất yêu cầu với ít lần phải liên hệ hỗ trợ hơn.

Giả thuyết cần gắn với một nhóm người dùng và tình huống cụ thể. Không nhất thiết dùng ngôn ngữ nghiên cứu quá trang trọng, nhưng phải biết điều gì có thể làm nhóm đổi ý.

**Bước 2 — Chọn phép kiểm chứng nhỏ nhất trả lời được câu hỏi.**

Nếu cần biết người dùng có hiểu trạng thái không, một bản mẫu có thể thử là đủ cho vòng đầu tiên. Nếu cần xác nhận không đặt vượt năng lực xử lý, phải có kiểm thử kỹ thuật và dữ liệu phù hợp. Không nên dùng phỏng vấn để “chứng minh” hệ thống an toàn dưới tải, hoặc dùng unit test để “chứng minh” người dùng thấy tính năng hữu ích.

**Bước 3 — Thu thập phản hồi.**

Khi quan sát, ghi cả kết quả lẫn bối cảnh: nhóm người được thử, tác vụ giao cho họ, thiết bị, thời điểm, lỗi kỹ thuật hoặc điều kiện tác động. Dữ liệu định tính giúp hiểu **vì sao**, còn số liệu định lượng giúp thấy **mức độ và xu hướng**.

**Bước 4 — Diễn giải và quyết định.**

Một người dùng không hiểu chữ “đã tiếp nhận” có thể là dấu hiệu cần sửa thông điệp; chưa đủ kết luận toàn bộ quy trình đặt lịch sai. Nhóm có thể quyết định giữ hướng đi, chỉnh thiết kế, mở rộng phép thử hoặc dừng một giả thuyết, kèm mức độ tin cậy.

**Bước 5 — Cập nhật những gì nhóm sẽ làm tiếp.**

Phản hồi có ích khi làm thay đổi user story, tiêu chí chấp nhận, Product Backlog, mức ưu tiên hoặc kế hoạch kiểm chứng. Một cuộc demo có nhiều ý kiến nhưng không có quyết định tiếp theo chỉ là **đầu vào**, chưa phải vòng học hỏi khép kín.

## 4. Thu thập phản hồi từ đúng nguồn

Không có một nguồn phản hồi duy nhất cho mọi loại yêu cầu. Ba lớp thường xuyên bổ sung cho nhau:

| Nguồn | Nhận được điều gì? | Có thể dùng cách nào? | Không nên kết luận điều gì chỉ từ nguồn này? |
| --- | --- | --- | --- |
| **Người dùng và nghiệp vụ** | Nhu cầu, quy tắc, trải nghiệm, điểm vướng | Quan sát tác vụ, phỏng vấn, trao đổi với chuyên gia nghiệp vụ, thử bản mẫu | Hệ thống chắc chắn đáp ứng tải hoặc chống được lỗi kỹ thuật |
| **Phần mềm đang phát triển** | Hành vi thực thi có đúng ví dụ và tương thích không? | Unit test, integration test, acceptance test, code review, CI | Tính năng chắc chắn tạo ra giá trị cho người dùng |
| **Hệ thống vận hành và hỗ trợ** | Điều gì xảy ra khi dùng thực tế, dưới dữ liệu và lưu lượng thật? | Metric, log, trace, ticket hỗ trợ, phát hành giới hạn | Một sự cố đơn lẻ là nguyên nhân của mọi vấn đề người dùng |

### Phỏng vấn: tìm hiểu tình huống, không chỉ hỏi giải pháp mong muốn

Câu hỏi “Bạn có muốn thêm nút đổi lịch không?” thường dẫn đến câu trả lời thuận chiều. Thay vào đó:

- “Lần gần nhất bạn muốn đổi lịch nhận hàng là khi nào?”
- “Khi đó bạn đã làm gì? Bước nào mất thời gian nhất?”
- “Bạn biết việc đổi lịch thành công bằng cách nào?”
- “Nếu không đổi được, hậu quả thực tế là gì?”

Những câu hỏi dựa trên trải nghiệm đã xảy ra thường giúp khám phá vấn đề và ràng buộc tốt hơn việc yêu cầu người dùng tự thiết kế sản phẩm. Vẫn cần kiểm chứng kết luận qua các nhóm và bối cảnh khác nhau.

### Bản mẫu: làm lộ cách hiểu sai trước khi lập trình sâu

Một bản mẫu cho phép người dùng thử nhiệm vụ như:

> “Bạn đã chọn khoảng 14:00–16:00. Hãy chỉ ra khi nào bạn biết chắc nhân viên sẽ đến và bạn có thể làm gì nếu cần đổi lịch.”

Người quan sát không nên hướng dẫn ngay khi người thử bị vướng, vì điều đó che đi khó khăn thực tế. Ghi lại nơi họ dừng, câu chữ họ hiểu khác và mục tiêu họ không hoàn thành.

### Kiểm thử: biến quyết định nghiệp vụ thành hành vi có thể kiểm chứng

Khi quy tắc nghiệp vụ được làm rõ, người phát triển và kiểm thử có thể đưa ví dụ thành bài kiểm thử. Việc này phát hiện cách hiểu khác nhau ngay trong quá trình xây dựng, đặc biệt ở tình huống biên như hai khách cùng chọn chỗ cuối cùng.

### Phát hành giới hạn: phát hiện điều chưa thấy trước đó

Sau khi đạt tiêu chuẩn chất lượng cần thiết, nhóm có thể đưa một khả năng đến nhóm người dùng phù hợp, quan sát kết quả, lỗi, phản hồi hỗ trợ và mức tải. Đó là bước kiểm chứng các giả định mà bản mẫu hoặc môi trường kiểm thử chưa trả lời được. Cần có điều kiện mở rộng hoặc dừng và cách giảm tác động nếu phát sinh vấn đề.

## 5. Ví dụ xuyên suốt: yêu cầu “đặt lịch nhận bưu kiện tại nhà”

Đây là **tình huống giả định phục vụ học tập**, với quy tắc và số liệu minh họa. Không coi những quy tắc dưới đây là chính sách của một doanh nghiệp cụ thể.

### 5.1. Đầu vào ban đầu: một đề xuất tưởng như đã rõ

Stakeholder nói:

> “Khách phải được chọn chính xác giờ nhân viên tới lấy bưu kiện. Hãy xây bộ chọn thời gian từng 15 phút.”

Nếu nhóm lập trình ngay, họ có thể mất nhiều công tạo bộ chọn giờ, tích hợp lịch nhân viên và xử lý giữ chỗ. Trước đó cần hỏi: **Vì sao khách cần chính xác từng 15 phút?**

Người phụ trách sản phẩm tìm hiểu một số trường hợp hỗ trợ. Khách nói họ thường phải đợi cả buổi và không biết yêu cầu có được xác nhận chưa. Đây là bằng chứng ban đầu cho một **nhu cầu khác**: khả năng dự đoán và tin cậy, chưa chắc là độ chính xác 15 phút.

Nhóm ghi:

| Nội dung | Ghi nhận sau trao đổi đầu tiên |
| --- | --- |
| Vấn đề | Người gửi không biết khoảng thời gian nhân viên sẽ đến và trạng thái xác nhận |
| Giả định A | Khoảng hẹn hai giờ đáng tin có thể tốt hơn một thời điểm chính xác nhưng thường bị trễ |
| Giả định B | Tách “đã gửi yêu cầu” và “đã xác nhận lịch” sẽ giảm nhầm lẫn |
| Rủi ro lớn | Xác nhận vượt năng lực nhận hàng khiến cả lịch và kỳ vọng người dùng sai |
| Chưa rõ | Khả năng giữ chỗ, chính sách đổi/hủy, thời hạn xác nhận, dữ liệu năng lực khu vực |

### 5.2. Vòng phản hồi thứ nhất: kiểm chứng vấn đề và trải nghiệm

Nhóm dựng bản mẫu gồm:

- Danh sách các **khoảng giờ có thể yêu cầu**.
- Trạng thái **“Đang chờ xác nhận”** sau khi gửi.
- Trạng thái **“Đã xác nhận: 14:00–16:00”** khi có xác nhận hợp lệ.
- Hướng dẫn rõ nếu lịch chưa thể xác nhận.

Người dùng thử tác vụ đặt lịch. Nhóm quan sát thấy có người tưởng nút “Gửi yêu cầu” đồng nghĩa với lịch đã chắc chắn; người khác muốn biết việc đổi lịch ảnh hưởng thế nào đến thời điểm nhân viên đến.

**Điều mới học:** Cần phân biệt rõ các trạng thái và giải thích mức độ cam kết. Nhóm sửa câu chữ và ưu tiên tìm hiểu **quy tắc xác nhận** thay vì chỉ thêm tùy chọn giờ chi tiết.

Không cần giả định toàn bộ người dùng đều có hành vi giống nhóm thử. Nếu mẫu nhỏ hoặc chỉ gồm người quen với công nghệ, nhóm phải ghi rõ giới hạn và tiếp tục quan sát ở đối tượng phù hợp.

### 5.3. Vòng phản hồi thứ hai: làm rõ quy tắc nghiệp vụ và kỹ thuật

Người điều phối cho biết một khu vực có **năng lực hữu hạn trong mỗi khoảng giờ**. Để có bài kiểm chứng cụ thể, nhóm thống nhất quy tắc ví dụ:

1. Một khung giờ ở khu vực A nhận tối đa **3 đơn đã xác nhận**.
2. Nếu đã đủ 3 đơn, khách tiếp theo không được nhận xác nhận cho khung đó.
3. “Đã gửi yêu cầu” **khác** “Đã xác nhận”; chỉ hiển thị xác nhận sau khi hệ thống giữ được năng lực xử lý.
4. Nếu hai yêu cầu cùng đến khi chỉ còn một chỗ, tối đa **một yêu cầu** được xác nhận.
5. Khi lỗi xảy ra, khách thấy trạng thái phù hợp và có thể thử lại theo hướng dẫn, không tự nhận lịch thành công.

Đây là quy tắc minh họa được **cùng nghiệp vụ quyết định**. Những vấn đề như thời hạn giữ chỗ, đổi địa chỉ, hủy sau khi nhân viên nhận tuyến và dữ liệu sai lệch phải được đánh dấu cần làm rõ; không nên để lập trình viên âm thầm tự chọn chính sách.

Nhóm tạo kiểm thử tích hợp cho tình huống hai yêu cầu đồng thời. Nếu cơ chế chỉ đọc “còn chỗ” rồi ghi nhận độc lập, cả hai có thể cùng được xác nhận, vượt giới hạn. Phản hồi kỹ thuật dẫn đến yêu cầu bổ sung về **tính nhất quán khi xác nhận**, đồng thời ảnh hưởng tới thông điệp trên giao diện.

### 5.4. Vòng phản hồi thứ ba: kiểm chứng khi vận hành

Sau khi Increment đáp ứng Definition of Done, nhóm mở tính năng cho một khu vực thử nghiệm có thể giám sát. Họ quan sát:

- Tỷ lệ yêu cầu được xác nhận hợp lệ.
- Tỷ lệ người dùng nhận biết đúng trạng thái yêu cầu.
- Khoảng thời gian từ khi gửi yêu cầu đến khi có kết quả.
- Số yêu cầu xác nhận thất bại và nguyên nhân.
- Số liên hệ hỗ trợ về lịch chưa rõ ràng, tính trên số yêu cầu liên quan.

Giả sử dữ liệu chỉ ra nhiều yêu cầu được xác nhận đúng nhưng thường xuyên trễ hẹn ở giờ cao điểm. **Điều mới học không còn nằm chủ yếu ở giao diện**, mà ở năng lực điều phối và độ đáng tin của khung giờ. Product Owner cùng nhóm vận hành có thể ưu tiên điều chỉnh cách phân bổ năng lực hoặc cách hứa thời gian, trước khi thêm tính năng chọn giờ chính xác hơn.

### 5.5. Chuỗi yêu cầu thay đổi vì điều gì?

| Thời điểm | Nhận thức / yêu cầu | Nguồn bằng chứng | Quyết định |
| --- | --- | --- | --- |
| Ban đầu | “Cho khách chọn từng 15 phút” | Đề xuất từ stakeholder | Kiểm chứng nhu cầu phía sau |
| Sau phỏng vấn và bản mẫu | Khách cần khoảng hẹn đáng tin, trạng thái rõ | Quan sát tác vụ và phản hồi người dùng | Ưu tiên khoảng giờ và xác nhận |
| Sau kiểm thử kỹ thuật | Phải ngăn xác nhận vượt năng lực khi có yêu cầu đồng thời | Kiểm thử tích hợp, phân tích rủi ro | Bổ sung quy tắc nhất quán và tiêu chí chấp nhận |
| Sau phát hành giới hạn | Chậm lấy hàng ở giờ cao điểm làm giảm niềm tin | Dữ liệu vận hành và hỗ trợ | Điều chỉnh quy tắc phân bổ năng lực và cách hứa lịch |

Nhóm không nhất thiết “đổi mục tiêu liên tục”. **Mục tiêu giá trị vẫn là người gửi chủ động hẹn và tin được lịch**, trong khi hiểu biết về cách đạt mục tiêu trở nên chính xác hơn qua từng vòng.

## 6. Từ phản hồi đến user story có thể bàn giao

Trong Agile, user story có thể dùng làm **đầu mối cuộc hội thoại về giá trị**. Một mẫu thường gặp:

> Là **[vai trò]**, tôi muốn **[khả năng]**, để **[giá trị hoặc mục tiêu]**.

Với ví dụ nhận bưu kiện:

> Là người gửi bưu kiện, tôi muốn biết yêu cầu lấy hàng của mình **đang chờ hay đã được xác nhận cho khoảng giờ nào**, để chủ động sắp xếp thời gian và tránh gửi yêu cầu trùng.

User story này có ý nghĩa hơn hạng mục “Tạo API status”, vì nó chỉ ra **người được hưởng lợi** và **điều cần làm được**. Dù vậy, story chưa đủ để triển khai an toàn. Cần trao đổi quy tắc và ví dụ chấp nhận.

### 6.1. Ba chữ C: Card, Conversation, Confirmation

Một mô hình phổ biến để hiểu user story là:

- **Card:** Mô tả ngắn gọn nhu cầu, đủ để gợi nhớ và ưu tiên.
- **Conversation:** Những cuộc trao đổi thường xuyên để khám phá quy tắc, tình huống và đánh đổi.
- **Confirmation:** Các ví dụ hoặc tiêu chí chấp nhận giúp xác nhận cách hiểu chung.

User story không phải một bản hợp đồng có thể hoàn thiện chỉ bằng điền đúng biểu mẫu. Khi bằng chứng mới làm thay đổi hiểu biết, nhóm cập nhật cả **cuộc hội thoại đã chốt thành quyết định** và **ví dụ kiểm chứng**.

### 6.2. Viết tiêu chí chấp nhận theo hành vi quan sát được

Một bộ tiêu chí chấp nhận minh họa cho story trên:

1. Sau khi gửi yêu cầu hợp lệ nhưng chưa có xác nhận, người dùng nhìn thấy **“Đang chờ xác nhận”**, không thấy thông báo chắc chắn có lịch.
2. Khi hệ thống xác nhận được năng lực xử lý, người dùng thấy **khoảng giờ, ngày, khu vực và mã yêu cầu**.
3. Nếu không thể xác nhận vì khung giờ đã đầy, người dùng nhận lý do dễ hiểu và có thể chọn khoảng giờ còn phù hợp.
4. Với hai yêu cầu đồng thời tranh cùng chỗ cuối cùng, hệ thống không xác nhận cả hai khi năng lực chỉ còn một chỗ.
5. Nếu truy vấn trạng thái thất bại tạm thời, giao diện không tự hiển thị “Đã xác nhận”; thông báo cho người dùng cách kiểm tra lại.

Cần thống nhất thêm những ràng buộc liên quan đến dữ liệu cá nhân, bảo mật và khả năng truy cập theo bối cảnh thực tế. Tiêu chí chấp nhận thường gắn với **một hạng mục**, còn **Definition of Done** là mô tả chính thức của tiêu chuẩn chất lượng cần đáp ứng để một Increment được coi là hoàn thành. Hai khái niệm bổ sung cho nhau.

### 6.3. Ví dụ Given–When–Then làm lộ bất đồng

~~~gherkin
Tính năng: Xác nhận khung giờ nhận bưu kiện

  Kịch bản: Yêu cầu được xác nhận khi còn năng lực
    Cho khung giờ 14:00-16:00 ở khu vực A còn 1 chỗ
    Và người gửi cung cấp địa chỉ hợp lệ trong khu vực A
    Khi người gửi yêu cầu khung giờ đó
    Và hệ thống giữ chỗ thành công theo quy tắc nghiệp vụ
    Thì yêu cầu hiển thị trạng thái "Đã xác nhận"
    Và thông tin xác nhận ghi rõ ngày, khung giờ và mã yêu cầu

  Kịch bản: Khung giờ đã đầy
    Cho khung giờ 14:00-16:00 ở khu vực A không còn chỗ
    Khi người gửi yêu cầu khung giờ đó
    Thì hệ thống không xác nhận lịch cho khung giờ đó
    Và người gửi được hướng dẫn chọn khung giờ khác

  Kịch bản: Chưa có kết quả xác nhận
    Cho một yêu cầu đã gửi nhưng chưa có kết quả giữ chỗ
    Khi người gửi mở trang theo dõi
    Thì hệ thống hiển thị trạng thái "Đang chờ xác nhận"
    Và không hiển thị lịch đã được xác nhận
~~~

Nhóm kiểm thử cần thêm trường hợp **hai yêu cầu cạnh tranh cùng lúc**, bản tin xác nhận trễ hoặc lặp, và thử lại sau khi mạng gián đoạn. Một số kịch bản phụ thuộc cách tổ chức giao dịch và tích hợp thực tế, nên không thể chỉ từ các dòng Gherkin suy ra hệ thống đã bảo đảm tính nhất quán.

### 6.4. Câu hỏi nào chưa cần chốt ngay?

Nhóm có thể chưa cần xây chức năng đổi lịch trong lát cắt đầu tiên, nhưng vẫn phải ghi nhận các phụ thuộc hoặc ràng buộc ảnh hưởng trực tiếp. Ví dụ, nếu hệ thống chưa cho đổi lịch, giao diện phải nói rõ giới hạn; không được tự tạo ấn tượng chức năng đã có.

**Làm rõ vừa đủ** nghĩa là đủ hiểu để xây một phần giá trị **an toàn, có thể kiểm chứng**, đồng thời giữ chỗ cho điều cần học ở vòng sau. Đây không phải lý do bỏ qua các trường hợp biên có thể gây hỏng dữ liệu, vi phạm chính sách hoặc làm người dùng chịu rủi ro.

## 7. Refinement: điều chỉnh Product Backlog bằng điều vừa học

**Product Backlog refinement** là hoạt động liên tục chia nhỏ và làm rõ các Product Backlog Item. Nhóm có thể bổ sung mô tả, thứ tự ưu tiên, kích thước và thông tin cần thiết khi đến gần thời điểm thực hiện.

Trong **Scrum**, Product Backlog là danh sách công việc cần thiết để cải thiện sản phẩm, được sắp xếp thứ tự và luôn phát triển. **Product Owner chịu trách nhiệm quản lý Product Backlog hiệu quả**; Developers và những người có hiểu biết phù hợp tham gia làm rõ. Product Backlog không phải bản kế hoạch đóng băng ngay đầu dự án.

### 7.1. Từ một ý tưởng lớn đến các lát cắt phản hồi được

Ý tưởng ban đầu:

> “Xây hệ thống nhận bưu kiện tại nhà đầy đủ, có chọn giờ, đổi lịch, thông báo, phân tuyến và báo cáo.”

Đây là phạm vi quá rộng để kiểm chứng một giả định trong thời gian ngắn. Nhóm có thể chọn các **lát cắt dọc**:

| Lát cắt | Khả năng người dùng hoặc hệ thống đạt được | Điều có thể học |
| --- | --- | --- |
| 1 | Người gửi xem các khoảng hẹn có thể yêu cầu tại một khu vực thí điểm | Người dùng có hiểu các lựa chọn và có nhu cầu với chúng không? |
| 2 | Người gửi gửi yêu cầu và nhìn thấy trạng thái xử lý rõ ràng | Họ có phân biệt được yêu cầu đã gửi với lịch đã xác nhận không? |
| 3 | Hệ thống xác nhận khi có năng lực, ngăn đặt vượt giới hạn | Quy tắc và cơ chế tích hợp có đủ tin cậy không? |
| 4 | Người gửi nhận thông báo khi trạng thái thay đổi | Thông báo có giảm nhu cầu hỏi hỗ trợ không? |
| 5 | Người gửi đổi lịch trong những điều kiện đã thống nhất | Những ngoại lệ nào có ảnh hưởng cao và cần xử lý? |

Đây là **gợi ý phân tách**, không phải trình tự luôn đúng. Tùy rủi ro và hệ thống hiện có, phần xác nhận và kiểm soát năng lực có thể phải đi cùng lát cắt đầu tiên để bảo đảm không gây hại. Khi cần, nhóm kiểm chứng kỹ thuật trong môi trường an toàn trước khi cho người dùng đặt thật.

Một **lát cắt dọc (vertical slice)** nên tạo ra một hành vi hoặc luồng có ý nghĩa từ đầu đến cuối. Chia theo “xong cơ sở dữ liệu, xong backend, xong frontend” có thể thuận tiện cho tổ chức công việc, nhưng mỗi phần kỹ thuật riêng lẻ chưa chắc trả lời câu hỏi về giá trị người dùng.

### 7.2. Dùng INVEST như câu hỏi kiểm tra chất lượng story

Một cách đánh giá user story thường gặp là **INVEST**:

| Chữ | Ý nghĩa | Câu hỏi khi làm rõ yêu cầu |
| --- | --- | --- |
| **I – Independent** | Tương đối độc lập | Có thể giảm phụ thuộc hoặc tách phần giao giá trị được không? |
| **N – Negotiable** | Có thể thương lượng | Nhóm còn không gian trao đổi giải pháp và phạm vi không? |
| **V – Valuable** | Tạo giá trị | Ai hưởng lợi và vì sao phần này đáng làm? |
| **E – Estimable** | Có thể ước lượng | Còn bất định nào khiến nhóm chưa dự báo được kích thước? |
| **S – Small** | Đủ nhỏ | Có thể hoàn thành và kiểm chứng trong vòng làm việc phù hợp không? |
| **T – Testable** | Có thể kiểm chứng | Biết điều gì chứng minh hành vi mong đợi được đáp ứng không? |

INVEST là **hướng dẫn suy nghĩ**, không phải bộ luật bắt buộc mọi Product Backlog Item phải thỏa tuyệt đối. Một công việc giảm rủi ro hạ tầng hoặc nghiên cứu kỹ thuật không phải lúc nào cũng phù hợp với mẫu user story, nhưng vẫn có thể rất quan trọng cho Product Goal.

### 7.3. Quyết định ưu tiên theo giá trị, rủi ro và khả năng học hỏi

Khi phản hồi làm xuất hiện yêu cầu mới, đừng mặc định thêm nó vào đầu backlog. Hãy đánh giá:

- **Liên quan mục tiêu:** Điều mới có giúp giải quyết vấn đề người dùng và tiến tới Product Goal không?
- **Tác động và mức độ khẩn cấp:** Nếu không xử lý, người dùng hoặc hệ thống gặp hậu quả gì?
- **Mức độ tin cậy:** Đây là sự kiện đã quan sát hay chỉ là ý kiến / giả định?
- **Chi phí cơ hội:** Chọn nó đồng nghĩa trì hoãn việc gì?
- **Bất định:** Có thể thử một phép kiểm chứng rẻ hơn trước khi cam kết lớn không?
- **Phụ thuộc:** Có rủi ro kỹ thuật, nghiệp vụ hoặc vận hành cần tháo gỡ trước không?

**Phản hồi không tự động trở thành yêu cầu phải thực hiện.** Phản hồi là thông tin đầu vào; người có trách nhiệm sản phẩm phải xem xét, sắp xếp thứ tự và giải thích các đánh đổi.

## 8. Quy tắc được phát hiện dần: ghi sao cho không mất tri thức?

Điều nguy hiểm là thảo luận rất nhiều nhưng quyết định chỉ nằm trong tin nhắn riêng hoặc trí nhớ một người. Cách ghi chép nên **đủ nhẹ để cập nhật thường xuyên** và **đủ rõ để kiểm tra lại**.

### 8.1. Nhật ký giả định và bằng chứng

Một bản ghi ngắn có thể gồm:

| Trường | Ví dụ |
| --- | --- |
| Mã hoặc tên | ASSUMPTION-07 – Mức chính xác của khung giờ |
| Câu hỏi | Khách có thật sự cần khung 15 phút không? |
| Giả định hiện tại | Khoảng hai giờ đáng tin hữu ích hơn giờ chính xác nhưng dễ trễ |
| Cách kiểm chứng | Phỏng vấn các tình huống gần đây, thử hai cách hiển thị trên bản mẫu |
| Bằng chứng | Phần lớn người thử ưu tiên biết lịch đã xác nhận; cần kiểm chứng thêm ở nhóm khách đặc thù |
| Mức tin cậy | Sơ bộ, mẫu nhỏ và chưa đại diện toàn bộ khu vực |
| Quyết định | Làm lát cắt hai giờ cho thí điểm; tiếp tục theo dõi nhu cầu hẹn chính xác |
| Người theo dõi / thời điểm xem lại | Product Owner và nhóm nghiên cứu khi có dữ liệu thí điểm |

Không nhất thiết biến mọi câu hỏi thành tài liệu dài. Điều đáng giữ là **giả định, bằng chứng, quyết định, giới hạn và bước tiếp theo**.

### 8.2. Quyết định nghiệp vụ và dấu vết thay đổi

Một mẫu ngắn:

~~~text
Vấn đề:
  Hai khách chọn chỗ cuối cùng trong cùng khung giờ.

Quy tắc đã thống nhất:
  Không xác nhận quá năng lực khu vực.

Điều kiện áp dụng:
  Khu vực A, các khoảng giờ được hệ thống điều phối quản lý.

Ví dụ:
  Chỉ còn 1 chỗ; 2 yêu cầu đồng thời -> tối đa 1 xác nhận.

Người quyết định:
  Người phụ trách chính sách điều phối nhận hàng.

Việc cần làm:
  Cập nhật acceptance criteria và integration test;
  xác định trải nghiệm cho yêu cầu không được xác nhận.
~~~

Khi quy tắc thay đổi, nên lưu được **lý do và thời điểm có hiệu lực** nếu chúng quan trọng với vận hành, kiểm toán hoặc hỗ trợ. Quyết định về quyền truy cập, tiền, dữ liệu cá nhân và chính sách có thể cần phê duyệt chính thức theo tổ chức; Agile không loại bỏ các trách nhiệm đó.

### 8.3. Các tiêu chí chấp nhận phải phản ánh điều đã thống nhất

Nếu nhóm đổi từ “xác nhận ngay sau khi nhấn nút” sang “xác nhận sau khi giữ được năng lực”, cần cập nhật không chỉ giao diện mà cả:

1. User story và tiêu chí chấp nhận liên quan.
2. Ví dụ kiểm thử, kể cả trường hợp bị từ chối và xử lý đồng thời.
3. Sự kiện đo lường, để không nhầm “gửi yêu cầu” với “lịch thành công”.
4. Thông báo tới người dùng và tài liệu hỗ trợ.
5. Các tích hợp phụ thuộc vào trạng thái xác nhận.

**Nhất quán giữa yêu cầu, kiểm thử và hành vi quan sát** giúp nhóm tránh tình trạng tài liệu cập nhật nhưng mã vẫn dùng quy tắc cũ, hoặc mã đổi nhưng báo cáo đo lường chưa được điều chỉnh.

## 9. Cộng tác: ai cùng phát triển hiểu biết về yêu cầu?

Yêu cầu thích ứng không phải trách nhiệm riêng của Business Analyst hay Product Owner. Mỗi góc nhìn có những điều cần đưa vào vòng học hỏi:

| Vai trò / góc nhìn | Đóng góp quan trọng |
| --- | --- |
| Người dùng / khách hàng | Tình huống sử dụng thực tế, hành vi, khó khăn, phản hồi về giá trị |
| Stakeholder và chuyên gia nghiệp vụ | Quy tắc, chính sách, ràng buộc, mục tiêu tổ chức |
| Product Owner | Tạo sự rõ ràng về mục tiêu và thứ tự Product Backlog; cân nhắc giá trị, rủi ro và cơ hội |
| Developers | Phương án kỹ thuật, giới hạn hệ thống, cách chia lát cắt, thiết kế kiểm chứng |
| Người kiểm thử | Ví dụ, trường hợp biên, rủi ro và bằng chứng về hành vi được chấp nhận |
| Thiết kế trải nghiệm | Cách người dùng hiểu giao diện và luồng thao tác |
| Vận hành / hỗ trợ | Lỗi thực tế, phụ thuộc hạ tầng, phản hồi khách hàng, khả năng phục hồi |

Trong Scrum, **Product Owner là một người chịu trách nhiệm Product Backlog**, nhưng trách nhiệm ấy không có nghĩa là Product Owner phải tự biết mọi quy tắc nghiệp vụ hoặc tự thiết kế mọi giải pháp. Nhóm cần mở đường để thông tin từ đúng chuyên gia đến đúng người khi cần quyết định.

### Trao đổi sớm, ghi quyết định ngắn gọn

Ví dụ một câu hỏi hiệu quả từ Developers:

> “Trong story xác nhận lịch, khi khu vực chỉ còn một chỗ và hai yêu cầu đến đồng thời, nghiệp vụ muốn tối đa một xác nhận hay cho phép danh sách chờ? Nếu chưa có quyết định, việc triển khai phần xác nhận đang bị chặn. Nhóm đề xuất giữ đúng năng lực và trả về trạng thái chưa xác nhận cho yêu cầu còn lại.”

Câu hỏi này nêu bối cảnh, trường hợp cụ thể, phương án và tác động. Người có quyền về nghiệp vụ có thể quyết định nhanh hơn nhiều so với câu “xử lý hết chỗ thế nào?” gửi thiếu ngữ cảnh.

Nhóm nên thống nhất **đầu mối trả lời, thời gian phản hồi phù hợp và cách ghi quyết định**. Không cần tổ chức cuộc họp lớn cho mọi câu hỏi, nhưng cũng không nên để những vấn đề đang chặn công việc phải chờ đến cuối Sprint.

## 10. Scrum, Kanban và XP hỗ trợ yêu cầu thích ứng ra sao?

### 10.1. Scrum: kiểm tra và thích ứng Product Backlog

Trong Scrum, ba nền tảng thực nghiệm là **minh bạch, kiểm tra và thích ứng**. Việc phát triển hiểu biết về yêu cầu xuất hiện ở nhiều điểm:

- **Product Backlog refinement:** Liên tục làm rõ và chia nhỏ Product Backlog Item theo hiểu biết mới, không phải chỉ một cuộc họp bắt buộc vào ngày cố định.
- **Sprint Planning:** Scrum Team thống nhất **Sprint Goal**, chọn công việc và xây dựng kế hoạch dựa trên ưu tiên và thông tin hiện có.
- **Trong Sprint:** Developers có thể trao đổi và thương lượng phạm vi Sprint Backlog với Product Owner khi hiểu biết thay đổi, trong khi không làm ảnh hưởng Sprint Goal.
- **Daily Scrum:** Developers kiểm tra tiến độ hướng tới Sprint Goal, điều chỉnh kế hoạch; đây không phải buổi duyệt mọi yêu cầu mới.
- **Sprint Review:** Scrum Team và stakeholder xem sản phẩm cùng bối cảnh thay đổi, thảo luận điều học được và điều chỉnh Product Backlog khi cần.
- **Sprint Retrospective:** Nhóm xem lại cách phối hợp và quy trình để những vòng học hỏi tiếp theo hiệu quả hơn.

**Điểm cần phân biệt:** Sprint Goal tạo sự tập trung và ổn định tương đối trong một Sprint. Khi phát hiện yêu cầu mới, không có nghĩa là phải đưa mọi đề xuất vào Sprint đang chạy. Product Owner và Developers cần đánh giá tác động, khả năng giữ Sprint Goal và thời điểm phù hợp để làm tiếp.

### 10.2. Kanban: nhìn thấy yêu cầu bị chặn và luồng làm rõ

Trong một luồng có yêu cầu đến liên tục, nhóm có thể dùng Kanban:

~~~text
Ý tưởng / Phản hồi
       ↓
Cần xác minh vấn đề → Cần làm rõ quy tắc → Sẵn sàng → Đang làm
                                                   ↓
                                            Kiểm thử / Xem kết quả
                                                   ↓
                                              Bàn giao / Học hỏi
~~~

Chính sách rõ ràng giúp biết:

- Khi nào một yêu cầu có đủ thông tin để kéo vào làm?
- Ai trả lời câu hỏi khi thiếu quy tắc?
- Hạng mục bị chặn được đánh dấu và xử lý thế nào?
- Khi nào cần đưa hạng mục trở lại bước khám phá?
- Nhóm giới hạn **WIP (work in progress)** ở những trạng thái nào?

Theo dõi thời gian hạng mục chờ làm rõ giúp tìm ra nút thắt. Tuy nhiên, **giảm thời gian chờ bằng cách tự đoán yêu cầu** không phải cải tiến đáng tin cậy. Cần giảm chờ thông qua khả năng tiếp cận thông tin và người ra quyết định.

### 10.3. XP: kiểm chứng các hiểu biết mới gần thời điểm viết mã

Các thực hành của **Extreme Programming (XP)** có thể giúp vòng phản hồi kỹ thuật ngắn hơn:

- **TDD (Test-Driven Development):** Mô tả hành vi bằng bài kiểm thử, làm kiểm thử đạt và cải thiện mã trong khi giữ hành vi.
- **Kiểm thử chấp nhận từ ví dụ:** Người hiểu nghiệp vụ, Developers và kiểm thử cùng thống nhất tình huống mong đợi.
- **Lập trình cặp:** Nhận phản hồi về thiết kế và cách hiện thực ngay trong lúc làm.
- **Tích hợp liên tục:** Kiểm tra những thay đổi nhỏ thường xuyên, phát hiện lỗi tương thích sớm.
- **Tái cấu trúc:** Cải thiện thiết kế bên trong khi có sự bảo vệ của kiểm thử, giúp hệ thống dễ thích ứng với hiểu biết mới.

XP không thay thế việc khám phá giá trị người dùng. Kiểm thử có thể chứng minh quy tắc đã thống nhất được hiện thực trong phạm vi kiểm tra; **người dùng và dữ liệu thực tế** vẫn cần xác nhận quy tắc đó có tạo giá trị không.

## 11. Đo xem vòng phản hồi yêu cầu có hiệu quả không

Không nên đánh giá chất lượng khám phá yêu cầu chỉ bằng **số trang tài liệu**, **số câu hỏi đã trả lời** hoặc **số story được tạo**. Những con số ấy không cho biết hiểu biết có tiến triển đúng hướng hay không.

| Chỉ số / tín hiệu | Nó giúp thấy điều gì? | Cần tránh hiểu sai |
| --- | --- | --- |
| **Time to feedback** | Từ lúc đưa giả định ra kiểm chứng đến khi nhận được tín hiệu sử dụng được | Nhanh không đồng nghĩa đủ tin cậy |
| **Time to decision** | Từ lúc có câu hỏi cần quyết định đến lúc các bên thống nhất hướng xử lý | Chốt nhanh nhưng thiếu người có quyền / chuyên môn có thể gây làm lại |
| **Thời gian bị chặn do chưa rõ yêu cầu** | Khoảng chờ đang làm chậm dòng công việc ở đâu | Không dùng để quy trách nhiệm cá nhân khi chính sách phối hợp có vấn đề |
| **Làm lại vì khác cách hiểu** | Mức hao phí do diễn giải quy tắc không thống nhất | Không xem mọi thay đổi dựa trên học hỏi là thất bại |
| **Cycle time / lead time** | Công việc đi qua quy trình mất bao lâu theo mốc nhóm định nghĩa | Giảm bằng cách bỏ kiểm thử có thể làm tăng rủi ro |
| **Số giả định quan trọng đã được kiểm chứng** | Nhóm đang giảm bất định nào? | Không chạy theo số lượng phép thử nhỏ vô nghĩa |
| **Outcome người dùng** | Thay đổi có cải thiện khả năng hoàn thành tác vụ và giá trị không? | Không suy từ vài kết quả riêng lẻ ra kết luận chắc chắn |
| **Chỉ số bảo vệ chất lượng** | Giá trị có đi kèm lỗi, sự cố hoặc tổn hại khác không? | Không bỏ qua khi chỉ số kinh doanh chính đang tăng |

### Ví dụ về thời gian chờ

Giả sử một story cần:

| Hoạt động | Thời gian minh họa |
| --- | ---: |
| Làm rõ quy tắc có ảnh hưởng đến cách xác nhận | 3 ngày chờ |
| Phát triển và kiểm thử | 2 ngày |
| Chờ nghiệm thu ví dụ nghiệp vụ | 2 ngày |
| Triển khai và nhận phản hồi ban đầu | 1 ngày |
| **Tổng theo mô hình tuần tự** | **8 ngày** |

Nếu nhóm có đầu mối nghiệp vụ tham gia trao đổi ngắn đúng lúc và có ví dụ kiểm thử chấp nhận chung, thời gian chờ hai lần làm rõ có thể giảm đáng kể mà **không cần rút bớt kiểm thử**. Đây là số giả định minh họa; việc đo trong thực tế cần phân biệt ngày làm việc, ngày lịch, công việc song song và thời gian quan sát sau triển khai.

### Quan sát xu hướng thay vì đánh giá một lần

Một phản hồi mâu thuẫn không nhất thiết chứng minh sản phẩm sai; một kết quả kiểm thử xanh không chứng minh nhu cầu đúng. Nên xem **nhiều nguồn bằng chứng**, theo dõi xu hướng và ghi điều kiện đo. Đặc biệt với thử nghiệm thay đổi hành vi, cần cân nhắc nhóm người dùng, số quan sát và khoảng thời gian trước khi ra quyết định đầu tư lớn.

## 12. Những phản mẫu thường làm hỏng việc phát triển yêu cầu

| Phản mẫu | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| “Đã ký yêu cầu, không được hỏi thêm” | Cách hiểu sai kéo dài đến lúc nghiệm thu | Giữ khả năng làm rõ và ghi quyết định thay đổi có trách nhiệm |
| “Agile nên không cần tài liệu gì” | Quy tắc và quyết định biến mất khi thành viên thay đổi | Ghi ngắn giả định, ví dụ, quyết định và tiêu chí chấp nhận |
| Mọi góp ý người dùng đều thành backlog item ưu tiên cao | Mục tiêu sản phẩm bị loãng và thay đổi liên tục | Phân biệt dữ liệu đầu vào với quyết định ưu tiên |
| Hỏi người dùng muốn nút gì thay vì vấn đề thực tế | Dễ xây giải pháp được gợi ý nhưng không tạo giá trị | Hỏi tình huống gần đây, mục tiêu và cách người dùng đang xử lý |
| Chia việc chỉ theo lớp kỹ thuật | Phải đợi tích hợp dài mới thấy giá trị | Cắt lát nhỏ có hành vi đầu cuối và kiểm chứng được |
| Chỉ viết tiêu chí cho tình huống lý tưởng | Ngoại lệ gây lỗi, tranh cãi và làm lại | Dùng ví dụ biên, dữ liệu sai, đồng thời, phụ thuộc thất bại |
| Chờ cuối Sprint mới làm rõ yêu cầu đang chặn việc | Thời gian chờ lớn dù đội có họp thường xuyên | Thiết lập đầu mối và kênh giải đáp sớm |
| Đổi phạm vi Sprint sau mỗi ý kiến mới | Mất tập trung và khó đạt Sprint Goal | Đánh giá tác động, thương lượng với Product Owner, ưu tiên backlog |
| Dùng mẫu khảo sát nhỏ để kết luận chắc chắn | Quyết định dựa trên tín hiệu thiếu đại diện | Ghi giới hạn và tiếp tục kiểm chứng ở nhóm phù hợp |
| Thay đổi quy tắc mà không cập nhật kiểm thử và tài liệu hỗ trợ | Hệ thống có nhiều cách hiểu mâu thuẫn | Liên kết story, acceptance criteria, test và thông điệp người dùng |
| Phát hành gấp khi chưa xử lý rủi ro nghiêm trọng | Sai dữ liệu hoặc phá vỡ niềm tin người dùng | Giữ Definition of Done và điều kiện phát hành an toàn |

## 13. Bài thực hành: làm rõ yêu cầu bằng ba vòng phản hồi

**Bối cảnh:** Một nền tảng học trực tuyến nhận yêu cầu “thêm chức năng nhắc học viên vì nhiều người chưa hoàn thành bài đầu tiên”. Đội chưa biết vì sao học viên không bắt đầu học, nhắc qua kênh nào có ích, hoặc liệu lỗi lưu tiến độ đang khiến người học phải làm lại.

### Nhiệm vụ 1 — Tách vấn đề, giả định và giải pháp

Hãy điền vào bảng:

| Loại thông tin | Câu trả lời đề xuất |
| --- | --- |
| Vấn đề quan sát | Nhiều người đăng ký nhưng chưa hoàn thành bài đầu tiên |
| Giả định A | Học viên quên quay lại sau khi đăng ký |
| Giả định B | Học viên không tìm thấy bài phù hợp để bắt đầu |
| Giả định C | Tiến độ lưu không đúng nên họ mất động lực |
| Giải pháp được đề xuất ban đầu | Gửi thông báo nhắc học |
| Kết quả cần kiểm chứng | Nhiều học viên thật sự bắt đầu và hoàn tất bài đầu tiên hơn, không tăng phản hồi khó chịu vì thông báo |

**Câu hỏi:** Nếu chỉ xây thông báo nhắc học ngay, nhóm đang mặc định giả định nào đúng? Có thể kiểm tra giả định đó với chi phí thấp hơn bằng cách nào?

### Nhiệm vụ 2 — Thiết kế ba vòng phản hồi

| Vòng | Câu hỏi | Phép kiểm chứng gợi ý | Quyết định có thể thay đổi |
| --- | --- | --- | --- |
| 1 – Người dùng | Vì sao học viên chưa bắt đầu? | Phỏng vấn theo tình huống và quan sát học viên mới tìm bài đầu tiên | Ưu tiên tìm bài, nội dung hay thông báo |
| 2 – Phần mềm | Tiến độ hoàn thành có được lưu và hiển thị đúng? | Kiểm thử logic lưu tiến độ, mất mạng, tải lại trang, nhiều thiết bị | Sửa lỗi trước khi đầu tư thêm vào nhắc học |
| 3 – Sử dụng thực tế | Thay đổi nhỏ có cải thiện việc hoàn tất bài đầu tiên không? | Phát hành giới hạn, quan sát tỷ lệ hoàn tất theo định nghĩa ổn định | Mở rộng, điều chỉnh hoặc dừng giải pháp |

Với mỗi vòng, hãy viết **giả định, nguồn bằng chứng, thời điểm xem xét, giới hạn và hành động tiếp theo**. Nếu vòng 1 cho thấy nhiều người không hiểu nên chọn bài nào, nhóm có thể thử **gợi ý bài khởi đầu** trước khi gửi thêm thông báo.

### Nhiệm vụ 3 — Viết một user story và ba tiêu chí chấp nhận

Ví dụ:

> Là học viên mới, tôi muốn biết bài học phù hợp để bắt đầu và nhìn thấy tiến độ đã được lưu, để có thể tiếp tục học mà không phải tìm lại từ đầu.

Tiêu chí có thể gồm:

1. Khi học viên mở trang sau đăng ký, hệ thống hiển thị đường dẫn rõ tới bài được chọn theo quy tắc đã thống nhất.
2. Khi hoàn tất bài, tiến độ được lưu và hiển thị nhất quán sau khi tải lại.
3. Khi việc lưu tiến độ gặp lỗi, giao diện không báo thành công sai và hướng dẫn cách thử lại.

Hãy chỉ ra **quy tắc nào còn thiếu** (ví dụ “bài phù hợp” xác định bằng gì, tiến độ “hoàn tất” có nghĩa là gì), **ai cần quyết định** và **kiểm thử nào có thể làm lộ lỗi**.

### Nhiệm vụ 4 — Ưu tiên lại backlog khi có bằng chứng mới

Giả sử kết quả các vòng như sau:

- Một số học viên nói họ không cần nhắc; họ bỏ dở vì bài khởi đầu quá dài.
- Kiểm thử cho thấy tiến độ không được lưu khi mạng mất giữa chừng.
- Dữ liệu thí điểm chưa đủ lớn để kết luận tác động của thông báo nhắc học.

Hãy chọn một thứ tự xử lý có giải thích. Một cách hợp lý là **xem mức ảnh hưởng của lỗi mất tiến độ và sửa rủi ro dữ liệu cần thiết**, tiếp tục kiểm chứng cách chia bài và trải nghiệm bắt đầu, rồi cân nhắc thông báo khi có bằng chứng rõ hơn. Thứ tự cuối cùng còn phụ thuộc mức độ nghiêm trọng, lượng người bị ảnh hưởng và mục tiêu sản phẩm; bài học không giả định có một thứ tự luôn đúng.

## 14. Mẫu làm việc ngắn cho một nhóm Agile

Trước khi kéo một hạng mục quan trọng vào thực hiện, nhóm có thể tự hỏi:

- [ ] **Giá trị:** Ai đang gặp vấn đề gì? Điều gì sẽ cải thiện nếu giải quyết?
- [ ] **Bằng chứng:** Phần nào đã biết chắc, phần nào vẫn là giả định?
- [ ] **Rủi ro:** Có quy tắc hoặc giới hạn nào ảnh hưởng chất lượng, an toàn, bảo mật, tiền hoặc dữ liệu không?
- [ ] **Lát cắt:** Phần dùng được nhỏ nhất có thể kiểm chứng là gì?
- [ ] **Trao đổi:** Ai có thông tin và quyền quyết định khi gặp ngoại lệ?
- [ ] **Tiêu chí chấp nhận:** Có ví dụ cho luồng chính, điều kiện biên và trường hợp lỗi quan trọng chưa?
- [ ] **Definition of Done:** Phần bàn giao sẽ đáp ứng những tiêu chuẩn chất lượng nào?
- [ ] **Phản hồi:** Ai sẽ thử, quan sát điều gì, vào lúc nào?
- [ ] **Thích ứng:** Bằng chứng mới sẽ dẫn tới quyết định và cập nhật backlog thế nào?

Không phải checklist này phải được điền thành một biểu mẫu dài cho mọi lỗi nhỏ. Nó là cách nhắc nhóm **đặt đúng câu hỏi ở đúng thời điểm**, nhất là với hạng mục ảnh hưởng lớn và chưa có nhiều bằng chứng.

## 15. Câu hỏi tự kiểm tra

1. Vì sao một tài liệu yêu cầu được viết rất chi tiết vẫn có thể bỏ sót nhu cầu thực tế của người dùng?
2. Điểm khác nhau giữa *nhu cầu*, *giải pháp đề xuất*, *giả định* và *tiêu chí chấp nhận* là gì?
3. Trong ví dụ nhận bưu kiện, phản hồi nào khiến nhóm chuyển trọng tâm từ “chọn giờ thật chính xác” sang “xác nhận đáng tin cậy”?
4. Một cuộc phỏng vấn người dùng có thể xác nhận cơ chế chống đặt trùng đã đúng về kỹ thuật không? Cần kiểm chứng bằng gì?
5. Ba chữ C của user story đóng vai trò thế nào khi hiểu biết về yêu cầu thay đổi?
6. Tại sao tiêu chí chấp nhận không thay thế Definition of Done?
7. Product Backlog refinement hỗ trợ việc hiểu yêu cầu phát triển dần ra sao?
8. Khi một stakeholder có góp ý mới giữa Sprint, nhóm có bắt buộc đưa ngay góp ý ấy vào Sprint Backlog không?
9. Nếu mất ba ngày chờ làm rõ nghiệp vụ và chỉ một ngày lập trình, nhóm nên kiểm tra nút thắt ở đâu?
10. Những dấu hiệu nào cho thấy nhóm đang **học được điều mới có giá trị**, thay vì chỉ tạo thêm nhiều story và cuộc họp?

**Ghi nhớ:** Yêu cầu thích ứng không bắt đầu bằng việc phủ nhận kế hoạch hay tài liệu. Nó bắt đầu bằng sự thừa nhận rằng **hiểu biết về vấn đề và giải pháp luôn có thể được cải thiện**. Trong Agile, nhóm liên tục làm rõ giả định, đưa ra lát cắt có thể kiểm chứng, nhận phản hồi từ người dùng, phần mềm và vận hành, rồi cập nhật user story, tiêu chí chấp nhận và Product Backlog. **Mỗi vòng phản hồi cần giúp nhóm đưa ra quyết định tốt hơn**, trong khi vẫn bảo đảm chất lượng và giữ hướng đi tới giá trị sản phẩm.
