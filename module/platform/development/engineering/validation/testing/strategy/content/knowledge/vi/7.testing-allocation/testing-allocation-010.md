# Đánh đổi giữa cô lập, độ giống thực tế, tốc độ và khả năng chẩn đoán

Phân bổ kiểm thử là quyết định nên kiểm tra hành vi ở đâu, với những thành phần thật hay thay thế nào, trong môi trường nào và bằng cách nào để kết quả vừa đáng tin cậy vừa hữu ích. Bốn yếu tố thường phải cân bằng là **mức độ cô lập**, **độ giống thực tế**, **tốc độ thực thi** và **khả năng chẩn đoán**. Tối ưu một yếu tố riêng lẻ có thể làm suy yếu các yếu tố còn lại.

Ví dụ, một kiểm thử đơn vị dùng đối tượng giả (mock) có thể chạy rất nhanh và chỉ ra chính xác hàm nào xử lý sai. Tuy nhiên, nó không chứng minh rằng ứng dụng giao tiếp đúng với cơ sở dữ liệu hoặc cổng thanh toán thật. Một kiểm thử đầu cuối chạy qua toàn bộ hệ thống và các dịch vụ thật có độ gần thực tế cao hơn, nhưng thường chậm hơn, khó thiết lập và khi thất bại có thể khó xác định thành phần gây lỗi.

Chiến lược phù hợp thường phân bổ nhiều loại kiểm thử ở các mức khác nhau. Mục tiêu là đặt mỗi kiểm tra tại ranh giới tạo ra bằng chứng tốt nhất cho rủi ro cần xác nhận, đồng thời giữ chi phí chạy và điều tra trong giới hạn có thể quản lý.

## 1. Bốn yếu tố cần cân bằng

### 1.1. Mức độ cô lập (isolation)

Cô lập mô tả mức độ một kiểm thử có thể chạy mà không phụ thuộc vào trạng thái, dữ liệu hoặc sự sẵn sàng của thành phần bên ngoài phạm vi đang kiểm tra. Kiểm thử càng cô lập thì càng dễ kiểm soát đầu vào, thiết lập trạng thái ban đầu và lặp lại trong điều kiện giống nhau.

Các kỹ thuật tạo cô lập gồm:

- Thay thế dịch vụ bên ngoài bằng stub, fake hoặc mock.
- Dùng cơ sở dữ liệu tạm thời, schema riêng hoặc transaction có thể rollback.
- Tạo dữ liệu riêng cho từng ca kiểm thử và dọn dẹp sau khi chạy.
- Kiểm soát đồng hồ, số ngẫu nhiên, luồng bất đồng bộ và các yếu tố môi trường.
- Chạy thành phần trong tiến trình hoặc container riêng với cấu hình xác định.

Cô lập giúp giảm nhiễu do hệ thống khác, tăng tốc và làm lỗi dễ khoanh vùng hơn. Tuy nhiên, nếu thay thế quá nhiều thành phần, kiểm thử có thể chỉ xác nhận cách các mock được cấu hình. Nó có thể bỏ qua sai lệch giao thức, cấu hình, truy vấn, thứ tự sự kiện hoặc hành vi thật của phụ thuộc.

### 1.2. Độ giống thực tế (realism)

Độ giống thực tế cho biết điều kiện kiểm thử phản ánh môi trường sử dụng và hành vi của các phụ thuộc thật đến mức nào. Một kiểm thử có độ giống thực tế cao có thể dùng cấu hình gần sản xuất, dữ liệu đại diện, giao thức thật và các dịch vụ thực tế.

Độ giống thực tế có thể tăng khi:

- Dùng cơ sở dữ liệu cùng loại và phiên bản gần với môi trường mục tiêu.
- Gọi dịch vụ tích hợp qua giao thức thật hoặc môi trường sandbox chính thức.
- Kiểm tra ứng dụng qua API, giao diện hoặc luồng người dùng thực tế.
- Dùng dữ liệu có phân bố, kích thước và đặc điểm gần với dữ liệu vận hành, sau khi đã bảo vệ thông tin nhạy cảm.
- Giữ cấu hình mạng, quyền hạn, cơ chế xác thực và cách triển khai tương đương môi trường đích.

Độ giống thực tế giúp phát hiện vấn đề chỉ xuất hiện khi các thành phần tương tác, chẳng hạn khác biệt về SQL, serialization, timeout, TLS, quyền truy cập hoặc cấu hình triển khai. Đổi lại, kiểm thử có thể chậm, phụ thuộc môi trường và khó tái tạo khi dịch vụ bên ngoài thay đổi hoặc gặp sự cố.

Không phải cứ dùng toàn bộ hệ thống thật là kiểm thử tốt hơn. Một dịch vụ sandbox có thể không tái hiện đầy đủ độ trễ, lỗi hiếm hoặc giới hạn của môi trường sản xuất. Độ giống thực tế cần được đánh giá theo rủi ro cụ thể, không chỉ theo số lượng thành phần thật.

### 1.3. Tốc độ thực thi (execution speed)

Tốc độ thực thi là thời gian cần để chuẩn bị, chạy và nhận kết quả kiểm thử. Tốc độ ảnh hưởng trực tiếp đến tần suất kiểm tra và thời gian phản hồi cho lập trình viên.

Kiểm thử thường chạy nhanh hơn khi:

- Phạm vi nhỏ và số lượng thành phần phụ thuộc ít.
- Không cần khởi động nhiều dịch vụ hoặc tạo dữ liệu lớn.
- Dùng dữ liệu cố định, môi trường ổn định và tránh chờ dịch vụ bên ngoài.
- Có thể chạy song song mà không tranh chấp tài nguyên hoặc dữ liệu dùng chung.
- Chỉ thực hiện các bước cần thiết để xác nhận mục tiêu của kiểm thử.

Kiểm thử nhanh giúp phát hiện lỗi sớm và có thể chạy thường xuyên trong quá trình phát triển. Tuy nhiên, chỉ tối ưu tốc độ có thể dẫn đến quá nhiều mock, kiểm tra quá hẹp hoặc bỏ qua tích hợp quan trọng. Tốc độ cần được cân nhắc cùng với giá trị của bằng chứng và chi phí bảo trì.

### 1.4. Khả năng chẩn đoán (diagnosability)

Khả năng chẩn đoán là mức độ dễ dàng xác định nguyên nhân khi kiểm thử thất bại hoặc kết quả bất thường. Một kiểm thử có khả năng chẩn đoán tốt cho biết điều kiện nào đã được dùng, bước nào thất bại, trạng thái hệ thống ra sao và dữ liệu nào hỗ trợ điều tra.

Khả năng chẩn đoán được cải thiện nhờ:

- Phạm vi kiểm thử vừa đủ nhỏ để khoanh vùng nguyên nhân.
- Tên kiểm thử và thông báo lỗi mô tả hành vi đang được xác nhận.
- Log, trace, ảnh chụp, phản hồi API và dữ liệu đầu vào được lưu đúng mức.
- Mỗi ca dùng dữ liệu riêng và có thể chạy độc lập.
- Có thể tái hiện thất bại với cùng phiên bản, cấu hình và dữ liệu.
- Kiểm tra được các trạng thái trung gian, không chỉ kết quả cuối cùng.

Một kiểm thử đầu cuối có thể phát hiện luồng thanh toán thất bại, nhưng nếu chỉ báo “checkout failed” thì nhóm khó biết nguyên nhân nằm ở giao diện, dịch vụ đơn hàng, cơ sở dữ liệu hay cổng thanh toán. Ngược lại, kiểm thử một thành phần nhỏ thường chỉ ra chính xác hàm hoặc quy tắc gây lỗi, nhưng có thể không phát hiện được sự không tương thích giữa các thành phần.

Khả năng chẩn đoán không đồng nghĩa với việc thu thập càng nhiều log càng tốt. Log quá lớn, chứa dữ liệu nhạy cảm hoặc thiếu cấu trúc có thể làm điều tra khó hơn. Bằng chứng cần đủ để giải thích kết quả, có thể truy vết và tuân thủ chính sách bảo vệ dữ liệu.

## 2. Mối quan hệ và các đánh đổi

Bốn yếu tố có xu hướng tác động lẫn nhau:

| Quyết định | Lợi ích thường có | Chi phí hoặc giới hạn có thể xuất hiện |
|---|---|---|
| Tăng cô lập bằng mock/fake | Chạy nhanh, kết quả ổn định, khoanh vùng lỗi dễ | Giảm độ giống thực tế; có thể bỏ sót sai lệch tích hợp |
| Dùng nhiều phụ thuộc thật | Độ giống thực tế cao, kiểm tra được giao thức và cấu hình thật | Chạy chậm hơn, phụ thuộc môi trường, lỗi có thể khó khoanh vùng |
| Mở rộng kiểm thử đầu cuối | Xác nhận được hành trình hoàn chỉnh qua nhiều lớp | Tốn thời gian, dữ liệu và bảo trì; thất bại khó xác định nguyên nhân |
| Thu hẹp kiểm thử vào một thành phần | Dễ chẩn đoán và lặp lại, phù hợp chạy thường xuyên | Không chứng minh được hành vi toàn hệ thống |
| Chạy nhiều kiểm thử song song | Giảm thời gian chờ tổng thể | Tranh chấp dữ liệu, cổng dịch vụ, CPU hoặc tài nguyên môi trường có thể làm kết quả không ổn định |
| Thu thập nhiều bằng chứng vận hành | Hỗ trợ phân tích sự cố phức tạp | Tăng chi phí lưu trữ, xử lý và nguy cơ lộ dữ liệu nếu không kiểm soát |

Đây là xu hướng, không phải quy luật tuyệt đối. Một kiểm thử tích hợp có thể nhanh nếu phụ thuộc nhẹ và môi trường được tối ưu; một kiểm thử đơn vị có thể chậm nếu tạo fixture phức tạp hoặc truy cập tài nguyên dùng chung. Cần đo thời gian và phân tích nguyên nhân thực tế của bộ kiểm thử thay vì suy luận chỉ từ tên loại kiểm thử.

### 2.1. Cô lập và độ giống thực tế

Hai yếu tố này thường kéo theo hai hướng khác nhau. Thay dịch vụ thật bằng mock giúp kiểm soát hành vi và tạo tình huống lỗi hiếm, nhưng không xác nhận dịch vụ thật có tuân theo hợp đồng hay không. Dùng dịch vụ thật kiểm tra được tích hợp thực tế hơn, nhưng kết quả có thể phụ thuộc mạng, giới hạn tốc độ hoặc trạng thái của nhà cung cấp.

Giải pháp thường là kiểm tra ở nhiều ranh giới:

- Kiểm thử đơn vị cô lập logic nghiệp vụ và các nhánh điều kiện.
- Kiểm thử hợp đồng xác nhận hai bên thống nhất cấu trúc dữ liệu và giao thức.
- Kiểm thử tích hợp chọn lọc xác nhận hành vi với phụ thuộc thật.
- Kiểm thử đầu cuối xác nhận một số luồng quan trọng qua toàn hệ thống.

Nhờ đó, nhóm có thể kiểm soát phần lớn trường hợp thường gặp nhưng vẫn thu thập bằng chứng thực tế ở những ranh giới có rủi ro cao.

### 2.2. Tốc độ và độ giống thực tế

Khởi động cơ sở dữ liệu thật, nhiều dịch vụ và giao diện trình duyệt thường mất thời gian hơn gọi hàm trong bộ nhớ. Tuy vậy, bỏ qua tích hợp để đạt thời gian chạy ngắn có thể làm lỗi nghiêm trọng chỉ xuất hiện sau khi triển khai.

Không cần chạy mọi kiểm thử thực tế ở mọi lần commit. Nhóm có thể chạy các kiểm tra nhanh ở giai đoạn phát triển, kiểm thử tích hợp chọn lọc trong pipeline, và bộ kiểm thử rộng hơn theo lịch hoặc trước mốc phát hành. Cách phân tầng này giữ phản hồi sớm trong khi vẫn có thời điểm kiểm tra những rủi ro cần môi trường gần thực tế.

### 2.3. Tốc độ và khả năng chẩn đoán

Một kiểm thử quá rộng có thể chạy lâu và tạo ra lỗi khó hiểu. Thu hẹp phạm vi giúp kết quả nhanh và dễ khoanh vùng, nhưng có thể bỏ lỡ lỗi chỉ xuất hiện khi nhiều thành phần phối hợp. Để cân bằng, hãy dùng kiểm thử nhỏ cho quy tắc và logic, sau đó dùng một số kiểm thử rộng để xác nhận các hành trình quan trọng.

Nếu cần chạy song song, dữ liệu phải được cách ly theo worker hoặc ca kiểm thử. Dùng chung một tài khoản, giỏ hàng hay bản ghi có thể khiến các ca ghi đè trạng thái của nhau. Khi đó, lỗi có vẻ ngẫu nhiên dù nguyên nhân là tranh chấp dữ liệu.

## 3. Đặt kiểm thử ở đúng ranh giới

Mỗi loại kiểm thử nên trả lời một câu hỏi cụ thể. Việc chọn ranh giới cần dựa trên mục tiêu và rủi ro, không nên áp dụng máy móc một tỷ lệ cố định giữa kiểm thử đơn vị, tích hợp và đầu cuối.

| Mức kiểm thử | Cô lập thường gặp | Độ giống thực tế | Tốc độ tương đối | Khả năng chẩn đoán thường gặp |
|---|---|---|---|---|
| Đơn vị/thành phần | Cao, phụ thuộc thường được thay thế hoặc kiểm soát | Thấp đến trung bình | Nhanh | Cao nếu ca nhỏ và thông báo rõ |
| Hợp đồng | Kiểm soát hai phía và thông điệp trao đổi | Trung bình đến cao ở ranh giới giao tiếp | Nhanh đến trung bình | Cao khi báo rõ sai lệch schema hoặc giao thức |
| Tích hợp | Một số phụ thuộc thật, phạm vi giới hạn | Trung bình đến cao | Trung bình | Trung bình đến cao nếu có log và trace |
| Hệ thống/đầu cuối | Thấp hơn, nhiều lớp cùng tham gia | Cao hơn | Chậm hơn | Thường thấp hơn nếu thiếu quan sát trung gian |
| Chấp nhận trong bối cảnh sử dụng | Phụ thuộc vào môi trường và người dùng đại diện | Cao trong bối cảnh được mô phỏng hoặc triển khai | Thường tốn thời gian tổ chức | Phụ thuộc vào tiêu chí, ghi nhận và khả năng tái hiện |

Các mức “thấp”, “cao”, “nhanh” và “chậm” trong bảng là xu hướng phổ biến. Cách triển khai cụ thể có thể làm thay đổi đáng kể kết quả. Ví dụ, một kiểm thử hợp đồng có thể dùng dữ liệu cố định và chạy rất nhanh; một kiểm thử đầu cuối có thể khó chẩn đoán nếu chỉ kiểm tra trạng thái cuối cùng mà không lưu trace.

### 3.1. Kiểm thử đơn vị và thành phần

Đặt logic có thể kiểm tra độc lập ở phạm vi nhỏ. Dùng fake hoặc mock khi cần mô phỏng lỗi phụ thuộc, thời gian hoặc kết quả khó tạo ra bằng dịch vụ thật. Giữ các kiểm tra này nhanh và tập trung vào hành vi mà thành phần chịu trách nhiệm.

Không nên mock mọi đối tượng chỉ để làm kiểm thử chạy được. Nếu mock lặp lại chi tiết nội bộ của chính thành phần đang kiểm tra, ca kiểm thử có thể trở nên mong manh và phản ánh cấu trúc triển khai thay vì hợp đồng hành vi.

### 3.2. Kiểm thử hợp đồng

Kiểm thử hợp đồng xác nhận bên cung cấp và bên sử dụng thống nhất về cấu trúc, kiểu dữ liệu, trường bắt buộc, quy tắc lỗi và giao thức trao đổi. Nó hữu ích khi cần độ tin cậy ở ranh giới dịch vụ mà không phải khởi chạy toàn bộ hệ thống.

Hợp đồng đạt không chứng minh mọi hành vi của dịch vụ thật đều đúng. Nó xác nhận các tương tác được mô tả trong hợp đồng. Các rủi ro về hiệu năng, độ tin cậy, cấu hình và hành vi ngoài hợp đồng vẫn có thể cần kiểm thử khác.

### 3.3. Kiểm thử tích hợp

Dùng thành phần thật tại những ranh giới quan trọng, chẳng hạn ứng dụng với cơ sở dữ liệu, message broker hoặc API của đối tác. Giữ phạm vi vừa đủ để biết lỗi có thể phát sinh ở đâu. Cung cấp dữ liệu riêng, log truy vấn hoặc trace xuyên dịch vụ để việc điều tra không phụ thuộc vào phỏng đoán.

Không nhất thiết phải kết nối mọi tích hợp thật trong mọi kiểm thử. Chọn phụ thuộc dựa trên mức rủi ro, tính ổn định của sandbox, chi phí và khả năng quan sát.

### 3.4. Kiểm thử hệ thống và đầu cuối

Kiểm tra các luồng có ý nghĩa với người dùng qua nhiều lớp, ví dụ đăng nhập, tạo đơn, thanh toán và nhận xác nhận. Chỉ giữ số lượng luồng đầu cuối đủ để xác nhận các hành trình có giá trị cao. Dùng kiểm thử ở mức thấp hơn để bao phủ nhiều biến thể và nhánh lỗi.

Khi kiểm thử đầu cuối thất bại, cần có khả năng xem trạng thái trung gian: request/response, log theo mã tương quan, trạng thái cơ sở dữ liệu cần thiết và sự kiện từ các dịch vụ liên quan. Điều này giúp biến một tín hiệu “luồng không hoàn tất” thành thông tin có thể hành động.

## 4. Ví dụ: phân bổ kiểm thử cho chức năng thanh toán

Giả sử một hệ thống thương mại điện tử có luồng thanh toán gồm tính tổng tiền, tạo đơn, gọi cổng thanh toán và cập nhật trạng thái. Mỗi rủi ro cần loại bằng chứng khác nhau.

| Rủi ro hoặc câu hỏi | Kiểm thử phù hợp | Lý do lựa chọn |
|---|---|---|
| Quy tắc tính thuế và giảm giá có đúng không? | Kiểm thử đơn vị cho các tổ hợp và giá trị biên | Nhanh, cô lập logic và chỉ rõ trường hợp tính sai |
| Dịch vụ thanh toán gửi và nhận đúng cấu trúc thông điệp không? | Kiểm thử hợp đồng | Xác nhận cấu trúc và quy tắc giao tiếp ở ranh giới |
| Giao dịch và đơn hàng có được lưu nhất quán không? | Kiểm thử tích hợp với cơ sở dữ liệu và sandbox chọn lọc | Xác nhận hành vi phối hợp giữa các thành phần thật |
| Gửi lại yêu cầu sau timeout có tạo giao dịch trùng không? | Kiểm thử tích hợp với mô phỏng timeout, kết hợp kiểm thử đầu cuối cho luồng quan trọng | Cần kiểm tra idempotency và trạng thái xuyên nhiều thành phần |
| Khách hàng có thể hoàn tất thanh toán và nhận thông báo đúng không? | Một số kiểm thử đầu cuối và chấp nhận | Xác nhận hành trình sử dụng thực tế |

Ví dụ về phân bổ:

1. Kiểm tra hàng trăm tổ hợp tính tiền bằng kiểm thử đơn vị với dữ liệu xác định.
2. Kiểm tra các thông điệp thanh toán quan trọng bằng kiểm thử hợp đồng.
3. Chạy tập kiểm thử tích hợp giới hạn với cơ sở dữ liệu cùng loại và sandbox của nhà cung cấp.
4. Chạy một số luồng đầu cuối cho thanh toán thành công, thất bại, hủy và gửi lại yêu cầu.
5. Trong phiên thăm dò, thử các tình huống mất kết nối, phản hồi đến muộn và thao tác đồng thời để tìm rủi ro chưa được mô tả.

Cách phân bổ này sử dụng kiểm thử nhanh để bao phủ nhiều trường hợp logic, và dành kiểm thử có độ giống thực tế cao cho những ranh giới và hành trình có tác động lớn. Nếu một kiểm thử đầu cuối thất bại, nhóm có thể chạy lại ca hợp đồng hoặc tích hợp liên quan để thu hẹp vùng nguyên nhân.

## 5. Thiết kế kiểm thử để dễ chẩn đoán

Khả năng chẩn đoán cần được thiết kế từ đầu, không chỉ bổ sung sau khi bộ kiểm thử đã trở nên khó bảo trì.

### 5.1. Giữ mỗi kiểm thử tập trung vào một mục tiêu

Một ca kiểm thử nên xác nhận một hành vi hoặc một nhóm hành vi có liên quan chặt chẽ. Nếu một ca vừa tạo tài khoản, cập nhật hồ sơ, đặt hàng, thanh toán và gửi email, khi thất bại sẽ khó biết hành vi nào không đạt. Có thể giữ một số kiểm thử đầu cuối cho hành trình tổng thể, nhưng cần có kiểm thử nhỏ hơn để điều tra từng quy tắc và ranh giới.

### 5.2. Dùng dữ liệu có định danh và trạng thái rõ ràng

Mỗi ca nên tạo hoặc nhận dữ liệu có thể truy vết. Tránh phụ thuộc vào thứ tự chạy hoặc bản ghi do ca khác tạo. Nếu cần dữ liệu dùng chung, quy định quyền sở hữu, cách làm mới và cách xử lý khi nhiều ca chạy song song.

Ví dụ, mã đơn hàng và mã tương quan request có thể được đưa vào log để tìm đúng chuỗi sự kiện. Không ghi thông tin thẻ, mật khẩu hoặc dữ liệu cá nhân không cần thiết vào log kiểm thử.

### 5.3. Lưu thông tin môi trường và phiên bản

Khi kiểm thử thất bại, cần biết bản dựng, cấu hình, loại cơ sở dữ liệu, phiên bản dịch vụ phụ thuộc, trình duyệt và dữ liệu đã sử dụng. Nếu môi trường thay đổi giữa các lần chạy, việc tái hiện có thể không đáng tin cậy.

### 5.4. Tạo thông báo lỗi có ý nghĩa

Thông báo nên chỉ ra điều kiện và giá trị liên quan. Ví dụ, “expected total 950000 but received 980000 for cart C-123 after coupon SPRING” có ích hơn “assertion failed”. Trong log thực tế, cần che dữ liệu nhạy cảm và chỉ giữ định danh cần thiết.

### 5.5. Dùng log, metric và trace theo mục đích

- **Log** ghi lại sự kiện và ngữ cảnh xử lý.
- **Metric** cho thấy xu hướng hoặc giá trị định lượng như độ trễ, số lỗi và số lần thử lại.
- **Trace** liên kết các bước của một yêu cầu qua nhiều dịch vụ.

Với kiểm thử tích hợp hoặc đầu cuối, mã tương quan (correlation ID) giúp nối log và trace của cùng một luồng. Cần bảo đảm thời gian hệ thống có thể đối chiếu và log không tiết lộ dữ liệu bí mật.

## 6. Kiểm soát tính ổn định và khả năng lặp lại

Một kiểm thử không ổn định (flaky test) có thể lúc đạt, lúc thất bại dù mã sản phẩm không thay đổi. Nguyên nhân thường gặp gồm phụ thuộc thời gian, tranh chấp dữ liệu, chờ bất đồng bộ không đúng cách, dịch vụ ngoài không ổn định, thứ tự chạy và tài nguyên dùng chung.

Để giảm hiện tượng này:

- Dùng đồng hồ giả hoặc điều khiển thời gian khi kiểm tra logic phụ thuộc thời gian.
- Chờ điều kiện thực tế thay vì sleep một khoảng cố định không bảo đảm.
- Cô lập dữ liệu và tài nguyên giữa các ca.
- Thiết lập timeout hợp lý và ghi lại lý do hết thời gian.
- Giữ phụ thuộc bên ngoài ở mức cần thiết; kiểm tra chúng bằng bộ kiểm thử tích hợp có kiểm soát.
- Theo dõi tỷ lệ thất bại không ổn định và điều tra nguyên nhân gốc.

Không nên tự động chạy lại mọi kiểm thử thất bại cho đến khi đạt rồi xem đó là thành công. Retry có thể che giấu lỗi thật. Nếu phải thử lại để xác định tính không ổn định, cần lưu tất cả kết quả, số lần chạy và nguyên nhân nghi ngờ; báo cáo phải phân biệt lần chạy đạt sau retry với lần chạy đầu tiên thất bại.

## 7. Phân bổ theo giai đoạn và mức độ quan trọng

Không phải mọi thay đổi đều cần chạy toàn bộ bộ kiểm thử. Có thể tổ chức các lớp kiểm tra theo thời điểm để giữ phản hồi nhanh và vẫn có đủ bằng chứng trước các mốc quan trọng.

| Giai đoạn | Kiểm tra thường phù hợp | Mục đích |
|---|---|---|
| Khi phát triển cục bộ | Kiểm thử đơn vị/thành phần, kiểm tra tĩnh và một số kiểm thử nhanh | Phát hiện lỗi logic sớm, hỗ trợ chỉnh sửa liên tục |
| Khi tạo pull request hoặc tích hợp | Kiểm thử đơn vị, hợp đồng và tích hợp chọn lọc | Xác nhận thay đổi không phá vỡ các ranh giới quan trọng |
| Sau khi triển khai môi trường kiểm thử | Kiểm thử hệ thống, đầu cuối trọng yếu và kiểm tra môi trường | Xác nhận bản dựng và cấu hình hoạt động cùng nhau |
| Trước phát hành | Bộ kiểm thử theo rủi ro, hồi quy, phi chức năng và chấp nhận | Thu thập bằng chứng cho quyết định phát hành |
| Sau phát hành | Smoke test, kiểm tra sức khỏe và giám sát vận hành | Xác nhận dịch vụ hoạt động trong môi trường thật và phát hiện bất thường sớm |

Đây là mẫu tổ chức, không phải lịch bắt buộc. Một dự án có thể cần kiểm thử tích hợp sớm hơn nếu phụ thuộc là nguồn rủi ro chính. Một thay đổi nhỏ vẫn có thể yêu cầu kiểm tra rộng nếu ảnh hưởng đến xác thực, dữ liệu hoặc cơ chế thanh toán.

Ưu tiên chạy kiểm thử theo tác động và khả năng lỗi. Những hành vi cốt lõi, dữ liệu quan trọng, quyền truy cập, tích hợp mới hoặc thành phần vừa thay đổi thường cần được kiểm tra sớm. Khi bộ kiểm thử lớn, có thể chọn tập kiểm tra theo vùng mã thay đổi, quan hệ phụ thuộc và rủi ro, nhưng cần có cơ chế chạy bộ rộng hơn định kỳ để tránh vùng ít thay đổi bị bỏ quên.

## 8. Đánh giá chiến lược phân bổ

Để biết phân bổ có phù hợp không, hãy theo dõi cả chi phí và giá trị của bằng chứng. Một số chỉ số hữu ích:

- Thời gian chạy theo từng nhóm kiểm thử và tổng thời gian phản hồi của pipeline.
- Tỷ lệ kiểm thử không ổn định, số lần retry và nguyên nhân thất bại.
- Thời gian trung bình từ lúc phát hiện thất bại đến khi xác định được nguyên nhân.
- Tỷ lệ lỗi được phát hiện ở từng mức kiểm thử và lỗi lọt sang giai đoạn sau.
- Mức độ bao phủ yêu cầu hoặc rủi ro quan trọng bằng kiểm thử phù hợp.
- Chi phí thiết lập, vận hành và bảo trì môi trường cùng dữ liệu.
- Tỷ lệ kiểm thử bị chặn do dịch vụ, môi trường hoặc dữ liệu không sẵn sàng.

Không nên dùng một chỉ số đơn lẻ để kết luận chiến lược tốt hay kém. Tăng tốc độ pipeline nhưng làm tăng lỗi lọt ra sản xuất có thể là đánh đổi không chấp nhận được. Giảm số lỗi lọt ra nhưng khiến mỗi thay đổi phải chờ nhiều giờ cũng có thể làm giảm hiệu quả phát triển. Cần xem xét mục tiêu chất lượng, mức rủi ro, tần suất thay đổi và chi phí vận hành của nhóm.

Khi điều chỉnh, hãy tìm nguyên nhân của chi phí lớn nhất. Nếu kiểm thử đầu cuối chậm vì khởi tạo dữ liệu, tối ưu fixture hoặc chia dữ liệu có thể giúp mà không giảm độ giống thực tế. Nếu lỗi khó chẩn đoán vì thiếu trace, bổ sung quan sát có thể đem lại giá trị lớn hơn việc viết thêm nhiều ca. Nếu kiểm thử đơn vị phụ thuộc quá nhiều mock, bổ sung kiểm thử hợp đồng hoặc tích hợp ở ranh giới cần thiết sẽ tăng độ tin cậy.

## 9. Những sai lầm thường gặp

- **Tối đa hóa cô lập:** Mock quá nhiều khiến kiểm thử không còn xác nhận giao tiếp với phụ thuộc thật.
- **Tối đa hóa độ giống thực tế:** Chạy mọi ca qua toàn hệ thống làm phản hồi chậm, tốn tài nguyên và khó điều tra.
- **Tối đa hóa tốc độ:** Bỏ qua các ranh giới có rủi ro cao hoặc giảm dữ liệu đến mức không còn đại diện.
- **Chỉ nhìn kết quả cuối:** Không lưu trạng thái trung gian khiến lỗi xuyên dịch vụ khó truy nguyên.
- **Chia sẻ dữ liệu giữa các ca:** Tạo tranh chấp, phụ thuộc thứ tự và lỗi không ổn định.
- **Nhầm mock với xác nhận hợp đồng:** Mock phản ánh hành vi do kiểm thử định nghĩa; nó không chứng minh dịch vụ thật tuân thủ hợp đồng.
- **Cho rằng kiểm thử đầu cuối luôn đáng tin hơn:** Một kiểm thử rộng có thể thất bại do môi trường, dữ liệu hoặc dịch vụ ngoài, và vẫn bỏ qua nhiều biến thể.
- **Dùng retry để che lỗi không ổn định:** Kết quả đạt sau nhiều lần thử không xóa đi tín hiệu thất bại ban đầu.
- **Đo tốc độ mà bỏ qua thời gian điều tra:** Một bộ kiểm thử chạy nhanh nhưng mất hàng giờ để tìm nguyên nhân có thể chậm hơn trong toàn bộ chu trình sửa lỗi.

## 10. Quy trình ra quyết định thực tế

Trước khi thêm hoặc thay đổi một nhóm kiểm thử, hãy trả lời lần lượt:

1. **Rủi ro nào cần xác nhận?** Nêu hành vi hoặc thuộc tính chất lượng và hậu quả nếu sai.
2. **Ranh giới nào tạo bằng chứng phù hợp nhất?** Chọn thành phần, hợp đồng, tích hợp, hệ thống hoặc bối cảnh người dùng.
3. **Cần thành phần thật đến mức nào?** Xác định phụ thuộc nào có thể thay thế và phụ thuộc nào phải kiểm tra thật.
4. **Tốc độ cần đạt là bao nhiêu?** Xác định thời điểm cần phản hồi và tần suất chạy.
5. **Nếu thất bại, nhóm sẽ tìm nguyên nhân bằng cách nào?** Chuẩn bị log, trace, dữ liệu và trạng thái có thể kiểm tra.
6. **Điều kiện lặp lại là gì?** Kiểm soát dữ liệu, cấu hình, thời gian và phụ thuộc để kết quả ổn định.
7. **Bằng chứng còn thiếu là gì?** Ghi rõ rủi ro chưa được xác nhận và nơi cần bổ sung kiểm thử.

Một chiến lược tốt không tìm cách đạt điểm tối đa ở cả bốn yếu tố trong mọi kiểm thử. Nó chọn sự cân bằng phù hợp cho từng mục tiêu: kiểm thử nhỏ để nhanh và dễ chẩn đoán, kiểm thử tích hợp để xác nhận ranh giới thật, và một số kiểm thử đầu cuối để chứng minh hành trình quan trọng. Khi được đo lường và điều chỉnh theo rủi ro, cách phân bổ này giúp nhóm phản hồi nhanh, tin cậy vào kết quả và xử lý thất bại hiệu quả hơn.
