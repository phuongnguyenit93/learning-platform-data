# Mutual TLS

## 1. Từ kênh mã hóa tới xác thực hai phía

Trong chương **Communication security**, mutual TLS, viết tắt là **mTLS**, là cách sử dụng TLS trong đó cả hai phía xác thực đối tác bằng chứng thư và bằng chứng sở hữu khóa riêng tương ứng theo cấu hình đã chọn.

Trong một kết nối TLS xác thực server thông thường, client kiểm tra server nhưng server không nhất thiết nhận diện client bằng chứng thư. Với mTLS, server cũng yêu cầu và xác minh danh tính chứng thư của client. Điều này phù hợp với các đường giao tiếp cần nhận diện workload, ứng dụng tích hợp hoặc thiết bị trong một miền tin cậy.

mTLS giúp bảo vệ tính bí mật và toàn vẹn của dữ liệu trên đoạn kết nối được bảo vệ, đồng thời cung cấp một danh tính đối tác đã được xác thực. Tuy nhiên:

- Có kênh mã hóa chưa đủ nếu không kiểm tra đúng danh tính đối tác.
- Một chứng thư hợp lệ không tự cho phép mọi API.
- Danh tính workload không tự chứng minh danh tính người dùng cuối hoặc tenant của nghiệp vụ.
- Nếu TLS kết thúc ở proxy, bảo vệ và xác thực của đoạn đó không tự kéo dài tới mọi đoạn sau.

Đối với đặc tả yêu cầu bảo mật, câu “các service phải dùng mTLS” cần được cụ thể hóa thành:

**Luồng dữ liệu → đối tác mong đợi → miền tin cậy → kiểm tra chứng thư → phân quyền → vòng đời và bằng chứng.**

Các tên dịch vụ, URI danh tính, ngưỡng và thời hạn trong bài là ví dụ thiết kế. Chúng không phải cấu hình mặc định hay mức bắt buộc cho mọi hệ thống.

## 2. Các thành phần và thuật ngữ cần thống nhất

| Thành phần | Vai trò | Điều không được suy ra |
|---|---|---|
| Chứng thư của workload | Ràng buộc khóa công khai với danh tính theo chính sách cấp phát | Người trình chứng thư được phép làm mọi hành động |
| Khóa riêng | Được dùng để chứng minh quyền sử dụng khóa trong giao thức | Có thể chia sẻ chung giữa mọi replica hoặc mọi service mà không có hệ quả |
| CA và chuỗi chứng thư | Cung cấp quan hệ xác thực tới trust anchor được chấp nhận | Mọi chứng thư có chuỗi hợp lệ đều thuộc môi trường hoặc vai trò mong muốn |
| Trust store | Tập trust anchor được sử dụng cho một mục đích | Kho CA mặc định của máy phù hợp với mọi client nội bộ |
| SAN — subject alternative name | Nơi có thể biểu diễn DNS, URI hoặc dạng danh tính khác | Mọi SAN đều có cùng ngữ nghĩa hoặc được phép dùng làm workload identity |
| Key usage và extended key usage | Giới hạn mục đích sử dụng khóa/chứng thư theo profile | Chứng thư dùng cho server luôn được dùng như client |
| Policy phân quyền | Quyết định danh tính được gọi hành động nào | TLS handshake thành công đồng nghĩa request được cho phép |

Chứng thư thường là dữ liệu công khai để trình bày danh tính. Khóa riêng phải được bảo vệ. Không đưa khóa riêng vào log, repository, ảnh container hoặc gói cấu hình công khai chỉ vì chứng thư có thể được chia sẻ.

Nếu dùng thiết bị hoặc dịch vụ giữ khóa, ứng dụng có thể sử dụng thao tác mật mã mà không đọc trực tiếp byte khóa. Yêu cầu vẫn phải kiểm soát chủ thể được sử dụng khóa và vòng đời quyền đó.

## 3. mTLS diễn ra như thế nào ở mức khái niệm?

Xét service A gọi service B:

```text
Service A                                      Service B
   |------ thiết lập TLS và tham số ----------->|
   |<----- danh tính server và bằng chứng ------|
   |------ danh tính client và bằng chứng ----->|
   |<===== kênh TLS đã xác thực hai phía =======>|
   |------ request ứng dụng ------------------->|
   |       B tiếp tục kiểm tra quyền của A       |
```

Sơ đồ thể hiện các trách nhiệm logic, không phải thứ tự đầy đủ của mọi message trong từng phiên bản TLS.

### 3.1. Trách nhiệm của client

Client phải xác minh:

1. Chuỗi chứng thư server đi tới trust anchor được chấp nhận cho luồng này.
2. Chứng thư còn hiệu lực và đáp ứng profile về thuật toán, mục đích sử dụng và trạng thái tin cậy.
3. Danh tính server khớp đối tác mà client dự định gọi.
4. Không có lỗi xác thực bị bỏ qua bằng cấu hình “trust all” hoặc bỏ kiểm tra danh tính.

Với endpoint có danh tính DNS, việc kiểm tra tên server phải theo cơ chế được thiết kế cho danh tính đó. Định tuyến đúng IP hoặc gửi đúng thông tin chọn virtual host không tự chứng minh server là đối tác mong muốn.

Nếu dùng URI workload thay vì chỉ DNS, phải có quy tắc kiểm tra danh tính tương ứng được thư viện hoặc lớp kiểm soát hỗ trợ. Không tùy ý bỏ hostname verification rồi cho rằng một CA bất kỳ sẽ thay thế được kiểm tra đối tác.

### 3.2. Trách nhiệm của server

Server phải yêu cầu chứng thư client trên đúng listener hoặc luồng bắt buộc mTLS, xác minh chuỗi và profile, rồi ánh xạ danh tính tới chủ thể nội bộ có ý nghĩa.

Danh tính client không nhất thiết là hostname. Cần chọn SAN hoặc cơ chế định danh được policy quy định, kiểm tra miền tin cậy và xử lý trường hợp nhiều danh tính, danh tính mơ hồ hoặc thiếu danh tính bắt buộc.

Client phải chứng minh quyền sử dụng khóa tương ứng trong giao thức. Chỉ có một bản sao file chứng thư công khai không đủ hoàn tất xác thực như chủ thể đó.

### 3.3. TLS bảo vệ đoạn kết nối

Sau handshake, dữ liệu ứng dụng trên đoạn TLS được bảo vệ theo giao thức và cấu hình đã thương lượng. Điều đó không tự bảo vệ:

- Dữ liệu sau khi một endpoint hợp lệ đã giải mã.
- Nội dung được ghi vào log hoặc nơi lưu trữ.
- Đoạn truyền tiếp sau khi TLS kết thúc.
- Hành vi lạm dụng của một workload được xác thực nhưng có quyền quá rộng.

Cần mô tả rõ điểm kết thúc TLS trong sơ đồ kiến trúc thay vì dùng một đường mũi tên “encrypted” cho toàn bộ hệ thống.

## 4. Đặc tả danh tính và miền tin cậy

### 4.1. Chọn một biểu diễn có ngữ nghĩa rõ ràng

Ví dụ danh tính URI do hệ thống giả định quy định:

```text
urn:example:workload:production:order-api
urn:example:workload:production:inventory-api
```

Đây là quy ước nội bộ minh họa, không phải yêu cầu mọi nền tảng dùng cùng định dạng.

Policy phải xác định nguồn cấp, trường chứng thư được đọc, chuẩn hóa, môi trường và phạm vi danh tính. Không suy quyền bằng cách tìm một chuỗi tên service xuất hiện ở bất kỳ đâu trong subject hoặc certificate.

Một danh tính ổn định có thể được giữ khi chứng thư được gia hạn, nhưng nhiều workload không liên quan không nên dùng chung khóa để trở thành cùng một chủ thể ngoài ý muốn.

### 4.2. Trust anchor đúng chưa đủ nếu profile quá rộng

Nếu server chấp nhận mọi chứng thư từ một tập CA rất rộng, nó có thể nhận những client không thuộc miền nghiệp vụ mong muốn. Cần ràng buộc issuer, profile và danh tính đủ hẹp cho luồng.

Các câu hỏi cần chốt:

- Production có tin chứng thư của môi trường thử không?
- CA nào được cấp danh tính client và CA nào được cấp danh tính server?
- Có chấp nhận chứng thư dùng nhiều mục đích không?
- Danh tính thiếu hoặc nằm ngoài namespace được xử lý thế nào?
- Có nhiều trust anchor trong lúc chuyển đổi thì phạm vi quyền của từng miền là gì?

Một chứng thư tự ký không được tin chỉ vì tự ký thành công. Nếu có trust anchor hoặc pinning được cấu hình chủ đích, phải quản lý nó như một quyết định tin cậy có vòng đời, không như một đường bỏ qua xác thực.

## 5. Từ danh tính đã xác thực tới quyền gọi nghiệp vụ

### 5.1. Hai quyết định cần được tách rõ

Một đường gọi cần có cả:

```text
Peer authentication:
    đối tác đã chứng minh danh tính nào?

Authorization:
    danh tính đó có được thực hiện action này
    trên tài nguyên và trong ngữ cảnh này không?
```

Ví dụ policy:

| Danh tính client | Hành động | Kết quả minh họa |
|---|---|---|
| `production:order-api` | Đọc tình trạng còn hàng qua API được cấp | Cho phép trong phạm vi nghiệp vụ |
| `production:order-api` | Điều chỉnh số lượng tồn kho | Từ chối nếu chưa được cấp action |
| Client có chuỗi hợp lệ nhưng danh tính chưa được cấp quyền | Gọi API nội bộ | Từ chối theo policy mặc định |
| Danh tính môi trường thử | Gọi inventory production | Không được tin hoặc không được cấp quyền theo ranh giới đã chọn |

Tùy kiến trúc, một trường hợp bị chặn ở handshake hoặc ở cổng ứng dụng. Cần ghi rõ tầng nào thực thi điều kiện; không yêu cầu mọi lỗi quyền đều biểu hiện thành lỗi TLS.

### 5.2. Không lấy workload làm người dùng cuối

Một service có thể nhận request của nhiều user hoặc tenant. Chứng thư của service xác thực service đó, không tự cung cấp quyền của từng user.

Nếu service A hành động thay người dùng, B cần ngữ cảnh ủy quyền được xác minh phù hợp: ai là người dùng, audience, phạm vi, tenant, thời hạn và quan hệ với caller. Không tin một header `user_id` tự khai chỉ vì request có mTLS.

Tương tự, mTLS giữa các service không tự ngăn lỗi truy cập đối tượng ngoài quyền. Kiểm tra tenant, ownership và action ở nghiệp vụ vẫn cần thiết.

### 5.3. Policy phải có phiên bản và hành vi lỗi

Cần xác định nơi ánh xạ danh tính, ai được đổi quyền, hiệu lực cache và thời gian thu hồi. Không mở rộng quyền tự động chỉ vì một workload có chứng thư mới từ CA được tin.

Nếu không xác định được danh tính hoặc policy cần thiết, luồng được bảo vệ không được chuyển thành anonymous hoặc cho phép tất cả. Nếu có chế độ suy giảm, phải đặc tả phạm vi và cận rủi ro riêng.

## 6. Proxy, gateway và điểm kết thúc TLS

### 6.1. Các mô hình thường gặp

| Mô hình | Ai xác thực ai? | Điều phải đặc tả |
|---|---|---|
| mTLS trực tiếp A tới B | A xác thực B, B xác thực A | Trust store, danh tính mong đợi và quyền tại B |
| Thành phần trung gian chuyển tiếp kết nối ở mức mạng | Handshake có thể vẫn giữa A và B nếu thực sự không kết thúc TLS | Điểm kết thúc thật, định tuyến và khả năng quan sát |
| Proxy kết thúc TLS rồi mở kết nối mới | A và proxy là một đoạn; proxy và B là đoạn khác | Danh tính proxy ở đoạn sau và cách chuyển ngữ cảnh client |
| Sidecar hoặc lớp giao tiếp cạnh workload | Các thành phần đó xác thực đối tác trên đoạn được quản lý | Bảo vệ đoạn ứng dụng tới lớp giao tiếp và ràng buộc danh tính workload |

Ví dụ:

```text
Client A == mTLS ==> Proxy P == mTLS ==> Service B
```

Nếu P dùng chứng thư của chính mình ở đoạn tới B, peer trực tiếp mà B xác thực là P. B không tự có bằng chứng handshake trực tiếp của A.

### 6.2. Chuyển danh tính qua proxy là một quan hệ tin cậy mới

Nếu B cần biết A, cần cơ chế để P cung cấp ngữ cảnh đã xác minh, với bảo vệ tính toàn vẹn, nguồn gửi và phạm vi sử dụng phù hợp.

Yêu cầu tối thiểu:

- P phải bỏ hoặc ghi đè các trường danh tính không đáng tin từ bên ngoài.
- B chỉ chấp nhận ngữ cảnh từ đúng proxy đã xác thực và được cấp quyền đại diện.
- Đường gọi trực tiếp không được giả làm đường qua proxy.
- Ngữ cảnh phải gắn với luồng hoặc request theo cơ chế đã thiết kế.
- Không coi một header chứa certificate hoặc tên client là bằng chứng tự xác thực.

mTLS ở đoạn P tới B chứng minh đối tác của đoạn đó và bảo vệ dữ liệu trên đoạn đó. Tính đúng của danh tính A phụ thuộc thêm vào việc P xác minh, tạo và chuyển ngữ cảnh đúng.

### 6.3. Đoạn cục bộ cũng cần ranh giới

Nếu TLS kết thúc tại sidecar và ứng dụng nhận dữ liệu qua kênh cục bộ, phải kiểm soát ai có thể dùng kênh đó và ai có thể tạo ngữ cảnh danh tính. “Cùng máy” không tự đồng nghĩa chỉ có workload dự định mới truy cập được.

Nếu có đoạn không mã hóa được chấp nhận trong một miền cô lập, cần mô tả miền, chủ thể truy cập và điều kiện bảo vệ. Không ghi toàn bộ đường truyền là mTLS khi có đoạn khác chưa nằm trong cam kết.

## 7. Cấp phát, bảo vệ khóa và vòng đời tin cậy

### 7.1. Bootstrap và cấp chứng thư

mTLS sử dụng một danh tính đã được cấp; nó không tự giải quyết ai được nhận danh tính đó.

Quy trình cấp phát cần kiểm tra nguồn danh tính workload, môi trường và quyền nhận certificate profile. CSR có thể chứng minh requester sở hữu khóa tương ứng, nhưng không tự chứng minh requester được quyền chọn SAN của service khác.

CA hoặc thành phần đăng ký phải ràng buộc nội dung cấp với policy. Không sao chép nguyên danh tính, thời hạn hay mục đích sử dụng do requester tự yêu cầu mà không kiểm tra.

Cần có audit cho cấp mới, cấp lại, đổi danh tính và thu hồi; khóa bootstrap không được trở thành một secret dùng chung vô thời hạn giữa mọi workload.

### 7.2. Khóa riêng và gia hạn

Yêu cầu nên nêu:

- Ai được tạo, lưu và sử dụng khóa.
- Có dùng khóa riêng theo workload hoặc instance không, và hệ quả khi một khóa bị lộ.
- Cách phân phối và nạp chứng thư mới mà không để lộ khóa.
- Khi nào bắt đầu gia hạn, xử lý lỗi và cảnh báo trước hết hạn.
- Phạm vi luân chuyển khóa, thời gian đồng tồn tại và cách loại bỏ bản cũ.

Ví dụ profile có chứng thư workload tối đa 24 giờ và bắt đầu gia hạn khi còn ít nhất 6 giờ. Đây là tham số minh họa, cần kiểm chứng với thời gian cấp phát và mô hình lỗi.

Nếu gia hạn thất bại, không được kéo dài hiệu lực bằng cách bỏ kiểm tra hết hạn. Cần chuyển sang trạng thái vận hành đã đặc tả và cảnh báo đủ sớm.

### 7.3. Thu hồi và dữ liệu trạng thái tin cậy

Có thể dùng cơ chế thu hồi chứng thư, danh sách chặn danh tính/serial, vô hiệu quyền sử dụng hoặc kết hợp với chứng thư ngắn hạn. Phải phân biệt:

- Chứng thư hết hạn.
- Khóa hoặc chứng thư bị thu hồi.
- Workload còn chứng thư nhưng mất quyền gọi một action.
- Trust anchor hoặc miền cấp phát không còn được chấp nhận.

Chứng thư ngắn hạn tạo cận theo thời hạn nhưng không tự đáp ứng mọi yêu cầu thu hồi nhanh hơn. Nếu mục tiêu là chặn trong 5 phút mà chứng thư còn hiệu lực nhiều giờ, cần cơ chế bổ sung.

Dữ liệu trạng thái có thể bị cũ hoặc không lấy được. Policy phải quy định độ cũ tối đa, nguồn thời gian và hành vi khi không đủ bằng chứng. Không để một lỗi truy vấn bị xử lý ngầm thành “chưa thấy bị thu hồi nên cho phép mãi”.

### 7.4. Kết nối đang mở và session resumption

Kiểm tra chứng thư khi handshake không đồng nghĩa chứng thư và quyền được kiểm tra lại trên từng request. Một kết nối dài có thể còn dùng được sau khi policy hoặc trạng thái tin cậy đã thay đổi nếu không có cơ chế bổ sung.

Session resumption cũng có thể dùng trạng thái phiên đã xác lập trước đó thay vì trình và kiểm tra lại toàn bộ chứng thư như một kết nối mới. Cần ràng buộc danh tính, thời hạn và trạng thái policy của phiên được tiếp tục.

Muốn đáp ứng cận thu hồi phải kiểm soát cả:

- Kết nối mới.
- Kết nối đang mở.
- Phiên được tiếp tục và vé phiên còn hiệu lực.
- Cache danh tính hoặc quyền ở proxy, client và ứng dụng.

Có thể cần kiểm tra trạng thái tại cổng request, đóng kết nối, vô hiệu trạng thái phiên hoặc giới hạn thời gian phù hợp. Nếu nền tảng không chứng minh được ràng buộc cần thiết cho resumption, phải tắt tính năng đó trong profile thay vì giả định an toàn.

Nếu dùng TLS early data, cần đánh giá khả năng phát lại theo đặc tính giao thức và ngữ nghĩa action. Ví dụ trong bài chọn không cho early data trên đường API được bảo vệ; mTLS không được xem là cơ chế tự chống lặp nghiệp vụ.

### 7.5. Chuyển CA và quản lý thời gian

Khi đổi CA, có thể cần thời gian tin đồng thời trust anchor cũ và mới. Phải xác định lúc bắt đầu, phạm vi, cách kiểm tra và khi nào loại bỏ miền cũ khỏi mọi thành phần.

Không giữ mọi CA từng dùng trong trust store vô thời hạn chỉ để tránh lỗi kết nối. Chứng thư hoặc root mới cũng không được cấp quyền rộng hơn ngoài ý muốn vì ánh xạ danh tính khác.

Đồng hồ ảnh hưởng kiểm tra thời hạn và thu hồi. Cần có nguồn thời gian, độ lệch chấp nhận và cảnh báo; không chữa lỗi đồng hồ bằng cách tắt kiểm tra ngày hiệu lực.

## 8. Ví dụ đặc tả: order API gọi inventory API

### 8.1. Bối cảnh và rủi ro

Service `order-api` ở production gọi `inventory-api` để đọc tình trạng còn hàng. Rủi ro `R-MTLS-01` là một workload giả mạo đối tác, một service không đủ quyền gọi action nhạy cảm hoặc một chứng thư bị thu hồi vẫn tiếp tục được dùng.

Ví dụ chọn:

- Kết nối trực tiếp hoặc một lớp giao tiếp được quản lý có cùng các cam kết đã xác định.
- TLS 1.3 là phiên bản duy nhất được profile này cho phép.
- Server có danh tính DNS `inventory.prod.example.internal`.
- Client có URI danh tính `urn:example:workload:production:order-api`.
- Trust anchor, issuer và certificate profile được quản lý riêng cho miền production này.
- Chứng thư workload tối đa 24 giờ; bắt đầu gia hạn khi còn ít nhất 6 giờ.
- Mục tiêu chặn sử dụng credential hoặc danh tính bị thu hồi không quá 5 phút từ lúc nguồn có thẩm quyền xác nhận việc thu hồi.
- Không cho phép early data trên đường API này.

Lựa chọn TLS 1.3 là điều kiện của ví dụ, không thay thế phân tích tương thích và profile mật mã của hệ thống khác.

### 8.2. Tập yêu cầu có thể kiểm chứng

| ID | Yêu cầu |
|---|---|
| SEC-MTLS-01 | Mọi đường tới API inventory thuộc phạm vi phải bắt buộc mTLS theo profile, gồm các replica và đường nội bộ. Không có listener hoặc route thay thế nhận cùng nghiệp vụ mà bỏ xác thực. |
| SEC-MTLS-02 | Profile chỉ cho TLS 1.3 và các tham số mật mã được quản lý theo phiên bản cấu hình đã kiểm chứng. Không tự fallback sang plaintext, bỏ xác thực hoặc chế độ không yêu cầu client certificate khi gặp lỗi. |
| SEC-MTLS-03 | Client phải xác minh chuỗi server tới trust anchor đúng miền và kiểm tra danh tính DNS `inventory.prod.example.internal`. Có chuỗi hợp lệ nhưng sai đối tác vẫn bị từ chối. |
| SEC-MTLS-04 | Server phải xác minh chuỗi client, issuer/profile đủ điều kiện và URI danh tính được policy chấp nhận. Không lấy identity từ một header client tự khai. |
| SEC-MTLS-05 | Profile phải kiểm tra thời hạn, mục đích sử dụng, thuật toán và trạng thái tin cậy. Chứng thư client bắt buộc đáp ứng profile client authentication; chứng thư server đáp ứng profile server authentication. |
| SEC-MTLS-06 | Chỉ action đọc tình trạng còn hàng được cấp cho `order-api` trong ví dụ. Các action như điều chỉnh tồn kho mặc định bị từ chối; quyền đối tượng và tenant vẫn được kiểm tra ở nghiệp vụ. |
| SEC-MTLS-07 | Nếu request thay người dùng, ngữ cảnh user/tenant phải được xác minh theo hợp đồng ủy quyền. Danh tính workload không tự cấp quyền cho một user ID tự khai. |
| SEC-MTLS-08 | Khi nguồn có thẩm quyền xác nhận thu hồi, hệ thống không được tiếp tục cho phép request nghiệp vụ mới dùng credential/danh tính đó sau 5 phút, kể cả trên kết nối đang mở hoặc phiên tiếp tục. |
| SEC-MTLS-09 | Dữ liệu trạng thái dùng cho kiểm tra không được cũ quá 180 giây theo mốc có thẩm quyền của snapshot. Không biết trạng thái hoặc quá cận thì không cấp phép request nghiệp vụ mới bằng dữ liệu đó. |
| SEC-MTLS-10 | Khóa riêng không dùng chung giữa các service hoặc môi trường ngoài policy. Gia hạn, luân chuyển và nạp chứng thư mới phải tự động có kiểm soát, có cảnh báo khi không giữ được khoảng đệm. |
| SEC-MTLS-11 | Session resumption nếu bật phải giữ đúng danh tính, giới hạn thời hạn và ràng buộc trạng thái policy cần thiết; nếu không chứng minh được thì tắt. Không chấp nhận early data trong profile này. |
| SEC-MTLS-12 | Nếu có proxy kết thúc TLS, phải kiểm chứng từng đoạn và nguồn ngữ cảnh danh tính. Bỏ/ghi đè header không đáng tin, không có đường giả làm proxy tin cậy. |
| SEC-MTLS-13 | Đổi CA hoặc trust store phải có kế hoạch đồng tồn tại, kiểm thử và thời điểm loại bỏ miền cũ. Sau hạn loại bỏ, miền cũ không tiếp tục được dùng qua cache hoặc trạng thái phiên ngoài cam kết. |
| SEC-MTLS-14 | Quyết định xác thực, phân quyền, thu hồi và đổi cấu hình phải có bằng chứng đủ điều tra; không ghi khóa riêng, token hoặc payload nhạy cảm dư thừa vào log. |

Mốc 180 giây được tính theo dữ liệu trạng thái do nguồn có thẩm quyền phát hành, không phải cứ tải lại một bản cũ là làm nó “mới”. Đạt mốc này cũng chưa tự chứng minh mục tiêu 5 phút; phải đo cả phát hành trạng thái, lan truyền và cổng thực thi.

Yêu cầu SEC-MTLS-08 là cam kết của toàn bộ thiết kế, không phải tính năng tự có ở một handshake mTLS. Kiến trúc phải chỉ rõ thành phần kiểm soát kết nối đang mở và resumption. Nếu không làm được, phải điều chỉnh thiết kế hoặc cam kết thay vì ghi đạt trên giấy.

### 8.3. Profile logic minh họa

```text
communication_policy: inventory-read-production
tls_versions: [TLS_1_3]
client_certificate: REQUIRED

expected_server_identity:
    dns: inventory.prod.example.internal

accepted_client_identity:
    uri: urn:example:workload:production:order-api
    trust_domain: production-workloads
    certificate_profile: order-client-v1

authorization:
    allowed_action: inventory.availability.read
    other_actions: DENY

early_data: DISABLED
unknown_identity: DENY
unknown_or_stale_required_trust_status: DENY_NEW_REQUEST
```

Đây là biểu diễn yêu cầu logic, không phải file cấu hình có thể dùng nguyên trạng với một thư viện. Trust anchor cụ thể, profile thuật toán, cơ chế trạng thái và mapping action phải có phiên bản và bằng chứng tương ứng trong triển khai.

## 9. Tiêu chí kiểm thử và bằng chứng

### 9.1. Kiểm thử các lớp khác nhau

Cần tách:

- Handshake: chứng thư, danh tính, giao thức và trust store có được kiểm tra đúng không.
- Phân quyền: peer đã xác thực có được làm đúng action không.
- Kiến trúc: proxy và đường thay thế có giữ ranh giới không.
- Vòng đời: hết hạn, thu hồi, gia hạn, chuyển CA và cache có đúng không.

Một bài kiểm thử chỉ thấy dữ liệu được mã hóa trên mạng không chứng minh các lớp còn lại.

### 9.2. Ma trận kiểm chứng ví dụ

| Ca kiểm thử | Thiết lập và kích thích | Kết quả mong đợi |
|---|---|---|
| T01 — Luồng hợp lệ | Client và server đúng profile, đúng đối tác, action được cấp | Kết nối và request thành công trong phạm vi quyền |
| T02 — Thiếu chứng thư client | Gọi API bắt buộc mTLS mà không trình client certificate | Không truy cập được nghiệp vụ; không tự chuyển sang anonymous |
| T03 — Không thuộc miền tin cậy | Dùng client hoặc server certificate từ CA không được tin cho luồng | Xác thực thất bại, không thử lại bằng cách bỏ kiểm tra |
| T04 — Sai server identity | Server có chuỗi hợp lệ nhưng SAN không khớp đối tác mong đợi | Client từ chối; không chỉ kiểm tra issuer |
| T05 — Sai mục đích hoặc danh tính client | Client có profile sai mục đích hoặc thiếu URI bắt buộc | Bị chặn tại tầng đã đặc tả; không lấy danh tính thay thế từ header |
| T06 — Không có khóa tương ứng | Trình certificate nhưng không thể chứng minh dùng đúng private key | Không hoàn tất xác thực như chủ thể đó |
| T07 — Chưa hiệu lực hoặc hết hạn | Điều khiển thời gian kiểm thử qua các biên validity | Không bỏ kiểm tra thời gian; lỗi và cảnh báo đúng nguyên nhân |
| T08 — Xác thực đúng, action sai | `order-api` gọi action điều chỉnh tồn kho | Phân quyền từ chối dù mTLS hợp lệ |
| T09 — Ngữ cảnh người dùng giả | Client hợp lệ gửi user/tenant không đủ bằng chứng ủy quyền | Không lấy mTLS làm căn cứ tin toàn bộ header nghiệp vụ |
| T10 — Thu hồi trên kết nối mới | Thu hồi peer, tiếp tục tạo kết nối và request | Không cho phép sau cận 5 phút theo mốc kiểm soát |
| T11 — Thu hồi trên kết nối cũ | Giữ kết nối mở từ trước, tiếp tục request sau thu hồi | Cận thu hồi vẫn được thực thi, không chỉ kiểm tra handshake mới |
| T12 — Session resumption | Tiếp tục phiên sau thu hồi, hết hạn hoặc đổi policy liên quan | Không khôi phục quyền cũ ngoài điều kiện; profile không hỗ trợ thì không bật |
| T13 — Trạng thái quá cũ | Làm nguồn cập nhật không khả dụng hoặc phát lại snapshot cũ | Không gia hạn độ mới giả; quá cận thì không cấp phép request mới |
| T14 — Giả danh qua proxy | Gửi header identity tự khai hoặc gọi đường sau proxy trực tiếp | Không được nhận là peer gốc đã xác minh |
| T15 — Luân chuyển và đổi CA | Nạp chứng thư mới, kiểm tra đồng tồn tại rồi loại CA cũ | Luồng hợp lệ hoạt động; miền đã loại không tiếp tục có hiệu lực |
| T16 — Giao thức hoặc đường thay thế | Thử profile ngoài allowlist, plaintext và listener khác | Không có fallback hoặc đường truy cập nghiệp vụ bỏ kiểm soát |
| T17 — Early data | Thử gửi sớm theo tính năng giao thức khi profile không cho phép | Không xử lý nghiệp vụ qua early data |
| T18 — Lỗi gia hạn hoặc cấp phát | Làm bước cấp mới thất bại và theo dõi trước expiry | Cảnh báo theo khoảng đệm; không kéo dài hiệu lực bằng cấu hình bỏ xác thực |

T03 cần bao gồm cả chứng thư tự ký không được cấp tin cậy. Nó không có nghĩa mọi trust anchor được quản lý chủ đích đều không hợp lệ vì tự ký.

Với T08, handshake có thể thành công rồi ứng dụng từ chối. Báo cáo phải phân biệt xác thực và phân quyền, không quy mọi lỗi thành “mTLS không hoạt động”.

Với T10–T13, phải kiểm tra mọi replica và điểm cache thuộc phạm vi. Đo thời gian từ sự kiện thu hồi có thẩm quyền, không chỉ từ lúc một worker cuối cùng nhận được bản cập nhật.

## 10. Liên kết rủi ro, yêu cầu và kiến trúc

| Rủi ro hoặc mục tiêu | Yêu cầu liên quan | Quyết định kiến trúc | Bằng chứng |
|---|---|---|---|
| R-MTLS-01: Giả mạo peer hoặc gọi nhầm server | SEC-MTLS-01–05 | Listener bắt buộc mTLS, trust store và kiểm tra danh tính đúng mục đích | T02–T07, T16 |
| Workload hợp lệ có quyền quá rộng | SEC-MTLS-06, 07 | Ánh xạ danh tính sang action, quyền đối tượng và ngữ cảnh ủy quyền | T08, T09 |
| Credential đã thu hồi tiếp tục dùng | SEC-MTLS-08, 09, 11 | Trạng thái tin cậy có cận, cổng request và kiểm soát phiên | T10–T13 |
| Danh tính bị giả qua proxy | SEC-MTLS-12 | Kiểm tra từng đoạn, proxy được cấp quyền đại diện và ngữ cảnh tin cậy | T14 |
| Gia hạn hoặc đổi CA gây mở rộng tin cậy ngoài ý muốn | SEC-MTLS-10, 13 | Cấp phát có policy, luân chuyển và kế hoạch kết thúc đồng tồn tại | T15, T18 |
| Không điều tra được quyết định | SEC-MTLS-14 | Log có cấu trúc, phiên bản profile và kết quả quyền | Đối chiếu handshake, request và control plane |

Thay proxy, thêm listener, bật resumption hoặc đổi hệ thống cấp chứng thư đều có thể ảnh hưởng cam kết. Cần cập nhật truy vết và kiểm chứng phần chịu tác động trong vòng đời phát triển.

Không dùng tên một công cụ mTLS như toàn bộ yêu cầu. Công cụ là lựa chọn triển khai; yêu cầu phải nói được peer nào được tin, danh tính nào được chấp nhận, action nào được phép và điều kiện nào làm quyền hết hiệu lực.

## 11. Logging, giám sát và vận hành

### 11.1. Dữ liệu điều tra

Một record có thể gồm:

```text
connection_reference hoặc request_reference
local_workload_reference
peer_identity_status = verified | unverified | none
verified_peer_identity nếu có
peer_certificate_reference
trust_domain, trust_profile_version
negotiated_protocol
authentication_result, authorization_result
reason_code
policy_version
trust_status_snapshot_version, snapshot_age
session_kind = full | resumed
timestamp
```

Không ghi một identity do đối tác chưa được xác minh trình ra như thể nó đã được xác thực. Nếu cần giữ dữ liệu đó để điều tra, phải đánh dấu rõ nguồn và mức tin cậy.

Certificate reference có thể dùng fingerprint hoặc tham chiếu serial kèm issuer phù hợp. Nó giúp tương quan một phiên cụ thể, còn workload identity giúp tương quan các lần gia hạn. Không thay định danh ổn định bằng fingerprint mà thiếu kế hoạch cho rotation, trừ khi pinning là lựa chọn có chủ đích.

Không ghi private key, secret bootstrap, session secret, token hoặc toàn bộ payload nghiệp vụ vào log thông thường. Quyền đọc log phải tương xứng với thông tin danh tính và cấu trúc hệ thống mà nó tiết lộ.

### 11.2. Chỉ số và cảnh báo

Các chỉ số hữu ích:

- Handshake thành công và thất bại theo nhóm nguyên nhân.
- Request bị từ chối vì action, identity hoặc trạng thái tin cậy.
- Thời gian còn lại của chứng thư, lỗi gia hạn và thời gian cấp mới.
- Độ cũ dữ liệu thu hồi và thời gian lan truyền thay đổi.
- Request tiếp tục dùng danh tính đã thu hồi sau mốc yêu cầu.
- Lỗi trust store, server identity, thời gian và chuyển CA.
- Tỷ lệ phiên tiếp tục, kết nối dài và các lần policy buộc dừng sử dụng.

Chỉ dùng nhãn có tập giá trị được kiểm soát. Một lượng lớn identity tự khai hoặc serial ngẫu nhiên không được tạo metric cardinality vô hạn. Log chi tiết cũng cần cận để một đợt handshake lỗi không làm đầy nơi lưu trữ.

mTLS không tự chặn tấn công làm cạn tài nguyên ở bước kết nối hoặc handshake. Cần giới hạn phù hợp về connection, thời gian, tốc độ và năng lực xử lý trước khi request được xác thực hoàn chỉnh.

### 11.3. Kiểm chứng hành vi lỗi và phục hồi

Quy trình vận hành cần chỉ rõ người quản lý CA/profile, người quản lý quyền workload, quyền đổi trust store và điều kiện rollback. Một thay đổi trust store có thể mở rộng miền được tin, không chỉ sửa lỗi kết nối.

Khi điều tra, đối chiếu chuỗi tin cậy, danh tính mong đợi, mục đích, thời gian, trạng thái và phiên bản policy. Không khắc phục bằng một cấu hình bỏ xác thực rồi quên thu hồi ngoại lệ.

Hiệu lực trên kết nối đang mở phải được nêu cả với hết hạn chứng thư lẫn thu hồi. Nếu cam kết không cho request mới dùng chứng thư đã hết hạn, lớp quản lý phiên hoặc cổng request phải thực thi điều đó; một lần kiểm tra ở handshake không đủ làm bằng chứng.

Diễn tập nên gồm lỗi cấp phát, lỗi nguồn trạng thái, đồng hồ sai ngoài mức chấp nhận, CA rotation và khôi phục sau gián đoạn. Bản ghi diễn tập cần có profile, số replica, các điểm kết thúc TLS, trạng thái phiên và mốc thời gian có thẩm quyền.

## 12. Các lỗi đặc tả thường gặp

| Phát biểu | Điểm thiếu | Cách viết rõ hơn |
|---|---|---|
| “Có HTTPS là đã có mTLS” | Có thể chỉ xác thực server | Nêu rõ yêu cầu client certificate và kiểm tra ở cả hai phía |
| “Chứng thư hợp lệ nên cho gọi mọi API” | Lẫn xác thực với phân quyền | Ánh xạ identity sang action, đối tượng và ngữ cảnh |
| “CA đúng là server đúng” | Chưa kiểm tra đối tác dự định | Ràng buộc server identity với endpoint mong đợi |
| “Client certificate có tên service là đủ” | Tên có thể ở field sai hoặc ngoài namespace | Định nghĩa issuer, profile, SAN và ánh xạ chính xác |
| “Header client identity là bằng chứng mTLS” | Caller có thể tự gửi | Chỉ tin ngữ cảnh từ thành phần đã xác thực, được cấp quyền và bảo vệ |
| “Proxy tới backend cũng TLS nên end-to-end giữ nguyên danh tính” | Mỗi đoạn có peer riêng | Mô tả điểm kết thúc và cơ chế chuyển ngữ cảnh gốc |
| “Chứng thư ngắn hạn giải quyết mọi thu hồi” | Cận expiry có thể dài hơn mục tiêu | Đặt mục tiêu và cơ chế chặn sử dụng có kiểm chứng |
| “Thu hồi chỉ cần thử kết nối mới” | Kết nối cũ và resumption có thể còn quyền | Thử mọi trạng thái phiên và cache liên quan |
| “CSR chứng minh được quyền chọn SAN” | Chỉ chứng minh một phần quan hệ với khóa | Kiểm tra quyền cấp danh tính bằng nguồn bootstrap có thẩm quyền |
| “Lỗi TLS thì thử lại không kiểm tra” | Tạo đường vượt xác thực | Giữ hành vi từ chối và xử lý lỗi vận hành theo policy |

## 13. Bài tập áp dụng

Bạn thiết kế giao tiếp giữa service xử lý hồ sơ và service lưu tài liệu, có một proxy nội bộ và nhiều tenant. Hãy viết tập yêu cầu gồm:

1. Điểm kết thúc TLS trên từng đoạn và peer thực sự của mỗi đoạn.
2. Danh tính server/client, trust domain, profile và nguồn cấp phát.
3. Quyền workload, quyền người dùng và ngữ cảnh ủy quyền cần xác minh.
4. Cách bảo vệ private key, gia hạn, thu hồi và chuyển CA.
5. Cận thu hồi trên kết nối mới, kết nối đang mở và phiên tiếp tục.
6. Hành vi khi nguồn trạng thái quá cũ, đồng hồ ngoài mức cho phép hoặc cấp chứng thư lỗi.
7. Ca kiểm thử sai server identity, client đúng danh tính nhưng sai action và giả header qua proxy.
8. Chuỗi truy vết từ rủi ro tới yêu cầu, kiến trúc và bằng chứng.

Tự kiểm tra: **Mỗi phía có xác thực đúng đối tác mong đợi không, và danh tính đó có được cấp đúng quyền ở thời điểm request diễn ra không?** Nếu chỉ chứng minh có mã hóa hoặc có một certificate trong kết nối, yêu cầu mTLS còn thiếu.
