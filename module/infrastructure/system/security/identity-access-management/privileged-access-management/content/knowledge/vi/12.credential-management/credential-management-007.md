# Credential dependency trong quản lý credential đặc quyền

## 1. Credential dependency là gì?

**Credential dependency** là quan hệ phụ thuộc liên quan tới việc cấp, lưu trữ, phân phối, sử dụng, thay đổi hoặc thu hồi một credential.

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), một credential hiếm khi tồn tại độc lập. Mật khẩu của tài khoản dịch vụ có thể được ba instance ứng dụng sử dụng, được một công cụ triển khai đưa vào cấu hình, được vault lưu theo phiên bản và được một connector thay tại hệ thống đích.

Ví dụ:

~~~text
Tài khoản cơ sở dữ liệu
  → có credential đang được đích chấp nhận.

Ứng dụng, job đối soát và công cụ backup
  → cần credential đó để làm việc.

Vault và pipeline triển khai
  → tham gia lưu hoặc phân phối credential.

Connector rotation
  → cần quyền và đường kết nối để thay credential.
~~~

Nếu chỉ đổi mật khẩu rồi xác nhận đăng nhập từ một máy kiểm tra, tổ chức có thể bỏ sót các consumer khác. Một job chạy vào cuối tháng hoặc một môi trường dự phòng có thể chỉ phát hiện lỗi rất lâu sau lần thay đổi.

Mục tiêu quản lý dependency là biết **ai phụ thuộc vào credential nào, qua cơ chế nào, tại thời điểm nào và bằng chứng nào xác nhận trạng thái đó**. Đây là nền tảng cho rotation, thu hồi, least privilege, phục hồi và kiểm toán.

## 2. Phân biệt tài khoản, credential, phiên bản và consumer

| Đối tượng | Ý nghĩa | Ví dụ logic |
|---|---|---|
| Danh tính hoặc tài khoản | Chủ thể được hệ thống đích nhận diện | Tài khoản dịch vụ thanh toán |
| Credential | Phương tiện chứng minh danh tính | Mật khẩu, khóa hoặc token |
| Phiên bản credential | Một lần phát hành hoặc thay đổi cụ thể | Credential version 12 |
| Đối tượng quản lý trong vault | Bản ghi lưu hoặc tham chiếu credential | Secret object của dịch vụ |
| Secret reference | Cách consumer tìm đối tượng hoặc phiên bản | Tham chiếu tới secret đang được quản lý |
| Consumer | Thành phần dùng credential hoặc reference | Instance, job, agent hoặc công cụ backup |
| Nguồn xác thực | Nơi quyết định credential có được chấp nhận | Directory, cơ sở dữ liệu hoặc issuer |
| Bộ phân phối | Thành phần đưa credential tới consumer | Agent, broker, pipeline hoặc cơ chế mount |
| Tác vụ vòng đời | Thành phần tạo, đổi, kiểm tra hoặc thu hồi | Rotation connector hoặc revoke job |

Một tài khoản có thể có nhiều credential. Một credential có thể được nhiều consumer dùng. Một consumer cũng có thể cần nhiều credential để hoàn thành công việc.

Không đồng nhất số secret object với số credential độc lập. Hai đối tượng vault có thể cùng đại diện một tài khoản tập trung hoặc chứa bản sao của cùng một credential nền.

Cũng cần tách **reference đã cập nhật** khỏi **credential tiến trình đang dùng**. Consumer có thể đọc reference một lần khi khởi động, giữ bản sao trong bộ nhớ hoặc tiếp tục dùng kết nối đã xác thực từ trước.

## 3. Các loại dependency cần quản lý

### 3.1. Dependency sử dụng

Consumer cần credential để xác thực tới một tài nguyên. Đây là quan hệ trực tiếp dễ thấy nhất.

Ví dụ, một worker dùng tài khoản cơ sở dữ liệu để ghi kết quả xử lý.

### 3.2. Dependency lấy và phân phối credential

Consumer cần một danh tính khác để gọi vault, broker hoặc agent. Pipeline có thể cần quyền đọc secret để đưa vào một môi trường chạy.

Nếu danh tính lấy secret bị lỗi, credential tại đích có thể vẫn đúng nhưng ứng dụng không lấy được. Đây là lỗi khác với đích từ chối mật khẩu.

### 3.3. Dependency thay đổi và phục hồi

Connector cần quyền đổi credential hoặc một tài khoản reconcile để phục hồi khi mất đồng bộ.

Credential của connector, tài khoản reconcile và đường kết nối cũng cần owner, vòng đời cùng giới hạn quyền. Chúng không nằm ngoài PAM chỉ vì phục vụ hệ thống quản lý credential.

### 3.4. Dependency cấu hình và trạng thái mong muốn

Một công cụ triển khai hoặc controller có thể duy trì cấu hình chứa secret reference. Nếu nguồn này còn giữ reference cũ, lần triển khai sau có thể đưa consumer trở lại trạng thái lỗi.

Cấu hình đang chạy đúng chưa chứng minh cấu hình mong muốn đã đúng.

### 3.5. Dependency trust và phiên

Consumer có thể cần trust chain, host key hoặc thông tin xác minh máy chủ để kết nối an toàn. Đây là dependency liên quan, nhưng không phải mọi đối tượng trust đều là credential đăng nhập.

Phiên hoặc connection pool lại có vòng đời khác: chúng có thể tiếp tục hoạt động sau khi credential đã đổi. Dependency phiên cần được ghi rõ để đánh giá thu hồi và kiểm tra sau rotation.

| Loại quan hệ | Câu hỏi cần trả lời |
|---|---|
| Sử dụng credential | Thành phần nào xác thực bằng credential này? |
| Đọc secret reference | Consumer lấy thông tin từ đâu? |
| Cache phiên bản | Tiến trình đang giữ bản nào và đến khi nào? |
| Phân phối | Thành phần nào cập nhật cho consumer? |
| Rotation hoặc reconcile | Ai có quyền thay credential tại nguồn? |
| Quản lý cấu hình | Nguồn nào có thể ghi đè reference hoặc bản sao? |
| Trust | Consumer xác minh đích dựa vào đâu? |
| Phiên | Xác thực cũ có thể tiếp tục tồn tại bao lâu? |

## 4. Biểu diễn dependency bằng đồ thị

Một đồ thị có thể dùng các node cho tài khoản, credential, reference, consumer và thành phần quản lý; các cạnh có loại quan hệ rõ.

~~~mermaid
flowchart LR
    A["Ứng dụng production"] -->|Đọc reference| R["Secret reference"]
    J["Job đối soát"] -->|Đọc hoặc nhận credential| R
    B["Công cụ backup"] -->|Có bản sao theo cơ chế riêng| V["Phiên bản credential"]
    R -->|Trỏ tới| V
    V -->|Được chấp nhận cho| I["Tài khoản tại nguồn xác thực"]
    A -->|Xác thực để làm việc| T["Tài nguyên đích"]
    J -->|Xác thực để làm việc| T
    C["Connector rotation"] -->|Thay tại nguồn| I
    C -->|Cập nhật đối tượng quản lý| R
    P["Pipeline triển khai"] -->|Duy trì cấu hình lấy secret| A
    O["Owner dịch vụ"] -.->|Chịu trách nhiệm| A
    O -.->|Chịu trách nhiệm| J
~~~

Chiều mũi tên biểu diễn quan hệ được ghi nhãn, không phải thứ tự rotation. Muốn lập kế hoạch thay đổi cần hiểu cơ chế của từng cạnh, không chỉ chạy theo chiều hình vẽ.

### 4.1. Định danh ổn định

Nên dùng định danh có nguồn quản lý cho tài khoản, credential object, workload và target. Tên hiển thị, IP hoặc đường dẫn có thể đổi hoặc được cấp lại.

Với tài khoản tập trung phục vụ nhiều đích, cần giữ liên kết tới nguồn danh tính thật sự. Không mô hình hóa thành nhiều mật khẩu local độc lập chỉ vì có nhiều endpoint.

### 4.2. Phân biệt dependency đã xác nhận và mới nghi ngờ

Một chuỗi cấu hình có tên tài khoản là bằng chứng gợi ý, chưa chắc là consumer đang sử dụng.

Ngược lại, không có đăng nhập gần đây chưa chứng minh consumer đã hết nhu cầu. Nó có thể là job ít chạy hoặc môi trường dự phòng.

Mỗi quan hệ nên có trạng thái bằng chứng, phạm vi quan sát và thời điểm xác minh thay vì một nhãn “đã biết” vĩnh viễn.

### 4.3. Không lưu secret để nhận diện quan hệ

Dùng credential ID, version ID và tham chiếu có kiểm soát. Không dùng giá trị mật khẩu làm khóa của đồ thị hoặc nhãn metric.

Cũng không xuất hash đơn giản của mật khẩu vào danh mục để so sánh bản sao. Với secret có không gian đoán nhỏ, dữ liệu đó có thể hỗ trợ tấn công ngoại tuyến. Việc đối chiếu vật liệu secret, nếu thật sự cần, phải dùng cơ chế được thiết kế và bảo vệ phù hợp.

## 5. Hồ sơ dependency tối thiểu

Một cấu trúc logic minh họa:

~~~yaml
credential_dependency:
  credential_id: credential-payment-database
  account_source_id: database-identity-source
  account_id: payment-service-account
  target_scope: approved-payment-database-scope
  owner_team: payment-platform

  consumers:
    - consumer_id: payment-api-production
      dependency_type: runtime-authentication
      acquisition_mode: managed-secret-reference
      refresh_behavior: startup-read
      update_method: coordinated-instance-replacement
      evidence_state: confirmed-for-recorded-scope
      verification_reference: verification-042

    - consumer_id: monthly-reconciliation-job
      dependency_type: scheduled-authentication
      acquisition_mode: deployment-injected-reference
      refresh_behavior: read-at-job-start
      evidence_state: requires-scheduled-path-validation

  lifecycle:
    rotation_owner: pam-operations
    consumer_change_owner: payment-platform
    recovery_reference: recovery-plan-017
    completeness_state: bounded-by-recorded-discovery-scope
~~~

Đây không phải cấu hình của sản phẩm cụ thể. Những giá trị như refresh_behavior hoặc update_method chỉ là mô tả đã được xác minh trong tình huống, không tự tạo ra khả năng tương ứng cho ứng dụng.

Hồ sơ thực tế cần bổ sung:

- Môi trường và các instance hoặc nhóm triển khai liên quan.
- Điểm lấy secret và quyền của danh tính lấy secret.
- Phiên bản hoặc bằng chứng quan sát phiên bản.
- Cache, connection pool và cách tạo xác thực mới.
- Lịch hoạt động, kể cả consumer ít chạy.
- Phụ thuộc dự phòng hoặc khôi phục.
- Tiêu chí thành công, điều kiện dừng và trách nhiệm xử lý lỗi.
- Thời điểm xác minh từng quan hệ.

Không dùng unknown bằng một giá trị như cache_ttl=0. Không biết thời gian cache khác hoàn toàn với đã xác minh rằng không cache.

## 6. Phát hiện và xác minh dependency

### 6.1. Kết hợp nhiều loại bằng chứng

Có thể xem xét những nguồn phù hợp với phạm vi được phép trong một hoạt động triển khai thực tế:

| Nguồn bằng chứng | Có thể cho biết | Giới hạn |
|---|---|---|
| Danh mục dịch vụ và owner | Nhu cầu, trách nhiệm, môi trường | Có thể chưa cập nhật |
| Cấu hình và template triển khai | Reference hoặc bản sao được phân phối | Chưa chứng minh tiến trình hiện tại đang dùng |
| Cấu hình job theo lịch | Consumer ít chạy | Có thể tồn tại job không còn hoạt động |
| Log truy cập vault hoặc broker | Ai đã lấy secret | Một lần lấy có thể phục vụ nhiều lần dùng |
| Log xác thực tại đích | Chủ thể, nguồn và thời điểm dùng | Tài khoản dùng chung có thể khó phân biệt consumer |
| Agent hoặc trạng thái runtime | Phiên bản và cách refresh theo khả năng | Phạm vi quan sát có thể không đầy đủ |
| Hồ sơ backup và phục hồi | Consumer hoặc bản sao dự phòng | Không phải lúc nào cũng đang chạy để quan sát |

Không cần thu thập giá trị secret để chứng minh mọi quan hệ. Cần ưu tiên metadata và tham chiếu có thể liên kết.

### 6.2. Xác minh với owner và đường chạy thật

Cần làm rõ consumer có cần credential ở lúc khởi động, từng request, khi mở kết nối mới hay khi thực hiện một loại job.

Một dịch vụ đang khỏe có thể chỉ đang dùng connection pool cũ. Cần chọn cách kiểm tra xác thực mới phù hợp, không gây gián đoạn ngoài phạm vi.

### 6.3. Ghi phạm vi discovery

Một báo cáo nên nói đã quan sát những môi trường, nhóm workload, khoảng thời gian và loại đường chạy nào.

“Không tìm thấy consumer khác trong phạm vi đã kiểm tra” là tuyên bố khác với “không còn consumer khác ở bất kỳ đâu”.

Nếu còn vùng chưa xác minh, cần ghi owner, ảnh hưởng và cách xử lý. Không xóa phần chưa biết để làm tỷ lệ hoàn thành đẹp hơn.

## 7. Đánh giá ảnh hưởng và least privilege

### 7.1. Blast radius không chỉ là số consumer

Ảnh hưởng phụ thuộc:

- Quyền hiệu lực của tài khoản.
- Giá trị và độ nhạy cảm của tài nguyên.
- Số môi trường hoặc đích dùng chung credential.
- Khả năng chuyển sang quyền khác hoặc tạo thay đổi bền vững.
- Thời gian credential còn hiệu lực.
- Những bên có thể đọc hoặc phân phối secret.
- Khả năng thu hồi mà không làm mất dịch vụ thiết yếu.
- Chất lượng bằng chứng và phần chưa biết.

Một credential chỉ có một consumer nhưng có quyền quản trị toàn bộ hạ tầng vẫn có ảnh hưởng lớn.

### 7.2. Dependency cho thấy cơ hội giảm chia sẻ

Nếu nhiều chức năng không liên quan cùng dùng một tài khoản, có thể cần đánh giá tách danh tính hoặc role theo nhu cầu.

Mục tiêu là giảm ảnh hưởng khi lộ credential hoặc khi một consumer lỗi. Việc tách phải đi cùng quản lý owner, quyền và vòng đời; tạo thêm tài khoản mà không quản lý có thể chỉ chuyển khó khăn sang nơi khác.

### 7.3. Tách quyền sử dụng khỏi quyền quản lý

Consumer cần xác thực tới đích không nhất thiết cần quyền đổi credential hoặc đọc secret của consumer khác.

Người xử lý dependency có thể cần quyền JIT cho một tác vụ bảo trì, nhưng không cần giữ quyền quản trị rộng thường trực. Giới hạn JEA phải được thực thi bởi role, endpoint hoặc cơ chế phù hợp tại lớp liên quan.

## 8. Chuỗi phụ thuộc và vòng bootstrap

### 8.1. Một consumer có thể cần nhiều bước xác thực

~~~text
Workload cần credential cơ sở dữ liệu.
  → phải gọi broker.
  → broker phải xác minh danh tính workload.
  → broker hoặc vault phải dùng được khóa và policy cần thiết.
  → connector có thể cần danh tính khác để tạo credential tại đích.
~~~

Nếu chỉ lập bản đồ consumer tới mật khẩu cuối cùng, tổ chức có thể bỏ sót các điều kiện để lấy hoặc phục hồi credential.

### 8.2. Vòng phụ thuộc có thể làm mất khả năng phục hồi

Ví dụ logic:

~~~text
Vault cần một tài khoản directory để thực hiện một chức năng.
Credential của tài khoản đó chỉ có trong vault.
Đường lấy credential phục hồi lại cần chức năng directory đang lỗi.
~~~

Không phải mọi mũi tên tạo vòng đều là lỗi giống nhau. Cần phân biệt đường sử dụng thường ngày, quản trị, khởi động và phục hồi.

Nhưng nếu một vòng không có điểm bắt đầu khả dụng trong tình huống cần khôi phục, hệ thống có thể không tự phục hồi được.

### 8.3. Thiết kế điểm khởi đầu và đường phục hồi

Có thể cần cơ chế danh tính workload từ nền tảng, credential bootstrap có giới hạn hoặc quy trình khẩn cấp độc lập theo kiến trúc.

Cần xác định:

- Bằng chứng danh tính ban đầu đến từ đâu.
- Vật liệu hoặc quyền nào cần trước khi vault hoạt động.
- Ai có quyền tiếp cận trong tình huống khẩn cấp.
- Điểm hỏng nào mà đường phục hồi phải độc lập.
- Cách quản lý vòng đời sau sử dụng.

Không xử lý vòng bootstrap bằng cách đặt một mật khẩu quản trị rộng, không có owner và không rotation vào cấu hình cố định.

### 8.4. Đồ thị giúp phát hiện nhưng không tự quyết định thứ tự

Phân tích chu trình hoặc các nhóm quan hệ liên thông có thể giúp tìm điểm cần điều tra. Tuy nhiên, không thể dùng một phép sắp xếp đồ thị đơn giản làm runbook cho mọi trường hợp.

Loại cạnh, khả năng dùng đồng thời credential, trạng thái phiên và hành vi consumer quyết định bước thực thi. Một dependency trust có thể cần thứ tự khác dependency mật khẩu.

## 9. Chuẩn bị thay đổi dựa trên dependency

Trước khi rotation hoặc thu hồi, cần có một kế hoạch đủ cụ thể:

1. Xác định credential và nguồn xác thực thật sự.
2. Liệt kê consumer đã xác nhận cùng vùng chưa xác minh.
3. Kiểm tra quyền, owner và actor có thể ghi cùng đối tượng.
4. Xác định khả năng của đích: nhiều credential đồng thời hay chỉ một.
5. Xác định cách refresh, thay thế hoặc tái kết nối từng consumer.
6. Chuẩn bị đường phục hồi phù hợp.
7. Chọn tiêu chí kiểm tra xác thực mới và tác vụ đại diện.
8. Xác định điều kiện ngừng, reconcile hoặc chuyển phương án.
9. Gắn công việc cập nhật consumer với người chịu trách nhiệm.
10. Chuẩn bị bằng chứng theo từng bước.

Một kế hoạch “đổi secret rồi báo các đội cập nhật” chưa đủ khi thứ tự có thể làm dịch vụ ngừng hoạt động.

### 9.1. Kiểm soát actor ghi đồng thời

Các actor có thể gồm scheduler rotation, pipeline, controller, người quản trị và cơ chế refresh tự động.

Cần kiểm soát theo đúng phạm vi credential hoặc tài khoản liên quan. Nếu một scheduler vẫn chạy trong lúc đội khác cập nhật consumer, credential có thể bị đổi thêm lần nữa.

Không tạm dừng toàn bộ quản lý credential ngoài phạm vi chỉ để đơn giản hóa một thay đổi. Nếu dừng tác vụ có liên quan tới thu hồi quyền hoặc lease, cần giữ trách nhiệm theo dõi phần đó.

### 9.2. Baseline phải có thời điểm

Baseline có thể ghi reference, phiên bản và trạng thái quan sát của các consumer mà không chứa secret rõ.

Trước khi thực thi, kiểm tra có thay đổi nào làm baseline không còn đúng. Một bản đồ được xác nhận nhiều tháng trước chưa tự đủ cơ sở cho lần rotation hiện tại.

## 10. Rotation khi đích hỗ trợ nhiều credential đồng thời

### 10.1. Điều kiện phải được xác minh

Khả năng dùng song song có thể đến từ nhiều khóa, nhiều token hoặc cơ chế khác của nền tảng. Không mặc định mọi tài khoản hỗ trợ hai mật khẩu cùng lúc.

Cần biết:

- Credential mới đại diện cùng tài khoản hay tài khoản khác.
- Quyền của credential mới có đúng phạm vi không.
- Có giới hạn số credential hoặc thời gian chồng lấn không.
- Cách nhận diện consumer đã chuyển.
- Cách thu hồi credential cũ.
- Cách xử lý phiên đã được credential cũ tạo ra.

### 10.2. Luồng chuyển đổi tham chiếu

~~~text
Chuẩn bị credential mới
  → kích hoạt và xác minh tại đúng nguồn
  → lưu hoặc công bố qua cơ chế phân phối được phép
  → chuyển từng consumer
  → kiểm tra xác thực mới và chức năng đại diện
  → xử lý consumer ít chạy và dự phòng
  → thu hồi credential cũ theo điều kiện
  → xác minh trạng thái cuối.
~~~

Đây là thứ tự logic cho một mô hình có thể chồng lấn. Trình tự cụ thể còn phụ thuộc cơ chế phát hành và phân phối.

### 10.3. Giới hạn khoảng chồng lấn

Giữ credential cũ vô thời hạn để tránh lỗi làm mất ý nghĩa của rotation.

Cần có mốc, owner, điều kiện chuyển cấp và cách xử lý consumer chưa cập nhật. Nếu phải kéo dài, quyết định cần thể hiện rủi ro còn lại và phạm vi được cho phép.

### 10.4. Tách tài khoản không phải lúc nào cũng tương đương thêm credential

Một phương án tạo tài khoản mới để chuyển đổi có thể thay đổi owner, quyền, quota, hành vi ứng dụng hoặc chính sách tại đích.

Cần xác minh đầy đủ rồi xử lý tài khoản cũ. Không coi việc tạo một tài khoản thứ hai tự động giải quyết mọi dependency.

## 11. Rotation khi đích chỉ hỗ trợ một credential

### 11.1. Có một khoảng chuyển tiếp cần được thiết kế

Nếu thay mật khẩu tại đích làm mật khẩu cũ mất hiệu lực ngay cho lần xác thực mới, vault và consumer có thể chưa cập nhật đồng thời.

Không có một thứ tự đơn giản luôn bảo đảm không gián đoạn:

~~~text
Đổi đích trước:
  Consumer còn giữ credential cũ có thể lỗi.

Cập nhật consumer trước:
  Credential mới có thể chưa được đích chấp nhận.
~~~

Cần phương án phối hợp theo khả năng ứng dụng, như giới hạn việc nhận tác vụ mới, cập nhật theo cửa sổ thay đổi, refresh có điều khiển hoặc chuyển sang một mô hình xác thực khác đã được kiểm chứng.

Không tuyên bố zero downtime nếu chưa có cơ chế và bằng chứng phù hợp.

### 11.2. Trình tự có checkpoint

Một mô hình có thể gồm:

1. Chuẩn bị và xác minh dữ liệu phạm vi.
2. Giữ trạng thái vận hành phù hợp cho consumer.
3. Áp dụng thay đổi tại nguồn xác thực.
4. Cập nhật đối tượng quản lý và reference theo thiết kế.
5. Thực hiện refresh hoặc chuyển consumer.
6. Kiểm tra kết nối mới.
7. Kiểm tra tác vụ đại diện.
8. Xác minh các consumer còn lại và cấu hình mong muốn.
9. Khôi phục nhịp vận hành theo tiêu chí.

Mỗi bước cần ghi điều gì đã xác minh và điều gì có thể vẫn đang chạy. Các thao tác không phải một giao dịch nguyên tử xuyên hệ thống.

### 11.3. Không để kết nối cũ che lỗi

Trong lúc chuyển đổi, các kết nối đã xác thực có thể tiếp tục xử lý bình thường. Dashboard sức khỏe có thể vẫn xanh trong khi mọi kết nối mới đều thất bại.

Tiêu chí cần có xác thực mới hoặc bằng chứng tương đương theo nền tảng, cùng cách quan sát ở từng nhóm consumer.

Không khởi động lại hàng loạt chỉ để tạo kết nối mới nếu việc đó làm tăng ảnh hưởng ngoài kế hoạch.

## 12. Refresh, cache và vòng đời kết nối

### 12.1. Các mô hình cập nhật khác nhau

| Hành vi consumer | Ảnh hưởng khi credential đổi | Điều cần kiểm tra |
|---|---|---|
| Đọc một lần khi khởi động | Tiến trình có thể giữ bản cũ | Cách thay thế hoặc khởi động lại có phối hợp |
| Refresh theo lịch | Có khoảng trễ cập nhật | Giới hạn thời gian và xử lý refresh lỗi |
| Đọc khi mở kết nối mới | Kết nối mới có thể nhận bản mới | Cơ chế cache bên dưới và quyền đọc |
| Agent phân phối | Phụ thuộc agent và đường cập nhật | Phiên bản đã bàn giao và consumer đã dùng |
| Mount hoặc tệp được cập nhật | Nội dung có thể đổi nhưng ứng dụng chưa đọc lại | Hành vi reload thật sự |
| Token hoặc credential động | Có vòng đời từng lần cấp | TTL tại đích, renew, revoke và phiên |

Không suy ra refresh đã xảy ra chỉ vì secret object hoặc nội dung tệp đã đổi.

### 12.2. Cache có thể nằm ở nhiều lớp

Một lượt cập nhật có thể đi qua vault, agent, thư viện, ứng dụng và connection pool.

Cần biết lớp nào lưu dữ liệu gì, giới hạn và cách làm mất hiệu lực. Một cache TTL ở agent chưa chứng minh ứng dụng không giữ credential lâu hơn.

Nếu dữ liệu không biết, ghi unknown và xác minh. Không lấy cấu hình mong muốn thay cho bằng chứng hành vi.

### 12.3. Job ít chạy cần kế hoạch riêng

Một job hàng tháng có thể chưa có cơ hội xác thực bằng credential mới trong thời gian theo dõi thông thường.

Có thể cần một đường kiểm tra được phép đại diện cho lúc chạy, hoặc giữ công việc xác minh theo lịch với owner và biện pháp kiểm soát rõ. Không tự chạy đầy đủ một tác vụ nghiệp vụ có tác động chỉ để thử mật khẩu.

### 12.4. Môi trường dự phòng vẫn là dependency

Một site dự phòng, pipeline phục hồi hoặc bản cấu hình khởi động lạnh có thể chứa reference hoặc bản sao cũ.

Nếu không cập nhật, sự cố chỉ xuất hiện khi chuyển dự phòng, đúng lúc khả năng xử lý đã hạn chế. Kế hoạch phải chỉ rõ những đường này có được kiểm tra không.

## 13. Theo dõi trạng thái theo từng consumer

### 13.1. Không dùng một trạng thái tổng để che khác biệt

Có thể theo dõi các mốc:

~~~text
Quan hệ được phát hiện.
Owner và nhu cầu được xác nhận.
Cách cập nhật được xác minh.
Reference hoặc dữ liệu phân phối đã cập nhật.
Tiến trình đã nhận hoặc refresh.
Xác thực mới đã được kiểm tra.
Tác vụ đại diện đạt tiêu chí.
Phần truy cập cũ đã được xử lý trong phạm vi.
~~~

Các mốc là những bằng chứng khác nhau. Một số mô hình không cần tất cả các bước hoặc có thứ tự khác, nhưng không nên gộp chúng thành một ô “updated”.

### 13.2. Phân biệt phiên bản mong muốn và quan sát được

Ví dụ:

~~~text
Consumer: payment-worker-group
Desired reference: managed-secret-current
Observed delivery version: version-13
Observed new-authentication evidence: pending
Existing connections: still-active
~~~

Bản ghi này chưa đủ để nói consumer đã dùng credential mới thành công. Nó cho biết phần nào cần xác minh tiếp.

### 13.3. Tổng hợp phải giữ phạm vi

“Đã xác minh mọi consumer trong danh sách” chưa chứng minh discovery đã tìm đủ mọi consumer.

Báo cáo nên tách:

- Tiến độ của tập quan hệ đã biết.
- Chất lượng và độ mới của bằng chứng.
- Vùng chưa được kiểm tra.
- Ngoại lệ hoặc dependency chưa có owner.

Không dùng một tỷ lệ duy nhất để thay thế cả bốn nhóm thông tin.

## 14. Lỗi từng phần, timeout và phục hồi

### 14.1. Phân loại lỗi theo lớp

| Quan sát | Nguyên nhân có thể cần kiểm tra |
|---|---|
| Không gọi được vault | Mạng, trust, danh tính lấy secret hoặc quyền API |
| Vault trả được dữ liệu nhưng đích từ chối | Sai phiên bản, sai tài khoản, nguồn xác thực hoặc trạng thái đích |
| Một instance thành công, instance khác lỗi | Cache, cấu hình, phiên bản hoặc môi trường khác nhau |
| Ứng dụng đang chạy nhưng restart lỗi | Kết nối cũ che lỗi bootstrap hoặc credential mới |
| Job theo lịch thất bại sau rotation nhiều ngày | Dependency ít chạy hoặc bản sao chưa cập nhật |
| Cấu hình đúng rồi lại sai sau deploy | Nguồn cấu hình mong muốn hoặc controller ghi đè |

Không reset credential chỉ từ một lỗi kết nối chưa được phân loại. Lỗi xác minh máy chủ không nên được “khắc phục” bằng bỏ kiểm tra trust.

### 14.2. Timeout không chứng minh chưa thay đổi

Nguồn xác thực có thể đã áp dụng credential mới nhưng connector chưa nhận phản hồi. Vault hoặc consumer có thể đang ở các phiên bản khác nhau.

Cần dừng retry thiếu kiểm soát, giữ request reference và đối soát trước khi thực hiện thay đổi tiếp.

Trạng thái unknown là dữ liệu vận hành cần xử lý, không phải một giá trị để tự động đổi thành success.

### 14.3. Chọn rollback hoặc roll forward theo trạng thái

Nếu đích và vault đã đúng, consumer chưa cập nhật, hoàn tất chuyển consumer có thể phù hợp hơn đặt lại credential cũ.

Nếu credential cũ nghi lộ, tái sử dụng nó để phục hồi có thể khôi phục cả đường xâm nhập.

Phương án cần xét consumer đã chuyển, khả năng dùng song song, nguồn cấu hình mong muốn và đường phục hồi. Khôi phục snapshot vault cũ không tự rollback credential tại đích.

### 14.4. Kết thúc phục hồi

Cần xác minh credential hợp lệ, consumer hoạt động theo tiêu chí, quyền đúng, tác vụ không còn ghi chồng và cấu hình không đưa bản cũ trở lại.

Nếu còn consumer chưa xác minh, giữ owner và trạng thái xử lý. Không đóng chỉ vì một endpoint đã hoạt động lại.

## 15. Dependency trong thu hồi và ứng phó sự cố

### 15.1. Dependency quyết định phạm vi xử lý

Khi một credential nghi lộ, cần biết những đích và consumer nào có thể bị ảnh hưởng. Phạm vi không chỉ gồm nơi secret được lưu mà còn gồm nơi nó có thể được dùng.

Một tài khoản dùng chung cho ứng dụng, backup và quản trị tương tác làm việc thu hồi khó hơn. Bản đồ dependency giúp chọn biện pháp và phối hợp dịch vụ, nhưng không nên trở thành lý do để giữ credential nghi lộ hoạt động không có giới hạn.

### 15.2. Tách các lớp hành động

| Lớp | Ví dụ xử lý | Giới hạn cần kiểm tra |
|---|---|---|
| Danh tính lấy secret | Chặn workload hoặc principal gọi vault | Bản sao đã lấy có thể còn dùng |
| Policy phân phối | Ngừng cấp mới hoặc renew | Không tự thay credential tại đích |
| Credential tại nguồn | Rotation, vô hiệu hóa hoặc thu hồi | Khả năng thực thi phụ thuộc loại credential |
| Consumer | Chuyển sang danh tính hoặc credential phù hợp | Có thể cần refresh hoặc thay kết nối |
| Grant | Gỡ role hoặc quyền tạm | Quyền gián tiếp có thể còn |
| Phiên | Kết thúc kết nối liên quan | Có thể có phiên ngoài đường quan sát |
| Thay đổi bền vững | Kiểm tra tài khoản, khóa hoặc cấu hình phát sinh | Thu hồi ban đầu không tự đảo ngược mọi hoạt động |

Cần liên kết các hành động với định danh và thời điểm. Một cờ revoked trên vault chưa chứng minh đích đã ngừng chấp nhận credential.

### 15.3. Xử lý consumer không rõ hoặc ngoài kiểm soát

Nếu không biết ai giữ bản sao, cần đánh giá dựa trên phạm vi credential có thể sử dụng và bằng chứng hiện có.

Có thể cần thu hẹp quyền, thay credential, hạn chế đường truy cập hoặc chuyển sang cơ chế khác theo quyết định xử lý. Những thay đổi này phải xét ảnh hưởng dịch vụ và khả năng phục hồi.

Không biến trạng thái “chưa biết consumer nào còn dùng” thành kết luận “credential không thể thu hồi”. Đó là một phần rủi ro và công việc cần được quản trị.

### 15.4. Bản đồ phải được cập nhật sau sự cố

Consumer bị loại bỏ, đường cấp bị chặn hoặc credential được tách thành nhiều danh tính cần được phản ánh trong danh mục.

Giữ lịch sử để biết dependency nào tồn tại tại thời điểm sự cố. Chỉ lưu trạng thái hiện tại có thể làm mất khả năng giải thích quá khứ.

## 16. Audit và bằng chứng theo dependency

### 16.1. Chuỗi bằng chứng

~~~text
Credential và nguồn xác thực
  → quan hệ consumer đã xác nhận
  → kế hoạch thay đổi theo phạm vi
  → thay đổi tại nguồn
  → phiên bản quản lý hoặc phân phối
  → consumer nhận và dùng
  → xác thực mới
  → chức năng đại diện
  → thu hồi phần cũ và trạng thái cuối.
~~~

Không phải mọi triển khai có cùng nguồn log. Điều cần có là khả năng giải thích từng tuyên bố trong phạm vi bằng chứng thực tế.

### 16.2. Sự kiện xác minh consumer

Một ví dụ logic:

~~~json
{
  "event_type": "consumer_authentication_verified",
  "change_reference": "credential-change-042",
  "credential_id": "credential-payment-database",
  "credential_version_reference": "version-13",
  "consumer_id": "payment-api-production",
  "consumer_scope": "recorded-instance-set",
  "target_id": "payment-database-production",
  "verification_method": "new-authentication-check",
  "evidence_reference": "verification-042",
  "outcome": "passed-for-defined-scope"
}
~~~

Ví dụ không chứa giá trị secret và không phải một kết quả thực tế. Hệ thống cần ghi thời điểm, chủ thể hoặc thành phần kiểm tra và giới hạn của phương pháp.

Nếu không quan sát trực tiếp phiên bản credential được consumer dùng, không nên ghi chắc chắn version-13 chỉ từ giả định. Cần mô tả phương pháp suy ra hoặc giữ trạng thái chưa xác minh.

### 16.3. Bằng chứng cấu hình khác bằng chứng sử dụng

- Một reference trong template chứng minh cấu hình mong muốn được ghi nhận.
- Một agent báo nhận phiên bản chứng minh một bước phân phối.
- Một tiến trình refresh thành công chứng minh hành động của tiến trình trong phạm vi quan sát.
- Một lần xác thực mới và tác vụ đại diện cung cấp bằng chứng sử dụng tại đích.

Không dùng các mức này thay thế nhau.

### 16.4. Bảo vệ danh mục dependency

Đồ thị có thể tiết lộ cấu trúc hệ thống, tài khoản đặc quyền và điểm phụ thuộc. Cần kiểm soát quyền xem, sửa, xuất và giữ lịch sử thay đổi.

Người sửa quan hệ không được tùy ý đánh dấu một consumer đã loại bỏ để né điều kiện rotation. Các thay đổi quan trọng cần owner và bằng chứng phù hợp.

## 17. Tình huống xuyên suốt: một credential có năm nhóm consumer

### 17.1. Bối cảnh

Một dịch vụ dùng tài khoản kỹ thuật trên cơ sở dữ liệu production. Đội vận hành muốn rotation credential và đưa mọi consumer về cơ chế phân phối được quản lý.

Sau discovery, có năm nhóm:

| Consumer | Cách lấy hiện tại | Hành vi quan trọng |
|---|---|---|
| API gồm nhiều instance | Reference được đọc khi khởi động | Tiến trình cũ không tự refresh |
| Worker xử lý nền | Agent phân phối | Thư viện kết nối có thể cache |
| Job đối soát theo lịch | Đọc reference lúc bắt đầu job | Chưa hoạt động trong giờ triển khai |
| Công cụ backup | Bản sao theo cấu hình riêng | Cần cập nhật tích hợp và quyền |
| Môi trường dự phòng | Template triển khai | Có thể mang reference cũ khi khởi động lạnh |

Các consumer và định danh là giả định của tình huống.

### 17.2. Phát hiện vấn đề ngoài trạng thái runtime

API đang truy cập bình thường, nhưng điều đó chưa chứng minh dùng được credential mới. Worker có agent cập nhật, nhưng chưa biết thư viện đã làm mất cache chưa.

Job theo lịch và môi trường dự phòng không tạo đăng nhập gần đây. Nếu chỉ dùng log giờ cao điểm, chúng có thể bị bỏ sót.

Công cụ backup có một bản sao riêng. Rotation ở vault không tự cập nhật bản sao đó.

### 17.3. Lập kế hoạch

Giả sử nguồn xác thực trong tình huống chỉ hỗ trợ một credential cho tài khoản này. Đội triển khai không hứa chuyển đổi không gián đoạn nếu chưa có cơ chế bảo đảm.

Kế hoạch xác định:

1. Phạm vi từng nhóm consumer và owner.
2. Cách kiểm soát tác vụ mới trong khoảng thay đổi.
3. Thứ tự cập nhật tại nguồn, vault và cơ chế phân phối.
4. Cách thay thế instance API.
5. Cách refresh và tạo kết nối mới cho worker.
6. Đường kiểm tra được phép cho job và backup.
7. Việc cập nhật template dự phòng.
8. Điều kiện đối soát hoặc phục hồi khi có lỗi.

Công cụ triển khai được cập nhật ở nguồn cấu hình mong muốn để không khôi phục reference cũ trong lần deploy sau.

### 17.4. Theo dõi kết quả từng phần

Sau rotation, API và worker đạt kiểm tra xác thực mới. Backup đã cập nhật reference nhưng chưa hoàn tất kiểm tra đường chạy. Job đối soát chưa có bằng chứng phù hợp.

Báo cáo đúng là:

~~~text
API: xác minh trong phạm vi instance đã ghi.
Worker: xác minh đường kết nối mới theo phương pháp đã ghi.
Backup: phân phối cập nhật; kiểm chứng sử dụng còn chờ.
Job đối soát: chưa hoàn tất kiểm chứng đường chạy.
Dự phòng: template đã cập nhật; trạng thái bootstrap cần kiểm tra theo kế hoạch.
~~~

Không báo toàn bộ rotation đã hoàn tất dependency chỉ vì ứng dụng chính đang khỏe.

### 17.5. Nếu job thất bại vào hôm sau

Cần kiểm tra job thực sự lấy reference nào, quyền đọc, phiên bản phân phối, cache và nguồn xác thực.

Nếu phát hiện pipeline của job còn inject một bản sao cũ, sửa đúng nguồn đó và kiểm chứng theo phạm vi. Không reset credential chung về bản cũ khi các consumer khác đã chuyển mà chưa đánh giá ảnh hưởng.

Sự kiện cũng cho thấy cần cập nhật bản đồ và phương pháp discovery. Một lỗi muộn có thể là dấu hiệu thiếu dependency, không chỉ là lỗi riêng của job.

## 18. Tiêu chí nghiệm thu và chỉ số quản trị

### 18.1. Nghiệm thu theo từng tuyên bố

| Tuyên bố | Bằng chứng cần có |
|---|---|
| Đã kiểm kê phạm vi | Danh sách nguồn, môi trường, loại đường chạy và giới hạn |
| Consumer còn nhu cầu | Xác nhận owner và bằng chứng phù hợp |
| Đã cập nhật reference | Trạng thái tại đúng nguồn cấu hình hoặc phân phối |
| Tiến trình đã nhận thay đổi | Bằng chứng từ runtime hoặc cơ chế cập nhật |
| Credential mới dùng được | Xác thực mới tại đúng nguồn theo phương pháp được phép |
| Consumer hoạt động | Tác vụ đại diện đạt tiêu chí |
| Credential cũ đã được xử lý | Trạng thái tại nguồn xác thực và phần phiên liên quan |
| Cấu hình không quay về cũ | Nguồn cấu hình mong muốn đã được cập nhật và kiểm tra |
| Đường phục hồi còn dùng được | Bằng chứng theo các tình huống đã xác định |

Không yêu cầu chứng minh bằng thử sai hàng loạt credential cũ nếu cách đó có thể khóa tài khoản hoặc gây tác động. Cần chọn phương pháp phù hợp khả năng nền tảng.

### 18.2. Các điều kiện còn mở

Nếu có consumer ít chạy chưa được kiểm tra, có thể cần giữ một công việc xác minh riêng với owner, thời hạn và biện pháp kiểm soát.

Trạng thái tổng cần nói rõ phần đã đạt và phần chưa đạt. Ngoại lệ không nên bị ẩn trong một nhãn success chung.

### 18.3. Chỉ số hữu ích

- Credential có owner, nguồn xác thực và phạm vi quyền rõ.
- Consumer có owner và cách cập nhật đã xác minh.
- Quan hệ đã cũ hoặc chưa có bằng chứng.
- Rotation có đủ kiểm chứng consumer theo phạm vi.
- Thời gian từ thay đổi nguồn tới xác thực mới của từng nhóm consumer.
- Lỗi dependency xuất hiện sau rotation.
- Bản sao hoặc reference ngoài cơ chế được quản lý.
- Vòng bootstrap chưa có đường phục hồi rõ.
- Credential dùng chung cho nhiều chức năng hoặc môi trường.
- Consumer đã loại bỏ nhưng vẫn còn quyền hoặc secret reference.

Mẫu số của chỉ số phải rõ. Tỷ lệ cập nhật trong tập consumer đã biết không chứng minh tỷ lệ bao phủ toàn bộ consumer thực tế nếu discovery chưa đầy đủ.

## 19. Duy trì dependency trong vòng đời hệ thống

### 19.1. Khi thêm consumer mới

Consumer mới cần được đăng ký với owner, nhu cầu, quyền, cách lấy secret và cách cập nhật. Không chờ tới lần rotation lỗi mới bổ sung vào danh mục.

Nếu consumer mới dùng credential chung, cần đánh giá ảnh hưởng tới blast radius và khả năng thu hồi. Có thể cần danh tính riêng thay vì mở rộng chia sẻ.

### 19.2. Khi thay đổi kiến trúc

Di chuyển môi trường, thay agent, đổi connection library hoặc chuyển sang broker có thể làm hành vi refresh khác trước.

Một quan hệ vẫn có cùng tên nhưng cơ chế đã đổi cần được xác minh lại. Không giữ bằng chứng cũ như thể mọi điều kiện vẫn giữ nguyên.

### 19.3. Khi đổi owner hoặc loại bỏ dịch vụ

Cần chuyển trách nhiệm, rà soát quyền và xác định những consumer nào thực sự còn hoạt động.

Khi offboard, phải xử lý tài khoản, credential, reference, bản sao, job, grant và các đường dự phòng trong phạm vi. Xóa tên dịch vụ khỏi danh mục không tự làm các dependency mất hiệu lực.

### 19.4. Phát hiện drift

Drift có thể là một consumer mới không đăng ký, pipeline đưa bản sao secret trở lại, role bị mở rộng hoặc cơ chế refresh bị tắt.

Cần so sánh trạng thái mong muốn với bằng chứng vận hành, phân loại khác biệt và cập nhật có trách nhiệm. Không tự xóa mọi đối tượng chưa biết mà chưa hiểu ảnh hưởng.

## 20. Lỗi thường gặp và bài tập áp dụng

### 20.1. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Một secret object được coi là một credential độc lập | Bỏ sót chia sẻ cùng tài khoản nền | Liên kết tới nguồn danh tính và credential thực tế |
| Chỉ ghi ứng dụng chính | Bỏ job, backup và dự phòng | Discovery nhiều nguồn và ghi rõ phạm vi |
| Reference đổi là coi consumer đã dùng mới | Cache hoặc tiến trình cũ tiếp tục dùng bản trước | Xác minh runtime và xác thực mới |
| Dịch vụ đang khỏe là coi rotation đạt | Kết nối cũ che lỗi | Kiểm tra đường xác thực mới phù hợp |
| Không có log gần đây là coi hết dependency | Bỏ sót consumer ít chạy | Xác minh lịch, owner và đường phục hồi |
| Mặc định đích cho dùng hai credential | Kế hoạch chuyển đổi không thực hiện được | Kiểm tra khả năng thật của nguồn |
| Chỉ sửa runtime, bỏ template | Lần deploy sau tái tạo lỗi | Cập nhật nguồn cấu hình mong muốn |
| Retry rotation sau timeout mà không đối soát | Tăng số trạng thái lệch | Giữ request reference và xác minh trước khi thử lại |
| Dùng lại credential nghi lộ để rollback | Khôi phục đường xâm nhập | Chọn trạng thái phục hồi theo rủi ro và bằng chứng |
| Xóa vault object để dọn lỗi | Mất tham chiếu và khả năng phục hồi | Xử lý dependency trước khi loại bỏ |
| Đổi credential là coi mọi phiên kết thúc | Truy cập cũ có thể còn | Quản lý phiên và grant riêng |
| Dùng secret hoặc hash đơn giản làm ID | Tạo thêm đường lộ dữ liệu | Dùng định danh và metadata có kiểm soát |
| Một tỷ lệ completion che mọi vùng chưa biết | Báo cáo quá mức bằng chứng | Tách tiến độ, độ mới, phạm vi và ngoại lệ |

### 20.2. Bài tập

Một đội quản lý tài khoản kỹ thuật được dùng bởi hai ứng dụng, một job cuối tháng và một site dự phòng. Vault đã đổi credential thành công. Hai ứng dụng vẫn chạy, nên đội muốn đóng thay đổi. Job không có log trong tuần này; template dự phòng chưa được kiểm tra. Một ứng dụng chỉ đọc secret lúc khởi động, ứng dụng còn lại dùng connection pool dài hạn.

Hãy phân tích:

1. Vì sao trạng thái đang chạy chưa đủ chứng minh hai ứng dụng đã dùng credential mới?
2. Cần biết thêm gì về job và site dự phòng?
3. Những trạng thái nào cần tách trong báo cáo?
4. Cần kiểm soát nguồn cấu hình nào để lỗi không quay lại?
5. Nếu credential cũ bị nghi lộ, kế hoạch thu hồi cần xem những lớp nào?
6. Những bằng chứng nào đủ để đóng từng phần trong phạm vi?

Hướng phân tích:

- Tiến trình hoặc kết nối cũ có thể tiếp tục dù lần xác thực mới sẽ lỗi.
- Cần owner, lịch chạy, cách lấy secret, refresh và đường bootstrap của các consumer ít hoạt động.
- Phân biệt cập nhật reference, phân phối, runtime, xác thực mới, chức năng và xử lý truy cập cũ.
- Pipeline, template, controller hoặc nguồn cấu hình có thể đưa reference cũ trở lại.
- Cần xử lý quyền lấy secret, credential tại nguồn, consumer, grant, phiên và thay đổi bền vững liên quan.
- Tiêu chí đóng phải gắn với bằng chứng từng consumer và giữ rõ phần chưa xác minh.

## 21. Các điểm cần nắm

Credential dependency là mạng quan hệ giữa danh tính, credential, cơ chế phân phối, consumer và các tác vụ vòng đời. Quản lý dependency giúp rotation và thu hồi dựa trên phạm vi thực tế thay vì một danh sách secret đơn thuần.

Đã đổi credential, đã cập nhật reference, tiến trình đã nhận và xác thực mới thành công là các kết quả khác nhau. Mỗi kết quả cần bằng chứng phù hợp.

Khi đánh giá một thay đổi, hãy lần theo credential từ nguồn xác thực qua vault, cấu hình, cache, consumer, phiên và đường phục hồi. Luôn nêu rõ phạm vi đã xác minh, phần chưa biết và người chịu trách nhiệm cho bước tiếp theo.
