# Localized date handling — Xử lý ngày giờ theo ngôn ngữ và múi giờ

Trong luồng khôi phục tài khoản, một thông báo như “Liên kết hết hạn lúc 09:10” chỉ hữu ích khi người dùng hiểu đó là ngày nào và theo múi giờ nào. Người nhận có thể đang đi công tác, dùng giao diện tiếng Việt trên thiết bị đặt ở nước khác hoặc đọc email sau nhiều giờ.

Bài học này thuộc module SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY. Mục tiêu là trình bày thời gian rõ ràng khi khôi phục mật khẩu, MFA, passkey và thiết bị xác thực, đồng thời giữ nguyên quyết định bảo mật ở máy chủ. Các thời hạn và API trong bài là ví dụ thiết kế, không phải thông số áp dụng chung cho mọi hệ thống.

## 1. Bốn khái niệm cần tách biệt

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Thời điểm tuyệt đối — instant | Sự kiện xảy ra ở điểm nào trên dòng thời gian? | `2026-11-23T02:10:00Z` |
| Múi giờ — time zone | Điểm đó tương ứng giờ dân sự nào tại một vùng? | `Asia/Ho_Chi_Minh` |
| Ngôn ngữ và quy ước vùng — locale | Viết ngày, tháng, giờ như thế nào? | `vi-VN`, `en-US` |
| Khoảng thời gian — duration | Hai thời điểm cách nhau bao lâu? | 10 phút |

Trong Java, `Instant` biểu diễn một điểm trên dòng thời gian. Đây là kiểu thích hợp để mô hình hóa mốc phát hành hoặc hết hạn. [Oracle: Instant](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html)

Ví dụ, cùng thời điểm `2026-11-23T02:10:00Z` có thể được trình bày dưới các offset cố định sau:

| Offset hiển thị | Giờ tương ứng |
| --- | --- |
| UTC | 02:10 ngày 23/11/2026 |
| UTC+07:00 | 09:10 ngày 23/11/2026 |
| UTC−05:00 | 21:10 ngày 22/11/2026 |

Bảng dùng offset cố định để làm rõ phép chuyển đổi; nó không mô tả quy tắc cả năm của một vùng địa lý.

Ba quy tắc nền tảng:

1. Đổi locale không đổi thời điểm hết hạn.
2. Đổi múi giờ chỉ đổi cách nhìn thời điểm, không cấp thêm thời gian sử dụng.
3. Chuỗi đã bản địa hóa dành cho con người đọc, không được dùng làm dữ liệu đầu vào cho kiểm tra token.

## 2. Locale không phải múi giờ

Một người dùng có thể chọn tiếng Việt nhưng đang sống ở Paris. Một người dùng ở Việt Nam cũng có thể chọn giao diện tiếng Anh.

Vì vậy, không dùng các suy luận sau:

- `vi-VN` luôn có nghĩa là `Asia/Ho_Chi_Minh`.
- Đuôi email hoặc số điện thoại đủ để xác định múi giờ hiện tại.
- Ngôn ngữ trình duyệt quyết định giờ địa phương.
- Múi giờ mặc định của máy chủ là múi giờ của người nhận.

Trong ví dụ thiết kế của bài, lựa chọn hiển thị được giải quyết độc lập:

| Thông tin | Thứ tự ưu tiên minh họa |
| --- | --- |
| Locale | Lựa chọn đã lưu → ngôn ngữ được hỗ trợ từ trình duyệt → locale mặc định của sản phẩm |
| Múi giờ | Lựa chọn đã lưu → gợi ý từ thiết bị đang dùng → UTC được ghi nhãn rõ |

Gợi ý từ thiết bị chỉ phục vụ hiển thị. Nó không chứng minh vị trí thật hoặc quyền sở hữu tài khoản, cũng không tự cập nhật hồ sơ người dùng.

`ZoneId` phân biệt offset cố định với vùng có tập quy tắc chuyển đổi. Một region ID như `Europe/Paris` có thể có offset khác nhau ở các thời điểm khác nhau. [Oracle: ZoneId](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html)

Tránh viết tắt như `CST` khi cần diễn đạt chính xác. Nhãn đầy đủ hoặc region ID cùng offset tại thời điểm đang hiển thị giúp người dùng và nhân viên hỗ trợ đối chiếu dễ hơn.

## 3. Hợp đồng thời gian của luồng khôi phục

Trước khi định dạng, cần xác định ý nghĩa các trường dữ liệu.

| Trường | Ý nghĩa | Nguồn quyết định |
| --- | --- | --- |
| `issuedAt` | Thời điểm máy chủ phát hành yêu cầu hoặc bí mật | Backend |
| `expiresAt` | Mốc kết thúc hiệu lực | Backend và chính sách khôi phục |
| `serverNow` | Thời điểm máy chủ tạo phản hồi hiện tại | Backend |
| `resendAvailableAt` | Mốc sớm nhất có thể xin gửi lại theo trạng thái hiện tại | Backend |
| `displayLocale` | Quy ước trình bày | Lựa chọn giao diện được hỗ trợ |
| `displayTimeZone` | Múi giờ hiển thị | Lựa chọn giao diện hợp lệ |

`serverNow` phải được lấy mới cho phản hồi; nó không phải bản sao của `issuedAt` từ lần phát hành trước.

API minh họa:

```json
{
  "issuedAt": "2026-11-23T02:00:00Z",
  "expiresAt": "2026-11-23T02:10:00Z",
  "serverNow": "2026-11-23T02:00:05Z",
  "resendAvailableAt": "2026-11-23T02:00:30Z"
}
```

Hợp đồng của ví dụ chọn timestamp UTC, có `Z`, với phần giây thập phân tối đa ở độ chính xác mili giây. Số epoch, nếu sử dụng thay chuỗi, phải ghi rõ đơn vị giây hay mili giây.

RFC 3339 là một profile của ISO 8601 cho timestamp trên Internet. Không nên gọi mọi chuỗi trông giống ngày giờ là một timestamp phù hợp hợp đồng. [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339.html)

Các biểu diễn dễ gây lỗi:

```text
23/11/2026 09:10
11/23/2026 09:10
2026-11-23T09:10:00
```

Hai dòng đầu phụ thuộc cách đọc địa phương. Dòng cuối thiếu offset nên chưa xác định một thời điểm toàn cầu.

Hợp đồng cũng cần quy định:

- Độ chính xác lưu trữ và so sánh phải nhất quán giữa ứng dụng và cơ sở dữ liệu.
- Không cắt phần giây ở một tầng rồi dùng giá trị đã cắt để kéo dài hiệu lực.
- Không gửi thời điểm hết hạn hoặc trạng thái riêng của một tài khoản qua endpoint công khai trước khi có ngữ cảnh phù hợp.
- Một request chỉ đọc lại trạng thái không được tạo lại `expiresAt` bằng “hiện tại cộng thời hạn”.
- Dữ liệu đã hết hạn, đã dùng hoặc bị thu hồi vẫn phải được xử lý theo trạng thái giao dịch.

Không ghi thời hạn vào chuỗi dịch rồi cố phân tích lại. Ví dụ “Hết hạn vào {deadline}” thuộc tài nguyên ngôn ngữ; `deadline` được định dạng từ dữ liệu thời gian chuẩn.

## 4. Tính hiệu lực bằng thời điểm tuyệt đối trong Java

Giả sử chính sách minh họa cho một loại token là 10 phút. Phạm vi sử dụng được diễn đạt:

```text
issuedAt <= now < expiresAt
```

Mốc `expiresAt` là cận trên không bao gồm. Tại đúng mốc đó, token không còn nằm trong khoảng hiệu lực.

Ví dụ Java sau chỉ mô hình hóa dữ liệu thời gian:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Objects;

public final class RecoveryTimePolicy {
    private final Clock clock;
    private final Duration lifetime;

    public RecoveryTimePolicy(Clock clock, Duration lifetime) {
        this.clock = Objects.requireNonNull(clock);
        this.lifetime = Objects.requireNonNull(lifetime);

        if (lifetime.isZero() || lifetime.isNegative()) {
            throw new IllegalArgumentException("Lifetime must be positive");
        }
    }

    public record Lifetime(Instant issuedAt, Instant expiresAt) {
    }

    public Lifetime issueLifetime() {
        Instant issuedAt = clock.instant()
                .truncatedTo(ChronoUnit.MILLIS);
        Instant expiresAt = issuedAt.plus(lifetime);
        return new Lifetime(issuedAt, expiresAt);
    }

    public boolean isWithinLifetime(Lifetime storedLifetime) {
        Instant now = clock.instant();
        return !now.isBefore(storedLifetime.issuedAt())
                && now.isBefore(storedLifetime.expiresAt());
    }
}
```

Cách khởi tạo minh họa:

```java
RecoveryTimePolicy timePolicy = new RecoveryTimePolicy(
        Clock.systemUTC(),
        Duration.ofMinutes(10)
);
```

Trong ví dụ này, cấu hình lifetime nên là số mili giây nguyên và nằm trong giới hạn chính sách của sản phẩm. `issueLifetime()` chỉ được gọi khi thật sự phát hành; kết quả phải gắn với bản ghi giao dịch được lưu. Không gọi lại phương thức đó mỗi lần người dùng mở email hoặc tải lại trang.

`Clock` cho phép truyền nguồn thời gian vào thành phần cần dùng, thay vì để mỗi nơi tự lấy giờ theo cách riêng. Tuy nhiên, abstraction này không tự bảo đảm đồng hồ máy chủ chính xác. [Oracle: Clock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html)

`isWithinLifetime` chỉ kiểm tra điều kiện thời gian. Nó không xác minh bí mật, quyền sở hữu, số lần thử, trạng thái đã dùng hoặc mức rủi ro. Việc kiểm tra và tiêu thụ token còn phải bảo đảm tính nhất quán khi có nhiều request.

Không thay đoạn so sánh trên bằng:

```java
// Sai hướng thiết kế: giá trị phụ thuộc cách hiển thị và mất ngữ nghĩa instant.
String nowText = java.time.LocalDateTime.now().toString();
boolean accepted = nowText.compareTo(userVisibleDeadline) < 0;
```

Cũng không lấy `LocalDate.now()` rồi cho token sống đến cuối ngày. “Mười phút từ khi phát hành” và “đến hết ngày địa phương” là hai chính sách khác nhau.

## 5. Định dạng deadline ở backend

Backend thường cần định dạng thời gian cho email, SMS hoặc tài liệu hỗ trợ. Cần truyền rõ locale và múi giờ thay vì dùng cấu hình mặc định của máy chạy ứng dụng.

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.chrono.IsoChronology;
import java.time.format.DateTimeFormatter;
import java.time.format.FormatStyle;
import java.util.Locale;

public final class RecoveryDeadlineText {
    public static String format(
            Instant expiresAt,
            Locale locale,
            ZoneId displayZone
    ) {
        DateTimeFormatter formatter =
                DateTimeFormatter.ofLocalizedDateTime(
                        FormatStyle.MEDIUM,
                        FormatStyle.MEDIUM
                )
                .withLocale(locale)
                .withChronology(IsoChronology.INSTANCE)
                .withZone(displayZone);

        ZoneOffset offset = displayZone.getRules().getOffset(expiresAt);
        String offsetLabel = offset.equals(ZoneOffset.UTC)
                ? "UTC"
                : "UTC" + offset.getId();

        return formatter.format(expiresAt)
                + " (" + displayZone.getId()
                + ", " + offsetLabel + ")";
    }
}
```

Ví dụ sử dụng:

```java
String deadline = RecoveryDeadlineText.format(
        Instant.parse("2026-11-23T02:10:00Z"),
        Locale.forLanguageTag("vi-VN"),
        ZoneId.of("Asia/Ho_Chi_Minh")
);
```

Trong phương án này, sản phẩm chọn lịch ISO/Gregorian cho thông báo bảo mật. Đó là lựa chọn có chủ đích, không phải kết luận rằng mọi locale đều dùng cùng loại lịch.

Formatter hỗ trợ locale, chronology và zone riêng biệt. Khi dùng pattern, cần phân biệt `u` với `y`, `Y`; `M` với `m`. Chẳng hạn `Y` là năm theo tuần, còn `m` là phút. [Oracle: DateTimeFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html)

Nếu phải dùng pattern cố định cho công cụ vận hành, một lựa chọn rõ nghĩa là:

```text
uuuu-MM-dd HH:mm:ss XXX
```

Pattern này phục vụ trường hợp cố định của công cụ, không tự thay thế việc bản địa hóa mọi giao diện.

Về lựa chọn hiển thị:

- Dùng tên tháng khi chuỗi ngày toàn chữ số dễ gây nhầm.
- Thông báo khôi phục nên có ngày đầy đủ khi sự kiện có thể qua nửa đêm.
- Giữ múi giờ ở gần deadline, không chỉ giấu trong trang cài đặt.
- Offset phải được lấy tại `expiresAt`, không mặc định là offset đang áp dụng ở thời điểm gửi.
- Dấu câu và thứ tự thành phần có thể khác giữa runtime hoặc dữ liệu locale; không dùng chuỗi đã format làm định danh hay khóa so sánh.

## 6. Định dạng phía trình duyệt bằng Intl

Trình duyệt nhận timestamp chuẩn và tạo chuỗi hiển thị theo lựa chọn người dùng. Không đưa chuỗi đã dịch vào `Date.parse`.

Ví dụ dưới đây giả định `expiresAt` đã đáp ứng hợp đồng UTC của API. Kiểm tra `Invalid Date` ở client chỉ là phòng lỗi hiển thị, không thay thế kiểm tra dữ liệu ở máy chủ.

```javascript
const supportedLocales = new Set(["vi-VN", "en-US", "en-GB"]);

function formatRecoveryDeadline(expiresAt, requestedLocale, requestedZone) {
  const instant = new Date(expiresAt);

  if (Number.isNaN(instant.getTime())) {
    throw new Error("Invalid recovery timestamp");
  }

  const localeCandidates = supportedLocales.has(requestedLocale)
    ? [requestedLocale, "vi-VN", "en"]
    : ["vi-VN", "en"];

  const options = {
    dateStyle: "long",
    timeStyle: "long",
    calendar: "gregory"
  };

  let formatter;

  try {
    formatter = new Intl.DateTimeFormat(localeCandidates, {
      ...options,
      timeZone: requestedZone || "UTC"
    });
  } catch (error) {
    if (!(error instanceof RangeError)) {
      throw error;
    }

    formatter = new Intl.DateTimeFormat(localeCandidates, {
      ...options,
      timeZone: "UTC"
    });
  }

  const resolved = formatter.resolvedOptions();

  return {
    text: formatter.format(instant),
    timeZone: resolved.timeZone,
    locale: resolved.locale
  };
}
```

Khi fallback về UTC, hàm trả cả múi giờ thực sự được dùng. Giao diện phải hiển thị nhãn đó, không tiếp tục ghi tên múi giờ mà người dùng đã yêu cầu nhưng runtime từ chối.

`Intl.DateTimeFormat` hỗ trợ định dạng theo ngôn ngữ và các tùy chọn thời gian. `resolvedOptions()` cho biết các tùy chọn được giải quyết khi tạo formatter. [MDN: Intl.DateTimeFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat)

Ví dụ HTML và cách gắn nội dung:

```html
<p>
  Liên kết có hiệu lực trước:
  <time id="deadline"></time>
  <span id="deadline-zone"></span>
</p>
```

```javascript
const expiresAt = "2026-11-23T02:10:00Z";
const displayed = formatRecoveryDeadline(
  expiresAt,
  "vi-VN",
  "Asia/Ho_Chi_Minh"
);

const timeElement = document.querySelector("#deadline");
timeElement.dateTime = expiresAt;
timeElement.textContent = displayed.text;

document.querySelector("#deadline-zone").textContent =
  " — " + displayed.timeZone;
```

`<time datetime="…">` giữ biểu diễn máy đọc được bên cạnh nội dung dành cho người dùng. Nó không tự chuyển đổi hay dịch ngày giờ. [WHATWG: The time element](https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-time-element)

Đổi locale hoặc múi giờ chỉ cần định dạng lại cùng `expiresAt`. Không gọi endpoint phát hành token mới để đổi cách trình bày.

Nếu cần tách thành phần ngày giờ để làm giao diện riêng, dùng API phù hợp như `formatToParts`. Không `split("/")` hoặc tách theo dấu phẩy vì dấu phân cách không cố định giữa các locale.

## 7. Đồng hồ đếm ngược chỉ là ước lượng giao diện

Thông báo tuyệt đối và tương đối bổ sung cho nhau:

```text
Liên kết có hiệu lực trước 09:10 ngày 23/11/2026, UTC+07:00.
Còn khoảng 8 phút theo thông tin mới nhất từ máy chủ.
```

Câu thứ nhất giúp đối chiếu email và lịch sử sự kiện. Câu thứ hai giảm nhu cầu tự tính nhẩm.

Không dùng đồng hồ của thiết bị làm nguồn cấp quyền. Nếu người dùng đặt giờ máy tính chậm một tiếng, hiệu lực token vẫn phải do backend quyết định.

Ví dụ ước lượng dựa trên `serverNow` và thời gian đã trôi qua trong trang:

```javascript
function createRemainingEstimate(serverNow, expiresAt) {
  const serverMillis = Date.parse(serverNow);
  const expiresMillis = Date.parse(expiresAt);

  if (!Number.isFinite(serverMillis) || !Number.isFinite(expiresMillis)) {
    throw new Error("Invalid timing response");
  }

  const receivedAt = performance.now();

  return function remainingSeconds() {
    const elapsedMillis = performance.now() - receivedAt;
    const estimatedMillis = expiresMillis - serverMillis - elapsedMillis;

    return Math.max(0, Math.ceil(estimatedMillis / 1000));
  };
}
```

Đây là ước lượng tại giao diện. Độ trễ từ lúc máy chủ tạo phản hồi đến lúc trang nhận được khiến số còn lại có thể lớn hơn thực tế. Khi tab hoặc thiết bị ngủ rồi hoạt động lại, nên lấy trạng thái mới nếu cần thay vì coi giá trị cũ là chắc chắn.

Các quy ước sản phẩm cho ví dụ:

- Mỗi lần cập nhật, tính lại từ mốc đã ghi; không chỉ lấy biến `seconds` trừ đi một.
- Không phát thông báo cho trình đọc màn hình từng giây.
- Không để số âm xuất hiện khi mã đã hết hạn.
- Khi đồng hồ về không, thông báo rằng hạn sử dụng có thể đã kết thúc và cung cấp hành động tiếp theo.
- Khi người dùng submit, backend kiểm tra lại; số giây còn trên trang không phải bằng chứng token vẫn hợp lệ.
- Nếu định dạng tương đối cho nhiều ngôn ngữ, dùng cơ chế xử lý đơn vị và số nhiều thích hợp, thay vì ghép chuỗi theo ngữ pháp của một ngôn ngữ.

Một nút đã được phép theo đồng hồ giao diện vẫn có thể bị máy chủ từ chối do giới hạn yêu cầu hoặc thay đổi trạng thái. Giao diện phải giải thích phản hồi mới đó.

## 8. DST: ngày địa phương không luôn có 24 giờ

Ở vùng có thay đổi giờ mùa hè, giờ dân sự có thể nhảy qua một khoảng hoặc lặp lại một khoảng. Bởi vậy, “cộng một ngày theo lịch địa phương” và “cộng đúng 24 giờ đã trôi qua” không luôn cho cùng kết quả.

Với token có thời hạn tính bằng phút, cách diễn đạt nhất quán là:

```java
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(10));
```

Không chuyển sang ngày giờ địa phương rồi mới cộng phút và bỏ thông tin zone. Nếu có chính sách riêng như “chỉ xử lý sau 09:00 ngày làm việc tiếp theo”, đó là quy tắc lịch khác, cần mô hình hóa độc lập.

Hầu hết màn hình khôi phục không cần người dùng nhập deadline. Nếu công cụ hỗ trợ cho phép nhập một giờ địa phương, phải xử lý ba trường hợp:

| Số offset hợp lệ | Ý nghĩa | Hành vi đề xuất |
| --- | --- | --- |
| 0 | Giờ nằm trong khoảng bị bỏ qua | Yêu cầu chọn giờ hợp lệ, không âm thầm sửa |
| 1 | Giờ được xác định duy nhất | Chuyển sang instant |
| 2 | Giờ nằm trong khoảng lặp thông thường | Yêu cầu làm rõ lần xuất hiện hoặc offset |

`ZoneRules.getValidOffsets` cung cấp thông tin về offset hợp lệ cho một `LocalDateTime`, giúp nhận biết các trường hợp này. [Oracle: ZoneRules](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRules.html)

Ví dụ hàm dành cho công cụ nội bộ, chỉ nhận thời gian không mơ hồ:

```java
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

static Instant resolveUnambiguous(
        LocalDateTime localDateTime,
        ZoneId zone
) {
    List<ZoneOffset> offsets = zone.getRules()
            .getValidOffsets(localDateTime);

    if (offsets.size() != 1) {
        throw new DateTimeException(
                "Choose an unambiguous local time or specify an offset"
        );
    }

    return localDateTime.toInstant(offsets.get(0));
}
```

Đây là một phương án từ chối đầu vào chưa rõ, không phải chính sách duy nhất. Nếu hệ thống cho phép chọn offset khi giờ lặp, cần xác nhận offset được chọn thật sự hợp lệ với vùng và thời điểm nhập.

Khi dữ liệu múi giờ trong các runtime khác nhau, cách trình bày có thể lệch ở một số vùng hoặc mốc chuyển đổi. Hệ thống nên quản lý phiên bản dữ liệu múi giờ; phép kiểm tra hiệu lực vẫn dựa trên instant đã lưu.

## 9. Ngày thuần túy khác timestamp

Không phải trường nào chứa ngày cũng cần đổi múi giờ.

| Dữ liệu | Kiểu ý nghĩa phù hợp |
| --- | --- |
| Thời điểm gửi hướng dẫn | Instant |
| Thời điểm đăng ký lại MFA | Instant |
| Deadline token | Instant |
| Ngày sinh trên hồ sơ, nếu thật sự cần dùng | Ngày theo lịch, không có giờ |
| Lịch hẹn hỗ trợ ở một địa điểm | Ngày giờ địa phương kèm zone và quy tắc giải quyết |

Ví dụ ngày `1990-04-03` không nên bị đổi thành ngày hôm trước chỉ vì trình duyệt ở múi giờ khác. Với ngày thuần túy, lưu và truyền theo hợp đồng date-only; đừng ép thành “nửa đêm UTC” rồi hiển thị như timestamp.

Nếu biểu mẫu thật sự cần ngày địa phương:

- Cho biết thứ tự ngày, tháng, năm và có ví dụ phù hợp.
- Phân tích theo định dạng đã xác định, không đoán nhiều kiểu cho cùng một chuỗi.
- Từ chối ngày không tồn tại; không tự sửa “31 tháng 4” thành một ngày khác.
- Với lịch khác Gregorian, xác định rõ lịch ở bước nhập và cách chuyển đổi.
- Không dùng một ngày dễ biết như ngày sinh làm bằng chứng duy nhất để trao quyền khôi phục.

Đối với quy trình thông thường, người dùng không nên phải gõ lại thời điểm hết hạn để xác minh mình là chủ tài khoản. Timestamp là ngữ cảnh thông báo, không phải bí mật sở hữu.

## 10. Nội dung email và thông báo bảo mật

Email có thể được đọc nhiều lần, chuyển tiếp tới hỗ trợ hoặc mở trên thiết bị có múi giờ khác. Vì vậy, cần để lại đủ ngữ cảnh ngay trong thông điệp.

Mẫu nội dung minh họa:

```text
Bạn vừa yêu cầu khôi phục quyền truy cập.

Hướng dẫn này có hiệu lực trước:
[ngày và giờ đã bản địa hóa] ([múi giờ/offset được dùng]).

Nếu bạn không gửi yêu cầu này, hãy làm theo hướng dẫn bảo vệ tài khoản.
```

Những lựa chọn nội dung cần thống nhất:

- Dùng mốc tuyệt đối cho email; câu “còn 10 phút” sẽ sai khi người nhận đọc muộn.
- Nêu “tính từ lúc phát hành” nếu nói về thời lượng, không ngụ ý email mở ra thì thời hạn mới bắt đầu.
- Không dùng “hôm nay” hoặc “ngày mai” làm thông tin duy nhất.
- Khi có chờ xử lý, phân biệt “được phép tiếp tục từ thời điểm…” với “yêu cầu có hiệu lực đến thời điểm…”.
- Nếu thời điểm nằm qua nửa đêm, hiển thị ngày của chính deadline sau khi đổi zone.
- Khi phải fallback về UTC, nói rõ UTC thay vì để người dùng tự suy.
- Bản dịch thay đổi câu chữ, không thay đổi khoảng hiệu lực.

Với người cần thêm thời gian thao tác, sản phẩm có thể cung cấp cơ chế xin hướng dẫn mới hoặc một quy trình hỗ trợ được phép. Việc bản địa hóa thông báo không tự gia hạn token, bỏ qua kiểm soát session hay giảm yêu cầu xác minh danh tính.

## 11. Vận hành, dữ liệu và quyền riêng tư

Ngày giờ còn xuất hiện trong log và màn hình của nhân viên hỗ trợ. Hai người nhìn hai múi giờ khác nhau có thể tưởng rằng đang nói về hai yêu cầu khác nhau.

Một cách tổ chức thông tin:

| Nơi dùng | Biểu diễn ưu tiên trong thiết kế này |
| --- | --- |
| Bản ghi giao dịch | Instant và trường trạng thái riêng |
| API giữa các thành phần | Timestamp chuẩn, đơn vị và độ chính xác rõ |
| Log kỹ thuật | Timestamp UTC với thông tin tương quan không chứa bí mật |
| Giao diện người dùng | Ngày giờ theo locale và zone được chọn, có nhãn |
| Màn hình hỗ trợ | Cho thấy giờ hiển thị và giá trị UTC khi cần đối chiếu |

Không ghi token, mã dự phòng hoặc toàn bộ liên kết khôi phục chỉ để tìm lại sự kiện theo thời gian. Locale và múi giờ cũng là thông tin có thể phản ánh sở thích hoặc bối cảnh của người dùng; chỉ thu thập và lưu theo nhu cầu thực tế.

Trong hệ thống nhiều máy chủ:

- Đồng hồ giữa các thành phần cần được quản lý và theo dõi.
- Một quy ước UTC thống nhất không có nghĩa mọi máy đã đồng bộ chính xác.
- Nếu có dung sai lệch đồng hồ, chính sách phải nói rõ phạm vi; không tự cộng thêm thời gian tại mỗi tầng.
- Nguồn thời gian dùng để tiêu thụ token phải được xác định, tránh để ứng dụng và truy vấn cơ sở dữ liệu ra quyết định theo các đồng hồ khác nhau mà không có chủ đích.
- Gia hạn, thu hồi và tiêu thụ token là thay đổi trạng thái có kiểm soát, không phải thao tác format ngày giờ.

Locale có thể ảnh hưởng cache của email template hoặc chuỗi hiển thị. Không đưa dữ liệu riêng của một yêu cầu khôi phục vào cache dùng chung mà thiếu phạm vi phân tách phù hợp.

## 12. Những tình huống làm rõ yêu cầu

Bảng dưới là tình huống để thảo luận khi thiết kế sản phẩm, không giả định một chuỗi định dạng cụ thể xuất hiện giống hệt trên mọi runtime.

| Tình huống | Điều cần giữ đúng |
| --- | --- |
| Người dùng đổi từ tiếng Việt sang tiếng Anh | `expiresAt` không thay đổi |
| Người dùng đổi zone khi đi công tác | Giờ và có thể cả ngày thay đổi, hiệu lực không đổi |
| Thiết bị đặt giờ chậm | Backend vẫn quyết định hạn dùng |
| Yêu cầu gửi lúc gần nửa đêm | Thông báo dùng ngày thật của deadline trong zone hiển thị |
| Người dùng đọc email sau vài giờ | Có mốc tuyệt đối, không dựa riêng vào “còn vài phút” |
| Region ID không được runtime hỗ trợ | Fallback có nhãn múi giờ thực tế |
| Giao dịch tới đúng `expiresAt` | Xử lý theo cận trên không bao gồm |
| Có chuyển đổi DST | Không tính lifetime bằng giờ địa phương thiếu zone |
| Trình duyệt ngủ rồi hoạt động lại | Thông tin thời gian được cập nhật khi cần |
| Trường dữ liệu chỉ chứa ngày | Không chuyển zone như một timestamp |
| Nhân viên hỗ trợ nhìn một zone khác | Có thông tin UTC để đối chiếu cùng sự kiện |
| Người dùng tải lại trang nhiều lần | Không tự tạo thêm thời gian hiệu lực |

Câu hỏi quan trọng nhất là: **Người dùng đang nhìn cách trình bày nào của cùng một thời điểm, và thành phần nào có quyền quyết định hiệu lực?** Khi hai trách nhiệm đó được giữ rõ, bản địa hóa giúp người dùng hiểu thông báo mà không làm biến đổi ranh giới bảo mật.