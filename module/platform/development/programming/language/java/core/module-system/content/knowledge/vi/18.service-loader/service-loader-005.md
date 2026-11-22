# ServiceLoader.Provider type

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích `ServiceLoader.Provider<S>` đại diện cho điều gì trong cơ chế ServiceLoader.
- Phân biệt `type()` và `get()`.
- Dùng `ServiceLoader.stream()` để lọc hoặc sắp xếp provider dựa trên metadata trước khi tạo instance.
- Hiểu cách `Provider.type()` hoạt động khi module dùng provider factory method.

## 1. ServiceLoader.Provider nằm ở đâu?

Từ Java 9, `java.util.ServiceLoader` cung cấp interface lồng nhau `ServiceLoader.Provider<S>`. `S` là kiểu service mà ứng dụng đang tìm kiếm. Interface này kế thừa `Supplier<S>` và biểu diễn một service provider do `ServiceLoader` tìm thấy.

Khi gọi `ServiceLoader.stream()`, mỗi phần tử của stream có kiểu `ServiceLoader.Provider<S>`, không phải trực tiếp là một đối tượng service:

~~~java
ServiceLoader<CodecFactory> loader =
        ServiceLoader.load(CodecFactory.class);

Stream<ServiceLoader.Provider<CodecFactory>> providers =
        loader.stream();
~~~

Điểm quan trọng là ứng dụng có thể xem thông tin về kiểu provider trước khi yêu cầu tạo đối tượng. Điều này hữu ích khi cần chọn implementation dựa trên annotation, tên lớp, package hoặc metadata khác.

So sánh hai cách duyệt:

| Cách duyệt | Phần tử nhận được | Khi nào lấy instance service? |
|---|---|---|
| `loader.iterator()` | `S` | Khi lấy phần tử tiếp theo từ iterator |
| `loader.stream()` | `ServiceLoader.Provider<S>` | Khi gọi `Provider.get()` |

`stream()` hỗ trợ xử lý theo kiểu lazy. Việc tìm và xử lý provider diễn ra khi stream được tiêu thụ. Một pipeline có thể loại provider không phù hợp dựa trên `type()` mà không gọi `get()` cho các provider đó.

## 2. Cấu trúc API

API cốt lõi có dạng:

~~~java
public static interface ServiceLoader.Provider<S>
        extends Supplier<S> {

    Class<? extends S> type();

    S get();
}
~~~

Hai phương thức có hai mục đích riêng:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `type()` | `Class<? extends S>` | Trả về kiểu provider |
| `get()` | `S` | Trả về một instance của service provider |

Vì `Provider` kế thừa `Supplier<S>`, bạn cũng có thể dùng method reference `ServiceLoader.Provider::get` trong Stream API.

### 2.1. `type()` — xem kiểu mà chưa lấy instance

~~~java
ServiceLoader.Provider<CodecFactory> provider = /* lấy từ loader.stream() */;

Class<? extends CodecFactory> providerType = provider.type();

System.out.println(providerType.getName());
~~~

`type()` cung cấp đối tượng `Class` để ứng dụng đọc metadata, ví dụ:

~~~java
boolean supportsPng =
        provider.type().isAnnotationPresent(SupportsPng.class);

String implementationName = provider.type().getName();
~~~

Gọi `type()` không yêu cầu tạo instance của service provider. Tuy nhiên, kiểu được trả về không được bảo đảm là accessible từ code hiện tại hoặc có public constructor không tham số. Vì vậy, không nên dùng `type()` như một cách tự tạo instance bằng reflection.

### 2.2. `get()` — lấy instance service

~~~java
CodecFactory factory = provider.get();
String format = factory.format();
~~~

`get()` trả về instance có kiểu service `S`. Với provider thông thường, `ServiceLoader` tạo provider bằng public constructor không tham số. Với provider khai báo factory method trong module, `ServiceLoader` gọi method đó để lấy instance.

Nếu không thể khởi tạo provider, factory method trả về `null`, hoặc factory method ném lỗi/exception, `get()` có thể ném `ServiceConfigurationError`.

Không gọi constructor từ `provider.type()` để thay thế `get()`. Cách đó bỏ qua quy tắc khởi tạo của ServiceLoader và có thể thất bại với provider dùng factory method.

## 3. Ví dụ: lọc provider trước khi khởi tạo

Giả sử ứng dụng có service `CodecFactory`:

~~~java
package com.example.codec;

public interface CodecFactory {
    String format();
}
~~~

Ứng dụng dùng annotation để đánh dấu provider hỗ trợ PNG:

~~~java
package com.example.codec;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface SupportsPng {
}
~~~

Một implementation được đánh dấu annotation:

~~~java
package com.example.codec.png;

import com.example.codec.CodecFactory;
import com.example.codec.SupportsPng;

@SupportsPng
public final class PngCodecFactory implements CodecFactory {

    public PngCodecFactory() {
    }

    @Override
    public String format() {
        return "PNG";
    }
}
~~~

Module chứa provider khai báo service bằng directive `provides`:

~~~java
module codec.png {
    requires codec.api;

    provides com.example.codec.CodecFactory
            with com.example.codec.png.PngCodecFactory;
}
~~~

Module ứng dụng khai báo service mà nó sử dụng bằng directive `uses`:

~~~java
module codec.app {
    requires codec.api;

    uses com.example.codec.CodecFactory;
}
~~~

Ứng dụng có thể kiểm tra annotation trước, sau đó chỉ khởi tạo provider phù hợp:

~~~java
import com.example.codec.CodecFactory;
import com.example.codec.SupportsPng;

import java.util.List;
import java.util.ServiceLoader;

public class CodecRegistry {

    public static List<CodecFactory> loadPngFactories() {
        ServiceLoader<CodecFactory> loader =
                ServiceLoader.load(CodecFactory.class);

        return loader.stream()
                .filter(provider ->
                        provider.type()
                                .isAnnotationPresent(SupportsPng.class))
                .map(ServiceLoader.Provider::get)
                .toList();
    }
}
~~~

Pipeline trên hoạt động theo thứ tự:

1. `ServiceLoader.load(...)` tạo loader cho service `CodecFactory`.
2. `stream()` cung cấp các đối tượng `Provider<CodecFactory>`.
3. `filter(...)` gọi `type()` để kiểm tra annotation trên kiểu provider.
4. Provider không có annotation bị loại khỏi pipeline mà không cần gọi `get()` cho provider đó.
5. `map(ServiceLoader.Provider::get)` tạo instance cho các provider còn lại.
6. `toList()` tiêu thụ stream và thu thập các instance thành danh sách.

Nếu muốn xử lý theo tên lớp, có thể sắp xếp trước bước tạo instance:

~~~java
List<CodecFactory> factories = loader.stream()
        .sorted((left, right) ->
                left.type().getName().compareTo(right.type().getName()))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

Cách sắp xếp này làm thứ tự xử lý rõ ràng theo tên lớp, thay vì phụ thuộc vào thứ tự provider được phát hiện.

## 4. Provider factory method và kết quả của `type()`

Trong named module, provider có thể được tạo thông qua một public static method tên `provider`, không có tham số và có kiểu trả về tương thích với service. Khi dùng cách này, lớp khai báo method `provider()` không bắt buộc phải implement service.

Ví dụ:

~~~java
package com.example.codec.png;

import com.example.codec.CodecFactory;

public final class PngCodecFactory implements CodecFactory {

    @Override
    public String format() {
        return "PNG";
    }
}
~~~

Lớp factory:

~~~java
package com.example.codec.png;

public final class ExtendedCodecsFactory {

    public static PngCodecFactory provider() {
        return new PngCodecFactory();
    }
}
~~~

Module khai báo factory class là provider:

~~~java
module codec.png {
    requires codec.api;

    provides com.example.codec.CodecFactory
            with com.example.codec.png.ExtendedCodecsFactory;
}
~~~

Ở trường hợp này:

- `ExtendedCodecsFactory` là lớp chứa factory method.
- `PngCodecFactory` là kiểu trả về được khai báo của method `provider()`.
- `Provider.type()` trả về `PngCodecFactory.class`, tức kiểu trả về của factory method.
- `Provider.get()` gọi factory method để nhận instance service.

Do đó, `type()` không nhất thiết trả về lớp được liệt kê sau `with` trong directive `provides`. Khi module sử dụng provider factory, API quy định `type()` trả về kiểu trả về của method `provider()`.

Chi tiết này quan trọng khi dùng annotation hoặc metadata để lựa chọn provider: hãy đặt metadata trên kiểu mà `type()` thực sự trả về.

## 5. Những điểm cần nhớ khi sử dụng

- Dùng `type()` khi cần kiểm tra metadata hoặc quyết định có chọn provider hay không.
- Dùng `get()` khi thực sự cần instance để gọi các phương thức của service.
- `Provider<S>` là wrapper mô tả provider; bản thân nó không phải instance `S`.
- Không giả định kiểu từ `type()` có thể truy cập trực tiếp hoặc có public constructor không tham số.
- Không tự khởi tạo bằng reflection; để `ServiceLoader.Provider.get()` thực hiện đúng quy tắc tạo provider.
- Xử lý `ServiceConfigurationError` ở nơi phù hợp nếu provider có thể cấu hình sai hoặc không thể khởi tạo.
- Với provider factory trong named module, nhớ rằng `type()` trả về kiểu trả về của method `provider()`.

## 6. Tóm tắt

`ServiceLoader.Provider<S>` bổ sung một bước trung gian giữa việc tìm thấy provider và việc tạo instance service. `type()` cho phép xem kiểu provider để lọc, sắp xếp hoặc kiểm tra annotation. `get()` mới là thao tác lấy instance `S`. Kết hợp hai phương thức với `ServiceLoader.stream()` giúp ứng dụng lựa chọn provider dựa trên metadata trước khi khởi tạo những provider cần dùng.

Tài liệu API: [ServiceLoader.Provider — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.Provider.html)
