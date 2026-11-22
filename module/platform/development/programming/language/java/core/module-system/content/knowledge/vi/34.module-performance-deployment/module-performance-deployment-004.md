# ServiceLoader discovery và lazy provider

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích ServiceLoader tìm provider từ classpath và named module như thế nào.
- Chọn overload `ServiceLoader.load(...)` phù hợp với class loader hoặc ModuleLayer.
- Phân biệt discovery provider với việc tạo instance provider.
- Dùng `iterator()` và `stream()` để tiêu thụ provider theo nhu cầu.
- Dùng `Provider.type()` để kiểm tra metadata trước khi gọi `Provider.get()`.
- Hiểu cache, `reload()`, `ServiceConfigurationError` và giới hạn thread-safety.

## 1. Discovery và instantiation là hai bước khác nhau

`ServiceLoader<S>` là cơ chế tìm và sử dụng các implementation của service type `S`. Ứng dụng chỉ phụ thuộc vào service interface; provider có thể được bổ sung khi đóng gói hoặc triển khai.

Ví dụ, service API:

~~~java
package com.example.codec;

public interface Codec {
    String name();
    byte[] encode(String input);
}
~~~

Có thể có nhiều provider như `JsonCodec`, `XmlCodec` hoặc `BinaryCodec`. Consumer không cần tạo các class cụ thể trực tiếp. Nó yêu cầu `ServiceLoader` tìm provider cho `Codec`:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);
~~~

Tạo `ServiceLoader` chưa có nghĩa là tất cả provider đã được khởi tạo. ServiceLoader tìm provider theo cơ chế phù hợp với môi trường, sau đó tạo instance khi ứng dụng tiêu thụ provider. Cách làm này giúp ứng dụng tránh khởi tạo những implementation không cần dùng.

Hai khái niệm cần tách biệt:

- **Discovery:** xác định provider nào được cấu hình và có thể được nhìn thấy trong phạm vi tìm kiếm.
- **Instantiation:** tạo một instance của provider để ứng dụng gọi service method.

Discovery cũng không đồng nghĩa với việc mọi provider đều chắc chắn khởi tạo thành công. Một provider có thể được phát hiện nhưng lỗi khi class được nạp hoặc khi constructor/factory method chạy.

## 2. Provider được khai báo ở đâu?

Cách đăng ký provider phụ thuộc vào cách ứng dụng được triển khai.

### 2.1. Provider trên classpath

Với provider nằm trong unnamed module, thư viện đăng ký tên class trong service configuration file:

~~~text
META-INF/services/com.example.codec.Codec
~~~

Nội dung file là tên đầy đủ của từng provider class, mỗi tên trên một dòng:

~~~text
com.example.codec.json.JsonCodec
com.example.codec.xml.XmlCodec
~~~

Có thể ghi chú bằng ký tự `#`. Dòng trống được bỏ qua và tên provider trùng lặp không tạo thêm một provider khác.

Ví dụ, JAR provider JSON chứa:

~~~text
codec-json.jar
└── META-INF/
    └── services/
        └── com.example.codec.Codec
~~~

Khi service configuration file có mặt trên classpath được dùng để tìm kiếm, ServiceLoader đọc file này để phát hiện provider. Provider class theo cơ chế classpath phải đáp ứng quy tắc provider class, trong đó có public class và public constructor không tham số.

### 2.2. Provider trong named module

Với JPMS, provider được khai báo trong module descriptor bằng directive `provides`:

~~~java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.Codec
            with com.example.codec.json.JsonCodec;
}
~~~

Module consumer khai báo service mà nó sử dụng:

~~~java
module com.example.codec.app {
    requires com.example.codec.api;

    uses com.example.codec.Codec;
}
~~~

Trong named module, `uses` và `provides` là metadata mà hệ thống module dùng để xác định quan hệ service. Không cần tạo `META-INF/services` cho provider đã được đăng ký bằng module descriptor.

Có thể có nhiều provider module cùng cung cấp một service. ServiceLoader sẽ tìm các provider phù hợp trong phạm vi module layer hoặc class loader được yêu cầu.

## 3. Chọn phạm vi discovery bằng ServiceLoader.load

ServiceLoader có nhiều overload để chỉ rõ nơi tìm provider.

| Cách gọi | Phạm vi tìm kiếm |
|---|---|
| `ServiceLoader.load(Service.class)` | Dùng thread context class loader của thread hiện tại |
| `ServiceLoader.load(Service.class, classLoader)` | Dùng class loader được truyền vào |
| `ServiceLoader.load(layer, Service.class)` | Tìm provider trong ModuleLayer được chỉ định và các parent layer của nó |
| `ServiceLoader.loadInstalled(Service.class)` | Dùng extension/platform class loader theo cơ chế của API này |

Ví dụ với context class loader:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);
~~~

Ví dụ với class loader tường minh:

~~~java
ClassLoader pluginLoader =
        Thread.currentThread().getContextClassLoader();

ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class, pluginLoader);
~~~

Ví dụ với custom module layer:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(pluginLayer, Codec.class);
~~~

Overload nhận `ModuleLayer` phù hợp khi ứng dụng tạo plugin layer bằng `ModuleLayer.defineModules...` và muốn tìm provider thuộc layer đó. Nó tránh việc vô tình chỉ tìm provider theo một class loader không đại diện cho layer plugin.

Trong named module, module gọi ServiceLoader cần khai báo `uses` cho service tương ứng. Nếu thiếu directive này, việc gọi API trong ngữ cảnh named module có thể thất bại với `ServiceConfigurationError`.

## 4. Lazy loading khi dùng iterator()

Có thể duyệt provider bằng iterator:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

Iterator<Codec> iterator = loader.iterator();

while (iterator.hasNext()) {
    Codec codec = iterator.next();

    System.out.println(codec.name());
}
~~~

Iterator của ServiceLoader có hai đặc điểm:

1. Những provider instance đã được cache được trả về trước theo thứ tự chúng đã được thêm vào cache.
2. Các provider chưa được nạp sẽ được tìm và khởi tạo khi iterator cần phần tử tiếp theo; instance mới được thêm vào cache.

Vì vậy, ứng dụng có thể xử lý từng provider một thay vì buộc phải khởi tạo tất cả provider ngay từ đầu. Tuy nhiên, nếu vòng lặp duyệt hết iterator thì cuối cùng tất cả provider được tìm thấy trong phạm vi đó sẽ được tiêu thụ và khởi tạo.

Nếu chỉ cần provider đầu tiên, hãy dừng iteration sớm. Đừng chuyển iterator thành danh sách đầy đủ nếu mục tiêu là tránh khởi tạo các provider còn lại.

## 5. Lazy loading với stream() và Provider<S>

`ServiceLoader.stream()` trả về stream của `ServiceLoader.Provider<S>`, không phải stream của instance service `S`:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class);

Stream<ServiceLoader.Provider<Codec>> providers =
        loader.stream();
~~~

`Provider<S>` cung cấp hai phương thức quan trọng:

| Phương thức | Kết quả | Vai trò |
|---|---|---|
| `type()` | `Class<? extends S>` | Xem kiểu provider |
| `get()` | `S` | Lấy instance service |

Điểm hữu ích của `stream()` là ứng dụng có thể xem metadata của provider trước khi yêu cầu tạo instance.

Ví dụ, chỉ chọn provider có tên class thuộc package JSON:

~~~java
List<Codec> codecs = loader.stream()
        .filter(provider ->
                provider.type().getPackageName()
                        .equals("com.example.codec.json"))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

Pipeline được thực thi khi có terminal operation như `toList()`. `filter` kiểm tra `type()` trước; `map(Provider::get)` chỉ được thực hiện với provider vượt qua điều kiện lọc. Nhờ đó, provider không phù hợp có thể bị loại mà không cần gọi `get()`.

Có thể sắp xếp dựa trên tên class trước khi khởi tạo:

~~~java
List<Codec> codecs = loader.stream()
        .sorted(Comparator.comparing(
                provider -> provider.type().getName()))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

Thứ tự provider được phát hiện không nên được xem là thứ tự ưu tiên nghiệp vụ. Nếu ứng dụng cần ưu tiên JSON hơn XML, hãy định nghĩa metadata hoặc contract ưu tiên rõ ràng rồi sắp xếp theo quy tắc đó.

## 6. Provider factory method trong named module

Named module có thể khai báo provider thông qua public static method tên `provider`, không có tham số và có kiểu trả về tương thích với service.

Ví dụ:

~~~java
package com.example.codec.json;

import com.example.codec.Codec;

public final class JsonCodecFactory {

    private JsonCodecFactory() {
    }

    public static Codec provider() {
        return new JsonCodec();
    }
}
~~~

Module descriptor:

~~~java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.Codec
            with com.example.codec.json.JsonCodecFactory;
}
~~~

Trong cách này, class được liệt kê sau `with` là factory class. Nó không nhất thiết phải implement `Codec`; method `provider()` tạo và trả về implementation thực sự.

Khi sử dụng `ServiceLoader.Provider`:

- `Provider.get()` gọi factory method để lấy service instance.
- `Provider.type()` trả về kiểu trả về được khai báo của factory method.
- Vì vậy, `type()` có thể trả về `Codec.class` thay vì `JsonCodecFactory.class`.

Điều này quan trọng nếu ứng dụng lọc provider theo annotation hoặc package. Hãy đặt metadata trên kiểu mà `Provider.type()` thực sự trả về và kiểm tra module descriptor để biết provider đang dùng constructor hay factory method.

## 7. Cache và reload()

ServiceLoader lưu cache các provider instance được tìm thấy qua iterator. Khi iterator tiếp theo được tạo, các instance đã cache được trả về trước; sau đó ServiceLoader tiếp tục tìm provider chưa được nạp.

Khi ứng dụng cần nạp lại cấu hình provider, có thể gọi:

~~~java
loader.reload();
~~~

`reload()` xóa cache hiện tại và đặt lại trạng thái tìm kiếm provider. Những lần duyệt tiếp theo có thể phát hiện provider mới nếu class loader hoặc môi trường cấu hình đã thay đổi theo cách ServiceLoader có thể nhìn thấy.

Một số điểm cần chú ý:

- `reload()` không tự cài thêm JAR hoặc module vào class loader/module layer.
- Nếu class loader không thể nhìn thấy provider mới, gọi `reload()` cũng không làm provider đó xuất hiện.
- Không gọi `reload()` khi một iterator của cùng loader đang được duyệt; kết quả của việc reload trong lúc iteration đang diễn ra không được xác định.
- `reload()` không thay thế việc tạo class loader hoặc ModuleLayer mới khi plugin deployment yêu cầu một phạm vi nạp module khác.

Ví dụ:

~~~java
ServiceLoader<Codec> loader =
        ServiceLoader.load(Codec.class, pluginLoader);

// Nạp và sử dụng provider hiện có
loader.forEach(codec ->
        System.out.println(codec.name()));

// Xóa cache trước lần duyệt tiếp theo
loader.reload();

loader.forEach(codec ->
        System.out.println(codec.name()));
~~~

Nếu plugin được triển khai theo từng phiên bản hoặc cần unload độc lập, hãy cân nhắc tạo class loader hoặc module layer riêng cho từng vòng đời plugin thay vì chỉ dựa vào `reload()`.

## 8. Lỗi khi discovery hoặc khởi tạo provider

ServiceLoader có thể ném `ServiceConfigurationError` khi phát hiện cấu hình provider không hợp lệ hoặc không thể sử dụng provider. Một số nguyên nhân thường gặp:

- Service configuration file sai định dạng hoặc tên provider class không hợp lệ.
- Provider class không tìm thấy được bằng class loader đang dùng.
- Provider không phải subtype của service.
- Provider class không đáp ứng quy tắc constructor hoặc factory method.
- Constructor hoặc factory method ném exception.
- Named module thiếu directive `uses` hoặc provider declaration không hợp lệ.

Ví dụ xử lý lỗi tại ranh giới nạp plugin:

~~~java
try {
    ServiceLoader.load(Codec.class, pluginLoader)
            .forEach(codec ->
                    System.out.println(codec.name()));
} catch (ServiceConfigurationError error) {
    logger.error("Unable to load a Codec provider", error);
}
~~~

Không nên bắt lỗi rồi bỏ qua hoàn toàn. Hãy ghi lại provider hoặc cấu hình gây lỗi để người vận hành biết vì sao một implementation không xuất hiện. Nếu ứng dụng có thể tiếp tục khi thiếu một provider tùy chọn, hãy quyết định rõ chính sách fallback.

Lỗi có thể xuất hiện trong lúc tiêu thụ iterator/stream, không nhất thiết ngay khi gọi `ServiceLoader.load(...)`. Vì vậy, đặt xử lý lỗi quanh đoạn thực sự duyệt hoặc lấy instance.

## 9. Thread-safety và vòng đời loader

Các instance `ServiceLoader` không an toàn cho việc sử dụng đồng thời từ nhiều thread. Cache nội bộ và trạng thái discovery của loader không được thiết kế như một concurrent collection.

Nếu nhiều thread cần truy cập service, có thể:

- Tạo loader riêng theo thread hoặc theo thành phần, nếu phạm vi discovery cho phép.
- Hoàn tất discovery ở một bước khởi tạo có kiểm soát, sau đó công bố danh sách service instance bất biến cho các thread.
- Dùng cơ chế đồng bộ bên ngoài nếu buộc phải chia sẻ một loader.
- Quản lý rõ vòng đời class loader/module layer để tránh giữ tham chiếu tới plugin đã ngừng hoạt động.

Cũng không nên giả định mọi lần gọi `Provider.get()` đều trả về cùng một singleton instance. Provider có thể tạo instance theo constructor hoặc factory method. Nếu ứng dụng yêu cầu singleton, hãy định nghĩa và quản lý vòng đời instance trong chính ứng dụng hoặc provider contract.

## 10. Chọn iterator hay stream?

| Nhu cầu | Cách phù hợp |
|---|---|
| Duyệt từng service instance theo thứ tự discovery | `iterator()` hoặc enhanced for |
| Xử lý tuần tự và dừng khi tìm thấy kết quả đầu tiên | `iterator()` hoặc stream có short-circuit terminal operation |
| Lọc theo class, package hoặc annotation trước khi tạo instance | `stream()` và `Provider.type()` |
| Sắp xếp theo metadata của provider | `stream().sorted(...)` rồi mới gọi `get()` |
| Cần tất cả instance để xử lý hàng loạt | `stream().map(Provider::get).toList()` |
| Nạp lại cache sau khi cấu hình class loader thay đổi | `reload()` rồi duyệt lại |

Hãy nhớ rằng terminal operation có thể làm pipeline tiêu thụ provider. Một pipeline không có terminal operation chưa thực hiện toàn bộ công việc discovery và instantiation.

## 11. Tóm tắt

ServiceLoader phát hiện provider từ service configuration file trên classpath hoặc từ directive `provides` trong named module. Phạm vi tìm kiếm được chọn bằng overload `load(...)`, chẳng hạn context class loader, class loader tường minh hoặc ModuleLayer.

Discovery và instantiation diễn ra lazy. Iterator tạo instance khi cần phần tử tiếp theo; stream trả về `Provider<S>` để ứng dụng kiểm tra `type()` trước khi gọi `get()`. Cache giúp tái sử dụng provider instance trong các lần duyệt iterator, còn `reload()` xóa cache và khởi động lại việc tìm kiếm. Ứng dụng cần xử lý `ServiceConfigurationError`, quản lý vòng đời loader và tránh chia sẻ một ServiceLoader giữa nhiều thread mà không có đồng bộ.

Tài liệu tham khảo:

- [ServiceLoader — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html)
- [ServiceLoader.Provider — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.Provider.html)
- [The Java Module System — JLS, Chapter 7](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html)
