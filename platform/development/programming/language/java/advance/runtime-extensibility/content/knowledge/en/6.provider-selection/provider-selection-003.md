# Quyết định dùng một provider, tất cả provider hoặc chuỗi xử lý

## 1. Vấn đề cốt lõi: phát hiện được nhiều provider thì gọi thế nào?

Trong hệ thống mở rộng lúc chạy của Java, một **service contract** (interface hoặc abstract type) có thể có nhiều **provider** (implementation). \`ServiceLoader\`, dependency injection container hoặc plugin registry giúp **phát hiện** các implementation, nhưng việc **lựa chọn và phối hợp thực thi** vẫn là trách nhiệm thiết kế của ứng dụng.

Ví dụ, interface \`DocumentProcessor\` có ba provider: kiểm tra định dạng, quét thông tin nhạy cảm và chuyển đổi nội dung. Có trường hợp ứng dụng chỉ cần một trong ba, có trường hợp phải gọi cả ba độc lập, và cũng có trường hợp đầu ra của bước trước là đầu vào của bước sau. Ba tình huống này dẫn đến ba mô hình khác nhau:

| Mô hình | Ý nghĩa | Câu hỏi chính |
|---|---|---|
| **Single provider** | Chọn đúng một triển khai để xử lý yêu cầu | Ai chịu trách nhiệm xử lý yêu cầu này? |
| **All providers / fan-out** | Gọi một tập provider, thường trên cùng một đầu vào | Mỗi provider cần đóng góp kết quả hay tác dụng riêng gì? |
| **Processing chain / pipeline** | Gọi các provider theo thứ tự và chuyển kết quả giữa các bước | Dữ liệu đi qua các bước biến đổi như thế nào? |

Không có mô hình nào luôn tốt nhất. Nếu hiểu sai ngữ nghĩa, ứng dụng có thể gửi giao dịch nhiều lần, làm hỏng thứ tự biến đổi, hoặc chọn provider không phù hợp.

## 2. Single provider: một yêu cầu, một nơi xử lý

**Single provider** phù hợp khi một yêu cầu có đúng một chiến lược hoặc một nơi chịu trách nhiệm: chọn bộ mã hóa theo định dạng, bộ thanh toán theo phương thức, trình điều khiển theo protocol, hoặc một handler theo loại sự kiện.

Một registry thường ánh xạ khóa sang implementation:

\`\`\`text
Request(format="csv")
       |
       v
Registry: "csv" -> CsvExporter
       |
       v
CsvExporter.export(...)
       |
       v
Response
\`\`\`

Các bước thiết kế:

1. Định nghĩa khóa lựa chọn, ví dụ \`format\`, \`protocol\`, \`tenant\` hoặc \`paymentMethod\`.
2. Kiểm tra mỗi provider khai báo khóa hoặc khả năng đáp ứng. Nếu có trùng khóa, đưa ra quy tắc rõ ràng; **fail-fast** thường tốt hơn chọn ngẫu nhiên.
3. Lựa chọn provider một lần tại ranh giới request, tránh thay đổi giữa chừng nếu registry có thể hot-reload.
4. Xác định hành vi khi không có provider: trả lỗi rõ ràng, fallback có kiểm soát, hoặc từ chối yêu cầu.
5. Ghi nhận provider thực sự được chọn để hỗ trợ debug, theo dõi phiên bản và audit.

Nếu hệ thống dùng \`ServiceLoader\`, không nên giả định thứ tự discovery là quy tắc ưu tiên nghiệp vụ. Thứ tự nạp có thể bị ảnh hưởng bởi classpath/module path, nguồn cấu hình hoặc class loader và không phù hợp để thay thế một chính sách lựa chọn tường minh.

**Trường hợp cần ưu tiên:** có thể định nghĩa điểm số, mức ưu tiên, hoặc độ chuyên biệt. Phải xác định cách phá hòa khi hai provider có cùng priority, ví dụ từ chối cấu hình mơ hồ hoặc chọn theo một khóa ổn định đã được công bố. Nếu nhiều provider nhận \`supports(request)\`, cần cân nhắc chi phí và tác dụng phụ của phép kiểm tra: \`supports\` nên nhanh và không thay đổi trạng thái nghiệp vụ.

## 3. All providers: gọi nhiều bên độc lập

Mô hình **all providers**, đôi khi gọi là broadcast hoặc fan-out, gửi cùng một sự kiện/đầu vào tới nhiều provider độc lập. Ví dụ: gửi sự kiện đã hoàn thành đơn hàng cho logger, metrics collector và audit sink; hoặc lấy kết quả từ nhiều bộ kiểm tra độc lập rồi tổng hợp.

\`\`\`text
         +--> AuditProvider -------+
Event ---+--> MetricsProvider -----+--> Tổng hợp kết quả
         +--> NotificationProvider-+
\`\`\`

Điểm phân biệt: các provider **không cần kết quả của provider trước** làm đầu vào. Chúng có thể chạy tuần tự hoặc song song, tùy độ an toàn và yêu cầu nghiệp vụ.

Cần quyết định từ đầu:

- **Phạm vi**: gọi mọi provider đã đăng ký, hay chỉ những provider hỗ trợ loại request này?
- **Đồng bộ hay bất đồng bộ**: nếu cần phản hồi ngay, gọi tuần tự dễ hiểu; nếu tác vụ độc lập và có giới hạn tài nguyên, có thể dùng executor.
- **Kết quả**: tập hợp mọi output, lấy tổng hợp/điểm số, hoặc chỉ quan tâm side effect?
- **Lỗi một provider**: dừng toàn bộ (fail-fast), thu thập lỗi để trả báo cáo, hay cho các provider còn lại chạy (best-effort)?
- **Idempotency và retry**: gửi lại sự kiện có thể khiến notification hoặc giao dịch bị thực hiện nhiều lần.
- **Thứ tự**: nếu có yêu cầu phải chạy sau một provider khác, đó có thể là pipeline/dependency graph chứ không còn fan-out độc lập.

Không nên dùng all-providers để xử lý một **thanh toán duy nhất**, vì gọi hai bộ xử lý thanh toán có thể dẫn đến hai giao dịch. Với các bộ tích hợp có side effect, phải phân biệt “đồng thời chạy mọi handler” với “chỉ chọn một handler chịu trách nhiệm”.

Chạy song song không tự động bảo đảm nhanh hơn: cần kiểm soát pool, timeout, backpressure, giới hạn cạnh tranh và cách kết thúc tác vụ còn chạy khi request bị hủy. Đồng thời, mỗi provider phải thread-safe theo cách sử dụng thực tế.

## 4. Processing chain: mỗi bước nhận kết quả của bước trước

**Chain / pipeline** phù hợp khi có các bước biến đổi hoặc kiểm tra theo thứ tự. Ví dụ, một tài liệu đi qua quá trình chuẩn hóa, che dữ liệu nhạy cảm, rồi xuất nội dung.

\`\`\`text
Input
  |
  v
NormalizeProvider
  |
  v
RedactProvider
  |
  v
FormatProvider
  |
  v
Output
\`\`\`

Đặc điểm quan trọng:

- **Thứ tự là ngữ nghĩa**: thay đổi thứ tự có thể làm khác kết quả.
- **Hợp đồng đầu vào/đầu ra**: các bước phải thống nhất kiểu dữ liệu, hoặc cần adapter để chuyển kiểu giữa các stage.
- **Chính sách lỗi**: một bước không hoàn thành thường làm pipeline không tạo ra output hợp lệ; có thể dùng cơ chế bỏ qua bước tùy chọn nhưng phải được thiết kế rõ.
- **Biến đổi trạng thái**: ưu tiên dữ liệu bất biến hoặc xác định rõ ownership nếu có mutation.
- **Khả năng bỏ qua/dừng sớm**: cần biểu diễn trong kết quả có kiểu (ví dụ accepted/rejected) thay vì dùng \`null\` mơ hồ.
- **Quan sát được**: ghi thời lượng, đầu vào/đầu ra an toàn và lỗi theo từng bước; không log dữ liệu nhạy cảm.

Một pipeline xử lý tuần tự khác với **Chain of Responsibility** trong GoF: ở Chain of Responsibility, mỗi handler có thể quyết định xử lý hoặc chuyển tiếp cho handler sau; pipeline biến đổi thường yêu cầu mọi stage áp dụng (trừ khi có chính sách skip). Hai cách có thể kết hợp nhưng không đồng nhất.

Khi pipeline có nhánh, hội tụ, điều kiện hoặc phụ thuộc chéo, mô hình **DAG/workflow engine** có thể phù hợp hơn một danh sách tuyến tính.

## 5. Ví dụ Java 17+: minh họa cả ba chiến lược

Tạo file **\`ProviderSelectionDemo.java\`**. Chương trình dùng registry và dữ liệu trong bộ nhớ, không yêu cầu thư viện ngoài. Các ví dụ chủ động không sử dụng \`ServiceLoader\` để làm rõ **chính sách thực thi** sau khi đã có danh sách provider.

\`\`\`java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.UnaryOperator;

public class ProviderSelectionDemo {
    // 1. Single provider: chọn một formatter bằng khóa.
    interface Formatter {
        String format(String input);
    }

    static final class UppercaseFormatter implements Formatter {
        public String format(String input) {
            return input.toUpperCase(java.util.Locale.ROOT);
        }
    }

    static final class BracketFormatter implements Formatter {
        public String format(String input) {
            return "[" + input + "]";
        }
    }

    static String single(Map<String, Formatter> registry,
                         String key, String input) {
        Formatter formatter = registry.get(key);
        if (formatter == null) {
            throw new IllegalArgumentException("Unknown formatter: " + key);
        }
        return formatter.format(input);
    }

    // 2. All providers: mỗi observer nhận cùng một event.
    interface Observer {
        String name();
        String onEvent(String event);
    }

    static List<String> all(List<Observer> observers, String event) {
        List<String> reports = new ArrayList<>();
        for (Observer observer : observers) {
            reports.add(observer.name() + ": " + observer.onEvent(event));
        }
        return reports;
    }

    // 3. Pipeline: đầu ra bước trước thành đầu vào bước sau.
    static String pipeline(List<UnaryOperator<String>> stages, String input) {
        String current = input;
        for (UnaryOperator<String> stage : stages) {
            current = stage.apply(current);
        }
        return current;
    }

    public static void main(String[] args) {
        Map<String, Formatter> formatters = Map.of(
            "upper", new UppercaseFormatter(),
            "bracket", new BracketFormatter()
        );
        System.out.println("Single: " +
            single(formatters, "upper", "java"));

        Observer audit = new Observer() {
            public String name() { return "audit"; }
            public String onEvent(String event) {
                return "recorded " + event;
            }
        };
        Observer metric = new Observer() {
            public String name() { return "metric"; }
            public String onEvent(String event) {
                return "counted " + event;
            }
        };
        System.out.println("All: " +
            all(List.of(audit, metric), "order-created"));

        List<UnaryOperator<String>> stages = List.of(
            String::strip,
            s -> s.replace(" ", "-"),
            s -> "[" + s + "]"
        );
        System.out.println("Pipeline: " +
            pipeline(stages, "  hello world  "));
    }
}
\`\`\`

Biên dịch và chạy:

\`\`\`bash
javac ProviderSelectionDemo.java
java ProviderSelectionDemo
\`\`\`

Kết quả chính xác:

\`\`\`text
Single: JAVA
All: [audit: recorded order-created, metric: counted order-created]
Pipeline: [hello-world]
\`\`\`

Giải thích:

- \`single\` chỉ gọi formatter được xác định bởi key \`upper\`. \`Map.of\` phù hợp registry cố định và không cho phép thay đổi sau khi tạo.
- \`all\` gọi cả \`audit\` và \`metric\` với cùng event \`order-created\`. Ở đây các kết quả được trả về theo thứ tự \`List.of(audit, metric)\`, nhưng không có cam kết thứ tự tương tự cho mọi nguồn discovery.
- \`pipeline\` bắt đầu với chuỗi có khoảng trắng, \`strip\` loại khoảng trắng đầu/cuối, bước thứ hai đổi khoảng trắng giữa hai từ thành dấu nối, bước thứ ba bọc trong ngoặc vuông. Nếu đổi thứ tự các stage, đầu ra có thể khác.

Ví dụ là **đăng ký tĩnh**, chưa phải hot plugin loading. Khi dùng class loader riêng hoặc \`ServiceLoader\`, danh sách provider sau discovery vẫn cần đi qua các quy tắc chọn, kiểm tra phiên bản, ordering và vòng đời tương tự.

## 6. Chọn mô hình theo yêu cầu

| Tình huống | Gợi ý | Vì sao |
|---|---|---|
| Chọn một bộ xuất \`pdf\` hoặc \`csv\` | Single | Một đầu ra thuộc một định dạng cụ thể |
| Chọn payment gateway theo nhà phát hành thẻ | Single | Một nơi chịu trách nhiệm thanh toán |
| Gửi sự kiện cho logging, metrics và audit | All providers | Các subscriber độc lập |
| Chạy nhiều bộ phân tích để thu thập nhận định | All providers + aggregate | Cần kết quả của nhiều nguồn |
| Chuẩn hóa → che dữ liệu → serialize | Pipeline | Mỗi bước phụ thuộc kết quả bước trước |
| Lần lượt thử các provider đến khi một bên chấp nhận | Chain of Responsibility/fallback | Có quy tắc dừng, không chạy tất cả |
| Nhiều bước song song rồi gom và kiểm tra chung | DAG/workflow | Phụ thuộc không tuyến tính |

Một cách chọn nhanh là đặt ba câu hỏi:

1. **Nếu chỉ một provider hoàn thành là đủ và các provider còn lại là lựa chọn thay thế?** Sử dụng single hoặc fallback có quy tắc.
2. **Nếu tất cả provider đều phải thấy cùng một sự kiện/đầu vào, và không phụ thuộc output của nhau?** Sử dụng fan-out.
3. **Nếu output của bước A là input của bước B hoặc thứ tự tạo ra khác biệt?** Sử dụng pipeline/chain.

Đừng chọn all-providers chỉ vì \`ServiceLoader\` trả về \`Iterable\`. Cơ chế phát hiện trả về **tập ứng viên**, không quyết định cách thực thi nghiệp vụ.

## 7. Quy tắc thứ tự và ưu tiên trong hệ plugin

Thứ tự provider là nguồn lỗi phổ biến khi ứng dụng phát triển. Nếu cần thứ tự xác định, hãy khai báo metadata như \`order\`, \`phase\` hoặc danh sách dependency. Khi hai provider cùng order, chọn quy tắc phá hòa minh bạch hoặc từ chối cấu hình. Đừng để thứ tự \`HashMap\`, classpath, đường dẫn JAR hoặc tình cờ từ quá trình scanning làm quyết định nghiệp vụ.

Ví dụ một pipeline có giai đoạn \`VALIDATE\`, \`TRANSFORM\`, \`PERSIST\` có thể yêu cầu provider triển khai một \`Stage\` cụ thể. Trước kích hoạt, host sắp xếp provider dựa trên metadata được kiểm tra; phát hiện vòng phụ thuộc; và xác minh mỗi stage phù hợp vị trí. Nếu registry hot-reload, hãy chụp một **snapshot bất biến** cho toàn bộ request để tránh việc provider biến mất hoặc thứ tự thay đổi trong quá trình xử lý.

Đối với single-provider selection có nhiều candidate cùng thỏa \`supports\`, có thể dùng độ ưu tiên, độ đặc hiệu hay phiên bản đã pin, nhưng ưu tiên tuyệt đối không được che giấu xung đột cấu hình hoặc rủi ro lựa chọn sai nhà cung cấp.

## 8. Xử lý lỗi: fail-fast, best-effort, fallback và rollback

Ba mô hình có ngữ nghĩa lỗi khác nhau:

**Single:** lỗi của provider được chọn là lỗi của request, trừ khi có fallback được xác định trước. Fallback chỉ an toàn khi biết provider đầu tiên chưa thực hiện side effect không thể đảo ngược. Ví dụ timeout khi gọi payment gateway không có nghĩa giao dịch chưa được xử lý; tự động thử gateway khác có thể tạo thanh toán trùng.

**All providers:** có thể chọn **fail-fast** nếu toàn bộ đóng góp là bắt buộc; hoặc **best-effort** khi một observer lỗi không cản trở các observer còn lại. Cần trả báo cáo kết quả theo provider và phân biệt thành công, thất bại, timeout, đã bỏ qua. Với phát sự kiện bất đồng bộ, cân nhắc outbox, retry có giới hạn, idempotency key và dead-letter queue cho thông điệp không xử lý được.

**Pipeline:** lỗi của stage thường ngăn các bước sau chạy. Nếu các bước đã ghi dữ liệu bên ngoài, rollback có thể cần transaction (nếu cùng phạm vi hỗ trợ) hoặc **compensation** (saga) vì không thể đảo ngược toàn bộ chỉ bằng exception. Dữ liệu trung gian nên có ownership rõ ràng để tránh còn trạng thái nửa chừng.

Có thể mô hình hóa kết quả với kiểu rõ ràng như \`Success<T>\`, \`Failure(code, detail)\`, \`Skipped(reason)\` hoặc record/enum để tránh trả \`null\` gây mơ hồ. Log phải ghi \`pluginId\`, \`pluginVersion\`, \`requestId\`, giai đoạn và thời lượng theo cách không làm lộ dữ liệu nhạy cảm.

## 9. Luồng xử lý đồng thời và quản lý vòng đời

Trong host chạy nhiều request, lựa chọn provider gắn với quy tắc thread-safety và hot reload.

- **Registry:** immutable snapshot hoặc cấu trúc thread-safe giúp tránh race khi đăng ký/tháo provider. Chỉ thread-safe ở registry không đủ nếu implementation giữ trạng thái mutable thiếu đồng bộ.
- **All providers chạy song song:** tránh chia sẻ mutable input; đặt giới hạn concurrency, timeout và chính sách hủy. Kết quả có thể đến không theo thứ tự gọi, vì vậy tổng hợp theo ID hoặc thứ tự xác định khi cần.
- **Pipeline:** nếu các stage có side effect, cần quy tắc truy vết và dữ liệu trung gian. Không thể song song hóa tùy tiện các bước có quan hệ phụ thuộc.
- **Hot replacement:** một request nên giữ provider snapshot đã chọn; phiên bản cũ ngừng nhận request mới nhưng hoàn thành tác vụ đang chạy trước khi đóng tài nguyên.
- **Tài nguyên và class loader:** host phải quản lý \`close\`, thread, subscription và reference còn sống. Việc \`URLClassLoader.close()\` không tức thì giải phóng class hay mọi instance plugin.

Một plugin chạy trong cùng JVM thường có quyền đáng kể của tiến trình. Thứ tự nạp và cách chọn provider không thay thế kiểm tra metadata, compatibility, authenticity và quy tắc tin cậy trước khi thực thi mã bên thứ ba. Khi plugin không tin cậy, cân nhắc cô lập ngoài tiến trình.

## 10. Áp dụng với ServiceLoader

\`ServiceLoader\` là cơ chế **discovery** tích hợp Java. Giả sử interface \`TaskProvider\` đã có và các JAR khai báo provider đúng quy tắc, host có thể xây danh sách ứng viên:

\`\`\`java
// Đoạn tích hợp vào hệ thống có TaskProvider, không phải tệp chạy độc lập.
List<TaskProvider> discovered = new ArrayList<>();
for (TaskProvider provider : ServiceLoader.load(TaskProvider.class)) {
    discovered.add(provider);
}
\`\`\`

Sau bước discovery, host nên:

1. Kiểm tra hợp đồng và metadata của từng provider theo chính sách tin cậy.
2. Áp dụng cấu hình để quyết định single, all hoặc pipeline. Không mặc định \`forEach(provider::execute)\` trong mọi trường hợp.
3. Xây một registry/snapshot có thứ tự hoặc khóa lựa chọn rõ ràng.
4. Thực thi với chính sách lỗi, timeout và lifecycle phù hợp.

Trong thực tế, iteration của \`ServiceLoader\` có thể khiến provider được khởi tạo trong quá trình duyệt; vì vậy nếu cần kiểm tra JAR trước khi **bất kỳ mã plugin nào chạy**, phải thực hiện validation artifact/manifest ở bước trước, không coi việc iterate qua \`ServiceLoader\` là một thao tác discovery vô hại với plugin chưa được tin cậy. \`ServiceLoader.reload()\` chỉ xóa cache provider của loader; nó không tự thêm JAR ngoài phạm vi class loader.

## 11. Những lỗi thường gặp và checklist thiết kế

- Coi \`ServiceLoader\` trả về nhiều provider là yêu cầu gọi tất cả.
- Dùng \`findFirst()\` để chọn provider mà không có quy tắc priority/identity.
- Để các plugin có side effect cùng nhận một request chỉ nên xử lý một lần.
- Tưởng fan-out song song luôn nhanh và không cần backpressure hay kiểm soát lỗi.
- Thứ tự pipeline không được khai báo; kết quả thay đổi khi thứ tự discovery đổi.
- Dùng fallback ngay sau timeout của thao tác có thể đã commit bên ngoài.
- Không kiểm soát duplicate key/provider hoặc thay đổi registry trong lúc request chạy.
- Dùng exception chung cho mọi lỗi rồi mất thông tin provider và stage gây lỗi.
- Không có kiểm thử contract cho các provider và không mô phỏng trường hợp thiếu, trùng, lỗi hoặc chậm.

Trước khi triển khai, kiểm tra: **mục tiêu nghiệp vụ** là một / tất cả / chuỗi; **nguồn quyết định** là khóa/cấu hình/metadata; **thứ tự** có được xác định không; **kiểu kết quả và chính sách lỗi** có rõ không; **side effect và retry** có an toàn không; **thread-safety, timeout, lifecycle, bảo mật** có phù hợp với môi trường chạy hay không.

**Ghi nhớ:** provider là đơn vị cung cấp hành vi, còn **selection policy** là luật của host để dùng hành vi đó. Chọn **một provider** cho quyết định có một chủ thể chịu trách nhiệm, chọn **tất cả** khi các đóng góp độc lập đều cần thiết, và chọn **chuỗi xử lý** khi thứ tự và dữ liệu trung gian là một phần của hợp đồng nghiệp vụ.
