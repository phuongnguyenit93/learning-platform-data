# Phòng vệ DDoS, WAF và giới hạn tác động tại điểm vào

## 1. Điểm vào là ranh giới quan trọng của kiến trúc cloud

Một ứng dụng có thể triển khai nhiều bản sao trên nhiều availability zone nhưng vẫn mất khả năng phục vụ nếu mọi yêu cầu từ Internet đều đi qua một điểm vào nghẽn hoặc nếu lưu lượng bất thường đẩy cơ sở dữ liệu đến giới hạn. Vì vậy, thiết kế **điểm vào hệ thống** (system entry point) phải trả lời đồng thời ba câu hỏi:

1. **Ai được đi vào và bằng con đường nào?** Xác định hostname, giao thức, cổng, loại client và đường tới ứng dụng.
2. **Mối đe dọa nào cần được lọc trước khi tới workload?** Phân biệt DDoS hạ tầng, lưu lượng ứng dụng độc hại, bot và hành vi lạm dụng API.
3. **Nếu điểm vào bị quá tải hoặc một lớp kiểm soát lỗi, tác động được giới hạn đến đâu?** Chỉ tiêu quan trọng không chỉ là chặn lưu lượng độc hại, mà còn là giữ được khả năng phục vụ người dùng hợp lệ.

Trong module **CLOUD_ARCHITECTURE**, bảo vệ điểm vào phải được thiết kế từ yêu cầu nghiệp vụ cùng các quyết định về **mạng, compute, dữ liệu và mô hình triển khai**. Trọng tâm là đánh đổi giữa **độ tin cậy, bảo mật, hiệu năng, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

**Tình huống xuyên suốt:** nền tảng đặt chỗ có website, ứng dụng di động, API tìm kiếm phòng, API xác nhận đặt chỗ, đăng nhập và webhook thanh toán. Tìm kiếm có thể được cache theo chính sách phù hợp; tạo đặt chỗ cần bảo vệ tính nhất quán giao dịch; webhook được gửi từ một đối tác bên ngoài. Các con số trong ví dụ dưới đây chỉ là **giả định phục vụ học tập**, phải thay bằng dữ liệu tải và yêu cầu được xác nhận.

## 2. Phân biệt DDoS, WAF và những kiểm soát liên quan

**DDoS (Distributed Denial of Service)** là hành vi làm suy giảm hoặc ngừng khả năng phục vụ bằng lượng truy cập hay xử lý bất thường từ nhiều nguồn. Tùy kiểu tấn công, điểm nghẽn có thể là băng thông, số kết nối, khả năng xử lý của thiết bị mạng, TLS, ứng dụng hoặc tài nguyên dữ liệu.

**WAF (Web Application Firewall)** kiểm tra một số thuộc tính của lưu lượng **HTTP/HTTPS**, thường tại lớp ứng dụng (L7), rồi cho phép, ghi nhận, yêu cầu thử thách hoặc chặn theo các quy tắc. WAF có thể phát hiện một số mẫu khai thác và hành vi lạm dụng nhưng không thay thế việc sửa lỗ hổng ứng dụng hoặc phòng vệ trước mọi kiểu DDoS hạ tầng.

| Nhóm rủi ro | Đường tác động phổ biến | Lớp phòng vệ chính cần xem xét | Điều cần tránh hiểu sai |
| --- | --- | --- | --- |
| DDoS lưu lượng lớn (volumetric) | Làm nghẽn đường mạng và năng lực nhận lưu lượng phía trước ứng dụng | Nhà cung cấp mạng/đám mây có chống DDoS upstream, hạ tầng phân tán/Anycast, dịch vụ lọc lưu lượng | WAF đặt sát origin không thể khôi phục một đường truyền đã bị nghẽn trước đó |
| DDoS giao thức hoặc kết nối (L3/L4) | Làm cạn trạng thái/kết nối hoặc khả năng xử lý của tầng mạng/transport | Bảo vệ DDoS L3/L4, load balancer, chính sách kết nối và năng lực mạng | Lọc HTTP ở L7 không xử lý hết mọi lưu lượng transport |
| DDoS ứng dụng (L7) | Nhiều HTTP request đắt đỏ làm cạn thread, CPU, DB, hàng đợi | WAF, bot management, rate limiting, giới hạn đồng thời, cache, backpressure | Chỉ đo request/giây có thể bỏ qua yêu cầu ít nhưng rất tốn tài nguyên |
| Khai thác HTTP/API | Payload bất thường, truy cập không hợp lệ, lỗi phân quyền | Quy tắc WAF phù hợp, xác thực, phân quyền, validation, vá lỗi và kiểm thử ứng dụng | WAF không thay cơ chế phân quyền theo đối tượng/dữ liệu |
| Credential stuffing và bot lạm dụng | Đăng nhập tự động, scraping, gọi API quá mức | Rate limit theo danh tính/rủi ro, bảo vệ đăng nhập, bot detection, MFA khi phù hợp | Chỉ chặn theo IP có thể ảnh hưởng người dùng cùng NAT và dễ bị lách bằng nhiều IP |
| Tăng tải hợp lệ (flash crowd) | Khuyến mãi hoặc sự kiện khiến tải tăng đột biến | CDN/cache, autoscaling, queue, capacity planning và load shedding | Không nên coi mọi đột biến là tấn công rồi chặn khách thật |

Một kiến trúc phòng vệ hiệu quả thường dùng **nhiều lớp phối hợp**. Lớp mạng xử lý áp lực mạng, lớp edge/WAF kiểm soát request, gateway xác thực và giới hạn sử dụng API, còn ứng dụng bảo vệ tài nguyên nội bộ. Không có một dịch vụ độc lập nào tự bảo đảm hệ thống đạt SLO trong mọi cuộc tấn công.

### 2.1. Định nghĩa rõ "thành công" của phòng vệ

Mục tiêu không phải "chặn được càng nhiều request càng tốt". Một cấu hình chặn rất mạnh có thể từ chối cả khách hàng hợp lệ. Cần xác định:

- **Tỷ lệ thành công của hành trình hợp lệ:** ví dụ tìm kiếm phòng, đăng nhập và hoàn tất đặt chỗ.
- **Độ trễ end-to-end:** p95/p99 của từng hành trình dưới tải bình thường và các kịch bản bất thường có kiểm soát.
- **Tỷ lệ chặn sai (false positive):** yêu cầu hợp lệ bị từ chối, thử thách hoặc trì hoãn quá mức.
- **Thời gian phát hiện, phân loại và giảm thiểu:** từ khi thấy bất thường tới khi khôi phục chất lượng phục vụ.
- **Giới hạn chi phí và tác động:** request độc hại không được biến thành lượng lớn tác vụ DB/compute/billing không kiểm soát.

Tất cả chỉ tiêu cần có cách đo, phạm vi, dữ liệu kiểm thử và người chịu trách nhiệm. Không nên diễn đạt yêu cầu kiểu "chống được mọi DDoS" vì không thể kiểm chứng theo một ngưỡng vô hạn.

## 3. Xây dựng mô hình đe dọa và yêu cầu chất lượng

Trước khi chọn dịch vụ WAF hoặc chống DDoS, hãy xác định **tài sản cần bảo vệ**, hành trình quan trọng và các đường truy cập có thể bỏ qua điểm vào.

| Tài sản/hành trình | Rủi ro tại điểm vào | Mục tiêu kiến trúc cần xác nhận |
| --- | --- | --- |
| Trang danh mục và tìm kiếm | Request L7 tăng nhanh, scraping, truy vấn nặng | Truy cập hợp lệ vẫn có tỷ lệ thành công và độ trễ trong SLO |
| Đăng nhập | Thử mật khẩu tự động, tạo phiên quá mức | Không để một nhóm nguồn lạm dụng làm hết tài nguyên xác thực; không khóa oan hàng loạt |
| Tạo đặt chỗ | Gửi lặp, tranh chấp cùng phòng, truy vấn ghi đắt | Bảo đảm idempotency và nhất quán nghiệp vụ ngay cả khi có retry |
| Webhook thanh toán | Giả mạo nguồn gửi, lặp sự kiện, payload không hợp lệ | Xác minh chữ ký/nguồn theo hợp đồng, chống replay và xử lý lặp an toàn |
| Quản trị | Dò tìm endpoint hoặc khai thác quyền nhạy cảm | Hạn chế điểm vào, xác thực mạnh, quyền tối thiểu và audit |
| Origin, database, message broker | Bị truy cập trực tiếp hoặc vượt qua WAF | Chỉ cho phép kết nối từ đường đã được phê duyệt; không công khai thành phần nội bộ |

### 3.1. Ví dụ yêu cầu có thể kiểm chứng

Các mục tiêu sau **chỉ là giả định thiết kế** cho bài tập:

| ID | Yêu cầu | Cách kiểm chứng |
| --- | --- | --- |
| SEC-EDGE-01 | Backend API chỉ nhận lưu lượng Internet qua điểm vào được phê duyệt | Kiểm tra routing, firewall/security group và thử truy cập trực tiếp từ môi trường kiểm thử được phép |
| SEC-WAF-01 | Các quy tắc WAF ưu tiên được bật sau giai đoạn giám sát và đánh giá false positive | Kiểm tra nhật ký, tập request hợp lệ/không hợp lệ và kết quả triển khai từng giai đoạn |
| PERF-EDGE-01 | p95 API tìm kiếm không quá 800 ms ở mức 200 request/giây trên bộ dữ liệu đã định | Load test có kiểm soát và distributed tracing tới backend |
| REL-EDGE-01 | Có khả năng giữ hành trình tìm kiếm hoạt động khi endpoint thanh toán ngoài hệ thống lỗi | Diễn tập timeout/không thể kết nối tới đối tác và đo kết quả tìm kiếm |
| OPS-EDGE-01 | Cảnh báo lưu lượng bất thường tới người trực trong 5 phút kể từ khi điều kiện phát hiện được đáp ứng | Kiểm thử cảnh báo, đo độ trễ telemetry và xác nhận escalation |
| COST-EDGE-01 | Có dự báo chi phí bảo vệ, request xử lý, log và dữ liệu truyền trong kịch bản đỉnh | So sánh dự toán với hóa đơn từ bài thử và giả định lưu lượng |

Cần phân biệt **SLO của điểm vào** và **SLO nghiệp vụ**. Load balancer trả HTTP 200 cho trang lỗi không chứng minh khách đặt được phòng; WAF chặn một request không chứng minh request đó độc hại. Phải kiểm tra toàn hành trình với danh tính và dữ liệu đại diện.

## 4. Kiến trúc tham khảo: phòng vệ nhiều lớp

~~~mermaid
flowchart TB
    U["Client hợp lệ và lưu lượng Internet"]
    DNS["DNS / điểm phân phối toàn cầu"]
    DDOS["Chống DDoS upstream L3/L4"]
    EDGE["CDN / Edge với cơ chế chống bot"]
    WAF["WAF HTTP(S)"]
    GW["Load balancer / API Gateway"]
    APP["Web và API ở mạng private"]
    Q["Queue / bộ đệm theo nghiệp vụ"]
    DB[("Database và dịch vụ dữ liệu private")]
    OBS["Metric, audit log, trace và cảnh báo"]
    U --> DNS --> DDOS --> EDGE --> WAF --> GW --> APP
    APP --> Q
    APP --> DB
    GW -.-> OBS
    WAF -.-> OBS
    APP -.-> OBS
~~~

Sơ đồ thể hiện **các năng lực logic**, không bắt buộc phải mua từng sản phẩm riêng. Một nhà cung cấp có thể tích hợp chống DDoS, CDN, WAF và cân bằng tải trong ít lớp vật lý hơn. Thứ tự vật lý còn tùy sản phẩm: có nơi WAF nằm tại CDN, có nơi gắn với API Gateway hoặc load balancer. Đường đi thật phải được kiểm tra từ tài liệu dịch vụ và cấu hình đang chạy.

### 4.1. Những câu hỏi thiết kế ở mỗi lớp

| Lớp | Trách nhiệm chính | Câu hỏi bắt buộc |
| --- | --- | --- |
| DNS/điểm phân phối | Đưa client tới điểm vào thích hợp | DNS dự phòng thế nào, có phụ thuộc một zone/nhà cung cấp không, failover mất bao lâu? |
| Chống DDoS upstream | Hấp thụ/lọc áp lực trước origin | Lưu lượng bảo vệ áp dụng cho địa chỉ/endpoint nào, phạm vi và giới hạn dịch vụ ra sao? |
| CDN/edge | Cache nội dung cho phép, giảm số request tới origin | Dữ liệu nào cache an toàn, cache key gì, có ngăn cache nhầm dữ liệu theo người dùng không? |
| WAF/bot protection | Kiểm tra HTTP, phát hiện mẫu rủi ro | Dùng managed rule nào, false positive được xử lý ra sao, có kiểm soát phiên bản không? |
| API Gateway/LB | Route, TLS, xác thực/chính sách API tùy dịch vụ, health check | Có giới hạn toàn cục và theo route không, có điểm lỗi chung không? |
| Ứng dụng và dữ liệu | Xác thực, phân quyền, tính đúng đắn và giới hạn tiêu thụ tài nguyên | Có rate limit theo danh tính, timeout, idempotency, concurrency limit và queue không? |
| Quan sát/vận hành | Tìm nguyên nhân và phối hợp ứng phó | Log có đủ ngữ cảnh nhưng không lộ bí mật/PII, có playbook và người trực không? |

**Origin bypass** là rủi ro quan trọng: nếu ai đó gọi trực tiếp địa chỉ public của origin, quy tắc WAF trên CDN có thể bị bỏ qua. Vì thế cần hạn chế nguồn được kết nối tới origin theo cách mà nhà cung cấp hỗ trợ, xác thực kết nối edge→origin khi phù hợp và ngăn phát tán endpoint không cần thiết.

### 4.2. TLS, địa chỉ client và ranh giới tin cậy

- Xác định nơi kết thúc TLS ở edge và liệu đoạn edge→origin có tiếp tục được mã hóa, xác thực theo yêu cầu không.
- Không tin tùy tiện vào header X-Forwarded-For hoặc Forwarded do client bên ngoài cung cấp. Chỉ sử dụng chuỗi proxy đáng tin cậy và cấu hình chuẩn hóa địa chỉ client tại điểm vào.
- Nếu rate limit theo IP, phải hiểu khách dùng NAT mạng di động, doanh nghiệp hoặc gateway dùng chung có thể trùng IP nguồn; chặn toàn bộ một IP có thể ảnh hưởng nhiều người hợp lệ.
- Đảm bảo header Host, đường dẫn và phương thức được xử lý nhất quán giữa edge, WAF, proxy và ứng dụng; khác biệt về cách phân tích request có thể gây lỗi định tuyến và bỏ sót chính sách.
- Cấu hình TLS và chứng chỉ cần có owner, theo dõi hạn sử dụng và kế hoạch thay đổi; một chứng chỉ hỏng ở edge đủ làm tất cả request hợp lệ thất bại.

## 5. Phòng vệ DDoS: bắt đầu từ nơi áp lực xuất hiện

### 5.1. Đặt phòng vệ upstream cho nguy cơ nghẽn mạng

Khi lưu lượng vượt khả năng đường truyền/thiết bị nhận request, **chặn tại ứng dụng thường quá muộn**. Để giảm áp lực L3/L4 hoặc volumetric cần đánh giá năng lực lọc của nhà cung cấp cloud/ISP, kiến trúc phân tán và các dịch vụ chống DDoS ở phía trước origin.

Các phương án thường được cân nhắc:

- Hạ tầng edge/Anycast phân phối lưu lượng tới nhiều điểm nhận, giảm tập trung tải ở một endpoint khi phù hợp.
- Dịch vụ chống DDoS của nhà cung cấp mạng/cloud có khả năng phát hiện và giảm thiểu ở lớp mạng và transport.
- Cơ chế lọc/scrubbing upstream cho hệ thống có yêu cầu và mô hình kết nối thích hợp.
- Dự phòng DNS, đường kết nối và vùng triển khai theo mục tiêu độ tin cậy.

**Không nên suy ra rằng việc bật một tính năng chống DDoS bảo đảm chống mọi cuộc tấn công.** Cần biết endpoint nào thực sự được bảo vệ, loại lưu lượng hỗ trợ, giới hạn và nghĩa vụ hỗ trợ, điều kiện kích hoạt giảm thiểu, phương thức quan sát và tác động tới lưu lượng hợp lệ.

### 5.2. Bảo vệ trước tấn công ở lớp ứng dụng

Với HTTP/HTTPS, số request không phải thước đo chi phí duy nhất. Một truy vấn tìm kiếm cần lọc nhiều dữ liệu, request upload lớn hoặc request gây chờ kết nối có thể dùng tài nguyên nhiều hơn request tĩnh.

Kiến trúc nên dùng đồng thời:

1. **Cache hợp lệ** ở CDN/edge cho nội dung có thể cache, dùng cache key rõ và kiểm tra dữ liệu cá nhân.
2. **Rate limit** theo danh tính, route và mức độ tốn tài nguyên, không chỉ một ngưỡng chung toàn website.
3. **Giới hạn kết nối đồng thời, thời gian chờ, kích thước request và tài nguyên đọc/ghi** ở gateway lẫn ứng dụng.
4. **Backpressure/queue** cho tác vụ có thể xử lý bất đồng bộ; bảo vệ connection pool và downstream.
5. **Suy giảm chức năng có kiểm soát** để giữ chức năng ưu tiên khi tải vượt năng lực.

Phải kiểm thử năng lực xử lý của cơ sở dữ liệu và dịch vụ phía sau. Chặn request tại edge có thể giảm tác động đáng kể, nhưng nếu đã có những request hợp lệ vượt khả năng ghi của DB thì cần phương án ứng dụng và dữ liệu, không thể chỉ tăng WAF.

### 5.3. Phân biệt đột biến hợp lệ và lạm dụng

Một chiến dịch giảm giá khiến khách hàng thật truy cập đồng loạt có hình dạng lưu lượng gần giống một đợt DDoS L7 ở một số chỉ số. Do đó, quy tắc bảo vệ phải dựa trên **nhiều tín hiệu** và được đánh giá bằng tác động tới người dùng hợp lệ:

- Sự thay đổi theo từng endpoint, danh tính, quốc gia và khung giờ so với baseline.
- Tỷ lệ yêu cầu được xác thực, chuỗi hành vi hợp lệ, phiên và kết quả nghiệp vụ.
- Độ trễ, bão hòa CPU/DB, queue depth, tỷ lệ error và kết quả từ WAF/bot manager.
- Số request bị thử thách và tỷ lệ người dùng hợp lệ vượt qua thử thách.

Không dùng địa lý hoặc IP đơn lẻ làm bằng chứng chắc chắn request độc hại. Trường hợp cần giới hạn theo vùng địa lý phải xét khách đi du lịch, mạng doanh nghiệp, VPN hợp lệ và yêu cầu kinh doanh.

## 6. Thiết kế WAF có kiểm soát và có khả năng giải thích

WAF phù hợp để áp chính sách ở lớp HTTP(S) cho những endpoint được đặt sau điểm kiểm soát. Quy tắc có thể dựa vào phương thức, đường dẫn, header, mẫu đầu vào, đặc điểm request và tín hiệu phát hiện bot tùy sản phẩm. **WAF không hiểu toàn bộ logic nghiệp vụ** và có thể chặn nhầm, nên cần quy trình đánh giá chính sách.

### 6.1. Managed rules và custom rules

| Nhóm quy tắc | Khi nào dùng | Rủi ro hoặc giới hạn |
| --- | --- | --- |
| Managed rules do nhà cung cấp cập nhật | Giảm công tạo quy tắc cho những lớp tấn công web phổ biến | Có thể tạo false positive; việc cập nhật rule có thể thay đổi hành vi |
| Quy tắc riêng theo ứng dụng | Bảo vệ route nhạy cảm, giới hạn phương thức, chặn pattern không hợp lệ đã xác minh | Dễ lỗi thời khi API thay đổi; cần kiểm thử và owner |
| Rate-based rules của WAF | Giảm request bất thường theo tiêu chí/cửa sổ mà sản phẩm hỗ trợ | Không thay limiter theo quota nghiệp vụ hoặc trạng thái trong ứng dụng |
| Bot management và challenge | Giảm hành vi tự động ở những tuyến hỗ trợ trình duyệt/challenge | Không phù hợp mọi API, mobile client, webhook hay accessibility flow |
| Danh sách cho phép/ngoại lệ | Cho phép luồng hệ thống đặc thù đã xác thực | Ngoại lệ quá rộng có thể vô hiệu hóa các lớp phòng vệ |

Không đặt ngoại lệ toàn hệ thống chỉ vì một webhook hoặc một endpoint có payload giống mẫu bị WAF đánh dấu. Hãy **thu hẹp theo hostname, route, phương thức, nguồn đáng tin và thời hạn**, rồi kiểm chứng tính hợp lệ bằng chữ ký, token hoặc cơ chế thích hợp của ứng dụng.

### 6.2. Quy trình đưa WAF rule vào production

~~~mermaid
flowchart LR
    A["Phân tích nguy cơ và endpoint"] --> B["Chọn managed/custom rule"]
    B --> C["Quan sát/Count/Log nếu hỗ trợ"]
    C --> D["Đánh giá request hợp lệ và false positive"]
    D --> E["Thử nghiệm ở phạm vi hẹp"]
    E --> F["Chuyển sang Block/Challenge có kiểm soát"]
    F --> G["Giám sát, rollback và cập nhật"]
    G --> D
~~~

1. Tập hợp **nhóm request hợp lệ đại diện**, gồm web, mobile, API, thanh toán, hỗ trợ khách hàng và các client truy cập đặc biệt.
2. Bắt đầu ở chế độ quan sát/count nếu nền tảng hỗ trợ; lấy metric và ví dụ nhật ký đã được làm sạch dữ liệu nhạy cảm.
3. Phân loại nguyên nhân chặn dự kiến, đánh giá tỷ lệ trùng khớp sai và rủi ro chưa chặn; chọn mức hành động phù hợp.
4. Thử ở một nhóm traffic nhỏ hoặc môi trường đủ giống production; ghi version, người duyệt và điều kiện rollback.
5. Chuyển từng quy tắc sang block/challenge, theo dõi p95, tỷ lệ thành công theo hành trình và khiếu nại người dùng.
6. Tạo ngoại lệ hẹp, có hạn dùng; sau thay đổi ứng dụng hoặc rule managed cần đánh giá lại.

**False positive** có thể gây mất doanh thu hoặc chặn webhook, vì vậy cần theo dõi tác động nghiệp vụ bên cạnh số yêu cầu bị WAF từ chối. Nếu một rule gây lỗi lớn, phải có cơ chế rollback nhanh nhưng vẫn giữ các lớp bảo vệ còn lại.

### 6.3. WAF không thay thế bảo mật ứng dụng

WAF có thể hỗ trợ chống một số dạng injection hoặc request độc hại, nhưng ứng dụng vẫn cần:

- Xác thực và **phân quyền từng tài nguyên** (ngăn người dùng đọc đơn hàng của người khác).
- Kiểm tra đầu vào ở phía server và dùng truy vấn tham số hóa/biện pháp an toàn tương ứng.
- Bảo vệ phiên, bí mật và token; cấu hình CORS/CSRF thích hợp với kiểu client.
- Idempotency và chống replay cho yêu cầu có tác dụng ghi.
- Cập nhật dependency, kiểm thử bảo mật và giám sát bất thường.

Ví dụ, WAF cho phép request xem đơn hàng có cú pháp hợp lệ nhưng **không thể tự biết** khách A có quyền xem đơn của khách B hay không. Quyền này thuộc lớp ứng dụng và dữ liệu.

## 7. Rate limiting: giới hạn theo hành vi và tài nguyên thật

**Rate limiting** là cơ chế kiểm soát tốc độ hoặc số lượng thao tác trong một khoảng thời gian. Nó giúp bảo vệ khỏi lạm dụng và phân chia năng lực phục vụ giữa các client, nhưng cần chọn **đơn vị đếm và khóa giới hạn** đúng với nghiệp vụ.

| Khóa giới hạn | Phù hợp với | Nhược điểm cần xử lý |
| --- | --- | --- |
| IP nguồn sau proxy tin cậy | Điểm vào công khai, request chưa xác thực, tín hiệu phát hiện sơ bộ | Một IP có thể đại diện nhiều khách hợp lệ; bot dùng nhiều IP có thể phân tán lưu lượng |
| Tài khoản/người dùng | API đã xác thực, chính sách sử dụng dịch vụ | Kẻ lạm dụng có thể tạo nhiều tài khoản; tài khoản doanh nghiệp có mức sử dụng khác cá nhân |
| API key / client ID | Đối tác, dịch vụ gọi qua API | Phải bảo vệ khóa và xử lý nhiều client dùng chung khóa |
| Tenant / tổ chức | SaaS nhiều khách hàng, hạn mức theo hợp đồng | Một tenant lớn có thể cần cấp riêng; phải ngăn tenant chiếm tài nguyên chung |
| Route / thao tác | Phân biệt tìm kiếm với tạo đơn, upload, xuất báo cáo | Cần duy trì khi route thay đổi và đo được chi phí thực |
| Phiên hoặc tín hiệu rủi ro | Login, hành vi bot, challenge | Có thể thiếu ổn định khi cookie bị chặn hoặc client không dùng browser |
| Nhiều tầng kết hợp | Bảo vệ cả toàn hệ thống và từng khách | Phải xác định thứ tự, phạm vi và tránh chồng giới hạn khó giải thích |

**Không dùng một ngưỡng toàn hệ thống cho mọi route** nếu chi phí xử lý và mức độ ưu tiên khác nhau. Một request xem ảnh có thể được cache, một request tìm phòng có thể truy vấn chỉ mục, còn một request xác nhận đặt chỗ có thể cần giao dịch và liên hệ dịch vụ thanh toán.

### 7.1. Token bucket, cửa sổ thời gian và burst

Một cơ chế phổ biến là **token bucket**: mỗi nhóm client có một lượng token tối đa (burst capacity) và được nạp token theo tốc độ định trước. Request tiêu thụ token; khi hết token, hệ thống có thể trả mã từ chối phù hợp hoặc đưa vào cơ chế chờ được thiết kế riêng.

Giả sử mỗi tài khoản được phép **10 request/giây với burst tối đa 20 request** ở một API đọc. Đây chỉ là ví dụ, không phải hạn mức khuyên dùng. Nếu bucket có 20 token lúc đầu, một cụm request có thể tiêu thụ tối đa 20 token ngay; về lâu dài tốc độ chấp nhận bị chi phối bởi mức nạp 10 token/giây. Trong thực tế còn có giới hạn đồng thời, thời gian xử lý, mức chia sẻ trạng thái giữa các gateway và cách thuật toán triển khai.

| Thuật toán | Ưu điểm | Điều cần kiểm tra |
| --- | --- | --- |
| Fixed window counter | Đơn giản, dễ đếm theo khoảng thời gian | Có thể có burst ở ranh giới hai cửa sổ |
| Sliding window / rolling counter | Hạn chế đột biến ở ranh giới tốt hơn tùy triển khai | Tốn tài nguyên lưu trạng thái hơn |
| Token bucket | Cho phép burst có kiểm soát và tốc độ bình quân | Phải định nghĩa sức chứa, tốc độ nạp và trạng thái phân tán |
| Leaky bucket / queue | Làm mượt tốc độ xử lý đầu ra | Nếu xếp hàng quá lâu có thể gây timeout và tiêu thụ bộ nhớ |
| Concurrency limit | Giới hạn số thao tác đang xử lý đồng thời | Không thay giới hạn số request theo thời gian hay ngân sách CPU/DB |

### 7.2. Cơ chế phân tán và tính nhất quán của giới hạn

Một hệ thống có nhiều edge node, gateway hoặc vùng triển khai cần quyết định **giới hạn áp dụng toàn cục hay cục bộ**. Nếu mỗi node giữ một bucket riêng, số request được chấp nhận cộng lại có thể vượt hạn mức dự kiến. Nếu mọi node hỏi một kho trạng thái tập trung cho mỗi request, dịch vụ limiter có thể trở thành điểm nghẽn hoặc điểm lỗi chung.

Các lựa chọn có thể gồm giới hạn cục bộ để bảo vệ từng node, giới hạn phân tán cho tenant quan trọng, hoặc **phân bổ quota thành từng phần**. Phải ghi rõ sai số chấp nhận, thời gian đồng bộ và hành vi khi dịch vụ giới hạn không khả dụng.

**Fail-open hay fail-closed?** Không có câu trả lời chung. Với API đọc ít nhạy cảm, cho phép một lượng request nhất định khi limiter lỗi có thể phù hợp để giữ độ sẵn sàng; với thao tác nhạy cảm cần kiểm soát chặt, từ chối tạm thời có thể phù hợp hơn. Quyết định phải dựa trên rủi ro, lượng tài nguyên dự phòng và chính sách đã phê duyệt.

### 7.3. Phản hồi khi giới hạn bị vượt

Đối với HTTP API, mã **429 Too Many Requests** thường phù hợp khi client vượt giới hạn tốc độ. Header **Retry-After** có thể giúp client biết khoảng chờ nếu server cung cấp và client hỗ trợ. Cần chuẩn hóa lỗi và mô tả hạn mức trong hợp đồng API để client sử dụng backoff/jitter, tránh thử lại đồng loạt.

Khi toàn hệ thống quá tải do thiếu năng lực, **503 Service Unavailable** có thể mô tả tình trạng tạm thời phù hợp hơn 429 trong nhiều trường hợp. Phân biệt nguyên nhân giúp client và bộ phận vận hành hành động đúng. Tuy nhiên, cơ chế retry phải **bảo toàn idempotency** và giới hạn số lần thử; không phát lại thao tác thanh toán chỉ vì nhận timeout mà chưa rõ kết quả.

### 7.4. Rate limit theo mức tiêu thụ thay vì chỉ request

Một request xuất báo cáo có thể tiêu tốn 100 lần CPU hoặc DB I/O so với đọc bản ghi nhỏ. Có thể cần kết hợp:

- Giới hạn **số thao tác trên giây** theo identity và route.
- Giới hạn **số job xuất báo cáo đang chạy** cùng lúc cho mỗi tenant.
- Giới hạn **kích thước request/upload** và dung lượng dữ liệu trả về.
- Giới hạn **số truy vấn DB/connection** hoặc thời gian xử lý tại ứng dụng.
- Hàng đợi hữu hạn với ưu tiên rõ khi tác vụ được phép thực hiện bất đồng bộ.

Các giới hạn này phải được đo và điều chỉnh theo thí nghiệm. Một chính sách chỉ chú ý request/giây có thể bỏ sót các request ít nhưng tiêu tốn rất nhiều tài nguyên.

## 8. Giới hạn vùng ảnh hưởng (blast radius) tại điểm vào

**Blast radius** là phạm vi tài nguyên, dịch vụ và người dùng bị ảnh hưởng khi xảy ra lỗi hoặc lưu lượng bất thường. Mục tiêu phòng vệ không chỉ là chặn request ở edge mà còn là **đảm bảo một nhóm request hoặc một tenant không kéo sập các hành trình khác**.

### 8.1. Phân tách ưu tiên theo hành trình

Trong hệ thống đặt chỗ, nhóm có thể ưu tiên:

1. **Chức năng cốt lõi:** tra cứu tình trạng đặt chỗ, xác nhận trạng thái giao dịch và kiểm tra quyền truy cập.
2. **Chức năng quan trọng nhưng có phương án giảm tải:** tìm kiếm, lọc phòng, tải danh mục.
3. **Chức năng có thể trì hoãn:** báo cáo quản trị, gửi email không khẩn cấp, thống kê theo lô.

Đây là ví dụ; thứ tự ưu tiên thực tế do chủ nghiệp vụ phê duyệt. Khi áp lực tăng, hệ thống có thể phục vụ trang tĩnh/cached content, giảm tần suất cập nhật gợi ý, trì hoãn báo cáo, nhưng **không được trả kết quả đặt chỗ sai hoặc tự ý xác nhận thanh toán chưa được kiểm chứng**.

### 8.2. Các lớp giới hạn ảnh hưởng

| Kỹ thuật | Bảo vệ điều gì? | Giới hạn hoặc đánh đổi |
| --- | --- | --- |
| Cô lập đường vào theo hostname/route/tenant | Tránh một tuyến hoặc một nhóm khách chiếm toàn bộ hạn mức | Không tự cô lập CPU/DB nếu cùng dùng backend |
| Concurrency limit/bulkhead | Giữ số tác vụ đang chạy dưới mức an toàn ở gateway và downstream | Cần từ chối hoặc xếp hàng phần vượt ngưỡng |
| Queue hữu hạn và backpressure | Điều hòa tác vụ bất đồng bộ; bảo vệ dịch vụ ghi/worker | Queue quá lớn làm tăng thời gian chờ, chi phí và nguy cơ hết bộ nhớ |
| Timeout và cancellation | Tránh giữ tài nguyên vô hạn do đối tác hoặc DB chậm | Chọn timeout quá thấp có thể gây từ chối hợp lệ |
| Circuit breaker | Tạm hạn chế gọi dependency liên tục lỗi | Phải có cách thử phục hồi và tránh chuyển lỗi sang phần khác |
| Cache với TTL phù hợp | Giảm tải request đọc lặp lại | Cần quản lý dữ liệu cá nhân, cache stampede và độ mới chấp nhận được |
| Load shedding | Loại bỏ/từ chối một phần công việc khi không đủ năng lực | Phải xác định ưu tiên nghiệp vụ và phản hồi nhất quán |
| Hạn mức database/connection pool | Ngăn ứng dụng mở quá nhiều kết nối/transaction | Có thể giảm thông lượng; cần đo bão hòa |

Ví dụ, nếu cổng tìm kiếm có thể tạo 2.000 request/giây nhưng DB chỉ đáp ứng được 300 truy vấn nặng/giây, tăng thêm instance API mà không có cache, giới hạn đồng thời hoặc tối ưu truy vấn sẽ làm DB bão hòa nhanh hơn. **Điểm nghẽn phải được giới hạn gần nơi phát sinh chi phí và tại chính tài nguyên cần bảo vệ**.

### 8.3. Sơ đồ giới hạn tác động theo đường đi

~~~mermaid
flowchart LR
    NET["Internet / lưu lượng bất thường"]
    EDGE["DDoS protection + WAF tại edge"]
    GW["API Gateway: auth, rate, concurrency"]
    READ["Search: cache / read replicas"]
    WRITE["Booking: queue, idempotency, DB pool"]
    DB[("Database")]
    PAYMENT["Payment provider"]
    NET --> EDGE --> GW
    GW -->|Đọc| READ
    GW -->|Ghi| WRITE
    WRITE --> DB
    WRITE -->|Timeout + đối soát| PAYMENT
~~~

Đường đọc và đường ghi nên có cơ chế giới hạn phù hợp với đặc điểm dữ liệu. **Cùng dùng một DB hoặc một gateway** vẫn có thể khiến chúng ảnh hưởng nhau; cần quan sát CPU, connection pool, quota và thiết kế bulkhead thật ở lớp xử lý, thay vì chỉ tách nhãn route trên sơ đồ.

### 8.4. Bảo vệ nhiều tenant và hạn chế người dùng gây ồn

Với SaaS, một khách hàng lớn có thể dùng hợp pháp nhiều tài nguyên hơn khách hàng nhỏ. Hạn mức bình quân phải gắn với hợp đồng/quyền sử dụng và năng lực thực tế, có thể có **quota riêng theo tenant** kết hợp giới hạn an toàn toàn hệ thống. Chế độ ưu tiên không nên phụ thuộc vào những nhãn dễ giả mạo do client tự gửi.

Khi một tenant vượt hạn mức, hệ thống chỉ nên ảnh hưởng phần đã thỏa thuận của tenant đó, đồng thời giữ tài nguyên đủ cho các tenant khác. Nếu tất cả tenant chia sẻ một connection pool mà không có giới hạn, rate limit ngoài edge khó bảo đảm cô lập thực sự.

## 9. Bảo vệ đường vào của web, API, webhook và quản trị khác nhau

Không áp một chính sách chung cho mọi kiểu client:

| Điểm vào | Đặc điểm | Kiểm soát quan trọng |
| --- | --- | --- |
| Website công cộng | Trình duyệt, nội dung có phần cache được, cần trải nghiệm người dùng | CDN/cache, WAF phù hợp, TLS, bot detection thận trọng, rate limit theo rủi ro |
| Mobile API | Client tự động, nhiều thiết bị cùng IP NAT, có thể không thực hiện browser challenge | Xác thực token, rate limit theo tài khoản/client, versioning, giới hạn request hợp lệ |
| API đối tác | Đã có hợp đồng/định danh ứng dụng, lưu lượng theo lịch và quota riêng | API key/OAuth hoặc phương thức xác thực thích hợp, hạn mức theo client, audit và hợp đồng retry |
| Webhook thanh toán | Đối tác chủ động gửi sự kiện, có khả năng lặp và đến sai thứ tự | Xác minh chữ ký và thời gian/nonce nếu giao thức hỗ trợ, idempotency, queue, giới hạn kích thước và chống replay |
| Endpoint quản trị | Ít người dùng, quyền nhạy cảm, thao tác có rủi ro cao | Không công khai nếu không cần, MFA, truy cập có kiểm soát, audit và kiểm tra quyền chi tiết |
| Health check | Được gọi thường xuyên bởi hạ tầng | Quy tắc riêng theo nguồn/tầng kiểm tra, không làm lộ thông tin nhạy cảm |

### 9.1. Đừng yêu cầu webhook giải bài toán CAPTCHA

Nếu dùng challenge dành cho trình duyệt ở route webhook, đối tác thanh toán có thể không gửi được thông báo; đặt chỗ sẽ bị kẹt dù giao dịch đã thành công ở phía đối tác. Với webhook cần ưu tiên **xác thực thông điệp, nguồn kết nối nếu đáng tin và được công bố, kiểm tra payload, giới hạn tác động, chống xử lý trùng và đối soát**.

Tương tự, không loại trừ hoàn toàn webhook khỏi WAF chỉ vì có false positive. Ngoại lệ cần hẹp và phải bù bằng kiểm soát tương ứng. Một địa chỉ IP được nhà cung cấp công bố có thể thay đổi; cho phép theo IP mà bỏ qua xác thực chữ ký thường không đủ để chứng minh tính hợp lệ.

### 9.2. Bảo vệ tuyến nhạy cảm bằng idempotency

Ví dụ khách gửi yêu cầu tạo đặt chỗ, client bị timeout rồi gửi lại. Rate limit có thể giảm tần suất lặp nhưng **không ngăn mọi trường hợp ghi trùng**. Ứng dụng cần một khóa idempotency/định danh giao dịch phù hợp, quy tắc xử lý cạnh tranh và cơ chế trả lại trạng thái khi yêu cầu trước đã hoàn thành hoặc đang được xử lý.

Mỗi lần retry không được tự hiểu là một giao dịch mới. Hệ thống phải có cách đối soát với cổng thanh toán nếu kết quả mạng và trạng thái giao dịch không đồng nhất.

## 10. Kiểm soát khả dụng và các phụ thuộc ẩn của điểm vào

Điểm vào công khai phụ thuộc nhiều hệ thống ngoài process ứng dụng: DNS, chứng chỉ, edge network, WAF policy, API Gateway, dịch vụ danh tính, bộ đếm rate limit, route tới origin và telemetry. Một thay đổi cấu hình lỗi ở thành phần dùng chung có thể ảnh hưởng **mọi** request trong nhiều vùng.

### 10.1. Xác định miền lỗi và mức dự phòng

- **Đa availability zone:** giảm tác động của mất một zone, nhưng phải bảo đảm LB còn backend khỏe, DB và các dịch vụ phụ thuộc cũng có khả năng chịu lỗi.
- **Nhiều region:** có thể phục vụ khi một region mất kết nối nếu dữ liệu, DNS/routing, danh tính, quota và quy trình chuyển vùng đã sẵn sàng. Không mặc định "đa region" tự có RTO/RPO tốt.
- **Điểm vào toàn cầu:** cần xác định nhà cung cấp và control plane nào là phụ thuộc chung, các tuyến dự phòng và cách vận hành khi control plane không khả dụng.
- **DDoS protection và WAF:** phải tính khả năng áp dụng chính sách, rollback và bảo vệ ở mọi đường vào, kể cả tuyến dự phòng.
- **Quản lý định danh và giới hạn:** khi một thành phần chung chậm hoặc lỗi, cần xác định hành vi cho từng loại API thay vì để mọi request chờ vô hạn.

### 10.2. Không để route dự phòng trở thành đường vòng qua bảo mật

Nếu tạo DNS failover tới một origin dự phòng mà origin đó không có kiểm soát tương đương, lưu lượng độc hại có thể đi vào qua tuyến dự phòng. Ngược lại, nếu chỉ có một nhà cung cấp WAF/edge và nhà cung cấp đó không thể phục vụ, thiết kế dự phòng cần xác định **phương án được chấp thuận và rủi ro khi kích hoạt**.

Một route dự phòng phải được kiểm tra như route chính: TLS, WAF/rate limit khi áp dụng, xác thực, mạng, dữ liệu, logging và điều kiện chuyển đổi. Đừng triển khai tuyến phụ chỉ để vượt health check mà chưa kiểm tra tác động khi xảy ra sự cố thật.

## 11. Giám sát, cảnh báo và đánh giá tác động

Phòng vệ điểm vào cần quan sát trên **ba lớp: lưu lượng đi vào, hiệu quả kiểm soát, trạng thái nghiệp vụ phía sau**.

| Nhóm chỉ số | Ví dụ cần theo dõi | Dùng để quyết định |
| --- | --- | --- |
| Lưu lượng L3/L4 | Băng thông, connections/s, packets/s, lỗi thiết lập kết nối, tín hiệu từ dịch vụ chống DDoS | Có nghẽn trước WAF/origin không? |
| Request L7 | RPS theo hostname/route, status code, request size, user agent và đặc điểm client hợp lệ | Route nào tăng tải, tăng vì chiến dịch hay bất thường? |
| WAF/bot | Tỷ lệ allow/block/challenge/count, rule ID, mức nghi ngờ và false positive qua bộ mẫu | Rule nào đang giảm nguy cơ, rule nào chặn nhầm? |
| Rate limiting | Số 429 theo danh tính/route/tenant, quota còn lại, tỷ lệ retry | Giới hạn có hợp lý hay đang gây lỗi trải nghiệm? |
| Hiệu năng edge và backend | p95/p99, backend errors, connection pool, queue depth, CPU/DB saturation | Có giảm được áp lực lên tài nguyên cần bảo vệ không? |
| Nghiệp vụ | Đăng nhập thành công, tìm phòng, tỷ lệ hoàn tất đặt chỗ, webhook xử lý hợp lệ | Người dùng thật còn hoàn thành hành trình không? |
| Chi phí | WAF request, CDN traffic, egress, log volume, phí chống DDoS/giám sát theo hợp đồng | Chi phí phòng vệ và cuộc tấn công có vượt kịch bản dự báo không? |

**Bảo vệ log và dữ liệu:** không ghi mật khẩu, token, cookie phiên, dữ liệu thanh toán nhạy cảm hay toàn bộ request body một cách mặc định vào WAF/access log. Cần che dữ liệu, phân quyền đọc, thời hạn lưu và đánh giá nơi lưu log theo yêu cầu nghiệp vụ/pháp lý.

### 11.1. Một dashboard tối thiểu cần trả lời được

1. Mức request/giây và băng thông thay đổi như thế nào ở từng điểm vào?
2. Tỷ lệ HTTP 2xx/4xx/5xx, 429 và các trường hợp challenge phân bố theo route/tenant ra sao?
3. Có bao nhiêu yêu cầu bị từ chối trước khi tới origin? Tỷ lệ chặn nhầm hợp lệ ước tính thế nào?
4. Điểm nghẽn chuyển từ edge xuống app, DB hoặc đối tác hay không?
5. Hành trình tìm kiếm và đặt chỗ còn đáp ứng SLO không?
6. Người trực có thể xác định version WAF rule và thay đổi cấu hình gần nhất không?

Thêm cảnh báo khi tỷ lệ lỗi, latency, backend saturation, WAF blocks hoặc 429 vượt ngưỡng có ý nghĩa. Cảnh báo chỉ dựa vào "RPS tăng" có thể báo động oan trong chiến dịch; nên kết hợp **sức khỏe hệ thống, tín hiệu bảo mật và kết quả người dùng**.

### 11.2. Phân biệt tác động thực của cuộc tấn công

Một đợt lưu lượng bị chặn tại edge với backend vẫn khỏe có ý nghĩa khác với một đợt khiến dữ liệu không thể truy cập. Báo cáo sau sự cố nên gồm thời gian bắt đầu/kết thúc, phạm vi request, ngưỡng kích hoạt, rule gây ảnh hưởng, tỷ lệ người dùng hợp lệ bị tác động, thời gian phục hồi, chi phí và thay đổi phòng vệ cần triển khai.

## 12. Quy trình ứng phó tại điểm vào

Một runbook phòng vệ phải mô tả **ai quyết định thay đổi chính sách, sửa gì, đo bằng cách nào và khi nào rollback**.

~~~mermaid
flowchart TD
    A["Phát hiện bất thường tại edge/gateway"] --> B["Xác minh SLI nghiệp vụ và dấu hiệu DDoS/bot"]
    B --> C{"Lớp nào bị ảnh hưởng?"}
    C -->|L3/L4| D["Phối hợp bảo vệ upstream / nhà cung cấp mạng"]
    C -->|L7/API| E["Xem rule WAF, rate, cache và tải backend"]
    D --> F["Áp biện pháp đã phê duyệt có thời hạn"]
    E --> F
    F --> G["Đo thành công hợp lệ, false positive, p95 và chi phí"]
    G --> H{"Đã về ngưỡng chấp nhận?"}
    H -->|Chưa| B
    H -->|Rồi| I["Ổn định, ghi timeline và rà soát phòng ngừa"]
~~~

### Quy trình tham khảo

1. **Triage:** xác định mục tiêu bị ảnh hưởng, nguồn telemetry đáng tin, các request hợp lệ và rủi ro đang diễn ra; phân biệt DDoS hạ tầng, L7, bot, sự cố cấu hình và flash crowd.
2. **Khoanh vùng:** xác định hostname/route/tenant bị ảnh hưởng, phụ thuộc ứng dụng đang bão hòa và mức cần bảo vệ. Liên hệ nhà cung cấp upstream nếu đường mạng đã nghẽn.
3. **Giảm thiểu trong phạm vi cần thiết:** điều chỉnh managed/custom WAF rule, rate limit, cache, access policy hoặc giới hạn đồng thời theo runbook đã duyệt.
4. **Đo hiệu quả liên tục:** tỷ lệ người dùng hợp lệ, p95, error budget, WAF false positive, connection pool và chi phí. Không coi số block tăng là bằng chứng duy nhất.
5. **Chuyển/khôi phục hành trình cần thiết:** với tuyến ghi, đảm bảo không mất tính nhất quán và đối soát; với tuyến đọc, có thể dùng dữ liệu cached khi nghiệp vụ cho phép.
6. **Khôi phục cấu hình an toàn:** rollback quy tắc khẩn cấp khi không còn cần thiết; tránh giữ danh sách chặn hay ngoại lệ quá rộng không có thời hạn.
7. **Rút kinh nghiệm:** cập nhật mô hình tải, policy, kiểm thử, dự toán và phân công owner; lưu bằng chứng phục vụ đánh giá Well-Architected.

Phân quyền nên rõ: người trực SRE có thể thực hiện các biện pháp giảm thiểu đã được phê duyệt; thay đổi nhạy cảm cần security hoặc owner tương ứng; truy cập khẩn cấp phải được ghi audit. Trong môi trường nhiều nhà cung cấp, cần biết ai liên hệ ISP, cloud provider và nhà cung cấp CDN/WAF.

## 13. Áp dụng vào nền tảng đặt chỗ: ma trận bảo vệ điểm vào

Giả định hệ thống có bốn tuyến khách hàng và một tuyến đối tác. Mỗi tuyến có mức tiêu thụ và rủi ro khác nhau:

| Tuyến | Bảo vệ tại edge | Giới hạn trong gateway/app | Cách giảm tác động |
| --- | --- | --- | --- |
| GET /rooms/search | WAF phù hợp, chống bot, CDN/cache các response được phép | Giới hạn theo danh tính/IP có kiểm soát, giới hạn truy vấn nặng | Tối ưu chỉ mục, cache, giảm các bộ lọc tốn tài nguyên khi có tải cao |
| POST /auth/login | WAF, phát hiện lạm dụng, challenge phù hợp với loại client | Rate limit theo tài khoản và tín hiệu rủi ro, MFA cho tình huống cần | Cô lập pool xác thực, cảnh báo đăng nhập bất thường |
| POST /bookings | WAF, TLS, xác thực; không cache kết quả giao dịch tùy tiện | Rate và concurrency riêng, idempotency, kiểm tra quyền, DB transaction | Bảo vệ DB pool, phản hồi rõ trạng thái đang xử lý khi dependency chậm |
| GET /bookings/{id} | WAF và xác thực | Ủy quyền theo đơn hàng, giới hạn đọc theo user | Không cache chéo khách; duy trì ưu tiên tra cứu trạng thái |
| POST /payments/webhook | WAF rule riêng không ép browser challenge | Chữ ký thông điệp, idempotency, giới hạn body, queue hữu hạn | Đối soát khi chậm, không mất trạng thái giao dịch khi nhận lặp |

**Lưu ý:** các route và biện pháp là ví dụ logic; cần điều chỉnh theo hợp đồng API, cách tích hợp thanh toán, khả năng của sản phẩm WAF và yêu cầu tuân thủ. Nếu một quy tắc WAF gây chặn webhook, ưu tiên **tạo ngoại lệ hẹp có kiểm soát** và kiểm chứng chữ ký tại ứng dụng.

### 13.1. Mẫu chính sách trung lập để thảo luận

Đây là cấu hình **minh họa ý định**, không phải YAML có thể áp trực tiếp cho một dịch vụ cloud:

~~~yaml
edgePolicy:
  hostname: api.example.invalid
  tlsRequired: true
  allowedEntry:
    - approved-edge
  waf:
    managedRules:
      mode: monitor-then-enforce
    exceptions:
      - route: POST /payments/webhook
        reason: Không áp browser challenge cho client máy-máy
        compensatingControls:
          - verify-webhook-signature
          - idempotent-event-processing
  limits:
    search:
      identity: authenticated-user-or-trusted-client-signal
      algorithm: token-bucket
      ratePerSecond: 10   # Giá trị giả định, không áp dụng mặc định
      burst: 20           # Cần hiệu chỉnh theo tải và false positive
    booking:
      identity: authenticated-user
      requireIdempotency: true
      concurrencyControl: enabled
  monitoring:
    - edge-http-latency
    - waf-action-by-rule
    - backend-error-rate
    - completed-bookings
    - false-positive-review
~~~

Trước khi đưa vào production phải kiểm chứng công cụ cloud có hỗ trợ đúng **loại limiter, danh tính, hành động WAF và phạm vi kết nối** đã mô tả không. Ngưỡng 10 request/giây và burst 20 chỉ để minh họa cơ chế, chưa thể dùng cho API tìm phòng nếu chưa có bằng chứng từ traffic và thử nghiệm.

### 13.2. Đánh giá bằng kiểm thử đã được cho phép

| Kịch bản | Kết quả cần kiểm tra |
| --- | --- |
| Request hợp lệ từ web/mobile | Đi đúng qua edge, TLS và xác thực phù hợp; không bị chặn sai do quy tắc WAF mới |
| Request HTTP không hợp lệ trong tập kiểm thử an toàn | Bị lọc/ghi nhận theo quy tắc dự kiến, có rule ID và bằng chứng |
| Tải hợp lệ tăng theo chiến dịch trên môi trường thử nghiệm | Tăng năng lực/điều tiết phù hợp, p95 và tỉ lệ thành công đạt mục tiêu đã thống nhất |
| Client thử vượt hạn mức API trong phạm vi tải kiểm thử được phê duyệt | Nhận thông báo hạn mức thích hợp, không làm sập gateway/backend hoặc ảnh hưởng các client khác |
| Webhook hợp lệ gửi lặp theo hợp đồng tích hợp | Chỉ xử lý nghiệp vụ một lần; kết quả và audit đúng |
| Backend xử lý chậm hoặc DB đạt giới hạn | Concurrency/queue/timeout bảo vệ tài nguyên; chức năng độc lập vẫn phục vụ |
| Origin bị truy cập bằng đường ngoài điểm vào | Bị từ chối bởi cấu hình mạng/xác thực kết nối; không bypass WAF |
| Một quy tắc WAF mới chặn nhầm khách | Phát hiện từ SLI/log, rollback và phục hồi lưu lượng hợp lệ trong thời gian quy định |

Không tạo traffic phá hoại vào dịch vụ công cộng hoặc hạ tầng chưa được cho phép. Các kiểm thử tải và lỗi nên thực hiện trên môi trường được quản lý, với giới hạn đã duyệt, thời điểm phù hợp và khả năng dừng thử nghiệm; bài thực hành có thể mô phỏng tín hiệu và hành vi phòng vệ thay vì tạo một cuộc DDoS thực.

## 14. Chi phí, vận hành và đánh đổi Well-Architected

Chi phí bảo vệ có thể bao gồm dịch vụ chống DDoS nâng cao, CDN/WAF, các rule/rate rule, request hoặc dung lượng được kiểm tra, bot challenge, load balancer, lưu lượng ra Internet, log, giám sát và nhân lực trực sự cố. Mô hình tính phí khác nhau theo sản phẩm, nên cần xem hợp đồng/bảng giá của dịch vụ cụ thể. **Lưu lượng bị chặn sớm có thể giảm tải backend nhưng vẫn tạo chi phí tại edge hoặc logging** tùy sản phẩm.

| Trụ cột | Câu hỏi đánh giá |
| --- | --- |
| **Security** | Các tuyến công khai có WAF phù hợp, TLS, xác thực, phân quyền và chống origin bypass không? |
| **Reliability** | Khi bị quá tải, có giữ được hành trình quan trọng, phát hiện sớm và tránh điểm lỗi chung tại edge không? |
| **Performance Efficiency** | Cache, rate limit và concurrency có bảo vệ DB mà vẫn giữ p95 cho khách hợp lệ không? |
| **Operational Excellence** | Có owner, runbook, thử nghiệm rule, giám sát false positive, rollback và quy trình phối hợp với nhà cung cấp không? |
| **Cost Optimization** | Có dự báo request/traffic/log, chi phí bảo vệ và kịch bản lưu lượng bất thường, tránh tạo chi phí không giới hạn không? |
| **Sustainability** | Có giảm request và xử lý lặp vô ích, tận dụng cache phù hợp và tránh scale tài nguyên dư thừa không? |

Đánh đổi cần ghi rõ: tăng mức lọc WAF có thể giảm tấn công nhưng tăng chặn sai; tăng challenge có thể chống bot nhưng hại trải nghiệm; thêm dịch vụ trung gian có thể tăng độ trễ/chi phí và thêm điểm lỗi; tăng mức dự phòng giúp phục vụ dưới tải cao nhưng phải có ngân sách. **Quyết định dựa trên mục tiêu và bằng chứng**, không phải số lượng tính năng bảo vệ đã bật.

## 15. Bài thực hành: phòng vệ điểm vào cho hệ thống đặt chỗ

**Bối cảnh:** một nền tảng đặt chỗ đang mở rộng từ một khu vực sang nhiều khu vực. Lưu lượng tìm phòng biến động lớn vào kỳ nghỉ. API tạo đơn ghi vào database, còn webhook thanh toán được gửi từ hệ thống đối tác. Công ty yêu cầu bảo vệ origin, giảm sự cố do bot và giữ những hành trình quan trọng khi có tải bất thường.

**Yêu cầu thực hiện:**

1. **Lập threat model**: liệt kê ít nhất ba kiểu rủi ro ở L3/L4/L7, mục tiêu bị ảnh hưởng, điểm chặn phù hợp và những hành vi được phép.
2. **Vẽ đường đi ingress** từ client qua DNS, lớp bảo vệ DDoS, WAF, API Gateway/LB tới workload private; chỉ rõ nơi kết thúc TLS và cách ngăn origin bypass.
3. **Thiết kế chính sách riêng cho năm route** đã nêu; chọn khóa rate limit, hành động khi vượt giới hạn và lý do không challenge webhook.
4. **Đề xuất bulkhead** cho search, booking và tác vụ báo cáo; xác định thành phần nào có thể cache/xếp hàng, thành phần nào cần nhất quán tức thời.
5. **Định nghĩa bốn tiêu chí nghiệm thu** về SLI nghiệp vụ, p95, false positive, phát hiện sự cố và xác định các công cụ thu thập.
6. **Mô tả hai sự cố:** một WAF rule chặn nhầm khách hợp lệ và một đợt tải làm bão hòa DB. Lập quy trình triage, giảm thiểu, rollback và cách chứng minh trạng thái phục hồi.
7. **Ước lượng chi phí** của CDN, WAF, bảo vệ DDoS, gateway, dữ liệu và log theo tải bình thường, cao điểm và tải bất thường; nêu giả định cần xác minh.
8. **Viết ADR rút gọn** về điểm vào, các phương án đã cân nhắc, đánh đổi giữa an toàn, hiệu năng, độ tin cậy và ngân sách, cùng điều kiện cần xem lại.

### Tiêu chí hoàn thành

| Tiêu chí | Dấu hiệu đạt |
| --- | --- |
| Phân lớp phòng vệ | Không nhầm WAF với cơ chế xử lý volumetric DDoS upstream; có điểm kiểm soát phù hợp từng loại rủi ro |
| Bảo vệ đúng endpoint | Có chính sách khác nhau cho search, booking, login và webhook; có quyền/nghiệp vụ phía ứng dụng |
| Giới hạn tác động | Rate limit, concurrency, timeout và queue có mục tiêu rõ; tải tìm kiếm không được phép làm sai giao dịch đặt chỗ |
| Chống chặn sai | Có tập request hợp lệ, đo false positive, canary và rollback WAF rule |
| Vận hành được | Có SLI, cảnh báo, owner, runbook và quy trình xử lý sự cố có kiểm chứng |
| Kiểm soát chi phí | Có dự báo chi phí edge/log cùng lưu lượng bất thường và người quyết định khi vượt ngưỡng |

## 16. Checklist trước khi đưa điểm vào vào production

- [ ] Xác định đầy đủ các hostname, route, port và loại client được phép truy cập từ bên ngoài.
- [ ] Đã rà soát bảo vệ L3/L4 ở phía upstream và hiểu phạm vi/giới hạn dịch vụ chống DDoS đang dùng.
- [ ] Đã bảo vệ origin khỏi đường truy cập bỏ qua WAF/CDN/gateway.
- [ ] Đã xác định TLS termination, kết nối edge–origin và chuỗi proxy tin cậy khi đọc IP client.
- [ ] Đã phân nhóm endpoint theo rủi ro, độ nhạy cảm và chi phí xử lý; không dùng một quy tắc cho mọi route.
- [ ] Đã kiểm thử managed/custom WAF rules, false positive, thay đổi policy và cách rollback.
- [ ] Đã có rate limiting theo danh tính/tenant/route phù hợp, cùng hành vi 429/503 và retry an toàn.
- [ ] Đã xác định giới hạn đồng thời, kích thước request, timeout, queue và bảo vệ database.
- [ ] Đã bảo vệ webhook bằng xác thực thông điệp, chống lặp và ngoại lệ WAF thật hẹp khi cần.
- [ ] Đã có kịch bản suy giảm có kiểm soát và kiểm thử khi một dependency hoặc một lớp edge gặp lỗi.
- [ ] Đã có dashboard kết hợp lưu lượng, WAF action, p95, lỗi backend, kết quả giao dịch và chi phí.
- [ ] Đã định nghĩa người trực, kênh phối hợp upstream, quyền thay đổi khẩn cấp và runbook rollback.
- [ ] Đã kiểm thử đường dự phòng và đánh giá rằng nó có kiểm soát bảo mật tương đương đường chính.
- [ ] Đã ghi các quyết định và đánh đổi theo Well-Architected bằng ADR có bằng chứng.

Phòng vệ điểm vào hiệu quả là kết quả của **kiến trúc nhiều lớp và kiểm soát tác động**, từ chống DDoS ở phía mạng đến WAF, giới hạn sử dụng API và bảo vệ tài nguyên phía sau. Khi các lớp đó được kiểm chứng bằng hành trình người dùng hợp lệ, phép đo độ trễ, tỷ lệ chặn sai, thử nghiệm lỗi và quy trình vận hành, hệ thống mới có cơ sở vững chắc để duy trì dịch vụ dưới tải bất thường.
