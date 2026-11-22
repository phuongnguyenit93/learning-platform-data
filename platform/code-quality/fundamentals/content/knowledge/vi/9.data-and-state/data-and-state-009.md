# Tách trạng thái theo từng yêu cầu hoặc tác vụ

Khi nhiều yêu cầu được xử lý cùng lúc, một đối tượng dùng chung có thể vô tình giữ dữ liệu của yêu cầu trước đó: mã đơn hàng của người A xuất hiện trong kết quả của người B, bộ đếm tác vụ bị cộng sai hoặc một lần thử lại dùng nhầm trạng thái cũ. Những lỗi này thường khó tái hiện vì kết quả phụ thuộc vào thứ tự các luồng chạy.

Bài học thuộc chương **Dữ liệu và trạng thái** của **CODE_QUALITY_FUNDAMENTALS**, với mục tiêu hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Nội dung tập trung vào việc xác định **ai sở hữu trạng thái, trạng thái sống bao lâu, ai được phép thay đổi nó** và cách bảo đảm yêu cầu hoặc tác vụ độc lập không ảnh hưởng ngoài ý muốn đến nhau.

## 1. Trạng thái là gì và tại sao phạm vi sở hữu quan trọng?

**Trạng thái (state)** là dữ liệu có thể ảnh hưởng đến hành vi hoặc kết quả xử lý tại một thời điểm. Nó có thể là một biến tích lũy, danh sách bản ghi đang xử lý, mã tương quan, trạng thái workflow, bản ghi trong cơ sở dữ liệu hoặc dữ liệu cache.

Không phải mọi trạng thái đều nguy hiểm. Vấn đề xuất hiện khi **nhiều luồng xử lý cùng có quyền đọc/ghi một giá trị** nhưng không có ranh giới hoặc quy tắc đồng bộ phù hợp.

Ví dụ trong dịch vụ tính phí:

- **Chính sách thuế** có thể là cấu hình bất biến dùng chung cho nhiều yêu cầu.
- **Giỏ hàng và mã yêu cầu** chỉ thuộc về một lần tính phí.
- **Danh mục sản phẩm** có thể là dữ liệu dùng chung nhưng phải có hợp đồng cập nhật và tính nhất quán.
- **Số dư tài khoản** là trạng thái nghiệp vụ được lưu bền vững và cần giao dịch/kiểm soát đồng thời; không được coi chỉ là biến riêng trong bộ nhớ của một request.

Câu hỏi cốt lõi là: **Dữ liệu này thuộc về một lời gọi, một tác vụ, một phiên làm việc, một tiến trình hay toàn hệ thống?**

### 1.1. Bảng phạm vi trạng thái thường gặp

| Phạm vi | Ví dụ | Thời gian tồn tại | Quy tắc thiết kế |
| --- | --- | --- | --- |
| Cục bộ trong phương thức | Tổng tiền đang tính, biến kiểm tra | Trong một lần gọi | Ưu tiên biến cục bộ, không rò tham chiếu mutable |
| Một yêu cầu (request) | Mã tương quan, người gọi, kết quả kiểm tra đầu vào | Từ khi yêu cầu bắt đầu đến khi kết thúc | Không dùng field mutable của singleton để lưu |
| Một tác vụ (task/job) | Bộ đếm xử lý, checkpoint tạm, tập lỗi của một batch | Trong một lần thực thi tác vụ | Tạo trạng thái mới cho mỗi lần chạy; định nghĩa vòng đời retry |
| Phiên làm việc | Ngữ cảnh của phiên đăng nhập hoặc phiên người dùng | Qua nhiều yêu cầu | Có cơ chế hết hạn, đồng bộ và phân quyền |
| Toàn tiến trình | Cấu hình, pool kết nối, cache, metric | Sống cùng ứng dụng | Chia sẻ có chủ đích, có cơ chế thread-safety và giới hạn |
| Nghiệp vụ dùng chung bền vững | Tồn kho, số dư, trạng thái đơn hàng | Qua nhiều tiến trình và lần triển khai | Quản lý bằng kho dữ liệu/giao dịch, tính nhất quán và quyền |

Đặc biệt, **request-scoped** không đồng nghĩa **thread-scoped**: một thread trong pool có thể lần lượt xử lý nhiều request, còn một request có thể mở thêm nhiều task chạy trên các thread khác.

### 1.2. Trạng thái thuộc về ai?

Một cách thực dụng để xác định phạm vi là hỏi:

1. Ai tạo dữ liệu và ai có trách nhiệm kết thúc vòng đời của nó?
2. Có bao nhiêu yêu cầu/tác vụ được phép đọc và sửa dữ liệu này?
3. Nếu hai yêu cầu chạy xen kẽ, kết quả của yêu cầu A có phụ thuộc vào dữ liệu riêng của B không?
4. Khi retry hoặc chạy lại, có phải tạo trạng thái mới hay khôi phục từ checkpoint đã xác thực?
5. Dữ liệu cần tồn tại khi tiến trình dừng hay chỉ trong một lần xử lý?

Nếu dữ liệu chỉ có ý nghĩa với một lời gọi, nơi đặt đầu tiên nên là **tham số và biến cục bộ**. Nếu nhiều thành phần của cùng yêu cầu cần dùng, có thể truyền một **ngữ cảnh rõ ràng** hoặc tạo đối tượng ngắn hạn do yêu cầu đó sở hữu.

## 2. Phản ví dụ: lưu thông tin yêu cầu trong field dùng chung

Giả sử ứng dụng Java nhận nhiều yêu cầu xử lý đơn cùng lúc. Để đơn giản, ví dụ chỉ nhân số đơn vị công việc và trả kết quả. Một đối tượng xử lý được dùng lại cho nhiều request:

~~~java
record WorkItem(String requestId, int units) {}
record WorkResult(String requestId, int processedUnits) {}

final class UnsafeWorker {
    private String currentRequestId;

    WorkResult execute(WorkItem item) {
        currentRequestId = item.requestId();
        int result = Math.multiplyExact(item.units(), 2);

        return new WorkResult(currentRequestId, result);
    }
}
~~~

Nếu hai thread cùng dùng một `UnsafeWorker`, có thể xảy ra:

| Thời điểm | Thread A (request A) | Thread B (request B) |
| --- | --- | --- |
| T1 | Gán `currentRequestId = "A"` | |
| T2 | | Gán `currentRequestId = "B"` |
| T3 | Tính `result` cho A | |
| T4 | Đọc `currentRequestId` đang là `"B"` | |
| T5 | Trả `WorkResult("B", result-của-A)` | |

Lịch chạy này chỉ là một khả năng. Vì field bị truy cập đồng thời mà không có bảo vệ, mã còn có **data race** theo mô hình bộ nhớ Java; kết quả phụ thuộc vào đồng bộ và thời điểm quan sát. Đừng dựa vào việc “chạy thử nhiều lần chưa thấy lỗi” để kết luận an toàn.

Trường hợp này đặc biệt nguy hiểm khi field chứa **customerId**, quyền truy cập, token, dữ liệu cá nhân hoặc giá trị phục vụ quyết định nghiệp vụ. Một sai lệch nhỏ trong luồng điều phối có thể trở thành lỗi tính đúng đắn hoặc lỗi phân tách dữ liệu người dùng.

### 2.1. Vì sao `volatile` và `AtomicReference` không giải quyết đúng vấn đề?

Có thể thay field bằng `volatile String currentRequestId` hoặc `AtomicReference<String>`. Những công cụ này giúp về **khả năng nhìn thấy giá trị** hoặc thao tác cập nhật riêng lẻ, nhưng **không biến mỗi request thành chủ sở hữu độc lập**.

Thread A vẫn có thể đọc mã của B vì cả hai đang cố dùng **cùng một ô nhớ** cho hai giá trị riêng. Tương tự, khóa `synchronized` quanh toàn bộ `execute` có thể tránh xen kẽ trong phạm vi một instance, nhưng tuần tự hóa các request và làm giảm tính đồng thời mà không có lợi ích nghiệp vụ.

**Sửa nguyên nhân gốc:** đặt `requestId` trong dữ liệu hoặc biến riêng của từng lần gọi.

~~~java
import java.util.Objects;

final class StatelessWorker {
    WorkResult execute(WorkItem item) {
        Objects.requireNonNull(item, "item");
        if (item.requestId() == null || item.requestId().isBlank()) {
            throw new IllegalArgumentException(
                    "requestId must not be blank");
        }
        if (item.units() < 0) {
            throw new IllegalArgumentException("units must be nonnegative");
        }

        int result = Math.multiplyExact(item.units(), 2);
        return new WorkResult(item.requestId(), result);
    }
}
~~~

`StatelessWorker` không có field mutable cho request nên nhiều thread có thể gọi cùng một instance mà không làm lẫn mã yêu cầu. Nó vẫn cần các quy tắc nghiệp vụ hợp lệ và kiểm thử; **stateless** không tự đồng nghĩa với **không bao giờ lỗi**.

## 3. Thiết kế trạng thái theo request trong một ví dụ thực tế

Xét một dịch vụ tính tổng tiền giỏ hàng. Đầu vào gồm mã yêu cầu và nhiều dòng hàng; mỗi dòng có đơn giá tính bằng VND cùng số lượng. Giá trị tiền được biểu diễn bằng `long` cho ví dụ, số lượng là số nguyên dương.

Mục tiêu thiết kế:

- Mỗi lần gọi có dữ liệu đầu vào riêng, đã kiểm tra.
- Tính toán chỉ dùng trạng thái của lần gọi đó.
- Đối tượng dịch vụ có thể dùng lại đồng thời.
- Kết quả trả về không mang tham chiếu đến danh sách mutable của bên gọi.
- Tràn số được phát hiện thay vì im lặng tạo tổng tiền sai.

### 3.1. Dữ liệu đầu vào có hợp đồng rõ ràng

Ví dụ dùng `record` của Java 17:

~~~java
import java.util.List;
import java.util.Objects;

record CartLine(String sku, long unitPriceVnd, int quantity) {
    CartLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}

record QuoteRequest(String requestId, List<CartLine> lines) {
    QuoteRequest {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException(
                    "requestId must not be blank");
        }
        Objects.requireNonNull(lines, "lines");
        // Bảo vệ danh sách khỏi việc bên gọi sửa sau khi gửi yêu cầu.
        lines = List.copyOf(lines);
    }
}

record QuoteResult(String requestId, long totalVnd) {}
~~~

`List.copyOf` tạo một danh sách không thể thay đổi qua giao diện trả về và bảo vệ khỏi sửa đổi cấu trúc danh sách nguồn sau khi tạo `QuoteRequest`. Đây là **bản sao nông (shallow copy)**; nó đủ cho ví dụ vì các phần tử `CartLine` là record chứa trường bất biến. Nếu phần tử là đối tượng mutable hoặc chứa tham chiếu mutable, cần thiết kế sở hữu dữ liệu sâu hơn.

Lưu ý: ví dụ chấp nhận danh sách rỗng với tổng bằng 0. Trong nghiệp vụ thật, điều này phải được xác nhận theo hợp đồng: hệ thống có thể yêu cầu tối thiểu một dòng hàng.

### 3.2. Trạng thái tính toán nằm trong lần gọi

~~~java
final class QuoteService {
    QuoteResult calculate(QuoteRequest request) {
        if (request == null) {
            throw new IllegalArgumentException("request is required");
        }

        long totalVnd = 0L;
        for (CartLine line : request.lines()) {
            long lineTotal = Math.multiplyExact(
                    line.unitPriceVnd(), (long) line.quantity());
            totalVnd = Math.addExact(totalVnd, lineTotal);
        }

        return new QuoteResult(request.requestId(), totalVnd);
    }
}
~~~

`QuoteService` không lưu `currentRequest`, `totalVnd` hay danh sách hàng vào field. Biến `totalVnd` tồn tại riêng trong mỗi lần gọi, và các đối tượng `QuoteRequest` được sử dụng như ảnh chụp đầu vào.

Bộ tính toán trên không truy cập cơ sở dữ liệu hoặc trạng thái chia sẻ. Vì vậy, **nếu các đối tượng đầu vào bảo đảm bất biến như đã mô tả**, các lần gọi đồng thời không có dữ liệu mutable của request để tranh chấp. Việc gọi `Math.addExact` và `Math.multiplyExact` còn giúp báo lỗi khi tổng tiền vượt phạm vi `long`, thay vì tạo kết quả sai do overflow.

Một mẫu dùng không cần tạo instance dịch vụ riêng cho từng request:

~~~java
QuoteService service = new QuoteService();

QuoteRequest first = new QuoteRequest(
        "REQ-A",
        List.of(new CartLine("P-01", 120_000L, 2)));

QuoteRequest second = new QuoteRequest(
        "REQ-B",
        List.of(new CartLine("P-02", 75_000L, 3)));

QuoteResult a = service.calculate(first);  // REQ-A, 240000
QuoteResult b = service.calculate(second); // REQ-B, 225000
~~~

Không cần biến `service` thành đối tượng request-scoped nếu bản thân nó **stateless** và những phụ thuộc mà nó sử dụng cũng an toàn cho truy cập đồng thời. Tạo một instance mới mỗi lần gọi chỉ có ích khi bản thân đối tượng chứa trạng thái riêng thực sự cần vòng đời đó.

### 3.3. Phân biệt “đối tượng không có field” với “hành vi an toàn khi chia sẻ”

Một lớp không có field mutable riêng vẫn có thể không an toàn nếu gọi đến phụ thuộc có trạng thái chia sẻ không được bảo vệ:

~~~java
final class QuoteCounter {
    private long count;

    void recorded() {
        count++; // Không phải thao tác nguyên tử khi nhiều thread cùng gọi.
    }

    long getCount() {
        return count;
    }
}

final class QuotingFacade {
    private final QuoteService service = new QuoteService();
    private final QuoteCounter counter = new QuoteCounter();

    QuoteResult handle(QuoteRequest request) {
        QuoteResult result = service.calculate(request);
        counter.recorded();
        return result;
    }
}
~~~

`QuotingFacade` không lưu trạng thái riêng của request, nhưng `QuoteCounter` có một biến đếm **dùng chung** mà nhiều thread cập nhật. `count++` gồm các bước đọc, tăng, ghi nên có thể mất cập nhật khi chạy đồng thời.

Nếu bộ đếm chỉ là metric, có thể dùng công cụ đo/collector phù hợp hoặc `LongAdder` trong trường hợp nhiều cập nhật đồng thời. Nếu đó là một **giá trị nghiệp vụ phải đúng tuyệt đối** và được dùng để quyết định giao dịch, cách quản lý còn phải xét tính nguyên tử, bền vững, nhiều tiến trình và cơ sở dữ liệu. Không nên dùng một bộ đếm trong bộ nhớ thay thế trạng thái nghiệp vụ của toàn hệ thống.

## 4. Request-scoped state, task-scoped state và dữ liệu dùng chung

### 4.1. Trạng thái của yêu cầu

Một request HTTP thường có dữ liệu như mã tương quan, chủ thể đã xác thực, locale, thông tin phân trang hoặc các kết quả xác thực trong luồng. Chúng nên đi kèm request từ tầng nhận đến các thành phần cần dùng.

**Không được tin dữ liệu từ client chỉ vì nó được đặt trong `RequestContext`.** Ví dụ, `userId` trong ngữ cảnh bảo mật phải được xác nhận từ cơ chế xác thực đáng tin cậy; không lấy trực tiếp từ tham số do client tự khai rồi coi là danh tính đã kiểm chứng.

Các thành phần nghiệp vụ không nên lén đọc “người dùng hiện tại” từ một biến static thay đổi theo từng yêu cầu. Làm vậy tạo phụ thuộc ngầm và gây khó kiểm thử.

### 4.2. Trạng thái của tác vụ

Một tác vụ nền có thể có `taskId`, số bản ghi đã xử lý, danh sách lỗi và trạng thái checkpoint. Nó có vòng đời **khác với request HTTP đã tạo tác vụ**:

- Request có thể trả về `202 Accepted` trong khi task vẫn chạy.
- Task có thể retry sau lỗi hoặc được xử lý trên worker khác.
- Một task có thể chia thành nhiều subtasks chạy song song.
- Tiến trình có thể dừng trước khi task hoàn tất.

Vì vậy, trạng thái **tạm trong bộ nhớ** chỉ nên dùng để xử lý một lần chạy; trạng thái cần sống qua khởi động lại hoặc phục vụ retry phải có kho lưu bền vững, nhận diện task và quy tắc cập nhật rõ ràng.

### 4.3. Cấu hình và tài nguyên dùng chung có chủ đích

Có thể chia sẻ:

- Cấu hình bất biến, bảng quy tắc không thay đổi trong quá trình xử lý.
- Client mạng hoặc pool kết nối được tài liệu của thư viện xác nhận an toàn khi dùng chung.
- Cache có chính sách key, cập nhật, giới hạn dung lượng và xử lý đồng thời phù hợp.
- Metric collector chuyên dụng cho cập nhật đồng thời.

Không phải “mọi thứ đều phải tách riêng”. Tạo một kết nối hoặc một thread pool mới cho từng request có thể làm giảm hiệu năng và gây cạn tài nguyên. Thiết kế tốt **chia sẻ tài nguyên an toàn**, đồng thời **tách dữ liệu riêng của từng thao tác**.

## 5. Ngữ cảnh yêu cầu: truyền rõ ràng để dễ hiểu và dễ kiểm thử

Khi nhiều lớp cần mã tương quan hoặc thông tin ngôn ngữ, có thể dùng một đối tượng ngữ cảnh bất biến:

~~~java
record RequestContext(String correlationId, String locale) {
    RequestContext {
        if (correlationId == null || correlationId.isBlank()) {
            throw new IllegalArgumentException(
                    "correlationId must not be blank");
        }
        if (locale == null || locale.isBlank()) {
            throw new IllegalArgumentException(
                    "locale must not be blank");
        }
    }
}
~~~

Một hàm nhận rõ ngữ cảnh:

~~~java
final class ReceiptFormatter {
    String format(QuoteResult quote, RequestContext context) {
        if (quote == null || context == null) {
            throw new IllegalArgumentException("inputs are required");
        }
        return context.locale().equals("vi")
                ? "Tổng tiền: " + quote.totalVnd() + " VND"
                : "Total: " + quote.totalVnd() + " VND";
    }
}
~~~

Cách truyền tham số có các lợi ích:

- Quan hệ phụ thuộc hiện rõ trong chữ ký phương thức.
- Unit test có thể đưa ngữ cảnh bất kỳ mà không dựng cả web framework.
- Khi đổi cấu trúc ngữ cảnh, các nơi sử dụng có thể được tìm và cập nhật chủ động.
- Khi xử lý bất đồng bộ, ngữ cảnh có thể được chuyển tiếp một cách tường minh.

Nhưng không nên tạo một `RequestContext` quá lớn chứa mọi thông tin rồi truyền vào tất cả phương thức. Chỉ truyền thông tin có ý nghĩa cho chức năng đó; tránh biến ngữ cảnh thành **“túi dữ liệu” thay thế thiết kế hợp đồng**. Với thông tin xác thực, dùng đúng đối tượng đã được xác minh và kiểm tra quyền ở ranh giới nghiệp vụ thích hợp.

## 6. Lưu ý lớn với `ThreadLocal` và thread pool

Java cung cấp `ThreadLocal<T>` để lưu giá trị riêng **theo thread**. Một số framework dùng nó cho ngữ cảnh request trong mô hình xử lý đồng bộ. Tuy nhiên, `ThreadLocal` không tự gắn vòng đời giá trị với request.

Ví dụ dễ gây lỗi:

~~~java
final class CurrentRequest {
    static final ThreadLocal<String> ID = new ThreadLocal<>();
}

// Request A chạy trên thread #1:
CurrentRequest.ID.set("A");
// ... xử lý, nhưng quên remove().

// Sau đó request B cũng được thread #1 xử lý:
String inheritedFromPreviousWork = CurrentRequest.ID.get();
// Có thể vẫn là "A".
~~~

Khi thread pool tái sử dụng thread, dữ liệu còn lưu có thể lọt sang yêu cầu sau; dữ liệu lớn hoặc tham chiếu mạnh trong `ThreadLocal` còn làm tăng nguy cơ giữ bộ nhớ lâu hơn dự kiến.

Nếu bắt buộc dùng `ThreadLocal` theo hợp đồng của framework, phải ràng buộc vòng đời bằng `try/finally`:

~~~java
final class RequestScope {
    private static final ThreadLocal<String> CURRENT_ID =
            new ThreadLocal<>();

    static void runWith(String requestId, Runnable action) {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("requestId is required");
        }
        if (action == null) {
            throw new IllegalArgumentException("action is required");
        }

        CURRENT_ID.set(requestId);
        try {
            action.run();
        } finally {
            CURRENT_ID.remove();
        }
    }

    static String currentId() {
        return CURRENT_ID.get();
    }
}
~~~

Mẫu này làm sạch giá trị khi `action` kết thúc, kể cả nếu có ngoại lệ. Nó **không truyền tự động sang thread khác** và chưa xử lý đầy đủ trường hợp cùng thread gọi lồng các scope khác nhau; nếu cần nesting, phải thiết kế bảo toàn/khôi phục ngữ cảnh trước đó một cách có kiểm soát.

Với ứng dụng dùng mô hình reactive, `CompletableFuture`, thread pool riêng hoặc virtual threads, không được mặc định `ThreadLocal` đang chứa đúng thông tin nghiệp vụ ở mọi điểm thực thi. Hãy ưu tiên API context propagation được framework hỗ trợ hoặc truyền dữ liệu cần thiết dưới dạng tham số bất biến.

**Phạm vi theo luồng là công cụ kỹ thuật, không phải bằng chứng quyền sở hữu theo yêu cầu.**

## 7. Xử lý bất đồng bộ: request kết thúc nhưng task vẫn chạy

Giả sử request HTTP khởi tạo việc báo giá ở executor khác. Nếu task tham chiếu một đối tượng mutable mà request tiếp tục thay đổi, nội dung task xử lý có thể không còn là nội dung lúc được gửi.

Phương án rõ ràng là tạo **ảnh chụp dữ liệu đầu vào** và **ngữ cảnh bất biến** trước khi gửi task:

~~~java
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

record TracedQuote(String correlationId, QuoteResult result) {}

final class AsyncQuoteFacade {
    private final QuoteService service;
    private final Executor executor;

    AsyncQuoteFacade(QuoteService service, Executor executor) {
        this.service = Objects.requireNonNull(service, "service");
        this.executor = Objects.requireNonNull(executor, "executor");
    }

    CompletableFuture<TracedQuote> submit(
            QuoteRequest request, RequestContext context) {

        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(context, "context");

        return CompletableFuture.supplyAsync(
                () -> new TracedQuote(
                        context.correlationId(),
                        service.calculate(request)),
                executor);
    }
}
~~~

Ở đây, `QuoteRequest` chứa danh sách đã sao chép cấu trúc, `CartLine` là record bất biến, và `RequestContext` cũng bất biến. `AsyncQuoteFacade` chỉ giữ các phụ thuộc dùng chung; mỗi task nắm dữ liệu riêng. Có thể sử dụng cùng `QuoteService` cho nhiều task vì logic tính toán không có trạng thái mutable dùng chung.

Tuy nhiên, tính an toàn của thiết kế còn phụ thuộc vào **contract của Executor**, cấu hình số lượng task, giới hạn hàng đợi và cách tiêu thụ kết quả. Không nên tạo vô hạn task chỉ vì mỗi task có dữ liệu tách biệt.

### 7.1. Điều gì xảy ra khi task thất bại hoặc bị hủy?

Khi `CompletableFuture` lỗi, cần có nơi nhận và xử lý kết quả thất bại. Khi phía yêu cầu đã ngắt kết nối, không nên mặc định công việc phía sau đã dừng: **hủy `CompletableFuture` không bảo đảm ngắt ngay tác vụ đang chạy**.

Một task dài nên có chính sách deadline, hủy có hợp tác, dọn tài nguyên và trạng thái hoàn tất rõ ràng. Nếu task có tác dụng phụ như ghi đơn hàng, cần kiểm soát retry và idempotency; dữ liệu task tách riêng không tự giải quyết vấn đề ghi trùng.

### 7.2. Task con có được dùng chung ngữ cảnh của task cha?

Có thể chuyển tiếp **dữ liệu bất biến** như `correlationId` và ngưỡng cấu hình đến task con. Với một bộ tích lũy mutable, hai task con cùng sửa một danh sách hoặc bộ đếm sẽ cần cơ chế đồng bộ rõ ràng, hoặc tốt hơn là mỗi task con tính **kết quả riêng** rồi thành phần cha hợp nhất.

Ví dụ:

~~~java
long total = partialResults.stream()
        .mapToLong(Long::longValue)
        .reduce(0L, Math::addExact);
~~~

Đây là cách cộng các kết quả đã hoàn tất, thay vì để nhiều thread cùng thay đổi biến `total` dùng chung. Phải lưu ý giới hạn `long` và đảm bảo mỗi phần dữ liệu đầu vào chỉ được tính một lần theo yêu cầu nghiệp vụ.

## 8. Tác vụ chạy lại: phân biệt trạng thái của “một lần thử” và của “công việc”

Trong xử lý nền, cùng một tác vụ nghiệp vụ có thể được thực thi nhiều lần do retry, timeout hoặc tiến trình dừng đột ngột.

Ví dụ một job nhập 10.000 bản ghi:

- **Job ID:** nhận diện công việc mà người dùng yêu cầu.
- **Attempt ID:** nhận diện một lần cố gắng xử lý.
- **Trạng thái tạm của attempt:** bộ đếm trong bộ nhớ, buffer, danh sách lỗi đang tổng hợp.
- **Checkpoint bền vững:** vị trí đã xác nhận hoàn tất, có thể đọc lại sau restart.
- **Trạng thái nghiệp vụ:** bản ghi đã được nhập, cập nhật theo cơ chế nhất quán.

Một thiết kế chỉ dùng `static int processedCount` cho tất cả job có thể làm trộn số liệu giữa các lần chạy và mất thông tin khi restart. Trái lại, mỗi attempt có bộ đếm cục bộ sẽ cách ly tốt hơn, nhưng **không tự ngăn xử lý trùng** nếu retry đã ghi một phần dữ liệu.

### 8.1. Vòng đời trạng thái trong một lần chạy

~~~mermaid
flowchart TD
    A[Nhận yêu cầu hoặc tác vụ] --> B[Tạo dữ liệu/ngữ cảnh của lần xử lý]
    B --> C[Thực thi với trạng thái cục bộ]
    C --> D{Kết thúc thế nào?}
    D -- Thành công --> E[Ghi kết quả theo hợp đồng]
    D -- Thất bại --> F[Ghi lỗi và dọn tài nguyên]
    D -- Hủy --> G[Dọn tài nguyên, ghi trạng thái hủy nếu cần]
    E --> H[Kết thúc phạm vi xử lý]
    F --> H
    G --> H
~~~

Nếu cần checkpoint hoặc kết quả bền vững, phải ghi qua kho lưu trữ có hợp đồng đồng thời và xác nhận phù hợp. Sau khi phạm vi xử lý kết thúc, các tham chiếu đến dữ liệu riêng không nên bị giữ lại trong cache hoặc map toàn cục mà không có lý do và chính sách dọn dẹp.

### 8.2. “Dùng map theo requestId” chưa chắc là tách trạng thái đúng

Một cách khắc phục thường gặp là thay field bằng:

~~~java
// Chỉ minh họa một cấu trúc có thể gặp:
Map<String, MutableTaskState> statesByRequestId;
~~~

Đây vẫn là **trạng thái dùng chung** ở cấp map. Muốn thiết kế an toàn, cần trả lời:

- ID có duy nhất đúng phạm vi không? Có cần kết hợp tenant và attempt ID?
- `MutableTaskState` có được nhiều thread sửa cùng lúc không?
- Ai xóa phần tử sau khi kết thúc? Có TTL/giới hạn dung lượng?
- Task bị hủy, timeout, restart hoặc crash được xử lý ra sao?
- Việc cập nhật nhiều trường có yêu cầu nguyên tử không?
- Đây là dữ liệu tạm thời hay trạng thái cần lưu bền vững?

`ConcurrentHashMap` chỉ hỗ trợ tính an toàn cho **các thao tác của map theo hợp đồng**; nó không tự làm cho mọi thay đổi bên trong `MutableTaskState` trở nên nguyên tử hay đúng nghiệp vụ.

Nếu không cần chia sẻ trạng thái giữa nhiều request, **đừng đưa nó vào map toàn cục** chỉ để “dễ tìm”.

## 9. Kiểm thử sự cô lập của các yêu cầu

Một dịch vụ có thể qua unit test khi gọi tuần tự nhưng sai khi xử lý đồng thời. Vì vậy cần kiểm thử cả **tính đúng riêng lẻ** và **sự độc lập giữa các lần gọi**.

### 9.1. Kiểm thử dữ liệu không bị lẫn

Ví dụ JUnit 5 (dựa trên `CartLine`, `QuoteRequest`, `QuoteResult`, `QuoteService` ở phần 3):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.Test;

class QuoteServiceTest {
    @Test
    void keepsResultsIndependentAcrossConcurrentRequests()
            throws Exception {

        QuoteService service = new QuoteService();
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<QuoteRequest> requests = new ArrayList<>();
            List<Callable<QuoteResult>> tasks = new ArrayList<>();

            for (int i = 1; i <= 100; i++) {
                QuoteRequest request = new QuoteRequest(
                        "REQ-" + i,
                        List.of(new CartLine("P-01", 1_000L, i)));
                requests.add(request);
                tasks.add(() -> service.calculate(request));
            }

            List<Future<QuoteResult>> futures = pool.invokeAll(tasks);

            for (int i = 0; i < requests.size(); i++) {
                QuoteResult result = futures.get(i).get();
                QuoteRequest input = requests.get(i);

                assertEquals(input.requestId(), result.requestId());
                assertEquals((long) (i + 1) * 1_000L,
                        result.totalVnd());
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Test gọi **cùng một instance** từ nhiều thread và xác minh từng kết quả gắn đúng request. Nó có giá trị để phát hiện một số lỗi cô lập; nhưng **test đồng thời qua vài lần không chứng minh không còn race condition**. Cần kết hợp xem xét quyền sở hữu mutable state, kiểm thử biên, và kiểm thử có điều phối thứ tự xen kẽ nếu nghi ngờ một điểm tranh chấp.

### 9.2. Kiểm thử đầu vào không bị thay đổi sau khi nhận

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import org.junit.jupiter.api.Test;

class RequestSnapshotTest {
    @Test
    void snapshotsLineList() {
        ArrayList<CartLine> original = new ArrayList<>();
        original.add(new CartLine("P-01", 10_000L, 2));

        QuoteRequest request = new QuoteRequest("REQ-1", original);
        original.clear();

        QuoteResult result = new QuoteService().calculate(request);

        assertEquals(20_000L, result.totalVnd());
        assertEquals(1, request.lines().size());
    }
}
~~~

Test này cho thấy việc thay đổi danh sách nguồn **sau khi constructor trả về** không làm thay đổi request đã tạo. Nó không bao quát mọi tình huống đọc/ghi đồng thời ngay trong lúc sao chép một danh sách mutable; trước khi tạo snapshot, cần đảm bảo bên tạo không đang sửa đồng thời thiếu đồng bộ.

### 9.3. Trường hợp lỗi nên kiểm tra

| Trường hợp | Hành vi cần xác nhận |
| --- | --- |
| Hai request đồng thời có ID khác nhau | Kết quả của từng request vẫn gắn đúng ID |
| Một request thất bại khi request khác thành công | Trạng thái lỗi không làm hỏng bộ tích lũy của request khác |
| Bên gọi sửa danh sách sau khi gửi request | Dữ liệu đã chốt để tính không tự thay đổi |
| Task A bị hủy, task B đang chạy | Dọn tài nguyên A không xóa hoặc sửa dữ liệu của B |
| Cùng job bị retry sau timeout | Không ghi trùng dữ liệu nghiệp vụ hoặc tính lặp sai |
| Hai task cùng cập nhật một bản ghi thật | Có cơ chế giao dịch/phiên bản/đồng bộ theo bất biến nghiệp vụ |
| Thread được tái sử dụng cho request khác | Không sót `ThreadLocal` hoặc dữ liệu ngữ cảnh cũ |
| Một request tạo nhiều task con | Ngữ cảnh cần thiết được chuyển đúng, kết quả được hợp nhất có kiểm soát |

Các tình huống có database, message broker hoặc framework nên được kiểm tra bằng integration test phù hợp, không chỉ dùng mock. Độ tin cậy cần được chứng minh tại đúng ranh giới có rủi ro.

## 10. Các quyết định đánh đổi

Tách trạng thái theo phạm vi thường làm mã an toàn và dễ kiểm thử hơn, nhưng cũng có chi phí thiết kế:

| Phương án | Lợi ích | Chi phí / rủi ro | Khi nào cân nhắc |
| --- | --- | --- | --- |
| Biến cục bộ trong phương thức | Dễ hiểu, vòng đời rõ, tự cô lập mỗi lần gọi | Phải truyền dữ liệu qua các hàm cần dùng | Mặc định cho tính toán của một yêu cầu |
| Đối tượng context bất biến | Dữ liệu liên quan đi cùng nhau; dễ truyền qua async | Có thể phình to thành đối tượng chứa quá nhiều trách nhiệm | Nhiều thành phần cần cùng một ngữ cảnh |
| Tạo instance mới theo request | Cô lập field instance mutable trong một phạm vi | Cần quản lý vòng đời và chi phí khởi tạo | Đối tượng thực sự giữ trạng thái của một request |
| `ThreadLocal` | Tích hợp thuận tiện với một số cơ chế đồng bộ theo thread | Dễ sót cleanup, sai ngữ cảnh trong async | Khi framework đã quy định và vòng đời được kiểm soát |
| Map trạng thái dùng chung theo ID | Cho phép tra cứu từ nhiều nơi | Cần đồng bộ, giới hạn, cleanup, quyền và khóa phù hợp | Có yêu cầu chia sẻ trạng thái thật sự |
| Kho dữ liệu bền vững | Hỗ trợ retry/restart, nhiều tiến trình | Cần giao dịch, schema, tính nhất quán, vận hành | Trạng thái phải sống vượt một lần chạy |

Lựa chọn phù hợp tùy **tuổi thọ dữ liệu, mức chia sẻ và hậu quả khi sai**. Không phải cứ dùng đối tượng bất biến là mọi vấn đề đồng thời đều biến mất: nếu hai task cùng ghi một tài nguyên bên ngoài, ranh giới cần bảo vệ nằm ở tài nguyên đó.

## 11. Những nhầm lẫn thường gặp

**“Mỗi request chạy trên thread riêng nên field singleton là an toàn.”** Sai. Field của một instance dùng chung vẫn được mọi thread nhìn thấy. Chỉ biến cục bộ mới tự tách trong mỗi lần gọi, miễn không chia sẻ tham chiếu mutable ra ngoài.

**“Đã dùng `volatile` hoặc `AtomicReference` thì hết lẫn request.”** Không. Những công cụ này không tạo một giá trị riêng cho mỗi request; chúng hỗ trợ truy cập một giá trị dùng chung theo những bảo đảm cụ thể.

**“Dùng `ThreadLocal` tức là đã có request scope.”** Không chính xác. Thread có thể được tái sử dụng, còn request có thể chuyển qua nhiều thread. Vòng đời dữ liệu cần được quản lý theo request hoặc task thực.

**“Bất biến chỉ cần khai báo field là `final`.”** Chưa đủ. `final List<...>` không ngăn người khác sửa các phần tử của danh sách hoặc sửa chính danh sách mutable qua tham chiếu; cần xem tính bất biến của toàn bộ cấu trúc dữ liệu liên quan.

**“`ConcurrentHashMap` làm mọi đối tượng trong map an toàn.”** Không. Map bảo vệ các thao tác map theo hợp đồng; các đối tượng mutable và bất biến nghiệp vụ vẫn cần thiết kế đồng bộ riêng.

**“Tác vụ chạy lại thì cứ tạo object mới là xong.”** Chưa đủ. Request/task isolation chỉ nói về trạng thái đang chạy; ghi dữ liệu nghiệp vụ vẫn cần idempotency, checkpoint và giao dịch khi có retry.

**“Stateless nghĩa là không có trạng thái ở đâu.”** Không. Dịch vụ stateless có thể đọc dữ liệu bền vững, dùng cache và gọi API; nó chỉ không giữ **trạng thái riêng của từng yêu cầu** trong instance được chia sẻ.

**“Không tái hiện được race thì không có lỗi.”** Race condition thường phụ thuộc lịch chạy; lần kiểm thử thành công không chứng minh quyền sở hữu trạng thái đã đúng.

**“Tách mọi thứ thành đối tượng mới sẽ tốt hơn.”** Không hẳn. Client mạng, connection pool, metric và cấu hình an toàn khi dùng chung thường nên được tái sử dụng để tiết kiệm tài nguyên. Phân tách cần theo **ý nghĩa và vòng đời**, không theo thói quen tạo object.

## 12. Quy trình review mã đang xử lý nhiều yêu cầu

Khi review một handler, service hoặc worker, có thể đi theo thứ tự:

1. **Xác định vòng đời đối tượng:** framework tạo handler singleton, mỗi request một instance hay mỗi task một instance? Chưa biết thì phải kiểm tra cấu hình thay vì suy đoán từ tên lớp.
2. **Đánh dấu field mutable:** biến nào bị thay đổi trong quá trình xử lý? Nó thuộc request, task, session hay trạng thái dùng chung có chủ đích?
3. **Vẽ đường dữ liệu:** dữ liệu của một lần gọi đi từ đầu vào đến kết quả và tác dụng phụ nào? Có chỗ nào gán vào static field, cache hoặc map chung không?
4. **Kiểm tra bất biến và sở hữu:** tham chiếu danh sách, map hoặc object có thể bị sửa bởi bên khác sau khi nhận không? Có cần snapshot hoặc hợp đồng rõ?
5. **Kiểm tra chuyển thread:** có `CompletableFuture`, executor, reactive pipeline, scheduler hoặc callback không? Ngữ cảnh có truyền đúng qua ranh giới không?
6. **Xác nhận xử lý retry và cancel:** dữ liệu nào cần giữ bền vững, dữ liệu nào cần dọn, tác dụng phụ có thể lặp không?
7. **Thiết kế kiểm thử:** test logic đơn lẻ, test gọi đồng thời, test thất bại xen kẽ, và integration test khi có trạng thái dùng chung ngoài tiến trình.
8. **Đánh giá chi phí:** chia sẻ tài nguyên nào là hợp lý, và biến nào bắt buộc phải tách để tránh nhầm dữ liệu?

Phương pháp trên giúp phát hiện cả trường hợp **lộ dữ liệu giữa người dùng**, **lỗi số liệu**, **race condition** và **khó kiểm thử**, đồng thời tránh tạo nhiều lớp trừu tượng không cần thiết.

## 13. Bài tập vận dụng

### Tình huống A — Handler dùng chung giữ `currentUserId`

Một web controller được framework tạo một lần cho toàn ứng dụng. Trước khi gọi service, controller gán `this.currentUserId = authenticatedUserId`. Một phương thức khác đọc field đó để kiểm tra quyền.

**Câu hỏi:** rủi ro gì và nên sửa thế nào?

**Gợi ý:** Hai request có thể làm lẫn danh tính, dẫn đến kiểm tra quyền trên người khác. Nên đưa danh tính **đã được xác thực** qua tham số hoặc ngữ cảnh yêu cầu có vòng đời phù hợp, thực hiện kiểm tra quyền ở ranh giới nghiệp vụ, và test khi các request chạy xen kẽ. Thêm `volatile` không giải quyết việc nhiều request dùng chung một ô nhớ.

### Tình huống B — Dùng `ThreadLocal` cho mã yêu cầu

Một filter gán mã request vào `ThreadLocal` rồi gọi service. Sau khi response trả về, thread được đưa lại pool; filter không xóa dữ liệu. Một request tiếp theo dùng cùng thread và không thiết lập mã mới.

**Câu hỏi:** log có thể xuất hiện vấn đề gì?

**Gợi ý:** Request sau có thể dùng mã tương quan của request trước, làm sai truy vết và có thể rò thông tin. Cần cleanup `finally`; khi có xử lý bất đồng bộ, phải xem cách framework truyền context và không dựa vào thread identity.

### Tình huống C — Job nhập dữ liệu có retry

Một job xử lý một triệu dòng; khi lỗi ở dòng 700.000, worker restart và chạy lại từ đầu. Job có biến đếm riêng nên số liệu của các job khác không lẫn.

**Câu hỏi:** như vậy đã đủ bảo đảm đúng đắn chưa?

**Gợi ý:** Chưa. Những bản ghi đã ghi trước khi lỗi có thể được nhập lặp. Cần checkpoint và chiến lược idempotency hoặc cập nhật có điều kiện phù hợp. Đếm riêng giải quyết cô lập trạng thái trong bộ nhớ, không giải quyết tính đúng đắn của trạng thái bền vững.

### Tình huống D — Parallel processing trên danh sách dùng chung

Một task chia danh sách đầu vào thành bốn phần, mỗi task con tính một subtotal. Cả bốn task cùng gọi `totals.add(subtotal)` trên một `ArrayList` dùng chung.

**Câu hỏi:** dữ liệu có được bảo vệ vì mỗi subtotal là biến cục bộ không?

**Gợi ý:** Không. Biến subtotal riêng từng task nhưng `ArrayList` là mutable state dùng chung; thêm đồng thời không được bảo đảm an toàn. Có thể trả `Future<Long>` cho từng task, đợi hoàn tất và tổng hợp ở cha, hoặc dùng cấu trúc đồng bộ phù hợp nếu bắt buộc chia sẻ.

## 14. Checklist trước khi đưa vào vận hành

- **Sở hữu:** trạng thái nào dành riêng cho request/task và trạng thái nào được chia sẻ có chủ đích?
- **Vòng đời:** ai tạo, ai dọn, điều gì xảy ra khi timeout, exception, cancel hoặc restart?
- **Bất biến:** dữ liệu chuyển qua các tầng có bị sửa sau khi đã tiếp nhận không?
- **Đồng thời:** có hai luồng nào cùng ghi một đối tượng không, và hợp đồng đồng bộ là gì?
- **Ngữ cảnh:** danh tính, quyền và correlation ID có đi theo đúng yêu cầu qua async không?
- **Tài nguyên:** có chia sẻ thread pool, HTTP client, cache một cách an toàn và có giới hạn không?
- **Bền vững:** dữ liệu nào cần lưu qua retry/restart, tránh xử lý trùng bằng cách nào?
- **Kiểm chứng:** đã thử gọi song song, lỗi xen kẽ và trường hợp đầu vào bị thay đổi chưa?
- **Dễ bảo trì:** người khác có thể xác định nơi lưu trạng thái và ai được phép thay đổi nó chỉ từ code/hợp đồng không?

Tách trạng thái theo từng yêu cầu hoặc tác vụ giúp **loại bỏ một nguồn sai lệch khó phát hiện**: dữ liệu của các lần xử lý độc lập vô tình ảnh hưởng lẫn nhau. Trong **CODE_QUALITY_FUNDAMENTALS**, thiết kế tốt không chỉ là tránh race condition, mà còn làm quyền sở hữu dữ liệu rõ ràng, kiểm thử có thể cô lập và việc thay đổi ít lan truyền rủi ro hơn. Chia sẻ những tài nguyên cần chia sẻ, đồng thời giữ **dữ liệu riêng đúng phạm vi và vòng đời của nó**, là một nền tảng để mã nguồn đáng tin cậy, dễ hiểu và dễ thay đổi.
