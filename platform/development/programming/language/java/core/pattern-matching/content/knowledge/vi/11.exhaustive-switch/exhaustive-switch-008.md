# Exhaustiveness khi thêm subtype mới vào sealed hierarchy của Java

## 1. Vì sao thêm một subtype có thể làm switch không còn exhaustive?

Khi một **sealed class** hoặc **sealed interface** chỉ cho phép một tập subtype, compiler Java có thể dùng danh sách này để chứng minh **switch expression** xử lý đầy đủ mọi loại đối tượng được phép. Lợi ích lớn nhất xuất hiện khi mô hình dữ liệu **thay đổi theo thời gian**: thêm subtype mới có thể khiến các switch cũ thiếu case và gây **lỗi biên dịch khi biên dịch lại**.

Xét phiên bản ban đầu của mô hình sự kiện:

~~~java
sealed interface Event permits Started, Stopped {}

record Started(String id) implements Event {}
record Stopped(String id) implements Event {}

static String describe(Event event) {
    return switch (event) {
        case Started started -> "started:" + started.id();
        case Stopped stopped -> "stopped:" + stopped.id();
    };
}
~~~

Đây là **đoạn khai báo và phương thức minh họa Java 21**, chưa phải chương trình độc lập. Vì **Started** và **Stopped** là toàn bộ permitted direct subtypes của **Event**, hai case không guard đã bao phủ mọi đối tượng **Event** khác **null**. Do đó không cần **default**.

Giả sử phiên bản tiếp theo bổ sung một trạng thái:

~~~java
// Mô hình phiên bản mới, thay cho khai báo cũ.
sealed interface Event permits Started, Stopped, Paused {}

record Started(String id) implements Event {}
record Stopped(String id) implements Event {}
record Paused(String id) implements Event {}
~~~

Nếu giữ nguyên **describe** và **biên dịch lại trên Java 21 với mô hình mới**, compiler sẽ thấy đối tượng **Paused** chưa được xử lý. Kết quả là lỗi **switch expression does not cover all possible input values** (cách diễn đạt chẩn đoán cụ thể có thể khác giữa các compiler). Đây chính là tác dụng bảo vệ của exhaustiveness: thay đổi model buộc các consumer phải cân nhắc hành vi cho subtype mới.

**Điểm quan trọng:** chuyện “thêm subtype sẽ làm switch cũ hỏng” cần phân biệt **source compatibility lúc biên dịch lại**, **binary compatibility của class file đã biên dịch** và **hành vi khi chạy với dữ liệu thuộc subtype mới**. Ba việc này không hoàn toàn giống nhau.

## 2. Luồng nâng cấp đúng: thêm model, nhận lỗi, bổ sung case

Một quy trình tiến hóa hợp lý:

1. Thêm **Paused** vào danh sách **permits** của **Event**, rồi tạo implementation hợp lệ.
2. Biên dịch lại toàn bộ module chứa những switch expression xử lý **Event**.
3. Compiler chỉ ra những switch chưa có nhánh dành cho **Paused**.
4. Bổ sung **case Paused paused** và quyết định kết quả nghiệp vụ.
5. Chạy test cho cả ba subtype, bao gồm trường hợp dữ liệu mới được tạo từ API, database hoặc thông điệp bất đồng bộ.

Phiên bản switch được cập nhật:

~~~java
static String describe(Event event) {
    return switch (event) {
        case Started started -> "started:" + started.id();
        case Stopped stopped -> "stopped:" + stopped.id();
        case Paused paused -> "paused:" + paused.id();
    };
}
~~~

Phương thức này **không có default** nhưng đã exhaustive với phiên bản mới của Event. Khi một subtype thứ tư được bổ sung, người bảo trì lại nhận được tín hiệu từ compiler.

**Thêm case là phần kỹ thuật; chọn hành vi là phần nghiệp vụ.** Với sự kiện **Paused**, ứng dụng cần quyết định có ghi log, thay đổi state, tạo notification, hay từ chối sự kiện hay không. Chỉ thêm nhánh trả về chuỗi không có nghĩa toàn bộ luồng xử lý liên quan đã sẵn sàng.

## 3. Ví dụ Java 21 đầy đủ: subtype mới đã được xử lý

Lưu chương trình **SealedEvolutionDemo.java**:

~~~java
public class SealedEvolutionDemo {
    sealed interface Notification
            permits Sent, Failed, Queued {}

    record Sent(String id) implements Notification {}
    record Failed(String reason) implements Notification {}
    record Queued(int position) implements Notification {}

    static String describe(Notification notification) {
        return switch (notification) {
            case Sent sent -> "sent:" + sent.id();
            case Failed failed -> "failed:" + failed.reason();
            case Queued queued -> "queued:" + queued.position();
        };
    }

    static String describeWithDefault(Notification notification) {
        return switch (notification) {
            case Sent sent -> "sent";
            case Failed failed -> "failed";
            default -> "fallback";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Sent("A1")));
        System.out.println(describe(new Failed("timeout")));
        System.out.println(describe(new Queued(3)));
        System.out.println(
                describeWithDefault(new Queued(3)));
    }
}
~~~

Biên dịch/chạy bằng JDK 21 trở lên:

~~~bash
javac -encoding UTF-8 SealedEvolutionDemo.java
java SealedEvolutionDemo
~~~

Đầu ra:

~~~text
sent:A1
failed:timeout
queued:3
fallback
~~~

**Giải thích từng kết quả:**

- **Sent("A1")** khớp nhánh **Sent**, tạo **sent:A1**.
- **Failed("timeout")** khớp **Failed**, tạo **failed:timeout**.
- **Queued(3)** là subtype mới trong tập **permits** hiện tại; phương thức **describe** có case tương ứng nên tạo **queued:3**.
- **describeWithDefault** chỉ liệt kê **Sent** và **Failed**, sau đó có **default**, nên compiler vẫn chấp nhận. **Queued(3)** đi vào **fallback** mà không buộc người phát triển viết nhánh xử lý riêng.

Chương trình này cho thấy **default vẫn làm switch exhaustive về mặt cú pháp nhưng có thể làm mất tín hiệu khi mở rộng tập subtype**. Nếu **Queued** có nghiệp vụ riêng bắt buộc phải thực hiện, phương thức có default quá rộng có thể che một lỗi thiết kế dù biên dịch thành công.

**Phiên bản:** sealed types được chuẩn hóa từ Java 17; pattern matching cho **switch** và cú pháp **case Type variable ->** chính thức từ Java 21. Chương trình không cần preview.

## 4. Default có nên xuất hiện trong switch sealed không?

Không có quy tắc “cấm default”. Quyết định phụ thuộc hợp đồng nghiệp vụ:

| Cách viết | Khi thêm subtype mới và biên dịch lại | Khi nên dùng |
| --- | --- | --- |
| Liệt kê mọi subtype, **không default** | Compiler có thể báo thiếu case, buộc cập nhật | Phải xử lý riêng từng loại |
| Một vài subtype + **default** | Thường vẫn biên dịch, subtype mới rơi vào default | Mọi loại chưa liệt kê thực sự có chung hành vi |
| Case kiểu cha rộng, như **case Event e** ở cuối | Có thể vẫn exhaustive, subtype mới khớp nhánh rộng | Thật sự muốn xử lý chung cho toàn bộ phần còn lại |
| Các subtype có guard **when** | Guard tùy ý không tự bảo đảm exhaustive | Dùng thêm case không guard bao phủ phần dư hoặc chính sách dự phòng |

Ví dụ **default** hợp lý khi nhiệm vụ chỉ cần trả về mô tả chung **"not supported"** cho mọi trạng thái chưa xử lý, và việc chấp nhận thêm một subtype với hành vi đó là ý định rõ ràng.

Ngược lại, trong một **state machine** có quy tắc chính xác cho từng trạng thái, default rộng có thể trì hoãn lỗi đến khi người dùng gặp trạng thái mới. Khi ấy, **bỏ default** để tận dụng compiler thường giúp bảo trì tốt hơn.

Ngay cả khi bỏ default, vẫn cần test cho từng subtype: compiler chỉ chứng minh nhánh **tồn tại**, không chứng minh nội dung nhánh **đúng**.

## 5. Bổ sung subtype trực tiếp khác gì bổ sung lớp con bên dưới subtype có sẵn?

Tập **permits** của một sealed type kiểm soát **các subtype trực tiếp**. Mỗi permitted subtype phải tuân thủ quy tắc của Java và được khai báo theo một trong các hình thức thích hợp: **final**, **sealed** hoặc **non-sealed**; **record** là final theo đặc tính ngôn ngữ.

### 5.1. Thêm permitted direct subtype mới

~~~java
sealed interface Shape permits Circle, Rectangle, Triangle {}
~~~

Nếu switch trước đó chỉ có **case Circle** và **case Rectangle**, compiler Java 21 không còn xem là exhaustive khi **Triangle** được phép và chưa được bao phủ.

### 5.2. Thêm implementation của một nhánh non-sealed đã có

~~~java
sealed interface Task permits KnownTask, ExternalTask {}

record KnownTask(int id) implements Task {}

non-sealed interface ExternalTask extends Task {}

final class ThirdPartyTask implements ExternalTask {}
~~~

Đây là **mã minh họa các khai báo kiểu**, không phải một chương trình có main. Nếu switch của **Task** có **case KnownTask known** và **case ExternalTask external**, compiler có thể coi nó exhaustive đối với các subtype được phép, và **ThirdPartyTask** đã nằm trong phạm vi khớp của **ExternalTask**.

Khi bổ sung một class khác triển khai **ExternalTask**, không nhất thiết phát sinh một case compile-time mới: case **ExternalTask** đã bao phủ mọi implementation của interface đó. Điều này rất quan trọng: tính exhaustive là thuộc tính **quan hệ kiểu**, không phải một danh sách cứng mọi tên class trong toàn chương trình.

### 5.3. Sealed hierarchy nhiều tầng

Nếu một permitted subtype tự nó **sealed**, compiler có thể theo dõi các nhánh con để chứng minh exhaustive. Khi thêm subtype vào tầng sâu hơn, switch đang liệt kê riêng các subtype ở tầng đó có thể trở nên thiếu nhánh sau khi biên dịch lại.

Nếu switch có một case rộng khớp trực tiếp kiểu cha đã được phép, subtype mới ở tầng sâu vẫn được bao phủ. Vì vậy mức độ compiler buộc sửa code phụ thuộc **cách các case phân chia hierarchy**.

## 6. Source compatibility: lỗi xuất hiện khi biên dịch lại

Một thay đổi có thể làm **mã nguồn consumer cũ** không còn biên dịch khi dùng phiên bản model mới:

~~~java
// Phiên bản cũ:
sealed interface State permits Open, Closed {}
record Open() implements State {}
record Closed() implements State {}

// Switch cũ đã exhaustive.
static String label(State value) {
    return switch (value) {
        case Open opened -> "open";
        case Closed closed -> "closed";
    };
}
~~~

Sau khi sửa model thành **permits Open, Closed, Suspended** và thêm **record Suspended() implements State {}**, compiler không thể bảo đảm mọi State đều khớp switch cũ. **Phần thiếu không cần được gọi lúc chạy mới bị phát hiện**; chỉ việc biên dịch lại với hierarchy mới đã đủ.

Cách xử lý tốt là **cập nhật mã nguồn consumer**:

~~~java
// Đoạn thay thế phương thức label sau khi thêm subtype Suspended:
static String label(State value) {
    return switch (value) {
        case Open opened -> "open";
        case Closed closed -> "closed";
        case Suspended suspended -> "suspended";
    };
}
~~~

Đoạn mã trong phần này là các **phiên bản thay thế nhau**, không được chép cả hai khai báo/phương thức trùng tên vào một tệp. Ví dụ runnable đầy đủ ở phần 3 thể hiện trạng thái sau khi cập nhật.

Một nguyên tắc có ích trong review: **compiler báo thiếu case sau khi nâng cấp dependency là tín hiệu cần phân tích nghiệp vụ**, không phải chỉ là sự phiền toái để dập tắt bằng default.

## 7. Binary compatibility: class file cũ có thể vẫn liên kết được

Đặc tả Java 21 phân biệt rất rõ việc bổ sung permitted direct subtype của sealed class/interface với việc chạy một switch đã được biên dịch trước khi subtype đó tồn tại:

- **Thêm subtype được phép** nhìn chung là một thay đổi **binary compatible** đối với các binary trước đó: class file đã tồn tại vẫn có thể liên kết với model mới.
- Tuy nhiên, một **switch exhaustive được biên dịch theo hierarchy cũ** có thể gặp một **instance thuộc subtype mới** mà switch không có nhãn áp dụng.
- Trong trường hợp không tìm được nhãn áp dụng lúc chạy, **Java 21 có thể ném java.lang.MatchException**. Đây là vấn đề **migration/runtime behavior**, dù thay đổi model là binary compatible ở cấp liên kết.
- Nếu **recompile** consumer với model mới mà vẫn thiếu case và không có nhánh bao phủ phù hợp, lỗi xuất hiện ở **compile time** thay vì đợi runtime.

Điều này không có nghĩa bất kỳ subtype mới nào cũng luôn gây **MatchException**. Lỗi chỉ có thể xảy ra khi binary cũ nhận một giá trị thuộc kiểu mới và **không case nào áp dụng**. Nếu switch đã có **default** hoặc một pattern rộng bao phủ đối tượng đó, nhánh tương ứng có thể xử lý được.

**Không nhầm với IncompatibleClassChangeError khi bỏ subtype:** thay đổi **loại bỏ** một class khỏi danh sách permitted của sealed hierarchy có quy tắc tương thích khác và có thể khiến binary của class đó không được tải đúng. Bài này nói chủ yếu về **thêm subtype**.

### Bảng kiểm tra ba kịch bản triển khai

| Tình huống | Hiện tượng có thể xảy ra | Việc nên làm |
| --- | --- | --- |
| Biên dịch lại model mới + consumer switch cũ không default | Lỗi compile-time vì chưa exhaustive | Thêm case thích hợp |
| Chỉ thay binary model mới, vẫn chạy consumer đã build với model cũ | Có thể ném **MatchException** khi gặp instance subtype mới không khớp | Build/test lại toàn bộ consumer và cập nhật case |
| Consumer có default hoặc nhánh tổng quát | Có thể chạy nhánh dự phòng thay vì lỗi bao phủ | Xem fallback có đúng nghiệp vụ hay đang che thiếu sót |

Vì một hệ thống nhiều module có thể phân phối **library chứa sealed model** và **consumer chứa switch** theo thời điểm khác nhau, cả **kiểm tra tương thích khi build** lẫn **test với dữ liệu từ phiên bản model mới** đều cần thiết.

## 8. Thêm enum constant cũng đặt ra bài toán tương tự

Với enum:

~~~java
enum Phase { NEW, RUNNING, DONE }

static String label(Phase phase) {
    return switch (phase) {
        case NEW -> "new";
        case RUNNING -> "running";
        case DONE -> "done";
    };
}
~~~

Nếu bổ sung **CANCELLED** vào **Phase**, switch expression không default ban đầu sẽ thiếu case và thường bị báo lỗi khi biên dịch lại. Ngay cả khi binary cũ vẫn liên kết, hành vi runtime với một hằng enum mới không có case áp dụng có thể thất bại.

Từ Java 21, các switch expression và pattern switch cần tính exhaustive, nhưng **không nên áp một tên ngoại lệ cố định cho mọi phiên bản Java**: các phiên bản cũ của switch expression từng dùng loại lỗi runtime khác khi hằng enum mới xuất hiện mà binary cũ chưa biết. Khi chẩn đoán thực tế, hãy kiểm tra đúng JDK đang chạy.

Tương tự sealed hierarchy, thêm **default** có thể giúp chuyển sang hành vi dự phòng, nhưng cũng có thể che việc một trạng thái nghiệp vụ mới chưa được thiết kế xử lý rõ ràng.

## 9. Null, when và thứ tự case khi mở rộng subtype

### Null không tự được xử lý bởi exhaustiveness

Một switch của **Notification** có đầy đủ **Sent**, **Failed**, **Queued** vẫn có thể ném **NullPointerException** khi đầu vào là **null**. Nếu null là trạng thái hợp lệ, thêm **case null**:

~~~java
// Đoạn switch expression minh họa Java 21+:
return switch (notification) {
    case null -> "missing";
    case Sent sent -> "sent:" + sent.id();
    case Failed failed -> "failed:" + failed.reason();
    case Queued queued -> "queued:" + queued.position();
};
~~~

**case null** xử lý vấn đề null, còn các case type pattern xử lý những đối tượng không null; hai kiểm tra phải được xem riêng.

### Case có when chưa chắc bao phủ subtype

~~~java
// Không exhaustive nếu đây là case duy nhất cho Queued.
case Queued queued when queued.position() > 0 ->
        "queued-positive";
~~~

Một **Queued(0)** sẽ không khớp guard. Khi thêm subtype mới có nhiều trạng thái bên trong, cần case không guard để nhận phần còn lại hoặc một cấu trúc bao phủ khác hợp lệ:

~~~java
case Queued queued when queued.position() > 0 ->
        "queued-positive";
case Queued queued -> "queued-other";
~~~

Đây là các nhãn minh họa trong một **switch Java 21**, không phải toàn bộ chương trình độc lập. Case **Queued** không guard phải đứng sau case cụ thể có **when**, nếu không có thể gây **dominated case**.

### Kiểu cha rộng có thể che subtype mới

Nếu đặt case kiểu cha (ví dụ **case Notification n**) trước các nhánh subtype, những nhánh riêng phía sau có thể bị compiler báo dominance. Khi có subtype mới, nên đặt các case cụ thể trước case rộng và đánh giá xem case rộng có đang vô tình che yêu cầu xử lý riêng hay không.

## 10. Quy trình thay đổi sealed model an toàn

Khi đề xuất thêm subtype, có thể sử dụng checklist theo thứ tự:

1. **Xác định hợp đồng công khai của sealed type.** Đọc các permitted direct subtype, nhánh **final**, **sealed** và **non-sealed**, cùng các phụ thuộc module liên quan.
2. **Định nghĩa rõ hành vi subtype mới.** Ví dụ status mới cần log, chuyển state, hiển thị UI hay mapping API như thế nào?
3. **Cập nhật declaration model và implementation** theo cú pháp sealed của Java.
4. **Build sạch và biên dịch lại consumer** sử dụng switch expression hoặc enhanced switch; ghi nhận mọi lỗi chưa exhaustive.
5. **Bổ sung case xử lý riêng**, không thêm default tràn lan chỉ để dập lỗi.
6. **Kiểm tra các switch đã có default/pattern rộng:** chúng sẽ không nhất thiết báo compile error, nhưng có thể đang nhận subtype mới bằng hành vi không phù hợp.
7. **Test từng subtype cũ và mới**, gồm dữ liệu null, các guard đúng/sai, trường hợp biên của mỗi state và hành vi ngoại lệ.
8. **Kiểm tra tương thích khi triển khai nhiều version:** tránh dùng consumer binary cũ với model mới mà chưa test subtype mới; thử cả kịch bản rolling upgrade khi hệ thống có nhiều service/module.
9. **Đánh giá các serializer/deserializer và API contracts** vì subtype mới có thể ảnh hưởng cách parse, persist và trao đổi dữ liệu ngoài switch.
10. **Tài liệu hóa thay đổi** và cập nhật ví dụ/test fixture cho subtype mới; chú ý mọi nhánh state machine và phép ánh xạ dữ liệu.

Một tình huống dễ bỏ sót: switch hiện tại có default để trả về **"unknown"**, nên build xanh sau khi thêm subtype. Điều đó không chứng minh nghiệp vụ đã hỗ trợ subtype mới; hãy bổ sung test dựa trên giá trị thực tế của subtype ấy.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Sealed interface **Result** ban đầu chỉ có **Ok** và **Error**; switch expression có hai case không default. Thêm **Pending** rồi biên dịch lại consumer mà không sửa switch. Điều gì xảy ra? **Lỗi chưa exhaustive ở compile time**, vì kiểu nguồn bây giờ có một subtype mới chưa được bao phủ.

**Câu 2.** Thêm **default -> "other"** có giải quyết được lỗi biên dịch không? **Thường có**, nhưng chưa chắc đúng nghiệp vụ. Nếu Pending cần quy tắc riêng, phải thêm **case Pending**.

**Câu 3.** Không biên dịch lại consumer mà chỉ triển khai thư viện model mới, mọi thứ có chắc an toàn không? **Không.** Dù thay đổi có thể binary compatible, một instance Pending đi vào switch cũ không có nhánh áp dụng có thể gây **MatchException** trên Java 21.

**Câu 4.** Sealed interface có permitted subtype **External**, được khai báo **non-sealed**, và switch đã có **case External x**. Thêm một class mới implements External. Có phải switch luôn thiếu case? **Không**. Type pattern External đã bao phủ cả những implementation đó.

**Câu 5.** Subtype mới **Queued** chỉ được xử lý bằng **case Queued q when q.position() > 0**. Có đủ cho mọi Queued không? **Không**. Giá trị có position bằng 0 hoặc âm có thể trượt guard; cần nhánh phủ phần còn lại.

**Câu 6.** Có đủ case cho mọi subtype nhưng truyền null vào switch không case null. Exhaustive có ngăn NPE không? **Không**. Tính bao phủ kiểu và xử lý null là hai vấn đề độc lập.

## 12. Tài liệu chính thức

- [JLS Java 21 §14.11.1.1 — Exhaustive Switch Blocks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): cách compiler tính bao phủ sealed type, enum, pattern và default.
- [JLS Java 21 §13.4.2.1 — Sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.2.1): thêm permitted subclass, binary compatibility và tác động lên exhaustive switch.
- [JLS Java 21 §13.5.2 — Sealed and Non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.5.2): cập nhật permitted interfaces, binary compatibility và MatchException.
- [JLS Java 21 §15.28.2 — Run-Time Evaluation of switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28.2): điều gì xảy ra nếu không có nhãn phù hợp ở runtime.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): cú pháp và ý nghĩa của switch pattern trong Java 21.

**Kết luận:** thêm subtype mới là phép thử thực tế cho lợi ích của exhaustive switch. Với sealed hierarchy và switch không default, compiler Java 21 giúp phát hiện những case còn thiếu **khi biên dịch lại**. Nhưng **binary compatibility không đảm bảo an toàn nghiệp vụ lúc chạy với subtype mới**: consumer cũ có thể gặp **MatchException** nếu không có nhánh áp dụng. Vì vậy, hãy cập nhật switch một cách có chủ ý, kiểm tra các default hiện hữu và chạy lại test/bản build đầy đủ khi tiến hóa mô hình kiểu.