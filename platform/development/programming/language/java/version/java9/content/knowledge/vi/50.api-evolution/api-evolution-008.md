# Kiểm tra tính năng và khả năng hỗ trợ thay cho suy đoán từ tên bản phát hành

## Mục tiêu và bối cảnh: Tiến hóa API trong Java hiện đại

Khi một API phát triển qua các phiên bản Java, câu hỏi vận hành quan trọng là **“môi trường đang chạy có thật sự cung cấp và cho phép dùng khả năng này không?”**. Câu trả lời không chỉ dựa vào dòng chữ “Java 17”, “Java 21”, phiên bản thư viện hoặc tên một bản phát hành. Cùng một bản JDK có thể được đóng gói với tập module khác nhau, dùng security provider khác nhau, có cờ cấu hình khác nhau và tương tác với môi trường ngoài khác nhau.

Sau bài này, bạn có thể:

1. Phân biệt **baseline biên dịch**, **JVM release**, **module trong runtime image**, **module đã resolve**, **implementation/provider**, **cấu hình supported/enabled**, **chính sách ứng dụng** và **thao tác thực sự thành công**.
2. Kiểm tra capability bằng các API chính thức, chẳng hạn `ModuleFinder.ofSystem()`, `ModuleLayer.boot().findModule(...)`, `MessageDigest.getInstance(...)`, `SSLContext.getSupportedSSLParameters()` và `ToolProvider.findFirst(...)`.
3. Phân biệt `ENABLED`, `UNAVAILABLE`, `DISABLED_BY_POLICY` và `FAILED`; thiết kế fallback có điều kiện, tránh âm thầm đổi hợp đồng giao tiếp/bảo mật.
4. Viết chương trình Java 17+ chạy độc lập và bộ kiểm thử có cả nhánh được hỗ trợ lẫn không được hỗ trợ; kiểm chứng trên JDK đầy đủ và image đóng gói bằng `jlink`.

Cơ chế module và service provider thuộc Java hiện đại, xuất hiện cùng Java Platform Module System (JPMS) từ Java 9. Bài ưu tiên những API và cách triển khai vẫn áp dụng cho JDK hiện hành; ví dụ sử dụng **baseline Java 17** để bảo đảm mã biên dịch được và dễ kiểm thử.

## 1. Một “phiên bản” trả lời được gì và không trả lời được gì?

Phiên bản JVM giúp ghi nhận mốc tương thích ở mức ngôn ngữ, class file và API tiêu chuẩn. Ví dụ từ Java 10 trở lên:

```java
int runtimeFeature = Runtime.version().feature();
```

Đây là **đoạn trích**, không phải chương trình độc lập. `Runtime.version()` có từ Java 9, nhưng **phương thức `feature()` được giới thiệu trong Java 10**; nếu cần hỗ trợ chạy trực tiếp trên Java 9 thì không được gọi `feature()` trong mã biên dịch theo baseline 9.

Những kết luận dưới đây đều thiếu cơ sở:

```java
// Các ví dụ SAI về tư duy: nhãn release không phải feature probe.
boolean sha3Ready = Runtime.version().feature() >= 9;
boolean httpClientReady = Runtime.version().feature() >= 11;
boolean tls13Negotiated = Runtime.version().feature() >= 11;
```

Tại sao sai?

- Tên thuật toán `SHA3-256` có từ Java 9, nhưng cần security provider hiện hành cung cấp implementation.
- HTTP Client là API chuẩn từ Java 11 trong module `java.net.http`; một runtime image tùy chỉnh có thể đã loại module đó. Module có trong image cũng chưa chắc được resolve vào module layer mà ứng dụng dùng.
- TLS 1.3 có thể được provider hỗ trợ nhưng bị tắt trong cấu hình endpoint hoặc không thương lượng được với peer. Tên JVM release không chứng minh phiên kết nối dùng TLS 1.3.

Cũng **không so sánh tên bản phát hành bằng chuỗi**:

```text
"9".compareTo("17") > 0  // đúng về thứ tự từ điển, sai về thứ tự số phiên bản
```

Dùng `Runtime.version()`, thông tin vendor/build, toolchain và manifest để **chẩn đoán**. Dùng probe ở đúng tầng để quyết định **khả năng thực tế**.

## 2. Bản đồ các tầng hỗ trợ

| Cấp độ | Câu hỏi kiểm tra | Công cụ/API thích hợp | Chưa bảo đảm điều gì? |
| --- | --- | --- | --- |
| Build/API | Source có thể dùng API theo mốc Java cam kết? | `javac --release 17`, compile/test CI. | Chưa bảo đảm provider hoặc module tùy chọn ở máy đích có mặt. |
| JVM version | Release feature của JVM đang chạy là bao nhiêu? | `Runtime.version().feature()`, `java --version`. | Không biết tính năng cụ thể được bật hay bị loại khỏi image. |
| Runtime image | Module hệ thống được đóng gói không? | `ModuleFinder.ofSystem().find(name)`, `java --list-modules`. | Module có thể chưa được resolve trong layer. |
| Module layer | Module có thể được tìm thấy trong layer đang xét? | `ModuleLayer.boot().findModule(name)` hoặc custom layer. | Không tự cấp quyền `exports/opens`, không chứng minh API hoạt động. |
| Class/method | Chữ ký API có thật ở runtime không? | `Class.forName`, `Class.getMethod` trong trường hợp tương thích động. | Không biết dependency, chính sách, quyền và hành vi thực thi. |
| Service/provider | Có implementation cho capability? | `getInstance(...)`, `ServiceLoader`, `ToolProvider.findFirst`. | Provider có thể hỏng, không phù hợp policy hoặc thao tác thất bại. |
| Configuration | Feature do implementation hỗ trợ và có được bật không? | `SSLContext` supported/default params; config/feature flag. | Chưa chứng minh peer, mạng, chứng chỉ hoặc workload thực tế. |
| Operation | Tác vụ cụ thể thành công theo hợp đồng không? | Integration test, xử lý ngoại lệ, xác minh kết quả. | Không bảo đảm trạng thái mạng, file, credential không thay đổi sau đó. |

Một quyết định chỉ nên trả `ENABLED` sau khi xác minh **những điều kiện liên quan tới thao tác**:

```text
Yêu cầu nghiệp vụ
     |
Feature được chính sách cho phép?
     | no -> DISABLED_BY_POLICY
     | yes
Implementation/module/provider phù hợp có mặt?
     | no -> UNAVAILABLE
     | yes
Đã kiểm tra config/khả năng thực thi cần thiết?
     | no -> FAILED/UNAVAILABLE theo nguyên nhân
     | yes
Thực hiện thao tác và kiểm tra kết quả
     | success -> COMPLETED
     | failure -> FAILED (gắn nguyên nhân)
```

Tùy loại capability, việc kiểm tra có thể thực hiện ngay khi startup, trước khi nhận một loại request hoặc tại thời điểm thực hiện. Không cần chạy mọi probe cho mọi request nếu trạng thái ổn định; ngược lại không cache vĩnh viễn kết quả phụ thuộc mạng, file, credential hoặc peer từ startup.

## 3. Module có trong image khác module đã resolve

Java 9 đưa cơ chế JPMS, nhờ đó ứng dụng biết các module hệ thống nào thực sự có trong runtime image:

```java
// Trích đoạn: dùng java.lang.module.ModuleFinder.
boolean installed = ModuleFinder.ofSystem()
        .find("java.net.http").isPresent();

// Module trong boot layer:
boolean resolved = ModuleLayer.boot()
        .findModule("java.net.http").isPresent();
```

`ModuleFinder.ofSystem()` nhìn vào **module trong runtime image**, còn `ModuleLayer.boot().findModule(...)` tìm module đã định nghĩa trong **boot layer hoặc layer cha**. Hai câu hỏi khác nhau: một module có thể tồn tại nhưng chưa được resolve.

Lưu ý thêm:

- Ứng dụng có thể định nghĩa module ở **custom ModuleLayer**. Nếu feature thuộc plugin được load ở layer riêng, kiểm tra layer đó, không mặc định boot layer chứa mọi module.
- Dù module có mặt và resolved, ranh giới `requires`, `exports` và `opens` vẫn có ý nghĩa. `findModule` không cấp quyền reflection hay cho phép sử dụng package không export.
- Với module ứng dụng từ module path, `ModuleFinder.ofSystem()` không phải phép liệt kê mọi module người dùng đã cung cấp; nó chỉ tìm **system modules**. Để kiểm tra module bên ngoài, cần module finder/layer tương ứng.
- Module `java.net.http` được giới thiệu từ Java 11. Một runtime Java 17/21 được tạo với `jlink` có thể không chứa nó; việc chạy ở release cao hơn **không bảo đảm** nó hiện diện.

Để kiểm tra image trên đúng máy deploy:

```bash
java --version
java --list-modules
```

Khi dùng image tùy chỉnh, phải chạy lệnh `java` **bên trong image đó**, tránh vô tình dùng JDK khác từ `PATH`. Kết quả `--list-modules` là chứng cứ packaging, không phải kết quả test API/network.

## 4. Provider mật mã: kiểm tra thuật toán thay vì mốc Java

JCA cung cấp cơ chế truy vấn implementation qua tên thuật toán. Ví dụ:

```java
// Trích đoạn, cần import MessageDigest, NoSuchAlgorithmException, Optional.
Optional<MessageDigest> trySha3() {
    try {
        return Optional.of(MessageDigest.getInstance("SHA3-256"));
    } catch (NoSuchAlgorithmException noProvider) {
        return Optional.empty();
    }
}
```

`MessageDigest.getInstance("SHA3-256")` hỏi **các security provider đã đăng ký**, trả implementation thực hoặc ném `NoSuchAlgorithmException`. Nó chính xác hơn điều kiện `Runtime.version().feature() >= 9`. Để chẩn đoán, có thể xem `digest.getProvider().getName()`. Không cần hard-code tên provider nếu hợp đồng không yêu cầu cụ thể.

Cách xử lý phải theo hợp đồng:

1. Nếu thuật toán **bắt buộc** cho một định dạng dữ liệu/giao thức, khi không có implementation phải báo lỗi **UNAVAILABLE** hoặc fail startup. Không tự thay `SHA3-256` bằng `SHA-256` chỉ vì cả hai dài 256 bit.
2. Nếu giao thức **cho phép thương lượng** nhiều thuật toán, hãy chọn từ danh sách được policy cho phép và ghi rõ tên được chọn trong metadata.
3. Có provider chưa chắc thao tác thành công; test vector và kiểm tra độ dài/kết quả ở dữ liệu thật giúp phát hiện lỗi cấu hình/implementation.
4. Chỉ bắt `NoSuchAlgorithmException` để diễn giải trường hợp **provider không có thuật toán**. Đừng bắt bừa `Exception` hay `Error` và xem mọi lỗi là “unsupported”; ví dụ lỗi class linkage/provider hỏng là lỗi khác.

Thông tin Java release vẫn hữu ích trong log hỗ trợ kỹ thuật, nhưng không được dùng làm giá trị thay thế cho kết quả `getInstance`.

## 5. TLS: supported, enabled và negotiated là ba trạng thái khác nhau

Với JSSE:

```java
SSLContext ssl = SSLContext.getDefault();
String[] supported = ssl.getSupportedSSLParameters().getProtocols();
String[] enabledByDefault = ssl.getDefaultSSLParameters().getProtocols();
```

Đây là **đoạn trích**; cần import `javax.net.ssl.SSLContext` và xử lý exception phù hợp.

- **Supported**: provider triển khai protocol mà `SSLContext` công bố; không nói rằng protocol đó được khuyến nghị hoặc được phép tại endpoint.
- **Default-enabled**: những protocol trong cấu hình mặc định của context; từng socket/engine có thể được cấu hình khác.
- **Enabled thực tế**: cấu hình trên `SSLSocket` hoặc `SSLEngine` ở thời điểm chuẩn bị handshake.
- **Negotiated**: phiên bản/cipher thật đã thống nhất **sau khi handshake thành công** và xác minh peer theo chính sách.

Kiểm tra `TLSv1.3` xuất hiện trong supported **không đủ** để kết luận một kết nối đã sử dụng TLS 1.3. Cần kiểm tra protocol/cipher đã đàm phán, trust/certificate, endpoint identification, ALPN (nếu giao thức yêu cầu), remote peer và giới hạn bảo mật.

Cũng không tự hạ xuống protocol không đạt chính sách chỉ vì môi trường hiện tại có vẻ “không hỗ trợ” lựa chọn mới. Nếu cấu hình bảo mật bắt buộc một protocol, phải fail rõ ràng khi thiếu.

## 6. Service và công cụ tùy chọn

Một JVM chạy ứng dụng không nhất thiết chứa compiler Java. Java 9 cung cấp `ToolProvider`:

```java
boolean canCompileDynamically =
        java.util.spi.ToolProvider.findFirst("javac").isPresent();
```

Một runtime image được tạo từ subset module có thể bỏ `jdk.compiler`, dù JVM phát hành theo cùng mốc với JDK đầy đủ. Nếu chức năng biên dịch động là optional, tắt đúng chức năng đó khi `javac` không có. Nếu biên dịch động là yêu cầu bắt buộc, startup có thể fail với thông báo rõ. `findFirst("javac")` chỉ cho biết có tool provider tương ứng; chưa chứng minh compile của dự án thành công.

Đối với plugin/provider do dự án tự định nghĩa, dùng `ServiceLoader` thay vì đoán từ version JAR:

```java
// Trích đoạn minh họa: ReportExporter là SPI của ứng dụng, cần tự định nghĩa.
for (ReportExporter exporter :
        java.util.ServiceLoader.load(ReportExporter.class)) {
    if (exporter.supports("pdf")) {
        // Chỉ chọn sau khi xét cấu hình/policy và kiểm thử chức năng.
    }
}
```

`ServiceLoader` tìm implementation qua metadata/module `provides ... with ...` hoặc khai báo service phù hợp, tùy classpath/module path. Một thư viện “có hỗ trợ PDF” trên website không có nghĩa provider được đóng gói/đăng ký trong deployment này. Nếu provider lỗi hoặc bị `ServiceConfigurationError`, cần ghi nhận đúng là lỗi provider, không giả định tính năng vắng mặt là bình thường.

## 7. API mới hơn baseline: kiểm tra chữ ký có giới hạn

Giả sử ứng dụng phải chạy trên **Java 17+** nhưng muốn dùng API **virtual threads** ổn định từ Java 21. Mã biên dịch bằng `javac --release 17` không thể gọi trực tiếp `Thread.ofVirtual()`, vì chữ ký chưa có trong Java 17.

Có thể hỏi **chữ ký public** bằng reflection:

```java
// Trích đoạn method, dùng API Java 17 trở xuống:
static boolean hasVirtualThreadBuilder() {
    try {
        Thread.class.getMethod("ofVirtual");
        return true;
    } catch (NoSuchMethodException absent) {
        return false;
    }
}
```

Điều này chỉ kết luận phương thức có tồn tại; nó chưa kiểm chứng thực thi thread, quyền tài nguyên hoặc hiệu năng. Nếu cần dùng thật, có ba hướng đúng:

- Nâng **baseline** lên Java 21, rồi dùng API trực tiếp và khai báo yêu cầu deployment.
- Tách adapter Java 21 ra artifact/source set riêng, chỉ load adapter khi môi trường đáp ứng hợp đồng và kiểm thử nó trên Java 21.
- Dùng reflection/MethodHandles tại một biên tương thích hẹp và kiểm thử đủ nhánh lookup/invocation; tránh làm toàn bộ nghiệp vụ phụ thuộc reflection.

Việc biên dịch class chứa lời gọi API mới bằng Java 21 rồi bọc `if (version >= 21)` **không đủ** để bảo đảm artifact chạy được trên Java 17: class file version, direct linkage và module/API đều phải tương thích. Một class có thể không load được trước khi điều kiện chạy.

Với tính năng **preview/incubator**, việc nó hiện diện trong bản JDK không có nghĩa đã ổn định hoặc được bật mặc định. Dựa vào trạng thái chính thức và các tùy chọn build/runtime của đúng release. Tránh coi preview feature là cam kết tương thích cho mọi release sau đó.

## 8. Chương trình Java 17+ hoàn chỉnh

Chương trình sau kiểm tra **nhiều tầng capability thật** trong một lượt, không cần mạng hoặc thư viện bên thứ ba. Nó dùng release version **chỉ để biết baseline**, kiểm tra riêng hệ module, provider thuật toán, danh sách TLS supported/default, công cụ compiler và chính sách ứng dụng.

Lưu tệp **`CapabilityCheckDemo.java`**:

```java
import java.lang.module.ModuleFinder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Optional;
import java.util.Set;
import java.util.spi.ToolProvider;
import javax.net.ssl.SSLContext;

public final class CapabilityCheckDemo {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    private static Optional<MessageDigest> availableDigest(String algorithm) {
        try {
            return Optional.of(MessageDigest.getInstance(algorithm));
        } catch (NoSuchAlgorithmException unavailable) {
            return Optional.empty();
        }
    }

    private static String decision(boolean supported, boolean permitted) {
        if (!permitted) return "DISABLED_BY_POLICY";
        return supported ? "ENABLED" : "UNAVAILABLE";
    }

    public static void main(String[] args) throws Exception {
        int feature = Runtime.version().feature();
        check(feature >= 17, "Requires Java 17+");
        System.out.println("PASS runtime version recorded as metadata");

        boolean installed = ModuleFinder.ofSystem()
                .find("java.net.http").isPresent();
        boolean resolved = ModuleLayer.boot()
                .findModule("java.net.http").isPresent();
        check(!resolved || installed, "Resolved system module must exist");
        System.out.println("PASS installed and resolved modules inspected");

        Optional<MessageDigest> sha3 = availableDigest("SHA3-256");
        if (sha3.isPresent()) {
            check(sha3.get().digest("abc".getBytes(StandardCharsets.UTF_8))
                    .length == 32, "Incorrect SHA3-256 length");
        }
        check(availableDigest("UNSUPPORTED-DIGEST-DEMO").isEmpty(),
                "Unknown digest must be unavailable");
        System.out.println("PASS JCA provider probed and absent path tested");

        SSLContext tls = SSLContext.getDefault();
        Set<String> supported = new HashSet<>(Arrays.asList(
                tls.getSupportedSSLParameters().getProtocols()));
        Set<String> enabledByDefault = new HashSet<>(Arrays.asList(
                tls.getDefaultSSLParameters().getProtocols()));
        check(supported.containsAll(enabledByDefault),
                "Defaults must be supported by provider");
        System.out.println("PASS TLS supported and default-enabled checked");

        boolean compilerTool = ToolProvider.findFirst("javac").isPresent();
        check(!compilerTool || ModuleFinder.ofSystem()
                .find("jdk.compiler").isPresent(),
                "javac provider requires its module in system image");
        System.out.println("PASS tooling availability probed");

        check("ENABLED".equals(decision(true, true)), "Enabled case");
        check("UNAVAILABLE".equals(decision(false, true)), "Unavailable case");
        check("DISABLED_BY_POLICY".equals(decision(true, false)),
                "Policy-denied case");
        System.out.println("PASS support and policy treated separately");
        System.out.println("ALL CHECKS PASSED");
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 --release 17 CapabilityCheckDemo.java
java CapabilityCheckDemo
```

Stdout khi chạy thành công trên JDK 24 có JSSE:

```text
PASS runtime version recorded as metadata
PASS installed and resolved modules inspected
PASS JCA provider probed and absent path tested
PASS TLS supported and default-enabled checked
PASS tooling availability probed
PASS support and policy treated separately
ALL CHECKS PASSED
```

**Đọc kết quả cho đúng:**

1. `PASS runtime version recorded as metadata` chỉ nói ví dụ có baseline Java 17 trở lên. Không dùng nó để suy ra thuật toán/module/protocol.
2. `PASS installed and resolved modules inspected` chứng minh phép kiểm tra logic giữa module hệ thống đã resolve và module trong image nhất quán. Nó **không** nói `java.net.http` phải có trong mọi runtime.
3. `PASS JCA provider probed and absent path tested` xác minh đường hỗ trợ khi `SHA3-256` có provider và nhánh âm cho tên thuật toán không tồn tại. Nếu SHA3 là **bắt buộc**, code nghiệp vụ phải fail khi `sha3.isEmpty()`.
4. `PASS TLS supported and default-enabled checked` xác minh tập default-enabled nằm trong tập supported của context. Đây **không phải** handshake test. Demo yêu cầu `SSLContext.getDefault()` tạo được context; nếu môi trường không cung cấp JSSE thích hợp, phải báo lỗi capability thiếu.
5. `PASS tooling availability probed` chỉ kiểm tra provider của `javac` và nhất quán với system module, không tự chạy compiler.
6. Các assertion `decision(...)` kiểm tra nhánh **policy trước, capability sau**. Feature có implementation nhưng bị policy cấm phải là `DISABLED_BY_POLICY`, không là `ENABLED`.

Các dòng PASS là kết quả **kiểm thử cơ chế phát hiện và xử lý**. Chúng không in các giá trị `installed`, `resolved`, `sha3.isPresent()` hay `compilerTool`, vì những giá trị ấy tùy runtime. Khi chẩn đoán triển khai, log cụ thể từng giá trị kèm provider/image/operation có liên quan.

## 9. Cách quyết định fallback an toàn

Một probe không thể tự quyết định thay đổi giao thức. Nên phân loại kết quả rõ ràng:

| Trạng thái | Nghĩa | Hướng xử lý |
| --- | --- | --- |
| `ENABLED` | Có implementation, policy cho phép và các điều kiện cần đã được xác nhận. | Thực hiện, tiếp tục xử lý lỗi runtime tại thao tác. |
| `UNAVAILABLE` | Module, provider, method hoặc service cần thiết không có. | Thông báo thiếu capability, tắt phần tùy chọn hoặc fail startup nếu bắt buộc. |
| `DISABLED_BY_POLICY` | Tính năng có thể tồn tại nhưng ứng dụng/tổ chức cấm. | Không cố kích hoạt hay fallback vượt chính sách. |
| `FAILED` | Thao tác gặp lỗi IO, network, certificate, quyền, initialization hoặc bug. | Báo lỗi đúng nguyên nhân; retry/fail theo hợp đồng. |

Ví dụ:

- Một service cho phép xuất báo cáo **CSV hoặc JSON** và plugin JSON vắng mặt: có thể đưa CSV nếu người dùng/giao thức chấp thuận.
- Một giao thức chữ ký quy định **SHA3-256**: provider thiếu thì **không** tự chuyển sang SHA-256.
- Policy TLS bắt buộc TLS 1.3: nếu endpoint chưa thể thương lượng, **không** hạ xuống giao thức bị cấm.
- Công cụ build động optional thiếu `jdk.compiler`: có thể tắt mục “Compile” mà không ảnh hưởng chức năng đọc dữ liệu.
- Module có đầy đủ nhưng đọc file bị từ chối: đó là lỗi quyền hoặc tài nguyên, không phải dấu hiệu “JDK release chưa hỗ trợ”.

Nếu feature **bắt buộc và ổn định** (ví dụ module chính, provider mã hóa được yêu cầu), kiểm tra lúc startup hoặc readiness. Nếu feature **phụ thuộc môi trường đang thay đổi** (kết nối mạng, tài nguyên file, token/quyền), phải tiếp tục kiểm soát lỗi tại thời điểm dùng và không coi startup probe là bảo đảm suốt đời ứng dụng.

## 10. Baseline build và runtime image đều cần xác minh

### 10.1. `--release` giúp khóa API nguồn

```bash
javac --release 17 CapabilityCheckDemo.java
```

`--release 17` yêu cầu compiler biên dịch với ngôn ngữ/API chuẩn của Java 17 và class-file target phù hợp. Nó giúp ngăn vô tình gọi API chỉ có ở release mới hơn. Cờ `-source 17 -target 17` đơn thuần trên JDK mới không tương đương hoàn toàn với `--release 17` nếu còn để code tham chiếu API của JDK mới.

Tuy nhiên, `--release` **không đóng gói** module/provider tùy chọn, không cấu hình service và không thể bảo đảm tương thích mọi thứ trong runtime image mục tiêu. Vì vậy, pipeline cần **compile test + integration test** trên artifact/images triển khai.

### 10.2. `jlink` và phân tích dependency

`jlink` tạo image từ tập module được chọn và dependency của chúng. Hai image dùng cùng Java feature release nhưng có module/provider khác nhau. Hãy kiểm tra chính artifact dùng ở production:

```bash
# Lệnh mẫu: thay đường dẫn bằng image và artifact thực tế.
path/to/runtime-image/bin/java --list-modules
jdeps --print-module-deps path/to/application.jar
```

`jdeps` là phân tích **tĩnh** bytecode: có thể không phát hiện mọi optional provider, dependency load qua reflection, `ServiceLoader`, tên class lưu trong config hoặc native library. Cần kết hợp với test trên image thật. Đặc biệt, dùng `java --list-modules` từ JDK build **không** tương đương với việc đọc module trong runtime image đã triển khai.

Với plugin trong custom `ModuleLayer`, kiểm tra module và service của layer đó. Với classpath truyền thống, kiểm tra class loader/metadata thư viện tương ứng; không lẫn mọi vấn đề vào danh sách system modules.

### 10.3. API được biên dịch nhưng thiếu ở runtime

Từng trường hợp có thể xuất hiện các lỗi khác nhau:

- `UnsupportedClassVersionError`: runtime không hiểu phiên bản bytecode của class.
- `NoClassDefFoundError`, `ClassNotFoundException`: class không load/tìm được theo đường sử dụng tương ứng.
- `NoSuchMethodError`: binary kỳ vọng method có ở lúc link nhưng runtime lại không có phương thức tương ứng.
- `NoSuchAlgorithmException`: không có provider hỗ trợ tên thuật toán JCA được yêu cầu.
- `ServiceConfigurationError`: cấu hình/implementation của service provider lỗi.

Đừng biến mọi lỗi này thành “Java quá cũ”. Mỗi lỗi có nguyên nhân và cách khắc phục riêng. Nếu dùng API optional mới hơn baseline, phải tránh **direct linkage trước guard**; giữ implementation mới ở vùng được load có điều kiện hoặc nâng baseline khi nghiệp vụ cho phép.

## 11. Ma trận kiểm thử nên áp dụng

| Tình huống | Thiết lập/fixture | Assertion |
| --- | --- | --- |
| Baseline đúng | `javac --release 17`, chạy trên JDK được hỗ trợ | Biên dịch/chạy; API có trong baseline. |
| Hai bản JDK khác nhau | JDK 17 và 21+ hoặc hai vendor | Log version khác nhau nhưng logic capability không phụ thuộc đơn độc vào version. |
| Module optional bị loại | Runtime image `jlink` không chứa `java.net.http` | `ModuleFinder.ofSystem()` trả absent; tính năng tương ứng tắt/báo lỗi đúng. |
| Module có nhưng chưa resolve | Module có trong image nhưng không thuộc boot graph | Installed true khác resolved false; không giả định load API thành công. |
| Thuật toán tồn tại | Provider có `SHA3-256` | `getInstance` chạy được, digest đúng test vector. |
| Thuật toán thiếu | Provider fixture hoặc tên `UNSUPPORTED-DIGEST-DEMO` | Có nhánh `UNAVAILABLE`, không nuốt lỗi bất ngờ. |
| Tính năng bị cấm | Config `feature.enabled=false`, capability true | `DISABLED_BY_POLICY` được ưu tiên. |
| TLS hỗ trợ nhưng tắt | Supported có TLSv1.3, enabled không chứa | Không tuyên bố handshake TLS 1.3 đã thành công. |
| Tool compiler absent | Image không đóng gói `jdk.compiler` | `ToolProvider.findFirst("javac")` absent và xử lý theo optional/required. |
| Optional API trên baseline cũ | Java 17 không có `Thread.ofVirtual()` | Reflection signature false; adapter không được direct-link trước guard. |
| Provider hỏng | Test provider ném lỗi initialization/config | `FAILED` với nguyên nhân, không biến thành unsupported. |
| Mạng hoặc credential thay đổi | Integration test thu hồi quyền hoặc ngắt peer | Operation báo lỗi đúng và cơ chế recovery giới hạn. |

Nên cô lập logic quyết định để unit test bằng dữ liệu giả, ví dụ `decision(supported, permitted)` ở chương trình. Test integration thật mới kiểm chứng `ModuleFinder`, provider JCA, JSSE và module layout. Việc chỉ chạy trên full JDK của developer không chứng minh nhánh thiếu module/provider của production đã được xử lý.

Một lớp thiết kế nhỏ có thể giúp ích:

```java
// Trích đoạn kiến trúc; interface do ứng dụng định nghĩa.
interface CapabilityProbe {
    boolean isModuleResolved(String name);
    boolean hasDigestProvider(String algorithm);
    boolean supportsTlsProtocol(String protocol);
}
```

Với sản phẩm lớn, cân nhắc kết quả nhiều trạng thái thay cho chỉ `boolean` (supported, disabled, unavailable, error cùng nguyên nhân); không được ghi “unsupported” khi thực chất provider bị lỗi hoặc policy không cho phép.

## 12. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách thay thế |
| --- | --- | --- |
| Dùng `version >= N` để kết luận mọi API/provider có mặt. | Sai trên custom image, provider khác hoặc config bị tắt. | Probe đúng tầng và test thực thi. |
| So sánh chuỗi version. | Sai thứ tự cho các số có nhiều chữ số. | Dùng API version như metadata, không thay capability probe. |
| Chỉ kiểm tra `Class.forName`. | Có class nhưng phụ thuộc/quyền/provider hoặc method có thể thiếu. | Kiểm tra signature và chạy operation có giới hạn. |
| Nhầm module installed với resolved. | Tưởng module đã ở graph khi chưa có. | So `ModuleFinder.ofSystem` và `ModuleLayer` phù hợp. |
| Nhầm TLS supported với negotiated. | Ghi sai mức bảo mật kết nối. | Kiểm tra config endpoint và session sau handshake. |
| Thiếu `javac` và kết luận JVM “không đủ mới”. | Chẩn đoán sai custom runtime. | Probe tool provider và module packaging. |
| Bắt mọi exception rồi trả false. | Che lỗi code, policy, certificate, IO, service. | Bắt đúng lỗi unsupported, để lỗi khác báo rõ. |
| Tự thay thuật toán hoặc giao thức bảo mật. | Vi phạm hợp đồng, có thể làm giảm an toàn. | Chỉ fallback khi hợp đồng cho phép. |
| Dùng API mới direct-link trong artifact baseline cũ. | Compile/link/load fail trước khi guard chạy. | Adapter, reflection giới hạn hoặc nâng baseline. |
| Không kiểm thử image production. | Khác module, provider và permission so với máy build. | CI chạy trên đúng artifact/runtime image. |
| Chỉ probe một lần rồi tin mọi tài nguyên luôn sẵn. | Không xử lý network, file, credential đổi trạng thái. | Xử lý failure ở thời điểm thao tác. |

## 13. Câu hỏi tự luyện

1. Hai tiến trình đều hiển thị Java 21, nhưng chỉ một tiến trình có `java.net.http`. Hãy nêu cơ chế của `jlink` có thể tạo ra sự khác biệt và hai phép probe cần thực hiện.
2. Vì sao `SHA3-256` “được giới thiệu từ Java 9” không đủ để khẳng định một custom provider/environment sẽ thực hiện được thuật toán này?
3. Nếu `TLSv1.3` có trong supported nhưng không nằm trong enabled của một `SSLEngine`, bạn nên kết luận điều gì? Cần kiểm tra gì sau handshake?
4. Nếu business policy tắt chức năng nhưng implementation sẵn có, trạng thái là `UNAVAILABLE` hay `DISABLED_BY_POLICY`? Vì sao?
5. Một app phải chạy Java 17 nhưng muốn dùng `Thread.ofVirtual()` trên Java 21. Vì sao `--release 17` không cho gọi trực tiếp, và cách nào cho phép tiến hóa API an toàn?
6. Chạy `CapabilityCheckDemo` ở nhiều runtime: thêm log module installed/resolved, provider digest, tool provider. Vì sao các dòng PASS trong ví dụ không có nghĩa “mọi khả năng đều được bật”?
7. Vì sao `jdeps` không thể tìm hoàn toàn những provider được load qua reflection hoặc `ServiceLoader`? Bạn cần bước xác minh nào sau khi đóng gói image?

## Ghi nhớ

- **Version là metadata/baseline, capability là thuộc tính của môi trường và thao tác thực tế.**
- Kiểm tra riêng **module trong image**, **module đã resolve**, **implementation/provider**, **supported vs enabled**, **policy** và **operation**.
- Dùng API chính thức của JPMS, JCA, JSSE, `ServiceLoader`, `ToolProvider`; tránh đoán từ tên release hoặc provider.
- Khi feature thiếu, báo nguyên nhân đúng. Fallback chỉ được phép khi **hợp đồng và chính sách chấp nhận**.
- Biên dịch với `--release` phù hợp, chạy test trên runtime image thực và có cả negative tests.

### Tài liệu chuẩn đang áp dụng

- [Java SE 21 — Runtime.Version](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.Version.html) — `feature()` và cấu trúc thông tin phiên bản.
- [Java SE 21 — ModuleFinder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html), [ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html) — system module/image và module layer.
- [Java SE 21 — MessageDigest](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html) — thuật toán và provider JCA.
- [Java SE 21 — SSLContext](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/SSLContext.html) — danh sách supported và default-enabled.
- [Java SE 21 — ToolProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/spi/ToolProvider.html), [jdk.compiler](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/module-summary.html) — tool provider trong runtime.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html) — `Thread.ofVirtual()` từ Java 21.
- [Java SE 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html), [jlink](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html) — `--release` và runtime image tùy chỉnh.