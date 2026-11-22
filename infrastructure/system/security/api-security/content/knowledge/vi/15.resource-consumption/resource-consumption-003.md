# Rate limit theo IP, identity, API key và tenant

## 1. Rate limit bảo vệ API như thế nào?

Rate limit giới hạn số lượng request hoặc mức tiêu thụ tài nguyên trong một khoảng thời gian. Mục tiêu là giữ cho API phục vụ được người dùng hợp lệ, ngăn một caller chiếm phần lớn tài nguyên, kiểm soát chi phí và giảm tác động của hành vi lạm dụng.

Một API có thể bị quá tải dù mọi request đều có token hợp lệ. Một client có quyền đọc báo cáo vẫn có thể gửi hàng nghìn truy vấn tốn CPU; một API key bị lộ có thể được dùng để gọi export liên tục; một tenant có thể tạo tải lớn làm ảnh hưởng tenant khác. Xác thực cho biết caller là ai, còn rate limit kiểm soát caller được tiêu thụ bao nhiêu tài nguyên trong một khoảng thời gian.

Trong phạm vi **SECURITY_API_SECURITY**, rate limit cần gắn với từng endpoint, loại hành động và chi phí xử lý. Không nên áp dụng một con số giống nhau cho mọi request hoặc chỉ giới hạn theo địa chỉ IP. Một chính sách thực tế thường kết hợp nhiều chiều:

- **IP/network:** hạn chế lưu lượng từ một địa chỉ hoặc mạng nguồn, hữu ích cho request chưa xác thực và tín hiệu chống bot.
- **Authenticated identity:** giới hạn theo user principal hoặc service principal đã xác minh.
- **API key/client:** giới hạn theo credential hoặc ứng dụng tích hợp đã đăng ký.
- **Tenant:** giới hạn tổng mức sử dụng của một tổ chức để bảo vệ tính công bằng giữa các tenant.

Các chiều này bổ sung cho nhau. Một request có thể đồng thời tiêu thụ ngân sách IP, identity, API key và tenant. Nếu chỉ dùng một chiều, attacker có thể chuyển sang chiều khác để né giới hạn hoặc một caller dùng chung hạ tầng có thể làm ảnh hưởng nhiều người dùng.

Sau bài học này, người học có thể:

1. Phân biệt rate limit theo IP, identity, API key và tenant.
2. Chọn đúng nguồn dữ liệu tin cậy để tạo rate-limit key.
3. Thiết kế chính sách nhiều tầng theo endpoint, chi phí và mức rủi ro.
4. Chọn thuật toán giới hạn phù hợp với burst, lưu lượng và kiến trúc phân tán.
5. Trả lỗi 429 nhất quán và giúp client retry đúng cách.
6. Kiểm thử khả năng bypass, fairness, concurrency và giám sát hiệu quả rate limit.

## 2. Vì sao cần giới hạn theo nhiều chiều?

Mỗi chiều có điểm mạnh và điểm yếu riêng.

| Chiều giới hạn | Ưu điểm | Điểm yếu nếu dùng riêng |
|---|---|---|
| IP/network | Có thể áp dụng trước authentication; hữu ích cho anonymous traffic và chống request flood | Nhiều người dùng có thể chung NAT/proxy; IP thay đổi hoặc phân tán; không đại diện chắc chắn cho danh tính |
| User/service identity | Gắn với principal đã xác minh; chính sách gần với quyền và hành vi thực tế | Chỉ có sau authentication; một user có thể có nhiều phiên hoặc token; workload có thể gọi thay mặt nhiều user |
| API key | Phân biệt từng credential tích hợp; dễ thu hồi và theo dõi | Một client có thể có nhiều key; key có thể bị chia sẻ hoặc xoay vòng; key ID từ request chưa xác minh không đáng tin |
| Tenant | Bảo vệ tài nguyên dùng chung và giới hạn mức sử dụng theo tổ chức | Cần ánh xạ tenant đáng tin; tenant lớn có thể có nhu cầu cao hơn; một tenant có thể có nhiều client và user |

Ví dụ, một đối tác tích hợp có ba API key và chạy từ nhiều IP. Nếu chỉ giới hạn theo IP, đối tác có thể vượt quota bằng cách chuyển workload sang IP khác. Nếu chỉ giới hạn theo từng key, họ có thể tạo thêm key để chia nhỏ tải. Nếu chỉ giới hạn theo tenant, một workload lỗi có thể tiêu thụ hết ngân sách của tenant và ảnh hưởng các ứng dụng khác trong cùng tổ chức.

Vì vậy, một request đã xác thực có thể chịu đồng thời các giới hạn:

- IP/network: chống một nguồn gửi quá nhiều request.
- User hoặc service identity: giới hạn principal cụ thể.
- API key/client: giới hạn credential hoặc tích hợp.
- Tenant: giới hạn tổng mức sử dụng của tổ chức.
- Endpoint/operation: bảo vệ chức năng tốn tài nguyên.
- Global/system: bảo vệ năng lực tổng thể của dịch vụ.

Rate limit không thay thế authorization. Caller có quyền gọi endpoint vẫn có thể bị giới hạn tốc độ; caller còn quota vẫn phải được kiểm tra quyền trên object và tenant.

## 3. Phân biệt rate limit, quota, concurrency limit và cost limit

Các khái niệm này liên quan nhưng giải quyết những vấn đề khác nhau.

| Cơ chế | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| Rate limit | Số request hoặc đơn vị sử dụng trong một khoảng thời gian | 60 request/phút |
| Quota | Tổng mức sử dụng trong một chu kỳ dài hơn | 100.000 request/tháng |
| Concurrency limit | Số tác vụ đang chạy cùng lúc | Tối đa 5 export đồng thời |
| Cost/complexity limit | Chi phí ước lượng của một request | GraphQL query tối đa 500 complexity points |
| Payload limit | Kích thước dữ liệu đầu vào/đầu ra | Body tối đa 1 MB |
| Timeout/deadline | Thời gian tối đa một thao tác được phép chiếm tài nguyên | Request xử lý tối đa 3 giây |

Một API export có thể có rate limit 2 request/phút, concurrency limit 1 tác vụ, giới hạn tối đa 50.000 bản ghi mỗi lần và quota 20 lần export/ngày. Các giới hạn bảo vệ những nguồn tài nguyên khác nhau.

Nếu chỉ đặt rate limit, một request duy nhất có thể vẫn tiêu tốn quá nhiều CPU hoặc bộ nhớ. Nếu chỉ đặt concurrency limit, một caller có thể hoàn thành và khởi chạy liên tục hàng nghìn tác vụ. Thiết kế tốt kết hợp giới hạn số lần, số tác vụ đang chạy và chi phí của mỗi tác vụ.

## 4. Xác định đúng định danh cho từng chiều

### 4.1. IP và network source

IP nguồn có thể hữu ích khi request chưa được xác thực hoặc khi cần giới hạn theo nguồn mạng. Tuy nhiên, IP không phải danh tính người dùng.

Các trường hợp cần cân nhắc:

- Nhiều người dùng hợp lệ cùng đi qua NAT của công ty, trường học hoặc nhà mạng di động.
- Client dùng proxy, VPN, CDN hoặc mobile network nên IP thay đổi.
- IPv6 có thể tạo nhiều địa chỉ trong cùng một prefix.
- Botnet có thể phân tán request qua nhiều IP.
- Một IP public có thể đại diện cho nhiều workload phía sau gateway.

Với anonymous endpoint, giới hạn theo IP thường là lớp bảo vệ ban đầu. Với API đã xác thực, IP nên là một tín hiệu bổ sung hoặc một tầng bảo vệ rộng, không phải khóa duy nhất quyết định toàn bộ quota.

### 4.2. Authenticated identity

Identity phải được lấy từ authentication context đã xác minh, ví dụ:

- User principal được tạo từ access token/session hợp lệ.
- Service principal được xác minh qua OAuth client credentials, mTLS hoặc workload identity.
- Subject và actor được phân biệt nếu service gọi thay mặt người dùng.

Không tạo rate-limit key từ header tùy ý như `X-User-Id`, `X-Service-Name` hoặc `X-Authenticated-User` nếu các header đó chưa được trusted gateway xác minh và ghi đè. Caller có thể tự thay header để nhận một ngân sách mới.

Với luồng service gọi thay mặt user, có thể áp dụng cả hai giới hạn: theo service principal để bảo vệ năng lực backend, và theo user subject để ngăn một người dùng tiêu thụ quá mức thông qua service có quyền rộng.

### 4.3. API key và client

Sau khi xác minh API key, server có thể lấy `key_id` và `client_id` từ key record. Có thể áp dụng hai giới hạn:

- Theo key ID để phát hiện một credential cụ thể bị lạm dụng hoặc bị chia sẻ.
- Theo client ID để ngăn một ứng dụng vượt quota bằng cách tạo nhiều key.

Không dùng raw API key hoặc secret làm Redis key, metric label hay log field. Secret có thể rò rỉ qua hệ thống giám sát và làm tăng nguy cơ compromise. Key ID đã được xác minh là định danh phù hợp hơn.

Một key ID do request gửi lên trước khi xác minh chỉ là dữ liệu không tin cậy. Có thể dùng nó để phân tích format hoặc áp dụng một lớp chống flood sơ bộ, nhưng không cấp quota có lợi hoặc quyền truy cập dựa trên giá trị chưa xác minh.

### 4.4. Tenant

Tenant context phải được xác định từ danh tính và quan hệ đã xác minh, chẳng hạn:

- Tenant được gắn với service principal.
- Tenant membership đã được xác minh của user.
- Tenant binding trong API key record.
- Delegated token có audience/scope và tenant context hợp lệ.

Không tin `tenantId` do request body hoặc query parameter tự gửi. Nếu API cho phép user chọn tenant đang hoạt động, server phải xác minh user có membership và quyền trong tenant đó trước khi dùng tenant làm khóa quota.

Một user có thể thuộc nhiều tenant. Chính sách nên giới hạn theo tenant đang được xác minh trong request, đồng thời có thể áp dụng thêm user-level cap để một người không tạo tải quá lớn bằng cách chuyển tenant liên tục.

## 5. Lấy IP đúng khi API đứng sau proxy

### 5.1. Không tin X-Forwarded-For từ mọi nguồn

Khi API nằm sau CDN, load balancer hoặc reverse proxy, socket peer mà ứng dụng nhìn thấy có thể là IP của proxy. Hệ thống thường dùng `Forwarded`, `X-Forwarded-For` hoặc header riêng của nhà cung cấp để chuyển tiếp IP gốc.

Các header này có thể bị client giả mạo nếu ingress không xóa giá trị do client gửi hoặc ứng dụng đọc sai chuỗi proxy. Không nên đơn giản lấy phần tử đầu tiên của `X-Forwarded-For` rồi tin đó là IP thật.

Thiết kế an toàn cần:

1. Xác định các proxy/load balancer được tin cậy.
2. Cấu hình ingress xóa hoặc chuẩn hóa header forwarding do client gửi.
3. Proxy đáng tin ghi lại IP quan sát được và chuyển tiếp theo một quy ước thống nhất.
4. Ứng dụng chỉ xử lý forwarding header khi kết nối đến từ proxy được tin cậy.
5. Phân tích chuỗi proxy theo trust configuration, không theo vị trí cố định thiếu kiểm chứng.
6. Nếu không có proxy tin cậy, dùng remote address từ kết nối mạng.

### 5.2. Chuẩn hóa địa chỉ

Khi tạo khóa rate limit, cần chuẩn hóa IP để tránh một địa chỉ có nhiều biểu diễn:

- Parse thành kiểu địa chỉ IP, không chỉ xử lý chuỗi tùy ý.
- Chuẩn hóa IPv4 và IPv6.
- Xử lý IPv4-mapped IPv6 nhất quán.
- Quyết định có giới hạn theo địa chỉ đơn lẻ hay prefix IPv6.
- Không lưu địa chỉ đầy đủ lâu hơn nhu cầu nếu chính sách quyền riêng tư yêu cầu giảm dữ liệu.

Giới hạn theo IPv6 prefix có thể giảm việc né giới hạn bằng cách thay đổi địa chỉ trong cùng một mạng, nhưng có thể ảnh hưởng nhiều thiết bị hợp lệ. Chọn prefix cần dựa trên đặc điểm mạng, lưu lượng và dữ liệu quan sát.

### 5.3. Tránh chặn nhầm người dùng chung IP

Một văn phòng có hàng trăm nhân viên có thể cùng đi qua một NAT. Nếu chỉ cho phép 10 request/phút/IP, người dùng hợp lệ sẽ bị chặn cùng nhau.

Đối với API đã xác thực, nên kết hợp IP cap rộng hơn với identity, key và tenant cap. Với anonymous endpoint, có thể dùng ngưỡng IP riêng, nhưng cần có ngoại lệ hoặc cơ chế điều chỉnh khi traffic hợp lệ tập trung sau NAT.

## 6. Thiết kế chính sách theo endpoint và mức chi phí

Không nên dùng một giới hạn chung cho mọi operation. Trước tiên, phân loại endpoint theo chi phí, độ nhạy và tác động khi bị lạm dụng.

| Nhóm endpoint | Ví dụ | Chính sách tham khảo |
|---|---|---|
| Đọc đơn giản | Xem một object đã phân quyền | Ngưỡng tương đối cao, có object/identity cap |
| Tìm kiếm | Search, autocomplete, filter nhiều trường | Giới hạn theo identity/tenant, page size và query cost |
| Ghi dữ liệu | Tạo hoặc cập nhật object | Giới hạn theo identity/key/tenant và business invariant |
| Gửi thông báo | OTP, email, SMS, webhook trigger | Ngưỡng thấp hơn, quota theo người nhận và tenant |
| Export/report | Xuất dữ liệu lớn, tạo báo cáo | Rate limit thấp, concurrency cap, async queue và quota |
| Upload/process file | Upload, giải nén, xử lý ảnh | Giới hạn payload, số tác vụ và tài nguyên xử lý |
| Tác vụ tài chính | Hoàn tiền, thanh toán, chuyển tiền | Rate limit, velocity check, idempotency và policy nghiệp vụ |
| Endpoint xác thực | Login, token, API key validation | Chống brute force và credential stuffing theo IP/identity phù hợp |

Con số cụ thể phải dựa trên tải bình thường, năng lực hệ thống, SLA và chi phí mỗi operation. Không sao chép một ngưỡng ví dụ vào production mà không đo đạc.

### 6.1. Đặt ngưỡng theo burst và sustained rate

Một client có thể gửi một cụm request ngắn khi đồng bộ dữ liệu rồi hoạt động bình thường trong thời gian còn lại. Chính sách nên phân biệt:

- **Burst:** lượng request tăng ngắn hạn mà hệ thống có thể hấp thụ.
- **Sustained rate:** tốc độ trung bình trong một khoảng dài.
- **Daily/monthly quota:** tổng mức tiêu thụ trong chu kỳ.
- **Concurrency:** số công việc đang chạy đồng thời.

Ví dụ chính sách cho một client có thể cho phép burst 20 request, trung bình 5 request/giây và tối đa 100.000 request/ngày. Các con số chỉ minh họa cách diễn đạt policy; cần benchmark và xác nhận với chủ sở hữu API.

### 6.2. Cost-based limiting

Hai request cùng tính là một request nhưng chi phí có thể khác nhau. Ví dụ `GET /orders/123` đọc một bản ghi, trong khi `GET /orders?include=items,history,documents` tải nhiều quan hệ và thực hiện nhiều truy vấn.

Có thể gán cost unit cho operation hoặc đặc điểm request:

- Đọc object đơn giản: 1 unit.
- Tìm kiếm phức tạp: 5 units.
- Export: 100 units hoặc chuyển sang queue riêng.
- Truy vấn có nhiều nested relation: cost tăng theo số quan hệ.
- GraphQL: tính complexity theo field, depth, list multiplier và resolver cost.

Cost cần được tính ở server từ schema và query đã phân tích. Không tin client tự gửi `X-Request-Cost`. Giới hạn cost giúp bảo vệ tài nguyên tốt hơn việc chỉ đếm số request.

## 7. Chính sách nhiều tầng: IP, identity, API key và tenant

Một policy có thể biểu diễn bằng nhiều bucket độc lập. Ví dụ cho request đọc hóa đơn đã xác thực:

| Bucket | Khóa logic | Mục đích |
|---|---|---|
| IP | `ip:<normalized-address>` | Chặn flood từ một nguồn mạng |
| User | `user:<issuer>:<subject>` | Giới hạn hành vi của người dùng |
| Service | `service:<workload-id>` | Bảo vệ backend khỏi một workload |
| API key | `key:<verified-key-id>` | Giới hạn một credential |
| Client | `client:<client-id>` | Ngăn nhiều key cùng client chia nhỏ quota |
| Tenant | `tenant:<verified-tenant-id>` | Bảo vệ tổng tài nguyên tenant |
| Operation | `operation:<route-id>` | Bảo vệ endpoint tốn tài nguyên |
| Global | `global:<service>:<route-group>` | Bảo vệ năng lực toàn hệ thống |

Không nhất thiết mọi request đều dùng tất cả bucket. Anonymous request chưa có user, key hoặc tenant identity; request service-to-service có thể không có end-user. Policy engine chọn các bucket phù hợp với thông tin đã xác minh và loại operation.

### 7.1. Mô hình quyết định

Một request được chấp nhận khi mọi giới hạn bắt buộc đều còn ngân sách:

\[
Allow = IP_{ok} \land Identity_{ok} \land Key_{ok} \land Tenant_{ok} \land Operation_{ok}
\]

Nếu một bucket bắt buộc đã vượt ngưỡng, request bị từ chối. Không nên cho request đi tiếp chỉ vì các bucket khác còn quota.

Cần xác định rõ bucket nào là bắt buộc và bucket nào là tín hiệu bổ sung. Ví dụ, IP cap có thể dùng ngưỡng rộng để chống flood, còn tenant quota là giới hạn chính cho workload đã xác thực.

### 7.2. Thứ tự áp dụng

Một luồng tham khảo:

1. Ở edge/gateway, áp dụng giới hạn sơ bộ theo IP/network và kích thước request.
2. Xác thực credential.
3. Lấy user/service principal và API key/client record đã xác minh.
4. Xác định tenant context đáng tin cậy.
5. Chọn policy theo route, method và loại hành động.
6. Kiểm tra các bucket theo thứ tự phù hợp.
7. Nếu được phép, ghi nhận tiêu thụ quota và tiếp tục authorization nghiệp vụ.
8. Thực hiện xử lý và ghi metric/audit.

Thứ tự thực tế cần tránh cho attacker tạo chi phí lớn trước khi bị giới hạn. Các lớp edge có thể chặn sớm request flood; lớp ứng dụng sau authentication mới có đủ identity để áp dụng chính sách chính xác.

### 7.3. Giới hạn cả caller và người được đại diện

Nếu service gọi API thay mặt user, chỉ giới hạn theo service có thể khiến một user lạm dụng service có quyền rộng. Chỉ giới hạn theo user có thể để một service lỗi tạo quá nhiều request hệ thống không gắn với user.

Có thể áp dụng:

- Service cap cho tổng workload.
- Subject/user cap cho hành vi người dùng.
- Tenant cap cho tổng mức sử dụng tổ chức.
- Operation cap cho endpoint tốn tài nguyên.

Audit và metric cần phân biệt actor service với subject user để xác định bucket nào bị tiêu thụ.

## 8. Các thuật toán rate limiting

### 8.1. Fixed window counter

Chia thời gian thành các cửa sổ cố định, ví dụ mỗi phút. Mỗi khóa có một counter; khi request đến, tăng counter và từ chối nếu vượt ngưỡng.

Ưu điểm:

- Dễ triển khai.
- Ít bộ nhớ.
- Dễ giải thích và giám sát.

Nhược điểm là hiện tượng burst ở ranh giới cửa sổ. Nếu giới hạn 60 request/phút, caller có thể gửi 60 request ở cuối phút và 60 request ngay đầu phút tiếp theo, tạo 120 request trong thời gian rất ngắn.

Dùng fixed window khi tải đơn giản và hệ thống chấp nhận burst ở ranh giới, hoặc kết hợp với một limiter khác ở tầng edge.

### 8.2. Sliding window log

Lưu timestamp của từng request trong khoảng thời gian trượt. Khi request mới đến, xóa timestamp đã cũ, đếm số còn lại rồi quyết định.

Ưu điểm là chính xác theo cửa sổ trượt. Nhược điểm là cần lưu nhiều timestamp và thao tác có thể tốn bộ nhớ khi lưu lượng lớn.

Phù hợp với endpoint nhạy cảm, volume vừa phải hoặc khi cần giới hạn chính xác theo từng hành động.

### 8.3. Sliding window counter

Kết hợp counter của cửa sổ hiện tại và cửa sổ trước, ước lượng phần request còn nằm trong cửa sổ trượt dựa trên tỷ lệ thời gian.

Ưu điểm là giảm hiện tượng burst của fixed window mà không phải lưu timestamp từng request. Nhược điểm là kết quả là xấp xỉ, phụ thuộc cách tính và độ dài cửa sổ.

Phù hợp với nhiều API có lưu lượng lớn cần cân bằng độ chính xác và chi phí.

### 8.4. Token bucket

Bucket chứa tối đa một số token. Token được bổ sung theo tốc độ xác định; mỗi request tiêu thụ một hoặc nhiều token. Khi bucket không đủ token, request bị giới hạn.

Hai tham số chính:

- **Capacity:** số token tối đa, quyết định burst cho phép.
- **Refill rate:** tốc độ bổ sung token, quyết định sustained rate.

Ví dụ bucket capacity 30, refill 10 token/giây cho phép một burst tối đa 30 token nếu bucket đầy, sau đó trung bình được bổ sung 10 token mỗi giây.

Token bucket phù hợp với API cần cho phép burst ngắn nhưng vẫn kiểm soát tốc độ trung bình. Có thể tiêu thụ nhiều token cho operation có cost cao.

### 8.5. Leaky bucket và GCRA

Leaky bucket mô hình hóa hàng đợi được xử lý ở tốc độ cố định, giúp làm phẳng lưu lượng. Nó hữu ích khi muốn kiểm soát tốc độ đưa công việc vào hệ thống hoặc điều tiết downstream.

GCRA (Generic Cell Rate Algorithm) là một thuật toán kiểm soát tốc độ thường được dùng để triển khai hành vi gần với leaky bucket/token bucket bằng trạng thái nhỏ. Nó có thể biểu diễn dung sai burst và thời điểm request tiếp theo được phép.

Lựa chọn thuật toán phụ thuộc yêu cầu: token bucket dễ hiểu cho burst, fixed/sliding window dễ áp quota theo chu kỳ, leaky bucket/GCRA hữu ích cho shaping hoặc limiter hiệu quả.

### 8.6. So sánh nhanh

| Thuật toán | Độ chính xác cửa sổ | Hỗ trợ burst | Chi phí trạng thái | Trường hợp phù hợp |
|---|---|---|---|---|
| Fixed window | Thấp ở ranh giới | Có thể burst lớn tại ranh giới | Thấp | Giới hạn đơn giản |
| Sliding log | Cao | Theo ngưỡng chính xác | Cao | Endpoint nhạy cảm, volume vừa |
| Sliding counter | Xấp xỉ | Kiểm soát tốt hơn fixed | Thấp-vừa | API lưu lượng lớn |
| Token bucket | Theo refill/capacity | Có chủ đích | Thấp | API tương tác, burst ngắn |
| Leaky bucket/GCRA | Theo lịch xử lý | Có dung sai cấu hình | Thấp | Shaping và điều tiết downstream |

## 9. Giới hạn trong hệ thống phân tán

Một API thường chạy nhiều instance sau load balancer. Nếu mỗi instance có counter trong bộ nhớ riêng, caller có thể vượt giới hạn bằng cách phân phối request qua nhiều instance.

Ví dụ, policy cho phép 100 request/phút. Có 5 instance, mỗi instance đếm riêng và cho phép 100 request/phút; caller có thể đạt gần 500 request/phút nếu tải được phân phối đều.

### 9.1. Shared counter

Các lựa chọn phổ biến:

- Redis hoặc một kho key-value có thao tác atomic.
- API gateway có rate-limit store dùng chung.
- Rate-limit service chuyên dụng.
- Database counter cho quota dài hạn hoặc nghiệp vụ cần audit chặt.

Counter và thao tác kiểm tra/tiêu thụ cần được thực hiện nguyên tử. Nếu ứng dụng đọc counter, kiểm tra, rồi ghi tăng bằng nhiều lệnh riêng, nhiều request đồng thời có thể cùng thấy quota còn và đều được chấp nhận.

### 9.2. Atomicity và race condition

Với token bucket, việc đọc trạng thái, tính token được bổ sung, quyết định và cập nhật timestamp/counter phải là một thao tác logic nguyên tử. Với Redis, có thể dùng Lua script hoặc primitive atomic phù hợp. Không để nhiều application instance tự cập nhật các trường riêng rẽ.

Cần xử lý thời gian nhất quán. Dùng clock của kho trạng thái hoặc một nguồn thời gian được quản lý tốt để giảm sai lệch giữa node. Nếu clock lùi hoặc nhảy mạnh, limiter có thể cấp thêm token hoặc khóa nhầm caller.

### 9.3. TTL và dọn trạng thái

Các bucket theo IP, user, key hoặc tenant cần thời gian sống phù hợp. Nếu không có TTL, attacker có thể tạo vô số khóa và làm phình bộ nhớ. Nếu TTL quá ngắn, trạng thái bị xóa sớm và caller có thể reset quota.

Không tạo key cho mọi chuỗi tùy ý trước khi xác thực và giới hạn độ dài. Với identifier chưa xác minh, cần giới hạn cardinality và áp dụng edge protection.

### 9.4. Redis lỗi hoặc rate-limit store không khả dụng

Cần định nghĩa hành vi khi kho trạng thái bị lỗi:

- **Fail closed:** từ chối request nếu không thể xác minh quota. Bảo vệ tài nguyên tốt hơn nhưng có thể làm gián đoạn dịch vụ.
- **Fail open:** cho request đi qua khi limiter lỗi. Tăng khả năng sẵn sàng nhưng có thể mở cửa cho lạm dụng.
- **Degraded mode:** chuyển sang giới hạn cục bộ thấp hơn hoặc policy bảo vệ tối thiểu, đồng thời phát cảnh báo.

Không có lựa chọn đúng cho mọi endpoint. Endpoint tài chính, gửi OTP hoặc export tốn kém có thể cần fail closed hoặc degraded mode chặt. Endpoint đọc công khai có thể chấp nhận fail open trong một thời gian ngắn nếu có edge protection khác.

### 9.5. Hot key và partition

Tenant hoặc API key lớn có thể tạo một counter nóng, gây tranh chấp trên một partition. Có thể cần phân vùng trạng thái, local token allocation hoặc hierarchical quota. Nhưng chia counter thành nhiều phần có thể làm quota toàn cục bị vượt trong một khoảng thời gian; cần định lượng trade-off và giới hạn sai số.

## 10. Fairness giữa các tenant và workload

Trong hệ thống multi-tenant, một tenant có thể tiêu thụ tài nguyên dùng chung và làm giảm chất lượng dịch vụ của tenant khác. Rate limit cần hỗ trợ fairness chứ không chỉ chống attacker.

### 10.1. Hierarchical quota

Có thể kết hợp:

- Global capacity cho toàn service.
- Per-tenant quota cho mỗi tổ chức.
- Per-client quota cho từng tích hợp trong tenant.
- Per-key limit cho credential cụ thể.
- Per-user limit cho người dùng cuối.
- Per-operation limit cho endpoint hoặc nhóm tác vụ.

Tenant cap bảo vệ tổ chức khác khỏi noisy neighbor. Client cap giúp một integration lỗi không chiếm toàn bộ ngân sách tenant. Global cap bảo vệ hạ tầng khi tổng tải tăng bất thường.

### 10.2. Tier và quota theo hợp đồng

Một số sản phẩm có gói dịch vụ khác nhau. Có thể cấu hình quota theo tier, nhưng cần đảm bảo:

- Tier được xác định từ dữ liệu server đáng tin.
- Client không thể tự gửi plan=premium.
- Nâng/hạ tier có audit và thời điểm hiệu lực rõ.
- Quota không vượt năng lực hệ thống hoặc cam kết SLA.
- Các endpoint tốn kém có hạn mức riêng dù tenant thuộc tier cao.

Không để gói trả phí bỏ qua mọi kiểm soát bảo vệ hệ thống. Tier có thể thay đổi quota, nhưng không nên vô hiệu hóa giới hạn an toàn toàn cục.

### 10.3. Tránh một tenant làm cạn quota của tenant khác

Không dùng một counter chung cho mọi tenant nếu nghiệp vụ yêu cầu fairness. Nếu một tenant vượt ngưỡng, nên trả 429 cho tenant đó và vẫn phục vụ tenant khác khi global capacity còn.

Tuy nhiên, nếu hạ tầng thực sự đã cạn, global protection có thể phải giới hạn tất cả tenant. Khi đó cần ưu tiên theo SLA hoặc hàng đợi công bằng thay vì để tenant gửi nhanh nhất chiếm toàn bộ năng lực.

## 11. Xử lý các cách bypass rate limit

### 11.1. Đổi IP hoặc phân tán request

Attacker có thể dùng proxy, botnet, VPN hoặc nhiều mạng để né IP limit. Do đó, IP limit cần kết hợp identity, API key, client và tenant sau khi xác thực.

Với anonymous traffic, có thể bổ sung bot detection, challenge hoặc giới hạn theo network prefix, nhưng cần cân nhắc false positive và người dùng hợp lệ dùng chung mạng.

### 11.2. Tạo nhiều API key

Nếu chỉ giới hạn theo key ID, một client có thể tạo nhiều key để chia nhỏ quota. Cần thêm giới hạn theo client ID và tenant. Việc tạo key cũng cần authorization, quota số key, owner và audit.

### 11.3. Giả mạo user hoặc tenant header

Không lấy `X-User-Id`, `X-Tenant-Id` hoặc `X-Client-Id` do public caller gửi làm bucket chính. Dùng principal và tenant context đã xác minh. Trusted gateway phải xóa header spoofed trước khi thêm metadata nội bộ.

### 11.4. Thay đổi route hoặc method

Nếu limiter dùng raw URL string, attacker có thể thử các cách biểu diễn khác nhau như trailing slash, encoded path, method khác hoặc route alias. Nên gắn policy với route/operation ID đã được router xác định, đồng thời chuẩn hóa path và method.

### 11.5. Batch, GraphQL và nested request

Một request có thể chứa nhiều operation hoặc truy vấn phức tạp. Đếm một HTTP request là một đơn vị sẽ đánh giá thấp chi phí.

Cần giới hạn:

- Số item trong batch.
- Độ sâu và complexity của GraphQL query.
- Số resolver hoặc nested relation.
- Kích thước danh sách và page size.
- Tổng cost unit được tính ở server.
- Concurrency của tác vụ được khởi tạo từ request.

### 11.6. Retry và request amplification

Client retry ngay lập tức khi nhận lỗi có thể làm tải tăng thêm. Backend cũng có thể retry service phụ thuộc nhiều lần. Cần giới hạn retry, dùng exponential backoff với jitter, đặt deadline và tránh retry các lỗi không thể phục hồi.

Rate limit nên tính cả request retry nếu chúng tiêu thụ tài nguyên. Với thao tác ghi, dùng idempotency key để tránh một hành động logic bị thực hiện nhiều lần.

## 12. Phản hồi khi vượt giới hạn

Khi caller vượt rate limit, HTTP `429 Too Many Requests` là status code thường dùng. Response nên ổn định và không tiết lộ quá nhiều chi tiết nội bộ.

Ví dụ:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 12
RateLimit-Limit: 60
RateLimit-Remaining: 0
RateLimit-Reset: 12

{
  "code": "RATE_LIMITED",
  "message": "Request rate exceeded. Retry later.",
  "traceId": "trc-8f31"
}
```

Các trường `RateLimit-*` là ví dụ theo RateLimit Fields for HTTP (RFC 9333). Cần kiểm tra chuẩn và cách triển khai đang dùng trước khi phát hành; không tự ý thay đổi ý nghĩa các header. `Retry-After` có thể biểu diễn thời gian chờ hoặc ngày HTTP theo quy định.

Không nhất thiết phải tiết lộ bucket chính xác đã vượt nếu điều đó giúp attacker dò policy. Có thể trả thông báo chung và trace ID, trong khi log nội bộ ghi `limit_dimension`, policy ID và định danh đã được che phù hợp.

### 12.1. Client nên retry như thế nào?

Client cần:

- Tôn trọng `Retry-After` hoặc reset time được trả.
- Dùng exponential backoff và jitter khi không có thời gian retry cụ thể.
- Không retry liên tục ngay sau 429.
- Giảm concurrency hoặc batch size nếu endpoint đang quá tải.
- Giữ idempotency key cho thao tác ghi khi retry.
- Phân biệt 429 với lỗi 5xx và lỗi authorization.

Nếu client không tuân thủ retry policy, một sự cố nhỏ có thể trở thành retry storm.

### 12.2. Phân biệt 429 và 503

- `429` thường cho biết caller hoặc bucket của caller vượt giới hạn.
- `503 Service Unavailable` thường cho biết dịch vụ tạm thời không thể xử lý request do tình trạng hệ thống hoặc bảo trì.

Không dùng 429 cho mọi tình trạng quá tải toàn cục nếu client không phải nguyên nhân hoặc không có bucket cụ thể. Có thể dùng 503 kèm `Retry-After` khi service tạm thời không khả dụng theo chính sách vận hành.

## 13. Ví dụ policy rate limit theo nhiều chiều

Giả sử API cung cấp các endpoint:

- `GET /v1/invoices/{id}`: đọc một hóa đơn.
- `GET /v1/invoices`: tìm kiếm hóa đơn.
- `POST /v1/invoices/export`: tạo export.
- `POST /v1/otp/send`: gửi OTP.

Một policy minh họa:

| Operation | IP/network | User/service | API key/client | Tenant | Giới hạn bổ sung |
|---|---|---|---|---|---|
| Đọc hóa đơn | Cap rộng | Theo user | Theo key nếu là integration | Theo tenant | Cost 1 |
| Tìm kiếm hóa đơn | Cap rộng | Theo user | Theo key và client | Theo tenant | Page size, query cost |
| Export | Cap rộng | Thấp hơn | Theo client | Quota export | Concurrency 1, async queue |
| Gửi OTP | Chặt theo IP | Theo user/đích nhận | Theo client | Theo tenant | Cooldown theo số điện thoại/email |

Các ngưỡng phải được hiệu chỉnh theo dữ liệu thực tế. Với OTP, chỉ giới hạn theo IP là chưa đủ vì attacker có thể đổi IP để gửi đến cùng một số điện thoại. Cần giới hạn theo đích nhận, user/account, IP và client, đồng thời có cooldown và chống enumeration.

Với export, giới hạn theo tenant giúp ngăn một tổ chức tiêu thụ toàn bộ năng lực. Giới hạn theo client ngăn một integration trong tenant tạo quá nhiều tác vụ. Concurrency cap và hàng đợi giúp điều tiết công việc nặng.

## 14. Ví dụ triển khai ở tầng ứng dụng

Một middleware hoặc filter có thể thực hiện các bước khái niệm:

1. Nhận route/operation đã được router xác định.
2. Lấy IP từ kết nối hoặc trusted proxy chain.
3. Xác thực request và lấy principal.
4. Lấy API key ID/client ID từ key record đã xác minh nếu có.
5. Xác định tenant context đã được xác minh.
6. Nạp policy theo operation.
7. Tạo danh sách bucket cần kiểm tra.
8. Gọi limiter dùng chung để kiểm tra và tiêu thụ ngân sách nguyên tử.
9. Nếu vượt ngưỡng, trả 429 và metric/audit phù hợp.
10. Nếu được phép, tiếp tục object authorization và nghiệp vụ.

Pseudocode Java:

```java
RateLimitDecision checkRequest(
        HttpRequest request,
        Route route,
        Authentication authentication
) {
    ClientAddress ip = trustedClientAddressResolver.resolve(request);

    List<RateLimitBucket> buckets = new ArrayList<>();
    buckets.add(policy.ipBucket(ip, route));

    if (authentication.isAuthenticated()) {
        Principal principal = verifiedPrincipal(authentication);
        buckets.add(policy.identityBucket(principal, route));

        if (principal instanceof ApiClientPrincipal client) {
            buckets.add(policy.apiKeyBucket(client.keyId(), route));
            buckets.add(policy.clientBucket(client.clientId(), route));
        }

        TenantId tenant = verifiedTenantContext(authentication, request);
        if (tenant != null) {
            buckets.add(policy.tenantBucket(tenant, route));
        }
    }

    buckets.add(policy.operationBucket(route));
    return distributedLimiter.consumeAtomically(buckets);
}
```

Đây là pseudocode minh họa cấu trúc, không phải code hoàn chỉnh. Trong triển khai thật:

- `trustedClientAddressResolver` chỉ tin proxy được cấu hình.
- `verifiedPrincipal` phải lấy từ authentication đã xác minh.
- `verifiedTenantContext` phải kiểm tra membership hoặc tenant binding.
- `route` phải là operation đã được router xác định, không lấy path tùy ý làm policy key.
- `consumeAtomically` phải bảo đảm các bucket bắt buộc được cập nhật nhất quán; nếu một bucket vượt ngưỡng, cần xác định có hoàn tác phần token đã tiêu thụ ở các bucket khác hay không.
- API key secret không được đưa vào bucket hoặc log.
- Policy phải định nghĩa rõ hành vi khi limiter store lỗi.

### 14.1. Vấn đề atomicity giữa nhiều bucket

Khi một request phải tiêu thụ token từ nhiều bucket, cần quyết định tất cả-or-nothing hay chấp nhận tiêu thụ một phần. Nếu IP bucket đã trừ token nhưng tenant bucket từ chối, hệ thống có thể:

- Giữ phần token đã trừ như chi phí xử lý kiểm tra; đơn giản nhưng có thể làm caller bị giới hạn sớm hơn.
- Dùng transaction/script để kiểm tra tất cả bucket trước, chỉ trừ khi mọi bucket đều cho phép.
- Dùng reservation/refund có kiểm soát, phức tạp hơn khi có lỗi giữa các bước.

Với rate limiter phân tán, all-or-nothing thường giúp kết quả dễ hiểu nhưng cần implementation atomic phù hợp. Không giả định nhiều lệnh Redis độc lập tự tạo thành transaction logic.

## 15. Kiểm thử rate limit

Kiểm thử cần xác nhận đúng bucket, đúng ngưỡng và đúng hành vi khi có nhiều caller đồng thời.

### 15.1. Kiểm thử từng chiều

| Chiều | Trường hợp kiểm thử |
|---|---|
| IP | Nhiều request từ cùng IP vượt ngưỡng; IP khác vẫn được xử lý |
| Proxy/IP | Header giả mạo không thay đổi IP tin cậy |
| Identity | User A vượt ngưỡng; user B không bị ảnh hưởng |
| Service identity | Workload A vượt cap; workload B vẫn có ngân sách riêng |
| API key | Key A vượt limit; key B được xử lý theo policy |
| Client | Nhiều key cùng client không chia nhỏ client quota |
| Tenant | Tenant A vượt quota; tenant B vẫn hoạt động khi global capacity còn |
| Operation | Endpoint export có limit thấp hơn endpoint đọc đơn giản |
| Anonymous | Request chưa xác thực vẫn bị edge/IP limit |
| Spoofing | Header user/tenant/client giả không tạo bucket mới có lợi |

### 15.2. Kiểm thử tương tác giữa các chiều

- Một user đổi IP nhưng vẫn bị user-level cap.
- Một client tạo key mới nhưng vẫn chịu client-level cap.
- Nhiều user trong cùng tenant cùng tiêu thụ tenant quota.
- Một service gọi thay mặt nhiều user chịu cả service cap và subject cap.
- Một IP NAT có nhiều user hợp lệ không bị chặn quá mức do ngưỡng không phù hợp.
- Một tenant vượt quota không làm giảm quota độc lập của tenant khác.

### 15.3. Kiểm thử concurrency và phân tán

- Gửi đồng thời nhiều request ở sát ngưỡng.
- Chia request qua nhiều application instance.
- Kiểm tra counter atomic và không vượt ngưỡng ngoài sai số đã chấp nhận.
- Kiểm tra TTL và reset window.
- Mô phỏng Redis timeout, failover và network partition.
- Kiểm tra clock skew giữa các node.
- Kiểm tra hot key khi một tenant hoặc client có lưu lượng lớn.
- Kiểm tra trạng thái limiter không bị reset ngoài ý muốn khi deploy.

### 15.4. Kiểm thử client behavior

- 429 có `Retry-After` hợp lệ khi policy cung cấp.
- Client tôn trọng backoff và jitter.
- Retry không tạo request storm.
- Idempotency bảo vệ thao tác ghi khỏi thực hiện trùng.
- Client phân biệt rate limit theo caller với service unavailable.

## 16. Giám sát và vận hành

Rate limit cần có metric để biết policy đang bảo vệ hệ thống hay đang chặn nhầm người dùng.

Nên theo dõi:

- Request được phép và bị từ chối theo route/operation.
- Số lượng 429 theo chiều IP, identity, key, client và tenant.
- Tỷ lệ bucket cạn token và thời gian chờ.
- Request rate, concurrency, p95/p99 latency và error rate.
- Cost unit, payload size, query complexity và số tác vụ đang chạy.
- Quota sử dụng theo tenant/tier.
- Số lần limiter store lỗi, timeout và chuyển degraded mode.
- Phân bố IP, key/client và tenant có lưu lượng bất thường.

### 16.1. Cẩn thận với metric cardinality

Không đưa raw API key, user ID hoặc tenant ID không giới hạn vào metric label. Một hệ thống có hàng triệu user có thể tạo cardinality rất lớn, làm tốn bộ nhớ và chi phí observability.

Có thể:

- Dùng route, policy ID, tier và dimension làm label có cardinality kiểm soát.
- Dùng log/audit có quyền truy cập hạn chế để tra cứu định danh cụ thể.
- Hash hoặc pseudonymize identifier nếu cần phân tích xu hướng.
- Chỉ tạo metric chi tiết theo tenant/client cho nhóm đã được chọn hoặc theo sampling.
- Không bao giờ ghi secret credential.

### 16.2. Phát hiện false positive

Một đợt 429 tăng không luôn có nghĩa attacker. Có thể do:

- Client mới triển khai bị cấu hình retry sai.
- NAT tập trung nhiều người dùng.
- Batch job chạy lệch lịch.
- Một tenant có mùa cao điểm.
- Policy vừa được giảm ngưỡng.
- Một endpoint mới có cost cao hơn dự kiến.

Theo dõi tỷ lệ 429 cùng business success, latency, tenant impact và thay đổi cấu hình. Có quy trình điều chỉnh policy, owner và audit để tránh mở rộng quota tùy tiện.

### 16.3. Alert và phản ứng

Cảnh báo khi:

- 429 tăng đột biến trên nhiều tenant.
- Một key/client tạo tải bất thường.
- Một tenant liên tục chạm quota.
- Limiter store mất khả năng phục vụ.
- Global capacity hoặc queue saturation tiến gần ngưỡng.
- Retry storm làm request tăng nhanh.
- Nhiều IP/identity thay đổi bất thường trong một khoảng ngắn.

Phản ứng có thể gồm xác minh traffic, giảm concurrency, tạm thời siết endpoint đắt tiền, thu hồi key bị lộ hoặc điều chỉnh policy có kiểm soát. Không nên tự động nâng quota chỉ để xóa cảnh báo.

## 17. Những lỗi thiết kế thường gặp

1. **Chỉ giới hạn theo IP.** Người dùng chung NAT bị ảnh hưởng và attacker có thể đổi IP.
2. **Chỉ giới hạn theo API key.** Một client có thể tạo nhiều key để chia nhỏ quota.
3. **Chỉ giới hạn theo user.** Service-to-service và anonymous traffic không được bảo vệ đầy đủ.
4. **Tin header identity do caller gửi.** Attacker có thể thay user, client hoặc tenant để nhận bucket khác.
5. **Dùng raw API key làm Redis key hoặc metric label.** Secret có thể bị lộ qua observability.
6. **Dùng một ngưỡng cho mọi endpoint.** Endpoint export và endpoint đọc đơn giản có chi phí rất khác.
7. **Đếm request nhưng bỏ qua cost.** Một request GraphQL hoặc batch có thể tạo hàng nghìn truy vấn.
8. **Counter chỉ lưu trong memory từng instance.** Caller phân phối request qua nhiều node để vượt giới hạn.
9. **Không cập nhật counter nguyên tử.** Request đồng thời cùng vượt qua ngưỡng.
10. **Không xử lý Redis/KV outage.** Limiter lỗi có thể làm hệ thống fail-open ngoài ý muốn hoặc gián đoạn diện rộng.
11. **Không đặt TTL hoặc kiểm soát cardinality.** Attacker tạo nhiều bucket và làm cạn bộ nhớ.
12. **Không phân biệt quota với concurrency.** Một tác vụ dài vẫn chiếm tài nguyên dù request rate thấp.
13. **Retry ngay sau 429.** Client tự tạo retry storm.
14. **Không kiểm tra proxy trust.** Header forwarding giả làm sai IP bucket.
15. **Không có fairness theo tenant.** Một tenant noisy neighbor ảnh hưởng các tenant khác.
16. **Không đo false positive.** Người dùng hợp lệ bị chặn mà nhóm vận hành không nhận ra.

## 18. Checklist thiết kế và triển khai

Trước khi đưa rate limit vào production, hãy xác nhận:

- [ ] Đã phân loại endpoint theo chi phí, độ nhạy và SLA.
- [ ] Đã xác định bucket cần dùng: IP, user/service identity, API key/client, tenant, operation và global.
- [ ] IP được lấy từ kết nối hoặc trusted proxy chain; header do caller gửi không được tin mặc định.
- [ ] Identity được lấy từ authentication context đã xác minh.
- [ ] API key bucket dùng key ID đã xác minh, không dùng raw secret.
- [ ] Client cap ngăn nhiều key cùng client chia nhỏ quota.
- [ ] Tenant context được xác minh từ membership hoặc binding đáng tin cậy.
- [ ] User subject và service actor được giới hạn riêng khi service gọi thay mặt user.
- [ ] Chính sách có burst, sustained rate và quota phù hợp.
- [ ] Endpoint tốn kém có cost limit, payload limit hoặc concurrency cap bổ sung.
- [ ] Thuật toán được chọn phù hợp với yêu cầu chính xác, burst và lưu lượng.
- [ ] Counter phân tán có atomicity và TTL.
- [ ] Có hành vi fail-open/fail-closed/degraded mode khi limiter store lỗi.
- [ ] Có fairness và bảo vệ noisy neighbor giữa các tenant.
- [ ] 429 và Retry-After được trả theo quy ước nhất quán.
- [ ] Client có retry/backoff/jitter và idempotency phù hợp.
- [ ] Có kiểm thử spoofing, bypass, NAT, IPv6, multi-key và multi-tenant.
- [ ] Có metric, alert, audit và quy trình điều chỉnh policy.
- [ ] Không ghi secret hoặc tạo metric cardinality không kiểm soát.

## 19. Kết luận

Rate limit hiệu quả cần giới hạn theo danh tính và phạm vi tiêu thụ thực tế. IP/network hỗ trợ chặn flood từ nguồn mạng; user/service identity giới hạn principal đã xác minh; API key và client giúp kiểm soát credential cùng tích hợp; tenant bảo vệ tính công bằng giữa các tổ chức. Không chiều nào đủ tin cậy để đứng một mình trong mọi tình huống.

Một thiết kế tốt chọn bucket theo endpoint và cost, kết hợp burst với sustained rate, quota và concurrency, đồng thời thực thi counter phân tán một cách nguyên tử. Hệ thống phải lấy IP từ proxy đáng tin, identity từ authentication đã xác minh, key ID từ key record và tenant từ membership hoặc binding đã kiểm tra.

Rate limit cần được kiểm thử cả trường hợp hợp lệ lẫn bypass, theo dõi false positive và trả 429 với hướng dẫn retry rõ ràng. Khi kết hợp giới hạn nhiều tầng với authorization, validation, idempotency, timeout và monitoring, API có thể bảo vệ tài nguyên tốt hơn mà vẫn duy trì trải nghiệm ổn định cho các client và tenant hợp lệ.

