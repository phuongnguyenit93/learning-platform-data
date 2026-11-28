# Named admin account

## Mục tiêu bài học

Trong chương **Tài khoản đặc quyền**, named admin account là **tài khoản quản trị được cấp riêng cho một cá nhân xác định**, thay vì để nhiều người cùng sử dụng một tài khoản quản trị chung.

Trong phạm vi **Privileged Access Management (PAM)**, việc gắn tài khoản với cá nhân là điểm khởi đầu để kiểm kê quyền, giới hạn đặc quyền, kiểm soát credential, giám sát phiên và giữ bằng chứng phục vụ kiểm toán, ứng phó sự cố. Tên tài khoản có chứa tên người dùng chưa đủ để đạt những mục tiêu đó.

Sau bài học, bạn có thể:

- Phân biệt tài khoản quản trị cá nhân với tài khoản thường, tài khoản dùng chung và tài khoản dịch vụ.
- Giải thích những lợi ích và giới hạn của việc gắn tài khoản với một người.
- Thiết kế vòng đời tài khoản, quyền và credential theo least privilege, JIT/JEA.
- Xác định bằng chứng cần để liên kết một yêu cầu quản trị với người dùng và hành động ở hệ thống đích.
- Xử lý việc chuyển vị trí, nghỉ việc hoặc nghi tài khoản bị chiếm quyền mà không chỉ dựa vào đổi mật khẩu.

## 1. Điều gì làm một tài khoản trở thành named admin account?

Một named admin account cần có ít nhất ba đặc điểm:

1. **Có người được cấp sử dụng rõ ràng:** tại một thời điểm, tài khoản được giao cho một cá nhân xác định.
2. **Có khả năng quản trị:** tài khoản có quyền hoặc có đường nhận quyền thực hiện những thao tác quản trị trong phạm vi được giao.
3. **Có liên kết danh tính được quản lý:** tổ chức có thể đối chiếu tài khoản với hồ sơ cá nhân, người bảo trợ và vòng đời truy cập.

Ví dụ, một kỹ sư có thể được cấp hai tài khoản:

| Tài khoản minh họa | Mục đích | Quyền dự kiến |
| --- | --- | --- |
| `engineer-a` | Công việc hằng ngày | Thư điện tử, tài liệu và công cụ thông thường |
| `engineer-a-admin` | Công việc quản trị được giao | Chỉ các khả năng quản trị phù hợp, có thể được cấp theo thời hạn |

Hậu tố `-admin` chỉ giúp nhận diện mục đích. Một tài khoản mang tên cá nhân nhưng được cả nhóm biết mật khẩu vẫn đang bị sử dụng như tài khoản chung. Ngược lại, tên hiển thị không nhất thiết chứa họ tên thật nếu hệ thống có định danh ổn định và ánh xạ cá nhân đáng tin cậy.

Tài khoản quản trị cá nhân cũng không nhất thiết có quyền mạnh thường trực. Nó có thể tồn tại lâu dài nhưng chỉ nhận vai trò quản trị khi có nhiệm vụ và đáp ứng điều kiện cấp quyền.

## 2. Phân biệt với các loại tài khoản khác

| Loại tài khoản | Chủ thể hoặc cách sử dụng | Điểm phân biệt |
| --- | --- | --- |
| Tài khoản thường của cá nhân | Một người làm công việc hằng ngày | Không mặc định cần quyền quản trị |
| Named admin account | Một cá nhân thực hiện nhiệm vụ quản trị | Có liên kết cá nhân và mục đích quản trị rõ ràng |
| Tài khoản quản trị dùng chung | Nhiều người cùng sử dụng một principal kỹ thuật | Cần cơ chế bổ sung để liên kết từng lượt dùng với người thực tế |
| Tài khoản tích hợp sẵn | Tài khoản do hệ thống tạo cho quản trị ban đầu hoặc chức năng đặc biệt | Cách quản lý phụ thuộc nền tảng; không mặc nhiên là tài khoản cá nhân |
| Tài khoản dịch vụ hoặc workload | Phần mềm thực thi công việc tự động | Cần chủ sở hữu nhưng không được đồng nhất với một người đang đăng nhập |
| Tài khoản khẩn cấp | Sử dụng trong điều kiện khôi phục hoặc sự cố xác định | Có quy trình truy cập, cảnh báo và xem xét riêng; có thể là cá nhân hoặc kỹ thuật tùy thiết kế |

Các loại trên có thể giao nhau theo mục đích, nhưng không nên đánh đồng. Một tài khoản quản trị cá nhân không nên trở thành credential chạy dịch vụ chỉ vì người đó đang phụ trách ứng dụng.

Nếu job tự động dùng tài khoản của một DBA hoặc kỹ sư, khi người đó chuyển vị trí việc thu hồi sẽ dễ làm gián đoạn job. Đồng thời, log mang tên người không còn phân biệt được hành động cá nhân với hành động tự động.

## 3. Lợi ích chính: quản trị quyền và quy trách nhiệm theo cá nhân

### 3.1. Có thể cấp và thu hồi độc lập

Khi mỗi người có tài khoản riêng, có thể thay đổi quyền của một người mà không cần phát lại cùng một credential cho cả nhóm.

Ví dụ:

- Người A chỉ quản trị ứng dụng A.
- Người B chỉ quản trị môi trường thử nghiệm.
- Người C được cấp quyền production trong một nhiệm vụ đã xác định.

Mỗi người có phạm vi và thời hạn riêng. Việc một người hết nhu cầu không cần kéo dài quyền cho họ chỉ để tránh ảnh hưởng những người khác.

### 3.2. Hỗ trợ liên kết hành động với danh tính

Log ở hệ thống đích có thể ghi principal riêng của người thực hiện. Khi được đối chiếu với xác thực, yêu cầu quyền và phiên, bằng chứng này giúp điều tra rõ hơn so với một tài khoản chung không có ánh xạ.

Tuy nhiên:

> Log mang tên một người chứng minh hệ thống ghi nhận tài khoản đó; tự nó chưa chứng minh người đó trực tiếp thực hiện mọi hành động.

Credential bị đánh cắp, phiên bị chiếm, máy quản trị bị xâm nhập hoặc việc chia sẻ tài khoản đều có thể làm sai lệch suy luận về chủ thể thực tế.

### 3.3. Hỗ trợ rà soát nhu cầu quyền

Có thể yêu cầu người quản lý hoặc chủ sở hữu tài nguyên xác nhận:

- Người này còn làm nhiệm vụ quản trị không?
- Quyền trên từng môi trường có còn cần thiết không?
- Có nhiệm vụ nào chỉ cần quyền tạm thời không?
- Có quyền kế thừa hoặc đường tự cấp quyền nào chưa được xem xét không?

Việc tài khoản đã tồn tại lâu không phải bằng chứng rằng quyền hiện tại vẫn phù hợp.

## 4. Những giới hạn cần hiểu ngay từ đầu

### 4.1. Có tên riêng không làm quyền trở nên tối thiểu

Một tài khoản cá nhân giữ quyền quản trị toàn tổ chức vẫn có phạm vi tác động lớn. Nếu bị chiếm quyền, người tấn công có thể sử dụng tập khả năng đó trong giới hạn hệ thống cho phép.

Cần kiểm tra quyền thực tế, không chỉ kiểm tra rằng “mỗi người đã có tài khoản riêng”.

### 4.2. Có tài khoản riêng không ngăn được chia sẻ

Người dùng có thể chia sẻ mật khẩu, khóa, token hoặc một phiên đang mở. Các bản sao credential có thể xuất hiện trong công cụ quản trị, file kết nối hoặc ghi chú.

Cơ chế xác thực, quản lý bí mật, bảo vệ thiết bị và phát hiện sử dụng bất thường phải hỗ trợ nguyên tắc không chia sẻ. Quy định trên giấy không đủ.

### 4.3. Tách hai tài khoản chưa chắc tách được mọi đường chiếm quyền

Nếu tài khoản thường có thể tự đặt lại credential quản trị, quản lý mọi yếu tố xác thực của tài khoản quản trị hoặc điều khiển thiết bị đang giữ phiên quản trị, việc tách tài khoản có thể không đạt mức cô lập mong muốn.

Cần xem các phụ thuộc:

- Nhà cung cấp danh tính và cơ chế khôi phục.
- Thiết bị, trình duyệt và nơi lưu phiên.
- Người hoặc nhóm được quyền hỗ trợ đặt lại tài khoản.
- Quyền thay đổi chính sách cấp quyền quản trị.
- Credential và khóa được đồng bộ hoặc sao lưu ở đâu.

Mức tách biệt cần được thiết kế theo rủi ro, không suy ra chỉ từ việc có hai tên đăng nhập.

## 5. Thiết kế danh tính và quy tắc đặt tên

### 5.1. Dùng định danh ổn định để ánh xạ

Tên đăng nhập và tên hiển thị có thể thay đổi. Vì vậy, nên có một định danh cá nhân ổn định trong hệ thống quản lý danh tính và liên kết tới các tài khoản quản trị tương ứng.

Một bản ghi quản lý có thể gồm:

| Trường thông tin | Mục đích |
| --- | --- |
| Định danh cá nhân ổn định | Đối chiếu với đúng người qua các lần đổi tên hoặc thay bộ phận |
| Định danh tài khoản quản trị | Xác định principal cụ thể ở hệ thống quản lý hoặc hệ thống đích |
| Mục đích | Nêu công việc quản trị được giao |
| Người quản lý hoặc người bảo trợ | Xác nhận quan hệ công việc và điều kiện duy trì truy cập |
| Chủ sở hữu quyền hoặc tài nguyên | Xác nhận phạm vi quyền phù hợp |
| Trạng thái và ngày xem xét | Theo dõi vòng đời, thời hạn và ngoại lệ |
| Nguồn bằng chứng | Chỉ ra nơi liên kết yêu cầu, xác thực, phiên và audit |

Không ghi mật khẩu, token hay khóa riêng vào bản kiểm kê.

### 5.2. Không tái sử dụng tài khoản của người cũ cho người mới

Đổi tên tài khoản cũ rồi giao cho người khác làm cho một principal có nhiều người sử dụng qua thời gian và gây khó khăn khi đọc lịch sử.

Nên cấp tài khoản phù hợp cho người mới, xử lý tài khoản cũ theo vòng đời và giữ ánh xạ lịch sử cần thiết. Nếu hệ thống có hạn chế buộc phải xử lý ngoại lệ, phải lưu rõ thời điểm và chủ thể được giao, đồng thời bảo vệ bằng chứng cũ.

### 5.3. Tên gọi chỉ là công cụ hỗ trợ

Quy tắc tên có thể giúp nhận diện tài khoản quản trị, môi trường hoặc phạm vi phụ trách. Tuy nhiên:

- Không coi hậu tố tên là cơ chế phân quyền.
- Không dùng tên tài khoản thay cho định danh ổn định trong mọi phép đối chiếu.
- Không đưa thông tin cá nhân không cần thiết vào tên.
- Không giả định tên giống nhau ở hai hệ thống có nghĩa là cùng một danh tính.

## 6. Cấp quyền theo least privilege, JIT và JEA

### 6.1. Bắt đầu từ nhiệm vụ

Thay yêu cầu “cấp admin production” bằng yêu cầu cụ thể:

> Người vận hành cần khởi động lại dịch vụ ứng dụng A trên production để xử lý sự cố đã xác định, trong phạm vi thời gian được chấp nhận.

Từ đó đánh giá:

- Tài nguyên nào cần truy cập?
- Hành động nào cần thực hiện?
- Có cần đọc dữ liệu nhạy cảm không?
- Có cần cấp quyền cho người khác không?
- Có thể hoàn thành công việc bằng một role hoặc giao diện hẹp hơn không?

Least privilege phải xét cả quyền trực tiếp, quyền kế thừa và khả năng sửa thành phần chạy với quyền mạnh hơn.

### 6.2. JIT giới hạn thời gian có quyền

Just-in-Time có thể cho phép tài khoản quản trị cá nhân nhận vai trò khi có nhiệm vụ, rồi thu hồi sau thời hạn hoặc khi công việc kết thúc.

Cần phân biệt:

- Tài khoản tồn tại bao lâu.
- Điều kiện được phép yêu cầu quyền tồn tại bao lâu.
- Quyền đã cấp có hiệu lực bao lâu.
- Credential và phiên từ quyền đó còn dùng được bao lâu.

Một tài khoản tồn tại lâu nhưng không có quyền mạnh ngoài nhiệm vụ khác với một tài khoản giữ quyền mạnh thường trực.

Nếu người dùng luôn có thể tự nhận lại vai trò quản trị rộng mà không có điều kiện phù hợp, thời hạn ngắn của từng lần cấp chưa chắc làm giảm đáng kể khả năng sử dụng quyền.

### 6.3. JEA giới hạn tập hành động

Just Enough Administration là nguyên tắc giới hạn khả năng quản trị vào đúng nhu cầu. Cơ chế có thể là role hẹp, policy API, công cụ quản trị giới hạn hoặc tác vụ được ràng buộc theo hệ thống.

Cho phép khởi động lại một dịch vụ khác với cho quyền quản trị toàn máy. Tuy nhiên, một công cụ được gọi là “chỉ bảo trì” vẫn có thể tạo đường thực thi rộng nếu nó cho phép nhập lệnh tùy ý hoặc sửa mã chạy bằng quyền cao.

Cần kiểm tra khả năng thực tế của tập hành động được cho phép. Không giả định mọi nền tảng đều có tính năng JEA cùng tên hoặc cùng cách thực thi.

### 6.4. Kiểm soát quyền cấp lại và quyền tồn tại sau nhiệm vụ

Trong thời gian nhận quyền, tài khoản có thể tạo thêm tài khoản, khóa, token, quan hệ tin cậy hoặc tác vụ nếu role cho phép.

Việc thu hồi role ban đầu không tự xóa những thay đổi đó. Với các nhiệm vụ có quyền cấp tiếp, cần giới hạn, giám sát và xem xét các thay đổi phát sinh phù hợp.

## 7. Bảo vệ credential và đường truy cập

### 7.1. Xác thực phù hợp cho hoạt động quản trị

Luồng quản trị của con người nên sử dụng xác thực mạnh tương xứng với rủi ro. Khi nền tảng hỗ trợ, có thể lựa chọn phương thức giảm nguy cơ lộ hoặc bị đánh cắp thông tin xác thực qua giả mạo.

Cần xem toàn bộ đường xác thực:

- Đăng nhập nhà cung cấp danh tính.
- Kích hoạt hoặc yêu cầu vai trò quản trị.
- Mở kết nối đến hệ thống đích.
- Khôi phục tài khoản và thay yếu tố xác thực.
- Sử dụng đường khẩn cấp hoặc công cụ cũ.

Một luồng thông thường được bảo vệ tốt vẫn có thể bị làm yếu bởi đường khôi phục hoặc đường đăng nhập trực tiếp dùng credential khác.

### 7.2. Vault và phân phối bí mật

Nếu hệ thống đích yêu cầu mật khẩu hoặc khóa dài hạn, vault có thể hỗ trợ lưu trữ, kiểm soát truy xuất, luân chuyển và giữ bằng chứng sử dụng.

Cần làm rõ:

- Người dùng có được thấy credential hay công cụ dùng credential thay họ?
- Ai có quyền lấy, sửa hoặc thay chính sách quản lý bí mật?
- Credential có thể được dùng trực tiếp ngoài PAM không?
- Sau khi lấy, bản sao tồn tại ở đâu?
- Khi nghi bị lộ, thu hồi những gì và kiểm tra kết quả bằng cách nào?

Named admin account không bắt buộc phải dùng một loại vault hoặc phương pháp xác thực duy nhất. Thiết kế phải phù hợp với hệ thống đích và các đường truy cập thực tế.

### 7.3. Luân chuyển và thu hồi

Đổi mật khẩu định kỳ không thay thế xử lý khẩn cấp khi có dấu hiệu lộ credential.

Một tài khoản có thể đồng thời có mật khẩu, khóa, token, chứng thư hoặc phiên hoạt động. Cần quản lý từng loại theo khả năng của hệ thống. Đổi một credential không mặc nhiên thu hồi tất cả các phương tiện khác.

Nếu một named admin account đang được job tự động sử dụng, cần nhận diện và tách phụ thuộc đó trước khi coi luân chuyển là một việc chỉ ảnh hưởng cá nhân. Tác vụ tự động nên có danh tính và quyền riêng phù hợp.

### 7.4. Bảo vệ ngữ cảnh quản trị

Hoạt động quản trị cần được thực hiện từ thiết bị và công cụ đáp ứng yêu cầu kiểm soát phù hợp. Những hoạt động như đọc thư, duyệt nội dung không tin cậy hoặc chạy mã chưa được chấp nhận có thể tăng nguy cơ đối với phiên quản trị nếu dùng chung ngữ cảnh.

Mức tách biệt có thể gồm tài khoản, hồ sơ công cụ, phiên hoặc thiết bị chuyên dụng theo rủi ro. Chỉ tách cửa sổ đăng nhập không bảo đảm cô lập nếu cùng một môi trường đã bị chiếm quyền.

## 8. Luồng sử dụng một named admin account

Ví dụ sau mô tả một nhiệm vụ giả định: kỹ sư A cần khởi động lại dịch vụ ứng dụng A.

```text
Danh tính cá nhân được xác thực
              |
              v
Yêu cầu quyền cho nhiệm vụ và tài nguyên xác định
              |
              v
Kiểm tra điều kiện và quyết định cấp quyền
              |
              v
Tài khoản quản trị cá nhân nhận tập quyền có giới hạn
              |
              v
Mở phiên và thực hiện hành động được phép
              |
              v
Kết thúc công việc, xử lý phiên và thu hồi quyền
              |
              v
Liên kết bằng chứng và xem xét ngoại lệ
```

Một mô tả yêu cầu có thể như sau. Đây là **ví dụ ở mức ý định, không phải cấu hình triển khai cho sản phẩm cụ thể**:

```yaml
access_request:
  person_id: person-example-104
  admin_principal: engineer-a-admin
  reason: incident-example-52

scope:
  environment: production
  resource: application-a
  capability: restart-application-service

lifecycle:
  grant: task-bound
  expiry: explicit
  session_end: governed-by-target-system-policy

evidence:
  correlate:
    - request-id
    - personal-subject-id
    - admin-principal-id
    - target-session-id
    - action-result
```

Khi thực hiện, cần xác minh hệ thống thực sự áp dụng phạm vi đó. Việc một form ghi “khởi động lại dịch vụ” không giới hạn được người dùng nếu role được cấp vẫn cho phép quản trị mọi tài nguyên.

## 9. Giám sát phiên và xây dựng bằng chứng quy trách nhiệm

Một chuỗi bằng chứng hữu ích cần liên kết:

| Giai đoạn | Nội dung cần xác định |
| --- | --- |
| Nhận diện | Người được cấp sử dụng và định danh cá nhân ổn định |
| Yêu cầu | Nhiệm vụ, lý do, phạm vi, thời gian và quyết định |
| Xác thực | Chủ thể đã xác thực, phương thức và ngữ cảnh phù hợp |
| Cấp quyền | Tài khoản quản trị, role, tài nguyên, thời hạn |
| Sử dụng | Phiên, hành động, đối tượng, kết quả và thay đổi |
| Kết thúc | Thu hồi quyền, xử lý phiên, ngoại lệ hoặc sự cố |

### Khi hệ thống đích có tài khoản cá nhân

Audit nên ghi principal riêng, nhưng vẫn cần đối chiếu với yêu cầu quyền và phiên. Điều này giúp phân biệt thao tác được phép với sử dụng quyền ngoài nhiệm vụ.

### Khi hệ thống đích chỉ hỗ trợ tài khoản kỹ thuật chung

Có thể dùng danh tính cá nhân ở phía PAM hoặc gateway rồi ánh xạ từng phiên đến tài khoản đích. Khi đó, giá trị quy trách nhiệm phụ thuộc vào:

- Độ tin cậy của ánh xạ người dùng với phiên.
- Khả năng ngăn hoặc phát hiện đường truy cập trực tiếp ngoài luồng.
- Chất lượng audit tại hệ thống đích.
- Việc bảo vệ log và định danh liên kết.

Không nên gọi tài khoản đích chung là tài khoản cá nhân chỉ vì người dùng đăng nhập vào PAM bằng tài khoản riêng. Hai lớp danh tính phải được mô tả chính xác.

### Giới hạn của bản ghi phiên

Ghi hình có thể hỗ trợ xem xét một phiên tương tác, nhưng không nhất thiết ghi đầy đủ API, kết nối nền hoặc công cụ khác. Cần lựa chọn nguồn audit phù hợp với giao thức và hệ thống.

Bản ghi có thể chứa dữ liệu nhạy cảm. Cần giới hạn quyền xem, bảo vệ khỏi sửa hoặc xóa trái phép và tránh ghi credential đầy đủ. Nhãn người dùng do client tự khai không nên được coi là bằng chứng xác thực độc lập nếu có thể bị giả mạo.

## 10. Vòng đời: cấp mới, chuyển vị trí và nghỉ việc

### 10.1. Cấp mới

Một quy trình có thể gồm:

1. Xác minh người được cấp và quan hệ công việc.
2. Xác nhận nhiệm vụ quản trị, tài nguyên và người chịu trách nhiệm quyền.
3. Tạo hoặc liên kết tài khoản theo quy tắc định danh.
4. Cấu hình xác thực, khôi phục và luồng truy cập.
5. Cấp tập quyền tối thiểu hoặc điều kiện nhận quyền theo nhiệm vụ.
6. Ghi nguồn audit và cách thu hồi.
7. Xác nhận tài khoản hoạt động đúng trong phạm vi được giao.

Việc tạo tài khoản và cấp quyền là hai quyết định cần được phân biệt. Có tài khoản không có nghĩa mặc định được mọi quyền quản trị.

### 10.2. Chuyển vị trí

Khi một người đổi đội hoặc trách nhiệm, cần xem lại quyền cũ trước khi bổ sung quyền mới.

Rủi ro phổ biến là cộng dồn: người dùng giữ quyền từ nhiều vai trò trước đây vì mỗi lần chuyển chỉ thêm quyền. Cần kiểm tra nhóm, quyền kế thừa, tài khoản cục bộ và điều kiện nhận quyền, không chỉ một role nổi bật.

### 10.3. Nhà thầu hoặc nhân sự có thời hạn

Cần có người bảo trợ, mục đích và ngày kết thúc hoặc xem xét. Việc gia hạn phải gắn với nhu cầu còn tồn tại, tránh để tài khoản duy trì vô thời hạn vì hợp đồng từng được mở.

### 10.4. Nghỉ việc hoặc hết nhu cầu

Quy trình thu hồi cần xem cả:

- Tài khoản trung tâm và tài khoản đích không được đồng bộ.
- Nhóm, role và quyền đủ điều kiện kích hoạt.
- Credential, token, khóa và chứng thư liên quan.
- Phiên đang mở và kết nối từ công cụ quản trị.
- Quyền quản lý bí mật, chính sách và quan hệ tin cậy.
- Tác vụ hoặc tài nguyên đang phụ thuộc vào tài khoản.
- Ánh xạ lịch sử cần giữ để phục vụ điều tra.

Vô hiệu hóa tài khoản trung tâm có thể không tự xử lý mọi credential hoặc phiên ở hệ thống khác. Cần xác nhận theo từng đường truy cập thực tế.

## 11. Hết hạn quyền không luôn đồng nghĩa hết phiên

Một người nhận quyền trong một khoảng thời gian giới hạn có thể đã mở phiên, nhận token hoặc lấy credential trước khi hết hạn.

Khi thiết kế thu hồi, phải trả lời:

1. Có chặn được yêu cầu quyền mới không?
2. Credential đã phát hành còn hiệu lực không?
3. Phiên ở đích có tiếp tục thực hiện thao tác không?
4. Vai trò đã thu hồi được hệ thống đích đánh giá vào lúc nào?
5. Có thay đổi quyền, tài khoản hoặc credential mới được tạo trong nhiệm vụ không?

Hành vi phụ thuộc nền tảng. Không giả định rằng xóa bản ghi yêu cầu trong PAM, đổi mật khẩu hoặc thu hồi role sẽ kết thúc mọi hoạt động hiện có.

Xử lý phiên cũng cần xét tác động vận hành. Ngắt một phiên có thể ảnh hưởng giao dịch hoặc tác vụ đang chạy. Quy trình cần có cách xử lý phù hợp với rủi ro và mức khẩn cấp, thay vì chỉ có một trạng thái “đã thu hồi” ở phía quản lý.

## 12. Khi nghi tài khoản quản trị cá nhân bị chiếm quyền

Giả sử audit ghi nhận `engineer-a-admin` sửa chính sách ngoài nhiệm vụ được chấp nhận.

Một hướng xử lý:

1. **Đối chiếu bằng chứng.** Kiểm tra yêu cầu quyền, sự kiện xác thực, ngữ cảnh nguồn, phiên và hành động.
2. **Giới hạn truy cập tiếp.** Chặn hoặc thu hẹp đường nhận quyền, kết nối và principal liên quan theo mức độ sự cố.
3. **Xử lý credential và phiên.** Thu hồi từng loại phù hợp; kiểm tra các phiên đã tồn tại.
4. **Kiểm tra thay đổi phát sinh.** Tìm quyền, tài khoản, token, khóa hoặc cấu hình được tạo hay sửa trong phạm vi nghi vấn.
5. **Xem xét ngữ cảnh bị chiếm.** Thiết bị, nhà cung cấp danh tính, cơ chế khôi phục hoặc công cụ quản trị có thể liên quan.
6. **Bảo toàn bằng chứng và phục hồi.** Giữ dữ liệu cần thiết, sửa nguyên nhân và khôi phục quyền phù hợp từ ngữ cảnh được tin cậy.

Không nên kết luận ngay rằng người được cấp tài khoản cố ý thực hiện hành vi. Tên tài khoản là một điểm liên kết điều tra, cần được đối chiếu với các nguồn khác.

Đổi mật khẩu rồi mở lại quyền trong khi thiết bị hoặc phiên vẫn bị chiếm có thể làm credential mới tiếp tục bị lạm dụng.

## 13. Tình huống tự đánh giá

Một đội đã thay tài khoản quản trị chung bằng bốn tài khoản có tên riêng. Tuy nhiên:

- Cả bốn tài khoản đều có quyền quản trị toàn bộ production thường trực.
- Credential được lưu trong một mục vault mà cả nhóm có thể lấy.
- Một job triển khai dùng tài khoản của trưởng nhóm.
- Người dùng có thể kết nối trực tiếp ngoài gateway.
- Log chỉ được giữ ở máy chủ mà các tài khoản này cũng quản trị.
- Nhóm cho rằng đã hoàn tất PAM vì mỗi tài khoản mang tên một người.

### Phân tích

**Cá nhân hóa mới ở mức tên gọi:** credential dùng chung qua vault làm suy yếu giả định một người sử dụng một tài khoản.

**Phạm vi và thời gian chưa được giới hạn:** mọi người giữ quyền rộng thường trực dù nhiệm vụ có thể khác nhau.

**Trộn con người và tự động hóa:** hành động của job có thể bị hiểu là hành động của trưởng nhóm; thu hồi tài khoản cá nhân còn ảnh hưởng triển khai.

**Đường truy cập không đầy đủ:** gateway không bảo đảm quan sát mọi hoạt động nếu vẫn có thể dùng cùng credential đi trực tiếp.

**Bằng chứng dễ bị tác động:** quyền quản trị hệ thống đích có thể ảnh hưởng log cục bộ, tùy cấu hình bảo vệ.

### Hướng cải thiện

- Ràng buộc tài khoản và phương tiện xác thực với từng cá nhân theo thiết kế phù hợp.
- Tách danh tính cho job triển khai.
- Thu hẹp quyền theo nhiệm vụ, ứng dụng và môi trường.
- Áp dụng quyền có thời hạn khi phù hợp, kèm cách xử lý phiên.
- Kiểm soát các đường truy cập trực tiếp và ngoại lệ.
- Liên kết yêu cầu, xác thực, principal, phiên và audit.
- Bảo vệ bằng chứng trong miền quản trị phù hợp, có quyền truy cập được kiểm soát.
- Rà soát vòng đời và cách thu hồi khi người dùng chuyển vị trí hoặc hết nhu cầu.

Không cần tạo thêm nhiều tên tài khoản nếu các tài khoản mới vẫn chia sẻ credential, quyền và đường sử dụng như cũ. Cần sửa chính các ranh giới kiểm soát.

## 14. Những điểm cần ghi nhớ

- Named admin account là tài khoản quản trị gắn với một cá nhân xác định, có liên kết danh tính và vòng đời được quản lý.
- Tài khoản riêng hỗ trợ cấp quyền, thu hồi và điều tra theo cá nhân; không tự bảo đảm least privilege hay chứng minh ai đã trực tiếp thao tác.
- Phải tách mục đích công việc thường, quản trị và tự động hóa; đồng thời đánh giá các phụ thuộc xác thực, khôi phục và thiết bị.
- JIT giới hạn thời gian, JEA giới hạn hành động, vault và luân chuyển quản lý credential; các cơ chế cần được kiểm tra trong hệ thống đích.
- Quyền, credential và phiên có vòng đời khác nhau. Thu hồi cần xử lý đúng từng lớp và kiểm tra quyền phát sinh.
- Bằng chứng cần trả lời rõ: **người nào, tài khoản quản trị nào, quyền gì, trên tài nguyên nào, vì nhiệm vụ gì, đã làm gì và kết thúc quyền ra sao**.