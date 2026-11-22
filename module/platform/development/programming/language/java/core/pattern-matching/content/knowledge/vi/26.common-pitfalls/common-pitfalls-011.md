# Bỏ qua thay đổi khi subtype mới xuất hiện

**Chủ đề:** Lỗi thường gặp trong Java Core Pattern Matching. Ví dụ chính dùng **Java 21 trở lên** với sealed interface, record patterns và pattern matching for switch. Bài tập trung vào một lỗi bảo trì nguy hiểm: **thêm subtype mới nhưng các nhánh xử lý cũ vẫn biên dịch và âm thầm bỏ qua dữ liệu mới**.

## 1. Vấn đề: hệ thống mở rộng kiểu dữ liệu, logic cũ không đổi

Giả sử một ứng dụng xử lý sự kiện có hai loại: **Added** (được thêm) và **Removed** (bị xóa). Lúc đầu, mã xử lý cả hai và có một nhánh chung dành cho trường hợp không nhận diện được:

~~~java
// Minh họa: Event, Added, Removed được khai báo ở nơi khác.
static String legacy(Event event) {
    if (event instanceof Added a) {
        return "ADDED:" + a.id();
    } else if (event instanceof Removed r) {
        return "REMOVED:" + r.id();
    }
    return "IGNORED";
}
~~~

Sau một thời gian, domain thêm **Updated** (được cập nhật). Người phát triển bổ sung kiểu mới nhưng không sửa phương thức legacy. Khi gặp Updated, cả hai điều kiện instanceof đều false và phương thức trả về **IGNORED**.

Đây là một lỗi thường gặp vì:

1. **Không có lỗi biên dịch**: chuỗi if-else không có cơ chế bắt buộc xét hết subtype.
2. **Không có exception**: nhánh cuối trả về một chuỗi có vẻ hợp lệ.
3. **Dữ liệu mới có thể bị bỏ qua**: downstream không nhận biết rằng cập nhật đã xảy ra.
4. **Test cũ vẫn xanh**: nếu bộ test chỉ gửi Added/Removed, việc thêm Updated không bị phát hiện.
5. **Default của switch có thể che vấn đề tương tự**: viết switch có default không tự bảo đảm tính đúng của nghiệp vụ.

**Bài học trọng tâm:** “Có đường fallback” không đồng nghĩa “đã thiết kế hành vi cho subtype mới”. Trường hợp chưa hiểu phải được phân biệt với trường hợp nghiệp vụ chủ ý bỏ qua.

## 2. Nhận diện các cách viết dễ làm mất tín hiệu thay đổi

### 2.1. Chuỗi if-else + nhánh else rộng

~~~java
if (event instanceof Added a) {
    processAdded(a);
} else if (event instanceof Removed r) {
    processRemoved(r);
} else {
    // Không làm gì.
}
~~~

Đây là cấu trúc **có thể bỏ qua subtype mới một cách im lặng**. Nếu Updated xuất hiện, nhánh else không phát ra cảnh báo hay xử lý tương ứng. Trong các hệ thống thu thập dữ liệu, đồng bộ trạng thái hoặc thanh toán, cách bỏ qua đó có thể gây hậu quả khó phát hiện.

Không phải mọi else đều sai. Nếu nghiệp vụ định nghĩa rằng những loại khác **thực sự không cần hành động**, fallback là một lựa chọn có chủ đích. Vấn đề là **sự im lặng không được ghi vào hợp đồng và không được kiểm thử**.

### 2.2. Switch expression với default bao phủ mọi kiểu còn lại

~~~java
// Ví dụ minh họa riêng, không chép cùng hàm khác tên vào cùng class.
static String withDefault(Event event) {
    return switch (event) {
        case Added(var id) -> "ADDED:" + id;
        case Removed(var id) -> "REMOVED:" + id;
        case null -> "IGNORED";
        default -> "IGNORED";
    };
}
~~~

**default** khiến switch expression exhaustive về mặt cú pháp: mọi giá trị không được các case trước xử lý đều vào default. Khi thêm Updated, phương thức vẫn biên dịch, nhưng Updated bị quy về IGNORED. Lợi thế **compiler buộc bổ sung nhánh khi sealed hierarchy đổi** đã không còn.

Một **default ném exception** thì tốt hơn về khả năng phát hiện trong runtime nhưng vẫn không tạo ra lỗi biên dịch khi thêm subtype:

~~~java
// Chỉ là minh họa fallback fail-fast, chưa thay thế exhaustiveness.
default -> throw new IllegalStateException("Unexpected event: " + event);
~~~

Nó phù hợp khi kiểu cha mở hoặc phải xử lý đầu vào ngoài phạm vi đã biết, song không thay thế việc review domain khi thêm subtype.

### 2.3. Type pattern quá rộng

~~~java
return switch (event) {
    case Added a -> "added";
    case Event e -> "other event";
};
~~~

Với selector kiểu Event, case **Event e** có thể bao phủ toàn bộ các subtype còn lại. Một subtype mới sẽ tự động nhận cách xử lý **other event**, kể cả khi cần logic riêng. Pattern này là một nhánh tổng quát hợp lệ khi nghiệp vụ muốn như vậy, nhưng nếu mục tiêu là xét riêng từng subtype, nó có thể che sự thiếu sót tương tự default.

## 3. Cách giảm rủi ro: sealed hierarchy + exhaustive switch không có default

Java hỗ trợ **sealed class/interface** từ Java 17. Sealed type khai báo danh sách những kiểu được phép trực tiếp kế thừa hoặc triển khai:

~~~java
sealed interface Event permits Added, Removed, Updated {}

record Added(String id) implements Event {}
record Removed(String id) implements Event {}
record Updated(String id, int version) implements Event {}
~~~

Ba record là các subtype trực tiếp được phép. Record ngầm final, nên không có các subclass thêm bên dưới những nhánh này.

Đối với kiểu selector **Event**, một switch expression có nhánh xử lý đầy đủ Added, Removed, Updated có thể viết mà **không cần default**:

~~~java
static String complete(Event event) {
    return switch (event) {
        case Added(var id) -> "ADDED:" + id;
        case Removed(var id) -> "REMOVED:" + id;
        case Updated(var id, var version) ->
                "UPDATED:" + id + "@v" + version;
        case null -> "IGNORED";
    };
}
~~~

Điều này có hai lợi ích:

- Từng subtype có **quyết định nghiệp vụ rõ ràng**: dữ liệu Updated không thể vô tình rơi vào một nhánh catch-all.
- Nếu sau này thêm subtype **Restored** vào danh sách permits rồi biên dịch lại, switch expression thiếu Restored sẽ bị báo **không exhaustive**. Compiler nhắc đúng nơi cần xem lại.

**Điều kiện quan trọng:** compiler chỉ có thể đánh giá dựa trên thông tin kiểu mà nó thấy lúc biên dịch. Nếu selector là Object hoặc subtype có khả năng mở rộng (chẳng hạn qua **non-sealed**), cần phân tích miền kiểu tương ứng; không thể kết luận mọi switch đều bỏ default được.

### Tại sao case null vẫn xuất hiện?

Trong ví dụ này, nhánh cuối của hàm legacy trả IGNORED khi đầu vào là null (vì instanceof luôn false với null). Khi chuyển sang pattern switch, việc có đủ case cho các subtype **không bảo đảm null được xử lý giống trước**. Không có case null, switch trên null có thể ném NullPointerException.

Vì muốn **giữ hành vi cũ trên null**, ví dụ complete dùng **case null -> "IGNORED"**. Trong hệ thống thực tế, có thể thay bằng việc từ chối null rõ ràng, nhưng đó là quyết định về hợp đồng API, không phải tác dụng phụ nên để xảy ra âm thầm khi refactor.

## 4. Ví dụ đầy đủ có thể chạy trên Java 21

Chương trình sau cố ý đặt **ba phương án cạnh nhau**:

- **legacy:** chuỗi if-else chỉ biết Added và Removed.
- **catchAll:** switch với default, cũng chỉ biết hai subtype cũ.
- **exhaustive:** switch không có default và chủ động xử lý cả Updated.

Lưu mã trong **NewSubtypeDemo.java**:

~~~java
public class NewSubtypeDemo {
    sealed interface Event permits Added, Removed, Updated {}

    record Added(String id) implements Event {}
    record Removed(String id) implements Event {}
    record Updated(String id, int version) implements Event {}

    static String legacy(Event event) {
        if (event instanceof Added a) {
            return "ADDED:" + a.id();
        } else if (event instanceof Removed r) {
            return "REMOVED:" + r.id();
        }
        return "IGNORED";
    }

    static String catchAll(Event event) {
        return switch (event) {
            case Added(var id) -> "ADDED:" + id;
            case Removed(var id) -> "REMOVED:" + id;
            case null -> "IGNORED";
            default -> "IGNORED";
        };
    }

    static String exhaustive(Event event) {
        return switch (event) {
            case Added(var id) -> "ADDED:" + id;
            case Removed(var id) -> "REMOVED:" + id;
            case Updated(var id, var version) ->
                    "UPDATED:" + id + "@v" + version;
            case null -> "IGNORED";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Added("A-1"),
            new Removed("A-2"),
            new Updated("A-3", 2),
            null
        };

        for (Event event : events) {
            System.out.println(legacy(event) + " | "
                + catchAll(event) + " | " + exhaustive(event));
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NewSubtypeDemo.java
java NewSubtypeDemo
~~~

Kết quả chính xác:

~~~text
ADDED:A-1 | ADDED:A-1 | ADDED:A-1
REMOVED:A-2 | REMOVED:A-2 | REMOVED:A-2
IGNORED | IGNORED | UPDATED:A-3@v2
IGNORED | IGNORED | IGNORED
~~~

**Đọc kết quả:**

1. Đối với Added và Removed, ba phương án cùng trả kết quả đúng.
2. Đối với **Updated**, hai phương án cũ đều trả IGNORED, còn phương án exhaustive trả **UPDATED:A-3@v2**.
3. Đối với null, cả ba trả IGNORED vì được thiết kế rõ ràng để giữ hợp đồng cũ.
4. Kết quả không có exception trong hai phương án cũ **không chứng minh tính đúng**. Nó chính là nguyên nhân khiến lỗi mới dễ lọt qua kiểm thử nếu thiếu test cho Updated.

Với dữ liệu miền quan trọng, kết quả IGNORED nên là quyết định nghiệp vụ được đặt tên và có test. Đừng dùng nó như “giá trị mặc định vô hại” khi chưa biết subtype mới mang ý nghĩa gì.

## 5. Kiểm chứng compiler có phát hiện thiếu subtype hay không

Hãy xét một thiết kế sealed có ba subtype:

~~~java
sealed interface Signal permits Opened, Closed, Retried {}
record Opened() implements Signal {}
record Closed() implements Signal {}
record Retried(int count) implements Signal {}
~~~

Nếu viết switch expression chỉ xử lý hai subtype đầu, đoạn sau **không biên dịch**:

~~~java
// Ví dụ âm tính, không thuộc chương trình runnable ở mục 4.
static String missing(Signal signal) {
    return switch (signal) {
        case Opened o -> "opened";
        case Closed c -> "closed";
    };
}
~~~

Compiler có thể thông báo:

~~~text
the switch expression does not cover all possible input values
~~~

Lý do là **Retried** có thể xuất hiện nhưng không có case nào khớp. Việc sửa không nên là thêm default cho nhanh; hãy quyết định đúng nghiệp vụ khi Retried xuất hiện, ví dụ:

~~~java
case Retried(var count) -> "retried " + count;
~~~

Khi sử dụng sealed hierarchy và một switch expression không có default, **thêm subtype mới rồi biên dịch lại** là phép thử đặc biệt hữu ích. Nó xác nhận các điểm tiêu thụ cần được cập nhật được báo rõ ở compile time.

### Cẩn thận: có case của subtype chưa chắc đã bao phủ hết subtype đó

Vẫn với Signal, đoạn này cũng có thể thiếu nhánh:

~~~java
// Ví dụ âm tính: count = 0 không khớp nhánh Retried.
static String guarded(Signal signal) {
    return switch (signal) {
        case Opened o -> "opened";
        case Closed c -> "closed";
        case Retried(int count) when count > 0 -> "retried";
    };
}
~~~

**when** thu hẹp điều kiện của case. Nếu có Retried(0) hoặc Retried(-1), không nhánh nào xử lý. Để exhaustive, thêm case không guard cho phần còn lại:

~~~java
case Retried(var count) -> "invalid retry count";
~~~

Phân tích exhaustiveness không tự suy ra mọi mệnh đề nghiệp vụ tùy ý là đúng/sai để lấp các lỗ hổng. Một case có guard thông thường không được coi là bao phủ toàn bộ subtype, vì guard có thể false.

## 6. Enum cũng gặp cùng kiểu lỗi khi thêm giá trị mới

Giả sử một trạng thái được mô hình hóa bằng enum:

~~~java
enum Status { NEW, SENT }
~~~

Một switch expression không có default và có đủ các hằng enum có thể là exhaustive:

~~~java
static String label(Status status) {
    return switch (status) {
        case NEW -> "new";
        case SENT -> "sent";
    };
}
~~~

Nếu sau này thêm **ARCHIVED**, việc biên dịch lại phương thức trên với enum mới sẽ phát hiện thiếu case. Ngược lại, nếu ngay từ đầu viết:

~~~java
return switch (status) {
    case NEW -> "new";
    default -> "other";
};
~~~

thì ARCHIVED tự đi vào **other**. Đây có thể là đúng nếu “mọi trạng thái trừ NEW” thực sự có cùng cách xử lý; nhưng nếu ARCHIVED cần nghiệp vụ riêng, default đã làm mất tín hiệu yêu cầu cập nhật.

**Quy tắc review:** Với enum có tập giá trị được kiểm soát và mỗi hằng mang ý nghĩa riêng, ưu tiên các case tường minh. Chỉ đặt default nếu chính sách chung cho mọi giá trị khác là một quyết định được ghi nhận, không phải vì lo ngại “nếu có trạng thái mới”.

## 7. Khi nào exhaustive switch thực sự giúp và khi nào không?

| Mô hình dữ liệu | Khả năng hỗ trợ từ compiler | Điều cần xem xét |
| --- | --- | --- |
| **Sealed interface** với các subtype record/final | Có thể chứng minh mọi subtype đã được bao phủ | Tránh default che subtype mới khi cần xem xét từng loại |
| **Enum** | Có thể chứng minh mọi hằng đã được bao phủ | Đừng để hằng mới rơi vào nhánh chung ngoài ý muốn |
| **Sealed có nhánh non-sealed** | Một type pattern cho nhánh mở có thể bao phủ mọi descendant | Compiler không thể yêu cầu liệt kê từng descendant sẽ được thêm về sau |
| **Kiểu cha mở (Object/interface thường)** | Không có danh sách đóng đầy đủ các subtype từ chỉ kiểu cha | Cần nhánh tổng quát hoặc chiến lược từ chối/ủy quyền |
| **if-else với instanceof** | Không có nghĩa vụ exhaustive tương đương switch expression | Test đủ subtype và cảnh báo khi gặp kiểu không biết |
| **switch với default/case tổng quát** | Cú pháp có thể exhaustive, nhưng nhiều subtype cùng vào fallback | Xác định rõ fallback là hành vi mong muốn hay đang che thiếu nhánh |

Một sealed interface được khai báo **non-sealed** ở nhánh con cho phép bên ngoài mở rộng tiếp. Khi một switch dùng type pattern cho nhánh non-sealed đó, compiler có thể coi nhánh là được bao phủ đầy đủ; nhưng những descendant mới sẽ **không** bắt buộc cần case riêng. Nếu hệ thống yêu cầu quyết định xử lý với mỗi loại mới, cần cân nhắc đóng nhánh hoặc điều chỉnh ranh giới API.

Với kiểu cha mở như Object, không thể chỉ liệt kê vài case rồi kỳ vọng compiler biết hết những subtype có thể xuất hiện. Ở đó, một fallback **fail-fast có quan sát được** thường tốt hơn việc bỏ qua âm thầm.

## 8. Những giới hạn của exhaustive switch: điều gì vẫn có thể lọt lỗi?

### 8.1. Exhaustive không đồng nghĩa đúng nghiệp vụ

Compiler kiểm tra **có đường xử lý** cho mọi dạng kiểu/mẫu. Nó không biết liệu trả "IGNORED" cho Updated có đúng nhu cầu ứng dụng không. Viết một case rõ ràng như:

~~~java
case Updated(var id, var version) -> "IGNORED";
~~~

vẫn exhaustive, nhưng có thể sai về mặt nghiệp vụ. Vì vậy cần review yêu cầu và test hành vi, không chỉ nhìn kết quả biên dịch.

### 8.2. Default làm thiếu tín hiệu khi subtype mở rộng

Compiler không báo thiếu nhánh khi đã có default bao phủ subtype mới. Dù default ném exception và giúp lỗi lộ ra runtime, mã vẫn biên dịch và cần test hoặc log/alert để phát hiện vấn đề trong vận hành.

### 8.3. Null là một chiều riêng

Sealed hierarchy mô tả những subtype hợp lệ, **không biến null thành subtype**. Với switch pattern, nếu đầu vào null không được xử lý bởi case null phù hợp, nó có thể ném NullPointerException. Default thông thường không phải cách thay thế cho case null.

Khi refactor từ instanceof chain, hãy kiểm tra hành vi null cũ. Có thể chọn từ chối null (ví dụ Objects.requireNonNull) hoặc case null để giữ hành vi, nhưng phải xác định rõ thay đổi này là có chủ đích.

### 8.4. Record pattern lồng nhau có thể bỏ sót một phần subtype

Một case có dạng **Outer(Inner(var value))** không khớp khi component Inner là null. Dù tên Outer đã xuất hiện, có thể vẫn còn Outer với component null chưa được xử lý. Trong một switch expression, cần pattern bao phủ phần còn lại, ví dụ **case Outer(var inner)** nếu phù hợp với record và hợp đồng nghiệp vụ.

### 8.5. Thay đổi binary không đồng bộ

Exhaustiveness được phân tích tại **thời điểm biên dịch** dựa trên những class hiện diện. Nếu library thay đổi hierarchy sau khi consumer đã được biên dịch và các thành phần được triển khai không đồng bộ, một switch từng được coi là exhaustive có thể gặp subtype mà bytecode cũ chưa xử lý. Với pattern switch, tình huống không có nhánh khớp như vậy có thể dẫn tới **MatchException**.

Không nên hiểu rằng “không có default” tự động bảo vệ mọi thay đổi binary ở runtime. Cần biên dịch lại, kiểm thử hồi quy và triển khai các thành phần phụ thuộc nhất quán.

## 9. Phương pháp phát hiện thiếu thay đổi trong dự án thật

Một kế hoạch thực tế khi thêm subtype mới:

1. **Xác định tất cả nơi dùng kiểu cha:** tìm các switch, instanceof, phương thức dispatch, serializer, mapper, validator và test có xử lý hierarchy này.
2. **Phân biệt từng consumer:** parser, audit log, thông báo và state machine có thể cần phản ứng khác nhau với subtype mới. Không suy ra từ một consumer rằng tất cả đều bỏ qua.
3. **Tận dụng sealed và switch không default ở những nơi phù hợp:** compiler sẽ chỉ ra các nơi thiếu bao phủ khi biên dịch lại.
4. **Tìm nhánh bắt tất cả:** xem các default, case kiểu cha quá rộng, else, catch-all visitor và các logger nuốt lỗi. Chúng có thể che subtype mới.
5. **Chốt hành vi nghiệp vụ:** với mỗi consumer, quyết định xử lý subtype mới như thế nào: chuyển đổi, từ chối, ghi nhận, bỏ qua có chủ đích hoặc đặt cảnh báo.
6. **Viết test cho subtype mới:** không chỉ kiểm tra nó tạo được object, mà còn kiểm tra output và tác dụng phụ ở các consumer quan trọng.
7. **Test đường lỗi:** null, component thiếu, guard false, dữ liệu không hợp lệ và phiên bản không tương thích.
8. **Theo dõi trong vận hành:** nếu fallback là cần thiết, hãy có log/metric/cảnh báo và hành vi lỗi rõ ràng, tránh silent no-op trong đường xử lý thiết yếu.
9. **Biên dịch lại và triển khai nhất quán:** kiểm tra những module phụ thuộc vào danh sách subtype, đặc biệt khi hệ thống dùng nhiều artifact/binary khác phiên bản.

### Kiểm thử bằng ví dụ nhỏ

Một test hồi quy cho chương trình mục 4 có thể khẳng định Updated được xử lý đúng:

~~~java
// Đoạn kiểm thử minh họa, nằm trong ngữ cảnh class NewSubtypeDemo.
String actual = exhaustive(new Updated("A-3", 2));
if (!actual.equals("UPDATED:A-3@v2")) {
    throw new AssertionError("Updated must be processed");
}
~~~

Test này sẽ thất bại nếu ai đó vô tình đổi nhánh Updated thành IGNORED. Trong dự án có framework như JUnit, có thể dùng assertEquals; không cần framework để hiểu nguyên tắc.

Cũng có thể thêm test **completeness** ở tầng consumer hoặc kiểm tra danh sách subtype tùy thiết kế, nhưng test không thay thế compiler: hãy dùng cả **kiểm tra exhaustiveness ở compile time** và **assert hành vi** ở runtime.

## 10. Cách xử lý tình huống thật sự cho phép bỏ qua subtype chưa hỗ trợ

Một số hệ thống cần nhận thông điệp mở rộng từ bên ngoài và **không thể biết trước mọi loại**. Trong trường hợp đó, bỏ qua có điều kiện không hẳn là lỗi, nhưng cần được mô tả rõ:

- Nêu rõ **hợp đồng hỗ trợ phiên bản**: kiểu nào được xử lý, kiểu nào được bỏ qua hoặc từ chối.
- Có **quan sát được**: thông báo kiểu chưa biết, số lần bỏ qua, correlation ID và metric phù hợp (tránh log dữ liệu nhạy cảm).
- Tách nhánh **unsupported** khỏi lỗi dữ liệu malformed. Unknown subtype khác với một subtype được hỗ trợ nhưng nội dung không hợp lệ.
- Chọn fail-fast hay ignore theo mức độ quan trọng. Sự kiện ảnh hưởng tiền hoặc trạng thái không nên biến mất âm thầm.
- Thêm test chứng minh fallback chỉ áp dụng cho những trường hợp **được phép**, không che các subtype nằm trong hợp đồng bắt buộc.

Ví dụ với kiểu cha mở, một nhánh cuối ném exception có thông điệp rõ thường an toàn hơn trả null hoặc chuỗi rỗng. Tuy nhiên, **thiết kế error handling** còn phụ thuộc vào việc có retry, dead-letter queue, rollback hoặc cơ chế bù trừ hay không; không có một fallback phù hợp cho mọi hệ thống.

## 11. Lỗi thường gặp và cách phòng tránh nhanh

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Thêm subtype nhưng không sửa chuỗi instanceof | Subtype mới đi tới else hoặc bị bỏ qua | Tìm toàn bộ consumer, thêm test cho subtype mới |
| Luôn viết default trong sealed switch | Compiler không nhắc khi thêm subtype | Bỏ default khi cần từng nhánh tường minh và miền kiểu đóng |
| Default trả null/empty/IGNORED | Đánh mất dữ liệu, không có dấu hiệu lỗi | Chỉ ignore khi hợp đồng cho phép; log/metric nếu cần |
| Tưởng có case chứa subtype là đủ | Guard hoặc record con null để lại lỗ hổng | Kiểm tra miền khớp thực tế, thêm case bao phủ |
| Dùng case type cha quá rộng | Tự động gom subtype mới vào một hành vi chung | Dùng case cụ thể hoặc tổ chức hierarchy rõ hơn |
| Quên xử lý null khi chuyển từ if-else | Hành vi đổi thành NullPointerException | Nêu rõ hợp đồng null, thêm case null khi cần |
| Chỉ dựa vào compiler để chứng minh nghiệp vụ | Switch exhaustive nhưng kết quả vẫn sai | Có assertions/test đầu ra và side effects |
| Không biên dịch lại các consumer | Binary cũ không nhận diện subtype mới | Build/test/deploy các phụ thuộc nhất quán |
| Giữ nhánh non-sealed nhưng muốn compiler báo mọi descendant | Phân tích tĩnh không biết tất cả kiểu tương lai | Thiết kế miền đóng hơn hoặc quy định fallback/test |

## 12. Checklist review khi thêm subtype

Trước khi merge thay đổi thêm subtype mới, có thể lần lượt hỏi:

- [ ] Hierarchy này sealed, enum hay mở? Danh sách subtype/giá trị thay đổi ở đâu?
- [ ] Những switch không default đã được biên dịch lại và sửa các lỗi exhaustiveness chưa?
- [ ] Có else/default/case kiểu cha nào tự động nhận subtype mới mà không có review nghiệp vụ không?
- [ ] Nếu có guard hoặc record pattern lồng, có giá trị nào chưa được nhánh xử lý không?
- [ ] Null selector và null component có quy tắc rõ ràng không?
- [ ] Mỗi consumer quan trọng có test cho subtype mới, kết quả và side effects không?
- [ ] Có kế hoạch tương thích binary và thứ tự triển khai các module không?
- [ ] Nếu subtype mới bị bỏ qua theo chủ đích, điều đó có được ghi rõ, quan sát được và kiểm thử không?

**Kết luận:** Khi tập subtype mở rộng, **rủi ro lớn nhất không phải lỗi biên dịch mà là không có lỗi gì trong khi hành vi mới bị bỏ qua**. Sealed hierarchy kết hợp exhaustive switch không default giúp compiler biến thiếu nhánh thành lỗi sớm; test và review nghiệp vụ bảo đảm nhánh có nội dung đúng. Chỉ dùng else, default hoặc case tổng quát khi cách xử lý phần còn lại là một quyết định có chủ đích, không phải khoảng trống do quên cập nhật.