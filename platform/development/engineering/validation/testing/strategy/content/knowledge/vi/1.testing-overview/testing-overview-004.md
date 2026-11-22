# Phân biệt kiểm chứng kỹ thuật (verification) và xác nhận nhu cầu sử dụng (validation)

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, hai câu hỏi cần được trả lời xuyên suốt quá trình phát triển là: **chúng ta có xây dựng sản phẩm đúng theo những gì đã đặc tả không**, và **sản phẩm đó có thực sự giải quyết đúng nhu cầu của người sử dụng không**. Câu hỏi thứ nhất thuộc về *verification* (kiểm chứng); câu hỏi thứ hai thuộc về *validation* (xác nhận).

Hai hoạt động có liên quan chặt chẽ, thường dùng chung bằng chứng và có thể diễn ra song song. Tuy vậy, chúng đánh giá hai khía cạnh khác nhau. Một sản phẩm có thể vượt qua toàn bộ kiểm thử theo đặc tả nhưng vẫn không hữu ích trong công việc thực tế. Ngược lại, một ý tưởng có thể được người dùng đánh giá cao nhưng phần triển khai vẫn sai, thiếu ổn định hoặc không đáp ứng yêu cầu kỹ thuật. Chiến lược kiểm thử tốt cần có bằng chứng cho cả hai câu hỏi.

## 1. Hai khái niệm cốt lõi

### Verification — kiểm chứng sản phẩm có đúng với đặc tả

Verification đánh giá các sản phẩm công việc trong quá trình phát triển để xác định chúng có tuân thủ yêu cầu, thiết kế, hợp đồng giao tiếp, tiêu chuẩn và quy tắc đã thống nhất hay không.

Câu hỏi trọng tâm:

> Chúng ta có xây dựng sản phẩm đúng theo yêu cầu và thiết kế đã được xác định không?

Đối tượng được kiểm chứng không chỉ là phần mềm đã chạy. Có thể kiểm chứng tài liệu yêu cầu, mô hình dữ liệu, kiến trúc, thiết kế giao diện, mã nguồn, cấu hình triển khai, API và cả bộ kiểm thử. Ví dụ:

- Rà soát tài liệu để phát hiện yêu cầu mâu thuẫn, thiếu điều kiện biên hoặc không thể kiểm thử.
- Kiểm tra thiết kế API có đúng hợp đồng đã công bố hay không.
- Chạy kiểm thử đơn vị để xác nhận hàm tính phí xử lý đúng các trường hợp đã đặc tả.
- Chạy kiểm thử tích hợp để xác nhận hai dịch vụ trao đổi dữ liệu theo đúng schema và quy tắc lỗi.
- Dùng phân tích tĩnh để tìm lỗi kiểu dữ liệu, đường đi nguy hiểm hoặc vi phạm quy tắc mã nguồn.
- Kiểm tra cấu hình bảo mật, quyền truy cập và thông số triển khai so với baseline đã phê duyệt.

Verification có thể dùng kỹ thuật tĩnh như review, inspection, phân tích tĩnh; hoặc kỹ thuật động như chạy test. Vì vậy, không nên đồng nhất verification với “kiểm thử bằng cách chạy chương trình”.

### Validation — xác nhận sản phẩm phù hợp với nhu cầu và mục đích sử dụng

Validation đánh giá sản phẩm hoặc giải pháp trong bối cảnh sử dụng dự kiến để xác định nó có giải quyết đúng vấn đề của người dùng và các bên liên quan hay không.

Câu hỏi trọng tâm:

> Chúng ta có xây dựng đúng sản phẩm mà người dùng cần, và họ có thể sử dụng nó hiệu quả trong hoàn cảnh thực tế không?

Validation xem xét mục đích, quy trình làm việc, môi trường, người dùng và kết quả mong muốn. Ví dụ:

- Trao đổi với người dùng để kiểm tra giả định về vấn đề cần giải quyết trước khi chốt yêu cầu.
- Cho người dùng thực hiện tác vụ trên prototype để tìm hiểu liệu luồng thao tác có dễ hiểu hay không.
- Thực hiện kiểm thử chấp nhận với kịch bản gần với công việc thực tế.
- Chạy pilot hoặc beta trong môi trường đại diện để quan sát vấn đề phát sinh khi sử dụng.
- Đo tỷ lệ hoàn thành tác vụ, thời gian xử lý, tỷ lệ bỏ dở, số yêu cầu hỗ trợ hoặc kết quả nghiệp vụ sau triển khai.

Validation không chỉ là hỏi người dùng “có thích sản phẩm không”. Cần xác định trước mục tiêu sử dụng và thu thập bằng chứng phù hợp, chẳng hạn người dùng có hoàn thành tác vụ chính xác, an toàn và trong thời gian chấp nhận được hay không.

## 2. So sánh verification và validation

| Khía cạnh | Verification — kiểm chứng | Validation — xác nhận |
|---|---|---|
| Trọng tâm | Sự phù hợp với yêu cầu, thiết kế và tiêu chuẩn đã xác định | Sự phù hợp với nhu cầu, mục đích và bối cảnh sử dụng |
| Câu hỏi | Sản phẩm có được xây dựng đúng theo đặc tả không? | Đặc tả và sản phẩm có giải quyết đúng vấn đề không? |
| Tiêu chí | Yêu cầu kỹ thuật, quy tắc, hợp đồng, tiêu chuẩn, tiêu chí chấp nhận đã ghi rõ | Mục tiêu người dùng, quy trình thực tế, kết quả nghiệp vụ, mức độ phù hợp và khả năng sử dụng |
| Đối tượng tham gia thường gặp | Kỹ sư, tester, kiến trúc sư, người review, chuyên gia bảo mật hoặc vận hành | Người dùng đại diện, khách hàng, chủ sản phẩm, chuyên gia nghiệp vụ, vận hành và các bên liên quan |
| Thời điểm | Từ lúc hình thành yêu cầu và thiết kế đến khi triển khai | Có thể bắt đầu từ lúc khám phá nhu cầu, qua prototype, bản chạy thử và sau khi phát hành |
| Phương pháp | Review, inspection, phân tích tĩnh, kiểm thử đơn vị/tích hợp/hệ thống, kiểm tra hợp đồng | Phỏng vấn, quan sát tác vụ, thử nghiệm prototype, UAT, pilot, beta, thử nghiệm tại hiện trường, đo lường kết quả |
| Bằng chứng | Biên bản review, báo cáo phân tích, kết quả test, log, độ bao phủ truy vết | Kết quả tác vụ, phản hồi có ngữ cảnh, dữ liệu sử dụng, chỉ số nghiệp vụ, xác nhận của bên liên quan |
| Khi thất bại | Có sai lệch so với điều đã quy định hoặc thiết kế | Sản phẩm không đáp ứng nhu cầu, giả định hoặc điều kiện sử dụng thực tế |

Các hàng trong bảng mô tả trọng tâm điển hình, không phải ranh giới tuyệt đối. Ví dụ, một bài kiểm thử chấp nhận có thể đồng thời kiểm tra tiêu chí đã ghi trong yêu cầu (verification) và đánh giá liệu quy trình có dùng được trong công việc thật (validation). Hãy phân loại theo **mục tiêu và câu hỏi mà bằng chứng đang trả lời**, không chỉ theo tên loại test hoặc người thực hiện.

## 3. Không nhầm lẫn với các cặp khái niệm khác

### Không phải đơn giản là “tĩnh” và “động”

Review tài liệu hoặc phân tích tĩnh thường cung cấp bằng chứng verification, nhưng validation cũng có thể bắt đầu trước khi có phần mềm hoàn chỉnh. Một prototype, bản phác thảo quy trình hoặc mô hình tương tác có thể giúp người dùng xác nhận sớm rằng hướng giải quyết phù hợp.

Ngược lại, chạy chương trình không tự động biến một hoạt động thành validation. Một bài test chạy trên môi trường kiểm thử nhưng chỉ so sánh kết quả tính toán với đặc tả vẫn chủ yếu là verification.

### Không phải chỉ là “nội bộ” và “bên ngoài”

Kỹ sư có thể tham gia validation khi họ quan sát người dùng và kiểm tra giả định về quy trình. Người dùng hoặc chuyên gia nghiệp vụ cũng có thể tham gia verification khi cùng rà soát tiêu chí chấp nhận. Vai trò tham gia có thể giao nhau; mục đích đánh giá mới là điểm phân biệt.

### Không phải hai giai đoạn tách biệt, làm xong cái này mới đến cái kia

Verification và validation diễn ra lặp lại trong suốt vòng đời sản phẩm. Một yêu cầu mới cần được xác nhận là đúng nhu cầu, sau đó được kiểm chứng về tính rõ ràng và khả năng thực hiện. Khi có bản triển khai, nhóm tiếp tục kiểm chứng hành vi theo yêu cầu và xác nhận trải nghiệm trong kịch bản sử dụng. Phản hồi validation có thể làm thay đổi yêu cầu, từ đó tạo ra vòng verification mới.

## 4. Ví dụ xuyên suốt: quy trình thanh toán của cửa hàng trực tuyến

Giả sử nhóm phát triển chức năng thanh toán cho một cửa hàng trực tuyến. Người mua cần đặt hàng nhanh, hiểu rõ số tiền phải trả và nhận được xác nhận đơn hàng đáng tin cậy.

### Bắt đầu từ nhu cầu và yêu cầu

Nhu cầu của người mua có thể được diễn đạt như sau: “Tôi muốn biết tổng số tiền và ngày giao dự kiến trước khi xác nhận mua, để có thể quyết định có đặt hàng hay không.” Đây là mô tả về nhu cầu sử dụng. Nhóm cần trao đổi với người mua và bộ phận vận hành để xác nhận các thông tin nào cần hiển thị, thời điểm nào cần hiển thị và ngoại lệ nào có thể xảy ra.

Từ nhu cầu đã được làm rõ, nhóm có thể viết yêu cầu cụ thể:

- Tổng tiền phải phản ánh giá sản phẩm, giảm giá, phí giao hàng và thuế theo quy tắc áp dụng.
- Trang xác nhận phải hiển thị phần phân rã các khoản tiền trước khi người mua gửi đơn.
- Hệ thống chỉ tạo một đơn hàng cho một yêu cầu thanh toán đã được xác nhận, kể cả khi trình duyệt gửi lại yêu cầu.
- Nếu cổng thanh toán không phản hồi, giao diện phải thông báo trạng thái rõ ràng và cho phép người mua kiểm tra lại mà không tạo đơn trùng.

### Bằng chứng verification

Nhóm thiết kế các phép kiểm tra để chứng minh triển khai đáp ứng các yêu cầu vừa nêu:

1. Kiểm thử đơn vị cho công thức tính tổng tiền: không giảm giá, có giảm giá, miễn phí giao hàng, thuế bằng không và các trường hợp làm tròn.
2. Kiểm thử biên cho số lượng, giá trị giảm tối đa, đơn hàng đạt ngưỡng miễn phí giao hàng và các giá trị không hợp lệ.
3. Kiểm thử tích hợp để xác nhận dữ liệu giá, tồn kho, vận chuyển và thanh toán được trao đổi đúng hợp đồng.
4. Gửi lặp cùng một yêu cầu thanh toán để xác nhận cơ chế idempotency không tạo đơn hàng trùng.
5. Mô phỏng timeout hoặc lỗi từ cổng thanh toán để kiểm tra trạng thái và thông báo theo đặc tả.
6. Đối chiếu nội dung hiển thị với quy tắc đã duyệt, gồm các khoản phí và thời điểm xuất hiện.

Nếu một đơn hàng có tổng tiền sai do hàm tính thuế dùng nhầm mức thuế, đó là lỗi verification: phần triển khai không tuân thủ quy tắc đã xác định.

### Bằng chứng validation

Nhóm mời người mua đại diện thực hiện các kịch bản gần với thực tế:

1. Thêm nhiều sản phẩm vào giỏ và áp dụng mã giảm giá.
2. Chọn địa chỉ giao hàng khác nhau để xem phí và thời gian giao dự kiến.
3. Kiểm tra tổng tiền, giải thích khoản giảm giá rồi quyết định có đặt hàng hay không.
4. Xử lý tình huống thanh toán chậm hoặc không rõ đã thành công hay chưa.

Nhóm quan sát xem người mua có tìm thấy thông tin cần thiết, hiểu tổng tiền, hoàn tất tác vụ và biết cách xử lý khi giao dịch gặp sự cố hay không. Có thể kết hợp quan sát với chỉ số như tỷ lệ hoàn tất thanh toán, tỷ lệ bỏ giỏ ở bước cuối, số lần liên hệ hỗ trợ và tỷ lệ đơn hàng cần xử lý thủ công.

Giả sử tất cả phép tính đều chính xác và mọi test đều pass, nhưng phí giao hàng chỉ xuất hiện sau khi người mua nhập thông tin thanh toán. Người mua thường bất ngờ và bỏ giỏ. Sản phẩm có thể đạt verification theo đặc tả hiện tại nhưng validation cho thấy trải nghiệm chưa đáp ứng nhu cầu minh bạch chi phí. Nhóm cần xem lại yêu cầu và thiết kế luồng, sau đó bổ sung kiểm chứng cho thay đổi.

Ví dụ này cho thấy một kết quả validation có thể chỉ ra rằng yêu cầu ban đầu chưa đúng hoặc chưa đầy đủ. Sửa mã nguồn không phải lúc nào cũng giải quyết được vấn đề; đôi khi cần sửa cách nhóm hiểu nhu cầu.

## 5. Kết hợp hai hoạt động trong chiến lược kiểm thử

Một chiến lược kiểm thử nên tạo được chuỗi liên kết từ nhu cầu đến yêu cầu, từ yêu cầu đến phép kiểm chứng, và từ mục tiêu sử dụng đến kịch bản xác nhận.

### Bước 1: Hiểu vấn đề và bối cảnh sử dụng

Xác định ai sẽ sử dụng sản phẩm, họ đang cố hoàn thành công việc gì, môi trường sử dụng ra sao, điều gì gây khó khăn và kết quả nào được xem là thành công. Tách biệt điều người dùng thực sự cần khỏi giải pháp mà nhóm đang giả định.

### Bước 2: Làm rõ yêu cầu và tiêu chí thành công

Chuyển nhu cầu thành yêu cầu có thể thảo luận và kiểm tra. Mỗi yêu cầu nên có phạm vi, điều kiện, dữ liệu liên quan, hành vi mong đợi và ngoại lệ. Đồng thời xác định kết quả sử dụng cần đạt, chẳng hạn tỷ lệ hoàn thành tác vụ, độ chính xác, thời gian xử lý hoặc khả năng tiếp cận.

### Bước 3: Lập truy vết hai chiều

Với mỗi yêu cầu quan trọng, ghi rõ bằng chứng verification dự kiến. Với mỗi mục tiêu sử dụng quan trọng, xác định kịch bản validation và cách thu thập bằng chứng. Truy vết hai chiều giúp phát hiện yêu cầu không có kiểm tra, test không gắn với nhu cầu, hoặc mục tiêu nghiệp vụ chưa được đánh giá.

| Nhu cầu / mục tiêu | Yêu cầu có thể kiểm chứng | Bằng chứng verification | Bằng chứng validation |
|---|---|---|---|
| Người mua biết tổng chi phí trước khi đặt | Hiển thị giá, giảm giá, phí giao hàng và thuế trước khi xác nhận | Test dữ liệu và quy tắc tính; kiểm tra nội dung và thời điểm hiển thị | Quan sát người mua tìm và giải thích tổng tiền trong kịch bản đặt hàng |
| Không phát sinh đơn trùng khi gửi lại yêu cầu | Cùng một khóa idempotency chỉ tạo một đơn hàng | Test gửi lặp, kiểm tra dữ liệu và log giao dịch | Thử nghiệm tình huống mạng chập chờn để xác nhận người mua hiểu trạng thái và tiếp tục được |
| Người mua hoàn tất thanh toán thuận tiện | Luồng thanh toán hỗ trợ các phương thức được công bố và xử lý lỗi theo quy định | Test tích hợp từng phương thức, timeout và các trạng thái lỗi | Đo tỷ lệ hoàn tất, thời gian thao tác và quan sát điểm người dùng bỏ dở |

### Bước 4: Chọn phương pháp theo rủi ro

Không phải mọi tính năng đều cần cùng một mức kiểm tra. Ưu tiên các luồng có tác động lớn đến người dùng, dữ liệu, an toàn, tiền bạc, tuân thủ hoặc hoạt động vận hành. Với rủi ro kỹ thuật, tăng cường review, phân tích tĩnh, kiểm thử tự động và kiểm thử tích hợp. Với rủi ro về nhu cầu hoặc trải nghiệm, tăng cường phỏng vấn, prototype, thử nghiệm tác vụ và pilot.

Ví dụ, một thay đổi về công thức tính thuế cần kiểm chứng kỹ tính đúng đắn và các trường hợp biên. Một thay đổi về thứ tự các bước thanh toán cần được xác nhận với người dùng sớm, vì đặc tả có thể đúng về mặt kỹ thuật nhưng làm quy trình khó hoàn thành.

### Bước 5: Thu thập bằng chứng sớm và lặp lại

Không chờ đến cuối dự án mới hỏi người dùng. Có thể xác nhận giả định bằng phỏng vấn hoặc prototype trước khi triển khai; kiểm chứng yêu cầu và thiết kế bằng review; kiểm chứng mã nguồn bằng test; sau đó xác nhận bản chạy được trong môi trường đại diện. Khi sản phẩm đã phát hành, tiếp tục theo dõi dữ liệu sử dụng và phản hồi để phát hiện nhu cầu mới hoặc tác động ngoài dự kiến.

### Bước 6: Phân loại phát hiện và xử lý đúng nguyên nhân

Khi có vấn đề, hãy xác định bằng chứng đang chỉ ra điều gì:

- Nếu kết quả thực tế khác yêu cầu đã thống nhất, điều tra lỗi triển khai, dữ liệu, cấu hình hoặc môi trường — đây thường là vấn đề verification.
- Nếu sản phẩm làm đúng yêu cầu nhưng người dùng vẫn không hoàn thành được công việc, xem lại giả định, yêu cầu, quy trình và bối cảnh — đây thường là vấn đề validation.
- Nếu yêu cầu mơ hồ hoặc mâu thuẫn, cần làm rõ và xác nhận lại yêu cầu trước khi kết luận sản phẩm đúng hay sai.

Một phát hiện có thể thuộc cả hai nhóm. Ví dụ, người dùng không thể hoàn tất một tác vụ vì yêu cầu đã bỏ sót một loại địa chỉ hợp lệ; điều này vừa bộc lộ thiếu sót trong yêu cầu, vừa tạo ra hành vi không phù hợp trong sản phẩm.

### Bước 7: Ra quyết định phát hành dựa trên cả hai loại bằng chứng

Điều kiện phát hành cần nêu rõ những yêu cầu nào phải được kiểm chứng, kịch bản sử dụng nào phải được xác nhận, rủi ro còn lại là gì và ai có thẩm quyền chấp nhận rủi ro. Một báo cáo “100% test pass” chỉ cho biết các test đã chạy đều đạt kết quả mong đợi; nó không chứng minh rằng test bao phủ đúng nhu cầu hoặc sản phẩm phù hợp với người dùng.

## 6. Chọn đúng loại bằng chứng cho từng câu hỏi

Một số ví dụ dưới đây giúp phân biệt mục đích của hoạt động kiểm tra:

| Tình huống | Verification | Validation |
|---|---|---|
| Tốc độ phản hồi | Đo và xác nhận API đáp ứng ngưỡng thời gian đã ghi trong yêu cầu dưới tải quy định | Quan sát độ trễ có làm gián đoạn công việc của người dùng trong điều kiện thực tế hay không |
| Khả năng tiếp cận | Kiểm tra tuân thủ các tiêu chí accessibility đã chọn, cấu trúc semantic và điều khiển bằng bàn phím | Cho người dùng có nhu cầu tiếp cận khác nhau thực hiện tác vụ và ghi nhận trở ngại thực tế |
| Phân quyền | Kiểm thử vai trò, quyền và các trường hợp truy cập trái phép theo ma trận quyền | Xác nhận nhân viên có thể hoàn thành công việc cần thiết mà không bị quy trình cấp quyền cản trở |
| Báo cáo nghiệp vụ | Đối chiếu công thức, bộ lọc và dữ liệu đầu ra với định nghĩa chỉ số | Xác nhận báo cáo giúp người quản lý trả lời câu hỏi và ra quyết định mà họ cần |
| Ứng dụng di động | Kiểm tra chức năng trên các phiên bản hệ điều hành và thiết bị nằm trong phạm vi hỗ trợ | Thử nghiệm trong điều kiện di chuyển, mạng yếu và thao tác một tay để xác nhận ứng dụng phù hợp với hoàn cảnh sử dụng |

Các chỉ số kỹ thuật như độ bao phủ mã nguồn, số lượng test pass hoặc số lỗi tìm thấy có giá trị cho verification, nhưng tự chúng không chứng minh validation. Tương tự, phản hồi tích cực của một vài người dùng không thay thế cho việc kiểm chứng tính chính xác, an toàn và độ tin cậy của hệ thống.

## 7. Những sai lầm thường gặp

**Chỉ kiểm thử theo yêu cầu đã viết.** Nếu yêu cầu sai, thiếu hoặc không phản ánh nhu cầu thật, nhóm có thể chứng minh một sản phẩm không phù hợp được triển khai rất chính xác. Hãy xác nhận yêu cầu với người có hiểu biết về công việc và người dùng đại diện.

**Coi UAT là bằng chứng duy nhất của validation.** UAT thường diễn ra gần giai đoạn bàn giao và có thể bị giới hạn bởi kịch bản đã viết. Phỏng vấn, quan sát, prototype và pilot từ sớm giúp phát hiện sai giả định trước khi chi phí sửa đổi tăng lên.

**Coi test pass là sản phẩm đã sẵn sàng.** Test chỉ chứng minh hành vi nằm trong phạm vi và điều kiện đã kiểm tra. Cần xem cả độ bao phủ yêu cầu, chất lượng dữ liệu, rủi ro chưa kiểm tra và kết quả sử dụng.

**Chỉ hỏi người dùng có hài lòng không.** Câu trả lời có thể chịu ảnh hưởng bởi kỳ vọng hoặc bối cảnh buổi thử nghiệm. Hãy kết hợp lời nói với quan sát tác vụ, lỗi thực tế và chỉ số kết quả.

**Để validation đến cuối dự án.** Khi người dùng phát hiện luồng công việc không phù hợp sau khi hệ thống đã hoàn thiện, thay đổi có thể tốn kém. Hãy kiểm tra giả định quan trọng bằng prototype và ví dụ cụ thể từ sớm.

**Không phân biệt lỗi triển khai với yêu cầu sai.** Nếu nhóm chỉ sửa mã nguồn trong khi vấn đề nằm ở cách hiểu nhu cầu, lỗi tương tự có thể lặp lại ở nhiều tính năng. Khi điều tra, luôn hỏi cả “đã làm đúng đặc tả chưa?” và “đặc tả có đúng với nhu cầu không?”.

## 8. Checklist áp dụng trong một dự án

Trước khi bắt đầu triển khai:

- [ ] Đã xác định người dùng, công việc họ cần hoàn thành và bối cảnh sử dụng.
- [ ] Các nhu cầu quan trọng đã được trao đổi và xác nhận với bên liên quan phù hợp.
- [ ] Yêu cầu có phạm vi, điều kiện, ngoại lệ và tiêu chí chấp nhận rõ ràng.
- [ ] Các mục tiêu sử dụng có cách quan sát hoặc đo lường kết quả.

Trong quá trình phát triển:

- [ ] Mỗi yêu cầu quan trọng có phương pháp verification và bằng chứng dự kiến.
- [ ] Mỗi mục tiêu sử dụng quan trọng có kịch bản validation phù hợp.
- [ ] Review và kiểm tra được thực hiện sớm trên yêu cầu, thiết kế, mã nguồn và cấu hình.
- [ ] Người dùng đại diện được tham gia khi cần kiểm tra prototype hoặc luồng nghiệp vụ.
- [ ] Phát hiện được phân loại theo sai lệch triển khai, thiếu sót yêu cầu hoặc vấn đề phù hợp với nhu cầu.

Trước và sau khi phát hành:

- [ ] Có bằng chứng cho các tiêu chí verification bắt buộc và các kịch bản validation trọng yếu.
- [ ] Rủi ro chưa được kiểm tra và giới hạn của bằng chứng đã được ghi nhận.
- [ ] Người có thẩm quyền đã xem xét và chấp nhận các rủi ro còn lại.
- [ ] Có kế hoạch theo dõi phản hồi, chỉ số sử dụng và vấn đề vận hành sau phát hành.

## 9. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Đặc tả yêu cầu màn hình đăng nhập khóa tài khoản sau năm lần nhập sai. Test tự động xác nhận tài khoản bị khóa đúng ở lần thứ năm. Đây là verification vì nhóm đang đối chiếu hành vi với quy tắc đã đặc tả. Nếu sau đó nhóm quan sát thấy người dùng hợp lệ thường bị khóa do bàn phím tự động điền mật khẩu cũ và không biết cách khôi phục, đó là bằng chứng validation cho thấy trải nghiệm khôi phục chưa phù hợp.

**Tình huống 2:** Người dùng yêu cầu báo cáo “doanh thu theo tháng”. Nhóm triển khai đúng công thức được ghi trong tài liệu, nhưng người quản lý thực tế cần phân biệt doanh thu ghi nhận với tiền đã thu. Test công thức hiện tại pass là bằng chứng verification; trao đổi nghiệp vụ cho thấy định nghĩa chỉ số chưa đúng là phát hiện validation. Nhóm cần thống nhất lại ý nghĩa chỉ số trước khi sửa báo cáo.

**Tình huống 3:** Một API đáp ứng ngưỡng 200 ms trong bài kiểm thử tải đã định nghĩa. Đây là verification cho yêu cầu hiệu năng. Nếu ứng dụng vẫn có cảm giác chậm vì giao diện chờ nhiều API tuần tự trước khi cho phép người dùng thao tác, cần đánh giá thêm trải nghiệm tổng thể; đó là câu hỏi validation.

Khi gặp một hoạt động kiểm thử mới, hãy tự hỏi: **bằng chứng này đang chứng minh sản phẩm tuân thủ điều đã quy định, hay đang chứng minh giải pháp phù hợp với nhu cầu sử dụng?** Nếu câu trả lời chưa rõ, hãy làm rõ mục tiêu và tiêu chí đánh giá trước khi chọn phương pháp.

## Kết luận

Verification giúp kiểm soát tính đúng đắn của sản phẩm so với yêu cầu và thiết kế. Validation giúp kiểm soát việc sản phẩm có giải quyết đúng vấn đề trong bối cảnh sử dụng hay không. Hai hoạt động bổ sung cho nhau: validation giúp nhóm xác định đúng điều cần xây dựng; verification giúp nhóm triển khai điều đó một cách chính xác và đáng tin cậy. Một chiến lược kiểm thử đầy đủ cần lập kế hoạch, thu thập bằng chứng và ra quyết định dựa trên cả hai.
