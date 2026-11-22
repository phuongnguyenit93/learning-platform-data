# Chia sẻ trách nhiệm khi dịch vụ hoặc nhóm khác thay đổi

## 1. Vì sao cần chia sẻ trách nhiệm khi có thay đổi liên dịch vụ?

Trong một hệ thống gồm nhiều dịch vụ, ứng dụng hoặc nhóm phát triển độc lập, thay đổi ở một thành phần có thể ảnh hưởng đến thành phần khác dù nhóm tạo thay đổi không sửa mã nguồn của bên kia. Một thay đổi schema, quy tắc xác thực, giới hạn tốc độ, cấu hình mạng, thứ tự sự kiện hoặc cách xử lý lỗi có thể làm consumer ngừng hoạt động, xử lý sai dữ liệu hoặc tạo ra sự cố dây chuyền.

Không một nhóm nào có thể tự mình bảo đảm toàn bộ hệ thống khi thay đổi vượt qua ranh giới sở hữu. Nhóm cung cấp dịch vụ hiểu implementation và khả năng vận hành của provider; nhóm tiêu thụ hiểu cách tích hợp và nhu cầu của consumer; nhóm nền tảng/vận hành hiểu môi trường và cơ chế phát hành; nhóm sản phẩm hiểu tác động đến người dùng và nghiệp vụ. Chất lượng phụ thuộc vào việc các bên trao đổi thông tin, xác nhận hợp đồng và cùng quản lý rủi ro.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, chia sẻ trách nhiệm không có nghĩa là mọi người cùng chịu một trách nhiệm mơ hồ. Mỗi bên cần có ranh giới sở hữu, nghĩa vụ phối hợp và quyền quyết định rõ ràng. Provider chịu trách nhiệm về cam kết và hành vi của dịch vụ mình; consumer chịu trách nhiệm sử dụng hợp đồng đúng cách và kiểm thử hành vi tích hợp của mình; các bên phối hợp đánh giá ảnh hưởng, chuẩn bị bằng chứng và xử lý sự cố xuyên ranh giới.

Mục tiêu của bài học là giúp nhóm tổ chức sự phối hợp đó khi một dịch vụ hoặc nhóm khác thay đổi: biết ai cần được thông báo, phân tích điều gì có thể bị ảnh hưởng, kiểm thử ở đâu, bằng chứng nào cần có, phát hành theo thứ tự nào và hành động ra sao khi thay đổi gây sự cố.

## 2. Xác định ranh giới sở hữu và trách nhiệm

### 2.1. Provider, consumer và chủ sở hữu nền tảng

Trong một tương tác dịch vụ:

- **Provider (bên cung cấp)** sở hữu dịch vụ hoặc giao diện được cung cấp. Provider quản lý implementation, hợp đồng công bố, phiên bản, thay đổi, khả năng tương thích, giám sát và thông báo về dịch vụ.
- **Consumer (bên tiêu thụ)** gọi API, nhận sự kiện hoặc phụ thuộc vào hành vi của provider. Consumer quản lý cách tích hợp, giả định được sử dụng, xử lý lỗi, retry, timeout, dữ liệu và khả năng tương thích trong ứng dụng của mình.
- **Platform/Operations/SRE** quản lý hoặc hỗ trợ hạ tầng, mạng, gateway, pipeline, quan sát, triển khai, phân quyền và quy trình ứng phó vận hành theo mô hình tổ chức.
- **Product/Business owner** xác định hành trình và tác động nghiệp vụ, ưu tiên công việc, thông báo khách hàng và chấp nhận rủi ro kinh doanh trong thẩm quyền.
- **Security/Data/Compliance** tư vấn hoặc quyết định các yêu cầu thuộc phạm vi bảo mật, quyền riêng tư, dữ liệu và tuân thủ.

Một nhóm có thể đồng thời là provider của dịch vụ này và consumer của dịch vụ khác. Ranh giới cần được xác định theo từng giao diện, không chỉ theo sơ đồ tổ chức.

### 2.2. Những gì provider cần chịu trách nhiệm

Provider thường có trách nhiệm:

- Duy trì hợp đồng API, schema sự kiện, tài liệu ngữ nghĩa và chính sách phiên bản.
- Thông báo thay đổi có khả năng ảnh hưởng consumer theo quy trình và thời hạn đã thống nhất.
- Đánh giá tác động của thay đổi đến các consumer đã biết và các tích hợp được hỗ trợ.
- Cung cấp môi trường, dữ liệu thử nghiệm, sandbox hoặc cơ chế xác minh phù hợp khi có thể.
- Chạy kiểm thử provider, contract verification, kiểm thử hồi quy và kiểm thử phi chức năng liên quan.
- Nêu rõ giới hạn tương thích, thời gian hỗ trợ, thời điểm ngừng cung cấp và phương án chuyển đổi.
- Cung cấp thông tin phiên bản, trạng thái triển khai, metric, log và hướng dẫn xử lý sự cố trong phạm vi được phép.
- Duy trì khả năng rollback hoặc biện pháp khắc phục tương ứng với loại thay đổi.

Provider không thể khẳng định consumer sẽ hoạt động đúng trong mọi tình huống chỉ dựa trên kiểm thử nội bộ. Provider cần cung cấp bằng chứng về hợp đồng và hành vi đã cam kết; consumer vẫn phải xác nhận tích hợp trong bối cảnh sử dụng của mình.

### 2.3. Những gì consumer cần chịu trách nhiệm

Consumer thường có trách nhiệm:

- Theo dõi thông báo và tài liệu thay đổi của provider mà mình phụ thuộc.
- Chỉ dựa vào phần hợp đồng đã công bố, tránh phụ thuộc vào chi tiết implementation không được cam kết.
- Duy trì kiểm thử consumer contract hoặc kiểm thử tương đương cho các tương tác quan trọng.
- Xử lý đúng timeout, lỗi, retry, rate limit, sự kiện lặp và phiên bản được hỗ trợ.
- Đánh giá ảnh hưởng đến dữ liệu, luồng nghiệp vụ, trải nghiệm và các dịch vụ phía sau.
- Kiểm thử phiên bản mới trong môi trường phù hợp và báo kết quả cho provider trước khi chuyển đổi nếu có rủi ro.
- Triển khai nâng cấp theo kế hoạch, theo dõi chỉ báo sau phát hành và có phương án giảm thiểu khi không tương thích.
- Thông báo ngược cho provider về lỗi, giả định chưa được đáp ứng hoặc nhu cầu hợp đồng mới.

Consumer không nên kỳ vọng provider giữ vĩnh viễn mọi hành vi không được ghi trong hợp đồng. Nếu consumer đang dựa vào một hành vi chưa được cam kết nhưng quan trọng, cần trao đổi để biến nó thành yêu cầu có chủ sở hữu và được xác nhận.

### 2.4. Trách nhiệm chung tại ranh giới

Provider và consumer cần cùng thống nhất:

- Ai là đầu mối kỹ thuật và đầu mối nghiệp vụ của mỗi bên.
- Hợp đồng nào là nguồn thông tin chính thức và cách quản lý phiên bản.
- Cách thông báo, đánh giá và phê duyệt thay đổi.
- Bộ kiểm thử hợp đồng, dữ liệu và môi trường phối hợp.
- Điều kiện tương thích trong giai đoạn triển khai chuyển tiếp.
- Chỉ báo theo dõi, ngưỡng dừng, rollback và quy trình sự cố.
- Thời gian hỗ trợ và cách ngừng một giao diện cũ.

Trách nhiệm chung tập trung vào giao diện và rủi ro liên hệ thống. Nó không xóa ranh giới sở hữu của từng nhóm.

## 3. Phân tích ảnh hưởng trước khi thay đổi

### 3.1. Lập bản đồ phụ thuộc

Trước khi sửa một dịch vụ có consumer khác, provider cần biết ai đang sử dụng giao diện đó. Bản đồ phụ thuộc có thể gồm:

- Dịch vụ hoặc ứng dụng tiêu thụ trực tiếp.
- Consumer gián tiếp thông qua gateway, adapter, event bus hoặc một dịch vụ trung gian.
- Batch job, báo cáo, data pipeline, webhook và công cụ nội bộ.
- Phiên bản client, SDK, schema hoặc message còn đang được hỗ trợ.
- Nhóm sở hữu từng consumer và môi trường triển khai.

Không nên chỉ dựa vào sơ đồ kiến trúc tĩnh. Cần kết hợp registry dịch vụ, catalog API, hợp đồng đã xuất bản, log truy cập, metric theo client, cấu hình gateway và xác nhận từ nhóm sở hữu. Một consumer ít hoạt động hoặc chạy theo lịch có thể không xuất hiện trong mẫu quan sát ngắn.

### 3.2. Phân loại mức độ ảnh hưởng

Với mỗi thay đổi, đánh giá tác động theo nhiều chiều:

| Chiều ảnh hưởng | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Cấu trúc giao diện | Endpoint, field, kiểu dữ liệu, header hoặc schema có thay đổi không? | Đổi `customerId` từ chuỗi sang số |
| Ngữ nghĩa nghiệp vụ | Ý nghĩa, đơn vị, quy tắc hoặc trạng thái có thay đổi không? | `amount` chuyển từ đơn vị đồng sang xu |
| Xác thực và quyền | Credential, scope, vai trò hoặc chính sách truy cập có đổi không? | Bổ sung scope bắt buộc cho API đọc hồ sơ |
| Lỗi và khả năng phục hồi | Mã lỗi, timeout, retry, rate limit hoặc hành vi fallback có đổi không? | Provider bắt đầu trả 429 khi vượt ngưỡng mới |
| Dữ liệu và sự kiện | Schema, thứ tự, tần suất, tính duy nhất hoặc thời gian lưu có đổi không? | Event mới được gửi trước event xác nhận cũ |
| Phi chức năng | Độ trễ, thông lượng, giới hạn payload hoặc tính sẵn sàng có thay đổi không? | Thời gian phản hồi p95 tăng do truy vấn mới |
| Triển khai và vận hành | Cấu hình, mạng, chứng chỉ, lịch bảo trì hoặc khả năng rollback có đổi không? | Gateway chuyển sang yêu cầu TLS phiên bản mới |
| Hành trình nghiệp vụ | Luồng nào của người dùng bị ảnh hưởng nếu consumer lỗi? | Thanh toán không thể xác nhận đơn hàng |

Một thay đổi có thể tương thích về schema nhưng phá vỡ ngữ nghĩa. Ví dụ, provider vẫn trả `status` dạng chuỗi nhưng đổi cách diễn giải `PENDING` để bao gồm cả giao dịch đã gửi đến ngân hàng và giao dịch đang chờ xác nhận. Consumer có thể hiểu sai trạng thái dù contract test cấu trúc vẫn đạt.

### 3.3. Phân tích thay đổi theo phạm vi

Với từng consumer, xác định:

1. Giao diện hoặc hành vi nào consumer đang sử dụng.
2. Consumer dùng dữ liệu đó cho quy tắc hoặc hành trình nào.
3. Thay đổi có ảnh hưởng trực tiếp, gián tiếp hay không ảnh hưởng.
4. Có cần sửa mã, cấu hình, dữ liệu, quyền hoặc lịch chạy không.
5. Kiểm thử nào cần chạy và ai cung cấp môi trường/bằng chứng.
6. Có thể triển khai độc lập hay cần thứ tự phối hợp.
7. Tác động nếu consumer chưa nâng cấp đúng thời điểm.

Kết quả phân tích nên phân loại ít nhất: không ảnh hưởng có căn cứ, tương thích cần xác minh, cần hành động từ consumer, hoặc thay đổi phá vỡ tương thích cần kế hoạch chuyển đổi. Không kết luận “không ảnh hưởng” chỉ vì không thấy lỗi trong một lần chạy.

### 3.4. Đánh giá rủi ro và ưu tiên

Ưu tiên dựa trên hậu quả, khả năng xảy ra, mức phơi nhiễm và khả năng phát hiện/khôi phục. Các thay đổi liên quan đến tiền, dữ liệu cá nhân, phân quyền, trạng thái giao dịch, an toàn hoặc nghĩa vụ tuân thủ cần được xem xét kỹ hơn.

Có thể dùng phân loại sau để điều phối:

| Mức thay đổi | Dấu hiệu | Phối hợp tối thiểu |
|---|---|---|
| Thấp | Nội bộ implementation, không đổi hợp đồng hoặc hành vi được cam kết; có bằng chứng kiểm thử | Provider review và kiểm thử hồi quy phù hợp |
| Trung bình | Mở rộng tương thích, thay đổi hiệu năng hoặc cấu hình có thể ảnh hưởng một số consumer | Thông báo consumer liên quan, contract test và kiểm thử tích hợp chọn lọc |
| Cao | Thay đổi ngữ nghĩa, xác thực, schema, giới hạn hoặc hành vi lỗi có ảnh hưởng nhiều consumer | Phân tích ảnh hưởng liên nhóm, kế hoạch chuyển đổi, kiểm thử phối hợp và phê duyệt phát hành |
| Nghiêm trọng | Breaking change hoặc rủi ro lớn với dữ liệu, tiền, bảo mật, tuân thủ hay tính sẵn sàng | Quyết định liên chức năng, cổng phát hành bắt buộc, phương án rollback/khắc phục và truyền thông rõ ràng |

Đây là thang tham khảo. Tổ chức cần định nghĩa tiêu chí theo sản phẩm. Yêu cầu bắt buộc về bảo mật hoặc tuân thủ không được hạ mức chỉ vì phạm vi consumer nhỏ.

## 4. Phối hợp giữa consumer và provider

### 4.1. Thiết lập đầu mối và kênh làm việc

Mỗi dịch vụ quan trọng nên có thông tin chủ sở hữu kỹ thuật, đầu mối vận hành và kênh hỗ trợ. Consumer cần biết nơi tìm hợp đồng, changelog, lịch bảo trì và trạng thái dịch vụ. Provider cần biết nhóm nào phụ thuộc và cách liên hệ khi phát hiện lỗi tương thích.

Với thay đổi có ảnh hưởng lớn, nên có một buổi review ngắn giữa các nhóm để thống nhất phạm vi, giả định, tiêu chí kiểm thử, dữ liệu, lịch triển khai và cách ứng phó. Các quyết định cần được ghi lại trong hệ thống quản lý công việc hoặc tài liệu kỹ thuật mà các bên có thể truy cập.

### 4.2. Thỏa thuận trước khi triển khai thay đổi

Trước khi phát hành, các bên cần trả lời:

- Hợp đồng hoặc hành vi nào thay đổi?
- Consumer nào bị ảnh hưởng và ai đã xác nhận?
- Phiên bản cũ có tiếp tục được hỗ trợ không, trong bao lâu?
- Consumer cần thay đổi mã, cấu hình, dữ liệu hoặc quyền nào?
- Kiểm thử nào do provider chạy, kiểm thử nào do consumer chạy và kiểm thử nào cần chạy chung?
- Có môi trường sandbox hoặc môi trường tích hợp phù hợp không?
- Bằng chứng nào là điều kiện để chuyển sang bước triển khai?
- Ngưỡng nào khiến dừng mở rộng hoặc rollback?
- Ai ra quyết định khi các bên không thống nhất hoặc phát hiện rủi ro mới?

Không nên đợi đến ngày phát hành mới mời consumer kiểm thử một thay đổi đã được phát triển xong. Tham gia sớm giúp consumer phát hiện giả định sai và provider điều chỉnh hợp đồng trước khi chi phí thay đổi tăng.

### 4.3. Consumer-driven contract và provider verification

Consumer-driven contract ghi nhận những tương tác mà consumer thực sự cần. Consumer tạo kỳ vọng về request/response hoặc message, sau đó provider xác minh implementation của mình đáp ứng các hợp đồng đang có hiệu lực.

Provider cũng có thể công bố hợp đồng chuẩn như OpenAPI, AsyncAPI hoặc schema sự kiện. Consumer sử dụng hợp đồng đó để kiểm tra cách tích hợp và phát hiện thay đổi không tương thích.

Hai cách tiếp cận có thể kết hợp: hợp đồng do provider quản lý xác định giao diện chính thức; hợp đồng do consumer đóng góp phản ánh nhu cầu cụ thể của từng bên tiêu thụ. Các hợp đồng phải được phiên bản hóa, review và gắn với đúng phiên bản provider/consumer.

Contract test không thay thế kiểm thử tích hợp thật. Các bên vẫn cần xác nhận những rủi ro liên quan đến mạng, cấu hình, quyền, dữ liệu, thứ tự sự kiện, timeout và tác dụng phụ mà hợp đồng không thể bao phủ đầy đủ.

## 5. Thông báo và quản lý thay đổi

### 5.1. Thông tin cần có trong thông báo thay đổi

Một thông báo thay đổi hữu ích nên bao gồm:

- Tên dịch vụ, giao diện và chủ sở hữu thay đổi.
- Phiên bản hiện tại và phiên bản dự kiến.
- Mô tả trước/sau, gồm thay đổi schema, ngữ nghĩa, lỗi, bảo mật và phi chức năng.
- Phân loại mức độ tương thích và lý do.
- Consumer hoặc nhóm có khả năng bị ảnh hưởng.
- Việc consumer cần làm, ví dụ cập nhật client, scope, schema hoặc cấu hình.
- Môi trường và thời điểm có thể kiểm thử.
- Ngày dự kiến phát hành, thời gian hỗ trợ song song và ngày ngừng hỗ trợ nếu có.
- Bằng chứng kiểm thử đã có và các giới hạn còn lại.
- Kế hoạch triển khai, rollback hoặc khắc phục.
- Đầu mối liên hệ và kênh báo vấn đề.

Thông báo không nên chỉ ghi “API đã cập nhật”. Consumer cần hiểu điều gì thay đổi, họ có phải hành động hay không và hạn chót là khi nào.

### 5.2. Chọn thời điểm thông báo

Thời gian báo trước cần tương xứng với mức ảnh hưởng và khả năng nâng cấp của consumer. Thay đổi nội bộ không ảnh hưởng hợp đồng có thể được thông báo qua changelog hoặc kênh kỹ thuật thông thường. Thay đổi breaking cần thời gian đủ để consumer đánh giá, sửa đổi, kiểm thử, phê duyệt và triển khai.

Nếu có chính sách hỗ trợ phiên bản hoặc SLA thông báo thay đổi, phải tuân thủ chính sách đó. Khi chưa có quy định, provider và consumer cần thống nhất thời hạn phù hợp, ghi rõ mốc ngày và tránh dùng cụm từ mơ hồ như “sẽ thông báo sớm”.

### 5.3. Quản lý thay đổi khẩn cấp

Lỗ hổng bảo mật nghiêm trọng hoặc sự cố đang diễn ra có thể buộc provider thay đổi nhanh hơn quy trình thông thường. Trong trường hợp này, provider cần thông báo qua kênh khẩn cấp, nêu lý do, phạm vi, hành động consumer cần làm và cách nhận hỗ trợ. Sau khi ổn định, các bên bổ sung hồ sơ quyết định, bằng chứng và đánh giá tác động còn lại.

Không dùng quy trình khẩn cấp để bỏ qua mọi kiểm soát. Cần lưu ai phê duyệt, rủi ro được chấp nhận và những kiểm thử tối thiểu đã thực hiện.

## 6. Bảo đảm tương thích và lập kế hoạch chuyển đổi

### 6.1. Phân loại thay đổi tương thích

| Loại thay đổi | Ví dụ | Cách xử lý thường dùng |
|---|---|---|
| Nội bộ, không đổi cam kết | Tối ưu truy vấn nhưng giữ nguyên schema và ngữ nghĩa | Provider chạy hồi quy và theo dõi metric; consumer được thông báo theo quy trình nếu có tác động vận hành |
| Mở rộng tương thích | Thêm endpoint hoặc trường response tùy chọn | Kiểm tra consumer có xử lý trường lạ; cập nhật hợp đồng và kiểm thử provider |
| Thay đổi có điều kiện | Tăng rate limit, đổi timeout, thêm giá trị enum | Phân tích cách consumer xử lý giới hạn và giá trị chưa biết; kiểm thử trên các consumer liên quan |
| Phá vỡ tương thích | Xóa trường, đổi kiểu, đổi ngữ nghĩa, thay cơ chế xác thực bắt buộc | Tạo kế hoạch phiên bản/chuyển đổi, hỗ trợ song song và phê duyệt rõ |

Tương thích phụ thuộc cách consumer thực sự giải mã và sử dụng dữ liệu. Thêm một giá trị enum có thể phá vỡ consumer dùng switch nghiêm ngặt; thêm trường response có thể phá vỡ client cũ nếu parser từ chối trường không biết. Do đó, phân tích phải xét cả hợp đồng và hành vi triển khai phổ biến.

### 6.2. Mở rộng trước, thu hẹp sau (expand-and-contract)

Đối với thay đổi schema hoặc API, một chiến lược giảm rủi ro thường là:

1. **Mở rộng provider:** bổ sung trường hoặc endpoint mới theo cách tương thích, giữ hành vi cũ.
2. **Xác minh provider:** kiểm thử cả hành vi cũ và mới, cập nhật hợp đồng.
3. **Nâng cấp consumer:** chuyển từng consumer sang giao diện mới, chạy contract test và kiểm thử tích hợp.
4. **Theo dõi sử dụng:** dùng log/metric để xác nhận không còn consumer quan trọng dùng giao diện cũ.
5. **Thu hẹp:** chỉ loại bỏ giao diện cũ sau khi hết thời gian hỗ trợ và có xác nhận từ các bên liên quan.

Với thay đổi dữ liệu, cần xem xét migration, dual-read/dual-write nếu phù hợp, bản ghi cũ và khả năng khôi phục. Không nên loại bỏ cột hoặc định dạng cũ trước khi các consumer và quy trình batch đã chuyển đổi.

### 6.3. Ma trận tương thích

Khi provider và consumer phát hành độc lập, cần ghi rõ các tổ hợp phiên bản được hỗ trợ. Ví dụ:

| Provider | Consumer v1 | Consumer v2 | Trạng thái |
|---|---|---|---|
| Provider v1 | Có | Chưa hỗ trợ | Tổ hợp hiện tại |
| Provider v2 mở rộng | Có | Có | Giai đoạn chuyển tiếp |
| Provider v3 loại bỏ trường cũ | Không | Có | Chỉ sau khi consumer v1 hết hỗ trợ |

Ma trận thực tế cần bao gồm phiên bản SDK, gateway, schema và các message đang tồn tại nếu chúng ảnh hưởng đến tương thích. Không suy luận rằng hai phiên bản có thể giao tiếp chỉ vì cả hai đều khởi động thành công.

## 7. Bằng chứng kiểm thử và tiêu chí chấp nhận thay đổi

### 7.1. Bằng chứng từ provider

Provider nên cung cấp bằng chứng phù hợp với loại thay đổi:

- Kiểm tra lint và tính hợp lệ của đặc tả/schema.
- Kiểm thử đơn vị, thành phần và hồi quy cho logic thay đổi.
- Provider contract verification với các hợp đồng consumer còn hiệu lực.
- Kiểm thử API cho đường thành công, lỗi, xác thực, phân quyền và dữ liệu biên.
- Kiểm thử tích hợp với database, broker hoặc sandbox liên quan.
- Kiểm thử hiệu năng, tải, timeout hoặc phục hồi khi thay đổi có ảnh hưởng phi chức năng.
- Kết quả phân tích thay đổi tương thích và danh sách consumer đã được đánh giá.
- Bằng chứng triển khai, smoke test, giám sát và rollback nếu cần.

### 7.2. Bằng chứng từ consumer

Consumer cần xác nhận:

- Consumer contract hoặc kiểm thử tương đương vẫn đạt với provider mới.
- Mã nguồn, SDK, cấu hình, scope và schema đã được cập nhật nếu cần.
- Các luồng nghiệp vụ quan trọng hoạt động đúng trong môi trường tích hợp.
- Consumer xử lý đúng timeout, lỗi, retry, rate limit và sự kiện lặp.
- Dữ liệu và trạng thái được duy trì đúng qua giai đoạn chuyển tiếp.
- Chỉ báo sau triển khai có thể phát hiện vấn đề liên quan đến thay đổi.
- Có phương án giảm thiểu nếu consumer chưa thể nâng cấp hoặc provider có sự cố.

### 7.3. Bằng chứng phối hợp

Với thay đổi ảnh hưởng nhiều nhóm, nên có một hồ sơ phối hợp ghi:

- Danh sách consumer và chủ sở hữu đã được xác định.
- Kết quả impact analysis và các giả định còn mở.
- Thông báo thay đổi và xác nhận của các bên liên quan.
- Ma trận phiên bản/tương thích và thứ tự triển khai.
- Kết quả kiểm thử provider, consumer và tích hợp.
- Các lỗi đã biết, ngoại lệ, rủi ro còn lại và người chấp thuận.
- Kế hoạch triển khai, tiêu chí dừng, rollback và đầu mối sự cố.

### 7.4. Tiêu chí chấp nhận

Thay đổi chỉ nên chuyển sang phát hành khi đáp ứng các điều kiện đã thống nhất, ví dụ:

- Không có thay đổi phá vỡ tương thích chưa được đánh giá và phê duyệt.
- Các contract test bắt buộc của consumer được xác minh.
- API và integration test trọng yếu đạt trên phiên bản/cấu hình phù hợp.
- Rủi ro bảo mật, dữ liệu và tuân thủ không vượt ngưỡng chấp nhận.
- Các consumer bị ảnh hưởng đã có kế hoạch nâng cấp hoặc phương án tương thích.
- Bằng chứng, ngoại lệ và người phê duyệt được lưu lại.
- Có giám sát, ngưỡng dừng và phương án khôi phục phù hợp.

Không dùng một tỷ lệ test pass chung để thay thế các điều kiện trọng yếu. Một lỗi duy nhất làm sai lệch giao dịch hoặc lộ dữ liệu có thể chặn phát hành dù hàng nghìn kiểm thử khác đạt.

## 8. Phối hợp phát hành, triển khai và rollback

### 8.1. Lập kế hoạch thứ tự phát hành

Thứ tự triển khai phụ thuộc vào tính tương thích giữa phiên bản. Với chiến lược expand-and-contract, provider thường triển khai phần mở rộng trước, sau đó consumer nâng cấp, rồi provider mới loại bỏ hành vi cũ. Với thay đổi xác thực, chứng chỉ hoặc giao thức, hai bên có thể cần giai đoạn hỗ trợ song song để tránh mất kết nối.

Kế hoạch phát hành nên xác định:

- Phiên bản provider và consumer cần có ở mỗi bước.
- Môi trường và nhóm người dùng được triển khai trước.
- Điều kiện bắt đầu, tiếp tục, dừng và mở rộng.
- Người theo dõi metric/log và người có quyền quyết định.
- Khoảng thời gian quan sát sau mỗi bước.
- Cách phối hợp khi một nhóm không thể hoàn thành đúng lịch.

### 8.2. Triển khai theo từng đợt

Với thay đổi rủi ro cao, có thể dùng canary, feature flag hoặc nhóm người dùng giới hạn. Theo dõi tỷ lệ lỗi, độ trễ, giao dịch chưa rõ, lỗi contract ở consumer và các chỉ báo nghiệp vụ. Chỉ mở rộng khi kết quả nằm trong ngưỡng và các bên xác nhận.

Canary không tự động bảo vệ mọi consumer. Cần chắc chắn nhóm canary đại diện cho các cấu hình, phiên bản và hành trình có liên quan. Nếu consumer quan trọng không nằm trong nhóm thử nghiệm, vẫn cần kiểm thử hoặc kế hoạch riêng.

### 8.3. Chuẩn bị rollback và khắc phục

Rollback có thể là quay provider về phiên bản trước, tắt feature flag, chuyển consumer về endpoint cũ hoặc khôi phục cấu hình. Tuy nhiên, rollback mã nguồn không luôn đảo ngược dữ liệu hoặc tác dụng phụ đã xảy ra.

Trước khi phát hành, cần trả lời:

- Phiên bản trước có còn tương thích với schema/dữ liệu hiện tại không?
- Migration có thể đảo ngược an toàn hay cần migration tiến về phía trước?
- Message đã phát hoặc giao dịch đã tạo có thể được xử lý bởi phiên bản cũ không?
- Consumer có thể tiếp tục hoạt động khi provider quay lại phiên bản trước không?
- Có thể tắt riêng phần thay đổi gây lỗi không?
- Ai quyết định rollback và ai thông báo cho các nhóm khác?

Với thay đổi không thể rollback an toàn, cần có phương án forward-fix, bù trừ giao dịch, khôi phục dữ liệu hoặc giới hạn chức năng. Không coi việc có nút rollback là đủ nếu chưa kiểm tra tính tương thích của dữ liệu và consumer.

## 9. Xử lý sự cố liên dịch vụ

### 9.1. Phát hiện và xác định phạm vi

Khi consumer gặp lỗi sau thay đổi provider, các bên cần nhanh chóng xác định:

- Thời điểm bắt đầu và phiên bản thay đổi gần nhất.
- Consumer, endpoint, message hoặc nhóm người dùng bị ảnh hưởng.
- Lỗi có tái hiện được không và điều kiện kích hoạt là gì.
- Metric, log, trace, correlation ID và mã phản hồi liên quan.
- Tác động đến dữ liệu, giao dịch, bảo mật và hành trình nghiệp vụ.
- Có consumer khác hoặc dịch vụ phụ thuộc nào bị ảnh hưởng dây chuyền không.

Dùng cùng một mốc thời gian và định danh tương quan khi trao đổi. Log cần loại bỏ token, secret và dữ liệu nhạy cảm trước khi chia sẻ liên nhóm.

### 9.2. Ứng phó và giảm thiểu

Ưu tiên giới hạn tác động đến người dùng và dữ liệu. Tùy tình huống, có thể tắt tính năng, giảm lưu lượng, chuyển sang endpoint tương thích, tạm dừng consumer, đưa message vào hàng đợi xử lý lại hoặc rollback provider.

Một nhóm điều phối sự cố nên có người chỉ huy, người điều tra provider, người điều tra consumer, người phụ trách vận hành và đầu mối truyền thông nghiệp vụ. Các bên cần thống nhất một nguồn cập nhật trạng thái để tránh thông tin mâu thuẫn.

Không nên thay đổi đồng thời nhiều thành phần khi chưa biết nguyên nhân, trừ khi cần hành động khẩn cấp để ngăn tác động tiếp diễn. Ghi lại từng hành động và thời điểm để có thể đánh giá sau sự cố.

### 9.3. Khôi phục và xác nhận

Sau khi áp dụng biện pháp giảm thiểu, chạy kiểm tra xác nhận trên luồng bị ảnh hưởng, đối chiếu dữ liệu và theo dõi metric. Chỉ tuyên bố khôi phục khi có bằng chứng dịch vụ hoạt động trong điều kiện cần thiết và backlog xử lý dữ liệu tồn đọng được kiểm soát.

Nếu đã phát sinh giao dịch trùng, mất message hoặc sai lệch dữ liệu, cần quy trình đối soát và khắc phục riêng. Khôi phục endpoint không đồng nghĩa dữ liệu nghiệp vụ đã được sửa.

### 9.4. Học từ sự cố

Sau khi ổn định, provider và consumer cùng thực hiện review không đổ lỗi để xác định:

- Vì sao thay đổi không được phát hiện trước phát hành?
- Bản đồ phụ thuộc hoặc thông báo có thiếu consumer không?
- Contract test có mô tả đúng ngữ nghĩa mà consumer dựa vào không?
- Môi trường kiểm thử có khác sản xuất ở điểm quyết định nào?
- Cổng phát hành và giám sát có đủ tín hiệu không?
- Rollback hoặc forward-fix có hoạt động như kế hoạch không?
- Cần bổ sung test, metric, tài liệu, quy trình hoặc trách nhiệm nào?

Hành động sau sự cố cần có chủ sở hữu, thời hạn và tiêu chí hoàn tất. Cập nhật hợp đồng, hồ sơ rủi ro, checklist và kế hoạch kiểm thử để ngăn lặp lại.

## 10. Ma trận RACI và ma trận quyết định

### 10.1. RACI cho thay đổi liên dịch vụ

RACI giúp phân biệt người thực hiện (R), người chịu trách nhiệm cuối cùng/phê duyệt (A), người cần tham vấn (C) và người cần được thông báo (I). Mỗi hoạt động nên có một vai trò A rõ ràng; tổ chức có thể điều chỉnh theo cơ cấu thực tế.

| Hoạt động | Provider owner | Consumer owner | Platform/SRE | Product owner | Security/Data |
|---|---|---|---|---|---|
| Duy trì hợp đồng provider | A/R | C | I | I | C khi liên quan |
| Xác định consumer bị ảnh hưởng | A/R | R/C xác nhận sử dụng | C | I | I |
| Phân tích ảnh hưởng phía consumer | C | A/R | C | C | C khi liên quan |
| Thông báo thay đổi provider | A/R | I | I | I | I/C khi thay đổi nhạy cảm |
| Consumer contract test | C | A/R | I | I | C khi liên quan |
| Provider verification | A/R | C | I | I | C khi liên quan |
| Kiểm thử tích hợp phối hợp | R | R | C/R theo môi trường | I | C theo rủi ro |
| Phê duyệt phát hành provider | R | C | R/C | A theo chính sách phát hành | C/A với yêu cầu chuyên môn bắt buộc |
| Phê duyệt nâng cấp consumer | C | R | C | A theo chính sách phát hành | C/A với yêu cầu chuyên môn bắt buộc |
| Ứng phó sự cố liên dịch vụ | R | R | A/R điều phối kỹ thuật theo mô hình trực | A về tác động nghiệp vụ | C/R theo loại sự cố |
| Truyền thông đến khách hàng | C | C | I | A/R | C khi liên quan |

RACI trên là ví dụ tham khảo. Nếu tổ chức có incident commander, service owner hoặc release manager riêng, cần đưa đúng vai trò đó vào ma trận. Không nên gán A cho nhiều nhóm cùng một hoạt động nếu không xác định rõ người ra quyết định cuối cùng.

### 10.2. Ma trận quyết định khi có thay đổi

| Tình huống | Provider cần làm | Consumer cần làm | Quyết định phát hành |
|---|---|---|---|
| Thay đổi nội bộ, không đổi cam kết | Chạy hồi quy và xác nhận metric không suy giảm | Theo dõi thông báo; kiểm tra nếu có tác động đã biết | Có thể phát hành theo quy trình provider nếu bằng chứng đạt |
| Thêm trường hoặc endpoint tương thích | Cập nhật hợp đồng, kiểm thử parser/serializer và provider | Xác nhận consumer bỏ qua hoặc sử dụng phần mới đúng cách | Phát hành khi tương thích với consumer được hỗ trợ |
| Đổi ngữ nghĩa hoặc giới hạn | Phân tích consumer, thông báo và cung cấp chuyển tiếp | Đánh giá logic, cập nhật xử lý và chạy test tích hợp | Chỉ phát hành sau khi các consumer liên quan có phương án được chấp thuận |
| Breaking change | Cung cấp phiên bản/compatibility window và kế hoạch ngừng hỗ trợ | Nâng cấp, xác minh và xác nhận lịch chuyển đổi | Không loại bỏ giao diện cũ trước khi điều kiện chuyển đổi được đáp ứng |
| Thay đổi khẩn cấp vì bảo mật/sự cố | Thông báo khẩn, giới hạn thay đổi và cung cấp hướng dẫn | Áp dụng biện pháp cần thiết, kiểm tra tác động và xác nhận | Người có thẩm quyền quyết định theo quy trình khẩn cấp, lưu rủi ro và bằng chứng |
| Sự cố sau phát hành | Điều tra provider, giảm thiểu và cung cấp trạng thái | Điều tra consumer, bảo vệ dữ liệu và xác nhận phục hồi | Incident commander/release authority điều phối hành động theo mức độ ảnh hưởng |

## 11. Ví dụ phối hợp thực tế

### Ví dụ A: Provider đổi kiểu dữ liệu của trường API

Một dịch vụ khách hàng dự kiến đổi `customerId` từ chuỗi sang số nguyên. Nhiều consumer đang lưu giá trị này dưới dạng chuỗi và một số mã có thể chứa ký tự định danh.

Provider lập danh sách consumer từ registry và log truy cập, công bố thay đổi cùng ví dụ trước/sau, đánh giá breaking change và đề xuất trường mới `customerNumericId` trong giai đoạn chuyển tiếp. Consumer kiểm tra cách lưu trữ, serialization, tìm kiếm và dữ liệu cũ; chạy contract test với provider phiên bản mới. Hai bên thống nhất hỗ trợ song song, theo dõi mức sử dụng trường cũ rồi mới ngừng hỗ trợ. Nếu một consumer quan trọng chưa nâng cấp, provider không xóa trường cũ chỉ dựa trên việc phần lớn consumer đã chuyển đổi.

### Ví dụ B: Provider thay đổi cách trả lỗi và rate limit

Một API trước đây trả 503 khi quá tải, nay áp dụng rate limit và trả 429 cùng thông tin thời gian chờ. Consumer có retry tự động ngay lập tức nên có thể làm tăng tải và gây vòng lặp retry.

Provider thông báo ngưỡng mới, mã lỗi và header retry. Consumer cập nhật backoff có jitter, giới hạn số lần thử và chỉ retry các thao tác an toàn hoặc có idempotency. Kiểm thử tích hợp mô phỏng 429 liên tiếp, header thiếu hoặc không hợp lệ, timeout và phục hồi. Hai bên theo dõi tỷ lệ 429, số lần retry, độ trễ và tỷ lệ giao dịch hoàn tất sau phát hành.

### Ví dụ C: Nhóm dữ liệu đổi schema sự kiện

Nhóm dữ liệu thêm trường bắt buộc vào event `CustomerUpdated`. Một consumer cũ giải mã nghiêm ngặt và không chấp nhận trường mới; một batch job chạy theo lịch chỉ hoạt động mỗi đêm.

Provider kiểm tra schema registry, consumer contract và danh sách job định kỳ. Nhóm thông báo thời gian chuyển đổi, phát event tương thích trong giai đoạn hỗ trợ, đồng thời kiểm thử dữ liệu tồn trong broker. Consumer cập nhật parser và chạy test với cả event cũ lẫn mới. Việc loại bỏ schema cũ chỉ diễn ra sau khi batch job đã chạy thành công qua chu kỳ đại diện và các consumer xác nhận.

### Ví dụ D: Thay đổi xác thực ảnh hưởng nhiều nhóm

Provider chuyển API từ khóa tĩnh sang OAuth scope. Đây là thay đổi bảo mật và có thể làm gián đoạn consumer chưa có cơ chế cấp token.

Nhóm bảo mật xác định scope tối thiểu, quy trình cấp/thu hồi credential và yêu cầu audit. Provider công bố lịch hỗ trợ song song, sandbox và hướng dẫn chuyển đổi. Consumer triển khai lấy token, lưu trữ secret an toàn, kiểm thử token hết hạn, sai scope và thu hồi. Cổng phát hành xác nhận không còn consumer quan trọng dùng khóa cũ trước khi vô hiệu hóa cơ chế cũ, trừ trường hợp khẩn cấp có phê duyệt theo chính sách.

### Ví dụ E: Sự cố do triển khai không tương thích

Provider triển khai phiên bản loại bỏ trường `paymentStatus` trước khi một consumer batch nâng cấp. Consumer bắt đầu lỗi khi chạy ban đêm, khiến trạng thái thanh toán không được đối soát.

Các nhóm phối hợp dừng batch nếu có nguy cơ ghi sai dữ liệu, khôi phục trường cũ hoặc triển khai forward-fix, sau đó chạy lại các bản ghi chưa xử lý theo cơ chế idempotent. Incident commander điều phối cập nhật, Product owner đánh giá ảnh hưởng nghiệp vụ và nhóm dữ liệu đối chiếu số giao dịch. Sau sự cố, bổ sung inventory consumer theo lịch, kiểm tra compatibility matrix và cổng ngăn xóa field khi consumer còn hoạt động.

## 12. Hồ sơ và mẫu thông báo thay đổi

### 12.1. Hồ sơ phối hợp thay đổi

Mỗi thay đổi liên dịch vụ quan trọng nên có hồ sơ bao gồm:

| Trường | Nội dung |
|---|---|
| Change ID | Mã thay đổi và liên kết yêu cầu/PR |
| Provider/service | Dịch vụ, giao diện và nhóm sở hữu |
| Phiên bản | Phiên bản hiện tại, phiên bản mục tiêu và thời điểm áp dụng |
| Mô tả thay đổi | Trước/sau, cấu trúc, ngữ nghĩa, bảo mật, lỗi và phi chức năng |
| Consumer bị ảnh hưởng | Danh sách consumer trực tiếp/gián tiếp và đầu mối |
| Impact analysis | Mức ảnh hưởng, giả định, dữ liệu và rủi ro |
| Tương thích | Phân loại breaking/non-breaking, ma trận phiên bản và thời gian hỗ trợ |
| Kế hoạch kiểm thử | Provider, consumer, contract, integration, hiệu năng và bảo mật |
| Bằng chứng | Báo cáo, kết quả pipeline, log đã làm sạch và xác nhận của nhóm |
| Kế hoạch phát hành | Thứ tự, canary, cửa sổ triển khai và người điều phối |
| Rollback/mitigation | Điều kiện dừng, rollback, forward-fix hoặc biện pháp bù trừ |
| Chấp thuận | Người phê duyệt, ngoại lệ và rủi ro còn lại |
| Truyền thông | Kênh, ngày thông báo, người nhận và trạng thái xác nhận |

### 12.2. Mẫu thông báo ngắn

```text
Tiêu đề: Thay đổi API [service/endpoint] - [version]

Provider và owner:
Consumer dự kiến bị ảnh hưởng:
Ngày phát hành dự kiến:
Ngày ngừng hỗ trợ phiên bản cũ (nếu có):

Thay đổi:
- Trước:
- Sau:
- Phân loại tương thích:

Consumer cần thực hiện:
- Cập nhật mã/cấu hình/quyền:
- Kiểm thử cần chạy:
- Hạn xác nhận:

Bằng chứng và môi trường:
- Hợp đồng/schema:
- Kết quả provider verification:
- Sandbox/integration environment:

Kế hoạch phát hành và khôi phục:
- Thứ tự triển khai:
- Ngưỡng dừng:
- Rollback/forward-fix:

Đầu mối kỹ thuật và kênh hỗ trợ:
Rủi ro còn lại/ngoại lệ:
```

Mẫu cần được điền bằng thông tin cụ thể. Không gửi thông báo chỉ có tiêu đề và ngày phát hành mà thiếu mô tả thay đổi, consumer bị ảnh hưởng hoặc hành động cần làm.

## 13. Những sai lầm thường gặp

- **Cho rằng provider chịu toàn bộ trách nhiệm tích hợp:** provider không thể xác nhận mọi cách consumer sử dụng API.
- **Cho rằng consumer phải tự thích nghi với mọi thay đổi:** provider vẫn phải tuân thủ hợp đồng, chính sách thông báo và thời gian hỗ trợ đã cam kết.
- **Không duy trì danh sách consumer:** thay đổi bỏ sót batch job, webhook hoặc tích hợp ít hoạt động.
- **Chỉ kiểm tra schema:** ngữ nghĩa, quyền, trạng thái, retry và giới hạn vận hành vẫn có thể phá vỡ consumer.
- **Thông báo quá muộn:** consumer không đủ thời gian sửa, kiểm thử và triển khai.
- **Không có chủ sở hữu đầu mối:** câu hỏi và lỗi bị chuyển qua nhiều nhóm mà không ai điều phối.
- **Chỉ chạy test ở provider:** consumer có thể dùng sai giả định hoặc cấu hình riêng.
- **Chỉ chạy test ở consumer:** provider có thể thay đổi làm ảnh hưởng những consumer khác chưa tham gia.
- **Triển khai breaking change cùng lúc ở nhiều bên:** khó xác định nguyên nhân và khó rollback độc lập.
- **Không kiểm tra consumer chạy theo lịch:** batch job hoặc dữ liệu tồn có thể bị bỏ sót.
- **Rollback mà không xét dữ liệu:** phiên bản cũ có thể không đọc được dữ liệu hoặc message mới.
- **Không cập nhật sau sự cố:** cùng một loại lỗi tương thích có thể lặp lại ở lần phát hành sau.

## 14. Checklist chia sẻ trách nhiệm khi có thay đổi

### Trước khi phát triển thay đổi

- [ ] Provider và consumer owner của giao diện đã được xác định.
- [ ] Hợp đồng và phiên bản hiện hành có nguồn chính thức.
- [ ] Bản đồ phụ thuộc gồm consumer trực tiếp, gián tiếp và job theo lịch đã được rà soát.
- [ ] Tác động cấu trúc, ngữ nghĩa, bảo mật, dữ liệu, hiệu năng và vận hành đã được phân tích.
- [ ] Thay đổi được phân loại mức tương thích và mức rủi ro.
- [ ] Các bên đã thống nhất thông báo, thời gian hỗ trợ và đầu mối phối hợp.

### Trước khi phát hành

- [ ] Provider verification và kiểm thử hồi quy phù hợp đã đạt.
- [ ] Consumer contract và kiểm thử tích hợp của các consumer quan trọng đã đạt.
- [ ] Ma trận phiên bản và thứ tự triển khai được thống nhất.
- [ ] Consumer đã nhận thông báo và xác nhận kế hoạch hành động.
- [ ] Rủi ro còn lại, ngoại lệ và người chấp thuận được ghi nhận.
- [ ] Có metric, log, trace và cảnh báo để phát hiện tác động.
- [ ] Có tiêu chí dừng, rollback hoặc forward-fix và người ra quyết định.

### Sau khi phát hành

- [ ] Theo dõi chỉ báo kỹ thuật và nghiệp vụ trong cửa sổ quan sát đã định.
- [ ] Xác nhận các consumer và batch job hoạt động với phiên bản mới.
- [ ] Đối soát dữ liệu hoặc sự kiện nếu thay đổi có tác động trạng thái.
- [ ] Sự cố được điều phối qua đầu mối chung và cập nhật cho các bên liên quan.
- [ ] Bằng chứng, hợp đồng, changelog và ma trận tương thích được cập nhật.
- [ ] Hành động sau sự cố có chủ sở hữu, thời hạn và tiêu chí hoàn tất.

## Kết luận

Khi một dịch vụ hoặc nhóm khác thay đổi, chất lượng phụ thuộc vào sự phối hợp có tổ chức giữa provider, consumer, nền tảng, sản phẩm và các chuyên gia liên quan. Provider cần quản lý hợp đồng và thông báo minh bạch; consumer cần xác nhận cách tích hợp và khả năng tương thích; các bên cùng phân tích ảnh hưởng, thống nhất bằng chứng, thứ tự phát hành và cách ứng phó. Ranh giới sở hữu rõ ràng, ma trận trách nhiệm, kiểm thử hợp đồng, kế hoạch chuyển đổi và quy trình sự cố giúp thay đổi độc lập diễn ra an toàn mà vẫn bảo vệ các hành trình nghiệp vụ xuyên dịch vụ.
