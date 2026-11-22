# Mô tả bối cảnh, mục tiêu, phạm vi và giả định

Một tài liệu chiến lược kiểm thử chỉ hữu ích khi người đọc hiểu sản phẩm đang được xây dựng trong hoàn cảnh nào, nhóm muốn đạt kết quả gì, phần nào nằm trong kế hoạch và những điều kiện nào đang được xem là đúng. Nếu thiếu các nội dung này, phần mô tả phương pháp và hoạt động kiểm thử dễ trở thành danh sách kỹ thuật rời rạc: người đọc không biết vì sao một luồng được ưu tiên, vì sao một môi trường được chọn hoặc kết luận kiểm thử áp dụng tới đâu.

Bối cảnh, mục tiêu, phạm vi và giả định tạo nên nền tảng để các phần còn lại của chiến lược có ý nghĩa. Chúng giúp nhóm thống nhất vấn đề cần giải quyết, xác định ranh giới trách nhiệm, chọn bằng chứng phù hợp và nhận biết khi nào chiến lược cần được xem xét lại.

## 1. Vai trò của bốn thành phần nền tảng

Trong tài liệu chiến lược, bốn thành phần có quan hệ với nhau nhưng trả lời những câu hỏi khác nhau:

| Thành phần | Câu hỏi chính | Nội dung cần mô tả |
| --- | --- | --- |
| Bối cảnh (context) | Chúng ta đang kiểm thử sản phẩm nào, trong hoàn cảnh nào và vì sao? | Sản phẩm, người dùng, nghiệp vụ, kiến trúc, tổ chức, môi trường và các yếu tố ảnh hưởng |
| Mục tiêu (objectives) | Hoạt động kiểm thử cần tạo ra kết quả gì? | Kết quả mong muốn, tiêu chí đo, mức ưu tiên và điều kiện thành công |
| Phạm vi (scope) | Những gì được kiểm tra và những gì nằm ngoài kế hoạch? | Sản phẩm, tính năng, nền tảng, loại kiểm thử, ranh giới và ngoại lệ |
| Giả định (assumptions) | Điều gì đang được tạm xem là đúng để lập kế hoạch? | Điều kiện chưa được xác nhận, bằng chứng hiện có, người xác minh và tác động nếu sai |

Các thành phần này cần được viết đủ cụ thể để một người mới tham gia dự án có thể hiểu quyết định kiểm thử mà không phải suy đoán ý định của người viết.

## 2. Mô tả bối cảnh của sản phẩm

Bối cảnh giải thích môi trường kinh doanh và kỹ thuật mà sản phẩm hoạt động. Không cần chép toàn bộ tài liệu kiến trúc hoặc yêu cầu vào chiến lược. Hãy chọn những thông tin có ảnh hưởng đến rủi ro, cách kiểm thử, nguồn lực và quyết định phát hành.

### 2.1. Bối cảnh nghiệp vụ

Mô tả sản phẩm hỗ trợ hoạt động nào, vấn đề nào cần giải quyết và những quy trình nghiệp vụ quan trọng. Có thể bao gồm:

- Sản phẩm hoặc dịch vụ đang được phát triển, nâng cấp hay thay thế.
- Mục đích sử dụng và giá trị mà sản phẩm cung cấp.
- Các hành trình nghiệp vụ trọng yếu, ví dụ đăng ký, đặt hàng, thanh toán, phê duyệt hoặc đối soát.
- Quy tắc nghiệp vụ có hậu quả lớn nếu xử lý sai.
- Mùa vụ, giờ cao điểm, thời hạn hoặc sự kiện làm thay đổi lưu lượng.
- Yêu cầu pháp lý, hợp đồng, kiểm toán hoặc chính sách có liên quan.
- Các hệ thống, đối tác hoặc quy trình bên ngoài mà sản phẩm phụ thuộc.

Ví dụ, một nền tảng đặt hàng trực tuyến cần xử lý tìm kiếm sản phẩm, giỏ hàng, tính giá, thanh toán, giữ tồn kho, giao hàng và hoàn tiền. Một lỗi hiển thị mô tả sản phẩm có thể gây bất tiện; một lỗi tính giá hoặc ghi nhận thanh toán có thể gây thiệt hại tài chính và tranh chấp. Bối cảnh nghiệp vụ giúp giải thích vì sao các luồng tiền và tồn kho cần ưu tiên cao hơn một số trang nội dung ít sử dụng.

### 2.2. Người dùng và các bên liên quan

Xác định các nhóm người dùng và bên liên quan có ảnh hưởng đến chất lượng hoặc quyết định kiểm thử:

- Người dùng cuối và nhóm người dùng có nhu cầu đặc biệt.
- Nhân viên vận hành, hỗ trợ khách hàng và quản trị hệ thống.
- Chủ sản phẩm, chuyên gia nghiệp vụ và người phê duyệt.
- Nhóm phát triển, kiểm thử, nền tảng, bảo mật và dữ liệu.
- Nhà cung cấp, đối tác tích hợp và đơn vị xử lý bên ngoài.

Không chỉ liệt kê tên nhóm. Hãy mô tả điều họ cần ở sản phẩm và cách nhu cầu đó tạo ra yêu cầu kiểm thử. Ví dụ, nhân viên hỗ trợ cần xem được lịch sử giao dịch chính xác; nhóm vận hành cần phát hiện queue bị tắc; người dùng cuối cần biết đơn hàng đang chờ hay đã được xác nhận.

### 2.3. Bối cảnh kỹ thuật

Chỉ nêu các đặc điểm kỹ thuật ảnh hưởng đến chiến lược:

- Kiến trúc tổng thể: ứng dụng đơn khối, dịch vụ phân tán, event-driven hoặc kiến trúc lai.
- Thành phần quan trọng: giao diện, API, database, cache, broker, batch job và dịch vụ bên ngoài.
- Nền tảng triển khai: cloud, on-premises, thiết bị biên hoặc ứng dụng di động.
- Công nghệ, runtime, trình duyệt, hệ điều hành và phiên bản cần hỗ trợ.
- Cách tích hợp, xác thực, phân quyền và trao đổi dữ liệu.
- Cách phát hành: theo đợt, canary, blue-green, feature flag hoặc cập nhật trực tiếp.
- Hạn chế đã biết: môi trường dùng chung, dữ liệu khó tạo, sandbox không đầy đủ hoặc phụ thuộc không ổn định.

Ví dụ, hệ thống xử lý thanh toán bất đồng bộ qua message broker cần kiểm thử thứ tự sự kiện, retry, giao nhận trùng và khả năng đối soát. Nếu chiến lược chỉ ghi “kiểm thử API” mà không mô tả kiến trúc bất đồng bộ, người đọc có thể bỏ qua các rủi ro quan trọng.

### 2.4. Bối cảnh tổ chức và dự án

Chiến lược cũng cần phản ánh cách công việc được tổ chức:

- Các nhóm và vai trò chịu trách nhiệm.
- Mô hình phối hợp giữa phát triển, kiểm thử, vận hành và bảo mật.
- Nhịp phát hành, sprint, mốc bàn giao và các phụ thuộc.
- Năng lực kiểm thử hiện có, kỹ năng, công cụ và ngân sách.
- Quy trình quản lý thay đổi, lỗi, rủi ro và phê duyệt.
- Những giới hạn về thời gian, môi trường, dữ liệu hoặc quyền truy cập.

Thông tin này giúp chiến lược khả thi. Ví dụ, nếu nhóm không có môi trường hiệu năng riêng, tài liệu cần nói rõ cách đặt lịch sử dụng môi trường, giới hạn tải và cách ghi nhận rủi ro của phép đo.

## 3. Viết bối cảnh có chọn lọc và có nguồn

Một phần bối cảnh tốt không phải là bản mô tả dài nhất. Nó tập trung vào thông tin làm thay đổi quyết định kiểm thử.

Với mỗi thông tin, cân nhắc:

1. Thông tin này ảnh hưởng đến rủi ro, phạm vi, phương pháp hoặc nguồn lực nào?
2. Nó là dữ kiện đã xác minh, yêu cầu chính thức hay nhận định tạm thời?
3. Nguồn nào là nguồn chuẩn và ai chịu trách nhiệm cập nhật?
4. Thông tin có thời hạn hoặc phụ thuộc phiên bản không?
5. Nếu thông tin thay đổi, phần nào của chiến lược phải xem xét lại?

Nên liên kết tới nguồn chuẩn như tài liệu yêu cầu, sơ đồ kiến trúc, risk register, hợp đồng API, quyết định kiến trúc hoặc kế hoạch phát hành. Tránh sao chép các đoạn dài rồi để chúng nhanh chóng lỗi thời.

Ví dụ về cách ghi:

> **Bối cảnh:** Checkout xử lý yêu cầu tạo đơn đồng bộ nhưng xác nhận thanh toán và cập nhật tồn kho diễn ra bất đồng bộ qua broker. Các luồng tạo đơn, ghi nhận thanh toán và giữ tồn kho có tác động tài chính trực tiếp. Sơ đồ kiến trúc và hợp đồng sự kiện là nguồn tham chiếu cho các ranh giới tích hợp. Nhóm cần kiểm thử retry, sự kiện trùng, trạng thái đến muộn và đối soát.

Đoạn này nêu đặc điểm có ảnh hưởng trực tiếp tới cách kiểm thử và lý do ưu tiên.

## 4. Xác định mục tiêu kiểm thử

Mục tiêu kiểm thử mô tả kết quả mà chiến lược cần đạt để hỗ trợ quyết định về chất lượng. Mục tiêu không nên chỉ là hoạt động như “viết thêm test”, “chạy regression” hoặc “kiểm thử đầy đủ”. Những hoạt động đó là phương tiện; mục tiêu phải nói rõ giá trị cần đạt.

Ví dụ:

- Bảo đảm các giao dịch thanh toán được ghi nhận đúng một lần trong điều kiện retry và giao nhận sự kiện trùng.
- Phát hiện lỗi hồi quy ở các hành trình đặt hàng quan trọng trước khi phát hành.
- Xác minh API tuân thủ hợp đồng được công bố cho các consumer đang được hỗ trợ.
- Đo thời gian phản hồi ở tải dự kiến và xác định giới hạn suy giảm khi tải tăng.
- Bảo đảm dữ liệu nhạy cảm không bị truy cập bởi vai trò không được phép.
- Xác minh khả năng khôi phục dịch vụ và tính toàn vẹn dữ liệu trong tình huống lỗi đã xác định.

### 4.1. Phân biệt mục tiêu, hoạt động và chỉ số

| Loại | Ví dụ | Cách sử dụng |
| --- | --- | --- |
| Mục tiêu | Giảm rủi ro ghi nhận giao dịch trùng | Nêu kết quả chất lượng cần đạt |
| Hoạt động | Viết integration test cho retry và duplicate delivery | Mô tả công việc thực hiện |
| Chỉ số | Số lần test tạo nhiều ledger entry trong cùng khóa nghiệp vụ | Đo kết quả hoặc tín hiệu liên quan |
| Tiêu chí thành công | Không có giao dịch logic trùng trong các tình huống đã xác định | Quy tắc kết luận dựa trên bằng chứng |

Không nên dùng số lượng hoạt động làm bằng chứng trực tiếp cho mục tiêu. Viết 50 test không chứng minh rủi ro đã giảm nếu chúng không kiểm tra đúng cơ chế gây lỗi.

### 4.2. Viết mục tiêu theo kết quả có thể đánh giá

Một mục tiêu có thể đánh giá thường nêu:

- Kết quả hoặc rủi ro cần kiểm soát.
- Phạm vi sản phẩm hoặc nhóm người dùng liên quan.
- Mức chất lượng hoặc tiêu chí cần đạt.
- Cách thu thập bằng chứng.
- Thời điểm hoặc mốc cần hoàn tất.

Ví dụ chưa rõ:

> Kiểm tra hiệu năng tốt trước release.

Ví dụ cụ thể hơn:

> Trước release candidate, đo p95 và tỷ lệ lỗi của API tìm kiếm trong mô hình tải đại diện cho giờ cao điểm; xác minh p95 không vượt ngưỡng đã được chủ sản phẩm và service owner phê duyệt, đồng thời tỷ lệ lỗi không vượt giới hạn trong cửa sổ đo.

Giá trị ngưỡng cụ thể nên nằm trong tiêu chí chất lượng hoặc kế hoạch kiểm thử liên quan để có thể cập nhật mà không phải viết lại toàn bộ bối cảnh.

### 4.3. Phân cấp mục tiêu

Có thể nhóm mục tiêu theo các cấp:

- **Mục tiêu sản phẩm:** bảo vệ trải nghiệm và kết quả nghiệp vụ quan trọng.
- **Mục tiêu chất lượng:** kiểm soát hiệu năng, độ tin cậy, bảo mật, khả năng sử dụng, tương thích và khả năng phục hồi.
- **Mục tiêu quy trình:** tạo phản hồi đủ sớm, có thể truy nguyên và hỗ trợ quyết định.
- **Mục tiêu phát hành:** cung cấp bằng chứng và điều kiện cần để quyết định triển khai.

Không nên tạo quá nhiều mục tiêu ngang hàng. Hãy ưu tiên mục tiêu theo tác động và liên kết mỗi mục tiêu với một hoặc nhiều rủi ro, yêu cầu và bằng chứng.

## 5. Chọn chỉ số và tiêu chí thành công

Mục tiêu cần có cách đánh giá. Chỉ số phù hợp phải phản ánh kết quả cần quan tâm và có định nghĩa rõ.

Một số nhóm chỉ số:

| Mục tiêu | Chỉ số/bằng chứng có thể dùng | Lưu ý |
| --- | --- | --- |
| Tính đúng đắn nghiệp vụ | Tỷ lệ giao dịch đúng, trạng thái cuối, tính toàn vẹn dữ liệu | Phải xác định oracle và tập giao dịch hợp lệ |
| Hiệu năng | p95/p99 latency, throughput, error rate, tài nguyên | Nêu tải, dữ liệu, môi trường và thời lượng |
| Độ tin cậy | Tỷ lệ yêu cầu thành công, thời gian gián đoạn, lỗi tái diễn | Nêu cửa sổ đo và định nghĩa “thành công” |
| Bảo mật | Kết quả kiểm tra quyền, phát hiện theo mức độ, bằng chứng xử lý | Phạm vi quét và giới hạn công cụ phải rõ |
| Khả năng phục hồi | RTO, RPO, thời gian phục hồi, tính toàn vẹn sau restore | Nêu loại sự cố và quy mô dữ liệu |
| Khả năng sử dụng | Tỷ lệ hoàn thành tác vụ, thời gian, lỗi thao tác | Nêu nhóm người tham gia và kịch bản |
| Chất lượng phản hồi | Thời gian phát hiện, thời gian phân loại failure | Phân biệt phản hồi đầu tiên với giải quyết cuối |

Không phải mọi mục tiêu đều cần một chỉ số số học. Một số tiêu chí có thể là điều kiện định tính nhưng phải có rubric, bằng chứng và người đánh giá rõ ràng.

### 5.1. Chỉ số kết quả và chỉ số bảo vệ

Để tránh tối ưu sai mục tiêu, nên kết hợp:

- **Chỉ số kết quả:** phản ánh mục tiêu chính, ví dụ thời gian phản hồi hoặc tỷ lệ hoàn thành.
- **Chỉ số bảo vệ:** phát hiện tác dụng phụ, ví dụ tỷ lệ lỗi, giao dịch trùng hoặc vi phạm quyền.
- **Chỉ số chẩn đoán:** giải thích nguyên nhân, ví dụ queue lag, CPU, retry count hoặc lỗi phụ thuộc.

Ví dụ, giảm p95 bằng cách từ chối nhiều yêu cầu có thể làm chỉ số latency đẹp hơn nhưng chất lượng sản phẩm giảm. Vì vậy, latency cần được xem cùng error rate và tỷ lệ hoàn thành nghiệp vụ.

### 5.2. Tránh mục tiêu không thể kiểm chứng

Những câu như “chất lượng cao”, “không có lỗi”, “hệ thống ổn định” hoặc “đảm bảo bảo mật” quá rộng nếu không có định nghĩa. Hãy làm rõ:

- Phạm vi chức năng hoặc tài sản.
- Loại lỗi hoặc rủi ro được xem xét.
- Điều kiện và dữ liệu thử.
- Mức ngưỡng hoặc quy tắc chấp nhận.
- Bằng chứng và giới hạn của phương pháp.

Không thể chứng minh một hệ thống “không có lỗi”. Có thể chứng minh các kiểm tra đã xác định được thực hiện trong phạm vi và điều kiện cụ thể, kết quả đạt tiêu chí, cùng các rủi ro còn lại.

## 6. Xác định phạm vi kiểm thử

Phạm vi trả lời điều gì sẽ được kiểm tra, trong điều kiện nào và ở mức nào. Một phạm vi rõ giúp tránh kỳ vọng rằng chiến lược bao phủ mọi thứ hoặc ngược lại bỏ sót các khu vực quan trọng.

### 6.1. Phạm vi sản phẩm và chức năng

Liệt kê các thành phần, tính năng hoặc hành trình thuộc phạm vi. Có thể phân nhóm:

- Luồng nghiệp vụ trọng yếu.
- API và hợp đồng tích hợp.
- Thành phần xử lý dữ liệu và tác vụ nền.
- Giao diện và nền tảng người dùng.
- Quản trị, phân quyền và audit.
- Cấu hình, migration và triển khai.

Không chỉ liệt kê tên module. Nên ghi rõ mức kiểm tra và hành vi cần xác minh. Ví dụ, “Payment API” có thể bao gồm tạo giao dịch, truy vấn trạng thái, retry, hoàn tiền và xử lý callback; mỗi luồng có rủi ro khác nhau.

### 6.2. Phạm vi chất lượng

Xác định thuộc tính chất lượng sẽ được đánh giá:

- Tính đúng đắn và phù hợp chức năng.
- Hiệu năng và khả năng mở rộng.
- Độ tin cậy và tính sẵn sàng.
- Bảo mật và quyền riêng tư.
- Khả năng sử dụng và tiếp cận.
- Tương thích và khả năng cài đặt.
- Khả năng phục hồi và bảo trì.

Không nhất thiết mọi thuộc tính đều được kiểm tra ở cùng mức cho mọi tính năng. Mức độ cần thiết phụ thuộc rủi ro, yêu cầu, loại sản phẩm và điều kiện sử dụng.

### 6.3. Phạm vi nền tảng và cấu hình

Nêu các tổ hợp được hỗ trợ hoặc được chọn để kiểm tra:

- Trình duyệt, hệ điều hành, thiết bị và phiên bản.
- Cấu hình server, container, runtime và database.
- Khu vực triển khai, ngôn ngữ, múi giờ và cấu hình mạng.
- Vai trò, nhóm quyền và loại tài khoản.
- Phiên bản API, schema, client và phụ thuộc.

Nếu không kiểm tra mọi tổ hợp, ghi nguyên tắc chọn tổ hợp đại diện theo mức sử dụng, rủi ro và khác biệt kỹ thuật. Không để người đọc hiểu rằng danh sách đã chọn đồng nghĩa mọi tổ hợp đều được xác minh.

### 6.4. Phạm vi tầng và loại kiểm thử

Chiến lược có thể xác định các tầng:

| Tầng/loại | Mục đích thường gặp | Phạm vi cần nêu |
| --- | --- | --- |
| Unit/component | Kiểm tra quy tắc cục bộ | Module, logic và nhóm giá trị biên |
| Integration | Kiểm tra tương tác và lưu trữ | Ranh giới dịch vụ, database, broker và phụ thuộc |
| Contract/API | Kiểm tra hợp đồng | Provider, consumer, schema, mã lỗi và tương thích |
| System/E2E | Kiểm tra hành trình xuyên hệ thống | Hành trình quan trọng và trạng thái cuối |
| Regression | Phát hiện tác động ngoài ý muốn | Bộ test chọn theo thay đổi và rủi ro |
| Non-functional | Đo thuộc tính chất lượng | Hiệu năng, bảo mật, phục hồi, khả năng sử dụng... |
| Exploratory/manual | Tìm hiểu hành vi và rủi ro chưa mô hình hóa | Charter, khu vực và điều kiện khám phá |

Không cần mô tả mọi test case ở phần phạm vi. Hãy nêu loại bằng chứng và ranh giới; chi tiết trường hợp có thể nằm trong test plan hoặc test suite.

## 7. Nêu rõ phần nằm ngoài phạm vi

Phần ngoài phạm vi (out of scope) cần được ghi rõ để quản lý kỳ vọng và rủi ro. Một nội dung có thể bị loại khỏi đợt kiểm thử vì:

- Không thuộc sản phẩm hoặc phiên bản đang bàn.
- Được một nhóm hoặc nhà cung cấp khác kiểm tra.
- Không có môi trường hoặc quyền truy cập trong giai đoạn hiện tại.
- Có mức ưu tiên thấp hơn trong phạm vi nguồn lực đã thống nhất.
- Chỉ được xác minh ở một giai đoạn hoặc chương trình riêng.

Với mỗi nội dung ngoài phạm vi quan trọng, nên ghi lý do, bên chịu trách nhiệm, bằng chứng thay thế nếu có và rủi ro còn lại.

Ví dụ:

| Nội dung ngoài phạm vi | Lý do | Rủi ro/biện pháp theo dõi |
| --- | --- | --- |
| Kiểm thử hiệu năng toàn vùng địa lý thứ hai | Hạ tầng vùng này chưa sẵn sàng trong release hiện tại | Chủ sở hữu nền tảng cung cấp kế hoạch kiểm tra trước khi mở rộng vùng |
| Kiểm thử thiết bị di động đời rất cũ | Không nằm trong danh sách thiết bị được hỗ trợ | Product owner xác nhận phạm vi hỗ trợ và theo dõi phản hồi người dùng |
| Kiểm thử xâm nhập độc lập bởi bên thứ ba | Được lên lịch trong đợt đánh giá riêng | Không mở rộng phát hành trước khi phê duyệt bảo mật bắt buộc hoàn tất |

Không nên ghi “không áp dụng” nếu thực tế chỉ là chưa có nguồn lực hoặc chưa có bằng chứng. Hai trường hợp có ý nghĩa khác nhau.

## 8. Xác định ranh giới và điểm bàn giao

Phạm vi cần nêu ranh giới giữa trách nhiệm của nhóm kiểm thử và các bên liên quan:

- Thành phần nào do nhóm dự án sở hữu?
- Thành phần nào do nhóm nền tảng hoặc nhà cung cấp quản lý?
- Ai cung cấp sandbox, dữ liệu và tài khoản?
- Ai xác minh hợp đồng của provider và ai xác minh consumer?
- Những kiểm thử nào cần phối hợp với security, privacy, operations hoặc nghiệp vụ?
- Kết quả nào được chấp nhận từ nhà cung cấp và cần xác minh độc lập đến đâu?

Ranh giới không có nghĩa bỏ qua rủi ro ở thành phần bên ngoài. Nhóm có thể không kiểm thử nội bộ mã nguồn của nhà cung cấp nhưng vẫn cần kiểm tra hợp đồng, timeout, lỗi, giới hạn, retry và cách hệ thống xử lý khi phụ thuộc không sẵn sàng.

### Ví dụ ranh giới tích hợp

Với cổng thanh toán bên ngoài:

- Nhà cung cấp chịu trách nhiệm vận hành hệ thống thanh toán của họ.
- Nhóm sản phẩm kiểm thử cách tích hợp gửi yêu cầu, xác minh chữ ký callback, xử lý timeout, retry và đối soát.
- Nhóm kiểm thử dùng sandbox để xác minh các trạng thái và lỗi được nhà cung cấp hỗ trợ.
- Những hành vi không thể mô phỏng trong sandbox được ghi là giới hạn bằng chứng và có biện pháp vận hành tương ứng.

## 9. Phân biệt giả định, ràng buộc và phụ thuộc

Ba khái niệm này thường bị trộn lẫn nhưng cần được ghi riêng.

| Khái niệm | Định nghĩa | Ví dụ | Cách quản lý |
| --- | --- | --- | --- |
| Giả định (assumption) | Điều được tạm xem là đúng để lập kế hoạch nhưng chưa được xác nhận đầy đủ | Sandbox mô phỏng đúng các mã lỗi chính của provider | Xác minh, ghi người phụ trách và đánh giá nếu sai |
| Ràng buộc (constraint) | Giới hạn đã biết mà nhóm phải tuân theo | Chỉ có một môi trường staging dùng chung | Lập kế hoạch trong giới hạn hoặc xin thay đổi có thẩm quyền |
| Phụ thuộc (dependency) | Đầu vào, dịch vụ hoặc hành động cần từ bên khác để hoàn thành công việc | Nhóm dữ liệu cung cấp fixture trước khi chạy integration test | Gán owner, mốc cần có và phương án khi trễ |

Ví dụ, “staging sẽ luôn sẵn sàng” là giả định nếu chưa có cam kết. “Chỉ được dùng staging ngoài giờ cao điểm” là ràng buộc nếu đã được quy định. “Nhóm nền tảng cấp chứng thư trước ngày kiểm thử” là phụ thuộc.

### 9.1. Viết giả định có thể kiểm chứng

Mỗi giả định quan trọng nên có:

- Mã hoặc tên nhận diện.
- Phát biểu rõ điều đang được giả định.
- Lý do và bằng chứng hiện có.
- Mức độ quan trọng và hậu quả nếu sai.
- Người hoặc nhóm xác minh.
- Thời điểm cần xác minh.
- Kế hoạch thay thế nếu giả định không đúng.

Ví dụ:

| ID | Giả định | Vì sao quan trọng? | Cách xác minh | Owner / hạn |
| --- | --- | --- | --- | --- |
| A-01 | Sandbox hỗ trợ callback thành công, thất bại và timeout | Quyết định phạm vi contract/integration test | Đối chiếu tài liệu và chạy thử ba tình huống | Integration owner / trước test cycle |
| A-02 | Bộ dữ liệu tổng hợp đại diện phân bố đơn hàng giờ cao điểm | Ảnh hưởng kết quả load test | So sánh phân bố kích thước giỏ hàng và tần suất giao dịch | Data steward / trước performance test |
| A-03 | Mọi consumer đang dùng phiên bản event schema được liệt kê | Ảnh hưởng tương thích khi phát hành | Kiểm tra inventory và contract test | Service owner / trước release candidate |

Giả định không được xác minh không tự trở thành sự thật theo thời gian. Nếu hết hạn mà chưa xác minh, cần nêu trạng thái và đánh giá tác động.

### 9.2. Đánh giá khi giả định sai

Khi một giả định bị bác bỏ:

1. Xác định phần chiến lược đang dựa vào giả định đó.
2. Đánh giá tác động tới mục tiêu, phạm vi, dữ liệu, môi trường, lịch và rủi ro.
3. Xác định có cần dừng kiểm thử hoặc giữ quyết định phát hành không.
4. Tìm phương án thay thế hoặc thu hẹp kết luận.
5. Cập nhật tài liệu, người chịu trách nhiệm và ngày hiệu lực.

Ví dụ, nếu sandbox không hỗ trợ timeout thật, nhóm không thể kết luận hành vi retry đã được xác minh đầy đủ chỉ bằng sandbox. Có thể cần fault injection trong môi trường cô lập hoặc ghi rõ khoảng trống và yêu cầu bằng chứng bổ sung.

## 10. Gắn mục tiêu và phạm vi với rủi ro

Mục tiêu và phạm vi nên có mối liên hệ tới rủi ro để tránh kiểm thử dàn trải.

Có thể lập ma trận:

| Rủi ro | Mục tiêu kiểm thử | Phạm vi | Bằng chứng dự kiến |
| --- | --- | --- | --- |
| Giao dịch thanh toán bị ghi nhận trùng | Bảo đảm một giao dịch logic chỉ tạo một charge | Retry, duplicate callback, consumer restart | Integration test, trạng thái ledger và đối soát |
| Người dùng truy cập dữ liệu tenant khác | Bảo vệ cô lập dữ liệu theo tenant | API đọc, tìm kiếm, export và quyền quản trị | Authorization tests, audit log và kiểm tra dữ liệu |
| Tìm kiếm chậm giờ cao điểm | Đáp ứng mục tiêu độ trễ ở tải dự kiến | API tìm kiếm và luồng lọc phổ biến | Load test, p95, error rate và tài nguyên |
| Mất trạng thái khi phụ thuộc gián đoạn | Phục hồi đúng sau timeout hoặc restart | Queue, database và luồng cập nhật trạng thái | Resilience test, replay, RTO/RPO khi áp dụng |

Ma trận này giúp người đọc thấy vì sao một hoạt động nằm trong phạm vi. Nếu một rủi ro quan trọng không có mục tiêu hoặc bằng chứng, cần quyết định bổ sung, chấp nhận khoảng trống có thẩm quyền hoặc thu hẹp phạm vi sản phẩm.

## 11. Xác định giới hạn của chiến lược

Không tài liệu chiến lược nào có thể bao phủ mọi tình huống. Hãy nêu giới hạn để kết luận được diễn giải đúng.

Các giới hạn thường gặp:

- Môi trường thử nghiệm khác production về quy mô hoặc cấu hình.
- Sandbox không mô phỏng hết hành vi của nhà cung cấp.
- Không thể kiểm thử một số lỗi hiếm hoặc sự kiện ở quy mô thực.
- Một số nền tảng hoặc phiên bản không nằm trong phạm vi hỗ trợ.
- Dữ liệu tổng hợp không phản ánh đầy đủ hành vi người dùng thực.
- Kiểm thử bảo mật tự động không thay thế đánh giá chuyên sâu.
- Phần kiểm thử thủ công bị giới hạn bởi thời gian và cỡ mẫu.
- Một số phụ thuộc hoặc quyền truy cập chưa sẵn sàng.

Với mỗi giới hạn đáng kể, ghi tác động tới kết luận và biện pháp bù đắp. Ví dụ, nếu load test chỉ chạy trên staging nhỏ hơn production, báo cáo cần nêu cấu hình, khác biệt và giới hạn suy rộng; không nên khẳng định chắc chắn hệ thống sẽ đạt cùng kết quả ở production.

## 12. Quản lý thay đổi bối cảnh, mục tiêu và phạm vi

Bối cảnh và phạm vi có thể thay đổi khi yêu cầu, kiến trúc, đối tác, người dùng hoặc lịch phát hành thay đổi. Tài liệu cần có cơ chế cập nhật.

Các sự kiện kích hoạt xem xét:

- Thay đổi đáng kể về yêu cầu hoặc hành trình nghiệp vụ.
- Thêm/bỏ dịch vụ, API, nhà cung cấp hoặc nền tảng.
- Thay đổi dữ liệu, schema, lưu lượng hoặc nhóm người dùng.
- Sự cố production hoặc near miss làm thay đổi hiểu biết về rủi ro.
- Thay đổi luật, hợp đồng hoặc chính sách.
- Môi trường, công cụ hoặc nguồn lực kiểm thử thay đổi.
- Giả định quan trọng bị bác bỏ hoặc phụ thuộc trễ.
- Phạm vi release hoặc tỷ lệ rollout thay đổi.

Quy trình cập nhật có thể gồm:

1. Ghi nhận thay đổi và nguồn yêu cầu.
2. Xác định phần bối cảnh, mục tiêu, phạm vi hoặc giả định bị ảnh hưởng.
3. Phân tích tác động tới rủi ro, kế hoạch, nguồn lực và tiêu chí.
4. Tham vấn và xin phê duyệt theo thẩm quyền.
5. Cập nhật phiên bản tài liệu và thông báo nhóm liên quan.
6. Kiểm tra các test, báo cáo và quyết định đang dựa trên phiên bản cũ.

Không nên sửa tài liệu âm thầm sau khi đã dùng nó để phê duyệt. Lịch sử thay đổi giúp biết quyết định nào được đưa ra dựa trên bối cảnh nào.

## 13. Cấu trúc đề xuất cho phần bối cảnh, mục tiêu, phạm vi và giả định

Có thể dùng cấu trúc sau trong tài liệu chiến lược:

```text
1. PURPOSE AND CONTEXT
   - Product / service overview
   - Business goals and critical user journeys
   - User groups and stakeholders
   - Architecture and key integrations
   - Project and organizational context

2. TESTING OBJECTIVES
   - Quality outcomes to protect
   - Risk-based priorities
   - Measures and success criteria
   - Release decision support

3. SCOPE
   - In-scope products, features and interfaces
   - Quality attributes and test levels
   - Platforms, configurations and environments
   - Out-of-scope items and reasons
   - Ownership boundaries and external interfaces

4. ASSUMPTIONS, CONSTRAINTS AND DEPENDENCIES
   - Assumption register and validation owner
   - Known constraints
   - External/internal dependencies and due dates
   - Consequences and fallback if an assumption is false

5. LIMITATIONS AND CHANGE CONTROL
   - Evidence limitations
   - Review triggers
   - Approval and version history
```

Không cần giữ nguyên tên mục nếu tổ chức đã có template. Điều quan trọng là mọi nội dung cần thiết đều có vị trí dễ tìm và được duy trì.

## 14. Ví dụ tổng hợp: chiến lược kiểm thử cho nền tảng đặt hàng

Giả sử một doanh nghiệp triển khai nền tảng đặt hàng trực tuyến mới, tích hợp cổng thanh toán và hệ thống quản lý kho.

### Bối cảnh

- Khách hàng có thể duyệt sản phẩm, tạo giỏ hàng, thanh toán, theo dõi đơn và yêu cầu hủy/hoàn tiền.
- Nhân viên hỗ trợ cần tra cứu lịch sử đơn và trạng thái thanh toán.
- Checkout xử lý yêu cầu tạo đơn; thanh toán và cập nhật kho có các bước bất đồng bộ.
- Dịch vụ phụ thuộc gồm payment provider, inventory service, notification service và hệ thống báo cáo.
- Lưu lượng tăng mạnh vào các đợt khuyến mãi; dữ liệu đơn hàng tích lũy theo thời gian.
- Nhóm phát triển triển khai theo sprint; phát hành qua pipeline CI/CD và rollout theo đợt.

### Mục tiêu

1. Xác minh giá, thuế, ưu đãi và tổng tiền nhất quán giữa giỏ hàng, thanh toán và hóa đơn.
2. Bảo đảm retry hoặc callback trùng không tạo giao dịch logic trùng.
3. Xác minh quyền truy cập đơn hàng theo người dùng và tenant.
4. Đo hiệu năng tìm kiếm và checkout ở tải dự kiến.
5. Xác minh hệ thống xử lý được timeout của provider và phục hồi trạng thái.
6. Cung cấp bằng chứng đủ tin cậy cho quyết định release.

### Phạm vi trong

- Hành trình duyệt sản phẩm, giỏ hàng, tạo đơn, thanh toán, hủy và hoàn tiền.
- API và hợp đồng giữa Checkout, Payment, Inventory và Notification.
- Quy tắc tính giá, ưu đãi, thuế và trạng thái đơn.
- Phân quyền khách hàng, nhân viên hỗ trợ và quản trị viên.
- Kiểm thử chức năng, unit, integration, contract, E2E, hiệu năng và phục hồi theo rủi ro.
- Các trình duyệt và thiết bị nằm trong ma trận hỗ trợ.

### Phạm vi ngoài

- Kiểm thử nội bộ mã nguồn của payment provider.
- Đánh giá xâm nhập độc lập do bên thứ ba thực hiện trong chương trình riêng.
- Kiểm thử trên thiết bị không thuộc danh sách hỗ trợ.

Những nội dung ngoài phạm vi vẫn có chủ sở hữu và bằng chứng thay thế hoặc kế hoạch riêng. Không xem việc không kiểm thử provider nội bộ là miễn trừ kiểm tra hợp đồng tích hợp.

### Giả định, ràng buộc và phụ thuộc

| Loại | Nội dung | Cách xử lý |
| --- | --- | --- |
| Giả định | Sandbox có thể mô phỏng callback thành công, từ chối và timeout | Xác minh trước integration cycle; nếu thiếu, dùng fault injection an toàn |
| Giả định | Dữ liệu tổng hợp đại diện được phân bố giỏ hàng giờ cao điểm | Data steward so sánh phân bố trước load test |
| Ràng buộc | Chỉ có một staging environment dùng chung | Lập lịch và cô lập dữ liệu theo test run |
| Phụ thuộc | Inventory team cung cấp contract và test endpoint | Gán owner và mốc bàn giao trước contract testing |

### Cách dùng ví dụ

Người đọc có thể thấy bối cảnh dẫn tới mục tiêu, mục tiêu dẫn tới phạm vi, và giả định quyết định tính khả thi của bằng chứng. Nếu sandbox không mô phỏng được timeout, chiến lược phải cập nhật phương án kiểm tra hoặc nêu giới hạn; không thể coi giả định ban đầu là bằng chứng.

## 15. Rà soát chất lượng của phần nền tảng

Trước khi phê duyệt chiến lược, hãy kiểm tra:

- Bối cảnh có giải thích những yếu tố ảnh hưởng trực tiếp đến kiểm thử không?
- Các hành trình và nhóm người dùng quan trọng đã được nêu chưa?
- Mục tiêu có mô tả kết quả và cách đánh giá không?
- Mỗi mục tiêu có liên kết với rủi ro, yêu cầu hoặc quyết định nào không?
- Phạm vi trong và ngoài có rõ ràng, có lý do và chủ sở hữu không?
- Nền tảng, cấu hình và loại kiểm thử được mô tả ở mức phù hợp không?
- Ranh giới với nhà cung cấp và nhóm khác có rõ không?
- Giả định được phân biệt với ràng buộc và phụ thuộc chưa?
- Giả định quan trọng có người xác minh, thời hạn và phương án khi sai không?
- Giới hạn bằng chứng và cách diễn giải kết quả có được ghi không?
- Có cơ chế xem xét lại khi bối cảnh hoặc phạm vi thay đổi không?

## 16. Những lỗi thường gặp khi viết

- **Chép mô tả sản phẩm chung chung:** không nêu yếu tố làm thay đổi quyết định kiểm thử.
- **Mục tiêu chỉ là hoạt động:** “chạy regression” không nói kết quả chất lượng cần đạt.
- **Dùng từ tuyệt đối:** “kiểm thử toàn bộ”, “không có lỗi”, “bảo đảm an toàn” mà không có định nghĩa và bằng chứng.
- **Không ghi ngoài phạm vi:** người đọc mặc định mọi chức năng hoặc nền tảng đều được kiểm tra.
- **Giả định ẩn:** kế hoạch phụ thuộc sandbox, dữ liệu hoặc quyền truy cập nhưng không ai xác minh.
- **Nhầm giả định với ràng buộc:** một điều chưa xác nhận bị coi như giới hạn cố định hoặc ngược lại.
- **Bỏ qua phụ thuộc:** không có owner và mốc bàn giao cho môi trường, dữ liệu hoặc dịch vụ ngoài.
- **Không nêu giới hạn:** kết quả staging bị suy rộng thành cam kết production.
- **Không cập nhật sau thay đổi:** chiến lược tiếp tục dựa vào kiến trúc hoặc yêu cầu cũ.
- **Không liên kết mục tiêu với rủi ro:** phạm vi được chọn theo thói quen, không theo tác động.

## 17. Checklist hoàn thiện bối cảnh, mục tiêu, phạm vi và giả định

- [ ] Mô tả sản phẩm, mục đích nghiệp vụ và các hành trình quan trọng.
- [ ] Xác định nhóm người dùng và bên liên quan chính.
- [ ] Nêu các đặc điểm kiến trúc, tích hợp và môi trường ảnh hưởng đến kiểm thử.
- [ ] Ghi các điều kiện tổ chức, lịch phát hành và giới hạn nguồn lực liên quan.
- [ ] Mục tiêu diễn đạt kết quả chất lượng, không chỉ hoạt động.
- [ ] Mục tiêu có chỉ số hoặc tiêu chí đánh giá phù hợp.
- [ ] Mục tiêu liên kết với yêu cầu, rủi ro và bằng chứng dự kiến.
- [ ] Phạm vi trong nêu rõ chức năng, chất lượng, nền tảng và tầng kiểm thử.
- [ ] Phạm vi ngoài có lý do, chủ sở hữu và cách xử lý rủi ro.
- [ ] Ranh giới trách nhiệm với nhà cung cấp và nhóm khác được mô tả.
- [ ] Giả định, ràng buộc và phụ thuộc được phân biệt.
- [ ] Giả định quan trọng có cách xác minh, owner, hạn và phương án dự phòng.
- [ ] Giới hạn của môi trường và bằng chứng được ghi rõ.
- [ ] Có trigger và quy trình cập nhật khi bối cảnh hoặc phạm vi thay đổi.

## 18. Những điểm cần ghi nhớ

- Bối cảnh giải thích sản phẩm, người dùng, nghiệp vụ, kiến trúc và điều kiện tổ chức ảnh hưởng đến kiểm thử.
- Mục tiêu mô tả kết quả chất lượng cần đạt; hoạt động và chỉ số là phương tiện để đánh giá.
- Phạm vi cần nói rõ nội dung trong phạm vi, ngoài phạm vi, nền tảng, tầng kiểm thử và ranh giới trách nhiệm.
- Giả định là điều chưa được xác minh đầy đủ; ràng buộc là giới hạn đã biết; phụ thuộc là đầu vào hoặc hành động cần từ bên khác.
- Giả định quan trọng phải có bằng chứng, người xác minh, thời hạn và phương án nếu sai.
- Mục tiêu và phạm vi nên liên kết với rủi ro để ưu tiên đúng khu vực.
- Giới hạn môi trường và phép đo phải được ghi để tránh suy rộng kết luận.
- Bối cảnh, mục tiêu, phạm vi và giả định cần được xem xét lại khi yêu cầu, kiến trúc, dữ liệu hoặc kế hoạch phát hành thay đổi.

## Câu hỏi tự kiểm tra

1. Bối cảnh, mục tiêu, phạm vi và giả định trả lời những câu hỏi khác nhau nào trong tài liệu chiến lược kiểm thử?
2. Hãy mô tả ba yếu tố nghiệp vụ và ba yếu tố kỹ thuật có thể làm thay đổi ưu tiên kiểm thử của một sản phẩm.
3. Phân biệt mục tiêu kiểm thử, hoạt động kiểm thử, chỉ số và tiêu chí thành công bằng một ví dụ.
4. Vì sao mục tiêu “kiểm thử đầy đủ trước release” chưa đủ cụ thể để lập kế hoạch?
5. Một phần chức năng được loại khỏi phạm vi do thiếu sandbox. Cần ghi những thông tin nào để người đọc hiểu rủi ro còn lại?
6. Phân biệt giả định, ràng buộc và phụ thuộc bằng ví dụ từ một dự án tích hợp API.
7. Nếu giả định sandbox mô phỏng đúng timeout bị bác bỏ, nhóm cần đánh giá và cập nhật những phần nào của chiến lược?
8. Làm thế nào liên kết một rủi ro sản phẩm với mục tiêu, phạm vi và bằng chứng kiểm thử?
9. Hãy viết phần bối cảnh, mục tiêu, phạm vi trong/ngoài và ba giả định cho một sản phẩm bạn biết.
10. Những sự kiện nào nên kích hoạt việc rà soát lại bối cảnh, mục tiêu, phạm vi và giả định?
