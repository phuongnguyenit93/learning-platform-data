# Directory integration trong kiến trúc PAM

## 1. Tích hợp directory giải quyết vấn đề gì?

**Directory integration** là việc kết nối hệ thống quản lý truy cập đặc quyền (Privileged Access Management — PAM) với nguồn quản lý danh tính, tài khoản, nhóm và các thuộc tính liên quan để hỗ trợ xác thực, đánh giá quyền và quản lý vòng đời truy cập.

Directory thường cho biết một tài khoản tồn tại ở đâu, thuộc đối tượng nào, còn được phép hoạt động không và có những quan hệ thành viên nhóm nào. PAM sử dụng dữ liệu đó theo chính sách để quyết định ai được xem một đối tượng được quản lý, yêu cầu credential, mở phiên quản trị hoặc nhận quyền tạm thời.

Ví dụ, một kỹ sư được chuyển từ nhóm vận hành cơ sở dữ liệu sang đội phát triển. Việc thay đổi nhóm tại directory cần dẫn tới cập nhật quyền PAM phù hợp. Nếu PAM tiếp tục dùng dữ liệu cũ, kỹ sư có thể giữ quyền truy cập production sau khi nhu cầu công việc đã kết thúc.

Tích hợp directory không chỉ là cấu hình một kết nối thành công. Một thiết kế đầy đủ phải làm rõ:

1. Nguồn nào có thẩm quyền cho từng dữ liệu.
2. Cách định danh đối tượng qua thay đổi tên và vòng đời.
3. Cách ánh xạ nhóm hoặc thuộc tính sang quyền PAM.
4. Cách phát hiện và truyền thay đổi tới điểm thực thi.
5. Điều gì xảy ra khi dữ liệu thiếu, trễ hoặc không truy cập được.
6. Bằng chứng nào chứng minh việc cấp và thu hồi đã thực sự có hiệu lực.

Phạm vi bài học gồm tài khoản quản trị, tài khoản dịch vụ và truy cập hạ tầng nhạy cảm. Mục tiêu là hỗ trợ kiểm kê quyền, least privilege, JIT/JEA, quản lý credential và giám sát phiên bằng danh tính có nguồn gốc rõ ràng.

## 2. Phân biệt các chức năng thường bị gộp chung

| Chức năng | Câu hỏi chính | Ví dụ kết quả |
|---|---|---|
| Xác thực | Chủ thể đang đăng nhập là ai? | Một danh tính đã được xác minh theo cơ chế tin cậy |
| Tra cứu danh tính | Đối tượng có thuộc tính và trạng thái gì? | Owner, trạng thái tài khoản, định danh nguồn |
| Phân giải thành viên nhóm | Chủ thể có quan hệ thành viên nào? | Thành viên trực tiếp hoặc quan hệ gián tiếp đã được xác định |
| Đồng bộ | Dữ liệu nào cần được sao chép hoặc cập nhật? | Bản ghi người dùng, nhóm, trạng thái và quan hệ |
| Provisioning | Tài khoản hoặc liên kết nào cần được tạo, sửa, vô hiệu hóa? | Tài khoản PAM được tạo hoặc ngừng sử dụng |
| Ủy quyền | Chủ thể được phép làm gì trong bối cảnh cụ thể? | Cho phép yêu cầu phiên với một role tại một target |
| Thực thi | Điều kiện nào được áp dụng tại đích? | Gán quyền tạm, mở gateway hoặc từ chối kết nối |

Các chức năng có thể được một sản phẩm tích hợp chung, nhưng chúng có cơ chế và bằng chứng khác nhau.

Một người đăng nhập thành công chưa chắc được mở phiên quản trị. Một tài khoản đã được đồng bộ vào PAM chưa chắc có quyền đọc secret. Một nhóm xuất hiện trong directory chưa chắc đủ điều kiện dùng làm nhóm cấp quyền.

Tương tự, việc PAM vô hiệu hóa tài khoản nội bộ chưa chứng minh các phiên quản trị, credential đã cấp hoặc quyền tại hệ thống đích đã được thu hồi.

## 3. Directory, identity provider và giao thức có vai trò khác nhau

Một directory quản lý đối tượng và quan hệ danh tính. Một identity provider cung cấp cơ chế xác thực và bằng chứng danh tính cho ứng dụng theo mô hình tin cậy. Hai vai trò có thể cùng dựa trên một nền tảng, nhưng không nên coi là một chức năng duy nhất.

Một số nhóm cơ chế thường gặp:

| Cơ chế | Mục đích có thể phục vụ | Giới hạn cần làm rõ |
|---|---|---|
| LDAP và các cơ chế bảo vệ kết nối tương ứng | Tra cứu đối tượng, nhóm hoặc xác thực theo khả năng triển khai | Không tự mang đầy đủ ngữ nghĩa phê duyệt hay quyền PAM |
| SAML hoặc OpenID Connect qua identity provider | Đăng nhập liên kết và truyền thông tin danh tính | Claim nhóm có thể không đầy đủ hoặc không phản ánh thay đổi ngay |
| SCIM hoặc API provisioning | Quản lý vòng đời tài khoản và thuộc tính | Không phải bằng chứng xác thực tương tác cho từng phiên |
| API hoặc connector đồng bộ riêng | Đọc trạng thái, quan hệ, thay đổi từ nguồn | Phụ thuộc phạm vi quyền và ngữ nghĩa của từng nguồn |

Không thể thay một chức năng bằng tên giao thức. Chẳng hạn, có đăng nhập liên kết không đồng nghĩa đã có quy trình xóa quyền khi nhân sự nghỉ việc.

Cần xác định cơ chế nào phụ trách xác thực, cơ chế nào cung cấp trạng thái tài khoản, cơ chế nào cho biết thành viên nhóm và cơ chế nào thực thi thay đổi tại PAM.

## 4. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    H["Nguồn quản trị nhân sự hoặc owner dịch vụ"] -->|Sự kiện vòng đời| D["Directory"]
    D -->|Đối tượng, nhóm, trạng thái| C["Connector hoặc bộ đồng bộ"]
    D -->|Dữ liệu danh tính theo kiến trúc| I["Identity provider"]
    U["Người dùng hoặc workload"] -->|Xác thực| I
    I -->|Bằng chứng danh tính| P["PAM: xác thực và chính sách"]
    C -->|Dữ liệu có nguồn gốc và độ mới| P
    M["Ánh xạ role và phạm vi tài nguyên"] --> P
    P -->|Cấp credential hoặc quyền tạm| V["Vault, broker hoặc điểm thực thi"]
    P -->|Mở hoặc quản lý phiên| G["Gateway quản trị"]
    G --> T["Hệ thống đích"]
    V --> T
    C --> A["Audit và giám sát"]
    P --> A
    T --> A
~~~

Đây là mô hình logic. Không phải mọi triển khai đều cần tất cả các thành phần hay cùng một đường truyền dữ liệu.

Các ranh giới tin cậy cần được xác định:

- Connector tin nguồn directory nào và được đọc phạm vi nào.
- PAM tin issuer nào khi nhận bằng chứng danh tính.
- Định danh trong bằng chứng được nối với bản ghi directory bằng cách nào.
- Chính sách PAM nào biến dữ liệu nhóm thành quyền.
- Thành phần nào quản lý credential, grant và phiên sau khi quyết định được cho phép.
- Thành phần nào xác nhận kết quả tại đích.

Nếu directory hoặc tài khoản quản trị directory bị xâm phạm, kẻ tấn công có thể sửa dữ liệu đầu vào của quyết định PAM. Kết nối được mã hóa và connector chỉ đọc không loại bỏ rủi ro từ một nguồn dữ liệu bị thao túng.

## 5. Xác định nguồn có thẩm quyền

### 5.1. Không dùng một nguồn cho mọi loại sự thật

Một mô hình trách nhiệm có thể là:

| Dữ liệu | Nguồn có thẩm quyền trong thiết kế giả định |
|---|---|
| Tình trạng nhân sự | Quy trình nhân sự đã được quản trị |
| Trạng thái tài khoản đăng nhập | Directory hoặc nền tảng danh tính |
| Quan hệ thành viên nhóm | Nguồn quản lý nhóm tương ứng |
| Owner và mục đích tài khoản dịch vụ | Danh mục dịch vụ hoặc quy trình quản trị ứng dụng |
| Role, phạm vi và điều kiện PAM | Chính sách PAM đã được phê duyệt |
| Quyền hiệu lực trên tài nguyên | Cấu hình và cơ chế ủy quyền tại đích |
| Phiên đang hoạt động | Gateway hoặc hệ thống đích có thẩm quyền |

Bảng trên là ví dụ phân công, không phải quy tắc bắt buộc cho mọi tổ chức. Điều cần có là quyền sở hữu dữ liệu rõ ràng và cách giải quyết mâu thuẫn.

Một trường department có thể hỗ trợ phân loại, nhưng không nên tự trở thành bằng chứng đủ để cấp quyền quản trị nếu ai cũng có thể sửa trường đó.

### 5.2. Quy định cách xử lý mâu thuẫn

Giả sử nhân sự đã đánh dấu nghỉ việc nhưng tài khoản directory chưa bị vô hiệu hóa. Thiết kế cần chỉ rõ quy trình nào xử lý khoảng trễ và tín hiệu nào có thể chặn truy cập ngay.

Không nên để từng connector tự lựa chọn dữ liệu có lợi nhất để tiếp tục cấp quyền. Các quyết định có ảnh hưởng đặc quyền cần dựa trên quy tắc đã được thống nhất.

### 5.3. Thuộc tính phải đi kèm nguồn và độ mới

Một giá trị như active=true không đủ nếu không biết:

- Giá trị thuộc đối tượng nào và nguồn nào.
- Lần cuối được xác minh khi nào.
- Phạm vi nào của quá trình đồng bộ đã hoàn tất.
- Có lỗi hoặc giới hạn nào làm kết quả không đầy đủ.

Một lượt sync thành công cho người dùng không chứng minh nhóm và quan hệ thành viên cũng đã được cập nhật thành công.

## 6. Định danh ổn định và liên kết tài khoản

### 6.1. Không dùng tên hiển thị làm khóa quyền

Tên đăng nhập, email, đường dẫn đối tượng và tên nhóm có thể thay đổi. Một tên cũ cũng có thể được cấp lại cho một đối tượng mới.

Nên dùng khóa tham chiếu kết hợp nguồn danh tính với định danh đối tượng phù hợp của nguồn:

~~~text
principal_key = directory_id + source_object_id
group_key     = directory_id + source_group_object_id
~~~

Tính ổn định của định danh phải được kiểm tra theo loại directory và vòng đời thực tế. Không mặc định mọi thuộc tính mang tên ID đều không đổi trong mọi hoạt động di chuyển hay khôi phục.

### 6.2. Đổi tên khác với xóa rồi tạo lại

Nếu một nhóm được đổi tên nhưng vẫn là cùng đối tượng nguồn, ánh xạ theo định danh ổn định có thể được giữ theo chính sách.

Nếu nhóm bị xóa rồi một nhóm mới được tạo với cùng tên, đó là một đối tượng mới. Không tự gán quyền của nhóm cũ cho nhóm mới chỉ vì tên trùng.

Lịch sử nên giữ được:

~~~text
Đối tượng cũ
  → ánh xạ quyền đã áp dụng
  → thời điểm xóa hoặc ngừng hiệu lực
  → việc thu hồi liên quan.

Đối tượng mới cùng tên
  → định danh nguồn mới
  → đánh giá và ánh xạ mới theo thẩm quyền.
~~~

### 6.3. Liên kết người dùng và tài khoản quản trị

Một người có thể có tài khoản làm việc thông thường, tài khoản quản trị và tài khoản quản trị khẩn cấp riêng. Cần giữ liên kết có kiểm soát giữa người chịu trách nhiệm và các tài khoản.

Không suy ra liên kết chỉ bằng cách bỏ hậu tố “-admin” khỏi tên. Cách đặt tên có thể sai, trùng hoặc thay đổi.

Tài khoản dịch vụ cũng không nên được coi như tài khoản nhân sự chỉ vì có thuộc tính owner là một cá nhân. Khi owner nghỉ việc, cần chuyển trách nhiệm và đánh giá quyền của dịch vụ; không mặc định mọi dịch vụ phải bị tắt theo cùng một luồng.

### 6.4. Tránh ghép nhầm danh tính giữa nhiều nguồn

Hai directory có thể có cùng tên đăng nhập. Một issuer mới có thể phát hành cùng giá trị subject như issuer cũ.

Phải ràng buộc định danh với nguồn và phạm vi tin cậy. Nếu kết quả liên kết không rõ ràng, không chọn đối tượng đầu tiên hoặc dùng tài khoản có quyền rộng nhất làm phương án dự phòng.

## 7. Thiết kế ánh xạ nhóm sang quyền PAM

### 7.1. Tách nhóm nguồn khỏi role hiệu lực

Một ánh xạ nên cho biết:

~~~text
Nhóm nguồn đã xác định
  → role PAM
  → tập tài nguyên
  → hành động được phép
  → điều kiện bổ sung
  → giới hạn thời gian hoặc phiên
  → phiên bản và người phê duyệt.
~~~

Ví dụ, thành viên nhóm vận hành cơ sở dữ liệu có thể được phép yêu cầu một phiên chẩn đoán production. Điều đó không nhất thiết cho phép đọc mật khẩu quản trị, sửa cấu hình vault hoặc cấp quyền cho người khác.

Các quyền nên được tách theo chức năng: xem metadata, yêu cầu truy cập, phê duyệt, đọc hoặc sử dụng credential, quản trị policy và xem bằng chứng phiên.

### 7.2. Không tự đồng bộ mọi nhóm thành role

Nếu mọi nhóm được nhìn thấy đều tự tạo quyền PAM, việc tạo một nhóm ở directory có thể trở thành đường cấp quyền đặc quyền ngoài quy trình.

Nên có danh sách ánh xạ được quản trị và chủ thể có quyền phê duyệt. Những nhóm có thể cấp quyền quản trị PAM cần được bảo vệ nghiêm ngặt vì chúng tác động tới chính cơ chế kiểm soát.

### 7.3. Thẩm quyền sửa nhóm là thẩm quyền cấp quyền gián tiếp

Nếu một nhóm được ánh xạ tới role production, người có thể thêm thành viên vào nhóm đó có ảnh hưởng tới quyền production.

Cần kiểm tra:

- Ai sửa thành viên nhóm.
- Ai đổi owner hoặc quyền quản lý nhóm.
- Có cơ chế tự phục vụ tham gia nhóm không.
- Có tự động hóa nào sửa nhóm từ nguồn khác không.
- Có bằng chứng và cảnh báo cho thay đổi nhạy cảm không.

Quyền tại directory và quyền quản trị policy PAM cần được đánh giá cùng nhau. Chỉ bảo vệ giao diện PAM sẽ bỏ sót đường cấp quyền qua nhóm nguồn.

### 7.4. Xử lý xung đột role có quy tắc

Một người có thể thuộc nhiều nhóm. Tổ chức cần quy định cách kết hợp quyền, các điều kiện cấm, phân tách nhiệm vụ và xung đột lợi ích.

Không mặc định hợp của mọi nhóm luôn là kết quả được phép. Một tài khoản bị vô hiệu hóa không nên tiếp tục được cấp quyền chỉ vì còn thuộc một nhóm cho phép.

## 8. Nhóm lồng nhau và tính đầy đủ của quan hệ thành viên

### 8.1. Thành viên trực tiếp khác với thành viên gián tiếp

Ví dụ:

~~~text
Người dùng An
  → Nhóm SRE khu vực
  → Nhóm Vận hành production
  → Role PAM production-operator
~~~

Nếu policy cho phép mở rộng nhóm lồng nhau, An có thể được xét theo đường quan hệ trên. Nếu policy chỉ xét thành viên trực tiếp, kết quả sẽ khác.

Cần ghi rõ loại quan hệ được sử dụng. Không để cấu hình mặc định không được hiểu rõ quyết định phạm vi đặc quyền.

### 8.2. Kiểm soát việc mở rộng quan hệ

Khi phân giải nhóm, cần xác định:

- Loại nhóm đủ điều kiện cho quyết định truy cập.
- Có xét nhóm lồng nhau hay không.
- Giới hạn phạm vi directory hoặc miền tin cậy.
- Cách phát hiện chu trình và giới hạn xử lý.
- Cách xử lý nhóm không đọc được hoặc kết quả bị giới hạn.
- Có cho phép quan hệ qua nhiều nguồn hay không.

Một truy vấn trả về một phần danh sách không được coi là kết quả đầy đủ. Lỗi phân trang hoặc lỗi phân giải nhóm con cần làm thay đổi trạng thái chất lượng dữ liệu.

### 8.3. Claim nhóm trong token không luôn là toàn bộ sự thật

Thông tin nhóm trong bằng chứng đăng nhập có thể là ảnh chụp tại thời điểm phát hành. Tùy cơ chế, danh sách có thể bị giới hạn, được thay bằng tham chiếu hoặc không chứa quan hệ mà PAM cần.

Chữ ký hợp lệ chứng minh dữ liệu đến từ issuer được tin cậy theo cơ chế xác minh; nó không tự chứng minh danh sách nhóm là đầy đủ hay còn mới tại thời điểm quyết định.

Thiết kế cần xác định khi nào dùng claim, khi nào cần tra cứu bổ sung và điều gì xảy ra nếu không thể xác minh điều kiện bắt buộc.

## 9. Bảo vệ kết nối và tài khoản connector

### 9.1. Bảo vệ đường truyền và xác minh máy chủ

Kết nối tới directory phải sử dụng cơ chế bảo mật phù hợp với giao thức và triển khai. Cần xác minh danh tính máy chủ, chuỗi tin cậy và tên đích theo cấu hình.

Nếu dùng một cơ chế nâng cấp kết nối sang bảo mật, cần bảo đảm yêu cầu bảo mật được đáp ứng trước khi gửi dữ liệu nhạy cảm. Không tự tiếp tục qua kênh không được bảo vệ khi bước nâng cấp thất bại.

Không vô hiệu hóa kiểm tra chứng thư chỉ để khắc phục nhanh lỗi kết nối. Quy trình vận hành cần xử lý vòng đời chứng thư và trust configuration.

### 9.2. Connector chỉ có quyền cần thiết

Một connector chỉ đọc người dùng và nhóm thường không cần quyền quản trị toàn directory.

Nên tách danh tính dùng để:

- Đọc và đồng bộ dữ liệu danh tính.
- Thay đổi thành viên nhóm phục vụ JIT nếu có.
- Quản lý credential đặc quyền.
- Quản trị cấu hình tích hợp.

Sự tách biệt giúp giới hạn ảnh hưởng và phân biệt hành động đọc với hành động tạo quyền.

### 9.3. Credential connector cũng thuộc phạm vi PAM

Nếu connector dùng mật khẩu hoặc khóa, credential đó cần owner, phạm vi quyền, bảo vệ lưu trữ, rotation và phương án phục hồi.

Cần tránh vòng phụ thuộc: connector cần đăng nhập directory để lấy credential, nhưng PAM cần chính connector đó để cho phép thao tác phục hồi. Kiến trúc phải có đường phục hồi đã được quản trị cho tình huống này.

### 9.4. Giới hạn truy vấn và bảo vệ đầu vào

Phạm vi tra cứu phải được cấu hình rõ. Không nối trực tiếp dữ liệu do người dùng nhập vào biểu thức truy vấn mà không xử lý phù hợp với cú pháp đang dùng.

Việc mã hóa giá trị cho một bộ lọc và cho một định danh đường dẫn có thể khác nhau. Nên dùng API hoặc thư viện hỗ trợ xây truy vấn an toàn thay vì ghép chuỗi tùy ý.

Nếu connector có thể theo tham chiếu sang nguồn khác, cần biết ranh giới tin cậy và chính sách kết nối tương ứng. Một kết quả phân giải không nên tự mở rộng quyền truy cập mạng hay nguồn tin cậy ngoài phạm vi đã duyệt.

## 10. Đồng bộ, sự kiện và đối soát

### 10.1. Các cách nhận thay đổi

| Cách tiếp cận | Điểm mạnh | Điều cần thiết kế |
|---|---|---|
| Đồng bộ toàn bộ phạm vi | Có thể đối soát trạng thái hiện tại | Tải, thời gian chạy, dữ liệu không đọc được |
| Đồng bộ thay đổi | Giảm lượng dữ liệu cần xử lý | Mốc tiếp tục, mất sự kiện, thay đổi vượt thời gian lưu |
| Sự kiện gần thời điểm thay đổi | Có thể giảm độ trễ phát hiện | Giao trùng, giao muộn, sai thứ tự hoặc mất kết nối |
| Tra cứu tại thời điểm quyết định | Kiểm tra điều kiện gần lúc cấp quyền | Độ trễ, tính sẵn sàng, phạm vi và tính nhất quán nguồn |

Không có cơ chế nào tự loại bỏ nhu cầu đối soát. Sự kiện có thể bị thiếu; một lượt quét có thể không hoàn tất; một lần đọc có thể tới bản sao chưa cập nhật.

### 10.2. Trạng thái đồng bộ cần đủ chi tiết

Nên phân biệt:

~~~text
Lần chạy được bắt đầu
  ≠ truy vấn đã hoàn tất
  ≠ mọi trang đã đọc được
  ≠ quan hệ nhóm đã phân giải đầy đủ
  ≠ thay đổi đã được áp dụng vào PAM
  ≠ quyền tại đích đã được cập nhật.
~~~

Ghi last_sync_success toàn cục có thể che khuất lỗi ở một nhóm nhạy cảm. Độ mới cần được đánh giá theo nguồn, loại dữ liệu và phạm vi liên quan tới quyết định.

### 10.3. Không diễn giải lỗi đọc thành hành động vòng đời

Nếu không đọc được một đối tượng do timeout hoặc quyền connector bị thay đổi, không nên tự kết luận đối tượng đã bị xóa.

Tương tự, không được coi một danh sách nhóm bị thiếu do lỗi là danh sách chắc chắn đầy đủ. Cần giữ trạng thái unknown hoặc incomplete để chính sách xử lý.

Cơ chế xác nhận xóa, mất phạm vi quản lý hoặc ngừng hiệu lực phải được thiết kế theo nguồn dữ liệu. Không dùng một kết quả truy vấn rỗng không rõ nguyên nhân để thực hiện thay đổi hàng loạt không được kiểm soát.

### 10.4. Đồng bộ phải xử lý yêu cầu lặp lại

Một sự kiện có thể được giao nhiều lần. Áp dụng lại cùng thay đổi không nên tạo nhiều tài khoản, nhiều grant hoặc nhiều liên kết quyền.

Cần giữ định danh nguồn, mốc xử lý phù hợp và lịch sử lỗi để có thể chạy lại có kiểm soát. Nếu dùng phiên bản hoặc thứ tự sự kiện, phải hiểu phạm vi của chúng; không mặc định một số thứ tự là thời gian toàn cục cho mọi máy chủ directory.

## 11. Cache, replication và độ trễ thu hồi

### 11.1. Một thay đổi có thể đi qua nhiều lớp

~~~text
Thay đổi vòng đời
  → directory nhận thay đổi
  → bản sao hoặc nguồn connector dùng phản ánh thay đổi
  → PAM nhận và áp dụng dữ liệu
  → cache hoặc bằng chứng đăng nhập cũ ngừng được sử dụng
  → broker/gateway ngừng cấp mới
  → grant, credential và phiên tại đích được xử lý.
~~~

Độ trễ từ lúc thay đổi đến lúc không còn sử dụng được quyền có thể dài hơn chu kỳ sync.

Trong một đường xử lý tuần tự, có thể ước lượng theo tổng các khoảng phát hiện, áp dụng, làm mới và thực thi. Thực tế có các bước song song và nhiều đường truy cập, nên cần đo đường chậm nhất còn cho phép hành động trong phạm vi đang đánh giá.

### 11.2. Đọc lại không luôn bảo đảm đã thấy trạng thái mới nhất

Directory có thể có nhiều bản sao và độ trễ truyền thay đổi. Một lần kiểm tra ở máy chủ khác có thể trả dữ liệu khác trong khoảng chuyển tiếp.

Thiết kế cần hiểu nguồn đọc, hành vi chuyển dự phòng và cách xác minh thay đổi nhạy cảm. Không gọi kết quả “mới nhất” nếu chỉ biết một truy vấn vừa hoàn tất.

### 11.3. Cache có giới hạn theo loại quyết định

Có thể áp dụng yêu cầu độ mới khác nhau cho:

- Xem metadata ít nhạy cảm.
- Yêu cầu credential production.
- Phê duyệt một phiên đặc quyền.
- Sửa policy hoặc cấp quyền quản trị PAM.

Giới hạn cache phải được quyết định theo rủi ro và khả năng vận hành. Không có một thời hạn chung mặc nhiên phù hợp cho mọi hành động.

Một dữ liệu last-known-good có thể giúp vận hành trong giới hạn đã định, nhưng không nên trở thành quyền tiếp tục truy cập vô thời hạn khi nguồn không còn xác minh được.

## 12. Vòng đời joiner, mover và leaver

### 12.1. Joiner: có tài khoản không đồng nghĩa có đặc quyền

Khi người mới tham gia, có thể tạo tài khoản PAM hoặc liên kết danh tính. Quyền production cần dựa trên nhu cầu và ánh xạ đã được phê duyệt.

Không sao chép toàn bộ quyền của một người cùng chức danh chỉ để hoàn thành onboarding nhanh. Những quyền của người mẫu có thể chứa ngoại lệ hoặc quyền không còn cần thiết.

### 12.2. Mover: xử lý quyền cũ cùng quyền mới

Khi chuyển đội, cần đánh giá cả quyền được cấp thêm lẫn quyền phải gỡ.

Nếu chỉ thêm nhóm mới mà giữ nhóm cũ, người dùng có thể tích lũy đặc quyền qua mỗi lần đổi vai trò. Cũng cần rà soát grant trực tiếp trong PAM, quyền ngoài directory và các ngoại lệ còn hiệu lực.

### 12.3. Leaver: ngừng cấp mới chưa đủ

Khi người dùng nghỉ việc hoặc bị đình chỉ, luồng xử lý có thể cần:

1. Chặn xác thực hoặc bằng chứng mới tại nguồn phù hợp.
2. Chặn yêu cầu mới và renew tại PAM.
3. Thu hồi role hoặc grant trong phạm vi quản lý.
4. Xử lý credential đã được cấp hoặc đã bị tiết lộ.
5. Kết thúc phiên liên quan theo chính sách và khả năng thực thi.
6. Kiểm tra quyền trực tiếp, tài khoản phụ và đường truy cập ngoài PAM.
7. Lưu bằng chứng của từng bước và phần còn tồn tại.

Nếu người dùng đã biết mật khẩu của tài khoản chia sẻ, việc xóa họ khỏi nhóm không làm họ quên mật khẩu. Cần xử lý credential và các đường sử dụng tương ứng.

### 12.4. Tài khoản dịch vụ có vòng đời riêng

Tài khoản dịch vụ cần được liên kết với dịch vụ, workload, owner và consumer. Việc nghỉ việc của owner là tín hiệu chuyển trách nhiệm và rà soát, không phải bằng chứng tự động rằng dịch vụ đã hết nhu cầu.

Khi dịch vụ bị loại bỏ, cần xác minh quyền, credential, job, consumer và tài khoản liên quan đã được xử lý. Một trường trạng thái trong directory chưa đủ chứng minh toàn bộ hạ tầng đã được dọn.

## 13. Directory integration hỗ trợ JIT và JEA như thế nào?

### 13.1. Nhóm directory có thể là điều kiện đủ tư cách

Thành viên của một nhóm có thể được phép yêu cầu truy cập, nhưng vẫn phải có lý do, phê duyệt, thời hạn và giới hạn tài nguyên.

~~~text
Nhóm đủ điều kiện
  → yêu cầu công việc cụ thể
  → đánh giá điều kiện
  → phê duyệt nếu cần
  → cấp quyền hoặc credential có giới hạn
  → theo dõi và thu hồi.
~~~

Cách này tránh biến thành viên nhóm thành quyền quản trị thường trực.

### 13.2. Thêm vào nhóm tạm thời không tự làm mọi quyền trở thành tạm thời

Một mô hình JIT có thể thêm tài khoản vào nhóm tại đích rồi gỡ sau thời hạn. Tuy nhiên, token đăng nhập, cache quyền hoặc phiên đã được tạo có thể tiếp tục phản ánh quyền trước đó.

Cần kiểm tra tại đích:

- Khi nào thay đổi nhóm được dùng trong quyết định quyền.
- Có cần đăng nhập hoặc tái xác thực không.
- Khi gỡ nhóm, phiên hiện tại có bị ảnh hưởng không.
- Có quyền hoặc thay đổi bền vững được tạo trong thời gian grant không.

Một tác vụ gỡ nhóm thành công chứng minh quan hệ nhóm đã được thay đổi trong phạm vi quan sát; chưa tự chứng minh mọi phiên đã mất quyền.

### 13.3. JEA cần giới hạn năng lực tại điểm thực thi

Nhóm mang tên “diagnostic-only” không đủ nếu role đích vẫn cho phép sửa cấu hình hoặc tạo quản trị viên mới.

Giới hạn thao tác phải được thực thi bởi role, endpoint, gateway hoặc cơ chế phù hợp tại hệ thống đích. Directory cung cấp tín hiệu danh tính và quan hệ, còn quyền thực tế cần được xác minh riêng.

## 14. Ví dụ cấu hình logic và quyết định truy cập

Các cấu trúc dưới đây là giả mã minh họa, không phải cú pháp của một sản phẩm cụ thể. Định danh và điều kiện là dữ liệu giả định.

~~~yaml
directory_source:
  directory_id: corp-production
  identity_key: source-object-id
  read_scope: approved-operations-population
  membership_mode: explicitly-approved-nested-groups
  require_complete_membership_result: true

role_mapping:
  source_group:
    directory_id: corp-production
    object_id: group-db-operations-042
  pam_role: database-diagnostic-requester
  target_scope: production-database-approved-set
  allowed_action: request-diagnostic-session
  secret_export: false
  approval_required: true
  freshness_policy: production-privileged-access
~~~

Việc secret_export=false biểu diễn một yêu cầu chính sách trong ví dụ; chỉ có hiệu lực nếu sản phẩm và luồng thực thi thật sự hỗ trợ giới hạn đó. Không dùng một trường cấu hình minh họa để suy ra tính năng đã tồn tại.

Một mô hình quyết định:

~~~text
evaluate_access(authentication, requested_action, target):
    subject = verify_and_resolve_subject(authentication)
    if subject is unknown or ambiguous:
        return DENY

    identity_state = load_state_with_provenance(subject)
    if identity_state is disabled or deleted:
        return DENY

    if not freshness_policy_satisfied(identity_state, requested_action):
        return NOT_AUTHORIZED_WITH_CURRENT_EVIDENCE

    membership = resolve_membership_under_configured_scope(subject)
    if membership is incomplete or unverifiable:
        return NOT_AUTHORIZED_WITH_CURRENT_EVIDENCE

    role = resolve_approved_mapping(membership, requested_action, target)
    if role is absent:
        return DENY

    if not required_conditions_verified(subject, role, target):
        return DENY

    record_policy_version_and_evidence_references()
    return PERMIT_FOR_DEFINED_ACTION_AND_SCOPE
~~~

Giả mã nhấn mạnh chất lượng dữ liệu là đầu vào của quyết định. Nó không thay thế toàn bộ cơ chế xác thực, phân tách nhiệm vụ, phê duyệt hay giới hạn quyền tại đích.

Việc truy cập ít nhạy cảm có thể có chính sách độ mới khác. Mọi ngoại lệ cần được thể hiện rõ thay vì âm thầm bỏ điều kiện khi hệ thống gặp lỗi.

## 15. Nhiều directory, nhiều miền và nhiều môi trường

### 15.1. Quan hệ tin cậy không tự cấp quyền PAM

Hai miền có thể có cơ chế tin cậy để phục vụ xác thực, nhưng PAM vẫn cần policy về nguồn danh tính, nhóm và tài nguyên được phép.

Không tự hợp nhất mọi người dùng từ mọi nguồn vào một không gian tên không phân biệt. Danh tính ở môi trường thử nghiệm không nên được nâng thành quyền production chỉ nhờ trùng tên nhóm.

### 15.2. Chuẩn hóa cần giữ ngữ nghĩa nguồn

Cách so sánh tên, chữ hoa/chữ thường và thuộc tính có thể phụ thuộc nguồn. Nên chuẩn hóa theo quy tắc đã xác minh, giữ định danh nguồn và phát hiện mâu thuẫn.

Không dùng quy tắc xử lý chuỗi tùy ý làm cơ sở duy nhất để liên kết danh tính có đặc quyền.

### 15.3. Di chuyển nguồn cần giữ lịch sử và đánh giá quyền

Khi chuyển directory hoặc thay issuer, cùng một người có thể nhận định danh nguồn mới. Cần quy trình liên kết có thẩm quyền, xử lý quyền cũ và giữ khả năng truy vết lịch sử.

Không tự kế thừa quyền chỉ vì email khớp. Cũng không xóa lịch sử cũ để làm báo cáo trông như một đối tượng duy nhất từ trước tới nay.

## 16. Vận hành khi directory hoặc connector gặp lỗi

### 16.1. Phân biệt lỗi nguồn với thay đổi quyền

Các tình huống có ý nghĩa khác nhau:

| Tình huống | Điều có thể kết luận |
|---|---|
| Nguồn xác nhận tài khoản đã vô hiệu hóa | Có thay đổi vòng đời cần thực thi |
| Không kết nối được nguồn | Chưa xác minh được trạng thái hiện tại |
| Truy vấn nhóm bị giới hạn | Kết quả quan hệ có thể không đầy đủ |
| Credential connector hết hiệu lực | Lỗi tích hợp, chưa chứng minh mọi người dùng mất quyền |
| Một bản sao chưa cập nhật | Có thể còn độ trễ truyền thay đổi |
| Policy mapping bị xóa hợp lệ | Quyền qua ánh xạ đó cần được xử lý theo phạm vi |

Không chuyển mọi lỗi thành “người dùng không tồn tại”, cũng không chuyển mọi lỗi thành “giữ nguyên toàn bộ quyền”.

### 16.2. Quy định hành vi theo hành động

Với lần cấp credential hoặc quyền production mới, không xác minh được điều kiện bắt buộc không nên được coi là điều kiện đã đạt.

Đối với phiên đang hoạt động, cần cơ chế theo mức rủi ro: giới hạn tiếp diễn, chặn yêu cầu mới, yêu cầu tái xác thực khi có thể hoặc kết thúc phiên theo quy trình. Cần hiểu ảnh hưởng vận hành và khả năng thực thi.

Không phát sinh một cơ chế tự động cho mọi người dùng trở thành quản trị viên cục bộ khi directory lỗi.

### 16.3. Đường khẩn cấp phải tránh cùng điểm hỏng

Nếu đường break-glass cần chính directory đang lỗi để lấy credential hoặc phê duyệt, nó có thể không phục vụ được mục tiêu phục hồi.

Thiết kế khẩn cấp cần có chủ thể chịu trách nhiệm, cách bảo vệ credential, điều kiện sử dụng, giới hạn phạm vi, bằng chứng và rà soát sau sự kiện.

Khả năng hoạt động độc lập với directory không đồng nghĩa được bỏ mọi lớp bảo vệ. Cần quản trị vòng đời và kiểm tra khả năng sử dụng của đường khẩn cấp theo chính sách.

## 17. Audit và bằng chứng kiểm toán

### 17.1. Các nhóm sự kiện cần liên kết

~~~text
Thay đổi tại directory
  → connector nhận hoặc phát hiện
  → PAM cập nhật trạng thái
  → policy tương ứng được đánh giá
  → quyền, credential hoặc phiên được thay đổi
  → điểm thực thi xác nhận kết quả.
~~~

Mỗi bước cần thời điểm, chủ thể hoặc thành phần thực hiện, phạm vi và kết quả. Nên phân biệt thời điểm sự kiện xảy ra, được nhận và được áp dụng nếu nguồn cho phép.

Một sự kiện minh họa:

~~~json
{
  "event_type": "pam_membership_change_applied",
  "directory_id": "corp-production",
  "subject_object_id": "user-017",
  "group_object_id": "group-db-operations-042",
  "change": "membership_removed",
  "mapping_version": "mapping-v12",
  "pam_effect": "new_diagnostic_session_requests_denied",
  "source_change_reference": "change-081",
  "processing_reference": "sync-204"
}
~~~

Sự kiện này chỉ mô tả việc PAM áp dụng thay đổi tới yêu cầu mới. Nó chưa chứng minh phiên cũ đã kết thúc hoặc secret đã được rotation. Những kết quả đó cần sự kiện và bằng chứng riêng.

### 17.2. Giữ lịch sử, không suy ngược từ trạng thái hiện tại

Danh sách nhóm hiện tại không chứng minh người dùng thuộc nhóm nào khi một phiên được cấp hôm trước.

Bằng chứng cần đủ để tái hiện hoặc giải thích quyết định quá khứ: danh tính nguồn, phiên bản mapping, kết quả phân giải quan hệ, độ mới dữ liệu và điều kiện bổ sung đã được xác minh.

Nếu không lưu được toàn bộ dữ liệu nguồn vì giới hạn dữ liệu hoặc riêng tư, cần thiết kế tham chiếu và bằng chứng phù hợp với yêu cầu kiểm toán, đồng thời nêu giới hạn truy vết.

### 17.3. Không đưa secret vào bằng chứng tích hợp

Log không nên chứa mật khẩu bind, token xác thực nguyên vẹn, khóa riêng hoặc giá trị credential được PAM quản lý.

Thông tin nhóm và cấu trúc tổ chức cũng có thể nhạy cảm. Cần giới hạn người xem, người sửa, việc xuất dữ liệu và thời hạn lưu theo yêu cầu của tổ chức.

## 18. Tình huống xuyên suốt: kỹ sư chuyển khỏi đội production

### 18.1. Bối cảnh

An thuộc nhóm vận hành cơ sở dữ liệu production, được phép yêu cầu phiên chẩn đoán qua PAM. Quyền mở phiên yêu cầu phê duyệt, và thao tác tại đích bị giới hạn bởi role chẩn đoán.

An chuyển sang một đội khác. Nhóm directory phải được cập nhật, nhưng cần xác minh ảnh hưởng tới toàn bộ đường truy cập liên quan.

### 18.2. Dòng thời gian minh họa

Các mốc dưới đây chỉ minh họa cách theo dõi, không phải mục tiêu thời gian chung:

| Thời điểm | Sự kiện | Điều đã được chứng minh |
|---|---|---|
| 10:00 | Nguồn directory xác nhận gỡ thành viên nhóm | Quan hệ tại nguồn được thay đổi trong phạm vi xác nhận |
| 10:02 | Connector phát hiện và hoàn tất phân giải liên quan | PAM đã có dữ liệu đầu vào mới |
| 10:03 | PAM cập nhật ánh xạ hiệu lực | Yêu cầu phiên mới qua role đó bị từ chối |
| 10:04 | Grant tạm tại đích được gỡ và đọc lại | Grant cụ thể đã được xử lý |
| 10:06 | Gateway xác nhận phiên liên quan đã kết thúc | Phiên được theo dõi đã đóng |
| Sau đó | Rà soát quyền trực tiếp và credential đã tiết lộ | Xác định phần truy cập còn tồn tại ngoài đường nhóm |

Không kết luận toàn bộ quyền đã được thu hồi chỉ từ dòng 10:03. Kết quả cần gắn với phạm vi thật sự đã kiểm tra.

### 18.3. Các câu hỏi điều tra

- An có role trực tiếp nào trong PAM không?
- Tài khoản quản trị riêng của An có liên kết đúng với danh tính nhân sự không?
- An có thuộc nhóm cấp quyền khác qua quan hệ lồng nhau không?
- Có credential nào được An đọc và còn dùng được ngoài gateway không?
- Phiên tại đích có tồn tại độc lập với gateway không?
- Có quyền local, khóa hoặc grant ngoài đường tích hợp không?
- Quyết định đã dựa trên nguồn và phiên bản mapping nào?

Nếu còn một đường quyền khác, cần xử lý đường đó thay vì sửa báo cáo để chỉ nhìn nhóm vừa gỡ.

## 19. Kiểm tra triển khai và chỉ số vận hành

### 19.1. Các tình huống cần kiểm chứng

| Tình huống | Kết quả cần quan sát |
|---|---|
| Người dùng hợp lệ nhưng không có mapping | Không nhận quyền PAM chỉ nhờ đăng nhập thành công |
| Tài khoản bị vô hiệu hóa nhưng còn trong nhóm | Không tiếp tục được cấp mới theo nhóm đó |
| Nhóm đổi tên | Mapping theo định danh hoạt động theo thiết kế |
| Nhóm bị xóa rồi tạo lại cùng tên | Không tự kế thừa quyền cũ |
| Quan hệ lồng nhau có chu trình hoặc không đọc đủ | Không coi kết quả thiếu là bằng chứng đầy đủ |
| Directory hoặc connector tạm lỗi | Hành vi cấp mới và phiên hiện tại đúng chính sách |
| Bỏ một thành viên trong nhóm nhạy cảm | Đo được từ thay đổi nguồn tới hiệu lực ở từng lớp |
| Hai nguồn có cùng tên người dùng | Không liên kết nhầm danh tính |
| Rotation credential connector | Kết nối phục hồi đúng và không cần mở rộng quyền |
| Tài khoản dịch vụ đổi owner | Trách nhiệm được chuyển, quyền được rà soát theo nhu cầu |

Các kiểm chứng này đánh giá hành vi triển khai. Việc cấu hình kết nối hiển thị “success” mới chỉ là một phần bằng chứng.

### 19.2. Chỉ số cần theo dõi

- Độ trễ phát hiện và áp dụng thay đổi theo nguồn và loại dữ liệu.
- Thời gian từ ngừng đủ điều kiện tới chặn yêu cầu mới.
- Thời gian từ quyết định thu hồi tới hiệu lực tại đích và phiên.
- Số đối tượng hoặc quan hệ đang ở trạng thái unknown/incomplete.
- Tuổi dữ liệu của các nhóm dùng để cấp quyền nhạy cảm.
- Mapping trỏ tới nhóm đã xóa, ngoài phạm vi hoặc không còn owner.
- Tài khoản PAM có quyền nhưng không có nguồn danh tính hoặc căn cứ hợp lệ.
- Thay đổi thành viên các nhóm quản trị PAM.
- Lỗi xác thực connector và các lượt đối soát chưa hoàn tất.

Không dùng số lượng người dùng đã đồng bộ làm chỉ số duy nhất. Đồng bộ được nhiều đối tượng không chứng minh quyền được thu hẹp hay thu hồi đúng thời hạn.

## 20. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng email hoặc tên nhóm làm khóa quyền duy nhất | Đổi tên hoặc cấp lại tên gây liên kết sai | Ràng buộc nguồn và định danh đối tượng |
| Đăng nhập thành công là được quản trị | Trộn xác thực với ủy quyền | Đánh giá role, scope và điều kiện riêng |
| Mọi nhóm tự tạo role PAM | Tạo nhóm trở thành đường cấp đặc quyền | Mapping có phê duyệt và phạm vi rõ |
| Bỏ qua nhóm lồng nhau | Bỏ sót quyền hiệu lực hoặc cấp sai | Quy định rõ cách phân giải quan hệ |
| Coi claim nhóm là luôn đầy đủ và mới | Dùng dữ liệu thiếu hoặc cũ | Kiểm tra ngữ nghĩa, độ mới và cơ chế bổ sung |
| Connector chỉ đọc nhưng dùng quyền quản trị rộng | Tăng ảnh hưởng nếu connector bị xâm phạm | Tài khoản và quyền đúng chức năng |
| Một lượt sync thành công chứng minh mọi dữ liệu đã mới | Che khuất lỗi theo phạm vi | Theo dõi chất lượng và độ mới chi tiết |
| Gỡ nhóm là coi đã đóng mọi phiên | Quyền còn tồn tại qua token hoặc kết nối | Quản lý grant, credential và phiên riêng |
| Chỉ gỡ quyền qua nhóm, bỏ grant trực tiếp | Người dùng vẫn có đường truy cập khác | Đối soát toàn bộ căn cứ cấp quyền |
| Directory lỗi thì giữ quyền vô hạn | Không còn giới hạn thời gian rủi ro | Chính sách độ mới và xử lý lỗi rõ |
| Break-glass phụ thuộc cùng directory bị lỗi | Không thể phục hồi khi cần | Thiết kế và kiểm tra đường khẩn cấp phù hợp |
| Dùng danh sách nhóm hiện tại để giải thích quá khứ | Không tái hiện được quyết định | Lưu lịch sử và phiên bản bằng chứng |

## 21. Bài tập áp dụng

Một hệ thống PAM cho phép thành viên nhóm Prod-Admins lấy mật khẩu của tài khoản quản trị dùng chung. Tài khoản PAM được liên kết bằng email. Đồng bộ chạy theo lịch, nhưng dashboard chỉ hiển thị lần chạy gần nhất. Khi một người bị gỡ nhóm, PAM chặn yêu cầu lấy mật khẩu mới; các phiên SSH đang mở không được theo dõi.

Hãy phân tích:

1. Vì sao liên kết bằng email có thể gây rủi ro?
2. Cần biết gì về quyền sửa nhóm Prod-Admins?
3. Dashboard hiện tại chưa chứng minh những điều gì?
4. Gỡ nhóm đã tác động tới lớp nào và chưa tác động tới lớp nào?
5. Nếu người dùng đã biết mật khẩu chung, cần thêm biện pháp gì?
6. Làm thế nào để chuyển từ quyền rộng thường trực sang truy cập theo tác vụ?

Hướng phân tích:

- Cần định danh có nguồn rõ và cách xử lý thay đổi, cấp lại hoặc trùng email.
- Người có thể sửa nhóm đang có ảnh hưởng tới quyền lấy credential quản trị.
- Lần chạy gần nhất không chứng minh mọi trang, nhóm và mapping đã được cập nhật.
- Chặn lấy mật khẩu mới chưa vô hiệu hóa bản sao mật khẩu hoặc kết thúc phiên.
- Cần quản lý credential, đường đăng nhập trực tiếp và phiên liên quan theo phạm vi sự kiện.
- Có thể thu hẹp role tại đích, tách quyền yêu cầu khỏi quyền xuất secret, thêm thời hạn, phê duyệt và gateway phù hợp. Mỗi giới hạn phải có thành phần thực thi và bằng chứng.

## 22. Các điểm cần nắm

Directory integration đưa dữ liệu danh tính và vòng đời vào quyết định PAM. Nó chỉ có giá trị kiểm soát khi định danh, nguồn thẩm quyền, mapping, độ mới và cách xử lý lỗi được thiết kế rõ ràng.

Thành viên nhóm là một đầu vào của chính sách. Quyền hiệu lực còn phụ thuộc role PAM, credential, grant, cơ chế tại đích và trạng thái phiên.

Để đánh giá một luồng tích hợp, hãy theo một thay đổi từ nguồn tới chặn yêu cầu mới, xử lý quyền tại đích và trạng thái phiên cuối cùng. Mỗi bước cần có chủ thể chịu trách nhiệm, phạm vi xác nhận và bằng chứng phù hợp.
