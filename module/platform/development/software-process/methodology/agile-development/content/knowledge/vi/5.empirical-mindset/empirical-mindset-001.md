# Phân biệt điều đã biết, giả định và điều cần khám phá

Trong phát triển phần mềm, nhóm thường phải quyết định trước khi có đầy đủ thông tin: người dùng có thực sự cần tính năng này không, giải pháp kỹ thuật có đáp ứng tải không, hay thời gian chờ kiểm thử có phải nguyên nhân khiến phát hành chậm? Nếu mọi nhận định đều được trình bày như sự thật, nhóm dễ xây sai sản phẩm hoặc lập kế hoạch dựa trên niềm tin chưa kiểm chứng.

Bài học này thuộc chương **Tư duy thực nghiệm** của module **AGILE_DEVELOPMENT**. Tư duy Agile hướng đến việc giao giá trị tăng dần, lấy phản hồi sớm và cải tiến liên tục. Để làm được điều đó, nhóm cần phân biệt rạch ròi giữa **điều đã biết dựa trên bằng chứng**, **giả định đang dùng để ra quyết định** và **điều chưa biết cần khám phá**. Sự phân biệt này giúp biến bất định thành những câu hỏi có thể kiểm tra bằng cách làm nhỏ, quan sát kết quả và cập nhật quyết định.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân loại một phát biểu thành điều đã biết, giả định hoặc điều cần khám phá, đồng thời chỉ ra bằng chứng còn thiếu.
- Phân biệt **quan sát**, **diễn giải**, **giả thuyết** và **quyết định**; không biến một phản hồi đơn lẻ thành kết luận chắc chắn.
- Ghi rõ mức độ tin cậy, phạm vi áp dụng và thời điểm của những điều nhóm cho là đã biết.
- Chuyển một giả định quan trọng thành câu hỏi kiểm chứng, lựa chọn phương pháp khám phá phù hợp và đặt tiêu chí đánh giá trước khi thực hiện.
- Đưa kết quả học được vào backlog, user story, kế hoạch Sprint hoặc luồng công việc mà không đánh đồng “đã làm xong” với “đã tạo ra giá trị”.

## 2. Ba loại tri thức cần tách biệt

Giả sử nhóm xây dựng nền tảng học trực tuyến và nhận yêu cầu: “Thêm tính năng nhắc học để học viên quay lại nhiều hơn”. Hãy xem ba cách phát biểu:

1. “Trong 30 ngày vừa qua, 28% học viên mới quay lại mở bài học trong vòng bảy ngày sau bài đầu tiên.” Đây **có thể là điều đã biết**, nếu số liệu được kiểm tra, định nghĩa rõ đối tượng và khoảng thời gian.
2. “Học viên không quay lại vì quên mất khóa học.” Đây là **giả định về nguyên nhân**, chưa được xác nhận chỉ bằng tỷ lệ quay lại thấp.
3. “Lý do chính khiến học viên bỏ dở là gì và lời nhắc có làm thay đổi hành vi hay không?” Đây là **điều cần khám phá**.

| Loại | Bản chất | Câu hỏi kiểm tra | Cách xử lý |
| --- | --- | --- | --- |
| **Điều đã biết (known / evidence-backed)** | Một thông tin hoặc kết luận có căn cứ đủ tin cậy **trong phạm vi đã nêu** | Bằng chứng đến từ đâu? Đo lúc nào? Áp dụng cho ai? Có thể kiểm tra lại không? | Ghi nguồn, định nghĩa, giới hạn và thời điểm; sử dụng làm đầu vào cho quyết định |
| **Giả định (assumption)** | Điều nhóm đang tạm coi là đúng, dù chưa có bằng chứng đủ mạnh để dựa vào một cách chắc chắn | Chúng ta đang tin điều gì? Nếu sai, hậu quả ra sao? Có thể bác bỏ không? | Phát biểu rõ ràng, đánh giá rủi ro, lập giả thuyết để kiểm chứng khi cần |
| **Điều cần khám phá (unknown / question)** | Khoảng trống hiểu biết, mâu thuẫn dữ liệu hoặc câu hỏi chưa có câu trả lời đạt yêu cầu | Chính xác chúng ta cần biết điều gì để đưa ra quyết định nào? | Chọn cách học phù hợp, người phụ trách, thời điểm và tiêu chí dừng khám phá |

**Điều đã biết không đồng nghĩa chân lý vĩnh viễn.** Một đo lường đúng trong tháng trước có thể không đại diện cho tháng sau; một phát biểu đúng với người học trên điện thoại có thể không đúng với người học trên máy tính. “Đã biết” luôn nên đi kèm **nguồn, thời gian, phạm vi và mức độ tin cậy**.

**Giả định không đồng nghĩa sai lầm.** Mọi thiết kế và kế hoạch đều cần những giả định tạm thời. Vấn đề xuất hiện khi nhóm quên rằng đó là giả định, đặc biệt khi chi phí sai cao.

**Điều cần khám phá không chỉ là câu hỏi chung chung.** Câu hỏi “Sản phẩm có tốt không?” khó dẫn đến hành động. Câu hỏi “Với học viên mới học bài đầu, điểm nào khiến họ không tiếp tục trong vòng bảy ngày?” đã khoanh được người dùng, hành vi và khoảng thời gian.

### Ba loại này có thể thay đổi qua thời gian

~~~mermaid
flowchart TD
    A["Phát biểu ban đầu"] --> B{"Đủ bằng chứng tin cậy<br/>cho phạm vi ra quyết định?"}
    B -->|Có| C["Điều đã biết<br/>ghi nguồn và giới hạn"]
    B -->|Chưa| D{"Đang mặc nhiên<br/>coi là đúng?"}
    D -->|Có| E["Giả định<br/>nêu rõ rủi ro nếu sai"]
    D -->|Chưa| F["Điều cần khám phá<br/>biến thành câu hỏi"]
    E --> G["Thiết kế cách kiểm chứng"]
    F --> G
    G --> H["Thu thập quan sát và dữ liệu"]
    H --> I["Đánh giá bằng chứng, giới hạn<br/>và tác động đến quyết định"]
    I --> C
    I --> E
    I --> F
    C --> J["Bối cảnh thay đổi hoặc<br/>bằng chứng mới mâu thuẫn"]
    J --> F
~~~

Sơ đồ là cách suy nghĩ thực hành, không phải một quy trình bắt buộc. Một giả thuyết có thể bị bác bỏ, được ủng hộ một phần hoặc vẫn chưa rõ sau thử nghiệm. Khi đó, nhóm phải giữ đúng mức độ chắc chắn thay vì ép kết quả thành “đúng/sai” tuyệt đối.

## 3. Phân biệt quan sát, diễn giải, giả thuyết và quyết định

Một lỗi tư duy phổ biến là đi thẳng từ điều vừa quan sát sang kết luận về nguyên nhân. Bốn tầng sau giúp ngắt bước nhảy đó:

| Tầng | Ví dụ trong sản phẩm học trực tuyến | Nhận xét |
| --- | --- | --- |
| **Quan sát / dữ kiện thô** | “Trong phiên nghiên cứu, 6/8 người tham gia không nhìn thấy nút ‘Học tiếp’ trong 20 giây đầu.” | Đây là điều **quan sát được ở tám người tham gia**; chưa đại diện cho toàn bộ học viên |
| **Diễn giải** | “Vị trí nút có thể khó thấy.” | Cách giải thích hợp lý nhưng chưa phải kết luận chắc chắn |
| **Giả thuyết có thể kiểm tra** | “Đưa nút ‘Học tiếp’ lên vùng dễ thấy sẽ giúp học viên mới tìm đúng bài nhanh hơn.” | Có đối tượng, thay đổi và tác động mong đợi để kiểm chứng |
| **Quyết định** | “Thử hai cách bố trí với một nhóm người dùng, đo tỷ lệ hoàn thành nhiệm vụ trước khi triển khai rộng.” | Hành động dựa trên mức độ hiểu biết hiện có, có cơ chế học tiếp |

Câu “Sáu trong tám người không thấy nút” và câu “75% học viên không thấy nút” **không tương đương**. Câu thứ nhất mô tả chính xác mẫu quan sát nhỏ; câu thứ hai suy rộng sang quần thể mà mẫu chưa đủ đại diện.

Tương tự:

- **Sự kiện:** Một khách hàng nói “Tôi cần xuất báo cáo PDF”. **Diễn giải chưa kiểm chứng:** “Mọi khách hàng cần tính năng xuất PDF”.
- **Sự kiện:** Một lỗi xuất hiện sau khi triển khai. **Giả định:** “Bản triển khai mới chắc chắn gây lỗi”. Cần điều tra tương quan thời gian, bản thay đổi, nhật ký và điều kiện tái hiện.
- **Sự kiện:** Sprint trước hoàn thành ít mục backlog. **Giả định:** “Nhóm làm việc kém hiệu quả”. Có thể tồn tại nhiều nguyên nhân: đầu việc quá lớn, phụ thuộc bên ngoài, định nghĩa Done chưa rõ hoặc chất lượng kỹ thuật giảm.

Một thói quen hữu ích trong họp là hỏi: **“Đâu là bằng chứng, đâu là cách chúng ta đang diễn giải và điều gì có thể khiến chúng ta đổi ý?”**

## 4. Điều đã biết cần có nguồn, phạm vi và hạn sử dụng

Khi ghi điều đã biết, tránh câu khẳng định trống như “Hệ thống chịu được 5.000 người dùng” hoặc “Khách hàng thích giao diện mới”. Một phát biểu đáng tin cậy tối thiểu nên chỉ ra:

1. **Nội dung:** cụ thể điều gì được quan sát hoặc kiểm chứng.
2. **Nguồn:** sự kiện trong hệ thống, báo cáo đo lường, nghiên cứu người dùng, thử tải hay tài liệu kỹ thuật được xác minh.
3. **Phạm vi:** loại người dùng, thiết bị, môi trường, phiên bản, khu vực và điều kiện áp dụng.
4. **Thời điểm:** bằng chứng được tạo ra khi nào và còn phù hợp không.
5. **Giới hạn:** dữ liệu thiếu, sai số, độ lệch chọn mẫu hoặc tác động chưa đo.

Ví dụ tốt:

> “Trong bản thử tải ngày 10/11, môi trường staging với cấu hình X xử lý 500 yêu cầu đồng thời trong 15 phút, thời gian phản hồi p95 là 420 ms và tỷ lệ lỗi là 0,2%. Kết quả chưa chứng minh hệ thống production chịu được tải tương tự.”

Phát biểu trên có giá trị hơn nhiều so với “Hệ thống đủ nhanh” vì nhóm biết điều gì đã đo và điều gì **chưa** được chứng minh. Các con số chỉ là minh họa giả định của một tình huống học tập.

### Mức độ tin cậy là một chiều khác

Có thể bổ sung thang nhận định nội bộ:

| Mức độ | Ví dụ | Cách dùng |
| --- | --- | --- |
| **Cao trong phạm vi rõ ràng** | Kết quả kiểm thử tự động được lặp lại, kèm mã nguồn/phiên bản và điều kiện chạy | Dùng để quyết định trong phạm vi đã thử; vẫn theo dõi khi hệ thống đổi |
| **Trung bình** | Dữ liệu hành vi đủ thời gian nhưng phân khúc người dùng còn thiếu | Tạm dùng để ưu tiên, tránh kết luận vượt phạm vi |
| **Thấp** | Một cuộc phỏng vấn, ý kiến cá nhân hoặc dữ liệu không có định nghĩa nhất quán | Ghi như tín hiệu, tạo câu hỏi và kiểm chứng thêm trước quyết định lớn |

Thang này chỉ là **quy ước giao tiếp**. Không có phép biến “tin cậy cao” thành “đúng 100%”. Đồng thời không nên đòi một mức chắc chắn như nhau cho mọi quyết định: đổi nhãn một nút có thể cần ít bằng chứng hơn thay toàn bộ cơ sở dữ liệu.

## 5. Nhận diện các dạng giả định trong sản phẩm và quy trình

Một backlog có thể chứa nhiều **giả định ngầm** hơn số câu hỏi được viết ra. Dùng bảng dưới để rà soát trước khi đầu tư lớn:

| Nhóm giả định | Câu nói thường gặp | Rủi ro nếu sai | Điều cần xác minh |
| --- | --- | --- | --- |
| **Nhu cầu / giá trị** | “Học viên muốn được nhắc qua email.” | Làm tính năng mà ít người cần hoặc gây phiền | Có vấn đề thực, ai gặp, tần suất và mức ảnh hưởng ra sao? |
| **Khả năng sử dụng** | “Người dùng sẽ hiểu biểu tượng này.” | Tính năng đúng nhưng khó dùng | Người dùng có tìm, hiểu và hoàn thành nhiệm vụ không? |
| **Khả thi kỹ thuật** | “Dịch vụ hiện tại lưu tiến độ ổn định khi mạng chập chờn.” | Lỗi mất dữ liệu, phát sinh chi phí sửa | Kiểm thử tình huống ngoại lệ, đồng bộ và phục hồi |
| **Hiệu quả kinh doanh / vận hành** | “Cách này không làm tăng chi phí hỗ trợ.” | Tăng chi phí, giảm tính bền vững | Chi phí gửi thông báo, vận hành, hỗ trợ và lợi ích đo được |
| **Chất lượng và an toàn** | “Không có dữ liệu cá nhân nhạy cảm trong sự kiện đo này.” | Thu thập hoặc xử lý dữ liệu vượt mục đích | Kiểm tra trường dữ liệu, quyền truy cập, lưu giữ và các yêu cầu áp dụng |
| **Phối hợp và kế hoạch** | “Nhóm đối tác sẽ cấp API tuần sau.” | Sprint Goal hoặc phát hành phụ thuộc điều ngoài tầm kiểm soát | Có cam kết và bản mẫu tích hợp có thể kiểm tra chưa? |
| **Đo lường** | “Sự kiện ‘lesson_completed’ luôn phản ánh việc học viên thực sự học xong.” | Quyết định dựa trên số đo sai | Xem lại điểm bắn sự kiện, trường hợp phát lặp và điều kiện tính |

Có những giả định **nền tảng**: nếu sai, toàn bộ hướng giải pháp cần đổi. Có những giả định **chi tiết**: nếu sai, nhóm chỉ cần chỉnh sửa nhỏ. Nhóm nên tìm giả định nền tảng trước, nhất là những điều kết hợp **bất định cao và hậu quả lớn**.

### Từ giả định chung chung sang giả thuyết kiểm tra được

Giả định mơ hồ: “Học viên thích lời nhắc”.

Giả thuyết cụ thể hơn:

> “Đối với học viên mới đã hoàn thành bài đầu nhưng chưa quay lại sau ba ngày, gửi **một lời nhắc có liên kết trở lại đúng bài** sẽ làm tăng tỷ lệ quay lại học trong bảy ngày so với nhóm không nhận lời nhắc, mà không làm tỷ lệ hủy nhận thông báo vượt ngưỡng chấp nhận.”

Để sử dụng trong thử nghiệm, nhóm phải xác định thêm: người dùng nào được đưa vào, “quay lại học” đo bằng sự kiện nào, khoảng thời gian, cỡ mẫu khả thi, mức tăng nào đủ đáng để triển khai, ngưỡng tác động phụ và cách đánh giá sự khác biệt. Không cần biến mọi cuộc thảo luận thành nghiên cứu thống kê, nhưng quyết định lớn cần tiêu chí rõ từ trước.

Một giả thuyết tốt **có thể sai**. Câu “Một số người chắc chắn sẽ thích” gần như không thể bác bỏ và ít giúp ra quyết định.

## 6. Từ điều chưa biết đến câu hỏi khám phá có ích

“Chúng ta chưa biết” chưa đủ để bắt đầu tìm hiểu. Câu hỏi nên gắn với **quyết định sắp phải đưa ra**.

| Câu hỏi quá rộng | Câu hỏi khám phá tốt hơn | Quyết định được hỗ trợ |
| --- | --- | --- |
| “Người dùng nghĩ gì về ứng dụng?” | “Học viên bỏ dở ở bước nào khi muốn tiếp tục khóa học đang học?” | Có nên ưu tiên sửa luồng tiếp tục học? |
| “Có nên dùng công nghệ mới không?” | “Giải pháp hiện tại có đáp ứng mục tiêu tải và khả năng phục hồi trong kịch bản X không?” | Tiếp tục kiến trúc hiện tại hay thử phương án khác? |
| “Bao giờ xong?” | “Với loại việc tương tự, thời gian hoàn thành từ bắt đầu đến Done phân bố thế nào?” | Đặt kỳ vọng thời gian và điều chỉnh WIP |
| “Khách hàng có muốn tính năng này?” | “Nhóm người dùng nào gặp vấn đề, hiện giải quyết ra sao và sẵn sàng thay đổi hành vi không?” | Đầu tư xây dựng hay dừng lại? |
| “Tại sao Sprint chậm?” | “Trong 4 Sprint gần đây, công việc chờ review, phụ thuộc bên ngoài và sửa lỗi chiếm bao nhiêu thời gian?” | Thử thay đổi quy trình ở điểm nghẽn nào? |

**Điều chưa biết đã nhận diện** thường được gọi là *known unknown*: “Chúng ta biết mình chưa biết tỷ lệ lỗi trong điều kiện mạng yếu”. Còn *unknown unknown* là những vấn đề nhóm chưa nghĩ tới. Nhóm không thể lập danh sách hoàn chỉnh các vấn đề chưa biết trước, nhưng có thể tạo điều kiện để chúng lộ ra: giao phần nhỏ, thử với người dùng thật, mời góc nhìn khác, kiểm thử tình huống biên và kiểm tra giả định sau mỗi vòng.

Không phải mọi câu hỏi đều cần nghiên cứu ngay. Câu hỏi nên được xử lý sớm nếu nó có thể làm thay đổi quyết định trọng yếu, làm tăng rủi ro lớn hoặc tạo phụ thuộc kéo dài. Câu hỏi ít tác động có thể được ghi nhận để kiểm tra khi đến lúc phù hợp.

## 7. Ưu tiên khám phá: bất định, tác động và chi phí học

Nhóm có thời gian hữu hạn. Nếu chỉ xác minh những điều dễ đo, nhóm có thể thu được nhiều con số nhưng vẫn không giải quyết được rủi ro quan trọng.

Một cách đánh giá đơn giản:

- **Bất định:** ta đang có ít bằng chứng đến đâu?
- **Tác động nếu sai:** quyết định có khiến phải làm lại, mất khách hàng, chậm phát hành hoặc tạo lỗi nghiêm trọng không?
- **Thời điểm cần biết:** có cần trả lời trước một cam kết hoặc quyết định gần tới không?
- **Chi phí và tốc độ khám phá:** có cách học nhanh, rẻ và an toàn hơn xây toàn bộ tính năng không?

| Giả định | Bất định | Hậu quả nếu sai | Hướng xử lý |
| --- | --- | --- | --- |
| “Người dùng sẵn sàng bật thông báo cho mọi khóa học.” | Cao | Cao: dễ gây khó chịu và ảnh hưởng niềm tin | Phỏng vấn theo tình huống, thử lựa chọn nhận thông báo và đo tỷ lệ chấp nhận |
| “API hiện tại hỗ trợ cập nhật tiến độ không trùng khi thử lại.” | Trung bình | Cao: có thể sai dữ liệu | Tạo thử nghiệm kỹ thuật và kiểm thử tình huống gửi lặp |
| “Đổi màu nút từ xám sang xanh giúp dễ thấy hơn.” | Trung bình | Thấp nếu thay đổi dễ đảo ngược | Thử trong prototype hoặc một nhóm nhỏ sau các giả định quan trọng |
| “Một đơn vị liên quan sẽ phản hồi trong hôm nay.” | Cao | Trung bình đến cao nếu đang chặn Sprint Goal | Hỏi xác nhận và chuẩn bị phương án giảm phụ thuộc |

Không cần gán điểm số giả chính xác cho mọi ô. Mục tiêu của bảng là khiến nhóm **nói rõ rủi ro**. Khi hậu quả liên quan bảo mật, an toàn, tính đúng đắn của dữ liệu hoặc nghĩa vụ tuân thủ, nhóm cần biện pháp kiểm soát phù hợp ngay cả khi chưa có nhiều dữ liệu lịch sử.

### Chọn phương pháp học phù hợp với loại câu hỏi

| Muốn tìm hiểu | Phương pháp thường hữu ích | Bằng chứng nhận được | Giới hạn cần lưu ý |
| --- | --- | --- | --- |
| Người dùng gặp khó khăn gì và vì sao | Phỏng vấn theo trải nghiệm đã xảy ra, quan sát công việc | Bối cảnh, động cơ, trở ngại, cách xử lý hiện tại | Lời nói và mẫu nhỏ không trực tiếp đo tần suất trong quần thể |
| Người dùng có tìm được nút hoặc hoàn thành tác vụ không | Kiểm thử khả dụng với prototype | Khó khăn quan sát trực tiếp, thời gian và tỷ lệ hoàn thành trong mẫu thử | Cần người tham gia phù hợp; kết quả phụ thuộc kịch bản |
| Có bao nhiêu người thực hiện một hành vi | Phân tích sự kiện và funnel với định nghĩa rõ | Tần suất, phân khúc, điểm rơi trong luồng | Tương quan không tự chứng minh nguyên nhân |
| Công nghệ có đáp ứng yêu cầu không | Spike, proof of concept, thử tải, kiểm thử tích hợp | Ràng buộc, giới hạn hoặc bằng chứng khả thi trong môi trường thử | Prototype không tự chứng minh khả năng vận hành thật |
| Một thay đổi có gây ra cải thiện không | Thử nghiệm có đối chứng / phân nhóm ngẫu nhiên nếu phù hợp | Bằng chứng về tác động nhân quả mạnh hơn quan sát trước–sau | Phải kiểm soát sai lệch, số lượng mẫu, thời gian và tác động phụ |
| Vì sao công việc giao chậm | Quan sát workflow, dữ liệu cycle time/WIP, trao đổi với nhóm | Điểm chờ, biến thiên, phụ thuộc và trở ngại | Định nghĩa các mốc đo phải nhất quán |

**Thử nghiệm rẻ nhất không phải lúc nào cũng tốt nhất.** Một cuộc thăm dò hỏi “Bạn có thích tính năng này không?” có thể rẻ nhưng quá yếu để quyết định đầu tư lớn. Hãy chọn **thử nghiệm nhỏ nhất tạo ra bằng chứng đủ dùng cho quyết định**.

## 8. Chu trình tư duy thực nghiệm trong Agile

~~~mermaid
flowchart LR
    A["1. Nêu quyết định<br/>cần đưa ra"] --> B["2. Tách điều biết,<br/>giả định, câu hỏi"]
    B --> C["3. Chọn rủi ro<br/>cần học trước"]
    C --> D["4. Thiết kế thử nghiệm<br/>và tiêu chí đánh giá"]
    D --> E["5. Thực hiện, quan sát,<br/>thu thập bằng chứng"]
    E --> F["6. Cập nhật hiểu biết<br/>và quyết định"]
    F -->|"Xuất hiện câu hỏi mới"| B
    F -->|"Đã đủ bằng chứng"| G["Giao phần giá trị tiếp theo<br/>và tiếp tục theo dõi"]
~~~

### Bước 1 — Nêu rõ quyết định

Ví dụ: “Có nên dành hai Sprint xây hệ thống nhắc học bằng email hay nên ưu tiên cải thiện nút tiếp tục học?”. Khi quyết định rõ, nhóm biết cần thu thập **loại bằng chứng nào**. Nếu chưa có quyết định cần đưa ra, việc khám phá dễ bị kéo dài thành thu thập thông tin vô hạn.

### Bước 2 — Liệt kê những gì biết và chưa biết

Viết riêng các dữ kiện đã kiểm tra (“Tỷ lệ quay lại 7 ngày là X trong phân khúc Y”), giả định (“Quên học là lý do chính”) và câu hỏi (“Cách nào ít gây phiền mà giúp học viên quay lại?”). Nêu nguồn và lỗ hổng thay vì lập luận bằng chức danh hoặc thâm niên người phát biểu.

### Bước 3 — Chọn rủi ro học trước

Nếu người dùng không có vấn đề cần giải quyết, tính khả thi của dịch vụ gửi email không còn là rủi ro đầu tiên. Nếu nhu cầu đã được chứng minh nhưng nguy cơ mất dữ liệu lớn, cần chứng minh tính đúng đắn kỹ thuật trước khi phát hành. Thứ tự phụ thuộc vào **quyết định và hậu quả nếu giả định sai**.

### Bước 4 — Thiết kế kiểm chứng trước khi nhìn kết quả

Nêu: đối tượng, thay đổi hoặc phương pháp quan sát, biến đo, khoảng thời gian, nguồn dữ liệu, ngưỡng hỗ trợ quyết định, các chỉ số cảnh báo và phương án khi kết quả không rõ. Định nghĩa trước giúp giảm thói quen chọn một con số thuận lợi sau khi thử.

### Bước 5 — Quan sát cả kết quả không như mong đợi

Thực hiện nhỏ và có kiểm soát: phỏng vấn vài người dùng phù hợp, dựng prototype, kiểm tra kỹ thuật, hoặc triển khai cho một nhóm hạn chế nếu an toàn. Chú ý bằng chứng trái với giả thuyết, dữ liệu thiếu và lỗi đo. Nếu thử nghiệm thất bại, bài học vẫn có giá trị khi nó giúp tránh một quyết định sai đắt đỏ.

### Bước 6 — Quyết định và ghi lại điều đã học

Các lựa chọn hợp lệ gồm: **tiếp tục**, **thay đổi hướng giải pháp**, **thử thêm vì bằng chứng chưa đủ**, hoặc **dừng đầu tư**. Không phải mọi thử nghiệm đều kết luận được ngay. Sau khi quyết định, cập nhật backlog, tiêu chí chấp nhận, rủi ro và quy trình làm việc.

## 9. Ví dụ xuyên suốt: vì sao học viên không quay lại học?

Một nhóm phát triển nền tảng đào tạo muốn cải thiện việc học viên tiếp tục khóa học sau bài đầu. Các số liệu dưới đây là **giả định minh họa** để thực hành phân loại; chúng không phải kết quả nghiên cứu thực tế.

### 9.1. Trạng thái hiểu biết ban đầu

| Phát biểu | Loại lúc đầu | Vì sao |
| --- | --- | --- |
| “Trong 30 ngày, 2.000 học viên mới bắt đầu bài đầu; 600 người hoàn thành bài đầu; trong số 600 người đó, 180 người mở bài tiếp theo trong vòng bảy ngày.” | **Đã biết có điều kiện** | Chỉ khi xác nhận cách tính người dùng duy nhất, định nghĩa “hoàn thành” và “mở bài tiếp theo”, nguồn log và tính đầy đủ dữ liệu |
| “Phần lớn học viên bỏ dở vì quên quay lại.” | **Giả định** | Log cho thấy hành vi, không trực tiếp chỉ ra nguyên nhân |
| “Gửi email nhắc sau ba ngày sẽ giải quyết vấn đề.” | **Giả định giải pháp** | Chưa biết người dùng có muốn email hay email có tạo thay đổi tích cực không |
| “Trong nhóm 600 người hoàn thành, điều gì cản trở 420 người còn lại mở bài tiếp theo trong bảy ngày?” | **Điều cần khám phá** | Câu hỏi mở về bối cảnh và nguyên nhân |
| “Bao nhiêu người thực sự không thấy nút ‘Học tiếp’?” | **Điều cần khám phá** | Cần kiểm tra khả dụng hoặc phân tích hành vi phù hợp |

Nếu 180/600 người mở bài tiếp theo trong vòng bảy ngày, tỷ lệ tương ứng là **30% trong tập 600 người**. Không được nói “30% tất cả học viên quay lại”, vì mẫu số và điều kiện đã đổi. Đây là ví dụ điển hình về cách một con số đúng biến thành kết luận sai khi bị tách khỏi ngữ cảnh.

### 9.2. Câu hỏi nghiên cứu và bằng chứng ban đầu

Nhóm chọn hai câu hỏi:

1. Học viên muốn tiếp tục học nhưng không tìm được đúng vị trí, hay họ chưa có nhu cầu quay lại?
2. Nếu cần can thiệp, cải thiện luồng tiếp tục học hay gửi email nhắc mang lại lợi ích lớn hơn với ít phiền nhiễu hơn?

Nhóm kiểm tra tính toàn vẹn dữ liệu sự kiện, quan sát học viên thực hiện nhiệm vụ tìm bài đang học, phỏng vấn về một lần bỏ dở gần đây và phân tích các nhóm thiết bị. Trong phiên thử khả dụng giả định, một số học viên phải mở nhiều màn hình mới tìm được bài; nhiều người khác nói họ chủ động tạm nghỉ vì lịch cá nhân. Hai kết quả này cho thấy có **nhiều nguyên nhân khả dĩ**, nên lời nhắc hàng loạt chưa chắc là giải pháp đúng.

Nhóm không suy rộng số người trong nghiên cứu nhỏ thành tỷ lệ của toàn bộ người học. Kết quả định tính giúp hình thành và chọn giả thuyết; số liệu hành vi có thể giúp ước lượng độ phổ biến khi được thu thập đúng cách.

### 9.3. Chọn một thử nghiệm tăng dần

Giả thuyết được ưu tiên:

> “Với học viên mới đã hoàn thành bài đầu, đặt nút ‘Học tiếp’ trên trang khóa học và mở đúng bài chưa học sẽ tăng tỷ lệ mở bài tiếp theo trong bảy ngày, đồng thời không làm tăng lỗi điều hướng và yêu cầu hỗ trợ.”

Nhóm làm lát cắt nhỏ: lưu tiến độ, hiện tên bài tiếp theo, kiểm thử tình huống học trên nhiều thiết bị và phát hành có kiểm soát. Nếu có đủ lượng người dùng và điều kiện phù hợp, nhóm có thể so sánh nhóm trải nghiệm cũ với nhóm trải nghiệm mới bằng phân nhóm ngẫu nhiên. Nếu lượng mẫu nhỏ, nhóm có thể ưu tiên quan sát khả dụng, dữ liệu định tính và một đợt thí điểm, đồng thời **không tuyên bố đã chứng minh tác động thống kê**.

| Thành phần thử nghiệm | Ví dụ thiết kế |
| --- | --- |
| **Đối tượng** | Học viên mới vừa hoàn thành bài đầu, phân định nhất quán theo tài khoản |
| **Biến thay đổi** | Vị trí và hành vi nút “Học tiếp”; các yếu tố khác giữ ổn định nếu có thể |
| **Chỉ số chính** | Tỷ lệ mở bài tiếp theo trong bảy ngày từ lần hoàn thành bài đầu |
| **Chỉ số phụ** | Thời gian tìm bài, số lần điều hướng lỗi, tỷ lệ hoàn thành bài tiếp theo |
| **Chỉ số bảo vệ** | Lỗi mất tiến độ, số yêu cầu hỗ trợ, tác động hiệu năng |
| **Điều kiện ra quyết định** | Định trước mức cải thiện có ý nghĩa thực tế, bằng chứng đủ tin cậy, phạm vi triển khai và ngưỡng tác động phụ |
| **Nếu kết quả chưa rõ** | Kiểm tra cỡ mẫu, phân khúc, thời gian quan sát, chất lượng đo; quyết định thử tiếp hoặc không đầu tư lớn |

Ví dụ, nếu tỷ lệ quan sát tăng từ 30% lên 33%, nhóm **chưa được tự động kết luận** giao diện mới gây tăng 3 điểm phần trăm: cần xem cách chia nhóm, kích thước mẫu, biến động ngẫu nhiên, thời điểm và những thay đổi cùng xảy ra. **Khác biệt quan sát được** và **hiệu quả nhân quả được kiểm chứng** là hai điều khác nhau.

### 9.4. Cập nhật tri thức sau một vòng học

Giả sử nghiên cứu khả dụng cho thấy nhiều người thử nghiệm tìm nút mới nhanh hơn, nhưng dữ liệu hành vi sau thí điểm chưa đủ để kết luận có tăng tỷ lệ quay lại dài hạn. Bảng hiểu biết nên cập nhật trung thực:

| Trước khi thử | Sau khi thử | Hành động |
| --- | --- | --- |
| Giả định: nút hiện tại khó tìm | Có **bằng chứng định tính trong mẫu thử** rằng vị trí cũ gây khó khăn | Giữ phương án mới để tiếp tục kiểm chứng với người dùng phù hợp |
| Giả định: nút mới tăng tỷ lệ quay lại | **Chưa đủ bằng chứng** về mức tăng dài hạn | Theo dõi chỉ số đã định nghĩa trong khoảng thời gian phù hợp |
| Giả định: gửi email là cách tốt nhất | Vẫn là **giả định chưa kiểm chứng** | Chưa xây hàng loạt; nghiên cứu mức chấp nhận và tác động phụ nếu cần |
| Đã biết trong mẫu 30 ngày: 180/600 học viên mở bài tiếp theo | Vẫn là đường cơ sở **trong phạm vi đo trước thay đổi**, nếu dữ liệu đạt chất lượng | Dùng để lập so sánh tiếp, không mở rộng sai mẫu số |

Nhóm đã học được điều có ích dù chưa thể tuyên bố “tính năng thành công”. Đây là tinh thần **empiricism**: quyết định dựa trên bằng chứng hiện có, minh bạch về giới hạn, rồi thích ứng theo điều mới.

## 10. Kết nối tư duy thực nghiệm với các thực hành Agile

### Product Backlog và user story

**Backlog** không chỉ là danh sách “tính năng phải xây”; nó có thể phản ánh cơ hội, vấn đề người dùng, rủi ro và những việc cần làm để học thêm. Một user story mô tả nhu cầu mong muốn, nhưng bản thân câu chuyện chưa chứng minh nhu cầu đó tồn tại rộng rãi. Ví dụ:

> “Là học viên đang học dở, tôi muốn tiếp tục đúng bài đã dừng để không phải tìm lại thủ công.”

Nhóm có thể gắn với user story các trường thông tin: bằng chứng về vấn đề, giả định giải pháp, tiêu chí chấp nhận và cách đánh giá kết quả sau phát hành. **Acceptance criteria** giúp xác định phần mềm cần hoạt động thế nào; **tiêu chí kiểm chứng giá trị** giúp biết giải pháp có ích hay không. Chúng có liên hệ nhưng không thay thế nhau.

### Scrum: minh bạch, kiểm tra và thích ứng

Scrum dựa trên tư duy thực nghiệm, với ba trụ cột **transparency, inspection, adaptation**:

- **Transparency — minh bạch:** các bên hiểu trạng thái công việc, chất lượng, rủi ro và điều chưa chắc chắn. Definition of Done làm rõ khi nào Increment đáp ứng tiêu chuẩn chất lượng.
- **Inspection — kiểm tra:** nhóm xem Increment, tiến độ hướng đến Sprint Goal, phản hồi sản phẩm và cách phối hợp; dùng thông tin thực tế thay vì báo cáo cho có.
- **Adaptation — thích ứng:** cập nhật kế hoạch và cách làm dựa trên điều vừa học. Product Backlog có thể được điều chỉnh sau Sprint Review; Sprint Retrospective tập trung cải thiện cách nhóm làm việc.

**Sprint Goal** giúp giữ hướng đi trong khi nhóm học thêm và điều chỉnh chi tiết công việc. Không nên viện lý do “Agile phải linh hoạt” để liên tục đổi mục tiêu tùy hứng hoặc giảm chất lượng nhằm kịp mốc. Increment vẫn phải đáp ứng Definition of Done.

Một Spike hoặc thử nghiệm khám phá có thể giúp giảm bất định, nhưng việc tổ chức nó trong Scrum cần gắn với giá trị và mục tiêu phù hợp; không biến toàn bộ Sprint thành nghiên cứu không có đầu ra rõ ràng.

### Kanban và Lean: đo luồng, kiểm chứng điểm nghẽn

Trong quản lý dòng công việc, các nhận định như “Review lúc nào cũng chậm” cần dữ liệu về thời gian chờ, work item age, cycle time, WIP, throughput và quan sát thực tế. Chẳng hạn, nếu công việc thường chờ kiểm thử nhiều ngày, nhóm có thể thử giới hạn WIP hoặc cùng giải quyết việc đang bị chặn, sau đó kiểm tra liệu thời gian hoàn thành có cải thiện mà không tăng lỗi.

Lean nhắc nhóm nhìn **toàn dòng giá trị**; tối ưu thời gian lập trình có thể ít hiệu quả nếu điểm nghẽn nằm ở phê duyệt, phát hành hoặc hiểu sai nhu cầu. Định luật Little và các chỉ số flow hữu ích khi ranh giới đo rõ ràng, dữ liệu đủ phù hợp; không nên dùng công thức để đưa ra lời hứa chắc chắn cho một công việc riêng lẻ.

### XP và thực hành kỹ thuật: giả thuyết cũng tồn tại trong mã

Giả định “mỗi lần lưu tiến độ đều thành công” có thể kiểm chứng bằng kiểm thử tự động với điều kiện mạng gián đoạn; “đổi cấu trúc không ảnh hưởng hành vi” cần bộ kiểm thử hồi quy; “mọi thay đổi đều tích hợp được” cần tích hợp liên tục và phản hồi sớm. TDD, refactoring, CI, kiểm thử tích hợp và phát hành nhỏ giúp biến **rủi ro kỹ thuật** thành tín hiệu sớm, hỗ trợ khả năng thích ứng của sản phẩm.

## 11. Công cụ thực hành: sổ ghi tri thức và giả định

Không cần công cụ phức tạp để bắt đầu. Một bảng chung, cập nhật trong quá trình làm việc, có thể lưu dấu vết từ giả định đến bằng chứng và quyết định:

| ID | Phát biểu / câu hỏi | Trạng thái | Bằng chứng hoặc khoảng trống | Mức tác động | Cách kiểm chứng tiếp | Người theo dõi |
| --- | --- | --- | --- | --- | --- | --- |
| K-01 | 180/600 học viên hoàn thành bài đầu mở bài tiếp theo trong 7 ngày ở kỳ đo A | Đã biết có điều kiện | Báo cáo sự kiện, cần xác minh định nghĩa và phạm vi | Cao | Kiểm tra nguồn log và phân khúc | Nhóm sản phẩm + phân tích |
| A-02 | Học viên không quay lại chủ yếu vì quên | Giả định | Chưa có bằng chứng trực tiếp về nguyên nhân | Cao | Phỏng vấn trải nghiệm bỏ dở gần đây | Product Owner |
| U-03 | Nút “Học tiếp” có dễ tìm trên điện thoại không? | Cần khám phá | Chưa có kiểm thử khả dụng trên thiết bị di động | Trung bình–cao | Quan sát nhiệm vụ với người học mục tiêu | Thiết kế + phát triển |
| A-04 | Lưu tiến độ khi mất mạng không mất dữ liệu | Giả định kỹ thuật | Chưa có thử nghiệm điều kiện offline/retry | Cao | Viết kiểm thử và mô phỏng lỗi mạng | Developers |

Một bản ghi chất lượng nên được cập nhật khi xuất hiện bằng chứng, với **ngày ghi nhận**, **nguồn**, **ngữ cảnh**, **quyết định liên quan** và **điều gì sẽ khiến nhóm xem xét lại**. Không cần giữ bảng này như thủ tục hành chính; chỉ cần giúp người nhận việc tiếp theo thấy được logic của quyết định.

### Mẫu ngắn cho một giả định có rủi ro

~~~text
Quyết định cần đưa ra:
  Có nên ưu tiên tính năng X trong vòng phát triển tới?

Điều đã biết:
  [Dữ kiện + nguồn + thời gian + đối tượng + giới hạn]

Giả định quan trọng:
  [Nếu điều này sai, quyết định sẽ bị ảnh hưởng ra sao?]

Điều cần khám phá:
  [Câu hỏi cụ thể để ra quyết định]

Giả thuyết:
  [Đối tượng] + [thay đổi] + [tác động dự kiến]

Cách kiểm chứng:
  [Phương pháp] + [chỉ số/quan sát] + [thời gian] + [mức đủ bằng chứng]

Kết quả:
  [Bằng chứng ủng hộ/phản bác/chưa rõ + giới hạn]

Quyết định tiếp:
  [Tiếp tục, điều chỉnh, thử thêm hoặc dừng] + [người phụ trách]
~~~

## 12. Những sai lầm thường gặp

**1. Biến ý kiến của người có thâm niên thành sự thật.** Kinh nghiệm giúp nêu giả thuyết tốt, nhưng cần phân biệt “tôi tin” với “chúng ta đã đo/quan sát trong điều kiện nào”.

**2. Gọi dữ liệu là bằng chứng mà không kiểm tra cách thu thập.** Một biểu đồ đẹp vẫn có thể dùng sự kiện phát lặp, mẫu số sai hoặc bỏ sót người dùng. Độ chính xác của phép tính không cứu được một định nghĩa sai.

**3. Nhầm tương quan với nguyên nhân.** Người dùng có bật thông báo có thể quay lại học nhiều hơn vì họ vốn tích cực hơn. Chỉ quan sát hai đặc điểm đi cùng không chứng minh thông báo tạo tác động.

**4. Chỉ tìm tín hiệu xác nhận ý mình.** Nếu nhóm đã thích giải pháp gửi email, họ dễ bỏ qua người dùng không muốn nhận thư. Hãy chủ động hỏi “Bằng chứng nào có thể bác bỏ giả thuyết?”.

**5. Tránh ghi giả định vì sợ thiếu chắc chắn.** Công khai bất định là điều kiện của minh bạch; giả vờ chắc chắn làm giảm khả năng nhận phản hồi sớm.

**6. Muốn đo mọi thứ trước khi bắt đầu.** Không phải quyết định nào cũng cần nghiên cứu dài. Với thay đổi nhỏ, dễ đảo ngược và ít rủi ro, nhóm có thể thử an toàn rồi theo dõi. Với rủi ro bảo mật, mất dữ liệu hay tác động lớn, mức kiểm chứng phải cao hơn.

**7. Đánh đồng hoàn thành tính năng với giả thuyết giá trị đã đúng.** Phần mềm chạy theo yêu cầu là bằng chứng về **việc triển khai**; người dùng được lợi hay không cần bằng chứng từ sử dụng thực tế và mục tiêu sản phẩm.

**8. Thử nghiệm mà không xác định tiêu chí đánh giá trước.** Sau khi có số liệu, nhóm dễ lựa chọn chỉ số thuận lợi hoặc đổi khoảng thời gian để tuyên bố thành công.

**9. Dùng kết quả của nhóm nhỏ để khẳng định cho mọi người dùng.** Nghiên cứu định tính rất hữu ích để phát hiện vấn đề và giải thích hành vi, nhưng một mẫu thuận tiện không thể tự đưa ra tỷ lệ cho cả quần thể.

**10. Không cập nhật giả định sau khi học.** Nếu kết quả mới không được đưa vào backlog, tài liệu quyết định và tiêu chí chấp nhận, nhóm có thể lặp lại chính sai lầm cũ.

## 13. Bài tập áp dụng

### Bài tập A — Phân loại phát biểu

Nhóm đang xây tính năng tìm kiếm khóa học. Với mỗi câu dưới đây, hãy chọn **đã biết**, **giả định** hoặc **cần khám phá** và nêu điều kiện để phân loại:

1. “Theo log đã xác minh của tuần trước, 230/1.000 phiên tìm kiếm trả về trang kết quả rỗng.”
2. “Người dùng bỏ cuộc vì thuật toán tìm kiếm thiếu từ đồng nghĩa.”
3. “Có bao nhiêu truy vấn kết quả rỗng thực sự là do lỗi chính tả?”
4. “Nếu thêm đề xuất từ khóa, tỷ lệ người dùng tìm được khóa học phù hợp sẽ tăng.”
5. “Trong thử nghiệm trên môi trường staging với dữ liệu X, truy vấn p95 hoàn thành dưới 300 ms.”

**Gợi ý tự đối chiếu:** (1) Đã biết trong đúng tập phiên, khoảng thời gian và định nghĩa đã kiểm tra; (2) giả định nguyên nhân; (3) điều cần khám phá; (4) giả thuyết/giả định cần kiểm chứng; (5) đã biết trong điều kiện thử nghiệm, chưa đại diện cho production.

### Bài tập B — Thiết kế một vòng học

Tình huống: Product Owner muốn có bộ lọc khóa học theo trình độ vì cho rằng người mới học không tìm được nội dung phù hợp.

Hãy hoàn thành:

1. **Quyết định cần đưa ra:** xây ngay bộ lọc hay kiểm tra nhu cầu trước?
2. **Dữ liệu đã biết:** hiện đã có bằng chứng nào, ai cung cấp và trong phạm vi nào?
3. **Giả định rủi ro:** người dùng có thực sự gặp khó khăn, có hiểu nhãn trình độ, có dữ liệu phân loại khóa học đáng tin không?
4. **Câu hỏi cần khám phá:** những người mới bắt đầu hiện tìm khóa học thế nào, bị chặn ở đâu, phân loại nào có ý nghĩa với họ?
5. **Thử nghiệm nhỏ:** quan sát người dùng thực hiện nhiệm vụ tìm khóa học; thử prototype bộ lọc; kiểm tra dữ liệu gán nhãn khóa học.
6. **Tiêu chí quyết định:** bằng chứng nào khiến nhóm xây tiếp, thay đổi phương án hoặc hoãn tính năng?

Không có một câu trả lời mẫu duy nhất. Lời giải tốt phải **nêu được ranh giới của điều đã biết**, có giả thuyết có thể kiểm tra, và chọn cách khám phá đủ tin cậy so với chi phí sai.

## 14. Checklist dùng trong mỗi vòng phát triển

Trước khi cam kết với một tính năng, thay đổi kiến trúc hoặc cải tiến quy trình, nhóm có thể rà lại:

- [ ] Chúng ta đang ra **quyết định cụ thể** nào?
- [ ] Có tách **quan sát**, **diễn giải** và **giả định** trong lời giải thích không?
- [ ] Mọi điều gọi là “đã biết” có **nguồn, phạm vi, thời điểm, giới hạn** không?
- [ ] Giả định nào có **hậu quả lớn nhất nếu sai**?
- [ ] Điều cần khám phá đã được viết thành **câu hỏi trả lời được** chưa?
- [ ] Có cách kiểm chứng nhỏ, an toàn và đủ hữu ích trước khi đầu tư lớn không?
- [ ] Thước đo, tiêu chí quyết định và tác động phụ được xác định **trước khi xem kết quả** chưa?
- [ ] Khi bằng chứng trái kỳ vọng xuất hiện, nhóm có sẵn sàng cập nhật quyết định không?
- [ ] Kết quả đã được phản ánh vào backlog, chất lượng sản phẩm hoặc workflow chưa?

## 15. Tài liệu tham khảo và bước học tiếp

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị nền tảng về cộng tác, phần mềm hoạt động được, phản hồi và khả năng thích ứng.
- [The Scrum Guide](https://scrumguides.org/): nền tảng thực nghiệm của Scrum, ba trụ cột minh bạch, kiểm tra, thích ứng, và mối quan hệ giữa Product Goal, Sprint Goal, Increment.
- [The Kanban Guide](https://kanbanguides.org/): các khái niệm dòng chảy, WIP và số đo cơ bản giúp kiểm tra những nhận định về hiệu quả công việc.

**Điểm cốt lõi cần nhớ:** Tư duy thực nghiệm không đòi hỏi nhóm biết tất cả trước khi làm; nó đòi hỏi nhóm **biết rõ mình đã xác minh điều gì, đang tin điều gì và cần học thêm điều gì**. Mỗi lần giao phần giá trị nhỏ, nhận phản hồi và cập nhật quyết định là một cơ hội biến bất định thành tri thức đủ tốt cho bước tiếp theo.
