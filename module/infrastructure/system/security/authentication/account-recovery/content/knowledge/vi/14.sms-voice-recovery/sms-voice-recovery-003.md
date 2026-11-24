# Telephony delivery risks: Rủi ro giao mã khôi phục qua SMS và cuộc gọi

## 1. Giao được mã chưa có nghĩa là khôi phục đúng người

SMS và cuộc gọi tự động giúp người dùng tiếp tục khôi phục tài khoản khi không còn mật khẩu hoặc một thiết bị xác thực. Tuy nhiên, số điện thoại là một địa chỉ định tuyến do hệ thống viễn thông quản lý. Quyền nhận thông tin tại số đó có thể thay đổi mà ứng dụng không biết ngay.

Một luồng khôi phục cần phân biệt ba kết quả:

- **Yêu cầu gửi đã được tiếp nhận:** hệ thống của ứng dụng hoặc nhà cung cấp đã nhận tác vụ.
- **Thông điệp hoặc cuộc gọi đã được giao:** hạ tầng báo một trạng thái giao nhận theo định nghĩa của nhà cung cấp.
- **Bằng chứng khôi phục đã được chấp nhận:** máy chủ xác minh mã, kiểm tra ngữ cảnh và xác định bằng chứng đủ cho một hành động cụ thể.

Chỉ kết quả cuối cùng mới có thể dẫn đến quyền khôi phục. Ngay cả khi nhập đúng mã, mức quyền vẫn phải phụ thuộc chính sách rủi ro, đặc biệt khi người dùng yêu cầu thay MFA, đăng ký passkey mới hoặc thu hồi thiết bị cũ.

Bài học này tập trung vào những gì có thể xảy ra trên đường giao mã và cách thiết kế hệ thống để lỗi viễn thông không trở thành đường chiếm đoạt tài khoản.

## 2. Nhận diện chuỗi giao nhận và các ranh giới tin cậy

Một yêu cầu SMS thường đi qua nhiều thành phần. Cuộc gọi có thể đi qua nhà cung cấp thoại, mạng điện thoại, tổng đài doanh nghiệp hoặc dịch vụ chuyển tiếp.

~~~mermaid
flowchart LR
    A[Luồng khôi phục] --> B[Chính sách rủi ro và giới hạn gửi]
    B --> C[Nhà cung cấp SMS hoặc Voice]
    C --> D[Nhà mạng và tuyến trung gian]
    D --> E[Số điện thoại đã đăng ký]
    E --> F[Thiết bị, tổng đài hoặc hộp thư thoại]
    F --> G[Người nhận thực tế]
    C -. Trạng thái giao nhận .-> H[Bộ xử lý callback]
    H --> I[Hồ sơ giao nhận]
    G --> J[Nhập mã trong phiên khôi phục]
    J --> K[Máy chủ xác minh bằng chứng]
    K --> L[Hành động được phép theo chính sách]
~~~

Ứng dụng thường kiểm soát được việc tạo challenge, chọn đích nhận và xác minh mã. Ứng dụng không mặc nhiên kiểm soát được người đang giữ SIM, cấu hình chuyển tiếp hoặc quyền truy cập hộp thư thoại.

Có bốn nhóm rủi ro cần theo dõi:

| Nhóm | Câu hỏi thiết kế | Ví dụ hậu quả |
| --- | --- | --- |
| Bí mật của mã | Ai có thể đọc hoặc nghe mã trên đường đi? | Người khác dùng mã trước chủ tài khoản |
| Đúng người nhận | Số đang đăng ký có còn thuộc người dùng không? | Mã tới người nhận số tái cấp |
| Khả dụng và thời gian | Mã có tới kịp và đúng thứ tự không? | Người dùng nhập mã cũ hoặc bị khóa đường khôi phục |
| Lạm dụng tài nguyên | Ai có thể ép hệ thống gửi tin hoặc gọi điện? | Tăng cước, quấy rối, cạn hạn mức nhà cung cấp |

Mã hóa HTTPS giữa ứng dụng và API nhà cung cấp bảo vệ một đoạn của chuỗi. Không được từ đó suy ra toàn bộ đường SMS hoặc cuộc gọi là kênh mã hóa đầu cuối do ứng dụng kiểm soát.

## 3. SIM swap và chuyển mạng giữ số làm thay đổi người nhận

### Hai cơ chế cần phân biệt

**SIM swap** là việc dịch vụ của số điện thoại được chuyển sang SIM hoặc hồ sơ eSIM khác. **Port-out** là chuyển số sang nhà cung cấp khác. Cả hai đều có thể là thao tác hợp lệ của người dùng; khi bị thực hiện trái phép, người khác có thể nhận tin nhắn hoặc cuộc gọi gửi tới số đó.

Trong kịch bản chiếm đoạt, kẻ tấn công có thể:

1. Biết tên đăng nhập hoặc email của nạn nhân.
2. Giành quyền nhận thông tin tại số đã đăng ký.
3. Khởi tạo khôi phục tài khoản.
4. Nhận mã gửi tới số đó.
5. Dùng mã để tìm cách thay thông tin đăng nhập.

Nếu hệ thống chỉ kiểm tra “mã đúng”, kẻ tấn công có thể đi qua luồng dù chưa từng cầm thiết bị cũ của nạn nhân.

NIST xếp xác minh ngoài băng qua PSTN vào nhóm bị hạn chế, yêu cầu có phương thức thay thế và khuyến nghị xét tín hiệu đổi thiết bị, đổi SIM hoặc chuyển mạng. Đổi số đã đăng ký được xem là gắn một phương thức xác thực mới. Tham khảo [NIST SP 800-63B-4, mục 3.1.3.3](https://pages.nist.gov/800-63-4/sp800-63b.html#pstn).

### Sử dụng tín hiệu nhà mạng đúng mức

Tín hiệu về lần đổi SIM gần đây có thể hỗ trợ quyết định, nếu nhà cung cấp dữ liệu có khả năng cung cấp tại khu vực liên quan. Khi tích hợp, cần lưu cả thời điểm truy vấn, độ mới của thông tin và trạng thái không có dữ liệu.

Không đồng nhất các kết quả sau:

| Kết quả tín hiệu | Cách hiểu phù hợp |
| --- | --- |
| Có thay đổi gần đây | Cần đánh giá thêm cùng hành động được yêu cầu |
| Không ghi nhận thay đổi trong phạm vi dữ liệu | Chưa thấy tín hiệu đó; không chứng minh tài khoản an toàn |
| Dịch vụ truy vấn lỗi | Chưa đánh giá được, không phải kết quả rủi ro thấp |
| Không hỗ trợ số hoặc khu vực | Thiếu tín hiệu, cần áp dụng chính sách cho dữ liệu không xác định |

Một người đổi điện thoại hợp lệ không nhất thiết là kẻ tấn công. Vì vậy, tín hiệu rủi ro nên dẫn tới bước xác minh độc lập hoặc xử lý theo chính sách, thay vì tự động khóa tài khoản vô thời hạn.

## 4. Số điện thoại tái cấp phá vỡ giả định về chủ sở hữu lâu dài

Người dùng có thể bỏ số cũ nhưng quên gỡ số khỏi các tài khoản trực tuyến. Khi số được cấp lại, người mới có thể nhận thông điệp khôi phục vẫn được gửi tới địa chỉ cũ.

Ví dụ:

- Tháng 1, Minh đăng ký tài khoản bằng số A.
- Tháng 6, Minh ngừng sử dụng số A nhưng vẫn giữ liên kết trong tài khoản.
- Sau đó, số A được nhà mạng cấp cho người khác.
- Một yêu cầu khôi phục gửi mã tới số A có thể tới người mới.

Trong trường hợp này, không cần giả định có SIM swap trái phép. Dữ liệu liên kết giữa tài khoản và số đã lỗi thời.

Nghiên cứu của Kevin Lee và Arvind Narayanan tại Princeton phân tích nguy cơ số tái cấp dẫn tới chiếm đoạt tài khoản qua khôi phục. Nghiên cứu thực hiện với nhà mạng tại Hoa Kỳ; không nên dùng kết quả mẫu đó như tỷ lệ rủi ro của mọi quốc gia. Xem [Security and Privacy Risks of Number Recycling at Mobile Carriers in the United States](https://collaborate.princeton.edu/en/publications/security-and-privacy-risks-of-number-recycling-at-mobile-carriers/).

Các lựa chọn thiết kế từ rủi ro này gồm:

- Cung cấp thao tác thay hoặc gỡ số khi người dùng còn đăng nhập được.
- Nhắc rà soát phương thức khôi phục trong các thời điểm phù hợp.
- Xét tuổi của liên kết số điện thoại và lịch sử sử dụng cùng các bằng chứng khác.
- Áp dụng kiểm tra mạnh hơn khi một tài khoản lâu không hoạt động đột ngột khôi phục chỉ bằng số.
- Chuẩn bị mã dự phòng hoặc phương thức độc lập trước khi người dùng mất quyền truy cập.

Xác minh một mã SMS hôm nay chứng minh khả năng nhận mã ở thời điểm đó. Nó không tự chứng minh người nhận là chủ sở hữu lịch sử của tài khoản.

## 5. Rủi ro đặc thù của SMS, cuộc gọi và thiết bị nhận

### SMS có thể lộ sau khi đã tới thiết bị

Ngay cả khi tuyến gửi hoạt động đúng, mã vẫn có thể xuất hiện trên màn hình khóa, thiết bị đồng bộ hoặc ứng dụng có quyền đọc thông tin liên quan. Điện thoại dùng chung cũng làm suy yếu giả định chỉ một người đọc được mã.

Thiết kế thông điệp nên hạn chế dữ liệu đi kèm: không gửi mật khẩu mới, thông tin tài khoản đầy đủ hoặc nhiều bí mật trong cùng tin nhắn. Mã cần gắn với mục đích cụ thể để người nhận có cơ sở nhận biết yêu cầu bất thường.

Tên người gửi hoặc một chuỗi hội thoại có thương hiệu có thể hỗ trợ nhận diện, nhưng không nên được xem là bằng chứng đủ để người dùng tin mọi yêu cầu cung cấp mã.

### Cuộc gọi có thể bị chuyển tiếp hoặc vào hộp thư thoại

Cuộc gọi đến số đã đăng ký có thể:

- Được chuyển sang số khác.
- Đi qua tổng đài có nhiều người tiếp cận.
- Được trả lời bởi IVR.
- Rơi vào hộp thư thoại.
- Bị ghi âm hoặc phát loa ngoài trong không gian dùng chung.

Vì vậy, trạng thái “cuộc gọi đã kết nối” không xác định ai nghe mã.

Một phương án giảm việc đọc mã ngay vào hộp thư thoại là yêu cầu tương tác trước khi phát mã, chẳng hạn nhấn một phím. Tuy nhiên, bước này chỉ là biện pháp hỗ trợ: người tấn công cũng có thể tương tác, và hệ thống phát hiện máy trả lời tự động có thể phân loại sai. Không nâng mức bảo đảm danh tính chỉ vì có một lần bấm phím.

Nếu chính sách không cho phép lưu mã vào hộp thư thoại, cách phát thoại, phát lại và xử lý khi không có người nghe cần được thiết kế tương ứng. Chức năng ghi âm hoặc phiên âm cũng phải được xem xét vì có thể tạo thêm bản sao của mã.

### SMS và cuộc gọi tới cùng số có rủi ro chung

Khi quyền định tuyến của số đã bị chuyển, cả SMS lẫn cuộc gọi đều có thể tới cùng người không được phép. Chuyển từ SMS sang Voice không tự tạo ra một yếu tố độc lập.

Cần phân biệt:

- **Đổi cách giao:** thử cuộc gọi vì tin nhắn không tới.
- **Đổi bằng chứng:** dùng một phương thức đã đăng ký khác, không dựa vào cùng số bị nghi ngờ.

Chỉ lựa chọn thứ hai mới có khả năng giải quyết sự cố mất kiểm soát số điện thoại, tùy mức độc lập thực tế của phương thức thay thế.

## 6. Chậm, mất, trùng và sai thứ tự là các tình huống cần dự kiến

### Mã tới sau khi hết hạn

Tin nhắn có thể bị giữ trong hàng đợi, thiết bị mất sóng, người dùng đang roaming hoặc mạng có sự cố. Giao nhận thành công sau đó không làm thay đổi thời hạn đã được máy chủ đặt cho challenge.

Trong một thiết kế minh họa:

- Challenge hết hạn sau một khoảng ngắn kể từ khi cấp.
- Tác vụ chưa gửi phải kiểm tra challenge còn hoạt động trước khi gọi nhà cung cấp.
- Nếu nhà cung cấp có giới hạn thời gian nằm trong hàng đợi, ứng dụng cấu hình phù hợp với thời hạn còn lại.
- Máy chủ luôn kiểm tra hạn khi xác minh, dù thông điệp vừa mới tới.
- Callback giao thành công tới muộn không được làm sống lại challenge đã hết hạn.

Khoảng thời gian cụ thể phải dựa vào rủi ro và đặc điểm giao nhận. Tăng thời hạn mã vô hạn để bù mạng chậm làm kéo dài cơ hội sử dụng mã bị lộ.

### Mã cũ tới sau mã mới

Khi người dùng yêu cầu gửi lại, thông điệp đầu tiên có thể tới sau thông điệp thứ hai. Nếu mỗi lần cấp tạo một mã mới, người dùng dễ chọn nhầm mã.

Cần xác định rõ chính sách:

| Chính sách | Điều cần quản lý |
| --- | --- |
| Giao lại mã đang còn hoạt động | Không gia hạn mã hoặc xóa ngân sách thử chỉ vì gửi lại |
| Cấp mã mới và thay thế mã cũ | Vô hiệu hóa phiên bản cũ nhất quán, hướng dẫn dùng thông điệp mới nhất |
| Cho phép nhiều mã cùng tồn tại | Đánh giá phần tăng của không gian tấn công và cơ chế tiêu thụ; không mặc định lựa chọn này |

Không trộn các chính sách ngoài ý muốn khi chuyển nhà cung cấp hoặc chuyển sang Voice.

### Timeout API là kết quả chưa xác định

Ứng dụng gửi yêu cầu rồi bị timeout không đồng nghĩa nhà cung cấp chưa nhận được yêu cầu. Gọi lại ngay có thể tạo hai tin nhắn hoặc hai cuộc gọi có tính phí.

Hệ thống nên có mã yêu cầu nội bộ và khả năng đối soát. Chỉ dựa vào idempotency của API khi sản phẩm và endpoint cụ thể có hỗ trợ được xác nhận. Nếu chưa biết yêu cầu trước đã được tạo hay chưa, xử lý trạng thái chưa xác định thay vì tự kết luận thất bại.

Retry cần có giới hạn, giãn nhịp phù hợp và xét thời hạn challenge. Không thử lại vô hạn tới nhiều nhà cung cấp.

### Bộ lọc, loại số và định dạng nội dung

Một số tuyến có thể chặn nội dung, thiếu hỗ trợ cho loại người gửi hoặc không giao được tới loại số nhất định. Không suy ra số sai hay có gian lận chỉ từ một lần giao thất bại.

Nội dung tiếng Việt và ký tự đặc biệt có thể ảnh hưởng cách mã hóa, phân đoạn và chi phí theo dịch vụ. Cần kiểm tra thông điệp thực tế với nhà cung cấp, thay vì chỉ đếm số ký tự hiển thị. Việc chuẩn hóa số điện thoại giúp tránh gửi nhầm do định dạng, nhưng không chứng minh người nhận có quyền với tài khoản.

## 7. Không dùng trạng thái nhà cung cấp làm bằng chứng danh tính

### Ý nghĩa trạng thái phụ thuộc sản phẩm

Ví dụ, tài liệu Messages của Twilio định nghĩa trạng thái `delivered` dựa trên xác nhận từ nhà mạng phía trên và, khi có, thiết bị nhận. Điều đó không xác định người đọc là chủ tài khoản. Xem [Twilio Messages resource, Message status values](https://www.twilio.com/docs/messaging/api/message-resource#message-status-values).

Đối với cuộc gọi, Twilio giải thích rằng trạng thái `completed` có thể xảy ra khi người, IVR hoặc hộp thư thoại trả lời và có dữ liệu âm thanh được truyền. Xem [Twilio Call resource, Notice about completed calls](https://www.twilio.com/docs/voice/api/call-resource#notice-about-completed-calls).

Đây là ví dụ của một nhà cung cấp. Khi sử dụng dịch vụ khác, phải đọc định nghĩa tương ứng; không suy diễn từ tên trạng thái.

Các suy luận sau đều không đủ:

~~~text
SMS được báo delivered       -> chủ tài khoản đã đọc mã
Cuộc gọi được báo completed  -> đúng người đã nghe mã
Có callback hợp lệ          -> người dùng đã xác minh OTP
~~~

Callback hợp lệ chỉ chứng minh một thông báo giao nhận đã được chấp nhận từ nguồn tương ứng theo cơ chế tích hợp.

### Tách hai vòng đời trong mô hình dữ liệu

Một cách thiết kế là duy trì hai nhóm trạng thái độc lập:

| Vòng đời nội bộ | Ví dụ trạng thái | Thành phần được phép cập nhật |
| --- | --- | --- |
| Giao nhận | REQUESTED, ACCEPTED, REPORTED_DELIVERED, FAILED, UNKNOWN | Bộ gửi và bộ xử lý thông báo nhà cung cấp |
| Khôi phục | PENDING_PROOF, NEED_MORE_PROOF, GRANTED, CONSUMED, EXPIRED | Máy chủ xác minh và chính sách khôi phục |

Các tên trên là mô hình minh họa của ứng dụng, không phải danh sách trạng thái API của nhà cung cấp.

Một lần gửi thất bại không tự chứng minh mã sai. Một lần gửi thành công không được chuyển trực tiếp từ PENDING_PROOF sang GRANTED.

Hồ sơ giao nhận có thể chứa:

~~~json
{
  "deliveryAttemptId": "delivery-internal-identifier",
  "challengeId": "recovery-challenge-identifier",
  "provider": "provider-a",
  "providerResourceId": "provider-message-or-call-identifier",
  "channel": "SMS",
  "destinationVersion": 4,
  "deliveryState": "REPORTED_DELIVERED",
  "reportedAt": "2026-11-23T07:30:20Z"
}
~~~

Đây là bản ghi nội bộ minh họa, không phải phản hồi cần công khai. Nó không chứa OTP, quyền khôi phục hoặc số điện thoại đầy đủ.

`destinationVersion` giúp liên hệ lần gửi với phiên bản thông tin liên lạc đã được dùng. Nếu số điện thoại được thay đổi hợp lệ trong lúc có challenge, hệ thống cần áp dụng chính sách hủy hoặc đánh giá lại challenge cũ, thay vì lặng lẽ đổi đích cho lần gửi tiếp theo.

## 8. Bảo vệ callback và xử lý thông báo đến muộn

Endpoint nhận callback không được tin một nội dung JSON hoặc form data chỉ vì trong đó có mã tài nguyên của nhà cung cấp. Kẻ khác có thể tự gửi yêu cầu tới endpoint công khai.

Các trách nhiệm chính gồm:

1. Kiểm tra nguồn theo cơ chế xác thực hoặc chữ ký mà nhà cung cấp quy định.
2. Xác nhận tài nguyên thuộc đúng tài khoản nhà cung cấp, môi trường và lần gửi nội bộ.
3. Kiểm tra trạng thái và cấu trúc dữ liệu được phép.
4. Xử lý thông báo lặp và thông báo tới không đúng thứ tự.
5. Lưu kết quả giao nhận mà không cấp quyền khôi phục.

Twilio khuyến nghị dùng thư viện xác minh chữ ký do họ cung cấp. Dữ liệu cần xác minh phụ thuộc giao thức webhook, URL và tham số thực tế; không nên tự sáng tạo thuật toán chung cho mọi sản phẩm. Tham khảo [Twilio Secure webhooks](https://www.twilio.com/docs/usage/webhooks/webhooks-security).

Nếu ứng dụng nằm sau reverse proxy, cần xác định URL công khai một cách đáng tin cậy cho quá trình xác minh. Không tùy tiện tin các header chuyển tiếp do nguồn không được kiểm soát cung cấp.

Mã giả cho cách phân tách trách nhiệm:

~~~text
handleDeliveryCallback(httpRequest):
    event = providerAdapter.verifyAndParse(httpRequest)
    attempt = findAttemptByProviderResource(event.resourceId)

    requireExpectedProviderAccount(event, attempt)
    requireSupportedEvent(event)

    atomically:
        if eventAlreadyHandled(event, attempt):
            return ACK

        storeMinimalDeliveryEvent(event, attempt)
        updateDeliveryProjectionAccordingToProviderRules(event, attempt)

    return ACK
~~~

Các hàm trên là mô tả trách nhiệm. Cách nhận diện sự kiện trùng phải dựa trên dữ liệu thực tế của nhà cung cấp. Nếu không có event ID ổn định, vẫn cần bảo đảm cập nhật lặp không tạo tác dụng phụ lặp.

Chữ ký hợp lệ không tự ngăn phát lại một thông báo đã được ký. Nếu giao thức có timestamp hoặc cơ chế chống phát lại, cần kiểm tra theo tài liệu. Dù có hay không, việc xử lý idempotent và liên kết đúng lần gửi vẫn cần thiết.

Thông báo giao thành công tới sau khi challenge EXPIRED hoặc CONSUMED có thể được lưu để đối soát. Nó không được:

- Gia hạn mã.
- Gỡ giới hạn thử.
- Tạo challenge mới.
- Phát hành session đăng nhập.
- Hoàn thành việc thay mật khẩu hoặc xóa MFA.

## 9. Chuyển kênh và chuyển nhà cung cấp cần giữ nguyên chính sách rủi ro

### Fallback để cải thiện giao nhận

Nếu nhà cung cấp SMS gặp sự cố, chuyển sang nhà cung cấp khác có thể cải thiện khả dụng. Nếu người dùng không đọc được SMS nhưng vẫn nghe cuộc gọi tại số đó, Voice có thể là phương án được phép.

Tuy nhiên, một cơ chế fallback cần trả lời:

- Đây là lỗi tuyến gửi hay nghi ngờ mất quyền kiểm soát số?
- Phương án mới có dựa vào cùng số đang bị nghi ngờ không?
- Challenge và phiên khôi phục nào được tiếp tục?
- Mã cũ còn hoạt động hay đã bị thay thế?
- Tổng số lần gửi và thử mã còn lại là bao nhiêu?
- Chi phí và mức độ quấy rối có tăng ngoài giới hạn không?

Không tự động chuyển sang cuộc gọi chỉ vì dịch vụ chống lạm dụng vừa chặn SMS. Việc đổi kênh có thể giúp đối tượng tấn công vượt một lớp kiểm soát nếu chính sách không được áp dụng chung.

### Bảng quyết định minh họa

| Điều kiện | Hành động minh họa |
| --- | --- |
| Lỗi giao SMS tạm thời, không có tín hiệu rủi ro khác | Cho retry có giới hạn hoặc kênh khác đã được phép |
| Có tín hiệu mất kiểm soát số | Không dựa thêm vào SMS hoặc cuộc gọi tới cùng số; yêu cầu bằng chứng độc lập |
| Số mới được thêm trong chính yêu cầu khôi phục | Chưa coi số đó là phương thức khôi phục đã tin cậy |
| Nhà cung cấp dữ liệu rủi ro không phản hồi | Áp dụng chính sách cho trạng thái chưa xác định |
| Hết ngân sách gửi hoặc phát hiện bơm lưu lượng | Hạn chế gửi trên các kênh liên quan; giữ đường khôi phục khác phù hợp |
| Mất mọi phương thức đã đăng ký | Chuyển quy trình xác minh khác đã được phê duyệt |

Bảng này không đặt ra ngưỡng thời gian hoặc mức rủi ro chung cho mọi dịch vụ. Tài khoản có quyền quản trị, thông tin tài chính hoặc dữ liệu nhạy cảm có thể cần yêu cầu bằng chứng khác với tài khoản ít đặc quyền.

Nếu còn một passkey hợp lệ trên thiết bị khác hoặc một mã dự phòng chưa dùng, hệ thống có thể hướng người dùng tới phương thức đó theo chính sách. Không mô tả cuộc gọi tới cùng số như một yếu tố độc lập thứ hai chỉ vì giao diện có thêm một bước.

## 10. Chống bơm lưu lượng, gian lận cước và quấy rối

Một đối tượng không cần khôi phục thành công để gây thiệt hại. Chỉ riêng khả năng buộc hệ thống gửi nhiều SMS hoặc tạo nhiều cuộc gọi đã có thể làm phát sinh chi phí hoặc gây phiền cho người nhận.

Twilio mô tả nguy cơ SMS pumping và lạm dụng xác minh thoại để tạo lưu lượng có tính phí. Xem [Twilio Anti-Fraud Developer’s Guide](https://www.twilio.com/docs/usage/anti-fraud-developer-guide).

Trong thiết kế khôi phục, cần có nhiều phạm vi giới hạn:

| Phạm vi | Mục tiêu |
| --- | --- |
| Mỗi phiên hoặc challenge | Hạn chế nhấn gửi lại và tự động hóa trong một luồng |
| Mỗi tài khoản hoặc đích nhận | Giảm quấy rối một người và tránh tạo challenge mới để né giới hạn |
| IP, thiết bị hoặc nhóm tín hiệu | Hạn chế nguồn phát sinh yêu cầu bất thường |
| Quốc gia, tuyến và loại số | Giới hạn gửi đến nơi không phục vụ hoặc tuyến có rủi ro chi phí |
| Toàn dịch vụ | Kiểm soát tốc độ gửi, ngân sách và nguy cơ cạn hạn mức |
| Chung giữa SMS và Voice | Tránh đổi kênh để có lại toàn bộ lượt gửi |

IP không phải danh tính của người dùng: nhiều người hợp lệ có thể dùng chung mạng, còn đối tượng tấn công có thể phân tán nguồn yêu cầu. Vì vậy, không chỉ dùng một bộ đếm IP.

Với cuộc gọi, có thể giới hạn số lần gọi, thời lượng, số lần phát lại mã và quyền gọi tới các vùng được hỗ trợ. Đích gọi phải lấy từ phương thức đã đăng ký phù hợp, không cho API công khai gọi tùy ý tới số do người yêu cầu cung cấp.

CAPTCHA hoặc thử thách chống bot có thể bổ sung kiểm soát lưu lượng. Chúng không chứng minh quyền sở hữu tài khoản và cần có phương án tiếp cận phù hợp.

Giới hạn gửi mã cũng không nên vô tình biến thành cách khóa mọi hoạt động tài khoản của nạn nhân. Chặn lạm dụng trên đường khôi phục và quyết định đình chỉ đăng nhập là hai hành động cần được đánh giá riêng.

Các ngưỡng phải được thực thi trên máy chủ và được chia sẻ phù hợp giữa các thành phần gửi. Một nhà cung cấp mới không được mặc nhiên có lại ngân sách riêng cho cùng yêu cầu đang bị giới hạn.

## 11. Xử lý sự cố mà không hạ yêu cầu xác minh

Giả sử tỷ lệ SMS thất bại tăng đột ngột tại một mạng di động. Cách xử lý cần vừa khôi phục khả dụng vừa bảo toàn chính sách.

Một trình tự vận hành minh họa:

1. Xác định phạm vi bằng dữ liệu lần gửi, tuyến, mã lỗi và thời điểm; không kết luận mọi thất bại là gian lận.
2. Giới hạn retry để tránh tăng thêm hàng đợi và cước.
3. Kiểm tra kênh hoặc nhà cung cấp dự phòng đã được phê duyệt.
4. Giữ nguyên giới hạn gửi, thời hạn challenge và yêu cầu bằng chứng.
5. Cung cấp thông báo cho người dùng và đường khôi phục thay thế khả dụng.
6. Theo dõi tác động sau chuyển tuyến trước khi mở lại đầy đủ.

Không dùng biện pháp “tạm cho bỏ qua OTP vì nhà mạng lỗi”. Tương tự, nhân viên hỗ trợ không nên thay số bằng một số mới rồi dùng chính mã gửi tới số mới làm bằng chứng duy nhất.

Thông báo giao diện có thể là:

> Hiện chưa thể hoàn tất việc gửi mã. Bạn có thể thử lại khi được phép hoặc chọn phương thức khôi phục khác.

Ở điểm vào công khai, cần bảo đảm câu chữ, mã lỗi và dữ liệu phản hồi không làm lộ tài khoản có tồn tại hoặc số nào đang được đăng ký. Mã lỗi chi tiết của nhà cung cấp có thể chỉ dành cho vận hành.

Một luồng đang bị nghi ngờ SIM swap cũng không nên gửi cảnh báo duy nhất qua chính số bị nghi ngờ. Nếu có kênh độc lập đã xác minh trước, có thể dùng kênh đó để thông báo theo chính sách.

## 12. Tình huống tổng hợp: đúng mã nhưng bằng chứng chưa đủ

Hà mất điện thoại có ứng dụng MFA và muốn khôi phục tài khoản. Tài khoản vẫn gắn số cũ. Trong cùng thời điểm, dịch vụ rủi ro ghi nhận thay đổi SIM gần đây.

Nếu hệ thống làm theo chuỗi:

~~~text
Gửi SMS -> nhận đúng OTP -> xóa MFA -> cấp session đầy đủ
~~~

thì một người đã giành quyền nhận SMS có thể nhận được toàn bộ tài khoản.

Một thiết kế thận trọng hơn sẽ:

- Gắn yêu cầu với hành động “khôi phục hoặc thay MFA”, thay vì xem đây là đăng nhập thông thường.
- Đánh giá tín hiệu thay SIM cùng các thông tin liên quan.
- Không coi cuộc gọi tới cùng số là bằng chứng bổ sung độc lập.
- Yêu cầu phương thức độc lập còn hợp lệ hoặc chuyển quy trình khôi phục đã chuẩn bị.
- Chỉ khi đủ bằng chứng mới cấp quyền giới hạn để thực hiện hành động được phép.
- Sau thay đổi, áp dụng chính sách với phương thức cũ, session và refresh token có liên quan.
- Thông báo sự kiện bằng kênh thích hợp để hỗ trợ phát hiện lạm dụng.

Nếu Hà còn passkey trên thiết bị khác, khả năng dùng phương thức đó cần được hướng dẫn rõ. Nếu mất mọi phương thức, hệ thống phải đi theo đường xác minh khác; không có một mã SMS “đúng” nào tự giải quyết được toàn bộ vấn đề danh tính.

Nếu chấp nhận cho đăng ký passkey mới sau khôi phục, thao tác đó tạo khóa mới theo quy trình tương ứng. SMS hoặc cuộc gọi không phục hồi khóa riêng của passkey đã mất.

## 13. Quan sát đúng chỉ số và giữ bí mật của mã

Cần tách chỉ số giao nhận khỏi chỉ số khôi phục:

| Chỉ số | Điều có thể quan sát | Điều không được tự kết luận |
| --- | --- | --- |
| Số yêu cầu gửi được chấp nhận | Tác vụ đã đi vào hệ thống hoặc nhà cung cấp | Người dùng đã nhận mã |
| Tỷ lệ báo giao thành công | Mức độ giao nhận theo định nghĩa dịch vụ | Đúng người đã đọc hoặc nghe |
| Độ trễ phản hồi giao nhận | Thời gian giữa các mốc kỹ thuật đã ghi nhận | Chính xác lúc con người biết mã |
| Tỷ lệ xác minh mã thành công | Một bước chứng minh đã thành công | Toàn bộ khôi phục đã đủ điều kiện |
| Tỷ lệ hoàn tất hành động khôi phục | Hiệu quả của toàn bộ luồng | Tất cả trường hợp đều là chủ tài khoản hợp lệ |
| Chi phí và lưu lượng theo tuyến | Dấu hiệu tăng tải, sai cấu hình hoặc lạm dụng | Chỉ riêng số lớn đã đủ xác định gian lận |

Các mốc thời gian do nhà cung cấp cung cấp có thể có độ trễ hoặc độ chính xác khác nhau. Khi phân tích, cần ghi rõ đang đo thời gian xử lý nội bộ, thời gian nhà cung cấp hay thời gian phản hồi callback.

Không ghi OTP vào log để điều tra việc gửi chậm. Cũng cần rà soát log request, công cụ APM, dashboard nhà cung cấp, bản ghi âm và bản phiên âm để tránh tạo thêm bản sao bí mật.

Số điện thoại, mã tài nguyên nhà cung cấp và dữ liệu truy vấn rủi ro đều cần quyền truy cập và thời hạn lưu phù hợp. Mã tương quan dùng để đối soát không nên trở thành công cụ tra cứu công khai giúp dò tài khoản.

## 14. Các nguyên tắc cần giữ khi thiết kế

Một thiết kế khôi phục qua điện thoại cần đáp ứng đồng thời:

- **Đích nhận có lịch sử và ngữ cảnh tin cậy:** số vừa nhập hoặc số đã quá lâu không kiểm tra không tự có cùng giá trị với phương thức đã được quản lý tốt.
- **Vòng đời mã độc lập với giao nhận:** trễ, gửi lại, chuyển tuyến và callback không được tự gia hạn hoặc khôi phục mã đã vô hiệu.
- **Bằng chứng được đánh giá theo hành động:** nhận đúng OTP không đồng nghĩa được xóa MFA, thay passkey và đăng nhập toàn quyền.
- **Fallback giữ nguyên giới hạn:** thay kênh hoặc nhà cung cấp phải tiếp tục chính sách chống lạm dụng và kiểm tra rủi ro.
- **Có đường đi khi điện thoại không còn đáng tin:** chuẩn bị phương thức độc lập trước sự cố và quy trình xử lý khi người dùng mất mọi phương thức.

Ba câu hỏi quyết định chất lượng luồng là: **mã đã tới đâu, ai có khả năng nhận nó, và bằng chứng đó cho phép hành động nào**. Hạ tầng viễn thông chủ yếu giúp trả lời câu đầu; hệ thống khôi phục phải chịu trách nhiệm với hai câu còn lại.
