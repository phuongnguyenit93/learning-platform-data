# Cân đối dung lượng runtime với locale, charset và công cụ chẩn đoán cần dùng

## 1. Vì sao runtime image cần được cân đối?

`jlink` cho phép tạo runtime image chỉ chứa module và tài nguyên mà ứng dụng cần. Một image nhỏ hơn thuận tiện cho phân phối, giảm dung lượng tải xuống và giảm số thành phần phải quản lý. Tuy nhiên, loại bỏ module chỉ để giảm kích thước có thể làm mất dữ liệu locale, bộ chuyển đổi charset hoặc công cụ chẩn đoán cần cho vận hành.

Khi thiết kế runtime, hãy phân loại nhu cầu thành ba nhóm:

- **Locale:** dữ liệu định dạng ngày giờ, số, tiền tệ, quy tắc sắp xếp và quy tắc ngôn ngữ theo vùng.
- **Charset:** bộ mã hóa/ký tự cần để đọc và ghi dữ liệu từ hệ thống bên ngoài.
- **Chẩn đoán:** công cụ quan sát JVM, thu thập thông tin tiến trình và ghi nhận sự kiện khi điều tra sự cố.

Không phải ứng dụng nào cũng cần toàn bộ ba nhóm. Hãy xác định nhu cầu từ tính năng thực tế, tạo image tương ứng rồi kiểm thử trên chính runtime sẽ phát hành.

## 2. Các module thường liên quan

| Nhu cầu | Module thường cần xem xét | Vai trò |
| --- | --- | --- |
| Dữ liệu locale mở rộng | `jdk.localedata` | Cung cấp locale data ngoài locale US |
| Charset bổ sung | `jdk.charsets` | Cung cấp các charset không nằm trong `java.base` |
| Công cụ chẩn đoán JVM | `jdk.jcmd` | Cung cấp các công cụ như `jcmd`, `jps` và `jstat` |
| Java Flight Recorder | `jdk.jfr` | API ghi và đọc sự kiện Flight Recorder |
| Quản lý JVM | `jdk.management` | Các giao diện quản lý đặc thù của JDK |
| JMX management agent | `jdk.management.agent` | Agent quản lý JMX khi ứng dụng cần cơ chế này |
| Giao diện giám sát đồ họa | `jdk.jconsole` | Công cụ JConsole, chỉ cần khi môi trường vận hành thực sự dùng |

Các module JDK trên có mục đích riêng. Không thêm tất cả vào mọi runtime. Ví dụ, ứng dụng web không có giao diện đồ họa thường không cần `jdk.jconsole`; ứng dụng chỉ dùng UTF-8 cũng thường không cần `jdk.charsets`.

## 3. Locale data và module jdk.localedata

`java.base` cung cấp dữ liệu nền tảng cần thiết cho locale mặc định và locale US. Module `jdk.localedata` cung cấp locale data cho các locale khác. Nếu ứng dụng cần định dạng tiếng Việt, Nhật, Pháp hoặc những vùng khác, hãy kiểm tra locale mà ứng dụng thực sự sử dụng.

`jlink` có plugin `--include-locales` để giới hạn locale data được đưa vào runtime image. Giá trị là BCP 47 language tag và hỗ trợ locale matching theo RFC 4647. Khi dùng plugin này, phải thêm `jdk.localedata` vào module roots.

Ví dụ ứng dụng cần tiếng Việt Việt Nam và tiếng Anh Mỹ:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,jdk.localedata --include-locales=vi-VN,en-US --compress=zip-6 --no-header-files --no-man-pages --output build\runtime
~~~

Trong ví dụ:

- `com.example.app` là module ứng dụng.
- `jdk.localedata` cung cấp dữ liệu locale ngoài US.
- `--include-locales=vi-VN,en-US` giới hạn dữ liệu locale theo nhu cầu.
- `--compress=zip-6` nén tài nguyên trong runtime image bằng mức nén hiện hành.
- `--no-header-files` và `--no-man-pages` bỏ các file header native và trang hướng dẫn không cần cho runtime ứng dụng.

Nếu ứng dụng cần nhiều locale, hãy liệt kê các language tag cần hỗ trợ. Có thể dùng pattern được hỗ trợ bởi RFC 4647 khi yêu cầu triển khai bao gồm một nhóm locale; không dùng wildcard rộng nếu mục tiêu là giới hạn kích thước.

Nếu bỏ `jdk.localedata`, việc chỉ ghi `--include-locales` không thể bổ sung dữ liệu locale còn thiếu. Nếu thêm `jdk.localedata` nhưng không giới hạn locale, image có thể mang theo nhiều locale data hơn nhu cầu.

## 4. Kiểm thử locale sau khi tạo runtime

Đừng chỉ xác nhận module `jdk.localedata` có trong image. Hãy kiểm tra các thao tác ứng dụng thực sự thực hiện:

~~~java
import java.text.NumberFormat;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class LocaleSmokeTest {
    public static void main(String[] args) {
        Locale vietnamese = Locale.forLanguageTag("vi-VN");
        Locale englishUs = Locale.forLanguageTag("en-US");

        System.out.println(
                NumberFormat.getCurrencyInstance(vietnamese)
                        .format(1234567.89));

        System.out.println(
                DateTimeFormatter.ofLocalizedDate(
                        java.time.format.FormatStyle.LONG)
                        .withLocale(vietnamese)
                        .format(LocalDate.of(2026, 11, 27)));

        System.out.println(
                NumberFormat.getCurrencyInstance(englishUs)
                        .format(1234567.89));
    }
}
~~~

Chạy chương trình bằng `java` nằm trong runtime image và xác nhận kết quả đúng với yêu cầu giao diện/nghiệp vụ. Nên kiểm tra thêm:

- Định dạng số thập phân, phân nhóm và tiền tệ.
- Định dạng ngày giờ và tên tháng.
- So sánh/sắp xếp chuỗi nếu ứng dụng dùng `Collator`.
- Locale được chọn từ cấu hình hoặc theo người dùng.
- Hành vi fallback khi locale không có trong danh sách được đóng gói.

Không so sánh chuỗi định dạng bằng một kết quả cố định nếu ứng dụng hỗ trợ nhiều phiên bản JDK hoặc nhà cung cấp runtime. Hãy kiểm tra ngữ nghĩa và các yêu cầu hiển thị cần thiết.

## 5. Charset cơ bản và module jdk.charsets

`java.base` cung cấp các charset chuẩn thường dùng, trong đó có UTF-8 và UTF-16. Module `jdk.charsets` bổ sung các charset không nằm trong `java.base`, gồm một số bộ mã đa byte và bộ mã theo nhà cung cấp.

Nếu ứng dụng chỉ trao đổi dữ liệu UTF-8, thường không cần thêm `jdk.charsets`. Hãy chỉ thêm module này khi một hệ thống tích hợp hoặc định dạng dữ liệu được hỗ trợ yêu cầu charset nằm ngoài `java.base`.

Ví dụ thêm module charset vào runtime:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,jdk.charsets --compress=zip-6 --no-header-files --no-man-pages --output build\runtime
~~~

Trước khi thêm module, xác định charset thực sự cần bằng API:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class CharsetSmokeTest {
    public static void main(String[] args) {
        System.out.println(StandardCharsets.UTF_8.name());
        System.out.println(Charset.isSupported("UTF-8"));

        String requiredCharset = "UTF-8";
        if (!Charset.isSupported(requiredCharset)) {
            throw new IllegalStateException(
                    "Missing charset: " + requiredCharset);
        }
    }
}
~~~

Nếu tích hợp yêu cầu một charset cụ thể ngoài `java.base`, thay `UTF-8` trong ví dụ bằng tên charset đã được hệ thống đích thống nhất, rồi kiểm tra `Charset.isSupported` trên runtime image.

## 6. Ghi rõ charset khi đọc và ghi dữ liệu

Đừng để khả năng đọc/ghi file phụ thuộc ngầm vào charset mặc định của máy. Hãy chỉ rõ charset tại ranh giới dữ liệu:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class TextFileExample {
    public static void main(String[] args) throws Exception {
        Path file = Path.of("data", "message.txt");

        Files.writeString(
                file,
                "Xin chào Java",
                StandardCharsets.UTF_8);

        String content = Files.readString(
                file,
                StandardCharsets.UTF_8);

        System.out.println(content);
    }
}
~~~

UTF-8 là charset chuẩn có trong `java.base`. JDK 18 trở lên mặc định dùng UTF-8 theo JEP 400, nhưng ứng dụng cần tương thích với runtime Java 16 hoặc môi trường có cấu hình khác vẫn nên chỉ định charset tường minh. Điều này giúp kết quả không phụ thuộc hệ điều hành hoặc cấu hình máy.

Module `jdk.charsets` không phải cách sửa lỗi mojibake do đọc file bằng charset sai. Trước tiên phải xác định encoding thật của dữ liệu và dùng đúng charset khi giải mã; chỉ thêm module khi charset đó không có trong `java.base`.

## 7. Công cụ chẩn đoán JVM và module jdk.jcmd

Một runtime image tối giản có thể không chứa các lệnh phục vụ điều tra sự cố. Module `jdk.jcmd` cung cấp nhóm công cụ chẩn đoán như `jcmd`, `jps` và `jstat`.

Các lệnh này hữu ích trong môi trường vận hành:

- `jcmd` gửi diagnostic command tới JVM đang chạy và lấy thông tin như phiên bản VM, trạng thái hoặc dữ liệu phục vụ điều tra.
- `jps` liệt kê các tiến trình Java mà người dùng hiện tại có thể quan sát.
- `jstat` theo dõi một số chỉ số của JVM.

Nếu đội vận hành cần chạy công cụ trực tiếp từ runtime image, thêm `jdk.jcmd`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,jdk.jcmd --compress=zip-6 --no-header-files --no-man-pages --output build\diagnostic-runtime
~~~

Sau khi tạo image, kiểm tra các lệnh thực sự có trong thư mục `bin`:

~~~powershell
Get-ChildItem build\diagnostic-runtime\bin
~~~

Không giả định chỉ cần thêm module là mọi native command đều được giữ lại. Nếu dùng `--strip-native-commands`, các lệnh native có thể bị loại khỏi image; hãy bỏ tùy chọn này trong diagnostic image và xác nhận các công cụ cần thiết còn tồn tại.

## 8. Java Flight Recorder và quản lý JVM

`jdk.jfr` cung cấp API Java Flight Recorder để ghi nhận sự kiện JVM và ứng dụng. Nếu ứng dụng gọi trực tiếp API JFR hoặc đội vận hành cần khả năng ghi/đọc sự kiện bằng runtime phân phối, hãy đánh giá việc thêm module này.

Ví dụ tạo image có JFR API và công cụ chẩn đoán:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,jdk.jcmd,jdk.jfr,jdk.management --compress=zip-6 --no-header-files --no-man-pages --output build\observability-runtime
~~~

Chỉ thêm `jdk.management.agent` nếu ứng dụng thực sự cần JMX management agent, chẳng hạn để hỗ trợ quản trị từ xa theo chính sách bảo mật đã cấu hình. Chỉ thêm `jdk.jconsole` nếu môi trường vận hành có nhu cầu sử dụng công cụ giao diện đồ họa và runtime đích hỗ trợ.

Trong nhiều hệ thống production, lựa chọn hợp lý là giữ runtime ứng dụng gọn và dùng một JDK công cụ tương thích từ môi trường quản trị để chạy lệnh chẩn đoán. Không nhất thiết mọi máy người dùng phải nhận các công cụ phát triển hoặc giao diện giám sát.

## 9. Không loại bỏ dữ liệu cần cho điều tra sự cố

Một số tùy chọn giảm kích thước có ảnh hưởng đến khả năng chẩn đoán:

| Tùy chọn | Tác động | Khi nên dùng |
| --- | --- | --- |
| `--compress=zip-6` | Nén tài nguyên trong image | Lựa chọn cân bằng thường phù hợp; đo lại kích thước và thời gian khởi động |
| `--no-header-files` | Bỏ header phục vụ phát triển native | Thường phù hợp với runtime chỉ dùng để chạy ứng dụng |
| `--no-man-pages` | Bỏ trang hướng dẫn công cụ | Phù hợp với image phân phối cho người dùng cuối |
| `--strip-debug` | Loại thông tin debug như source file và line number khỏi class file | Chỉ dùng khi chấp nhận mất một phần thông tin hữu ích cho stack trace và debugger |
| `--strip-native-commands` | Loại các native command khỏi runtime image | Không dùng nếu cần gọi `jcmd` hoặc công cụ native từ chính image |

Đặc biệt, `--strip-debug` có thể khiến stack trace thiếu tên file nguồn và số dòng cho các lớp bị strip. Nếu đội vận hành dựa vào stack trace hoặc debugger để phân tích lỗi, hãy giữ debug information trong diagnostic image.

Có thể tạo hai cấu hình runtime:

- **Production image:** chỉ chứa module và locale/charset cần cho tính năng; tối ưu kích thước sau khi đã kiểm thử.
- **Diagnostic image:** bổ sung `jdk.jcmd`, `jdk.jfr` và các module quản lý cần thiết; giữ native commands và debug information theo yêu cầu điều tra.

Hai image có thể dùng cùng mã ứng dụng và cùng quy trình build, nhưng phải được kiểm thử riêng để tránh khác biệt không mong muốn.

## 10. Ví dụ chọn module theo nhu cầu

Ứng dụng có module chính `com.example.app`, cần locale Việt Nam và tiếng Anh Mỹ, chỉ dùng UTF-8, nhưng muốn giữ công cụ chẩn đoán cơ bản trong image:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app,jdk.localedata,jdk.jcmd,jdk.jfr --include-locales=vi-VN,en-US --compress=zip-6 --no-header-files --no-man-pages --output build\runtime
~~~

Nếu ứng dụng còn cần charset ngoài `java.base`, thêm `jdk.charsets` sau khi xác nhận bằng test. Nếu không cần công cụ chẩn đoán trong runtime, bỏ `jdk.jcmd` và `jdk.jfr` để giảm thành phần được phân phối.

Nếu tạo diagnostic image, tránh `--strip-native-commands` và cân nhắc không dùng `--strip-debug`. Nếu tạo production image, chỉ bật các tùy chọn strip sau khi xác định rõ khả năng chẩn đoán mà hệ thống vẫn cần.

## 11. Đo kích thước và xác nhận nội dung runtime

Không nên đánh giá image chỉ bằng số module. Dung lượng phụ thuộc module, tài nguyên locale, charset, native library, mức nén và nền tảng build.

Trên Windows PowerShell, đo tổng dung lượng file trong image:

~~~powershell
$bytes = (Get-ChildItem build\runtime -Recurse -File |
    Measure-Object -Property Length -Sum).Sum
"Runtime size: {0:N1} MiB" -f ($bytes / 1MB)
~~~

Sau đó xem module được liên kết:

~~~powershell
build\runtime\bin\java.exe --list-modules
~~~

Với runtime có công cụ chẩn đoán, kiểm tra thư mục `bin` để xác nhận `jcmd` và các lệnh cần thiết tồn tại. Với runtime locale, chạy chương trình định dạng ngày giờ/số cho từng locale đã chọn. Với runtime charset, chạy kiểm tra đọc/ghi bằng encoding thực tế.

Hãy lưu lại dung lượng image và kết quả smoke test cho từng profile build. Khi cập nhật JDK hoặc dependency, chạy lại kiểm tra vì module graph và nội dung runtime có thể thay đổi.

## 12. Checklist trước khi phát hành

- Xác định locale người dùng thực sự cần và thêm `jdk.localedata` khi cần.
- Dùng `--include-locales` với BCP 47 tags phù hợp; không đóng gói tất cả locale nếu không có lý do.
- Xác định charset của từng tích hợp; ưu tiên UTF-8 tường minh và chỉ thêm `jdk.charsets` khi cần charset ngoài `java.base`.
- Xác định công cụ chẩn đoán cần có trong runtime; thêm `jdk.jcmd`, `jdk.jfr` hoặc module quản lý phù hợp.
- Không strip native commands nếu cần chạy công cụ chẩn đoán từ image.
- Không strip debug information nếu cần line number và source file trong stack trace hoặc debugger.
- Kiểm tra module bằng `--list-modules` và lệnh thực tế trong thư mục `bin`.
- Chạy test locale, charset, service và chức năng ứng dụng trên image cuối.
- Đo dung lượng image trên đúng nền tảng sẽ phân phối.
- Duy trì kế hoạch cập nhật runtime image khi nâng JDK hoặc dependency.

**Ghi nhớ:** Runtime nhỏ cần đúng dữ liệu và công cụ cho môi trường sử dụng. `jdk.localedata` cùng `--include-locales` giúp giới hạn locale; `jdk.charsets` chỉ cần khi ứng dụng dùng charset ngoài `java.base`; `jdk.jcmd` và `jdk.jfr` phục vụ chẩn đoán. Đo kích thước, kiểm tra module và chạy smoke test trên runtime image thực tế trước khi phát hành.

## Nguồn tham khảo chính thức

- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [JDK 26 Module Summary](https://docs.oracle.com/en/java/javase/26/docs/api/)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [Java Flight Recorder — JDK 26](https://docs.oracle.com/en/java/javase/26/jfapi/flight-recorder-api-programming-guide.pdf)
