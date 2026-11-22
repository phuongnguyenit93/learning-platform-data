# Đọc thay đổi hành vi trong tài liệu của JDK đang sử dụng

## 1. Vì sao phải đọc tài liệu theo đúng phiên bản JDK?

Java có cam kết tương thích mạnh, nhưng **biên dịch thành công không có nghĩa hành vi lúc chạy hoàn toàn giống giữa các JDK**. Khi đổi JDK để build, chạy ứng dụng, kiểm thử hoặc triển khai, một số thay đổi có thể tác động đến giá trị mặc định, bảo mật, bộ thư viện chuẩn, phản chiếu (*reflection*), cấu hình JVM, kết quả đọc/ghi dữ liệu và phần mềm phụ thuộc.

Ví dụ: ứng dụng biên dịch hợp lệ với API Java 15 vẫn có thể chạy khác trên JDK 17 hoặc JDK 21 vì môi trường thực thi đã đổi. Muốn xác định chính xác ảnh hưởng, phải đọc **tài liệu của JDK nguồn, các bản phát hành đi qua và JDK đích thực sự được dùng**, rồi kiểm tra trên môi trường chạy thật.

Mục tiêu của bài này là hình thành quy trình trả lời được năm câu hỏi:

1. Chương trình **đang được build và chạy bởi bản JDK nào** (major, update, vendor, cấu hình)?
2. Thông tin nào trong tài liệu là **tính năng mới**, **thay đổi hành vi**, **cảnh báo**, **API bị ngừng khuyến nghị**, **API bị xóa** hay **thay đổi bảo mật**?
3. Thay đổi đó tác động đến **mã nguồn, file `.class`, lúc chạy, công cụ build, thư viện thứ ba hay hệ thống triển khai**?
4. Những điều kiện nào kích hoạt thay đổi; đã có bằng chứng chương trình của mình phụ thuộc vào hành vi cũ chưa?
5. Cần sửa và kiểm thử thế nào, tiêu chí nào xác nhận phiên bản JDK mới hoạt động đúng?

Đây là kỹ năng dùng được với Java 15 cũng như các JDK hiện nay. Không coi tài liệu của một JDK bất kỳ là mô tả mặc định cho mọi JDK khác.

## 2. Xác định chính xác “JDK đang sử dụng”

Một dự án có thể đồng thời dùng: JDK chạy IDE, JDK chạy Maven/Gradle, JDK mà compiler dùng để tạo `.class`, và JDK trong container/server production. **Bốn nơi có thể khác nhau.**

Tại terminal dùng để build hoặc chạy, kiểm tra:

```bash
java --version
javac --version
java -XshowSettings:properties -version
```

`java --version` cho biết runtime do lệnh `java` hiện tại gọi; `javac --version` cho biết compiler hiện tại. Lệnh thứ ba cho biết các system properties như `java.home`, `java.version`, `java.vendor`, `file.encoding` và `java.class.path` nếu có. Một số thông tin của `-XshowSettings` được in ra standard error.

Trong dự án dùng công cụ build, kiểm tra chính công cụ đó:

```bash
mvn --version
```

hoặc, với dự án Gradle có wrapper:

```bash
./gradlew --version
```

Trên Windows PowerShell, thường dùng `.\gradlew.bat --version`. Cần xem thêm cấu hình **Maven Toolchains** hoặc **Gradle Java Toolchains** nếu dự án có dùng, vì JDK chạy công cụ build và JDK được chọn để biên dịch/test có thể khác nhau. Khi chạy trong Docker/CI, thực hiện kiểm tra **bên trong container hoặc job**; kết quả trên máy cá nhân không đại diện cho môi trường triển khai.

Ghi lại tối thiểu:

| Thông tin | Dùng để xác định |
| --- | --- |
| JDK major/update/build | Mốc tài liệu, lỗi đã được sửa trong các bản vá, mức hỗ trợ. |
| Vendor/distribution | Release notes và bản vá phụ thuộc nhà cung cấp, nếu có. |
| JDK dùng cho compile | Cú pháp, API được compiler kiểm tra và dạng class file sinh ra. |
| `--release` hoặc cấu hình target | Phiên bản Java tối thiểu mà binary hướng tới. |
| JDK chạy unit/integration test | Hành vi thực tế mà test đã quan sát. |
| JDK chạy production | Hành vi đang ảnh hưởng người dùng. |
| OS, locale, charset, múi giờ, JVM flags | Những biến môi trường có thể tạo khác biệt giữa hai lần chạy. |

**Chú ý `javac --release`:** `javac --release 15` (nếu compiler đó còn hỗ trợ release 15) yêu cầu cú pháp, dạng class file và **API công khai được hỗ trợ** theo Java 15. Nó không tái tạo các mặc định hoặc cách xử lý runtime của JDK 15 khi ứng dụng chạy trên JDK mới. `--release` khác với chỉ đặt `-source`/`-target`; xem danh sách release được compiler hỗ trợ bằng `javac --help`.

## 3. Chọn đúng nguồn tài liệu chính thức

Khi gặp từ “behavior change”, **đừng chỉ đọc danh sách tính năng mới**. Nhiều thay đổi gây hỏng ứng dụng nằm trong migration guide, release notes, security notes hoặc phần cảnh báo của một API.

| Nguồn | Trả lời câu hỏi nào? | Cần đọc phần nào? |
| --- | --- | --- |
| **JDK Release Notes** của từng phiên bản và bản vá | Bản phát hành này thay đổi hoặc sửa gì? | Compatibility, behavioral changes, noteworthy issues, known issues, security, removed/deprecated options. |
| **JDK Migration Guide** của JDK đích | Cần làm gì khi nâng JDK? | Significant Changes, Removed APIs/Tools, Security Updates, Preparing for Migration. |
| **Java API Documentation** đúng phiên bản | Phương thức/lớp có contract gì? | Mô tả hành vi, parameter, exception, `@since`, `@Deprecated`, `forRemoval`, liên kết `See Also`. |
| **JDK Tool Specifications** | Flag của `java`, `javac`, `jar`, `jdeps`, `jdeprscan` hoạt động thế nào? | Option semantics, mặc định, tương tác giữa tùy chọn, lỗi khi dùng sai. |
| **OpenJDK JEP** | Lý do thiết kế, phạm vi và các điểm đổi lớn là gì? | Summary, Goals, Non-Goals, Motivation, Description, Compatibility/Risks, phiên bản phát hành. |
| **JDK bug tracker / change record** khi cần | Một lỗi cụ thể đã được sửa hoặc đưa vào bản vá nào? | Issue ID, affected/fix versions, mô tả và điều kiện tái hiện; kiểm tra lại với release notes của bản đang chạy. |
| **Release notes của vendor và thư viện/framework** | Bản phân phối hoặc thư viện hiện tại có thay đổi riêng gì? | Phiên bản tương thích, yêu cầu tối thiểu, cấu hình được hỗ trợ, các bản vá. |

Cách truy cập đáng tin cậy là mở [trang tài liệu Java SE theo phiên bản](https://docs.oracle.com/en/java/javase/index.html), chọn **đúng phiên bản mục tiêu**, rồi đi đến **Release Notes**, **Migration Guide**, **API Specification** hoặc **Tool Specifications**. Với JDK 27 có thể bắt đầu tại [JDK 27 Documentation](https://docs.oracle.com/en/java/javase/27/) và [JDK 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/index.html). Khi dự án vẫn chạy JDK 17 hay 21, phải mở tài liệu của phiên bản đó và các bản cập nhật liên quan, không mặc định lấy JDK 27 thay thế.

Một thay đổi chuyển từ JDK 15 sang JDK 21 có thể xuất hiện ở JDK 16, 17, 18, 19, 20 hoặc 21. **Đọc cả các mốc nằm giữa**; chỉ so hai trang “What's New” đầu và cuối dễ bỏ sót một thay đổi runtime.

### Đọc một entry theo sáu trường

Đối với mỗi mục nghi vấn, ghi ra:

1. **Version/scope:** thay đổi xuất hiện ở JDK major nào hoặc update nào; áp dụng cho OS, kiến trúc, module, provider, cấu hình nào?
2. **Before:** trước đây chương trình được tài liệu mô tả hoạt động thế nào?
3. **After:** hành vi mới là gì? Có thay đổi default, exception, thứ tự, dữ liệu, lỗi hay log không?
4. **Trigger:** điều kiện kích hoạt là gì? Có cần gọi API cũ, phản chiếu sâu, format đặc biệt, certificate hoặc JVM flag cụ thể không?
5. **Impact:** ứng dụng của mình có phụ thuộc trực tiếp/gián tiếp không; kết quả đúng kỳ vọng của nghiệp vụ có đổi không?
6. **Action/evidence:** sửa ở đâu; cần chạy test gì; log, kết quả thử nghiệm hoặc link nào chứng minh đã xử lý?

**Đừng suy ra hành vi từ tiêu đề JEP.** Một JEP có thể giới thiệu preview/incubator API, đổi chi tiết implementation hoặc chỉ chuẩn bị cho hạn chế ở tương lai. Cần đọc trạng thái của tính năng, thời điểm tích hợp vào JDK và nội dung giải thích. Tương tự, chữ “deprecated” không đồng nghĩa “đã bị xóa”; “deprecated for removal” nghĩa là có dự định xóa ở bản tương lai nhưng phải xác nhận tình trạng thực tế tại phiên bản đích.

## 4. Phân loại loại thay đổi để khỏi sửa sai chỗ

| Loại | Dấu hiệu và ví dụ | Kiểm tra phù hợp |
| --- | --- | --- |
| **Source compatibility** | Cú pháp/kiểm tra compiler/API công khai đổi, mã nguồn không còn biên dịch. | Build lại bằng compiler/cấu hình thực dùng; kiểm tra diagnostics. |
| **Binary compatibility** | `.class`/JAR đã build gặp `UnsupportedClassVersionError`, `NoSuchMethodError`, `NoClassDefFoundError` hoặc `IllegalAccessError`. | Chạy chính artifact đã đóng gói trên JDK đích, kiểm tra classpath/module path và thư viện. |
| **Behavioral compatibility** | Cùng API nhưng kết quả, default encoding, locale, exception, ordering hoặc timeout khác. | Test cùng input trên JDK cũ và mới, ghi rõ biến môi trường. |
| **Access/encapsulation** | Thư viện dùng reflection vào phần không công khai của JDK và gặp `InaccessibleObjectException`. | Xác định code/library gây truy cập; cập nhật thư viện hoặc chuyển sang API hỗ trợ. |
| **Security compatibility** | TLS, truststore, certificate, algorithm constraints, signature/provider đổi. | Integration test thực với peer, certificate, security properties và runtime đích. |
| **Tool/packaging** | Lệnh/flag JVM không còn được chấp nhận; build plugin/annotation processor không tương thích. | Chạy CI build, packaging, startup script trên chính toolchain đích. |
| **Performance/resource** | GC, JIT, memory, CPU, latency hoặc cấu hình mặc định thay đổi. | Benchmark/quan sát có tải đại diện, tách khỏi khác biệt phần cứng. |

Không vội áp dụng cách sửa như `--add-opens`, đổi JVM flags hoặc khóa encoding khi chưa biết **trigger**. Một workaround có thể chỉ che dấu lỗi thực sự và khiến nâng cấp sau khó hơn.

## 5. Ví dụ đọc tài liệu: thay đổi default charset từ JDK 18

Đây là ví dụ điển hình của **thay đổi hành vi**, không nhất thiết là lỗi compile.

- **Nguồn:** [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400) và phần Default Charset trong [Oracle JDK Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- **Trước JDK 18:** charset mặc định có thể phụ thuộc hệ điều hành và locale. Ví dụ trên một số máy Windows trước đây có thể là Windows code page thay vì UTF-8.
- **Từ JDK 18:** default charset của các API Java SE liên quan được chuẩn hóa là UTF-8. Có các tùy chọn tương thích được tài liệu mô tả, chẳng hạn `-Dfile.encoding=COMPAT`, nên không được bỏ qua cấu hình lúc chạy.
- **Trigger:** dùng API đọc/ghi text mà không chỉ định charset; hành vi sẽ lộ rõ khi dữ liệu chứa ký tự ngoài ASCII, khi máy cũ có charset mặc định khác UTF-8.
- **Hệ quả:** cùng một file có thể được giải mã/ghi khác khi chạy ứng dụng trên các JDK hoặc hệ điều hành khác nhau.
- **Cách xử lý lâu dài:** ghi rõ encoding tại ranh giới dữ liệu, ví dụ `StandardCharsets.UTF_8`, và kiểm thử file/network payload có tiếng Việt.

Lưu ý: **không được khẳng định “trên JDK 15 luôn dùng Windows-1252”**. JDK 15 trên máy đang dùng UTF-8 có thể đã cho cùng kết quả với JDK 18+. Phải đo `Charset.defaultCharset()` trên môi trường thực.

## 6. Ví dụ đọc tài liệu: strong encapsulation từ JDK 17

Đây là thay đổi liên quan **quyền truy cập**, thường ảnh hưởng thư viện dùng reflection.

- **Nguồn:** [Oracle JDK Migration Guide — Strong Encapsulation](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html) và [OpenJDK JEP 403](https://openjdk.org/jeps/403).
- **Thay đổi:** JDK 17 áp dụng strong encapsulation với nhiều phần nội bộ của JDK. Mã cố mở field/method không công khai của module JDK qua deep reflection có thể nhận `java.lang.reflect.InaccessibleObjectException` thay vì hoạt động với cảnh báo như ở một số bản trước đó.
- **Trigger:** một thư viện serialization, bytecode, test hoặc chính mã ứng dụng dùng reflection đến thành phần không được `opens` cho module gọi.
- **Cách đọc stack trace:** tìm tên module/package bị từ chối và code gọi `setAccessible(...)`, rồi truy ra phiên bản thư viện.
- **Hành động:** cập nhật thư viện sang bản tương thích và dùng API công khai. `--add-opens` cho một package cụ thể có thể là biện pháp chuyển tiếp trong tình huống được kiểm soát, nhưng không biến API nội bộ thành API có contract được hỗ trợ.

Đừng đánh đồng thay đổi ở JDK 17 với “mọi reflection đều hỏng”: reflection trên API công khai và module mở phù hợp vẫn hoạt động. Cần xác định chính xác thành phần bị truy cập.

## 7. Thực hành: lập bằng chứng hành vi trên JDK thực tế

Ví dụ Java bên dưới cố ý in **thông tin runtime** và thực hiện hai cách giải mã cùng một dãy byte: theo default charset, và theo UTF-8 chỉ định tường minh. Kết quả sẽ giúp phát hiện liệu môi trường có phụ thuộc charset không được khai báo hay không.

Lưu thành tệp **`JdkBehaviorProbe.java`**:

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.time.ZoneId;
import java.util.Arrays;
import java.util.Locale;

public class JdkBehaviorProbe {
    public static void main(String[] args) {
        byte[] euroUtf8 = {
                (byte) 0xE2, (byte) 0x82, (byte) 0xAC
        };

        String implicit = new String(euroUtf8);
        String explicit = new String(euroUtf8, StandardCharsets.UTF_8);

        System.out.println("Runtime feature: " + Runtime.version().feature());
        System.out.println("Runtime version: "
                + System.getProperty("java.runtime.version"));
        System.out.println("Vendor: " + System.getProperty("java.vendor"));
        System.out.println("Default charset: "
                + Charset.defaultCharset().name());
        System.out.println("Default locale: "
                + Locale.getDefault().toLanguageTag());
        System.out.println("Default time zone: "
                + ZoneId.systemDefault().getId());
        System.out.println("Implicit equals UTF-8: "
                + implicit.equals(explicit));
        System.out.println("UTF-8 bytes: "
                + Arrays.toString("€".getBytes(StandardCharsets.UTF_8)));
    }
}
```

`new String(euroUtf8)` là **trường hợp cần phát hiện**, không phải cách được khuyên dùng trong code production. `new String(euroUtf8, StandardCharsets.UTF_8)` thể hiện lựa chọn encoding rõ ràng, ổn định qua các JDK có hỗ trợ UTF-8.

Biên dịch và chạy trên JDK 17+ với terminal đặt ở thư mục chứa file:

```bash
javac --release 17 -encoding UTF-8 JdkBehaviorProbe.java
java JdkBehaviorProbe
```

Kết quả gồm các dòng dạng:

```text
Runtime feature: <số major của JDK đang chạy>
Runtime version: <chuỗi phiên bản đầy đủ>
Vendor: <nhà cung cấp runtime>
Default charset: <charset thực tế>
Default locale: <locale thực tế>
Default time zone: <múi giờ thực tế>
Implicit equals UTF-8: <true hoặc false>
UTF-8 bytes: [-30, -126, -84]
```

Các giá trị trong dấu ngoặc nhọn **mô tả trường phụ thuộc môi trường**, không phải stdout cố định. Dòng `UTF-8 bytes: [-30, -126, -84]` là kết quả cố định của chuỗi `€` khi mã hóa bằng UTF-8. Khi `Charset.defaultCharset()` là UTF-8, dòng `Implicit equals UTF-8: true`; nếu mặc định khác và giải mã dãy byte thành ký tự khác, kết quả sẽ là `false`.

Để so sánh đúng, chạy **cùng mã nguồn, input và test** trên các JDK được kiểm thử (ví dụ JDK 17 và 21 hoặc JDK 21 và 27), lưu đầu ra từng lần kèm `java --version`. Nếu chỉ thay đổi máy mà không cố định locale, timezone, OS và charset, chưa thể kết luận nguyên nhân thuộc JDK.

Với ứng dụng thực, hãy thêm integration test đọc một tệp UTF-8 có tiếng Việt, rồi ghi lại và so byte đầu ra; kiểm tra đồng thời kết quả nghiệp vụ, không chỉ dòng `java --version`.

### Cách viết kết luận đúng từ kết quả

- **Tài liệu:** “JDK 18 chuyển default charset sang UTF-8.”
- **Điều kiện:** “Mã hiện dùng constructor chuỗi không truyền `Charset` và dữ liệu chứa byte ngoài ASCII.”
- **Bằng chứng:** “Máy A/JDK cũ cho `Charset.defaultCharset()` khác UTF-8, máy B/JDK mới cho UTF-8; test giải mã cùng input tạo chuỗi khác.”
- **Kết luận:** “Ứng dụng đang phụ thuộc default charset; chuyển sang UTF-8 tường minh và kiểm thử ngược dữ liệu đã lưu.”
- **Không kết luận:** “Mọi ứng dụng Java 15 sẽ hỏng encoding khi nâng JDK.”

## 8. Dùng công cụ hỗ trợ rà soát tương thích

Tài liệu cho biết **có thể thay đổi điều gì**; công cụ phân tích cho biết **mã và binary của mình có dấu hiệu phụ thuộc vào đâu**. Đây là công cụ hỗ trợ, không thay thế chạy test.

### `javac --release` và compiler warnings

Kiểm tra compiler và những release mà nó hỗ trợ:

```bash
javac --version
javac --help
```

Với source của ví dụ trên:

```bash
javac --release 17 -Xlint:deprecation -encoding UTF-8 JdkBehaviorProbe.java
```

`--release` kiểm tra API/cú pháp mục tiêu; `-Xlint:deprecation` cảnh báo các API đánh dấu deprecated trong mã được biên dịch. **Không kỳ vọng** compiler phát hiện mọi thay đổi runtime hay dependency được nạp động.

### `jdeps` — phát hiện dùng JDK-internal APIs

Với một JAR ứng dụng giả định tên `application.jar` đã được build:

```bash
jdeps --jdk-internals application.jar
```

Lệnh phân tích quan hệ phụ thuộc ở bytecode tới internal APIs của JDK. Nếu chưa tìm thấy các dependency khác, cần cung cấp classpath/module path phù hợp rồi chạy lại. `jdeps` không thấy chắc chắn các đường gọi hình thành qua `Class.forName(...)`, reflection chuỗi hay code chỉ được nạp khi runtime; vì vậy **không có kết quả không đồng nghĩa an toàn tuyệt đối**.

### `jdeprscan` — rà soát API deprecated

```bash
jdeprscan --for-removal application.jar
```

Lệnh kiểm tra tham chiếu đến API Java SE đã đánh dấu deprecated for removal theo dữ liệu của tool, giúp tìm việc cần ưu tiên di chuyển. Sử dụng `jdeprscan --help` trên JDK đang chạy để xem tùy chọn và phiên bản `--release` thực sự hỗ trợ. Nó không thay thế danh sách **Removed APIs** của Migration Guide, vì API đã xóa hoặc dependency thiếu có thể tạo vấn đề khác.

### Binary và runtime thực

Sau khi đóng gói artifact, chạy **chính JAR/container image được dùng triển khai** với JDK mục tiêu. Ghi lại startup logs, warnings, exception, HTTP/TLS integration, đọc/ghi dữ liệu và các test hành vi. Đừng xem `javac --release 17` là bằng chứng artifact đã chạy thành công trên JDK 17.

## 9. Quy trình đánh giá nâng JDK trong dự án thật

### Bước 1 — Chốt hai mốc và môi trường

Ghi rõ JDK hiện tại và JDK muốn chuyển tới, gồm major/update/vendor và JDK của CI/production. Xác nhận toolchain build, IDE, test và JVM chạy production. Chọn một artifact cố định để đo.

### Bước 2 — Đọc changelog qua toàn bộ các mốc liên quan

Mở tài liệu phiên bản đích và lần lượt đọc Release Notes/Migration Guide của các major/update đi qua. Ưu tiên **behavior change, security, removed/deprecated APIs, JVM flags và tool compatibility**. Đọc JEP/API docs khi cần hiểu chi tiết. Xác định change ID và link chính thức cho từng rủi ro.

### Bước 3 — Lọc theo mức độ ảnh hưởng

Lập bảng đơn giản:

| Change | Điều kiện chạm | Evidence hiện có | Action |
| --- | --- | --- | --- |
| Default charset (JDK 18) | File/text không chỉ định encoding | Probe + test tiếng Việt | Thêm charset tường minh, test byte. |
| Strong encapsulation (JDK 17) | Thư viện dùng deep reflection vào JDK | Stack trace + bản thư viện | Update thư viện, dùng API hỗ trợ. |
| TLS/certificate/security policy | Kết nối đến peer có cấu hình cũ | TLS handshake, cert chain, log | Sửa cấu hình/certificate ở bên phù hợp, test lại. |
| JVM options/GC defaults | Script truyền flag hoặc đặt giới hạn tài nguyên | Startup output, flags, telemetry | Bỏ/sửa flag đã đổi, chạy performance test. |

Đây là **mẫu cách điều tra**, không phải kết luận tất cả thay đổi đều ảnh hưởng mọi chương trình.

### Bước 4 — Tái hiện bằng cùng một phép thử

Dùng cùng input, dependency, classpath/module path và cấu hình ứng dụng; thay duy nhất JDK khi có thể. Chạy unit test, integration test, kiểm tra packaging và khởi động. Với lỗi có tính môi trường, cố định locale, timezone, encoding, OS và JVM flags hoặc ghi rõ phần nào không giữ được giống nhau.

Để đánh giá bản vá JDK cùng major, cũng đọc release notes **đúng số update**: bản vá bảo mật hoặc bug fix có thể thay đổi cách kiểm tra dữ liệu, xác thực hoặc lỗi trả về dù API không đổi.

### Bước 5 — Sửa nguyên nhân và xác nhận

- Cập nhật dependency hoặc dùng API công khai khi JDK thay đổi quyền truy cập.
- Chỉ định charset, locale hoặc timezone rõ ràng ở ranh giới dữ liệu nếu hợp đồng ứng dụng cần kết quả cố định.
- Kiểm thử end-to-end cho TLS, serialization, database driver, file encoding và native integration có dùng.
- Chỉnh các JVM flags theo tool spec của JDK đích; tránh giữ workaround không còn cần.
- Thử nghiệm hiệu năng/tiêu thụ bộ nhớ trên tải đại diện sau khi kiểm tra correctness.
- Ghi nhận test đã PASS/FAIL trên JDK đích, bao gồm đường dẫn tài liệu đã đọc.

**Nguyên tắc:** tài liệu mô tả hợp đồng/hành vi theo điều kiện; test trên JDK mục tiêu xác nhận chương trình của mình thực sự gặp hay không gặp điều kiện đó.

## 10. Phân biệt các cảnh báo thường bị hiểu nhầm

**“Release notes nói đã sửa lỗi” không đồng nghĩa “ứng dụng sẽ đổi hành vi”.** Phải đối chiếu điều kiện gây lỗi, phiên bản thực dùng, mức bản vá và đường code của mình. Một bug fix có thể làm test cũ sai nếu test dựa trên lỗi cũ.

**“API vẫn hiện trong JavaDoc” không đồng nghĩa “nên tiếp tục phụ thuộc”.** Xem mô tả deprecation/forRemoval và giải pháp thay thế. Ngược lại, tính năng chỉ “preview” tại một bản JDK không tự động trở thành API ổn định của các bản sau.

**“Compile thành công” không đồng nghĩa “runtime tương thích”.** Có những thay đổi về quyền truy cập module, charset, TLS, default locale, GC hoặc native libraries chỉ biểu hiện khi chạy.

**“Không có warning” không đồng nghĩa “không bị ảnh hưởng”.** Runtime behavior changes nhiều khi không sinh compiler warning. Có thay đổi phụ thuộc dữ liệu đặc biệt hoặc cấu hình ít được test.

**“Vẫn chạy khi thêm `--add-opens`” không đồng nghĩa “đã sửa xong”.** Phải xác định thư viện hoặc reflection path đang phụ thuộc internal API và kế hoạch bỏ workaround.

**“JDK và Java language version giống nhau” không đồng nghĩa “đúng một runtime”.** Compiler target xác định cú pháp/API và class-file; JDK runtime còn có các lựa chọn implementation, security providers, resource policy, cài đặt OS và bản cập nhật riêng.

**“Lỗi trên JDK mới” không mặc nhiên là lỗi JDK.** Dependency đã quá cũ, cấu hình JVM khác, container base image khác hoặc test không kiểm soát locale cũng có thể là nguyên nhân.

## 11. Mẫu ghi chú điều tra có thể dùng lại

```text
Thay đổi cần kiểm tra: Default charset JDK 18 (JEP 400)
JDK nguồn/đích: <major, update, vendor được xác nhận>
Tài liệu: <link Release Notes/Migration Guide/JEP/API đúng bản>
Điều kiện: API đọc text không chỉ định Charset; dữ liệu ngoài ASCII
Giả thuyết: Đọc byte UTF-8 khác trên JDK cũ có default charset khác UTF-8
Bằng chứng: Charset.defaultCharset(), input bytes, output và test logs
Tác động: Kết quả decode/encode và dữ liệu ghi ra file
Sửa: Dùng StandardCharsets.UTF_8 tại input/output boundary
Xác nhận: Test cùng fixture và so byte trên cả JDK nguồn lẫn JDK đích
Kết luận: PASS/FAIL kèm đường dẫn log/test và phiên bản JVM thực chạy
```

Trong một báo cáo thật, **thay** các trường mô tả bằng bằng chứng cụ thể; đừng giữ những mục chưa đo thành một kết luận. Nếu bài test không tái hiện, ghi “chưa tái hiện trên môi trường X” và các giới hạn, thay vì khẳng định rủi ro không tồn tại.

## 12. Câu hỏi tự kiểm tra

1. Vì sao một ứng dụng build với `javac --release 15` vẫn có thể hoạt động khác trên JDK 21 so với JDK 15?
2. Khi nâng JDK từ 15 lên 21, cần đọc những mốc tài liệu nào để không bỏ sót thay đổi tại JDK 17 và 18?
3. Nếu ứng dụng chỉ lỗi với text tiếng Việt trên một máy Windows cũ, cần ghi lại những thuộc tính/byte nào trước khi kết luận JDK mới gây lỗi?
4. `jdeps --jdk-internals` có chứng minh mã không dùng reflection vào internal API không? Vì sao?
5. `@Deprecated(forRemoval = true)` khác thế nào với API đã bị xóa ở JDK đích?
6. Khi thấy `InaccessibleObjectException` sau nâng JDK, nên dùng bằng chứng nào để tìm nguyên nhân và hướng sửa lâu dài?
7. Vì sao release notes của một **JDK update** và release notes của một **JDK major** đều quan trọng?

## Nguồn tra cứu chính thức

- [Oracle Java SE Documentation — chọn phiên bản đang dùng](https://docs.oracle.com/en/java/javase/index.html).
- [Oracle JDK 27 Documentation — Release Notes, Migration Guide, API, Tools](https://docs.oracle.com/en/java/javase/27/).
- [Oracle JDK 27 Migration Guide](https://docs.oracle.com/en/java/javase/27/migrate/index.html).
- [Oracle JDK Migration Guide — Behavioral/Internationalization/Encapsulation (JDK 26)](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- [Oracle `javac` Tool Specification — `--release` (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).
- [Oracle `jdeps` Tool Specification (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html).
- [Oracle `jdeprscan` Tool Specification (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeprscan.html).
- [OpenJDK JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400).
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403).

**Điều cần nắm:** đọc tài liệu theo *JDK thật đang build/chạy*, tìm đúng phần **behavior/compatibility**, xác định trigger và mốc version, rồi kiểm chứng bằng test trên artifact/môi trường đích. Chỉ khi nối được **tài liệu → điều kiện tác động → bằng chứng → cách sửa → test xác nhận**, ta mới có một kết luận tương thích đáng tin cậy.