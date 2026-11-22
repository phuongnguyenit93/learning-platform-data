# Đánh giá mức độ phức tạp, tốc độ thay đổi và giá trị kinh doanh

Khi phân rã một domain thành các subdomain, đội phát triển cần hiểu mỗi phần nghiệp vụ quan trọng đến đâu, khó giải quyết ở mức nào và thường xuyên thay đổi ra sao. Ba góc nhìn này giúp tổ chức quyết định nên đầu tư chuyên gia, thời gian khám phá và năng lực mô hình hóa vào đâu; phần nào có thể chuẩn hóa, mua hoặc sử dụng dịch vụ có sẵn.

Trong Domain-Driven Design (DDD), việc đánh giá subdomain hỗ trợ **strategic design**: xác định đâu là năng lực tạo khác biệt cạnh tranh, đâu là năng lực hỗ trợ hoạt động và đâu là bài toán phổ biến có thể dùng giải pháp chung. Đánh giá tốt cũng giúp đội nhận ra miền nào cần khám phá sâu, miền nào cần khả năng thích nghi nhanh và miền nào nên được giữ đơn giản.

Ba câu hỏi cần trả lời riêng:

- **Độ phức tạp:** Nghiệp vụ có bao nhiêu quy tắc, trạng thái, ngoại lệ và mối quan hệ cần hiểu để đưa ra quyết định đúng?
- **Tốc độ thay đổi:** Nhu cầu, chính sách, quy tắc và cách vận hành của nghiệp vụ thay đổi thường xuyên đến mức nào?
- **Giá trị kinh doanh:** Năng lực này đóng góp ra sao vào mục tiêu, kết quả cho khách hàng và lợi thế cạnh tranh của tổ chức?

Không nên gộp ba câu hỏi thành một điểm số duy nhất. Một subdomain có thể rất phức tạp nhưng không tạo khác biệt; một subdomain có quy tắc đơn giản vẫn có thể là trung tâm của chiến lược kinh doanh; một subdomain ít phức tạp hôm nay có thể thay đổi nhanh khi thị trường hoặc mô hình kinh doanh chuyển hướng.

## 1. Đặt đánh giá trong đúng phạm vi domain và subdomain

**Domain** là lĩnh vực hoạt động mà tổ chức cần hiểu và giải quyết để đạt mục tiêu kinh doanh. **Subdomain** là một phần của domain, thường tập trung vào một nhóm vấn đề hoặc năng lực nghiệp vụ tương đối rõ ràng.

Ví dụ, domain thương mại điện tử có thể được phân rã thành các subdomain:

- Quản lý danh mục sản phẩm.
- Tìm kiếm và gợi ý sản phẩm.
- Giá và khuyến mãi.
- Đặt hàng và thanh toán.
- Quản lý tồn kho.
- Giao nhận.
- Đổi trả và hoàn tiền.
- Chăm sóc khách hàng.

Ranh giới phân rã nên dựa trên vấn đề nghiệp vụ, trách nhiệm và cách tổ chức tạo ra giá trị. Không nên mặc định mỗi phòng ban, microservice, cơ sở dữ liệu hoặc nhóm màn hình là một subdomain. Cấu trúc tổ chức và kiến trúc kỹ thuật có thể cung cấp manh mối, nhưng chúng không tự xác định cấu trúc miền.

Trước khi chấm điểm, hãy viết mô tả ngắn cho từng subdomain: nó giải quyết vấn đề gì, ai là người sử dụng hoặc chịu trách nhiệm, đầu vào và kết quả chính là gì, phạm vi nào nằm ngoài nó. Nếu hai người hiểu phạm vi khác nhau, điểm đánh giá sau đó sẽ không thể so sánh đáng tin cậy.

## 2. Đánh giá độ phức tạp nghiệp vụ

Độ phức tạp nghiệp vụ (business complexity) phản ánh mức độ khó khi hiểu, ra quyết định và thực thi các quy tắc của subdomain. Nó đến từ chính bản chất bài toán và các lựa chọn nghiệp vụ, không đơn thuần đến từ công nghệ đang dùng.

Một quy trình có nhiều bước chưa chắc phức tạp. Nếu mỗi bước đều tuyến tính, quy tắc rõ ràng và ít ngoại lệ, quy trình đó có thể dễ hiểu. Ngược lại, một quyết định chỉ có vài bước nhưng phụ thuộc vào nhiều điều kiện, thời điểm, quyền hạn và ngoại lệ có thể rất phức tạp.

### 2.1. Những dấu hiệu tạo nên độ phức tạp

**Số lượng và sự tương tác của quy tắc**

- Có bao nhiêu điều kiện ảnh hưởng đến một quyết định?
- Các quy tắc có phụ thuộc lẫn nhau hoặc có thứ tự ưu tiên không?
- Có quy tắc nào thay đổi theo loại khách hàng, sản phẩm, khu vực, kênh hoặc thời điểm không?
- Hai quy tắc có thể xung đột và cần cơ chế giải quyết không?

**Ngoại lệ và tình huống biên**

- Tỷ lệ trường hợp không đi theo luồng thông thường là bao nhiêu?
- Có nhiều tình huống cần con người đánh giá hay phê duyệt không?
- Khi dữ liệu thiếu, sai hoặc đến trễ thì nghiệp vụ xử lý thế nào?
- Có những trường hợp hiếm nhưng gây hậu quả lớn không?

**Trạng thái và vòng đời**

- Đối tượng nghiệp vụ có nhiều trạng thái và chuyển trạng thái không?
- Có chuyển trạng thái nào chỉ được phép khi thỏa một số điều kiện?
- Có thao tác nào cần hoàn tác, hủy, thử lại hoặc bù trừ không?
- Thời gian, hạn chót, thứ tự sự kiện hoặc dữ liệu lịch sử có ảnh hưởng đến kết quả không?

**Số lượng bên tham gia và sự phụ thuộc**

- Có bao nhiêu vai trò, nhóm, đối tác hoặc hệ thống tham gia?
- Mỗi bên có mục tiêu và cách hiểu khác nhau không?
- Có bàn giao, chờ xác nhận hoặc phối hợp nhiều bên không?
- Một quyết định ở subdomain này ảnh hưởng đến những năng lực nào khác?

**Kiến thức chuyên môn và tính khó diễn đạt**

- Quy tắc có phụ thuộc vào kinh nghiệm của một số chuyên gia không?
- Cùng một thuật ngữ có được các nhóm hiểu khác nhau không?
- Có những đánh đổi cần cân nhắc giữa chi phí, tốc độ, chất lượng và rủi ro không?
- Việc giải thích vì sao một trường hợp được xử lý theo cách cụ thể có khó không?

Các dấu hiệu này giúp nhận diện độ phức tạp trong mô hình nghiệp vụ. Số lượng bảng dữ liệu, dòng mã, API hoặc công nghệ tích hợp có thể phản ánh độ phức tạp kỹ thuật, nhưng không nên dùng chúng thay thế cho phân tích nghiệp vụ. Một hệ thống cũ có thể khó bảo trì vì lựa chọn kỹ thuật lịch sử dù quy tắc kinh doanh đơn giản; một bài toán nghiệp vụ phức tạp có thể đang được xử lý bằng bảng tính.

### 2.2. Thang đánh giá độ phức tạp

Có thể dùng thang 1–5 để tạo cách nói chung trong buổi khám phá. Các mức dưới đây là điểm tham chiếu; tổ chức cần hiệu chỉnh theo lĩnh vực và quy mô của mình.

| Điểm | Mô tả | Dấu hiệu gợi ý |
|---|---|---|
| 1 – Rất thấp | Quy tắc đơn giản, ít tình huống và dễ dự đoán | Một vài quy tắc ổn định, ít ngoại lệ, ít vai trò |
| 2 – Thấp | Có nhiều điều kiện nhưng phần lớn độc lập và dễ giải thích | Một số nhánh xử lý, ngoại lệ ít và có hướng dẫn rõ |
| 3 – Trung bình | Nhiều quy tắc, trạng thái hoặc vai trò cần phối hợp | Có phụ thuộc giữa quy tắc, nhiều trường hợp cần xác minh |
| 4 – Cao | Quy tắc tương tác phức tạp, ngoại lệ đáng kể và cần chuyên gia | Nhiều điều kiện theo ngữ cảnh, quyền hạn và thời điểm; có đánh đổi |
| 5 – Rất cao | Bài toán khó dự đoán, kiến thức chuyên môn sâu và nhiều quyết định liên kết | Quy tắc phụ thuộc chặt chẽ, ngoại lệ khó bao quát, sai quyết định gây hậu quả lớn |

Không cần đếm số quy tắc một cách máy móc. Hãy xem xét mức độ tương tác giữa chúng, mức độ khó giải thích và khả năng xử lý trường hợp mới. Một trăm quy tắc độc lập, dễ tra cứu có thể ít phức tạp hơn mười quy tắc phụ thuộc lẫn nhau.

## 3. Đánh giá tốc độ thay đổi

Tốc độ thay đổi (rate of change) cho biết nghiệp vụ biến động thường xuyên và sâu rộng đến đâu. Nó phản ánh nhịp thay đổi của thị trường, khách hàng, chiến lược, chính sách, luật lệ, đối tác và cách vận hành.

Tốc độ thay đổi không đồng nghĩa với số lần phát hành phần mềm hoặc số commit trong repository. Một đội có thể triển khai hàng chục lần mỗi ngày nhưng quy tắc nghiệp vụ gần như không đổi. Ngược lại, một chính sách giá thay đổi mỗi tuần có thể tạo áp lực lớn dù hệ thống chỉ phát hành mỗi tháng.

### 3.1. Những nguồn tạo ra thay đổi

- **Thị trường và cạnh tranh:** đối thủ đưa ra dịch vụ mới, giá mới hoặc cách phục vụ mới.
- **Khách hàng:** kỳ vọng, hành vi, phân khúc và nhu cầu thay đổi.
- **Chiến lược:** tổ chức mở kênh bán hàng, thị trường, sản phẩm hoặc mô hình doanh thu mới.
- **Chính sách và quy định:** điều khoản hợp đồng, thuế, quyền riêng tư, tiêu chuẩn hoặc quy định ngành thay đổi.
- **Đối tác và nhà cung cấp:** API, SLA, quy trình giao nhận, phương thức thanh toán hoặc khả năng cung ứng thay đổi.
- **Vận hành nội bộ:** tổ chức thay đổi vai trò, ngưỡng phê duyệt, quy trình hoặc cách phân bổ nguồn lực.

Khi khảo sát, hãy phân biệt thay đổi nhỏ về tham số với thay đổi làm biến đổi ý nghĩa hoặc cấu trúc của nghiệp vụ. Điều chỉnh một ngưỡng giá có thể đơn giản; bổ sung một mô hình đấu giá, chương trình thành viên hoặc cơ chế định giá theo thời gian có thể làm thay đổi cả tập hợp quy tắc.

### 3.2. Các khía cạnh cần xem xét

**Tần suất:** Một năm qua có bao nhiêu thay đổi nghiệp vụ có ý nghĩa? Thay đổi diễn ra theo mùa, theo quý, hàng tháng hay liên tục?

**Biên độ:** Mỗi lần thay đổi tác động đến một tham số, một nhóm quy tắc hay toàn bộ quy trình và trách nhiệm?

**Khả năng dự đoán:** Thay đổi có theo lịch hoặc kế hoạch đã biết, hay xuất hiện đột ngột do cạnh tranh, khách hàng và quy định?

**Thời gian phản hồi:** Tổ chức phải thay đổi nghiệp vụ nhanh đến mức nào để không bỏ lỡ cơ hội hoặc vi phạm cam kết?

**Phạm vi ảnh hưởng:** Một thay đổi tác động đến một nhóm nhỏ hay lan qua nhiều subdomain, đối tác và kênh?

### 3.3. Thang đánh giá tốc độ thay đổi

| Điểm | Mô tả | Dấu hiệu gợi ý |
|---|---|---|
| 1 – Rất thấp | Nghiệp vụ ổn định trong thời gian dài | Thay đổi hiếm, có thể lên kế hoạch trước nhiều tháng hoặc nhiều năm |
| 2 – Thấp | Thay đổi có lịch và phạm vi hạn chế | Một vài lần trong năm, thường là điều chỉnh nhỏ |
| 3 – Trung bình | Có thay đổi định kỳ và một số yêu cầu phát sinh | Thường theo quý hoặc tháng, đôi khi ảnh hưởng nhiều quy tắc |
| 4 – Cao | Thay đổi thường xuyên, tổ chức cần phản hồi nhanh | Theo tháng hoặc tuần, chịu tác động rõ từ thị trường hay chính sách |
| 5 – Rất cao | Nghiệp vụ biến động liên tục và khó dự đoán | Thay đổi có thể diễn ra hàng tuần hoặc hàng ngày, cần thử nghiệm và điều chỉnh nhanh |

Các mốc thời gian chỉ mang tính minh họa. Một ngành có chu kỳ thay đổi chậm có thể xem thay đổi hàng quý là nhanh; một nền tảng quảng cáo hoặc giao dịch theo thời gian thực có thể xem thay đổi hàng tuần là bình thường. Quan trọng là so sánh với nhịp vận hành và yêu cầu phản hồi của chính domain đó.

### 3.4. Dữ liệu có thể dùng để đánh giá

- Lịch sử thay đổi chính sách, bảng giá, quy tắc và quy trình trong 6–12 tháng gần nhất.
- Số lượng yêu cầu thay đổi nghiệp vụ, phân loại theo mức độ ảnh hưởng.
- Thời gian từ khi có yêu cầu đến khi nghiệp vụ mới được áp dụng.
- Số lần thay đổi khẩn cấp, ngoại lệ tạm thời hoặc phải quay lại quy tắc cũ.
- Các thay đổi từ cơ quan quản lý, đối tác và thị trường.
- Phỏng vấn chuyên gia về những thay đổi họ dự đoán trong 6–12 tháng tiếp theo.

Không phải mọi thay đổi đều được ghi nhận trong ticket. Hãy hỏi chuyên gia về các quyết định diễn ra qua email, cuộc họp, bảng tính hoặc thao tác thủ công. Nếu dữ liệu lịch sử không đầy đủ, ghi rõ mức tin cậy thay vì đưa ra điểm số có vẻ chính xác.

## 4. Đánh giá giá trị kinh doanh

Giá trị kinh doanh (business value) phản ánh mức đóng góp của subdomain vào kết quả và định hướng của tổ chức. Giá trị có thể xuất hiện dưới dạng doanh thu, lợi nhuận, trải nghiệm khách hàng, khả năng giữ chân, hiệu suất vận hành, giảm rủi ro hoặc lợi thế cạnh tranh.

Điểm quan trọng trong DDD là xác định năng lực nào giúp tổ chức tạo ra giá trị riêng mà đối thủ khó bắt chước. Một năng lực có thể cần thiết để vận hành nhưng không phải lý do khách hàng chọn doanh nghiệp. Ngược lại, một khả năng ít người nhìn thấy ở giao diện có thể tạo nên lợi thế chiến lược.

### 4.1. Các câu hỏi xác định giá trị

**Đóng góp chiến lược**

- Subdomain có trực tiếp hỗ trợ mục tiêu chiến lược hoặc lời hứa giá trị của doanh nghiệp không?
- Nó có tạo nên điều mà khách hàng nhận thấy và đánh giá cao không?
- Đối thủ có thể dễ dàng cung cấp năng lực tương đương không?
- Nếu năng lực này tốt hơn đáng kể, tổ chức có thể tạo ra lợi thế bền vững nào?

**Tác động đến khách hàng và thị trường**

- Nó ảnh hưởng đến hành trình, trải nghiệm, độ tin cậy hoặc mức độ hài lòng của khách hàng như thế nào?
- Nó có ảnh hưởng đến tỷ lệ chuyển đổi, giữ chân, tần suất mua hoặc giá trị vòng đời khách hàng không?
- Có phân khúc khách hàng hoặc thị trường nào phụ thuộc đặc biệt vào năng lực này không?

**Tác động tài chính và vận hành**

- Nó tạo doanh thu, biên lợi nhuận hoặc cơ hội kinh doanh nào?
- Nó giảm chi phí, thời gian, sai sót hoặc công sức thủ công đến đâu?
- Nếu năng lực này ngừng hoạt động, tổ chức chịu tổn thất gì?

**Rủi ro và nghĩa vụ**

- Nó có ảnh hưởng đến an toàn, tuân thủ, quyền riêng tư, gian lận hoặc uy tín không?
- Nếu thực hiện sai, hậu quả tài chính, pháp lý và vận hành lớn đến mức nào?
- Có cam kết hợp đồng hoặc nghĩa vụ với khách hàng phụ thuộc vào nó không?

**Tiềm năng tương lai**

- Đây có phải năng lực tổ chức đang đầu tư để tạo ra mô hình kinh doanh mới không?
- Giá trị hiện tại thấp nhưng có thể tăng mạnh khi mở rộng thị trường hoặc sản phẩm không?
- Có bằng chứng nào ủng hộ tiềm năng đó, hay mới chỉ là giả định?

### 4.2. Thang đánh giá giá trị kinh doanh

| Điểm | Mô tả | Dấu hiệu gợi ý |
|---|---|---|
| 1 – Rất thấp | Ít ảnh hưởng đến kết quả và không tạo khác biệt | Tác động nhỏ, dễ thay thế, chủ yếu là tiện ích nội bộ |
| 2 – Thấp | Hỗ trợ vận hành hoặc nghĩa vụ cơ bản | Cần thiết nhưng đóng góp hạn chế vào kết quả chiến lược |
| 3 – Trung bình | Có ảnh hưởng rõ đến hiệu suất hoặc trải nghiệm | Cải thiện đáng kể một chỉ số vận hành hoặc một phần hành trình khách hàng |
| 4 – Cao | Tác động lớn đến kết quả kinh doanh quan trọng | Ảnh hưởng mạnh đến doanh thu, giữ chân, chi phí, chất lượng hoặc rủi ro |
| 5 – Rất cao | Là năng lực cốt lõi tạo khác biệt hoặc quyết định thành công chiến lược | Gắn trực tiếp với lời hứa giá trị, lợi thế cạnh tranh hoặc hướng tăng trưởng then chốt |

Khi chấm điểm, nên tách **mức đóng góp hiện tại** và **tiềm năng chiến lược tương lai** nếu hai mức này khác nhau. Một năng lực mới có thể chưa tạo doanh thu đáng kể nhưng là khoản đầu tư chiến lược. Hãy ghi rõ giả định, bằng chứng và người chịu trách nhiệm xác nhận.

Không đánh đồng giá trị kinh doanh với mức độ quan trọng về tuân thủ. Một subdomain thuế có thể có hậu quả rất lớn nếu xử lý sai, nhưng cách tính thuế tiêu chuẩn thường không phải năng lực tạo khác biệt cạnh tranh. Giá trị, rủi ro và tính khác biệt là những góc nhìn liên quan nhưng cần được ghi nhận riêng.

## 5. So sánh ba trục đánh giá

| Trục | Trọng tâm | Bằng chứng nên tìm | Câu hỏi quyết định |
|---|---|---|---|
| Độ phức tạp | Quy tắc, ngoại lệ, trạng thái, phụ thuộc và tri thức nghiệp vụ | Bảng quy tắc, ví dụ xử lý, sơ đồ luồng, phỏng vấn chuyên gia | Cần đầu tư bao nhiêu công sức để hiểu và mô hình hóa đúng? |
| Tốc độ thay đổi | Tần suất, biên độ, tính khó dự đoán và thời gian phản hồi | Lịch sử thay đổi, yêu cầu nghiệp vụ, thay đổi chính sách và thị trường | Năng lực cần thích nghi nhanh đến mức nào? |
| Giá trị kinh doanh | Đóng góp chiến lược, khách hàng, tài chính, vận hành và rủi ro | KPI, chiến lược, phản hồi khách hàng, phân tích doanh thu và chi phí | Vì sao tổ chức nên đầu tư hoặc bảo vệ năng lực này? |

Ba trục trả lời ba loại quyết định khác nhau:

- Độ phức tạp cho biết cần bao nhiêu hiểu biết chuyên môn và chiều sâu mô hình.
- Tốc độ thay đổi cho biết cần khả năng thử nghiệm, cấu hình, mở rộng và phản hồi nhanh đến đâu.
- Giá trị kinh doanh cho biết mức ưu tiên và loại đầu tư có ý nghĩa với chiến lược.

Một điểm số chỉ có ích khi đi kèm mô tả và bằng chứng. Không nên cộng ba điểm thành một tổng duy nhất rồi dùng tổng đó để tự động kết luận subdomain là core, supporting hay generic. Hai subdomain có cùng tổng điểm có thể cần chiến lược hoàn toàn khác nhau.

## 6. Quy trình đánh giá trong buổi khám phá domain

### Bước 1: Xác định subdomain và ranh giới

Viết tên, mục đích, vấn đề nghiệp vụ, người liên quan, đầu vào, kết quả và phạm vi không bao gồm. Dùng ngôn ngữ nghiệp vụ để mô tả. Nếu chưa thống nhất được ranh giới, hãy làm rõ trước khi đánh giá.

### Bước 2: Xác định chuyên gia và bên liên quan

Mời người trực tiếp thực hiện công việc, người chịu trách nhiệm chính sách, người ra quyết định, người sử dụng kết quả và người hiểu mục tiêu chiến lược. Không chỉ phỏng vấn quản lý vì họ có thể không nắm các ngoại lệ trong vận hành hằng ngày.

### Bước 3: Thu thập bằng chứng

Kết hợp phỏng vấn theo tình huống cụ thể, quan sát công việc, hồ sơ giao dịch, dữ liệu vận hành, tài liệu chính sách và lịch sử thay đổi. Với mỗi nhận định, ghi rõ nguồn và thời điểm.

### Bước 4: Đánh giá độ phức tạp

Liệt kê các quy tắc quan trọng, nhánh xử lý, ngoại lệ, trạng thái, vai trò và phụ thuộc. Chọn một số trường hợp bình thường và biên để kiểm tra xem mô hình có giải thích được quyết định thực tế không.

### Bước 5: Đánh giá tốc độ thay đổi

Xem lại lịch sử thay đổi nghiệp vụ trong một khoảng thời gian đủ đại diện. Phân biệt thay đổi tham số với thay đổi chính sách hoặc cấu trúc. Hỏi chuyên gia về những thay đổi sắp tới và thời gian tổ chức cần để phản hồi.

### Bước 6: Đánh giá giá trị kinh doanh

Liên hệ subdomain với mục tiêu chiến lược, hành trình khách hàng, doanh thu, chi phí, rủi ro và năng lực khác biệt. Dùng số liệu khi có thể; nếu chưa có, ghi nhận nhận định và giả định cần kiểm chứng.

### Bước 7: Thảo luận điểm số và mức tin cậy

Để các vai trò chấm điểm độc lập trước khi thảo luận. Khi điểm khác nhau, yêu cầu mỗi người nêu ví dụ và bằng chứng. Giữ lại bất đồng nếu chưa đủ dữ liệu để kết luận.

### Bước 8: Xác định quyết định tiếp theo

Chọn cách đầu tư phù hợp: khám phá sâu và xây mô hình riêng, chuẩn hóa quy trình, cải thiện khả năng thay đổi, tích hợp sản phẩm có sẵn hoặc tiếp tục thu thập dữ liệu. Ghi rõ người chịu trách nhiệm và thời điểm đánh giá lại.

## 7. Ví dụ: đánh giá các subdomain của một sàn thương mại điện tử

Giả sử một sàn thương mại điện tử cạnh tranh bằng khả năng tạo chương trình khuyến mãi linh hoạt và cá nhân hóa trải nghiệm mua sắm. Nhóm đang xem xét bốn subdomain. Các điểm sau chỉ là ví dụ minh họa cho bối cảnh giả định, không phải chuẩn chung cho ngành.

| Subdomain | Phức tạp | Tốc độ thay đổi | Giá trị kinh doanh | Nhận định ban đầu |
|---|---:|---:|---:|---|
| Giá và khuyến mãi | 5 | 5 | 5 | Quy tắc chồng lấn, nhiều điều kiện theo khách hàng và chiến dịch; tạo khác biệt trực tiếp |
| Đồng bộ tồn kho | 4 | 3 | 3 | Có nhiều trạng thái và tình huống lệch dữ liệu; quan trọng cho vận hành nhưng chưa phải lợi thế riêng |
| Tính thuế | 4 | 4 | 2 | Quy tắc theo khu vực và thời điểm có thể phức tạp, thay đổi theo quy định; thường có giải pháp chuyên dụng phổ biến |
| Tính lương | 2 | 2 | 1 | Quy trình tương đối chuẩn hóa và ít ảnh hưởng trực tiếp đến đề xuất giá trị cho khách hàng |

### 7.1. Giá và khuyến mãi

Một chiến dịch có thể áp dụng đồng thời mã giảm giá, ưu đãi theo hạng thành viên, giảm theo số lượng, trợ giá từ nhà bán hàng và điều kiện thanh toán. Hệ thống cần xác định ưu tiên, khả năng cộng dồn, giới hạn ngân sách, thời gian hiệu lực, nhóm khách hàng và cách xử lý khi chiến dịch bị hủy.

Độ phức tạp cao vì các quy tắc tương tác với nhau. Tốc độ thay đổi cao vì đội kinh doanh thử nghiệm chiến dịch liên tục và phản ứng với đối thủ. Giá trị cao vì khả năng tạo ưu đãi phù hợp là một phần của chiến lược cạnh tranh giả định. Subdomain này là ứng viên **core domain**; tổ chức nên đầu tư chuyên gia nghiệp vụ, khám phá sâu và mô hình hóa riêng.

### 7.2. Đồng bộ tồn kho

Tồn kho có thể thay đổi do đơn hàng, hủy đơn, hàng trả lại, điều chỉnh kiểm kê và cập nhật từ nhà bán hàng. Các trạng thái như khả dụng, đã giữ chỗ, đang giao và lỗi đồng bộ cần được phân biệt rõ.

Độ phức tạp khá cao vì có nhiều nguồn dữ liệu và sự kiện. Tốc độ thay đổi trung bình trong giả định này. Năng lực rất cần thiết để tránh bán vượt tồn và bảo đảm vận hành, nhưng cách đồng bộ cơ bản có thể không tạo ra khác biệt riêng. Đây là ứng viên **supporting subdomain**. Nếu doanh nghiệp xây dựng được năng lực cung ứng tức thời vượt trội so với đối thủ, đánh giá giá trị có thể tăng và phân loại cần được xem xét lại.

### 7.3. Tính thuế

Thuế phụ thuộc vào khu vực, loại hàng hóa, loại giao dịch và thời điểm hiệu lực. Quy tắc có thể phức tạp và thay đổi thường xuyên khi quy định được cập nhật. Tuy vậy, nhiều doanh nghiệp có thể dùng dịch vụ tính thuế chuyên dụng đã được duy trì bởi nhà cung cấp có chuyên môn.

Subdomain này có thể có độ phức tạp và tốc độ thay đổi cao nhưng không nhất thiết tạo lợi thế cạnh tranh riêng. Trong giả định này, nó là ứng viên **generic subdomain**: cần kiểm soát tính chính xác, khả năng tuân thủ và tích hợp tốt, nhưng không cần tự phát triển toàn bộ năng lực tính thuế nếu giải pháp chung đáp ứng yêu cầu.

### 7.4. Tính lương

Tính lương thường tuân theo quy trình và quy định tương đối phổ biến, dù vẫn cần xử lý phụ cấp, khấu trừ và quy định lao động. Nếu đây không phải năng lực tạo khác biệt của sàn, tổ chức có thể sử dụng sản phẩm nhân sự hoặc dịch vụ tính lương phù hợp. Đây là ứng viên **generic subdomain** trong bối cảnh ví dụ.

### 7.5. Bài học từ ví dụ

Tính thuế cho thấy một subdomain có thể phức tạp và thay đổi nhanh nhưng vẫn là generic. Đồng bộ tồn kho cho thấy năng lực quan trọng với vận hành chưa chắc là core. Giá và khuyến mãi cho thấy khi nghiệp vụ trực tiếp tạo nên lợi thế cạnh tranh, tổ chức có lý do đầu tư vào hiểu biết và mô hình riêng.

Kết luận có thể khác nếu chiến lược kinh doanh khác. Với một doanh nghiệp cạnh tranh bằng giao hàng trong hai giờ, điều phối tồn kho và giao nhận có thể trở thành core domain. Phân loại phải xuất phát từ chiến lược và năng lực thực tế của từng tổ chức.

## 8. Dùng ba trục để định hướng đầu tư

Không có một công thức duy nhất phù hợp cho mọi tổ chức. Có thể dùng các kết hợp dưới đây như gợi ý để thảo luận:

| Độ phức tạp | Tốc độ thay đổi | Giá trị kinh doanh | Hướng xem xét |
|---|---|---|---|
| Cao | Cao | Cao | Đầu tư chuyên gia, khám phá liên tục, mô hình miền rõ và khả năng thích nghi nhanh |
| Cao | Thấp | Cao | Đầu tư hiểu biết sâu, kiểm soát quy tắc và tính đúng đắn; thay đổi có thể cần quy trình phê duyệt chặt |
| Thấp | Cao | Cao | Ưu tiên khả năng thử nghiệm, cấu hình và triển khai thay đổi nhanh; tránh tạo kiến trúc cứng |
| Cao | Cao | Thấp | Xem xét đơn giản hóa, chuẩn hóa, dùng sản phẩm chuyên dụng hoặc chuyển giao cho nhà cung cấp |
| Thấp | Thấp | Thấp | Giữ giải pháp đơn giản, tự động hóa vừa đủ hoặc dùng năng lực dùng chung |
| Trung bình | Trung bình | Trung bình | Cân bằng giữa chi phí, mức kiểm soát và khả năng mở rộng; đánh giá lại khi chiến lược đổi |

Có thể hình dung cách dùng kết quả:

~~~mermaid
flowchart TD
    A["Xác định subdomain"] --> B["Thu thập bằng chứng nghiệp vụ"]
    B --> C["Đánh giá độ phức tạp"]
    B --> D["Đánh giá tốc độ thay đổi"]
    B --> E["Đánh giá giá trị kinh doanh"]
    C --> F["Thảo luận hồ sơ đánh giá"]
    D --> F
    E --> F
    F --> G{"Có tạo khác biệt chiến lược?"}
    G -->|Có| H["Xem xét Core Domain"]
    G -->|Không| I{"Là năng lực hỗ trợ riêng?"}
    I -->|Có| J["Xem xét Supporting Subdomain"]
    I -->|Không, bài toán phổ biến| K["Xem xét Generic Subdomain"]
    H --> L["Chọn mức đầu tư và cách phát triển"]
    J --> L
    K --> L
    L --> M["Theo dõi thay đổi và đánh giá lại"]
~~~

Độ phức tạp và tốc độ thay đổi chủ yếu giúp xác định cách thiết kế, cách tổ chức chuyên gia và mức độ linh hoạt cần có. Giá trị chiến lược và tính khác biệt giúp định hướng phân loại core, supporting và generic. Không nên để một ngưỡng điểm tự động quyết định phân loại.

## 9. Từ đánh giá đến phân loại Core, Supporting và Generic

Trong strategic design của DDD, ba loại subdomain thường được dùng để xác định nơi tổ chức cần tập trung năng lực.

### Core Subdomain

Core subdomain chứa năng lực nghiệp vụ tạo ra khác biệt cạnh tranh hoặc thực hiện lời hứa giá trị quan trọng của tổ chức. Đây là nơi tổ chức thường cần hiểu sâu, có chuyên gia giỏi và liên tục cải thiện.

Đặc điểm thường gặp:

- Gắn trực tiếp với chiến lược và lý do khách hàng chọn doanh nghiệp.
- Có các quy tắc hoặc quyết định phản ánh tri thức riêng của tổ chức.
- Có thể cần thay đổi để đáp ứng cạnh tranh và thử nghiệm mô hình kinh doanh.
- Đáng để đầu tư vào mô hình miền, ngôn ngữ chung, thiết kế và kiểm thử chuyên sâu.

Core không có nghĩa là phần mềm phải phức tạp nhất hoặc có nhiều mã nhất. Một thuật toán đơn giản nhưng tạo ra trải nghiệm độc đáo vẫn có thể thuộc core. Ngược lại, một bài toán cực kỳ phức tạp nhưng đã được chuẩn hóa trong ngành có thể không phải core.

### Supporting Subdomain

Supporting subdomain cung cấp năng lực cần thiết để core hoạt động, nhưng bản thân nó không phải nguồn tạo khác biệt chính. Năng lực này có thể mang đặc thù tổ chức nên sản phẩm phổ thông không đáp ứng hoàn toàn, song mức đầu tư chiến lược thường thấp hơn core.

Đặc điểm thường gặp:

- Cần thiết cho quy trình hoặc dịch vụ tổng thể.
- Có thể chứa quy tắc riêng, nhưng không phải lợi thế cạnh tranh chủ đạo.
- Có thể phát triển giải pháp vừa đủ, đơn giản hóa quy trình hoặc dùng thành phần dùng chung.
- Nên tránh đầu tư quá mức vào mô hình và kiến trúc nếu giá trị mang lại không tương xứng.

### Generic Subdomain

Generic subdomain giải quyết bài toán phổ biến mà nhiều tổ chức gặp phải, thường đã có sản phẩm, dịch vụ hoặc giải pháp tiêu chuẩn trên thị trường.

Đặc điểm thường gặp:

- Không phải năng lực làm khách hàng chọn riêng doanh nghiệp.
- Quy tắc thường được chuẩn hóa bởi ngành, luật lệ hoặc thông lệ.
- Có thể mua, thuê, dùng thư viện hoặc tích hợp dịch vụ chuyên dụng.
- Cần tập trung vào lựa chọn nhà cung cấp, cấu hình, tích hợp, bảo mật và kiểm soát dữ liệu.

Generic không có nghĩa là không quan trọng. Tính lương, thuế, xác thực danh tính hoặc thanh toán có thể ảnh hưởng lớn đến hoạt động và rủi ro. Phân loại generic chỉ nói rằng tổ chức thường không cần tự tạo ra lợi thế cạnh tranh bằng cách phát minh lại toàn bộ bài toán đó.

### 9.1. Không suy ra phân loại chỉ từ điểm số

| Nhận định | Kết luận cần tránh | Cách xem xét đúng |
|---|---|---|
| Độ phức tạp rất cao | Chắc chắn là Core | Xác định độ phức tạp có xuất phát từ tri thức riêng hay từ một bài toán phổ biến |
| Thay đổi rất thường xuyên | Chắc chắn là Core | Kiểm tra thay đổi đến từ chiến lược cạnh tranh hay chỉ từ quy định bên ngoài |
| Giá trị vận hành cao | Chắc chắn là Core | Phân biệt năng lực thiết yếu với năng lực tạo khác biệt |
| Có thể mua sản phẩm | Chắc chắn là Generic | Kiểm tra sản phẩm có thực sự đáp ứng chính sách, trải nghiệm và ràng buộc của tổ chức không |
| Ít phức tạp hiện tại | Không cần quan tâm | Xem xét vai trò chiến lược và tiềm năng thay đổi trong tương lai |

Phân loại là một quyết định chiến lược cần được chuyên gia nghiệp vụ, chủ sở hữu sản phẩm và kiến trúc sư cùng thảo luận. Khi chiến lược, thị trường hoặc năng lực tổ chức thay đổi, phân loại cũng có thể thay đổi.

## 10. Mối quan hệ với Bounded Context và kiến trúc

Subdomain mô tả cách chia nhỏ vấn đề nghiệp vụ. Bounded Context xác định ranh giới mà trong đó một mô hình và ngôn ngữ chung có ý nghĩa nhất quán. Hai khái niệm liên quan nhưng không đồng nhất và không bắt buộc ánh xạ một-một.

Đánh giá ba trục có thể cung cấp manh mối cho thiết kế:

- Một subdomain có nhiều chính sách, thuật ngữ và quyết định riêng có thể cần bounded context với mô hình rõ ràng.
- Một subdomain thay đổi nhanh có thể cần ranh giới giúp hạn chế ảnh hưởng của thay đổi sang các mô hình khác.
- Một core subdomain có thể cần đội ngũ sở hữu tri thức miền và phát triển mô hình chuyên sâu.
- Một generic subdomain có thể được tích hợp qua một ranh giới rõ để bảo vệ mô hình nội bộ khỏi cách biểu diễn của sản phẩm bên ngoài.
- Một supporting subdomain có thể được tổ chức thành mô hình đơn giản, miễn là ranh giới và trách nhiệm được hiểu rõ.

Không nên tự động tạo một bounded context cho mỗi subdomain hoặc một microservice cho mỗi bounded context. Ranh giới cần phản ánh ngôn ngữ, mô hình, quyền sở hữu và nhu cầu thay đổi. Kiến trúc triển khai là quyết định tiếp theo, phụ thuộc thêm vào yêu cầu vận hành, dữ liệu và năng lực đội ngũ.

## 11. Mẫu ghi nhận kết quả đánh giá

Mỗi subdomain nên có một hồ sơ đủ ngắn để thảo luận và đủ rõ để người khác kiểm tra lại:

| Trường | Nội dung |
|---|---|
| Tên subdomain | Tên nghiệp vụ được thống nhất |
| Mục đích | Vấn đề hoặc năng lực nghiệp vụ được giải quyết |
| Ranh giới | Phạm vi bao gồm, không bao gồm và các bên liên quan |
| Độ phức tạp | Điểm 1–5, dấu hiệu, ví dụ và bằng chứng |
| Tốc độ thay đổi | Điểm 1–5, giai đoạn quan sát và nguồn thay đổi |
| Giá trị kinh doanh | Điểm 1–5, kết quả chiến lược và chỉ số liên quan |
| Mức tin cậy | Cao, trung bình hoặc thấp; nêu phần còn thiếu dữ liệu |
| Phân loại đề xuất | Core, Supporting, Generic hoặc đang chờ xác minh |
| Quyết định đầu tư | Xây dựng, mua, tích hợp, đơn giản hóa hoặc tiếp tục khám phá |
| Người xác nhận | Chuyên gia nghiệp vụ và người chịu trách nhiệm |
| Ngày xem xét lại | Thời điểm hoặc sự kiện kích hoạt đánh giá mới |

Ví dụ về một bản ghi:

~~~text
Subdomain: Giá và khuyến mãi
Mục đích: Xác định giá bán cuối cùng và ưu đãi hợp lệ cho từng đơn hàng.
Ranh giới: Bao gồm quy tắc chiến dịch, điều kiện áp dụng và ưu tiên ưu đãi;
không bao gồm xử lý thanh toán.

Độ phức tạp: 5/5
Bằng chứng: Nhiều quy tắc có thể cộng dồn hoặc loại trừ lẫn nhau;
cần xét phân khúc khách hàng, thời gian và ngân sách chiến dịch.

Tốc độ thay đổi: 5/5
Bằng chứng: Đội kinh doanh triển khai và điều chỉnh chiến dịch liên tục;
cạnh tranh tạo yêu cầu phản hồi nhanh.

Giá trị kinh doanh: 5/5
Bằng chứng: Khuyến mãi cá nhân hóa là một phần của chiến lược thu hút
và giữ chân khách hàng.

Phân loại đề xuất: Core Subdomain
Quyết định đầu tư: Duy trì chuyên gia miền, khám phá liên tục và mô hình
riêng; theo dõi tác động của thay đổi đến các context liên quan.
Mức tin cậy: Trung bình; cần xác nhận thêm bằng dữ liệu giữ chân và biên lợi nhuận.
Người xác nhận: Chủ nghiệp vụ giá và khuyến mãi.
Xem xét lại: Khi thay đổi chiến lược giá hoặc mô hình doanh thu.
~~~

## 12. Những sai lầm thường gặp

**Đánh giá theo cảm giác mà không có bằng chứng.** Một người có kinh nghiệm có thể nhận định đúng, nhưng cần ví dụ, hồ sơ và dữ liệu để cả nhóm hiểu vì sao. Hãy ghi rõ nhận định nào đã xác minh và nhận định nào còn là giả định.

**Đồng nhất phức tạp nghiệp vụ với phức tạp kỹ thuật.** Hệ thống nhiều bảng, tích hợp hoặc mã cũ không tự chứng minh subdomain phức tạp về nghiệp vụ. Phân tích quy tắc và quyết định trước.

**Đếm số thay đổi phần mềm thay cho thay đổi nghiệp vụ.** Tần suất phát hành không phản ánh tần suất chính sách, nhu cầu hoặc quy tắc kinh doanh thay đổi. Hãy dùng lịch sử thay đổi nghiệp vụ.

**Xem mức độ quan trọng là lợi thế cạnh tranh.** Một năng lực có thể rất quan trọng vì nếu hỏng sẽ gây thiệt hại, nhưng vẫn là bài toán tiêu chuẩn có thể mua. Hãy phân biệt mức thiết yếu, rủi ro và tính khác biệt.

**Cộng điểm thành một con số tổng.** Tổng điểm che khuất bản chất khác nhau của ba trục. Giữ hồ sơ ba chiều và dùng nó để thảo luận quyết định đầu tư.

**Chấm điểm khi ranh giới subdomain chưa rõ.** Phạm vi không thống nhất khiến các điểm số không thể so sánh. Xác định mục đích, đầu vào, đầu ra và trách nhiệm trước.

**Dùng một thang điểm cho mọi ngành mà không hiệu chỉnh.** Nhịp thay đổi và mức phức tạp bình thường của ngân hàng, thương mại điện tử và sản xuất khác nhau. Thang điểm cần có mốc tham chiếu phù hợp.

**Coi phân loại là vĩnh viễn.** Một supporting subdomain có thể trở thành core khi chiến lược đổi; một core có thể trở nên phổ thông khi thị trường chuẩn hóa. Hãy đánh giá lại theo sự kiện và chu kỳ phù hợp.

**Mua giải pháp generic mà không kiểm tra ranh giới.** Sản phẩm phổ biến vẫn có thể áp đặt mô hình dữ liệu hoặc thuật ngữ không phù hợp. Cần xác định cách tích hợp, chuyển đổi ngôn ngữ và bảo vệ mô hình nội bộ.

## 13. Cách tổ chức một buổi đánh giá ngắn

Với một subdomain đã có phạm vi tương đối rõ, có thể tổ chức buổi làm việc theo trình tự:

1. Chủ nghiệp vụ mô tả mục đích và kết quả quan trọng của subdomain.
2. Người trực tiếp vận hành kể lại một trường hợp thông thường và một trường hợp ngoại lệ.
3. Cả nhóm liệt kê các quy tắc, phụ thuộc, trạng thái và điểm cần chuyên gia quyết định.
4. Cùng xem lịch sử thay đổi nghiệp vụ và các tác nhân tạo thay đổi.
5. Kết nối năng lực với chiến lược, hành trình khách hàng, doanh thu, chi phí và rủi ro.
6. Mỗi người chấm độc lập ba trục, sau đó giải thích khác biệt bằng bằng chứng.
7. Đề xuất phân loại và quyết định đầu tư; ghi rõ phần còn chưa chắc chắn.

Một số câu hỏi hữu ích:

- “Nếu một người mới tiếp nhận nghiệp vụ, họ cần học những quy tắc và ngoại lệ nào trước khi tự xử lý được?”
- “Trường hợp nào thường khiến các nhóm bất đồng hoặc phải xin ý kiến chuyên gia?”
- “Trong năm vừa qua, thay đổi nào buộc tổ chức phải điều chỉnh cách vận hành?”
- “Nếu đối thủ làm năng lực này tốt hơn, khách hàng có nhận thấy và thay đổi lựa chọn không?”
- “Nếu không tự phát triển năng lực này, có sản phẩm hoặc dịch vụ nào đáp ứng được yêu cầu?”
- “Điều gì có thể khiến cách đánh giá hôm nay không còn đúng trong sáu tháng tới?”

## 14. Tiêu chí tự kiểm tra

Trước khi dùng kết quả để quyết định chiến lược hoặc kiến trúc, hãy kiểm tra:

- Ranh giới và mục đích của subdomain đã được các bên thống nhất chưa?
- Điểm phức tạp dựa trên quy tắc, ngoại lệ, trạng thái và phụ thuộc nghiệp vụ chưa?
- Đã phân biệt độ phức tạp nghiệp vụ với độ phức tạp kỹ thuật chưa?
- Tốc độ thay đổi được đánh giá bằng lịch sử nghiệp vụ và nguồn thay đổi chưa?
- Đã xem xét cả tần suất, biên độ và khả năng dự đoán của thay đổi chưa?
- Giá trị kinh doanh có liên hệ với chiến lược, khách hàng, kết quả tài chính hoặc rủi ro không?
- Đã phân biệt năng lực thiết yếu với năng lực tạo khác biệt cạnh tranh chưa?
- Mỗi điểm số có ví dụ, nguồn và mức tin cậy không?
- Phân loại Core, Supporting hoặc Generic có được giải thích bằng bối cảnh chiến lược không?
- Quyết định đầu tư có phù hợp với cả ba trục không?
- Đã xác định thời điểm hoặc sự kiện để đánh giá lại chưa?

Kết quả đánh giá không phải một nhãn cố định gắn vào subdomain. Nó là cách diễn đạt có căn cứ về mức độ khó của bài toán, nhịp biến động và đóng góp của năng lực đó. Khi hiểu ba khía cạnh này riêng biệt, tổ chức có thể tập trung chuyên gia và nỗ lực mô hình hóa vào nơi tạo ra lợi thế, đồng thời giữ các năng lực hỗ trợ và phổ biến ở mức đầu tư phù hợp.
