# Data retention cho Java Logging: giữ, lưu trữ và xóa log theo chính sách quyền riêng tư

## 1. Vì sao log cần có thời hạn lưu giữ?

Ứng dụng Java thường ghi log để vận hành, khắc phục sự cố, kiểm tra bảo mật và phân tích hành trình nghiệp vụ. Nhưng một dòng log có thể chứa IP, user ID, request ID, URL, tên tài khoản, thông tin thiết bị, dữ liệu lỗi hoặc cả thông tin nhạy cảm vô tình bị đưa vào thông điệp. **Giữ log vô thời hạn không phải mặc định an toàn**: nó tăng bề mặt rò rỉ dữ liệu, chi phí và độ phức tạp khi người có dữ liệu yêu cầu thực hiện quyền của họ.

**Data retention** là toàn bộ chính sách xác định:

- **Thu thập gì:** loại sự kiện và trường nào thực sự cần thiết cho mục đích đã xác định.
- **Giữ bao lâu:** thời hạn theo loại dữ liệu, mục đích, yêu cầu pháp lý/hợp đồng và mức rủi ro.
- **Giữ ở đâu:** stdout/container node, file cục bộ, hệ thống tập trung, object storage, bản sao lưu và bản trích xuất.
- **Ai được truy cập:** phân quyền theo chức năng, ghi audit việc xem/trích xuất và biện pháp bảo vệ.
- **Khi nào chuyển tầng lưu trữ:** hot/warm/cold/archive nếu có ích cho vận hành.
- **Khi nào và bằng cách nào xóa:** xác định hạn, xóa dữ liệu hết hạn, xác minh và theo dõi bằng chứng thực thi.
- **Trường hợp ngoại lệ:** incident, investigation, legal hold hoặc một nghĩa vụ giữ lại hợp lệ.
- **Khi khôi phục bản sao lưu:** làm sao không vô tình khôi phục và sử dụng lại những log đáng lẽ đã bị xóa/hạn chế.

Mục tiêu là một vòng đời nhất quán, có thể kiểm chứng; không chỉ cài maxFileSize của logging framework hay đặt một cron xóa file.

### Sau bài học, bạn có thể

1. Phân biệt log rotation, retention, archival, deletion và legal hold.
2. Thiết kế bảng phân loại log theo mục đích và thời hạn có người phê duyệt.
3. Xác định ranh giới dữ liệu cá nhân trong event/MDC/exception/URL.
4. Tính thời điểm hết hạn trong Java 17, xử lý UTC, ranh giới thời gian và ngoại lệ hold.
5. Áp chính sách tại Logback/FileAppender, container và backend tập trung đúng giới hạn của từng công cụ.
6. Kiểm tra xóa ở index, file, object storage, replica, snapshot và backup.
7. Giám sát lượng dữ liệu hết hạn, lỗi xóa, chi phí, các bản sao còn lại và sai lệch chính sách.

**Không có một con số 7/30/90/365 ngày mặc định đúng cho mọi log, mọi công ty và mọi quốc gia.** Các mốc trong ví dụ dưới đây chỉ phục vụ thực hành; thời hạn production phải được xác định từ mục đích sử dụng, yêu cầu hợp lệ và quyết định của bộ phận phụ trách.

## 2. Những khái niệm thường bị nhầm

| Khái niệm | Định nghĩa | Không bảo đảm điều gì |
| --- | --- | --- |
| Log rotation | Chuyển sang file mới theo ngày/kích thước, có thể nén file cũ | Không tự bảo đảm mọi bản sao của log hết hạn đúng ngày |
| Retention period | Khoảng thời gian dữ liệu được phép/cần được giữ theo chính sách | Không tự thực thi nếu chỉ viết trong tài liệu |
| TTL (time-to-live) | Quy tắc hết hạn của record/object/index sau một khoảng thời gian | Có thể xóa bất đồng bộ; không luôn đến đúng mili-giây |
| Hot storage | Nơi dữ liệu mới dễ truy vấn, thường chi phí cao hơn | Không có nghĩa dữ liệu được xóa khi chuyển khỏi hot |
| Archive / cold storage | Lưu lâu hơn hoặc truy cập chậm hơn, có thể phục vụ điều tra | Không đồng nghĩa ẩn danh hay xóa dữ liệu |
| Expiration | Dữ liệu đủ điều kiện để xóa theo chính sách | Chưa chắc đã bị xóa vật lý hoặc xóa hết phiên bản |
| Deletion / purge | Loại bỏ dữ liệu khỏi những vị trí thuộc phạm vi xử lý | Phải xét backup, replica, version và quyền truy cập còn lại |
| Legal hold | Tạm ngăn xóa theo một căn cứ/điều kiện được phê duyệt | Không có nghĩa được giữ mọi dữ liệu vô thời hạn |
| Redaction | Bỏ/mask trường nhạy cảm | Không thay thế retention của những trường còn lại |
| Pseudonymization | Thay định danh trực tiếp bằng định danh giả có thể liên kết trong điều kiện nhất định | Thường vẫn là dữ liệu cá nhân nếu còn khả năng tái liên kết |
| Anonymization | Xử lý khiến cá nhân không còn nhận diện được theo tiêu chuẩn áp dụng | Khó hơn xóa một username; phải xét khả năng liên kết chéo |

**Rotation theo kích thước khác retention theo thời gian.** Ví dụ appender chỉ giữ ba file 20 MB có thể hết sạch log trong vài phút khi tải tăng hoặc giữ log rất lâu khi tải thấp. Nó kiểm soát dung lượng cục bộ, **không phải cam kết giữ đúng số ngày**.

**Chuyển archive không phải xóa.** Nếu một log rời index tìm kiếm sau 14 ngày nhưng vẫn còn ở object storage 2 năm, vòng đời dữ liệu thực tế vẫn kéo dài 2 năm hoặc hơn.

## 3. Quyền riêng tư: dữ liệu cá nhân nằm trong log ở đâu?

Một log nghiệp vụ hoặc vận hành có thể chứa dữ liệu định danh trực tiếp hoặc gián tiếp. Không chỉ username mới cần xem xét.

| Trường hoặc nguồn | Rủi ro | Khuyến nghị |
| --- | --- | --- |
| user_id/customer_id | Có thể liên kết với tài khoản/cá nhân | Chỉ giữ khi cần; gắn policy, phân quyền |
| IP, thiết bị, user-agent | Có thể góp phần nhận dạng/hồ sơ hành vi | Giới hạn mục đích, mức chi tiết và hạn giữ |
| URL, query, HTTP header | Có thể chứa email, token, mã phiên, tham số nhạy cảm | Log path template; lọc query/header qua allowlist |
| Request/response body | Có thể chứa toàn bộ dữ liệu người dùng | Mặc định không log; chỉ ghi trường an toàn cần thiết |
| Exception message / stack trace | Có thể vô tình chứa input và identifier | Dùng error code, redaction, tránh nhúng bí mật |
| MDC/ThreadContext | Dễ tích lũy nhiều trường context | Chỉ các khóa ổn định được duyệt; clear/restore theo scope |
| Session ID/access token/cookie | Có thể bị lạm dụng để chiếm phiên hoặc truy cập | Không ghi nguyên văn |
| Database URL/credentials | Có thể lộ cơ sở hạ tầng hoặc bí mật | Không ghi chuỗi kết nối chứa secret |
| Trace ID/span ID | Dùng để nối sự kiện, có thể liên kết hành vi | Hạn chế quyền và thời gian lưu; không coi trace ID là danh tính |
| Log truy vấn tìm kiếm | Có thể tiết lộ mục đích/hành vi người dùng | Đánh giá có thật sự cần log nội dung truy vấn hay không |

**Dữ liệu ít nhất cần thiết (data minimization)** nên áp dụng *trước khi ghi log*, thay vì giữ mọi payload rồi hy vọng có thể xóa đúng hạn ở backend. Kể cả log được giữ một ngày, việc ghi password hay token nguyên văn thường vẫn không chấp nhận được.

### Ví dụ trước và sau

**Không nên:**

~~~java
// Snippet minh họa: log toàn bộ request có thể lộ dữ liệu.
log.info("Checkout request: {}", request);
~~~

**Nên ưu tiên field đã được duyệt:**

~~~java
// Snippet SLF4J; cần application và logger đã khai báo.
log.info("checkout_result order_id={} status={} duration_ms={}",
        orderId, safeStatus, durationMs);
~~~

Đây là ví dụ code trong ứng dụng có các biến tương ứng, **không phải chương trình độc lập**. orderId có thể vẫn là định danh cần kiểm soát; chỉ ghi nếu mục đích cho phép. safeStatus phải được tạo từ các trạng thái hợp lệ do ứng dụng xác định, không để user tùy ý viết vào metadata tin cậy.

## 4. Retention policy phải bắt đầu bằng mục đích

Hãy xác định loại log trước, sau đó xây chính sách cho từng nhóm. Một bảng minh họa dùng để trao đổi yêu cầu:

| Loại log | Mục đích | Hạn ví dụ | Nơi lưu | Người phê duyệt |
| --- | --- | --- | --- | --- |
| DEBUG/TRACE chi tiết | Chẩn đoán ngắn hạn | 3 ngày | Hot | Owner ứng dụng và bảo mật |
| APPLICATION INFO/WARN | Vận hành, sự cố | 14 ngày | Hot | Owner vận hành |
| SECURITY event | Phát hiện và điều tra sự cố | 90 ngày | Hot + archive có kiểm soát | Bộ phận bảo mật/pháp chế nếu liên quan |
| AUDIT sự kiện được quy định | Truy trách nhiệm/thực hiện nghĩa vụ | 365 ngày | Kho riêng có quyền hạn chế | Owner dữ liệu và tuân thủ |
| Access log của gateway | Theo dõi truy cập, bảo vệ dịch vụ | Theo đánh giá riêng | Backend quan sát | Owner hạ tầng và quyền riêng tư |

**3, 14, 90, 365 ngày ở đây hoàn toàn là giả định để học lập trình.** Không biến bảng này thành một quy định pháp lý. Một tổ chức có thể cần giữ ngắn hơn hoặc dài hơn, hoặc không có căn cứ thu thập một loại dữ liệu ngay từ đầu.

Đối với mỗi hàng policy nên ghi thêm:

- **Policy ID và version:** chẳng hạn retention.application.v3.
- **Owner:** người/chức năng có thẩm quyền thay đổi.
- **Purpose và lawful basis khi áp dụng:** tại sao được thu thập/lưu giữ.
- **Data class:** log nào, chứa field nhạy cảm nào.
- **Thời điểm bắt đầu tính hạn:** event_time, ingestion_time, transaction close hoặc mốc được định nghĩa rõ.
- **Hạn tối đa và quy tắc xóa:** TTL, archive schedule, grace period nếu được phê duyệt.
- **Deletion target:** index, collector spool, file, archive, backup, replica, export.
- **Exception:** legal hold, incident review hoặc quy tắc lưu giữ bắt buộc.
- **Vị trí địa lý và bên xử lý:** dữ liệu được chuyển đến đâu, ai có quyền.
- **Bằng chứng kiểm tra:** metrics, deletion job result, audit trail và lần review policy.

### Luật và quy định: cách diễn giải thận trọng

Nguyên tắc **storage limitation** trong GDPR, Điều 5(1)(e), yêu cầu không giữ dữ liệu dưới dạng cho phép nhận dạng cá nhân lâu hơn mức cần thiết cho mục đích xử lý, với những ngoại lệ/điều kiện cụ thể do luật quy định. Điều này **không quy định một TTL log chung bằng 30 hoặc 90 ngày cho mọi ứng dụng**. Quy định và nghĩa vụ khác nhau tùy phạm vi pháp lý, loại dữ liệu, hợp đồng và cơ quan quản lý; khi triển khai phải nhận quyết định từ người phụ trách tuân thủ/pháp lý.

OWASP Logging Cheat Sheet cũng nhấn mạnh log, log debug tạm, bản sao và backup không nên bị hủy trước thời hạn bắt buộc và không nên bị giữ vượt thời hạn cho phép. Hai mục tiêu **giữ đủ khi cần** và **xóa đúng khi hết hạn** cần đi cùng nhau.

## 5. Vòng đời dữ liệu: một log có thể tồn tại ở nhiều nơi

Một event Java thường không chỉ nằm trong một file:

~~~text
Java application
    |
    +--> ConsoleAppender / JUL ConsoleHandler
    |          |
    |          v
    |      stdout/stderr
    |          |
    |          v
    |      runtime/node log files --------------+
    |                                           |
    +--> (optional) local rolling file --------+
                                                |
                                                v
                                          Collector / Agent
                                                |
                                                +--> local spool / retry queue
                                                |
                                                v
                                          Transport / Broker
                                                |
                                                +--> buffering / replica
                                                |
                                                v
                                       Search index / log store
                                                |
                                                +--> snapshots
                                                +--> cold archive
                                                +--> object versions
                                                +--> backup / restore copy
                                                +--> analyst export
~~~

**Hạn retention phải được thực thi ở tất cả vị trí trong phạm vi xử lý**, không chỉ tại Search Index. Đặt index lifecycle 14 ngày trong khi object storage lưu vô thời hạn là một retention policy **không đầy đủ**.

### Từng tầng thường giữ dữ liệu ra sao?

| Tầng | Dữ liệu có thể còn sau khi xóa ở tầng khác? | Điều cần kiểm chứng |
| --- | --- | --- |
| Logger/async appender | Queue chứa event chưa gửi | Thời gian sống queue, flush/shutdown, xử lý khi đầy |
| File do Logback/Log4j 2 tạo | File active + archive nén | Rotation theo ngày/kích thước, max history, dọn file cũ |
| Docker runtime | File log local theo driver | Driver, dung lượng, retention node, container deletion |
| Kubernetes node | Container log + phần đã rotate | Kubelet settings, Pod eviction, node lifecycle |
| Collector | Disk buffer/spool/retry | Hạn tối đa, lỗi gửi, dead-letter queue |
| Message broker | Topic phân vùng, replay | Topic retention và bản sao |
| Search backend | Primary/replica/index | Delete index, TTL, compaction, snapshots |
| Object storage | Objects, versions, replicas | Lifecycle/current và noncurrent versions, locks/holds |
| Backup và snapshot | Bản sao lưu thời điểm trước đó | Lịch giữ backup, restore controls, purge sau hạn |
| CSV/JSON export và support ticket | Bản trích xuất ngoài pipeline | Inventory, quyền truy cập, TTL của export |
| Monitoring/alert body | Nội dung event có thể bị sao chép | Đặc biệt chú ý thông tin cá nhân trong notification |

Đối với một hệ thống nhiều cloud region hoặc nhiều đối tác xử lý, phải xác định ai có trách nhiệm xóa bản sao và bằng chứng nào chứng tỏ xóa đã hoàn thành. Không nên trả lời “đã xóa” nếu mới ẩn event khỏi giao diện truy vấn.

## 6. Retention vs rotation trong Logback

Với Java dùng SLF4J + Logback, một file appender thường được cấu hình bằng RollingFileAppender và RollingPolicy. Ví dụ:

**src/main/resources/logback.xml**

~~~xml
<configuration>
    <appender name="APP"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>
                logs/application.%d{yyyy-MM-dd}.log.gz
            </fileNamePattern>
            <maxHistory>14</maxHistory>
            <totalSizeCap>1GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %-5level %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="APP"/>
    </root>
</configuration>
~~~

Đây là **ví dụ cấu hình Logback**, không phải chương trình Java độc lập. Khi backend và phiên bản Logback phù hợp:

- fileNamePattern có %d{yyyy-MM-dd} thể hiện archive theo khoảng ngày và nén .gz.
- maxHistory=14 giới hạn số **khoảng lưu archive đã rollover** theo chính sách Logback; không nên hiểu là xóa từng LogRecord đúng 14×24 giờ sau lúc phát.
- totalSizeCap=1GB áp giới hạn tổng kích thước lịch sử archive phù hợp chính sách; quá giới hạn có thể xóa archive **trước** khi đủ 14 ngày. Vì vậy “giữ đúng ít nhất 14 ngày” không được bảo đảm chỉ bằng cặp tham số này.
- cleanHistoryOnStart=true cho phép xử lý dọn history khi appender khởi tạo; còn việc cleanup trong vận hành phụ thuộc sự kiện rollover và cơ chế thực thi của backend.
- logs/application.log là **file active**. Dọn archive không đồng nghĩa file active chứa các event cũ đã được xóa ngay.
- Nếu nhiều ứng dụng/replica cùng ghi một đường dẫn, vấn đề khóa file/rotation có thể xảy ra; không dùng cấu hình này như một giải pháp multi-process logging chung.

### Khi cần cả giới hạn thời gian và kích thước

Một rolling policy theo ngày cộng totalSizeCap giúp tránh archive tích lũy quá lớn, nhưng chính sách “giữ tối thiểu 14 ngày để điều tra” có thể mâu thuẫn với “tối đa 1 GB”. Khi khối lượng log vượt dự kiến, phải chọn: tăng dung lượng, chuyển sang archive phù hợp hoặc giảm log rate. **Không âm thầm giảm retention của loại log bắt buộc** chỉ để tránh đầy disk.

### Log4j 2

Log4j 2 có RollingFileAppender, triggering policies và rollover strategies, có thể dùng delete action/filter theo tuổi file trong cấu hình phù hợp. Tuy nhiên **tuổi file theo filesystem (last modified) khác tuổi của từng event**. Ví dụ việc copy hoặc cập nhật metadata file có thể thay đổi mtime, và file chứa nhiều sự kiện ngày khác nhau.

Hãy đọc tài liệu đúng phiên bản Log4j 2 đang chạy, xác định cơ chế xóa của rollover strategy và kiểm tra file nào bị xóa thực tế. Nếu retention có yêu cầu nghiêm ngặt theo từng record hoặc theo lớp dữ liệu, nên đặt nó tại backend hỗ trợ TTL/index lifecycle chứ không dựa hoàn toàn vào mtime của file.

### File retention không thay thế chính sách tập trung

Nếu service chạy trong Docker/Kubernetes, thường nên ghi console và để collector xử lý; file log cục bộ chỉ là một tầng nữa cần kiểm soát. Đặt maxHistory trong Logback không ảnh hưởng tới log đã được gửi sang OpenSearch, Elasticsearch, Loki, object storage hay SIEM.

## 7. Container runtime và Kubernetes: giới hạn log node không phải toàn bộ retention

Khi Java ghi stdout/stderr, Docker hoặc container runtime thu thập và lưu log cục bộ theo driver. Ví dụ Docker với logging driver local:

~~~bash
docker run --name sample-service \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  image:tag
~~~

Đây là lệnh **minh họa cấu hình runtime**, cần image:tag có thực và quyền chạy Docker; không phải lệnh để thực thi tự động. max-size/max-file kiểm soát dung lượng và số file cục bộ, không có nghĩa log được giữ ba ngày. Docker daemon còn có cấu hình log driver mặc định, nhưng thay đổi cấu hình daemon không tự cập nhật container đã tồn tại.

Với Kubernetes, kubelet quản lý rotation của container logs trên node. Các tham số thường gặp:

~~~yaml
containerLogMaxSize: 10Mi
containerLogMaxFiles: 5
~~~

Đây là **kubelet configuration**, không phải field trong spec của ứng dụng Deployment. Kubelet cung cấp log từ node cho kubectl logs; theo tài liệu Kubernetes, kubectl logs thông thường chỉ đọc nội dung file log mới nhất, và --previous chỉ hỗ trợ trường hợp container instance trước đó còn có log. Khi Pod bị evict hoặc node bị mất, log node có thể không còn.

**Vì vậy:**

1. Dùng node/runtime rotation để giới hạn dung lượng **tạm thời**, không để đĩa node đầy.
2. Dùng collector để chuyển tiếp log quan trọng đến backend tập trung.
3. Đặt **retention theo thời gian và loại dữ liệu** ở backend/archives.
4. Cấu hình vòng đời của spool, dead-letter queue, backups và bản xuất.
5. Kiểm tra cuối cùng xem event thật sự hết hạn và không còn được truy vấn/phục hồi trái chính sách.

Nếu collector bị lỗi liên tục, có thể mất event trước khi tới backend. Giám sát drop rate, queue depth, lỗi gửi và khoảng thời gian có thể buffer được; đây là vấn đề **availability**, khác với thời hạn giữ dữ liệu sau khi đã nhận thành công.

## 8. Chọn thời điểm bắt đầu tính hạn

“Giữ 14 ngày” vẫn mơ hồ nếu không định nghĩa thời điểm bắt đầu. Có ít nhất ba mốc:

- **event_time:** khi sự kiện xảy ra trong ứng dụng.
- **ingest_time:** khi collector/backend thực sự nhận event.
- **archive_time:** khi object/index được tạo ở tầng lưu trữ khác.

Ví dụ event xảy ra ngày 1, collector bị gián đoạn và nhận ngày 10. Nếu policy bắt đầu từ event_time, event có thể đã quá tuổi ngay khi tới backend; nếu từ ingest_time, sẽ được giữ thêm nguyên thời hạn ở backend. Cả hai có ưu và nhược, nhưng phải **được phê duyệt, ghi thành quy tắc và triển khai nhất quán**.

Các trường nên phân biệt rõ trong structured log:

~~~json
{
  "event_time": "2026-11-01T09:00:00Z",
  "ingested_at": "2026-11-10T09:00:00Z",
  "category": "APPLICATION",
  "retention_class": "APP_STANDARD",
  "event_type": "REQUEST_FINISHED"
}
~~~

Chỉ là schema minh họa. retention_class phải được gán từ policy/cấu hình **đáng tin cậy**, không nhận tùy ý từ client, nếu không kẻ tấn công có thể chọn class dài hơn hoặc ngắn hơn để thay đổi lịch xóa.

### UTC và quy tắc ranh giới

- Lưu timestamp với timezone rõ ràng, thường UTC/ISO 8601.
- Với TTL chính xác theo khoảng thời gian, có thể tính expires_at = event_time + Duration.
- **Đủ điều kiện xóa khi expires_at không nằm sau now** (expires_at ≤ now), nếu không có hold/ngoại lệ.
- Phân biệt “14 × 24 giờ” với “14 ngày lịch” theo timezone doanh nghiệp; hai phép tính có thể khác khi có DST.
- Không dùng LocalDateTime không timezone để so sánh timestamp nhiều service/node; tránh suy luận thứ tự từ đồng hồ lệch.
- Clock của hệ thống chạy job cần đáng tin cậy; log “thời gian trong tương lai” phải được xử lý theo policy thay vì tùy ý giữ vô hạn.

Khi dùng index lifecycle theo ngày, việc xóa toàn bộ index có thể phụ thuộc **ngày tạo index**, kích thước/rollover và lịch chạy lifecycle, không chính xác tới từng event. Nếu cần xóa từng record theo event_time, phải thiết kế index partition/TTL hoặc cơ chế xóa theo trường được backend hỗ trợ.

## 9. Java 17 thực hành: tính KEEP, EXPIRE và HOLD một cách có thể kiểm thử

Ví dụ này **không xóa file hay record thật**. Nó là một **retention decision engine tối giản**: nhận log event giả lập, loại log và thời điểm, rồi trả về quyết định theo policy ví dụ. Không phụ thuộc Maven hoặc thư viện ngoài JDK 17.

Các TTL dùng để minh họa là DEBUG = 3 ngày, APPLICATION = 14 ngày, SECURITY = 90 ngày và AUDIT = 365 ngày. Chúng **không phải thời hạn được khuyến nghị cho production hoặc quy định pháp luật**.

**Tệp: LogRetentionDemo.java**

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class LogRetentionDemo {
    enum Category { DEBUG, APPLICATION, SECURITY, AUDIT }

    record LogEntry(
            String id,
            Category category,
            Instant occurredAt,
            boolean legalHold) { }

    record Decision(
            String id,
            Category category,
            String action,
            Instant expiresAt) { }

    private static final Map<Category, Duration> POLICY = Map.of(
            Category.DEBUG, Duration.ofDays(3),
            Category.APPLICATION, Duration.ofDays(14),
            Category.SECURITY, Duration.ofDays(90),
            Category.AUDIT, Duration.ofDays(365));

    private static Decision evaluate(LogEntry entry, Instant now) {
        Duration ttl = POLICY.get(entry.category());
        Instant expiresAt = entry.occurredAt().plus(ttl);

        // Một hold hợp lệ phải được xử lý trước quy tắc hết hạn.
        if (entry.legalHold()) {
            return new Decision(
                    entry.id(), entry.category(), "HOLD", expiresAt);
        }

        if (!expiresAt.isAfter(now)) {
            return new Decision(
                    entry.id(), entry.category(), "EXPIRE", expiresAt);
        }

        return new Decision(
                entry.id(), entry.category(), "KEEP", expiresAt);
    }

    public static void main(String[] args) {
        // Cố định mốc kiểm tra để có output lặp lại chính xác.
        Instant now = Instant.parse("2026-11-10T00:00:00Z");

        List<LogEntry> entries = List.of(
                new LogEntry(
                        "debug-old", Category.DEBUG,
                        Instant.parse("2026-11-01T00:00:00Z"), false),
                new LogEntry(
                        "app-current", Category.APPLICATION,
                        Instant.parse("2026-11-01T00:00:00Z"), false),
                new LogEntry(
                        "security-held", Category.SECURITY,
                        Instant.parse("2026-01-01T00:00:00Z"), true),
                new LogEntry(
                        "audit-boundary", Category.AUDIT,
                        Instant.parse("2025-11-10T00:00:00Z"), false));

        for (LogEntry entry : entries) {
            Decision result = evaluate(entry, now);
            System.out.printf(
                    "%s category=%s action=%s expires=%s%n",
                    result.id(), result.category(),
                    result.action(), result.expiresAt());
        }
    }
}
~~~

**Chạy:**

~~~bash
javac -encoding UTF-8 LogRetentionDemo.java
java LogRetentionDemo
~~~

**Stdout chính xác:**

~~~text
debug-old category=DEBUG action=EXPIRE expires=2026-11-04T00:00:00Z
app-current category=APPLICATION action=KEEP expires=2026-11-15T00:00:00Z
security-held category=SECURITY action=HOLD expires=2026-04-01T00:00:00Z
audit-boundary category=AUDIT action=EXPIRE expires=2026-11-10T00:00:00Z
~~~

### Giải thích kết quả

- debug-old có timestamp 01/11/2026 và TTL 3 ngày, hết hạn 04/11; mốc kiểm tra 10/11 nên EXPIRE.
- app-current có TTL 14 ngày, hết hạn 15/11; tại 10/11 vẫn KEEP.
- security-held đáng lẽ hết hạn 01/04 theo TTL 90 ngày của ví dụ, nhưng cờ legalHold=true nên quyết định là HOLD. Điều này **không có nghĩa hệ thống được phép gắn hold vô thời hạn**; production phải kiểm tra căn cứ, phạm vi, thẩm quyền và lần rà soát.
- audit-boundary có TTL 365 ngày, hết hạn **đúng** mốc now 10/11/2026; so sánh !expiresAt.isAfter(now) cho EXPIRE tại ranh giới bằng nhau.
- Chương trình không tác động filesystem, database hay object storage; nó tách riêng **quyết định retention** khỏi **thực thi deletion**. Đây là ranh giới thiết kế có lợi cho kiểm thử.

### Những điều production cần thêm

Động cơ policy thật thường cần:

- Policy phiên bản hóa và được tải từ nguồn đáng tin; kiểm tra class, TTL hợp lệ, chặn giá trị thiếu.
- Phân loại tự động từ nguồn log tin cậy, không do user tự khai.
- Hold được quản lý trong kho/quy trình riêng, có case ID, phạm vi, người phê duyệt, thời điểm review và cơ chế release.
- Giao thức chạy job: dry-run → xác nhận policy → lập lô → xóa → xác minh → audit.
- Transaction/lock hoặc concurrency control để tránh xóa dữ liệu vừa được đưa vào hold.
- Idempotency để job chạy lại an toàn khi timeout; ghi nhận thất bại riêng.
- Kế hoạch purge ở các bản sao, snapshots và backup.
- Quan sát theo tỷ lệ hết hạn và thời gian trễ của job.
- Chính sách xử lý event trễ và dữ liệu có timestamp sai.

Tuyệt đối **không** biến ví dụ trên thành một cron xóa mọi file có tên trùng category khi chưa quản lý phạm vi, hold, quyền và verification.

## 10. Kiến trúc áp retention theo lớp dữ liệu

Một kiến trúc tham khảo:

~~~text
Java application (data minimization, safe logging)
    |
    +--> Local stdout/file: rotation và dung lượng giới hạn
    |
    v
Collector: queue TTL + retry policy + dropped-event metrics
    |
    v
Central log store
    |
    +--> HOT index / stream (truy vấn nhanh)
    |        |
    |        +--> lifecycle / TTL / index deletion
    |
    +--> ARCHIVE (nếu được yêu cầu)
    |        |
    |        +--> object lifecycle / version cleanup
    |
    +--> snapshots / backups
             |
             +--> backup retention + restore re-apply policy
    |
    v
Retention controller / scheduled process
    |
    +--> policy registry + legal-hold registry
    +--> deletion eligibility / dry-run
    +--> purge + verification
    +--> evidence / alert / exception review
~~~

### Tách retention giữa các loại log

Nếu SECURITY có nghĩa vụ khác APPLICATION, đừng đưa tất cả vào cùng một index rồi xóa index theo TTL ngắn nhất hoặc dài nhất. Có thể phân tách stream/index theo retention_class đã được xác thực. Nếu không thể tách vật lý, backend phải hỗ trợ chính sách ở mức record mà không ảnh hưởng tới dữ liệu cần giữ khác.

Phân tách theo loại không có nghĩa mỗi customer/order được một index: số lượng index lớn có thể làm tăng chi phí, metadata và khó vận hành. Thường nên chia theo loại log, dịch vụ, mốc thời gian và quy mô phù hợp.

### Retention khác hệ thống phân tích dài hạn

Có thể cần giữ thống kê tổng hợp lâu hơn log chi tiết, ví dụ tổng số request thành công theo ngày. Nhưng dữ liệu tổng hợp không tự nhiên trở thành vô danh: nếu tập nhỏ hoặc có dimension quá chi tiết, có thể tái nhận dạng. Cần đánh giá lại mục đích, độ chi tiết và quyền truy cập đối với analytics aggregate.

## 11. Xóa trong object storage: current version khác noncurrent version

Nhiều hệ thống archive log lên S3 hoặc object storage tương đương. Thường có lifecycle rule chuyển tier sau một khoảng thời gian và hết hạn object sau thời gian khác. Nhưng khi **versioning được bật**, “delete object” có thể chỉ thêm delete marker, còn những phiên bản cũ vẫn tồn tại.

Với Amazon S3 versioning-enabled, tài liệu chính thức mô tả:

- Expiration đối với current version có thể tạo **delete marker** và biến version trước thành noncurrent.
- Muốn loại bỏ noncurrent versions cần quy tắc **NoncurrentVersionExpiration** phù hợp.
- Expired object delete markers có thể cần cleanup.
- Object Lock hoặc legal hold có thể ngăn xóa version đang được bảo vệ.
- S3 Lifecycle xử lý bất đồng bộ; không nên hứa xóa vật lý đồng thời trên mọi bản sao đúng một mili-giây khi TTL vừa tới.

Khái niệm này mang tính thiết kế storage, không phụ thuộc trực tiếp vào logger Java. Một pipeline đã xóa bản ghi khỏi search index nhưng để object version trong archive vẫn chưa đáp ứng được yêu cầu purge toàn vòng đời nếu chính sách yêu cầu xóa cả hai.

### Ví dụ mục tiêu lưu trữ (không phải rule triển khai sẵn)

~~~text
retention_class: APP_STANDARD
hot_search_ttl: 14 days
archive: none
backup_max_age: policy-defined
legal_hold: controlled exception
deletion_evidence: required

retention_class: SECURITY_REVIEW
hot_search_ttl: policy-defined
archive_ttl: policy-defined
backup_max_age: policy-defined
legal_hold: controlled exception
deletion_evidence: required
~~~

Đây là **mẫu tài liệu chính sách**, không phải cú pháp cấu hình hợp lệ cho S3/Logback hoặc một backend cụ thể. Hạn thực tế phải được phê duyệt trước. Đừng áp cứng “APP_STANDARD 14 days” lên mọi dự án.

## 12. Legal hold, điều tra và ngoại lệ

Có thể có trường hợp dữ liệu đáng lẽ đến hạn xóa nhưng phải tạm giữ vì một nghĩa vụ hợp lệ, yêu cầu điều tra đã được phê duyệt hoặc tranh chấp. Cần coi đây là **ngoại lệ được quản trị**, không phải lý do để bỏ toàn bộ retention.

Một record hold tối thiểu nên có:

| Trường | Mục đích |
| --- | --- |
| hold_id / case_id | Xác định yêu cầu |
| scope | Đối tượng/sự kiện/khoảng thời gian cần giữ |
| legal_or_policy_basis | Căn cứ và mục đích đã được phê duyệt |
| approved_by | Người/chức năng chịu trách nhiệm |
| created_at | Khi nào bắt đầu |
| review_at | Khi nào phải đánh giá lại |
| released_at | Khi nào kết thúc |
| action_on_release | Đánh giá lại hạn và xóa nếu đã quá hạn |
| audit_history | Ai đã tạo, thay đổi, giải phóng hold |

**Tính thứ tự thao tác rất quan trọng.** Nếu retention job kiểm tra hold ở thời điểm A nhưng một case mới được đưa vào hold ở thời điểm B trước khi job xóa, có thể xảy ra race. Production cần giao thức đồng bộ/transaction hoặc cơ chế lock/concurrency control phù hợp giữa tạo hold và deletion. Không thể chỉ đọc boolean rồi xóa ngay mà khẳng định đã bảo đảm.

Sau khi release hold, hệ thống cần đánh giá lại thời điểm hết hạn ban đầu và xóa những dữ liệu đủ điều kiện theo policy, thay vì mặc nhiên kéo dài thêm toàn bộ TTL trừ khi quy định cho phép.

Bất kỳ cơ chế immutable/WORM storage nào cũng cần cân bằng: dữ liệu phải được bảo vệ khỏi sửa/xóa trái phép, nhưng việc giữ vượt thời hạn được phép cũng có thể gây rủi ro. Cấu hình lock/retention mode cần review với owner bảo mật/pháp lý trước khi triển khai.

## 13. Backups, replicas và bản export: nơi dễ quên nhất

Một sự kiện có thể đã biến mất khỏi dashboard nhưng vẫn tồn tại ở:

- Snapshot của index.
- Object storage bản hiện tại và bản cũ.
- Replica/cross-region replication.
- Backup database, VM hoặc file.
- Disk spool của collector.
- Bản export JSON/CSV của analyst.
- Incident ticket, chat/email thông báo, tệp đính kèm.
- Môi trường staging/test vô tình copy dữ liệu production.

**Inventory dữ liệu** phải mô tả tất cả những nơi này. Nếu không có inventory, hệ thống khó biết đã xóa hết chưa.

### Lập chính sách cho backup

Bản sao lưu thường theo chu kỳ backup retention riêng. Việc xóa trực tiếp từng event bên trong một backup bất biến có thể không khả thi hoặc làm hỏng tính toàn vẹn phục hồi. Trong một số bối cảnh, một giải pháp được phê duyệt có thể là giới hạn thời gian giữ backup, hạn chế truy cập, không dùng backup để phục vụ truy vấn và **áp lại deletion rules ngay sau restore**. Điều này phải phù hợp với yêu cầu áp dụng; không thể mặc định “cứ để trong backup rồi tự hết hạn” là được chấp nhận.

Thiết kế restore cần:

1. Biết snapshot khôi phục có mốc thời gian nào.
2. Tải lại policy/hold hiện hành, không dùng bản policy quá cũ.
3. Đánh dấu dữ liệu đã bị yêu cầu xóa hoặc đã hết hạn.
4. Chặn sử dụng/phát hành lại các event phải purge cho đến khi re-apply xử lý.
5. Xác minh sau restore và lưu bằng chứng mà không sao chép lại PII quá mức.

### Bản export thường có TTL riêng

Một file CSV xuất từ log search có thể chứa dữ liệu cá nhân và nằm ngoài chính sách xóa index. Hệ thống nên có cơ chế export có hạn, download link hết hạn, phân quyền, dấu vết truy cập, cleanup workspace/ticket và hướng dẫn không chuyển tiếp không kiểm soát.

## 14. Request xóa dữ liệu cá nhân và log retention

Trong một số phạm vi pháp lý, người có dữ liệu có thể gửi yêu cầu truy cập/xóa/hạn chế xử lý. Đối với log, việc xử lý đòi hỏi cân bằng giữa quyền của người đó với các căn cứ lưu giữ hợp lệ và nghĩa vụ bảo mật/audit.

Một quy trình phối hợp thường gồm:

1. Nhận yêu cầu qua kênh được duyệt, xác thực người yêu cầu theo quy định.
2. Xác định các hệ thống/log classes có dữ liệu liên quan (không chỉ một index).
3. Kiểm tra căn cứ lưu và ngoại lệ hợp lệ, không tự suy đoán rằng phải xóa ngay mọi log.
4. Chọn phương án phù hợp: xóa record, xóa identifier, redaction, hạn chế truy cập hoặc giữ theo hold đúng căn cứ.
5. Thực thi trong các hệ thống có liên quan, bao gồm export/snapshot/backup theo cơ chế đã được phê duyệt.
6. Xác minh kết quả, xử lý các bản sao và theo dõi SLA/ngoại lệ.
7. Ghi **bằng chứng thao tác** an toàn (policy ID, job ID, counts, status), tránh lặp lại dữ liệu nhạy cảm trong audit của deletion.

Không phải mọi hệ thống logging hỗ trợ tìm/xóa theo một user ID dễ dàng. Vì vậy thiết kế index/schema và mục đích log ngay từ đầu giúp giảm độ khó. Tránh ghi thông tin cá nhân trong dữ liệu không có cách tìm hoặc không có cơ chế quản lý vòng đời.

**Anonymization khác pseudonymization:** bỏ username nhưng giữ IP, trace liên quan, thông tin thiết bị hoặc cấu trúc hiếm có thể vẫn cho phép tái nhận diện. Một token hóa có bảng mapping còn tồn tại không phải tự động là ẩn danh.

## 15. Xóa log: thiết kế một workflow an toàn

Đối với dữ liệu đã đủ điều kiện xóa, tiến trình deletion nên có các bước rõ ràng:

~~~text
Scheduled retention job
    |
    v
Load signed/approved policy version
    |
    v
List candidates by policy scope and age
    |
    v
Check holds / ownership / ingestion lag / exclusions
    |
    v
DRY RUN + estimate count/bytes/time span
    |
    v
Authorized execution: delete / expire / lifecycle
    |
    v
Verify search + archive + versions + replicas
    |
    v
Record safe evidence + alert on mismatch/failure
~~~

### Các bảo vệ cần có

- **Dry-run:** hiển thị số record/object, class, ngày cũ nhất/mới nhất, nhưng không xuất dữ liệu nhạy cảm vào chính log của deletion job.
- **Allowlist target:** chỉ tác động những resource/index/prefix thuộc phạm vi đã duyệt; không dùng wildcard rộng không được kiểm tra.
- **Giới hạn blast radius:** xử lý theo lô, rate limit, có cơ chế pause/cancel trước hành động không thể đảo ngược.
- **Recheck hold:** không dùng snapshot hold đã quá cũ ở lúc thực thi xóa.
- **Idempotency:** chạy lại sau timeout không xóa thêm sai phạm vi.
- **Audit tối thiểu:** ghi policy version, job id, count, kết quả, lỗi và người phê duyệt; không log raw user data.
- **Verification:** kiểm tra lần nữa tại backend/snapshot/backup theo điều kiện thực tế; không kết luận từ một HTTP 200 “delete accepted”.
- **Alert:** job không chạy đúng lịch, backlog ngày hết hạn tăng, quyền xóa bị lỗi, object lock chặn việc xóa.
- **Thay đổi policy:** có review, canary/dry-run trước khi áp cho toàn production.

Ví dụ Java ở mục 9 chỉ thực hiện quyết định KEEP/EXPIRE/HOLD. **Không tự thêm Files.walk(...).delete(...) vào code mẫu này** để áp dụng cho thư mục production: file mtime khác tuổi event, file có thể chứa nhiều record khác TTL, có legal hold và đường dẫn có thể không thuộc phạm vi cho phép.

## 16. Bảo mật của log trong suốt thời gian giữ

Retention càng dài, việc phân quyền và bảo vệ càng quan trọng.

**At rest:** mã hóa khi lưu phù hợp với hạ tầng, quản lý khóa, kiểm soát truy cập và kiểm tra quyền thường xuyên; tách production logs khỏi môi trường test khi có dữ liệu thật.

**In transit:** dùng kênh có xác thực/mã hóa giữa collector và backend khi phù hợp; không gửi log nhạy cảm qua endpoint không kiểm soát.

**Access control:** phân quyền theo vai trò, đội, service hoặc class dữ liệu; không mặc định mọi developer đều xem toàn bộ AUDIT/SECURITY log.

**Access logging:** chính hành vi tìm, đọc, export và thay đổi retention policy phải được theo dõi theo mức cần thiết; các access logs này lại cần một retention policy riêng.

**Integrity:** bảo vệ khỏi sửa/xóa trái phép, bảo đảm có thể phát hiện thao túng; không nhầm immutable storage với “giữ vô hạn”.

**Least privilege for deletion job:** quyền xóa chỉ trên resource cần thiết, không cùng quyền admin rộng toàn hệ thống.

**Khóa mã hóa:** hủy khóa có thể là thành phần của chiến lược cryptographic erasure khi được thiết kế và phê duyệt, nhưng không mặc định mọi bản sao, cache, replica hay snapshot được coi là đã xóa chỉ vì một khóa bị thay. Cần hiểu phạm vi khóa và cơ chế phục hồi.

## 17. Hiệu năng, chi phí và kích thước dữ liệu

Một câu hỏi vận hành hữu ích là: “Mỗi ngày hệ thống tạo bao nhiêu log, đang giữ bao nhiêu và vì sao?”

Có thể ước lượng sơ bộ:

~~~text
Dung lượng hot (chưa nén) xấp xỉ
    số event/giây × bytes/event × 86.400 × số ngày giữ
~~~

Đây chỉ là **ước lượng thô**; còn index overhead, replicas, nén, metadata, hot/warm tiers, spike và tỷ lệ lưu thực tế. Không dùng nó làm sizing cuối cùng.

Ví dụ nếu có 100 event/giây, trung bình 500 bytes/event, lưu 14 ngày, dữ liệu thô khoảng:

~~~text
100 × 500 × 86400 × 14 = 60480000000 bytes
≈ 60.48 GB (decimal), chưa tính replica/index/overhead
~~~

Trong hệ thống thật, cần đo events/s, bytes/s, tỷ lệ log theo level/category, mức nén, ingest lag, tốc độ xóa và phần archive/backup. Chi phí giảm khi bỏ những trường không cần ngay từ call site thường an toàn hơn “giữ hết trong 1 năm rồi mới tính”.

### Sampling không được thay thế retention một cách máy móc

Sampling có thể giảm DEBUG/TRACE phục vụ debug, nhưng không nên loại bỏ mù các security event, audit record hoặc business event phải được giữ đầy đủ. Retention trả lời **giữ bản ghi đã thu thập bao lâu**; sampling trả lời **có thu thập bản ghi hay không**. Hai chính sách khác nhau và phải được đánh giá riêng.

## 18. Kiểm thử chính sách Data retention

### 18.1. Unit test ở mức quyết định

| Tình huống | Kỳ vọng |
| --- | --- |
| Event mới hơn TTL | KEEP |
| Event quá TTL | EXPIRE |
| Event hết hạn đúng ranh giới expires_at == now | EXPIRE |
| Event quá TTL nhưng đang hold hợp lệ | HOLD |
| Hold được release | Tính lại hạn và EXPIRE nếu đủ điều kiện |
| Timestamp trong tương lai hoặc không hợp lệ | Có chính sách xử lý rõ, không giữ vĩnh viễn ngoài ý muốn |
| Policy thiếu category | Fail closed/alert theo thiết kế; không tự chọn TTL tùy ý |
| Tên category do client gửi | Không được làm tăng thời hạn nếu chưa qua phân loại đáng tin |
| Thay phiên bản policy | Có migration, review và QA theo version |
| Event đến trễ | Tuân thủ quy tắc chọn event_time/ingest_time đã duyệt |

Với LogRetentionDemo.java, hãy thay mốc now bằng các thời điểm trước và sau expiresAt để kiểm tra các nhánh. Nếu dùng Clock trong production, có thể inject Clock.fixed vào test, tránh phụ thuộc đồng hồ thực.

### 18.2. Integration test ở backend và archive

1. Nạp tập log giả đã phân loại, có timestamp ở trước/trong/sau giới hạn.
2. Gắn một legal hold được phê duyệt cho một subset.
3. Chạy retention job ở chế độ dry-run, so sánh số lượng candidate và hold.
4. Thực thi trong môi trường test; kiểm tra index và object versions/snapshots tương ứng.
5. Kiểm tra event **chưa hết hạn** vẫn query được, event hết hạn không còn trong phạm vi cần purge.
6. Thử khi backend chỉ trả accepted nhưng deletion bất đồng bộ: job phải tiếp tục xác minh.
7. Thử chạy job trùng lặp, timeout hoặc retry để kiểm tra idempotency.
8. Thử restore backup cũ; xác minh policy/deletion được tái áp trước khi đưa dữ liệu ra phục vụ người dùng.
9. Đánh giá quyền truy cập, báo cáo lỗi và audit không chứa dữ liệu cá nhân thừa.

### 18.3. Các chỉ số cần cảnh báo

| Metric | Giá trị vận hành |
| --- | --- |
| retention_job_last_success_time | Biết job có ngừng chạy không |
| expired_records_pending / expired_bytes_pending | Đo backlog hết hạn |
| deletion_latency | Độ trễ từ lúc đủ điều kiện đến lúc xác minh xóa |
| deletion_failures_total | Phát hiện lỗi quyền, API, storage |
| legal_hold_records | Thống kê đối tượng đang bị tạm giữ |
| unclassified_log_events | Phát hiện log không có policy |
| archive_objects_without_expiration | Phát hiện data “mồ côi” |
| backup_restore_reconciliation_failures | Phát hiện khôi phục vi phạm policy |
| log_volume_by_class | Tìm tăng trưởng bất thường |
| collector_dropped_events | Biết dữ liệu bị mất trước khi được lưu |

Metric chỉ số lượng và trạng thái, **không cần nhúng raw PII hoặc username** làm label metric; cardinality tăng và dữ liệu nhạy cảm có thể tiếp tục tồn tại ngoài retention của logs.

## 19. Các lỗi thường gặp

| Triệu chứng | Sai lầm có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Index chỉ lưu 14 ngày nhưng backup có log 2 năm | Chỉ cấu hình TTL ở search | Kiểm kê và áp lifecycle backup/archive |
| Xóa S3 object nhưng dung lượng vẫn còn | Bucket versioning giữ noncurrent version | Kiểm tra delete marker, noncurrent lifecycle, Object Lock |
| Log file cũ tồn tại dù đã đặt maxHistory | Chưa rollover, file active, cơ chế cleanup chưa chạy | Xác minh rolling policy, fileNamePattern và thời điểm cleanup |
| Log chỉ giữ vài giờ dù policy 14 ngày | Giới hạn kích thước/xoay vòng sớm | Đối chiếu volume, disk quota và min retention |
| PII tồn tại trong error log | Exception hoặc payload không được lọc | Allowlist field, redaction, kiểm tra toàn pipeline |
| Không thể xóa log của một user | Không có định danh/schema hoặc index hỗ trợ tra cứu | Thiết kế data discovery, phân loại và workflow sớm |
| Job xóa nhầm event đang cần điều tra | Hold kiểm tra quá sớm hoặc sai scope | Transaction/concurrency control với hold registry |
| Retention theo event_time khiến log đến trễ biến mất | Late ingestion chưa được xem xét | Ghi rõ mốc bắt đầu retention và xử lý late events |
| Restore backup làm dữ liệu đã xóa xuất hiện lại | Không re-apply policy sau restore | Chặn publish trước reconciliation |
| Backups/exports không có owner | Inventory không đầy đủ | Gắn owner, TTL, quyền và review định kỳ |
| Cấu hình một TTL cho mọi log | Không phân biệt mục đích và nghĩa vụ | Phân nhóm policy, phê duyệt từng loại |
| “Xóa thành công” nhưng backend vẫn có record | Async deletion/replica/snapshot | Thiết kế verification và đối soát eventual consistency |

## 20. Quy trình triển khai retention cho một dịch vụ Java

**Bước 1 – Inventory:** liệt kê logger, appender, file, stdout, backend, index, object storage, replica, backups và exports.

**Bước 2 – Phân loại:** từ từng loại event xác định mục đích, trường nhạy cảm và nguồn tin cậy. Giảm dữ liệu cần thu thập trước khi triển khai TTL.

**Bước 3 – Phê duyệt policy:** owner dữ liệu, bảo mật và pháp lý/tuân thủ khi cần xác định loại log, thời hạn, căn cứ, exceptions, cách xử lý request.

**Bước 4 – Gắn chính sách vào luồng:** logging category hoặc trusted retention_class, index/stream route; tránh client điều khiển retention.

**Bước 5 – Cấu hình từng tầng:** local rotation, collector buffer TTL, index lifecycle, object lifecycle, backup retention và exports.

**Bước 6 – Thiết lập hold và deletion controller:** phân quyền, dry-run, khóa/xử lý concurrency, audit idempotent.

**Bước 7 – Kiểm thử end-to-end:** từ event tới archival và xóa; chú ý versioning, restore và event trễ.

**Bước 8 – Quan sát:** metrics đã nêu, alert job hỏng hoặc có log không được phân loại.

**Bước 9 – Review định kỳ:** thay đổi nhu cầu vận hành, loại dữ liệu, kiến trúc cloud, quy định áp dụng, hợp đồng và tỷ lệ log thực tế.

**Bước 10 – Kiểm tra thay đổi:** mỗi khi thêm appender/collector/index hoặc data export mới, cập nhật inventory và retention policy, không chờ tới lần kiểm toán tiếp theo.

### Checklist triển khai nhanh

- [ ] Đã có owner và mục đích cho mỗi log class.
- [ ] Không log password, token, toàn bộ body hoặc dữ liệu không cần.
- [ ] TTL tính từ một mốc thời gian được định nghĩa rõ.
- [ ] Log rotation cục bộ khác policy dữ liệu tập trung đã được hiểu.
- [ ] Search index và archive có lifecycle hợp lệ.
- [ ] Đã kiểm tra current/noncurrent object versions nếu dùng storage có versioning.
- [ ] Replica, backup, snapshot và export nằm trong inventory.
- [ ] Có cơ chế hold hợp lệ với phạm vi, review, release và audit.
- [ ] Deletion job có dry-run, ít quyền, idempotency, verification và alert.
- [ ] Restore không làm dữ liệu đã purge tái xuất hiện trái policy.
- [ ] Kiểm thử hết hạn đúng ranh giới, late ingestion và policy thay đổi.
- [ ] Đã xác nhận quyền xem/export log và vị trí lưu dữ liệu.

## 21. Bài tập thực hành

### Bài 1: Thay đổi TTL và kiểm tra ranh giới

Chạy LogRetentionDemo.java đúng như hướng dẫn. Thêm một event APPLICATION đúng expiresAt, một event ngay trước ranh giới và một event ngay sau; dự đoán KEEP/EXPIRE. Giải thích vì sao dùng Instant với UTC giúp tránh mơ hồ về timezone.

### Bài 2: Đặt retention cho hệ thống thử nghiệm

Thiết kế bảng policy cho access log, application INFO, DEBUG, SECURITY và AUDIT. Nêu purpose, owner, sensitive fields, nơi lưu, mốc bắt đầu, thời hạn **mang tính giả định**, ngoại lệ và cách xóa. Giải thích tại sao một nhóm dùng 14 ngày và nhóm khác cần riêng, không viện dẫn “công ty nào cũng dùng 90 ngày”.

### Bài 3: Logback rolling files

Trong ứng dụng test có Logback, cấu hình maxHistory và totalSizeCap. Tạo archive qua các mốc ngày phù hợp trong test, kiểm tra file nào còn. Giải thích vì sao maxHistory không phải cơ chế xóa một record ngay đúng TTL, và vì sao totalSizeCap có thể làm retention thực tế ngắn hơn mong đợi.

### Bài 4: Object storage có versioning

Giả lập kiến trúc có một search index TTL ngắn và object archive có versioning. Sau khi xóa current object, hãy giải thích noncurrent versions, delete markers, các policy cần thiết, legal hold và cách kiểm chứng không còn bản sao ngoài phạm vi lưu giữ.

### Bài 5: Khôi phục backup

Một backup cũ chứa log đã được hệ thống production xóa theo yêu cầu hợp lệ. Vẽ quy trình restore, đối chiếu policy/deletion records, chặn truy cập vào dữ liệu đang reconciliation, rồi xác minh kết quả. Đề xuất metric và alert khi bước này thất bại.

### Bài 6: Tình huống legal hold cạnh tranh với retention job

Hai tác vụ chạy đồng thời: job quét event hết hạn và bộ phận có thẩm quyền tạo hold cho một subset. Chỉ ra race giữa lúc chọn candidate và lúc xóa. Đề xuất cơ chế atomic check/lock/transaction cho hệ thống cụ thể và test để đảm bảo không xóa sự kiện đang được giữ hợp lệ.

## 22. Ghi nhớ

**Data retention cho Java Logging là một vòng đời dữ liệu, không phải chỉ cấu hình file logging.** Phải bắt đầu từ mục đích, giảm lượng dữ liệu cá nhân được ghi, phân loại log đáng tin và quyết định thời hạn được phê duyệt. Retention cần được thực thi trên **toàn bộ pipeline**: appender, container/node, collector, index, archive, object versions, backup và export.

Một bản ghi được xem là đủ điều kiện để xóa không có nghĩa mọi bản sao đã bị xóa. Cần quy trình hold hợp lệ, deletion có kiểm soát, xác minh và bằng chứng; đồng thời không xóa trước thời hạn bắt buộc. Với Java 17, có thể kiểm thử logic KEEP/EXPIRE/HOLD bằng Instant và Duration mà không phải tác động dữ liệu thật. Đừng dùng giá trị thời hạn minh họa như quy định pháp lý.

### Tài liệu tham khảo chính thức

- OWASP Logging Cheat Sheet – Data to exclude; Disposal of logs: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- GDPR Regulation (EU) 2016/679, Article 5 – Storage limitation: https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng
- NIST SP 800-92 – Guide to Computer Security Log Management: https://csrc.nist.gov/pubs/sp/800/92/final
- Logback Manual – RollingFileAppender/TimeBasedRollingPolicy: https://logback.qos.ch/manual/appenders.html
- Apache Log4j 2 – RollingFileAppender: https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html
- Kubernetes – Logging Architecture, log rotation: https://kubernetes.io/docs/concepts/cluster-administration/logging/
- Docker – Configure Logging Drivers: https://docs.docker.com/engine/logging/configure/
- Amazon S3 – Lifecycle expiration with versioning: https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html
- Amazon S3 – Object Lock considerations: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html
- Oracle Java 17 – java.time.Instant: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Oracle Java 17 – java.time.Duration: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html
