# Truyền cấu hình tại thời điểm triển khai hoặc chạy ứng dụng

Một ứng dụng thường được triển khai ở nhiều môi trường như development, test, staging và production. Mã nguồn và artifact có thể giống nhau, nhưng địa chỉ dịch vụ, thông tin kết nối, giới hạn tài nguyên, chế độ hoạt động và thông tin xác thực sẽ khác nhau. Nếu đóng cứng các giá trị này vào mã nguồn hoặc tạo một bản build riêng cho từng môi trường, nhóm sẽ khó bảo đảm rằng bản đã kiểm thử chính là bản được đưa lên production.

Cách tổ chức phù hợp là tách cấu hình khỏi artifact và cấp cấu hình khi triển khai hoặc khi ứng dụng khởi động. Artifact được build từ một commit đã xác định, sau đó được promote qua các môi trường. Mỗi môi trường cung cấp bộ cấu hình tương ứng thông qua biến môi trường, tệp cấu hình được mount, hệ thống quản lý cấu hình hoặc secret manager. Ứng dụng đọc, xác thực và sử dụng cấu hình trong vòng đời chạy của nó.

Bài học này giải thích cách externalize configuration, chọn kênh truyền cấu hình, xác định thứ tự ưu tiên, quản lý secret, kiểm tra cấu hình trước khi phục vụ yêu cầu, xử lý thay đổi trong lúc chạy và truy vết cấu hình gắn với từng lần triển khai. Mục tiêu là giữ artifact nhất quán, giảm lỗi do cấu hình và bảo đảm mỗi môi trường chỉ nhận những giá trị mà nó được phép sử dụng.

## 1. Vì sao cấu hình cần được cấp lúc triển khai hoặc chạy ứng dụng?

Cấu hình là các giá trị quyết định cách ứng dụng hoạt động trong một môi trường cụ thể. Ví dụ:

- Địa chỉ API hoặc dịch vụ phụ thuộc.
- Host, port, database name và connection pool.
- Thời gian timeout, số lần retry và giới hạn đồng thời.
- Đường dẫn lưu file hoặc bucket lưu trữ.
- Chế độ logging, mức log và endpoint telemetry.
- Feature flag và các lựa chọn hành vi.
- Tên miền, callback URL và cấu hình tích hợp.
- Thông tin xác thực hoặc khóa truy cập cần thiết.

Một số giá trị không nhạy cảm nhưng vẫn thay đổi theo môi trường. Một số khác là bí mật và cần cơ chế bảo vệ riêng. Cả hai nhóm đều không nên bị đóng cứng trong artifact nếu mục tiêu là dùng cùng một đầu ra qua nhiều môi trường.

Có ba vấn đề thường xuất hiện khi cấu hình bị gắn chặt với quá trình build:

1. **Build riêng cho từng môi trường:** staging và production có thể nhận các binary khác nhau dù cùng một thay đổi mã nguồn. Điều này làm giảm độ tin cậy của kiểm thử trước phát hành.
2. **Lộ cấu hình nhạy cảm:** mật khẩu, token hoặc private key có thể đi vào Git, image layer, log build hoặc artifact.
3. **Khó thay đổi và truy vết:** đổi địa chỉ dịch vụ hoặc timeout có thể buộc phải build lại ứng dụng; đồng thời khó biết giá trị nào đã được sử dụng trong một lần triển khai.

Externalized configuration (cấu hình bên ngoài artifact) giải quyết các vấn đề này bằng cách cung cấp giá trị môi trường ở thời điểm triển khai hoặc chạy. Cùng một artifact có thể được dùng ở nhiều môi trường, trong khi mỗi môi trường nhận bộ cấu hình được quản lý riêng.

~~~mermaid
flowchart TD
    A["Commit mã nguồn"] --> B["CI build một artifact"]
    B --> C["Lưu artifact bất biến"]
    C --> D["Deploy cùng artifact lên test"]
    E["Cấu hình test"] --> D
    D --> F["Kiểm tra ứng dụng"]
    F --> G["Promote cùng artifact lên staging"]
    H["Cấu hình staging"] --> G
    G --> I["Phê duyệt phát hành"]
    I --> J["Deploy cùng artifact lên production"]
    K["Cấu hình production"] --> J
    J --> L["Xác minh phiên bản và cấu hình hiệu lực"]
~~~

Điểm cốt lõi là artifact và cấu hình có vòng đời riêng, nhưng phải được liên kết trong bản ghi phát hành. Artifact xác định phần mềm nào được chạy; cấu hình xác định phần mềm đó hoạt động như thế nào trong môi trường đích.

## 2. Phân biệt cấu hình build-time và runtime

Không phải mọi tham số đều có thể thay đổi sau khi build. Cần phân biệt cấu hình được dùng để tạo artifact với cấu hình được ứng dụng đọc khi chạy.

| Loại | Thời điểm áp dụng | Ví dụ | Có thể thay đổi mà không build lại? |
|---|---|---|---|
| Build-time input | Trong quá trình build | Phiên bản compiler, dependency, target architecture, build profile | Thường không; thay đổi có thể làm artifact khác |
| Runtime configuration | Khi deploy hoặc ứng dụng khởi động | URL dịch vụ, database endpoint, timeout, log level | Có, nếu ứng dụng hỗ trợ đọc giá trị mới |
| Secret runtime | Khi deploy hoặc khi cần sử dụng | Password, token, certificate, private key | Có thể luân chuyển mà không build lại, tùy cách ứng dụng nạp |
| Dynamic configuration | Trong lúc ứng dụng đang chạy | Feature flag, giới hạn nghiệp vụ, tỷ lệ rollout | Có, nếu ứng dụng hỗ trợ cập nhật an toàn |

Build-time input có thể ảnh hưởng trực tiếp đến nội dung binary. Ví dụ, thay đổi phiên bản thư viện hoặc target platform thường cần build lại. Runtime configuration thay đổi cách artifact hoạt động mà không cần thay đổi nội dung artifact.

Không nên dùng build profile để đóng gói URL production, mật khẩu hoặc endpoint môi trường vào binary nếu cùng artifact cần đi qua nhiều môi trường. Một profile có thể hữu ích để chọn tính năng build hoặc loại package, nhưng không nên trở thành cơ chế nhân bản artifact chỉ để thay đổi các giá trị vận hành.

Một số frontend static cần biết API base URL khi build nếu ứng dụng nhúng giá trị vào bundle. Trong trường hợp đó, cần cân nhắc cung cấp tệp cấu hình runtime được tải khi ứng dụng khởi động hoặc qua endpoint cấu hình, để tránh phải build lại toàn bộ frontend cho mỗi môi trường. Nếu kiến trúc bắt buộc dùng build-time configuration, cần ghi rõ đó là một biến thể artifact riêng và xác minh từng biến thể.

## 3. Chọn nguồn cung cấp cấu hình

Cấu hình có thể được truyền qua nhiều cơ chế. Không có một cơ chế duy nhất phù hợp với mọi ứng dụng. Cần chọn theo loại dữ liệu, khả năng của nền tảng, yêu cầu bảo mật và cách vận hành.

| Cơ chế | Cách sử dụng | Phù hợp với |
|---|---|---|
| Environment variables | Nền tảng triển khai đặt biến trước khi khởi chạy process | Giá trị đơn giản, cấu hình theo process |
| Mounted configuration file | Mount tệp vào container hoặc máy chạy | Cấu hình có cấu trúc, nhiều trường hoặc certificate |
| ConfigMap / platform configuration store | Nền tảng quản lý cấu hình theo workload hoặc môi trường | Cấu hình không bí mật gắn với deployment |
| Secret manager | Cấp secret qua API, agent, sidecar hoặc file mount | Password, token, key và certificate |
| Configuration service | Ứng dụng truy vấn dịch vụ cấu hình khi khởi động hoặc lúc chạy | Hệ thống nhiều dịch vụ, cần quản lý tập trung hoặc dynamic config |
| Deployment manifest / release values | Pipeline truyền tham số vào nền tảng khi triển khai | Cấu hình gắn với một release hoặc môi trường |

### 3.1. Environment variables

Biến môi trường là cách phổ biến để truyền cấu hình cho process. Nền tảng hoặc script khởi chạy đặt giá trị trước khi chạy ứng dụng. Ứng dụng đọc biến theo tên đã quy ước và chuyển đổi sang kiểu dữ liệu cần thiết.

Ví dụ:

~~~bash
APP_ENV=staging
HTTP_PORT=8080
PAYMENT_API_URL=https://payments.staging.example
DB_POOL_MAX=20
LOG_LEVEL=INFO
~~~

Ví dụ này chỉ minh họa giá trị không nhạy cảm. Không đưa mật khẩu hoặc token thật vào file .env được commit hay vào lệnh có thể bị ghi lại trong shell history hoặc log. Secret nên được cấp từ secret manager hoặc cơ chế bảo mật của nền tảng.

Ưu điểm của environment variables là đơn giản, được nhiều runtime hỗ trợ và không yêu cầu ứng dụng phụ thuộc vào một hệ thống cấu hình cụ thể. Hạn chế là biến môi trường thường chỉ được đọc khi process khởi động, khó biểu diễn cấu trúc phức tạp và có thể bị lộ nếu ứng dụng dump toàn bộ environment vào log hoặc trang chẩn đoán.

Nên quy ước tên biến rõ ràng, có prefix theo ứng dụng, định nghĩa kiểu và giá trị hợp lệ. Ví dụ DB_POOL_MAX phải được chuyển thành số nguyên dương, còn APP_ENV chỉ nhận một trong các môi trường đã được hỗ trợ.

### 3.2. Tệp cấu hình được mount

Tệp cấu hình phù hợp khi có nhiều nhóm giá trị, cấu trúc lồng nhau hoặc định dạng mà ứng dụng đã hỗ trợ như YAML, JSON, TOML hoặc properties.

Ví dụ một tệp cấu hình không chứa secret:

~~~yaml
server:
  port: 8080

database:
  host: db.staging.internal
  name: orders
  pool:
    maxSize: 20
    connectionTimeout: 5s

payment:
  baseUrl: https://payments.staging.example

logging:
  level: INFO
~~~

Nền tảng triển khai có thể mount tệp vào container hoặc máy chạy. Ứng dụng đọc tệp từ một đường dẫn được quy ước, chẳng hạn /etc/orders/application.yml.

Cần kiểm soát quyền đọc tệp, chủ sở hữu, quyền ghi và vòng đời mount. Tệp cấu hình có thể chứa thông tin nhạy cảm nếu không được phân tách; vì vậy nên để secret ở nguồn riêng hoặc mount qua cơ chế secret được bảo vệ.

### 3.3. Config store và ConfigMap

Một nền tảng điều phối có thể cung cấp đối tượng cấu hình riêng, chẳng hạn ConfigMap hoặc cơ chế tương đương. Điều này giúp nhóm thay đổi cấu hình mà không phải đóng gói lại ứng dụng.

Cần lưu ý rằng ConfigMap thường dành cho dữ liệu không bí mật. Việc lưu password hoặc token trong một đối tượng cấu hình thông thường không biến nó thành secret. Hãy sử dụng secret manager hoặc cơ chế secret được nền tảng bảo vệ, có phân quyền và mã hóa phù hợp.

### 3.4. Configuration service

Một dịch vụ cấu hình tập trung có thể cấp cấu hình theo ứng dụng, môi trường, tenant hoặc phiên bản. Cơ chế này hữu ích khi nhiều service cần chia sẻ quy tắc hoặc khi cần cập nhật một số giá trị trong lúc chạy.

Tuy nhiên, ứng dụng sẽ phụ thuộc thêm vào dịch vụ cấu hình. Cần xác định hành vi khi dịch vụ không khả dụng, cách xác thực, cache cục bộ, phiên bản cấu hình và khả năng quay lại bản trước. Không nên để ứng dụng khởi động mà không có cấu hình hợp lệ chỉ vì config service đang lỗi, trừ khi có chính sách fallback an toàn đã được thiết kế.

## 4. Xác định thứ tự ưu tiên khi nạp cấu hình

Một ứng dụng có thể nhận cùng một thuộc tính từ nhiều nguồn: giá trị mặc định, tệp cấu hình, biến môi trường, tham số dòng lệnh hoặc configuration service. Nếu không định nghĩa thứ tự ưu tiên, kết quả có thể khác nhau giữa local, CI và production.

Một thứ tự thường dùng, từ ưu tiên thấp đến cao, là:

1. Giá trị mặc định an toàn trong ứng dụng.
2. Tệp cấu hình mặc định đi kèm artifact.
3. Tệp cấu hình riêng của môi trường được mount.
4. Giá trị từ config store hoặc configuration service theo chính sách.
5. Environment variables được cấp cho process.
6. Tham số dòng lệnh hoặc override tường minh của lần chạy, nếu được cho phép.

Đây chỉ là một mô hình tham khảo. Framework hoặc nền tảng có thể dùng thứ tự khác. Nhóm phải ghi rõ precedence thực tế, tránh trường hợp một nguồn bất ngờ ghi đè nguồn khác.

Ví dụ, ứng dụng có giá trị mặc định HTTP_PORT=8080, nhưng deployment đặt HTTP_PORT=9090. Nếu environment variable có ưu tiên cao hơn file cấu hình, ứng dụng phải lắng nghe ở cổng 9090. Log khởi động có thể ghi nguồn và tên thuộc tính đã chọn, nhưng không được in secret hoặc toàn bộ giá trị nhạy cảm.

### 4.1. Tránh quá nhiều nguồn ghi đè

Càng nhiều nguồn override, việc điều tra càng khó. Hãy giới hạn số nguồn cấu hình và xác định chủ sở hữu của từng nhóm:

- Giá trị mặc định: nhóm phát triển ứng dụng.
- Cấu hình môi trường: nhóm vận hành hoặc nền tảng.
- Secret: nhóm sở hữu secret manager hoặc hệ thống tương ứng.
- Override release: pipeline hoặc người có quyền phê duyệt.

Không nên để một giá trị quan trọng đồng thời tồn tại trong file, biến môi trường, tham số command line và config service mà không có quy tắc rõ. Nếu có override, phải biết giá trị hiệu lực đến từ đâu.

### 4.2. Không dùng fallback nguy hiểm

Fallback hữu ích cho giá trị không nhạy cảm, nhưng có thể tạo rủi ro nếu dùng cho cấu hình bắt buộc. Ví dụ, nếu database password bị thiếu, ứng dụng không nên tự chuyển sang mật khẩu mặc định. Nếu endpoint thanh toán production bị thiếu, không nên tự gọi endpoint development.

Với cấu hình quan trọng, hành vi phù hợp thường là fail fast: từ chối khởi động hoặc từ chối nhận traffic, đồng thời báo rõ thuộc tính nào thiếu mà không tiết lộ giá trị bí mật.

## 5. Quản lý cấu hình riêng cho từng môi trường

Mỗi môi trường cần bộ cấu hình có mục đích rõ ràng. Không nên sao chép tùy tiện toàn bộ cấu hình production xuống test hoặc để môi trường phát triển dùng chung credential với staging.

| Nhóm cấu hình | Development | Test / QA | Staging | Production |
|---|---|---|---|---|
| Service endpoint | Local hoặc mock | Dịch vụ test | Dịch vụ staging | Dịch vụ production |
| Database | Dữ liệu local | Database kiểm thử | Database staging | Database production |
| Secret | Credential local riêng | Secret test | Secret staging | Secret production |
| Logging | DEBUG có kiểm soát | INFO/DEBUG theo nhu cầu | INFO | INFO/WARN theo chính sách |
| Timeout và pool | Nhỏ để phát triển | Gần cấu hình mục tiêu | Gần production | Theo tải và SLO |
| Feature flag | Có thể bật thử | Theo kịch bản test | Theo kế hoạch release | Theo rollout đã phê duyệt |
| Telemetry | Local collector hoặc tắt | Test collector | Staging collector | Hệ thống giám sát production |

Các môi trường nên gần nhau về cấu trúc cấu hình và cách cấp giá trị, nhưng không nhất thiết dùng cùng dữ liệu hoặc cùng quyền. Staging nên phản ánh những đặc tính quan trọng của production để kiểm tra trước phát hành, đồng thời dùng dữ liệu và credential an toàn.

### 5.1. Dùng cùng artifact qua nhiều môi trường

Một luồng phát hành đáng tin cậy thường:

1. Build artifact từ commit đã xác định.
2. Kiểm thử artifact trong môi trường test.
3. Promote chính artifact đó sang staging.
4. Phê duyệt và promote cùng artifact đến production.
5. Ghi lại artifact digest và cấu hình release đã dùng.

Nếu phải build lại chỉ để thay URL hoặc timeout, nhóm có thể vô tình tạo ra binary khác với bản đã kiểm thử. Hãy cung cấp những giá trị đó từ deployment configuration hoặc runtime configuration.

### 5.2. Không để môi trường phát triển làm nguồn cấu hình production

Cấu hình production cần được quản lý tại nơi có quyền truy cập phù hợp. Không nên lấy trực tiếp từ file local của một nhà phát triển, biến môi trường máy cá nhân hoặc secret dùng chung. Các giá trị production phải được cấp từ nguồn chính thức, có audit và có người sở hữu.

## 6. Truyền secret tại thời điểm triển khai hoặc chạy

Secret là dữ liệu xác thực hoặc mã hóa có thể cấp quyền truy cập, chẳng hạn password, token, private key, certificate hoặc connection string chứa credential.

Secret không nên được:

- Commit vào Git.
- Đóng gói trong JAR, WAR, container image hoặc frontend bundle.
- Lưu trong artifact build.
- Ghi vào log, exception message hoặc trang health/debug.
- Đặt trong tham số dòng lệnh có thể bị ghi lại.
- Lưu trong cache hoặc workspace dùng chung mà không có cơ chế bảo vệ.

Một luồng cấp secret tham khảo:

~~~mermaid
sequenceDiagram
    participant P as Pipeline / nền tảng triển khai
    participant I as Identity provider
    participant S as Secret manager
    participant A as Ứng dụng
    P->>I: Yêu cầu danh tính workload
    I-->>P: Token ngắn hạn theo scope
    P->>S: Đọc secret được phép
    S-->>P: Secret hoặc tham chiếu secret
    P->>A: Cấp secret qua file mount hoặc cơ chế an toàn
    A->>A: Khởi tạo client và xác thực
    Note over P,A: Không ghi giá trị secret vào log hoặc artifact
~~~

Cách triển khai có thể khác nhau: nền tảng có thể mount secret thành file, inject environment variable, cấp token cho ứng dụng tự truy vấn secret manager hoặc dùng sidecar/agent. Cần chọn cơ chế giảm khả năng secret bị lộ qua process listing, dump environment, log hoặc filesystem.

### 6.1. Phân quyền theo môi trường

Tách secret development, test, staging và production. Một job chạy test không cần quyền đọc secret production. Một job deploy staging không cần quyền triển khai production.

Ưu tiên credential ngắn hạn hoặc workload identity khi nền tảng hỗ trợ. Trust policy phải giới hạn repository, branch, environment, workflow hoặc danh tính workload được phép nhận credential. Không cấp quyền rộng chỉ vì pipeline cần tự động hóa.

### 6.2. Luân chuyển secret

Secret có thể cần luân chuyển theo lịch, khi nhân sự thay đổi quyền hoặc khi nghi ngờ bị lộ. Ứng dụng cần có cách nhận credential mới mà không phải build lại artifact.

Tùy cách nạp secret, có thể:

- Cấp credential mới và triển khai lại workload.
- Mount phiên bản secret mới rồi restart process.
- Dùng client hỗ trợ refresh token hoặc certificate.
- Dùng secret manager với lease ngắn hạn và tự động gia hạn.

Không nên xóa credential cũ trước khi xác minh ứng dụng đã chuyển sang credential mới, trừ khi cần thu hồi khẩn cấp. Với luân chuyển định kỳ, có thể dùng giai đoạn chấp nhận đồng thời credential cũ và mới để tránh gián đoạn.

## 7. Xác thực cấu hình trước khi ứng dụng phục vụ traffic

Cấu hình sai có thể khiến ứng dụng không khởi động, kết nối nhầm môi trường hoặc hoạt động không an toàn. Vì vậy, ứng dụng cần xác thực cấu hình ngay khi khởi động và trước khi nhận traffic.

Nên kiểm tra:

- Thuộc tính bắt buộc có tồn tại.
- Giá trị có đúng kiểu dữ liệu.
- URL có scheme và host hợp lệ.
- Port nằm trong phạm vi được phép.
- Timeout, pool size và retry limit có giá trị hợp lý.
- Tên môi trường và endpoint có tương thích.
- Feature flag không tạo tổ hợp trạng thái không hợp lệ.
- Secret có thể được đọc và sử dụng, nhưng không bị in ra.
- Cấu hình không vô tình trỏ production sang dịch vụ test hoặc ngược lại.

Ví dụ về schema khái niệm:

~~~yaml
application:
  environment:
    required: true
    allowed:
      - development
      - test
      - staging
      - production

  http:
    port:
      type: integer
      min: 1
      max: 65535

  database:
    url:
      required: true
    poolMax:
      type: integer
      min: 1
      max: 100

  payment:
    baseUrl:
      required: true
    connectTimeout:
      type: duration
      min: 100ms
      max: 30s
~~~

Đây là ví dụ mô tả schema, không phải định dạng cấu hình bắt buộc. Ứng dụng có thể dùng validation của framework, JSON Schema, thư viện cấu hình hoặc logic kiểm tra riêng.

### 7.1. Fail fast với cấu hình bắt buộc

Nếu cấu hình bắt buộc thiếu hoặc không hợp lệ, ứng dụng nên dừng khởi động với thông báo chỉ rõ tên thuộc tính và nguyên nhân, ví dụ PAYMENT_API_URL is required. Không đưa giá trị secret hoặc toàn bộ connection string vào lỗi.

Fail fast tránh việc ứng dụng chạy trong trạng thái nửa hoạt động rồi mới phát sinh lỗi khi có người dùng truy cập. Nền tảng triển khai cần phân biệt container/process đã chạy với ứng dụng đã sẵn sàng phục vụ.

### 7.2. Kiểm tra tương thích giữa các giá trị

Một giá trị riêng lẻ có thể hợp lệ nhưng tổ hợp nhiều giá trị lại sai. Ví dụ:

- APP_ENV=production nhưng database URL trỏ đến host test.
- TLS bị tắt trong khi endpoint yêu cầu TLS.
- Retry quá nhiều kết hợp timeout dài khiến request giữ tài nguyên quá lâu.
- Feature flag bật chức năng nhưng endpoint phụ thuộc chưa được cấu hình.
- Pool size vượt giới hạn kết nối mà database cho phép.

Nên có kiểm tra chéo cho những tổ hợp có rủi ro cao. Với endpoint hoặc secret production, có thể bổ sung allowlist hoặc quy tắc xác minh theo môi trường.

## 8. Cấu hình tĩnh và cấu hình thay đổi trong lúc chạy

Không phải mọi thay đổi cấu hình đều có cùng vòng đời.

- **Startup configuration:** được đọc khi process khởi động, ví dụ port, database pool hoặc TLS key.
- **Reloadable configuration:** ứng dụng có thể nạp lại mà không cần khởi động lại, ví dụ log level hoặc một số timeout.
- **Dynamic configuration:** được cập nhật qua config service hoặc feature flag trong lúc chạy.
- **Deployment configuration:** được nền tảng áp dụng khi tạo hoặc cập nhật workload.

Cần xác định thuộc tính nào thuộc nhóm nào. Nếu ứng dụng chỉ đọc biến môi trường lúc khởi động, thay đổi environment variable trên deployment không tự cập nhật process hiện tại; cần restart hoặc rollout workload.

### 8.1. Reload cấu hình an toàn

Nếu ứng dụng hỗ trợ reload, không nên cập nhật từng trường một cách tùy tiện khiến process ở trạng thái hỗn hợp. Một cách an toàn là:

1. Tải toàn bộ phiên bản cấu hình mới.
2. Parse và validate tất cả trường.
3. Kiểm tra các ràng buộc liên quan.
4. Chỉ khi toàn bộ hợp lệ mới thay thế cấu hình đang dùng.
5. Ghi nhận phiên bản cấu hình mới và kết quả áp dụng.
6. Nếu lỗi, tiếp tục dùng phiên bản cũ và phát cảnh báo.

Với thuộc tính ảnh hưởng đến kết nối, thread pool hoặc tài nguyên, cần xác định cách tạo và đóng tài nguyên cũ. Reload một giá trị không đơn giản chỉ là gán lại biến nếu thành phần phụ thuộc đã được khởi tạo từ trước.

### 8.2. Feature flag không thay thế cấu hình hạ tầng

Feature flag thường điều khiển việc bật/tắt hành vi sản phẩm hoặc rollout tính năng. Nó không nên được dùng để thay thế quản lý endpoint, credential hoặc quyền truy cập. Cần phân biệt cờ tính năng, cấu hình vận hành và secret vì chúng có yêu cầu bảo mật, audit và vòng đời khác nhau.

## 9. Quản lý phiên bản cấu hình và tránh drift

Cấu hình cũng cần được quản lý có phiên bản. Một lần triển khai không chỉ phụ thuộc artifact mà còn phụ thuộc cấu hình đã áp dụng.

Có thể lưu metadata như:

- Artifact version và digest.
- Commit SHA và pipeline run ID.
- Môi trường đích.
- Config bundle version hoặc revision.
- Tham chiếu phiên bản secret, không lưu giá trị secret.
- Thời điểm áp dụng và người hoặc workflow thực hiện.
- Kết quả validation và rollout.

**Configuration drift** xảy ra khi cấu hình thực tế khác với cấu hình đã được khai báo hoặc phê duyệt. Ví dụ, một người sửa timeout trực tiếp trên production, nhưng file cấu hình trong repository vẫn giữ giá trị cũ. Lần triển khai sau có thể ghi đè thay đổi hoặc tạo ra kết quả không dự đoán được.

Để giảm drift:

- Quản lý cấu hình không bí mật bằng version control hoặc hệ thống cấu hình có lịch sử.
- Hạn chế chỉnh sửa trực tiếp trên môi trường chạy.
- Dùng deployment automation để áp dụng cấu hình đã review.
- Định kỳ so sánh trạng thái mong muốn với trạng thái thực tế.
- Ghi audit cho mọi thay đổi và người thực hiện.
- Có quy trình khôi phục cấu hình về phiên bản đã biết.

Không đưa secret vào Git chỉ để có thể version hóa. Repository có thể lưu tên secret, tham chiếu, schema và policy; giá trị bí mật được lưu trong secret manager. Bản ghi phát hành nên tham chiếu phiên bản secret hoặc secret identifier mà không sao chép giá trị.

## 10. Cấu hình và khả năng rollback

Rollback ứng dụng không nhất thiết khôi phục toàn bộ trạng thái hệ thống nếu cấu hình đã thay đổi độc lập. Ví dụ, phiên bản mới cần một endpoint hoặc schema mới; nếu quay lại binary cũ nhưng giữ cấu hình mới, ứng dụng có thể không khởi động hoặc hoạt động sai.

Khi thiết kế rollback, cần xem xét:

- Artifact cũ còn được lưu và xác minh được không?
- Cấu hình cũ có được lưu theo phiên bản không?
- Secret đã luân chuyển có còn tương thích với phiên bản cũ không?
- Schema database có tương thích ngược không?
- Feature flag đã thay đổi có ảnh hưởng đến dữ liệu không?
- Cấu hình mạng hoặc quyền IAM có được thay đổi cùng release không?
- Có thể khôi phục cấu hình và artifact theo một release record thống nhất không?

Một bản phát hành nên ghi lại tổ hợp artifact và cấu hình đã triển khai. Khi rollback, nhóm cần biết có thể khôi phục cả hai hay phải thực hiện forward fix. Với secret đã bị thu hồi vì sự cố bảo mật, không nên khôi phục credential cũ chỉ để làm ứng dụng phiên bản cũ chạy lại; cần cấp credential mới tương thích.

### 10.1. Thay đổi cấu hình có kiểm soát

Cấu hình có thể được thay đổi mà không build lại, nhưng không có nghĩa mọi thay đổi đều an toàn. Thay đổi timeout, pool size, endpoint, quyền hoặc feature flag có thể ảnh hưởng trực tiếp đến hành vi và tải hệ thống.

Với thay đổi có tác động lớn, nên:

- Review và phê duyệt.
- Kiểm tra schema và policy.
- Áp dụng theo rollout hoặc canary nếu phù hợp.
- Theo dõi metric và log sau khi thay đổi.
- Giữ phiên bản trước để khôi phục.
- Ghi lại thời điểm, người thực hiện và kết quả.

## 11. Ví dụ triển khai cấu hình theo môi trường

Ví dụ sau mô tả một manifest khái niệm, không phải cú pháp đầy đủ của Kubernetes hay một nền tảng cụ thể:

~~~yaml
application:
  image: registry.example/orders@sha256:ARTIFACT_DIGEST

  environment:
    APP_ENV: production
    HTTP_PORT: "8080"
    PAYMENT_API_URL: https://payments.internal
    LOG_LEVEL: INFO
    DB_POOL_MAX: "30"

  secretReferences:
    DATABASE_PASSWORD: secret-manager://production/orders/database-password
    PAYMENT_API_TOKEN: secret-manager://production/orders/payment-token

  configuration:
    file: /etc/orders/runtime-config.yml
    revision: orders-production-config-v12
~~~

Manifest chỉ chứa giá trị không bí mật và tham chiếu secret. Nền tảng triển khai hoặc workload identity cấp secret thực tế theo quyền đã cấu hình. Artifact được xác định bằng digest để tránh tag mutable trỏ sang nội dung khác.

Một trình tự triển khai có thể là:

1. Pipeline xác minh artifact và cấu hình dự kiến.
2. Nền tảng tạo workload với environment variables và config file.
3. Secret manager cấp credential theo danh tính workload.
4. Ứng dụng khởi động, nạp cấu hình và xác thực.
5. Readiness check chỉ thành công khi cấu hình bắt buộc đã được áp dụng.
6. Pipeline xác minh artifact digest và config revision đang chạy.
7. Sau rollout, hệ thống theo dõi health, lỗi kết nối và metric quan trọng.

## 12. Điều tra lỗi cấu hình thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ứng dụng không khởi động | Thiếu biến bắt buộc hoặc giá trị sai kiểu | Kiểm tra tên thuộc tính, schema và nguồn cấp |
| Ứng dụng kết nối nhầm môi trường | Giá trị mặc định hoặc precedence ghi đè sai | Xác minh endpoint hiệu lực và nguồn cấu hình |
| Local chạy được nhưng staging lỗi | Khác secret, DNS, quyền hoặc config file mount | So sánh config metadata, kiểm tra quyền và kết nối |
| Thay đổi env var không có tác dụng | Process chỉ đọc cấu hình lúc startup | Kiểm tra cơ chế reload và thực hiện rollout nếu cần |
| Secret mới không được nhận | Credential cache, mount chưa cập nhật hoặc process chưa reload | Kiểm tra version secret, thời điểm mount và vòng đời client |
| Log vô tình chứa secret | Dump environment hoặc exception in connection string | Che/redact log, thu hồi secret bị lộ và sửa logging |
| Production drift sau deploy | Chỉnh sửa trực tiếp ngoài automation | So sánh desired/actual state và kiểm tra audit |
| Rollback ứng dụng nhưng vẫn lỗi | Cấu hình mới không tương thích binary cũ | Khôi phục config revision tương thích hoặc thực hiện forward fix |
| Config service không truy cập được | DNS, network, credential hoặc dịch vụ cấu hình lỗi | Xác minh dependency, retry policy và fallback đã thiết kế |
| Cấu hình hợp lệ riêng lẻ nhưng tổ hợp sai | Thiếu validation chéo | Thêm kiểm tra tương thích trước khi nhận traffic |

Khi điều tra, nên xác định giá trị hiệu lực, nguồn cung cấp và phiên bản cấu hình trước khi thay đổi. Không yêu cầu người vận hành gửi secret vào ticket hoặc log để tái hiện lỗi. Có thể dùng tên biến, secret reference, trạng thái tồn tại và kết quả xác thực mà không tiết lộ giá trị.

## 13. Tình huống mẫu: promote cùng artifact qua ba môi trường

Giả sử nhóm phát triển dịch vụ quản lý đơn hàng và chuẩn bị phát hành một phiên bản mới.

1. CI build artifact từ commit đã hợp nhất, chạy test và lưu artifact với digest.
2. Pipeline triển khai artifact lên test. Nền tảng cấp database endpoint, payment sandbox URL và credential test.
3. Ứng dụng nạp cấu hình, xác thực schema và chạy smoke test cùng integration test.
4. Sau khi đạt, pipeline promote cùng digest lên staging. Staging nhận endpoint và secret riêng, đồng thời dùng cấu hình timeout và pool gần production.
5. Nhóm chạy kiểm thử chấp nhận, kiểm tra luồng thanh toán và xác minh phiên bản artifact/config revision.
6. Khi được phê duyệt, pipeline triển khai cùng digest lên production. Secret manager cấp credential production cho workload theo danh tính và quyền đã được giới hạn.
7. Ứng dụng xác thực cấu hình trước khi readiness thành công. Pipeline ghi lại artifact digest, config revision và kết quả rollout.
8. Nếu phát hiện cấu hình sai sau triển khai, nhóm có thể khôi phục config revision tương thích hoặc rollback cả artifact và cấu hình theo release record.

Nhờ vậy, sự khác biệt giữa các môi trường nằm trong cấu hình được quản lý, còn nội dung artifact đã được kiểm thử vẫn giữ nguyên. Việc thay đổi cấu hình cũng có thể được review, phê duyệt và truy vết độc lập với quá trình build.

## 14. Lộ trình thực hành

Có thể thực hành trên một ứng dụng mẫu theo các bước:

1. **Liệt kê cấu hình:** phân loại giá trị thành build-time, runtime, secret và dynamic configuration.
2. **Tách giá trị môi trường khỏi source:** chuyển URL, port, timeout và log level sang environment variables hoặc config file được cấp khi chạy.
3. **Tách secret:** đưa password và token vào secret manager hoặc cơ chế secret của nền tảng; chỉ truyền tham chiếu trong manifest.
4. **Định nghĩa precedence:** ghi rõ thứ tự giữa default, file, config store, environment và command line.
5. **Thêm validation:** kiểm tra thuộc tính bắt buộc, kiểu, phạm vi và tương thích chéo; thử khởi động với cấu hình sai.
6. **Dùng cùng artifact:** triển khai một digest qua test, staging và production với bộ cấu hình riêng.
7. **Thử thay đổi runtime:** thay một giá trị có thể reload và một giá trị chỉ đọc lúc startup; xác minh hành vi khác nhau.
8. **Kiểm tra secret rotation:** cấp phiên bản credential mới trong môi trường thử nghiệm và xác nhận ứng dụng chuyển đổi an toàn.
9. **Phát hiện drift:** thay đổi cấu hình ngoài automation trong môi trường thử nghiệm và xác minh hệ thống phát hiện khác biệt.
10. **Diễn tập rollback:** khôi phục tổ hợp artifact/config revision đã biết và xác minh ứng dụng hoạt động.
11. **Kiểm tra truy vết:** từ deployment tìm được artifact digest, commit, config revision, secret reference và kết quả validation.

### Tiêu chí hoàn thành

Người học có thể xem bài thực hành hoàn thành khi chứng minh được:

- Giải thích được lý do tách cấu hình khỏi artifact.
- Phân biệt được build-time, runtime, secret và dynamic configuration.
- Chọn được cơ chế truyền cấu hình phù hợp với từng loại dữ liệu.
- Xác định được thứ tự ưu tiên và nguồn của giá trị hiệu lực.
- Quản lý cấu hình riêng cho từng môi trường mà không build lại ứng dụng.
- Cấp secret theo quyền tối thiểu và có thể luân chuyển.
- Xác thực cấu hình trước khi ứng dụng nhận traffic.
- Xử lý được reload, restart và thay đổi cấu hình có kiểm soát.
- Phát hiện configuration drift và truy vết revision.
- Khôi phục được tổ hợp artifact/cấu hình phù hợp khi rollback.

## Kết luận

Truyền cấu hình tại thời điểm triển khai hoặc chạy ứng dụng giúp tách vòng đời của phần mềm khỏi vòng đời của môi trường. Artifact được build và kiểm thử một lần có thể được promote qua nhiều môi trường; mỗi môi trường cung cấp endpoint, giới hạn vận hành và secret riêng thông qua cơ chế được quản lý.

Để cách làm này đáng tin cậy, nhóm cần định nghĩa nguồn cấu hình và thứ tự ưu tiên, xác thực giá trị trước khi phục vụ traffic, bảo vệ secret, quản lý phiên bản và phát hiện drift. Bản ghi phát hành phải liên kết artifact digest với cấu hình đã áp dụng để có thể điều tra, khôi phục và giải thích chính xác ứng dụng đã chạy như thế nào trên môi trường đích.

