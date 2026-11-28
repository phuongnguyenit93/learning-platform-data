# Rà soát thay đổi charset, locale, múi giờ và dữ liệu môi trường có ảnh hưởng kiểm thử

> **Chương:** Tác động nâng cấp  
> **Phạm vi:** Nâng cấp JDK 25 và đối chiếu dữ liệu quốc tế hóa trên các JDK mới hơn.  
> **Mục tiêu:** Phát hiện thay đổi về charset mặc định, locale data, múi giờ và môi trường chạy có thể làm thay đổi kết quả kiểm thử; xây dựng cách kiểm tra và cố định đầu vào để test có thể lặp lại.

## 1. Vì sao nâng JDK có thể làm test thay đổi dù code không đổi?

Một ứng dụng Java có thể đọc cùng một file, định dạng cùng một số tiền hoặc chuyển cùng một thời điểm sang giờ địa phương nhưng nhận kết quả khác sau khi đổi JDK. Nguyên nhân có thể nằm trong dữ liệu và mặc định của runtime:

- Charset mặc định dùng khi đọc/ghi text.
- Locale mặc định được suy ra từ hệ điều hành hoặc system properties.
- Dữ liệu định dạng ngày, số, tiền tệ và tên vùng được lấy từ CLDR.
- Quy tắc múi giờ được cập nhật theo IANA Time Zone Database (TZDB).
- Múi giờ và locale mặc định trong container/CI khác máy phát triển.
- Custom runtime được tạo bằng jlink thiếu module locale data cần thiết.

Các khác biệt này thường là **behavioral changes**: mã nguồn và binary vẫn chạy, nhưng output, parsing, thứ tự sắp xếp hoặc thời điểm địa phương thay đổi. Chỉ kiểm tra compile thành công không đủ để xác nhận tương thích.

Bài này tập trung vào bốn nhóm dữ liệu ảnh hưởng trực tiếp đến kiểm thử:

1. Charset và cách chuyển bytes thành text.
2. Locale và dữ liệu CLDR.
3. Time zone ID, TZDB rules và default zone.
4. Environment data trong máy phát triển, CI, container và production.

## 2. Bản đồ thay đổi theo JDK

Khi nâng cấp, hãy ghi lại cả **major release** lẫn **update release**. Một bản JDK 25.0.5 có thể chứa dữ liệu múi giờ mới hơn JDK 25 GA; không nên suy luận dữ liệu chỉ từ số major.

### Locale data

Oracle JDK dùng CLDR làm nguồn locale data mặc định. Các bản JDK gần đây có các phiên bản CLDR sau:

| JDK | CLDR | Điểm cần chú ý |
|---|---:|---|
| Java 25 | 47 | Mốc của bài học; CLDR là provider mặc định |
| Java 26 | 48 | Có thể thay đổi định dạng ngày, số, tiền tệ và tên locale |
| Java 27 | 48.2 | Tiếp tục cập nhật dữ liệu locale và một số quy tắc định dạng |

Dữ liệu CLDR có thể thay đổi giữa các release. Oracle lưu ý ứng dụng không nên giả định dữ liệu locale giữ nguyên; thay đổi có thể làm khác kết quả format hoặc khiến một chuỗi ngày cũ không còn parse được như trước.

Từ JDK 23, dữ liệu locale legacy của provider `JRE`/`COMPAT` đã bị loại bỏ. Trong JDK 25, provider mặc định tương đương `CLDR`; `HOST` và `SPI` có thể được dùng theo cấu hình và nền tảng. Nếu dự án còn cấu hình `java.locale.providers=COMPAT` hoặc `JRE`, hãy rà soát và chuyển sang CLDR hoặc provider SPI phù hợp.

### Time-zone database

TZDB được cập nhật theo thay đổi luật giờ địa phương của từng quốc gia. Ví dụ các bản Oracle JDK mới nhất tại thời điểm biên soạn:

| Runtime | Bản cập nhật | IANA TZ data |
|---|---|---|
| JDK 25 | 25.0.5.1, phát hành 17-11-2026 | 2026e |
| JDK 27 | 27.0.1.1, phát hành 17-11-2026 | 2026e |

Các con số trên mô tả bản Oracle JDK được nêu; vendor khác có thể đóng gói dữ liệu khác hoặc phát hành lịch cập nhật khác. Khi điều tra sự cố, hãy kiểm tra release notes của đúng JDK vendor/build.

### Charset mặc định

Từ JDK 18, JEP 400 quy định UTF-8 là charset mặc định cho Java SE APIs trên mọi hệ điều hành. Đây vẫn là hành vi trong JDK 25, 26 và 27. Ứng dụng nâng từ JDK 17 hoặc cũ hơn có thể thay đổi kết quả khi đọc/ghi file mà không truyền charset tường minh.

## 3. Charset: UTF-8 mặc định từ JDK 18

Trước JDK 18, charset mặc định thường phụ thuộc môi trường. Ví dụ trên Windows, nó có thể là code page như Windows-1252 hoặc Windows-31J; trên Linux/macOS thường là UTF-8 nhưng vẫn phụ thuộc locale và cấu hình.

Từ JDK 18 theo JEP 400:

- `Charset.defaultCharset()` trả về UTF-8 mặc định.
- Các Java SE APIs dựa trên default charset hoạt động nhất quán hơn giữa hệ điều hành.
- `file.encoding` mặc định là UTF-8.
- `native.encoding` mô tả encoding suy ra từ host environment; đây không phải giá trị để ứng dụng tự ghi đè.
- Giá trị `file.encoding=COMPAT` vẫn có thể dùng để chẩn đoán tương thích trong runtime hỗ trợ nó, nhằm tái hiện cách chọn charset trước JDK 18. Không dùng nó làm cấu hình chuẩn cho ứng dụng mới.

### Ví dụ lỗi khi nâng cấp

Giả sử file CSV cũ được xuất từ hệ thống Windows dùng Windows-1252:

~~~java
String text = Files.readString(Path.of("legacy.csv"));
~~~

Trên JDK mới, API dùng UTF-8 mặc định. Nếu file thực tế không phải UTF-8, một số ký tự có thể bị thay bằng ký tự lỗi hoặc giải mã sai. Cách sửa là xác định encoding thực của file và truyền rõ charset:

~~~java
String text = Files.readString(
        Path.of("legacy.csv"),
        Charset.forName("windows-1252"));
~~~

Với file do ứng dụng mới tạo theo UTF-8:

~~~java
String text = Files.readString(
        Path.of("orders.csv"),
        StandardCharsets.UTF_8);

Files.writeString(
        Path.of("orders-out.csv"),
        text,
        StandardCharsets.UTF_8);
~~~

**Không đoán charset từ máy chạy.** Encoding phải là một phần của hợp đồng file hoặc giao thức trao đổi dữ liệu.

### API nào cần rà soát?

| Cách dùng | Hành vi cần kiểm tra |
|---|---|
| `new String(bytes)` | Dùng default charset; có thể đổi khi nâng từ JDK 17 trở về trước |
| `text.getBytes()` | Dùng default charset |
| `FileReader(file)` / `FileWriter(file)` | Dùng default charset nếu không truyền charset |
| `Scanner` hoặc `Formatter` không chỉ định charset | Có thể phụ thuộc default charset |
| `Files.readString(path)` / `Files.writeString(path, text)` | UTF-8 theo hợp đồng API |
| `Files.newBufferedReader(path)` / `newBufferedWriter(path)` không truyền charset | UTF-8 theo hợp đồng API |
| `InputStreamReader(stream, charset)` | Dùng charset được chỉ định; rõ ràng và dễ kiểm soát |

Một ngoại lệ dễ bỏ sót: `Properties.load(InputStream)` có quy tắc encoding riêng theo đặc tả properties (ISO-8859-1), không tự động biến thành UTF-8 chỉ vì default charset của JVM là UTF-8. Nếu cần đọc properties bằng charset khác, dùng `Properties.load(Reader)` với Reader đã tạo bằng charset mong muốn.

## 4. Phân biệt file.encoding, native.encoding và encoding của standard streams

Ba nhóm này có mục đích khác nhau:

| Property | Ý nghĩa | Cách dùng |
|---|---|---|
| `file.encoding` | Charset mặc định cho nhiều Java SE APIs | JDK 18+ mặc định UTF-8 |
| `native.encoding` | Encoding được suy ra từ host environment | Dùng để chẩn đoán môi trường; không coi là cấu hình ứng dụng |
| `stdin.encoding` | Encoding của `System.in` | Có thể phụ thuộc terminal/host |
| `stdout.encoding` | Encoding của `System.out` và console | Có thể khác `file.encoding` |
| `stderr.encoding` | Encoding của `System.err` | Có thể khác `file.encoding` |

JEP 400 không có nghĩa mọi byte stream bên ngoài đều UTF-8. Encoding của standard input/output/error được cấu hình theo hệ thống và môi trường. Nếu test kiểm tra output console, log hoặc pipe từ process khác, hãy xác minh encoding của chính stream đó.

### Kiểm tra trên máy chạy

Linux/macOS:

~~~bash
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'file.encoding|native.encoding|stdin.encoding|stdout.encoding|stderr.encoding|user.language|user.country|user.timezone'
~~~

Windows PowerShell:

~~~powershell
java -XshowSettings:properties -version 2>&1 |
  Select-String 'file.encoding|native.encoding|stdin.encoding|stdout.encoding|stderr.encoding|user.language|user.country|user.timezone'
~~~

Có thể in trực tiếp trong ứng dụng:

~~~java
System.out.println("defaultCharset=" + Charset.defaultCharset());
System.out.println("file.encoding=" + System.getProperty("file.encoding"));
System.out.println("native.encoding=" + System.getProperty("native.encoding"));
System.out.println("stdout.encoding=" + System.getProperty("stdout.encoding"));
~~~

Không sửa system properties này sau khi JVM đã khởi động để kỳ vọng mọi API tự đổi hành vi. Hãy đặt cấu hình cần thiết trên command line khi tạo process, hoặc truyền charset tường minh tại API đọc/ghi.

## 5. Locale mặc định được lấy từ đâu?

Locale mặc định được thiết lập khi JVM khởi động, dựa trên host environment và các system properties như:

- `user.language` — mã ngôn ngữ, ví dụ `vi` hoặc `en`.
- `user.script` — hệ chữ viết, ví dụ `Latn`.
- `user.country` — mã vùng/quốc gia, ví dụ `VN` hoặc `US`.
- `user.variant` và `user.extensions` — thông tin bổ sung.

Locale có hai category quan trọng:

| Category | Mục đích | API truy vấn |
|---|---|---|
| `Locale.Category.FORMAT` | Định dạng ngày, giờ, số và tiền tệ | `Locale.getDefault(Locale.Category.FORMAT)` |
| `Locale.Category.DISPLAY` | Tên ngôn ngữ, quốc gia và nội dung giao diện | `Locale.getDefault(Locale.Category.DISPLAY)` |

Các factory không nhận Locale tường minh thường dùng default locale tương ứng. Ví dụ `NumberFormat.getCurrencyInstance()` dùng default FORMAT locale; các API lấy display name thường dùng DISPLAY locale.

Có thể đặt locale mặc định cho một tiến trình kiểm thử:

~~~bash
java \
  -Duser.language=vi \
  -Duser.country=VN \
  -Duser.timezone=Asia/Ho_Chi_Minh \
  -jar app.jar
~~~

Đây là cấu hình của JVM process. Nếu thay `System.setProperty("user.language", ...)` sau khi locale đã được khởi tạo, default Locale không tự thay đổi. `Locale.setDefault(...)` có thể thay đổi default locale của cả JVM, nên tránh dùng như cách thiết lập từng test khi test chạy song song.

### HOST provider và CLDR provider

Oracle JDK 25 hỗ trợ các locale data providers:

- `CLDR`: dữ liệu từ Unicode Common Locale Data Repository; là mặc định.
- `HOST`: phản ánh custom locale settings của hệ điều hành; trong Oracle JDK 25 provider này khả dụng trên Windows và macOS.
- `SPI`: provider do ứng dụng hoặc thư viện triển khai qua locale-sensitive SPI.

Nếu cấu hình `java.locale.providers`, thứ tự provider được đọc và cache khi locale service được khởi tạo; hãy đặt property lúc launch JVM, không đổi giữa một test suite đang chạy.

Không tiếp tục dùng `JRE`/`COMPAT` để mong lấy lại dữ liệu locale cũ trên JDK 25. Legacy locale provider đã bị loại bỏ; cần kiểm thử và chấp nhận dữ liệu CLDR hiện hành hoặc triển khai provider SPI theo yêu cầu.

## 6. CLDR thay đổi có thể làm output locale-sensitive khác nhau

CLDR chứa dữ liệu cho định dạng ngày, số, tiền tệ, tên tháng/ngày, tên quốc gia và nhiều quy tắc locale. Khi JDK cập nhật CLDR, cùng một API và cùng một Locale có thể trả về chuỗi khác.

Ví dụ:

~~~java
Locale locale = Locale.forLanguageTag("vi-VN");

NumberFormat currency =
        NumberFormat.getCurrencyInstance(locale);

DateTimeFormatter dateFormatter =
        DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG)
                .withLocale(locale);

System.out.println(currency.format(1250000));
System.out.println(dateFormatter.format(LocalDate.of(2026, 11, 27)));
~~~

Không nên chép một output cụ thể rồi khẳng định nó sẽ giống hệt trên mọi JDK update. Ký hiệu tiền tệ, khoảng trắng, dấu phân nhóm, cách viết tháng hoặc tên vùng có thể thay đổi theo CLDR.

### Các test dễ bị ảnh hưởng

| Test | Khác biệt có thể xuất hiện |
|---|---|
| Snapshot chuỗi ngày | Tên tháng, thứ tự ngày/tháng, dấu câu hoặc chữ viết |
| Format tiền tệ | Ký hiệu, vị trí ký hiệu, khoảng trắng, số chữ số thập phân |
| Format số | Dấu thập phân, dấu nhóm, chữ số |
| Parse ngày | Chuỗi cũ có thể không còn khớp parser sau cập nhật locale data |
| Collation/sorting | Thứ tự so sánh chuỗi có thể thay đổi |
| Tên quốc gia/ngôn ngữ | Bản dịch hoặc cách hiển thị có thể đổi |

### Cách viết test bền vững

- Truyền Locale tường minh thay vì dùng default.
- Với format máy đọc, dùng định dạng chuẩn như ISO-8601, không dùng chuỗi hiển thị theo ngôn ngữ.
- Với test kiểm tra phép tính, parse thành giá trị số/ngày rồi so sánh giá trị, không chỉ so sánh chuỗi hiển thị.
- Nếu output là hợp đồng giao tiếp hoặc snapshot sản phẩm, pin JDK build và cập nhật expected output có kiểm soát sau khi review thay đổi CLDR.
- Nếu cần output locale cố định lâu dài qua nhiều JDK, cân nhắc đóng gói/version hóa dữ liệu format riêng thay vì dựa vào dữ liệu locale mặc định của JDK.

Không dùng `Locale.ROOT` thay cho mọi locale. `ROOT` hữu ích cho quy tắc trung lập ngôn ngữ hoặc machine-oriented formatting; giao diện người dùng cần Locale cụ thể.

## 7. Custom runtime và module jdk.localedata

Trong Oracle JDK 25, locale data của US English và các parent locale nằm trong `java.base`. Phần lớn locale data khác nằm trong module `jdk.localedata`.

Một custom runtime tạo bằng `jlink` có thể bỏ module này nếu không thêm rõ ràng. Khi đó, ứng dụng có thể chạy được nhưng thiếu dữ liệu cho locale mà test hoặc production cần.

Ví dụ tạo runtime image có locale data:

~~~bash
jlink \
  --add-modules java.base,jdk.localedata,java.logging \
  --include-locales en,vi,ja \
  --output runtime-image
~~~

Danh sách module thực tế phải bao gồm tất cả module ứng dụng cần. Ví dụ chỉ minh họa cách giữ locale data; hãy kiểm tra locale tag được hỗ trợ bởi JDK/vendor và kiểm tra runtime image sau khi tạo.

### Kiểm tra runtime image

- Chạy cùng bộ test locale trên JDK đầy đủ và image jlink.
- Gọi các API format ngày/số/tiền tệ cho từng locale bắt buộc.
- Xác minh locale cần thiết xuất hiện trong `Locale.getAvailableLocales()`.
- Kiểm tra log và exception nếu locale data bị thiếu.
- Không giả định runtime image tối giản tương đương đầy đủ JDK về dữ liệu locale.

## 8. Múi giờ mặc định và cách JVM xác định

Múi giờ mặc định của JVM thường được lấy từ host environment. `TimeZone.getDefault()` dùng `user.timezone` nếu property có giá trị; nếu không, JVM phát hiện platform time-zone ID; nếu không xác định được, GMT là phương án cuối.

`ZoneId.systemDefault()` truy vấn default TimeZone rồi chuyển thành ZoneId. Vì vậy, hai môi trường có thể chạy cùng JAR nhưng có default zone khác nhau.

Các nguồn cần kiểm tra:

- Linux: `TZ`, cấu hình locale/time zone của hệ điều hành và file `/etc/localtime`.
- Container: environment variables được khai báo trong image/deployment, mount dữ liệu zone và cấu hình của container host.
- Windows: time-zone setting của hệ điều hành và cách JDK ánh xạ ID.
- Java process: `-Duser.timezone` hoặc property `user.timezone` nếu được đặt.

### Kiểm tra runtime

~~~java
System.out.println("zoneId=" + ZoneId.systemDefault());
System.out.println("timeZoneId=" + TimeZone.getDefault().getID());
System.out.println("user.timezone=" + System.getProperty("user.timezone"));
System.out.println("now=" + ZonedDateTime.now());
~~~

Lệnh Linux:

~~~bash
date
date +%Z
date +%z
printenv TZ
readlink -f /etc/localtime
~~~

Không phải môi trường nào cũng có `timedatectl` hoặc `readlink`. Trong container tối giản, kiểm tra các biến môi trường và file zone hiện có thay vì giả định tiện ích hệ điều hành được cài.

## 9. Region-based ZoneId khác fixed offset

Hai dạng này không tương đương:

~~~java
ZoneId region = ZoneId.of("America/New_York");
ZoneOffset fixed = ZoneOffset.ofHours(-5);
~~~

- Region ID như `America/New_York` đại diện cho quy tắc của một vùng địa lý. Offset có thể thay đổi theo mùa hoặc theo quyết định của chính phủ.
- Fixed offset như `-05:00` luôn giữ cùng offset, không có quy tắc DST.

Không lưu lịch hẹn tương lai theo offset cố định nếu nghiệp vụ thực sự gắn với giờ địa phương của một vùng. Ví dụ cuộc họp định kỳ lúc 09:00 tại New York nên lưu local date/time cùng region ID; khi luật DST thay đổi, runtime dùng TZDB mới để xác định offset phù hợp.

Với sự kiện đã xảy ra, lưu `Instant` là cách thể hiện thời điểm tuyệt đối. Có thể lưu thêm ZoneId gốc để hiển thị lại theo ngữ cảnh nghiệp vụ.

### Tránh timezone abbreviations

Các ID ba chữ như `PST`, `CST`, `IST` hoặc `VST` có thể mơ hồ. Java vẫn hỗ trợ một số abbreviation vì tương thích lịch sử, nhưng tài liệu khuyến cáo không dùng chúng cho hệ thống mới.

Dùng region ID rõ nghĩa, ví dụ:

- `Asia/Ho_Chi_Minh`
- `Asia/Tokyo`
- `Europe/Paris`
- `America/New_York`

Không giả định alias lịch sử sẽ luôn là ID mặc định được trả về. JDK 27 đã sửa một trường hợp trên Windows: `TimeZone.getDefault()` trước đây có thể trả ID cũ `Asia/Calcutta`, nay trả ID hiện hành `Asia/Kolkata`. Test so sánh chuỗi ID tuyệt đối có thể cần cập nhật nếu nó dựa vào alias cũ.

## 10. TZDB cập nhật có thể làm đổi kết quả ngày giờ

Quy tắc múi giờ do chính phủ quyết định và có thể đổi sau khi một ứng dụng đã được phát hành. JDK đóng gói dữ liệu TZDB; update JDK có thể cập nhật bộ dữ liệu đó.

Ví dụ trong JDK 25.0.5.1 và JDK 27.0.1.1 của Oracle, dữ liệu IANA được cập nhật lên 2026e. Bản cập nhật này có các thay đổi cho một số vùng tại Canada, nhưng tác động của TZDB không chỉ giới hạn ở các vùng đó: mọi ứng dụng dùng zone rules được cập nhật cần được kiểm tra lại ở những ngày chuyển đổi có liên quan.

### Xem phiên bản zone rules

Có thể truy vấn version mà provider đang cung cấp:

~~~java
NavigableMap<String, ZoneRules> versions =
        ZoneRulesProvider.getVersions("Asia/Ho_Chi_Minh");

System.out.println("tzdbVersion=" + versions.lastKey());
~~~

Phiên bản trả về phụ thuộc provider/JDK đang chạy. Ghi nó vào báo cáo kiểm thử để so sánh giữa các build. Với custom ZoneRulesProvider, version string có thể theo quy ước của provider đó.

### Tìm vùng và ngày nhạy cảm

- Các vùng có DST: kiểm tra ngày chuyển sang giờ mùa hè và quay lại giờ chuẩn.
- Các vùng vừa thay đổi luật: kiểm tra ngày hiệu lực và lịch hẹn sau ngày đó.
- Các vùng có thay đổi offset lịch sử: kiểm tra dữ liệu báo cáo quá khứ nếu ứng dụng tính lại thời gian địa phương.
- Các lịch hẹn tương lai: xác nhận chính sách nghiệp vụ khi luật địa phương thay đổi.

Khi tạo local date-time nằm trong DST gap hoặc overlap, cần xác định nghiệp vụ muốn tự điều chỉnh, chọn offset sớm/muộn hay từ chối dữ liệu. Không mặc định mọi LocalDateTime đều ánh xạ duy nhất sang một Instant.

## 11. Làm cho test thời gian có thể lặp lại bằng Clock

Không gọi trực tiếp `LocalDate.now()` hoặc `ZonedDateTime.now()` trong logic cần kiểm thử nếu kết quả phụ thuộc thời gian hiện tại. Các lời gọi đó lấy system clock và thường dùng system default zone.

Inject `Clock` để kiểm soát thời điểm và múi giờ:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

final class BillingPeriod {
    static LocalDate businessDate(Clock clock) {
        return LocalDate.now(clock);
    }

    public static void main(String[] args) {
        Clock fixed = Clock.fixed(
                Instant.parse("2026-11-27T02:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println(businessDate(fixed));
    }
}
~~~

Kết quả không phụ thuộc ngày chạy test hay timezone của CI.

Trong test:

- Dùng `Clock.fixed` cho một thời điểm cố định.
- Dùng `Clock.offset` để kiểm tra thời gian trước/sau một khoảng.
- Truyền `ZoneId` rõ ràng cho nghiệp vụ theo vùng.
- Kiểm tra các biên ngày, nửa đêm, tháng/năm mới và DST gap/overlap.
- Không thay đổi system default timezone của JVM trong test chạy song song.

### Mô hình lưu trữ thời gian

| Nhu cầu nghiệp vụ | Kiểu dữ liệu nên cân nhắc |
|---|---|
| Thời điểm sự kiện đã xảy ra | `Instant` |
| Ngày lịch không có giờ | `LocalDate` |
| Giờ địa phương không có ngày | `LocalTime` |
| Ngày/giờ địa phương cần gắn với một vùng | `LocalDateTime` + `ZoneId` |
| Thời điểm đã quy đổi theo zone | `ZonedDateTime` |
| Offset cố định trong giao thức | `OffsetDateTime` hoặc `ZoneOffset` theo hợp đồng |

Không dùng `LocalDateTime` đơn lẻ làm timestamp toàn cầu. Nó không chứa offset hoặc zone nên không xác định được duy nhất một Instant.

## 12. Kiểm thử locale và charset mà không phụ thuộc host

Một test tốt nên cố định đầu vào thay vì giả định máy chạy có locale hoặc encoding giống máy lập trình viên.

### Test charset

~~~java
@Test
void utf8FileRoundTrip() throws Exception {
    Path file = tempDir.resolve("vietnamese.txt");
    String expected = "Tiếng Việt: dấu và ký tự Unicode";

    Files.writeString(file, expected, StandardCharsets.UTF_8);

    String actual = Files.readString(file, StandardCharsets.UTF_8);

    assertEquals(expected, actual);
}
~~~

Test này xác nhận hợp đồng UTF-8 của ứng dụng. Nếu cần kiểm tra tương thích với file legacy, tạo fixture bytes đúng encoding legacy và đọc bằng charset được khai báo rõ.

### Test locale

~~~java
@Test
void currencyUsesExplicitLocale() {
    Locale locale = Locale.forLanguageTag("vi-VN");
    NumberFormat format = NumberFormat.getCurrencyInstance(locale);

    String result = format.format(1250000);

    assertNotNull(result);
    assertFalse(result.isBlank());
}
~~~

Nếu test cần xác nhận chuỗi hiển thị chính xác, pin JDK build và CLDR data version trong test environment; cập nhật expected string có review khi JDK/CLDR thay đổi. Nếu mục tiêu là logic nghiệp vụ, hãy kiểm tra giá trị số sau parse thay vì khóa cứng dấu phân nhóm hoặc ký hiệu tiền tệ.

### Test locale mặc định trong process riêng

Để xác nhận ứng dụng không vô tình phụ thuộc host, chạy một JVM test riêng với các giá trị khác nhau:

~~~bash
java -Duser.language=en -Duser.country=US -Duser.timezone=UTC -cp test-classes TestDefaults
java -Duser.language=vi -Duser.country=VN -Duser.timezone=Asia/Ho_Chi_Minh -cp test-classes TestDefaults
~~~

Hai process giúp phát hiện code dùng default locale/zone ngầm định. Không đổi global defaults giữa các test method đang chạy song song.

## 13. Kiểm tra environment data trong CI và container

Máy phát triển, CI runner và production container có thể khác nhau ở:

| Dữ liệu | Cần ghi nhận | Rủi ro |
|---|---|---|
| JDK | Vendor, full version, build | Locale/TZDB data và behavior khác |
| OS/architecture | Linux distribution, Windows/macOS, CPU arch | Default locale/timezone và native encoding |
| Charset | file.encoding, native.encoding, stream encodings | Đọc file hoặc kiểm tra console khác |
| Locale | LANG, LC_ALL, user.language, user.country | Format/parsing khác |
| Time zone | TZ, user.timezone, ZoneId.systemDefault() | Local date/time khác |
| Locale data | CLDR version, java.locale.providers | Currency/date/sort output khác |
| TZDB | Version từ ZoneRulesProvider | DST và offset lịch sử/tương lai khác |
| Runtime image | Có jdk.localedata hay không | Thiếu locale data trong custom image |

### Ví dụ Docker environment có chủ đích

~~~dockerfile
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV TZ=UTC

ENTRYPOINT ["java",
  "-Duser.language=en",
  "-Duser.country=US",
  "-Duser.timezone=UTC",
  "-jar",
  "/app/app.jar"]
~~~

Đây là ví dụ cấu hình môi trường test trung lập. Nếu ứng dụng cần hiển thị cho người dùng Việt Nam, hãy truyền Locale `vi-VN` ở tầng format nghiệp vụ/giao diện thay vì phụ thuộc default locale của container.

Không phải mọi image đều có sẵn dữ liệu zone hoặc tiện ích hệ điều hành. Xác nhận image có dữ liệu timezone cần thiết và dùng đúng đường dẫn/configuration của base image.

### Ghi environment fingerprint vào log test

Một bước setup test có thể in:

- `Runtime.version()` và `java.vendor`.
- `Charset.defaultCharset()`, `file.encoding` và `native.encoding`.
- `Locale.getDefault(FORMAT)` và `Locale.getDefault(DISPLAY)`.
- `ZoneId.systemDefault()` và TZDB version.
- `java.locale.providers` nếu được đặt.

Khi một snapshot thay đổi, fingerprint giúp xác định thay đổi đến từ JDK, locale data, timezone data hay environment.

## 14. Quy trình rà soát khi nâng từ JDK 25 lên JDK mới hơn

### Bước 1 — Lập baseline

Ghi lại full JDK build, vendor, OS, charset properties, default locales, default zone, CLDR version và TZDB version của môi trường hiện tại.

### Bước 2 — Tìm API phụ thuộc default

Rà soát code và test có dùng:

- `Charset.defaultCharset()` hoặc API đọc/ghi không truyền charset.
- `new String(bytes)`, `getBytes()`.
- `NumberFormat`, `DateFormat`, `Collator` không truyền Locale.
- `LocalDate.now()`, `ZonedDateTime.now()` hoặc `ZoneId.systemDefault()`.
- `TimeZone.getDefault()`, `Locale.getDefault()`.
- `java.locale.providers`, `file.encoding`, `user.timezone`.

### Bước 3 — Chạy test matrix

Chạy cùng bộ test trên JDK 25 hiện hành và JDK đích. Giữ nguyên application artifact, dữ liệu, OS image, locale, timezone và cấu hình load; sau đó chạy thêm một lượt cố ý thay đổi locale/timezone để phát hiện phụ thuộc ngầm.

### Bước 4 — Rà soát snapshot và dữ liệu

Phân loại thay đổi thành:

- Thay đổi hợp lệ do CLDR/TZDB cập nhật.
- Lỗi do code phụ thuộc default charset/locale/timezone.
- Thiếu locale data trong jlink image.
- Khác biệt environment giữa CI và production.
- Thay đổi không mong muốn cần báo lỗi hoặc rollback.

### Bước 5 — Cập nhật test và hợp đồng

Dùng explicit charset/locale/zone/clock ở nơi có hợp đồng xác định. Cập nhật snapshot chỉ sau khi xác minh output mới đúng với nghiệp vụ. Không tự động chấp nhận toàn bộ golden files thay đổi.

### Bước 6 — Đưa fingerprint vào CI

Lưu JDK build, CLDR/TZDB version và các default properties trong artifact test report. Khi test thất bại sau một lần JDK update, nhóm có thể tái hiện đúng môi trường.

~~~mermaid
flowchart TD
    A["Chốt JDK 25 baseline"] --> B["Thu charset / locale / zone / data versions"]
    B --> C["Rà soát API phụ thuộc default"]
    C --> D["Chạy test trên JDK đích"]
    D --> E["So sánh output và environment fingerprint"]
    E --> F{"Khác biệt có đúng nghiệp vụ?"}
    F -->|Có| G["Cập nhật expected data có review"]
    F -->|Không| H["Sửa code hoặc environment"]
    G --> I["Chạy lại regression và container tests"]
    H --> I
    I --> J["Lưu baseline mới"]
~~~

## 15. Các lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| File CSV lỗi dấu sau khi nâng JDK | File legacy không phải UTF-8 nhưng code dùng default charset | Xác định encoding thật và truyền charset tường minh |
| Console hiển thị sai dù file UTF-8 đúng | stdout/stderr encoding khác file.encoding | Kiểm tra stdout.encoding/stderr.encoding và terminal |
| Snapshot tiền tệ đổi | CLDR version hoặc Locale mặc định đổi | Truyền Locale rõ ràng; review expected output |
| Parse ngày cũ bị lỗi | CLDR date pattern/text thay đổi hoặc parser phụ thuộc locale | Dùng format giao thức cố định hoặc parser locale được chỉ định |
| Sort tên khác thứ tự | Collation data/provider thay đổi | Xác định quy tắc sort nghiệp vụ; pin provider/data nếu cần |
| Ngày nghiệp vụ lệch một ngày | Default timezone của CI/container khác | Inject ZoneId/Clock; cố định user.timezone trong test |
| Lịch hẹn tương lai đổi giờ | TZDB cập nhật quy tắc vùng | Kiểm tra region ID và quy tắc mới; xác nhận chính sách lịch hẹn |
| ID zone đổi tên trên Windows | JDK cập nhật mapping ID nền tảng | So sánh ZoneId/ZoneRules theo ý nghĩa; không khóa cứng alias cũ |
| Locale hoạt động trên JDK đầy đủ nhưng lỗi trong image | jlink thiếu jdk.localedata | Thêm module và include locale cần thiết |
| Cấu hình COMPAT không còn tác dụng | Legacy JRE/COMPAT locale provider đã bị loại bỏ | Chuyển sang CLDR hoặc SPI phù hợp |
| Test pass local nhưng fail CI | LANG, LC_ALL, TZ hoặc system properties khác nhau | Ghi fingerprint và cố định môi trường test |
| Test phụ thuộc ngày hiện tại chập chờn | Gọi now() trực tiếp | Inject Clock.fixed hoặc Clock có zone tường minh |

## 16. Checklist nghiệm thu và bài tập thực hành

### Checklist charset

- [ ] Đã xác nhận JDK 18+ dùng UTF-8 làm default charset.
- [ ] Đã rà soát API đọc/ghi không truyền charset.
- [ ] File legacy có encoding được xác định bằng hợp đồng hoặc metadata.
- [ ] Không dùng `native.encoding` làm default file charset.
- [ ] Đã kiểm tra riêng encoding của standard input/output/error.
- [ ] Đã kiểm tra cách đọc properties theo đúng quy tắc của `Properties`.

### Checklist locale

- [ ] Đã ghi CLDR version của JDK hiện tại và JDK đích.
- [ ] Đã kiểm tra `Locale.Category.FORMAT` và `DISPLAY`.
- [ ] Các API format/parse quan trọng truyền Locale tường minh.
- [ ] Không còn cấu hình `JRE`/`COMPAT` cũ.
- [ ] Đã kiểm tra jdk.localedata nếu dùng custom runtime.
- [ ] Snapshot locale được cập nhật có review.

### Checklist time zone

- [ ] Đã ghi `ZoneId.systemDefault()` và `user.timezone`.
- [ ] Lịch nghiệp vụ dùng region ID thay vì abbreviation mơ hồ.
- [ ] Đã phân biệt Instant, LocalDateTime, ZoneId và fixed offset.
- [ ] Đã ghi TZDB version của runtime.
- [ ] Đã kiểm tra DST gap/overlap và ngày có thay đổi luật.
- [ ] Test thời gian dùng Clock cố định hoặc Clock được inject.

### Bài tập thực hành

Một dịch vụ báo cáo chạy trên JDK 17 ở Windows và chuẩn bị nâng lên JDK 25 trong container Linux.

1. Xác định charset mặc định của JDK cũ và JDK mới; kiểm tra encoding thật của CSV.
2. Thay các API file I/O phụ thuộc default charset bằng API có charset rõ ràng.
3. Ghi lại default FORMAT/DISPLAY locale và CLDR version.
4. Chạy format tiền tệ với Locale `vi-VN` và `en-US`; xác định snapshot nào là hợp đồng sản phẩm, snapshot nào chỉ là dữ liệu hiển thị.
5. Ghi default timezone và TZDB version trong Windows, container và JDK 25.
6. Thay các lời gọi `now()` bằng Clock được inject.
7. Chạy regression trên JDK 25.0.5.1 và JDK 27.0.1.1, so sánh environment fingerprint.
8. Báo cáo từng khác biệt, giải thích nguồn dữ liệu và đề xuất cách sửa.

**Câu hỏi tự đánh giá:**

1. JEP 400 thay đổi default charset từ JDK nào?
2. Vì sao `native.encoding` không thay thế `file.encoding`?
3. Tại sao `System.out` có thể có encoding khác default charset?
4. CLDR data có thể làm thay đổi những loại output nào?
5. Vì sao cấu hình `java.locale.providers=COMPAT` không còn là giải pháp nâng cấp?
6. Khác biệt giữa `ZoneId.of("Asia/Ho_Chi_Minh")` và `ZoneOffset.ofHours(7)` là gì?
7. Vì sao cùng một JAR có thể tạo ngày địa phương khác nhau trong hai container?
8. Khi nào cần dùng `Clock.fixed()` thay vì gọi `LocalDate.now()`?
9. Vì sao phải kiểm tra cả JDK update release chứ không chỉ major version?
10. Custom runtime cần module nào để cung cấp locale data ngoài US English?

## 17. Tài liệu chính thức

- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi charset mặc định từ JDK 18.
- [Oracle JDK 25 — Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): rà soát ảnh hưởng khi nâng từ JDK cũ, bao gồm default charset.
- [Oracle JDK 25 — Supported Locales](https://www.oracle.com/java/technologies/javase/jdk25-supported-locales.html): CLDR 47, provider CLDR/HOST/SPI và module locale data.
- [Oracle JDK 26 — Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html): CLDR 48.
- [Oracle JDK 27 — Supported Locales](https://www.oracle.com/java/technologies/javase/jdk27-suported-locales.html): CLDR 48.2 và các provider hiện hành.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): lịch sử và cơ sở sử dụng CLDR.
- [Oracle JDK 25 — Charset API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/Charset.html): default charset và hành vi của Charset.
- [Oracle JDK 25 — Locale API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Locale.html): default locale, category FORMAT/DISPLAY và locale construction.
- [Oracle JDK 25 — ZoneId API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZoneId.html): region IDs, fixed offsets và zone rules.
- [Oracle JDK 25 — ZoneRulesProvider API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/zone/ZoneRulesProvider.html): truy vấn các version zone rules.
- [Oracle JDK 25 — Consolidated Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): phiên bản JDK update và IANA TZ data.
- [Oracle JDK 27 — Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): thay đổi locale/timezone và mapping ID trên Windows.
- [Oracle JDK 25 — Internationalization Guide](https://docs.oracle.com/en/java/javase/25/intl/internationalization-guide.pdf): hướng dẫn quốc tế hóa, locale provider và date/time.
- [Oracle JDK 25 — Supported Encodings](https://docs.oracle.com/en/java/javase/25/intl/supported-encodings.html): default charset và encoding của standard streams.

> **Ghi nhớ:** Khi nâng JDK, hãy so sánh cả charset, CLDR, TZDB và environment fingerprint. Từ JDK 18, default charset là UTF-8; JDK 25 dùng CLDR 47; các bản JDK 25/27 mới nhất của Oracle tại thời điểm biên soạn dùng TZDB 2026e. Trong test, truyền charset, Locale, ZoneId và Clock tường minh để kết quả có thể tái hiện.
