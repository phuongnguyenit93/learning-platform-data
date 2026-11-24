# Script adapter

Script adapter cho phép đưa một đoạn script vào luồng xử lý message của Spring Integration. Script có thể đảm nhiệm một bước chuyển đổi payload, kiểm tra điều kiện, định tuyến hoặc xử lý nghiệp vụ nhỏ. Nhờ vậy, ứng dụng có thể thay đổi một số quy tắc ánh xạ và xử lý mà không phải viết lại toàn bộ endpoint Java.

Trong module Spring Integration Adapters, script vẫn nằm ở ranh giới của một luồng message: message đi vào từ channel, endpoint cung cấp dữ liệu đầu vào cho script, kết quả được chuyển thành message tiếp theo hoặc quyết định message có tiếp tục hay không. Cần thiết kế rõ hợp đồng giữa Java và script, vòng đời của script engine và cách xử lý lỗi trước khi dùng cách này trong môi trường nhiều instance.

## 1. Script adapter đứng ở đâu trong IntegrationFlow?

Spring Integration làm việc với `Message<?>`, gồm payload và headers. Script adapter nhận message hoặc các phần dữ liệu được ánh xạ từ message, thực thi script, rồi trả về kết quả cho endpoint đang sử dụng nó.

| Vai trò endpoint | Kết quả script | Hành vi của luồng |
|---|---|---|
| Transformer | Payload đã chuẩn hóa hoặc một object mới | Phát message mới, thường giữ lại các header hiện có nếu transformer chỉ trả payload |
| Filter | Giá trị boolean | `true` cho message đi tiếp; `false` loại message khỏi nhánh đầu ra |
| Router | Tên channel hoặc giá trị định tuyến theo hợp đồng đã cấu hình | Chuyển message đến channel tương ứng |
| Service activator | Kết quả xử lý, hoặc không có kết quả | Thực hiện một hành động; nếu có kết quả trả về thì kết quả có thể đi tiếp qua output channel |

Không phải mọi script đều nên được dùng như một service activator. Nếu script chỉ biến đổi cấu trúc dữ liệu, hãy đặt nó ở transformer. Nếu script chỉ quyết định có tiếp tục hay không, dùng filter. Nếu script chọn đích đến, dùng router. Chọn đúng vai trò giúp hành vi của luồng dễ đọc và tránh nhồi nhiều trách nhiệm vào một đoạn script.

Spring Integration có hỗ trợ scripting dựa trên JSR-223 khi ứng dụng cung cấp script engine tương ứng. JSR-223 là API Java để tìm và gọi các scripting engine; bản thân JDK không bảo đảm có sẵn engine cho mọi ngôn ngữ. Tùy phiên bản Spring Integration và dependency được cài đặt, có thể khai báo script trực tiếp như phần xử lý của endpoint hoặc bọc script trong một POJO rồi đăng ký POJO đó làm transformer/service activator. Cú pháp XML và Java DSL cần đối chiếu với phiên bản thư viện của dự án.

## 2. Khi nào nên dùng script?

Script phù hợp với logic ngắn, có đầu vào/đầu ra rõ và thường thay đổi theo quy tắc tích hợp, ví dụ:

- Đổi tên trường giữa payload của đối tác và mô hình nội bộ.
- Chuẩn hóa định dạng ngày, số tiền hoặc mã trạng thái.
- Kiểm tra một số điều kiện đơn giản trước khi gửi message sang channel khác.
- Chuyển một mã loại sự kiện thành tên channel đích.
- Tạo payload trung gian từ dữ liệu nhận qua HTTP, file hoặc broker.

Nên dùng Java/POJO khi xử lý có nhiều nhánh phức tạp, cần transaction rõ ràng, thao tác với nhiều repository, gọi nhiều dịch vụ, cần tối ưu hiệu năng hoặc cần kiểm soát kiểu dữ liệu chặt chẽ. Script dài thường khó debug, refactor và kiểm tra bằng công cụ IDE hơn mã Java có kiểu tĩnh. Một quy tắc quan trọng có thể được triển khai trong POJO và được gọi từ script hoặc endpoint; không nên biến script thành nơi chứa toàn bộ nghiệp vụ cốt lõi.

Trước khi chọn script, hãy xác định ai được phép thay đổi nó, cách kiểm duyệt và phát hành, script có cần thay đổi khi ứng dụng đang chạy hay không, và điều gì xảy ra khi script lỗi. Nếu không có câu trả lời cho các câu hỏi đó, lợi ích linh hoạt có thể nhỏ hơn chi phí vận hành.

## 3. Hợp đồng dữ liệu giữa message và script

Không nên để script tự đoán cấu trúc message hoặc tự truy cập toàn bộ context của ứng dụng. Hãy quy định chính xác những biến script được nhận. Một hợp đồng đơn giản có thể gồm:

| Tên biến | Nội dung | Quy ước |
|---|---|---|
| `payload` | Payload của message | Dùng schema đã thống nhất; ví dụ `Map`, DTO hoặc chuỗi JSON đã parse |
| `headers` | Các header được cho phép | Chỉ cung cấp header cần cho xử lý, không đưa credential hoặc thông tin nội bộ không liên quan |
| `message` | Toàn bộ message, nếu thật sự cần | Chỉ dùng khi script cần metadata ngoài payload; tránh làm script phụ thuộc sâu vào Spring Messaging |
| `correlationId` | Mã liên kết luồng xử lý | Có thể ánh xạ từ header tương ứng để ghi log hoặc tạo reply |

Đây là hợp đồng do ứng dụng định nghĩa; tên biến không tự xuất hiện trong mọi JSR-223 engine. Adapter phải tạo bindings hoặc context và đưa dữ liệu vào theo đúng tên đã công bố. Nếu thay đổi tên biến, kiểu payload hoặc ý nghĩa header, hãy xem đó là thay đổi hợp đồng và cập nhật kiểm thử cùng script liên quan.

Nên truyền một tập header đã chọn thay vì toàn bộ header nếu script chỉ cần một vài giá trị. Ví dụ, script chuẩn hóa đơn hàng có thể chỉ nhận `sourceSystem`, `schemaVersion` và `correlationId`. Không đưa token xác thực, cookie, thông tin kết nối hoặc đối tượng chứa quyền truy cập vào context script.

## 4. Ví dụ: dùng Groovy làm transformer

Giả sử hệ thống nhận message đơn hàng dưới dạng map. Payload đầu vào có thể chứa `id`, `total` và `currency`; header `sourceSystem` xác định hệ thống gửi. Script kiểm tra tổng tiền rồi tạo cấu trúc chuẩn hóa cho luồng phía sau.

Script `order-normalize.groovy`:

```groovy
def total = new BigDecimal(payload.total.toString())

if (total.signum() <= 0) {
    throw new IllegalArgumentException("Order total must be positive")
}

return [
    orderId: payload.id.toString(),
    total: total,
    currency: payload.currency.toString().toUpperCase(),
    source: headers['sourceSystem']
]
```

Script chỉ đọc payload và header được cấp, sau đó trả về một map mới. Nó không gọi repository, không gửi HTTP request và không tự phát message sang broker. Những hành động đó thuộc trách nhiệm của các endpoint khác trong flow.

Đoạn Java sau minh họa một POJO transformer dùng JSR-223. Ví dụ cố ý tạo bindings mới cho từng lần thực thi và đồng bộ hóa lời gọi vì không phải mọi `ScriptEngine` đều bảo đảm an toàn khi nhiều thread dùng chung một instance:

```java
import java.util.Map;
import javax.script.Bindings;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
public class OrderScriptAdapter {

    private static final String SCRIPT = """
        def total = new BigDecimal(payload.total.toString())
        if (total.signum() <= 0) {
            throw new IllegalArgumentException('Order total must be positive')
        }
        return [
            orderId: payload.id.toString(),
            total: total,
            currency: payload.currency.toString().toUpperCase(),
            source: headers['sourceSystem']
        ]
        """;

    private final ScriptEngine engine;

    public OrderScriptAdapter() {
        this.engine = new ScriptEngineManager().getEngineByName("groovy");
        if (this.engine == null) {
            throw new IllegalStateException(
                "No JSR-223 engine named 'groovy' is available");
        }
    }

    public synchronized Object transform(
            Message<Map<String, Object>> message) throws ScriptException {
        Bindings bindings = engine.createBindings();
        bindings.put("payload", message.getPayload());
        Object sourceSystem = message.getHeaders().get("sourceSystem");
        if (sourceSystem == null) {
            throw new IllegalArgumentException("Missing required header: sourceSystem");
        }
        bindings.put("headers", Map.of("sourceSystem", sourceSystem));
        return engine.eval(SCRIPT, bindings);
    }
}
```

Flow dùng POJO như một transformer:

```java
@Bean
IntegrationFlow normalizeOrders(OrderScriptAdapter scriptAdapter) {
    return IntegrationFlow.from("orders.raw")
        .transform(scriptAdapter, "transform")
        .channel("orders.normalized")
        .get();
}
```

Trong ví dụ, ứng dụng phải thêm dependency cung cấp JSR-223 engine Groovy tương thích với phiên bản Java đang chạy. Nếu `getEngineByName("groovy")` trả về `null`, engine chưa được cài đặt hoặc tên engine không khớp với provider. Tên engine và dependency phải được kiểm tra trong môi trường build/deploy thực tế; không nên giả định rằng chỉ cần có JDK là đã có Groovy engine.

Ví dụ Java dùng text block, vì vậy cần Java 15 trở lên; với phiên bản Java cũ hơn, có thể chuyển nội dung script thành chuỗi thông thường hoặc đọc từ resource.

`synchronized` là lựa chọn đơn giản để minh họa việc bảo vệ một engine dùng chung. Nó tuần tự hóa các lần thực thi và có thể giới hạn throughput. Với tải lớn, hãy cân nhắc tạo engine theo từng worker hoặc dùng pool engine; chỉ dùng chung một engine khi tài liệu của engine cụ thể xác nhận chính sách concurrency. Nếu engine hỗ trợ biên dịch script, có thể biên dịch một lần rồi tái sử dụng đối tượng đã biên dịch theo đúng bảo đảm thread-safety của provider.

## 5. Dùng script cho filter, router và service activator

Khi cùng dùng một script engine, có thể xây dựng các POJO method có hợp đồng trả về rõ ràng rồi gắn chúng vào endpoint tương ứng.

**Filter:** method trả về `boolean`. `true` cho message đi tiếp; `false` loại message khỏi output của filter. Nếu cần lưu message bị loại để kiểm tra, cấu hình discard channel hoặc nhánh xử lý riêng thay vì âm thầm bỏ qua.

**Router:** method trả về giá trị định tuyến đã được giới hạn trong danh sách channel hợp lệ. Không cho script tùy ý tạo tên bean hoặc channel từ input bên ngoài. Nếu giá trị không hợp lệ, đưa message sang error channel hoặc nhánh lỗi có chủ đích.

**Service activator:** method thực hiện hành động hoặc trả kết quả. Các thao tác ghi dữ liệu, gọi dịch vụ và phát message nên được thể hiện rõ ở các thành phần có thể quan sát và kiểm thử. Script chỉ nên điều phối quy tắc nhỏ, không nên giữ connection hoặc tự quản lý transaction.

Hãy thống nhất cách xử lý kết quả `null`. Với transformer, không có payload đầu ra thường đồng nghĩa không phát message tiếp theo; với service activator, `null` có thể biểu thị không có reply. Nếu `null` là dữ liệu hợp lệ, hãy bọc kết quả trong một kiểu rõ ràng hoặc trả về object biểu diễn trạng thái thay vì để endpoint hiểu nhầm là không có kết quả.

## 6. Lỗi thực thi và retry

Script có thể lỗi vì cú pháp không hợp lệ, biến thiếu, kiểu dữ liệu không đúng, dữ liệu đầu vào vi phạm điều kiện hoặc lỗi trong engine. Cần phân loại lỗi để chọn cách xử lý:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi script/cấu hình | Thiếu dấu ngoặc, script không biên dịch được, không tìm thấy engine | Phát hiện khi khởi động hoặc kiểm tra lúc triển khai; không retry message vô hạn |
| Lỗi dữ liệu | Thiếu `id`, `total` không chuyển được sang số | Đưa message vào luồng lỗi/quarantine kèm nguyên nhân; sửa dữ liệu hoặc hợp đồng trước khi replay |
| Lỗi tạm thời bên ngoài | Script gọi một dịch vụ và dịch vụ tạm thời lỗi | Tốt hơn nên tách lời gọi dịch vụ thành endpoint riêng; retry có giới hạn ở endpoint đó |
| Lỗi lập trình | Null không dự kiến, ép kiểu sai, điều kiện xử lý thiếu | Ghi nhận exception và message ID, sửa script hoặc code rồi phát lại có kiểm soát |

Không retry tất cả exception theo cùng một chính sách. Lỗi cú pháp hoặc lỗi dữ liệu cố định sẽ tiếp tục thất bại ở mọi lần thử. Nếu script nằm trong flow đồng bộ, exception có thể truyền ngược về caller. Nếu flow bất đồng bộ, cần cấu hình error channel hoặc error handler phù hợp để lỗi không bị mất trong log chung.

Khi gửi message lỗi sang dead-letter channel, nên lưu message gốc, `messageId`, `correlationId`, phiên bản script, thời điểm và loại exception. Cẩn trọng với payload chứa dữ liệu cá nhân hoặc bí mật; áp dụng chính sách che dữ liệu và thời hạn lưu trữ. Chỉ replay sau khi đã xác định nguyên nhân và biết script phiên bản nào sẽ xử lý message đó.

## 7. Quản lý script và an toàn thực thi

Script là mã thực thi trong tiến trình ứng dụng. Một JSR-223 engine thông thường không tự tạo sandbox an toàn cho mã không tin cậy. Script có thể truy cập classpath, file, mạng hoặc API Java tùy engine và cách host cấp context. Vì vậy:

- Chỉ nạp script từ nguồn được kiểm soát, review và phát hành cùng quy trình phần mềm.
- Không cho người dùng cuối gửi script tùy ý để chạy trong JVM của ứng dụng.
- Không cấp `ApplicationContext`, bean factory, connection, credential hoặc đối tượng có quyền rộng vào bindings.
- Hạn chế API được phép gọi theo khả năng của engine; không coi việc ẩn một biến trong bindings là sandbox bảo mật.
- Giới hạn thời gian thực thi, kích thước input và mức độ tiêu thụ tài nguyên theo khả năng engine/runtime. Nếu cần chạy mã không tin cậy, dùng tiến trình hoặc dịch vụ cô lập có ranh giới bảo mật thực sự.
- Ghi nhận phiên bản hoặc checksum script để truy vết kết quả đã xử lý bằng logic nào.

Đối với script đóng gói trong ứng dụng, classpath resource giúp phiên bản script đi cùng phiên bản ứng dụng và dễ rollback. Nếu tải script từ kho cấu hình bên ngoài để thay đổi độc lập, cần quy định xác thực nguồn, kiểm tra cú pháp trước khi kích hoạt, cache, version, rollback và hành vi khi kho script không truy cập được. Không nên âm thầm tải lại script ở mỗi message vì sẽ làm tăng độ trễ và khiến hai replica có thể chạy hai phiên bản khác nhau.

## 8. Hiệu năng và vận hành nhiều replica

Script engine có chi phí khởi tạo, parse/compile và thực thi. Để kiểm soát tải:

1. Khởi tạo engine và nạp script theo vòng đời bean hoặc worker, không tạo engine mới cho từng message nếu không có lý do.
2. Tái sử dụng script đã biên dịch khi engine hỗ trợ và bảo đảm việc dùng chung an toàn.
3. Tạo bindings riêng cho từng message để tránh dữ liệu của message trước rò sang lần chạy sau.
4. Giới hạn số thread chạy script và độ dài queue phía trước; không để script chậm làm tăng backlog vô hạn.
5. Đo thời gian thực thi, tỷ lệ lỗi, số lần timeout, số message bị loại và phiên bản script đang hoạt động.

Mỗi replica có thể có một engine và cache script riêng. Khi triển khai phiên bản mới, hãy bảo đảm các replica cùng nhận đúng phiên bản đã phát hành hoặc có cơ chế chuyển đổi tương thích. Nếu script được cập nhật động, cần tránh tình trạng một phần replica chạy bản mới trong khi phần còn lại chạy bản cũ mà không có kiểm soát. Các biến toàn cục hoặc trạng thái lưu trong engine không nên được dùng làm nơi lưu trạng thái nghiệp vụ vì chúng không được chia sẻ nhất quán giữa các replica và có thể mất khi pod khởi động lại.

## 9. Kiểm thử script adapter

Kiểm thử cần xác nhận cả logic script lẫn hợp đồng của endpoint:

- **Kiểm thử script độc lập:** cung cấp payload và bindings mẫu; xác nhận output, kiểu dữ liệu và exception.
- **Kiểm thử adapter:** xác nhận adapter tạo đúng bindings, chỉ truyền header được cho phép và chọn đúng engine.
- **Kiểm thử IntegrationFlow:** gửi message vào input channel, kiểm tra output channel, header được giữ/chuyển đổi và hành vi filter/router.
- **Kiểm thử lỗi:** thử payload thiếu trường, sai kiểu, script lỗi cú pháp và engine không tồn tại; xác nhận message đi đến error path dự kiến.
- **Kiểm thử concurrency:** chạy nhiều message song song để phát hiện race condition, bindings dùng chung hoặc engine không an toàn thread.
- **Kiểm thử triển khai:** xác nhận engine dependency có mặt trong artifact/runtime container và script resource được đóng gói đúng đường dẫn.

Không chỉ kiểm tra một ví dụ thành công. Hãy bổ sung trường hợp biên như số tiền bằng 0, trường thiếu, chuỗi rỗng, header không có và schema version không được hỗ trợ. Với script có nhiều nhánh, dữ liệu kiểm thử nên bao phủ từng nhánh quan trọng.

## 10. Quy trình đưa script vào production

1. Xác định endpoint cần script và chọn transformer, filter, router hay service activator.
2. Viết hợp đồng đầu vào/đầu ra: payload schema, header được phép, kiểu trả về và cách biểu diễn lỗi.
3. Chọn engine và xác nhận dependency tương thích với Java cùng phiên bản Spring Integration đang dùng.
4. Viết script nhỏ, có phiên bản; review cùng mức độ cẩn thận như mã nguồn ứng dụng.
5. Kiểm thử độc lập, adapter, IntegrationFlow, lỗi và concurrency.
6. Đóng gói script hoặc triển khai nguồn script đã kiểm soát; kiểm tra script có thể nạp trước khi nhận message.
7. Theo dõi thời gian thực thi, lỗi, backlog và phiên bản script trên từng replica; chuẩn bị rollback và replay message lỗi.

Một script adapter tốt có đầu vào giới hạn, đầu ra dễ dự đoán, không giữ trạng thái giữa các message và không thực hiện tác dụng phụ ngoài hợp đồng đã định. Khi script bắt đầu cần nhiều phụ thuộc, nhiều transaction hoặc logic khó kiểm thử, hãy chuyển phần xử lý đó thành POJO/service có kiểu rõ ràng và để script chỉ làm nhiệm vụ chuyển đổi nhỏ nếu vẫn còn lợi ích thực tế.
