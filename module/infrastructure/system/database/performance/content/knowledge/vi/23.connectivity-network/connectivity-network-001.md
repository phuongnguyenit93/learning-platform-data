# Chi phí mở kết nối, xác thực và thiết lập TLS

Một câu truy vấn có thể chỉ mất vài mili giây để thực thi, nhưng ứng dụng vẫn phản hồi chậm nếu mỗi request phải tạo kết nối mới đến cơ sở dữ liệu. Trước khi gửi SQL, client thường phải phân giải tên máy chủ, thiết lập TCP, thương lượng TLS, trao đổi thông tin giao thức, xác thực danh tính và khởi tạo session. Mỗi bước có thể phát sinh round trip mạng (RTT), công việc CPU, thao tác mật mã hoặc chờ dịch vụ xác thực. Khi request ngắn và tần suất cao, chi phí thiết lập kết nối có thể lớn hơn thời gian chạy truy vấn.

Bài học thuộc chương **Kết nối và mạng** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Hiểu chi phí mở kết nối, xác thực và TLS giúp phân biệt độ trễ thiết lập với độ trễ truy vấn, thiết kế connection pool phù hợp và giữ an toàn đường truyền trong khi kiểm chứng hiệu năng bằng số liệu.

## 1. Một kết nối database cần thực hiện những bước nào?

Khi ứng dụng tạo một kết nối vật lý mới, đường đi khái quát thường gồm các bước:

1. Phân giải hostname thành địa chỉ IP, nếu client dùng tên máy chủ.
2. Mở socket và thiết lập kết nối TCP đến endpoint của database hoặc proxy.
3. Thương lượng TLS nếu kết nối được bảo vệ bằng TLS.
4. Trao đổi thông điệp khởi động của giao thức database và các khả năng client/server.
5. Xác thực client, có thể kèm kiểm tra chứng chỉ, mật khẩu, challenge-response hoặc token.
6. Tạo session và áp dụng thuộc tính ban đầu như database, schema, role, timezone, encoding, isolation hoặc session options.
7. Chỉ sau đó client mới có thể gửi câu lệnh SQL trong session đã sẵn sàng.

Không phải mọi driver hoặc hệ quản trị thực hiện các bước theo đúng thứ tự trên. Một số giao thức gửi thông điệp khởi động trước khi bắt đầu TLS; một số dùng proxy hoặc service mesh; DNS có thể đã được cache; TLS có thể được resume; xác thực có thể dựa vào chứng chỉ hoặc cơ chế tích hợp. Sơ đồ sau thể hiện các thành phần thường gặp, không phải một chuẩn bắt buộc:

```text
Ứng dụng / driver
       |
       v
DNS / endpoint discovery
       |
       v
TCP connect
       |
       v
TLS negotiation (nếu bật)
       |
       v
Database protocol startup
       |
       v
Authentication / authorization
       |
       v
Session initialization
       |
       v
Connection sẵn sàng nhận SQL
```

Một connection pool giữ các kết nối vật lý đã hoàn thành các bước này để nhiều request có thể mượn và trả lại. Vì vậy, request sử dụng kết nối có sẵn thường tránh được phần lớn chi phí setup, dù vẫn có thể phải chờ lấy connection từ pool hoặc chờ DB xử lý.

## 2. Chi phí của mỗi giai đoạn

### 2.1. DNS và endpoint discovery

Nếu connection string dùng hostname, client hoặc thư viện mạng cần phân giải tên thành IP. Thời gian phân giải phụ thuộc DNS resolver, cache, search domain, số bản ghi, DNS failover và môi trường mạng. Một lookup có thể rất nhanh khi cache còn hiệu lực, nhưng có thể chậm khi cache miss hoặc resolver gặp vấn đề.

Trong môi trường cloud, endpoint discovery còn có thể liên quan đến service discovery, load balancer, DNS-based failover hoặc lấy địa chỉ từ cấu hình động. Nếu ứng dụng mở kết nối mới liên tục, lookup và discovery có thể trở thành phần chi phí lặp lại.

Không nên khắc phục bằng cách hard-code IP nếu endpoint có thể thay đổi khi failover hoặc scale. Hãy đo DNS lookup time, xác định TTL và cache behavior của runtime, driver và resolver; đồng thời kiểm tra ứng dụng có phân giải lại hostname quá thường xuyên hay không.

### 2.2. TCP handshake

TCP thường cần một quá trình bắt tay ba bước để thiết lập trạng thái kết nối giữa client và server:

```text
Client                         Server
  | -------- SYN -------------> |
  | <----- SYN + ACK ----------- |
  | -------- ACK -------------> |
  |                              |
  |       TCP established        |
```

Ở điều kiện đơn giản, quá trình này cần khoảng một RTT giữa hai đầu, chưa tính thời gian xử lý, retransmission, congestion, route hoặc proxy. Một RTT là thời gian khứ hồi của gói tin giữa client và endpoint, không phải thời gian thực thi SQL.

Khi client ở xa database, RTT có thể lớn hơn đáng kể. Ví dụ, nếu RTT là 35 ms thì riêng TCP handshake đã có thể tiêu tốn khoảng một khoảng khứ hồi mạng. Nếu sau đó TLS và database protocol tiếp tục cần nhiều lượt trao đổi, thời gian kết nối mới có thể lên đến hàng chục hoặc hàng trăm mili giây trước câu SQL đầu tiên.

TCP handshake cũng có thể chịu ảnh hưởng của SYN retransmission, packet loss, firewall inspection, load balancer và connection tracking. Nếu thời gian mở socket có đuôi p95/p99 cao, hãy xem network telemetry và server accept queue thay vì chỉ xem thời gian truy vấn.

### 2.3. TLS handshake

TLS bảo vệ tính bí mật, toàn vẹn và xác thực endpoint cho đường truyền. Trong handshake, client và server thương lượng phiên bản/cipher suite, trao đổi khóa, xác thực chứng chỉ máy chủ và tạo khóa phiên. Với mutual TLS (mTLS), server còn yêu cầu client trình chứng chỉ để xác thực client ở tầng TLS.

TLS handshake có thể phát sinh thêm một hoặc nhiều RTT tùy phiên bản, chế độ bắt tay, resumption, xác thực client và cách giao thức database khởi động TLS. TLS 1.3 thường rút gọn full handshake so với TLS 1.2; session resumption có thể giảm thêm chi phí. Không nên gán một số RTT cố định cho mọi kết nối vì giao thức, mạng, cipher, certificate chain và cơ chế resume khác nhau.

TLS còn tiêu tốn CPU cho các phép toán mật mã, đặc biệt khi tạo rất nhiều kết nối mới. Với kết nối dài và lưu lượng lớn, chi phí mã hóa/giải mã dữ liệu cũng cần được tính đến, dù trên phần cứng hiện đại có thể được tăng tốc bằng CPU instructions hoặc offload.

### 2.4. Database protocol startup và xác thực

Sau khi đường truyền sẵn sàng, client và server trao đổi thông điệp của giao thức database. Các thông điệp có thể bao gồm tên database, user, application name, encoding, capability flags, startup parameters, authentication challenge và kết quả xác thực.

Xác thực có thể dựa trên:

- Username/password hoặc challenge-response.
- SCRAM hoặc cơ chế tương tự, tránh gửi mật khẩu thô qua giao thức.
- Chứng chỉ client hoặc mTLS.
- Kerberos, GSSAPI, LDAP hoặc dịch vụ danh tính tập trung.
- Token ngắn hạn/IAM authentication trong một số dịch vụ cloud.
- Socket peer credentials hoặc cơ chế xác thực cục bộ tùy hệ điều hành.

Một số cơ chế yêu cầu thêm round trip để trao đổi challenge/response hoặc liên hệ identity provider. Kiểm tra chứng chỉ, token signing/validation, DNS của identity service và network latency đến dịch vụ danh tính đều có thể ảnh hưởng thời gian tạo connection.

Xác thực thành công không đồng nghĩa client được phép truy cập mọi đối tượng. Authorization, role mapping, default schema và session setup cũng có thể phát sinh công việc trước câu truy vấn đầu tiên hoặc trong lần truy cập đầu.

### 2.5. Session initialization

Sau xác thực, driver hoặc pool có thể đặt các thuộc tính session như:

- Database/catalog và schema mặc định.
- Role hoặc search path.
- Timezone, date format, locale và encoding.
- Isolation level hoặc transaction defaults.
- Autocommit, statement timeout và application name.
- Các session variables, temporary objects hoặc optimizer options.

Nếu mỗi lần mượn connection ứng dụng lại gửi nhiều lệnh `SET`, thời gian này có thể trở thành chi phí lặp lại. Pool thường có thể giữ session đã cấu hình hoặc chạy một quy trình reset khi trả connection. Tuy nhiên, session state phải được quản lý chặt để không rò rỉ trạng thái của request trước sang request sau.

## 3. Ước lượng tác động của RTT

Chi phí setup có thể được hình dung như tổng thời gian của các giai đoạn:

```text
T_connect ≈ T_DNS
          + T_TCP
          + T_TLS
          + T_protocol
          + T_auth
          + T_session
```

Đây là mô hình phân tích, không phải công thức cộng độc lập tuyệt đối. Một số bước có thể chồng lấp, được cache hoặc thực hiện qua proxy; các giai đoạn khác có thể cần nhiều RTT nối tiếp.

Ví dụ giả định:

| Thành phần | Thời gian minh họa |
|---|---:|
| DNS cache miss | 4 ms |
| TCP handshake | 25 ms |
| TLS handshake | 30 ms |
| Database startup và authentication | 20 ms |
| Session initialization | 6 ms |
| Tổng gần đúng | 85 ms |

Nếu truy vấn sau đó chỉ mất 4 ms, tổng thời gian request đầu tiên có thể bị chi phối bởi setup kết nối. Những số liệu này chỉ minh họa; không dùng làm định mức cho hệ thống thật.

### 3.1. RTT nối tiếp quan trọng hơn số bước

Một bước xử lý CPU mất 2 ms có thể ít ảnh hưởng hơn một lượt trao đổi mạng 40 ms. Nếu handshake cần nhiều RTT nối tiếp, tổng thời gian sẽ tăng theo độ trễ mạng. Vì vậy, database đặt ở region khác với ứng dụng có thể khiến connection setup đắt hơn nhiều so với triển khai cùng vùng mạng.

### 3.2. Connection setup không nằm trong query execution time

Một số công cụ chỉ đo thời gian SQL sau khi connection đã sẵn sàng. Khi đó, query latency có thể là 5 ms trong khi request latency là 100 ms vì mở kết nối mới. Ngược lại, APM ở tầng ứng dụng có thể ghi toàn bộ thời gian lấy connection, khiến người phân tích nhầm chi phí pool wait hoặc handshake thành query execution.

Hãy xác định ranh giới của từng timer: DNS, TCP connect, TLS, authentication, pool acquisition, statement execution và result transfer. Chỉ khi tách được các giai đoạn, mới có thể chọn biện pháp tối ưu đúng.

## 4. Connection pooling giảm chi phí setup như thế nào?

Connection pool duy trì một tập kết nối vật lý đến DB hoặc proxy. Khi request cần DB, ứng dụng mượn một connection đã thiết lập, thực hiện transaction rồi trả lại pool. Request tiếp theo có thể dùng cùng connection.

```text
Request A ---- borrow ----> Connection 1 ---- execute ---- return
Request B ---- borrow ----> Connection 1 ---- execute ---- return
Request C ---- borrow ----> Connection 2 ---- execute ---- return

Pool giữ các connection vật lý đã TCP/TLS/authenticate sẵn.
```

Lợi ích:

- Tránh lặp TCP/TLS handshake cho mỗi request.
- Giảm số lần xác thực và khởi tạo session.
- Giảm CPU cho mật mã và database connection startup.
- Giảm connection churn và số socket mở/đóng.
- Có thể giới hạn số session DB và điều tiết concurrency.
- Giảm độ trễ tail khi request ngắn và DB ở xa ứng dụng.

Pool không loại bỏ mọi chi phí kết nối. Ứng dụng vẫn có thể chờ connection khả dụng; pool phải kiểm tra connection lỗi, tạo connection thay thế, reset session và duy trì kết nối qua thời gian. Nếu pool quá nhỏ, queue wait tăng; nếu quá lớn, DB có thể chịu áp lực do quá nhiều session và truy vấn đồng thời.

### 4.1. Vòng đời connection trong pool

Một connection thường trải qua các trạng thái:

1. **Create:** mở TCP, TLS, protocol startup và authentication.
2. **Idle:** đã sẵn sàng trong pool, chờ request mượn.
3. **Borrowed/in use:** một request hoặc transaction đang sử dụng.
4. **Return:** ứng dụng hoàn tất và trả connection.
5. **Reset/validate:** pool kiểm tra trạng thái, rollback transaction còn mở, reset session nếu cần và xác nhận connection còn sống.
6. **Retire:** loại connection cũ, lỗi hoặc quá hạn; tạo kết nối mới thay thế.

Nếu ứng dụng không trả connection khi kết thúc, pool có thể cạn dù DB còn khỏe. Nếu reset quá nhiều trạng thái bằng nhiều round trip, chi phí return/borrow có thể đáng kể. Cần cấu hình lifecycle theo driver và framework.

### 4.2. Pool acquisition time khác connection creation time

Hai chỉ số cần tách riêng:

- **Connection creation time:** thời gian tạo kết nối vật lý mới, bao gồm các bước setup.
- **Pool acquisition time:** thời gian request chờ để mượn được một connection từ pool.

Pool hit nhanh có thể có creation time cao nhưng không ảnh hưởng mỗi request. Khi pool hết connection, acquisition time có thể tăng dù không tạo connection mới. Nếu dashboard chỉ có “time to get connection”, cần biết đó là tạo mới hay chờ pool.

## 5. Chọn kích thước connection pool

Không có một con số pool size tối ưu cho mọi ứng dụng. Kích thước cần cân bằng giữa concurrency hữu ích và khả năng xử lý của database.

Nếu pool quá nhỏ:

- Request chờ connection dù DB có thể còn capacity.
- Pool acquisition p95/p99 tăng.
- Throughput ứng dụng có thể bị giới hạn bởi số connection khả dụng.
- Một transaction dài có thể giữ connection khiến request ngắn phải chờ.

Nếu pool quá lớn:

- DB có nhiều session active hoặc idle hơn cần thiết.
- Mỗi session có thể tiêu thụ memory và metadata.
- Nhiều truy vấn đồng thời có thể cạnh tranh CPU, I/O, lock và memory grants.
- Context switching, queueing và contention có thể tăng.
- Connection storm khi restart hoặc failover có thể làm DB quá tải.

### 5.1. Tính tổng pool trên tất cả instance

Giả sử ứng dụng có 12 instance, mỗi instance cấu hình pool tối đa 30 connection. Tổng giới hạn lý thuyết là:

```text
12 instances × 30 connections = 360 connections
```

Nếu còn worker, batch process, migration, monitoring, admin tool và service khác, tổng số session có thể cao hơn nhiều. Pool size phải được tính ở cấp toàn hệ thống, không chỉ xem một instance.

### 5.2. Dựa vào concurrency và thời gian giữ connection

Có thể dùng định luật Little để ước lượng số connection đang bận trung bình:

```text
Busy connections ≈ completed transactions/sec
                    × average connection hold time (sec)
```

Ví dụ 200 transaction/giây, mỗi transaction giữ connection trung bình 0,05 giây:

```text
200 × 0,05 = 10 busy connections trung bình
```

Con số này không có nghĩa pool size tối ưu là 10. Cần tính biến động, p95/p99 hold time, burst, batch job, headroom, transaction dài và giới hạn concurrency DB. Công thức chỉ giúp ước lượng tải trung bình.

### 5.3. Pool size không phải số worker DB tối ưu

Connection có thể idle, chờ lock hoặc chờ I/O. Tăng pool size làm tăng số session có khả năng gửi việc, nhưng không tăng số CPU core, IOPS hoặc khả năng xử lý log flush. Nếu DB bão hòa ở 40 active transactions, tăng pool từ 80 lên 300 có thể chỉ tạo hàng đợi sâu hơn.

Hãy quan sát active sessions, runnable workers, wait events, CPU, I/O, lock waits và pool wait time để xác định pool đang điều tiết đúng hay đang tạo quá nhiều concurrency.

## 6. Xác thực: bảo mật và hiệu năng

Xác thực là bước xác minh client có danh tính hợp lệ. Chi phí và đặc điểm phụ thuộc cơ chế được chọn.

### 6.1. Username/password

Client gửi thông tin đăng nhập qua database protocol. Khi dùng TLS đúng cách, thông tin được bảo vệ trên đường truyền. Server kiểm tra credential theo cơ chế nội bộ hoặc nguồn danh tính đã cấu hình.

Không nên lưu password dạng plaintext trong source code, log hoặc connection string được commit. Dùng secret manager, environment injection có kiểm soát hoặc cơ chế credential phù hợp. Rotation password có thể khiến connection mới thất bại nếu secret ở ứng dụng và DB không được cập nhật đồng bộ.

### 6.2. Challenge-response và SCRAM

Một số cơ chế không gửi password thô mà dùng challenge-response, nonce và proof dựa trên secret. Điều này có thể cần thêm lượt trao đổi và phép tính mật mã. Ví dụ PostgreSQL hỗ trợ SCRAM-SHA-256 trong các phiên bản hiện đại; client và server phải tương thích.

Chi phí xác thực thường nhỏ hơn chi phí mở TCP/TLS trên mạng có RTT cao, nhưng khi tạo hàng nghìn connection đồng thời, CPU và số lượt trao đổi có thể trở thành đáng kể.

### 6.3. Kerberos/GSSAPI hoặc LDAP

Xác thực tích hợp có thể phụ thuộc KDC, directory service hoặc identity provider. Client có thể dùng ticket đã có, hoặc cần lấy/renew credential. Nếu dịch vụ danh tính ở xa, DNS và network latency đến đó có thể làm thời gian connect tăng.

Khi chẩn đoán, hãy tách thời gian DB authentication khỏi thời gian liên hệ identity provider. Không giảm mức xác thực chỉ để benchmark nhanh hơn nếu hệ thống production yêu cầu cơ chế đó.

### 6.4. Certificate authentication và mTLS

Trong mTLS, client và server đều xác thực bằng chứng chỉ trong TLS handshake. Cần kiểm tra certificate chain, hostname/SAN, validity period, trust store, key usage và việc rotation. Việc kiểm tra chứng chỉ có thể tiêu tốn CPU và có thể phát sinh truy vấn kiểm tra thu hồi tùy cấu hình, nhưng lợi ích là danh tính client được ràng buộc với credential mật mã.

Chứng chỉ hết hạn hoặc CA chain không tin cậy thường gây lỗi kết nối trước khi câu SQL được gửi. Hãy theo dõi thời hạn chứng chỉ và thử rotation trong môi trường kiểm thử.

### 6.5. Token/IAM authentication

Một số dịch vụ database cloud hỗ trợ token ngắn hạn thay password tĩnh. Client có thể cần lấy token từ identity service hoặc ký token bằng credential. Nếu token được tạo cho mỗi connection, thời gian lấy token và giới hạn rate của identity provider có thể ảnh hưởng connection storm.

Có thể cache token đến gần thời điểm hết hạn theo hướng dẫn nhà cung cấp, nhưng phải bảo đảm không dùng token đã hết hạn và không chia sẻ credential sai security context. Connection pool giữ kết nối lâu hơn thời hạn token không nhất thiết phải xác thực lại cho mỗi câu lệnh; hành vi cụ thể phụ thuộc dịch vụ và chính sách session.

## 7. TLS: bảo vệ đường truyền và chi phí handshake

TLS cung cấp:

- **Confidentiality:** mã hóa dữ liệu để bên trung gian không đọc được nội dung.
- **Integrity:** phát hiện dữ liệu bị sửa đổi trên đường truyền.
- **Server authentication:** client xác minh đang kết nối đúng server theo chứng chỉ và hostname.
- **Client authentication (tùy chọn):** mTLS xác minh cả client.

TLS có chi phí trong hai giai đoạn:

1. **Handshake:** thương lượng, trao đổi khóa, kiểm tra chứng chỉ và tạo khóa phiên.
2. **Record processing:** mã hóa/giải mã và kiểm tra integrity cho dữ liệu truyền sau khi kết nối đã thiết lập.

Với kết nối sống lâu, chi phí handshake được phân bổ trên nhiều request. Với kết nối ngắn, handshake có thể chiếm tỷ lệ lớn trong tổng latency.

### 7.1. TLS 1.2 và TLS 1.3

TLS 1.3 được thiết kế để giảm số lượt trao đổi của full handshake so với TLS 1.2 và loại bỏ một số thuật toán/cấu hình cũ không còn phù hợp. Tuy nhiên, thời gian thực tế còn phụ thuộc cipher, chứng chỉ, CPU, RTT, proxy và việc session resumption có được dùng hay không.

Không nên chỉ đổi phiên bản TLS để tối ưu mà bỏ qua tương thích driver, database server, proxy, load balancer và chính sách bảo mật. Dùng phiên bản TLS được nhà cung cấp hỗ trợ và cấu hình cipher suite an toàn.

### 7.2. Certificate validation

Client cần xác minh chứng chỉ server theo trust chain và hostname. Chỉ bật mã hóa mà bỏ xác minh hostname hoặc chấp nhận mọi chứng chỉ sẽ làm suy yếu bảo vệ trước server giả mạo hoặc man-in-the-middle.

Các lỗi thường gặp:

- Hostname trong connection string không khớp SAN/CN của chứng chỉ.
- CA trung gian thiếu trong chain hoặc trust store không đúng.
- Chứng chỉ hết hạn hoặc chưa có hiệu lực theo clock hệ thống.
- Container/VM thiếu CA bundle cần thiết.
- Certificate rotation không đồng bộ giữa server, proxy và client.

Hãy khắc phục trust chain và hostname đúng cách, không tắt certificate verification để làm kết nối chạy được.

### 7.3. Session resumption và TLS tickets

TLS session resumption cho phép client và server tái sử dụng thông tin phiên trước để giảm công việc handshake. TLS 1.2 có session ID/session tickets; TLS 1.3 dùng PSK/tickets theo cơ chế riêng. Resumption có thể giảm RTT và CPU, nhưng còn phụ thuộc server, proxy, ticket lifetime, key rotation và client support.

Session resumption không thay thế việc xác thực server theo cách an toàn. Cần bảo đảm ticket keys được quản lý và xoay vòng đúng chính sách, đặc biệt khi nhiều server/proxy cần chia sẻ khả năng resume.

### 7.4. TLS 1.3 0-RTT và rủi ro replay

TLS 1.3 có cơ chế early data 0-RTT trong một số tình huống resume. Nó có thể gửi dữ liệu sớm hơn nhưng dữ liệu 0-RTT có thể bị replay bởi đối thủ trong các điều kiện giao thức. Không gửi thao tác có tác dụng phụ như INSERT, UPDATE, DELETE hoặc giao dịch tài chính qua early data trừ khi thiết kế ứng dụng và hệ thống có biện pháp chống replay phù hợp theo chuẩn và nhà cung cấp. Đối với kết nối database, không giả định driver hoặc server hỗ trợ 0-RTT an toàn; kiểm tra rõ hành vi thực tế.

## 8. TLS và database protocol: thứ tự thương lượng khác nhau

Một số giao thức database bắt đầu bằng một thông điệp đặc biệt để hỏi server có hỗ trợ TLS hay không, sau đó mới chuyển sang TLS. PostgreSQL là ví dụ điển hình: client có thể gửi `SSLRequest`, server trả lời, rồi TLS handshake bắt đầu. Các giao thức khác có thể khởi động TLS ngay khi kết nối TCP được thiết lập hoặc dùng proxy kết thúc TLS.

Do đó, khi đếm RTT, không nên chỉ cộng một con số cố định cho TCP cộng TLS cộng authentication. Hãy dùng packet capture ở môi trường được phép, driver telemetry hoặc server logs để biết số lượt trao đổi thực tế. Packet capture có thể chứa metadata nhạy cảm; cần giới hạn quyền truy cập và tránh ghi nội dung bí mật.

## 9. Connection pooler và proxy

Trong kiến trúc lớn, một proxy/pooler có thể đứng giữa ứng dụng và database:

```text
Nhiều ứng dụng / worker
          |
          v
   Client-side pools
          |
          v
   Proxy / connection pooler
          |
          v
   Database server
```

Proxy có thể duy trì một số kết nối backend ổn định đến DB, trong khi nhiều client connection được ghép hoặc điều phối lên các backend đó. Điều này giúp giới hạn số session DB, giảm connection churn và tách số client khỏi số backend session.

### 9.1. Session pooling

Trong session pooling, một client được gắn với một backend connection trong toàn bộ vòng đời session. Cách này tương thích tốt hơn với trạng thái session, temporary table, prepared statement hoặc session variables, nhưng mức độ multiplexing thấp hơn.

### 9.2. Transaction pooling

Trong transaction pooling, backend connection chỉ được gán cho client trong thời gian một transaction. Sau commit/rollback, backend có thể được trả về pool để phục vụ client khác. Cách này tăng khả năng multiplexing, nhưng không tương thích với mọi tính năng phụ thuộc session state.

Các tính năng cần kiểm tra gồm:

- Temporary tables và session variables.
- Session-level advisory locks.
- Prepared statements được giữ qua nhiều transaction.
- `SET`/`RESET` và search path.
- Cursors hoặc transaction state kéo dài.
- Driver features phụ thuộc một backend cố định.

Không bật transaction pooling chỉ vì muốn giảm connection count. Hãy kiểm tra compatibility của ứng dụng và pooler theo phiên bản/cấu hình. Nếu trạng thái session bị giả định nhưng backend thay đổi giữa các transaction, lỗi có thể khó tái hiện.

### 9.3. Proxy có thể trở thành một tầng độ trễ mới

Proxy thêm một network hop, queue, TLS termination hoặc authentication layer. Nó có thể giảm tổng chi phí bằng multiplexing nhưng cũng có thể trở thành bottleneck nếu CPU, connection limit hoặc queue không đủ. Đo latency từ ứng dụng đến proxy, proxy đến DB, backend pool wait và DB execution riêng biệt.

## 10. Connection storm khi khởi động hoặc failover

Connection storm xảy ra khi nhiều client đồng thời tạo kết nối mới, ví dụ sau deploy, restart, database failover hoặc pool reset. Mỗi kết nối mới có thể cần TCP, TLS, authentication và session setup; hàng trăm hoặc hàng nghìn handshake cùng lúc có thể tiêu tốn CPU và làm server accept/auth queue tăng.

Các dấu hiệu:

- Số connection creation tăng đột biến.
- TLS/authentication CPU tăng.
- Connection timeout hoặc handshake failure tăng.
- DB đạt giới hạn connection/session.
- Request queue và pool acquisition time tăng.
- Identity provider hoặc DNS bị tăng tải.

Biện pháp giảm rủi ro:

- Ramp-up connection theo từng nhóm thay vì tất cả instance cùng mở pool tối đa.
- Dùng jitter cho reconnect/retry để tránh đồng bộ thời điểm.
- Giới hạn số lần reconnect và dùng exponential backoff.
- Giữ pool nhỏ ban đầu rồi tăng theo nhu cầu thực.
- Duy trì kết nối sống đủ lâu nếu chính sách bảo mật và vận hành cho phép.
- Dùng proxy/pooler phù hợp để bảo vệ DB khỏi quá nhiều backend session.
- Đặt timeout và circuit breaker để lỗi không lan thành retry storm.
- Kiểm tra capacity của DB, proxy, DNS và identity provider trong kịch bản failover.

Không retry kết nối liên tục ngay lập tức. Một hệ thống đang quá tải có thể bị làm nặng hơn bởi chính các client đang cố kết nối lại.

## 11. Timeout và keepalive

Các timeout khác nhau cần được phân biệt:

- **DNS timeout:** thời gian chờ phân giải tên.
- **Connect timeout:** thời gian tối đa để thiết lập TCP/đến endpoint.
- **TLS handshake timeout:** thời gian tối đa để hoàn tất TLS nếu driver hỗ trợ cấu hình riêng.
- **Authentication/startup timeout:** thời gian hoàn thành protocol startup và xác thực.
- **Pool acquisition timeout:** thời gian chờ lấy connection từ pool.
- **Socket/read timeout:** thời gian chờ dữ liệu trên kết nối.
- **Statement/transaction timeout:** giới hạn thực thi câu SQL hoặc transaction.

Driver có thể gộp nhiều bước vào một connect timeout tổng. Cần đọc tài liệu driver để biết timeout bao phủ giai đoạn nào. Nếu timeout quá ngắn, kết nối hợp lệ trong môi trường RTT cao có thể thất bại; nếu quá dài, request lỗi giữ worker và tài nguyên lâu.

TCP keepalive giúp phát hiện kết nối chết sau một khoảng không hoạt động, nhưng không thay thế health check ở tầng database hoặc validation của pool. Một kết nối TCP còn sống không bảo đảm DB session vẫn dùng được; server có thể restart, failover hoặc đóng session.

## 12. Session reset và nguy cơ rò rỉ trạng thái

Connection pool tái sử dụng cùng một session cho nhiều request. Nếu request trước thay đổi session state và pool không reset, request sau có thể kế thừa trạng thái ngoài ý muốn.

Ví dụ trạng thái cần chú ý:

- Transaction chưa commit/rollback.
- Role hoặc search path đã thay đổi.
- Timezone, isolation level hoặc statement timeout khác mặc định.
- Temporary table, session variable hoặc advisory lock còn tồn tại.
- Session context phục vụ row-level security.
- Prepared statement hoặc cursor còn mở.

Pool nên có cơ chế reset hoặc quy ước rõ ràng về session state. Reset quá rộng có thể tốn round trip; reset quá nhẹ có thể gây lỗi correctness hoặc bảo mật. Chọn chính sách theo DBMS/driver, đo chi phí và kiểm tra bằng test tái sử dụng connection giữa hai request có context khác nhau.

## 13. Đo thời gian kết nối và xác định bottleneck

Một hệ thống cần tách các metric ở client, pool, proxy và DB.

| Thành phần | Metric nên thu thập | Dấu hiệu cần điều tra |
|---|---|---|
| DNS | Lookup duration, cache hit, resolver error | DNS chậm hoặc lookup lặp lại |
| TCP | Connect duration, retransmission, timeout | RTT cao, packet loss, accept queue |
| TLS | Handshake duration, version, resumption rate, failure | Full handshake quá thường xuyên, certificate issue, CPU crypto |
| Authentication | Auth duration, method, failure, identity provider latency | Challenge round trips hoặc external identity chậm |
| Session startup | Startup duration, init commands, reset duration | Nhiều lệnh setup lặp lại |
| Pool | Active/idle, pending borrowers, acquisition p95/p99, create/destroy rate | Pool quá nhỏ, connection churn hoặc leak |
| Proxy | Client/backend count, queue, backend wait, multiplexing ratio | Proxy trở thành bottleneck |
| Database | Active sessions, login rate, CPU, memory, wait events | DB bị quá nhiều session hoặc login storm |
| Application | End-to-end latency, request rate, timeout, retry | Tổng request chậm dù SQL execution ngắn |

### 13.1. Tách pool wait khỏi query time

Ví dụ một request có timeline:

```text
Pool acquisition:     45 ms
SQL execution:         6 ms
Result transfer:       3 ms
Application overhead:  4 ms
--------------------------------
Request DB segment:    58 ms
```

Trong trường hợp này, tối ưu index để giảm SQL từ 6 ms xuống 3 ms chỉ giảm một phần nhỏ tổng thời gian. Cần điều tra pool wait: pool size, connection hold time, transaction dài, rò rỉ connection hoặc DB concurrency.

### 13.2. So sánh cold connect và pooled request

Benchmark nên đo riêng:

- Thời gian tạo một kết nối vật lý mới.
- Thời gian lấy connection đã có từ pool.
- Thời gian reset và trả connection.
- Thời gian SQL trên kết nối đã sẵn sàng.
- Thời gian request đầu tiên sau failover/restart.

Đo nhiều lần và báo cáo p50/p95/p99, không chỉ trung bình. Kết nối mới chịu ảnh hưởng DNS/TCP/TLS/auth; pooled request chịu ảnh hưởng pool queue và trạng thái session.

## 14. Ví dụ đo bằng PostgreSQL client

Với PostgreSQL, có thể dùng `psql` để thử kết nối TLS và kiểm tra trạng thái session. Ví dụ:

```bash
psql "host=db.example.internal port=5432 dbname=app user=app_user sslmode=verify-full connect_timeout=5"
```

`sslmode=verify-full` yêu cầu TLS và kiểm tra chứng chỉ/hostname theo cấu hình trust của client. Không thay bằng `disable` hoặc chế độ bỏ kiểm tra chứng chỉ trong production chỉ để giảm thời gian kết nối.

Sau khi kết nối, có thể kiểm tra session TLS bằng view hệ thống:

```sql
SELECT ssl, version, cipher, bits
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

View và cột có thể khác theo phiên bản/quyền. Truy vấn này xác nhận trạng thái TLS của backend session; nó không tự đo handshake duration. Để đo thời gian connect, dùng telemetry của driver, APM hoặc đo từ client với đồng hồ monotonic.

Để so sánh connection mới với pool, tạo hai bài thử riêng: một bài mở/đóng kết nối cho từng lần chạy trong môi trường test, bài còn lại mượn connection đã được pool khởi tạo. Giữ nguyên endpoint, TLS, authentication, query và dữ liệu; ghi thời gian từng giai đoạn nếu driver cung cấp.

## 15. Ví dụ thực hành: API truy vấn ngắn nhưng phản hồi chậm

Giả sử một API thực hiện một câu SELECT chỉ mất 5 ms theo database statement metrics. APM ghi nhận p95 của đoạn truy cập DB là 95 ms. Điều tra cho thấy ứng dụng tạo một kết nối mới cho mỗi request; RTT đến DB là 28 ms.

Một phân rã giả định:

| Giai đoạn | p95 minh họa |
|---|---:|
| DNS và TCP | 30 ms |
| TLS | 24 ms |
| Authentication/startup | 25 ms |
| SQL execution | 5 ms |
| Trả kết quả và overhead | 6 ms |
| Tổng | 90 ms |

Các giá trị chỉ để minh họa cách phân rã. Nhóm có thể thử connection pool với số connection giới hạn, giữ TLS verification và authentication như cũ. Sau thay đổi, pooled request có thể không còn trả chi phí TCP/TLS/auth trên mỗi request, nhưng cần đo pool acquisition time và connection hold time.

Nếu p95 giảm còn 12 ms nhưng pool acquisition p99 tăng lên 200 ms khi tải đỉnh, pool có thể quá nhỏ hoặc transaction giữ connection quá lâu. Nếu tăng pool làm DB CPU và lock waits tăng, concurrency có thể vượt khả năng xử lý. Cần chọn pool size theo SLO, workload và capacity DB thay vì tối đa hóa số connection.

## 16. Quy trình tối ưu có kiểm chứng

1. **Đặt câu hỏi:** request chậm vì tạo connection mới, chờ pool, xác thực, TLS hay SQL?
2. **Đo baseline:** lấy p50/p95/p99 cho connection creation, pool acquisition, TLS/auth nếu có, SQL execution và end-to-end latency.
3. **Kiểm tra topology:** khoảng cách client-DB, DNS, proxy, load balancer, service mesh và identity provider.
4. **Kiểm tra connection churn:** số connection create/destroy, tuổi thọ connection, số login/giây và reconnect rate.
5. **Kiểm tra pool:** active/idle, pending borrowers, acquisition timeout, leak và thời gian giữ connection.
6. **Kiểm tra bảo mật:** TLS version, certificate validation, auth method, token/cert rotation và policy.
7. **Nêu giả thuyết:** ví dụ mỗi request mở connection mới, pool quá nhỏ hoặc identity lookup bị chậm.
8. **Thay đổi từng yếu tố:** bật pool, điều chỉnh lifecycle, giảm round trip không cần thiết hoặc dùng proxy phù hợp; giữ nguyên mức bảo vệ TLS/auth.
9. **Đo lại cùng workload:** cùng request rate, concurrency, region, query mix và thời lượng.
10. **Kiểm tra tác động phụ:** DB sessions, CPU, memory, lock waits, proxy queue, stale session state, reconnect storm và lỗi bảo mật.

Một tối ưu chỉ được chấp nhận khi end-to-end latency và throughput cải thiện mà tính đúng đắn, tính sẵn sàng và yêu cầu bảo mật vẫn được giữ.

## 17. Những sai lầm thường gặp

- **Đo query time rồi kết luận request nhanh:** bỏ qua DNS, TCP, TLS, authentication và pool wait.
- **Mở kết nối mới cho mỗi request ngắn:** lặp lại nhiều bước setup đắt hơn chính truy vấn.
- **Tăng pool vô hạn:** có thể làm DB quá tải bởi session và concurrency.
- **Nhầm pool acquisition với connection creation:** hai giai đoạn có nguyên nhân khác nhau.
- **Tắt TLS hoặc certificate verification để giảm latency:** làm suy yếu bảo mật và có thể che giấu lỗi cấu hình chứng chỉ.
- **Dùng TLS session resumption như thay thế pool:** resumption giảm handshake nhưng vẫn cần kết nối TCP mới và các bước database startup/auth phù hợp.
- **Cho rằng TLS 1.3 luôn có một số RTT cố định:** thực tế phụ thuộc full/resumed handshake, mTLS, proxy và giao thức DB.
- **Dùng transaction pooling mà không kiểm tra session state:** có thể làm hỏng giả định về temporary table, session variable hoặc prepared statement.
- **Retry kết nối ngay lập tức:** tạo connection storm và làm DB/identity provider quá tải hơn.
- **Chỉ tính pool của một instance:** bỏ qua tổng connection từ mọi replica, worker và công cụ vận hành.
- **Bỏ qua reset session:** trạng thái của request trước có thể ảnh hưởng request sau.
- **Không đo cold connect riêng:** không biết pool đang tiết kiệm được bao nhiêu thời gian.

## 18. Bài tập tự kiểm tra

### Bài tập 1: Phân rã latency

Một API có p95 120 ms. Database statement metrics cho thấy câu SQL chỉ mất 8 ms. APM ghi pool acquisition 70 ms.

**Câu hỏi:** phần thời gian nào cần điều tra trước?

**Gợi ý trả lời:** pool acquisition đang chiếm phần lớn thời gian được đo. Kiểm tra số connection active/idle, pending borrowers, connection hold time, transaction dài và leak. Tối ưu SQL 8 ms có thể hữu ích nhưng không giải quyết 70 ms chờ pool.

### Bài tập 2: Tác động của RTT

Ứng dụng đặt ở region khác database với RTT 45 ms. Một connection mới cần TCP, TLS và authentication với nhiều lượt trao đổi nối tiếp.

**Câu hỏi:** tại sao connection setup có thể lớn hơn thời gian SQL? Biện pháp nào giảm chi phí lặp lại?

**Gợi ý trả lời:** mỗi lượt trao đổi nối tiếp phải chờ RTT nên tổng setup có thể vượt thời gian truy vấn ngắn. Dùng connection pool hoặc pooler để tái sử dụng kết nối đã thiết lập; cân nhắc đặt ứng dụng gần DB nếu kiến trúc cho phép. Giữ TLS và xác thực an toàn.

### Bài tập 3: Pool quá lớn

Sau khi tăng pool từ 50 lên 400 connection trên mỗi instance, pool wait giảm nhưng DB CPU, lock waits và p99 tăng. Hệ thống có 8 instance.

**Câu hỏi:** tổng giới hạn lý thuyết là bao nhiêu và nên điều tra gì?

**Gợi ý trả lời:** 8 × 400 = 3.200 connection, chưa tính worker và công cụ khác. DB có thể bị quá tải bởi quá nhiều session/concurrency. Kiểm tra active transactions, CPU, I/O, lock waits, memory và throughput; thử pool nhỏ hơn hoặc proxy multiplexing phù hợp.

### Bài tập 4: TLS certificate lỗi

Sau khi rotate chứng chỉ server, một số client báo hostname mismatch và kết nối thất bại.

**Câu hỏi:** có nên tắt hostname verification để khôi phục dịch vụ không?

**Gợi ý trả lời:** không. Cần kiểm tra SAN/hostname, trust chain, CA bundle, thời hạn chứng chỉ và cấu hình endpoint. Cập nhật chứng chỉ hoặc trust store đúng cách, kiểm thử trước khi rollout.

### Bài tập 5: Transaction pooling

Ứng dụng lưu `SET search_path` và temporary table trong session, nhưng pooler được chuyển sang transaction pooling.

**Câu hỏi:** vì sao có thể phát sinh lỗi khó tái hiện?

**Gợi ý trả lời:** backend connection có thể thay đổi giữa các transaction. Session state và temporary table không nhất thiết tồn tại trên backend tiếp theo. Cần kiểm tra compatibility, chuyển state vào transaction hoặc dùng session pooling khi yêu cầu ứng dụng cần session cố định.

### Checklist thiết kế và đo connection setup

- [ ] Đã tách DNS, TCP, TLS, protocol startup, authentication và session initialization.
- [ ] Đã phân biệt connection creation time với pool acquisition time.
- [ ] Đã đo p50/p95/p99 và error rate cho từng giai đoạn.
- [ ] Đã ghi RTT, packet loss, retransmission và vị trí client/database.
- [ ] Đã xác định TLS version, certificate validation và session resumption.
- [ ] Đã giữ hostname verification và trust chain đúng.
- [ ] Đã xác định auth method và độ trễ identity provider nếu có.
- [ ] Đã tính tổng pool size trên mọi application instance và worker.
- [ ] Đã theo dõi active/idle/pending connections và connection hold time.
- [ ] Đã kiểm tra session reset và transaction cleanup khi trả connection.
- [ ] Đã xác nhận compatibility trước khi dùng transaction pooling.
- [ ] Đã có backoff/jitter và giới hạn reconnect để tránh connection storm.
- [ ] Đã so sánh cold connect với pooled request trong cùng điều kiện.
- [ ] Đã kiểm tra DB capacity, proxy queue, CPU, memory, lock và I/O sau thay đổi.
- [ ] Đã xác nhận latency/throughput cải thiện mà không giảm bảo mật hoặc tính đúng đắn.

Chi phí mở kết nối, xác thực và thiết lập TLS là một phần của độ trễ ứng dụng nhưng thường nằm ngoài thời gian thực thi SQL. TCP/TLS handshake, database startup, authentication và session initialization có thể tạo nhiều lượt trao đổi mạng và tiêu tốn CPU; connection pool giúp tái sử dụng kết nối nhưng cần giới hạn tổng concurrency, quản lý session state và xử lý reconnect có kiểm soát. Hãy đo riêng từng giai đoạn, phân biệt pool wait với query time, giữ nguyên yêu cầu TLS/xác thực và xác nhận thay đổi bằng workload đại diện cùng các chỉ số p95/p99, throughput, lỗi và tài nguyên DB.
