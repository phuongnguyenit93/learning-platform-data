# Tài liệu service provider contract

Trong Java Platform Module System (JPMS), cơ chế ServiceLoader cho phép một mô-đun **sử dụng dịch vụ** mà không phải phụ thuộc trực tiếp vào lớp cài đặt. Mô-đun định nghĩa service public API; các mô-đun khác đăng ký provider thông qua chỉ thị provides ... with ...; consumer khai báo uses và khám phá provider ở runtime.

Điểm dễ bị bỏ qua là: **module-info.java chỉ công bố khả năng kết nối, không mô tả đầy đủ hợp đồng vận hành**. Một provider có thể được ServiceLoader tìm thấy và tạo thành công nhưng vẫn không tương thích với ứng dụng nếu nó trả về dữ liệu sai, xử lý null khác kỳ vọng, không an toàn khi gọi đồng thời hoặc sử dụng tài nguyên không được quản lý.

Vì vậy, tài liệu service provider contract (SPI contract) phải nói rõ **consumer có thể kỳ vọng điều gì** và **provider bắt buộc thực hiện những gì**. Bài này hướng dẫn cách tài liệu hóa hợp đồng từ khai báo mô-đun đến hành vi, lỗi, vòng đời, kiểm thử và tiến hóa API.

## 1. Phân biệt service API, SPI, provider và consumer

Các vai trò thường gặp:

| Vai trò | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| Service API / SPI | Định nghĩa interface hoặc abstract class mà provider phải đáp ứng | GreetingService |
| Provider | Cài đặt hợp đồng và đăng ký với JPMS | EnglishGreetingProvider |
| Consumer | Dùng ServiceLoader để tìm và gọi provider | GreetingApplication |
| Host / runtime | Resolve module graph và tạo môi trường nạp provider | Java launcher hoặc ModuleLayer |
| Contract document | Mô tả hành vi, ràng buộc, lỗi và compatibility của SPI | Tài liệu này hoặc README cạnh SPI |

Trong dự án nhỏ, service API và SPI có thể là cùng một interface. Với hệ thống lớn, có thể tách public consumer API và extension SPI thành các package riêng. Dù tổ chức thế nào, hợp đồng cần chỉ ra chính xác **kiểu dịch vụ nào là điểm mở rộng ổn định**.

ServiceLoader không tự kiểm tra các quy tắc nghiệp vụ. Nó chỉ hỗ trợ khám phá và khởi tạo provider theo cấu hình module. Việc tuân thủ hợp đồng phải được thể hiện bằng tài liệu và kiểm thử.

## 2. Hợp đồng cần trả lời những câu hỏi gì?

Một tài liệu đủ dùng cho người viết provider cần trả lời:

1. Tên service interface và module sở hữu nó là gì?
2. Provider cần cài đặt những phương thức nào, với ý nghĩa cụ thể ra sao?
3. Tham số nào được phép null, rỗng hoặc nằm ngoài miền hợp lệ?
4. Giá trị trả về có thể null không, có bất biến hoặc format cố định không?
5. Exception nào biểu thị lỗi đầu vào, lỗi nghiệp vụ và lỗi hạ tầng?
6. Provider có được giữ trạng thái hoặc truy cập mạng/file khi khởi tạo không?
7. Một instance có thể được gọi từ nhiều thread đồng thời không?
8. Provider có cần id duy nhất, version hoặc priority không?
9. Consumer chọn provider nào khi có nhiều implementation?
10. Module provider đăng ký bằng provides ... with ... như thế nào?
11. Provider được discover trong boot layer hay plugin layer?
12. Làm sao chạy contract test và xác nhận backward compatibility?

Nếu tài liệu chỉ nói “implement interface này và thêm provides”, các câu hỏi quan trọng về vận hành vẫn chưa được giải đáp.

## 3. Ví dụ service contract: GreetingService

Giả sử ứng dụng muốn cho phép nhiều gói mở rộng cung cấp lời chào theo ngôn ngữ. Module API được định nghĩa:

~~~java
module com.example.greeting.api {
    exports com.example.greeting.spi;
}
~~~

Interface SPI:

~~~java
package com.example.greeting.spi;

public interface GreetingService {
    String id();

    String greet(String name);
}
~~~

Đây là cú pháp Java hợp lệ, nhưng chỉ nhìn vào interface chưa đủ để biết:

- id có được rỗng, viết hoa hoặc thay đổi theo thời gian không?
- name có được null không?
- greet có được trả về null không?
- Provider có được lưu trạng thái người dùng không?
- Consumer sẽ làm gì nếu hai provider trả về cùng id?

Những nội dung này cần được ghi thành contract rõ ràng.

## 4. Viết Javadoc ngay cạnh SPI

Javadoc là điểm tham chiếu gần nhất với người triển khai. Có thể định nghĩa lại interface với hợp đồng cụ thể:

~~~java
package com.example.greeting.spi;

import java.util.Objects;

/**
 * Extension point for language-specific greetings.
 *
 * <p>Implementations must be thread-safe after construction.
 * Returned values must never be null.
 *
 * @implSpec Providers must not perform network access in the
 * constructor and must return a stable identifier for the
 * lifetime of the provider instance.
 */
public interface GreetingService {

    /**
     * Stable provider identifier in lowercase ASCII.
     *
     * @return a non-empty id matching [a-z][a-z0-9-]*
     */
    String id();

    /**
     * Creates a greeting for one non-empty name.
     *
     * @param name user-visible name, never null or blank
     * @return a non-null and non-blank greeting
     * @throws NullPointerException if name is null
     * @throws IllegalArgumentException if name is blank
     */
    String greet(String name);

    /**
     * Shared input validation used by implementations.
     */
    static void validateName(String name) {
        Objects.requireNonNull(name, "name");
        if (name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
    }
}
~~~

Ví dụ sử dụng Javadoc để truyền đạt ràng buộc; phần nội dung cụ thể là quyết định thiết kế của SPI này, không phải quy tắc mặc định của mọi service.

Có thể bổ sung @since cho từng method, ví dụ @since 1.1, khi interface được tiến hóa. Với method có hành vi mặc định, mô tả rõ việc override có được phép hay không và trạng thái nào được duy trì.

Javadoc nên được xem là nguồn hợp đồng gần code; README/module documentation có thể giải thích cách đăng ký, cấu trúc dự án và luồng vận hành.

## 5. Đặc tả đầu vào và đầu ra phải kiểm chứng được

Mỗi method public trong SPI nên có bảng hợp đồng:

| Phương thức | Điều kiện đầu vào | Kết quả bắt buộc | Ngoại lệ |
| --- | --- | --- | --- |
| id() | Không có tham số | Chuỗi non-null, không rỗng, ổn định, dạng lowercase ASCII id | Không phát sinh lỗi trong điều kiện vận hành bình thường |
| greet(name) | name khác null và không blank | Chuỗi non-null, không blank; không sửa dữ liệu đầu vào | NullPointerException nếu null, IllegalArgumentException nếu blank |

Khi contract có rule về định dạng, hãy ghi rõ ví dụ đúng và sai:

~~~text
Provider id hợp lệ: en, vi, en-us
Provider id không hợp lệ: "", "EN", "en us", "123"
~~~

Không nên dùng mô tả mơ hồ như “trả về chuỗi hợp lệ” nếu consumer cần biết cách xử lý kết quả.

Một provider có thể trả lời bằng tiếng Việt hay tiếng Anh, nhưng cần giữ cùng quy tắc về null, chuỗi rỗng và ngoại lệ. Chính các bất biến chung này giúp consumer thay provider mà không sửa logic.

## 6. Provider mẫu và trách nhiệm cài đặt

Một implementation được đặt trong module provider riêng:

~~~java
module com.example.greeting.english {
    requires com.example.greeting.api;

    provides com.example.greeting.spi.GreetingService
        with com.example.greeting.english.EnglishGreetingProvider;
}
~~~

Provider:

~~~java
package com.example.greeting.english;

import com.example.greeting.spi.GreetingService;

public final class EnglishGreetingProvider
        implements GreetingService {

    public EnglishGreetingProvider() {
        // Lightweight initialization only.
    }

    @Override
    public String id() {
        return "en";
    }

    @Override
    public String greet(String name) {
        GreetingService.validateName(name);
        return "Hello, " + name.strip() + "!";
    }
}
~~~

Các điểm hợp đồng được thực hiện:

- id ổn định trong vòng đời instance và có format đúng.
- greet xác thực null/blank theo quy định.
- greet trả về chuỗi non-null, non-blank.
- Provider không lưu trạng thái thay đổi theo mỗi lời gọi, nên thuận lợi cho thread safety.
- Constructor không làm I/O nặng.

Provider không cần exports package cài đặt chỉ để ServiceLoader tìm thấy nó. Chỉ thị provides ... with ... đăng ký lớp cung cấp dịch vụ; package implementation có thể giữ không export.

Trong ví dụ này, provider class public và có public constructor không tham số. JPMS cũng hỗ trợ cơ chế provider method theo các điều kiện được đặc tả, nhưng cần tài liệu hóa rõ lựa chọn khởi tạo nếu dùng cơ chế đó.

## 7. Consumer khai báo uses

Module ứng dụng dùng service:

~~~java
module com.example.greeting.app {
    requires com.example.greeting.api;

    uses com.example.greeting.spi.GreetingService;
}
~~~

Mã consumer:

~~~java
package com.example.greeting.app;

import com.example.greeting.spi.GreetingService;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        for (GreetingService provider : loader) {
            System.out.println(
                    provider.id() + ": " + provider.greet("Lan"));
        }
    }
}
~~~

Đối với named module thực hiện ServiceLoader.load, chỉ thị uses nêu rõ module đó tiêu thụ loại service nào.

ServiceLoader có thể khám phá những provider phù hợp trong module configuration hoặc phạm vi nạp hiện hành. Nhưng việc một JAR nằm trên module path không tự chứng minh rằng provider module đã được resolve.

Vì vậy, tài liệu triển khai phải ghi rõ module provider cần được đưa vào module graph bằng cách nào.

## 8. Đảm bảo provider nằm trong module graph

Cấu trúc module:

~~~text
src/
├── com.example.greeting.api/
│   ├── module-info.java
│   └── com/example/greeting/spi/GreetingService.java
├── com.example.greeting.english/
│   ├── module-info.java
│   └── com/example/greeting/english/EnglishGreetingProvider.java
└── com.example.greeting.app/
    ├── module-info.java
    └── com/example/greeting/app/Main.java
~~~

Có thể biên dịch theo module source path:

~~~bash
javac --module-source-path src \
    -d out \
    -m com.example.greeting.api,com.example.greeting.english,com.example.greeting.app
~~~

Khi chạy, đưa provider module thành một root module bổ sung:

~~~bash
java --module-path out \
    --add-modules com.example.greeting.english \
    -m com.example.greeting.app/com.example.greeting.app.Main
~~~

Lệnh --add-modules ở đây giúp module provider được resolve trong cấu hình chạy minh họa. Nếu dùng hệ thống tạo layer có service binding, hoặc cấu hình launcher khác, cách đưa provider vào graph sẽ khác.

Trên Windows, dấu phân tách module path phụ thuộc hệ điều hành; trong ví dụ chỉ có một phần tử out nên không cần phân tách nhiều đường dẫn.

## 9. ServiceLoader không bảo đảm thứ tự chọn provider theo mong muốn nghiệp vụ

Nếu hệ thống có nhiều provider, không nên ngầm hiểu provider đầu tiên từ ServiceLoader là provider mặc định ổn định. Thứ tự khám phá có thể phụ thuộc module configuration, class loader và cách đóng gói.

Một contract tốt cần định nghĩa cách chọn rõ ràng, ví dụ chọn theo id:

~~~java
import com.example.greeting.spi.GreetingService;
import java.util.ServiceLoader;

public final class GreetingLookup {
    public static GreetingService require(String id) {
        GreetingService result = null;

        for (GreetingService provider :
                ServiceLoader.load(GreetingService.class)) {

            if (!provider.id().equals(id)) {
                continue;
            }

            if (result != null) {
                throw new IllegalStateException(
                        "Duplicate provider id: " + id);
            }

            result = provider;
        }

        if (result == null) {
            throw new IllegalStateException(
                    "No provider for id: " + id);
        }

        return result;
    }
}
~~~

Trong ví dụ này:

- Provider id phải duy nhất trong tập provider được consumer khám phá.
- Không có provider phù hợp là lỗi cấu hình có thể báo rõ.
- Hai provider trùng id là lỗi thay vì chọn ngẫu nhiên.

Nếu muốn ưu tiên provider theo priority, phải tài liệu hóa cách tính priority, tie-breaker, trường hợp thiếu metadata và việc có chấp nhận thay đổi mặc định giữa các lần chạy hay không.

## 10. Tài liệu hóa cách phát hiện và khởi tạo provider

ServiceLoader là một cơ chế lazy loading: provider thường được tìm và tạo khi duyệt loader hoặc gọi API tương ứng. Chi tiết vòng đời cần được hiểu trong phạm vi mỗi ServiceLoader instance.

Tài liệu SPI nên nói rõ:

- Constructor có được làm I/O không, có giới hạn thời gian hay không?
- Có được ném exception khi thiếu cấu hình không?
- Có được đọc environment variables hay system properties không?
- Provider có được phép bắt đầu thread khi khởi tạo không?
- Có cần một cơ chế shutdown/close không?
- Consumer có giữ lại instance lâu dài không?
- Có thể có nhiều ServiceLoader hoặc provider instance đồng thời không?

Với ví dụ GreetingService, hợp đồng có thể quy định constructor nhanh, không chạm mạng và không tạo thread; provider không có tài nguyên phải đóng. Nếu cần kết nối dữ liệu hoặc thread pool, nên định nghĩa lifecycle API rõ ràng.

Đừng mặc định ServiceLoader sẽ tự gọi close() hoặc dừng thread do provider tạo ra.

## 11. Classpath provider và JPMS provider khác nhau

ServiceLoader có thể được dùng trong cả ứng dụng modular và non-modular, nhưng cách đăng ký phụ thuộc cấu hình.

Named module explicit thường đăng ký bằng:

~~~java
provides com.example.greeting.spi.GreetingService
    with com.example.greeting.english.EnglishGreetingProvider;
~~~

Trong ứng dụng classpath truyền thống, provider có thể được khai báo qua file service configuration:

~~~text
META-INF/services/com.example.greeting.spi.GreetingService
~~~

Nội dung file là tên đầy đủ của provider class:

~~~text
com.example.greeting.english.EnglishGreetingProvider
~~~

Tài liệu cần nói rõ một artifact được hỗ trợ trên module path, classpath hay cả hai. Không nên giả định cùng một cơ chế đăng ký hoạt động hệt nhau trên mọi cách đóng gói.

Nếu JAR là automatic module trên module path, việc đăng ký và tên module được suy ra theo các quy tắc JPMS tương ứng. Hãy kiểm tra artifact thực tế, thay vì suy đoán tên module từ tên file.

## 12. Provider method và constructor: phải ghi rõ cơ chế

Trong explicit named module, ServiceLoader có thể tạo provider thông qua constructor phù hợp hoặc một public static provider method có tên provider theo quy tắc API.

Khi chọn cơ chế provider method, lớp được liệt kê sau provides có thể đóng vai trò factory cung cấp đối tượng service. Cách này phù hợp khi cần kiểm soát construction.

Một hướng mô tả:

~~~java
public final class GreetingProviderFactory {
    public static GreetingService provider() {
        return new EnglishGreetingProvider();
    }
}
~~~

Descriptor của module provider chỉ tới lớp factory:

~~~java
provides com.example.greeting.spi.GreetingService
    with com.example.greeting.english.GreetingProviderFactory;
~~~

Ví dụ giả định factory và implementation thuộc cùng module và những class liên quan có cấu hình đúng. Với explicit module, lớp factory không nhất thiết tự implement service interface nếu cung cấp phương thức provider() hợp lệ.

Những điểm cần ghi vào tài liệu:

- Provider dùng public constructor không tham số hay provider method?
- Provider method trả về kiểu nào và xử lý lỗi như thế nào?
- Mỗi lần gọi tạo một instance mới hay trả về instance chia sẻ?
- Có cần dependency injection hoặc cấu hình bên ngoài không?

Đối với automatic module, không dựa vào cơ chế provider method như một đặc tính chung; nên kiểm tra các yêu cầu riêng đối với provider class.

## 13. Khai báo thread safety như một phần contract

Nếu consumer có thể gọi service từ nhiều thread, tài liệu phải ghi rõ:

| Chính sách | Ý nghĩa |
| --- | --- |
| Thread-safe | Một provider instance có thể xử lý nhiều lời gọi đồng thời đúng đắn. |
| Thread-confined | Một instance chỉ được dùng từ một thread xác định. |
| Caller synchronized | Consumer phải đồng bộ khi chia sẻ instance. |
| Immutable | Trạng thái sau construction không đổi, thường giúp thực hiện thread safety. |

Ví dụ GreetingService có thể yêu cầu mọi implementation thread-safe. Điều đó có nghĩa các provider không được dùng mutable state không được bảo vệ khi greet() được gọi đồng thời.

Nếu một provider thực sự cần mutable cache, nó phải bảo đảm thread safety của cache hoặc triển khai chiến lược đồng bộ phù hợp.

Không nên ghi “thread-safe” chỉ vì class có final modifier. Final class không tự bảo đảm các field bên trong bất biến hoặc các thao tác đồng thời an toàn.

## 14. Quy định thời gian chạy, timeout và blocking

Một SPI không chỉ có type contract mà còn có operational contract.

Một provider có thể có hành vi:

- Tính toán hoàn toàn trong bộ nhớ, thường trả kết quả nhanh.
- Đọc file cục bộ, có thể block.
- Gọi API mạng, có thể timeout hoặc thất bại.
- Ghi dữ liệu, có side effect.

Consumer cần biết để quyết định có thể gọi trên event-loop thread, UI thread hay cần worker pool.

Với GreetingService, có thể quy định greet() không thực hiện I/O, không block chờ external service và không sửa global state. Khi muốn hỗ trợ remote provider, nên cân nhắc một SPI bất đồng bộ riêng hoặc cập nhật tài liệu để chỉ rõ timeout và chính sách hủy.

Nếu contract không quy định thời gian tuyệt đối, ít nhất cần phân loại phương thức blocking/non-blocking, khả năng timeout và trách nhiệm retry.

## 15. Exception contract: phân biệt lỗi provider và lỗi consumer

Tài liệu nên phân biệt:

1. **Lỗi đầu vào** do caller vi phạm precondition: NullPointerException hoặc IllegalArgumentException.
2. **Lỗi nghiệp vụ** được định nghĩa bởi SPI: có thể là exception riêng hoặc kiểu kết quả lỗi.
3. **Lỗi môi trường** của provider: I/O, network, quyền truy cập hoặc cấu hình.
4. **Lỗi khám phá/khởi tạo** khi ServiceLoader không thể load provider: ServiceConfigurationError.

Ví dụ:

~~~java
try {
    for (GreetingService provider :
            ServiceLoader.load(GreetingService.class)) {
        System.out.println(provider.greet("Lan"));
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println(
            "Unable to discover or instantiate service provider");
    throw error;
}
~~~

ServiceConfigurationError là Error, không phải checked Exception thông thường. Consumer cần quyết định có fail-fast, báo cấu hình không hợp lệ hay cô lập provider; không nên nuốt lỗi một cách âm thầm rồi khẳng định không có provider.

Contract cũng cần xác định provider được phép ném những runtime exception nào trong hoạt động bình thường. Nếu provider được phép trả kết quả lỗi thay vì ném exception, hãy tài liệu hóa bất biến của kiểu kết quả.

## 16. Khác biệt giữa lỗi ServiceLoader và lỗi method nghiệp vụ

Hai lỗi này xảy ra ở hai giai đoạn:

- **Discovery/instantiation:** module descriptor không hợp lệ, provider class không tạo được, constructor/provider method thất bại hoặc thiếu dependency. ServiceLoader có thể phát sinh ServiceConfigurationError.
- **Invocation:** provider đã được tạo nhưng greet() ném IllegalArgumentException, NullPointerException hoặc exception khác theo contract.

Khi ghi log, nên giữ module name, provider class và id nếu đã có instance. Điều này giúp xác định provider bị lỗi mà không phải quét toàn bộ source.

Không nên gọi provider.id() trong đường xử lý lỗi nếu chính id() có thể thất bại không kiểm soát. Contract cần quy định id() ổn định, không có side effect và không ném lỗi trong trạng thái bình thường.

## 17. ServiceLoader trong ModuleLayer riêng

Ứng dụng plugin có thể tạo một ModuleLayer riêng chứa provider. Khi đó nên dùng phương thức:

~~~java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(pluginLayer, GreetingService.class);
~~~

Trong ví dụ, pluginLayer là đối tượng ModuleLayer đã được tạo trước đó, còn GreetingService.class là kiểu service chia sẻ với host.

Tài liệu cần ghi rõ:

- Provider được resolve ở layer nào và layer cha nào liên quan.
- API service được nạp từ module/layer nào.
- Plugin layer có gắn đúng provider module vào graph không.
- Host và plugin có dùng cùng class identity của GreetingService không.
- Khi reload plugin, host tạo lại layer/loader và dọn tài nguyên như thế nào.

Nếu host và plugin mỗi bên nạp một bản sao GreetingService bằng hai class loader không tương thích, provider có thể không tương thích với service type mà host đang yêu cầu. Không nên coi tên class giống nhau là đủ; class loader định nghĩa type cũng là một phần của runtime identity.

## 18. Tài liệu hóa khả năng tương thích khi nâng cấp SPI

Thay đổi interface có thể làm hỏng provider bên ngoài:

- Thêm abstract method khiến provider cũ không đáp ứng interface mới.
- Đổi kiểu tham số, kiểu trả về hoặc tên method có thể phá source/binary compatibility.
- Thay đổi nghĩa của một phương thức có thể gây lỗi hành vi dù code vẫn biên dịch.
- Thắt chặt quy tắc null hoặc exception có thể làm provider cũ không còn hợp lệ.

Khi cần tiến hóa SPI, một hướng là thêm default method với hành vi tương thích:

~~~java
public interface GreetingService {
    String id();

    String greet(String name);

    default boolean supportsFormalGreeting() {
        return false;
    }
}
~~~

Ví dụ này cho phép implementation cũ tiếp tục sử dụng giá trị mặc định của method mới, nhưng cần kiểm tra compatibility theo chính sách versioning của thư viện.

Tài liệu version nên nêu:

- Phiên bản đầu tiên giới thiệu method hoặc rule mới.
- Provider tối thiểu được hỗ trợ từ phiên bản nào.
- Những thay đổi breaking change và hướng migration.
- Thời hạn loại bỏ các API deprecated, nếu có.

Không mặc định rằng thay đổi nhỏ trong code đồng nghĩa thay đổi không ảnh hưởng người viết provider.

## 19. Quy ước lựa chọn provider khi có nhiều implementation

Trong hệ thống mở rộng, nhiều provider có thể cùng hỗ trợ một khả năng. Contract nên chọn một chính sách minh bạch:

| Tình huống | Chính sách có thể chọn |
| --- | --- |
| Không có provider | Báo lỗi cấu hình hoặc dùng fallback đã tài liệu hóa. |
| Đúng một provider phù hợp | Sử dụng provider đó. |
| Nhiều provider khác id | Chọn bằng id do người dùng hoặc cấu hình chỉ định. |
| Nhiều provider cùng id | Báo trùng id; không dựa vào thứ tự ServiceLoader. |
| Provider lỗi khi khởi tạo | Fail-fast hoặc cô lập lỗi theo chính sách đã công bố. |
| Provider lỗi khi gọi | Propagate, retry hoặc fallback theo error contract, không tùy tiện. |

Một consumer có thể cung cấp cấu hình explicit id hoặc danh sách priority. Điều quan trọng là provider author phải hiểu cách implementation được chọn.

Nếu API yêu cầu id duy nhất, cần giải thích phạm vi duy nhất: trong một JVM, một module layer, hay một tập plugin được tải trong phiên chạy.

## 20. Tài liệu bảo mật và quản lý tài nguyên

Provider có thể do tổ chức khác viết. Contract cần nêu rõ quyền và tài nguyên mà host cho phép:

- Có được đọc system property hoặc environment variable không?
- Có được truy cập credential, key hoặc file hệ thống không?
- Có được mở socket hoặc thực hiện network call không?
- Có được khởi tạo thread hoặc executor không?
- Có yêu cầu đóng resource khi plugin unload không?
- Provider có được giữ dữ liệu người dùng sau lời gọi không?

Không nên xem JPMS hoặc class loader là sandbox bảo mật. Named module giúp kiểm soát dependency và access tới package, nhưng mã provider vẫn chạy trong cùng tiến trình với quyền hệ điều hành tương ứng.

Với provider không đáng tin cậy, phải cân nhắc cách ly ở mức tiến trình và các cơ chế kiểm soát riêng. Tài liệu SPI nên nói rõ giới hạn tin cậy, không tạo kỳ vọng sai về khả năng sandbox của ServiceLoader.

## 21. Contract test cho provider

Một provider contract hữu ích nên có bộ test chung. Mọi implementation phải vượt qua những test mô tả bất biến của SPI.

Ví dụ kiểm thử không phụ thuộc framework:

~~~java
import com.example.greeting.spi.GreetingService;

public final class GreetingContractTest {
    public static void assertContract(GreetingService service) {
        String id = service.id();

        if (id == null || !id.matches("[a-z][a-z0-9-]*")) {
            throw new AssertionError("Invalid provider id");
        }

        String greeting = service.greet("Lan");
        if (greeting == null || greeting.isBlank()) {
            throw new AssertionError("Blank greeting");
        }

        try {
            service.greet(null);
            throw new AssertionError(
                    "Expected NullPointerException");
        } catch (NullPointerException expected) {
            // Contract satisfied.
        }

        try {
            service.greet("  ");
            throw new AssertionError(
                    "Expected IllegalArgumentException");
        } catch (IllegalArgumentException expected) {
            // Contract satisfied.
        }
    }
}
~~~

Trong test thực tế, có thể dùng JUnit và bổ sung những test về concurrency, lifecycle, exception contract và tương thích với các version đã phát hành.

Bộ test nên được chạy với từng provider sau khi build, và với ứng dụng host có ServiceLoader để kiểm tra cả đăng ký module. Unit test truyền implementation trực tiếp chưa đủ để phát hiện lỗi provides/uses hoặc module graph.

## 22. Test đăng ký provider qua ServiceLoader

Có thể kiểm tra provider được khám phá trong cấu hình runtime thực tế:

~~~java
import com.example.greeting.spi.GreetingService;
import java.util.HashSet;
import java.util.ServiceLoader;
import java.util.Set;

public final class ProviderDiscoveryCheck {
    public static void main(String[] args) {
        Set<String> ids = new HashSet<>();
        int count = 0;

        for (GreetingService provider :
                ServiceLoader.load(GreetingService.class)) {

            GreetingContractTest.assertContract(provider);

            if (!ids.add(provider.id())) {
                throw new AssertionError(
                        "Duplicate provider id: " + provider.id());
            }

            count++;
        }

        if (count == 0) {
            throw new AssertionError(
                    "No GreetingService provider discovered");
        }
    }
}
~~~

Để chạy ví dụ với named module test, module chứa ProviderDiscoveryCheck cần requires tới service API và uses GreetingService. Đồng thời phải bảo đảm ít nhất một provider module được resolve vào graph.

Test này xác nhận cả hai mặt: provider tuân theo những ràng buộc được kiểm tra và cơ chế discovery tìm thấy implementation.

Nếu hệ thống cho phép cấu hình không provider, hãy chỉnh assertion count == 0 theo chính sách đã được tài liệu hóa.

## 23. Mẫu README service provider contract

Một README dành cho người viết plugin có thể dùng cấu trúc sau:

~~~text
# GreetingService Provider Contract

Module API: com.example.greeting.api
Service type: com.example.greeting.spi.GreetingService
Minimum runtime: Java 17 (theo chính sách dự án)

1. Purpose
   - Cung cấp lời chào theo một ngôn ngữ.

2. Registration
   - Module provider requires com.example.greeting.api.
   - Khai báo provides GreetingService with Implementation.
   - Provider phải có constructor/provider method phù hợp.

3. Method contract
   - id(): non-null, non-empty, lowercase ASCII, stable.
   - greet(name): name non-null và non-blank;
     kết quả non-null và non-blank.

4. Runtime
   - Provider thread-safe.
   - Constructor không gọi mạng hay khởi tạo thread.
   - Method greet không có side effect.

5. Failure
   - Null input -> NullPointerException.
   - Blank input -> IllegalArgumentException.
   - Discovery/config error -> xử lý theo host policy.

6. Selection
   - Consumer chọn theo id.
   - Trùng id -> lỗi cấu hình.

7. Testing
   - Chạy contract test trên provider.
   - Chạy ServiceLoader discovery test trên module path.

8. Compatibility
   - Ghi thay đổi breaking theo phiên bản.
   - Công bố chính sách migration.
~~~

Đây là mẫu, không phải một file độc lập của dự án. Khi áp dụng, thay thông tin minh họa bằng module name, Java version và chính sách thực tế.

## 24. Module documentation và cách liên kết tới contract

Trong dự án có nhiều module, nên đặt liên kết contract ở những vị trí mà provider author dễ tìm:

- Javadoc của service interface, nhất là @implSpec và @implNote.
- package-info.java của package spi để mô tả extension points.
- module-info.java Javadoc ở module API hoặc module host.
- README của thư viện/plugin SDK.
- Tài liệu phát hành và migration guide cho thay đổi version.

Ví dụ package-info.java:

~~~java
/**
 * Service Provider Interfaces for greeting extensions.
 *
 * <p>Provider authors should implement GreetingService
 * according to its method and lifecycle contract.
 */
package com.example.greeting.spi;
~~~

Hãy duy trì một nguồn mô tả chuẩn, sau đó liên kết từ những nơi khác thay vì sao chép các quy định có thể mâu thuẫn. Khi thay đổi contract, cập nhật Javadoc, test fixtures và hướng dẫn migration cùng một lần phát hành.

## 25. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy provider | Provider module chưa resolve hoặc thiếu provides/uses | Kiểm tra descriptor và cách khởi chạy. |
| ServiceConfigurationError | Provider class/factory không hợp lệ, thiếu dependency hoặc lỗi khởi tạo | Đọc root cause; xác nhận cơ chế constructor/provider method. |
| Provider được nạp nhưng host không dùng | Selector không khớp id/capability hoặc có policy ưu tiên | Đọc selection contract và log id. |
| Hai provider cùng id | Hợp đồng uniqueness không được thực thi | Báo cấu hình trùng; thêm contract test. |
| NullPointerException bất ngờ | Provider không tuân theo null contract | Rà soát Javadoc và test ràng buộc. |
| Lỗi dưới tải đồng thời | Provider không đạt thread safety contract | Cố định shared state hoặc thay mô hình instance. |
| ClassCastException giữa plugin và host | API service được nạp từ các loader không tương thích | Chia sẻ service API từ parent layer/loader phù hợp. |
| Phải export package implementation để load provider | Hiểu nhầm cơ chế provides | Đăng ký provider trong descriptor, giữ implementation không export nếu không cần. |
| Dùng provider đầu tiên đôi khi sai | Phụ thuộc thứ tự discovery | Chọn theo id/priority có quy tắc xác định. |

## 26. Quy trình chẩn đoán và hướng dẫn vận hành

Khi host không tìm thấy hoặc không dùng được provider:

1. Kiểm tra JAR hoặc output thực sự được triển khai.
2. Chạy jar --describe-module trên provider JAR để xem module name và provides.
3. Xác nhận module consumer khai báo uses service type.
4. Xác nhận module provider requires đúng module API và provides đúng service type.
5. Kiểm tra provider module đã được resolve vào runtime configuration.
6. Kiểm tra API service được chia sẻ cùng class identity giữa host và plugin.
7. Ghi lại provider id sau khi khởi tạo và kiểm tra selection policy.
8. Nếu gặp ServiceConfigurationError, xác định nguyên nhân khởi tạo hoặc thiếu dependency.
9. Chạy contract test, đặc biệt các trường hợp null/blank, duplicate id và concurrency.
10. So sánh version SPI của host với version provider được build.

Lệnh kiểm tra descriptor:

~~~bash
jar --describe-module --file plugins/greeting-provider.jar
~~~

Lệnh quan sát resolution khi chạy module application:

~~~bash
java --show-module-resolution \
    --module-path out \
    --add-modules com.example.greeting.english \
    -m com.example.greeting.app/com.example.greeting.app.Main
~~~

Các tên artifact và module trong ví dụ là minh họa; cần thay bằng dự án thực tế.

## 27. Nguyên tắc duy trì service provider contract

- Đặt service type trong package API/SPI được export và có module name rõ ràng.
- Ghi Javadoc cho mọi method theo precondition, postcondition, nullability và exception.
- Công bố quy tắc id, lựa chọn provider và chính sách không có/trùng provider.
- Tách trách nhiệm provider khỏi việc orchestration và lựa chọn của host.
- Nêu rõ constructor/provider method, lifecycle, resource ownership và thread safety.
- Không phụ thuộc vào thứ tự provider mà ServiceLoader trả về.
- Nêu rõ module graph, cách resolve provider và class identity trong plugin layer.
- Không mặc định ServiceLoader đóng tài nguyên hoặc sandbox provider.
- Cung cấp contract test chung cho các provider bên thứ ba.
- Quản lý thay đổi SPI bằng versioning, migration và chính sách compatibility.
- Đồng bộ README, Javadoc và test khi hợp đồng thay đổi.

Service provider contract là cầu nối giữa một extension point trong code và những cam kết mà host có thể dựa vào. JPMS cho phép khai báo rõ uses/provides và giữ package implementation được đóng gói; tài liệu contract bổ sung điều mà descriptor không thể biểu đạt: hành vi, lỗi, vòng đời và khả năng tương thích của từng provider.

## 28. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao chỉ có provides ... with ... chưa đủ để khẳng định provider tương thích?

Vì provides chỉ đăng ký implementation cho service type. Nó không kiểm tra nullability, quy tắc id, thread safety, lifecycle hay ý nghĩa của method.

**Câu 2:** Mô-đun consumer cần khai báo gì khi dùng ServiceLoader cho một service type?

Named consumer module cần khai báo uses service.type và requires tới module chứa service API khi sử dụng kiểu đó.

**Câu 3:** Provider có cần exports package implementation để ServiceLoader tạo instance không?

Không chỉ vì nhu cầu đăng ký. Với explicit named module, provides cho phép cơ chế service loading tìm provider theo hợp đồng module; package implementation có thể không export.

**Câu 4:** Nếu hai provider cùng trả về id "en", consumer nên làm gì?

Theo contract minh họa, consumer báo lỗi cấu hình trùng id thay vì phụ thuộc vào thứ tự duyệt ServiceLoader.

**Câu 5:** Vì sao không nên xem provider đầu tiên là mặc định ổn định?

ServiceLoader không cam kết thứ tự business priority. Host nên chọn theo id, priority hoặc chính sách được tài liệu hóa.

**Câu 6:** Test chỉ gọi new EnglishGreetingProvider() đã đủ chứng minh module provider hoạt động chưa?

Chưa. Test trực tiếp kiểm tra logic implementation nhưng không xác nhận module descriptor, root resolution và ServiceLoader discovery. Cần kiểm tra tích hợp trong runtime modular.

**Câu 7:** Khi thêm một abstract method vào SPI đã phát hành, rủi ro là gì?

Provider cũ có thể không cài đặt method mới và trở nên không tương thích. Cần cân nhắc default method, adapter hoặc migration/versioning có chủ đích.

**Câu 8:** Nếu provider chạy trong module layer riêng, yếu tố nào ngoài tên đầy đủ của interface cần giống với host?

Class identity của service type: cùng định nghĩa được chia sẻ qua class loader/module layer phù hợp. Hai class cùng tên từ loader khác nhau không nhất thiết thay thế được nhau.
