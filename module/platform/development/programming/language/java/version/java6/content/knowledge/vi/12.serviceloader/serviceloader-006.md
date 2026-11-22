# Bộ nhớ đệm và ServiceLoader.reload() trong Java

## 1. Mục tiêu và tình huống thực tế

`java.util.ServiceLoader<S>` là cơ chế khám phá và sử dụng các **service provider** theo chuẩn Java SPI (Service Provider Interface). Ứng dụng chỉ cần biết interface/dạng dịch vụ `S`, còn các triển khai có thể được công bố qua `META-INF/services` trên classpath hoặc khai báo `provides ... with ...` trong module Java.

`ServiceLoader` có **bộ nhớ đệm (cache) theo từng đối tượng loader**, giúp lần duyệt sau sử dụng lại những provider đã được tìm thấy, và đối với `iterator()`, sử dụng lại các **instance** đã khởi tạo. Khi hệ thống có thể bổ sung provider trong lúc chạy, `reload()` xóa các cache này để các lần duyệt tiếp theo khám phá lại provider theo cơ chế lazy.

Một câu hỏi quan trọng trong ứng dụng plugin là: “Sau khi đăng ký plugin mới hoặc thay cấu hình, vì sao `ServiceLoader` vẫn trả provider cũ?” Trả lời đúng cần phân biệt **cache của ServiceLoader**, **khả năng nhìn thấy class/resource của ClassLoader hoặc ModuleLayer**, và **các instance ứng dụng đã giữ lại**. `reload()` chỉ giải quyết lớp thứ nhất.

Sau bài này, bạn có thể:

- Giải thích cache và quá trình khám phá/khởi tạo lười (`lazy discovery/instantiation`).
- Biết chính xác `reload()` xóa gì, làm mới khi nào và không tự động làm gì.
- Nhận biết `Iterator`/`Stream` cũ không còn hợp lệ sau `reload()`.
- Viết chương trình Java 17+ kiểm chứng reuse instance, reload và vòng đời của provider.
- Thiết kế thao tác refresh an toàn cho registry ứng dụng, xử lý lỗi cấu hình, class loader và truy cập đồng thời.

> Phạm vi: những đặc tính API đang được duy trì trong Java hiện đại. Ví dụ dùng Java 17+ để chạy; `ServiceLoader` có từ Java 6, còn `stream()`, `findFirst()` và kiểu `Provider<S>` xuất hiện ở Java 9.

## 2. ServiceLoader chứa cache gì?

Giả sử `Greeting` là interface dịch vụ và `HelloGreeting` là một provider được đăng ký hợp lệ.

```java
ServiceLoader<Greeting> loader = ServiceLoader.load(Greeting.class);
```

Việc tạo `loader` **không đồng nghĩa với khởi tạo ngay mọi provider**. Việc tìm, tải và khởi tạo diễn ra khi ứng dụng duyệt loader hoặc xử lý stream.

### 2.1. Duyệt qua `iterator()`

`loader.iterator()` trả iterator của các đối tượng `Greeting`. Theo Javadoc:

1. Iterator trả trước các **instance provider đã có trong cache** của chính `ServiceLoader` này, theo thứ tự được khởi tạo trước đó.
2. Khi đi hết phần đã cache, iterator tiếp tục **tìm và khởi tạo** provider chưa được tải, từng cái một khi cần.
3. Provider mới được khởi tạo qua iterator sẽ được thêm vào cache để lần duyệt sau có thể sử dụng lại.

Vì vậy, nếu một loader đã tìm ra provider đầu tiên, `loader.findFirst()` gọi lần nữa sẽ lấy provider đã cache. `findFirst()` là phương thức tiện ích dựa trên iterator, không yêu cầu quét toàn bộ provider.

```java
Greeting a = loader.findFirst().orElseThrow();
Greeting b = loader.findFirst().orElseThrow();
// Với một provider tạo bằng constructor thông thường:
// a == b: true trước khi cache bị xóa.
```

**Cache thuộc về instance `loader`**, không phải một registry toàn cục. Hai lần gọi `ServiceLoader.load(Greeting.class)` tạo các đối tượng loader riêng và có trạng thái cache riêng; không nên xem việc reload loader A là lệnh làm mới loader B.

### 2.2. Duyệt qua `stream()` (Java 9+)

`loader.stream()` trả `Stream<ServiceLoader.Provider<Greeting>>`. Mỗi `Provider<S>` là một descriptor có `type()` và `get()`:

```java
long providerTypes = loader.stream().count();
```

Dòng này có thể tìm provider để đếm **mà không khởi tạo đối tượng dịch vụ**. Khi cần instance, gọi `Provider.get()`:

```java
List<Greeting> instances = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
```

`stream()` có cơ chế cache các provider đã tìm thấy trong những thao tác stream trước đó. Nó **không giống** cache instance dùng bởi `iterator()`; đừng giả định `Provider.get()` luôn trả cùng object như `iterator()`, hay cứ gọi `get()` nhiều lần sẽ cùng một instance. Với provider thông thường, mỗi lần `get()` có thể khởi tạo instance; provider trong module cũng có thể được cung cấp bởi phương thức factory `provider()`, và factory có quyền quyết định instance được trả về.

**Khi test cache, hãy xác định đang kiểm tra `iterator()` hay `stream()`.** Kiểm tra số lần gọi constructor thông qua `iterator()` là cách rõ ràng; nếu cần xác nhận discovery không khởi tạo, dùng `stream().count()` với provider tự kiểm soát.

### 2.3. Mốc thời gian cache

| Thời điểm | Trạng thái liên quan |
| --- | --- |
| `ServiceLoader.load(...)` | Tạo một đối tượng loader; provider chưa bắt buộc được tìm/khởi tạo. |
| `iterator().next()` hoặc `findFirst()` | Tìm/khởi tạo provider khi cần; instance được thêm vào cache iterator. |
| Duyệt `iterator()` lần nữa | Các instance đã cache được trả lại trước khi tìm phần còn lại. |
| `stream()` | Trả stream lazy gồm descriptor; việc xử lý stream tìm provider; `get()` mới lấy instance. |
| `loader.reload()` | Xóa các cache của loader này; **không khởi tạo lại ngay**. |
| `loader.iterator()` hoặc `loader.stream()` mới sau reload | Bắt đầu tìm lại provider một cách lazy. |

Một loader có thể mới tải một phần provider. Nếu vòng lặp dừng ở phần tử đầu tiên, không nên kết luận nó đã khởi tạo hết những provider còn lại.

## 3. Chính xác `ServiceLoader.reload()` làm gì?

```java
loader.reload();
```

Theo hợp đồng Java SE hiện hành, `reload()` **xóa cache provider của đúng đối tượng `loader`**. Những lời gọi `iterator()` hoặc `stream()` **sau đó** sẽ thực hiện lại việc định vị provider theo cơ chế lazy, giống trạng thái khởi đầu của một loader mới. Nếu đi qua iterator, provider sẽ được khởi tạo lại khi cần.

Với provider khởi tạo qua constructor và không tự giữ singleton, thường quan sát được:

```text
load -> findFirst -> instance #1
     -> findFirst -> vẫn instance #1 (cache)
reload()         -> cache bị xóa
     -> findFirst -> instance #2
```

`reload()` **không** có các tác dụng sau:

- **Không tự gọi constructor ngay** khi gọi `reload()`; việc khởi tạo diễn ra ở lượt đọc tiếp theo.
- **Không hủy, đóng hoặc cập nhật các object đã trả về**. Nếu ứng dụng giữ `Greeting old`, `old` vẫn là tham chiếu đến object cũ và vẫn có thể được sử dụng theo hợp đồng riêng của provider.
- **Không cập nhật các collection/snapshot mà ứng dụng đã tự lưu**; ví dụ một `List<Greeting>` được thu thập trước reload không tự đổi.
- **Không tự reload bytecode hoặc thay thế `ClassLoader`/`ModuleLayer`**. Provider mới chỉ được tìm thấy nếu ngữ cảnh tải lớp/tài nguyên thực sự có thể nhìn thấy nó.
- **Không làm mới mọi `ServiceLoader` trong JVM**, không phải thao tác làm sạch cache toàn hệ thống.
- **Không giải quyết thay đổi luồng an toàn**: gọi `reload()` đồng thời với duyệt trên cùng một `ServiceLoader` là không an toàn.

Khi dùng một provider có factory method có thể trả singleton, **không lấy `old != refreshed` làm bảo đảm chung của API**. Hợp đồng đảm bảo cache được xóa và discovery được thực hiện lại khi cần; identity cuối cùng còn phụ thuộc cách provider tạo object. Ví dụ tự xây dựng bên dưới cố ý dùng constructor mỗi lần tạo mới, nên assertion identity sẽ có ý nghĩa trong phạm vi ví dụ.

## 4. Vòng đời iterator và stream khi gọi reload

### 4.1. Iterator lấy *trước* reload phải bỏ

`reload()` làm mất hiệu lực của các iterator đã lấy từ loader đó. Javadoc nêu rằng gọi `hasNext()` hoặc `next()` trên iterator cũ sau khi xóa cache sẽ ném `ConcurrentModificationException`.

```java
Iterator<Greeting> oldIterator = loader.iterator();
loader.reload();

// Không tiếp tục dùng oldIterator.
Iterator<Greeting> freshIterator = loader.iterator();
while (freshIterator.hasNext()) {
    Greeting provider = freshIterator.next();
    // Dùng provider đã tải từ vòng duyệt mới.
}
```

Đây là **invalidation** của iterator do cache thay đổi; có thể xảy ra ngay trong **một luồng**, không chứng minh có hai luồng đang tranh chấp. Trên code thực tế, nên hoàn tất một lượt duyệt rồi mới reload, thay vì chủ ý dựa vào ngoại lệ để điều phối vòng đời.

### 4.2. Stream lấy *trước* reload cũng phải bỏ

Nguồn `Spliterator` của `loader.stream()` là fail-fast khi cache của loader đã bị xóa; quá trình xử lý stream cũ sau reload có thể phát sinh `ConcurrentModificationException`. Cách dùng đúng là tạo **stream mới** sau reload:

```java
loader.reload();

List<Class<? extends Greeting>> types = loader.stream()
        .map(ServiceLoader.Provider::type)
        .toList();
```

`Stream` thông thường vốn là luồng xử lý một lần; không tích trữ stream để dùng lâu dài. Cần giữ danh sách descriptor hoặc instance trong ứng dụng thì lấy snapshot với thiết kế refresh riêng. Đừng lưu iterator/stream như một phần tử của registry để dùng xuyên qua nhiều lần `reload()`.

### 4.3. Tham chiếu instance cũ không bị vô hiệu

`Iterator` và `Stream` cũ bị invalid **không có nghĩa object provider cũ bị phá hủy**. Nếu một lời gọi đang giữ provider trước reload, nó vẫn có thể gọi các phương thức của provider đó. Khả năng dùng tiếp có an toàn hay không còn phụ thuộc tài nguyên và hợp đồng nghiệp vụ của provider, hoàn toàn tách biệt với cache của `ServiceLoader`.

Ví dụ một provider giữ kết nối mạng hoặc file handle: `ServiceLoader.reload()` không tự gọi `close()`. Ứng dụng phải định nghĩa quá trình ngừng nhận tác vụ, chờ các tác vụ đang chạy, đóng tài nguyên và thay registry khi cần.

## 5. Demo Java 17+ chạy thật: cache, reload và iterator

Ví dụ này gồm service interface, một provider công bố bằng file `META-INF/services` và chương trình main. Provider dùng bộ đếm để minh họa lần khởi tạo; chỉ có một provider trong demo nên không có phụ thuộc vào thứ tự duyệt nhiều provider.

### 5.1. Cấu trúc tệp

```text
service-loader-demo/
├── src/
│   └── demo/
│       ├── spi/
│       │   └── Greeting.java
│       ├── impl/
│       │   └── HelloGreeting.java
│       └── Main.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.spi.Greeting
```

Tên của file cấu hình bằng **tên đầy đủ của service interface**; nội dung là **tên đầy đủ của provider class**. Thư mục `resources` cần nằm trên runtime classpath. Đây là quy ước SPI classpath vẫn được hỗ trợ trong Java hiện hành.

**Tệp `src/demo/spi/Greeting.java`:**

```java
package demo.spi;

public interface Greeting {
    String hello();
}
```

**Tệp `src/demo/impl/HelloGreeting.java`:**

```java
package demo.impl;

import demo.spi.Greeting;

public final class HelloGreeting implements Greeting {
    private static int created;
    private final int id;

    public HelloGreeting() {
        id = ++created;
    }

    @Override
    public String hello() {
        return "hello#" + id;
    }

    public static int createdCount() {
        return created;
    }
}
```

Đây là provider public có constructor public không đối số, phù hợp cách nạp qua `META-INF/services`. Biến đếm static chỉ dùng minh họa **một luồng** trong chương trình; không phải kỹ thuật đếm instance an toàn cho ứng dụng đa luồng.

**Tệp `resources/META-INF/services/demo.spi.Greeting`**, nội dung chính xác một dòng:

```text
demo.impl.HelloGreeting
```

**Tệp `src/demo/Main.java`:**

```java
package demo;

import demo.spi.Greeting;
import demo.impl.HelloGreeting;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeting> loader =
                ServiceLoader.load(Greeting.class);

        // findFirst() dùng iterator và cache instance của loader.
        Greeting first = loader.findFirst().orElseThrow();
        Greeting again = loader.findFirst().orElseThrow();
        System.out.println("cached same instance: " + (first == again));

        // Lấy iterator rồi xóa cache: iterator này không còn hợp lệ.
        Iterator<Greeting> oldIterator = loader.iterator();
        loader.reload();

        // Provider được tìm và khởi tạo khi truy cập lại, không phải
        // ngay tại thời điểm gọi reload().
        Greeting afterReload = loader.findFirst().orElseThrow();
        System.out.println(
                "new instance after reload: " + (first != afterReload));

        // reload không hủy những object đã trả về trước đó.
        System.out.println("old instance: " + first.hello());
        System.out.println("new instance: " + afterReload.hello());

        try {
            oldIterator.hasNext();
            System.out.println("old iterator: unexpectedly valid");
        } catch (ConcurrentModificationException expected) {
            System.out.println("old iterator: invalidated");
        }

        // stream() khám phá loại provider; count không gọi Provider.get().
        long discovered = loader.stream().count();
        System.out.println("provider types: " + discovered);
        System.out.println(
                "constructed instances: " + HelloGreeting.createdCount());
    }
}
```

### 5.2. Biên dịch và chạy

Tạo thư mục `out` để nhận file `.class`. Chạy các lệnh ở thư mục gốc `service-loader-demo`.

**Linux/macOS (shell):**

```bash
mkdir -p out
javac -encoding UTF-8 -d out \
  src/demo/spi/Greeting.java \
  src/demo/impl/HelloGreeting.java \
  src/demo/Main.java
java -cp "out:resources" demo.Main
```

**Windows (PowerShell):**

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/demo/spi/Greeting.java src/demo/impl/HelloGreeting.java src/demo/Main.java
java -cp "out;resources" demo.Main
```

Dấu phân cách classpath là `:` trên Linux/macOS, `;` trên Windows. Hai thư mục `out` và `resources` cùng phải được đưa vào classpath để JVM tìm cả class lẫn file cấu hình SPI.

**Stdout chính xác khi chạy demo với một provider như trên:**

```text
cached same instance: true
new instance after reload: true
old instance: hello#1
new instance: hello#2
old iterator: invalidated
provider types: 1
constructed instances: 2
```

Diễn giải kết quả:

1. `cached same instance: true`: hai lượt `findFirst()` trên cùng loader trả về đúng instance đã cache.
2. `new instance after reload: true`: trong **provider demo dùng constructor**, sau reload và truy cập tiếp, JVM tạo object thứ hai.
3. `old instance: hello#1`: tham chiếu `first` vẫn dùng được; reload không hủy instance cũ.
4. `old iterator: invalidated`: iterator lấy trước reload phải bỏ đi.
5. `provider types: 1` và `constructed instances: 2`: lần đếm bằng `stream()` tìm metadata provider nhưng không gọi `Provider.get()`, vì vậy không tạo instance thứ ba.

**Lưu ý:** Kết quả `first != afterReload` là một đặc điểm có thể kiểm soát của `HelloGreeting` cụ thể. Với provider do factory method tạo hoặc quản lý singleton, không khẳng định mọi provider đều phải có identity mới sau reload.

## 6. Khi nào reload có thể phát hiện provider mới?

Hợp đồng `reload()` cho phép **khám phá lại** provider, nhưng có phát hiện được thay đổi thực tế không còn phụ thuộc **nguồn công bố** và **ngữ cảnh nạp class**:

| Tình huống | Kết quả nên kỳ vọng |
| --- | --- |
| Loader đang cache instance và file/class SPI vốn đã nhìn thấy | Lượt duyệt mới tìm lại provider; đối với constructor demo, sẽ tạo instance mới. |
| Thêm provider vào vị trí classpath mà loader hiện tại **không nhìn thấy** | `reload()` không tự sửa classpath hoặc class loader nên không bảo đảm provider mới xuất hiện. |
| Dùng class loader/plugin manager hỗ trợ lắp thêm class và resource khi chạy | Sau khi nguồn provider mới thực sự nhìn thấy được, `reload()` có thể giúp phát hiện lại; phải kiểm tra cơ chế loader thực tế. |
| Thay nội dung `.class` bên dưới một class đã được JVM tải | `reload()` không thay bytecode của class đã tải; không phải cơ chế hot swap. |
| Thay `ModuleLayer` hoặc cấu hình module | Một loader đang gắn với ngữ cảnh module cũ không tự chuyển sang layer khác; tạo loader phù hợp ngữ cảnh mới khi cần. |
| Có hai `ServiceLoader` cùng kiểu service | `reload()` chỉ xóa cache của đúng đối tượng được gọi; loader còn lại giữ cache riêng. |

### ClassLoader và module là ranh giới quan trọng

`ServiceLoader.load(Greeting.class)` dùng **thread context class loader** của luồng gọi tại thời điểm tạo loader. Nếu hệ thống plugin có class loader riêng, có thể chỉ định rõ:

```java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(Greeting.class, pluginClassLoader);
```

Đoạn trên là ví dụ API, giả định ứng dụng đã tạo `pluginClassLoader` thích hợp. Đổi context class loader sau khi tạo `loader` không tự chuyển ngữ cảnh khám phá của đối tượng đó. Nếu cần lớp/tài nguyên mới hoặc class loader khác, có thể phải tạo **ServiceLoader mới** gắn với class loader mới.

Với **named modules** (JPMS), module sử dụng service khai báo `uses demo.spi.Greeting;`, còn module chứa provider khai báo `provides demo.spi.Greeting with demo.impl.HelloGreeting;`. Có overload `ServiceLoader.load(ModuleLayer, Class)` để khám phá provider từ layer chỉ định và các parent layer. `reload()` vẫn chỉ là thao tác làm sạch cache của loader hiện tại; không tự tạo hay cập nhật module layer.

Một cấu hình SPI sai (sai tên class, provider không triển khai service, thiếu constructor/provider method hợp lệ, file cấu hình sai định dạng, resource bị chặn) có thể gây `ServiceConfigurationError` khi duyệt; chỉ gọi `reload()` lặp đi lặp lại không sửa được cấu hình hỏng.

## 7. Thiết kế refresh registry trong ứng dụng

Nhiều ứng dụng không duyệt `ServiceLoader` trực tiếp mỗi lần xử lý request; thay vào đó, chúng xây một registry sử dụng chung. Khi đó phải phân biệt **cache bên trong ServiceLoader** và **snapshot của registry**.

Ví dụ sau là **đoạn minh họa**, chưa phải chương trình chạy độc lập vì ứng dụng phải định nghĩa interface `Plugin`. Nó dùng một loader được giữ nội bộ, một list công bố cho reader và một phương thức `refresh()` độc quyền. Đây là ý tưởng cho hệ thống chỉ có một nơi làm refresh; không phải giải pháp điều phối lifecycle cho mọi loại plugin.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;

final class PluginRegistry {
    private final ServiceLoader<Plugin> loader =
            ServiceLoader.load(Plugin.class);
    private volatile List<Plugin> active = List.of();

    // Không để code ngoài lớp truy cập trực tiếp loader.
    synchronized void refresh() {
        loader.reload();

        List<Plugin> next = new ArrayList<>();
        for (Plugin plugin : loader) {
            next.add(plugin);
        }

        // Công bố một snapshot cấu trúc sau khi duyệt thành công.
        active = List.copyOf(next);
    }

    List<Plugin> snapshot() {
        return active;
    }
}
```

Ý nghĩa:

- `refresh()` xóa cache trước rồi nạp danh sách provider mới, sau đó mới công bố danh sách để reader lấy.
- Nếu phát sinh lỗi trong lúc nạp, phép gán `active = ...` chưa diễn ra; bản snapshot trước vẫn còn. Tuy nhiên bộ đệm `loader` có thể đã ở trạng thái được tải một phần, nên lần refresh tiếp theo cần chủ động làm mới.
- `volatile` giúp những luồng khác thấy tham chiếu list mới khi được công bố. Nó **không làm các instance `Plugin` bên trong tự an toàn đa luồng**, không đóng plugin cũ và không giải quyết vấn đề request đang dùng phiên bản cũ.
- `synchronized` ngăn hai lượt `refresh()` đồng thời trên cùng registry, nhưng lớp này còn giả định **không có chỗ nào khác** đồng thời truy cập `loader`. `ServiceLoader` tự thân không thread-safe.
- `List.copyOf(next)` chỉ làm list không sửa được và sao chép **cấu trúc**; object provider vẫn có thể mutable. Nếu cần loại bỏ provider cũ, ứng dụng phải thiết kế cơ chế quản lý tài nguyên/lifecycle riêng.

Một lỗi phổ biến là chỉ viết:

```java
loader.reload();
// Danh sách List<Plugin> đã lưu trước đây vẫn chứa các instance cũ!
```

Để refresh thực sự có hiệu lực đối với người dùng registry, phải **lấy lại provider và cập nhật điểm tham chiếu/snapshot mà ứng dụng sử dụng**. Với hệ thống cần chuyển phiên bản không gián đoạn, cần thêm phối hợp với các request đang dùng provider cũ và chính sách đóng tài nguyên sau khi không còn ai dùng.

## 8. Kiểm thử cache và reload đúng hợp đồng

Có thể chuyển demo thành test JUnit Jupiter. Ví dụ dưới đây **dùng đúng fixture `Greeting`/`HelloGreeting` đã tạo ở phần 5**, và giả định test classpath chứa `resources/META-INF/services` cùng các class đã biên dịch. Đoạn JUnit này không phải chương trình standalone; dự án cần có JUnit Jupiter.

```java
import demo.spi.Greeting;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.ServiceLoader;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ServiceLoaderReloadTest {
    @Test
    void iteratorCacheReusesInstanceUntilReload() {
        ServiceLoader<Greeting> loader =
                ServiceLoader.load(Greeting.class);

        Greeting first = loader.findFirst().orElseThrow();
        Greeting cached = loader.findFirst().orElseThrow();
        assertSame(first, cached);

        loader.reload();

        Greeting refreshed = loader.findFirst().orElseThrow();
        // Chỉ áp dụng vì fixture có public constructor tạo mới.
        assertNotSame(first, refreshed);
        assertTrue(first.hello().startsWith("hello#"));
        assertTrue(refreshed.hello().startsWith("hello#"));
    }

    @Test
    void iteratorCreatedBeforeReloadIsInvalid() {
        ServiceLoader<Greeting> loader =
                ServiceLoader.load(Greeting.class);
        Iterator<Greeting> oldIterator = loader.iterator();

        loader.reload();

        assertThrows(ConcurrentModificationException.class,
                oldIterator::hasNext);

        // Tạo iterator mới là cách sử dụng lại sau reload.
        assertTrue(loader.iterator().hasNext());
    }

    @Test
    void streamCanInspectProviderType() {
        ServiceLoader<Greeting> loader =
                ServiceLoader.load(Greeting.class);

        long count = loader.stream()
                .filter(provider -> provider.type().getName()
                        .equals("demo.impl.HelloGreeting"))
                .count();

        assertEquals(1L, count);
    }
}
```

Chỉ sử dụng `assertNotSame` khi bạn **kiểm soát** cách provider được khởi tạo như fixture này. Với plugin thật, nếu provider dùng `provider()` trả về singleton, test nên tập trung vào việc cache được invalid và discovery được thực hiện lại, không ép identity mới.

Có thể lập bảng kiểm thử ngắn:

| Trường hợp | Điều kiện kiểm tra |
| --- | --- |
| Cache instance trước reload | Lặp `findFirst()` trên cùng loader với provider kiểm soát constructor; nhận cùng object. |
| Cache sau reload | Gọi `reload()`; lần `findFirst()` kế tiếp khởi tạo provider khi cần. |
| Iterator cũ | Sau reload, `hasNext()`/`next()` của iterator cũ không còn hợp lệ, có `ConcurrentModificationException`. |
| Stream cũ | Không dùng stream đã tạo trước reload; tạo stream mới trước lượt khám phá mới. |
| Tham chiếu cũ | Provider đã được ứng dụng giữ không tự bị đóng hoặc tự thay thế. |
| Nhiều loader | Mỗi instance có cache độc lập; không giả định reload một loader làm đổi loader khác. |
| Provider mới | Test với class loader hoặc module layer thực sự nhìn thấy provider mới; chỉ reload không đủ nếu class không nhìn thấy. |
| Cấu hình hỏng | Duyệt có thể gây `ServiceConfigurationError`; log nguyên nhân và xử lý tại ranh giới plugin. |

## 9. Lỗi thường gặp và cách tránh

**Nhầm lazy với eager.** `ServiceLoader.load(...)` không tải hết provider ngay. Nếu cần lấy đầy đủ để kiểm tra cấu hình ở startup, hãy duyệt hết hoặc xử lý stream có terminal operation. Việc duyệt có thể làm chậm startup hoặc kích hoạt constructor/provider factory, nên quyết định rõ lúc nào được thực hiện.

**Gọi `reload()` trong khi đang duyệt.** Iterator/stream đã tạo trước reload phải bị loại bỏ. Tổ chức refresh thành một pha riêng, kết thúc lượt duyệt hiện tại trước khi làm sạch cache.

**Tin rằng reload làm mọi reference thành instance mới.** Object cũ ứng dụng giữ vẫn là object cũ; danh sách đã xây cũng không tự đổi. Registry phải cập nhật snapshot và quản lý vòng đời nếu cần.

**Cho rằng reload tự cài JAR/plugin mới.** Nếu class loader và module layer hiện tại không nhìn thấy code/resource mới, rediscovery không có gì mới để khám phá. Xác định đúng ngữ cảnh nạp class, nguồn `META-INF/services`, `uses/provides` và cơ chế cập nhật plugin trước khi kết luận `reload()` bị lỗi.

**Cho rằng `stream()` và `iterator()` có cùng semantics instance.** `stream()` xuất descriptor; `Provider.get()` mới lấy instance. Tránh test identity xuyên hai API hoặc giả định gọi `get()` lặp lại luôn reuse cùng object.

**Lấy thứ tự provider làm hợp đồng toàn cục.** Java xác định một số quy tắc thứ tự trong từng nguồn nhưng không cam kết thứ tự mọi module trong cùng layer. Khi lựa chọn provider quan trọng, dùng tiêu chí rõ ràng (định danh, capability, priority do ứng dụng định nghĩa), không mặc định “provider đầu tiên” luôn là đúng trong hệ thống nhiều plugin.

**Bỏ qua tính an toàn luồng.** `ServiceLoader` không an toàn khi dùng đồng thời từ nhiều luồng. Khóa quyền truy cập để discovery/reload được tuần tự hoặc sử dụng registry snapshot bất biến về cấu trúc mà không cho reader chạm loader. Đồng bộ riêng việc truy cập provider nếu bản thân provider không thread-safe.

**Nuốt `ServiceConfigurationError` như trường hợp không tìm thấy.** Khi provider cấu hình sai, lỗi có thể xuất hiện trong `hasNext()`, `next()` hoặc khi xử lý stream. `findFirst()` không tìm thấy provider hợp lệ trả `Optional.empty()`; nó không có nghĩa các lỗi cấu hình sẽ bị chuyển thành `empty`. Nếu plugin là tùy chọn, xử lý lỗi ở ranh giới hệ thống với log rõ nguyên nhân; việc thử tiếp provider khác chỉ là best effort theo tài liệu API, không được bảo đảm phục hồi hoàn toàn.

**Giữ ServiceLoader toàn cục sai phạm vi.** `ServiceLoader.load(service)` dựa vào thread context class loader. Trong môi trường chứa nhiều ứng dụng/plugin với các class loader khác nhau, cache loader ở phạm vi JVM có thể tạo lỗi nhìn thấy provider và giữ class loader lâu hơn cần thiết. Nên quản lý cache theo scope ứng dụng/plugin và vòng đời class loader thích hợp.

## 10. Câu hỏi tự kiểm tra

1. Gọi `reload()` rồi không đụng `iterator()` hay `stream()`, provider mới có ngay được khởi tạo không? **Không.** Rediscovery và instantiation là lazy.
2. Gọi `findFirst()` hai lần với cùng loader, cache chưa bị xóa, có thể dùng lại instance không? **Có.** Cache iterator lưu instance đã khởi tạo và trả trước ở lần duyệt tiếp theo.
3. Gọi `reload()` có phá object `first` đã trả về trước đó không? **Không.** Ứng dụng còn giữ tham chiếu và tự quản lý lifecycle.
4. Gọi `hasNext()` của iterator cũ sau reload thì sao? **`ConcurrentModificationException`** theo hợp đồng API; nên bỏ iterator cũ.
5. Gọi `reload()` trên loader A có tự xóa cache của loader B không? **Không.** Mỗi `ServiceLoader` quản lý cache riêng.
6. Đặt JAR vào một thư mục mà class loader đang dùng không thể truy cập rồi gọi `reload()` có bảo đảm plugin mới xuất hiện không? **Không.** Phải giải quyết khả năng nhìn thấy provider.
7. `stream().count()` có nhất thiết tạo instance provider? **Không.** Stream duyệt metadata `Provider`; muốn lấy instance gọi `Provider.get()`.
8. Vì sao `List<Plugin> active` không đổi khi chỉ gọi `loader.reload()`? **Vì đó là dữ liệu ứng dụng đã lưu riêng.** Phải duyệt lại rồi công bố snapshot mới.

## Tài liệu API chính thức

- [Java SE 26 — `java.util.ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): `iterator()`, `stream()`, `findFirst()`, `reload()`, lazy discovery, lỗi và concurrency.
- [Java SE 26 — `ServiceLoader.Provider<S>`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()` và `get()`.
- [Java SE 26 — `java.lang.ClassLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): khả năng tải lớp và resource dùng trong classpath-based SPI.

Điểm cần nhớ khi triển khai hệ thống hiện đại: `reload()` là thao tác **xóa cache và cho phép khám phá lại khi truy cập tiếp** của một đối tượng `ServiceLoader`. Khả năng tìm plugin mới, thay provider cũ và an toàn đa luồng là những trách nhiệm thiết kế ở tầng class loading và registry ứng dụng.
