# Hủy tác vụ

## 1. Hủy tác vụ trong Language Server là gì?

Một Language Server thường xử lý nhiều yêu cầu từ editor: hoàn thành mã, tìm định nghĩa, tìm reference, hover, rename, format, phân tích chẩn đoán và các tác vụ khác. Một số yêu cầu có thể mất thời gian vì phải phân tích nhiều file, lập chỉ mục workspace hoặc gọi dịch vụ bên ngoài.

**Hủy tác vụ (task cancellation)** là cơ chế cho phép client hoặc server thông báo rằng một công việc đang chạy không còn cần thiết và yêu cầu nó dừng. Cơ chế này giúp Language Server phản hồi nhanh, tránh lãng phí CPU và bộ nhớ, đồng thời ngăn kết quả cũ ghi đè kết quả mới.

Ví dụ, người dùng đang gõ:

~~~text
customer.addre
~~~

Editor gửi yêu cầu completion. Trước khi server hoàn thành, người dùng tiếp tục gõ:

~~~text
customer.address
~~~

Yêu cầu completion trước đó có thể không còn hữu ích. Editor có thể hủy request cũ và gửi request mới với nội dung hiện tại. Nếu server vẫn tiếp tục xử lý mọi request cũ đến hết, nó có thể tiêu tốn tài nguyên và trả kết quả đã lỗi thời.

Hủy tác vụ đặc biệt quan trọng trong IDE vì các yêu cầu thường được kích hoạt liên tục khi người dùng gõ, di chuyển con trỏ, mở file hoặc thay đổi project.

Một thiết kế cancellation tốt cần:

- Theo dõi từng request đang chạy.
- Nhận thông báo hủy từ client.
- Truyền tín hiệu hủy đến các bước xử lý bên trong.
- Kiểm tra tín hiệu tại các điểm phù hợp.
- Dừng công việc càng sớm càng tốt.
- Giải phóng tài nguyên và trạng thái tạm.
- Không phát hành kết quả cũ như thể nó còn hợp lệ.
- Phân biệt request bị hủy với lỗi cú pháp hoặc lỗi nội bộ.

## 2. Vì sao Language Server cần cancellation?

Nếu không có cancellation, một thao tác đã lỗi thời vẫn có thể tiếp tục chạy.

### 2.1 Người dùng tạo request mới liên tục

Completion, signature help và hover có thể được gọi nhiều lần trong vài giây. Request trước thường trở nên không cần thiết khi vị trí con trỏ hoặc nội dung tài liệu thay đổi.

### 2.2 Workspace lớn

Find references, workspace symbol và indexing có thể phải duyệt nhiều file. Người dùng có thể đóng cửa sổ, đổi project hoặc chuyển sang một thao tác khác trước khi quá trình hoàn tất.

### 2.3 Tránh kết quả cũ

Một kết quả được tính từ document version cũ có thể không còn đúng với nội dung hiện tại. Cancellation giúp dừng tính toán không còn cần thiết; kiểm tra version vẫn cần thiết để ngăn kết quả cũ được công bố.

### 2.4 Tiết kiệm tài nguyên

Hủy sớm có thể giảm:

- CPU dùng cho parse và type checking không còn cần thiết.
- Bộ nhớ của AST, index tạm và danh sách kết quả.
- Số truy vấn đến database hoặc dịch vụ ngoài.
- Công việc nền của các worker.
- Độ trễ của request mới đang chờ tài nguyên.

### 2.5 Giữ trải nghiệm editor mượt

Một server không phản ứng với cancellation có thể làm completion xuất hiện muộn, diagnostics nhấp nháy hoặc thao tác điều hướng bị chậm. Cancellation là một phần của khả năng phản hồi, không chỉ là tối ưu hiệu năng.

## 3. Cancellation trong JSON-RPC và LSP

Language Server Protocol (LSP) sử dụng JSON-RPC để trao đổi request, response và notification.

- **Request:** có ID và cần response tương ứng.
- **Response:** trả kết quả hoặc lỗi cho một request.
- **Notification:** thông điệp không có response.

Client hủy một request đang chạy bằng notification **$/cancelRequest**, với tham số id khớp ID của request cần hủy.

Ví dụ thông điệp khái quát:

~~~json
{
  "jsonrpc": "2.0",
  "method": "$/cancelRequest",
  "params": {
    "id": 17
  }
}
~~~

Request ban đầu có thể là:

~~~json
{
  "jsonrpc": "2.0",
  "id": 17,
  "method": "textDocument/references",
  "params": {
    "textDocument": {
      "uri": "file:///workspace/policy.dsl"
    },
    "position": {
      "line": 12,
      "character": 8
    },
    "context": {
      "includeDeclaration": true
    }
  }
}
~~~

Server dùng ID 17 để tìm công việc đang chạy và yêu cầu công việc đó dừng.

### 3.1 Cancellation notification không phải request mới

$/cancelRequest là notification. Client không chờ một response riêng cho notification này. Server xử lý tín hiệu hủy đối với request có ID được chỉ định.

### 3.2 Request bị hủy vẫn cần kết thúc đúng giao thức

Với một request đã được nhận, server cần hoàn tất vòng đời JSON-RPC theo quy tắc của giao thức. Trong LSP, mã lỗi RequestCancelled là -32800 và được dùng để biểu thị request bị hủy.

Ví dụ response lỗi:

~~~json
{
  "jsonrpc": "2.0",
  "id": 17,
  "error": {
    "code": -32800,
    "message": "Request cancelled"
  }
}
~~~

Notification hủy không có response riêng; response lỗi ở trên là kết quả kết thúc request ban đầu.

### 3.3 Server không thể giả định client sẽ luôn chờ

Client có thể hủy request vì người dùng đã đổi ngữ cảnh, nhưng server cũng cần xử lý các tình huống request hoàn tất đúng lúc cancellation đến. Đây là race condition bình thường trong hệ thống bất đồng bộ.

### 3.4 ID phải được quản lý đúng

Request ID có thể là số hoặc chuỗi theo JSON-RPC. Server cần dùng đúng kiểu ID khi tra cứu. Không nên chuyển tất cả ID thành số hoặc so sánh bằng cách ép kiểu khiến hai ID khác nhau bị xem là một.

## 4. Vòng đời của một request

Một request trong Language Server thường đi qua các giai đoạn:

~~~text
Client sends request
        |
        v
Server receives request
        |
        v
Register request ID
and cancellation state
        |
        v
Run handler
        |
        +---- cancellation received
        |             |
        |             v
        |       signal cancellation
        |             |
        |             v
        |       handler stops safely
        |
        v
Complete or cancel request
        |
        v
Send one response
        |
        v
Remove request state
~~~

Các trạng thái nội bộ có thể gồm:

| Trạng thái | Ý nghĩa |
|---|---|
| RECEIVED | Server đã nhận request |
| RUNNING | Handler đang thực hiện |
| CANCELLATION_REQUESTED | Đã nhận tín hiệu hủy |
| COMPLETING | Đang hoàn tất và chuẩn bị response |
| COMPLETED | Đã gửi response thành công |
| CANCELLED | Công việc đã dừng do cancellation |
| FAILED | Công việc kết thúc vì lỗi khác |

Đây là mô hình triển khai minh họa, không phải tập trạng thái bắt buộc của LSP.

### 4.1 Đăng ký request trước khi chạy

Server cần ghi nhận ID và cancellation handle trước khi bắt đầu công việc bất đồng bộ. Nếu công việc bắt đầu trước khi được đăng ký, một notification hủy đến sớm có thể không tìm thấy request.

### 4.2 Kết thúc đúng một lần

Một request không được gửi nhiều response. Khi cancellation và completion xảy ra gần như đồng thời, server cần có cơ chế phối hợp để chỉ một nhánh được quyền hoàn tất request.

### 4.3 Dọn trạng thái sau khi kết thúc

Sau khi request hoàn tất, server cần xóa entry khỏi bảng request đang chạy. Nếu giữ lại, bảng có thể tăng không giới hạn hoặc một ID cũ có thể ảnh hưởng request khác.

### 4.4 Cancellation đến quá muộn

Nếu request đã hoàn tất và entry đã bị xóa, cancellation notification đến sau đó không thể dừng công việc đã kết thúc. Server nên xử lý trường hợp này một cách an toàn, không làm lỗi các request khác.

## 5. Cancellation token

Một cách phổ biến để truyền tín hiệu hủy trong code là **cancellation token**.

Token là một đối tượng hoặc handle cho phép phần xử lý kiểm tra xem công việc đã được yêu cầu dừng hay chưa.

API khái quát:

~~~java
interface CancellationToken {
    boolean isCancellationRequested();

    void throwIfCancellationRequested();
}
~~~

Handler nhận token:

~~~java
List<Location> findReferences(
    SymbolId symbol,
    CancellationToken token
) {
    List<Location> result = new ArrayList<>();

    for (Document document : workspace.documents()) {
        token.throwIfCancellationRequested();
        result.addAll(findInDocument(document, symbol, token));
    }

    return result;
}
~~~

Token giúp truyền cancellation qua nhiều lớp mà không cần mỗi hàm truy cập trực tiếp vào bảng request của JSON-RPC.

### 5.1 Cancellation source

Thông thường có một đối tượng sở hữu quyền phát tín hiệu hủy, gọi là cancellation source. Source tạo token để các thành phần khác đọc trạng thái.

~~~java
CancellationSource source = new CancellationSource();
CancellationToken token = source.token();

// Một thành phần khác có thể gọi:
source.cancel();
~~~

Tên API trên là minh họa. Java standard library không có sẵn đúng giao diện CancellationSource/CancellationToken này; dự án có thể dùng thư viện, abstraction nội bộ hoặc kết hợp Future, interruption và cờ hủy.

### 5.2 Token chỉ nên truyền một chiều

Thành phần thực thi nhận token để quan sát cancellation. Nó không nên tự ý reset token hoặc xóa tín hiệu hủy. Một source đã hủy thường giữ trạng thái hủy cho toàn bộ token được tạo từ nó.

### 5.3 Token dùng chung

Các bước con của cùng một request có thể nhận chung token:

~~~text
Request token
   |
   +--> Parser
   |
   +--> Name resolver
   |
   +--> Type checker
   |
   +--> Reference search
~~~

Khi request bị hủy, các bước đang chạy có thể quan sát cùng một tín hiệu.

## 6. Cooperative cancellation

Phần lớn hệ thống compiler và Language Server dùng **cooperative cancellation**: công việc tự kiểm tra tín hiệu tại các điểm an toàn và chủ động dừng.

Ví dụ:

~~~java
for (Node node : ast.nodes()) {
    token.throwIfCancellationRequested();
    analyze(node);
}
~~~

Không nên chờ đến cuối toàn bộ AST mới kiểm tra token nếu việc duyệt có thể kéo dài hàng phút.

### 6.1 Chọn cancellation point

Điểm kiểm tra phù hợp thường nằm:

- Đầu mỗi file khi phân tích workspace.
- Trong vòng lặp duyệt node lớn.
- Giữa các phase compiler.
- Trước truy vấn hoặc thao tác I/O tốn thời gian.
- Sau khi nhận kết quả từ dịch vụ bên ngoài.
- Trước khi xây dựng hoặc công bố kết quả lớn.

Không cần kiểm tra ở mọi lệnh nhỏ nếu chi phí kiểm tra đáng kể. Hãy đặt điểm kiểm tra đủ thường xuyên để độ trễ hủy có thể chấp nhận được.

### 6.2 Cancellation latency

Cancellation latency là khoảng thời gian từ lúc tín hiệu hủy được phát đến lúc công việc thực sự dừng.

Nếu một vòng lặp xử lý hàng triệu node mà chỉ kiểm tra token ở cuối, cancellation latency có thể rất cao. Nếu kiểm tra quá dày trong một thao tác rất nhỏ, overhead có thể tăng.

Hãy đo latency trên workload thực tế và chọn tần suất kiểm tra phù hợp.

### 6.3 Dừng ở ranh giới an toàn

Nếu đang cập nhật một cấu trúc dùng chung, không nên dừng giữa một thao tác khiến trạng thái bị hỏng. Có thể hoàn tất một đơn vị nhỏ có tính nguyên tử rồi kiểm tra cancellation trước đơn vị tiếp theo.

### 6.4 Không nuốt tín hiệu hủy

Nếu code bắt mọi exception rồi tiếp tục, cancellation có thể bị biến thành lỗi thông thường:

~~~java
try {
    analyzeDocument(document, token);
} catch (Exception ex) {
    log(ex);
    continue;
}
~~~

Nếu CancellationException cũng bị bắt như trên, request có thể tiếp tục chạy dù đã được yêu cầu dừng. Hãy phân biệt cancellation với lỗi phân tích thông thường và truyền tín hiệu hủy lên tầng điều phối.

## 7. Cancellation trong các phase của compiler

Một Language Server thường có pipeline:

~~~text
Text document
    |
    v
Lexing
    |
    v
Parsing
    |
    v
Name resolution
    |
    v
Type checking
    |
    v
Semantic analysis
    |
    v
Request result
~~~

Cancellation cần được truyền xuyên suốt pipeline.

### 7.1 Lexing

Lexer có thể kiểm tra token định kỳ khi xử lý file lớn. Nếu scanner đọc một đoạn rất dài hoặc xử lý chuỗi đặc biệt, cần có cách dừng mà không giữ tài nguyên tạm.

### 7.2 Parsing

Parser có thể kiểm tra token trong vòng lặp parse hoặc khi đi qua cấu trúc lồng nhau. Với parser đệ quy sâu, cần tránh việc cancellation chỉ được kiểm tra ở một điểm quá xa.

### 7.3 Name resolution

Name resolver có thể duyệt scope, import và symbol graph. Đây là nơi cancellation hữu ích khi workspace lớn hoặc có nhiều dependency.

### 7.4 Type checking

Type inference hoặc constraint solving có thể tốn thời gian. Các vòng lặp giải constraint nên có cancellation point và giới hạn tài nguyên.

### 7.5 Semantic rules

Rule engine cần truyền token cho từng rule. Một rule plugin chạy lâu mà không kiểm tra cancellation có thể giữ toàn bộ request không kết thúc.

### 7.6 Indexing

Indexing thường là công việc nền. Nếu một file thay đổi trong khi index đang xử lý snapshot cũ, server có thể hủy task cũ và lên lịch task mới. Kết quả index chỉ nên được commit nếu snapshot vẫn còn hợp lệ.

### 7.7 Sinh kết quả

Ngay trước khi trả response, handler nên kiểm tra request còn hợp lệ và chưa bị hủy. Tuy nhiên, kiểm tra cuối không thay thế các điểm kiểm tra trong quá trình tính toán.

## 8. Propagate cancellation qua nhiều tầng

Một lỗi thiết kế thường gặp là chỉ truyền cancellation token đến handler ngoài cùng. Các hàm sâu hơn vẫn chạy mà không biết request đã bị hủy.

Ví dụ cấu trúc:

~~~java
CompletionList complete(
    DocumentSnapshot document,
    Position position,
    CancellationToken token
) {
    token.throwIfCancellationRequested();

    Scope scope = resolver.scopeAt(
        document,
        position,
        token
    );

    token.throwIfCancellationRequested();

    return completionEngine.complete(
        scope,
        position,
        token
    );
}
~~~

Các hàm con cũng cần nhận token:

~~~java
Scope scopeAt(
    DocumentSnapshot document,
    Position position,
    CancellationToken token
) {
    for (ImportDeclaration declaration : document.imports()) {
        token.throwIfCancellationRequested();
        resolveImport(declaration, token);
    }
    return buildScope(document, position, token);
}
~~~

### 8.1 Không tạo token mới không liên quan

Nếu mỗi tầng tạo một token độc lập và không liên kết với token request, tín hiệu hủy bên ngoài sẽ không đến được công việc con.

### 8.2 Linked cancellation

Một task con có thể cần dừng khi:

- Request cha bị hủy.
- Server shutdown.
- Timeout nội bộ.
- Người dùng đóng workspace.

Có thể tạo linked token kết hợp nhiều nguồn. Khi một nguồn phát tín hiệu, task con dừng theo chính sách đã định.

### 8.3 Phân biệt lý do hủy

Dù nhiều nguyên nhân cùng dẫn đến trạng thái dừng, hệ thống có thể lưu lý do:

- CLIENT_REQUESTED.
- SERVER_SHUTDOWN.
- DOCUMENT_SUPERSEDED.
- TIMEOUT.
- RESOURCE_LIMIT.

Lý do giúp logging và xử lý kết quả phù hợp. Không phải mọi lý do đều cần trả cùng một mã lỗi cho client.

## 9. Hủy task bất đồng bộ và thread

Language Server thường xử lý request trên executor hoặc thread pool. Cancellation cần tương tác đúng với cơ chế concurrency.

### 9.1 Future và CompletableFuture

Java Future có phương thức cancel. Với:

~~~java
future.cancel(true);
~~~

tham số true yêu cầu interrupt thread đang thực thi nếu implementation hỗ trợ. Đây là yêu cầu interrupt, không phải bảo đảm thread dừng ngay.

Một số API hoặc task không kiểm tra interruption có thể tiếp tục chạy.

### 9.2 Interrupt

Thread interruption là tín hiệu hợp tác. Code có thể:

- Kiểm tra Thread.currentThread().isInterrupted().
- Gọi các API blocking có hỗ trợ interruption.
- Ném InterruptedException.

Nếu bắt InterruptedException, thường cần dọn tài nguyên và khôi phục interrupt flag khi không truyền exception lên:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new CancellationException("Task interrupted");
}
~~~

Ví dụ này minh họa cách bảo toàn interrupt status. Thiết kế thực tế cần thống nhất cách chuyển InterruptedException thành cancellation trong toàn ứng dụng.

### 9.3 Không interrupt bừa bãi thread dùng chung

Thread pool có thể tái sử dụng thread cho request khác. Hủy nhầm hoặc xử lý interrupt không đúng có thể ảnh hưởng task tiếp theo.

Chỉ hủy Future thuộc đúng request và bảo đảm worker không tiếp tục dùng thread sau khi trạng thái bị gián đoạn.

### 9.4 CPU-bound và I/O-bound

CPU-bound task cần kiểm tra token trong vòng lặp. I/O-bound task cần dùng API hỗ trợ timeout, cancellation hoặc đóng resource phù hợp. Một lời gọi mạng không có timeout có thể khiến cancellation bị trì hoãn rất lâu.

## 10. Quản lý request đang chạy

Server thường cần một bảng theo dõi request:

~~~text
Request ID -> RequestContext

17 -> {
  cancellation source,
  future,
  document version,
  start time
}

"workspace-42" -> {
  cancellation source,
  future,
  workspace snapshot
}
~~~

Ví dụ Java đơn giản:

~~~java
final class RequestRegistry {
    private final ConcurrentMap<Object, RequestContext> requests =
        new ConcurrentHashMap<>();

    void register(Object id, RequestContext context) {
        RequestContext previous = requests.putIfAbsent(id, context);
        if (previous != null) {
            throw new IllegalStateException(
                "Request ID is already active: " + id
            );
        }
    }

    void cancel(Object id) {
        RequestContext context = requests.get(id);
        if (context != null) {
            context.cancel();
        }
    }

    void complete(Object id, RequestContext context) {
        requests.remove(id, context);
    }
}
~~~

Đây là mô hình minh họa. RequestContext cần cung cấp cancellation source và trạng thái hoàn tất thread-safe. Việc remove(id, context) giúp tránh xóa nhầm entry mới nếu ID được tái sử dụng sau khi request cũ kết thúc.

### 10.1 Đăng ký và hủy có race condition

Cancellation notification có thể đến sát thời điểm request được đăng ký. Cần thiết kế thứ tự:

1. Nhận request.
2. Tạo context.
3. Đăng ký context.
4. Bắt đầu worker.

Nếu giao thức hoặc runtime cho phép cancellation đến trước khi registration hoàn tất, server cần quy định cách xử lý ID chưa được biết.

### 10.2 Cleanup trong finally

~~~java
try {
    return handler.execute(context.token());
} finally {
    registry.complete(requestId, context);
    context.close();
}
~~~

Cleanup không nên phụ thuộc vào việc handler trả kết quả bình thường.

### 10.3 Không giữ request đã kết thúc

Nếu không xóa entry, server có thể giữ reference đến document, AST, future và token lâu hơn cần thiết. Đây là một nguồn memory leak.

## 11. Race condition giữa cancellation và completion

Cancellation và hoàn tất có thể xảy ra gần như đồng thời.

Ví dụ:

1. Worker tính xong completion list.
2. Client gửi notification hủy.
3. Worker chuẩn bị gửi response.
4. Handler nhận tín hiệu hủy.

Server cần có quy tắc xác định request đã hoàn tất hay cancellation thắng.

### 11.1 Trạng thái terminal

Có thể dùng atomic state hoặc lock để chỉ một nhánh chuyển request sang terminal state:

~~~text
RUNNING
   | \
   |  \
   v   v
COMPLETED  CANCELLED
~~~

Không được chuyển từ COMPLETED sang CANCELLED rồi gửi thêm một response thứ hai.

### 11.2 Cancellation sau khi response đã gửi

Nếu response đã được gửi, cancellation đến sau không thể thu hồi response. Client cần kiểm tra context và document version để quyết định có sử dụng kết quả hay không.

### 11.3 Không gửi success giả sau khi đã hủy

Nếu handler đã quan sát cancellation và dừng trước khi hoàn tất, nó không nên trả một kết quả rỗng như thể request thành công. Điều đó khiến client khó phân biệt "không có kết quả" với "không hoàn thành".

### 11.4 Exactly-once response

Với mỗi request đã được nhận, tầng giao thức cần bảo đảm một kết quả kết thúc duy nhất: success hoặc error. Cancellation không tạo thêm một request response riêng ngoài response của request gốc.

## 12. Cancellation và tài liệu đã thay đổi

Một trường hợp phổ biến trong editor là request được tính trên document version cũ.

Ví dụ:

~~~text
Version 10: customer.addre
Version 11: customer.address
Version 12: customer.address.city
~~~

Server có thể đang phân tích version 10 khi version 11 đến. Server nên:

1. Hủy hoặc đánh dấu task version 10 là lỗi thời.
2. Tạo snapshot cho version 11.
3. Bắt đầu phân tích mới.
4. Chỉ công bố kết quả nếu version vẫn phù hợp.

### 12.1 Cancellation không thay thế version check

Một task cũ có thể hoàn tất đúng lúc cancellation được gửi. Vì vậy, server vẫn phải kiểm tra version trước khi publish diagnostics hoặc trả kết quả có phụ thuộc tài liệu.

### 12.2 ContentModified

LSP định nghĩa mã lỗi ContentModified là -32801 cho trường hợp nội dung liên quan đã thay đổi khiến request không thể được thực hiện trên trạng thái cũ. Đây là tình huống khác với việc client trực tiếp yêu cầu hủy request.

### 12.3 Snapshot bất biến

Mỗi task nên làm việc trên document snapshot có version cụ thể. Tránh để một worker đọc nội dung đang bị sửa đồng thời mà không có đồng bộ.

### 12.4 Publish diagnostics

Diagnostics thường được tính từ notification thay đổi tài liệu, không phải request có ID riêng. Khi có thay đổi mới, server có thể hủy computation cũ và lên lịch computation mới. Khi công bố, nên gắn version nếu phù hợp và bỏ qua kết quả không còn là snapshot mới nhất.

## 13. Hủy request và hủy công việc nền

Không phải mọi task của Language Server đều gắn với một JSON-RPC request.

Ví dụ:

- Workspace indexing.
- File watching.
- Cập nhật diagnostics.
- Refresh semantic cache.
- Background analysis.
- Tải metadata hoặc schema.

Các task này cần cancellation handle nội bộ hoặc cơ chế supersession.

### 13.1 Task gắn với request

Client gửi request có ID; server quản lý task theo ID. $/cancelRequest có thể tìm và yêu cầu task dừng.

### 13.2 Task gắn với document version

Task phân tích document version 10 có thể bị thay thế bởi task version 11. Dù client không gửi $/cancelRequest cho task nội bộ, server vẫn có thể hủy computation version 10.

### 13.3 Task gắn với workspace

Khi workspace đóng hoặc project configuration đổi, các task phụ thuộc snapshot cũ cần dừng hoặc bị đánh dấu stale.

### 13.4 Server shutdown

Khi nhận yêu cầu shutdown, server nên ngừng nhận công việc mới theo lifecycle của giao thức, phát tín hiệu hủy cho task nền và giải phóng tài nguyên. Cần phân biệt shutdown với exit và các thông điệp lifecycle khác của LSP.

## 14. Debounce, coalescing và cancellation

Cancellation thường phối hợp với debounce hoặc coalescing để tránh làm việc quá nhiều khi người dùng gõ liên tục.

### 14.1 Debounce

Debounce trì hoãn công việc cho đến khi input ngừng thay đổi trong một khoảng thời gian.

~~~text
User types: c
User types: cu
User types: cus
User types: cust
        |
        v
Wait for short quiet period
        |
        v
Run analysis for latest text
~~~

Debounce giảm số lần bắt đầu task. Cancellation dừng task đã bắt đầu nhưng không còn cần thiết. Hai kỹ thuật bổ trợ nhau.

### 14.2 Coalescing

Nếu nhiều sự kiện cùng yêu cầu cập nhật index, server có thể gộp chúng thành một công việc mới nhất thay vì chạy từng task riêng.

### 14.3 Không debounce mọi request

Một số thao tác cần phản hồi ngay như go to definition hoặc rename. Chính sách scheduling cần dựa trên loại request và trải nghiệm mong muốn.

### 14.4 Cancellation không phải queue management

Hủy task cũ không tự động bảo đảm task mới được chạy ngay. Server vẫn cần quản lý thread pool, queue priority và giới hạn concurrency.

## 15. Partial result và progress

Một số request LSP hỗ trợ partial result hoặc work-done progress. Server có thể gửi tiến độ hoặc từng phần kết quả trong lúc xử lý.

### 15.1 Partial result

Ví dụ workspace symbol có thể trả kết quả theo từng nhóm thay vì đợi toàn bộ workspace được duyệt.

Nếu request bị hủy:

- Server nên dừng tạo thêm phần kết quả.
- Không được giả vờ phần dữ liệu đã gửi là toàn bộ kết quả.
- Client cần coi request đã bị hủy là không hoàn tất.
- Phần kết quả từng phần đã nhận có thể cần được bỏ qua theo semantics của method và client.

### 15.2 Work-done progress

Progress giúp client hiển thị trạng thái như indexing hoặc searching. Progress token và request ID là các khái niệm khác nhau; server cần quản lý vòng đời của từng loại token theo giao thức.

### 15.3 Hủy không đồng nghĩa hoàn tất 100%

Khi hủy, server không nên gửi progress 100% nếu công việc chưa hoàn tất. Có thể kết thúc progress theo quy tắc method/client hỗ trợ và ghi nhận trạng thái bị hủy.

### 15.4 Không phát hành kết quả từng phần lỗi thời

Nếu tài liệu thay đổi, partial results được tính từ snapshot cũ có thể không còn hữu ích. Server cần kiểm tra version hoặc request context trước khi tiếp tục phát kết quả.

## 16. Cancellation trong truy vấn và dịch vụ bên ngoài

Một Language Server có thể truy cập:

- Database symbol index.
- Remote schema registry.
- Documentation service.
- Build server.
- Package metadata.
- Dịch vụ phân tích bảo mật.

Cancellation cần truyền đến các dịch vụ này nếu API hỗ trợ.

### 16.1 Timeout

Nếu dịch vụ ngoài không hỗ trợ cancellation, cần đặt timeout để request không bị treo vô hạn. Timeout và cancellation là hai nguyên nhân khác nhau nhưng có thể cùng dẫn đến dừng công việc.

### 16.2 Hủy HTTP request

HTTP client có thể cung cấp call cancellation hoặc đóng stream. Chỉ hủy Future ở tầng gọi chưa chắc đã dừng socket hoặc truy vấn đang chạy; cần dùng API cancellation thực tế của client.

### 16.3 Database query

Nếu driver hỗ trợ cancel query, server có thể gọi cơ chế đó khi token bị hủy. Cần kiểm tra trạng thái connection sau cancellation vì một số driver yêu cầu rollback hoặc reset session.

### 16.4 Hạn chế side effect

Các request như completion hoặc hover nên chủ yếu đọc dữ liệu. Nếu task đã ghi file, thay đổi database hoặc gửi lệnh đến thiết bị, cancellation không tự hoàn tác tác động đã xảy ra.

Hãy tránh thực hiện side effect trước khi request được xác nhận hoặc dùng transaction/compensation phù hợp.

## 17. Cancellation và cleanup tài nguyên

Khi task dừng, cần giải phóng tài nguyên:

- File handle.
- Stream.
- Database cursor.
- Temporary buffer.
- Lock.
- Subscription.
- Child task.
- Reference đến snapshot và AST.

Ví dụ:

~~~java
try (InputStream input = openDocumentStream()) {
    while (true) {
        token.throwIfCancellationRequested();
        int count = readChunk(input);
        if (count < 0) {
            break;
        }
        processChunk(count);
    }
}
~~~

Try-with-resources giúp đóng stream khi thoát bình thường hoặc khi exception/cancellation được truyền ra.

### 17.1 finally

Dùng finally cho cleanup không phụ thuộc kết quả:

~~~java
try {
    return runAnalysis(token);
} finally {
    releaseTemporaryState();
}
~~~

### 17.2 Không cleanup tài nguyên của task khác

Task có thể chia sẻ cache hoặc connection pool. Cancellation chỉ được giải phóng tài nguyên mà task sở hữu hoặc được phép release.

### 17.3 Child tasks

Nếu request tạo nhiều task con, cancellation của parent cần truyền xuống child. Parent cũng phải chờ hoặc quản lý việc dừng child để tránh task mồ côi tiếp tục chạy.

### 17.4 Cleanup phải an toàn khi chạy lặp

Trong một số thiết kế, cleanup có thể được gọi từ nhiều nhánh kết thúc. Hãy làm cho cleanup idempotent hoặc bảo vệ bằng trạng thái để không đóng hai lần tài nguyên không hỗ trợ.

## 18. Cancellation không phải rollback

Đây là điểm quan trọng: **cancellation dừng công việc; nó không tự động hoàn tác những tác động đã xảy ra**.

Ví dụ:

~~~text
1. Write generated file A
2. Write generated file B
3. Cancellation arrives
4. File C is not written
~~~

Sau cancellation, A và B vẫn có thể đã tồn tại. Nếu yêu cầu thao tác phải nguyên tử, hệ thống cần một transaction hoặc chiến lược commit riêng.

### 18.1 Prepare rồi commit

Một cách an toàn:

1. Tính toàn bộ kết quả vào vùng tạm.
2. Kiểm tra cancellation.
3. Xác nhận snapshot còn hợp lệ.
4. Commit kết quả như một thao tác nhất quán.

### 18.2 Compensation

Với hành động không thể rollback trực tiếp, có thể cần hành động bù (compensation). Ví dụ, nếu một dịch vụ đã tạo tài nguyên, hệ thống có thể gửi yêu cầu xóa tài nguyên đó. Compensation cũng có thể thất bại nên phải được quản lý như một quy trình riêng.

### 18.3 Request chỉ đọc

Các request editor như hover, completion và references nên tránh side effect. Khi chúng bị hủy, việc dừng tính toán thường đơn giản hơn vì không có trạng thái bên ngoài cần khôi phục.

## 19. Error handling và mã lỗi

Server cần phân biệt:

- Request bị client hủy.
- Server tự hủy vì shutdown hoặc policy.
- Nội dung tài liệu đã thay đổi.
- Timeout.
- Lỗi nội bộ.
- Lỗi từ dịch vụ ngoài.

Một số mã LSP liên quan:

| Mã | Tên | Ý nghĩa khái quát |
|---:|---|---|
| -32800 | RequestCancelled | Request bị hủy |
| -32801 | ContentModified | Nội dung liên quan đã thay đổi |
| -32802 | ServerCancelled | Server hủy request |
| -32803 | RequestFailed | Request thất bại theo điều kiện được mô tả |

Việc dùng mã cụ thể cần tuân theo phiên bản LSP và semantics của method. Không nên trả RequestCancelled cho mọi lỗi timeout hoặc lỗi nội bộ nếu nguyên nhân khác.

### 19.1 Cancellation exception nội bộ

Trong code, có thể dùng CancellationException hoặc một kiểu exception riêng. Tầng JSON-RPC chuyển trạng thái đó thành error response phù hợp.

### 19.2 Không báo cancellation như lỗi cú pháp

Nếu parser dừng vì token đã bị hủy, server không nên tạo diagnostic "Unexpected end of input" như thể source sai. Cancellation không phải lỗi chương trình DSL.

### 19.3 Logging

Cancellation thường là sự kiện bình thường khi người dùng gõ liên tục. Không nên log ở mức ERROR cho mọi request bị hủy. Có thể ghi debug/trace hoặc metric tổng hợp.

### 19.4 Tránh log quá nhiều

Một editor có thể hủy hàng trăm request trong một phiên. Log từng request ở mức cao sẽ gây nhiễu và làm phình file log.

## 20. Cancellation trong các loại request LSP

Mỗi request có đặc điểm và chính sách khác nhau.

| Request hoặc tác vụ | Khi nào có thể hủy | Lưu ý |
|---|---|---|
| Completion | Người dùng gõ tiếp hoặc đổi vị trí | Kết quả cũ thường không còn cần |
| Hover | Con trỏ chuyển sang vị trí khác | Không hiển thị hover stale |
| Signature help | Người dùng sửa đối số hoặc rời lời gọi | Giữ document version |
| References | Người dùng đổi symbol hoặc đóng view | Tìm kiếm có thể tốn thời gian |
| Workspace symbols | Query mới thay thế query cũ | Có thể xử lý partial result |
| Rename | Người dùng hủy dialog hoặc tài liệu đổi | Không áp dụng workspace edit dở dang |
| Formatting | Document thay đổi trước khi áp dụng | Kiểm tra version và range |
| Diagnostics | Có document change mới | Thường là task nội bộ theo version |
| Indexing | Workspace đổi hoặc đóng | Commit index theo snapshot |

Không phải method nào cũng hỗ trợ partial result hoặc có cùng semantics cancellation. Handler cần theo đúng đặc tả method và khả năng client.

## 21. Scheduling và ưu tiên request

Cancellation giúp dừng công việc cũ, nhưng server vẫn cần chính sách scheduling.

### 21.1 Thread pool

Thread pool giới hạn số request chạy đồng thời. Nếu tất cả worker bị chiếm bởi task nền lâu, completion mới có thể phải chờ.

### 21.2 Priority

Có thể ưu tiên thao tác tương tác như completion hoặc hover hơn indexing toàn workspace. Tuy nhiên, priority cần được cân bằng để task nền không bị đói tài nguyên mãi mãi.

### 21.3 Bounded queue

Queue không giới hạn có thể tích lũy request cũ nhanh hơn khả năng xử lý. Server nên giới hạn queue và loại bỏ hoặc hủy task đã lỗi thời theo chính sách.

### 21.4 Latest-wins

Với một số tác vụ theo document, chỉ kết quả của phiên bản mới nhất có ý nghĩa. Server có thể áp dụng latest-wins: hủy task cũ và giữ task mới nhất.

Không nên dùng latest-wins cho mọi request. Ví dụ, hai thao tác độc lập trên hai tài liệu khác nhau có thể cần hoàn thành cả hai.

## 22. Thiết kế cancellation trong Java

Một mô hình đơn giản có thể kết hợp token, Future và registry.

~~~java
final class RequestContext {
    private final AtomicBoolean cancelled = new AtomicBoolean();
    private final AtomicBoolean completed = new AtomicBoolean();
    private volatile Future<?> future;

    CancellationToken token() {
        return new CancellationToken() {
            @Override
            public boolean isCancellationRequested() {
                return cancelled.get()
                    || Thread.currentThread().isInterrupted();
            }

            @Override
            public void throwIfCancellationRequested() {
                if (isCancellationRequested()) {
                    throw new CancellationException();
                }
            }
        };
    }

    void attach(Future<?> future) {
        this.future = future;
        if (cancelled.get()) {
            future.cancel(true);
        }
    }

    void cancel() {
        if (cancelled.compareAndSet(false, true)) {
            Future<?> current = future;
            if (current != null) {
                current.cancel(true);
            }
        }
    }

    boolean tryComplete() {
        return completed.compareAndSet(false, true);
    }
}
~~~

Đây là ví dụ minh họa ý tưởng. Implementation thực tế cần xử lý race giữa attach/cancel, trạng thái completed/cancelled, việc gửi response và cleanup bằng một state machine hoặc cơ chế đồng bộ đầy đủ. Đoạn mã không phải một implementation LSP hoàn chỉnh.

### 22.1 Handler

~~~java
void handleReferences(
    RequestId id,
    ReferencesParams params
) {
    RequestContext context = new RequestContext();
    registry.register(id, context);

    Future<?> future = executor.submit(() -> {
        try {
            List<Location> locations =
                referenceService.find(params, context.token());

            context.token().throwIfCancellationRequested();

            if (context.tryComplete()) {
                protocol.sendResult(id, locations);
            }
        } catch (CancellationException ex) {
            if (context.tryComplete()) {
                protocol.sendError(
                    id,
                    LspError.REQUEST_CANCELLED,
                    "Request cancelled"
                );
            }
        } catch (Exception ex) {
            if (context.tryComplete()) {
                protocol.sendInternalError(id, ex);
            }
        } finally {
            registry.remove(id, context);
        }
    });

    context.attach(future);
}
~~~

Ví dụ trên thể hiện các thành phần cần phối hợp. Trong triển khai thật, không được để Future.cancel(true) tự hoàn tất request trước khi worker có cơ hội gửi response, cũng không được để worker gửi response sau khi tầng giao thức đã hoàn tất. Cần thiết kế rõ quyền sở hữu response và xử lý task bị hủy trước khi bắt đầu chạy.

### 22.2 Kiểm tra token trong service

~~~java
List<Location> find(
    ReferencesParams params,
    CancellationToken token
) {
    List<Location> result = new ArrayList<>();

    for (DocumentSnapshot document : workspace.snapshot()) {
        token.throwIfCancellationRequested();
        result.addAll(index.find(document, params, token));
    }

    return result;
}
~~~

Từng tầng cần hợp tác với cancellation. Chỉ hủy Future ở handler ngoài cùng chưa đủ nếu service bên trong không kiểm tra tín hiệu.

## 23. Kiểm thử cancellation

Cancellation cần được kiểm thử như một phần của request lifecycle và concurrency.

### 23.1 Kiểm thử cơ bản

- Request chạy bình thường trả success.
- Request đang chạy nhận $/cancelRequest.
- Handler quan sát token và dừng.
- Request kết thúc bằng cancellation error phù hợp.
- Request registry được dọn.
- Request không bị gửi hai response.

### 23.2 Kiểm thử race condition

- Cancellation đến trước khi worker bắt đầu.
- Cancellation đến trong khi handler đang chạy.
- Cancellation đến ngay trước khi hoàn tất.
- Cancellation đến sau response.
- Hai notification hủy cùng một ID.
- ID không tồn tại hoặc đã hoàn tất.

### 23.3 Kiểm thử propagation

Tạo một pipeline nhiều tầng và xác nhận cancellation đến được lexer, resolver, type checker hoặc rule engine. Một test chỉ kiểm tra token ở handler không chứng minh các task con dừng.

### 23.4 Kiểm thử cleanup

Sau cancellation, xác nhận:

- Stream đã đóng.
- Temporary buffer được giải phóng.
- Child task đã dừng hoặc được quản lý.
- Registry không còn entry.
- Lock được nhả.
- Không có kết quả stale được publish.

### 23.5 Kiểm thử document version

1. Bắt đầu phân tích version 10.
2. Gửi nội dung version 11.
3. Hủy hoặc supersede task cũ.
4. Cho task cũ hoàn tất muộn nếu có thể.
5. Xác nhận diagnostics version 10 không ghi đè kết quả version 11.

### 23.6 Kiểm thử latency

Đo thời gian từ khi phát cancellation đến khi task dừng. Kiểm tra với file nhỏ, file lớn, dependency graph sâu và tác vụ I/O.

### 23.7 Kiểm thử không hủy nhầm

Hủy request ID A không được dừng request ID B. Hủy một document task không được ảnh hưởng request độc lập trên document khác.

## 24. Quan sát và đo lường

Một hệ thống cancellation cần metrics để biết nó hoạt động tốt không.

Các chỉ số hữu ích:

- Số request bị hủy.
- Tỷ lệ request bị hủy trên tổng request.
- Cancellation latency.
- CPU time tiết kiệm được ước tính.
- Số task bị hủy nhưng vẫn chạy sau ngưỡng.
- Số request kết thúc do timeout.
- Số stale result bị loại bỏ.
- Số child task còn tồn tại sau khi parent kết thúc.
- Số lỗi cleanup.

### 24.1 Tỷ lệ cancellation cao có phải lỗi?

Không nhất thiết. Completion có thể bị hủy thường xuyên khi người dùng gõ liên tục. Điều cần quan tâm là task có dừng nhanh và server có giữ được độ phản hồi hay không.

### 24.2 Log có correlation ID

Khi điều tra, log nên liên kết request ID, document URI, version và lý do hủy. Không cần log toàn bộ nội dung tài liệu; tránh ghi source code nhạy cảm vào log.

### 24.3 Trace

Distributed trace có thể cho biết cancellation được truyền đến dịch vụ ngoài hay bị dừng ở một tầng. Với task nội bộ, trace span giúp nhận diện bước nào có cancellation latency cao.

## 25. Những sai lầm thường gặp

### Chỉ đánh dấu request là cancelled

Đổi trạng thái trong registry nhưng worker vẫn tiếp tục chạy.

**Cách khắc phục:** truyền token đến mọi tầng và kiểm tra tại cancellation point.

### Giả định interrupt luôn dừng thread

Code không kiểm tra interrupt có thể tiếp tục chạy.

**Cách khắc phục:** dùng cooperative cancellation và API I/O hỗ trợ hủy.

### Không phân biệt cancellation với lỗi cú pháp

Parser dừng do cancellation nhưng tạo diagnostic source error.

**Cách khắc phục:** dùng loại kết quả hoặc exception riêng cho cancellation.

### Gửi nhiều response

Completion và cancellation race khiến cả hai nhánh cùng gửi response.

**Cách khắc phục:** dùng state transition nguyên tử để chỉ một nhánh hoàn tất request.

### Không xóa request context

Entry giữ lại token, future và document sau khi kết thúc.

**Cách khắc phục:** cleanup trong finally và kiểm tra registry sau các đường kết thúc.

### Hủy request nhưng vẫn publish kết quả cũ

Worker hoàn tất muộn và gửi diagnostics cho version không còn hiện tại.

**Cách khắc phục:** kiểm tra cancellation và document version ngay trước khi publish.

### Coi cancellation là rollback

File hoặc database đã thay đổi trước khi nhận tín hiệu hủy.

**Cách khắc phục:** dùng prepare/commit, transaction hoặc compensation nếu có side effect.

### Không truyền cancellation xuống child task

Parent dừng nhưng child vẫn chạy.

**Cách khắc phục:** linked cancellation và quản lý vòng đời child task.

### Queue không giới hạn

Server nhận nhiều request cũ hơn khả năng xử lý.

**Cách khắc phục:** bounded queue, priority và chính sách supersession.

## 26. Quy trình thiết kế cancellation cho Language Server

Khi xây dựng cancellation, có thể thực hiện:

1. **Phân loại task:** request JSON-RPC, document analysis hay background task.
2. **Xác định owner:** thành phần nào tạo, hủy và hoàn tất task.
3. **Quản lý ID:** ánh xạ request ID đến context đang chạy.
4. **Tạo cancellation source:** mỗi request hoặc task có token phù hợp.
5. **Truyền token:** đi qua handler, parser, resolver, type checker và service.
6. **Chọn cancellation point:** đặt tại vòng lặp và ranh giới công việc tốn thời gian.
7. **Kết nối API bên ngoài:** dùng timeout/cancel thực tế của I/O hoặc database.
8. **Xử lý race:** chỉ cho phép một terminal response.
9. **Kiểm tra version:** không công bố kết quả từ snapshot lỗi thời.
10. **Cleanup:** đóng resource, dừng child task và xóa registry.
11. **Tách cancellation khỏi rollback:** dùng transaction nếu có side effect.
12. **Đo lường và kiểm thử:** race, propagation, cleanup, latency và stale result.

Một cancellation design tốt làm cho task dừng nhanh, trạng thái hệ thống vẫn nhất quán và client nhận được kết quả giao thức rõ ràng.

## 27. Ví dụ tổng hợp: completion bị thay thế bởi request mới

Giả sử editor đang mở policy.dsl.

### 27.1 Request đầu tiên

Document version 20:

~~~text
customer.addre
~~~

Editor gửi completion request ID 51. Server đăng ký RequestContext 51 và bắt đầu:

1. Tìm AST node tại vị trí con trỏ.
2. Resolve kiểu của customer.
3. Tìm thuộc tính phù hợp.
4. Xếp hạng completion items.

### 27.2 Người dùng gõ tiếp

Document version 21:

~~~text
customer.address
~~~

Editor gửi cancellation notification cho ID 51 và một completion request mới ID 52.

### 27.3 Server xử lý

- Context 51 nhận cancellation.
- Completion service kiểm tra token và dừng việc tìm kiếm.
- Request 51 kết thúc bằng response cancellation nếu chưa hoàn tất.
- Context 51 được xóa khỏi registry.
- Request 52 chạy trên snapshot version 21.

### 27.4 Ngăn kết quả stale

Ngay cả khi worker 51 đã tính xong trước khi quan sát cancellation, server vẫn kiểm tra request/document version trước khi công bố. Kết quả của version 20 không được thay thế completion của version 21.

### 27.5 Kết quả

Editor chỉ sử dụng completion phù hợp với nội dung mới nhất. Server không phải tiếp tục xử lý toàn bộ request cũ sau khi người dùng đã thay đổi input.

## 28. Câu hỏi tự kiểm tra

1. Hủy tác vụ trong Language Server giải quyết những vấn đề nào?
2. Phân biệt JSON-RPC request, response và notification.
3. $/cancelRequest dùng request ID như thế nào?
4. Vì sao cancellation notification không có response riêng nhưng request gốc vẫn cần kết thúc?
5. Cancellation token và cancellation source có vai trò gì?
6. Cooperative cancellation khác việc cưỡng bức dừng thread như thế nào?
7. Nên đặt cancellation point ở những phần nào của compiler pipeline?
8. Vì sao cần truyền token xuống child task?
9. Future.cancel(true) có bảo đảm thread dừng ngay không?
10. Race giữa cancellation và completion cần được xử lý ra sao?
11. Vì sao cancellation không thay thế document version check?
12. Phân biệt RequestCancelled và ContentModified.
13. Cancellation của background indexing khác cancellation của request như thế nào?
14. Debounce và cancellation bổ trợ nhau ra sao?
15. Vì sao cancellation không đồng nghĩa rollback?
16. Cần cleanup những tài nguyên nào sau khi task bị hủy?
17. Làm thế nào để tránh gửi nhiều response cho một request?
18. Những test nào xác nhận cancellation propagation và cancellation latency?

Hủy tác vụ là một phần thiết yếu của Language Server có khả năng phản hồi tốt. Khi request được quản lý theo ID, cancellation được truyền hợp tác qua các tầng xử lý, kết quả được kiểm tra theo document version và tài nguyên được dọn đúng cách, server có thể dừng công việc lỗi thời mà vẫn giữ trạng thái nhất quán cho editor.
