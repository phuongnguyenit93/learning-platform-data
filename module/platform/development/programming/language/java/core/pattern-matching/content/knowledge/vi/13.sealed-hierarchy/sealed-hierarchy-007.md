# Mở rộng sealed hierarchy mà không phá caller trong Java

## 1. Vấn đề: hierarchy đóng nhưng yêu cầu nghiệp vụ vẫn thay đổi

**Sealed class** và **sealed interface** giới hạn các kiểu được phép kế thừa hoặc triển khai trực tiếp thông qua danh sách **permits**. Tính năng này được chuẩn hóa từ **Java 17** và rất hữu ích khi mô hình dữ liệu chỉ có một số trạng thái được biết trước.

Ví dụ ban đầu:

~~~java
sealed interface Event permits Created, Deleted {}

record Created(String id) implements Event {}
record Deleted(String id) implements Event {}
~~~

Một caller sử dụng **pattern matching for switch** của **Java 21** có thể viết:

~~~java
static String render(Event event) {
    return switch (event) {
        case Created c -> "created:" + c.id();
        case Deleted d -> "deleted:" + d.id();
    };
}
~~~

Các đoạn trên là những khai báo minh họa cần đặt trong tệp/class hợp lệ; không phải chương trình độc lập. Vì hai record là toàn bộ subtype trực tiếp được phép của **Event**, compiler có thể chứng minh biểu thức **switch** đã bao phủ tất cả đối tượng Event khác **null**, không cần **default**.

Bây giờ hệ thống cần thêm trạng thái **Archived**. Nếu sửa model thành:

~~~java
// Phiên bản mới, THAY THẾ khai báo Event và các subtype ở trên.
sealed interface Event permits Created, Deleted, Archived {}

record Created(String id) implements Event {}
record Deleted(String id) implements Event {}
record Archived(String id) implements Event {}
~~~

thì phương thức **render** cũ, nếu **biên dịch lại** với định nghĩa Event mới, không còn exhaustive: thiếu **case Archived**. Với các caller đã biên dịch trước khi thêm subtype, tình huống cũng có rủi ro riêng khi nhận một instance Archived lúc chạy.

Vì thế, “mở rộng mà không phá caller” cần được xác định bằng một **hợp đồng tiến hóa API**: caller sẽ phải xử lý mọi subtype mới hay được phép dùng xử lý dự phòng? Có cần duy trì tương thích mã nguồn, tương thích class file hay hành vi nghiệp vụ trong quá trình nâng cấp nhiều phiên bản?

## 2. Ba mức tương thích phải phân biệt

| Mức tương thích | Câu hỏi cần trả lời | Nguy cơ khi thêm permitted subtype |
| --- | --- | --- |
| **Source compatibility** | Caller cũ có biên dịch lại với thư viện mới không? | Switch exhaustive không default có thể thiếu case và bị compiler từ chối |
| **Binary compatibility** | Class file caller đã biên dịch trước đây có còn liên kết với thư viện mới không? | Việc **thêm permitted direct subtype** là thay đổi tương thích nhị phân theo JLS; không tự nó gây lỗi liên kết |
| **Behavioral / migration compatibility** | Caller cũ có xử lý được object mới trong lúc chạy không? | Switch không có nhãn áp dụng có thể ném **MatchException** trên Java 21, hoặc vào fallback không đúng nghiệp vụ |

Theo **Java Language Specification 21**, thêm một permitted direct subclass/subinterface vào sealed hierarchy nhìn chung **binary compatible**, vì các binary đã biên dịch vẫn có thể liên kết. Nhưng nếu một **switch** đã được biên dịch theo danh sách subtype cũ gặp một instance subtype mới và không nhãn nào áp dụng, nó có thể ném **java.lang.MatchException**. Đặc tả gọi đây là vấn đề **migration compatibility**, không phải bằng chứng thay đổi sealed type đã phá binary compatibility.

Điều đó dẫn tới hai nguyên tắc:

1. **Build xanh trên thư viện mới không đồng nghĩa runtime an toàn** nếu một số consumer vẫn chạy binary cũ hoặc nhận subtype mới qua đường truyền dữ liệu.
2. **Không phá binary** cũng không có nghĩa **không phá source**: biên dịch lại một caller Java 21 có switch không default có thể báo lỗi chưa exhaustive, và đó là tín hiệu hữu ích để cập nhật nghiệp vụ.

**Lưu ý:** không phải mọi thay đổi của sealed hierarchy đều an toàn. *Bỏ* subtype khỏi danh sách permitted, thay đổi modifiers hoặc sửa hợp đồng method có quy tắc tương thích khác; bài này tập trung vào **mở rộng** và các chiến lược hạn chế tác động.

## 3. Chiến lược A — dành sẵn một nhánh mở rộng ổn định

Nếu biết hệ thống sẽ bổ sung biến thể mới trong tương lai, có thể thiết kế root sealed với một nhánh chuyên cho mở rộng:

~~~java
sealed interface Message permits Created, Deleted, Extension {}

record Created(String id) implements Message {}
record Deleted(String id) implements Message {}

non-sealed interface Extension extends Message {}
~~~

Ở đây:

- **Message** vẫn là sealed: người dùng không thể tùy ý tạo một *direct subtype* mới của Message ngoài danh sách permitted.
- **Extension** là một permitted direct subinterface nhưng được khai báo **non-sealed**; các lớp phù hợp có thể triển khai Extension mà **không cần sửa danh sách permits của Message**.
- Caller có thể xử lý **case Extension extension** như một nhánh dự phòng có kiểu tĩnh rõ ràng.
- Sau này thêm **record Paused(...) implements Extension** hoặc **record Resumed(...) implements Extension** mà không thêm trực tiếp vào permits của Message.

Đây là cách tạo một **vùng mở rộng** trong một mô hình phần lớn đóng. Nó đánh đổi một phần khả năng kiểm tra exhaustive ở nhánh Extension: compiler biết các instance Extension đều khớp **case Extension**, nhưng **không bắt buộc caller liệt kê từng implementation tương lai của Extension**. Hợp đồng xử lý Extension vì vậy phải chủ động định nghĩa hành vi cho cả những loại chưa biết.

**Điều kiện để giữ ổn định:** giữ nguyên các nhánh trực tiếp của Message và đừng tự thêm một subtype *trực tiếp* mới ngoài **Created**, **Deleted**, **Extension**. Nếu vẫn thêm một direct subtype mới vào permits, các switch exhaustive cũ không có case cho subtype đó có thể gặp cùng vấn đề như trước.

### Ví dụ Java 21 đầy đủ, chạy được

Tạo tệp **SealedCompatibilityDemo.java**:

~~~java
public class SealedCompatibilityDemo {
    sealed interface Message permits Created, Deleted, Extension {}

    record Created(String id) implements Message {}
    record Deleted(String id) implements Message {}

    non-sealed interface Extension extends Message {}

    record Paused(String id, int seconds) implements Extension {}
    record Resumed(String id) implements Extension {}

    static String handle(Message message) {
        return switch (message) {
            case null -> "missing";
            case Created c -> "created:" + c.id();
            case Deleted d -> "deleted:" + d.id();
            case Extension extension -> handleExtension(extension);
        };
    }

    static String handleExtension(Extension extension) {
        if (extension instanceof Paused paused) {
            return "paused:" + paused.id() + ":" + paused.seconds();
        }
        return "extension:" + extension.getClass().getSimpleName();
    }

    static String handleWithFallback(Message message) {
        return switch (message) {
            case null -> "missing";
            case Created c -> "created";
            case Deleted d -> "deleted";
            default -> "unknown-message";
        };
    }

    public static void main(String[] args) {
        Message[] examples = {
                new Created("A"),
                new Deleted("B"),
                new Paused("C", 5),
                new Resumed("D"),
                null
        };

        for (Message message : examples) {
            System.out.println(
                    handle(message) + " | " + handleWithFallback(message)
            );
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac -encoding UTF-8 SealedCompatibilityDemo.java
java SealedCompatibilityDemo
~~~

Đầu ra dự kiến:

~~~text
created:A | created
deleted:B | deleted
paused:C:5 | unknown-message
extension:Resumed | unknown-message
missing | missing
~~~

**Cách đọc kết quả:**

1. **Created** và **Deleted** được xử lý bằng nhánh riêng, giữ hợp đồng quen thuộc của caller.
2. **Paused** và **Resumed** đều thuộc **Extension**, nên **handle** không cần thêm case trực tiếp cho mỗi lớp này. Đây là cách bảo toàn cấu trúc switch trên Message.
3. Trong **handleExtension**, kiểu **Paused** được xử lý đặc biệt qua **instanceof Paused paused**. **Resumed** chưa có xử lý riêng, nên nhận fallback **extension:Resumed**. Khi thêm một implementation Extension mới, caller vẫn có đường xử lý có chủ đích.
4. **handleWithFallback** có **default**, nên các lớp Extension hiện có và tương lai đều vào nhánh **unknown-message**, không gây lỗi thiếu case.
5. **null** có nhánh riêng **case null**, giúp hai phương thức trả về **missing**. Không nên cho rằng default của switch pattern sẽ tự nhận null.

Ví dụ này cố ý dùng **non-sealed** cho Extension để minh họa hướng mở rộng. Trong dự án thực tế, chỉ nên dùng kiểu mở này khi việc cho phép implementation mới là chủ đích của API. Nếu chỉ tổ chức nội bộ được phép tạo subtype, thiết kế module/package và các quy tắc truy cập vẫn cần được xem xét riêng.

## 4. Chiến lược B — thêm fallback có chủ đích cho caller

Đôi khi không muốn đưa nhánh Extension vào model, nhưng vẫn cần cho phép owner mở rộng danh sách **permits**. Caller Java 21 có thể chọn một switch có **default**:

~~~java
static String render(Event event) {
    return switch (event) {
        case null -> "missing";
        case Created c -> "created:" + c.id();
        case Deleted d -> "deleted:" + d.id();
        default -> "unsupported-event";
    };
}
~~~

Ở đây **Event**, **Created**, **Deleted** là các kiểu minh họa đã khai báo trong ví dụ mở đầu. Với bản Event mới có subtype **Archived**, chương trình có thể biên dịch lại vì default nhận phần chưa được phân loại. Binary cũ cũng có nhánh dự phòng để xử lý một instance Archived theo hợp đồng thiết kế, thay vì rơi vào trường hợp không case nào áp dụng.

Nhưng fallback có một **đánh đổi**: compiler không còn nhắc người viết “Archived chưa được xử lý riêng” khi thêm subtype. Nếu Archived đáng lẽ phải kích hoạt một workflow quan trọng, việc im lặng trả về **unsupported-event** có thể che lỗi nghiệp vụ.

Vì vậy, fallback cần có chính sách rõ ràng: **trả lỗi có kiểu**, log/metric, giá trị “unknown” hiển thị an toàn, hoặc chuyển sang bộ xử lý phiên bản khác. Trong API trả về kết quả nghiệp vụ, thường nên biểu diễn **unknown/unsupported** bằng một loại kết quả tường minh thay vì trả về một thành công giả.

### Dùng catch-all pattern hay default?

Có thể dùng một pattern kiểu root ở cuối để bắt các object còn lại:

~~~java
// Đoạn minh họa Java 21+ đặt trong phương thức nhận Event event:
return switch (event) {
    case Created c -> "created:" + c.id();
    case Deleted d -> "deleted:" + d.id();
    case Event unknown -> "unsupported-event";
};
~~~

**case Event unknown** bao phủ mọi đối tượng Event khác null, kể cả subtype mới. Nó có kiểu biến **unknown** để có thể dùng trong xử lý fallback. Không thêm các case subtype phía sau nó: chúng sẽ bị nhánh tổng quát che và compiler có thể báo **dominated case**.

**Khác biệt:** **default** xử lý giá trị còn lại theo quy tắc fallback; **case Event unknown** là type pattern khớp mọi Event không null. Nếu hợp đồng cho phép null, vẫn nên viết nhánh xử lý null tường minh. Với sealed hierarchy mà caller muốn compiler nhắc khi thêm subtype, **không dùng cả hai dạng catch-all**.

## 5. Chiến lược C — giữ một nhánh sealed trung gian

Không phải lúc nào cũng phải dùng non-sealed. Một hướng khác là giữ root ổn định và đặt các kiểu có thể phát triển dưới một subinterface **sealed**:

~~~java
sealed interface Message permits Created, Deleted, Lifecycle {}

record Created(String id) implements Message {}
record Deleted(String id) implements Message {}

sealed interface Lifecycle extends Message
        permits Paused, Resumed {}

record Paused(String id) implements Lifecycle {}
record Resumed(String id) implements Lifecycle {}
~~~

Caller xử lý root bằng:

~~~java
static String summarize(Message message) {
    return switch (message) {
        case Created c -> "created";
        case Deleted d -> "deleted";
        case Lifecycle state -> "lifecycle";
    };
}
~~~

Các đoạn trên là **mã minh họa Java 21+**, không phải một chương trình độc lập. Nếu owner thêm một permitted subtype mới **Retrying implements Lifecycle** và cập nhật permits của Lifecycle, switch **summarize** vẫn có **case Lifecycle state** và tiếp tục bao phủ subtype ấy. Compiler của **summarize** không buộc caller phân biệt từng Lifecycle con.

Ngược lại, consumer đang switch trực tiếp trên **Lifecycle** với các case **Paused** và **Resumed** không default có thể phải thêm case **Retrying** khi biên dịch lại. Lợi ích của nhánh trung gian là **giới hạn vùng chịu tác động**: caller tổng quát chỉ biết Lifecycle, còn caller nghiệp vụ sâu hơn chấp nhận trách nhiệm phân loại các subtype của Lifecycle.

Điểm khác so với **non-sealed Extension**: nhánh **sealed Lifecycle** vẫn giữ một tập con đóng và kiểm tra exhaustiveness cho những đoạn code muốn phân tích chính xác tập trạng thái con. Đó có thể là lựa chọn tốt hơn khi owner cần kiểm soát hoàn toàn các subtype mới.

## 6. Không thể vừa ép mọi caller xử lý subtype mới, vừa hứa caller không phải đổi

Một sealed hierarchy liệt kê subtype một cách exhaustive chính là một **hợp đồng thế giới đóng**. Nếu bên thứ ba đang viết:

~~~java
return switch (event) {
    case Created c -> processCreated(c);
    case Deleted d -> processDeleted(d);
};
~~~

và bạn bổ sung **Archived** trực tiếp vào Event, compiler có lý do đúng đắn để báo thiếu nhánh khi consumer biên dịch lại.

Đó không nhất thiết là một “lỗi Java”. Nó là **thông báo thay đổi hợp đồng**. Một API muốn vừa cho caller xem toàn bộ trạng thái chi tiết, vừa tự do bổ sung bất kỳ trạng thái mới nào mà không làm caller thay đổi, phải xác định trước hành vi fallback hoặc tách một giao diện ổn định khỏi tầng chi tiết có thể mở rộng.

Ba lựa chọn nhất quán:

| Ưu tiên của API | Thiết kế thường phù hợp | Đánh đổi |
| --- | --- | --- |
| Mọi subtype mới bắt buộc được xử lý riêng | Sealed root + exhaustive switch, không default | Mở rộng sẽ yêu cầu sửa caller khi build lại |
| Hỗ trợ subtype tương lai với hành vi chung | Case **default** hoặc pattern kiểu root làm fallback | Caller có thể không phát hiện nghiệp vụ mới |
| Muốn ổn định caller cấp cao nhưng vẫn quản lý một nhánh chi tiết | Root sealed + nhánh **non-sealed** hoặc sealed trung gian | Caller sâu hơn có thể vẫn cần nâng cấp |
| Muốn giảm phân loại kiểu trong caller | Đa hình/handler/visitor thích hợp | Phải thiết kế trách nhiệm và versioning của interface |

**Không có giải pháp đơn lẻ bảo đảm mọi loại tương thích cho mọi thay đổi.** Cách tốt là xác định ai sở hữu các subtype, ai sở hữu switch, và vị trí nào được phép dùng fallback.

## 7. Tổ chức API để tiến hóa có kiểm soát

### 7.1. Giữ API công khai ít phụ thuộc tên subtype

Nếu một service chỉ cần hiển thị thông điệp tổng quát, nên cho caller dùng một phương thức hoặc adapter ổn định thay vì yêu cầu biết hết mọi record mới. Ví dụ:

~~~java
// Ví dụ chữ ký adapter, không phải chương trình đầy đủ.
interface MessagePresenter {
    String present(Message message);
}
~~~

Một implementation do thư viện quản lý có thể cập nhật logic xử lý subtype khi thư viện phát hành phiên bản mới. Caller chỉ gọi **present(message)**, nên ít phải sửa switch trực tiếp. Điều này không tự giải quyết mọi vấn đề phiên bản, nhưng **gom trách nhiệm** cập nhật các subtype về một vị trí.

Nếu muốn đưa hành vi vào interface, cân nhắc đa hình: các implementation tự đảm nhiệm phương thức trừu tượng hoặc dùng default method được thiết kế rõ. Tuy nhiên, việc thêm method bắt buộc vào interface công khai có thể gây vấn đề với implementation cũ; các quy tắc tương thích method cần được đánh giá riêng, không chỉ nhìn vào sealed permits.

### 7.2. Tách hành vi “đã biết” và “chưa biết”

Một bộ phân loại ổn định có thể trả về giá trị typed như **KnownResult** và **UnknownResult**, hoặc dùng mã trạng thái lỗi tường minh. Thay vì đổi một subtype mới thành thành công im lặng, caller có thể giữ quy tắc:

- Nếu subtype quen thuộc: xử lý đúng workflow đã hỗ trợ.
- Nếu subtype mới: lưu thông tin, báo hỗ trợ chưa đầy đủ, hoặc hiển thị fallback an toàn.
- Nếu subtype vi phạm hợp đồng: từ chối có kiểm soát.

Điều này đặc biệt cần thiết cho dữ liệu đi qua JSON, event bus, database hoặc giao diện giữa các service. Một switch có default chưa chắc đủ: **deserializer có thể từ chối loại dữ liệu mới trước khi logic switch được gọi**. Cần kiểm tra cả format, discriminator, schema và khả năng đọc phiên bản mới.

### 7.3. Versioning và rolling upgrade

Trong hệ thống nhiều module, owner thường triển khai model/producer trước hoặc sau consumer. Cần chú ý:

1. Consumer cũ có được nhận dữ liệu subtype mới trong giai đoạn chuyển tiếp không?
2. Tầng giải mã có bảo toàn được một loại chưa biết hoặc trả lỗi có kiểm soát không?
3. Consumer có default hoặc nhánh fallback đã định nghĩa từ trước chưa?
4. Có cơ chế theo dõi/tắt feature phát sinh subtype mới cho đến khi các consumer đã sẵn sàng không?
5. Việc build lại consumer với phiên bản API mới có bật kiểm tra exhaustiveness không?

Một chiến lược phát hành an toàn là **nâng cấp consumer trước**, bổ sung khả năng nhận hoặc từ chối subtype mới đúng hợp đồng, rồi mới bật producer phát dữ liệu subtype đó.

## 8. Các lỗi phổ biến cần tránh

**Lỗi 1 — nhầm binary compatible với “không bao giờ lỗi runtime”.** Thêm permitted direct subtype không nhất thiết phá liên kết class file, nhưng switch exhaustive cũ có thể ném **MatchException** khi gặp subtype mới không có case.

**Lỗi 2 — thêm default chỉ để dập lỗi compiler.** Default làm switch exhaustive, nhưng không bảo đảm fallback đúng yêu cầu nghiệp vụ. Nếu trạng thái mới quan trọng, cần xử lý riêng.

**Lỗi 3 — quên null.** Các type pattern **case Created c**, **case Extension e** không khớp null. **default** không thay thế **case null** trong các switch tham chiếu đã minh họa; không có case xử lý null có thể ném **NullPointerException**.

**Lỗi 4 — non-sealed extension mà không có nhánh xử lý chung.** Nếu Root cho phép Extension có vô số implementation tương lai, caller muốn ổn định phải có **case Extension** hoặc fallback bao phủ chúng, không chỉ liệt kê các class hiện biết.

**Lỗi 5 — giữ nguyên root permits rồi tưởng có thể thêm direct subtype tự do.** Sealed root vẫn giới hạn direct subtypes. Muốn thêm biến thể không đổi root, phải làm nó triển khai một permitted subinterface thích hợp, chẳng hạn Extension.

**Lỗi 6 — cho rằng mọi caller đều an toàn vì một switch đã có default.** Các caller khác có thể cast, serialize/deserialize, kiểm tra tên class hoặc switch không default. Cần kiểm kê các điểm phụ thuộc vào hierarchy.

**Lỗi 7 — guard khi chỉ có nhánh có điều kiện.** **case Extension e when supported(e)** không bao phủ những Extension không thỏa guard; cần một case Extension không guard hoặc fallback thích hợp.

**Lỗi 8 — đổi từ sealed sang non-sealed để “hết lỗi” mà không xem tác động API.** Mở rộng quyền triển khai có thể làm mất những bất biến của domain, thêm các implementation chưa được kiểm soát và thay đổi kỳ vọng của caller.

**Lỗi 9 — cho rằng exhaustiveness kiểm tra cả nghiệp vụ.** Compiler chỉ bảo đảm một case phù hợp về mặt kiểu; nó không chứng minh một nhánh trả về kết quả đúng, không gây tác dụng phụ xấu hay xử lý đúng serializer.

**Lỗi 10 — không test binary cũ.** Một bản build sạch toàn bộ project chỉ kiểm tra source compatibility của code mới. Nếu hệ thống thực tế cập nhật từng service, còn phải test đường nhận subtype mới của consumer phiên bản cũ.

## 9. Checklist kiểm chứng trước khi phát hành

1. **Xác định phạm vi mở rộng:** thêm direct subtype của root, thêm subtype dưới một nhánh sealed, hay thêm implementation của nhánh non-sealed?
2. **Liệt kê hợp đồng caller:** caller có switch exhaustive không default, pattern tổng quát, default, visitor hoặc adapter?
3. **Phân biệt ba mức tương thích:** source khi rebuild, binary khi liên kết, behavior khi gặp dữ liệu mới.
4. **Chọn chính sách subtype chưa biết:** cần case riêng, fallback an toàn, lỗi có kiểm soát hay cấm phát đến consumer cũ?
5. **Biên dịch lại các consumer** với phiên bản model mới để phát hiện switch chưa exhaustive, dominance và các thay đổi API khác.
6. **Test mọi subtype cũ và mới**, bao gồm null, guard đúng/sai, dữ liệu không hợp lệ và kết quả fallback.
7. **Test kịch bản version lệch nhau**, đặc biệt caller đã build trước khi subtype mới tồn tại; kiểm tra đường có thể gây MatchException.
8. **Kiểm tra serializer và transport schema**: switch đúng cũng vô ích nếu dữ liệu mới chưa parse được.
9. **Theo dõi fallback** bằng log/metric/test thay vì âm thầm coi subtype chưa biết là đã xử lý hoàn toàn.
10. **Viết hướng dẫn nâng cấp**: phiên bản nào giới thiệu subtype, consumer nào cần thay đổi, khi nào producer được phát dạng dữ liệu mới.

### Bài tập tự kiểm tra

**Câu 1.** Root sealed ban đầu có **Created** và **Deleted**; một switch Java 21 liệt kê cả hai, không default. Owner thêm direct subtype **Archived**. Khi rebuild caller cũ, chuyện gì xảy ra? **Compiler có thể báo switch chưa exhaustive.** Đó là kiểm tra có chủ ý.

**Câu 2.** Không rebuild caller, chỉ thay library bằng bản cho phép Archived. Binary cũ có chắc lỗi liên kết không? **Không.** Việc thêm permitted subtype là binary compatible, nhưng nếu Archived đi vào một switch cũ không có nhãn áp dụng thì Java 21 có thể ném **MatchException**.

**Câu 3.** Có **sealed Message permits Created, Deleted, Extension** và **non-sealed Extension**. Thêm **Paused implements Extension** có cần sửa danh sách permits của Message không? **Không.** Caller có **case Extension** sẽ bao phủ Paused.

**Câu 4.** Caller chỉ viết **case Extension e when e instanceof Paused** mà không có nhánh cho Extension khác. Có chắc exhaustive không? **Không.** Một implementation mới có thể không thỏa guard.

**Câu 5.** Root có default trả **unknown**; thêm subtype mới thì mọi thứ chắc đúng chưa? **Chưa**. Phải kiểm tra xem xử lý unknown có đáp ứng nghiệp vụ, hợp đồng lỗi và tiến trình nâng cấp không.

**Câu 6.** Root sealed có một nhánh con **sealed Lifecycle**, caller cấp cao dùng **case Lifecycle l**, còn caller cấp thấp switch riêng trên Lifecycle. Nếu thêm subtype trong Lifecycle, ai có nguy cơ phải sửa? **Caller cấp thấp** liệt kê từng subtype không default; caller cấp cao có case Lifecycle đã bao phủ nhánh đó.

## 10. Tài liệu chính thức

- [JLS Java SE 21, §13.4.2.1 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.2.1): tương thích nhị phân và migration khi thêm permitted subclass.
- [JLS Java SE 21, §13.5.2 — Sealed and Non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.5.2): thay đổi tập permitted subinterfaces và hành vi binary cũ.
- [JLS Java SE 21, §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): compiler phân tích tính bao phủ.
- [JLS Java SE 21, §15.28 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): cách switch expression cho kết quả và xử lý nhãn không phù hợp.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục đích và cơ chế giới hạn subtype.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type pattern, exhaustive switch, dominance và null.

**Kết luận:** mở rộng sealed hierarchy an toàn đòi hỏi chọn trước *caller có cần biết từng subtype hay không*. Nếu caller bắt buộc xử lý riêng mọi loại, exhaustive switch không default là cơ chế tốt và việc thêm subtype có thể chủ động làm build báo lỗi. Nếu ưu tiên tương thích tiến hóa, hãy dành nhánh mở rộng có case tổng quát, dùng fallback tường minh hoặc gom xử lý vào API ổn định. Dù chọn cách nào, phải kiểm chứng **source, binary và runtime behavior** riêng biệt; “thêm permitted subtype là binary compatible” không đồng nghĩa consumer cũ đã hiểu được dữ liệu mới.