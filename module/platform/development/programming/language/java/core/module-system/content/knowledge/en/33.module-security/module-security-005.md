# Provider service và code implementation cần tin cậy

## 1. Service provider là một ranh giới tin cậy

Trong Java Platform Module System (JPMS), Service Provider Interface (SPI) cho phép một module định nghĩa contract, còn các module khác cung cấp implementation. Consumer thường tìm implementation bằng `ServiceLoader` thay vì phụ thuộc trực tiếp vào class provider.

Cơ chế này giúp mở rộng ứng dụng, nhưng cũng tạo ra một quyết định bảo mật quan trọng: **provider là code sẽ được nạp và thực thi bên trong ứng dụng**.

Ví dụ, một ứng dụng có thể tìm formatter, database driver, plugin hoặc bộ xử lý file từ các provider có trên module path. Khi provider được khởi tạo và method của nó được gọi, implementation có thể thực hiện các thao tác mà tiến trình Java được phép thực hiện, chẳng hạn:

- Đọc file mà tài khoản chạy ứng dụng có quyền truy cập.
- Gửi dữ liệu qua mạng.
- Đọc biến môi trường hoặc cấu hình mà tiến trình nhìn thấy.
- Tạo thread, sử dụng CPU và bộ nhớ.
- Gọi các thư viện khác hoặc khởi tạo kết nối tới hệ thống bên ngoài.

Vì vậy, việc một module khai báo `provides` hợp lệ hoặc được `ServiceLoader` tìm thấy không chứng minh implementation đó an toàn. Chỉ nạp provider từ nguồn đã được đánh giá và phê duyệt.

## 2. Module encapsulation không phải sandbox

JPMS cung cấp ranh giới module để quản lý readability, exports, opens và dependency. Các cơ chế này giúp giới hạn API mà module khác có thể truy cập theo quy tắc Java, nhưng **không cô lập quyền thực thi của provider khỏi tiến trình**.

Ví dụ:

```java
module com.acme.provider {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.JsonFormatter;
}
```

Directive `provides` đăng ký implementation cho service type. Nó không giới hạn provider chỉ được đọc một thư mục, không tự chặn kết nối mạng và không ngăn provider đọc biến môi trường.

Tương tự:

- Package không được `exports` sẽ bị giới hạn truy cập theo module rules, nhưng provider vẫn có thể gọi các API công khai khác mà tiến trình được phép dùng.
- `opens` điều khiển reflective access tới package, không phải cơ chế sandbox.
- Một `ModuleLayer` hoặc class loader riêng giúp tổ chức và nạp class, nhưng bản thân chúng không tạo ranh giới bảo mật tương đương một tiến trình hệ điều hành riêng.

Đừng coi việc đặt provider vào module riêng là đủ để chạy code không đáng tin cậy một cách an toàn.

## 3. Luồng service và vị trí provider được thực thi

Giả sử có service contract:

```java
package com.acme.spi;

public interface Formatter {
    String format(String input);
}
```

Module SPI:

```java
module com.acme.spi {
    exports com.acme.spi;
}
```

Provider implementation:

```java
package com.acme.provider.json;

import com.acme.spi.Formatter;

public final class JsonFormatter implements Formatter {
    public JsonFormatter() {
    }

    @Override
    public String format(String input) {
        return "{\"value\":\"" + input + "\"}";
    }
}
```

Provider module:

```java
module com.acme.provider.json {
    requires com.acme.spi;

    provides com.acme.spi.Formatter
        with com.acme.provider.json.JsonFormatter;
}
```

Consumer module:

```java
module com.acme.app {
    requires com.acme.spi;

    uses com.acme.spi.Formatter;
}
```

Consumer tìm và gọi provider:

```java
import com.acme.spi.Formatter;
import java.util.ServiceLoader;

ServiceLoader<Formatter> services =
        ServiceLoader.load(Formatter.class);

for (Formatter formatter : services) {
    String result = formatter.format("hello");
    System.out.println(result);
}
```

Việc gọi `ServiceLoader.load` tạo cơ chế tra cứu service. Provider thường được nạp và khởi tạo lười khi duyệt kết quả; constructor hoặc provider method có thể chạy ở thời điểm đó. Khi consumer gọi `format`, implementation thực thi trong tiến trình consumer.

Vì vậy, cả giai đoạn discovery, khởi tạo và gọi method đều cần được xem xét trong threat model. Không nên cho rằng chỉ gọi một interface là thao tác vô hại.

## 4. Chỉ đưa artifact từ nguồn đáng tin vào module path

Bước bảo vệ đầu tiên là kiểm soát nguồn JAR và dependency được đưa vào ứng dụng.

Nên áp dụng các biện pháp sau:

- Chỉ lấy artifact từ repository hoặc registry nội bộ/nhà cung cấp đã được phê duyệt.
- Ghim phiên bản dependency cụ thể; tránh tải phiên bản thay đổi tùy ý trong lúc khởi động production.
- Xác minh checksum từ một kênh tin cậy độc lập với nơi tải artifact.
- Xác minh chữ ký và danh tính người phát hành khi hệ thống phân phối có cung cấp chữ ký.
- Review thay đổi source, dependency bắc cầu, lịch sử phát hành và quyền mà provider cần.
- Quét lỗ hổng dependency và lưu Software Bill of Materials (SBOM) cho bản phát hành.
- Dùng build có thể tái lập và quy trình review/publish có kiểm soát khi phù hợp.

Có thể tính SHA-256 cho JAR:

```bash
sha256sum provider-json.jar
```

Trên PowerShell:

```powershell
Get-FileHash .\provider-json.jar -Algorithm SHA256
```

So sánh kết quả với checksum được công bố qua kênh tin cậy. Hash chỉ xác nhận file có khớp với bản đã biết; nó không chứng minh bản đó không có mã độc.

Nếu artifact được ký, có thể kiểm tra chữ ký JAR:

```bash
jarsigner -verify -verbose -certs provider-json.jar
```

Cần kiểm tra kết quả xác minh và danh tính certificate theo chính sách trust của tổ chức. Một chữ ký hợp lệ cho biết nội dung đã ký không bị thay đổi kể từ lúc ký và gắn với khóa ký tương ứng; nó không chứng minh code bên trong an toàn. Certificate tự ký hoặc signer chưa được tin cậy cũng không tự trở thành đáng tin chỉ vì chữ ký đúng.

## 5. Kiểm soát provider được phép chạy

Không nên tự động chạy mọi provider có mặt trên module path nếu ứng dụng chỉ mong đợi một tập implementation nhỏ.

Thiết kế một allowlist dựa trên artifact/module đã được phê duyệt, ví dụ:

```text
Approved providers
- module: com.acme.provider.json
  artifact: com.acme:provider-json
  version: 2.4.1
  sha256: <verified digest>
- module: com.acme.provider.xml
  artifact: com.acme:provider-xml
  version: 1.8.0
  sha256: <verified digest>
```

Đây là cấu hình minh họa; digest phải được lấy từ quy trình phát hành thực tế, không điền giá trị giả.

Trước khi tạo module layer hoặc khởi chạy ứng dụng, xác định chính xác các module provider được phép nằm trong deployment. Không cho người dùng cuối tùy ý đặt một JAR bất kỳ vào thư mục plugin đang được tự động quét.

Nếu cần lọc provider ở tầng consumer, có thể kiểm tra loại provider trước khi gọi `get()`:

```java
import com.acme.spi.Formatter;
import java.util.Set;
import java.util.ServiceLoader;

Set<String> approvedTypes = Set.of(
        "com.acme.provider.json.JsonFormatter"
);

ServiceLoader<Formatter> services =
        ServiceLoader.load(Formatter.class);

for (ServiceLoader.Provider<Formatter> candidate
        : services.stream().toList()) {
    String typeName = candidate.type().getName();

    if (!approvedTypes.contains(typeName)) {
        continue;
    }

    Formatter formatter = candidate.get();
    System.out.println(formatter.format("hello"));
}
```

Đoạn code này minh họa cách chỉ khởi tạo provider có tên type được chấp nhận. Tuy nhiên, allowlist class name **không xác thực nguồn gốc artifact**: một JAR khác có thể cung cấp class cùng tên. Hãy xác minh artifact, module và checksum trước khi provider được đưa vào runtime; lọc trong consumer chỉ là lớp kiểm soát bổ sung.

Không dựa vào thứ tự duyệt của `ServiceLoader` để chọn provider ưu tiên. Nếu ứng dụng cần một implementation duy nhất, hãy chọn bằng cấu hình rõ ràng và báo lỗi khi provider được cấu hình không tồn tại hoặc không được phê duyệt.

## 6. Cấp ít dữ liệu và quyền nhất cho provider

SPI nên có contract nhỏ, rõ ràng và chỉ truyền dữ liệu cần thiết cho nhiệm vụ.

Ví dụ, nếu provider chỉ cần định dạng một chuỗi, không truyền toàn bộ application context, database connection, credential store hoặc đối tượng quản trị hệ thống vào implementation.

Nên:

- Dùng DTO chứa dữ liệu tối thiểu thay vì truyền object có quá nhiều quyền.
- Không đưa password, access token hoặc secret vào constructor, system property hay log.
- Tách interface đọc dữ liệu và interface thực hiện thay đổi nếu provider chỉ cần một trong hai quyền.
- Xác thực input trước khi gọi provider và kiểm tra output trước khi sử dụng.
- Đặt giới hạn kích thước input/output và số lượng công việc nếu service xử lý dữ liệu lớn.
- Tránh để provider giữ tham chiếu tới mutable object hoặc shared state không cần thiết.

Ví dụ contract có thể giới hạn khả năng:

```java
public interface DocumentFormatter {
    byte[] format(ReadOnlyDocument input);
}
```

Nếu provider chỉ cần đọc document, cung cấp abstraction chỉ đọc thay vì object có quyền sửa file gốc hoặc truy cập toàn bộ filesystem.

Tuy nhiên, interface hẹp chỉ giảm quyền mà ứng dụng chủ động trao qua API. Nó không ngăn provider tự gọi API hệ thống mà tiến trình có quyền sử dụng.

## 7. Xử lý lỗi và hành vi không ổn định

Provider có thể ném exception, trả dữ liệu sai, khởi tạo thất bại hoặc tiêu thụ quá nhiều tài nguyên.

Khi dùng `ServiceLoader`, cần xử lý lỗi ở ranh giới tích hợp:

```java
import com.acme.spi.Formatter;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

try {
    ServiceLoader<Formatter> services =
            ServiceLoader.load(Formatter.class);

    for (Formatter formatter : services) {
        try {
            String result = formatter.format("hello");
            validateResult(result);
        } catch (RuntimeException error) {
            reportProviderFailure(error);
        }
    }
} catch (ServiceConfigurationError error) {
    reportProviderConfigurationFailure(error);
}
```

Các method `validateResult`, `reportProviderFailure` và `reportProviderConfigurationFailure` là phần xử lý riêng của ứng dụng. Ví dụ này minh họa vị trí đặt error boundary, không thay thế chính sách retry hoặc phục hồi phù hợp với từng service.

Lưu ý:

- `ServiceConfigurationError` có thể xuất hiện khi cấu hình provider không hợp lệ hoặc khi provider không thể được nạp/khởi tạo.
- Provider có thể ném runtime exception khi xử lý request; cần xác định lỗi nào có thể bỏ qua và lỗi nào phải dừng request.
- Không nên bắt mọi `Throwable` rồi tiếp tục như không có gì xảy ra; các lỗi nghiêm trọng của JVM cần được xử lý theo chính sách của ứng dụng.
- Log tên provider, phiên bản artifact và correlation ID để truy vết, nhưng không ghi payload nhạy cảm hoặc secret.
- Không retry mù các thao tác có side effect; retry có thể lặp giao dịch hoặc gửi dữ liệu nhiều lần.

Timeout ở thread gọi không thể đảm bảo dừng một provider đang chạy code đồng bộ trong cùng JVM. Nếu cần giới hạn cứng thời gian CPU, bộ nhớ hoặc khả năng chấm dứt provider, hãy chuyển nó sang tiến trình riêng.

## 8. Khi nào cần chạy provider trong process riêng?

Nếu provider đến từ bên thứ ba chưa đủ tin cậy, cho phép người dùng tải plugin tùy ý hoặc xử lý dữ liệu có độ nhạy cao, nên cân nhắc kiến trúc out-of-process.

```text
Main application
      |
      | IPC / HTTP / message protocol
      v
Provider worker process
      |
      +-- dedicated OS user
      +-- restricted filesystem
      +-- restricted network
      +-- CPU / memory limits
      +-- independent lifecycle
```

Tiến trình worker có thể được chạy bằng tài khoản hệ điều hành riêng, container hoặc sandbox của nền tảng triển khai với:

- Chỉ mount thư mục dữ liệu cần thiết.
- Chặn outbound network nếu provider không cần truy cập mạng.
- Giới hạn CPU, memory, process count và thời gian xử lý.
- Truyền dữ liệu qua protocol có schema và giới hạn kích thước.
- Xác thực hai đầu giao tiếp và kiểm tra mọi message.
- Có thể restart hoặc terminate worker mà không làm sập toàn bộ ứng dụng.

IPC cũng có rủi ro riêng: cần xác thực caller, bảo vệ dữ liệu truyền, kiểm soát message replay nếu phù hợp và giới hạn tài nguyên. Nhưng tiến trình riêng tạo được ranh giới OS mà module hoặc class loader trong cùng JVM không cung cấp.

## 9. Quản lý cập nhật và vòng đời provider

Provider đáng tin tại thời điểm phát hành vẫn có thể thay đổi ở bản cập nhật sau. Vì vậy cần quản lý vòng đời:

1. Ghim version và checksum của từng provider trong release manifest.
2. Review thay đổi dependency và quyền trước khi nâng cấp.
3. Kiểm tra tương thích service contract và module descriptor.
4. Chạy test chức năng, bảo mật và hiệu năng với đúng artifact sẽ phát hành.
5. Chỉ cập nhật provider qua pipeline được phê duyệt.
6. Ghi nhận module, version, digest và nguồn phát hành trong log/telemetry.
7. Có quy trình rollback nếu provider mới lỗi hoặc có lỗ hổng.

Không nên tải JAR mới từ URL do request người dùng cung cấp rồi nạp trực tiếp vào ứng dụng production. Nếu hỗ trợ cài plugin động, hãy tách quy trình tải, xác minh, review và kích hoạt thành các bước có kiểm soát.

## 10. Checklist bảo mật trước khi bật một provider

- [ ] Artifact đến từ repository/registry được phê duyệt.
- [ ] Version và checksum khớp release manifest đáng tin cậy.
- [ ] Chữ ký được kiểm tra theo trust policy nếu artifact có ký.
- [ ] Source, dependency bắc cầu và lịch sử phát hành đã được xem xét.
- [ ] Module/provider nằm trong allowlist của deployment.
- [ ] Service contract chỉ cấp dữ liệu và capability tối thiểu.
- [ ] Input/output được kiểm tra và có giới hạn tài nguyên phù hợp.
- [ ] Lỗi khởi tạo và lỗi khi gọi service được ghi nhận an toàn.
- [ ] Không ghi secret hoặc dữ liệu nhạy cảm vào log.
- [ ] Provider chưa đủ tin cậy được cô lập trong tiến trình riêng.
- [ ] Version, digest và nguồn provider được lưu để audit/rollback.

## Ghi nhớ

- Provider được `ServiceLoader` nạp là code thực thi trong tiến trình ứng dụng.
- JPMS encapsulation, `ModuleLayer` và class loader không phải sandbox bảo mật.
- Chỉ đưa artifact từ nguồn được phê duyệt vào module path; xác minh version, checksum và chữ ký theo trust policy.
- Allowlist provider giúp kiểm soát lựa chọn, nhưng class name không chứng minh nguồn gốc JAR.
- Cấp dữ liệu/capability tối thiểu, xác thực input/output và xử lý lỗi ở ranh giới service.
- Nếu không thể tin cậy hoàn toàn provider, chạy nó trong process riêng với quyền hệ điều hành và tài nguyên bị giới hạn.
