# Giữ hợp đồng plugin nhỏ, tránh để lộ thư viện nội bộ của plugin

Một hệ thống mở rộng lúc chạy (runtime extensibility) thường có hai bên được phát hành, cập nhật và nạp vào JVM theo nhịp khác nhau: **host** (ứng dụng cung cấp điểm mở rộng) và **plugin** (thành phần thực hiện khả năng mới). Điểm chung bắt buộc giữa hai bên là **hợp đồng mở rộng**: một tập nhỏ các kiểu, hành vi và quy tắc mà cả host lẫn plugin cùng hiểu. Nếu hợp đồng buộc host biết chi tiết thư viện JSON, HTTP, database hay engine của từng plugin, mỗi lần plugin đổi cách triển khai có thể kéo theo thay đổi ở host và các plugin khác.

Mục tiêu của bài này là thiết kế ranh giới đủ nhỏ, có kiểu dữ liệu rõ ràng, để host gọi plugin qua API ổn định; thư viện, cấu hình và cấu trúc triển khai của plugin được giữ phía sau ranh giới đó.

## 1. Phân biệt hợp đồng với phần triển khai

Giả sử host muốn cung cấp chức năng biến đổi văn bản do nhiều plugin đăng ký.

| Phần | Thuộc hợp đồng dùng chung | Thuộc triển khai riêng |
| --- | --- | --- |
| Khả năng | Giao diện TextPlugin với thao tác transform | Thuật toán biến đổi, bộ đệm, cách gọi dịch vụ |
| Dữ liệu | TextRequest, TextResult do module API định nghĩa | ObjectMapper, JsonNode, HTTP client, DTO của nhà cung cấp |
| Khám phá | Tên service và quy tắc nạp provider | Tên lớp nội bộ, cấu trúc package và thư viện hỗ trợ |
| Lỗi | Quy ước lỗi mà host có thể xử lý | Ngoại lệ chuyên biệt, stack trace, cơ chế retry bên trong |
| Phiên bản | Mức tương thích API và khả năng được công bố | Phiên bản thư viện mà một plugin tự dùng |

**Hợp đồng nhỏ** nghĩa là ít trách nhiệm, ổn định và liên quan trực tiếp tới điểm mở rộng; không có nghĩa là thay mọi kiểu bằng Object hay Map<String, Object>. Những kiểu quá chung khiến việc kiểm tra, nâng cấp và hiểu lỗi khó hơn. Ngược lại, đẩy toàn bộ khả năng của một framework vào một interface cũng làm hợp đồng phình to.

### Ví dụ rò rỉ phụ thuộc cần tránh

Đoạn sau **chỉ minh họa thiết kế sai**, không phải chương trình độc lập có thể biên dịch:

~~~java
// API công khai của host: thiết kế KHÔNG nên dùng.
public interface TextPlugin {
    com.fasterxml.jackson.databind.JsonNode transform(
            com.vendor.plugin.internal.EngineSession session,
            com.fasterxml.jackson.databind.JsonNode request);
}
~~~

Ở đây, host và mọi plugin muốn dùng interface phải biết các kiểu thuộc Jackson và một thư viện nội bộ của plugin. Thay engine, đổi phiên bản JSON library hoặc nạp nhiều phiên bản thư viện trong các classloader khác nhau có thể làm API mất tương thích; bản thân lớp EngineSession cũng đã bị biến thành một phần cam kết công khai.

Thiết kế tốt hơn chuyển đổi dữ liệu **tại ranh giới**: phía host truyền một request thuộc API chung; plugin tự dịch request đó thành đối tượng của thư viện mà nó chọn, sau đó dịch kết quả về response chung. Không đưa thư viện nội bộ vào tham số, kiểu trả về, generic, callback, sự kiện hoặc kiểu ngoại lệ công khai.

## 2. Thiết kế hợp đồng tối thiểu nhưng có ý nghĩa

Với ví dụ biến đổi văn bản, module độc lập **plugin-api** có thể chỉ cần ba kiểu:

~~~java
// src/api/example/ext/api/TextRequest.java
package example.ext.api;

import java.util.Objects;

public record TextRequest(String text) {
    public TextRequest {
        Objects.requireNonNull(text, "text");
    }
}
~~~

~~~java
// src/api/example/ext/api/TextResult.java
package example.ext.api;

import java.util.Objects;

public record TextResult(String text) {
    public TextResult {
        Objects.requireNonNull(text, "text");
    }
}
~~~

~~~java
// src/api/example/ext/api/TextPlugin.java
package example.ext.api;

public interface TextPlugin {
    String id();
    TextResult transform(TextRequest request);
}
~~~

Các record trên có dữ liệu rõ nghĩa, chỉ dùng Java chuẩn, không phụ thuộc framework của host hay plugin; kiểm tra null ở biên giúp phát hiện đầu vào sai sớm. Chúng bất biến đối với trường String. Nếu request mang List hoặc Map, cần quy định tính bất biến, sao chép phòng vệ khi cần và cách biểu diễn giá trị; record **không tự làm collection bên trong bất biến**.

Hai quyết định quan trọng:

1. Host sở hữu và phát hành module hợp đồng. Plugin biên dịch dựa trên **cùng phiên bản tương thích của hợp đồng**; không sao chép hoặc đóng gói một bản TextPlugin khác vào classloader riêng.
2. Mỗi phương thức phản ánh một năng lực thực sự cần chia sẻ. Không cho plugin quyền truy cập nguyên ApplicationContext, DataSource, ClassLoader hoặc toàn bộ nội bộ host chỉ để làm một việc nhỏ. Nếu plugin cần dịch vụ từ host, cung cấp một interface capability hẹp, ví dụ Clock hoặc một cổng ghi log có giới hạn.

Không nên đưa thao tác chỉ dành cho một plugin vào interface mà tất cả plugin bắt buộc triển khai. Có thể giới thiệu một **interface khả năng tùy chọn** và để host kiểm tra sự hỗ trợ, thay vì thêm dồn phương thức trừu tượng vào hợp đồng gốc.

## 3. Ví dụ chạy được trên Java 17: host chỉ biết API

Cấu trúc tệp của ví dụ:

~~~text
src/
  api/example/ext/api/
    TextRequest.java
    TextResult.java
    TextPlugin.java
  plugin/example/ext/impl/
    UppercasePlugin.java
  plugin/META-INF/services/
    example.ext.api.TextPlugin
  host/example/ext/host/
    App.java
~~~

Ba tệp API chính là mã ở mục 2. Plugin cung cấp implementation và một helper **private**. Trong dự án thật, helper này có thể dùng một thư viện bên thứ ba, nhưng kiểu của thư viện ấy không xuất hiện trong TextPlugin, TextRequest hoặc TextResult.

~~~java
// src/plugin/example/ext/impl/UppercasePlugin.java
package example.ext.impl;

import example.ext.api.TextPlugin;
import example.ext.api.TextRequest;
import example.ext.api.TextResult;
import java.util.Locale;

public final class UppercasePlugin implements TextPlugin {
    private final UppercaseEngine engine = new UppercaseEngine();

    public UppercasePlugin() { }

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public TextResult transform(TextRequest request) {
        return new TextResult(engine.apply(request.text()));
    }

    private static final class UppercaseEngine {
        String apply(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

Tệp service descriptor có **đúng một dòng tên lớp đầy đủ**, không phải Java:

~~~text
# src/plugin/META-INF/services/example.ext.api.TextPlugin
example.ext.impl.UppercasePlugin
~~~

Dòng bắt đầu bằng dấu # trong khối trên chỉ là chú giải để chỉ vị trí tệp; **nội dung thực tế của tệp chỉ là** example.ext.impl.UppercasePlugin và ký tự xuống dòng. Tên tệp descriptor phải trùng tên nhị phân đầy đủ của service interface.

Host tìm implementation qua ServiceLoader và chỉ làm việc với API:

~~~java
// src/host/example/ext/host/App.java
package example.ext.host;

import example.ext.api.TextPlugin;
import example.ext.api.TextRequest;
import example.ext.api.TextResult;
import java.util.ServiceLoader;

public final class App {
    public static void main(String[] args) {
        boolean found = false;

        for (TextPlugin plugin : ServiceLoader.load(TextPlugin.class)) {
            found = true;
            TextResult result = plugin.transform(
                    new TextRequest("hello plugin"));
            System.out.println(plugin.id() + " -> " + result.text());
        }

        if (!found) {
            throw new IllegalStateException("No TextPlugin provider found");
        }
    }
}
~~~

Từ thư mục chứa src, chạy các lệnh sau trong shell kiểu Bash (cần JDK 17 trở lên):

~~~bash
mkdir -p out/api out/plugin out/host
javac --release 17 -encoding UTF-8 -d out/api src/api/example/ext/api/TextRequest.java src/api/example/ext/api/TextResult.java src/api/example/ext/api/TextPlugin.java
jar --create --file out/plugin-api.jar -C out/api .
javac --release 17 -encoding UTF-8 -cp out/plugin-api.jar -d out/plugin src/plugin/example/ext/impl/UppercasePlugin.java
jar --create --file out/plugin.jar -C out/plugin . -C src/plugin META-INF/services
javac --release 17 -encoding UTF-8 -cp out/plugin-api.jar -d out/host src/host/example/ext/host/App.java
java -cp "out/host:out/plugin-api.jar:out/plugin.jar" example.ext.host.App
~~~

Output khi chỉ có provider này:

~~~text
upper -> HELLO PLUGIN
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy thay vì dấu hai chấm. Ví dụ lệnh chạy tương ứng:

~~~powershell
java -cp "out/host;out/plugin-api.jar;out/plugin.jar" example.ext.host.App
~~~

**Điều được chứng minh:** mã host chỉ import ba kiểu trong example.ext.api và ServiceLoader; host không cần import UppercasePlugin, UppercaseEngine hoặc thư viện xử lý nội bộ. Plugin có thể thay engine riêng mà giữ nguyên API và kết quả hợp đồng. Khi chỉ có một provider, output trên là xác định; nếu đăng ký nhiều provider, không nên phụ thuộc vào thứ tự duyệt mặc định của ServiceLoader.

**Giới hạn của ví dụ:** các JAR đang cùng application classpath, vì vậy mã có thể vẫn nhìn thấy lớp public của nhau ở mức classpath. Việc không tham chiếu implementation là **kỷ luật kiến trúc**, chưa phải cơ chế cô lập vật lý hoặc sandbox bảo mật. Khi cần cô lập phiên bản thư viện, có thể dùng classloader riêng; khi cần đóng gói theo module, JPMS giúp chỉ xuất package API được chỉ định.

## 4. Phụ thuộc và classloader: giữ một danh tính API chung

Một bố trí phụ thuộc hợp lý:

~~~text
host ───────────────> plugin-api
                           ^
                           |
plugin-implementation -----+
        |
        +----> thư viện bên thứ ba riêng của plugin
~~~

Host biên dịch với plugin-api, không với implementation hay thư viện bên thứ ba của plugin. Plugin biên dịch với plugin-api, nhưng triển khai thuật toán bằng phụ thuộc riêng. Với Gradle, chọn khai báo phụ thuộc theo vai trò: thư viện chỉ phục vụ implementation thuộc cấu hình implementation; hợp đồng dùng chung được cung cấp ở cả hai phía theo chính sách đóng gói, có thể là compileOnly đối với plugin nếu runtime đã cung cấp plugin-api. Dùng implementation thay vì api cho thư viện nội bộ **không tự sửa được một chữ ký public đã lỡ dùng kiểu của thư viện ấy**: phải sửa chính chữ ký.

Trong JVM, danh tính lớp phụ thuộc vào **tên nhị phân và classloader định nghĩa lớp**. Hai lớp cùng tên example.ext.api.TextPlugin nhưng được hai classloader khác nhau định nghĩa không trở thành cùng một kiểu. Plugin đóng gói lại bản copy API hoặc nạp API bằng loader riêng có thể khiến ServiceLoader báo provider không phải subtype, hoặc gây lỗi ép kiểu/liên kết.

Khi thiết kế hệ thống dùng loader riêng:

- Chia sẻ **một định nghĩa API** mà host và plugin cùng nhìn thấy, thường từ parent loader; tránh shade/relocate các lớp hợp đồng vào JAR plugin.
- Cho mỗi plugin sở hữu implementation và các thư viện hỗ trợ của chính nó khi cần cô lập phụ thuộc. Quy tắc parent-first/child-first phải được đặt có chủ đích; ưu tiên chia sẻ package API từ parent.
- Xác định classloader dùng cho khám phá service và tài nguyên. ServiceLoader.load(service) theo mặc định dùng thread context classloader; nó phải nhìn thấy provider descriptor và các lớp provider tương ứng.
- Quản lý vòng đời loader, thread, executor, static reference và tài nguyên do plugin tạo; nếu không giải phóng, việc unload/reload có thể giữ classloader cũ trong bộ nhớ.

Cô lập classloader giúp quản lý phụ thuộc và vòng đời nhưng **không tạo ra ranh giới bảo mật đáng tin cậy cho mã không đáng tin** trong cùng JVM.

Với JPMS, module API chỉ exports các package hợp đồng; module plugin có thể provides service mà không exports package implementation. Ví dụ ý tưởng cấu hình (khác cơ chế classpath trong demo):

~~~java
// module-info.java của module API
module example.plugin.api {
    exports example.ext.api;
}
~~~

~~~java
// module-info.java của module plugin
module example.plugin.uppercase {
    requires example.plugin.api;
    provides example.ext.api.TextPlugin
        with example.ext.impl.UppercasePlugin;
}
~~~

~~~java
// module-info.java của module host
module example.plugin.host {
    requires example.plugin.api;
    uses example.ext.api.TextPlugin;
}
~~~

Để chạy trong module path, phải biên dịch và đóng gói theo quy tắc JPMS và đưa module provider vào layer/module path phù hợp; ba đoạn module-info trên **không phải lệnh thay thế trực tiếp** cho demo classpath. Trong JPMS, exports/opens và ServiceLoader là các lựa chọn thiết kế cần xét riêng.

## 5. Tương thích hợp đồng qua nhiều lần phát hành

Một plugin có thể được biên dịch từ trước và chỉ được nạp sau khi host cập nhật. Vì vậy cần xét **tương thích nguồn, nhị phân và ngữ nghĩa**; không chỉ xem mã mới còn biên dịch được hay không.

| Thay đổi | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Đổi tên, package, kiểu tham số/kiểu trả về của phương thức API | Có thể phá ABI, gây lỗi liên kết runtime | Giữ API cũ hoặc nâng major và có đường chuyển đổi |
| Thêm phương thức abstract vào interface đã có provider cũ | Provider cũ có thể gặp AbstractMethodError khi host gọi | Ưu tiên interface khả năng mới; cân nhắc default method nếu ngữ nghĩa hợp lý |
| Thêm thành phần vào public record | Thay đổi canonical constructor, có thể làm hỏng binary client cũ | Lập phiên bản DTO hoặc thiết kế luồng mở rộng có kiểm soát |
| Thay kiểu ngoại lệ/giá trị trả về về mặt hành vi | Mã host có thể xử lý sai dù ABI không đổi | Ghi rõ quy tắc null, lỗi, timeout, retry và trường hợp biên |
| Nâng version thư viện trong implementation | Thường không cần sửa API nếu không rò kiểu | Test lại hành vi và tính tương thích loader của plugin |

Nếu cần khả năng bổ sung, có thể định nghĩa interface khác trong plugin-api, ví dụ TextPluginMetrics, và để host dùng kiểm tra kiểu hoặc đăng ký capability tường minh. Điều đó cho phép plugin cũ tiếp tục cung cấp năng lực cơ bản. Các version/capability nên có chính sách rõ ràng: host chấp nhận dải phiên bản nào, từ chối khi nào, thông báo lỗi cho ai. SemVer hữu ích nhưng không thay thế kiểm thử nhị phân thực tế.

**Lỗi và tài nguyên cũng là một phần hợp đồng.** Không khai báo throws một kiểu exception thuộc SDK riêng của plugin, không bắt host đọc một exception nội bộ. Chọn kiểu lỗi chung hoặc chính sách chuyển đổi exception ở biên. Xác định plugin có được gọi đồng thời hay không, ai sở hữu đối tượng request/result, thời hạn gọi, quy tắc huỷ và đóng tài nguyên khi unload. Chỉ thêm các phương thức vòng đời khi nhiều plugin thực sự cần chung quy tắc đó.

## 6. Kiểm tra ranh giới trước khi phát hành

1. **Kiểm tra chữ ký công khai:** duyệt các public/protected method, constructor, field, generic, annotation và ngoại lệ của module plugin-api. Không cho xuất hiện package thuộc implementation, SDK, ORM, JSON, HTTP client hoặc lớp nội bộ host.
2. **Kiểm tra đồ thị phụ thuộc:** host phải biên dịch khi chỉ có plugin-api, không có plugin implementation hoặc JAR nội bộ của plugin. Module plugin-api tự nó không kéo theo thư viện implementation. Có thể dùng jdeps --summary out/plugin-api.jar để rà soát phụ thuộc JAR.
3. **Kiểm tra đăng ký provider:** tên file META-INF/services và tên lớp đầy đủ chính xác, provider có thể được khởi tạo, JAR và resource thực sự nằm trong runtime path. Với classpath ServiceLoader, provider cần lớp triển khai phù hợp và public constructor không tham số.
4. **Kiểm tra tương thích:** chạy provider cũ với host mới trong phạm vi version hỗ trợ, provider mới với host cũ nếu tuyên bố tương thích; kiểm tra dữ liệu null, lỗi, timeout, gọi song song và thiếu provider.
5. **Kiểm tra loader thực tế:** đảm bảo host và plugin dùng cùng class identity của API; thử hai plugin dùng các phiên bản thư viện implementation khác nhau; kiểm tra reload và giải phóng tài nguyên khi có hỗ trợ unload.

Một số dấu hiệu để điều tra: ServiceConfigurationError khi service descriptor/provider sai hoặc không nạp được; NoClassDefFoundError khi thiếu phụ thuộc runtime; ClassCastException hoặc lỗi service subtype khi chia cắt API qua loader; NoSuchMethodError/AbstractMethodError khi ABI của host và plugin lệch. Cần đọc nguyên nhân đầy đủ trong stack trace, không tự quy mọi trường hợp về một nguyên nhân.

## 7. Quy tắc thiết kế có thể áp dụng ngay

Trước khi thêm một kiểu hoặc phương thức vào plugin-api, hỏi: **host thực sự cần biết điều này để sử dụng năng lực hay chỉ cần plugin tự biết để triển khai?** Nếu chỉ phần triển khai cần, giữ nó sau adapter và chuyển đổi request/result tại biên. Ưu tiên interface nhỏ theo capability, DTO ổn định không mang kiểu của thư viện riêng, version rõ ràng và một danh tính lớp API dùng chung. Chỉ mở rộng hợp đồng sau khi kiểm tra ảnh hưởng lên plugin đã phát hành.

Một hợp đồng tốt cho phép thay thư viện, thay thuật toán hoặc nạp thêm plugin mà host vẫn gọi cùng một giao diện đã công bố; từ đó giảm liên kết chéo và làm cho runtime extensibility có thể nâng cấp an toàn hơn.