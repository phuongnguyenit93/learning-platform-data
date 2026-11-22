# ServiceLoader: nhiều provider và chính sách lựa chọn của ứng dụng

## 1. Bài toán: tìm được nhiều provider chưa có nghĩa là biết chọn provider nào

Trong kiến trúc Java SPI (Service Provider Interface), **service** là hợp đồng chung (thường là `interface` hoặc lớp trừu tượng), **provider** là một triển khai của hợp đồng ấy, còn **ứng dụng** là bên sử dụng dịch vụ. `java.util.ServiceLoader<S>` giúp ứng dụng **khám phá và nạp các provider hiện diện trong môi trường chạy** mà không phải viết cứng danh sách lớp triển khai.

Ví dụ: ứng dụng xuất báo cáo có các triển khai `TextFormatter` cho văn bản thường, chữ in hoa và văn bản có dấu ngoặc. Cả ba đều có thể cùng xuất hiện trên classpath hoặc module path. Khi đó:

- `ServiceLoader.load(TextFormatter.class)` tạo bộ nạp cho **một service type**, có thể tìm **0, 1 hoặc nhiều provider**.
- Thao tác duyệt `for (TextFormatter p : loader)` cung cấp lần lượt các đối tượng provider khi cần; `loader.stream()` cung cấp `ServiceLoader.Provider<TextFormatter>` để kiểm tra thông tin provider và gọi `get()` khi muốn lấy đối tượng.
- **ServiceLoader quyết định cơ chế khám phá, không quyết định chính sách nghiệp vụ**: ứng dụng phải xác định provider phù hợp với cấu hình, khả năng xử lý, tính năng, độ ưu tiên và quy tắc khi không tìm được kết quả duy nhất.

Tách hai trách nhiệm:

~~~text
Classpath / Module path
       ↓
ServiceLoader khám phá các provider đang có
       ↓
Ứng dụng kiểm tra danh tính, năng lực, điều kiện sử dụng
       ↓
Ứng dụng áp dụng chính sách lựa chọn rõ ràng
       ↓
Một provider được chọn, hoặc nhiều provider được phối hợp,
hoặc lỗi được báo minh bạch
~~~

Không nên suy luận rằng “provider nào xuất hiện đầu tiên là tốt nhất” hoặc “ServiceLoader tự chọn triển khai mặc định”.

## 2. Khi nhiều provider cùng tồn tại: điều gì được bảo đảm?

### 2.1. Có thể cùng cung cấp một interface

Các provider độc lập có thể triển khai cùng một service. Ở **classpath**, các tệp tài nguyên `META-INF/services/<tên-đầy-đủ-của-service>` khai báo tên lớp provider. Ở **named module**, mỗi module provider khai báo `provides ... with ...` trong `module-info.java`; module sử dụng dịch vụ khai báo `uses ...`. Đây đều là cơ chế hiện hành của Java.

Các nhà cung cấp có thể nằm ở các JAR hoặc module khác nhau, miễn được môi trường nạp tương ứng nhìn thấy. Một provider cùng lớp xuất hiện lặp trong khai báo cấu hình classpath có thể được ServiceLoader bỏ qua; điều đó **không giải quyết xung đột hai provider khác lớp nhưng cùng định danh nghiệp vụ**.

### 2.2. Thứ tự khám phá không phải chính sách ưu tiên

ServiceLoader có quy tắc thứ tự theo nguồn tìm kiếm (module/class loader/configuration file), nhưng **không có thứ tự ưu tiên nghiệp vụ tổng quát**. Đặc biệt, thứ tự các module cùng layer không được định nghĩa; trên classpath, thứ tự tìm thấy các file cấu hình phụ thuộc `ClassLoader.getResources()`, môi trường và cách đóng gói.

Vì vậy:

- `loader.findFirst()` chỉ lấy **provider đầu tiên theo thứ tự khám phá hiện tại**. Dùng khi “bất kỳ triển khai hợp lệ nào cũng được” hoặc hợp đồng đã quy định rõ tính bất biến của thứ tự; **không dùng để chọn backend ưu tiên theo nghiệp vụ**.
- Thứ tự các dòng trong một tệp `META-INF/services` có thể tham gia vào thứ tự khám phá từ tệp đó, **nhưng không tạo được cam kết thứ tự toàn hệ thống** khi ứng dụng có nhiều JAR/module.
- `stream().findFirst()` cũng không tạo chính sách lựa chọn; việc thay đổi bộ dependency hoặc module layer có thể làm thay đổi provider được gặp trước.
- Muốn kết quả ổn định, hãy **lọc và chọn bằng khóa/tiêu chí tường minh**; nếu cần sắp xếp, dùng quy tắc xếp hạng có điểm hòa (tie-break) hoặc lỗi hòa được định nghĩa trước.

## 3. Các chính sách lựa chọn thực tế

| Chính sách | Cách quyết định | Phù hợp khi | Điều phải quy định |
| --- | --- | --- | --- |
| **Theo ID trong cấu hình** | Đọc `provider.id` từ config; lấy đúng provider có `id()` trùng | Backend, formatter, payment adapter được chọn rõ ràng | ID duy nhất, không có ID, ID sai |
| **Theo năng lực** | Chọn provider hỗ trợ loại đầu vào/yêu cầu (`supports(...)`) | Codec, parser, driver có phạm vi hỗ trợ khác nhau | Không có provider phù hợp, nhiều provider cùng phù hợp |
| **Theo độ ưu tiên** | Lọc các provider phù hợp, lấy điểm `priority` cao nhất/thấp nhất theo hợp đồng | Chọn implementation tối ưu theo chính sách cố định | Chiều ưu tiên và xử lý hòa điểm |
| **Theo cấu hình + fallback** | Thử provider được chỉ định; chỉ chuyển dự phòng nếu chính sách cho phép | Ứng dụng cần khả năng dự phòng kiểm soát được | Điều kiện được fallback, logging, tránh lỗi bị che giấu |
| **Dùng tất cả provider** | Duyệt tất cả để đăng ký, gửi sự kiện, hoặc xử lý theo chuỗi | Bộ plugin độc lập cần cùng tham gia | Thứ tự, lỗi từng plugin, trùng tác động, tính idempotent |

Một chính sách điển hình nên được viết thành hợp đồng dễ kiểm thử:

1. Tìm các provider mà ứng dụng thực sự có quyền sử dụng và hỗ trợ yêu cầu hiện tại.
2. Ưu tiên **ID đã được cấu hình tường minh** nếu có; nếu ID không tồn tại thì báo lỗi hoặc fallback theo quy định, không tự lấy provider ngẫu nhiên.
3. Nếu dùng chấm điểm, đánh giá trên **cùng một bộ ứng viên hợp lệ**. Chỉ lựa chọn tự động khi có kết quả duy nhất; nếu hai provider cùng điểm cao nhất, áp dụng tie-break rõ ràng (ví dụ ID tăng dần) **hoặc** báo cấu hình mơ hồ.
4. Nếu không có provider, chọn default do ứng dụng **chủ động cung cấp** hoặc dừng với lỗi có thông tin rõ ràng.
5. Ghi nhận provider đã chọn (ID, phiên bản, môi trường) để hỗ trợ kiểm tra sự cố; không cần tiết lộ dữ liệu nhạy cảm trong log.

**Phân biệt lỗi khám phá và lỗi lựa chọn:** `ServiceConfigurationError` có thể phát sinh do khai báo provider hỏng, lớp không nạp được hoặc khởi tạo thất bại. “Không có provider thỏa chính sách” là lỗi nghiệp vụ ứng dụng tự định nghĩa. Hai lỗi này nên được xử lý khác nhau.

## 4. Ví dụ Java 17+: ba provider, chọn duy nhất bằng ID

Ví dụ hoàn chỉnh sau minh họa **một ứng dụng có nhiều provider** và chính sách “chọn theo ID người dùng cung cấp, từ chối ID trùng và ID không tồn tại”. Mọi lớp đều nằm trong package `demo`. Tệp cấu hình provider phải được đặt đúng đường dẫn resource khi chạy bằng classpath.

Cấu trúc dự án:

~~~text
service-loader-demo/
├── src/
│   └── demo/
│       ├── TextFormatter.java
│       ├── PlainFormatter.java
│       ├── UpperFormatter.java
│       ├── BracketFormatter.java
│       └── App.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.TextFormatter
~~~

### 4.1. Định nghĩa hợp đồng dịch vụ

`src/demo/TextFormatter.java`:

~~~java
package demo;

public interface TextFormatter {
    String id();                 // ID ổn định, duy nhất trong ứng dụng
    String format(String input);
}
~~~

ID thuộc hợp đồng ứng dụng, không phải trường bắt buộc của `ServiceLoader`. Việc đặt ID trong SPI giúp chính sách chọn provider **không phụ thuộc tên lớp hay thứ tự JAR**.

### 4.2. Ba provider độc lập

`src/demo/PlainFormatter.java`:

~~~java
package demo;

public final class PlainFormatter implements TextFormatter {
    public String id() { return "plain"; }
    public String format(String input) { return input; }
}
~~~

`src/demo/UpperFormatter.java`:

~~~java
package demo;

import java.util.Locale;

public final class UpperFormatter implements TextFormatter {
    public String id() { return "upper"; }
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

`src/demo/BracketFormatter.java`:

~~~java
package demo;

public final class BracketFormatter implements TextFormatter {
    public String id() { return "bracket"; }
    public String format(String input) {
        return "[" + input + "]";
    }
}
~~~

Các provider là lớp `public` với constructor không tham số công khai do Java tự sinh. Đó là yêu cầu thích hợp cho cách đăng ký provider **trên classpath** ở ví dụ này.

### 4.3. Đăng ký các provider trên classpath

Tạo tệp UTF-8 đúng tên `resources/META-INF/services/demo.TextFormatter` với toàn bộ nội dung:

~~~text
demo.PlainFormatter
demo.UpperFormatter
demo.BracketFormatter
~~~

Tên tệp là tên nhị phân đầy đủ của **service**, còn mỗi dòng là tên nhị phân đầy đủ của **lớp provider**. Tệp phải xuất hiện dưới `META-INF/services` trong root của classpath (hoặc bên trong JAR) khi chạy. Chỉ biên dịch `.java` mà không đóng gói tài nguyên này sẽ khiến ứng dụng không phát hiện các provider từ classpath.

### 4.4. Ứng dụng chọn theo ID và kiểm tra xung đột

`src/demo/App.java`:

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class App {
    public static void main(String[] args) {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java -cp out demo.App <provider-id>");
        }

        // TreeMap giúp thứ tự liệt kê ID ổn định,
        // độc lập với thứ tự ServiceLoader phát hiện provider.
        Map<String, TextFormatter> candidates = new TreeMap<>();

        for (TextFormatter provider : ServiceLoader.load(TextFormatter.class)) {
            String id = Objects.requireNonNull(
                    provider.id(), "Provider id must not be null");
            if (id.isBlank()) {
                throw new IllegalStateException("Blank provider id");
            }

            TextFormatter old = candidates.putIfAbsent(id, provider);
            if (old != null) {
                throw new IllegalStateException("Duplicate provider id: " + id);
            }
        }

        if (candidates.isEmpty()) {
            throw new IllegalStateException("No TextFormatter providers");
        }

        TextFormatter selected = candidates.get(args[0]);
        if (selected == null) {
            throw new IllegalArgumentException(
                    "Unknown provider id: " + args[0]
                    + "; available: " + candidates.keySet());
        }

        System.out.println("Available: " + candidates.keySet());
        System.out.println("Selected: " + selected.id());
        System.out.println("Output: " + selected.format("Hello Java"));
    }
}
~~~

**Vì sao phải duyệt hết?** Chính sách cần biết tất cả ứng viên để xác định ID có trùng không; nếu chỉ gọi `findFirst()` sẽ bỏ qua xung đột tiềm ẩn. `TreeMap` sắp xếp **khi liệt kê ID**, không làm thay đổi thứ tự khám phá bên trong ServiceLoader. `putIfAbsent` phát hiện **hai provider khác nhau tự khai báo cùng ID**, đây là kiểm tra riêng của ứng dụng.

**Biên dịch và chạy:** ở thư mục `service-loader-demo`, tạo thư mục `out`, rồi thực thi (mỗi lệnh là một bước):

~~~sh
mkdir out
javac -d out src/demo/TextFormatter.java src/demo/PlainFormatter.java src/demo/UpperFormatter.java src/demo/BracketFormatter.java src/demo/App.java
~~~

Sao chép tài nguyên để đường dẫn `out/META-INF/services/demo.TextFormatter` tồn tại.

Trên Linux/macOS:

~~~sh
cp -R resources/META-INF out/
~~~

Trên Windows PowerShell:

~~~powershell
Copy-Item -Recurse -Path resources/META-INF -Destination out
~~~

Chạy với provider được yêu cầu:

~~~sh
java -cp out demo.App upper
~~~

Kết quả chính xác (đã biên dịch và chạy):

~~~text
Available: [bracket, plain, upper]
Selected: upper
Output: HELLO JAVA
~~~

Nếu đổi thành `java -cp out demo.App bracket`:

~~~text
Available: [bracket, plain, upper]
Selected: bracket
Output: [Hello Java]
~~~

Việc sắp xếp danh sách `Available` do `TreeMap` thực hiện, vì thế kết quả không phụ thuộc provider nào được ServiceLoader tìm thấy đầu tiên.

## 5. Nếu không chỉ chọn bằng ID: chính sách về năng lực và ưu tiên

Trong ứng dụng thực, một service có thể mở rộng hợp đồng thành các phương thức mô tả năng lực, ví dụ `supports(MediaType)`, `priority()`, `version()` hoặc thông tin cấu hình. Đây là **API do ứng dụng tự thiết kế**, không phải các phương thức sẵn có của `ServiceLoader`.

Giả sử có ba provider cùng xử lý định dạng `image/png`:

| ID | Hỗ trợ PNG? | Điểm ưu tiên do ứng dụng quy định |
| --- | --- | ---: |
| `png-fast` | Có | 90 |
| `png-safe` | Có | 80 |
| `jpeg-only` | Không | 100 |

Nếu chính sách là “hỗ trợ PNG rồi lấy điểm cao nhất”, ứng dụng phải **lọc `supports(PNG)` trước**, sau đó mới so điểm. Provider `jpeg-only` không được chọn dù điểm cao hơn; kết quả là `png-fast`. Nếu hai provider tương thích đều có điểm 90, phải có **quy tắc hòa**: ví dụ cho phép chọn ID nhỏ nhất theo thứ tự từ điển **chỉ nếu đây là chính sách đã công bố**, hoặc báo lỗi để người cấu hình xác định rõ provider.

Đối với hệ thống có fallback, cần phân biệt:

- **Không tìm được provider trong cấu hình:** có thể dùng `defaultProviderId` đã định nghĩa rõ nếu nghiệp vụ cho phép.
- **Provider tìm thấy nhưng không hỗ trợ yêu cầu:** có thể thử provider tiếp theo trong danh sách được cấu hình; nên ghi rõ lý do bỏ qua.
- **Provider khởi tạo hoặc chạy bị lỗi:** không tự mặc định nuốt lỗi và chuyển provider khác nếu thao tác có tác dụng phụ (ghi dữ liệu, thanh toán, gửi yêu cầu ngoài hệ thống); việc retry/fallback phải an toàn với nghiệp vụ và idempotency.

Nếu phải xử lý **tất cả** provider (ví dụ nhiều plugin kiểm tra độc lập), đó là chính sách phối hợp, không phải chính sách “chọn duy nhất”. Ứng dụng phải kiểm soát trình tự chạy, độ trễ, cách gom kết quả và hành vi khi một plugin lỗi.

## 6. `iterator()`, `stream()` và thời điểm khởi tạo

Hai cách lấy provider giải quyết các mục tiêu khác nhau:

~~~java
ServiceLoader<TextFormatter> loader =
        ServiceLoader.load(TextFormatter.class);

// Duyệt instance: mỗi provider được lấy/khởi tạo khi duyệt đến.
for (TextFormatter formatter : loader) {
    System.out.println(formatter.id());
}

// Duyệt Provider descriptor: có thể xem type trước khi gọi get().
loader.stream()
        .map(provider -> provider.type().getName())
        .sorted()
        .forEach(System.out::println);
~~~

Đây là **đoạn minh họa đặt trong chương trình có các lớp từ mục 4**, không phải một tệp `.java` độc lập. Với `stream()`, phần tử là `ServiceLoader.Provider<S>`; `provider.type()` cho biết kiểu mà API công bố, còn `provider.get()` lấy/khởi tạo đối tượng. Có thể dùng kiểu hoặc annotation để lọc **trước khi khởi tạo đối tượng nặng**. Lưu ý: khi provider của một named module dùng static `provider()` factory, `type()` biểu diễn kiểu provider *được trả về*, không nhất thiết là lớp nhà máy được liệt kê trong `provides`.

`ServiceLoader` tìm và nạp provider **lười** (lazy) theo quá trình duyệt, đồng thời giữ cache các provider đã nạp theo **từng đối tượng ServiceLoader**. Vì vậy:

- Tạo loader chưa đồng nghĩa mọi provider đã được khởi tạo.
- Duyệt toàn bộ như ví dụ kiểm tra trùng ID sẽ khiến các provider được sử dụng/khởi tạo; tránh constructor tốn tài nguyên, thao tác mạng hoặc side effect không cần thiết.
- `loader.reload()` **xóa cache provider của loader đó** để lần duyệt sau tìm/nạp lại; nó **không tự tải thêm JAR, thay đổi classpath hay tạo ModuleLayer**. Những điều kiện thấy được provider mới phải được hệ thống nạp lớp quản lý riêng.
- Sau `reload()`, hãy bỏ iterator/stream cũ và tạo lượt duyệt mới; không dùng nhiều luồng đồng thời trên cùng một `ServiceLoader` vì đối tượng này **không thread-safe**.

Nếu cần lựa chọn trước khi khởi tạo một provider tốn kém, có thể đưa metadata lựa chọn lên annotation/type hoặc dùng SPI dạng **provider factory** có metadata nhẹ; sau khi chọn mới tạo tài nguyên nặng. Một `id()` trên instance như ví dụ đơn giản sẽ cần instance để đọc ID.

## 7. Classpath và named module: đăng ký khác nhau, chính sách chọn vẫn thuộc ứng dụng

Ví dụ chạy được ở mục 4 dùng **classpath** với tệp `META-INF/services/demo.TextFormatter`. Với ứng dụng JPMS (**named modules**), hãy tổ chức module service, module ứng dụng và các module provider. Minh họa các directive `module-info.java` (không phải bộ tệp độc lập để chạy ngay):

~~~java
// Module công bố interface: com.example.format.api
module com.example.format.api {
    exports com.example.format.spi;
}

// Module ứng dụng: com.example.format.app
module com.example.format.app {
    requires com.example.format.api;
    uses com.example.format.spi.TextFormatter;
}

// Module chứa provider: com.example.format.upper
module com.example.format.upper {
    requires com.example.format.api;
    provides com.example.format.spi.TextFormatter
            with com.example.format.upper.UpperFormatter;
}
~~~

Mỗi khối `module { ... }` ở trên thuộc **một tệp `module-info.java` riêng, trong module tương ứng**. Chúng minh họa module khác với package `demo` trong ví dụ classpath; khi triển khai thật, mã và tên package phải khớp nhau. Module chứa provider có thể không export package implementation. Từ phía ứng dụng, `ServiceLoader.load(TextFormatter.class)` vẫn tìm các provider phù hợp với môi trường nạp; **quy tắc ID/capability/priority vẫn do ứng dụng thực hiện**.

Khi ứng dụng có nhiều class loader (server, hệ plugin), `ServiceLoader.load(ServiceType.class)` dùng **thread context class loader**. Nếu muốn kiểm soát phạm vi khám phá, có thể dùng `load(ServiceType.class, classLoader)`; với module layer riêng, có `load(moduleLayer, ServiceType.class)`. Việc chọn class loader/layer là quyết định kiến trúc; nó không thay thế chính sách lựa chọn giữa các provider trong phạm vi ấy.

## 8. Kiểm tra lỗi, vận hành và an toàn khi có nhiều plugin

**Các tình huống phải kiểm thử:**

1. **Không provider nào được khám phá:** cấu hình sai, resource không được đóng gói, module provider không xuất hiện ở runtime. Ứng dụng nên báo nguyên nhân và danh sách dependency liên quan; chỉ fallback nếu được quy định.
2. **Có nhiều provider với cùng ID nghiệp vụ:** phải báo xung đột rõ ràng, như `Duplicate provider id` trong ví dụ. ServiceLoader không biết hợp đồng duy nhất của `id()`.
3. **ID được yêu cầu không tồn tại:** báo ID sai và các ID hợp lệ, không tự dùng `findFirst()`.
4. **Provider sai định dạng hoặc khởi tạo hỏng:** `ServiceConfigurationError` có thể xuất hiện **khi duyệt** `iterator()/stream()`, không chỉ ở lời gọi `ServiceLoader.load(...)`; log cả nguyên nhân gốc và thông tin triển khai.
5. **Kết quả hòa điểm:** kiểm tra tie-break hoặc lỗi mơ hồ đã công bố; không để thứ tự phụ thuộc JAR/module.
6. **Thêm/xóa provider ở runtime:** đánh giá lại phạm vi class loader/module layer và cache. Không dùng `reload()` như một cơ chế tự động hot-plug hoàn chỉnh.
7. **Hiệu năng và tác dụng phụ:** constructor provider có thể thực thi mã bên thứ ba. Chỉ triển khai plugin từ nguồn tin cậy, giữ hợp đồng khởi tạo đơn giản, và thực thi health check theo ranh giới nghiệp vụ.
8. **Đa luồng:** không chia sẻ một `ServiceLoader` để các luồng cùng duyệt/reload; nếu cần, khám phá và chốt lựa chọn khi khởi động rồi quản lý vòng đời của provider đã chọn. Tính thread-safe của provider phải được đánh giá riêng.

Một kiểm thử hồi quy có ích là **đảo thứ tự khai báo ba provider** trong `META-INF/services/demo.TextFormatter` và chạy lại `demo.App upper`. Kết quả lựa chọn vẫn phải là `upper`; thông tin `Available` vẫn là `[bracket, plain, upper]`. Điều này chứng minh ứng dụng chọn theo hợp đồng ID thay vì tình cờ dựa vào thứ tự cấu hình.

## 9. Câu hỏi tự kiểm tra

**Câu 1:** Hai JAR khai báo hai provider khác nhau, cả hai cùng `id() = "fast"`. Có nên dùng `findFirst()` để “chữa” lỗi?  
**Trả lời:** Không. Ứng dụng phải xử lý ID trùng theo chính sách, chẳng hạn từ chối cấu hình và yêu cầu đặt lại ID/loại bỏ một provider.

**Câu 2:** Một provider có điểm ưu tiên cao nhưng không hỗ trợ định dạng được yêu cầu; provider nào thắng?  
**Trả lời:** Chỉ so điểm trong tập provider đã vượt qua kiểm tra `supports(...)`. Provider không hỗ trợ yêu cầu bị loại dù có điểm cao.

**Câu 3:** `loader.reload()` có tự tải tệp JAR vừa sao chép vào ổ đĩa không?  
**Trả lời:** Không. Nó xóa cache của ServiceLoader; sự hiện diện của class/module mới vẫn phụ thuộc cách class loader hoặc module layer được cấu hình và quản lý.

**Ghi nhớ:** `ServiceLoader` giúp **khám phá và nạp nhiều implementation**, còn ứng dụng phải **thiết kế quy tắc chọn minh bạch, tái lập được**: bộ lọc hợp lệ, tiêu chí ưu tiên, xử lý xung đột, fallback và lỗi. Đừng biến thứ tự khám phá thành thứ tự ưu tiên nghiệp vụ.

### Tài liệu tham khảo

- [Oracle Java SE 26 API — ServiceLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): thiết kế SPI, provider nhiều triển khai, cách đăng ký, thứ tự tìm kiếm, lazy/cache, lỗi và đa luồng.
- [Oracle Java SE 26 API — ServiceLoader.Provider](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()` và `get()`.
