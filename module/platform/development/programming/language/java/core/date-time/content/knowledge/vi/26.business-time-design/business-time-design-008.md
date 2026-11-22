# Đặt tên trường và tham số thể hiện đơn vị, múi giờ và ý nghĩa

## 1. Tên thời gian là một phần của hợp đồng

Xét một hàm:

```java
void configure(long time, int offset);
```

Chữ ký minh họa này để lại quá nhiều câu hỏi:

- `time` là một thời điểm hay một khoảng chờ?
- Nếu là số thời gian, đơn vị là giây, mili giây hay nano giây?
- `offset` là độ lệch UTC, thời lượng dời lịch hay vị trí phân trang?
- Giá trị gắn với vùng nào, và có cần vùng để diễn giải hay không?

Một tên rõ không thay mọi tài liệu, nhưng giúp người gọi tránh phải đoán những điều cơ bản. Với dữ liệu thời gian, đặt tên tốt cần phối hợp **ý nghĩa nghiệp vụ, kiểu dữ liệu, đơn vị và ngữ cảnh vùng**.

Không cần nhét tất cả thông tin vào mọi tên. Nếu kiểu đã thể hiện một phần rõ ràng, tên nên tập trung vào ý nghĩa còn thiếu. Ví dụ `Duration requestTimeout` đã nói được đây là một thời lượng; không bắt buộc đổi thành một tên dài liệt kê giây và nano.

## 2. Trước khi đặt tên, xác định loại thông tin

| Cần biểu diễn | Kiểu phù hợp thường gặp | Tên gợi ý |
| --- | --- | --- |
| Lúc sự kiện thực sự xảy ra | `Instant` | `occurredAt` |
| Lúc hệ thống nhận sự kiện | `Instant` | `receivedAt` |
| Ngày giao hàng theo nghiệp vụ | `LocalDate` | `deliveryDate` |
| Giờ mở cửa theo đồng hồ địa phương | `LocalTime` | `openingLocalTime` |
| Ngày giờ địa phương chưa phân giải thành thời điểm | `LocalDateTime` | `scheduledLocalDateTime` |
| Vùng dùng cho lịch | `ZoneId` | `scheduleZone` |
| Độ lệch UTC cụ thể | `ZoneOffset` | `utcOffset` |
| Khoảng chờ tối đa | `Duration` | `requestTimeout` |
| Hạn chót là một mốc tuyệt đối | `Instant` | `requestDeadline` |
| Kỳ theo năm–tháng | `YearMonth` | `reportingPeriod` |

[Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) biểu diễn một điểm trên dòng thời gian. [LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html) không có múi giờ hoặc offset nên chưa xác định duy nhất một thời điểm. Chỉ đổi tên một biến `LocalDateTime` thành `eventInstant` không tạo ra thông tin còn thiếu.

Tên phải trung thực với kiểu và dữ liệu thực tế. Nếu miền yêu cầu một thời điểm, hãy chọn kiểu và bước chuyển đổi phù hợp, thay vì dùng một tên nghe như thời điểm cho dữ liệu vẫn còn mơ hồ.

Những hậu tố `At`, `Date` và `LocalTime` trong bài là các gợi ý nhất quán, không phải quy tắc bắt buộc của Java. Một dự án có thể chọn quy ước khác miễn là chúng được dùng rõ và nhất quán.

## 3. Với số nguyên, ghi rõ đơn vị

### 3.1. long không mang đơn vị

Hai giá trị sau đều là `long` nhưng khác nhau một nghìn lần:

```java
long occurredAtEpochSeconds = 1_704_067_200L;
long occurredAtEpochMillis = 1_704_067_200_000L;
```

Cả hai có thể biểu diễn cùng thời điểm `2024-01-01T00:00:00Z` khi được đưa vào đúng hàm chuyển đổi:

```java
Instant a = Instant.ofEpochSecond(occurredAtEpochSeconds);
Instant b = Instant.ofEpochMilli(occurredAtEpochMillis);
```

Nếu đặt tên cả hai là `timestamp`, kiểu `long` không giúp trình biên dịch phát hiện việc truyền nhầm. Tên `occurredAtEpochMillis` đồng thời nói:

- Đây là lúc sự kiện xảy ra, không phải lúc nhận.
- Đây là số tính từ epoch theo hợp đồng.
- Đơn vị là mili giây.

Tên chỉ là một lớp bảo vệ. Ở biên đọc dữ liệu, vẫn cần kiểm tra miền giá trị và hợp đồng nguồn, không tự suy đơn vị bằng cách đếm số chữ số của một số bất kỳ.

### 3.2. Dùng hậu tố đơn vị có nghĩa rõ

| Tên mơ hồ | Tên rõ hơn nếu vẫn dùng số |
| --- | --- |
| `timeout` | `requestTimeoutMillis` |
| `delay` | `retryDelaySeconds` |
| `timestamp` | `occurredAtEpochMillis` |
| `nano` | `nanoOfSecond` hoặc `elapsedNanos` tùy ý nghĩa |
| `offset` | `utcOffsetSeconds` nếu thực sự lưu offset bằng giây |
| `ttl` | `sessionTtlSeconds` nếu đây là thời lượng tính theo giây |

Không gắn hậu tố `Millis` cho một số thực chất đang chứa giây. Khi đổi đơn vị, phải đổi cả phép tính lẫn tên và hợp đồng. Đổi tên một mình có thể làm lỗi khó thấy hơn vì người gọi sẽ tin tên mới.

Đối với phần nano, phân biệt `nanoOfSecond` là thành phần trong một giây với một tổng thời lượng tính bằng nano. Một số `123_456_789` có thể là phần nano của giây hiện tại, không phải một thời điểm độc lập.

### 3.3. Chuyển sang kiểu thời lượng sớm ở biên

Trong mã nghiệp vụ, có thể chuyển một cấu hình số thành `Duration`:

```java
Duration requestTimeout = Duration.ofMillis(requestTimeoutMillis);
```

[Duration](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Duration.html) mô hình hóa thời lượng theo giây và nano giây. Nó giúp các hàm bên trong nhận một đại lượng có ý nghĩa hơn `long` rời rạc.

Tên tham số chuyển đổi nên nói rõ đơn vị đầu vào, chẳng hạn `requestTimeoutFromMillis(long requestTimeoutMillis)`. Sau chuyển đổi, `requestTimeout` là đủ rõ vì kiểu `Duration` đã mang nghĩa thời lượng.

Vẫn cần xác thực giá trị. `Duration` có thể âm; một timeout âm có được chấp nhận hay không là hợp đồng ứng dụng. Ví dụ trong bài chỉ chấp nhận timeout dương.

## 4. Phân biệt thời lượng, ngày lịch và hạn chót

Một tên `retentionDays` có thể vẫn chưa đủ rõ: “ngày” nghĩa là từng ngày trên lịch địa phương hay mỗi khối đúng 24 giờ?

| Ý nghĩa | Biểu đạt gợi ý |
| --- | --- |
| Giữ đúng 72 giờ đã trôi qua | `Duration retentionDuration` |
| Cộng ba ngày trên lịch nghiệp vụ | `int retentionCalendarDays` cùng chính sách vùng/ngày |
| Lúc hết hạn đã xác định | `Instant expiresAt` |
| Ngày hết hạn theo nghiệp vụ | `LocalDate expirationDate` |

`Duration.ofDays(1)` là một thời lượng đúng 24 giờ theo hợp đồng API. Nó không tự biểu đạt “cùng giờ địa phương vào ngày lịch tiếp theo” ở vùng có chuyển đổi giờ.

Tương tự:

- `requestTimeout` là một lượng thời gian.
- `requestDeadline` là một thời điểm.
- `processingDelay` là một lượng dời.
- `scheduledAt` là thời điểm đã được quyết định.

Không đặt một `Duration` là `deadline` vì nơi gọi có thể hiểu đó là mốc tuyệt đối. Không đặt một `Instant` là `timeoutMillis` vì tên đó tuyên bố cả ý nghĩa lẫn kiểu biểu diễn khác.

Nếu một hàm cần tính hạn từ điểm bắt đầu, chữ ký rõ hơn là:

```java
Instant calculateExpiry(
        Instant activatedAt,
        Duration validityDuration);
```

Đây là chữ ký minh họa. Quy tắc cho `validityDuration` âm, bằng không hoặc vượt miền phải được xác định trong hiện thực. Tên tốt giúp thấy các vai trò, còn kiểm tra đầu vào thực thi hợp đồng đó.

## 5. Múi giờ: đặt tên theo vai trò, không theo môi trường máy

[ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html) có thể biểu diễn vùng có quy tắc như `Europe/Berlin` hoặc độ lệch cố định. `ZoneOffset` biểu diễn một độ lệch UTC cụ thể.

Các tên có vai trò rõ:

| Tên | Ý nghĩa dự kiến |
| --- | --- |
| `businessZone` | Vùng dùng để xác định ngày nghiệp vụ |
| `scheduleZone` | Vùng gắn với lịch địa phương |
| `displayZone` | Vùng dùng khi hiển thị một thời điểm |
| `sourceOffset` | Offset được nguồn cung cấp |
| `utcOffset` | Độ lệch UTC cụ thể |

`zone` trong một hàm nhỏ có một vai trò duy nhất có thể là đủ. Khi có hai vùng nguồn/đích hoặc vùng hiển thị/vùng nghiệp vụ, nên phân biệt bằng tên.

Không dùng `serverZone` như một thay thế ngầm cho `businessZone`. Việc máy chủ hiện tại chạy ở đâu không xác định đơn vị nghiệp vụ cần chia ngày theo vùng nào.

Tên `timezone` cho một số nguyên không nói rõ đó là số giờ hay số giây; nó cũng không biểu diễn quy tắc vùng. Nếu dữ liệu thật sự là một chuỗi định danh vùng, `zoneId` hoặc `scheduleZoneId` rõ hơn.

Không dùng các chữ viết tắt dễ đa nghĩa thay cho hợp đồng vùng đầy đủ. Một offset hiện tại cũng không đủ để thay tên vùng của một lịch lặp cần theo các quy tắc thay đổi trong tương lai.

### 5.1. Instant thường không cần hậu tố Utc để có ý nghĩa

`Instant occurredAt` đã biểu diễn thời điểm tuyệt đối, không có vùng hiển thị riêng trong đối tượng. Không cần mặc định đổi tất cả tên thành `occurredAtUtcInstant`.

Ở biên API, nếu cần nhấn mạnh chuỗi bắt buộc dùng dạng UTC kết thúc bằng `Z`, hãy ghi quy tắc biểu diễn đó trong tài liệu và bộ chuyển đổi. Tên `occurredAtUtc` chỉ có ích nếu dữ liệu thực sự tuân thủ; nó không tự kiểm tra chuỗi.

Đặc biệt, `LocalDateTime createdAtUtc` chỉ là một cam kết ngoài kiểu. Kiểu đó chưa mang offset; nếu cần lưu một thời điểm thực sự, cân nhắc `Instant` thay vì dựa riêng vào tên.

### 5.2. LocalDate không mang zone nhưng có thể được suy ra theo một zone

Một `LocalDate businessDate` không chứa vùng. Tuy nhiên, nếu nó được tính từ `Instant`, bước tính cần vùng nghiệp vụ:

```java
LocalDate businessDate =
        occurredAt.atZone(businessZone).toLocalDate();
```

Tên `businessDate` nói đây là ngày nghiệp vụ, không phải ngày UTC mặc định. Nếu cần lưu lại cách suy ra, phải lưu hoặc truyền thêm vùng/quy tắc tương ứng; bản thân tên không thể khôi phục dữ liệu đã bỏ.

Ngược lại, ngày sinh hoặc một ngày do người dùng nhập có thể có ý nghĩa như một ngày thuần, không nhất thiết được suy từ `Instant`. Không tự chèn múi giờ vào mọi trường `LocalDate` khi miền không yêu cầu.

## 6. Đặt tên theo sự kiện đã xảy ra

Một hệ thống nhận và xử lý sự kiện có thể có nhiều mốc:

| Trường | Ý nghĩa cần xác định |
| --- | --- |
| `occurredAt` | Nguồn cho biết sự kiện xảy ra lúc nào |
| `receivedAt` | Hệ thống nhận sự kiện lúc nào |
| `processedAt` | Hệ thống hoàn thành bước xử lý lúc nào |
| `persistedAt` | Mốc ghi nhận lưu trữ theo hợp đồng đã chọn |
| `scheduledAt` | Thời điểm được lên kế hoạch |
| `startedAt` | Thời điểm bắt đầu thực tế |
| `completedAt` | Thời điểm hoàn thành thực tế |

Nếu tất cả đều đặt tên `timestamp` hoặc `time`, khó biết mốc nào dùng để báo cáo độ trễ, mốc nào dùng để chia ngày và mốc nào do nguồn cung cấp.

Tên cũng nên giúp phân biệt dự kiến với thực tế. `scheduledStartAt` và `actualStartAt` có thể phù hợp khi hai mốc cùng xuất hiện. Không ghi thời gian dự kiến vào `completedAt` chỉ vì hiện chưa có mốc hoàn thành.

Nguồn đồng hồ là một phần cần tài liệu hóa. `occurredAt` do thiết bị gửi có thể không đồng bộ với `receivedAt` do máy chủ ghi. Tên rõ giúp nhận ra hai nguồn nhưng không bảo đảm chúng luôn có thứ tự thời gian đúng. Không suy quan hệ nhân quả hoặc độ trễ chắc chắn chỉ từ tên trường.

## 7. Ranh giới phải nói rõ bao gồm hay loại trừ

Các tên `start` và `end` chưa cho biết dữ liệu đúng tại `end` có thuộc khoảng không.

Với khoảng nửa mở, có thể dùng:

```java
Instant fromInclusive;
Instant toExclusive;
```

hoặc một kiểu có ý nghĩa nghiệp vụ hơn:

```java
record ValidityWindow(
        Instant activeFromInclusive,
        Instant expiresAtExclusive) {}
```

Bản ghi trên chỉ minh họa tên; chương trình đầy đủ bên dưới bổ sung kiểm tra và phương thức.

Hợp đồng `[activeFromInclusive, expiresAtExclusive)` nói rõ:

- Đúng mốc bắt đầu thì còn hiệu lực.
- Ngay trước mốc kết thúc thì còn hiệu lực.
- Đúng mốc kết thúc thì hết hiệu lực.

Một tên phổ biến như `expiresAt` vẫn dùng được nếu cả hệ thống đã định nghĩa rõ đúng mốc đó được coi là hết hạn. Hậu tố `Exclusive` hữu ích ở nơi có thể nhầm đầu mút hoặc khi một hàm xử lý nhiều loại khoảng.

Không để tên và toán tử mâu thuẫn. Biến tên `toExclusive` mà điều kiện dùng `<=` tạo ra hợp đồng sai ngay trong mã.

Với ngày, dùng `LocalDate startDateInclusive`/`endDateExclusive` nếu cần phân biệt rõ kiểu khoảng. Đừng đưa một ngày vào tham số `Instant` bằng cách tự gán giờ 00:00 ở vùng chưa được xác định.

## 8. Chương trình Java 17+ đầy đủ

Lưu thành `TemporalNamingDemo.java`. Ví dụ dùng giá trị cố định để tập trung vào hợp đồng tên và kiểu.

```java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;

public class TemporalNamingDemo {
    record ValidityWindow(
            Instant activeFromInclusive,
            Instant expiresAtExclusive) {

        ValidityWindow {
            Objects.requireNonNull(activeFromInclusive);
            Objects.requireNonNull(expiresAtExclusive);
            if (expiresAtExclusive.isBefore(activeFromInclusive)) {
                throw new IllegalArgumentException("Reversed validity window");
            }
        }

        boolean isActiveAt(Instant checkedAt) {
            Objects.requireNonNull(checkedAt);
            return !checkedAt.isBefore(activeFromInclusive)
                    && checkedAt.isBefore(expiresAtExclusive);
        }
    }

    static Duration requestTimeoutFromMillis(long requestTimeoutMillis) {
        if (requestTimeoutMillis <= 0) {
            throw new IllegalArgumentException("Timeout must be positive");
        }
        return Duration.ofMillis(requestTimeoutMillis);
    }

    static LocalDate businessDateOf(
            Instant occurredAt, ZoneId businessZone) {
        Objects.requireNonNull(occurredAt);
        Objects.requireNonNull(businessZone);
        return occurredAt.atZone(businessZone).toLocalDate();
    }

    public static void main(String[] args) {
        Instant occurredAt = Instant.parse("2024-01-01T00:00:00Z");
        long occurredAtEpochSeconds = occurredAt.getEpochSecond();
        long occurredAtEpochMillis = occurredAt.toEpochMilli();

        System.out.println("epoch seconds = " + occurredAtEpochSeconds);
        System.out.println("epoch millis = " + occurredAtEpochMillis);
        System.out.println("correct seconds conversion = "
                + Instant.ofEpochSecond(occurredAtEpochSeconds));
        System.out.println("correct millis conversion = "
                + Instant.ofEpochMilli(occurredAtEpochMillis));
        System.out.println("wrong unit conversion = "
                + Instant.ofEpochMilli(occurredAtEpochSeconds));

        Duration requestTimeout = requestTimeoutFromMillis(90_000);
        Instant requestDeadline = occurredAt.plus(requestTimeout);
        System.out.println("request timeout = " + requestTimeout);
        System.out.println("request deadline = " + requestDeadline);

        ValidityWindow window = new ValidityWindow(
                occurredAt, requestDeadline);
        System.out.println("active at start = "
                + window.isActiveAt(occurredAt));
        System.out.println("active just before expiry = "
                + window.isActiveAt(requestDeadline.minusNanos(1)));
        System.out.println("active at expiry = "
                + window.isActiveAt(requestDeadline));

        Instant lateEventOccurredAt =
                Instant.parse("2024-01-01T23:30:00Z");
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        System.out.println("UTC calendar date = " + businessDateOf(
                lateEventOccurredAt, ZoneId.of("UTC")));
        System.out.println("business date = " + businessDateOf(
                lateEventOccurredAt, businessZone));
        System.out.println("business zone ID = " + businessZone.getId());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TemporalNamingDemo.java
java TemporalNamingDemo
```

Stdout:

```text
epoch seconds = 1704067200
epoch millis = 1704067200000
correct seconds conversion = 2024-01-01T00:00:00Z
correct millis conversion = 2024-01-01T00:00:00Z
wrong unit conversion = 1970-01-20T17:21:07.200Z
request timeout = PT1M30S
request deadline = 2024-01-01T00:01:30Z
active at start = true
active just before expiry = true
active at expiry = false
UTC calendar date = 2024-01-01
business date = 2024-01-02
business zone ID = Asia/Ho_Chi_Minh
```

Điểm cần quan sát:

- Hai biến epoch có đơn vị khác nhau nhưng dùng đúng hàm thì cho cùng thời điểm.
- Dùng số giây với `ofEpochMilli` vẫn biên dịch và chạy, nhưng cho thời điểm sai ở năm 1970. Tên và chuyển đổi tại biên giúp tránh lỗi này.
- `requestTimeout` là thời lượng `90` giây; `requestDeadline` là một `Instant` cụ thể.
- `ValidityWindow` kiểm tra đúng hợp đồng đầu mút, không coi mốc hết hạn còn hiệu lực.
- Một sự kiện lúc `23:30Z` có ngày UTC là 01/01 nhưng ngày nghiệp vụ trong vùng `Asia/Ho_Chi_Minh` của ví dụ là 02/01.

Tên không tạo ra các quy tắc này, nhưng làm chúng xuất hiện rõ trong dòng mã và giúp việc kiểm chứng chọn đúng trường hợp.

## 9. API, cấu hình và schema cần giữ cùng ý nghĩa

### 9.1. Biên truyền dữ liệu nên công bố biểu diễn

Nếu API dùng số:

```json
{
  "occurredAtEpochMillis": 1704067200000,
  "requestTimeoutMillis": 90000
}
```

Nếu API dùng chuỗi thời điểm:

```json
{
  "occurredAt": "2024-01-01T00:00:00Z"
}
```

Đây là hai biểu diễn có hợp đồng khác nhau. Phải xác định phần giây, offset/UTC và cách xử lý đầu vào không hợp lệ. Tên `occurredAt` cho một chuỗi không tự cho biết mọi định dạng đều được chấp nhận.

Không tự đổi một trường từ giây sang mili giây mà giữ hợp đồng cũ. Người dùng API có thể tiếp tục gửi đúng dữ liệu theo tài liệu trước và nhận kết quả sai thay vì một lỗi rõ ràng.

Nếu phải đổi tên hoặc kiểu biểu diễn của API đã công bố, cần có chiến lược tương thích hoặc phiên bản. Nếu hỗ trợ đồng thời trường cũ và mới trong một giai đoạn, phải định nghĩa cách xử lý khi cả hai xuất hiện và mâu thuẫn; không âm thầm ưu tiên ngẫu nhiên.

### 9.2. Cấu hình số cần kèm đơn vị

Các tên cấu hình như `request-timeout-ms` hoặc `request-timeout-millis` cho biết đơn vị nếu định dạng chỉ nhận số. Nếu định dạng cho phép một thời lượng tự mô tả như `PT1M30S`, nên ghi rõ cú pháp được chấp nhận và chuyển thành `Duration`.

Một giá trị cấu hình `timeout=90` chưa nói được đó là giây hay mili giây. Đơn vị cần nằm ở tên, cú pháp hoặc schema được công bố rõ, tốt nhất không chỉ trong trí nhớ của người viết.

### 9.3. Tên cột không thay thế kiểu cột

Một cột tên `created_at` không chứng minh nó có múi giờ hoặc độ chính xác nào. Một cột tên `expires_at_epoch_millis` cần thực sự lưu đúng đơn vị đã công bố.

Mã Java, DTO, tài liệu API, câu SQL và migration phải thống nhất. Nếu cột chỉ lưu đến micro giây nhưng API giữ nano, quy tắc cắt/làm tròn hoặc từ chối cần nằm trong hợp đồng; một hậu tố tên không tự giải quyết độ chính xác.

Không gán hậu tố `_utc` cho một cột địa phương rồi coi lỗi múi giờ đã được sửa. Cần kiểm tra giá trị, kiểu cột và cách driver ánh xạ thực tế.

## 10. Null, trạng thái và các ý nghĩa thiếu dữ liệu

Một trường `completedAt` có thể chưa có vì tác vụ chưa hoàn thành. Một trường `expiresAt` không có có thể nghĩa là không hết hạn, chưa xác định hoặc chưa được cấu hình. Ba ý nghĩa đó không tự động giống nhau.

Tên và kiểu có thể kết hợp với mô hình trạng thái:

- Nếu `null` nghĩa là chưa hoàn thành, nêu rõ quan hệ với trạng thái tác vụ.
- Nếu không hết hạn là một lựa chọn thật của miền, biểu đạt lựa chọn đó rõ, tránh một ngày “rất xa” làm giá trị giả.
- Nếu thời điểm bắt buộc, từ chối thiếu dữ liệu ở biên thay vì gán epoch hoặc thời gian hiện tại.

Không đặt tên `optionalDate` mà không nói đó là ngày gì. Từ “optional” chỉ mô tả việc có thể thiếu, chưa cho biết ý nghĩa nghiệp vụ. `deliveryDate` với hợp đồng thiếu rõ ràng thường dễ hiểu hơn.

## 11. Tên rõ vẫn cần kiểu và kiểm tra bảo vệ

Một hàm `sendAfterMillis(long delayMillis)` rõ hơn `send(long time)`, nhưng người gọi vẫn có thể truyền nhầm số giây. Nếu có thể, dùng `Duration` ở bên trong và chỉ nhận số nguyên ở biên cần tương thích.

Khi có nhiều đại lượng cùng kiểu nhưng dễ đảo vị trí, có thể tạo một bản ghi có ý nghĩa thay vì một danh sách tham số dài. Ví dụ `ValidityWindow` gom hai đầu mút và kiểm tra thứ tự một lần.

Tuy nhiên, không cần tạo một lớp riêng cho mọi biến thời gian ngắn. Cân nhắc theo nguy cơ nhầm ý nghĩa, số nơi sử dụng và lợi ích của việc giữ bất biến/ràng buộc.

Tên dài cũng không tự tốt hơn tên ngắn. Trong một hàm nhỏ chỉ xử lý một `LocalDate`, `date` có thể đủ rõ. Trong một hàm có ngày giao, ngày lập báo cáo và ngày tiếp nhận, những tên đầy đủ theo vai trò sẽ quan trọng hơn.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Mọi trường đều tên `timestamp` | Không biết mốc nghiệp vụ nào | Đặt theo sự kiện: `occurredAt`, `receivedAt`... |
| Số `long` không có đơn vị | Truyền nhầm giây/mili giây | Nêu epoch và đơn vị ở biên |
| Đặt `LocalDateTime` là `instant` | Tên hứa nhiều hơn dữ liệu | Dùng đúng kiểu hoặc nêu rõ địa phương |
| Đặt thời lượng là `deadline` | Nhầm lượng chờ với mốc tuyệt đối | Phân biệt `Duration` và `Instant` |
| Tên `days` không nói ngày lịch hay 24 giờ | Sai phép cộng qua chuyển đổi giờ | Nêu hợp đồng lịch/thời lượng |
| Đổi đơn vị nhưng chỉ đổi giá trị hoặc chỉ đổi tên | Lệch dữ liệu giữa các lớp | Đổi và kiểm chứng cả hợp đồng |
| Dùng `offset` cho nhiều ý nghĩa | Nhầm offset UTC với lượng dời | Đặt theo vai trò và kiểu |
| Dùng vùng máy chủ cho ngày nghiệp vụ | Ngày đổi theo môi trường | Truyền `businessZone` rõ ràng |
| `toExclusive` nhưng lọc cả đầu cuối | Lệch kết quả tại ranh giới | Đồng bộ tên với toán tử |
| Dùng epoch hoặc ngày xa làm tín hiệu thiếu | Trộn giá trị thật với trạng thái | Mô hình hóa trạng thái thiếu rõ |

## 13. Tự kiểm chứng và thực hành

1. Đổi chữ ký `configure(long time, int offset)` thành hai chữ ký theo hai mục đích khác nhau: cấu hình timeout và đặt lịch giờ địa phương. Chọn kiểu cho đúng, không chỉ đổi tên.
2. Tìm lỗi khi nhận `1704067200` vào biến tên `occurredAtEpochMillis`. Giải thích vì sao số chữ số chỉ có thể là dấu hiệu để điều tra, không thay hợp đồng nguồn.
3. Thiết kế ba trường riêng cho lúc xảy ra, lúc nhận và lúc xử lý một sự kiện. Nêu nguồn đồng hồ của từng trường.
4. Đặt tên đầu mút cho khoảng báo cáo nửa mở và viết điều kiện kiểm tra đúng đầu cuối.
5. Mô tả khác nhau giữa `LocalDate expirationDate` và `Instant expiresAt`. Thông tin nào còn cần nếu muốn chuyển từ ngày thành mốc hết hạn?
6. Đổi một cấu hình số mili giây thành `Duration` tại biên. Kiểm tra số âm, số không và số vượt phạm vi ứng dụng cho phép.
7. Với một sự kiện gần nửa đêm UTC, kiểm tra ngày nghiệp vụ bằng hai vùng khác nhau và giải thích tên vùng trong chữ ký hàm.
8. Thiết kế API dùng số epoch và API dùng chuỗi thời điểm. Công bố rõ đơn vị/định dạng, phần giây và cách xử lý dữ liệu sai.
9. Chọn ý nghĩa của `null` cho `expiresAt`. Nếu “không hết hạn” và “chưa xác định” đều tồn tại, không gộp chúng chỉ vì cùng chưa có một `Instant`.
10. Rà một hàm có nhiều tham số ngày giờ: với mỗi tham số, xác định loại thông tin, vai trò nghiệp vụ, đơn vị nếu có, vùng diễn giải và quy ước đầu mút. Những phần chưa rõ là điểm cần sửa ở hợp đồng.

Một tên thời gian tốt giúp người đọc biết đang cầm dữ liệu gì và phải dùng nó ra sao. Kết hợp tên theo nghiệp vụ với kiểu Java phù hợp, chuyển đổi rõ ở biên và kiểm tra ràng buộc sẽ giảm đáng kể những lỗi mà trình biên dịch không thể tự phát hiện từ các số hoặc chuỗi rời rạc.
