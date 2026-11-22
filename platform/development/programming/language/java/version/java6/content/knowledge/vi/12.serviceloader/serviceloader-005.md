# ServiceLoader — Nạp lười khi duyệt nhà cung cấp

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích đúng ý nghĩa **nạp lười (lazy loading)** của `java.util.ServiceLoader`: phát hiện và khởi tạo nhà cung cấp (provider) khi chương trình thực sự duyệt tới, thay vì khởi tạo toàn bộ ngay khi gọi `load(...)`.
- Phân biệt các mốc `ServiceLoader.load(...)`, `iterator()`, `hasNext()`, `next()`, `findFirst()` và `stream()`, đặc biệt sự khác nhau giữa **tìm thấy lớp provider** và **tạo đối tượng provider**.
- Tạo một Service Provider Interface (SPI) hoạt động trên classpath với `META-INF/services`, chạy thử và quan sát thời điểm constructor được gọi.
- Hiểu cache của `ServiceLoader`, tác dụng và giới hạn của `reload()`, cũng như các lỗi về thứ tự lựa chọn, cấu hình, đồng thời và class loader.
- Sử dụng `ServiceLoader.Provider` cùng `stream()` (API hiện hành từ Java 9) để lọc provider trước khi tạo đối tượng khi phù hợp.

Bài học dùng Java 17+ để thực hành. `ServiceLoader` và cơ chế SPI nêu dưới đây vẫn là API được hỗ trợ trong Java hiện đại; không dựa vào cơ chế đã lỗi thời.

## 1. ServiceLoader và nhà cung cấp dịch vụ

Giả sử ứng dụng có một giao diện `Renderer` nhưng nhiều thư viện có thể cung cấp cách triển khai khác nhau: xuất văn bản thuần, HTML, PDF... Ứng dụng không muốn phụ thuộc trực tiếp vào tên lớp của mọi bản triển khai.

Trong mô hình SPI:

- **Service type**: giao diện hoặc lớp trừu tượng công bố hợp đồng, ví dụ `Renderer`.
- **Provider**: lớp (hoặc một cơ chế provider được module khai báo) có thể tạo ra đối tượng thực hiện hợp đồng.
- **Provider registration**: khai báo để runtime biết thư viện nào cung cấp dịch vụ; trên classpath là tệp `META-INF/services/<tên.đầy.đủ.Service>`, trong named module là `provides ... with ...`.
- **Consumer**: mã gọi `ServiceLoader.load(Renderer.class)` rồi duyệt các provider được phát hiện.

Luồng ý tưởng:

```text
Consumer
   |
   | ServiceLoader.load(Renderer.class)
   v
ServiceLoader<Renderer>  -- tạo đối tượng loader
   |
   | iterator / stream / findFirst, khi được duyệt thực sự
   v
Thông tin đăng ký provider trong classpath hoặc module
   |
   | tới nhà cung cấp cần thiết
   v
Provider được nạp/tạo theo yêu cầu
   |
   v
Renderer được đưa cho consumer sử dụng
```

**Nạp lười không đồng nghĩa mọi thứ đều xảy ra lúc `load(...)`**. `ServiceLoader` giữ cơ chế để tìm provider, còn hoạt động tìm, kiểm tra và khởi tạo diễn ra khi duyệt. Từ “load” trong tên phương thức không có nghĩa nó đã khởi tạo sẵn toàn bộ provider.

## 2. Mốc nào thực sự kích hoạt công việc?

| Lời gọi | Điều cần hiểu |
| --- | --- |
| `ServiceLoader.load(Renderer.class)` | Tạo `ServiceLoader` dùng **thread context class loader** hiện hành để tìm dịch vụ; không duyệt và khởi tạo ngay tất cả provider. Lời gọi vẫn có thể kiểm tra điều kiện truy cập dịch vụ, đặc biệt với named module. |
| `loader.iterator()` | Tạo iterator cho những provider có thể được duyệt; bản thân việc lấy iterator không yêu cầu khởi tạo toàn bộ provider. |
| `iterator.hasNext()` | Có thể tìm tài nguyên, đọc cấu hình, xác định provider tiếp theo và nạp thông tin lớp; **có thể phát sinh lỗi cấu hình**. Không giả định `hasNext()` là thao tác hoàn toàn miễn phí hoặc không làm I/O. |
| `iterator.next()` | Trả provider tiếp theo; nếu chưa được cache thì provider được tạo theo cơ chế của nó. Đây là thời điểm thường thấy constructor/provider factory chạy. |
| Vòng `for (Renderer r : loader)` | Dùng iterator ngầm. Nếu duyệt hết sẽ lần lượt tạo các provider cần đến; `break` sớm tránh khởi tạo những provider chưa được duyệt. |
| `loader.findFirst()` | Trả `Optional<Renderer>` chứa provider đầu tiên (nếu có); có thể khởi tạo provider đầu tiên nhưng không đòi hỏi khởi tạo tất cả provider còn lại. |
| `loader.stream()` | Trả `Stream<ServiceLoader.Provider<Renderer>>`; khi xử lý stream, các descriptor provider được tìm lười; gọi `Provider.get()` để nhận một instance. |
| `loader.reload()` | Xóa cache của loader; lần duyệt kế tiếp lại tìm provider theo nhu cầu. Đây **không phải** lệnh buộc JVM dỡ class hoặc hủy mọi instance cũ. |

Điểm hay bị nhầm: `hasNext()` có thể thực hiện **discovery/đọc metadata**, còn `next()` có thể thực hiện **instantiation**. Vì vậy không thể kết luận “chưa làm gì” chỉ vì chương trình chưa gọi `next()`. Ngược lại, chỉ gọi `load(...)` cũng không có nghĩa tất cả constructor đã chạy.

## 3. Ví dụ chạy được: chỉ tạo provider khi thực sự duyệt tới

Chúng ta xây một ứng dụng classpath có hai provider. Dùng một tệp cấu hình liệt kê hai lớp theo thứ tự giúp ví dụ có kết quả dễ kiểm chứng. Đây là cơ chế SPI classpath **vẫn còn được hỗ trợ hiện nay**.

### 3.1. Cấu trúc tệp

```text
service-demo/
├── src/
│   └── demo/
│       ├── spi/
│       │   └── Renderer.java
│       ├── providers/
│       │   ├── PlainRenderer.java
│       │   └── HtmlRenderer.java
│       └── App.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.spi.Renderer
```

Tên tệp đăng ký **phải đúng** tên đầy đủ của service type: `demo.spi.Renderer`. Đường dẫn `META-INF/services` phải xuất hiện ở gốc classpath hoặc bên trong JAR chạy với classpath. Tệp đăng ký sử dụng UTF-8.

### 3.2. Service interface

Tệp `src/demo/spi/Renderer.java`:

```java
package demo.spi;

public interface Renderer {
    String name();
}
```

### 3.3. Hai provider

Tệp `src/demo/providers/PlainRenderer.java`:

```java
package demo.providers;

import demo.spi.Renderer;

public class PlainRenderer implements Renderer {
    public PlainRenderer() {
        System.out.println("[ctor] PlainRenderer");
    }

    @Override
    public String name() {
        return "plain";
    }
}
```

Tệp `src/demo/providers/HtmlRenderer.java`:

```java
package demo.providers;

import demo.spi.Renderer;

public class HtmlRenderer implements Renderer {
    public HtmlRenderer() {
        System.out.println("[ctor] HtmlRenderer");
    }

    @Override
    public String name() {
        return "html";
    }
}
```

Constructor in log là thiết bị quan sát để thấy thời điểm tạo instance. Trong ứng dụng thật, không cần in log mỗi khi khởi tạo.

### 3.4. Đăng ký provider

Tệp `resources/META-INF/services/demo.spi.Renderer` chứa **đúng hai dòng**:

```text
demo.providers.PlainRenderer
demo.providers.HtmlRenderer
```

Với provider trên classpath, mỗi dòng là **tên lớp đầy đủ**, không phải tên hiển thị hay chuỗi tùy ý. Lớp provider trong ví dụ phải public, implement service type và có constructor public không tham số. Dấu `#` bắt đầu chú thích trong tệp cấu hình; dòng trống được bỏ qua.

### 3.5. Consumer quan sát nạp lười và cache

Tệp `src/demo/App.java`:

```java
package demo;

import demo.spi.Renderer;
import java.util.Iterator;
import java.util.ServiceLoader;

public class App {
    public static void main(String[] args) {
        ServiceLoader<Renderer> loader = ServiceLoader.load(Renderer.class);
        System.out.println("after load");

        Iterator<Renderer> it = loader.iterator();
        System.out.println("after iterator");

        System.out.println("has provider: " + it.hasNext());

        Renderer first = it.next();
        System.out.println("first: " + first.name());

        Renderer again = loader.iterator().next();
        System.out.println("cached instance: " + (again == first));

        loader.reload();

        Renderer restarted = loader.iterator().next();
        System.out.println("fresh after reload: " + (restarted != first));
    }
}
```

Để chạy bằng PowerShell trên Windows, từ thư mục `service-demo`:

```powershell
javac -d out src\demo\spi\Renderer.java src\demo\providers\PlainRenderer.java src\demo\providers\HtmlRenderer.java src\demo\App.java
New-Item -ItemType Directory -Force out\META-INF\services | Out-Null
Copy-Item resources\META-INF\services\demo.spi.Renderer out\META-INF\services\
java -cp out demo.App
```

Nếu biên dịch hoặc chạy trong IDE, bảo đảm thư mục `resources` được đưa vào classpath đầu ra. Chỉ có các tệp `.class` mà thiếu `META-INF/services/demo.spi.Renderer` thì ServiceLoader sẽ không tìm thấy hai provider qua cơ chế classpath này.

**Kết quả đã kiểm tra khi biên dịch/chạy trên JDK 24**; cùng mã dùng được với Java 17+:

```text
after load
after iterator
has provider: true
[ctor] PlainRenderer
first: plain
cached instance: true
[ctor] PlainRenderer
fresh after reload: true
```

### 3.6. Đọc kết quả theo thời gian

1. `after load` xuất hiện ngay sau khi tạo loader: chưa có dòng `[ctor]`.
2. `after iterator` xuất hiện ngay sau khi lấy iterator: vẫn chưa tạo instance.
3. `has provider: true` chứng tỏ có cấu hình provider để duyệt. `hasNext()` có thể đã kiểm tra thông tin provider, nhưng constructor `PlainRenderer` chưa chạy.
4. `it.next()` lấy provider đầu tiên chưa được cache, nên in `[ctor] PlainRenderer`.
5. Một iterator mới từ **cùng loader** gặp provider đã được cache; `again == first` trả `true` và không in constructor lần nữa.
6. `reload()` xóa cache của loader. Lần `next()` sau đó tạo một đối tượng khác, vì thế constructor được in lần thứ hai và so sánh tham chiếu trả `true`.
7. **Không có `[ctor] HtmlRenderer`** vì chương trình chưa duyệt tới provider thứ hai.

Kết quả này thể hiện lợi ích chính: ứng dụng có thể khai báo nhiều provider nhưng chỉ trả chi phí khởi tạo cho provider mà nó thật sự sử dụng.

**Giới hạn của demo:** Vì đây là một tệp cấu hình classpath duy nhất, thứ tự hai dòng quyết định provider đầu tiên. Với nhiều JAR hoặc nhiều named module, thứ tự tìm provider có thể chịu ảnh hưởng của class loader, module layer và thứ tự tài nguyên; không dùng kết quả demo để khẳng định `findFirst()` luôn trả một provider “ưu tiên nhất” trong mọi môi trường.

## 4. Duyệt toàn bộ, dừng sớm và `findFirst()`

### 4.1. Duyệt bằng for-each

```java
ServiceLoader<Renderer> loader = ServiceLoader.load(Renderer.class);

for (Renderer renderer : loader) {
    if ("plain".equals(renderer.name())) {
        System.out.println("Selected " + renderer.name());
        break;
    }
}
```

**Đây là đoạn minh họa có thể đặt trong một phương thức của consumer**, cùng với các import và provider như demo trước. Vòng lặp tạo provider từng bước theo việc duyệt. Nếu provider phù hợp xuất hiện muộn, các provider trước đó đã phải được tạo để consumer gọi `name()` rồi quyết định có dùng hay không. `break` chỉ ngăn truy cập provider về sau; không “hoàn tác” những instance đã được tạo.

Khi chỉ cần một provider bất kỳ:

```java
Renderer renderer = ServiceLoader.load(Renderer.class)
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("No Renderer provider"));
```

`findFirst()` chỉ thuận tiện khi thứ tự bất kỳ chấp nhận được hoặc deployment đã kiểm soát rõ thứ tự. Nếu không có provider, nó trả `Optional.empty()`; ví dụ gọi `orElseThrow(...)` để biến trường hợp không có thành lỗi ứng dụng dễ hiểu.

### 4.2. Đừng nhầm “chỉ cần một” với “chỉ load một class”

Một provider có thể cần được **phát hiện hoặc kiểm tra kiểu** trước khi consumer biết nó có phù hợp không; việc tìm kiếm có thể làm I/O, truy cập metadata và nạp lớp. “Lazy” tập trung vào giảm công việc không cần thiết, nhất là **không tạo instance của mọi provider**, chứ không hứa rằng chỉ một class file hay một cấu hình sẽ từng được xem xét.

## 5. Lọc theo loại provider trước khi khởi tạo bằng `stream()`

Từ Java 9, `ServiceLoader.stream()` trả các đối tượng mô tả provider, có hai thao tác quan trọng:

- `provider.type()`: cho biết kiểu provider để lọc bằng class, annotation hay metadata phù hợp **mà chưa cần gọi constructor/provider factory**.
- `provider.get()`: lấy instance. Đây là điểm khởi tạo khi instance chưa được cung cấp theo cách khác.

Ví dụ **đoạn thay thế trong consumer**, dùng lại các lớp và cấu hình demo:

```java
import java.util.ServiceLoader;
import demo.spi.Renderer;

// Trong một phương thức:
Renderer html = ServiceLoader.load(Renderer.class)
        .stream()
        .filter(p -> p.type().getName()
                .equals("demo.providers.HtmlRenderer"))
        .findFirst()
        .map(ServiceLoader.Provider::get)
        .orElseThrow(() -> new IllegalStateException("No HTML renderer"));

System.out.println(html.name());
```

Ý nghĩa từng bước:

1. `stream()` cung cấp luồng descriptor; một chuỗi thao tác trung gian `filter(...)` chưa tự chạy cho đến terminal operation `findFirst()`.
2. Predicate sử dụng `p.type().getName()`. Trong demo classpath này, đó là tên lớp provider. Runtime có thể **nạp thông tin lớp**, nhưng chưa cần tạo instance chỉ để kiểm tra tên.
3. `findFirst()` dừng khi gặp descriptor khớp; chuỗi xử lý không cần xét các phần tử sau đó.
4. `map(ServiceLoader.Provider::get)` mới tạo/lấy instance của provider được chọn; constructor của provider không khớp không cần được gọi.
5. Nếu không có provider khớp, `orElseThrow(...)` giúp thể hiện lỗi thiếu extension một cách rõ ràng.

**Điểm tinh tế:** `ServiceLoader.Provider.type()` có thể trả **kiểu được trả về bởi provider factory method** đối với named module, không nhất thiết là chính lớp khai báo factory. Vì vậy, cách so tên lớp ở trên là ví dụ gắn với hai provider classpath cụ thể. Khi xây cơ chế lựa chọn mở rộng, ưu tiên contract/annotation hoặc metadata ổn định và được công bố, tránh phụ thuộc tên triển khai tùy tiện.

Các thao tác như `sorted(...)` hoặc `toList()` trên toàn bộ descriptor có thể khiến runtime **tìm/kiểm tra tất cả provider**, dù chưa gọi `get()`. Tối ưu nạp lười nên xét cả chi phí discovery và instantiation. `Provider.get()` không phải cam kết “cùng một object ở mọi lần gọi”; nếu cần giữ một instance, hãy tự quản lý rõ vòng đời đối tượng sau khi nhận được nó.

## 6. Cache của ServiceLoader và `reload()`

Một `ServiceLoader` lưu các provider đã nạp khi duyệt; ở lần gọi `iterator()` tiếp theo, những provider đã được cache được trả trước, rồi phần còn lại mới tiếp tục được phát hiện và khởi tạo theo nhu cầu.

```java
ServiceLoader<Renderer> loader = ServiceLoader.load(Renderer.class);

Renderer a = loader.iterator().next();
Renderer b = loader.iterator().next();

System.out.println(a == b); // true: provider được cache trong loader này
```

Trong ví dụ có constructor public, lần duyệt thứ hai từ **cùng loader** sử dụng instance đã cache. Tuy nhiên:

- Hai lời gọi `ServiceLoader.load(Renderer.class)` tạo **hai loader khác nhau**, không phải một cache toàn ứng dụng.
- `reload()` **xóa cache của loader hiện tại**; các lần duyệt mới có thể tìm và tạo lại provider. Các đối tượng ứng dụng đã giữ trước đó không biến mất hay tự ngừng hoạt động chỉ vì gọi `reload()`.
- **Iterator/stream đã tạo trước `reload()` phải bỏ đi**. Các iterator/stream cũ có thể ném `ConcurrentModificationException` khi tiếp tục dùng sau khi cache được xóa; tạo iterator/stream mới.
- `reload()` **không tự cài đặt plugin**, thay đổi module graph hay bảo đảm một JAR mới xuất hiện trên classpath sẽ được class loader hiện tại nhìn thấy. Nó chỉ khiến các lần tìm tiếp theo thực hiện lại trong phạm vi loader hiện có.
- Cache mô tả/provider qua `stream()` có ngữ nghĩa khác việc giữ instance bằng `iterator()`; không giả định các đường API hoặc nhiều lời gọi `Provider.get()` có cùng quy tắc chia sẻ instance nếu hợp đồng không nói vậy.

Chỉ `reload()` khi có lý do rõ ràng, chẳng hạn ứng dụng kiểm soát một môi trường provider động thực sự hỗ trợ cập nhật khả năng tìm thấy provider. Không gọi trước mỗi request: thao tác đó làm mất lợi ích của cache và có thể vô hiệu hóa iterator đang dùng.

## 7. Đăng ký provider trong ứng dụng Java hiện đại

### Trường hợp A: Classpath (ví dụ thực hành)

- Dùng `META-INF/services/demo.spi.Renderer` như phần 3.
- Provider classpath cần truy cập được từ class loader thích hợp, tương thích với service type, có constructor public không tham số.
- Khi build JAR, chắc chắn tệp `META-INF/services` thực sự nằm trong artifact. Nếu công cụ đóng gói nhiều JAR hợp nhất, phải bảo toàn các entry provider; nếu mất/ghi đè tệp cấu hình, một số provider sẽ không được phát hiện.

### Trường hợp B: Named modules (JPMS, dùng được trên Java 9+)

Ứng dụng dùng module descriptor thay vì dựa vào tệp đăng ký classpath. Ví dụ **các đoạn module-info.java minh họa cấu hình**, không phải nguyên một project có thể chạy độc lập:

```java
// module-info.java của module chứa API service
module demo.spi {
    exports demo.spi;
}
```

```java
// module-info.java của module chứa provider
module demo.providers {
    requires demo.spi;
    provides demo.spi.Renderer with demo.providers.PlainRenderer;
}
```

```java
// module-info.java của module consumer
module demo.app {
    requires demo.spi;
    uses demo.spi.Renderer;
}
```

Lệnh `uses` trong **module consumer** và `provides ... with ...` trong **module provider** là phần của hợp đồng JPMS. Provider có thể có constructor public không tham số hoặc (với named module phù hợp) dùng public static `provider()` không tham số theo hợp đồng API. Thực tế nên giữ implementation của provider được đóng gói, không yêu cầu consumer phụ thuộc trực tiếp vào module triển khai chỉ để khởi tạo nó.

Nếu hệ thống sử dụng module layer động, `ServiceLoader.load(layer, Renderer.class)` có thể tìm provider trong layer được chỉ định và các layer cha. Cần hiểu cấu trúc layer và cơ chế resolve module tương ứng; riêng `reload()` không thiết lập lại module layer.

**Lưu ý về thứ tự:** Với nhiều module trong một layer, thứ tự các provider giữa những module **không được bảo đảm**. Với classpath, thứ tự các tệp provider phụ thuộc `ClassLoader.getResources(...)`; trong một tệp, thứ tự các dòng có ý nghĩa. Vì thế không dựa vào “provider tình cờ đứng đầu” để thực thi quy tắc nghiệp vụ như mức độ ưu tiên, độ an toàn hay khả năng tương thích.

## 8. Xử lý lỗi đúng thời điểm

`ServiceConfigurationError` có thể phát sinh **khi đang duyệt**, chứ không nhất thiết ngay tại `load(...)`. Những nguyên nhân phổ biến gồm:

- Tệp `META-INF/services/<service>` thiếu, sai tên, sai UTF-8 hoặc sai cú pháp. Nếu **không có đăng ký hợp lệ**, `ServiceLoader` thường chỉ thấy không có provider; nhưng cấu hình **tồn tại mà bị lỗi** có thể tạo `ServiceConfigurationError`.
- Tên lớp provider trong cấu hình không tồn tại, không truy cập được qua class loader, không implement đúng service type, hoặc thiếu constructor public không tham số đối với provider classpath.
- Constructor/provider factory ném ngoại lệ, hoặc một factory method trong named module trả `null` hay vi phạm hợp đồng.
- Consumer modular thiếu `uses` hoặc không cấu hình module dependency cần thiết để nhìn thấy service type/provider.

Khi duyệt, nếu muốn báo lỗi với ngữ cảnh:

```java
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;
import demo.spi.Renderer;

// Trong một phương thức:
try {
    for (Renderer renderer : ServiceLoader.load(Renderer.class)) {
        System.out.println(renderer.name());
    }
} catch (ServiceConfigurationError error) {
    throw new IllegalStateException(
            "Cannot load Renderer providers; check SPI configuration", error);
}
```

Bắt lỗi ở **lời gọi duyệt/terminal operation** quan trọng vì `hasNext()`, `next()` hoặc xử lý `stream()` có thể mới làm công việc tìm và khởi tạo. Việc tiếp tục thử duyệt sau lỗi chỉ được Java xử lý best effort, không có bảo đảm phục hồi sạch; không âm thầm bỏ qua lỗi cấu hình quan trọng.

Trường hợp **không tìm thấy provider** thì tách biệt với **provider khai báo sai hoặc lỗi khởi tạo**. Với ứng dụng có fallback hợp lệ, có thể dùng `findFirst().orElse(defaultRenderer)`; đừng coi mọi `ServiceConfigurationError` là “không có plugin”.

## 9. Các hiểu lầm và lỗi thiết kế thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`load(...)` sẽ tạo hết các implementation.” | Nó tạo loader; discovery/instantiation diễn ra khi thực sự duyệt. |
| “`hasNext()` không làm việc gì đáng kể.” | Nó có thể tìm tài nguyên, đọc cấu hình, nạp metadata và ném lỗi. |
| “Dùng `for-each` nghĩa là luôn lazy nên không tốn nhiều tài nguyên.” | Nếu duyệt hết, tất cả provider gặp trong lần duyệt có thể được khởi tạo. Dừng sớm hoặc lọc descriptor khi phù hợp. |
| “`findFirst()` luôn chọn implementation tốt nhất.” | Không có chính sách ưu tiên tổng quát. Thứ tự tìm được phụ thuộc cách triển khai/đăng ký và môi trường. |
| “`stream().filter(p -> ...)` chắc chắn đã tạo provider để kiểm tra.” | Nếu chỉ dùng `p.type()` và metadata, thường chỉ cần thông tin kiểu; gọi `p.get()` mới cần instance. |
| “Mỗi lần gọi `iterator()` là lại tạo mọi provider từ đầu.” | Loader có cache; iterator mới phát lại provider đã cache rồi mới tìm phần còn lại. |
| “`reload()` dỡ class và thay nóng mọi plugin.” | Nó xóa cache; không tự thay class loader, module graph hay các object đã phát cho ứng dụng. |
| “Có thể dùng một `ServiceLoader` chung từ nhiều luồng mà không phối hợp.” | **ServiceLoader không thread-safe**. Quản lý quyền sở hữu, truy cập tuần tự/đồng bộ hoặc tạo loader phù hợp cho từng ngữ cảnh. |

Một lưu ý quan trọng khi tối ưu hiệu năng: **lazy discovery** không đồng nghĩa **lazy business initialization**. Nếu constructor của provider tự mở kết nối mạng, khởi tạo hệ thống nặng hoặc đọc toàn bộ dữ liệu, chi phí đó sẽ đến tại `next()`/`Provider.get()`. Với tài nguyên cực đắt, nên thiết kế service type là **factory nhỏ gọn** rồi để factory tạo tài nguyên nghiệp vụ theo nhu cầu thực tế.

## 10. Checklist áp dụng trong dự án

1. **Xác nhận điểm mở rộng**: service interface rõ ràng, consumer chỉ biết contract, implementation do module/JAR provider cung cấp.
2. **Đăng ký đúng hình thức đóng gói**: classpath → `META-INF/services`; named module → `provides`, consumer → `uses`.
3. **Chỉ duyệt đến khi cần**: chọn `findFirst()` khi chấp nhận provider đầu; dùng `stream()` và `Provider.type()` khi cần lọc mà chưa tạo instance.
4. **Không xem `hasNext()` là không có tác dụng phụ**: đây có thể là điểm phát sinh I/O hoặc lỗi cấu hình.
5. **Nhận biết cache**: giữ `ServiceLoader` phù hợp khi muốn tái sử dụng; không `reload()` tùy tiện; không dùng iterator/stream cũ sau reload.
6. **Chủ động xử lý thiếu provider và lỗi cấu hình**: `Optional.empty()` khác với `ServiceConfigurationError`.
7. **Không phụ thuộc thứ tự ngoài hợp đồng**: nếu muốn chọn theo priority/khả năng, công bố tiêu chí rõ ràng thay vì chỉ gọi `findFirst()`.
8. **Tôn trọng class loader và đồng thời**: `load(service)` dùng thread context class loader; không dùng chung loader thiếu đồng bộ; không cache một loader toàn JVM cho nhiều ứng dụng có TCCL khác nhau.
9. **Đo hiệu năng bằng công việc thật**: thời gian discovery, số constructor được gọi, chi phí plugin được kích hoạt; không suy luận từ tên API.

## 11. Tự kiểm tra

**Câu 1.** Có 10 provider đăng ký. Sau `ServiceLoader.load(MyService.class)`, có chắc 10 constructor đã chạy không?

**Đáp:** Không. `load` trả loader; quá trình duyệt mới làm các bước discovery/instantiation. Nếu duyệt đủ 10 provider, việc khởi tạo mới có thể diễn ra lần lượt.

**Câu 2.** Chương trình gọi `iterator().hasNext()` rồi không gọi `next()`. Có thể khẳng định không có I/O hoặc không đọc tệp cấu hình không?

**Đáp:** Không. `hasNext()` có thể tìm/đọc cấu hình và nạp thông tin provider; không có nghĩa instance provider đã được tạo.

**Câu 3.** Hai lần `loader.iterator().next()` có luôn trả cùng object không?

**Đáp:** Nếu cùng loader, cùng provider đầu tiên và chưa gọi `reload()`, iterator trả lại instance đã được cache như demo. Không áp dụng kết luận đó cho **hai loader khác nhau** hoặc mọi lời gọi `Provider.get()` qua `stream()`.

**Câu 4.** Muốn ưu tiên provider có annotation `@Preferred` mà không khởi tạo các provider không được chọn, nên dùng API nào?

**Đáp:** Dùng `loader.stream()`, lọc descriptor qua `Provider.type()` và annotation, rồi gọi `Provider.get()` cho provider đã chọn. Cần nhớ việc xem metadata vẫn có chi phí nạp/kiểm tra lớp.

**Câu 5.** Sau `loader.reload()`, có nên tiếp tục dùng iterator đã tạo trước đó?

**Đáp:** Không. Tạo iterator/stream mới; dùng lại bản cũ có thể ném `ConcurrentModificationException`.

## Tài liệu đối chiếu hiện hành

- [Oracle Java SE 26 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): contract, thời điểm discovery, cache, iterator, stream, reload, module/classpath.
- [Oracle Java SE 26 — `ServiceLoader.Provider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()` và `get()`.
- [Oracle Java SE 26 — `ServiceConfigurationError`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceConfigurationError.html): nhóm lỗi cấu hình provider.

**Ghi nhớ:** `ServiceLoader` cho phép **tìm và khởi tạo provider theo nhu cầu khi duyệt**. Chọn `iterator()/findFirst()` khi cần instance trực tiếp; chọn `stream()` để lọc thông tin provider trước `get()`; hiểu cache và `reload()`; và đừng nhầm nạp lười với việc bảo đảm không có discovery, I/O hay lỗi ở `hasNext()`.
