# Chọn provider theo định danh, khả năng hỗ trợ và cấu hình tường minh

Khi ứng dụng Java có nhiều provider cho cùng một dịch vụ, **phát hiện được provider chưa có nghĩa là chọn đúng provider**. `ServiceLoader` giúp tìm các implementation được đăng ký, nhưng không thay ứng dụng quyết định provider nào phù hợp với yêu cầu hiện tại. Việc lựa chọn nên dựa trên một chính sách rõ ràng: **định danh**, **khả năng hỗ trợ**, và **cấu hình tường minh**.

Bài này đi từ yêu cầu thiết kế đến một chương trình Java 17 chạy được: có hai provider lời chào, một bộ chọn provider và ba chế độ kiểm chứng. Đặc biệt, hai provider đều hỗ trợ tiếng Việt, nên đây là ví dụ thực tế của tình huống **nhiều provider cùng phù hợp**.

## 1. Từ khám phá đến lựa chọn: hai bước khác nhau

Xét một ứng dụng cho phép cài nhiều implementation của `GreetingProvider`:

```text
                     Runtime classpath
         +----------------+----------------+
         |                |                |
  CasualProvider    FormalProvider    Provider khác...
         |                |
         +--------+-------+
                  |
    ServiceLoader<GreetingProvider>
                  |
                  v
       Danh sách provider có mặt
                  |
                  v
          ProviderResolver
         /        |         \
     định danh  supports()  cấu hình
         \        |         /
                  v
        Provider được lựa chọn
                  |
                  v
          greet(request)
```

Cần phân biệt:

- **Discovery (khám phá):** nhận diện các provider hiện diện và được đăng ký hợp lệ. Trên classpath, `ServiceLoader` dùng tài nguyên `META-INF/services/<tên-đầy-đủ-của-SPI>`.
- **Selection (lựa chọn):** xác định provider nào nên xử lý **một yêu cầu cụ thể**. Việc này thuộc chính sách của ứng dụng, không được `ServiceLoader` tự giải quyết.
- **Invocation (gọi thực thi):** sau khi đã chọn, dùng provider đã chọn để xử lý; lỗi nghiệp vụ của provider phải được xử lý theo hợp đồng, không tùy tiện chuyển qua provider khác.

Nếu viết `ServiceLoader.load(SPI.class).iterator().next()` để lấy “provider tốt nhất”, bạn đang vô tình đồng nhất thứ tự khám phá với thứ tự ưu tiên. **Không có bảo đảm chung rằng provider đầu tiên là provider mong muốn.** Khi JAR, class loader hoặc cách đóng gói thay đổi, hành vi có thể thay đổi theo.

## 2. Ba tiêu chí lựa chọn

### 2.1. Theo định danh ổn định (`providerId`)

Mỗi provider công bố một định danh duy nhất, ví dụ `casual`, `formal`, `postgres`, `s3` hoặc `local`. Ứng dụng lưu định danh trong cấu hình, sau đó tra đúng provider tương ứng.

Một định danh tốt cần:

- Đủ ổn định để không bị thay đổi tùy hứng giữa các lần phát hành.
- Phân biệt với tên class và vị trí JAR, vì các chi tiết triển khai có thể đổi.
- Có quy tắc duy nhất trong **phạm vi registry đang được dùng**; phát hiện trùng phải báo lỗi hoặc có cơ chế giải quyết xung đột được tài liệu hóa.
- Có quy ước tên rõ ràng (ví dụ chữ thường, không khoảng trắng). Ví dụ bên dưới dùng `casual` và `formal`.

**Khi nào dùng?** Khi người vận hành hoặc cấu hình ứng dụng yêu cầu đúng một provider, chẳng hạn yêu cầu phải dùng driver/adapter cụ thể. Với cấu hình chọn chính xác, **thiếu provider hoặc provider không hỗ trợ yêu cầu phải báo lỗi**; chuyển âm thầm sang provider khác có thể làm sai hành vi hoặc vi phạm yêu cầu vận hành.

### 2.2. Theo khả năng hỗ trợ (`supports(request)`)

Một provider có thể hỗ trợ một tập trường hợp thay vì mọi yêu cầu. Hợp đồng có thể công bố tập capability cố định như MIME type, version, thuật toán, giao thức, hoặc dùng một predicate:

```java
boolean supports(GreetingRequest request);
```

Điều này giúp hệ thống lọc các provider không đáp ứng yêu cầu. Ví dụ, một provider hỗ trợ `en` và `vi`, provider khác chỉ hỗ trợ `vi`.

Nhưng **lọc không đồng nghĩa chọn duy nhất**:

| Số provider hỗ trợ | Chính sách hợp lý |
|---:|---|
| 0 | Báo không có provider phù hợp; chỉ fallback nếu sản phẩm định nghĩa rõ |
| 1 | Chọn provider duy nhất |
| 2 trở lên | Dùng cấu hình ưu tiên, quy tắc được công bố hoặc báo mơ hồ |
 
Một `supports` tốt nên nhanh, ít tác dụng phụ, nhất quán với khả năng thực sự khi gọi xử lý. Nếu capability phụ thuộc trạng thái ngoài (máy chủ, license, quota), kết quả kiểm tra tại thời điểm chọn có thể đã lỗi thời khi thực thi; cần xử lý lỗi runtime riêng.

### 2.3. Theo cấu hình tường minh

Cấu hình có thể đến từ tham số JVM, file `.properties`, biến môi trường hoặc hệ thống cấu hình của framework. Hai ý nghĩa cần tách bạch:

- **Chỉ định bắt buộc (hard pin):** `app.provider=formal` nghĩa là phải dùng `formal`. Không thấy hoặc không tương thích thì thất bại.
- **Ưu tiên khi có nhiều lựa chọn (tie-break preference):** `app.prefer=formal` nghĩa là khi nhiều provider cùng hỗ trợ yêu cầu, ưu tiên `formal` nếu nó nằm trong tập phù hợp. Nếu chỉ một provider phù hợp, dùng provider đó. Nếu nhiều provider mà cấu hình ưu tiên không khớp, ví dụ này báo lỗi rõ ràng.

Đây là **chính sách được thiết kế cho ví dụ**; Java không mặc định diễn giải hai thuộc tính này. Ứng dụng thật có thể đặt tên khác, nhưng phải công bố thứ tự ưu tiên và tính bắt buộc của từng lựa chọn.

## 3. Chính sách giải quyết xung đột trước khi viết mã

Ta dùng các quy tắc theo đúng thứ tự:

1. Tải danh sách provider; kiểm tra ID rỗng hoặc trùng. Nếu không có provider thì báo lỗi.
2. Nếu `app.provider` khác `auto`, chỉ tra cứu **đúng ID được chỉ định** rồi kiểm tra `supports(request)`. Nếu sai, báo lỗi; không fallback.
3. Nếu `app.provider=auto`, lọc các provider trả `true` từ `supports(request)`.
4. Nếu không có provider phù hợp thì báo lỗi.
5. Nếu chỉ có một provider phù hợp thì chọn nó.
6. Nếu có nhiều provider, dùng `app.prefer` để giải quyết. Không có cấu hình hoặc ưu tiên không phù hợp thì báo lỗi mơ hồ/không hợp lệ.
7. Khi `app.provider` đã chỉ định chính xác, **cấm đồng thời** khai báo `app.prefer` để tránh cấu hình tự mâu thuẫn.

Quy tắc này cố ý không chọn mặc định theo tên class, vị trí JAR, hoặc thứ tự `ServiceLoader`. Nếu một sản phẩm thực sự muốn ưu tiên theo điểm số/chi phí/độ tin cậy, hãy thiết kế tiêu chí chấm điểm và quy tắc xử lý hòa; đừng dùng thứ tự khám phá như một độ ưu tiên ngầm.

## 4. Ví dụ Java 17: SPI và hai provider có capability chồng lấp

Thư mục mẫu:

```text
provider-selection-demo/
├── src/
│   └── demo/
│       ├── GreetingRequest.java
│       ├── GreetingProvider.java
│       ├── CasualProvider.java
│       ├── FormalProvider.java
│       ├── ProviderResolver.java
│       └── Main.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.GreetingProvider
```

Mẫu chạy trên **classpath**, không dùng `module-info.java`. Hai provider được đặt chung một thư mục nguồn để dễ tái hiện; khi triển khai thật, có thể đóng mỗi provider thành một JAR độc lập. Bộ chọn và consumer vẫn chỉ phụ thuộc vào SPI.

### 4.1. Kiểu yêu cầu

Tệp `src/demo/GreetingRequest.java`:

```java
package demo;

public record GreetingRequest(String language, String name) {
    public GreetingRequest {
        if (language == null || language.isBlank()) {
            throw new IllegalArgumentException("language is required");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
    }
}
```

`record` (Java 16+) làm rõ dữ liệu đầu vào. Ví dụ chỉ chấp nhận các mã ngôn ngữ đơn giản `en`, `vi`; trong sản phẩm đa ngôn ngữ thật, hãy thống nhất chính sách chuẩn hóa mã ngôn ngữ (ví dụ `vi-VN`) trước khi lọc capability.

### 4.2. Hợp đồng SPI

Tệp `src/demo/GreetingProvider.java`:

```java
package demo;

public interface GreetingProvider {
    String id();

    boolean supports(GreetingRequest request);

    String greet(GreetingRequest request);
}
```

`id()` cung cấp định danh lựa chọn. `supports()` kiểm tra khả năng xử lý yêu cầu. `greet()` là hành vi mà consumer cuối cùng cần.

Hợp đồng ngữ nghĩa cho ví dụ: `id()` khác `null` và không rỗng; `supports()` không gây tác dụng phụ và trả kết quả phù hợp với việc `greet()` có thể thực thi; `greet()` chỉ được gọi khi request được hỗ trợ. Java không tự bảo đảm ngữ nghĩa này; nó phải được kiểm thử và quy định cho tác giả provider.

### 4.3. Provider dùng văn phong thân mật

Tệp `src/demo/CasualProvider.java`:

```java
package demo;

public final class CasualProvider implements GreetingProvider {
    @Override
    public String id() {
        return "casual";
    }

    @Override
    public boolean supports(GreetingRequest request) {
        return "en".equals(request.language())
                || "vi".equals(request.language());
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!supports(request)) {
            throw new IllegalArgumentException("Unsupported language");
        }

        if ("vi".equals(request.language())) {
            return "Chào " + request.name() + "!";
        }
        return "Hello, " + request.name() + "!";
    }
}
```

`CasualProvider` hỗ trợ `en` và `vi`.

### 4.4. Provider dùng văn phong trang trọng

Tệp `src/demo/FormalProvider.java`:

```java
package demo;

public final class FormalProvider implements GreetingProvider {
    @Override
    public String id() {
        return "formal";
    }

    @Override
    public boolean supports(GreetingRequest request) {
        return "vi".equals(request.language());
    }

    @Override
    public String greet(GreetingRequest request) {
        if (!supports(request)) {
            throw new IllegalArgumentException("Unsupported language");
        }
        return "Kính chào " + request.name() + ".";
    }
}
```

`FormalProvider` chỉ hỗ trợ `vi`. Cả hai lớp `public` đều có constructor không tham số công khai mặc định, đúng yêu cầu khởi tạo provider theo cách đăng ký trên classpath được dùng trong ví dụ.

Như vậy:

| Ngôn ngữ yêu cầu | Provider hỗ trợ | Ý nghĩa |
|---|---|---|
| `en` | `casual` | Chỉ một ứng viên |
| `vi` | `casual`, `formal` | Hai ứng viên, cần quyết định |
| `fr` | Không có | Không thể tự chọn hợp lệ |

### 4.5. Đăng ký provider cho `ServiceLoader`

Nội dung tệp `resources/META-INF/services/demo.GreetingProvider`:

```text
demo.CasualProvider
demo.FormalProvider
```

Tên tệp là tên đầy đủ của **service type**. Mỗi dòng là tên đầy đủ của **một provider class**; đây là cách đăng ký nhiều provider trong cùng một tài nguyên. Tệp phải được đưa vào `out/META-INF/services/demo.GreetingProvider` khi chạy classpath.

Nếu đóng gói nhiều JAR, mỗi provider JAR có thể chứa riêng tệp cùng tên nhưng liệt kê provider do JAR đó cung cấp. `ServiceLoader` có thể khám phá nhiều tài nguyên dịch vụ cùng tên từ các phần tử classpath nhìn thấy được; không cần viết một danh sách provider duy nhất vào consumer.

## 5. Viết bộ chọn có chính sách quyết định rõ ràng

Tệp `src/demo/ProviderResolver.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;
import java.util.stream.Collectors;

public final class ProviderResolver {
    private final Map<String, GreetingProvider> byId = new TreeMap<>();

    public ProviderResolver() {
        for (GreetingProvider provider
                : ServiceLoader.load(GreetingProvider.class)) {
            String id = provider.id();

            if (id == null || id.isBlank()) {
                throw new IllegalStateException("Provider id is blank");
            }
            if (byId.putIfAbsent(id, provider) != null) {
                throw new IllegalStateException("Duplicate provider id: " + id);
            }
        }

        if (byId.isEmpty()) {
            throw new IllegalStateException("No providers registered");
        }
    }

    public GreetingProvider select(
            GreetingRequest request, String providerId, String preferredId) {

        if (!"auto".equals(providerId)) {
            GreetingProvider selected = byId.get(providerId);

            if (selected == null) {
                throw new IllegalArgumentException(
                        "Unknown provider: " + providerId);
            }
            if (!selected.supports(request)) {
                throw new IllegalArgumentException(
                        "Provider " + providerId
                                + " does not support " + request.language());
            }
            return selected;
        }

        List<GreetingProvider> matches = new ArrayList<>();

        for (GreetingProvider provider : byId.values()) {
            if (provider.supports(request)) {
                matches.add(provider);
            }
        }

        if (matches.isEmpty()) {
            throw new IllegalStateException(
                    "No provider supports language: " + request.language());
        }
        if (matches.size() == 1) {
            return matches.get(0);
        }

        if (preferredId != null && !preferredId.isBlank()) {
            for (GreetingProvider provider : matches) {
                if (preferredId.equals(provider.id())) {
                    return provider;
                }
            }
            throw new IllegalArgumentException(
                    "Preferred provider " + preferredId
                            + " does not support " + request.language());
        }

        String ids = matches.stream()
                .map(GreetingProvider::id)
                .collect(Collectors.joining(", "));
        throw new IllegalStateException(
                "Ambiguous providers for language "
                        + request.language() + ": " + ids);
    }
}
```

Điểm quan trọng của bộ chọn:

- Registry `TreeMap` lưu theo định danh nên có **thứ tự ổn định để trình bày lỗi**. Ta không dựa vào thứ tự `ServiceLoader` trả về.
- `putIfAbsent` làm **trùng ID trở thành lỗi cấu hình rõ ràng**, thay vì cho provider đăng ký sau ghi đè provider trước.
- Nhánh chỉ định ID kiểm tra `supports()`; việc biết đúng ID chưa đủ để kết luận provider xử lý được một yêu cầu bất kỳ.
- Nhánh `auto` kiểm tra mọi provider, nên không bỏ sót candidate chỉ vì đứng sau một provider khác trong thứ tự khám phá.
- Khi hai provider hỗ trợ cùng một request, việc không có quy tắc phân định được xem là **mơ hồ**, không phải cơ hội để lấy provider đầu tiên.
- `preferredId` chỉ là **quy tắc phá hòa (tie-breaker)** trong ví dụ này: nó chỉ được xét khi có trên một provider phù hợp. Nếu chỉ có một provider phù hợp, bộ chọn dùng provider duy nhất, dù có đặt `app.prefer` cho provider khác. Nếu muốn ưu tiên có tính bắt buộc, hãy dùng `app.provider`.

Trong hệ thống thật, việc gọi `id()` và `supports()` có thể ném ngoại lệ hoặc rất tốn chi phí. Nếu yêu cầu sản phẩm cần xử lý provider lỗi riêng lẻ, hãy thiết kế chính sách lỗi có log/metrics và phân loại lỗi rõ ràng; không nên `catch (Exception)` rồi loại bỏ âm thầm một provider để có kết quả tưởng như hợp lệ.

## 6. Consumer nhận cấu hình tường minh từ JVM

Tệp `src/demo/Main.java`:

```java
package demo;

public final class Main {
    public static void main(String[] args) {
        String language = System.getProperty("app.language", "en");
        String providerId = System.getProperty("app.provider", "auto");
        String preferredId = System.getProperty("app.prefer", "");

        if (providerId.isBlank()) {
            throw new IllegalArgumentException("app.provider is blank");
        }
        if (!"auto".equals(providerId) && !preferredId.isBlank()) {
            throw new IllegalArgumentException(
                    "Use either app.provider or app.prefer");
        }

        GreetingRequest request = new GreetingRequest(language, "Linh");
        ProviderResolver resolver = new ProviderResolver();

        GreetingProvider provider =
                resolver.select(request, providerId, preferredId);

        System.out.println("Selected: " + provider.id());
        System.out.println(provider.greet(request));
    }
}
```

`Main` không import hay khởi tạo `CasualProvider` hoặc `FormalProvider`. Khi chạy, ứng dụng có thể truyền các JVM system properties:

- `-Dapp.language=en|vi`: yêu cầu ngôn ngữ. Mặc định `en`.
- `-Dapp.provider=<id>`: chỉ định provider bắt buộc. Mặc định `auto`, tức là chọn theo capability.
- `-Dapp.prefer=<id>`: ưu tiên khi có nhiều provider phù hợp. Mặc định rỗng.

**Cú pháp `-D...` phải nằm trước tên class `demo.Main`** để JVM nhận thuộc tính. Thông số này được cung cấp khi **khởi động tiến trình**; thay đổi một file cấu hình ngoài hệ thống không tự làm bộ chọn đang giữ trong bộ nhớ chạy lại.

Nếu dùng file cấu hình hoặc biến môi trường, tầng khởi động nên chuẩn hóa giá trị về cùng bộ ba `language/providerId/preferredId`, xác định nguồn nào ưu tiên cao hơn và ghi lại cấu hình có hiệu lực. Ví dụ này dùng system properties để dễ tái hiện, không mặc định đọc file hay biến môi trường.

## 7. Biên dịch và chạy được trên Java 17+

Đứng trong thư mục `provider-selection-demo` chứa hai thư mục `src`, `resources`. Cần JDK 17+ và terminal hỗ trợ Unicode để hiển thị tiếng Việt đúng.

### Windows PowerShell

```powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null

javac -encoding UTF-8 -d out src/demo/GreetingRequest.java src/demo/GreetingProvider.java src/demo/CasualProvider.java src/demo/FormalProvider.java src/demo/ProviderResolver.java src/demo/Main.java

Copy-Item resources/META-INF/services/demo.GreetingProvider out/META-INF/services/demo.GreetingProvider

java -cp out demo.Main
```

Kết quả stdout:

```text
Selected: casual
Hello, Linh!
```

### Linux/macOS

```bash
mkdir -p out/META-INF/services

javac -encoding UTF-8 -d out src/demo/*.java

cp resources/META-INF/services/demo.GreetingProvider out/META-INF/services/demo.GreetingProvider

java -cp out demo.Main
```

Kết quả stdout cũng là:

```text
Selected: casual
Hello, Linh!
```

Vì `language=en`, chỉ `CasualProvider` hỗ trợ, nên chọn tự động không cần cấu hình ưu tiên.

**Lưu ý kiểm tra classpath:** chỉ biên dịch lớp `.class` là chưa đủ. Nếu quên copy `resources/META-INF/services/demo.GreetingProvider` vào `out`, `ServiceLoader` không khám phá được provider từ ví dụ này và constructor của `ProviderResolver` ném `IllegalStateException: No providers registered` trên stderr (cùng stack trace). Nếu chạy trong JAR, tài nguyên đăng ký phải nằm trong JAR provider và các JAR cần thiết phải nhìn thấy từ class loader đang dùng.

## 8. Kiểm chứng từng chiến lược lựa chọn

Các lệnh sau giữ nguyên mã đã biên dịch. Lệnh `java -cp out` chạy trên cả Windows, Linux và macOS vì classpath chỉ có một phần tử `out`.

### Trường hợp A: chọn theo định danh bắt buộc

```bash
java -Dapp.language=vi -Dapp.provider=casual -cp out demo.Main
```

Stdout:

```text
Selected: casual
Chào Linh!
```

Dù `FormalProvider` cũng hỗ trợ `vi`, cấu hình **chỉ định** `casual`, nên bộ chọn chọn đúng định danh. Không dùng thứ tự nạp.

### Trường hợp B: chọn theo capability duy nhất

```bash
java -Dapp.language=en -cp out demo.Main
```

Stdout:

```text
Selected: casual
Hello, Linh!
```

Bộ chọn lọc theo `supports()`; `FormalProvider` không hỗ trợ `en`, nên chỉ còn `casual`.

### Trường hợp C: capability bị chồng lấp và có cấu hình ưu tiên

```bash
java -Dapp.language=vi -Dapp.prefer=formal -cp out demo.Main
```

Stdout:

```text
Selected: formal
Kính chào Linh.
```

Cả hai provider hỗ trợ `vi`; `app.prefer=formal` là quy tắc phá hòa có chủ đích, nên kết quả xác định.

### Trường hợp D: capability bị chồng lấp nhưng thiếu chính sách ưu tiên

```bash
java -Dapp.language=vi -cp out demo.Main
```

Chương trình thất bại với `IllegalStateException`. Phần thông báo của ngoại lệ trên stderr là:

```text
Ambiguous providers for language vi: casual, formal
```

Thứ tự hai ID trong thông báo ổn định vì registry là `TreeMap`. Dòng trên **không phải stdout**: chương trình không đến hai lệnh `println` trong `Main`; Java còn in stack trace trên stderr.

### Trường hợp E: chỉ định provider không hỗ trợ yêu cầu

```bash
java -Dapp.language=en -Dapp.provider=formal -cp out demo.Main
```

Phần thông báo ngoại lệ `IllegalArgumentException`:

```text
Provider formal does not support en
```

Không tự chuyển sang `casual`. Với lựa chọn bắt buộc, fallback ngầm làm mất ý nghĩa cấu hình.

### Trường hợp F: không provider nào hỗ trợ yêu cầu

```bash
java -Dapp.language=fr -cp out demo.Main
```

Phần thông báo ngoại lệ `IllegalStateException`:

```text
No provider supports language: fr
```

Đây là kết quả của bộ lọc capability; nó **khác** trường hợp không tìm thấy provider nào đã đăng ký.

### Trường hợp G: ID cấu hình không tồn tại

```bash
java -Dapp.language=vi -Dapp.provider=missing -cp out demo.Main
```

Phần thông báo ngoại lệ `IllegalArgumentException`:

```text
Unknown provider: missing
```

Bộ chọn không nên biến lỗi đánh máy trong cấu hình thành một kết quả ngẫu nhiên.

### Trường hợp H: cấu hình mâu thuẫn

```bash
java -Dapp.language=vi -Dapp.provider=casual -Dapp.prefer=formal -cp out demo.Main
```

Phần thông báo ngoại lệ `IllegalArgumentException`:

```text
Use either app.provider or app.prefer
```

Việc báo lỗi ngay ở tầng cấu hình giúp tránh trường hợp mỗi người hiểu khác nhau về độ ưu tiên của hai tùy chọn.

## 9. Chọn cấu hình trong sản phẩm thực tế

Một quy trình lựa chọn dễ kiểm soát có thể được diễn đạt:

```text
Đọc và kiểm tra cấu hình
        |
        v
Có providerId bắt buộc?
   | Có                     | Không (auto)
   v                         v
Tra ID trong registry     Lọc bằng supports(request)
   |                         |
   +--> Không thấy? Lỗi      +--> 0 ứng viên? Lỗi
   |                         +--> 1 ứng viên? Chọn
   +--> Không hỗ trợ? Lỗi    +--> N ứng viên? Xét ưu tiên
   |                                   |
   v                                   +--> Ưu tiên hợp lệ? Chọn
Chọn chính xác                        +--> Không? Lỗi mơ hồ
```

Khi ánh xạ vào cấu hình ngoài ứng dụng, nên phân biệt:

| Tình huống vận hành | Cách thể hiện | Cách ứng xử mong muốn |
|---|---|---|
| Chính sách bắt buộc nhà cung cấp cụ thể | `providerId = "formal"` | Không thấy/không hỗ trợ thì fail fast |
| Chọn tự động vì chỉ có một implementation hỗ trợ | `providerId = "auto"` | Chỉ chọn khi lọc ra đúng một ứng viên |
| Nhiều implementation cùng hỗ trợ | `providerId = "auto"`, `preferredId = "formal"` | Chọn ứng viên ưu tiên nếu nó hỗ trợ |
| Không chấp nhận kết quả mơ hồ | `providerId = "auto"` và không ưu tiên | Báo lỗi thay vì phụ thuộc thứ tự |
| Cho phép chuyển sang phương án dự phòng | Cấu hình fallback **riêng** | Chỉ thử fallback khi loại lỗi phù hợp và có quy tắc được công bố |

Các hệ thống có nhiều môi trường (local, staging, production) cần ghi rõ **cấu hình có hiệu lực** và định danh provider đã được chọn. Có thể log các ID, số lượng ứng viên và lý do lựa chọn, nhưng không ghi bí mật như token, mật khẩu hoặc toàn bộ payload nhạy cảm.

Nếu dùng dependency injection (ví dụ một framework IoC), framework có thể cung cấp cơ chế đặt tên, qualifier hoặc ưu tiên bean khác. Dù cơ chế khác, vấn đề lõi vẫn giống nhau: kiểm tra tính hợp lệ của ứng viên, cách phân xử nhiều implementation và bảo đảm cấu hình tường minh được tôn trọng.

## 10. Những điểm khó trong hệ thống lớn

### 10.1. Định danh trùng không đồng nghĩa capability trùng

Hai provider có cùng `id()` là **xung đột định danh**: registry không thể biết cấu hình `provider=formal` muốn chỉ đến lớp nào. Hai provider cùng `supports(request)=true` chỉ là **chồng lấp khả năng**: có thể hợp lệ và được giải quyết bằng chính sách chọn.

Đừng gộp hai loại xung đột. Bộ chọn ở ví dụ báo lỗi sớm khi trùng ID, nhưng chỉ báo mơ hồ khi có nhiều ứng viên sau bước lọc capability.

### 10.2. Khi nào dùng điểm số hoặc mức ưu tiên?

Một sản phẩm có thể muốn cân nhắc chi phí, độ trễ, khả năng truy cập, phiên bản, khu vực triển khai hoặc thứ tự ưu tiên. Khi đó có thể mở rộng SPI để trả metadata hoặc viết bộ đánh giá ứng viên.

Tuy nhiên phải quyết định **từ trước**:

- Những tiêu chí nào là điều kiện cứng (provider không thỏa phải bị loại)?
- Những tiêu chí nào dùng xếp hạng và thứ tự so sánh ra sao?
- Khi bằng điểm sẽ chọn thế nào? Dùng ID có được phép làm quy tắc thứ cấp hay phải báo mơ hồ?
- Điểm số có thay đổi theo thời gian không; cache lựa chọn trong bao lâu?

Không nên thay bằng `findFirst()` rồi gọi đó là “ưu tiên cao nhất”. Thứ tự khám phá của `ServiceLoader` không phải trọng số chất lượng.

### 10.3. Bảo đảm hợp đồng `supports()` và thực thi

`supports()` chỉ là một kiểm tra mà provider tự khai báo, **không chứng minh** yêu cầu chắc chắn xử lý thành công. Thực thi vẫn có thể thất bại do mạng, file, quota, quyền truy cập hoặc thay đổi trạng thái. Hãy quy định ngoại lệ, retry và fallback theo loại lỗi.

Fallback đặc biệt nguy hiểm khi hành động có tác dụng phụ: nếu provider đầu tiên đã gửi một thông báo nhưng trả lỗi muộn, thử provider thứ hai có thể gửi trùng. Cơ chế idempotency hoặc xác nhận kết quả cần được thiết kế ở mức nghiệp vụ, không giao mặc định cho SPI.

### 10.4. Phiên bản SPI và phụ thuộc class loader

Nếu một provider được biên dịch với phiên bản SPI mới nhưng ứng dụng chạy với SPI cũ, có thể gặp lỗi nạp lớp, `AbstractMethodError`, hoặc vi phạm ngữ nghĩa. Ngoài ra, hai class loader khác nhau có thể nạp hai bản của cùng tên interface, khiến một class không còn được xem là subtype của service type đang dùng.

Cần thống nhất phiên bản hợp đồng và class loader của phạm vi dịch vụ; xác thực metadata provider khi khởi động. Không tự coi việc có mặt trên classpath là bảo đảm tương thích.

### 10.5. Thời điểm khám phá và vòng đời lựa chọn

`ServiceLoader.load(...)` tạo bộ khám phá có bộ nhớ đệm provider đã được duyệt. Nó thường tải/khởi tạo lười khi duyệt. `reload()` chỉ làm mới cache của instance `ServiceLoader` đó; **không tự bổ sung JAR mới vào classpath, không hủy instance đang được consumer giữ, không cập nhật nóng class**.

Một registry tạo lúc khởi động như `ProviderResolver` trong ví dụ là **snapshot của các provider nó đã khám phá**. Nếu hệ thống cần plugin động hoặc hot reload, phải thiết kế riêng class loader/module layer, vòng đời instance, cập nhật registry an toàn và xử lý request đang chạy. `ServiceLoader` không tự giải quyết trọn quy trình này.

`ServiceLoader` cũng không được bảo đảm thread-safe khi chia sẻ và thao tác trực tiếp từ nhiều luồng. Với ứng dụng đa luồng, có thể khởi tạo registry một lần, công bố nó theo cách an toàn và bảo đảm provider được chọn đáp ứng hợp đồng đồng thời.

### 10.6. Bảo mật provider và cấu hình

Provider thường chạy với quyền của ứng dụng Java. SPI là ranh giới thiết kế mã, **không phải sandbox**. Cần kiểm soát nguồn JAR/provider, dependency và quyền thực thi; không cho phép người dùng không tin cậy tự chọn một provider nguy hiểm chỉ bằng tham số cấu hình.

## 11. Lỗi phổ biến và cách tránh

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Chọn `iterator().next()` | Phụ thuộc thứ tự khám phá không được định nghĩa làm chính sách | Dùng ID, lọc capability, hoặc cấu hình rõ ràng |
| Cho provider tự gán ID không kiểm tra trùng | Có thể chọn nhầm implementation | Dựng registry có kiểm tra ID duy nhất |
| Chỉ kiểm tra ID mà bỏ qua `supports` | Gọi provider không xử lý được request | Kiểm tra capability cả khi chỉ định ID |
| Tự fallback khi cấu hình bắt buộc sai | Lệch yêu cầu vận hành, khó quan sát | Báo lỗi và nêu ID/capability cần thiết |
| Mọi provider đều hỗ trợ một request nhưng chọn provider đầu tiên | Tính mơ hồ bị giấu | Có quy tắc ưu tiên hoặc báo lỗi |
| Không đăng ký `META-INF/services` | `ServiceLoader` không tìm ra lớp provider | Kiểm tra tài nguyên trong classpath/JAR |
| Thay classpath khi JVM đang chạy rồi gọi `reload()` | Không có provider mới như kỳ vọng | Thiết kế cơ chế nạp động riêng hoặc khởi động lại |
| `supports()` làm thay đổi trạng thái | Kết quả lọc khó dự đoán | Predicate có ngữ nghĩa ổn định, ít tác dụng phụ |
| Catch mọi lỗi provider rồi bỏ qua | Che lỗi cấu hình và lỗi phần mềm | Phân loại lỗi, log và chính sách xử lý minh bạch |

## 12. Bài tập tự kiểm tra

1. **Thêm provider ID `neutral`** hỗ trợ `en` và `fr`. Xác định đầu ra hoặc lỗi của các lệnh dùng `app.language=en`, `fr` trước và sau khi có cấu hình `app.prefer=neutral`.
2. **Tạo trùng ID:** sửa `FormalProvider.id()` thành `"casual"`. Quan sát constructor `ProviderResolver` dừng với lỗi nào. Tại sao không nên chờ đến khi một request cụ thể xảy ra mới phát hiện?
3. **Kiểm tra phân biệt hard pin/preference:** giải thích khác nhau giữa `-Dapp.language=en -Dapp.provider=formal` và `-Dapp.language=en -Dapp.prefer=formal` trong chính sách hiện tại. Một lệnh báo lỗi, một lệnh chọn ứng viên duy nhất; điều này có phù hợp ý nghĩa đã công bố không?
4. **Giảm sai sót cấu hình:** bổ sung bước in danh sách ID và capability được công bố khi khởi động, rồi kiểm tra việc in thông tin có lộ bí mật cấu hình hay không.
5. **Thiết kế fallback riêng:** giả sử provider đã chọn gọi API ngoài và bị timeout. Xây chính sách retry/fallback chỉ cho tác vụ đọc, đồng thời giải thích rủi ro thao tác ghi lặp lại.

Khi triển khai một điểm mở rộng Java, hãy giữ ranh giới rõ ràng: **`ServiceLoader` khám phá provider; ứng dụng định nghĩa chính sách lựa chọn; provider thực hiện hợp đồng**. Chọn theo ID khi cần bắt buộc một implementation; lọc theo capability khi yêu cầu thay đổi theo từng request; dùng cấu hình ưu tiên hoặc báo lỗi có chủ đích khi nhiều provider cùng phù hợp.