# Kiểm thử rotation trong Java logging: xoay file, retention và khôi phục

## 1. Rotation là gì và tại sao phải kiểm thử?

**Log rotation** là cơ chế chuyển từ file log đang ghi sang một file/thế hệ mới khi đạt một **điều kiện kích hoạt**: dung lượng, khoảng thời gian, hoặc một chính sách kết hợp. Những file cũ có thể được giữ, nén, chuyển đi hoặc xóa theo retention policy.

Ví dụ:

```text
Ứng dụng Java
    |
    v
Rolling appender / FileHandler
    |
    +--> logs/app.log                   (đang ghi)
    +--> logs/archive/app.2026-11-10.0.log.gz
    +--> logs/archive/app.2026-11-10.1.log.gz
    +--> logs/archive/app.2026-11-09.0.log.gz
    |
    v
Collector / shipper -> centralized logging
```

**Kiểm thử rotation** không chỉ xác nhận “có file mới được tạo”. Một hệ thống có thể tạo file đúng tên nhưng vẫn gặp các vấn đề nghiêm trọng:

- Ghi thiếu, trùng hoặc đảo trật tự bản ghi khi chuyển file.
- Cắt một log event/stack trace ở vị trí không hợp lý.
- Giữ quá nhiều thế hệ làm đầy disk, hoặc xóa bản ghi quá sớm.
- Việc nén/chuyển file lỗi nhưng appender vẫn báo bình thường.
- Sau restart, appender ghi đè file cũ hoặc không tiếp tục từ trạng thái đúng.
- Nhiều process cùng ghi một đường dẫn dẫn đến lock, đụng tên hoặc file hỏng.
- Gặp thiếu quyền ghi, đầy ổ đĩa, rename thất bại mà ứng dụng không được giám sát.
- Collector bám theo tên file thay vì file identity nên bỏ sót hoặc đọc trùng dữ liệu.

Vì vậy, một bài test tốt phải kiểm tra **trigger, file lifecycle, tính toàn vẹn bản ghi, retention, sự cố và khả năng quan sát**, chứ không chỉ nhìn thấy hậu tố `.1` hay `.gz`.

## 2. Phân biệt rotation và những cơ chế dễ nhầm

| Khái niệm | Hành vi | Điều phải kiểm tra |
| --- | --- | --- |
| **Size-based rotation** | Đổi file khi đạt ngưỡng kích thước | Ngưỡng, thế hệ, burst, bản ghi dài |
| **Time-based rotation** | Đổi file theo ngày/giờ/chu kỳ | Ranh giới thời gian, timezone, DST, idle period |
| **Size-and-time rotation** | Trong một khoảng thời gian, có thể tạo nhiều file theo index | Cả period và chỉ số thế hệ |
| **Retention / cleanup** | Xóa hoặc dọn file cũ theo count, age, total size | Không xóa sớm, không giữ vô hạn |
| **Compression** | Nén các bản đã rollover | File nén đọc được, nguồn được xử lý đúng, job hoàn thành |
| **Log shipping** | Chuyển file/event đến collector | Không mất/trùng khi file rename hoặc truncate |
| **External logrotate** | Hệ điều hành/tool ngoài JVM đổi tên hoặc copy/truncate | Appender có mở lại file, offset collector có hợp lệ |
| **Truncation** | File bị cắt nội dung tại chỗ | Không nhất thiết là rotation an toàn |

**Không đồng nhất tên file** với semantics. `java.util.logging.FileHandler` trong JDK, `RollingFileAppender` của Logback và `RollingFile` của Log4j 2 có cấu hình, thời điểm rollover, retention và khả năng nén khác nhau. Bài test phải bám vào **backend thực tế và version đang chạy**.

## 3. Xác định hợp đồng trước khi test

Trước khi viết một assertion, nên ghi rõ:

1. **Backend:** JUL `FileHandler`, Logback Classic, Log4j 2, hoặc hệ thống log của container/gateway?
2. **Trigger:** file đạt x bytes, đổi ngày lúc midnight, chu kỳ giờ/phút, hay đồng thời size + time?
3. **File active:** tên cố định `app.log` hay pattern có `%d`/`%i`/`%g`?
4. **Retention:** tối đa bao nhiêu thế hệ, bao nhiêu ngày, hay tổng dung lượng bao nhiêu?
5. **Compression:** `.gz`, `.zip`, hoặc không nén? Nén đồng bộ hay bất đồng bộ?
6. **Ghi tiếp:** chế độ append khi restart; có dọn history khi startup hay không?
7. **Độ tin cậy:** mức nào chấp nhận mất bản ghi khi process crash, disk đầy hoặc collector không đọc kịp?
8. **Phạm vi quyền:** ứng dụng có quyền tạo, rename, xóa file và thư mục lưu archive không?
9. **Thứ tự:** cần giữ thứ tự event theo một producer, hay chỉ cần mỗi event xuất hiện đúng một lần trong các file?
10. **Môi trường:** Windows/Linux, local disk, network mount, container writable layer, volume dùng chung?

Đừng viết test dựa trên giả định mơ hồ kiểu “file sẽ luôn chính xác 1 MB”. Một số appender kiểm tra kích thước **trước khi ghi event kế tiếp** hoặc kích hoạt rollover **sau khi một record đã vượt ngưỡng**, nên file thực tế có thể lớn hơn giá trị cấu hình trong thời gian ngắn. Kích thước được đo bằng **byte**, không phải số ký tự Java; UTF-8, stack trace, formatter và header/footer đều làm số byte thay đổi.

### 3.1. Những thuộc tính quan sát được

| Thuộc tính | Kiểm tra có ích |
| --- | --- |
| Rollover thực sự xảy ra | Thấy từ hai file/thế hệ sau khi ghi đủ event |
| File active tiếp tục nhận log | Marker mới nhất xuất hiện trong một file hợp lệ |
| Không vượt số thế hệ cấu hình | File count nằm trong bound được định nghĩa |
| Dữ liệu cũ được loại đúng lúc | Marker cũ nhất không còn khi retention đã kích hoạt |
| Dữ liệu còn trong cửa sổ giữ lại | Marker mới nhất và các marker cần giữ vẫn đọc được |
| Không có file bị giữ mở ngoài ý muốn | Handler/appender đóng được, lock được giải phóng |
| Compression hoàn chỉnh | Archive đọc giải nén được; không nhầm file tạm với file cuối |
| Restart an toàn | Trạng thái file cũ không bị truncate ngoài policy |
| Failure được thấy | Có thông báo/metrics/trạng thái khi rename hoặc write thất bại |
| Collector theo kịp | Log được ingest đủ theo hợp đồng, không chỉ tồn tại trên disk |

Một test không nhất thiết bao phủ tất cả. **Unit test** kiểm tra thuật toán/formatter, **integration test** kiểm tra file thật và backend, còn **end-to-end test** kiểm tra collector, restart và retention trên môi trường gần production.

## 4. Java 17: test tự động rotation của JUL FileHandler

Đây là chương trình **chạy độc lập với JDK 17+**, không cần Maven, SLF4J, Logback hay broker. Nó dùng `java.util.logging.FileHandler` với:

- Pattern `events-%g.log`: `%g` là **generation number**.
- Giới hạn file **240 bytes** và số thế hệ **3**.
- `append=false` để thư mục tạm mới bắt đầu từ trạng thái sạch.
- Formatter chỉ ghi message và dấu xuống dòng, tránh timestamp/stack trace làm test khó xác định.
- 36 marker `EVENT-001` đến `EVENT-036` với payload đủ dài để kích hoạt nhiều lần rollover.
- Các kiểm tra tự động về số file, marker mới nhất, marker cũ đã hết hạn và lock file sau khi đóng.

**Điểm mạnh:** chương trình kiểm tra *invariants*, không đoán chính xác mỗi file chứa bao nhiêu dòng. Chi tiết ngưỡng rollover ở byte cuối có thể thay đổi theo formatter và backend, nhưng hợp đồng test vẫn có ý nghĩa.

Lưu file **`RotationVerificationDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class RotationVerificationDemo {
    private static final int LIMIT_BYTES = 240;
    private static final int GENERATIONS = 3;

    private static List<Path> listFiles(Path dir) throws Exception {
        try (Stream<Path> stream = Files.list(dir)) {
            return stream.toList();
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("jul-rotation-test-");
        try {
            Logger logger = Logger.getLogger(
                    "demo.rotation." + System.nanoTime());
            logger.setUseParentHandlers(false);
            logger.setLevel(Level.INFO);

            String pattern = dir.resolve("events-%g.log").toString();
            FileHandler handler = new FileHandler(
                    pattern, LIMIT_BYTES, GENERATIONS, false);
            handler.setLevel(Level.INFO);
            handler.setEncoding(StandardCharsets.UTF_8.name());
            handler.setFormatter(new Formatter() {
                @Override
                public String format(LogRecord record) {
                    return record.getMessage() + "\n";
                }
            });

            logger.addHandler(handler);
            try {
                for (int i = 1; i <= 36; i++) {
                    logger.info(String.format(
                            Locale.ROOT,
                            "EVENT-%03d-%s", i, "X".repeat(80)));
                }
                handler.flush();
            } finally {
                logger.removeHandler(handler);
                handler.close();
            }

            List<Path> items = listFiles(dir);
            List<Path> logs = items.stream()
                    .filter(p -> p.getFileName().toString()
                            .matches("events-[0-9]+\\.log"))
                    .toList();

            require(logs.size() >= 2 && logs.size() <= GENERATIONS,
                    "Unexpected number of log generations");

            StringBuilder allContent = new StringBuilder();
            for (Path logFile : logs) {
                allContent.append(Files.readString(
                        logFile, StandardCharsets.UTF_8));
            }
            String text = allContent.toString();

            require(text.contains("EVENT-036-"),
                    "Newest log event missing");
            require(!text.contains("EVENT-001-"),
                    "Expired oldest log event still retained");

            boolean lockExists = items.stream().anyMatch(p ->
                    p.getFileName().toString().endsWith(".lck"));
            require(!lockExists, "FileHandler lock still present");

            System.out.println("PASS: rotated within 3 generations");
            System.out.println("PASS: latest message found");
            System.out.println("PASS: oldest message expired");
            System.out.println("PASS: lock released");
        } finally {
            // Xóa mọi file thử nghiệm, không tác động log thật.
            for (Path file : listFiles(dir)) {
                Files.deleteIfExists(file);
            }
            Files.deleteIfExists(dir);
        }
    }
}
```

Chạy:

```bash
javac RotationVerificationDemo.java
java RotationVerificationDemo
```

Kết quả **`stdout` khi cả bốn assertion thành công**:

```text
PASS: rotated within 3 generations
PASS: latest message found
PASS: oldest message expired
PASS: lock released
```

Nếu assertion thất bại, chương trình ném `AssertionError` và **không được coi là PASS**. Trong trường hợp filesystem/permissions lỗi, chương trình có thể ném exception; đây là lỗi môi trường hoặc I/O cần điều tra, không phải một stdout thành công khác.

### 4.1. Giải thích từng bước

1. `Files.createTempDirectory` tạo thư mục riêng cho lượt test. Nó có tên ngẫu nhiên nhưng không xuất vào các dòng PASS, nên output không phụ thuộc đường dẫn.
2. `Logger` riêng được tạo và `setUseParentHandlers(false)` tránh in thêm message vào console root logger.
3. `FileHandler(pattern, limit, count, append)` là API của JUL; `count=3` giữ số generation theo cơ chế `FileHandler`, không phải “giữ ba ngày”.
4. `%g` giúp tên file có generation riêng, ví dụ `events-0.log`, `events-1.log`. Test không giả định danh sách chính xác những generation đang tồn tại nếu không cần.
5. Mỗi message có 80 ký tự `X` cộng phần định danh. Sau 36 lần ghi, ngưỡng 240 bytes bị vượt nhiều lần, bảo đảm test phải quan sát rotation.
6. `handler.flush()` và `handler.close()` hoàn thành đường ghi đồng bộ thuộc handler. `close` cũng giải phóng lock do FileHandler quản lý.
7. `Files.list(dir)` chỉ đọc file sau khi handler đã đóng; điều này tránh đọc một file đang được ghi dở.
8. Test đếm **chỉ file `.log` theo tên generation**, không đếm `.lck` hay file khác vào retention.
9. `EVENT-036-` phải còn trong các file đang giữ, còn `EVENT-001-` phải bị loại sau rất nhiều lần xoay.
10. Test kiểm tra không còn `.lck` sau khi close rồi xóa thư mục tạm trong `finally`. Không dùng log folder của ứng dụng thật.

**Lưu ý quan trọng:** Ví dụ chỉ chứng minh các thuộc tính đã assert của **JUL FileHandler** trong môi trường chạy. Nó không chứng minh compression, time-based rotation, chống mất dữ liệu khi crash, thứ tự tuyệt đối giữa nhiều producer hoặc collector ingest đủ sự kiện.

### 4.2. Vì sao chọn kiểm tra marker thay vì đếm đúng 36 dòng?

Rotation có **retention hữu hạn**. Sau khi ghi 36 event nhưng chỉ giữ ba generation, nhiều event cũ **được phép bị xóa** theo chính sách. Assertion kiểu “đếm đủ 36 log cuối test” sẽ sai đối với cấu hình này.

Nếu mục tiêu là **không mất event trong một lần rollover cụ thể**, hãy chạy một test khác với retention đủ rộng, marker ID duy nhất, và đọc toàn bộ file tạo ra **trước khi cleanup xóa quá nhiều thế hệ**. Khi đó mới nên so sánh tập ID đầu vào và tập ID cuối cùng.

### 4.3. Những giới hạn thực tế của JUL FileHandler

`FileHandler` cung cấp size-based rotation theo `limit` và `count`; **không phải rolling policy time-based**. Pattern có thể dùng `%g` (generation), `%u` (unique ID), `%t` (temporary directory), `%h` (home), cùng các quy tắc giải tên của JUL.

- File naming có thể bổ sung hậu tố generation/unique nếu pattern không chứa các biến phù hợp.
- File lock `.lck` là một phần của cơ chế tránh va chạm tên trên handler/process; test cần đóng đúng lifecycle.
- `FileHandler` không cung cấp compression/age-based retention giống rolling policies của Logback/Log4j 2.
- Với non-ASCII, dung lượng file tính theo **bytes sau encoding**, không phải `String.length()`.
- Một event lớn có thể làm file vượt ngưỡng. Vì vậy test không nên áp một assertion cứng rằng **từng file luôn ≤ limit bytes** trong mọi trường hợp.
- Hành vi khi nhiều JVM cùng pattern và số file lock được quản lý cần kiểm thử riêng; đừng coi `%u` là sự bảo đảm coordination nhiều process trong mọi filesystem.

## 5. Size-based rotation: các ranh giới cần kiểm thử

Khi policy là “đổi file nếu size đạt ngưỡng”, test ít nhất các mức:

| Trường hợp | Cách thử | Kỳ vọng |
| --- | --- | --- |
| Dưới ngưỡng | Ghi một ít event có kích thước xác định | Chưa rollover khi điều kiện thực tế chưa đạt |
| Sát ngưỡng | Ghi tới vị trí gần giới hạn | Hành vi theo thuật toán trigger của backend |
| Vừa vượt ngưỡng | Ghi event làm tổng size vượt limit | Rotation được kích hoạt theo semantic đã định |
| Event đơn lẻ rất lớn | Ghi một message dài hơn limit | Không lỗi im lặng; xử lý oversize có quy tắc |
| Nhiều lần rollover | Ghi đủ nhiều event | Tạo thế hệ mới, chính sách cũ được áp dụng |
| File không có dữ liệu | Tạo appender, không gửi event | Không suy rằng luôn có archive |
| Flush/close | Ghi xong rồi đóng appender | Dữ liệu đã flush theo contract của handler |
| UTF-8 nhiều byte | Ghi ký tự tiếng Việt/emoji | Đo byte-size và decoder đúng encoding |
| Header/footer | Dùng formatter có head/tail | Không bỏ sót byte định dạng trong tính toán |
| Stack trace dài | Ghi Throwable với nhiều cause/suppressed | Rollover/formatter không làm hỏng event |

### 5.1. Tránh giả định về thời điểm xoay

Một backend có thể kiểm tra ngưỡng:

- **Trước khi** append một event mới;
- **Sau khi** đã ghi event làm vượt ngưỡng;
- Khi flush/rollover task chạy;
- Khi một period mới xuất hiện và **có event kế tiếp**.

Do đó “file 1 MB phải có chính xác 1.048.576 bytes” là assertion mong manh. Hãy kiểm tra hợp đồng: có rotation khi đủ tải, không vượt số thế hệ, phần dữ liệu cần giữ còn đọc được, và không có lỗi I/O bị che.

Đặc biệt không dùng `String.length()` làm đại diện cho kích thước file. `String.length()` trả số UTF-16 code units, trong khi `Files.size(path)` trả số byte. Dòng log còn chứa newline có thể là một hoặc hai byte tùy formatter/platform.

## 6. Time-based rotation: kiểm thử ranh giới ngày/giờ

Với time-based policy, điều quan trọng là **khoảng thời gian (period)** chứ không chỉ một giá trị epoch timestamp. Ví dụ pattern lưu theo ngày `app.%d{yyyy-MM-dd}.log` có thể xoay khi bước sang ngày mới.

Các ca test:

1. Ghi event ở thời điểm ngay **trước ranh giới period**.
2. Chuyển qua đầu period tiếp theo theo **clock/test fixture được kiểm soát** khi backend hỗ trợ.
3. Ghi event sau ranh giới.
4. Kiểm tra archive của period cũ và file nhận event của period mới.
5. Kiểm tra timezone, retention và policy restart khi ứng dụng bắt đầu giữa period.

**Không mặc định đến 00:00:00 hệ thống phải xoay file ngay lập tức.** Một số rolling appenders quyết định rollover khi **có event logging đầu tiên sau ranh giới**; hệ thống không có log lúc nửa đêm có thể chưa phát sinh file archive cho ngày mới cho đến khi hoạt động trở lại.

### 6.1. Đừng dùng sleep dài làm nền tảng duy nhất

Kiểu test:

```text
ghi log -> sleep tới 00:00 -> hy vọng file đổi tên -> assert
```

có thể chậm, dễ flaky vì scheduler, CI host tải cao, clock skew, DST hoặc nén bất đồng bộ. Ưu tiên:

- Test policy/clock abstraction bằng **clock giả/injectable** nếu phiên bản backend và API hỗ trợ.
- Integration test tách biệt với **period ngắn** trong môi trường riêng, có timeout và polling điều kiện.
- Test lại sau restart ở ngày/period mới.
- Không chỉnh đồng hồ máy CI dùng chung để ép rollover.

Nếu backend không hỗ trợ ép thời gian một cách ổn định qua public API, hãy ghi rõ giới hạn và dùng integration test chuyên biệt thay vì khẳng định có unit test deterministic hoàn toàn.

### 6.2. Timezone và DST

Khi dùng tên file theo ngày:

- Server có thể chạy theo UTC hoặc timezone địa phương.
- Đổi timezone cấu hình có thể khiến một timestamp thuộc ngày khác.
- DST khiến một số ngày có 23 hoặc 25 giờ, và một giờ local có thể xuất hiện hai lần.
- Container và host có thể có timezone khác nhau.
- Collector dùng UTC trong khi tên file ghi local time.

Một test tốt cố định timezone mong đợi, xác định nguồn thời gian và kiểm tra logic chuyển ngày. Tránh kỳ vọng “mỗi ngày luôn đúng 24 giờ” ở vùng có DST. Với hệ thống phân tán, UTC cho timestamp log thường giúp việc đối soát ổn định hơn.

## 7. Size-and-time rolling: kết hợp thời gian và số thứ tự

Nhiều ứng dụng production cần vừa tách archive theo ngày vừa không để một file của ngày đó quá lớn. Ví dụ tên:

```text
app.2026-11-10.0.log.gz
app.2026-11-10.1.log.gz
app.2026-11-10.2.log.gz
app.2026-11-11.0.log.gz
```

Hai điều kiện test độc lập:

1. **Cùng một period, đủ dữ liệu:** tăng `%i`, không ghi đè archive trước.
2. **Qua period mới:** tên period thay đổi và index được khởi tạo theo chính sách của backend.

Khi một event rất lớn vừa đúng lúc chuyển period, test xem **thứ tự trigger time/size** của thư viện thật. Không tự suy từ tên pattern rằng bộ xử lý luôn chạy time-based trước size-based.

Khi có compression, file `.gz` cuối có thể xuất hiện **sau** khi rollover đã bắt đầu. Phân biệt trạng thái: file active đã chuyển, archive bắt đầu nén, archive nén đã hoàn tất. Test không nên xem việc nhìn thấy tệp tên `.gz` có kích thước chưa ổn định là bằng chứng compression thành công.

## 8. Retention: xóa đúng nhưng không xóa nhầm

**Retention** có thể được định nghĩa bằng số thế hệ, số period lịch sử, tổng byte hoặc tổ hợp những điều kiện đó.

Ví dụ:

- JUL `FileHandler(count=3)`: tối đa ba generation theo cơ chế FileHandler.
- Logback `maxHistory=7` với rolling theo ngày: giữ khoảng **bảy period lịch sử**, không phải luôn bảy file; trong mỗi ngày có thể có nhiều `%i`.
- Logback `totalSizeCap`: giới hạn tổng dung lượng archives được quản lý theo logic cleanup của rolling policy, không phải “mỗi file luôn dưới cap”.
- Log4j 2 `DefaultRolloverStrategy max=...`: giới hạn index/rollover tương ứng với strategy và file pattern, **không tự là một chính sách xóa mọi file cũ qua mọi ngày**.

### 8.1. Ma trận test retention

| Kiểm thử | Mục tiêu |
| --- | --- |
| Chưa đủ lịch sử | Không xóa archive đang còn trong cửa sổ cho phép |
| Vượt số generation | Generation cũ nhất bị xoay/loại đúng policy |
| Vượt `maxHistory` | Chỉ xóa các period phù hợp; đúng timezone |
| Vượt tổng size archive | Cleanup chạy theo đúng điều kiện, có thể bất đồng bộ |
| Startup với nhiều archive cũ | Chính sách `cleanHistoryOnStart`/tương đương được tôn trọng |
| Restart nhiều lần | Không xóa dữ liệu còn hợp lệ hoặc giữ bản hết hạn mãi |
| Thư mục chứa file lạ | Không xóa file không thuộc rolling pattern |
| File archive đang được collector đọc | Không làm mất dữ liệu chưa được ingest theo thiết kế |
| Đổi naming pattern | Không giả định các archive cũ vẫn thuộc cleanup của policy mới |
| File permission/read-only | Xóa/rename thất bại được phát hiện |
| Compression chưa xong | Retention không để tệp nén nửa chừng thành bản cuối hợp lệ |

**Quan trọng:** việc dọn file lịch sử có thể được kích hoạt **sau rollover hoặc startup**, và có thể chạy asynchronous. Test nên **đợi một điều kiện trong khoảng thời gian hữu hạn** thay vì assert ngay sau một lời gọi ghi log nếu backend chưa bảo đảm cleanup đồng bộ.

### 8.2. Đừng test nhầm retention thành lossless delivery

Khi retention chủ đích xóa file cũ, các marker cũ **không còn là lỗi**. Hãy tách hai bài test:

- **Integrity during rollover:** set retention đủ rộng, kiểm tra event không bị mất trong quá trình đổi file.
- **Retention behavior:** chủ động vượt giới hạn rồi kiểm tra **đúng dữ liệu được xóa**.

Gộp cả hai và khẳng định “tất cả log từ đầu test phải còn nguyên” sẽ mâu thuẫn với cấu hình retention hữu hạn.

## 9. Compression: không chỉ nhìn đuôi .gz

Với archive nén gzip, nên kiểm tra:

1. Rollover tạo archive có tên đúng pattern.
2. Job nén kết thúc trong timeout hợp lý.
3. File archive có định dạng gzip hợp lệ và **giải nén đọc được**.
4. Nội dung giải nén có marker dự kiến.
5. Không còn file tạm/đầu ra dở theo policy sau khi hoàn tất.
6. Compression không làm file active ngừng ghi bất thường.
7. Cleanup không xóa nhầm archive đang nén hoặc còn trong retention.
8. Tốc độ nén, CPU và I/O đáp ứng tải thực tế.

Ví dụ lệnh kiểm tra archive gzip trong môi trường đã có công cụ gzip:

```bash
gzip -t logs/archive/app.2026-11-10.0.log.gz
gzip -cd logs/archive/app.2026-11-10.0.log.gz
```

Đây là **lệnh minh họa**, không bảo đảm file đó tồn tại. `gzip -t` kiểm tra cấu trúc gzip/CRC, còn `gzip -cd` giúp quan sát dữ liệu đã giải nén. Trên Windows hoặc CI image không có `gzip`, có thể dùng **`java.util.zip.GZIPInputStream`** để kiểm tra bằng Java.

Lưu ý nén thường làm kích thước archive **nhỏ hơn raw**, nhưng với dữ liệu ít hoặc không nén tốt, kích thước sau nén có thể lớn hơn đầu vào một chút. Không đặt assertion luôn “gzip file nhỏ hơn raw” như điều kiện correctness tuyệt đối.

## 10. Ví dụ cấu hình Logback để chạy integration test

Với ứng dụng **SLF4J + Logback Classic** đã có dependencies, có thể dùng một cấu hình **riêng cho bài kiểm thử**, không đụng thư mục log production.

Ví dụ `src/test/resources/logback-test.xml`:

```xml
<configuration>
    <appender name="ROLLING"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>build/test-logs/app.log</file>
        <rollingPolicy
            class="ch.qos.logback.core.rolling.SizeAndTimeBasedRollingPolicy">
            <fileNamePattern>build/test-logs/archive/app.%d{yyyy-MM-dd}.%i.log.gz</fileNamePattern>
            <maxFileSize>1MB</maxFileSize>
            <maxHistory>3</maxHistory>
            <totalSizeCap>10MB</totalSizeCap>
            <cleanHistoryOnStart>true</cleanHistoryOnStart>
        </rollingPolicy>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="ROLLING"/>
    </root>
</configuration>
```

Đây là **cấu hình tích hợp**, không chạy độc lập với JDK. Thư mục `build/test-logs` chỉ là đường dẫn minh họa: trong Gradle thường có `build`, trong Maven có thể chọn `target`; CI test nên dùng một **thư mục tạm riêng cho mỗi lượt chạy**, và truyền property vào cấu hình thay vì để nhiều test dùng chung một đường dẫn.

Ý nghĩa:

- `RollingFileAppender` ghi `build/test-logs/app.log` khi hoạt động.
- `SizeAndTimeBasedRollingPolicy` đặt pattern chứa cả `%d` và `%i`.
- `maxFileSize=1MB` kích hoạt vòng xoay theo size theo policy của phiên bản.
- `maxHistory=3` giới hạn **ba period lịch sử** (nếu period được suy ra theo ngày thì là khoảng ba ngày), không phải tối đa ba file archive.
- `totalSizeCap=10MB` đặt giới hạn tổng archive history khi cleanup chạy, không phải mỗi file.
- `cleanHistoryOnStart=true` cho phép xóa archive cũ khi appender khởi động theo chính sách.

**Tránh test ngay trên cấu hình production.** Retention/cleanHistoryOnStart có thể xóa archive thật. Không đưa file test vào thư mục dùng chung và không dựa trên ngày máy host nếu test cần deterministic.

### 10.1. Luồng integration test Logback

Một test đúng mức nên:

1. Tạo temp directory mới và cấu hình appender trỏ vào đó.
2. Bật pattern hoặc format đơn giản với **marker duy nhất** cho từng event.
3. Ghi đủ log để kích hoạt size rollover ở cùng period.
4. Đóng/stop `LoggerContext` hoặc appender được test theo lifecycle framework.
5. Kiểm tra archive và file active sau khi hoàn tất; nếu nén async, dùng polling điều kiện với timeout.
6. Giải nén archive và kiểm tra marker/encoding.
7. Khởi động lại với cùng thư mục để kiểm tra append/retention.
8. Xác minh metrics/status của logging backend không báo lỗi.
9. Dọn **chỉ** thư mục test sau khi mọi appender đã đóng.

Trong Logback, test có thể khai thác các API test nội bộ/clock phù hợp với phiên bản, nhưng không nên viết unit test phụ thuộc vào class internal nếu dễ thay đổi; ưu tiên contract test trên file output thực tế.

## 11. Log4j 2 RollingFile: chính sách và kiểm thử

Với ứng dụng dùng **Log4j 2**, một cấu hình minh họa:

```xml
<Configuration status="WARN">
    <Appenders>
        <RollingFile name="ROLLING"
                     fileName="build/test-logs/app.log"
                     filePattern="build/test-logs/archive/app-%d{yyyy-MM-dd}-%i.log.gz">
            <PatternLayout pattern="%d{ISO8601} %-5p %c - %m%n"/>
            <Policies>
                <TimeBasedTriggeringPolicy interval="1" modulate="true"/>
                <SizeBasedTriggeringPolicy size="1 MB"/>
            </Policies>
            <DefaultRolloverStrategy max="10"/>
        </RollingFile>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="ROLLING"/>
        </Root>
    </Loggers>
</Configuration>
```

Đây là cấu hình thử nghiệm cần dependency Log4j 2 tương thích, **không phải XML Logback**. Các thuộc tính `max`, `interval`, `modulate` và cách sắp xếp index phải được đánh giá trên version đang dùng.

Những điểm test chính:

- Có kích hoạt rollover do kích thước và ranh giới thời gian không?
- File pattern có tạo generation riêng, không overwrite ngoài policy?
- Strategy giới hạn những file/index mà nó chịu trách nhiệm như thế nào?
- Compression có hoàn tất và archive đọc được?
- Khi cần **age-based retention toàn bộ archive**, đã cấu hình Delete action/retention phù hợp hay chưa?
- Shutdown/reconfigure có đợi hoàn tất công việc đang chạy không?
- Có trạng thái lỗi qua Log4j 2 status logger hoặc bộ giám sát khi file không writable?

**Không kết luận `DefaultRolloverStrategy max="10"` có nghĩa “toàn bộ archive của mọi ngày trên disk sẽ luôn không quá 10 file”.** Kiểu retention này phụ thuộc file pattern, rollover strategy, điều kiện delete và môi trường.

## 12. Test rotation khi restart, crash và thay đổi cấu hình

Một ứng dụng Java được restart có thể mở lại cùng tên file active hoặc tiếp tục một generation. Những ca quan trọng:

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Graceful stop sau ghi | Appender flush/close, lock release |
| Restart khi file active chưa đầy | Append hoặc replace theo cấu hình, không ngoài ý muốn |
| Restart khi file gần đầy | Rollover đúng khi có event tiếp theo |
| Crash/kill bất ngờ | Giới hạn mất dữ liệu theo contract, không giả định shutdown hook chạy |
| Thư mục có archive cũ | Startup không xóa nhầm file còn hợp lệ |
| Đổi `fileNamePattern` | Cleanup và file enumeration xử lý naming mới/cũ theo chính sách |
| Đổi file size limit | Rollover sau restart được diễn giải đúng |
| Đổi retention | Những archive cũ bị giữ/xóa theo policy sau thay đổi |
| Đổi timezone | Phân loại period của archive không bị suy sai |
| Đổi encoding | Collector có đọc được file mới/cũ không |
| Đổi mức log | Tần suất ghi và kích hoạt rotation khác đi |
| Rolling appender báo lỗi đóng | App vẫn báo được sự cố ở đường giám sát độc lập |

**Shutdown thành công chưa đủ chứng minh durable logging.** `flush()` thường chuyển dữ liệu khỏi buffer của ứng dụng tới tầng I/O bên dưới, nhưng không mặc nhiên có nghĩa dữ liệu đã được `fsync` bền vững trên thiết bị. Nếu yêu cầu lưu audit nghiêm ngặt, cần thiết kế giải pháp có xác nhận/durability riêng, thay vì coi rotation là cơ chế bảo toàn giao dịch.

### 12.1. Test một thay đổi chính sách retention

Khi giảm retention từ 30 ngày xuống 7 ngày, cleanup có thể thực hiện sau rollover hoặc startup theo library. Test nên tạo **fixture file theo pattern và timestamp phù hợp**, kích hoạt cleanup theo documented API, sau đó polling trong timeout nếu chạy async. Không chỉ thay system clock hoặc chỉnh `lastModifiedTime` của file rồi cho rằng policy dựa trên thuộc tính đó: nhiều rolling implementations suy ra period từ **tên file**.

## 13. Concurrency: nhiều thread và nhiều process

Một ứng dụng Java có hàng chục thread cùng log. Cần test:

1. Nhiều thread ghi marker khác nhau cùng lúc.
2. Rollover xảy ra trong burst lớn.
3. Không có exception do rename/close trong lúc thread khác ghi.
4. Không bị corrupt encoding hoặc cắt message ngoài giới hạn formatter.
5. Marker cần giữ vẫn đọc được, số file không vượt policy sau khi appender ổn định.
6. Có thứ tự theo từng producer nếu ứng dụng cần, nhưng **không mặc định có thứ tự toàn cục** giữa các thread.
7. Với async logger, cần đợi queue drain trước khi đối chiếu.
8. Đo p95/p99 latency của producer khi rollover/nén, vì thao tác file có thể làm tăng độ trễ.

**Multi-process** là bài toán khác. Hai JVM cùng mở một đường dẫn file có thể đụng lock, gây tranh chấp rename hoặc mỗi process tự rotate một cách không phối hợp. JUL `FileHandler` có lock/`%u` nhưng không thể dùng đó làm lời cam kết rằng nhiều backend hoặc nhiều process cùng chia một RollingFileAppender sẽ hoạt động an toàn.

Khuyến nghị thực tế: thường để **mỗi process/container ghi một luồng riêng** và ship tới một collector, hoặc dùng cơ chế multi-process được backend hỗ trợ/kiểm chứng. Test trên **đúng hệ điều hành và filesystem** deployment; Windows có semantics khóa/rename file mở khác POSIX.

## 14. External logrotate: rename/reopen và copytruncate

Khi một tool ngoài JVM xoay log, appender nội bộ có thể không nhận ra ngay:

### 14.1. Rename + create new file

```text
app.log -> app.log.1
create new app.log
```

Một process còn giữ file descriptor cũ có thể tiếp tục ghi vào file đã rename, không phải file mới. Nếu backend không hỗ trợ reopen hoặc reconfiguration, test phải phát hiện rằng `app.log` mới không nhận dòng log như kỳ vọng.

### 14.2. Copytruncate

```text
copy app.log to app.log.1
truncate app.log in place
```

Giữa thao tác copy và truncate, process có thể ghi thêm; một số byte/log event có thể **bị mất hoặc nhân đôi**. Không khẳng định copytruncate là rotation lossless.

### 14.3. Tránh hai chủ sở hữu rotation

Nếu Logback RollingFileAppender **đã tự xoay theo policy** nhưng hệ điều hành còn chạy `logrotate` với cùng file active, hai cơ chế có thể đụng nhau. Một test end-to-end cần xác định chủ sở hữu rotation: **JVM** hay **external agent**. Không dùng cả hai mà không có thiết kế phối hợp cụ thể.

Trong container, đôi khi best practice là ứng dụng ghi `stdout/stderr` và nền tảng quản lý capture/rotation. Lúc đó test rotation phải nằm ở **container runtime/collector**, không phải nhất thiết tạo một `RollingFileAppender` trong ứng dụng Java.

## 15. Collector và rotation: test không mất/trùng dữ liệu

Một bài kiểm thử ở tầng ứng dụng có thể PASS nhưng observability end-to-end vẫn thất bại nếu shipper:

- Theo đường dẫn file nhưng không theo inode/file identity và bỏ sót sau rename.
- Đọc file mới từ offset cũ.
- Không đọc kịp trước khi retention xóa archive.
- Đọc trùng khi process restart hoặc state offset mất.
- Không xử lý multiline stack trace/JSON line đúng cách.
- Xử lý file nén/đổi tên khác với cấu hình.
- Không phân biệt dữ liệu có cùng timestamp từ nhiều JVM.

Test gần production:

```text
Java producer: emits marker ID 1..N
   -> RollingFile / FileHandler
   -> Log shipper
   -> Collector
   -> Search storage

Compare produced IDs, archived file IDs, ingested IDs,
duplicates, missing IDs and ingestion lag.
```

Dùng một lượt test có **retention đủ rộng** để việc xóa lịch sử không làm thiếu marker có chủ đích. Kiểm tra cả số lượng **ID logic** và số bản ghi trùng khi shipper retry. Một event có thể được giao **at-least-once** đến collector, nên có duplicate; nếu bài toán yêu cầu đếm chính xác phải có khóa/dedup phù hợp.

**Không dùng việc file đã tồn tại trên local disk để cam kết log đã đến centralized logging.** Rotation và shipping là hai chặng khác nhau.

## 16. Những lỗi môi trường phải chủ động gây ra trong test

| Fault injection | Kỳ vọng về phát hiện và xử lý |
| --- | --- |
| Thư mục log không tồn tại hoặc không writable | Appender thất bại rõ ràng hoặc failover theo policy |
| Filesystem đầy | Có cảnh báo/metric, không tiếp tục tuyên bố ghi thành công |
| Rename bị từ chối vì file lock | Được báo, không xóa archive hợp lệ |
| Compression lỗi | Có trạng thái lỗi, không nhầm archive hỏng là hoàn chỉnh |
| Path quá dài hoặc không hợp lệ | Config được kiểm tra và lỗi được phát hiện |
| Disk I/O rất chậm | Biết ảnh hưởng tới producer latency và async queue |
| Không đủ inode / quota | Biết khác với disk bytes còn trống |
| Collector mất kết nối | Biết mức backlog, lost/duplicate và thời gian hồi phục |
| Process bị kill cưỡng bức | Đánh giá mất event trước khi flush, không kỳ vọng drain |
| Clock/zone thay đổi | Tên period và retention không bất ngờ |
| Permission đổi trong lúc chạy | Biết lúc nào cần kiểm tra lại quyền |
| Archive directory đầy riêng | Không giả định active file và archive cùng filesystem |

Cần chạy những ca fault injection trong **môi trường test cô lập** với thư mục riêng. Không dùng ổ đĩa production để mô phỏng disk-full, không thay đổi quyền hoặc đồng hồ của host dùng chung.

## 17. Cách viết test ổn định trong CI

Những thực hành giảm flaky test:

- Dùng thư mục riêng mỗi test (`@TempDir` trong JUnit 5 hoặc `Files.createTempDirectory`).
- Dùng pattern path duy nhất để không đụng file của test chạy song song.
- Ghi marker đơn giản có ID xác định, không phụ thuộc text timestamp hoặc thread scheduling.
- Đợi appender/handler hoàn tất rồi **mới đọc các file**.
- Với nén và cleanup async, **poll điều kiện với timeout**, tránh `Thread.sleep(100)` rồi mong sự kiện đã kết thúc.
- Chặn tài nguyên leak bằng `try/finally` hoặc `try-with-resources` cho stream/reader.
- Đếm đúng tập file (archive, active, lock, tmp) thay vì `Files.list(dir).count()` toàn bộ.
- Test độc lập với thứ tự file do OS trả về; sort nếu trình bày.
- Đo kích thước bằng `Files.size`, không bằng `String.length`.
- Ghi rõ ý nghĩa version backend, default charset, timezone và lifecycle.
- Test assertion theo **hợp đồng** chứ không theo tên file ngẫu nhiên hoặc thời điểm chính xác tới millisecond.
- Không đưa test log vào cùng thư mục với log ứng dụng thật; dọn file sau khi đóng handler.

Với JUnit 5, có thể biến helper `require(...)` thành `assertTrue`/`assertFalse`, nhận thư mục từ `@TempDir` và chạy trước/sau mỗi test. Tuy nhiên, nếu dùng Logback/Log4j 2, cần tạo cấu hình test riêng và khởi tạo/dừng logger context đúng cách; **không gọi `LogManager.reset()` tùy tiện** trong một bộ test có những logger khác dùng chung global context.

### 17.1. Test timeout cho công việc bất đồng bộ

Ví dụ pseudo-code cho polling điều kiện:

```text
deadline = now_monotonic + timeout
while now_monotonic < deadline:
    if archive_ready_and_valid():
        PASS
    sleep_short_interval()
FAIL with useful diagnostics: observed files, sizes, backend status
```

Đây là **pseudocode**, không phải Java runnable. Dùng **monotonic clock** cho timeout (như `System.nanoTime()`) thay vì thời gian trên đồng hồ tường, vì timezone/NTP thay đổi có thể làm thời gian chờ sai. Timeout phải hữu hạn, tránh treo CI khi rollover/compression không xảy ra.

## 18. Monitoring giúp xác minh rotation trong vận hành

Không nên phát hiện lỗi rotation lần đầu tiên khi disk đầy. Những tín hiệu nên có:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Tổng byte log active và archive | Theo dõi tăng trưởng |
| Số file trong thư mục archive | Nhận diện retention không chạy |
| Thời gian từ lần rollover gần nhất | Phát hiện có log nhưng không xoay theo dự kiến |
| Lỗi file open/write/rename/delete | Báo I/O và quyền |
| Lỗi compression / archive invalid | Phát hiện file không dùng được |
| Thời gian rollover/compression | Đo độ trễ và CPU/I/O spike |
| Queue logging depth/dropped events | Theo dõi ảnh hưởng khi sink nghẽn |
| Shipper lag / ingestion lag | Biết collector có đọc kịp archive không |
| Disk usage / inode usage | Cảnh báo sớm trước khi hết tài nguyên |
| Restart count và config version | Nối sự cố rotation với deployment/cấu hình |

Đây là **nhóm tín hiệu gợi ý**, không phải metrics mặc định của mọi backend. Thông báo lỗi nội bộ của appender có thể được đưa qua status logger, `StatusManager` hoặc đường quản trị tùy thư viện. Nếu sink chính lỗi, chỉ log `ERROR rotation failed` vào **chính sink đó** có thể khiến cảnh báo cũng thất lạc; cần kênh monitoring thích hợp.

## 19. Những sai lầm phổ biến

### 19.1. Chỉ test tên file

Test `Files.exists("app.1.log")` không chứng minh file chứa nội dung hợp lệ, file active vẫn nhận dữ liệu hay archive không bị xóa sai.

### 19.2. So sánh `Files.size` bằng đúng giới hạn byte

Rollover có thể được kích hoạt trước/sau ghi event theo implementation; một event đơn lẻ có thể vượt limit. Hãy test trigger, retention và marker thay vì byte chính xác không có trong contract.

### 19.3. Dùng `Thread.sleep` để chắc chắn qua ngày

CI clock/scheduler có thể thay đổi; sleep dài và test chậm/flaky. Dùng clock abstraction/harness khi có thể hoặc integration test có timeout.

### 19.4. Đếm archive `.gz` ngay sau khi ghi

Nén có thể bất đồng bộ. File chưa tồn tại hoặc đang được tạo chưa chứng minh failure. Poll có timeout rồi xác minh giải nén và trạng thái backend.

### 19.5. Nghĩ `maxHistory=7` nghĩa là luôn có tối đa 7 file

Trong time-based rolling, đó thường là **số period lịch sử**. Với size-and-time, một period có thể có nhiều archive.

### 19.6. Đọc file đang mở và kết luận thiếu dữ liệu

Handler có thể còn buffer, compression chưa xong hoặc chưa flush. Đọc sau lifecycle đúng, không dùng thời điểm ngẫu nhiên làm mốc.

### 19.7. Test và app thật dùng chung log directory

Retention/cleanup của test có thể xóa file thật. Luôn cô lập đường dẫn test.

### 19.8. Không test restart

Một appender có thể xoay đúng trong một lần chạy nhưng ghi đè archive hoặc fail lock sau restart. Phải thử cả graceful và abrupt termination theo hợp đồng.

### 19.9. Dùng hai cơ chế xoay cùng một file

Internal rolling và external logrotate đồng thời có thể đụng rename/truncate. Chỉ định ownership rõ và test end-to-end.

### 19.10. Khẳng định rotation bảo đảm không mất log

Rotation là chính sách quản lý file; nó **không biến logging thành giao dịch bền vững**, không bảo đảm collector nhận đủ, và không chống mất dữ liệu khi crash/async queue đầy.

## 20. Checklist kiểm thử rotation

- [ ] Xác định backend, version, file pattern, trigger size/time, retention và compression.
- [ ] Dùng thư mục tạm độc lập, không chạm log production.
- [ ] Có marker duy nhất cho từng event và định nghĩa kiểm tra integrity.
- [ ] Test dưới ngưỡng, sát ngưỡng, vượt ngưỡng, event rất lớn, Unicode/UTF-8.
- [ ] Kiểm tra file active tiếp tục nhận log sau rollover.
- [ ] Đếm đúng generation, không tính file lock/tmp như archive.
- [ ] Test retention theo **count, period và totalSizeCap** khi áp dụng.
- [ ] Test nén archive bằng cách đọc/giải nén thật, có timeout cho job async.
- [ ] Test time boundary, timezone/DST và tình huống không có event qua ranh giới.
- [ ] Test restart/append/crash và thay đổi configuration version.
- [ ] Test nhiều thread và không dùng chung file với nhiều process ngoài hỗ trợ.
- [ ] Nếu dùng external logrotate, kiểm tra reopen và rủi ro copytruncate.
- [ ] Test collector ingest, lag, missing/duplicate IDs và retention đủ để ship.
- [ ] Fault injection: file lock, disk full, permission, rename/compression failure.
- [ ] Kiểm soát CI flakiness: temp dir, deterministic marker, polling timeout, close resources.
- [ ] Theo dõi disk usage, errors, queue depth/drops và status logger độc lập.
- [ ] Đối với audit log bắt buộc giữ, bổ sung yêu cầu durability và retention riêng.

**Kết luận:** Kiểm thử rotation trong Java logging là kiểm chứng **vòng đời file và tính đúng đắn của dữ liệu qua rollover**. Một test mạnh không dừng ở “file đã đổi tên”, mà xác nhận marker mới còn, dữ liệu cũ hết hạn đúng policy, lock được giải phóng, compression/collector không làm mất dữ liệu, và lỗi I/O được phát hiện. Hãy dùng **Java 17 FileHandler** để học cơ chế kích thước/số thế hệ, rồi kiểm thử đúng **Logback/Log4j 2 và môi trường triển khai thực tế** khi có time-based rolling, compression và retention phức tạp.
