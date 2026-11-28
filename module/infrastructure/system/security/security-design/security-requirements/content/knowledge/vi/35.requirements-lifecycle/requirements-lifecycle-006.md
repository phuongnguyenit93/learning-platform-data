# Acceptance criteria: tiêu chí chấp nhận cho yêu cầu bảo mật

## 1. Tiêu chí chấp nhận giải quyết vấn đề gì?

“Hệ thống phải an toàn”, “phải kiểm tra quyền” hoặc “log phải đầy đủ” đều thể hiện mong muốn nhưng chưa đủ để quyết định một bản triển khai có được chấp nhận hay không. Người phát triển có thể cho rằng đã hoàn tất khi thêm một điều kiện trong code, trong khi người kiểm thử cần biết điều kiện đó phải đúng trên những đường truy cập nào, trong hoàn cảnh nào và với bằng chứng gì.

Acceptance criteria, hay tiêu chí chấp nhận, mô tả các điều kiện cần được chứng minh để chấp nhận một yêu cầu hoặc phần thay đổi trong phạm vi đã xác định. Với bảo mật, tiêu chí phải thể hiện cả hành vi được phép, hành vi phải bị ngăn, điều kiện khi lỗi và tác dụng phụ cần kiểm soát.

Trong chương Requirement lifecycle của module Security Requirements, tiêu chí chấp nhận là cầu nối từ mục tiêu an toàn thông tin và mô hình đe dọa tới kiến trúc, kiểm thử, bằng chứng và quyết định phát hành.

Sau bài học, người học có thể:

- Chuyển một yêu cầu bảo mật thành điều kiện có thể quan sát và kết luận.
- Xác định phạm vi, tiền điều kiện, kết quả, ngưỡng và bằng chứng.
- Viết tiêu chí cho xác thực, phân quyền, dữ liệu, logging và phục hồi.
- Phân biệt tiêu chí chấp nhận với ca kiểm thử và quy tắc hoàn thành chung.
- Quản lý tiêu chí theo phiên bản yêu cầu và thay đổi kiến trúc.

Mọi mã định danh, trạng thái HTTP, ngưỡng thời gian và tình huống trong bài là ví dụ thiết kế cho hệ thống giả định. Chúng cần được thống nhất theo rủi ro và hợp đồng thực tế; không phải giá trị mặc định do một tiêu chuẩn bảo mật bắt buộc.

## 2. Yêu cầu, tiêu chí, ca kiểm thử và Definition of Done

Bài này dùng các khái niệm theo quy ước sau; cách đặt tên trong từng tổ chức có thể khác.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Mục tiêu bảo mật | Nêu điều cần bảo vệ và vì sao | Giữ bí mật hóa đơn giữa các tổ chức |
| Yêu cầu bảo mật | Quy định hành vi hoặc thuộc tính phải có | Người dùng chỉ đọc được hóa đơn trong tổ chức mà họ có quyền |
| Acceptance criteria | Nêu điều kiện để chấp nhận yêu cầu trong phạm vi cụ thể | Đổi mã hóa đơn sang tài nguyên của tổ chức khác phải bị từ chối mà không trả dữ liệu hóa đơn |
| Ca kiểm thử | Chọn dữ liệu, thiết lập và thao tác cụ thể để thu bằng chứng | Đăng nhập bằng người dùng A1, gọi API với mã hóa đơn B7, kiểm tra phản hồi |
| Definition of Done | Nêu điều kiện hoàn thành chung của nhóm hoặc sản phẩm | Có review, kiểm thử bắt buộc đạt, tài liệu và bằng chứng được lưu |
| Quyết định chấp nhận | Ghi nhận kết luận theo tiêu chí và thẩm quyền | Chấp nhận bản triển khai theo bộ tiêu chí phiên bản 2 |

Một tiêu chí có thể cần nhiều ca kiểm thử: nhiều vai trò, API, định dạng đầu vào, trạng thái phiên hoặc thời điểm thay đổi quyền. Một ca kiểm thử cũng có thể tạo bằng chứng cho nhiều tiêu chí, nhưng phải truy vết được từng kết luận.

“Đã chạy scanner” là một hoạt động. Nó chưa tự là kết quả chấp nhận cho yêu cầu cách ly dữ liệu. Cần biết công cụ kiểm tra thuộc tính nào, bao phủ tới đâu và điều kiện phát hiện nào làm không đạt.

OWASP ASVS cung cấp một khung yêu cầu để thiết kế, phát triển và kiểm chứng bảo mật ứng dụng. Có thể dùng khung tham chiếu như vậy để tìm điều kiện còn thiếu, rồi cụ thể hóa cho hệ thống đang xây dựng. [Nguồn: OWASP Application Security Verification Standard](https://asvs.owasp.org/).

## 3. Cấu trúc của một tiêu chí kiểm chứng được

Một tiêu chí tốt thường làm rõ các thành phần sau.

| Thành phần | Điều cần xác định |
| --- | --- |
| Mã và liên kết | Tiêu chí thuộc yêu cầu nào, phiên bản nào, xử lý rủi ro nào |
| Phạm vi | Tài nguyên, thao tác, endpoint, vai trò, môi trường và phần loại trừ |
| Tiền điều kiện | Danh tính, quyền, dữ liệu, cấu hình và trạng thái phụ thuộc trước hành động |
| Tác nhân và hành động | Ai hoặc thành phần nào làm gì, qua đường nào |
| Kết quả mong đợi | Hành vi được phép hoặc phải bị từ chối |
| Điều không được xảy ra | Rò dữ liệu, thay đổi nghiệp vụ, tạo file hoặc phát sinh tác vụ trái phép |
| Ngưỡng và thời gian | Giới hạn, đơn vị, mốc bắt đầu và kết thúc, điều kiện biên |
| Bằng chứng | Phản hồi, sự kiện, báo cáo, cấu hình hoặc kiểm tra chuyên môn cần có |
| Quy tắc kết luận | Khi nào đạt, không đạt hoặc chưa đủ điều kiện đánh giá |

Có thể viết theo mẫu:

~~~text
AC-<mã>, thuộc SEC-<mã> phiên bản <n>

Trong phạm vi <đối tượng và đường truy cập>,
với <tiền điều kiện xác định>,
khi <tác nhân thực hiện hành động>,
hệ thống phải <kết quả quan sát được>,
đồng thời không được <hậu quả bị cấm>.

Nếu có ngưỡng: đo <đại lượng> từ <mốc đầu> tới <mốc cuối>.
Bằng chứng: <nguồn, thời điểm, phiên bản và phạm vi>.
~~~

Không phải tiêu chí nào cũng cần một biểu mẫu dài. Tuy nhiên, những thông tin quyết định kết luận phải xuất hiện trong tiêu chí hoặc tài liệu được tham chiếu rõ ràng.

### Kết quả cần rõ hơn tên công nghệ

“Có annotation kiểm tra quyền” hoặc “dùng thư viện xác thực X” thường mô tả cách triển khai. Nếu mục tiêu là ngăn người dùng A đọc dữ liệu B, tiêu chí cần chứng minh hành vi đó thực sự bị ngăn ở các đường liên quan.

Khi thuật toán, giao thức hoặc cách triển khai là một ràng buộc bắt buộc, vẫn phải ghi nó cùng phiên bản chính sách được áp dụng. Tiêu chí lúc đó có thể cần cả kiểm tra cấu hình và kiểm chứng hành vi; không chỉ kiểm tra một dòng cấu hình tồn tại.

## 4. Chọn tình huống từ mô hình đe dọa

Không nên chỉ viết một tiêu chí cho luồng thành công. Từ yêu cầu và mô hình đe dọa, xác định các nhóm tình huống có thể làm thay đổi kết luận:

| Nhóm | Ví dụ cần cân nhắc |
| --- | --- |
| Được phép | Người đúng vai trò truy cập đúng tài nguyên |
| Bị cấm | Người thiếu quyền, sai tổ chức hoặc chưa xác thực |
| Điều kiện biên | Phiên vừa hết hạn, liên kết đúng thời điểm hết hiệu lực, số lần thử sát ngưỡng |
| Thay đổi trạng thái | Thu hồi quyền sau khi đăng nhập hoặc sau khi tạo tác vụ |
| Phụ thuộc lỗi | Dịch vụ quyết định quyền mất kết nối, kho bằng chứng tạm ngừng |
| Đường thay thế | API, tải file, tác vụ nền, cache hoặc chức năng quản trị khác |
| Tác dụng phụ | Không trả dữ liệu nhưng vẫn tạo file, gửi thông báo hoặc sửa trạng thái |
| Khả năng điều tra | Có sự kiện đúng nội dung mà không ghi bí mật vào log |

Không cần nhân mọi giá trị thành toàn bộ tổ hợp có thể có. Cần chọn tổ hợp theo rủi ro và cấu trúc kiến trúc, đồng thời ghi rõ phạm vi chưa được kiểm chứng.

Một tiêu chí không thể chứng minh “không tồn tại bất kỳ lỗ hổng nào”. Nó chỉ tạo ra một mệnh đề có phạm vi và cách thu bằng chứng đủ rõ để phát hiện sai lệch và hỗ trợ quyết định.

## 5. Ví dụ xuyên suốt: cách ly dữ liệu hóa đơn

### 5.1. Yêu cầu và dữ liệu thử

Giả sử sản phẩm có API đọc hóa đơn và chức năng tạo bản xuất.

**SEC-AUTHZ-12 phiên bản 2:** người dùng chỉ được đọc và yêu cầu xuất hóa đơn của tổ chức mà họ có quyền tại thời điểm quyết định truy cập, qua mọi đường truy cập thuộc phạm vi.

**Rủi ro:** người dùng hợp lệ của tổ chức A thay mã tài nguyên để đọc hoặc xuất dữ liệu của B. Client có thể gửi mã tổ chức giả, nên dữ liệu do client cung cấp không được tự trở thành căn cứ cấp quyền.

Dữ liệu thử gồm:

- Tổ chức A và B có bộ hóa đơn tổng hợp tách biệt.
- Người dùng A-reader có quyền đọc tại A nhưng không có quyền xuất.
- Người dùng A-exporter có quyền đọc và xuất tại A.
- Người dùng B-reader chỉ có quyền tại B.
- Có ít nhất một mã hóa đơn không tồn tại và một danh tính không còn quyền.

Phạm vi ban đầu gồm API đọc chi tiết, API tạo bản xuất và đường tải kết quả. Nếu có worker nền, việc kiểm tra trên worker và vòng đời quyền phải được bổ sung rõ, không mặc nhiên suy ra từ kiểm thử API.

### 5.2. Bộ tiêu chí chấp nhận minh họa

| Mã | Điều kiện và hành động | Kết quả phải chứng minh |
| --- | --- | --- |
| AC-12-01 | A-reader yêu cầu hóa đơn của A mà họ được đọc | Trả kết quả thành công theo hợp đồng, đúng hóa đơn và danh sách trường được phép |
| AC-12-02 | A-reader yêu cầu mã hóa đơn của B | Theo hợp đồng ví dụ, trả 404 với nội dung lỗi chung; không trả nội dung hoặc metadata hóa đơn B |
| AC-12-03 | A-reader đổi mã tổ chức trong đường dẫn, query hoặc header được API hỗ trợ | Không làm thay đổi quyền thực tế; không nhận dữ liệu B |
| AC-12-04 | Yêu cầu đọc không có thông tin xác thực hợp lệ | Theo hợp đồng ví dụ, trả 401; không trả dữ liệu hóa đơn |
| AC-12-05 | A-reader gọi API tạo bản xuất vốn đòi quyền xuất | Theo hợp đồng ví dụ, trả 403; không tạo tác vụ hoặc file xuất nghiệp vụ cho yêu cầu bị từ chối |
| AC-12-06 | A-exporter tạo bản xuất hợp lệ tại A | Kết quả chỉ chứa dữ liệu và trường thuộc phạm vi được cấp |
| AC-12-07 | Người không có quyền thử tải kết quả xuất của người khác hoặc tổ chức khác | Không nhận được file, nội dung hay metadata bị giới hạn; đường tải không bỏ qua kiểm tra quyền |
| AC-12-08 | Hệ thống không xác định được quyền vì phụ thuộc quyết định truy cập bị lỗi | Không cấp dữ liệu theo mặc định; trả lỗi đã thỏa thuận, ví dụ 503, thay vì coi lỗi phụ thuộc là được phép |

Mỗi dòng cần được triển khai thành các phép kiểm tra phù hợp. Ví dụ AC-12-03 chỉ áp dụng cho những vị trí đầu vào thực sự tồn tại; ghi rõ cách xử lý khi giá trị client gửi mâu thuẫn với ngữ cảnh danh tính.

404 trong AC-12-02 là một lựa chọn hợp đồng API nhằm hạn chế tiết lộ sự tồn tại của tài nguyên. Mã trạng thái này tự nó không chứng minh không có rò rỉ: vẫn phải kiểm tra body, header, thông báo và các thuộc tính khác mà yêu cầu đã quy định.

Với AC-12-05, việc ghi audit cho lần từ chối hoặc tăng bộ đếm chống lạm dụng có thể vẫn được phép. “Không có tác dụng phụ nghiệp vụ” không đồng nghĩa cấm mọi ghi nhận phục vụ bảo mật.

### 5.3. Khi thay đổi quyền giữa hai bước

Nếu bản xuất được tạo bất đồng bộ, cần quyết định thời điểm đánh giá quyền:

- Khi tiếp nhận yêu cầu.
- Khi worker bắt đầu xử lý.
- Khi công bố hoặc cho tải kết quả.

Không thể chỉ viết “worker phải dùng đúng quyền” vì các thời điểm có thể có trạng thái khác nhau. Ví dụ một chính sách có thể yêu cầu kiểm tra lại trước khi xử lý và trước khi cho tải, với giới hạn đồng bộ thu hồi được xác định riêng.

Một tiêu chí bổ sung có thể là:

> Khi quyền xuất của người dùng đã bị thu hồi và trạng thái thu hồi đã có hiệu lực theo thời hạn yêu cầu, các lần tải kết quả mới phải bị từ chối, kể cả khi file được tạo trước đó. Phép kiểm tra phải bao gồm đường tải trực tiếp đang được kiến trúc hỗ trợ.

Nếu dùng liên kết tải không cần phiên đăng nhập, phải xem cơ chế đó có thực thi được yêu cầu thu hồi hay không. Một liên kết còn hạn không tự đáp ứng chính sách quyền hiện tại.

Không nên hứa thu hồi ngay mọi byte của một luồng tải đã bắt đầu nếu kiến trúc chưa hỗ trợ. Phạm vi với yêu cầu mới, kết nối đang mở và file đã tải xuống phải được đặc tả riêng.

## 6. Viết bằng Given–When–Then khi phù hợp

Given–When–Then giúp tách trạng thái ban đầu, hành động và kết quả mong đợi. Tài liệu Gherkin mô tả Given thiết lập trạng thái xác định, When thể hiện hành động và Then kiểm tra kết quả quan sát được. Đây là một cách trình bày, không phải điều kiện bắt buộc để một tiêu chí có giá trị. [Nguồn: Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/).

~~~gherkin
Feature: Cách ly dữ liệu hóa đơn giữa các tổ chức

  Scenario: Người dùng đọc hóa đơn thuộc phạm vi được cấp
    Given A-reader có quyền đọc hóa đơn INV-A-01 của tổ chức A
    When A-reader yêu cầu đọc INV-A-01 qua API
    Then phản hồi thành công theo hợp đồng
    And phản hồi chỉ có các trường được phép của INV-A-01

  Scenario: Người dùng không đọc được hóa đơn của tổ chức khác
    Given A-reader chỉ có quyền tại tổ chức A
    And INV-B-01 thuộc tổ chức B
    When A-reader yêu cầu đọc INV-B-01 qua API
    Then phản hồi là 404 với nội dung lỗi chung đã quy định
    And phản hồi không chứa nội dung hoặc metadata của INV-B-01

  Scenario: Người thiếu quyền xuất không tạo được tác vụ xuất
    Given A-reader có quyền đọc nhưng không có quyền xuất tại A
    When A-reader yêu cầu tạo bản xuất hóa đơn của A
    Then phản hồi là 403 theo hợp đồng
    And không có tác vụ hoặc file xuất nghiệp vụ được tạo bởi yêu cầu đó
~~~

Các scenario trên là ví dụ đặc tả. Chúng chỉ trở thành kiểm thử thực thi khi có dữ liệu, bước thiết lập, thao tác và phép kiểm tra tương ứng.

Bằng chứng bên ngoài phù hợp để xác nhận hành vi mà người dùng hoặc hệ thống khác quan sát được. Với thuộc tính nội bộ như quản lý khóa, quyền của tiến trình hoặc bảo vệ kho audit, có thể cần thêm kiểm tra cấu hình, kiến trúc và quyền quản trị. Không buộc mọi tiêu chí bảo mật vào một màn hình hay một mã HTTP.

## 7. Tiêu chí cho năm nhóm yêu cầu bảo mật

### 7.1. Xác thực: kiểm tra hành vi và vòng đời phiên

Tiêu chí “người dùng đã đăng ký MFA” chưa chứng minh MFA được thực thi khi truy cập tài nguyên. Cần chỉ rõ loại người dùng, chính sách áp dụng và trạng thái phiên đủ điều kiện.

Ví dụ:

- **AC-AUTH-01:** khi người quản trị chưa có phiên đáp ứng chính sách MFA phiên bản được phê duyệt, họ không thể thực hiện thao tác quản trị thuộc phạm vi.
- **AC-AUTH-02:** khi phiên đáp ứng chính sách và người dùng có đúng quyền, thao tác hợp lệ vẫn thực hiện được. Tiêu chí này tránh việc hệ thống từ chối mọi truy cập nhưng được đánh giá là an toàn.
- **AC-AUTH-03:** sau khi tài khoản bị vô hiệu hóa tại nguồn danh tính có thẩm quyền, mọi yêu cầu quản trị mới qua các đường được liệt kê phải bị từ chối muộn nhất sau 300 giây.
- **AC-AUTH-04:** thông tin xác thực không hợp lệ không xuất hiện trong phản hồi lỗi hoặc log theo danh sách nguồn bằng chứng đã xác định.

AC-AUTH-03 cần quy định rõ có bao gồm token truy cập, cookie phiên và phiên ứng dụng cũ không. Khóa tài khoản ở IdP không tự chứng minh những cơ chế còn lại đã hết hiệu lực.

Nếu chính sách yêu cầu một thuộc tính xác thực cụ thể, tiêu chí cần kiểm chứng thuộc tính đó từ nguồn đáng tin cậy. Không lấy một trường do client tự khai làm bằng chứng phiên đã đáp ứng MFA.

### 7.2. Phân quyền: kiểm tra cả cho phép và từ chối

Ngoài bộ tiêu chí hóa đơn, cần phân biệt:

- Quyền trên chức năng: người dùng được gọi thao tác nào.
- Quyền trên đối tượng: người dùng được tác động lên bản ghi nào.
- Quyền trên thuộc tính: người dùng được đọc hoặc sửa trường nào.
- Quyền trên thời điểm và trạng thái: hành động còn được phép sau thu hồi hoặc đổi trạng thái nghiệp vụ không.

Ví dụ “chỉ người có quyền phê duyệt được duyệt hóa đơn” cần thêm điều kiện nếu nghiệp vụ cấm tự phê duyệt: người tạo hóa đơn không được tự phê duyệt chính hóa đơn đó, kể cả khi họ có vai trò phê duyệt nói chung.

Tiêu chí nên mô tả bất biến nghiệp vụ, chẳng hạn “không có hóa đơn nào chuyển sang trạng thái đã duyệt bằng thao tác của chính người tạo khi chính sách tách nhiệm vụ áp dụng”. Phép kiểm thử cần kiểm tra cả API, chức năng quản trị và đường xử lý nền có thể tạo chuyển trạng thái đó.

### 7.3. Dữ liệu: tách các thuộc tính cần bảo vệ

“Dữ liệu được bảo vệ” nên được tách thành các tiêu chí độc lập về lưu trữ, truyền, quyền truy cập, lưu giữ và xóa.

Ví dụ với file xuất hóa đơn:

| Mã | Điều kiện chấp nhận minh họa |
| --- | --- |
| AC-DATA-01 | File chỉ chứa các trường nằm trong danh sách được phê duyệt cho vai trò và mục đích xuất |
| AC-DATA-02 | File trong kho thuộc phạm vi được mã hóa theo chính sách có phiên bản; bằng chứng gồm cấu hình hiệu lực và cơ chế quản lý khóa liên quan |
| AC-DATA-03 | Danh tính ngoài danh sách được cấp không đọc được file hoặc sử dụng đường giải mã được hệ thống hỗ trợ |
| AC-DATA-04 | Đường tải không cho người không có quyền lấy file bằng cách biết mã hoặc URL |
| AC-DATA-05 | File hết thời hạn phục vụ không còn tải được qua các đường đã liệt kê, kể cả khi trước đó từng được truy cập |

AC-DATA-02 không được chứng minh chỉ bằng việc “không tìm thấy một chuỗi rõ” trong file nhị phân. Kiểm chứng cơ chế mã hóa cần bằng chứng phù hợp về cấu hình, khóa và ranh giới truy cập.

Nếu yêu cầu còn bao gồm xóa khỏi cache, bản sao tìm kiếm hoặc backup, phải có tiêu chí và thời hạn riêng cho từng loại. Việc không tải được file qua API chưa chứng minh mọi bản sao đã bị xóa vật lý.

### 7.4. Logging: định nghĩa sự kiện và chất lượng bằng chứng

Ví dụ yêu cầu: mọi thay đổi quyền quản trị thành công và bị từ chối phải có bằng chứng phục vụ điều tra.

Tiêu chí cho điều kiện vận hành bình thường có thể là:

> Khi thực hiện một thay đổi quyền quản trị hoặc nhận quyết định từ chối thay đổi quyền, sự kiện tương ứng phải có thể truy xuất tại kho audit trong tối đa 60 giây, gồm mã sự kiện, chủ thể, đối tượng, hành động, kết quả, thời điểm và mã tương quan; không chứa mật khẩu, token hoặc khóa bí mật.

Để kết luận tiêu chí này, cần xác định:

- Bắt đầu đo từ lúc quyết định xử lý được tạo ở đâu.
- Sự kiện có thể được gửi lại khi retry hay không; cách nhận diện cùng một sự kiện logic.
- Trường bắt buộc và giá trị kỳ vọng của cả trường hợp thành công lẫn từ chối.
- Các nguồn phản hồi và log cần kiểm tra việc không lộ bí mật.
- Cách xử lý đồng hồ lệch và bằng chứng tới trễ.

Trạng thái khi đường audit lỗi cần một tiêu chí riêng theo chính sách. Ví dụ, nếu thao tác nhạy cảm chỉ được hoàn tất sau khi có bản ghi bền vững tại một điểm lưu được phê duyệt, phép thử phải làm điểm lưu đó mất khả dụng và xác nhận thao tác không có hiệu lực trước khi điều kiện ghi nhận được đáp ứng.

Một collector còn gửi heartbeat chưa chứng minh ứng dụng có tạo đúng sự kiện bắt buộc. Cần phát sinh thao tác tổng hợp và đối chiếu bằng mã tương quan đầu cuối.

### 7.5. Phục hồi: đo kết quả nghiệp vụ

Tiêu chí “backup chạy thành công” khác với “dịch vụ phục hồi được theo yêu cầu”.

Giả sử mục tiêu đã được phê duyệt là RPO tối đa 15 phút và RTO tối đa 2 giờ trong kịch bản mất vùng lưu trữ chính. Tiêu chí cần bao gồm:

- Kịch bản sự cố, bộ dữ liệu và các phụ thuộc thuộc phạm vi diễn tập.
- Mốc bắt đầu sự cố giả lập và mốc dịch vụ đạt điều kiện sẵn sàng.
- Mốc dữ liệu nhất quán cuối cùng thực sự phục hồi được.
- Kiểm tra quyền truy cập, cấu hình, khóa và chức năng nghiệp vụ sau phục hồi.
- Bằng chứng thời gian và dữ liệu để tính RPO, RTO.

Ví dụ:

~~~text
t0: thời điểm gây sự cố giả lập đã thống nhất
t_ready: thời điểm dịch vụ phục hồi đạt toàn bộ tiêu chí sẵn sàng
t_data: mốc dữ liệu nhất quán cuối cùng khôi phục được trước t0

Thời gian phục hồi đo được = t_ready - t0
Khoảng mất dữ liệu đo được = t0 - t_data

Đạt nếu:
  thời gian phục hồi <= 2 giờ
  khoảng mất dữ liệu <= 15 phút
  kiểm tra toàn vẹn, quyền truy cập và chức năng nghiệp vụ đều đạt
~~~

Cần định nghĩa thế nào là “mốc dữ liệu nhất quán”, thay vì lấy thời gian sửa file backup làm bằng chứng. Một trang health check trả 200 cũng chưa chứng minh người dùng thực hiện được nghiệp vụ hoặc dữ liệu đã đủ nhất quán.

## 8. Ngưỡng, thời gian và điều kiện biên

Các từ “nhanh”, “đủ”, “gần như ngay” hoặc “sớm” cần được thay bằng định nghĩa phù hợp. Nhưng thêm một con số vẫn chưa đủ nếu chưa rõ cách đo.

### Ví dụ thu hồi quyền trong 300 giây

Định nghĩa:

- t0 là thời điểm nguồn có thẩm quyền xác nhận thay đổi thu hồi đã có hiệu lực.
- Các đường truy cập và loại phiên thuộc phạm vi được liệt kê.
- Mọi yêu cầu mới bắt đầu tại hoặc sau t0 + 300 giây phải bị từ chối theo chính sách.
- Phép đo dùng mốc thời gian đáng tin cậy; sai số đồng hồ phải đủ nhỏ để phân biệt đạt và không đạt.

Nên kiểm tra trước, tại và sau ranh giới với độ phân giải phù hợp. Nếu sai số phép đo lớn tới mức không biết hành vi xảy ra ở bên nào ranh giới, kết quả là chưa đủ bằng chứng để kết luận đạt.

Tiêu chí có thể cho phép hệ thống thu hồi sớm hơn. Không cần yêu cầu truy cập vẫn được phép ở giây thứ 299 nếu chính sách chỉ quy định thời hạn tối đa 300 giây.

### Phân biệt giới hạn tuyệt đối và phân vị

“Mọi yêu cầu trái quyền phải bị từ chối” khác với “95% yêu cầu trái quyền bị từ chối”. Một chỉ số phân vị phù hợp cho một số mục tiêu hiệu năng, nhưng không được tự dùng để nới lỏng một bất biến phân quyền.

Với tiêu chí đo theo tỷ lệ, phải ghi mẫu số, cửa sổ đo, điều kiện tải, nhóm đối tượng và cách xử lý dữ liệu thiếu. Không lấy số ca đã chạy làm toàn bộ phạm vi hệ thống rồi tuyên bố không còn vi phạm.

## 9. Bằng chứng và quy tắc kết luận

Một tiêu chí có thể cần nhiều loại bằng chứng:

| Thuộc tính cần chứng minh | Bằng chứng có thể phù hợp |
| --- | --- |
| Hành vi cho phép hoặc từ chối | Kết quả kiểm thử qua giao diện hoặc API liên quan |
| Đường đi vòng bị chặn | Kiểm thử từ các vùng truy cập và đường kiến trúc thuộc phạm vi |
| Cấu hình kiểm soát có hiệu lực | Cấu hình triển khai thực tế, chính sách và kiểm tra hành vi |
| Giới hạn quyền của dịch vụ | Quyền hiệu lực, thử truy cập được phép và bị cấm |
| Nội dung audit và độ trễ | Sự kiện tổng hợp, mã tương quan và thời điểm thu nhận |
| Phục hồi | Báo cáo diễn tập, dữ liệu khôi phục và kiểm tra nghiệp vụ |
| Quản lý khóa hoặc phân tách nhiệm vụ | Xem xét thiết kế, cấu hình, quyền và hồ sơ vận hành phù hợp |

Kiểm thử chỉ xác nhận mock từ chối truy cập không chứng minh cấu hình production kết nối đúng tới cơ chế quyết định quyền. Ngược lại, chỉ xem cấu hình không đủ để chứng minh mọi đường thực thi sử dụng cơ chế đó.

Bằng chứng tối thiểu nên gắn với:

- Mã yêu cầu, mã tiêu chí và phiên bản.
- Bản triển khai, cấu hình và môi trường được đánh giá.
- Bộ dữ liệu hoặc cách tạo dữ liệu tổng hợp.
- Thời điểm thực hiện, công cụ hoặc người thực hiện.
- Kết quả kỳ vọng, kết quả quan sát và giới hạn phạm vi.
- Phát hiện liên quan, quyết định xử lý và quyền truy cập bằng chứng.

Không lưu mật khẩu, token sống hoặc dữ liệu khách hàng thật vào báo cáo chỉ để làm bằng chứng. Dữ liệu tổng hợp có mã nhận diện riêng thường giúp xác minh rò rỉ hoặc đối chiếu sự kiện mà không tăng phạm vi dữ liệu nhạy cảm.

### Tách kết quả đánh giá khỏi quyết định vận hành

| Kết quả | Ý nghĩa |
| --- | --- |
| PASS | Bằng chứng cho thấy điều kiện đã định đạt trong phạm vi và phiên bản được kiểm tra |
| FAIL | Có bằng chứng một điều kiện không đạt |
| NOT_ASSESSED hoặc BLOCKED | Chưa đánh giá được do thiếu môi trường, dữ liệu, quyền hoặc bằng chứng |
| NOT_APPLICABLE | Có căn cứ được xem xét rằng tiêu chí không áp dụng cho phạm vi này |

Tên trạng thái tùy tổ chức, nhưng không được gộp “chưa đánh giá” vào PASS. Một test không chạy do môi trường lỗi không phải là test đã đạt.

Nếu một tiêu chí FAIL nhưng có ngoại lệ được phê duyệt, hãy giữ kết quả kỹ thuật và gắn quyết định ngoại lệ riêng. Quyết định tiếp tục vận hành trong điều kiện giới hạn không biến bằng chứng không đạt thành bằng chứng đạt.

Cũng cần phân biệt chất lượng bằng chứng: kết quả hết hạn, không biết phiên bản cấu hình hoặc thiếu một đường truy cập quan trọng không hỗ trợ được cùng kết luận với bằng chứng đầy đủ, còn hiệu lực.

## 10. Quản lý tiêu chí trong vòng đời yêu cầu

Tiêu chí chấp nhận nên được xây dựng trước khi hoàn tất triển khai, để kiến trúc có điểm thực thi và điểm quan sát cần thiết. Nếu đợi cuối kỳ mới viết tiêu chí, nhóm có thể phát hiện quá muộn rằng không có cách đo thu hồi phiên, đối chiếu danh tính hay chứng minh phục hồi.

NIST SSDF khuyến nghị đưa các thực hành phát triển phần mềm an toàn vào vòng đời phát triển. Đối với chủ đề này, có thể cụ thể hóa bằng việc duy trì yêu cầu, điều kiện kiểm chứng và bằng chứng xuyên suốt các lần thay đổi. [Nguồn: NIST SP 800-218 — Secure Software Development Framework](https://csrc.nist.gov/pubs/sp/800/218/final).

| Giai đoạn | Công việc với tiêu chí |
| --- | --- |
| Phân tích yêu cầu | Liên kết mục tiêu, rủi ro, nghĩa vụ và phạm vi |
| Thiết kế | Xác nhận kiến trúc có thể đáp ứng và tạo bằng chứng |
| Lập kế hoạch | Thống nhất dữ liệu, môi trường, người đánh giá và điều kiện chặn phát hành |
| Xây dựng | Viết các kiểm thử phù hợp, triển khai kiểm soát và khả năng quan sát |
| Chấp nhận thay đổi | Đánh giá từng tiêu chí trên đúng bản triển khai, lưu bằng chứng và giới hạn |
| Vận hành | Kiểm chứng các điều kiện cần tiếp tục được duy trì |
| Thay đổi hoặc ngừng dùng | Đánh giá tác động, cập nhật hoặc kết thúc tiêu chí có truy vết |

### Quản lý phiên bản và thay đổi phạm vi

Một chuỗi truy vết có thể là:

~~~text
RISK-17: đọc hóa đơn khác tổ chức
  -> SEC-AUTHZ-12 v2
  -> AC-12-01 ... AC-12-08
  -> thành phần API, worker, kho file, đường tải
  -> ca kiểm thử và đánh giá cấu hình
  -> bằng chứng trên bản triển khai cụ thể
  -> phát hiện, quyết định chấp nhận và điều kiện vận hành
~~~

Giả sử phiên bản đầu chỉ có API trả dữ liệu đồng bộ. Phiên bản mới bổ sung worker và URL tải file. Các ca kiểm thử API cũ có thể vẫn đạt, nhưng không chứng minh đường tải mới đáp ứng yêu cầu.

Cần xem xét ít nhất: danh tính được truyền tới worker như thế nào, quyền được đánh giá tại thời điểm nào, file gắn với ai, dữ liệu có bị lưu ngoài phạm vi và quyền tải có được thu hồi đúng hạn không.

Nếu thay đổi kết quả mong đợi, ngưỡng hoặc phạm vi, phải quản lý phiên bản tiêu chí. Không sửa âm thầm từ “mọi phiên phải bị thu hồi trong 300 giây” thành “đa số phiên được thu hồi” chỉ để phù hợp với kết quả triển khai.

Bằng chứng của phiên bản cũ chỉ được tái sử dụng khi có căn cứ rằng thay đổi không ảnh hưởng kết luận. Khi chưa rõ, cần xác định phần phải kiểm chứng lại.

## 11. Những cách viết dễ gây kết luận sai

| Cách viết thiếu rõ ràng | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| Hệ thống đăng nhập an toàn | Không có phạm vi hoặc kết quả đo được | Nêu điều kiện phiên, chính sách xác thực và đường truy cập phải bảo vệ |
| Có kiểm tra quyền | Chưa biết kiểm tra quyền nào, ở đâu | Nêu chủ thể, thao tác, đối tượng, thời điểm và kết quả khi bị cấm |
| API trả 403 khi bị từ chối | Có thể vẫn tạo file hoặc thay đổi dữ liệu | Bổ sung điều kiện không có tác dụng phụ nghiệp vụ trái phép |
| Token hợp lệ được chấp nhận | Chỉ bao phủ trường hợp thành công | Bổ sung các trường hợp sai hoặc hết hiệu lực theo chính sách đang áp dụng |
| Không có lỗ hổng nghiêm trọng | Chưa biết nguồn phát hiện, cách phân loại hoặc phạm vi | Nêu phép đánh giá, phạm vi, ngưỡng xử lý và cơ chế ngoại lệ |
| Log ghi đầy đủ | Không biết sự kiện, trường hoặc độ trễ | Liệt kê sự kiện bắt buộc, dữ liệu cần có, dữ liệu cấm ghi và cửa sổ thu nhận |
| Backup thành công mỗi ngày | Chưa chứng minh phục hồi được | Xác định kịch bản, dữ liệu, RPO, RTO và điều kiện nghiệp vụ sau phục hồi |
| Test pass là được chấp nhận | Có thể test thiếu phạm vi hoặc sai oracle | Truy vết từng tiêu chí tới bằng chứng và kiểm tra kết quả kỳ vọng độc lập |

“Không có phát hiện” luôn cần giới hạn theo cách đánh giá. Nó không đồng nghĩa không có điểm yếu chưa được công cụ hoặc người đánh giá nhận ra.

Một nguy cơ khác là sao chép logic triển khai vào phép kiểm tra. Ví dụ hệ thống lấy tổ chức từ header do client gửi, còn test cũng dùng header đó làm căn cứ quyền. Cả hai có thể cùng sai mà test vẫn đạt. Kết quả kỳ vọng phải xuất phát từ danh tính, quyền và dữ liệu do nguồn có thẩm quyền xác định.

## 12. Quy trình viết một bộ tiêu chí

Có thể thực hiện theo bảy bước:

1. **Nêu mục tiêu và rủi ro:** điều gì cần bảo vệ, ai có thể làm sai và hậu quả là gì.
2. **Chốt phạm vi:** tài sản, vai trò, thao tác, đường truy cập, thời điểm và điều kiện loại trừ.
3. **Xác định kết quả:** hành vi được phép, hành vi bị cấm và tác dụng phụ cần kiểm soát.
4. **Bổ sung biên và lỗi:** thay đổi quyền, hết hạn, phụ thuộc mất khả dụng, retry hoặc đường thay thế.
5. **Định nghĩa phép đo:** đơn vị, ngưỡng, cửa sổ, mốc thời gian và sai số chấp nhận.
6. **Chọn bằng chứng:** phương pháp, dữ liệu, môi trường và cách đối chiếu đúng kết quả.
7. **Thống nhất quyết định:** người đánh giá, điều kiện chặn phát hành, cách xử lý thiếu bằng chứng và quản lý phiên bản.

Trong trao đổi giữa nghiệp vụ, bảo mật, kiến trúc, phát triển và kiểm thử, mục tiêu là loại bỏ cách hiểu khác nhau trước khi chúng trở thành lỗi sản phẩm. Không cần buộc mọi vai trò xem từng chi tiết kỹ thuật; cần đúng người xác nhận phần họ có thẩm quyền và hiểu tác động.

Tiêu chí phải đủ cụ thể để đánh giá, đồng thời giữ đúng mức đặc tả. Chi tiết cài đặt không bắt buộc có thể để trong thiết kế hoặc ca kiểm thử; các ràng buộc an toàn bắt buộc không được bỏ đi chỉ để câu văn ngắn hơn.

## 13. Thực hành xây dựng tiêu chí

Với chức năng xuất hóa đơn, hãy xây dựng bộ tiêu chí cho:

- Người đúng quyền tạo và tải kết quả hợp lệ.
- Người sai tổ chức hoặc thiếu quyền bị từ chối.
- Quyền bị thu hồi trong lúc tác vụ đang chờ hoặc file đã được tạo.
- Dịch vụ quyết định quyền mất khả dụng.
- File hết thời hạn phục vụ.
- Sự kiện audit xuất hiện đúng nội dung, đúng thời hạn và không chứa bí mật.
- Khả năng phục hồi đáp ứng RPO, RTO và điều kiện nghiệp vụ đã thỏa thuận.

Mỗi tiêu chí cần có mã, yêu cầu liên quan, tiền điều kiện, hành động, kết quả, giới hạn thời gian nếu có và bằng chứng. Sau đó chọn ca kiểm thử đại diện cho hành vi hợp lệ, hành vi bị cấm và điều kiện biên; ghi rõ phần chưa được bao phủ.

Một bộ acceptance criteria có ích giúp người triển khai biết phải đạt điều gì, người kiểm thử biết phải chứng minh điều gì và người ra quyết định biết kết luận có giới hạn ở đâu. Giá trị nằm ở mối liên hệ rõ ràng giữa rủi ro, hành vi cần bảo đảm và bằng chứng trên hệ thống thực tế.
