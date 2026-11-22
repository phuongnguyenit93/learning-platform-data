# Provider stream và lazy instantiation trong ServiceLoader

## 1. Mục tiêu

Từ Java 9, `ServiceLoader` cung cấp phương thức `stream()` để làm việc với danh sách provider thông qua `ServiceLoader.Provider<S>`. Cách này cho phép ứng dụng xem loại class triển khai service, lọc hoặc chọn provider, rồi mới yêu cầu tạo instance khi thật sự cần.

Điểm quan trọng là phải phân biệt **khám phá provider**, **nạp class provider** và **khởi tạo service instance**. Ba việc này không nhất thiết xảy ra cùng lúc. Provider stream giúp trì hoãn bước khởi tạo instance, đặc biệt hữu ích khi ứng dụng có nhiều plugin hoặc provider có constructor hay factory method tốn tài nguyên.

Sau bài này, bạn có thể:

- Giải thích vai trò của `ServiceLoader`, `ServiceLoader.Provider<S>` và service instance.
- Dùng `stream()` để xem loại provider trước khi tạo instance.
- Lọc provider theo class rồi chỉ khởi tạo provider được chọn.
- Phân biệt lazy evaluation của Java Stream với lazy instantiation của ServiceLoader.

## 2. Ba thành phần cần phân biệt

Khi dùng ServiceLoader, hãy tách ba khái niệm sau:

| Thành phần | Vai trò |
| --- | --- |
| `ServiceLoader<S>` | Tìm và quản lý các provider cho service type `S`. |
| `ServiceLoader.Provider<S>` | Đại diện cho một provider; cho phép xem type và yêu cầu tạo service instance. |
| `S` | Instance thực tế mà ứng dụng gọi để sử dụng chức năng. |

Ví dụ:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

var providers = loader.stream();
```

Ở thời điểm tạo `loader` và pipeline `providers`, ứng dụng chưa yêu cầu một instance `Codec` cụ thể. Mỗi phần tử mà `stream()` cung cấp là một đối tượng `Provider<Codec>`, không phải một đối tượng `Codec`.

Hai phương thức quan trọng của `Provider<S>` là:

- `type()`: trả về class của provider để ứng dụng có thể xem tên class, annotation hoặc metadata trên class. Việc này có thể khiến class provider được nạp, nhưng không gọi constructor hoặc provider method để tạo service instance.
- `get()`: yêu cầu một service instance từ provider. Đây là điểm ứng dụng chủ động bước sang giai đoạn khởi tạo.

Vì vậy, **biết class provider không đồng nghĩa với việc đã tạo service instance**.

## 3. Ví dụ service trong Java Module System

Giả sử ứng dụng có service `Codec` và một provider là `JsonCodec`.

### Module khai báo service API

File `module-info.java` của module API:

```java
module com.example.codec.api {
    exports com.example.codec.api;
}
```

Interface service:

```java
package com.example.codec.api;

public interface Codec {
    String format();

    String encode(String input);
}
```

### Module cung cấp implementation

Module provider khai báo implementation bằng directive `provides ... with ...`:

```java
module com.example.codec.json {
    requires com.example.codec.api;

    provides com.example.codec.api.Codec
        with com.example.codec.json.JsonCodec;
}
```

Implementation có thể ghi log trong constructor để quan sát thời điểm khởi tạo:

```java
package com.example.codec.json;

import com.example.codec.api.Codec;

public final class JsonCodec implements Codec {

    public JsonCodec() {
        System.out.println("JsonCodec được khởi tạo");
    }

    @Override
    public String format() {
        return "json";
    }

    @Override
    public String encode(String input) {
        return "encoded:" + input;
    }
}
```

### Module tiêu thụ service

Module sử dụng service khai báo `uses`:

```java
module com.example.app {
    requires com.example.codec.api;

    uses com.example.codec.api.Codec;
}
```

Ứng dụng chỉ phụ thuộc vào service API. Nó không cần import trực tiếp hoặc khai báo `requires com.example.codec.json` để gọi ServiceLoader theo tên implementation. Provider module phải có mặt trong module path và được đưa vào module layer đang dùng.

## 4. Xem provider type mà chưa tạo instance

Dùng `stream()` kết hợp `Provider.type()` để lấy danh sách class:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

List<Class<? extends Codec>> providerTypes = loader.stream()
    .map(provider -> provider.type())
    .toList();

providerTypes.forEach(type ->
    System.out.println(type.getName())
);
```

Pipeline trên duyệt các provider và lấy class tương ứng. Nó không gọi `Provider.get()`, vì vậy constructor của `JsonCodec` chưa được gọi chỉ bởi thao tác lấy type.

Có thể dùng class để kiểm tra metadata trước khi khởi tạo:

```java
loader.stream()
    .map(provider -> provider.type())
    .filter(type -> type.getSimpleName().endsWith("Codec"))
    .forEach(type -> System.out.println("Provider: " + type.getName()));
```

Lưu ý: lấy `type()` có thể cần nạp class provider và có thể phát sinh lỗi cấu hình nếu provider không hợp lệ hoặc không thể được nạp. Lazy instantiation không có nghĩa là mọi bước khám phá class đều bị trì hoãn đến sau `get()`.

## 5. Chỉ khởi tạo provider được chọn

Lợi ích rõ nhất của provider stream xuất hiện khi có nhiều implementation nhưng ứng dụng chỉ cần một implementation phù hợp.

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

Codec codec = loader.stream()
    .filter(provider ->
        provider.type().getSimpleName().equals("JsonCodec")
    )
    .findFirst()
    .map(ServiceLoader.Provider::get)
    .orElseThrow(() ->
        new IllegalStateException("Không tìm thấy JsonCodec")
    );

System.out.println(codec.format());
System.out.println(codec.encode("hello"));
```

Luồng xử lý:

1. `loader.stream()` cung cấp các provider.
2. `filter(...)` kiểm tra class của từng provider. Việc kiểm tra này không tạo service instance.
3. `findFirst()` dừng khi tìm được provider phù hợp đầu tiên.
4. `map(Provider::get)` gọi `get()` trên provider đã chọn.
5. Constructor hoặc cơ chế factory của provider được thực thi để cung cấp service instance.

Nếu provider bị loại ở bước lọc, ứng dụng không gọi `get()` cho provider đó. Đây là cách tránh khởi tạo những implementation không được sử dụng.

Bạn cũng có thể chọn theo annotation, interface phụ hoặc quy tắc tên package. Ví dụ:

```java
Optional<Codec> selected = loader.stream()
    .filter(provider ->
        provider.type().isAnnotationPresent(PreferredCodec.class)
    )
    .findFirst()
    .map(provider -> provider.get());
```

Trong ví dụ này, annotation được đọc từ class provider. Chỉ provider đầu tiên thỏa điều kiện mới được yêu cầu tạo instance.

## 6. Lazy evaluation của Stream và lazy instantiation của provider

Hai cơ chế này liên quan với nhau nhưng không giống nhau:

**Lazy evaluation của Java Stream** có nghĩa là các intermediate operation như `filter`, `map` và `peek` chưa chạy cho đến khi có terminal operation, chẳng hạn `toList()`, `findFirst()` hoặc `forEach()`.

**Lazy instantiation của ServiceLoader.Provider** có nghĩa là ứng dụng có thể duyệt và kiểm tra provider type mà chưa tạo service instance. Instance chỉ được yêu cầu khi gọi `Provider.get()`.

Ví dụ:

```java
var stream = ServiceLoader.load(Codec.class)
    .stream()
    .filter(provider -> provider.type().getSimpleName().contains("Codec"));
```

Dòng lệnh trên mới xây dựng pipeline. Chưa có terminal operation nên pipeline chưa duyệt provider.

Khi gọi:

```java
List<ServiceLoader.Provider<Codec>> candidates = stream.toList();
```

Stream được thực thi và các provider phù hợp được thu thập. Tuy nhiên, thao tác này vẫn không gọi `get()`, nên chưa yêu cầu tạo các service instance.

Chỉ khi gọi:

```java
Codec first = candidates.get(0).get();
```

ứng dụng mới yêu cầu instance từ provider đầu tiên.

## 7. So sánh stream() với iterator()

Cả hai cách đều dùng ServiceLoader để duyệt provider, nhưng mức độ kiểm soát khác nhau.

| Cách duyệt | Giá trị nhận được | Có thể xem provider type trước khi tạo instance? |
| --- | --- | --- |
| `iterator()` hoặc vòng lặp for-each | Service instance | Không qua API iterator thông thường; gọi `next()` lấy instance. |
| `stream()` | `Provider<S>` | Có; gọi `type()` trước và chỉ gọi `get()` khi cần. |

Ví dụ dùng iterator:

```java
for (Codec codec : ServiceLoader.load(Codec.class)) {
    System.out.println(codec.format());
}
```

Cách này phù hợp khi ứng dụng chủ ý sử dụng mọi implementation. Khi duyệt bằng iterator, mỗi lần lấy phần tử tiếp theo sẽ cung cấp service instance.

Ví dụ dùng provider stream:

```java
ServiceLoader.load(Codec.class)
    .stream()
    .map(provider -> provider.type().getName())
    .forEach(System.out::println);
```

Cách này phù hợp khi ứng dụng cần kiểm tra hoặc chọn implementation trước khi tạo instance.

## 8. Những điểm cần chú ý

- **Không gọi `get()` quá sớm:** Nếu mục tiêu chỉ là liệt kê class, tên provider hoặc annotation thì dùng `type()`. Gọi `get()` sẽ yêu cầu tạo instance và có thể kích hoạt công việc tốn tài nguyên.
- **Không nhầm nạp class với tạo object:** `type()` có thể làm class được nạp. Điều đó vẫn khác với việc chạy constructor hoặc provider method.
- **Terminal operation quyết định lúc Stream chạy:** Nếu chỉ tạo pipeline rồi giữ lại, các intermediate operation chưa được thực thi.
- **Không dựa vào thứ tự provider như một chính sách ưu tiên:** Nếu ứng dụng cần chọn provider theo tiêu chí, hãy biểu diễn tiêu chí đó rõ ràng bằng filter hoặc logic lựa chọn.
- **Xử lý lỗi cấu hình:** ServiceLoader có thể ném `ServiceConfigurationError` khi khai báo provider sai, không tìm thấy class hoặc không thể tạo instance. Hãy xử lý lỗi tại ranh giới nạp plugin phù hợp.
- **Chú ý khả năng đồng thời:** Một đối tượng `ServiceLoader` không được thiết kế để nhiều thread cùng sửa đổi hoặc duyệt mà không có đồng bộ. Nếu cần dùng đồng thời, hãy quản lý vòng đời loader và việc truy cập theo cách an toàn.
- **Phân biệt module path và classpath:** Với named module, consumer khai báo `uses` và provider khai báo `provides ... with ...`. Với classpath, provider thường được đăng ký trong file `META-INF/services/<tên-đầy-đủ-của-service>`. Cả hai cách đều cần đúng service type và provider có thể được phát hiện trong môi trường chạy.

## 9. Khi nào nên dùng Provider stream?

Dùng `ServiceLoader.stream()` khi ứng dụng cần một hoặc nhiều việc sau:

- Có nhiều plugin nhưng chỉ muốn khởi tạo plugin phù hợp với cấu hình hiện tại.
- Cần đọc annotation hoặc metadata của implementation trước khi quyết định sử dụng.
- Muốn hiển thị danh sách provider để chẩn đoán mà không khởi tạo tất cả.
- Muốn tránh side effect hoặc chi phí trong constructor/provider method của implementation không được chọn.

Nếu ứng dụng chắc chắn cần chạy tất cả implementation, vòng lặp qua ServiceLoader có thể đơn giản và dễ đọc hơn. Nếu cần lựa chọn có điều kiện trước khi khởi tạo, provider stream cung cấp quyền kiểm soát phù hợp.

## 10. Ghi nhớ

- `ServiceLoader<S>` quản lý việc khám phá provider cho service.
- `stream()` trả về các `Provider<S>`, không trả về trực tiếp các service instance.
- `Provider.type()` cho phép xem class provider mà chưa yêu cầu tạo service instance.
- `Provider.get()` là thao tác yêu cầu service instance.
- Java Stream chỉ thực thi pipeline khi có terminal operation; điều này độc lập với việc provider có được khởi tạo hay không.

Khi đọc code ServiceLoader, hãy tìm vị trí gọi `Provider.get()`. Vị trí đó cho biết lúc nào ứng dụng thực sự yêu cầu tạo implementation, còn các thao tác trên `Provider.type()` thường phục vụ việc khám phá và lựa chọn trước đó.
