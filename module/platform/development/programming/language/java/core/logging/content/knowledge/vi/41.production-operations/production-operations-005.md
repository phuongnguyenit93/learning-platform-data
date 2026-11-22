# Replay log trong Java Logging — Vận hành production an toàn

## 1. Replay log là gì và tại sao cần?

**Replay log** là việc **đọc lại những sự kiện log đã tồn tại** từ một nguồn còn lưu dữ liệu rồi gửi lại qua một đường xử lý: parser, collector, index, kho quan sát hoặc quy trình phân tích. Mục tiêu có thể là khôi phục dữ liệu quan sát sau sự cố, nạp bù khoảng thời gian bị thiếu, sửa lỗi phân tích định dạng, đối chiếu kiểm toán hoặc xây dựng lại chỉ mục tìm kiếm.

Một tình huống phổ biến: ứng dụng Java vẫn ghi log xuống file khi Elasticsearch/collector gián đoạn. Sau khi hệ thống đích phục hồi, đội vận hành cần chuyển những bản ghi chưa ingest tới nơi truy vấn. Hoặc hệ thống đã ingest nhưng parser cũ xử lý sai timestamp; cần đọc lại bản gốc vào **index mới** với parser đã sửa để kiểm tra.

~~~text
Java application
    |
    v
File / stdout / archived logs / Kafka topic
    |                              |
    |                  [chọn offset hoặc time range]
    +--------------+---------------+
                   |
                   v
          Replay reader / shipper
                   |
             parse, validate
                   |
           dedup + rate limit
                   |
                   v
       ISOLATED destination index
                   |
           compare and approve
                   |
                   v
       Cutover hoặc kết thúc điều tra
~~~

Replay trong ngữ cảnh này **không có nghĩa chạy lại nghiệp vụ đã tạo log**. Gửi lại dòng INFO "payment succeeded" tới log collector không được kích hoạt thanh toán thêm một lần. **Log quan sát không tự là event log nghiệp vụ**; nó có thể thiếu thứ tự toàn cục, dữ liệu cần thiết, bảo đảm độ bền và schema để tái dựng trạng thái.

Những tình huống nên cân nhắc replay:

- **Backfill:** log tồn tại ở file/topic/archive nhưng thiếu tại hệ thống quan sát.
- **Reparse:** parser, multiline hoặc timezone mapping cũ sai, cần diễn giải lại.
- **Reindex:** chuyển dữ liệu từ index nguồn sang index có mapping/retention mới.
- **Điều tra sự cố:** dựng lại một tập log được giới hạn theo requestId, service hoặc khoảng thời gian.
- **Migration:** thử pipeline observability mới với dữ liệu lịch sử, không chạm pipeline live.
- **Disaster recovery:** tái tạo index truy vấn từ kho log đã được lưu bền vững, nếu nguồn còn đầy đủ.

**Nguyên tắc vận hành:** đọc lại log không được làm mất dữ liệu nguồn, làm quá tải pipeline live, ghi trùng ngoài chính sách hoặc tái tạo dữ liệu mà tổ chức đã có nghĩa vụ xóa.

## 2. Phân biệt những dạng replay dễ bị nhầm

| Khái niệm | Đầu vào | Đích/ý nghĩa | Nguy cơ chính |
| --- | --- | --- | --- |
| **Log replay / re-ingestion** | File log, Kafka topic chứa log, archive | Nạp lại vào observability pipeline | Duplicates, sai thứ tự, sai timestamp |
| **Log reprocessing** | Raw log đã lưu | Áp dụng parser/redaction/enrichment mới | Khác schema, lộ thông tin cũ |
| **Reindex** | Document đã index | Tạo index mới hoặc điều chỉnh cách lưu/truy vấn | Mất mapping, overwrite, conflict |
| **Kafka consumer replay** | Records còn tồn tại trong topic | Consumer đọc lại từ offset trước | Tác dụng phụ, thay consumer offset |
| **Event-sourcing replay** | Domain events có schema và contract | Dựng lại projection/trạng thái nghiệp vụ | Side effects, thứ tự và schema evolution |
| **Audit review** | Kho audit có tính toàn vẹn | Đối chiếu hoặc điều tra chứng cứ | Không được sửa hay phá chain bằng chứng |

Một dòng log text không đủ để chạy lại việc chuyển tiền hay gửi email. Nếu mục tiêu thực sự là **khôi phục state từ domain events**, phải áp dụng thiết kế event sourcing riêng, kiểm soát command handler và external side effects. Không dùng pipeline logging thông thường làm hệ thống command replay.

Tương tự, **reindex trên Elasticsearch** từ các document đã tồn tại không phải là đọc lại những file bị thất lạc. Nếu document chưa từng được ingest và không còn nguồn dự phòng, reindex không thể tự sinh lại dữ liệu đó.

## 3. Phải xác định mục tiêu và nguồn sự thật

Trước khi chạy job, trả lời:

1. **Tại sao replay?** Khôi phục thiếu log, sửa parsing, migration, hay kiểm chứng?
2. **Nguồn chuẩn ở đâu?** File gốc, rotated file, archive, Kafka topic, object storage hay index cũ?
3. **Phạm vi chính xác?** Service, environment, tenant, time range, source files, partition/offset, traceId hoặc eventCode.
4. **Đích sẽ ghi vào đâu?** Index cách ly, namespace mới, cluster thử nghiệm hay đích production đã duyệt?
5. **Có cho phép ghi đè không?** Nếu có, theo điều kiện/version nào? Nếu không, chọn create-only và xử lý conflict.
6. **Dữ liệu cần bảo toàn gì?** Event timestamp, source identity, raw bytes, thứ tự, metadata, redaction.
7. **Tiêu chí hoàn tất?** Bao nhiêu unique events phải có, khoảng trống nào được lấp, parser field nào phải khớp?
8. **Ai duyệt và rollback?** Owner vận hành, bảo mật, data retention và người điều hành cutover.

Không dùng một lệnh "replay toàn bộ" trong production khi chỉ cần một ngày log của một service. **Phạm vi nhỏ, có giới hạn** giúp giảm chi phí và thiệt hại khi nhầm nguồn hoặc đích.

Một kế hoạch mẫu:

~~~yaml
replayRunId: replay-20261110-01
purpose: repair-incorrect-timestamp-parsing
source: immutable-archive/orders/2026-11-09/
timeRangeUtc: "2026-11-09T00:00:00Z/2026-11-10T00:00:00Z"
destination: logs-orders-replay-20261110
parserVersion: orders-v4
mode: dry-run-then-bounded-write
maxRecordsPerBatch: 1000
maxRecordsPerSecond: 2000
approvalRef: change-1234
~~~

Đây là **bản kế hoạch minh họa**, không phải một schema cấu hình được mọi công cụ hỗ trợ. Tránh dùng tên production thực hoặc bí mật kết nối trong tài liệu/replay manifest mở rộng quyền.

## 4. Source of truth, timestamp và tính đầy đủ của log

Một tập log có thể xuất hiện nhiều nơi:

~~~text
Java / Logback / Log4j 2 / JUL
        |
        +--> stdout/container runtime logs
        +--> live application.log
        +--> rotated + compressed files
        |
        v
Filebeat / Fluent Bit / OpenTelemetry Collector
        |
        +--> buffering / disk queue / Kafka
        |
        v
Search index / object archive / dashboard / backup
~~~

**Nguồn dữ liệu đáng tin** không nhất thiết là file đầu tiên được tìm thấy. File có thể đã rotate, truncate, bị xóa, chỉ lưu một phần thời gian hoặc chứa log đã được redacted khác với nơi khác. Index cũ có thể thiếu record do sự cố ingest. Backup có thể già hơn khoảng dữ liệu cần tái dựng.

Một event có thể có nhiều loại timestamp:

- **Event timestamp:** lúc ứng dụng Java tạo sự kiện; cần giữ khi replay để phân tích đúng ngày xảy ra.
- **Observed/ingest timestamp:** lúc collector tiếp nhận, hoặc lần replay sau; có thể là nhiều giờ/ngày sau event.
- **Replay timestamp:** lúc job replay xử lý lại. Nên lưu riêng dạng metadata.
- **Source offset/position:** nơi bản ghi nằm trong file/partition; không phải thời gian nghiệp vụ.

Nếu parser gán lại mọi timestamp bằng "now()" thì log cũ có thể hiện như lỗi mới hôm nay, gây sai dashboard/alert. **Không được thay event time bằng replay time** trừ khi có hợp đồng di trú rõ ràng và vẫn giữ trường gốc.

Cũng phải ghi nhận các **khoảng không còn dữ liệu**: nếu retention đã xóa records trong Kafka hoặc file cũ bị mất, không có cách replay những record không còn ở nguồn. Kết quả cần nêu rõ phần bất khả khôi phục thay vì báo đã phục hồi đủ.

## 5. Bảo đảm phân phối: at-most-once, at-least-once và exactly-once

Khi replay, một record có thể được đọc và gửi nhiều lần, đặc biệt sau timeout:

~~~text
Reader gửi event E -> Sink đã ghi E
          |
       ACK bị mất
          |
Reader retry E -> Sink nhận E lần nữa
~~~

Các mô hình:

| Semantics | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| At-most-once | Mỗi record cố gửi tối đa một lần trong cơ chế đã định | Có thể mất record nếu lỗi sau khi advance cursor |
| At-least-once | Retry cho tới khi được xác nhận theo chính sách | Có thể phát duplicate |
| Exactly-once | Không tạo tác dụng quan sát trùng trong **ranh giới giao dịch cụ thể** | Đòi hỏi thiết kế nguồn, sink, transaction/idempotency phù hợp |

**At-least-once + idempotent sink** là một chiến lược phổ biến cho log backfill. Tuy nhiên, không nên tuyên bố exactly-once toàn hệ thống chỉ vì Kafka có tính năng transactional processing: nếu đích là một HTTP API, database, email hoặc Elasticsearch ngoài transaction liên kết, vẫn cần cơ chế tránh hiệu ứng trùng ở đích.

Phân biệt **số record đọc**, **số attempt gửi**, **số unique event được lưu**. Khi tính mức hoàn tất, số attempt lớn hơn số unique do retry không mặc nhiên là lỗi.

## 6. Thiết kế khóa chống trùng có ý nghĩa

Nếu nguồn có eventId **ổn định qua mọi lần replay**, có thể dùng nó làm khóa cùng phạm vi namespace:

~~~text
dedupKey = sourceIdentity + ":" + eventId
~~~

Một eventId chỉ duy nhất **trong từng nguồn** chưa chắc duy nhất trên toàn công ty. Vì vậy nên đưa service/source/tenant hoặc partition vào khóa theo đúng contract.

Những nguồn có sẵn vị trí:

- **Kafka:** thường có topic + partition + offset cho một physical record; offset thuộc từng partition, không có thứ tự toàn topic.
- **File:** có file identity + byte offset + boundary/length, nhưng cần cẩn thận file rotate, inode reuse, copy file và line ending.
- **JSON log:** có thể có eventId do ứng dụng sinh, ổn định ngay khi LogEvent được phát.
- **Search document:** có _id; cần hiểu liệu ID đã là stable event ID hay được backend tự tạo mới cho mỗi ingest.

Nếu không có eventId, content hash là một phương án phụ **chỉ khi** đã đánh giá việc trùng nội dung có thể là hai events hợp lệ. Hai dòng hoàn toàn giống nhau từ hai request khác nhau không nhất thiết là duplicate; hash chỉ theo message có thể xóa nhầm sự kiện thật.

Một vấn đề khác: **cùng ID nhưng nội dung khác**. Đừng bỏ qua âm thầm. Đây có thể là schema corruption, sai mapping, ID collision hoặc một bản ghi đã bị sửa; cần cảnh báo/conflict quarantine và quy trình quyết định chính sách.

Khi replay có chủ ý để **sửa dữ liệu đã sai**, mục tiêu có thể là replace document cũ theo version hoặc đưa vào index mới; không dùng create-only cùng ID rồi thắc mắc vì sao dữ liệu mới không xuất hiện.

## 7. Checkpoint và cursor: tiếp tục từ đâu sau khi dừng?

**Checkpoint** lưu vị trí **tiếp theo cần đọc** ở từng nguồn/partition/file, giúp job dừng rồi tiếp tục mà không quét lại toàn bộ dữ liệu.

~~~text
file-2026-11-09.log
    byte offset: 8,192,000
        |
        v
Replay batch records
        |
        v
Sink ACK + validate
        |
        v
Commit checkpoint for that source
~~~

Nguyên tắc an toàn:

1. Không advance checkpoint chỉ vì đã **đọc** hoặc **enqueue** thành công; cần biết điều kiện xác nhận đích.
2. Giữ cursor riêng cho mỗi file/partition, cùng identity, phiên bản parser và replayRunId khi cần.
3. Nếu job restart sau khi sink ghi thành công nhưng trước checkpoint, bản ghi có thể được gửi lại; **đích phải idempotent**.
4. Nếu record không parse được, phải có chính sách rõ: dừng, đưa vào quarantine bền vững rồi mới advance, hoặc xử lý theo mức quan trọng.
5. Không gộp checkpoint của pipeline live và replay nếu điều đó khiến tiến độ live bị thay đổi.
6. Nếu source file bị thay/truncate hoặc topic đã hết retention, không tin offset cũ còn trỏ đúng dữ liệu.
7. Dùng phép đối chiếu count, checksum/hash theo từng batch và marker hoàn tất để nghiệm thu.

**Không tự động commit offset sản xuất khi job replay còn đang thử nghiệm**, và không tái sử dụng group/registry live chỉ vì tiện. Mục tiêu replay là độc lập với luồng vận hành đang hoạt động.

## 8. Ví dụ Java 17+ chạy độc lập: replay idempotent vào đích cô lập

Ví dụ này dùng **Java Standard Library**, không cần Kafka, database hay quyền ghi file. Nó mô phỏng 5 vị trí log với một record được giao lặp, một record DEBUG được loại **theo policy minh họa**, và ba sự kiện được lưu vào Map biểu diễn **index cô lập**.

Mỗi event có source và eventId; khi replay lần hai từ offset 0, chương trình không tạo bản thứ hai ở index. Nếu cùng khóa nhưng nội dung khác, code **ném lỗi** thay vì ghi đè hoặc coi là duplicate hợp lệ.

Tạo file **ReplayLogDemo.java**:

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ReplayLogDemo {
    record Event(String source, String eventId,
                 String level, String code) {}

    record Positioned(long offset, Event event) {}

    record Result(int scanned, int inserted, int duplicates,
                  int filtered, long nextOffset) {}

    static Result replay(List<Positioned> input,
                         Map<String, Event> target,
                         long startOffset) {
        int scanned = 0;
        int inserted = 0;
        int duplicates = 0;
        int filtered = 0;
        long next = startOffset;

        for (Positioned line : input) {
            if (line.offset() < startOffset) {
                continue;
            }
            if (line.offset() < next) {
                throw new IllegalArgumentException("Out of order");
            }

            scanned++;
            Event event = line.event();
            if ("DEBUG".equals(event.level())) {
                // Chính sách minh họa: không replay DEBUG.
                filtered++;
            } else {
                String key = event.source() + ":" + event.eventId();
                Event previous = target.putIfAbsent(key, event);
                if (previous == null) {
                    inserted++;
                } else if (previous.equals(event)) {
                    duplicates++;
                } else {
                    throw new IllegalStateException(
                            "Conflicting event ID: " + key);
                }
            }
            next = line.offset() + 1;
        }

        return new Result(scanned, inserted, duplicates, filtered, next);
    }

    public static void main(String[] args) {
        Event created =
                new Event("orders", "evt-100", "INFO", "ORDER_CREATED");
        Event failed =
                new Event("orders", "evt-101", "ERROR", "PAYMENT_TIMEOUT");

        List<Positioned> archive = List.of(
            new Positioned(0, created),
            new Positioned(1, failed),
            new Positioned(2, failed), // Cùng event bị gửi hai lần.
            new Positioned(3, new Event(
                    "orders", "evt-102", "DEBUG", "CACHE_HIT")),
            new Positioned(4, new Event(
                    "orders", "evt-103", "WARN", "ORDER_DELAYED"))
        );

        Map<String, Event> isolatedIndex = new LinkedHashMap<>();

        Result first = replay(archive, isolatedIndex, 0);
        Result replayed = replay(archive, isolatedIndex, 0);
        Result resumed = replay(
                archive, isolatedIndex, first.nextOffset());

        System.out.println("first=" + first);
        System.out.println("replay=" + replayed);
        System.out.println("resume=" + resumed);
        System.out.println("indexedUnique=" + isolatedIndex.size());
        System.out.println("keys=" +
                String.join(",", isolatedIndex.keySet()));
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac ReplayLogDemo.java
java ReplayLogDemo
~~~

Kết quả **xác định**:

~~~text
first=Result[scanned=5, inserted=3, duplicates=1, filtered=1, nextOffset=5]
replay=Result[scanned=5, inserted=0, duplicates=4, filtered=1, nextOffset=5]
resume=Result[scanned=0, inserted=0, duplicates=0, filtered=0, nextOffset=5]
indexedUnique=3
keys=orders:evt-100,orders:evt-101,orders:evt-103
~~~

### Đọc kết quả

- **Lượt đầu:** quét 5 vị trí; ghi 3 unique events; phát hiện một duplicate của evt-101; bỏ một DEBUG theo policy demo; vị trí tiếp theo là 5.
- **Replay từ đầu:** quét lại 5 vị trí, không tăng số event đã index; 4 bản thuộc những ID đã có nên được tính duplicate (evt-101 có hai lần xuất hiện), DEBUG vẫn lọc.
- **Resume từ checkpoint 5:** không còn vị trí mới nên scanned=0, index vẫn có ba event.
- **Thứ tự key:** LinkedHashMap giữ thứ tự insertion trong demo; nó không chứng minh một backend phân tán có thứ tự toàn cục tương tự.

### Giới hạn quan trọng

1. Map chỉ tồn tại trong RAM; khi process restart, dedup state và checkpoint **biến mất**, nên ví dụ **không chứng minh durability hoặc exactly-once**.
2. Code chưa ghi file, chưa liên hệ collector, chưa xử lý retry/ACK, chưa có transaction giữa target write và checkpoint.
3. Checkpoint chỉ là long trên một nguồn tuyến tính. Production phải có cursor riêng theo Kafka partition hoặc file identity; không dùng cùng một số cho mọi nguồn.
4. DEBUG được loại **chỉ để minh họa policy**. Nếu mục tiêu là phục hồi mọi log, không lọc DEBUG tùy tiện. Với audit/security bắt buộc, phải tuân theo chính sách lưu và kiểm chứng riêng.
5. Dùng key source:eventId trong ví dụ không có escaping/normalization phức tạp. Production cần contract định danh tránh va chạm giữa tenant/service.
6. Map.putIfAbsent không phải thao tác atomic xuyên Kafka, database và file checkpoint. Đích thật phải hỗ trợ upsert/create-only có điều kiện và ghi nhận ACK thích hợp.
7. Nếu cùng ID có payload khác, demo ném IllegalStateException. Production cần alert, durable quarantine và xử lý conflict; không bỏ qua record hỏng rồi đánh dấu hoàn tất.

**Bài học chính:** replay lần hai có thể đọc lại nhiều events nhưng không nhất thiết phải tạo nhiều **document duy nhất**, nếu identity ổn định và sink có thiết kế idempotent.

## 9. Replay từ file và rotated logs

Với Logback RollingFileAppender, Log4j 2 RollingFile hoặc JUL FileHandler, dữ liệu có thể nằm ở file đang mở, file đã rotate, file nén hoặc archive. Một số nguyên tắc:

- **Ưu tiên đọc snapshot/archive ổn định** thay vì file live đang được ghi hoặc rotate.
- Chọn **file identity + offset**, không chỉ tên file. Cùng tên application.log có thể trỏ tới một inode/file khác sau rotation.
- Hiểu encoding UTF-8, line endings, multiline Java stack trace và JSON Lines. **Byte offset không tương đương số dòng**.
- Nhiều file theo ngày hoặc process không có thứ tự toàn cục; đừng nối tất cả bằng filename rồi giả định đúng thời gian event.
- Nếu file nén, cần giải nén/stream bằng công cụ có giới hạn kích thước và không ghi đè log gốc.
- Kiểm tra checksum của nguồn, kích thước, số lượng records dự kiến và khoảng timestamp.
- Cần phân biệt log bị **truncate** do rotate/copytruncate với file bị thiếu, tránh phát lại dữ liệu cũ hoặc bỏ qua đoạn mất.

### Filebeat registry

**Filebeat** lưu trạng thái đọc file trong **registry**, bao gồm vị trí harvester/offset. Khi output chưa ACK và process khởi động lại, Filebeat có thể gửi lại record đã từng đến sink; đó là một lý do dễ có duplicate trong cơ chế at-least-once.

**Không xóa hay sửa registry của Filebeat đang chạy production để “bắt đầu lại từ đầu”.** Việc đó có thể ảnh hưởng nhiều input, tạo duplicate lớn, thay live cursor và làm người vận hành khó khôi phục.

Để backfill, cân nhắc instance/config **riêng**, data path/registry riêng, include paths giới hạn vào archive read-only và output tới **index/namespace cách ly**. Đối chiếu hành vi filestream theo phiên bản, fingerprint và chính sách file identity; một file đã copy/đổi tên có thể hoặc không được nhận diện là mới theo cấu hình.

**At-least-once không bảo đảm còn mọi dữ liệu:** nếu file rotate và bị xóa trước khi shipper bắt kịp, nguồn đã mất và cần backup khác.

## 10. Replay với OpenTelemetry Collector filelog receiver

OpenTelemetry Collector Contrib có **filelog receiver** để tail và parse file. Một số phiên bản hỗ trợ cấu hình **start_at: beginning** hoặc **start_at: end** khi receiver khởi chạy.

Ví dụ **minh họa nguồn đọc cô lập**, cần ghép với exporter/pipeline của bản collector được triển khai và không phải cấu hình collector hoàn chỉnh:

~~~yaml
receivers:
  filelog/replay:
    include:
      - /archive/logs/order-service-2026-11-09.log
    start_at: beginning
    include_file_path: true
    encoding: utf-8
~~~

**Cảnh báo về offsets:** start_at: beginning nói về vị trí bắt đầu với file **chưa có state được phục hồi**. Theo tài liệu file input operator, nếu persistent storage đã có offsets của file thì trạng thái đã lưu có thể được ưu tiên; không giả định đổi một key start_at sẽ ép receiver đọc lại mọi bản ghi.

Một quy trình thận trọng:

1. Dùng một cấu hình/instance replay riêng, file archive chỉ đọc.
2. Bảo đảm storage/checkpoint của replay tách khỏi collector đang phục vụ live logs.
3. Cấu hình source/path/encoding phù hợp; nếu log multiline phải có operator đúng.
4. Định tuyến output vào sink mới, có giới hạn tài nguyên/batching.
5. Xác minh nguồn file, record count, parsed fields, lag và duplicate.
6. Không công bố dashboard mới hoặc đổi route production trước khi nghiệm thu.

Không mặc định mọi distribution của OTel Collector đều chứa filelog receiver: nó thuộc các distribution có tích hợp component tương ứng, như collector-contrib. Tên trường, version và processor cụ thể cần đối chiếu reference của bản đang chạy.

## 11. Kafka replay: group ID, partition và offsets

Kafka phù hợp để lưu dòng event/log theo topic có retention. Nhưng **offset là vị trí trong từng partition**, không phải ID nghiệp vụ và không có một thứ tự toàn cục trên topic nhiều partition.

Các đường replay thường dùng:

- Một **consumer group riêng** để đọc lại dữ liệu còn trong topic mà không ảnh hưởng cursor của group live.
- Dùng API **seek(TopicPartition, offset)** hoặc seekToBeginning(...) khi consumer đã được assign partition phù hợp.
- Xác định khoảng offset theo timestamp hoặc theo kết quả khảo sát cụ thể khi cần nạp bù một time range.
- Với group mới **chưa có committed offset**, auto.offset.reset=earliest có thể cho phép đọc từ earliest **còn được giữ** nếu không có offset.
- Với group đã có offset hợp lệ, chỉ thêm auto.offset.reset=earliest **không làm nó tự đọc lại từ đầu**.

Ví dụ **fragment Java Kafka consumer**, không độc lập; cần Apache Kafka Clients dependency, consumer đã được tạo và partition đã được assign:

~~~java
TopicPartition partition =
        new TopicPartition("app-logs", 0);

// Chỉ dùng trong replay consumer chuyên biệt đã được assign.
// startOffset phải được xác minh là còn tồn tại.
consumer.seek(partition, startOffset);

// poll() sẽ lấy dữ liệu từ vị trí được seek theo Kafka semantics.
ConsumerRecords<String, String> batch =
        consumer.poll(Duration.ofSeconds(1));
~~~

Không chạy fragment này trên live consumer với offset tự ý, vì có thể khiến group đang phục vụ production phát lại record hoặc bỏ sót dữ liệu. Sử dụng group replay riêng, principal được phân quyền đọc, topic allowlist và output cô lập.

**Retention là ranh giới thật:** "earliest" nghĩa là offset sớm nhất **còn lưu**, không phải offset 0 trong lịch sử. Với topic đã xóa dữ liệu cũ, cần archive/tiered storage/backups nếu hệ thống có hỗ trợ và phạm vi quyền phù hợp.

**Chế độ commit:** chỉ commit tiến độ replay sau khi xử lý tới mức ACK đã định; nếu commit trước khi sink lưu thì có thể bỏ mất event. Retry sau ACK bị mất có thể tạo duplicate; cần stable dedup key và cơ chế idempotent tại sink.

Đối với Kafka 4.x, tài liệu API/consumer config cần xem đúng phiên bản đang dùng; một số tuỳ chọn reset offset bổ sung có thể xuất hiện ở bản mới. Không dựng script dựa trên một phiên bản tài liệu cũ rồi áp nguyên vào cluster khác.

## 12. Elasticsearch/OpenSearch reindex: khác với đọc lại file log

Nếu dữ liệu **đã có trong index**, Elasticsearch cung cấp **Reindex API** để sao chép document từ index nguồn sang index đích khác; nó không tự đọc raw files. Một ví dụ request **chỉ để học**, không chạy trên hệ thống thật khi chưa kiểm tra names, permissions và mapping:

~~~http
POST /_reindex?wait_for_completion=false
Content-Type: application/json

{
  "source": {
    "index": "logs-orders-2026-11-09",
    "query": {
      "range": {
        "@timestamp": {
          "gte": "2026-11-09T00:00:00Z",
          "lt": "2026-11-10T00:00:00Z"
        }
      }
    }
  },
  "dest": {
    "index": "logs-orders-replay-20261110",
    "op_type": "create"
  },
  "conflicts": "proceed"
}
~~~

**Chú ý:**

- Source và destination phải khác nhau.
- Source cần _source được bật để reindex document như API yêu cầu.
- API **không tự sao chép settings và mappings**; nên tạo index đích với schema/template/retention đúng trước khi chạy.
- Với op_type=create, document đã có cùng ID ở đích sẽ gây version conflict thay vì overwrite. conflicts:proceed cho phép job tiếp tục trong những trường hợp conflict được quy định, nhưng **không có nghĩa mọi lỗi đều được bỏ qua**.
- Nếu destination là data stream append-only, cần tuân thủ semantics create-only.
- wait_for_completion=false trả về task ID nếu job được chấp nhận; **phải theo dõi task và kết quả cuối**, không coi phản hồi ban đầu là mọi document đã index.
- Thao tác có thể làm tăng tải cluster, cần throttling, batching, giám sát disk/CPU, shard failures và version conflicts.
- Muốn sửa dữ liệu đã parser sai, reindex vào index mới có thể cần ingest pipeline/script được kiểm soát; create-only không tự thay thế document đã tồn tại.

Với OpenSearch, API/fields và phiên bản có thể tương đồng nhưng phải kiểm tra tài liệu của bản cụ thể. Đừng giả định Elasticsearch và OpenSearch có hành vi giống hệt ở mọi tính năng.

## 13. Replay và parser/schema evolution

Một lý do lớn để replay là **sửa log parsing**. Ví dụ parser cũ xem durationMs là chuỗi "15ms", parser mới muốn số 15; hoặc multiline cũ chia Java stack trace thành nhiều records.

Khi reprocess:

1. Xác định **raw format/schema version** của nguồn từng giai đoạn. Không parse mọi file lịch sử bằng giả định encoder hôm nay.
2. Chọn parserVersion mới và lưu metadata replayRunId/processorVersion để truy vết.
3. Dùng **golden samples** gồm INFO/WARN/ERROR, Unicode, exception, null, JSON nested, malformed lines.
4. Giữ **event timestamp gốc** và source identity; tạo trường observedAt/replayedAt riêng.
5. Tách số **raw records**, số **logical events sau multiline**, số **parsed events**, số **rejected/quarantined**.
6. Kiểm tra mapping/index template và schema compatibility trước khi nạp lượng lớn.
7. So sánh các trường quan trọng: service, severity, requestId, traceId, eventCode, errorCode, thời gian.
8. Nếu thay đổi redaction, đảm bảo bản cũ vẫn được xử lý theo quyền dữ liệu và retention; replay không mở lại bí mật từ archive.

Nếu parser cũ đã loại mất các dòng stack trace và không còn raw file, parser mới **không tự phục hồi phần bị mất**. Việc replay chỉ có thể sử dụng dữ liệu còn tồn tại trong nguồn.

## 14. Replay phải cô lập các tác dụng phụ

Trong hệ thống production, nguy hiểm nhất là đưa dữ liệu cũ qua một pipeline vốn phát **alert, email, webhook, ticket, quyết định bảo mật hoặc command nghiệp vụ**.

~~~text
Old ERROR log -> replay -> live alert rule -> "sự cố mới"
Old AUDIT log -> replay -> automated workflow -> hành động lặp
Old event    -> replay -> side-effecting consumer -> ghi dữ liệu lần hai
~~~

Vì vậy:

- Tạo **index/namespace replay** và gắn replayRunId, sourceType=backfill theo policy.
- Tách replay ingest khỏi pipeline có action như email/webhook/ticket.
- Với dashboard alert, phân biệt event timestamp và replay ingest timestamp; có thể loại nguồn replay khỏi alert realtime cho tới khi dữ liệu được nghiệm thu.
- Với Kafka topic chứa **domain events**, đảm bảo consumer replay là **projection-only hoặc side-effect disabled**; không phát lại giao dịch/command.
- Không cập nhật production data lake/index gốc nếu chưa có kế hoạch cutover và rollback.
- Không để một replay job có quyền write/delete rộng hơn phạm vi đã duyệt.

Một log ERROR lịch sử không phải sự cố vừa xảy ra. Tuy nhiên không được làm mất dấu vết security/audit thật; sử dụng routing phù hợp và ghi nhận replay có thể phục vụ điều tra.

## 15. Quyền riêng tư, retention và legal hold

Replay có thể **đưa dữ liệu cá nhân đã bị xóa hoặc đã hết retention trở lại index**, nhất là sau restore backup. Cần bảo vệ điều đó giống như quy trình phục hồi dữ liệu.

Các câu hỏi trước replay:

- Dữ liệu trong source/archive có còn được phép xử lý theo mục đích hiện tại không?
- Dữ liệu cá nhân nào đã có yêu cầu xóa/khử nhận dạng? Có deletion ledger/tombstone cần áp dụng trước khi xuất vào đích không?
- Có legal hold hoặc nghĩa vụ giữ một số event không, và phạm vi cụ thể là gì?
- Đích mới có cùng policy masking, ACL, encryption, retention và giới hạn truy cập không?
- Có secret/token từng bị log nhầm trong bản cũ không? Nếu có, phải lọc/redact đúng trước khi ingest.
- Đã ghi nhận việc chia sẻ cho bên xử lý/collector ngoài tổ chức theo hợp đồng hay chưa?

**Không dùng replay làm cách vượt qua chính sách xóa**. Nếu index hiện tại đã xóa PII hợp lệ, việc nạp raw archive cũ mà không áp dụng deletion ledger có thể "hồi sinh" thông tin đó.

Tương tự, chỉ vì dữ liệu nằm trong log audit không có nghĩa nó có thể được phát tán tùy ý sang một hệ thống khác. Replay có mục đích mới vẫn cần căn cứ, phân quyền và retention phù hợp.

## 16. Batch, backpressure, cost và thời điểm vận hành

Một replay lớn có thể tạo tải mạnh hơn traffic live dù nguồn là dữ liệu cũ:

- CPU và heap cho JSON/Grok/multiline/redaction.
- Băng thông disk/network khi đọc archive và gửi collector.
- Queue và retry ở shipper, Kafka và exporter.
- Storage/index merge, shard allocation, disk watermark, search latency.
- Áp lực retention khi cùng dữ liệu được giữ thêm ở index replay.
- Phí cloud ingest, index, egress hoặc object retrieval.

Cần quy định:

| Điều khiển | Lợi ích |
| --- | --- |
| maxRecordsPerSecond hoặc bytes/s | Giới hạn tải replay |
| maxBatchSize | Giới hạn memory và request size |
| maxInflightBatches | Không dồn vô hạn backlog |
| Retry with backoff/jitter | Giảm tải khi sink chậm |
| Bounded queue / durable spool | Không mất kiểm soát memory |
| Pause/resume + checkpoint | Có thể dừng an toàn |
| Giám sát error/timeout | Phát hiện hỏng trước khi quá muộn |
| Separate replay capacity | Hạn chế tác động tới ingest live |

**Queue lớn không làm sink nhanh hơn**. Nếu accepted rate lớn hơn indexed rate trong thời gian dài, backlog tăng đến lúc đầy; cần giảm replay rate hoặc tăng năng lực đích.

Nên test một batch nhỏ trong giờ ít tải, đối chiếu số unique events và tốc độ, rồi tăng dần theo ngưỡng đã duyệt. Không nạp lại nhiều ngày ERROR với full stack trace vào index live khi cluster đang ở tình trạng disk gần đầy.

## 17. Metrics và dashboard dành riêng cho replay

Các metric hữu ích:

~~~text
replay_records_read_total{run,source}
replay_events_parsed_total{run,parser_version}
replay_events_rejected_total{run,error_code}
replay_events_inserted_total{run,destination}
replay_events_duplicate_total{run,destination}
replay_conflicts_total{run,destination}
replay_batches_failed_total{run,destination}
replay_bytes_read_total{run,source}
replay_checkpoint_offset{run,partition}
replay_backlog_records{run,source}
replay_ingest_latency_seconds{run,destination}
~~~

**Lưu ý cardinality:** nếu replayRunId là giá trị duy nhất được tạo quá thường xuyên, cần đánh giá chính sách label/retention; không cho eventId, requestId, userId hoặc raw message vào metric labels. Có thể lưu runId trong structured audit/log quản trị, dùng nhãn phân nhóm hữu hạn cho metrics chính.

Các chỉ số cần phân biệt:

- **Read:** bao nhiêu physical records được đọc từ nguồn?
- **Parsed:** bao nhiêu logical events hợp lệ sau multiline/validation?
- **Inserted:** bao nhiêu unique events mới lưu ở đích?
- **Duplicate:** bao nhiêu record khớp sự kiện đã có và được bỏ qua idempotently?
- **Conflict:** cùng ID nhưng khác payload hoặc destination version?
- **Rejected/quarantine:** bao nhiêu input chưa thể xử lý và còn chờ quyết định?
- **Lag:** chênh giữa event time và replay/ingest time; không nhầm lịch sử thành sự cố mới.
- **Checkpoint:** mỗi partition/file đã hoàn tất tới đâu?

Một phép kiểm tra cân đối ở **phạm vi đã xác định**:

~~~text
read_records
  = inserted + duplicates + filtered + rejected_or_quarantined
    + other_explicitly_accounted_outcomes
~~~

Công thức là một **bảng cân đối kết quả phân loại** khi mỗi record được tính đúng một nhánh, không phải đồng nhất tuyệt đối cho mọi pipeline. Một malformed multiline event có thể gồm nhiều dòng; vì thế phải thống nhất đang đếm **physical lines hay logical events**. Ghi rõ số đã durable-acknowledged, không chỉ accepted/enqueued.

## 18. Quy trình production runbook có kiểm soát

Một runbook khả thi:

### Giai đoạn A — Lập kế hoạch

1. Ghi incident/change ID, replayRunId, lý do, owner, thời gian và nguồn dữ liệu.
2. Xác định nguồn archive/backup/topic nào còn đủ, checksum và khả năng đọc.
3. Xác định phạm vi cụ thể theo source, tenant, service, file/partition, offset và UTC range.
4. Kiểm tra retention, legal hold, deletion requests, PII/secret và quyền đọc/ghi.
5. Định nghĩa stable event ID, dedup policy, conflict handling, parser version và expected schema.
6. Chọn destination **cách ly**, TTL/retention riêng và rollback/cutover plan.
7. Tạo giới hạn QPS/bytes, batch size, resource budget, checkpoint storage và điều kiện dừng.

### Giai đoạn B — Dry-run và thử nghiệm

8. Kiểm tra kết nối và quyền read-only của source, quyền ghi chỉ ở destination đã duyệt.
9. Chạy một phần rất nhỏ (canary) hoặc dry-run chỉ đếm/phân tích metadata.
10. Xác minh timestamp, severity, requestId, traceId, exception, multiline và redaction.
11. Đối chiếu expected count/hash với đầu ra, kiểm tra duplicate/conflict.
12. Đo tác động tới cluster live; xác minh không có side-effecting consumer/alert.

### Giai đoạn C — Replay có giám sát

13. Bắt đầu theo batch/partition, giữ cursor độc lập từng nguồn.
14. ACK durable theo semantics của sink trước checkpoint.
15. Theo dõi read/inserted/duplicate/rejected/backlog, throughput và latency.
16. Khi lỗi tăng hoặc đích quá tải, **pause** và điều tra; không tự tăng concurrency vô hạn.
17. Dừng đúng ranh giới snapshot/range đã định, không lấn sang log live mới.

### Giai đoạn D — Nghiệm thu và đóng việc

18. Đối chiếu counts, sampling, checksum/eventId, khoảng timestamp và trường quan trọng.
19. Xác minh các record bị conflict/quarantine được xử lý hoặc có lý do chưa xử lý.
20. Xác minh deletion ledger/retention/ACL và không kích hoạt nhầm alert nghiệp vụ.
21. Nếu cần cutover, chuyển alias/dashboard theo change plan; giữ khả năng rollback.
22. Lưu replay manifest, kết quả, phiên bản parser, checkpoint, lý do và người phê duyệt ở nơi quản trị phù hợp.
23. Dọn tài nguyên tạm và index replay theo retention đã duyệt, không xóa source gốc ngoài phạm vi.

**Đừng tuyên bố hoàn tất chỉ khi job trả HTTP 200 hoặc "submitted".** Nhiều đích chạy bất đồng bộ; cần đợi task completion và xác minh lại dữ liệu.

## 19. Kiểm thử replay và khả năng phục hồi

| Test case | Điều cần chứng minh |
| --- | --- |
| Replay lần đầu | Tập unique events xuất hiện đủ ở đích |
| Replay cùng dữ liệu lần hai | Không tăng document count ngoài chính sách |
| ACK bị mất rồi retry | Idempotency ngăn duplicate |
| Source có ID giống nhau nhưng payload khác | Conflict được phát hiện, không overwrite âm thầm |
| Checkpoint trước/sau ghi đích | Không bỏ record; retry xử lý đúng |
| Kafka nhiều partition | Offset/cursor riêng và ordering đúng từng partition |
| File rotate/truncate | Không nhảy sai file identity/offset |
| Java multiline exception | Một Throwable là một logical event, không hàng chục records |
| Parser cũ và mới | Field/timestamp map đúng, schema version rõ |
| Source thiếu dữ liệu do retention | Báo gap, không khẳng định khôi phục đủ |
| Collector timeout/429 | Backoff, pause, replay resume đúng |
| Data chứa PII/secret | Redaction và quyền truy cập vẫn được tuân thủ |
| Dữ liệu đã bị yêu cầu xóa | Không hồi sinh trong destination mới |
| Alert rule live | Log lịch sử không tạo ticket/call bất ngờ |
| Low disk/index mapping conflict | Job dừng có kiểm soát và báo lỗi |
| Restore replay state | Cursor/manifest được phục hồi theo thiết kế |
| Reindex async | Theo dõi task thực sự hoàn tất và kiểm tra destination |

Nên chuẩn bị fixture chứa cả log text, JSON, Unicode, stack trace, error code, requestId và eventId, nhưng **chỉ dùng dữ liệu tổng hợp**. Test đồng thời nhiều workers để thấy duplicate, race và ordering issues. Nếu có side-effecting consumer, phải có chế độ simulation/no-op được kiểm soát.

Khi unit test ở Java, ví dụ JDK trong bài chỉ chứng minh tính idempotent của Map trong bộ nhớ. Muốn nghiệm thu end-to-end, cần integration test với backend thật hoặc test container và một đích cách ly.

## 20. Những sai lầm nguy hiểm

**“Replay log nghĩa là chạy lại request.”** Không. Log quan sát ghi nhận điều đã xảy ra, không phải command có quyền tái thi hành nghiệp vụ.

**“Dùng auto.offset.reset=earliest là mọi Kafka consumer đều đọc lại.”** Sai nếu consumer group đã có committed offsets hợp lệ. Offset reset được áp dụng theo điều kiện cụ thể, và earliest chỉ là phần **dữ liệu còn giữ**.

**“Xóa registry Filebeat production để bắt đầu lại.”** Có thể làm hỏng tiến độ ingest live và nhân đôi log hàng loạt. Nên dùng replay reader/registry riêng.

**“start_at: beginning luôn bỏ qua checkpoint.”** Với filelog receiver, persisted offsets có thể được ưu tiên. Phải cô lập receiver storage và kiểm tra behavior theo phiên bản.

**“Log có cùng message nên là duplicate.”** Hai request độc lập có thể ghi câu ERROR giống nhau. Cần stable identity và phạm vi nguồn.

**“Một record đọc được = một document đã index.”** Parser, filter, dedup, quarantine, retry và indexing có các trạng thái khác nhau.

**“Reindex sẽ khôi phục log không tồn tại trong index.”** Reindex chỉ dùng documents của nguồn hiện hữu; cần file/archive khác để backfill dữ liệu chưa được ingest.

**“Reindex tự sao chép mappings và settings.”** Elasticsearch yêu cầu chuẩn bị đích; không thể dựa vào source schema tự xuất hiện đầy đủ.

**“Đặt op_type=create thì không bao giờ có duplicate.”** Nó tránh overwrite theo ID trong một ngữ cảnh API, nhưng phải có **ID ổn định**; nếu mỗi ingest sinh _id mới thì cùng sự kiện vẫn được lưu nhiều lần.

**“Replay cũ vào live index là vô hại.”** Có thể làm bùng disk, alert, chi phí ingest và làm lẫn event time với ingestion time.

**“Cứ tăng queue thì replay sẽ hoàn thành nhanh hơn.”** Queue hấp thụ burst, không tăng sustainable throughput của sink.

**“Tất cả dữ liệu trong backup đều có thể nạp trở lại.”** Không nhất thiết: retention, quyền xóa dữ liệu, legal hold và redaction phải được kiểm tra lại.

**“Đã thấy task accepted là hoàn tất.”** Cần job completion, per-batch acknowledgement, counts, conflicts và readback đích.

**“Sắp xếp theo timestamp là có thứ tự chính xác.”** Đồng hồ lệch, events cùng timestamp, Kafka nhiều partition và async delivery khiến không có thứ tự toàn cục đáng tin nếu không có sequence/ordering contract.

## 21. Checklist trước khi bấm chạy

- [ ] Có lý do, owner, approval và replayRunId.
- [ ] Nguồn còn dữ liệu trong thời gian yêu cầu; checksum/manifest đã được xác minh.
- [ ] Phạm vi service, tenant, UTC time, file/partition/offset được giới hạn.
- [ ] Phân biệt replay logs với replay domain events và side effects.
- [ ] Destination index/namespace **cách ly**, quyền ghi tối thiểu.
- [ ] Không chạm offset/registry của pipeline live.
- [ ] Biết eventId/dedup key ổn định và chiến lược xử lý conflict.
- [ ] Checkpoint được lưu sau ACK theo semantics của sink.
- [ ] Có retry/backoff, rate limit, bounded queue và pause/resume.
- [ ] Parser, multiline, schema, timezone và severity mapping được kiểm thử.
- [ ] Giữ event timestamp gốc, lưu replay metadata riêng.
- [ ] Không kích hoạt lại alert, webhook, command hoặc nghiệp vụ đã chạy.
- [ ] Có kiểm tra deletion ledger, PII/secret, retention, legal hold và ACL.
- [ ] Có metric read/parsed/inserted/duplicate/conflict/rejected/lag.
- [ ] Có canary/dry-run, nghiệm thu counts/IDs và lỗi từng batch.
- [ ] Có kế hoạch cutover/rollback và dọn tài nguyên sau khi hoàn tất.

**Kết luận:** Replay log trong **vận hành production** là một cách **đọc lại dữ liệu quan sát đã lưu** nhằm backfill, sửa parser hoặc tái dựng index. Nó an toàn khi xác định nguồn, phạm vi, identity, checkpoint, ranh giới ACK và đích rõ ràng; dùng idempotency để chống duplicate và cô lập replay khỏi tác dụng phụ của hệ thống live. **Replay không thể khôi phục dữ liệu không còn ở nguồn, không đảm bảo exactly-once chỉ bằng retry, và không được bỏ qua retention/quyền riêng tư.**

## 22. Tài liệu tham khảo

- [Apache Kafka Consumer Configuration](https://kafka.apache.org/44/configuration/consumer-configs/): auto.offset.reset, consumer groups và các tham số vận hành ở Kafka 4.4; đối chiếu đúng phiên bản thực tế.
- [Apache KafkaConsumer API](https://kafka.apache.org/44/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html): seek, seekToBeginning và hành vi offsets.
- [Elastic Filebeat — How Filebeat works](https://www.elastic.co/docs/reference/beats/filebeat/how-filebeat-works): registry, file identity, offsets và at-least-once delivery.
- [OpenTelemetry Collector Contrib — File Log Receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/receiver/filelogreceiver/README.md): filelog receiver, start_at, include, encoding và multiline.
- [OpenTelemetry Collector file input operator](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/pkg/stanza/docs/operators/file_input.md): persisted offsets có thể ưu tiên hơn start_at.
- [Elastic — Reindex API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-reindex): source/destination, _source, op_type, conflicts, task và mapping.
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/): phân biệt timestamp, observed timestamp, body, resource và attributes.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): file/rolling appenders và cơ chế xuất log.
- [Apache Log4j 2 — Appenders](https://logging.apache.org/log4j/2.x/manual/appenders.html): file và các đích xuất được hỗ trợ.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo mật, retention, giới hạn dữ liệu nhạy cảm và kiểm soát log.
- [Oracle Java SE 17 — Map.putIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#putIfAbsent(K,V)): semantics của ví dụ idempotent trong bộ nhớ.
