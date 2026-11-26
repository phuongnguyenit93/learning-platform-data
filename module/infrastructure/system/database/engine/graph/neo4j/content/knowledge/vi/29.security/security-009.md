# Nhật ký kiểm toán và bảo vệ dữ liệu nhạy cảm khi được hỗ trợ

Trong ứng dụng Neo4j, kiểm soát quyền đọc/ghi mới là một nửa của bài toán bảo mật. Khi có truy cập trái phép hoặc nghi ngờ dữ liệu bị thay đổi, đội vận hành còn cần trả lời: **ai đã làm gì, vào lúc nào, từ đâu, với kết quả nào và bằng chứng có đủ tin cậy không?** Ngược lại, nếu ghi nhật ký quá chi tiết, chính các tệp log lại có thể chứa email, số định danh, nội dung truy vấn, tham số và những quan hệ riêng tư mà hệ thống đang cố bảo vệ.

Bài học thuộc chương **Bảo mật** của module `DATABASE_ENGINE_GRAPH_NEO4J`, nơi Neo4j được dùng để mô hình hóa dữ liệu bằng **property graph**, truy vấn node và relationship bằng Cypher, quản lý index/constraint, tích hợp Java Driver và Spring Data Neo4j, đồng thời vận hành hệ thống đồ thị. Chủ đề là **nhật ký kiểm toán và bảo vệ dữ liệu nhạy cảm khi phiên bản, edition hoặc dịch vụ triển khai hỗ trợ**, kết hợp các kiểm soát ở database, ứng dụng và hạ tầng.

Sau bài học, bạn có thể:

- Phân biệt `security.log`, `query.log`, các log vận hành và nhật ký kiểm toán nghiệp vụ.
- Xác định sự kiện nào Neo4j ghi sẵn, sự kiện nào ứng dụng phải tự ghi, và trường hợp nào **không thể suy ra** từ log.
- Cấu hình query logging theo hướng hạn chế lộ literal/parameter, xử lý lỗi và metadata nhạy cảm.
- Lựa chọn quyền tối thiểu, bảo vệ thuộc tính và ranh giới tenant, nhận biết giới hạn theo edition/phiên bản.
- Thiết kế một audit event gắn với transaction thay đổi graph và luồng chuyển log sang nơi lưu có kiểm soát.
- Kiểm thử các tình huống truy cập không hợp lệ, log có nguy cơ lộ dữ liệu, mất log, rollback, rotation và khôi phục sau sự cố.

> **Giới hạn tính năng:** Neo4j Community, Enterprise, AuraDB và các gói Aura khác nhau không có cùng khả năng quản trị/logging/ủy quyền. Tên cấu hình cũng có thể đổi theo dòng phiên bản. Các ví dụ quản trị trong bài phải được đối chiếu với **tài liệu và quyền của hệ thống đang dùng**, không chạy trực tiếp trên production khi chưa có quy trình thay đổi.

## 1. Xây dựng mô hình đe dọa trước khi bật log

Giả sử hệ thống quản lý hồ sơ khách hàng và đơn đặt hàng:

~~~text
(:SecDemoCustomer {
  tenantId, customerId,
  displayName, email, phone, nationalId
})
       |
       | [:SEC_DEMO_PLACED]
       v
(:SecDemoOrder {
  tenantId, orderId,
  amountMinor, status
})
~~~

Các trường khác nhau có độ nhạy khác nhau:

| Loại thông tin | Ví dụ | Rủi ro khi lộ |
| --- | --- | --- |
| Định danh nội bộ | `customerId`, `orderId` | Bị dùng để liên kết và suy đoán hồ sơ nếu có thêm dữ liệu khác. |
| PII/liên hệ | `email`, `phone`, `nationalId` | Xâm phạm riêng tư, lừa đảo hoặc liên kết danh tính. |
| Thông tin tài chính | `amountMinor`, trạng thái giao dịch | Lộ hành vi, giá trị giao dịch hoặc bí mật kinh doanh. |
| Cấu trúc quan hệ | Ai kết nối với ai, mua gì, liên quan tổ chức nào | Có thể tiết lộ thông tin ngay cả khi đã ẩn tên. |
| Dữ liệu vận hành | Username, IP, query text, transaction metadata | Có thể chứa định danh và thông tin hệ thống để tấn công tiếp. |
| Bí mật hệ thống | Password, access token, API key, private key | Có thể dẫn đến chiếm quyền truy cập. **Không ghi bí mật thô vào log.** |

Đồ thị đặc biệt cần chú ý **suy luận từ quan hệ**. Một câu trả lời chỉ gồm tên node hoặc số lượng cạnh cũng có thể làm lộ việc hai người thuộc cùng nhóm nhạy cảm. Vì vậy, bảo vệ **node property** là cần thiết nhưng chưa đủ; phải kiểm soát khả năng duyệt, phát hiện và xuất relationship.

### 1.1. Mục tiêu bảo mật và kiểm toán

Mục tiêu gồm bốn nhóm:

1. **Ngăn truy cập trái phép:** xác thực, phân quyền, giới hạn dữ liệu theo tenant/đối tượng/field.
2. **Giảm lộ dữ liệu khi vận hành:** không đưa dữ liệu nhạy cảm vào query log, exception, tracing hoặc log của gateway.
3. **Có bằng chứng truy vết:** xác định actor, hành động, đối tượng, kết quả, request ID và thời gian.
4. **Bảo vệ chính bằng chứng:** hạn chế người sửa/xóa log, lưu bền vững, giám sát mất log và áp dụng thời hạn lưu/xóa theo chính sách.

**Logging không thay thế authorization.** Một hệ thống ghi lại rằng có người đọc dữ liệu sai quyền vẫn đã để lộ dữ liệu trước khi cảnh báo xuất hiện. Logging là lớp phát hiện/điều tra, còn quyền và thiết kế truy vấn là lớp ngăn chặn.

## 2. Không gọi tất cả mọi loại log là “audit log”

Neo4j và tầng ứng dụng có thể tạo ra nhiều nguồn thông tin. Chúng ghi **những sự kiện khác nhau**:

| Nguồn | Mục đích chính | Có thể hỗ trợ điều tra gì? | Không được tự kết luận |
| --- | --- | --- | --- |
| **`security.log`** (khi được hỗ trợ) | Ghi sự kiện bảo mật Neo4j. | Đăng nhập thành công/thất bại, lệnh quản trị, lỗi phân quyền và các sự kiện auth được hỗ trợ. | Không mặc nhiên ghi **mỗi node/property mà người dùng đã xem**. |
| **`query.log`** (khi được hỗ trợ) | Quan sát truy vấn và hiệu năng. | Query được thực thi, thời gian, nguồn kết nối, kết quả thành công/lỗi, metadata tùy cấu hình. | Không mặc nhiên là nhật ký thay đổi dữ liệu đầy đủ, không ghi các giá trị đã trả về cho client. |
| **`neo4j.log` / `debug.log`** | Vận hành, lỗi và chẩn đoán. | Database khởi động, trục trặc dịch vụ, lỗi cần điều tra. | Không bảo đảm ghi actor/hành động nghiệp vụ. |
| **`http.log` / log gateway** | Truy cập tầng HTTP. | Nguồn request, endpoint, status, độ trễ khi được bật. | Không xác định được tất cả dữ liệu Cypher/Bolt trả về. |
| **Audit event của ứng dụng** | Theo dõi hành động nghiệp vụ. | Ai duyệt hồ sơ, đổi vai trò, xuất dữ liệu, sửa đơn hàng. | Không tự chứng minh đã ngăn DBA/superuser sửa log trong cùng database. |
| **Log hạ tầng/cloud/IdP** | Quản trị tài nguyên, kết nối và danh tính. | Thay đổi cấu hình, quyền cloud, phiên đăng nhập, xuất snapshot. | Không tự thay thế kiểm tra dữ liệu ở tầng ứng dụng. |

Với Neo4j self-managed Enterprise, tài liệu Neo4j mô tả `security.log` ghi sự kiện bảo mật, bao gồm các lần đăng nhập, lệnh quản trị ở database `system` và lỗi authorization; `query.log` ghi truy vấn theo chính sách cấu hình. Các tính năng này có giới hạn theo edition. Với Neo4j Aura, một số gói cung cấp **query/security logs** trong giao diện dịch vụ và **activity feed** theo dõi hành động ở cấp tổ chức/dự án; không mặc định có quyền truy cập tệp log trong máy chủ như bản self-managed.

**Điểm quan trọng:** nếu ứng dụng dùng một tài khoản dịch vụ chung để kết nối Neo4j, `security.log` hoặc `query.log` ở phía database có thể chỉ nhìn thấy **tài khoản dịch vụ**, không tự biết người dùng cuối đã yêu cầu mở hồ sơ nào. Nếu cần truy vết người dùng cuối, ứng dụng phải ghi actor đã xác thực và correlation ID riêng, kèm chính sách bảo vệ log.

## 3. Những sự kiện nào cần kiểm toán?

Không phải hệ thống nào cũng cần lưu mọi lần đọc như nhau. Xác định mức độ quan trọng theo loại hành động và yêu cầu nghiệp vụ:

| Hành động | Ví dụ | Gợi ý nguồn bằng chứng |
| --- | --- | --- |
| Đăng nhập/đăng nhập thất bại | Người dùng hoặc tài khoản dịch vụ đăng nhập Neo4j. | Security log/IdP khi hỗ trợ và đúng phạm vi. |
| Thay đổi vai trò/quyền | Cấp quyền cho một user/role. | Security log và hệ thống quản trị danh tính. |
| Đọc hồ sơ nhạy cảm | Nhân viên xem chi tiết khách hàng. | Audit event ở API/service có danh tính người dùng cuối. |
| Xuất dữ liệu số lượng lớn | Export danh sách khách hàng. | Audit event riêng, sự kiện xuất file và log dịch vụ lưu trữ. |
| Chỉnh sửa thuộc tính | Đổi email, trạng thái đơn, thông tin liên hệ. | Audit event nghiệp vụ gắn với transaction đã commit. |
| Thay đổi quan hệ | Liên kết tài khoản với tổ chức, thêm quyền thành viên. | Audit event mô tả type, endpoint theo định danh được phép ghi. |
| Xóa/ẩn danh dữ liệu | Xóa theo yêu cầu hợp lệ. | Audit metadata về yêu cầu, chủ thể, trạng thái hoàn tất; hạn chế giữ PII trong audit. |
| Backup/restore/đổi cấu hình | Tạo bản sao, phục hồi database hoặc thay retention. | Log quản trị hạ tầng, activity feed hoặc cơ chế theo nền tảng. |

Một audit record có ích thường cần:

- **Actor:** định danh nội bộ của người/service đã xác thực, phân biệt `onBehalfOf` và tài khoản kỹ thuật nếu có.
- **Action:** mã hành động có ngữ nghĩa ổn định như `CUSTOMER_PROFILE_READ` hoặc `CUSTOMER_EMAIL_CHANGED`.
- **Target:** loại thực thể và định danh **ít nhạy cảm nhất có thể**.
- **Outcome:** `SUCCEEDED`, `DENIED`, `FAILED` hoặc `PENDING` với ý nghĩa rõ ràng.
- **Time:** timestamp có timezone rõ ràng, đồng bộ đồng hồ giữa các hệ thống.
- **Context:** tenant, request ID/trace ID, origin hoặc mục đích truy cập khi cần.
- **Integrity:** event ID duy nhất, phiên bản schema của audit record, vị trí/nguồn nhận và trạng thái chuyển tới nơi lưu bền vững.

Không ghi toàn bộ trước/sau của những trường nhạy cảm chỉ để “cho đủ bằng chứng”. Nhiều trường hợp chỉ cần **tên trường thay đổi**, mã hành động và tham chiếu hồ sơ được bảo vệ; nếu bắt buộc giữ giá trị trước/sau, hãy phân quyền và mã hóa phần đó theo chính sách riêng.

## 4. Cách tiếp cận log trên từng hình thức triển khai

### 4.1. Neo4j tự quản lý (self-managed)

Ở môi trường tự quản lý, người vận hành có thể cấu hình log theo những khả năng bản Neo4j hỗ trợ:

- Kiểm tra edition, phiên bản và cấu hình bảo mật trước khi kỳ vọng `security.log` hoặc `query.log`.
- Chọn cấu hình Log4j, vị trí lưu, quyền hệ điều hành, rotation và forwarding theo chuẩn của tổ chức.
- Hạn chế người được đọc tệp log và backup; tài khoản chạy Neo4j không nên là tài khoản cá nhân có đặc quyền vượt mức cần thiết.
- Giám sát dung lượng đĩa, tốc độ ghi log và trạng thái agent chuyển log tới hệ thống quan sát tập trung.

Tài liệu Neo4j các dòng 2025/2026 dùng `server-logs.xml` cho các log server như `debug.log`, `query.log` và `security.log`. Với các bản cũ hơn, một số tên setting/đường dẫn có thể khác; **không copy cấu hình của dòng 4.x vào dòng 2025+ mà không kiểm tra**.

### 4.2. Neo4j Aura

Với dịch vụ quản lý như Aura, hạ tầng và quyền xem log có thể được cung cấp **qua console/API**, tùy gói. Một số chức năng như xuất query/security log hoặc activity feed có thể giới hạn role, thời gian truy xuất, dung lượng và mức dịch vụ. Không giả định rằng có thể SSH vào máy chủ Aura hoặc sửa `neo4j.conf` như self-managed.

Khi yêu cầu kiểm toán bắt buộc, hãy xác minh **gói dịch vụ hiện có** cung cấp loại log nào, có thể xuất sang SIEM không, độ trễ và retention là bao nhiêu. Nếu log nền tảng không ghi sự kiện đọc hồ sơ của người dùng cuối, cần triển khai audit ở tầng ứng dụng.

### 4.3. Community Edition và quyền truy cập chi tiết

Một số chức năng quản lý người dùng cơ bản có trong Neo4j Community, nhưng các cơ chế **role-based, property-based/fine-grained access control và những log Enterprise** không nên mặc định là có. Nếu môi trường thiếu tính năng cần thiết:

- Đặt Neo4j trong mạng riêng, chỉ cho các service được ủy quyền truy cập.
- Thực thi authorization ở backend, không cấp tài khoản Neo4j trực tiếp cho client không tin cậy.
- Giới hạn field và đường truy vấn ở API, tránh `RETURN n` hoặc `RETURN *` cho đối tượng nhạy cảm.
- Dùng log ứng dụng/IdP/gateway để bổ sung dấu vết và forwarding sang nơi lưu có kiểm soát.
- Với yêu cầu cách ly nghiêm ngặt, cân nhắc edition/dịch vụ có cơ chế bắt buộc tại database hoặc tách môi trường dữ liệu.

Authorization chỉ ở tầng ứng dụng có thể bị vượt qua nếu xuất hiện đường truy cập trực tiếp khác đến Neo4j. Vì vậy, **khả năng giới hạn kết nối tới DB** là điều kiện thiết yếu khi dựa vào lớp ứng dụng.

## 5. Cấu hình query log để giảm nguy cơ rò rỉ

Query log rất hữu ích cho hiệu năng và điều tra, nhưng nguy cơ lớn nhất là **query text và tham số chứa PII/secrets**. Ví dụ:

~~~cypher
// KHÔNG nên đưa thông tin nhạy cảm trực tiếp vào literal query.
MATCH (c:SecDemoCustomer {email: 'real-person@example.invalid'})
RETURN c;
~~~

Nếu query text được ghi log ở dạng không che literal, email có thể xuất hiện trong `query.log`. Đổi sang tham số giúp tách query khỏi dữ liệu đầu vào, đồng thời tránh xây dựng Cypher bằng nối chuỗi:

~~~cypher
MATCH (c:SecDemoCustomer {email: $email})
RETURN c.customerId AS id,
       c.displayName AS name;
~~~

Nhưng **tham số hóa không đủ**: nếu query log được cấu hình ghi parameter thì giá trị `$email` vẫn có thể xuất hiện. Ngoài ra, `RETURN c` ở API có thể trả những property nhạy cảm không cần thiết; cần projection field có kiểm soát.

### 5.1. Một cấu hình minh họa có ý thức về dữ liệu

Ví dụ sau dành cho **bản self-managed hỗ trợ các setting tương ứng**, theo tên cấu hình của dòng Neo4j mới hơn; đây không phải mặc định an toàn cho mọi hệ thống:

~~~properties
# neo4j.conf - ví dụ chính sách ghi query chọn lọc
db.logs.query.enabled=INFO
db.logs.query.threshold=500ms
db.logs.query.parameter_logging_enabled=false
db.logs.query.obfuscate_literals=true
db.logs.query.early_raw_logging_enabled=false
~~~

Ý nghĩa:

| Setting | Tác dụng | Điểm cần cân nhắc |
| --- | --- | --- |
| `db.logs.query.enabled=INFO` | Ghi truy vấn khi kết thúc và vượt ngưỡng. | **Không tạo lịch sử đầy đủ** của mọi query dưới ngưỡng. |
| `db.logs.query.threshold=500ms` | Tập trung vào truy vấn chậm. | Bỏ qua truy vấn nhanh nhưng có thể nhạy cảm; không dùng làm audit toàn diện. |
| `db.logs.query.parameter_logging_enabled=false` | Không ghi giá trị parameter vào query log. | Giảm chi tiết hỗ trợ debug; **không** kiểm soát log của ứng dụng. |
| `db.logs.query.obfuscate_literals=true` | Che nhiều literal trong query text. | Không che tất cả yếu tố cấu trúc; không che giá trị parameter nếu parameter logging được bật. |
| `db.logs.query.early_raw_logging_enabled=false` | Tránh ghi query/parameter thô ở giai đoạn sớm với chế độ này. | Cần kiểm tra cài đặt khác và chính sách logging đầy đủ. |

Các phiên bản Neo4j 2026 có thêm setting `db.logs.query.obfuscate_errors` (được giới thiệu trong các bản 2026.01.x) để che thông tin nhạy cảm từ lỗi trong query log. **Chỉ dùng khi phiên bản đang chạy hỗ trợ** và đã kiểm tra tác dụng:

~~~properties
# Chỉ áp dụng trên phiên bản hỗ trợ setting này.
db.logs.query.obfuscate_errors=true
~~~

Lưu ý:

- Chỉ bật obfuscation **không** bảo đảm mọi dữ liệu nhạy cảm biến mất: tên label, relationship type, tên property và một số literal cú pháp vẫn có thể hiện ra.
- `db.logs.query.max_parameter_length` nếu được cấu hình chỉ **giới hạn độ dài giá trị log**, không phải biện pháp ẩn dữ liệu đáng tin cậy.
- Bật chế độ verbose/tracing trong lúc điều tra có thể tăng mức thu thập dữ liệu; cần quy trình phê duyệt, thời gian kết thúc và kiểm tra log thu được.
- Ở một số bản, thay đổi cài đặt che literal không ảnh hưởng các query đã cache; quy trình vận hành có thể cần xử lý query cache theo tài liệu phiên bản.
- Cấu hình log, nơi lưu và phạm vi truy vấn của **ứng dụng Java/Spring, reverse proxy và agent APM** cần được kiểm tra riêng.

**Không coi `query.log` là audit trail hoàn chỉnh.** Chế độ `INFO` với ngưỡng có thể bỏ qua nhiều truy vấn; ngay cả khi ghi mọi query, nó không mặc nhiên cho biết người dùng cuối, các node/field thực sự đọc, dữ liệu response hoặc ý nghĩa nghiệp vụ.

### 5.2. Kiểm tra setting thay vì đoán

Trong phiên bản hỗ trợ `SHOW SETTINGS` và với tài khoản có quyền:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name IN [
  'db.logs.query.enabled',
  'db.logs.query.threshold',
  'db.logs.query.parameter_logging_enabled',
  'db.logs.query.obfuscate_literals',
  'db.logs.query.early_raw_logging_enabled',
  'db.logs.query.obfuscate_errors'
]
RETURN name, value
ORDER BY name;
~~~

Nếu một setting không tồn tại trên phiên bản hiện tại, không cố gắng ép hệ thống nhận nó. Thay đổi cấu hình động có thể có phạm vi **mỗi server**, không tự lan sang mọi thành viên cluster; thay đổi runtime cũng có thể không được giữ sau restart nếu chưa cập nhật cấu hình bền vững. Với Aura, dùng giao diện/cơ chế do nền tảng cho phép thay vì giả định `SHOW SETTINGS` đồng nghĩa có quyền sửa mọi setting.

## 6. Security log ghi những gì và bỏ sót những gì?

Trong Neo4j self-managed Enterprise với xác thực bật, `security.log` được mô tả ghi các sự kiện như:

- Đăng nhập thành công và thất bại (tùy chính sách, có thể điều chỉnh logging đăng nhập thành công).
- Lệnh quản trị liên quan người dùng, role và quyền trên database `system`.
- Lỗi kiểm tra authorization do cơ chế RBAC.
- Một số sự kiện liên quan hệ thống xác thực ngoài như LDAP, tùy cấu hình.

Ví dụ minh họa **đã lược bỏ dữ liệu định danh cụ thể**, không phải format cố định:

~~~text
2026-11-25T08:00:01Z INFO  [svc-graph-read]: logged in
2026-11-25T08:01:10Z ERROR [unknown]: failed to log in
2026-11-25T08:03:00Z INFO  [admin-user]: GRANT ROLE ...
~~~

Nếu tổ chức cần biết “người dùng cuối X xem số điện thoại của khách hàng Y”, một log đăng nhập bằng tài khoản `svc-graph-read` **không cung cấp đủ thông tin đó**. Ứng dụng có thể dùng principal từ API, kiểm tra quyền, rồi ghi audit event `CUSTOMER_CONTACT_VIEWED` với đối tượng Y và kết quả truy cập.

### 6.1. Lựa chọn ghi sự kiện đăng nhập thành công

Ở các bản self-managed hỗ trợ, có setting:

~~~properties
dbms.security.log_successful_authentication=true
~~~

Việc ghi mọi lần đăng nhập thành công giúp điều tra nhưng có thể rất nhiều khi service mở kết nối hoặc xác thực liên tục. Nếu muốn giảm log và điều kiện nghiệp vụ cho phép bỏ bớt, kiểm tra chính sách và tác động trước khi chỉnh setting. **Tắt log đăng nhập thành công có thể làm mất bằng chứng cần cho kiểm toán**, không nên làm chỉ vì tiết kiệm dung lượng.

### 6.2. Từ log bảo mật tới SIEM

Khi forwarding các sự kiện sang SIEM/hệ thống log tập trung:

1. Chuyển log qua đường truyền được mã hóa, tài khoản agent chỉ có quyền cần thiết.
2. Chuẩn hóa timestamp UTC, event type, mức độ, source host/instance, user và request ID nếu có.
3. Giữ **dữ liệu thô trong vùng truy cập hạn chế** khi cần điều tra, còn dashboard dùng thông tin đã giảm độ nhạy.
4. Thiết lập cảnh báo bất thường: nhiều lần đăng nhập thất bại, cấp quyền admin ngoài lịch, thay đổi role hàng loạt, đột biến export hoặc query nhạy cảm.
5. Theo dõi lag của collector, thiếu sequence/time window và lỗi parse, vì **mất log** cũng là một sự kiện vận hành quan trọng.

Format và trường của log thay đổi theo version/JSON layout, nên parser không được phụ thuộc một ví dụ thông điệp duy nhất. Không tự nhận một quy trình forwarding có tính *tamper-proof* nếu người có đặc quyền có thể sửa cả nguồn và nơi lưu.

## 7. Bảo vệ dữ liệu nhạy cảm ngay ở cấp quyền truy cập

Tầng ứng dụng phải áp dụng **nguyên tắc quyền tối thiểu**:

- API đọc thông tin cơ bản không cần được phép đọc mọi property của `SecDemoCustomer`.
- Dịch vụ báo cáo chỉ cần dữ liệu đã tổng hợp, không nhất thiết thấy email, phone hoặc mọi relationship cá nhân.
- Tài khoản ghi dữ liệu không cần quyền quản lý users/roles hoặc backup.
- Tài khoản log collector chỉ cần đọc nguồn log, không có quyền sửa dữ liệu graph.
- Người vận hành không nên dùng chung tài khoản admin cho mọi job.

### 7.1. Neo4j fine-grained access control khi được hỗ trợ

Các cơ chế phân quyền chi tiết của Neo4j Enterprise và một số gói Aura cho phép kiểm soát khả năng **TRAVERSE** node/relationship và **READ** property theo role; một số dòng còn hỗ trợ điều kiện dựa trên giá trị property (*property-based access control*).

Ví dụ minh họa cho một **database học tập** khi có đủ đặc quyền quản trị (các lệnh quản trị vai trò chạy với database `system` hoặc được driver điều phối đúng):

~~~cypher
CREATE ROLE secDemoReader IF NOT EXISTS;
~~~

~~~cypher
GRANT ACCESS ON DATABASE neo4j TO secDemoReader;
~~~

~~~cypher
GRANT TRAVERSE ON GRAPH neo4j
NODES SecDemoCustomer TO secDemoReader;
~~~

~~~cypher
GRANT READ {displayName} ON GRAPH neo4j
NODES SecDemoCustomer TO secDemoReader;
~~~

Đây là ví dụ **allowlist** một property được đọc. Role này không tự có quyền đọc `email`, `phone` hoặc `nationalId` nếu không có những quyền khác được cấp từ các role chồng lấn. Tuy nhiên, người dùng có thể có **nhiều role**, nên phải kiểm tra quyền hợp nhất thực tế; không suy ra rằng một role hạn chế có thể thu hồi mọi quyền đã được cấp ở role khác.

Nếu ứng dụng cần lọc/so sánh bằng `tenantId` hoặc `customerId`, hãy xét kỹ quyền `READ/MATCH/TRAVERSE` cần thiết, cách query sử dụng property và chính sách bảo vệ định danh. **Chỉ cấp `TRAVERSE` không có nghĩa một truy vấn lọc property sẽ luôn hoạt động đúng.**

Ví dụ kiểm tra quyền role được thực hiện bởi người quản trị có thẩm quyền:

~~~cypher
SHOW ROLE secDemoReader PRIVILEGES AS COMMANDS;
~~~

Các lệnh `GRANT/DENY` phải được thử trên dữ liệu giả và tài khoản thử **không có role mạnh khác** trước khi áp dụng. Tùy phiên bản, có thể cần thêm quyền cụ thể để chạy procedure, quản trị index hoặc truy cập database.

### 7.2. Property-based access không phải cơ chế tenant magic

Một số phiên bản/edition hỗ trợ rule `GRANT ... WHERE property = value` để giới hạn khả năng duyệt/đọc. Tuy nhiên, **đừng tự giả định** có thể viết một rule dùng mọi `tenantId` động của người đăng nhập mà không cần cấu hình phân quyền tương ứng. Khi cần multi-tenant:

1. Định nghĩa nguồn danh tính và danh sách tenant được cấp quyền.
2. Xác định ranh giới enforcement ở Neo4j, API hoặc cơ sở dữ liệu riêng.
3. Ràng buộc truy vấn từ node bắt đầu đến **mọi endpoint mở rộng** theo phạm vi hợp lệ.
4. Kiểm tra cả đường đi, kết quả tổng hợp và các hàm suy ra liên kết.
5. Dùng **kiểm thử với user/role thật** để phát hiện lỗi khi có nhiều GRANT/DENY.

Với rule dựa trên property, kiểm tra trường hợp property **thiếu/null**, phiên bản rule, quyền sửa property điều kiện và các trường hợp `DENY` không được đánh giá như kỳ vọng. Không coi một biểu thức deny duy nhất là ranh giới cách ly mạnh nếu hệ thống có thể có bản ghi thiếu thuộc tính kiểm soát.

### 7.3. Projection bảo mật ở Cypher

Truy vấn đọc thông tin công khai:

~~~cypher
MATCH (c:SecDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id,
       c.displayName AS displayName;
~~~

Tránh các biểu thức như:

~~~cypher
// Không phù hợp cho API chỉ được trả thông tin công khai.
MATCH (c:SecDemoCustomer {customerId: $customerId})
RETURN c;
~~~

Truy vấn thứ hai thiếu ràng buộc tenant và có nguy cơ trả **mọi property** của node, kể cả trường mới thêm trong tương lai. Dù đã có phân quyền ở database, API vẫn cần chọn đúng các trường theo use case và không bật debug serialization tiết lộ toàn bộ entity.

**Không tin `$tenantId` do client gửi là bằng chứng ủy quyền.** Service phải xác nhận tenant từ principal/claim đã được kiểm chứng và ngăn yêu cầu tới tenant ngoài phạm vi.

## 8. Mã hóa, tối thiểu hóa và vòng đời dữ liệu

### 8.1. Mã hóa đường truyền

Với kết nối từ Java Driver/Spring Data Neo4j:

- Dùng giao thức kết nối có mã hóa và xác thực certificate đáng tin cậy, theo cấu hình Bolt/TLS của triển khai.
- Dùng HTTPS giữa client và API; bảo vệ kết nối giữa reverse proxy, backend, Neo4j và nơi nhận log.
- Không tắt kiểm tra certificate hoặc dùng cấu hình chấp nhận chứng chỉ bất kỳ trong production chỉ để “kết nối được”.
- Hạn chế cổng Bolt, HTTP, backup và cluster bằng phân đoạn mạng/firewall, chỉ cho phép nguồn cần thiết.

Đừng nhầm mã hóa **in transit** với bảo vệ dữ liệu đã lưu ở ổ đĩa hoặc backup.

### 8.2. Mã hóa dữ liệu lưu trữ

Ở self-managed, bảo vệ dữ liệu lưu trữ có thể gồm mã hóa volume/đĩa do hạ tầng quản lý, quyền filesystem, hạn chế truy cập backup/dump, kiểm soát key và kế hoạch restore. Với dịch vụ được quản lý, kiểm tra khả năng mã hóa at rest và cơ chế khóa theo gói dịch vụ.

**Không mặc định** Neo4j tự mã hóa riêng từng node property khi ứng dụng đặt giá trị vào Cypher. Nếu cần bí mật hóa một trường cụ thể:

- Cân nhắc **mã hóa ở tầng ứng dụng** bằng cơ chế quản lý khóa thích hợp, không tự xây thuật toán mã hóa.
- Xác định cách tìm kiếm, sắp xếp, uniqueness và index hoạt động khi dữ liệu thành ciphertext.
- Tránh đưa khóa mã hóa vào property, query parameter bị log, file cấu hình commit lên VCS hoặc audit record.
- Đánh giá khả năng bị lộ thông tin qua **mối quan hệ, tần suất truy cập và metadata** ngay cả khi nội dung property được mã hóa.

Ví dụ, nếu `email` được mã hóa bằng thuật toán có ngẫu nhiên hóa, so khớp trực tiếp `WHERE c.email = $email` có thể không còn hoạt động theo cách cũ. Có thể cần thiết kế chỉ mục tra cứu riêng bằng khóa đã chuẩn hóa và token hóa/HMAC theo tiêu chuẩn bảo mật của tổ chức, kèm phân tích rủi ro lộ sự trùng khớp. **Không dùng hash không khóa của email như một cách ẩn danh an toàn** vì email có thể bị đoán từ tập giá trị phổ biến.

### 8.3. Data minimization và retention

Mỗi property nhạy cảm cần có lý do tồn tại, quyền truy cập và thời hạn giữ. Cân nhắc:

- Chỉ lưu `phone` khi tính năng nghiệp vụ cần, không thêm mọi trường của database nguồn theo thói quen.
- Tách hoặc loại bỏ dữ liệu quá hạn bằng quy trình được phê duyệt, gồm các bản sao đọc, cache, export và backup theo chính sách.
- Không giữ payload raw trong event audit nếu mục tiêu chỉ là chứng minh hành động đã diễn ra.
- Khi xóa dữ liệu cá nhân, lưu **metadata kiểm toán tối thiểu** mà không tạo lại kho PII mới kéo dài vô hạn.

Chính sách retention liên quan đến luật/quy định và hợp đồng cụ thể; thời hạn trong bài thực hành chỉ mang tính ví dụ, không phải tư vấn pháp lý.

## 9. Thiết kế audit trail nghiệp vụ trong ứng dụng Neo4j

Một API nghiệp vụ có thể cần bằng chứng rằng service đã cập nhật một node và đã tạo record kiểm toán **trong cùng transaction**.

Ví dụ mô hình:

~~~text
API (principal đã xác thực)
        |
        v
Service kiểm tra quyền tenant + field
        |
        v
BEGIN TRANSACTION Neo4j
  - cập nhật (:SecDemoCustomer)
  - tạo (:SecDemoAuditEvent {auditId,...})
COMMIT
        |
        v
Collector/Exporter có thể chuyển event audit
    sang kho ghi bổ sung/append-only
~~~

Trong database, một audit event tối thiểu có thể chứa:

| Trường | Vai trò | Lưu ý riêng tư |
| --- | --- | --- |
| `auditId` | Khóa duy nhất để tránh event audit trùng. | Không tái sử dụng sau khi xóa dữ liệu nghiệp vụ. |
| `requestId` | Liên kết một yêu cầu API với log/tracing. | Không được chứa token hoặc PII tùy ý. |
| `actorRef` | Định danh người dùng/service đã xác thực. | Có thể là mã giả danh; giới hạn người tra cứu ánh xạ. |
| `action` | Mã hành động ổn định. | Dùng enum/code, tránh mô tả chứa nội dung người dùng. |
| `targetType` / `targetRef` | Loại và mã đối tượng bị tác động. | Có thể nhạy cảm nếu định danh nội bộ dễ liên kết. |
| `tenantRef` | Phạm vi dữ liệu, hỗ trợ điều tra. | Kiểm soát log theo tenant. |
| `result` | Hành động đã áp dụng hay không. | Event trong cùng transaction chỉ mô tả thành công sau commit; lỗi phải có luồng khác. |
| `occurredAt` | Thời điểm ghi sự kiện. | Kiểm tra UTC/timezone và lệch đồng hồ. |
| `fieldsChanged` | Danh sách **tên trường** đổi. | Không chứa giá trị email/phone cũ và mới. |

### 9.1. Constraint và truy vấn ghi cùng transaction

Chỉ chạy ví dụ trên **database thực hành** có quyền thay đổi schema; không dùng mã khách hàng thật:

~~~cypher
CREATE CONSTRAINT sec_demo_audit_id IF NOT EXISTS
FOR (a:SecDemoAuditEvent)
REQUIRE a.auditId IS UNIQUE;
~~~

Một câu lệnh Cypher cập nhật tên hiển thị và tạo audit event:

~~~cypher
MATCH (c:SecDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
SET c.displayName = $newDisplayName
CREATE (a:SecDemoAuditEvent {
  auditId: $auditId,
  requestId: $requestId,
  actorRef: $actorRef,
  action: 'CUSTOMER_DISPLAY_NAME_CHANGED',
  targetType: 'CUSTOMER',
  targetRef: $customerId,
  tenantRef: $tenantId,
  result: 'APPLIED',
  fieldsChanged: ['displayName'],
  occurredAt: datetime()
})
RETURN c.customerId AS customerId,
       a.auditId AS auditId;
~~~

**Điều kiện bắt buộc:**

1. API đã xác thực actor, kiểm quyền thay đổi khách hàng và xác nhận tenant từ security context trước khi chạy query; không lấy `actorRef` tùy ý từ client.
2. `$auditId` và `$requestId` do hệ thống quản lý/kiểm tra; không chứa bí mật. Với retry, service cần chính sách idempotency theo mã hành động để tránh thực hiện nghiệp vụ lặp.
3. `MATCH` có thể không khớp: khi đó **cả cập nhật và CREATE đều không chạy**, query trả 0 hàng. Service phải xem 0 hàng là không thành công, không tự báo đã cập nhật.
4. Nếu lỗi ở bước tạo audit event hoặc constraint, toàn bộ ghi trong transaction sẽ rollback. Nếu chạy các phần trong những transaction tự commit riêng, không còn bảo đảm này.
5. Ví dụ ghi giá trị mới vào node nghiệp vụ nhưng **không ghi giá trị nhạy cảm vào audit event**. Khi audit bắt buộc lưu bản trước/sau, cần cơ chế kiểm soát riêng.

Khi tích hợp Java Driver:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerAuditService {
    private final Driver driver;

    public CustomerAuditService(Driver driver) {
        this.driver = driver;
    }

    public String changeDisplayName(
            String tenantId, String customerId,
            String newName, String actorRef,
            String requestId, String auditId) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx -> {
                Record row = tx.run("""
                    MATCH (c:SecDemoCustomer {
                      tenantId: $tenantId,
                      customerId: $customerId
                    })
                    SET c.displayName = $newName
                    CREATE (a:SecDemoAuditEvent {
                      auditId: $auditId,
                      requestId: $requestId,
                      actorRef: $actorRef,
                      action: 'CUSTOMER_DISPLAY_NAME_CHANGED',
                      targetType: 'CUSTOMER',
                      targetRef: $customerId,
                      tenantRef: $tenantId,
                      result: 'APPLIED',
                      fieldsChanged: ['displayName'],
                      occurredAt: datetime()
                    })
                    RETURN a.auditId AS auditId
                    """, Map.of(
                    "tenantId", tenantId,
                    "customerId", customerId,
                    "newName", newName,
                    "actorRef", actorRef,
                    "requestId", requestId,
                    "auditId", auditId
                )).single();
                return row.get("auditId").asString();
            });
        }
    }
}
~~~

Đây là **mã minh họa tầng persistence**, không phải một endpoint an toàn hoàn chỉnh: phải thực hiện authorization, validation, xử lý exception, rate limit và idempotency trước khi cho người dùng gọi. `Map.of` không nhận giá trị null; ứng dụng phải validate đầy đủ đầu vào. `executeWrite` có thể retry callback khi lỗi transient phù hợp, nên **không gửi email, gọi API ngoài hoặc ack queue bên trong callback**.

**Giới hạn trung thực:** ghi audit node trong cùng Neo4j transaction bảo đảm hành động và audit node được commit/rollback cùng nhau, nhưng người có quyền quản trị cao vẫn có thể sửa/xóa audit node. Nếu cần bằng chứng khó bị sửa, hãy chuyển ra kho audit độc lập có chính sách append-only, retention, phân quyền tách biệt và cơ chế kiểm chứng toàn vẹn.

### 9.2. Audit các lần đọc nhạy cảm

Một lần `CUSTOMER_CONTACT_VIEWED` **không làm thay đổi node**, nên không thể dùng câu Cypher `SET` để tạo audit như ví dụ ghi. Có thể tạo event tại lớp service/API **sau khi đã kiểm tra quyền**, trước khi tiết lộ dữ liệu hoặc theo chính sách bền vững phù hợp.

Điểm cần quyết định trong thiết kế:

- Nếu audit writer lỗi, yêu cầu đọc dữ liệu nhạy cảm **bị từ chối (fail closed)** hay được phép tiếp tục và chấp nhận thiếu log? Với dữ liệu rủi ro cao, thường cần cơ chế bền vững/fail closed rõ ràng.
- Nếu ghi audit trước rồi truy vấn dữ liệu thất bại, outcome phải phản ánh rằng **không thực sự trả dữ liệu**.
- Nếu ghi audit sau khi đã trả response, có cửa sổ mất bằng chứng khi service chết giữa hai bước.
- Một job xuất dữ liệu hàng loạt cần audit thông tin *export initiated/completed*, số lượng và nơi nhận (theo mã tham chiếu), không chỉ log một câu query.

Không có một cơ chế duy nhất tự bảo đảm “mỗi lần đọc được ghi chính xác một lần” xuyên Neo4j, HTTP response và hệ thống log bên ngoài nếu chưa thiết kế giao thức phù hợp. Hãy định nghĩa mức đảm bảo theo yêu cầu nghiệp vụ.

### 9.3. Audit các trường hợp thất bại và bị từ chối

Audit event nằm trong transaction nghiệp vụ **sẽ rollback** nếu chính transaction đó thất bại. Điều đó đúng cho tính nguyên tử của **sự kiện đã áp dụng**, nhưng không lưu được dấu vết cố gắng truy cập bị từ chối.

Các trường hợp `DENIED` / `FAILED` nên được ghi qua đường bảo mật/ứng dụng riêng có quyền phù hợp, ví dụ:

~~~json
{
  "eventId": "audit-attempt-007",
  "requestId": "req-204",
  "actorRef": "actor-17",
  "tenantRef": "tenant-demo",
  "action": "CUSTOMER_CONTACT_VIEWED",
  "targetRef": "customer-51",
  "outcome": "DENIED",
  "reasonCode": "INSUFFICIENT_PERMISSION",
  "occurredAt": "2026-11-25T08:05:00Z"
}
~~~

Mọi giá trị trên là **giả lập**. Không ghi password, session token, số định danh thật hay toàn bộ hồ sơ vào event. `reasonCode` nên là mã chuẩn; thông báo exception thô có thể chứa PII hoặc dữ liệu kỹ thuật nhạy cảm.

## 10. Đảm bảo dấu vết khi có sự cố, retry và backup

### 10.1. Mất kết nối ngay lúc commit

Nếu Java Driver mất phản hồi ngay lúc transaction Neo4j commit, phía client có thể không biết chắc transaction đã lưu hay chưa. Không được mặc định rollback rồi chạy lại một side effect không idempotent.

Sử dụng `auditId` / mã yêu cầu ổn định, kiểm tra trạng thái đã lưu và quy tắc nghiệp vụ trước khi retry. Unique constraint cho `auditId` có thể ngăn tạo hai audit node cùng mã, nhưng **bản thân nó không tự đủ** để bảo đảm mọi thay đổi nghiệp vụ khác idempotent. Với operation có tính cộng/trừ số dư hoặc gửi dữ liệu ra ngoài, cần cơ chế riêng.

### 10.2. Log rotation, thời gian lưu và việc mất log

| Rủi ro | Biện pháp |
| --- | --- |
| Ổ đĩa đầy vì quá nhiều query/security log. | Rotation, retention, alert dung lượng và forwarding theo chính sách. |
| Rotation xóa quá sớm log đang cần điều tra. | Xác định thời hạn lưu, dung lượng, nguồn lưu trung tâm và yêu cầu pháp lý phù hợp. |
| Collector bị ngắt, mất các dòng log ở nguồn. | Giám sát lag, lỗi forwarding, retry có giới hạn và phát hiện khoảng thời gian thiếu. |
| Log trên cùng server bị xóa cùng database. | Đưa log trọng yếu tới nơi lưu độc lập, quyền riêng và backup hợp lệ. |
| Kẻ có đặc quyền sửa log hoặc clock. | Tách quyền, đồng bộ giờ, bảo vệ kho lưu và cân nhắc dấu vết bất biến/hash/signature. |
| Log làm lộ dữ liệu khi trích xuất hỗ trợ. | Redact trước khi chia sẻ, kiểm quyền export, mã hóa gói và theo dõi người nhận. |

Log mặc định có thể dùng cơ chế ghi có bộ đệm để tăng hiệu suất; với crash đột ngột, **không bảo đảm mọi dòng log cuối đã kịp ghi ra đĩa**. Những yêu cầu kiểm toán nghiêm ngặt cần lựa chọn hạ tầng ghi bền vững phù hợp, không chỉ bật logging rồi tuyên bố dữ liệu không thể mất.

### 10.3. Transaction log không phải nhật ký kiểm toán đọc

Neo4j có log giao dịch phục vụ phục hồi, sao chép và quản lý trạng thái database. Nó không nên bị coi là một bản báo cáo nghiệp vụ cho biết từng nhân viên đã xem field nào. Bảo vệ transaction logs và backups như **dữ liệu nhạy cảm**, vì chúng có thể chứa nội dung từ các thao tác ghi.

Khi backup/restore, cần kiểm tra cả:

- Quyền truy cập file backup, vị trí lưu, khóa mã hóa và vòng đời xóa.
- Khoảng thời gian log/audit cần giữ trước và sau restore.
- Tính liên tục của event ID, request ID và watermark chuyển log.
- Khả năng phát sinh log khác biệt sau restore hoặc replay; không tự nhân đôi sự kiện nghiệp vụ.

## 11. Liên hệ với Spring Data Neo4j và API GraphQL/REST

Khi Neo4j được truy cập qua **Spring Data Neo4j**, cần nhìn cả hai lớp:

~~~text
User -> API authentication/authorization
            |
            v
    Business service (@Transactional)
            |
       +----+----+
       |         |
       v         v
   Neo4j query  Audit event / outbox
       |
       v
Neo4j security/query logs (nếu được hỗ trợ)
~~~

Repository `findById()` hoặc GraphQL resolver không tự hiểu người dùng cuối, loại dữ liệu có quyền xem và audit theo yêu cầu riêng. Chúng có thể chạy với **một service account** có quyền lớn; nếu backend quên kiểm tra tenant thì cả quyền ở DB lẫn log có thể không ngăn được truy cập không hợp lệ.

Ví dụ luồng đọc nhạy cảm nên:

1. Xác thực user và lấy tenant/scope từ identity đã được kiểm chứng.
2. Kiểm tra user có quyền `CUSTOMER_CONTACT_READ` cho mục tiêu cụ thể.
3. Chỉ chọn property cần dùng trong Cypher/projection DTO; không tự trả toàn bộ entity.
4. Ghi audit event theo chính sách (có thể yêu cầu bền vững trước khi trả dữ liệu).
5. Trả response đã lọc; không log response body hoặc token.
6. Gắn request ID/trace ID để điều tra mà không chèn PII vào metadata.

Nếu có GraphQL, chặn các field nhạy cảm ở **field resolver** và đường đi liên quan, không dựa chỉ vào UI ẩn field. Một query có alias hoặc nhiều nhánh vẫn có thể cố đọc cùng trường; authorization cần được áp dụng nhất quán ở mọi đường fetch.

**Đối với quyền ghi:** dùng `@Transactional` ở service đúng transaction manager. Mọi thay đổi và audit event cùng một transaction sẽ rollback khi chưa commit; log ngoại vi qua SLF4J không tự rollback và không nên dùng để khẳng định thao tác đã commit thành công.

## 12. Kiểm thử bảo mật và nhật ký trên môi trường riêng

Một bộ kiểm thử cần xác minh cả **đúng quyền và đúng bằng chứng**, không chỉ sự tồn tại của file log.

| ID | Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- | --- |
| S01 | Đăng nhập hợp lệ vào self-managed Neo4j hỗ trợ security log. | Có dấu vết theo cấu hình log đã bật, người dùng được xác định đúng. |
| S02 | Đăng nhập thất bại. | Sự kiện thất bại được ghi và phân loại; không lộ password. |
| S03 | Một role không có quyền đọc `email`. | Truy vấn/API không trả `email`; test với đúng role thực tế. |
| S04 | User tenant A yêu cầu dữ liệu tenant B. | Bị chặn ở authorization; không lộ node, property hoặc relationship. |
| S05 | Query dùng literal chứa giá trị thử nhạy cảm. | Kiểm tra query log thực tế có áp dụng che literal đúng kỳ vọng. |
| S06 | Query dùng `$email` là tham số thử. | Khi parameter logging tắt, giá trị thử không xuất hiện trong `query.log`. |
| S07 | Query sinh lỗi chứa thông tin nhạy cảm. | Lỗi trả client và query log được hạn chế; xác minh riêng setting hỗ trợ che lỗi. |
| S08 | Thành công cập nhật thông tin khách hàng. | Node và audit node cùng commit; `auditId`/actor/action đúng, không chứa PII dư thừa. |
| S09 | Lỗi sau khi cập nhật node nhưng trước tạo audit node. | Transaction rollback; không có thay đổi được commit một phần. |
| S10 | API từ chối đọc hồ sơ. | Có sự kiện `DENIED` qua luồng audit phù hợp, không trả dữ liệu. |
| S11 | Mất kết nối đúng lúc commit. | Có thể hòa giải theo event ID/mã yêu cầu; không tạo audit hoặc bút toán trùng. |
| S12 | Rotation, collector ngắt kết nối hoặc disk gần đầy. | Có cảnh báo, log còn trong phạm vi retention đã cam kết hoặc sự cố mất log được phát hiện. |
| S13 | Đổi role/quyền trên database `system`. | Với edition/cấu hình hỗ trợ, sự kiện quản trị được ghi đúng và có người chịu trách nhiệm. |
| S14 | Cố truy cập trực tiếp Neo4j ngoài API. | Network/authn/authz chặn đường không được phép; không bỏ qua backend policy. |
| S15 | Restore database từ backup thử. | Kiểm tra tính liên tục audit, phân loại gap và không tự khai báo “đầy đủ” khi chưa kiểm chứng. |

### 12.1. Test không rò rỉ dữ liệu vào log

Với **giá trị giả** được tạo riêng cho test, ví dụ `TEST-SENSITIVE-MARKER-DO-NOT-USE`:

1. Thực thi một query tham số hóa dùng marker làm giá trị thử.
2. Gây một lỗi có kiểm soát để kiểm tra log lỗi và response.
3. Trích xuất log tương ứng từ **kho test có quyền phù hợp**, không phải nơi chứa dữ liệu thật.
4. Xác nhận marker **không xuất hiện** ở query log, log ứng dụng, HTTP log, trace hoặc thông báo lỗi mà chính sách yêu cầu che.
5. Kiểm tra các event hợp lệ vẫn có metadata cần điều tra: actor, action, request ID, thời gian.

Kiểm thử “không thấy marker” phải đọc **đúng cửa sổ thời gian** và kiểm tra rằng luồng log thật sự được bật/collector nhận đủ dữ liệu. Nếu test không tìm thấy bất kỳ dòng log nào vì collector đang chết, đó là lỗi observability chứ không phải thành công của cơ chế che dữ liệu.

### 12.2. Kiểm tra audit node không chứa PII

~~~cypher
MATCH (a:SecDemoAuditEvent {auditId: $auditId})
RETURN a.auditId AS auditId,
       a.action AS action,
       a.result AS result,
       a.fieldsChanged AS fieldsChanged,
       a.occurredAt AS occurredAt;
~~~

Đối chiếu thêm danh sách property thật trên audit node và schema audit đã phê duyệt: không nên có `newEmail`, `oldPhone`, `accessToken` hay nguyên vẹn `requestBody`. Nếu hệ thống lưu PII trong event vì yêu cầu đặc biệt, phải có giải thích, quyền và retention riêng.

### 12.3. Kiểm thử vai trò kết hợp và quyền quản trị

Một user có thể có nhiều role. Test ít nhất:

- Chỉ role đọc thông tin cơ bản.
- Role có quyền đọc thông tin liên hệ.
- Một user được gán nhiều role.
- User không có quyền `TRAVERSE` nhưng có một số `READ` property.
- Tài khoản service dùng để chạy batch, export và ghi audit.
- Admin có quyền thay role và người chịu trách nhiệm quản lý log.

Đừng chỉ kiểm `SHOW ROLE ... PRIVILEGES`; thực hiện query với **chính tài khoản/role thử nghiệm**, kiểm tra kết quả hiển thị và response API.

## 13. Xử lý một sự cố lộ dữ liệu hoặc thiếu audit

Khi có dấu hiệu dữ liệu nhạy cảm xuất hiện trong query log hoặc nghi ngờ log bị chỉnh sửa:

1. **Cô lập và giữ bằng chứng:** hạn chế quyền đến log/file/export liên quan, giữ trạng thái hiện tại và timestamp; không xóa log ngay vì có thể phá hủy dấu vết điều tra.
2. **Ngăn phát sinh thêm dữ liệu nhạy cảm:** chỉnh query/parameter logging, cấu hình che lỗi và các logger ứng dụng theo quy trình thay đổi; bảo đảm không ảnh hưởng điều tra đang thực hiện.
3. **Xác định phạm vi:** thời gian, tenant, loại field, server/instance, log collector, bản sao export, ai có quyền đọc tệp.
4. **Kiểm tra truy cập và hành động thực tế:** đối chiếu security log, query log, audit ứng dụng, gateway/IdP và log hạ tầng; chú ý các khoảng trống.
5. **Đánh giá xoay vòng bí mật:** nếu password/token/key bị lộ, dùng quy trình rotate/revoke phù hợp và giám sát sử dụng bất thường.
6. **Khắc phục nguyên nhân:** sửa field projection, hạn chế quyền, thay pipeline log hoặc chế độ debug; thêm regression test.
7. **Báo cáo và lưu hồ sơ:** theo quy trình incident response, chính sách riêng tư và nghĩa vụ pháp lý/hợp đồng phù hợp.

Nếu nhận thấy audit log có một khoảng trống, không tự ghi bổ sung các event với timestamp cũ rồi trình bày như dữ liệu gốc. Phải phân biệt **bằng chứng gốc**, **thông tin tái dựng** và **điều không thể xác minh**.

### 13.1. Cẩn trọng với thay đổi logging trong lúc sự cố

Một số setting Neo4j có thể thay đổi động; số khác đòi restart hoặc quyền quản trị, và trong cluster mỗi server có cấu hình riêng. Một thay đổi chỉ áp dụng trên một thành viên có thể để lại lỗ hổng trên thành viên khác. Trước khi kết luận đã khắc phục, xác nhận hiệu lực trên **mọi instance có thể nhận request** và kiểm tra sau restart/deploy.

## 14. Lỗi hiểu nhầm thường gặp

| Nhận định sai | Thực tế cần nhớ |
| --- | --- |
| “Bật `security.log` là biết mọi người đã xem node nào.” | Security log chủ yếu ghi sự kiện auth/authorization/admin được hỗ trợ, không tự ghi mọi lần đọc dữ liệu nghiệp vụ. |
| “Có `query.log` là có audit đủ cho tuân thủ.” | Query log có thể chỉ ghi theo ngưỡng/chế độ, không chứa đầy đủ actor cuối, kết quả trả về hay ý nghĩa hành động. |
| “Dùng parameter là log không có PII.” | Query parameter có thể được ghi nếu bật parameter logging; ứng dụng cũng có thể log giá trị riêng. |
| “Bật che literal là chắc chắn không lộ gì.” | Giá trị parameter, metadata, thông báo lỗi và log khác cần kiểm soát độc lập. |
| “Tắt introspection hoặc giấu field ở giao diện là bảo mật.” | Backend/database vẫn phải xác thực quyền đọc property, node và relationship. |
| “Chỉ cần mã hóa đĩa là đủ.” | Quyền đọc, truyền tải, log, export, backup và cấu trúc quan hệ vẫn có thể lộ dữ liệu. |
| “Tài khoản service có quyền rộng nhưng API có login nên an toàn.” | Một đường API bỏ lọc tenant hoặc truy cập trực tiếp DB có thể lộ dữ liệu hàng loạt. |
| “Ghi audit node cùng database là bất biến.” | Người có quyền sửa/xóa database có thể can thiệp; cần bảo vệ/đẩy log tới kho độc lập nếu yêu cầu. |
| “Đã log thành công trước commit nên nghiệp vụ thành công.” | Transaction có thể rollback sau đó; outcome audit phải phản ánh đúng thời điểm và ranh giới commit. |
| “Audit mọi lần đọc chỉ cần thêm một câu INSERT.” | Ghi sự kiện, trả response và khả năng lỗi nằm ở các hệ thống/ranh giới khác nhau; cần thiết kế mức bảo đảm. |
| “Một rule DENY là đủ cho mọi tenant.” | Cần kiểm thử các role kết hợp, trường null/missing, rule dựa trên property và mọi đường truy cập. |
| “Xóa file log có PII là hết rủi ro.” | Có thể còn bản sao, bản backup, SIEM, export; xóa vội có thể phá hủy bằng chứng sự cố. |

## 15. Bài tập thực hành

**Bài 1 — Phân loại log.** Một tài khoản Neo4j `svc-api` phục vụ 10.000 người dùng cuối. Hãy xác định dữ liệu nào có thể xuất hiện trong `security.log` và `query.log`, dữ liệu nào cần audit từ API để chứng minh người dùng cuối đã xem hồ sơ nhạy cảm. Giải thích vì sao không thể suy ra actor cuối chỉ từ username của service.

**Bài 2 — Cấu hình query log.** Dùng một môi trường test với bản Neo4j hỗ trợ logging. Thiết kế cấu hình giới hạn log query chậm, tắt ghi parameter và che literal; thử một giá trị marker giả, sau đó xác minh marker không xuất hiện trong query log và error log. Ghi lại phiên bản Neo4j, edition, các setting thật sự khả dụng và bằng chứng kiểm thử.

**Bài 3 — Chọn quyền tối thiểu.** Có role chỉ đọc tên hiển thị khách hàng nhưng không được thấy email, phone, nationalId. Viết chiến lược quyền database khi được hỗ trợ; bổ sung phương án ở API khi Community không có quyền property tương ứng. Thiết kế test với tài khoản được gán nhiều role.

**Bài 4 — Kiểm toán cập nhật.** Tạo `SecDemoCustomer` giả và triển khai giao dịch cập nhật `displayName` kèm `SecDemoAuditEvent`. Cố ý gây lỗi giữa transaction, chứng minh không có update dở dang, rồi chạy thành công và kiểm tra event chứa `actorRef`/`action`/`requestId` mà không chứa giá trị nhạy cảm.

**Bài 5 — Audit đọc và fail closed.** Hệ thống bắt buộc ghi bằng chứng trước khi trả số điện thoại khách hàng. Hãy thiết kế các tình huống audit writer chậm, không kết nối được, service chết sau audit nhưng trước response, service chết sau response nhưng trước xác nhận audit. Nêu chính sách nghiệp vụ cho từng trường hợp và giới hạn có thể bảo đảm.

**Bài 6 — Graph đa tenant.** Một node khách hàng thuộc tenant T1 có relationship nối sai sang node đơn hàng của T2. Hãy thiết kế truy vấn API và test xác minh T1 không thể nhìn thấy dữ liệu/quan hệ của T2 dù điểm bắt đầu thuộc tenant T1.

**Bài 7 — Sự cố lộ log.** Một kỹ sư bật query logging `VERBOSE` kèm parameter values trong một ngày; log chứa email khách hàng giả trong môi trường test. Viết runbook: khoanh vùng, đổi cấu hình, kiểm tra collector và bản sao, xác nhận quyền đọc log, xoay vòng secret nếu cần và lưu bằng chứng.

**Bài 8 — Kiểm toán theo edition.** So sánh một deployment Community tự quản lý, Enterprise tự quản lý và một gói Aura được cung cấp cho nhóm. Với từng môi trường, lập danh sách khả năng kiểm toán/ủy quyền có thể **xác minh thật**, khoảng trống phải giải quyết ở API hoặc hạ tầng, và các thông tin không thể khẳng định nếu thiếu quyền/phiên bản.

## 16. Checklist trước khi vận hành

1. **Biết dữ liệu:** đã phân loại node, relationship, thuộc tính và metadata nhạy cảm; không chỉ bảo vệ một vài cột PII?
2. **Biết sản phẩm:** đã xác minh edition, gói Aura/self-managed, phiên bản và các tính năng logging/ủy quyền thật sự hỗ trợ?
3. **Quyền tối thiểu:** mỗi service/user chỉ có database, node, relationship, property và quyền quản trị cần thiết?
4. **Ranh giới tenant:** mọi điểm bắt đầu, nhánh mở rộng, aggregate và đường xuất dữ liệu đã được kiểm thử chống truy cập chéo?
5. **Không lộ vào log:** query parameters, literals, error details, request body, response, tracing và debug logs đã được kiểm tra?
6. **Có audit nghiệp vụ:** xác định actor cuối, action, target, outcome và thời gian, không chỉ username service?
7. **Gắn đúng transaction:** ghi thay đổi và sự kiện đã áp dụng cùng commit/rollback; audit thất bại/từ chối có luồng riêng?
8. **Chống giả mạo:** quyền đến log tách biệt, collector có cảnh báo, có nơi lưu bền vững và cơ chế integrity phù hợp?
9. **Mã hóa:** đường truyền, volume/backup, file export và secret management đáp ứng chính sách?
10. **Quản lý vòng đời:** retention, rotation, quyền export/xóa, phương án xử lý data subject request và backup nhất quán?
11. **Kiểm thử sự cố:** đã thử mất log, rollback, retry commit không xác định, quyền chồng lấn và lỗi chuyển log?
12. **Có bằng chứng:** dashboard/alert, runbook, owner, correlation ID và khả năng truy vết sự kiện khi điều tra?

**Kết luận:** bảo mật Neo4j không dừng ở việc có `security.log` hay `query.log`. Log của database hữu ích để quan sát **xác thực, quản trị và truy vấn** theo khả năng sản phẩm, còn **kiểm toán hành động nghiệp vụ của người dùng cuối** thường phải được thiết kế ở ứng dụng. Đồng thời phải bảo vệ dữ liệu nhạy cảm trong node, relationship, query text, parameter, lỗi, log, backup và bản xuất. Hãy sử dụng đúng tính năng **khi được edition/phiên bản hỗ trợ**, cấp quyền tối thiểu, kiểm chứng cấu hình trên môi trường thử và xây audit trail có ranh giới transaction rõ ràng.

## Tài liệu tham khảo

- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/): phạm vi security/query logs, cấu hình logging, che literal/parameter và định dạng log.
- [Neo4j Operations Manual — Authentication and authorization](https://neo4j.com/docs/operations-manual/current/authentication-authorization/): role, privilege và các giới hạn theo edition.
- [Neo4j Operations Manual — Read privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/privileges-reads/): cấp quyền truy cập property và traversal.
- [Neo4j Operations Manual — Property-based access control](https://neo4j.com/docs/operations-manual/current/authentication-authorization/property-based-access-control/): điều kiện quyền theo property và các trường hợp giới hạn.
- [Neo4j Operations Manual — Security checklist](https://neo4j.com/docs/operations-manual/current/security/checklist/): bảo vệ kết nối, file, backup và hạ tầng.
- [Neo4j Aura — Activity feed](https://neo4j.com/docs/aura/logging/activity-feed/) và [Download logs](https://neo4j.com/docs/aura/logging/log-downloads/): chức năng quan sát/xuất log theo gói dịch vụ được hỗ trợ.
