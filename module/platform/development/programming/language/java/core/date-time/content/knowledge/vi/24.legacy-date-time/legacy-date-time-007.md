# SimpleDateFormat không an toàn khi dùng chung giữa nhiều luồng

## 1. Một mẫu cố định không làm đối tượng định dạng trở thành bất biến

Một tối ưu thường gặp trong mã cũ là tạo một `SimpleDateFormat` dùng chung để tránh khởi tạo nhiều lần:

```java
private static final SimpleDateFormat FORMAT =
        new SimpleDateFormat("yyyy-MM-dd", Locale.ROOT);
```

Đây là khai báo minh họa một đối tượng có thể bị dùng chung; bản thân dòng khai báo chưa nói nơi gọi đã đồng bộ hay chưa. Nếu nhiều luồng gọi `FORMAT.format(...)` hoặc `FORMAT.parse(...)` đồng thời mà không có bảo vệ, cách dùng đó **không an toàn**.

`final` chỉ giữ tham chiếu, không làm trạng thái bên trong `SimpleDateFormat` bất biến. Dù pattern không đổi và đầu vào mỗi luồng khác nhau, thao tác định dạng/phân tích vẫn có thể sử dụng trạng thái làm việc bên trong đối tượng.

Trong một ứng dụng xử lý nhiều yêu cầu, lỗi có thể hiếm gặp, chỉ xuất hiện dưới tải hoặc thay đổi giữa các lần chạy. Không thấy lỗi khi chạy đơn luồng không chứng minh một formatter dùng chung đã an toàn.

## 2. Vì sao format và parse có thể tranh chấp trạng thái?

`SimpleDateFormat` không chỉ giữ một chuỗi pattern. Nó còn gắn với các đối tượng và trạng thái dùng trong việc diễn giải các trường lịch và số, như `Calendar`, `NumberFormat` cùng cấu hình locale/múi giờ.

Khi một luồng đang xử lý đầu vào A và luồng khác dùng cùng đối tượng cho B, các bước đọc/ghi trạng thái có thể xen kẽ. Kết quả quan sát được có thể là chuỗi/ngày sai hoặc ngoại lệ xuất hiện bất thường. Biểu hiện cụ thể phụ thuộc lịch chạy của luồng và dữ liệu; không có một stdout hay stack trace cố định cho mọi lần chạy.

Hai điều dễ bỏ sót:

- **Chỉ gọi format vẫn cần quan tâm an toàn luồng.** Nó không trở thành thao tác thuần chỉ vì không mang tên setter.
- **Cấu hình lại formatter còn là thao tác thay đổi trạng thái.** `setTimeZone`, `applyPattern`, `setLenient` hoặc việc để tham chiếu nội bộ lọt ra ngoài có thể làm những lời gọi sau chạy theo cấu hình khác.

Đặt tham chiếu trong `volatile`, một `ConcurrentHashMap` hoặc một lớp bao có tên “thread safe” không tự bảo vệ các thao tác bên trong đối tượng được chứa. Cần chọn chính sách sử dụng formatter cụ thể.

## 3. Những cách xử lý phù hợp

| Cách làm | Cơ chế | Điều cần giữ rõ |
|---|---|---|
| Dùng `DateTimeFormatter` | Đối tượng bất biến, an toàn khi dùng chung | Chuyển đúng pattern, kiểu dữ liệu và chính sách parsing |
| Tạo `SimpleDateFormat` cho từng lần gọi | Mỗi lần xử lý có đối tượng riêng | Cấu hình đầy đủ locale, múi giờ, leniency |
| Một formatter riêng cho mỗi luồng | Không để các luồng cùng dùng một instance | Quản lý vòng đời và cấu hình theo ngữ cảnh |
| Đồng bộ một formatter dùng chung | Không cho các thao tác liên quan chạy đồng thời | Mọi đường truy cập phải dùng cùng một khóa |

Với mã mới, `DateTimeFormatter` thường diễn tả hợp đồng rõ và cho phép chia sẻ thuận tiện. Khi phải giữ API legacy, tạo riêng theo lần gọi hoặc đồng bộ là những phương án có thể kiểm tra trực tiếp.

Không chọn chỉ dựa trên cảm giác rằng khởi tạo formatter chắc chắn là nút thắt. Nếu hiệu năng là vấn đề thực tế, đo trong ngữ cảnh sử dụng rồi cân nhắc chi phí cấp phát, tranh chấp khóa và độ phức tạp cấu hình.

## 4. Tạo riêng hoặc khóa chung phải bao phủ đúng phạm vi

### Tạo mới trong phương thức

Một hàm tạo formatter cục bộ có thể cấu hình ngay từ đầu:

```java
SimpleDateFormat format = new SimpleDateFormat(pattern, Locale.ROOT);
format.setTimeZone(TimeZone.getTimeZone("UTC"));
format.setLenient(false);
```

Đây là cấu hình minh họa với biến `pattern`. Đối tượng chỉ được một lời gọi sở hữu nên không có tranh chấp formatter giữa các luồng.

Không tạo cục bộ một lần rồi đưa nó vào cache toàn cục sau đó mà vẫn gọi cách dùng ấy là “mỗi lần một đối tượng”. Ranh giới chia sẻ thực sự nằm ở nơi các tham chiếu được lưu và dùng.

### Đồng bộ formatter dùng chung

Nếu giữ một instance riêng tư, có thể dùng một khóa riêng:

```java
synchronized (LOCK) {
    return SHARED.format(date);
}
```

Mọi lời gọi `format`, `parse` và mọi thay đổi cấu hình của cùng instance phải tuân theo **cùng khóa**. Chỉ khóa phần tạo đối tượng, chỉ khóa một phía parse hoặc dùng hai khóa khác nhau không loại bỏ tranh chấp.

Giữ formatter riêng tư để nơi khác không gọi vòng qua khóa. Nếu thao tác của chức năng gồm đổi múi giờ theo yêu cầu rồi định dạng, toàn bộ chuỗi thay cấu hình + dùng cấu hình phải được bảo vệ như một thao tác nhất quán; tốt hơn có thể tránh đổi cấu hình dùng chung theo từng người dùng.

Khóa formatter cũng không tự bảo vệ một `Date` đầu vào đang bị luồng khác sửa. Dữ liệu và formatter là hai nguồn trạng thái khác nhau; trong ví dụ đầy đủ, đầu vào là `Instant` bất biến và Date chỉ được tạo cục bộ khi cần.

### Mỗi luồng một đối tượng

`ThreadLocal<SimpleDateFormat>` là một cách legacy có thể dùng để tách instance theo luồng. Tuy nhiên, luồng trong pool có thể sống lâu hơn một yêu cầu và xử lý nhiều người dùng. Không để múi giờ/pattern của yêu cầu trước lưu lại rồi ảnh hưởng yêu cầu sau.

Cần chính sách vòng đời rõ ràng; khi giá trị chỉ thuộc một tác vụ và không muốn giữ lại trong pool, có thể dọn bằng `remove()` trong `finally`. Với thiết kế tạo rất nhiều luồng hoặc yêu cầu cấu hình thay đổi, so sánh độ đơn giản của tạo cục bộ hoặc dùng `DateTimeFormatter` trước khi thêm trạng thái gắn với luồng.

## 5. Chuyển sang DateTimeFormatter không chỉ thay tên lớp

Một bộ định dạng hiện đại có thể giữ làm hằng dùng chung:

```java
private static final DateTimeFormatter FORMAT = DateTimeFormatter
        .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS", Locale.ROOT)
        .withResolverStyle(ResolverStyle.STRICT)
        .withZone(ZoneOffset.UTC);
```

`withZone`, `withLocale`, `withResolverStyle` trả về bộ định dạng mới; chúng không sửa hằng gốc. Đặc điểm này giúp không có cấu hình làm việc dùng chung bị thay đổi trong những lời gọi định dạng thông thường.

Tuy nhiên, ký hiệu pattern không trùng hoàn toàn với `SimpleDateFormat`. Ví dụ, `u` ở `SimpleDateFormat` là số thứ trong tuần, còn ở `DateTimeFormatter` là năm kéo dài. Với kiểm tra ngày ISO nghiêm ngặt trong mã mới, thường dùng `uuuu`, không sao chép máy móc `yyyy` rồi bỏ qua ý nghĩa năm trong kỷ nguyên.

Cần kiểm tra thêm:

- Độ chính xác phần giây và kiểu dữ liệu đầu vào/đầu ra.
- Múi giờ dùng khi một chuỗi không tự chứa offset.
- Tên tháng/ngôn ngữ theo locale.
- Các ngày không tồn tại có bị từ chối hay chuẩn hóa.
- Có bắt buộc đọc hết chuỗi không.

An toàn luồng chỉ là một thuộc tính. Một formatter an toàn nhưng chọn sai múi giờ vẫn tạo dữ liệu sai nghĩa.

## 6. Không lấy một lần thử tải làm bằng chứng về hợp đồng

Có thể viết thử nhiều luồng cùng dùng SimpleDateFormat không khóa để quan sát lỗi, nhưng không nên cam kết rằng một lần chạy chắc chắn thất bại hoặc có một thông điệp lỗi cụ thể.

Nếu phép thử không tạo lỗi, nó chỉ nói lịch chạy lần ấy chưa làm lộ vấn đề. Nếu nó tạo lỗi, đó là bằng chứng quan sát hữu ích nhưng không phải toàn bộ mô tả về mọi khả năng sai.

Chương trình bên dưới chủ động kiểm tra **ba cách dùng an toàn** với đầu vào xác định. Nó chờ kết quả từng tác vụ bằng `Future.get()` để lỗi trong worker không bị bỏ qua. Các chuỗi mong đợi được viết tường minh, không chỉ format rồi parse lại và mặc định hai lỗi có thể không bù nhau.

## 7. Chương trình chạy đầy đủ

Lưu mã sau vào `FormatterConcurrencyDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Mỗi phương án chạy 24 tác vụ, mỗi tác vụ kiểm tra 100 vòng định dạng và đọc lại.

```java
import java.text.ParseException;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FormatterConcurrencyDemo {
    private static final String LEGACY_PATTERN =
            "yyyy-MM-dd'T'HH:mm:ss.SSS";
    private static final DateTimeFormatter MODERN = DateTimeFormatter
            .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS", Locale.ROOT)
            .withResolverStyle(ResolverStyle.STRICT)
            .withZone(ZoneOffset.UTC);
    private static final Object LOCK = new Object();
    private static final SimpleDateFormat SHARED_LEGACY = newLegacyFormatter();

    interface Codec {
        String format(Instant value);
        Instant parse(String text) throws ParseException;
    }

    private static SimpleDateFormat newLegacyFormatter() {
        SimpleDateFormat format =
                new SimpleDateFormat(LEGACY_PATTERN, Locale.ROOT);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        format.setLenient(false);
        return format;
    }

    private static Instant parseFully(SimpleDateFormat format, String text)
            throws ParseException {
        ParsePosition position = new ParsePosition(0);
        Date parsed = format.parse(text, position);
        if (parsed == null || position.getIndex() != text.length()) {
            int index = position.getErrorIndex() >= 0
                    ? position.getErrorIndex() : position.getIndex();
            throw new ParseException("invalid timestamp", index);
        }
        return parsed.toInstant();
    }

    public static void main(String[] args) throws Exception {
        Codec modern = new Codec() {
            public String format(Instant value) {
                return MODERN.format(value);
            }
            public Instant parse(String text) {
                return LocalDateTime.parse(text, MODERN)
                        .toInstant(ZoneOffset.UTC);
            }
        };

        Codec perCall = new Codec() {
            public String format(Instant value) {
                return newLegacyFormatter().format(Date.from(value));
            }
            public Instant parse(String text) throws ParseException {
                return parseFully(newLegacyFormatter(), text);
            }
        };

        Codec locked = new Codec() {
            public String format(Instant value) {
                synchronized (LOCK) {
                    return SHARED_LEGACY.format(Date.from(value));
                }
            }
            public Instant parse(String text) throws ParseException {
                synchronized (LOCK) {
                    return parseFully(SHARED_LEGACY, text);
                }
            }
        };

        check("modern", modern);
        check("perCall", perCall);
        check("locked", locked);
    }

    private static void check(String label, Codec codec) throws Exception {
        Instant[] values = {
                Instant.parse("2026-10-25T10:20:30.123Z"),
                Instant.parse("2000-01-02T03:04:05.456Z")
        };
        String[] expected = {
                "2026-10-25T10:20:30.123",
                "2000-01-02T03:04:05.456"
        };
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            List<Callable<Void>> tasks = new ArrayList<>();
            for (int task = 0; task < 24; task++) {
                int index = task % values.length;
                tasks.add(() -> {
                    for (int repeat = 0; repeat < 100; repeat++) {
                        String text = codec.format(values[index]);
                        if (!expected[index].equals(text)
                                || !values[index].equals(codec.parse(text))) {
                            throw new AssertionError("wrong value: " + label);
                        }
                    }
                    return null;
                });
            }
            for (Future<Void> future : pool.invokeAll(tasks)) {
                future.get();
            }
            System.out.println(label + "=PASS");
        } finally {
            pool.shutdown();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac FormatterConcurrencyDemo.java
java FormatterConcurrencyDemo
```

Kết quả chuẩn khi mọi phép kiểm tra qua:

```text
modern=PASS
perCall=PASS
locked=PASS
```

Nếu chuỗi hoặc thời điểm sai, tác vụ ném `AssertionError`; `Future.get()` truyền thất bại về luồng chính. Chương trình không chỉ in “đã chạy” rồi coi đó là xác nhận dữ liệu đúng.

`parseFully` dùng `ParsePosition` để kiểm tra cả hai điều kiện: có tạo được Date và đã đọc hết chuỗi. `setLenient(false)` kiểm tra giá trị lịch, nhưng không tự thay cho việc xác nhận toàn bộ chuỗi đã được tiêu thụ trong API parsing legacy.

Các đầu vào đều có phần lẻ mili giây, phù hợp với Date/SimpleDateFormat trong ví dụ. Không suy ra rằng một vòng qua Date có thể bảo toàn mọi phần nano giây của Instant.

Chuỗi không có hậu tố offset; hợp đồng ví dụ xác định nó là giờ UTC. `newLegacyFormatter` và `MODERN` đều được cấu hình theo quyết định đó. Nếu dữ liệu thực cần tự mang offset, cần pattern và kiểu parsing tương ứng, không chỉ thêm một chữ `Z` nguyên văn vào chuỗi.

## 8. Những kết luận đúng mức từ ví dụ

- `modern` dựa trên hợp đồng bất biến/an toàn luồng của DateTimeFormatter, không phải chỉ nhờ số vòng thử hiện tại.
- `perCall` không chia sẻ đối tượng SimpleDateFormat, nên các tác vụ không tranh chấp trạng thái formatter.
- `locked` giữ một instance nhưng tuần tự hóa các thao tác qua cùng khóa riêng tư.
- Kết quả PASS của ví dụ không chứng minh mọi wrapper hoặc mọi cách cấu hình SimpleDateFormat khác đều an toàn.
- Đồng bộ một formatter không làm mọi thành phần khác trong ứng dụng an toàn luồng; dữ liệu đầu vào có thể sửa, formatter khác hoặc lớp cấu hình vẫn cần hợp đồng riêng.

Cũng không cần suy ra phương án nào nhanh nhất từ thời gian một lần chạy của chương trình này. Đây là minh chứng tính đúng cho các cấu trúc được chọn, không phải một benchmark.

## 9. Tự thực hành

1. Thêm một đầu vào thứ ba có ngày/tháng/năm khác xa hai đầu vào cũ, cùng chuỗi mong đợi. Xác nhận cả ba phương án vẫn giữ dữ liệu riêng của từng tác vụ.
2. Trong một bản thử nghiệm riêng, bỏ khóa ở một đường parse hoặc format của phương án `locked`. Giải thích vì sao cấu trúc không còn bảo đảm an toàn, ngay cả khi một lần chạy vẫn in PASS. Không đưa biến thể ấy vào mã dùng thật.
3. Thêm trường hợp chuỗi có phần dư ở cuối để kiểm tra `parseFully` từ chối. Phân biệt đây là kiểm tra hợp đồng parsing với kiểm tra tranh chấp luồng.
4. Nếu chọn ThreadLocal trong một ứng dụng legacy, viết rõ ai tạo cấu hình, có thay đổi theo người dùng không và khi nào dữ liệu gắn luồng được dọn. Đánh giá liệu tạo cục bộ có làm hợp đồng đơn giản hơn không.

Tham khảo: [SimpleDateFormat — synchronization](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/SimpleDateFormat.html) và [DateTimeFormatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/format/DateTimeFormatter.html) trong Java SE 21.
