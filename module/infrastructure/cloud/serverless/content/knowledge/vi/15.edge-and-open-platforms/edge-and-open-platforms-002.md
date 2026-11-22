# Giới hạn runtime, vị trí dữ liệu và độ trễ tại edge

Edge computing đưa một phần xử lý đến gần người dùng hoặc thiết bị hơn thay vì thực hiện mọi việc tại một trung tâm dữ liệu khu vực. Với ứng dụng serverless, edge function có thể kiểm tra request, xác thực token, định tuyến, chuẩn hóa header, áp dụng cache hoặc chọn backend trước khi request đi sâu vào hệ thống. Cách này có thể giảm thời gian phản hồi và lưu lượng về origin, nhưng chỉ hiệu quả khi runtime, dữ liệu và đường đi mạng được thiết kế phù hợp.

Chạy code ở edge không đồng nghĩa mọi thành phần của ứng dụng đều ở gần người dùng. Function có thể chạy tại một điểm hiện diện (Point of Presence, PoP) gần client trong khi database vẫn ở một Region xa. Khi đó, request được xử lý nhanh ở bước đầu nhưng vẫn phải đi một quãng đường dài để đọc hoặc ghi dữ liệu. Vị trí tính toán, vị trí dữ liệu và vị trí người dùng phải được xem như ba yếu tố riêng.

Trong module **CLOUD_SERVERLESS**, người học phát triển và triển khai Java function được kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý quyền truy cập, trạng thái, retry, idempotency, cold start, mở rộng và chi phí. Bài này giải thích giới hạn runtime tại edge, data locality và latency, sau đó xây dựng cách phân chia công việc giữa edge và Java function chạy ở Region.

## 1. Edge computing trong kiến trúc serverless

Edge là lớp hạ tầng phân tán nằm gần người dùng, thiết bị hoặc mạng truy cập. Nhà cung cấp có thể triển khai code tại nhiều PoP, edge location hoặc khu vực mạng. Khi request đến, hệ thống định tuyến đến một điểm phù hợp rồi thực thi logic tại đó.

Các tác vụ phù hợp với edge thường có đặc điểm:

- Xử lý nhanh, ít trạng thái và không cần truy vấn dữ liệu nghiệp vụ phức tạp.
- Có thể quyết định từ thông tin trong request, token, header hoặc dữ liệu cache.
- Giảm số lần gọi origin hoặc giảm kích thước dữ liệu truyền về client.
- Có lợi khi thực thi gần người dùng ở nhiều quốc gia/khu vực.
- Có thời gian xử lý ngắn và ít phụ thuộc thư viện hệ điều hành.

Ví dụ điển hình là redirect theo vùng, rewrite URL, kiểm tra token, lọc bot, thêm security header, cache key normalization, chọn origin, trả nội dung tĩnh hoặc phục vụ dữ liệu công khai đã cache.

Các công việc thường phù hợp hơn với Region hoặc backend chuyên dụng:

- Giao dịch cần transaction và tính nhất quán mạnh.
- Truy vấn nhiều bảng hoặc join trên database tập trung.
- Tác vụ dài, xử lý batch, workflow nhiều bước hoặc chờ callback.
- Xử lý file lớn, ML inference nặng hoặc cần GPU.
- Java application phụ thuộc đầy đủ JVM, reflection, native library hoặc framework lớn.
- Công việc cần kết nối TCP tùy ý, filesystem bền vững hoặc thread chạy nền lâu dài.

### Sơ đồ request qua edge và Region

~~~mermaid
flowchart LR
    C[Client / device] --> P[Edge PoP]
    P --> E[Edge function]
    E -->|Cache hit| K[Edge cache]
    K --> C
    E -->|Cache miss / business request| R[Regional API / Java Function]
    R --> D[(Regional database)]
    R --> Q[Queue / workflow]
    Q --> W[Background workers]
    R --> E
    E --> C
~~~

Edge có thể kết thúc request tại cache hoặc thực hiện logic nhẹ trước khi chuyển đến Region. Regional API và Java function thường sở hữu nghiệp vụ, dữ liệu chuẩn và các side effect cần kiểm soát.

## 2. Runtime tại edge bị giới hạn như thế nào?

Không có một edge runtime chung cho mọi nhà cung cấp. Một nền tảng có thể dùng isolate JavaScript, nền tảng khác chạy WebAssembly, native sandbox hoặc container nhỏ. Runtime quyết định ngôn ngữ, API hệ thống, mô hình bộ nhớ và cách giới hạn tài nguyên.

Các nhóm giới hạn thường gặp:

| Nhóm giới hạn | Điều cần kiểm tra | Tác động đến thiết kế |
|---|---|---|
| CPU time | Thời gian CPU thực sự được phép dùng | Tránh vòng lặp nặng, mã hóa/giải mã lớn hoặc tính toán kéo dài |
| Wall-clock duration | Tổng thời gian invocation được phép tồn tại | Hạn chế chuỗi network call và công việc chờ lâu |
| Memory | Heap/linear memory và memory tổng | Giới hạn payload, cache trong process và cấu trúc dữ liệu |
| Request/response size | Kích thước header, body và response | Stream, giới hạn upload hoặc chuyển file trực tiếp đến object storage |
| Subrequest/network | Số lần gọi fetch, số kết nối, protocol được phép | Gộp request, cache và tránh gọi nhiều dịch vụ từ edge |
| Artifact/package | Kích thước bundle, module hoặc dependency | Loại thư viện thừa và tách code theo chức năng |
| API runtime | API có sẵn như fetch, crypto, cache, timers | Không giả định có đầy đủ API của Linux/JVM |
| Concurrency | Số request song song hoặc giới hạn theo tenant | Tránh state mutable dùng chung và bảo vệ origin |
| Storage | Dung lượng, latency, consistency và quota của KV/cache | Không coi local memory là storage bền vững |
| CPU architecture/ABI | Kiến trúc và interface của binary | Native executable phải tương thích môi trường triển khai |

Giá trị giới hạn cụ thể thay đổi theo nhà cung cấp, gói dịch vụ, runtime version và loại sản phẩm. Một con số trong tài liệu cũ hoặc một gói free không thể được dùng làm giả định cho production. Trước khi triển khai, kiểm tra quota hiện hành của đúng dịch vụ, Region, runtime và plan; đồng thời đo bằng artifact thật.

### CPU time khác wall-clock time

CPU time là thời gian code thực sự dùng CPU. Wall-clock time là thời gian từ lúc invocation bắt đầu đến khi kết thúc, bao gồm cả thời gian chờ network hoặc I/O. Một function có thể dùng rất ít CPU nhưng vẫn vượt wall-clock limit vì chờ một API chậm. Ngược lại, vòng lặp tính toán có thể tiêu thụ CPU limit dù không gọi mạng.

Đừng tối ưu chỉ bằng cách giảm số dòng code. Hãy xác định bottleneck là CPU, network, storage, cold start hay chờ origin rồi chọn biện pháp phù hợp.

### API hệ điều hành và runtime

Một số edge isolate không cung cấp process, filesystem tùy ý, raw socket, native thread, JNI hoặc toàn bộ API của Java Standard Library. Những API như fetch, Web Crypto và stream có thể được cung cấp theo mô hình riêng của runtime.

Code được viết cho JVM có thể phụ thuộc:

- Reflection, classpath scanning và dynamic class loading.
- JNI hoặc thư viện native được biên dịch cho một hệ điều hành/kiến trúc cụ thể.
- Thread, executor và scheduler sống lâu.
- Filesystem hoặc file tạm.
- Socket TCP/UDP tùy ý.
- Cơ chế TLS, DNS hoặc certificate store của hệ điều hành.
- Framework cần khởi tạo application context lớn.

Vì vậy, không thể mặc định một JAR Java có thể chạy nguyên trạng trong edge isolate. Chỉ triển khai Java trực tiếp khi sản phẩm edge công bố hỗ trợ runtime Java/JVM phù hợp. Nếu nền tảng chỉ hỗ trợ JavaScript hoặc WebAssembly, cần build và kiểm thử một artifact tương thích với runtime/ABI đó; biên dịch native hoặc WebAssembly không tự động bảo đảm mọi thư viện Java hoạt động.

## 3. Java function nên đặt ở edge hay Region?

Java thường được triển khai tự nhiên ở một managed runtime trong Region, nơi có JVM, framework và thư viện quen thuộc. Một số edge platform có thể chạy WebAssembly hoặc native artifact, nhưng đây là một mô hình triển khai khác và cần kiểm tra compatibility riêng.

Có thể phân chia trách nhiệm như sau:

| Nhiệm vụ | Edge | Regional Java function |
|---|---|---|
| Redirect, rewrite URL | Rất phù hợp | Có thể làm nhưng thường thêm network hop |
| Kiểm tra JWT signature/claim đơn giản | Phù hợp nếu key và policy có thể phân phối an toàn | Phù hợp cho policy phức tạp hoặc introspection |
| Cache nội dung công khai | Rất phù hợp | Origin tạo nội dung và cache policy |
| Authorization theo dữ liệu tenant phức tạp | Chỉ kiểm tra sơ bộ nếu có đủ context | Nên thực hiện tại service sở hữu dữ liệu |
| Transaction và cập nhật database | Thường không phù hợp | Phù hợp |
| Xử lý file lớn | Nên chuyển upload trực tiếp đến storage | Phù hợp để điều phối hoặc xử lý stream |
| Batch, workflow, retry dài hạn | Không phù hợp | Phù hợp với queue/workflow |
| Java framework/JVM đầy đủ | Chỉ khi runtime hỗ trợ rõ ràng | Thường là lựa chọn tự nhiên |
| Chọn Region/origin và thêm header | Rất phù hợp | Không cần là bước riêng nếu edge đã làm |

Một mẫu kiến trúc thực tế là edge xử lý request rẻ và stateless, sau đó chuyển request đã chuẩn hóa đến Java API trong Region. Java service xác thực quyền theo dữ liệu chuẩn, thực hiện transaction và phát message cho công việc bất đồng bộ.

### Đừng đặt business rule chuẩn ở nhiều edge PoP

Nếu mỗi PoP có một bản rule hoặc cache dữ liệu nghiệp vụ riêng, chúng có thể không cập nhật đồng thời. Hai request gần nhau nhưng đi qua hai PoP có thể nhận quyết định khác nhau. Các quyết định như số dư, trạng thái đơn hàng, quota sử dụng hoặc quyền truy cập cần dựa trên nguồn dữ liệu có consistency phù hợp, thường là service/database sở hữu nghiệp vụ.

Edge có thể áp dụng policy tĩnh hoặc dữ liệu đã ký/có thời hạn, nhưng kết quả đó cần có expiry, version và cơ chế thu hồi rõ ràng.

## 4. Data locality: vị trí xử lý không phải vị trí lưu dữ liệu

Data locality mô tả dữ liệu được lưu ở đâu, được đọc/ghi ở đâu và phải đi qua mạng nào để đến nơi xử lý. Khi function chạy tại edge, dữ liệu có thể vẫn nằm trong database ở một Region trung tâm.

Ví dụ, client ở Việt Nam gửi request đến edge PoP tại khu vực gần đó. Edge kiểm tra token trong vài mili giây, sau đó gọi database đặt ở một Region xa hơn. Phần xác thực nhanh không loại bỏ latency của truy vấn dữ liệu.

Cần tách ít nhất bốn vị trí:

1. **Client location:** người dùng hoặc thiết bị gửi request.
2. **Compute location:** PoP hoặc Region nơi code thực thi.
3. **Data location:** nơi database, object storage, cache hoặc queue lưu dữ liệu.
4. **Control/management location:** nơi log, trace, secret, backup và control plane được lưu hoặc xử lý.

Đặt compute gần client có thể giảm client-to-compute latency, nhưng không tự động giảm compute-to-data latency. Ngoài ra, log và telemetry có thể được chuyển đến Region khác dù dữ liệu nghiệp vụ được lưu tại địa phương.

### Data locality và yêu cầu pháp lý

Yêu cầu data residency có thể áp dụng cho dữ liệu lưu trữ, bản sao, backup, log, metadata, dữ liệu truyền qua biên giới hoặc nơi nhân sự có thể truy cập. Một edge request được xử lý trong nước không đủ để chứng minh toàn bộ dữ liệu vẫn ở trong nước.

Khi có yêu cầu về vị trí dữ liệu:

- Xác định loại dữ liệu được xem là dữ liệu cá nhân, nhạy cảm hoặc dữ liệu cần lưu tại một lãnh thổ.
- Kiểm tra vị trí lưu trữ chính, replica, backup, cache và log.
- Xác định request body, header, cookie và token có bị chuyển đến PoP hoặc dịch vụ bên ngoài hay không.
- Kiểm tra nơi secret, encryption key và audit log được quản lý.
- Xác định data processor/subprocessor và điều khoản chuyển dữ liệu.
- Thiết kế chính sách xóa, retention, export và incident response phù hợp.

Không suy ra vị trí dữ liệu chỉ từ tên Region hoặc vị trí PoP. Hãy xác minh cấu hình dịch vụ, hợp đồng và tài liệu compliance hiện hành của nhà cung cấp.

## 5. Replication, consistency và dữ liệu phân tán

Để giảm latency, hệ thống có thể sao chép dữ liệu đến nhiều Region hoặc edge location. Nhưng bản sao phân tán tạo ra câu hỏi về consistency và cập nhật.

### Strong consistency

Strong consistency yêu cầu client đọc được giá trị mới nhất theo thứ tự giao dịch được định nghĩa. Cách này phù hợp với dữ liệu mà quyết định sai có thể gây thiệt hại, ví dụ số dư, tồn kho cuối cùng hoặc trạng thái thanh toán. Đổi lại, thao tác có thể cần liên hệ với một authority/leader ở xa và tăng latency.

### Eventual consistency

Eventual consistency cho phép các replica tạm thời khác nhau nhưng hội tụ khi không có cập nhật mới. Nó phù hợp với nội dung công khai, cấu hình ít thay đổi, catalog hoặc dữ liệu hiển thị có thể chấp nhận stale trong một khoảng thời gian. Ứng dụng cần biết TTL, replication lag và cách xử lý khi hai nơi cùng ghi.

### Read local, write home

Một mô hình phổ biến là đọc từ replica gần client nhưng gửi write đến một Region sở hữu dữ liệu. Mô hình này giảm latency cho read-heavy workload, đồng thời giữ quyền ghi ở một nơi để giảm conflict.

Tuy nhiên, read local có thể trả dữ liệu cũ ngay sau khi write. Nếu nghiệp vụ cần read-your-writes, client có thể được định tuyến về home Region sau write, dùng version token hoặc đọc từ primary trong một khoảng thời gian.

### Conflict và idempotency

Nếu nhiều PoP hoặc Region có thể ghi cùng một record, phải định nghĩa cách giải quyết conflict: version/sequence, compare-and-set, last-write-wins hay business merge. Last-write-wins dựa trên timestamp có thể sai khi đồng hồ lệch và có thể ghi đè thay đổi quan trọng.

Các event ghi dữ liệu cần có idempotency key và event ID. Khi replication hoặc retry gửi lại event, consumer phải nhận ra thao tác đã hoàn tất. Nếu side effect được thực hiện ở nhiều Region, cần xác định nơi sở hữu khóa idempotency và cách đồng bộ deduplication.

## 6. Độ trễ tại edge gồm những phần nào?

Latency end-to-end không chỉ là thời gian chạy edge function. Một request có thể đi qua nhiều chặng:

- DNS lookup và kết nối TCP/QUIC.
- TLS handshake hoặc tái sử dụng kết nối.
- Client đến edge PoP.
- Queueing và scheduling tại edge runtime.
- Cold start hoặc khởi tạo isolate.
- CPU time của edge function.
- Edge đến origin hoặc regional API.
- Regional API đến database/cache/service phụ trợ.
- Response quay về edge và client.

Có thể mô hình hóa đơn giản:

~~~text
Total latency
  = client-to-edge network
  + edge queue/startup/compute
  + edge-to-origin network
  + origin compute
  + origin-to-data network and query
  + response transfer
~~~

Các thành phần có thể chồng lấn khi dùng streaming hoặc parallel request, vì vậy đây là mô hình phân tích chứ không phải phép cộng chính xác trong mọi trường hợp.

### Ví dụ hai đường đi

Giả sử client ở gần một PoP:

- Edge xác thực token và trả cache hit: request kết thúc gần edge, không cần gọi Region.
- Edge xác thực token rồi gọi Java API và database ở Region xa: request vẫn chịu latency của đường edge-to-region và query database.

Với request động, edge chỉ có lợi nếu nó loại bỏ được một round trip, giảm dữ liệu truyền hoặc định tuyến đến backend phù hợp. Nếu edge thêm một bước network mà không giảm công việc phía sau, latency có thể tăng.

### Nearest không luôn là fastest

PoP gần nhất theo địa lý chưa chắc có đường mạng nhanh nhất. Routing, peering, congestion, ISP và health của origin ảnh hưởng thời gian thực. Nên đo theo vùng người dùng và ISP thực tế, không chỉ dựa vào bản đồ PoP của nhà cung cấp.

## 7. Cache là cách giảm round trip hiệu quả tại edge

Cache có thể tránh gọi origin cho nội dung được dùng lặp lại. Nó đặc biệt hữu ích với nội dung công khai, ít thay đổi hoặc có thể chấp nhận stale trong một khoảng thời gian.

Một cache key thường cần cân nhắc:

- Scheme/host/path và query parameter có ý nghĩa.
- Ngôn ngữ, encoding hoặc device class nếu response khác nhau.
- Phiên bản nội dung hoặc tenant khi cần.
- Header nào thực sự làm representation thay đổi.

Không đưa mọi header vào cache key vì cardinality lớn làm giảm hit ratio. Ngược lại, bỏ qua header ảnh hưởng nội dung có thể khiến client nhận sai response.

### Cache-Control và dữ liệu cá nhân

Ví dụ nội dung công khai có thể cache trong thời gian ngắn:

~~~http
Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=30
ETag: "catalog-v18"
~~~

Ví dụ response cá nhân hóa:

~~~http
Cache-Control: private, no-store
~~~

Không cache response chứa dữ liệu theo user/session ở shared cache trừ khi cache key và policy được thiết kế, kiểm thử rõ ràng. Cẩn thận với Authorization, Cookie, Set-Cookie và header do client tự đặt.

### Cache invalidation

Khi dữ liệu thay đổi, cache cần được cập nhật hoặc vô hiệu hóa. Các chiến lược thường gặp:

- TTL ngắn để giới hạn thời gian stale.
- Versioned URL hoặc content hash để nội dung mới có cache key mới.
- Purge/invalidation theo tag hoặc key nếu nền tảng hỗ trợ.
- Stale-while-revalidate để trả dữ liệu cũ trong khi làm mới.
- Event-driven invalidation từ hệ thống sở hữu dữ liệu.

Cache stampede xảy ra khi nhiều request cùng miss một key và đồng loạt gọi origin. Có thể dùng request coalescing, stale response, TTL jitter hoặc pre-warm cache nếu runtime hỗ trợ.

## 8. Định tuyến request đến origin và Region

Edge function có thể chọn backend dựa trên host, path, tenant, geo hint, health hoặc loại request. Cần phân biệt định tuyến theo vị trí người dùng với định tuyến đến nơi dữ liệu đang được sở hữu.

Ví dụ:

- Nội dung công khai: trả từ cache edge.
- API đọc catalog: chọn Region có replica gần client.
- API cập nhật đơn hàng: gửi đến home Region của tenant/order.
- Request quản trị: định tuyến đến backend được kiểm soát chặt.
- Origin lỗi: chuyển sang fallback chỉ khi dữ liệu và hành động đó cho phép.

Không nên định tuyến giao dịch ghi đến Region gần nhất một cách tùy ý nếu mỗi Region không có cơ chế ownership và conflict resolution. Một order thuộc home Region A cần tiếp tục được xử lý tại A hoặc qua một giao thức chuyển ownership có kiểm soát.

### Health check và failover

Failover không chỉ là chọn origin còn sống. Cần xác định:

- Origin có dữ liệu đủ mới không?
- Read-only hay write cũng được phép khi failover?
- Có nguy cơ hai Region cùng nhận write (split brain) không?
- DNS/edge route cần bao lâu để hội tụ?
- Request đang chạy có thể retry an toàn không?
- Có cần trả lỗi rõ ràng thay vì chuyển sang nơi dữ liệu không nhất quán?

Với thao tác không idempotent, edge không nên tự retry POST sang origin khác khi không biết origin đầu đã commit hay chưa. Dùng idempotency key và reconciliation để xác định kết quả.

## 9. Edge và bảo mật dữ liệu

Edge mở rộng bề mặt xử lý ra nhiều PoP. Điều này có thể cải thiện khả năng chống tấn công và giảm tải origin, nhưng cũng cần quản lý policy, secret và log nhất quán.

### Xác thực và authorization

Edge có thể kiểm tra JWT signature, issuer, audience, expiry và claim đơn giản. Cần bảo đảm:

- Chỉ chấp nhận thuật toán và key đã cấu hình; không tin header JWT để tự chọn thuật toán yếu.
- Key rotation được phân phối và cache có thời hạn phù hợp.
- Không log access token, refresh token hoặc cookie.
- Kiểm tra authorization theo resource ở backend sở hữu dữ liệu nếu edge không có nguồn quyền đủ mới.
- Không coi geo-IP hoặc header forwarded là danh tính người dùng.

Nếu edge dùng token introspection hoặc gọi identity provider cho mọi request, network call có thể triệt tiêu lợi ích latency. Có thể cache key/JWKS an toàn với TTL, nhưng phải thiết kế thời gian thu hồi và key rotation.

### Secrets và outbound access

Secret được phân phối đến nhiều edge location có thể tăng phạm vi ảnh hưởng khi bị lộ. Ưu tiên credential ngắn hạn, scope hẹp và cơ chế secret management của nền tảng. Không đưa secret dài hạn vào client-side code hoặc response.

Giới hạn outbound request theo allowlist host và protocol để tránh SSRF. Validate URL trước khi fetch; chặn metadata endpoint, private IP hoặc redirect sang host ngoài allowlist theo chính sách. Kiểm tra TLS và không tắt certificate validation để xử lý lỗi kết nối.

### Log và privacy

Request ở edge có thể chứa IP, cookie, query, user agent, token hoặc dữ liệu cá nhân. Chỉ log trường cần cho vận hành; redact hoặc hash identifier theo chính sách. Xác định log được gửi đến Region nào, retention bao lâu và ai có quyền truy cập.

## 10. State và lưu trữ trong edge runtime

Memory của một edge instance thường là tạm thời. Nó có thể được tái sử dụng trong một số request nhưng không được bảo đảm tồn tại qua deploy, scale, isolate eviction hoặc request tiếp theo. Static field trong JavaScript/Wasm hay global object không phải database.

Phân biệt các loại state:

| Loại state | Nơi lưu phù hợp | Ví dụ |
|---|---|---|
| Dữ liệu chỉ dùng trong một request | Local variable/request context | Parsed header, normalized path |
| Cache ngắn hạn không quan trọng nếu mất | Edge cache hoặc in-memory cache có TTL | Public configuration, metadata |
| Dữ liệu chia sẻ giữa PoP | Distributed KV/cache được nền tảng cung cấp | Feature flag, routing metadata |
| State có transaction/consistency mạnh | Regional database hoặc service sở hữu aggregate | Payment, inventory, order |
| Công việc cần tồn tại qua retry | Queue, durable workflow hoặc database job | Email, report, file processing |
| Dữ liệu lớn | Object storage | Upload, media, archive |

Distributed KV ở edge thường có consistency, replication lag, quota và giới hạn kích thước riêng. Không mặc định thao tác write ở một PoP lập tức nhìn thấy ở tất cả PoP. Đọc tài liệu consistency của sản phẩm trước khi dùng nó để lưu quyền, số dư hoặc trạng thái cần chính xác.

## 11. Mô hình upload và xử lý file lớn

Không nên truyền file lớn qua edge function nếu nền tảng có giới hạn request body, memory hoặc duration. Một pattern thường hiệu quả:

1. Client gọi regional API để xin upload authorization hoặc URL có thời hạn.
2. Client upload trực tiếp đến object storage trong Region phù hợp.
3. Storage phát event hoặc gửi message.
4. Java function trong Region xử lý file theo stream hoặc batch.
5. Edge phục vụ trạng thái, metadata hoặc kết quả đã cache.

Edge có thể kiểm tra token và cấp upload URL, nhưng cần giới hạn scope, object key, content type, size và expiry. Backend phải xác minh lại metadata và nội dung thực tế; không tin content type do client khai báo.

Nếu dữ liệu phải ở một quốc gia/Region cụ thể, upload URL cần trỏ đến storage được phê duyệt. Định tuyến edge gần client nhưng upload đến storage khác Region có thể làm tăng chi phí egress và vi phạm yêu cầu data residency.

## 12. Ví dụ: edge kiểm tra request, Java function xử lý nghiệp vụ

Giả sử một ứng dụng thương mại điện tử phục vụ người dùng ở nhiều khu vực. Edge có nhiệm vụ kiểm tra token và route request; Java function trong Region xử lý đơn hàng.

### Logic edge (pseudocode JavaScript)

~~~javascript
async function handleRequest(request) {
  const url = new URL(request.url);

  if (url.pathname.startsWith("/assets/")) {
    return fetch(request); // CDN/cache policy xử lý nội dung tĩnh.
  }

  const token = readBearerToken(request.headers);
  const claims = await verifyJwtLocally(token);

  if (!claims || !claims.sub) {
    return new Response("Unauthorized", { status: 401 });
  }

  const headers = new Headers(request.headers);
  headers.set("x-authenticated-subject", claims.sub);
  headers.set("x-request-region", selectRegion(request));

  // Origin phải chỉ nhận traffic từ edge tin cậy hoặc xác minh lại token.
  return fetch(buildRegionalOrigin(url), {
    method: request.method,
    headers,
    body: request.body
  });
}
~~~

Đây là pseudocode minh họa luồng, không phải code triển khai cho một edge provider cụ thể. API fetch, streaming request body, header forwarding, runtime limits và cách xác minh JWT khác nhau giữa các nền tảng. Header x-authenticated-subject không tự trở thành bằng chứng tin cậy nếu client có thể gọi thẳng origin hoặc tự gửi header đó; origin phải chặn đường gọi trực tiếp hoặc xác minh chữ ký/credential từ edge.

### Regional Java function

~~~java
public final class OrderService {
    public OrderResponse createOrder(
            CreateOrderCommand command,
            AuthenticatedPrincipal principal,
            String idempotencyKey) {

        validateRequest(command);
        authorizeCustomer(principal, command.customerId());

        // Transaction và idempotency được bảo vệ ở service sở hữu dữ liệu.
        return orderRepository.createOnce(
                command, principal.subject(), idempotencyKey);
    }
}
~~~

Java service giữ business rule, authorization theo resource và transaction. Edge chỉ thực hiện những kiểm tra có thể làm an toàn từ request/token và chuyển request đến Region phù hợp.

### Luồng tổng thể

~~~mermaid
sequenceDiagram
    participant U as User
    participant E as Edge Function
    participant C as Edge Cache
    participant J as Regional Java API
    participant D as Database
    participant Q as Queue

    U->>E: HTTPS request
    E->>E: Validate token and normalize request
    alt Public cache hit
        E->>C: Read cached object
        C-->>E: Cached response
        E-->>U: Response
    else Dynamic order request
        E->>J: Forward to home Region
        J->>J: Resource authorization
        J->>D: Transaction + idempotency
        D-->>J: Commit result
        J->>Q: Publish background event
        J-->>E: Order response
        E-->>U: Response
    end
~~~

## 13. Đo latency theo khu vực người dùng

Một bài benchmark chỉ chạy từ một máy trong một Region không phản ánh trải nghiệm toàn cầu. Cần đo từ các vị trí client đại diện, theo ISP và loại kết nối nếu có thể.

Các metric quan trọng:

- DNS, connect và TLS handshake time.
- Time to first byte (TTFB).
- End-to-end latency p50, p95 và p99.
- Edge compute duration và CPU time.
- Cache hit ratio, miss ratio và origin fetch rate.
- Edge-to-origin latency theo Region.
- Database query latency và dependency latency.
- Cold start/init duration nếu runtime cung cấp.
- Error, timeout, retry và throttling theo PoP/Region.

Nên gắn request ID và trace context xuyên suốt edge, regional API và database. Tránh ghi dữ liệu nhạy cảm trong trace. Khi so sánh edge với regional-only, dùng cùng request, cache state và workload để tránh kết luận sai do cache warm hoặc tải khác nhau.

### Phân tích theo từng vùng

Một dashboard toàn cầu có thể che giấu việc một ISP hoặc quốc gia đang có latency cao. Phân đoạn theo PoP/colo, client region, origin region, route và cache status. Nếu edge compute nhanh nhưng TTFB vẫn cao, kiểm tra network hoặc origin; nếu cache hit nhanh nhưng miss rất chậm, xem edge-to-origin và database path.

## 14. Chi phí và trade-off khi đưa xử lý ra edge

Edge có thể giảm egress về origin và giảm tải backend, nhưng có thể phát sinh chi phí theo request, CPU time, subrequest, storage replication, cache, log và data transfer. Một request được xử lý tại edge rồi gọi regional API vẫn có chi phí edge và origin.

Các yếu tố cần tính:

- Số request đi qua edge mỗi tháng.
- CPU time và memory/duration của edge function.
- Tỷ lệ cache hit và số origin fetch.
- Số subrequest hoặc external API call.
- Chi phí data transfer giữa PoP và Region.
- Chi phí replication và distributed KV.
- Log/trace volume và retention.
- Chi phí vận hành nhiều Region, secrets và policy.

Nếu edge chỉ thêm một network hop mà không tạo cache hit, giảm payload hoặc cải thiện route, nó có thể làm tăng cả latency lẫn chi phí. Đánh giá bằng end-to-end metrics và tổng chi phí hệ thống, không chỉ giá của edge invocation.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Cho rằng edge compute đồng nghĩa data ở gần client | Request vẫn chậm khi gọi database ở Region xa | Đo edge-to-origin và data locality riêng |
| Giả định JAR Java chạy được trong mọi edge runtime | Build hoặc runtime lỗi do thiếu JVM/API/native ABI | Xác minh ngôn ngữ, ABI và API được hỗ trợ |
| Đưa transaction vào edge KV eventual consistency | Đọc/ghi lệch hoặc conflict nghiệp vụ | Để service/database sở hữu transaction |
| Cache response cá nhân hóa ở shared cache | Rò dữ liệu giữa user/tenant | Cache-Control và cache key an toàn; private/no-store khi cần |
| Tin header do edge thêm nhưng origin vẫn public | Client giả mạo identity header và bypass edge | Chặn origin direct access hoặc ký/xác minh context |
| Retry POST sang origin khác sau timeout | Tạo side effect hai lần | Idempotency key và reconciliation |
| Đưa file lớn qua edge body | Vượt memory/body/duration limit | Upload trực tiếp object storage |
| Ghi state vào global/static memory | Mất state khi isolate bị thu hồi hoặc scale | Dùng store bền vững phù hợp |
| Chỉ đo từ một thành phố | Bỏ sót latency theo ISP/PoP | Synthetic và real-user monitoring đa vùng |
| Replica dữ liệu không có version/consistency rule | Người dùng nhận dữ liệu stale hoặc ghi đè | Version, TTL, ownership và conflict resolution |
| Log toàn bộ request | Lộ token, cookie, PII | Redaction, sampling và retention |
| Đưa mọi business rule ra edge | Policy phân tán khó đồng bộ và audit | Giữ nguồn sự thật tại regional service |

## 16. Quy trình quyết định có nên chạy một tác vụ tại edge

Có thể dùng quy trình sau:

1. **Xác định latency budget:** người dùng cần phản hồi trong bao lâu và phần thời gian nào đang bị tiêu tốn?
2. **Xác định dữ liệu cần thiết:** tác vụ có thể quyết định từ request, token hoặc cache không; có cần truy vấn database không?
3. **Kiểm tra runtime:** ngôn ngữ, CPU, memory, duration, API, network, package và request size có đáp ứng không?
4. **Kiểm tra vị trí dữ liệu:** dữ liệu nằm ở đâu, replica có consistency gì, có yêu cầu residency nào không?
5. **Tách phần xử lý:** việc stateless/nhẹ có thể chạy ở edge; transaction, stateful workflow và Java business logic chạy ở Region.
6. **Thiết kế failure mode:** edge/origin lỗi thì trả response, failover, retry hay queue; side effect có idempotent không?
7. **Kiểm tra bảo mật:** cache, token, forwarded header, secret, log và origin access có an toàn không?
8. **Benchmark đa vùng:** so sánh regional-only với edge-enabled trên p50/p95/p99, cache hit, error và cost.
9. **Triển khai có kiểm soát:** canary theo route/region, theo dõi và có rollback.
10. **Đánh giá lại:** khi runtime quota, data placement hoặc traffic thay đổi, tính lại latency và chi phí.

Một tác vụ phù hợp với edge khi lợi ích giảm round trip, cache hoặc định tuyến lớn hơn chi phí phân tán dữ liệu, giới hạn runtime và vận hành nhiều điểm thực thi.

## 17. Checklist production

- **Runtime:** đã xác minh ngôn ngữ, API, CPU, memory, duration, payload và artifact limit của đúng edge product chưa?
- **Java compatibility:** có yêu cầu JVM, reflection, JNI, filesystem, thread hoặc native library nào không; runtime có thực sự hỗ trợ không?
- **Data locality:** compute, database, cache, object storage, backup và log đang ở đâu?
- **Consistency:** dữ liệu được đọc từ replica có thể stale bao lâu; write có home Region và conflict rule không?
- **Latency:** đã đo client-to-edge, edge compute, edge-to-origin và database riêng chưa?
- **Cache:** cache key, TTL, invalidation và response cá nhân hóa có được kiểm thử không?
- **Security:** origin có thể bị gọi trực tiếp không; forwarded identity có được xác minh; secret và log đã được bảo vệ chưa?
- **State:** local memory chỉ dùng làm cache tạm; dữ liệu bền vững có nơi lưu phù hợp không?
- **Retry:** request không idempotent có key và reconciliation không; edge có retry nhầm side effect không?
- **Upload:** file lớn có đi thẳng đến object storage thay vì qua edge function không?
- **Observability:** trace ID xuyên edge/Region; dashboard phân đoạn theo PoP, client region và origin region chưa?
- **Cost:** đã tính invocation, CPU, subrequest, replication, egress, storage và telemetry chưa?
- **Recovery:** có canary, rollback, origin failover và runbook khi một PoP/Region lỗi không?

## 18. Kết luận

Edge computing đưa logic đến gần người dùng, nhưng lợi ích phụ thuộc vào runtime, đường đi đến dữ liệu và khả năng cache hoặc tránh round trip. Edge runtime thường có giới hạn chặt về CPU, memory, thời gian, package, API hệ điều hành và network; không thể mặc định ứng dụng Java/JVM đầy đủ chạy nguyên trạng trong mọi edge platform.

Hãy tách compute location khỏi data location và đo latency theo từng chặng. Edge phù hợp với xác thực nhẹ, rewrite, routing, cache và xử lý stateless; Java function trong Region phù hợp với nghiệp vụ, transaction, database, file lớn và workflow bền vững. Với dữ liệu phân tán, xác định ownership, consistency, replication lag, residency và idempotency trước khi đưa write ra nhiều vị trí.

Một kiến trúc edge/serverless tốt không đặt mọi thứ ở PoP gần nhất. Nó đặt từng phần xử lý ở nơi có runtime phù hợp, dữ liệu có thể truy cập an toàn và tổng latency/chi phí đáp ứng mục tiêu của người dùng.
