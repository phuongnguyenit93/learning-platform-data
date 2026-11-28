# Rotation database password trong PAM

## 1. Mục tiêu của rotation mật khẩu cơ sở dữ liệu

**Rotation database password** là quá trình thay mật khẩu của một danh tính đăng nhập cơ sở dữ liệu, cập nhật trạng thái quản lý và chuyển các consumer liên quan sang sử dụng mật khẩu mới theo một kế hoạch có kiểm chứng.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), rotation có thể áp dụng cho tài khoản quản trị, tài khoản dịch vụ, tài khoản backup hoặc danh tính kỹ thuật khác có khả năng truy cập dữ liệu và cấu hình nhạy cảm.

Mục tiêu không chỉ là database chấp nhận một lệnh đổi mật khẩu. Một lần rotation cần làm rõ:

1. Đúng tài khoản tại đúng nguồn xác thực đã được thay.
2. Vault quản lý đúng credential và phiên bản.
3. Các consumer được xác định đã chuyển theo cơ chế phù hợp.
4. Có bằng chứng xác thực mới và kiểm tra chức năng cần thiết.
5. Credential cũ được xử lý theo mục tiêu và khả năng nền tảng.
6. Phiên, kết nối và quyền liên quan được đánh giá riêng.
7. Có thể xử lý lỗi từng phần mà không mất kiểm soát trạng thái.

Ví dụ, một ứng dụng có thể vẫn hoạt động nhờ connection pool được mở trước rotation. Trong khi đó, mọi kết nối mới đều thất bại vì ứng dụng còn giữ mật khẩu cũ. Dashboard xanh chưa đủ để nói rotation đã thành công.

Các luồng và cấu trúc trong bài là mô hình logic. Cú pháp đổi mật khẩu, cơ chế lưu trạng thái và hành vi phiên cần được xác minh cho engine, phiên bản, driver và kiến trúc thực tế.

## 2. Xác định đúng tài khoản và nguồn xác thực

### 2.1. Tên tài khoản chưa đủ để xác định đối tượng

Một tên đăng nhập có thể tồn tại ở nhiều instance, môi trường, phạm vi database hoặc nguồn danh tính khác nhau.

Hồ sơ cần cho biết:

| Nhóm | Nội dung |
|---|---|
| Định danh tài nguyên | Instance, cụm, endpoint hoặc dịch vụ database |
| Môi trường | Production, thử nghiệm, dự phòng |
| Danh tính | Account ID và phạm vi định danh theo engine |
| Nguồn xác thực | Native database, directory, issuer hoặc cơ chế khác |
| Đường kết nối | Trực tiếp, proxy, pooler, gateway hoặc controller |
| Quyền | Role và quyền hiệu lực của tài khoản |
| Owner | Đội chịu trách nhiệm tài khoản và ứng dụng |
| Credential | Đối tượng quản lý, phiên bản và vòng đời |

Không đổi một tài khoản tập trung như thể nó chỉ thuộc một database. Thay mật khẩu tại directory hoặc nguồn dùng chung có thể ảnh hưởng nhiều hệ thống ngoài endpoint đang quan sát.

### 2.2. Xác minh cơ chế đăng nhập đang được dùng

Một tài khoản có thể truy cập qua mật khẩu, danh tính tích hợp, chứng thư hoặc cơ chế khác tùy triển khai.

Thay một trường password chưa chắc tác động tới đường xác thực đang được dùng. Cần xác định cơ chế thật sự và các phương thức thay thế vẫn còn hiệu lực.

Tương tự, một ứng dụng có thể xác thực với proxy bằng một credential, trong khi proxy dùng một credential khác để kết nối database. Hai vòng đời này không được gộp thành một.

### 2.3. Phân loại mục đích tài khoản

| Loại tài khoản | Điểm cần chú ý |
|---|---|
| Quản trị tương tác | Danh tính người dùng, checkout, gateway và phiên quản trị |
| Runtime ứng dụng | Consumer, refresh, connection pool và quyền dữ liệu |
| Backup hoặc khôi phục | Job theo lịch, đường phục hồi và dữ liệu nhạy cảm |
| Giám sát | Quyền đọc cần thiết, tần suất và cách mở kết nối |
| Replication hoặc chức năng hạ tầng | Cơ chế riêng, ảnh hưởng tới tính sẵn sàng |
| Rotation hoặc reconcile | Quyền thay credential và khả năng phục hồi |

Không dùng một tài khoản quản trị rộng cho tất cả mục đích chỉ để giảm số đối tượng cần quản lý. Tách theo nhu cầu giúp giảm phạm vi ảnh hưởng, nhưng phải phù hợp khả năng hệ thống và trách nhiệm vận hành.

## 3. Rotation mật khẩu khác những thay đổi nào?

| Thay đổi | Mục tiêu | Điều không tự xảy ra |
|---|---|---|
| Đổi mật khẩu database | Thay credential xác thực của tài khoản | Không tự đổi quyền của tài khoản |
| Rotation khóa mã hóa vault | Bảo vệ dữ liệu lưu trong vault | Không tự đổi mật khẩu tại database |
| Thu hồi grant hoặc role | Gỡ quyền thực hiện hành động | Không nhất thiết vô hiệu hóa mọi phương thức đăng nhập |
| Vô hiệu hóa tài khoản | Chặn sử dụng theo cơ chế engine | Không mặc định kết thúc mọi phiên đã mở |
| Đóng phiên | Dừng một kết nối hoặc phiên cụ thể | Không tự làm mật khẩu mất hiệu lực |
| Cập nhật secret reference | Đổi nguồn consumer đọc credential | Không chứng minh tiến trình đã refresh |
| Đổi mật khẩu ở proxy | Tác động một lớp xác thực | Không tự đổi credential upstream tới database |

Nếu mật khẩu nghi lộ, có thể cần phối hợp nhiều hành động trên. Một tác vụ rotation không thay thế toàn bộ quy trình ứng phó sự cố.

Nếu mục tiêu chỉ là rotation theo vòng đời, vẫn cần biết những hành động nào nằm trong và ngoài phạm vi. Không tuyên bố đã thu hồi toàn bộ truy cập khi chỉ mới thay một credential.

## 4. Kiến trúc tham chiếu và trạng thái cần đồng bộ

~~~mermaid
flowchart LR
    O["Điều phối rotation"] -->|Phạm vi, policy và lịch| R["Connector rotation"]
    V["Vault và phiên bản credential"] -->|Đọc hoặc chuẩn bị dữ liệu theo quyền| R
    R -->|Thay tại đúng nguồn xác thực| D["Database hoặc nguồn danh tính"]
    R -->|Cập nhật trạng thái quản lý| V
    A["Ứng dụng và connection pool"] -->|Lấy secret theo cơ chế| V
    J["Job, backup, giám sát"] -->|Lấy secret theo cơ chế| V
    A -->|Xác thực và tác vụ| D
    J -->|Xác thực và tác vụ| D
    C["Nguồn cấu hình mong muốn"] -->|Reference và cách refresh| A
    R --> E["Audit và bằng chứng"]
    D --> E
    A --> E
~~~

Sơ đồ là mô hình logic. Một hệ thống có proxy, agent hoặc directory có thể cần thêm các lớp trạng thái tương ứng.

### 4.1. Các chiều trạng thái

~~~text
Nguồn xác thực:
  Credential nào đang được chấp nhận?

Vault:
  Phiên bản nào đã được chuẩn bị, công bố hoặc giữ để phục hồi?

Consumer:
  Reference, dữ liệu đã nhận và credential đang dùng là gì?

Phiên:
  Kết nối cũ nào còn hoạt động?

Cấu hình:
  Pipeline hoặc controller sẽ phân phối gì ở lần triển khai tiếp theo?

Tự động hóa:
  Tác vụ nào còn có thể đổi cùng tài khoản?

Bằng chứng:
  Điều gì đã được xác minh, điều gì còn unknown?
~~~

Không phải mọi vault đều có cùng bộ nhãn như pending hoặc current. Điều cần có là phân biệt credential mới được chuẩn bị với credential đã được xác minh và công bố cho consumer.

### 4.2. Không có giao dịch nguyên tử mặc định

Database, vault, proxy và consumer thường không cùng tham gia một giao dịch thay đổi mật khẩu.

Có thể xảy ra trạng thái:

- Database đã đổi nhưng vault chưa cập nhật.
- Vault có phiên bản mới nhưng ứng dụng chưa nhận.
- Một nhóm consumer đã chuyển, nhóm khác chưa chuyển.
- Proxy còn cache thông tin cũ.
- Tác vụ timeout dù nguồn xác thực đã áp dụng.

Kế hoạch phải xử lý những trạng thái này, thay vì giả định lỗi sẽ đưa mọi thành phần trở lại điểm bắt đầu.

## 5. Kiểm kê consumer và dependency

### 5.1. Những consumer dễ bị bỏ sót

Ngoài ứng dụng chính, cần xem xét:

- Worker nền và tác vụ theo lịch.
- Công cụ backup, giám sát và kiểm tra sức khỏe.
- Pipeline triển khai hoặc migration.
- Báo cáo, tích hợp và tác vụ đối soát.
- Môi trường dự phòng hoặc khởi động lạnh.
- Công cụ quản trị và session gateway.
- Proxy hoặc pooler giữ credential upstream.
- Các bản sao cấu hình ngoài cơ chế phân phối chính.

Danh sách cần có owner, môi trường, cách lấy secret và phương pháp cập nhật.

### 5.2. Ghi hành vi thật của consumer

| Hành vi | Ý nghĩa với rotation |
|---|---|
| Đọc một lần khi khởi động | Có thể cần thay thế instance hoặc khởi động lại có phối hợp |
| Refresh theo lịch | Có khoảng trễ và cần xử lý refresh lỗi |
| Đọc khi mở kết nối | Phải kiểm tra cache ở driver, agent hoặc thư viện |
| Dùng connection pool dài hạn | Kết nối cũ có thể che lỗi xác thực mới |
| Nhận secret qua pipeline | Cần cập nhật nguồn cấu hình mong muốn |
| Job ít chạy | Có thể chưa dùng credential mới trong cửa sổ theo dõi |
| Dự phòng lạnh | Lỗi chỉ lộ khi failover hoặc phục hồi |

Không dùng một lần đọc secret thành công làm bằng chứng ứng dụng đã dùng credential mới để xác thực.

### 5.3. Bản sao và reference khác nhau

Một consumer có thể trỏ tới secret được quản lý, nhưng một công cụ khác giữ bản sao riêng. Rotation ở vault không tự cập nhật mọi bản sao.

Nếu chưa xác định đủ consumer, cần ghi phạm vi discovery và phần chưa biết. Không coi không có đăng nhập gần đây là bằng chứng một job đã hết nhu cầu.

## 6. Quyền của connector và đường phục hồi

### 6.1. Đổi mật khẩu của chính mình và reset tài khoản khác

Tùy engine và chính sách, connector có thể dùng credential hiện tại để đổi chính mật khẩu của tài khoản hoặc dùng một danh tính quản trị được phép reset.

Hai mô hình có yêu cầu khác nhau:

- Tự đổi có thể phụ thuộc credential hiện tại còn dùng được.
- Reset cần quyền đặc quyền đối với tài khoản khác.
- Khả năng giới hạn quyền reset theo tập tài khoản phụ thuộc nền tảng.
- Mất đồng bộ có thể cần quy trình reconcile riêng.

Không cấp quyền quản trị toàn bộ database nếu nhu cầu có thể được giới hạn bằng cơ chế được hỗ trợ.

### 6.2. Bảo vệ credential của chính connector

Credential rotation, reconcile và quyền truy cập vault cũng phải có owner, vòng đời, bằng chứng và phạm vi rõ.

Cần tránh một vòng phụ thuộc không có đường phục hồi: connector không lấy được credential vì chính credential đó là điều kiện duy nhất để truy cập hệ thống quản lý.

Đường khẩn cấp phải giải quyết đúng điểm hỏng và được quản trị riêng. Một phiên đang mở không thay thế hoàn toàn phương án phục hồi.

### 6.3. Kênh kết nối và cách truyền mật khẩu

Cần bảo vệ kênh tới vault và nguồn xác thực, đồng thời xác minh danh tính máy chủ theo thiết kế.

Không đưa mật khẩu mới vào log, tham số dòng lệnh dễ quan sát hoặc báo cáo tác vụ. Cơ chế đổi mật khẩu cần được kiểm tra về audit, trace và khả năng che dữ liệu nhạy cảm.

Không mặc định mọi câu lệnh quản trị đều hỗ trợ truyền mật khẩu qua cùng một cách bind parameter. Dùng API, driver hoặc connector phù hợp và được hỗ trợ cho nền tảng thực tế.

Mật khẩu sinh ra cần tương thích với chính sách, định dạng và giới hạn của nguồn xác thực. Nếu consumer dùng connection string, phải xử lý mã hóa và phân tách trường theo cơ chế đúng, tránh ghép chuỗi tùy ý.

## 7. Preflight cho một lần rotation

Một kế hoạch đủ cụ thể cần xác nhận:

1. Đúng account, nguồn xác thực, endpoint và môi trường.
2. Tập consumer đã biết cùng phần chưa xác minh.
3. Quyền của connector và phương án reconcile.
4. Khả năng dùng đồng thời credential hoặc giới hạn một credential.
5. Cách refresh, thay kết nối và kiểm tra từng nhóm consumer.
6. Hành vi của HA, proxy và các nguồn cấu hình liên quan.
7. Phương án phục hồi và điều kiện chuyển cấp.
8. Tiêu chí thành công và trạng thái lỗi từng phần.
9. Cơ chế bảo vệ credential mới trong giai đoạn chuẩn bị.
10. Các actor có thể thay cùng tài khoản.

### 7.1. Kiểm soát thay đổi đồng thời

Một scheduler rotation, thao tác của DBA, controller hoặc pipeline có thể cùng sửa đối tượng.

Cần điều phối theo tài khoản hoặc nguồn credential thực tế, không chỉ theo ID job. Hai đối tượng vault khác nhau cùng trỏ một tài khoản không nên tự rotation độc lập mà không nhận diện quan hệ đó.

Nếu dùng phiên bản hoặc generation để cập nhật trạng thái, phải kiểm tra điều kiện trước khi công bố thay đổi. Không ghi đè một phiên bản mới hơn bằng kết quả cũ.

### 7.2. Xác định cửa sổ và điều kiện dừng

Cần biết ảnh hưởng của tác vụ nghiệp vụ, job theo lịch và việc tạo kết nối mới.

Điều kiện dừng có thể là mất khả năng xác minh đích, consumer lỗi vượt phạm vi kế hoạch, kết quả thay đổi không xác định hoặc đường phục hồi không còn đáp ứng.

Không đổi cùng lúc password, role, endpoint và toàn bộ chính sách mạng nếu không có kế hoạch tách lỗi và phục hồi phù hợp.

## 8. Luồng rotation khi chỉ có một mật khẩu hiệu lực

### 8.1. Khoảng chuyển tiếp cần được thiết kế

Nếu đổi tại nguồn làm mật khẩu cũ mất hiệu lực cho xác thực mới, không có một thứ tự đơn giản luôn tránh được gián đoạn:

~~~text
Đổi database trước:
  Consumer còn giữ mật khẩu cũ có thể không mở được kết nối.

Cập nhật consumer trước:
  Mật khẩu mới có thể chưa được database chấp nhận.
~~~

Kế hoạch cần phối hợp việc nhận tác vụ mới, phân phối credential, refresh và tái kết nối. Không hứa zero downtime nếu chưa có cơ chế và bằng chứng tương ứng.

### 8.2. Chuẩn bị credential mới một cách bảo mật

Credential mới cần được sinh và giữ bằng cơ chế được bảo vệ, gắn với rotation ID, account và phiên bản quản lý.

Nếu vault có cơ chế giữ candidate hoặc trạng thái tương đương, phải giới hạn ai có thể đọc và khi nào được công bố. Tên trạng thái cụ thể phụ thuộc sản phẩm.

Credential được chuẩn bị chưa có nghĩa nguồn xác thực đã chấp nhận nó.

### 8.3. Thay tại nguồn

Connector xác minh precondition và áp dụng thay đổi qua đúng đường quản trị.

Cần ghi kết quả theo mức quan sát:

- Chưa thực hiện.
- Yêu cầu đã được gửi.
- Nguồn báo đã áp dụng.
- Đã xác minh bằng một lần xác thực mới.
- Chưa rõ kết quả do timeout hoặc mất phản hồi.

Không gộp tất cả thành một trạng thái success.

### 8.4. Đồng bộ vault và chuyển consumer

Sau khi có đủ bằng chứng theo thiết kế, trạng thái quản lý được cập nhật và consumer chuyển sang credential phù hợp.

Một luồng tham chiếu có thể là:

~~~text
Chuẩn bị và giữ phạm vi thay đổi
  → điều chỉnh nhịp consumer theo kế hoạch
  → đổi mật khẩu tại nguồn
  → kiểm tra xác thực mới có giới hạn
  → công bố trạng thái credential trong vault
  → refresh hoặc chuyển consumer
  → kiểm tra xác thực mới theo đường ứng dụng
  → kiểm tra tác vụ đại diện
  → tiếp tục vận hành theo tiêu chí.
~~~

Đây là mô hình phối hợp, không phải một giao dịch hai pha của database hay bảo đảm nguyên tử xuyên hệ thống. Chi tiết thứ tự phải phù hợp cơ chế phân phối, tiêu chí an toàn và khả năng phục hồi.

### 8.5. Hạn chế ảnh hưởng khi tái kết nối

Có thể cần thay thế instance theo nhóm hoặc điều khiển connection pool, tùy ứng dụng.

Không đồng loạt đóng mọi phiên chỉ để ép consumer dùng mật khẩu mới nếu điều đó gây tác động ngoài kế hoạch. Ngược lại, không giữ mãi kết nối cũ rồi coi đó là cách hoàn thành rotation.

## 9. Luồng khi hỗ trợ credential chồng lấn hoặc danh tính thay thế

### 9.1. Xác minh khả năng thật

Một nguồn có thể hỗ trợ nhiều credential, một giai đoạn chuyển tiếp hoặc một cơ chế tương đương. Khả năng này phải được kiểm tra cho đúng engine và cấu hình.

Cần biết:

- Credential mới và cũ có cùng quyền hay không.
- Khoảng chồng lấn được giới hạn bằng cơ chế nào.
- Cách xác định consumer đã chuyển.
- Cách vô hiệu hóa credential cũ.
- Phiên đã được credential cũ tạo ra còn tồn tại thế nào.
- Có thay đổi nào về nguồn danh tính hoặc quyền hiệu lực không.

### 9.2. Luồng chuyển đổi tham chiếu

~~~text
Tạo hoặc kích hoạt credential mới
  → xác minh tại nguồn
  → công bố qua cơ chế quản lý
  → chuyển từng nhóm consumer
  → xác minh kết nối mới và chức năng
  → xử lý job ít chạy, backup và dự phòng
  → ngừng chấp nhận credential cũ
  → xác minh điều kiện kết thúc.
~~~

Khoảng chồng lấn cần owner, thời hạn và cơ chế xử lý consumer chậm chuyển. Giữ credential cũ vô hạn để tránh lỗi không phải kết quả rotation đã hoàn tất theo mục tiêu thu hồi.

### 9.3. Tạo tài khoản thứ hai có thêm điều kiện

Một tài khoản thay thế có thể giúp chuyển đổi trong một số thiết kế, nhưng không mặc nhiên tương đương thêm mật khẩu cho cùng tài khoản.

Cần xét:

- Grant và role thực tế.
- Ownership hoặc đối tượng gắn với danh tính.
- Ngữ cảnh thực thi và hành vi ứng dụng.
- Chính sách truy cập, quota hoặc giới hạn liên quan.
- Cách audit phân biệt hai danh tính.
- Dọn hoặc thu hồi tài khoản cũ sau chuyển đổi.

Không sao chép toàn bộ quyền quản trị chỉ để hai tài khoản có vẻ tương đương. Phạm vi mới phải đúng nhu cầu.

## 10. Điều phối trạng thái và API minh họa

### 10.1. Trạng thái theo từng phần

| Phần | Ví dụ trạng thái |
|---|---|
| Credential mới | Đã chuẩn bị, đã gửi thay đổi, được xác minh |
| Vault | Chưa công bố, đã cập nhật, cần đối soát |
| Consumer | Chưa cập nhật, đã nhận, xác thực mới đạt, còn lỗi |
| Credential cũ | Còn hiệu lực theo kế hoạch, đã ngừng chấp nhận, chưa xác minh |
| Phiên | Tiếp tục theo policy, cần đóng, đã đóng, không quan sát được |
| Tác vụ tổng | Đang chuyển đổi, có lỗi từng phần, chờ xác minh, hoàn tất trong phạm vi |

Tên trạng thái chỉ minh họa. Một hệ thống có thể dùng mô hình khác, nhưng cần giữ được những sự khác biệt này.

### 10.2. Yêu cầu rotation logic

~~~json
{
  "rotation_id": "rotation-db-042",
  "managed_account_id": "payment-service-account",
  "authentication_source_id": "payment-db-native-identity",
  "target_scope_reference": "approved-db-endpoint-set",
  "consumer_plan_reference": "consumer-transition-042",
  "expected_managed_generation": 12,
  "recovery_plan_reference": "recovery-db-017"
}
~~~

Không có giá trị password trong ví dụ. Định danh client gửi phải được kiểm tra theo quyền và phạm vi; nó không tự là thẩm quyền thực hiện reset.

### 10.3. Giả mã điều phối

~~~text
rotate_database_password(plan):
    verify_identity_and_authority(plan)
    verify_account_source_and_target_scope(plan)
    verify_consumer_and_recovery_preconditions(plan)
    coordinate_concurrent_writers(plan.account)

    candidate_reference = prepare_secret_securely(plan)
    result = apply_password_change(plan, candidate_reference)

    if result is ambiguous:
        record_state_unknown()
        return RECONCILE_BEFORE_RETRY

    verify_fresh_authentication(candidate_reference)
    publish_managed_state_with_generation_check()
    transition_consumers_under_plan()

    verify_new_connections_and_required_functions()
    verify_old_credential_handling()
    verify_session_policy_and_remaining_scope()

    return COMPLETED_FOR_VERIFIED_SCOPE
~~~

Đây không phải mã chạy trực tiếp. Luồng có credential chồng lấn có thể cần thứ tự khác, đặc biệt ở bước ngừng chấp nhận credential cũ.

Rotation ID giúp theo dõi nhưng không tự làm mọi thao tác phía database có tính lặp an toàn.

## 11. Chuyển consumer và connection pool

### 11.1. Phân biệt cập nhật reference và cập nhật tiến trình

Một pipeline có thể đã lưu reference mới trong khi tiến trình vẫn dùng dữ liệu từ lúc khởi động.

Một agent có thể đã nhận phiên bản mới trong khi thư viện của ứng dụng còn cache. Mỗi bước cần bằng chứng phù hợp.

Một trạng thái minh họa:

~~~text
Consumer: payment-api-group
Desired secret reference: managed-payment-db-secret
Delivered credential version: version-13
Application refresh: reported-complete
Fresh database authentication: pending
Existing pool connections: still-active
~~~

Không thể kết luận consumer đã sử dụng mật khẩu mới thành công chỉ từ các dòng trước fresh authentication.

### 11.2. Kiểm soát việc mở kết nối mới

Cần biết driver hoặc pooler xác thực khi nào, có giữ credential cho kết nối sau không và khi nào đọc lại cấu hình.

Việc tái tạo một phần kết nối theo kế hoạch có thể giúp kiểm tra. Phương pháp cần phù hợp ứng dụng và tránh tạo đợt tái kết nối đồng loạt ngoài khả năng phục vụ.

Nếu lần mở mới thất bại nhưng pool cũ vẫn hoạt động, giữ trạng thái rõ ràng để chọn phương án xử lý. Không dựa vào pool cũ như một bảo đảm lâu dài.

### 11.3. Consumer ít chạy

Job cuối ngày, cuối tháng hoặc backup có thể chưa có cơ hội dùng mật khẩu mới.

Có thể cần đường kiểm tra được phép đại diện cho xác thực và quyền cần thiết. Không tự chạy một tác vụ nghiệp vụ có tác động chỉ để thử mật khẩu.

Nếu chưa kiểm tra được, báo phần chờ xác minh, owner và điều kiện xử lý. Không xóa consumer đó khỏi phạm vi để đóng thay đổi.

### 11.4. Nguồn cấu hình mong muốn

Cập nhật template, secret reference hoặc cấu hình quản lý cần thiết để lần deploy sau không đưa consumer về bản cũ.

Không sao chép giá trị password vào thêm một tệp cấu hình chỉ để làm nhanh quá trình chuyển đổi. Nếu nền tảng buộc phải có bản sao, cần quản lý quyền, vòng đời và phạm vi của bản sao đó.

## 12. Xác minh sau rotation

### 12.1. Xác thực mới tới đúng nguồn

Kiểm tra cần xác định:

- Đúng endpoint và danh tính máy chủ.
- Đúng tài khoản và phạm vi database.
- Đúng phương thức xác thực bằng password đang được kiểm chứng.
- Một kết nối mới, thay vì dùng lại phiên cũ.
- Kết quả không bị che bởi cơ chế xác thực thay thế.

Nếu dùng proxy, cần biết đang xác minh client tới proxy hay proxy tới database. Hai lần thành công không được tự suy ra từ một lần kiểm tra.

### 12.2. Xác thực thành công chưa đủ chứng minh ứng dụng hoạt động

Một kiểm tra ít tác động có thể chứng minh đăng nhập và kết nối. Nó chưa chắc chứng minh tài khoản truy cập được schema, đối tượng hoặc chức năng ứng dụng cần.

Cần tác vụ đại diện có phạm vi và ảnh hưởng phù hợp. Không cấp thêm quyền rộng chỉ để một bài kiểm tra thiếu chính xác trở lại màu xanh.

### 12.3. Credential cũ

Nếu mục tiêu là ngừng chấp nhận mật khẩu cũ, cần bằng chứng phù hợp cơ chế nguồn xác thực.

Không thử sai hàng loạt mật khẩu cũ trên mọi endpoint nếu điều đó có thể khóa tài khoản hoặc gây nhiễu. Có thể cần kiểm tra trạng thái hoặc phương pháp có giới hạn được nền tảng hỗ trợ.

Một số mô hình có khoảng chuyển tiếp hợp lệ. Khi đó, trạng thái phải nói rõ credential cũ còn được chấp nhận trong điều kiện nào, thay vì tuyên bố đã mất hiệu lực hoàn toàn.

### 12.4. Phiên và quyền

Đổi mật khẩu không nên được dùng làm bằng chứng tự động rằng các phiên hiện có đã kết thúc hoặc quyền đã được thu hẹp.

Nếu mục tiêu yêu cầu kết thúc phiên, cần thao tác và xác minh tại lớp quản lý phiên tương ứng. Nếu quyền tài khoản sai, phải xử lý grant hoặc role theo quy trình riêng.

### 12.5. Tổng hợp theo phạm vi

Một lần đăng nhập kiểm tra không chứng minh mọi consumer và mọi endpoint đã đạt.

Báo cáo nên giữ kết quả theo tài khoản, đường kết nối, nhóm consumer và giới hạn xác minh. Các vùng chưa kiểm tra phải còn nhìn thấy.

## 13. HA, failover, replica và proxy

### 13.1. Không mặc định credential được đồng bộ giống dữ liệu

Thông tin tài khoản và xác thực có thể được quản lý hoặc truyền giữa các node theo cơ chế riêng của nền tảng.

Cần hiểu:

- Nguồn nào được phép thay credential.
- Những node hoặc endpoint nào phục vụ xác thực.
- Thay đổi được truyền như thế nào.
- Có khoảng trễ hay trạng thái cần xác minh không.
- Sau failover, consumer có gặp cùng nguồn credential không.

Không tự đổi password trên mọi node bằng các thao tác riêng nếu kiến trúc yêu cầu quản lý ở nguồn tập trung. Cũng không coi thành công trên một node là bằng chứng toàn bộ cụm đã đồng bộ.

### 13.2. Đường đọc, ghi và dự phòng có thể khác

Ứng dụng có thể dùng endpoint ghi, endpoint đọc hoặc đường dự phòng với các điều kiện khác nhau.

Kế hoạch cần bao phủ những đường thực sự sử dụng credential. Không cần tạo failover production chỉ để kiểm tra nếu chưa có kế hoạch phù hợp; phần chưa diễn tập phải được ghi rõ.

### 13.3. Proxy và pooler có nhiều lớp trạng thái

Có thể tồn tại:

~~~text
Ứng dụng → xác thực với proxy.
Proxy → giữ hoặc lấy credential upstream.
Proxy → duy trì pool kết nối tới database.
~~~

Ứng dụng mở được kết nối mới tới proxy chưa chứng minh proxy đã mở kết nối upstream mới bằng mật khẩu mới.

Cần bằng chứng phù hợp từng lớp, đồng thời quản lý cache và reload ở proxy. Thay credential backend có thể ảnh hưởng nhiều client dùng chung proxy.

### 13.4. Tài khoản hạ tầng là đối tượng riêng

Credential replication, backup hạ tầng hoặc quản trị dịch vụ có thể có cơ chế vòng đời đặc thù.

Không gộp vào cùng một luồng rotation tài khoản runtime chỉ vì chúng đều liên quan tới database. Mỗi đối tượng cần phạm vi, quyền, consumer và phương án phục hồi riêng.

## 14. Timeout, lỗi từng phần và retry

### 14.1. Ma trận trạng thái

| Trạng thái đã xác minh | Hướng xử lý cần xem xét |
|---|---|
| Nguồn chưa thay, vault và consumer vẫn cũ | Sửa nguyên nhân trước khi thử lại |
| Nguồn đã thay, vault chưa đồng bộ | Đối soát hoặc reconcile qua cơ chế an toàn |
| Nguồn và vault đúng, consumer còn cũ | Hoàn tất chuyển consumer theo kế hoạch |
| Một số consumer đã chuyển | Chọn trạng thái hội tụ, tránh đổi mù về mật khẩu cũ |
| Không biết nguồn đã thay chưa | Dừng retry thiếu kiểm soát và xác minh |
| Proxy hoặc node có trạng thái khác nhau | Khoanh lớp và phạm vi, không suy rộng kết quả |
| Đổi thành công nhưng không lưu được bằng chứng | Theo dõi hiệu ứng đã xảy ra và xử lý yêu cầu audit |
| Credential mới bị lộ trong chẩn đoán | Xử lý phơi lộ, không chỉ xóa thông báo |

### 14.2. Retry có thể tạo thêm thay đổi

Một lần timeout có thể xảy ra sau khi password đã đổi. Tạo password khác rồi thử lại ngay có thể khiến vault và consumer không biết phiên bản nào có hiệu lực.

Cần giữ rotation ID, account, thời điểm, phiên bản dự kiến và trạng thái đã quan sát. Cơ chế thử lại phải dựa trên precondition cùng kết quả đối soát.

Không log mật khẩu để giải quyết sự không chắc chắn.

### 14.3. Giới hạn thử xác thực

Lỗi có thể do network, trust, trạng thái tài khoản, policy hoặc password. Thử lặp nhiều lần có thể khóa tài khoản và làm phức tạp sự cố.

Phân loại lỗi trước khi tăng số lần thử. Không bỏ xác minh máy chủ hoặc mở quyền rộng để che một lỗi connector chưa được hiểu.

### 14.4. Tách tiến trình đang chạy khỏi kết quả client

Client hết thời gian chờ không chứng minh tác vụ tại nguồn đã dừng. Trước khi bắt đầu thao tác thay đổi khác, cần biết actor cũ còn có thể tạo hiệu ứng không.

Một nút cancel trên giao diện không tự rollback mọi thay đổi bên ngoài.

## 15. Reconcile, rollback và roll forward

### 15.1. Chọn theo trạng thái thực tế

Rollback không nhất thiết là đặt lại password cũ. Một trạng thái cũ có thể không còn an toàn, không còn đồng bộ hoặc không được nguồn xác thực cho phép tái sử dụng.

Nếu database và vault đã đúng, cập nhật nốt consumer có thể phù hợp hơn. Nếu trạng thái chưa xác định, cần đối soát trước khi quyết định.

Cần mô tả rõ trạng thái phục hồi:

~~~text
Credential nào có hiệu lực tại nguồn?
Vault quản lý phiên bản nào?
Consumer nào đã chuyển?
Đường nào còn cần xử lý?
Phiên nào được tiếp tục hoặc kết thúc?
Tự động hóa nào có thể được bật lại?
~~~

### 15.2. Reconcile cần đúng thẩm quyền

Nếu có danh tính được phép reset, việc sử dụng phải gắn với đúng tài khoản và phạm vi.

Không reset một tài khoản dùng chung rộng hơn dự kiến. Cần kiểm tra consumer, tác vụ đang chạy và tác động của reset lên các đường đăng nhập khác.

Một tài khoản reconcile cũng là đặc quyền cần bảo vệ, không phải một lối bỏ kiểm soát thường trực.

### 15.3. Bảo toàn khả năng phục hồi

Không xóa phiên bản hoặc đối tượng quản lý cần cho đối soát trước khi biết trạng thái cuối.

Giữ lịch sử và tham chiếu bằng chứng, đồng thời kiểm soát quyền đọc các phiên bản credential theo vòng đời. Không đưa password cũ vào ticket với lý do cần rollback.

Khôi phục snapshot vault cũ có thể đưa secret cũ trở lại trong khi database vẫn dùng password mới. Phục hồi dữ liệu quản lý phải đi cùng đối soát với trạng thái nguồn xác thực.

### 15.4. Bật lại tự động hóa

Trước khi mở lại scheduler hoặc pipeline, xác minh chúng dùng đúng account, reference và cấu hình hiện hành.

Một tác vụ tự động còn giữ trạng thái cũ có thể đổi password thêm lần nữa hoặc phân phối lại reference sai. Đóng phần phục hồi kỹ thuật cần bao gồm những actor này trong phạm vi liên quan.

## 16. Rotation khẩn cấp khi nghi lộ password

### 16.1. Phạm vi khác rotation thường kỳ

Khi có dấu hiệu lộ password, cần đánh giá:

- Password có thể đã bị lấy ở đâu.
- Tài khoản dùng được trên những đích nào.
- Quyền hiệu lực và khả năng tạo thay đổi bền vững.
- Những consumer hợp lệ cần chuyển.
- Phiên đã mở và nguồn kết nối liên quan.
- Các credential hoặc phương thức xác thực thay thế.

Không chỉ chạy lại lịch rotation rồi coi sự cố đã kết thúc.

### 16.2. Credential và phiên là hai lớp

Đổi password có thể ngăn một phần xác thực mới theo cơ chế nguồn. Phiên cũ có thể tiếp tục.

Cần quyết định và thực thi cách xử lý phiên, grant, khóa hoặc tài khoản khác nếu có bằng chứng liên quan. Những thay đổi đã được thực hiện trong database cũng cần đánh giá riêng.

Nếu chọn vô hiệu hóa tài khoản, phải hiểu ảnh hưởng tới consumer hợp lệ và phương án phục hồi hoặc chuyển danh tính.

### 16.3. Không để dependency che khuất rủi ro còn lại

Consumer chưa cập nhật là một vấn đề cần xử lý. Nó không tự tạo thẩm quyền giữ password nghi lộ hoạt động vô thời hạn.

Cần phối hợp ưu tiên dịch vụ, mức ảnh hưởng và quyền quyết định theo phạm vi. Nếu phải có trạng thái tạm thời, phải ghi owner, điều kiện, thời hạn và biện pháp kiểm soát.

### 16.4. Bằng chứng kết thúc

Cần làm rõ credential nào còn hiệu lực, quyền và phiên nào đã được xử lý, consumer nào hoạt động và những giới hạn chưa khắc phục.

Nếu password bị lộ qua log chẩn đoán trong quá trình xử lý, đó là một điểm phơi lộ mới cần được đưa vào vòng đời credential.

## 17. Audit và bằng chứng rotation

### 17.1. Các sự kiện cần liên kết

~~~text
Yêu cầu hoặc lịch rotation
  → danh tính thực hiện và phạm vi
  → preflight và kế hoạch consumer
  → chuẩn bị credential
  → thay tại nguồn
  → xác minh nguồn
  → cập nhật vault
  → chuyển từng consumer
  → kiểm chứng xác thực mới và chức năng
  → xử lý credential cũ, phiên và phần còn lại.
~~~

Cần phân biệt thời điểm gửi yêu cầu, nhận kết quả và xác minh. Những mốc này có thể khác nhau.

### 17.2. Hồ sơ logic minh họa

~~~yaml
rotation_record:
  rotation_id: rotation-db-042
  account_id: payment-service-account
  authentication_source_id: payment-db-native-identity
  target_scope_reference: approved-db-endpoint-set
  previous_version_reference: version-12
  candidate_version_reference: version-13
  state_at_source: fresh-authentication-verified
  managed_state: published
  consumer_state:
    application_group: verified-for-recorded-scope
    scheduled_job: pending-validation
    backup_tool: verified-for-recorded-scope
  old_password_handling: requires-final-evidence
  session_handling: tracked-separately
  recovery_reference: recovery-db-017
  overall_state: partial-completion
~~~

Các giá trị chỉ minh họa; không phải cú pháp của sản phẩm. Hồ sơ không chứa password và không tuyên bố hoàn tất khi một phần phạm vi còn chờ.

### 17.3. Bảo vệ log và dữ liệu chẩn đoán

Log SQL, audit quản trị, trace của connector hoặc báo lỗi có thể ghi dữ liệu nhạy cảm nếu cơ chế không xử lý đúng.

Cần kiểm tra cách che giá trị credential theo đường thực thi, không chỉ che ở giao diện PAM. Không lưu nguyên request hoặc câu lệnh chứa password làm bằng chứng.

Dùng account ID, version reference, rotation ID và evidence reference để tương quan. Không dùng password hoặc hash đơn giản của password làm nhãn metric.

### 17.4. Giữ lịch sử trung thực

Không sửa lùi mốc thời gian để che khoảng không đồng bộ. Không đổi kết quả thất bại thành thành công chỉ vì một tác vụ sau đã khắc phục.

Lịch sử cần cho biết phần nào xảy ra trước, phần nào được đối soát và trạng thái cuối trong phạm vi nào.

## 18. Tình huống xuyên suốt: tài khoản runtime của dịch vụ thanh toán

### 18.1. Bối cảnh

Một dịch vụ có:

- Nhiều instance API đọc secret khi khởi động.
- Worker giữ connection pool dài hạn.
- Job đối soát theo lịch.
- Công cụ backup dùng cùng tài khoản.
- Một proxy quản lý kết nối upstream.
- Template dự phòng có secret reference.

Nguồn xác thực trong tình huống giả định chỉ cho một mật khẩu hiệu lực cho tài khoản này. Đội triển khai đã xác định kế hoạch chuyển đổi và đường phục hồi theo phạm vi.

### 18.2. Thay đổi bị dừng giữa chừng

Connector chuẩn bị credential version-13 và gửi yêu cầu đổi. Nguồn đã áp dụng nhưng phản hồi bị mất.

Vault chưa công bố phiên bản mới. Một số kết nối cũ vẫn phục vụ bình thường. Các kết nối mới bắt đầu lỗi.

Dashboard tác vụ ghi timeout, nhưng không thể từ đó kết luận database còn dùng version-12.

### 18.3. Ổn định và đối soát

Đội xử lý dừng retry theo tài khoản liên quan, xác định actor cũ còn chạy không và giữ rotation reference.

Qua phương pháp kiểm tra được cho phép, họ xác minh password mới đã có hiệu lực ở nguồn. Trạng thái vault được đối soát và cập nhật theo cơ chế phục hồi an toàn.

Họ không đặt lại password cũ ngay vì consumer có thể đã chuyển từng phần, và trạng thái cũ không được chọn làm mục tiêu phục hồi.

### 18.4. Chuyển và kiểm tra consumer

API được chuyển theo nhóm phù hợp khả năng ứng dụng. Worker được kiểm tra ở đường mở kết nối mới, không chỉ nhìn pool cũ.

Với proxy, cần xác minh cả đường ứng dụng tới proxy và proxy tới database theo phạm vi. Nếu chỉ kiểm tra client mới tới proxy, pool upstream cũ có thể vẫn che lỗi.

Backup và job có kế hoạch kiểm tra riêng. Template dự phòng được cập nhật để không tái tạo reference cũ.

### 18.5. Báo cáo từng phần

Một báo cáo có thể ghi:

~~~text
Nguồn xác thực: version-13 đã được xác minh bằng kết nối mới.
Vault: trạng thái quản lý đã được đối soát.
API: đạt trong tập instance được ghi.
Worker: kết nối mới đạt theo đường kiểm tra.
Proxy upstream: đã xác minh trong phạm vi đã định.
Backup: đạt.
Job đối soát: còn chờ kiểm tra đường chạy.
Dự phòng: cấu hình đã cập nhật; phần diễn tập chưa thực hiện được ghi rõ.
~~~

Không báo hoàn tất mọi consumer khi job đối soát còn chờ. Có thể đóng một phần phục hồi kỹ thuật theo phạm vi và giữ công việc xác minh còn lại với owner cùng điều kiện rõ.

### 18.6. Cải thiện sau sự cố

Cần xem xét connector xử lý timeout, checkpoint, khả năng đối soát và cách phân biệt trạng thái nguồn với trạng thái client.

Có thể cần tách tài khoản backup khỏi runtime để giảm phụ thuộc. Việc tách phải đi cùng thiết kế quyền đúng nhu cầu, không chỉ sao chép toàn bộ quyền sang thêm một tài khoản.

## 19. Tiêu chí nghiệm thu và kiểm chứng

### 19.1. Nghiệm thu theo tuyên bố

| Tuyên bố | Bằng chứng phù hợp |
|---|---|
| Đã đổi đúng tài khoản | Nguồn, account và phạm vi được xác định rõ |
| Password mới có hiệu lực | Xác thực mới theo đúng phương thức và endpoint |
| Vault đã đồng bộ | Đối tượng và phiên bản quản lý khớp trạng thái đã xác minh |
| Consumer đã cập nhật | Reference hoặc cơ chế phân phối cùng trạng thái runtime |
| Consumer dùng được | Xác thực mới và chức năng đại diện |
| Credential cũ đã được xử lý | Bằng chứng từ cơ chế nguồn phù hợp mục tiêu |
| Phiên đã được xử lý | Trạng thái từ proxy, gateway hoặc database liên quan |
| HA hoặc đường dự phòng đạt | Kết quả trong phạm vi endpoint hoặc tình huống đã kiểm tra |
| Tự động hóa tiếp tục đúng | Actor dùng cấu hình và reference hiện hành |
| Có thể phục hồi | Phương án được xác minh theo tình huống đã xác định |

Không suy rộng từ một endpoint hoặc một instance sang toàn bộ hệ thống.

### 19.2. Các tình huống cần kiểm chứng

- Nguồn từ chối password mới do policy hoặc định dạng.
- Thay tại nguồn thành công nhưng cập nhật vault lỗi.
- Consumer giữ cache sau khi secret đã đổi.
- Job không chạy trong cửa sổ triển khai.
- Timeout trước và sau khi đích áp dụng.
- Hai actor cùng cố rotation một tài khoản.
- Proxy giữ kết nối upstream cũ.
- Một endpoint chưa phản ánh thay đổi theo cơ chế thực tế.
- Mất quyền hoặc credential reconcile.
- Audit không lưu được ở một bước có hiệu ứng.
- Password bị thu hồi nhưng phiên cũ còn hoạt động.

Cách kiểm chứng cần phù hợp môi trường và phạm vi. Không tạo gián đoạn production ngoài kế hoạch chỉ để chứng minh một kịch bản lỗi.

### 19.3. Chỉ số vận hành

Có thể theo dõi:

- Rotation theo trạng thái nguồn, vault và consumer.
- Thời gian từ thay tại nguồn tới consumer xác thực mới.
- Tác vụ timeout hoặc không xác định.
- Lỗi xác thực sau rotation.
- Consumer còn dùng reference hoặc bản sao cũ.
- Credential cũ còn trong giai đoạn chuyển tiếp.
- Thời gian reconcile và phục hồi.
- Phạm vi dependency chưa xác minh.
- Thay đổi quyền hoặc cấu hình ngoài kế hoạch.

Số tác vụ “đã chạy” không phải số tài khoản đã rotation hoàn tất. Mẫu số và phạm vi của các tỷ lệ phải được ghi rõ.

## 20. Lỗi thường gặp và bài tập áp dụng

### 20.1. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ đổi trường password trong vault | Đích vẫn chấp nhận credential cũ | Thực hiện và xác minh tại đúng nguồn |
| Lệnh đổi thành công là coi xong | Consumer hoặc proxy chưa đồng bộ | Theo dõi từng lớp trạng thái |
| Ứng dụng khỏe là coi password mới dùng được | Pool cũ che lỗi | Kiểm tra xác thực mới |
| Mặc định mọi engine hỗ trợ hai password | Kế hoạch chuyển đổi không thực hiện được | Xác minh khả năng thật |
| Tạo tài khoản thứ hai rồi sao chép toàn quyền | Tăng đặc quyền và sai ngữ nghĩa danh tính | Kiểm tra role, ownership và nhu cầu |
| Không kiểm kê backup và job | Lỗi xuất hiện muộn | Lập kế hoạch từng nhóm consumer |
| Chỉ sửa runtime, bỏ template | Deploy sau khôi phục reference sai | Cập nhật nguồn cấu hình mong muốn |
| Retry ngay sau timeout | Tăng số phiên bản lệch và mất dấu trạng thái | Đối soát trước khi thử lại |
| Reset tài khoản tập trung như tài khoản local | Ảnh hưởng nhiều hệ thống | Xác định nguồn và phạm vi identity |
| Dùng phiên cũ để xác minh | Không chứng minh lần đăng nhập mới | Kết nối mới đúng đường |
| Đổi password là coi hết phiên và quyền | Hoạt động cũ hoặc grant vẫn còn | Quản lý phiên và quyền riêng |
| Log câu lệnh có password | Tạo điểm lộ credential | Dùng cơ chế che dữ liệu và metadata |
| Bỏ kiểm tra trust khi chẩn đoán | Có thể gửi credential tới sai đích | Sửa nguyên nhân tin cậy |
| Đóng thay đổi khi còn consumer unknown | Báo vượt bằng chứng | Giữ phạm vi, owner và phần còn lại |

### 20.2. Bài tập

Một tài khoản database được dùng bởi ứng dụng, proxy và job cuối tháng. PAM báo đổi password thành công. Ứng dụng không lỗi vì đang dùng pool cũ. Proxy nhận kết nối client mới nhưng chưa mở kết nối upstream mới. Job không có log gần đây. Template triển khai còn chứa reference trước rotation.

Hãy trả lời:

1. Những tuyên bố nào chưa đủ bằng chứng?
2. Cần kiểm tra các lớp xác thực nào của proxy?
3. Vì sao lần deploy sau có thể gây sự cố?
4. Có thể xác minh job ít chạy bằng cách nào trong phạm vi được phép?
5. Nếu tác vụ thực tế timeout sau khi database đã đổi, vì sao không nên thử đổi ngay lần nữa?
6. Cần gì để kết luận rotation hoàn tất theo phạm vi?

Hướng phân tích:

- Thành công của tác vụ và tình trạng ứng dụng chưa chứng minh mọi kết nối mới hoặc consumer đã dùng password mới.
- Cần phân biệt client tới proxy và proxy tới nguồn xác thực database.
- Nguồn cấu hình mong muốn có thể đưa reference cũ trở lại.
- Cần một đường kiểm tra phù hợp khả năng job, hoặc công việc xác minh có owner và trạng thái rõ; không tự chạy tác vụ có tác động ngoài kế hoạch.
- Retry mù có thể tạo thêm credential mới trong khi các thành phần chưa biết trạng thái trước.
- Cần bằng chứng nguồn, vault, consumer, credential cũ, phiên và phần HA hoặc dự phòng đã cam kết.

## 21. Các điểm cần nắm

Rotation database password là quá trình đồng bộ thay đổi giữa nguồn xác thực, vault, consumer, proxy và các nguồn cấu hình liên quan.

Một lần đổi password thành công không tự chứng minh consumer đã chuyển, credential cũ đã mất hiệu lực hoặc phiên cũ đã đóng. Kết nối mới và tác vụ đại diện là những loại bằng chứng cần được thiết kế theo phạm vi.

Khi xử lý lỗi, bắt đầu từ trạng thái thực tế, kiểm soát actor ghi đồng thời và đối soát trước khi retry. Chỉ báo hoàn tất những phần đã được xác minh, đồng thời giữ rõ owner và công việc của phần còn lại.
