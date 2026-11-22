# API và SPI: ai sử dụng, ai cung cấp dịch vụ?

Trong một hệ thống Java có khả năng mở rộng lúc chạy (runtime extensibility), ứng dụng cần **dùng một chức năng** mà không nhất thiết phải biết **lớp nào cung cấp chức năng đó**. Phân biệt API và SPI giúp xác định đúng hai phía của hợp đồng này: mã sử dụng dịch vụ (consumer) và mã triển khai dịch vụ (provider).

## 1. Hai góc nhìn trên cùng một dịch vụ

**API (Application Programming Interface)** là bề mặt mà bên sử dụng gọi để hoàn thành công việc. API trả lời: “Tôi có thể yêu cầu hệ thống làm gì, truyền gì vào và nhận gì ra?”. Nó có thể gồm interface, class, method, kiểu dữ liệu, ngoại lệ và quy tắc hành vi công khai.

**SPI (Service Provider Interface)** là hợp đồng mà một thư viện hoặc nền tảng công bố để các bên khác **cài đặt và đăng ký phần thực thi**. SPI trả lời: “Muốn cung cấp khả năng này cho hệ thống, tôi phải hiện thực những điểm mở rộng nào?”. Provider là thư viện/lớp cụ thể hiện thực SPI; thành phần điều phối sẽ tìm và gọi provider khi cần.

| Góc nhìn | API — bên sử dụng dịch vụ | SPI — bên cung cấp dịch vụ |
|---|---|---|
| Đối tượng chính | Consumer, ứng dụng nghiệp vụ, mã gọi thư viện | Tác giả provider/driver/plugin/adapter |
| Câu hỏi | “Gọi chức năng nào?” | “Cài đặt chức năng theo hợp đồng nào?” |
| Hướng phụ thuộc | Consumer phụ thuộc vào hợp đồng API | Provider phụ thuộc vào hợp đồng SPI, thường cả các kiểu API liên quan |
| Ai quyết định cách thực thi? | Thường không cần biết chi tiết | Provider triển khai logic thực tế |
| Ai gọi ai lúc chạy? | Consumer gọi API | Framework/nền tảng gọi SPI hoặc đối tượng do SPI tạo ra |
| Điều cần ổn định | Chữ ký, dữ liệu đầu vào/đầu ra, ngoại lệ, ngữ nghĩa cho consumer | Điểm mở rộng, vòng đời, yêu cầu đăng ký, tương thích cho provider |

**API và SPI là hai *vai trò*, không nhất thiết là hai interface khác nhau.** Một interface có thể vừa là API mà ứng dụng gọi, vừa là SPI mà provider hiện thực. Ở hệ thống lớn, người ta thường tách API facade khỏi SPI để consumer không phải biết cơ chế nạp plugin.

## 2. Vì sao tách hai phía?

Giả sử ứng dụng xuất báo cáo và cần hỗ trợ nhiều định dạng. Nếu mã nghiệp vụ trực tiếp viết `new PdfFormatter()` hay `new HtmlFormatter()`, mỗi định dạng mới có thể buộc ứng dụng chỉnh mã, biên dịch và phát hành lại. Thiết kế có API/SPI tạo ranh giới:

```text
Ứng dụng (consumer)
    |
    | dùng API: Formatters.get("upper").format(text)
    v
Thư viện điều phối / API facade
    |
    | khám phá provider và gọi hợp đồng SPI
    v
FormatterProvider (SPI)
    |
    +--> UppercaseProvider (provider A)
    +--> ...               (provider B có thể bổ sung sau)
```

Đổi hoặc thêm provider không buộc consumer biết tên lớp triển khai. Tuy nhiên, “nạp lúc chạy” **không đồng nghĩa tự động cài đặt nóng**: cơ chế nạp lớp, classpath/module path và vòng đời class loader vẫn quyết định lúc nào provider mới được nhìn thấy.

## 3. Ví dụ Java 17+: consumer chỉ gọi API, provider hiện thực SPI

Ta tạo một dịch vụ định dạng chữ đơn giản. Ví dụ đặt mọi lớp trong cùng thư mục biên dịch cho dễ chạy; trong dự án thật, API/SPI và từng provider nên nằm ở các JAR/module riêng.

Cấu trúc tệp:

```text
src/
├── demo/
│   ├── Main.java
│   ├── api/
│   │   ├── TextFormatter.java
│   │   └── Formatters.java
│   ├── spi/
│   │   └── FormatterProvider.java
│   └── provider/
│       └── UppercaseProvider.java
└── META-INF/
    └── services/
        └── demo.spi.FormatterProvider
```

### 3.1. API công khai cho consumer

Tệp `src/demo/api/TextFormatter.java`:

```java
package demo.api;

@FunctionalInterface
public interface TextFormatter {
    String format(String input);
}
```

Tệp `src/demo/api/Formatters.java`:

```java
package demo.api;

import demo.spi.FormatterProvider;
import java.util.ServiceLoader;

public final class Formatters {
    private Formatters() {}

    public static TextFormatter get(String id) {
        for (FormatterProvider provider : ServiceLoader.load(FormatterProvider.class)) {
            if (provider.id().equals(id)) {
                return provider.create();
            }
        }
        throw new IllegalArgumentException("Unknown format: " + id);
    }
}
```

Consumer thấy `TextFormatter` và phương thức `Formatters.get(...)`; nó không phải tạo hay import lớp provider. `Formatters` là lớp điều phối: bên trong nó dùng SPI để chọn thực thi. Trong ứng dụng thật, cần quy định cách xử lý `id` trùng nhau, ưu tiên, cấu hình và trường hợp không tìm thấy dịch vụ.

### 3.2. SPI cho người viết provider

Tệp `src/demo/spi/FormatterProvider.java`:

```java
package demo.spi;

import demo.api.TextFormatter;

public interface FormatterProvider {
    String id();
    TextFormatter create();
}
```

Đây là hợp đồng mở rộng: provider phải công bố mã nhận diện và tạo bộ định dạng theo API. Thư viện điều phối quyết định *khi nào* gọi `id()` và `create()`; provider quyết định *cách* tạo đối tượng xử lý.

Tệp `src/demo/provider/UppercaseProvider.java`:

```java
package demo.provider;

import demo.api.TextFormatter;
import demo.spi.FormatterProvider;
import java.util.Locale;

public final class UppercaseProvider implements FormatterProvider {
    @Override
    public String id() {
        return "upper";
    }

    @Override
    public TextFormatter create() {
        return input -> input.toUpperCase(Locale.ROOT);
    }
}
```

`UppercaseProvider` **hiện thực SPI** nhưng trả về một đối tượng tuân thủ **API**. Nó sử dụng `Locale.ROOT` để ví dụ cho kết quả chuyển chữ hoa không phụ thuộc locale mặc định của máy.

### 3.3. Đăng ký provider cho `ServiceLoader`

Nội dung tệp **không có phần mở rộng** `src/META-INF/services/demo.spi.FormatterProvider`:

```text
demo.provider.UppercaseProvider
```

Tên tệp phải trùng **tên đầy đủ của kiểu dịch vụ SPI**; mỗi dòng nội dung là tên đầy đủ của một lớp provider. Trên classpath, `ServiceLoader` tra cứu các tài nguyên `META-INF/services/<tên-đầy-đủ-của-SPI>`. Lớp provider trong ví dụ là `public`, có constructor không tham số công khai mặc định, và hiện thực SPI.

### 3.4. Consumer và chạy thử

Tệp `src/demo/Main.java`:

```java
package demo;

import demo.api.Formatters;
import demo.api.TextFormatter;

public class Main {
    public static void main(String[] args) {
        TextFormatter formatter = Formatters.get("upper");
        System.out.println(formatter.format("Xin chào Java"));
    }
}
```

Trong **PowerShell trên Windows**, đứng tại thư mục chứa `src` và chạy:

```powershell
javac -encoding UTF-8 -d out src/demo/api/TextFormatter.java src/demo/api/Formatters.java src/demo/spi/FormatterProvider.java src/demo/provider/UppercaseProvider.java src/demo/Main.java
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
Copy-Item src/META-INF/services/demo.spi.FormatterProvider out/META-INF/services/demo.spi.FormatterProvider
java -cp out demo.Main
```

Trên **Linux/macOS**, thay hai lệnh tạo/copy thư mục tài nguyên bằng `mkdir -p out/META-INF/services` và `cp src/META-INF/services/demo.spi.FormatterProvider out/META-INF/services/`; lệnh `javac` và `java` giữ nguyên.

Đầu ra:

```text
XIN CHÀO JAVA
```

Nếu bỏ tệp đăng ký `out/META-INF/services/demo.spi.FormatterProvider` rồi chạy lại, `ServiceLoader` không tìm thấy provider qua cấu hình classpath trong ví dụ; `Formatters.get("upper")` ném `IllegalArgumentException` với thông báo `Unknown format: upper`. Điều đó minh họa rằng **có lớp provider trên classpath chưa đủ; phải có đăng ký đúng**.

Ví dụ này cố ý đơn giản: mọi tệp biên dịch chung để tái hiện dễ dàng. Khi đóng JAR, hãy đặt `META-INF/services/...` **vào bên trong JAR của provider**; consumer phụ thuộc vào API, còn provider JAR được đưa vào môi trường chạy. Nếu dùng nhiều provider, nên kiểm tra mã `id` trùng thay vì âm thầm lấy provider đầu tiên.

## 4. `ServiceLoader` làm gì và không làm gì?

`java.util.ServiceLoader<S>` là tiện ích chuẩn để khám phá các implementation/provider của kiểu dịch vụ `S`. Trong ví dụ, các bước là:

1. Thư viện gọi `ServiceLoader.load(FormatterProvider.class)`.
2. Cơ chế nạp tìm các khai báo provider khả dụng qua class loader/module tương ứng.
3. Khi duyệt, provider được nạp và tạo theo quy tắc của `ServiceLoader`.
4. Thư viện dùng hợp đồng SPI để chọn provider và cung cấp đối tượng API cho consumer.

Các đặc tính cần hiểu rõ:

- **Khám phá và tạo thường diễn ra lười (lazy).** Việc gọi `load(...)` không có nghĩa mọi provider đã được khởi tạo ngay. Đừng đặt tác dụng phụ quan trọng vào giả định “tất cả provider đã chạy”.
- **Có bộ nhớ đệm provider đã tìm được/tạo ra.** `reload()` xóa bộ nhớ đệm của *đối tượng `ServiceLoader` đó* để thực hiện khám phá lại. Nó không tự tải JAR mới vào classpath, tạo class loader mới hay thay thế lớp Java đã nạp.
- **Phạm vi nhìn thấy phụ thuộc class loader/module layer.** `ServiceLoader.load(S.class)` sử dụng context class loader của luồng gọi theo cách nạp thông thường; có overload nhận class loader rõ ràng. Hãy kiểm tra nơi đặt provider JAR nếu chạy không thấy dịch vụ.
- **Đừng phụ thuộc vào thứ tự provider** trừ khi chính ứng dụng có quy tắc chọn được kiểm soát. Chọn theo `id`, cấu hình hoặc ưu tiên được định nghĩa và xử lý trùng lặp.
- **Provider lỗi có thể làm quá trình khám phá thất bại** (chẳng hạn `ServiceConfigurationError` vì tên lớp sai, kiểu không phù hợp hoặc không tạo được instance). Ghi lại nguyên nhân rõ ràng, quyết định fail fast hay fallback theo yêu cầu nghiệp vụ.
- **`ServiceLoader` không được thiết kế để chia sẻ tùy tiện giữa nhiều luồng.** Nếu dùng lâu dài ở môi trường đa luồng, thiết kế việc khởi tạo, đồng bộ và lưu cache dịch vụ ở tầng điều phối.

`ServiceLoader` là một lựa chọn để hiện thực SPI, **không phải định nghĩa duy nhất của SPI**. Framework có thể đăng ký provider bằng cấu hình, dependency injection, factory registry hoặc cơ chế plugin riêng.

### Classpath khác gì với Java module system (JPMS)?

Với ví dụ **classpath**, file `META-INF/services/...` là cách đăng ký thông dụng. Với **named modules** trên module path, provider có thể được khai báo bằng `provides ... with ...`, còn module thực hiện việc tra cứu khai báo `uses ...`. Ví dụ minh họa mối quan hệ (không phải hai module đầy đủ có thể biên dịch riêng chỉ từ đoạn trích này):

```java
// module-info.java của module chứa API/SPI và mã gọi ServiceLoader
module formatter.core {
    exports demo.api;
    exports demo.spi;
    uses demo.spi.FormatterProvider;
}

// module-info.java của module provider (trong dự án/module khác)
module formatter.upper {
    requires formatter.core;
    provides demo.spi.FormatterProvider with demo.provider.UppercaseProvider;
}
```

Trong JPMS, cần cấu hình module path và việc phân giải module/layer phù hợp. Không nên dùng đồng thời hai cách đăng ký chỉ vì “càng nhiều càng tốt”; hãy xác định ứng dụng chạy trên classpath hay module path và kiểm tra chính cơ chế đó.

## 5. API và SPI trong những thư viện quen thuộc

**JDBC** là ví dụ điển hình. Ứng dụng dùng API `DriverManager.getConnection(...)`, `Connection`, `PreparedStatement`, `ResultSet` để truy cập cơ sở dữ liệu. Nhà cung cấp driver triển khai `java.sql.Driver` và đăng ký driver để runtime có thể tìm thấy. Ứng dụng không cần tự viết logic giao tiếp của từng hệ quản trị cơ sở dữ liệu. Lưu ý `java.sql.Driver` là điểm mở rộng SPI; consumer thường không trực tiếp khởi tạo driver bằng tên lớp cụ thể.

Các mô hình tương tự xuất hiện trong hệ sinh thái Java: thư viện logging sử dụng các implementation khác nhau, hệ thống serializer có thể đăng ký codec, và framework web có các adapter cho từng công nghệ. **Không phải mọi thư viện trong các nhóm này đều dùng `ServiceLoader`**; cần xem hợp đồng và cơ chế đăng ký thực tế của từng thư viện.

## 6. Thiết kế hợp đồng cho đúng phía

Khi viết **API cho consumer**:

- Đặt tên theo nhu cầu nghiệp vụ: `format`, `save`, `send`, thay vì lộ cách phát hiện provider hay tên lớp cụ thể.
- Quy định kết quả, lỗi, xử lý `null`, thread safety và vòng đời đối tượng mà người gọi cần biết.
- Giữ phụ thuộc của consumer vào hợp đồng ổn định; hạn chế bắt consumer import gói `spi`/`internal`.

Khi viết **SPI cho provider**:

- Nêu rõ nghĩa của từng method, điều kiện hợp lệ, thứ tự/lần gọi, thread safety, cách quản lý tài nguyên và phương thức đóng khi cần.
- Mô tả cơ chế đăng ký, yêu cầu constructor/factory, cách nạp và thông báo lỗi khi provider không hợp lệ.
- Thiết kế versioning có chủ đích: thêm abstract method vào SPI hiện có có thể làm provider cũ không còn tương thích; cân nhắc default method, interface mới hoặc phiên bản hợp đồng mới khi thích hợp.
- Tách contract khỏi implementation. Provider không nên phụ thuộc vào chi tiết nội bộ không được công bố của framework.

Ở tầng điều phối, cần quy định rõ cách chọn giữa nhiều provider, việc không có provider, trùng mã nhận diện, tình huống provider khởi tạo lỗi và chính sách fallback. Không nên bắt tất cả lỗi rồi âm thầm bỏ qua: hệ thống có thể chạy sai mà không ai biết.

## 7. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “API là interface; SPI là class.” | Cả hai là vai trò của hợp đồng. SPI thường là interface/abstract class; API có thể gồm nhiều kiểu và phương thức. |
| “Cứ `implements` là đã dùng SPI.” | Chỉ là SPI theo nghĩa mở rộng khi hệ thống công bố điểm triển khai và có cơ chế nhận/gọi provider theo hợp đồng. |
| “Provider JAR có trong máy thì `ServiceLoader` tự nhận.” | Nó phải nằm trong phạm vi nạp thích hợp, được đăng ký đúng và phù hợp cơ chế classpath/JPMS. |
| “Gọi `reload()` sẽ thay provider đang chạy bằng JAR mới.” | `reload()` làm mới cache khám phá của loader, không tự triển khai hot swap hay thay class loader. |
| “SPI chỉ cần compile được là an toàn tương thích.” | Còn phải tuân thủ ngữ nghĩa, vòng đời, ngoại lệ và phiên bản contract lúc chạy. |
| “Plugin nạp động luôn an toàn vì nằm sau SPI.” | SPI là ranh giới kiến trúc, không phải sandbox bảo mật. Provider vẫn chạy với quyền của tiến trình JVM trừ khi có kiến trúc cô lập riêng. |

## 8. Cách tự kiểm tra đã hiểu

1. **Đổi provider:** Tạo `LowercaseProvider` với `id()` trả `"lower"`, trả về formatter dùng `toLowerCase(Locale.ROOT)`; thêm lớp đó vào tệp `META-INF/services/demo.spi.FormatterProvider`. Consumer chỉ cần đổi tham số `"upper"` thành `"lower"` để chọn hành vi.
2. **Thiếu provider:** Bỏ đăng ký provider và quan sát nhánh lỗi. Sau đó quyết định yêu cầu sản phẩm là báo lỗi, cấu hình mặc định hay fallback.
3. **Trùng provider:** Đăng ký hai provider cùng `id`. Hỏi: mã ví dụ đang chọn cái nào? Vì sao thiết kế thực tế nên phát hiện trùng hoặc có quy tắc ưu tiên rõ ràng?
4. **Đánh dấu ranh giới:** Trong mã trên, `Main` là consumer; `Formatters` và `TextFormatter` tạo API; `FormatterProvider` là SPI; `UppercaseProvider` là provider; tệp `META-INF/services` là metadata đăng ký.

**Tự hỏi khi gặp một thư viện mới:** “Mã nghiệp vụ gọi bề mặt nào?” là câu hỏi về API. “Muốn viết implementation thay thế, tôi phải triển khai và đăng ký hợp đồng nào?” là câu hỏi về SPI. Hiểu cả hai phía là nền tảng để thiết kế dịch vụ Java có khả năng thay đổi provider mà ít sửa mã consumer.