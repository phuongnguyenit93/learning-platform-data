# SPI và tách hợp đồng dịch vụ khỏi nhà cung cấp với Java ServiceLoader

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **hợp đồng dịch vụ (service contract/SPI)**, **nhà cung cấp (provider)** và **bên sử dụng (consumer)**.
- Giải thích vì sao consumer chỉ phụ thuộc vào hợp đồng giúp thay đổi nhà cung cấp mà không sửa mã nghiệp vụ.
- Đăng ký và tìm provider bằng **java.util.ServiceLoader** trong ứng dụng Java hiện đại, cả **JPMS (named modules)** và **classpath**.
- Xử lý lựa chọn provider, lỗi cấu hình, vòng đời đối tượng và các giới hạn thực tế khi xây dựng kiến trúc plugin.

Nội dung sử dụng cú pháp và API còn áp dụng với **Java 17+**, bao gồm các JDK hiện đại. ServiceLoader xuất hiện từ Java 6, nhưng ví dụ dưới đây ưu tiên cách tổ chức và triển khai đang được sử dụng.

## 1. SPI là gì và vấn đề nó giải quyết

Giả sử ứng dụng cần biến đổi văn bản, xuất báo cáo hoặc tích hợp nhiều nhà cung cấp lưu trữ. Nếu code nghiệp vụ tạo trực tiếp lớp triển khai:

~~~java
// Ví dụ minh họa sự phụ thuộc trực tiếp, không phải chương trình độc lập:
UpperFormatter formatter = new UpperFormatter();
String result = formatter.format(input);
~~~

Consumer phải biết tên và cách khởi tạo provider cụ thể. Khi đổi provider, thêm plugin hoặc đóng gói lại, consumer có nguy cơ phải biên dịch và phát hành lại.

**Service Provider Interface (SPI)** là hợp đồng mà các provider thực thi để một consumer có thể sử dụng chúng qua một kiểu chung. Trong Java, hợp đồng thường là **public interface** hoặc **abstract class**. **ServiceLoader** là cơ chế chuẩn của JDK để *phát hiện và tạo* các provider được đăng ký; bản thân SPI là quyết định thiết kế, không phải một từ khóa Java.

Ba vai trò:

| Vai trò | Chịu trách nhiệm | Biết về |
| --- | --- | --- |
| **Contract/SPI** | Định nghĩa hành vi, dữ liệu trao đổi, điều kiện và lỗi chung | Các kiểu ổn định của chính nó |
| **Provider** | Thực thi hợp đồng, quản lý chi tiết kỹ thuật riêng | Contract và thư viện cần dùng |
| **Consumer** | Gọi hành vi qua contract, chọn provider theo chính sách | Contract và nhu cầu nghiệp vụ |

Hướng phụ thuộc ở **thời điểm biên dịch**:

~~~text
consumer  ───────►  contract/SPI  ◄───────  provider A
                          ▲
                          └───────────────  provider B
~~~

Consumer **không import** lớp provider A/B. Ở thời điểm chạy, runtime phân phối provider hợp lệ qua ServiceLoader. Việc *đóng gói và cung cấp* provider vẫn là trách nhiệm của ứng dụng hoặc môi trường triển khai; cơ chế phát hiện không tự tải thư viện từ Internet.

### API, SPI và DI khác nhau thế nào?

- **API** mô tả khả năng mà một thành phần công khai cho phía gọi; **SPI** nhấn mạnh điểm mở rộng mà bên thứ ba có thể *cung cấp một triển khai*. Một Java interface hoàn toàn có thể là API nhìn từ consumer và SPI nhìn từ provider.
- **Dependency Inversion Principle** là nguyên tắc hướng phụ thuộc về abstraction; SPI là một cách hiện thực nguyên tắc đó.
- **Dependency Injection (DI)** quyết định cách cấp đối tượng phụ thuộc. ServiceLoader có khả năng khám phá/khởi tạo provider nhưng không có đầy đủ scope, injection graph, configuration hay lifecycle management của các DI container. Trong ứng dụng Spring, DI thường phù hợp với bean nội bộ; ServiceLoader phù hợp khi cần điểm mở rộng/plugin độc lập framework.

## 2. Thiết kế hợp đồng thực sự tách khỏi triển khai

Một contract tốt có các đặc điểm:

1. **Nhỏ, rõ nghĩa và ổn định:** khai báo những hành vi consumer thực sự cần, tránh đặt lớp nội bộ của provider vào kiểu tham số hoặc kiểu trả về.
2. **Dữ liệu chung thuộc contract hoặc API dùng chung:** không rò rỉ kiểu SDK của riêng một nhà cung cấp. Với API trả kết quả phức tạp, dùng các DTO chung có ý nghĩa nghiệp vụ.
3. **Provider phụ thuộc vào contract:** provider tự quản lý SDK, kết nối, bộ nhớ đệm; consumer không gọi phương thức nội bộ của provider.
4. **Nêu rõ ngữ nghĩa:** nullability, lỗi có thể phát sinh, thứ tự xử lý, tính thread-safe, side effects, giới hạn đầu vào và hành vi khi thiếu provider.
5. **Có cơ chế chọn provider:** phát hiện được nhiều triển khai không có nghĩa thứ tự nào đó là ưu tiên nghiệp vụ. Lựa chọn cần dựa trên ID, capability, cấu hình hoặc chính sách được định nghĩa rõ.

Tách contract giúp **thay provider**, **thêm triển khai** và **kiểm thử bằng fake provider** mà không buộc consumer biên dịch phụ thuộc vào lớp triển khai. Nó không bảo đảm thay thế an toàn nếu hai provider vi phạm cùng một hợp đồng về ngữ nghĩa hoặc chất lượng.

## 3. ServiceLoader hoạt động ra sao?

**java.util.ServiceLoader<S>** nhận một kiểu dịch vụ rồi tìm các provider đã đăng ký phù hợp với môi trường runtime. Consumer gọi **ServiceLoader.load(TextFormatter.class)**, duyệt các provider và chọn một cái cần dùng.

### Hai cách đăng ký provider vẫn được hỗ trợ

| Môi trường | Consumer khai báo | Provider khai báo |
| --- | --- | --- |
| **Named modules (JPMS, Java 9+)** | **uses** trong module-info.java | **provides ... with ...** trong module-info.java |
| **Classpath truyền thống, vẫn hợp lệ** | Dùng **ServiceLoader.load(...)** | Tệp tài nguyên **META-INF/services/<tên đầy đủ của service>** nằm trong JAR/classpath |

JPMS cho phép giấu package triển khai: provider module không cần **exports** package chứa provider, nhưng vẫn công bố triển khai thông qua **provides**. Module consumer phải có **uses** cho service mà nó nạp. Khi chạy ứng dụng dạng module, các module provider phải hiện diện và được runtime resolve.

### Các đặc tính cần hiểu

- **Lazy:** tìm và tạo provider theo nhu cầu khi duyệt iterator/stream; tạo một ServiceLoader không có nghĩa mọi provider đều đã được khởi tạo.
- **Cache theo instance:** ServiceLoader giữ cache các provider đã nạp; **reload()** xóa cache khám phá/khởi tạo của loader đó để lần duyệt sau tìm lại. Reload **không tự gỡ class/module**, không thu hồi instance đã đưa cho consumer, và không thay thế một cơ chế hot deploy.
- **Thứ tự không phải chính sách chọn:** thứ tự từ ServiceLoader không nên được dùng làm độ ưu tiên nghiệp vụ, đặc biệt khi có nhiều provider.
- **Lỗi có thể phát sinh trong lúc duyệt:** provider thiếu class, sai cấu hình, lỗi khởi tạo hoặc không tuân thủ contract có thể gây **ServiceConfigurationError**. Không coi danh sách rỗng và cấu hình hỏng là cùng một trường hợp.
- **ServiceLoader không thread-safe:** nếu nhiều thread cùng thao tác một loader hoặc gọi reload, cần đồng bộ bên ngoài hoặc giới hạn loader trong một luồng/pha khởi động. Thread safety của provider là một vấn đề riêng.
- **Provider không tự động đáng tin:** khi khởi tạo, code của provider chạy trong process với quyền và tài nguyên của ứng dụng; cần kiểm soát nguồn thư viện và dependency.

## 4. Ví dụ hoàn chỉnh: đổi provider mà consumer không biết lớp triển khai

Ví dụ chạy được với **JDK 17+**. Có ba named modules: hợp đồng, nhà cung cấp chứa hai triển khai và ứng dụng tiêu thụ. Tên module cũng là tên thư mục trực tiếp dưới **src**.

~~~text
src/
├── com.example.format.spi/
│   ├── module-info.java
│   └── com/example/format/spi/TextFormatter.java
├── com.example.format.provider/
│   ├── module-info.java
│   └── com/example/format/provider/
│       ├── PlainFormatter.java
│       └── UpperFormatter.java
└── com.example.format.app/
    ├── module-info.java
    └── com/example/format/app/Main.java
~~~

### 4.1. Module hợp đồng: com.example.format.spi

**src/com.example.format.spi/module-info.java**

~~~java
module com.example.format.spi {
    exports com.example.format.spi;
}
~~~

**src/com.example.format.spi/com/example/format/spi/TextFormatter.java**

~~~java
package com.example.format.spi;

public interface TextFormatter {
    String id();
    String format(String text);
}
~~~

Contract chỉ biết rằng mỗi provider có một **id** và thực hiện **format**. Nó không import class nào của provider hay consumer.

### 4.2. Module provider: com.example.format.provider

**src/com.example.format.provider/module-info.java**

~~~java
module com.example.format.provider {
    requires com.example.format.spi;

    provides com.example.format.spi.TextFormatter
        with com.example.format.provider.PlainFormatter,
             com.example.format.provider.UpperFormatter;
}
~~~

**src/com.example.format.provider/com/example/format/provider/PlainFormatter.java**

~~~java
package com.example.format.provider;

import com.example.format.spi.TextFormatter;

public final class PlainFormatter implements TextFormatter {
    public PlainFormatter() {}

    @Override
    public String id() {
        return "plain";
    }

    @Override
    public String format(String text) {
        return text;
    }
}
~~~

**src/com.example.format.provider/com/example/format/provider/UpperFormatter.java**

~~~java
package com.example.format.provider;

import com.example.format.spi.TextFormatter;
import java.util.Locale;

public final class UpperFormatter implements TextFormatter {
    public UpperFormatter() {}

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String format(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

Hai provider cài đặt cùng một contract và có constructor public không tham số. Package triển khai **không được exports**; consumer không cần và không thể import trực tiếp các class này qua module boundary thông thường. **Locale.ROOT** làm kết quả chuyển chữ hoa độc lập với locale mặc định của máy.

### 4.3. Module consumer: com.example.format.app

**src/com.example.format.app/module-info.java**

~~~java
module com.example.format.app {
    requires com.example.format.spi;
    uses com.example.format.spi.TextFormatter;
}
~~~

**src/com.example.format.app/com/example/format/app/Main.java**

~~~java
package com.example.format.app;

import com.example.format.spi.TextFormatter;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        String selected = args.length == 0 ? "upper" : args[0];

        ServiceLoader<TextFormatter> loader =
            ServiceLoader.load(TextFormatter.class);

        TextFormatter formatter = loader.stream()
            .map(ServiceLoader.Provider::get)
            .filter(item -> item.id().equals(selected))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown formatter: " + selected));

        System.out.println(formatter.format("Hello Java"));
    }
}
~~~

Điểm cần quan sát: **Main** chỉ import **TextFormatter** và **ServiceLoader**. Nó chọn provider theo **id**, không theo vị trí đầu tiên trong danh sách và không dùng **new UpperFormatter()**. **Provider::get** kích hoạt việc lấy/khởi tạo đối tượng provider khi pipeline thực thi.

### 4.4. Biên dịch và chạy

Chạy tại thư mục chứa **src**, với **javac** và **java** cùng JDK 17 trở lên:

~~~bash
javac --module-source-path src -d mods -m com.example.format.spi,com.example.format.provider,com.example.format.app
java --module-path mods --add-modules com.example.format.provider -m com.example.format.app/com.example.format.app.Main upper
~~~

Kết quả chuẩn trên stdout:

~~~text
HELLO JAVA
~~~

Thử một provider khác, **không sửa hoặc biên dịch lại Main**:

~~~bash
java --module-path mods --add-modules com.example.format.provider -m com.example.format.app/com.example.format.app.Main plain
~~~

Stdout:

~~~text
Hello Java
~~~

**--add-modules com.example.format.provider** bảo đảm provider module được resolve trong ví dụ này. Ở môi trường sản xuất, việc cung cấp/resolve provider nên nằm trong cấu hình đóng gói và khởi chạy. Consumer vẫn chỉ khai báo **requires** với contract, không khai báo **requires** với provider.

**Luồng xử lý:** JVM resolve các module cần thiết → ServiceLoader tìm thông tin **provides** của provider khả dụng → consumer duyệt/lấy instance → lọc theo ID → gọi phương thức của contract → provider thực thi. Thay provider tương thích hoặc thay chính sách chọn chỉ tác động đến khâu cấu hình/lựa chọn thích hợp, không bắt consumer phụ thuộc vào class triển khai.

## 5. Nếu ứng dụng dùng classpath và JAR thông thường

ServiceLoader vẫn hỗ trợ classpath; JPMS không phải điều kiện bắt buộc để áp dụng SPI. Có thể giữ nguyên interface, lớp triển khai và logic Main ở trên, nhưng **không dùng các tệp module-info.java** trong cấu hình classpath. Provider JAR phải chứa tài nguyên:

~~~text
META-INF/services/com.example.format.spi.TextFormatter
~~~

Nội dung của tệp **UTF-8** đó là mỗi tên class provider đầy đủ trên một dòng:

~~~text
com.example.format.provider.PlainFormatter
com.example.format.provider.UpperFormatter
~~~

Đây là **minh họa cấu hình đóng gói classpath**, không phải một bộ lệnh build độc lập. Hệ thống build (Gradle/Maven) phải đóng gói tệp đúng đường dẫn **META-INF/services/** trong JAR runtime; provider class và dependency của nó phải nhìn thấy từ class loader phù hợp. Bên consumer chỉ cần biết contract và gọi ServiceLoader. Với cách đăng ký classpath này, các provider thông thường phải là lớp triển khai có thể khởi tạo bằng constructor public không tham số.

Với **named modules**, dùng **uses/provides** như mục 4. Không lấy việc có tệp META-INF/services làm lý do bỏ khai báo **provides** của một provider module. Khi dùng module layer hoặc custom class loader, hãy kiểm tra phạm vi khám phá thực tế bằng thử nghiệm tích hợp.

## 6. Áp dụng trong dự án thực tế

### Quy tắc chọn provider

Không dùng **iterator().next()** hoặc **findFirst()** một cách vô điều kiện khi tồn tại nhiều provider hợp lệ. Ưu tiên:

- Khai báo rõ ID/capability provider trong cấu hình của ứng dụng.
- Kiểm tra không có provider, ID trùng, provider không phù hợp phiên bản hoặc điều kiện runtime.
- Chọn chính xác một provider nếu nghiệp vụ chỉ cho phép một; nêu lỗi có ngữ cảnh khi thiếu hoặc có xung đột.
- Nếu muốn fallback, định nghĩa thứ tự ưu tiên **trong chính sách của ứng dụng**, có kiểm thử, thay vì ngầm dựa vào thứ tự tìm thấy.

Ví dụ mục 4 cố tình chỉ chọn theo ID để dễ quan sát; sản phẩm thực tế nên phát hiện ID trùng và quyết định lỗi/fallback ở pha khởi động.

### Vòng đời và khả năng tương thích

- Đừng tự giả định instance provider là singleton hoặc thread-safe. Nếu provider giữ kết nối hay tài nguyên, contract phải thống nhất **ai sở hữu và đóng tài nguyên**; cân nhắc dùng factory SPI trả về tài nguyên có **AutoCloseable**.
- Khi tiến hóa contract công khai, thêm phương thức abstract mới có thể làm provider cũ không còn tương thích. Cân nhắc **default method** khi thật sự có mặc định đúng nghĩa, giao diện phiên bản mới hoặc cơ chế capability/version rõ ràng.
- Viết **contract tests** dùng chung cho mọi provider, kiểm thử hành vi và trường hợp lỗi, thay vì chỉ kiểm tra provider có được tìm thấy.
- Dùng dependency constraints, ký/kiểm tra nguồn artifact và nguyên tắc quyền tối thiểu cho plugin. ServiceLoader là cơ chế kết nối code trong process, **không tạo sandbox**.
- Nếu provider có cấu hình riêng (endpoint, token, pool), hãy cung cấp qua cơ chế cấu hình/factory có thiết kế; đừng ép contract phụ thuộc trực tiếp vào implementation-specific configuration.

### Khi nào nên dùng, khi nào nên cân nhắc giải pháp khác?

**Phù hợp:** thư viện/framework muốn bên thứ ba đóng gói plugin; JDK extension points; ứng dụng cung cấp nhiều implement cùng một hợp đồng và khám phá chúng qua runtime packaging.

**Cân nhắc DI thông thường:** toàn bộ provider đều là bean nằm trong một ứng dụng Spring và cần lifecycle, configuration, proxy hay dependency injection sâu. Vẫn có thể kết hợp: dùng ServiceLoader để khám phá plugin rồi đưa adapter của nó vào layer nghiệp vụ, nếu kiến trúc thực sự cần.

## 7. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không tìm thấy provider | Thiếu **provides** hoặc thiếu tài nguyên **META-INF/services/**; module provider không được resolve | Kiểm tra module-info.java, module path/classpath, nội dung JAR và cấu hình chạy |
| **ServiceConfigurationError** | Sai tên class, provider không phù hợp service, lỗi tạo instance hay dependency thiếu | Đọc cause/stack trace, kiểm tra constructor hoặc provider factory được hỗ trợ và khả năng truy cập |
| Chọn nhầm provider | Dựa vào thứ tự phát hiện không ổn định | Chọn theo ID/capability và kiểm tra xung đột |
| Provider chạy được nhưng API bị rò rỉ | Contract trả về kiểu nội bộ/SDK của provider | Đưa DTO/exception có ý nghĩa chung vào contract |
| Kết quả thay đổi khi chạy đồng thời | Chia sẻ ServiceLoader không đồng bộ, hoặc provider chứa trạng thái không thread-safe | Đồng bộ vòng đời loader; đánh giá riêng thread safety của provider |
| Thay JAR nhưng ứng dụng không thấy triển khai mới | Hiểu nhầm **reload()** thành hot deploy hoặc module/class loader không nhìn thấy thay đổi | Thiết kế cơ chế reload/khởi động lại và class loader/layer rõ ràng |

Một cách kiểm tra nhanh khi debug là tạm in **loại provider** đang được phát hiện (ví dụ với **loader.stream().map(p -> p.type().getName())**). Chỉ dùng log chẩn đoán với dữ liệu không nhạy cảm; không biến tên class hoặc thứ tự xuất hiện thành hợp đồng nghiệp vụ.

## 8. Tự luyện tập

1. Thêm một **LowerFormatter** có ID **lower** và đăng ký nó trong **provides** của module provider. Chạy cùng Main với tham số **lower**; dự kiến stdout là **hello java**.
2. Bỏ **--add-modules com.example.format.provider** hoặc bỏ provider khỏi runtime rồi quan sát hành vi; xác định sự khác nhau giữa **không tìm thấy provider** và **provider cấu hình lỗi** trong môi trường chạy của mình.
3. Thử yêu cầu một ID không tồn tại. Main hiện báo **IllegalArgumentException** có chứa ID được yêu cầu; đề xuất nơi chuyển lỗi này thành thông báo cấu hình dễ hiểu hơn.
4. Định nghĩa một bộ contract tests chung để bảo đảm **format(null)**, ID trùng, ký tự Unicode và sử dụng đa luồng có hành vi được công bố rõ.

## Ghi nhớ

**Contract thuộc về phần dùng chung; provider triển khai contract; consumer chỉ gọi contract.** ServiceLoader cung cấp cơ chế khám phá provider tại runtime, còn lựa chọn provider, kiểm soát phiên bản, lỗi và vòng đời vẫn thuộc trách nhiệm thiết kế của ứng dụng. Phân tách đúng biên giới phụ thuộc đem lại khả năng thay thế và mở rộng mà không làm rò rỉ implementation vào nghiệp vụ.

**Tài liệu chính thức để đối chiếu:** [ServiceLoader Javadoc](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html) và [javac command reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html).