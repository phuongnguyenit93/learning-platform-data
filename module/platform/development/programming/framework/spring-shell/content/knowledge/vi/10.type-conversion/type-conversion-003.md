# Đường dẫn, URL, UUID và các kiểu cần đối chiếu khả năng chuyển đổi

Command Spring Shell nhận dữ liệu từ dòng lệnh dưới dạng token văn bản, sau đó chuyển các token thành kiểu Java của tham số method. Những kiểu quen thuộc như số, boolean và enum thường có converter sẵn. Với các kiểu như `Path`, `URI`, `URL` hoặc `UUID`, cần biết Spring ConversionService hỗ trợ theo cách nào và kiểm tra trên đúng cấu hình Spring Shell của ứng dụng.

Điểm quan trọng là không suy luận rằng mọi lớp Java có constructor hoặc factory method đều chắc chắn chuyển đổi được. Spring Framework có một số converter tường minh và một converter theo quy ước; một kiểu như `Path` có thể cần converter riêng. Bài này tập trung vào cách phân biệt, kiểm tra và bổ sung conversion cho các giá trị thường gặp khi viết CLI quản lý file, tài nguyên và định danh.

## 1. Conversion diễn ra ở đâu trong luồng xử lý command?

Khi người dùng nhập:

```text
artifact inspect "./reports/monthly report.csv" --id 9f3d7a2e-5b6c-4a10-8d91-1b2c3d4e5f60 --endpoint https://api.example.com/v1/items
```

Spring Shell xử lý theo các bước tổng quát:

1. Parser tách dòng lệnh thành command path, argument và option. Dấu nháy giữ đường dẫn có dấu cách thành một token.
2. Command adapter xác định token nào được bind vào tham số `@Argument` hoặc `@Option`.
3. ConversionService chuyển chuỗi sang kiểu Java được khai báo trên method.
4. Nếu chuyển đổi thành công, Spring Shell gọi method command với các giá trị đã chuyển đổi.
5. Nếu conversion thất bại, command không nhận được giá trị hợp lệ; lỗi được báo cho người dùng.

Conversion chỉ biến đổi biểu diễn dữ liệu. Chuyển một chuỗi thành `Path` không có nghĩa file tồn tại; chuyển thành `URI` hoặc `URL` không có nghĩa máy chủ đang truy cập được; chuyển thành `UUID` không có nghĩa bản ghi mang ID đó tồn tại trong database.

## 2. Phân biệt `Path`, `URI`, `URL` và `UUID`

Các kiểu này biểu diễn những khái niệm khác nhau:

| Kiểu Java | Mục đích | Ví dụ biểu diễn |
|---|---|---|
| `java.nio.file.Path` | Đường dẫn file hoặc thư mục trên hệ thống file | `./reports/monthly.csv` |
| `java.net.URI` | Định danh tài nguyên theo cú pháp URI; có thể là tương đối hoặc tuyệt đối | `https://example.com/api/items`, `urn:isbn:...` |
| `java.net.URL` | Địa chỉ tài nguyên có giao thức và khả năng mở kết nối theo protocol handler | `https://example.com/manual.pdf` |
| `java.util.UUID` | Định danh duy nhất 128-bit | `9f3d7a2e-5b6c-4a10-8d91-1b2c3d4e5f60` |

Không dùng các kiểu này thay thế cho nhau. `Path` phụ thuộc hệ điều hành và hệ thống file. `URI` mô tả một định danh; `URL` hướng tới vị trí có thể truy cập bằng một giao thức. `UUID` là định danh dữ liệu, không phải đường dẫn hay địa chỉ mạng.

## 3. Spring ConversionService cung cấp những gì?

Spring Framework cung cấp `ConversionService` để chuyển đổi kiểu tại runtime. API cho phép kiểm tra khả năng chuyển đổi và thực hiện chuyển đổi:

```java
boolean canConvert(Class<?> sourceType, Class<?> targetType);
<T> T convert(Object source, Class<T> targetType);
```

`DefaultConversionService` đăng ký các converter phổ biến, bao gồm converter cho số, boolean, enum, collection và `UUID`. Nó cũng đăng ký `ObjectToObjectConverter`, một converter theo quy ước. Converter này có thể tìm:

- Method không static trên source có tên `to` cộng với tên kiểu đích, ví dụ `toTargetType()`.
- Factory method static `valueOf(sourceType)`, `of(sourceType)` hoặc `from(sourceType)` trên kiểu đích.
- Constructor của kiểu đích nhận đúng một tham số có kiểu bằng kiểu source.

Quy tắc theo quy ước giúp một số kiểu Java chuyển đổi được mà không cần viết converter riêng. Tuy nhiên, nó không tự hiểu mọi API factory của JDK. Chẳng hạn, một factory có tham số varargs không tương đương một factory nhận đúng một `String` theo quy tắc tìm method này.

## 4. Đối chiếu khả năng chuyển đổi của từng kiểu

Với Spring Framework 7 đi cùng dòng Spring Boot 4 và Spring Shell 4, có thể dùng bảng sau làm điểm xuất phát. Kết quả cuối cùng vẫn cần kiểm tra trên shell ConversionService thực tế của ứng dụng, vì ứng dụng có thể bổ sung hoặc thay thế converter.

| Kiểu đích | Cơ chế có thể dùng | Kết luận thực hành |
|---|---|---|
| `UUID` | Converter tường minh `StringToUUIDConverter` | Có hỗ trợ mặc định trong `DefaultConversionService`; chuỗi phải hợp lệ với `UUID.fromString` |
| `URI` | Constructor `URI(String)` được `ObjectToObjectConverter` phát hiện | Có thể chuyển đổi theo quy ước; chuỗi phải đúng cú pháp URI |
| `URL` | Constructor `URL(String)` có thể được `ObjectToObjectConverter` phát hiện | Có thể chuyển đổi theo quy ước, nhưng constructor này deprecated từ JDK 20; ưu tiên parse `URI` rồi gọi `toURL()` |
| `Path` | `Path.of(String, String...)` là factory varargs trên interface `Path` | Không nên giả định converter mặc định chuyển `String` sang `Path`; đăng ký converter riêng để có hành vi rõ ràng |
| `File` | Constructor `File(String)` | Có thể chuyển đổi theo quy ước; việc file có tồn tại hay không là kiểm tra riêng |

Đặc biệt, `UUID` được hỗ trợ bằng converter cụ thể, trong khi `URI` có thể dựa vào constructor theo quy ước. `URL` cũng có thể khớp constructor theo quy ước, nhưng JDK đã deprecated các constructor `URL` từ Java 20 và khuyến nghị dùng `URI` để parse rồi gọi `URI.toURL()`. `Path` là interface và factory `Path.of` nhận `String` cùng một mảng varargs, nên không khớp quy tắc tìm factory nhận đúng một tham số `String` của `ObjectToObjectConverter`.

Không nên chỉ nhìn bảng để kết luận converter đang có trong ứng dụng. Hãy gọi `canConvert(String.class, TargetType.class)` trên conversion service mà Spring Shell đang dùng và thử thực thi command. Điều này phát hiện được cả converter bổ sung, cấu hình custom và khác biệt phiên bản dependency.

## 5. Kiểm tra khả năng chuyển đổi trong Spring Shell

Spring Shell 4 có `ShellConversionServiceSupplier` để cung cấp ConversionService dành riêng cho shell. Có thể inject supplier này vào một bean chẩn đoán và kiểm tra các kiểu đích trước khi đưa command vào sử dụng:

```java
import java.net.URI;
import java.net.URL;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.shell.config.ShellConversionServiceSupplier;
import org.springframework.stereotype.Component;

@Component
class ConversionDiagnostics {

    private final ShellConversionServiceSupplier supplier;

    ConversionDiagnostics(ShellConversionServiceSupplier supplier) {
        this.supplier = supplier;
    }

    void reportCapabilities() {
        var conversionService = supplier.get();

        System.out.println("Path: " + conversionService.canConvert(String.class, Path.class));
        System.out.println("URI:  " + conversionService.canConvert(String.class, URI.class));
        System.out.println("URL:  " + conversionService.canConvert(String.class, URL.class));
        System.out.println("UUID: " + conversionService.canConvert(String.class, UUID.class));
    }
}
```

`canConvert` chỉ trả lời service có converter phù hợp cho cặp kiểu source/target hay không. Nó không xác nhận một chuỗi đầu vào cụ thể có hợp lệ. Ví dụ, service có thể chuyển `String` sang `URI`, nhưng chuỗi `"not a uri with spaces"` vẫn thất bại khi thực thi conversion.

Nếu cần kiểm tra một giá trị cụ thể, có thể gọi `convert` và xử lý lỗi:

```java
try {
    URI uri = conversionService.convert(
            "https://example.com/api/items",
            URI.class);
} catch (RuntimeException ex) {
    // Ghi nhận giá trị không chuyển đổi được và hướng dẫn người dùng.
}
```

Khi kiểm tra command, hãy chạy ứng dụng thật với cùng starter và dependency như môi trường triển khai. Một `DefaultConversionService` được tạo thủ công trong unit test có thể không chứa đúng những converter đã đăng ký cho Spring Shell.

## 6. Bổ sung converter cho `Path`

Khi command cần nhận đường dẫn dưới dạng `Path`, hãy đăng ký converter rõ ràng. Ví dụ dưới đây kiểm tra chuỗi rỗng và chuyển chuỗi còn lại bằng `Path.of`:

```java
import java.nio.file.Path;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
class StringToPathConverter implements Converter<String, Path> {

    @Override
    public Path convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException("Path must not be blank");
        }
        return Path.of(source);
    }
}
```

Đặt converter trong package được component scan của ứng dụng Spring Boot phát hiện để nó trở thành bean. Spring Shell dùng ConversionService riêng cho việc bind tham số command; hãy xác minh converter đã được đưa vào service đó bằng `canConvert` và bằng một command thử nghiệm. Nếu ứng dụng tự cung cấp shell ConversionService, cần đăng ký converter vào service tùy chỉnh ấy.

Converter trên chỉ tạo đối tượng `Path`. Nó không gọi `Files.exists`, không kiểm tra quyền đọc/ghi và không tạo thư mục. Tách các bước kiểm tra filesystem khỏi conversion để converter giữ đúng một trách nhiệm.

## 7. Dùng `Path` trong command

Sau khi đăng ký converter, có thể khai báo `Path` trực tiếp trên command:

```java
import java.nio.file.Files;
import java.nio.file.Path;

import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class FileCommands {

    @Command(name = "file inspect", description = "Kiểm tra file")
    public String inspect(
            @Argument(index = 0, description = "Đường dẫn file") Path path) {
        if (!Files.exists(path)) {
            return "Không tìm thấy: " + path;
        }
        if (!Files.isRegularFile(path)) {
            return "Đường dẫn không phải file thường: " + path;
        }
        if (!Files.isReadable(path)) {
            return "Không có quyền đọc: " + path;
        }
        return "File hợp lệ: " + path.toAbsolutePath();
    }
}
```

Gọi command với đường dẫn tương đối:

```text
file inspect ./reports/monthly.csv
```

Nếu đường dẫn có khoảng trắng, bao toàn bộ giá trị bằng dấu nháy:

```text
file inspect "./reports/monthly report.csv"
```

`Path.of` tạo đường dẫn theo quy tắc của hệ điều hành hiện tại. Đường dẫn tương đối được hiểu theo working directory của tiến trình; có thể dùng `toAbsolutePath()` để xem đường dẫn tuyệt đối tương ứng. `normalize()` chỉ chuẩn hóa thành phần `.` và `..` theo cú pháp, không xác minh đường dẫn tồn tại và không truy cập filesystem.

## 8. Dùng `URI` và `URL` đúng mục đích

`URI` thích hợp khi cần lưu hoặc phân tích một định danh tài nguyên. Nó có thể là URI tương đối, URI opaque hoặc URI tuyệt đối. `URL` biểu diễn địa chỉ gắn với một giao thức có khả năng truy cập tài nguyên. Từ Java 20, các constructor `URL` đã deprecated; API JDK khuyến nghị dùng `URI` để parse/construct rồi gọi `URI.toURL()` khi cần đối tượng URL.

Ví dụ command nhận URI:

```java
import java.net.URI;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "endpoint inspect", description = "Phân tích endpoint")
public String inspectEndpoint(
        @Option(longName = "uri", description = "URI cần kiểm tra") URI uri) {
    return "Scheme=" + uri.getScheme() + ", host=" + uri.getHost();
}
```

Lệnh:

```text
endpoint inspect --uri https://api.example.com/v1/items
```

Nếu method nghiệp vụ bắt buộc nhận `URL`, hãy đăng ký converter rõ ràng để tránh dựa vào constructor đã deprecated:

```java
import java.net.MalformedURLException;
import java.net.URI;
import java.net.URL;

import org.springframework.core.convert.converter.Converter;
import org.springframework.stereotype.Component;

@Component
class StringToUrlConverter implements Converter<String, URL> {

    @Override
    public URL convert(String source) {
        try {
            return URI.create(source).toURL();
        } catch (IllegalArgumentException | MalformedURLException ex) {
            throw new IllegalArgumentException("URL không hợp lệ: " + source, ex);
        }
    }
}
```

Sau khi converter được đăng ký vào shell ConversionService, command có thể nhận `URL`:

```java
import java.net.URL;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;

@Command(name = "endpoint open", description = "Kiểm tra địa chỉ endpoint")
public String inspectUrl(
        @Option(longName = "url", description = "URL cần kiểm tra") URL url) {
    return "Protocol=" + url.getProtocol() + ", host=" + url.getHost();
}
```

Hãy kiểm tra URL có scheme và host phù hợp với nghiệp vụ. Conversion thành công chỉ chứng minh chuỗi có thể tạo thành URL; nó không gửi HTTP request, không xác minh DNS, TLS hoặc trạng thái máy chủ. Nếu cần gọi endpoint, hãy thực hiện trong service nghiệp vụ bằng HTTP client có timeout, xử lý lỗi mạng và chính sách bảo mật phù hợp.

Đối với URL đầu vào, cân nhắc dùng `URI` làm kiểu biên để kiểm tra cú pháp và scheme trước, sau đó gọi `toURL()` khi thực sự cần một URL. URI có thể tương đối, trong khi chuyển URI thành URL cần một URI tuyệt đối có scheme hợp lệ.

## 9. Dùng `UUID` để nhận định danh

Spring Framework có converter mặc định từ `String` sang `UUID`. Ví dụ:

```java
import java.util.UUID;

import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;

@Command(name = "user show", description = "Xem người dùng theo ID")
public String showUser(
        @Argument(index = 0, description = "UUID người dùng") UUID userId) {
    return "User ID: " + userId;
}
```

Gọi command:

```text
user show 9f3d7a2e-5b6c-4a10-8d91-1b2c3d4e5f60
```

Nếu chuỗi không phải UUID hợp lệ, conversion thất bại trước khi method command chạy. Đừng tự parse UUID bằng `substring` hoặc tách chuỗi theo dấu gạch nối; dùng converter chuẩn để xử lý định dạng và nhận lỗi nhất quán.

Sau khi conversion thành công, vẫn cần kiểm tra ID có tồn tại trong hệ thống hay không:

```java
User user = userService.findById(userId)
        .orElseThrow(() -> new UserNotFoundException(userId));
```

UUID hợp lệ về cú pháp không đồng nghĩa có bản ghi tương ứng trong database.

## 10. Phân biệt conversion, validation và truy cập tài nguyên

Ba bước này giải quyết các vấn đề khác nhau:

| Bước | Câu hỏi | Ví dụ |
|---|---|---|
| Conversion | Chuỗi có chuyển thành kiểu Java được không? | `"..."` có parse thành `UUID` không? |
| Validation | Giá trị sau conversion có thỏa quy tắc đầu vào không? | Path có nằm trong thư mục được phép không? URI có scheme `https` không? |
| Kiểm tra tài nguyên/nghiệp vụ | Tài nguyên có tồn tại hoặc thao tác có được phép không? | File có đọc được không? UUID có thuộc về user hiện tại không? URL có phản hồi không? |

Ví dụ, một chuỗi có thể chuyển thành `Path` nhưng trỏ tới file không tồn tại. Một URI có thể hợp lệ về cú pháp nhưng dùng scheme mà ứng dụng không cho phép. Một UUID có thể parse thành công nhưng không tìm thấy người dùng. Không gộp các kiểm tra này vào một converter duy nhất.

Với dữ liệu không tin cậy, kiểm tra thêm giới hạn nghiệp vụ. Đặc biệt với file path, nếu command chỉ được phép thao tác trong một thư mục gốc, hãy chuẩn hóa và xác minh đường dẫn sau khi resolve với thư mục gốc. Chỉ kiểm tra `startsWith` trên chuỗi chưa chuẩn hóa có thể bỏ sót đường dẫn chứa `..`.

## 11. Xử lý lỗi conversion thân thiện

Khi converter từ chối giá trị, thông báo nên cho người dùng biết kiểu dữ liệu hoặc định dạng cần nhập. Với converter tự viết, ném `IllegalArgumentException` có thông điệp cụ thể thay vì trả `null` cho dữ liệu không hợp lệ.

Ví dụ:

```java
@Override
public Path convert(String source) {
    if (source == null || source.isBlank()) {
        throw new IllegalArgumentException("Hãy nhập đường dẫn file không rỗng");
    }
    try {
        return Path.of(source);
    } catch (RuntimeException ex) {
        throw new IllegalArgumentException("Đường dẫn không hợp lệ: " + source, ex);
    }
}
```

Không nên bắt mọi exception rồi trả `null`. `null` có thể khiến lỗi bị đẩy xuống tầng nghiệp vụ và làm nguyên nhân khó xác định. Giữ exception gốc làm cause để log và chẩn đoán khi cần.

Đối với URL/URI, thông báo có thể yêu cầu scheme cụ thể, ví dụ `https`. Đối với UUID, có thể hướng dẫn nhập dạng UUID chuẩn. Đối với Path, có thể nêu ví dụ đường dẫn tương đối hoặc tuyệt đối theo hệ điều hành.

## 12. Kiểm thử khả năng chuyển đổi

Hãy kiểm thử hai cấp:

**Kiểm thử converter:** xác nhận chuỗi hợp lệ tạo đúng đối tượng, chuỗi rỗng hoặc sai định dạng bị từ chối, và dữ liệu biên được xử lý như dự kiến.

**Kiểm thử tích hợp Spring Shell:** khởi chạy ứng dụng với cùng starter và cấu hình như production, gọi command bằng chuỗi đầu vào thực tế, rồi xác nhận method nhận đúng kiểu và đúng giá trị. Kiểm thử tích hợp sẽ phát hiện converter chưa được đăng ký vào shell ConversionService dù unit test converter riêng lẻ đã thành công.

Bảng ca kiểm thử gợi ý:

| Kiểu | Input hợp lệ | Input cần từ chối hoặc kiểm tra riêng |
|---|---|---|
| `Path` | `./reports/monthly.csv` | Chuỗi rỗng; đường dẫn có dấu cách; file không tồn tại; đường dẫn vượt thư mục gốc được phép |
| `URI` | `https://example.com/api` | URI sai cú pháp; URI tương đối nếu nghiệp vụ yêu cầu tuyệt đối; scheme không được phép |
| `URL` | `https://example.com/file.csv` | URL sai cú pháp; protocol không hỗ trợ; host không truy cập được (kiểm tra mạng riêng) |
| `UUID` | UUID có dạng chuẩn | Chuỗi thiếu nhóm ký tự hoặc chứa ký tự không hợp lệ; UUID hợp lệ nhưng không có bản ghi |

Đừng kiểm tra khả năng truy cập mạng trong unit test converter. Converter nên thực hiện chuyển đổi xác định, không tạo side effect như mở kết nối hoặc đọc file.

## 13. Bài tập thực hành

Xây dựng command `artifact inspect` cho một công cụ quản trị. Command nhận đường dẫn file, endpoint API và ID của artifact.

1. Khai báo positional argument `Path artifactPath`.
2. Khai báo option `URI endpoint`.
3. Khai báo option `UUID artifactId`.
4. Dùng `ShellConversionServiceSupplier` để kiểm tra `canConvert` cho `String` sang `Path`, `URI` và `UUID`.
5. Đăng ký `Converter<String, Path>` và xác nhận shell ConversionService nhận converter.
6. Gọi command với đường dẫn có khoảng trắng, endpoint HTTPS và UUID hợp lệ.
7. Thử UUID sai định dạng và URI có khoảng trắng không được quote/encode đúng.
8. Kiểm tra file tồn tại, quyền đọc và quy tắc thư mục gốc ở tầng nghiệp vụ.
9. Ghi rõ trường hợp nào là lỗi conversion, validation hay truy cập tài nguyên.

**Kết quả cần nộp:** source code command, converter cho `Path`, kết quả `canConvert`, các lệnh thử nghiệm và bảng phân loại lỗi theo ba tầng.

## 14. Checklist trước khi dùng kiểu dữ liệu đặc biệt

- [ ] Đã xác định kiểu Java phản ánh đúng khái niệm dữ liệu: `Path`, `URI`, `URL` hay `UUID`.
- [ ] Đã kiểm tra `canConvert(String.class, TargetType.class)` trên shell ConversionService thực tế.
- [ ] Đã phân biệt converter tường minh với conversion theo quy ước constructor/factory.
- [ ] Đã đăng ký converter riêng cho `Path` nếu service không hỗ trợ.
- [ ] Converter từ chối input rỗng hoặc sai định dạng bằng thông báo rõ ràng.
- [ ] Đã quote giá trị dòng lệnh có khoảng trắng.
- [ ] Đã kiểm tra scheme/host của URI hoặc URL theo yêu cầu nghiệp vụ.
- [ ] Đã tách conversion khỏi kiểm tra file tồn tại, quyền truy cập và kết nối mạng.
- [ ] Đã kiểm tra UUID có bản ghi tương ứng ở tầng nghiệp vụ.
- [ ] Đã chạy kiểm thử tích hợp bằng đúng Spring Shell starter và cấu hình runtime.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation — Command Syntax](https://docs.spring.io/spring-shell/reference/commands/syntax.html)
- [Spring Shell API — `ShellConversionServiceSupplier`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/config/ShellConversionServiceSupplier.html)
- [Spring Shell API — `MethodInvokerCommandAdapter`](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/adapter/MethodInvokerCommandAdapter.html)
- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework API — `DefaultConversionService`](https://docs.spring.io/spring-framework/docs/7.0.0/javadoc-api/org/springframework/core/convert/support/DefaultConversionService.html)
- [Spring Framework source — `ObjectToObjectConverter`](https://github.com/spring-projects/spring-framework/blob/main/spring-core/src/main/java/org/springframework/core/convert/support/ObjectToObjectConverter.java)
- [Java API — `Path`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Path.html)
- [Java API — `URI`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html)
- [Java API — `URL` (constructor deprecated; use `URI.toURL()`)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URL.html)
- [Java API — `UUID`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html)
