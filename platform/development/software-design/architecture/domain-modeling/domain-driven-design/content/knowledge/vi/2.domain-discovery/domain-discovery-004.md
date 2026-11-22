# Phân biệt hoạt động hiện tại với chính sách và mục tiêu mong muốn

Trong Domain-Driven Design (DDD), khám phá nghiệp vụ bắt đầu bằng việc hiểu cách tổ chức đang vận hành, cách mọi người đưa ra quyết định và kết quả mà họ muốn đạt được. Ba nội dung này có liên quan nhưng không đồng nghĩa:

- **Hoạt động hiện tại** mô tả những gì đang thực sự diễn ra trong công việc.
- **Chính sách** mô tả nguyên tắc hoặc tiêu chí chi phối cách đưa ra quyết định.
- **Mục tiêu mong muốn** mô tả kết quả cần đạt trong tương lai.

Nếu trộn lẫn ba nội dung, đội phát triển dễ biến một thói quen tạm thời thành quy tắc nghiệp vụ, hiểu nhầm một quy định chưa được thực thi thành hành vi thực tế, hoặc xây dựng phần mềm để tự động hóa quy trình hiện tại dù quy trình đó đang có vấn đề. Phân biệt chúng giúp đội phát triển và chuyên gia nghiệp vụ thống nhất vấn đề cần giải quyết trước khi bàn đến giải pháp.

## 1. Ba góc nhìn cần tách biệt

### Hoạt động hiện tại: điều gì đang thực sự xảy ra?

Hoạt động hiện tại (current activity hoặc as-is) là mô tả dựa trên bằng chứng về cách công việc được thực hiện ở thời điểm khảo sát. Nó bao gồm người tham gia, sự kiện khởi đầu, trình tự công việc, thông tin được sử dụng, các lần bàn giao, kết quả, ngoại lệ và cách xử lý khi có sự cố.

Khi tìm hiểu hoạt động hiện tại, hãy ghi nhận cả quy trình chính thức lẫn cách nhân viên thực sự hoàn thành công việc. Một quy trình trên tài liệu có thể nói rằng yêu cầu được xử lý tự động, trong khi nhân viên vẫn phải tải bảng tính về, gọi điện xác minh và nhập lại dữ liệu. Những thao tác thủ công đó là một phần của thực tế cần được khám phá.

Hoạt động hiện tại trả lời các câu hỏi:

- Ai thực hiện công việc và ai chịu trách nhiệm cho kết quả?
- Điều gì khiến công việc bắt đầu?
- Người thực hiện nhận thông tin từ đâu và tạo ra kết quả gì?
- Các bước diễn ra theo thứ tự nào? Có bước nào diễn ra song song không?
- Công việc được chuyển giữa những vai trò hoặc bộ phận nào?
- Trường hợp bình thường và trường hợp ngoại lệ khác nhau ra sao?
- Có thao tác thủ công, bảng tính, tin nhắn hoặc hệ thống phụ nào đang được dùng không?
- Có bao nhiêu trường hợp thất bại, bị trả lại hoặc phải xử lý lại?

Một mô tả tốt về hiện trạng có thể được kiểm chứng bằng một trường hợp cụ thể, quan sát tại nơi làm việc, hồ sơ giao dịch, nhật ký hệ thống hoặc số liệu vận hành. Câu nói như “bộ phận luôn kiểm tra trong ngày” vẫn chỉ là giả thuyết cho đến khi có dữ liệu hoặc ví dụ xác nhận.

### Chính sách: quyết định được định hướng như thế nào?

Chính sách (policy) là nguyên tắc, tiêu chí hoặc định hướng mà tổ chức sử dụng để quyết định nên làm gì trong một tình huống. Chính sách có thể được ghi trong quy định, hợp đồng, hướng dẫn nội bộ hoặc chỉ tồn tại dưới dạng kinh nghiệm truyền miệng.

Chính sách thường xuất hiện tại một điểm cần lựa chọn: chấp nhận hay từ chối, ưu tiên trường hợp nào, ai được quyền phê duyệt, mức giá nào được áp dụng, hoặc khi nào cần chuyển cấp xử lý. Một chính sách có thể được diễn đạt ở mức định hướng, sau đó cụ thể hóa thành các quy tắc nghiệp vụ có thể kiểm tra.

Ví dụ:

- Định hướng: ưu tiên khách hàng bị gián đoạn dịch vụ lâu hơn.
- Quy tắc cụ thể: yêu cầu có thời gian gián đoạn trên bốn giờ được xếp vào nhóm ưu tiên cao.
- Quyền quyết định: trưởng ca được phép phê duyệt khoản bồi hoàn dưới một ngưỡng đã quy định.

Khi khảo sát, cần phân biệt **chính sách được công bố**, **chính sách đang được áp dụng** và **cách nhân viên thực sự quyết định**. Ba điều này có thể không trùng nhau. Nhân viên có thể chưa biết quy định mới, hệ thống có thể chưa hỗ trợ quy định, hoặc người quản lý có thể cho phép ngoại lệ. Không nên kết luận một chính sách đang có hiệu lực chỉ vì nó xuất hiện trong tài liệu; cũng không nên kết luận một hành vi lặp lại là chính sách nếu chưa xác minh căn cứ và thẩm quyền.

Chính sách trả lời các câu hỏi:

- Tiêu chí nào được dùng để ra quyết định?
- Quy tắc này áp dụng cho đối tượng và tình huống nào?
- Ai có thẩm quyền quyết định hoặc cho phép ngoại lệ?
- Khi nhiều tiêu chí xung đột, tiêu chí nào được ưu tiên?
- Chính sách xuất phát từ luật, hợp đồng, cam kết với khách hàng hay lựa chọn kinh doanh?
- Chính sách có hiệu lực từ khi nào, do ai quản lý và được xem xét lại ra sao?
- Có ví dụ nào cho thấy chính sách được áp dụng khác nhau giữa các nhóm hoặc kênh không?

### Mục tiêu mong muốn: tổ chức muốn đạt kết quả gì?

Mục tiêu mong muốn (desired outcome hoặc to-be outcome) mô tả trạng thái hoặc kết quả mà các bên liên quan muốn đạt được. Mục tiêu giải thích vì sao cần thay đổi. Nó có thể liên quan đến khách hàng, doanh thu, chi phí, chất lượng, tốc độ, rủi ro, khả năng tuân thủ hoặc trải nghiệm của nhân viên.

Mục tiêu nên được diễn đạt bằng kết quả có thể quan sát hoặc đo lường. “Xây dựng màn hình tự phục vụ” là một ý tưởng giải pháp. “Khách hàng có thể gửi yêu cầu hoàn trả mà không cần gọi tổng đài, và nhận được quyết định trong vòng một ngày làm việc” mô tả kết quả mong muốn rõ hơn.

Một mục tiêu hữu ích thường nêu:

- **Đối tượng hưởng lợi:** khách hàng, nhân viên, đối tác hay tổ chức.
- **Kết quả cần cải thiện:** thời gian xử lý, tỷ lệ lỗi, chi phí, mức độ hài lòng hoặc chỉ số khác.
- **Mức hiện tại và mức đích:** có số liệu nền để biết khoảng cách cần thu hẹp.
- **Phạm vi và thời hạn:** nhóm nghiệp vụ, kênh, loại giao dịch và thời điểm cần đạt.
- **Ràng buộc hoặc giới hạn:** chất lượng, an toàn, tuân thủ, ngân sách và rủi ro không được đánh đổi.

Không phải mục tiêu nào cũng có thể định lượng ngay từ đầu. Khi chưa có dữ liệu, hãy ghi rõ giả định và xác định cách thu thập số liệu nền. Tránh tự đặt con số để làm mục tiêu trông có vẻ cụ thể.

## 2. So sánh ba nội dung

| Góc nhìn | Trọng tâm | Câu hỏi chính | Bằng chứng thường dùng |
|---|---|---|---|
| Hoạt động hiện tại | Hành vi và luồng công việc đang diễn ra | Chuyện gì thực sự xảy ra? | Quan sát, hồ sơ, nhật ký, phỏng vấn theo trường hợp cụ thể |
| Chính sách | Nguyên tắc và tiêu chí ra quyết định | Vì sao quyết định đó được đưa ra? | Quy định, hợp đồng, bảng quyết định, ví dụ phê duyệt và từ chối |
| Mục tiêu mong muốn | Kết quả cần đạt trong tương lai | Thành công sẽ trông như thế nào? | Chỉ số mục tiêu, nhu cầu của bên liên quan, cam kết và tiêu chí nghiệm thu |

Có thể ghi nhớ bằng ba câu hỏi: **đang làm gì**, **dựa vào đâu để quyết định**, và **muốn đạt điều gì**. Một phát biểu có thể chứa cả ba nội dung; khi đó hãy tách nó thành các phát biểu nhỏ để mỗi phát biểu có thể được xác minh riêng.

## 3. Ví dụ: khám phá nghiệp vụ hoàn trả đơn hàng

Giả sử một cửa hàng trực tuyến muốn cải thiện việc tiếp nhận và xử lý yêu cầu hoàn trả. Trong buổi trao đổi, các bên nói:

> Khách hàng gọi tổng đài trong vòng bảy ngày, nhân viên kiểm tra đơn hàng rồi gửi yêu cầu cho kho. Chúng ta muốn hoàn tất tự động trong ngày.

Phát biểu này có vẻ đơn giản nhưng chứa nhiều loại thông tin. Hãy phân tách và xác minh từng phần.

### 3.1. Ghi nhận hoạt động đang diễn ra

Quan sát một số yêu cầu gần đây cho thấy:

1. Khách hàng gọi tổng đài hoặc gửi biểu mẫu trên website.
2. Nhân viên hỗ trợ tìm đơn hàng bằng mã đơn.
3. Nhân viên kiểm tra lý do hoàn trả và ghi chú tình trạng sản phẩm do khách mô tả.
4. Nếu chưa rõ tình trạng đơn hàng, nhân viên nhắn cho kho để xác minh.
5. Nhân viên nhập kết quả vào một bảng theo dõi chung.
6. Kho nhận hàng, kiểm tra sản phẩm và phản hồi kết quả.
7. Nhân viên hỗ trợ thông báo kết quả cho khách hàng và chuyển yêu cầu hoàn tiền sang bộ phận liên quan.

Đây là mô tả hiện trạng, chưa phải kết luận rằng mọi bước đều cần thiết. Cần tiếp tục khảo sát các trường hợp khác: khách nhận sai sản phẩm, sản phẩm bị hỏng khi giao, đơn hàng đã thanh toán một phần, khách không có mã đơn hoặc kho chưa xác nhận được tình trạng hàng.

### 3.2. Tìm chính sách đứng sau các quyết định

Trong luồng trên có một số điểm cần ra quyết định:

- Yêu cầu có đủ điều kiện hoàn trả không?
- Trường hợp sản phẩm bị hỏng được xử lý khác với trường hợp khách đổi ý như thế nào?
- Ai được quyền chấp nhận yêu cầu khi thông tin chưa đầy đủ?
- Khi nào phải chờ kho kiểm tra?
- Ai được quyền phê duyệt ngoại lệ?

Qua trao đổi và đối chiếu tài liệu, đội có thể phát hiện các quy tắc hiện hành như:

- Yêu cầu thông thường được tiếp nhận trong vòng bảy ngày kể từ khi khách nhận hàng.
- Sản phẩm đã qua sử dụng không đủ điều kiện theo chính sách hoàn trả thông thường.
- Sản phẩm giao sai hoặc bị hỏng cần được xem xét theo chính sách xử lý lỗi giao hàng.
- Nhân viên hỗ trợ chỉ được phê duyệt trực tiếp các trường hợp đáp ứng đầy đủ điều kiện; trường hợp ngoại lệ phải chuyển quản lý.

Đây là các quy tắc cần được xác nhận với người có thẩm quyền và bằng chứng phù hợp. Nếu tài liệu nói thời hạn là bảy ngày nhưng nhân viên đang áp dụng mười ngày, cần ghi nhận sự khác biệt và tìm hiểu nguyên nhân. Đừng âm thầm chọn một con số làm “sự thật”.

### 3.3. Diễn đạt mục tiêu thành kết quả

“Hoàn tất tự động trong ngày” chưa đủ rõ. Hoàn tất ở đây là tiếp nhận yêu cầu, quyết định đủ điều kiện, nhận hàng, kiểm tra hay hoàn tiền? Có loại hoàn trả nào được xử lý tự động? Chỉ số nào bảo đảm tốc độ không làm giảm khả năng kiểm soát gian lận?

Một mục tiêu rõ hơn có thể là:

> Trong phạm vi các yêu cầu hoàn trả tiêu chuẩn có đủ dữ liệu, khách hàng nhận được quyết định đủ điều kiện trong vòng một ngày làm việc. Các trường hợp cần kiểm tra hàng hóa hoặc phê duyệt ngoại lệ được chuyển đến đúng nhóm phụ trách, có trạng thái và lý do chờ rõ ràng.

Sau khi có số liệu nền, tổ chức có thể bổ sung tỷ lệ yêu cầu tiêu chuẩn được quyết định đúng hạn, thời gian xử lý trung vị, tỷ lệ quyết định phải sửa lại và tỷ lệ thất thoát do hoàn trả sai. Các chỉ số này giúp đánh giá kết quả mà không khuyến khích nhân viên chỉ đóng yêu cầu cho nhanh.

### 3.4. Đặt ba góc nhìn cạnh nhau

| Nội dung | Kết quả khám phá |
|---|---|
| Hiện trạng | Tổng đài tiếp nhận, nhân viên kiểm tra thủ công, kho xác minh, dữ liệu được theo dõi qua bảng chung và kết quả được thông báo cho khách |
| Chính sách hiện hành | Thời hạn tiếp nhận, điều kiện tình trạng sản phẩm, cách xử lý hàng lỗi và thẩm quyền phê duyệt ngoại lệ |
| Mục tiêu | Rút ngắn thời gian ra quyết định cho yêu cầu tiêu chuẩn, theo dõi rõ các trường hợp cần kiểm tra hoặc phê duyệt |
| Khoảng cách cần giải quyết | Dữ liệu phân tán, phụ thuộc vào xác minh thủ công, chưa có trạng thái thống nhất và chưa rõ cách đo thời gian xử lý |

Tách biệt ba góc nhìn cho thấy vấn đề có thể nằm ở chất lượng dữ liệu, điểm bàn giao, quyền quyết định hoặc khả năng theo dõi. Chỉ sau khi hiểu rõ các nguyên nhân này, đội mới có cơ sở đánh giá giải pháp như tự động kiểm tra điều kiện, tích hợp kho hay bổ sung trạng thái xử lý.

## 4. Quy trình khám phá và xác minh

### Bước 1: Chọn một phạm vi nghiệp vụ cụ thể

Không bắt đầu bằng câu hỏi quá rộng như “quy trình hoàn trả hoạt động thế nào?”. Hãy xác định điểm bắt đầu, điểm kết thúc, loại giao dịch, kênh và nhóm tham gia. Có thể bắt đầu bằng một trường hợp phổ biến rồi mở rộng sang ngoại lệ.

Phạm vi rõ giúp các bên nói về cùng một loại công việc. Nếu yêu cầu hoàn trả do khách đổi ý và yêu cầu do cửa hàng giao sai có chính sách khác nhau, hãy ghi nhận chúng thành các nhánh riêng.

### Bước 2: Thu thập bằng chứng về hiện trạng

Kết hợp phỏng vấn với quan sát và dữ liệu thực tế. Yêu cầu người tham gia kể lại một trường hợp vừa xử lý thay vì chỉ mô tả quy trình lý tưởng. Theo dấu trường hợp đó từ lúc phát sinh đến khi kết thúc, bao gồm cả thao tác ngoài hệ thống.

Ghi rõ đâu là sự kiện đã xảy ra, đâu là nhận định của người được phỏng vấn và đâu là giả định của nhóm. Khi có mâu thuẫn, giữ lại cả hai phiên bản cùng nguồn thông tin để tiếp tục xác minh.

### Bước 3: Đánh dấu các điểm ra quyết định

Trong luồng công việc, tìm những chỗ người thực hiện phải chọn một hướng xử lý. Với mỗi điểm, ghi lại đầu vào, tiêu chí, người có thẩm quyền, kết quả và cách xử lý ngoại lệ.

Một bảng quyết định đơn giản có thể giúp phát hiện quy tắc thiếu rõ ràng:

| Điều kiện | Kết quả dự kiến | Người hoặc vai trò quyết định | Cần xác minh |
|---|---|---|---|
| Đủ thời hạn và sản phẩm đáp ứng điều kiện | Tiếp nhận yêu cầu tiêu chuẩn | Nhân viên hỗ trợ hoặc hệ thống theo thẩm quyền | Có cần kiểm tra thêm loại sản phẩm không? |
| Sản phẩm giao sai hoặc bị hỏng | Chuyển sang chính sách xử lý lỗi giao hàng | Nhóm hỗ trợ theo quy định | Bằng chứng nào được chấp nhận? |
| Thiếu dữ liệu hoặc có ngoại lệ | Chuyển cấp để xem xét | Quản lý có thẩm quyền | Thời hạn phản hồi và quyền phê duyệt là gì? |

Bảng trên chỉ minh họa cách đặt câu hỏi, không phải chính sách mặc định cho mọi doanh nghiệp. Quy tắc thực tế phải được xác nhận với chuyên gia nghiệp vụ.

### Bước 4: Làm rõ chính sách và các xung đột

Đối chiếu lời giải thích của nhân viên với quy định, hợp đồng, biểu mẫu, cấu hình hệ thống và ví dụ giao dịch. Xác định chính sách nào đang có hiệu lực, chính sách nào đã lỗi thời, ai có quyền thay đổi và ngoại lệ được ghi nhận ở đâu.

Nếu hai bộ phận áp dụng tiêu chí khác nhau, đừng gộp chúng thành một quy tắc trung bình. Hãy tìm hiểu xem sự khác biệt đến từ phạm vi, kênh, loại khách hàng, thời điểm hiệu lực hay xung đột chưa được giải quyết.

### Bước 5: Xác định mục tiêu và cách đo

Hỏi các bên liên quan điều gì cần cải thiện và vì sao. Phân biệt mục tiêu với giải pháp được đề xuất. Sau đó xác định chỉ số nền, mức đích, thời hạn và các điều kiện bảo vệ chất lượng.

Ví dụ, giảm thời gian xử lý cần đi cùng tỷ lệ quyết định chính xác và tỷ lệ yêu cầu bị mở lại. Nếu chỉ đo tốc độ, đội có thể tạo động lực đóng hồ sơ sớm dù vấn đề của khách hàng chưa được giải quyết.

### Bước 6: Kiểm tra lại bằng tình huống cụ thể

Đưa mô tả hiện trạng, chính sách và mục tiêu trở lại với chuyên gia nghiệp vụ. Dùng cả trường hợp bình thường, trường hợp biên và trường hợp ngoại lệ. Hỏi xem mỗi trường hợp đã được mô tả đúng chưa, quy tắc nào còn mơ hồ và ai có quyền xác nhận.

Một mô hình chỉ có giá trị khi người hiểu nghiệp vụ nhận ra công việc của họ trong đó và có thể chỉ ra điểm chưa đúng.

## 5. Kỹ thuật đặt câu hỏi để không trộn lẫn dữ kiện

| Mục đích | Câu hỏi nên dùng | Câu hỏi cần hỏi tiếp |
|---|---|---|
| Hiểu hiện trạng | “Ở lần gần nhất, anh/chị đã xử lý trường hợp này như thế nào?” | “Có hồ sơ hoặc ví dụ nào để cùng xem lại không?” |
| Tìm ngoại lệ | “Khi thông tin thiếu hoặc hai hệ thống khác nhau thì chuyện gì xảy ra?” | “Ai xử lý và kết quả được ghi ở đâu?” |
| Tìm chính sách | “Tiêu chí nào khiến yêu cầu được chấp nhận hoặc từ chối?” | “Quy định nằm ở đâu, ai phê duyệt và có ngoại lệ nào?” |
| Kiểm tra việc áp dụng | “Quy tắc này có được áp dụng giống nhau ở mọi kênh không?” | “Có trường hợp nào làm khác không, vì sao?” |
| Làm rõ mục tiêu | “Nếu thay đổi thành công, khách hàng hoặc nhân viên sẽ nhận thấy điều gì?” | “Đo bằng chỉ số nào và hiện tại là bao nhiêu?” |
| Tách mục tiêu khỏi giải pháp | “Kết quả nào khiến anh/chị đề xuất chức năng này?” | “Nếu không có chức năng đó, kết quả mong muốn vẫn có thể đạt bằng cách nào?” |

Tránh hỏi dẫn dắt như “Có phải hệ thống cần tự động phê duyệt tất cả không?”. Câu hỏi này đã giả định giải pháp và có thể khiến người trả lời bỏ qua các ràng buộc quan trọng. Hãy hỏi về quyết định, tiêu chí và kết quả trước.

## 6. Ghi chép để giữ được nguồn gốc thông tin

Một bản ghi khám phá nên giúp người đọc biết phát biểu nào mô tả hiện trạng, phát biểu nào là chính sách và phát biểu nào là mục tiêu. Có thể dùng cấu trúc sau cho từng phát hiện:

| Trường | Nội dung cần ghi |
|---|---|
| ID | Mã tham chiếu duy nhất của phát hiện |
| Loại | Hoạt động hiện tại, chính sách hiện hành, chính sách đề xuất, mục tiêu hoặc giả định |
| Phát biểu | Một câu ngắn, rõ nghĩa và có thể kiểm chứng |
| Phạm vi | Loại giao dịch, kênh, nhóm hoặc thời gian áp dụng |
| Nguồn | Người xác nhận, tài liệu, hồ sơ hoặc quan sát |
| Ví dụ | Trường hợp minh họa hoặc phản ví dụ |
| Mức tin cậy | Đã xác nhận, đang tranh luận hoặc chưa có bằng chứng |
| Người xác nhận | Vai trò có trách nhiệm xác nhận nội dung |
| Câu hỏi còn mở | Thông tin cần làm rõ và người phụ trách |

Ví dụ về cách ghi:

| Loại | Phát biểu | Nguồn và trạng thái |
|---|---|---|
| Hoạt động hiện tại | Nhân viên hỗ trợ ghi yêu cầu hoàn trả vào bảng theo dõi chung sau khi tìm thấy đơn hàng | Quan sát ba hồ sơ; đã xác nhận trong phạm vi kênh tổng đài |
| Chính sách hiện hành | Yêu cầu hoàn trả thông thường phải được gửi trong bảy ngày kể từ khi nhận hàng | Tài liệu chính sách; cần xác nhận phiên bản đang có hiệu lực |
| Mục tiêu | Yêu cầu tiêu chuẩn nhận quyết định đủ điều kiện trong một ngày làm việc | Đề xuất của chủ nghiệp vụ; cần thống nhất chỉ số nền và phạm vi |

Không nên xóa một phát hiện khi có ý kiến trái chiều. Hãy ghi rõ ai đưa ra ý kiến, phạm vi họ nói đến và bằng chứng hiện có. Việc giữ lại khác biệt giúp đội nhận diện câu hỏi cần quyết định thay vì che giấu chúng trong một mô tả tưởng như thống nhất.

## 7. Những nhầm lẫn thường gặp

### Nhầm quy trình trên tài liệu với hoạt động thực tế

Tài liệu có thể đã lỗi thời hoặc mô tả quy trình chuẩn trong khi nhân viên phải xử lý nhiều ngoại lệ. Hãy theo dấu giao dịch thực tế và ghi lại chênh lệch giữa quy định với thực hành.

### Nhầm thói quen với chính sách

Một nhân viên luôn gọi quản lý trước khi xử lý có thể đang tuân theo chính sách, nhưng cũng có thể chỉ làm vậy vì hệ thống thiếu thông tin. Hãy xác minh căn cứ, thẩm quyền và phạm vi áp dụng trước khi biến hành vi đó thành quy tắc.

### Nhầm chính sách được viết với chính sách đang có hiệu lực

Một tài liệu có thể chưa được cập nhật, chưa được truyền đạt hoặc không còn được áp dụng. Kiểm tra chủ sở hữu, phiên bản, ngày hiệu lực và ví dụ thực tế.

### Nhầm mục tiêu với chức năng

“Có dashboard”, “tự động gửi email” hay “tích hợp hệ thống kho” là ý tưởng giải pháp. Hãy tìm kết quả nghiệp vụ mà chức năng đó cần hỗ trợ, rồi mới đánh giá giải pháp.

### Đặt mục tiêu mà không có chỉ số bảo vệ

Tăng tốc độ xử lý có thể làm tăng sai sót hoặc rủi ro. Cần xem xét đồng thời chỉ số kết quả và các giới hạn về chất lượng, tuân thủ, chi phí hoặc trải nghiệm.

### Gộp các chính sách khác nhau thành một quy tắc chung

Các loại giao dịch, nhóm khách hàng hoặc khu vực có thể chịu những điều kiện khác nhau. Giữ rõ phạm vi và ngày hiệu lực để mô hình không áp dụng nhầm quy tắc.

### Vội thiết kế mô hình phần mềm

Khi chưa thống nhất thuật ngữ, phạm vi và chính sách, việc tạo entity, service hoặc trạng thái kỹ thuật quá sớm dễ đóng băng một cách hiểu chưa được xác minh. Hãy hoàn thành khám phá và làm rõ các điểm bất đồng trước khi chuyển sang thiết kế chiến thuật.

## 8. Liên hệ với Domain-Driven Design

DDD hướng đến việc xây dựng mô hình miền phản ánh hiểu biết nghiệp vụ đã được kiểm chứng. Việc tách hiện trạng, chính sách và mục tiêu hỗ trợ trực tiếp cho quá trình này:

- **Ngôn ngữ chung (Ubiquitous Language):** các bên thống nhất ý nghĩa của những thuật ngữ như “yêu cầu hoàn trả”, “đủ điều kiện”, “ngoại lệ”, “đã tiếp nhận” và “đã hoàn tiền”. Cùng một từ không nên bị dùng cho nhiều trạng thái khác nhau mà không giải thích.
- **Khám phá miền (Domain Discovery):** hiện trạng cho biết công việc và sự kiện đang diễn ra; chính sách cho biết logic nghiệp vụ đứng sau quyết định; mục tiêu cho biết lý do cần thay đổi.
- **Thiết kế chiến lược (Strategic Design):** khác biệt về chính sách, trách nhiệm và ngôn ngữ giữa các nhóm có thể là tín hiệu để xem xét ranh giới miền hoặc bounded context. Không nên suy ra bounded context chỉ từ sơ đồ phòng ban.
- **Thiết kế chiến thuật (Tactical Design):** sau khi chính sách được xác nhận, đội mới quyết định cách biểu diễn các khái niệm và quy tắc trong mô hình miền, chẳng hạn entity, value object, aggregate hoặc domain service. Việc một chính sách có trở thành một đối tượng hay dịch vụ riêng hay không phụ thuộc vào trách nhiệm và quy tắc thực tế của miền.
- **Domain Event:** sự kiện như “Yêu cầu hoàn trả đã được gửi” hoặc “Yêu cầu hoàn trả đã được phê duyệt” mô tả điều đã xảy ra. Sự kiện giúp tái dựng luồng nghiệp vụ, nhưng bản thân tên sự kiện không giải thích chính sách nào khiến quyết định được đưa ra.

Có thể hình dung mối quan hệ giữa ba góc nhìn như sau:

~~~mermaid
flowchart TD
    A["Quan sát công việc và trường hợp thực tế"] --> B["Mô tả hoạt động hiện tại"]
    C["Quy định, tiêu chí và thẩm quyền"] --> D["Xác minh chính sách"]
    E["Nhu cầu và kết quả cần đạt"] --> F["Xác định mục tiêu"]
    B --> G["Đối chiếu khoảng cách và vấn đề"]
    D --> G
    F --> G
    G --> H["Thống nhất hiểu biết nghiệp vụ"]
    H --> I["Làm cơ sở cho mô hình miền và thiết kế"]
~~~

Mục tiêu mong muốn không tự động trở thành chính sách. Tổ chức có thể cần thay đổi chính sách để đạt mục tiêu, nhưng thay đổi đó phải được người có thẩm quyền quyết định. Tương tự, mô hình phần mềm không nên mô tả một quy tắc là hiện hành nếu các bên vẫn đang tranh luận về hiệu lực của nó.

## 9. Mẫu đầu ra sau một vòng khám phá

Trước khi kết thúc một vòng khám phá, đội nên có tối thiểu:

1. **Phạm vi khảo sát:** điểm bắt đầu, điểm kết thúc, loại trường hợp và nhóm tham gia.
2. **Bản mô tả hiện trạng:** các bước, vai trò, thông tin, sự kiện, điểm bàn giao và ngoại lệ có bằng chứng.
3. **Danh sách chính sách:** nội dung, phạm vi, nguồn, người có thẩm quyền, ngày hiệu lực và các điểm chưa thống nhất.
4. **Mục tiêu mong muốn:** đối tượng hưởng lợi, kết quả, chỉ số nền, mức đích, thời hạn và ràng buộc.
5. **Khoảng cách và vấn đề:** nơi hiện trạng hoặc chính sách hiện hành chưa đáp ứng mục tiêu.
6. **Giả định và câu hỏi mở:** nội dung chưa được xác minh, người cần xác nhận và bước tiếp theo.

Có thể dùng mẫu ngắn sau trong buổi làm việc:

~~~text
Phạm vi:

HOẠT ĐỘNG HIỆN TẠI
- Sự kiện bắt đầu:
- Các vai trò tham gia:
- Các bước thực tế:
- Ngoại lệ và cách xử lý:
- Bằng chứng:

CHÍNH SÁCH
- Quyết định cần đưa ra:
- Tiêu chí và quy tắc:
- Người có thẩm quyền:
- Nguồn và ngày hiệu lực:
- Ngoại lệ hoặc xung đột:

MỤC TIÊU MONG MUỐN
- Đối tượng hưởng lợi:
- Kết quả cần đạt:
- Chỉ số nền và mức đích:
- Thời hạn:
- Ràng buộc cần giữ:

KHOẢNG CÁCH VÀ CÂU HỎI MỞ
- Vấn đề đã xác nhận:
- Giả định cần kiểm chứng:
- Người chịu trách nhiệm xác nhận:
~~~

## 10. Tiêu chí tự kiểm tra

Một kết quả khám phá đủ rõ để chuyển sang bước mô hình hóa khi người đọc có thể trả lời được:

- Mô tả hiện trạng có dựa trên trường hợp hoặc dữ liệu thực tế không?
- Đã phân biệt quy trình chính thức với cách công việc đang được thực hiện chưa?
- Mỗi chính sách có phạm vi, nguồn và người có thẩm quyền xác nhận chưa?
- Những nơi chính sách và thực hành khác nhau có được ghi lại không?
- Mục tiêu mô tả kết quả nghiệp vụ hay chỉ liệt kê chức năng dự kiến?
- Có chỉ số hoặc cách thu thập dữ liệu để đánh giá tiến triển không?
- Các giả định, mâu thuẫn và câu hỏi còn mở có được công khai không?
- Các bên liên quan có cùng hiểu những thuật ngữ quan trọng không?

Nếu chưa trả lời được, hãy tiếp tục khám phá hoặc ghi rõ mức độ chưa chắc chắn. Một mô hình miền tốt bắt đầu từ hiểu biết trung thực về nghiệp vụ: điều gì đang xảy ra, quyết định dựa trên nguyên tắc nào và tổ chức muốn đạt kết quả gì.
