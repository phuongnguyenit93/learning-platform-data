# Ma trận hệ điều hành, CPU, locale và phiên bản driver

*Tình trạng được đối chiếu với Oracle JDK 26 và tài liệu driver hiện hành tại ngày 27/11/2026.*

Một ứng dụng Java có thể biên dịch thành công nhưng vẫn lỗi khi chạy trên một hệ điều hành, kiến trúc CPU, locale hoặc phiên bản driver khác. Để phát hành đáng tin cậy, cần kiểm thử tổ hợp môi trường thực tế mà ứng dụng hỗ trợ, ghi lại chính xác phiên bản từng thành phần và phân biệt lỗi của bytecode Java với lỗi native library hoặc tích hợp bên ngoài.

Ma trận kiểm thử của bài này có bốn trục chính:

1. **Hệ điều hành (OS):** tên, phiên bản, bản cập nhật và môi trường triển khai.
2. **CPU architecture:** x64, AArch64 hoặc kiến trúc khác được JDK và dependency hỗ trợ.
3. **Locale và timezone:** định dạng ngày, số, tiền tệ, collation, parsing và dữ liệu locale của JDK.
4. **Driver version:** phiên bản driver cùng các thành phần phụ thuộc như JDK, server, native client và giao thức.

Đây là hướng dẫn kiểm thử triển khai cho Java 26, không phải một danh sách OS/CPU được bảo đảm cho mọi vendor JDK. Bảng chứng nhận của Oracle chỉ áp dụng cho Oracle JDK; OpenJDK build từ vendor khác có thể có ma trận hỗ trợ riêng.

## 1. Vì sao cần ma trận thay vì chỉ kiểm thử trên máy phát triển?

Java bytecode được thiết kế để chạy trên JVM tương thích, nhưng môi trường chạy còn chứa nhiều thành phần phụ thuộc nền tảng:

- JVM build và native code bên trong JDK.
- JNI, JNA, Foreign Function & Memory API và thư viện native được đóng gói cùng ứng dụng.
- Driver dùng native client, thư viện hệ điều hành hoặc giao thức riêng.
- Locale data, timezone database và cấu hình mặc định của máy.
- File system, đường dẫn, quyền truy cập, encoding và network stack.
- Khác biệt giữa x64 và AArch64 trong JIT, native library và CPU instruction.

Một lần chạy thành công trên Windows x64 không chứng minh ứng dụng hoạt động trên Linux AArch64. Tương tự, kiểm thử locale en-US không phát hiện lỗi khi parsing ngày kiểu dd/MM/yyyy, dấu thập phân, ký hiệu tiền tệ hoặc thứ tự sắp xếp tiếng Việt.

Ma trận giúp xác định rõ tổ hợp nào phải được hỗ trợ, tổ hợp nào cần smoke test và tổ hợp nào được kiểm tra theo cặp rủi ro. Không cần chạy mọi tổ hợp có thể có; cần bảo đảm mọi tổ hợp quan trọng và các điểm giao nhau dễ phát sinh lỗi đều được kiểm tra.

## 2. Phân biệt build compatibility và runtime compatibility

Khi biên dịch Java, javac tạo class file chạy trên JVM. Tùy chọn --release kiểm soát quy tắc ngôn ngữ, API Java/JDK được phép sử dụng và target class file của release đã chọn.

Ví dụ biên dịch bằng JDK 26 cho Java 26:

```bash
javac --release 26 -Xlint:all -d out @sources.txt
```

Nếu sản phẩm cần chạy trên Java 25, biên dịch cho target đó bằng --release 25 nếu release này nằm trong danh sách compiler hỗ trợ:

```bash
javac --release 25 -Xlint:all -d out @sources.txt
```

Không dùng riêng -source và -target để thay thế --release khi cần kiểm tra API tương thích. --release biên dịch theo tập API của release đích, tránh vô tình gọi API chỉ có ở JDK đang cài.

Tuy nhiên, --release **không phải cross-compiler cho OS/CPU**. Nó không tạo sẵn JNI library cho Windows, Linux hay AArch64; cũng không xác nhận driver native có thể được nạp trên máy đích. Một JAR thuần Java có thể dùng chung giữa nhiều nền tảng, nhưng phần native và tích hợp hệ điều hành phải có artifact, cấu hình và kiểm thử riêng.

| Loại kiểm tra | Câu hỏi được trả lời | Công cụ hoặc cách làm |
|---|---|---|
| Compile target | Source dùng đúng ngôn ngữ và API của Java release nào? | javac --release |
| Bytecode compatibility | Class file có target phù hợp JVM đích không? | javap -verbose, kiểm thử trên JVM đích |
| OS compatibility | JVM và dependency có chạy trên OS này không? | Cài JDK đúng vendor/build trên OS thật |
| CPU compatibility | JVM và native library có đúng kiến trúc không? | Chạy trên x64/AArch64 đích |
| Locale compatibility | Formatting, parsing và sorting có đúng không? | Test với locale cụ thể và default locale |
| Driver compatibility | Driver có tương thích JDK, server và native client không? | Vendor compatibility matrix và integration test |

Không coi một lần compile thành công là bằng chứng cho toàn bộ ma trận runtime.

## 3. Ma trận OS và CPU của Oracle JDK 26

Oracle công bố một bảng Certified System Configurations riêng cho từng release. Tại thời điểm đối chiếu, một số cấu hình tiêu biểu của Oracle JDK 26 gồm:

| Hệ điều hành | CPU architecture | Ghi chú |
|---|---|---|
| Windows 11 | x64 | 64-bit JVM |
| Windows Server 2016, 2019, 2022, 2025 | x64 | 64-bit JVM |
| Oracle Linux 8, 9 | x64; một số phiên bản có AArch64 | Một số giới hạn display server theo kiến trúc |
| Oracle Linux 10 | x64, AArch64 | ARM cần kernel UEK đủ phiên bản |
| Red Hat Enterprise Linux 8, 9, 10 | x64; một số phiên bản có AArch64 | Kiểm tra ghi chú X.org/XWayland theo bản OS |
| Ubuntu 24.04 LTS | x64 | Cấu hình được chứng nhận |
| Ubuntu 26.04 LTS | x64 | Được bổ sung từ JDK 26.0.1 |
| SUSE Linux Enterprise Server 15 | x64 | X.org theo ghi chú chứng nhận |
| SUSE Linux Enterprise Server 16 | x64 | Được bổ sung từ JDK 26.0.1 |
| macOS 14 | x64, AArch64 | 64-bit JVM |
| macOS 15 | x64, AArch64 | Oracle chỉ chứng nhận đến macOS 15.6 |
| macOS 26 | AArch64 | Apple Silicon |

Bảng trên là ví dụ từ Oracle JDK 26 Certified System Configurations, không phải cam kết cho mọi OpenJDK distribution. Oracle cũng ghi rõ chỉ JVM 64-bit được chứng nhận. Một OS có thể được hỗ trợ ở x64 nhưng chưa có trong danh sách AArch64, hoặc được bổ sung ở một bản update sau GA.

Khi chọn JDK cho sản phẩm:

1. Xác định vendor JDK sẽ chạy production.
2. Đối chiếu đúng trang supported platforms của vendor đó.
3. Kiểm tra cả phiên bản OS, CPU architecture và các ghi chú kernel/display server.
4. Ghi nhận JDK update/build cụ thể, không chỉ ghi Java 26.
5. Kiểm tra các image container và hypervisor nằm trong phạm vi được vendor hỗ trợ.

Không lấy bảng Oracle để suy ra hỗ trợ của Temurin, Corretto, Microsoft Build of OpenJDK, Azul Zulu hoặc build khác. Các vendor có thể khác nhau về platform certification, patch cadence và native packaging.

## 4. Kiểm tra CPU architecture và native dependencies

Hai máy cùng chạy Linux nhưng khác CPU architecture vẫn có thể cần dependency khác nhau. Ví dụ:

- x64 thường dùng tên kiến trúc amd64 hoặc x86_64.
- ARM 64-bit thường dùng aarch64 hoặc arm64.
- Tên classifier trong Maven artifact có thể khác tên do OS trả về.

Đối với JAR thuần Java, bytecode thường không phụ thuộc CPU. Đối với JNI/JNA, FFM hoặc driver native, binary phải được build cho đúng OS và architecture. Không đổi tên file .so, .dll hoặc .dylib để giả vờ binary thuộc kiến trúc khác.

Ví dụ kiểm tra thông tin runtime trong Java:

```java
public class RuntimePlatform {
    public static void main(String[] args) {
        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("java.vendor = "
                + System.getProperty("java.vendor"));
        System.out.println("os.name = "
                + System.getProperty("os.name"));
        System.out.println("os.version = "
                + System.getProperty("os.version"));
        System.out.println("os.arch = "
                + System.getProperty("os.arch"));
        System.out.println("data.model = "
                + System.getProperty("sun.arch.data.model"));
        System.out.println("runtime = " + Runtime.version());
    }
}
```

Các property này hữu ích để ghi log chẩn đoán, nhưng không phải API chứng nhận platform. Giá trị os.arch phụ thuộc cách JDK/vendor đặt tên; không nên viết logic nghiệp vụ dựa trên một chuỗi architecture duy nhất mà không xử lý alias.

### Khi nào cần chạy native test trên từng kiến trúc?

Chạy trên đúng OS/CPU khi ứng dụng hoặc dependency có một trong các thành phần:

- JNI/JNA hoặc native library đóng gói theo classifier.
- FFM gọi hàm native hoặc thao tác memory layout phụ thuộc ABI.
- Driver cần client library của hệ điều hành.
- Thành phần dùng SIMD/native instruction hoặc tối ưu theo CPU feature.
- Phần mềm cài đặt service, thao tác file lock, signal, process hoặc thiết bị.

Trong ma trận, ghi rõ native artifact đi cùng ứng dụng: tên file, version, checksum, OS, architecture và ABI. Test tối thiểu phải xác nhận thư viện được nạp, gọi được hàm cơ bản, xử lý lỗi và giải phóng tài nguyên đúng cách.

## 5. Locale trong Java 26: dữ liệu và mặc định

Locale ảnh hưởng đến định dạng ngày giờ, số, tiền tệ, tên tháng, tên quốc gia, collation và một số thao tác văn bản. Locale không đồng nghĩa với timezone hoặc charset.

Oracle JDK 26 dùng dữ liệu locale từ CLDR 48 theo mặc định. JDK 26 hỗ trợ ba locale data provider:

- CLDR: dữ liệu từ Unicode Common Locale Data Repository; đây là mặc định.
- HOST: phản ánh tùy chỉnh locale của hệ điều hành. Trong Oracle JDK 26, provider này có trên Windows và macOS.
- SPI: provider do ứng dụng hoặc thư viện triển khai qua java.text.spi và java.util.spi.

Tài liệu Supported Locales của Oracle cũng lưu ý dữ liệu CLDR cho BreakIterator và Collator không được áp dụng theo cách thông thường trong bản JDK này. Nếu ứng dụng phụ thuộc phân đoạn văn bản hoặc sắp xếp ngôn ngữ, hãy kiểm thử riêng các kết quả đó trên đúng JDK 26 thay vì suy ra chỉ từ phiên bản CLDR.

Các provider legacy COMPAT/JRE đã bị loại bỏ. Không xây dựng cấu hình mới dựa trên các provider này. Nếu cần giữ hành vi theo hệ điều hành, có thể cấu hình HOST,CLDR; nếu không đặt property, hành vi mặc định tương đương CLDR.

Ví dụ chọn provider ở lúc khởi chạy:

```bash
java -Djava.locale.providers=CLDR -jar app.jar
```

Hoặc yêu cầu ưu tiên dữ liệu của OS khi provider HOST có sẵn:

```bash
java -Djava.locale.providers=HOST,CLDR -jar app.jar
```

java.locale.providers được đọc và cache khi lớp locale provider được khởi tạo. Vì vậy, cấu hình trên command line/JVM startup là cách đáng tin cậy; không nên thay đổi bằng System.setProperty() sau khi ứng dụng đã bắt đầu dùng locale API.

### Locale data và module jdk.localedata

Trong Oracle JDK 26, java.base chỉ chứa dữ liệu locale tiếng Anh Mỹ và các locale cha, gồm ROOT. Dữ liệu locale khác nằm trong module jdk.localedata. Một JDK đầy đủ thường có module này, nhưng runtime image rút gọn bằng jlink có thể loại bỏ nó.

Ví dụ tạo runtime image chỉ giữ một số locale:

```bash
jlink --add-modules java.base,jdk.localedata --include-locales en,vi,ja -o runtime
```

Danh sách locale thực tế phải được đối chiếu với dữ liệu được hỗ trợ trong JDK và module image. Nếu ứng dụng dùng jlink, kiểm thử chính image đã đóng gói, không chỉ kiểm thử trên JDK developer đầy đủ. Thiếu locale data có thể khiến ứng dụng fallback về locale cha hoặc không có kết quả như mong đợi.

## 6. Thiết kế locale test matrix

Đừng chỉ test locale mặc định của máy CI. Hãy chọn locale theo rủi ro nghiệp vụ:

| Locale | Điều cần kiểm tra |
|---|---|
| vi-VN | Dấu tiếng Việt, định dạng ngày/số và tên tháng |
| en-US | Dấu thập phân là "."; dấu nhóm hàng nghìn là "," |
| de-DE | Dấu thập phân là ","; dấu nhóm hàng nghìn là "." và định dạng tiền tệ |
| ja-JP | Lịch, tên tháng/ngày và dữ liệu locale tiếng Nhật |
| th-TH | Calendar/numbering system theo locale và extension nếu dùng |
| ar-EG | Hướng chữ, chữ số, định dạng ngày và currency |
| Locale.ROOT | Định dạng ổn định cho dữ liệu kỹ thuật và giao thức |

Đây là tập locale mẫu, không phải danh sách bắt buộc cho mọi sản phẩm. Hãy chọn theo thị trường, dữ liệu người dùng và hợp đồng API.

Test nên bao gồm:

- Format rồi parse lại ngày/giờ, số thập phân và tiền tệ.
- Kiểm tra tên tháng, thứ, dấu phân nhóm và dấu thập phân.
- Kiểm tra sorting/collation khi danh sách được sắp xếp theo ngôn ngữ.
- Kiểm tra Unicode và dữ liệu có dấu, không chỉ ASCII.
- Kiểm tra Locale.Category.FORMAT và Locale.Category.DISPLAY nếu ứng dụng dùng hai category riêng.
- Kiểm tra timezone độc lập với locale, nhất là thời điểm chuyển DST.
- Kiểm tra kết quả trên JDK 25 và JDK 26 nếu nâng cấp runtime làm thay đổi CLDR data.

Một ví dụ format có locale tường minh:

```java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleCheck {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2026, 11, 27);

        for (Locale locale : new Locale[] {
                Locale.forLanguageTag("vi-VN"),
                Locale.US,
                Locale.GERMANY,
                Locale.JAPAN
        }) {
            DateTimeFormatter formatter =
                    DateTimeFormatter.ofLocalizedDate(
                            java.time.format.FormatStyle.LONG
                    ).withLocale(locale);

            NumberFormat numberFormat =
                    NumberFormat.getNumberInstance(locale);

            System.out.println(locale.toLanguageTag());
            System.out.println(formatter.format(date));
            System.out.println(numberFormat.format(1234567.89));
        }
    }
}
```

Khi format dữ liệu cho người dùng, truyền locale rõ ràng để kết quả không thay đổi chỉ vì máy chạy ở quốc gia khác. Khi tạo định dạng cho giao thức, log máy đọc hoặc file trao đổi, dùng định dạng chuẩn hóa được giao thức quy định; không dựa vào default locale.

Ví dụ, số trong JSON phải dùng dấu chấm thập phân theo JSON grammar. Không dùng NumberFormat.getInstance() với default locale để serialize số thành chuỗi JSON.

## 7. Tách locale, timezone và charset

Ba thiết lập này thường bị nhầm:

| Thiết lập | Điều khiển | Cách kiểm tra |
|---|---|---|
| Locale | Ngôn ngữ, format ngày/số/tiền tệ, collation | Locale.getDefault() |
| Timezone | Offset và quy tắc giờ địa phương/DST | ZoneId.systemDefault() |
| Charset | Chuyển văn bản thành byte | Charset.defaultCharset() hoặc charset được chỉ định |

Ghi nhận cả ba khi chạy test:

```java
import java.nio.charset.Charset;
import java.time.ZoneId;
import java.util.Locale;

public class RuntimeDefaults {
    public static void main(String[] args) {
        System.out.println("locale.format = "
                + Locale.getDefault(Locale.Category.FORMAT));
        System.out.println("locale.display = "
                + Locale.getDefault(Locale.Category.DISPLAY));
        System.out.println("timezone = " + ZoneId.systemDefault());
        System.out.println("charset = " + Charset.defaultCharset());
    }
}
```

Đừng giả định đổi Locale sẽ đổi timezone. Đừng dùng default charset để trao đổi dữ liệu giữa các hệ thống; chỉ định charset như UTF-8 trong API I/O và giao thức. Nếu cần test timezone, chạy các case riêng với UTC, timezone nghiệp vụ và vùng có DST.

## 8. Phiên bản driver: phải biết chính xác đang kiểm thử loại nào

Trong hệ sinh thái Java, từ driver có thể chỉ nhiều thành phần. Phải ghi rõ loại driver trong ma trận:

- **JDBC driver:** kết nối database; cần kiểm tra JDK, database server và tính năng JDBC được hỗ trợ.
- **JDBC driver có native client:** ngoài JAR còn cần thư viện native theo OS/CPU.
- **Browser/WebDriver:** cần kiểm tra browser, driver và Selenium/client version theo ma trận vendor.
- **GPU, thiết bị hoặc native driver:** cần kiểm tra OS, architecture, ABI và runtime library tương ứng.

Không dùng một ma trận JDBC để kết luận browser driver hoặc native device driver tương thích.

### JDBC Thin và OCI không có cùng phụ thuộc nền tảng

Ví dụ Oracle JDBC:

- JDBC Thin là driver Java thuần, không yêu cầu cài Oracle Client riêng trên máy ứng dụng; cần kết nối TCP/IP đến listener database.
- JDBC OCI cần Oracle Client, Oracle Net và OCI native libraries. Trên Linux cần shared library như libocijdbc*.so; trên Windows cần DLL tương ứng và cấu hình library path.

Do đó, JDBC Thin có thể dùng cùng JAR trên nhiều OS/CPU được hỗ trợ, trong khi OCI phải kiểm tra cả phiên bản native client, OS, architecture và library path. Đây là lý do cần đưa loại driver vào matrix thay vì chỉ ghi version của file JAR.

### Không nhầm driver major version với JDK major version

Số 26 trong tên dòng driver hoặc database không tự động có nghĩa driver được chứng nhận chạy trên JDK 26. Tài liệu Oracle Database 26 phân biệt riêng:

1. Ma trận phiên bản JDBC driver với phiên bản database server.
2. Ma trận JAR driver với các JDK được hỗ trợ.

Trong bảng tài liệu được tham chiếu, dòng JDBC 26.x được liệt kê tương thích với database 26.x, 21.x và 19.x; bảng JAR/JDK lại liệt kê cụ thể các JDK được hỗ trợ cho ojdbc17.jar, ojdbc11.jar và ojdbc8.jar. Vì vậy, hãy đọc đúng bảng JDK compatibility của artifact driver đang dùng và release notes mới nhất; không suy ra JDK support từ số phiên bản driver hoặc database.

Ví dụ, bảng JAR/JDK trong tài liệu Oracle được dẫn ở đây liệt kê ojdbc17.jar cho JDK 17, 19 và 21; bảng đó không liệt kê JDK 26. Không được tự suy ra chứng nhận JDK 26 từ tên JDBC 26.x. Hãy kiểm tra tài liệu của bản driver mới nhất mà dự án thực sự triển khai và yêu cầu vendor xác nhận nếu JDK 26 chưa xuất hiện trong compatibility matrix.

## 9. Xác minh phiên bản driver lúc chạy

Không chỉ dựa vào tên dependency trong file build. Có thể đọc metadata từ JDBC connection:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class JdbcVersionInfo {
    public static void printJdbcVersions(Connection connection)
            throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();

        System.out.println("driver = " + metadata.getDriverName());
        System.out.println("driver.version = " + metadata.getDriverVersion());
        System.out.println("driver.major = " + metadata.getDriverMajorVersion());
        System.out.println("driver.minor = " + metadata.getDriverMinorVersion());
        System.out.println("database = " + metadata.getDatabaseProductName());
        System.out.println("database.version = "
                + metadata.getDatabaseProductVersion());
    }
}
```

Ghi lại ít nhất:

- Driver name, version và major/minor version.
- Database product name và server version.
- JDK vendor, version và build.
- OS, OS version và CPU architecture.
- Loại kết nối Thin/OCI hoặc mode native tương ứng.
- TLS version, authentication mechanism và các extension được ứng dụng sử dụng.

Nếu dependency có nhiều bản cùng tồn tại trên classpath, metadata runtime giúp phát hiện driver thực sự được nạp. Có thể kiểm tra thêm nguồn class bằng Class.getProtectionDomain().getCodeSource() trong môi trường chẩn đoán, nhưng không nên phụ thuộc vào đường dẫn file JAR trong logic nghiệp vụ.

## 10. Xây dựng ma trận driver test

Với JDBC, các trục tối thiểu nên gồm:

| Trục | Ví dụ giá trị | Câu hỏi cần xác nhận |
|---|---|---|
| JDK | JDK 26 update/build được hỗ trợ | Driver có hỗ trợ release JDK này không? |
| Driver artifact | Phiên bản JAR cụ thể | Đây có phải artifact được vendor khuyến nghị/certified không? |
| Database server | Các phiên bản server còn được hỗ trợ | Driver và server có tương thích không? |
| OS/CPU | Windows x64, Linux x64, Linux AArch64 | Có native client hoặc dependency platform-specific không? |
| Connection mode | Thin, OCI hoặc native mode | Cần client libraries và biến môi trường nào? |
| TLS/authentication | TLS config, wallet, Kerberos hoặc cơ chế thực tế | Handshake và xác thực có hoạt động không? |
| Feature usage | Batch, LOB, JSON, generated keys, stored procedure | Các tính năng ứng dụng dùng có được hỗ trợ không? |

Không nhất thiết kiểm thử mọi driver version lịch sử. Chọn tối thiểu:

- Phiên bản thấp nhất còn được sản phẩm hỗ trợ.
- Phiên bản khuyến nghị hoặc hiện hành đã được phê duyệt.
- Phiên bản mới đang được đánh giá trước khi nâng cấp.
- Phiên bản cũ cần duy trì cho khách hàng đang triển khai, nếu có.

Khi nâng driver, chạy integration test với database server thật hoặc môi trường tương đương. Unit test mock JDBC không thể xác nhận TLS, authentication, wire protocol, transaction semantics hoặc native library loading.

## 11. Thiết kế ma trận OS × CPU × Locale × Driver

Ma trận đầy đủ có thể bùng nổ tổ hợp. Ví dụ 4 OS, 2 architecture, 5 locale và 3 driver version đã tạo 120 tổ hợp trước khi tính thêm JDK build và database version.

Dùng phân tầng:

**Tier 1 – Release blocking**

- Tất cả OS/CPU được công bố hỗ trợ chính thức.
- JDK vendor/build dùng trong production.
- Locale của thị trường chính và locale ROOT.
- Driver version được phê duyệt cho production.
- Native dependencies phải chạy được trên từng target architecture.

**Tier 2 – Compatibility**

- Các OS version còn trong vòng hỗ trợ.
- Locale bổ sung theo thị trường.
- Driver version thấp nhất còn hỗ trợ và phiên bản mới đang đánh giá.
- JDK update/build kế tiếp trước khi rollout.

**Tier 3 – Pairwise hoặc scheduled**

- Các tổ hợp ít phổ biến nhưng vẫn được hỗ trợ.
- Locale và OS không thường xuất hiện cùng nhau.
- Driver/database combinations ít dùng.
- Chạy định kỳ hoặc trước một release lớn.

Pairwise testing giúp giảm số tổ hợp nhưng không thay thế kiểm thử các tổ hợp rủi ro cao đã biết. Ví dụ, nếu OCI chỉ có native library trên Linux x64 và Windows x64, phải test riêng cả hai nền tảng; không thể lấy một kết quả pairwise bất kỳ làm bằng chứng cho architecture còn lại.

Ví dụ ma trận nhỏ:

| Job | OS | CPU | JDK | Locale | Driver |
|---|---|---|---|---|---|
| A | Windows 11 | x64 | JDK 26 | vi-VN, en-US | JDBC Thin production |
| B | Linux RHEL 9 | x64 | JDK 26 | vi-VN, de-DE | JDBC Thin production |
| C | Linux RHEL 9 | AArch64 | JDK 26 | en-US | JDBC Thin production |
| D | macOS 14 | AArch64 | JDK 26 | ja-JP | Driver/dev integration |
| E | Linux RHEL 9 | x64 | JDK 26 | vi-VN | OCI + đúng Oracle Client |
| F | Windows 11 | x64 | JDK 26 | en-US | OCI + đúng Oracle Client |

Đây là ví dụ thiết kế, không phải khẳng định tất cả các tổ hợp trong bảng đều nằm trong một chứng nhận chung. Trước khi dùng làm release gate, kiểm tra từng OS/CPU với ma trận chứng nhận của vendor JDK và driver.

## 12. Kiểm thử compile, smoke và integration

Một pipeline tốt tách ba loại test:

### Compile test

Xác nhận source, API và dependency compile với target Java dự kiến:

```bash
javac --release 26 -Xlint:all -d out @sources.txt
```

Nếu dùng Maven/Gradle, cấu hình toolchain và release target nhất quán; khóa phiên bản plugin/compiler và dependency để các job không tự resolve những phiên bản khác nhau.

### Runtime smoke test

Chạy trên từng OS/CPU mục tiêu:

- JVM khởi động được.
- Classpath/module path và native libraries được nạp.
- Locale, timezone và charset được ghi nhận đúng.
- File access, process creation, socket và TLS cơ bản hoạt động.
- Ứng dụng có thể start, health check và shutdown.

### Integration test

Chạy các luồng tích hợp thật:

- Kết nối database bằng driver đúng version.
- Xác thực, query, transaction commit/rollback.
- Prepared statement, batch, LOB/JSON hoặc stored procedure nếu ứng dụng dùng.
- TLS, certificate, wallet và connection pool.
- Parsing/formatting dữ liệu theo locale của thị trường.
- Đọc/ghi file có Unicode và đường dẫn theo OS.
- Native library calls và xử lý lỗi trên từng architecture.

Một compile job không thay cho smoke test; smoke test không thay cho integration test.

## 13. Lưu lại fingerprint môi trường để tái lập lỗi

Mỗi kết quả CI cần lưu metadata của môi trường. Nếu không biết chính xác JDK, driver và locale đang chạy, rất khó tái hiện lỗi khác biệt giữa developer, CI và production.

Nên ghi:

```text
JDK vendor/version/build
OS name/version
CPU architecture
Container image digest
Locale FORMAT/DISPLAY
Timezone
Default charset
Driver artifact/version
Database product/version
Native client version
Test suite commit/build id
```

Không ghi password, access token, JDBC URL có credential hoặc thông tin kết nối nhạy cảm vào artifact CI. Chỉ ghi tên service, loại driver, phiên bản và metadata cần cho chẩn đoán.

Với container, pin image theo immutable digest khi cần tái lập chính xác. Tag như latest hoặc jdk26 có thể trỏ sang image khác sau này. Với driver, khóa dependency version và checksum theo quy trình quản lý artifact của tổ chức.

## 14. Những thay đổi cần chạy lại ma trận

| Thay đổi | Kiểm thử cần chạy lại |
|---|---|
| Nâng JDK 26 update/build | Compile, smoke, locale, driver integration và native tests |
| Đổi JDK vendor | Toàn bộ runtime compatibility matrix quan trọng |
| Chuyển x64 sang AArch64 | Native libraries, driver native, performance smoke và integration |
| Nâng OS hoặc base container image | Smoke, file/process/network/TLS và native library loading |
| Nâng JDBC driver | JDK/database compatibility, query, transaction, TLS và connection pool |
| Nâng database server | Driver/server interoperability và feature integration |
| Đổi locale provider hoặc java.locale.providers | Formatting, parsing, collation và default locale |
| Dùng jlink image mới | Locale modules, service providers, native modules và startup |
| Thay native client hoặc shared library | Load/link, ABI, integration và shutdown |
| Thay timezone database hoặc OS locale config | Date/time, DST và locale-dependent tests |

Không chạy lại toàn bộ test chỉ vì một thay đổi không liên quan, nhưng phải chạy lại các giao điểm mà thay đổi có thể ảnh hưởng. Ví dụ nâng JDBC OCI client cần kiểm tra OS/CPU native matrix; nâng locale data cần chạy lại locale tests trên runtime image thực tế.

## 15. Checklist trước khi phát hành

- [ ] Đã xác định vendor và build JDK 26 dùng trong production.
- [ ] Đã đối chiếu OS và CPU với supported/certified configurations của đúng vendor.
- [ ] Đã phân biệt compile target --release với runtime OS/CPU test.
- [ ] Đã xác nhận native library có artifact cho mọi kiến trúc mục tiêu.
- [ ] Đã xác định locale provider, locale data và module jdk.localedata.
- [ ] Đã kiểm thử locale thị trường, Locale.ROOT, timezone và charset độc lập.
- [ ] Đã bỏ cấu hình dựa trên provider locale legacy COMPAT/JRE.
- [ ] Đã ghi rõ loại driver: JDBC Thin, OCI, browser, GPU hoặc native driver.
- [ ] Đã xác minh phiên bản driver thực tế lúc chạy.
- [ ] Đã kiểm tra ma trận driver với JDK, database/server, OS và CPU.
- [ ] Đã kiểm thử integration trên môi trường thật hoặc tương đương production.
- [ ] Đã lưu fingerprint môi trường và artifact version cho mỗi CI job.
- [ ] Đã xác định test nào phải chạy lại khi nâng JDK, OS, locale hoặc driver.

## Tài liệu tham chiếu

1. [Oracle JDK 26 Certified System Configurations](https://www.oracle.com/java/technologies/javase/products-doc-jdk26certconfig.html)
2. [Oracle JDK 26 Supported Locales](https://www.oracle.com/java/technologies/javase/jdk26-supported-locales.html)
3. [Oracle Java SE 26 – LocaleServiceProvider API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/LocaleServiceProvider.html)
4. [Oracle Java SE 26 – javac Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
5. [Oracle Database 26 – JDBC Getting Started and Compatibility](https://docs.oracle.com/en/database/oracle/oracle-database/26/jjdbc/JDBC-getting-started.html)
6. [Oracle Java SE 26 – Internationalization Overview](https://docs.oracle.com/en/java/javase/26/intl/internationalization-overview.html)

