# Dùng exhaustive switch cho command handler

**Chủ đề:** Java Core Pattern Matching — Case study command. Bài sử dụng **Java 21 trở lên**, khi **pattern matching for switch** (JEP 441) và **record patterns** (JEP 440) đã là tính năng chính thức. Trọng tâm là xây dựng một **command handler bao phủ mọi biến thể lệnh** bằng sealed hierarchy và switch expression, không để lệnh mới bị bỏ qua âm thầm.

## 1. Vấn đề: một handler phải biết xử lý những lệnh nào?

Trong ứng dụng, **command** diễn tả *yêu cầu làm một việc*, ví dụ mở một mục, đổi tên hoặc đóng mục. Đây là ý định cần được xác thực và có thể bị từ chối; nó khác với **event** diễn tả sự việc đã xảy ra.

Giả sử một ứng dụng giữ danh sách mục được quản lý theo mã định danh. Có ba lệnh:

- **Open(id, title):** tạo mục mới với mã và tên.
- **Rename(id, title):** đổi tên mục đã tồn tại.
- **Close(id):** đóng hoặc xóa mục khỏi bộ nhớ.

Một handler cần chọn đúng nhánh theo subtype, thực hiện quy tắc nghiệp vụ và trả về một kết quả rõ ràng. Khi miền command được kiểm soát, ta còn muốn trình biên dịch nhắc mọi nơi cần cập nhật nếu sau này thêm lệnh thứ tư, chẳng hạn **Archive(id)**.

Một chuỗi điều kiện cũ thường có dạng:

~~~java
// Minh họa trong ngữ cảnh có các kiểu Command, Open, Rename, Close.
if (command instanceof Open open) {
    return open(open.id(), open.title());
} else if (command instanceof Rename rename) {
    return rename(rename.id(), rename.title());
} else if (command instanceof Close close) {
    return close(close.id());
}
return new Rejected("unsupported");
~~~

Mã này có thể chạy đúng với ba lệnh hiện tại nhưng **không yêu cầu xét hết subtype**. Khi Archive được thêm, một handler cũ có thể vẫn biên dịch và trả unsupported, ngay cả khi nghiệp vụ yêu cầu xử lý Archive riêng.

**Mục tiêu của exhaustive switch không phải đơn thuần thay if-else bằng switch.** Mục tiêu là giúp compiler kiểm tra rằng handler đã đưa ra **quyết định cho mọi biến thể** mà kiểu command cho phép, đồng thời vẫn giữ null behavior, validation và side effects có chủ đích.

## 2. Thiết kế miền command đóng với sealed interface

Bắt đầu bằng mô hình:

~~~java
sealed interface Command permits Open, Rename, Close {}

record Open(long id, String title) implements Command {}
record Rename(long id, String title) implements Command {}
record Close(long id) implements Command {}
~~~

Đây là **đoạn khai báo minh họa**; mã chạy đầy đủ ở mục 5 bổ sung kiểm tra invariant trong constructor.

**sealed interface** cho biết những kiểu được phép trực tiếp triển khai Command. Ba record đều ngầm **final**, vì thế mỗi nhánh không có cây subtype mở rộng phía dưới. Compiler có đủ thông tin để phân tích tập biến thể khi gặp selector có kiểu tĩnh **Command**.

Các đặc điểm hữu ích:

1. Người tạo lệnh phải chọn một kiểu cụ thể, thay vì truyền String với tên lệnh tùy ý.
2. Thành phần của mỗi record có tên và kiểu tường minh; Open có id và title, còn Close chỉ cần id.
3. **Record pattern** trong switch vừa chọn biến thể vừa trích dữ liệu của biến thể ấy.
4. Khi thêm subtype vào tập permitted và biên dịch lại, các switch expression chưa bao phủ subtype mới sẽ báo lỗi thay vì âm thầm đi tới nhánh fallback.
5. Kiểu dữ liệu lệnh độc lập với mã gửi HTTP, CLI hay message queue: các tầng ngoài có thể chuyển yêu cầu thành Command trước khi gọi handler.

**Giới hạn quan trọng:** Sealed chỉ giới hạn subtype trực tiếp. Một nhánh được phép có thể khai báo **non-sealed**, từ đó cho phép các descendant chưa biết. Trong mô hình dùng record final ở đây, mỗi nhánh là một loại lệnh đóng; không có descendant mới dưới Open/Rename/Close.

## 3. Bảo vệ dữ liệu lệnh từ lúc tạo record

Một lệnh có id không dương hoặc title toàn khoảng trắng không mang ý nghĩa hợp lệ trong ví dụ. Có thể kiểm tra tại **compact constructor**, để handler không phải lặp cùng validation ở từng case:

~~~java
record Open(long id, String title) implements Command {
    Open {
        requireId(id);
        requireTitle(title);
    }
}
~~~

Hai helper **requireId** và **requireTitle** sẽ được định nghĩa trong class đầy đủ ở mục 5. Chúng thực hiện:

- **id > 0**;
- **title != null** và **!title.isBlank()**.

Record dùng các component dạng final nhưng **không tự kiểm tra invariant**. Compact constructor là lựa chọn để bảo đảm không tạo Open hợp lệ với id âm hoặc title blank. Tương tự, Rename cần id và title hợp lệ; Close chỉ cần id hợp lệ.

**Phân biệt hai loại lỗi:**

| Tình huống | Xảy ra khi nào? | Cách xử lý trong ví dụ |
| --- | --- | --- |
| **new Open(0, "Bad")** | Trước khi có object Command hợp lệ | Constructor ném IllegalArgumentException |
| **new Rename(25, "   ")** | Trước khi gọi handler | Constructor ném IllegalArgumentException |
| **Open(10, "Duplicate")** khi id 10 đã tồn tại | Trong nghiệp vụ xử lý lệnh | Handler trả Rejected("already exists 10") |
| **Close(99)** khi id 99 không có | Trong nghiệp vụ xử lý lệnh | Handler trả Rejected("not found 99") |
| **handle(null)** | Tại ranh giới handler | Handler trả Rejected("null command") |

Đặt validation tại constructor phù hợp khi invariant là đúng cho **mọi instance** của command. Nếu dữ liệu đầu vào chưa được parse hoặc còn thiếu từ bên ngoài, một lớp request/DTO riêng có thể dùng để báo lỗi trước khi dựng domain command.

## 4. Đừng bắt caller đoán thành công hay thất bại

Thay vì cho handler trả String hoặc null không rõ nghĩa, mô hình hóa kết quả thành hai biến thể:

~~~java
sealed interface Result permits Applied, Rejected {}

record Applied(String detail) implements Result {}
record Rejected(String reason) implements Result {}
~~~

- **Applied:** lệnh được chấp nhận và đã thực hiện trong ví dụ.
- **Rejected:** lệnh không thể hoàn tất theo một điều kiện đã xác định.

Consumer có thể render bằng một switch expression exhaustive thứ hai:

~~~java
static String render(Result result) {
    return switch (result) {
        case Applied(String detail) -> "OK: " + detail;
        case Rejected(String reason) -> "ERR: " + reason;
    };
}
~~~

Ở đây **Result** là sealed interface và cả Applied lẫn Rejected đều là record final. Không cần **default**; nếu sau này thêm loại kết quả mới như Pending, compiler sẽ nhắc cập nhật render sau khi biên dịch lại.

**Đây là hai trách nhiệm khác nhau:** handler chuyển Command thành Result; formatter chuyển Result thành văn bản hiển thị. Trong hệ thống production, có thể thay String detail/reason bằng mã lỗi, ID, dữ liệu kết quả hoặc một cấu trúc dành cho API. Không nên dựa vào việc phân tích chuỗi "ERR:" để xác định nghiệp vụ.

Nếu **render(null)** được gọi, switch không có case null và có thể ném NullPointerException; bản thiết kế này mặc định Result từ handler **không bao giờ null**. Nếu một API khác cho phép null result, cần hợp đồng riêng.

## 5. Ví dụ Java 21 hoàn chỉnh: handler exhaustive

Chương trình dùng **TreeMap** làm kho lưu tạm trong bộ nhớ để minh họa chuyển trạng thái. Không có database, transaction hay xử lý song song. Nó cho thấy cơ chế phân nhánh rõ hơn mà không đưa hạ tầng phức tạp vào ví dụ.

Lưu toàn bộ vào tệp **ExhaustiveCommandHandlerDemo.java**:

~~~java
import java.util.Map;
import java.util.TreeMap;

public class ExhaustiveCommandHandlerDemo {
    sealed interface Command permits Open, Rename, Close {}

    record Open(long id, String title) implements Command {
        Open {
            requireId(id);
            requireTitle(title);
        }
    }

    record Rename(long id, String title) implements Command {
        Rename {
            requireId(id);
            requireTitle(title);
        }
    }

    record Close(long id) implements Command {
        Close {
            requireId(id);
        }
    }

    sealed interface Result permits Applied, Rejected {}
    record Applied(String detail) implements Result {}
    record Rejected(String reason) implements Result {}

    private static void requireId(long id) {
        if (id <= 0) throw new IllegalArgumentException("id");
    }

    private static void requireTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title");
        }
    }

    private final Map<Long, String> titles = new TreeMap<>();

    Result handle(Command command) {
        return switch (command) {
            case Open(long id, String title) -> open(id, title);
            case Rename(long id, String title) -> rename(id, title);
            case Close(long id) -> close(id);
            case null -> new Rejected("null command");
        };
    }

    private Result open(long id, String title) {
        if (titles.putIfAbsent(id, title) != null) {
            return new Rejected("already exists " + id);
        }
        return new Applied("opened " + id + " " + title);
    }

    private Result rename(long id, String title) {
        if (!titles.containsKey(id)) {
            return new Rejected("not found " + id);
        }
        titles.put(id, title);
        return new Applied("renamed " + id + " " + title);
    }

    private Result close(long id) {
        if (titles.remove(id) == null) {
            return new Rejected("not found " + id);
        }
        return new Applied("closed " + id);
    }

    static String render(Result result) {
        return switch (result) {
            case Applied(String detail) -> "OK: " + detail;
            case Rejected(String reason) -> "ERR: " + reason;
        };
    }

    public static void main(String[] args) {
        var handler = new ExhaustiveCommandHandlerDemo();

        Command[] commands = {
            new Open(10, "Atlas"),
            new Rename(10, "Orion"),
            new Open(10, "Duplicate"),
            new Close(99),
            new Close(10),
            new Rename(10, "Nova"),
            new Open(20, "Solar"),
            new Rename(20, "Lunar"),
            null
        };

        for (Command command : commands) {
            System.out.println(render(handler.handle(command)));
        }

        try {
            new Open(0, "Invalid");
        } catch (IllegalArgumentException ex) {
            System.out.println("INVALID: " + ex.getMessage());
        }

        try {
            new Rename(25, "   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("INVALID: " + ex.getMessage());
        }

        System.out.println("STATE: " + handler.titles);
    }
}
~~~

### Biên dịch và chạy

Dùng JDK 21 hoặc mới hơn:

~~~bash
javac ExhaustiveCommandHandlerDemo.java
java ExhaustiveCommandHandlerDemo
~~~

**Đầu ra chính xác:**

~~~text
OK: opened 10 Atlas
OK: renamed 10 Orion
ERR: already exists 10
ERR: not found 99
OK: closed 10
ERR: not found 10
OK: opened 20 Solar
OK: renamed 20 Lunar
ERR: null command
INVALID: id
INVALID: title
STATE: {20=Lunar}
~~~

### Đọc từng nhóm kết quả

1. **Open(10, "Atlas")** thành công và tạo mục 10.
2. **Rename(10, "Orion")** đổi tên mục 10 thành Orion.
3. **Open(10, "Duplicate")** bị từ chối vì id 10 đã tồn tại; Map giữ giá trị đang có.
4. **Close(99)** không tìm thấy mục và trả Rejected.
5. **Close(10)** loại bỏ mục 10, thành công.
6. **Rename(10, "Nova")** bị từ chối vì mục đã đóng.
7. **Open(20, "Solar")** rồi **Rename(20, "Lunar")** tạo và đổi tên mục 20.
8. **null command** được xử lý bởi case null thành Result loại Rejected thay vì NPE ngầm.
9. Hai phép tạo command không hợp lệ ném exception từ constructor, được main bắt và in **INVALID: id/title**.
10. Map còn đúng mục **20=Lunar**, nên **STATE: {20=Lunar}**.

**Kết quả này là kiểm tra hành vi, không phải benchmark.** Các dòng được tạo từ trình tự đầu vào xác định; vì TreeMap được dùng nên biểu diễn các key có thứ tự, và chỉ còn một key ở ví dụ. Trong hệ thống thật cần kiểm thử đồng thời, transaction và tính nhất quán ở tầng lưu trữ.

## 6. Vì sao switch handler được coi là exhaustive?

Phần cốt lõi là:

~~~java
Result handle(Command command) {
    return switch (command) {
        case Open(long id, String title) -> open(id, title);
        case Rename(long id, String title) -> rename(id, title);
        case Close(long id) -> close(id);
        case null -> new Rejected("null command");
    };
}
~~~

Phân tích theo từng yếu tố:

- **Selector** có kiểu tĩnh Command.
- **Permits** của Command gồm đúng Open, Rename, Close.
- Cả ba subtype trực tiếp đều là record final, không có nhánh mở rộng dưới chúng.
- Mỗi **record pattern** nhận toàn bộ instance của record tương ứng; các component kiểu long/String được ràng buộc qua pattern, không có guard hạn chế giá trị.
- **case null** quy định hành vi khi chính selector không có lệnh; nó không thay thế case cho subtype.
- Không có **default** nên compiler có thể phát hiện khi thêm subtype mà chưa cập nhật handler.

Một switch expression bắt buộc phải **exhaustive**. Trong ví dụ, khi selector có giá trị Command khác null, nó phải là một trong ba biến thể permitted. Record patterns bao phủ ba biến thể đó, và case null thêm hợp đồng với null selector. Từng nhánh trả về một Result, vì thế toàn bộ expression có kiểu Result.

**Exhaustive không đồng nghĩa lệnh luôn thành công.** Một case có thể trả **Rejected** hoặc ném exception. Exhaustiveness chỉ bảo đảm có nhánh phù hợp về kiểu và pattern; tính đúng nghiệp vụ còn do hàm open/rename/close và test xác nhận.

## 7. Khi thêm subtype mới, compiler bảo vệ điều gì?

Giả sử hệ thống sau đó bổ sung lệnh Archive. Thay đổi thiết kế ở phía model:

~~~java
// Minh họa phiên bản mở rộng, không ghép vào file demo nguyên trạng.
sealed interface Command permits Open, Rename, Close, Archive {}

record Archive(long id) implements Command {}
~~~

Khi biên dịch lại handler cũ, compiler thấy **Archive** là một biến thể permitted nhưng không có case xử lý. Một switch expression không default như trên sẽ báo lỗi dạng:

~~~text
the switch expression does not cover all possible input values
~~~

Để sửa đúng, đừng vội thêm default. Hãy quyết định ý nghĩa Archive rồi cập nhật handler:

~~~java
// Đoạn minh họa cần có phương thức archive(id) trong handler mở rộng.
case Archive(long id) -> archive(id);
~~~

Sau đó thêm test về Archive, kể cả trường hợp id không tồn tại, trạng thái không thể archive và các side effects liên quan. Có thể phải cập nhật thêm parser/mapper, phân quyền, logging, API contract hoặc event phát ra; switch chỉ nhắc một phần những nơi cần xử lý.

**Cơ chế compile-time có điều kiện:** Nó hoạt động khi biên dịch lại với định nghĩa hierarchy mới. Nếu những binary đã build trước đó được triển khai lệch phiên bản với library mới, một switch từng exhaustive có thể gặp dạng runtime không có nhánh tương ứng và ném **MatchException**. Vì vậy cần build/test/triển khai tương thích các module phụ thuộc.

### Tại sao không dùng default để tránh lỗi?

~~~java
// Anti-pattern nếu nghiệp vụ yêu cầu handler phải xét mọi command.
return switch (command) {
    case Open(var id, var title) -> open(id, title);
    case Rename(var id, var title) -> rename(id, title);
    case Close(var id) -> close(id);
    case null -> new Rejected("null command");
    default -> new Rejected("unsupported");
};
~~~

Khi Archive xuất hiện, nó có thể bị đưa vào unsupported mà không buộc người phát triển thiết kế cách xử lý cụ thể. Điều đó không phải lúc nào cũng sai: với một kiểu selector thực sự **mở** và một hợp đồng cho phép từ chối mọi loại chưa hỗ trợ, fallback là cần thiết. Nhưng với **sealed command model có tập lệnh được kiểm soát**, bỏ default thường giúp bắt thiếu sót sớm hơn.

Nếu vẫn muốn reject command không hợp lệ từ bên ngoài, hãy reject ở **boundary parse/validation**, không biến tất cả subtype mới trong domain thành “unsupported” mặc định.

## 8. Guard when có thể làm handler không exhaustive

Giả sử chỉ cho phép Rename với title có một điều kiện nhất định:

~~~java
// Đây là một ví dụ âm tính: chỉ một phần Rename được xử lý.
return switch (command) {
    case Open(var id, var title) -> open(id, title);
    case Rename(long id, String title) when title.startsWith("A") ->
            rename(id, title);
    case Close(var id) -> close(id);
    case null -> new Rejected("null command");
};
~~~

Với một Rename có title không bắt đầu bằng A, guard false; không có nhánh khác cho subtype Rename, nên switch expression có thể bị compiler đánh giá **không exhaustive**. Thêm một nhánh không guard dành riêng cho phần còn lại:

~~~java
case Rename(var id, var title) ->
        new Rejected("rename policy not satisfied");
~~~

Nhánh Rename có guard phải xuất hiện **trước** nhánh Rename tổng quát. Đặt nhánh rộng lên trước sẽ khiến nhánh sau bị che (**dominated**) và compiler có thể báo lỗi.

**Giới hạn của exhaustiveness:** Compiler không nhất thiết suy ra toàn bộ các điều kiện nghiệp vụ như x > 0 và x <= 0 để chứng minh coverage. Guard là một phép kiểm tra runtime; khi guard false, switch thử các case phù hợp tiếp theo; khi guard ném exception, nó không được hiểu là false.

Với các điều kiện phức tạp, có thể giữ switch chỉ làm dispatch và kiểm tra trong phương thức xử lý tương ứng. Ví dụ **case Rename(var id, var title) -> rename(id, title)** vừa dễ đọc vừa giúp handler không lẫn các quy tắc nghiệp vụ dài trong nhãn case.

## 9. Null command và component null: không nhầm hai lỗi

Ở demo, **case null** xử lý khi toàn bộ command là null:

~~~java
case null -> new Rejected("null command");
~~~

Nhưng nó **không xử lý title null** của một object Open hoặc Rename. Việc đó đã do compact constructor đảm nhiệm:

~~~java
record Rename(long id, String title) implements Command {
    Rename {
        requireId(id);
        requireTitle(title);
    }
}
~~~

Vì vậy:

- **handler.handle(null)** trả Rejected theo hợp đồng.
- **new Rename(1, null)** ném IllegalArgumentException("title") **trước** khi handler được gọi.
- **new Rename(1, " ")** cũng bị constructor từ chối.
- **new Close(1)** không có component title, nên không cần kiểm tra title.

Nếu hệ thống chọn mô hình command cho phép component null, record pattern vẫn có thể match record và ràng buộc biến title null ở một nhánh không guard. Khi đó phải kiểm tra title trong body hoặc một tầng validation, không được suy ra **case Rename(var id, var title)** bảo đảm title nonnull.

Một lựa chọn API khác là **Objects.requireNonNull(command, "command")** trước switch, làm null selector ném NullPointerException. Lựa chọn này hợp lý nếu null là lỗi lập trình. Tuy nhiên, đó là **hợp đồng khác** với demo trả Rejected; khi đổi chính sách phải sửa Javadoc và test.

**Không được mặc nhiên coi null command là một lệnh hợp lệ:** việc chọn trả Rejected ở đây chỉ nhằm minh họa một API xử lý lỗi có cấu trúc.

## 10. Side effects trong handler: switch không thay thế transaction

Demo dùng một Map để mô phỏng thay đổi trạng thái. Chọn case đúng chỉ là bước đầu của việc xử lý command thực sự.

### 10.1. Dispatch tách khỏi nghiệp vụ

Một case handler thường rõ hơn khi chỉ gọi một method được đặt tên:

~~~java
case Open(long id, String title) -> open(id, title);
case Rename(long id, String title) -> rename(id, title);
case Close(long id) -> close(id);
~~~

Các phương thức con có thể dùng repository, kiểm tra quyền, xác nhận trạng thái và trả Result. Cách này tránh một switch chứa hàng chục dòng I/O và validation, đồng thời giữ chức năng **chọn đúng subtype** có thể review được.

### 10.2. Trạng thái của demo không thread-safe

**TreeMap** không phải cấu trúc để nhiều thread cùng thay đổi không đồng bộ. Phép kiểm tra rồi cập nhật trong rename cũng không tự trở thành thao tác nguyên tử. Nếu nhiều command được xử lý song song, cần một cơ chế kiểm soát đồng thời phù hợp: khóa, transaction, optimistic locking hoặc kho dữ liệu có thao tác điều kiện nguyên tử.

Không nên thay TreeMap bằng ConcurrentHashMap rồi mặc nhiên tin toàn bộ chuỗi **containsKey → put** đã nguyên tử; tính nguyên tử của cả một quy trình nghiệp vụ cần được xem xét riêng.

### 10.3. Lặp command và tính idempotent

Message queue có thể giao lại command; API có thể bị client retry khi timeout. Nếu handler thực hiện side effect như gửi mail hoặc thu tiền rồi timeout, một lần retry có thể lặp tác dụng phụ. Tùy domain cần **idempotency key**, transaction/outbox, trạng thái xử lý hoặc cơ chế deduplication.

Trong demo, Open trùng id bị Rejected, nhưng đó **không phải** là bảo đảm idempotency hoàn chỉnh cho mọi nghiệp vụ. Command trùng cần được thiết kế theo yêu cầu hệ thống; kết quả của lần retry có thể cần giống kết quả lần đầu, thay vì trả lỗi mới.

### 10.4. Ranh giới lỗi có chủ đích

Một command có thể bị từ chối vì dữ liệu hoặc trạng thái nghiệp vụ; cũng có thể thất bại vì database, network hoặc bug. Không nên catch toàn bộ Exception rồi trả Applied hoặc nuốt lỗi:

~~~java
// Anti-pattern: biến lỗi thực thi thành thành công giả.
try {
    performOperation();
    return new Applied("done");
} catch (Exception ex) {
    return new Applied("done");
}
~~~

Nếu cần mô hình hóa lỗi hạ tầng bằng kiểu Result riêng, hãy xác định rõ loại và nơi retry. Một hệ thống phức tạp có thể dùng **Applied**, **Rejected** và **Failed** (hoặc phân lớp errors) với exhaustive switch ở consumer.

## 11. Khi nào dùng switch expression, statement hay polymorphism?

### Switch expression

Phù hợp khi handler **chọn một kết quả** theo command subtype và các nhánh có kiểu trả về thống nhất:

~~~java
return switch (command) {
    case Open(var id, var title) -> open(id, title);
    case Rename(var id, var title) -> rename(id, title);
    case Close(var id) -> close(id);
    case null -> new Rejected("null command");
};
~~~

Các case đều cho Result; nếu case cần nhiều lệnh, có thể dùng block và **yield**:

~~~java
// Minh họa: có audit(...) và open(...) do ứng dụng định nghĩa.
case Open(var id, var title) -> {
    audit("open", id);
    yield open(id, title);
}
~~~

Một nhánh có thể ném exception thay vì yield. Nhưng không nên dồn nhiều tác vụ có side effect vào switch expression nếu phải quản lý transaction hoặc rollback; hãy tách phương thức chuyên trách.

### Switch statement

Một switch statement thường phù hợp khi chủ yếu **thực thi hành động** và không cần tạo giá trị trực tiếp. Với **pattern switch** trên Java 21, switch statement cũng chịu các quy tắc exhaustiveness tương ứng; đừng nhầm với switch statement truyền thống chỉ dùng các nhãn hằng số, vốn có thể thiếu default.

### Polymorphism

Nếu mỗi command tự có hành vi ổn định và thao tác tự nhiên nằm ngay trong subtype, thiết kế polymorphic có thể phù hợp:

~~~java
// Phác thảo một phương án thiết kế khác, không ghép vào demo.
interface ExecutableCommand {
    Result execute(Context context);
}
~~~

Nhưng nếu muốn giữ DTO/command records độc lập với cơ sở dữ liệu, service và hạ tầng, một **handler bên ngoài dùng exhaustive switch** thường rõ ràng hơn. Một số hệ thống dùng registry/map từ class tới handler, nhưng cách đó không tự có bảo đảm exhaustiveness tĩnh như switch trên sealed hierarchy và cần cơ chế kiểm tra đăng ký riêng.

| Tiêu chí | Sealed + exhaustive switch | Polymorphism/registry |
| --- | --- | --- |
| Miền command đóng và được kiểm soát | Rất phù hợp | Có thể dùng |
| Muốn compiler nhắc khi thêm subtype | Lợi thế rõ rệt | Cần interface contract hoặc kiểm tra đăng ký |
| Nhiều consumer đọc cùng command | Có thể viết switch riêng theo trách nhiệm | Tùy cách tổ chức handler |
| Plugin thêm command động lúc runtime | Hạn chế do miền sealed | Registry hoặc cơ chế extension có thể hợp lý |
| Mỗi command gắn chặt với một hành vi domain | Có thể dẫn tới switch dài | Polymorphism có thể rõ hơn |
| Tách command data khỏi service/hạ tầng | Thuận tiện | Cần thiết kế interface/phụ thuộc cẩn thận |

Không có giải pháp duy nhất đúng cho mọi ứng dụng. Hãy ưu tiên một ranh giới dispatch rõ ràng, khả năng mở rộng thực tế và cách xử lý lỗi có thể kiểm chứng.

## 12. Kiểm thử handler: không chỉ xác nhận code biên dịch

Compiler giúp phát hiện **thiếu nhánh**, nhưng không chứng minh nghiệp vụ của từng nhánh đúng. Một ma trận test cho demo:

| Lệnh / tình huống | Kỳ vọng | Điểm được kiểm tra |
| --- | --- | --- |
| Open mới | Applied; mục được tạo | Chọn đúng subtype và tạo trạng thái |
| Rename mục có sẵn | Applied; title được đổi | Đúng id, không tạo bản ghi mới |
| Open id đã tồn tại | Rejected; giữ giá trị cũ | Không ghi đè dữ liệu |
| Close id không tồn tại | Rejected | Không giả thành công |
| Close id có sẵn | Applied; mục bị xóa | Side effect đúng |
| Rename sau khi Close | Rejected | Xác thực trạng thái trước cập nhật |
| handle(null) | Rejected("null command") | Hợp đồng null selector |
| Open id không hợp lệ | IllegalArgumentException từ constructor | Invariant trước khi dispatch |
| Rename title blank/null | IllegalArgumentException từ constructor | Component null/blank |
| Thêm subtype mới vào permits | Lỗi exhaustiveness ở switch thiếu case | Compile-time regression |
| Có lệnh với guard false | Phải có case phù hợp cho phần còn lại | Không bỏ sót pattern |

### Test đơn giản không dùng framework

Đặt các câu lệnh minh họa sau trong phạm vi class demo (hoặc một test có quyền truy cập phù hợp):

~~~java
var handler = new ExhaustiveCommandHandlerDemo();

Result first = handler.handle(new Open(1, "A"));
if (!(first instanceof Applied)) {
    throw new AssertionError("Open should succeed");
}

Result duplicate = handler.handle(new Open(1, "B"));
if (!(duplicate instanceof Rejected)) {
    throw new AssertionError("Duplicate id should fail");
}

Result missing = handler.handle(null);
if (!(missing instanceof Rejected)) {
    throw new AssertionError("Null command contract");
}
~~~

Đây là **đoạn kiểm thử bổ sung**, không phải một chương trình Java độc lập bên ngoài class. Với JUnit, có thể dùng **assertInstanceOf**, **assertEquals**, **assertThrows** và kiểm tra trạng thái sau mỗi lệnh. Trong dự án lớn, test cần xác nhận cả transaction boundary, quyền truy cập và tác dụng phụ như event hoặc thông báo.

### Test compile-time khi thêm subtype

Một cách review hữu ích là tạo subtype mới trên một nhánh phát triển, sửa danh sách **permits** rồi biên dịch toàn bộ module liên quan. Khi handler chưa có case tương ứng và không có default rộng, trình biên dịch sẽ báo nơi cần cập nhật. Sau đó thêm case đúng nghiệp vụ và regression test, chứ không chỉ chèn default cho qua build.

Lưu ý compiler nhìn **kiểu tĩnh**. Nếu bạn đổi tham số thành Object hoặc một interface mở không có sealed coverage, không thể kỳ vọng nó biết toàn bộ các loại command của ứng dụng từ tên class.

## 13. Lỗi thường gặp khi xây dựng command handler

**Sai 1 — Luôn dùng default -> unsupported.** Với sealed hierarchy có tập subtype đóng, điều đó khiến compiler không nhắc khi lệnh mới được thêm. Nếu mục tiêu là review từng command, bỏ default và liệt kê đầy đủ.

**Sai 2 — Chỉ có một case có guard cho mỗi subtype.** Guard có thể false, làm switch expression thiếu nhánh. Thêm nhánh cùng subtype không guard hoặc chuyển validation vào phương thức xử lý.

**Sai 3 — Đặt case Command c trước case Open.** Type pattern tổng quát có thể che các pattern cụ thể và gây lỗi dominance. Đặt case cụ thể trước khi thực sự cần fallback rộng.

**Sai 4 — Coi exhaustive là validation.** Switch có đủ case nhưng một command vẫn có thể mang id không hợp lệ, quyền không đủ hoặc trạng thái không cho phép thao tác. Tính đúng nghiệp vụ cần invariant và kiểm thử.

**Sai 5 — Quên null selector.** Chuỗi instanceof với null thường rơi vào else, còn pattern switch có quy tắc null riêng. Chọn case null hoặc từ chối bằng Objects.requireNonNull theo hợp đồng.

**Sai 6 — Bỏ qua component null.** Record pattern không tự bảo đảm component String khác null nếu constructor cho phép. Đừng gọi method trên biến pattern mà không có invariant hoặc kiểm tra.

**Sai 7 — Nhầm command với event.** Command có thể bị từ chối và có side effect; event là sự việc đã xảy ra. Không nên biến việc nhận một command thành bảo đảm rằng một event đã phát sinh.

**Sai 8 — Đặt toàn bộ I/O, transaction, retry và logging vào case.** Dispatch sẽ khó review, lỗi khó test và side effects khó quản lý. Dùng phương thức/service riêng.

**Sai 9 — Thấy Map trong ví dụ và mặc định thread-safe.** TreeMap không được dùng đồng thời mà không có đồng bộ; nhiều hành động read-then-write không nguyên tử.

**Sai 10 — Chỉ dựa vào compiler để xác nhận thay đổi domain.** Nó phát hiện thiếu subtype ở các switch được biên dịch lại, không biết các tác vụ nội bộ, permission hay response JSON có đúng không.

## 14. Checklist thiết kế và code review

- [ ] Command hierarchy có thật sự đóng và phù hợp để khai báo **sealed** không?
- [ ] Mỗi command được biểu diễn bằng một kiểu có component rõ ràng?
- [ ] Invariant chung của command được kiểm tra khi tạo object?
- [ ] Handler có selector kiểu tĩnh **Command**, không bị làm rộng thành Object ngoài ý muốn?
- [ ] Các case của **Open, Rename, Close** đều hiện diện và không bị dominance?
- [ ] Switch expression có **không dùng default** khi cần compiler nhắc subtype mới?
- [ ] Nếu dùng **when**, có case dự phòng cho guard false?
- [ ] Null command và null component có quy tắc tường minh?
- [ ] Handler trả Result phù hợp, không trộn lỗi nghiệp vụ với ngoại lệ hạ tầng?
- [ ] Có test trạng thái trước/sau, lệnh trùng, id không tồn tại và lệnh sai dữ liệu?
- [ ] Side effects, concurrent update, retry và idempotency được giải quyết ở tầng phù hợp?
- [ ] Khi thêm command mới, toàn bộ switch và consumer được biên dịch và kiểm thử lại?

**Kết luận:** **Exhaustive switch cho handler** là cách kết hợp sức mạnh của **sealed interface**, **record patterns** và **switch expression** để diễn đạt tập lệnh được hỗ trợ một cách rõ ràng. Compiler giúp phát hiện **thiếu xử lý khi subtype mới xuất hiện**; các method chuyên trách giữ nghiệp vụ gọn; Result tường minh giúp caller phân biệt thành công và từ chối. Nhưng exhaustiveness không thay validation, transaction hay test: một handler đáng tin cậy cần cả **coverage ở compile time** lẫn **hành vi đúng ở runtime**.