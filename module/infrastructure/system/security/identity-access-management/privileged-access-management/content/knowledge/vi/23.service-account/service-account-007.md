# Workload identity

Một ứng dụng cần danh tính để đọc cơ sở dữ liệu, lấy secret, ghi bản sao lưu hoặc triển khai thành phần khác. Cách triển khai quen thuộc là cấp một mật khẩu hoặc khóa truy cập dài hạn rồi đưa nó vào cấu hình ứng dụng. Khi credential bị sao chép, hệ thống đích thường khó phân biệt ứng dụng hợp lệ với người đang cầm bản sao đó.

**Workload identity** là cách nhận diện và xác thực một thực thể phần mềm đang chạy dựa trên danh tính và ngữ cảnh được một nền tảng tin cậy xác nhận. Workload có thể là dịch vụ, container, máy ảo, tác vụ xử lý hoặc job trong pipeline. Sau khi được nhận diện, workload có thể nhận credential hoặc quyền có thời hạn để thực hiện công việc được cho phép.

Trong chương trình Privileged Access Management (PAM), workload identity giúp giảm sự phụ thuộc vào secret dài hạn và làm rõ tài khoản, dịch vụ nào đang sử dụng quyền đặc biệt. Giá trị này chỉ đạt được khi danh tính, quan hệ tin cậy, quyền truy cập và bằng chứng vận hành đều được thiết kế đúng. Token ngắn hạn vẫn có thể mang quyền quá rộng, bị đánh cắp hoặc được cấp cho sai workload.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt workload identity với service account, credential và quyền truy cập.
- Giải thích chuỗi tin cậy từ nền tảng chạy workload tới tài nguyên đích.
- Xác định các điều kiện cần kiểm tra khi chấp nhận một bằng chứng danh tính.
- Thiết kế việc gắn danh tính và cấp quyền theo least privilege.
- Nhận diện rủi ro của metadata endpoint, token bị đánh cắp và quan hệ federation quá rộng.
- Lập kế hoạch chuyển một workload từ secret dài hạn sang danh tính được quản lý.
- Xác định log, kiểm thử và chỉ số cần thiết để chứng minh kiểm soát PAM.

Bài học sử dụng mô hình chung, không giả định mọi nền tảng đều có cùng giao thức, API hoặc khả năng thu hồi.

## 2. Danh tính, tài khoản và credential

### 2.1. Workload là phần mềm đang thực hiện công việc

Ví dụ về workload:

- Một dịch vụ tạo hóa đơn.
- Một job xuất báo cáo chạy cuối ngày.
- Một tiến trình sao lưu.
- Một máy ảo chạy ứng dụng.
- Một pipeline triển khai.
- Một container xử lý sự kiện.

Tên ứng dụng trong danh mục không tự chứng minh tiến trình đang chạy thật sự thuộc ứng dụng đó. Nền tảng cần có cơ chế gắn quá trình thực thi với một danh tính đã được cấp phép.

Ví dụ, nhãn cấu hình `application=invoice` có thể giúp quản lý tài nguyên, nhưng nếu bất kỳ người dùng nào cũng tự đặt nhãn đó thì nhãn không đủ mạnh để cấp quyền đọc dữ liệu tài chính.

### 2.2. Service account là một đối tượng danh tính có thể được gắn cho workload

Service account thường là đối tượng đại diện cho dịch vụ trong một miền quản lý danh tính. Workload identity mô tả rộng hơn cách workload được chứng minh và sử dụng danh tính.

Một service account có thể được dùng theo nhiều cách:

- Ứng dụng giữ mật khẩu dài hạn của tài khoản.
- Nền tảng cấp token có thời hạn cho workload được gắn tài khoản.
- Một hệ thống đích tin cậy bằng chứng từ nền tảng khác và ánh xạ sang tài khoản hoặc vai trò nội bộ.

Vì vậy, sử dụng service account không tự động đồng nghĩa đã áp dụng workload identity theo một mô hình giảm secret dài hạn.

### 2.3. Credential là phương tiện chứng minh danh tính

Credential hoặc bằng chứng xác thực có thể là:

- Token được ký.
- Chứng thư và khóa riêng dùng trong giao thức xác thực.
- Credential tạm thời do một dịch vụ cấp.
- Bằng chứng gắn với phiên hoặc khóa mà workload phải chứng minh đang sở hữu.

Danh tính có thể tồn tại ổn định qua nhiều lần triển khai, trong khi credential thay đổi và hết hạn. Với một dịch vụ có nhiều bản sao, các instance có thể cùng đại diện cho danh tính logic của dịch vụ nhưng vẫn có metadata thực thi riêng để điều tra.

Cần chọn độ chi tiết phù hợp. Nếu mọi dịch vụ dùng chung một danh tính, việc quy trách nhiệm và giới hạn phạm vi ảnh hưởng sẽ yếu. Nếu tạo danh tính bền vững cho từng token tạm thời, inventory lại trở nên khó quản lý mà chưa chắc tăng giá trị kiểm soát.

### 2.4. Xác thực không thay thế cấp quyền

Xác thực trả lời: **Bên gọi được hệ thống nhận diện là ai?**

Cấp quyền trả lời: **Danh tính đó được thực hiện hành động nào trên tài nguyên nào, trong điều kiện nào?**

Một workload được xác thực thành công vẫn có thể phải nhận kết quả từ chối truy cập. Ngược lại, một cấu hình cấp quyền rất hẹp không có giá trị nếu bằng chứng danh tính có thể được giả mạo.

| Khái niệm | Ví dụ minh họa | Điều không nên suy ra |
| --- | --- | --- |
| Workload | Job xuất hóa đơn trong production | Tên job tự chứng minh nguồn gốc |
| Danh tính | Danh tính logic của dịch vụ xuất hóa đơn | Mọi instance của nó đều được phép làm mọi việc |
| Credential | Token có thời hạn hoặc chứng thư | Credential ngắn hạn không thể bị đánh cắp |
| Quyền | Đọc tập dữ liệu hóa đơn đã chốt | Xác thực thành công là được đọc mọi bảng |
| Trust policy | Điều kiện chấp nhận bằng chứng từ một bên phát hành | Tin một issuer nghĩa là tin mọi subject của issuer |

## 3. Chuỗi tin cậy của workload identity

Một mô hình phổ biến có các thành phần sau:

1. **Nền tảng thực thi:** nơi chạy workload và biết workload được triển khai theo cấu hình nào.
2. **Bên phát hành bằng chứng danh tính:** xác nhận danh tính hoặc ngữ cảnh của workload bằng một cơ chế được bảo vệ.
3. **Bên chấp nhận hoặc trao đổi bằng chứng:** kiểm tra bằng chứng rồi ánh xạ sang danh tính hoặc quyền mà hệ thống đích hiểu.
4. **Tài nguyên đích:** thực thi quyết định cấp quyền khi xử lý yêu cầu.
5. **Hệ thống giám sát và quản lý vòng đời:** ghi lại việc gắn danh tính, cấp credential, sử dụng quyền và thay đổi chính sách.

Trong một hệ thống, một thành phần có thể đảm nhiệm nhiều vai trò. Không phải triển khai nào cũng có bước trao đổi token riêng.

~~~mermaid
sequenceDiagram
    participant W as Workload
    participant P as Nền tảng danh tính
    participant B as Bên chấp nhận / trao đổi
    participant R as Tài nguyên đích
    W->>P: Yêu cầu bằng chứng theo danh tính đã gắn
    P-->>W: Bằng chứng có thời hạn và đối tượng nhận
    W->>B: Trình bằng chứng
    B->>B: Kiểm tra nguồn, hiệu lực và điều kiện tin cậy
    B-->>W: Credential hoặc quyền cho đích
    W->>R: Yêu cầu nghiệp vụ kèm bằng chứng được đích chấp nhận
    R->>R: Kiểm tra xác thực và quyền trên tài nguyên
    R-->>W: Kết quả hoặc từ chối
~~~

Các mũi tên không tự tạo ra bảo mật. Mỗi bước dựa vào một cấu hình tin cậy cụ thể:

- Ai được phép gắn danh tính cho workload?
- Nền tảng nhận biết tiến trình nào đang yêu cầu bằng chứng bằng cách nào?
- Bên chấp nhận tin issuer nào và chỉ chấp nhận subject nào?
- Credential đầu ra được dùng ở tài nguyên nào?
- Ai có thể thay đổi mã, cấu hình hoặc đường phân phối danh tính?

Nếu kẻ tấn công được phép sửa workload hợp lệ, chúng có thể chạy mã dưới danh tính hợp lệ mà không cần giả mạo chữ ký token.

## 4. Bài toán khởi tạo niềm tin

### 4.1. Bỏ secret trong mã nguồn chưa giải quyết hết vấn đề

Chuyển một mật khẩu từ mã nguồn sang biến môi trường chỉ thay đổi nơi đặt secret. Chuyển nó vào vault cải thiện khả năng quản lý, nhưng workload vẫn cần một cách xác thực với vault.

Workload identity giải quyết một phần bài toán này bằng cách dùng khả năng nhận diện của nền tảng thay cho một secret ứng dụng tự mang theo. Ví dụ, nền tảng có thể xác nhận máy ảo, tác vụ hoặc job được tạo trong một phạm vi nhất định và được gắn một danh tính cụ thể.

Câu hỏi phải được đẩy tới tận gốc:

> Điều gì khiến bên cấp credential tin rằng yêu cầu này đến từ workload được phép, thay vì một tiến trình khác đang cố mượn danh tính?

Có thể tồn tại credential ở lớp nền tảng như khóa của node, khóa của bên phát hành hoặc chứng thư của agent. Mục tiêu là quản lý chúng tại ranh giới tin cậy phù hợp, không phải tuyên bố hệ thống không có bí mật nào.

### 4.2. Danh tính gắn với nền tảng, không chỉ gắn với lời khai

Một workload tự gửi chuỗi `service=payment` không đủ để nhận quyền của dịch vụ thanh toán. Chuỗi đó phải được gắn với bằng chứng từ nguồn được tin cậy và các điều kiện không thể tùy tiện tự đặt.

Ví dụ, điều kiện có thể liên quan đến:

- Miền quản lý hoặc trust domain.
- Tài khoản, dự án hoặc môi trường thực thi.
- Danh tính được nền tảng gắn cho workload.
- Namespace và đối tượng chạy được nền tảng xác nhận.
- Repository, workflow và môi trường triển khai của một job tự động hóa.

Các trường trên chỉ đáng tin khi issuer thật sự xác nhận chúng và bên chấp nhận hiểu đúng ý nghĩa của chúng. Không phải trường nào trong token cũng là điều kiện tin cậy phù hợp.

### 4.3. Quyền sửa workload là quyền sử dụng gián tiếp danh tính

Một người không được đọc token trực tiếp vẫn có thể chiếm quyền của workload nếu họ có thể:

- Sửa mã hoặc cấu hình mà workload sẽ chạy.
- Gắn danh tính production vào workload do họ kiểm soát.
- Sửa pipeline phát hành.
- Thêm tác vụ gọi API trong một job hợp lệ.
- Thay image hoặc artifact mà quy trình triển khai tin tưởng.

Do đó, inventory và đánh giá PAM phải bao gồm cả đường quản trị workload và đường cấp danh tính. Chỉ bảo vệ secret tại đích mà bỏ qua quyền triển khai sẽ để lại một đường truy cập đặc biệt quan trọng.

## 5. Các mô hình thường gặp

### 5.1. Danh tính do nền tảng thực thi quản lý

Nền tảng chạy workload có thể cung cấp credential tạm thời cho danh tính đã được gắn. Ứng dụng dùng cơ chế được nền tảng hỗ trợ để nhận và làm mới credential.

Điểm cần kiểm tra:

- Danh tính gắn ở mức máy, tác vụ hay workload cụ thể.
- Tiến trình nào trên cùng môi trường có thể lấy credential.
- Người nào được phép gắn, đổi hoặc sử dụng danh tính.
- Credential có giới hạn đối tượng nhận và tài nguyên hay không.
- SDK hoặc thư viện thực sự chọn nguồn credential nào.

Nếu mọi tiến trình trên cùng một máy đều có thể lấy credential của máy, ranh giới bảo vệ không phải từng ứng dụng riêng lẻ trên máy đó. Cần thiết kế môi trường và quyền tương ứng với ranh giới thật.

### 5.2. Federation giữa hai miền tin cậy

Federation cho phép hệ thống đích chấp nhận bằng chứng do một miền khác phát hành, theo chính sách đã cấu hình.

Ví dụ, một job chạy trên nền tảng tự động hóa trình bằng chứng cho hệ thống quản lý tài nguyên. Hệ thống này chỉ cấp quyền triển khai nếu nguồn phát hành, danh tính job và môi trường đều phù hợp.

Federation giúp tránh sao chép khóa đích dài hạn vào nền tảng nguồn. Tuy nhiên, nó chuyển trọng tâm sang chất lượng trust policy. Một chính sách chỉ kiểm tra issuer nhưng cho phép mọi job cùng issuer nhận quyền production sẽ tạo phạm vi tin cậy quá rộng.

### 5.3. Danh tính dùng chứng thư và xác thực hai chiều

Một môi trường có thể cấp chứng thư ngắn hạn cho workload để dùng trong xác thực kết nối, chẳng hạn mTLS.

Cần phân biệt:

- Kết nối được mã hóa.
- Hai bên đã được xác thực theo chính sách chứng thư.
- Danh tính trong chứng thư đã được ánh xạ đúng.
- Yêu cầu nghiệp vụ đã được cấp quyền.

mTLS không tự quyết định dịch vụ nào được đọc dữ liệu hoặc gọi một thao tác quản trị. Việc xác nhận đúng danh tính phía đối tác và áp dụng chính sách cấp quyền vẫn cần được thực hiện.

Chứng thư có thời hạn cũng không tự làm khóa riêng an toàn. Phải bảo vệ nơi tạo, lưu và sử dụng khóa, đồng thời xác định khả năng tác động nếu host hoặc agent bị xâm phạm.

## 6. Kiểm tra bằng chứng danh tính

Một mô hình dùng token được ký cần kiểm tra nhiều hơn việc token “giải mã được”.

### 6.1. Những kiểm tra cốt lõi

| Thành phần | Câu hỏi phải trả lời |
| --- | --- |
| Nguồn phát hành | Issuer có đúng nguồn đã cấu hình và được phép không? |
| Chữ ký | Chữ ký có được xác minh bằng khóa tin cậy và thuật toán được cho phép không? |
| Đối tượng nhận | Audience có chứa đối tượng mà bên xác minh này được cấu hình để chấp nhận không? |
| Subject | Danh tính nguồn có đúng workload hoặc mẫu danh tính đã phê duyệt không? |
| Thời gian | Bằng chứng có hiệu lực theo quy tắc của giao thức và chính sách không? |
| Ngữ cảnh | Môi trường, workflow, tenant hoặc thuộc tính bắt buộc có phù hợp không? |
| Ánh xạ | Bằng chứng này được ánh xạ sang danh tính đích và quyền nào? |
| Ràng buộc sử dụng | Có điều kiện chống dùng sai đích hoặc bằng chứng sở hữu khóa cần kiểm tra không? |

Không phải mọi định dạng có cùng claim hoặc cùng quy tắc xác minh. Phải dùng thư viện và quy trình được giao thức, nền tảng hỗ trợ; bảng trên là tập câu hỏi thiết kế.

### 6.2. Audience không phải danh sách quyền

Audience mô tả đối tượng nhận theo ngữ nghĩa của hệ thống phát hành và xác minh. Nó không thay thế scope, role hoặc chính sách tài nguyên.

Một token dành cho bên trao đổi credential không mặc nhiên được API dữ liệu chấp nhận. Tương tự, một ID token dùng cho một luồng xác thực không tự động là access token hợp lệ cho một API bất kỳ.

Bên nhận phải kiểm tra đúng loại bằng chứng và mục đích sử dụng. Việc bỏ qua khác biệt này dễ dẫn đến chấp nhận nhầm token giữa các hệ thống.

### 6.3. Subject cần đủ hẹp

Ví dụ chính sách ý tưởng:

~~~yaml
# Mô hình khái niệm; không phải cấu hình dùng trực tiếp cho một nhà cung cấp.
trusted_source:
  issuer_ref: approved-ci-issuer
  required_subject: repo:finance/invoice-service:environment:production
  required_audience: production-identity-broker
  required_context:
    deployment_environment: production

mapping:
  target_identity_ref: invoice-deployer-production

authorization:
  allowed_resource_refs:
    - deployment/invoice-service/production
  allowed_actions:
    - publish_approved_release
~~~

Chính sách này vẫn cần kiểm tra nguồn có thực sự bảo vệ được environment và subject đó hay không. Nếu người không được phép vẫn có thể tạo job mang cùng ngữ cảnh, cấu hình so khớp chuỗi chính xác chưa đủ bảo vệ.

Khi phải dùng mẫu thay vì giá trị chính xác, cần giải thích rõ tập đối tượng được bao phủ và kiểm thử các trường hợp gần giống nhưng không được phép. Tránh wildcard rộng trên repository, namespace hoặc môi trường nếu không có lý do kiểm soát được.

### 6.4. Không tự xây một bộ xác minh token sơ sài

Những lỗi phổ biến:

- Chỉ giải mã payload rồi đọc `sub`.
- Chấp nhận thuật toán do token tùy ý đề xuất.
- Không kiểm tra issuer hoặc audience.
- Tin một URL khóa tùy ý lấy từ dữ liệu không tin cậy.
- Cho phép thời gian lệch quá rộng để xử lý lỗi đồng hồ.
- Chấp nhận token đã hết hạn khi hệ thống cấp token gặp sự cố.

Nguồn khóa xác minh phải bắt nguồn từ cấu hình tin cậy. Việc cập nhật khóa, cache và xử lý khóa mới phải theo cơ chế được nền tảng hỗ trợ; không biến thông tin do token tự khai thành quyền tải khóa từ bất kỳ địa chỉ nào.

## 7. Thiết kế quyền theo least privilege

### 7.1. Tách ranh giới danh tính

Một thiết kế thường bắt đầu bằng việc tách:

- Production và các môi trường khác.
- Dịch vụ có chức năng khác nhau.
- Quyền runtime và quyền triển khai.
- Quyền đọc dữ liệu và quyền quản trị.
- Tác vụ thường ngày và tác vụ khôi phục đặc biệt.

Không phải lúc nào cũng cần danh tính riêng cho mọi tiến trình. Cần chọn ranh giới có ý nghĩa đối với trách nhiệm, phạm vi ảnh hưởng và chính sách có thể vận hành được.

Ví dụ, API hóa đơn chỉ cần đọc và ghi bản ghi theo chức năng nghiệp vụ. Job triển khai có thể cập nhật phiên bản dịch vụ nhưng không cần đọc nội dung hóa đơn. Dùng chung danh tính cho hai workload sẽ trộn hai loại đặc quyền rất khác nhau.

### 7.2. Quyền ngắn hạn không có nghĩa quyền tối thiểu

Hai thuộc tính độc lập:

~~~text
Thời gian được sử dụng quyền
            và
Phạm vi hành động / tài nguyên được phép
~~~

Token hiệu lực ngắn nhưng mang quyền quản trị toàn hệ thống vẫn có thể gây tác động lớn ngay khi bị lộ. Ngược lại, credential dài hạn có quyền hẹp vẫn tạo rủi ro tồn tại lâu và khó kiểm soát bản sao.

Thiết kế cần giảm cả thời gian và phạm vi theo nhu cầu thực tế. Phải tính thêm khả năng workload xin credential mới: một tiến trình đã bị chiếm quyền có thể liên tục lấy token mới nếu vẫn giữ quyền nhận danh tính.

### 7.3. Quyền tạo hoặc sử dụng danh tính cũng là đặc quyền

Các thao tác sau cần được đưa vào mô hình PAM:

- Tạo danh tính workload.
- Gắn danh tính vào ứng dụng hoặc tài nguyên thực thi.
- Sửa trust policy.
- Cấp quyền cho danh tính đích.
- Sửa nguồn mã, artifact hoặc pipeline được tin cậy.
- Đọc hoặc điều khiển môi trường có thể lấy credential.

Có thể cần phê duyệt thay đổi, quyền quản trị có thời hạn, phân tách trách nhiệm và lưu bằng chứng cho các thao tác này. Với workload tự động chạy liên tục, không nhất thiết phải yêu cầu con người phê duyệt từng lần lấy token; kiểm soát nên đặt vào cấu hình, điều kiện cấp và vòng đời quyền phù hợp.

## 8. Bảo vệ credential lúc chạy

### 8.1. Bearer token vẫn có thể bị sao chép

Nếu việc sở hữu token đủ để sử dụng, người lấy được token có thể thực hiện hành động trong phạm vi token khi token còn được chấp nhận.

Token có thời hạn giảm một phần cửa sổ khai thác nhưng không ngăn:

- Tiến trình bị xâm phạm sử dụng token ngay.
- Token rò rỉ qua log hoặc thông báo lỗi.
- Một bên có quyền đọc bộ nhớ hoặc filesystem lấy token.
- Tác nhân đang kiểm soát workload liên tục yêu cầu token mới.

Một số mô hình hỗ trợ ràng buộc token hoặc bằng chứng sở hữu khóa, nhưng không nên giả định mọi credential đều có tính chất đó.

### 8.2. Metadata endpoint và nguồn credential cục bộ

Một nền tảng có thể cung cấp credential qua endpoint hoặc agent cục bộ. Khi đó cần xem xét:

- Workload nào truy cập được endpoint.
- Ứng dụng có lỗ hổng khiến bên ngoài điều khiển yêu cầu từ phía server hay không.
- Có ranh giới giữa các workload dùng chung host không.
- Cấu hình mạng và nền tảng có ngăn truy cập ngoài dự kiến không.
- Credential trả về thuộc danh tính và phạm vi nào.

Nếu một ứng dụng bị lợi dụng để gửi yêu cầu tùy ý tới nguồn credential, việc credential không nằm trong file cấu hình vẫn chưa đủ bảo vệ.

Biện pháp cụ thể phụ thuộc nền tảng. Cần đánh giá cơ chế bảo vệ metadata, cách cô lập workload và xử lý yêu cầu từ ứng dụng; không dựa vào việc endpoint “chỉ nội bộ” như bằng chứng an toàn duy nhất.

### 8.3. Thư viện có thể dùng nhầm nguồn credential

Một chuỗi tìm credential có thể thử nhiều nguồn như cấu hình tĩnh, biến môi trường, hồ sơ người dùng và danh tính nền tảng. Thứ tự thực tế phụ thuộc thư viện.

Rủi ro chuyển đổi thường gặp là ứng dụng chạy thành công nhưng vẫn dùng khóa cũ từ biến môi trường. Nhóm triển khai tưởng workload identity đã hoạt động vì lời gọi API không lỗi.

Cần xác minh danh tính hiệu lực bằng log hoặc metadata không chứa secret, đồng thời kiểm tra và loại bỏ nguồn credential cũ theo kế hoạch. Không suy ra nguồn xác thực chỉ từ kết quả thành công.

### 8.4. Không log credential để tiện điều tra

Không ghi token thô, header xác thực, private key hoặc nội dung secret vào log. Với token có cấu trúc, payload cũng có thể chứa dữ liệu nhạy cảm dù không mã hóa.

Để đối soát, có thể ghi:

- ID danh tính logic.
- Issuer đã được chuẩn hóa.
- Tài nguyên hoặc audience được chấp nhận khi phù hợp.
- ID sự kiện phát hành hoặc ID tương quan do hệ thống cung cấp.
- Thời điểm, kết quả và lý do từ chối.
- Instance hoặc phiên bản workload.

Các trường này cũng cần kiểm soát truy cập và thời gian lưu phù hợp. Không đưa toàn bộ claim vào log chỉ vì không ghi chữ ký token.

## 9. Thời hạn, làm mới và thu hồi

### 9.1. Có nhiều thời hạn trong cùng một luồng

Một luồng federation có thể có:

1. Thời hạn của bằng chứng nguồn.
2. Thời hạn của credential được trao đổi.
3. Thời hạn của phiên hoặc kết nối tới tài nguyên.
4. Thời gian cache chính sách và thông tin danh tính.

Các thời hạn không tự động trùng nhau. Bằng chứng nguồn hết hạn không nhất thiết làm credential đầu ra hoặc kết nối đã thiết lập chấm dứt ngay.

Phải hiểu hành vi của từng thành phần trước khi cam kết thời gian thu hồi trong runbook.

### 9.2. Làm mới phải chịu được lỗi nhưng giữ ranh giới kiểm soát

Một thiết kế vận hành thường cần:

- Làm mới trước khi hết hạn với khoảng dự phòng phù hợp.
- Phân tán thời điểm làm mới để tránh mọi instance cùng gọi một lúc.
- Retry có giới hạn và độ trễ tăng dần theo cơ chế được hỗ trợ.
- Đồng bộ thời gian đáng tin cậy.
- Đo lỗi cấp credential và thời gian còn lại trước khi hết hạn.
- Hạn chế nhân bản logic làm mới ở nhiều lớp nếu thư viện đã xử lý đúng.

Nếu bên cấp credential tạm thời không hoạt động, credential còn hiệu lực có thể tiếp tục dùng theo hành vi và chính sách của hệ thống. Không kéo dài hiệu lực của credential đã hết hạn hoặc bỏ kiểm tra chỉ để giữ dịch vụ chạy.

Ứng dụng phải có cách xử lý khi không thể xác thực: báo lỗi đúng, giảm tải hoặc tạm dừng tác vụ theo yêu cầu nghiệp vụ. Việc âm thầm quay về một khóa quản trị dài hạn sẽ phá vỡ mục tiêu kiểm soát.

### 9.3. Ngừng cấp mới và chấm dứt quyền đang tồn tại là hai việc

Khi cần thu hồi quyền:

- Chặn workload nhận credential mới.
- Thu hồi hoặc giảm quyền tại đích theo khả năng nền tảng.
- Xử lý token, phiên hoặc kết nối đã được cấp nếu có cơ chế.
- Cô lập workload hoặc host khi cần.
- Kiểm tra các danh tính phụ và đường truy cập khác.
- Xác nhận qua bằng chứng rằng thao tác mới đã bị từ chối.

Đổi khóa ký của issuer không phải biện pháp thay thế phổ quát cho thu hồi một workload. Nó có thể gây ảnh hưởng rộng và vẫn cần hiểu cách cache khóa, xác minh và phiên hoạt động.

## 10. Tích hợp với PAM và inventory

### 10.1. Workload identity có thể bổ sung cho vault

Có ít nhất hai hướng phổ biến:

- Workload dùng danh tính của mình để lấy secret cần cho một hệ thống cũ.
- Workload dùng danh tính để nhận credential động hoặc truy cập trực tiếp một tài nguyên hỗ trợ cơ chế đó.

Ở hướng thứ nhất, secret tại đích vẫn tồn tại. Cần tiếp tục kiểm kê, giới hạn và luân chuyển nó; việc bỏ secret xác thực với vault không làm secret cơ sở dữ liệu tự biến mất.

Ở hướng thứ hai, cần quản lý vòng đời credential động và chính sách phát hành. Quyền cấp credential hoặc sửa chính sách phát hành có thể là đặc quyền rất quan trọng.

### 10.2. Thông tin cần giữ trong inventory

| Nhóm thông tin | Ví dụ |
| --- | --- |
| Danh tính logic | Dịch vụ, owner, môi trường, mã định danh ổn định |
| Nguồn tin cậy | Issuer, trust domain, nền tảng thực thi |
| Cách gắn danh tính | Đối tượng triển khai nào nhận danh tính, ai được phép thay đổi |
| Điều kiện chấp nhận | Subject, audience, ngữ cảnh bắt buộc, phiên bản trust policy |
| Danh tính đích | Tài khoản, vai trò hoặc principal sau ánh xạ |
| Quyền và tài nguyên | Hành động được phép, tài nguyên đích, giới hạn điều kiện |
| Credential và phiên | Loại, cơ chế cấp, thời hạn theo cấu hình, cách làm mới |
| Thu hồi | Cách ngừng cấp mới, xử lý quyền hoặc phiên đang tồn tại |
| Bằng chứng | Sự kiện triển khai, cấp credential, từ chối và sử dụng quyền |

Không cần lưu một bản ghi tài khoản bền vững cho mỗi token. Có thể lưu sự kiện cấp và liên kết token hoặc phiên với danh tính theo khả năng nền tảng, trong khi inventory giữ cấu hình và quan hệ bền vững.

### 10.3. Bằng chứng kiểm toán cho truy cập máy

Với tài khoản quản trị viên, session recording có thể là một nguồn bằng chứng. Với workload, bằng chứng thường đến từ sự kiện cấp credential, log API, hoạt động trên tài nguyên và thay đổi cấu hình.

Một chuỗi đối soát có ích là:

~~~text
Thay đổi được phê duyệt
    -> phiên bản workload được triển khai
    -> danh tính được gắn
    -> bằng chứng được chấp nhận
    -> quyền được cấp
    -> thao tác trên tài nguyên
~~~

Khả năng liên kết có thể không đầy đủ trong mọi nền tảng. Phải ghi rõ khoảng trống và chất lượng nguồn, thay vì tuyên bố truy vết hoàn chỉnh chỉ vì các hệ thống đều có log.

## 11. Kế hoạch chuyển đổi từ secret dài hạn

### Bước 1: Lập bản đồ phụ thuộc

Xác định workload, môi trường, tài nguyên, credential hiện tại, owner và mọi consumer dùng chung.

Kiểm tra cả tác vụ ít chạy như khôi phục, xuất dữ liệu cuối kỳ và job vận hành thủ công. Nếu chỉ chuyển luồng chính, secret cũ có thể vẫn cần cho một consumer chưa biết.

### Bước 2: Chọn danh tính và ranh giới quyền

Thiết kế danh tính cho runtime, triển khai hoặc khôi phục theo nhu cầu. Xác định quyền tối thiểu và tài nguyên chính xác.

Ví dụ, job xuất báo cáo chỉ được đọc tập dữ liệu đã phê duyệt và ghi vào vùng đích của nó. Nó không cần quyền sửa chính sách cấp quyền hoặc tạo tài khoản mới.

### Bước 3: Cấu hình quan hệ tin cậy

Chọn nguồn phát hành đã được quản lý, điều kiện chấp nhận và ánh xạ danh tính đích. Xác định ai có thể sửa các điều kiện đó.

Lưu cấu hình qua quy trình thay đổi có thể rà soát. Một thay đổi wildcard trong trust policy có thể mở rộng quyền đáng kể dù không sửa chính sách tài nguyên.

### Bước 4: Tích hợp cơ chế nhận và làm mới

Dùng cơ chế được nền tảng hỗ trợ, hạn chế ứng dụng tự xử lý token khi không cần thiết.

Thử nghiệm:

- Khởi động mới.
- Làm mới qua nhiều chu kỳ.
- Mất kết nối tạm thời tới nguồn cấp.
- Thay khóa hoặc chứng thư theo quy trình hỗ trợ.
- Mở rộng nhiều instance.
- Chạy đủ dài để vượt thời hạn credential ban đầu.

Một phép thử API ngay sau khởi động chưa chứng minh cơ chế làm mới hoạt động.

### Bước 5: Kiểm thử trường hợp được phép và bị cấm

Không chỉ kiểm tra “đã đọc được dữ liệu”. Cần kiểm tra workload hoặc ngữ cảnh sai không được nhận quyền.

Tách lỗi xác thực khỏi lỗi cấp quyền để biết chính sách nào đã thực sự chặn yêu cầu.

### Bước 6: Chuyển traffic hoặc tác vụ có kiểm soát

Quan sát danh tính hiệu lực, lỗi xác thực và kết quả nghiệp vụ. Đặt tiêu chí dừng và phương án khôi phục được phê duyệt.

Nếu phải giữ credential cũ trong giai đoạn chuyển đổi, ghi rõ phạm vi, owner, hạn kết thúc và bằng chứng sử dụng. Tránh để cơ chế dự phòng tồn tại vô thời hạn.

### Bước 7: Thu hồi secret cũ và đối soát

Sau khi mọi consumer đã chuyển:

- Ngừng khả năng dùng credential cũ theo quy trình của đích.
- Kiểm tra nguồn cấu hình và nơi phân phối để loại bỏ bản sao còn được quản lý.
- Theo dõi lỗi từ consumer chưa phát hiện.
- Xác nhận ứng dụng không quay về nguồn credential cũ.
- Cập nhật inventory, runbook và bằng chứng.

Không tuyên bố đã thu hồi toàn bộ chỉ vì xóa một biến môi trường ở một phiên bản triển khai.

## 12. Ví dụ: job xuất hóa đơn

### 12.1. Trước chuyển đổi

Job `invoice-export` chạy trong production. Một khóa truy cập dài hạn được đưa vào cấu hình để đọc dữ liệu hóa đơn và ghi tệp kết quả.

Các vấn đề:

- Staging từng dùng chung khóa.
- Khóa có quyền đọc nhiều vùng dữ liệu hơn nhu cầu.
- Không biết bản sao nào còn tồn tại trong các cấu hình cũ.
- Log tài nguyên chỉ ghi tài khoản chung, khó phân biệt job.
- Luân chuyển khóa phụ thuộc vào cập nhật nhiều nơi.

### 12.2. Thiết kế đích

~~~text
Workload:
  invoice-export, production

Danh tính nguồn:
  danh tính riêng được gắn cho job production

Quan hệ tin cậy:
  nguồn phát hành được phê duyệt
  subject đúng job production
  audience đúng bên chấp nhận
  chỉ môi trường production được ánh xạ sang danh tính đích

Quyền đích:
  đọc tập dữ liệu hóa đơn đã chốt
  ghi vùng kết quả của invoice-export
  không sửa chính sách hoặc tài khoản

Vận hành:
  credential có thời hạn
  cơ chế làm mới được hỗ trợ
  log cấp quyền và thao tác đích
  runbook ngừng cấp mới và xử lý phiên đang tồn tại
~~~

Workload staging dùng danh tính và quyền riêng. Nó không được nhận credential production dù dùng cùng một mã nguồn.

### 12.3. Các phép thử cần có

| Phép thử | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- |
| Job production hợp lệ đọc dữ liệu đã cho phép | Thành công | Log danh tính hiệu lực và thao tác đích |
| Job staging xin quyền production | Bị từ chối | Sự kiện từ chối đúng điều kiện môi trường hoặc subject |
| Bằng chứng dành cho bên nhận khác | Bị từ chối | Lỗi kiểm tra audience ở bên xác minh phù hợp |
| Danh tính hợp lệ đọc tài nguyên ngoài phạm vi | Bị từ chối | Log cấp quyền tại tài nguyên |
| Job chạy qua nhiều chu kỳ credential | Tiếp tục hoạt động nhờ làm mới hợp lệ | Chuỗi sự kiện và kết quả nghiệp vụ |
| Chặn cấp mới cho job | Không nhận được credential mới | Log phát hành và thử lại sau thời điểm chặn |
| Dùng credential cũ sau thu hồi theo cơ chế đích | Bị từ chối theo hành vi đã xác định | Log đích, kèm giới hạn phiên hoặc cache nếu có |

Nếu một phép thử âm tính thất bại do lỗi mạng trước khi tới điểm xác minh, chưa thể dùng nó để chứng minh chính sách danh tính chặn đúng yêu cầu. Cần biết yêu cầu đã đi đến đâu và thành phần nào đưa ra quyết định.

## 13. Vận hành và ứng phó sự cố

### 13.1. Khi có dấu hiệu token bị lộ

Không chỉ chờ token hết hạn. Cần xác định:

- Token hoặc credential thuộc danh tính nào.
- Bị lộ ở đâu và workload còn bị kiểm soát bởi kẻ tấn công không.
- Có thể xin credential mới không.
- Tài nguyên và hành động nào có thể bị ảnh hưởng.
- Có token hoặc phiên đầu ra khác được tạo từ bằng chứng đó không.
- Cần cô lập, giảm quyền hoặc chấm dứt phiên bằng cơ chế nào.

Lưu bằng chứng phù hợp nhưng không sao chép token đang có hiệu lực vào ticket thông thường.

### 13.2. Khi bên phát hành hoặc broker gặp sự cố

Phân biệt:

- Workload chưa có credential.
- Workload có credential còn hiệu lực.
- Workload cần làm mới nhưng nguồn cấp không hoạt động.
- Tài nguyên đích không thể xác minh bằng chứng do vấn đề khóa hoặc cấu hình.

Mỗi tình huống có thể có hành vi khác nhau. Runbook phải dựa trên thời hạn và khả năng thực tế của hệ thống. Tránh một cơ chế “khẩn cấp” bỏ qua kiểm tra cho mọi workload vì sẽ mở quyền đúng lúc hệ thống khó quan sát nhất.

Nếu có phương án truy cập khẩn cấp được tổ chức chấp thuận, nó cần phạm vi, thời hạn, owner và bằng chứng riêng; không nên ẩn trong logic tự động của ứng dụng.

### 13.3. Khi nền tảng thực thi bị xâm phạm

Danh tính workload phụ thuộc một phần vào độ tin cậy của nền tảng. Nếu kẻ tấn công kiểm soát node, agent hoặc quyền quản trị nền tảng, chúng có thể tiếp cận credential hoặc tạo yêu cầu dưới danh tính workload, tùy kiến trúc.

Biện pháp xử lý có thể cần:

- Cô lập hạ tầng bị ảnh hưởng.
- Chặn gắn hoặc cấp danh tính từ phạm vi đó.
- Đổi hoặc thu hồi credential nền tảng có liên quan.
- Xem lại sự kiện cấp quyền và thao tác đích.
- Khôi phục workload từ nguồn tin cậy.

Chỉ thay token ứng dụng mà giữ nguyên môi trường đã bị kiểm soát thường không loại bỏ được nguyên nhân.

## 14. Chỉ số kiểm soát

Chỉ số phải có mẫu số và phạm vi rõ ràng.

### 14.1. Tỷ lệ workload đã chuyển cơ chế xác thực

~~~text
Số workload trong phạm vi đã xác minh dùng danh tính được quản lý
/
Tổng số workload được xác định cần chuyển trong phạm vi
~~~

“Đã xác minh” nên bao gồm danh tính hiệu lực, cơ chế làm mới và trạng thái credential cũ. Chỉ có cấu hình mới chưa đủ.

### 14.2. Tình trạng trust policy

Theo dõi:

- Quan hệ tin cậy không rõ owner.
- Điều kiện subject hoặc môi trường quá rộng.
- Danh tính đích dùng chung giữa các ranh giới không phù hợp.
- Chính sách chưa có kiểm thử âm tính.
- Thay đổi chính sách không có bằng chứng rà soát.

Không có một số lượng wildcard duy nhất phản ánh đầy đủ rủi ro; cần hiểu wildcard bao phủ đối tượng nào và chúng có thể nhận quyền gì.

### 14.3. Sức khỏe phát hành và làm mới

Theo dõi lỗi cấp credential, lỗi làm mới, độ trễ, lỗi đồng hồ và các đợt tăng đột biến. Đối chiếu với kết quả nghiệp vụ để tránh tình huống credential được cấp thành công nhưng ứng dụng vẫn không truy cập được tài nguyên cần thiết.

### 14.4. Khả năng thu hồi

Đo và diễn tập thời gian từ khi quyết định chặn tới khi:

- Không thể nhận credential mới.
- Thao tác mới tại đích bị từ chối.
- Phiên hoặc kết nối cũ được xử lý theo mục tiêu kiểm soát.

Các mốc có thể khác nhau. Báo cáo một con số “thu hồi tức thì” khi chỉ mới chặn phát hành sẽ gây hiểu nhầm.

## 15. Bài thực hành thiết kế

Một hệ thống có ba workload:

- `orders-api` chạy liên tục trong production.
- `orders-deployer` triển khai phiên bản mới từ pipeline.
- `orders-recovery` chỉ chạy khi khôi phục dữ liệu.

Hiện tại cả ba dùng một tài khoản có quyền đọc dữ liệu, sửa dịch vụ và quản trị một vùng lưu trữ.

### Yêu cầu

1. Đề xuất ranh giới danh tính cho ba workload.
2. Ghi mục đích, owner, môi trường và tài nguyên của mỗi danh tính.
3. Mô tả nguồn bằng chứng và điều kiện để mỗi workload được nhận quyền.
4. Liệt kê người hoặc hệ thống có thể sửa workload hoặc gắn danh tính.
5. Thiết kế các phép thử từ chối cho môi trường, subject và tài nguyên sai.
6. Mô tả cách làm mới và hành vi khi nguồn cấp credential không hoạt động.
7. Xác định cách chặn cấp mới và cách xử lý quyền đã cấp.
8. Lập kế hoạch thu hồi tài khoản hoặc credential dùng chung cũ.

### Hướng giải thích tham khảo

- `orders-api` cần quyền runtime theo dữ liệu nghiệp vụ, không cần quyền triển khai.
- `orders-deployer` cần quyền triển khai ở phạm vi dịch vụ được giao, không mặc nhiên cần đọc dữ liệu khách hàng.
- `orders-recovery` cần quy trình kích hoạt, phạm vi khôi phục và bằng chứng riêng; không nên bị coi là thừa chỉ vì ít hoạt động.
- Quyền sửa pipeline hoặc gắn danh tính production phải được xem như đường sử dụng đặc quyền gián tiếp.
- Điều kiện tin cậy cần phân biệt đúng workload và môi trường, đồng thời dựa trên thuộc tính được nguồn tin cậy bảo vệ.
- Việc làm mới phải được kiểm thử qua thời hạn credential ban đầu.
- Thu hồi credential cũ chỉ thực hiện sau khi đã kiểm tra mọi consumer và chuẩn bị xử lý sự cố.

Bài thực hành đạt khi thiết kế giải thích được không chỉ ai truy cập thành công, mà cả vì sao workload hoặc ngữ cảnh sai bị từ chối và phải dùng bằng chứng nào để kiểm tra.

## 16. Câu hỏi tự kiểm tra

**1. Workload identity có nghĩa là hệ thống không còn secret nào không?**

Không. Nó có thể giảm secret dài hạn mà ứng dụng phải tự quản lý. Nền tảng, bên phát hành hoặc đích cũ vẫn có thể sử dụng khóa, chứng thư và secret cần được bảo vệ.

**2. Token hợp lệ chữ ký đã đủ để cấp quyền chưa?**

Chưa. Cần kiểm tra nguồn, mục đích nhận, hiệu lực, subject, ngữ cảnh và chính sách ánh xạ, rồi áp dụng quyền tại tài nguyên.

**3. Vì sao token ngắn hạn vẫn có thể gây rủi ro lớn?**

Nó có thể mang quyền rộng, bị dùng ngay khi lộ, hoặc được xin lại liên tục nếu workload vẫn bị kiểm soát.

**4. Audience có thay thế quyền truy cập tài nguyên không?**

Không. Audience giúp kiểm tra đối tượng nhận theo cơ chế xác thực. Quyền đọc, ghi hoặc quản trị tài nguyên cần được cấp và thực thi riêng.

**5. Vì sao quyền sửa workload cần nằm trong đánh giá PAM?**

Người sửa được mã hoặc cấu hình có thể làm workload thực hiện hành động bằng danh tính hợp lệ. Đây là một đường sử dụng quyền gián tiếp.

**6. Làm sao biết ứng dụng thật sự đã chuyển khỏi khóa cũ?**

Kiểm tra danh tính hiệu lực, nguồn credential được sử dụng, hoạt động qua các chu kỳ làm mới và kết quả sau khi credential cũ bị thu hồi theo kế hoạch.

**7. Chặn cấp token mới có chấm dứt mọi truy cập ngay không?**

Không nhất thiết. Credential đầu ra, token đã cấp, cache hoặc kết nối có thể còn hiệu lực theo cơ chế riêng. Runbook phải xác định và kiểm thử các giới hạn đó.

## 17. Checklist áp dụng

- Có danh tính và owner rõ ràng cho workload trong phạm vi.
- Ranh giới production, runtime, triển khai và khôi phục được xem xét phù hợp.
- Nguồn phát hành và nguồn khóa xác minh được cấu hình tin cậy.
- Bằng chứng được kiểm tra đúng loại, issuer, audience, subject và hiệu lực.
- Quan hệ tin cậy chỉ bao phủ workload và ngữ cảnh cần thiết.
- Quyền tại tài nguyên được giới hạn theo công việc thực tế.
- Quyền gắn danh tính và sửa workload được quản lý như đường đặc quyền.
- Credential không bị đưa vào log hoặc kho lưu trữ không phù hợp.
- Cơ chế làm mới và lỗi nguồn cấp đã được kiểm thử.
- Có kiểm thử từ chối, không chỉ kiểm thử thành công.
- Credential cũ có kế hoạch thu hồi và bằng chứng hoàn tất.
- Inventory, log và runbook mô tả được chuỗi cấp và sử dụng quyền.

Workload identity tạo nền tảng để phần mềm nhận quyền theo danh tính được kiểm chứng, thay vì phụ thuộc vào một secret dài hạn được sao chép giữa nhiều nơi. Trong PAM, nền tảng đó cần đi cùng quyền tối thiểu, quản lý quan hệ tin cậy, bảo vệ môi trường thực thi và bằng chứng về toàn bộ vòng đời truy cập.
