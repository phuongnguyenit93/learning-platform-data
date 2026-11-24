# Business day calculation — Tính ngày làm việc an toàn trong quy tắc nghiệp vụ

## 1. Vì sao tính ngày làm việc là vấn đề bảo mật logic nghiệp vụ?

Trong chương **Time Based Rules**, tính ngày làm việc không chỉ là tiện ích hiển thị ngày. Kết quả có thể quyết định một yêu cầu còn được phê duyệt, đơn hàng còn được sửa, hạn mức tạm giữ đã phải giải phóng hay người dùng còn được thực hiện một thao tác có điều kiện.

Nếu backend tin vào ngày hết hạn do client gửi, bỏ qua múi giờ của nghiệp vụ hoặc tính lại thời hạn từ thời điểm mỗi lần retry, người dùng có thể kéo dài quyền thao tác ngoài giới hạn. Một phép tính đúng khi chạy đơn lẻ cũng chưa bảo vệ được hệ thống nếu tác vụ hết hạn và yêu cầu thực hiện cùng thay đổi một đối tượng mà không kiểm soát xung đột.

Bài học tập trung vào các bất biến, quyền theo đối tượng, vòng đời trạng thái, transaction, idempotency và kiểm thử tình huống lạm dụng liên quan đến ngày làm việc. Các chính sách lịch trong ví dụ là quy ước giả định để minh họa thiết kế phần mềm, không đại diện cho một lịch nghỉ chính thức hoặc quy định pháp lý.

Sau bài học, người học có thể:

- Đặc tả chính xác ngày bắt đầu, ngày được tính, giờ chốt và thời điểm hết hạn.
- Tách lịch nghiệp vụ khỏi dữ liệu thời gian do client cung cấp.
- Xây dựng phép tính tái lập được theo phiên bản lịch và chính sách.
- Gắn deadline với đối tượng nghiệp vụ để retry không tạo thêm thời gian.
- Kiểm soát tranh chấp giữa thực hiện, hết hạn và thay đổi deadline.
- Thiết kế kiểm thử ở biên thời gian, ngày nghỉ, quyền và trạng thái.

## 2. Ngày làm việc không đồng nghĩa với khoảng thời gian cố định

### 2.1. Ba bài toán cần tách biệt

| Quy tắc | Cách hiểu |
| --- | --- |
| Sau 48 giờ | Cộng một khoảng thời gian thực 48 giờ vào thời điểm bắt đầu |
| Sau 2 ngày theo lịch | Dịch ngày theo múi giờ và quy tắc giờ trong ngày được chỉ định |
| Sau 2 ngày làm việc | Bỏ qua các ngày không làm việc theo một lịch nghiệp vụ cụ thể |

Không thể thay “2 ngày làm việc” bằng `2 * 24 * 60 * 60` giây. Thời gian chờ có thể đi qua cuối tuần, ngày nghỉ hoặc khoảng đổi giờ địa phương. Ngay cả “ngày làm việc” cũng không có một lịch duy nhất cho mọi tenant, thị trường, loại dịch vụ hay bộ phận.

Một ngày thứ Bảy có thể được khai báo là ngày làm việc bù. Một ngày thứ Hai có thể là ngày đóng cửa riêng của dịch vụ. Kiểm tra duy nhất `dayOfWeek != SATURDAY && dayOfWeek != SUNDAY` không thể biểu diễn đầy đủ các trường hợp đó.

### 2.2. Ngày làm việc và giờ làm việc là hai đại lượng khác nhau

Giả sử một ngày chỉ hoạt động buổi sáng. Theo chính sách đếm ngày, ngày đó vẫn có thể tính là một ngày làm việc, nhưng giờ chốt nhận yêu cầu và giờ kết thúc có thể sớm hơn.

Nếu hợp đồng yêu cầu “16 giờ làm việc”, cần cộng thời lượng bên trong các khoảng mở cửa hợp lệ, trừ các khoảng đóng cửa và tránh đếm chồng khoảng giao nhau. Thuật toán cộng số ngày làm việc trong bài này không giải quyết bài toán giờ làm việc và không nên được dùng thay thế.

### 2.3. Dữ liệu đầu vào tối thiểu

Một phép tính cần xác định được:

```text
acceptedAt          Thời điểm nghiệp vụ bắt đầu, do server ghi nhận
businessZone        Múi giờ có thẩm quyền của nghiệp vụ
calendarId          Lịch áp dụng cho đúng phạm vi
calendarVersion     Phiên bản lịch bất biến dùng để tính
calculationPolicy   Quy tắc chọn ngày gốc, đếm ngày và giờ hết hạn
policyVersion       Phiên bản quy tắc tính
businessDays        Số ngày được chính sách cho phép
```

`acceptedAt` không phải `clientCreatedAt`. Một timestamp có chữ ký của một hệ thống khác cũng chỉ được dùng nếu chính sách công nhận hệ thống đó là nguồn có thẩm quyền cho sự kiện bắt đầu này.

## 3. Đặc tả chính sách trước khi viết thuật toán

### 3.1. Các câu hỏi bắt buộc phải trả lời

| Thành phần | Câu hỏi cần chốt |
| --- | --- |
| Sự kiện bắt đầu | Tính từ lúc tạo nháp, gửi hợp lệ, đủ phê duyệt hay nhận đủ hồ sơ? |
| Múi giờ | Dùng múi giờ của đối tượng, dịch vụ, thị trường hay tenant? |
| Ngày gốc | Có tính ngày tiếp nhận là ngày thứ nhất không? |
| Giờ chốt | Đúng giờ chốt còn thuộc lượt nhận của ngày hiện tại không? |
| Ngày đóng cửa | Dời ngày gốc đến ngày làm việc tiếp theo hay xử lý theo quy tắc khác? |
| Giờ hết hạn | Hết hạn vào giờ đóng cửa, giờ chốt hay một giờ riêng? |
| Biên hết hạn | Đúng thời điểm deadline còn được thao tác không? |
| Đổi lịch | Đề nghị đang mở giữ lịch cũ hay được tính lại có kiểm soát? |
| Thiếu dữ liệu | Chờ xử lý hay áp dụng một phương án dự phòng đã được phê chuẩn? |

Một yêu cầu chỉ ghi “hạn 2 ngày làm việc” chưa đủ để lập trình. Các cách hiểu khác nhau ở ngày gốc và giờ chốt có thể lệch một ngày hoặc nhiều ngày sau một kỳ nghỉ dài.

### 3.2. Chính sách minh họa của bài

Để các ví dụ có kết quả nhất quán, bài sử dụng chính sách sau:

1. Server ghi một `acceptedAt` khi đề nghị lần đầu được tiếp nhận hợp lệ.
2. Chuyển `acceptedAt` sang ngày địa phương trong `businessZone`.
3. Nếu ngày đó làm việc và thời điểm tiếp nhận **trước** giờ chốt, ngày đó là `anchorDate`.
4. Nếu ngày đó đóng cửa hoặc thời điểm tiếp nhận đúng hay sau giờ chốt, lấy ngày làm việc tiếp theo làm `anchorDate`.
5. Cộng `N` ngày làm việc **sau** `anchorDate`, không tính chính ngày gốc vào `N`.
6. Deadline nằm ở giờ kết thúc được cấu hình cho ngày kết quả.
7. Quyền thao tác theo thời gian dùng khoảng nửa mở: `decisionAt < dueAt`. Đúng `dueAt` là đã hết hạn.

Với `N = 0`, ngày kết quả là `anchorDate`. Đây là lựa chọn được nêu rõ, không phải mặc định cho mọi hệ thống. Nếu nghiệp vụ tính ngày tiếp nhận là ngày thứ nhất, phải dùng một chính sách khác và có định danh phiên bản khác.

Trong ví dụ Java ở phần sau, mỗi ngày làm việc có một giờ chốt và một giờ kết thúc trên cùng ngày, với giờ chốt không muộn hơn giờ kết thúc. Ca làm việc qua nửa đêm cần mô hình khoảng hoạt động riêng.

### 3.3. Ví dụ có ngày nghỉ giả định

Giả sử lịch dịch vụ dùng `Asia/Ho_Chi_Minh`, giờ chốt và giờ hết hạn đều là 17:00. Thứ Bảy, Chủ nhật đóng cửa; thứ Hai **09/03/2026** cũng đóng cửa theo dữ liệu giả định của ví dụ. Số ngày cần cộng là `N = 2`.

| Thời điểm tiếp nhận theo giờ nghiệp vụ | Ngày gốc | Các ngày được đếm | Deadline |
| --- | --- | --- | --- |
| Thứ Sáu 06/03/2026, 16:59:59 | 06/03 | 10/03 là ngày 1, 11/03 là ngày 2 | 11/03/2026, 17:00 |
| Thứ Sáu 06/03/2026, 17:00:00 | 10/03 | 11/03 là ngày 1, 12/03 là ngày 2 | 12/03/2026, 17:00 |
| Thứ Bảy 07/03/2026, 10:00:00 | 10/03 | 11/03 là ngày 1, 12/03 là ngày 2 | 12/03/2026, 17:00 |

Sự khác biệt giữa 16:59:59 và 17:00:00 là hệ quả trực tiếp của quy tắc “trước giờ chốt”, không phải sai số cần tự làm tròn. Nếu sản phẩm có thời gian ân hạn, phải đặc tả riêng khoảng ân hạn và điều kiện áp dụng.

## 4. Nguồn có thẩm quyền và các bất biến bảo mật

### 4.1. Không để client chọn quy tắc có lợi cho mình

Client có thể gửi ý định như “nộp yêu cầu xử lý cho hồ sơ X”. Backend phải suy ra tenant, loại dịch vụ, lịch và chính sách từ hồ sơ cùng ngữ cảnh xác thực.

Các trường dưới đây không được mặc nhiên nhận làm dữ liệu quyết định từ request:

```json
{
  "acceptedAt": "2026-03-06T09:59:59Z",
  "businessDays": 30,
  "calendarId": "calendar-with-long-holidays",
  "calendarVersion": "old-version",
  "timeZone": "Pacific/Honolulu",
  "dueAt": "2026-12-31T23:59:59Z",
  "approved": true
}
```

Nếu một API quản trị cho phép thay đổi các giá trị này, đó là một nghiệp vụ riêng cần quyền trên đối tượng, kiểm tra lý do, giới hạn, dấu vết và phê duyệt tương ứng. Việc một trường có định dạng ISO hợp lệ không chứng minh người gọi được phép đặt nó.

### 4.2. Các bất biến cần giữ

- **Tái lập được:** cùng sự kiện bắt đầu, chính sách và snapshot lịch phải cho cùng kết quả.
- **Không tự gia hạn khi retry:** gửi lại cùng nghiệp vụ không đổi `acceptedAt`, lịch hay deadline đã chốt.
- **Đúng phạm vi:** lịch áp dụng thuộc đúng tenant, loại dịch vụ và thị trường được chính sách chọn.
- **Không bỏ qua trạng thái:** còn thời gian là một điều kiện; quyền đối tượng và trạng thái cho phép vẫn phải đồng thời thỏa mãn.
- **Không tin đồng hồ client:** quyết định hết hạn dùng thời điểm phía server hoặc nguồn thời gian được hệ thống công nhận.
- **Không tạo quyền từ dữ liệu thiếu:** thiếu lịch hoặc gặp thời gian địa phương không được hỗ trợ không được tự dẫn đến “chưa hết hạn”.
- **Có thể truy nguyên:** deadline lưu được gắn với dữ liệu đầu vào và phiên bản đã tạo ra nó.

Với chính sách đếm ở mục 3 và cùng một snapshot lịch, tăng `N` không được làm deadline sớm hơn. Tuy nhiên, không nên so sánh tính đơn điệu giữa hai lịch có giờ chốt hoặc cách mở cửa khác nhau rồi kết luận một cách tổng quát.

### 4.3. Quản trị lịch cũng là một bề mặt tấn công

Nếu người dùng sửa được lịch áp dụng cho hồ sơ của mình, họ có thể thêm ngày nghỉ để kéo dài thời hạn hoặc đánh dấu ngày làm việc để làm hồ sơ của người khác hết hạn sớm. Cần kiểm soát quyền sửa và quyền công bố lịch, giới hạn phạm vi và kiểm tra các thay đổi có ảnh hưởng lớn.

Không sửa âm thầm một phiên bản lịch đã được dùng để chốt deadline. Công bố phiên bản mới và lưu nguồn thay đổi. Nếu cần áp dụng thay đổi cho đối tượng đang mở, thực hiện theo một quy trình tính lại có kiểm soát, được phân tích ở mục 8.

## 5. Mô hình thời gian và snapshot lịch

### 5.1. Vai trò của từng kiểu dữ liệu

Trong Java, có thể tách các đại lượng như sau:

| Kiểu | Vai trò trong bài |
| --- | --- |
| `Instant` | Thời điểm tiếp nhận, thời điểm quyết định và deadline để so sánh trên cùng trục thời gian |
| `ZoneId` | Múi giờ nghiệp vụ có định danh, chẳng hạn `Asia/Ho_Chi_Minh` |
| `LocalDate` | Ngày dùng để tra cứu lịch làm việc |
| `LocalTime` | Giờ chốt hoặc giờ kết thúc của một ngày trong lịch |
| `LocalDateTime` | Kết hợp ngày và giờ địa phương trước khi áp dụng quy tắc múi giờ |

`LocalDate` không tự có múi giờ. Một `LocalDateTime` cũng chưa xác định duy nhất một thời điểm thực. Không lấy múi giờ mặc định của máy chạy ứng dụng hoặc trình duyệt làm quy tắc nghiệp vụ; hai instance cấu hình khác nhau có thể đưa ra deadline khác nhau.

Chuyển một `Instant` đã biết sang múi giờ để lấy ngày tiếp nhận là thao tác xác định được. Chiều ngược lại, từ ngày và giờ địa phương sang `Instant`, cần chú ý các múi giờ có đổi giờ: có thời gian địa phương không tồn tại hoặc xuất hiện hai lần.

Trong ví dụ, chính sách là **từ chối tự tính nếu giờ chốt hoặc giờ hết hạn rơi vào thời gian không tồn tại hay không duy nhất**. Hệ thống chuyển sang xử lý lỗi lịch có kiểm soát, không tự chọn một offset có thể kéo dài thời hạn. Một chính sách khác có thể chọn offset sớm hoặc muộn, nhưng phải được đặc tả và kiểm thử riêng.

### 5.2. Phân biệt ngày đóng cửa với dữ liệu chưa biết

Một snapshot lịch nên trả về một trong các kết quả rõ ràng:

- Ngày làm việc, có giờ chốt và giờ kết thúc hợp lệ.
- Ngày đóng cửa theo lịch đã công bố.
- Không có dữ liệu cho ngày đó, hoặc snapshot không sử dụng được.

Trường hợp cuối không tương đương ngày đóng cửa, cũng không tương đương ngày làm việc. Nếu cứ coi mọi ngày thiếu là ngày nghỉ, một phép cộng có thể bị đẩy rất xa hoặc lặp không giới hạn. Nếu coi ngày thiếu là ngày làm việc, hệ thống có thể đặt hạn sớm hơn cam kết.

Có thể tạo snapshot từ lịch tuần, ngày nghỉ, ngày mở bù và các ngoại lệ giờ hoạt động. Cần quy định thứ tự ưu tiên, ví dụ ngoại lệ đã công bố cho một ngày ghi đè lịch tuần của ngày đó. Dù lưu dạng quy tắc hay bản đồ ngày đã tính sẵn, snapshot dùng trong một phép tính phải nhất quán và bất biến.

Nếu cache lịch, key phải phân biệt đầy đủ phạm vi, định danh và phiên bản cần thiết. Không dùng một key chung như `holidays` cho nhiều tenant. Chỉ dùng snapshot cũ làm dự phòng khi chính sách cho phép, snapshot đúng phiên bản và có đủ dữ liệu cho phép tính.

### 5.3. Tái dựng qua các lần cập nhật dữ liệu múi giờ

Các quy tắc ánh xạ giờ địa phương sang thời điểm thực cũng là một phần của phép tính. Khi dữ liệu múi giờ của môi trường được cập nhật, việc tính lại một ngày tương lai có thể khác kết quả trước đó.

Vì vậy, lưu `dueAt` đã chốt như kết quả có thẩm quyền, cùng ngày địa phương, múi giờ, phiên bản lịch và phiên bản chính sách. Nếu cần tái dựng chính xác qua các lần cập nhật dữ liệu múi giờ, phải lưu hoặc quản lý thêm phiên bản quy tắc múi giờ đã dùng. Tính tái lập được ở đây giả định cùng quy tắc ánh xạ thời gian, không chỉ cùng chuỗi tên múi giờ.

## 6. Ví dụ thuật toán Java

Ví dụ dưới đây dùng cú pháp Java 17, không phụ thuộc framework. Đây là bộ tính thuần: nó nhận thời điểm bắt đầu đã được xác định, không gọi đồng hồ hiện tại và không đọc request HTTP.

`CalendarSnapshot` có hợp đồng trả dữ liệu của đúng phiên bản bất biến. `ruleFor` trả `null` khi ngày nằm ngoài dữ liệu có sẵn; bộ tính xử lý trường hợp đó như lỗi. Các giới hạn 365 ngày làm việc và 3.660 ngày tìm kiếm là giới hạn minh họa phía server, không phải giới hạn chung cho mọi sản phẩm.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Objects;

public final class BusinessDayCalculator {
    private static final int MAX_BUSINESS_DAYS = 365;
    private static final int MAX_SEARCH_DAYS = 3_660;
    private static final String POLICY_VERSION = "EXCLUDE_ANCHOR_STRICT_TIME_V1";

    public interface CalendarSnapshot {
        String id();
        String version();
        ZoneId zone();
        DayRule ruleFor(LocalDate date);
    }

    public record DayRule(
        boolean businessDay, LocalTime cutoff, LocalTime deadline
    ) {
        public DayRule {
            if (businessDay) {
                Objects.requireNonNull(cutoff, "cutoff");
                Objects.requireNonNull(deadline, "deadline");
                if (cutoff.isAfter(deadline)) {
                    throw new IllegalArgumentException("Cutoff after deadline");
                }
            }
        }
    }

    public record Result(
        String calendarId,
        String calendarVersion,
        String policyVersion,
        ZoneId zone,
        Instant acceptedAt,
        int businessDays,
        LocalDate anchorDate,
        LocalDate dueDate,
        Instant dueAt
    ) {}

    public static Result calculate(
        Instant acceptedAt, int businessDays, CalendarSnapshot calendar
    ) {
        Objects.requireNonNull(acceptedAt, "acceptedAt");
        Objects.requireNonNull(calendar, "calendar");
        if (businessDays < 0 || businessDays > MAX_BUSINESS_DAYS) {
            throw new IllegalArgumentException("Unsupported business day count");
        }

        String calendarId = Objects.requireNonNull(calendar.id(), "calendarId");
        String version = Objects.requireNonNull(calendar.version(), "version");
        ZoneId zone = Objects.requireNonNull(calendar.zone(), "zone");
        LocalDate receivedDate = acceptedAt.atZone(zone).toLocalDate();
        LocalDate limitExclusive = receivedDate.plusDays(MAX_SEARCH_DAYS);

        DayRule receivedRule = requireRule(calendar, receivedDate, limitExclusive);
        LocalDate anchorDate;
        if (receivedRule.businessDay()) {
            Instant cutoffAt = strictInstant(
                receivedDate, receivedRule.cutoff(), zone
            );
            anchorDate = acceptedAt.isBefore(cutoffAt)
                ? receivedDate
                : nextBusinessDay(calendar, receivedDate, limitExclusive);
        } else {
            anchorDate = nextBusinessDay(calendar, receivedDate, limitExclusive);
        }

        LocalDate dueDate = anchorDate;
        for (int count = 0; count < businessDays; count++) {
            dueDate = nextBusinessDay(calendar, dueDate, limitExclusive);
        }
        DayRule dueRule = requireRule(calendar, dueDate, limitExclusive);
        Instant dueAt = strictInstant(dueDate, dueRule.deadline(), zone);

        return new Result(
            calendarId, version, POLICY_VERSION, zone, acceptedAt,
            businessDays, anchorDate, dueDate, dueAt
        );
    }

    private static LocalDate nextBusinessDay(
        CalendarSnapshot calendar, LocalDate current, LocalDate limitExclusive
    ) {
        LocalDate candidate = current;
        while (true) {
            candidate = candidate.plusDays(1);
            DayRule rule = requireRule(calendar, candidate, limitExclusive);
            if (rule.businessDay()) {
                return candidate;
            }
        }
    }

    private static DayRule requireRule(
        CalendarSnapshot calendar, LocalDate date, LocalDate limitExclusive
    ) {
        if (!date.isBefore(limitExclusive)) {
            throw new IllegalStateException("Calendar search limit exceeded");
        }
        DayRule rule = calendar.ruleFor(date);
        if (rule == null) {
            throw new IllegalStateException("Calendar data unavailable");
        }
        return rule;
    }

    private static Instant strictInstant(
        LocalDate date, LocalTime time, ZoneId zone
    ) {
        LocalDateTime local = LocalDateTime.of(date, time);
        List<ZoneOffset> offsets = zone.getRules().getValidOffsets(local);
        if (offsets.size() != 1) {
            throw new IllegalStateException("Ambiguous or missing local time");
        }
        return local.toInstant(offsets.get(0));
    }
}
```

Các điểm cần giữ khi tích hợp:

- `acceptedAt` được server cấp một lần cho sự kiện bắt đầu; không lấy từ body của người dùng.
- `businessDays` do chính sách xác định. Kiểm tra miền giá trị không thay thế việc kiểm tra quyền chọn số ngày.
- `calendar` đã được lựa chọn theo đối tượng nghiệp vụ và được cố định phiên bản.
- `requireRule` bảo đảm không âm thầm bỏ qua dữ liệu lịch thiếu.
- Vòng tìm ngày bị chặn bởi horizon phía server, kể cả khi lịch cấu hình đóng cửa liên tục.
- Chuyển sang thời điểm thực chỉ thực hiện sau khi chọn được ngày và giờ theo chính sách.

Ví dụ chỉ có một phiên bản chính sách trong mã. Khi cần nhiều cách đếm, nên chọn bộ tính bằng phiên bản đã lưu trên đối tượng, thay vì sửa ý nghĩa của phiên bản cũ tại chỗ. Phần chọn chính sách và phần lưu kết quả nằm ngoài bộ tính này.

## 7. Gắn deadline với transaction, trạng thái và idempotency

### 7.1. Chốt deadline ở sự kiện bắt đầu

Một đối tượng có thời hạn có thể lưu:

```text
id, tenantId, state, objectVersion
acceptedAt, businessDays
calendarId, calendarVersion, businessZone
policyVersion, anchorDate, dueDate, dueAt
deadlineRevision
```

Trong lần tiếp nhận đầu tiên, backend xác thực quyền, xác định sự kiện bắt đầu, chọn lịch và chính sách, tính deadline rồi lưu cùng trạng thái nghiệp vụ thích hợp. `acceptedAt` và `dueAt` trở thành dữ liệu được kiểm soát của đối tượng.

Idempotency của lệnh tạo hoặc gửi phải trả lại cùng đối tượng và deadline khi key cùng nội dung được gửi lại. Cùng key nhưng nội dung khác phải bị từ chối. Key cần được phân phạm vi theo tenant, chủ thể và loại lệnh phù hợp, có ràng buộc duy nhất để chống hai request cùng tạo mới.

Chống retry bằng key chưa đủ nếu người dùng có thể dùng key mới để lặp lại một sự kiện vốn chỉ được bắt đầu một lần. Cần cả quy tắc nghiệp vụ, chẳng hạn một hồ sơ chỉ có một lần gửi hợp lệ đang hoạt động hoặc một định danh sự kiện gửi duy nhất.

Ví dụ lỗi cần tránh:

```java
// Sai nếu chạy lại mỗi lần người dùng bấm thử hoặc retry lệnh thực hiện.
Instant acceptedAt = Instant.now();
Instant dueAt = calculateFrom(acceptedAt, policy.businessDays());
```

Nếu deadline được tính lại từ hiện tại trong mỗi lần gọi, cửa sổ thao tác có thể không bao giờ đóng. Trong lệnh thực hiện, đọc deadline đã chốt; không tạo lại nó từ đồng hồ hiện tại.

### 7.2. Thời điểm nào quyết định yêu cầu còn hạn?

Phải phân biệt thời điểm client bấm nút, gateway nhận request, server ra quyết định và transaction commit. Với chính sách của bài, điểm quyết định là **thời điểm server lấy sau khi đã khóa đối tượng và ngay trước khi quyết định chuyển trạng thái**. Thời điểm này được lưu thành `decisionAt`.

Điều kiện là:

```text
state cho phép hành động
AND người gọi có quyền trên đối tượng
AND decisionAt < dueAt
```

Một transaction được quyết định hợp lệ trước deadline có thể commit hoặc trả phản hồi sau deadline. Điều đó vẫn đúng theo chính sách đã chọn. Không được mô tả điều kiện này thành bảo đảm “mọi commit đều xảy ra trước deadline”.

Nếu sản phẩm cam kết nhận request trước hạn dù xử lý sau hạn, phải dùng một chính sách tiếp nhận khác: thời điểm nhận có thẩm quyền được ghi bền vững, gắn với đúng request đã xác thực và không cho client tự khai hoặc tạo placeholder giữ chỗ vô hạn. Không trộn hai cách hiểu khi xử lý tranh chấp.

### 7.3. Kiểm tra và chuyển trạng thái trong cùng ranh giới giao dịch

Mã giả dưới đây chỉ minh họa vị trí các kiểm soát, không phải API framework có sẵn:

```java
return transaction.required(() -> {
    RequestRecord request = idempotency.claimOrLock(
        authenticatedScope, operationKey, canonicalCommandFingerprint
    );
    request.requireSameFingerprint(canonicalCommandFingerprint);

    BusinessObject object = repository.lockByTenantAndId(
        authenticatedTenantId, command.objectId()
    );
    authorization.requireCanAccess(currentActor, object);

    if (request.isCompleted()) {
        authorization.requireCanReadResult(currentActor, object);
        return request.storedResult();
    }

    authorization.requireCanPerform(currentActor, object);
    object.requireExpectedVersion(command.expectedVersion());
    object.requireState(OPEN);

    Instant decisionAt = trustedClock.instant();
    if (!decisionAt.isBefore(object.dueAt())) {
        throw new BusinessWindowExpired();
    }

    BusinessResult result = object.performAndRecord(decisionAt);
    repository.save(object);
    audit.appendAction(object, decisionAt, object.deadlineRevision());
    idempotency.complete(request, result);
    return result;
});
```

Giữ cùng transaction cho hiệu ứng nghiệp vụ, chuyển trạng thái, dấu vết cần thiết và kết quả idempotency. Nếu hành động tác động nhiều đối tượng hoặc tạo hiệu ứng ở hệ thống khác, cần bổ sung kiểm soát transaction hay giao thức tương ứng; đoạn mã không tự làm các lời gọi bên ngoài trở nên nguyên tử.

Lấy khóa hàng chỉ có tác dụng khi các luồng cập nhật liên quan phối hợp cùng quy tắc. Nếu dùng optimistic locking hoặc cập nhật có điều kiện, phải kiểm tra xung đột và đánh giá lại quyền, trạng thái cùng thời gian cho lần thử mới. Không dùng `decisionAt` cũ của một transaction đã rollback để vượt qua deadline ở lần thử tiếp theo.

### 7.4. Worker hết hạn chỉ là một đường chuyển trạng thái

Worker có thể tìm đối tượng `OPEN` đã đến hạn và chuyển sang `EXPIRED`, giải phóng reservation hoặc phát sự kiện cần thiết. Luồng này phải cạnh tranh với lệnh thực hiện qua khóa hoặc điều kiện phiên bản tương đương.

- Nếu lệnh thực hiện quyết định hợp lệ và hoàn tất trước trong thứ tự giao dịch, worker thấy trạng thái đã hoàn tất và không hết hạn đối tượng đó.
- Nếu worker hết hạn trước, lệnh thực hiện phải đọc lại và từ chối vì trạng thái không còn `OPEN`.
- Nếu worker chưa chạy dù `dueAt` đã qua, API vẫn phải từ chối theo `decisionAt`; không coi trạng thái `OPEN` là bằng chứng còn thời gian.

Nếu việc hết hạn giải phóng một tài nguyên giữ chỗ, thao tác giải phóng cũng phải chống thực hiện trùng. Sự kiện gửi qua outbox có thể được phát lại; consumer cần định danh hiệu ứng để không giải phóng hoặc hoàn tài nguyên thêm lần nữa.

## 8. Thay đổi lịch và tính lại deadline

### 8.1. Giữ kết quả đã chốt hay áp dụng lịch mới?

Có hai cách tiếp cận chính, cần chọn theo hợp đồng nghiệp vụ:

| Cách áp dụng | Hành vi |
| --- | --- |
| Giữ kết quả đã chốt | Đối tượng đang mở tiếp tục dùng deadline và phiên bản lịch đã lưu; đối tượng mới dùng phiên bản mới |
| Tính lại có kiểm soát | Một nghiệp vụ riêng xác định đối tượng bị ảnh hưởng, tính deadline mới và cập nhật có dấu vết |

Không để cùng đối tượng nhận hai deadline khác nhau chỉ vì request được chuyển đến hai instance đang cache hai phiên bản lịch. Giao diện xem chi tiết nên lấy deadline đã chốt của đối tượng, thay vì tự tính từ lịch mới nhất.

Trong một quy trình tính lại, phải nêu rõ:

- Đối tượng và trạng thái nào được áp dụng.
- Có được rút ngắn hạn đã thông báo hay chỉ được gia hạn.
- Có được mở lại đối tượng đã hết hạn hay không.
- Ai có quyền đề xuất và ai có quyền phê duyệt.
- Kết quả mới dựa trên sự kiện bắt đầu gốc nào.
- Cách xử lý các tác vụ lên lịch, reservation và thông báo liên quan.

Một phiên bản lịch mới không tự cấp quyền mở lại hồ sơ đã đóng. Nếu cần mở lại, đó phải là một chuyển trạng thái được cho phép, cùng chính sách phục hồi tài nguyên tương ứng.

### 8.2. Phê duyệt phải gắn với thay đổi cụ thể

Một đề nghị tính lại có thể chứa:

```text
objectId, currentDeadlineRevision
oldDueAt, proposedDueAt
oldCalendarVersion, proposedCalendarVersion
policyVersion, reason, requestedBy
approvalRevision
```

Người duyệt phải duyệt đúng nội dung. Nếu sau phê duyệt người yêu cầu đổi lịch, deadline đề xuất hoặc tập đối tượng, phải yêu cầu revision và phê duyệt mới theo chính sách. Không sử dụng một cờ `approved=true` có thể tái dùng cho mọi thay đổi.

Khi áp dụng, khóa đối tượng hoặc dùng điều kiện cập nhật trên `currentDeadlineRevision`, kiểm tra trạng thái hiện tại và lưu deadline mới cùng revision tăng lên. Nếu lệnh thực hiện đã hoàn tất đối tượng trong lúc chờ duyệt, không được ghi đè kết quả đó bằng dữ liệu snapshot cũ.

### 8.3. Không để tác vụ cũ áp dụng deadline đã lỗi thời

Tác vụ hết hạn được tạo trước khi gia hạn có thể vẫn tồn tại trong hàng đợi. Nó nên mang `objectId` và `deadlineRevision` kỳ vọng, rồi đọc lại đối tượng trước khi thực hiện.

```text
Chỉ hết hạn khi:
    state == OPEN
    AND currentDeadlineRevision == expectedDeadlineRevision
    AND authoritativeNow >= currentDueAt
```

Một worker quét trực tiếp cơ sở dữ liệu không nhất thiết có revision từ message, nhưng vẫn cần đánh giá trạng thái và deadline hiện tại trong cùng thao tác được kiểm soát xung đột. Timer hay message đã đến giờ chỉ là tín hiệu kiểm tra, không phải quyền cưỡng ép đóng đối tượng.

## 9. Thiếu dữ liệu, đồng hồ và giới hạn vận hành

### 9.1. Không tự tạo deadline có lợi khi lịch lỗi

Khi chưa thể tính deadline cho đối tượng mới, có thể từ chối tiếp nhận hoặc đưa vào trạng thái chờ lịch theo chính sách sản phẩm. Trạng thái chờ không được cấp quyền thao tác vốn cần một deadline hợp lệ.

Nếu hệ thống đã công nhận sự kiện tiếp nhận và lưu `acceptedAt`, lần xử lý tiếp phải dùng thời điểm đó, không lấy thời điểm dịch vụ lịch phục hồi làm ngày bắt đầu mới. Nếu không, lỗi lịch sẽ âm thầm gia hạn thời gian.

Đối với đối tượng đã có deadline được chốt, việc dịch vụ lịch tạm mất kết nối không tự làm deadline mất hiệu lực. Nếu chính sách cho phép tiếp tục dùng kết quả đã lưu, API có thể kiểm tra `dueAt` đó mà không tải lại lịch cho từng thao tác. Phân biệt trường hợp này với một snapshot bị thu hồi hiệu lực bởi quyết định quản trị rõ ràng.

### 9.2. Nguồn thời gian phải được quản lý

Các instance cần nguồn thời gian được vận hành nhất quán. Nếu dùng thời gian của cơ sở dữ liệu, phải biết giá trị được lấy tại lúc bắt đầu transaction hay tại điểm câu lệnh được thực thi; không mặc nhiên coi mọi hàm “thời gian hiện tại” có cùng ngữ nghĩa.

Đồng hồ phía server vẫn có thể sai lệch hoặc bị điều chỉnh. Cần theo dõi sai lệch, xử lý các bước nhảy bất thường theo chính sách và điều tra khi thời điểm quyết định lùi không hợp lý so với dữ liệu đã ghi. Không giải quyết vấn đề bằng cách cho client truyền một timestamp thay thế.

Đồng hồ đơn điệu có ích để đo thời lượng trong một tiến trình, nhưng giá trị của nó không thay cho `Instant` bền vững dùng so sánh deadline qua nhiều tiến trình và sau khởi động lại.

### 9.3. Thống nhất độ chính xác

API, cơ sở dữ liệu, bộ tính và luồng kiểm tra cần có quy ước độ chính xác tương thích. Nếu một nơi giữ nano giây, nơi khác cắt xuống mili giây còn nơi khác làm tròn lên giây, các request gần biên có thể nhận kết quả khác nhau.

Lưu và so sánh theo kiểu thời gian đúng; không so sánh chuỗi ngày được định dạng theo locale. Giao diện có thể hiển thị đến phút, nhưng backend vẫn phải áp dụng biên theo dữ liệu có thẩm quyền. Nếu muốn có ân hạn do độ chính xác hoặc trải nghiệm người dùng, hãy biến nó thành chính sách rõ ràng.

### 9.4. Chặn việc lạm dụng bộ tính

Không để client yêu cầu cộng một lượng ngày vô hạn, chọn lịch ngoài phạm vi hoặc tạo hàng loạt preview tốn tài nguyên. Giới hạn số ngày và horizon tìm kiếm thuộc cấu hình server; lịch đóng cửa liên tục phải kết thúc bằng lỗi có kiểm soát.

Endpoint xem thử deadline có thể hữu ích cho giao diện, nhưng kết quả preview không tự cấp quyền và không thay thế deadline đã chốt. Khi gửi thật, backend phải gắn kết quả với sự kiện tiếp nhận và phiên bản phù hợp. Nếu sản phẩm cam kết bảo lưu một báo giá hoặc deadline preview, cần một đối tượng cam kết riêng có thời hạn và chống sửa nội dung.

## 10. Các tình huống lạm dụng và kiểm thử

### 10.1. Kiểm thử phép tính thuần

Dùng snapshot lịch giả định và thời điểm đầu vào cố định. Không gọi đồng hồ thật trong kiểm thử phép tính. Với lịch ở mục 3, các kết quả phải khớp chính sách đếm đã công bố.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Nhận 06/03/2026 lúc 16:59:59, `N=2` | Deadline 11/03/2026 lúc 17:00 theo giờ nghiệp vụ |
| Nhận 06/03/2026 đúng 17:00, `N=2` | Deadline 12/03/2026 lúc 17:00 |
| Nhận trong ngày đóng cửa 07/03/2026, `N=2` | Ngày gốc 10/03; deadline 12/03 lúc 17:00 |
| `N=0`, nhận trước giờ chốt của một ngày làm việc | Ngày hết hạn là chính ngày gốc |
| `N=0`, nhận đúng giờ chốt | Ngày hết hạn là ngày làm việc tiếp theo theo chính sách |
| Ngày cuối tuần được mở bù trong snapshot | Ngày đó được đếm là ngày làm việc |
| Ngày làm việc có giờ chốt sớm | Chọn ngày gốc theo giờ chốt riêng của ngày đó |
| Đi qua cuối tháng, cuối năm hoặc ngày nhuận | Đếm theo ngày lịch hợp lệ, không dựa vào số ngày cố định của tháng |
| Snapshot thiếu một ngày cần tra cứu | Báo lỗi dữ liệu lịch; không tự coi là ngày nghỉ hay làm việc |
| Toàn bộ horizon được cấu hình đóng cửa | Dừng ở giới hạn tìm kiếm, không lặp vô hạn |
| `N` âm hoặc vượt giới hạn server | Từ chối đầu vào |
| Giờ chốt hoặc giờ deadline rơi vào khoảng giờ địa phương bị thiếu hoặc lặp | Từ chối theo chính sách thời gian nghiêm ngặt của ví dụ |
| Hai lần tính với cùng đầu vào và cùng quy tắc thời gian | Kết quả giống nhau |

Với kiểm thử đổi giờ, fixture phải chủ động chọn một vùng và ngày chuyển giờ phù hợp với dữ liệu múi giờ của môi trường kiểm thử. Kiểm tra riêng hai trường hợp không tồn tại và có hai offset; không chỉ kiểm tra một ngày thông thường rồi kết luận đã hỗ trợ đổi giờ.

### 10.2. Kiểm thử quyền, trạng thái và retry

| Tình huống tấn công hoặc lỗi | Bất biến cần xác nhận |
| --- | --- |
| Client đổi múi giờ, lịch hoặc số ngày trong body | Không thay đổi lựa chọn có thẩm quyền của backend |
| Client gửi `dueAt` rất xa hoặc `acceptedAt` lùi về trước giờ chốt | Không ghi đè các giá trị do server quản lý |
| Chọn lịch hoặc đối tượng thuộc tenant khác | Từ chối theo phạm vi và quyền đối tượng |
| Đổi giờ hoặc locale của trình duyệt | Không đổi deadline và kết quả cấp quyền |
| Retry cùng lệnh tiếp nhận sau vài ngày | Cùng đối tượng, cùng thời điểm bắt đầu và deadline đã chốt |
| Cùng key nhưng thay nội dung | Từ chối xung đột key, không gia hạn hoặc tạo đối tượng khác |
| Dùng key mới để gửi lại sự kiện chỉ được phép xảy ra một lần | Quy tắc duy nhất nghiệp vụ vẫn chặn việc khởi động lại cửa sổ |
| Còn hạn nhưng người dùng không có quyền | Từ chối; điều kiện thời gian không thay thế quyền |
| Còn hạn nhưng trạng thái đã hoàn tất hoặc bị hủy | Không thực hiện hiệu ứng lần nữa |
| Đã quá `dueAt` nhưng worker chưa đổi trạng thái | API từ chối theo thời gian có thẩm quyền |
| Sau commit mất phản hồi rồi retry | Trả kết quả gốc nếu có quyền đọc, không chạy hiệu ứng lần nữa |
| Gia hạn đã duyệt rồi sửa deadline đề xuất | Không áp dụng bằng phê duyệt của revision cũ |
| Task hết hạn mang revision cũ sau một lần gia hạn | Không đóng đối tượng theo deadline cũ |
| Sự kiện hết hạn được phát lại | Không giải phóng reservation hay hoàn tài nguyên thêm lần nữa |

Người dùng cố ý gửi sau giờ chốt để nhận ngày gốc muộn hơn có thể là hành vi được chính sách cho phép. Chỉ coi đó là lỗ hổng khi nó vi phạm quy tắc đã cam kết, chẳng hạn sửa được thời điểm tiếp nhận hoặc khởi động lại sự kiện không được phép lặp. Kiểm thử cần phân biệt lựa chọn hợp lệ với bỏ qua điều kiện nghiệp vụ.

### 10.3. Kiểm thử tại biên và khi đồng thời

Với `tick` là đơn vị chính xác đã thống nhất, kiểm tra ít nhất:

```text
decisionAt = dueAt - tick  → được phép nếu quyền và trạng thái hợp lệ
decisionAt = dueAt         → hết hạn
decisionAt = dueAt + tick  → hết hạn
```

Đối với tranh chấp, chủ động cho các luồng gặp nhau tại điểm khóa hoặc cập nhật có điều kiện:

1. Lệnh thực hiện đối đầu worker hết hạn.
2. Lệnh thực hiện đối đầu lệnh tính lại deadline.
3. Hai lần thực hiện cùng đối tượng với cùng hoặc khác idempotency key.
4. Worker cũ đối đầu worker mới sau khi deadline revision tăng.

Xác nhận trạng thái cuối, số hiệu ứng, revision và dấu vết thời gian. Không ép một luồng cụ thể phải thắng nếu quy tắc giao dịch cho phép cả hai thứ tự; chỉ cho phép những kết cục thỏa bất biến.

Khi một transaction thất bại vì xung đột rồi được chạy lại sau deadline, nó phải lấy thời điểm quyết định mới và có thể bị từ chối. Trường hợp thành công đã commit nhưng phản hồi bị mất phải nhận lại kết quả đã lưu, kể cả khi lúc retry đã quá hạn. Đó là đọc lại hiệu ứng hợp lệ trước đó, không phải cấp quyền thực hiện một hiệu ứng mới sau hạn.

## 11. Dấu vết và quan sát vận hành

Để giải thích vì sao một yêu cầu còn hoặc hết hạn, nên truy được:

- Đối tượng nghiệp vụ, tenant, loại sự kiện bắt đầu và `acceptedAt` gốc.
- Lịch, phiên bản lịch, múi giờ và phiên bản chính sách tính.
- Số ngày, ngày gốc, ngày kết quả và `dueAt` đã chốt.
- `deadlineRevision`, trạng thái trước và sau thao tác.
- `decisionAt`, chủ thể thực hiện, kết quả cho phép hoặc từ chối.
- Lý do và phê duyệt khi deadline được điều chỉnh.

Không ghi token truy cập, bí mật hoặc toàn bộ dữ liệu nhạy cảm của hồ sơ vào log. Quyền truy cập log và bản ghi audit cũng phải theo phạm vi đối tượng, tenant và vai trò phù hợp.

Các tín hiệu đáng theo dõi gồm tỷ lệ lỗi lịch thiếu, horizon bị vượt, số lần client cố thay trường thời gian, nhiều lần khởi động lại cùng một nghiệp vụ, xung đột revision, worker dùng deadline cũ và sai lệch nguồn thời gian.

Đối soát có thể phát hiện đối tượng `OPEN` đã quá hạn quá lâu, đối tượng thiếu metadata tính deadline hoặc reservation chưa được giải phóng sau trạng thái cuối. Tuy nhiên, một job đối soát không thay thế việc kiểm tra deadline ngay ở lệnh thực hiện.

## 12. Ví dụ xuyên suốt và câu hỏi tự kiểm tra

Giả sử một hồ sơ được phép sửa trong 2 ngày làm việc theo chính sách minh họa, có ngày nghỉ giả định như mục 3:

1. Server tiếp nhận hợp lệ lúc `2026-03-06T09:59:59Z`, tương ứng 16:59:59 tại `Asia/Ho_Chi_Minh`.
2. Backend xác định lịch dịch vụ và snapshot đã công bố, không nhận lịch do client tự chọn.
3. Ngày gốc là 06/03/2026. Bỏ qua hai ngày cuối tuần và ngày đóng cửa giả định 09/03, bộ tính đếm 10/03 và 11/03.
4. Deadline được chốt là `2026-03-11T10:00:00Z`, tương ứng 17:00 ngày 11/03 tại múi giờ nghiệp vụ; hồ sơ lưu cả phiên bản lịch, chính sách và deadline revision.
5. Client gửi lại lệnh tiếp nhận vào ngày hôm sau. Backend trả cùng hồ sơ, không bắt đầu lại 2 ngày.
6. Khi sửa hồ sơ, backend khóa đối tượng, kiểm tra quyền, trạng thái và `decisionAt < dueAt` rồi mới ghi hiệu ứng.
7. Nếu quyết định diễn ra đúng `2026-03-11T10:00:00Z`, yêu cầu sửa mới bị từ chối vì đã hết hạn, kể cả worker chưa xử lý hồ sơ.
8. Nếu một lần sửa đã commit hợp lệ trước hạn nhưng client mất phản hồi, retry có kiểm soát trả kết quả gốc; không thực hiện một lần sửa mới.

Trước khi đưa quy tắc ngày làm việc vào một luồng nghiệp vụ, cần trả lời được:

- Sự kiện nào bắt đầu tính hạn, và có được phép xảy ra lại không?
- Ai chọn lịch, múi giờ và số ngày? Ai được thay đổi những lựa chọn đó?
- Ngày gốc có được đếm không? Đúng giờ chốt thì xử lý thế nào?
- Deadline biểu diễn bằng giờ nào, theo độ chính xác nào, và biên nào được chấp nhận?
- Nếu thiếu lịch hoặc gặp giờ địa phương không hợp lệ, hệ thống sẽ đưa đối tượng về trạng thái nào?
- Thay đổi lịch ảnh hưởng đối tượng đang mở ra sao, và task cũ bị vô hiệu hóa bằng cách nào?
- Quyền, trạng thái và thời gian được kiểm tra ở cùng điểm quyết định nào?
- Retry trước và sau commit có thể làm thay đổi deadline hoặc tạo hiệu ứng trùng không?

Một quy tắc ngày làm việc được bảo vệ khi lịch có thẩm quyền, cách đếm rõ ràng, deadline được gắn với sự kiện và phiên bản cụ thể, còn hiệu ứng chỉ được tạo qua quyết định giao dịch thỏa quyền, trạng thái và thời gian. Bộ tính ngày là một thành phần của kiểm soát nghiệp vụ; toàn bộ luồng phải giữ được các điều kiện đó cả khi có sửa request, retry và xử lý đồng thời.


