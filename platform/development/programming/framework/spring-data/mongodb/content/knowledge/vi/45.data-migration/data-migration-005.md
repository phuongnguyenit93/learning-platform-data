# Thiết kế migration có phiên bản bằng công cụ hoặc tác vụ riêng

Trong ứng dụng **Spring Data MongoDB**, thay đổi cấu trúc dữ liệu không nhất thiết đi kèm một câu lệnh `ALTER TABLE` như ở cơ sở dữ liệu quan hệ. Document cũ và mới có thể cùng tồn tại trong một collection, còn entity Java, repository, `MongoTemplate`, aggregation và index có thể đã chuyển sang cách đọc mới. Vì vậy, một bản phát hành ứng dụng có thể chạy thành công nhưng vẫn xử lý sai dữ liệu lịch sử.

**Migration có phiên bản** là tập hợp các bước chuyển đổi có định danh, thứ tự, lịch sử thực thi và tiêu chí xác nhận rõ ràng. Ta có thể dùng công cụ chuyên dụng như **Mongock** hoặc chạy một **tác vụ độc lập** (Spring Boot CLI, Kubernetes Job, pipeline triển khai, v.v.). Mục tiêu là biết *đã chạy bước nào, trên môi trường nào, với mã nguồn nào, kết quả ra sao* và có thể khôi phục khi quá trình bị ngắt.

## 1. Vì sao không nên đặt chuyển đổi dữ liệu tùy tiện trong ứng dụng?

Giả sử collection `customers` đang chứa:

~~~json
{
  "_id": "CUS-1001",
  "name": "Nguyễn Minh An",
  "status": "ACTIVE"
}
~~~

Phiên bản ứng dụng mới muốn dùng `displayName` thay cho `name`. Nếu chỉ đổi thuộc tính trong `@Document` rồi triển khai, những document cũ có thể không có giá trị `displayName`. Nếu vừa khởi động ứng dụng vừa gọi `updateMany` không có kiểm soát, ta có nguy cơ chạy trùng trên nhiều instance, sửa nhầm dữ liệu, tăng tải MongoDB hoặc báo ứng dụng sẵn sàng trước khi chuyển đổi hoàn tất.

Một migration được quản lý tốt cần đáp ứng:

- **Có thể truy vết:** mỗi bước có ID/version, mô tả mục đích, tác giả, thời điểm, kết quả và mã kiểm tra nội dung (*checksum*).
- **Có thứ tự và phụ thuộc:** không chạy bước xóa trường cũ trước khi mọi consumer đã đọc được trường mới.
- **Chạy lại an toàn:** khởi động lại sau lỗi không làm nhân đôi dữ liệu, ghi đè dữ liệu mới hoặc phát sinh tác dụng phụ không mong muốn.
- **Không chạy đồng thời ngoài ý muốn:** nhiều pod/worker không cùng giành quyền chuyển đổi một tập dữ liệu.
- **Có thể quan sát và kiểm chứng:** biết tổng số bản ghi cần xử lý, đã xử lý, còn lỗi, độ trễ và ảnh hưởng tới hệ thống.
- **Có kế hoạch triển khai và phục hồi:** biết điểm dừng an toàn, tương thích giữa các phiên bản ứng dụng và cách xử lý sau khi chuyển đổi một phần.

## 2. Phân biệt phiên bản migration, phiên bản ứng dụng và phiên bản document

Ba loại phiên bản phục vụ ba nhu cầu khác nhau:

| Loại | Ví dụ | Mục đích |
| --- | --- | --- |
| Phiên bản ứng dụng | `orders-service 2.8.0` | Cho biết phiên bản code đang chạy |
| Phiên bản migration | `V005__backfill_customer_display_name` | Xác định *bước chuyển đổi dữ liệu* đã thực thi |
| Phiên bản schema document (tùy thiết kế) | `schemaVersion: 2` trong từng document | Cho phép logic đọc/ghi phân biệt nhiều dạng document cùng tồn tại |

Một ứng dụng có thể phát hành nhiều lần mà không cần migration mới. Một migration cũng có thể chạy trước khi triển khai ứng dụng mới. Không lấy `schemaVersion` trong từng document thay cho **migration history** của toàn hệ thống: hai thứ chỉ trùng nhau khi kiến trúc chủ đích thiết kế như vậy.

### Quy ước định danh

Có thể tổ chức mã nguồn migration theo thứ tự:

~~~text
migrations/
  V001__create_customer_indexes
  V002__introduce_display_name
  V003__backfill_display_name
  V004__verify_display_name
  V005__remove_legacy_name     # chỉ chạy sau giai đoạn tương thích
~~~

Tên trên là **minh họa về quy ước**. Một công cụ có thể dùng số thứ tự và annotation riêng; một tác vụ độc lập có thể dùng tệp cấu hình hoặc bảng đăng ký các class. Quan trọng là ID ổn định, có thứ tự quyết định được, tên có ý nghĩa và không tái sử dụng ID để thực hiện mục đích khác.

**Nguyên tắc bất biến:** Sau khi `V003` đã được chạy ở một môi trường, không âm thầm sửa thân migration đó rồi giữ nguyên ID. Hệ thống cần kiểm tra checksum để phát hiện khác biệt, hoặc dùng một migration mới `V006` để sửa dữ liệu. Nếu buộc phải sửa do lỗi triển khai, cần một quy trình quản trị và đối soát rõ ràng.

## 3. Hai cách tổ chức: công cụ migration và tác vụ riêng

| Cách triển khai | Đặc điểm | Nên cân nhắc khi |
| --- | --- | --- |
| Công cụ chuyên dụng (ví dụ Mongock) | Quản lý change unit, lịch sử chạy và cơ chế khóa theo tính năng/phiên bản công cụ; tích hợp với Java/Spring | Có nhiều migration nhỏ, cần chuẩn hóa cách quản lý giữa các môi trường |
| Spring Boot CLI / job độc lập | Tự điều khiển trình tự, checkpoint, batch, điều kiện chạy và đo đạc; dùng `MongoTemplate` hoặc driver | Dữ liệu lớn, cần chạy ngoài vòng đời web app, cần rate limit và giám sát riêng |
| Dùng công cụ migration **trong** job độc lập | Tận dụng lịch sử/khóa của công cụ nhưng chủ động chạy tại bước deploy | Muốn có cả hợp đồng thực thi thống nhất và quyền chủ động về thời điểm chạy |

### Với công cụ như Mongock

Mỗi change unit thường có một định danh, thứ tự, phần thực thi và khả năng khai báo bước rollback/khôi phục tùy API phiên bản được chọn. Khi áp dụng với Spring Data MongoDB, code chuyển đổi nên dùng chung cấu hình kết nối, converter và transaction policy đã được đánh giá; kiểm tra tài liệu đúng phiên bản công cụ để cấu hình scanner, driver và lock.

Không nên mặc định rằng công cụ tự đảm bảo **mọi thay đổi dữ liệu đều atomic**, rằng rollback luôn thực hiện được, hoặc rằng một lock giúp tác vụ an toàn khi lease đã hết hạn. Những bảo đảm đó còn phụ thuộc vào MongoDB, transaction, thời gian chạy, chính sách retry và nội dung migration.

### Với tác vụ độc lập

Job có thể nhận các tham số rõ ràng:

~~~text
java -jar migration-runner.jar \
  --spring.profiles.active=production \
  --migration.to-version=V003 \
  --migration.batch-size=500 \
  --migration.dry-run=false
~~~

Đây là **minh họa giao diện CLI** cho một runner tự xây dựng; các tùy chọn `migration.*` chỉ có tác dụng nếu ứng dụng đã tự định nghĩa và xử lý chúng. Không giả định Spring Boot hay MongoDB cung cấp sẵn những tùy chọn này.

Trong pipeline, cần chạy job với đúng quyền và giới hạn tài nguyên, đợi kết quả xác nhận, kiểm tra dữ liệu rồi mới chuyển sang giai đoạn triển khai tiếp theo. Tránh cho mỗi instance web tự chạy migration lâu dài qua `CommandLineRunner` hoặc `@PostConstruct` khi chưa có cơ chế phối hợp cụ thể.

## 4. Quy trình thay đổi dữ liệu trực tuyến: mở rộng → chuyển đổi → thu hẹp

Để đổi `customers.name` thành `customers.displayName` mà hệ thống vẫn hoạt động, nên chia thành các giai đoạn tương thích:

~~~mermaid
flowchart LR
    A[Release A: đọc được cả hai trường] --> B[Migration: sao chép và kiểm tra dữ liệu cũ]
    B --> C[Release B: ưu tiên trường mới]
    C --> D[Quan sát và xác nhận không còn consumer cũ]
    D --> E[Migration sau: bỏ trường cũ]
~~~

1. **Expand:** triển khai mã đọc được `displayName` và có fallback về `name`. Nếu vẫn còn instance cũ ghi `name`, thiết kế cơ chế ghi tương thích như *dual-write* tạm thời hoặc trì hoãn bước chuyển đổi đến khi mọi writer hiểu schema mới.
2. **Backfill:** sao chép giá trị `name` sang `displayName` cho bản ghi chưa có trường mới. Chỉ ghi những giá trị thiếu và phải xác định cách giải quyết khi hai trường đã tồn tại nhưng khác nhau.
3. **Verify:** đếm bản ghi chưa chuyển đổi, tìm xung đột, kiểm tra dữ liệu mẫu theo từng nhóm và đánh giá ứng dụng mới trên dữ liệu thật.
4. **Switch:** chuyển reader/writer sang `displayName`, theo dõi lỗi và bảo đảm không còn luồng ghi theo schema cũ.
5. **Contract:** ở bản phát hành sau, xóa trường `name` cũ và các index/logic đã hết nhu cầu; chỉ làm khi chắc chắn không còn consumer phụ thuộc.

Không nên gom “copy trường” và “xóa trường cũ” vào cùng một migration khi các phiên bản ứng dụng đang được triển khai luân phiên. Nếu vẫn có writer cũ, các bản ghi mới tạo sau lúc backfill chạy có thể thiếu `displayName`; cần cơ chế ghi tương thích, migration bù hoặc một bước đóng băng ghi có kiểm soát.

## 5. Ví dụ một migration idempotent với `MongoTemplate`

Ví dụ sau minh họa **phần chuyển đổi dữ liệu của một bước migration**, dùng `MongoTemplate` mở collection `customers` và MongoDB **update pipeline** để copy trường. Pipeline update được hỗ trợ từ MongoDB 4.2. Code chỉ cập nhật document có `name` nhưng thiếu `displayName`, đồng thời giữ nguyên `name` trong giai đoạn tương thích.

~~~java
import java.util.List;
import com.mongodb.client.model.Filters;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class V003BackfillCustomerDisplayName {
    private final MongoTemplate mongoTemplate;

    public V003BackfillCustomerDisplayName(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public long execute() {
        return mongoTemplate.execute("customers", collection -> {
            Bson missingNewField = Filters.and(
                Filters.exists("name", true),
                Filters.exists("displayName", false)
            );

            // Giá trị "$name" trong update pipeline là tham chiếu tới trường cũ.
            List<Bson> pipeline = List.of(
                new Document("$set", new Document("displayName", "$name"))
            );

            UpdateResult result = collection.updateMany(missingNewField, pipeline);
            return result.getModifiedCount();
        });
    }
}
~~~

Điểm đáng chú ý:

- Điều kiện `displayName` **chưa tồn tại** khiến lần chạy lại bỏ qua document đã chuyển đổi; tránh ghi đè giá trị mới của người dùng. Một cập nhật document đơn lẻ vẫn tuân theo tính nguyên tử ở cấp document của MongoDB.
- Trong update pipeline, `"$name"` là biểu thức đọc giá trị trường `name`; nếu dùng dạng `$set` thông thường với literal `"$name"`, kết quả có thể không phải điều mong muốn.
- `updateMany` có thể cập nhật **nhiều document**, nhưng toàn bộ thao tác không tự trở thành một giao dịch atomic trên tất cả document. Ví dụ này phù hợp dữ liệu quy mô vừa; không nên chạy không giới hạn trên collection khổng lồ vào giờ cao điểm.
- Kết quả `modifiedCount` phục vụ quan sát, **không** thay cho kiểm tra hậu điều kiện. Một document có cả hai trường với giá trị khác nhau không được tác vụ này tự sửa.

Sau khi backfill, kiểm tra những document còn thiếu:

~~~javascript
db.customers.countDocuments({
  name: { $exists: true },
  displayName: { $exists: false }
});
~~~

Kiểm tra bản ghi có cả hai trường nhưng không khớp (nếu quy tắc nghiệp vụ yêu cầu giá trị phải giống nhau trong giai đoạn này):

~~~javascript
db.customers.countDocuments({
  name: { $exists: true },
  displayName: { $exists: true },
  $expr: { $ne: ["$name", "$displayName"] }
});
~~~

Nếu migration này chạy đồng thời với thao tác ghi của người dùng, phép kiểm tra phải được đánh giá cùng cơ chế dual-write hoặc một giai đoạn ngừng ghi được kiểm soát. Đếm bằng 0 tại một thời điểm **không đảm bảo** các writer cũ sẽ không tạo thêm document chưa chuyển đổi sau đó.

### Khi dữ liệu rất lớn

Thay một `updateMany` lớn bằng các batch có giới hạn, thường duyệt theo `_id` hoặc khóa ổn định và lưu **checkpoint**. Chẳng hạn mỗi batch lấy tối đa 500 `_id`, cập nhật các bản ghi còn thiếu, xác minh đã ghi thành công rồi mới lưu khóa cuối cùng đã duyệt. Cần chú ý các document được thêm hoặc sửa trong lúc duyệt: checkpoint theo `_id` không tự xử lý được những bản ghi mới có khóa nằm trước mốc đã quét. Vì vậy phải có chiến lược đồng bộ writer, quét bù hoặc chốt dữ liệu đầu vào.

Tránh `skip` với offset tăng dần trên tập đang thay đổi: tốn chi phí với offset lớn và dễ bỏ sót dữ liệu. Thiết lập giới hạn batch, tốc độ ghi, retry có backoff, timeout, đo replication lag, độ trễ truy vấn và kích thước index. Với dữ liệu lớn, ưu tiên backfill theo từng batch nhỏ thay vì một transaction bao trùm hàng triệu document.

## 6. Migration runner phải quản lý lịch sử và quyền thực thi

Một migration chỉ “có số phiên bản trong tên” là chưa đủ. Runner cần có một nơi lưu lịch sử riêng, ví dụ collection `migration_history`:

~~~json
{
  "_id": "V003__backfill_customer_display_name",
  "version": 3,
  "checksum": "sha256:<digest-of-immutable-migration-definition>",
  "status": "APPLIED",
  "startedAt": "2026-11-20T02:00:00Z",
  "finishedAt": "2026-11-20T02:03:11Z",
  "runnerVersion": "1.4.0",
  "modifiedCount": 73420
}
~~~

Đây là **hợp đồng minh họa**, không phải schema cố định do MongoDB hoặc Mongock bắt buộc. Trên môi trường thực, nên ghi thời gian bằng BSON Date, áp dụng index duy nhất cho ID (trường `_id` vốn đã duy nhất), lưu mã lỗi và thông tin checkpoint ở nơi thích hợp.

### Luồng thực thi được đề xuất

~~~mermaid
flowchart TD
    A[Bắt đầu job] --> B[Giành quyền chạy / lock]
    B --> C[Đọc migration history]
    C --> D{Đã APPLIED?}
    D -->|Có, checksum khớp| E[Bỏ qua bước này]
    D -->|Có, checksum khác| F[Dừng để điều tra]
    D -->|Chưa| G[Kiểm tra tiền điều kiện]
    G --> H[Chạy migration có thể tiếp tục]
    H --> I[Kiểm tra hậu điều kiện]
    I --> J{Đạt?}
    J -->|Có| K[Ghi APPLIED và checkpoint]
    J -->|Không| L[Ghi lỗi và giữ trạng thái cần xử lý]
    E --> M[Giải phóng lock]
    F --> M
    K --> M
    L --> M
~~~

Quy trình cần trả về mã lỗi khi không lấy được lock, checksum khác, tiền điều kiện không thỏa, hoặc xác minh cuối cùng thất bại. Pipeline triển khai phải **dừng** thay vì tiếp tục như thể migration đã thành công.

### Lock, checkpoint và xử lý lỗi giữa chừng

- **Chạy một lần tại một thời điểm:** dùng cơ chế lock được công cụ hỗ trợ hoặc tự tạo một document lock với cập nhật có điều kiện mang tính atomic, chủ sở hữu, thời hạn lease và cơ chế gia hạn. Cần tính đến trường hợp worker còn chạy sau khi lease hết hạn; dùng cơ chế chặn worker cũ (*fencing*) hoặc bảo đảm worker cũ không thể tiếp tục ghi. Chỉ có TTL/lease mà không kiểm soát worker cũ là chưa đủ.
- **Trạng thái và checksum:** `APPLIED` + checksum khớp thì bỏ qua. `APPLIED` + checksum khác thì dừng kiểm tra. `FAILED`/`RUNNING` tồn dư phải được đối soát và khôi phục theo quy tắc từng migration; không mặc định đánh dấu lại là chưa chạy.
- **Thứ tự checkpoint:** chỉ ghi mốc tiến độ sau khi batch tương ứng đã được ghi thành công và kiểm tra cần thiết đã đạt. Nếu tác vụ dừng sau khi ghi dữ liệu nhưng trước khi cập nhật checkpoint, lần chạy lại có thể gặp lại batch đó — vì thế thao tác phải idempotent.
- **Cắt ngang phiên chạy:** `updateMany`, `bulkWrite` hoặc một chuỗi batch có thể đã sửa một phần dữ liệu. Phải lưu số đã xử lý, lỗi, khóa cuối và có đường khôi phục từ phần đã hoàn thành.
- **Không lạm dụng transaction:** MongoDB hỗ trợ multi-document transaction trên replica set/sharded cluster phù hợp, nhưng transaction dài và khối lượng lớn tạo chi phí, giữ tài nguyên và tăng nguy cơ timeout. Chỉ dùng transaction cho đơn vị công việc ngắn thật sự cần tính nguyên tử nhiều document; cấu hình `MongoTransactionManager` khi dùng `@Transactional` với Spring Data MongoDB và bảo đảm code tham gia đúng transaction.

Nếu migration cần tạo index, đổi validator hoặc thay collection, hãy đánh giá riêng thao tác quản trị phù hợp với phiên bản MongoDB. Không giả định mọi thao tác DDL và tất cả công đoạn backfill đều có thể gom trong một transaction. Migration liên quan index phải cân nhắc tải tạo index và các truy vấn đang chạy.

## 7. Thiết kế điều kiện chạy trong pipeline triển khai

Một kế hoạch phát hành thường cần chia việc giữa **ứng dụng**, **job migration** và **kiểm chứng**:

| Bước | Người/hệ thống thực hiện | Điều kiện qua bước |
| --- | --- | --- |
| 1. Sao lưu và xác định phạm vi | Pipeline + vận hành | Có bản sao lưu/khả năng phục hồi được kiểm tra, đo được số bản ghi thuộc phạm vi |
| 2. Deploy mã tương thích | Hệ thống triển khai | Reader và writer chấp nhận cả schema cũ/mới theo thiết kế |
| 3. Dry run (chỉ đọc) | Migration job | Xác định số bản ghi, xung đột, thời gian dự kiến, không có thao tác ghi |
| 4. Chạy backfill | Job riêng hoặc công cụ | Lock hợp lệ; batch và retry được giám sát; log đầy đủ |
| 5. Kiểm tra hậu điều kiện | Job + kiểm thử tích hợp | Không còn bản ghi chưa chuyển, sai lệch đạt ngưỡng cho phép, ứng dụng hoạt động |
| 6. Chuyển traffic/cách đọc | Ứng dụng mới | Không còn writer/consumer cũ; các chỉ số ổn định |
| 7. Cleanup ở bản phát hành sau | Migration contract | Mọi thành phần đã ngừng sử dụng schema cũ; có phương án phục hồi phù hợp |

Nên để pipeline quyết định có cho phép tiếp tục triển khai hay không thông qua **exit code**, kết quả kiểm tra và chỉ số giám sát của job. Tránh truyền thông tin đăng nhập trực tiếp trong command line hoặc đưa secret vào log; sử dụng secret manager và tài khoản chỉ có quyền cần thiết cho từng migration.

### Ghi log và đo lường

Với mỗi bước, log nên có `migrationId`, `checksum`, `executionId`, collection, tổng số dự kiến, số đã xem xét, số cập nhật, số lỗi, checkpoint, thời gian chạy và trạng thái. Không log nguyên document nếu có thông tin cá nhân. Nếu cần phân tích tốc độ, đo số document/giây, độ trễ các batch, tải CPU/I/O, kết nối, slow query và replication lag.

Đặc biệt, **số bản ghi sửa được** không tương đương **số bản ghi đúng sau migration**. Phải xác minh hậu điều kiện bằng truy vấn độc lập và kiểm tra dữ liệu mẫu hoặc invariant nghiệp vụ khi cần.

## 8. Kiểm thử migration trước khi chạy production

Kiểm thử với MongoDB thật (ví dụ môi trường Testcontainers có cấu hình replica set nếu cần transaction), tập dữ liệu chứa đủ trường hợp cũ/mới và bản sao đã ẩn danh của các tình huống khó.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Database mới, chưa chạy migration | Các bước chạy theo đúng thứ tự và ghi lịch sử `APPLIED` |
| Chạy lại đúng cùng mã | Không thay đổi dữ liệu ngoài ý muốn; bước đã áp dụng được nhận diện |
| ID cũ nhưng mã migration bị sửa | Runner phát hiện checksum khác và dừng |
| Document chỉ có `name` | `displayName` được copy; `name` được giữ trong giai đoạn expand |
| Document đã có `displayName` | Giá trị mới không bị backfill ghi đè |
| Hai trường cùng tồn tại nhưng khác nhau | Có báo cáo xung đột; xử lý theo quy tắc nghiệp vụ đã duyệt |
| Dừng giữa chừng, khởi động lại | Có thể tiếp tục từ checkpoint hoặc chạy lại an toàn; không bỏ sót |
| Hai worker tranh chạy cùng migration | Chỉ worker hợp lệ được phép ghi; worker mất lease không tiếp tục ghi |
| Writer cũ vẫn ghi trong lúc backfill | Chiến lược tương thích hoặc quét bù không để phát sinh bản ghi mới bị bỏ sót |
| Dữ liệu lớn, replica có độ trễ | Giới hạn batch và cảnh báo hoạt động; không gây suy giảm vượt ngưỡng đã định |

Cần kiểm tra cả bước **contract** ở vòng đời thực tế: sau khi loại bỏ trường `name`, không còn class, query, aggregation pipeline, index, báo cáo, ETL hoặc consumer nào đọc trường đó. Khi dùng `@Field` hay custom converter trong Spring Data MongoDB, xác minh mapping giữa tên thuộc tính Java và tên field vật lý để tránh migration chạy trên sai field.

## 9. Sai lầm thường gặp và cách tránh

**Sửa migration đã phát hành:** giữ nguyên version rồi đổi code làm môi trường có lịch sử khác nhau. Giải pháp là bước migration mới và kiểm tra checksum.

**Chạy ở startup mọi pod:** nhiều instance khởi động cùng lúc dễ gây xung đột và kéo dài thời gian readiness. Giải pháp là job điều phối duy nhất hoặc công cụ có lock, kèm chính sách xử lý lease rõ ràng.

**Xóa field ngay khi backfill:** phá vỡ các phiên bản cũ và khó rollback ứng dụng. Giải pháp là quy trình expand–backfill–contract qua nhiều lần phát hành.

**Đặt `APPLIED` trước khi xác minh:** hệ thống ghi nhận thành công khi dữ liệu mới chỉ chuyển đổi một phần. Giải pháp là checkpoint theo batch và chỉ chốt lịch sử sau khi kiểm chứng hậu điều kiện.

**Giả định transaction cho mọi thứ:** một transaction khổng lồ không phải cách mặc định để backfill hàng triệu document. Giải pháp là các batch idempotent, checkpoint và chốt theo invariant cụ thể.

**Không có phương án khôi phục:** nhiều phép chuyển đổi mất thông tin không thể đảo ngược bằng cách chạy ngược script. Giải pháp là backup/restore đã thử nghiệm, giữ trường cũ trong giai đoạn chuyển tiếp, hoặc viết bước bù được thiết kế riêng và đánh giá hệ quả của dữ liệu mới phát sinh.

## 10. Chọn chiến lược cho hệ thống Spring Data MongoDB

Nếu số lượng bước không lớn, thời gian chạy ngắn và yêu cầu quản trị rõ ràng, một công cụ như Mongock giúp chuẩn hóa định danh, thứ tự, lịch sử và lock theo năng lực phiên bản đang dùng. Nếu migration cần xử lý hàng triệu document, giới hạn tải, checkpoint nhiều giờ hoặc chạy theo lịch triển khai độc lập, nên dùng **runner/job riêng** với các cơ chế lịch sử, khóa và đối soát tương đương. Có thể kết hợp hai cách bằng việc cho công cụ migration chạy từ job triển khai.

Trong cả hai phương án, **Spring Data MongoDB cung cấp API truy cập và cập nhật dữ liệu; quy tắc migration quyết định khi nào, theo thứ tự nào, dưới quyền thực thi nào và đạt điều kiện gì mới xem là hoàn tất**. Một bước chỉ được coi là triển khai xong khi đã xác minh dữ liệu, lưu trạng thái `APPLIED` đáng tin cậy và hệ thống vẫn tương thích với các phiên bản ứng dụng liên quan.
