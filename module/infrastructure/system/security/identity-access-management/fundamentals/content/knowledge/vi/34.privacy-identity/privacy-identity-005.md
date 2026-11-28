# Attribute release policy

## 1. Chính sách phát hành thuộc tính là gì?

**Attribute release policy** là tập quy tắc quyết định một hệ thống IAM được cung cấp những thuộc tính danh tính nào cho một bên nhận, dưới dạng nào, trong mục đích và ngữ cảnh nào.

Thuộc tính có thể gồm định danh chủ thể, tên hiển thị, email, ngôn ngữ, đơn vị, vai trò hoặc một kết quả đã dẫn xuất như “thuộc nhóm nhân viên đang hoạt động”. Chúng có thể xuất hiện trong thông điệp liên kết danh tính, token, phản hồi lấy thông tin người dùng hoặc API hồ sơ.

Một hệ thống có đủ dữ liệu để xác thực và quản lý danh tính không có nghĩa mọi ứng dụng liên kết đều cần nhận toàn bộ dữ liệu đó. Chính sách phát hành thuộc tính đặt một ranh giới giữa **dữ liệu hệ thống biết** và **dữ liệu một bên cụ thể được phép nhận**.

Ví dụ, cổng học tập có thể cần định danh ổn định trong phạm vi ứng dụng, tên hiển thị và ngôn ngữ. Nó không mặc nhiên cần ngày sinh, số điện thoại, địa chỉ nhà hoặc toàn bộ nhóm nội bộ chỉ để cho người dùng đăng nhập.

Chính sách này thực hiện nguyên tắc ít quyền nhất đối với việc chia sẻ dữ liệu danh tính: đúng bên nhận, đúng tập thuộc tính, đúng mục đích và đủ điều kiện tại thời điểm phát hành.

## 2. Phân biệt phát hành thuộc tính với các quyết định khác

| Quyết định | Câu hỏi chính | Quan hệ với việc phát hành thuộc tính |
|---|---|---|
| Authentication | Chủ thể đã đáp ứng điều kiện xác thực nào? | Cung cấp ngữ cảnh đáng tin cậy cho quyết định phát hành |
| Attribute release | Bên nhận được biết dữ liệu danh tính nào? | Là phạm vi chính của bài học |
| Authorization | Chủ thể được thực hiện hành động gì trên tài nguyên? | Có thể dùng thuộc tính đã được phát hành, nhưng vẫn phải đánh giá quyền |
| Consent | Người dùng đã lựa chọn hoặc đồng ý điều gì trong phạm vi cho phép? | Có thể là một điều kiện; không thay thế mọi quy tắc khác |
| Provisioning | Tài khoản và thuộc tính nào được tạo, cập nhật hoặc vô hiệu hóa ở hệ thống đích? | Là một đường truyền dữ liệu khác cần được quản trị riêng |

Nếu một ứng dụng nhận `department=engineering`, điều đó không tự cấp cho nó quyền đọc mọi tài liệu kỹ thuật. Ứng dụng hoặc resource server vẫn phải áp dụng chính sách authorization tương ứng.

Ngược lại, chỉ cần ứng dụng được đọc một thuộc tính đã là một quyết định chia sẻ dữ liệu. “Chưa dùng để cấp quyền” không phải lý do để gửi không giới hạn.

Việc cho phép SSO cũng không đồng nghĩa cho phép đồng bộ toàn bộ hồ sơ, và việc đã provision một vài thuộc tính không có nghĩa token phải chứa lại mọi thuộc tính đó.

## 3. Mô hình các bên và các đường phát hành

Trong mô hình đơn giản:

```text
Nguồn thuộc tính có thẩm quyền
    -> dịch vụ danh tính / điểm quyết định chính sách
    -> lọc và biến đổi theo bên nhận, mục đích, ngữ cảnh
    -> thông điệp, token hoặc phản hồi được bảo vệ
    -> ứng dụng / dịch vụ nhận dữ liệu
```

Nguồn có thẩm quyền có thể là kho danh tính, hệ thống nhân sự hoặc dữ liệu đã được kiểm chứng theo quy trình. Không phải thuộc tính nào nằm trong cùng một hồ sơ cũng có cùng mức tin cậy hoặc chủ sở hữu nghiệp vụ.

Những đường phát hành thường gặp gồm:

- Thông điệp liên kết danh tính gửi tới ứng dụng.
- ID token hoặc thông tin hồ sơ gửi cho client trong luồng phù hợp.
- Access token mang các claim cần thiết cho resource server đích.
- Phản hồi của endpoint lấy thông tin người dùng.
- API hồ sơ hoặc directory query.
- Provisioning và đồng bộ thuộc tính tới hệ thống đích.

Phải quản trị nhất quán các đường liên quan. Lọc email khỏi token nhưng để cùng client lấy email qua endpoint hồ sơ với quyền rộng hơn vẫn có thể làm mất mục tiêu của chính sách.

Điều này không có nghĩa mọi đường dùng cùng một tập claim. Mỗi loại thông điệp, token và API có bên nhận, hợp đồng và mục đích khác nhau; quyết định phải phù hợp với từng đường cụ thể.

## 4. Những đầu vào của một quyết định phát hành

Một quyết định tốt cần đủ thông tin để phân biệt các trường hợp có bề ngoài giống nhau.

| Nhóm đầu vào | Ví dụ | Điều cần kiểm soát |
|---|---|---|
| Bên nhận | Client, relying party, service provider hoặc resource đích đã đăng ký | Không lấy định danh do request tự khai làm bằng chứng duy nhất |
| Chủ thể | Người dùng, workload, tenant hoặc tổ chức liên quan | Tránh nhầm tài khoản hoặc trộn ranh giới tenant |
| Thuộc tính | Tên, kiểu dữ liệu, độ nhạy cảm, nguồn và độ mới | Chỉ phát hành giá trị có ý nghĩa và nguồn phù hợp |
| Mục đích | Đăng nhập cổng học, hiển thị hồ sơ, nhận thông báo | Mục đích phải gắn với hợp đồng được duyệt |
| Ngữ cảnh | Flow, môi trường, mức xác thực, trạng thái tài khoản | Chỉ tin các tín hiệu đã được kiểm chứng ở mức cần thiết |
| Quyền và lựa chọn | Chính sách tổ chức, phê duyệt, lựa chọn của người dùng nếu áp dụng | Một điều kiện riêng lẻ không tự vượt mọi giới hạn |
| Đường truyền dữ liệu | Loại token, API hoặc thông điệp | Đúng bên nhận, audience và hợp đồng dữ liệu |

Ví dụ, một client không được tự gửi `purpose=payroll` rồi được nhận thêm dữ liệu nhân sự. Mục đích đó phải được ràng buộc với client, chức năng và quyền truy cập đã được quản trị.

Tương tự, mức xác thực mạnh hơn có thể là điều kiện cần để phát một dữ liệu nhạy cảm, nhưng không tự làm bên nhận có nhu cầu hợp lệ đối với dữ liệu đó.

## 5. Thiết kế từ nhu cầu tối thiểu của bên nhận

### 5.1. Lập hợp đồng thuộc tính

Với mỗi ứng dụng hoặc nhóm bên nhận, nên xác định rõ:

- Chức năng nào cần dữ liệu và vì sao.
- Thuộc tính tối thiểu nào là bắt buộc cho chức năng đó.
- Thuộc tính nào chỉ phục vụ tính năng tùy chọn.
- Kiểu dữ liệu, nguồn, độ mới và ý nghĩa của từng thuộc tính.
- Cách xử lý khi thiếu hoặc không được phép phát hành.
- Ai phê duyệt thay đổi, ai sở hữu dữ liệu và ai vận hành tích hợp.

Một bảng minh họa cho cổng học tập:

| Thuộc tính | Nhu cầu | Quyết định minh họa |
|---|---|---|
| Định danh chủ thể trong phạm vi ứng dụng | Liên kết đúng tài khoản | Bắt buộc theo hợp đồng định danh |
| Tên hiển thị | Cá nhân hóa giao diện | Tùy chọn; có thể dùng tên hiển thị cục bộ |
| Ngôn ngữ | Chọn giao diện | Tùy chọn; có giá trị mặc định phù hợp khi thiếu |
| Email | Gửi thông báo theo tính năng đã duyệt | Chỉ phát hành nếu nhu cầu và điều kiện được đáp ứng |
| Toàn bộ group nội bộ | Không cần cho đăng nhập cơ bản | Không phát hành |
| Ngày sinh, địa chỉ nhà | Không phục vụ chức năng đã xác định | Không phát hành |

Không đánh dấu tất cả thuộc tính là bắt buộc chỉ để giảm số trường hợp ứng dụng phải xử lý. Thiết kế ứng dụng phải chấp nhận sự vắng mặt của những dữ liệu không thực sự cần thiết.

### 5.2. Ưu tiên kết quả dẫn xuất khi đủ dùng

Nếu một chức năng chỉ cần biết “đủ điều kiện sử dụng dịch vụ”, có thể cân nhắc phát hành kết quả đã dẫn xuất thay vì toàn bộ dữ liệu nguồn, miễn là phép biến đổi và ý nghĩa kết quả được quản trị rõ ràng.

Ví dụ, một ứng dụng chỉ cần biết người dùng có quyền sử dụng khóa học nội bộ có thể nhận một entitlement dành riêng cho ứng dụng. Gửi toàn bộ cây đơn vị, chức danh và nhóm tổ chức thường là phạm vi rộng hơn nhu cầu đó.

Thuộc tính dẫn xuất vẫn có thể tiết lộ thông tin hoặc ảnh hưởng quyết định cấp quyền. Nó cần nguồn đáng tin, độ mới, chủ sở hữu, hợp đồng và cách xử lý lỗi; không tự trở thành dữ liệu vô hại chỉ vì đã được rút gọn.

## 6. Quy tắc mặc định và thứ tự đánh giá

Một thiết kế thường bắt đầu từ **không phát hành thuộc tính chưa được cho phép rõ ràng cho bên nhận và đường truyền tương ứng**.

Có thể mô hình hóa việc đánh giá như sau:

```text
1. Xác minh bên nhận và ngữ cảnh của yêu cầu.
2. Lấy hợp đồng thuộc tính đã duyệt cho bên nhận và loại thông điệp.
3. Xác định tập ứng viên từ hợp đồng và yêu cầu hợp lệ.
4. Áp dụng giới hạn theo chủ thể, tenant, mục đích và ngữ cảnh.
5. Kiểm tra nguồn, độ mới và các điều kiện bổ sung.
6. Tạo các giá trị được phép, bao gồm biến đổi đã phê duyệt.
7. Kiểm tra yêu cầu bắt buộc của hợp đồng đầu ra.
8. Phát hành tập đã lọc hoặc trả kết quả lỗi phù hợp.
9. Ghi bằng chứng quyết định với dữ liệu tối thiểu cần thiết.
```

Tập ứng viên có thể bao gồm thuộc tính định danh bắt buộc theo hợp đồng, không chỉ những thuộc tính mà client liệt kê tùy chọn trong request. Cơ chế request không được mở rộng tập cho phép của bên nhận.

Các quy tắc xung đột phải có ngữ nghĩa rõ ràng: ví dụ một quy tắc từ chối cụ thể có thể được thiết kế để ưu tiên hơn một quy tắc cho phép tổng quát. Đây là lựa chọn phải được khai báo và kiểm chứng trong hệ thống chính sách; không mặc định mọi policy engine đều xử lý giống nhau.

Nếu thuộc tính bắt buộc không được phép phát hành hoặc nguồn không đủ tin cậy, không âm thầm dùng dữ liệu khác hay mở rộng quyền để luồng “chạy được”. Cần áp dụng cách thất bại đã xác định trong giao thức và hợp đồng tích hợp.

Với thuộc tính tùy chọn, có thể bỏ thuộc tính khi không đủ điều kiện và để tính năng tương ứng suy giảm theo thiết kế. Ứng dụng phải phân biệt thiếu dữ liệu với một giá trị nghiệp vụ như `false` hoặc chuỗi rỗng.

## 7. Ví dụ chính sách cho một ứng dụng

Ví dụ sau là schema tự đặt để diễn giải thiết kế, không phải cấu hình có thể dùng trực tiếp cho một sản phẩm IAM:

```yaml
policyId: learning-portal-attribute-release
version: example-v1
recipient:
  registeredClient: learning-portal
  environment: production
  channel: identity-profile-response
purpose: learning-account-and-display
defaults:
  releaseUnlistedAttributes: false
requiredAttributes:
  - subjectForRecipient
optionalAttributes:
  - displayName
  - preferredLanguage
conditionalAttributes:
  email:
    requires:
      - approvedNotificationFeature
      - recipientAllowedToReceiveEmail
      - subjectConditionsSatisfied
prohibitedAttributes:
  - birthDate
  - homeAddress
  - fullDirectoryGroups
audit:
  includePolicyVersion: true
  includeAttributeNames: true
  includeAttributeValues: false
```

Những tên như `subjectConditionsSatisfied` đại diện cho điều kiện cần được định nghĩa cụ thể trong triển khai. Không dùng một nhãn mơ hồ thay cho quy tắc có thể kiểm chứng.

Trong tình huống email không đủ điều kiện, phản hồi minh họa có thể chỉ gồm:

```json
{
  "subjectForRecipient": "lp-subject-example-7f3a",
  "displayName": "Người học A",
  "preferredLanguage": "vi"
}
```

Ứng dụng vẫn có thể liên kết tài khoản bằng định danh được cấp trong đúng ngữ cảnh, hiển thị tên và dùng giao diện tiếng Việt. Tính năng thông báo email phải xử lý trường hợp không có email theo hợp đồng của nó.

Nếu client xin thêm `fullDirectoryGroups`, hệ thống không phát hành chỉ vì thuộc tính tồn tại trong directory. Nếu một client chưa đăng ký sao chép cùng yêu cầu, nó cũng không được hưởng chính sách của `learning-portal`.

Thay đổi môi trường hoặc thêm đường API mới cần quyết định quản trị riêng phù hợp. Không tự cho production và development dùng chung quyền nhận thuộc tính nhạy cảm.

## 8. Áp dụng trong token và liên kết danh tính

### 8.1. Claim, scope và bên nhận

Trong các tích hợp dựa trên token, scope và yêu cầu claim là những đầu vào của quá trình đánh giá, không phải bằng chứng rằng client được nhận mọi thuộc tính tương ứng.

Ví dụ, một ứng dụng yêu cầu thông tin hồ sơ vẫn phải chịu giới hạn phát hành dành cho ứng dụng đó. Tập dữ liệu thực tế cần tuân theo giao thức, quyền đã được cấp và chính sách của nhà cung cấp danh tính.

Không dùng một cấu hình “mọi claim cho mọi client” chỉ để đơn giản hóa tích hợp. ID token, access token và phản hồi hồ sơ có mục đích, bên nhận và cách sử dụng khác nhau. Một claim cần cho resource server không mặc nhiên cần xuất hiện trong token dành cho client hoặc trong mọi phản hồi hồ sơ.

Với thông điệp liên kết danh tính, mapping thuộc tính cũng phải được ràng buộc với bên nhận đã cấu hình và xác minh. Không phát hành dựa trên một địa chỉ đích hoặc tên service provider do đầu vào chưa được kiểm chứng cung cấp.

### 8.2. Chữ ký không tạo ra tính bí mật

Chữ ký bảo vệ tính toàn vẹn và hỗ trợ kiểm chứng nguồn theo cơ chế được sử dụng; nó không tự làm nội dung claim trở nên bí mật đối với mọi bên cầm token.

Một token có chữ ký vẫn có thể chứa dữ liệu mà bên nhận hoặc người có được token đọc được, tùy định dạng và cơ chế bảo vệ. Mã hóa đường truyền cũng không ngăn bên nhận hợp lệ đọc hoặc lưu lại nội dung sau khi nhận.

Vì vậy, cần giảm dữ liệu trước khi phát hành. Không đưa thông tin nhạy cảm không cần thiết vào token rồi coi chữ ký hoặc HTTPS là lý do đủ để bỏ qua ranh giới chia sẻ.

### 8.3. Nhất quán giữa các đường truy cập

Kiểm tra cả token, phản hồi hồ sơ, provisioning, API directory và các kênh liên quan mà cùng bên nhận có thể sử dụng. Mỗi đường có hợp đồng riêng nhưng phải giữ các giới hạn chia sẻ đã được xác định.

Nếu email bị giới hạn ở một đường, cần xem bên nhận có thể lấy lại nó qua một quyền API rộng hơn hay không. Việc cần sửa có thể là quyền API, mapping hoặc hợp đồng tích hợp, không chỉ một bộ lọc claim.

## 9. Định danh theo bên nhận và nguy cơ liên kết chéo

Một định danh toàn cục dùng ở nhiều ứng dụng làm việc nối dữ liệu giữa các bên dễ hơn. Khi phù hợp với thiết kế giao thức và nhu cầu liên kết, có thể dùng định danh khác nhau theo bên nhận hoặc một nhóm bên nhận được quản trị.

Ví dụ minh họa:

```text
Cùng một tài khoản trong nguồn danh tính
    -> cổng học tập: subject LP-A1
    -> hệ thống đặt phòng: subject MR-B8
```

Các giá trị chỉ là ví dụ, không mô tả thuật toán tạo định danh. Triển khai cần bảo đảm tính ổn định, đúng phạm vi, tránh gán lại gây nhầm tài khoản và có quy trình migration khi thay đổi cấu hình.

Việc dùng định danh theo bên nhận có thể giảm khả năng liên kết trực tiếp, nhưng không bảo đảm ẩn danh. Nếu cả hai bên vẫn nhận cùng email hoặc những tổ hợp thuộc tính đủ đặc trưng, chúng vẫn có thể liên kết dữ liệu.

Băm email rồi dùng kết quả như một định danh chung cũng không tự đạt mục tiêu này. Dữ liệu đầu vào có thể dễ đoán, và một giá trị chung vẫn cho phép nối dữ liệu giữa các ứng dụng.

Định danh cần được diễn giải trong ngữ cảnh nguồn phát hành và phạm vi tương ứng. Không dùng một tên hiển thị, email có thể thay đổi hoặc định danh ngoài ngữ cảnh như bằng chứng duy nhất để nối hai tài khoản.

## 10. Consent, mục đích và thuộc tính bắt buộc

Một số luồng chia sẻ có thể có lựa chọn của người dùng. Nếu áp dụng, giao diện cần giải thích bên nhận, mục đích và nhóm dữ liệu theo ngôn ngữ dễ hiểu, đồng thời phản ánh đúng quyết định kỹ thuật.

Lựa chọn của người dùng không được làm client vượt tập thuộc tính mà tổ chức cho phép nhận. Ngược lại, việc client có trong danh sách được phép cũng không tự đáp ứng mọi điều kiện liên quan đến chủ thể và mục đích.

Không coi một lần đăng nhập thành công là sự đồng ý không giới hạn cho mọi chia sẻ về sau. Cần quản trị phạm vi, trạng thái và thay đổi lựa chọn theo cơ chế của hệ thống.

Với thuộc tính được gọi là bắt buộc, phải kiểm tra tính bắt buộc ở cấp chức năng. Nếu chỉ tính năng gửi thông báo cần email thì có thể thiết kế để thiếu email chỉ ảnh hưởng tính năng đó, thay vì buộc toàn bộ chức năng đăng nhập phải nhận email.

Nếu một chức năng thực sự không thể thực hiện khi thiếu dữ liệu cần thiết, hệ thống cần thể hiện rõ giới hạn và trả kết quả phù hợp. Không dùng thông báo mơ hồ để che việc ứng dụng đang yêu cầu quá nhiều dữ liệu.

Mục đích cũng phải được kiểm soát sau khi chia sẻ. Chính sách phát hành chỉ quyết định thời điểm đưa dữ liệu ra; nó không tự bảo đảm bên nhận sẽ lưu, sử dụng và chia sẻ tiếp đúng mục đích. Những nghĩa vụ này cần được thể hiện trong quản trị ứng dụng và các kiểm soát ở bên nhận.

## 11. Nguồn dữ liệu, độ mới và vòng đời quyền

### 11.1. Thuộc tính đúng phải đến từ nguồn phù hợp

Một trường do người dùng tự nhập không nên được dùng như thuộc tính đáng tin để cấp quyền quan trọng nếu chưa có quy trình kiểm chứng tương ứng. Cần ghi rõ nguồn nào sở hữu từng thuộc tính và hệ thống nào được phép cập nhật nó.

Các giá trị như email đã được kiểm chứng, trạng thái làm việc hoặc vai trò cần giữ đúng ngữ nghĩa. Việc một địa chỉ từng được kiểm chứng không tự chứng minh mọi thông tin danh tính khác hoặc quyền sở hữu địa chỉ ở mọi thời điểm trong tương lai.

Khi nhiều nguồn mâu thuẫn, chính sách phải có thứ tự ưu tiên hoặc cách thất bại rõ ràng. Không tùy tiện lấy giá trị có vẻ đầy đủ nhất chỉ để hoàn tất phản hồi.

### 11.2. Cache và token tạo ra độ trễ của thay đổi

Một token hoặc thông điệp có thể phản ánh snapshot của thuộc tính tại thời điểm phát hành. Sau khi nhân viên chuyển bộ phận hoặc bị thu hồi vai trò, bản đã được phát hành có thể vẫn tồn tại ở client, cache hoặc resource server.

Vì vậy, thay policy không đồng nghĩa dữ liệu đã chia sẻ lập tức biến mất. Cần xác định thời hạn token, cache, cơ chế cập nhật, kiểm tra trạng thái hoặc thu hồi được hỗ trợ và khả năng xử lý tại bên nhận.

Thuộc tính dùng cho quyết định nhạy cảm cần độ mới phù hợp. Việc phát hành tối thiểu vẫn không khắc phục được một claim cấp quyền đã quá cũ.

### 11.3. Người dùng và workload có hợp đồng khác nhau

Workload thường cần định danh dịch vụ, phạm vi sử dụng và những thuộc tính phục vụ authorization cho chính nó. Không sao chép hồ sơ người sở hữu workload, email cá nhân hoặc toàn bộ nhóm của người tạo vào token dịch vụ theo mặc định.

Nếu workload hành động thay người dùng, cần mô hình hóa sự ủy quyền và các chủ thể liên quan theo cơ chế của hệ thống. Không gộp danh tính workload với danh tính con người chỉ vì chúng cùng xuất hiện trong một quy trình.

## 12. Audit quyết định mà không nhân bản dữ liệu nhạy cảm

Bản ghi audit có thể lưu định danh chính sách, phiên bản, bên nhận, loại đường truyền, thời gian, nhóm thuộc tính được cho phép hoặc từ chối và mã lý do phù hợp.

Việc điều tra thường cần biết **đã phát hành loại dữ liệu gì, theo chính sách nào và cho ai**, không nhất thiết cần lưu lại toàn bộ giá trị của từng thuộc tính trong log phổ thông.

Một bản ghi minh họa:

```text
policy=learning-portal-attribute-release
version=example-v1
recipient=learning-portal
channel=identity-profile-response
released=[subjectForRecipient, displayName, preferredLanguage]
withheld=[email]
reason=email_conditions_not_satisfied
decision=partial_release_optional_attribute_omitted
```

Đây là ví dụ về ý nghĩa audit, không phải định dạng bắt buộc. Những tham chiếu tới chủ thể hoặc giao dịch, nếu cần, phải nằm trong cơ chế được phân quyền và có giới hạn dữ liệu thích hợp.

Không log toàn bộ token, header xác thực, mật khẩu, secret hoặc response body chỉ để chứng minh bộ lọc đã chạy. Quyền xem audit, sửa policy và phê duyệt thay đổi cũng cần được quản trị; người có thể sửa chính sách có thể làm thay đổi ranh giới chia sẻ dữ liệu.

## 13. Quản lý thay đổi và các tình huống kiểm chứng

Một thay đổi thêm claim có thể tác động đến quyền riêng tư, kích thước token, hợp đồng ứng dụng và quyết định authorization. Cần có phiên bản, người chịu trách nhiệm, lý do nghiệp vụ, phạm vi triển khai và cách khôi phục phù hợp.

Kiểm chứng cả trường hợp được phép và những ranh giới phải từ chối:

| Tình huống | Kết quả cần kiểm chứng |
|---|---|
| Client hợp lệ chỉ cần định danh và ngôn ngữ | Chỉ có các thuộc tính trong hợp đồng được đáp ứng điều kiện |
| Client yêu cầu thêm dữ liệu không có trong danh sách | Không mở rộng quyền phát hành theo request |
| Client chưa đăng ký hoặc không xác minh được | Không dùng chính sách của client khác |
| Thuộc tính tùy chọn không được phép chia sẻ | Bị bỏ đúng cách; ứng dụng xử lý theo hợp đồng |
| Thiếu thuộc tính bắt buộc hoặc nguồn không đáng tin | Không phát hành một kết quả giả đầy đủ |
| Subject và recipient thuộc tenant không được phép kết nối | Ranh giới tenant được bảo toàn |
| Một điều kiện cho phép và một điều kiện từ chối cùng khớp | Kết quả theo đúng ngữ nghĩa kết hợp chính sách đã công bố |
| API hồ sơ hoặc provisioning có đường lấy dữ liệu khác | Không vô tình vượt giới hạn chia sẻ qua đường phụ |
| Email hoặc tên hiển thị thay đổi | Không nối nhầm tài khoản chỉ dựa trên thuộc tính có thể đổi |
| Hai ứng dụng dùng định danh theo bên nhận | Tính ổn định và phạm vi giữ đúng hợp đồng |
| Vai trò hoặc trạng thái chủ thể vừa thay đổi | Độ mới, cache và vòng đời token được xử lý theo thiết kế |
| Policy mới bị cấu hình lỗi hoặc không tải được | Không fallback sang phát hành tất cả thuộc tính |
| Audit và telemetry được bật | Không chứa credential hoặc bản sao dữ liệu nhạy cảm không cần thiết |
| Workload yêu cầu token | Không tự kèm hồ sơ cá nhân của người sở hữu |

Có thể kiểm chứng bằng dữ liệu tổng hợp thay cho hồ sơ thật khi phù hợp. Đánh giá kết quả ở cả nơi phát hành và nơi nhận: một phản hồi tối thiểu vẫn cần ứng dụng nhận sử dụng đúng, không tự suy ra quyền hoặc đi tìm lại dữ liệu bị giới hạn qua một kênh khác.

Attribute release policy biến nhu cầu “ứng dụng cần biết ai đang truy cập” thành một hợp đồng chia sẻ danh tính có giới hạn. Hợp đồng đó phải chỉ rõ bên nhận, dữ liệu, mục đích, điều kiện, nguồn và vòng đời, để hệ thống IAM hỗ trợ xác thực và cấp quyền mà không phát hành hồ sơ rộng hơn nhu cầu đã được xác định.
