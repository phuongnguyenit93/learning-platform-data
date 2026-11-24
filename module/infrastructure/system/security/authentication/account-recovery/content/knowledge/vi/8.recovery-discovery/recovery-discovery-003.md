# Phát hiện thiết bị đáng tin cậy trong khôi phục tài khoản

Khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, người dùng có thể vẫn còn một máy tính đã đăng nhập, một điện thoại khác hoặc một khóa bảo mật đã đăng ký. Những tài sản này có thể giúp họ tiếp tục xác thực mà không phải chuyển ngay sang một đường recovery yếu hơn.

Trong chương **Recovery Discovery** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **Discovering trusted devices** là quá trình xác định thiết bị hoặc khả năng xác thực nào còn có thể được sử dụng, rồi kiểm tra xem chúng đủ điều kiện cho hành động recovery nào.

Phát hiện một thiết bị không đồng nghĩa thiết bị đang an toàn, đang nằm trong tay người dùng thật hoặc được phép phê duyệt mọi thay đổi. Tên thiết bị, cookie quen thuộc, trạng thái online và bằng chứng mật mã có ý nghĩa khác nhau.

Sau bài học, người học có thể:

- Phân biệt thiết bị quen thuộc, session hiện có và authenticator đã đăng ký.
- Thiết kế các bước discovery mà không công khai danh sách thiết bị của tài khoản.
- Kiểm tra tính hợp lệ hiện tại thay vì dựa vào nhãn “đáng tin” trong quá khứ.
- Ràng buộc xác nhận từ thiết bị với đúng hồ sơ và hành động recovery.
- Xử lý thiết bị mất, bị đánh cắp, không phản hồi hoặc chỉ còn dấu vết cũ.

## 1. Mục tiêu của discovery: tìm khả năng còn dùng được

Giả sử Linh mất điện thoại chứa ứng dụng MFA. Cô vẫn còn một máy tính cá nhân đã đăng nhập và một khóa bảo mật đã đăng ký trước đó.

Một giao diện chỉ có nút “Gửi mã qua email để xóa MFA” sẽ bỏ qua các khả năng mạnh hơn đang tồn tại. Discovery giúp Linh nhận biết những lựa chọn phù hợp:

- Mở một thiết bị vẫn đang đăng nhập để xem yêu cầu recovery.
- Dùng authenticator đã đăng ký để xác thực lại.
- Dùng passkey còn khả dụng qua giao diện của hệ điều hành hoặc trình duyệt.
- Chọn một phương án khác đã được chính sách cho phép nếu không còn thiết bị phù hợp.

Nếu Linh còn một phương thức đăng nhập đủ mạnh, có thể chỉ cần đăng nhập bình thường rồi thực hiện thay đổi yếu tố theo chính sách. Không phải trường hợp mất một thiết bị nào cũng cần khôi phục toàn bộ tài khoản.

### Ba kết quả cần tách biệt

| Kết quả | Ý nghĩa |
|---|---|
| Phát hiện ứng viên | Có dấu hiệu một thiết bị, session hoặc authenticator có thể liên quan |
| Xác minh khả năng hiện tại | Có phản hồi hợp lệ hoặc session còn đáp ứng điều kiện |
| Cho phép hành động | Chính sách chấp nhận bằng chứng để thực hiện đúng thay đổi được yêu cầu |

Một bản ghi thiết bị từ sáu tháng trước chỉ là ứng viên. Một phản hồi từ thiết bị có thể chứng minh quyền sở hữu khóa hiện tại. Quyền xóa MFA hoặc đổi email vẫn cần quyết định riêng.

## 2. “Thiết bị đáng tin cậy” có thể đang chỉ những thứ khác nhau

Tên gọi này thường bị dùng cho nhiều cơ chế không tương đương.

| Đối tượng | Hệ thống thực sự biết gì? | Giới hạn |
|---|---|---|
| Trình duyệt được ghi nhớ bằng cookie | Có một giá trị được phát hành cho trình duyệt trước đó | Cookie có thể bị sao chép, mất hoặc đánh cắp |
| Session đã đăng nhập | Một session còn được máy chủ chấp nhận | Mức xác thực, độ mới và nguy cơ lộ session có thể không đủ cho recovery |
| Thiết bị cài ứng dụng đã đăng ký | Có một quan hệ đăng ký ứng dụng–tài khoản | Cần biết quan hệ đó được thiết lập và bảo vệ thế nào |
| Thiết bị có khóa riêng liên kết từ trước | Có thể yêu cầu chứng minh sở hữu khóa qua challenge | Phải kiểm tra khóa còn hiệu lực, mục đích và điều kiện xác nhận người dùng |
| Authenticator hoặc passkey đã đăng ký | Có một credential mà dịch vụ có thể xác minh | Một credential không nhất thiết tương ứng một thiết bị vật lý duy nhất |
| Dấu vân tay trình duyệt, IP hoặc vị trí quen thuộc | Có tín hiệu giống một môi trường từng dùng | Không phải bằng chứng mật mã về quyền sở hữu |

Không nên chuyển một tín hiệu yếu thành quyền recovery mạnh chỉ vì giao diện gọi nó là “thiết bị tin cậy”.

### Cookie ghi nhớ không phải khóa sở hữu thiết bị

Cookie “ghi nhớ thiết bị” thường là bearer credential: người có giá trị cookie có thể trình lại nó. Nó không tự chứng minh đang chạy trên cùng phần cứng.

Nếu một thiết kế cần ràng buộc thiết bị bằng khóa, phải có cơ chế đăng ký, lưu khóa và xác minh phù hợp. Không thể đạt điều đó chỉ bằng cách đặt tên cookie là `trusted_device`.

### Session còn hiệu lực không đồng nghĩa đủ quyền nhạy cảm

Một session có thể chỉ được xác thực bằng mật khẩu từ lâu. Một session khác có thể vừa được xác thực lại bằng yếu tố mạnh.

Cần đánh giá:

- Cách session được tạo và mức xác thực đã đạt.
- Thời điểm xác thực, không chỉ thời điểm hoạt động gần nhất.
- Session có bị thu hồi hoặc nằm trong sự cố hay không.
- Có cần xác thực lại trước hành động recovery cụ thể không.

Việc thiết bị liên tục gửi heartbeat hoặc gọi API không làm thời điểm xác thực mạnh tự trở nên mới.

### Passkey không luôn là định danh một thiết bị vật lý

Một passkey có thể được đồng bộ theo mô hình của nền tảng. Dịch vụ nên xác minh credential và các thuộc tính cần thiết, thay vì mặc định credential đó chỉ tồn tại trên chiếc điện thoại có tên trong hồ sơ.

Tên do người dùng đặt, thông tin loại authenticator hoặc dữ liệu vận chuyển là gợi ý về trải nghiệm; chúng không tự chứng minh một phần cứng cụ thể vẫn do đúng người giữ.

## 3. Mô hình đe dọa của bước discovery

Discovery có thể bị lạm dụng trước cả khi có thay đổi tài khoản.

| Nguy cơ | Ví dụ | Mục tiêu kiểm soát |
|---|---|---|
| Dò tài khoản và thiết bị | Nhập email rồi biết người đó dùng loại điện thoại nào | Không công khai inventory cho người chưa đủ quyền |
| Đánh cắp session hoặc cookie | Đối thủ trình dấu thiết bị quen thuộc | Không coi bearer credential yếu là bằng chứng độc lập mạnh |
| Thiết bị cũ đã bị mất | Thiết bị vẫn có nhãn trusted và session còn sống | Đánh giá tình trạng hiện hành và khả năng thu hồi |
| Gửi yêu cầu phê duyệt liên tục | Đối thủ làm người dùng bấm chấp nhận vì mệt mỏi | Giới hạn yêu cầu, thiết kế xác nhận có chủ đích |
| Trộn hồ sơ hoặc hành động | Phản hồi cho recovery mật khẩu bị dùng để đổi email | Ràng buộc challenge với đúng mục đích |
| Phát lại xác nhận | Dùng phản hồi cũ sau khi tài khoản đã thay đổi | Challenge mới, một lần, có hạn và kiểm tra phiên bản |
| Giả tên thiết bị | Đặt nhãn giống thiết bị của nạn nhân | Không dùng nhãn hoặc fingerprint làm căn cứ cấp quyền |
| Đối thủ kiểm soát thiết bị đáng tin | Người dùng bị mất thiết bị đang mở khóa | Không mặc định mọi phản hồi từ thiết bị cũ đều là ý định hợp pháp |

Một thiết bị có nguồn gốc đăng ký tốt vẫn có thể bị đánh cắp hoặc nhiễm mã độc. Chữ ký đúng chứng minh điều mà cơ chế khóa thực sự bảo đảm; nó không loại trừ mọi tình huống người khác đang điều khiển thiết bị.

Cần ghi rõ những giả định: khóa có được bảo vệ theo mô hình nào, có yêu cầu xác minh người dùng không, session có thể bị sao chép không và nền tảng đồng bộ ảnh hưởng đến tính độc lập ra sao.

## 4. Những nguồn discovery có thể sử dụng

### 4.1. Người dùng tự mở thiết bị còn đăng nhập

Đây là một cách hướng dẫn không cần công khai danh sách thiết bị trên trang chưa xác minh:

> Nếu bạn còn một thiết bị đã đăng nhập, hãy mở ứng dụng hoặc trang tài khoản trên thiết bị đó để xem các phương án hỗ trợ khôi phục.

Hướng dẫn có thể được hiển thị chung, không phụ thuộc việc tài khoản có thật sự có thiết bị nào. Khi thiết bị mở ứng dụng, session và quyền hiện tại mới được kiểm tra.

Thiết bị cũ có thể xem một yêu cầu gắn với tài khoản sau khi đạt điều kiện truy cập. Nhưng trước khi phê duyệt thay đổi nhạy cảm, vẫn có thể cần xác thực lại hoặc bằng chứng mạnh hơn.

### 4.2. Danh sách session và thiết bị trong vùng đã được phân quyền

Nếu người dùng đã có quyền xem quản lý thiết bị, có thể hiển thị các bản ghi phù hợp như tên, loại, hoạt động gần đây và trạng thái thu hồi.

Không nên xem mọi context recovery là đủ quyền đọc inventory. Ví dụ, xác nhận email có thể vẫn chưa đủ khi mô hình đe dọa bao gồm hộp thư bị xâm nhập.

Quyền xem danh sách cần được quyết định riêng theo mức nhạy cảm. Chỉ hiển thị thông tin tối thiểu cần cho lựa chọn.

### 4.3. Authenticator hoặc passkey khả dụng

Giao diện xác thực của nền tảng có thể giúp người dùng chọn credential còn sử dụng được. Dịch vụ xác minh kết quả của ceremony tương ứng, không tự quét tùy ý kho credential trên mọi thiết bị của người dùng.

Danh sách credential trong cơ sở dữ liệu của dịch vụ cũng không cho biết chắc credential nào hiện đang có mặt trên một thiết bị vật lý. Cần một phản hồi hợp lệ cho challenge mới để xác nhận khả năng sử dụng.

Nếu credential đã đáp ứng yêu cầu đăng nhập thông thường, ưu tiên đánh giá đường đăng nhập và quản lý yếu tố hợp lệ, thay vì ép người dùng qua luồng recovery yếu hơn.

### 4.4. Ứng dụng có khóa thiết bị đã đăng ký

Một ứng dụng có thể có cơ chế chứng minh sở hữu khóa được đăng ký từ trước. Khi dùng cho recovery, cần xác định:

- Ai đã có quyền đăng ký khóa vào tài khoản?
- Khóa được phép dùng cho mục đích nào?
- Có yêu cầu tương tác và xác minh người dùng khi phê duyệt không?
- Khi mất hoặc thay thiết bị, khóa được thu hồi thế nào?
- Một phản hồi được ràng buộc với hành động recovery cụ thể ra sao?

Không tự thiết kế một giao thức đơn giản như “ứng dụng gửi device ID là đủ”. Device ID thường là định danh tra cứu, không phải bí mật chứng minh sở hữu.

### 4.5. Tín hiệu môi trường

IP, vị trí gần đúng, loại trình duyệt hoặc lịch sử sử dụng có thể giúp xếp thứ tự ứng viên hay yêu cầu kiểm tra bổ sung.

Chúng không nên là điều kiện đủ cho việc xóa MFA, thêm passkey hoặc đổi kênh recovery. Người dùng thật có thể đổi mạng và đối thủ có thể tái tạo một số tín hiệu.

## 5. Thiết kế discovery theo quyền của người đang yêu cầu

Một mô hình hữu ích là tăng thông tin theo quyền đã có, thay vì trả toàn bộ inventory ngay từ đầu.

| Ngữ cảnh | Điều có thể cung cấp theo chính sách | Điều cần tránh |
|---|---|---|
| Chưa xác minh tài khoản | Hướng dẫn chung về thiết bị còn đăng nhập và phương án xác thực | Xác nhận tài khoản tồn tại, số lượng, tên hoặc vị trí thiết bị |
| Context recovery quyền hạn thấp | Các lựa chọn được cho phép trong đúng hồ sơ | Tự mở quyền quản lý thiết bị hoặc đọc thông tin nhạy cảm |
| Session đủ điều kiện xem inventory | Danh sách tối thiểu để nhận diện ứng viên | Trả bí mật, định danh nội bộ không cần thiết hoặc dữ liệu quá chi tiết |
| Thiết bị đang chứng minh khả năng | Challenge và nội dung hành động phù hợp | Dùng thành công ở bước discovery làm quyền toàn bộ tài khoản |
| Đã đạt điều kiện hành động | Thực hiện đúng kế hoạch được cho phép | Mở rộng sang đổi email, xóa mọi yếu tố hoặc cấp session ngoài phạm vi |

### Public response và inventory response là hai hợp đồng khác nhau

Một API công khai không nên trả:

~~~text
accountExists: true
trustedDeviceCount: 3
lastDeviceName: "Điện thoại của Linh"
lastSeenLocation: ...
~~~

Đổi tên trường hoặc che vài ký tự không giải quyết được việc thông tin đã bị tiết lộ.

Phản hồi công khai có thể đưa hướng dẫn chung và trạng thái tiếp nhận phù hợp. Inventory chỉ được lấy qua endpoint có kiểm tra quyền rõ ràng.

Không chỉ nội dung JSON mới làm lộ thông tin. Mã trạng thái, nhánh điều hướng, thông báo lỗi và khác biệt thời gian xử lý cũng cần được xem xét theo thiết kế chống dò tài khoản. Không nên tuyên bố chỉ cần thêm một khoảng chờ cố định là giải quyết mọi kênh tiết lộ.

### Danh sách che bớt thông tin vẫn cần phân quyền

Tên hệ điều hành, thời điểm hoạt động và vị trí có thể tiết lộ lịch sinh hoạt hoặc quan hệ sử dụng dịch vụ. Dữ liệu “đã che” không đồng nghĩa có thể cho mọi người xem.

Trạng thái “không có thiết bị phù hợp” cũng có thể tiết lộ cấu hình bảo mật. Cần quyết định thông điệp theo ngữ cảnh, không mặc định mọi kết quả discovery đều công khai.


## 6. Bản ghi trusted device cần giữ được nguồn gốc và phạm vi

Một bản ghi chỉ có `device_id`, `name` và `trusted=true` thường không đủ để đánh giá recovery.

Một mô hình minh họa có thể chứa:

~~~text
device_record_id
account_id
record_type
credential_or_key_reference
enrollment_source
enrolled_at
allowed_purposes
state
trust_version
last_successful_proof_at
last_seen_at
revoked_at
display_label
~~~

Với session, cần thêm hoặc tham chiếu các thuộc tính xác thực tương ứng. Không bắt buộc gộp session, credential và thiết bị vật lý vào cùng một bảng.

### Nguồn gốc đăng ký

Cần biết thiết bị hoặc khóa được liên kết với tài khoản bằng thẩm quyền nào. Một khóa mới được thêm chỉ từ recovery context yếu không thể tự trở thành bằng chứng đủ mạnh để hợp thức hóa chính recovery đó.

Một bước đăng ký không đáng tin không được sửa bằng việc thiết bị sau đó chứng minh sở hữu đúng khóa vừa đăng ký. Đối thủ cũng sở hữu khóa của họ.

### Phạm vi tin cậy

Một thiết bị được phép nhận thông báo chưa chắc được phép phê duyệt recovery. Một session được bỏ qua một bước đăng nhập trong một thời hạn nhất định chưa chắc được phép thay kênh recovery.

Các mục đích nên được đánh giá rõ, chẳng hạn:

- Nhận thông báo.
- Đăng nhập hoặc tiếp tục session.
- Thực hiện xác thực lại.
- Cung cấp bằng chứng cho recovery.
- Phê duyệt một thay đổi nhạy cảm theo chính sách.

Không nhất thiết lưu tất cả bằng cờ, nhưng quyết định quyền phải có cơ sở có thể giải thích.

### Trạng thái hiện hành và phiên bản

Khi thiết bị bị thu hồi, khóa thay đổi hoặc phạm vi quyền đổi, các challenge và quyết định cũ liên quan cần được kiểm tra lại.

Phiên bản của bản ghi giúp tránh dùng một phản hồi phát hành cho trạng thái cũ. Phiên bản bảo mật của tài khoản cũng có thể phát hiện việc hồ sơ recovery dựa vào cấu hình không còn hiện hành.

### Hoạt động gần đây không chứng minh đang ở trong tay người dùng

`last_seen_at` chỉ mô tả một sự kiện được quan sát. Nó có thể phản ánh session bị đánh cắp hoặc một tác vụ nền.

`last_successful_proof_at` cũng là dữ liệu lịch sử. Với hành động nhạy cảm, cần quyết định có phải tạo challenge mới và yêu cầu tương tác hiện tại hay không.

## 7. Quy trình từ ứng viên đến bằng chứng recovery

Một luồng tổng quát có thể gồm:

1. Tiếp nhận nhu cầu recovery và tạo hồ sơ quyền hạn thấp.
2. Hướng dẫn người dùng tìm thiết bị hoặc phương thức xác thực còn khả dụng.
3. Chỉ trả danh sách ứng viên khi người xem có quyền phù hợp.
4. Đánh giá ứng viên dựa trên nguồn đăng ký, trạng thái và mục đích.
5. Tạo challenge mới cho đúng hồ sơ và hành động.
6. Nhận bằng chứng hiện tại từ thiết bị hoặc authenticator.
7. Kiểm tra bằng chứng, ghi kết quả và tiêu thụ challenge.
8. Đánh giá toàn bộ điều kiện trước khi cấp lại quyền.

~~~mermaid
flowchart TD
    A["Nhu cầu recovery"] --> B["Hướng dẫn tìm phương thức còn dùng được"]
    B --> C["Ứng viên: session, ứng dụng hoặc authenticator"]
    C --> D{"Đủ điều kiện và còn hiệu lực?"}
    D -->|Không| E["Phương án khác theo chính sách"]
    D -->|Có| F["Challenge mới, đúng hồ sơ và hành động"]
    F --> G["Phản hồi và xác nhận phù hợp"]
    G --> H{"Bằng chứng hợp lệ?"}
    H -->|Không| E
    H -->|Có| I["Ghi bằng chứng vào hồ sơ"]
    I --> J["Kiểm tra điều kiện cấp lại quyền"]
~~~

Discovery không được tự chuyển sang bước hoàn tất chỉ vì một thiết bị phản hồi.

Nếu phương thức tìm được đủ cho đăng nhập bình thường, có thể chuyển người dùng sang đường xác thực đó. Cần bảo toàn phạm vi và trạng thái; không dùng chuyển hướng để biến một bằng chứng có mục đích hẹp thành quyền rộng hơn.

### Phát hiện không phải quét mạng

Dịch vụ không cần và thường không có cơ sở để quét mạng nội bộ hoặc thiết bị cá nhân nhằm tìm “máy của người dùng”. Nó dựa vào liên kết đã đăng ký, session được phép và cơ chế xác thực của nền tảng.

Không yêu cầu người dùng cài công cụ điều khiển từ xa hoặc cung cấp bí mật chỉ để chứng minh họ còn một thiết bị đáng tin.

## 8. Challenge và xác nhận phải nói rõ điều gì đang được cho phép

Một challenge recovery cần ràng buộc ít nhất các yếu tố liên quan:

- Tài khoản đích.
- Hồ sơ recovery.
- Hành động hoặc kế hoạch đang yêu cầu.
- Khóa hoặc credential được phép cung cấp bằng chứng.
- Mục đích, thời điểm phát hành và hạn hiệu lực.
- Trạng thái sử dụng và các phiên bản bảo mật cần kiểm tra.

Không nhận một phản hồi hợp lệ cho đăng nhập rồi tự phát lại nó ở endpoint xóa MFA. Nếu kết quả đăng nhập được dùng làm cơ sở cho hành động sau đó, phải thông qua session và chính sách cấp quyền phù hợp, không tái sử dụng challenge cũ sai mục đích.

### Nội dung hiển thị trên thiết bị xác nhận

Thông báo nên thể hiện rõ hành động, chẳng hạn:

> Có yêu cầu thay phương thức MFA. Nếu bạn đang tự thực hiện yêu cầu này, hãy mở ứng dụng để xem chi tiết và xác nhận.

Trong giao diện được bảo vệ, người dùng cần thấy đủ thông tin để hiểu:

- Đây là recovery cho tài khoản nào trong phạm vi được phép hiển thị.
- Thay đổi cụ thể nào sẽ được thực hiện.
- Có cấp quyền cho một trình duyệt hoặc thiết bị khác hay không.
- Cách từ chối và xử lý nếu họ không khởi tạo yêu cầu.

Tên thiết bị yêu cầu, vị trí hoặc thông tin trình duyệt có thể là dữ liệu suy đoán hoặc do bên yêu cầu cung cấp. Không trình bày chúng như bằng chứng chắc chắn về người đang ở phía bên kia.

### Tránh phê duyệt mù và mệt mỏi vì thông báo

Một nút “Cho phép” trong thông báo không có ngữ cảnh dễ khiến người dùng chấp nhận nhầm. Đối thủ cũng có thể gửi liên tục để gây áp lực.

Có thể dùng việc mở ứng dụng, tương tác chủ động hoặc đối chiếu thông tin giữa hai thiết bị để giảm nhầm lẫn. Tuy nhiên, đối chiếu một con số không tự chứng minh yêu cầu hợp pháp; đối thủ vẫn có thể lừa người dùng đọc hoặc chấp nhận nó.

Cần kết hợp giới hạn tần suất, phạm vi xác nhận rõ và một đường từ chối an toàn. Không gửi lại vô hạn chỉ vì chưa nhận được phản hồi.

### Thông báo không phải bearer credential

Không đặt bí mật đủ để phê duyệt recovery trực tiếp vào payload hiển thị trên màn hình khóa. Có thể gửi thông báo rằng có yêu cầu cần xem, còn thao tác xác nhận phải qua ngữ cảnh đã được xác thực và kiểm tra quyền.

Nếu dùng liên kết hoặc mã chuyển tiếp giữa thiết bị, nó cần phạm vi, hạn và ràng buộc riêng. Người có một URL không được mặc nhiên có quyền thay đổi tài khoản.

## 9. Mã giả chấp nhận bằng chứng từ thiết bị đã đăng ký

Ví dụ dưới đây minh họa một nhánh yêu cầu bằng chứng từ khóa đã đăng ký và được phép tham gia recovery. Nó không mô tả mọi loại session hay triển khai passkey.

~~~text
function acceptTrustedDeviceEvidence(challengeId, response, deviceContext):
    require validSubmissionContext(deviceContext)

    transaction:
        records = lockRelatedRecordsInConsistentOrder(challengeId)
        challenge = records.challenge
        attempt = records.attempt
        account = records.account
        device = records.device

        require challenge exists
        require challenge.purpose == "RECOVERY_DEVICE_EVIDENCE"
        require challenge.usedAt is null
        require now < challenge.expiresAt
        require attempt is active

        require attempt.accountId == account.id
        require challenge.recoveryAttemptId == attempt.id
        require device.accountId == account.id
        require device.id == challenge.deviceRecordId

        require deviceContext is authorized for this operation
        require device.state == "ACTIVE"
        require device.trustVersion == challenge.deviceTrustVersion
        require account.securityVersion == challenge.accountSecurityVersion

        require device.enrollmentSource satisfies currentPolicy
        require device.allowedPurposes include requiredPurpose(attempt)
        require evidenceIsNotBootstrappedFromThisWeakRecovery(device, attempt)

        verifiedProof = verifyServiceBoundResponse(
            response,
            challenge,
            registeredKey(device),
            currentPolicy
        )

        require verifiedProof is valid
        require verifiedProof.userVerification meets currentPolicy
        require response is bound to challenge.approvedActionPlan

        challenge.usedAt = now
        recordRecoveryEvidence(attempt, device, verifiedProof)
        recordEventWithoutSecrets("DEVICE_EVIDENCE_ACCEPTED", attempt)

    return nextPermittedRecoveryStep(attempt)
~~~

Trong một ceremony WebAuthn, việc xác minh cần kiểm tra challenge, ràng buộc với dịch vụ như RP ID và origin, chữ ký cùng các thuộc tính mà chính sách yêu cầu. Không lấy một cờ “đã xác minh người dùng” do trình duyệt tự khai ngoài bằng chứng để thay thế kiểm tra.

Với cơ chế khóa ứng dụng khác, cần dùng giao thức và cơ chế đăng ký được thiết kế phù hợp; không coi một chữ ký bất kỳ trên chuỗi dữ liệu bất kỳ là đủ.

### Những giới hạn của ví dụ

- Cách khóa dữ liệu và transaction phụ thuộc kiến trúc; cần xử lý cạnh tranh nhất quán.
- Bằng chứng từ thiết bị là đầu vào của quyết định, chưa phải quyền hoàn tất.
- Có thể cần kiểm tra lại độ mới và trạng thái ngay trước thay đổi credential.
- Nếu có nhiều dịch vụ, việc thu hồi và áp dụng quyền cần cơ chế phối hợp thực tế.
- Ghi log không bao gồm token, cookie, challenge chứa bí mật hoặc dữ liệu xác thực nhạy cảm.

Không phải mọi phương thức đều đáp ứng cùng mức bảo đảm. Một cookie ghi nhớ không thể đi qua nhánh này bằng cách giả làm một khóa đã đăng ký.

## 10. Thiết bị không phản hồi, bị mất hoặc chỉ còn dấu vết cũ

### Không phản hồi không phải từ chối

Điện thoại có thể hết pin, tắt mạng, gỡ ứng dụng hoặc không còn nhận thông báo. Không nhận phản hồi không chứng minh người dùng từ chối, cũng không chứng minh thiết bị bị chiếm.

Cần có thời hạn chờ, cách thử lại có giới hạn và đường chuyển sang phương án khác đã được chính sách cho phép.

Không tự hạ yêu cầu xác minh chỉ vì thiết bị không online. Một khoảng timeout không tạo ra bằng chứng mới.

### Thiết bị mất vẫn có session hoạt động

Nếu người dùng khai báo mất thiết bị, phải xem xét nguy cơ session hoặc khóa trên thiết bị đó nằm trong tay đối thủ. Nhãn trusted trong quá khứ không đủ để tiếp tục dùng nó như bên phê duyệt.

Việc yêu cầu xác minh người dùng trên authenticator có thể giảm một số rủi ro, nhưng không nên giả định mọi thiết bị mất đều an toàn hoặc mọi khóa đều có cùng thuộc tính bảo vệ.

Cần xử lý theo mô hình sự cố: hạn chế, thu hồi hoặc đánh giá lại đúng tài sản liên quan. Một người chưa được xác minh không nên có quyền xóa mọi thiết bị chỉ bằng cách khai báo “tôi làm mất”, vì điều đó cũng có thể được dùng để khóa nạn nhân.

### Thiết bị cũ và credential còn sử dụng được là hai vòng đời

Một bản ghi trình duyệt cũ có thể hết giá trị discovery, trong khi một credential vẫn hợp lệ theo chính sách riêng. Ngược lại, một thiết bị vẫn online có thể dùng một credential đã bị thu hồi.

Không tự đồng nhất các thao tác:

- Xóa nhãn thiết bị khỏi giao diện.
- Kết thúc session.
- Thu hồi quyền ứng dụng.
- Vô hiệu credential ở máy chủ.
- Xóa bản sao credential trên thiết bị.

Với credential được đồng bộ, một thao tác “xóa thiết bị” trong sản phẩm không tự bảo đảm mọi bản sao đã bị xóa. Dịch vụ cần biết chính xác quyền nào mình đang vô hiệu.

### Không còn ứng viên phù hợp

Có thể chuyển sang mã dự phòng, một phương thức độc lập khác hoặc quy trình xác minh phù hợp đã được thiết lập.

Nếu không có bằng chứng đủ mạnh, có thể phải chưa cấp lại quyền. Không biến việc không tìm thấy thiết bị thành lý do tự động dùng email để bỏ mọi MFA hoặc passkey.

## 11. Phối hợp hai thiết bị và xử lý gián đoạn

Một recovery có thể bắt đầu ở máy tính mới và được xác nhận trên điện thoại cũ. Hai ngữ cảnh cần được nối bằng hồ sơ và challenge phía máy chủ, không chỉ bằng một mã tài khoản do trình duyệt gửi lên.

### Ràng buộc yêu cầu khởi tạo và xác nhận

Phản hồi từ thiết bị cũ phải gắn với đúng hồ sơ, kế hoạch và quyền dự kiến cho thiết bị mới. Không dùng một xác nhận để mở khóa mọi hồ sơ đang chờ của cùng tài khoản.

Thiết bị mới chỉ được nhận trạng thái trong phạm vi context của nó. Một mã hồ sơ bị lộ không nên đủ để đọc kết quả hoặc lấy quyền.

### Mất mạng sau khi phê duyệt

Nếu thiết bị cũ gửi bằng chứng thành công nhưng mất phản hồi, dùng checkpoint và tra trạng thái bằng ngữ cảnh hợp lệ. Không cho challenge đã dùng hoạt động lại.

Nếu máy tính mới chưa nhận kết quả, nó có thể kiểm tra tiến độ theo nhịp có giới hạn. Việc refresh hoặc mở tab mới không tự tạo thêm phê duyệt hay bỏ qua điều kiện.

### Thu hồi trong lúc chờ

Một thiết bị có thể bị thu hồi hoặc tài khoản thay đổi sau khi challenge được phát hành. Cần kiểm tra trạng thái khi chấp nhận bằng chứng và trước khi áp dụng hành động.

Nếu một luồng recovery khác đã hoàn tất, hồ sơ cũ không được tiếp tục cấp quyền theo cấu hình trước đó.

### Không tự cấp session đầy đủ chỉ vì có phản hồi

Kết quả discovery hoặc xác nhận một bước có thể chỉ cho phép tiếp tục hồ sơ. Chính sách phải xác định riêng điều kiện cấp session, phạm vi quyền, thiết lập yếu tố mới và xử lý session cũ.

Nếu recovery xác nhận việc thiết bị cũ không còn đáng tin, kế hoạch cần xử lý quyền tồn tại của thiết bị đó, không chỉ thêm một thiết bị mới.

## 12. Chống lạm dụng và bảo vệ dữ liệu thiết bị

### Giới hạn yêu cầu

Cần kiểm soát việc khởi tạo discovery, gửi thông báo, tạo challenge và kiểm tra trạng thái. Có thể kết hợp tài khoản, hồ sơ, thiết bị và nguồn yêu cầu.

Giới hạn chỉ theo tài khoản có thể bị dùng để chặn người dùng thật. Giới hạn chỉ theo IP có thể ảnh hưởng người dùng chung mạng hoặc bị né. Cần cân nhắc cả nguy cơ chiếm đoạt và từ chối dịch vụ.

Một người chưa xác minh không nên có khả năng gửi liên tục thông báo recovery tới mọi thiết bị của nạn nhân. Có thể ưu tiên hướng dẫn người dùng tự mở ứng dụng, hoặc chỉ cho gửi thông báo khi đạt điều kiện khởi tạo phù hợp.

### Tối thiểu hóa inventory

Tên thiết bị, vị trí, địa chỉ mạng và thời điểm hoạt động cần được bảo vệ theo vai trò và mục đích. Không đưa chúng vào URL công khai, thông báo trên màn hình khóa hoặc công cụ phân tích không cần thiết.

Tên thiết bị có thể do người dùng nhập. Cần hiển thị an toàn, không diễn giải như mã hoặc HTML và không dùng nó làm bằng chứng danh tính.

### Dấu vết cần thiết

Các sự kiện hữu ích gồm:

- Discovery được khởi tạo và quyền xem inventory được kiểm tra.
- Ứng viên được chọn hoặc bị loại theo mã lý do.
- Challenge phát hành, hết hạn, bị thu hồi hoặc được chấp nhận.
- Bằng chứng được gắn với hồ sơ.
- Quyết định cấp quyền và kết quả thu hồi liên quan.

Không ghi cookie, token, khóa riêng hoặc bí mật phê duyệt. Dùng định danh nội bộ và dữ liệu tối thiểu; việc điều tra không cần một bản sao đầy đủ của mọi phản hồi xác thực trong log thông thường.

### Đọc số liệu theo đúng giai đoạn

Có thể đo tỷ lệ tìm được ứng viên, tỷ lệ cung cấp bằng chứng hợp lệ, thời gian chờ và tỷ lệ phải chuyển phương án. Đây là các đơn vị khác nhau.

“Tìm được thiết bị” không đồng nghĩa “recovery thành công”. Tỷ lệ phê duyệt cao cũng có thể do thông báo gây nhầm lẫn hoặc kiểm soát bị bỏ qua.

Cần kết hợp các số liệu với sự cố, phản hồi người dùng và chất lượng bằng chứng. Không có báo cáo chiếm đoạt ngay không chứng minh cơ chế an toàn, vì phát hiện sự cố có thể chậm.

## 13. Các tình huống dùng để kiểm tra thiết kế

Bảng sau là các tình huống rà soát của bài học, không phải kết quả kiểm thử một hệ thống cụ thể.

| Tình huống | Kết quả mong đợi |
|---|---|
| Người lạ nhập email ở trang recovery | Không nhận tên, số lượng hoặc vị trí thiết bị |
| Có cookie ghi nhớ nhưng không có bằng chứng mạnh theo yêu cầu | Không tự được xóa MFA hoặc đổi kênh recovery |
| Session cũ vẫn hoạt động | Kiểm tra mức xác thực, độ mới và nguy cơ lộ trước hành động nhạy cảm |
| Thiết bị gửi heartbeat | Chỉ cập nhật tín hiệu hoạt động, không coi là xác nhận recovery |
| Credential hợp lệ còn khả dụng | Có thể dùng đường xác thực phù hợp thay vì ép qua recovery yếu hơn |
| Passkey được đồng bộ sang nơi khác | Xác minh credential theo mô hình thực tế, không giả định một thiết bị vật lý |
| Thiết bị chỉ có quyền nhận thông báo | Không được tự có quyền phê duyệt thay đổi |
| Một khóa vừa được thêm từ recovery context yếu | Không được dùng để hợp thức hóa quyền recovery trước đó |
| Thiết bị bị thu hồi sau khi challenge phát hành | Phản hồi cũ không tiếp tục cấp quyền trái trạng thái hiện hành |
| Phản hồi hợp lệ cho hồ sơ A được trình ở hồ sơ B | Bị từ chối vì sai ràng buộc |
| Phê duyệt thay MFA bị dùng để đổi email | Bị từ chối vì sai hành động |
| Challenge được gửi hai lần hoặc đồng thời | Chỉ được chấp nhận một lần |
| Thiết bị không phản hồi | Có timeout và phương án khác, không tự bỏ xác minh |
| Người yêu cầu gửi nhiều thông báo | Bị kiểm soát mà không dễ khóa nạn nhân vô thời hạn |
| Mất phản hồi sau khi chấp nhận bằng chứng | Tiếp tục bằng checkpoint, không hồi sinh challenge |
| Xóa nhãn thiết bị trên giao diện | Không tuyên bố session và credential đều đã bị thu hồi nếu chưa thực hiện |
| Không còn thiết bị phù hợp | Chuyển theo chính sách; có thể chưa cấp quyền nếu thiếu bằng chứng |

## 14. Áp dụng lại vào tình huống của Linh

Linh mất điện thoại chứa MFA, nhưng còn máy tính đã đăng nhập và khóa bảo mật đã đăng ký.

Một hành trình phù hợp có thể là:

1. Trang recovery đưa hướng dẫn chung về thiết bị hoặc phương thức còn dùng được, không công khai inventory.
2. Linh mở tài khoản trên máy tính cũ. Dịch vụ kiểm tra session và không coi cookie quen thuộc là toàn bộ bằng chứng.
3. Nếu khóa bảo mật đáp ứng yêu cầu, Linh thực hiện xác thực phù hợp bằng challenge mới.
4. Kết quả được gắn với đúng hồ sơ và hành động thay MFA; không tự cho đổi mọi thông tin bảo mật.
5. Trước khi hoàn tất, dịch vụ kiểm tra lại trạng thái tài khoản và những quyền cần xử lý trên điện thoại bị mất.
6. Khi thay đổi thành công, session, yếu tố cũ và quyền tồn tại được xử lý theo kế hoạch, cùng thông báo phù hợp.

Nếu máy tính chỉ có một cookie cũ hoặc điện thoại đã mất là ứng viên duy nhất, hệ thống không nên gắn nhãn “đã xác minh” chỉ vì bản ghi thiết bị vẫn còn.

Điều cần giữ là sự khác nhau giữa **tìm thấy dấu vết của một thiết bị**, **xác minh khả năng hiện tại** và **cho phép hành động cụ thể**. Discovery an toàn giúp người dùng tìm đúng bằng chứng còn dùng được, đồng thời giữ ba quyết định đó tách bạch trong cách cấp quyền.
