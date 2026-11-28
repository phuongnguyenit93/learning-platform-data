# Cập nhật requirement sau incident

## 1. Mục tiêu: biến bài học sự cố thành nghĩa vụ có thể kiểm chứng

Một incident có thể được khoanh vùng và dịch vụ đã hoạt động trở lại, nhưng những giả định hoặc khoảng trống khiến sự cố xảy ra vẫn còn trong đặc tả. Nếu kết quả chỉ là “cần cẩn thận hơn” hoặc “bổ sung bảo mật”, nhóm phát triển chưa có cơ sở rõ để thay đổi hành vi hệ thống.

**Cập nhật yêu cầu sau sự cố** là quá trình dùng bằng chứng và phân tích để quyết định yêu cầu nào cần được thêm, sửa, giữ nguyên hoặc thay thế; sau đó đưa thay đổi qua thiết kế, triển khai, kiểm thử và vận hành.

Đầu ra cần trả lời:

- Quan sát nào cho thấy cần thay đổi?
- Mục tiêu bảo vệ và rủi ro nào liên quan?
- Đây là thiếu yêu cầu hay hệ thống chưa thực hiện đúng yêu cầu đã có?
- Nghĩa vụ mới áp dụng cho phiên bản, dữ liệu và đường xử lý nào?
- Ai xác nhận nội dung và ai thực hiện?
- Bằng chứng nào đủ để xác nhận thay đổi đã có hiệu lực?

[NIST SP 800-61 Rev. 3](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf) đặt cải tiến từ vận hành, ứng phó và phục hồi trong nhóm ID.IM. Bài học có thể được chia sẻ và sử dụng ngay khi đủ cơ sở, không cần đợi mọi hoạt động phục hồi kết thúc.

Trong module này, vòng phản hồi cần nối được:

**Sự cố → bằng chứng → nguyên nhân và khoảng trống → rủi ro → yêu cầu → kiến trúc → kiểm thử → bằng chứng vận hành.**

Mục tiêu không phải tạo nhiều yêu cầu hơn sau mỗi incident. Mục tiêu là sửa đúng khoảng trống bảo vệ và chứng minh thay đổi hữu ích.

## 2. Những việc cần phân biệt

| Việc | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Containment | Hạn chế thiệt hại tiếp diễn | Giữ luồng xuất dữ liệu trong phạm vi bị ảnh hưởng |
| Khắc phục kỹ thuật | Loại bỏ lỗi hoặc điểm yếu cụ thể | Sửa worker dùng quyền đã lỗi thời |
| Phục hồi | Đưa hoạt động trở lại trạng thái được chấp nhận | Mở lại dịch vụ bằng cấu hình đã xác minh |
| Báo cáo sau sự cố | Ghi điều đã xảy ra, hành động và hiệu quả | Timeline, phạm vi, bằng chứng và bài học |
| Cập nhật requirement | Thay đổi nghĩa vụ cần được hệ thống hoặc quy trình đáp ứng | Yêu cầu kiểm tra quyền tại thời điểm bàn giao bản xuất |
| Kiểm chứng cải tiến | Xác nhận thay đổi đáp ứng yêu cầu | Kiểm thử thu hồi quyền khi tác vụ đang chạy |

Một hotfix có thể cần được triển khai trước khi hoàn tất đặc tả dài hạn. Vẫn phải lưu lý do, phạm vi và hạn chế của quyết định, rồi đối chiếu nó với yêu cầu và rủi ro liên quan.

Ngược lại, sửa tài liệu không có nghĩa hệ thống đã được sửa. Cần phân biệt ít nhất ba trạng thái:

- Nội dung yêu cầu đã được xác nhận.
- Cơ chế đáp ứng đã được triển khai trong phạm vi.
- Bằng chứng đánh giá và vận hành đã đủ theo tiêu chí.

Đóng incident về mặt điều phối cũng không tự đóng các công việc cải tiến. Các công việc đó phải có nơi theo dõi, người chịu trách nhiệm và điều kiện hoàn tất riêng.

## 3. Chuẩn bị đầu vào đáng tin cậy

### 3.1. Thu thập điều cần cho quyết định

Các đầu vào có thể gồm:

- Timeline phát hiện, truy cập, thay đổi quyền, containment và phục hồi.
- Log xác thực, phân quyền và hành động nghiệp vụ.
- Dữ liệu về tác vụ, hàng đợi, tệp và đường bàn giao.
- Phiên bản mã, cấu hình, policy và feature flag khi sự cố xảy ra.
- Yêu cầu, thiết kế và tiêu chí kiểm thử từng có hiệu lực.
- Kết quả điều tra và phạm vi chưa xác minh.
- Quyết định ngoại lệ, giả định hoặc rủi ro đã được chấp nhận.
- Hạn chế quan sát làm ảnh hưởng kết luận.

Không cần sao chép toàn bộ dữ liệu sự cố vào tài liệu yêu cầu. Tham chiếu đến hiện vật được bảo vệ và nêu phần kết luận cần thiết.

### 3.2. Tách sự kiện, suy luận và điều chưa biết

| Loại thông tin | Ví dụ | Cách ghi |
| --- | --- | --- |
| Quan sát có bằng chứng | Sau khi quyền bị thu hồi, hệ thống vẫn bàn giao một bản xuất cho cùng người dùng | Dẫn hiện vật, thời điểm và phạm vi xác nhận |
| Suy luận đã được kiểm tra | Worker không xét lại quyền tại thời điểm bàn giao | Nêu cơ sở phân tích hoặc tái hiện |
| Giả thuyết | Có thể còn đường tải khác bỏ qua quyền | Giao người xác minh, không ghi như sự thật |
| Khoảng trống bằng chứng | Log không đủ nối một tệp với người nhận | Nêu giới hạn của kết luận phạm vi |
| Đề xuất | Thêm điểm kiểm soát quyền trước khi bàn giao | Đưa vào thay đổi cần đánh giá và xác nhận |

Không có log truy cập không chứng minh không có truy cập. Một thao tác sai được xác nhận cũng chưa chứng minh mọi dữ liệu cùng loại đều đã bị lộ.

Kết luận cần có mức chắc chắn và giới hạn phù hợp. Nếu thông tin mới xuất hiện, sửa kết luận theo phiên bản thay vì âm thầm thay bản ghi cũ.

### 3.3. Xem xét baseline đúng thời điểm

Phải biết khi sự cố xảy ra:

- Yêu cầu nào đã có hiệu lực?
- Phiên bản nào đã được triển khai?
- Điều kiện ngoại lệ nào đang áp dụng?
- Có bằng chứng đánh giá nào và phạm vi của bằng chứng là gì?

Không dùng yêu cầu vừa bổ sung để viết lại kết luận rằng bản cũ từng đáp ứng nó. Có thể kết luận bản cũ đáp ứng một yêu cầu hẹp nhưng không bảo vệ đủ mục tiêu rộng hơn.

## 4. Phân tích nguyên nhân và phân loại khoảng trống

### 4.1. Không dừng ở nhãn “lỗi con người”

Một phát biểu như “nhân viên quên khóa quyền” chưa giải thích:

- Hệ thống có phản ánh đúng thay đổi quyền không?
- Thao tác có kết quả quan sát được không?
- Có đường nào dùng cache hoặc quyền đã chụp trước đó không?
- Quy trình có người chịu trách nhiệm và công cụ phù hợp không?
- Kiểm thử trước đây đã bao phủ điều kiện đó chưa?

Có thể có nhiều yếu tố đóng góp: giả định thiết kế, dữ liệu, cấu hình, quy trình và khả năng giám sát. Cần đủ phân tích để chọn thay đổi có tác dụng, không cần ép mọi sự cố vào đúng một nguyên nhân.

[NIST SSDF 1.1, nhóm RV.3](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf) đề cập phân tích nguyên nhân, tìm điểm yếu tương tự và cập nhật quy trình phát triển để giảm tái diễn. Điều này giúp mở rộng từ một lỗi cụ thể sang lớp vấn đề cần phòng ngừa.

### 4.2. Chọn đúng loại thay đổi

| Khoảng trống | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Đã có yêu cầu rõ nhưng triển khai vi phạm | API bỏ kiểm tra tenant dù đặc tả đã yêu cầu | Giữ nghĩa vụ, sửa triển khai và bổ sung bằng chứng/hồi quy |
| Yêu cầu thiếu phạm vi | Chỉ nói kiểm tra quyền lúc nhận tác vụ | Mở rõ phạm vi đến thời điểm xử lý hoặc bàn giao cần bảo vệ |
| Yêu cầu mơ hồ | “Thu hồi quyền nhanh” | Xác định sự kiện bắt đầu, đường xử lý, giới hạn và cách đo |
| Thiếu yêu cầu | Chưa có nghĩa vụ kiểm soát đường tải bản xuất | Thêm yêu cầu có nguồn và lý do |
| Thiết kế không đáp ứng yêu cầu | Cơ chế tải không hỗ trợ giới hạn quyền đã đặc tả | Thay thiết kế hoặc xem xét thay đổi yêu cầu đúng thẩm quyền |
| Quy trình không được thực hiện | Thay đổi quyền chưa được lưu thành công | Sửa quy trình, công cụ phản hồi và trách nhiệm |
| Đánh giá chưa đủ | Test chỉ kiểm tra tạo tác vụ, không kiểm tra tải kết quả | Mở rộng tiêu chí và kế hoạch đánh giá |
| Rủi ro đã được chấp nhận nhưng bối cảnh đổi | Giới hạn trước đây không còn đủ khi tăng loại dữ liệu | Xem xét lại quyết định và biện pháp |
| Nguồn nghĩa vụ cần làm rõ | Hợp đồng có điều kiện chưa được ánh xạ | Xác nhận phạm vi với người có trách nhiệm |

Một phát hiện có thể cần nhiều loại hành động. Tuy nhiên, không cần viết lại mọi yêu cầu chức năng nếu lỗi nằm ở việc triển khai nghĩa vụ vốn đã rõ.

### 4.3. Tìm các nơi có cùng giả định

Nếu lỗi do dùng quyền tại thời điểm xếp hàng, cần xem xét các luồng khác có cùng giả định: gửi email, xuất báo cáo, đồng bộ đối tác hoặc tác vụ xử lý tệp.

Đây là phạm vi cần phân tích, không phải kết luận rằng mọi luồng đó đều có lỗi. Mỗi kết luận phải được xác nhận bằng bằng chứng phù hợp.

## 5. Quyết định thêm, sửa, giữ hay thay thế yêu cầu

### Giữ nguyên

Chọn khi nghĩa vụ đã đúng, đủ phạm vi và vẫn phù hợp. Cập nhật việc triển khai, kiểm thử hoặc vận hành, đồng thời liên kết sự cố với yêu cầu hiện có.

### Sửa một yêu cầu

Chọn khi cần làm rõ phạm vi, điều kiện, thời điểm, tham số hoặc tiêu chí. Giữ mã nếu quy tắc quản lý của tổ chức cho phép, nhưng phải có phiên bản và lịch sử rõ.

### Thêm yêu cầu mới

Chọn khi có một nghĩa vụ độc lập chưa được mô tả, như giới hạn đường tải đã cấp hoặc khả năng audit một quyết định bàn giao.

### Tách hoặc hợp nhất

Có thể tách một câu quá rộng thành các nghĩa vụ riêng để đánh giá từng phần. Có thể hợp nhất mục trùng nếu không làm mất điều kiện hoặc mức bảo vệ.

### Thay thế hoặc retire theo phạm vi

Chỉ thực hiện khi lý do áp dụng đã hết hoặc nghĩa vụ được chuyển giao có kiểm soát. Không retire một yêu cầu chỉ vì nó làm xuất hiện phát hiện khó xử lý.

Các lựa chọn cần giữ truy vết từ nguồn, mục tiêu và rủi ro đến yêu cầu hiện hành. Không để thay đổi mã hoặc cấu trúc tài liệu làm mất nghĩa vụ từng cần bảo vệ.

## 6. Ví dụ: quyền bị thu hồi nhưng bản xuất vẫn được bàn giao

### 6.1. Bối cảnh và bằng chứng

Giả sử một nền tảng hồ sơ dự án có chức năng xuất dữ liệu bất đồng bộ. Người dùng phải thuộc tenant và có quyền Reader trên dự án để yêu cầu xuất.

Yêu cầu hiện hành:

**SR-EXP-CREATE-01 v1.0:** API tạo tác vụ xuất phải kiểm tra danh tính, tenant và quyền đọc dự án của người yêu cầu tại thời điểm tiếp nhận.

Mục tiêu bảo vệ là giới hạn bàn giao dữ liệu cho người còn quyền phù hợp. Tuy nhiên, thời gian thu hồi có hiệu lực và hành vi của tác vụ đang chạy chưa được đặc tả đủ.

Các dữ kiện giả định đã được xác nhận:

| Mã | Quan sát | Cơ sở |
| --- | --- | --- |
| F-01 | 09:59, người dùng U có quyền và tạo tác vụ J cho dự án P | Audit tiếp nhận và trạng thái quyền |
| F-02 | 10:03, thao tác thu hồi Reader của U trên P được xác nhận thành công | Bản ghi thay đổi quyền từ nguồn có thẩm quyền |
| F-03 | 10:10, worker tạo tệp cho J từ ngữ cảnh đã lưu | Trace tác vụ và thông tin kết quả |
| F-04 | 10:11, U vẫn nhận được dữ liệu xuất của P | Bằng chứng bàn giao và đối chiếu dữ liệu mẫu |
| F-05 | Worker và đường bàn giao không xét lại quyền theo trạng thái đã thu hồi | Phân tích triển khai và tái hiện có kiểm soát |

Những điều chưa được xác nhận, như mọi tệp cũ có cùng vấn đề hay có thêm người khác tải được, phải được ghi riêng để điều tra.

### 6.2. Điều gì thực sự cần thay đổi?

SR-EXP-CREATE-01 có thể đã được thực hiện đúng tại 09:59. Chỉ sửa API tạo tác vụ sẽ không giải quyết việc bàn giao lúc 10:11.

Khoảng trống gồm:

- Đặc tả chưa bao phủ thời điểm bàn giao.
- Chưa có giới hạn rõ cho hiệu lực thu hồi trên luồng xuất.
- Chưa đưa đường tải đã phát hành vào phạm vi quyền cần duy trì.
- Kiểm thử chỉ dùng quyền không đổi trong suốt tác vụ.
- Bằng chứng vận hành cần nối rõ hơn thay đổi quyền với quyết định bàn giao.

Không nên kết luận rằng cần thay toàn bộ cơ chế xác thực. Trong tình huống này, U có thể vẫn là người dùng hợp lệ cho các dự án khác. Vấn đề là quyền với P, không nhất thiết là danh tính toàn tài khoản.

Mã hóa dữ liệu lưu trữ cũng không tự ngăn ứng dụng bàn giao dữ liệu cho một người đã mất quyền. Thay đổi phải tác động đúng đường gây hại.

## 7. Viết yêu cầu sau sự cố có thể kiểm chứng

Các yêu cầu sau là đề xuất minh họa. Các ngưỡng chỉ có hiệu lực khi được xác nhận theo quy trình của tổ chức.

### 7.1. Giữ nghĩa vụ đúng tại thời điểm tiếp nhận

**SR-EXP-CREATE-01 v1.0** tiếp tục có hiệu lực vì vẫn cần kiểm tra quyền khi tạo tác vụ. Không cần sửa nó chỉ để tăng số lượng yêu cầu được cập nhật.

Bổ sung liên kết sự cố và các ca kiểm thử liên quan vào hồ sơ truy vết nếu cần.

### 7.2. Làm rõ hiệu lực thu hồi

**SR-REV-01 v1.1:** Không muộn hơn 60 giây từ khi thao tác thu hồi quyền Reader trên dự án được nguồn quản lý quyền xác nhận thành công, các yêu cầu bàn giao mới của chủ thể đối với dữ liệu dự án đó phải bị từ chối khi quyền chưa được cấp lại hợp lệ.

Ngưỡng 60 giây là giả định của bài học, không phải ngưỡng mặc định từ NIST. Chủ nghiệp vụ, chủ dữ liệu và người quản lý rủi ro cần cân nhắc mức phơi nhiễm trong khoảng chuyển tiếp trước khi xác nhận.

Đặc tả cần nêu:

- Nguồn có thẩm quyền xác nhận thay đổi quyền.
- Mốc bắt đầu và loại yêu cầu bàn giao thuộc phạm vi.
- Các nút, cache và đường tải liên quan.
- Cách quản lý sai lệch thời gian.
- Hành vi với truyền dữ liệu đã bắt đầu trước đó.
- Cách xử lý cấp lại quyền để tránh dùng trạng thái thu hồi cũ.
- Điều kiện không đạt và cách quan sát.

Không dùng thời gian trung bình thay cho giới hạn tối đa nếu yêu cầu là tối đa 60 giây.

### 7.3. Kiểm tra quyền trước bàn giao

**SR-EXP-DELIVERY-02 v1.0:** Trước mỗi yêu cầu bàn giao mới của bản xuất, hệ thống phải xác định quyền đọc có hiệu lực của người nhận đối với các tài nguyên trong tệp theo SR-REV-01. Nếu có tài nguyên ngoài quyền, hệ thống phải từ chối bàn giao toàn bộ tệp và không cấp liên kết tải có hiệu lực cho yêu cầu đó.

Ví dụ chọn chính sách từ chối toàn bộ tệp; hệ thống thực tế có thể chọn cấu trúc khác nếu được đặc tả và xác nhận phù hợp.

Phạm vi bao gồm:

- API tải kết quả.
- Đường tải được cấp trước khi quyền thay đổi.
- Bản xuất được tạo trước hoặc sau thời điểm thu hồi.
- Các điểm cung cấp dữ liệu thuộc hợp đồng của chức năng xuất.

Việc một URL còn hạn không được coi là lý do bỏ qua nghĩa vụ trong phạm vi này. Nếu kiến trúc hiện tại không đáp ứng được, cần thay thiết kế hoặc xử lý quyết định yêu cầu đúng thẩm quyền.

Đây là nghĩa vụ về kết quả bảo vệ, không bắt buộc một công nghệ cụ thể.

### 7.4. Bổ sung quan sát quyết định

**SR-EXP-AUDIT-03 v1.0:** Các sự kiện tạo tác vụ và quyết định bàn giao phải cho phép liên kết người yêu cầu, tenant, dự án hoặc manifest tài nguyên, mã tác vụ, thời điểm, kết quả và phiên bản chính sách được sử dụng.

Đồng thời, lược đồ phải loại các loại dữ liệu bị cấm như token, cookie phiên và nội dung hồ sơ khỏi trường audit thông thường.

Yêu cầu cần làm rõ người được đọc log, thời hạn lưu theo nguồn áp dụng và cách xử lý gián đoạn. Không suy từ một incident thành yêu cầu “ghi mọi request body vô thời hạn”.

### 7.5. Phân biệt thay đổi được xác nhận với đề xuất phòng ngừa

Nhóm nhận thấy phục hồi dữ liệu quyền cũ có thể làm tái xuất hiện vấn đề. Nếu incident chưa cung cấp bằng chứng về kịch bản đó, ghi đây là ứng viên cần phân tích:

**Ứng viên SR-RESTORE-04:** Trước khi mở lại chức năng bàn giao sau phục hồi, trạng thái quyền phải được đối chiếu với nguồn có thẩm quyền theo phạm vi đã xác định.

Cần tiếp tục làm rõ tính khả thi, phụ thuộc và ảnh hưởng RTO/RPO. Không trình bày nó như một nguyên nhân đã được xác nhận của incident.

## 8. Liên kết thay đổi với thiết kế và tiêu chí đánh giá

### 8.1. Ma trận truy vết

| Bằng chứng hoặc bài học | Khoảng trống | Quyết định yêu cầu | Bằng chứng cần tạo |
| --- | --- | --- | --- |
| F-01 | Kiểm tra lúc nhận vẫn cần thiết | Giữ SR-EXP-CREATE-01 | Ca đúng quyền và thiếu quyền lúc tạo |
| F-02, F-04 | Thu hồi không có giới hạn rõ ở luồng xuất | Làm rõ SR-REV-01 | Kiểm tra thời gian và quyền trước/sau |
| F-03 đến F-05 | Dùng ngữ cảnh cũ khi bàn giao | Thêm SR-EXP-DELIVERY-02 | Ca đổi quyền khi tác vụ chờ, chạy và đã có tệp |
| Khó nối sự kiện khi điều tra | Thiếu thông tin quan sát cần thiết | Thêm hoặc mở rõ SR-EXP-AUDIT-03 | Đối chiếu sự kiện, lược đồ và quyền log |
| Phân tích kiến trúc sau incident | Phục hồi có thể đưa quyền cũ trở lại | Tạo ứng viên SR-RESTORE-04 | Phân tích và diễn tập nếu yêu cầu được xác nhận |

Ma trận phải giữ được lý do, không chỉ liên kết số ticket với mã yêu cầu.

### 8.2. Tác động kiến trúc

Những vùng có thể cần thay đổi:

- Nguồn quyền và cơ chế phân phối trạng thái.
- Điểm quyết định trước bàn giao.
- Cache quyền và giới hạn độ cũ.
- Nội dung lưu trong thông điệp hàng đợi.
- Đường truy cập tệp và liên kết tải.
- Manifest tài nguyên để đánh giá quyền cho tệp tổng hợp.
- Audit và quan sát thời gian.
- Quy trình phục hồi và đồng bộ quyền.

Không thể chọn giải pháp chỉ từ tên lỗi. Ví dụ, rút ngắn hạn URL có thể giảm một phần phơi nhiễm nhưng chưa chắc đáp ứng giới hạn thu hồi và mọi đường tải của yêu cầu.

Thiết kế cần chứng minh cách đáp ứng yêu cầu trong các trường hợp được hỗ trợ, kể cả lỗi phụ thuộc và trạng thái không đủ để xác định quyền.

### 8.3. Tiêu chí kiểm chứng cho ví dụ

| Tình huống | Kết quả mong đợi |
| --- | --- |
| U có quyền suốt quá trình | Tạo và nhận bản xuất đúng phạm vi |
| U không có quyền lúc tạo | Không tạo tác vụ xuất trái quyền |
| Quyền bị thu hồi khi tác vụ đang chờ | Yêu cầu bàn giao sau giới hạn bị từ chối |
| Quyền bị thu hồi khi tác vụ đang chạy | Không dùng quyền đã chụp trước đó để bỏ qua nghĩa vụ bàn giao |
| Tệp đã tạo trước khi thu hồi | Đường tải vẫn áp dụng giới hạn quyền có hiệu lực |
| URL đã cấp trước thu hồi | Không trở thành đường bỏ qua SR-EXP-DELIVERY-02 |
| Tệp chứa tài nguyên không còn đủ quyền | Từ chối toàn bộ theo chính sách của ví dụ |
| U vẫn có quyền với dự án khác | Không bị khóa ngoài phạm vi thay đổi |
| Quyền được cấp lại hợp lệ | Áp dụng đúng trạng thái mới theo chính sách |
| Không xác định được quyền hoặc nguồn quyền lỗi | Không tự mặc định cho phép; hành vi cụ thể theo hợp đồng |
| Audit được tạo | Đủ liên kết quyết định, không có dữ liệu bị cấm |

Mỗi ca cần fixture, danh tính hợp lệ, tài nguyên tồn tại và điểm quan sát rõ. Một lỗi token hoặc lỗi route không được tính là bằng chứng đã từ chối đúng quyền.

## 9. Ưu tiên và quản lý biện pháp tạm

### 9.1. Không xếp hạng chỉ theo mức độ nổi bật của incident

Xem xét:

- Tác động với tài sản và nhóm người dùng.
- Đường gây hại còn mở hay đã được hạn chế.
- Phạm vi dùng chung của thành phần.
- Khả năng tái diễn và điều kiện khai thác.
- Độ tin cậy của phân tích.
- Nghĩa vụ đã được xác nhận là áp dụng.
- Thời gian và phụ thuộc để tạo bảo vệ bền vững.

Một lỗi nhỏ trong thành phần dùng chung có thể cần xử lý rộng. Một đề xuất lớn sau sự cố cũng có thể cần thu hẹp nếu không giải quyết đúng nguyên nhân.

### 9.2. Giữ biện pháp tạm với trách nhiệm rõ

Ví dụ, tổ chức đang giữ chức năng xuất của dự án P. Bản ghi cần nêu:

- Biện pháp đang có hiệu lực và phạm vi.
- Rủi ro còn lại.
- Người chịu trách nhiệm duy trì.
- Điều kiện và thẩm quyền mở lại.
- Hạn xem xét.
- Thay đổi lâu dài đang thay thế nó.

Không tự gỡ biện pháp chỉ vì requirement đã được phê duyệt hoặc code đã merge. Cần bằng chứng cơ chế đích đã có hiệu lực theo điều kiện mở lại.

[NIST SSDF 1.1, RV.2.2](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf) đề cập lập kế hoạch ứng phó rủi ro và biện pháp tạm khi chưa có xử lý lâu dài. Trong quản lý yêu cầu, cần giữ liên kết giữa quyết định tạm, nghĩa vụ hiện hành và việc hoàn tất thay đổi.

### 9.3. Chấp nhận rủi ro không phải kết quả kiểm thử đạt

Nếu quyết định triển khai với hạn chế hoặc ngoại lệ, giữ nguyên phát hiện và trạng thái bằng chứng. Ghi riêng người có thẩm quyền, phạm vi, điều kiện và thời hạn.

Một chữ ký không làm hệ thống đáp ứng một giới hạn mà nó chưa đạt. Nó ghi nhận quyết định về cách xử lý rủi ro theo cơ chế được phép.

## 10. Kiểm soát phiên bản và đưa vào baseline

Mỗi thay đổi nên có:

- Yêu cầu và phiên bản trước/sau.
- Lý do và tham chiếu incident.
- Nguồn bằng chứng.
- Nội dung thay đổi và phần giữ nguyên.
- Phạm vi hiệu lực.
- Tác động tới thiết kế, dữ liệu, nhà cung cấp và vận hành.
- Tiêu chí kiểm chứng.
- Người xác nhận và quyết định.
- Phiên bản triển khai dự kiến hoặc thực tế.

Không sửa nội dung cũ rồi làm mất khả năng biết khi incident xảy ra hệ thống từng phải đáp ứng điều gì.

### Bản ghi thay đổi minh họa

~~~text
Thay đổi: CR-REQ-EXPORT-07
Nguồn: Incident về bàn giao bản xuất sau thu hồi quyền

Quyết định:
- Giữ SR-EXP-CREATE-01 v1.0.
- Làm rõ SR-REV-01 ở v1.1.
- Thêm SR-EXP-DELIVERY-02 v1.0.
- Thêm hoặc mở rõ audit theo SR-EXP-AUDIT-03.
- Phân tích tiếp ứng viên SR-RESTORE-04.

Phạm vi:
Các đường tạo và bàn giao bản xuất thuộc sản phẩm,
gồm đường tải đã phát hành được chức năng này hỗ trợ.

Cơ sở:
Các dữ kiện F-01 đến F-05 và phân tích tác động liên quan.

Điều kiện triển khai:
Thiết kế đáp ứng quyền có hiệu lực, giới hạn thu hồi,
phạm vi URL và chính sách lỗi đã được xác nhận.

Hoàn tất:
Có bằng chứng đánh giá của bản triển khai tương ứng
và cập nhật tài liệu, vận hành, truy vết.

Người phụ trách:
Chủ yêu cầu, chủ hệ thống, nhóm triển khai và người đánh giá
theo phân công của tổ chức.
~~~

Mẫu phải được bổ sung định danh, phạm vi cụ thể, thời điểm và tham chiếu xác nhận trước khi dùng để điều phối công việc thực tế.

## 11. Triển khai, kiểm thử và xác nhận thay đổi

### 11.1. Chứng minh đúng lỗi đã được xử lý

Với ví dụ, cần tái hiện được điều kiện cốt lõi: quyền hợp lệ lúc tạo, bị thu hồi trước lúc bàn giao, sau đó người dùng thử nhận kết quả.

Ca kiểm chứng phải quan sát dữ liệu hoặc khả năng tải thực tế. Chỉ kiểm tra worker có gọi một hàm mới không chứng minh quyết định từ chối đã được thực thi.

Nếu phù hợp trong môi trường thử có kiểm soát, có thể xác nhận ca phát hiện hành vi sai trước bản sửa và đạt sau bản sửa. Kết quả phải thất bại hoặc đạt vì thuộc tính bảo mật đang xét, không phải vì fixture lỗi.

### 11.2. Mở rộng theo nguyên nhân

Bổ sung kiểm tra các đường có cùng cơ chế:

- Xuất đồng bộ và bất đồng bộ.
- Tệp đã có và tệp mới tạo.
- Các loại phiên hoặc token được hỗ trợ.
- Cache quyền và nhiều nút xử lý.
- Bản xuất có nhiều tài nguyên.
- Các phiên bản và môi trường đang phục vụ phạm vi liên quan.
- Đường tải trực tiếp hoặc tích hợp bên ngoài được chức năng hỗ trợ.

Không tự kết luận mọi sản phẩm dùng hàng đợi đều có cùng lỗi. Phân tích thành phần dùng chung để quyết định nơi cần đánh giá.

### 11.3. Giữ kiểm thử hồi quy

Một lỗi đã xử lý cần có ca hồi quy phù hợp để thay đổi sau không tái tạo cùng đường gây hại.

Ví dụ ca REG-EXPORT-REVOKE-01 liên kết tới SR-REV-01 và SR-EXP-DELIVERY-02, giữ rõ:

- Danh tính và quyền ban đầu.
- Tài nguyên và tenant.
- Mốc tạo tác vụ.
- Mốc thu hồi được xác nhận.
- Mốc yêu cầu bàn giao.
- Kết quả mong đợi.
- Các dữ liệu hoặc liên kết không được trả.

Không dùng lại bí mật hoặc dữ liệu khách hàng từ incident làm fixture nếu không cần thiết. Có thể dùng dữ liệu mẫu mang cùng quan hệ và trạng thái.

### 11.4. Đánh giá yêu cầu thời gian và audit

Đối với giới hạn 60 giây, phải đo từ mốc đúng và biết yêu cầu bàn giao bắt đầu lúc nào. Kiểm tra token hoặc phiên cũ để tránh bỏ sót trạng thái đã được cấp trước thu hồi.

Đối với audit, đối chiếu các quyết định tạo, thu hồi và bàn giao bằng mã liên kết phù hợp. Kiểm tra nhánh thành công, bị từ chối và lỗi; không chỉ kiểm tra một dòng log mẫu.

Không thêm khoảng ngủ dài tùy ý rồi coi đó là bằng chứng đã đáp ứng ngưỡng tối đa. Tầng thành phần có thể dùng đồng hồ điều khiển được; tầng tích hợp vẫn phải đánh giá các cơ chế thực tế có ảnh hưởng.

### 11.5. Xác minh bản triển khai và cấu hình

Bằng chứng cần gắn với bản phần mềm, policy, cấu hình và môi trường cụ thể. Nếu thay đổi chưa được bật ở một tenant hoặc phiên bản, không báo toàn bộ phạm vi đã được xử lý.

Một rollout có thể diễn ra theo từng phần, nhưng phần chưa đạt cần tiếp tục có quyết định và biện pháp tương ứng. Rollback cũng phải xét nguy cơ khôi phục cơ chế đã được xác nhận gây lỗi.

## 12. Trách nhiệm và phối hợp

| Vai trò | Trách nhiệm trong cập nhật requirement |
| --- | --- |
| Người điều phối incident | Giữ liên kết với bằng chứng, phạm vi và quyết định ứng phó |
| Chủ nghiệp vụ | Xác nhận hành vi được phép và tác động của giới hạn mới |
| Chủ dữ liệu | Xác nhận phạm vi dữ liệu và hậu quả cần ngăn |
| Chủ yêu cầu | Quản lý phát biểu, phiên bản và nguồn thay đổi |
| Nhóm bảo mật | Phân tích rủi ro, giả định và khoảng trống bảo vệ |
| Kiến trúc và phát triển | Đánh giá tính khả thi, phụ thuộc và cách thực hiện |
| QA hoặc người đánh giá | Xây dựng tiêu chí, ca thử và bằng chứng |
| Vận hành | Cập nhật runbook, cảnh báo, cấu hình và kiểm chứng triển khai |
| Người phụ trách nghĩa vụ áp dụng | Làm rõ yêu cầu chính sách, hợp đồng hoặc nghĩa vụ liên quan |
| Nhà cung cấp | Cung cấp khả năng kỹ thuật và bằng chứng trong phần trách nhiệm |
| Người có thẩm quyền quyết định | Xác nhận thay đổi, phạm vi và quyết định rủi ro phù hợp |

Một người có thể giữ nhiều vai trò. Dù vậy, phải biết ai quyết định nội dung, ai triển khai và ai xác minh, thay vì gán toàn bộ cho một nhóm “security” chung chung.

### 12.1. Truyền đạt đúng mức thông tin

Nhóm triển khai cần biết yêu cầu và điều kiện kiểm chứng. Nhóm vận hành cần biết trạng thái mới, cảnh báo và điều kiện mở lại. Người quyết định cần biết rủi ro, bằng chứng và giới hạn.

Thông tin mô tả chi tiết đường khai thác, dữ liệu hoặc bí mật phải được giới hạn theo nhu cầu. Tài liệu yêu cầu có thể dẫn đến hiện vật điều tra được bảo vệ thay vì sao chép mọi chi tiết.

### 12.2. Không nhầm cải tiến với nghĩa vụ thông báo

Một incident có thể có nghĩa vụ thông báo, lưu giữ hoặc phối hợp riêng. Việc cập nhật requirement không thay thế các hoạt động đó.

Nếu cần thay đổi yêu cầu liên quan thông báo hoặc xử lý dữ liệu, người phụ trách phải xác nhận nguồn, phạm vi và điều kiện áp dụng. Không tự lấy một thời hạn quen thuộc rồi coi nó bắt buộc cho mọi sản phẩm.

### 12.3. Đồng bộ kế hoạch vận hành

[NIST SP 800-61 Rev. 3, ID.IM-04](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf) đề cập duy trì và cải tiến các kế hoạch liên quan, cùng sự phối hợp với hoạt động liên tục nghiệp vụ.

Khi yêu cầu mới làm thay đổi quyền, giới hạn thu hồi hoặc đường bàn giao, cần xem lại:

- Hướng dẫn xử lý sự cố và containment.
- Tài liệu hỗ trợ người dùng.
- Quy trình thay đổi quyền.
- Điều kiện phục hồi.
- Cam kết hoặc phụ thuộc nhà cung cấp.
- Công cụ quan sát và cách diễn tập.

Không để requirement mới đúng trên tài liệu nhưng đội trực vẫn làm theo runbook cũ.

## 13. Tiêu chí đóng một việc cải tiến

Một việc cập nhật yêu cầu không nên đóng chỉ bằng “đã họp”, “đã viết tài liệu” hoặc “đã merge”.

Tùy phạm vi, điều kiện đóng có thể gồm:

1. Kết luận và nguồn bằng chứng đủ để giải thích thay đổi.
2. Yêu cầu có phát biểu, phạm vi và phiên bản đã xác nhận.
3. Thiết kế và trách nhiệm được cập nhật.
4. Cơ chế được triển khai trong phạm vi đã cam kết.
5. Các ca kiểm chứng và hồi quy liên quan đạt.
6. Các ca bị chặn hoặc chưa chạy được xử lý minh bạch.
7. Cấu hình vận hành và khả năng quan sát được xác minh.
8. Runbook, đào tạo hoặc phối hợp nhà cung cấp được cập nhật khi cần.
9. Rủi ro còn lại và quyết định ngoại lệ được ghi riêng.
10. Người có trách nhiệm chấp nhận kết quả theo tiêu chí đã định.

Có thể đóng từng phần công việc, như hoàn tất đặc tả, trước khi hoàn tất rollout. Nhưng tên trạng thái và báo cáo phải phản ánh đúng phần đã làm.

### Kiểm tra hiệu quả sau triển khai

Một thời gian quan sát phù hợp có thể giúp xác định:

- Có yêu cầu bàn giao bị từ chối sau thu hồi như thiết kế không?
- Người còn quyền có bị chặn ngoài ý định không?
- Các điểm thực thi có độ trễ vượt giới hạn không?
- Audit có đủ để điều tra và có chứa dữ liệu bị cấm không?
- Có đường tải hoặc phiên bản nào chưa đi qua cơ chế mới không?

Không có incident tương tự trong một thời gian chưa tự chứng minh thay đổi đã hiệu quả. Có thể hệ thống chưa gặp lại điều kiện đó hoặc khả năng phát hiện còn hạn chế. Cần đọc quan sát cùng bằng chứng kiểm thử.

## 14. Theo dõi danh mục cải tiến sau nhiều incident

### 14.1. Tìm mẫu lặp

Khi có nhiều sự cố, có thể thấy các mẫu:

- Yêu cầu chỉ bao phủ request trực tiếp, bỏ tác vụ nền.
- Thời điểm quyền có hiệu lực không được đặc tả.
- Các sản phẩm cùng bỏ qua đường tải đã cấp.
- Audit thiếu quan hệ giữa quyết định và dữ liệu.
- Quy trình phục hồi dùng cấu hình hoặc dữ liệu quyền lỗi thời.
- Kiểm thử chỉ có luồng thành công.

Nếu cùng một mẫu xuất hiện ở nhiều nơi, có thể cần sửa hướng dẫn đặc tả, thành phần dùng chung hoặc tiêu chí thiết kế. Không chỉ tạo nhiều ticket có cùng nguyên nhân mà không thay đổi cách phòng ngừa.

[NIST SSDF 1.1, RV.3.2 đến RV.3.4](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf) liên hệ phân tích mẫu nguyên nhân với phát hiện điểm yếu tương tự và cập nhật SDLC.

### 14.2. Số liệu có ý nghĩa

Có thể theo dõi:

- Các việc cải tiến có nguồn, người phụ trách và tiêu chí đóng.
- Các mục quá hạn hoặc rủi ro chưa được xử lý.
- Thời gian từ xác định khoảng trống đến triển khai có bằng chứng.
- Tỷ lệ phạm vi triển khai đã được xác minh.
- Các lỗi đã xử lý nhưng tái xuất hiện.
- Những ứng viên yêu cầu còn thiếu thông tin quyết định.
- Tác động ngoài ý định sau khi mở cơ chế mới.

Số requirement được thêm không phải thước đo trực tiếp của mức an toàn. Tốc độ đóng ticket cũng không có ý nghĩa nếu không có bằng chứng đáp ứng.

### 14.3. Không tự động áp một bài học cho mọi hệ thống

Một mẫu yêu cầu có thể được đưa vào thư viện dùng chung, nhưng từng dự án vẫn phải xác định phạm vi, dữ liệu, chủ thể và ngưỡng phù hợp.

Ví dụ, chính sách từ chối toàn bộ bản xuất khi mất quyền một tài nguyên có thể phù hợp với sản phẩm này; sản phẩm khác có thể tái tạo bản xuất từ tập tài nguyên còn được phép. Cả hai cần đặc tả rõ và được xác nhận theo rủi ro, không sao chép máy móc.

## 15. Các lỗi thường gặp

| Sai sót | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Mọi incident đều dẫn đến thêm requirement | Đặc tả phình to, không giải quyết đúng nguyên nhân | Phân loại thiếu yêu cầu, lỗi triển khai và lỗi đánh giá |
| Viết “tăng cường bảo mật” | Không biết triển khai hoặc kiểm chứng gì | Nêu chủ thể, phạm vi, điều kiện và kết quả |
| Dùng giả thuyết như dữ kiện | Đầu tư sai hoặc bỏ sót nguyên nhân thật | Ghi độ chắc chắn và người xác minh |
| Chỉ sửa đường tái hiện đầu tiên | Cùng lỗi còn ở luồng hoặc sản phẩm khác | Phân tích nguyên nhân và phụ thuộc dùng chung |
| Chọn công nghệ trước khi xác định nghĩa vụ | Giải pháp có thể không chặn đường gây hại | Xác định kết quả bảo vệ trước |
| Chốt thời hạn không có căn cứ | Yêu cầu thiếu khả thi hoặc chấp nhận phơi nhiễm ngoài ý muốn | Xác nhận ngưỡng cùng tác động và cách đo |
| Yêu cầu ghi mọi dữ liệu để điều tra | Tạo thêm rủi ro dữ liệu và chi phí | Đặc tả sự kiện, trường, quyền và thời hạn phù hợp |
| Sửa lại baseline cũ | Mất khả năng giải thích sự cố theo thời điểm | Giữ lịch sử và hiệu lực phiên bản |
| Đóng việc khi merge | Chưa chứng minh cấu hình thật đã đáp ứng | Gắn tiêu chí đóng với triển khai và bằng chứng |
| Xóa ca thất bại hoặc đổi kỳ vọng cho xanh | Che khoảng trống còn tồn tại | Đối chiếu yêu cầu và quyết định đúng thẩm quyền |
| Gỡ containment vì đã có tài liệu mới | Đường gây hại có thể còn mở | Gỡ theo điều kiện kỹ thuật và quyết định phục hồi |
| Áp chính sách mới cho mọi sản phẩm không phân tích | Tạo gián đoạn hoặc sai phạm vi | Đánh giá khả năng dùng lại theo ngữ cảnh |

## 16. Tiêu chí sẵn sàng của thay đổi requirement sau incident

Đây là kiểm tra tính đầy đủ của vòng phản hồi, không phải kết luận hệ thống đã loại bỏ mọi rủi ro.

- [ ] Có mã incident và nguồn bằng chứng được bảo vệ.
- [ ] Phân biệt quan sát, suy luận, giả thuyết và điều chưa biết.
- [ ] Xác định đúng yêu cầu và cấu hình từng có hiệu lực.
- [ ] Có phân tích nguyên nhân và các yếu tố đóng góp.
- [ ] Phân loại đúng yêu cầu mới, yêu cầu cần sửa và lỗi triển khai.
- [ ] Giữ liên kết với tài sản, rủi ro và mục tiêu bảo vệ.
- [ ] Phạm vi gồm các đường xử lý và thời điểm quan trọng.
- [ ] Các ngưỡng có căn cứ, người xác nhận và cách đo.
- [ ] Xác thực, phân quyền, dữ liệu, logging và phục hồi được xem xét theo tác động.
- [ ] Không chọn giải pháp chỉ vì quen thuộc hoặc nổi bật.
- [ ] Có phân tích tác động đến kiến trúc, dữ liệu và nhà cung cấp.
- [ ] Có phiên bản, lịch sử và phạm vi baseline mới.
- [ ] Công việc có người phụ trách, thứ tự ưu tiên và điều kiện đóng.
- [ ] Biện pháp tạm và rủi ro còn lại được quản lý riêng.
- [ ] Kiểm chứng có ca dương, ca âm và tình huống tái hiện liên quan.
- [ ] Có kiểm thử hồi quy phù hợp cho lỗi đã được xử lý.
- [ ] Bằng chứng gắn với đúng bản triển khai và cấu hình.
- [ ] Runbook và trách nhiệm vận hành được đồng bộ.
- [ ] Phần bị chặn, chưa chạy hoặc chưa xác nhận không bị coi là đã hoàn tất.
- [ ] Có cách theo dõi hiệu quả và mở lại việc khi giả định thay đổi.

## 17. Tài liệu tham khảo

- [NIST SP 800-61 Rev. 3 — trang công bố chính thức](https://csrc.nist.gov/pubs/sp/800/61/r3/final): ứng phó sự cố gắn với quản lý rủi ro theo CSF 2.0.
- [NIST SP 800-61 Rev. 3 — toàn văn](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r3.pdf): ID.IM-03 về cải tiến từ vận hành, ứng phó và phục hồi; ID.IM-04 về duy trì các kế hoạch; RC.RP-06 về báo cáo sau hoạt động phục hồi.
- [NIST SP 800-218 — SSDF Version 1.1](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf): RV.2.2 về ứng phó rủi ro và RV.3 về nguyên nhân, điểm yếu tương tự và cải tiến SDLC.
