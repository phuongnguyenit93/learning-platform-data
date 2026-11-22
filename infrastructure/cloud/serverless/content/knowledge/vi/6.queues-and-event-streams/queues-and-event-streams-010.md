# Lập lịch tác vụ, múi giờ và xử lý lịch bị chạy trùng

Một hệ thống serverless thường cần chạy công việc theo thời gian: gửi báo cáo mỗi sáng, đồng bộ dữ liệu mỗi giờ, nhắc lịch trước một ngày hoặc đóng kỳ vào cuối tháng. Với Java function, dịch vụ lập lịch thường phát một event hoặc message để kích hoạt function. Function xử lý lần chạy đó rồi kết thúc; scheduler và queue chịu trách nhiệm duy trì lịch, giao công việc và retry.

Thiết kế lịch không chỉ là viết một biểu thức cron. Ứng dụng phải xác định thời điểm theo múi giờ nào, điều gì xảy ra khi giờ địa phương đổi do daylight saving time (DST), cách xử lý lần chạy bị trễ, và cách tránh xử lý hai lần khi scheduler hoặc queue giao lại cùng một occurrence. Các quyết định này ảnh hưởng trực tiếp đến tính đúng đắn của nghiệp vụ.

## 1. Phân biệt lịch một lần, lịch định kỳ và khoảng thời gian cố định

Có ba kiểu lập lịch thường gặp:

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| Một lần (one-time) | Chạy tại một thời điểm cụ thể | Gửi nhắc lịch lúc 2026-12-01T02:00:00Z |
| Định kỳ theo lịch (calendar-based) | Chạy theo ngày/tuần/tháng và giờ địa phương | Mỗi ngày lúc 09:00 theo giờ của khách hàng |
| Định kỳ theo khoảng (fixed interval) | Chạy sau mỗi khoảng thời gian xác định | Cứ 15 phút tạo một lần đồng bộ |

Không nên đánh đồng lịch mỗi ngày lúc 09:00 với lịch cách nhau đúng 24 giờ. Một ngày theo lịch có thể dài 23 hoặc 25 giờ ở vùng có DST. Lịch theo giờ địa phương cần giữ giờ tường (wall-clock time), còn lịch theo khoảng cố định thường được tính trên trục thời gian tuyệt đối.

Ví dụ:

- “Mỗi ngày lúc 09:00 tại Paris” là lịch calendar-based, gắn với múi giờ Europe/Paris.
- “Cứ sau đúng 24 giờ” là khoảng Duration 24 giờ, không bảo đảm luôn rơi vào 09:00 địa phương.
- “Mỗi 15 phút kể từ thời điểm bắt đầu” là lịch fixed interval.
- “Vào 00:00 ngày đầu mỗi tháng” là lịch calendar-based; không thể thay bằng một số ngày cố định.

Hãy viết yêu cầu nghiệp vụ trước khi chọn cron hoặc rate expression. Những từ như “mỗi ngày”, “mỗi 24 giờ”, “ngày làm việc”, “cuối tháng” và “theo giờ người dùng” có ý nghĩa khác nhau.

## 2. Scheduler, queue và Java function phối hợp như thế nào?

Scheduler quản lý thời điểm đến hạn. Khi occurrence đến hạn, scheduler phát event hoặc gửi message vào queue. Queue lưu công việc để worker function nhận và xử lý. Cách tổ chức này tách việc xác định thời gian khỏi việc thực thi nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant Q as Queue
    participant F as Java Function
    participant D as Database
    S->>Q: Phát event của occurrence
    Q->>F: Giao message
    F->>D: Kiểm tra / claim occurrence
    D-->>F: Cho phép xử lý hoặc đã xử lý
    F->>D: Ghi kết quả và trạng thái
    F-->>Q: Xác nhận message
~~~

Các thành phần có trách nhiệm riêng:

- **Scheduler:** lưu lịch, tính occurrence tiếp theo, phát event khi đến hạn và retry theo chính sách của dịch vụ.
- **Queue:** giữ message, phân phối cho worker, quản lý visibility/acknowledgement và có thể giao lại khi worker lỗi.
- **Java function:** xác thực event, kiểm tra occurrence, thực hiện nghiệp vụ, ghi trạng thái và xác nhận message theo giao thức.
- **Database hoặc kho trạng thái:** lưu lịch, lần chạy, idempotency key, checkpoint và kết quả nghiệp vụ.

Không nên dùng một thread trong Java function để ngủ đến giờ chạy. Execution environment có thể bị đóng băng hoặc thu hồi; function có thể scale về 0; và nhiều instance có thể cùng tạo lịch trùng. Một ScheduledExecutorService trong process chỉ phù hợp với tác vụ nội bộ có vòng đời của process, không thay thế scheduler bền vững cho hệ thống serverless.

Scheduler cũng không phải đồng hồ đảm bảo function bắt đầu chính xác tuyệt đối ở giây đã định. Có thể có độ trễ do tải, retry, queue backlog, giới hạn concurrency hoặc sự cố dịch vụ. Ứng dụng nên phân biệt thời điểm dự kiến với thời điểm thực tế.

## 3. Lưu thời gian đúng cách

### 3.1. Instant, LocalDateTime và ZonedDateTime

Java cung cấp các kiểu thời gian khác nhau cho những mục đích khác nhau:

| Kiểu | Biểu diễn | Khi nào dùng |
|---|---|---|
| Instant | Một điểm duy nhất trên trục thời gian UTC | Thời điểm thực thi, event timestamp, log và lưu occurrence |
| LocalDateTime | Ngày và giờ địa phương, không có múi giờ | Giờ người dùng nhập, ví dụ 09:00 ngày 1/12 |
| LocalDate | Một ngày lịch, không có giờ hoặc múi giờ | Ngày thanh toán hoặc ngày nghỉ |
| ZoneId | Quy tắc múi giờ, ví dụ Asia/Ho_Chi_Minh | Xác định giờ địa phương theo quy tắc vùng |
| ZonedDateTime | Ngày giờ địa phương kèm ZoneId và offset được áp dụng | Tính và hiển thị một occurrence theo vùng |

Một Instant luôn xác định được một thời điểm duy nhất. LocalDateTime thì không: 09:00 ngày 1/12 có thể tương ứng với các Instant khác nhau tùy múi giờ. Vì vậy, không lưu giờ địa phương như một chuỗi “09:00” rồi giả định mọi server hiểu giống nhau.

Với lịch một lần, thường lưu Instant đã được xác định. Với lịch định kỳ theo giờ địa phương, lưu cả quy tắc lặp và ZoneId, ví dụ:

~~~text
schedule_id: monthly-report-tenant-42
recurrence: 0 9 1 * *
zone_id: Europe/Paris
misfire_policy: COALESCE
overlap_policy: SKIP_IF_RUNNING
enabled: true
~~~

Ví dụ chỉ minh họa cấu trúc dữ liệu; cú pháp cron và tên policy phải khớp với scheduler thực tế. Nếu chỉ lưu offset như +01:00, ứng dụng sẽ không biết quy tắc DST và thay đổi múi giờ trong tương lai.

### 3.2. Dùng ZoneId thay cho offset cố định

ZoneId dựa trên cơ sở dữ liệu múi giờ IANA, chứa quy tắc lịch sử và các thay đổi đã được công bố. Một vùng như Europe/Paris có thể chuyển offset theo mùa; Asia/Ho_Chi_Minh hiện dùng quy tắc khác. Không nên tự cộng hoặc trừ một số giờ cố định để chuyển đổi giữa UTC và giờ địa phương.

Ví dụ chuyển một Instant sang giờ địa phương:

~~~java
Instant scheduledAt = Instant.parse("2026-12-01T08:00:00Z");
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime localTime = scheduledAt.atZone(zone);
System.out.println(localTime);
~~~

Để lập lịch theo giờ người dùng, hãy lưu ZoneId mà người dùng đã chọn. Nếu người dùng thay đổi nơi cư trú hoặc timezone trong hồ sơ, cần xác định lịch hiện tại có đổi theo hay giữ nguyên vùng đã chọn khi tạo lịch. Đây là quyết định nghiệp vụ, không nên tự động suy ra từ timezone của máy chủ.

### 3.3. Không dùng timezone mặc định của máy chủ

Timezone mặc định có thể khác giữa máy phát triển, container, môi trường cloud và các region. Code gọi LocalDateTime.now() hoặc ZoneId.systemDefault() có thể tạo kết quả khác khi triển khai ở môi trường khác.

Hãy truyền Clock hoặc ZoneId rõ ràng vào lớp nghiệp vụ. Với log và lưu thời điểm thực tế, ưu tiên Instant. Với lịch theo giờ địa phương, dùng ZoneId được lưu trong cấu hình schedule. Khi kiểm thử, dùng Clock cố định thay vì phụ thuộc đồng hồ thật.

## 4. Daylight saving time: giờ bị thiếu và giờ bị lặp

Ở vùng có DST, đồng hồ địa phương có thể nhảy tiến hoặc lùi. Điều này tạo ra hai tình huống mà lịch định kỳ phải xử lý rõ ràng.

### 4.1. Khoảng giờ bị thiếu (DST gap)

Khi đồng hồ chuyển từ 01:59 sang 03:00, các giờ từ 02:00 đến trước 03:00 không tồn tại trong ngày đó. Một lịch “chạy lúc 02:30” không có thời điểm địa phương hợp lệ.

Ứng dụng phải chọn chính sách:

- Bỏ qua occurrence của ngày đó.
- Chạy ngay tại thời điểm hợp lệ đầu tiên sau khoảng gap, ví dụ 03:00.
- Dịch chuyển theo độ dài gap, ví dụ 02:30 thành 03:30.
- Dùng quy tắc riêng của scheduler hoặc thư viện cron.

Không có một cách đúng cho mọi nghiệp vụ. Báo cáo có thể chấp nhận chạy trễ một giờ; nhắc lịch có thể cần gửi vào thời điểm hợp lệ gần nhất; xử lý thanh toán có thể cần quy tắc chặt hơn.

### 4.2. Khoảng giờ bị lặp (DST overlap)

Khi đồng hồ chuyển lùi, một khoảng giờ địa phương xuất hiện hai lần. Ví dụ, 02:30 có thể tương ứng với hai Instant khác nhau và hai UTC offset khác nhau.

Ứng dụng phải quyết định:

- Chỉ chạy ở lần xuất hiện đầu tiên.
- Chỉ chạy ở lần xuất hiện thứ hai.
- Chạy ở cả hai lần.
- Chọn một occurrence duy nhất theo ngày địa phương và bỏ qua lần còn lại.

Nếu hệ thống cần một lần chạy cho mỗi ngày địa phương, idempotency key có thể dựa trên schedule ID và ngày lịch. Nếu nghiệp vụ muốn chạy ở cả hai thời điểm vật lý, khóa phải phân biệt hai Instant hoặc offset.

### 4.3. Kiểm tra DST bằng ZoneRules trong Java

Java Time API cho phép xem một LocalDateTime có bao nhiêu offset hợp lệ trong một ZoneId:

- Không có offset hợp lệ: giờ địa phương nằm trong DST gap.
- Có một offset: thời điểm không mơ hồ.
- Có hai offset: giờ địa phương nằm trong DST overlap.

Ví dụ sau minh họa chính sách: trong gap, dịch đến thời điểm hợp lệ đầu tiên sau gap; trong overlap, chọn lần sớm hoặc lần muộn theo cấu hình.

~~~java
enum OverlapPolicy {
    EARLIER,
    LATER
}

static ZonedDateTime resolveLocalTime(
        LocalDate date,
        LocalTime time,
        ZoneId zone,
        OverlapPolicy overlapPolicy) {

    LocalDateTime local = LocalDateTime.of(date, time);
    ZoneRules rules = zone.getRules();
    List<ZoneOffset> offsets = rules.getValidOffsets(local);

    if (offsets.size() == 1) {
        return ZonedDateTime.ofLocal(local, zone, offsets.get(0));
    }

    if (offsets.isEmpty()) {
        ZoneOffsetTransition transition = rules.getTransition(local);
        return transition.getDateTimeAfter().atZone(zone);
    }

    ZoneOffset selected = overlapPolicy == OverlapPolicy.EARLIER
            ? offsets.get(0)
            : offsets.get(offsets.size() - 1);

    return ZonedDateTime.ofLocal(local, zone, selected);
}
~~~

Đoạn mã cần các import từ java.time, java.time.zone và java.util. Nó thể hiện một policy cụ thể; ứng dụng cần bổ sung lựa chọn skip hoặc shift theo nghiệp vụ nếu các cách trên chưa phù hợp.

Không nên tự viết phép cộng offset bằng tay. Hãy dùng ZoneRules để xử lý quy tắc của vùng. Cũng cần kiểm tra phiên bản timezone database trên runtime và scheduler: quy định giờ mùa hè có thể thay đổi do quyết định hành chính.

## 5. Cron, rate expression và lịch theo lịch dân sự

Cron thường mô tả các trường thời gian như phút, giờ, ngày trong tháng, tháng và thứ trong tuần. Nhưng cron không có một dialect duy nhất. Các scheduler có thể khác nhau về:

- Có hoặc không có trường giây.
- Cách viết ngày trong tháng và thứ trong tuần.
- Ký hiệu cho “không chỉ định” hoặc “ngày cuối tháng”.
- Cách xử lý đồng thời ngày trong tháng và thứ trong tuần.
- Cách chỉ định timezone.
- Hành vi khi occurrence rơi vào DST gap hoặc overlap.

Không sao chép biểu thức cron từ hệ thống này sang hệ thống khác mà chưa kiểm tra tài liệu. Hãy validate biểu thức ở thời điểm tạo lịch và lưu rõ timezone cùng phiên bản policy.

Một số ví dụ mang tính khái niệm:

| Yêu cầu | Biểu thức hoặc cách mô tả |
|---|---|
| Mỗi ngày lúc 09:00 | Cron theo giờ và phút, gắn ZoneId |
| Thứ Hai đến thứ Sáu lúc 08:30 | Cron theo ngày trong tuần, gắn ZoneId |
| Mỗi 15 phút | Rate/fixed interval hoặc cron theo phút |
| Ngày đầu tháng lúc 00:00 | Cron theo ngày trong tháng |
| Sau đúng 24 giờ kể từ lần trước | Fixed interval trên Instant |

Với lịch calendar-based, scheduler thường tính occurrence theo lịch và timezone. Với fixed interval, hãy xác định interval được tính từ thời điểm bắt đầu, từ lần dự kiến trước hay sau khi lần trước hoàn tất. Ba cách này có thể tạo ra kết quả khác nhau khi function chạy lâu hoặc bị trễ.

## 6. Misfire: điều gì xảy ra khi lịch bị bỏ lỡ?

Misfire là occurrence đã đến hạn nhưng không được kích hoạt đúng lúc. Nguyên nhân có thể là scheduler gián đoạn, queue không sẵn sàng, function bị throttled, concurrency đạt giới hạn hoặc hệ thống tạm ngừng trong lúc bảo trì.

Khi hoạt động trở lại, hệ thống cần chính sách rõ ràng:

| Chính sách | Hành vi | Phù hợp khi |
|---|---|---|
| Catch up all | Phát tất cả occurrence bị lỡ | Mỗi kỳ đều cần xử lý, ví dụ tạo bản ghi kế toán theo từng ngày |
| Coalesce | Gộp nhiều occurrence bị lỡ thành một lần chạy | Chỉ cần trạng thái mới nhất, ví dụ đồng bộ snapshot |
| Skip missed | Bỏ qua occurrence cũ và chờ lần kế tiếp | Công việc cũ không còn giá trị |
| Expire after deadline | Chỉ chạy nếu chưa quá hạn cho phép | Nhắc lịch hoặc ưu đãi có thời hạn |
| Manual recovery | Đưa occurrence vào hàng chờ xử lý thủ công | Tác vụ có rủi ro nghiệp vụ cao |

Catch up all có thể tạo ra một đợt tải lớn sau sự cố. Nếu có 30 lần chạy bị lỡ và tất cả được phát cùng lúc, function, database và API bên ngoài có thể quá tải. Khi chọn catch-up, hãy giới hạn tốc độ phát lại, batch size và concurrency.

Không phải scheduler nào cũng cung cấp đầy đủ các chế độ misfire trên. Một số dịch vụ bỏ qua occurrence khi đích không khả dụng, một số retry trong thời gian giới hạn, và một số chỉ bảo đảm phát event trong một cửa sổ nhất định. Hãy kiểm tra hợp đồng của nhà cung cấp. Nếu nghiệp vụ bắt buộc phải xử lý mọi kỳ, lưu lịch occurrence hoặc watermark ở kho bền vững để worker có thể đối chiếu và tạo lại phần còn thiếu.

Coalesce cần xác định cách gộp. Có thể chỉ giữ occurrence mới nhất, hoặc tạo một job bao phủ khoảng thời gian bị lỡ. Không được gộp nếu mỗi occurrence đại diện cho một nghĩa vụ riêng, chẳng hạn một hóa đơn hoặc một kỳ thanh toán.

Một scheduler event nên mang theo thời điểm dự kiến của occurrence. Worker dùng thời điểm đó để xác định công việc thuộc kỳ nào, không dùng thời điểm nhận message làm kỳ nghiệp vụ. Nếu worker nhận event trễ, thời điểm thực tế không được làm thay đổi định danh occurrence.

## 7. Vì sao lịch có thể chạy trùng?

Một lịch bị chạy trùng không nhất thiết là lỗi của scheduler. Duplicate có thể xuất hiện ở nhiều lớp:

- Scheduler phát lại event sau khi không nhận được xác nhận.
- Queue giao lại message khi worker timeout hoặc không xác nhận kịp.
- Function hoàn thành side effect nhưng lỗi trước khi message được acknowledge.
- Hai lịch khác nhau vô tình cùng đại diện một nghiệp vụ.
- Người vận hành tạo lịch mới mà không vô hiệu hóa lịch cũ.
- Hai function instance cùng nhận hoặc cùng xử lý một occurrence.
- Một lần chạy trước còn kéo dài khi occurrence tiếp theo đã đến hạn.
- Catch-up phát lại occurrence cũ sau thời gian gián đoạn.

Trong hệ thống phân tán, không thể giả định “mỗi lịch chỉ chạy đúng một lần”. Scheduler và queue thường ưu tiên khả năng giao lại để tránh mất công việc. Worker phải chấp nhận duplicate và bảo đảm xử lý idempotent.

### 7.1. Không dùng thời điểm nhận message làm idempotency key

Giả sử cùng occurrence được giao lúc 09:00:01 và retry lúc 09:00:20. Nếu key được tạo bằng thời điểm nhận, hai lần giao có hai key khác nhau và cùng thực hiện nghiệp vụ.

Hãy dùng định danh ổn định của lần chạy dự kiến, ví dụ:

~~~text
occurrence_key = schedule_id + ":" + scheduled_at_utc
~~~

Nếu policy nghiệp vụ là một lần mỗi ngày địa phương, có thể dùng schedule ID và LocalDate. Nếu muốn chạy cả hai occurrence của giờ bị lặp trong DST overlap, phải dùng Instant hoặc offset để phân biệt chúng.

Event nên mang các trường như:

~~~json
{
  "scheduleId": "daily-report-tenant-42",
  "occurrenceId": "daily-report-tenant-42:2026-12-01T08:00:00Z",
  "scheduledAt": "2026-12-01T08:00:00Z",
  "scheduleVersion": 3
}
~~~

Đây là payload minh họa. Event ID của nhà cung cấp có thể hữu ích để theo dõi lần giao, nhưng không nhất thiết là định danh occurrence nghiệp vụ. Nhiều lần giao lại có thể có delivery ID khác nhau nhưng vẫn thuộc cùng một scheduled occurrence.

## 8. Idempotency và lưu trạng thái occurrence

### 8.1. Tạo bản ghi occurrence có khóa duy nhất

Một cách phổ biến là lưu mỗi occurrence vào bảng trạng thái với unique key gồm schedule ID và occurrence ID hoặc scheduled instant.

Ví dụ cấu trúc khái niệm:

| Trường | Mục đích |
|---|---|
| schedule_id | Định danh lịch |
| occurrence_id | Định danh lần chạy dự kiến |
| scheduled_at | Instant dự kiến |
| status | PENDING, RUNNING, SUCCEEDED, FAILED hoặc CANCELLED |
| attempt_count | Số lần thử |
| lease_owner | Worker đang giữ quyền xử lý |
| lease_until | Thời điểm hết hạn lease |
| fencing_token | Số thứ tự quyền sở hữu tăng dần |
| completed_at | Thời điểm hoàn tất |

Tạo occurrence bằng thao tác insert có unique constraint. Nếu insert thất bại vì khóa đã tồn tại, worker đọc trạng thái hiện tại để quyết định bỏ qua, retry hoặc tiếp tục phục hồi. Không chỉ dựa vào một câu SELECT rồi INSERT riêng biệt; hai worker có thể cùng đọc “chưa tồn tại” trước khi cả hai insert.

### 8.2. Ví dụ Java với occurrence store

Ví dụ dùng record, có trong Java 16 trở lên. Các kiểu ScheduledEvent và implementation của OccurrenceStore là thành phần ứng dụng cần định nghĩa.

~~~java
public record OccurrenceKey(
        String scheduleId,
        Instant scheduledAt
) {}

public record OccurrenceClaim(
        boolean acquired,
        long fencingToken
) {}

public interface OccurrenceStore {
    OccurrenceClaim claim(OccurrenceKey key);
    void markSucceeded(OccurrenceKey key, long fencingToken);
    void markRetryableFailure(
            OccurrenceKey key,
            long fencingToken,
            String reason
    );
}

void handleScheduledEvent(ScheduledEvent event) throws Exception {
    OccurrenceKey key = new OccurrenceKey(
            event.scheduleId(),
            event.scheduledAt()
    );

    OccurrenceClaim claim = occurrenceStore.claim(key);
    if (!claim.acquired()) {
        return;
    }

    try {
        runBusinessWork(event);
        occurrenceStore.markSucceeded(key, claim.fencingToken());
    } catch (Exception error) {
        occurrenceStore.markRetryableFailure(
                key,
                claim.fencingToken(),
                error.getClass().getSimpleName()
        );
        throw error;
    }
}
~~~

Đây là ví dụ kiến trúc; implementation của claim phải là thao tác nguyên tử trong kho bền vững. Nó cần phân biệt occurrence đã hoàn tất với occurrence đang chạy bởi worker khác và occurrence có lease hết hạn. Nếu mọi bản ghi đã tồn tại đều bị bỏ qua, worker sẽ không thể tiếp tục một occurrence bị lỗi giữa chừng.

Nếu nghiệp vụ gồm nhiều side effect, chẳng hạn ghi database rồi gửi email, một lần claim không thể tự tạo exactly-once cho cả hai hệ thống. Hãy ghi trạng thái nghiệp vụ và outbox trong cùng transaction, sau đó publisher gửi email với idempotency key. Receiver hoặc dịch vụ gửi email cần hỗ trợ deduplication nếu yêu cầu không gửi trùng là bắt buộc.

### 8.3. Lease và fencing token

Một worker có thể chết khi đang xử lý. Nếu trạng thái RUNNING không có cơ chế hết hạn, occurrence sẽ bị kẹt mãi. Lease cho phép worker giữ quyền xử lý đến một thời điểm; nếu lease hết hạn, worker khác có thể claim lại.

Tuy nhiên, lease đơn lẻ chưa đủ. Worker cũ có thể bị tạm dừng lâu, lease hết hạn và worker mới đã claim. Khi worker cũ chạy tiếp, cả hai có thể ghi dữ liệu. Fencing token là số tăng dần mỗi lần claim. Mọi thao tác ghi kết quả cần kiểm tra token hiện tại; token cũ không được phép ghi đè kết quả của worker mới.

Lease cần được gia hạn (heartbeat) nếu công việc dài. Thời gian lease nên lớn hơn khoảng heartbeat và phù hợp với timeout invocation. Khi function sắp hết deadline, nó nên dừng ở checkpoint hoặc nhường quyền theo giao thức đã thiết kế.

## 9. Xử lý các occurrence đến gần nhau

Nếu tác vụ chạy lâu hơn chu kỳ lịch, hai occurrence có thể chồng lấn. Ví dụ, báo cáo được lên lịch mỗi 10 phút nhưng lần chạy trước mất 18 phút.

Cần chọn một chính sách:

- **Allow overlap:** cho phép nhiều occurrence chạy đồng thời. Chỉ phù hợp khi các lần chạy độc lập và dependency chịu được tải.
- **Skip if running:** bỏ qua occurrence mới nếu lần trước còn chạy.
- **Queue:** giữ occurrence mới để chạy sau.
- **Coalesce:** gộp nhiều occurrence đang chờ thành một lần xử lý.
- **Replace/cancel previous:** hủy hoặc thay thế lần trước nếu nghiệp vụ cho phép.

Chính sách phải được xác định theo schedule hoặc loại công việc. Không dùng một cờ boolean trong memory để khóa vì nhiều execution environment không chia sẻ trạng thái. Dùng database transaction, distributed lock hoặc cơ chế concurrency của scheduler/queue.

Nếu dùng queue, visibility timeout hoặc acknowledgement deadline phải phù hợp với thời gian xử lý. Nếu message trở nên visible khi worker cũ vẫn đang chạy, queue có thể giao cùng message cho worker thứ hai. Cấu hình thời gian quá dài lại làm chậm retry khi worker thực sự chết. Có thể gia hạn visibility trong khi xử lý nếu dịch vụ hỗ trợ, nhưng idempotency vẫn cần thiết.

## 10. Quản lý thay đổi lịch và phiên bản schedule

Lịch có thể được tạo, sửa, tạm dừng hoặc xóa trong khi occurrence đang được phát hoặc xử lý. Hãy lưu schedule ID ổn định và version tăng dần mỗi lần thay đổi cấu hình.

Cần xác định:

- Occurrence đã phát theo version cũ có tiếp tục được xử lý không?
- Thay đổi timezone có áp dụng ngay hay từ occurrence tiếp theo?
- Đổi giờ chạy có làm hủy occurrence đã lên lịch không?
- Xóa lịch có xóa cả job đang chạy không?
- Nếu vô hiệu hóa rồi bật lại, occurrence bị bỏ lỡ được catch up hay skip?
- Khi đổi cron, làm sao tránh scheduler cũ và mới cùng phát một occurrence?

Một cách triển khai là lưu version trong event và trong occurrence record. Worker kiểm tra version cùng chính sách hiệu lực. Khi cập nhật lịch, dùng một transaction hoặc quy trình có trạng thái để tạo schedule version mới, vô hiệu hóa version cũ và xử lý các occurrence đang chờ. Không chỉ dựa vào tên hiển thị của lịch để phân biệt phiên bản.

## 11. Bảo mật và quyền của scheduled event

Scheduler thường gọi queue hoặc function bằng service identity. Chỉ cấp quyền publish vào đúng queue hoặc invoke đúng function cần thiết. Worker chỉ nên đọc message từ queue và truy cập các tài nguyên nghiệp vụ cần cho công việc.

Đừng coi payload của scheduler là dữ liệu đáng tin cậy tuyệt đối. Worker vẫn cần:

- Xác minh schema và version của event.
- Kiểm tra schedule ID có tồn tại và đang được phép chạy.
- Kiểm tra tenant và quyền truy cập từ dữ liệu đã xác thực.
- Từ chối trường tenant hoặc resource ID không hợp lệ.
- Không cho event tùy ý chỉ định URL hoặc lệnh cần thực thi.
- Không đưa secret vào message; dùng secret manager hoặc service identity.
- Ghi audit cho thay đổi lịch, người tạo, người sửa và lần chạy thủ công.

Nếu có endpoint cho phép người dùng tạo lịch, cần giới hạn số lịch mỗi tenant, tần suất tối thiểu, thời gian chạy xa nhất và loại recurrence được hỗ trợ. Nếu không, một tài khoản có thể tạo hàng triệu lịch hoặc đặt lịch chạy mỗi giây để gây cạn tài nguyên.

## 12. Quan sát độ trễ, duplicate và misfire

Một hệ thống lập lịch cần phân biệt ít nhất ba thời điểm:

- **scheduledAt:** thời điểm occurrence dự kiến.
- **receivedAt:** thời điểm worker nhận event hoặc message.
- **startedAt:** thời điểm bắt đầu xử lý nghiệp vụ.

Từ đó có thể tính schedule lag = receivedAt - scheduledAt và queue wait = startedAt - receivedAt. Theo dõi thêm thời gian xử lý, thời điểm hoàn tất và số lần retry.

Metric hữu ích gồm:

- Số occurrence dự kiến, phát thành công và bị lỡ.
- Schedule lag p50/p95/p99.
- Tuổi message cũ nhất trong queue.
- Số duplicate event và số lần idempotency từ chối xử lý lại.
- Số occurrence đang RUNNING quá lease.
- Số lần lease hết hạn, claim lại và fencing conflict.
- Số job catch-up, coalesce, skip và expire.
- Tỷ lệ thành công, retry, DLQ và thời gian xử lý.
- Số lịch đang hoạt động theo tenant và số lần thay đổi schedule.

Log nên chứa schedule ID, schedule version, occurrence ID, scheduledAt, delivery ID, attempt count và correlation ID. Không log token, secret hoặc payload nhạy cảm. Khi có sự cố, các trường này giúp phân biệt scheduler phát trùng, queue giao lại và worker tự tạo duplicate.

## 13. Kiểm thử lịch và múi giờ

Không chỉ kiểm tra lịch trong một ngày bình thường. Hãy kiểm thử:

1. Lịch một lần tại thời điểm UTC cụ thể.
2. Lịch mỗi ngày theo timezone có DST.
3. Local time rơi vào DST gap.
4. Local time rơi vào DST overlap.
5. Thay đổi timezone của lịch khi occurrence đang chờ.
6. Scheduler phát trễ sau thời gian gián đoạn.
7. Nhiều occurrence bị lỡ và catch-up cùng lúc.
8. Hai worker nhận cùng occurrence gần như đồng thời.
9. Worker chết sau side effect nhưng trước acknowledgement.
10. Lease hết hạn trong khi worker cũ còn chạy.
11. Lần chạy trước kéo dài qua occurrence kế tiếp.
12. Lịch bị tạo hai lần hoặc version cũ vẫn phát event.
13. Queue visibility timeout ngắn hơn thời gian xử lý.
14. Tenant đạt quota số lịch hoặc tần suất tối thiểu.

Dùng Clock cố định để kiểm thử logic thời gian. Kiểm tra ZoneRules cho những ngày có chuyển DST thay vì chờ đến đúng ngày đó trong môi trường thật. Khi chạy integration test, xác minh cron dialect và timezone behavior của scheduler đang dùng.

## 14. Quy trình thiết kế một lịch bền vững

1. **Làm rõ ý nghĩa thời gian.** Lịch theo giờ địa phương, theo UTC hay theo khoảng thời gian tuyệt đối?
2. **Chọn ZoneId.** Lưu tên vùng IANA và quy tắc DST; không dựa vào timezone mặc định của process.
3. **Định nghĩa occurrence.** Tạo định danh ổn định từ schedule ID và scheduled instant hoặc ngày nghiệp vụ.
4. **Chọn misfire policy.** Catch up, coalesce, skip, expire hay manual recovery.
5. **Chọn overlap policy.** Cho phép song song, skip, queue hay coalesce khi lần trước chưa xong.
6. **Thiết kế idempotency.** Unique constraint, occurrence store, trạng thái và lease/fencing nếu cần.
7. **Đặt retry và DLQ.** Giới hạn số lần thử, backoff và quy trình phục hồi.
8. **Kiểm soát quyền.** Giới hạn quyền scheduler, queue, worker và người tạo lịch.
9. **Đo độ trễ và duplicate.** Theo dõi scheduledAt, receivedAt, startedAt và kết quả.
10. **Kiểm thử DST và sự cố.** Mô phỏng gap, overlap, backlog, worker crash và chạy đồng thời.

Lịch bền vững cần được xem như một luồng phát sinh công việc có định danh. Scheduler quyết định khi nào một occurrence đến hạn; queue đảm bảo công việc được chuyển đến worker; Java function xử lý idempotent và ghi trạng thái để có thể retry hoặc phục hồi.

## 15. Câu hỏi tự kiểm tra

- Vì sao “mỗi ngày lúc 09:00” khác “mỗi 24 giờ”?
- Instant, LocalDateTime và ZonedDateTime khác nhau như thế nào?
- DST gap và DST overlap ảnh hưởng lịch định kỳ ra sao?
- Vì sao cần lưu ZoneId thay vì chỉ lưu offset?
- Misfire policy catch-up all có thể tạo ra rủi ro gì sau sự cố?
- Vì sao delivery ID của queue không luôn phù hợp làm occurrence ID?
- Làm thế nào để hai worker đồng thời không xử lý cùng một occurrence?
- Vì sao lease cần fencing token khi worker cũ có thể chạy lại?
- Nên làm gì khi lần chạy trước kéo dài qua occurrence kế tiếp?
- Làm thế nào để thay đổi lịch mà không phát đồng thời từ version cũ và mới?

Nắm được lập lịch, múi giờ và duplicate giúp người phát triển Java serverless xây dựng công việc định kỳ có thể phục hồi. Hãy xác định rõ ý nghĩa của từng occurrence, lưu thời gian bằng kiểu phù hợp, chọn chính sách cho DST và misfire, đồng thời thiết kế worker idempotent để việc retry không tạo hiệu ứng nghiệp vụ lặp.

