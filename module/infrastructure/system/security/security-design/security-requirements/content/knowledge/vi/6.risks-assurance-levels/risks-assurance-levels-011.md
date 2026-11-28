# Chấp nhận hoặc chuyển giao rủi ro

## 1. Vị trí của quyết định trong thiết kế yêu cầu bảo mật

Sau khi xác định tài sản, mô hình đe dọa, khả năng xảy ra và mức tác động, tổ chức phải quyết định cách xử lý rủi ro. Không phải mọi rủi ro đều có thể được loại bỏ hoàn toàn, nhưng mọi quyết định quan trọng cần có phạm vi, người có thẩm quyền và căn cứ.

Hai phương án thường được sử dụng là:

- **Chấp nhận rủi ro — risk acceptance:** quyết định có hiểu biết rằng tổ chức sẽ tiếp tục hoạt động với phần rủi ro còn lại trong điều kiện đã xác định.
- **Chuyển giao rủi ro — risk transfer:** phân bổ cho bên khác một phần hậu quả hoặc trách nhiệm xử lý thông qua cơ chế được thỏa thuận, trong khi vẫn xác định rõ phần rủi ro tổ chức giữ lại.

Trong thiết kế yêu cầu bảo mật, quyết định này phải dẫn đến các yêu cầu có thể thực hiện và kiểm chứng. Một chữ ký chấp thuận hoặc một hợp đồng với nhà cung cấp chưa chứng minh rằng dữ liệu được bảo vệ đúng, quyền được thu hồi hay hệ thống có thể phục hồi.

Chuỗi cần có là:

**Kịch bản rủi ro → lựa chọn xử lý → điều kiện và trách nhiệm → yêu cầu bảo mật → bằng chứng → quyết định về rủi ro còn lại.**

Bài học giúp bạn phân biệt hai phương án, biết khi nào cần xem xét chúng, ghi nhận quyết định và liên kết với yêu cầu về xác thực, phân quyền, dữ liệu, logging và phục hồi. Các tình huống, thời hạn và mục tiêu trong bài là giả định để minh họa phương pháp.

## 2. Phân biệt các phương án xử lý rủi ro

| Phương án | Ý nghĩa | Ví dụ |
|---|---|---|
| Tránh | Dừng hoặc thay đổi hoạt động tạo ra kịch bản | Không triển khai một chức năng xuất dữ liệu chưa có nhu cầu nghiệp vụ rõ ràng |
| Giảm | Thay đổi thiết kế hoặc vận hành để giảm khả năng xảy ra hoặc hậu quả | Kiểm tra quyền theo đối tượng, giảm dữ liệu thu thập, kiểm thử phục hồi |
| Chấp nhận | Tiếp tục với rủi ro đã được mô tả, đánh giá và quyết định đúng thẩm quyền | Chấp nhận tạm thời phần rủi ro còn lại khi dùng quy trình kiểm tra thủ công có giới hạn |
| Chuyển giao hoặc chia sẻ một phần | Phân bổ nghĩa vụ xử lý hoặc một phần hậu quả cho bên khác | Thuê dịch vụ vận hành sao lưu với cam kết, trách nhiệm và bằng chứng cụ thể |

Các phương án có thể kết hợp. Một hệ thống có thể giảm rủi ro bằng phân quyền, chuyển một phần công việc phục hồi cho nhà cung cấp và chấp nhận phần rủi ro tồn dư sau khi kiểm chứng.

### 2.1. Phân biệt rủi ro hiện tại, mục tiêu và tồn dư

- **Rủi ro hiện tại:** được đánh giá với kiểm soát đang hoạt động và bằng chứng hiện có.
- **Rủi ro mục tiêu:** dự kiến sau khi hoàn thành biện pháp đã đề xuất.
- **Rủi ro tồn dư đã xác minh:** được đánh giá sau triển khai và kiểm chứng, kèm giả định và giới hạn.

Không dùng mức mục tiêu làm căn cứ nói rằng rủi ro hiện tại đã được chấp nhận ở mức thấp hơn. Nếu nhà cung cấp chưa được tích hợp hoặc chưa thử phục hồi, hiệu quả dự kiến vẫn là giả định.

### 2.2. Quyết định xử lý khác với kết quả đáp ứng yêu cầu

Giả sử yêu cầu quy định thu hồi quyền trong 15 phút nhưng hệ thống thực tế cần 4 giờ. Một cấp có thẩm quyền có thể phải xem xét ngoại lệ theo chính sách, nhưng quyết định đó không đổi kết quả kỹ thuật thành “đáp ứng 15 phút”.

Cần ghi riêng:

1. Yêu cầu hiện hành và sai lệch.
2. Rủi ro do sai lệch.
3. Quyết định xử lý hoặc ngoại lệ.
4. Điều kiện, thời hạn và kế hoạch khắc phục.

Quyết định nội bộ không tự loại bỏ nghĩa vụ bắt buộc mà tổ chức phải tuân thủ.

## 3. Chấp nhận rủi ro có điều kiện

### 3.1. Chấp nhận là một quyết định chủ động

Chấp nhận rủi ro cần dựa trên việc hiểu kịch bản, hậu quả, kiểm soát và các phần chưa biết. Những tình huống sau chưa đủ để coi là đã chấp nhận:

- Không ai xử lý đầu việc.
- Hạn khắc phục đã qua nhưng không có quyết định.
- Nhóm triển khai nói rằng sửa lỗi quá tốn thời gian.
- Không ghi nhận sự cố nên mặc định rủi ro thấp.
- Có người đồng ý trong trao đổi nhưng không rõ phạm vi và thẩm quyền.

Quyết định cần đến trước khi hoạt động trong điều kiện được chấp nhận có hiệu lực. Một phê duyệt sau sự kiện không tự sửa được khoảng thời gian trước đó không có quyết định phù hợp.

### 3.2. Những căn cứ cần có

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Kịch bản | Điều gì có thể xảy ra, trên tài sản và đường đi nào? |
| Hậu quả | Ai bị ảnh hưởng, ở mức nào, có thể khắc phục được không? |
| Khả năng xảy ra | Đánh giá trong khoảng thời gian nào, dựa vào bằng chứng gì? |
| Kiểm soát hiện có | Biện pháp nào đang thực sự hoạt động? |
| Bất định | Điều gì chưa biết và ảnh hưởng đến quyết định ra sao? |
| Phương án khác | Có thể tránh, giảm hoặc chuyển một phần không? |
| Lợi ích và chi phí | Vì sao tiếp tục trong phạm vi này là lựa chọn được đề xuất? |
| Thẩm quyền | Ai được quyền quyết định đối với hậu quả và mức rủi ro này? |
| Điều kiện | Phải duy trì giới hạn, giám sát và biện pháp nào? |
| Hiệu lực | Bắt đầu, hết hạn hoặc rà soát khi nào, sự kiện nào làm mất hiệu lực? |

Không phải mọi bất định đều phải được loại bỏ trước quyết định. Tuy nhiên, bất định quan trọng cần được trình bày và giới hạn phù hợp, thay vì che bằng một điểm số chính xác giả tạo.

### 3.3. Khi nào có thể xem xét?

Có thể xem xét chấp nhận khi:

- Rủi ro nằm trong phạm vi thẩm quyền và tiêu chí chấp nhận đã định nghĩa.
- Yêu cầu bắt buộc và kiểm soát nền liên quan đã được đáp ứng hoặc xử lý theo cơ chế hợp lệ.
- Các phương án khác đã được cân nhắc.
- Phần hậu quả còn lại được người quyết định hiểu rõ.
- Có nguồn lực duy trì điều kiện, theo dõi và phản ứng.
- Có thời hạn hoặc cơ chế rà soát phù hợp với loại quyết định.

Một quyết định tạm thời nên có ngày hết hiệu lực và đầu việc kết thúc. Với quyết định dài hạn, vẫn cần chu kỳ rà soát và sự kiện kích hoạt đánh giá lại.

### 3.4. Khi nào cần dừng để đánh giá lại?

Những dấu hiệu cần xem xét lại gồm:

- Không rõ dữ liệu, người dùng hoặc phạm vi ảnh hưởng.
- Hậu quả vượt thẩm quyền người được đề nghị phê duyệt.
- Kiểm soát bù đắp chưa được triển khai hoặc không có người thực hiện.
- Có điểm yếu đang bị khai thác nhưng đánh giá vẫn dựa trên giả định cũ.
- Không có khả năng phát hiện điều kiện chấp nhận bị vi phạm.
- Quyết định không có giới hạn và liên tục được gia hạn mà không thay đổi kế hoạch.
- Một bên gọi sai lệch là “đã chấp nhận” để đánh dấu yêu cầu đã đạt.

Việc thiếu căn cứ không tự làm rủi ro thấp đi. Có thể cần thu hẹp chức năng hoặc tạm dừng đường tạo rủi ro trong khi bổ sung bằng chứng.

### 3.5. Nội dung một hồ sơ chấp nhận

Một hồ sơ hữu ích cần ghi:

- Mã rủi ro và mô tả kịch bản.
- Tài sản, phiên bản, môi trường và phạm vi người dùng.
- Likelihood, impact, độ tin cậy và căn cứ.
- Yêu cầu hoặc sai lệch liên quan.
- Biện pháp hiện có và bằng chứng.
- Phương án đã cân nhắc, lý do đề xuất chấp nhận.
- Điều kiện, giới hạn và chỉ báo phải theo dõi.
- Chủ sở hữu rủi ro, người thực hiện và người có thẩm quyền phê duyệt.
- Thời điểm hiệu lực, hết hạn hoặc lịch rà soát.
- Kế hoạch xử lý khi hết hạn hoặc điều kiện không còn đúng.

Không ghi mật khẩu, token, khóa bí mật hoặc dữ liệu khách hàng đầy đủ vào hồ sơ quyết định. Hồ sơ cũng cần được kiểm soát truy cập vì có thể mô tả điểm yếu của hệ thống.

## 4. Chuyển giao rủi ro: xác định chính xác phần được chuyển

### 4.1. Chuyển giao không có nghĩa toàn bộ rủi ro biến mất

Một thỏa thuận có thể phân bổ nghĩa vụ vận hành, trách nhiệm khắc phục hoặc một phần tổn thất kinh tế. Những hậu quả khác như gián đoạn nghiệp vụ, mất lòng tin hoặc dữ liệu đã bị tiết lộ có thể vẫn do tổ chức chịu.

Cần phân biệt ba việc:

| Việc | Ý nghĩa |
|---|---|
| Giao công việc | Bên khác thực hiện sao lưu, giám sát hoặc xử lý yêu cầu |
| Thỏa thuận trách nhiệm | Các bên thống nhất nghĩa vụ, giới hạn và cơ chế xử lý khi không đáp ứng |
| Chuyển một phần hậu quả | Một phần chi phí hoặc hậu quả được phân bổ theo cơ chế thực tế có hiệu lực |

Thuê ngoài một công việc không tự chứng minh đã chuyển được rủi ro. Phải xác định điều kiện, phạm vi, giới hạn và khả năng bên nhận thực hiện cam kết.

### 4.2. Các cơ chế thường được xem xét

- **Dịch vụ quản lý:** nhà cung cấp vận hành một phần hạ tầng hoặc quy trình với yêu cầu cụ thể.
- **Thỏa thuận trách nhiệm trong hợp đồng:** quy định nghĩa vụ bảo vệ, khắc phục và xử lý hậu quả theo bối cảnh.
- **Bảo hiểm phù hợp:** có thể phân bổ một phần tổn thất kinh tế thuộc phạm vi được bảo vệ, với điều kiện và giới hạn cụ thể.
- **Thỏa thuận giữa các bên cùng cung cấp dịch vụ:** chia trách nhiệm theo từng ranh giới và đầu ra.

Không suy ra mức bảo vệ từ tên gói dịch vụ hoặc tên loại bảo hiểm. Các điều kiện thực tế, phần loại trừ, giới hạn, thủ tục và khả năng đáp ứng cần được những người có chuyên môn phù hợp xem xét trong quy trình của tổ chức.

### 4.3. Những rủi ro vẫn có thể giữ lại hoặc phát sinh thêm

| Phần rủi ro | Ví dụ |
|---|---|
| Trách nhiệm cấu hình của khách hàng | Kho dữ liệu bị mở do quyền do chính tổ chức đặt sai |
| Hậu quả không thể thu hồi | Dữ liệu đã bị sao chép ra ngoài |
| Phụ thuộc nhà cung cấp | Sự cố chung, thiếu năng lực hoặc không thể hỗ trợ đúng lúc |
| Tập trung | Hệ thống chính và mọi bản sao cùng phụ thuộc một miền sự cố |
| Khóa chặt dịch vụ | Khó xuất dữ liệu, thay nhà cung cấp hoặc phục hồi sang đích khác |
| Phát hiện và phối hợp | Hai bên không có cùng mốc thời gian, log hoặc đầu mối |
| Phạm vi không được bảo vệ | Loại sự cố hoặc phần thiệt hại nằm ngoài điều kiện đã thỏa thuận |

Một khoản giảm phí dịch vụ không tự tương đương chi phí sự cố thực tế. Một cam kết thời gian cũng cần được kiểm chứng trong luồng nghiệp vụ đầy đủ.

### 4.4. Trách nhiệm nội bộ vẫn phải rõ

Tổ chức vẫn cần chủ sở hữu tài sản và chủ sở hữu rủi ro nội bộ để xác nhận mục đích, nhu cầu bảo vệ, điều kiện sử dụng và mức rủi ro còn lại.

Nhà cung cấp có thể là bên thực hiện kiểm soát, nhưng không tự trở thành người có thẩm quyền chấp nhận mọi hậu quả thay cho tổ chức. Bảng trách nhiệm cần chỉ ra phần nhà cung cấp thực hiện, phần tổ chức thực hiện và phần cần phối hợp.

## 5. Chọn phương án và chuẩn bị quyết định

### 5.1. So sánh theo kịch bản

| Câu hỏi | Khi xem xét chấp nhận | Khi xem xét chuyển giao |
|---|---|---|
| Mục đích | Vì sao tiếp tục với rủi ro còn lại? | Phần nghĩa vụ hoặc hậu quả nào cần bên khác nhận? |
| Căn cứ chính | Rủi ro trong giới hạn thẩm quyền, điều kiện và bằng chứng đủ rõ | Khả năng thực hiện, phạm vi thỏa thuận và bằng chứng của bên nhận |
| Kiểm soát vẫn cần | Điều kiện bảo vệ, giám sát và phản ứng | Kiểm soát tại ranh giới và phần trách nhiệm tổ chức giữ lại |
| Điều cần theo dõi | Điều kiện chấp nhận, thời hạn và thay đổi rủi ro | Hiệu quả dịch vụ, thay đổi điều khoản, phụ thuộc và khả năng thoát |
| Khi kết thúc | Đóng, xử lý tiếp hoặc phê duyệt lại | Bàn giao, xuất dữ liệu, thu hồi quyền và xử lý bản sao |

Có thể chọn phương án kết hợp. Ví dụ, nhà cung cấp quản lý sao lưu, tổ chức kiểm thử phục hồi đầu cuối và cấp có thẩm quyền xem xét rủi ro tập trung còn lại.

### 5.2. Trình tự thực hiện

1. Mô tả kịch bản, tài sản, khoảng đánh giá và hậu quả.
2. Đánh giá likelihood, impact và bất định với kiểm soát hiện tại.
3. Xác định những yêu cầu không được tùy ý bỏ qua.
4. So sánh tránh, giảm, chấp nhận và chuyển một phần.
5. Đặc tả điều kiện, trách nhiệm, thời gian và bằng chứng.
6. Thực hiện phần chuẩn bị, kiểm chứng cần thiết.
7. Đưa hồ sơ đến người có thẩm quyền quyết định.
8. Theo dõi hiệu lực và đánh giá lại khi điều kiện thay đổi.

Việc phê duyệt một đề xuất chuyển giao có thể phụ thuộc hoàn tất kiểm chứng nhà cung cấp, hợp đồng hoặc khả năng phục hồi. Phải phân biệt đề xuất, cam kết đã hình thành, kiểm soát đã hoạt động và mức rủi ro tồn dư đã được xác minh.

## 6. Tình huống A: chấp nhận tạm thời một phần rủi ro

### 6.1. Bối cảnh

Một hệ thống xử lý đơn hàng tạo tệp chẩn đoán để hỗ trợ vận hành. Phạm vi **DIAG-011** chỉ cho phép các trường kỹ thuật đã duyệt, không chứa thông tin khách hàng, token, mật khẩu hoặc khóa bí mật.

Tệp được lưu tối đa 24 giờ trong kho riêng và chỉ nhóm hỗ trợ được phê duyệt truy cập. Kiểm soát truy cập, cấu trúc dữ liệu đầu ra và thời hạn đã được xác minh trong tình huống giả định.

Nhóm dự định bổ sung kiểm tra tổng hợp tự động về quyền kho. Trong 14 ngày chuyển tiếp, họ đề xuất kiểm tra thủ công mỗi 24 giờ.

Kịch bản **R-ACC-011**:

> Một thay đổi quyền sai tại kho chẩn đoán không được phát hiện kịp do bỏ sót kiểm tra thủ công, làm thông tin chẩn đoán nội bộ bị truy cập ngoài nhóm được phép.

Rủi ro được đề xuất chấp nhận là phần còn lại liên quan đến quy trình thủ công trong phạm vi này. Không bao gồm việc đưa dữ liệu khách hàng hoặc bí mật vào tệp, mở truy cập công khai hay bỏ kiểm soát xác thực.

### 6.2. Điều kiện đề xuất

- Chỉ áp dụng cho DIAG-011 trong môi trường và phiên bản được ghi nhận.
- Dữ liệu đầu ra tuân theo danh sách trường cho phép đã kiểm chứng.
- Quyền đọc giới hạn ở nhóm hỗ trợ, có danh tính và dấu vết.
- Tệp tự hết vòng đời trong tối đa 24 giờ.
- Có người trực và người thay thế thực hiện kiểm tra mỗi 24 giờ.
- Quá hạn kiểm tra phải ngừng tạo tệp mới cho đến khi điều kiện được khôi phục.
- Phát hiện dữ liệu ngoài phạm vi hoặc quyền không phù hợp phải kích hoạt xử lý sự cố và đánh giá lại quyết định.
- Sau 14 ngày, cơ chế tạm thời hết hiệu lực; cần kiểm chứng phương án thay thế hoặc ngừng phần chức năng tạo tệp.

Các con số là lựa chọn minh họa. Tính phù hợp phải được xác nhận từ tác động thực tế, khả năng vận hành và thẩm quyền quyết định.

### 6.3. Mẫu hồ sơ đề xuất

```text
Mã rủi ro: R-ACC-011
Trạng thái: Chờ quyết định theo thẩm quyền
Phạm vi: Kho chẩn đoán DIAG-011 của bản phát hành đã nêu
Kịch bản: Bỏ sót kiểm tra quyền thủ công dẫn đến truy cập ngoài nhóm
Phương án: Chấp nhận có điều kiện trong 14 ngày
Kiểm soát bắt buộc:
    Danh sách trường đầu ra; xác thực và phân quyền;
    thời hạn tệp 24 giờ; kiểm tra quyền mỗi 24 giờ;
    log thay đổi quyền; cơ chế dừng tạo tệp khi quá hạn.
Bằng chứng:
    Kết quả kiểm chứng đầu ra và quyền;
    cấu hình thời hạn; phân công trực;
    thử nghiệm quá hạn và dừng chức năng.
Chủ sở hữu rủi ro: Vai trò có thẩm quyền với nghiệp vụ liên quan
Kết thúc:
    Kiểm chứng cơ chế kiểm tra tự động hoặc ngừng tạo tệp;
    không tự gia hạn quyết định.
```

Hồ sơ còn cần đánh giá likelihood, impact, bất định và người phê duyệt thực tế. Một mẫu điền sẵn chưa thay thế được các căn cứ đó.

## 7. Tình huống B: chuyển một phần trách nhiệm phục hồi

### 7.1. Bối cảnh và mục tiêu

Cùng hệ thống sử dụng nhà cung cấp quản lý sao lưu. Kịch bản **R-TRF-011**:

> Khi hạ tầng chính gặp sự cố, tổ chức không thể khôi phục dữ liệu đơn hàng và nghiệp vụ trong giới hạn đã chấp nhận.

Tổ chức đề xuất:

- Giao nhà cung cấp thực hiện công việc sao lưu, theo dõi và hỗ trợ phục hồi trong phạm vi thỏa thuận.
- Thỏa thuận cách xử lý khi dịch vụ không đáp ứng, với điều kiện và giới hạn được xác định.
- Giữ trách nhiệm nội bộ về mục tiêu nghiệp vụ, quyền truy cập, cấu hình ứng dụng, khóa theo phân công, kiểm chứng đầu cuối và quyết định tồn dư.

Giao công việc có thể giúp giảm rủi ro nếu bên nhận thực hiện tốt. Phần hậu quả kinh tế được phân bổ phải được xác định riêng từ thỏa thuận thực tế; không suy ra từ việc đã thuê dịch vụ.

### 7.2. Mục tiêu phục hồi cần đo được

Tình huống chọn:

- **RPO không quá 15 phút:** mức lùi dữ liệu tối đa được chấp nhận.
- **RTO không quá 4 giờ:** thời gian từ khi sự cố làm nghiệp vụ không đáp ứng đến lúc nghiệp vụ đã chọn hoạt động và qua kiểm tra chấp nhận.

Một ngân sách thời gian minh họa nếu các bước diễn ra tuần tự:

| Chặng | Giới hạn |
|---|---|
| Phát hiện, xác định và gửi yêu cầu hợp lệ | 15 phút |
| Nhà cung cấp thực hiện phần phục hồi đã thỏa thuận từ lúc nhận yêu cầu hợp lệ | 3 giờ |
| Tổ chức cấu hình phần còn lại, kiểm tra dữ liệu và mở nghiệp vụ | 45 phút |
| Tổng | 4 giờ |

Ngân sách này cần được thử bằng thực tế. Nếu thiếu thời gian điều phối, giải mã, dựng phụ thuộc hoặc kiểm tra, mục tiêu có thể không đạt dù nhà cung cấp hoàn thành phần việc riêng.

Cam kết “khôi phục trong 3 giờ” của nhà cung cấp không tự chứng minh RTO 4 giờ của dịch vụ. Cần cố định mốc bắt đầu, đầu ra và điều kiện ở từng chặng.

### 7.3. Phân công trách nhiệm

| Hoạt động | Trách nhiệm tổ chức | Trách nhiệm nhà cung cấp |
|---|---|---|
| Xác định RPO, RTO và dữ liệu trong phạm vi | Chủ sở hữu nghiệp vụ phê duyệt | Xác nhận khả năng đáp ứng phần được giao |
| Xác thực và quyền truy cập dịch vụ | Phê duyệt danh tính, phạm vi và thu hồi theo phần quản lý | Thực thi và ghi dấu vết phần dịch vụ phụ trách |
| Sao lưu và theo dõi lỗi | Theo dõi kết quả, xử lý các cấu hình thuộc trách nhiệm nội bộ | Thực hiện, phát hiện lỗi và thông báo theo cam kết |
| Bảo vệ dữ liệu và khóa | Thực hiện phần quản lý khóa, quyền hoặc cấu hình đã phân công | Thực hiện phần lưu trữ, truy cập và bảo vệ đã phân công |
| Phục hồi hạ tầng hoặc dữ liệu | Gửi yêu cầu, phối hợp và cung cấp điều kiện cần thiết | Thực hiện phần phục hồi được mô tả |
| Xác nhận nghiệp vụ hoạt động | Kiểm tra tính toàn vẹn, quyền hiện hành và nghiệp vụ | Cung cấp kết quả, log và hỗ trợ |
| Kết thúc dịch vụ | Xác nhận chuyển giao và thu hồi quyền | Xuất dữ liệu, xử lý bản sao và cung cấp bằng chứng theo thỏa thuận |

Mỗi đầu ra phải có đầu mối và mốc thời gian. Một hàng có hai bên tham gia cần tách rõ phần việc, tránh ghi chung “cùng chịu trách nhiệm” mà không ai chủ trì.

### 7.4. Căn cứ trước khi kết luận phương án có hiệu quả

Cần có bằng chứng phù hợp về:

- Dữ liệu và bản sao thực sự nằm trong phạm vi dịch vụ.
- Quyền truy cập, xác thực và cơ chế thu hồi.
- Khả năng phát hiện, thông báo lỗi và phối hợp.
- Phục hồi có dữ liệu kiểm tra và mốc đo rõ ràng.
- Tính toàn vẹn cùng quyền hiện hành sau phục hồi.
- Khả năng xuất dữ liệu hoặc chuyển sang đích thay thế.
- Phần rủi ro chưa được xử lý, đặc biệt phụ thuộc và tập trung.

Báo cáo của nhà cung cấp cần được đối chiếu phạm vi, thời kỳ, dịch vụ và phần trách nhiệm của khách hàng. Không dùng một tài liệu chung để kết luận cấu hình cụ thể của tổ chức đã đúng.

## 8. Chuyển quyết định thành yêu cầu bảo mật

Một yêu cầu có ích phải nói rõ hành vi, điều kiện, thời hạn, người thực hiện và cách kiểm chứng. Hai câu “rủi ro đã được chấp nhận” và “nhà cung cấp chịu trách nhiệm” chưa đáp ứng điều đó.

### 8.1. Yêu cầu cho chấp nhận tạm thời

| Mã | Yêu cầu | Kiểm chứng |
|---|---|---|
| RA-DATA-01 | DIAG-011 chỉ được tạo từ danh sách trường kỹ thuật được phê duyệt. Trường mới không tự xuất hiện trong tệp; không có dữ liệu khách hàng hoặc bí mật hoạt động. | Dùng dữ liệu giả định và giá trị đánh dấu trong trường nguồn, nhánh lỗi; kiểm tra tệp và log thực tế. |
| RA-ACCESS-01 | Mọi lần đọc tệp phải xác minh danh tính và tư cách thành viên nhóm hỗ trợ phía máy chủ. Kho không cho truy cập công khai hoặc qua đường trực tiếp vượt quyền. | Thử chưa xác thực, ngoài nhóm, đường tải cũ và đường truy cập kho. |
| RA-REVIEW-01 | Kiểm tra quyền đầu tiên phải hoàn tất trước khi bắt đầu cơ chế tạm thời; mỗi kết quả chỉ có hiệu lực tối đa 24 giờ. Quá hạn, hệ thống phải từ chối tạo tệp mới cho đến khi có kết quả hợp lệ. | Mô phỏng mốc quá hạn và kiểm tra việc dừng, khôi phục; đối chiếu danh tính người kiểm tra và nội dung kết quả. |
| RA-EXPIRY-01 | Quyết định tạm thời hết hiệu lực sau 14 ngày kể từ mốc được phê duyệt. Hệ thống không được tiếp tục tạo tệp theo cơ chế tạm thời sau mốc đó nếu chưa có quyết định mới hợp lệ. | Thử trước và sau mốc hiệu lực; kiểm tra mọi tác vụ tạo, kể cả tác vụ chờ. |
| RA-LOG-01 | Thay đổi quyền, kết quả rà soát, truy cập bị từ chối và việc dừng chức năng phải có sự kiện chứa danh tính, thời điểm, đối tượng, hành động, kết quả và mã quyết định. Log không chứa tệp chẩn đoán gốc. | Sinh từng loại sự kiện, đối chiếu đủ trường và kiểm tra quyền bảo vệ log. |

### 8.2. Yêu cầu cho phần trách nhiệm được giao

| Mã | Yêu cầu | Kiểm chứng |
|---|---|---|
| RT-IDENTITY-01 | Nhân sự hỗ trợ truy cập bằng danh tính có thể truy vết, với xác thực đa yếu tố cho quyền quản trị theo chính sách tình huống. Danh tính dịch vụ có phạm vi riêng; quyền tạm thời phải có thời hạn và cơ chế thu hồi. | Thử thiếu điều kiện xác thực, ngoài phạm vi, sau hết hạn và sau thu hồi; kiểm tra cả phiên đã tồn tại. |
| RT-DATA-01 | Dữ liệu truyền, lưu và sao lưu phải được bảo vệ theo hồ sơ thiết kế đã duyệt, xác định rõ quyền dùng khóa, quyền quản trị, cấu hình và trách nhiệm từng bên. | Đối chiếu cấu hình, thử danh tính không có quyền đọc hoặc giải mã và kiểm tra các bản sao thuộc phạm vi. |
| RT-RECOVERY-01 | Phương án phải đạt RPO 15 phút và RTO 4 giờ trong kịch bản đã duyệt, được kiểm chứng theo quý và sau thay đổi lớn ảnh hưởng phục hồi. | Đo từ sự cố đến nghiệp vụ, đối chiếu tính đầy đủ dữ liệu, quyền hiện hành và phụ thuộc; không chỉ kiểm tra tệp sao lưu tồn tại. |
| RT-EVIDENCE-01 | Kết quả sao lưu, lỗi, yêu cầu hỗ trợ và phục hồi phải có mã liên kết, thời điểm, trạng thái và đầu mối. Mỗi lần kiểm chứng phải gắn với phiên bản dịch vụ, cấu hình và phạm vi. | Đối chiếu sự kiện giữa hai bên, kiểm tra trường hợp thiếu hoặc chậm bằng chứng và quy trình xử lý. |
| RT-EXIT-01 | Trước sử dụng, phải có kế hoạch chuyển dịch vụ nêu định dạng xuất, dữ liệu và cấu hình cần bàn giao, thời hạn, quyền truy cập và xử lý bản sao còn lại. Kế hoạch phải được kiểm chứng bằng một lần xuất và đọc lại có kiểm soát. | Đối chiếu dữ liệu, tính toàn vẹn, khả năng sử dụng tại đích thử và bằng chứng thu hồi hoặc xử lý theo phạm vi. |

Các yêu cầu này cần được gắn vào tài liệu thiết kế, trách nhiệm vận hành và thỏa thuận phù hợp. Một tiêu chí xuất hiện trong hồ sơ mua sắm nhưng không được thực thi và kiểm chứng vẫn có thể để lại khoảng trống.

## 9. Bằng chứng và mức đảm bảo cho quyết định

### 9.1. Chấp thuận không thay thế bằng chứng

Cần kiểm tra ít nhất ba lớp:

1. **Tính đúng của quyết định:** phạm vi, thẩm quyền, điều kiện và thời hạn có rõ không?
2. **Tính hiện hữu của kiểm soát:** các biện pháp được dùng làm căn cứ đã hoạt động chưa?
3. **Hiệu quả trong kịch bản:** chúng có xử lý đường rủi ro và hậu quả đã mô tả không?

Với R-ACC-011, một văn bản có chữ ký chưa chứng minh kiểm tra thủ công được thực hiện đúng hạn. Với R-TRF-011, hợp đồng chưa chứng minh dữ liệu có thể phục hồi trong 4 giờ.

### 9.2. Chọn độ sâu kiểm chứng theo hậu quả và bất định

Những phần có hậu quả nghiêm trọng, dữ liệu nhạy cảm, nhiều ranh giới hoặc nhiều giả định cần bằng chứng sâu hơn. Có thể bổ sung:

- Xem xét mô hình đe dọa và tính đầy đủ của phạm vi.
- Kiểm thử trường hợp từ chối, lỗi, quá hạn và đường thay thế.
- Kiểm tra tác vụ đang chờ, quyền cũ và bộ nhớ đệm.
- Diễn tập phối hợp hai bên và phục hồi đầu cuối.
- Xem xét độc lập với người tạo cấu hình hoặc triển khai.
- Đánh giá các khác biệt giữa môi trường thử và sản xuất.

Nếu dùng tên low, medium hoặc high assurance, cần định nghĩa hồ sơ bằng chứng tương ứng trong tổ chức. Không suy ra mức đảm bảo chỉ từ điểm rủi ro hoặc tên nhà cung cấp.

### 9.3. Bảng truy vết cho hai tình huống

| Kịch bản | Điều kiện hoặc trách nhiệm | Yêu cầu | Bằng chứng và giới hạn cần ghi |
|---|---|---|---|
| R-ACC-011 | Chỉ dùng dữ liệu chẩn đoán đã giới hạn | RA-DATA-01 | Nội dung đầu ra, nhánh lỗi và cấu trúc nguồn; giới hạn của việc phát hiện nội dung tự do |
| R-ACC-011 | Duy trì kiểm tra mỗi 24 giờ | RA-REVIEW-01, RA-LOG-01 | Kết quả kiểm tra, người thực hiện, thử quá hạn và log; phạm vi kiểm tra thủ công |
| R-ACC-011 | Không tiếp tục sau 14 ngày nếu thiếu quyết định mới | RA-EXPIRY-01 | Mốc hiệu lực, cấu hình và thử tác vụ chờ; phụ thuộc đồng hồ và nguồn quyết định |
| R-TRF-011 | Nhà cung cấp chỉ có quyền được giao | RT-IDENTITY-01, RT-DATA-01 | Chính sách, kiểm thử truy cập và log; phần hạ tầng không thể quan sát trực tiếp |
| R-TRF-011 | Đạt mục tiêu phục hồi nghiệp vụ | RT-RECOVERY-01 | Diễn tập, mốc đo, dữ liệu và quyền sau phục hồi; kịch bản sự cố đã thử |
| R-TRF-011 | Có khả năng chuyển dịch vụ | RT-EXIT-01 | Kết quả xuất, đọc lại và kiểm tra tính đầy đủ; điều kiện tại đích thay thế |

Bằng chứng cần có phiên bản, môi trường, dữ liệu kiểm thử, người thực hiện, kết quả và thời điểm. Một lần thử không đại diện cho mọi loại sự cố; giới hạn đó phải đi vào đánh giá tồn dư.

### 9.4. Đánh giá phần rủi ro còn lại

Sau triển khai và kiểm chứng, cập nhật:

- Kịch bản nào được giảm hoặc tránh.
- Phần trách nhiệm nào đã được phân bổ và dựa vào căn cứ gì.
- Hậu quả nào tổ chức vẫn chịu.
- Giả định, giới hạn và bất định còn lại.
- Likelihood và impact sau xử lý, với lý do thay đổi.
- Cấp có thẩm quyền cần quyết định tiếp.

Không tự hạ cả likelihood và impact vì “đã có hợp đồng”. Nếu dịch vụ vận hành tốt hơn, có thể có căn cứ giảm khả năng thất bại. Nếu có cơ chế phân bổ tổn thất, cần đánh giá đúng phần hậu quả được phân bổ. Hai lập luận này khác nhau.

Bảo vệ dữ liệu, tính sẵn sàng nghiệp vụ và tổn thất kinh tế cũng có thể thay đổi khác nhau. Không dùng một con số tổng để che phần hậu quả chưa được xử lý.

## 10. Theo dõi, hết hạn và thay đổi quyết định

### 10.1. Trạng thái quyết định phải rõ

Một luồng quản lý minh họa:

**Đề xuất → bổ sung căn cứ → quyết định → có hiệu lực → theo dõi → đóng hoặc đánh giá lại.**

Cần phân biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| Đề xuất | Chưa được phép dựa vào quyết định để hoạt động |
| Có hiệu lực | Đã được phê duyệt, điều kiện bắt đầu đã đáp ứng |
| Cần đánh giá lại | Có thay đổi hoặc thiếu bằng chứng ảnh hưởng căn cứ |
| Hết hiệu lực | Đã qua thời hạn hoặc điều kiện hiệu lực không còn |
| Đóng | Đã kết thúc phạm vi hoặc hoàn tất phương án thay thế với bằng chứng |

Tổ chức có thể dùng tên trạng thái khác, nhưng cần biết ai cập nhật và hệ thống phản ứng thế nào.

### 10.2. Tín hiệu kích hoạt đánh giá lại

Với chấp nhận rủi ro:

- Dữ liệu, người nhận hoặc môi trường vượt phạm vi.
- Kiểm soát bù đắp không hoạt động.
- Quá hạn rà soát hoặc thiếu người thực hiện.
- Có sự cố, bằng chứng khai thác hoặc tác động mới.
- Kế hoạch khắc phục không còn khả thi.
- Thẩm quyền hoặc người chịu trách nhiệm thay đổi.

Với chuyển giao:

- Nhà cung cấp thay đổi dịch vụ, cấu hình, nhà thầu phụ hoặc vị trí xử lý liên quan.
- Cam kết, điều kiện hoặc phạm vi bảo vệ thay đổi.
- Dịch vụ không đáp ứng hoặc bằng chứng không được cung cấp.
- Kết quả phục hồi, xuất dữ liệu hoặc kiểm tra quyền có sai lệch.
- Mức tập trung hoặc phụ thuộc tăng lên.
- Tổ chức thay đổi mục tiêu nghiệp vụ hoặc loại dữ liệu.

Không nên đợi hết chu kỳ nếu điều kiện quan trọng đã không còn đúng.

### 10.3. Hành động khi quá hạn hoặc vi phạm điều kiện

Cần đặc tả trước hành động tương xứng:

1. Ghi sự kiện và thông báo đầu mối có trách nhiệm.
2. Ngừng mở rộng phạm vi rủi ro hoặc dừng chức năng liên quan theo thiết kế.
3. Duy trì các kiểm soát nền và xử lý dữ liệu còn tồn tại.
4. Đánh giá có cần kích hoạt quy trình sự cố không.
5. Chọn khắc phục, kết thúc, phương án thay thế hoặc quyết định mới đúng thẩm quyền.
6. Lưu căn cứ và kết quả.

Trong tình huống A, dừng tạo tệp chẩn đoán mới không đồng nghĩa dừng nghiệp vụ xử lý đơn hàng. Hành động kết thúc phải đúng phạm vi, đồng thời không tạo thêm gián đoạn ngoài kế hoạch.

Gia hạn cần là một quyết định mới với căn cứ cập nhật. Không chỉ đổi ngày để giữ trạng thái “có hiệu lực”.

### 10.4. Chỉ số phục vụ theo dõi

| Chỉ số | Cách diễn giải đúng |
|---|---|
| Quyết định sắp hết hạn hoặc đã quá hạn | Cần chủ sở hữu và hành động cụ thể |
| Điều kiện chấp nhận chưa được xác minh | Phân biệt chưa có bằng chứng với đã phát hiện vi phạm |
| Sai lệch cam kết dịch vụ | Ghi phạm vi, mốc thời gian và tác động nghiệp vụ thực tế |
| Thời gian thu hồi quyền nhà cung cấp | Đo từ mốc đã định nghĩa đến lúc quyền thực sự mất hiệu lực |
| Kết quả phục hồi và chuyển dịch vụ | Nêu kịch bản, dữ liệu và giới hạn đã kiểm tra |
| Đầu việc khắc phục quá hạn | Gắn với quyết định và mức rủi ro hiện tại |

Không dùng số lượng quyết định đã ký làm thước đo duy nhất cho hiệu quả quản trị rủi ro. Việc duy trì đúng điều kiện và xử lý sai lệch mới giúp quyết định còn giá trị.

## 11. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Không xử lý thì coi là chấp nhận | Không có người chịu trách nhiệm hay giới hạn | Ghi quyết định chủ động, có căn cứ và thẩm quyền |
| Nhóm kỹ thuật tự chấp nhận hậu quả kinh doanh | Quyết định vượt phạm vi được giao | Đưa đến đúng chủ sở hữu và cấp có thẩm quyền |
| Chấp thuận đồng nghĩa yêu cầu đã đạt | Báo cáo kỹ thuật sai thực tế | Ghi riêng kết quả đáp ứng, ngoại lệ và quyết định |
| Chấp nhận mục tiêu thay cho rủi ro hiện tại | Đánh giá dựa trên kiểm soát chưa hoạt động | Tách hiện tại, mục tiêu và tồn dư đã xác minh |
| Hết hạn nhưng tự gia hạn | Cơ chế tạm thời trở thành lâu dài không kiểm soát | Quyết định lại với căn cứ cập nhật và phương án kết thúc |
| Thuê ngoài là chuyển toàn bộ rủi ro | Bỏ sót cấu hình, phụ thuộc và hậu quả giữ lại | Chỉ rõ phần việc, nghĩa vụ, hậu quả và giới hạn |
| Có cam kết dịch vụ là chắc chắn phục hồi được | Thiếu kiểm chứng nghiệp vụ đầu cuối | Đo toàn bộ RTO, RPO và kiểm tra phụ thuộc |
| Giảm phí dịch vụ bằng toàn bộ thiệt hại | Ước lượng sai phần hậu quả được phân bổ | Đánh giá cơ chế thực tế và tổn thất còn lại |
| Bảo hiểm thay cho kiểm soát bảo mật | Sự cố và hậu quả vẫn xảy ra | Duy trì yêu cầu bảo vệ và xem đúng phạm vi phân bổ tổn thất |
| Bằng chứng nhà cung cấp áp dụng cho mọi cấu hình | Kết luận không đúng phạm vi | Đối chiếu dịch vụ, thời kỳ và trách nhiệm khách hàng |
| Không có kế hoạch thoát | Khó đổi bên cung cấp hoặc khôi phục độc lập | Đặc tả xuất dữ liệu, kiểm tra và bàn giao trước sử dụng |
| Hai bên cùng chịu trách nhiệm nhưng không có đầu mối | Sự cố bị chậm xử lý | Tách đầu ra, người chủ trì và mốc thời gian |
| Chỉ theo dõi đến ngày ký | Điều kiện thực tế thay đổi nhưng quyết định vẫn được dùng | Giám sát hiệu lực và đánh giá lại theo sự kiện |

## 12. Bài tập thực hành

Một ứng dụng lưu dữ liệu khách hàng và sử dụng dịch vụ quản lý sao lưu. Có hai đề xuất:

1. Trong 10 ngày, dùng kiểm tra thủ công quyền truy cập bản xuất thay cho một cơ chế kiểm tra tự động chưa hoàn tất.
2. Giao nhà cung cấp phục hồi dữ liệu khi hạ tầng chính gặp sự cố, với mục tiêu dịch vụ được công bố trong tài liệu đề xuất.

Thực hiện:

1. Viết kịch bản rủi ro cho từng đề xuất, gồm tài sản, đường xảy ra, hậu quả và phạm vi.
2. Ghi likelihood, impact, căn cứ và những điều chưa biết.
3. Xác định yêu cầu bắt buộc nào vẫn phải đáp ứng.
4. Với đề xuất thứ nhất, viết điều kiện chấp nhận, người có thẩm quyền, mốc hết hiệu lực và hành động khi quá hạn.
5. Với đề xuất thứ hai, tách phần việc nhà cung cấp nhận, phần hậu quả được phân bổ và phần tổ chức giữ lại.
6. Viết yêu cầu về danh tính, phân quyền, log và phục hồi có cách đo rõ ràng.
7. Lập kế hoạch bằng chứng, gồm một trường hợp hợp lệ, một trường hợp trái quyền, một trường hợp lỗi và một trường hợp hết hạn.
8. Đề xuất cách chuyển dịch vụ hoặc kết thúc cơ chế tạm thời.

Câu hỏi tự đối chiếu:

- Quyết định đang chấp nhận rủi ro thực tế hay chỉ một mục tiêu dự kiến?
- Có đang dùng phê duyệt để thay cho bằng chứng yêu cầu đã đạt?
- Nhà cung cấp nhận phần hậu quả nào, căn cứ ở đâu?
- Khi nhà cung cấp không đáp ứng, tổ chức còn phải làm gì?
- Quyết định còn hiệu lực khi dữ liệu, người nhận hoặc kiến trúc thay đổi không?
- Có thể kết thúc phương án mà vẫn bảo vệ dữ liệu và duy trì nghiệp vụ trong giới hạn đã chọn không?

Chấp nhận và chuyển giao rủi ro đều cần giới hạn rõ ràng. Khi quyết định được gắn với yêu cầu, trách nhiệm, bằng chứng và cơ chế kết thúc, nhóm phát triển mới có cơ sở để triển khai và kiểm chứng phương án trong suốt vòng đời hệ thống.
