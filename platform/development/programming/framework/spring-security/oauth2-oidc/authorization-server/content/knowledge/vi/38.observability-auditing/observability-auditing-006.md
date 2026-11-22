# Theo dõi tải cơ sở dữ liệu, pool kết nối và kho khóa

Authorization Server thường phải đọc và ghi dữ liệu trong những thời điểm nhạy cảm của luồng OAuth 2.0 và OpenID Connect. Khi người dùng đăng nhập, chấp thuận consent, đổi authorization code hoặc refresh token, ứng dụng có thể truy cập dữ liệu client, authorization và consent. Sau đó máy chủ còn phải ký token bằng khóa riêng tương ứng. Nếu cơ sở dữ liệu chậm, pool kết nối cạn hoặc kho khóa không sẵn sàng, độ trễ và tỷ lệ lỗi của toàn bộ luồng cấp token sẽ tăng.

Theo dõi riêng từng thành phần giúp xác định nút thắt nằm ở ứng dụng, pool kết nối, cơ sở dữ liệu hay dịch vụ khóa. Bài học này tập trung vào các tín hiệu vận hành, cách thu thập chúng bằng Spring Boot Actuator và Micrometer, cách đặt cảnh báo, cùng quy trình điều tra khi hệ thống gặp sự cố.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích được các chỉ số phản ánh tải và độ trễ của cơ sở dữ liệu trong Authorization Server.
- Phân biệt tình trạng quá tải cơ sở dữ liệu với tình trạng cạn pool kết nối ở từng instance ứng dụng.
- Ước lượng giới hạn kết nối an toàn khi Authorization Server chạy nhiều replica.
- Theo dõi khả năng đọc khóa, ký token, trạng thái xoay vòng khóa và độ sẵn sàng của KMS hoặc HSM.
- Xuất metrics bằng Actuator và Micrometer, thiết kế dashboard và cảnh báo có ích.
- Điều tra sự cố theo thứ tự từ request, ứng dụng, pool, cơ sở dữ liệu đến kho khóa mà không làm lộ token hoặc bí mật.

## Bức tranh quan sát của Authorization Server

Một luồng cấp token có thể đi qua nhiều thành phần. Ví dụ, khi xử lý authorization code, máy chủ kiểm tra client và authorization đã lưu, xác minh các dữ liệu cần thiết, tạo token rồi ký token bằng khóa riêng. Khi refresh token, máy chủ có thể đọc và cập nhật bản ghi authorization. Với cấu hình JDBC, các dịch vụ lưu trữ như `JdbcRegisteredClientRepository`, `JdbcOAuth2AuthorizationService` và `JdbcOAuth2AuthorizationConsentService` tạo tải lên cơ sở dữ liệu. Cách triển khai cụ thể có thể khác nhau, vì vậy hãy xác nhận thành phần lưu trữ thực tế của hệ thống trước khi đặt dashboard.

| Thành phần | Câu hỏi cần trả lời | Tín hiệu chính |
|---|---|---|
| Authorization Server | Request cấp token có chậm hoặc thất bại không? | Tỷ lệ request, độ trễ, mã lỗi, trace |
| DataSource và pool | Ứng dụng có lấy được kết nối đúng lúc không? | Kết nối active/idle, pending, timeout, thời gian acquire |
| Cơ sở dữ liệu | Máy chủ dữ liệu có đủ tài nguyên và xử lý truy vấn nhanh không? | Kết nối, CPU, I/O, query latency, lock wait, deadlock |
| Kho khóa hoặc KMS/HSM | Ứng dụng có tải được khóa và ký token thành công không? | Lỗi tải khóa, độ trễ ký, lỗi KMS/HSM, tuổi khóa, trạng thái xoay vòng |

Nên kết hợp metrics, logs và traces. Metrics cho biết xu hướng và mức độ ảnh hưởng; logs cung cấp sự kiện cụ thể; traces nối thời gian xử lý của một request qua các thành phần. Không một loại tín hiệu nào thay thế được hai loại còn lại.

## 1. Theo dõi tải cơ sở dữ liệu

### 1.1. Theo dõi cả phía ứng dụng và phía cơ sở dữ liệu

Chỉ nhìn vào CPU của máy chủ cơ sở dữ liệu là chưa đủ. Một database có CPU thấp vẫn có thể khiến ứng dụng chậm vì truy vấn chờ lock, kết nối bị giới hạn, I/O tăng hoặc một số truy vấn có thời gian phản hồi dài. Ngược lại, pool ở ứng dụng có thể cạn dù database chưa đạt giới hạn tài nguyên, chẳng hạn do transaction giữ kết nối quá lâu.

Thu thập ít nhất các nhóm chỉ số sau:

| Nhóm | Chỉ số nên quan sát | Ý nghĩa khi chỉ số tăng bất thường |
|---|---|---|
| Kết nối database | Số session hiện tại, số kết nối tối đa, số kết nối đang hoạt động | Nhiều ứng dụng hoặc replica cùng sử dụng database; nguy cơ chạm giới hạn kết nối |
| Truy vấn | Thời gian trung bình và p95/p99, số truy vấn chậm, throughput | Truy vấn hoặc chỉ mục có vấn đề; tải tăng vượt khả năng xử lý |
| Transaction | Số transaction đang mở, thời gian transaction, transaction bị rollback | Transaction dài, giữ lock hoặc giữ kết nối quá lâu |
| Lock | Thời gian chờ lock, deadlock, số session bị block | Tranh chấp khi cập nhật authorization hoặc consent, hoặc thiết kế transaction chưa phù hợp |
| Tài nguyên | CPU, bộ nhớ, I/O, dung lượng và tốc độ tăng dữ liệu | Database thiếu tài nguyên hoặc sắp hết dung lượng |
| Đồng bộ dữ liệu | Replication lag, trạng thái replica, lỗi failover (nếu có) | Đọc từ replica có thể trả dữ liệu trễ; failover có thể làm gián đoạn request |

Tên metric và cách lấy số liệu phụ thuộc hệ quản trị cơ sở dữ liệu. Có thể dùng công cụ giám sát tích hợp của dịch vụ database, exporter phù hợp, view thống kê của hệ quản trị hoặc công cụ quản trị do tổ chức cung cấp. Hãy kiểm tra đơn vị đo và ý nghĩa của từng metric trước khi đưa vào dashboard.

### 1.2. Liên hệ tải database với hoạt động OAuth/OIDC

Các thao tác sau thường tạo tải đọc hoặc ghi:

- Tra cứu cấu hình client khi xác thực client hoặc xử lý yêu cầu ủy quyền.
- Đọc và lưu authorization khi cấp authorization code, access token hoặc refresh token.
- Đọc và cập nhật consent khi người dùng chấp thuận hoặc thay đổi quyền đã cấp.
- Thu hồi authorization hoặc refresh token khi có yêu cầu logout, revoke hay quy trình quản trị tương ứng.
- Các tác vụ nền như dọn dữ liệu hết hạn, đồng bộ hoặc migration nếu hệ thống có triển khai.

Khi độ trễ tăng, hãy đối chiếu thời điểm và loại luồng với trace hoặc log ứng dụng. Ví dụ, nếu request refresh token tăng p95 đồng thời với thời gian truy vấn cập nhật authorization, hãy kiểm tra câu truy vấn, lock và transaction liên quan. Nếu tất cả luồng đều chậm nhưng truy vấn database bình thường, cần mở rộng điều tra sang pool, mạng hoặc kho khóa.

Không ghi access token, refresh token, authorization code, client secret, mã xác thực hoặc nội dung nhạy cảm của authorization vào log truy vấn. Nếu cần nhận diện truy vấn, dùng fingerprint hoặc tên thao tác đã chuẩn hóa thay vì ghi giá trị tham số. Cần giới hạn quyền truy cập vào slow query log vì câu SQL và tham số đôi khi chứa dữ liệu cá nhân.

### 1.3. Theo dõi chất lượng truy vấn và transaction

Một truy vấn có thời gian trung bình thấp vẫn có thể có p99 rất cao. Hãy theo dõi phân vị độ trễ, số lần thực thi và lượng dữ liệu đọc/ghi. Khi phát hiện truy vấn bất thường:

1. Xác định thao tác ứng dụng và fingerprint truy vấn liên quan.
2. Kiểm tra execution plan bằng công cụ phù hợp với hệ quản trị cơ sở dữ liệu.
3. Xác minh chỉ mục, điều kiện lọc, số hàng được đọc và số hàng thực tế trả về.
4. Kiểm tra transaction có giữ lock hoặc kết nối trong lúc thực hiện công việc không liên quan đến database hay không.
5. Đo lại dưới tải đại diện sau khi điều chỉnh.

Không thêm chỉ mục một cách máy móc. Chỉ mục có thể giảm thời gian đọc nhưng làm tăng chi phí ghi, dung lượng lưu trữ và công việc bảo trì. Quyết định cần dựa trên workload thực tế của các bảng client, authorization và consent.

## 2. Theo dõi và cấu hình pool kết nối

### 2.1. Pool giải quyết vấn đề gì?

Mở kết nối database cho từng request thường tốn thời gian và tài nguyên. Connection pool giữ sẵn một tập kết nối để các request mượn và trả lại. Trong nhiều ứng dụng Spring Boot, HikariCP là pool mặc định khi có mặt trên classpath và cấu hình phù hợp.

Pool có giới hạn. Khi mọi kết nối đều đang được sử dụng, request mới phải chờ. Nếu thời gian chờ vượt `connectionTimeout`, pool phát sinh lỗi lấy kết nối. Điều này có thể xảy ra ngay cả khi database vẫn còn khả năng xử lý thêm truy vấn, ví dụ do ứng dụng giữ kết nối quá lâu.

Các metric thường gặp của HikariCP gồm:

| Metric | Cách đọc |
|---|---|
| `hikaricp.connections.active` | Số kết nối đang được ứng dụng sử dụng |
| `hikaricp.connections.idle` | Số kết nối đang rảnh trong pool |
| `hikaricp.connections.max` | Giới hạn kết nối tối đa của pool |
| `hikaricp.connections.min` | Mức kết nối tối thiểu được cấu hình |
| `hikaricp.connections.pending` | Số luồng đang chờ lấy kết nối |
| `hikaricp.connections.timeout` | Số lần không lấy được kết nối trước timeout |
| `hikaricp.connections.acquire` | Thời gian chờ lấy kết nối |
| `hikaricp.connections.usage` | Thời gian một kết nối được giữ trước khi trả lại pool |

Tên và dạng export có thể thay đổi theo phiên bản Micrometer, HikariCP và registry. Kiểm tra danh sách metric thực tế tại endpoint metrics hoặc trong hệ thống giám sát trước khi viết truy vấn dashboard.

### 2.2. Đọc dấu hiệu pool bị nghẽn

Một pool hoạt động bình thường thường có số kết nối active thay đổi theo tải, còn pending gần bằng không trong phần lớn thời gian. Cần điều tra khi xuất hiện một hoặc nhiều dấu hiệu:

- `active` thường xuyên tiến sát `max`.
- `pending` tăng và duy trì qua nhiều khoảng lấy mẫu.
- Thời gian `acquire` tăng cùng lúc với p95/p99 của request.
- Bộ đếm timeout tăng.
- Thời gian `usage` dài bất thường, cho thấy kết nối bị giữ lâu.

Một đỉnh ngắn có thể chỉ phản ánh burst traffic. Hãy đối chiếu với request rate, thời gian truy vấn và thời gian transaction. Nếu active cao nhưng database vẫn nhàn, hãy tìm transaction kéo dài, tác vụ đồng bộ chạy trong lúc giữ kết nối, hoặc nhánh code không trả kết nối đúng cách. Nếu active cao cùng CPU, I/O và query latency của database, database có thể là nút thắt thực sự.

### 2.3. Ước lượng kích thước pool

Không nên chọn `maximumPoolSize` chỉ dựa trên số CPU của ứng dụng hoặc tăng nó mỗi khi thấy pending. Mỗi kết nối bổ sung làm tăng tài nguyên database phải duy trì. Với nhiều replica, tổng kết nối có thể vượt giới hạn database dù pool ở từng instance có vẻ nhỏ.

Ước lượng tổng kết nối ứng dụng theo công thức:

\[
C_{app}=N_{replica}\times P_{max}
\]

Trong đó `N_replica` là số replica tối đa có thể chạy trong kịch bản scale hoặc rolling deployment, còn `P_max` là `maximumPoolSize` trên mỗi replica. Sau đó cộng thêm kết nối từ worker, dịch vụ khác, migration, công cụ quản trị và giám sát. Tổng dự kiến phải thấp hơn giới hạn database, đồng thời dành một phần dự phòng cho failover và thao tác vận hành.

Có thể dùng định luật Little để ước lượng sơ bộ số kết nối đồng thời cần thiết:

\[
L\approx \lambda\times W
\]

Trong đó `λ` là số thao tác database mỗi giây và `W` là thời gian trung bình một thao tác giữ kết nối, tính bằng giây. Đây chỉ là ước lượng ban đầu: workload có phân bố đuôi dài, transaction nhiều truy vấn và tải đột biến cần được kiểm chứng bằng thử tải.

Ví dụ: một hệ thống có tối đa 6 replica và pool tối đa 12 kết nối mỗi replica có thể mở tới 72 kết nối ứng dụng. Nếu database cho phép 100 kết nối, con số 72 chưa phải toàn bộ tải: các service khác, migration và phiên quản trị cũng dùng chung giới hạn đó. Khi rolling deployment, replica cũ và mới có thể cùng tồn tại trong một khoảng thời gian, vì vậy cần tính cả số replica tạm thời.

### 2.4. Cấu hình pool minh họa

Ví dụ cấu hình HikariCP trong `application.yml`:

```yaml
spring:
  datasource:
    hikari:
      pool-name: authorization-server
      maximum-pool-size: 12
      minimum-idle: 3
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1740000
```

Các con số trên chỉ minh họa cú pháp, không phải cấu hình tối ưu cho mọi môi trường. Hãy chọn `maximum-pool-size` dựa trên giới hạn database và số replica; đặt `max-lifetime` thấp hơn thời gian sống tối đa do database hoặc hạ tầng mạng áp đặt; và chọn timeout phù hợp với ngân sách độ trễ của request. `minimum-idle` ảnh hưởng số kết nối giữ sẵn. Với một số cấu hình, `idle-timeout` không có tác dụng như mong đợi nếu pool được giữ ở kích thước cố định.

Không tăng `connection-timeout` để che giấu pool cạn. Timeout dài có thể làm request giữ thread lâu hơn và tạo hàng đợi lớn hơn. Trước tiên cần xác định kết nối bị giữ bởi truy vấn chậm, lock, transaction dài hay cấu hình pool thiếu hợp lý.

### 2.5. Phát hiện kết nối bị giữ quá lâu

HikariCP có tùy chọn `leak-detection-threshold` để ghi log khi một kết nối được mượn lâu hơn ngưỡng cấu hình. Đây là công cụ chẩn đoán, không phải cơ chế tự sửa leak. Chỉ bật khi điều tra và đặt ngưỡng dựa trên thời gian xử lý bình thường; ngưỡng quá thấp tạo nhiều log nhiễu. Khi phát hiện cảnh báo, kiểm tra stack trace nơi kết nối được mượn và bảo đảm transaction hoặc tài nguyên JDBC được giải phóng đúng cách.

Các thao tác gọi HTTP, KMS/HSM, ghi file hoặc xử lý nặng nên nằm ngoài transaction database nếu nghiệp vụ cho phép. Giữ transaction mở trong lúc chờ dịch vụ từ xa làm kết nối bị chiếm dụng và tăng nguy cơ cạn pool. Hãy thiết kế ranh giới transaction ngắn, rõ ràng và kiểm tra lại tính nhất quán nghiệp vụ khi tách thao tác.

## 3. Theo dõi kho khóa và hoạt động ký token

### 3.1. Những điểm cần quan sát

Authorization Server cần khóa phù hợp để ký token và công bố khóa công khai cho bên tiêu thụ xác minh chữ ký. Khóa có thể được nạp từ JKS/PKCS12, file được bảo vệ, secret manager, KMS hoặc HSM. Cách lưu trữ quyết định cách thu thập tín hiệu, nhưng các câu hỏi vận hành cơ bản vẫn giống nhau:

- Ứng dụng có nạp được khóa khi khởi động và khi làm mới cấu hình không?
- Khóa đang dùng có đúng mục đích, thuật toán và trạng thái hiệu lực không?
- Hoạt động ký có thành công và nằm trong ngân sách độ trễ không?
- KMS/HSM có phản hồi, có bị giới hạn quota hoặc throttling không?
- Khóa sắp hết hạn hoặc đến thời điểm xoay vòng chưa?
- JWKS công khai có chứa khóa cần thiết để xác minh token còn hiệu lực không?

Nên có các metric hoặc sự kiện sau:

| Nhóm | Tín hiệu |
|---|---|
| Nạp khóa | Số lần nạp thành công/thất bại, thời gian nạp, lần nạp thành công gần nhất |
| Ký token | Số lần ký, độ trễ ký p95/p99, số lần ký thất bại |
| KMS/HSM | Độ trễ request, tỷ lệ lỗi, timeout, throttling, quota và độ dài hàng đợi nếu nhà cung cấp hỗ trợ |
| Vòng đời khóa | Thời điểm tạo, thời điểm bắt đầu dùng, thời điểm ngừng dùng và hạn hết hiệu lực |
| JWKS | Thời điểm cập nhật lần cuối, số khóa công khai đang công bố và sự hiện diện của `kid` đang được tham chiếu |

Không đưa private key, mật khẩu keystore, secret, token hoặc nội dung private JWK vào metrics, log, trace hay nhãn dashboard. Không dùng client ID, subject, token ID hoặc authorization ID làm nhãn metric vì chúng tạo cardinality lớn và có thể làm lộ dữ liệu. Với `kid`, chỉ dùng làm nhãn nếu số lượng khóa được giới hạn và chính sách bảo mật cho phép; thường có thể theo dõi trạng thái khóa bằng sự kiện quản trị hoặc metric tổng hợp.

### 3.2. Theo dõi dịch vụ khóa từ xa

Khi ký token qua KMS/HSM, độ trễ cấp token bao gồm thời gian gọi dịch vụ khóa. Theo dõi riêng latency, timeout và lỗi của nhà cung cấp để phân biệt lỗi mạng, lỗi xác thực, quota, throttling và lỗi thiết bị. Dùng timeout hữu hạn và chính sách retry có giới hạn; retry không kiểm soát có thể khuếch đại sự cố khi KMS/HSM đang quá tải.

Nếu dùng cơ chế cache hoặc nạp khóa vào bộ nhớ, cần quan sát thời điểm làm mới và cách ứng dụng phản ứng khi nguồn khóa tạm thời không sẵn sàng. Không tự động chuyển sang một khóa dự phòng không được phê duyệt. Khóa thay thế phải thuộc quy trình quản lý khóa và được công bố công khai đúng cách.

### 3.3. Quan sát vòng đời và xoay vòng khóa

Xoay vòng khóa cần phối hợp giữa bên ký token và các resource server hoặc client xác minh token. Một quy trình điển hình gồm:

1. Tạo khóa mới trong kho khóa có kiểm soát quyền truy cập.
2. Công bố phần khóa công khai với `kid` mới trên JWKS endpoint.
3. Xác nhận JWKS được phân phối và cache ở các bên tiêu thụ có đủ thời gian cập nhật.
4. Chuyển Authorization Server sang ký bằng khóa mới.
5. Tiếp tục công bố khóa cũ trong khoảng thời gian cần thiết để xác minh các token đã phát hành bằng khóa đó.
6. Chỉ loại bỏ khóa cũ khi các token liên quan đã hết hiệu lực và chính sách vận hành cho phép.

Dashboard nên thể hiện khóa hiện hành, khóa kế tiếp, hạn hiệu lực, lần công bố JWKS gần nhất và kết quả của từng bước xoay vòng. Cảnh báo trước hạn hết hiệu lực đủ lâu để đội vận hành xử lý, thay vì chờ đến khi request ký token bắt đầu thất bại.

Không xóa khóa cũ ngay sau khi đổi khóa ký. Resource server có thể vẫn cần khóa công khai cũ để xác minh access token hoặc ID token chưa hết hạn. Thời gian giữ khóa cần tính đến thời hạn token dài nhất, độ trễ đồng bộ JWKS, cache của bên tiêu thụ và quy định nội bộ.

### 3.4. Health check cho kho khóa

Health check nên xác nhận ứng dụng có thể sử dụng nguồn khóa theo cách nhẹ và an toàn. Với KMS/HSM, có thể dùng API kiểm tra trạng thái hoặc một thao tác kiểm tra được nhà cung cấp khuyến nghị. Tránh thực hiện thao tác ký tốn kém trên mỗi lần gọi health endpoint. Tránh trả chi tiết cấu hình, địa chỉ nội bộ hoặc thông tin bí mật trong response health.

Phân biệt liveness và readiness. Liveness trả lời tiến trình có còn hoạt động hay không; readiness trả lời instance có đủ điều kiện nhận request hay không. Nếu database hoặc kho khóa là phụ thuộc bắt buộc để cấp token, readiness có thể phản ánh trạng thái phụ thuộc đó. Tuy nhiên, không nên đưa lỗi database dùng chung vào liveness của mọi replica: điều này có thể khiến nền tảng liên tục khởi động lại các instance trong lúc database đang gặp sự cố, làm tình hình nghiêm trọng hơn.

## 4. Thu thập metrics bằng Spring Boot Actuator và Micrometer

### 4.1. Bật endpoint quan sát

Với ứng dụng Spring Boot có Actuator và registry Prometheus, có thể dùng cấu hình minh họa sau:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
  metrics:
    tags:
      application: authorization-server
```

Thêm dependency Actuator và registry phù hợp với hệ thống build. Ví dụ với Gradle:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Endpoint `/actuator/metrics` hỗ trợ khám phá metric do ứng dụng cung cấp; `/actuator/prometheus` xuất dữ liệu theo định dạng Prometheus khi registry tương ứng đã được cài đặt. Đường dẫn thực tế có thể thay đổi theo `management.endpoints.web.base-path` và cấu hình triển khai.

Chỉ mở endpoint quản trị trên mạng nội bộ hoặc qua cơ chế xác thực và phân quyền phù hợp. Không công khai `env`, `configprops`, `heapdump`, `logfile` hoặc các endpoint nhạy cảm. Ngay cả `metrics` và `prometheus` cũng có thể tiết lộ cấu trúc hệ thống, tên pool hoặc nhãn nội bộ; cần giới hạn nguồn truy cập. `show-details: when-authorized` không thay thế cấu hình bảo vệ endpoint.

### 4.2. Xác minh metric thực tế

Sau khi khởi chạy ứng dụng trong môi trường phù hợp:

1. Kiểm tra health và trạng thái readiness.
2. Mở danh sách metric hoặc truy vấn metric theo tên để xác nhận DataSource đã được instrument.
3. Xác minh metric pool có thay đổi khi tạo tải đọc/ghi đại diện.
4. Xác nhận registry xuất được histogram hoặc timer cần dùng cho p95/p99.
5. Kiểm tra nhãn chỉ gồm các chiều có cardinality thấp, chẳng hạn application, instance, pool hoặc environment.

Spring Boot và Micrometer có thể tự cung cấp metric JVM, HTTP server, DataSource và pool tùy dependency, phiên bản và cấu hình. Không giả định mọi metric đều xuất hiện chỉ vì Actuator đã được thêm. Nếu thiếu metric, kiểm tra registry, binder, loại DataSource, cấu hình export và phiên bản thư viện.

### 4.3. Bổ sung metric cho hoạt động ký

Metric có sẵn thường không mô tả đầy đủ hoạt động ký của Authorization Server. Có thể đo thời gian và số lỗi ở lớp bao quanh thao tác ký thực tế bằng Micrometer. Ví dụ dưới đây minh họa một helper tổng quát; cần đặt nó tại ranh giới mà ứng dụng gọi signer hoặc KMS/HSM:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.Callable;
import org.springframework.stereotype.Component;

@Component
public class SigningMetrics {
    private final MeterRegistry registry;
    private final Timer signingTimer;
    private final Counter signingFailures;

    public SigningMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.signingTimer = Timer.builder("oauth2.signing.duration")
                .description("Thời gian thực hiện thao tác ký token")
                .publishPercentileHistogram()
                .register(registry);
        this.signingFailures = Counter.builder("oauth2.signing.failures")
                .description("Số thao tác ký token thất bại")
                .register(registry);
    }

    public <T> T record(Callable<T> operation) throws Exception {
        Timer.Sample sample = Timer.start(registry);
        try {
            return operation.call();
        } catch (Exception exception) {
            signingFailures.increment();
            throw exception;
        } finally {
            sample.stop(signingTimer);
        }
    }
}
```

Ví dụ sử dụng:

```java
String signedValue = signingMetrics.record(() -> signer.sign(payload));
```

`signer.sign(payload)` đại diện cho API ký của ứng dụng, không phải một API cố định của Spring Authorization Server. Điều chỉnh kiểu trả về và cách xử lý exception theo signer thực tế. Nếu ứng dụng cần đếm cả lỗi dạng `Error`, hãy cân nhắc chính sách đo lường riêng; không nên bắt mọi lỗi rồi tiếp tục xử lý như thể thao tác ký thành công.

Không thêm nhãn có giá trị thay đổi theo từng request vào timer hoặc counter. Nếu cần phân biệt nhóm thuật toán hoặc nhà cung cấp, chỉ dùng tập nhãn hữu hạn đã được kiểm soát. Không ghi payload, token hoặc nội dung khóa khi đo thời gian.

## 5. Dashboard và cảnh báo

### 5.1. Bố cục dashboard

Dashboard vận hành nên cho thấy quan hệ giữa request và các phụ thuộc:

| Khu vực | Biểu đồ hoặc bảng | Mục đích |
|---|---|---|
| Luồng OAuth/OIDC | Request rate, p95/p99, tỷ lệ lỗi theo endpoint hoặc nhóm thao tác | Xác định thời điểm và phạm vi ảnh hưởng |
| Pool theo instance | Active, idle, max, pending, timeout, acquire latency, usage duration | Phát hiện cạn pool và instance bất thường |
| Database | Kết nối, CPU, I/O, query latency, lock wait, deadlock, dung lượng | Xác định database có phải nút thắt |
| Kho khóa | Signing latency, signing failures, KMS/HSM latency và error rate | Phát hiện lỗi ký hoặc phụ thuộc từ xa |
| Vòng đời khóa | Khóa hiện hành, hạn hiệu lực, thời điểm xoay vòng và cập nhật JWKS | Phòng ngừa sự cố do khóa hết hạn hoặc phân phối thiếu |

Đặt cùng trục thời gian cho request latency, pool pending, database latency và signing latency. Khi các đường biểu diễn tăng cùng lúc, đội vận hành có thể nhanh chóng khoanh vùng thành phần gây ảnh hưởng.

### 5.2. Ví dụ truy vấn Prometheus

Tên metric Prometheus thường được chuyển từ tên Micrometer, nhưng có thể khác theo phiên bản và cấu hình. Các biểu thức sau là mẫu để điều chỉnh sau khi xác minh tên metric trong môi trường thật.

Tỷ lệ sử dụng pool theo từng pool:

```promql
hikaricp_connections_active
  / clamp_min(hikaricp_connections_max, 1)
```

Số lần timeout khi lấy kết nối trong mỗi giây:

```promql
sum by (application, instance) (
  rate(hikaricp_connections_timeout_total[5m])
)
```

Độ trễ p95 của thao tác ký, nếu timer đã xuất histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le, application) (
    rate(oauth2_signing_duration_seconds_bucket[5m])
  )
)
```

Tốc độ phát sinh lỗi ký:

```promql
sum by (application) (
  rate(oauth2_signing_failures_total[5m])
)
```

Hãy kiểm tra đơn vị và tên metric được registry xuất ra trước khi sử dụng các biểu thức. Một số metric là gauge, một số là counter hoặc histogram; áp dụng `rate()` sai loại metric sẽ tạo kết quả sai.

### 5.3. Thiết kế cảnh báo

Một cảnh báo pool có ý nghĩa thường kết hợp nhiều tín hiệu: tỷ lệ active/max cao kéo dài, pending lớn hơn không và acquire latency tăng. Cảnh báo timeout có thể phát ngay khi có lỗi, nhưng cần nhóm theo application và instance để xác định phạm vi. Cảnh báo database nên kết hợp độ trễ truy vấn hoặc lock wait với tín hiệu tài nguyên. Cảnh báo kho khóa cần bao gồm lỗi ký, timeout KMS/HSM và hạn khóa sắp tới.

Không dùng một ngưỡng cố định cho mọi môi trường. Hãy lấy baseline từ tải bình thường, giờ cao điểm, chiến dịch tăng tải và các bài thử tải. Đặt thời gian duy trì để tránh cảnh báo do một spike ngắn; với lỗi bảo mật hoặc lỗi ký làm gián đoạn cấp token, có thể cần cảnh báo nhanh hơn. Mỗi alert nên có người nhận, mức độ ưu tiên, dashboard liên quan và bước xử lý đầu tiên.

Ví dụ các điều kiện cần cảnh báo:

- Pool pending liên tục lớn hơn không và p95 thời gian acquire vượt ngân sách đã đặt.
- Số lần connection timeout tăng trong khi request lỗi database tăng.
- Query latency hoặc lock wait tăng kéo dài, đồng thời request cấp/refresh token chậm.
- KMS/HSM timeout, throttling hoặc lỗi ký vượt ngưỡng vận hành.
- Không thể nạp khóa sau triển khai hoặc làm mới cấu hình.
- Khóa hiện hành sắp hết hạn mà chưa có khóa kế tiếp được công bố và xác nhận.
- JWKS không được cập nhật theo tiến độ xoay vòng đã định.

## 6. Quy trình điều tra sự cố

Khi người dùng hoặc hệ thống giám sát báo lỗi cấp token, thực hiện theo trình tự sau để thu hẹp phạm vi:

1. **Xác định ảnh hưởng.** Kiểm tra endpoint hoặc nhóm grant bị ảnh hưởng, tỷ lệ lỗi, p95/p99, thời điểm bắt đầu và số instance gặp lỗi. Không đưa token thật vào báo cáo sự cố.
2. **Kiểm tra pool ở từng instance.** Đối chiếu active, max, idle, pending, acquire latency và timeout. Nếu chỉ một instance bất thường, xem log và trace của instance đó.
3. **Kiểm tra database.** So sánh số kết nối, query latency, lock wait, deadlock, CPU và I/O trong cùng khoảng thời gian. Xác định truy vấn hoặc transaction liên quan.
4. **Kiểm tra kho khóa.** Xem lỗi nạp khóa, signing latency, timeout hoặc throttling của KMS/HSM, trạng thái khóa hiện hành và lần cập nhật JWKS gần nhất.
5. **Đối chiếu trace.** Xác định thời gian bị tiêu tốn ở bước truy vấn, chờ kết nối, gọi dịch vụ khóa hay xử lý trong ứng dụng.
6. **Khôi phục có kiểm soát.** Áp dụng biện pháp phù hợp như giảm tải, khắc phục truy vấn, điều chỉnh transaction hoặc phục hồi dịch vụ khóa theo runbook đã phê duyệt. Ghi lại tác động và xác nhận tỷ lệ lỗi, latency cùng metrics phụ thuộc đã trở về mức bình thường.

### Ví dụ: request refresh token tăng độ trễ

Giả sử p95 của endpoint token tăng từ 150 ms lên 2 giây. Dashboard cho thấy pool active gần bằng max, pending tăng; database có lock wait cao, còn signing latency vẫn ổn định. Dấu hiệu này hướng điều tra vào transaction và truy vấn lưu authorization. Kiểm tra trace để xác định thao tác giữ kết nối lâu, sau đó xem execution plan và lock liên quan. Tăng pool ngay có thể làm database chịu thêm kết nối trong lúc lock chưa được giải quyết.

### Ví dụ: lỗi ký token sau khi triển khai

Giả sử database và pool vẫn bình thường nhưng tỷ lệ lỗi cấp token tăng ngay sau khi triển khai. Signing failures tăng, đồng thời log ứng dụng ghi nhận không tìm thấy khóa tương ứng. Kiểm tra cấu hình nguồn khóa, quyền truy cập secret manager/KMS, `kid` đang được chọn và nội dung JWKS đã công bố. Nếu thay khóa, xác nhận các resource server có thể lấy khóa công khai mới và khóa cũ vẫn được giữ trong thời gian cần thiết.

## 7. Kiểm chứng trước khi đưa vào vận hành

Hãy kiểm tra dashboard và cảnh báo bằng tải đại diện, đồng thời mô phỏng một số tình huống có kiểm soát trong môi trường thử nghiệm:

- Tăng số request cấp token và refresh token để quan sát pool active, pending và query latency.
- Làm chậm một truy vấn thử nghiệm hoặc tạo lock có kiểm soát để xác minh trace và cảnh báo database.
- Giới hạn pool trong môi trường thử nghiệm để xác minh timeout và runbook nhận diện đúng nguyên nhân.
- Mô phỏng KMS/HSM chậm, timeout hoặc từ chối request để xác minh signing metrics và hành vi lỗi.
- Thực hiện quy trình xoay vòng khóa đầy đủ, kiểm tra JWKS và xác minh token được ký bằng cả khóa cũ lẫn khóa mới trong khoảng chuyển tiếp.
- Khởi động lại hoặc triển khai rolling để xác minh tổng số kết nối không vượt giới hạn database.

Không gây tải hoặc cố tình làm hỏng database/KMS/HSM production để kiểm tra cảnh báo. Thử nghiệm phải có giới hạn tải, người chịu trách nhiệm, thời gian thực hiện và cách khôi phục rõ ràng.

## 8. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ theo dõi CPU database | Bỏ sót lock, query chậm và cạn pool | Kết hợp metric ứng dụng, pool và database |
| Tăng `maximum-pool-size` mỗi khi pending tăng | Có thể làm database quá tải hơn | Xác định thời gian giữ kết nối, query latency và giới hạn tổng kết nối |
| Chỉ xem trung bình latency | Bỏ sót request chậm ở p95/p99 | Theo dõi histogram và phân vị |
| Giữ transaction trong lúc gọi dịch vụ từ xa | Chiếm kết nối lâu, tăng nguy cơ cạn pool | Rút ngắn transaction và thiết kế ranh giới thao tác rõ ràng |
| Chỉ kiểm tra khóa lúc khởi động | Không phát hiện lỗi khi làm mới khóa hoặc gọi KMS/HSM | Theo dõi nạp khóa, ký token và vòng đời khóa liên tục |
| Xóa khóa cũ ngay khi xoay vòng | Token còn hiệu lực có thể không xác minh được | Giữ khóa công khai cũ theo thời hạn token và chính sách cache |
| Gắn token hoặc client ID vào nhãn metric | Cardinality tăng và rò rỉ dữ liệu | Dùng nhãn có tập giá trị nhỏ, đã được kiểm soát |
| Công khai endpoint quản trị | Lộ thông tin vận hành và cấu hình | Giới hạn mạng, xác thực và quyền truy cập |

## Kết luận

Theo dõi tải database, pool kết nối và kho khóa giúp đội vận hành nhìn thấy các phụ thuộc trực tiếp của luồng cấp token. Cần đo đồng thời thời gian request, trạng thái pool, hiệu năng truy vấn và hoạt động ký; sau đó đối chiếu chúng trên cùng trục thời gian. Cấu hình pool phải dựa trên tổng số replica và giới hạn database, còn quy trình xoay vòng khóa phải theo dõi cả khóa ký lẫn khả năng phân phối khóa công khai. Khi metrics, logs, traces và runbook được nối với nhau, việc phát hiện và xử lý sự cố sẽ nhanh và có căn cứ hơn.
