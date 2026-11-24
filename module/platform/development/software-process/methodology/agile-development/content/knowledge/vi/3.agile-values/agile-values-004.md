# Ứng phó thay đổi so với bám theo kế hoạch

> **Chương:** Giá trị Agile  
> **Học phần:** AGILE_DEVELOPMENT — phát triển phần mềm thích ứng thông qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục.

Trong phát triển phần mềm, kế hoạch thường được lập khi nhóm **biết ít nhất** về hành vi của người dùng, độ phức tạp kỹ thuật và điều kiện vận hành. Sau khi tạo một phần sản phẩm, kiểm thử và nhận phản hồi, nhóm biết thêm những điều có thể khiến kế hoạch ban đầu không còn phù hợp. Nếu cứ cố hoàn thành đúng danh sách chức năng đã chốt, nhóm có thể giao hàng đúng lịch nhưng lại giải quyết sai vấn đề.

Giá trị thứ tư trong **Tuyên ngôn Agile (Agile Manifesto)** là:

> **Responding to change over following a plan.**  
> Ưu tiên **ứng phó với thay đổi** hơn **bám theo kế hoạch**.

Tuyên ngôn cũng nói rõ rằng vế bên phải vẫn có giá trị. Do đó, Agile **không yêu cầu bỏ lập kế hoạch** và cũng không khuyến khích đổi hướng bất cứ khi nào có ý kiến mới. Nhóm cần có mục tiêu và kế hoạch đủ rõ để phối hợp, đồng thời chủ động điều chỉnh cách thực hiện khi có bằng chứng đáng tin cậy.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao khả năng ứng phó với thay đổi là một giá trị cốt lõi của Agile.
2. Phân biệt mục tiêu, giả định, kế hoạch, phạm vi công việc và ràng buộc bắt buộc.
3. Đánh giá một thay đổi dựa trên giá trị kỳ vọng, bằng chứng, chi phí, rủi ro và ảnh hưởng tới công việc đang làm.
4. Vận dụng Product Backlog và Sprint Goal trong Scrum, giới hạn WIP trong Kanban, các thực hành kỹ thuật XP để thích ứng có kiểm soát.
5. Thiết kế vòng phản hồi từ khám phá nhu cầu đến giao phần mềm, vận hành và điều chỉnh ưu tiên.

## 2. Hiểu đúng hai vế của giá trị Agile

### 2.1. Kế hoạch vẫn quan trọng

Kế hoạch giúp trả lời: nhóm muốn đạt kết quả gì; việc nào nên làm trước; có những phụ thuộc nào; cần bao nhiêu thời gian, người và kinh phí; ai cần phối hợp; điều gì có thể gây rủi ro. Kế hoạch tốt tạo sự minh bạch và cho các bên một cơ sở để thống nhất kỳ vọng.

Tuy nhiên, kế hoạch là **dự báo dựa trên thông tin ở một thời điểm**. Trong sản phẩm có độ bất định cao, một số giả định ban đầu gần như chắc chắn sẽ cần được kiểm tra lại:

- Người dùng thật có hành xử giống những gì nhóm dự đoán?
- Tính năng được yêu cầu có giải quyết đúng vấn đề?
- API, dữ liệu, kiến trúc hiện tại có đáp ứng thiết kế được chọn?
- Đối tác, quy định, thị trường và điều kiện vận hành có giữ nguyên?
- Thời gian thực tế có giống ước lượng ban đầu?

Khi dữ liệu mới phủ nhận một giả định quan trọng, cố giữ nguyên mọi chi tiết kế hoạch có thể làm tăng chi phí sửa sai.

### 2.2. Ứng phó với thay đổi là một quyết định có trách nhiệm

Ứng phó với thay đổi có nghĩa là **phát hiện một tín hiệu mới, đánh giá tác động và điều chỉnh hành động khi việc đó giúp đạt mục tiêu tốt hơn hoặc giảm rủi ro đáng kể**. Đó không phải phản xạ nhận ngay mọi yêu cầu hoặc thay đổi liên tục chỉ để chứng tỏ mình linh hoạt.

| Chỉ bám theo kế hoạch | Chủ động ứng phó với thay đổi |
| --- | --- |
| “Tài liệu đã chốt nên cứ triển khai đến hết.” | “Giả định nào vừa bị phản hồi thực tế bác bỏ?” |
| Đánh giá thành công chủ yếu bằng tỷ lệ công việc đã hoàn tất. | Đánh giá bằng giá trị người dùng nhận được, chất lượng và khả năng học hỏi. |
| Làm rõ mọi chức năng từ sớm rồi hạn chế xem lại. | Làm rõ dần, ưu tiên chi tiết cho công việc gần nhất và kiểm tra những giả định rủi ro. |
| Tiếp nhận hoặc từ chối yêu cầu mới theo phản xạ. | So giá trị, chi phí, rủi ro, độ khẩn cấp và phương án thay thế. |
| Xem cập nhật kế hoạch là thất bại. | Xem cập nhật có lý do và được truyền đạt rõ là kết quả của học hỏi. |

**Ví dụ:** Một ứng dụng đặt lịch có kế hoạch phát triển bộ lọc theo địa điểm trước. Sau đợt thử nghiệm, nhóm thấy nhiều người dùng thất bại ở bước xác nhận khung giờ và có nguy cơ tạo lịch trùng. Nhóm nên cân nhắc ưu tiên làm rõ xác nhận và bảo vệ dữ liệu đặt lịch trước; hoàn thành bộ lọc đúng kế hoạch không có ý nghĩa nếu chức năng cốt lõi vẫn chưa đáng tin cậy.

Ngược lại, nếu một người đề nghị đổi toàn bộ giao diện chỉ vì thích màu khác, chưa có dữ liệu về tác động và nhóm đang xử lý lỗi nghiêm trọng, phản ứng “Agile thì phải đổi ngay” cũng không đúng.

### 2.3. Mục tiêu, kế hoạch và ràng buộc khác nhau

| Thành phần | Câu hỏi | Mức độ thay đổi hợp lý |
| --- | --- | --- |
| **Product Goal / kết quả mong muốn** | Sản phẩm cần tạo lợi ích gì cho người dùng và tổ chức? | Tương đối ổn định để định hướng; xem lại khi chiến lược hoặc bằng chứng nền tảng thay đổi. |
| **Giả định** | Nhóm đang tin điều gì nhưng chưa kiểm chứng? | Chủ động kiểm tra và cập nhật khi có bằng chứng. |
| **Giải pháp và phạm vi** | Sẽ thử chức năng, thiết kế hoặc quy trình nào? | Có thể chia nhỏ, đổi thứ tự, thay thế hoặc bỏ theo ưu tiên. |
| **Kế hoạch thực hiện** | Làm vào thời điểm nào, phụ thuộc vào ai, giao bằng cách nào? | Là dự báo cần cập nhật khi thông tin mới xuất hiện. |
| **Chuẩn chất lượng** | Increment phải đạt điều kiện nào để sử dụng an toàn? | Không tùy tiện hạ thấp để kịp lịch; thay đổi tiêu chuẩn phải có lý do và thẩm quyền phù hợp. |
| **Nghĩa vụ và giới hạn** | Pháp lý, bảo mật, hợp đồng, ngân sách, thời hạn cố định? | Phải tuân thủ hoặc thương lượng rõ ràng với người có thẩm quyền, không thể tự bỏ qua. |

Một câu ghi nhớ hữu ích là **giữ rõ vấn đề cần giải quyết, linh hoạt với cách giải quyết**. Nhưng ngay cả mục tiêu cũng không bất biến tuyệt đối nếu nhu cầu và bối cảnh thực sự đã đổi.

## 3. Vì sao thay đổi xuất hiện thường xuyên?

### 3.1. Bất định về nhu cầu

Người dùng có thể yêu cầu “thêm mười bộ lọc” trong khi vấn đề thật là “không tìm được mục phù hợp”. Phỏng vấn, quan sát thao tác, dữ liệu sử dụng và bản mẫu giúp nhóm phân biệt giải pháp được đề xuất với nhu cầu thực tế.

### 3.2. Bất định về kỹ thuật

Một tích hợp tưởng đơn giản có thể vướng giới hạn API, hiệu năng, quyền truy cập hoặc di chuyển dữ liệu. Thử nghiệm kỹ thuật nhỏ, tích hợp sớm và kiểm thử giúp nhóm phát hiện sớm những rủi ro này, thay vì chờ đến cuối dự án.

### 3.3. Thay đổi từ môi trường

Đối tác có thể ngừng hỗ trợ phiên bản API; quy định bảo vệ dữ liệu có thể thay đổi; nhu cầu hỗ trợ vận hành tăng; một nhóm người dùng mới xuất hiện. Các trường hợp này có mức độ khẩn cấp khác nhau và cần được đánh giá riêng.

### 3.4. Kiến thức tăng theo từng lần giao sản phẩm

Nhóm hiếm khi có đủ bằng chứng ngay từ đầu. Một bản mẫu cho thấy người dùng hiểu giao diện ra sao; một lát cắt đã tích hợp cho thấy giới hạn kỹ thuật; bản phát hành thật cho thấy hiệu quả và sự cố vận hành. Vì vậy, việc giao tăng dần là **cơ chế học hỏi**, không chỉ là cách chia tiến độ.

~~~mermaid
flowchart LR
    A["Giả định và mục tiêu"] --> B["Lát cắt nhỏ / thử nghiệm"]
    B --> C["Kiểm thử và phát hành phù hợp"]
    C --> D["Phản hồi, dữ liệu, sự cố"]
    D --> E{"Giả định còn phù hợp?"}
    E -->|Có| F["Tiếp tục và tinh chỉnh kế hoạch"]
    E -->|Không / chưa rõ| G["Xem lại phương án và ưu tiên"]
    F --> B
    G --> B
~~~

Vòng phản hồi giúp hạn chế **chi phí đi sai hướng**. Không phải mọi bất định đều cần một thử nghiệm tốn kém: mức kiểm chứng nên tương xứng với hậu quả nếu sai, chi phí thay đổi và khả năng đảo ngược quyết định.

## 4. Lập kế hoạch linh hoạt bằng nhiều tầm nhìn

Kế hoạch dài hạn quá chi tiết có thể tạo cảm giác chắc chắn giả. Một cách hợp lý là lập kế hoạch theo nhiều tầng và chỉ chi tiết hóa khi sắp thực hiện:

| Tầm nhìn | Nên làm rõ | Khi nào thích ứng |
| --- | --- | --- |
| **Chiến lược / Product Goal** | Người dùng, vấn đề, giá trị kỳ vọng và giới hạn. | Khi bằng chứng chiến lược hoặc điều kiện kinh doanh thay đổi đáng kể. |
| **Roadmap định hướng kết quả** | Những vấn đề hoặc kết quả ưu tiên theo giai đoạn; mốc phụ thuộc. | Khi nhu cầu, mức rủi ro hoặc khả năng giao thay đổi. |
| **Product Backlog** | Các lựa chọn tạo giá trị, giảm rủi ro; thứ tự ưu tiên. | Thường xuyên, qua khám phá và phản hồi sau giao hàng. |
| **Kế hoạch ngắn hạn / Sprint** | Mục tiêu cụ thể và phương án thực hiện gần nhất. | Khi nhóm học thêm, trong giới hạn mục tiêu và quy tắc phối hợp. |
| **Kế hoạch hằng ngày** | Công việc đang diễn ra, trở ngại và phối hợp. | Khi có thông tin mới từ kiểm thử, tích hợp hoặc người dùng. |

Cách làm này thường được gọi là **rolling-wave planning**: kế hoạch gần được chi tiết hơn, kế hoạch xa giữ ở mức mục tiêu, giả định và dự báo. Không cần mô tả chính xác công việc của nhiều tháng tới khi còn thiếu thông tin quan trọng.

### 4.1. Biến những giả định ngầm thành điều có thể kiểm tra

Nếu nhóm ghi “tích hợp hệ thống thanh toán A trong hai tuần”, có thể đang ngầm giả định:

- API A có đầy đủ trường dữ liệu cần thiết.
- Môi trường thử nghiệm và quyền truy cập đã sẵn sàng.
- Các quy tắc giao dịch và bảo mật đã được hiểu đúng.
- Người dùng cần tích hợp A trước những lựa chọn khác.
- Phần việc có thể kiểm thử và vận hành trong thời gian ước lượng.

Ghi những giả định quan trọng sẽ giúp nhóm biết **tín hiệu nào cần điều chỉnh kế hoạch**. Nếu API không thể hỗ trợ trường hợp cốt lõi, đổi phương án triển khai là hành động có trách nhiệm.

### 4.2. Không thể giải quyết xung đột bằng cách âm thầm bỏ chất lượng

Khi thời hạn, ngân sách và phạm vi cùng bị giới hạn, thay đổi cần kèm lựa chọn rõ ràng: giảm phạm vi, đổi thứ tự, thương lượng thời điểm hoặc tăng năng lực nếu khả thi. Không nên che giấu rủi ro bằng cách bỏ kiểm thử, bỏ theo dõi sau phát hành hoặc phụ thuộc vào làm thêm giờ kéo dài.

## 5. Quy trình sáu bước để xử lý đề xuất thay đổi

### Bước 1 — Xác định tín hiệu và vấn đề gốc

Đừng bắt đầu từ “hãy thêm nút này”. Hãy hỏi: **Ai gặp vấn đề gì, trong tình huống nào, hậu quả là gì?** Tín hiệu đến từ quan sát sử dụng, dữ liệu sản phẩm, báo cáo sự cố, khách hàng, đối tác hay quy định mới?

Ví dụ, “khách nhấn Đặt lịch hai lần khi mạng chậm” mô tả hiện tượng cụ thể hơn “cần làm lại màn hình”.

### Bước 2 — Kiểm tra bằng chứng và độ khẩn cấp

Không phải mọi tín hiệu có cùng mức ưu tiên:

| Loại thay đổi | Ví dụ | Cách phản ứng thường phù hợp |
| --- | --- | --- |
| **Sự cố khẩn cấp** | Mất dữ liệu, dịch vụ ngừng hoạt động, lỗ hổng đang ảnh hưởng người dùng. | Ưu tiên ứng cứu và giảm thiệt hại theo chính sách, thông báo ảnh hưởng tới công việc khác. |
| **Nghĩa vụ bắt buộc có hạn** | API cũ có ngày ngừng hỗ trợ; yêu cầu pháp lý phải đáp ứng. | Xác minh phạm vi, hạn, rủi ro và phụ thuộc; xếp kế hoạch phù hợp. |
| **Cơ hội sản phẩm có bằng chứng** | Người dùng bỏ dở cùng một bước; phản hồi lặp lại từ nhiều nguồn. | Đánh giá ưu tiên, thử giải pháp nhỏ và đo kết quả. |
| **Ý tưởng còn yếu bằng chứng** | Đề xuất của một cá nhân, xu hướng mới chưa rõ tác động. | Ghi giả thuyết, khám phá thêm hoặc chờ thời điểm phù hợp. |

Một mẫu quan sát nhỏ có thể giúp phát hiện vấn đề sử dụng nhưng chưa đủ để ước lượng chính xác tỷ lệ ảnh hưởng. Phân biệt **điều đã thấy** với **điều suy đoán** trước khi đổi phạm vi lớn.

### Bước 3 — So sánh lợi ích với chi phí và rủi ro

Đối với mỗi phương án, xem:

1. **Giá trị:** Thay đổi phục vụ kết quả nào và cho người dùng nào?
2. **Bằng chứng:** Điều gì ủng hộ hoặc phản bác giả thuyết?
3. **Chi phí:** Phát triển, kiểm thử, tích hợp, hỗ trợ, bảo trì.
4. **Gián đoạn:** Bao nhiêu việc dở dang, WIP và chuyển ngữ cảnh nếu đổi ngay?
5. **Rủi ro:** Bảo mật, dữ liệu, tính đúng đắn, độ tin cậy, khả năng tiếp cận.
6. **Chi phí trì hoãn:** Nếu chờ một tuần hoặc Sprint kế tiếp, điều gì mất đi?
7. **Khả năng đảo ngược:** Có thể thử giới hạn và quay lại nhanh không?

Không bắt buộc biến mọi yếu tố thành điểm số giả chính xác. Với thay đổi rủi ro nhỏ, một cuộc trao đổi ngắn kèm bằng chứng có thể đủ. Với thay đổi khó đảo ngược hoặc có tác động pháp lý lớn, cần phân tích sâu và quyết định đúng thẩm quyền.

### Bước 4 — Quyết định và cập nhật kế hoạch minh bạch

Các kết quả hợp lệ gồm: **làm ngay**, **đưa lên đầu backlog cho vòng sau**, **thử nghiệm trước**, **hoãn**, hoặc **không thực hiện**. Cần ghi ngắn gọn lý do, ai chịu trách nhiệm và thời điểm xem lại.

Nếu đổi kế hoạch, phải cho thấy **việc gì sẽ bị hoãn hoặc loại bỏ**, tác động tới mốc thời gian, ngân sách, rủi ro và các nhóm phụ thuộc. Chỉ thêm việc mà không giảm WIP hoặc điều chỉnh dự báo làm mọi thứ kém đáng tin.

### Bước 5 — Giao phần nhỏ và bảo vệ chất lượng

Chia thay đổi thành lát cắt có thể kiểm chứng, xác định tiêu chí chấp nhận, viết kiểm thử cần thiết, tích hợp sớm và theo dõi sau triển khai. Với rủi ro phù hợp, có thể dùng feature flag, rollout giới hạn, canary, rollback hoặc phương án roll forward.

### Bước 6 — Đo và học từ kết quả thật

Đo **kết quả chính** song song với **chỉ số bảo vệ**. Ví dụ, tỷ lệ hoàn tất đăng ký tăng nhưng số tài khoản gian lận cũng tăng thì không thể kết luận cải tiến thành công. Sau khi xem kết quả, nhóm tiếp tục, điều chỉnh hoặc dừng giả thuyết.

~~~mermaid
flowchart TD
    A["Tín hiệu mới"] --> B["Xác định vấn đề và nguồn bằng chứng"]
    B --> C{"Khẩn cấp / nghĩa vụ bắt buộc?"}
    C -->|Có| D["Ưu tiên theo chính sách ứng cứu hoặc tuân thủ"]
    C -->|Không| E["Đánh giá giá trị, chi phí, WIP và rủi ro"]
    E --> F{"Đã đủ cơ sở thay đổi?"}
    F -->|Chưa| G["Khám phá thêm / hoãn / từ chối"]
    F -->|Có| H["Quyết định và cập nhật backlog"]
    D --> I["Thực hiện với chuẩn chất lượng"]
    H --> I
    I --> J["Đo kết quả và phản hồi"]
    J --> B
~~~

Mẫu ghi quyết định ngắn có thể sử dụng ngay:

~~~text
Tín hiệu mới        : Người dùng bỏ dở ở bước xác nhận số điện thoại.
Bằng chứng          : Dữ liệu luồng + quan sát; cần kiểm tra quy mô ảnh hưởng.
Mục tiêu            : Tăng tỷ lệ hoàn tất đăng ký hợp lệ.
Các phương án       : Giữ nguyên / đơn giản hóa / thử nghiệm giới hạn.
Chi phí chuyển hướng: Hoãn hạng mục ít giá trị, bổ sung kiểm thử xác minh.
Chỉ số bảo vệ       : Gian lận, lỗi đăng ký, dữ liệu cá nhân.
Quyết định          : Thử bản mẫu trước khi đổi backlog phát hành.
Người quyết định    : ...
Ngày xem lại        : ...
~~~

## 6. Scrum: thích ứng trong khi bảo vệ Sprint Goal

Scrum giúp nhóm kiểm tra và thích ứng theo Sprint. **Product Owner** chịu trách nhiệm tối ưu giá trị sản phẩm và quản lý hiệu quả Product Backlog. Backlog là danh sách công việc có thứ tự được cập nhật khi học thêm; không phải cam kết làm hết mọi mục ở thứ tự cũ.

### 6.1. Product Goal và Sprint Goal giúp thay đổi có định hướng

**Product Goal** là mục tiêu dài hạn của Scrum Team; **Sprint Goal** tạo mục đích chung cho Sprint. Theo Scrum Guide 2020, trong Sprint:

- Không có thay đổi nào được thực hiện nếu **đe dọa Sprint Goal**.
- **Chất lượng không được suy giảm**.
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được làm rõ và thương lượng lại với Product Owner khi nhóm học thêm.

Vì vậy, “đã chọn mười story thì bắt buộc làm đủ mười story trong mọi hoàn cảnh” không phải nguyên tắc Scrum. Developers chịu trách nhiệm tạo Sprint Backlog và điều chỉnh kế hoạch thực hiện khi có hiểu biết mới, đồng thời tập trung đạt Sprint Goal.

**Ví dụ:** Sprint Goal là “khách đặt được một lịch hẹn hợp lệ”. Nhóm phát hiện khi hai người đặt cùng giờ, hệ thống có thể tạo lịch trùng. Ưu tiên xử lý giao dịch đồng thời và kiểm thử tình huống này phục vụ trực tiếp chất lượng và Sprint Goal. Một đề nghị bổ sung bộ lọc màu không liên quan có thể chờ trong Product Backlog.

Khi Sprint Goal thật sự trở nên lỗi thời, **chỉ Product Owner có thẩm quyền hủy Sprint** theo Scrum Guide. Hủy Sprint không phải phản ứng thường lệ đối với bất cứ yêu cầu mới nào.

### 6.2. Các sự kiện Scrum giúp cập nhật quyết định

| Sự kiện | Đóng góp vào khả năng thích ứng |
| --- | --- |
| **Sprint Planning** | Chọn Sprint Goal và dự báo phương án thực hiện theo thông tin hiện có. |
| **Daily Scrum** | Developers kiểm tra tiến độ với Sprint Goal, điều chỉnh kế hoạch hằng ngày. |
| **Sprint Review** | Xem Increment và hoàn cảnh mới cùng các bên liên quan để thích ứng Product Backlog. |
| **Sprint Retrospective** | Xem lại hiệu quả, chất lượng và cách phối hợp để cải tiến hệ thống làm việc. |

Sprint Review không đơn thuần là buổi demo hay báo cáo tiến độ. Retrospective cũng không nhằm quy lỗi người đã ước lượng sai; điều quan trọng là học cách dự báo, phối hợp và bảo vệ chất lượng tốt hơn.

## 7. Kanban: phản ứng với ưu tiên mới mà vẫn giữ dòng công việc

Kanban hữu ích khi công việc đến liên tục, chẳng hạn yêu cầu bảo trì, hỗ trợ vận hành và phát triển những hạng mục nhỏ. Việc **trực quan hóa luồng**, công khai **chính sách xử lý** và giới hạn **work in progress (WIP)** giúp nhóm thấy chi phí của việc đổi ưu tiên.

~~~text
Lựa chọn ưu tiên -> Sẵn sàng -> Đang làm [WIP: 3] -> Review [WIP: 2] -> Hoàn tất
                                     |                 |
                                  Bị chặn?         Hàng đợi?
~~~

Giới hạn WIP trong ví dụ chỉ mang tính minh họa. Con số thực tế phải được điều chỉnh theo năng lực nhóm và bản chất công việc. Nếu cột Review đang đầy, việc tiếp tục bắt đầu nhiều việc mới có thể làm tăng hàng đợi và kéo dài thời gian hoàn tất.

Khi một yêu cầu mới xuất hiện:

1. Xác định mức khẩn cấp theo chính sách rõ ràng.
2. Kiểm tra WIP, các việc sắp xong và điểm nghẽn.
3. Nếu bình thường, đặt vào hàng ưu tiên và kéo khi có năng lực.
4. Nếu thực sự khẩn cấp, áp dụng chính sách việc khẩn cấp, công khai điều gì bị gián đoạn.
5. Dùng dữ liệu **cycle time**, **throughput**, WIP và số việc bị chặn để xem chính sách có hiệu quả không.

**Cycle time** là thời gian từ khi một công việc bắt đầu được xử lý đến lúc hoàn tất theo định nghĩa đã thống nhất; **lead time** có thể tính từ lúc tiếp nhận yêu cầu đến lúc giao xong. Khi đổi mốc đo hoặc cách chia mục công việc, không nên so sánh số liệu trực tiếp.

Một số nhóm dùng **class of service** để phân loại việc khẩn cấp, việc có hạn cố định và việc thông thường. Đây là cách tổ chức chính sách theo hoàn cảnh; không nên gắn nhãn “khẩn cấp” cho tất cả yêu cầu, vì như vậy giới hạn WIP sẽ mất tác dụng.

**Ứng phó hiệu quả đôi khi có nghĩa là không bắt đầu ngay**: hoàn tất việc quan trọng đang dang dở có thể tạo giá trị sớm hơn việc mở thêm ba hạng mục mới.

## 8. XP: năng lực kỹ thuật giúp đổi hướng với chi phí hợp lý

Quyết định thay đổi đúng về sản phẩm vẫn có thể thực hiện chậm và rủi ro nếu mã khó sửa hoặc thiếu kiểm thử. **Extreme Programming (XP)** cung cấp các thực hành giảm chi phí và rủi ro thay đổi:

| Thực hành | Lợi ích khi yêu cầu thay đổi |
| --- | --- |
| **Test-driven development (TDD)** | Thể hiện hành vi kỳ vọng qua kiểm thử, giúp phát hiện lỗi hồi quy khi sửa mã. |
| **Continuous integration (CI)** | Tích hợp thường xuyên để phát hiện sớm xung đột và lỗi liên quan. |
| **Refactoring** | Cải thiện cấu trúc bên trong mà không thay đổi hành vi bên ngoài; giữ mã dễ hiểu và dễ sửa. |
| **Pair programming / code review** | Chia sẻ tri thức và kiểm tra giả định thiết kế qua trao đổi trực tiếp. |
| **Thiết kế đơn giản** | Tránh xây sẵn quá nhiều khả năng chưa có bằng chứng, giảm khối lượng phải bảo trì khi đổi hướng. |
| **Bước tiến nhỏ, nhịp bền vững** | Giảm phạm vi lỗi và tránh phụ thuộc vào làm thêm giờ kéo dài. |

**Ví dụ:** Để thêm phương thức thanh toán mới, hệ thống có các kiểm thử hành vi thanh toán, kiểm thử hợp đồng API, CI và thiết kế tách trách nhiệm sẽ ít rủi ro hơn hệ thống dồn mọi xử lý thanh toán vào một hàm lớn không được kiểm thử.

“Thiết kế để thay đổi được” không đồng nghĩa xây trước mọi tầng trừu tượng có thể tưởng tượng. Nhóm nên thiết kế vừa đủ với hiểu biết hiện tại và duy trì chất lượng để có thể cải tiến sau này.

## 9. Ví dụ xuyên suốt: đổi ưu tiên cho sản phẩm đặt lịch

Giả sử nhóm phát triển một ứng dụng đặt lịch tư vấn trên điện thoại. Trong sáu tuần đầu, kế hoạch dự kiến:

1. Hoàn thiện màn hình chọn loại tư vấn.
2. Bổ sung luồng xem và chọn khung giờ.
3. Thêm email xác nhận.
4. Xây bộ lọc theo nhiều địa điểm.

**Mục tiêu:** Người dùng đặt được lịch hợp lệ nhanh chóng, ít bỏ dở, không phát sinh lịch trùng.

### 9.1. Thông tin mới

Nhóm giao một lát cắt cơ bản và cho người dùng thử. Họ nhận thấy:

- Trên màn hình nhỏ, nút xác nhận cuối không rõ.
- Khi mạng chậm, một số người bấm nút Đặt lịch nhiều lần.
- Nhiều người rời luồng trước khi thấy kết quả.

Các quan sát này gợi ra giả thuyết có vấn đề ở bước xác nhận. Tuy nhiên, mẫu quan sát nhỏ **chưa đủ** để suy ra tỷ lệ ảnh hưởng chính xác trên toàn bộ người dùng.

### 9.2. Thay đổi quyết định có lý do

| Hạng mục | Liên hệ với mục tiêu | Quyết định minh họa |
| --- | --- | --- |
| Làm rõ nút và trạng thái xác nhận | Có thể giảm bỏ dở | **Ưu tiên**, thử thay đổi nhỏ rồi đo. |
| Ngăn yêu cầu gửi lặp tạo lịch trùng | Bảo vệ tính đúng đắn | **Phải xử lý** trước khi mở rộng phát hành. |
| Email xác nhận sau khi đặt | Có ích, nhưng chưa giải quyết vấn đề ở bước đặt | **Giữ trong backlog**, xem lại thứ tự. |
| Bộ lọc nhiều địa điểm | Chưa có bằng chứng là nhu cầu cấp bách | **Hoãn** để khám phá thêm. |

Nếu nhóm đang dùng Scrum với Sprint Goal “cho phép khách đặt một lịch hợp lệ”, sửa chống trùng có thể phục vụ trực tiếp mục tiêu. Developers và Product Owner trao đổi để làm rõ tác động phạm vi, không tự động nhận mọi yêu cầu. Nếu dùng Kanban, nhóm kiểm tra WIP và chính sách xử lý lỗi trước khi kéo việc.

### 9.3. Giao phần nhỏ, đo kết quả, bảo vệ chất lượng

Nhóm cập nhật thiết kế, bổ sung kiểm thử gửi yêu cầu lặp, kiểm tra lỗi mạng và phát hành giới hạn. Sau đó họ theo dõi:

- **Chỉ số kết quả:** Tỷ lệ đặt thành công trên số lượt bắt đầu hợp lệ, thời gian hoàn tất.
- **Chỉ số bảo vệ:** Lịch trùng, lỗi API, độ trễ xác nhận, yêu cầu hỗ trợ.
- **Phản hồi định tính:** Người dùng có hiểu trạng thái đang xử lý và biết bước tiếp theo không?

Số liệu sau là **giả định để minh họa cách phân tích**, không phải kết quả thực nghiệm:

| Giai đoạn | Tỷ lệ hoàn tất | Tỷ lệ yêu cầu đặt lịch bị lỗi |
| --- | ---: | ---: |
| Trước thay đổi | 44% | 2,0% |
| Sau phát hành giới hạn | 52% | 1,4% |

Những con số này **không tự chứng minh** thay đổi là nguyên nhân: nhóm còn phải xét cách chọn mẫu, thay đổi nguồn truy cập, yếu tố mùa vụ và cách ghi nhận dữ liệu. Nếu muốn ước lượng tác động nhân quả, có thể thiết kế thử nghiệm đối chứng phù hợp. Nếu lỗi tăng hoặc có lịch trùng, cần ưu tiên chất lượng dù tỷ lệ hoàn tất tăng.

### 9.4. Điều gì làm ví dụ này thể hiện giá trị Agile?

Nhóm **giữ mục tiêu tạo trải nghiệm đặt lịch đáng tin cậy**, nhưng đổi thứ tự backlog khi có phản hồi. Việc bị hoãn và lý do đổi kế hoạch được chia sẻ rõ. Thay đổi được giao thành lát cắt có thể kiểm chứng rồi đo lại, thay vì nhận yêu cầu theo cảm tính.

## 10. Khi nào không nên đổi kế hoạch ngay?

### 10.1. Khi yêu cầu thiếu bằng chứng hoặc không gắn với mục tiêu

“Đối thủ có chatbot nên chúng ta cũng phải có” là một giả thuyết, không phải bằng chứng giá trị. Trước khi thêm chức năng, cần xem người dùng đang cần trợ giúp ở đâu và giải pháp nào phù hợp.

### 10.2. Khi gián đoạn lớn hơn giá trị ngắn hạn

Một thay đổi giao diện nhỏ chưa có căn cứ có thể chờ nếu nhóm đang chuẩn bị phát hành khả năng cốt lõi. Liên tục đổi việc làm tăng WIP, chuyển ngữ cảnh và thời gian chờ.

### 10.3. Khi thay đổi đe dọa chất lượng hoặc nghĩa vụ bắt buộc

Không thể bỏ xác minh danh tính hoặc kiểm soát quyền truy cập chỉ vì muốn giảm số bước thao tác. Cần khám phá phương án ít ma sát nhưng vẫn đáp ứng yêu cầu an toàn, riêng tư và pháp lý.

### 10.4. Khi mốc hợp đồng cần thương lượng

Nếu khách hàng có cam kết bàn giao cụ thể, thay đổi phạm vi hoặc thời hạn phải được thông báo và quyết định đúng thẩm quyền. Giá trị Agile không xóa bỏ nghĩa vụ với khách hàng.

### 10.5. Khi dữ liệu mới có thể bị nhiễu

Một ngày có tỷ lệ chuyển đổi giảm có thể do chiến dịch quảng cáo, thay đổi cơ cấu người dùng, lỗi đo hoặc yếu tố mùa vụ. Nhóm cần kiểm tra bối cảnh và độ tin cậy trước khi đảo hướng chiến lược.

## 11. Ngộ nhận thường gặp

| Ngộ nhận | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Agile không cần kế hoạch.” | Thiếu mục tiêu, không dự báo được phụ thuộc và nguồn lực. | Lập kế hoạch đủ rõ và thường xuyên xem lại giả định. |
| “Khách hàng muốn gì cũng nhận ngay.” | Backlog phình to, không hoàn tất việc, mất tập trung. | Đánh giá giá trị, rủi ro, WIP và ưu tiên có trách nhiệm. |
| “Mỗi lần đổi backlog là thất bại.” | Nhóm che giấu thông tin mới để giữ kế hoạch. | Backlog được cập nhật khi học thêm; công khai lý do quyết định. |
| “Đang trong Sprint không được thay đổi gì.” | Bỏ qua vấn đề cần thiết để đạt Sprint Goal. | Scrum cho phép làm rõ, thương lượng phạm vi nhưng bảo vệ Sprint Goal và chất lượng. |
| “Đổi nhanh nghĩa là bỏ kiểm thử.” | Lỗi hồi quy, nợ kỹ thuật và chi phí thay đổi tăng. | Duy trì DoD, kiểm thử, tích hợp và phát hành an toàn. |
| “Có số liệu thì cứ làm theo số liệu.” | Đảo hướng theo dao động ngẫu nhiên hoặc dữ liệu sai. | Kiểm tra định nghĩa đo, mẫu, bối cảnh và nguyên nhân khả dĩ. |
| “Không đổi kế hoạch là không Agile.” | Đổi hướng không cần thiết, tiêu hao năng lực nhóm. | Giữ kế hoạch khi bằng chứng tiếp tục ủng hộ; đổi khi có lý do chính đáng. |

## 12. Đo lường khả năng thích ứng

**Số lần đổi kế hoạch** không phải thước đo mức độ Agile. Một nhóm đổi liên tục có thể đang thiếu định hướng. Các chỉ số hữu ích hơn phản ánh **khả năng học và giao giá trị trong điều kiện thay đổi**:

| Điều cần hiểu | Tín hiệu / chỉ số | Lưu ý |
| --- | --- | --- |
| Có giải quyết đúng nhu cầu? | Tỷ lệ hoàn tất tác vụ, mức sử dụng tính năng, phản hồi người dùng. | Kết hợp dữ liệu định lượng và định tính; xét yếu tố ngoài sản phẩm. |
| Từ phản hồi tới quyết định mất bao lâu? | Thời gian phát hiện vấn đề đến lúc kiểm chứng hoặc quyết định. | Nhanh không đồng nghĩa đúng nếu thiếu bằng chứng. |
| Dòng công việc có thông suốt? | Cycle time, lead time, throughput, WIP, thời gian bị chặn. | Thống nhất mốc đo; không dùng số liệu thô để xếp hạng cá nhân. |
| Thay đổi có an toàn? | Lỗi hồi quy, tỷ lệ lỗi, độ trễ, thời gian phục hồi, mức đạt SLO. | Cần cân bằng tốc độ với độ tin cậy. |
| Có học từ kết quả? | Giả thuyết được kiểm chứng, backlog cập nhật theo phản hồi, cải tiến quy trình được đánh giá lại. | Số cuộc họp hoặc số thí nghiệm không đủ chứng minh giá trị. |

Các chỉ số thuộc nghiên cứu **DORA** có thể hỗ trợ hiểu khả năng giao thay đổi phần mềm và độ ổn định vận hành. Chúng cần được xem cùng kết quả sản phẩm. Phát hành nhiều hơn không tự động đồng nghĩa tạo nhiều giá trị hơn.

**Story point và velocity**, nếu nhóm dùng để hỗ trợ dự báo, không trực tiếp đo giá trị sản phẩm hoặc năng suất từng cá nhân. Không nên so sánh chúng giữa các nhóm để ép nhận thêm việc khi kế hoạch thay đổi.

## 13. Bài tập ứng dụng

### Tình huống A — Một thay đổi giữa Sprint

Scrum Team đang ở ngày thứ năm của Sprint hai tuần. Sprint Goal là “khách đặt được lịch và nhận xác nhận hợp lệ”. Nhóm vừa phát hiện hai người có thể đặt cùng giờ khi yêu cầu đến đồng thời. Bộ phận kinh doanh cũng yêu cầu thêm bộ lọc màu cho buổi demo tuần sau.

**Câu hỏi:**

1. Tín hiệu nào ảnh hưởng trực tiếp tới Sprint Goal và chất lượng?
2. Ai cần phối hợp để làm rõ phạm vi Sprint?
3. Có nên đưa bộ lọc màu vào Sprint ngay không? Vì sao?
4. Cần thêm kiểm thử và điều kiện chấp nhận nào?

**Gợi ý:** Điều tra và xử lý lịch trùng là ưu tiên thiết yếu để đạt mục tiêu; Developers điều chỉnh phương án kỹ thuật và trao đổi với Product Owner khi phạm vi cần thương lượng. Bộ lọc màu được ghi vào Product Backlog để xem giá trị và thứ tự ưu tiên; không tự động đưa vào Sprint khi chưa có lý do liên quan mục tiêu.

### Tình huống B — Dữ liệu chưa chứng minh nguyên nhân

Nhóm vận hành luồng đăng ký bằng Kanban. Một ngày sau phát hành, tỷ lệ hoàn tất giảm từ 61% xuống 58%. Cùng ngày, một chiến dịch quảng cáo bắt đầu đưa người dùng mới vào sản phẩm. Có ý kiến yêu cầu rollback ngay.

**Câu hỏi:**

1. Mẫu người dùng và định nghĩa chỉ số trước/sau có giống nhau không?
2. Có lỗi dịch vụ hoặc tín hiệu an toàn nghiêm trọng nào không?
3. Nên phân đoạn dữ liệu hoặc kiểm chứng thêm điều gì?
4. Khi nào cần hành động khẩn cấp dù chưa kết luận được nguyên nhân?

**Gợi ý:** Trước hết kiểm tra sức khỏe dịch vụ và chất lượng dữ liệu. Nếu có lỗi nghiêm trọng, xử lý theo quy trình sự cố. Nếu chỉ có biến động nhỏ chưa rõ nguyên nhân, phân tích theo nguồn truy cập, thiết bị, phiên bản và thời gian trước khi ra quyết định lớn.

### Bài tập cho dự án đang làm

Điền bảng dưới đây cùng nhóm:

| Câu hỏi | Câu trả lời |
| --- | --- |
| Mục tiêu sản phẩm đang ưu tiên? | ... |
| Giả định rủi ro nhất trong kế hoạch? | ... |
| Bằng chứng nào có thể làm nhóm đổi hướng? | ... |
| Lát cắt nhỏ nhất để kiểm tra giả định? | ... |
| Nếu đổi hướng, hạng mục nào sẽ bị hoãn hoặc bỏ? | ... |
| Chuẩn chất lượng và ràng buộc nào không được phá vỡ? | ... |
| Khi nào, bằng chỉ số nào nhóm xem lại quyết định? | ... |

Nhóm có thể dùng bảng này trong backlog refinement, Sprint Review hoặc buổi cải tiến dòng công việc, tùy cách phối hợp đã chọn. Mục đích là làm rõ **điều kiện thay đổi quyết định**, không phải tạo thêm tài liệu cho đủ thủ tục.

## 14. Checklist trước khi chấp nhận thay đổi

- [ ] Đã nói rõ vấn đề gốc và đối tượng chịu ảnh hưởng.
- [ ] Xác định nguồn bằng chứng, độ tin cậy và điều còn chưa chắc chắn.
- [ ] Nêu liên hệ với Product Goal, Sprint Goal hoặc kết quả đang ưu tiên.
- [ ] Cân nhắc giá trị, chi phí trì hoãn, rủi ro, phụ thuộc và WIP hiện tại.
- [ ] Chỉ rõ việc bị hoãn, loại bỏ hoặc cần thương lượng lại.
- [ ] Có người quyết định phù hợp và cách chia sẻ tác động tới các bên liên quan.
- [ ] Có kế hoạch giao phần nhỏ, kiểm thử, bảo vệ chất lượng và theo dõi sau phát hành.
- [ ] Định nghĩa chỉ số kết quả và chỉ số bảo vệ để đánh giá hiệu quả thực tế.

## 15. Ghi nhớ cốt lõi

**Ứng phó thay đổi hơn bám theo kế hoạch** là coi kế hoạch như **công cụ để tạo giá trị trong điều kiện bất định**, thay vì coi việc tuân thủ từng dòng kế hoạch là đích đến. Nhóm cần có mục tiêu rõ ràng, giao phần mềm tăng dần, lấy phản hồi sớm, đánh giá thay đổi có trách nhiệm và cải tiến liên tục.

Scrum cung cấp nhịp kiểm tra và thích ứng theo mục tiêu Sprint; Kanban làm rõ dòng công việc và giá của việc đổi ưu tiên; XP giúp giảm chi phí sửa đổi bằng kỷ luật kỹ thuật. Chọn và kết hợp chúng tùy vào vấn đề thực tế, luôn bảo vệ chất lượng và độ tin cậy.

Một quyết định tốt có thể là **đổi hướng**, **giữ hướng**, **thử nghiệm nhỏ trước**, hoặc **từ chối yêu cầu mới**. Điểm chung là quyết định được giải thích bằng mục tiêu, bằng chứng, tác động và cách kiểm chứng tiếp theo.

### Tài liệu gốc nên đọc thêm

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — nguyên văn bốn giá trị.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — nguyên tắc chào đón thay đổi, giao thường xuyên và cải tiến.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Backlog, Sprint Goal, Sprint Review và quy tắc trong Sprint.
- [The Kanban Guide](https://kanbanguides.org/) — trực quan hóa dòng, WIP và các chỉ số dòng công việc.
- [DORA](https://dora.dev/) — tài liệu nghiên cứu về giao phần mềm và vận hành.
