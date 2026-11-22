# Phỏng vấn chuyên gia bằng tình huống và ví dụ nghiệp vụ cụ thể

Trong Domain-Driven Design (DDD), mô hình miền phải phản ánh cách doanh nghiệp thực sự vận hành. Muốn xây dựng được mô hình như vậy, đội phát triển cần hiểu cách chuyên gia nghiệp vụ nhìn nhận công việc, những quyết định họ đưa ra, các quy tắc chi phối quyết định và ý nghĩa chính xác của những thuật ngữ họ sử dụng.

Phỏng vấn chuyên gia là một hoạt động khám phá miền (domain discovery), không đơn thuần là thu thập danh sách yêu cầu. Một câu hỏi chung chung thường chỉ nhận được câu trả lời khái quát như “đơn hàng được kiểm tra, thanh toán rồi giao cho khách”. Khi cùng chuyên gia lần lại một đơn hàng cụ thể, đội phát triển có thể phát hiện những chi tiết quan trọng: thời điểm đơn được xem là hợp lệ, ai có quyền giữ hàng, điều gì xảy ra khi tồn kho sai lệch, trường hợp nào được giao một phần và lúc nào doanh nghiệp phải hoàn tiền.

Cách phỏng vấn hiệu quả là bắt đầu từ một tình huống có thật, dựng lại diễn biến theo thời gian, hỏi sâu vào từng quyết định, sau đó thay đổi một vài điều kiện để làm rõ quy tắc. Kết quả cần đạt được là một hiểu biết có thể kiểm chứng về nghiệp vụ, cùng một ngôn ngữ đủ rõ để chuyên gia và đội phát triển tiếp tục mô hình hóa miền.

## 1. Vì sao nên phỏng vấn bằng tình huống cụ thể?

Kiến thức nghiệp vụ thường nằm trong kinh nghiệm và thói quen xử lý công việc. Chuyên gia có thể biết rất rõ cách giải quyết một vấn đề nhưng khó diễn đạt toàn bộ quy trình thành một bản mô tả hoàn chỉnh. Họ cũng có thể bỏ qua những bước mà họ cho là hiển nhiên, hoặc dùng một thuật ngữ quen thuộc với bộ phận của mình nhưng mang nghĩa khác ở bộ phận khác.

Câu hỏi trừu tượng thường tạo ra câu trả lời theo quy trình lý tưởng:

- “Quy trình xử lý đơn hàng diễn ra như thế nào?”
- “Khi nào một đơn hàng được coi là hoàn tất?”
- “Nếu thiếu hàng thì hệ thống cần làm gì?”

Những câu hỏi này có ích để mở đầu, nhưng chưa đủ để hiểu nghiệp vụ. Câu trả lời có thể bỏ qua người ra quyết định, dữ liệu được xem xét, điều kiện áp dụng, ngoại lệ và trách nhiệm giữa các bộ phận.

Có thể chuyển chúng thành câu hỏi gắn với một trường hợp:

| Câu hỏi chung | Câu hỏi theo tình huống |
|---|---|
| Quy trình xử lý đơn hàng thế nào? | Hãy chọn một đơn hàng gần đây và kể lại từ lúc khách gửi đơn đến khi đơn được xử lý xong. |
| Khi nào đơn được coi là hoàn tất? | Với đơn hàng này, ai xác nhận hoàn tất, xác nhận vào thời điểm nào và dựa trên bằng chứng nào? |
| Thiếu hàng thì xử lý ra sao? | Lần gần nhất kho phát hiện số lượng thực tế ít hơn số lượng trên đơn, mọi người đã làm gì tiếp theo? |
| Ai có quyền hủy đơn? | Trong trường hợp cụ thể này, ai yêu cầu hủy, ai phê duyệt và điều kiện nào khiến yêu cầu được chấp nhận? |

Tình huống cụ thể giúp người được phỏng vấn nhớ lại hành động và quyết định thực tế. Nó cũng cho phép người phỏng vấn kiểm tra câu trả lời bằng cách hỏi tiếp: “Điều gì xảy ra ngay sau đó?”, “Vì sao lại chọn cách này?” và “Nếu điều kiện thay đổi thì kết quả có khác không?”.

Một tình huống không đại diện cho toàn bộ nghiệp vụ. Nó là điểm bắt đầu để tìm ra quy tắc, sau đó cần so sánh với những trường hợp khác.

## 2. Chuẩn bị trước buổi phỏng vấn

### 2.1. Xác định điều cần khám phá

Không nên bắt đầu với mục tiêu quá rộng như “tìm hiểu toàn bộ quy trình bán hàng”. Hãy chọn một phạm vi có thể theo dõi được, chẳng hạn:

- Cách doanh nghiệp tiếp nhận và xác nhận đơn hàng.
- Cách giữ hàng và xử lý chênh lệch tồn kho.
- Điều kiện cho phép thay đổi hoặc hủy đơn.
- Cách xác định một giao dịch đã được thanh toán.
- Cách xử lý khiếu nại sau khi giao hàng.

Mục tiêu rõ giúp người phỏng vấn biết cần đi sâu vào quyết định nào và tránh để cuộc trao đổi trôi sang những vấn đề chưa liên quan.

### 2.2. Chọn đúng người và vai trò

Một chuyên gia có thể hiểu sâu một phần quy trình nhưng không nắm mọi quyết định ở các bộ phận khác. Khi nghiệp vụ đi qua nhiều vai trò, nên phỏng vấn những người trực tiếp thực hiện, người chịu trách nhiệm ra quyết định và người tiếp nhận kết quả ở bước kế tiếp.

Ví dụ, để hiểu việc giao hàng thiếu sản phẩm, có thể cần trao đổi với nhân viên kho, bộ phận chăm sóc khách hàng và người có quyền quyết định phương án xử lý. Mỗi người có thể cung cấp một góc nhìn khác nhau về cùng một sự kiện.

Không nên mặc định người có chức danh cao nhất là người hiểu rõ nhất các tình huống phát sinh hằng ngày. Người trực tiếp xử lý công việc thường biết những ngoại lệ mà tài liệu quy trình không đề cập.

### 2.3. Chuẩn bị tài liệu và tình huống gợi nhớ

Nếu được phép, hãy đề nghị chuyên gia chọn một hồ sơ đã xử lý hoặc một ví dụ đã ẩn thông tin nhạy cảm. Những thứ như phiếu xử lý, biểu mẫu, trạng thái đơn, thông báo, báo cáo hoặc lịch sử giao dịch có thể giúp hai bên cùng nhìn vào một sự việc.

Cần thống nhất cách bảo vệ dữ liệu khách hàng và thông tin nội bộ. Chỉ sử dụng dữ liệu cần thiết cho việc khám phá nghiệp vụ; xin phép trước khi ghi âm hoặc lưu lại tài liệu có giới hạn truy cập.

### 2.4. Ghi rõ giả thuyết

Người phỏng vấn thường mang theo giả định từ kinh nghiệm trước đó, ví dụ:

- Đơn chỉ được xác nhận sau khi thanh toán.
- Hàng luôn được giữ ngay khi khách đặt.
- Mọi đơn đều có thể giao thành nhiều đợt.

Hãy ghi các ý này thành giả thuyết cần kiểm chứng. Không biến chúng thành sự thật chỉ vì chúng hợp lý với cách một hệ thống thường được thiết kế.

Một câu hỏi tốt để kiểm tra giả thuyết là: “Có trường hợp nào đơn đã được xác nhận nhưng chưa thanh toán không?” hoặc “Có khi nào hàng được giữ trước khi đơn được xác nhận không?”.

## 3. Quy trình phỏng vấn theo một tình huống

Một buổi phỏng vấn có thể đi theo bảy bước. Trình tự này tạo ra mạch kể chuyện tự nhiên, đồng thời giúp người phỏng vấn đi từ sự kiện quan sát được đến quy tắc nghiệp vụ ẩn phía sau.

### Bước 1: Giới thiệu mục đích và phạm vi

Nói rõ rằng mục tiêu là hiểu cách công việc diễn ra, không phải đánh giá hiệu suất cá nhân hay yêu cầu chuyên gia thiết kế phần mềm. Hãy thống nhất phạm vi và cách ghi nhận thông tin.

Có thể mở đầu:

> Tôi muốn hiểu cách bộ phận xử lý trường hợp đơn hàng có vấn đề về tồn kho. Anh/chị có thể chọn một trường hợp gần đây và cùng tôi lần lại những gì đã xảy ra không?

Cách mở đầu này mời chuyên gia kể về công việc thực tế, thay vì yêu cầu họ trình bày một quy trình lý tưởng.

### Bước 2: Chọn một trường hợp có thật

Ưu tiên một trường hợp gần đây, có diễn biến đủ rõ và nằm trong phạm vi cần khám phá. Có thể bắt đầu với một trường hợp bình thường để hiểu luồng chính, sau đó chọn một trường hợp ngoại lệ để tìm hiểu quy tắc.

Câu hỏi gợi mở:

- Anh/chị nhớ đơn hàng hoặc giao dịch nào gần đây thể hiện rõ quy trình này?
- Điều gì khiến trường hợp đó đáng chú ý?
- Ai tham gia xử lý?
- Kết quả cuối cùng là gì?

Nếu chuyên gia chỉ mô tả một quy trình chung, hãy nhẹ nhàng đưa cuộc trao đổi trở lại trường hợp đã chọn: “Trong đơn hàng vừa nhắc đến, việc đó đã diễn ra cụ thể như thế nào?”.

### Bước 3: Dựng lại diễn biến theo thời gian

Yêu cầu chuyên gia kể từ thời điểm sự việc bắt đầu, lần lượt qua từng hành động và kết quả. Không vội chuyển sang giải pháp kỹ thuật.

Với mỗi bước, làm rõ:

1. Điều gì vừa xảy ra?
2. Ai thực hiện hoặc chịu trách nhiệm?
3. Người đó nhận được thông tin gì?
4. Họ đã làm gì hoặc quyết định điều gì?
5. Kết quả nào xuất hiện sau hành động đó?
6. Bước tiếp theo do ai tiếp nhận?

Ví dụ, thay vì ghi “kho xử lý đơn”, hãy tìm hiểu xem nhân viên kho nhận danh sách lấy hàng lúc nào, đối chiếu số lượng ở đâu, xử lý chênh lệch như thế nào và thông báo cho bộ phận nào.

Có thể vẽ một dòng thời gian đơn giản trong lúc trao đổi:

~~~text
Khách gửi đơn
    |
    v
Đơn được tiếp nhận
    |
    v
Kiểm tra khả năng cung ứng
    |
    +---- Đủ hàng ------> Tiếp tục xử lý
    |
    +---- Thiếu hàng ---> Chọn phương án theo quy tắc
                              |
                              v
                        Thông báo kết quả
~~~

Sơ đồ chỉ là khung ghi nhận ban đầu. Các bước, tên gọi và nhánh xử lý phải được xác nhận với chuyên gia.

### Bước 4: Hỏi sâu vào từng quyết định

Một mô tả hành động chưa giải thích được vì sao hành động đó xảy ra. Hãy tập trung vào điểm có lựa chọn hoặc phán đoán của con người.

Các câu hỏi hữu ích:

- Tại sao anh/chị chọn phương án đó?
- Có những phương án nào khác?
- Điều kiện nào khiến phương án này được chấp nhận?
- Ai có quyền đưa ra quyết định?
- Có trường hợp nào phải xin phê duyệt không?
- Nếu không có đủ thông tin thì xử lý thế nào?
- Quyết định có thể được thay đổi sau đó không?

Đặc biệt chú ý những từ như “phải”, “chỉ khi”, “trừ khi”, “thông thường”, “được phép” và “không được”. Chúng thường dẫn đến quy tắc nghiệp vụ hoặc điều kiện ngoại lệ.

### Bước 5: Thay đổi một điều kiện để tìm ranh giới của quy tắc

Sau khi hiểu một trường hợp, hãy đặt câu hỏi về một biến thể gần với trường hợp ban đầu. Chỉ thay đổi một yếu tố mỗi lần để xác định điều gì làm kết quả thay đổi.

Ví dụ:

- Nếu đơn có đủ hàng nhưng thanh toán thất bại thì sao?
- Nếu kho phát hiện thiếu hàng sau khi đơn đã được xác nhận thì sao?
- Nếu khách yêu cầu hủy sau khi kho đã đóng gói thì sao?
- Nếu hai đơn cùng yêu cầu đơn vị hàng cuối cùng thì ai được ưu tiên?
- Nếu khách đồng ý nhận hàng thành nhiều đợt thì quy trình có khác không?

Không nên chỉ hỏi những tình huống tưởng tượng xa thực tế. Hãy ưu tiên các trường hợp đã từng xảy ra, sau đó mới hỏi về khả năng chưa gặp để làm rõ giới hạn của quy tắc.

### Bước 6: Làm rõ thuật ngữ nghiệp vụ

Khi chuyên gia sử dụng một từ quan trọng, hãy hỏi ý nghĩa của nó trong tình huống vừa kể.

Ví dụ:

- “Đơn đã nhận” có nghĩa là doanh nghiệp đã ghi nhận yêu cầu, đã chấp nhận đơn hay đã cam kết giao hàng?
- “Giữ hàng” là ghi nhận số lượng dự kiến, khóa số lượng cho một đơn hay chuyển hàng sang khu vực riêng?
- “Đã giao” nghĩa là hàng rời kho, đơn vị vận chuyển đã nhận hay khách đã nhận hàng?
- “Hoàn tiền” là đã tạo yêu cầu hoàn tiền hay tiền đã thực sự về tài khoản khách?

Không nên tự thay thế thuật ngữ của chuyên gia bằng thuật ngữ quen thuộc với đội phát triển. Nếu hai bên dùng cùng một từ nhưng hiểu khác nhau, mô hình sẽ dễ phản ánh sai nghiệp vụ.

### Bước 7: Tóm tắt và xác nhận

Cuối buổi, hãy kể lại diễn biến bằng ngôn ngữ của mình và nhờ chuyên gia xác nhận:

- Các bước có đúng thứ tự không?
- Có quyết định nào bị bỏ sót không?
- Quy tắc nào chỉ đúng trong điều kiện nhất định?
- Có ngoại lệ nào cần trao đổi thêm?
- Thuật ngữ nào cần định nghĩa chính xác hơn?

Nếu chuyên gia sửa lại cách diễn giải, hãy ghi nhận phần sửa đổi. Một bản tóm tắt được xác nhận có giá trị hơn những ghi chú chỉ phản ánh cách hiểu của người phỏng vấn.

## 4. Ví dụ thực hành: khám phá quy tắc xử lý đơn hàng thiếu hàng

Phần này dùng một tình huống bán lẻ giả định để minh họa cách đặt câu hỏi. Các phương án dưới đây không phải quy tắc mặc định cho mọi doanh nghiệp; người phỏng vấn phải hỏi chuyên gia để xác định chính sách thực tế.

### 4.1. Bắt đầu từ sự việc

Giả sử khách đặt ba sản phẩm. Đến bước chuẩn bị hàng, nhân viên kho phát hiện chỉ có hai sản phẩm khả dụng. Thông tin tồn kho trước đó thể hiện có đủ ba sản phẩm.

Thay vì hỏi ngay “hệ thống nên xử lý thế nào?”, hãy đề nghị chuyên gia kể lại một trường hợp tương tự đã từng xảy ra.

Người phỏng vấn cần làm rõ:

- Đơn được tạo và tiếp nhận vào thời điểm nào?
- Tồn kho được kiểm tra ở bước nào?
- Hàng đã được giữ cho đơn chưa?
- Ai phát hiện chênh lệch?
- Số lượng thực tế được xác minh bằng cách nào?
- Bộ phận nào được thông báo?
- Ai quyết định phương án cuối cùng?
- Khách được thông báo khi nào?
- Thanh toán được xử lý ra sao?

### 4.2. Tìm hiểu các phương án nghiệp vụ

Khi xác nhận thiếu hàng, doanh nghiệp có thể có nhiều chính sách. Chẳng hạn:

| Phương án có thể có | Điều cần hỏi chuyên gia |
|---|---|
| Giao phần hàng hiện có | Có được phép giao một phần không? Ai xác nhận với khách? Chi phí giao hàng thay đổi thế nào? |
| Chờ bổ sung hàng | Thời hạn chờ là bao lâu? Đơn có giữ chỗ cho số hàng còn thiếu không? Khi quá hạn thì sao? |
| Đề nghị sản phẩm thay thế | Ai chọn sản phẩm thay thế? Khách phải đồng ý trong điều kiện nào? Giá bán được tính lại ra sao? |
| Hủy toàn bộ đơn | Ai có quyền hủy? Có cần khách xác nhận không? Khoản thanh toán được xử lý thế nào? |
| Hủy một phần | Phần còn lại của đơn có tiếp tục không? Số tiền và phí liên quan được tính lại ra sao? |

Không ghi tất cả phương án vào mô hình như thể chúng đều tồn tại. Mục tiêu của bảng là giúp người phỏng vấn đặt câu hỏi có hệ thống và xác định phương án nào thực sự được doanh nghiệp áp dụng.

### 4.3. So sánh các tình huống

Hãy thay đổi điều kiện và hỏi chuyên gia kết quả có khác không:

| Tình huống | Điểm cần khám phá |
|---|---|
| Thiếu hàng trước khi đơn được xác nhận | Đơn có được tiếp nhận không? Khách có thể sửa số lượng không? |
| Thiếu hàng sau khi đã giữ hàng | Việc giữ hàng có được coi là cam kết không? Ai xử lý chênh lệch? |
| Thiếu hàng sau khi đã thanh toán | Khoản tiền được giữ, hoàn hay điều chỉnh như thế nào? |
| Khách đồng ý nhận hàng một phần | Phần còn lại có tiếp tục được theo dõi trong cùng đơn không? |
| Khách không phản hồi đề xuất | Đơn được chờ đến thời điểm nào? Ai quyết định bước tiếp theo? |

Từ những câu trả lời này, đội phát triển có thể nhận diện các điều kiện làm thay đổi luồng nghiệp vụ. Chẳng hạn, thời điểm phát hiện thiếu hàng có thể quan trọng vì trách nhiệm và cách xử lý thanh toán khác nhau trước và sau khi đơn được xác nhận.

### 4.4. Nhận diện sự kiện, hành động và quy tắc

Trong DDD, cần phân biệt điều mà một người yêu cầu thực hiện với điều đã thực sự xảy ra.

- **Command (lệnh nghiệp vụ):** ý định yêu cầu một hành động, ví dụ yêu cầu hủy đơn hoặc xác nhận giao một phần.
- **Domain event (sự kiện miền):** một sự việc có ý nghĩa nghiệp vụ đã xảy ra, ví dụ đơn đã bị hủy hoặc hàng đã được giữ.
- **Business rule (quy tắc nghiệp vụ):** điều kiện chi phối hành động hoặc quyết định, ví dụ chỉ được giao một phần khi khách đã đồng ý.
- **Policy (chính sách phản ứng):** quy định cách nghiệp vụ phản ứng khi một sự kiện hoặc điều kiện xuất hiện, ví dụ khi kho báo thiếu hàng thì yêu cầu bộ phận chăm sóc khách hàng liên hệ khách.

Ví dụ, “yêu cầu hủy đơn” không đồng nghĩa “đơn đã bị hủy”. Yêu cầu có thể cần phê duyệt hoặc có thể bị từ chối. Tương tự, “yêu cầu hoàn tiền” không chứng minh tiền đã được hoàn thành công.

Các khái niệm này là gợi ý để phân tích câu chuyện, không phải nhãn cần gán máy móc cho mọi câu nói. Chỉ xác định một sự kiện miền khi chuyên gia xác nhận đó là điều đã xảy ra và có ý nghĩa đối với nghiệp vụ.

## 5. Các nhóm câu hỏi giúp tìm ra quy tắc ẩn

Một luồng xử lý bình thường thường chưa bộc lộ hết mô hình miền. Người phỏng vấn nên khám phá các nhóm tình huống sau.

### 5.1. Trường hợp bình thường

Tìm hiểu luồng phổ biến nhất, các vai trò tham gia, đầu vào cần thiết và kết quả mong đợi.

- Trường hợp này thường bắt đầu từ đâu?
- Điều kiện tối thiểu để bắt đầu là gì?
- Ai chịu trách nhiệm ở mỗi bước?
- Kết quả nào cho biết công việc đã hoàn thành?

### 5.2. Trường hợp biên

Trường hợp biên giúp tìm ra ranh giới của quy tắc.

- Số lượng bằng đúng mức tồn kho tối thiểu thì xử lý thế nào?
- Giao dịch xảy ra đúng thời điểm hết hạn thì được tính ra sao?
- Giá trị bằng ngưỡng phê duyệt có cần cấp cao hơn duyệt không?
- Khi một thông tin bắt buộc bị thiếu thì quy trình dừng ở đâu?

### 5.3. Trường hợp ngoại lệ và thất bại

Đừng chỉ hỏi “điều gì xảy ra khi có lỗi?”. Hãy hỏi lỗi được phát hiện bởi ai, vào lúc nào và doanh nghiệp xử lý hậu quả như thế nào.

- Thanh toán thất bại nhưng đơn đã được tạo thì sao?
- Hệ thống bên ngoài không phản hồi thì ai theo dõi?
- Dữ liệu giữa hai bộ phận không khớp thì nguồn nào được dùng để xác nhận?
- Có thể thử lại không? Nếu thử lại nhiều lần thì điều gì ngăn việc xử lý trùng?

### 5.4. Trường hợp thay đổi quyết định

Nghiệp vụ có thể cho phép thay đổi một quyết định trước đó.

- Khi nào khách được sửa hoặc hủy yêu cầu?
- Quyết định nào không thể đảo ngược?
- Nếu đã chuyển giao cho bộ phận khác thì ai có quyền thay đổi?
- Khi sửa thông tin, những bước nào phải thực hiện lại?

### 5.5. Trường hợp đồng thời và xung đột

Một quy tắc có thể đúng khi chỉ có một giao dịch nhưng thất bại khi nhiều giao dịch xảy ra cùng lúc.

- Nếu hai khách cùng mua đơn vị hàng cuối cùng thì ai được ưu tiên?
- Nếu hai nhân viên cùng xử lý một yêu cầu thì sao?
- Có cần khóa tài nguyên hoặc xác nhận lại trước khi cam kết không?
- Ai chịu trách nhiệm giải quyết khi hai bộ phận ghi nhận kết quả khác nhau?

### 5.6. Trường hợp có can thiệp thủ công

Các thao tác thủ công thường cho thấy quyền hạn và quy tắc chưa được thể hiện rõ.

- Ai được phép ghi đè kết quả tự động?
- Có cần lý do hoặc phê duyệt không?
- Thay đổi có được lưu dấu vết không?
- Người xử lý tiếp theo có nhìn thấy lý do thay đổi không?

Khi ghi nhận câu trả lời, cần phân biệt quy tắc chính thức với cách làm tạm thời do công cụ hoặc quy trình hiện tại còn hạn chế.

## 6. Khám phá ngôn ngữ chung của miền

DDD sử dụng Ubiquitous Language (ngôn ngữ chung) để chuyên gia nghiệp vụ và đội phát triển trao đổi bằng những thuật ngữ có ý nghĩa nhất quán trong một phạm vi mô hình.

Phỏng vấn là cơ hội phát hiện các vấn đề về ngôn ngữ:

**Một từ có nhiều nghĩa.** Ví dụ, “đơn đã nhận” có thể được bộ phận bán hàng hiểu là đã ghi nhận yêu cầu, trong khi bộ phận kho hiểu là đã có lệnh chuẩn bị hàng.

**Nhiều từ chỉ cùng một khái niệm.** Bộ phận này gọi là “giữ hàng”, bộ phận khác gọi là “khóa tồn”, nhưng cả hai có thể đang mô tả cùng một hành động. Cần xác minh trước khi coi chúng là đồng nghĩa.

**Từ quen thuộc nhưng thiếu điều kiện.** “Khách hàng hợp lệ”, “giao hàng thành công” hay “đơn hoàn tất” nghe có vẻ rõ ràng nhưng thường cần điều kiện cụ thể.

Với mỗi thuật ngữ quan trọng, hãy ghi:

| Thành phần | Nội dung cần làm rõ |
|---|---|
| Thuật ngữ | Từ chuyên gia thực sự sử dụng |
| Định nghĩa | Ý nghĩa trong nghiệp vụ đang khám phá |
| Ví dụ | Một tình huống thể hiện đúng khái niệm |
| Phản ví dụ | Một tình huống dễ nhầm nhưng không thuộc khái niệm |
| Vai trò sử dụng | Bộ phận hoặc vai trò dùng thuật ngữ |
| Phạm vi | Nơi định nghĩa này có hiệu lực |
| Câu hỏi còn mở | Điểm chưa thống nhất hoặc cần xác minh |

Đừng ép các bộ phận dùng chung một từ nếu họ thực sự đang nói về hai khái niệm khác nhau. Sự khác biệt trong ngôn ngữ có thể phản ánh sự khác biệt về trách nhiệm, quy tắc hoặc ranh giới giữa các bounded context.

## 7. Từ ghi chú phỏng vấn đến bằng chứng cho mô hình miền

Sau phỏng vấn, hãy chuyển câu chuyện thành những thông tin có thể xem xét và kiểm chứng. Không nên lập tức biến mọi danh từ thành entity hoặc mọi động từ thành domain event.

Một số dấu hiệu cần chú ý:

| Dấu hiệu trong câu chuyện | Câu hỏi phân tích tiếp |
|---|---|
| Một đối tượng có vòng đời và cần được phân biệt với đối tượng khác | Đối tượng có danh tính riêng và được theo dõi qua thời gian không? Có thể là ứng viên Entity. |
| Một giá trị được xác định bởi các thuộc tính | Hai giá trị có cùng thuộc tính được xem là tương đương không? Có thể là ứng viên Value Object. |
| Một hành động được yêu cầu | Đây là ý định cần xử lý hay sự kiện đã xảy ra? Có thể là Command. |
| Một sự việc đã hoàn thành | Sự việc có ý nghĩa nghiệp vụ nào và bộ phận nào cần biết? Có thể là Domain Event. |
| Một điều kiện phải luôn đúng | Ai bảo đảm điều kiện đó? Khi vi phạm thì nghiệp vụ phản ứng ra sao? Có thể là Invariant. |
| Một sự kiện dẫn đến hành động tiếp theo | Quy tắc hoặc Policy nào quyết định phản ứng? |

Ví dụ, chuyên gia nói “nhân viên xác nhận giữ hàng”. Hãy hỏi xác nhận đó tạo ra cam kết gì, có thời hạn không, số lượng được dành riêng cho đơn nào và khi hết hạn thì điều gì xảy ra. Chỉ sau khi hiểu ý nghĩa nghiệp vụ mới nên cân nhắc đối tượng, trạng thái và quy tắc cần có trong mô hình.

Cũng cần phân biệt **trạng thái** với **sự kiện**. “Đang chờ giao” có thể là trạng thái hiện tại của đơn; “đơn đã được bàn giao cho đơn vị vận chuyển” mô tả một sự việc đã xảy ra. Một trạng thái có thể được hình thành từ nhiều sự kiện, và một sự kiện có thể khiến nhiều đối tượng liên quan thay đổi.

### 7.1. Ghi lại nguồn gốc của từng kết luận

Với mỗi quy tắc hoặc định nghĩa, hãy ghi rõ nó đến từ đâu:

- Chuyên gia kể lại một trường hợp đã xảy ra.
- Người thực hiện mô tả thao tác hằng ngày.
- Người có thẩm quyền giải thích chính sách.
- Một biểu mẫu hoặc hồ sơ minh họa.
- Một giả thuyết chưa được xác nhận.

Cách ghi này giúp đội phát triển phân biệt dữ kiện với suy luận. Nếu hai chuyên gia đưa ra câu trả lời khác nhau, đừng tự chọn một câu trả lời có vẻ hợp lý hơn. Hãy ghi lại vai trò, điều kiện và phạm vi mà mỗi người đang đề cập, sau đó tìm hiểu xem có khác biệt về chính sách hoặc bounded context hay không.

### 7.2. Không đồng nhất nghiệp vụ với cách triển khai hiện tại

Chuyên gia có thể mô tả một thao tác theo tên màn hình, nút bấm hoặc bước trong phần mềm đang dùng. Hãy hỏi mục đích nghiệp vụ của thao tác đó.

Ví dụ, “bấm nút chuyển trạng thái” chưa cho biết doanh nghiệp đang xác nhận điều gì. Có thể đó là xác nhận hàng đã được đóng gói, xác nhận đã bàn giao hoặc chỉ là cập nhật tiến độ nội bộ. Những ý nghĩa này khác nhau dù giao diện hiện tại có thể dùng một nút chung.

Cần hiểu cam kết và kết quả nghiệp vụ trước khi quyết định cách biểu diễn chúng trong phần mềm.

## 8. Xác nhận hiểu biết sau buổi phỏng vấn

Một buổi phỏng vấn tốt tạo ra giả thuyết và bằng chứng ban đầu. Để tránh xây dựng mô hình dựa trên cách hiểu của một cá nhân, hãy thực hiện các bước xác nhận:

1. **Dựng lại dòng thời gian.** Viết các bước theo thứ tự, nêu vai trò, quyết định và kết quả.
2. **Tách quy tắc khỏi ví dụ.** Ghi rõ điều gì là chính sách chung và điều gì chỉ đúng với trường hợp đã kể.
3. **Đối chiếu với trường hợp khác.** Hỏi một chuyên gia hoặc người thực hiện khác về trường hợp tương tự và những điều kiện làm kết quả thay đổi.
4. **Kiểm tra thuật ngữ.** Đọc lại các định nghĩa và ví dụ để phát hiện từ đa nghĩa hoặc cách gọi khác nhau.
5. **Đánh dấu điểm chưa rõ.** Ghi câu hỏi chưa có câu trả lời, người có thể xác nhận và bằng chứng cần tìm.
6. **Trả kết quả cho chuyên gia xem lại.** Nhờ họ sửa những chỗ diễn giải sai trước khi dùng ghi chú làm cơ sở mô hình hóa.

Nếu có mâu thuẫn, hãy tìm nguyên nhân trước khi hợp nhất câu trả lời. Có thể hai người đang nói về hai loại giao dịch, hai thời điểm hoặc hai phạm vi trách nhiệm khác nhau. Trong DDD, khác biệt đó có thể là tín hiệu để khám phá ranh giới của một bounded context.

## 9. Những lỗi thường gặp khi phỏng vấn

### Chỉ hỏi về quy trình lý tưởng

Quy trình lý tưởng không thể hiện hết những gì nhân viên phải làm khi dữ liệu thiếu, khách thay đổi yêu cầu hoặc hệ thống bên ngoài gặp sự cố. Hãy yêu cầu một trường hợp thực tế và hỏi thêm một tình huống ngoại lệ.

### Đưa giải pháp vào câu hỏi

Câu hỏi như “Có nên tự động hủy đơn khi thiếu hàng không?” đã gợi ý một giải pháp. Hãy hỏi “Khi thiếu hàng, doanh nghiệp quyết định tiếp tục hay hủy đơn dựa trên điều kiện nào?” để khám phá quy tắc trước.

### Chấp nhận câu trả lời “thông thường”

“Thông thường” có thể che giấu nhiều nhánh nghiệp vụ. Hãy hỏi tiếp: “Có trường hợp nào không làm theo cách đó không?”, “Lần gần nhất ngoại lệ xảy ra là khi nào?” và “Ai quyết định cách xử lý?”.

### Chỉ phỏng vấn một vai trò

Một người có thể hiểu rõ bước của mình nhưng không biết cam kết của bộ phận trước hoặc điều kiện của bộ phận sau. Hãy xác minh những điểm bàn giao với các vai trò liên quan.

### Nhầm cách làm hiện tại với quy tắc nghiệp vụ

Một nhân viên có thể đang dùng bảng tính hoặc gọi điện để xử lý vì hệ thống hiện tại thiếu chức năng. Đừng mặc định thao tác đó là quy tắc bắt buộc. Hãy hỏi vì sao phải thực hiện và kết quả nào doanh nghiệp cần bảo đảm.

### Vội đặt tên cho mô hình

Ghi chú phỏng vấn có thể chứa nhiều danh từ và động từ hấp dẫn, nhưng chưa đủ để kết luận chúng là Entity, Value Object, Aggregate hay Domain Event. Trước tiên hãy hiểu định nghĩa, danh tính, vòng đời và quy tắc liên quan.

### Không xác nhận lại cách hiểu

Ghi chú của người phỏng vấn có thể bỏ sót điều kiện hoặc diễn giải sai thuật ngữ. Hãy tóm tắt cho chuyên gia xác nhận và lưu lại những chỗ họ chỉnh sửa.

## 10. Mẫu ghi chú cho một buổi phỏng vấn

Có thể sử dụng mẫu sau để giữ cho các cuộc phỏng vấn nhất quán mà vẫn linh hoạt theo từng chủ đề.

### Thông tin buổi phỏng vấn

| Mục | Nội dung |
|---|---|
| Chủ đề | Phạm vi nghiệp vụ cần khám phá |
| Người tham gia | Vai trò và trách nhiệm liên quan |
| Mục tiêu | Câu hỏi chính cần trả lời |
| Tình huống được chọn | Mô tả ngắn trường hợp thực tế |
| Thời điểm và bối cảnh | Khi nào, ở đâu, điều kiện nào |
| Nguồn tham chiếu | Hồ sơ hoặc tài liệu được phép sử dụng |

### Dòng thời gian tình huống

| Thứ tự | Sự việc / tác nhân | Hành động hoặc quyết định | Điều kiện / quy tắc | Kết quả |
|---:|---|---|---|---|
| 1 | Ai hoặc điều gì khởi đầu? | Hành động đầu tiên là gì? | Điều kiện bắt đầu? | Điều gì được ghi nhận? |
| 2 | Ai tiếp nhận? | Họ kiểm tra hoặc quyết định gì? | Quy tắc nào áp dụng? | Kết quả nào xuất hiện? |
| 3 | Ai xử lý tiếp? | Có lựa chọn nào? | Điều kiện để chọn? | Trách nhiệm chuyển cho ai? |

### Quy tắc và ngoại lệ

| Quy tắc cần xác minh | Bằng chứng / ví dụ | Ngoại lệ | Người xác nhận | Trạng thái hiểu biết |
|---|---|---|---|---|
| Điều kiện để nghiệp vụ được phép thực hiện | Tình huống đã xảy ra | Trường hợp làm thay đổi kết quả | Vai trò có thẩm quyền | Đã xác nhận / Cần hỏi thêm |

### Ngôn ngữ miền

| Thuật ngữ | Định nghĩa tạm thời | Ví dụ | Thuật ngữ dễ nhầm | Câu hỏi còn mở |
|---|---|---|---|---|
| Từ chuyên gia sử dụng | Ý nghĩa trong phạm vi đang khám phá | Trường hợp thể hiện đúng nghĩa | Từ có thể bị hiểu giống | Điều cần xác minh |

### Câu hỏi còn mở và mức độ tin cậy

Với mỗi điểm chưa rõ, ghi:

- Câu hỏi cần trả lời.
- Vì sao câu trả lời ảnh hưởng đến mô hình.
- Ai có thể xác nhận.
- Cần tình huống hoặc bằng chứng nào.
- Kết luận hiện tại là dữ kiện đã xác nhận, giả thuyết hay suy luận.

Mẫu ghi chú không nhằm tạo ra tài liệu dài nhất có thể. Nó giúp đội phát triển giữ được mối liên hệ giữa câu chuyện thực tế, quy tắc được phát hiện và quyết định mô hình hóa về sau.

## 11. Bộ câu hỏi gợi ý có thể dùng ngay

**Để bắt đầu từ sự việc**

- Anh/chị có thể kể một trường hợp gần đây không?
- Sự việc bắt đầu từ đâu và ai là người đầu tiên tham gia?
- Kết quả cuối cùng của trường hợp đó là gì?

**Để dựng lại quy trình**

- Điều gì xảy ra ngay trước bước này?
- Ai tiếp nhận kết quả sau bước này?
- Thông tin nào được dùng để quyết định?
- Có bước nào được thực hiện ngoài quy trình thông thường không?

**Để khám phá quy tắc**

- Điều kiện nào bắt buộc phải đúng?
- Ai có quyền quyết định?
- Trường hợp nào bị từ chối?
- Có ngoại lệ nào và ai được phép chấp thuận ngoại lệ?
- Quyết định này có thể thay đổi sau đó không?

**Để khám phá trường hợp biên và thất bại**

- Nếu thiếu một thông tin thì sao?
- Nếu hai yêu cầu xảy ra cùng lúc thì sao?
- Nếu bước tiếp theo không thể thực hiện thì ai xử lý?
- Nếu kết quả được ghi nhận sai thì có thể sửa bằng cách nào?

**Để làm rõ ngôn ngữ**

- Khi nói “hoàn tất”, anh/chị đang xác nhận điều gì?
- Có trường hợp nào được gọi bằng một tên khác không?
- Thuật ngữ này có cùng ý nghĩa ở bộ phận khác không?
- Một trường hợp nào trông giống nhưng thực ra không thuộc khái niệm này?

**Để xác nhận hiểu biết**

- Tôi tóm tắt như vậy đã đúng chưa?
- Có điều kiện nào tôi bỏ sót không?
- Nếu đổi điều kiện này, kết quả có thay đổi không?
- Ai khác nên xác nhận quy tắc này?

## Kết luận

Phỏng vấn chuyên gia bằng tình huống và ví dụ nghiệp vụ cụ thể giúp đội phát triển đi từ mô tả khái quát đến những quyết định và quy tắc thực sự chi phối hoạt động của doanh nghiệp. Bắt đầu bằng một trường hợp có thật, dựng lại dòng thời gian, tìm hiểu lý do của từng quyết định, kiểm tra ngoại lệ và xác nhận thuật ngữ sẽ tạo ra hiểu biết có thể kiểm chứng.

Trong DDD, chất lượng mô hình miền phụ thuộc vào chất lượng hiểu biết về miền. Ghi chú phỏng vấn cần giữ được câu chuyện, bằng chứng, quy tắc, ngôn ngữ và những điểm còn chưa rõ. Khi chuyên gia và đội phát triển cùng xác nhận được các thông tin đó, họ có nền tảng tốt hơn để xây dựng mô hình và ngôn ngữ chung phản ánh đúng nghiệp vụ.

