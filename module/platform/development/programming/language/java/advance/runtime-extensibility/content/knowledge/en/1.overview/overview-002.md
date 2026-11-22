# Ứng dụng chủ, hợp đồng dịch vụ và phần mở rộng (plugin) liên hệ như thế nào?

## 1. Nhìn toàn cảnh

Một hệ thống có khả năng mở rộng lúc chạy (runtime extensibility) thường có ba vai trò:

- **Ứng dụng chủ (host application):** chương trình sở hữu luồng nghiệp vụ, giao diện, dữ liệu, cấu hình và quyết định khi nào cần một khả năng mở rộng.
- **Hợp đồng dịch vụ (service contract/SPI):** tập kiểu và quy tắc công khai xác định plugin có thể cung cấp khả năng gì, host được phép gọi gì và hai bên phải tuân thủ điều kiện nào.
- **Phần mở rộng (plugin/service provider):** thành phần triển khai hợp đồng đó, thường đóng gói riêng, có thể bổ sung hoặc thay thế cách thực hiện một chức năng mà không phải sửa mã nghiệp vụ của host.

Có thể hình dung mối quan hệ:

```text
                       gọi theo hợp đồng
   +------------------+ -------------------> +----------------------+
   | Ứng dụng chủ      |                      | Hợp đồng dịch vụ     |
   | chọn, điều phối,  |                      | Formatter (API/SPI)  |
   | quản lý lỗi       |                      +-----------+----------+
   +--------+---------+                                  ^
            |                                            | implements
            | khám phá, tải, chọn                        |
            +------------------------------------> +-----+--------------+
                                                  | Plugin A / Plugin B |
                                                  | các triển khai cụ thể|
                                                  +---------------------+
```

Mũi tên `gọi theo hợp đồng` diễn tả host làm việc qua giao diện đã biết. Plugin **triển khai** giao diện đó. Bước **khám phá và nạp** là cơ chế để host tìm được đối tượng triển khai; nó có thể dựa trên cấu hình, đăng ký thủ công, `ServiceLoader`, dependency injection hoặc một bộ quản lý plugin riêng.

Điểm cốt lõi: **host biết khả năng cần dùng và hợp đồng cần tuân thủ; host không cần biết trước tên lớp triển khai của từng plugin**. Vì vậy, có thể đưa thêm triển khai vào hệ thống mà vẫn giữ ổn định mã gọi dịch vụ.

## 2. Trách nhiệm và ranh giới của từng thành phần

| Thành phần | Sở hữu điều gì? | Không nên phụ thuộc trực tiếp vào điều gì? |
|---|---|---|
| Host | Luồng nghiệp vụ, lựa chọn plugin, cấu hình, dữ liệu, kiểm soát lỗi và quyền truy cập | Lớp triển khai cụ thể của plugin nếu có thể gọi qua hợp đồng |
| Service contract | Tên thao tác, kiểu tham số/kết quả, tiền điều kiện, hậu điều kiện, ngoại lệ, phiên bản tương thích | Chi tiết nội bộ hoặc thư viện riêng của một plugin |
| Plugin | Thuật toán/khả năng cụ thể, tài nguyên và phụ thuộc riêng, hành vi đáp ứng hợp đồng | Cấu trúc nội bộ không công khai của host |

**Hợp đồng không chỉ là một `interface`.** Ví dụ một dịch vụ chuyển đổi văn bản có thể phải quy định thêm mã định danh duy nhất, cách xử lý giá trị `null`, định dạng đầu ra, khả năng an toàn khi gọi đồng thời, trạng thái và vòng đời. Nếu hai bên chỉ khớp chữ ký phương thức nhưng hiểu khác ý nghĩa, plugin vẫn có thể gây lỗi nghiệp vụ.

Thuật ngữ cần phân biệt:

- **Service** là khả năng trừu tượng được mô tả bằng kiểu/hợp đồng, chẳng hạn `Formatter`.
- **Provider** là lớp/đối tượng thực thi service; với Java SPI, provider thường được tìm qua `ServiceLoader`.
- **Plugin** là đơn vị mở rộng có thể được phân phối, bật/tắt hoặc quản lý riêng. Một plugin có thể cung cấp nhiều provider và có mã phụ trợ; không phải mọi provider đều là một hệ plugin đầy đủ.
- **API** là phần lập trình công khai; **SPI** (Service Provider Interface) nhấn mạnh hợp đồng dành cho bên thứ ba triển khai. Cùng một giao diện Java có thể đóng cả hai vai trò trong ví dụ đơn giản.

## 3. Quan hệ phụ thuộc: ai biết ai?

Thiết kế phổ biến tách hợp đồng ra một thư viện nhỏ:

```text
             +------------------------+
             | shared-contract.jar    |
             | Formatter, kiểu dữ liệu|
             +------------+-----------+
                          ^
                phụ thuộc | phụ thuộc
                 +--------+--------+
                 |                 |
       +---------+------+  +-------+-----------+
       | host.jar       |  | upper-plugin.jar  |
       | chỉ gọi        |  | implements        |
       | Formatter      |  | Formatter         |
       +----------------+  +-------------------+
```

Ở **thời điểm biên dịch**, cả host và plugin biết chung hợp đồng, nhưng host không phải `import demo.plugin.UpperFormatter`. Ở **thời điểm chạy**, hệ thống cần thêm cách tìm và kết nối triển khai với hợp đồng. Việc nạp JAR không tự làm cho một lớp trở thành plugin; host phải có quy tắc đăng ký/khám phá và gọi nó.

Đây là ứng dụng của **đảo chiều phụ thuộc (Dependency Inversion)**: mã điều phối cấp cao không phụ thuộc vào chi tiết của thuật toán cụ thể; hai bên cùng dựa trên một hợp đồng ổn định. Host vẫn kiểm soát việc **chọn** provider, thứ tự xử lý, dữ liệu cấp cho plugin và hành vi khi không có provider phù hợp.

Ví dụ thực tế: một ứng dụng xuất báo cáo có hợp đồng `ReportExporter`. Plugin CSV và plugin JSON đều triển khai hợp đồng; host dựa vào định dạng người dùng chọn để gọi provider thích hợp. Bổ sung plugin PDF là bổ sung một triển khai và đăng ký mới, không phải viết nhánh `if/else` gắn chặt với một lớp PDF trong lõi ứng dụng.

## 4. Chuỗi hoạt động từ khởi động đến sử dụng

1. **Định nghĩa hợp đồng:** host hoặc nhóm sở hữu nền tảng công bố service type và quy tắc tương thích.
2. **Triển khai:** tác giả plugin viết lớp thực thi đúng hợp đồng, đóng gói phụ thuộc và siêu dữ liệu đăng ký.
3. **Triển khai plugin (deployment):** cung cấp artifact tại vị trí mà cơ chế nạp có thể nhìn thấy, ví dụ JAR trên classpath hoặc module path.
4. **Khám phá:** host lấy danh sách provider qua `ServiceLoader`, registry hoặc cơ chế khác.
5. **Kiểm tra và chọn:** host kiểm tra khả năng, cấu hình, phiên bản và các điều kiện cần trước khi sử dụng.
6. **Thực thi:** host truyền dữ liệu đầu vào theo hợp đồng và xử lý đầu ra/lỗi của provider.
7. **Quản lý vòng đời:** nếu hợp đồng có khởi tạo, đóng hoặc giải phóng tài nguyên, host điều phối các bước đó.

Ba vai trò trên là **mô hình kiến trúc**. `ServiceLoader` chỉ là một **công cụ khám phá provider** mà Java cung cấp; nó không tự giải quyết phân quyền, cách ly tiến trình, cập nhật nóng, quản lý phiên bản hay đóng tài nguyên.

## 5. Ví dụ Java 17+: host gọi plugin qua ServiceLoader

Ta xây dựng một dịch vụ định dạng chuỗi. Host chỉ biết `Formatter`; plugin cung cấp định dạng chữ hoa. Ví dụ dùng **classpath** để thể hiện rõ hai bên biên dịch riêng.

Cấu trúc tệp cần tạo:

```text
demo/
├── api/src/demo/spi/Formatter.java
├── host/src/demo/host/Main.java
└── plugin-upper/
    ├── src/demo/plugin/UpperFormatter.java
    └── resources/META-INF/services/demo.spi.Formatter
```

**Hợp đồng** — `api/src/demo/spi/Formatter.java`:

```java
package demo.spi;

public interface Formatter {
    String id();
    String format(String value);
}
```

`id()` là mã để host nhận diện khả năng; `format(String)` là thao tác host được phép gọi. Trong hệ thống thật, nên quy định `id` có duy nhất không và cách xử lý đầu vào bất thường.

**Plugin** — `plugin-upper/src/demo/plugin/UpperFormatter.java`:

```java
package demo.plugin;

import demo.spi.Formatter;
import java.util.Locale;

public final class UpperFormatter implements Formatter {
    public UpperFormatter() {
    }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String format(String value) {
        return value.toUpperCase(Locale.ROOT);
    }
}
```

Provider `UpperFormatter` triển khai hợp đồng và có constructor công khai không tham số, phù hợp với cách tạo provider trên classpath của Java `ServiceLoader`. `Locale.ROOT` giúp phép đổi chữ hoa có kết quả ổn định, không dựa trên locale mặc định của máy.

**Đăng ký provider** — tệp văn bản UTF-8 tên chính xác là `plugin-upper/resources/META-INF/services/demo.spi.Formatter`:

```text
demo.plugin.UpperFormatter
```

Tên **tệp** bằng tên đầy đủ của service interface; **nội dung** là tên lớp provider. Khi đóng gói JAR, phải giữ nguyên đường dẫn `META-INF/services/demo.spi.Formatter` trong JAR. Đây là cầu nối để `ServiceLoader` tìm được plugin trên classpath; chỉ triển khai `implements Formatter` mà thiếu tệp đăng ký thì ví dụ này không tự phát hiện provider.

**Host** — `host/src/demo/host/Main.java`:

```java
package demo.host;

import demo.spi.Formatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        int found = 0;

        for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
            System.out.println(
                formatter.id() + " -> " + formatter.format("hello plugin")
            );
            found++;
        }

        if (found == 0) {
            System.out.println("No formatter provider found");
        }
    }
}
```

Host không `import` lớp `UpperFormatter` hay gọi `new UpperFormatter()`. Host yêu cầu một service kiểu `Formatter`, duyệt các provider được tìm thấy và gọi chúng qua cùng hợp đồng.

**Biên dịch và chạy từ thư mục `demo` bằng PowerShell (Windows, JDK 17+):**

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\host,out\plugin | Out-Null

javac -d out\api api\src\demo\spi\Formatter.java
javac -cp out\api -d out\host host\src\demo\host\Main.java
javac -cp out\api -d out\plugin plugin-upper\src\demo\plugin\UpperFormatter.java

Copy-Item -Path plugin-upper\resources\META-INF -Destination out\plugin -Recurse
jar --create --file out\upper.jar -C out\plugin .

java -cp "out\api;out\host;out\upper.jar" demo.host.Main
```

Kết quả chuẩn với đúng một provider:

```text
upper -> HELLO PLUGIN
```

Thử chạy lại mà **bỏ plugin JAR khỏi classpath**:

```powershell
java -cp "out\api;out\host" demo.host.Main
```

Kết quả:

```text
No formatter provider found
```

Trên macOS/Linux, thay dấu phân cách classpath `;` bằng `:`; dùng đường dẫn `/` và lệnh tạo thư mục/sao chép tương đương. Các lệnh Java `javac` và `jar` vẫn cùng ý nghĩa.

**Điều ví dụ chứng minh:** mã host vẫn vậy trong cả hai lần chạy; sự khác biệt do provider có được triển khai và phát hiện hay không. Muốn thêm định dạng khác, viết thêm một provider thực thi `Formatter`, đăng ký và đưa JAR của nó vào môi trường chạy. Host chỉ cần thay đổi nếu yêu cầu nghiệp vụ về cách **chọn** plugin thay đổi.

## 6. Classpath, JPMS và giới hạn của việc khám phá

Với Java 9+ và **Java Platform Module System (JPMS)**, một provider nằm trong named module thường được công bố qua `provides ... with ...`; module sử dụng service khai báo `uses ...`. Ví dụ cấu trúc ý tưởng, **tách biệt với chương trình classpath ở mục 5**:

```java
// module-info.java trong module hợp đồng
module demo.api {
    exports demo.spi;
}
```

```java
// module-info.java trong module host
module demo.host {
    requires demo.api;
    uses demo.spi.Formatter;
}
```

```java
// module-info.java trong module provider
module demo.upper {
    requires demo.api;
    provides demo.spi.Formatter with demo.plugin.UpperFormatter;
}
```

Các file `module-info.java` trên minh họa cấu hình module; muốn chạy theo JPMS phải tổ chức và biên dịch lại thành các module tương ứng, đặt chúng trên module path. Với provider thuộc **named module tường minh**, khai báo `provides` mới là cơ chế đăng ký chính; tệp `META-INF/services` của ví dụ classpath không thay thế cho khai báo đó.

Những đặc tính đáng nhớ của `ServiceLoader`:

- Provider thường được **tìm và khởi tạo lười** khi duyệt loader, không có nghĩa tất cả plugin khởi tạo ngay tại lời gọi `load`.
- Một đối tượng `ServiceLoader` có thể lưu cache các provider đã được nạp. `reload()` làm mới bộ nhớ đệm/việc tìm kiếm của loader; **không bảo đảm** JAR mới được đưa vào classloader, không tự gỡ lớp đã nạp, và không tạo cơ chế hot-reload hoàn chỉnh.
- Provider lỗi, không tìm thấy lớp, sai kiểu hoặc không thể khởi tạo có thể gây `ServiceConfigurationError`. Host cần có chiến lược báo lỗi và cách xử lý phù hợp.
- Khi có nhiều provider, không nên mặc định thứ tự duyệt chính là thứ tự ưu tiên nghiệp vụ. Nếu cần chọn một provider, nên định nghĩa mã/khả năng, quy tắc phát hiện trùng, điều kiện chọn và chính sách fallback.

Nếu yêu cầu nạp JAR **sau khi host đã khởi động**, thay thế plugin mà không khởi động lại, hoặc cách ly các phiên bản thư viện, thường cần quản lý `ClassLoader`/`ModuleLayer` và vòng đời rõ ràng, hoặc một framework plugin phù hợp. Không nên suy diễn rằng có `ServiceLoader` là có thể cập nhật nóng an toàn.

## 7. Thiết kế hợp đồng để plugin có thể sống lâu

**Ổn định kiểu và ngữ nghĩa.** Cả hai bên phải dùng phiên bản hợp đồng tương thích. Đổi tên phương thức, đổi kiểu trả về hoặc thêm phương thức trừu tượng có thể làm plugin cũ không còn tương thích. Nên ưu tiên thay đổi có chủ đích, có phiên bản và thử nghiệm tương thích; không coi `default method` là giải pháp cho mọi thay đổi ngữ nghĩa.

**Giảm rò rỉ phụ thuộc.** Tránh đưa kiểu nội bộ của host hoặc kiểu từ thư viện triển khai riêng vào chữ ký service. Một hợp đồng nhỏ với kiểu dữ liệu ổn định dễ được plugin bên ngoài triển khai hơn.

**Xác định rõ khả năng.** Nếu có nhiều plugin cùng cung cấp một service, host có thể cần mã nhận diện, tên hiển thị, phiên bản, danh sách định dạng hỗ trợ và khả năng hoạt động. Dữ liệu này nên được cung cấp qua hợp đồng/siêu dữ liệu rõ ràng; tránh dựa vào tên lớp Java hoặc thứ tự tình cờ của classpath.

**Phân định quyền kiểm soát.** Plugin thực thi chức năng được giao; host quyết định dữ liệu và quyền hạn được chuyển vào, số lần gọi, timeout, retry, ghi log, lựa chọn provider và cách xử lý khi plugin thất bại. Không nên để plugin tự ý điều khiển toàn bộ luồng nghiệp vụ chỉ vì nó được nạp vào JVM.

**Quản lý tài nguyên.** Nếu plugin mở tệp, socket, thread hoặc kết nối, hợp đồng nên có cơ chế khởi tạo/đóng rõ ràng, chẳng hạn phương thức `close()` hoặc `AutoCloseable`. Ví dụ `Formatter` không cần bước đóng vì nó không giữ tài nguyên. Host phải xác định có dùng chung một instance giữa nhiều thread không; tính an toàn khi gọi đồng thời phải là phần của hợp đồng.

**Kiểm soát lỗi và quan sát.** Ghi nhận provider nào đang chạy, phiên bản nào, lỗi ở thao tác nào. Một plugin hỏng không nên khiến host hiểu nhầm rằng toàn bộ hệ thống không có provider; lỗi tải provider, lỗi khởi tạo và lỗi khi gọi hàm là các trường hợp khác nhau.

## 8. Tính mở rộng không đồng nghĩa với cách ly an toàn

Plugin Java được chạy trong cùng JVM thường có khả năng thực thi mã với quyền của tiến trình host. `ServiceLoader` **không phải cơ chế sandbox**. Chỉ nạp plugin từ nguồn tin cậy, kiểm soát phụ thuộc và quyền truy cập; nếu cần chạy mã bên thứ ba không đáng tin, nên cân nhắc cách ly bằng tiến trình/container và giao thức giao tiếp riêng.

Classloader tạo một ranh giới nạp lớp, nhưng không mặc nhiên là ranh giới bảo mật. Hai lớp có cùng tên đầy đủ nhưng do hai classloader khác nhau định nghĩa có thể là **hai kiểu khác nhau** ở JVM; điều này gây `ClassCastException` nếu host và plugin nạp bản sao tách biệt của chính interface hợp đồng. Thiết kế nạp động cần đảm bảo hai bên nhìn thấy **cùng định danh lớp của service contract**, thường bằng cách chia sẻ API từ một classloader cha thích hợp.

Plugin còn có thể có phụ thuộc thư viện xung đột phiên bản, chiếm nhiều CPU/bộ nhớ, tạo thread không kết thúc hoặc chặn I/O. Đó là trách nhiệm kiến trúc của host/plugin manager chứ không phải việc `interface` tự bảo vệ được.

## 9. Lỗi thiết kế thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
|---|---|---|
| Host gọi `new ConcretePlugin()` ở nhiều nơi | Lõi bị buộc vào triển khai cụ thể | Gọi qua service type và cơ chế lựa chọn provider |
| Có lớp `implements` nhưng không phát hiện được plugin | Thiếu/sai tệp `META-INF/services` hoặc khai báo `provides`, JAR không nằm ở nơi loader thấy | Kiểm tra đúng tên đầy đủ, đường dẫn đóng gói và môi trường chạy |
| Đổi interface làm plugin cũ lỗi | Hợp đồng thay đổi thiếu chính sách tương thích | Quản lý phiên bản API, kiểm thử plugin trên nhiều phiên bản host |
| Chọn provider đầu tiên được tìm thấy | Không có quy tắc ưu tiên nghiệp vụ | Chọn bằng mã/cấu hình/khả năng; kiểm tra trùng và thiếu |
| Gọi `reload()` rồi kỳ vọng hot-swap hoàn chỉnh | Nhầm quét lại service với thay classloader và giải phóng tài nguyên | Thiết kế cơ chế nạp/gỡ và vòng đời riêng |
| Plugin giữ tài nguyên sau khi ngừng dùng | Hợp đồng không có trách nhiệm đóng | Thêm lifecycle và chủ sở hữu việc đóng |
| Tin rằng plugin trong cùng JVM được cách ly an toàn | Nhầm cơ chế nạp lớp với ranh giới bảo mật | Chỉ dùng plugin tin cậy hoặc chuyển sang tiến trình tách biệt |

## 10. Tự kiểm tra hiểu biết

1. **Vì sao host nên import `Formatter` thay vì `UpperFormatter`?** Vì hợp đồng cho phép thay triển khai mà giữ nguyên mã gọi.
2. **Plugin có thể hoạt động nếu chỉ có JAR chứa lớp triển khai?** Chưa chắc. Host còn cần phát hiện/đăng ký và nạp provider theo đúng cơ chế đã chọn.
3. **Nếu bỏ `upper.jar` khỏi classpath ví dụ, điều gì thay đổi?** Host chạy được nhưng không tìm thấy provider, nên in `No formatter provider found`.
4. **Thêm một plugin có tự giải quyết xung đột ưu tiên không?** Không. Host cần quy tắc chọn provider nếu có nhiều kết quả phù hợp.
5. **`ServiceLoader` có tự bảo vệ host khỏi plugin độc hại hay cập nhật nóng JAR không?** Không. Bảo mật, quản lý phiên bản, vòng đời và nạp động là các vấn đề thiết kế bổ sung.

**Bài tập nhỏ:** Viết thêm `LowerFormatter` trả về chữ thường, đặt vào JAR riêng và đăng ký cùng service `demo.spi.Formatter`. Chạy host với một hoặc hai plugin JAR; quan sát mỗi provider được khám phá rồi bổ sung quy tắc chọn theo `id`. Việc này giúp thấy rõ ranh giới giữa **hợp đồng ổn định**, **nhiều triển khai** và **chính sách của host**.

## Tài liệu tham khảo

- Java SE 17, `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java Tutorials, `Creating Extensible Applications`: https://docs.oracle.com/javase/tutorial/ext/basics/spi.html

Khi đọc tài liệu Java cũ, chú ý cơ chế thư mục extensions trong những phiên bản JDK trước đây đã lỗi thời; ví dụ trên chủ động dùng classpath/JAR và JPMS của Java 17+.