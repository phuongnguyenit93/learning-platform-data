# Kiểm thử nhiều luồng với formatter và locale khác nhau

## 1. Vấn đề: đúng ở một request, sai khi nhiều người dùng đồng thời

Một ứng dụng Java đa ngôn ngữ có thể phục vụ đồng thời người dùng `en-US`, `de-DE`, `vi-VN` và `fr-FR`. Mỗi người có quy tắc riêng để hiển thị số, phần trăm, tiền tệ, ngày giờ và thông báo. Nếu một formatter **có trạng thái mutable** được chia sẻ giữa các request, luồng này có thể thay cấu hình trong lúc luồng khác đang sử dụng, gây ra:

- Người dùng Mỹ nhìn thấy dấu phân nhóm, dấu thập phân hoặc ký hiệu tiền của người dùng Đức.
- Giá trị USD của đơn hàng A bị render bằng ký hiệu EUR do request B vừa gọi `setCurrency`.
- `SimpleDateFormat` trả kết quả sai, lỗi parse ngẫu nhiên hoặc exception trong khi dùng chung nhiều thread.
- Thay đổi `Locale.setDefault` toàn JVM để phục vụ từng request làm request khác nhận formatter mặc định sai locale.
- Test tuần tự vượt qua nhưng test load/concurrency bị flaky: cùng input và domain value, output không ổn định.

Đây là vấn đề thiết kế **trạng thái và ownership** của đối tượng, không phải lỗi bản dịch. Cùng một dữ liệu domain `BigDecimal("1234.50")` và `Currency USD` phải được bảo toàn. Chỉ **presentation formatter** được phép quyết định cách hiển thị theo locale/zone của **chính request đó**.

Bài thuộc nhóm **Kiểm thử và lỗi**, tập trung vào cách **phát hiện, tái hiện, sửa và kiểm thử** những lỗi do nhiều luồng dùng formatter và locale khác nhau. Tất cả ví dụ chính dùng Java 17+.

### Mục tiêu

Sau bài này, bạn có thể:

1. Phân biệt các API **mutable, không bảo đảm thread-safe** với các API **immutable/thread-safe**.
2. Hiểu vì sao tạo một `NumberFormat`/`SimpleDateFormat` static rồi thay locale/currency cho từng request là nguy hiểm.
3. Viết bài kiểm thử race **có kiểm soát bằng CountDownLatch** thay vì chỉ trông đợi lỗi ngẫu nhiên.
4. Tái hiện rò rỉ locale khi sử dụng `Locale.setDefault(...)` trong server đa luồng.
5. Triển khai formatter **riêng theo thao tác/request** hoặc dùng `DateTimeFormatter` immutable chia sẻ an toàn.
6. Thiết kế stress test nhiều locale, kiểu number/date/currency khác nhau, dữ liệu cố định và domain invariants.
7. Hiểu giới hạn của `ThreadLocal`, cache theo `Locale`, `ResourceBundle`, `MessageFormat` và `Collator`.
8. Phân biệt kiểm thử **hành vi đúng chức năng** với kiểm thử **có bằng chứng về race**.

## 2. Một đối tượng formatter chứa trạng thái gì?

Ví dụ:

```java
NumberFormat number =
        NumberFormat.getCurrencyInstance(Locale.US);
number.setCurrency(Currency.getInstance("USD"));
number.setMaximumFractionDigits(2);
```

Đây là đoạn minh họa trong phương thức; cần import `java.text.NumberFormat`, `java.util.Currency`, `java.util.Locale`. Dù formatter được tạo theo `Locale.US`, object vẫn có những trường cấu hình có thể thay đổi: currency, grouping, precision, rounding, parsing behavior, symbols và trong `DecimalFormat` còn có pattern, multiplier, `DecimalFormatSymbols`.

Nếu giữ một instance ở static field:

```java
// Anti-pattern nếu nhiều request được phép thay cấu hình:
static final NumberFormat SHARED =
        NumberFormat.getCurrencyInstance(Locale.US);
```

thì `final` chỉ bảo đảm **tham chiếu không được gán lại**. Nó **không đóng băng trạng thái bên trong**. Luồng A có thể gọi `SHARED.setCurrency(USD)` và luồng B gọi `SHARED.setCurrency(EUR)` trước khi A thực hiện `format`.

Ngay cả nếu mọi request chỉ gọi `format` trên cùng `NumberFormat` mà không chủ động gọi setter, tài liệu Java SE vẫn nêu **number formats generally not synchronized**. Không suy diễn tính thread-safe chỉ từ việc ứng dụng hiện tại không sửa cấu hình sau khởi tạo.

### Bảng tính chất API cần nhớ

| API | Đặc điểm quan trọng | Chiến lược sử dụng |
| --- | --- | --- |
| `java.text.NumberFormat` | Mutable; không bảo đảm thread-safe | Instance riêng mỗi thao tác hoặc đồng bộ có chủ đích |
| `java.text.DecimalFormat` | Mutable: pattern, symbols, rounding, multiplier và parse state | Không share mutable formatter giữa requests |
| `java.text.DateFormat` / `SimpleDateFormat` | Mutable; không an toàn để dùng chung không đồng bộ | Ưu tiên `java.time`; legacy thì tạo instance riêng |
| `java.text.MessageFormat` | Mutable: pattern, locale, các subformatter | Tạo instance riêng, hoặc dùng clone/đồng bộ với hợp đồng rõ |
| `java.text.Collator` | Mutable: strength/decomposition; không tự bảo đảm mọi cấu hình dùng chung | Một instance mỗi thao tác hoặc bản sao độc lập |
| `java.util.Calendar` | Mutable date/time fields, locale/week policy | Không share giữa requests |
| `java.util.TimeZone` | Mutable configuration trong một số triển khai; global default có thể đổi | Tránh dùng object shared mutable |
| `java.time.format.DateTimeFormatter` | **Immutable và thread-safe** | An toàn khi share cùng cấu hình |
| `java.time.Instant`, `LocalDate`, `ZonedDateTime` | Immutable | An toàn để chia sẻ như giá trị |
| `java.util.Locale` | Immutable | Có thể dùng chung; lưu locale trong context từng request |
| `java.util.Currency`, `BigDecimal` | Immutable value objects | Dùng làm dữ liệu domain; format ở boundary |
| `java.util.ResourceBundle` | Cơ chế bundle hỗ trợ truy cập đồng thời; provider/subclass có thể có riêng trạng thái | Chọn đúng locale, không mutate bundle/custom data |
| `java.text.DecimalFormatSymbols` | Mutable | Không chia sẻ rồi sửa symbols giữa threads |

**Điểm then chốt:** tính bất biến của `Locale` không truyền sang formatter mutable được tạo bằng locale đó. Và tính thread-safe của `DateTimeFormatter` không có nghĩa có thể thay đổi `Locale.setDefault` toàn JVM mà không gây ảnh hưởng tới request khác.

## 3. Ba loại lỗi cần kiểm thử riêng

### 3.1. Data race và shared mutable state

Hai luồng sử dụng cùng một instance. Một luồng đổi `setCurrency`, `setGroupingUsed` hoặc pattern trong khi luồng khác đang định dạng. Có thể có lỗi logic dù thao tác setter và format **không cùng chạy tại đúng một CPU instruction**: chỉ cần thao tác của hai request xen kẽ đã đủ.

### 3.2. Global-state interference

Một request gọi `Locale.setDefault(...)` hoặc `Locale.setDefault(Locale.Category.FORMAT, ...)` để tạm đổi ngôn ngữ. Đây là **default toàn JVM**, không phải biến local của request hay thread. Một request khác dùng `NumberFormat.getNumberInstance()` **không truyền locale** có thể nhận locale của người dùng trước.

### 3.3. Incorrect cache key hoặc vòng đời formatter

Một cache như:

```java
Map<String, DateTimeFormatter> cache;
```

không tự đúng chỉ vì `ConcurrentHashMap` an toàn cho nhiều luồng. Key cũng phải bao gồm **những cấu hình định danh output**: pattern, `Locale`, `ZoneId`, chronology, currency/numbering/rounding policy khi thích hợp. Nếu cache một formatter immutable theo pattern nhưng bỏ locale, ứng dụng không có data race trong Java memory model mà vẫn **trả kết quả sai theo ngữ cảnh**.

Đây là ba lỗi khác nhau, có thể tồn tại độc lập. Bộ test tốt phải xác nhận cả **thread safety**, **request isolation**, và **correct cache-key semantics**.

## 4. Anti-pattern 1: một `NumberFormat` chia sẻ cho nhiều currencies

Giả sử server khai báo:

```java
static final NumberFormat CURRENCY_FORMAT =
        NumberFormat.getCurrencyInstance(Locale.US);

String show(BigDecimal amount, Currency currency) {
    CURRENCY_FORMAT.setCurrency(currency);
    return CURRENCY_FORMAT.format(amount);
}
```

Đây là code minh họa, cần khai báo trong class. Tính chất nguy hiểm: mỗi request cố thay một object chung để phục vụ currency của mình.

### Timeline

```text
Thread A (đơn USD)             Thread B (đơn EUR)
-------------------------      ------------------------
setCurrency(USD)
                               setCurrency(EUR)
format(1234.50)
→ kết quả có thể là €1,234.50
```

Bản thân request A vẫn nắm `Currency USD` đúng trong domain; lỗi xuất hiện vì formatter dùng chung đã bị thay cấu hình. Không sửa bằng cách đổi cả domain currency của A, mà phải sửa **ownership của formatter**.

## 5. Tái hiện lỗi có kiểm soát bằng `CountDownLatch`

Một race test chỉ chạy hai tác vụ rồi `sleep(10)` là thiếu tin cậy: scheduler có thể chạy theo thứ tự khác, lỗi không xuất hiện và test pass dù code vẫn sai.

`CountDownLatch` giúp **đặt chính xác điểm xen kẽ**. Ví dụ bên dưới ép:

1. Luồng A đặt shared formatter ở USD.
2. Luồng B đợi A xong rồi đặt formatter ở EUR.
3. Luồng A chỉ bắt đầu format sau khi B đã đổi currency.

Tạo file `SharedCurrencyRaceDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Currency;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SharedCurrencyRaceDemo {
    static final NumberFormat SHARED =
            NumberFormat.getCurrencyInstance(Locale.US);

    public static void main(String[] args) throws Exception {
        CountDownLatch usdSet = new CountDownLatch(1);
        CountDownLatch eurSet = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<String> userA = pool.submit(() -> {
                SHARED.setCurrency(Currency.getInstance("USD"));
                usdSet.countDown();
                eurSet.await();
                return SHARED.format(new BigDecimal("1234.50"));
            });

            Future<String> userB = pool.submit(() -> {
                usdSet.await();
                SHARED.setCurrency(Currency.getInstance("EUR"));
                eurSet.countDown();
                return "configured EUR";
            });

            System.out.println("B: " + userB.get());
            System.out.println("A: " + userA.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 SharedCurrencyRaceDemo.java
java SharedCurrencyRaceDemo
```

Kết quả trên JDK đã chạy thử với locale data thông dụng:

```text
B: configured EUR
A: €1,234.50
```

Điều đáng lưu ý:

- A **đang có ý định format USD** nhưng nhận ký hiệu EUR.
- Các latch bảo đảm B đã đặt EUR trước khi A gọi `format`. Đây là **state interference có điều phối**, không dựa vào xác suất race tình cờ.
- `NumberFormat` của A vẫn được tạo với locale US, nên dấu phân nhóm/thập phân vẫn theo US; chỉ currency symbol bị thay. Nếu còn cùng lúc thay locale provider/default hoặc pattern, lỗi có thể phức tạp hơn.
- Output symbol cụ thể có thể thay theo JDK/locale data; điều chắc chắn cần assert trong test là **mã currency/cấu hình của formatter A đã bị B làm sai so với request A**.
- `CountDownLatch.await()` được khai báo ném `InterruptedException`; `Callable` do `ExecutorService.submit` chọn cho lambda ở đây có thể ném exception đó. Khi viết code tác vụ thật, cần có chính sách xử lý interrupt/cancellation rõ.

**Không coi ví dụ là cách sử dụng formatter hợp lệ**. Nó cố tình minh họa sự cố để test và đào tạo.

## 6. Cách sửa: mỗi tác vụ có formatter riêng

Thay vì `SHARED`, tạo formatter trong phạm vi local của request:

```java
static String showMoney(BigDecimal amount,
        Currency currency, Locale locale) {
    NumberFormat formatter =
            NumberFormat.getCurrencyInstance(locale);
    formatter.setCurrency(currency);
    return formatter.format(amount);
}
```

Mỗi invocation có object mới. Không có request khác giữ cùng instance để sửa trước khi `format`. Đây là hướng sửa **đơn giản, ít rủi ro và dễ kiểm thử**.

**Đừng nhầm "tạo formatter riêng" với "tạo JVM riêng"**; chỉ cần một object mới trong mỗi invocation hoặc một lifetime không bị share. Khi profiling cho thấy việc tạo formatter thật sự tốn chi phí đáng kể, có thể cân nhắc caching cấu hình bất biến hoặc chiến lược instance-per-thread có kỷ luật, nhưng phải bảo toàn locale/currency và trạng thái mutable.

### Ví dụ Java 17+: thử 1.000 tác vụ nhiều locale

Tạo file `SafeNumberConcurrencyDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SafeNumberConcurrencyDemo {
    public static void main(String[] args) throws Exception {
        final BigDecimal expected = new BigDecimal("1234.50");
        List<Callable<Boolean>> tasks = new ArrayList<>();

        for (int i = 0; i < 1_000; i++) {
            final Locale locale =
                    (i % 2 == 0) ? Locale.US : Locale.GERMANY;

            tasks.add(() -> {
                // Instance mới, private cho đúng một tác vụ.
                NumberFormat base =
                        NumberFormat.getNumberInstance(locale);
                if (!(base instanceof DecimalFormat formatter)) {
                    return false;
                }
                formatter.setMinimumFractionDigits(2);
                formatter.setMaximumFractionDigits(2);
                formatter.setParseBigDecimal(true);

                String rendered = formatter.format(expected);
                ParsePosition position = new ParsePosition(0);
                Number parsed =
                        formatter.parse(rendered, position);

                return parsed instanceof BigDecimal exact
                        && expected.compareTo(exact) == 0
                        && position.getIndex() == rendered.length();
            });
        }

        ExecutorService pool = Executors.newFixedThreadPool(8);
        int failures = 0;
        try {
            List<Future<Boolean>> results =
                    pool.invokeAll(tasks);
            for (Future<Boolean> result : results) {
                if (!result.get()) {
                    failures++;
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("cases=" + tasks.size()
                + " failures=" + failures);
    }
}
```

```bash
javac -encoding UTF-8 SafeNumberConcurrencyDemo.java
java SafeNumberConcurrencyDemo
```

Stdout trên runtime đã kiểm thử:

```text
cases=1000 failures=0
```

Test này kiểm tra **isolation và numeric round-trip trong điều kiện chọn formatter chỉ hiển thị 2 chữ số phần lẻ**, với giá trị có đúng 2 chữ số. Nó **không chứng minh bằng một lần chạy** rằng mọi phiên bản JDK/provider đều an toàn, và cũng không kiểm tra strict grouping input. Tuy nhiên, thiết kế per-task tránh đúng loại chia sẻ mutable object đã minh họa.

Một suite production còn nên thêm:

- Nhiều amount khác nhau, cả số âm, số 0, số lớn, scale khác nhau.
- `en-US`, `de-DE`, `fr-FR`, `vi-VN`, `ar-EG`, nhiều currency thực tế.
- Số lượng luồng và lịch chạy khác nhau, barrier đồng thời, workload lặp lại.
- Assertions theo **giá trị domain** và currency code, không chỉ kiểm tra output là chuỗi không rỗng.
- Test chính sách rounding/scale khi `format → parse` không phải phép biến đổi bảo toàn mọi chữ số.

## 7. Anti-pattern 2: đổi `Locale.setDefault` cho từng request

`Locale.setDefault(...)` và `Locale.setDefault(Locale.Category.FORMAT, ...)` thay đổi **default của JVM**. Nó không tạo một "locale local" riêng cho thread đang chạy.

Phân biệt:

- `Locale.getDefault()`: locale mặc định chung.
- `Locale.getDefault(Locale.Category.DISPLAY)`: mặc định phục vụ hiển thị tên locale/language.
- `Locale.getDefault(Locale.Category.FORMAT)`: mặc định cho nhiều factory formatter số/ngày.
- `NumberFormat.getNumberInstance()`: overload **không có locale**, dựa vào default FORMAT.
- `NumberFormat.getNumberInstance(locale)`: overload **có locale**, giảm phụ thuộc vào global default.
- `String.format(locale, ...)`: chọn locale tường minh khi cần string formatting; `String.format(...)` không có locale có thể dùng default FORMAT.
- `DateTimeFormatter.withLocale(locale)`: trả bản formatter immutable cấu hình theo locale tường minh.

**Cạm bẫy:** code dùng `Locale.setDefault(Locale.US)` để "khởi tạo môi trường tiếng Anh" rồi sau đó một request gọi `setDefault(Locale.GERMANY)`. Không thread-local nào bảo vệ được default JVM này khi các request khác vẫn gọi API factory không truyền locale.

### Timeline lỗi

```text
Thread A: setDefault(FORMAT, en-US)
Thread B: setDefault(FORMAT, de-DE)
Thread A: NumberFormat.getNumberInstance().format(1234.5)
       → 1.234,5 (định dạng Đức)
```

**Cách đúng:** luôn xác định `Locale` của request từ profile/session/đầu vào đã kiểm tra, rồi truyền vào formatter:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(requestLocale);
```

Không sửa global default để phục vụ từng request. Với ứng dụng chỉ một locale toàn process, cấu hình default lúc khởi động có thể hợp lý, nhưng vẫn nên làm dependency của formatter rõ ràng và test không dựa vào locale của máy lập trình.

## 8. Java 17+: tái hiện race của `Locale.setDefault`

Ví dụ dưới đây **thay đổi default toàn JVM có chủ đích**, vì vậy chỉ chạy trong **chương trình demo độc lập**, không gọi trong server hay cùng test suite với tác vụ phụ thuộc default locale. Nó lưu và phục hồi `Locale.Category.FORMAT` trong `finally`.

File `DefaultLocaleRaceDemo.java`:

```java
import java.text.NumberFormat;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class DefaultLocaleRaceDemo {
    public static void main(String[] args) throws Exception {
        Locale original =
                Locale.getDefault(Locale.Category.FORMAT);
        CountDownLatch usSet = new CountDownLatch(1);
        CountDownLatch deSet = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Locale.setDefault(
                    Locale.Category.FORMAT, Locale.US);

            Future<String> userA = pool.submit(() -> {
                Locale.setDefault(
                        Locale.Category.FORMAT, Locale.US);
                usSet.countDown();
                deSet.await();
                // Sai: factory không nhận request locale.
                return NumberFormat.getNumberInstance()
                        .format(1234.5);
            });

            Future<String> userB = pool.submit(() -> {
                usSet.await();
                Locale.setDefault(
                        Locale.Category.FORMAT, Locale.GERMANY);
                deSet.countDown();
                return "set de-DE";
            });

            System.out.println("B: " + userB.get());
            System.out.println("A: " + userA.get());
        } finally {
            Locale.setDefault(
                    Locale.Category.FORMAT, original);
            pool.shutdown();
        }
    }
}
```

```bash
javac DefaultLocaleRaceDemo.java
java DefaultLocaleRaceDemo
```

Stdout trên runtime thông dụng:

```text
B: set de-DE
A: 1.234,5
```

Thread A đã đặt `en-US`, nhưng khi tạo formatter thì default FORMAT đang là `de-DE`. Điều kiện latch làm lỗi **tái hiện được** thay vì chờ scheduling ngẫu nhiên.

**Phạm vi của việc phục hồi default:** `finally` làm sạch bản demo khi không có phần mềm nào khác cùng JVM sửa locale default. Trong chương trình thực có thread khác đồng thời thay default, ngay cả việc "lưu rồi khôi phục" cũng có thể **ghi đè cấu hình của bên khác**. Đó là lý do kiến trúc đúng là **không thay default per request**, chứ không phải thêm `try/finally` quanh mỗi yêu cầu.

## 9. `SimpleDateFormat`: vấn đề cũ trong xử lý ngày giờ

`java.text.SimpleDateFormat` kế thừa `DateFormat`, là formatter **mutable và không thread-safe**. Nó có các thành phần trạng thái như `Calendar`, `NumberFormat` và zone. Những thao tác parse/format có thể sử dụng trạng thái nội bộ trong quá trình xử lý, nên dùng một instance static chia sẻ cho các luồng có thể dẫn tới kết quả không nhất quán, exception hoặc parse sai, kể cả khi người viết không chủ động gọi setter giữa requests.

Anti-pattern:

```java
// Không dùng chung không đồng bộ:
private static final SimpleDateFormat FORMATTER =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
```

Càng nguy hiểm khi request gọi `setTimeZone(...)` trên cùng object để phục vụ nhiều zone.

### Hai hướng an toàn

**Giải pháp A — tương thích legacy:** tạo `SimpleDateFormat` mới bên trong mỗi tác vụ, truyền `Locale` tường minh và set `TimeZone` thuộc tác vụ:

```java
SimpleDateFormat format =
        new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", locale);
format.setTimeZone(TimeZone.getTimeZone(zoneId));
String text = format.format(legacyDate);
```

Đây là đoạn minh họa trong phương thức, có các biến `locale`, `zoneId` và `legacyDate`. Khi cần parse nghiêm ngặt, còn phải đặt `setLenient(false)` và kiểm tra tiêu thụ toàn bộ input.

**Giải pháp B — ưu tiên hiện đại:** dùng `java.time.Instant`, `ZoneId` và `DateTimeFormatter` immutable. Các API này có thể chia sẻ formatter base; cấu hình locale/zone của mỗi request được tạo bằng `withLocale`/`withZone`, trả instance mới. Việc đổi zone trình bày **không thay đổi Instant**.

## 10. `DateTimeFormatter` immutable: có thể chia sẻ base đúng cách

Tạo một formatter bất biến:

```java
static final DateTimeFormatter BASE =
        DateTimeFormatter.ofPattern(
                "uuuu-MM-dd HH:mm XXX", Locale.ROOT);
```

Trong mỗi request:

```java
String text = BASE.withLocale(requestLocale)
        .withZone(requestZone)
        .format(instant);
```

Không có setter nào chỉnh `BASE`; `withLocale`/`withZone` trả formatter mới (hoặc cùng instance khi không đổi). Chính vì vậy không có race trên trạng thái cấu hình formatter, miễn dữ liệu được truyền vào đúng request.

### Java 17+: kiểm chứng hai zone dưới nhiều luồng

Tạo file `ImmutableDateTimeConcurrencyDemo.java`:

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ImmutableDateTimeConcurrencyDemo {
    private static final DateTimeFormatter BASE =
            DateTimeFormatter.ofPattern(
                    "uuuu-MM-dd HH:mm XXX", Locale.ROOT);

    public static void main(String[] args) throws Exception {
        Instant time = Instant.parse(
                "2026-10-28T01:30:00Z");
        ZoneId utc = ZoneId.of("UTC");
        ZoneId tokyo = ZoneId.of("Asia/Tokyo");

        String expectedUtc = BASE.withZone(utc).format(time);
        String expectedTokyo = BASE.withZone(tokyo).format(time);

        List<Callable<Boolean>> tasks = new ArrayList<>();
        for (int i = 0; i < 1_000; i++) {
            final ZoneId zone = (i % 2 == 0) ? utc : tokyo;
            final Locale locale = (i % 2 == 0)
                    ? Locale.US : Locale.GERMANY;
            final String expected = (i % 2 == 0)
                    ? expectedUtc : expectedTokyo;

            tasks.add(() -> BASE.withLocale(locale)
                    .withZone(zone).format(time).equals(expected));
        }

        ExecutorService pool = Executors.newFixedThreadPool(8);
        int failures = 0;
        try {
            List<Future<Boolean>> results =
                    pool.invokeAll(tasks);
            for (Future<Boolean> result : results) {
                if (!result.get()) {
                    failures++;
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("UTC=" + expectedUtc);
        System.out.println("Tokyo=" + expectedTokyo);
        System.out.println("cases=1000 failures=" + failures);
    }
}
```

```bash
javac ImmutableDateTimeConcurrencyDemo.java
java ImmutableDateTimeConcurrencyDemo
```

Stdout với `DateTimeFormatter` pattern cố định:

```text
UTC=2026-10-28 01:30 Z
Tokyo=2026-10-28 10:30 +09:00
cases=1000 failures=0
```

Ví dụ cố tình dùng pattern có ký tự Latin/số cố định và `Locale.ROOT` để stdout ít phụ thuộc CLDR. Với `ofLocalizedDateTime(FormatStyle.MEDIUM)`, tên tháng, dấu câu và pattern có thể khác khi nâng JDK/CLDR; test nên so với expectation theo locale/runtime đã xác định.

**Không suy rằng mọi thứ trong hệ ngày giờ tự bất biến:** `ZoneId` là giá trị bất biến nhưng các quy tắc tzdb có thể được cập nhật giữa các bản JDK; cùng `Instant` và vùng có thể hiển thị offset lịch sử khác nếu tzdb thay đổi. Đây là vấn đề dữ liệu múi giờ, không phải race của formatter.

## 11. Kiểm thử `MessageFormat` và `Collator` khi xử lý đa ngôn ngữ

### 11.1. `MessageFormat`

`java.text.MessageFormat` có thể thay locale, pattern và các `Format` con. Không lưu một `MessageFormat` static rồi gọi `setLocale`/`applyPattern` cho nhiều request:

```java
// Không an toàn nếu request thay trạng thái dùng chung:
static final MessageFormat MESSAGE =
        new MessageFormat("{0,number}", Locale.US);
```

Ngoài race, `MessageFormat.setLocale(...)` **không tự động thay đổi mọi subformat đã được cài đặt trước đó** theo mọi pattern mong đợi. Nếu muốn message đúng locale, tạo mới từ **pattern của ResourceBundle theo locale**:

```java
ResourceBundle bundle =
        ResourceBundle.getBundle("Messages", locale);
MessageFormat message = new MessageFormat(
        bundle.getString("order.summary"), locale);
String text = message.format(new Object[] {amount, count});
```

Đây là đoạn minh họa trong phương thức; cần `Messages_<language>.properties` trên classpath và key tương ứng. Không dùng shared mutable `MessageFormat` làm global cache mà không có ownership.

### 11.2. `Collator`

`Collator` phục vụ so sánh/sắp xếp ngôn ngữ. Nó có các setter như `setStrength` và `setDecomposition`, nên không tạo một `Collator` shared rồi điều chỉnh cho từng request. Một comparator dùng `Collator` mutable cũng có thể tạo **thứ tự không ổn định** giữa lúc sort.

**Không trộn hai loại test:**

- Sorting test so thứ tự theo locale trong một phép sort với comparator có cấu hình cố định.
- Concurrency test đảm bảo request A không đổi `strength`/`locale` của comparator mà request B đang dùng.

Nếu cần cache collator, hãy xét clone/instance riêng cho thao tác theo tài liệu API của provider, và không sửa đối tượng mà nhiều thread đang sử dụng.

### 11.3. `ResourceBundle`

`ResourceBundle.getBundle(baseName, locale)` được thiết kế cho môi trường đa luồng và có caching hỗ trợ. Bản thân cache bundle không khiến bạn phải `Locale.setDefault` per request. Vấn đề thường nằm ở:

- Lấy bundle **không truyền locale**, dẫn tới default JVM.
- Lưu `ResourceBundle` của `en-US` vào field "current bundle" mutable toàn app, rồi đổi field khi request `vi-VN` đến.
- Tạo custom `ResourceBundle` subclass hoặc map value mutable không bảo đảm truy cập an toàn.
- Dùng một `MessageFormat` mutable trích từ bundle rồi share giữa threads.

Nên giữ bundle theo **locale tường minh** và lấy `getString(key)`, sau đó format thành text trong phạm vi request.

## 12. `ThreadLocal` có phải lời giải?

`ThreadLocal<SimpleDateFormat>` là cách xử lý legacy thường gặp:

```java
static final ThreadLocal<SimpleDateFormat> FORMAT =
        ThreadLocal.withInitial(() ->
                new SimpleDateFormat("yyyy-MM-dd"));
```

Nó tránh chia **cùng instance** giữa các threads. Nhưng với server dùng **thread pool**, mỗi thread được tái sử dụng cho nhiều người dùng. Nếu instance trong `ThreadLocal` được tạo theo locale/zone của request đầu tiên, request sau được điều phối lên cùng thread có thể dùng **locale cũ**. `ThreadLocal` bảo vệ ở cấp *thread*, không bảo vệ ở cấp *request*.

### Các nguy cơ khác

- Giá trị còn giữ trong thread pool khi request kết thúc; có thể gây rò memory/context.
- Một thread dùng nhiều formatter khác loại/locale; key chỉ theo thread là thiếu.
- Task bất đồng bộ có thể chuyển sang thread khác; thread-local context không tự đi theo task.
- Thiết kế xử lý exception không gọi `remove()` ở `finally` sẽ giữ state lâu hơn mong muốn.
- Thread-local không khắc phục việc gọi `Locale.setDefault` toàn JVM.

**Ưu tiên:** tạo formatter mutable trong phương thức nếu chi phí chấp nhận được; dùng formatter immutable cho java.time; chỉ áp dụng pool/cache/ThreadLocal sau khi đo hiệu năng và có test concurrency, locale switch, cancellation, cleanup.

## 13. Cache formatter: cache đúng thứ và đúng khóa

Một số chiến lược:

| Cache | Thread safety | Nhận xét |
| --- | --- | --- |
| `static NumberFormat SHARED` | **Không an toàn** nếu dùng chung không đồng bộ | Mutable, config cross-talk |
| `ConcurrentHashMap<Locale, NumberFormat>` | Map thread-safe, **formatter bên trong không tự an toàn** | Không đủ |
| `ConcurrentHashMap<Key, DateTimeFormatter>` | Có thể an toàn nếu Key immutable và đủ tham số | DateTimeFormatter immutable |
| Cache `String` pattern/locale policy | Có thể an toàn nếu dữ liệu bất biến | Tạo DecimalFormat per-call |
| Clone formatter template cho mỗi request | Có thể phù hợp tùy provider/clone semantics | Cần xác minh clone tạo bản độc lập |
| `ThreadLocal<DecimalFormat>` | Tách instance theo thread nhưng có thể sai request locale | Chỉ dùng khi có quản lý context rõ |
| Đồng bộ toàn bộ thao tác với shared formatter | Có thể tránh race nếu **mọi đọc/ghi** cùng lock | Giảm throughput, dễ thiếu lock chỗ khác |

**Cache key cần phản ánh mọi tham số ảnh hưởng output.** Ví dụ formatter ngày giờ có thể cần `Locale`, `ZoneId`, pattern/style và chronology. Formatter tiền cần locale **và** mã currency; rounding/fraction digits và numbering systems cũng là cấu hình liên quan.

### Java 17+: cache immutable `DateTimeFormatter` đúng cách

Một đoạn mã minh họa độc lập về thiết kế key:

```java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;

public class FormatterCacheDemo {
    record Key(Locale locale, ZoneId zone) {}

    private static final ConcurrentHashMap<Key, DateTimeFormatter>
            CACHE = new ConcurrentHashMap<>();

    static DateTimeFormatter get(Locale locale, ZoneId zone) {
        return CACHE.computeIfAbsent(
                new Key(locale, zone),
                key -> DateTimeFormatter
                        .ofPattern("uuuu-MM-dd HH:mm", key.locale())
                        .withZone(key.zone()));
    }

    public static void main(String[] args) {
        var a = get(Locale.US, ZoneId.of("UTC"));
        var b = get(Locale.GERMANY, ZoneId.of("UTC"));
        var c = get(Locale.US, ZoneId.of("Asia/Tokyo"));

        System.out.println("different locale key: " + (a != b));
        System.out.println("different zone key: " + (a != c));
        System.out.println("entries: " + CACHE.size());
    }
}
```

```bash
javac FormatterCacheDemo.java
java FormatterCacheDemo
```

```text
different locale key: true
different zone key: true
entries: 3
```

**Giới hạn:** ví dụ dùng một pattern cố định trong source code; nếu pattern/style có thể khác theo request, phải bổ sung vào key. Cache không có eviction có thể tăng kích thước vô hạn khi sinh locale/zone/pattern tùy input; trong production cần chính sách giới hạn và validate supported locale/zone.

Các instance cached là **immutable**, do đó có thể chia sẻ. `computeIfAbsent` bảo vệ việc chèn vào map, nhưng **không tự khiến một object mutable bên trong trở nên thread-safe**.

## 14. Chọn đúng oracle cho kiểm thử nhiều locale

Một concurrency test sai:

```java
// Sai nếu các thread đang thao tác trên formatter cùng lúc:
assertEquals("1,234.50", shared.format(amount));
```

Phép so này có thể báo lỗi khi locale/currency đổi đúng yêu cầu, hoặc pass tình cờ khi race không xảy ra. Test cần expectation theo *request context*, không theo global state hiện tại.

### Những dữ liệu test phải được mang theo mỗi task

```text
requestId
localeTag
currencyCode nếu định dạng tiền
zoneId nếu định dạng ngày giờ
domain amount/ratio/instant
pattern hoặc style, rounding và fraction digits
expected result hoặc oracle xác định độc lập
```

**Oracle có hai cấp:**

1. **Numeric/domain oracle**: `BigDecimal.compareTo`, currency code, `Instant.equals`, scale/rounding policy. Đây là điều phải đúng bất kể CLDR.
2. **Presentation oracle**: chuỗi hiển thị theo locale, dữ liệu CLDR/JDK và pattern. Khi assert literal, cố định runtime/provider hoặc dùng fixture đã được chấp thuận cho runtime ấy.

Một test tốt tạo expectation **trước khi chạy song song**, không dựa vào shared mutable formatter đang bị các luồng khác thay config. Ví dụ có thể tạo một formatter riêng cho từng locale tuần tự để tạo baseline; sau đó dùng exact per-task formatter trong pool và so kết quả với baseline. Khi so locale có trường hợp output trùng nhau về text, vẫn kiểm tra **locale/currency context đúng**, không ép mọi locale đều phải cho chuỗi khác.

## 15. Xây dựng stress test có xác suất bắt race cao hơn

Thử một lần trên máy phát triển không đủ. Ngoài test latch deterministic để tái hiện một thứ tự cụ thể, dùng stress test:

1. **Nhiều luồng:** số thread vượt số CPU hoặc giống cấu hình thread pool production.
2. **Nhiều locale/currency:** `en-US`/`de-DE`/`fr-FR`/`vi-VN`, USD/EUR/JPY/VND; zone UTC/Asia/Tokyo/Europe/Berlin khi cần.
3. **Nhiều giá trị:** zero, số âm, amount lớn, BigDecimal scale khác, tỷ lệ phần trăm, ngày có DST, text với Unicode spacing.
4. **Đồng bộ điểm bắt đầu:** có thể dùng `CountDownLatch` hoặc `CyclicBarrier` để tạo các pha cạnh tranh; không coi `Thread.sleep` là oracle.
5. **Repeat:** lặp nhiều lần trên nhiều JDK/provider/OS; gắn seed nếu sinh ngẫu nhiên và log input tối thiểu khi fail.
6. **Tách lỗi:** wrong locale symbol, wrong number, exception, parse suffix, mất precision, stale ThreadLocal, UI snapshot khác CLDR.
7. **Time-bound:** đặt timeout cho task/future để không treo CI; khi timeout/hủy phải xử lý interrupt và cleanup.
8. **Không bỏ ngoại lệ task:** `Future.get()` có thể ném `ExecutionException`; xem nguyên nhân, không chỉ đếm result false.
9. **Không chia sẻ object domain mutable:** `BigDecimal`/`Instant` bất biến tốt, nhưng nếu test dùng `Calendar`/`Date` mutable cần snapshot/ownership rõ.
10. **Không đồng bộ hóa chính đoạn code production sai** chỉ để test pass; nếu dùng lock trong oracle khác lock của system under test, lỗi vẫn có thể tồn tại.

### Tính xác định và giới hạn

- **Latch tests** chứng minh một interleaving gây lỗi logic một cách có kiểm soát; cực kỳ giá trị khi xây regression test.
- **Stress tests** tăng xác suất bắt race khác; nếu pass không thể chứng minh toàn bộ code không có race.
- **Static analysis/code review** tìm shared mutable fields và default-locale calls; hỗ trợ chứ không thay test.
- **Load test production-like** kiểm tra cả thread pools, async context propagation và framework request scope.

**Không dựa vào dòng log trông "lạ" để kết luận ngay về race**. Một thay đổi output còn có thể do CLDR, timezone database, format pattern hoặc default JVM khác giữa môi trường. Cần tái hiện với input/runtime tương đương và truy dấu state ownership.

## 16. Locale context có thể bị rò qua thread pool

Trong web server, một request tiếng Đức có thể được xử lý trên thread từng phục vụ người dùng tiếng Anh. Nếu ứng dụng giữ locale của request trong `ThreadLocal<Locale>` và quên `remove()`, tác vụ sau có thể kế thừa locale cũ.

Đây là **context leak**. Dù formatter được tạo mới, nó vẫn có thể dùng **locale sai** do context đã bị rò.

### Khuôn mẫu lifecycle

```java
try {
    REQUEST_LOCALE.set(localeFromRequest);
    // Xử lý request, tạo formatter theo locale này.
} finally {
    REQUEST_LOCALE.remove();
}
```

Đây là đoạn mã **minh họa trong một lớp có `ThreadLocal<Locale> REQUEST_LOCALE`**. Nó chỉ mô tả cleanup; không nên xem ThreadLocal là mặc định tốt nhất. **Truyền locale như đối số tường minh** qua service/presenter thường đơn giản và ít rủi ro hơn.

Khi dùng `CompletableFuture`/`ExecutorService`, task có thể chạy ở thread khác; `ThreadLocal` thông thường không tự mang context sang thread đó. Không sửa bằng cách chuyển `Locale.setDefault` toàn JVM. Hãy truyền `Locale`, `ZoneId`, `Currency` vào lambda/task như các giá trị bất biến hoặc dùng cơ chế context propagation được framework hỗ trợ và test kỹ.

## 17. Các trường hợp locale không phải lỗi thread nhưng dễ bị chẩn đoán nhầm

### 17.1. `Locale` và `Currency` độc lập

`Locale.GERMANY` không có nghĩa đơn hàng bắt buộc là EUR. Một user chọn tiếng Đức có thể thanh toán USD. Khi test, expectation cần **cả locale và currency code**. Không dựa vào `Currency.getInstance(locale)` nếu domain currency đã được lưu riêng.

### 17.2. `Locale.Category.DISPLAY` khác `FORMAT`

Thay `Locale.Category.DISPLAY` có thể ảnh hưởng tên hiển thị của language/country, còn `Category.FORMAT` thường liên quan formatting số/ngày. Phải test API đúng category. Nếu cố tạo tình huống race của `NumberFormat.getNumberInstance()` thì nên can thiệp **FORMAT**, không suy từ DISPLAY.

### 17.3. Grouping Unicode và CLDR

`fr-FR` có thể dùng **U+202F NARROW NO-BREAK SPACE**, trong khi một runtime/provider khác dùng U+00A0 hoặc cách khác. Cùng input không có race nhưng output khác sau nâng JDK. Khi test concurrency, snapshot literal nên gắn metadata runtime; kết quả domain phải được so độc lập.

### 17.4. Thay đổi timezone rules

Date/time formatting khác nhau giữa các bản tzdb cũng có thể làm snapshot fail. Không phải race nếu mọi luồng cùng zone và formatter immutable tạo cùng output trong một runtime.

### 17.5. Dùng locale mặc định trong test

CI chạy với default locale khác máy cá nhân. Test phải có `Locale` được truyền tường minh, hoặc chạy một bài test riêng kiểm soát default trong **JVM độc lập**. Một test sửa `Locale.setDefault` có thể gây ảnh hưởng test khác chạy parallel trên cùng JVM ngay cả khi test đó có `finally`.

## 18. Một bài test hoàn chỉnh: request context và formatter per-call

Cách thiết kế thực tế là đóng gói dữ liệu không đổi vào một record:

```java
record DisplayContext(Locale locale, Currency currency) {}
```

Sau đó mỗi task nhận context cố định. Mọi formatter mutable được tạo bên trong task; không có biến static mutable đóng vai trò "locale hiện tại".

Tạo file `RequestScopedFormattingDemo.java`:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.ArrayList;
import java.util.Currency;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RequestScopedFormattingDemo {
    record Context(Locale locale, Currency currency) {}

    static String render(BigDecimal amount, Context context) {
        NumberFormat formatter =
                NumberFormat.getCurrencyInstance(context.locale());
        formatter.setCurrency(context.currency());
        return formatter.format(amount);
    }

    public static void main(String[] args) throws Exception {
        BigDecimal amount = new BigDecimal("1234.50");
        Context us = new Context(
                Locale.US, Currency.getInstance("USD"));
        Context de = new Context(
                Locale.GERMANY, Currency.getInstance("EUR"));

        String expectedUs = render(amount, us);
        String expectedDe = render(amount, de);

        List<Callable<Boolean>> tasks = new ArrayList<>();
        for (int i = 0; i < 1_000; i++) {
            final Context context = (i % 2 == 0) ? us : de;
            final String expected = (i % 2 == 0)
                    ? expectedUs : expectedDe;
            tasks.add(() -> render(amount, context).equals(expected));
        }

        ExecutorService pool = Executors.newFixedThreadPool(8);
        int failures = 0;
        try {
            List<Future<Boolean>> results = pool.invokeAll(tasks);
            for (Future<Boolean> future : results) {
                if (!future.get()) {
                    failures++;
                }
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("cases=1000");
        System.out.println("failures=" + failures);
        System.out.println("context unchanged="
                + (us.currency().getCurrencyCode().equals("USD")
                && de.currency().getCurrencyCode().equals("EUR")));
    }
}
```

```bash
javac -encoding UTF-8 RequestScopedFormattingDemo.java
java RequestScopedFormattingDemo
```

```text
cases=1000
failures=0
context unchanged=true
```

Ở đây exact rendering expectation được tính **tuần tự bằng formatter riêng** trước khi bắt đầu 1.000 tasks. Điều đó khiến bài test ổn định hơn việc hardcode ký hiệu/khoảng trắng của một JDK cụ thể. Nó phát hiện output khác baseline trong một runtime, nhưng không thay thế test **currency identity** hoặc test hiển thị nhiều locale có kết quả trùng nhau.

Dùng record `Context` không phải để tránh mọi vấn đề concurrency thần kỳ; nó làm cho việc truyền phụ thuộc theo request trở nên **tường minh**. Các thành phần `Locale`/`Currency`/`BigDecimal` vốn là immutable value objects.

## 19. Kiểm thử parse khi các formatter có locale khác nhau

Cùng `"1,234"` có thể mang nghĩa khác nhau:

- `en-US`: thường là một nghìn hai trăm ba mươi tư.
- `de-DE`: thường là một phẩy hai ba bốn.

Hai parser đều có thể đọc **hết chuỗi**, nhưng tạo **hai giá trị khác nhau**. Vì thế kiểm tra `ParsePosition.getIndex()==input.length()` tuy cần để từ chối suffix vẫn **không phát hiện việc dùng nhầm locale** khi input tình cờ hợp lệ cho cả hai locale.

### Một parser an toàn về ownership

```java
static BigDecimal parseDecimal(String raw, Locale locale) {
    NumberFormat base = NumberFormat.getNumberInstance(locale);
    if (!(base instanceof DecimalFormat format)) {
        throw new IllegalStateException("DecimalFormat required");
    }
    format.setParseBigDecimal(true);
    ParsePosition pos = new ParsePosition(0);
    Number parsed = format.parse(raw, pos);

    if (!(parsed instanceof BigDecimal decimal)
            || pos.getIndex() != raw.length()) {
        throw new IllegalArgumentException("Invalid input");
    }
    return decimal;
}
```

Đây là phương thức minh họa trong lớp có các import `BigDecimal`, `NumberFormat`, `DecimalFormat`, `ParsePosition` và `Locale`. Mỗi lần parse tạo formatter riêng nên an toàn với những request gọi đồng thời. Nhưng **full consumption không đồng nghĩa strict grouping**: `DecimalFormat` có thể cho phép dấu nhóm ở vị trí không chuẩn. Nếu parser phục vụ tiền hoặc schema nghiêm, cần thêm lexical/domain validation.

### Những test quan trọng

| Input | Locale nguồn | Giá trị mong đợi | Nhận định |
| --- | --- | --- | --- |
| `"1,234"` | en-US | `1234` | Phải truyền locale nguồn |
| `"1,234"` | de-DE | `1.234` | Cùng text, giá trị khác |
| `"1.234,50"` | de-DE | `1234.50` | Không được parse bằng locale US |
| `"1,234.50oops"` | en-US | REJECT | Kiểm tra full input |
| `"12,34.50"` | en-US | Tùy lexical policy | Full parse chưa đủ |
| `"NaN"` | en-US | REJECT nếu domain là Money | Có thể trả `Double` đặc biệt |
| Số `fr-FR` dùng U+202F | fr-FR | Đúng giá trị số | Kiểm tra Unicode space |
| Amount USD hiển thị de-DE | de-DE + USD | Numeric amount đúng, currency USD | Không suy currency từ locale |

**Lỗi khi concurrency và locale mismatch có thể trông giống nhau:** nếu một request de-DE bị cấp parser en-US do cache sai, `ParsePosition` có thể dừng sớm hoặc cũng có thể parse thành số hoàn chỉnh nhưng sai ý nghĩa. Test phải xác minh **cả source locale lẫn numeric result**.

## 20. Ma trận kiểm thử chuyên sâu

| Nhóm | Tình huống test | Điều phải khẳng định |
| --- | --- | --- |
| Shared formatter | A set USD, B set EUR, A format | Reproduce lỗi của anti-pattern |
| Per-request formatter | 1.000–10.000 tasks khác locale | Không mismatch về value/context |
| Global default race | A set en-US, B set de-DE | Overload không locale bị can thiệp |
| Immutable date formatter | Shared BASE + `withLocale`/`withZone` | Không ảnh hưởng task khác |
| `SimpleDateFormat` legacy | Tạo riêng hoặc dùng synchronized access | Không share mutable |
| `MessageFormat` | Hai locale, pattern/placeholders khác | Không rò nội dung/ngữ pháp |
| `Collator` | Hai strength và locale khi sort | Không mutate comparator đang dùng |
| `ThreadLocal` | Hai request khác locale cùng pool thread | Không dùng stale locale |
| Async task | Locale truyền theo task thay vì đọc thread-local | Context không bị mất |
| Currency | USD/EUR/JPY, same locale và khác locale | Mã currency và amount bất biến |
| Number parsing | Input cùng text ở en-US/de-DE | Result đúng source locale |
| Percent | Ratio 0.125 in 12.5% | Không nhân/chia 100 hai lần |
| Date/time | UTC/Tokyo, ngày DST | Instant bất biến, zone đúng |
| Unicode spaces | fr-FR, các dấu nhóm U+202F/U+00A0 | Không so ký tự bằng mắt |
| JDK/CLDR upgrade | Cùng task cùng locale khác runtime | Phân loại presentation diff |
| Error handling | Future throws/timeout/interruption | Không bỏ lỗi test |
| Cleanup | Shutdown executor, clear ThreadLocal | Không giữ state sau request |
| Performance | Có/không cache formatter | Tối ưu sau khi đã đạt correctness |

Nên đặt test race điều phối được trong CI; stress tests có thể chạy thêm các lần lặp, cấu hình worker count và runtime khác nhau. Nếu dùng unit framework, mỗi test phải cô lập state toàn JVM. Những bài test cố ý sửa `Locale.setDefault` nên chạy trong **forked JVM riêng** hoặc được serialize tuyệt đối với các test phụ thuộc locale default.

## 21. Cách ghi nhận lỗi khi test thất bại

Với dữ liệu giả lập không nhạy cảm, log các thông tin:

```text
testCaseId
threadName / taskId
request localeTag, currencyCode, zoneId
formatter type / intended configuration
domain input (anonymized fixture)
expected output / actual output
actual Unicode code points
parse consumed index + error index nếu có
Java runtime/version, locale provider
worker exception/timeout/interrupt status
```

**Không log bí mật người dùng hoặc dữ liệu giao dịch thật** chỉ để debug localization. Khi output khác vì Unicode space, in code points bằng `String.codePoints()` thay vì nhìn chuỗi:

```java
static String points(String text) {
    return text.codePoints()
            .mapToObj(cp -> String.format(
                    Locale.ROOT, "U+%04X", cp))
            .toList().toString();
}
```

Đây là đoạn minh họa; cần import `java.util.Locale`. Nó làm rõ `U+0020`, `U+00A0` và `U+202F` nếu formatter hoặc CLDR đổi ký tự khoảng trắng.

## 22. Những lỗi phổ biến và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `static final DecimalFormat` chung | `final` không bảo vệ state mutable | Tạo per-call hoặc đồng bộ trọn thao tác |
| Dùng `ConcurrentHashMap<Locale, NumberFormat>` | Map an toàn, formatter vẫn không an toàn | Cache immutable config hoặc instance riêng |
| A setCurrency rồi format trên shared object | B đổi currency làm A nhận ký hiệu sai | Currency từ domain + formatter per request |
| `SimpleDateFormat` static | Parse/format không ổn định đa luồng | `DateTimeFormatter` immutable |
| `Locale.setDefault` theo request | Locale global bị cross-talk | Truyền locale tường minh |
| Dùng `Locale.getDefault()` trong parser mọi người dùng | Nguồn input có locale khác server | Input locale theo request |
| Dùng `ThreadLocal` không reset | Thread pool leak/stale locale | `finally/remove` hoặc bỏ ThreadLocal |
| Dùng `ThreadLocal` để chuyển async context | Task khác thread mất context | Truyền values vào task |
| Cache key chỉ có pattern, bỏ locale | Formatting sai dù cache thread-safe | Key chứa đủ Locale/Zone/pattern |
| Cache `DateTimeFormatter` nhưng input chưa validate | Bùng số entry do locale/zone tùy ý | Validate và giới hạn cache |
| Race test chỉ dùng `Thread.sleep` | Flaky và khó tái hiện | CountDownLatch/CyclicBarrier |
| Test pass một lần thì kết luận an toàn | Không bao phủ mọi lịch chạy | Deterministic interleaving + stress |
| Xét chuỗi theo một locale duy nhất | Bỏ lỗi khác dấu và chữ số | Matrix multi-locale |
| Hardcode symbol/space mọi JDK | CLDR upgrade làm test fail giả | Runtime metadata và domain invariants |
| So chuỗi khi domain là số | Không xác định đúng nghiệp vụ | `BigDecimal`/currency code |
| Không gọi `Future.get()` | Bỏ exception trong worker | Collect mọi futures, assert/propagate |
| Không `shutdown()` executor | Thread không kết thúc, leak | `finally/shutdown`, timeout nếu cần |
| Coi full parse là đúng locale | Cùng input có thể thành hai số | Test source locale và numeric value |

## 23. Câu hỏi tự kiểm tra

1. **Vì sao `static final NumberFormat` không tự an toàn?** `final` cố định tham chiếu, không làm formatter mutable thành immutable.
2. **Một thread A set USD, B set EUR, A format có thể xảy ra lỗi gì?** A hiển thị ký hiệu EUR dù domain currency là USD.
3. **Vì sao ví dụ `CountDownLatch` tốt hơn `Thread.sleep`?** Nó tạo thứ tự xen kẽ cụ thể, tái hiện được lỗi logic.
4. **`Locale` có immutable không?** Có. Nhưng formatter được tạo bằng locale có thể vẫn mutable.
5. **`Locale.setDefault` có áp dụng riêng cho request hiện tại không?** Không; thay default toàn JVM.
6. **`NumberFormat.getNumberInstance()` không đối số dùng locale nào?** Default FORMAT phù hợp của JVM.
7. **Nếu dùng `NumberFormat.getNumberInstance(locale)` cho từng task thì tránh được điều gì?** Giảm phụ thuộc default locale và chia sẻ cấu hình mutable.
8. **`DateTimeFormatter.withLocale` có sửa formatter gốc không?** Không; trả formatter immutable được cấu hình.
9. **`SimpleDateFormat` có an toàn để dùng chung qua nhiều threads không?** Không nếu không đồng bộ thích hợp.
10. **`ConcurrentHashMap<Locale, DecimalFormat>` đủ để bảo vệ format không?** Không; nó chỉ bảo vệ cấu trúc map.
11. **`ThreadLocal` có đảm bảo locale đúng cho request sau trên cùng thread không?** Không nếu stale state hoặc cache bỏ ngữ cảnh.
12. **Tại sao `Future.get()` quan trọng trong stress test?** Để quan sát kết quả và exception thay vì bỏ lỗi bên trong worker.
13. **`ResourceBundle` dùng trong nhiều luồng có bắt buộc setDefault không?** Không; lấy bundle bằng locale tường minh.
14. **`MessageFormat` có thể dùng một instance static rồi gọi `setLocale` từng request không?** Không nên; có mutable state và format con.
15. **Hai luồng tạo `DateTimeFormatter` từ shared immutable BASE có an toàn không?** Có nếu dùng immutable methods và context đúng.
16. **Vì sao cùng `"1,234"` ở en-US/de-DE nguy hiểm?** Có thể parse hết nhưng cho hai giá trị khác nhau.
17. **Stress test pass 1.000 tác vụ có chứng minh mọi race đã biến mất không?** Không; chỉ xác minh những tình huống và lịch chạy đã thực hiện.
18. **Vì sao dùng snapshot literal số Pháp có thể flake sau nâng JDK?** CLDR có thể thay grouping space U+202F/U+00A0.
19. **Nên làm gì khi locale của request được truyền sang `CompletableFuture`?** Capture/truyền đối số bất biến, không phụ thuộc ThreadLocal tự lan truyền.
20. **Khi nào cache immutable formatter nên có key Locale và ZoneId?** Khi hai thuộc tính này ảnh hưởng output; thêm mọi pattern/style liên quan.
21. **Nếu format date time khác do tzdb update, đó có chắc là race không?** Không; phải đối chiếu runtime/rules.
22. **Điều gì phải bất biến dù request chạy song song và đổi locale?** Số tiền domain, currency code, ratio, Instant, trạng thái và tính đúng use case.
23. **Tại sao lock chỉ quanh `format` chưa chắc đủ?** Nếu setter cấu hình nằm ngoài cùng lock, thread khác vẫn có thể can thiệp giữa setter và format.
24. **Khi nào cần kiểm thử riêng `Locale.Category.DISPLAY`?** Khi code hiển thị tên ngôn ngữ/vùng, khác phạm vi number/date FORMAT.

## 24. Checklist trước khi triển khai

- [ ] Xác định tất cả formatter mutable dưới dạng static field, singleton hoặc cache.
- [ ] Không có request nào gọi `Locale.setDefault` hay `TimeZone.setDefault` để đổi ngữ cảnh người dùng.
- [ ] Mọi formatter số/tiền nhận `Locale` tường minh và currency code từ domain.
- [ ] Legacy formatter mutable được tạo per operation, hoặc toàn bộ chuỗi set/format/parse nằm trong synchronization đúng.
- [ ] Với ngày giờ mới, ưu tiên `DateTimeFormatter` và các kiểu `java.time` immutable.
- [ ] `MessageFormat` và `Collator` không bị thay cấu hình khi đang được các task dùng chung.
- [ ] Không cache mutable object chỉ bằng `ConcurrentHashMap` rồi nghĩ là đã thread-safe.
- [ ] Nếu cache immutable formatter, key gồm locale/zone/pattern/style và có giới hạn vòng đời phù hợp.
- [ ] `ThreadLocal` có cleanup và được kiểm tra với thread pool/async tasks, hoặc được loại bỏ khi không cần.
- [ ] Stress test chạy nhiều locale/currency/zone, nhiều luồng, nhiều giá trị và quan sát `Future.get()`.
- [ ] Có ít nhất một deterministic interleaving test cho anti-pattern đã từng gây lỗi.
- [ ] Không dùng `Thread.sleep` đơn độc làm cơ chế kiểm thử thứ tự.
- [ ] Test phân biệt domain numeric/instant invariants và output presentation theo CLDR.
- [ ] Input parser kiểm tra full consumption, đúng source locale, strict grammar/domain khi cần.
- [ ] Test thay default locale được chạy trong JVM cô lập, tránh ảnh hưởng test khác.
- [ ] Test CI ghi JDK/provider/locale và Unicode code points khi xuất hiện output khác.
- [ ] Executor/tài nguyên được dọn trong `finally`; timeout và interrupt được xử lý đúng policy.

## Tài liệu tham khảo

- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): cảnh báo number formats không synchronized, locale-specific factory và parsing.
- [Java SE 17 — DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): cấu hình mutable, pattern, symbols và rounding.
- [Java SE 17 — SimpleDateFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/SimpleDateFormat.html): synchronization và xử lý ngày giờ legacy.
- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): pattern, locale, subformat và tính mutable.
- [Java SE 17 — Collator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html): mutable collation strength/decomposition.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html): immutable, thread-safe formatting theo locale/zone.
- [Java SE 17 — Locale](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): `setDefault`, `getDefault` và `Locale.Category.FORMAT`/`DISPLAY`.
- [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): cơ chế bundle/cache và locale-specific lookup.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): điều phối thứ tự các luồng trong kiểm thử.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit/invokeAll/shutdown.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): lifetime, set/get/remove, thread-pool context.
- [Unicode CLDR](https://cldr.unicode.org/): nguồn locale data, Unicode number/date/currency patterns được cập nhật theo phiên bản.
