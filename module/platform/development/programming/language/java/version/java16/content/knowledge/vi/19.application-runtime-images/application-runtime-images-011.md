# Kiểm thử TLS, múi giờ, font và provider thực sự được ứng dụng sử dụng

## 1. Vì sao phải kiểm thử trên runtime image cuối?

`jlink` cho phép tạo runtime image chỉ chứa module và tài nguyên mà ứng dụng cần. Một ứng dụng có thể chạy tốt trên JDK đầy đủ của máy phát triển nhưng lỗi sau khi tạo runtime image tối giản. JDK đầy đủ chứa nhiều module, dữ liệu locale, provider và công cụ hơn cấu hình runtime được phân phối. Những thành phần bị lược bỏ chỉ bộc lộ khi ứng dụng chạy đúng tính năng phụ thuộc vào chúng.

Các chức năng thường bị bỏ sót trong kiểm thử đóng gói gồm:

- **TLS:** chứng chỉ, truststore, thuật toán mật mã, provider và cấu hình TLS.
- **Múi giờ:** dữ liệu timezone, quy tắc daylight saving time (DST) và vùng giờ mà ứng dụng sử dụng.
- **Font:** font vật lý trên máy đích, font fallback, khả năng hiển thị ký tự và thư viện đồ họa native.
- **Provider:** JDBC driver, charset provider, locale provider, timezone provider, security provider và SPI/plugin riêng.

Kiểm thử cần chạy bằng chính Java executable nằm trong runtime image hoặc launcher của application image. Việc chỉ chạy test trên JDK đầy đủ không chứng minh runtime tối giản đã đóng gói đủ thành phần.

## 2. Lập danh sách capability trước khi tạo runtime

Trước khi chọn module, hãy ghi lại tính năng ứng dụng thực sự dùng và cách kiểm chứng:

| Capability | Câu hỏi cần trả lời | Ví dụ kiểm thử |
| --- | --- | --- |
| TLS/HTTPS | Ứng dụng kết nối tới endpoint nào, dùng truststore và thuật toán nào? | HTTPS request, xác minh hostname và certificate chain |
| Múi giờ | Ứng dụng xử lý những vùng giờ và thời điểm DST nào? | Chuyển đổi instant sang zoned date-time, kiểm tra DST |
| Font | Ứng dụng render ký tự và font family nào? | Kiểm tra font family, glyph và ảnh render |
| Provider | Ứng dụng nạp implementation nào qua SPI hoặc cấu hình bảo mật? | Kiểm tra provider đã đăng ký và gọi chức năng thực tế |

Đồng thời phân biệt ba nguồn thành phần:

1. **Module JDK:** ví dụ `java.net.http`, `java.desktop`, `jdk.crypto.ec`, `jdk.localedata`.
2. **Tài nguyên bên ngoài JDK:** truststore riêng, font hệ điều hành, thư viện native hoặc file cấu hình.
3. **Dependency ứng dụng:** JDBC driver, provider JAR, plugin và service implementation.

`jlink` chỉ liên kết module JDK và named module hợp lệ trên module path. Công cụ không tự đóng gói mọi truststore tùy chỉnh, font hệ điều hành hoặc JAR classpath chỉ vì ứng dụng có tham chiếu tới chúng.

## 3. Kiểm thử TLS và HTTPS

### 3.1. Các thành phần TLS cần xác nhận

API JSSE như `javax.net.ssl` nằm trong nền tảng Java. Khi tạo runtime, cần kiểm tra cả module và cấu hình liên quan:

- Module ứng dụng có dependency cần thiết, chẳng hạn `java.net.http` nếu dùng Java HTTP Client.
- Provider mật mã có thuật toán mà chứng chỉ hoặc TLS handshake cần. `jdk.crypto.ec` thường cần khi dùng thuật toán elliptic curve (EC), ECDSA hoặc ECDH.
- Nếu tích hợp HSM qua PKCS#11, xem xét `jdk.crypto.cryptoki` và cấu hình native library/token tương ứng.
- Trên Windows, nếu ứng dụng dùng Microsoft Crypto API provider, xem xét `jdk.crypto.mscapi`.
- Truststore chứa CA tin cậy phải có trong runtime hoặc được cung cấp từ cấu hình triển khai.
- Các thiết lập trong `conf/security/java.security` và thuộc tính JSSE phải phù hợp với chính sách bảo mật.

Không phải ứng dụng HTTPS nào cũng cần thêm mọi module crypto. Hãy xác định thuật toán, provider và loại khóa thực tế từ hệ thống tích hợp. `jdk.crypto.ec` là module riêng thường bị thiếu khi runtime tối giản cần các thuật toán EC.

### 3.2. Tạo runtime có HTTP Client và EC provider

Ví dụ ứng dụng modular dùng Java HTTP Client và kết nối endpoint HTTPS có thể cần các module sau:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.client,java.net.http,jdk.crypto.ec --strip-debug --no-header-files --no-man-pages --output build\tls-runtime
~~~

Danh sách này chỉ là ví dụ. Module ứng dụng có thể đã kéo `java.net.http` qua `requires`; `jdk.crypto.ec` chỉ nên thêm khi ứng dụng hoặc TLS configuration cần các thuật toán EC. Nếu dùng PKCS#11 hoặc Windows Crypto API, xác định và thêm module tương ứng.

### 3.3. Smoke test HTTPS bằng Java HttpClient

Dùng Java HTTP Client để kiểm tra TLS theo cấu hình mặc định của runtime:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class TlsSmokeTest {
    public static void main(String[] args) throws Exception {
        URI uri = URI.create("https://example.com/");

        HttpClient client = HttpClient.newBuilder().build();
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request,
                HttpResponse.BodyHandlers.discarding());

        System.out.println("HTTP status: " + response.statusCode());
        response.sslSession().ifPresent(session -> {
            System.out.println("TLS protocol: " + session.getProtocol());
            System.out.println("Cipher suite: " + session.getCipherSuite());
        });
    }
}
~~~

Chạy test bằng Java trong runtime image. Thay endpoint minh họa bằng endpoint test do tổ chức kiểm soát để kiểm tra đúng certificate chain, hostname, TLS version và cipher suite của hệ thống thật.

Không tắt certificate validation hoặc hostname verification để làm test pass. Một kết nối chỉ thành công khi xác minh chứng chỉ, hostname và chính sách TLS vẫn được thực hiện.

### 3.4. Truststore và certificate

JSSE thường sử dụng truststore mặc định của runtime. Ứng dụng có thể chỉ định truststore riêng qua các thuộc tính:

~~~powershell
.\build\tls-runtime\bin\java.exe -Djavax.net.ssl.trustStore="config\company-truststore.p12" -Djavax.net.ssl.trustStoreType=PKCS12 -m com.example.client/com.example.client.Main
~~~

Đảm bảo file truststore được phân phối an toàn và launcher trỏ tới đúng đường dẫn. Không nhúng mật khẩu truststore hoặc private key vào source code, script đóng gói hay image công khai; lấy bí mật từ cơ chế quản lý secret của môi trường triển khai.

Khi dùng truststore mặc định, có thể kiểm tra danh sách CA bằng `keytool -list -cacerts` từ JDK tương ứng. Khi dùng truststore tùy chỉnh, kiểm tra alias, thời hạn và certificate chain của CA cần tin cậy.

Nếu TLS thất bại, bật log chẩn đoán có kiểm soát:

~~~powershell
.\build\tls-runtime\bin\java.exe -Djavax.net.debug=ssl,handshake -m com.example.client/com.example.client.Main
~~~

Log TLS có thể chứa thông tin endpoint, certificate và chi tiết kết nối; chỉ thu thập trong môi trường phù hợp và xử lý theo chính sách bảo mật.

## 4. Kiểm thử dữ liệu múi giờ

### 4.1. Dữ liệu timezone nằm ở đâu?

API thời gian hiện đại như `java.time.ZoneId` và `ZoneRules` thuộc module `java.base`. Dữ liệu timezone (tzdb) được cung cấp cùng runtime Java; không có một module JDK riêng mang tên `jdk.timezone` cần thêm bằng `jlink`.

`jdk.localedata` chủ yếu cung cấp dữ liệu locale như định dạng số, ngày, tên tháng và quy tắc ngôn ngữ. Không nhầm module này với dữ liệu quy tắc timezone. Nếu ứng dụng cần định dạng ngày theo tiếng Việt, có thể cần locale data; nếu cần quy tắc DST của một vùng, phải kiểm tra tzdb trong runtime.

### 4.2. Kiểm tra zone ID và phiên bản quy tắc

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.zone.ZoneRulesProvider;

public class TimeZoneSmokeTest {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime now = Instant.now().atZone(zone);

        System.out.println("Zone: " + zone);
        System.out.println("Current local time: " + now);
        System.out.println("Current offset: " + now.getOffset());

        System.out.println(
                "Available zones: " + ZoneId.getAvailableZoneIds().size());

        System.out.println(
                "TZDB versions: "
                        + ZoneRulesProvider.getVersions("Asia/Ho_Chi_Minh")
                                .keySet());
    }
}
~~~

Kiểm tra các vùng giờ mà ứng dụng thực sự dùng, ví dụ `Asia/Ho_Chi_Minh`, `Asia/Tokyo`, `Europe/Paris` hoặc `America/New_York`. Danh sách ví dụ không thay thế việc xác định zone ID từ dữ liệu nghiệp vụ.

### 4.3. Kiểm tra thời điểm DST chuyển tiếp

Một lỗi phổ biến là giả định mọi ngày có 24 giờ hoặc mọi local date-time đều ánh xạ tới đúng một instant. Ở vùng có DST, local time có thể không tồn tại trong lúc đồng hồ nhảy tới hoặc xuất hiện hai lần khi đồng hồ quay lùi.

~~~java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;

public class DstSmokeTest {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZoneRules rules = zone.getRules();

        LocalDateTime transitionTime =
                LocalDateTime.of(2026, 3, 8, 2, 30);

        System.out.println(
                "Valid offsets: "
                        + rules.getValidOffsets(transitionTime));
    }
}
~~~

Danh sách offset rỗng nghĩa là local time nằm trong khoảng bị bỏ qua; hai offset nghĩa là thời điểm bị lặp. Hãy chọn thời điểm kiểm thử theo quy tắc DST của năm và vùng giờ cần hỗ trợ, vì lịch chuyển đổi có thể thay đổi theo luật địa phương.

Không nên tự cộng cố định 24 giờ để tính ngày nghiệp vụ theo vùng giờ. Dùng `ZonedDateTime`, `LocalDate` và `ZoneId` phù hợp với ý nghĩa nghiệp vụ; lưu instant hoặc offset rõ ràng khi trao đổi dữ liệu giữa hệ thống.

## 5. Kiểm thử font và khả năng render ký tự

### 5.1. Module Java và font hệ điều hành

API font, AWT và Java 2D thuộc module `java.desktop`. Nếu ứng dụng dùng `Font`, `Graphics2D`, `BufferedImage` hoặc render PDF/image qua Java2D, runtime cần module này.

Tuy nhiên, thêm `java.desktop` không có nghĩa `jlink` sẽ đóng gói toàn bộ font hệ điều hành. Java thường sử dụng font vật lý được cài trên máy và cơ chế font configuration của nền tảng:

- Windows dùng các font có sẵn trong hệ điều hành.
- Linux thường cần fontconfig, FreeType và font package phù hợp.
- macOS sử dụng font và cơ chế font của hệ điều hành.

Nếu ứng dụng chạy trên Linux container tối giản, cần kiểm tra thư viện native font và font file thực tế trong image/container. Logical font như `SansSerif` hoặc `Dialog` có thể fallback sang font khác; không bảo đảm mọi ký tự tiếng Việt, CJK hoặc emoji đều được hiển thị như mong muốn.

### 5.2. Thêm java.desktop khi ứng dụng cần render

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.report,java.desktop --strip-debug --no-header-files --no-man-pages --output build\font-runtime
~~~

Chỉ thêm `java.desktop` khi ứng dụng dùng API desktop/Java2D hoặc thư viện phụ thuộc vào các API này. Ứng dụng server không render font, ảnh hoặc PDF có thể không cần module.

### 5.3. Kiểm tra font family và glyph

~~~java
import java.awt.Font;
import java.awt.GraphicsEnvironment;

public class FontSmokeTest {
    public static void main(String[] args) {
        String requiredText = "Tiếng Việt: ă â ê ô ơ ư đ";
        String[] families =
                GraphicsEnvironment.getLocalGraphicsEnvironment()
                        .getAvailableFontFamilyNames();

        for (String family : families) {
            if (family.equalsIgnoreCase("Noto Sans")) {
                Font font = new Font(family, Font.PLAIN, 16);
                System.out.println("Font found: " + family);
                System.out.println(
                        "Missing glyph index: "
                                + font.canDisplayUpTo(requiredText));
            }
        }
    }
}
~~~

Test cần chạy trên đúng OS/container sẽ phân phối. Trên Linux, có thể dùng `fc-match` và `fc-list` để kiểm tra fontconfig nhìn thấy font family nào:

~~~bash
fc-match "Noto Sans"
fc-list : family | sort -u
~~~

Nếu font không có trên máy đích, hãy cài font package cần thiết vào image/container hoặc phân phối font theo giấy phép và cấu hình được phép. Không giả định runtime image Java tự mang theo font mà ứng dụng cần.

### 5.4. Kiểm tra ảnh render thực tế

Kiểm tra font family và glyph chưa bảo đảm layout cuối cùng đúng. Với ứng dụng xuất báo cáo hoặc ảnh, hãy render một ảnh mẫu bằng `Graphics2D`:

~~~java
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
import java.io.File;

public class FontRenderSmokeTest {
    public static void main(String[] args) throws Exception {
        BufferedImage image =
                new BufferedImage(640, 120, BufferedImage.TYPE_INT_ARGB);
        Graphics2D graphics = image.createGraphics();
        try {
            graphics.setFont(new Font("SansSerif", Font.PLAIN, 28));
            graphics.drawString("Báo cáo tiếng Việt: Đặng Thị Ánh", 16, 64);
        } finally {
            graphics.dispose();
        }

        ImageIO.write(image, "png", new File("font-smoke-test.png"));
    }
}
~~~

Mở ảnh đầu ra để xác nhận dấu tiếng Việt, khoảng cách, font fallback và bố cục. Nếu ứng dụng tạo PDF hoặc ảnh bằng thư viện riêng, hãy chạy test bằng chính pipeline render đó thay vì chỉ dựa vào ví dụ Java2D.

## 6. Kiểm thử provider và SPI mà ứng dụng dùng

### 6.1. Không phải mọi provider đều được nạp cùng một cách

Java có nhiều cơ chế provider. Cần xác định API cụ thể trước khi quyết định module:

| Loại provider | Cơ chế phát hiện/cấu hình | Ví dụ kiểm tra |
| --- | --- | --- |
| SPI module | `uses`/`provides`, `ServiceLoader` và service binding | Kiểm tra provider type được tìm thấy |
| SPI trên classpath | `META-INF/services` và class loader | Kiểm tra JAR cùng file service config |
| JDBC driver | `java.sql`, `DriverManager` và service provider | Mở kết nối bằng driver thực tế |
| JCA/JSSE security provider | Danh sách provider trong cấu hình security và `java.security.Security` | Liệt kê provider, kiểm tra thuật toán |
| Charset provider | `CharsetProvider` và provider module/JAR | `Charset.isSupported` và round-trip dữ liệu |
| Timezone provider | `ZoneRulesProvider` | Kiểm tra zone ID và rules |
| Locale provider | Locale SPI và `jdk.localedata` | Định dạng dữ liệu theo locale thực tế |

`jlink --bind-services` phục vụ service binding của JPMS đối với các module khai báo service. Nó không thay thế cấu hình riêng của mọi provider registry. Đặc biệt, security provider còn phụ thuộc cấu hình `java.security` và thứ tự provider; phải kiểm tra bằng API bảo mật thực tế.

### 6.2. Kiểm tra JCA security providers và thuật toán

~~~java
import java.security.Provider;
import java.security.Security;
import java.security.Signature;

public class SecurityProviderSmokeTest {
    public static void main(String[] args) throws Exception {
        for (Provider provider : Security.getProviders()) {
            System.out.println(
                    provider.getName() + " " + provider.getVersionStr());
        }

        Signature signature = Signature.getInstance("SHA256withECDSA");
        System.out.println(
                "ECDSA provider: " + signature.getProvider().getName());
    }
}
~~~

Ví dụ ECDSA chỉ phù hợp nếu ứng dụng thực sự cần thuật toán này. Nếu hệ thống dùng RSA, EdDSA hoặc HSM, hãy thay bằng thuật toán và provider thực tế. Không giả định provider có mặt chỉ vì module đã được thêm; kiểm tra `Security.getProviders()` và khởi tạo thuật toán.

### 6.3. Kiểm tra JDBC provider

Với JDBC driver, xác nhận driver JAR hoặc module được đóng gói cùng ứng dụng và có thể mở kết nối tới database test:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;

public class JdbcSmokeTest {
    public static void main(String[] args) throws Exception {
        String url = System.getenv("JDBC_TEST_URL");
        String user = System.getenv("JDBC_TEST_USER");
        String password = System.getenv("JDBC_TEST_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {
            System.out.println(
                    "Database: "
                            + connection.getMetaData().getDatabaseProductName());
        }
    }
}
~~~

Thông tin kết nối được truyền từ biến môi trường hoặc secret manager; không ghi thông tin xác thực vào code hoặc file Markdown. Nếu driver là named module, kiểm tra module path và khai báo service provider. Nếu driver là JAR classpath, giữ file `META-INF/services/java.sql.Driver` và bảo đảm launcher có JAR trong classpath.

## 7. Chọn module theo tính năng thực tế

Ví dụ runtime cho ứng dụng báo cáo modular cần HTTPS, font render, locale tiếng Việt và provider EC:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods;providers" --add-modules com.example.report,java.net.http,java.desktop,jdk.crypto.ec,jdk.localedata --include-locales=vi-VN,en-US --compress=zip-6 --no-header-files --no-man-pages --output build\report-runtime
~~~

Đây là tập module minh họa, không phải danh sách mặc định cho mọi ứng dụng. Hãy bỏ module không dùng và bổ sung module provider thực tế sau khi kiểm tra dependency, security configuration và service contract.

Múi giờ cơ bản được cung cấp bởi `java.base`, vốn luôn có trong runtime image; không cần thêm module timezone riêng. Nếu dùng PKCS#11, Windows Crypto API, charset mở rộng hoặc công cụ chẩn đoán, bổ sung module tương ứng theo nhu cầu đã xác minh.

## 8. Kiểm thử theo đúng runtime và nền tảng phát hành

Một quy trình kiểm thử hiệu quả nên có các bước:

1. Tạo runtime image bằng đúng JDK/toolchain dùng trong pipeline phát hành.
2. Kiểm tra module bằng `java --list-modules` trong image.
3. Chạy TLS smoke test với endpoint test, certificate chain và hostname thật.
4. Chạy timezone test với zone ID và các mốc DST nghiệp vụ.
5. Chạy font/glyph/render test trên đúng OS hoặc container image.
6. Kiểm tra từng provider bằng API thực tế: `ServiceLoader`, `Security`, `Charset`, `ZoneRulesProvider` hoặc `DriverManager`.
7. Tạo application image bằng `jpackage` và chạy launcher, vì launcher có thể dùng Java options, module path hoặc classpath khác lệnh test thủ công.
8. Chạy lại smoke/integration test trên máy sạch không cài JDK đầy đủ.

Runtime image gắn với nền tảng hệ điều hành và kiến trúc CPU nơi nó được tạo. Font, thư viện native, crypto provider và installer cũng phụ thuộc nền tảng. Build và kiểm thử riêng cho từng target platform; không lấy kết quả Windows để kết luận Linux hoặc macOS hoạt động giống hệt.

## 9. Ma trận lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| HTTPS lỗi trust path | Thiếu CA hoặc truststore sai | Kiểm tra truststore và certificate chain |
| TLS không chọn được cipher/algorithm | Provider hoặc thuật toán không có/không được phép | Kiểm tra `Security.getProviders()`, `jdk.crypto.ec` và security properties |
| TLS handshake lỗi sau khi nâng JDK | Chính sách TLS, certificate hoặc thuật toán bị thay đổi | Kiểm tra handshake log và cấu hình `java.security` |
| Không tìm thấy ZoneId | Zone ID sai hoặc provider/tzdb không có | Kiểm tra `ZoneId.getAvailableZoneIds()` và zone ID chuẩn |
| DST tính sai | Dùng offset cố định hoặc dữ liệu timezone cũ | Dùng `ZoneRules` và cập nhật runtime có tzdb mới |
| Font bị thay thế hoặc mất dấu | Font không có trên máy, fontconfig/native dependency thiếu | Kiểm tra font family, glyph và ảnh render |
| JDBC driver không được tìm thấy | Thiếu JAR/module hoặc service descriptor | Kiểm tra classpath, module path và `META-INF/services` |
| Security provider không xuất hiện | Thiếu module, sai `java.security` hoặc provider không được đăng ký | Kiểm tra `Security.getProviders()` và security configuration |
| Chỉ lỗi trong application image | Launcher hoặc resource path khác môi trường test | Kiểm tra launcher options, classpath và thư mục làm việc |

## 10. Checklist phát hành

- Xác định endpoint TLS, truststore, certificate chain, TLS version và thuật toán cần hỗ trợ.
- Thêm `jdk.crypto.ec`, `jdk.crypto.cryptoki` hoặc `jdk.crypto.mscapi` chỉ khi provider tương ứng được sử dụng.
- Xác nhận truststore mặc định hoặc truststore riêng có trong môi trường triển khai.
- Kiểm tra timezone ID, tzdb version và các mốc DST nghiệp vụ; không nhầm timezone data với locale data.
- Thêm `java.desktop` khi ứng dụng render font/ảnh/PDF bằng Java desktop APIs.
- Cài và kiểm tra font vật lý, fontconfig và native dependencies trên OS/container đích.
- Kiểm tra các provider cụ thể: SPI, JDBC, JCA/JSSE, charset, locale và timezone.
- Dùng `--bind-services` cho provider module theo JPMS khi cần; kiểm tra cấu hình riêng của security provider.
- Chạy smoke test trên runtime image, sau đó chạy lại qua application launcher.
- Lặp lại kiểm thử trên từng OS/CPU target trước khi phát hành.

**Ghi nhớ:** Runtime image chỉ đủ dùng khi các capability thực tế đều hoạt động trên môi trường đích. TLS phụ thuộc truststore, thuật toán và provider; timezone dựa vào tzdb trong `java.base`; font cần `java.desktop` cùng font hệ điều hành; provider có nhiều cơ chế đăng ký khác nhau. Hãy kiểm thử chức năng thực tế trên runtime image và launcher cuối, không chỉ kiểm tra danh sách module.

## Nguồn tham khảo chính thức

- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [Java Secure Socket Extension (JSSE) Reference Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html)
- [Java Cryptography Architecture (JCA) Reference Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html)
- [java.time.zone API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/zone/package-summary.html)
- [java.awt.Font API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/Font.html)
- [ServiceLoader API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html)
