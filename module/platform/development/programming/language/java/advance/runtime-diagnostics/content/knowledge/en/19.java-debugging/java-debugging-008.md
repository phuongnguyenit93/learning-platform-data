# 19.8. Bảo vệ cổng debug và giới hạn sử dụng debugger trên tiến trình đang phục vụ

## 1. Vì sao cổng debug là một điểm nhạy cảm?

Với ứng dụng Java đang phục vụ request, debugger giúp xem luồng chạy, stack frame, giá trị biến, exception và nguyên nhân lỗi. Nhưng kết nối debugger **không phải quyền chỉ đọc**. Thông qua giao diện điều khiển JVM, người có quyền debug có thể tạm dừng thread, quan sát dữ liệu trong bộ nhớ, thay đổi giá trị, yêu cầu đánh giá biểu thức hoặc gọi phương thức. Tác động có thể vượt xa thao tác xem log và ảnh hưởng trực tiếp tới **bí mật dữ liệu, tính toàn vẹn và độ sẵn sàng**.

Công nghệ thường gặp:

- **JPDA** (*Java Platform Debugger Architecture*) là kiến trúc gồm giao diện JVM và debugger.
- **JDWP** (*Java Debug Wire Protocol*) trao đổi lệnh/sự kiện giữa debug agent trong JVM và chương trình debugger.
- **JDI** (*Java Debug Interface*) là API mức Java mà nhiều công cụ/IDE sử dụng để điều khiển phiên debug.
- **JVM TI** cung cấp các khả năng tầng JVM cho agent, trong đó có các khả năng debugger cần.
- **`dt_socket`** là cơ chế vận chuyển JDWP qua TCP socket; chính cổng listener này cần bảo vệ.

**Nguyên tắc mặc định:** không bật JDWP trên tiến trình production đang phục vụ. Nếu cần ngoại lệ phục vụ sự cố nghiêm trọng, phải được phê duyệt, giới hạn thời gian, thu hẹp đường truy cập, có người trực điều phối và kế hoạch đóng cổng. Việc debugger thuận tiện cho lập trình viên **không** có nghĩa nó an toàn trong môi trường nhiều người dùng.

### Mục tiêu học tập

Sau bài này bạn có thể:

1. Giải thích vì sao JDWP là một kênh điều khiển nhạy cảm, không phải HTTP API cần password.
2. Phân biệt `address=127.0.0.1:5005`, `address=5005` và `address=*:5005` trên JDK hiện đại; kiểm tra cổng bind thực tế.
3. Hiểu `server=y`, `suspend=n`, `allow`, firewall, SSH tunnel và các lớp phân quyền; biết giới hạn của từng lớp.
4. Đánh giá tác động của breakpoint, `Suspend All`/`Suspend Thread`, step, watchpoint và evaluate expression trên service đang chạy.
5. Thực hiện một phiên debug có chủ sở hữu, phạm vi, thời hạn, tiêu chí dừng và xác nhận đóng.
6. Chạy ví dụ Java 17+ không phơi cổng debug ra mạng: chứng minh chương trình vẫn xử lý request khi không bị tạm dừng, và nhận biết rủi ro khi dừng thread.
7. Ưu tiên JFR, metrics, trace, log hoặc thread dump khi các cách đó đã đủ trả lời câu hỏi mà không phải mở JDWP.

**Phạm vi:** bảo vệ cổng debug và kiểm soát ảnh hưởng khi gắn debugger vào một JVM đang phục vụ. Bài không hướng dẫn khai thác cổng lộ thiên, không coi việc truy cập tiến trình không thuộc quyền quản trị là bài thực hành.

## 2. Mô hình rủi ro: ba tính chất đều có thể bị ảnh hưởng

| Tài sản | Người có quyền debugger có thể tác động thế nào? | Tình huống |
| --- | --- | --- |
| **Confidentiality** (bí mật) | Xem object, biến local, header, token, kết nối, giá trị cấu hình, dữ liệu khách hàng trên heap | Một biến access token hoặc chuỗi SQL được hiển thị trong IDE |
| **Integrity** (toàn vẹn) | Đánh giá code có side effect; sửa giá trị trường hoặc trạng thái tùy khả năng debugger/JVM | Evaluate một getter có ghi cache; thay trạng thái đơn hàng |
| **Availability** (sẵn sàng) | Tạm dừng tất cả thread, dừng thread giữ lock, gây timeout và lỗi health check | Breakpoint trên đường request nóng khiến nhiều request xếp hàng |
| **Độ tin cậy điều tra** | Debugger thay timing và lịch trình, làm race condition biến mất hoặc xuất hiện | Deadlock/race chỉ xảy ra ngoài phiên debug |
| **Governance** | Kết nối qua đường không được ghi audit, file đính kèm/ảnh chụp chứa dữ liệu thật | Screenshot IDE lộ PII trong ticket |

JDWP socket của triển khai HotSpot thông dụng **không cung cấp xác thực người dùng hay mã hóa TLS tích hợp như một kênh quản trị doanh nghiệp**. Không có trường username/password trong chuỗi cấu hình JDWP làm nhiệm vụ bảo vệ tài khoản. Vì thế phải coi người nào có thể kết nối thành công là người có quyền điều khiển rất mạnh trên tiến trình. Phải dựa vào **khả năng tiếp cận mạng được hạn chế, phân quyền hệ điều hành/hạ tầng và đường vận chuyển an toàn**.

> Cần tách bạch: `allow=...` trên socket transport của JDWP là bộ lọc **địa chỉ IP/subnet**, không phải cơ chế xác thực danh tính hay mã hóa. Có firewall và private subnet cũng không đủ nếu nhiều người/dịch vụ không tin cậy có thể truy cập từ subnet đó.

### Sự khác biệt giữa debug port và service port

~~~text
                     Lưu lượng nghiệp vụ bình thường
Client -----------> :8080 (HTTP/TLS; được định tuyến qua gateway)
                      |
                      v
                   Java service
                      ^
                      |  JDWP điều khiển JVM, không phải endpoint REST
                      |
                  :5005 (JDWP)
                      ^
                      |
                Chỉ debugger được ủy quyền, tốt nhất qua localhost
                và kênh SSH/VPN có kiểm soát, theo phiên ngắn hạn
~~~

Không đặt `:5005` sau một public LoadBalancer, Ingress, NodePort hay firewall rule mở rộng chỉ để IDE “dễ kết nối”. JDWP không trở nên an toàn chỉ vì service port `:8080` đã bật HTTPS.

## 3. Tùy chọn JDWP trên JDK 17/21

Cú pháp khởi chạy một JVM với agent:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 MyApplication
~~~

Ở đây `MyApplication` là **tên class Java có main** hoặc thay bằng `-jar app.jar` trong ứng dụng tương ứng. Lệnh này là ví dụ cho **môi trường được ủy quyền**, không phải cấu hình mặc định cho production.

| Tùy chọn | Ý nghĩa | Quy tắc thực hành |
| --- | --- | --- |
| `-agentlib:jdwp` | Nạp JDWP agent vào JVM | Không nạp nếu không có yêu cầu được phê duyệt |
| `transport=dt_socket` | Dùng TCP socket | Socket là tài sản cần quản trị như cổng nhạy cảm |
| `server=y` | JVM **lắng nghe** debugger attach | Chỉ listener ở giao diện mạng thực sự cần |
| `server=n` | JVM kết nối **ra** debugger đang chờ | Không tự động bảo mật; phải xem topology, auth và quyền đầu xa |
| `address=127.0.0.1:5005` | Bind trên IPv4 loopback, port 5005 | Phù hợp lab/cổng nội bộ với đường truy cập được kiểm soát |
| `address=5005` | Theo tài liệu JDK 17/21, hostname rỗng dùng **local loopback** | Vẫn nên ghi host tường minh để người vận hành dễ audit |
| `address=*:5005` | Bind **mọi network interface** | Không sử dụng trên service production; rủi ro lộ cổng cao |
| `suspend=n` | Không yêu cầu treo VM lúc khởi động chờ debugger | Tránh trì hoãn startup; không ngăn breakpoint gây treo sau đó |
| `suspend=y` | VMStartEvent yêu cầu suspend toàn VM trước khi main chạy | Dễ làm service không khởi động/không healthy nếu chưa attach |
| `allow=IP/subnet` | Giới hạn IP nguồn được phép theo JDWP socket transport | Defense-in-depth, **không phải** authentication hoặc TLS |
| `timeout=...` | Timeout attach/chờ kết nối tùy chế độ transport | Không phải TTL phiên debug hay giới hạn thời gian breakpoint |

**Cực kỳ quan trọng về phiên bản:** cú pháp và địa chỉ mặc định thay đổi qua các bản Java. Tài liệu JDK 17/21 cho ví dụ `address=8000` chỉ nghe trên loopback; không áp quy tắc đó bừa bãi cho JDK 8 hoặc bản JVM khác. Trước khi cấu hình, kiểm tra:

~~~bash
java -version
java -agentlib:jdwp=help
~~~

Lệnh help nhằm xem option JDWP do JVM hiện tại hỗ trợ, không mở phiên debug ứng dụng. Trên JVM đang chạy, bạn còn phải kiểm tra command line được deploy thực tế và **cổng đang listen thật**, thay vì dựa vào YAML/template chưa chắc đã được áp dụng.

### 3.1. Vì sao `suspend=n` vẫn không làm debugger “non-intrusive”?

`suspend=n` chỉ mô tả **hành vi khi VM khởi động**. Khi đã attach, breakpoint có thể áp dụng chính sách suspend thread hoặc toàn JVM. Một dòng cài `suspend=n` không ngăn một người trong IDE bấm Pause, thêm breakpoint ở hàm nhiều request đi qua, dùng Step Into hàng trăm lần hay Evaluate biểu thức có tác dụng phụ.

Cũng không có nghĩa `server=n` an toàn hơn `server=y` theo mặc định: với `server=n`, JVM chủ động kết nối tới debugger endpoint; nếu đầu xa không được quản lý và bảo vệ, người nhận kết nối vẫn có quyền debug rất mạnh.

### 3.2. Sự khác biệt giữa `allow` và firewall

- `allow` được JDWP socket transport xử lý theo IP nguồn/subnet.
- Firewall hoặc security group giới hạn ingress/egress của host/pod/node theo policy mạng.
- SSH/VPN/bastion có thể cung cấp kênh truyền đã xác thực, mã hóa và audit kết nối.
- RBAC của Kubernetes quyết định ai có thể thực hiện hành động quản trị như port-forward, nhưng không thay thế quyền trong chính JVM.
- OS user, pod security context và permission của tiến trình ảnh hưởng ai có thể cấu hình, khởi động, dừng hoặc attach công cụ quản trị.

Không lớp nào biến JDWP thành API có role “chỉ xem”. Khi đã kết nối đến JDWP, debugger có thể có khả năng điều khiển toàn tiến trình. **Defense in depth** có nghĩa giảm khả năng tiếp cận, ghi rõ ai được dùng và dừng nhanh nếu có sai lệch.

## 4. Chọn phương án theo mức rủi ro

| Môi trường | Mức khuyến nghị | Cách tổ chức |
| --- | --- | --- |
| Máy học cá nhân / môi trường test cô lập | Chấp nhận với kiểm soát cơ bản | `127.0.0.1`, cổng tạm, không chứa dữ liệu thật, đóng sau buổi học |
| Staging gần production | Có thể dùng khi được cấp phép | Namespace/network riêng, dữ liệu đã giảm nhạy cảm, lịch thu hẹp |
| Production đang phục vụ | **Mặc định không JDWP** | Ưu tiên metrics/log/traces/JFR/thread dumps, tái hiện lỗi trên canary |
| Production gặp sự cố nghiêm trọng không tái hiện được | Ngoại lệ có kiểm soát | Phê duyệt sự cố, owner/on-call, thời gian và phạm vi giới hạn, rollback/cleanup |
| Pod hoặc VM chứa dữ liệu nhạy cảm cao | Tránh attach trực tiếp | Isolated replica/canary với dữ liệu tối thiểu; đánh giá bảo mật riêng |

Chọn phương án theo **câu hỏi chẩn đoán**. Nếu chỉ cần biết thread nào đang chờ lock, một thread dump từ công cụ phù hợp thường an toàn hơn dừng toàn bộ VM bằng debugger. Nếu cần biết phương thức nào tiêu tốn CPU, JFR hoặc sampling profiler thường có ít tác động hơn việc bước từng dòng. Nếu cần inspect một giá trị không có trong telemetry, xem có thể bổ sung custom metric/log đã lọc trên canary trước khi mở JDWP production.

Không tự suy “JFR không overhead” hay “thread dump không tác động”: mọi công cụ chẩn đoán đều có chi phí, nhưng quyền kiểm soát và khả năng làm hệ thống dừng của debugger thường lớn hơn.

## 5. Bảo vệ cổng ở các lớp mạng và hạ tầng

### 5.1. Bind loopback và kiểm tra listener thật

Đối với JDK 17+ HotSpot, ví dụ an toàn hơn cho một lab đơn máy là:

~~~bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DebugPortSafetyDemo 30
~~~

JVM mở JDWP trên loopback **của network namespace nơi JVM chạy**. Trên một Linux host, có thể kiểm tra trong đúng namespace:

~~~bash
# Chỉ quan sát, không thay đổi service.
ss -lntp | grep ':5005'
~~~

Mong muốn là local address **`127.0.0.1:5005`**, không phải `0.0.0.0:5005`, `*:5005` hoặc địa chỉ public. Danh sách socket còn phụ thuộc quyền người xem và OS; không thấy process name không có nghĩa listener chắc chắn an toàn. Trên Windows có thể quan sát bằng PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 5005 -State Listen |
  Select-Object LocalAddress, LocalPort, OwningProcess
~~~

**Địa chỉ lắng nghe là một điều kiện, không phải toàn bộ kiểm thử.** Reverse proxy, NAT, port mapping, SSH forwarding, container port publish hoặc hostNetwork có thể tạo đường đến cổng mà bạn không lường trước. Cần xem đường từ workstation → bastion → host → container/pod → JVM và kiểm tra quy tắc thực tế ở từng bước.

Chỉ gọi các thao tác quan sát mạng trên hệ thống thuộc quyền quản trị của bạn; không quét cổng hoặc thử attach vào tiến trình không được phép.

### 5.2. Đường SSH tunnel có kiểm soát

Với một host do đội vận hành quản lý, JVM chỉ nghe trên loopback của **remote host** và debugger chạy trên máy kỹ sư được cho phép, có thể dùng SSH local forwarding để không cần public JDWP:

~~~bash
# Chạy tại workstation của kỹ sư có quyền SSH tới máy đích.
# Chỉ công bố đầu local 127.0.0.1; đầu xa là loopback của SSH server.
ssh -N -L 127.0.0.1:5005:127.0.0.1:5005 debug-user@approved-host
~~~

IDE kết nối tới `127.0.0.1:5005` **ở workstation**. Đầu xa của tunnel được SSH server kết nối tới `127.0.0.1:5005` **trên remote host**.

Điều kiện bắt buộc:

1. Dùng kênh SSH có xác thực và host key được kiểm tra; quyền debug-user hạn chế, có log/audit theo policy.
2. Xác minh JVM lắng nghe đúng loopback trên remote host; SSH vào host không tự chuyển tiếp tới loopback **bên trong container** nếu network namespace khác.
3. Đầu local không bị bind `0.0.0.0`; kiểm tra có forward khác, proxy khác hoặc port conflict hay không.
4. Tunnel chỉ tồn tại trong cửa sổ xử lý sự cố; đóng tunnel và loại bỏ debug agent/config khi kết thúc.
5. SSH tunnel **bảo vệ đoạn mạng qua SSH**, không thêm authentication vào bản thân JDWP phía sau; người có quyền mở tunnel có quyền rất cao với JVM.

VPN riêng cũng có thể bảo vệ transport nhưng không tự biến JDWP thành an toàn; nếu VPN mở cho nhiều máy/người, một JDWP listener trực tiếp trên private IP vẫn rất nhạy cảm. Không “giải quyết” bằng cách mở `*:5005` cho cả VPN rồi coi như chỉ có kỹ sư.

### 5.3. Container và Kubernetes

Ba khái niệm khác nhau:

- **Bind address bên trong pod:** `127.0.0.1:5005` nghĩa là loopback của network namespace pod, không nhất thiết là loopback của node hay workstation.
- **Port publishing:** Docker `-p 5005:5005` có thể tạo listener hoặc NAT tại host; cần xem interface host đang publish. Không dùng cấu hình đó mặc định cho JDWP.
- **Kubernetes port-forward:** `kubectl port-forward` là hành động quản trị qua Kubernetes API, phụ thuộc RBAC và đường quản trị cluster. Nếu cho phép, nó có thể cung cấp đường tới cổng của pod mà không mở Ingress/Service bên ngoài.

Ví dụ **chỉ dành cho namespace và pod staging được phê duyệt**:

~~~bash
# Thiết lập từ workstation đã đăng nhập cluster với quyền tương ứng.
# kubectl mặc định bind vào localhost; ghi tường minh để dễ kiểm tra.
kubectl port-forward --address localhost pod/staging-java-pod 5005:5005
~~~

Không đổi thành `--address 0.0.0.0` để nhiều người trong mạng LAN cùng dùng; đó là việc mở đầu local ra mọi interface. Không tạo Service `NodePort`/`LoadBalancer` hoặc Ingress chỉ cho debug. Cần xét RBAC `pods/portforward`, service account, audit log, network namespace, quyền host và mục tiêu phê duyệt.

**Giới hạn quan trọng:** quyền `port-forward` vào pod là một đường truy cập mạnh. Không suy “NetworkPolicy đang chặn port 5005 nên người có quyền port-forward không thể debug”; đường traffic quản trị có đặc tính riêng và cần kiểm tra policy thực tế. Nếu không hiểu network topology, dừng và trao đổi với đội platform/security.

### 5.4. Kênh debug trên máy dùng chung

Bind loopback **giảm phạm vi mạng**, nhưng không phân quyền giữa các người dùng hoặc process có quyền truy cập loopback trên cùng host. Trên máy multi-tenant, account không tin cậy chạy cùng network namespace có thể là rủi ro. Hãy cô lập môi trường theo user/container/VM và quyền process. Với hệ thống có dữ liệu bí mật, **localhost không đồng nghĩa “chỉ có tôi”.**

## 6. Hạn chế tác động của debugger lên tiến trình đang phục vụ

Bảo vệ cổng giải quyết câu hỏi **ai có thể điều khiển**. Hạn chế thao tác debug giải quyết câu hỏi **người được phép sẽ làm ảnh hưởng hệ thống đến mức nào**.

### 6.1. Breakpoint có thể dừng toàn JVM

Trong JDI, mỗi event request có một `suspendPolicy`:

| Chính sách | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| `SUSPEND_ALL` | Tạm dừng mọi thread khi event được phát | Service có thể ngừng xử lý request/health, gây hàng loạt timeout |
| `SUSPEND_EVENT_THREAD` | Chỉ tạm dừng thread phát event | Có thể cô lập phần nào, nhưng thread đó có thể đang giữ lock hoặc resource quan trọng |
| `SUSPEND_NONE` | Không tạm dừng thread do event đó | Phù hợp quan sát không treo từ một số event request, không phải “read-only security mode” |

Theo JDI `EventRequest`, mặc định của event request là `SUSPEND_ALL` nếu không đổi chính sách. IDE có thể đặt UI “Suspend All” hoặc “Suspend Thread”; phải **xác minh setting của breakpoint thực tế**, không dựa vào tên IDE. Khi debugger giữ một thread đang sở hữu monitor hoặc lock, thread khác có thể chờ khóa và trải nghiệm service vẫn bị ngưng dù đã chọn suspend một thread.

~~~text
Request A -> Thread-17 giữ lock OrderCache
                     |
                     +--- BREAKPOINT (Suspend Thread) --- [dừng]
                     |
Request B -> Thread-22 đợi OrderCache ---------------> timeout
Health check -> Thread-24 nếu cần cùng lock ---------> có thể timeout
~~~

Vì vậy **“Suspend Thread” giảm phạm vi nhưng không bảo đảm an toàn**. Không cài breakpoint ở vùng global lock, transaction, code xử lý lượng lớn request hoặc sau khi đã giữ connection/lease lâu dài.

### 6.2. Một số thao tác dễ gây rủi ro

| Hành động | Điều có thể xảy ra | Khuyến nghị |
| --- | --- | --- |
| Breakpoint không điều kiện ở hot path | Mỗi request vướng breakpoint, hàng loạt request bị dừng | Tránh trên production; nếu buộc dùng, lọc điều kiện rất hẹp |
| Conditional breakpoint | IDE có thể đánh giá điều kiện trên JVM đích, tiêu thụ CPU và có side effect | Không gọi method có tác dụng phụ; xem điều kiện có đắt không |
| Evaluate Expression | Có thể gọi method, thay đổi object/DB/cache hoặc kích hoạt code không mong muốn | Mặc định **không evaluate** biểu thức tùy ý trên production |
| Set Value / Change State | Thay đổi dữ liệu sống làm mất toàn vẹn logic | Cấm khi mục tiêu chỉ là chẩn đoán; quy trình thay đổi riêng nếu cần |
| Step Into/Over liên tục | Phá vỡ timing, tăng thời gian giữ khóa, làm request timeout | Tái hiện trên staging/canary; dùng sampling/tracing trước |
| Watchpoint/method-entry rộng | Event volume cao và overhead lớn | Giới hạn package/thread/instance, tắt ngay khi có bằng chứng |
| HotSwap / Reload class | Có thể không thành công hoặc làm đổi code đang chạy; giới hạn JVM | Không coi là phương tiện hotfix production; dùng deploy chuẩn |
| Inspect biến nhạy cảm | Bí mật có thể xuất hiện trong IDE, history, screenshot, logs | Chỉ xem dữ liệu cần thiết; không chụp/lưu/đính kèm secrets |
| Pause VM thủ công | Dừng thread của cả ứng dụng | Không thực hiện nếu không có phê duyệt tác động rõ ràng |

**Không có “cửa sổ debug không side effect” chỉ vì người dùng định quan sát.** Một biểu thức như `order.getTotal()` có thể bình thường nếu getter thuần, nhưng method Java có thể lazy-load, cấp phát, gọi DB hoặc sửa cache. Không thể khẳng định getter có/không tác dụng phụ chỉ từ tiền tố `get`.

### 6.3. Ngân sách dừng và tình huống sự cố dây chuyền

Giả sử một service nhận 500 request/giây. Một breakpoint `SUSPEND_ALL` dừng 10 giây ngay lúc tải ổn định: theo ước tính đơn giản, có thể có **khoảng 5.000 lượt request đến trong thời gian bị dừng**. Kết quả thực phụ thuộc load balancer, queue capacity, timeout, retry và khả năng điều hướng sang replica khác; số 5.000 chỉ minh họa công thức `rate × duration`, không phải số request chắc chắn lỗi.

Tác động không chỉ ở JVM:

- Client có thể timeout và tự retry làm tăng tải sau khi resume.
- Circuit breaker có thể mở; health/liveness probe có thể đánh dấu pod không khỏe.
- Lock/transaction/lease timeout dẫn đến rollback, deadlock hoặc cạnh tranh.
- Dừng một replica trong cụm ít replica có thể làm quá tải các replica còn lại.
- Debugger không tự khôi phục tất cả trạng thái khi có network disconnect hoặc khi người thao tác rời máy.

**Mục tiêu phiên debug sống:** nếu được phê duyệt, chỉ thao tác quan sát ngắn trong giới hạn SLO; người điều phối phải theo dõi khả năng resume ngay, biết cách đóng kết nối và dừng experiment. Nếu pause đã vượt ngân sách hoặc error rate tăng, ưu tiên phục hồi dịch vụ.

### 6.4. Quy định “read-only” thực tế

Một quy tắc nhóm “chỉ xem biến” chỉ có hiệu quả nếu đi kèm phân quyền người tham gia, huấn luyện, checklist và giám sát; JDWP không cung cấp RBAC fine-grained “được inspect nhưng cấm set value/evaluate”. Đừng ghi `readonly=true` vào một cấu hình tự nghĩ rồi xem như có quyền hạn chế.

Nếu nhu cầu chỉ là quan sát, thay JDWP bằng **JFR, metrics, tracing, logs có lọc, thread dump** hoặc snapshot đã được phê duyệt thường phù hợp hơn. Chọn công cụ theo loại câu hỏi thay vì cho mọi kỹ sư attach debugger vào process thật.

## 7. Ví dụ thực hành Java 17+: dịch vụ HTTP nhỏ để thấy ranh giới ảnh hưởng

Bài lab chạy hoàn toàn trên **loopback**, tạo HTTP server tạm với endpoint `/health` và `/work`, gửi hai request nội bộ, rồi tắt server. Dữ liệu là giả lập; **không dùng production, không mở debug port công khai**.

Mục tiêu:

- Bình thường: `/health` và `/work` trả về HTTP 200, request count bằng 1.
- Khi chủ động bật JDWP loopback và gắn debugger có quyền: đặt breakpoint ở handler `/work`, quan sát khác nhau giữa `Suspend All` và `Suspend Thread`; chỉ thực hiện trên **máy test cô lập**.
- Nhận ra `suspend=n` không ngăn breakpoint dừng khi đã attach.
- Dùng `try/finally` dừng HTTP server và worker executor; không để demo tồn tại vô hạn.

Tạo tệp **`DebugPortSafetyDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public final class DebugPortSafetyDemo {
    private static final AtomicInteger COMPLETED = new AtomicInteger();

    private static void respond(HttpExchange exchange, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        try (exchange) {
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        int attachWindowSeconds = args.length == 0 ? 0 : Integer.parseInt(args[0]);
        if (attachWindowSeconds < 0 || attachWindowSeconds > 120) {
            throw new IllegalArgumentException("Attach window must be 0..120 seconds");
        }

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        server.setExecutor(workers);
        server.createContext("/health", e -> respond(e, "OK"));
        server.createContext("/work", e -> {
            int id = COMPLETED.incrementAndGet(); // Breakpoint location.
            respond(e, "work-" + id);
        });
        server.start();

        try {
            if (attachWindowSeconds > 0) {
                System.out.println("attachWindowSeconds=" + attachWindowSeconds);
                Thread.sleep(Duration.ofSeconds(attachWindowSeconds).toMillis());
            }
            int port = server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();
            HttpRequest health = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + port + "/health"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpRequest work = HttpRequest.newBuilder(
                    URI.create("http://127.0.0.1:" + port + "/work"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> r1 =
                    client.send(health, HttpResponse.BodyHandlers.ofString());
            HttpResponse<String> r2 =
                    client.send(work, HttpResponse.BodyHandlers.ofString());
            System.out.println("health=" + r1.statusCode() +
                               " body=" + r1.body());
            System.out.println("work=" + r2.statusCode() +
                               " body=" + r2.body());
            System.out.println("completed=" + COMPLETED.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
            System.out.println("stopped=true");
        }
    }
}
~~~

### 7.1. Chạy không có debugger

~~~bash
javac DebugPortSafetyDemo.java
java DebugPortSafetyDemo
~~~

Stdout đã kiểm tra bằng **JDK 24** (phần Java API của ví dụ tương thích JDK 17+ có module `jdk.httpserver`):

~~~text
health=200 body=OK
work=200 body=work-1
completed=1
stopped=true
~~~

HTTP server bind vào `127.0.0.1` với port **0** để OS tự cấp một port đang trống. Port này không phải cổng JDWP; nó chỉ dùng trao đổi dữ liệu trong lab. Số port thực không in ra vì khác nhau giữa các lần chạy.

### 7.2. Chạy với JDWP chỉ trên loopback

Trên máy test được kiểm soát, trong một terminal:

~~~bash
# Chỉ chạy ở môi trường test, không dùng lệnh này cho production.
# Port JDWP cố định 5005, không có wildcard.
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 DebugPortSafetyDemo 30
~~~

JVM in một dòng trạng thái từ debug agent tương tự:

~~~text
Listening for transport dt_socket at address: 5005
attachWindowSeconds=30
~~~

Sau đó chương trình chờ tối đa 30 giây để bạn gắn debugger **từ chính máy test** bằng IDE, host `127.0.0.1` port `5005`, rồi tự gửi hai HTTP requests. Nếu không gắn debugger, các dòng cuối cùng giống phần 7.1. Nếu đặt breakpoint trong `/work` và không resume kịp, HTTP client có thể timeout và chương trình không in cùng stdout; **đó là kết quả cần quan sát, không phải lỗi của bài lab**.

**Lưu ý kiểm chứng:** JDK 24 đã chạy được ví dụ với JDWP trên loopback, kể cả cấu hình `address=127.0.0.1:0` để OS tự cấp port; lệnh `:5005` ở trên giúp IDE biết cổng. Nếu port 5005 đang bị dùng, đừng tắt/ghi đè process khác: hãy chọn một port loopback còn trống và cập nhật cả IDE.

Các bước trong IDE:

1. Tạo cấu hình *Remote JVM Debug/Attach* theo tên IDE, host `127.0.0.1`, port `5005`. Chỉ nối tới tiến trình lab đang chạy.
2. Đặt breakpoint ở dòng `int id = COMPLETED.incrementAndGet();`. Kiểm tra chính sách *Suspend* của breakpoint.
3. Lần đầu có thể chọn `Suspend Thread` để quan sát phạm vi; nhớ rằng chỉ một thread bị pause vẫn có thể gây ảnh hưởng do lock/resource trong code thực.
4. Chỉ pause ngắn và **Resume** ngay, không evaluate biểu thức có side effect; ghi lại thời điểm và phản ứng của request.
5. Sau đó detach, bảo đảm tiến trình kết thúc, và dùng công cụ OS xác minh listener JDWP đã biến mất.

Phần code dùng `HttpClient` với timeout 5 giây nhằm làm rõ hậu quả khi một breakpoint bị giữ quá lâu. **Tuy nhiên khi `Suspend All`, thread xử lý timer cũng có thể bị dừng**, nên không có cam kết timeout luôn xảy ra đúng sau 5 giây wall-clock; vì vậy cần người thao tác chủ động resume. Trên service thật, timeout ở load balancer hoặc hệ thống bên ngoài JVM còn có thể xảy ra trong lúc JVM bị treo.

### 7.3. Ý nghĩa của kết quả

| Quan sát | Kết luận đúng | Kết luận sai cần tránh |
| --- | --- | --- |
| Không bật debugger, hai HTTP 200 | Đường xử lý bình thường của lab hoạt động | “Ứng dụng production chắc chắn sẽ an toàn khi bật JDWP” |
| JDWP in “Listening ... 5005” | Agent đang nghe trên socket do cấu hình | “Có mật khẩu/mã hóa mặc định” |
| `suspend=n` nhưng breakpoint vẫn dừng | Startup không chờ debugger; breakpoint là cơ chế riêng | “suspend=n nghĩa là mọi breakpoint chỉ quan sát” |
| Pause thread `/work` khiến request chậm | Thread thực hiện request đã bị giữ | “Suspend Thread không ảnh hưởng user khác” |
| Detach xong service hoạt động | Phiên điều khiển hiện tại kết thúc | “Port JDWP đã đóng vĩnh viễn dù JVM còn chạy” |
| Process kết thúc và không còn listener | Cổng JDWP của process đã được tháo | “Không còn một instance khác đang chạy JDWP” |

Một điểm rất quan trọng: **Detach debugger không tương đương loại bỏ JDWP agent khỏi cấu hình khởi động**. Nếu service vẫn sống với `server=y`, listener có thể tiếp tục tồn tại hoặc được thiết lập lại tùy JDWP implementation/config; phải xác minh và dùng rollout/restart chuẩn để loại bỏ cờ debug. Không lấy thao tác Disconnect trong IDE làm bằng chứng đã khử rủi ro.

## 8. Quy trình cho phép ngoại lệ trên hệ thống đang phục vụ

Đây là **runbook có kiểm soát**. Mặc định chọn phương án không dùng debugger; chỉ đi tiếp nếu đã có quyết định vận hành phù hợp.

### 8.1. Trước phiên: phê duyệt và thiết lập phạm vi

Ghi vào incident/change record tối thiểu:

| Thuộc tính | Giá trị cần có |
| --- | --- |
| Mục đích | Câu hỏi kỹ thuật cụ thể không thể giải bằng JFR/log/metrics/traces |
| Phạm vi | Service, cluster, namespace/pod/VM, instance/PID, JDK/vendor |
| Owner | Kỹ sư debug, SRE/on-call giám sát, người phê duyệt |
| Thời hạn | Start/stop window và thời điểm buộc đóng, không để mở vô hạn |
| Dữ liệu | Phân loại sensitivity; có thể xem/ghi/đính kèm gì, không xem gì |
| Network | Loopback/tunnel/RBAC/firewall, source host nào được phép |
| Tác động chấp nhận | p95/p99/error rate, số request đang xử lý, pause budget |
| Rollback | Cách detach/resume, kill tunnel, tắt flag JDWP qua deploy chuẩn |
| Audit | Nơi lưu log về phê duyệt, phiên, thời điểm attach/detach và kết quả |

Không sao chép tài khoản/secret trong ticket hoặc command log. Với production có nhiều replica, cân nhắc cô lập một **canary replica** và định tuyến tải thấp hoặc dừng nhận traffic ở replica đó (theo policy) để giảm blast radius. Đừng tắt ngẫu nhiên liveness probe hay thay đổi pool chỉ để debugger dễ dùng; mỗi thay đổi có thể tăng rủi ro vận hành.

### 8.2. Trước phiên: kiểm tra kỹ thuật

1. Xác định process/PID và container/network namespace **chính xác**. Đừng dùng PID của sidecar hoặc JVM khác.
2. Xác minh version với `java -version` và cú pháp `java -agentlib:jdwp=help` trên image tương đương; kiểm tra cờ debug hiện tại.
3. Kiểm tra JDWP listener chỉ bind ở interface mong muốn trong namespace của JVM, không có port publish ra public; kiểm tra security group, firewall, service mesh/proxy nếu có.
4. Xác minh một kênh quản trị **được phép** (SSH tunnel/port-forward có RBAC) với endpoint local loopback; audit người dùng.
5. Thống nhất thời gian breakpoint tối đa, không evaluate/set state, người theo dõi SLO và người có quyền yêu cầu abort.
6. Kiểm tra khả năng Resume/Disconnect/rollback trước khi người dùng mở debugger.
7. Nếu JVM chưa bật JDWP, đừng “thử” một lệnh `jcmd` tùy ý hoặc gắn agent trong production. Kích hoạt agent có thể cần thay đổi cách launch/restart theo JVM và policy; phải lập change riêng, không suy nó luôn hỗ trợ enable động.

### 8.3. Trong phiên: thu bằng chứng có giới hạn

- Chỉ đặt breakpoint ở vị trí/điều kiện đã được thẩm định; tránh hot path, lock, transaction dài và khối đồng bộ.
- Ưu tiên breakpoint có điều kiện hẹp hoặc logpoint/tracepoint **nếu đã hiểu rõ overhead và đánh giá biểu thức**. Không coi logpoint là an toàn tuyệt đối.
- Nếu cần quan sát đồng thời nhiều thread, xem thread dump/trace thay vì pause all.
- Quan sát p99, throughput, error rate, health/readiness, request queue, transaction timeouts và alarm của downstream.
- Khi thấy SLO vượt ngưỡng, pause kéo dài bất thường hoặc rò rỉ dữ liệu, **Resume/Abort ngay** theo runbook; đừng chờ chụp đủ screenshot.
- Chỉ ghi nhận thông tin cần để xác định nguyên nhân; không lưu token, PII, memory dump hoặc nguyên bộ object graph vào kênh công khai.

### 8.4. Sau phiên: đóng, kiểm chứng và báo cáo

1. Resume mọi thread đang pause, dỡ breakpoint/watchpoint và detach IDE.
2. Dừng SSH tunnel/port-forward và thu hồi quyền tạm theo change.
3. Gỡ `-agentlib:jdwp` khỏi cấu hình triển khai; nếu cần, rollout/restart có kiểm soát để **không còn agent listener**. Không restart bất ngờ một JVM sản xuất.
4. Xác minh lại bind/port trong namespace thật (ví dụ `ss -lntp` hoặc `Get-NetTCPConnection`); kết hợp inventory cấu hình và kiểm tra hạ tầng.
5. Xác minh traffic, error rate, p99, health và queue trở lại ngưỡng chấp nhận. Theo dõi trễ sau phiên do retry/backlog đã tích lũy.
6. Ghi lại ai đã tham gia, thời gian, bằng chứng tối thiểu, tác động thực, root cause/hypothesis và biện pháp xử lý lâu dài.
7. Xóa hoặc đặt retention đúng chính sách cho screenshot, debug logs và bản sao chẩn đoán.

**Điều kiện hoàn tất không phải “debugger đã ngắt”.** Điều kiện hoàn tất là phiên đã kết thúc, quyền tạm thu hồi, listener không còn lộ, flag không còn trong deployment target, SLO trở lại bình thường và dữ liệu nhạy cảm được xử lý đúng.

## 9. Tình huống và quyết định

### Tình huống A: cổng 5005 đang lắng nghe trên `0.0.0.0`

Dấu hiệu: trong namespace của JVM, `ss` hoặc công cụ tương đương báo debug listener bind mọi IPv4 interface. Đây là **sự cố cấu hình cần ưu tiên xử lý**, nhất là nếu security group/firewall/port publishing cho phép truy cập từ mạng khác.

Hành động: hạn chế đường truy cập mạng theo quy trình khẩn cấp có quyền, đánh giá ai có thể đã tiếp cận, rồi loại bỏ cấu hình wildcard qua triển khai đã phê duyệt. Không chứng minh an toàn bằng cách “thử đăng nhập” vào cổng từ máy lạ. Nếu nghi có người đã điều khiển trái phép, tuân theo quy trình an ninh thay vì tự điều tra bằng cách gửi lệnh debug.

### Tình huống B: cổng bind loopback nhưng pod có `kubectl port-forward`

Loopback trong pod giảm bề mặt công khai; tuy nhiên ai có RBAC đủ để port-forward có thể tạo đường vào. Kiểm tra quyền `pods/portforward`, audit API server, công cụ truy cập và thời hạn của phiên. Không thêm Service type LoadBalancer để “đỡ cần port-forward”.

### Tình huống C: một breakpoint `Suspend Thread` nhưng p99 vẫn tăng

Thread được dừng có thể giữ lock, connection hoặc transaction. Other threads chờ tài nguyên này dẫn đến domino. Kiểm tra lock owners, thread stack, pool saturation và log timeout; resume ngay. Không suy chỉ `Suspend All` mới gây outage.

### Tình huống D: engineer chỉ cần biết thread nào bị block

Dùng thread dump theo công cụ phù hợp (`jcmd <pid> Thread.print` trên HotSpot khi được phép), thread states, JFR lock events và metrics trước. Nếu chúng đủ phân biệt blocked/runnable/waiting, **không bật JDWP** chỉ để mở thread view trong IDE.

### Tình huống E: cần xem một biến chỉ tồn tại trên production

Cân nhắc một event/log có lọc hoặc snapshot tối thiểu trên canary, giới hạn cardinality và dữ liệu nhạy cảm. Nếu bắt buộc debugger, người owner cần phê duyệt cụ thể về phạm vi quan sát và tác động. Không “đánh giá thử” method trực tiếp trong JVM nhằm lấy biến vì có thể thực thi business logic ngoài mong muốn.

## 10. Các lỗi phổ biến

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `address=*:5005` để IDE dễ attach | Cổng có thể được truy cập qua mạng không mong muốn | Loopback + đường quản trị có kiểm soát; tốt nhất không bật production |
| Cho rằng `suspend=n` chống mọi pause | Breakpoint/IDE vẫn có thể dừng VM hoặc thread | Kiểm tra `suspendPolicy`, đặt pause budget |
| Cho rằng private VPC = JDWP có authentication | Nhiều workload/người cùng subnet có thể truy cập | Segmentation, RBAC, SSH, audit, remove listener |
| Dùng `allow=...` như mật khẩu | IP filter không xác thực danh tính hay mã hóa | Giữ tunnel/VPN an toàn và kiểm soát nguồn |
| Bind loopback trong pod nhưng publish port từ host | Bề mặt thực tế có thể khác với dự kiến | Kiểm tra namespace, NAT/port mapping và firewall |
| Detach IDE rồi coi port đã đóng | Agent/JVM có thể tiếp tục listen | Gỡ debug flag, xác minh listener sau rollout |
| Set breakpoint trên mọi request | Tăng độ trễ, có thể dừng toàn cụm | Tránh hot path; dùng log/trace/JFR |
| Chọn Suspend Thread rồi coi an toàn 100% | Thread giữ lock/connection vẫn ảnh hưởng thread khác | Thiết kế vị trí an toàn, giới hạn thời gian |
| Evaluate một getter để “chỉ xem” | Getter có thể lazy-load/gọi DB/sửa cache | Không thực thi code tùy ý trong production |
| Chụp screenshot chứa token để gửi ticket | Rò rỉ dữ liệu nhạy cảm | Redact/minimize, quyền xem và retention |
| Bật debug flag qua `JAVA_TOOL_OPTIONS` toàn cluster | Có thể lan sang nhiều JVM, mở nhiều port | Thay đổi có phạm vi nhỏ, được review, có rollback |
| Không có người theo dõi dịch vụ khi debugger thao tác | Không phát hiện timeout/outage kịp | SRE/on-call quan sát SLO và quyền abort |
| Mở cổng debug trước rồi xin phê duyệt sau | Rủi ro đã phát sinh, khó audit | Phê duyệt và thiết lập controls **trước** |
| Cố sửa bug bằng HotSwap trên production | Khó audit/rollback, behavior khác build đã kiểm thử | Fix qua CI/CD và rollout chuẩn |

## 11. Tự kiểm tra và bài tập tình huống

**Câu 1.** Một JVM dùng `-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005`. Cờ `suspend=n` đã làm kết nối an toàn chưa? **Chưa.** Nó chỉ bỏ việc chờ debugger khi startup, còn `*:5005` có thể lắng nghe mọi interface và JDWP là kênh điều khiển mạnh.

**Câu 2.** `address=5005` trên Oracle/OpenJDK 21 có giống `address=*:5005`? **Không.** Tài liệu JDK 21 nói host rỗng dùng local loopback; wildcard nghe trên mọi interface. Vẫn phải kiểm tra listener thực tế và JDK cụ thể.

**Câu 3.** Một debugger có lựa chọn `Suspend Thread`. Nếu breakpoint dừng thread đang giữ monitor trên `OrderCache`, những request khác có chắc tiếp tục bình thường không? **Không.** Chúng có thể bị chặn khi chờ monitor đó.

**Câu 4.** Có thể thêm `allow=10.0.0.0/8` rồi phát hành port JDWP công khai không? **Không.** `allow` chỉ lọc IP; không xác thực hay mã hóa, và subnet có thể có nhiều nguồn không tin cậy. Trên production nên tắt JDWP hoặc dùng cửa sổ ngoại lệ rất hẹp.

**Câu 5.** Người vận hành chỉ cần lấy một thread dump. Có nhất thiết mở debug port không? **Không.** Trên HotSpot có thể dùng `jcmd <pid> Thread.print` khi được ủy quyền; cần đánh giá chi phí và quyền nhưng không yêu cầu JDWP listener.

**Câu 6.** Trong 12 giây pause-all, traffic trung bình 200 req/s. Tới khoảng bao nhiêu request theo mô hình đơn giản? **2.400 arrivals**. Không phải chắc chắn 2.400 request thất bại: còn phụ thuộc timeout, queue, cân bằng tải và retry.

**Câu 7.** Nếu debugger ngắt kết nối, JDWP có được gỡ hoàn toàn khỏi JVM không? **Không được mặc định.** Kiểm tra debug agent/config và listener; gỡ qua quy trình triển khai chính thức.

**Câu 8.** Một pod có listener `127.0.0.1:5005` nhưng team platform cấp quyền `pods/portforward` cho tất cả developer. Đây có phải điều kiện “chỉ người nội bộ được xem log” không? **Không.** Port-forward vào JDWP có thể trao quyền điều khiển JVM, phải xét RBAC và giới hạn người được phép.

**Câu 9.** Một kỹ sư chạy Evaluate `service.refreshCache()` khi đang xem biến. Đây có phải chỉ đọc không? **Không.** Có thể thực thi code sửa state và làm phát sinh I/O; không sử dụng như bước quan sát vô hại.

**Câu 10.** Một cấu hình mới đã gỡ `-agentlib:jdwp` khỏi manifest nhưng process cũ vẫn chạy. Kết luận “cổng đã tắt” có đúng không? **Không.** Cần kiểm tra instance đang chạy, rollout status và listener thực tế; manifest không đồng nghĩa trạng thái runtime.

## 12. Checklist ra quyết định và đóng phiên

Trước khi cho phép ngoại lệ live debug:

- [ ] Đã thử log/metrics/traces/JFR/thread dump hoặc reproduction staging trước.
- [ ] Sự cố, JVM cụ thể, kỹ sư, SRE, người phê duyệt và lý do đã được ghi.
- [ ] Cửa sổ thời gian hữu hạn; có pause budget, SLO guardrails và người có quyền abort.
- [ ] JDWP bind loopback trong đúng network namespace, không wildcard/public/NodePort/LoadBalancer.
- [ ] Đường truy cập có xác thực (SSH/VPN/bastion/cluster RBAC) và ghi audit tương ứng.
- [ ] Không coi `allow`, `suspend=n` hay “private network” là xác thực JDWP.
- [ ] Breakpoint/condition được review; không evaluate/set state/hot swap trong phiên quan sát.
- [ ] Đã dự kiến secret/PII trong biến và chính sách ghi nhận tối thiểu.
- [ ] Có phương án Resume, Disconnect, rollback và loại bỏ agent khi phiên kết thúc.

Sau phiên:

- [ ] Không còn thread bị pause, breakpoint/watchpoint và tunnel đã đóng.
- [ ] JDWP launch flag đã loại khỏi workload đích, rollout/restart chuẩn đã hoàn tất nếu cần.
- [ ] Đã kiểm tra listener thực tế không còn lộ, không chỉ dựa vào nút Disconnect.
- [ ] Latency, error rate, throughput, health đã ổn định và downstream không còn backlog do debug.
- [ ] Quyền tạm và artifact nhạy cảm đã được thu hồi/xóa đúng hạn.
- [ ] Báo cáo có kết luận, tác động và biện pháp tránh phải dùng JDWP trên production lần sau.

**Kết luận:** cổng JDWP là một **đường điều khiển JVM nhạy cảm**. Bảo vệ chỉ bằng port number, private subnet hoặc `suspend=n` là không đủ. Mặc định không bật trên tiến trình đang phục vụ; nếu được phép dùng như ngoại lệ, hãy **giới hạn đường truy cập, giới hạn hành động, giới hạn thời gian, có người giám sát và xác minh đóng sạch**.

## Tài liệu đối chiếu

- Oracle Java SE 21: [JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/21/docs/specs/jpda/conninv.html) — `-agentlib:jdwp`, `dt_socket`, `server`, `address`, `allow`, `suspend`, `timeout` và sự khác nhau giữa loopback/wildcard.
- Oracle Java SE 17: [JDWP/JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html) — kiểm tra hành vi của JDK 17.
- Oracle Java SE 17: [JDI EventRequest](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jdi/com/sun/jdi/request/EventRequest.html) — `SUSPEND_ALL`, `SUSPEND_EVENT_THREAD`, `SUSPEND_NONE`.
- Oracle Java SE 21: [Java Debug Wire Protocol](https://docs.oracle.com/en/java/javase/21/docs/specs/jdwp/jdwp-protocol.html) — bộ lệnh debugger và khả năng thao tác JVM.
- Kubernetes: [kubectl port-forward](https://kubernetes.io/docs/reference/generated/kubectl/kubectl-commands#port-forward) — default bind localhost, `--address` và các ví dụ chuyển tiếp.
- Oracle Java SE 21: [jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — các lệnh chẩn đoán như `Thread.print` khi có quyền.
