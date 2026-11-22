# Tách kiểm tra mô tả nhẹ khỏi khởi tạo provider tốn tài nguyên

## 1. Bài toán khi chọn provider

Trong kiến trúc plugin, một host thường phát hiện nhiều **provider** (lớp triển khai hợp đồng mở rộng), nhưng chỉ cần sử dụng một hoặc một số ít. Nếu host tạo tất cả đối tượng chỉ để hỏi chúng có phù hợp hay không, quá trình khám phá có thể vô tình:

- Kết nối mạng hoặc cơ sở dữ liệu trong constructor.
- Khởi tạo native library, thread pool, cache hoặc đọc cấu hình lớn.
- Gây hiệu ứng phụ trước khi người dùng chọn chức năng.
- Làm chậm khởi động hoặc thất bại vì một plugin không được chọn.
- Khó thu hồi tài nguyên đã cấp phát cho các provider bị bỏ qua.

Ví dụ sai về thời điểm khởi tạo:

\`\`\`java
for (MessageProvider provider : ServiceLoader.load(MessageProvider.class)) {
    if (provider.id().equals(requestedId)) {
        return provider;
    }
}
\`\`\`

Vòng lặp này gọi \`iterator()\` của \`ServiceLoader\` và yêu cầu các **instance**. Để đến provider phù hợp, nó có thể tạo mọi provider nằm trước trong thứ tự duyệt. Nếu constructor có chi phí đáng kể, chỉ riêng bước kiểm tra \`id()\` đã tạo ra phần việc không cần thiết.

Mục tiêu: tách **discovery và kiểm tra mô tả nhẹ** khỏi **activation và cấp phát tài nguyên**. Host nên lựa chọn dựa trên thông tin không cần đối tượng đầy đủ, sau đó chỉ khởi tạo provider trúng tuyển khi thật sự cần.

## 2. Ba lớp hoạt động cần phân biệt

| Giai đoạn | Việc cần làm | Có nên tạo provider thật? |
|---|---|---|
| **Discovery** | Tìm những provider đã đăng ký trong JAR/module, lấy tên lớp hoặc thông tin nhà cung cấp | Chưa |
| **Selection** | Kiểm tra metadata: ID, loại chức năng, version, capability, priority, policy | Thường chưa |
| **Activation** | Tạo instance, nạp config, mở kết nối, thực thi công việc, giải phóng tài nguyên đúng vòng đời | Có, với provider được chọn |

Không phải mọi metadata đều có sẵn từ Java SPI. \`META-INF/services\` theo classpath chỉ ghi tên lớp provider; nó **không** có sẵn trường \`id\`, \`priority\` hoặc \`capabilities\`. Muốn chọn theo những tiêu chí ấy trước khi tạo instance, host và tác giả plugin phải thống nhất một cách mô tả: annotation có retention runtime, manifest/descriptor riêng, registry, hoặc module descriptor và quy tắc nhận diện kiểu.

Cần phân biệt thêm: **không khởi tạo instance** không đồng nghĩa **không tải hoặc không kiểm tra class**. Việc khám phá và truy cập metadata có thể gây class loading/linkage, xử lý module configuration hoặc lỗi provider; vì vậy vẫn cần xử lý lỗi ở giai đoạn khám phá.

## 3. Cơ chế Java 9+: ServiceLoader.Provider

Từ Java 9, \`ServiceLoader.stream()\` trả về các phần tử \`ServiceLoader.Provider<S>\`, cho phép:

- \`Provider.type()\`: hỏi kiểu provider (đối tượng \`Class\`) để xem annotation hoặc tên lớp.
- \`Provider.get()\`: yêu cầu một provider instance khi đã chọn.

Ví dụ:

\`\`\`java
ServiceLoader<MyService> loader = ServiceLoader.load(MyService.class);

MyService selected = loader.stream()
    .filter(p -> p.type().isAnnotationPresent(MyPlugin.class))
    .findFirst()
    .orElseThrow()
    .get();
\`\`\`

Điểm khác biệt so với \`for (MyService instance : loader)\` là quá trình lọc theo \`type()\` không gọi \`get()\` cho các provider bị bỏ qua. **Lưu ý:** \`get()\` là điểm yêu cầu instance; \`ServiceLoader\` có thể cache những instance nó đã tạo trong các lần duyệt tùy cách dùng, nên đừng mặc định mỗi \`get()\` luôn sinh đối tượng mới. Khi làm việc với provider factory của module, \`type()\` có thể mô tả kiểu trả về từ factory; annotation và quy tắc metadata phải tương thích loại provider mà ứng dụng hỗ trợ.

### Metadata qua annotation

Định nghĩa annotation:

\`\`\`java
package example.api;

import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
public @interface PluginInfo {
    String id();
    String category();
    int priority() default 0;
}
\`\`\`

Đặt annotation lên lớp implementation:

\`\`\`java
@PluginInfo(id = "uppercase", category = "text", priority = 10)
public final class UppercaseProvider implements TextProvider {
    // Chỉ khởi tạo các tài nguyên cần thiết khi provider được sử dụng.
}
\`\`\`

Host có thể đọc \`p.type().getAnnotation(PluginInfo.class)\` trong bước selection. Annotation phải có \`RUNTIME\` retention; nếu dùng \`SOURCE\` hoặc \`CLASS\`, reflection runtime không tìm được. Metadata annotation là thông tin từ mã plugin nên không được mặc nhiên tin cậy: host phải xác thực giá trị và kiểm soát chính sách chọn.

## 4. Ví dụ hoàn chỉnh, chạy trên Java 17+

Ví dụ sau đặt tất cả class trong **một tệp** \`Demo.java\` để dễ biên dịch, đồng thời dùng file SPI riêng. Trong ứng dụng thực, hợp đồng nằm ở API JAR, host và các implementation ở các JAR riêng; nguyên lý selection không đổi.

Cấu trúc:

\`\`\`text
demo/
├── Demo.java
└── META-INF/
    └── services/
        └── Demo$TextProvider
\`\`\`

### Mã nguồn Demo.java

\`\`\`java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;

public class Demo {
    @Retention(RetentionPolicy.RUNTIME)
    public @interface PluginInfo {
        String id();
        String category();
        int priority() default 0;
    }

    public interface TextProvider {
        String transform(String text);
    }

    @PluginInfo(id = "lowercase", category = "text", priority = 1)
    public static final class LowercaseProvider implements TextProvider {
        public LowercaseProvider() {
            System.out.println("init lowercase");
        }

        @Override
        public String transform(String text) {
            return text.toLowerCase(java.util.Locale.ROOT);
        }
    }

    @PluginInfo(id = "uppercase", category = "text", priority = 10)
    public static final class UppercaseProvider implements TextProvider {
        public UppercaseProvider() {
            System.out.println("init uppercase");
        }

        @Override
        public String transform(String text) {
            return text.toUpperCase(java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        ServiceLoader<TextProvider> loader = ServiceLoader.load(TextProvider.class);

        List<ServiceLoader.Provider<TextProvider>> candidates = loader.stream()
                .filter(p -> {
                    PluginInfo info = p.type().getAnnotation(PluginInfo.class);
                    return info != null && info.category().equals("text");
                })
                .toList();

        System.out.println("discovered: " + candidates.size());

        ServiceLoader.Provider<TextProvider> chosen = candidates.stream()
                .max(Comparator.comparingInt(
                        p -> p.type().getAnnotation(PluginInfo.class).priority()))
                .orElseThrow(() -> new IllegalStateException("No provider"));

        System.out.println("selected: "
                + chosen.type().getAnnotation(PluginInfo.class).id());

        TextProvider provider = chosen.get();
        System.out.println("result: " + provider.transform("HeLLo"));
    }
}
\`\`\`

Tệp \`META-INF/services/Demo$TextProvider\` chứa hai dòng:

\`\`\`text
Demo$LowercaseProvider
Demo$UppercaseProvider
\`\`\`

Vì các class lồng nhau là \`public static\`, chúng có tên binary chứa ký hiệu \`$\`. Tên file service descriptor cũng phải là **binary name** của service interface, tức \`Demo$TextProvider\`; không dùng tên viết kiểu source \`Demo.TextProvider\`.

Biên dịch và chạy từ thư mục \`demo/\`:

\`\`\`bash
javac -encoding UTF-8 Demo.java
java -cp . Demo
\`\`\`

Kết quả chính xác:

\`\`\`text
discovered: 2
selected: uppercase
init uppercase
result: HELLO
\`\`\`

Điều cần quan sát: không có dòng \`init lowercase\`. Cả hai provider đều đã được phát hiện và đọc annotation, nhưng chỉ provider có \`priority\` cao nhất mới được tạo instance.

Với ví dụ này, \`Demo.java\` được biên dịch thành nhiều file \`.class\` (gồm các nested classes). Thư mục \`META-INF/services\` là **tài nguyên runtime**, không phải kết quả của \`javac\`; nếu đóng gói thành JAR, phải đưa descriptor vào đúng vị trí. Để xem toàn bộ JAR sau khi đóng gói:

\`\`\`bash
jar --create --file demo.jar \
  -C . 'Demo.class' \
  -C . 'Demo$PluginInfo.class' \
  -C . 'Demo$TextProvider.class' \
  -C . 'Demo$LowercaseProvider.class' \
  -C . 'Demo$UppercaseProvider.class' \
  -C . META-INF/services
jar --list --file demo.jar
java -cp demo.jar Demo
\`\`\`

Các lệnh \`jar\` trên dùng cách quote tên file có \`$\` của POSIX shell. Trên Windows, có thể thay phần đóng gói bằng việc đặt class và descriptor trong một thư mục staging rồi chạy \`jar --create --file demo.jar -C staging .\`, đảm bảo staging chứa đúng các file được liệt kê.

## 5. Khi nào metadata thực sự “nhẹ”?

Đọc annotation qua reflection thường rẻ hơn khởi tạo provider có kết nối ngoài, nhưng vẫn có chi phí nạp lớp, tra cứu annotation và dependency của kiểu class. Để tối ưu, chọn mức phù hợp:

| Cách mô tả | Ưu điểm | Giới hạn |
|---|---|---|
| \`Provider.type()\` + annotation | Không tạo instance, gắn metadata sát implementation | Có class loading/reflection; cần kiểm soát tương thích |
| Descriptor độc lập (JSON/YAML/properties) | Có thể đọc mô tả trước khi nạp lớp plugin | Cần schema, versioning, validation, tránh metadata lỗi thời |
| Registry được build sinh ra | Tra cứu ID/capability nhanh, thuận tiện kiểm tra trước | Cần pipeline đảm bảo đồng bộ metadata và class |
| Provider factory nhẹ | Cho phép lựa chọn factory trước khi tạo sản phẩm nặng | Bản thân factory/provider của SPI vẫn có thể được khởi tạo |
| Khởi tạo mọi provider rồi hỏi \`id()\` | API đơn giản | Tốn tài nguyên, hiệu ứng phụ và nguy cơ thất bại không cần thiết |

Nếu ứng dụng có hàng trăm plugin, metadata độc lập có thể cho phép hiển thị danh sách mà chưa kích hoạt class loader của plugin. Một file minh họa:

\`\`\`properties
plugin.id=uppercase
plugin.category=text
plugin.priority=10
plugin.implementation=example.plugin.UppercaseProvider
plugin.apiVersion=1
\`\`\`

Đây là **định dạng do ứng dụng tự quy ước**, không phải chuẩn Java SPI. Host phải kiểm tra tính duy nhất của ID, giá trị \`priority\`, phiên bản API, tên implementation, tính nhất quán giữa descriptor và thực tế, và nguồn cung cấp plugin trước khi quyết định kích hoạt.

## 6. Đừng nhầm chọn provider với khởi tạo tài nguyên

Ngay cả khi \`Provider.get()\` tạo instance, không nhất thiết constructor phải mở mọi tài nguyên. Một thiết kế dễ bảo trì là constructor chỉ nhận cấu hình và dependency; activation thực sự có phương thức vòng đời rõ ràng:

\`\`\`java
public interface ManagedPlugin extends AutoCloseable {
    void start();
    void execute();
    @Override void close();
}
\`\`\`

Đoạn trên là **một hợp đồng minh họa**, không phải chương trình chạy độc lập. Host chọn implementation bằng metadata, gọi \`get()\`, rồi \`start()\` đúng thời điểm. Khi kết thúc, host gọi \`close()\` trong \`finally\` hoặc dùng \`try-with-resources\` nếu vòng đời thích hợp. Constructor nên tránh kết nối cơ sở dữ liệu hay khởi chạy thread nếu chưa cần; \`start()\` nên rõ lỗi, còn \`close()\` phải giải phóng tài nguyên đã tạo, kể cả activation thất bại một phần.

Khi provider quản lý kết nối đắt tiền hoặc state không thread-safe, cần xác định ai sở hữu đối tượng, có reuse hay không, liệu truy cập đồng thời có hợp lệ, và khi nào dừng. \`ServiceLoader\` không thay thế cơ chế lifecycle management.

## 7. Quy tắc lựa chọn để kết quả ổn định

Ví dụ dùng \`max(priority)\` ở trên đủ khi priority khác nhau, nhưng hệ thống thật cần quy tắc khi trùng priority:

1. **Lọc capability và compatibility**: loại provider sai loại, thiếu tính năng hoặc không hợp phiên bản API/runtime.
2. **Áp dụng policy**: danh sách allow/deny, quyền truy cập hoặc cấu hình của host.
3. **Xếp hạng rõ ràng**: so sánh priority, sau đó dùng ID duy nhất làm tie-breaker. Không coi thứ tự khám phá của \`ServiceLoader\` là ý nghĩa nghiệp vụ.
4. **Chỉ activate provider được chọn**: yêu cầu \`get()\` sau khi lựa chọn; nếu lỗi thì ghi log nguyên nhân và áp dụng chính sách fallback rõ ràng.
5. **Quan sát được**: log ID, phiên bản, nguyên nhân được chọn/từ chối và thời gian activation, tránh log bí mật.

Chẳng hạn, host có thể sắp xếp priority giảm dần rồi ID tăng dần để tie-break:

\`\`\`java
Comparator<ServiceLoader.Provider<TextProvider>> ranking =
    Comparator.<ServiceLoader.Provider<TextProvider>>comparingInt(
        p -> p.type().getAnnotation(PluginInfo.class).priority())
        .reversed()
        .thenComparing(
            p -> p.type().getAnnotation(PluginInfo.class).id());
\`\`\`

Đây là đoạn **minh họa đặt trong ngữ cảnh của Demo.java**, không phải source độc lập. Sau khi sắp xếp \`candidates.stream().sorted(ranking).findFirst()\`, host nhận provider có priority cao nhất; nếu bằng nhau, chọn ID đứng trước theo thứ tự từ điển. Khi metadata từ plugin chưa tin cậy, cần kiểm tra annotation có tồn tại và hợp lệ trước khi chạy comparator để tránh lỗi bất ngờ.

## 8. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Provider không được tìm thấy | Thiếu file \`META-INF/services\`, sai binary name, plugin JAR không ở class path/module layer | Kiểm tra descriptor, JAR và class loader |
| Provider bị khởi tạo khi mới lọc | Duyệt trực tiếp \`ServiceLoader<T>\` lấy instance rồi gọi \`id()\` | Duyệt \`loader.stream()\`, đọc metadata qua \`Provider.type()\` |
| \`getAnnotation(...)\` trả \`null\` | Annotation thiếu \`RUNTIME\` retention hoặc provider class không có annotation | Khai báo retention đúng và kiểm tra \`null\` |
| Provider lỗi dù chưa gọi \`get()\` | Class loading, linkage, cấu hình SPI hoặc metadata có lỗi | Bắt và xử lý lỗi khám phá/validation; không giả định discovery là miễn phí |
| Không chọn đúng provider khi bằng priority | Dựa vào thứ tự duyệt không có contract nghiệp vụ | Sắp xếp có tie-break ổn định |
| Descriptor nói một đằng, class làm một nẻo | Metadata được viết thủ công, thiếu đồng bộ | Validate lúc build và lúc load, dùng schema/version rõ ràng |
| Phí khởi tạo vẫn cao | Constructor làm việc nặng ngay khi gọi \`get()\` | Phân tách constructor và \`start()\`; quản lý lifecycle riêng |
| Plugin bị lặp/hỏng API | Host và plugin nhìn thấy các bản contract khác nhau | Chia sẻ đúng API JAR, kiểm soát class loader và compatibility |

## 9. Kiểm thử đúng hai giai đoạn

Một bộ kiểm thử tối thiểu nên xác nhận:

- **Discovery không activation**: khi chỉ gọi \`stream()\`, \`type()\`, đọc annotation và chọn, constructor của provider không được chọn chưa chạy.
- **Activation chính xác**: chỉ gọi \`get()\` của provider đã chọn; thực thi kết quả đúng và kiểm tra resource lifecycle.
- **Không có provider phù hợp**: host trả lỗi có ngữ nghĩa hoặc fallback đã định, không tự khởi tạo tất cả.
- **Metadata bất hợp lệ**: thiếu annotation, trùng ID, priority không hợp lệ, version không tương thích.
- **Provider lỗi**: lỗi SPI (\`ServiceConfigurationError\`) và lỗi khởi tạo/activation không làm host mất khả năng chẩn đoán.
- **Nhiều provider**: selection lặp lại cho kết quả ổn định theo quy tắc đã công bố; không phụ thuộc thứ tự JAR.

Có thể đo thời gian discovery và activation riêng (ví dụ \`System.nanoTime()\`) để phát hiện constructor gây chậm. Khi benchmark, nên warm up JVM và phân biệt chi phí lần đầu class loading với chi phí thường xuyên; đo một lần không đủ để kết luận hiệu năng.

## 10. Tổng kết thiết kế

Trong hệ thống runtime extensibility, **metadata phục vụ việc quyết định**, còn **instance phục vụ việc thực thi**. Bước quyết định nên càng ít tác dụng phụ càng tốt; bước thực thi nên có quản lý vòng đời, lỗi và tài nguyên rõ ràng. Trên Java 17+, \`ServiceLoader.Provider.type()\` giúp lọc bằng kiểu/annotation trước khi gọi \`get()\`, miễn là metadata phù hợp và host xử lý được giới hạn của discovery. Nếu cần duyệt catalog plugin rất lớn mà không muốn nạp class, hãy tách metadata thành descriptor ngoài class và chỉ load provider sau khi đã quyết định.
