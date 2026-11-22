# Truyền Locale và ZoneId qua ngữ cảnh xử lý tường minh trong Java

## 1. Bài toán: người dùng khác nhau, ngôn ngữ và múi giờ khác nhau

Một dịch vụ Java có thể phục vụ đồng thời người dùng ở Việt Nam, Mỹ và Pháp. Cùng một sự kiện diễn ra tại thời điểm UTC `2026-10-28T03:30:00Z`, nhưng người dùng muốn nhìn thấy thông tin theo **ngôn ngữ** và **múi giờ** riêng:

| Người xem | Locale dùng trình bày | ZoneId dùng quy đổi thời gian | Cách nhìn cùng Instant |
| --- | --- | --- | --- |
| Người xem ở Việt Nam | `vi-VN` | `Asia/Ho_Chi_Minh` | 10:30 ngày 28/10/2026 |
| Người xem ở New York | `en-US` | `America/New_York` | 23:30 ngày 27/10/2026 |
| Người dùng tiếng Pháp ở Việt Nam | `fr-FR` | `Asia/Ho_Chi_Minh` | 10:30, dùng chữ và mẫu ngày theo tiếng Pháp |

Một ứng dụng có thể “chạy được” nhưng hiển thị sai nếu vô tình sử dụng `Locale.getDefault()`, `ZoneId.systemDefault()` hoặc thay default của JVM trong từng request. Cả hai default đều là **trạng thái môi trường**, không phải đặc tính riêng của từng người dùng.

Giải pháp là **truyền `Locale` và `ZoneId` tường minh trong ngữ cảnh xử lý** (*explicit processing context*), giống như ta truyền ID bản ghi hoặc tham số nghiệp vụ. Context được tạo ở ranh giới đầu vào, kiểm tra tính hợp lệ, sau đó chuyển qua controller → service → formatter → tác vụ bất đồng bộ mà không phụ thuộc trạng thái ẩn.

**Mục tiêu bài học:** thiết kế request context bất biến; phân biệt locale với zone; truyền context qua API, service và async; xử lý lịch địa phương và DST; xác định default hợp lý; kiểm thử kết quả tái lập; nhận diện bẫy toàn cục, `ThreadLocal` và dữ liệu sai.

## 2. Locale và ZoneId thực sự quyết định điều gì?

### 2.1. Locale: ngôn ngữ, vùng và quy tắc trình bày

`java.util.Locale` biểu diễn một lựa chọn ngôn ngữ/vùng/script/extension cho hoạt động bản địa hóa. Ví dụ:

~~~java
Locale vi = Locale.forLanguageTag("vi-VN");
Locale en = Locale.US;
Locale fr = Locale.FRANCE;
~~~

Những đối tượng này thường dùng khi:

- Format tên tháng, tên thứ và bố cục ngày thông qua `DateTimeFormatter`.
- Format số, phần trăm và tiền bằng `NumberFormat`.
- Tra cứu tài nguyên giao diện và thông điệp theo ngôn ngữ.
- Chọn quy tắc so sánh/sắp xếp ngôn ngữ nếu API hỗ trợ.

**Locale không xác định thời điểm hoặc múi giờ.** `Locale.forLanguageTag("vi-VN")` không tự chuyển một `Instant` sang giờ Việt Nam. Một người chọn giao diện tiếng Việt nhưng đang ở Paris có thể cần locale `vi-VN` cùng `Europe/Paris`.

### 2.2. ZoneId: quy tắc quy đổi thời gian theo địa lý

`java.time.ZoneId` là ID vùng giờ, ví dụ:

~~~java
ZoneId hcm = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId ny = ZoneId.of("America/New_York");
ZoneId utc = ZoneOffset.UTC;
~~~

ZoneId vùng (*region ID*) gắn với quy tắc chuyển đổi UTC offset theo thời gian, bao gồm những nơi có thay đổi giờ mùa hè (*daylight saving time*). `America/New_York` không phải offset `-05:00` cố định: nó có thể là `-04:00` vào một giai đoạn của năm.

`ZoneOffset` chỉ mô tả offset cố định; `ZoneId` dạng vùng còn mang **quy tắc lịch sử/tương lai** từ time-zone database của runtime. Không thể thay `ZoneId` của một khu vực có DST bằng một offset tính từ “hôm nay” rồi áp dụng mãi.

**ZoneId không xác định ngôn ngữ.** Vùng `Asia/Ho_Chi_Minh` không buộc hệ thống in “Thứ Tư” thay vì “Wednesday”. Ngôn ngữ do `Locale` của người xem quyết định.

### 2.3. Đừng trộn lẫn giá trị thời gian với cách trình bày

| Đối tượng | Có ngày? | Có giờ? | Có zone/offset? | Vai trò thường gặp |
| --- | --- | --- | --- | --- |
| `LocalDate` | Có | Không | Không | Sinh nhật, ngày theo lịch |
| `LocalTime` | Không | Có | Không | Giờ mở cửa theo quy tắc địa phương |
| `LocalDateTime` | Có | Có | Không | Lịch hẹn địa phương trước khi chọn zone |
| `Instant` | Mốc thời gian toàn cầu | Có | Không lưu zone hiển thị | Sự kiện, thời điểm tạo bản ghi |
| `OffsetDateTime` | Có | Có | Có offset | Thời gian với offset cụ thể |
| `ZonedDateTime` | Có | Có | Có ZoneId | Ngày giờ vùng cụ thể, DST-aware |

Đối với một sự kiện đã xảy ra, thường lưu `Instant` (hoặc thời điểm có offset đúng) và chuyển sang zone hiển thị ở tầng trình bày. Với lịch hẹn “9 giờ sáng ngày 28/10 ở địa phương”, phải biết **zone của lịch hẹn** để xác định mốc UTC. Đây là hai mô hình khác nhau.

## 3. Vì sao default locale/time zone nguy hiểm trong ứng dụng nhiều người dùng?

Một chương trình desktop đơn người dùng có thể dựa trên `Locale.getDefault()` hoặc `ZoneId.systemDefault()` trong những tình huống đơn giản. Nhưng server thường chạy trong container hoặc máy chủ có cấu hình khác máy khách, và nhiều request hoạt động đồng thời.

**Không nên** chọn ngôn ngữ từng request theo cách sau:

~~~java
Locale.setDefault(userLocale); // Anti-pattern trong web server.
~~~

Và cũng không nên đổi timezone toàn bộ runtime cho từng request:

~~~java
TimeZone.setDefault(TimeZone.getTimeZone(userZone)); // Anti-pattern.
~~~

Hai đoạn trên là **minh họa cách làm cần tránh trong phương thức**, với `userLocale` và `userZone` là các biến ngữ cảnh; không phải chương trình độc lập. Những thao tác đó thay trạng thái dùng chung của JVM, làm một request có thể ảnh hưởng request khác và các thư viện liên quan.

Thay vào đó, ưu tiên:

~~~java
DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm XXX", locale)
        .withZone(zone)
        .format(instant);
~~~

Đoạn minh họa này yêu cầu `locale`, `zone`, `instant` cùng import `java.time.format.DateTimeFormatter`. `DateTimeFormatter` immutable và thread-safe: `withZone` tạo formatter mới, không chỉnh cấu hình toàn hệ thống.

**Không đoán ngữ cảnh từ máy chủ.** `ZoneId.systemDefault()` phản ánh múi giờ của quá trình Java, thường là UTC trong container; nó không thể thay cho zone tài khoản/người xem hoặc vùng diễn ra sự kiện.

## 4. Thiết kế RequestContext bất biến

Một cấu trúc đơn giản trong Java 17+ dùng `record` để giữ `Locale` và `ZoneId`:

~~~java
import java.time.ZoneId;
import java.util.Locale;
import java.util.Objects;

public record RequestContext(Locale locale, ZoneId zone) {
    public RequestContext {
        Objects.requireNonNull(locale, "locale");
        Objects.requireNonNull(zone, "zone");
    }
}
~~~

Lưu file `RequestContext.java` và biên dịch:

~~~bash
javac -encoding UTF-8 RequestContext.java
~~~

Đây là một **record khai báo kiểu dữ liệu**, không có `main` và không có stdout. Có thể dùng từ controller và service.

Tại sao hợp lý?

- **Tường minh:** chữ ký method cho thấy một chức năng phụ thuộc ngôn ngữ và múi giờ.
- **Bất biến:** hai thành phần record không bị gán lại sau khi tạo; `Locale` và `ZoneId` cũng được thiết kế để dùng an toàn giữa luồng.
- **Không có global state:** request A dùng `vi-VN` không đổi ngữ cảnh request B dùng `fr-FR`.
- **Dễ kiểm thử:** test tự cung cấp context và thời điểm cố định.
- **Dễ truyền qua async:** tham số được capture rõ ràng trong tác vụ, không dựa vào `ThreadLocal` của thread xử lý ban đầu.

Có thể đặt tên `FormattingContext`, `UserPresentationContext` hoặc `RequestContext` tùy phạm vi. Nếu đối tượng chỉ phục vụ hiển thị, tên `FormattingContext` giúp tránh nhầm nó chứa quyền truy cập hay mọi metadata của HTTP request.

**Không biến context thành một túi mọi thông tin.** Những dữ liệu như authentication token, tenant privilege hoặc dữ liệu cá nhân không nên được nhét vào đây chỉ vì tiện truyền qua service. Locale và ZoneId là **sở thích/ngữ cảnh trình bày**, không phải thông tin xác thực.

## 5. Chương trình hoàn chỉnh: hai người dùng, cùng một Instant

Tạo file `ExplicitContextDemo.java`. Chương trình chỉ sử dụng một thời điểm cố định, truyền context vào hàm và không gọi default locale/timezone:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Objects;

public class ExplicitContextDemo {
    public record ViewContext(Locale locale, ZoneId zone) {
        public ViewContext {
            Objects.requireNonNull(locale, "locale");
            Objects.requireNonNull(zone, "zone");
        }
    }

    static String render(Instant when, ViewContext context) {
        DateTimeFormatter formatter = DateTimeFormatter
                .ofPattern("uuuu-MM-dd HH:mm XXX",
                        context.locale())
                .withZone(context.zone());
        return formatter.format(when);
    }

    public static void main(String[] args) {
        Instant when = Instant.parse("2026-10-28T03:30:00Z");

        ViewContext vietnam = new ViewContext(
                Locale.forLanguageTag("vi-VN"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        ViewContext newYork = new ViewContext(
                Locale.US,
                ZoneId.of("America/New_York"));

        System.out.println("VN=" + render(when, vietnam));
        System.out.println("US=" + render(when, newYork));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ExplicitContextDemo.java
java ExplicitContextDemo
~~~

Stdout đã kiểm tra trên OpenJDK 24:

~~~text
VN=2026-10-28 10:30 +07:00
US=2026-10-27 23:30 -04:00
~~~

Giải thích: đầu vào `Instant` hoàn toàn giống nhau. Ở TP. Hồ Chí Minh vào ngày đó, offset là `+07:00`; ở New York, offset là `-04:00` do quy tắc DST của vùng. Vì thế ngày địa phương của New York là **27/10**, trong khi ngày tại Việt Nam là **28/10**.

Pattern trong ví dụ chủ đích dùng trường số và offset để stdout ổn định. Trong UI thực tế, hãy dùng `ofLocalizedDateTime(FormatStyle.MEDIUM).withLocale(locale).withZone(zone)` hoặc pattern riêng theo yêu cầu, để tên tháng và bố cục ngày được bản địa hóa khi thích hợp.

`withLocale` và `withZone` xử lý **hai vấn đề độc lập**. Đổi Locale sang tiếng Pháp vẫn giữ cùng giờ địa phương nếu giữ ZoneId, nhưng tên tháng và bố cục có thể chuyển sang tiếng Pháp. Đổi ZoneId lại làm thay đổi giờ/phút/ngày địa phương được tính từ cùng `Instant`.

## 6. Luồng xử lý: xác định context một lần rồi truyền xuống

Một thiết kế có thể nhìn như:

~~~text
HTTP request / event / scheduled job
          |
          v
ContextResolver (validate preferences + defaults)
          |
          v
RequestContext { Locale, ZoneId }
          |
          +----> Controller ----> Service ----> Presenter
          |                         |
          |                         +----> Asynchronous task (capture context)
          |
          +----> Audit/log layer (UTC/ISO theo chính sách log)
~~~

**Tại biên ứng dụng:**

- Đọc locale từ thiết lập ngôn ngữ đã lưu, lựa chọn UI hoặc `Accept-Language` nếu phù hợp.
- Đọc ZoneId từ thiết lập múi giờ đã lưu, yêu cầu giao diện có kiểm tra hoặc từ chính thực thể nghiệp vụ (ví dụ zone của cửa hàng).
- Áp dụng whitelist/chính sách fallback rõ ràng.
- Tạo `RequestContext` một lần cho operation.
- Chuyển context **bằng tham số** tới những hàm thực sự cần bản địa hóa hoặc quy đổi thời gian.

**Ở service domain:** các phép tính nghiệp vụ không cần ngôn ngữ thì không phải nhận `Locale` chỉ để “đủ chữ ký”. Ngược lại, formatter hoặc function tạo thông báo phụ thuộc ngôn ngữ phải nhận thông tin tương ứng, tránh đọc default một cách ẩn.

Ví dụ phương thức minh họa (không phải chương trình độc lập):

~~~java
ReceiptView buildReceipt(
        Order order, RequestContext context) {

    Instant paidAt = order.paidAt();
    String timeLabel = renderTime(paidAt, context);
    String amountLabel = renderAmount(
            order.amount(), context.locale());
    return new ReceiptView(timeLabel, amountLabel);
}
~~~

Ở đây `Order`, `ReceiptView`, `renderTime`, `renderAmount` thuộc tầng nghiệp vụ giả định. Điều quan trọng là **phụ thuộc được thể hiện rõ ở chữ ký method**; không có cuộc gọi ngầm đến `Locale.getDefault` hay `ZoneId.systemDefault`.

## 7. Chọn Locale từ yêu cầu mà không tin mọi chuỗi người dùng gửi

Một `Accept-Language` header có thể là:

~~~text
fr-CA,fr;q=0.8,en-US;q=0.6
~~~

Đây **không phải một language tag duy nhất** để truyền nguyên vào `Locale.forLanguageTag`. Nó là danh sách ưu tiên cùng trọng số; nếu dùng header này, hãy xử lý bằng cơ chế thương lượng ngôn ngữ, ví dụ `Locale.LanguageRange.parse(...)` rồi lựa chọn trong tập locale được hỗ trợ.

Trong nhiều sản phẩm, thứ tự chính sách có thể là:

1. Locale do người dùng xác nhận trong tài khoản.
2. Locale người dùng chọn trong request hợp lệ.
3. Thương lượng từ `Accept-Language` trên tập được hỗ trợ.
4. Locale mặc định **do sản phẩm định nghĩa** khi không có lựa chọn phù hợp.

Không sử dụng máy chủ làm nguồn sự thật cho locale của người dùng. Ngoài ra, `Locale.forLanguageTag` có thể xử lý tag sai theo cách *lenient* và không nhất thiết ném lỗi cho mọi chuỗi không hợp lệ. Nếu hệ thống yêu cầu một tập locale cụ thể, hãy **đối chiếu với allowlist** sau khi canonicalize hoặc parse.

**Cần phân biệt:** locale của UI không quyết định loại tiền của một giao dịch hoặc vùng giờ của một lịch hẹn. Một người nói tiếng Pháp vẫn có thể đặt lịch tại Việt Nam và thanh toán bằng USD; những trường nghiệp vụ này cần lưu độc lập.

## 8. ZoneId: nguồn gốc, xác thực và fallback

ZoneId nên đến từ **nguồn có ý nghĩa**, ví dụ:

- Múi giờ người dùng đã chọn trong tài khoản cho lịch hiển thị cá nhân.
- Múi giờ cửa hàng/địa điểm cho các hoạt động mở cửa, lịch hẹn tại chỗ.
- Múi giờ được chỉ rõ trong lịch hoặc sự kiện.
- Quy tắc sản phẩm, ví dụ báo cáo toàn công ty chạy theo UTC.

Không suy múi giờ từ locale: `en-US` bao phủ nhiều vùng giờ; `vi-VN` không chứng minh người đang ở Việt Nam. Địa chỉ IP và vị trí trình duyệt cũng có thể không ổn định; khi nhận loại dữ liệu đó, chỉ dùng theo chính sách và cho người dùng quyền xác nhận.

`ZoneId.of(id)` có thể ném `DateTimeException` nếu id không hợp lệ hoặc không được time-zone database hỗ trợ. Không nên bắt lỗi rồi âm thầm chọn máy chủ mà không log/định nghĩa fallback. Đối với hệ thống hạn chế tập vùng giờ, có thể kiểm tra allowlist `Set<String>` gồm những ID được hỗ trợ.

**Chọn `ZoneId` vùng thay vì offset cố định** khi nghiệp vụ phụ thuộc quy tắc DST. `America/New_York` có lịch sử và các quy tắc chuyển offset; `ZoneOffset.of("-05:00")` không có khả năng theo DST.

### Ví dụ Java 17+: resolver kiểm soát tập locale và zone

Tạo file `ContextResolverDemo.java`:

~~~java
import java.time.ZoneId;
import java.util.Locale;
import java.util.Set;

public class ContextResolverDemo {
    record RequestContext(Locale locale, ZoneId zone) {}

    private static final Set<String> LOCALES =
            Set.of("vi-VN", "en-US", "fr-FR");

    private static final Set<String> ZONES =
            Set.of("Asia/Ho_Chi_Minh",
                    "America/New_York",
                    "Europe/Paris");

    static RequestContext resolve(String languageTag,
                                  String zoneId) {
        Locale locale = Locale.forLanguageTag(languageTag);
        String tag = locale.toLanguageTag();

        if (!LOCALES.contains(tag)) {
            throw new IllegalArgumentException(
                    "Unsupported locale");
        }
        if (!ZONES.contains(zoneId)) {
            throw new IllegalArgumentException(
                    "Unsupported time zone");
        }

        return new RequestContext(locale, ZoneId.of(zoneId));
    }

    public static void main(String[] args) {
        RequestContext c = resolve(
                "vi-VN", "Asia/Ho_Chi_Minh");

        System.out.println(c.locale().toLanguageTag());
        System.out.println(c.zone().getId());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ContextResolverDemo.java
java ContextResolverDemo
~~~

Stdout:

~~~text
vi-VN
Asia/Ho_Chi_Minh
~~~

Đây là một chính sách **minh họa**. Một ứng dụng có thể cho phép nhiều locale và zone hơn, cần xử lý `null`/chuỗi rỗng, canonicalization, alias và fallback theo cấu hình thực. `resolve` trong ví dụ cố tình từ chối locale/zone ngoài tập, không đoán default của máy chủ.

Không suy quyền truy cập của người dùng từ `RequestContext`: locale và zone chỉ phục vụ trình bày/lịch, không phải authorization. Dù một người gửi `en-US` hoặc `America/New_York`, họ không có thêm quyền truy cập tài nguyên nào.

## 9. Locale để định dạng số và thông điệp, ZoneId để quy đổi Instant

Đối với số lượng hoặc phần trăm:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(
        context.locale());
String amount = number.format(value);
~~~

Đây là đoạn mã **trong phương thức**, với `context` mang locale, `value` là số và import `java.text.NumberFormat`. `ZoneId` không có tác dụng trong định dạng số.

Đối với thời điểm:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofLocalizedDateTime(
                FormatStyle.MEDIUM)
                .withLocale(context.locale())
                .withZone(context.zone());

String time = formatter.format(instant);
~~~

Đoạn này yêu cầu `instant` kiểu `Instant`, import `java.time.format.*`. **Locale** định hướng cách viết; **ZoneId** định hướng giờ địa phương.

Ví dụ dùng `Locale.FRANCE` và `Asia/Ho_Chi_Minh` có thể cho ngày tháng bằng tiếng Pháp nhưng giờ theo Việt Nam. Đây là cấu hình hợp lệ và có thể được yêu cầu bởi người dùng sống ở một quốc gia nhưng chọn ngôn ngữ khác.

Trong các thành phần tạo message (“Đơn hàng được giao lúc …”), nên dùng **toàn câu được dịch** từ tài nguyên ứng dụng, rồi chèn thời gian đã định dạng vào placeholder phù hợp; không nối mảnh tiếng Anh với mảnh ngày đã format. Một locale context có thể được dùng cho tra cứu ResourceBundle, nhưng **ResourceBundle không tự biết ZoneId**.

## 10. Truyền context qua xử lý bất đồng bộ

Một lỗi phổ biến của ứng dụng Java là đặt locale/zone vào `ThreadLocal` của HTTP thread rồi khởi chạy tác vụ trên executor:

~~~java
CompletableFuture.supplyAsync(
        () -> renderForCurrentUser(event));
~~~

Đây chỉ là **anti-pattern minh họa**: `renderForCurrentUser` là hàm giả định sử dụng ngữ cảnh ẩn. Thread của executor không nhất thiết là thread HTTP; `ThreadLocal` mặc định không tự truyền đúng dữ liệu; task khác có thể dùng lại thread. `InheritableThreadLocal` cũng không phải giải pháp tổng quát cho thread pools vì thread có thể được tạo trước hoặc tái sử dụng.

**Giải pháp rõ ràng:** truyền context bằng tham số hoặc capture một đối tượng bất biến trong lambda. Nó giúp người đọc code và bộ kiểm thử nhìn ra phụ thuộc.

### Ví dụ Java 17+ chạy được với CompletableFuture

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;

public class AsyncContextDemo {
    record ViewContext(Locale locale, ZoneId zone) {}

    static String render(Instant t, ViewContext c) {
        return DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", c.locale())
                .withZone(c.zone())
                .format(t);
    }

    public static void main(String[] args) {
        Instant instant =
                Instant.parse("2026-10-28T03:30:00Z");

        ViewContext vi = new ViewContext(
                Locale.forLanguageTag("vi-VN"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        ViewContext us = new ViewContext(
                Locale.US,
                ZoneId.of("America/New_York"));

        CompletableFuture<String> vnTask =
                CompletableFuture.supplyAsync(
                        () -> render(instant, vi));

        CompletableFuture<String> usTask =
                CompletableFuture.supplyAsync(
                        () -> render(instant, us));

        System.out.println("VN "
                + vnTask.join());
        System.out.println("US "
                + usTask.join());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AsyncContextDemo.java
java AsyncContextDemo
~~~

Stdout:

~~~text
VN 2026-10-28 10:30 +07:00
US 2026-10-27 23:30 -04:00
~~~

Hai task có thể chạy theo thứ tự bất kỳ, nhưng **các dòng được in từ main sau `join()` theo thứ tự cố định**. Context được capture thành hai giá trị bất biến khác nhau. Đừng dựa vào việc worker thread tình cờ có đúng default JVM.

Khi dùng `ExecutorService`, reactive pipeline, message queue hoặc scheduled jobs, vẫn áp dụng nguyên tắc tương tự: đính kèm dữ liệu context hợp lệ với work item và truyền tới các hàm cần nó. Với job chạy sau khi request đã kết thúc, cần cân nhắc **snapshot** ngôn ngữ/múi giờ tại thời điểm tạo job hay đọc lại sở thích người dùng ở thời điểm thực thi. Đó là quyết định nghiệp vụ, không phải hành vi mặc định của Java.

## 11. Lịch địa phương: cùng 09:00 có thể là hai Instant khác nhau

Khi người dùng nhập “09:00 ngày 28/10/2026”, ta chưa biết một thời điểm UTC duy nhất nếu thiếu `ZoneId`. Cùng `LocalDateTime` có thể đại diện những `Instant` khác nhau theo vùng:

~~~java
LocalDateTime local =
        LocalDateTime.of(2026, 10, 28, 9, 0);

Instant hcm =
        local.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant();

Instant ny =
        local.atZone(ZoneId.of("America/New_York"))
                .toInstant();
~~~

Đây là mã **minh họa trong một phương thức**, cần import `java.time.*`. Với dữ liệu ngày đã cho, `hcm` là `2026-10-28T02:00:00Z` và `ny` là `2026-10-28T13:00:00Z` theo time-zone rules đã kiểm chứng.

Vì thế nên lưu **zone của lịch hẹn hoặc địa điểm** trong model khi nghiệp vụ dựa trên giờ địa phương. Không chỉ lưu `LocalDateTime` nếu downstream phải gửi lời nhắc ở một mốc UTC chính xác. Đối với sự kiện tương lai, hãy quyết định quy tắc khi luật giờ mùa hè thay đổi, thời điểm tính mốc UTC và cách thông báo đến người dùng.

Đừng tự lấy `ZoneId` từ locale. Một khách chọn `Locale.US` nhưng đặt lịch dịch vụ ở Việt Nam thường cần `Asia/Ho_Chi_Minh` **cho lịch hẹn**; khi hiển thị trên thiết bị cá nhân, người xem có thể lựa chọn zone riêng để quy đổi.

## 12. DST: không phải LocalDateTime nào cũng hợp lệ hoặc duy nhất

Đối với vùng thay đổi giờ mùa hè, có thể tồn tại ba trạng thái tại một `LocalDateTime`:

| Số offset hợp lệ | Ý nghĩa | Chính sách cần có |
| ---: | --- | --- |
| 0 | **Gap**: giờ địa phương không tồn tại | Từ chối, yêu cầu chọn lại hoặc dịch theo quy tắc rõ |
| 1 | Giờ địa phương có một offset hợp lệ | Có thể xác định một Instant |
| 2 | **Overlap**: giờ địa phương xảy ra hai lần | Chọn offset trước/sau hoặc yêu cầu người dùng quyết định |

`LocalDateTime.atZone(zone)` có cách xử lý mặc định khi gặp gap/overlap. Điều đó thuận tiện nhưng **không có nghĩa đã phản ánh đúng quy tắc đặt lịch của sản phẩm**. Nếu yêu cầu sự rõ ràng, dùng `ZoneRules.getValidOffsets(localDateTime)` để kiểm tra trước.

### Ví dụ Java 17+: kiểm tra DST ở New York

Tạo `DstValidityDemo.java`:

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

public class DstValidityDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime gap =
                LocalDateTime.of(2026, 3, 8, 2, 30);
        LocalDateTime normal =
                LocalDateTime.of(2026, 7, 1, 9, 0);
        LocalDateTime overlap =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        for (LocalDateTime local : List.of(
                gap, normal, overlap)) {
            List<ZoneOffset> offsets =
                    rules.getValidOffsets(local);
            System.out.println(local
                    + " offsetCount=" + offsets.size()
                    + " offsets=" + offsets);
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 DstValidityDemo.java
java DstValidityDemo
~~~

Stdout trên dữ liệu múi giờ JDK được kiểm tra:

~~~text
2026-03-08T02:30 offsetCount=0 offsets=[]
2026-07-01T09:00 offsetCount=1 offsets=[-04:00]
2026-11-01T01:30 offsetCount=2 offsets=[-04:00, -05:00]
~~~

Ngày **8/3/2026** tại New York, 02:30 rơi vào khoảng giờ không tồn tại do chuyển sang DST. Ngày **1/11/2026**, 01:30 xuất hiện hai lần với hai offset khác nhau khi quay lại giờ chuẩn. Với lịch hẹn, tạo mốc UTC từ local+zone mà không xét hai trường hợp này có thể đặt nhầm giờ.

**Quan trọng:** ví dụ dùng dữ liệu quy tắc vùng của JDK; ở các bản tzdb khác hoặc nếu pháp luật thay đổi, quy tắc tương lai có thể khác. Kiểm thử trên runtime triển khai và version database thời gian đúng cho hệ thống.

## 13. Phân biệt ZoneId trình bày với ZoneId nghiệp vụ

Không nhất thiết chỉ có **một** ZoneId cho mọi việc trong một request. Ví dụ:

- `viewerZone`: vùng giờ mà người dùng muốn xem trên màn hình.
- `eventZone`: vùng giờ của địa điểm tổ chức.
- `reportZone`: vùng giờ quy định chốt kỳ báo cáo.
- `systemLogZone`: thường dùng UTC để log/sắp xếp sự kiện.

Nếu các vùng này khác nhau, **đặt tên rõ** hoặc dùng các value objects riêng, thay vì dùng một `context.zone()` cho mọi bước một cách máy móc.

Một `RequestContext` kiểu `locale + viewerZone` rất hữu ích cho **presentation layer**. Nhưng việc xác định một lịch họp tại New York có thể phải lấy `event.zoneId` từ bản ghi sự kiện; không được âm thầm thay bằng zone của người xem.

Tương tự, chọn locale hiển thị không được làm thay đổi currency code của đơn hàng, định dạng ID kỹ thuật hoặc timezone chính thức của kỳ kế toán. **Ngữ cảnh trình bày** và **nguồn sự thật nghiệp vụ** là hai tầng khác nhau.

## 14. Job nền và gửi thông báo: snapshot hay lấy sở thích mới?

Giả sử người dùng đăng ký nhận email nhắc hẹn sau ba ngày. Có hai thiết kế hợp lệ:

1. **Snapshot tại thời điểm lên lịch:** lưu locale và ZoneId đã được chọn khi tạo nhắc hẹn. Thông báo thể hiện cùng cách hiểu mà người dùng đã xác nhận lúc đặt lịch.
2. **Resolve lại tại thời điểm gửi:** tải locale và vùng giờ từ tài khoản khi job chạy. Thông báo theo sở thích mới, nhưng phải bảo đảm sự kiện vẫn dùng zone nghiệp vụ đúng.

Chọn theo kỳ vọng sản phẩm, bảo đảm có dấu vết/version khi cần. Một job không thể dựa vào request-scoped object đã hết vòng đời; dữ liệu cần thiết phải đi kèm work item hoặc có thể đọc lại có kiểm soát.

Ví dụ payload ý tưởng:

~~~text
notificationId: 1729
eventInstant: 2026-10-28T03:30:00Z
recipientId: 431
locale: vi-VN
viewerZone: Asia/Ho_Chi_Minh
~~~

Đây là **ví dụ cấu trúc**, không phải Java code hoặc lời khuyên lưu mọi thông tin người dùng vào queue. Dữ liệu nhạy cảm cần được tối thiểu hóa và bảo vệ; dùng ID để tham chiếu và giữ snapshot chỉ khi nghiệp vụ cần.

Khi chạy job, tạo lại `RequestContext` từ dữ liệu đã kiểm tra và tiếp tục truyền tường minh. Không mong `ThreadLocal` của HTTP request tồn tại trong scheduler.

## 15. Clock tường minh để kiểm thử và ngăn phụ thuộc thời gian hiện tại

Ngữ cảnh locale/zone không giải quyết toàn bộ tính tái lập nếu code vẫn gọi `Instant.now()` rải rác. Khi một chức năng cần “thời điểm hiện tại”, cân nhắc truyền `Clock` như một phụ thuộc riêng:

~~~java
Instant now = clock.instant();
~~~

Đây là đoạn mã minh họa trong phương thức có `Clock clock`. Trong test:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-10-28T03:30:00Z"),
        ZoneOffset.UTC);
~~~

Đoạn minh họa này cần import `java.time.*`. `Clock.fixed` cung cấp thời điểm cố định. Có thể truyền `Clock` qua constructor/service và `RequestContext` qua operation, vì chúng giải quyết **hai câu hỏi khác nhau**:

- `Clock`: “hiện tại là lúc nào?”
- `RequestContext`: “hiển thị theo ngôn ngữ và múi giờ của ai?”

Nếu tạo `Clock.systemUTC()` trong production, đó là nguồn thời gian chủ đích, không phải timezone của người xem. Với lịch hẹn từ `LocalDateTime`, zone phải đến từ dữ liệu lịch chứ không nhất thiết từ clock.

## 16. Tính an toàn luồng và vòng đời của formatter

`DateTimeFormatter` là immutable và thread-safe. `withLocale` và `withZone` trả về formatter mới; có thể tạo formatter base dùng chung và áp dụng context tại từng lần hiển thị.

~~~java
private static final DateTimeFormatter BASE =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

static String format(Instant instant,
                     RequestContext context) {
    return BASE.withLocale(context.locale())
            .withZone(context.zone())
            .format(instant);
}
~~~

Đây là **mã minh họa trong class**, yêu cầu import và kiểu `RequestContext` được khai báo trước. Pattern chủ yếu gồm ký hiệu số; với định dạng tên tháng nên dùng localized style hoặc formatter có locale thích hợp.

Ngược lại, `NumberFormat` và `DecimalFormat` là những formatter **có thể thay đổi trạng thái** và nói chung không nên chia sẻ một instance mutable rồi `setCurrency`/`setMaximumFractionDigits` theo request đồng thời. Tạo instance riêng hoặc quản lý concurrency phù hợp.

`Locale`, `ZoneId` và record context có thể được truyền giữa các thread khi bản thân đối tượng được giữ bất biến. Nhưng đừng gắn mọi thông tin phụ thuộc request vào singleton mutable; một context mới cho request/job sẽ dễ suy luận và an toàn hơn.

## 17. Các lỗi phổ biến

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Dùng `Locale.setDefault` theo request | Request này có thể ảnh hưởng request khác | Truyền Locale tường minh |
| Dùng `TimeZone.setDefault` theo request | Timezone toàn JVM bị đổi | Truyền ZoneId tường minh |
| Dùng `ZoneId.systemDefault()` cho người xem | Lấy múi giờ container/server | Lấy user preference/venue zone |
| Cho rằng `vi-VN` luôn là `Asia/Ho_Chi_Minh` | Sai với người dùng khác vùng | Tách locale và zone |
| Cho rằng `en-US` suy ra một timezone | Mỹ có nhiều timezone | Yêu cầu zone phù hợp |
| Đưa `Accept-Language` nguyên chuỗi vào `forLanguageTag` | Không đúng cấu trúc header | Parse/negotiation và allowlist |
| Dùng `Locale.forLanguageTag` làm strict validator | Tag sai có thể được xử lý lenient | Kiểm tra locale được hỗ trợ |
| Nhận ZoneId tùy ý nhưng không bắt lỗi | Có thể `DateTimeException` | Validate và xử lý fallback rõ |
| Sử dụng `ThreadLocal` làm context qua async | Worker thread thiếu/sai dữ liệu | Capture và truyền context |
| Chỉ lưu `LocalDateTime` cho cuộc hẹn toàn cầu | Không xác định một Instant | Lưu zone và xử lý DST |
| Thay `ZoneId` bằng offset cố định | Sai khi chuyển DST | Giữ region-based ZoneId |
| Bỏ qua gap/overlap DST | Lịch hẹn sai một giờ hoặc không tồn tại | `getValidOffsets` và chính sách |
| Dùng viewer zone cho giờ đóng sổ địa điểm | Sai timezone nghiệp vụ | Phân biệt eventZone/reportZone |
| Dùng local date format trong log/ID | Khó đối chiếu khi locale đổi | Dùng UTC/ISO theo hợp đồng |
| Test phụ thuộc `now()` và default | Không tái lập giữa môi trường | Inject Clock, Locale, ZoneId |
| Dùng chung NumberFormat mutable | Race condition | Tạo formatter riêng cho mỗi ngữ cảnh |

## 18. Checklist triển khai và kiểm thử

1. **Context type:** có `Locale` và `ZoneId` với chính sách null rõ ràng.
2. **Nguồn dữ liệu:** locale và zone được chọn từ tài khoản, lựa chọn UI hay ngữ cảnh nghiệp vụ, không suy từ server.
3. **Validation:** hỗ trợ language tag/zone ID hợp lệ theo tập locale/zone của sản phẩm.
4. **Fallback:** nếu thiếu lựa chọn, dùng mặc định **được sản phẩm định nghĩa**, không dùng ngầm system default.
5. **Controller/service:** context được truyền tường minh tới nơi cần.
6. **Async:** tác vụ dùng context đã capture/đọc lại có chủ đích, không dựa vào `ThreadLocal`.
7. **Formatting:** `DateTimeFormatter.withLocale` cho ngôn ngữ, `withZone` cho vùng giờ.
8. **Numbers/currency:** formatter số nhận locale; currency thuộc dữ liệu giao dịch, không phụ thuộc viewer zone.
9. **Instant:** cùng mốc UTC được hiển thị khác nhau theo vùng, nhưng không đổi bản chất thời điểm.
10. **Calendar semantics:** local date/time không bị quy đổi thành Instant khi chưa có zone nghiệp vụ.
11. **DST:** có test cho gap 0 offset, normal 1 offset và overlap 2 offset.
12. **Clock:** thời điểm hiện tại được cố định trong test.
13. **Default state:** không gọi `Locale.setDefault` hoặc `TimeZone.setDefault` theo request.
14. **Parallel requests:** gửi đồng thời context `vi-VN` và `en-US`, xác nhận không rò dữ liệu.
15. **Time zone DB:** kiểm tra version runtime/tzdb khi lịch tương lai có thể chịu thay đổi chính sách DST.
16. **Presentation vs domain:** phân biệt viewer zone với event/venue/report zone.
17. **Localization data:** kết quả ngôn ngữ phụ thuộc dữ liệu locale JDK; kiểm thử runtime phát hành.
18. **Logging:** ghi timestamp rõ ràng (thường UTC/ISO) và truyền zone khi cần theo chính sách log.
19. **Privacy/security:** context không được dùng để cấp quyền hoặc lưu dữ liệu nhạy cảm không cần thiết.
20. **Contract tests:** API truyền locale/zone theo quy định; message/jobs có chiến lược snapshot/resolve.

### Bài tập thực hành

1. Chạy `ExplicitContextDemo`; giữ `ZoneId` Việt Nam nhưng đổi `Locale` từ `vi-VN` sang `fr-FR` và dùng pattern có `MMMM`. Giải thích vì sao tên tháng đổi nhưng giờ địa phương không đổi.
2. Chạy `AsyncContextDemo` với ba request song song. Đảm bảo mọi task vẫn có locale/zone của chính mình dù executor thực thi thứ tự khác.
3. Viết một `ContextResolver` hỗ trợ locale `vi-VN`, `fr-FR` và zone `Asia/Ho_Chi_Minh`, `Europe/Paris`; viết test cho giá trị bị từ chối.
4. Tạo `LocalDateTime.of(2026,3,8,2,30)` ở `America/New_York`, dùng `ZoneRules.getValidOffsets` rồi đề xuất chính sách đặt lịch khi `offsetCount == 0`.
5. Tạo hai `Instant` từ cùng local `2026-11-01T01:30` ở New York với hai offset hợp lệ; tính chênh lệch giữa chúng.
6. Viết test dạng table-driven cho 2026-10-28T03:30Z với context VN/US/France, không dùng `Instant.now()` hoặc default JVM.
7. Thiết kế payload của một job gửi email sau ba ngày: xác định locale và zone cần snapshot hay đọc lại, phân biệt zone hiển thị với zone địa điểm.
8. Thêm một `Clock.fixed(...)` cho service tạo nhãn “đã cập nhật X phút trước”, và truyền `Locale` cho thông điệp bản địa hóa; giải thích vì sao cần cả Clock lẫn locale.

## 19. Kết luận

**Locale** quyết định ngôn ngữ/quy ước hiển thị; **ZoneId** quyết định cách một mốc thời gian được quy đổi sang ngày giờ địa phương. Hai đối tượng có thể độc lập hoàn toàn: người nói tiếng Việt sống tại Pháp, một hội nghị ở New York có khách từ nhiều quốc gia, hoặc báo cáo UTC hiển thị theo ngôn ngữ riêng của người đọc.

Thiết kế bền vững là **tạo context bất biến từ nguồn được kiểm tra ngay tại ranh giới ứng dụng**, truyền nó bằng tham số qua các tầng và capture rõ khi chạy bất đồng bộ. Tránh thay global defaults hoặc dựa vào `ThreadLocal` qua thread pools. Đối với thời điểm đã xảy ra, giữ `Instant`; đối với lịch địa phương, giữ ZoneId nghiệp vụ và xử lý DST; đối với test, dùng `Clock.fixed` và dữ liệu cố định.

Một API rõ ràng như `format(Instant when, RequestContext context)` giúp ứng dụng đa người dùng **không rò locale, không nhầm múi giờ và có kết quả kiểm thử tái lập**.

## Tài liệu tham khảo

- [Oracle Java 21 — Locale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html)
- [Oracle Java 21 — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html)
- [Oracle Java 21 — ZoneRules](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/zone/ZoneRules.html)
- [Oracle Java 21 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html)
- [Oracle Java 21 — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html)
- [Oracle Java 21 — LocalDateTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html)
- [Oracle Java 21 — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html)
- [Oracle Java 21 — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
