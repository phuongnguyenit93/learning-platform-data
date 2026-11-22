# Mở rộng lúc chạy là gì và vì sao ứng dụng cần điểm mở rộng

## 1. Mở rộng lúc chạy là gì?

**Mở rộng lúc chạy (runtime extensibility)** là khả năng một ứng dụng tiếp nhận, lựa chọn, nạp hoặc thay đổi thành phần cung cấp hành vi trong khi tiến trình đang hoạt động. Thành phần mở rộng thường tuân theo một hợp đồng (interface/API) đã được ứng dụng định nghĩa từ trước. Tùy kiến trúc, ứng dụng có thể phát hiện plugin mới, cấu hình lại chiến lược, đăng ký handler, hoặc kích hoạt/tắt tính năng mà không cần sửa mã nguồn của lõi ứng dụng.

Cần phân biệt ba cấp độ:

- **Mở rộng ở thời điểm biên dịch:** viết thêm lớp triển khai interface rồi biên dịch và triển khai phiên bản ứng dụng mới. Thiết kế có điểm mở rộng nhưng việc bổ sung hành vi chưa diễn ra trong một tiến trình đang chạy.
- **Mở rộng ở thời điểm khởi động:** ứng dụng chọn và nạp các triển khai dựa trên cấu hình, classpath hoặc module path. Không phải sửa lõi; muốn thấy plugin mới có thể vẫn phải khởi động lại.
- **Mở rộng khi tiến trình đang chạy:** một thành phần có thể được phát hiện, nạp, đăng ký hoặc thay thế động. Đây là yêu cầu mạnh nhất, đòi hỏi quản lý vòng đời, cô lập, tương thích và tài nguyên.

Ví dụ, một hệ thống xuất báo cáo có thể cung cấp định dạng CSV mặc định rồi bổ sung bộ xuất JSON thông qua plugin. Lõi hệ thống chỉ yêu cầu đối tượng thực hiện hợp đồng `ReportExporter`; loại định dạng cụ thể do registry và cơ chế phát hiện quyết định.

Mở rộng lúc chạy **không đồng nghĩa** với sửa bytecode hoặc tạo class mới bằng reflection. Reflection, `ServiceLoader`, class loader, `ModuleLayer` hay một registry đều có thể góp phần hiện thực, nhưng bản thân chúng không đảm bảo hot-reload hoặc khả năng thay đổi plugin an toàn.

## 2. Vì sao ứng dụng cần điểm mở rộng?

**Điểm mở rộng (extension point)** là vị trí và hợp đồng được lõi ứng dụng chủ động công bố để thành phần khác cung cấp hành vi. Nó tách phần ổn định của quy trình khỏi phần có thể thay đổi.

Giả sử một dịch vụ phải hỗ trợ nhiều kiểu gửi thông báo. Khi không có điểm mở rộng, lõi phải kiểm tra từng loại:

```java
if ("email".equals(channel)) {
    // gửi email
} else if ("sms".equals(channel)) {
    // gửi SMS
} else if ("push".equals(channel)) {
    // gửi push
}
```

Mỗi kênh mới làm lõi phải sửa, kiểm thử và triển khai lại; luồng xử lý chính dễ bị gắn với chi tiết của từng nhà cung cấp. Một điểm mở rộng chuyển trách nhiệm đó sang các triển khai của hợp đồng `NotificationSender`.

Các lợi ích chính:

1. **Giảm phụ thuộc:** lõi phụ thuộc vào interface và các quy tắc chung, không phụ thuộc trực tiếp vào từng triển khai.
2. **Cho phép tùy biến:** khách hàng, môi trường hoặc nhà tích hợp bổ sung hành vi theo nhu cầu riêng.
3. **Giữ lõi ổn định:** thêm định dạng, quy tắc kiểm tra, connector hoặc chiến lược mới với ít thay đổi trong logic chung.
4. **Hỗ trợ hệ sinh thái plugin:** nhiều nhóm có thể phát triển thành phần độc lập nếu hợp đồng đủ rõ và tương thích.
5. **Cho phép chọn hành vi theo ngữ cảnh:** registry có thể tìm triển khai theo loại dữ liệu, tenant, phiên bản hoặc cấu hình.
6. **Khoanh vùng kiểm thử và vận hành:** từng triển khai có thể được kiểm thử theo bộ contract test chung, đo hiệu năng và tắt khi lỗi.

Không phải hệ thống nào cũng cần khả năng nạp nóng. Một interface với các triển khai được chọn lúc khởi động thường đơn giản, an toàn và đủ dùng. Chỉ chọn cơ chế nạp động khi yêu cầu nghiệp vụ thực sự cần thêm/thay đổi chức năng trong lúc tiến trình đang phục vụ.

## 3. Một điểm mở rộng gồm những gì?

Một thiết kế thực tế thường có năm thành phần:

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| **Hợp đồng** | Định nghĩa phương thức, kiểu dữ liệu, lỗi và ý nghĩa của hành vi | `ReportExporter.export(Report)` |
| **Triển khai** | Cung cấp hành vi cụ thể theo hợp đồng | `CsvExporter`, `JsonExporter` |
| **Cơ chế khám phá** | Tìm thành phần có thể sử dụng | `ServiceLoader`, cấu hình, quét metadata |
| **Registry/dispatcher** | Đăng ký, tra cứu và lựa chọn triển khai | Map từ `format` đến exporter |
| **Quản lý vòng đời** | Khởi tạo, kích hoạt, ngừng nhận việc và giải phóng tài nguyên | `start()`, `close()` |

Luồng điển hình:

```text
Yêu cầu từ người dùng
        |
        v
Lõi ứng dụng --> Registry --> Triển khai được chọn
        |                           |
        +<------ Kết quả -----------+
```

Hợp đồng không chỉ là chữ ký phương thức. Nó nên nói rõ dữ liệu đầu vào hợp lệ, kết quả, mã lỗi hoặc exception, tính thread-safe, thời gian thực thi, quyền truy cập, quản lý tài nguyên và chính sách tương thích phiên bản. Nếu hai plugin cùng nhận một key, registry cũng cần quy tắc xử lý xung đột rõ ràng: từ chối, ưu tiên có chủ đích hoặc yêu cầu cấu hình chọn tường minh.

## 4. Ví dụ Java 17+: một điểm mở rộng đơn giản

Ví dụ sau sử dụng interface, hai triển khai và một registry. Toàn bộ mã nằm trong **một tệp `ExtensionDemo.java`**, biên dịch và chạy được với Java 17+.

```java
import java.util.HashMap;
import java.util.Map;

public class ExtensionDemo {
    interface GreetingProvider {
        String language();
        String greet(String name);
    }

    static final class VietnameseGreeting implements GreetingProvider {
        public String language() { return "vi"; }
        public String greet(String name) { return "Xin chào, " + name; }
    }

    static final class EnglishGreeting implements GreetingProvider {
        public String language() { return "en"; }
        public String greet(String name) { return "Hello, " + name; }
    }

    static final class GreetingRegistry {
        private final Map<String, GreetingProvider> providers = new HashMap<>();

        void register(GreetingProvider provider) {
            if (providers.putIfAbsent(provider.language(), provider) != null) {
                throw new IllegalArgumentException("Duplicate language: " + provider.language());
            }
        }

        String greet(String language, String name) {
            GreetingProvider provider = providers.get(language);
            if (provider == null) {
                throw new IllegalArgumentException("Unsupported language: " + language);
            }
            return provider.greet(name);
        }
    }

    public static void main(String[] args) {
        GreetingRegistry registry = new GreetingRegistry();
        registry.register(new VietnameseGreeting());
        registry.register(new EnglishGreeting());

        System.out.println(registry.greet("vi", "Lan"));
        System.out.println(registry.greet("en", "Lan"));
    }
}
```

Chạy:

```bash
javac ExtensionDemo.java
java ExtensionDemo
```

Kết quả:

```text
Xin chào, Lan
Hello, Lan
```

Ở đây `GreetingProvider` là hợp đồng, `VietnameseGreeting` và `EnglishGreeting` là triển khai, còn `GreetingRegistry` đóng vai trò đăng ký và lựa chọn. Muốn thêm ngôn ngữ mới, có thể tạo triển khai mới mà không sửa phương thức `greet` của registry. Tuy nhiên ví dụ vẫn đăng ký các triển khai tĩnh trong `main`; **nó minh họa điểm mở rộng, chưa phải nạp plugin từ tệp JAR khi đang chạy**.

Registry sử dụng `HashMap` nên chỉ phù hợp tình huống đăng ký trước khi nhiều luồng bắt đầu sử dụng. Nếu registry phải thay đổi đồng thời với các request, cần một thiết kế thread-safe, chẳng hạn `ConcurrentHashMap`, snapshot bất biến hoặc đồng bộ hóa có kiểm soát. Sự an toàn của registry không tự làm cho các provider bên trong thread-safe.

## 5. Từ hợp đồng đến khám phá plugin

Java cung cấp `java.util.ServiceLoader` để tìm các provider được công bố theo cơ chế service-provider. Nó tách mã tiêu thụ dịch vụ khỏi danh sách lớp triển khai cụ thể.

Ví dụ khái niệm:

```java
ServiceLoader<GreetingProvider> loader = ServiceLoader.load(GreetingProvider.class);
for (GreetingProvider provider : loader) {
    registry.register(provider);
}
```

*Đoạn trên là phần tích hợp vào ứng dụng đã định nghĩa `GreetingProvider` và `registry`, không phải chương trình độc lập.*

Với classpath thông thường, JAR cung cấp provider có thể đặt tệp `META-INF/services/<tên interface đầy đủ>`, mỗi dòng ghi tên đầy đủ của lớp triển khai. Với module Java được khai báo tường minh, module tiêu thụ dùng `uses`, module provider dùng `provides ... with ...`. Provider cần đáp ứng quy tắc khởi tạo tương ứng của cơ chế service.

`ServiceLoader.load(...)` dùng class loader phù hợp để phát hiện provider trong phạm vi nhìn thấy của nó; việc thêm JAR vào thư mục sau khi JVM đã khởi chạy **không tự khiến classpath của JVM cập nhật**. `reload()` làm mới cache provider của loader, nhưng không tự thêm class loader mới, không phát hiện JAR ngoài phạm vi class loader, không gỡ bỏ instance đang được ứng dụng giữ và không bảo đảm nạp nóng. Muốn hỗ trợ plugin JAR thực sự trong lúc chạy, cần thiết kế riêng cho class loader/layer, đường dẫn plugin, vòng đời và chuyển đổi request đang hoạt động.

Các cơ chế mở rộng thường gặp khác gồm:

- **Dependency injection:** cấu hình nhiều implementation và chọn bean theo qualifier/chiến lược. Thường quyết định tại thời điểm khởi động application context.
- **Event/listener hooks:** mở rộng phản ứng trước sự kiện mà lõi phát ra. Cần làm rõ thứ tự, xử lý lỗi và chính sách giao dịch.
- **Scripting hoặc rule engine:** thay đổi quy tắc qua dữ liệu/script. Cần giới hạn quyền truy cập và đánh giá tác động bảo mật.
- **Plugin API + class loader riêng:** có thể nạp mã từ JAR được cung cấp sau khi triển khai. Phức tạp hơn về class identity, versioning, cô lập và đóng tài nguyên.
- **Extension qua giao thức:** tiến trình bên ngoài triển khai HTTP/gRPC/event contract, giúp tách vòng đời và giảm yêu cầu nạp mã vào cùng JVM, đổi lại có chi phí mạng và vận hành.

## 6. Khác biệt giữa mở rộng, cấu hình và cập nhật ứng dụng

| Tình huống | Có phải điểm mở rộng? | Có cần nạp động? |
|---|---|---|
| Đổi timeout qua tệp cấu hình | Không nhất thiết; thường chỉ đổi tham số | Không |
| Thêm `PaymentProvider` rồi build lại ứng dụng | Có | Không |
| Chọn provider đã có theo tenant khi request đến | Có | Không nhất thiết |
| Nạp plugin JAR mới vào tiến trình đang phục vụ | Có | Có |
| Thay hẳn code lõi và deploy phiên bản mới | Không phải mở rộng lúc chạy của tiến trình cũ | Không |

**Open/Closed Principle** khuyến khích thành phần ổn định có thể được mở rộng mà không cần liên tục sửa logic cũ. Điểm mở rộng là một cách hiện thực nguyên tắc đó, nhưng cũng tạo ra hợp đồng mà ứng dụng phải duy trì. Đưa ra quá nhiều điểm mở rộng trước khi có nhu cầu thật khiến hệ thống phức tạp, khó debug và tốn chi phí tương thích.

## 7. Thiết kế điểm mở rộng an toàn và bền vững

### Hợp đồng và tương thích

- Chọn API nhỏ, tập trung vào một trách nhiệm. Dùng các kiểu dữ liệu rõ ràng, tránh lộ quá nhiều lớp nội bộ của lõi.
- Định nghĩa quy tắc versioning. Việc thay đổi phương thức interface có thể phá vỡ khả năng biên dịch hoặc liên kết của plugin cũ; thêm default method cũng cần đánh giá hành vi.
- Cung cấp test contract cho mọi triển khai; không chỉ test một provider mặc định.
- Xử lý trường hợp không có provider, trùng key, provider không tương thích hoặc lỗi khởi tạo bằng thông báo cụ thể.

### Bảo mật và độ tin cậy

**Plugin Java chạy cùng JVM thường có quyền thực thi mã của tiến trình**. Class loader riêng là cơ chế phân vùng tên lớp và hỗ trợ vòng đời tải lớp, không phải ranh giới bảo mật đáng tin cậy cho mã không tin cậy. Không coi Java Security Manager là giải pháp sandbox cho hệ Java hiện đại.

Nếu plugin đến từ bên thứ ba, cần xác minh nguồn gốc và chữ ký/artifact, quản lý phiên bản dependency, giới hạn người có quyền cài đặt và theo dõi các thành phần đang bật. Với mã không tin cậy, ưu tiên tách sang tiến trình/container với quyền hệ điều hành và kết nối mạng bị giới hạn, kèm xác thực giao thức.

### Vòng đời và vận hành

Nạp và gỡ plugin cần trả lời các câu hỏi: request đang dùng plugin cũ sẽ hoàn thành thế nào; callback, thread, scheduler, socket và file handle được đóng ra sao; rollback ra phiên bản nào; plugin lỗi có làm sập lõi hay không?

Các lớp đã nạp thường chỉ có khả năng được thu hồi khi class loader của chúng và mọi đối tượng/class liên quan không còn được tham chiếu phù hợp. Không thể mặc nhiên giả định `close()` trên `URLClassLoader` sẽ lập tức dỡ toàn bộ lớp đã nạp; nó chủ yếu đóng tài nguyên liên quan đến loader. Registry và cơ chế khám phá cần ngừng tham chiếu plugin cũ, đồng thời có chiến lược xử lý công việc đang chạy.

Bổ sung log/audit cho việc nạp, kích hoạt, từ chối, lỗi và gỡ plugin. Đo thời gian thực thi và tỷ lệ lỗi theo provider; định nghĩa timeout hoặc circuit breaker tại ranh giới gọi phù hợp. Đối với nghiệp vụ quan trọng, đặt chính sách fallback minh bạch, tránh âm thầm chọn plugin khác làm thay đổi ý nghĩa xử lý.

## 8. Khi nào nên dùng và cách bắt đầu?

Một điểm mở rộng phù hợp khi có ít nhất một trục biến thiên rõ ràng: định dạng xuất, bộ xử lý tài liệu, phương thức thanh toán, cổng thông báo, bước xử lý pipeline hoặc quy tắc xác thực. Nếu hệ thống chỉ có một hành vi cố định và chưa có kế hoạch tích hợp, viết mã trực tiếp có thể dễ bảo trì hơn.

Lộ trình thực tế:

1. **Xác định phần thay đổi:** ví dụ chỉ bộ chuyển đổi dữ liệu thay đổi, còn bước nhận request và lưu kết quả ổn định.
2. **Định nghĩa hợp đồng nhỏ:** dữ liệu vào/ra, lỗi, thread-safety, quyền và lifecycle.
3. **Viết hai triển khai:** chứng minh hợp đồng không bị bó chặt vào một trường hợp.
4. **Đưa registry/dispatcher vào lõi:** chọn triển khai bằng key/cấu hình; có cách báo lỗi khi không có lựa chọn hợp lệ.
5. **Thêm cơ chế khám phá khi cần:** bắt đầu bằng đăng ký tĩnh hoặc `ServiceLoader`; chỉ thêm class loader động khi yêu cầu nạp nóng thực sự tồn tại.
6. **Kiểm thử và quan sát:** contract test, version compatibility, tải đồng thời, lỗi khởi tạo, rollback và giải phóng tài nguyên.

### Những lỗi thường gặp

- Gọi mọi interface là runtime extensibility dù các triển khai đều đóng cứng trong ứng dụng.
- Nhầm `ServiceLoader.reload()` với việc JVM tự tìm mọi JAR mới trên đĩa.
- Công bố interface quá phụ thuộc implementation nội bộ khiến plugin luôn phải cập nhật theo lõi.
- Đăng ký hoặc thay provider trong `HashMap` khi các luồng khác đang truy cập mà không đồng bộ.
- Tin rằng class loader riêng cô lập được mã độc trong cùng JVM.
- Thiếu chính sách lỗi, timeout, rollback và đóng tài nguyên khi muốn hỗ trợ thay plugin nóng.
- Để plugin quyết định thứ tự xử lý hoặc ghi đè provider khác mà không có quy tắc rõ ràng.

**Ghi nhớ:** một điểm mở rộng tốt là **hợp đồng ổn định + cách tìm/chọn triển khai + quy tắc vận hành rõ ràng**. Khả năng mở rộng lúc chạy được xây trên nền tảng này, nhưng việc có thể nạp/gỡ plugin ngay trong tiến trình là yêu cầu riêng, cần cơ chế và kiểm thử chặt chẽ hơn.
