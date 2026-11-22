# Log retention trong Java Observability: thiết kế chính sách lưu giữ, lưu trữ và xóa log

## 1. Log retention là gì?

**Log retention** là chính sách quyết định **những bản ghi log được giữ trong bao lâu, ở đâu, với mức truy cập nào, và khi nào chúng được lưu trữ lạnh hoặc xóa**. Trong Java observability, nó liên quan đến toàn bộ đường đi của sự kiện: từ `logger.info(...)`, file hoặc stdout, collector, nền tảng tìm kiếm, object storage cho đến snapshot, backup và export.

Log giúp điều tra lỗi, bảo mật, đo hiệu năng và truy vết giao dịch. Nhưng giữ mọi log vô hạn gây tốn tài nguyên, tăng rủi ro lộ dữ liệu cá nhân và khiến việc quản trị hoặc tuân thủ khó hơn. Ngược lại, xóa quá sớm có thể làm mất chứng cứ khi sự cố được phát hiện muộn.

**Mục tiêu của retention** là cân bằng ít nhất năm yếu tố:

1. **Khả năng quan sát và điều tra:** có dữ liệu đủ lâu để truy nguyên lỗi và sự kiện bảo mật.
2. **Hiệu năng truy vấn:** dữ liệu gần đây cần tìm nhanh, dữ liệu cũ có thể truy vấn chậm hơn.
3. **Chi phí:** dung lượng file, index, replica, snapshot, object storage, băng thông và phí truy xuất.
4. **An toàn dữ liệu:** áp dụng quyền đọc, mã hóa, giới hạn PII/secret, kiểm soát xuất dữ liệu.
5. **Yêu cầu nghiệp vụ và pháp lý:** audit, legal hold, lịch sử giao dịch, dữ liệu cá nhân và quy trình xóa.

**Không có một con số ngày giữ log đúng cho mọi hệ thống.** Một debug log thường có giá trị trong thời gian ngắn; security log hoặc audit trail có thể cần lâu hơn. Các con số trong bài là **ví dụ thiết kế**, không phải thời hạn pháp lý bắt buộc.

## 2. Phân biệt retention, rotation, archival, expiration và deletion

Các thuật ngữ này thường bị đánh đồng nhưng có trách nhiệm khác nhau:

| Thuật ngữ | Câu hỏi nó giải quyết | Điều nó không tự bảo đảm |
| --- | --- | --- |
| **Rotation / rollover** | Khi nào ngừng ghi file/index hiện tại và tạo file/index mới? | Không mặc định xóa dữ liệu đã lưu |
| **Retention** | Chính sách giữ dữ liệu bao lâu, theo loại và nguồn nào? | Chính sách viết ra chưa chắc được mọi sink thực thi |
| **Archival / tiering** | Dữ liệu ít truy vấn được chuyển sang tầng lạnh ở đâu? | Chuyển tầng không có nghĩa đã xóa |
| **Expiration / TTL** | Khi nào dữ liệu đủ điều kiện rời một tầng hoặc bị xóa? | “Đủ điều kiện” chưa chắc đã được xóa ngay |
| **Deletion** | Hủy file/index/object hoặc record theo cơ chế nào? | Xóa ở một sink chưa xóa hết replica, backup, export |
| **Legal hold** | Bản ghi nào phải được giữ dù đã tới thời hạn thông thường? | Không thể áp dụng an toàn nếu không có thẩm quyền và chứng cứ |
| **Data minimization** | Có cần tạo/ghi trường dữ liệu này ngay từ đầu không? | Xóa sau vài ngày không sửa được việc đã lộ token |

Ví dụ appender Logback quay file hằng ngày, giữ tối đa 14 kỳ lưu trữ. Nhưng collector vẫn gửi nội dung tới một backend có retention 90 ngày. Xóa file cục bộ sau 14 ngày **không xóa dữ liệu 90 ngày trong backend**. Ngược lại, nếu index của backend bị xóa sau 7 ngày, file ứng dụng 14 ngày vẫn có thể chứa bản ghi chưa còn tìm kiếm được trong backend.

Cần phân biệt **thời gian truy vấn được** với **thời gian dữ liệu còn tồn tại**. Một index đã rời tầng tìm kiếm có thể vẫn nằm trong bản snapshot hoặc bucket archive.

## 3. Vẽ vòng đời log trước khi đặt TTL

```text
Java application
  ├── SLF4J/Logback/Log4j2 → local rolling file
  └── stdout/stderr        → container runtime
                                    │
                                    ▼
                            Collector / Agent
                                    │
                           Buffer / Retry / Queue
                                    │
                   ┌────────────────┴────────────────┐
                   ▼                                 ▼
           Searchable log backend              Archive objects
            (hot → warm → cold)                 (low-cost tier)
                   │                                 │
             Lifecycle delete                 Object expiration
                   │                                 │
                   └─────────► Backups / snapshots ◄┘
                                        │
                                        ▼
                                 Export / download
```

**Mỗi điểm lưu lại dữ liệu đều cần câu trả lời riêng**: ai sở hữu, retention bao lâu, cách xóa, hành vi khi có legal hold, quyền truy cập, mã hóa, giám sát và xác nhận xóa. Đây không chỉ là việc cấu hình `maxHistory` cho Java logger.

Lập một **inventory**:

| Nơi lưu | Dữ liệu gì? | Ai cấu hình retention? |
| --- | --- | --- |
| File rolling của Java app | Application/debug/error log | Nhóm ứng dụng hoặc nền tảng |
| Node/container stdout logs | stdout/stderr của container | Kubernetes/kubelet/container runtime |
| Collector buffer | Event đang chờ gửi, retry, spool | Nhóm observability |
| Search index/data stream | JSON log có index và mapping | Nhóm vận hành logging backend |
| Object storage archive | File nén, JSONL, Parquet hoặc blob | Nhóm data/platform |
| Snapshot/backup | Bản sao phục hồi của index/object | Nhóm backup/DR |
| Export/dashboard cache | CSV, notebook, liên kết tải, cache | Nhóm sản phẩm, bảo mật và người dùng |

Nếu một nguồn chưa được đưa vào inventory, không nên khẳng định “log đã bị xóa hoàn toàn sau 30 ngày”.

## 4. Phân loại log theo mục đích, độ nhạy cảm và thời hạn

Retention tốt bắt đầu ở **loại sự kiện** chứ không phải chỉ ở logger level.

| Loại log | Công dụng | Ví dụ chính sách minh họa |
| --- | --- | --- |
| `DEBUG` / `TRACE` | Chẩn đoán ngắn hạn, lưu lượng lớn | Hot 2 ngày, tổng 7 ngày |
| `APPLICATION` / `ERROR` | Tìm lỗi, khắc phục sự cố | Hot 7 ngày, tổng 30 ngày |
| `HTTP_ACCESS` | Phân tích traffic, response, latency | Hot 7 ngày, tổng 30 ngày |
| `SECURITY_EVENT` | Phát hiện xâm nhập, điều tra | Hot 30 ngày, tổng 90 ngày |
| `AUDIT` | Đối soát hành động quan trọng, nghĩa vụ kiểm toán | Hot 90 ngày, tổng 365 ngày hoặc theo yêu cầu |
| `METRIC` / `TRACE` | Chuỗi đo, vết phân tán | Có retention riêng, không mặc định dùng policy log |

Các mốc **2/7/30/90/365 ngày chỉ để minh họa** cách xây policy; phải điều chỉnh theo hợp đồng, nhu cầu nghiệp vụ, phân loại dữ liệu, chính sách tổ chức và pháp luật áp dụng.

**Không dùng severity làm toàn bộ retention classification.** HTTP 500 access event có thể ở log level INFO; security event đăng nhập thất bại có thể không được phát dưới ERROR. Ngược lại, một ERROR chứa thông tin nhạy cảm không nhất thiết nên giữ lâu hơn mọi INFO.

Một schema gợi ý:

```json
{
  "timestamp": "2026-11-10T03:15:00Z",
  "ingested_at": "2026-11-10T03:15:01Z",
  "kind": "SECURITY_EVENT",
  "event.name": "authorization_denied",
  "service.name": "identity-api",
  "environment": "production",
  "retention.class": "security",
  "schema.version": 1
}
```

**Đừng tin `retention.class` do HTTP client cung cấp.** Route collector/index policy phải dựa trên nguồn đã xác thực hoặc schema được server kiểm soát. Nếu client có thể tự chọn “audit” hoặc “keep_forever”, hắn có thể làm tăng chi phí, tạo kho dữ liệu lâu dài hoặc che dữ liệu vào nhóm quyền khác.

## 5. Chính sách phải ghi rõ mốc bắt đầu tính tuổi

“Giữ 30 ngày” chưa đủ rõ. Tuổi được tính từ **event time**, **ingestion time**, **file modification time**, **index creation**, **rollover time** hay ngày chuyển sang archive?

| Mốc | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Event timestamp | Gắn với thời điểm nghiệp vụ | Client/snapshot có thể ghi timestamp sai; event đến muộn |
| Ingestion timestamp | Nguồn xử lý biết lúc nhận log | Có thể giữ dữ liệu phát sinh cũ thêm một khoảng |
| File modification time | Dễ dùng với rolling file | Copy/restore/append có thể đổi `mtime` |
| Index creation/rollover time | Thuận tiện index lifecycle | Tuổi index không bằng tuổi từng event |
| Archive upload/object creation time | Quản lý lifecycle trên bucket | File có thể chứa nhiều event với tuổi khác nhau |

Ví dụ một sự kiện xảy ra ngày 1/11 nhưng mất mạng và chỉ được ingest ngày 10/11. Với TTL 30 ngày từ **ingest**, backend có thể giữ đến khoảng 10/12. Với TTL từ **event time**, thời gian giữ còn ngắn hơn. Cần định nghĩa rõ, đồng bộ clock, xử lý late-arriving events và các timestamp đến từ nguồn không đáng tin.

**Dùng UTC/`Instant` khi tính tuổi**, không đơn giản trừ chuỗi ngày địa phương. `Duration.ofDays(1)` là 24 giờ; “ngày lịch” trong một timezone có thể khác khi chuyển daylight saving time. Nếu nghiệp vụ yêu cầu hết hạn vào cuối ngày theo múi giờ địa phương, dùng `ZonedDateTime`/`LocalDate` và quy tắc calendar riêng.

**Ranh giới tuổi chính xác:** `age >= TTL` là đủ điều kiện hết hạn trong nhiều chính sách; phép quét và xóa thực tế có thể chạy trễ. Đừng hứa một event bị xóa tại đúng mili giây thứ 30 ngày nếu công cụ dùng background sweeper hoặc index-level deletion.

## 6. Ước tính dung lượng và ngân sách retention

Trước khi chọn hot/warm/cold, đo số sự kiện thật và kích thước encoded:

```text
raw_bytes_per_day
  = events_per_second × avg_bytes_per_event × 86,400

raw_retained_bytes
  ≈ raw_bytes_per_day × retained_days

effective_storage_bytes
  ≈ raw_retained_bytes × indexing_compression_replica_factor
```

**Ví dụ minh họa:** 1.000 events/s với mỗi event trung bình 500 byte:

- `1.000 × 500 = 500.000 B/s`.
- `500.000 × 86.400 = 43.200.000.000 B/ngày` ≈ **43,2 GB/ngày** (GB thập phân).
- Giữ 30 ngày: **1.296 GB ≈ 1,296 TB** dữ liệu raw.
- Nếu tổng hệ số lưu hiệu dụng bằng **2×** trong một thiết kế cụ thể: khoảng **2,592 TB**; chưa tính những bản snapshot, export hoặc replica ngoài giả định hệ số.

Đây là **ước lượng**, không phải cam kết sizing: index overhead, compression, trường bổ sung, replica, số shard, routing metadata, ingest retries, payload phân bố lệch, file nén và phí lưu theo vùng đều ảnh hưởng.

Các câu hỏi phải trả lời khi capacity planning:

1. Tốc độ event trung bình, p95, peak và burst lớn nhất?
2. Bao nhiêu log DEBUG/INFO/WARN/ERROR, access, audit và security?
3. Kích thước event JSON trung bình/p95, có stack trace hoặc nested fields lớn không?
4. Giữ bao lâu ở **hot**, **warm/cold**, và **archive**?
5. Bản sao index, snapshot, cross-region replication và backup chiếm thêm bao nhiêu?
6. Chi phí theo tháng của storage, ingest, query, retrieval, network egress, API và xóa?
7. Khi tốc độ log tăng gấp 3 trong một sự cố, queue, disk và budget còn chịu được không?

**Data minimization là đòn bẩy lớn:** bỏ request/response body không cần thiết thường vừa an toàn hơn vừa giảm chi phí hơn so với ghi đầy đủ rồi nén/lưu lâu. Nếu lấy mẫu debug log, phải nêu rõ sampling có thể làm mất chi tiết và thiên lệch thống kê; security/audit event có yêu cầu khác.

## 7. Hot, warm, cold, frozen và archive

Các tầng lưu không phải là tên gọi bắt buộc của mọi sản phẩm; chúng biểu diễn **đánh đổi giữa tốc độ truy vấn và chi phí**:

| Tầng | Cách sử dụng | Đặc điểm cần cân nhắc |
| --- | --- | --- |
| **Hot** | Dashboard hiện tại, alert, điều tra lỗi đang diễn ra | Truy vấn nhanh, ingest nhiều, chi phí cao |
| **Warm** | Sự cố của vài tuần gần đây | Truy vấn ít hơn, tối ưu phần lưu/index |
| **Cold / frozen** | Điều tra muộn, truy vấn hiếm | Độ trễ tìm kiếm/recovery cao hơn |
| **Archive** | Bản lưu dài hạn, ít truy vấn hoặc lưu theo quy định | Có thể không trực tiếp query được; cần quy trình restore |
| **Deleted** | Hết mục đích và đủ điều kiện xóa | Có thể còn backup/hold/copy theo policy khác |

**Hot-to-cold không tự giảm tổng thời gian giữ.** Một event có thể hết hạn ở hot sau 7 ngày, được chuyển archive, rồi xóa toàn bộ sau 90 ngày. Cần quy trình đủ tin cậy để bảo đảm archive đã được ghi/kiểm trước khi xóa bản hot nếu đó là mục đích.

Thời gian khôi phục từ archive là một phần của **SLO điều tra**: nếu security incident cần dữ liệu 6 tháng trước trong 30 phút, không thể chọn một tầng archive mà việc restore thường mất nhiều ngày mà không thiết kế trước.

## 8. Trong Java: rolling file của Logback khác backend retention

Ví dụ một ứng dụng Java dùng Logback-classic có thể cấu hình rolling file theo **thời gian và kích thước**:

```xml
<configuration>
    <appender name="APPLICATION"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/application.log</file>

        <rollingPolicy
                class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>logs/application.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>100MB</maxFileSize>
            <maxHistory>14</maxHistory>
            <totalSizeCap>10GB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>

        <encoder>
            <pattern>%d{ISO8601} %-5level [%thread] %logger - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="APPLICATION"/>
    </root>
</configuration>
```

Ý nghĩa:

- `application.log` là file đang ghi; archive có tên ngày và chỉ số `%i`.
- `maxFileSize=100MB` kích hoạt thêm rollover khi kích thước file tới ngưỡng; đây **không phải tổng disk quota tuyệt đối**.
- `maxHistory=14` theo mẫu `%d{yyyy-MM-dd}` nghĩa là giữ khoảng **14 kỳ ngày archive**, không phải mọi event tự xóa đúng 14×24 giờ sau khi phát.
- `totalSizeCap=10GB` giúp giới hạn tổng archive theo khả năng thực thi cleanup, nhưng **không nên coi là hard quota của filesystem**. File active, các file ngoài pattern, đĩa dùng chung và thời điểm cleanup cần kiểm chứng riêng.
- `cleanHistoryOnStart=true` cho phép dọn archive khi appender khởi động; thông thường cleanup cũng diễn ra trong rollover.
- Cấu hình **không áp dụng cho log do gateway, Tomcat AccessLogValve hoặc một collector khác lưu**.
- Nếu app chạy trong Kubernetes container và file nằm trong filesystem tạm, pod bị xóa có thể mất file; cần kiểm tra volume và cách ship log.
- Không cho nhiều pod/process cùng ghi vào một đường dẫn file thông thường nếu chưa thiết kế cơ chế đồng bộ, file locking và rotation thích hợp.

Logback rotation là giải pháp quản lý **file cục bộ**. Khi đưa log vào Elasticsearch, Loki, OpenSearch hoặc object storage, phải đặt **retention bên backend** riêng.

**Lưu ý phiên bản:** rolling policy, encoder và cách cleanup có thay đổi giữa các phiên bản Logback. Kiểm tra tài liệu của bản đang triển khai, theo dõi startup status và thử rollover thực tế trước khi đưa vào production.

## 9. Log4j2 và các chiến lược dọn archive

Nếu dùng Log4j2, `RollingFileAppender` và rollover strategy có thể hỗ trợ các policy theo thời gian/kích thước và hành động xóa file archive theo điều kiện. Đây là **trích đoạn ý tưởng** của chiến lược, không phải file cấu hình Log4j2 hoàn chỉnh:

```xml
<DefaultRolloverStrategy max="10">
    <Delete basePath="logs" maxDepth="1">
        <IfFileName glob="app-*.log.gz"/>
        <IfLastModified age="P14D"/>
    </Delete>
</DefaultRolloverStrategy>
```

Ở đây:

- `max="10"` trong rollover strategy liên quan đến cơ chế chỉ số archive theo chiến lược, **không nên diễn giải thành “retention 10 ngày”**.
- `IfLastModified age="P14D"` chọn file cũ theo **modification time**; không phải event timestamp của từng dòng.
- `IfFileName` và `basePath` cần được review kỹ để không xóa nhầm file của service khác.
- Delete action thường chạy trong ngữ cảnh rollover, nên không bảo đảm thời điểm xóa chính xác nếu ứng dụng ít ghi.
- Chỉ áp dụng sau khi đã cấu hình chính xác `RollingFileAppender`, policies, file pattern và cơ chế vận hành của **phiên bản Log4j2 thật**.

Không copy rule xóa vào thư mục chứa nhiều ứng dụng hoặc nhiều tenant mà không thử trên dữ liệu giả. **Một sai lầm trong glob/path có thể mất log không khôi phục được**. Tổ chức thường cần công cụ retention và quyền xóa tập trung thay vì mỗi app tự thao tác vào nhiều thư mục dùng chung.

## 10. Container và Kubernetes: hai vòng đời khác nhau

Trong mô hình phổ biến, ứng dụng Java ghi log ra `stdout/stderr`, container runtime lưu tạm trên node và collector gửi log ra backend.

Kubernetes/kubelet quản lý rotation của container log theo cấu hình như `containerLogMaxSize` và `containerLogMaxFiles`. Theo tài liệu Kubernetes, giá trị mặc định thường được nêu là **10Mi** và **5 file**, nhưng có thể bị cluster admin thay đổi. Đây là **giới hạn log cục bộ trên node**, không phải chính sách lưu 30 hay 90 ngày của backend.

Các hệ quả thực tế:

1. `kubectl logs` thường chỉ đọc file log hiện hành/gần nhất mà kubelet cung cấp; nó **không thay công cụ truy vấn lịch sử cluster-wide**.
2. Khi pod bị xóa, evict hoặc node mất, log cục bộ có thể không còn; phải ship log đến hệ thống tập trung nếu cần lưu lâu.
3. Collector có thể chưa ingest kịp trước khi file bị rotate/delete; cần đo lag và dropped events.
4. Container log retention không áp dụng trực tiếp lên các **file tự ghi vào custom volume** nếu ứng dụng dùng RollingFileAppender trong pod.
5. Việc tăng số file giữ trên node không thay việc cấu hình ILM/TTL ở backend, và có thể làm đầy đĩa node.
6. Nhiều service có chính sách pháp lý khác nhau nên không nên phụ thuộc duy nhất vào cấu hình kubelet chung.

**Chiến lược thực tế:** xác định node spool window đủ đệm khi collector ngừng ngắn hạn; backend có retention class riêng. Cần test collector outage, pod restart, deployment rollout và disk pressure.

## 11. Elasticsearch ILM và lifecycle của search index

Ở nền tảng có **Index Lifecycle Management (ILM)**, data stream/index có thể đi qua các phase như **hot, warm, cold, frozen, delete**. Những hành động có thể gồm rollover, giảm số shard, chuyển tầng, snapshot hoặc xóa index.

Điểm cần hiểu:

- ILM quản lý **index/backing index**; một hành động xóa index thường xóa **toàn bộ các document trong index**, không xét từng event riêng lẻ.
- `min_age` của phase và thời điểm bắt đầu tính tuổi có semantics theo **lifecycle/rollover của index**, không mặc định là `event.timestamp + N ngày`.
- Nếu index chứa event có tuổi rất khác nhau, việc xóa theo tuổi index có thể giữ một số event lâu hơn hoặc ngắn hơn dự kiến theo từng event.
- Policy gán vào index template/data stream cần được kiểm tra cả với backing index mới sau rollover; đừng chỉ cập nhật một index rồi nghĩ mọi index tương lai tự tuân thủ.
- Xóa index ở search backend chưa đảm bảo bản snapshot, archive object hoặc export cũng bị xóa ngay.

Ví dụ thiết kế **mang tính khái niệm**:

```text
logs-application-prod
  hot: 0–7 days
  warm: 7–30 days
  delete after 30 days

logs-security-prod
  hot: 0–30 days
  cold/archive: 30–90 days
  delete/hold handling after 90 days

logs-audit-prod
  separate archive and legal-hold policy
  independent permissions and documented retention
```

Trên các sản phẩm và phiên bản khác nhau, thời điểm chuyển phase có thể không chính xác đến từng ngày, và cú pháp cấu hình cũng khác. **Thiết kế policy ở mức event class trước**, sau đó ánh xạ sang ILM/data stream lifecycle/OpenSearch ISM hoặc các cơ chế của backend được chọn.

### Vấn đề index có nhiều loại retention

Nếu DEBUG cần giữ 7 ngày, AUDIT cần 365 ngày, **không đổ cả hai vào cùng index** rồi mong ILM xử lý riêng từng event. Một index-level delete không thể đồng thời thỏa đúng hai yêu cầu. Hãy route theo `kind` và độ nhạy cảm vào data stream/index phù hợp, hoặc dùng cơ chế xóa theo document có chi phí và semantics được kiểm soát.

## 12. Object storage, archive, snapshots và legal hold

Lưu archive dưới dạng object nén có thể giảm chi phí nhưng phải đặt **bucket/container lifecycle policy** riêng. Khi thiết kế:

- Xác định object key prefix theo `service`, `environment`, `retention.class`, ngày ingest và schema version, không lấy raw user input làm path.
- Tạo object bằng quy trình có kiểm soát, xác minh checksum/count và khả năng đọc/giải nén trước khi loại dữ liệu hot nếu archive phải là bản lưu chính.
- Lifecycle chuyển lớp storage hoặc expire object phải tương thích với thời gian khôi phục và chi phí retrieval.
- Với versioning, **xóa phiên bản hiện tại/đặt delete marker** có thể không xóa mọi phiên bản lịch sử. Phải kiểm tra policy cho noncurrent versions.
- Replication/cross-region backup và snapshot cũng cần retention; không giả định bucket gốc xóa thì bản sao tự biến mất.
- Object Lock/WORM, legal hold hoặc retention lock có thể ngăn xóa trước kỳ hạn. Đây là **một tính chất bảo vệ** nhưng cũng làm thay đổi phương án xử lý yêu cầu xóa dữ liệu cá nhân.
- Mã hóa dữ liệu at rest/in transit cùng phân quyền là cần thiết khi chính sách yêu cầu; archive rẻ nhưng public hoặc dùng khóa chung quá rộng là rủi ro nghiêm trọng.

**Legal hold không phải cờ do client tự gửi.** Chỉ quy trình có thẩm quyền mới được đặt/bỏ hold; phải audit ai làm, lý do, phạm vi dữ liệu và thời điểm. Nếu hold được áp trên tập dữ liệu rộng, cần đánh giá chi phí và quyền riêng tư.

Không sử dụng `rm -rf`, lệnh delete index hay API bulk delete trực tiếp trong ví dụ học tập. Với retention, phép thử mặc định nên là **dry-run** và danh sách “đủ điều kiện” trước, vì thao tác xóa có thể không phục hồi được.

## 13. Java 17 chạy độc lập: mô phỏng retention policy an toàn

Ví dụ này dùng **JDK 17 thuần**, không có dependency ngoài. Mục đích là mô hình hóa cách quyết định:

- **HOT:** còn trong thời gian truy vấn nhanh.
- **ARCHIVE:** đã hết hot window nhưng chưa hết tổng thời hạn.
- **DELETE_ELIGIBLE:** vượt thời hạn tổng và có thể được **xem xét** xóa.
- **HOLD:** bị legal hold hợp lệ nên không được xóa theo lịch bình thường.
- **REVIEW_TIME:** thời điểm ingest ở tương lai so với clock quan sát, cần kiểm tra clock/data thay vì quyết định xóa.

Để tránh lỗi tuổi log, bài minh họa dùng **`ingestedAt`** đã được hệ thống thu thập xác lập, không dùng event timestamp từ client. Policy 2/7, 7/30, 30/90, 90/365 chỉ là **giả định mô phỏng**. Chương trình **không xóa một file, index hoặc object nào**.

Lưu thành file **`LogRetentionPolicyDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class LogRetentionPolicyDemo {
    enum Kind {
        DEBUG, ACCESS, SECURITY, AUDIT
    }

    enum Stage {
        HOT, ARCHIVE, DELETE_ELIGIBLE, HOLD, REVIEW_TIME
    }

    record Policy(Duration hot, Duration total) {
        Policy {
            Objects.requireNonNull(hot);
            Objects.requireNonNull(total);
            if (hot.isNegative() || total.isNegative()
                    || total.isZero() || hot.compareTo(total) > 0) {
                throw new IllegalArgumentException("Invalid retention");
            }
        }
    }

    record Entry(
            String id,
            Kind kind,
            Instant ingestedAt,
            boolean legalHold) {}

    private static final Map<Kind, Policy> POLICIES = Map.of(
            Kind.DEBUG,
            new Policy(Duration.ofDays(2), Duration.ofDays(7)),
            Kind.ACCESS,
            new Policy(Duration.ofDays(7), Duration.ofDays(30)),
            Kind.SECURITY,
            new Policy(Duration.ofDays(30), Duration.ofDays(90)),
            Kind.AUDIT,
            new Policy(Duration.ofDays(90), Duration.ofDays(365)));

    private static Stage decide(Entry entry, Instant now) {
        Objects.requireNonNull(entry);
        Objects.requireNonNull(now);
        if (entry.legalHold()) {
            return Stage.HOLD;
        }
        if (entry.ingestedAt().isAfter(now)) {
            return Stage.REVIEW_TIME;
        }

        Policy policy = POLICIES.get(entry.kind());
        Duration age = Duration.between(entry.ingestedAt(), now);

        if (age.compareTo(policy.total()) >= 0) {
            return Stage.DELETE_ELIGIBLE;
        }
        if (age.compareTo(policy.hot()) >= 0) {
            return Stage.ARCHIVE;
        }
        return Stage.HOT;
    }

    private static Entry entry(
            String id, Kind kind, String ingestedAt, boolean hold) {
        return new Entry(id, kind, Instant.parse(ingestedAt), hold);
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-10T00:00:00Z");

        List<Entry> entries = List.of(
            entry("debug_2d", Kind.DEBUG,
                    "2026-11-08T00:00:00Z", false),
            entry("debug_7d", Kind.DEBUG,
                    "2026-11-03T00:00:00Z", false),
            entry("access_10d", Kind.ACCESS,
                    "2026-10-31T00:00:00Z", false),
            entry("security_1d", Kind.SECURITY,
                    "2026-11-09T00:00:00Z", false),
            entry("audit_hold", Kind.AUDIT,
                    "2025-01-01T00:00:00Z", true),
            entry("audit_old", Kind.AUDIT,
                    "2025-09-01T00:00:00Z", false),
            entry("future_time", Kind.ACCESS,
                    "2026-11-11T00:00:00Z", false));

        List<Stage> expected = List.of(
                Stage.ARCHIVE,
                Stage.DELETE_ELIGIBLE,
                Stage.ARCHIVE,
                Stage.HOT,
                Stage.HOLD,
                Stage.DELETE_ELIGIBLE,
                Stage.REVIEW_TIME);

        for (int i = 0; i < entries.size(); i++) {
            Entry item = entries.get(i);
            Stage actual = decide(item, now);
            if (actual != expected.get(i)) {
                throw new AssertionError("Wrong stage: " + item.id());
            }
            System.out.println(item.id() + " -> " + actual);
        }

        boolean invalidPolicyRejected = false;
        try {
            new Policy(Duration.ofDays(10), Duration.ofDays(3));
        } catch (IllegalArgumentException expectedError) {
            invalidPolicyRejected = true;
        }
        if (!invalidPolicyRejected) {
            throw new AssertionError("Invalid policy accepted");
        }

        System.out.println("invalid_policy -> REJECTED");
        System.out.println("ALL POLICY CHECKS PASSED");
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac --release 17 LogRetentionPolicyDemo.java
java LogRetentionPolicyDemo
```

**Stdout chính xác:**

```text
debug_2d -> ARCHIVE
debug_7d -> DELETE_ELIGIBLE
access_10d -> ARCHIVE
security_1d -> HOT
audit_hold -> HOLD
audit_old -> DELETE_ELIGIBLE
future_time -> REVIEW_TIME
invalid_policy -> REJECTED
ALL POLICY CHECKS PASSED
```

Cách hiểu:

1. `debug_2d` vừa chạm mốc hot 2×24 giờ nên chuyển sang ARCHIVE.
2. `debug_7d` chạm đúng tổng 7 ngày nên vào `DELETE_ELIGIBLE`. **Đủ điều kiện** không đồng nghĩa đã bị xóa.
3. `access_10d` vượt hot 7 ngày nhưng chưa tới tổng 30 ngày.
4. `security_1d` vẫn trong hot window.
5. `audit_hold` đã cũ nhưng bị HOLD; chính sách thông thường không được phép xóa. Ví dụ tin rằng cờ hold đã được thiết lập bởi nguồn có thẩm quyền.
6. `audit_old` quá mốc 365 ngày và không có hold nên là ứng viên xóa.
7. `future_time` có ingestion timestamp sau `now`, cần kiểm tra clock hoặc metadata thay vì xử lý như log 0 ngày tuổi.
8. Policy với hot 10 ngày nhưng tổng 3 ngày bị từ chối ngay khi tạo.

**Giới hạn cố ý:** `LogRetentionPolicyDemo` chỉ là **policy evaluator/dry-run**, không mở file, không xóa dữ liệu, không thay ILM, không quyết định quyền legal hold. Với hệ thống thật, điều kiện xóa còn bao gồm tính toàn vẹn của archive, các quy định lưu giữ, object versioning, audit trail của tác vụ xóa và error handling.

## 14. Từ quyết định policy tới tác vụ xóa an toàn

Một worker dọn log thực tế không nên gọi delete ngay sau khi một phép tính thời gian trả về true. Nên dùng state machine rõ:

```text
INVENTORY
   │
   ▼
CLASSIFY (kind, owner, sensitivity, retention class)
   │
   ▼
EVALUATE AGE (trusted timestamp + policy version)
   │
   ▼
CHECK EXCEPTIONS (legal hold, investigation, required copies)
   │
   ▼
DRY-RUN CANDIDATES + COUNTS + SIZE
   │
   ▼
APPROVE / SCHEDULE / RATE-LIMIT
   │
   ▼
DELETE / EXPIRE by backend-supported mechanism
   │
   ▼
VERIFY DELETION + RECORD AUDIT RESULT
   │
   ▼
RECONCILE COPIES, BACKUPS, EXPORTS & METRICS
```

Đối với dữ liệu đã được phân loại bảo mật/audit cao, có thể cần **hai người phê duyệt** hoặc workflow có quyền tách biệt. Đối với debug log phổ thông, một lifecycle rule đã kiểm thử có thể được áp dụng tự động, nhưng vẫn cần audit việc đổi policy.

**Idempotency** rất quan trọng: worker có thể retry sau timeout. Cần phân biệt “không tồn tại vì đã xóa thành công” và “không tìm thấy do sai index/path/permission”. Các backend khác nhau có semantics deletion khác nhau, vì vậy không áp đặt “exactly-once delete” khi không có bảo đảm.

Khi xảy ra lỗi:

- **Policy không xác định:** quarantine hoặc bỏ qua ứng viên, phát cảnh báo; không fallback xóa bằng mặc định ngắn nhất.
- **Clock sai:** dừng quyết định xóa cho đối tượng có timestamp bất thường.
- **Không xác minh được archive:** đừng xóa bản duy nhất nếu mục tiêu là lưu bản archive bắt buộc.
- **Có legal hold:** chặn xóa và nêu nguyên nhân được kiểm soát; không cho operator thường tự xóa cờ.
- **Thiếu quyền xóa:** ghi lỗi và báo người quản trị; không mở rộng credential tự động.
- **Delete timeout:** đối chiếu trạng thái trước retry, tránh xóa nhầm đối tượng khác sau rollover.
- **Mass deletion bất thường:** giới hạn tối đa số byte/index mỗi đợt và có cảnh báo/phê duyệt.

## 15. Retention, quyền riêng tư, bảo mật và pháp lý

Log có thể chứa dữ liệu cá nhân: địa chỉ IP, request path, email, device ID, user ID, access pattern và audit actor. Vì vậy retention không chỉ là câu chuyện dung lượng.

Các nguyên tắc:

- **Ghi tối thiểu:** không log token/password/cookie, raw request/response body hoặc query nhạy cảm chỉ để “biết đâu cần”.
- **Mục đích rõ:** thời hạn phải phù hợp mục đích debug, vận hành, an ninh hoặc audit; dữ liệu càng nhạy cảm càng cần review.
- **Phân quyền:** chỉ người được phép xem security/audit log; tách quyền search/export, đổi retention và delete.
- **Mã hóa:** at rest/in transit khi yêu cầu, quản lý khóa và log truy cập kho.
- **Retain và delete:** lưu đủ theo nghĩa vụ nhưng không giữ vô hạn; xử lý legal hold và yêu cầu xóa theo quy trình được pháp chế/bảo mật xác nhận.
- **Không dùng một retention chung cho mọi tenant** nếu hợp đồng, địa lý lưu trữ hoặc phân loại dữ liệu khác nhau; phải xác định owner và namespace.
- **Xem xét backup, snapshot và export:** bản copy ra khỏi backend thường cần cùng chính sách hoặc chính sách riêng được ghi nhận.

Không khẳng định một mốc như **30, 90 hay 365 ngày là bắt buộc theo GDPR hoặc pháp luật Việt Nam** cho mọi loại log. Các nghĩa vụ phụ thuộc mục đích, chủ thể dữ liệu, ngành, hợp đồng, khu vực và trường hợp đặc biệt; cần đội pháp chế/bảo mật kiểm tra.

**Xung đột legal hold với data subject deletion:** không tự giải bằng cách xóa toàn bộ hoặc giữ vĩnh viễn. Tạo workflow có căn cứ pháp lý, phạm vi rõ, kiểm toán quyết định và khả năng xử lý từng bản sao.

## 16. Immutable retention và khả năng sửa lỗi

Audit log có thể được lưu trong WORM/Object Lock hoặc hệ thống append-only để chống xóa/sửa trái phép. Nhưng cần biết đánh đổi:

1. **Retention lock** có thể ngăn xóa trước mốc đã định, kể cả khi phát hiện một event chứa secret. Vì vậy **data minimization tại nguồn** càng quan trọng.
2. Không dùng một bucket immutable duy nhất cho cả DEBUG chứa payload, access log và audit log.
3. Khi cần sửa schema hoặc thông tin sai, có thể dùng event **correction/superseding** thay vì sửa record gốc nếu quy định audit yêu cầu bất biến.
4. Việc đổi thời hạn hoặc gỡ legal hold phải có thẩm quyền, lý do và audit, không phải API mở cho ứng dụng.
5. Nếu một secret lộ vào immutable log, phải xử lý token/credential (revoke/rotate), quyền truy cập, phạm vi bản sao và quy trình xử lý theo chính sách; không giả định có thể lập tức xóa vật lý.

**Immutable ≠ always correct.** Không có chữ ký hoặc storage lock nào làm cho một actor ID lấy từ header giả trở nên xác thực. Tính đúng của log bắt đầu ở event nguồn, còn storage lock bảo vệ bản đã ghi.

## 17. Snapshot, backup, bản sao và chu kỳ xóa

Một lỗi phổ biến: dashboard không tìm thấy log vì index TTL đã xóa, rồi tuyên bố “dữ liệu đã được xóa hoàn toàn”. Nhưng log có thể còn trong:

- Snapshot của index hoặc file backup ngày trước.
- Cross-cluster/cross-region replication.
- Object storage versioning và noncurrent versions.
- Collector spool hoặc file ứng dụng chưa rotate.
- Export CSV, notebook, BI report, ticket attachment.
- Cold archive hoặc data warehouse.
- DR restore environment/test environment.
- Cache có TTL khác backend chính.

Định nghĩa **bằng chứng xóa** theo từng lớp:

| Lớp | Câu hỏi kiểm tra |
| --- | --- |
| Hot index | Index/backing index hoặc document hết hạn còn truy vấn được không? |
| Archive | Object tồn tại, bị hold, versioning hoặc noncurrent retention không? |
| Snapshot | Snapshot hết hạn theo policy riêng hay chưa? |
| Source file/node | File rolling/container runtime còn giữ bản sao không? |
| Collector buffer | Event retry/spool tồn tại trong bao lâu? |
| Export | Người dùng có link/file đã tải, expiry/revocation thế nào? |
| Backup restore | Dữ liệu cũ có quay trở lại khi phục hồi không? |

Với hệ thống có backup bất biến, có thể cần policy **hạn chế sử dụng hoặc tái xử lý dữ liệu đã hết hạn khi restore**, thay vì cố hứa mọi byte biến mất ngay. Quy trình này phải được mô tả trung thực trong tài liệu vận hành.

## 18. Cảnh báo chi phí: tăng retention không miễn phí

Chi phí log có thể tăng theo ba trục:

1. **Ingest volume:** số event/s × kích thước event; tăng DEBUG hoặc stack trace làm tăng mạnh.
2. **Storage duration:** lượng dữ liệu cần giữ và độ đắt của tầng lưu.
3. **Query & recovery:** index nhiều, shard không tối ưu, restore archive và phí truy xuất.

**Hãy phân biệt tối ưu retention với bỏ log quan trọng.** Có thể:

- Giảm DEBUG/TRACE không cần thiết ở production.
- Không log full body/header, nhất là token và PII.
- Chọn structured fields có giá trị, route template thay raw URL.
- Dùng metrics/aggregates cho sự kiện tần suất cao nếu không cần từng dòng.
- Phân tầng hot/cold thay vì giữ mọi thứ hot.
- Nén/chọn định dạng archive phù hợp với công cụ tìm kiếm/restore.
- Dùng retention ngắn hơn cho event debug đã được chứng minh ít giá trị.
- Giữ security/audit log theo policy riêng, không sampling tùy tiện các event phải bảo toàn.

**Sampling thay đổi ý nghĩa thống kê.** Nếu lưu toàn bộ lỗi nhưng chỉ 10% request thành công, tỷ lệ lỗi tính từ access logs lưu trữ sẽ bị thiên lệch nếu không có weighting hoặc metric độc lập.

## 19. Những chỉ số giám sát retention

Một hệ thống có retention policy trên giấy chưa đủ; cần biết enforcement có đang chạy không.

| Metric / tín hiệu | Dùng để kiểm tra |
| --- | --- |
| `logs_ingested_bytes_total` | Dung lượng đầu vào; dấu hiệu tăng đột biến |
| `logging_events_dropped_total` | Mất log ở producer/collector trước retention |
| `retention_candidates_total` | Số event/index/object đủ điều kiện |
| `retention_deleted_total` | Số đã xóa, phân theo class/backend |
| `retention_delete_errors_total` | Lỗi quyền, timeout, policy hoặc storage |
| `retention_backlog_bytes` | Dung lượng đáng lẽ đã hết hạn nhưng chưa xử lý |
| `oldest_expired_item_age` | Độ trễ thực thi dọn dữ liệu |
| `archive_transfer_lag` | Event đã hết hot nhưng chưa lưu archive đúng quy trình |
| `archive_verify_failures_total` | Object đã chuyển nhưng checksum/count không khớp |
| `legal_hold_items_total` | Quy mô hold, ảnh hưởng retention/cost |
| `storage_used_bytes` / `quota_remaining` | Nguy cơ disk đầy hoặc chi phí vượt ngân sách |
| `restore_test_success` | Archive có thực sự đọc/restore được khi điều tra không |
| `log_access_export_events` | Ai truy vấn/export dữ liệu nhạy cảm |

Tên metric là **đề xuất schema**, không phải mọi backend đều xuất sẵn. Khi thiết kế label, không đưa từng `request_id`, `trace_id`, `user.id` hoặc object key thành label có cardinality không giới hạn.

### SLO ví dụ

- “95% sự kiện application có thể truy vấn trong hot tier sau ingest ≤ 2 phút” là **ingestion/query SLO**, khác retention.
- “Không có application index đã hết hạn quá 24 giờ mà chưa được xử lý, ngoại trừ hold có thẩm quyền” là **enforcement SLO**.
- “Restore được một mẫu archive tháng trước trong 2 giờ” là **recovery SLO**.
- “Không có event cần giữ bị xóa trước thời hạn” là **safety invariant**, không đơn thuần là tối ưu chi phí.

Các giá trị SLO này chỉ minh họa; cần đo và thỏa thuận với đội vận hành.

## 20. Kiểm thử retention policy với fixed clock

Không nên kiểm thử TTL bằng `Thread.sleep(...)` suốt nhiều ngày. Có thể dùng `Clock.fixed(...)` hoặc truyền `Instant now` như `LogRetentionPolicyDemo`.

Các boundary tests quan trọng:

| Tình huống | Kỳ vọng |
| --- | --- |
| Log vừa mới ingest | HOT |
| Tuổi `hot - 1 ms` | Vẫn HOT |
| Tuổi đúng `hot` | ARCHIVE |
| Tuổi `total - 1 ms` | Chưa đủ điều kiện xóa |
| Tuổi đúng `total` | DELETE_ELIGIBLE |
| Có legal hold dù rất cũ | HOLD |
| Ingestion time ở tương lai | REVIEW_TIME/quarantine theo policy |
| Policy hot lớn hơn total | Validation từ chối |
| Event không có `retention.class` | Không xóa theo mặc định quá ngắn |
| Timestamp parse lỗi/clock drift | Cảnh báo, không tự đưa vào nhóm xóa |
| Event đến muộn | Quy tắc tính tuổi nhất quán với ingestion/event time |
| Restore archive trước hạn | Dữ liệu còn và giải mã/giải nén được |
| Đổi policy 30 → 7 ngày | Dry-run kiểm tác động trước áp dụng |
| Có snapshot/versioned object | Xóa hot không được báo xóa toàn bộ |
| Worker retry khi timeout | Không xóa nhầm, có idempotency/reconciliation |
| Hold được gỡ có phê duyệt | Được đánh giá lại theo policy mới, không bỏ qua audit |

Ở unit test chỉ đánh giá **decision logic**. Integration test phải chạy với file/index/object giả trong namespace test, xác minh cleanup đúng quyền, lịch, format, versioning và khả năng restore. **Không dùng dữ liệu production thật để thử lệnh delete**.

### Kiểm tra rollover thực tế

Với Logback/Log4j2, tạo nhiều event giả nhỏ trong môi trường cô lập để kích hoạt rollover:

1. Kiểm tra file active và archive pattern hợp lệ.
2. Xác nhận `maxFileSize`/period rollover theo phiên bản backend đang dùng.
3. Tạo archive cũ bằng fixture có thời gian/metadata kiểm soát và đo policy cleanup, không dựa sleep nhiều ngày.
4. Xác nhận file ngoài glob hoặc thư mục khác không bị xóa.
5. Kiểm tra behavior khi restart, không có rollover trong thời gian dài và permission denied.
6. Xác nhận file thực đã được collector ship trước khi xóa nếu đó là yêu cầu.

## 21. Những lỗi retention thường gặp

| Hiện tượng | Nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| File Logback cũ vẫn còn sau `maxHistory` | Cleanup chạy lúc rollover/startup, chưa được kích hoạt | Kiểm policy, thời điểm rollover, `cleanHistoryOnStart` |
| Disk đầy dù có `totalSizeCap` | Active file, file khác, cleanup chưa chạy | Đo disk thực và quota, không coi archive cap là hard limit |
| Backend giữ log lâu hơn kỳ vọng | ILM/index age khác event age | Kiểm thời gian rollover, phase và index policy |
| Một số event bị mất quá sớm | Index chứa nhiều tuổi sự kiện, delete theo index | Tách index theo class/period, xét late arrivals |
| `kubectl logs` không thấy log cũ | Node log rotation hoặc pod bị xóa | Tra backend tập trung, không dựa node history |
| Log vẫn lộ sau khi index xóa | Snapshot, export, archive, backup còn | Inventory tất cả bản sao và policy |
| Giữ audit ít ngày như debug | Phân loại theo root logger level | Route theo `kind`/audit policy được phê duyệt |
| Policy xóa nhầm bucket/object | Glob/prefix quá rộng | Dry-run, least privilege, canary và approval |
| Delete fail do hold | Immutable retention/legal hold | Kiểm thẩm quyền, không tự bỏ hold |
| Event cũ vừa mới ingest bị xóa | Tính tuổi theo event time mà không xử lý late arrival | Chốt mốc tin cậy và policy cho dữ liệu đến muộn |
| Đổi config retention nhưng dữ liệu mới vẫn sai | Template/data stream không được áp dụng đúng | Kiểm bootstrap, rollover và effective policy |
| Archive tồn tại nhưng không restore được | Thiếu key, corruption hoặc sai codec/schema | Restore drill, checksum, quản lý khóa |
| Tiết kiệm dung lượng nhưng không còn chứng cứ | Sampling/retention quá ngắn | Review incident detection window và audit requirements |
| Xóa nóng không giải phóng đủ dung lượng | Replica, snapshot, tombstone, retention job chưa chạy | Đo trạng thái storage và thời gian reclaim |
| Worker retention làm sập backend | Xóa mass index/object trong một đợt | Throttle, batch, quota, giám sát |
| Khôi phục backup làm log quá hạn xuất hiện lại | Restore không áp lại lifecycle | Có bước reapply/reconcile policy sau restore |

## 22. Quản lý thay đổi retention an toàn

Thay retention từ 90 xuống 14 ngày có thể làm mất khối lượng lớn bằng chứng. Không nên chỉ sửa một biến config rồi triển khai.

Quy trình đề xuất:

1. **Nêu mục đích thay đổi:** chi phí, nhu cầu điều tra, quy định hay thay data tier.
2. **Inventory nơi lưu và owner**, phân loại security/audit, PII và các bản sao.
3. **Xác định policy hiện tại và policy mới**, mốc tính tuổi, exception/hold.
4. **Dry-run** trên dữ liệu metadata thật để đếm index/object/GB sẽ chuyển tầng hoặc xóa.
5. **Đánh giá tác động tới incident window, SLO restore, legal hold và privacy requests**.
6. **Phê duyệt** theo thẩm quyền; với audit/immutable storage cần kiểm tra khả năng áp dụng thay đổi.
7. **Rollout nhỏ** ở một service/environment/test namespace và xác minh không xóa nhầm.
8. **Theo dõi** backlog, errors, lượng dữ liệu giảm, lag, cost và log bị mất.
9. **Audit** ai đổi policy, thời điểm, phiên bản và lý do.
10. **Review sau triển khai** để xác nhận cả file, index, archive, snapshot và export đúng phạm vi mới.

Với retention tăng lên, ngân sách và quyền truy cập cũng phải review. Với retention giảm, trọng tâm là **không xóa nhầm dữ liệu chưa hết nghĩa vụ**.

## 23. Ví dụ thiết kế policy cho một Java service

Giả sử có service `checkout-api` chạy trong Kubernetes, gửi structured JSONL qua collector vào backend tìm kiếm:

```text
Checkout Java service
  ├─ application/debug log       → logs-app-prod      → hot 7d, total 30d
  ├─ access log                  → logs-access-prod   → hot 7d, total 30d
  ├─ security events             → logs-security-prod → hot 30d, total 90d
  └─ audit events                → audit archive      → separate hold/retention
         │
         └─ stdout on pod → node spool → collector → routed destinations
```

**Bảng trách nhiệm mẫu:**

| Thành phần | Người chịu trách nhiệm | Điều kiện kiểm tra |
| --- | --- | --- |
| Java logger/encoder | Nhóm ứng dụng | Không log secret, sự kiện đúng `kind`/schema |
| Container stdout rotation | Nhóm nền tảng | Node spool không đầy, collector ship kịp |
| Collector routing | Nhóm observability | Phân loại service/tenant đúng, không double ingest |
| Search ILM/data stream | Nhóm backend | Delete phase và index age đúng class |
| Audit archive/hold | Nhóm bảo mật/compliance | Quyền, đối soát, retention và hold đúng |
| Backup/snapshot | Nhóm DR | Recovery drill và TTL bản sao |
| Dashboard/export | Chủ quản dữ liệu | RBAC, link expiry và quy trình xóa/export |

Giả sử p99 thời gian phát hiện sự cố là vài tuần, hot 7 ngày có thể vẫn hợp lý nếu archive/warm có thể được truy vấn nhanh khi cần; hoặc có thể không đủ nếu đội phản ứng cần tra sự cố 20 ngày trước ngay tức thì. **Retention và thời gian truy vấn sẵn có phải được thiết kế cùng nhau**.

## 24. Checklist triển khai

- [ ] Đã inventory mọi nơi dữ liệu log tồn tại: app file/stdout, collector, search, archive, snapshot, export.
- [ ] Đã phân loại log theo purpose/kind, sensitivity và owner; không dùng chỉ severity.
- [ ] Chính sách có hot duration, total duration, TTL start clock, exception/hold, deletion mechanism.
- [ ] Thời hạn được duyệt theo nghiệp vụ, bảo mật, hợp đồng và pháp lý; không lấy số ví dụ làm quy định.
- [ ] Đã tính raw bytes, index/replica/snapshot factor và peak ingest.
- [ ] File rotation/Logback/Log4j2 được cấu hình và thử thực tế.
- [ ] Retention trên Kubernetes node **khác** retention ở backend, đã kiểm tra cả hai.
- [ ] Index/data stream policy phù hợp nhóm log và thời điểm rollover.
- [ ] Archive đã được xác minh checksum/count và restore thử trước khi xóa bản hot bắt buộc.
- [ ] Legal hold/immutable retention có thẩm quyền, audit và quy tắc xử lý exception.
- [ ] Dữ liệu nhạy cảm không được thu không cần thiết; có RBAC, encryption, retention của bản export.
- [ ] Đã thử expiry boundary, late arrival, clock skew, worker retry và chính sách khi có lỗi.
- [ ] Delete job có dry-run, blast-radius limit, approval khi cần và audit log thay đổi/xóa.
- [ ] Có metric backlog, delete errors, archive lag, expired data và storage quota.
- [ ] Có quy trình restore/reconcile để dữ liệu hết hạn không vô tình quay lại sau disaster recovery.
- [ ] Đã xác minh không loại mất security/audit event chỉ để giảm chi phí.

**Ghi nhớ:** log retention là **quy tắc vòng đời dữ liệu**, không chỉ cấu hình xoay file. Muốn vận hành đúng, phải biết **loại log nào cần giữ, mốc bắt đầu tuổi, hot/archive bao lâu, ai có quyền giữ hoặc xóa, và mỗi bản sao được xử lý ra sao**. Dùng dry-run, kiểm thử ranh giới và giám sát để tránh cả hai cực đoan: xóa quá sớm hoặc giữ dữ liệu vô hạn.

### Tài liệu tham khảo

- [Logback — RollingFileAppender, maxHistory, totalSizeCap, cleanHistoryOnStart](https://logback.qos.ch/manual/appenders-rolling.html)
- [Apache Log4j2 — RollingFile Appender](https://logging.apache.org/log4j/2.x/manual/appenders/rolling-file.html)
- [Kubernetes — Logging Architecture](https://kubernetes.io/docs/concepts/cluster-administration/logging/)
- [Elastic — Index Lifecycle Management](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management)
- [Elastic — Index lifecycle phases](https://www.elastic.co/docs/manage-data/lifecycle/index-lifecycle-management/index-lifecycle)
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final)
- [Java 17 — java.time.Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html)
