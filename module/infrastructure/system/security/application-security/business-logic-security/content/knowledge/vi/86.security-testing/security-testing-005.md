# Replay attack test — Kiểm thử tấn công phát lại yêu cầu

## 1. Mục tiêu và phạm vi

Một yêu cầu từng hợp lệ không nhất thiết được phép tạo hiệu lực nhiều lần. Nếu hệ thống nhận lại yêu cầu thu tiền, hoàn tiền, sử dụng ưu đãi hoặc xác nhận phê duyệt mà tiếp tục thực hiện như một thao tác mới, người gọi có thể lợi dụng bản sao của yêu cầu cũ để phá quy tắc nghiệp vụ.

**Replay attack test** là kiểm thử việc phát lại yêu cầu, thông điệp hoặc bằng chứng ủy quyền đã tồn tại, nhằm xác định hệ thống có ngăn hiệu lực không được phép hay không. Điểm cần quan sát là tác động nghiệp vụ và quyền truy cập, không chỉ việc server nhận ra hai request giống nhau.

Bài học thuộc module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`, tập trung vào business invariants, state machine, quyền theo đối tượng, transaction và idempotency. Các tình huống dùng tài khoản, dữ liệu, khóa ký và dịch vụ giả lập trong môi trường kiểm thử được kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt replay attack với retry hợp lệ, yêu cầu trùng và thao tác mới.
- Chuyển quy tắc nghiệp vụ thành kỳ vọng kiểm thử phát lại.
- Kiểm tra idempotency, nonce, timestamp và chữ ký mà không coi một lớp bảo vệ là đủ cho mọi tình huống.
- Phát lại sau thay đổi quyền, trạng thái, revision hoặc sau khi tiến trình bị gián đoạn.
- Kiểm chứng hiệu lực đã commit và hiệu lực ngoài hệ thống, đồng thời bảo vệ dữ liệu trong bộ test.

## 2. Phân biệt các tình huống dễ bị gọi chung là replay

| Tình huống | Đặc điểm | Kỳ vọng cần làm rõ |
| --- | --- | --- |
| Retry hợp lệ | Client chưa nhận kết quả và gửi lại cùng ý định | Theo dõi hoặc trả kết quả cũ, không cộng thêm hiệu lực |
| Giao thông điệp lặp | Hệ thống giao lại cùng sự kiện | Consumer không áp dụng lại hiệu lực đã ghi nhận |
| Replay độc hại | Người gọi cố dùng lại yêu cầu hoặc bằng chứng để có thêm lợi ích | Không tạo hiệu lực ngoài chính sách, không mở thêm quyền |
| Yêu cầu mới giống nội dung | Người dùng thật sự muốn thực hiện lần thứ hai | Được xử lý nếu nghiệp vụ cho phép và điều kiện hiện tại đáp ứng |
| Biến đổi yêu cầu cũ | Đổi khóa, ID, số tiền, đối tượng hoặc metadata | Không dùng biến đổi để vượt ràng buộc hoặc đổi nội dung đã xác nhận |

Một lần chuyển tiền mới có cùng số tiền và người nhận có thể hoàn toàn hợp lệ. Ngược lại, đổi khóa idempotency không biến việc thực hiện lại cùng một yêu cầu hoàn tiền đã được duyệt thành một quyền hoàn tiền mới.

Hệ thống cũng không cần luôn trả lỗi cho bản phát lại. Một webhook đã xử lý có thể được xác nhận lại thành công để bên gửi dừng retry, miễn không tạo thêm hiệu lực. Khi đó phản hồi thành công lần hai là hành vi đúng, còn khoản hoàn tiền thứ hai mới là dấu hiệu vi phạm.

## 3. Những điều chữ ký, token và kết nối an toàn không tự bảo đảm

Chữ ký hợp lệ có thể chứng minh nội dung đến từ bên nắm khóa phù hợp và không bị sửa ngoài phạm vi cho phép. Một bản sao nguyên vẹn vẫn có thể giữ chữ ký hợp lệ. Vì vậy, kiểm tra chữ ký không tự chứng minh yêu cầu mới, chưa dùng hoặc còn phù hợp với trạng thái nghiệp vụ hiện tại.

Tương tự:

- Kết nối được bảo vệ không ngăn một client có quyền gửi lại chính yêu cầu của mình.
- Access token còn hiệu lực thường có thể dùng cho nhiều request; không mặc định nó là bằng chứng dùng một lần.
- Một mã định danh trong token chỉ chống phát lại nếu hợp đồng và phía nhận thật sự áp dụng quy tắc tương ứng.
- Cơ chế chống yêu cầu giả mạo từ trình duyệt không thay thế kiểm soát giao dịch trùng.
- Timestamp nằm trong cửa sổ chấp nhận không chứng minh thông điệp chưa từng được xử lý trong cửa sổ đó.
- Khóa idempotency không cấp quyền xem kết quả và không thay thế kiểm tra theo đối tượng.

Kiểm thử cần chỉ ra lớp nào bảo vệ điều gì: tính toàn vẹn, nguồn gửi, độ mới, sử dụng một lần, quyền hành động hay số hiệu lực nghiệp vụ. Một test chữ ký sai bị chặn chưa chứng minh bản phát lại có chữ ký đúng cũng an toàn.

## 4. Bắt đầu từ bất biến và danh tính nghiệp vụ

### 4.1. Viết điều kiện cần bảo vệ

Ví dụ trong hệ thống mua hàng và thanh toán:

1. Mỗi yêu cầu hoàn tiền được duyệt chỉ tạo tối đa một khoản hoàn tương ứng.
2. Tổng hoàn có hiệu lực không vượt số tiền còn được phép hoàn theo chính sách.
3. Một hồ sơ chỉ được đặt hàng theo revision đáp ứng điều kiện phê duyệt.
4. Bằng chứng xác nhận dùng một lần không được dùng cho đối tượng, chủ thể hoặc hành động khác.
5. Phát lại kết quả chỉ công bố dữ liệu cho người có quyền xem tại thời điểm truy cập theo chính sách.
6. Yêu cầu quá hạn hoặc có nội dung bị thay đổi không tạo hiệu lực trái hợp đồng.

Không áp dụng bất biến quá rộng. Một giao dịch có thể được hoàn nhiều đợt hợp lệ; điều cần chặn là hoàn lặp cùng một yêu cầu hoặc hoàn quá phần còn được phép, không nhất thiết là mọi lần hoàn thứ hai.

### 4.2. Phân biệt các định danh

| Định danh | Vai trò minh họa | Nguy cơ nếu dùng sai |
| --- | --- | --- |
| Request ID | Theo dõi một lần gọi kỹ thuật | Đổi request ID làm hệ thống tưởng hiệu lực cũ là thao tác mới |
| Idempotency key | Nhận diện một lần thao tác trong phạm vi đã định | Đổi khóa để thực hiện lại cùng quyền nghiệp vụ |
| Event ID | Nhận diện một sự kiện từ nguồn đã xác minh | Chỉ khử trùng trong một instance hoặc một endpoint |
| Business operation ID | Nhận diện yêu cầu hoàn, kỳ thu hoặc quyền sử dụng cụ thể | Thiếu ràng buộc nên nhiều đường vào tạo nhiều hiệu lực cho cùng quyền |
| Nonce | Giá trị dùng theo quy tắc về độ mới hoặc dùng một lần | Không ràng buộc mục đích hoặc không tiêu thụ nguyên tử |

Các định danh cần được đặt trong phạm vi phù hợp: tổ chức, nguồn sự kiện, loại thao tác hoặc không gian người gọi theo hợp đồng. Cùng một chuỗi ký tự không nhất thiết là cùng một thao tác ở mọi phạm vi; ngược lại, các request ID khác nhau vẫn có thể trỏ tới một hiệu lực nghiệp vụ duy nhất.

## 5. Chuẩn bị kịch bản và mẫu yêu cầu phát lại

### 5.1. Fixture có trường hợp hợp lệ đối chứng

Chuẩn bị một giao dịch đã thu `1000000 VND`, một yêu cầu hoàn `RF-1` được duyệt cho `300000 VND`, và một người gọi có quyền thực hiện yêu cầu đó. Không có phí hoặc giao dịch khác trong ví dụ.

Lần thực hiện hợp lệ phải tạo đúng một khoản hoàn `300000 VND`, còn phần có thể hoàn là `700000 VND`. Bản phát lại của cùng yêu cầu không được làm các giá trị này thay đổi thêm.

Đối chứng này quan trọng: nếu lần đầu cũng bị chặn vì fixture sai quyền hoặc sai trạng thái, lần phát lại bị chặn không chứng minh cơ chế chống replay đang hoạt động.

### 5.2. Lưu đủ thành phần để biết đang thử điều gì

Một mẫu yêu cầu kiểm thử có thể gồm:

```yaml
scenario: refund-request-replay
actor: Người có quyền thực hiện RF-1 trong tổ chức A
resource: Giao dịch đã thu 1000000 VND
businessOperationId: RF-1
approvedAmount: 300000
currency: VND
idempotencyKey: key-for-RF-1
replayMode: Gửi lại cùng lệnh sau khi lần đầu hoàn tất
expected:
  effectiveRefundCountForRF1: 1
  refundedTotal: 300000
  refundableRemaining: 700000
```

Đây là mẫu mô tả trong bài học, không yêu cầu tạo thêm tệp. Khi có chữ ký, lưu chính xác phần dữ liệu được ký theo hợp đồng kiểm thử. Nếu chữ ký áp dụng trên byte của body, việc parse rồi ghi JSON lại có thể thay đổi byte và biến test phát lại thành test chữ ký sai.

Dùng dữ liệu tổng hợp và thông tin xác thực riêng cho test. Không sao chép token production hoặc đưa khóa ký, cookie và payload riêng tư vào báo cáo. Mẫu tái hiện cần có thời hạn lưu và kiểm soát truy cập phù hợp.

## 6. Kiểm thử phát lại nguyên bản

Bắt đầu bằng bản phát lại không thay đổi ý nghĩa yêu cầu. Có thể đổi metadata theo dõi nếu hợp đồng xác định nó không tham gia danh tính hoặc chữ ký, nhưng phải biết rõ điều đó.

```text
given:
  RF-1 đã được duyệt cho 300000 VND
  người gọi có quyền, giao dịch còn đủ phần được hoàn
  K là khóa của lần thực hiện RF-1

when:
  gửi yêu cầu executeRefund(RF-1, K)
  chờ kết quả cuối cùng và xác nhận thành công
  ghi snapshot dữ liệu đã commit
  gửi lại cùng yêu cầu một hoặc nhiều lần
  chờ các thao tác liên quan kết thúc theo hợp đồng

then:
  RF-1 vẫn có đúng một khoản hoàn có hiệu lực
  tổng hoàn của giao dịch vẫn là 300000 VND
  phần còn được hoàn vẫn là 700000 VND
  kết quả được công bố tuân thủ hợp đồng phát lại và quyền truy cập
  không có hiệu lực ngoài hệ thống bị cộng lặp
```

Không bắt buộc mọi lần gọi trả cùng mã HTTP hoặc cùng body từng byte. Lần đầu có thể đang xử lý, lần sau hoàn tất; mã theo dõi request có thể khác. Các giá trị thuộc kết quả nghiệp vụ đã hoàn tất, chẳng hạn định danh khoản hoàn, số tiền và tiền tệ, phải phản ánh đúng hiệu lực cũ.

Kiểm tra log hoặc bộ đếm số lần thử tăng là hợp lệ nếu đó là hành vi được thiết kế. Thuộc tính cần bảo vệ không phải “không có bất cứ bản ghi mới nào”, mà là không có thêm hiệu lực nghiệp vụ trái chính sách.

## 7. Ma trận biến thể để tránh chỉ kiểm tra một đường phát lại

| Biến thể | Cách thử trong môi trường kiểm thử | Kỳ vọng cốt lõi |
| --- | --- | --- |
| Bản sao nguyên vẹn | Gửi lại cùng nội dung và định danh | Không tạo thêm hiệu lực |
| Đổi request ID | Giữ nguyên ý định, đổi mã theo dõi kỹ thuật | Không coi đó là quyền thực hiện mới |
| Đổi idempotency key | Giữ cùng business operation ID đã dùng | Ràng buộc nghiệp vụ vẫn ngăn thực hiện lại nếu chính sách chỉ cho một lần |
| Cùng khóa, đổi số tiền | Khóa đã gắn với lệnh cũ, payload có ý nghĩa khác | Không thay nội dung đã ràng buộc, không thực hiện phần sửa |
| Đổi đối tượng hoặc tổ chức | Thay ID ở path, body hoặc dữ liệu lồng nhau | Không vượt phạm vi quyền hoặc dùng bằng chứng sai đối tượng |
| Phát lại qua endpoint khác | Dùng đường tích hợp hoặc chức năng khác cùng tạo hiệu lực | Các đường vào giữ cùng quy tắc nghiệp vụ |
| Phát lại sau restart | Xóa trạng thái bộ nhớ bằng khởi động lại thành phần test | Bằng chứng đã xử lý cần thiết vẫn tồn tại bền vững |
| Phát lại ở instance khác | Gửi các bản sao tới các instance trong môi trường test | Không phụ thuộc tập chống trùng cục bộ của một instance |
| Sự kiện mới về cùng giao dịch | Dùng định danh sự kiện khác nhưng cùng hiệu lực nghiệp vụ | Xử lý theo quy tắc nguồn và đối tượng, không cộng tiền sai |

Với mỗi biến thể, giữ các tiền điều kiện khác đủ tương đồng. Nếu đổi ID sang một đối tượng không tồn tại, kết quả từ chối chưa chứng minh hệ thống bảo vệ một đối tượng tồn tại ngoài phạm vi.

Cùng khóa nhưng khác nội dung chỉ có kỳ vọng xung đột khi khóa đã được ràng buộc theo hợp đồng. Một yêu cầu lỗi định dạng bị từ chối trước bước đăng ký có thể chưa chiếm khóa; cần nêu rõ trạng thái đó trong test.

## 8. Kiểm thử nonce, timestamp và chữ ký

### 8.1. Nonce chỉ có tác dụng khi được áp dụng đúng hợp đồng

Nếu một bằng chứng xác nhận được quy định dùng một lần, kiểm thử lần sử dụng đầu hợp lệ rồi phát lại cùng nonce. Phải quan sát hiệu lực thực tế, kể cả khi hai lần gửi đồng thời.

Các thuộc tính quan trọng:

- Nonce được ràng buộc với mục đích, chủ thể hoặc phạm vi và đối tượng cần thiết theo thiết kế.
- Đổi số tiền, revision hay người nhận không tái sử dụng được bằng chứng cũ cho nội dung mới.
- Việc chiếm hoặc tiêu thụ nonce chịu được cạnh tranh giữa các instance.
- Trạng thái đã dùng không mất chỉ vì tiến trình khởi động lại.
- Yêu cầu chưa được xác thực hợp lệ không thể tùy tiện tiêu thụ nonce của thao tác thật để chặn người dùng hợp lệ.

Không mặc định mọi nonce hoặc token đều phải dùng một lần. Trước hết xác định quy tắc của loại bằng chứng đang kiểm thử, tránh áp yêu cầu giao dịch một lần lên một access token được thiết kế cho nhiều request.

### 8.2. Cửa sổ thời gian

Với timestamp được ký, sinh các mốc nằm trong cửa sổ chấp nhận, sát biên, quá cũ và quá xa trong tương lai theo mức lệch đồng hồ được cho phép. Dùng nguồn thời gian có thể điều khiển trong môi trường test, thay vì chờ thời gian thật dài hoặc thay đổi đồng hồ toàn máy một cách thiếu kiểm soát.

Kiểm tra cả ba việc:

1. Chữ ký hợp lệ nhưng thời gian không còn hợp lệ có bị xử lý đúng chính sách không?
2. Phát lại nhiều lần trong cửa sổ còn hợp lệ có tạo thêm hiệu lực không?
3. Sửa timestamp mà không tạo chữ ký hợp lệ mới có bị chặn không?

Timestamp giới hạn khoảng thời gian một bản sao có thể được chấp nhận; nó không tự loại các bản sao trong khoảng đó.

### 8.3. Thời hạn giữ dữ liệu chống phát lại

Thời gian lưu nonce hoặc bản ghi chống trùng phải phù hợp với toàn bộ khoảng mà cùng bằng chứng còn có thể được chấp nhận, bao gồm quy tắc lệch đồng hồ và các đường xử lý liên quan. Không chỉ chọn thời hạn theo cảm giác.

Ví dụ hợp đồng kiểm thử cho phép timestamp đi trước thời gian phía nhận tối đa 30 giây và chấp nhận tuổi thông điệp tối đa 5 phút. Thông điệp có timestamp `10:00:00` có thể được tiếp nhận lần đầu lúc `09:59:30` và vẫn hợp lệ về tuổi tới biên `10:05:00`, tùy quy tắc bao gồm biên của hợp đồng.

Nếu bản ghi chống phát lại bị xóa sau 5 phút tính từ lúc nhận đầu, nó có thể biến mất lúc `10:04:30`, trong khi bản sao vẫn nằm trong cửa sổ thời gian. Test nên tạo đúng khoảng hở đó để kiểm tra việc dùng lại bằng chứng.

Ràng buộc nghiệp vụ dài hạn có thể cần tồn tại lâu hơn cửa sổ nonce. Xóa dữ liệu chống trùng ngắn hạn không đồng nghĩa một yêu cầu hoàn tiền cũ được quyền thực hiện lại.

### 8.4. Envelope mới, cùng sự kiện cũ

Một nguồn tích hợp có thể ký lại lần giao sau bằng timestamp mới. Khi hợp đồng cho phép điều đó, kiểm thử cùng event ID hoặc cùng hiệu lực nghiệp vụ trong envelope mới được xác thực hợp lệ. Không chỉ dựa vào chữ ký hoặc timestamp nguyên bản để nhận diện sự kiện đã xử lý.

Nếu nội dung sự kiện bị sửa trái hợp đồng, cần từ chối hoặc xử lý xung đột phù hợp. Một chữ ký hợp lệ từ nguồn có quyền gửi không tự cho phép nguồn đó ghi đè lịch sử hiệu lực đã hoàn tất.

## 9. Phát lại sau thay đổi quyền, trạng thái và phê duyệt

### 9.1. Quyền đã bị thu hồi

Cho người dùng thực hiện hợp lệ, sau đó thu hồi quyền đọc hoặc quyền thao tác theo cơ chế của hệ thống và phát lại yêu cầu cũ. Tách hai câu hỏi:

- Có tạo thêm hiệu lực hay không?
- Có công bố dữ liệu mà người gọi không còn được phép xem hay không?

Một cơ chế trả ngay kết quả từ bộ nhớ idempotency trước kiểm tra quyền công bố có thể không tạo giao dịch trùng nhưng vẫn làm lộ dữ liệu. API tra cứu mã thao tác, đường tải kết quả và thông báo lỗi cũng cần được kiểm tra.

Chính sách thu hồi có thể có điểm hiệu lực hoặc độ trễ được cam kết. Test phải đối chiếu với cam kết đó; không mặc định mọi phiên, token và bộ nhớ đệm đều thay đổi tức thời.

### 9.2. Revision đã được sửa

Sau khi revision 7 được duyệt, sửa trường trọng yếu tạo revision 8. Thử phát lại lệnh đặt hàng cũ, bằng chứng phê duyệt cũ hoặc payload tự khai revision được duyệt.

Nếu thao tác cũ chưa từng hoàn tất, việc tiếp nhận lại không được tạo đơn với nội dung revision 8 dựa trên phê duyệt revision 7. Nếu thao tác cũ đã hoàn tất đúng theo snapshot revision 7, phát lại chỉ có thể trả kết quả cũ theo quyền, không tạo thêm đơn và không đổi nội dung lịch sử sang revision 8.

### 9.3. Trạng thái cuối và giá đã thay đổi

Thử phát lại sau khi đối tượng bị hủy, đóng hoặc hết hiệu lực theo chính sách. Phân biệt trả kết quả của một hiệu lực đã xảy ra với tạo hiệu lực mới trên trạng thái hiện tại.

Một kết quả thu tiền đã hoàn tất không được tính lại thành số tiền khác vì giá hiện tại đổi. Ngược lại, một thao tác mới sau khi sửa dữ liệu phải kiểm tra giá, quyền và trạng thái hiện tại; không dùng yêu cầu cũ làm giấy phép bỏ qua các bước đó.

## 10. Phát lại quanh transaction và lỗi tiến trình

Chống replay không chỉ là lưu một cờ `used`. Thời điểm lưu cờ so với hiệu lực nghiệp vụ quyết định cả nguy cơ tạo trùng và nguy cơ làm mất thao tác hợp lệ.

| Điểm gián đoạn | Nguy cơ | Kỳ vọng sau phục hồi và phát lại |
| --- | --- | --- |
| Trước đăng ký thao tác | Yêu cầu chưa được tiếp nhận bền vững | Có thể tiếp nhận theo hợp đồng nhưng vẫn giữ bất biến |
| Sau đăng ký, trước hiệu lực | Cờ đã có nhưng công việc chưa xong | Có đường tiếp tục hoặc kết thúc rõ ràng, không coi mặc định đã thành công |
| Sau ghi dữ liệu, trước commit | Dữ liệu nghiệp vụ chưa hoàn tất | Phần chưa commit được xử lý nguyên tử theo thiết kế |
| Sau commit, trước phản hồi | Client không biết đã thành công | Nhận diện kết quả cũ, không thực hiện lại |
| Sau hiệu lực ngoài, trước lưu kết quả | Khoản thu hoặc hoàn có thể đã xảy ra | Theo dõi, đối soát hoặc phát lại cùng định danh ngoài phù hợp |

Với hiệu lực thuần database, kiểm thử xem bản ghi thao tác, sổ nghiệp vụ và sự kiện cần thiết có nhất quán tại commit hay không. Với dịch vụ ngoài, rollback database nội bộ không tự hoàn tác được khoản thu hoặc hoàn ở hệ thống khác.

Một test có giá trị là cho server hoàn tất commit nhưng làm mất phản hồi, sau đó gửi lại cùng thao tác. Kỳ vọng là kết quả được khôi phục mà số hiệu lực không tăng.

Không coi timeout, lỗi mạng hoặc lỗi kỹ thuật là bằng chứng chắc chắn chưa có hiệu lực. Việc xóa bản ghi chống trùng rồi gửi một giao dịch mới trong trạng thái chưa rõ có thể chính là nguyên nhân tạo trùng.

## 11. Phát lại đồng thời, giao trễ và đảo thứ tự

### 11.1. Nhiều bản sao cùng lúc

Cho hai tác vụ độc lập gửi cùng yêu cầu và cùng định danh gần đồng thời. Dùng điểm đồng bộ đầu vào hoặc điểm điều khiển test có giới hạn thời gian để tiếp cận vùng tranh chấp.

Kiểm chứng việc đăng ký và tạo hiệu lực không có khoảng hở kiểu “cả hai cùng thấy chưa xử lý”. Đọc dữ liệu đã commit sau khi cả hai thao tác có kết quả cuối theo hợp đồng. Chỉ gửi tuần tự chưa kiểm tra được tình huống này.

Điểm điều khiển không được buộc request đang giữ khóa phải chờ request khác đi qua chính khóa đó. Khi triển khai đúng cố tình tuần tự hóa, bộ test phải cho phép cơ chế phân xử hoàn tất thay vì tự tạo deadlock.

### 11.2. Thông điệp đến trễ

Phát lại thông điệp sau khi bản ghi ngắn hạn đã được dọn hoặc sau khi worker khởi động lại. Hành vi phát lại phải được đối chiếu với cửa sổ cam kết, đồng thời các giới hạn nghiệp vụ còn hiệu lực phải tiếp tục đúng.

Nếu thông điệp có thể được giao lại lâu hơn thời gian lưu khóa, cần kiểm tra cơ chế nhận diện dài hạn hoặc ràng buộc trên đối tượng mà thiết kế cung cấp. Không suy ra hiệu lực cũ đã biến mất chỉ vì một bảng chống trùng không còn dòng tương ứng.

### 11.3. Sự kiện đảo thứ tự

Một sự kiện trạng thái cũ đến sau sự kiện mới có thể làm đối tượng lùi trạng thái hoặc phát sinh lại tác động. Sinh thứ tự giao khác nhau theo hợp đồng nguồn và kiểm tra state machine, phiên bản sự kiện hoặc quy tắc đối soát tương ứng.

Không sắp xếp mọi sự kiện theo thời gian do client tự khai rồi coi đó là thứ tự đáng tin cậy. Cần dựa vào định danh, phiên bản hoặc nguồn sự thật mà hệ thống thực sự cam kết sử dụng.

## 12. Oracle: điều gì chứng minh bản phát lại không gây hại?

Oracle là căn cứ để kết luận kiểm thử đúng hay sai. Với replay, cần quan sát nhiều lớp thay vì chỉ đọc phản hồi.

| Lớp | Bằng chứng minh họa |
| --- | --- |
| API | Kết quả phù hợp hợp đồng; không lộ dữ liệu ngoài quyền |
| Thao tác | Một danh tính nghiệp vụ, nội dung đã ràng buộc không bị đổi |
| Sổ nghiệp vụ | Số khoản thu hoặc hoàn, tổng giá trị và quan hệ bảo toàn đúng |
| Đối tượng | Trạng thái, revision, phê duyệt và chủ sở hữu đúng |
| Tích hợp ngoài | Số hiệu lực được chấp nhận đúng, định danh ngoài nhất quán |
| Sự kiện | Không tạo thêm hiệu lực logic trái chính sách khi giao lại |
| Kiểm toán | Có dấu vết cần thiết và không ghi bí mật |

Phân biệt số lần gọi dịch vụ với số hiệu lực. Một dịch vụ ngoài có hợp đồng khử trùng có thể được gọi nhiều lần cho cùng thao tác nhưng chỉ tạo một khoản hoàn. Kiểm tra “chỉ gọi đúng một lần” có thể sai với một thiết kế retry hợp lệ.

Ngược lại, một dòng idempotency nội bộ không chứng minh ngoài hệ thống chỉ có một khoản hoàn. Bộ giả lập tích hợp nên ghi nhận cả định danh yêu cầu và các hiệu lực đã được chấp nhận.

Với worker bất đồng bộ, xác định điểm kết thúc quan sát và chờ theo điều kiện có thời hạn. Hết thời hạn mà kết quả vẫn chưa rõ là thất bại hoặc cần điều tra; không đánh dấu an toàn chỉ vì chưa thấy dòng trùng ở lần truy vấn đầu.

Snapshot phải đọc dữ liệu đã commit bằng ngữ cảnh phù hợp. Transaction bao ngoài hoặc cache của framework test có thể che trạng thái thật nếu không được kiểm soát.

## 13. Ví dụ đầy đủ: cùng yêu cầu hoàn tiền, nhiều đường gửi

Sử dụng fixture giao dịch `1000000 VND`, yêu cầu `RF-1` đã duyệt `300000 VND` và một tích hợp hoàn tiền giả lập.

1. Thực hiện `RF-1` với khóa `K1`; dịch vụ ngoài xác nhận một khoản hoàn.
2. Phát lại nguyên bản `RF-1, K1`; kiểm tra không tăng tổng hoàn.
3. Gửi lại cùng `RF-1` với request ID mới; kiểm tra không coi là quyền hoàn mới.
4. Gửi cùng `RF-1` với khóa `K2`; ràng buộc một lần cho yêu cầu hoàn vẫn phải ngăn khoản hoàn thứ hai.
5. Phát lại thông báo hoàn thành từ tích hợp; không cộng tiền lần nữa vào sổ nội bộ.
6. Khởi động lại worker rồi tra cứu; kết quả lịch sử vẫn nhất quán và chỉ được công bố đúng quyền.

Kỳ vọng sau các bước trên:

```text
số khoản hoàn có hiệu lực của RF-1 = 1
tổng hoàn của giao dịch = 300000 VND
phần còn được hoàn = 700000 VND
```

Sau đó tạo yêu cầu độc lập `RF-2` được duyệt hợp lệ cho `200000 VND`. Nếu chính sách cho phép hoàn nhiều đợt, thực hiện `RF-2` phải thành công, làm tổng hoàn thành `500000 VND`, còn `500000 VND` có thể hoàn.

Đối chứng `RF-2` giúp phát hiện cơ chế chống trùng quá rộng, chẳng hạn cấm mọi lần hoàn thứ hai cho cùng giao dịch. Cơ chế đúng nhận diện quyền nghiệp vụ đã dùng, đồng thời giữ giới hạn tổng hợp trên giao dịch.

Trong bộ test tự động, nên tách các biến thể thành các ca độc lập khi có thể để lỗi ở một bước không che các bước sau. Giữ một số chuỗi dài có chủ đích cho rủi ro phụ thuộc lịch sử, restart hoặc phục hồi.

## 14. Tự động hóa và sinh biến thể có ý nghĩa

Đặt kiểm thử ở lớp đủ để chứng minh rủi ro:

- Unit hoặc domain test cho ràng buộc theo yêu cầu nghiệp vụ, trạng thái và revision.
- Integration test với database phù hợp cho đăng ký nguyên tử, transaction, restart và cạnh tranh.
- API test cho phạm vi khóa, quyền, payload bị sửa và hợp đồng phản hồi.
- Kiểm thử tích hợp ngoài cho chữ ký, timestamp, thông điệp trùng, timeout và đối soát.
- Một số luồng toàn hệ thống cho các hiệu lực nhạy cảm đi qua nhiều thành phần.

Với property-based testing, có thể sinh số lần phát lại, độ trễ, biến thể metadata, chủ thể, trạng thái ban đầu và điểm lỗi. Thuộc tính cốt lõi là số hiệu lực không vượt quyền của thao tác, trong khi lần thực hiện hợp lệ vẫn có thể hoàn tất.

Ví dụ giả mã:

```text
forAll validRefundRequest, replayHistory:
    initializeIsolatedFixture(validRefundRequest)
    executeOneValidOperation()
    runHistoryWithDuplicatesDelaysAndControlledFailures(replayHistory)
    awaitContractualCompletion(deadline)

    assert effectiveRefundsForBusinessRequest <= 1
    assert totalRefunded <= allowedRefundTotal
    assert noUnauthorizedResultDisclosure
    assert completedValidOperationIsNotLost
```

Bộ sinh phải tạo đủ trường hợp thật sự tiếp cận cơ chế chống replay. Nếu đa số payload sai chữ ký hoặc sai định dạng từ đầu, test ít chứng minh được điều gì về phát lại một yêu cầu hợp lệ.

Khi thu nhỏ phản ví dụ, giữ cùng danh tính thao tác, cùng phạm vi và điểm lỗi quan trọng. Nếu quá trình thu nhỏ biến bản phát lại thành hai thao tác mới độc lập, kết quả không còn kiểm tra cùng thuộc tính.

Lưu seed, dữ liệu đã thu nhỏ và lịch lỗi đủ tái hiện. Với đồng thời, seed không luôn tái tạo được lịch của hệ điều hành; cần thêm mốc hoặc điểm điều khiển thích hợp.

## 15. Những kết luận sai cần tránh và cách báo cáo lỗi

| Kết luận sai | Điều còn thiếu |
| --- | --- |
| “Có chữ ký nên không replay được” | Bản sao nguyên vẹn có thể giữ chữ ký hợp lệ |
| “Có timestamp nên chỉ chạy một lần” | Nhiều bản sao vẫn có thể nằm trong cùng cửa sổ |
| “Lần hai trả lỗi nên an toàn” | Hiệu lực có thể đã xảy ra trước khi trả lỗi |
| “Lần hai trả thành công nên bị lỗi” | Có thể chỉ xác nhận lại kết quả cũ mà không tạo thêm hiệu lực |
| “Đổi khóa là giao dịch mới hợp lệ” | Cùng quyền nghiệp vụ có thể đã được sử dụng |
| “Có một dòng chống trùng là đủ” | Dữ liệu nghiệp vụ và tích hợp ngoài có thể không nhất quán |
| “Xóa bản ghi cũ thì được thực hiện lại” | Hiệu lực và giới hạn nghiệp vụ dài hạn vẫn tồn tại |
| “Biết khóa thì được đọc kết quả” | Vẫn cần kiểm tra quyền theo chủ thể và đối tượng |
| “Không thấy dòng trùng ngay lập tức là đạt” | Worker hoặc thông điệp còn có thể tạo hiệu lực sau đó |

Một báo cáo lỗi nên nêu bất biến bị phá, tiền điều kiện, bản yêu cầu tổng hợp hoặc đã che bí mật, thứ tự phát lại, kết quả mong đợi, kết quả thực tế và bằng chứng đã commit. Nếu có hiệu lực ngoài, ghi định danh thao tác test và kết quả từ bộ giả lập hoặc môi trường kiểm thử tương ứng.

Phân biệt lỗi hệ thống với fixture sai, oracle sai và kết quả chưa xác định do môi trường. Không sửa kỳ vọng thành chấp nhận hành vi hiện tại chỉ để test xanh. Nếu chính sách thay đổi hợp lệ, cập nhật phát biểu bất biến và các ca đối chứng liên quan cùng nhau.

Khi tìm thấy lỗi thật, giữ ca tái hiện tối thiểu làm hồi quy, bổ sung các đường vào cùng tạo hiệu lực và chạy lại ở lớp quan sát được ranh giới lỗi. Không chỉ kiểm tra lại giao diện nếu lỗi nằm ở transaction hoặc consumer.

## 16. Danh sách kiểm tra cho replay attack test

- Đã xác định một lần thao tác hợp lệ và quyền nghiệp vụ mà nó sử dụng.
- Đã phân biệt request ID, idempotency key, event ID, nonce và business operation ID.
- Đã có lần đầu thành công làm đối chứng, cùng thao tác mới hợp lệ khi nghiệp vụ cho phép.
- Đã thử phát lại nguyên bản, đổi metadata và đổi khóa nhưng giữ cùng quyền nghiệp vụ.
- Đã thử nội dung bị sửa, phạm vi khác và đường vào khác có liên quan.
- Đã kiểm tra cửa sổ timestamp, ràng buộc nonce và chữ ký theo đúng hợp đồng.
- Đã kiểm tra restart, nhiều instance và nhiều bản sao đồng thời nếu thuộc mô hình triển khai.
- Đã thử phát lại sau thay đổi quyền, trạng thái, giá hoặc revision được duyệt.
- Đã tiêm lỗi quanh commit và hiệu lực ngoài khi chúng ảnh hưởng kết quả.
- Đã đọc dữ liệu đã commit, sổ nghiệp vụ và hiệu lực tích hợp cần thiết.
- Đã xác định thời điểm kết thúc quan sát cho xử lý bất đồng bộ.
- Đã bảo vệ thông tin xác thực, khóa ký và dữ liệu trong mẫu tái hiện.

Một replay attack test có giá trị khi nó chứng minh yêu cầu cũ không thể tạo thêm quyền hoặc hiệu lực ngoài chính sách, đồng thời vẫn cho phép retry và các thao tác mới hợp lệ. Kết luận cần dựa trên danh tính nghiệp vụ, trạng thái đã commit và hiệu lực thực tế qua toàn bộ luồng xử lý.
