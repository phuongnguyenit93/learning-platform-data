# Ứng dụng cho request ID, thông tin người dùng và cấu hình theo yêu cầu

## 1. Phạm vi bài học và phiên bản Java

Một yêu cầu đọc đơn hàng thường cần nhiều lớp cùng biết mã yêu cầu, người đang thao tác và cấu hình đã chọn cho yêu cầu đó. Nếu truyền tất cả qua mọi phương thức, những lớp trung gian phải nhận thêm các tham số mà chúng không sử dụng.

Scoped Values phù hợp khi những dữ liệu này được thiết lập ở đầu luồng xử lý và được đọc ở các lời gọi phía dưới. Bài học tập trung vào ba ứng dụng của chương Scoped Value: liên kết log bằng request ID, cung cấp danh tính đã xác thực và áp dụng cấu hình theo yêu cầu.

Trong Java 22, `ScopedValue` còn là API preview. Tính năng này đã xuất hiện trước Java 22 và trở thành API chính thức ở Java 25. Bài dùng API ổn định từ Java 25, với các thao tác vẫn có trong tài liệu Java 27; các ví dụ không cần bật preview chỉ để sử dụng Scoped Values. Xem [API Java 22](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/ScopedValue.html), [thông báo của nhóm Java về việc hoàn tất tính năng ở Java 25](https://inside.java/2025/10/20/jdk-25-performance-improvements/#enhancements-in-jdk-libraries) và [API Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html).

## 2. Chọn dữ liệu nào để đưa vào ngữ cảnh

| Loại dữ liệu | Giá trị minh họa | Nơi thiết lập | Nơi sử dụng |
| --- | --- | --- | --- |
| Request ID | `req-1001` | Bộ phận tiếp nhận yêu cầu | Log, thông tin chẩn đoán, lời gọi dịch vụ khác |
| Danh tính người dùng | User ID, tenant ID, quyền đã xác định | Sau bước xác thực và xác định tenant hợp lệ | Kiểm tra quyền, chọn phạm vi dữ liệu, ghi nhận người thao tác |
| Cấu hình theo yêu cầu | Locale, chế độ hiển thị, phiên bản cấu hình | Sau khi tổng hợp chính sách và tùy chọn được phép | Định dạng kết quả, chọn hành vi phụ trợ, giải thích kết quả |

Nên tiếp tục truyền tường minh những đầu vào trực tiếp của nghiệp vụ. Ví dụ, `orderId` là đối tượng mà thao tác đọc đơn hàng cần xử lý, nên xuất hiện trong chữ ký phương thức. Request ID chủ yếu phục vụ việc quan sát hoạt động của thao tác đó, nên có thể được cung cấp qua ngữ cảnh.

Cách phân chia này giúp người đọc nhận ra phương thức đang làm việc với đơn hàng nào, trong khi các lớp ghi log không cần nhận thêm request ID từ mọi lớp trung gian.

## 3. Vòng đời của một ngữ cảnh yêu cầu

Luồng xử lý đề xuất:

```text
Tiếp nhận yêu cầu
    |
    +-- Tạo hoặc chuẩn hóa request ID
    +-- Xác thực danh tính và tenant
    +-- Tính cấu hình hiệu lực
    |
    +-- Thiết lập các binding bằng where(...).call(...)
            |
            +-- Lớp điều phối
            +-- Lớp nghiệp vụ: đọc danh tính, kiểm tra quyền
            +-- Lớp dữ liệu: nhận tenant/user/order ID tường minh
            +-- Log: đọc request ID
            |
        Trả kết quả hoặc ném ngoại lệ
    |
Các binding của yêu cầu kết thúc
```

`ScopedValue.where(key, value)` tạo một `Carrier` chứa ánh xạ. Việc tạo carrier chưa làm ngữ cảnh có hiệu lực; `run(...)` hoặc `call(...)` mới thực thi công việc với các binding đó. Dùng `run` cho thao tác không trả kết quả và `call` cho thao tác trả kết quả.

Khi công việc kết thúc, kể cả bằng ngoại lệ, binding trước đó được khôi phục; nếu trước đó chưa có binding thì scoped value trở về trạng thái chưa được gán trong thread đang chạy. Không cần viết thao tác xóa binding ở cuối yêu cầu. Hành vi này được quy định trong [API ScopedValue.Carrier của Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html).

## 4. Ví dụ hoàn chỉnh: đọc đơn hàng trong ngữ cảnh yêu cầu

Ví dụ sau dùng ba khóa riêng vì cấu hình có thể cần được thay thế trong một phạm vi con, trong khi request ID và danh tính vẫn giữ nguyên. Toàn bộ lớp có thể đặt trong tệp `RequestScopeDemo.java`.

Đây là chương trình minh họa độc lập. Danh tính trong `main` là dữ liệu mẫu; trong ứng dụng thực tế, chỉ gọi `handleVerifiedRequest` sau khi lớp tiếp nhận đã xác thực người dùng, chuẩn hóa request ID và tính cấu hình hợp lệ.

```java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class RequestScopeDemo {

    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    private static final ScopedValue<Identity> USER =
            ScopedValue.newInstance();

    private static final ScopedValue<RequestOptions> OPTIONS =
            ScopedValue.newInstance();

    record Identity(
            String userId,
            String tenantId,
            Set<String> permissions) {

        Identity {
            requireText(userId, "userId");
            requireText(tenantId, "tenantId");
            permissions = Set.copyOf(permissions);
        }
    }

    record RequestOptions(Locale locale, String configVersion) {

        RequestOptions {
            Objects.requireNonNull(locale, "locale");
            requireText(configVersion, "configVersion");
        }

        RequestOptions withLocale(Locale nextLocale) {
            return new RequestOptions(nextLocale, configVersion);
        }
    }

    record Order(
            String id,
            String tenantId,
            String ownerId,
            BigDecimal amount) {
    }

    // Dữ liệu trong bộ nhớ chỉ phục vụ ví dụ.
    private static final Map<String, Order> ORDERS = Map.of(
            "O-101",
            new Order(
                    "O-101",
                    "shop-a",
                    "u-01",
                    new BigDecimal("1250000.00")),
            "O-202",
            new Order(
                    "O-202",
                    "shop-b",
                    "u-02",
                    new BigDecimal("700000.00"))
    );

    public static void main(String[] args) {
        Identity verifiedUser = new Identity(
                "u-01",
                "shop-a",
                Set.of("orders:read"));

        RequestOptions options = new RequestOptions(
                Locale.forLanguageTag("vi-VN"),
                "cfg-42");

        System.out.println(
                "Trước yêu cầu: " + REQUEST_ID.isBound());

        String result = handleVerifiedRequest(
                "req-1001",
                verifiedUser,
                options,
                "O-101");

        System.out.println(result);

        System.out.println(
                "Sau yêu cầu: " + REQUEST_ID.isBound());
    }

    static String handleVerifiedRequest(
            String internalRequestId,
            Identity verifiedUser,
            RequestOptions effectiveOptions,
            String orderId) {

        requireText(internalRequestId, "internalRequestId");
        requireText(orderId, "orderId");
        Objects.requireNonNull(verifiedUser, "verifiedUser");
        Objects.requireNonNull(effectiveOptions, "effectiveOptions");

        return ScopedValue
                .where(REQUEST_ID, internalRequestId)
                .where(USER, verifiedUser)
                .where(OPTIONS, effectiveOptions)
                .call(() -> summarizeOrder(orderId));
    }

    static String summarizeOrder(String orderId) {
        Identity actor = USER.orElseThrow(
                () -> new IllegalStateException(
                        "Thiếu danh tính trong ngữ cảnh yêu cầu"));

        if (!actor.permissions().contains("orders:read")) {
            throw new SecurityException("Không có quyền đọc đơn hàng");
        }

        Order order = findOwnedOrder(
                actor.tenantId(),
                actor.userId(),
                orderId);

        RequestOptions originalOptions = OPTIONS.get();

        log("Đọc đơn " + order.id()
                + "; config=" + originalOptions.configVersion());

        String standard = formatOrder(order);

        // Chỉ thay locale cho bản hiển thị phụ.
        String alternate = ScopedValue
                .where(OPTIONS, originalOptions.withLocale(Locale.US))
                .call(() -> {
                    log("Locale trong scope con: "
                            + OPTIONS.get().locale().toLanguageTag());
                    return formatOrder(order);
                });

        log("Locale sau scope con: "
                + OPTIONS.get().locale().toLanguageTag());

        return standard + System.lineSeparator() + alternate;
    }

    static Order findOwnedOrder(
            String tenantId,
            String userId,
            String orderId) {

        Order order = ORDERS.get(orderId);

        if (order == null
                || !order.tenantId().equals(tenantId)
                || !order.ownerId().equals(userId)) {
            throw new SecurityException(
                    "Đơn hàng không thuộc phạm vi được phép");
        }

        return order;
    }

    static String formatOrder(Order order) {
        Locale locale = OPTIONS.get().locale();

        return String.format(
                locale,
                "Đơn %s: %,.2f",
                order.id(),
                order.amount());
    }

    static void log(String message) {
        Identity actor = USER.get();

        System.out.printf(
                "[request=%s user=%s tenant=%s] %s%n",
                REQUEST_ID.get(),
                actor.userId(),
                actor.tenantId(),
                message);
    }

    private static void requireText(String value, String name) {
        Objects.requireNonNull(value, name);

        if (value.isBlank()) {
            throw new IllegalArgumentException(name + " không được rỗng");
        }
    }
}
```

Với JDK 25 hoặc mới hơn, có thể biên dịch và chạy bằng:

```shell
javac -encoding UTF-8 RequestScopeDemo.java
java RequestScopeDemo
```

Những hành vi cần quan sát khi chạy:

| Thời điểm | Hành vi dự kiến |
| --- | --- |
| Trước `handleVerifiedRequest` | `REQUEST_ID.isBound()` là `false` |
| Trong các lời gọi nghiệp vụ và log | Cùng đọc được `req-1001`, `u-01` và `shop-a` |
| Khi định dạng thông thường | Dùng locale `vi-VN` |
| Khi định dạng bản phụ | Dùng locale `en-US`; request ID và danh tính không đổi |
| Sau scope con | Locale trở lại `vi-VN` |
| Sau khi xử lý xong | `REQUEST_ID.isBound()` lại là `false` |

Số tiền được định dạng theo hai locale khác nhau, nhưng giá trị `BigDecimal` của đơn hàng không bị thay đổi. Scope con chỉ quyết định cách biểu diễn.

Trong ví dụ, phương thức dữ liệu vẫn nhận `tenantId` và `userId` tường minh. Khi chuyển sang cơ sở dữ liệu, cần đưa các điều kiện giới hạn dữ liệu tương ứng vào truy vấn hoặc cơ chế kiểm soát dữ liệu đang dùng.

## 5. Ứng dụng request ID: nối các sự kiện của cùng một yêu cầu

Một lần đọc đơn hàng có thể phát sinh nhiều log: bắt đầu xử lý, kiểm tra quyền, đọc dữ liệu và trả kết quả. Gắn cùng request ID giúp tìm lại chuỗi sự kiện khi điều tra lỗi.

Nên tạo một mã nội bộ ở ranh giới tiếp nhận. Nếu hệ thống cho phép nhận correlation ID từ bên ngoài, hãy kiểm tra định dạng và giới hạn độ dài trước khi sử dụng; cũng có thể lưu mã bên ngoài ở trường riêng. Request ID không chứng minh danh tính người gửi.

Trong ví dụ, `log` lấy request ID từ ngữ cảnh ngay tại thời điểm ghi. Vì vậy, `formatOrder` hoặc lớp trung gian không phải nhận thêm request ID chỉ để chuyển tiếp cho logger.

Khi tích hợp vào hệ thống thực tế, cần xác định rõ ba ranh giới:

- **Log trong tiến trình:** logger hoặc lớp bọc logger phải chủ động đọc ngữ cảnh và ghi trường request ID.
- **Lời gọi ra ngoài:** HTTP client hoặc bộ phát thông điệp phải chủ động đưa mã tương quan vào metadata theo quy ước của hệ thống.
- **Xử lý tại dịch vụ nhận:** dịch vụ đó kiểm tra metadata rồi tạo ngữ cảnh cục bộ của chính nó.

`ScopedValue` không tự thêm trường vào MDC, header HTTP hay hệ thống tracing. Nếu ứng dụng đã dùng MDC hoặc tracing context, hãy xây dựng phần tích hợp tại đúng ranh giới và kiểm tra cách thư viện đó truyền ngữ cảnh khi đổi thread.

Cũng nên phân biệt request ID của ứng dụng với trace ID/span ID của hệ thống quan sát. Một mã có thể được dùng để tra cứu mã còn lại, nhưng việc đặt request ID vào scoped value không tự tạo một trace phân tán.

## 6. Ứng dụng thông tin người dùng: cung cấp danh tính đã xác thực

Ngữ cảnh người dùng nên là ảnh chụp nhỏ của thông tin cần cho thao tác hiện tại. Với ví dụ đọc đơn hàng, ba trường có ý nghĩa trực tiếp:

- `userId`: người đang thao tác.
- `tenantId`: phạm vi tổ chức mà yêu cầu được phép sử dụng.
- `permissions`: các quyền mà lớp xác thực/phân quyền đã xác định.

Không lấy `userId`, `tenantId` hay quyền quản trị từ một header tùy ý rồi coi đó là danh tính đáng tin cậy. Lớp tiếp nhận phải xác định các giá trị này từ cơ chế xác thực và chính sách của ứng dụng trước khi thiết lập binding.

### 6.1. Có danh tính vẫn phải kiểm tra quyền

Trong ví dụ có hai bước riêng:

1. Kiểm tra quyền `orders:read`.
2. Giới hạn đơn hàng theo tenant và người sở hữu.

Một người có quyền đọc đơn hàng chưa chắc được đọc mọi đơn hàng của mọi tenant. Scoped Values giúp đưa thông tin đến nơi cần kiểm tra; quyết định cho phép truy cập vẫn thuộc chính sách nghiệp vụ.

Quyền trong ví dụ được chụp tại lúc nhận yêu cầu. Với thao tác yêu cầu thông tin quyền mới nhất, như thay đổi đặc quyền hoặc xử lý giao dịch nhạy cảm, ứng dụng cần thực hiện kiểm tra bổ sung tại thời điểm phù hợp với chính sách của mình.

### 6.2. Thiếu danh tính phải được xử lý tường minh

`USER.orElseThrow(...)` làm rõ điều kiện gọi phương thức: thao tác này cần có danh tính. Không tạo người dùng mặc định mang quyền cao khi ngữ cảnh bị thiếu.

Đối với endpoint cho phép khách chưa đăng nhập, có thể thiết kế một kiểu danh tính thể hiện rõ trạng thái khách và chỉ cấp các khả năng dành cho khách. Quyết định đó phải là một phần của mô hình phân quyền, thay vì được suy ra từ việc quên tạo binding.

### 6.3. Giữ khóa trong phạm vi truy cập hẹp

Ví dụ khai báo các khóa là `private static final`. Mã cần sử dụng thông tin đi qua các phương thức do lớp sở hữu ngữ cảnh cung cấp.

Nếu công khai khóa ra mọi nơi, mã giữ khóa có thể tạo binding mới trong scope con. Vì thế, tính chất binding không bị sửa tại chỗ không có nghĩa là mã không thể thay thế danh tính trong một phạm vi lồng nhau.

Tài liệu Java mô tả đối tượng `ScopedValue` như một khóa để truy cập giá trị; việc kiểm soát nơi giữ khóa là một phần của thiết kế. Xem [Scoped Values as capabilities](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html#scoped-values-as-capabilities).

Với ứng dụng nhiều lớp, có thể tách thành lớp quản lý ngữ cảnh và chỉ công bố các hàm đọc phù hợp. Điểm vào có quyền tạo binding nên nằm ở lớp tích hợp đã được xác định rõ.

## 7. Ứng dụng cấu hình theo yêu cầu: dùng một ảnh chụp nhất quán

Giả sử locale có thể được xác định từ cấu hình hệ thống, thiết lập của tenant và tùy chọn người dùng được phép thay đổi. Một chính sách minh họa là:

```text
Cấu hình mặc định
    -> Áp dụng thiết lập tenant hợp lệ
    -> Áp dụng tùy chọn người dùng nằm trong danh sách được phép
    -> Kiểm tra giá trị cuối cùng
    -> Tạo RequestOptions
    -> Thiết lập binding cho yêu cầu
```

Thứ tự ưu tiên phải do ứng dụng quy định. Không nên để mọi tham số mà client gửi đều có quyền ghi đè cấu hình máy chủ.

Việc tạo `RequestOptions` một lần giúp các bước của cùng yêu cầu sử dụng cùng lựa chọn cấu hình. Nếu kho cấu hình được cập nhật giữa chừng, yêu cầu hiện tại vẫn có thể tiếp tục với ảnh chụp đã chọn; yêu cầu tiếp theo có thể dùng phiên bản mới. Đây là lựa chọn thiết kế về tính nhất quán, không phải cơ chế tự cập nhật do Scoped Values cung cấp.

Trường `configVersion` trong ví dụ giúp giải thích một kết quả đã được tạo với cấu hình nào. Trong hệ thống thực tế, phiên bản nên do thành phần quản lý cấu hình cấp hoặc xác định.

### 7.1. Ghi đè trong phạm vi con

Ví dụ tạo bản hiển thị phụ bằng `originalOptions.withLocale(Locale.US)`, rồi bind riêng đối tượng mới cho `OPTIONS`. Khi scope con kết thúc, binding cấu hình bên ngoài tiếp tục có hiệu lực. Request ID và danh tính không cần bind lại trong chuỗi lời gọi đồng bộ đó.

Đây là rebinding: scope con có một giá trị cấu hình khác. Đối tượng cấu hình ban đầu vẫn giữ nguyên. Cơ chế khôi phục cũng áp dụng nếu phần định dạng bên trong ném ngoại lệ. Xem [API Carrier của Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.Carrier.html#call(java.lang.ScopedValue.CallableOp)).

Chỉ nên áp dụng kiểu ghi đè này cho lựa chọn mà thao tác con được phép thay đổi, chẳng hạn locale của một bản xuất. Việc thay tenant, nâng quyền hoặc bỏ điều kiện kiểm soát truy cập phải tuân theo chính sách phân quyền tương ứng.

### 7.2. Bất biến phải bao gồm dữ liệu được giữ bên trong

Một record có trường `Set` hoặc `Map` chưa tự làm cho tập hợp đó trở nên bất biến. Trong ví dụ, constructor của `Identity` sử dụng `Set.copyOf` để tránh giữ tập quyền có thể bị người gọi thay đổi.

Nếu cấu hình chứa collection, cũng cần tạo bản sao phù hợp và bảo đảm các phần tử bên trong không chứa trạng thái thay đổi ngoài ý muốn. `Map.copyOf` không biến mọi đối tượng được map tham chiếu thành đối tượng bất biến sâu.

Đừng đặt một đối tượng cấu hình toàn cục có thể sửa vào scoped value rồi kỳ vọng các yêu cầu sẽ có ảnh chụp riêng. Nhiều binding vẫn có thể cùng tham chiếu một đối tượng.

## 8. Khi luồng xử lý đổi thread

Binding được sử dụng theo thread đang thực thi. Một lambda được tạo trong scope không tự mang binding sang nơi lambda đó chạy sau này.

| Cách thực thi công việc | Có thể trông chờ tự thấy binding hiện tại không? |
| --- | --- |
| Gọi phương thức đồng bộ trong cùng scope | Có |
| `new Thread(...)` hoặc bắt đầu một virtual thread thông thường | Không |
| Gửi task vào `ExecutorService` thông thường | Không |
| `CompletableFuture.supplyAsync(...)` | Không |
| Callback được lưu lại rồi chạy sau khi scope kết thúc | Không |
| Task được `fork` trong `StructuredTaskScope` đúng cấu trúc | Có cơ chế kế thừa do API quy định |

Dùng virtual thread không tự giải quyết việc truyền ngữ cảnh. Các nguyên tắc về scope và ranh giới thực thi vẫn cần được áp dụng.

Với Structured Concurrency, binding được chụp khi mở task scope và được các thread do scope đó tạo kế thừa. Task scope phải được quản lý trong vòng đời bao quanh thích hợp. Tài liệu Java 27 vẫn đánh dấu `StructuredTaskScope` là preview, dù `ScopedValue` đã là API chính thức. Xem [mục kế thừa của ScopedValue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ScopedValue.html#inheritance) và [API StructuredTaskScope Java 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html).

### 8.1. Tạo binding tường minh cho một task trong executor

Khi cần tích hợp với executor thông thường, có thể chụp các giá trị cần dùng trước lúc gửi task và tạo scope mới bên trong task.

Đoạn mở rộng sau có thể đặt trong lớp `RequestScopeDemo`; nó dùng tên đầy đủ của `Callable` để không cần thêm import:

```java
static java.util.concurrent.Callable<String> captureSummaryTask(
        String orderId) {

    // Phải gọi phương thức này khi ngữ cảnh yêu cầu còn hiệu lực.
    String capturedRequestId = REQUEST_ID.get();
    Identity capturedUser = USER.get();
    RequestOptions capturedOptions = OPTIONS.get();

    return () -> ScopedValue
            .where(REQUEST_ID, capturedRequestId)
            .where(USER, capturedUser)
            .where(OPTIONS, capturedOptions)
            .call(() -> summarizeOrder(orderId));
}
```

Người gọi tạo task trong scope hiện tại rồi gửi nó vào executor. Khi executor thực thi task, task thiết lập các binding của chính nó. Đây là truyền dữ liệu tường minh kết hợp với một scope mới.

Cách này không tự áp đặt thời hạn, hủy tác vụ hay buộc task kết thúc cùng request ban đầu. Thành phần điều phối vẫn phải quản lý kết quả, lỗi và vòng đời tác vụ. Nếu yêu cầu bị hủy, việc task con phải dừng thế nào cần được thiết kế riêng.

### 8.2. Công việc nền cần ngữ cảnh riêng

Task được trả về ở trên giữ tham chiếu đến các giá trị đã chụp. Các giá trị đó có thể còn tồn tại sau khi binding nguồn kết thúc. Thoát scope không thu hồi những tham chiếu đã được lưu ở nơi khác.

Vì vậy, với công việc nền dài hạn, thường nên tạo một dữ liệu công việc riêng: mã công việc, mã tương quan, đối tượng nghiệp vụ cần xử lý và thông tin người khởi tạo ở mức cần thiết. Tác vụ nền xác định lại quyền và cấu hình theo chính sách của loại công việc đó.

Không nên giữ cả đối tượng HTTP request, session, token xác thực hoặc toàn bộ ngữ cảnh người dùng chỉ vì task ban đầu được tạo trong một request.

## 9. Thiết kế giá trị bắt buộc và giá trị tùy chọn

Chính sách đọc ngữ cảnh nên được quyết định theo loại dữ liệu:

| Dữ liệu | Khi thiếu binding | Cách xử lý đề xuất |
| --- | --- | --- |
| Danh tính cho thao tác yêu cầu đăng nhập | Vi phạm điều kiện thực thi | Dừng bằng lỗi rõ ràng |
| Tenant của thao tác có phân vùng dữ liệu | Không xác định được phạm vi truy cập | Dừng trước khi đọc dữ liệu |
| Request ID trong bộ xử lý HTTP | Thường là thiếu bước khởi tạo | Sửa ranh giới tiếp nhận hoặc tạo mã trước khi vào nghiệp vụ |
| Locale trong tiện ích được phép chạy độc lập | Có thể là trường hợp hợp lệ | Dùng một giá trị mặc định đã thống nhất |
| Cấu hình bắt buộc cho quyết định nghiệp vụ | Không có đủ đầu vào | Báo thiếu cấu hình thay vì đoán |

`get()` ném `NoSuchElementException` khi chưa có binding; `orElse` và `orElseThrow` cho phép biểu đạt chính sách thay thế hoặc báo lỗi. Xem [các phương thức của ScopedValue Java 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html#method-summary).

Ví dụ, một tiện ích định dạng được thiết kế để hoạt động cả ngoài request có thể chọn locale như sau:

```java
static Locale optionalLocale() {
    return OPTIONS.isBound()
            ? OPTIONS.get().locale()
            : Locale.ROOT;
}
```

Ngược lại, `summarizeOrder` trong ví dụ chính yêu cầu ngữ cảnh đầy đủ. Không nên thêm fallback vào đó chỉ để che việc lời gọi đã đi ra ngoài scope.

API cho phép bind giá trị `null`; có binding và có đối tượng hợp lệ là hai điều khác nhau. Ví dụ chính chủ động từ chối các giá trị ngữ cảnh `null` ở ranh giới tạo scope, nhờ đó các phương thức phía dưới có điều kiện thực thi rõ ràng.

## 10. Khi nào dùng một khóa, khi nào dùng nhiều khóa?

Ba khóa trong ví dụ thể hiện ba vai trò và cho phép ghi đè cấu hình riêng. Với ứng dụng có nhiều trường luôn đi cùng nhau, có thể gom thành một record `RequestContext` rồi bind một khóa.

| Phương án | Phù hợp khi | Điều cần cân nhắc |
| --- | --- | --- |
| Một `ScopedValue<RequestContext>` | Các trường có cùng vòng đời và thường được sử dụng cùng nhau | Lớp chỉ cần request ID có thể bị cung cấp nhiều thông tin hơn cần thiết |
| Một số khóa theo vai trò | Có nhu cầu truy cập hoặc rebinding độc lập | Tránh tạo quá nhiều khóa nhỏ |
| Tham số phương thức tường minh | Đầu vào quyết định trực tiếp ý nghĩa nghiệp vụ | Có thể phải truyền qua các lớp điều phối |

Tài liệu Java khuyến khích giữ số lượng scoped value ở mức nhỏ và cân nhắc gom các giá trị liên quan vào record. Đây là định hướng thiết kế, không phải cam kết rằng một phương án luôn nhanh hơn trong mọi ứng dụng. Xem [ghi chú triển khai ScopedValue Java 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ScopedValue.html).

Đối với bài này, lợi ích cần đánh giá trước tiên là sự rõ ràng của vòng đời ngữ cảnh và nơi chịu trách nhiệm thiết lập dữ liệu. Nếu cần so sánh hiệu năng, hãy đo trong tải công việc thực tế của ứng dụng.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chỉ tạo carrier rồi gọi nghiệp vụ ở bên ngoài `run/call` | Nghiệp vụ không có binding mong đợi | Đưa toàn bộ phần cần ngữ cảnh vào thao tác được thực thi bởi carrier |
| Dùng một biến `static` thường để giữ người dùng hiện tại | Các yêu cầu có thể đọc nhầm dữ liệu của nhau | Dùng binding có vòng đời theo yêu cầu |
| Bind tập quyền có thể sửa | Quyết định quyền thay đổi ngoài ý muốn | Chụp dữ liệu bất biến trước khi tạo scope |
| Dựa vào tenant ID do client tự khai | Có thể truy cập sai phạm vi dữ liệu | Xác minh quyền tham gia tenant trước khi bind |
| Công khai khóa danh tính cho mã không cần tạo scope | Khó kiểm soát nơi rebinding xảy ra | Giới hạn truy cập khóa và cung cấp hàm đọc phù hợp |
| Cho rằng executor tự kế thừa ngữ cảnh | Task thiếu binding hoặc xử lý sai điều kiện đầu vào | Truyền dữ liệu cần thiết và tạo scope trong task |
| Trả callback hoặc luồng dữ liệu lười rồi xử lý sau | Công việc thực sự chạy khi binding đã kết thúc | Thực thi phần cần ngữ cảnh trong scope hoặc truyền dữ liệu ra rõ ràng |
| Cho rằng hết scope là mọi dữ liệu đã bị xóa | Task hoặc cache vẫn giữ đối tượng đã chụp | Quản lý riêng những tham chiếu có vòng đời dài hơn |
| Thay mọi tham số bằng ngữ cảnh ẩn | Khó hiểu và khó tái sử dụng phương thức | Giữ đầu vào nghiệp vụ tường minh; giới hạn dữ liệu ngữ cảnh |

Trong một bộ xử lý HTTP có streaming hoặc callback bất đồng bộ, thời điểm phương thức handler trả về có thể khác thời điểm công việc hoàn tất. Khi tích hợp, cần xác định chính xác đoạn nào được thực thi trong scope và đoạn nào sẽ chạy sau đó.

## 12. Quan sát thêm từ ví dụ

Có thể thay đổi đầu vào của chương trình để tự quan sát các điều kiện thực thi:

- Giữ `u-01/shop-a` nhưng yêu cầu `O-202`: thao tác bị từ chối vì đơn hàng nằm ngoài phạm vi dữ liệu.
- Tạo danh tính không có `orders:read`: thao tác dừng trước khi đọc đơn hàng.
- Gọi `summarizeOrder` trực tiếp ngoài `handleVerifiedRequest`: phương thức báo thiếu danh tính.
- Đặt một lời gọi yêu cầu hợp lệ sau lời gọi trước: yêu cầu mới phải tạo các binding của riêng mình.
- Cho phần xử lý bên trong scope ném ngoại lệ rồi bắt ngoại lệ ở bên ngoài: các binding của scope đã thoát không tiếp tục là ngữ cảnh hiện tại.

Khi đưa mẫu này vào ứng dụng, hãy đặt việc tạo binding tại ranh giới có đủ thông tin đã xác minh. Các lớp nghiệp vụ đọc ngữ cảnh cần thiết, kiểm tra chính sách tương ứng và truyền rõ phạm vi dữ liệu tới lớp truy cập dữ liệu.