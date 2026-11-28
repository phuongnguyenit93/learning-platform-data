# Thời điểm cài resolver toàn JVM: sau khởi tạo VM và khi phát sinh tra cứu đầu tiên

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **VM đã khởi tạo xong**, **lần tra cứu địa chỉ đầu tiên cần resolver** và **những lần tra cứu tiếp theo**.
- Giải thích lúc nào Java chọn một `InetAddressResolver` từ SPI và vì sao lựa chọn đó có phạm vi **toàn JVM**.
- Đăng ký `InetAddressResolverProvider` từ đầu tiến trình, quan sát thời điểm phương thức `get(...)` được gọi và tránh khởi tạo đệ quy.
- Phân tích các tình huống dễ nhầm: tra cứu trong giai đoạn khởi động, literal IP, bộ nhớ đệm địa chỉ, nhiều provider và thay đổi cấu hình khi ứng dụng đang chạy.

**Phạm vi:** Từ Java 18, JEP 418 cung cấp Internet-Address Resolution SPI với `java.net.spi.InetAddressResolverProvider` và `java.net.spi.InetAddressResolver`. Đây vẫn là cơ chế hiện hành trên các JDK mới có hỗ trợ SPI này. Bài học tập trung vào thời điểm lựa chọn resolver của `java.net.InetAddress`, không đồng nhất SPI này với mọi cơ chế DNS của hệ điều hành hay thư viện bên ngoài.

## 1. Ba thời điểm cần phân biệt

Một `InetAddressResolverProvider` là nhà cung cấp dịch vụ; phương thức `get(Configuration)` của nó tạo hoặc trả về một `InetAddressResolver` thực sự xử lý các yêu cầu tra cứu. Java chỉ cần chọn resolver cho một JVM một lần trong luồng khởi tạo bình thường.

| Thời điểm | Hành vi quan trọng | Hệ quả |
| --- | --- | --- |
| **Trong lúc VM còn khởi tạo** | Các tra cứu cần thiết cho quá trình bootstrap có thể dùng resolver tích hợp sẵn của JDK. | Không thể suy ra rằng provider tùy biến đã được phát hiện chỉ vì một thao tác liên quan đến mạng xảy ra rất sớm. |
| **Sau khi VM khởi tạo, trước lần tra cứu cần resolver** | Lựa chọn SPI cho JVM chưa nhất thiết được thực hiện; nhà cung cấp phải sẵn sàng để Java phát hiện khi cần. | Cấu hình service/provider phải có mặt trong môi trường khởi chạy. |
| **Lần tra cứu đầu tiên sau khi VM khởi tạo mà cần sử dụng resolver** | `InetAddress` khởi tạo resolver cho JVM: tìm provider theo cơ chế dịch vụ, nhận resolver qua `get(...)` hoặc dùng resolver tích hợp khi không có provider phù hợp. | Resolver được chọn và dùng cho các lần phân giải tiếp theo trong JVM. |
| **Những lần tra cứu về sau** | `InetAddress` tiếp tục dùng lựa chọn resolver đã thiết lập, tùy việc tra cứu có đi tới resolver hay được xử lý ngay bởi cache/địa chỉ literal. | Không có cơ chế công khai để thay provider toàn JVM chỉ bằng sửa file service lúc đang chạy. |

Điểm cốt lõi nằm ở **tra cứu thực sự phải đi qua resolver**. Việc gọi một API có tên “getByName” không có nghĩa chắc chắn đã xảy ra một truy vấn DNS hoặc phương thức tra cứu trên custom resolver: địa chỉ IP dạng số có thể được phân tích trực tiếp, và tên đã được lưu trong cache có thể không cần gọi resolver lần nữa.

### Dòng thời gian

~~~text
Khởi động JVM
    |
    |  Có thể cần tra cứu khi VM đang bootstrap
    |  -> resolver tích hợp phục vụ nhu cầu khởi động
    v
VM khởi tạo xong
    |
    |  Provider đã được cấu hình trên class path/module path
    |  nhưng chưa chắc được khởi tạo
    v
Tra cứu đầu tiên cần resolver sau khởi tạo VM
    |
    +--> Tìm InetAddressResolverProvider
    |       |
    |       +--> Có provider: gọi provider.get(configuration)
    |       |                   -> lấy resolver tùy biến
    |       |
    |       +--> Không có provider: dùng resolver tích hợp
    v
Resolver đã chọn cho JVM
    |
    +--> Các yêu cầu InetAddress tiếp theo sử dụng cùng lựa chọn
         (cache/literal có thể làm giảm số lần gọi resolver)
~~~

**Ví dụ thực tế:** một ứng dụng có mã cấu hình DNS trong `main` nhưng một thư viện đã gọi `InetAddress.getByName(...)` trước đó. Khi provider đã được chọn, thay file cấu hình hoặc thêm một JAR cung cấp service trong cùng tiến trình không làm `InetAddress` tự chọn lại. Vì vậy, việc cài provider cần là một phần của **cấu hình khởi chạy**, và bài kiểm chứng phải chạy trong **JVM mới**.

## 2. “Toàn JVM” nghĩa là gì?

`InetAddressResolverProvider` không được chọn riêng cho từng đối tượng `InetAddress`, từng lớp nghiệp vụ hay từng request. Resolver được chọn thuộc cơ chế tra cứu địa chỉ của `InetAddress` trong tiến trình Java.

Những hệ quả thực tế:

1. Nhiều luồng gọi `InetAddress.getByName` hoặc `InetAddress.getAllByName` trong cùng JVM cùng chịu ảnh hưởng của resolver đã được chọn. Phần hiện thực resolver cần xử lý truy cập đồng thời phù hợp.
2. Tạo thêm `InetAddress`, tạo class loader ứng dụng mới hoặc gọi `ServiceLoader.reload()` của một đối tượng `ServiceLoader` riêng **không phải** thao tác thay resolver mà `InetAddress` đang sử dụng.
3. Nếu có nhiều provider, không nên dựa vào thứ tự phát hiện không được đảm bảo để quyết định provider nào thắng. Hãy cấu hình một provider rõ ràng cho tiến trình.
4. Phạm vi này áp dụng cho đường phân giải địa chỉ qua API `InetAddress`. Một thư viện có DNS client hoặc resolver riêng không nhất thiết đi qua SPI này.

Trong nhiều ứng dụng, `main` bắt đầu khi VM đã khởi tạo xong. Tuy nhiên, framework, bộ nạp lớp, mã khởi tạo tĩnh hoặc thư viện có thể yêu cầu tra cứu trước khi phần mã nghiệp vụ bạn dự kiến thực thi. Do đó, đừng dựa vào giả định “lần đầu gọi trong hàm của tôi là lần đầu của JVM”.

## 3. Đăng ký provider trước khi tra cứu

Có hai cách đăng ký chuẩn trong hệ sinh thái Java: thông qua service descriptor trên class path hoặc khai báo dịch vụ của một named module. Chọn cách phù hợp với kiểu đóng gói ứng dụng.

### Cách A: class path và `META-INF/services`

Trong JAR chứa provider, tạo tài nguyên:

~~~text
META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

Nội dung là tên lớp provider đầy đủ, chẳng hạn:

~~~text
demo.resolver.LoggingResolverProvider
~~~

JAR này phải xuất hiện trên class path phù hợp **ngay khi khởi chạy JVM**. Việc đặt một file cùng tên vào thư mục bất kỳ không tự động đăng ký được service; nó phải nằm đúng vị trí tài nguyên trong đầu vào mà cơ chế nạp dịch vụ của Java nhìn thấy.

### Cách B: named module

Một module chứa provider có thể khai báo:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with demo.resolver.LoggingResolverProvider;
}
~~~

Module chứa provider phải được giải quyết (resolved) khi chạy ứng dụng. Với một module chỉ đóng vai trò nhà cung cấp và không được module chính tham chiếu trực tiếp, cần bảo đảm cấu hình khởi chạy đưa module đó vào tập module được giải quyết, chẳng hạn sử dụng `--add-modules` khi phù hợp.

**Chú ý:** đây là đăng ký **service provider**, không phải lệnh gọi trực tiếp để thay `InetAddress` resolver. Đoạn `new LoggingResolverProvider()` trong mã ứng dụng không tự cài resolver cho JVM.

## 4. Ví dụ quan sát thời điểm cài đặt

Provider dưới đây chỉ ghi log khi được yêu cầu cung cấp resolver, rồi trả về resolver tích hợp của JDK. Cách này cho phép kiểm chứng vòng đời SPI mà vẫn giữ cách phân giải địa chỉ thông thường.

~~~java
package demo.resolver;

import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;

public final class LoggingResolverProvider
        extends InetAddressResolverProvider {

    @Override
    public String name() {
        return "logging-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        System.out.println("[SPI] get(): chon resolver cho JVM");
        return configuration.builtinResolver();
    }
}
~~~

Giả sử provider đã được đăng ký như phần trên, dùng chương trình kiểm tra:

~~~java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;

public final class Main {
    public static void main(String[] args) {
        System.out.println("[main] truoc tra cuu A");
        lookup("example.com");

        System.out.println("[main] truoc tra cuu B");
        lookup("openjdk.org");
    }

    private static void lookup(String host) {
        try {
            InetAddress.getByName(host);
        } catch (UnknownHostException e) {
            System.out.println("[main] khong phan giai duoc " + host);
        }
    }
}
~~~

Biên dịch và đóng gói lớp cùng tài nguyên `META-INF/services` vào JAR. Chạy chương trình trong một **JVM mới** với JDK hỗ trợ SPI, ví dụ:

~~~sh
java --class-path demo.jar demo.resolver.Main
~~~

Khi không có tra cứu nào khác đã kích hoạt việc chọn resolver trước đó, kết quả có thể có dạng:

~~~text
[main] truoc tra cuu A
[SPI] get(): chon resolver cho JVM
[main] truoc tra cuu B
~~~

Log `get()` xuất hiện một lần cho lần khởi tạo resolver thành công, không xuất hiện lặp lại mỗi lần gọi `getByName`. Việc hai tên miền phân giải thành công hay thất bại phụ thuộc môi trường mạng; kiểm thử **thời điểm chọn provider** chỉ cần quan sát log. Trong môi trường có tra cứu sớm, dòng log SPI có thể đến trước dòng đầu tiên của `main`. Đây là kết quả hợp lệ, cần xét cùng mã khởi động và cấu hình ứng dụng.

Nếu **không** thấy log SPI, kiểm tra lần lượt: service descriptor đúng đường dẫn và tên lớp, lớp provider có trên class path hoặc module path, module provider đã được giải quyết, và có nhà cung cấp khác đang được phát hiện trước hay không. Cũng cần chạy lại bằng tiến trình mới để không bị ảnh hưởng bởi lựa chọn đã thực hiện trước đó.

## 5. Vì sao không nên tra cứu trong lúc tạo provider?

Một lỗi thiết kế dễ gặp là khởi tạo provider bằng cách gọi chính các API `InetAddress` đang cần resolver:

~~~java
@Override
public InetAddressResolver get(Configuration configuration) {
    // KHONG NEN: co the kich hoat lai luong khoi tao resolver.
    try {
        InetAddress.getByName("example.com");
    } catch (java.net.UnknownHostException ignored) {
        // Loi DNS khong loai bo nguy co khoi tao de quy.
    }
    return configuration.builtinResolver();
}
~~~

Vấn đề chính là **phụ thuộc vòng**: lúc `InetAddress` đang khởi tạo resolver, `get(...)` lại yêu cầu `InetAddress` phân giải tên. Tùy đường chạy và phiên bản triển khai, việc này có thể làm khởi tạo thất bại hoặc cho hành vi khó dự đoán. Việc bắt `UnknownHostException` không giải quyết phụ thuộc vòng. Tương tự, tránh gọi tra cứu địa chỉ trong static initializer hoặc constructor của provider.

Nếu muốn mở rộng resolver tích hợp, lấy đối tượng gốc bằng:

~~~java
InetAddressResolver builtin = configuration.builtinResolver();
~~~

Sau đó tạo một `InetAddressResolver` có phương thức tra cứu chuyển tiếp sang `builtin` và thêm logic cần thiết. Nếu gọi `InetAddress.getByName` từ bên trong phương thức phân giải tên của resolver tùy biến, yêu cầu có thể quay lại chính resolver đó và gây đệ quy. Cần ủy quyền trực tiếp qua API `InetAddressResolver` của resolver tích hợp.

Ngoài ra, tránh thực hiện công việc chậm, truy cập mạng phụ thuộc DNS hoặc nạp cấu hình phức tạp trong `get(...)`. Đây là đường khởi tạo có thể nằm trên luồng đầu tiên cần tra cứu; nếu xử lý lâu hoặc lỗi, tác động sẽ lan đến toàn bộ các thành phần dùng `InetAddress`.

## 6. Các tình huống cần phân tích

| Tình huống | Điều nên kết luận |
| --- | --- |
| Có yêu cầu tra cứu trong giai đoạn VM còn khởi tạo | Resolver tích hợp có thể phục vụ giai đoạn bootstrap; không nên lấy sự kiện này làm bằng chứng provider đã được cài. |
| Ứng dụng gọi `InetAddress.getByName("127.0.0.1")` trước | Địa chỉ literal có thể được xử lý trực tiếp; không phải phép thử đáng tin cậy cho thời điểm SPI hoạt động. |
| Gọi lại cùng tên miền liên tục nhưng log resolver không xuất hiện nữa | Cache có thể trả kết quả. Điều đó không đồng nghĩa resolver toàn JVM bị thay hoặc vô hiệu hóa. |
| Đã có tra cứu sau VM khởi tạo, rồi mới chép JAR provider vào thư mục | Java không tự tải lại và thay resolver đã chọn. Khởi chạy tiến trình mới với cấu hình service đúng. |
| Hai provider cùng được đăng ký | Tránh phụ thuộc thứ tự nhà cung cấp khi chạy; loại bỏ sự nhập nhằng trong cấu hình. |
| Provider trả về resolver tự viết | Cần xử lý cả tra cứu tên thành địa chỉ và địa chỉ thành tên theo hợp đồng `InetAddressResolver`, đồng thời tôn trọng chính sách chọn IPv4/IPv6 và vấn đề đồng thời. |
| `InetAddress.getByName` không cho kết quả như mong đợi | Phân biệt lỗi DNS/mạng, lỗi service discovery, cache và lỗi trong custom resolver. Không suy luận mọi lỗi phân giải đều do thời điểm cài SPI. |

### Quy trình kiểm chứng tối thiểu

1. Đóng gói provider và khai báo service đúng cách trên một JDK hiện hành (JDK 18 trở lên).
2. Ghi log trong constructor và `get(...)` của provider, đồng thời ghi log trước các đoạn ứng dụng gọi `InetAddress`.
3. Khởi chạy **tiến trình Java mới**, dùng tên host thật khi kiểm chứng đường phân giải. Không dùng IP literal làm phép thử chính.
4. Quan sát thời điểm log của `get(...)` và đối chiếu với hoạt động tra cứu đầu tiên của **toàn JVM**, kể cả thư viện khởi động. Tránh kết luận chỉ dựa vào thứ tự lời gọi trong một hàm ứng dụng.
5. Thử nhiều lần tra cứu trong cùng JVM, rồi chạy một JVM mới sau khi thay cấu hình provider. Quan sát rằng sự lựa chọn chỉ được thực hiện lại khi JVM mới khởi tạo đường resolver.

## 7. Câu hỏi tự kiểm tra

**Câu 1.** Một thư viện đã tra cứu hostname khi khởi chạy ứng dụng, sau đó `main` mới gọi hàm cấu hình service provider. Có thể đảm bảo provider đó sẽ được `InetAddress` chọn không?

**Trả lời:** Không. SPI được phát hiện theo cơ chế khởi tạo resolver của JVM khi cần; nếu lựa chọn đã được thực hiện, không có thao tác cấu hình lại công khai để thay nó. Hãy đưa provider vào cấu hình khởi chạy từ đầu.

**Câu 2.** Vì sao `get(...)` chỉ log một lần, dù có một trăm request mạng?

**Trả lời:** `get(...)` cung cấp resolver khi Java khởi tạo lựa chọn cho JVM, không phải API được gọi cho mỗi hostname. Những request sau có thể gọi resolver đã chọn hoặc lấy kết quả từ cache.

**Câu 3.** Vì sao tránh gọi `InetAddress.getByName` trong `get(Configuration)`?

**Trả lời:** Nó có thể yêu cầu sử dụng resolver ngay trong lúc resolver đang được khởi tạo, tạo phụ thuộc vòng. Nếu cần giữ cách tra cứu mặc định, dùng `configuration.builtinResolver()` để ủy quyền.

## Ghi nhớ

- **Khởi tạo VM xong** và **phát sinh tra cứu đầu tiên cần resolver** là hai mốc khác nhau.
- Trong giai đoạn bootstrap, Java có thể cần resolver tích hợp. Sau khởi tạo VM, lựa chọn resolver SPI được thực hiện khi cơ chế phân giải thực sự cần nó.
- **Một lựa chọn resolver phục vụ phạm vi JVM**; đăng ký provider đúng cách trước lúc chạy và dùng JVM mới để thử cấu hình khác.
- Quan sát log của `provider.get(...)` cùng với kết quả tra cứu, nhưng luôn xét cache, literal IP, khởi tạo sớm và tính sẵn có của DNS.

**Tài liệu tham khảo:** JEP 418 — Internet-Address Resolution SPI (`https://openjdk.org/jeps/418`); Java API `java.net.spi.InetAddressResolverProvider`, `java.net.spi.InetAddressResolver` và `java.net.InetAddress` trên phiên bản JDK đang sử dụng.
