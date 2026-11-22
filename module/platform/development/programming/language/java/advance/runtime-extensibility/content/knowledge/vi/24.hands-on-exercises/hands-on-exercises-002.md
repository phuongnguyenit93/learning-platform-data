# Thêm lựa chọn provider theo khả năng hỗ trợ và cấu hình người dùng

## 1. Mục tiêu bài thực hành

Trong ứng dụng Java có kiến trúc plugin, **ServiceLoader** giúp phát hiện nhiều implementation của cùng một service interface. Nhưng việc phát hiện provider **không đồng nghĩa** có thể chọn bừa provider đầu tiên: một provider có thể chỉ xuất HTML, một provider chỉ hỗ trợ plain text, một provider có tính năng màu sắc, trong khi người dùng có yêu cầu và lựa chọn ưu tiên riêng.

Bài thực hành này xây dựng một **ReportProvider** SPI. Host sẽ nạp provider bằng **ServiceLoader**, sau đó lựa chọn dựa trên:

1. **Định dạng đầu ra bắt buộc** từ cấu hình người dùng: text, markdown hoặc html.
2. **Các capability bắt buộc**: ví dụ unicode, heading, color. Provider chỉ hợp lệ nếu hỗ trợ **tất cả** các capability được yêu cầu.
3. **Preferred provider**: người dùng có thể yêu cầu ưu tiên một provider có ID ổn định.
4. **Strict preference**: nếu bật, không được âm thầm dùng provider khác khi provider được chọn không phù hợp.
5. **Fallback có kiểm soát**: nếu strict tắt, preferred provider không phù hợp thì chọn một provider hợp lệ khác theo chính sách rõ ràng.
6. **Thứ tự xác định**: khi còn nhiều lựa chọn hợp lệ, dùng priority giảm dần và ID tăng dần thay vì phụ thuộc thứ tự phát hiện service.

Kết thúc bài, chương trình Java 17 sẽ chạy được với ba provider độc lập đóng gói thành một JAR và cấu hình từ command line. Ta cũng kiểm thử các trường hợp không có provider phù hợp, preference xung đột capability, trùng ID và lỗi cấu hình.

**Phạm vi:** Lựa chọn provider, không phải thay đổi implementation của ServiceLoader. Trong ví dụ, các provider đã được tin cậy và nằm trên classpath. Phần sau giải thích những lưu ý khi chuyển sang JPMS/module path hoặc khi provider đến từ bên ngoài.

## 2. Vì sao không chỉ dùng findFirst()?

Đây là cách thường gặp khi mới học SPI:

~~~java
// Mảnh minh họa: không đủ để chọn theo nhu cầu người dùng.
ReportProvider provider = ServiceLoader.load(ReportProvider.class)
        .findFirst()
        .orElseThrow();
~~~

**findFirst()** chọn provider đầu tiên theo quy tắc phát hiện/cache của ServiceLoader. Thứ tự này không phải chính sách kinh doanh: thứ tự giữa các module không nhất thiết xác định; thứ tự resource trên classpath có thể thay đổi khi đóng gói hoặc thay class loader. Provider đầu tiên cũng chưa chắc hỗ trợ format, locale, dữ liệu hoặc capability mà người dùng yêu cầu.

Thay vào đó, kiến trúc nên là:

~~~text
User config
    |
    v
Chuẩn hóa + kiểm tra cú pháp
    |
    v
ServiceLoader<ReportProvider>
    |
    v
Discovery -> kiểm tra ID -> lấy capability từng provider
    |
    v
Hard filter: định dạng + requiredFeatures
    |
    +-- không provider hợp lệ -> báo lỗi rõ
    |
    v
Ưu tiên preferredId nếu có trong tập hợp hợp lệ
    |
    +-- không hợp lệ và strict=true -> báo lỗi, KHÔNG fallback
    |
    +-- không hợp lệ và strict=false -> fallback có kiểm soát
    |
    v
Sort: priority giảm dần, ID tăng dần
    |
    v
Provider đã chọn -> render
~~~

**Phân biệt hard constraint và soft preference** là nội dung trọng tâm. Format/capability bắt buộc luôn phải được kiểm tra trước. Preferred provider **không được vượt qua** điều kiện hard constraint; nếu có chế độ strict, thiếu preferred là lỗi chứ không phải lý do bỏ qua yêu cầu.

## 3. Thiết kế hợp đồng SPI và cấu hình

Ta xây dựng **ReportProvider** như một service interface. Mỗi implementation khai báo metadata và tạo kết quả:

- **id():** định danh ổn định để người dùng tham chiếu trong cấu hình, ví dụ plain, md, html.
- **formats():** tập định dạng được hỗ trợ: text, markdown hoặc html.
- **features():** capability được công bố, ví dụ unicode, heading, color.
- **priority():** điểm ưu tiên mặc định. Giá trị lớn hơn được chọn trước khi không có preferred hợp lệ.
- **supports(request):** kiểm tra hard constraints; trong bài dùng default implementation từ formats và features.
- **render(input, request):** thực hiện nghiệp vụ khi đã được chọn.

Cấu hình người dùng là một **RenderRequest** bất biến, gồm **format**, **requiredFeatures**, **preferredId** và **strict**.

| Thuộc tính | Ví dụ | Ý nghĩa |
|---|---|---|
| **format** | markdown | Định dạng bắt buộc |
| **requiredFeatures** | unicode,heading | Provider phải có đủ hai capability |
| **preferredId** | plain | Ưu tiên provider có ID plain, nếu hợp lệ |
| **strict** | true hoặc false | Có cho phép fallback khi preferred không hợp lệ? |

**Quy ước quan trọng:** Chỉ **requiredFeatures** là một tập điều kiện bắt buộc. Chúng ta không dùng “số capability nhiều nhất” để tự suy ra provider tốt nhất, vì provider có nhiều tính năng không nhất thiết đáp ứng ưu tiên về độ trễ, chi phí hoặc khả năng giải thích. Chính sách lựa chọn được viết minh bạch bằng preference, priority và tie-breaker.

## 4. Đặc tả hành vi mong muốn

Trong ví dụ có ba provider:

| ID | Formats | Features | Priority |
|---|---|---|---:|
| **plain** | text | unicode | 10 |
| **md** | text, markdown | unicode, heading | 30 |
| **html** | html | unicode, heading, color | 20 |

Từ bảng này suy ra:

- Người dùng yêu cầu **format=text, requires=unicode, prefer=plain, strict=true** → chọn plain, dù md có priority cao hơn.
- Người dùng yêu cầu **format=markdown, requires=heading, prefer=plain, strict=false** → plain không đủ capability, fallback sang md.
- Yêu cầu **format=html, requires=color, prefer=plain, strict=false** → chọn html, vì plain không hỗ trợ html/color.
- Yêu cầu **format=text, requires=unicode**, không có preferred → cả plain và md hợp lệ; md thắng nhờ priority 30.
- Yêu cầu **format=markdown, requires=heading, prefer=plain, strict=true** → báo lỗi, không tự fallback.
- Yêu cầu **format=pdf** → không có provider đủ điều kiện, báo lỗi.

**Lưu ý tính quyết định:** Trong ví dụ, nếu hai provider cùng priority, ta so **id()** theo thứ tự chữ cái để tránh kết quả phụ thuộc thứ tự ServiceLoader trả về. Nếu trùng ID, chương trình **từ chối** thay vì ngẫu nhiên chọn một implementation.

## 5. Cấu trúc dự án thực hành Java 17

Tạo thư mục **provider-selection-lab** với các tệp sau:

~~~text
provider-selection-lab/
├── api/
│   └── src/demo/spi/
│       ├── RenderRequest.java
│       └── ReportProvider.java
├── providers/
│   ├── src/demo/providers/
│   │   ├── PlainProvider.java
│   │   ├── MarkdownProvider.java
│   │   └── HtmlProvider.java
│   └── resources/META-INF/services/
│       └── demo.spi.ReportProvider
├── app/
│   └── src/demo/app/Main.java
└── build/             # được tạo bởi các lệnh biên dịch
~~~

Ở cấu trúc này:

- **api/** công bố service contract và kiểu cấu hình dùng chung.
- **providers/** chứa ba implementation; thông thường chúng được đóng gói JAR riêng.
- **app/** là host chỉ phụ thuộc vào API, không import trực tiếp lớp provider.
- **META-INF/services/demo.spi.ReportProvider** là tệp đăng ký provider trong mô hình classpath.

Tên package và đường dẫn nguồn phải khớp nhau. Tệp service descriptor **không có đuôi .java**, và tên của nó là **fully qualified binary name** của service interface.

## 6. Viết hai tệp API

### 6.1. Cấu hình bất biến RenderRequest

**api/src/demo/spi/RenderRequest.java**

~~~java
package demo.spi;

import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public record RenderRequest(
        String format,
        Set<String> requiredFeatures,
        String preferredId,
        boolean strict) {

    public RenderRequest {
        format = Objects.requireNonNull(format, "format")
                .trim().toLowerCase(Locale.ROOT);

        if (format.isEmpty()) {
            throw new IllegalArgumentException("empty format");
        }

        requiredFeatures = Set.copyOf(
                Objects.requireNonNull(requiredFeatures, "requiredFeatures"));

        preferredId = preferredId == null
                ? ""
                : preferredId.trim().toLowerCase(Locale.ROOT);

        if (strict && preferredId.isEmpty()) {
            throw new IllegalArgumentException(
                    "strict requires --prefer");
        }
    }
}
~~~

**Giải thích:**

1. Java **record** phù hợp với dữ liệu cấu hình bất biến.
2. Format và preferred ID được chuẩn hóa thành lowercase theo **Locale.ROOT**, tránh thay đổi theo locale của máy chạy.
3. **Set.copyOf** chụp một bản tập hợp không thể sửa từ bên ngoài sau khi request được tạo.
4. Nếu strict=true nhưng không có preferred ID, cấu hình không hợp lý, nên báo lỗi ngay.
5. Ví dụ cố ý cho phép một format hay feature mới chưa được provider công bố: kết quả selector sẽ là **no eligible provider**, không âm thầm bỏ điều kiện đó.

Trong hệ thống thực tế, thêm validation cho độ dài, tập ký tự được phép, giá trị null từng phần tử và quota theo nguồn cấu hình. Tên feature phải thống nhất theo quy ước; ví dụ ở đây CLI chuyển feature về lowercase trước khi tạo record.

### 6.2. Hợp đồng ReportProvider

**api/src/demo/spi/ReportProvider.java**

~~~java
package demo.spi;

import java.util.Set;

public interface ReportProvider {

    String id();

    Set<String> formats();

    Set<String> features();

    int priority();

    String render(String input, RenderRequest request);

    default boolean supports(RenderRequest request) {
        return formats().contains(request.format())
                && features().containsAll(request.requiredFeatures());
    }
}
~~~

**Vì sao dùng supports(request)?**

Trong ví dụ đơn giản, format + capability là đủ để quyết định eligibility. Nhưng với provider thực tế, khả năng hỗ trợ có thể phụ thuộc dữ liệu, phiên bản mô hình, giới hạn kích thước, quyền người dùng hoặc loại nội dung. Khi ấy provider có thể override **supports(request)** và giữ contract chọn lựa nhất quán.

**Tuy nhiên:** Một hàm supports được gọi nhiều lần trong quá trình chọn nên lý tưởng là **nhanh, ổn định và không có side effects**. Không nên để supports âm thầm gửi network request tốn phí, thay đổi database hoặc mở tài nguyên không được đóng. Nếu việc kiểm tra capability đắt tiền, cần metadata/health cache có thời hạn và chính sách fallback rõ.

## 7. Viết ba provider

### 7.1. PlainProvider: text đơn giản

**providers/src/demo/providers/PlainProvider.java**

~~~java
package demo.providers;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;
import java.util.Set;

public final class PlainProvider implements ReportProvider {

    public PlainProvider() { }

    @Override
    public String id() {
        return "plain";
    }

    @Override
    public Set<String> formats() {
        return Set.of("text");
    }

    @Override
    public Set<String> features() {
        return Set.of("unicode");
    }

    @Override
    public int priority() {
        return 10;
    }

    @Override
    public String render(String input, RenderRequest request) {
        return "TEXT: " + input;
    }
}
~~~

PlainProvider chỉ cung cấp text và unicode; nó **không** nhận rằng có heading hay color. Đây không phải “provider kém chất lượng” mà là một implementation có phạm vi rõ. Nếu người dùng chọn plain nhưng yêu cầu html, bộ chọn phải từ chối plain.

### 7.2. MarkdownProvider: text hoặc Markdown có heading

**providers/src/demo/providers/MarkdownProvider.java**

~~~java
package demo.providers;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;
import java.util.Set;

public final class MarkdownProvider implements ReportProvider {

    public MarkdownProvider() { }

    @Override
    public String id() {
        return "md";
    }

    @Override
    public Set<String> formats() {
        return Set.of("text", "markdown");
    }

    @Override
    public Set<String> features() {
        return Set.of("unicode", "heading");
    }

    @Override
    public int priority() {
        return 30;
    }

    @Override
    public String render(String input, RenderRequest request) {
        if ("markdown".equals(request.format())) {
            return "# " + input;
        }
        return "MD-TEXT: " + input;
    }
}
~~~

Provider này hỗ trợ **hai format**, nhưng output thay đổi theo cấu hình. Nó có priority lớn hơn plain, nên sẽ được chọn mặc định cho text khi không có preferred ID. Đây là **chính sách do ứng dụng định nghĩa**, không phải thuộc tính cố định của ServiceLoader.

### 7.3. HtmlProvider: HTML có heading và màu sắc

**providers/src/demo/providers/HtmlProvider.java**

~~~java
package demo.providers;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;
import java.util.Set;

public final class HtmlProvider implements ReportProvider {

    public HtmlProvider() { }

    @Override
    public String id() {
        return "html";
    }

    @Override
    public Set<String> formats() {
        return Set.of("html");
    }

    @Override
    public Set<String> features() {
        return Set.of("unicode", "heading", "color");
    }

    @Override
    public int priority() {
        return 20;
    }

    @Override
    public String render(String input, RenderRequest request) {
        String safe = input
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");

        return "<h1 style=\"color:navy\">" + safe + "</h1>";
    }
}
~~~

Bài sử dụng chuỗi đầu vào **Hello <Java>** để thấy HTML output có escaping: dấu **<** và **>** được chuyển thành entities. Escaping giúp minh họa rằng format output phải được triển khai đúng ở từng provider; selector không tự chuyển plain text thành HTML an toàn.

**Giới hạn thực tế:** Hàm escape ở trên đủ cho **nội dung text node** đang được đặt trong h1 ở ví dụ. Nếu chèn dữ liệu vào URL, JavaScript, CSS hoặc HTML attribute theo ngữ cảnh khác, cần encoder phù hợp với **từng ngữ cảnh**, không được dùng lại tùy tiện.

## 8. Đăng ký provider để ServiceLoader tìm thấy

Tạo tệp:

**providers/resources/META-INF/services/demo.spi.ReportProvider**

~~~text
demo.providers.PlainProvider
demo.providers.MarkdownProvider
demo.providers.HtmlProvider
~~~

Mỗi dòng là tên binary đầy đủ của **provider class**. Tệp dùng UTF-8, có thể có dòng trống hoặc comment bắt đầu bằng **#**; ví dụ giữ nguyên ba dòng đơn giản.

**Điều kiện của classpath service provider:**

- Class provider là **public concrete class** và implements **ReportProvider**.
- Có **public constructor không tham số**, được ServiceLoader dùng để tạo instance.
- Class và các dependencies được class loader nhìn thấy.
- Resource phải nằm trong JAR tại **META-INF/services/demo.spi.ReportProvider**; không được bỏ sót khi đóng gói.

Đừng ghi tên class vào tệp **META-INF/services/ReportProvider** thiếu package, và đừng đặt **demo.spi.RenderRequest** ở đó: đó không phải service interface cần tìm. Hai API types cần dùng chung giữa host và provider để tránh lỗi class identity khi dùng nhiều class loaders.

Trong ví dụ, ba provider được đóng vào một JAR để việc dựng project ngắn. Ở ứng dụng thật, mỗi provider có thể ở JAR riêng miễn là cấu hình service discovery phù hợp.

## 9. Host Main: parse config, lọc capability và chọn provider

**app/src/demo/app/Main.java**

~~~java
package demo.app;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {

    private static RenderRequest parse(String[] args) {
        Map<String, String> values = new LinkedHashMap<>();
        Set<String> allowed =
                Set.of("format", "requires", "prefer", "strict");

        for (String arg : args) {
            if (!arg.startsWith("--") || !arg.contains("=")) {
                throw new IllegalArgumentException(
                        "use --key=value");
            }

            String[] pair = arg.substring(2).split("=", 2);
            String key = pair[0];

            if (!allowed.contains(key)) {
                throw new IllegalArgumentException(
                        "unknown option: " + key);
            }

            if (values.putIfAbsent(key, pair[1]) != null) {
                throw new IllegalArgumentException(
                        "duplicate option: " + key);
            }
        }

        Set<String> required = new LinkedHashSet<>();
        String raw = values.getOrDefault("requires", "");

        if (!raw.isBlank()) {
            for (String piece : raw.split(",")) {
                String feature = piece.trim()
                        .toLowerCase(Locale.ROOT);

                if (feature.isEmpty()) {
                    throw new IllegalArgumentException(
                            "empty required feature");
                }
                required.add(feature);
            }
        }

        String strictText =
                values.getOrDefault("strict", "false");

        if (!strictText.equalsIgnoreCase("true")
                && !strictText.equalsIgnoreCase("false")) {
            throw new IllegalArgumentException(
                    "strict must be true or false");
        }

        return new RenderRequest(
                values.getOrDefault("format", "text"),
                required,
                values.getOrDefault("prefer", ""),
                Boolean.parseBoolean(strictText));
    }

    private static ReportProvider select(
            RenderRequest request) {

        ServiceLoader<ReportProvider> loader =
                ServiceLoader.load(ReportProvider.class);

        // get() khởi tạo provider để supports() có thể
        // kiểm tra capability thực tế của instance.
        List<ReportProvider> discovered = loader.stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        Set<String> ids = new HashSet<>();
        for (ReportProvider provider : discovered) {
            if (provider.id() == null
                    || provider.id().isBlank()
                    || !ids.add(provider.id())) {
                throw new IllegalStateException(
                        "duplicate or blank provider id");
            }
        }

        // Hard filter luôn thực hiện TRƯỚC preference.
        List<ReportProvider> eligible = discovered.stream()
                .filter(p -> p.supports(request))
                .sorted(
                    Comparator.comparingInt(
                            ReportProvider::priority)
                        .reversed()
                        .thenComparing(ReportProvider::id))
                .toList();

        if (!request.preferredId().isEmpty()) {
            Optional<ReportProvider> preferred = eligible.stream()
                    .filter(p -> p.id()
                            .equals(request.preferredId()))
                    .findFirst();

            if (preferred.isPresent()) {
                return preferred.get();
            }

            if (request.strict()) {
                throw new NoSuchElementException(
                    "preferred provider not eligible: "
                        + request.preferredId());
            }
        }

        if (eligible.isEmpty()) {
            throw new NoSuchElementException(
                    "no eligible provider");
        }

        return eligible.get(0);
    }

    public static void main(String[] args) {
        try {
            RenderRequest request = parse(args);
            ReportProvider provider = select(request);

            System.out.println(
                    "selected=" + provider.id());
            System.out.println(
                    "rendered=" + provider.render(
                        "Hello <Java>", request));

        } catch (IllegalArgumentException
                | NoSuchElementException e) {
            System.out.println("ERROR=" + e.getMessage());
        }
    }
}
~~~

**Lưu ý về source:** Main có các import **ArrayList** và **HashMap** không dùng đến; Java compiler cho phép unused imports, nhưng có thể bỏ chúng để dự án sạch hơn. Các import còn lại tương ứng cấu trúc code. **Không có class implementation provider nào được Main import trực tiếp**: host chỉ dùng service type, còn provider implementations được phát hiện tại runtime.

### 9.1. Vì sao không chọn ngay từ ServiceLoader.findFirst()?

Host gom các provider được tìm thấy thành danh sách **discovered**, rồi lọc bằng **supports(request)**. Điều này bảo đảm quyết định dựa trên **capability thực tế** và cấu hình.

### 9.2. Vì sao instantiate trước khi kiểm tra supports?

**ServiceLoader.stream()** tạo stream của **ServiceLoader.Provider<ReportProvider>**. **Provider.type()** có thể cho phép kiểm tra metadata về class mà chưa khởi tạo service. Nhưng trong bài, capabilities được công bố bởi **method instance formats()/features()/supports()**, vì vậy phải gọi **Provider.get()** trước khi hỏi khả năng hỗ trợ.

Điều này có giá phải trả: **tất cả provider có thể được tạo** dù cuối cùng chỉ một provider được chọn. Nếu constructor đắt hoặc có side effects, hãy chuyển metadata sớm hơn vào một lightweight **factory-as-service**, annotation phù hợp hoặc manifest/registry đáng tin cậy, rồi chỉ tạo tài nguyên nặng sau khi provider được chọn. Không ép **Provider.type()** luôn là class implementation trong mọi trường hợp: với explicit named JPMS module sử dụng public static provider() factory, **type() là declared return type của provider method**.

### 9.3. Vì sao lọc hard constraints trước?

Ta chỉ cho một provider vào danh sách eligible khi:

~~~java
provider.formats().contains(request.format())
        && provider.features().containsAll(
                request.requiredFeatures())
~~~

Nếu user yêu cầu HTML + color, plain không đủ điều kiện, kể cả khi họ đặt **--prefer=plain**. Đây là nguyên tắc *không được hạ thấp yêu cầu bắt buộc chỉ để đáp ứng preference*.

**Lưu ý:** Trong code ví dụ, supports đã là default method trong interface, nên Main gọi **p.supports(request)** thay vì lặp logic; provider sau này có thể override để kiểm tra thêm điều kiện thực tế.

### 9.4. Vì sao sort sau khi filter?

Nếu không có preferred hợp lệ và strict=false, selector chọn trong tập **đã đủ điều kiện** theo:

1. **priority giảm dần**.
2. Nếu bằng priority, **id tăng dần**.

Nhờ vậy việc thêm JAR hoặc thay đổi thứ tự service file không làm tự động thay đổi provider được chọn **trong trường hợp tập provider/priority/ID thực sự không đổi**. Nếu thêm provider mới có priority cao hơn, chọn lựa có thể thay đổi theo chính sách; cần ghi log để giải thích quyết định này.

### 9.5. Vì sao strict phải thất bại?

Strict thể hiện ý định “**chỉ dùng provider ID này**”. Khi preferred không tồn tại hoặc không đáp ứng format/features, tự chuyển sang provider khác sẽ vi phạm cam kết cấu hình. Code vì vậy ném **NoSuchElementException** với thông điệp có ID bị từ chối; Main biến nó thành một dòng ERROR.

Ở hệ thống production, thường chuyển tình huống này thành một kiểu lỗi domain như **ProviderSelectionException** kèm reason code, thay vì phụ thuộc nội dung text exception.

## 10. Biên dịch và đóng gói trên Java 17

Từ thư mục **provider-selection-lab**, chạy với JDK 17 trở lên.

### 10.1. Linux/macOS (bash)

~~~bash
mkdir -p build/api build/providers build/app
mkdir -p build/providers/META-INF/services

javac --release 17 -encoding UTF-8 -d build/api \
  api/src/demo/spi/RenderRequest.java \
  api/src/demo/spi/ReportProvider.java

javac --release 17 -encoding UTF-8 -cp build/api \
  -d build/providers \
  providers/src/demo/providers/PlainProvider.java \
  providers/src/demo/providers/MarkdownProvider.java \
  providers/src/demo/providers/HtmlProvider.java

cp providers/resources/META-INF/services/demo.spi.ReportProvider \
  build/providers/META-INF/services/

jar --create --file build/providers.jar -C build/providers .

javac --release 17 -encoding UTF-8 -cp build/api \
  -d build/app app/src/demo/app/Main.java
~~~

### 10.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api, build/providers, build/app, build/providers/META-INF/services | Out-Null

javac --release 17 -encoding UTF-8 -d build/api api/src/demo/spi/RenderRequest.java api/src/demo/spi/ReportProvider.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/providers providers/src/demo/providers/PlainProvider.java providers/src/demo/providers/MarkdownProvider.java providers/src/demo/providers/HtmlProvider.java

Copy-Item -Force providers/resources/META-INF/services/demo.spi.ReportProvider build/providers/META-INF/services/

jar --create --file build/providers.jar -C build/providers .

javac --release 17 -encoding UTF-8 -cp build/api -d build/app app/src/demo/app/Main.java
~~~

JAR cần chứa các class provider và resource:

~~~text
META-INF/services/demo.spi.ReportProvider
demo/providers/PlainProvider.class
demo/providers/MarkdownProvider.class
demo/providers/HtmlProvider.class
~~~

Kiểm tra bằng:

~~~bash
jar --list --file build/providers.jar
~~~

Danh sách JAR cũng có thể có **META-INF/MANIFEST.MF** và các entry thư mục; điều quan trọng là service descriptor và ba class phải tồn tại đúng đường dẫn.

**Không đóng gói bản duplicate của API trong providers.jar** khi host đã có API cùng phiên bản. Cả hai phía phải tham chiếu cùng kiểu **demo.spi.ReportProvider** theo class identity; sự trùng binary name ở các class loaders khác nhau không có nghĩa là cùng một Java Class.

## 11. Chạy các cấu hình người dùng và đối chiếu kết quả

Chương trình cho phép các option:

~~~text
--format=text|markdown|html
--requires=unicode,heading,color
--prefer=plain|md|html
--strict=true|false
~~~

**Cú pháp là --key=value**, không có dấu cách giữa key và dấu bằng. Không nhập ký tự **|** vào command thực tế; chúng chỉ biểu thị các lựa chọn trong tài liệu. Có thể bỏ option để nhận giá trị mặc định: format=text, requiredFeatures rỗng, preferredId rỗng, strict=false.

### 11.1. Ưu tiên plain khi nó đáp ứng đủ

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=text --requires=unicode --prefer=plain --strict=true
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=text --requires=unicode --prefer=plain --strict=true
~~~

**Stdout:**

~~~text
selected=plain
rendered=TEXT: Hello <Java>
~~~

Dù md có priority 30, **preferred plain** thắng vì nó đã qua hard filter. Đây là cách ưu tiên người dùng mà không phá điều kiện bắt buộc.

### 11.2. Preferred không hỗ trợ Markdown, strict=false cho phép fallback

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=markdown --requires=heading --prefer=plain
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=markdown --requires=heading --prefer=plain
~~~

**Stdout:**

~~~text
selected=md
rendered=# Hello <Java>
~~~

Plain không có format markdown hoặc feature heading; nó bị loại khỏi danh sách eligible. Vì strict=false theo mặc định, host chọn md là provider hợp lệ.

### 11.3. Yêu cầu HTML có màu sắc

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=html --requires=color --prefer=plain
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=html --requires=color --prefer=plain
~~~

**Stdout:**

~~~text
selected=html
rendered=<h1 style="color:navy">Hello &lt;Java&gt;</h1>
~~~

HtmlProvider là provider duy nhất công bố đủ format html và feature color. Ở đây lựa chọn của người dùng được **thử**, nhưng bị bác vì không đáp ứng hard constraints. HTML provider còn escape đầu vào trước khi tạo HTML output.

### 11.4. Không có preferred: chọn theo priority

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=text --requires=unicode
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=text --requires=unicode
~~~

**Stdout:**

~~~text
selected=md
rendered=MD-TEXT: Hello <Java>
~~~

Plain và md đều hợp lệ, nhưng md có priority 30 so với 10. Nếu muốn plain, người dùng có thể đặt **--prefer=plain**.

### 11.5. Strict preference không hợp lệ phải báo lỗi

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=markdown --requires=heading \
  --prefer=plain --strict=true
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=markdown --requires=heading --prefer=plain --strict=true
~~~

**Stdout:**

~~~text
ERROR=preferred provider not eligible: plain
~~~

Đây là hành vi **đúng** của strict mode: không có dòng selected, không chạy render, không tự dùng md dù md đủ điều kiện.

### 11.6. Không có provider nào đáp ứng định dạng

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=pdf --requires=unicode
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=pdf --requires=unicode
~~~

**Stdout:**

~~~text
ERROR=no eligible provider
~~~

Bộ lọc không tự bỏ qua format=pdf. Nếu yêu cầu bắt buộc không được hỗ trợ, kết quả đúng là “không có provider hợp lệ”.

### 11.7. Strict=true nhưng không chọn preferred

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --strict=true
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --strict=true
~~~

**Stdout:**

~~~text
ERROR=strict requires --prefer
~~~

Đây là lỗi cấu hình được phát hiện **trước service discovery**. Cần phân biệt input sai với lỗi do thiếu provider.

## 12. Chọn provider theo capability: thiết kế điều kiện đúng

### 12.1. Mô hình AND giữa các required features

Code của ReportProvider dùng:

~~~java
// Mảnh minh họa trong ReportProvider.
return formats().contains(request.format())
        && features().containsAll(request.requiredFeatures());
~~~

Điều này nghĩa là yêu cầu **requires=unicode,heading** cần có cả unicode và heading. Không phải “có một trong hai”. Nếu nghiệp vụ cần biểu thức OR, NOT hoặc nhóm yêu cầu phức tạp, hãy mô hình hóa điều kiện rõ hơn thay vì giả định Set.containsAll làm mọi việc.

### 12.2. Phân biệt capability và preference

**Capability** cho biết *provider có thực hiện được yêu cầu không*. **Preference** cho biết *trong các provider phù hợp, người dùng muốn ưu tiên cái nào*. **Priority** là chính sách fallback của host khi không có preferred hợp lệ.

Các khái niệm này không được trộn với nhau. Một provider có priority rất cao vẫn bị loại nếu thiếu **format** hoặc **requiredFeatures**.

### 12.3. Capability động phụ thuộc request

Trong ví dụ, capabilities là các Set cố định. Khi mở rộng thực tế, có thể thêm:

~~~java
// Mảnh minh họa: bổ sung một chính sách trong một provider.
@Override
public boolean supports(RenderRequest request) {
    return ReportProvider.super.supports(request)
            && quotaService.hasCapacity();
}
~~~

**Mảnh trên không chạy độc lập** vì quotaService là dependency của ứng dụng thực. Nó chỉ thể hiện hướng override. Nếu quota thay đổi theo thời gian, kết quả của supports có thể đổi giữa lúc chọn và lúc render; phải có cơ chế reservation/transaction hoặc kiểm tra lại ở bước xử lý. Không nên coi câu trả lời supports là bảo đảm vĩnh viễn nếu có external state.

### 12.4. Cấu hình nên được validate tại ranh giới

Code Main xử lý unknown key, duplicate option, strict không phải true/false, format rỗng và required feature rỗng. Trong ứng dụng thực, có thể thay CLI bằng JSON, YAML, environment variables hoặc UI. Dù lấy nguồn nào, cần chuẩn hóa key/ID, kiểm tra required features và **không silently ignore cấu hình không hiểu**.

Ví dụ: người dùng gõ **--requires=colr** thay vì color. Selector phải trả no eligible provider; không được tự bỏ qua colr để chọn bất kỳ renderer nào.

## 13. Khi nào nên dùng Provider.type() trước Provider.get()?

**ServiceLoader.stream()** trả stream của **ServiceLoader.Provider<S>**, khác với **ServiceLoader.iterator()** vốn cung cấp trực tiếp instance service.

- **Provider.type()** trả một Class mô tả provider type. Ở classpath constructor route, thường là class implementation. Có thể kiểm tra annotation trên type mà chưa instantiate.
- **Provider.get()** tạo/nhận service instance, dùng để gọi methods như supports, id, render. Nó có thể phát sinh lỗi cấu hình hoặc chi phí constructor.
- **ServiceLoader.iterator()** thường instantiate provider khi duyệt, cũng có thể dùng nếu bạn cần metadata instance ngay.

Ví dụ mảnh lọc theo annotation:

~~~java
// Mảnh minh họa, giả sử có annotation @PreferredBackend.
ServiceLoader<ReportProvider> loader =
        ServiceLoader.load(ReportProvider.class);

var candidates = loader.stream()
        .filter(p -> p.type()
                .isAnnotationPresent(PreferredBackend.class))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

**Đây không phải chương trình độc lập**: PreferredBackend phải được định nghĩa. Và có một lưu ý quan trọng của JPMS: Nếu explicit named module dùng **public static provider()** làm provider factory, **Provider.type() trả declared return type của provider method**, không nhất thiết là class provider được viết trong module descriptor. Đừng xây chính sách chọn provider dựa trên assumption type() luôn trỏ đến class implementation vật lý.

Với tính năng **user preference + dynamic capabilities**, chọn **factory service** nhẹ để đọc metadata, rồi mới tạo renderer/resource tốn kém là một hướng thiết kế mạnh hơn. Ví dụ này chủ động instantiate cả ba provider vì constructor rẻ, nhằm tập trung vào logic lựa chọn.

## 14. Xử lý ServiceConfigurationError đúng cách

Trong demo, lỗi selection thường là **IllegalArgumentException** hoặc **NoSuchElementException**. Nhưng **ServiceLoader** có thể ném **ServiceConfigurationError** khi:

- Resource **META-INF/services** sai format hoặc chỉ đến class không tồn tại.
- Provider không implements đúng service hoặc thiếu public no-arg constructor ở classpath.
- Constructor hoặc provider factory ném lỗi.
- Lỗi I/O hoặc class loading khi ServiceLoader phát hiện provider.

**ServiceConfigurationError là Error**, không nằm trong catch IllegalArgumentException | NoSuchElementException của ví dụ. Điều này **có chủ đích**: cấu hình deployment hỏng không bị biến thành lỗi người dùng “no eligible provider”.

Trong hệ thống production có biên giới quản lý plugin, có thể bắt lỗi ở tầng bootstrap/plugin manager để log đầy đủ và cách ly plugin bị lỗi, nhưng không nên âm thầm bỏ qua nó rồi chọn provider khác mà không có chính sách rõ. Nếu provider được cài bởi bên thứ ba, cần quyết định fail-fast hay isolate-one-provider và có thông tin audit.

**Tránh xử lý kiểu này:**

~~~java
// Anti-pattern minh họa, không phải code độc lập.
try {
    return ServiceLoader.load(ReportProvider.class)
            .findFirst().orElse(null);
} catch (Throwable ignore) {
    return null;
}
~~~

Đoạn trên nuốt cả lỗi lập trình/deployment và khiến việc debug cực kỳ khó. Phân biệt:

- Không có provider được tìm thấy: danh sách discovered rỗng.
- Có provider nhưng không đáp ứng yêu cầu: eligible rỗng.
- Người dùng chọn provider cụ thể nhưng strict thất bại: preferred không eligible.
- Cấu hình SPI bị hỏng: ServiceConfigurationError.
- Provider được chọn gặp lỗi render: lỗi thực thi nghiệp vụ hoặc deployment của provider, cần xử lý riêng.

## 15. Đưa thiết kế sang JPMS hoặc module path

Ví dụ chính dùng classpath và **META-INF/services**. Khi chuyển sang explicit named modules, service mechanism vẫn là ServiceLoader nhưng cách khai báo provider thay đổi.

**Module API** (mảnh minh họa):

~~~java
module report.api {
    exports demo.spi;
}
~~~

**Module provider** (mảnh minh họa):

~~~java
module report.plugins {
    requires report.api;
    provides demo.spi.ReportProvider
        with demo.providers.PlainProvider,
             demo.providers.MarkdownProvider,
             demo.providers.HtmlProvider;
}
~~~

**Module host** (mảnh minh họa):

~~~java
module report.host {
    requires report.api;
    uses demo.spi.ReportProvider;
}
~~~

Đây là các **module-info.java minh họa**, không phải yêu cầu chỉnh ví dụ classpath thành module tự động. Khi triển khai JPMS thật, phải compile đúng module layout, resolve provider module và đảm bảo tất cả modules có thể đọc API contract.

Với **automatic module** (JAR legacy không có module-info.class trên module path), ServiceLoader có thể sử dụng service metadata suy ra từ META-INF/services, nhưng automatic-module provider phải có **public no-arg constructor**. Không có hỗ trợ cho static provider factory method ở automatic module.

Với explicit named module, có thể dùng **provides ... with ...** và, nếu khai báo đúng, một **public static provider()** không tham số được ServiceLoader gọi; khi đó **Provider.type()** có thể là return type của method ấy. Đây là lý do phải thiết kế logic chọn capability dựa trên hợp đồng service ổn định, không dựa vào tên implementation class nếu không cần.

**Không dùng ServiceLoader.findFirst() để tự quyết thứ tự ưu tiên giữa các module**, vì thứ tự providers thuộc các module trong cùng layer không được đảm bảo tổng quát. Giữ thuật toán sort theo priority + ID như trong bài.

## 16. Cân nhắc cấu hình, bảo mật và vòng đời provider

### 16.1. Nguồn cấu hình phải rõ ràng

Cấu hình có thể đến từ CLI, properties file, environment variables hoặc giao diện. Xác định độ ưu tiên giữa chúng (ví dụ CLI ghi đè file), validate từng nguồn và ghi log lựa chọn cuối cùng. Không tự suy đoán preferred provider từ thứ tự file trong JAR.

### 16.2. ID là hợp đồng người dùng

Khi user lưu **--prefer=md**, **id()** trở thành public configuration contract. Đừng đổi ID tùy tiện khi rename class. Nếu đổi, cần alias/migration. Nếu hai JAR công bố cùng ID, selector phải từ chối hoặc có chính sách namespace rõ.

### 16.3. Provider metadata không phải bảo mật

**features()** và **supports()** chỉ là lời khai khả năng của provider. Một provider không tin cậy có thể nói sai, và constructor/renderer có thể chạy code tùy ý trong JVM. Không sử dụng capability filter để coi provider là sandbox. Khi thực thi plugin không tin cậy, cần cách ly process/container hoặc cơ chế bảo mật phù hợp và xác minh supply chain.

### 16.4. Lựa chọn không đồng nghĩa đăng ký trọn vòng đời

Demo tạo mọi provider một lần để kiểm tra metadata. Trong hệ thống thực tế, provider có thể mở kết nối, thread pool hoặc file handle. Nếu service tạo resource, nên có lifecycle contract rõ ràng (ví dụ Closeable, factory tạo session rồi close), hoặc lazy initialization sau khi chọn. Không để constructor của provider làm tác vụ đắt bất ngờ.

### 16.5. Concurrency và cache

ServiceLoader có cache và **reload()** để phát hiện lại providers, nhưng việc sửa module path/classpath không phải lúc nào cũng làm mọi class loader tự nhận JAR mới. Các cấu hình instance có thể khác giữa request; tránh cache một lựa chọn chỉ theo format nếu còn requiredFeatures, preferred ID hay policy strict khác. Lựa chọn theo external health/quota cũng cần invalidation.

**ServiceLoader không phải cấu trúc dùng chung thread-safe cho mọi thao tác**; cần quản lý việc tìm và dùng providers trong runtime đồng thời theo tài liệu và quy tắc class loader. Tránh gọi **reload()** trong lúc đang duyệt stream/iterator khác của cùng ServiceLoader.

### 16.6. Độ ổn định của chọn lựa

Comparator priority rồi ID giúp ổn định khi tập provider không đổi. Nếu thêm một provider có priority cao, kết quả automatic có thể thay đổi. Ghi lại **providerId**, **format**, **requiredFeatures**, **policy version** và lý do fallback trong log giúp truy vết thay đổi.

## 17. Kiểm thử chọn provider có hệ thống

Nên tách logic chọn khỏi System.out và CLI khi đưa vào production. Viết unit tests cho các tình huống:

| Test | Input | Kỳ vọng |
|---|---|---|
| Preferred phù hợp | text, unicode, plain, strict=true | **plain** |
| Preferred thiếu capability, fallback | markdown, heading, plain, strict=false | **md** |
| Preferred thiếu capability, strict | markdown, heading, plain, strict=true | **lỗi** |
| Không preferred, hai provider eligible | text, unicode | **md** theo priority |
| Chỉ một provider eligible | html, color | **html** |
| Không có provider format | pdf | **no eligible provider** |
| Không có feature | text, ocr | **no eligible provider** |
| Unknown CLI key | --unknown=x | **lỗi cấu hình** |
| Strict thiếu preferred | --strict=true | **lỗi cấu hình** |
| Hai provider cùng priority | hai provider eligible | **ID tăng dần** |
| Hai provider trùng ID | IDs không duy nhất | **fail-fast** |
| Provider class hỏng | service descriptor sai | **ServiceConfigurationError** |

**Kiểm thử provider thực tế** nên gồm cả khả năng hỗ trợ đầu vào đặc biệt: Unicode, HTML metacharacters, dữ liệu rỗng, độ dài tối đa, locale và giới hạn resource. Capability quảng bá phải đi kèm kiểm thử hành vi, không chỉ kiểm tra Set.contains().

### Bài tập 1: thêm CsvProvider

Tạo một class provider mới với ID **csv**, format **csv**, feature **unicode** và priority 15, đăng ký trong META-INF/services rồi chạy **--format=csv**. Kiểm tra provider mới xuất hiện mà không cần thay đổi import hoặc switch-case trong host.

Gợi ý nghiệp vụ: cần escape các ô CSV đúng quy tắc quote khi chứa comma, quote hoặc newline; đừng coi ghép chuỗi bằng dấu phẩy là CSV parser/serializer hoàn chỉnh.

### Bài tập 2: thêm capability max-size

Mở rộng RenderRequest với kích thước input dự kiến; provider override supports để từ chối request vượt giới hạn. Kiểm thử rằng preferred provider **không** vượt qua hard limit và strict=true trả lỗi.

### Bài tập 3: đổi chính sách fallback

Cho phép người dùng chọn một danh sách ID ưu tiên, ví dụ md rồi html rồi plain. Chỉ chọn từ tập eligible theo thứ tự ưu tiên; nếu không có preferred hợp lệ, dùng priority + ID. Ghi rõ “strict” áp dụng cho **toàn bộ preferred list** hay chỉ phần tử đầu tiên trước khi lập trình.

### Bài tập 4: tách factory khỏi renderer nặng

Thay ReportProvider instance service bằng **ReportProviderFactory** có metadata nhẹ và **create(request)**. ServiceLoader chọn factory hợp lệ trước, rồi mới khởi tạo resource renderer. Kiểm tra constructor của renderer không chạy đối với provider không được chọn.

## 18. Lỗi thường gặp và cách sửa

**Lỗi 1: chọn provider đầu tiên.** Sử dụng findFirst() để quyết định logic nghiệp vụ sẽ khiến thứ tự discovery ảnh hưởng kết quả. **Sửa:** hard filter + preferred + priority + tie-breaker.

**Lỗi 2: coi preferred là yêu cầu bắt buộc ngay cả khi strict=false.** Điều này không cho fallback dù user cho phép. **Sửa:** thử preferred trong eligible, nếu không có thì fallback chỉ khi strict=false.

**Lỗi 3: cho preferred vượt qua capability filter.** Người dùng ưu tiên plain nhưng yêu cầu html; nếu host vẫn chọn plain thì vi phạm yêu cầu. **Sửa:** lọc format/features trước.

**Lỗi 4: quên copy META-INF/services vào JAR.** ServiceLoader có thể trả danh sách rỗng dù class đã compile. **Sửa:** kiểm tra **jar --list** và đúng tên service file.

**Lỗi 5: thiếu public no-arg constructor.** Classpath provider không thể được ServiceLoader tạo. **Sửa:** triển khai public no-arg constructor và contract đúng, hoặc chuyển sang explicit JPMS provider method khi phù hợp.

**Lỗi 6: ưu tiên theo thứ tự JAR.** Classpath/module resolution có thể thay đổi, không phải policy ổn định. **Sửa:** comparator tường minh.

**Lỗi 7: gọi get() quá sớm trong hệ thống đắt đỏ.** Khởi tạo mọi backend chỉ để xem capability gây chậm/side effects. **Sửa:** factory nhẹ hoặc metadata prefilter, sau đó lazy-create resource thực.

**Lỗi 8: nuốt ServiceConfigurationError.** Cấu hình JAR sai bị báo như “không có provider phù hợp”. **Sửa:** phân biệt broken deployment với unsupported request và log đủ cause.

**Lỗi 9: cache kết quả mà bỏ quên preference.** Một lựa chọn cho user A bị dùng cho user B dù họ có cấu hình khác. **Sửa:** cache key đủ format/features/preferred/strict/policy, quản lý stale cache.

**Lỗi 10: dùng capability như quyền truy cập.** Plugin có features() khai báo "secure" không có nghĩa được tin cậy. **Sửa:** phân quyền và cách ly là tầng khác.

## 19. Câu hỏi tự đánh giá

**Câu 1.** Tại sao không nên chọn ServiceLoader.findFirst() khi người dùng có cấu hình?

**Đáp án:** Thứ tự discovery không phải chính sách lựa chọn. Provider đầu tiên có thể không đáp ứng format, requiredFeatures hoặc preference; trong các module thứ tự cũng không được bảo đảm tổng quát.

**Câu 2.** Người dùng chọn **prefer=plain**, **format=markdown**, **strict=false**. Chọn gì?

**Đáp án:** Plain không đủ hard constraints. Fallback chọn md vì nó hỗ trợ markdown. Không báo lỗi nếu có provider hợp lệ khác.

**Câu 3.** Cùng cấu hình trên nhưng strict=true?

**Đáp án:** Báo lỗi preferred provider not eligible, không tự dùng md.

**Câu 4.** Hai provider đều hỗ trợ text/unicode; chọn theo quy tắc gì khi không có preferred?

**Đáp án:** Sort priority giảm dần, rồi ID tăng dần. Với bảng bài thực hành, md có priority 30 nên thắng plain 10.

**Câu 5.** Nếu có provider với priority=100 nhưng thiếu color, nó có được chọn cho requires=color không?

**Đáp án:** Không. Priority chỉ áp dụng sau khi provider thỏa mãn mọi hard constraints.

**Câu 6.** Vì sao ServiceLoader.Provider.type() không phải lúc nào cũng là class triển khai vật lý?

**Đáp án:** Với explicit named module dùng static provider() factory, type() có thể trả declared return type của provider method thay vì factory class.

**Câu 7.** Tại sao cần phát hiện duplicate provider ID?

**Đáp án:** PreferredId là một định danh cấu hình công khai. Nếu hai implementation có cùng ID mà host chọn tùy ý, kết quả khó dự đoán và khó audit.

**Câu 8.** Không có provider đủ format khác với META-INF/services bị hỏng như thế nào?

**Đáp án:** Không có candidate hợp lệ là kết quả bình thường của lọc capability; descriptor/provider hỏng có thể ném ServiceConfigurationError, báo sự cố deployment cần xử lý riêng.

## 20. Checklist hoàn thành bài thực hành

1. API định nghĩa được **ReportProvider**, **RenderRequest**, các capability và lựa chọn ưu tiên.
2. Có ít nhất hai provider độc lập với format/features khác nhau; ví dụ này có ba.
3. **ServiceLoader** tìm thấy provider từ đúng **META-INF/services** trên classpath.
4. Host **không import implementation class** và không dùng if/else theo class name.
5. Cấu hình người dùng được parse/normalize/validate rõ ràng.
6. Selector chỉ chọn trong **eligible providers** thỏa mãn mọi hard constraints.
7. **Preferred** có quyền ưu tiên trong eligible, không có quyền vượt qua hard constraints.
8. **Strict=true** trả lỗi khi preferred không đủ điều kiện; strict=false được fallback.
9. Fallback chọn theo priority giảm dần, ID tăng dần; ID trùng được chặn.
10. Có test cho format không tồn tại, feature không hỗ trợ, CLI sai và SPI descriptor lỗi.
11. Không nuốt lỗi discovery như ServiceConfigurationError; không xem metadata là sandbox.
12. Ghi log lựa chọn cuối cùng và có vòng đời hợp lý cho provider/resource.

**Kết luận:** ServiceLoader cung cấp **discovery và instantiation**, còn ứng dụng phải tự định nghĩa **chính sách selection**. Chính sách an toàn và dễ kiểm thử là **lọc theo khả năng hỗ trợ bắt buộc → xét lựa chọn ưu tiên của người dùng → strict hoặc fallback → tie-break deterministic**. Nhờ vậy hệ thống dễ thêm plugin mà không làm mất kiểm soát kết quả cho từng yêu cầu.

### Tài liệu Java SE 17

- ServiceLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- ServiceLoader.Provider: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java Service Provider framework, ServiceLoader configuration files và JPMS providers: xem mục Developing/Deploying service providers trong trang ServiceLoader ở trên.
- Set.copyOf và collection bất biến: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)
- Java record classes, Java Language Specification §8.10: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10
