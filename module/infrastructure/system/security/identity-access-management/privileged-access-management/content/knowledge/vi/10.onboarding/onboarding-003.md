# Onboard database

## Mục tiêu bài học

Trong chương **Onboarding**, onboard database vào **Privileged Access Management (PAM)** là quá trình đưa các tài khoản, credential và đường sử dụng đặc quyền của cơ sở dữ liệu vào cơ chế quản lý có chủ sở hữu, chính sách và bằng chứng.

Phạm vi bao gồm tài khoản quản trị, tài khoản dịch vụ, danh tính triển khai và đường truy cập khẩn cấp trên hạ tầng dữ liệu nhạy cảm. Kết quả cần hỗ trợ kiểm kê quyền, least privilege, JIT/JEA khi phù hợp, lưu giữ bí mật trong vault, luân chuyển credential, giám sát phiên và ứng phó sự cố.

**Tạo một bản ghi chứa mật khẩu trong vault chưa đủ để coi cơ sở dữ liệu đã được onboard.** Cần chứng minh đúng tài khoản được quản lý, tác vụ hợp lệ vẫn hoạt động, đường sử dụng được kiểm soát và credential có vòng đời đã xác minh.

Sau bài học, bạn có thể:

- Xác định đối tượng và phạm vi của một đợt onboarding cơ sở dữ liệu.
- Phân biệt tài khoản quản trị, tài khoản ứng dụng, tài khoản triển khai và tài khoản khẩn cấp.
- Chuẩn bị quyền, kết nối, phụ thuộc và cơ chế phục hồi trước thay đổi.
- Thiết kế lưu credential, kiểm soát phiên và rotation phù hợp với hệ thống đích.
- Thực hiện cutover theo giai đoạn và xác định tiêu chí nghiệm thu.
- Lưu bằng chứng đủ để giải thích trạng thái quản lý và điều tra sự cố.

## 1. “Onboard database” thực sự đưa những gì vào PAM?

Trong bài này, onboarding không phải thao tác tạo mới một cơ sở dữ liệu. Đối tượng được đưa vào quản lý là các danh tính và đường đặc quyền liên quan đến một hệ thống cơ sở dữ liệu.

Một cơ sở dữ liệu có thể có nhiều lớp:

~~~text
Nền tảng hoặc máy chủ
        |
        v
Instance hoặc cụm cơ sở dữ liệu
        |
        v
Database và phạm vi dữ liệu
        |
        v
Schema, đối tượng và thao tác
~~~

Quyền quản trị hệ điều hành, quyền quản trị dịch vụ cơ sở dữ liệu và quyền trên dữ liệu là những lớp khác nhau. Quản lý tài khoản ở một lớp không tự bao phủ các lớp còn lại.

Ngoài ra, mô hình danh tính khác nhau giữa các hệ quản trị:

- Có hệ thống tách danh tính đăng nhập với người dùng trong từng database.
- Role có thể là tập quyền, principal đăng nhập hoặc có hành vi khác tùy nền tảng.
- Xác thực có thể do cơ sở dữ liệu thực hiện hoặc được ủy quyền cho nguồn bên ngoài.
- Phạm vi thay đổi credential có thể nằm ở tài khoản, instance, cụm hoặc nguồn danh tính.

Vì vậy, phải ánh xạ theo mô hình thực tế. Không áp dụng một chuỗi lệnh SQL chung cho mọi hệ quản trị.

### Những ranh giới cần ghi rõ

| Ranh giới | Ví dụ câu hỏi |
| --- | --- |
| Hệ thống đích | Đây là môi trường thử nghiệm hay production? |
| Phạm vi tài khoản | Tài khoản thuộc instance nào, database nào hoặc nguồn danh tính nào? |
| Phạm vi quyền | Có quyền trên một schema, toàn database hay toàn nền tảng? |
| Đường truy cập | Qua broker, công cụ DBA, ứng dụng hay pipeline? |
| Vòng đời credential | Ai đổi, đổi tại đâu và bên nào nhận phiên bản mới? |
| Bằng chứng | Có thể liên kết danh tính ban đầu với hoạt động ở đích không? |

## 2. Xác định loại tài khoản trước khi chọn cách quản lý

Không nên dùng cùng một chính sách cho mọi tài khoản.

| Nhóm | Nhu cầu điển hình | Hướng kiểm soát cần đánh giá |
| --- | --- | --- |
| Tài khoản DBA | Chẩn đoán, bảo trì, thay đổi quản trị | Danh tính cá nhân, phê duyệt, broker, giới hạn nhiệm vụ hoặc thời gian |
| Tài khoản ứng dụng | Kết nối liên tục để thực hiện chức năng dịch vụ | Quyền dữ liệu hẹp, lấy bí mật có kiểm soát, rotation gắn với phụ thuộc |
| Tài khoản triển khai | Migration hoặc thay đổi cấu trúc theo đợt | Tách khỏi runtime, giới hạn scope và thời gian |
| Tài khoản rotation | Đổi và kiểm tra credential được giao | Quyền tối thiểu theo connector và hệ thống đích |
| Tài khoản đối soát hoặc phục hồi | Khôi phục trạng thái khi credential không còn khớp | Quyền mạnh được bảo vệ riêng, sử dụng có kiểm soát |
| Tài khoản khẩn cấp | Phục hồi khi đường truy cập thông thường mất | Quy trình break-glass, kiểm tra khả dụng, review sau sử dụng |

Một tài khoản dùng đồng thời cho ứng dụng và người vận hành tạo khó khăn cho rotation, truy vết và thu hồi. Phương án ưu tiên là tách theo nhiệm vụ nếu hệ thống và kế hoạch chuyển đổi cho phép.

Không phải mọi tài khoản kết nối cơ sở dữ liệu đều cần đặc quyền cao. Việc onboarding cần đi cùng đánh giá nhu cầu, tránh hợp thức hóa quyền quản trị rộng chỉ vì tài khoản đã được đưa vào vault.

## 3. Xác định trách nhiệm và điều kiện bắt đầu

Một đợt onboarding cần có người chịu trách nhiệm cho cả bảo mật lẫn hoạt động dịch vụ.

| Vai trò | Trách nhiệm |
| --- | --- |
| Chủ sở hữu dịch vụ | Xác nhận nhu cầu, phụ thuộc và tác động đến người dùng |
| Chủ sở hữu cơ sở dữ liệu hoặc DBA | Xác nhận principal, quyền và cơ chế đích |
| Nhóm PAM/IAM | Thiết kế chính sách, vault, danh tính và luồng sử dụng |
| Nhóm ứng dụng | Chuyển cách nhận credential, kiểm tra hành vi runtime |
| Nhóm nền tảng hoặc mạng | Chuẩn bị tuyến kết nối, endpoint, chứng thư và khả năng phục hồi |
| Người chấp nhận thay đổi | Xác nhận phạm vi, thời điểm và rủi ro còn lại |
| Người xác minh | Kiểm tra tiêu chí nghiệm thu và lưu bằng chứng |

Tùy quy mô, một người có thể đảm nhiệm nhiều vai trò. Những thao tác mạnh như sửa chính sách vault, dùng tài khoản reset hoặc thay đổi quyền quản trị cần mức kiểm soát độc lập phù hợp.

### Điều kiện đầu vào

Trước khi thay đổi credential trên production, tối thiểu cần xác định:

1. Hệ thống đích và tài khoản đúng.
2. Chủ sở hữu và mục đích sử dụng.
3. Quyền hiện tại và quyền cần giữ.
4. Các bên phụ thuộc đã biết cùng giới hạn kiểm kê.
5. Cách cập nhật, xác minh và xử lý lỗi credential.
6. Người thực hiện, thời điểm và tiêu chí dừng.
7. Phương án truy cập phục hồi phù hợp.
8. Cách thu thập bằng chứng.

Nếu thiếu thông tin làm ảnh hưởng trực tiếp đến khả năng khôi phục hoặc tính liên tục dịch vụ, cần giữ trạng thái chờ xử lý cho phần liên quan. Không nên đổi mật khẩu trước rồi mới tìm ứng dụng đang dùng.

## 4. Khảo sát kiến trúc và lập phạm vi

Cần mô tả hệ thống đủ để tránh thay đổi nhầm principal hoặc endpoint.

Những thông tin cần có:

- Hệ quản trị và kiểu triển khai.
- Instance, cụm, database, môi trường và định danh tài nguyên.
- Endpoint dùng bởi ứng dụng, DBA và bộ rotation.
- Nguồn xác thực: nội bộ database, thư mục, nền tảng hoặc cơ chế khác.
- Cơ chế kết nối bảo vệ đường truyền và xác thực máy chủ.
- Vai trò các node, tuyến truy cập và hành vi failover.
- Cách lưu và đồng bộ tài khoản theo thiết kế thực tế.
- Nguồn audit và khả năng liên kết phiên.

### Cụm và failover

Một địa chỉ kết nối có thể đại diện cho cả cụm, còn một node vật lý có thể đổi vai trò sau failover. Bản ghi PAM phải liên kết được với đúng tài khoản và cơ chế quản lý trong cấu trúc đó.

Cần xác nhận:

- Thao tác đổi credential phải đi đến endpoint nào?
- Có được phép thao tác trên node chỉ đọc không?
- Credential hoặc principal có được đồng bộ giữa các node không, theo cách nào?
- Sau failover, connector và broker còn tìm đúng đích không?
- Có nguy cơ tạo nhiều bản ghi PAM độc lập cùng quản lý một principal không?

Không mặc định đổi mật khẩu ở mọi node là an toàn. Cũng không mặc định thay đổi trên một node luôn tự lan đến toàn cụm.

### Xác thực bên ngoài

Nếu database sử dụng nguồn danh tính bên ngoài, nơi có thẩm quyền thay đổi credential có thể nằm ngoài database. Cần quản lý đúng nguồn, đồng thời review quyền được ánh xạ vào database.

Trong trường hợp không sử dụng mật khẩu database tĩnh, PAM vẫn cần xét quyền nhận danh tính, vòng đời token hoặc chứng thư, quyền ở đích và khả năng truy vết.

## 5. Kiểm kê tài khoản, quyền và đường truy cập

### 5.1. Định danh chính xác

Không dùng tên tài khoản đơn lẻ làm định danh duy nhất. Cùng một tên có thể tồn tại trên nhiều instance hoặc môi trường nhưng đại diện cho những principal khác nhau.

Bản kiểm kê nên liên kết được:

~~~text
Nguồn danh tính hoặc hệ thống
        + phạm vi instance/cụm/database
        + ID principal hoặc định danh gốc
        + mục đích và chủ sở hữu
~~~

Nếu nền tảng không có ID ổn định, cần ghi giới hạn và quy tắc đối soát.

### 5.2. Review quyền hiệu lực

Cần xét quyền trực tiếp, role, nhóm, kế thừa, sở hữu đối tượng, điều kiện và các khả năng quản trị gián tiếp theo quy tắc của hệ quản trị.

Những câu hỏi quan trọng:

- Tài khoản có thể tạo hoặc sửa principal khác không?
- Có thể cấp role hoặc thay đổi cơ chế xác thực không?
- Có thể thay audit, backup hoặc cấu hình nhạy cảm không?
- Có quyền ngoài database ứng dụng thực sự cần không?
- Có thể sửa công việc hoặc mã chạy dưới danh tính mạnh hơn không?

Không nên chỉ nhìn tên role rồi kết luận phạm vi. Một role tên “operator” vẫn có thể chứa khả năng rất mạnh.

### 5.3. Xác định đường sử dụng hiện tại

Phải tìm cả:

- Công cụ DBA và phiên quản trị tương tác.
- Ứng dụng runtime và worker nền.
- Job theo lịch, báo cáo, đồng bộ và tác vụ bảo trì.
- Pipeline triển khai hoặc migration.
- Script vận hành và công cụ giám sát.
- Credential đã được phát hành hoặc sao chép ngoài đường quản lý dự kiến.

Không đưa giá trị bí mật vào hồ sơ kiểm kê. Dùng tham chiếu được bảo vệ, thông tin phiên bản và nơi phân phối thay vì sao chép mật khẩu.

## 6. Phụ thuộc ứng dụng quyết định kế hoạch rotation

Với tài khoản dịch vụ, cần hiểu ứng dụng sử dụng credential thế nào.

| Câu hỏi | Ảnh hưởng đến onboarding |
| --- | --- |
| Bí mật được đọc lúc khởi động hay khi cần? | Có thể cần nạp lại hoặc khởi động lại sau thay đổi |
| Có connection pool không? | Kết nối cũ và kết nối mới có hành vi khác nhau |
| Có cache credential không? | Phiên bản cũ có thể tiếp tục tồn tại bên ngoài vault |
| Có nhiều instance ứng dụng không? | Cần chuyển đổi và xác minh đủ các bên |
| Có job chạy hiếm không? | Cửa sổ quan sát ngắn có thể bỏ sót phụ thuộc |
| Đích hỗ trợ nhiều credential đồng thời không? | Quyết định có thể chuyển tiếp theo giai đoạn hay không |
| Ứng dụng xử lý lỗi xác thực ra sao? | Retry không phù hợp có thể gây tải hoặc khóa tài khoản |

Một kiểm tra kết nối thành công từ máy DBA không chứng minh ứng dụng sẽ hoạt động sau rotation.

Cũng không thể chỉ kiểm tra một connection pool đang giữ kết nối cũ. Cần có cách xác nhận kết nối mới sử dụng đúng credential mới theo kế hoạch thử nghiệm.

### Khi chưa đủ thông tin

Có thể tiếp tục những phần độc lập như xác nhận principal, thiết kế policy hoặc chuẩn bị môi trường thử nghiệm. Với phần phụ thuộc chưa rõ, phải ghi rõ giới hạn và người chịu trách nhiệm xác nhận trước cutover tương ứng.

Không coi “chưa thấy ứng dụng nào khác” là bằng chứng chắc chắn không còn bên phụ thuộc.

## 7. Thiết kế trạng thái đích theo least privilege

Onboarding là thời điểm phù hợp để phân tách những nhu cầu đang bị gộp chung.

Ví dụ, một tài khoản quản trị đang phục vụ cả ứng dụng A, migration và DBA. Có thể thiết kế:

| Danh tính hoặc vai trò | Nhu cầu | Giới hạn mong muốn |
| --- | --- | --- |
| Runtime ứng dụng A | Đọc/ghi dữ liệu phục vụ chức năng A | Chỉ phạm vi dữ liệu và hành động cần thiết |
| Triển khai A | Thay đổi cấu trúc được chấp nhận | Theo đợt triển khai, đúng database và quy trình |
| Người vận hành | Chẩn đoán hoặc bảo trì | Danh tính có thể truy vết, nhiệm vụ và thời gian phù hợp |
| Phục hồi khẩn cấp | Khôi phục trong tình huống đã định nghĩa | Điều kiện kích hoạt, bảo vệ riêng và review sau dùng |

Đây là mô tả nhu cầu, không phải danh sách quyền SQL có thể sao chép nguyên trạng. Quyền cụ thể cần được ánh xạ theo hệ quản trị.

### JIT và JEA

**JIT** giới hạn thời điểm hoặc thời gian quyền có hiệu lực. Cần kiểm tra cơ chế cấp, hết hạn, thu hồi và phiên tại đích.

**JEA** giới hạn khả năng thực thi theo nhiệm vụ. Một công cụ “chạy script bảo trì” nhưng cho sửa script tùy ý có thể vẫn tạo quyền rộng.

Không coi thời hạn yêu cầu trong PAM là bằng chứng mọi quyền trên database đã hết. Credential, role được cấp thêm và phiên đang tồn tại có thể có vòng đời riêng.

## 8. Chuẩn bị kết nối và quyền của thành phần PAM

Mô hình logic thường gồm:

~~~mermaid
flowchart TD
    Human[Người vận hành] --> Access[Cổng PAM và chính sách]
    Access --> Broker[Broker hoặc đường truy cập được chấp nhận]
    App[Ứng dụng hoặc pipeline] --> SecretAPI[Đường nhận credential theo danh tính]
    SecretAPI --> Vault[Vault]
    Broker --> Vault
    Rotation[Bộ rotation] --> Vault
    Broker --> DB[Cơ sở dữ liệu]
    App --> DB
    Rotation --> DB
    Broker --> Audit[Bằng chứng được bảo vệ]
    Rotation --> Audit
    DB --> Audit
~~~

Ứng dụng có thể nhận credential có kiểm soát rồi kết nối trực tiếp đến database theo thiết kế. Không phải mọi kết nối ứng dụng đều phải đi qua broker phiên của người dùng.

### 8.1. Kết nối mạng và xác thực đích

Cần kiểm tra tuyến kết nối của broker, rotation và ứng dụng riêng biệt. Một tuyến hoạt động không chứng minh các tuyến còn lại hoạt động.

Xác thực máy chủ và bảo vệ đường truyền phải phù hợp với giao thức. Không nên giải quyết lỗi kết nối bằng cách bỏ kiểm tra đích hoặc mở truy cập rộng cho mọi nguồn.

### 8.2. Quyền rotation và đối soát

Connector có thể đổi credential bằng tài khoản tự đổi mật khẩu hoặc bằng danh tính quản lý khác, tùy khả năng đích.

Cần xác định rõ:

- Có cần credential cũ để đổi không?
- Quyền reset tài khoản khác có phạm vi nào?
- Có thể giới hạn chỉ các tài khoản được giao không?
- Khi trạng thái không khớp, ai được phép thực hiện đối soát?
- Bằng chứng nào ghi nhận việc sử dụng quyền mạnh?

Không mặc định cần một tài khoản quản trị toàn cục dùng chung cho tất cả connector.

### 8.3. Kiểm tra tương thích

Cần xác nhận connector và đường phiên đáp ứng cơ chế xác thực, kiểu credential, chính sách mật khẩu hoặc chứng thư, mô hình cụm và hành vi đích.

Khả năng mở kết nối thành công chưa chứng minh hỗ trợ đầy đủ rotation, thu hồi hay giám sát phiên.

## 9. Tạo bản ghi và chính sách trong PAM

Một bản ghi quản lý cần đủ thông tin để vận hành mà không phải đoán lại:

- Định danh principal và hệ thống đích.
- Môi trường, phạm vi và mục đích sử dụng.
- Chủ sở hữu cùng bên phụ thuộc.
- Cơ chế xác thực và tham chiếu credential.
- Cách sử dụng được phép: truy xuất, broker hoặc cơ chế khác.
- Người có thể yêu cầu, duyệt, xem bí mật hoặc sửa policy.
- Cơ chế rotation, xác minh và xử lý lỗi.
- Chính sách phiên, bằng chứng và truy cập khẩn cấp.

Quyền yêu cầu một phiên không nhất thiết bao gồm quyền xem mật khẩu. Quyền vận hành vault cũng không nên tự động cho phép sử dụng mọi tài khoản database.

### Hồ sơ minh họa

Đây là **mô tả thiết kế, không phải cấu hình chạy trực tiếp của một sản phẩm**. Không điền giá trị bí mật vào hồ sơ.

~~~yaml
onboarding:
  reference: database-a-runtime-example
  owner: application-a-operations
  environment: production

target:
  service_reference: database-a
  principal_reference: application-a-runtime
  authentication_authority: target-database
  cluster_mapping: requires-confirmed-topology

access:
  requester: application-a-workload
  purpose: runtime-data-access
  scope: application-a-required-data
  human_secret_read: not-granted-by-this-policy

dependencies:
  - application-a-api
  - application-a-background-worker

credential_lifecycle:
  delivery: approved-secret-retrieval
  rotation_method: supported-target-connector
  uncertain_result: stop-and-reconcile
  acceptance:
    - new-target-authentication-verified
    - required-application-operations-verified
    - old-credential-handling-verified

evidence:
  record_secret_value: false
  correlation:
    - onboarding-reference
    - principal-reference
    - credential-version
    - rotation-operation
~~~

Ý định trong hồ sơ phải được đối chiếu với quyền hiệu lực. Một policy không cấp đọc bí mật không chứng minh người dùng không được cấp quyền đó từ policy khác.

## 10. Tiếp nhận credential ban đầu và chạy thử

Nếu sử dụng credential hiện có, cần đưa vào vault qua kênh được chấp nhận và giảm việc tạo thêm bản sao.

Sau khi nhập, cần xác minh:

1. Đúng tài khoản, đúng đích và đúng môi trường.
2. Credential có thể được dùng theo đường dự kiến.
3. Phạm vi truy xuất trong vault đúng với chính sách.
4. Log không chứa giá trị bí mật.
5. Thao tác kiểm tra không tạo tác động ngoài kế hoạch.

Credential đã từng được chia sẻ rộng không trở thành bí mật chỉ có trong vault sau khi nhập. Kế hoạch cutover cần xử lý những bản sao và đường sử dụng cũ.

### Pilot theo mục tiêu

Nên có một phạm vi thử đủ đại diện cho rủi ro cần xác nhận:

- Đường truy cập tương tác nếu quản lý DBA.
- Tác vụ ứng dụng nếu quản lý tài khoản runtime.
- Rotation với cùng kiểu xác thực và phụ thuộc cần thiết.
- Hành vi khi thiếu quyền, đích không sẵn sàng hoặc kết quả chưa rõ.

Môi trường thử nghiệm cần phản ánh những đặc điểm quan trọng. Tuy nhiên, việc chạy tốt ở đó không thay thế kiểm tra cấu hình và phụ thuộc riêng của production.

## 11. Luân chuyển credential và xác minh ở đích

Rotation là một quá trình phối hợp, thường không có giao dịch nguyên tử giữa vault, database và ứng dụng.

Một mô hình khái niệm:

~~~text
Xác nhận trạng thái hiện tại và bên phụ thuộc
                  |
                  v
Chuẩn bị credential mới qua cơ chế được bảo vệ
                  |
                  v
Áp dụng thay đổi đúng nơi có thẩm quyền
                  |
                  v
Xác minh trạng thái xác thực ở đích
                  |
                  v
Chuyển hoặc nạp lại ở bên phụ thuộc
                  |
                  v
Xác minh tác vụ hợp lệ và xử lý credential cũ
~~~

Thứ tự chi tiết phải theo khả năng hệ thống. Có nơi hỗ trợ giai đoạn nhiều credential, có nơi chỉ chấp nhận một mật khẩu. Không sao chép trình tự minh họa thành thao tác mặc định trên mọi database.

### Những điểm phải phân biệt

- Đích đã đổi credential.
- Vault đã lưu đúng phiên bản.
- Ứng dụng đã nhận phiên bản mới.
- Kết nối mới xác thực thành công.
- Tác vụ được phép vẫn hoạt động.
- Credential cũ không còn hiệu lực theo mục tiêu.
- Phiên cũ đã được xử lý theo chính sách.

Đổi mật khẩu không bảo đảm mọi phiên đang chạy lập tức kết thúc. Cần kiểm tra hành vi của hệ quản trị và kế hoạch quản lý phiên.

### Xác minh phải vượt quá “đăng nhập được”

Một tài khoản có thể đăng nhập nhưng thiếu quyền cho job thực tế. Ngược lại, kết nối cũ có thể tiếp tục hoạt động khiến người vận hành tưởng phiên bản mới đã được dùng.

Bộ tiêu chí cần bao phủ xác thực mới và những tác vụ đại diện đã được chấp nhận. Cách thử phải phù hợp mức tác động; không dùng thao tác phá hủy dữ liệu production chỉ để kiểm tra quyền.

## 12. Xử lý lỗi và trạng thái chưa xác định

| Tình huống | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Mất kết nối sau yêu cầu đổi credential | Không biết đích đã đổi hay chưa | Ghi trạng thái chưa xác định, đối soát có kiểm soát |
| Đích đổi nhưng vault chưa ghi nhận | Bên lấy bí mật có thể nhận giá trị cũ | Bảo vệ trạng thái thao tác và xác minh phiên bản |
| Vault có giá trị mới nhưng đích chưa chấp nhận | Kết nối mới thất bại | Không báo hoàn tất trước khi xác minh |
| Một ứng dụng chưa nạp lại | Gián đoạn ở một phần dịch vụ | Dừng theo tiêu chí, xử lý bên phụ thuộc |
| Retry liên tục với credential sai | Có thể khóa tài khoản hoặc gây tải | Giới hạn retry, phân loại lỗi và cảnh báo |
| Failover đổi endpoint đang hoạt động | Connector thao tác sai node hoặc mất đích | Kiểm tra mapping cụm và trạng thái thực tế |
| Hai bộ điều phối cùng quản lý một principal | Credential cuối không khớp dự kiến | Có điều phối độc quyền và kiểm soát thao tác lặp |

Không nên xử lý mọi lỗi bằng cách thử đổi mật khẩu thêm lần nữa. Retry cần biết trạng thái, phạm vi và khả năng lặp an toàn của thao tác.

### Phương án khôi phục

Kế hoạch cần nêu rõ khi nào dừng, ai quyết định và cách đưa dịch vụ về trạng thái hoạt động được kiểm soát.

Tùy tình huống, có thể cần:

- Hoàn tất việc chuyển ứng dụng sang credential đã xác minh.
- Dùng quyền đối soát được bảo vệ để đưa đích và vault về trạng thái phù hợp.
- Khôi phục cấu hình tích hợp hoặc đường kết nối.
- Thực hiện một thay đổi credential mới đã được chấp nhận.

Không mặc định rollback luôn là đưa mật khẩu cũ trở lại. Nếu credential cũ bị nghi lộ, việc khôi phục nó có thể khôi phục cả đường truy cập của người không còn được phép.

Tài khoản hoặc đường phục hồi phải được chuẩn bị trước; không nên chỉ nằm sau đúng thành phần đang cần phục hồi.

## 13. Cutover và xử lý đường truy cập cũ

Cutover là chuyển các bên sử dụng sang mô hình được chấp nhận và xử lý phần còn sót.

Một kế hoạch có thể đi theo từng nhóm:

1. Xác nhận tiêu chí sẵn sàng và phạm vi đợt chuyển.
2. Chuyển người dùng hoặc workload sang đường mới.
3. Kiểm tra chức năng và bằng chứng.
4. Đổi hoặc thu hồi credential cũ theo cơ chế đích.
5. Xử lý cấu hình cũ, bản sao bí mật và quyền không còn cần.
6. Theo dõi một khoảng phù hợp với chu kỳ công việc.
7. Ghi ngoại lệ và quyết định nghiệm thu.

### Với người vận hành

Nếu chính sách yêu cầu phiên qua broker, cần xác định cách hạn chế đường trực tiếp ngoài chính sách và bảo vệ đường khẩn cấp đã được chấp nhận.

Không chỉ đổi biểu tượng công cụ DBA rồi coi mọi truy cập đã đi qua PAM. Cần kiểm tra danh tính, tuyến kết nối, credential và quyền ở đích.

### Với ứng dụng

Ứng dụng có thể tiếp tục kết nối trực tiếp nhưng nhận credential qua cơ chế mới. Cần kiểm tra cấu hình triển khai, quyền lấy bí mật, cache và cách xử lý khi vault tạm thời không sẵn sàng.

Không để một bản sao mật khẩu cũ trong cấu hình vẫn là đường dự phòng vô thời hạn mà không có quyết định rõ ràng.

### Đường quyền phát sinh

Một người dùng đặc quyền có thể tạo tài khoản hoặc grant mới trong thời gian được phép. Cần xét audit, kiểm kê thay đổi và thu hồi những khả năng phát sinh ngoài mục tiêu.

Chặn yêu cầu PAM mới không tự thu hồi mọi principal, credential hoặc phiên đã tạo trước đó.

## 14. Giám sát phiên và bằng chứng kiểm toán

Database có đặc điểm riêng: thao tác có thể đi qua công cụ đồ họa, giao thức quản trị, driver hoặc connection pool. Khả năng ghi nhận của PAM phụ thuộc đường truy cập và tích hợp.

Cần xác định chính xác đang có:

- Bằng chứng yêu cầu và quyết định cấp quyền.
- Sự kiện truy xuất hoặc sử dụng credential.
- Metadata phiên broker.
- Bản ghi phiên nếu giải pháp hỗ trợ.
- Audit của cơ sở dữ liệu.
- Sự kiện thay đổi quyền, credential và cấu hình.

Không mặc định có broker là đã thấy đầy đủ mọi câu lệnh hoặc tác động dữ liệu.

### Liên kết danh tính

Bằng chứng cần nối được:

~~~text
Danh tính ban đầu
      |
      v
Yêu cầu / quyết định trong PAM
      |
      v
Tài khoản đích và credential hoặc cơ chế xác thực
      |
      v
Phiên kết nối / tác vụ tại database
      |
      v
Kết quả và thay đổi liên quan
~~~

Nếu nhiều người dùng một tài khoản chung, chỉ log tên tài khoản database là chưa đủ phân biệt người thực hiện. Cần cơ chế liên kết phù hợp theo đường phiên.

Với ứng dụng dùng connection pool và tài khoản chung, không nên suy ra người dùng cuối chỉ từ tài khoản kết nối. Muốn truy vết đến người dùng nghiệp vụ cần cơ chế tương ứng ở lớp ứng dụng và bằng chứng liên kết.

### Bảo vệ bằng chứng

Log hoặc bản ghi phiên có thể chứa câu truy vấn, dữ liệu kết quả và thông tin nhạy cảm. Cần giới hạn người xem, việc xuất và vòng đời lưu giữ.

Không ghi mật khẩu, token hoặc khóa riêng vào bằng chứng. Dùng ID credential, phiên bản, mã thao tác và kết quả xác minh.

## 15. Tiêu chí nghiệm thu theo từng lớp

Một tài khoản chỉ nên được đánh dấu hoàn tất theo tiêu chí đã thỏa thuận, không theo cảm giác rằng “đã cất mật khẩu”.

| Lớp | Tiêu chí ví dụ |
| --- | --- |
| Định danh và sở hữu | Đúng principal, môi trường, chủ sở hữu và mục đích |
| Quyền | Phạm vi cần thiết được xác nhận, quyền dư có quyết định xử lý |
| Truy cập PAM | Danh tính đúng được sử dụng, danh tính ngoài phạm vi bị hạn chế |
| Chức năng database | Xác thực mới và tác vụ hợp lệ được xác minh |
| Vòng đời credential | Rotation và xử lý trạng thái lỗi được xác nhận |
| Phụ thuộc | Các bên thuộc phạm vi đã chuyển và được kiểm tra |
| Đường cũ | Credential, cấu hình và quyền cũ được xử lý hoặc có ngoại lệ |
| Bằng chứng | Liên kết được yêu cầu, tài khoản đích, thao tác và kết quả |
| Phục hồi | Có đường và trách nhiệm khôi phục phù hợp với kịch bản |
| Bàn giao | Người vận hành biết cách sử dụng và xử lý lỗi |

### Kiểm tra cho phép và giới hạn

Cần xác nhận cả khả năng cần giữ lẫn giới hạn mong muốn:

- Ứng dụng thực hiện được chức năng được giao.
- Tài khoản runtime không nhận quyền quản trị ngoài mục tiêu.
- Người được phép mở đúng phiên trong phạm vi.
- Người ngoài phạm vi không được lấy credential qua các đường đã kiểm tra.
- Rotation không làm mất chức năng hợp lệ và có bằng chứng phiên bản.
- Các khoảng trống chưa giải quyết được thể hiện rõ.

Có thể dùng đánh giá quyền, kiểm tra cấu hình hoặc môi trường phù hợp để xác minh giới hạn. Không cần thực hiện hành động gây hại để chứng minh nó bị cấm.

### Ngoại lệ

Nếu một job chưa chuyển được, cần ghi tài khoản, phạm vi, lý do, chủ sở hữu, rủi ro, biện pháp bù đắp và thời hạn xem xét.

Không tính ngoại lệ là đã hoàn tất kiểm soát chỉ vì đã có người chấp nhận rủi ro. Báo cáo phải cho thấy phần đã xác minh và phần còn tồn tại.

## 16. Ví dụ xuyên suốt: ứng dụng A trên production

### Hiện trạng

Ứng dụng A và nhóm DBA đang dùng chung một tài khoản quyền rộng. Credential nằm trong cấu hình ứng dụng và được một số người biết. Một job nền chạy theo lịch cũng dùng tài khoản đó.

Mục tiêu là tách nhu cầu, đưa credential vào quản lý và giữ dịch vụ hoạt động.

### Thiết kế chuyển đổi

1. Xác nhận tài khoản, nguồn xác thực, quyền và các endpoint.
2. Kiểm kê ứng dụng, worker và job đã biết.
3. Thiết kế tài khoản runtime có quyền phù hợp.
4. Thiết kế đường DBA có thể truy vết và giới hạn theo nhiệm vụ.
5. Tách nhu cầu migration nếu đang dùng chung.
6. Chuẩn bị bản ghi vault, chính sách và bộ rotation.
7. Chuyển từng bên phụ thuộc, kiểm tra kết nối mới và tác vụ hợp lệ.
8. Xử lý tài khoản chung cũ cùng credential và phiên liên quan.

Tài khoản dùng cho công việc bảo trì cần quyền khác runtime; không chỉ sao chép toàn bộ quyền cũ sang tất cả tài khoản mới.

### Tình huống phát sinh

Ứng dụng chính hoạt động sau thay đổi nhưng job nền thất bại ở lần chạy kế tiếp.

Phân tích cho thấy job chỉ đọc cấu hình khi khởi động và vẫn dùng giá trị cũ. Đây là thiếu sót trong chuyển đổi phụ thuộc, không phải bằng chứng rằng mọi tài khoản phải được trả lại quyền quản trị hoặc mật khẩu cũ.

Hướng xử lý là xác nhận credential hiện tại, cập nhật hoặc nạp lại job theo quy trình, kiểm tra tác vụ hợp lệ và bổ sung bằng chứng. Nếu cần biện pháp tạm thời để duy trì dịch vụ, phải ghi phạm vi và thời hạn cụ thể.

### Kết quả được chấp nhận

Có thể nghiệm thu khi:

- Runtime và người vận hành dùng đúng danh tính theo thiết kế.
- Các bên phụ thuộc trong phạm vi hoạt động với cơ chế mới.
- Quyền runtime đã được xác nhận phù hợp.
- Rotation và kết nối mới được xác minh.
- Tài khoản chung cũ được xử lý hoặc có trạng thái ngoại lệ rõ ràng.
- Có bằng chứng và người nhận bàn giao vận hành.

Nếu một phần chưa thỏa mãn, cần báo trạng thái tương ứng thay vì ghi toàn bộ database đã được kiểm soát đầy đủ.

## 17. Vận hành sau onboarding

Onboarding là bước chuyển sang quản lý thường xuyên.

Các sự kiện có thể cần xem xét lại:

- Thay đổi chủ sở hữu, đội vận hành hoặc ứng dụng.
- Thêm database, node, endpoint hoặc thay mô hình failover.
- Thay nguồn danh tính, chứng thư hoặc cách xác thực.
- Thêm job, pipeline hoặc bên phụ thuộc.
- Role hoặc quyền được mở rộng.
- Rotation thất bại hoặc credential bị nghi lộ.
- Nâng cấp connector, broker hoặc hệ quản trị.

### Theo dõi

Những chỉ số hữu ích gồm số tài khoản trong phạm vi đã nghiệm thu, tài khoản còn ngoại lệ, lỗi rotation, tuổi của lần xác minh gần nhất và số đường sử dụng chưa chuyển đổi.

Mẫu số phải rõ: số tài khoản được giao onboarding khác số database, số role hoặc số phiên. Không trộn các đơn vị để tạo tỷ lệ hoàn thành gây hiểu nhầm.

### Khôi phục từ backup

Bản sao vault cũ có thể chứa credential không còn khớp với database. Khôi phục cần đi kèm quản lý khóa, policy, mapping đích và đối soát trạng thái.

Không coi việc giải mã được backup là bằng chứng mọi tài khoản đã sẵn sàng sử dụng. Cũng cần xem đường khẩn cấp có hoạt động khi một số phụ thuộc PAM hoặc nguồn danh tính mất.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Nhập mật khẩu rồi báo hoàn tất | Chưa xác minh quyền, phụ thuộc và vòng đời | Nghiệm thu theo từng lớp kiểm soát |
| Dùng cùng tài khoản cho DBA và runtime | Khó truy vết, khó rotation và thu hồi | Tách principal theo nhu cầu |
| Chỉ kiểm tra đăng nhập | Có thể thiếu quyền tác vụ hoặc vẫn dùng kết nối cũ | Kiểm tra xác thực mới và chức năng cần thiết |
| Đổi credential không biết phụ thuộc | Job hoặc dịch vụ gián đoạn | Kiểm kê, chuyển đổi và xác minh từng bên |
| Giữ credential cũ làm dự phòng vô hạn | Đường truy cập ngoài PAM còn tồn tại | Quản lý ngoại lệ và xử lý vòng đời |
| Mọi connector dùng quản trị toàn cục | Phạm vi ảnh hưởng quá lớn | Giới hạn danh tính và quyền quản lý |
| Bỏ kiểm tra đích để hết lỗi kết nối | Có thể kết nối sai hoặc không đáng tin cậy | Sửa tuyến, endpoint và quan hệ tin cậy |
| Xem hết hạn PAM là phiên đã hết | Đặc quyền ở đích có thể tiếp tục | Kiểm tra credential, role và vòng đời phiên |
| Ghi credential trong log cutover | Tạo thêm nơi lộ bí mật | Dùng tham chiếu và kết quả xác minh |
| Phục hồi vault mà không đối soát đích | Kho và database có thể lệch phiên bản | Có quy trình xác minh sau khôi phục |

## 19. Bài tập tự đánh giá

Một nhóm đã nhập tài khoản quản trị database vào vault, cấu hình đổi mật khẩu định kỳ và yêu cầu DBA truy cập qua broker. Ứng dụng cùng hai job vẫn dùng tài khoản này. Nhóm kiểm tra bằng một phiên kết nối đã mở trước rotation rồi kết luận onboarding thành công.

Hãy trả lời:

1. Vì sao kết nối đang tồn tại chưa chứng minh credential mới dùng được?
2. Những nhu cầu nào nên được tách khỏi tài khoản quản trị chung?
3. Cần biết gì về ứng dụng và job trước lần rotation tiếp theo?
4. Broker có tự chứng minh đã giới hạn quyền SQL không?
5. Nếu credential cũ bị nghi lộ, phương án phục hồi phải xét điều gì?
6. Những bằng chứng nào còn thiếu để nghiệm thu?

### Gợi ý phân tích

**Kết nối:** phiên hoặc pool có thể tiếp tục hoạt động theo cơ chế của đích. Cần kiểm tra kết nối mới cùng đúng phiên bản và tác vụ hợp lệ.

**Phân tách:** runtime, job, migration và DBA có thể có nhu cầu khác nhau. Không mặc định tất cả cần quyền quản trị rộng.

**Phụ thuộc:** cần biết cách lấy bí mật, cache, nạp lại, lịch chạy, retry và người chịu trách nhiệm kiểm tra.

**Broker:** kiểm soát đường phiên không tự thay thế quyền trên database. Khả năng giám sát và giới hạn cần được xác nhận theo giao thức và tích hợp.

**Phục hồi:** phải tránh khôi phục một credential bị nghi lộ thành đường hoạt động bình thường. Cần xét đích, bên phụ thuộc, phiên và bằng chứng sự cố.

**Nghiệm thu:** còn thiếu xác nhận principal, quyền, chuyển đổi phụ thuộc, kết nối mới, xử lý đường cũ, rotation, audit và khả năng phục hồi.

## 20. Những điểm cần ghi nhớ

- Onboard database là đưa các tài khoản và đường đặc quyền vào vòng quản lý đã xác minh, không chỉ lưu mật khẩu.
- Mô hình principal, nguồn xác thực, cụm và phạm vi quyền phải được xác định theo hệ thống đích.
- Tách tài khoản theo nhiệm vụ giúp thực hiện least privilege, truy vết và luân chuyển.
- Tài khoản dịch vụ cần kế hoạch phụ thuộc, cache, pool và kiểm tra kết nối mới.
- Rotation phải xử lý trạng thái chưa rõ; thành công ở một thành phần chưa chứng minh toàn bộ chuyển đổi đã hoàn tất.
- Quyền trong PAM, credential, role và phiên tại database có vòng đời khác nhau.
- Chỉ nghiệm thu phần đã đáp ứng tiêu chí; ngoại lệ, đường cũ và khoảng trống phải có chủ sở hữu cùng bằng chứng.
