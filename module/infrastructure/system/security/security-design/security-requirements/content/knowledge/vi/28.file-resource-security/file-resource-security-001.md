# File upload requirement

## 1. Vì sao upload cần một bộ yêu cầu bảo mật riêng?

Upload đưa dữ liệu do bên khác kiểm soát vào hệ thống lưu trữ, bộ xử lý và luồng phân phối của ứng dụng. Tệp có thể ảnh hưởng tới người gửi, người tải xuống, dịch vụ phân tích và các tenant dùng chung hạ tầng. Vì vậy, yêu cầu “chỉ cho upload PDF và ảnh” chưa đủ để xác định một luồng upload an toàn.

Trong chương **File và resource security** của module yêu cầu bảo mật, mục tiêu là chuyển tài sản cần bảo vệ và mô hình đe dọa thành các điều kiện cụ thể, đo được, kiểm chứng được. Cần đặc tả cả việc xác thực, phân quyền, dữ liệu, tài nguyên, logging và phục hồi trong vòng đời của tệp.

Ví dụ, một hệ thống có thể kiểm tra phần mở rộng đúng nhưng vẫn gặp những vấn đề sau:

- Tệp chưa được kiểm tra đã có URL tải công khai.
- Bộ phân tích dùng quá nhiều bộ nhớ khi mở một ảnh nhỏ về dung lượng nhưng có kích thước giải mã rất lớn.
- Người dùng tenant A thay định danh để tải tệp của tenant B.
- Nội dung được thay đổi sau khi scanner xác nhận một phiên bản trước đó.
- Một phiên upload bỏ dở giữ dung lượng tạm và quota vô thời hạn.
- Tệp được phục vụ dưới origin ứng dụng với cách hiển thị cho phép nội dung chủ động gây tác động ngoài dự kiến.

Upload cần được đặc tả như một quy trình có trạng thái và ranh giới tin cậy, từ trước khi nhận byte đầu tiên đến khi tệp và các bản sao hết thời hạn lưu.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định rủi ro tại từng bước tiếp nhận, kiểm tra, lưu trữ và phân phối tệp.
2. Viết yêu cầu về loại tệp, kích thước, quyền truy cập và ngân sách xử lý.
3. Phân biệt metadata khai báo với bằng chứng từ nội dung thực tế.
4. Đặc tả cách ly, trạng thái lỗi và liên kết kết quả kiểm tra với phiên bản byte.
5. Xây dựng ma trận truy vết và các tiêu chí nghiệm thu cho luồng upload.

## 2. Phạm vi và mô hình đe dọa

Trước khi chọn scanner hoặc định dạng, cần xác định nhu cầu nghiệp vụ: ai được gửi tệp, gửi vào đối tượng nào, ai được đọc, hệ thống có xử lý nội dung hay chỉ lưu, và cần giữ bao lâu.

| Tài sản hoặc mục tiêu | Kịch bản đe dọa | Yêu cầu cần xem xét |
|---|---|---|
| Dữ liệu của tenant | Đọc hoặc ghi tệp ngoài phạm vi quyền | Phân quyền đối tượng và cách ly lưu trữ, cache, URL |
| Tính toàn vẹn tệp | Ghi đè tệp khác hoặc thay nội dung sau kiểm tra | Định danh do máy chủ cấp, phiên bản bất biến và kiểm tra đồng thời |
| Bộ xử lý nội dung | Tệp khai thác parser hoặc kích hoạt truy cập bên ngoài | Cách ly xử lý, giới hạn tài nguyên và quyền tối thiểu |
| Năng lực phục vụ | Tệp lớn, nhiều phiên bỏ dở, nhiều tác vụ kiểm tra | Giới hạn byte, quota, concurrency và tuổi công việc |
| Người tải xuống | Nội dung chủ động hoặc tệp có hại | Chính sách định dạng, kiểm tra và phân phối phù hợp |
| Bí mật của hệ thống | Log hoặc thông báo lỗi làm lộ đường dẫn, token, nội dung | Tối thiểu hóa dữ liệu và kiểm soát bằng chứng |
| Khả năng điều tra | Không biết ai đưa tệp vào hoặc phiên bản nào đã được tải | Audit liên kết chủ thể, phiên bản, quyết định và hành động |

Các điểm vào cần liệt kê riêng: upload qua backend, upload trực tiếp tới object storage, API mobile, công cụ hỗ trợ, import nội bộ và upload chia phần nếu có. Mọi đường tạo ra tệp được sử dụng bởi sản phẩm phải chịu các bất biến phù hợp.

**Nhập tệp từ URL** là một khả năng khác với nhận byte từ client. Nếu hỗ trợ, phải có yêu cầu riêng cho việc máy chủ truy cập mạng, chuyển hướng, địa chỉ đích, DNS, thời hạn và giới hạn tải. Không tự bật khả năng đó chỉ vì API có một trường tên tệp hoặc đường dẫn.

## 3. Hồ sơ tham chiếu cho một tính năng upload

Xét một cổng quản lý hồ sơ nhiều tenant. Người có quyền sửa hồ sơ được đính kèm tài liệu; người có quyền xem hồ sơ được tải những tệp đã được cho phép sử dụng.

Bộ tham số sau dùng để minh họa cách đặc tả, không phải ngưỡng chuẩn cho mọi ứng dụng:

| Thuộc tính | Chính sách của ví dụ |
|---|---|
| Định dạng | PDF, JPEG, PNG theo chính sách nội dung tương ứng |
| Mã hóa hoặc mật khẩu | Không nhận tệp mà hệ thống không kiểm tra được do mã hóa hoặc mật khẩu |
| Tệp nén | Không hỗ trợ archive trong tính năng này |
| Dung lượng một tệp | Lớn hơn 0 và không vượt 10 MiB byte thực nhận |
| Số tệp trong một đợt đính kèm | Tối đa 5 |
| Tổng byte tệp trong một đợt | Không vượt 25 MiB |
| Kích thước request multipart | Không vượt 26 MiB, bao gồm phần bao của giao thức |
| Tên hiển thị | Tối đa 128 ký tự; từ chối ký tự điều khiển và ký tự phân cách đường dẫn |
| Dung lượng tenant | Tối đa 1 GiB cho dữ liệu tệp thuộc phạm vi tính quota |
| Phiên đang nhận dữ liệu | Tối đa 3 phiên đồng thời mỗi tenant |
| Thời hạn nhận dữ liệu | Tối đa 120 giây cho một phiên của tính năng này |
| Upload chia phần | Chưa hỗ trợ; không có đường ghép tệp bỏ qua giới hạn trên |

Trong bài, `1 MiB = 1.048.576 byte`. Khi triển khai, cần dùng đơn vị nhất quán trong UI, API, cấu hình và kiểm thử. Giới hạn 10 MiB cho tệp không phải là giới hạn 10 MiB cho toàn bộ request multipart.

Quota tenant trong ví dụ phải tính dữ liệu đã nhận còn được giữ: tệp đang cách ly, đang kiểm tra, có thể sử dụng, phiên bản cũ còn lưu và dữ liệu của phiên bỏ dở chưa được dọn. Các bản sao tạm do xử lý cần ngân sách hạ tầng riêng; không giả định quota logic đã chặn mọi mức sử dụng vật lý.

PDF, JPEG và PNG chỉ được tiếp nhận khi vượt qua các kiểm tra tương ứng. Danh sách định dạng được hỗ trợ không phải lời khẳng định rằng mọi tệp có nhãn đó đều an toàn.

## 4. Hợp đồng tiếp nhận: quyền và tài nguyên trước byte tốn kém

### 4.1. Kiểm tra quyền tạo tệp

Máy chủ phải xác định danh tính, tenant, đối tượng đích và quyền đính kèm. Định danh hồ sơ hoặc tenant do client gửi không phải bằng chứng người gửi có quyền.

Cần kiểm tra cả trạng thái nghiệp vụ. Ví dụ, hồ sơ đã khóa hoặc hết quyền sửa có thể không được nhận tệp mới dù người dùng vẫn được xem hồ sơ. Với upload dài hoặc upload trực tiếp, hợp đồng phải quy định quyền được chốt tại thời điểm cấp phiên hay được đánh giá lại khi hoàn tất gắn tệp.

Nếu endpoint dùng thông tin đăng nhập được trình duyệt tự gửi như cookie, cần bảo vệ khỏi việc website khác kích hoạt thao tác trái ý người dùng theo mô hình xác thực của ứng dụng. Việc đã đăng nhập không tự chứng minh request upload xuất phát từ một hành động được phép.

### 4.2. Đo byte thực nhận

Không chỉ dựa vào `Content-Length`, kích thước do SDK khai báo hoặc metadata của object. Luồng nhận cần đếm byte thực và dừng khi vượt giới hạn, kể cả khi không có kích thước khai báo đáng tin cậy.

Các giới hạn cần áp dụng nhất quán ở các tầng liên quan: proxy, backend, dịch vụ lưu trữ và bước hoàn tất upload. Giới hạn ở giao diện chỉ hỗ trợ trải nghiệm; API vẫn phải cưỡng chế phía máy chủ.

Khi vượt giới hạn, hệ thống phải ngừng nhận hoặc lưu theo cơ chế giao thức phù hợp, đánh dấu thất bại, không đưa tệp vào bước phân phối và thu dọn dữ liệu đã nhận theo chính sách. Không tiếp tục đệm toàn bộ tệp vào RAM chỉ để trả thông báo rằng nó quá lớn.

### 4.3. Cấp phát quota có kiểm soát

Hai phiên upload có thể cùng thấy tenant còn đủ quota rồi cùng nhận dữ liệu vượt mức. Yêu cầu cần có cơ chế giữ chỗ hoặc hạch toán nguyên tử phù hợp, bao gồm điều chỉnh theo byte thực tế và giải phóng sau khi dữ liệu không còn được giữ.

Không cho client khai dung lượng rất nhỏ để giữ chỗ rồi gửi nhiều hơn. Nếu có chênh lệch, hệ thống phải bổ sung ngân sách có kiểm soát hoặc dừng phiên trước khi vượt phần được phép.

Quy tắc quota cũng cần xử lý retry. Một upload mới thật sự chiếm dữ liệu phải được tính; một lần gửi lại chỉ tham chiếu cùng thao tác không được làm sai bộ đếm. Chỉ giải phóng quota theo sự kiện xóa hoặc thu dọn được xác nhận trong mô hình đã chọn.

### 4.4. Thời gian và số phiên

Giới hạn byte chưa ngăn được phiên gửi rất chậm hoặc quá nhiều phiên cùng mở. Cần quy định thời hạn toàn phiên, thời gian chờ dữ liệu phù hợp với giao thức, số phiên đồng thời và hành vi khi hết hạn.

Giới hạn phải có phạm vi rõ: theo tài khoản, tenant, instance hay toàn cụm. Ba phiên mỗi tenant trên từng instance không tương đương ba phiên trên toàn hệ thống.

## 5. Loại tệp và metadata: kiểm tra nhiều lớp

### 5.1. Phần mở rộng và MIME chỉ là tín hiệu

Tên tệp và `Content-Type` do client khai báo không chứng minh nội dung thực tế. Magic bytes hoặc chữ ký định dạng có thể hỗ trợ nhận diện, nhưng vài byte đầu đúng cũng không chứng minh cấu trúc hợp lệ hoặc nội dung được phép.

Một chính sách cần xác định:

1. Danh sách định dạng được phép, không chỉ danh sách định dạng bị cấm.
2. Cách nhận diện từ nội dung và bộ parser được dùng để xác minh cấu trúc.
3. Cách xử lý khi phần mở rộng, MIME khai báo và định dạng phát hiện mâu thuẫn.
4. Các tính năng bên trong định dạng được phép hoặc bị từ chối.
5. Hành vi khi công cụ không nhận diện chắc chắn hoặc không phân tích được.

Trong ví dụ, tên có phần mở rộng phải phù hợp với định dạng được hệ thống xác nhận theo bảng ánh xạ đã duyệt. MIME khai báo là dữ liệu cần đối chiếu; một giá trị chung như `application/octet-stream` không được coi là bằng chứng đã xác nhận định dạng.

Tệp có thể được nhiều công cụ hiểu theo các cách khác nhau. Cần tránh để bộ kiểm tra coi dữ liệu là một định dạng nhưng bộ phân phối hoặc trình duyệt lại diễn giải nó theo một định dạng chủ động khác.

### 5.2. Quy định tính năng bên trong tệp

PDF có thể có tính năng vượt nhu cầu đọc tài liệu; ảnh có metadata và chi phí giải mã riêng. Đặc tả phải chọn nội dung nào được phép, ví dụ chính sách đối với script, tệp nhúng, tham chiếu bên ngoài hoặc metadata nhạy cảm.

Không yêu cầu chung “PDF hợp lệ là được phép” nếu sản phẩm không chấp nhận mọi tính năng của PDF. Khi không thể xác minh một thuộc tính bắt buộc, kết quả cần là không được phát hành hoặc chuyển sang xử lý theo chính sách, không tự coi như đã vượt kiểm tra.

Chuyển đổi hoặc tái mã hóa có thể làm giảm một số rủi ro và loại metadata không cần thiết. Tuy nhiên, chính bộ chuyển đổi cũng là bề mặt xử lý đầu vào không tin cậy. Kết quả chuyển đổi là một phiên bản nội dung mới và phải được xác minh theo chính sách đầu ra.

### 5.3. Tên hiển thị khác khóa lưu trữ

Máy chủ nên cấp `file_id` và khóa lưu trữ riêng. Không ghép tên do client gửi thành đường dẫn hoặc cho phép client chọn khóa có thể ghi đè đối tượng khác.

Tên gốc, nếu cần giữ, là metadata có kiểm soát để hiển thị. Cần giới hạn độ dài, xử lý Unicode nhất quán, kiểm soát ký tự đặc biệt và mã hóa đầu ra khi đưa vào HTML hoặc header.

Không dựa vào việc tên khó đoán để thay thế phân quyền. Một `file_id` ngẫu nhiên giúp giảm khả năng đoán nhưng người có định danh vẫn phải được kiểm tra quyền trước các hành động nhạy cảm.

## 6. Cách ly và máy trạng thái của tệp

### 6.1. Nhận thành công chưa phải được phép sử dụng

Một luồng tham khảo:

```text
CREATED → RECEIVING → QUARANTINED → CHECKING → AVAILABLE
              ↓            ↓           ↓
           EXPIRED      REJECTED     REJECTED hoặc CHECK_ERROR

AVAILABLE → DELETING → DELETED
```

Ý nghĩa trạng thái:

| Trạng thái | Ý nghĩa | Quyền sử dụng thông thường |
|---|---|---|
| CREATED | Đã cấp phiên và ngân sách cần thiết | Chưa có tệp được tải xuống |
| RECEIVING | Đang nhận byte; có thể chưa đầy đủ | Không tải xuống hoặc preview |
| QUARANTINED | Có dữ liệu được giữ riêng, chưa đủ bằng chứng kiểm tra | Không phân phối cho người dùng |
| CHECKING | Đang xác minh định dạng, chính sách và nội dung | Không phân phối cho người dùng |
| AVAILABLE | Phiên bản nội dung thỏa các điều kiện phát hành | Tải theo quyền đối tượng hiện hành |
| REJECTED | Không thỏa chính sách đã xác định | Không phân phối; xử lý lưu giữ hoặc xóa theo chính sách |
| CHECK_ERROR | Chưa có kết luận do lỗi kiểm tra hoặc hạ tầng | Không coi là đã vượt kiểm tra |
| EXPIRED | Phiên hoặc công việc hết thời hạn theo hợp đồng | Không được tự hoàn tất để phát hành |
| DELETING | Đã chặn truy cập mới và đang dọn dữ liệu theo chính sách | Không tải qua đường thông thường |
| DELETED | Đã đạt điều kiện xóa được công bố | Không truy cập qua ứng dụng |

Sơ đồ chỉ mô tả luồng chính. Các thao tác hủy, thử lại từ `CHECK_ERROR` và hết hạn ở từng bước cần được định nghĩa khi triển khai. Không cho client tự gửi `state=AVAILABLE` để bỏ qua pipeline.

### 6.2. Cách ly là ranh giới truy cập

Tệp chưa được cho phép sử dụng phải nằm trong vùng mà đường phân phối thông thường không thể đọc hoặc phục vụ. Chỉ ẩn liên kết trên UI chưa đủ nếu object storage, proxy hoặc CDN vẫn trả byte bằng một URL biết trước.

Tài khoản nhận upload chỉ cần quyền tạo đối tượng trong phạm vi được cấp. Bộ kiểm tra chỉ cần đọc phiên bản đang xử lý và ghi kết quả tương ứng. Dịch vụ phân phối chỉ được phục vụ các phiên bản đã phát hành theo quyền.

Nếu nhân sự điều tra cần truy cập tệp cách ly, phải có đường truy cập riêng với quyền, môi trường xử lý và audit phù hợp. Đây không phải quyền mặc định của người gửi hoặc người xem hồ sơ.

### 6.3. Kết quả kiểm tra gắn với đúng byte

Một bản ghi nội dung minh họa:

```json
{
  "fileId": "file-example-42",
  "tenantId": "tenant-example-A",
  "parentRecordId": "record-example-9",
  "artifactVersion": "immutable-version-3",
  "receivedBytes": 5242880,
  "detectedFormat": "PDF",
  "inspectionPolicyVersion": "upload-policy-4",
  "state": "CHECKING"
}
```

Kết quả kiểm tra cần liên kết với định danh, phiên bản, số byte và bằng chứng nội dung theo thiết kế. Digest có thể hỗ trợ liên kết nhưng phải được tính hoặc xác minh từ dữ liệu đáng tin cậy; không lấy digest tự khai làm bằng chứng scanner đã đọc tệp.

Nội dung đã kiểm tra phải không bị thay đổi trước hoặc trong lúc được sử dụng theo hợp đồng. Một lần upload thay thế tạo phiên bản mới và cần kết quả mới. Nếu scanner trả kết quả muộn cho phiên bản cũ, kết quả đó không được nâng trạng thái của phiên bản mới.

## 7. Kiểm tra nội dung và giới hạn bộ xử lý

### 7.1. Kiểm tra theo chính sách, không hứa an toàn tuyệt đối

Pipeline có thể gồm xác minh cấu trúc, kiểm tra tính năng bên trong, quét nội dung có hại và chuyển đổi sang dạng được phép. Cần xác định bước nào bắt buộc cho từng định dạng và điều kiện nào làm tệp bị từ chối.

Một kết quả quét không phát hiện vấn đề chỉ có nghĩa tệp đã vượt kiểm tra với công cụ, phiên bản và chính sách tương ứng. Nó không chứng minh mọi hành vi có hại trong tương lai đều đã được loại bỏ. Vì vậy, vẫn cần phân quyền, cách ly bộ xử lý và chính sách phân phối.

Scanner lỗi, hết thời gian, không đọc được tệp hoặc không có cấu hình hợp lệ không được quy đổi thành kết quả chấp nhận. Phải phân biệt lỗi hạ tầng với kết luận nội dung vi phạm để hỗ trợ vận hành và phản hồi đúng.

### 7.2. Cấp ngân sách cho từng tác vụ

Ví dụ bổ sung cho hồ sơ tham chiếu:

| Tài nguyên xử lý | Giới hạn minh họa |
|---|---|
| Ảnh | Không vượt 25 triệu pixel sau xác định kích thước; giải mã vẫn chịu trần bộ nhớ |
| PDF | Không vượt 100 trang; các thao tác render có ngân sách riêng |
| Một lần kiểm tra đang chạy | Tối đa 30 giây thời gian thực kể từ khi bắt đầu xử lý |
| Bộ nhớ của một worker kiểm tra | Tối đa 256 MiB theo cơ chế cưỡng chế của môi trường |
| Tác vụ kiểm tra chạy đồng thời | Tối đa 4 trên toàn cụm của tính năng |
| Hàng đợi kiểm tra | Tối đa 100 tệp và đồng thời không vượt 512 MiB dữ liệu chờ |
| Retry lỗi kiểm tra tự động | Tối đa 1 lần gửi lại sau lần đầu; vẫn chưa có kết luận thì giữ trạng thái lỗi để xử lý |

Các giới hạn phải được đo ở đúng phạm vi. Nếu 4 worker trên mỗi instance nhưng có nhiều instance, không được báo đó là trần 4 toàn cụm. Một tệp nằm dưới giới hạn byte vẫn có thể bị từ chối nếu vượt ngân sách pixel, trang, thời gian hoặc bộ nhớ.

Cần xác định nơi thực thi deadline và nơi thực sự dừng công việc. Request HTTP hết thời gian không chứng minh parser hoặc job từ xa đã ngừng chiếm tài nguyên. Việc thu hồi slot phải theo vòng đời xử lý thật.

### 7.3. Bộ xử lý là nơi tiếp xúc đầu vào không tin cậy

Worker cần quyền tối thiểu, hạn chế truy cập mạng và chỉ có quyền đọc, ghi những vùng dữ liệu cần thiết. Không để parser tùy ý truy cập dịch vụ nội bộ, thông tin xác thực của ứng dụng hoặc đường dẫn tùy ý do nội dung tệp chỉ ra.

Nếu định dạng có tham chiếu bên ngoài, cần chính sách rõ: từ chối, bỏ qua hoặc chỉ xử lý bằng một cơ chế được kiểm soát. Không mặc nhiên cho phép tải tài nguyên từ mạng trong quá trình tạo preview hoặc phân tích.

Vùng tạm, số tệp phụ, dung lượng đầu ra và tốc độ sinh dữ liệu cũng cần giới hạn. Giới hạn đầu vào 10 MiB không tự giới hạn ảnh đã giải mã, số trang được render hoặc dung lượng các bản chuyển đổi.

### 7.4. Khi pipeline thiếu năng lực

Nếu không có ngân sách cách ly hoặc hàng đợi an toàn, hệ thống cần từ chối phiên mới hoặc áp dụng hợp đồng chờ có giới hạn. Không bỏ qua scanner để tiếp tục công bố tệp.

Việc cấp phiên phải tính các tệp có thể đang nhận và sẽ cần đưa vào pipeline, tránh để hàng loạt upload hoàn tất cùng lúc rồi không còn nơi giữ. Cần xác định cơ chế đặt trước năng lực hoặc hành vi khi công việc không thể chuyển bước.

Người dùng cần thấy trạng thái đang kiểm tra, lỗi hoặc bị từ chối cùng hành động được phép. “Đã nhận dữ liệu” và “tệp có thể sử dụng” phải có ý nghĩa phân biệt trong API và UI.

## 8. Các khả năng mở rộng cần hợp đồng riêng

### 8.1. Nếu hỗ trợ archive

Tính năng tham chiếu từ chối tệp nén. Nếu bổ sung giải nén, cần đánh giá lại rủi ro trước khi mở rộng danh sách định dạng.

Yêu cầu phải bao gồm số entry, tổng byte giải nén thực, kích thước mỗi entry, độ sâu lồng nhau, thời gian, bộ nhớ, dung lượng tạm và hành vi khi vượt giới hạn. Metadata kích thước bên trong archive không phải bằng chứng đủ về dung lượng thực sẽ được sinh ra.

Tên entry, đường dẫn tuyệt đối, tham chiếu ra ngoài vùng đích và các kiểu liên kết đặc biệt phải được xử lý theo chính sách nền tảng. Không ghép tên entry trực tiếp thành đường dẫn ghi. Cần bảo đảm không ghi đè đối tượng ngoài phạm vi hoặc đối tượng của công việc khác.

Archive được chấp nhận về mặt cấu trúc chưa có nghĩa mọi nội dung bên trong được phép phát hành. Cần xác định các entry có được kiểm tra, phân loại và áp dụng chính sách tương ứng hay không.

### 8.2. Nếu hỗ trợ upload trực tiếp tới storage

Quyền upload tạm thời phải bị ràng buộc với đúng tenant, phiên, khóa đối tượng mới, thao tác và thời hạn. Không cấp quyền liệt kê, đọc hoặc ghi đè tùy ý chỉ để giảm tải backend.

Giới hạn kích thước cần được cưỡng chế ở nơi cơ chế upload trực tiếp hỗ trợ và được xác minh lại khi hoàn tất. Nếu storage không cưỡng chế được một thuộc tính bắt buộc, kiến trúc phải có cách bảo vệ khác; không chỉ ghi thuộc tính đó vào metadata do client cung cấp.

API hoàn tất phải kiểm tra quyền và trạng thái phiên theo hợp đồng, đối chiếu object thực với khóa, phiên bản và kích thước được phép, rồi đưa đúng phiên bản vào cách ly. Client nói “upload xong” không phải bằng chứng rằng đúng tệp đã được lưu an toàn.

Thông tin cấp quyền upload phải được bảo vệ khỏi log, chia sẻ ngoài ý muốn và sử dụng lại ngoài phạm vi. Hết hạn phiên trong ứng dụng cũng cần được liên kết với khả năng sử dụng quyền tạm thời ở storage theo bảo đảm thực tế của hệ thống.

### 8.3. Nếu hỗ trợ upload chia phần

Cần giới hạn số phần, tổng byte, số phiên chưa hoàn tất, thời gian lưu phần và dung lượng trong lúc ghép. Mỗi phần và bước ghép phải thuộc cùng một phiên đã được xác minh; không cho ghép phần của tenant hoặc đối tượng khác.

Tệp sau ghép là đối tượng cần được kiểm tra đầy đủ. Việc từng phần nằm dưới giới hạn không chứng minh tệp tổng nằm trong giới hạn hoặc đúng định dạng. Hành vi gửi lại phần, hoàn tất lặp và hủy đồng thời cũng phải có ngữ nghĩa nhất quán.

## 9. Lưu trữ và tải xuống

### 9.1. Lưu riêng, không tự thực thi

Nơi lưu tệp không được tự thực thi nội dung upload như mã ứng dụng. Khóa và đường dẫn nội bộ phải do máy chủ kiểm soát; thao tác tạo không được ghi đè tài nguyên khác ngoài hợp đồng thay thế có quyền.

Dữ liệu cần được bảo vệ khi truyền và khi lưu theo phân loại, bao gồm quản lý quyền sử dụng khóa và thông tin xác thực. Mã hóa không thay thế kiểm tra quyền tải xuống hoặc cách ly tenant.

Nếu có deduplication, việc dùng chung byte bên dưới không được làm chia sẻ quyền, lộ sự tồn tại của tệp tenant khác hoặc cho một người tự nhận quyền sở hữu chỉ vì biết digest.

### 9.2. Phân quyền mỗi đường đọc

Máy chủ phải xác minh người đọc có quyền với hồ sơ và phiên bản tệp được yêu cầu, đồng thời tệp đang ở trạng thái được phân phối. Điều này áp dụng cho download, preview, thumbnail, bản chuyển đổi, truy vấn metadata và export hàng loạt.

Cache và tác vụ tạo báo cáo cũng phải giữ phạm vi quyền. Một URL hoặc cache key chỉ phân biệt `file_id` nhưng thiếu ngữ cảnh cần thiết có thể đưa dữ liệu từ người có quyền sang người không có quyền.

Không cho đường đọc trực tiếp từ storage hoặc CDN bỏ qua chính sách đã cam kết. Nếu sử dụng URL tải tạm thời, cần kiểm tra quyền lúc cấp URL, giới hạn đúng đối tượng và phiên bản, thời hạn và hành vi cache.

URL tạm thời có hiệu lực trong một khoảng không tự đáp ứng thu hồi tức thì sau khi quyền đổi. Nếu yêu cầu thu hồi tức thì đối với lượt tải mới, phải chọn cơ chế phân phối có thể cưỡng chế điều đó. Với mô hình chấp nhận hiệu lực đến khi URL hết hạn, cần công bố cửa sổ và thời điểm kiểm tra. Dữ liệu người dùng đã tải về không tự bị thu hồi bởi việc vô hiệu hóa URL.

### 9.3. Điều khiển cách client diễn giải nội dung

Phản hồi cần có loại nội dung do máy chủ xác định, cách tải xuống hoặc hiển thị được phép và tên hiển thị được mã hóa phù hợp. Không ghép trực tiếp tên gốc vào header hoặc HTML; ký tự đặc biệt phải được xử lý theo ngữ cảnh.

Tệp cần tải như phần đính kèm không nên vô tình được phục vụ như nội dung chủ động trong ngữ cảnh ứng dụng. Nếu cần preview inline, phải đặc tả định dạng, cơ chế cách ly và các quyền được cấp cho nội dung đó.

Một origin phân phối riêng chỉ có ích khi thực sự không mang cookie hoặc credential ứng dụng và không được cấp quyền truy cập origin chính. Không mặc nhiên cho rằng đổi sang một subdomain là đã đạt mọi điều kiện cách ly.

Các kiểm soát kiểu nội dung và chống diễn giải ngoài dự kiến cần đồng nhất ở backend, proxy và CDN. Một header không thay thế việc xác minh định dạng hoặc kiểm soát quyền đọc.

## 10. Lưu giữ, xóa và phục hồi

Cần xác định thời hạn cho dữ liệu bỏ dở, tệp bị từ chối, tệp hợp lệ, bản chuyển đổi, phiên bản cũ và bằng chứng kiểm tra. Lịch giữ không nhất thiết giống nhau nhưng phải có chủ sở hữu và căn cứ nghiệp vụ.

Một chính sách dọn dữ liệu minh họa có thể yêu cầu: dữ liệu của phiên hết hạn và tệp bị từ chối được đưa vào công việc xóa trong tối đa 1 giờ kể từ khi được đánh dấu đủ điều kiện xóa; tiến độ và lỗi xóa phải quan sát được. Nếu cần cam kết thời gian xóa hoàn tất, phải đặc tả thêm thời hạn cùng điều kiện của storage, bản sao và sao lưu.

Khi người có quyền yêu cầu xóa, cần chặn các lượt đọc mới theo mô hình thu hồi đã chọn, cập nhật trạng thái và xử lý dữ liệu vật lý cùng các bản sao liên quan. Không coi việc xóa một hàng metadata là chứng minh mọi byte đã biến mất.

Quota chỉ được giải phóng theo ngữ nghĩa đã công bố, tránh vừa giữ dữ liệu vật lý không giới hạn vừa báo đã trả hết dung lượng. Tác vụ xóa phải có thể chạy lại an toàn và không xóa nhầm phiên bản mới do tên hoặc định danh được tái sử dụng.

Khi phục hồi dữ liệu từ sao lưu, trạng thái quyền, phiên bản và kết quả kiểm tra phải được đối chiếu. Không phục hồi một blob riêng lẻ rồi tự đánh dấu nó `AVAILABLE` nếu bằng chứng hoặc chính sách tương ứng không còn hợp lệ. Cần kiểm tra lại khi hợp đồng yêu cầu.

## 11. Logging, audit và chỉ số vận hành

### 11.1. Theo dõi quyết định theo phiên bản tệp

Các sự kiện có ý nghĩa gồm cấp phiên, bắt đầu và kết thúc nhận dữ liệu, từ chối do quyền hoặc giới hạn, kết quả kiểm tra, chuyển trạng thái phát hành, tải xuống nhạy cảm, thay quyền và xóa.

Bằng chứng cần liên kết được danh tính, tenant, hồ sơ, `file_id`, phiên upload, phiên bản nội dung, số byte thực nhận, định dạng phát hiện, chính sách kiểm tra, kết quả và mã lý do. Với bộ xử lý ngoài tiến trình, cần mã công việc và liên kết lần thử để điều tra lỗi hoặc kết quả đến muộn.

Tên gốc và metadata có thể chứa thông tin nhạy cảm hoặc dữ liệu do bên ngoài điều khiển. Cần giới hạn dữ liệu được ghi, mã hóa hiển thị phù hợp và không ghi URL tạm thời, token hoặc toàn bộ nội dung tệp vào log.

Thao tác sửa chính sách, cấp ngoại lệ, xem tệp cách ly, phát hành thủ công nếu được phép và can thiệp xóa cần audit theo quyền riêng. Một ngoại lệ không được tự chuyển mọi tệp đang lỗi thành `AVAILABLE` mà thiếu quyết định có căn cứ và phạm vi.

### 11.2. Đo chất lượng và năng lực pipeline

Các chỉ số hữu ích gồm:

- Số phiên nhận, byte thực nhận và số phiên bỏ dở theo phạm vi được phép.
- Số tệp bị từ chối theo lý do: quyền, byte, định dạng, tính năng hoặc kết quả nội dung.
- Số tệp và byte đang cách ly, đang chờ, đang kiểm tra và đang ở trạng thái lỗi.
- Tuổi hàng đợi, thời gian kiểm tra, số timeout và số lần thử lại.
- Mức sử dụng quota, dung lượng tạm và dung lượng chờ xóa.
- Số kết quả không khớp phiên bản, lỗi phân quyền download và sai lệch đối soát storage.

Mỗi chỉ số cần đơn vị, phạm vi và cửa sổ thời gian rõ ràng. Không lấy thời gian kiểm tra của riêng những tệp hoàn tất để kết luận mọi tệp được xử lý nhanh, trong khi nhiều tệp khác đang treo.

Đường từ chối và ghi log phải có ngân sách để không trở thành điểm cạn tài nguyên mới. Có thể dùng bộ đếm đầy đủ kết hợp log lấy mẫu cho sự kiện khối lượng lớn, nhưng cần công bố việc lấy mẫu và vẫn giữ bằng chứng bắt buộc cho các hành động nhạy cảm.

## 12. Bộ yêu cầu bảo mật minh họa

Các yêu cầu dưới đây áp dụng cho hồ sơ tham chiếu của bài. Khi triển khai, chủ yêu cầu cần chốt thêm chính sách nội dung chi tiết, quyền, lưu giữ, phân phối và hành vi thu hồi của sản phẩm.

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
|---|---|---|
| FU-01 | Cấp phiên, hoàn tất gắn tệp và mọi đường đọc phải kiểm tra danh tính, tenant, quyền đối tượng và trạng thái theo hợp đồng | Kiểm thử người không có quyền, hồ sơ khóa, tenant khác và liên kết trực tiếp |
| FU-02 | Cưỡng chế byte thực: mỗi tệp tối đa 10 MiB, mỗi đợt tối đa 5 tệp và 25 MiB dữ liệu tệp, request multipart tối đa 26 MiB | Dữ liệu ở biên, vượt biên và kích thước khai báo không đủ làm bằng chứng |
| FU-03 | Tối đa 3 phiên đang nhận mỗi tenant trong phạm vi toàn hệ thống của tính năng; phiên không kéo dài quá 120 giây; quota 1 GiB được hạch toán cả dữ liệu còn giữ của các trạng thái đã định | Upload đồng thời sát quota, phiên chậm, bỏ dở và thu dọn |
| FU-04 | Chỉ nhận PDF, JPEG, PNG được xác minh cấu trúc và chính sách; trong ví dụ, PDF có script, tệp nhúng hoặc mã hóa không được chấp nhận; archive không được hỗ trợ | Mâu thuẫn tên, MIME, định dạng và tính năng bên trong |
| FU-05 | Khóa lưu trữ phải do máy chủ cấp, không cho tên client chọn đường dẫn hoặc ghi đè; tên hiển thị tuân giới hạn 128 ký tự và quy tắc ký tự đã nêu | Tên trùng, ký tự đặc biệt, tên vượt giới hạn và thao tác thay thế trái quyền |
| FU-06 | Tệp chưa `AVAILABLE` không được đọc qua đường phân phối thông thường, kể cả khi client biết định danh hoặc địa chỉ storage | Truy cập khi đang nhận, cách ly, kiểm tra và lỗi |
| FU-07 | Kết quả kiểm tra và phát hành phải gắn với đúng phiên bản nội dung; thay byte hoặc phiên bản phải có kiểm tra tương ứng | Thay nội dung giữa kiểm tra và phát hành, callback cũ |
| FU-08 | Cưỡng chế ngân sách xử lý tham chiếu: 25 triệu pixel, 100 trang PDF, 30 giây mỗi lần kiểm tra, 256 MiB mỗi worker, 4 tác vụ toàn cụm, queue tối đa 100 tệp và 512 MiB | Tệp khuếch đại tài nguyên, lỗi worker và tải burst |
| FU-09 | Lỗi kiểm tra không tạo kết quả chấp nhận; chỉ tối đa 1 retry tự động sau lần đầu; mọi lần xử lý vẫn chịu ngân sách và trạng thái | Scanner mất kết nối, timeout, parser lỗi và kết quả đến muộn |
| FU-10 | Download và preview phải dùng kiểu nội dung, cách hiển thị, metadata và phạm vi cache do máy chủ kiểm soát; URL tạm thời nếu có phải theo mô hình hiệu lực được công bố | Đối chiếu response, cache, quyền và hành vi sau thu hồi |
| FU-11 | Quyết định và chuyển trạng thái quan trọng phải có bằng chứng liên kết phiên bản; log không chứa credential hoặc nội dung tệp ngoài chính sách | Đối chiếu audit, quyền đọc và kiểm tra dữ liệu nhạy cảm |
| FU-12 | Dữ liệu hết hạn hoặc bị từ chối đủ điều kiện xóa phải được đưa vào tác vụ xóa trong tối đa 1 giờ; lỗi, bản sao liên quan và giải phóng quota phải được theo dõi theo hợp đồng | Hủy phiên, xóa chạy lại, lỗi storage và phục hồi sao lưu |

Đối với FU-08, trần dung lượng tạm và đầu ra cần được cấu hình riêng trước nghiệm thu; không lấy giới hạn queue làm trần dung lượng mọi bước. Đối với FU-10, phải chọn rõ mô hình thu hồi và cấu hình cache, thay vì chỉ ghi “URL an toàn”.

Các giới hạn tham chiếu là ví dụ giúp yêu cầu đo được. Một sản phẩm phục vụ video, dữ liệu khoa học hoặc hồ sơ lớn cần tham số khác và đánh giá lại mô hình đe dọa, không chỉ tăng dung lượng rồi giữ nguyên mọi giả định.

## 13. Tiêu chí nghiệm thu

### 13.1. Phân quyền xuyên suốt và cách ly tenant

```gherkin
Given người dùng U có quyền đính kèm và xem hồ sơ của tenant A
And U không có quyền với hồ sơ của tenant B
When U yêu cầu cấp phiên hoặc gắn tệp vào hồ sơ của B
Then thao tác bị từ chối theo hợp đồng quyền
And không có tệp được gắn vào hồ sơ của B

When U yêu cầu download, preview hoặc metadata nhạy cảm của tệp B
Then không có dữ liệu ngoài phạm vi được trả về
And cache hoặc liên kết trực tiếp không vượt qua kiểm tra quyền
```

Thêm biến thể quyền bị thu hồi trong lúc upload, hồ sơ đổi trạng thái trước hoàn tất và file đã chuyển sang `DELETING`. Kết quả phải tuân ngữ nghĩa quyền và thu hồi đã chọn, không phụ thuộc việc UI còn hiển thị nút hay không.

### 13.2. Kiểm tra byte, số lượng và quota

Tạo fixture hợp lệ về định dạng, giữ các điều kiện khác đủ ngân sách và kiểm tra:

- Tệp đúng 10 MiB có thể vượt điều kiện kích thước; tệp lớn hơn một byte phải bị từ chối vì giới hạn đó.
- Tệp rỗng bị từ chối theo chính sách.
- Năm tệp có tổng 25 MiB thỏa điều kiện đợt; tệp thứ sáu hoặc tổng vượt 25 MiB không được tiếp nhận như một đợt hợp lệ.
- Request vượt 26 MiB bị xử lý theo giới hạn request, bao gồm phần bao của giao thức.
- Không có kích thước khai báo đáng tin cậy vẫn không cho phép nhận byte vô hạn.

Cho hai phiên cùng cạnh tranh phần quota chỉ đủ cho một tệp. Đối chiếu byte đã giữ, ngân sách đặt trước và dữ liệu thực trong storage để chứng minh không vượt cam kết do kiểm tra rồi cập nhật tách rời.

Với giới hạn 3 phiên toàn hệ thống của một tenant, thực hiện qua nhiều instance. Phiên thứ tư không được bắt đầu chiếm slot trái chính sách; sau khi một phiên kết thúc hoặc bị hủy thực sự, việc sử dụng lại slot phải nhất quán.

### 13.3. Đối chiếu loại tệp và chính sách nội dung

Kiểm thử tên và MIME cho một định dạng nhưng byte thuộc định dạng khác, cấu trúc hỏng, phần mở rộng kép và nội dung không được hỗ trợ. Đối chiếu mã lý do và trạng thái cuối với chính sách.

Với PDF, kiểm tra các tính năng bị cấm trong ví dụ và tệp không thể đọc do mã hóa. Với ảnh, kiểm tra kích thước pixel và lỗi giải mã. Một ảnh dưới 10 MiB nhưng vượt 25 triệu pixel không được vượt kiểm tra chỉ vì đã qua giới hạn byte.

Các fixture kiểm thử nên vô hại và có thuộc tính được kiểm soát. Khi kiểm tra scanner, có thể dùng thành phần thử nghiệm trả kết luận xác định để kiểm chứng luồng trạng thái mà không cần đưa mã độc thật vào môi trường thông thường.

### 13.4. Không truy cập trước kiểm tra và khi scanner lỗi

```gherkin
Given tệp đã được nhận vào QUARANTINED
And scanner chưa có kết quả hợp lệ
When người gửi thử download hoặc mở preview
Then đường phân phối không trả nội dung tệp

When scanner lỗi hoặc quá 30 giây xử lý
Then tệp không chuyển thành AVAILABLE
And retry tuân giới hạn đã định
And người dùng thấy trạng thái chưa có kết luận hoặc lỗi theo hợp đồng
```

Kiểm tra cả API, storage, CDN và các bản chuyển đổi. Một thumbnail được tạo sớm không được trở thành đường đọc nội dung cách ly ngoài chính sách.

### 13.5. Kết quả cũ không phát hành phiên bản mới

Cho scanner kiểm tra phiên bản V1 rồi tạm dừng trước khi trả kết quả. Tạo hoặc trỏ sang phiên bản V2 theo luồng thay thế có quyền. Khi kết quả của V1 đến, nó chỉ được áp dụng cho đúng phiên bản đó.

V2 không được thành `AVAILABLE` nhờ kết quả của V1. Thử gửi lặp kết quả và hoàn tất upload nhiều lần để xác minh không tạo bản ghi, công việc hoặc quyền truy cập bổ sung ngoài hợp đồng.

### 13.6. Cạn tài nguyên và công việc bỏ dở

Thử tệp có cấu trúc gây xử lý lâu trong môi trường kiểm soát, vượt trang hoặc vượt ngân sách bộ nhớ. Xác minh worker được dừng hoặc cô lập đúng cách, slot không được trả trong khi công việc thật vẫn chạy và dịch vụ khác không bị kéo vào cùng sự cố.

Làm đầy queue theo số tệp và theo byte riêng biệt. Khi một trong hai trần đã chạm, hệ thống không vượt ngân sách và không bỏ kiểm tra để giải phóng hàng đợi. Theo dõi cả các upload đang nhận có thể sắp tạo thêm công việc.

Ngắt kết nối giữa chừng, chờ quá hạn phiên và kiểm tra việc đánh dấu dữ liệu để dọn. Đối chiếu lịch đưa vào tác vụ xóa, lỗi xóa và quota thay vì chỉ nhìn số phiên đã biến mất khỏi UI.

### 13.7. Phân phối, xóa và phục hồi

Đối chiếu kiểu nội dung và tên hiển thị với dữ liệu máy chủ đã xác minh. Kiểm tra metadata có ký tự đặc biệt không làm thay đổi header hoặc cấu trúc trang. Với preview inline, kiểm tra cơ chế cách ly và quyền của origin phân phối theo thiết kế.

Nếu dùng URL tạm thời, kiểm thử cấp URL khi không có quyền, truy cập sau thời hạn và sau thu hồi theo hợp đồng đã chọn. Kiểm tra cache không tiếp tục phục vụ ngoài cửa sổ cho phép.

Xóa một phiên bản trong khi có phiên bản khác cùng file và chạy lại tác vụ dọn. Phiên bản không thuộc phạm vi xóa phải được giữ nguyên. Khi phục hồi từ sao lưu, tệp bị từ chối hoặc thiếu bằng chứng không được tự quay lại trạng thái có thể tải.

## 14. Truy vết tới kiến trúc và vòng đời phát triển

| Rủi ro | Yêu cầu liên quan | Điểm thực thi | Kiểm chứng chính |
|---|---|---|---|
| Gửi hoặc đọc dữ liệu tenant khác | FU-01, FU-10 | Nguồn danh tính, API, storage và cache | Request trái quyền qua mọi đường đọc, ghi |
| Làm cạn byte, phiên hoặc pipeline | FU-02, FU-03, FU-08 | Tầng nhận, quota và worker | Biên kích thước, tải đồng thời và dữ liệu khuếch đại |
| Ghi đè hoặc chọn đường dẫn tùy ý | FU-05 | Cấp định danh và thao tác lưu trữ | Tên không tin cậy và tranh chấp tạo đối tượng |
| Phát hành tệp chưa được kiểm tra | FU-06, FU-09 | Máy trạng thái và ranh giới phân phối | Scanner chậm, lỗi và truy cập trực tiếp |
| Đổi byte sau kiểm tra | FU-07 | Lưu trữ phiên bản, kết quả và bước phát hành | Kết quả cũ, thay phiên bản và công việc lặp |
| Mất kiểm soát dữ liệu sau xóa hoặc phục hồi | FU-11, FU-12 | Audit, tác vụ dọn và sao lưu | Đối soát dữ liệu, quyền và quota |

Ở bước phân tích, xác định ai có nhu cầu upload, loại dữ liệu, người đọc và hậu quả nếu tệp bị lộ, thay đổi hoặc làm cạn tài nguyên. Chốt các khả năng được hỗ trợ, đặc biệt archive, URL import và upload trực tiếp.

Ở bước thiết kế, xác định máy trạng thái, ranh giới cách ly, định danh và phiên bản, chính sách nội dung, ngân sách và quyền từng thành phần. Việc chọn scanner hoặc storage phải đáp ứng yêu cầu này thay vì thay thế chúng.

Ở bước triển khai và nghiệm thu, liên kết mã yêu cầu với cấu hình và bài kiểm thử. Đo tại nơi thực sự nhận byte, thực thi công việc và phục vụ dữ liệu; không chỉ dựa vào trạng thái do giao diện báo.

Ở bước vận hành, theo dõi pipeline, tuổi dữ liệu cách ly, lỗi kiểm tra, quota, truy cập và xóa. Khi đổi thư viện xử lý, chính sách kiểm tra, nguồn lưu trữ hoặc origin phân phối, đánh giá lại các bảo đảm có liên quan và việc sử dụng kết quả kiểm tra cũ.

## 15. Những lỗi đặc tả thường gặp

| Cách đặc tả dễ gây lỗi | Khoảng hở | Cách làm rõ |
|---|---|---|
| “Chỉ nhận đuôi PDF và JPG” | Tên không chứng minh nội dung | Xác minh cấu trúc, chính sách bên trong và cách phân phối |
| “Client đã kiểm tra 10 MB” | API hoặc upload trực tiếp có thể bỏ qua | Cưỡng chế byte thực nhận, đơn vị và giới hạn từng tầng |
| “Upload xong là có URL” | Tệp cách ly đã bị phân phối | Phân biệt nhận dữ liệu với trạng thái phát hành |
| “Scanner không trả lỗi nên tệp sạch” | Không có kết luận không đồng nghĩa vượt kiểm tra | Đặc tả verdict, lỗi, timeout và trạng thái mặc định |
| “Giới hạn byte là đủ” | Giải mã, render và dữ liệu đầu ra có thể lớn | Giới hạn pixel, trang, thời gian, bộ nhớ và dung lượng tạm |
| “Tên ngẫu nhiên nên không cần quyền” | Định danh bị lộ vẫn có thể đọc | Kiểm tra quyền đối tượng và tenant trên mọi đường |
| “Dùng subdomain là đã cách ly” | Cookie hoặc quyền truy cập chéo vẫn có thể tồn tại | Chốt origin, credential và quyền của nội dung |
| “Xóa metadata là trả hết quota” | Byte, phiên bản và bản sao vẫn còn | Định nghĩa điều kiện xóa và đối soát dung lượng |
| “Tệp đã quét rồi thì thay byte được” | Kết quả không còn gắn với nội dung sử dụng | Phiên bản bất biến và kết quả theo phiên bản |
| “Lỗi scanner thì tạm cho tải để không gián đoạn” | Tính sẵn sàng bị đổi lấy việc bỏ kiểm soát chưa được phê duyệt | Giữ cách ly, áp dụng chờ hoặc từ chối có giới hạn |

## 16. Bài tập tự kiểm tra

Một ứng dụng cho phép người dùng gửi tệp có đuôi `.pdf`, lấy tên gốc làm khóa lưu trữ và trả URL ngay khi nhận xong. UI giới hạn 10 MB nhưng backend chỉ tin `Content-Length`. Scanner chạy bất đồng bộ; nếu quá 30 giây không có kết quả, hệ thống tự đánh dấu tệp được dùng. Người có `file_id` tải được tệp qua storage. Phiên upload bỏ dở không có tác vụ dọn.

Hãy thực hiện các việc sau:

1. Liệt kê rủi ro đối với bí mật, toàn vẹn và tính sẵn sàng tại từng bước.
2. Viết yêu cầu cho quyền cấp phiên, hoàn tất và tải xuống.
3. Định nghĩa loại tệp, giới hạn byte, số phiên, quota và ngân sách xử lý.
4. Thiết kế máy trạng thái cùng ranh giới cách ly và điều kiện phát hành.
5. Quy định cách liên kết kết quả kiểm tra với đúng phiên bản nội dung.
6. Viết bài kiểm thử cho scanner lỗi, tenant khác và upload đồng thời sát quota.
7. Đặc tả dọn dữ liệu bỏ dở, xóa, audit và phục hồi.

Một lời giải đầy đủ cần chứng minh tệp đúng quyền, đúng phiên bản và đúng chính sách ở cả nơi nhận, nơi xử lý lẫn nơi phân phối. Yêu cầu upload có thể kiểm chứng khi mỗi trạng thái đều có điều kiện vào, quyền truy cập, ngân sách tài nguyên và bằng chứng cho phép chuyển sang bước tiếp theo.
