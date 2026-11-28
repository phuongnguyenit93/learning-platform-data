# Nhiều provider cùng tồn tại: thứ tự phát hiện phụ thuộc triển khai và cách tránh lựa chọn mơ hồ

> **Chương:** Resolver SPI  
> **Áp dụng:** Java 18 trở lên, bao gồm các JDK hiện đại còn hỗ trợ `java.net.spi.InetAddressResolverProvider`.

## 1. Vấn đề: một ứng dụng có nhiều nhà cung cấp phân giải tên

Từ Java 18, **Internet-Address Resolution SPI** (JEP 418) cho phép tích hợp một bộ phân giải địa chỉ riêng thông qua `java.net.spi.InetAddressResolverProvider`. Khi ứng dụng gọi `InetAddress.getByName(...)`, `InetAddress.getAllByName(...)` hoặc những API dùng cơ chế phân giải tên của `InetAddress`, JVM có thể sử dụng `InetAddressResolver` do provider được cài đặt cung cấp.

Trong một ứng dụng thực tế, nhiều thư viện hoặc module có thể đồng thời đóng gói provider. Ví dụ:

- `corp-dns.jar` mang provider giải quyết tên trong mạng doanh nghiệp.
- `observability-dns.jar` mang provider ghi thông tin chẩn đoán DNS.
- Một module khác khai báo provider để thay đổi chiến lược tra cứu trong môi trường kiểm thử.

Nếu nhiều provider cùng xuất hiện trên đường chạy, việc giả định provider nào được dùng dựa trên **tên lớp, tên JAR, thứ tự dependency hoặc kết quả liệt kê của `ServiceLoader`** có thể khiến ứng dụng chạy khác nhau khi đổi cách đóng gói, môi trường hoặc bản JDK.

**Nguyên tắc quan trọng:** hợp đồng API của `InetAddressResolverProvider` không cung cấp cơ chế ưu tiên portable để ứng dụng ấn định provider thắng bằng tên, trọng số hoặc vị trí trong danh sách. Không xây dựng tính đúng đắn của ứng dụng trên thứ tự lựa chọn khi có nhiều provider.

## 2. Phân biệt phát hiện provider và sử dụng resolver

| Khái niệm | Ý nghĩa | Điều có thể dựa vào |
| --- | --- | --- |
| **Đăng ký** | Đưa provider vào nơi Java có thể tìm thấy, ví dụ `provides ... with` ở module hoặc tệp dịch vụ trên classpath | Có thể kiểm soát nội dung artifact và runtime image |
| **Phát hiện** | Cơ chế nạp dịch vụ nhận diện các provider khả dụng | Có thể kiểm tra provider nào hiện diện; không suy ra ưu tiên ứng dụng sẽ nhận được |
| **Lựa chọn** | Cơ chế của `InetAddress` quyết định resolver được sử dụng | Khi nhiều provider cùng tồn tại, không có thứ tự lựa chọn ổn định được bảo đảm bởi API |
| **Tra cứu** | Resolver đã chọn thực thi `lookupByName` hoặc `lookupByAddress` | Có thể quan sát lời gọi thực tế bằng instrumentation trong resolver |

SPI này liên quan đến hai kiểu chính:

- `InetAddressResolverProvider`: lớp cơ sở để cung cấp resolver; triển khai `name()` và `get(Configuration)`.
- `InetAddressResolver`: giao diện thực hiện phân giải tên sang địa chỉ qua `lookupByName(...)`, và địa chỉ sang tên qua `lookupByAddress(...)`.

`Configuration.builtinResolver()` cung cấp resolver tích hợp sẵn của nền tảng để provider có thể ủy quyền hoặc làm phương án dự phòng. Nếu không cài đặt provider tùy chỉnh, `InetAddress` dùng cơ chế phân giải mặc định của nền tảng.

**Lưu ý về phạm vi:** việc nhiều địa chỉ IPv4/IPv6 được trả về từ *một lần tra cứu* là vấn đề thứ tự địa chỉ và `LookupPolicy`; nó khác với việc *nhiều provider* cùng được phát hiện. Đừng trộn hai loại thứ tự này.

## 3. Provider đến từ đâu?

### 3.1. Ứng dụng dùng Java Platform Module System (JPMS)

Trong `module-info.java`, module cung cấp dịch vụ có thể khai báo:

```java
module vn.example.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with vn.example.resolver.OnlyResolverProvider;
}
```

Provider cần được đóng gói và có thể được cơ chế dịch vụ khởi tạo theo quy tắc của JPMS. Việc có nhiều module cùng `provides` làm tăng số provider khả dụng, nhưng **không tạo ra thứ tự ưu tiên do ứng dụng kiểm soát**.

### 3.2. Ứng dụng dùng classpath

Với JAR chạy trên classpath, tệp đăng ký dịch vụ có đường dẫn:

```text
META-INF/services/java.net.spi.InetAddressResolverProvider
```

Nội dung của tệp có thể là tên lớp provider:

```text
vn.example.resolver.OnlyResolverProvider
```

Một ứng dụng có nhiều JAR chứa tệp dịch vụ này có thể phát hiện nhiều provider. Khi tạo fat JAR hoặc thực hiện shading, hãy kiểm tra việc **gộp các tệp `META-INF/services`**: thao tác gộp sai có thể làm mất provider hoặc giữ lại provider không mong muốn. Cả hai đều có thể khiến việc triển khai khác kết quả dự kiến.

### 3.3. Vì sao không nên phụ thuộc vào thứ tự?

Ngay cả khi một lần chạy thấy provider A trước B, điều đó không chứng minh A luôn được chọn trên mọi JVM hoặc kiểu đóng gói. Thứ tự tìm thấy dịch vụ có thể chịu ảnh hưởng của cách tổ chức classpath, module path, class loader và chi tiết triển khai. Ngoài ra, thứ tự do công cụ chẩn đoán liệt kê **không phải cam kết** về cách `InetAddress` chọn provider.

Đặc biệt, `name()` của provider là tên nhận diện phục vụ SPI, **không phải** tham số `priority` hay cơ chế so sánh tên để phân xử nhiều provider. Không đặt tên `000-first`, `primary` hoặc tương tự với kỳ vọng Java sẽ tự ưu tiên.

## 4. Cách thiết kế không mơ hồ: một provider duy nhất, lựa chọn chiến lược bên trong

Giải pháp đơn giản và có thể kiểm soát là **đóng gói đúng một `InetAddressResolverProvider`** trong runtime và để provider đó chọn hành vi bằng cấu hình tường minh. Ví dụ sau minh họa hai chế độ: dùng resolver tích hợp của JVM hoặc bọc resolver tích hợp để ghi log lời gọi. Cả hai đều ủy quyền việc tra cứu thực tế cho resolver sẵn có, vì vậy không tự đặt ra quy tắc DNS hay làm sai `LookupPolicy`.

```java
package vn.example.resolver;

import java.net.UnknownHostException;
import java.net.InetAddress;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.stream.Stream;

public final class OnlyResolverProvider extends InetAddressResolverProvider {
    @Override
    public String name() {
        return "app-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();
        String mode = System.getProperty("app.resolver.mode", "platform");

        return switch (mode) {
            case "platform" -> builtin;
            case "trace" -> new InetAddressResolver() {
                @Override
                public Stream<InetAddress> lookupByName(
                        String host, LookupPolicy lookupPolicy)
                        throws UnknownHostException {
                    System.err.println("[resolver] lookupByName: " + host);
                    return builtin.lookupByName(host, lookupPolicy);
                }

                @Override
                public String lookupByAddress(byte[] address)
                        throws UnknownHostException {
                    System.err.println("[resolver] lookupByAddress");
                    return builtin.lookupByAddress(address);
                }
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported app.resolver.mode: " + mode);
        };
    }
}
```

Để dùng lớp trên, chỉ đăng ký **một** provider bằng `module-info.java` hoặc tệp `META-INF/services` như phần 3. Khi khởi động, chỉ định chế độ:

```bash
java -Dapp.resolver.mode=platform -cp "app.jar:resolver.jar" vn.example.Main
java -Dapp.resolver.mode=trace    -cp "app.jar:resolver.jar" vn.example.Main
```

> Các lệnh trên minh họa cú pháp classpath trên hệ điều hành dùng dấu `:`. Trên Windows, dấu phân cách classpath là `;`. `vn.example.Main` đại diện cho lớp khởi động của ứng dụng.

Trong ứng dụng thực, cấu hình có thể chuyển giữa một resolver nội bộ và resolver nền tảng. Khi tự hiện thực tra cứu, phải xử lý hợp đồng của `InetAddressResolver`, gồm ngoại lệ `UnknownHostException`, `LookupPolicy`, họ địa chỉ IPv4/IPv6 và hành vi tra cứu ngược. Ví dụ ở trên tránh các sai sót đó bằng cách ủy quyền toàn bộ việc phân giải.

**Vì sao cách này xác định được?** Runtime chỉ có một provider khả dụng, còn chế độ hoạt động được quyết định bằng thuộc tính `app.resolver.mode` có giá trị rõ ràng. Thay đổi thứ tự dependency không làm JVM phải chọn giữa hai provider cạnh tranh.

## 5. Khi bắt buộc phải phối hợp nhiều chiến lược

Nếu cần DNS doanh nghiệp, ghi log và fallback, hãy kết hợp chúng **bên trong một resolver** thay vì đăng ký ba `InetAddressResolverProvider` cạnh tranh:

```text
InetAddress
    |
    v
OnlyResolverProvider
    |  (cau hinh tuong minh)
    v
Resolver dieu phoi
    |-- tra cuu ten noi bo khi khop mien duoc quan ly
    |-- uy quyen cho builtinResolver() voi ten khac
    `-- ghi log/metric tren duong xu ly
```

Ví dụ, chính sách có thể là: tra cứu tên thuộc vùng `*.corp.example` qua nguồn nội bộ; các tên còn lại được ủy quyền cho `builtinResolver()`. Chính sách này phải được hiện thực có chủ đích và kiểm thử riêng, đặc biệt là các lỗi phân giải, tra cứu ngược, cache và trường hợp tên nội bộ không tồn tại. Không tự động giả định mọi lỗi từ DNS nội bộ đều nên chuyển sang DNS công cộng, vì điều đó có thể làm rò rỉ tên nội bộ.

Nếu nhiều thư viện cùng khai báo SPI, có hai lựa chọn thực tế: loại bỏ đăng ký của các provider không được chọn khỏi artifact triển khai, hoặc chuyển các thư viện thành thành phần được **một** provider điều phối gọi trực tiếp. Chỉ thay đổi thứ tự dependency để ép chọn provider là giải pháp mong manh.

## 6. Quan sát và kiểm chứng trên JVM thực tế

### 6.1. Kiểm tra provider hiện diện

Đoạn mã sau dùng `ServiceLoader` để hỗ trợ chẩn đoán các provider mà class loader được chỉ định có thể phát hiện:

```java
import java.net.spi.InetAddressResolverProvider;
import java.util.ServiceLoader;

public class ListResolverProviders {
    public static void main(String[] args) {
        ServiceLoader.load(
                InetAddressResolverProvider.class,
                ClassLoader.getSystemClassLoader())
            .stream()
            .map(ServiceLoader.Provider::type)
            .map(Class::getName)
            .forEach(System.out::println);
    }
}
```

Đây là **phép kiểm tra sự hiện diện**, không phải bằng chứng provider nào đã được `InetAddress` lựa chọn. Kết quả cũng phụ thuộc class loader và cách đóng gói đang kiểm tra; khi chạy dưới module system, cần xem thêm module nào có khai báo `provides`.

### 6.2. Kiểm tra resolver thực sự được gọi

1. Tạo bản triển khai mà runtime có đúng một provider, sau đó bật `-Dapp.resolver.mode=trace`.
2. Khởi động **JVM mới**, gọi `InetAddress.getByName("example.com")` hoặc một hostname dành riêng cho kiểm thử.
3. Quan sát log `[resolver] lookupByName: ...`; log này chứng minh phương thức trên resolver đã thực thi.
4. Chạy cùng bài kiểm thử với `platform` và đối chiếu kết quả. Nếu thay đổi danh sách provider ở bước thử nghiệm, tạo JVM mới cho từng cấu hình.

**Vì sao cần JVM mới?** Việc khởi tạo resolver và các cơ chế cache của `InetAddress` có thể khiến phép thử lặp trong cùng process không đi qua đường gọi tra cứu như dự đoán. Một cache hit không chứng minh provider đã biến mất; tương tự, chỉ thấy class của provider được nạp không chứng minh resolver của nó đã phục vụ một truy vấn.

### 6.3. Tình huống nên đưa vào kiểm thử triển khai

| Tình huống | Điều cần xác minh |
| --- | --- |
| Classpath/module path có đúng một provider | Resolver được gọi đúng với cấu hình dự kiến |
| Hai dependency vô tình cùng đăng ký SPI | Bước kiểm tra đóng gói phát hiện và chặn cấu hình mơ hồ |
| Fat JAR/shading thay đổi nội dung `META-INF/services` | Provider mong muốn còn được đăng ký, không bị nhân đôi hoặc bị loại mất |
| Cache trả kết quả không qua resolver trong lần gọi sau | Không kết luận nhầm về provider chỉ từ số lần ghi log |
| Tra cứu IPv4/IPv6 và tra cứu ngược | Provider tùy chỉnh tuân thủ `LookupPolicy` và hợp đồng API |
| Thay đổi bản JDK/runtime image | Kiểm tra lại danh sách provider và hành vi được quan sát |

Trong CI, có thể đặt một quy tắc kiểm tra artifact hoặc cấu hình module path: **chỉ một provider được phép xuất hiện** trong ứng dụng nếu kiến trúc của hệ thống yêu cầu resolver xác định. Quy tắc này đơn giản hơn việc cố suy ra thứ tự lựa chọn của JVM.

## 7. Các ngộ nhận thường gặp

- **“Provider được `ServiceLoader` in trước sẽ luôn được dùng.”** Sai: danh sách chẩn đoán không tạo ra hợp đồng lựa chọn cho `InetAddress`.
- **“`name()` là ưu tiên.”** Sai: không có giao ước SPI cho phép dùng tên để xác định thứ tự ưu tiên.
- **“Sắp xếp JAR hoặc dependency bảo đảm chọn đúng provider.”** Sai: thứ tự có thể thay đổi theo cơ chế đóng gói và triển khai.
- **“Cứ để nhiều provider rồi thử xem JVM chọn ai.”** Chưa đủ cho sản phẩm: quan sát một lần chạy không bảo đảm hành vi ổn định trên môi trường khác.
- **“Không có log nghĩa là provider không chạy.”** Chưa chắc: cache, thao tác tra cứu khác hoặc nhánh xử lý khác có thể khiến phép đo không ghi log.
- **“Tự cài đặt SPI thì không cần resolver mặc định.”** Không đúng trong mọi thiết kế: `Configuration.builtinResolver()` là cách hợp lệ để ủy quyền và giảm phạm vi tự hiện thực.

## 8. Ghi nhớ và tự kiểm tra

**Quy tắc triển khai:** đóng gói một `InetAddressResolverProvider`, cấu hình chiến lược rõ ràng, dùng `builtinResolver()` khi cần ủy quyền, rồi xác minh bằng lần tra cứu thực tế trong một JVM mới. Không suy ra ưu tiên từ thứ tự phát hiện.

**Câu hỏi tự kiểm tra:**

1. Hai JAR cùng khai báo `InetAddressResolverProvider`; vì sao thứ tự in ra của `ServiceLoader` không phải bằng chứng lựa chọn của JVM?
2. Nếu cần một resolver theo dõi DNS và một resolver nội bộ, làm sao để sử dụng cả hai mà vẫn bảo đảm chọn chiến lược có chủ đích?
3. Vì sao nên đo lời gọi `lookupByName` trong JVM mới khi kiểm thử thay đổi provider?
4. Với ứng dụng đóng gói thành fat JAR, cần kiểm tra điều gì trong `META-INF/services/java.net.spi.InetAddressResolverProvider`?

**Tài liệu chuẩn để đối chiếu khi nâng cấp JDK:** JEP 418 *Internet-Address Resolution SPI* và Javadoc của `java.net.spi.InetAddressResolverProvider`, `java.net.spi.InetAddressResolver`, `java.net.InetAddress` trên đúng phiên bản JDK chạy ứng dụng.
