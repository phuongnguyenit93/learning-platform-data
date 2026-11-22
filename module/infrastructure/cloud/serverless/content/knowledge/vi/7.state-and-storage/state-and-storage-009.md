# TTL, vòng đời dữ liệu và dọn tài nguyên tạm

Ứng dụng serverless thường tạo ra nhiều dữ liệu và tài nguyên có thời hạn: cache entry, idempotency key, session, lock, file tạm, object trung gian, kết quả job, token truy cập, bản ghi retry và dữ liệu staging. Nếu không xác định lúc nào chúng hết giá trị và cách thu hồi, hệ thống sẽ tích lũy dữ liệu cũ, tăng chi phí lưu trữ, giữ thông tin nhạy cảm lâu hơn cần thiết hoặc để tài nguyên tạm chiếm chỗ.

**Time to live (TTL)** là khoảng thời gian một dữ liệu hoặc tài nguyên được xem là còn hiệu lực. Khi TTL hết, dữ liệu được xem là hết hạn theo chính sách ứng dụng. Tuy nhiên, thời điểm hết hạn logic và thời điểm dữ liệu bị xóa vật lý có thể khác nhau. Nhiều dịch vụ thực hiện xóa bất đồng bộ, theo đợt hoặc khi có hoạt động truy cập.

Thiết kế vòng đời dữ liệu cần trả lời ba câu hỏi: dữ liệu còn có giá trị trong bao lâu, khi hết hạn thì hệ thống phải cư xử thế nào, và thành phần nào chịu trách nhiệm dọn dẹp. Trong Java serverless, cần tính thêm việc execution environment có thể được tái sử dụng hoặc thu hồi bất kỳ lúc nào. Bộ nhớ và ổ đĩa tạm của function không phải kho lưu trữ bền vững, còn cleanup trong code không thể là cơ chế duy nhất cho dữ liệu cần được xóa chắc chắn.

## 1. TTL, expiration, retention và deletion

Các thuật ngữ này liên quan nhưng biểu đạt những chính sách khác nhau:

- **TTL:** khoảng thời gian một bản ghi, key hoặc tài nguyên được phép tồn tại hoặc được xem là hợp lệ.
- **Expiration (hết hạn):** thời điểm dữ liệu không còn được xem là hợp lệ theo quy tắc ứng dụng.
- **Retention (thời gian lưu giữ):** khoảng thời gian tổ chức hoặc hệ thống giữ dữ liệu trước khi được phép xóa hoặc phải xóa.
- **Deletion (xóa):** hành động loại bỏ dữ liệu khỏi một hệ thống lưu trữ cụ thể.
- **Purge (xóa triệt để theo chính sách):** quy trình xóa dữ liệu khỏi các vị trí và bản sao thuộc phạm vi chính sách, có thể gồm index, replica, backup hoặc archive theo yêu cầu áp dụng.

Ví dụ, một link tải báo cáo có thể có TTL 15 phút. Sau thời điểm đó, API phải từ chối link dù object vẫn còn trong object storage. Một lifecycle rule có thể xóa object sau 7 ngày. Như vậy, link hết hạn và object bị xóa là hai sự kiện khác nhau.

Tương tự, dữ liệu audit có thể cần retention nhiều năm dù ứng dụng không còn dùng thường xuyên. Không nên gắn TTL ngắn cho dữ liệu chỉ vì nó không còn xuất hiện trên màn hình người dùng.

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| TTL | Bao lâu thì dữ liệu hết hiệu lực? | Cache key có TTL 10 phút |
| Expiration | Sau mốc nào ứng dụng phải từ chối dữ liệu? | Token hết hạn lúc 12:00 UTC |
| Retention | Dữ liệu phải được giữ trong bao lâu? | Audit record giữ 3 năm |
| Deletion | Khi nào và ở đâu dữ liệu bị xóa? | Xóa object đã hết hạn |
| Purge | Những bản sao nào thuộc phạm vi xóa? | Xóa record và các bản sao được quản lý theo chính sách |

Không mặc định TTL hết là dữ liệu lập tức biến mất khỏi ổ đĩa. Hãy kiểm tra semantics của dịch vụ đang dùng: một số cache làm key không còn truy cập được sau khi hết hạn; một số database đánh dấu item hết hạn rồi xóa nền; object storage lifecycle thường chạy bất đồng bộ; backup có thể còn giữ bản sao đến hết chu kỳ backup.

## 2. Phân loại dữ liệu trước khi đặt TTL

Không nên dùng một TTL chung cho toàn bộ ứng dụng. Mỗi loại dữ liệu có mục đích, mức nhạy cảm, yêu cầu phục hồi và chi phí khác nhau.

| Loại dữ liệu | Mục đích | Chính sách vòng đời thường gặp |
|---|---|---|
| Cache | Giảm truy vấn hoặc tính toán lặp | TTL ngắn; có thể tái tạo |
| Session hoặc token | Duy trì phiên và quyền truy cập | Hết hạn theo thời gian, thu hồi khi cần |
| Idempotency record | Ngăn thao tác nghiệp vụ bị thực hiện lặp | Giữ ít nhất trong cửa sổ retry/replay |
| Distributed lock hoặc lease | Điều phối quyền thực hiện tạm thời | Có thời hạn và cơ chế gia hạn |
| Job state | Theo dõi công việc bất đồng bộ | Giữ đủ lâu cho client tra cứu và vận hành |
| File/object tạm | Trung gian xử lý hoặc tải xuống | Xóa sau khi hoàn tất và hết thời gian tải |
| Log và trace | Chẩn đoán, kiểm toán | Theo retention và yêu cầu bảo vệ dữ liệu |
| Audit/business record | Lịch sử nghiệp vụ | Theo chính sách lưu giữ, pháp lý và nghiệp vụ |
| DLQ message | Điều tra và phục hồi lỗi | Giữ đủ lâu cho xử lý; có quy trình redrive |
| Backup/archive | Khôi phục hoặc lưu trữ dài hạn | Theo lịch backup, retention và quy trình purge |

Một bản ghi có thể không còn cần cho luồng xử lý trực tuyến nhưng vẫn cần cho đối soát hoặc audit. Hãy xác định chủ sở hữu dữ liệu, mục đích sử dụng, mức độ nhạy cảm, nguồn tạo, nơi sao chép và điều kiện xóa trước khi đặt TTL.

Nên mô tả vòng đời theo trạng thái nghiệp vụ thay vì chỉ có một mốc thời gian. Ví dụ, báo cáo có thể đi qua QUEUED, RUNNING, SUCCEEDED, FAILED, EXPIRED và DELETED. Mỗi trạng thái quy định ai được đọc, tải hoặc hủy kết quả; TTL của job metadata có thể khác TTL của file báo cáo.

## 3. Biểu diễn thời điểm hết hạn nhất quán

Đối với dữ liệu lưu lâu hơn một invocation, nên lưu thời điểm hết hạn tuyệt đối thay vì chỉ lưu số giây còn lại trong bộ nhớ. Thời điểm tuyệt đối giúp nhiều function, worker và tiến trình cleanup dùng chung một quy tắc.

Một số nguyên tắc:

- Dùng UTC để lưu timestamp, tránh phụ thuộc timezone của máy chạy.
- Dùng kiểu thời gian có độ chính xác phù hợp, ví dụ Instant trong Java.
- Xác định rõ mốc bắt đầu TTL: lúc tạo, lúc truy cập gần nhất, lúc hoàn tất hay lúc phát hành.
- Không nhận expiresAt tùy ý từ client cho dữ liệu bảo mật; server cần tự tính theo policy.
- Xác định quy tắc so sánh: dữ liệu hết hạn khi expiresAt <= now.
- Đồng bộ thời gian giữa các hệ thống; tránh dựa vào clock cục bộ không đáng tin cho các quyết định phân tán.
- Không tái sử dụng trường timestamp cho nhiều ý nghĩa khác nhau.

Ví dụ record:

~~~json
{
  "id": "job-91ac",
  "status": "SUCCEEDED",
  "createdAt": "2026-11-17T10:00:00Z",
  "completedAt": "2026-11-17T10:03:12Z",
  "expiresAt": "2026-11-24T10:03:12Z"
}
~~~

Trong ví dụ này, job được giữ 7 ngày sau khi hoàn tất. Thời hạn được tính từ completedAt vì người dùng cần thời gian tải kết quả sau khi job thành công. Nếu tính từ lúc tạo, một job chạy lâu có thể hết hạn ngay khi vừa hoàn thành.

TTL có thể là fixed TTL hoặc sliding TTL:

- **Fixed TTL:** thời điểm hết hạn được xác định khi tạo và không thay đổi khi truy cập. Phù hợp với token, link tải có thời hạn và dữ liệu tạm cần giới hạn tuổi tối đa.
- **Sliding TTL:** mỗi lần truy cập hợp lệ, thời điểm hết hạn được kéo dài. Phù hợp với một số session hoặc cache hoạt động theo mức sử dụng, nhưng cần giới hạn tuổi tối đa và tránh gia hạn vô hạn.

Với sliding TTL, cập nhật thời hạn phải nguyên tử hoặc có kiểm soát concurrency. Nếu hai request đồng thời ghi hai thời điểm khác nhau, request cũ có thể vô tình rút ngắn TTL mới. Có thể dùng conditional update để chỉ gia hạn khi giá trị mới lớn hơn giá trị hiện tại và vẫn nằm trong maximum lifetime.

## 4. TTL hết hạn không đồng nghĩa xóa ngay lập tức

Nhiều hệ thống tách việc kiểm tra expiration khỏi việc dọn dữ liệu vật lý. Cơ chế này giúp tránh phải quét và xóa mọi bản ghi đúng vào từng giây, nhưng tạo ra khoảng trễ giữa hai thời điểm.

Một vòng đời thường gặp:

~~~mermaid
flowchart TD
    A["Tạo dữ liệu"] --> B["Đặt expiresAt / TTL"]
    B --> C["Dữ liệu còn hiệu lực"]
    C --> D{"Đã đến hạn?"}
    D -->|"Chưa"| C
    D -->|"Rồi"| E["Ứng dụng từ chối hoặc đánh dấu hết hạn"]
    E --> F["Cleanup worker / lifecycle service"]
    F --> G{"Xóa thành công?"}
    G -->|"Có"| H["Đã xóa khỏi kho đích"]
    G -->|"Không"| I["Retry hoặc đưa vào hàng chờ xử lý lỗi"]
    I --> F
~~~

Có hai thời điểm cần quan sát:

1. **Logical expiration:** ứng dụng không còn cho phép sử dụng dữ liệu.
2. **Physical deletion:** dịch vụ lưu trữ thực sự xóa dữ liệu theo cơ chế của nó.

Nếu quyền truy cập phải chấm dứt đúng lúc TTL hết, không thể chỉ trông chờ background cleanup. API và domain service phải kiểm tra expiresAt trước khi trả hoặc sử dụng dữ liệu. Cleanup vật lý có thể chạy sau đó.

Ví dụ, signed URL có thể tự hết hiệu lực theo chữ ký và thời gian hết hạn dù object chưa bị xóa. Ngược lại, nếu chỉ đặt TTL metadata mà endpoint vẫn trả object không kiểm tra thời hạn, dữ liệu vẫn có thể truy cập được sau khi lẽ ra phải hết hiệu lực.

Không dùng TTL như một bộ định thời chính xác để kích hoạt nghiệp vụ vào một thời điểm cụ thể. Nếu cần gửi thông báo đúng lịch hoặc thực hiện hành động vào thời điểm xác định, dùng scheduler, queue có delay hoặc workflow timer. Các cơ chế này cũng có thể giao sự kiện lặp hoặc trễ, nên handler vẫn phải idempotent.

## 5. TTL trong database và kho key-value

Có nhiều cách triển khai TTL trong database. Một số dịch vụ hỗ trợ TTL attribute và tự động xóa item hết hạn; một số database dùng TTL index; một số kho key-value hỗ trợ expiration trực tiếp trên key; hệ thống khác cần scheduled cleanup worker.

### Lưu thời điểm hết hạn trong record

Một cách tổng quát là thêm trường expiresAt:

~~~json
{
  "id": "idem-4e9f",
  "tenantId": "tenant-42",
  "eventId": "evt-8f31",
  "status": "COMPLETED",
  "expiresAt": "2026-11-24T10:15:30Z"
}
~~~

Khi đọc, ứng dụng kiểm tra expiration:

~~~java
public boolean isExpired(Instant expiresAt, Instant now) {
    return expiresAt != null && !expiresAt.isAfter(now);
}
~~~

Điều kiện trên có nghĩa record hết hạn khi expiresAt bằng hoặc trước now. Việc kiểm tra trong ứng dụng bảo đảm record không được sử dụng chỉ vì dịch vụ chưa kịp xóa vật lý.

### Database TTL hoặc TTL index

Nếu database có hỗ trợ TTL, ứng dụng có thể ghi một field thời gian hết hạn và để dịch vụ dọn item ở nền. Cần tìm hiểu:

- Field phải có kiểu dữ liệu nào và đơn vị nào (giây, millisecond hay timestamp).
- Dịch vụ quét expiration theo chu kỳ nào.
- Item hết hạn có còn đọc được trong một khoảng thời gian không.
- TTL có hỗ trợ compound index hoặc partition key như thế nào.
- Việc xóa có phát event hay không, và event có thể đến trễ hoặc lặp không.
- TTL có áp dụng cho replica, backup và bản export hay không.

TTL index thường là cơ chế cleanup bất đồng bộ, không nên xem như điều kiện authorization hoặc transaction constraint. Nếu dữ liệu hết hạn không được phép sử dụng, kiểm tra ở tầng ứng dụng vẫn cần thiết.

### TTL trong cache

Cache thường hỗ trợ TTL trực tiếp cho từng key. TTL giúp giới hạn thời gian dữ liệu cũ tồn tại và tránh cache tăng vô hạn. Tuy nhiên, cache expiration có thể tạo nhiều key hết hạn cùng lúc và gây cache stampede khi nhiều request cùng tải lại dữ liệu.

Có thể thêm jitter nhỏ vào TTL để phân tán thời điểm hết hạn, dùng request coalescing hoặc stale-while-revalidate nếu nghiệp vụ cho phép. Không cache dữ liệu nhạy cảm hoặc dữ liệu tenant-specific bằng key thiếu phân vùng. Cache không phải nguồn sự thật duy nhất; nếu cache bị xóa, ứng dụng phải có thể đọc lại từ nguồn bền vững.

## 6. TTL cho idempotency key, session và distributed lease

Một số dữ liệu có thời hạn vì chúng bảo vệ một quy trình phân tán.

### Idempotency record

Idempotency record ngăn cùng một ý định nghiệp vụ bị thực hiện nhiều lần. TTL phải dài ít nhất bằng cửa sổ mà client, gateway, broker hoặc vận hành có thể retry/replay. Nếu record hết hạn quá sớm, một request cũ được gửi lại có thể tạo đơn hàng hoặc giao dịch lần nữa.

Hãy phân biệt thời gian hết hạn của API request với thời gian lưu idempotency record. Ví dụ, một API có timeout 30 giây nhưng client có thể retry trong 24 giờ; idempotency record cần được giữ theo cửa sổ retry 24 giờ hoặc dài hơn theo rủi ro nghiệp vụ.

### Session và token

Token có claim exp xác định thời điểm không còn hợp lệ. Server phải kiểm tra thời hạn và các claim liên quan ở mỗi request. Session record có thể được xóa nền sau khi hết hạn, nhưng authorization không được dựa vào việc cleanup đã chạy hay chưa.

Với sliding session, cập nhật last-access hoặc expiry cần có giới hạn tối đa. Khi logout hoặc thu hồi quyền, cần cơ chế revoke hoặc versioning; chờ TTL tự hết có thể quá lâu.

### Distributed lock và lease

Lock dùng để điều phối công việc giữa nhiều worker. Lock có TTL giúp hệ thống phục hồi nếu worker chết mà không nhả lock. Tuy nhiên, worker cũ có thể tiếp tục chạy sau khi lease hết hạn và một worker mới đã lấy lock.

Chỉ kiểm tra lock còn hạn chưa đủ để ngăn worker cũ ghi đè kết quả. Với tài nguyên cần bảo vệ, dùng fencing token hoặc version tăng dần. Mỗi lần cấp lease mới, hệ thống phát một token lớn hơn; kho dữ liệu chỉ chấp nhận thao tác có token mới nhất. Điều này giúp ngăn một worker đã mất lease tiếp tục ghi dữ liệu sau worker mới.

Gia hạn lease cần dùng compare-and-set hoặc conditional update gắn với owner token. Không gia hạn chỉ dựa trên tên lock vì worker cũ có thể vô tình gia hạn lock mà worker khác đã nhận.

## 7. Vòng đời object và file trong object storage

File được tạo trong quá trình xử lý serverless thường cần vòng đời riêng. Ví dụ: file upload chưa qua kiểm tra, ảnh đã resize, báo cáo xuất ra, file import staging hoặc object trung gian giữa các bước workflow.

Một cách tổ chức là tách prefix theo mục đích:

~~~text
uploads/quarantine/{tenantId}/{uploadId}
processing/{jobId}/input
processing/{jobId}/intermediate
reports/{tenantId}/{jobId}/result
archive/{year}/{month}/...
~~~

Tên prefix giúp áp dụng lifecycle rule, phân quyền và quan sát dễ hơn. Tuy nhiên, prefix không phải cơ chế bảo mật; vẫn cần IAM và authorization theo bucket, object và tenant.

Một vòng đời file có thể là:

1. Client upload vào vùng quarantine với giới hạn kích thước và quyền ghi riêng.
2. Function xác minh loại file, nội dung, kích thước và quyền sở hữu.
3. File hợp lệ được chuyển hoặc ghi vào vùng processing.
4. Worker tạo các object trung gian và kết quả.
5. Metadata job được cập nhật khi hoàn tất.
6. File tạm được xóa sau khi không còn bước nào cần dùng.
7. Kết quả được giữ theo thời hạn tải hoặc chính sách nghiệp vụ.
8. Lifecycle rule dọn object còn sót lại và các multipart upload chưa hoàn tất.

Object storage lifecycle thường chạy bất đồng bộ. Nếu có versioning, xóa object có thể chỉ tạo delete marker trong khi các phiên bản cũ vẫn tồn tại. Cần cấu hình riêng để xóa noncurrent versions hoặc delete marker theo policy. Multipart upload chưa hoàn tất cũng có thể giữ dữ liệu và phát sinh chi phí; cấu hình abort incomplete multipart uploads nếu dịch vụ hỗ trợ.

Đối với object nhạy cảm, đừng chỉ dựa vào lifecycle rule để chặn truy cập. Khi hết hạn, API phải từ chối tải, thu hồi quyền hoặc tạo signed URL mới. Lifecycle rule đảm nhiệm dọn vật lý theo lịch của dịch vụ.

## 8. Tài nguyên tạm trong Java function

Java function có thể tạo file tạm, buffer, stream, archive hoặc nội dung trung gian. Một số nền tảng cung cấp thư mục tạm cục bộ như /tmp. Dữ liệu ở đó có thể còn tồn tại khi execution environment được tái sử dụng, nhưng cũng có thể biến mất khi môi trường bị thu hồi.

Vì vậy:

- Không lưu dữ liệu nghiệp vụ duy nhất trong thư mục tạm.
- Không giả định thư mục tạm được làm sạch ngay sau mỗi invocation.
- Tạo tên file hoặc thư mục duy nhất cho từng invocation.
- Chỉ cấp quyền truy cập cần thiết; tránh để payload nhạy cảm có thể bị đọc bởi tiến trình không liên quan.
- Đóng stream và xóa file trong finally hoặc try-with-resources phù hợp.
- Có chiến lược xử lý file mồ côi nếu invocation bị kill trước khi cleanup.
- Theo dõi dung lượng đĩa tạm và giới hạn kích thước đầu vào.

Ví dụ tạo và xóa file tạm:

~~~java
Path tempFile = Files.createTempFile("report-", ".csv");

try {
    try (BufferedWriter writer = Files.newBufferedWriter(
            tempFile, StandardCharsets.UTF_8)) {
        reportWriter.writeCsv(writer);
    }

    objectStorage.upload(tempFile, destinationKey);
} finally {
    try {
        Files.deleteIfExists(tempFile);
    } catch (IOException cleanupError) {
        logger.warn("Could not remove temporary report file", cleanupError);
    }
}
~~~

Ví dụ giả định reportWriter, objectStorage, destinationKey và logger được cung cấp bởi ứng dụng. Khối finally chạy trong luồng điều khiển Java bình thường, nhưng không bảo đảm chạy khi runtime bị kill đột ngột, mất host hoặc bị thu hồi cưỡng bức.

Nếu tạo nhiều file cho một invocation, tạo một thư mục riêng bằng Files.createTempDirectory, đặt mọi file con trong đó và xóa đệ quy sau khi hoàn tất. Khi cần dọn file mồ côi, chỉ quét namespace do ứng dụng sở hữu và chỉ xóa thư mục cũ hơn ngưỡng an toàn; phải tránh xóa file của invocation đồng thời. Một lease hoặc marker có thời hạn có thể giúp phân biệt thư mục đang hoạt động với thư mục bị bỏ lại.

Không dùng một tên file cố định như /tmp/report.csv cho mọi request. Nếu môi trường có concurrency, các invocation có thể ghi đè file của nhau. Ngay cả khi runtime hiện tại xử lý tuần tự, môi trường được tái sử dụng có thể để lại nội dung cũ nếu lần chạy mới không ghi đè toàn bộ file.

## 9. Cleanup phải chịu được lỗi và chạy lặp an toàn

Cleanup là một công việc phân tán và có thể thất bại giống các công việc nghiệp vụ khác. API xóa object có thể timeout sau khi object đã bị xóa; worker có thể bị gọi lại; một record có thể đã được cleanup bởi tiến trình khác.

Vì vậy, cleanup worker cần idempotent:

- Xóa một resource đã không còn tồn tại nên được xem là hoàn tất nếu semantics dịch vụ cho phép.
- Ghi trạng thái cleanup bằng conditional update hoặc version để không ghi đè trạng thái mới.
- Dùng batch nhỏ, retry có giới hạn và backoff cho lỗi tạm thời.
- Phân loại lỗi vĩnh viễn như permission denied hoặc resource ownership mismatch để cảnh báo.
- Không xóa resource nếu owner, tenant hoặc version không khớp.
- Ghi nhận thời điểm thử cuối, số lần retry và lỗi cuối cùng.
- Có DLQ hoặc danh sách lỗi cần điều tra cho cleanup không thể phục hồi.

Ví dụ, cleanup worker đọc một record có expiresAt, sau đó kiểm tra lại ngay trước khi xóa. Nếu người dùng vừa gia hạn resource, worker cũ không được xóa dữ liệu mới. Có thể dùng conditional delete yêu cầu expiresAt vẫn bằng giá trị đã đọc và version không thay đổi.

Một quy trình xóa an toàn:

~~~mermaid
flowchart TD
    A["Tìm record có expiresAt <= now"] --> B["Đọc owner và version"]
    B --> C["Kiểm tra lại policy và trạng thái"]
    C --> D{"Vẫn hết hạn và đúng owner?"}
    D -->|"Không"| E["Bỏ qua; dữ liệu đã được gia hạn hoặc thay đổi"]
    D -->|"Có"| F["Conditional delete / purge"]
    F --> G{"Kết quả?"}
    G -->|"Thành công hoặc đã xóa"| H["Ghi nhận hoàn tất"]
    G -->|"Lỗi tạm thời"| I["Retry có backoff"]
    G -->|"Lỗi quyền / không hợp lệ"| J["Cách ly và cảnh báo"]
~~~

Đối với cleanup có nhiều bước, lưu trạng thái tiến trình để có thể tiếp tục sau crash. Ví dụ, xóa object, xóa metadata, thu hồi signed URL hoặc cập nhật job status có thể không nằm trong cùng transaction. Mỗi bước nên có thể chạy lại mà không tạo tác dụng phụ sai.

## 10. Lên lịch cleanup: TTL engine, sweeper và event trigger

Có ba cách phổ biến để dọn dữ liệu hết hạn.

### TTL engine của dịch vụ

Database, cache hoặc object storage có thể cung cấp expiration hoặc lifecycle rule tích hợp. Ưu điểm là ít code và không cần tự quét toàn bộ dữ liệu. Nhược điểm là thời gian xóa thường không chính xác đến từng giây, khả năng phát event và semantics khác nhau giữa dịch vụ.

Dùng TTL engine khi yêu cầu là dữ liệu hết hạn được dọn trong một khoảng trễ chấp nhận được và ứng dụng vẫn kiểm tra logical expiration.

### Scheduled sweeper

Một scheduled function chạy định kỳ, tìm các record có expiresAt <= now rồi xóa theo batch. Cách này linh hoạt khi cần nhiều bước, audit hoặc điều kiện nghiệp vụ. Cần index theo thời điểm hết hạn, giới hạn batch, checkpoint và concurrency control để tránh full table scan hoặc nhiều sweeper xử lý cùng record.

Nếu sweeper chạy mỗi 5 phút, dữ liệu có thể còn tồn tại vật lý thêm gần 5 phút hoặc lâu hơn khi backlog. Đừng quảng bá TTL là chính xác đến giây nếu cơ chế cleanup chỉ chạy định kỳ.

### Event-driven cleanup

Một scheduler hoặc workflow có thể phát sự kiện khi đến hạn để kích hoạt cleanup. Cách này phù hợp với số lượng tài nguyên nhỏ hoặc công việc có quy trình rõ. Tuy nhiên, timer/event có thể đến trễ, lặp hoặc thất bại. Handler phải kiểm tra trạng thái hiện tại và idempotent trước khi xóa.

Với số lượng lớn tài nguyên, một sự kiện cho từng item có thể tạo chi phí và tải đáng kể. Có thể dùng TTL engine hoặc sweeper theo lô thay thế.

### Kết hợp các cơ chế

Một thiết kế thường dùng TTL engine để dọn phần lớn dữ liệu, đồng thời có sweeper định kỳ để phát hiện item bị sót, cleanup lỗi hoặc tài nguyên ngoài phạm vi TTL tự động. Tránh để hai cơ chế xóa cạnh tranh mà không có conditional check.

## 11. Backup, replica, log và yêu cầu xóa dữ liệu

Xóa record khỏi bảng chính không đồng nghĩa mọi bản sao của dữ liệu đã biến mất. Dữ liệu có thể còn trong:

- Read replica hoặc bản sao vùng địa lý.
- Backup snapshot và point-in-time recovery.
- Export, data lake hoặc analytics store.
- Log, trace, metric label hoặc error report.
- Cache và CDN.
- DLQ, event stream hoặc archive.
- File tạm và object version cũ.

Retention policy cần chỉ rõ thời hạn và cơ chế xử lý cho từng bản sao. Một số backup có thể được giữ đến hết chu kỳ rồi mới hết hạn; một số hệ thống hỗ trợ crypto-shredding bằng cách hủy khóa mã hóa theo thiết kế. Đây là quyết định kiến trúc và quản trị dữ liệu, không thể suy ra chỉ từ TTL của bảng chính.

Không đưa payload nhạy cảm vào log nếu không cần. Dùng ID tham chiếu, che trường hoặc giảm dữ liệu ghi. Nếu một yêu cầu xóa phải áp dụng trên nhiều hệ thống, tạo deletion workflow có danh sách đích, trạng thái từng bước, retry và bằng chứng hoàn tất. Nếu có legal hold hoặc yêu cầu giữ bắt buộc, policy phải xác định cách xử lý ngoại lệ trước khi purge.

TTL cũng không thay thế chính sách retention tối thiểu. Dữ liệu cần giữ để đáp ứng hợp đồng, kế toán hoặc audit có thể không được xóa ngay khi ứng dụng ngừng sử dụng. Ngược lại, dữ liệu cá nhân không cần thiết không nên giữ vô thời hạn chỉ vì storage rẻ.

## 12. Chi phí và tác động vận hành của vòng đời dữ liệu

Chi phí lưu trữ thường phụ thuộc dung lượng, thời gian lưu, số lần truy cập, request cleanup, replication, backup và data transfer. Dữ liệu tạm bị bỏ quên có thể tạo chi phí liên tục dù không còn giá trị nghiệp vụ.

Khi thiết kế TTL, hãy xem:

- Dung lượng trung bình mỗi bản ghi hoặc object.
- Số lượng dữ liệu mới tạo mỗi ngày.
- TTL trung bình và phân bố thời gian lưu.
- Chi phí truy vấn index để tìm dữ liệu hết hạn.
- Chi phí request xóa và lifecycle operation.
- Dung lượng replica, version và backup.
- Chi phí lưu DLQ, log và archive.
- Chi phí khôi phục hoặc tái tạo dữ liệu nếu TTL quá ngắn.

Một TTL ngắn hơn không phải lúc nào cũng rẻ hơn. Nếu dữ liệu phải được tạo lại liên tục, chi phí tính toán và dependency có thể tăng. Cache TTL quá ngắn có thể gây cache stampede; job TTL quá ngắn làm người dùng không kịp tải kết quả; idempotency TTL quá ngắn có thể dẫn đến side effect trùng.

Một TTL quá dài cũng có tác động: dung lượng tích lũy, thời gian lộ dữ liệu tăng, index phình to và cleanup backlog lớn hơn. Hãy đo cả chi phí lưu trữ lẫn chi phí tái tạo và vận hành.

## 13. Kiểm thử TTL và cleanup

TTL thường khó kiểm thử nếu test phải chờ thời gian thực. Có thể tách logic tính hạn khỏi cơ chế đồng hồ và inject Clock trong Java để test bằng thời điểm cố định.

Ví dụ:

~~~java
public final class ExpirationPolicy {
    private final Clock clock;

    public ExpirationPolicy(Clock clock) {
        this.clock = clock;
    }

    public Instant expiresAfter(Duration ttl) {
        if (ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException("TTL must be positive");
        }
        return clock.instant().plus(ttl);
    }

    public boolean isExpired(Instant expiresAt) {
        return expiresAt != null
                && !expiresAt.isAfter(clock.instant());
    }
}
~~~

Trong test, dùng Clock.fixed để kiểm tra trước hạn, đúng thời điểm hết hạn và sau hạn mà không cần chờ. Các kịch bản cần kiểm thử:

1. Dữ liệu còn hạn được đọc bình thường.
2. Dữ liệu đúng tại mốc expiresAt bị xem là hết hạn.
3. Dữ liệu đã hết hạn không được trả về dù cleanup chưa chạy.
4. Cleanup chạy hai lần không tạo lỗi hoặc side effect trùng.
5. Cleanup cũ không xóa resource vừa được gia hạn.
6. Lỗi xóa tạm thời được retry; lỗi quyền được cảnh báo.
7. Invocation bị dừng giữa các bước cleanup vẫn có thể tiếp tục.
8. File tạm được xóa khi xử lý thành công và khi có exception.
9. File mồ côi không bị xóa khi invocation khác vẫn đang dùng.
10. Backup, object version, DLQ và log tuân theo retention riêng.

Đừng chỉ test logic expiresAt. Cần kiểm thử integration với dịch vụ thật hoặc môi trường tương thích để xác nhận đơn vị TTL, độ trễ cleanup, cách xử lý version và giới hạn batch.

## 14. Checklist thiết kế TTL và vòng đời dữ liệu

Trước khi triển khai, hãy trả lời:

1. Dữ liệu được tạo để phục vụ mục đích gì và ai sở hữu nó?
2. Dữ liệu hết hiệu lực khi nào? TTL tính từ lúc tạo, hoàn tất hay truy cập gần nhất?
3. Đây là fixed TTL hay sliding TTL? Có maximum lifetime không?
4. Dùng timestamp UTC và đơn vị TTL đúng theo contract của dịch vụ chưa?
5. Ứng dụng có kiểm tra logical expiration trước khi đọc hoặc sử dụng không?
6. Dịch vụ xóa vật lý ngay hay bất đồng bộ? Độ trễ cleanup được chấp nhận bao lâu?
7. TTL có phù hợp với retry, replay, idempotency và thời gian phục hồi không?
8. Cleanup có idempotent, có conditional delete và chống race với thao tác gia hạn không?
9. File/object tạm có prefix, owner, retention và lifecycle rule rõ ràng không?
10. Java function có xóa file trong finally và xử lý file mồ côi không?
11. Backup, replica, log, cache, DLQ và object version có policy riêng không?
12. Có legal hold hoặc retention tối thiểu cần ưu tiên hơn TTL không?
13. Có metric cho dữ liệu hết hạn, cleanup lag, lỗi cleanup và dung lượng tích lũy không?
14. Có cảnh báo khi cleanup backlog tăng hoặc tài nguyên tạm vượt ngưỡng không?
15. Có kiểm thử concurrency, retry, invocation bị kill và cleanup chạy lặp không?

## Kết luận

TTL xác định khoảng thời gian dữ liệu hoặc tài nguyên còn hiệu lực; retention xác định thời gian hệ thống giữ dữ liệu; expiration và physical deletion có thể xảy ra ở những thời điểm khác nhau. Vì nhiều dịch vụ dọn dữ liệu bất đồng bộ, ứng dụng cần tự từ chối dữ liệu hết hạn và dùng cleanup worker hoặc lifecycle rule để xóa vật lý theo chính sách.

Trong Java serverless, hãy lưu thời điểm hết hạn tuyệt đối, chọn TTL theo mục đích dữ liệu, giữ idempotency record đủ lâu cho retry/replay, dùng lease có fencing khi cần điều phối và dọn file tạm trong phạm vi invocation. Cleanup cần chạy lặp an toàn, có retry, conditional delete và quan sát được. Một vòng đời dữ liệu rõ ràng giúp giảm chi phí, hạn chế dữ liệu nhạy cảm tồn tại quá lâu và bảo đảm function có thể phục hồi khi execution environment bị thu hồi bất kỳ lúc nào.

