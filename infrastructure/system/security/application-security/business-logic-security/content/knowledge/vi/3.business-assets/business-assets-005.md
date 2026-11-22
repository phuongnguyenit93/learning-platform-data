# Dữ liệu cá nhân và sự đồng ý — Personal data and consent

## 1. Hai tài sản cần được bảo vệ cùng nhau

Trong chương **Business Assets** của học phần **Business Logic Security**, dữ liệu cá nhân là tài sản cần kiểm soát cả việc truy cập lẫn cách sử dụng. Một hệ thống có thể không làm lộ bảng dữ liệu nhưng vẫn xử lý sai nghiệp vụ: gửi quảng cáo sau khi người dùng đã rút đồng ý, dùng địa chỉ giao hàng để lập danh sách tiếp thị hoặc xuất dữ liệu của một người theo yêu cầu chưa được xác minh.

**Sự đồng ý** là một quyết định có phạm vi của chủ thể hoặc người đại diện được xác minh theo chính sách. Bản ghi đồng ý cũng là tài sản nghiệp vụ: sửa sai bản ghi này có thể mở quyền xử lý dữ liệu mà chủ thể chưa cho phép, hoặc làm mất bằng chứng về một quyết định đã có.

Bài học tập trung vào thiết kế kỹ thuật và các chính sách minh họa. Không giả định mọi hoạt động xử lý dữ liệu đều dựa trên sự đồng ý. Với từng hoạt động, tổ chức cần xác định cơ sở xử lý và quy tắc áp dụng; hệ thống phải thực thi đúng lựa chọn đó, thay vì dùng một cờ đồng ý làm giấy phép chung.

Sau bài này, bạn cần có khả năng:

- Nhận diện dữ liệu cá nhân, quan hệ chủ thể và ranh giới sử dụng.
- Phân biệt quyền truy cập của người vận hành với quyền xử lý theo mục đích.
- Mô hình hóa đồng ý theo chủ thể, mục đích, phạm vi, phiên bản và thời gian.
- Bảo vệ việc cấp, rút lại và thực thi đồng ý trước request giả mạo, retry, cạnh tranh và dữ liệu đồng bộ chậm.
- Kiểm thử kết quả nghiệp vụ, bao gồm tác vụ đã xếp hàng và hệ thống nhận dữ liệu phía sau.

## 2. Nhận diện dữ liệu và quan hệ với chủ thể

Dữ liệu cá nhân không chỉ là họ tên hoặc số định danh. Một giá trị có thể liên quan tới một người khi kết hợp với dữ liệu khác trong bối cảnh hệ thống.

| Nhóm dữ liệu | Ví dụ | Rủi ro nghiệp vụ cần xem xét |
| --- | --- | --- |
| Thông tin liên hệ | Email, số điện thoại, địa chỉ giao nhận | Dùng ngoài mục đích, gửi nhầm người, thay thông tin để chiếm luồng nhận dữ liệu |
| Định danh trong hệ thống | Mã tài khoản, mã khách hàng, mã thiết bị | Liên kết hoạt động hoặc chọn sai chủ thể khi xử lý |
| Giao dịch và hành vi | Đơn hàng, lịch sử sử dụng, vị trí giao nhận | Suy luận hoặc phân loại người dùng ngoài phạm vi đã xác định |
| Sở thích và hồ sơ suy ra | Nhóm quan tâm, điểm phân loại, dự đoán hành vi | Tạo dữ liệu mới nhưng không áp dụng kiểm soát tương ứng |
| Chứng từ và thông tin có mức nhạy cảm cao | Hồ sơ xác minh, tài liệu hỗ trợ, thông tin sức khỏe trong sản phẩm phù hợp | Phạm vi tiếp cận và hậu quả sai mục đích lớn hơn |
| Bằng chứng quyết định | Lịch sử đồng ý, rút lại, phiên bản thông báo | Giả mạo quyền xử lý hoặc tiết lộ lựa chọn riêng tư |

Không nên mặc nhiên coi dữ liệu đã mã hóa hoặc thay bằng mã giả là vô danh. Nếu còn khả năng liên kết với chủ thể bằng khóa hoặc bảng ánh xạ, hệ thống vẫn phải kiểm soát quan hệ đó. Mã hóa giúp bảo vệ bí mật ở một số ranh giới; nó không quyết định dữ liệu có được dùng cho chiến dịch mới hay không.

### 2.1. Một tài khoản không luôn tương đương một chủ thể

Các quan hệ thường gặp:

- Một người có nhiều tài khoản hoặc nhiều địa chỉ liên hệ.
- Một tài khoản doanh nghiệp thao tác cho nhiều người.
- Người mua nhập thông tin người nhận quà.
- Nhân viên hỗ trợ thay mặt khách hàng.
- Người đại diện được xác minh thao tác trong một phạm vi nhất định.

Biết email không chứng minh sở hữu email; sở hữu tài khoản không tự chứng minh được quyền quyết định mọi dữ liệu được nhập vào tài khoản. Nếu khách mua hàng nhập số điện thoại của người nhận, không được tự suy ra người nhận đã đồng ý nhận tiếp thị.

Mô hình nên tách định danh chủ thể, tài khoản đăng nhập, thông tin liên hệ và quan hệ đại diện. Thông tin liên hệ có thể thay đổi hoặc được tái cấp; không nên dùng riêng chuỗi số điện thoại làm bằng chứng cho mọi quyết định lịch sử.

### 2.2. Phạm vi tenant là một phần của quan hệ

Cùng một người có thể xuất hiện trong nhiều tenant với quan hệ khác nhau. Quyền hoặc đồng ý được ghi nhận trong tenant T1 không mặc nhiên có hiệu lực trong T2.

Nếu có cơ chế chia sẻ giữa các đơn vị hoặc dịch vụ, cần mô tả rõ bên sử dụng, mục đích, phạm vi dữ liệu và căn cứ cho việc chia sẻ. Không suy ra quyền chia sẻ chỉ vì hai dịch vụ cùng thuộc một hạ tầng.

## 3. Tách quyền truy cập khỏi quyền sử dụng theo mục đích

Có ít nhất ba câu hỏi độc lập:

1. **Actor có được gọi chức năng và tác động lên đối tượng này không?**
2. **Hoạt động xử lý có đúng mục đích, phạm vi và cơ sở đã được xác định không?**
3. **Các điều kiện hiện tại, như đồng ý còn hiệu lực hoặc thời hạn sử dụng, có còn đúng không?**

Một nhân viên có quyền xem địa chỉ để xử lý giao hàng không tự có quyền dùng địa chỉ đó cho mọi chiến dịch. Ngược lại, khách hàng đã đồng ý tiếp thị không có nghĩa mọi nhân viên đều được tải toàn bộ dữ liệu của họ.

| Hoạt động | Kiểm tra quyền theo đối tượng | Kiểm tra điều kiện xử lý |
| --- | --- | --- |
| Xem hồ sơ hỗ trợ | Nhân viên thuộc đúng tenant, được phân công đúng hồ sơ | Chỉ dùng trường cần cho tác vụ hỗ trợ |
| Gửi chiến dịch email | Tài khoản dịch vụ được chạy chiến dịch đã phê duyệt | Đúng mục đích, kênh, phạm vi và trạng thái đồng ý nếu hoạt động dựa vào đồng ý |
| Xuất dữ liệu cho chủ thể | Đúng người hoặc đại diện có thẩm quyền, đúng chủ thể mục tiêu | Đúng phạm vi yêu cầu và điều kiện xác minh, chuyển giao |
| Rút lại đồng ý | Người gọi có quyền quản lý lựa chọn của chủ thể đó | Chuyển đúng trạng thái và ngăn sử dụng tiếp theo theo chính sách |
| Gửi thông báo giao dịch | Dịch vụ có quyền trên đơn và người nhận liên quan | Nội dung thực sự thuộc luồng giao dịch theo chính sách, không bị đổi nhãn để chèn tiếp thị |

**Sự đồng ý không thay thế phân quyền. Phân quyền cũng không thay thế kiểm tra mục đích.** Hai cơ chế cần gặp nhau ở nơi dữ liệu được đọc, xuất, gửi hoặc cấp cho hệ thống khác.

Không cho client tự gửi một chuỗi như `purpose=ORDER_SERVICE` rồi được bỏ kiểm tra đồng ý. Mục đích phải gắn với chức năng và chính sách đã được máy chủ phê duyệt. Nếu một endpoint thực sự phục vụ nhiều mục đích, mỗi đường phải có điều kiện riêng và không cho người gọi chọn đường dễ hơn để thực hiện cùng một hành vi bị cấm.

### 3.1. Không dùng thất bại của consent làm đường chuyển cơ sở tùy ý

Giả sử chiến dịch M được thiết kế dựa trên đồng ý. Khi không có đồng ý, chương trình không được tự gán một cơ sở khác chỉ để tiếp tục gửi.

Những hoạt động xử lý dựa trên cơ sở khác cần được định nghĩa độc lập với điều kiện, quyền hạn và mục đích riêng. Thiết kế nên làm rõ điều đó ngay trong danh mục hoạt động xử lý, thay vì có nhánh dự phòng “không consent thì vẫn cho phép”.

Tương tự, rút lại đồng ý tiếp thị không nhất thiết hủy mọi quan hệ giao dịch hoặc mọi nghĩa vụ lưu trữ. Mỗi hoạt động cần được đánh giá theo chính sách thực sự áp dụng, không dùng một cờ để bật hoặc tắt toàn bộ hệ thống.

## 4. Ví dụ xuyên suốt: rút đồng ý khi email đã xếp hàng

Xét một chính sách minh họa:

- Gửi email tiếp thị cần đồng ý cho mục đích `MARKETING_EMAIL`.
- Đồng ý cho email không tự cho phép SMS hoặc cung cấp dữ liệu cho một đối tác khác.
- Rút lại đồng ý có hiệu lực trong hệ thống có thẩm quyền khi transaction ghi nhận rút lại đã commit.
- Tác vụ chưa qua ranh giới cấp phép gửi cuối cùng phải kiểm tra trạng thái hiện tại.
- Tác vụ đã bàn giao ra ngoài cần theo dõi và áp dụng khả năng hủy hoặc ngừng xử lý mà tích hợp hỗ trợ; không hứa thu hồi được một email đã gửi.

Luồng có lỗi:

~~~text
09:00  Job lấy danh sách người đồng ý và tạo 10.000 tác vụ.
09:05  Người dùng U1 rút lại đồng ý; bản ghi chính đã cập nhật.
09:10  Worker gửi cho U1 dựa trên danh sách chụp lúc 09:00.
~~~

API rút lại có thể đã trả thành công đúng kỹ thuật. Tuy nhiên, mục tiêu nghiệp vụ bị phá nếu worker coi snapshot cũ là quyền sử dụng còn hiệu lực.

Cần phân biệt hai việc:

- Danh sách 09:00 xác định ứng viên để xử lý.
- Kiểm tra gần điểm gửi xác định tác vụ đó có còn được phép thực hiện không.

Snapshot, cache hoặc message mang một cờ `consent=true` không tự có hiệu lực vô thời hạn.

### 4.1. Cần ràng buộc quyết định với đúng phạm vi

Một quyền xử lý theo đồng ý thường cần định danh được:

~~~text
tenant
chủ thể
mục đích
phạm vi dữ liệu hoặc loại xử lý
kênh và bên nhận theo chính sách
phiên bản nội dung được chấp thuận
trạng thái hiện tại
phiên bản quyết định
thời điểm và điều kiện hiệu lực
~~~

Không nhất thiết tất cả đều là các cột trong một bảng. Có thể tham chiếu danh mục mục đích và một snapshot bất biến. Điều bắt buộc là bên thực thi hiểu đúng phạm vi, không mở rộng ý nghĩa bằng cách chỉ nhìn một boolean.

### 4.2. Thay đổi mục đích không phải thay tên nhãn

Nếu phiên bản thông báo mới thêm bên nhận dữ liệu hoặc thêm hoạt động phân tích, cần đánh giá liệu quyết định cũ có bao phủ thay đổi đó theo chính sách hay không. Không đơn giản cập nhật nhãn trên giao diện rồi coi mọi bản ghi cũ đã chấp thuận nội dung mới.

Mặt khác, không phải mọi sửa dấu câu đều buộc tạo lại mọi đồng ý. Cần phân loại thay đổi có ảnh hưởng và quy tắc tương thích rõ ràng, cùng phiên bản có thể truy nguyên.

## 5. Bản ghi đồng ý và bằng chứng nguồn gốc

Một bản ghi hiện tại giúp kiểm tra nhanh. Lịch sử bất biến giúp hiểu vì sao hệ thống tin rằng quyết định hiện tại hợp lệ. Hai nhu cầu này nên được thiết kế cùng nhau.

| Thành phần | Nội dung minh họa | Mục đích |
| --- | --- | --- |
| Khóa phạm vi | Tenant, chủ thể, mục đích và phạm vi | Tránh dùng nhầm quyết định |
| Quyết định | Cấp, từ chối, rút lại hoặc yêu cầu xác nhận lại | Không diễn giải thiếu dữ kiện thành đồng ý |
| Phiên bản | Revision do hệ thống có thẩm quyền quản lý | Ngăn ghi đè bằng quyết định cũ |
| Bằng chứng thông báo | Mã và phiên bản nội dung đã hiển thị, tham chiếu snapshot | Biết điều gì đã được đưa ra cho người dùng |
| Chủ thể thao tác | Người quyết định, tài khoản và quan hệ đại diện đã xác minh nếu có | Giải thích thẩm quyền |
| Nguồn tiếp nhận | Kênh, workflow hoặc tham chiếu yêu cầu | Phân biệt lựa chọn trực tiếp, nhập liệu và tích hợp |
| Hiệu lực | Thời điểm ghi nhận, thời hạn nếu có, điều kiện liên quan | Kiểm tra quyết định hiện còn dùng được |
| Dấu vết vận hành | Mã tương quan, tác vụ đồng bộ và xác nhận từ bên nhận | Theo dõi việc thực thi |

Không cần mặc nhiên ghi địa chỉ IP, dấu vân tay thiết bị hoặc toàn bộ nội dung request để tạo “bằng chứng mạnh”. Chỉ lưu dữ liệu cần thiết cho mục tiêu đã xác định, bảo vệ nó và có thời gian lưu tương ứng.

Một bản ghi phía máy chủ có `accepted=true` chỉ chứng minh hệ thống đã ghi nhận giá trị đó theo cơ chế của mình. Độ tin cậy còn phụ thuộc việc người thao tác có được xác minh, nội dung có được hiển thị đúng và workflow có cho phép lựa chọn có ý nghĩa không. Hash hoặc chữ ký không sửa được một giao diện mặc định tích sẵn rồi ghi nhận như lựa chọn mới.

Khi nhập dữ liệu từ hệ thống cũ, “không có cột consent” không đồng nghĩa “đã đồng ý”. Cần giữ trạng thái không xác định hoặc chưa cấp theo mô hình và xử lý bằng chính sách chuyển đổi đã được phê duyệt.

## 6. Invariant và vòng đời của quyết định đồng ý

Các invariant quan trọng cho chính sách minh họa:

~~~text
Không có đồng ý hợp lệ không được diễn giải thành đã đồng ý.
Đồng ý chỉ bao phủ đúng chủ thể, tenant, mục đích và phạm vi đã xác định.
Chỉ chủ thể hoặc bên được xác minh thẩm quyền mới được thay đổi lựa chọn.
Quyết định cũ không được ghi đè quyết định mới chỉ vì được gửi đến sau.
Rút lại phải tác động tới những đường xử lý dựa trên đồng ý đó.
Tạo lại tài khoản hoặc nhập lại danh bạ không được tự phục hồi đồng ý đã rút.
Mỗi tác động xử lý phải có căn cứ còn hiệu lực theo chính sách của nó.
~~~

Một state machine minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> NOT_GRANTED
    NOT_GRANTED --> GRANTED: Lựa chọn mới có bằng chứng phù hợp
    GRANTED --> WITHDRAWN: Yêu cầu rút lại được xác minh
    GRANTED --> EXPIRED: Hết hạn theo chính sách
    GRANTED --> RECONFIRM_REQUIRED: Thay đổi cần xác nhận lại
    WITHDRAWN --> GRANTED: Lựa chọn cấp lại mới và hợp lệ
    EXPIRED --> GRANTED: Lựa chọn mới và hợp lệ
    RECONFIRM_REQUIRED --> GRANTED: Chấp thuận nội dung áp dụng
    RECONFIRM_REQUIRED --> WITHDRAWN: Rút lại
~~~

`NOT_GRANTED`, `WITHDRAWN`, `EXPIRED` và `RECONFIRM_REQUIRED` đều không cấp quyền cho hoạt động đang yêu cầu một đồng ý có hiệu lực. Chúng vẫn có ý nghĩa lịch sử khác nhau.

Không đặt trạng thái đích từ JSON vào entity mà bỏ qua điều kiện chuyển trạng thái. Chẳng hạn, endpoint cập nhật hồ sơ không được cho phép gửi `consentStatus=GRANTED` để thay thế toàn bộ quy trình ghi nhận lựa chọn.

### 6.1. Revision giúp phân biệt mới cũ

Ví dụ:

~~~text
revision 41: GRANTED
revision 42: WITHDRAWN
~~~

Một message cũ mang revision 41 đến sau không được làm bản sao quay về `GRANTED`. Bên nhận cần áp dụng quy tắc phiên bản theo đúng khóa phạm vi và bỏ qua bản cập nhật cũ.

Không chỉ dùng timestamp do client khai hoặc thời điểm message đến làm thứ tự quyết định. Đồng hồ khác nhau, retry và độ trễ mạng có thể đảo thứ tự. Revision phải do nguồn có thẩm quyền quản lý với cơ chế cập nhật nhất quán.

Nếu nhiều nguồn có quyền thay đổi cùng quyết định, cần xác định nguồn chủ hoặc một giao thức giải quyết xung đột rõ ràng. Tăng bộ đếm riêng ở mỗi nguồn rồi so sánh số lớn hơn không tạo ra thứ tự chung đáng tin cậy.

### 6.2. Rút lại và cấp lại phải được phân biệt

Retry yêu cầu cấp cũ không phải là một lựa chọn cấp lại mới. Để cấp lại sau khi đã rút, cần một thao tác mới có bằng chứng phù hợp với trạng thái hiện tại.

Một cách thiết kế là ràng buộc thao tác cấp với phiên bản nền, nội dung thông báo và ngữ cảnh lựa chọn. Nếu biểu mẫu cũ được gửi lại sau khi trạng thái đã đổi, hệ thống yêu cầu xác nhận lại thay vì tự kích hoạt quyền.

Với rút lại, có thể chọn thao tác áp dụng lên trạng thái hiện tại sau khi khóa, thay vì buộc người dùng biết revision mới nhất. Điều quan trọng là không để lỗi cạnh tranh khiến hệ thống báo đã rút thành công nhưng bản ghi thực tế vẫn cho phép.

Khả năng cấp lại và cách chứng minh lựa chọn mới phải tuân theo workflow đã xác định. Không cấm vĩnh viễn chỉ vì từng rút, cũng không coi bất kỳ lần cập nhật hồ sơ nào là cấp lại.

## 7. Transaction, idempotency và thông báo thay đổi

### 7.1. Ghi trạng thái và lịch sử cùng nhau

Trong một transaction cục bộ, thao tác thay đổi đồng ý nên gồm:

1. Xác định tenant và người gọi từ ngữ cảnh xác thực.
2. Xác minh người gọi được quản lý lựa chọn của chủ thể mục tiêu.
3. Tải và khóa đúng bản ghi phạm vi hoặc dùng cập nhật có điều kiện.
4. Kiểm tra điều kiện chuyển trạng thái.
5. Tăng revision khi có thay đổi có ý nghĩa.
6. Ghi lịch sử và trạng thái hiện tại nhất quán.
7. Ghi sự kiện outbox để các consumer biết thay đổi.
8. Lưu kết quả xử lý request theo cơ chế chống gửi lại nếu cần.

Nếu chỉ cập nhật trạng thái rồi phát message sau commit, tiến trình có thể dừng trước khi phát. Outbox giúp bảo toàn ý định thông báo trong transaction cục bộ.

Outbox không làm mọi hệ thống phụ đổi trạng thái ngay lập tức. Bên nhận cần xử lý trùng, kiểm tra revision và báo trạng thái đồng bộ nếu quy trình cần theo dõi.

### 7.2. Idempotency không thay thế điều kiện nghiệp vụ

Một yêu cầu rút lại được gửi lại phải không tạo thêm lần thay đổi vô nghĩa hoặc làm lùi trạng thái. Cùng khóa request nhưng khác chủ thể hoặc phạm vi phải được coi là xung đột theo hợp đồng API.

Đổi sang khóa request mới cũng không được khiến một yêu cầu cấp cũ trở thành bằng chứng mới. Cần kiểm soát chính thao tác cấp quyền, phiên bản và nguồn bằng chứng, không chỉ lưu khóa idempotency.

Nếu bản ghi đang ở trạng thái rút lại, retry rút lại có thể trả trạng thái hiện tại mà không tăng revision lần nữa. Có thể ghi nhận việc tiếp nhận request riêng nếu cần, nhưng không biến mỗi retry thành một sự kiện nghiệp vụ cấp hoặc rút mới.

### 7.3. Minh họa mã Java cho thao tác rút lại

Đoạn mã dưới đây là **mã khung kiến trúc**, chưa phải ứng dụng chạy độc lập. Nó giả định một dịch vụ có thẩm quyền quản lý lựa chọn và có repository, transaction cùng outbox được hiện thực đúng hợp đồng.

~~~java
record WithdrawConsentCommand(
        String subjectReference,
        String purposeId,
        String scopeId) {}

record ConsentReceipt(
        String consentId,
        long revision,
        String status) {}

public ConsentReceipt withdrawConsent(
        ActorContext actor,
        WithdrawConsentCommand command) {

    validateCommand(command);

    return transactions.required(() -> {
        var subject = subjects.resolveForConsentManagement(
                actor, command.subjectReference());

        var purpose = purposes.requireManageablePurpose(
                actor.tenantId(), command.purposeId(), command.scopeId());

        var key = new ConsentKey(
                actor.tenantId(),
                subject.id(),
                purpose.id(),
                command.scopeId());

        var consent = consents.lockOrCreateNotGranted(key);
        permissions.requireCanManageConsent(actor, subject, consent);

        // Returns no change only when already withdrawn.
        var transition = consent.withdrawIfNeeded(
                actor.subjectId(), serverClock.instant());

        if (transition.changed()) {
            consents.saveCurrentAndAppendHistory(consent, transition);
            outbox.appendConsentChanged(
                    consent.id(),
                    key,
                    consent.revision(),
                    consent.status());
        }

        return new ConsentReceipt(
                consent.id(),
                consent.revision(),
                consent.status().name());
    });
}
~~~

Các hợp đồng quan trọng:

- `resolveForConsentManagement` xác minh quyền quản lý chủ thể hoặc quan hệ đại diện trong đúng tenant. Không coi `subjectReference` là bằng chứng thẩm quyền.
- `lockOrCreateNotGranted` có khóa duy nhất theo phạm vi. Nếu hai transaction cùng tạo, repository phải xử lý tranh chấp bằng cơ chế cơ sở dữ liệu và retry thích hợp; không chỉ kiểm tra tồn tại rồi insert.
- Việc tạo bản ghi ban đầu không được tạo trạng thái đã cấp quyền. Yêu cầu không có thẩm quyền phải rollback mọi thay đổi.
- `withdrawIfNeeded` chuyển sang rút lại và tăng revision theo quy tắc nhất quán. Nếu đã rút thì không tạo thêm chuyển trạng thái. Nó không tự xóa bằng chứng lịch sử.
- Trạng thái hiện tại, lịch sử và outbox được commit cùng nhau.
- Thao tác cấp lại phải khóa cùng phạm vi hoặc dùng cơ chế cạnh tranh tương thích, đồng thời xác minh đây là lựa chọn mới hợp lệ. Mã khung chưa hiện thực thao tác đó.
- Thành công của hàm xác nhận đã ghi nhận quyết định tại nguồn có thẩm quyền. Nó không chứng minh mọi consumer đã cập nhật hoặc mọi tác động bên ngoài đã dừng.

Trong triển khai, response có thể kèm trạng thái lan truyền nếu sản phẩm cần phân biệt “đã ghi nhận” với “đã xác nhận xử lý ở các bên liên quan”. Không tự báo hoàn tất đồng bộ khi chỉ mới phát một message.

## 8. Thực thi tại nơi sử dụng dữ liệu

### 8.1. Một quyết định cho phép cần đúng ngữ cảnh

Tại điểm xuất, gửi hoặc truy vấn dữ liệu, hệ thống cần đánh giá:

~~~text
actor có quyền thực hiện tác vụ không?
đối tượng và tenant có đúng không?
tác vụ thuộc mục đích đã được định nghĩa nào?
những trường dữ liệu nào thực sự cần?
cơ sở xử lý và điều kiện tương ứng là gì?
nếu dựa trên đồng ý: phạm vi và trạng thái hiện tại có cho phép không?
có điều kiện giữ lại, cấm sử dụng hoặc hết hạn nào đang áp dụng không?
~~~

Một kết quả `ALLOW` không nên được dùng lại cho tác vụ khác chỉ vì cùng chủ thể. Có thể ràng buộc kết quả với mục đích, phạm vi dữ liệu, bên nhận, revision đã đánh giá và thời hạn ngắn phù hợp. Nếu cần hiệu lực thu hồi ngay, riêng thời hạn ngắn vẫn chưa đủ; cần kiểm tra trạng thái theo cơ chế mạnh hơn tại ranh giới thực thi.

Khi nguồn quyết định không khả dụng, hoạt động phụ thuộc đồng ý không được tự mặc định cho phép. Cách chờ, thử lại hoặc từ chối phải theo hợp đồng; không âm thầm tiếp tục bằng cache cũ nếu điều kiện bắt buộc yêu cầu trạng thái hiện hành.

### 8.2. Queue nên mang tham chiếu thay vì toàn bộ dữ liệu khi có thể

Nếu message chứa đầy đủ email, hồ sơ hành vi và cờ đồng ý tại lúc tạo, worker có thể xử lý mà không kiểm tra lại nguồn. Message cũng trở thành một bản sao dữ liệu cần quản lý.

Một thiết kế có thể đưa `taskId`, `subjectId`, `purposeId`, phạm vi và các tham chiếu cần thiết vào queue. Worker tải tối thiểu dữ liệu sau khi kiểm tra điều kiện.

Nếu bắt buộc chứa dữ liệu trong payload, cần bảo vệ quyền đọc, thời hạn và cơ chế xử lý tác vụ mất hiệu lực. Việc xóa bản ghi chính không tự xóa dữ liệu đã sao chép vào queue, file tạm hoặc dead-letter queue.

### 8.3. Kiểm tra ngay trước gửi vẫn có khoảng tranh chấp

Chỉ gọi hàm `hasConsent()` trước lời gọi mạng chưa tạo ra tính nguyên tử:

~~~text
Worker kiểm tra: GRANTED
Người dùng rút lại và transaction commit
Worker gửi sang nhà cung cấp
~~~

Cần xác định **ranh giới cấp phép hoặc bàn giao cuối cùng** và cách nó tương tác với rút lại. Ví dụ, transaction rút lại và transaction giành quyền gửi có thể dùng cùng bản ghi trạng thái, khóa hoặc phiên bản để xác định thứ tự. Tác vụ được cấp phép trước khi rút cần được phân loại là đang xử lý; tác vụ đến sau phải bị chặn.

Một bản ghi dispatch được tạo trước không đồng nghĩa dữ liệu đã gửi. Nếu chính sách yêu cầu hủy mọi tác vụ chưa thật sự bàn giao, worker phải kiểm tra khả năng hủy tại bước bàn giao và phối hợp với tích hợp, thay vì coi mọi outbox là đã gửi.

Transaction cơ sở dữ liệu không bao trùm hệ thống email hoặc đối tác bên ngoài. Không nên hứa ngăn tuyệt đối mọi tác động sau thời điểm commit chỉ bằng một kiểm tra trong cơ sở dữ liệu. Phải định nghĩa trung thực trạng thái đang xử lý, khả năng hủy, kết quả chưa rõ và cơ chế xác nhận từ bên ngoài.

Mục tiêu là giữ một quy tắc có thể kiểm chứng về thứ tự và hiệu lực, xử lý phần đã ra ngoài theo hợp đồng, đồng thời không để tác vụ cũ chưa được xử lý tiếp tục vô thời hạn.

## 9. Phạm vi lan truyền: bản sao, cache, chiến dịch và đối tác

Một hệ thống có thể có nhiều nơi giữ dữ liệu hoặc quyền xử lý:

| Nơi lưu hoặc sử dụng | Rủi ro sau khi rút đồng ý | Kiểm soát cần xác định |
| --- | --- | --- |
| Cache lựa chọn | Tiếp tục trả trạng thái đã cấp | Revision, vô hiệu hóa và chiến lược kiểm tra tại điểm dùng |
| Danh sách chiến dịch | Danh sách cũ tiếp tục được dùng | Kiểm tra lại trước tác động, đánh dấu tác vụ bị loại |
| Kho phân tích hoặc đặc trưng | Tiếp tục dùng dữ liệu cho mục đích phụ thuộc đồng ý | Phạm vi ngừng sử dụng, xóa hoặc tái xử lý theo chính sách |
| File xuất và vùng tạm | Dữ liệu còn tồn tại ngoài bảng gốc | Hạn dùng, quyền tải và theo dõi bản sao |
| Nhà cung cấp bên ngoài | Chưa biết thay đổi hoặc đang xử lý | Lệnh cập nhật, mã tương quan, xác nhận và retry |
| Backup và môi trường khôi phục | Phục hồi trạng thái cũ, làm sống lại quyền | Quy trình áp dụng lại quyết định mới trước khi phục vụ |

Không nên coi message gửi thành công là bằng chứng bên nhận đã ngừng xử lý. Nếu chính sách cần xác nhận, theo dõi riêng trạng thái đã phát, đã nhận, đã áp dụng hoặc cần can thiệp.

Khi consumer nhận các revision 42 rồi 41, nó không được quay về trạng thái cũ. Khi restore backup chỉ có revision 41, hệ thống cần khôi phục các thay đổi có hiệu lực sau đó trước khi cho phép hoạt động phụ thuộc quyền xử lý.

Một danh sách ngừng sử dụng tối thiểu có thể giúp không tái nhập lại người đã rút. Tuy nhiên, bản thân danh sách đó vẫn chứa dữ liệu hoặc định danh cần được bảo vệ, có mục đích và quy tắc lưu riêng. Không giữ toàn bộ hồ sơ vô hạn chỉ để phục vụ việc chặn gửi.

## 10. Rút đồng ý, ngừng sử dụng và xóa dữ liệu là các thao tác khác nhau

Không nên triển khai mọi yêu cầu riêng tư bằng cùng một cờ hoặc cùng một lệnh xóa.

| Thao tác | Mục tiêu nghiệp vụ | Điều cần phân biệt |
| --- | --- | --- |
| Rút lại đồng ý | Không tiếp tục dựa vào quyết định đồng ý đó | Không tự giải quyết mọi bản sao hoặc mọi hoạt động có cơ sở khác |
| Ngừng một loại xử lý | Chặn hoạt động theo phạm vi được xác định | Có thể không cần xóa mọi bản ghi giao dịch |
| Xóa hoặc giảm dữ liệu | Loại bỏ trường hoặc bản sao không còn được giữ theo chính sách | Cần xét quan hệ, dữ liệu dẫn xuất và các điều kiện lưu được phê duyệt |
| Xuất dữ liệu cho chủ thể | Cung cấp đúng dữ liệu cho đúng người yêu cầu | Không được xuất dữ liệu người khác hoặc gửi đến địa chỉ mới chưa kiểm chứng |
| Sửa dữ liệu | Cập nhật thông tin đúng và lan truyền cần thiết | Không được dùng để giả mạo danh tính hoặc xóa lịch sử quyết định |

Chính sách thời gian lưu và các điều kiện giữ lại phải được xác định theo bối cảnh áp dụng. Bài này không đặt một thời hạn chung cho mọi loại dữ liệu.

### 10.1. Không biến yêu cầu dữ liệu thành đường lấy dữ liệu trái quyền

Endpoint “tải toàn bộ dữ liệu của tôi” vẫn cần xác minh chủ thể và quan hệ với dữ liệu. Không tin `subjectId` do khách gửi rồi xuất toàn bộ hồ sơ tương ứng.

Với tác vụ bất đồng bộ:

1. Xác minh người yêu cầu và phạm vi đại diện nếu có.
2. Chốt chủ thể, phạm vi và mục đích của yêu cầu.
3. Tạo job có trạng thái, quyền truy cập và mã tương quan.
4. Lọc dữ liệu theo quan hệ, tránh lẫn thông tin người khác.
5. Kiểm tra quyền khi nhận kết quả; không chỉ khi tạo job.
6. Chuyển giao qua kênh được kiểm chứng và quản lý thời hạn file tạm.
7. Ghi dấu vết phù hợp mà không sao chép toàn bộ nội dung xuất vào log.

Không để người gọi thay email nhận kết quả ngay trước khi gửi mà bỏ xác minh. Nếu dùng link tải có token, link đó là một khả năng truy cập cần được bảo vệ: giới hạn phạm vi, thời hạn và số lần hoặc điều kiện sử dụng theo thiết kế. Chọn cách gửi link không thay thế kiểm tra dữ liệu trong file.

### 10.2. Xóa dữ liệu cần biết các bản sao và quan hệ

Một lệnh xóa ở bảng khách hàng không chứng minh dữ liệu đã biến mất khỏi chỉ mục tìm kiếm, kho phân tích, file xuất hoặc nhà cung cấp. Quy trình cần danh mục nơi lưu và trạng thái xử lý ở từng nơi cần thiết.

Ngược lại, không xóa mù mọi tham chiếu làm hỏng sổ giao dịch hoặc xóa bằng chứng đang được giữ theo chính sách đã xác định. Cần phân loại dữ liệu, mục đích còn hiệu lực và cách giảm nhận diện khi phù hợp.

Nếu xóa tài khoản rồi đăng ký lại, không tự chuyển quyết định cũ sang chủ thể mới chỉ vì dùng lại cùng email. Nếu vẫn cần ngăn nhập lại vào chiến dịch sau khi rút, cơ chế đối chiếu phải có mục đích, căn cứ và quy tắc riêng; không nhập nhằng giữa hồ sơ tài khoản mới và bằng chứng cũ.

## 11. Các đường lạm dụng cần thiết kế để chặn

| Cách lạm dụng hoặc lỗi logic | Vì sao kiểm tra thông thường chưa đủ? | Hướng bảo vệ |
| --- | --- | --- |
| Gửi `marketingConsent=true` qua API sửa hồ sơ | Người dùng có quyền sửa hồ sơ nhưng endpoint bỏ qua workflow lựa chọn | Tách lệnh và kiểm tra nguồn bằng chứng |
| Quản lý consent bằng ID của người khác | Đã đăng nhập không chứng minh quyền trên chủ thể | Phân quyền theo đối tượng và quan hệ đại diện |
| Dùng đồng ý email để gửi SMS | Boolean không biểu diễn kênh và phạm vi | Ràng buộc đúng phạm vi xử lý |
| Tự gán nhãn “thông báo giao dịch” cho quảng cáo | Caller đang chọn chính sách dễ hơn | Mục đích gắn với chức năng và nội dung được kiểm soát |
| Import danh bạ với mặc định đã đồng ý | Có dữ liệu không đồng nghĩa có quyết định hợp lệ | Kiểm tra nguồn, giữ trạng thái chưa xác định khi thiếu bằng chứng |
| Phát lại lệnh cấp cũ sau khi rút | Idempotency ngắn hạn không chặn được quyền cũ sống lại | Revision, điều kiện cấp lại và bằng chứng mới |
| Dùng cache hoặc token lâu hạn | Quyền có thể đã bị rút tại nguồn | Kiểm tra hiệu lực theo yêu cầu của điểm thực thi |
| Chỉ xóa khỏi một danh sách | Dữ liệu còn ở chiến dịch, queue hoặc bên ngoài | Theo dõi phạm vi lan truyền và xác nhận |
| Gửi file dữ liệu sang email vừa đổi | Tài khoản hoặc trường liên hệ có thể bị lợi dụng | Xác minh người nhận theo mức bảo vệ cần thiết |
| Restore backup rồi chạy worker ngay | Quyết định mới chưa được phục hồi | Đồng bộ thay đổi có hiệu lực trước khi phục vụ |
| Ghi quá nhiều bằng chứng vào log | Dấu vết trở thành một kho dữ liệu có quyền đọc rộng | Tối thiểu hóa, phân quyền và thời gian lưu phù hợp |

Nếu lựa chọn được thay đổi qua trình duyệt dùng cookie phiên, còn cần cơ chế chống giả mạo yêu cầu phù hợp với kiến trúc. Một request hợp lệ về cú pháp không chứng minh chủ thể đã chủ động thực hiện thao tác. Với link quản lý lựa chọn không cần đăng nhập, token cần đủ khó đoán, đúng phạm vi và không được mở rộng thành quyền xem hồ sơ hoặc cấp quyền khác ngoài thiết kế.

## 12. Kiểm thử theo kết quả xử lý bị cấm

Kiểm thử cần xem cả bản ghi quyết định lẫn nơi dữ liệu thật sự được sử dụng. HTTP 200 của endpoint rút lại không chứng minh worker đã ngừng gửi.

| Tình huống | Thao tác trong môi trường kiểm thử | Điều cần chứng minh |
| --- | --- | --- |
| Chưa có đồng ý | Tạo chủ thể không có bằng chứng cấp rồi chạy chiến dịch dựa trên đồng ý | Không được chọn hoặc gửi như người đã đồng ý |
| Sai chủ thể hoặc tenant | Dùng ID hợp lệ của người khác hoặc tenant khác | Không sửa lựa chọn, không tiết lộ dữ liệu trái quyền |
| Sai phạm vi | Đồng ý email nhưng thử gửi SMS hoặc chia sẻ cho bên nhận ngoài phạm vi | Không được diễn giải mở rộng |
| Tài khoản nhập người nhận khác | Mua hàng với địa chỉ liên hệ của người nhận quà | Không tự cấp quyền tiếp thị cho người nhận |
| Rút sau khi xếp hàng | Tạo task từ revision 41 rồi rút ở revision 42 trước ranh giới cấp phép cuối | Tác vụ chưa qua ranh giới bị chặn theo chính sách |
| Message đến lệch thứ tự | Consumer nhận revision 42 rồi 41 | Không phục hồi trạng thái cũ |
| Cạnh tranh cấp và rút | Đồng bộ hai request trên cùng phạm vi | Kết quả theo thứ tự có thẩm quyền, không bị mất cập nhật |
| Replay thao tác cấp | Phát lại lựa chọn cũ sau khi đã rút, kể cả với khóa request mới | Không tự coi là một lựa chọn cấp lại mới |
| Retry rút lại | Gửi lại nhiều lần hoặc nhiều worker xử lý cùng sự kiện | Trạng thái ổn định, không tạo chuyển trạng thái sai |
| Thiếu nguồn quyết định | Làm nguồn consent không khả dụng tại điểm dùng | Không mặc định cho phép hoạt động cần consent hiện hành |
| Thay đổi thông báo | Thêm phạm vi mới rồi dùng bản ghi cũ | Áp dụng đúng quy tắc tương thích hoặc yêu cầu xác nhận lại |
| Tác vụ ngoài đang xử lý | Bàn giao trước rút, sau đó gửi yêu cầu hủy và nhận kết quả muộn | Trạng thái phản ánh đúng khả năng hủy, không báo hoàn tất sai |
| Import hoặc khôi phục | Nhập bản sao cũ hoặc restore backup trước khi chạy worker | Không làm sống lại quyền đã bị rút |
| Yêu cầu xuất dữ liệu | Tạo job cho chủ thể khác hoặc thay người nhận kết quả | Không xuất hoặc chuyển giao trái quyền |
| Xóa và bản sao | Xử lý yêu cầu trên dữ liệu có queue, file và kho phụ | Kết quả khớp chính sách ở từng nơi, có dấu vết chưa hoàn tất |

Với cạnh tranh, cần đặt điểm đồng bộ để các transaction thật sự cùng tranh chấp. Mock repository không chứng minh ngữ nghĩa khóa, uniqueness hoặc rollback. Kiểm thử với cơ sở dữ liệu và hạ tầng mô phỏng có khả năng thể hiện độ trễ, trùng và đảo thứ tự.

Ngoài trạng thái hiện tại, hãy kiểm tra:

- Revision và lịch sử có khớp quyết định được chấp nhận không?
- Có outbox nào bị mất hoặc sự kiện cũ nào được áp dụng lại không?
- Worker có thực sự gửi, xuất hoặc đọc dữ liệu sau khi mất quyền không?
- Tác vụ bị loại có còn giữ dữ liệu không cần thiết trong file tạm hay queue không?
- Bên nhận đã xác nhận thay đổi hay mới chỉ nhận một lời gọi mạng?
- Các hoạt động có cơ sở khác có bị chặn hoặc cho phép đúng chính sách riêng không?

Có thể bổ sung kiểm thử sinh chuỗi thao tác: cấp, sửa phạm vi, rút, retry, hết hạn, import, khôi phục và thực thi task. Sau mỗi bước commit, quyết định hiện tại không được bị thay thế bởi bằng chứng cũ; mỗi tác động phải có căn cứ đúng phạm vi.

## 13. Dấu vết, giám sát và thông tin phản hồi

Một chuỗi tương quan hữu ích:

~~~text
subjectId + purposeId + scopeId
  -> consentRevision
  -> processingDecisionId
  -> taskId hoặc exportJobId
  -> downstreamAcknowledgement
~~~

Dấu vết nên giúp trả lời ai yêu cầu, hệ thống quyết định thế nào, dựa trên revision nào và dữ liệu đã đi tới đâu trong phạm vi được theo dõi. Không biến chuỗi tương quan thành quyền truy cập dữ liệu: người đọc lịch sử vẫn cần được phân quyền.

Các tín hiệu hữu ích để điều tra:

- Tác vụ dùng revision cũ sau khi nguồn đã có quyết định mới.
- Sự kiện cấp quyền không có nguồn bằng chứng hoặc thông báo tương ứng.
- Tỷ lệ cao thao tác sửa lựa chọn qua tài khoản nhân viên hoặc luồng import.
- Bên nhận chưa xác nhận ngừng xử lý quá thời gian vận hành đã định.
- File xuất còn khả dụng sau thời hạn cấu hình.
- Quyết định đã rút bị đổi thành đã cấp mà không có lựa chọn mới hợp lệ.

Không ghi đầy đủ dữ liệu cá nhân trong mỗi sự kiện kiểm toán. Có thể dùng tham chiếu và dữ kiện tối thiểu, đồng thời kiểm soát quyền truy cập kho bằng chứng.

Giao diện nên phân biệt chính xác trạng thái của yêu cầu: đã tiếp nhận, đã ghi nhận tại nguồn, đang lan truyền hoặc cần xử lý bổ sung nếu sản phẩm theo dõi các bước đó. Thông tin phản hồi phải phản ánh điều hệ thống đã làm được, nhất là khi có tích hợp ngoài.

## 14. Bài tập tự kiểm tra

### Bài 1: một cờ đồng ý cho mọi hoạt động

Hệ thống có cột `consent=true`. Đội email, đội SMS và dịch vụ phân tích đều dùng nó để quyết định xử lý.

**Gợi ý trả lời:** mô hình chưa biểu diễn chủ thể quyết định đã cho phép mục đích, kênh và phạm vi nào. Cần danh mục hoạt động, khóa phạm vi và phiên bản nội dung có thể truy nguyên. Đồng thời kiểm tra quyền của dịch vụ gọi; không coi consent là quyền truy cập chung.

### Bài 2: rút lại thành công nhưng worker vẫn gửi

API rút lại đã commit, còn worker dùng danh sách tạo từ một giờ trước và không gọi lại nguồn quyền.

**Gợi ý trả lời:** danh sách cũ chỉ là ứng viên, không đủ chứng minh quyền hiện tại. Cần kiểm tra tại ranh giới cấp phép hoặc bàn giao đã xác định, phối hợp với thứ tự rút lại, hủy task chưa được phép và theo dõi tác vụ đã ra ngoài. Một lần kiểm tra rồi gọi mạng vẫn có khoảng cạnh tranh cần được thiết kế rõ.

### Bài 3: bản cập nhật cũ đến sau

Consumer đã áp dụng `WITHDRAWN` ở revision 42, sau đó nhận `GRANTED` ở revision 41.

**Gợi ý trả lời:** không áp dụng lại bản cũ. Revision cần được so theo cùng phạm vi và nguồn có thẩm quyền. Nếu có nhiều nguồn ghi, phải có mô hình xung đột phù hợp; timestamp do client tự khai không thay thế được thứ tự đó.

### Bài 4: xóa tài khoản có đồng nghĩa xóa hết dữ liệu không?

Một job xóa bản ghi tài khoản, nhưng file xuất, kho phân tích và một nhà cung cấp vẫn còn dữ liệu.

**Gợi ý trả lời:** chưa thể kết luận đã hoàn tất theo toàn bộ phạm vi. Cần bản đồ nơi lưu, chính sách cho từng nhóm dữ liệu, trạng thái thực thi và cơ chế xác nhận. Cũng không xóa mù dữ liệu còn được giữ theo chính sách riêng; phải giải thích được điều gì đã xóa, đã ngừng sử dụng hoặc còn đang xử lý.

## 15. Các điểm cần ghi nhớ

Dữ liệu cá nhân và bằng chứng đồng ý là các tài sản có quan hệ với chủ thể, mục đích, phạm vi và thời gian. Bảo vệ bí mật dữ liệu không tự bảo đảm dữ liệu được sử dụng đúng nghiệp vụ.

Một thiết kế có thể kiểm chứng cần tách phân quyền khỏi điều kiện xử lý, quản lý quyết định theo phạm vi và revision, bảo vệ nguồn bằng chứng, đồng thời thực thi tại nơi dữ liệu thật sự được dùng. Transaction và idempotency giữ nhất quán cục bộ; outbox, kiểm soát phiên bản và xác nhận phía sau giúp lan truyền; chúng không tự tạo ra một transaction nguyên tử với mọi đối tác.

Câu hỏi cốt lõi là: **Ở thời điểm sử dụng dữ liệu này, hệ thống có căn cứ nào còn hiệu lực cho đúng chủ thể, mục đích và phạm vi, và căn cứ đó được giữ nhất quán đến tác động thực tế bằng cách nào?**
