# 5.4 Đọc exception, cause chain, suppressed exception và stack frame

## Mục tiêu học tập

Khi service Java báo lỗi, một bản ghi có thể chứa nhiều exception, hàng chục stack frame, các dòng `Caused by:`, `Suppressed:` và ký hiệu `... n more`. Nếu chỉ nhìn dòng exception đầu tiên, dòng cuối cùng hoặc tìm một frame quen thuộc, ta có thể nhầm lỗi xử lý nghiệp vụ với lỗi dọn tài nguyên, nhầm wrapper với nguyên nhân ban đầu, hoặc bỏ qua bối cảnh thực thi có ý nghĩa.

Bài này hướng dẫn **đọc và giải thích exception từ log thực tế** theo đúng mô hình `Throwable` trong Java 17+:

- Phân biệt **exception đang được báo cáo**, **cause chain** và **suppressed exceptions**; hiểu chúng tạo thành cây/đồ thị thông tin chứ không chỉ một danh sách phẳng.
- Đọc từng **stack frame**: class, method, file, line, module, native method và thứ tự lời gọi; biết giới hạn của line number và stack trong môi trường tối ưu hóa.
- Hiểu cách `Throwable.printStackTrace()` nén các frame trùng bằng `... n more` và cách lần ra vị trí khởi phát lỗi, nơi chuyển đổi exception và điểm nó đi qua lớp xử lý.
- Tạo và phân tích ví dụ Java có đồng thời **cause** và **suppressed** từ `try-with-resources`, phân biệt lỗi chính với lỗi khi đóng tài nguyên.
- Thu thập stack trace có ngữ cảnh, giữ đầy đủ chuỗi nguyên nhân trong log/observability, đồng thời hạn chế lộ dữ liệu nhạy cảm và chi phí logging.
- Xây dựng quy trình tìm root cause có kiểm chứng, tránh kết luận chỉ dựa trên tên exception hoặc một stack frame đứng đầu.

## 1. Một exception trong Java thực chất mang những gì?

`Throwable` là kiểu gốc của các đối tượng Java có thể được ném bằng `throw`. Nó là lớp cha của `Exception` và `Error`. `RuntimeException` là một nhánh của `Exception`; sự phân biệt checked/unchecked liên quan quy tắc biên dịch, còn **cách đọc stack trace, cause và suppressed** dựa trên mô hình `Throwable` chung.

Một đối tượng `Throwable` thường giữ:

| Thành phần | API | Câu hỏi trả lời |
| --- | --- | --- |
| Kiểu exception | `t.getClass().getName()` | Loại thất bại được biểu diễn là gì? |
| Message | `t.getMessage()` | Tác giả exception diễn giải tình trạng này ra sao? |
| Stack trace | `t.getStackTrace()` | Những frame nào được ghi tại thời điểm stack trace của exception hình thành? |
| Cause | `t.getCause()` | Có exception khác được khai báo là nguyên nhân trực tiếp của exception hiện tại không? |
| Suppressed | `t.getSuppressed()` | Có lỗi phụ bị giữ lại trong khi một lỗi khác tiếp tục được truyền đi không? |

Các giá trị không bắt buộc phải đầy đủ: `getMessage()` có thể trả `null`; `getCause()` có thể `null`; `getSuppressed()` có thể là mảng rỗng; stack trace có thể rỗng hoặc thiếu frame trong một số điều kiện. Ngoài ra, lỗi được log từ framework có thể bị cắt, lọc hoặc biến đổi trước khi tới người đọc.

### 1.1 Phân biệt “throwable chính”, cause và suppressed

Ví dụ luồng xử lý:

```text
Application layer: IllegalStateException("Cannot complete checkout")  <-- throwable được log
    |
    +-- cause --> SQLException("Query failed")                         <-- nguyên nhân trực tiếp
    |                  |
    |                  +-- cause --> SocketTimeoutException("Read timed out")
    |
    +-- suppressed --> IOException("Failed to close resource")
```

Đây là **mô hình minh họa**, không phải một đoạn stack trace thật. `SQLException` và `SocketTimeoutException` cùng nằm trên **cause chain**; `IOException` xuất hiện trên nhánh **suppressed** của exception chính. Lỗi đóng tài nguyên không nhất thiết đã gây ra lỗi query; nó có thể chỉ xảy ra **trong lúc xử lý hậu quả của lỗi chính**.

Nguyên tắc:

- `getCause()` tạo liên kết **nguyên nhân được ứng dụng/JDK khai báo**. Một cause có thể có cause tiếp theo.
- `getSuppressed()` trả **tập lỗi phụ** được lưu lại thay vì đè lên lỗi chính. Mỗi suppressed throwable có thể tự có cause hoặc suppressed của riêng nó.
- `getStackTrace()` của **mỗi throwable** là một chuỗi frame riêng; nhiều throwable trong cùng log không mặc nhiên có cùng nguồn gốc.
- “Root cause” là **kết luận chẩn đoán có bối cảnh**. Cause cuối cùng trong chuỗi đôi khi là điểm xuất phát kỹ thuật có ý nghĩa, nhưng không tự chứng minh nguyên nhân nghiệp vụ/hệ thống.

## 2. Giải phẫu một stack trace được in ra

Xem bản minh họa cố ý dùng tên class và line number giả định:

```text
2026-10-29T08:15:30Z ERROR checkout-service traceId=abc123 checkout failed
java.lang.IllegalStateException: Cannot complete checkout
    at com.example.CheckoutService.checkout(CheckoutService.java:84)
    at com.example.CheckoutController.submit(CheckoutController.java:37)
    Suppressed: java.io.IOException: Cannot close audit stream
        at com.example.AuditWriter.close(AuditWriter.java:52)
        at com.example.CheckoutService.checkout(CheckoutService.java:76)
        ... 1 more
Caused by: java.sql.SQLException: Query failed
    at com.example.OrderRepository.save(OrderRepository.java:119)
    at com.example.CheckoutService.checkout(CheckoutService.java:80)
    ... 1 more
Caused by: java.net.SocketTimeoutException: Read timed out
    at java.base/sun.nio.ch.NioSocketImpl.timedRead(NioSocketImpl.java:289)
    ... 3 more
```

Đây là **trace tổng hợp để học cách đọc**, không phải stdout của chương trình chạy ở phần thực hành. Tùy logger/VM, message, indentation, tên module, line và cách in có thể khác; dòng đầu là **log event header**, không thuộc bản thân stack trace của `Throwable`.

### 2.1 Cấu trúc dòng

| Phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Header của log event | `ERROR checkout-service traceId=abc123` | Thời điểm, mức độ, service, correlation ID và thông điệp ở tầng logging |
| Throwable header | `java.lang.IllegalStateException: Cannot complete checkout` | Kiểu và message của throwable được log |
| Stack frame | `at com.example.CheckoutService.checkout(CheckoutService.java:84)` | Method đang nằm trên stack được ghi trong trace của throwable đó |
| Suppressed header | `Suppressed: java.io.IOException: ...` | Lỗi phụ được gắn vào throwable cha; thường được thụt sâu hơn |
| Cause header | `Caused by: java.sql.SQLException: ...` | Cause trực tiếp của throwable gần nhất theo cấu trúc in |
| Shared tail | `... 1 more` | Một số frame cuối trùng với trace bao quanh nên không lặp lại |

**Quan trọng:** `Caused by:` và `Suppressed:` không phải là tên các phương thức. Chúng mô tả **quan hệ giữa các đối tượng Throwable**. Dòng `at` mới mang một phần thông tin của `StackTraceElement`. Nếu log đã rút gọn hoặc bị chia thành nhiều event, phải khôi phục bối cảnh trước khi giải thích.

### 2.2 Vì sao không chỉ đọc dòng đầu hoặc dòng cuối?

Dòng đầu có thể là một wrapper hữu ích ở tầng service nhưng quá tổng quát, ví dụ `CompletionException` hoặc `IllegalStateException: request failed`. Dòng cuối của trace có thể là `main`, `Thread.run`, servlet/HTTP handler hoặc framework executor, chỉ cho thấy khung gọi từ bên ngoài, chưa phải nơi lỗi phát sinh.

Thông thường cần **đọc từ exception được log, lần theo từng `Caused by`, rồi xem frame đầu tiên có giá trị chẩn đoán ở từng tầng**, đồng thời kiểm tra nhánh suppressed. Không nên bỏ qua wrapper ngay lập tức: vị trí tạo wrapper có thể chỉ ra tầng nào chuyển đổi lỗi, retry, timeout hoặc quyết định biến exception thấp thành lỗi nghiệp vụ.

## 3. Cause chain: chuỗi nguyên nhân có chủ đích

### 3.1 Cơ chế Java

Một tầng repository có thể ném `SQLException`; tầng service muốn thể hiện lỗi ở ngôn ngữ nghiệp vụ nên wrap exception đó:

```java
// Đoạn minh họa, giả định repository có phương thức save(order).
try {
    repository.save(order);
} catch (SQLException original) {
    throw new IllegalStateException("Cannot save order", original);
}
```

Đoạn trên **không phải chương trình độc lập**: `repository` và `order` thuộc ứng dụng. Constructor `IllegalStateException(String, Throwable)` thiết lập `original` làm cause; khi log đầy đủ, JVM có thể in cả wrapper và `Caused by: java.sql.SQLException`.

Trường hợp giữ nguyên exception:

```java
// Bên trong một method có thể ném lại exception này.
try {
    riskyOperation();
} catch (IOException e) {
    auditFailure(e);
    throw e;
}
```

Hai method được gọi là **minh họa, không được định nghĩa ở đây**. `throw e` truyền **cùng một đối tượng**; nó không tự tạo cause mới và cũng không tự ghi lại stack tại dòng rethrow. Nếu tạo wrapper mới, wrapper nhận stack trace riêng và giữ cause qua constructor, giúp lưu cả vị trí chuyển đổi lẫn lỗi ban đầu.

### 3.2 Root cause không đồng nghĩa tuyệt đối với cause cuối

Xét chuỗi:

```text
CompletionException: request failed
  Caused by: IllegalStateException: inventory unavailable
    Caused by: SocketTimeoutException: Read timed out
```

Cause cuối mô tả **timeout khi đọc socket**; kết luận vận hành còn cần endpoint, thời điểm, network metrics, timeout policy và trạng thái downstream. Có thể là downstream quá tải, vấn đề mạng, timeout quá thấp, pool queue dài hoặc một request quá lớn. Stack trace **không chứng minh** riêng lẻ nguyên nhân hệ thống.

Một số framework còn wrap cùng lỗi nhiều lần (async, reflection, transaction, RPC), làm cause chain dài. Lớp wrapper có giá trị vì nói lỗi đi qua ranh giới nào, nhưng nên đi sâu tới cause có thông tin nhất. `getCause()==null` không chứng minh không tồn tại nguyên nhân: tác giả exception có thể không lưu cause, log bị cắt hoặc một hệ thống khác chỉ truyền text lỗi.

### 3.3 Cách đọc từng nút trong chain

Theo thứ tự:

1. Xác định **exception được log ở event chính**: class, message, timestamp, service/thread/traceId, vị trí trong request.
2. Với mỗi `Caused by`, ghi **class, message, frame phát sinh và lớp abstraction**: HTTP handler, service, repository, driver, network, parsing...
3. Đánh dấu vị trí **wrap/rethrow** để hiểu tại sao lỗi kỹ thuật xuất hiện dưới dạng lỗi nghiệp vụ.
4. Nếu lớp cuối nói “timeout”, “connection refused”, “constraint violation” hay “class not found”, xem đó là **giả thuyết kỹ thuật**, sau đó đối chiếu cấu hình, dữ liệu và telemetry.
5. Kiểm tra mọi **suppressed exception của từng nút**, vì suppressed có thể tiết lộ tài nguyên bị đóng thất bại hoặc một lỗi phụ đáng kể.
6. Đối chiếu **tần suất và điều kiện tái hiện**: một occurrence đơn lẻ không cho thấy tỷ lệ hay phạm vi tác động.

Khi trình bày kết quả, phân biệt **nguyên nhân do code khai báo trong cause chain** với **nguyên nhân gốc đã kiểm chứng**. Đây là hai mức khẳng định khác nhau.

### 3.4 API tạo và đọc cause

- `new IllegalStateException("msg", cause)` là cách trực tiếp và được ưu tiên khi thiết kế exception có cause.
- `Throwable.getCause()` trả một cause hoặc `null`; gọi lặp cho đến cuối chuỗi, nhưng với dữ liệu Throwable có thể tùy biến, code duyệt tổng quát nên kiểm soát số bước/những đối tượng đã xem để tránh vòng lặp bất thường.
- `initCause(cause)` dành cho các kiểu legacy không hỗ trợ constructor cause; chỉ được gán **một lần** và không được làm throwable tự gây ra chính nó.
- Gọi `new IllegalStateException("msg")` khi đang xử lý một exception khác nhưng **không truyền cause** khiến mối liên hệ có thể biến mất khỏi stack trace được in.
- `new IllegalStateException(e.toString())` chỉ sao chép **text**, không giữ `getCause()` hoặc stack của `e`.

Cũng cần biết một số API có chuỗi lỗi riêng ngoài cause/suppressed. Ví dụ `SQLException.getNextException()` biểu diễn các SQL exceptions liên quan; không phải mọi diagnostic detail đều nằm trên `getCause()`. Đọc contract của thư viện khi log thực tế gợi ý nhiều lỗi.

## 4. Suppressed exceptions: lỗi phụ không nên che lỗi chính

### 4.1 Vì sao Java cần suppressed?

Khi một tác vụ thất bại nhưng quá trình **đóng tài nguyên** cũng thất bại, ta có **hai lỗi** trong cùng một lần thực thi. Chỉ một exception được truyền ra theo cách thông thường. `try-with-resources` (Java 7+) ưu tiên giữ exception ném trong **thân `try`** làm exception chính; các exception do `close()` gây ra trong lúc unwinding thường được gắn dưới dạng suppressed.

Ví dụ:

```text
Thân try ném:       IllegalArgumentException("invalid request")
close() cũng ném:   IOException("cannot close stream")
Kết quả bắt được:   primary = IllegalArgumentException
                    primary.getSuppressed()[0] = IOException
```

Như vậy `Suppressed:` **không có nghĩa “lỗi bị bỏ qua và vô hại”**. Nó cho biết lỗi được giữ lại theo dạng phụ để bảo toàn lỗi chính. Một failure khi đóng transaction/file/socket có thể rất quan trọng, nhưng muốn biết nó có gây mất dữ liệu hay không phải phân tích ngữ cảnh của tài nguyên cụ thể.

### 4.2 Quy tắc try-with-resources cần nhớ

| Tình huống | Throwable truyền ra ngoài | Suppressed |
| --- | --- | --- |
| Thân `try` thành công, `close()` thành công | Không có exception | Không có |
| Thân `try` thất bại, đóng tài nguyên thành công | Exception từ thân `try` | Thường không có |
| Thân `try` thành công, `close()` thất bại | Exception do `close()` ném trở thành chính | Không có lỗi từ thân `try` |
| Thân `try` thất bại, `close()` thất bại | Exception từ thân `try` vẫn là chính | Exception đóng tài nguyên được gắn vào chính |
| Nhiều resources đóng thất bại | Quy tắc trên áp dụng theo quá trình unwind | Có thể có nhiều suppressed, thường theo thứ tự đóng ngược với khai báo |

Khi khai báo nhiều resources trong `try (A a = ...; B b = ...)`, Java đóng **B trước rồi A**. Nếu cả hai `close()` ném exception trong lúc xử lý một primary, có thể thấy `Suppressed` của B trước A. Trường hợp tạo/khởi tạo resource thất bại cũng có quy tắc unwind: các resource đã khởi tạo thành công trước đó vẫn phải được đóng và lỗi close có thể bị suppress.

### 4.3 Khác biệt với finally thủ công

Một `finally` ném exception mới có thể **thay thế exception đang truyền**, làm mất lỗi xảy ra ở thân `try` nếu code không chủ động giữ lại. `try-with-resources` sử dụng cơ chế suppression để giữ thông tin quan trọng; đó là lý do cần xem `Suppressed:` trong output.

```java
// Minh họa một anti-pattern: lỗi cleanup có thể che lỗi thao tác chính.
try {
    performBusinessOperation();
} finally {
    closeResource(); // Nếu lệnh này ném exception, nó có thể thay thế lỗi ở try.
}
```

Các method trên là giả định của ứng dụng và đoạn này không độc lập. Với tài nguyên thực thi `AutoCloseable`, ưu tiên `try-with-resources` khi phù hợp. Nếu phải dọn tài nguyên thủ công phức tạp, cần thiết kế cách giữ lại cả lỗi chính và lỗi phụ; không mặc định `finally` tự động gọi `addSuppressed`.

### 4.4 API suppressed

- `t.addSuppressed(other)` thêm lỗi phụ theo chủ đích, có kiểm tra `other != t` và `other != null`; không nên dùng tùy tiện để che một exception liên quan nhân quả.
- `t.getSuppressed()` trả mảng (có thể rỗng), **không trả null**.
- Suppression có thể bị vô hiệu hóa trong các constructor `Throwable` chuyên dụng; trong trường hợp đó `addSuppressed` không lưu lỗi và `getSuppressed()` rỗng.
- Một suppressed exception **có thể có cause**, còn một cause cũng có thể có suppressed. Vì vậy cần hiểu **cấu trúc phân nhánh** khi phân tích log dài.
- Suppressed không đồng nghĩa root cause của primary; nếu body bị timeout và close bị lỗi “connection closed”, nguyên nhân hai lỗi có thể liên hệ nhưng điều đó cần kiểm chứng.

## 5. Stack frame: đọc đúng class, method, source và line

Một stack frame thường được trình bày dạng:

```text
at package.Class.method(Class.java:123)
```

Trong trace có module Java 9+ có thể thấy:

```text
at java.base/java.util.ArrayList.get(ArrayList.java:427)
at my.module/com.example.OrderService.load(OrderService.java:58)
```

Hai dòng trên **minh họa cú pháp**, không cam kết line number ở mọi bản JDK. Dấu `java.base/` hoặc `my.module/` là thông tin module/runtime, không phải một phần của Java package name.

### 5.1 Từng thành phần của StackTraceElement

| Thành phần | API Java | Cách diễn giải |
| --- | --- | --- |
| Class | `getClassName()` | Tên lớp chứa method theo thông tin stack; có thể là lớp framework, proxy hoặc lớp do compiler tạo |
| Method | `getMethodName()` | Method trong frame; `<init>` biểu thị constructor, `<clinit>` là static initializer |
| Source file | `getFileName()` | Tên file nguồn nếu thông tin có sẵn; có thể null |
| Source line | `getLineNumber()` | Dòng được ghi từ debug/source mapping; giá trị âm hoặc marker đặc biệt khi không xác định |
| Native frame | `isNativeMethod()` | Thể hiện method native, thường hiển thị `Native Method` thay vì Java source line |
| Module | `getModuleName()`, `getModuleVersion()` | Nguồn module nếu có thông tin, có thể null |
| Class loader | `getClassLoaderName()` | Nhãn loader nếu có; không mặc nhiên xác định mọi class loader tùy biến |

`StackTraceElement[]` có **thứ tự từ đầu mảng là frame gần điểm ghi stack nhất**, còn frame cuối thường thuộc đường gọi từ lớp bao ngoài. Ví dụ:

```text
at com.example.Parser.parse(Parser.java:25)        <-- frame gần lỗi
at com.example.Service.execute(Service.java:73)
at com.example.Controller.post(Controller.java:44)
at ...
```

Không phải lúc nào frame đầu tiên cũng là code cần sửa: ví dụ stack có thể bắt đầu trong `java.base`, JDBC driver hoặc framework parser, còn **frame đầu của application** mới chỉ ra nơi gửi input sai. Nhưng cũng không được bỏ qua thư viện tự động: bug/cấu hình không tương thích hoặc version dependency có thể thực sự nằm tại đó.

### 5.2 Stack trace là ảnh chụp, không phải timeline

Theo `Throwable` API, stack trace thường được khởi tạo khi **Throwable được tạo** (qua `fillInStackTrace()` trong constructor), không phải tự động được thay mới ở mọi lần ném. Nếu exception được tạo sẵn ở một method rồi ném sau đó, top frame có thể trỏ đến **nơi tạo**, không phải nơi ném. `throw e` lại cùng exception không tự thêm frame vào stack.

Ngược lại, code `throw new IllegalStateException("...", e)` tạo wrapper mới với stack mới tại vị trí wrap; cause vẫn mang stack gốc của nó. Đây chính là lý do đọc **hai stack** rất hữu ích: một stack chỉ ra chỗ lỗi gốc được tạo, stack kia chỉ ra ranh giới chuyển đổi exception.

`fillInStackTrace()` có thể ghi lại trạng thái stack vào throwable và thay đổi bằng chứng, nên không coi là thao tác quan sát vô hại. Một số Throwable có thể cố ý không ghi stack để tối ưu; VM có thể bỏ frame trong điều kiện đặc biệt; lỗi low-memory/stack overflow cũng có thể thiếu dữ liệu.

### 5.3 Dòng line number có thật sự đáng tin?

Thông tin `File.java:123` thường dựa vào metadata debug của bytecode và stack capture. Nó hữu ích nhưng phải kiểm tra:

- **Đúng binary/JAR và phiên bản code đang chạy chưa?** Line 123 của commit mới có thể khác line 123 trong JAR trên production.
- **Debug line table có tồn tại không?** Build không chứa thông tin dòng có thể in `Unknown Source`; method native có thể in `Native Method`.
- **JIT, instrumentation, bytecode weaving, proxy, generated code** có thể làm mối quan hệ giữa dòng stack và source repo khó trực tiếp hơn.
- **Module/version/class loader** có thể khiến hai class có cùng tên đầy đủ nhưng đến từ nguồn thực thi khác nhau.
- **Async/task boundary** không luôn hiển thị toàn bộ quan hệ logic giữa producer và consumer; phải dùng trace/context để nối các bước xuyên thread.

Đừng nhìn `com.example.Foo.bar(Foo.java:88)` ở một log rồi mở ngay code branch hiện tại và coi line 88 là nguồn đáng tin nếu chưa xác nhận artifact/version thực sự.

### 5.4 Những tên đặc biệt

- `<init>`: constructor trong bytecode/trace.
- `<clinit>`: class initializer tĩnh; `ExceptionInInitializerError` có thể bao bọc lỗi gây ra khi khởi tạo lớp.
- `lambda$...`: method tổng hợp phục vụ lambda, không phải tên method khai báo trực tiếp trong source.
- `access$...` hoặc tên proxy/generated: dấu hiệu compiler/framework sinh code; quay lại caller application hoặc logic callback.
- `Native Method`: frame thực thi native, không mang Java line source.
- `Unknown Source`: chưa có thông tin file/line đủ rõ; không suy ra rằng exception không xuất phát từ Java.

## 6. Đọc “... n more” đúng nghĩa

Khi exception có cause/suppressed, các stack thường chia sẻ nhiều frame ở phía **cuối** (những call frames ngoài cùng). Để output không lặp vô ích, `printStackTrace()` có thể dùng:

```text
java.lang.IllegalStateException: service failed
    at app.Service.load(Service.java:20)
    at app.Main.main(Main.java:8)
Caused by: java.io.IOException: read failed
    at app.Client.read(Client.java:53)
    at app.Service.load(Service.java:18)
    ... 1 more
```

Đây là trace minh họa. `... 1 more` biểu thị **một frame cuối của stack cause trùng với frame cuối của stack bao quanh**, trong ví dụ là `app.Main.main(Main.java:8)`. Nó **không có nghĩa** “còn một exception khác”, “chương trình đã bỏ một lỗi” hay “không đủ RAM để in stack”. Tên frame trùng được suy ra từ stack ở **tầng bao quanh gần nhất** theo ngữ cảnh in.

Muốn dựng logic:

1. Đọc các frame được in rõ của cause/suppressed.
2. Khi thấy `... n more`, quay lại **đoạn trace bao quanh** mà nhánh đó thuộc về và bổ sung `n` frame cuối trùng.
3. Nếu có nhiều tầng causes và suppressed, dùng đúng **cấp thụt lề/quan hệ cha–con**; không tự gộp mọi `... n more` vào một exception duy nhất.
4. Nếu log platform đã truncate, không còn đủ enclosing trace hoặc event bị chia nhỏ, **không thể phục hồi chắc chắn toàn bộ** chỉ từ văn bản còn lại.

Ký hiệu nén trùng `... n more` trong Java stack trace **khác** thông báo của logger/aggregator như “truncated 200 lines”, “stack trace limit reached” hay thông báo bị cắt vì giới hạn kích thước. Hai hiện tượng dẫn đến mức độ đầy đủ bằng chứng khác nhau.

## 7. Ví dụ Java 17+ chạy độc lập: cause và suppressed cùng tồn tại

Đoạn sau tạo một exception do **parse input**, wrap thành exception có ngữ nghĩa nghiệp vụ, đồng thời gây lỗi lúc `close()`. Mục tiêu là nhìn trực tiếp `getCause()` và `getSuppressed()` trước khi phân tích trace có nhiều line number phụ thuộc môi trường.

Tạo tệp **`ExceptionGraphDemo.java`**:

```java
public final class ExceptionGraphDemo {
    private static final class FailingResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    private static void parse() {
        try {
            Integer.parseInt("not-a-number");
        } catch (NumberFormatException cause) {
            throw new IllegalArgumentException("invalid item id", cause);
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            parse();
        } catch (IllegalArgumentException error) {
            Throwable cause = error.getCause();
            Throwable[] suppressed = error.getSuppressed();

            System.out.println("primary=" + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
            System.out.println("cause=" + cause.getClass().getSimpleName());
            System.out.println("suppressed.count=" + suppressed.length);
            System.out.println("suppressed.first=" +
                    suppressed[0].getClass().getSimpleName() +
                    ": " + suppressed[0].getMessage());
            System.out.println("primary.topMethod=" +
                    error.getStackTrace()[0].getMethodName());
            System.out.println("suppressed.topMethod=" +
                    suppressed[0].getStackTrace()[0].getMethodName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ExceptionGraphDemo.java
java ExceptionGraphDemo
```

Trên JDK HotSpot thông thường với stack traces được bật, **stdout chính xác** là:

```text
primary=IllegalArgumentException: invalid item id
cause=NumberFormatException
suppressed.count=1
suppressed.first=IllegalStateException: close failed
primary.topMethod=parse
suppressed.topMethod=close
```

Hai dòng `topMethod` được lấy từ stack trace tiêu chuẩn của chương trình đơn giản này. API cho phép một số VM/điều kiện trả stack thiếu hoặc rỗng; nếu muốn viết ứng dụng production phòng thủ, **kiểm tra độ dài mảng trước khi truy cập `[0]`**. Kết quả không chứa line number cố định để không bị ảnh hưởng bởi vị trí code trong file.

### 7.1 Dòng nào là lỗi chính?

- `Integer.parseInt("not-a-number")` ném `NumberFormatException`. Trong `catch`, code tạo `IllegalArgumentException("invalid item id", cause)`. Đây là **wrapper chính** được throw.
- Khi rời `try-with-resources` do exception đó, Java vẫn gọi `FailingResource.close()`. Method `close()` ném `IllegalStateException("close failed")`.
- Theo semantics của `try-with-resources`, lỗi `close()` được **suppress vào lỗi chính**, chứ không tự thay thế `IllegalArgumentException`.
- Trong `catch` bên ngoài, `error.getCause()` là `NumberFormatException`, còn `error.getSuppressed()[0]` là `IllegalStateException` từ `close()`.
- Hai stack được lấy riêng: stack của wrapper có top `parse`, stack của lỗi đóng tài nguyên có top `close`. Cause `NumberFormatException` có stack riêng bên trong JDK parsing.

Vì `try-with-resources` quyết định primary và suppressed ở mức ngôn ngữ, **không có thứ tự “nặng hơn” mặc định** dựa trên class exception. Cần xem nghiệp vụ: một lỗi parse có thể là input invalid; lỗi close có thể cần xử lý riêng nếu ảnh hưởng tài nguyên.

### 7.2 Thử in toàn bộ exception tree

Trong `catch` của ví dụ, có thể **thêm tạm** dòng:

```java
error.printStackTrace();
```

Đây là đoạn bổ sung, **không phải chương trình chạy độc lập**. `printStackTrace()` mặc định ghi vào **`System.err`**, còn các dòng `println` phía trên ghi vào `System.out`. Khi hai luồng stdout/stderr được terminal hay log collector gộp lại, thứ tự hiển thị giữa chúng **không được đảm bảo**. Phần exception message, `Suppressed:`, `Caused by:` có thể quan sát trực tiếp, nhưng số dòng stack, module prefix, source line number và cách nén `... n more` phụ thuộc môi trường.

Muốn giữ tất cả vào một stream trong bài thực hành, dùng `error.printStackTrace(System.out)` khi mục tiêu là demo; trong ứng dụng thực tế ưu tiên logger được cấu hình, không tự trộn stdout/stderr khi cần log có cấu trúc.

### 7.3 Nếu muốn đọc stack bằng API

Có thể duyệt các frame theo thứ tự được ghi:

```java
// Đoạn minh họa đặt bên trong catch, với biến error của ví dụ trên.
for (StackTraceElement frame : error.getStackTrace()) {
    if (frame.getClassName().equals(ExceptionGraphDemo.class.getName())) {
        System.out.println("applicationMethod=" + frame.getMethodName());
        System.out.println("sourceFile=" + frame.getFileName());
        System.out.println("sourceLine=" + frame.getLineNumber());
        break;
    }
}
```

Đoạn này **không độc lập** và file/line không có stdout cố định. Nó minh họa cách tìm frame thuộc application thay vì phụ thuộc thao tác regex văn bản. Trong chẩn đoán thực tế, đừng mặc định mảng có frame thuộc ứng dụng; có thể không có metadata hoặc exception đến từ thư viện/runtime.

## 8. Ba cách log exception và sự khác biệt

Một exception có thể bị log sai dù được tạo với cause đầy đủ. Lựa chọn overload/cấu hình logger là rất quan trọng.

### 8.1 Ghi message so với ghi Throwable

Giả sử dùng một logging framework có API `error(message, throwable)`:

```java
// Minh họa API logger phổ biến, không phải chương trình Java độc lập.
logger.error("Checkout failed", error);
```

Với logger được cấu hình để hiển thị stack trace, lệnh này có thể giữ đầy đủ Throwable tree. Trái lại:

```java
// Chỉ chuyển Throwable thành chuỗi; không gửi đối tượng Throwable cho logger.
logger.error("Checkout failed: " + error);
```

Cách thứ hai thường chỉ chứa class/message qua `toString()` và **mất cause stack/suppressed** ở bản ghi, trừ khi code bổ sung chỗ khác. Cú pháp chính xác của logger phụ thuộc thư viện và overload; không suy ra rằng mọi framework sẽ in toàn bộ throwable ở mọi cấu hình.

Đối với SLF4J/Logback hoặc logger có placeholder, phải kiểm tra overload phù hợp và khả năng nhận `Throwable` cuối cùng làm exception, không để code formatter biến nó thành text. Trong các hệ log production có giới hạn dung lượng, kể cả cách gọi đúng vẫn có thể bị truncation hoặc sampling bởi appender/collector.

### 8.2 Không log cùng exception ở mọi tầng

Nếu repository log stack trace và throw; service log stack trace rồi throw; controller lại log cùng lỗi, một request có thể tạo 3 event lỗi gần giống nhau. Điều đó làm tăng chi phí, có thể dẫn đến alert count sai, che mờ lỗi chính và gây nhầm lẫn về số request bị ảnh hưởng.

Thường chọn một ranh giới quan sát thích hợp để ghi **stack đầy đủ một lần**, kèm request/correlation ID, route, operation, category và mức độ; những tầng thấp hơn có thể bổ sung ngữ cảnh bằng cách wrap cause, enrich structured context hoặc metric mà không log trùng mọi lần. Đây là hướng thiết kế, không phải quy tắc tuyệt đối: sự cố phân tán có thể cần log tại nhiều service, nhưng phải phân biệt mỗi **event** với một **incident/request**.

### 8.3 Structured logging và log nhiều dòng

Một Java stack trace thường có nhiều dòng. Khi gửi qua container stdout, agent, log shipper và dashboard, nó có thể bị tách thành nhiều event nếu parser chỉ dựa trên newline. Khi đó các dòng `Caused by:` hoặc `Suppressed:` có thể mất header timestamp/traceId, hoặc xuất hiện như “một lỗi khác”.

Ưu tiên logger xuất **một event có trường exception** và traceId/requestId nếu hệ thống hỗ trợ; nếu phải ingest text nhiều dòng, cấu hình multiline framing phù hợp với định dạng thực tế và giới hạn buffering. Không tự kết luận “có năm lỗi” chỉ vì thấy năm dòng chứa tên exception trong cùng một stack.

Các công cụ APM có thể cung cấp structured exception type/message/stack và có thể giữ cause hoặc suppressed riêng tùy SDK/collector. Cần xác nhận schema dữ liệu thực: không phải mọi nền tảng tự động bảo toàn đầy đủ Throwable tree.

## 9. Cách nhận ra vị trí lỗi có ý nghĩa trong trace dài

### 9.1 Quy trình tìm frame hành động được

1. **Xác định cùng một event:** timestamp, environment, service, instance/pod, thread, traceId/requestId. Nếu trace bị tách, khôi phục tất cả dòng cùng event trước khi đọc.
2. **Lấy header exception được log:** class/message, có phải lỗi nghiệp vụ hay wrapper của framework? Đừng gán nhãn root cause ngay.
3. **Lần theo cause chain:** từ outer xuống inner, ghi thông điệp và frame nổi bật ở từng tầng. Nếu cause cuối “connect timeout”, xác định client và endpoint tương ứng.
4. **Mở các nhánh suppressed:** đặc biệt khi dùng resource, DB transaction, file, stream, socket hoặc batch cleanup. Ghi rõ lỗi nào là primary và lỗi nào là lỗi phụ.
5. **Xem frame gần điểm throw/construct có ý nghĩa nhất:** có thể là frame trong application hoặc library; đối chiếu method, source line, artifact version, input và cấu hình.
6. **Phân biệt caller/callee:** stack thường in từ điểm exception về caller; frame gần cuối là entry path, không mặc nhiên là nơi phát sinh lỗi.
7. **Xác minh bằng telemetry:** query/SQL error, DB pool, downstream latency, network, request params đã được xử lý an toàn, deploy/config changes và reproduction.
8. **Kết luận theo mức chắc chắn:** “Trace cho thấy lỗi timeout ở database client” khác “nguyên nhân gốc là database quá tải” nếu chưa có bằng chứng về DB.

### 9.2 Tình huống: wrapper ở tầng async

`CompletionException` hoặc `ExecutionException` có thể xuất hiện ngoài cùng khi lấy kết quả của tác vụ bất đồng bộ. Ví dụ minh họa:

```text
java.util.concurrent.CompletionException: java.lang.IllegalArgumentException: bad payload
    at java.base/java.util.concurrent.CompletableFuture.encodeThrowable(...)
    ...
Caused by: java.lang.IllegalArgumentException: bad payload
    at com.example.PayloadValidator.validate(PayloadValidator.java:61)
    ...
```

Ngoài cùng nói **cách lỗi được chuyển qua Future**, còn cause đưa về application validator. Tuy nhiên, nếu triệu chứng là “task hoàn tất chậm” thì stack chỉ cho thấy exception và chưa đủ đo latency: cần thời gian queue, scheduling, thread pool và distributed tracing.

Tương tự, reflection có thể wrap trong `InvocationTargetException`; proxy transaction trong một wrapper khác; RPC có thể chuyển lỗi thành status riêng. Đừng cố dự đoán đầy đủ cause tree chỉ từ class ngoài cùng.

### 9.3 Tình huống: suppression của đóng tài nguyên che vấn đề thứ hai

Một request đọc file thất bại do dữ liệu không hợp lệ và phần đóng stream cũng ném exception. Trace có:

```text
java.lang.IllegalArgumentException: invalid payload
    at com.example.Parser.decode(Parser.java:70)
    ...
    Suppressed: java.io.IOException: close failed
        at com.example.PayloadStream.close(PayloadStream.java:121)
        ...
```

Nếu xử lý đầu vào sai là lỗi chính, fix parser; đồng thời cần xác minh resource vẫn được release/cleanup và việc close failure có gây rò rỉ FD hay mất dữ liệu không. **Không kết luận** chỉ vì suppressed nên close failure không quan trọng. Phải đánh giá ảnh hưởng thực tế.

### 9.4 Tình huống: có nhiều suppressed

Trong `try (A a = ...; B b = ...)`, cả hai `close()` thất bại khi body đã throw. Một primary có thể có **hai suppressed**. Thứ tự thông thường đi theo thao tác close B rồi A; mỗi suppressed có stack riêng. Khi viết báo cáo incident, nên liệt kê từng lỗi và tài nguyên liên quan thay vì chỉ ghi “2 suppressed exceptions”.

### 9.5 Tình huống: code source line không còn khớp

Trace nói `OrderService.java:142` nhưng branch hiện tại có method ở line 190. Trước khi “sửa line 142”, kiểm tra commit/build ID, JAR hoặc image digest của instance lỗi, runtime instrumentation/proxy và mapping source chính xác. Một bản ứng dụng khác có thể đã được deploy. Không dùng line number như bằng chứng thay thế cho binary identity.

### 9.6 Tình huống: exception không có stack

Một số lỗi xảy ra rất nhiều lần có thể bị JVM tối ưu đường ném, hoặc exception được tạo với stack trace không thể ghi; một số log system đặt giới hạn depth/length. Ví dụ HotSpot có cơ chế FastThrow liên quan `-XX:+OmitStackTraceInFastThrow` trong những điều kiện nhất định. Nếu stack trống/thiếu, đừng suy ra exception “không được ném” hoặc “không có caller”. Hãy kiểm tra cấu hình VM, loại throwable, log formatter và policy thu thập; cân nhắc capture có giới hạn hoặc test tái hiện.

## 10. Đọc bằng code thay vì regex log khi có đối tượng Throwable

Nếu bạn đang phát triển thư viện xử lý lỗi và **đã có** đối tượng `Throwable`, nên truy cập các field có cấu trúc qua API thay vì parse lại output của `printStackTrace()`. Một đoạn helper an toàn khi muốn lấy **cause chain** ngắn:

```java
// Đoạn minh họa có thể đặt trong một class tiện ích; cần import các kiểu java.util.
static void summarizeCauses(Throwable root) {
    java.util.Set<Throwable> visited =
            java.util.Collections.newSetFromMap(
                    new java.util.IdentityHashMap<>());
    Throwable current = root;
    int depth = 0;

    while (current != null && depth < 16 && visited.add(current)) {
        System.out.println(depth + ": " + current.getClass().getName());
        current = current.getCause();
        depth++;
    }
}
```

Đoạn này không tự động đi vào các suppressed, không phải một chương trình độc lập. Nó dùng **identity-based set** để chống vòng lặp bất thường, giới hạn depth để kiểm soát dữ liệu log. Khi muốn biểu diễn **cả đồ thị**, cần duyệt riêng `getCause()` và từng phần tử `getSuppressed()`, có cơ chế visited, giới hạn số nút/stack frames và chỉ hiển thị các thông tin không nhạy cảm.

Không nên tự viết một serializer đầy đủ Throwable graph chỉ để thay thế logger trong ứng dụng thông thường: dễ bỏ sót cause/suppressed, gây recursion không giới hạn, lộ dữ liệu trong message và khó kiểm soát dung lượng. Dùng logger/SDK được kiểm chứng hoặc schema chuẩn khi có thể.

### 10.1 Vì sao traversal cần giới hạn?

Các class có thể override `getCause()` và xử lý nguyên nhân theo cách riêng; suppressed có thể liên kết các throwable tạo thành cấu trúc phức tạp. Dù `Throwable` cấm tự suppression trực tiếp, đồ thị có thể có vòng tham chiếu qua nhiều object trong các thao tác tùy biến. Một collector không nên làm stack overflow khi xử lý lỗi của ứng dụng.

Giới hạn về depth và số frame chỉ để bảo vệ telemetry, **không phải bằng chứng rằng phần đã cắt không tồn tại**. Nếu phải cắt, ghi `truncated=true` hoặc một chỉ báo rõ ràng về số lượng bản ghi đã bỏ.

### 10.2 Những thuộc tính không thể suy ra chỉ từ Throwable

- **Request ID, tenant, endpoint, deployment:** không phải thuộc tính của `Throwable`, trừ khi ứng dụng đưa vào message/metadata.
- **Thời điểm exception xảy ra:** mặc định `Throwable` không có trường timestamp chuẩn; cần timestamp của event/log/trace và đồng hồ hệ thống.
- **Thread hiện tại khi log:** có thể khác thread ban đầu tạo exception, nhất là asynchronous pipeline.
- **Nguyên nhân tải hệ thống:** không tự chứa CPU, GC, queue length, DB saturation.
- **Thời lượng thao tác:** stack trace là snapshot, không thay thế profiler hoặc metrics.
- **Số lần lỗi xảy ra:** số dòng stack, số nested exception hoặc số `Caused by` không bằng số request lỗi.

## 11. Ranh giới bảo mật và chi phí khi lưu exception

Error message và stack trace có thể vô tình chứa **PII, đường dẫn nội bộ, token, SQL text, query params, payload, hostname, key hoặc resource identifier**. Ngay cả khi đối tượng Throwable không có field riêng cho secret, message được xây từ string input của người dùng có thể lộ dữ liệu.

**Khi thiết kế logging production:**

1. Dùng error category, stable error code và request/trace ID để liên kết bản ghi. Giới hạn giá trị input đưa vào message; không ghi nguyên credentials hoặc full body.
2. Phân quyền truy cập logs, áp dụng retention, redact thông tin nhạy cảm và kiểm soát nơi gửi stderr/structured event.
3. Giảm log trùng ở nhiều tầng; dùng sampling/rate limit cho lỗi lặp lại có volume rất lớn nhưng bảo đảm giữ bằng chứng đại diện cho incident nghiêm trọng.
4. Thận trọng với việc **gọi `printStackTrace()` liên tục** hoặc serialize Throwable sâu; tạo stack có chi phí CPU/allocation tùy VM và output nhiều dòng có chi phí I/O.
5. Không tắt stack trace của toàn bộ hệ thống chỉ để giảm dung lượng khi chưa đánh giá khả năng chẩn đoán; có thể cần ghi stack đầy đủ cho lỗi hiếm/nghiêm trọng và giảm tần suất cho lỗi nghiệp vụ dự kiến.
6. Khi tổng hợp thông tin nguyên nhân, ghi rõ nếu dữ liệu đã bị truncate hoặc error event được sampling. Thiếu frame vì log pipeline là **giới hạn dữ liệu**, không phải kết luận về code.

Trong một incident đang xử lý, bản ghi đầu ra cần đủ để nhóm kỹ thuật tìm đúng artifact/source, nhưng không nhất thiết công bố toàn bộ raw stack hoặc request object ở mọi ticket/chat.

## 12. Checklist đọc một exception trong incident

| Bước | Cần ghi | Mục đích |
| --- | --- | --- |
| 1. Gắn event | UTC timestamp, environment, service/instance, thread, traceId, app build | Không lẫn log của nhiều request/phiên triển khai |
| 2. Xác nhận đầy đủ | Trace có bị tách/truncate không? Có message và stack không? | Biết giới hạn bằng chứng |
| 3. Đọc outer exception | Class + message + vị trí wrapper | Biết tầng nào báo lỗi |
| 4. Duyệt cause | `Caused by` từng lớp, thông điệp, frame gần lỗi | Phân biệt wrapper và nguồn lỗi kỹ thuật |
| 5. Duyệt suppressed | `Suppressed` trên từng Throwable, tài nguyên đóng thất bại | Không bỏ qua lỗi phụ/cleanup |
| 6. Diễn giải frame | Method, class, source line/module, artifact identity | Xác định code ứng dụng/thư viện liên quan |
| 7. Xử lý nén | `... n more`, indent, enclosing trace | Không đọc sai shared frames thành lỗi mới |
| 8. Kiểm chứng | Input an toàn, metrics, traces, logs liên quan, tái hiện | Chuyển giả thuyết thành kết luận |
| 9. Hành động | Fix, test, dashboard/alert cải tiến, theo dõi hồi phục | Giảm khả năng tái phát và phát hiện nhanh |

Một mẫu kết luận tốt:

```text
Sự cố: checkout trả HTTP 500 lúc 08:15 UTC tại instance checkout-2.
Exception được log: IllegalStateException("Cannot complete checkout").
Cause chain: SQLException("Query failed") -> SocketTimeoutException("Read timed out").
Suppressed: IOException("Cannot close audit stream") trên cùng throwable chính.
Frame ứng dụng liên quan: CheckoutService.checkout(...), bản build xyz.
Bằng chứng thêm: DB client timeouts tăng cùng cửa sổ; đã xác nhận ở traceId cụ thể.
Chưa kết luận: timeout do DB load hay network; cần thêm DB/network telemetry.
```

Tên service, build và dữ liệu trong mẫu đều **giả định**. Kết luận cuối cùng cần dựa trên hệ thống thực tế. Trình bày riêng **đã xác nhận** và **còn giả thuyết** giúp người khác không nhầm một chuỗi cause với root cause của toàn hệ thống.

## 13. Sai lầm phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Exception cuối cùng trong log luôn là nguyên nhân gốc.” | Có thể là cause sâu nhất hoặc suppressed; cần xác định quan hệ, message, frame và bối cảnh. |
| “Dòng `at` cuối cùng là nơi bug xảy ra.” | Thường là caller/entry framework; hãy xem frame gần exception trong đúng tầng. |
| “`Caused by` là một lỗi khác xảy ra sau lỗi đầu.” | Thường là nguyên nhân được gắn vào wrapper; nó có thể xảy ra **trước** wrapper. |
| “`Suppressed` là nguyên nhân trực tiếp của primary.” | Suppressed là lỗi phụ bị giữ lại; thường do cleanup nhưng có thể liên quan vận hành. |
| “`Suppressed` có nghĩa lỗi đó không đáng sửa.” | Mức độ nghiêm trọng phải đánh giá theo tài nguyên và hậu quả thực tế. |
| “`... 3 more` nghĩa có 3 exception bị che.” | Đó là ba **stack frames trùng** ở cuối nhánh được nén, không phải ba Throwable. |
| “Mỗi `Caused by`/`Suppressed` là một request bị lỗi.” | Chúng có thể thuộc **một Throwable tree của một event**. |
| “`throw e` thêm dòng stack tại chỗ rethrow.” | Rethrow cùng throwable không tự cập nhật stack; wrapper mới có stack mới. |
| “`getMessage()` luôn chứa nguyên nhân và stack.” | Message chỉ là một chuỗi (có thể null), không thay `getCause()` và `getStackTrace()`. |
| “Đổi wrapper bằng `new Exception(e.toString())` vẫn giữ nguyên trace.” | Chỉ chép text; mất cause link nếu không truyền cause. |
| “Java trace luôn có source line chính xác.” | Có thể thiếu line info, dùng code generated, mapping khác hoặc binary không khớp. |
| “Một trace có thể cho biết toàn bộ async call graph.” | Thread/task boundaries có thể không hiển thị; cần correlation/tracing. |
| “Nếu logger không in cause, tức Throwable không có cause.” | Logger/encoder có thể chỉ in message hoặc cắt stack; kiểm tra đối tượng hoặc cấu hình. |
| “Mỗi lần in stack sẽ có cùng thứ tự với stdout.” | `printStackTrace()` mặc định dùng stderr; gộp nhiều stream không đảm bảo thứ tự. |

## 14. Tự kiểm tra

**Câu 1.** Một log có `IllegalStateException` ở ngoài và `Caused by: NumberFormatException` ở trong. Lỗi nào cần sửa?

**Trả lời:** cần xem cả hai. `NumberFormatException` chỉ điểm parse bị lỗi; `IllegalStateException` nói tầng nào chuyển thành thất bại của operation. Xác minh input/validation, frame application và quy tắc nghiệp vụ; không sửa chỉ theo tên class.

**Câu 2.** `try-with-resources` body ném A, `close()` ném B. Catch bên ngoài bắt exception nào?

**Trả lời:** thông thường catch nhận **A**, còn B ở `A.getSuppressed()`. Nếu body không ném mà close ném B, B là exception chính.

**Câu 3.** Có hai tài nguyên khai báo A rồi B. Khi thoát `try-with-resources`, tài nguyên nào đóng trước?

**Trả lời:** B trước A. Nếu cả hai close thất bại và đã có primary, có thể quan sát hai suppressed tương ứng theo thứ tự đóng; không nhầm thành cause chain.

**Câu 4.** Dòng `... 4 more` ở cause có nghĩa là bốn exception nữa không hiển thị?

**Trả lời:** không. Nó cho biết **bốn stack frames cuối trùng** với trace bao quanh theo cách `printStackTrace()` nén output. Muốn khôi phục phải đọc enclosing trace.

**Câu 5.** Tại sao cause stack chỉ ra method parser, còn wrapper stack chỉ ra service?

**Trả lời:** chúng là **hai Throwable khác nhau**, được tạo ở hai vị trí khác nhau. Wrapper giữ cause nhằm bảo toàn lỗi gốc qua ranh giới abstraction.

**Câu 6.** Một exception được log hai lần ở hai tầng và hai stack giống nhau. Có khẳng định hai request bị lỗi không?

**Trả lời:** không. Cần correlation ID, event count và request metrics; có thể cùng một lỗi được ghi trùng.

**Câu 7.** `getSuppressed()` rỗng có chứng minh không có lỗi cleanup?

**Trả lời:** không tuyệt đối. Có thể không có lỗi, nhưng cũng có thể app dùng `finally` thủ công làm mất lỗi, suppression bị tắt, code không thêm lỗi phụ hoặc log không có đầy đủ thông tin.

**Câu 8.** Log ghi `Unknown Source` hoặc không có stack frame. Có nên kết luận JVM đang chạy bản code không có lỗi?

**Trả lời:** không. Kiểm tra metadata build, logging/truncation policy, JVM optimization, exception type và các nguồn observability khác.

## 15. Ghi nhớ

- **Exception được log** cho biết kiểu lỗi ở tầng quan sát hiện tại.
- **Cause chain** giữ những exception được khai báo là nguyên nhân qua các tầng abstraction; tìm cause sâu giúp khoanh vùng nhưng **không tự chứng minh root cause**.
- **Suppressed exceptions** giữ lỗi phụ, nhất là khi đóng tài nguyên trong `try-with-resources`; chúng cần được xem xét, không bỏ qua.
- **Stack frame** cho biết đường gọi được ghi ở mỗi Throwable, thường tại lúc nó được tạo; frame đầu gần điểm ghi stack, frame cuối thường là caller ngoài cùng.
- **`... n more`** là cách nén phần đuôi stack trùng với nhánh bao quanh, **không phải thêm n lỗi**.
- **Phân tích đáng tin** cần đầy đủ event, traceId, phiên bản binary, telemetry và test tái hiện, đồng thời bảo vệ dữ liệu nhạy cảm trong logs.

### Tài liệu tham khảo

- [Oracle Java SE 21 — Throwable API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html): `getCause()`, `getSuppressed()`, `addSuppressed()`, `getStackTrace()`, `printStackTrace()`, cách in `Caused by`, `Suppressed`, `... n more`.
- [Oracle Java SE 21 — StackTraceElement API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StackTraceElement.html): class, method, file, line, module và native method.
- [Oracle — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html): semantics khi body và `close()` cùng ném exception. Tài liệu tutorial dùng ví dụ Java 7/8; các quy tắc suppression vẫn có giá trị với Java 17+.
- [Java Language Specification, Java SE 21 — `try` statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3): quy tắc đóng tài nguyên và lưu suppressed exceptions.
