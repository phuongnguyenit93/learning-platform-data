# Phân biệt thời điểm xử lý với thời điểm có hiệu lực nghiệp vụ

Trong Domain-Driven Design (DDD), thời gian không chỉ là một thuộc tính kỹ thuật để ghi log. Nhiều quy tắc nghiệp vụ phụ thuộc vào câu hỏi một sự kiện xảy ra lúc nào, hệ thống tiếp nhận hoặc xử lý nó lúc nào, và thay đổi đó có hiệu lực đối với nghiệp vụ từ thời điểm nào.

Ba thời điểm này có thể khác nhau. Một hợp đồng được nhập vào hệ thống hôm nay nhưng có hiệu lực từ đầu tháng trước. Một lệnh chuyển tiền được tiếp nhận lúc 10 giờ, xử lý lúc 10 giờ 2 phút, nhưng ngày giá trị của giao dịch là ngày làm việc tiếp theo. Một sự kiện giao hàng xảy ra tại kho lúc 23 giờ 55 nhưng đến hệ thống trung tâm sau nửa đêm vì mất kết nối.

Nếu chỉ lưu một trường timestamp rồi dùng nó cho mọi mục đích, hệ thống có thể tính sai giá, thuế, hạn mức, trạng thái hợp đồng hoặc báo cáo lịch sử. Bài học này phân biệt thời điểm xử lý, thời điểm ghi nhận và thời điểm có hiệu lực nghiệp vụ; hướng dẫn mô hình hóa khoảng hiệu lực, múi giờ, lịch sử thay đổi và dữ liệu hai chiều thời gian (bitemporal); đồng thời đưa ra ví dụ Java, SQL và cách kiểm thử các trường hợp thời gian biên.

## 1. Vì sao phải phân biệt các loại thời điểm?

### 1.1. Một hành động có thể có nhiều mốc thời gian

Giả sử một công ty nhập mức phí dịch vụ mới vào hệ thống ngày 12 tháng 6. Chính sách được phê duyệt có hiệu lực từ ngày 1 tháng 6.

Ta có ít nhất ba mốc:

- Thời điểm có hiệu lực nghiệp vụ: ngày 1 tháng 6.
- Thời điểm hệ thống ghi nhận thay đổi: ngày 12 tháng 6.
- Thời điểm một tiến trình đọc hoặc tính toán lại dữ liệu: có thể là ngày 12 tháng 6 hoặc muộn hơn.

Nếu báo cáo trả lời câu hỏi “mức phí nào áp dụng cho dịch vụ ngày 5 tháng 6?”, hệ thống cần dùng ngày có hiệu lực. Nếu câu hỏi là “đến ngày 8 tháng 6, hệ thống đã biết mức phí nào?”, cần biết thời điểm ghi nhận. Hai câu hỏi khác nhau và có thể có hai câu trả lời khác nhau.

### 1.2. Dùng nhầm thời điểm dẫn đến sai nghiệp vụ

Một số lỗi thường gặp:

- Dùng createdAt thay cho effectiveFrom khiến chính sách hồi tố không áp dụng cho giao dịch trong quá khứ.
- Dùng ngày xử lý message thay cho thời điểm sự kiện xảy ra khiến báo cáo theo ngày bị lệch khi message đến muộn.
- Dùng UTC date thay cho ngày địa phương khiến giao dịch gần nửa đêm bị tính vào sai ngày kinh doanh.
- Ghi đè giá trị cũ khiến không thể giải thích vì sao một hóa đơn trước đây được tính theo mức giá khác.
- Dùng thời điểm hiện tại để xác định chính sách cho một giao dịch có ngày giá trị trong tương lai.

Thời gian cần được mô hình hóa theo ý nghĩa nghiệp vụ. Tên trường rõ ràng là bước đầu tiên để tránh nhầm lẫn.

## 2. Các loại thời gian cần phân biệt

Không phải hệ thống nào cũng cần tất cả các trường dưới đây. Hãy chọn những mốc có ý nghĩa trong quy trình.

| Khái niệm | Câu hỏi được trả lời | Ví dụ tên trường |
|---|---|---|
| Occurrence time / Event time | Sự việc xảy ra khi nào? | occurredAt, eventTime |
| Received time | Hệ thống nhận dữ liệu khi nào? | receivedAt |
| Processing time | Hệ thống bắt đầu hoặc hoàn tất xử lý khi nào? | processingStartedAt, processedAt |
| Recorded time / Transaction time | Dữ liệu được ghi nhận vào hệ thống khi nào? | recordedAt, transactionFrom |
| Effective time / Valid time | Dữ liệu hoặc quy tắc có hiệu lực đối với nghiệp vụ khi nào? | effectiveFrom, validFrom |
| Scheduled time | Hành động được lên lịch diễn ra khi nào? | scheduledAt |
| Expiration time | Quyền hoặc trạng thái hết hiệu lực khi nào? | expiresAt |

Các tên này không phải lúc nào cũng có định nghĩa thống nhất giữa mọi tổ chức. Điều quan trọng là mỗi hệ thống phải định nghĩa rõ semantics của chúng và dùng nhất quán trong API, event, database và báo cáo.

### 2.1. Occurrence time — thời điểm sự việc xảy ra

Occurrence time mô tả thời điểm một hành động hoặc sự kiện thực tế diễn ra theo nguồn phát sinh.

Ví dụ:

- Thiết bị quét kiện hàng lúc 23:55.
- Khách xác nhận đơn lúc 09:15.
- Nhân viên ký biên bản lúc 14:30.
- Máy ATM ghi nhận khách rút tiền lúc 08:02.

Thời điểm này có thể được thiết bị hoặc hệ thống nguồn cung cấp. Cần xem xét độ tin cậy của đồng hồ nguồn, timezone và độ chính xác. Một timestamp từ thiết bị chưa đồng bộ giờ không nên mặc nhiên được xem là thời gian chuẩn tuyệt đối.

### 2.2. Received time — thời điểm hệ thống tiếp nhận

Received time là thời điểm một hệ thống nhận được thông điệp hoặc dữ liệu.

Ví dụ, thiết bị quét kiện hàng xảy ra lúc 23:55 nhưng mất kết nối. Message được gửi và nhận lúc 00:10 ngày hôm sau.

Khi đó:

- occurredAt: 23:55.
- receivedAt: 00:10.

Nếu báo cáo hoạt động của kho dựa trên ngày xảy ra, dùng occurredAt. Nếu đo độ trễ truyền dữ liệu, dùng receivedAt trừ occurredAt.

### 2.3. Processing time — thời điểm xử lý

Processing time mô tả khi hệ thống thực hiện công việc xử lý dữ liệu. Tùy quy trình, có thể cần cả thời điểm bắt đầu và kết thúc:

- processingStartedAt: lúc worker bắt đầu xử lý.
- processedAt: lúc xử lý hoàn tất.
- failedAt: lúc ghi nhận xử lý thất bại.

Một message có thể được nhận lúc 10:00, bắt đầu xử lý lúc 10:01 và hoàn tất lúc 10:03. Các mốc này hữu ích để đo queue lag, thời gian xử lý và điều tra sự cố.

Processing time thường do hệ thống xử lý ghi nhận. Nó không tự quyết định ngày nghiệp vụ mà giao dịch thuộc về.

### 2.4. Recorded time — thời điểm dữ liệu được hệ thống ghi nhận

Recorded time cho biết từ lúc nào hệ thống lưu giữ một phiên bản thông tin trong cơ sở dữ liệu hoặc sổ ghi nhận.

Ví dụ, nhân viên nhập một quyết định vào ngày 12 tháng 6. Hệ thống ghi nhận phiên bản đó từ ngày 12 tháng 6, dù quyết định có hiệu lực từ ngày 1 tháng 6.

Recorded time rất quan trọng khi cần trả lời câu hỏi lịch sử: “Tại thời điểm ngày 8 tháng 6, hệ thống đang lưu thông tin nào?”

Trong mô hình bitemporal, recorded time thường được gọi là transaction time hoặc system time. Nó mô tả lịch sử mà hệ thống biết và lưu trữ, không nhất thiết là thời điểm nghiệp vụ thực sự thay đổi.

### 2.5. Effective time / Valid time — thời điểm có hiệu lực nghiệp vụ

Effective time cho biết một dữ liệu, chính sách hoặc trạng thái được xem là đúng trong thế giới nghiệp vụ từ lúc nào.

Ví dụ:

- Mức lương mới có hiệu lực từ ngày 1 tháng 7.
- Hợp đồng bảo hiểm có hiệu lực từ 00:00 ngày 1 tháng 1.
- Giá sản phẩm mới áp dụng cho đơn tạo từ ngày mai.
- Địa chỉ giao hàng mới có hiệu lực từ thời điểm khách xác nhận thay đổi.

Effective time có thể nằm trong quá khứ, hiện tại hoặc tương lai so với thời điểm hệ thống ghi nhận.

### 2.6. Scheduled time — thời điểm dự kiến thực hiện

Scheduled time cho biết một hành động được lên lịch, không khẳng định nó đã xảy ra hoặc đã được xử lý.

Ví dụ, một lệnh thanh toán được lên lịch vào ngày làm việc tiếp theo. Nếu worker xử lý muộn, scheduledAt vẫn giữ nguyên; processedAt ghi thời điểm thực tế.

Không nên dùng scheduledAt làm occurrence time. Hành động có thể bị hủy, trì hoãn hoặc thất bại.

## 3. Processing time và effective time khác nhau như thế nào?

### 3.1. Ví dụ thay đổi chính sách có hiệu lực hồi tố

Một doanh nghiệp phê duyệt mức phí mới vào ngày 12 tháng 6 và xác định mức phí áp dụng từ ngày 1 tháng 6.

| Thuộc tính | Giá trị |
|---|---|
| effectiveFrom | 2026-06-01 |
| approvedAt | 2026-06-12T09:00:00Z |
| recordedAt | 2026-06-12T09:05:00Z |
| processedAt | 2026-06-12T09:06:00Z |

Khi tính phí cho dịch vụ diễn ra ngày 5 tháng 6, hệ thống phải chọn chính sách có effectiveFrom phù hợp với ngày đó.

Nếu chỉ truy vấn bản ghi mới nhất theo recordedAt, hệ thống có thể áp dụng sai chính sách cho một ngày khác hoặc không thể tái tạo kết quả lịch sử.

### 3.2. Ví dụ thay đổi có hiệu lực trong tương lai

Khách hàng ký hợp đồng ngày 20 tháng 8, nhưng hợp đồng bắt đầu có hiệu lực ngày 1 tháng 9.

- occurredAt: thời điểm ký hợp đồng.
- recordedAt: thời điểm hợp đồng được lưu.
- effectiveFrom: ngày bắt đầu hiệu lực.

Trong khoảng từ ngày 20 đến hết ngày 31 tháng 8, hợp đồng đã tồn tại trong hệ thống nhưng chưa có hiệu lực. Mô hình cần phân biệt trạng thái hồ sơ với trạng thái hiệu lực.

### 3.3. Ví dụ sự kiện đến muộn

Một thiết bị tại kho ghi nhận hàng đã rời kho lúc 23:58. Message đến hệ thống trung tâm lúc 00:07 ngày hôm sau và được xử lý lúc 00:08.

Nếu báo cáo xuất kho theo ngày dùng processedAt, số lượng xuất sẽ bị chuyển sang ngày hôm sau. Nếu dùng occurredAt đã được xác thực, báo cáo phản ánh ngày thực tế sự kiện diễn ra.

Tuy nhiên, nếu đồng hồ thiết bị sai hoặc timestamp không đáng tin, hệ thống cần quy tắc xử lý chất lượng thời gian nguồn. Không phải mọi timestamp do client gửi đều đáng tin hơn thời điểm server nhận.

## 4. Mô hình hóa thời gian trong Java

### 4.1. Chọn kiểu thời gian theo ý nghĩa

Java Time API cung cấp các kiểu có semantics khác nhau:

| Kiểu | Ý nghĩa | Dùng khi |
|---|---|---|
| Instant | Một điểm trên dòng thời gian toàn cục | occurredAt, recordedAt, processedAt |
| LocalDate | Ngày lịch, không có giờ hoặc timezone | Ngày hiệu lực theo lịch, ngày sinh, ngày đáo hạn |
| LocalTime | Giờ trong ngày, không có ngày | Giờ mở cửa, giờ chốt nhận đơn |
| LocalDateTime | Ngày và giờ địa phương, không có timezone | Giá trị lịch địa phương trước khi xác định vùng |
| OffsetDateTime | Ngày giờ cùng UTC offset cụ thể | Giao tiếp timestamp có offset |
| ZonedDateTime | Ngày giờ gắn với vùng timezone và quy tắc lịch | Lịch địa phương có DST |
| Duration | Khoảng thời gian theo giây/nano | Thời gian xử lý, timeout |
| Period | Khoảng thời gian theo năm/tháng/ngày lịch | Kỳ hạn theo lịch, tuổi |

Không chọn kiểu chỉ vì nó tiện chuyển đổi. Hãy xác định dữ liệu biểu diễn một điểm trên timeline hay một ngày/giờ theo lịch nghiệp vụ.

### 4.2. Dùng Instant cho thời điểm tuyệt đối

Ví dụ:

~~~java
public record ProcessingMetadata(
    Instant receivedAt,
    Instant processingStartedAt,
    Instant processedAt
) {
    public ProcessingMetadata {
        Objects.requireNonNull(receivedAt);
        Objects.requireNonNull(processingStartedAt);
    }
}
~~~

Instant không chứa timezone. Nó biểu diễn một điểm trên timeline, thường được lưu và trao đổi ở UTC. Khi hiển thị cho người dùng, chuyển đổi sang timezone phù hợp với nghiệp vụ hoặc người dùng.

### 4.3. Dùng LocalDate cho ngày hiệu lực theo lịch

Nếu chính sách nói “có hiệu lực từ ngày 1 tháng 7 tại thị trường Việt Nam” và không có ý nghĩa theo một thời điểm chính xác trong ngày, LocalDate có thể phù hợp.

~~~java
public record EmploymentPeriod(
    LocalDate startDate,
    LocalDate endDateExclusive
) {
    public EmploymentPeriod {
        Objects.requireNonNull(startDate);

        if (endDateExclusive != null
            && !endDateExclusive.isAfter(startDate)) {
            throw new IllegalArgumentException(
                "End date must be after start date"
            );
        }
    }

    public boolean contains(LocalDate date) {
        return !date.isBefore(startDate)
            && (endDateExclusive == null
                || date.isBefore(endDateExclusive));
    }
}
~~~

Không chuyển một ngày lịch thành Instant lúc 00:00 UTC nếu quy tắc thực chất là ngày địa phương. 00:00 UTC có thể rơi vào buổi sáng cùng ngày ở một timezone khác hoặc ngày khác ở phía tây UTC.

### 4.4. LocalDateTime không xác định được một thời điểm tuyệt đối

LocalDateTime như 2026-10-25T02:30 không cho biết nó thuộc timezone nào. Ở một số vùng có daylight saving time, một giờ địa phương có thể xảy ra hai lần hoặc không xảy ra lần nào khi đồng hồ đổi giờ.

Nếu cần chuyển LocalDateTime thành Instant, phải có ZoneId và quy tắc xử lý trường hợp gap/overlap. Không dựa vào timezone mặc định của máy.

### 4.5. Offset và ZoneId không giống nhau

Offset như +07:00 chỉ cho biết độ lệch so với UTC tại một thời điểm. ZoneId như Asia/Ho_Chi_Minh mang quy tắc timezone theo vùng và lịch sử thay đổi.

Nếu nghiệp vụ cần tái hiện lịch địa phương, lưu ZoneId. Nếu chỉ cần trao đổi một timestamp đã xác định, Instant hoặc OffsetDateTime có thể phù hợp.

## 5. Khoảng thời gian có hiệu lực

### 5.1. Dùng khoảng nửa mở [from, to)

Một quy ước dễ quản lý là khoảng hiệu lực bao gồm điểm bắt đầu và không bao gồm điểm kết thúc:

\[
[from, to)
\]

Nghĩa là:

- Tại from, bản ghi có hiệu lực.
- Trước to, bản ghi có hiệu lực.
- Tại to, bản ghi đã hết hiệu lực.

Ví dụ:

- Mức giá A: [2026-01-01, 2026-04-01).
- Mức giá B: [2026-04-01, 2026-07-01).

Hai khoảng liền kề không bị chồng lấn và không có khoảng trống ở thời điểm chuyển giao. Ngày 1 tháng 4 thuộc mức giá B.

### 5.2. Vì sao tránh dùng 23:59:59.999?

Cách biểu diễn kết thúc ngày bằng 23:59:59.999 phụ thuộc độ chính xác timestamp của database và ứng dụng. Một hệ thống có microsecond hoặc nanosecond có thể ghi nhận thời điểm nằm sau giá trị đó nhưng vẫn thuộc ngày cần xét.

Khoảng nửa mở tránh phải đoán độ chính xác cuối ngày. Với LocalDate, dùng ngày kết thúc exclusive. Với Instant, dùng thời điểm chuyển giao exclusive.

### 5.3. Khoảng mở ở đầu hoặc cuối

Một quy tắc có thể không có ngày kết thúc:

- effectiveFrom có giá trị.
- effectiveTo null nghĩa là chưa có thời điểm kết thúc.

Một số mô hình cũng cần khoảng không xác định thời điểm bắt đầu, nhưng chỉ nên cho phép nếu nghiệp vụ có ý nghĩa rõ. Tránh dùng null tùy tiện khiến không biết nó có nghĩa “vô hạn”, “chưa xác định” hay “dữ liệu thiếu”.

### 5.4. Kiểm tra khoảng chồng lấn

Hai khoảng nửa mở [aStart, aEnd) và [bStart, bEnd) chồng lấn khi:

\[
aStart < bEnd \quad \text{và} \quad bStart < aEnd
\]

Nếu một end là vô hạn, có thể xem như không có giới hạn trên khi tính toán.

Không phải mọi loại dữ liệu đều cấm chồng lấn. Một khách hàng có thể có nhiều hợp đồng cùng hiệu lực ở các phạm vi khác nhau. Nhưng với một mức thuế duy nhất cho cùng sản phẩm, khu vực và loại giao dịch, chồng lấn có thể là lỗi dữ liệu.

Quy tắc uniqueness phải xác định đầy đủ chiều phân loại: cùng sản phẩm, cùng thị trường, cùng loại khách, cùng loại chính sách hoặc phạm vi nào khác.

## 6. Mô hình hóa chính sách có hiệu lực trong Domain Model

### 6.1. Tách giá trị chính sách khỏi thời gian hiệu lực

Một chính sách có thể gồm giá trị và khoảng thời gian mà giá trị đó áp dụng.

~~~java
public record EffectivePeriod(
    LocalDate fromInclusive,
    LocalDate toExclusive
) {
    public EffectivePeriod {
        Objects.requireNonNull(fromInclusive);

        if (toExclusive != null
            && !toExclusive.isAfter(fromInclusive)) {
            throw new IllegalArgumentException(
                "Effective period end must be after start"
            );
        }
    }

    public boolean contains(LocalDate date) {
        return !date.isBefore(fromInclusive)
            && (toExclusive == null
                || date.isBefore(toExclusive));
    }

    public boolean overlaps(EffectivePeriod other) {
        boolean thisEndsAfterOtherStarts =
            toExclusive == null
                || other.fromInclusive.isBefore(toExclusive);

        boolean otherEndsAfterThisStarts =
            other.toExclusive == null
                || fromInclusive.isBefore(other.toExclusive);

        return thisEndsAfterOtherStarts
            && otherEndsAfterThisStarts;
    }
}
~~~

EffectivePeriod có thể là Value Object vì nó được nhận diện bằng hai đầu mút và quy tắc khoảng. Các phương thức contains và overlaps diễn đạt hành vi miền của khoảng hiệu lực.

### 6.2. Chính sách thuế có hiệu lực theo ngày

~~~java
public record TaxRate(
    String taxCode,
    BigDecimal rate,
    EffectivePeriod period
) {
    public TaxRate {
        if (taxCode == null || taxCode.isBlank()) {
            throw new IllegalArgumentException(
                "Tax code is required"
            );
        }

        Objects.requireNonNull(rate);
        Objects.requireNonNull(period);

        if (rate.signum() < 0) {
            throw new IllegalArgumentException(
                "Tax rate cannot be negative"
            );
        }
    }

    public boolean appliesOn(LocalDate businessDate) {
        return period.contains(businessDate);
    }
}
~~~

Mức thuế không cần chứa processing time để xác định ngày áp dụng. Thời điểm tạo hoặc ghi nhận phiên bản được quản lý riêng trong lịch sử thay đổi.

### 6.3. Lịch chính sách chọn phiên bản theo ngày nghiệp vụ

Một PolicySchedule có thể chứa nhiều phiên bản hiệu lực theo thời gian. Khi tìm chính sách, nó dùng businessDate:

~~~java
public final class TaxPolicySchedule {

    private final List<TaxRate> rates;

    public TaxPolicySchedule(List<TaxRate> rates) {
        this.rates = List.copyOf(rates);
    }

    public TaxRate rateFor(LocalDate businessDate) {
        List<TaxRate> matches = rates.stream()
            .filter(rate -> rate.appliesOn(businessDate))
            .toList();

        if (matches.size() != 1) {
            throw new IllegalStateException(
                "Expected exactly one applicable tax rate"
            );
        }

        return matches.get(0);
    }
}
~~~

Ví dụ giả định danh sách đã được kiểm tra để không có khoảng chồng lấn. Trong triển khai thực tế, nên xác nhận tính duy nhất ngay khi thêm phiên bản hoặc trong constructor/factory của schedule.

### 6.4. Không dùng createdAt để chọn chính sách có hiệu lực

Một bản ghi mới được tạo hôm nay có thể có hiệu lực từ tháng trước hoặc tháng sau. Vì vậy, truy vấn “chính sách áp dụng ngày X” phải lọc theo effective period.

createdAt hoặc recordedAt chỉ trả lời bản ghi được lưu khi nào. Nếu cần biết “hệ thống đã biết điều gì tại thời điểm Y”, phải kết hợp thêm transaction time.

## 7. Lịch sử thay đổi và hiệu lực hồi tố

### 7.1. Ghi đè dữ liệu hiện tại làm mất lịch sử

Giả sử mức phí ban đầu là 5%. Sau đó doanh nghiệp điều chỉnh thành 6% từ ngày 1 tháng 4.

Nếu chỉ UPDATE rate = 6% trên cùng bản ghi, hệ thống mất thông tin mức phí cũ. Không thể trả lời chính xác giao dịch tháng 3 được tính theo chính sách nào, hoặc tại thời điểm tháng 3 nhân viên đã nhìn thấy mức phí nào.

Có thể lưu mỗi phiên bản thành một bản ghi riêng với effective period. Khi thay đổi, đóng khoảng cũ và tạo khoảng mới thay vì xóa lịch sử.

### 7.2. Thay đổi trong tương lai

Một chính sách được phê duyệt hôm nay nhưng có hiệu lực tháng sau có thể được lưu ngay với effectiveFrom trong tương lai.

Khi truy vấn tại ngày hiện tại, hệ thống chưa chọn phiên bản đó. Đến ngày bắt đầu, phiên bản tự động trở thành chính sách áp dụng theo dữ liệu thời gian.

Không cần chờ đến ngày hiệu lực mới ghi nhận quyết định đã được phê duyệt. Tuy nhiên, cần phân biệt trạng thái phê duyệt, trạng thái đã ghi nhận và trạng thái có hiệu lực.

### 7.3. Thay đổi hồi tố

Thay đổi hồi tố xảy ra khi hôm nay hệ thống nhận được thông tin rằng một giá trị đáng lẽ có hiệu lực từ trước đó.

Ví dụ, ngày 12 tháng 6 nhận quyết định điều chỉnh phí áp dụng từ ngày 1 tháng 6. Hệ thống cần xác định:

- Những giao dịch nào trong khoảng bị ảnh hưởng?
- Hóa đơn đã phát hành có cần điều chỉnh không?
- Có cần tính lại báo cáo hoặc công nợ không?
- Phiên bản cũ có được giữ để giải thích kết quả trước khi biết quyết định mới không?
- Ai phê duyệt thay đổi hồi tố?

Không nên tự động sửa mọi giao dịch lịch sử chỉ vì một chính sách được nhập hồi tố. Quy trình điều chỉnh cần tuân theo quy tắc pháp lý và nghiệp vụ.

### 7.4. Tách hành động thay đổi khỏi khoảng thời gian hiệu lực

Một lệnh thay đổi có thể chứa:

- effectiveFrom: ngày bắt đầu áp dụng.
- requestedAt: thời điểm yêu cầu được gửi.
- approvedAt: thời điểm được phê duyệt.
- recordedAt: thời điểm phiên bản được lưu.

Không nhất thiết phải lưu tất cả nếu không có nhu cầu. Nhưng nếu cần audit và giải thích quyết định, các mốc phải có semantics riêng.

## 8. Bitemporal — quản lý hai chiều thời gian

### 8.1. Hai câu hỏi lịch sử khác nhau

Bitemporal modeling quản lý đồng thời hai chiều:

- **Valid time**: khoảng thời gian thông tin đúng trong thế giới nghiệp vụ.
- **Transaction time**: khoảng thời gian hệ thống lưu phiên bản thông tin đó như dữ liệu hiện hành đã biết.

Ví dụ:

Ngày 12 tháng 6, hệ thống mới ghi nhận rằng mức phí 6% có hiệu lực từ ngày 1 tháng 6.

| Phiên bản | Valid time | Transaction time | Rate |
|---|---|---|---|
| A | [01/01, vô hạn) | [01/01, 12/06) | 5% |
| B1 | [01/01, 01/06) | [12/06, vô hạn) | 5% |
| B2 | [01/06, vô hạn) | [12/06, vô hạn) | 6% |

Bảng rút gọn này cho thấy:
- Hỏi “mức phí có hiệu lực ngày 5 tháng 6 theo hiểu biết hiện tại?” → 6%.
- Hỏi “ngày 8 tháng 6 hệ thống đang lưu mức phí nào cho ngày 5 tháng 6?” → 5%.

Nếu chỉ có valid time, câu hỏi thứ hai không thể được trả lời chính xác sau khi lịch sử bị cập nhật.

### 8.2. Valid time và transaction time không thay thế nhau

Valid time trả lời thông tin áp dụng trong nghiệp vụ khi nào. Transaction time trả lời hệ thống biết hoặc lưu thông tin đó khi nào.

Một quyết định có thể được ghi nhận hôm nay và có hiệu lực trong quá khứ. Một quyết định khác có thể được ghi nhận hôm nay và có hiệu lực trong tương lai.

Bitemporal không phải là việc thêm hai cột timestamp cho đủ. Nó cần giữ các phiên bản lịch sử theo cả hai chiều và có quy tắc cập nhật không phá hủy thông tin đã ghi nhận.

### 8.3. Mô hình dữ liệu bitemporal đơn giản

Ví dụ bảng lưu lịch sử mức phí:

~~~sql
CREATE TABLE service_rate_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    service_code VARCHAR(80) NOT NULL,
    rate NUMERIC(12, 4) NOT NULL,

    valid_from DATE NOT NULL,
    valid_to DATE,

    recorded_from TIMESTAMPTZ NOT NULL,
    recorded_to TIMESTAMPTZ,

    recorded_by VARCHAR(120) NOT NULL
);
~~~

Quy ước:
- valid_from inclusive.
- valid_to exclusive; null nghĩa là chưa có ngày kết thúc.
- recorded_from inclusive.
- recorded_to exclusive; null nghĩa là phiên bản đang được hệ thống giữ như hiện hành.

Đây là schema minh họa. Cần bổ sung khóa nghiệp vụ, ràng buộc không chồng lấn và chiến lược cập nhật phù hợp với database đang sử dụng.

### 8.4. Truy vấn theo thời điểm nghiệp vụ và thời điểm hệ thống biết

Muốn biết mức phí có hiệu lực tại businessDate theo thông tin hệ thống đã biết ở knownAt:

~~~sql
SELECT service_code, rate
FROM service_rate_history
WHERE service_code = :serviceCode
  AND valid_from <= :businessDate
  AND (valid_to IS NULL OR :businessDate < valid_to)
  AND recorded_from <= :knownAt
  AND (recorded_to IS NULL OR :knownAt < recorded_to);
~~~

Truy vấn có hai điều kiện thời gian độc lập. Nếu bỏ điều kiện recorded time, hệ thống chỉ trả phiên bản đang được biết hiện tại, không tái hiện được góc nhìn lịch sử.

### 8.5. Ghi nhận điều chỉnh hồi tố mà không xóa lịch sử đã biết

Khi nhận thay đổi mới:

1. Đóng transaction time của phiên bản đang được hệ thống xem là hiện hành bằng cách đặt recorded_to.
2. Tạo một hoặc nhiều phiên bản mới với recorded_from là thời điểm ghi nhận mới.
3. Chia valid period nếu chỉ một đoạn thời gian bị điều chỉnh.
4. Giữ phiên bản cũ để có thể trả lời câu hỏi hệ thống đã biết gì trước thời điểm sửa.
5. Thực hiện trong transaction để không để lộ lịch sử ở trạng thái nửa chừng.

Việc chia khoảng phải bảo đảm các phiên bản hiện hành không chồng lấn trong cùng phạm vi nghiệp vụ nếu chính sách yêu cầu duy nhất.

### 8.6. Khi nào cần bitemporal?

Bitemporal hữu ích khi cần trả lời đồng thời:

- Điều gì thực sự có hiệu lực tại một ngày trong quá khứ?
- Tại thời điểm đó hệ thống đã biết thông tin nào?
- Ai đã ghi nhận thay đổi và khi nào?
- Một báo cáo cũ được tạo dựa trên phiên bản dữ liệu nào?
- Một quyết định hồi tố ảnh hưởng thế nào đến kết quả trước đây?

Không phải mọi bảng đều cần bitemporal. Với dữ liệu không cần tái dựng góc nhìn lịch sử, validFrom/validTo cùng audit log có thể đủ. Hãy cân nhắc chi phí lưu trữ, truy vấn, chỉnh sửa khoảng và vận hành.

## 9. Thời gian trong Domain Event và Event Sourcing

### 9.1. Một event có thể mang nhiều mốc thời gian

Ví dụ event xác nhận hợp đồng:

~~~java
public record ContractActivated(
    UUID eventId,
    ContractId contractId,
    Instant occurredAt,
    LocalDate effectiveFrom,
    String sourceContext
) {
}
~~~

Trong đó:
- occurredAt là lúc sự kiện xác nhận được phát sinh.
- effectiveFrom là ngày hợp đồng bắt đầu có hiệu lực.
- eventId nhận diện message hoặc event cụ thể.

Consumer có thể nhận event muộn hơn. Consumer cần ghi receivedAt và processedAt riêng nếu cần theo dõi vận hành.

### 9.2. Event time không phải processing time

Trong event-driven system, event time thường mô tả lúc sự kiện xảy ra ở nguồn. Processing time là lúc consumer xử lý sự kiện.

Nếu consumer xử lý lại message sau một ngày, event time không thay đổi. Nếu dùng processing time để dựng lịch sử nghiệp vụ, thứ tự hoặc ngày của sự kiện có thể bị sai.

### 9.3. Event Sourcing không tự động giải quyết mọi câu hỏi thời gian

Event Sourcing lưu chuỗi sự kiện để tái dựng trạng thái. Tuy nhiên, cần xác định timestamp của event có ý nghĩa gì:

- Thời điểm hành động nghiệp vụ xảy ra?
- Thời điểm command được chấp nhận?
- Thời điểm event được append vào event store?
- Thời điểm event có hiệu lực trong nghiệp vụ?

Một event stream có thứ tự append, nhưng thứ tự append không luôn giống thứ tự xảy ra ngoài đời. Message có thể đến muộn hoặc được hiệu chỉnh hồi tố.

Nếu cần tái dựng trạng thái “theo hiệu lực nghiệp vụ tại ngày X”, projection phải áp dụng semantics effective time và xử lý event đến muộn. Không chỉ replay theo thứ tự append rồi giả định kết quả luôn đúng với mọi câu hỏi lịch sử.

### 9.4. Xử lý event đến muộn và ngoài thứ tự

Consumer cần phân biệt:

- Event trùng: đã xử lý cùng Event ID.
- Event đến muộn: occurredAt cũ hơn những event đã xử lý.
- Event ngoài thứ tự: sequence hoặc version không theo thứ tự mong đợi.
- Event hồi tố: sự kiện mới ghi nhận một thay đổi có hiệu lực trong quá khứ.

Cách xử lý có thể là:
- Deduplicate theo Event ID.
- Kiểm tra Aggregate version hoặc sequence.
- Lưu event chờ nếu thiếu sự kiện trước.
- Rebuild projection hoặc tính lại khoảng hiệu lực.
- Phát lệnh bù trừ theo quy trình nghiệp vụ.

Không nên tự động loại bỏ mọi event có occurredAt nhỏ hơn event gần nhất. Có thể đó là dữ liệu đến muộn nhưng vẫn hợp lệ.

## 10. Múi giờ và lịch nghiệp vụ

### 10.1. Lưu thời điểm tuyệt đối, hiển thị theo timezone có nghĩa

Với thời điểm xảy ra chính xác, lưu Instant hoặc kiểu timestamp có timezone semantics rõ ràng. Khi hiển thị, chuyển sang timezone được quy định bởi nghiệp vụ hoặc người dùng.

Ví dụ một giao dịch được lưu là 2026-11-18T16:30:00Z có thể hiển thị thành sáng hôm sau ở một timezone khác. Không nên đổi timestamp gốc chỉ để phù hợp màn hình.

### 10.2. Ngày kinh doanh có thể khác ngày UTC

Một ngân hàng có thể chốt ngày kinh doanh theo timezone của chi nhánh. Một giao dịch lúc 00:30 UTC có thể vẫn thuộc ngày kinh doanh trước đó ở một khu vực khác.

Hãy định nghĩa rõ:
- Business timezone của tổ chức hoặc chi nhánh.
- Thời điểm cut-off trong ngày.
- Quy tắc ngày nghỉ và cuối tuần.
- Cách xử lý giao dịch sau giờ cut-off.

Không dùng LocalDate.now() không tham số trong logic miền vì nó dựa vào timezone mặc định của máy. Hãy nhận Clock hoặc business date được xác định rõ từ tầng ứng dụng.

### 10.3. Daylight Saving Time tạo ra khoảng trống và thời điểm lặp

Ở các vùng có DST:
- Khi đồng hồ tiến lên, một số giờ địa phương không tồn tại.
- Khi đồng hồ lùi lại, một số giờ địa phương xảy ra hai lần.

Nếu lịch hẹn được lưu bằng LocalDateTime mà không có ZoneId hoặc offset, một số thời điểm có thể mơ hồ.

Khi nhận lịch hẹn địa phương, cần có timezone vùng và quy tắc giải quyết gap/overlap. Có thể yêu cầu người dùng chọn một trong hai offset khi giờ xảy ra hai lần.

### 10.4. Không dùng timezone mặc định của server

Server có thể chạy UTC trong khi người dùng ở múi giờ khác. Một node khác có thể được cấu hình timezone khác. Nếu code dựa vào default timezone, kết quả có thể khác giữa máy phát triển, CI và production.

Hãy cấu hình timezone rõ ràng, ưu tiên UTC cho timestamp tuyệt đối và truyền ZoneId cụ thể khi tính lịch nghiệp vụ.

## 11. API và hợp đồng tích hợp về thời gian

### 11.1. Tên trường phải thể hiện semantics

Tránh API chỉ có một trường timestamp không rõ nghĩa:

~~~json
{
  "timestamp": "2026-06-12T09:05:00Z"
}
~~~

Thay vào đó, dùng tên cụ thể:

~~~json
{
  "occurredAt": "2026-06-12T09:00:00Z",
  "recordedAt": "2026-06-12T09:05:00Z",
  "effectiveFrom": "2026-06-01"
}
~~~

Consumer biết mốc nào dùng cho lịch sử nghiệp vụ và mốc nào dùng để audit.

### 11.2. Định dạng timestamp nên có offset hoặc UTC

Với Instant, API thường trao đổi ISO 8601/RFC 3339 có Z hoặc offset, ví dụ 2026-06-12T09:00:00Z. Không gửi local datetime không có timezone nếu consumer cần xác định thời điểm tuyệt đối.

Với ngày hiệu lực theo lịch, dùng chuỗi ngày ISO như 2026-06-01 và định nghĩa rõ đó là ngày lịch của phạm vi nghiệp vụ nào.

### 11.3. Hợp đồng cần xác định độ chính xác

Database và ngôn ngữ có thể hỗ trợ độ chính xác khác nhau: giây, mili giây, micro giây hoặc nano giây.

Nếu một hệ thống lưu microsecond còn hệ thống khác chỉ giữ millisecond, so sánh timestamp có thể lệch. Hãy thống nhất precision, rounding/truncation và quy tắc so sánh trong hợp đồng.

### 11.4. Không suy diễn effective time từ receivedAt

Một consumer nhận message lúc 10:05 không có nghĩa thay đổi có hiệu lực lúc 10:05. Nếu producer không cung cấp effectiveFrom, cần xác định chính sách mặc định hoặc từ chối dữ liệu thiếu thay vì tự gán receivedAt một cách âm thầm.

## 12. Kiểm thử logic thời gian

### 12.1. Tiêm Clock để test lặp lại được

~~~java
public final class PolicyService {

    private final Clock clock;

    public PolicyService(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public boolean isCurrentlyEffective(
        EffectivePeriod period,
        ZoneId businessZone
    ) {
        LocalDate businessDate =
            LocalDate.now(clock.withZone(businessZone));

        return period.contains(businessDate);
    }
}
~~~

Test dùng Clock cố định:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-06-01T00:30:00Z"),
    ZoneOffset.UTC
);
~~~

Sau đó truyền ZoneId của nghiệp vụ để xác định business date. Cùng một test sẽ cho kết quả giống nhau trên mọi máy.

### 12.2. Kiểm tra boundary của khoảng hiệu lực

Với khoảng [from, to), test cần xác nhận:

- Ngày trước from: false.
- Đúng from: true.
- Ngày nằm giữa: true.
- Ngày trước to: true.
- Đúng to: false.
- Ngày sau to: false.

Nếu to là null, xác nhận khoảng vẫn hiệu lực ở các ngày sau from theo chính sách.

### 12.3. Kiểm tra khoảng chồng lấn và liền kề

Ví dụ:
- [01/01, 01/04) và [01/04, 01/07) không chồng lấn.
- [01/01, 01/05) và [01/04, 01/07) chồng lấn.
- [01/01, vô hạn) và [01/04, 01/07) chồng lấn.

Kiểm thử các trường hợp này giúp phát hiện lỗi khi thêm phiên bản chính sách.

### 12.4. Kiểm thử timezone và DST

Với nghiệp vụ phụ thuộc timezone:
- Kiểm tra cùng Instant được chuyển thành ngày khác nhau ở hai timezone.
- Kiểm tra thời điểm nằm trong DST gap.
- Kiểm tra thời điểm lặp khi DST kết thúc.
- Kiểm tra timezone mặc định của máy không ảnh hưởng kết quả.

Không chỉ test UTC nếu nghiệp vụ thực sự dùng lịch địa phương.

### 12.5. Kiểm thử event đến muộn và điều chỉnh hồi tố

Tạo test theo thứ tự:
1. Ghi nhận một chính sách hiện hành.
2. Ghi nhận một giao dịch theo chính sách đó.
3. Nhận thay đổi có effectiveFrom nằm trong quá khứ.
4. Kiểm tra kết quả hiện tại theo valid time.
5. Kiểm tra góc nhìn tại recorded time trước thay đổi.
6. Xác nhận lịch sử cũ vẫn có thể truy vấn.

Những test này đặc biệt quan trọng với dữ liệu tài chính, hợp đồng, bảo hiểm và tuân thủ.

## 13. Những sai lầm thường gặp

### Dùng một trường timestamp cho mọi mục đích

occurredAt, processedAt, recordedAt và effectiveAt trả lời các câu hỏi khác nhau. Hãy đặt tên và semantics rõ.

### Dùng processing time thay cho business time

Message đến muộn có thể bị tính vào sai ngày hoặc sai kỳ. Dùng event time hoặc effective time theo quy tắc nghiệp vụ.

### Dùng createdAt để chọn phiên bản chính sách

Phiên bản mới nhất được ghi nhận không nhất thiết là phiên bản có hiệu lực cho giao dịch đang xét. Truy vấn theo effective period.

### Ghi đè lịch sử

UPDATE giá trị hiện tại mà không giữ phiên bản cũ khiến hệ thống không thể tái dựng kết quả lịch sử. Dùng version history hoặc bitemporal khi cần.

### Lưu LocalDateTime như thể nó là Instant

LocalDateTime không xác định timezone và có thể mơ hồ khi chuyển DST. Hãy dùng kiểu phù hợp với ý nghĩa dữ liệu.

### Dùng timezone mặc định của server

Kết quả có thể khác giữa môi trường. Dùng UTC cho thời điểm tuyệt đối và ZoneId được định nghĩa cho lịch nghiệp vụ.

### Kết thúc khoảng bằng 23:59:59.999

Độ chính xác timestamp có thể khác nhau. Dùng khoảng nửa mở [from, to).

### Giả định event append order là business order

Event có thể đến muộn hoặc được ghi nhận hồi tố. Cần semantics thời gian và version rõ ràng.

### Bitemporal ở mọi nơi

Bitemporal tăng chi phí lưu trữ, truy vấn và vận hành. Chỉ dùng khi cần trả lời cả câu hỏi valid time và “hệ thống đã biết gì tại thời điểm đó”.

### Không kiểm thử ngày biên

Các lỗi thường nằm đúng tại effectiveFrom, effectiveTo, cut-off và DST. Hãy biến chúng thành test case cụ thể.

## 14. Bài tập thực hành: quản lý phiên bản giá dịch vụ

Một nền tảng dịch vụ có bảng giá thay đổi theo thị trường. Nhân viên có thể nhập bảng giá hôm nay nhưng áp dụng từ đầu tháng sau. Đôi khi doanh nghiệp nhận quyết định điều chỉnh hồi tố từ đầu tháng hiện tại.

Yêu cầu:

- Mỗi thị trường và loại dịch vụ có một mức giá có hiệu lực tại một ngày nghiệp vụ.
- Các khoảng hiệu lực của cùng phạm vi không được chồng lấn.
- Hệ thống phải lưu thời điểm nhập và người nhập.
- Có thể truy vấn mức giá hiện hành cho một ngày bất kỳ.
- Có thể giải thích ngày 10 tháng này hệ thống đã biết mức giá nào cho ngày 5 tháng này.
- Một thay đổi hồi tố không được xóa lịch sử phiên bản đã ghi nhận trước đó.

Hãy thực hiện:

1. Xác định trường nào là valid time, trường nào là transaction time.
2. Chọn LocalDate hay Instant cho effective period và giải thích.
3. Thiết kế Value Object EffectivePeriod.
4. Thiết kế Aggregate hoặc repository quản lý các phiên bản giá.
5. Xác định quy tắc khoảng nửa mở và kiểm tra overlap.
6. Thiết kế bảng bitemporal và truy vấn theo businessDate/knownAt.
7. Viết test cho thay đổi tương lai, thay đổi hồi tố và khoảng liền kề.
8. Xác định quy trình phê duyệt và tính lại hóa đơn nếu giá hồi tố ảnh hưởng giao dịch đã hoàn tất.

### 14.1. Gợi ý bộ dữ liệu

| Phiên bản | Giá | Valid time | Recorded time |
|---|---:|---|---|
| A | 5% | [01/01, vô hạn) | [01/01, 12/06) |
| B1 | 5% | [01/01, 01/06) | [12/06, vô hạn) |
| B2 | 6% | [01/06, vô hạn) | [12/06, vô hạn) |

Các câu hỏi cần trả lời:
- Giá áp dụng cho ngày 05/06 theo hiểu biết hiện tại là bao nhiêu?
- Ngày 08/06, hệ thống đang lưu giá nào cho ngày 05/06?
- Ngày 15/06, hệ thống lưu giá nào cho ngày 10/06?
- Nếu có một điều chỉnh mới ngày 20/06 có hiệu lực từ 10/06, các câu trả lời lịch sử thay đổi thế nào?

## 15. Checklist thiết kế thời gian và lịch sử

Trước khi hoàn thành một mô hình hoặc use case có yếu tố thời gian, hãy kiểm tra:

- Đã định nghĩa rõ occurredAt, receivedAt, processedAt và recordedAt nếu cần.
- Đã xác định effective time thuộc ngày lịch hay một thời điểm tuyệt đối.
- Đã chọn Instant, LocalDate, ZonedDateTime hoặc kiểu phù hợp với semantics.
- Business timezone và cut-off được xác định rõ.
- Không phụ thuộc timezone mặc định của máy.
- Khoảng hiệu lực dùng quy ước inclusive/exclusive nhất quán.
- Quy tắc overlap được xác định theo đúng phạm vi nghiệp vụ.
- Thay đổi tương lai và thay đổi hồi tố có quy trình rõ.
- Lịch sử cũ được giữ nếu cần tái dựng góc nhìn trước đây.
- Bitemporal chỉ được dùng khi cần cả valid time và transaction time.
- Event time không bị nhầm với consumer processing time.
- API/event contract nêu rõ semantics và precision của timestamp.
- Có unit test cho boundary, timezone, DST và Clock.
- Có integration test cho lưu trữ và truy vấn lịch sử.
- Có quy trình phê duyệt, audit và tính lại dữ liệu bị ảnh hưởng.

## Kết luận

Thời điểm xử lý cho biết hệ thống thực hiện công việc khi nào; thời điểm ghi nhận cho biết hệ thống lưu phiên bản thông tin khi nào; thời điểm có hiệu lực nghiệp vụ cho biết thông tin được xem là đúng trong thế giới nghiệp vụ từ lúc nào. Chúng có thể trùng nhau nhưng không nên mặc định là một.

Mô hình thời gian tốt bắt đầu bằng việc xác định câu hỏi nghiệp vụ cần trả lời. Dùng Instant cho điểm thời gian tuyệt đối, LocalDate cho ngày lịch, ZoneId cho quy tắc timezone và khoảng nửa mở cho các phiên bản hiệu lực khi phù hợp. Khi cần biết cả điều gì có hiệu lực trong quá khứ lẫn hệ thống đã biết gì tại một thời điểm trước đây, bitemporal modeling giữ lại hai chiều lịch sử đó.

Phân biệt đúng các mốc thời gian giúp hệ thống xử lý message đến muộn, chính sách hồi tố, thay đổi tương lai và báo cáo lịch sử một cách có thể giải thích. Quan trọng nhất, mỗi trường thời gian phải nói rõ nó đại diện cho sự kiện nào và được dùng để trả lời câu hỏi nào.

