# Tài liệu hóa null behavior trong API Java Pattern Matching

**Chủ đề:** Java Core Pattern Matching — API và tài liệu. Bài sử dụng **Java 21 trở lên** cho record patterns (JEP 440) và pattern matching for switch (JEP 441); type pattern với instanceof đã chính thức từ Java 16. Mục tiêu là thiết kế, công bố và kiểm chứng **hợp đồng xử lý null** của một API, không chỉ làm cho một nhánh switch biên dịch được.

## 1. Vì sao null behavior là một phần của API contract?

Một phương thức Java có tham số thuộc kiểu tham chiếu có thể được gọi với **null** nếu không có kiểm tra nào ngăn điều đó. Người dùng API cần biết:

1. Có được truyền **null** vào phương thức không?
2. Nếu truyền null, phương thức **trả kết quả**, **trả giá trị báo vắng mặt** hay **ném ngoại lệ**?
3. Nếu tham số là một **record**, component của nó có thể null không?
4. Nếu record lồng record, việc component bên trong null có khác việc chính selector null không?
5. Phương thức có thể **trả về null** không? Nếu có, null mang ý nghĩa gì?
6. Loại ngoại lệ, điều kiện ném, thông điệp ổn định cần dựa vào và trách nhiệm của caller là gì?

Nếu không có hợp đồng rõ, hai phương thức cùng trả String nhưng có thể khiến người gọi hiểu sai: một phương thức dùng null như “không có dữ liệu”, phương thức kia coi đó là lỗi lập trình. Khi refactor từ chuỗi instanceof sang pattern switch, chính sách null có thể **đổi ngoài ý muốn**.

**Null behavior** không chỉ là cú pháp **case null**. Nó gồm **đầu vào, dữ liệu bên trong, đầu ra, ngoại lệ và hành vi được tài liệu hóa**. Đây là một yếu tố của khả năng tương thích API: thay đổi từ “nhận null và trả giá trị mặc định” sang “ném NullPointerException” có thể làm vỡ caller dù chữ ký phương thức không đổi.

## 2. Ba loại null phải phân biệt

Trong code pattern matching, có ít nhất ba tình huống cần tách biệt:

| Trường hợp | Ví dụ | Cần chú ý |
| --- | --- | --- |
| **Selector null** | **formatNullable(null)** | Giá trị đem vào switch là null; cần case null hoặc chính sách từ chối |
| **Record component null** | **new Text(null)** | Record tồn tại, nhưng component value là null |
| **Record lồng bên trong null** | **new Box(null)** | Box tồn tại, song component inner vốn được kỳ vọng là Text lại null |

Cũng cần phân biệt **Box(new Text(null))**: record Box khác null, record Text bên trong cũng khác null, nhưng giá trị String bên trong Text mới là null.

Những trường hợp này có thể dẫn đến hành vi khác nhau. Nếu API gom chúng vào một kết quả chung như “EMPTY”, tài liệu phải nói rõ phạm vi nhóm trường hợp đó. Nếu cần phân biệt ý nghĩa “không có payload”, “payload có văn bản rỗng” và “payload chứa record con vắng mặt”, nên biểu diễn chúng bằng kết quả khác nhau hoặc loại kết quả rõ nghĩa.

### 2.1. instanceof trả false khi operand null

~~~java
Object value = null;

boolean text = value instanceof String;     // false
boolean number = value instanceof Integer;  // false
~~~

Type pattern cũng không ràng buộc biến khi operand null:

~~~java
Object value = null;
if (value instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not a String");
}
~~~

Kết quả của đoạn thứ hai là **not a String**. Trường hợp null rơi vào else, không tự ném NullPointerException chỉ vì toán tử instanceof.

### 2.2. Pattern switch có quy tắc null riêng

Với pattern switch trên selector tham chiếu, nếu selector là null mà không có nhãn xử lý null phù hợp, switch thông thường ném **NullPointerException**. Một **default** thông thường không phải là thay thế cho **case null**.

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> "text";
        case null -> "missing";
        default -> "other";
    };
}
~~~

Đoạn này xử lý selector null một cách **tường minh** và trả **missing**. Nếu bỏ case null, đừng giả định default sẽ trả other cho null.

### 2.3. Record pattern có thể khớp record với component null

Một **Text(null)** là đối tượng Text hợp lệ nếu constructor không cấm null. Pattern phù hợp có thể ràng buộc component null, chẳng hạn **case Text(var value)**. Vì vậy code bên trong case phải xem value có thể null hay không theo hợp đồng record.

Với **Box(null)**, một mẫu record lồng yêu cầu phải có đối tượng Text để phân rã, như **case Box(Text(var value))**, không thể match component inner null bằng cách phân rã một Text không tồn tại. Một nhánh rộng hơn như **case Box(var inner)** có thể tiếp nhận Box còn lại.

Hãy giải thích riêng selector null và component null trong Javadoc. Chỉ ghi “null supported” là quá mơ hồ khi API dùng nhiều cấp record.

## 3. Chọn chính sách null trước khi viết code

Thông thường có ba hợp đồng khả thi:

**A. Null là một đầu vào hợp lệ, có ý nghĩa riêng.** Ví dụ service nhận một payload tùy chọn: khi không có payload, trả **NO PAYLOAD**. Tài liệu phải nói rõ giá trị đó; code dùng case null hoặc kiểm tra trước switch.

**B. Null là đầu vào không hợp lệ.** Ví dụ phương thức **requireText** yêu cầu một Payload thật. API có thể gọi **Objects.requireNonNull(payload, "payload")** để ném NullPointerException ngay ở ranh giới, trước khi xử lý subtype.

**C. Null được biến thành trạng thái nghiệp vụ có kiểu rõ.** Với API lớn, thay vì dùng null như tín hiệu “không tìm thấy”, có thể trả **Optional<T>**, một sealed result hierarchy hoặc một result object mô tả chính xác **Found / Missing / Invalid**. Cách này phù hợp khi caller cần phân biệt các lý do không có dữ liệu.

Không phải mọi API đều nên chấp nhận null. Chọn theo ý nghĩa miền và nguyên tắc thiết kế. Cách diễn đạt tốt trong tài liệu là **“tham số này có thể null; khi đó trả ...”** hoặc **“không chấp nhận null; ném ...”** — tránh các câu không kiểm chứng được như “null được xử lý an toàn”.

### Bảng quyết định

| Hợp đồng | Cách thực hiện thường rõ ràng | Điều tài liệu cần nói |
| --- | --- | --- |
| Null selector hợp lệ | **case null -> "NO PAYLOAD"** | Giá trị trả về khi selector null |
| Null selector không hợp lệ | **Objects.requireNonNull** | Loại ngoại lệ, điều kiện ném |
| Component null được xem như rỗng | **case Text(var value)** + guard hoặc kiểm tra | Phân biệt null, blank, nonblank |
| Component null vi phạm invariant | Validation trong constructor record | Record không thể được tạo với component null bằng constructor hợp lệ |
| Thiếu kết quả là trạng thái bình thường | **Optional<T>** hoặc result type | Ý nghĩa vắng mặt, có thể trả null hay không |
| Null phải được chuyển tới downstream | Chính sách rõ ở boundary và test liên quan | Downstream có chấp nhận null không, có chuyển đổi không |

**Lưu ý:** Việc bắt NullPointerException chung rồi biến thành “không có dữ liệu” là nguy hiểm: nó có thể che cả những lỗi null ngoài ý muốn bên trong logic. Hãy xử lý null **tại chỗ biết nguyên nhân**, không dựa vào catch rộng để đoán ý nghĩa.

## 4. Đưa hợp đồng vào Javadoc: @param, @return và @throws

Javadoc là nơi chính thức công bố hành vi của public API. Ba tag đặc biệt hữu ích:

- **@param:** tham số có chấp nhận null không; nếu null là hợp lệ, nó có ý nghĩa gì.
- **@return:** kết quả có bao giờ null không; giá trị sentinel hoặc kết quả rỗng tương ứng với trạng thái nào.
- **@throws:** loại exception được ném và điều kiện gây ra exception.

Ví dụ phương thức **cho phép selector null**:

~~~java
/**
 * Tạo mô tả dễ đọc cho payload.
 *
 * <p>Cho phép {@code payload == null}; khi đó trả {@code "NO PAYLOAD"}.
 * Với {@code Text} có value null, rỗng hoặc chỉ có khoảng trắng,
 * trả {@code "EMPTY TEXT"}. Với {@code Box} không có văn bản
 * không rỗng bên trong, trả {@code "EMPTY BOX"}.
 *
 * @param payload payload cần hiển thị; có thể null
 * @return chuỗi mô tả; không bao giờ null
 */
static String formatNullable(Payload payload) {
    // Body xuất hiện trong chương trình hoàn chỉnh ở mục 7.
    throw new UnsupportedOperationException("illustrative declaration");
}
~~~

**Đây là chữ ký và Javadoc minh họa**, không phải bản triển khai để ghép vào chương trình mục 7. Method thật ở mục 7 có body đầy đủ và được chạy thử.

Ví dụ phương thức **từ chối null**:

~~~java
/**
 * Lấy nguyên văn chuỗi của Text.
 *
 * @param payload phải là Text không null với value không null
 * @return chuỗi value của Text, không bao giờ null;
 *         chuỗi rỗng vẫn là kết quả hợp lệ
 * @throws NullPointerException nếu payload null hoặc Text.value null
 * @throws IllegalArgumentException nếu payload không phải Text
 */
static String requireText(Payload payload) {
    // Body xuất hiện trong chương trình hoàn chỉnh ở mục 7.
    throw new UnsupportedOperationException("illustrative declaration");
}
~~~

Hai ví dụ chỉ là **tài liệu hợp đồng**. Các câu về null, chuỗi rỗng và ngoại lệ phải khớp chính xác implementation. Không viết **@return never null** nếu có một nhánh thực sự trả null; không khai báo ngầm mọi IllegalArgumentException đều do null, vì hai loại lỗi mang ý nghĩa khác nhau.

### Có nên dựa vào thông điệp exception?

Thông điệp giúp debug, nhưng nhiều API không nên coi nội dung **getMessage()** là định dạng ổn định để caller phân tích. Hợp đồng thường chỉ cần **loại exception** và **điều kiện ném**. Nếu downstream cần mã lỗi ổn định, hãy thiết kế một enum hoặc kiểu lỗi chuyên biệt thay vì so sánh chuỗi thông điệp.

## 5. Type pattern, record pattern và null ở từng tầng

Hãy dùng mô hình dưới đây:

~~~java
sealed interface Payload permits Text, Count, Box {}

record Text(String value) implements Payload {}
record Count(int value) implements Payload {}
record Box(Text inner) implements Payload {}
~~~

**Text**, **Count** và **Box** đều là record final, còn Payload là sealed interface. Vì ba record không có compact constructor kiểm tra null, **Text(null)** và **Box(null)** có thể tạo được. Đó là lựa chọn minh họa để học về contract null; trong hệ thống thực tế có thể **cấm null ngay tại constructor**.

### Record pattern với guard

~~~java
case Text(String value) when value != null && !value.isBlank() ->
        "TEXT: " + value.trim();
case Text(var value) -> "EMPTY TEXT";
~~~

Case đầu chỉ chấp nhận value khác null, không blank. Case thứ hai không có guard, bao phủ những Text còn lại, kể cả value null. Vì vậy null của component không dẫn tới lỗi khi gọi **trim()** trong nhánh đầu: điều kiện **value != null && ...** được đánh giá ngắn mạch.

**Sai dễ gặp:** đổi toán tử **&&** thành **||** sẽ có thể gọi **isBlank()** ngay khi value null, làm guard ném NullPointerException. Guard ném exception là khác với guard trả false: lỗi sẽ lan ra chứ không tự thử case tiếp theo như một kết quả false.

### Record pattern lồng và nhánh dự phòng

~~~java
case Box(Text(String value))
        when value != null && !value.isBlank() ->
        "BOX: " + value.trim();
case Box(var inner) -> "EMPTY BOX";
~~~

Nếu Box.inner null, pattern **Box(Text(...))** không thể giải cấu trúc một Text bên trong. Nếu inner là **new Text(null)**, logic nhánh đầu cũng không sinh ra văn bản hiển thị. Nhánh **Box(var inner)** xử lý phần còn lại theo hợp đồng ví dụ.

**Kết luận ở mức pattern:** Bản thân một record bên ngoài khác null không đảm bảo mọi component của nó khác null. Dùng record patterns để trích dữ liệu; dùng invariant hoặc kiểm tra rõ để xác nhận dữ liệu có được phép null.

## 6. API từ chối null: fail fast và thông báo rõ

Giả sử phương thức chỉ chấp nhận một **Text** có component value không null:

~~~java
static String requireText(Payload payload) {
    Objects.requireNonNull(payload, "payload");
    return switch (payload) {
        case Text(var value) -> Objects.requireNonNull(value, "text.value");
        case Count c -> throw new IllegalArgumentException("expected Text");
        case Box b -> throw new IllegalArgumentException("expected Text");
    };
}
~~~

**Objects.requireNonNull(payload, "payload")** ném NullPointerException nếu selector null. Vì đã từ chối null trước switch, phần switch không cần case null để thực hiện hợp đồng này. Đây là cách **từ chối tại biên API**: người đọc thấy ngay giá trị null không được phép và có nguyên nhân cụ thể.

Nếu selector là Text nhưng value null, lần kiểm tra **Objects.requireNonNull(value, "text.value")** ném NullPointerException. Nếu selector thuộc một subtype khác, phương thức ném IllegalArgumentException với ý nghĩa “sai loại payload”.

Ba loại đầu vào được phân biệt:

1. **payload null:** thiếu đối tượng bắt buộc.
2. **Text.value null:** đối tượng tồn tại nhưng dữ liệu bên trong không hợp lệ theo contract của requireText.
3. **Count/Box:** đối tượng hợp lệ về kiểu Payload nhưng không phải Text.

Không phải mọi API cần phân tách như thế. Điểm quan trọng là **chọn một chính sách, triển khai nhất quán, ghi đúng @throws và kiểm thử**.

### Vì sao không chỉ có default?

Một **default** của switch có thể tạo hành vi dự phòng cho các subtype, nhưng không mô tả đầy đủ contract null. Với sealed Payload, việc liệt kê ba subtype giúp compiler kiểm tra exhaustiveness. Nếu sau này thêm subtype mới, một switch không default buộc người phát triển xem lại nhánh. Ngược lại, default rộng có thể âm thầm gom subtype mới vào một xử lý không phù hợp.

## 7. Chương trình Java 21 hoàn chỉnh

Ví dụ dưới đây có ba API với hợp đồng null khác nhau:

- **formatNullable(Payload)**: chấp nhận null selector, trả String không null.
- **requireText(Payload)**: từ chối null selector, từ chối Text.value null và loại Payload không phải Text.
- **hasNonblankText(Payload)**: dùng instanceof record pattern; trả boolean, trong đó null selector trả false.

Tất cả thuộc cùng file **NullBehaviorApiDemo.java**:

~~~java
import java.util.Objects;

public class NullBehaviorApiDemo {
    sealed interface Payload permits Text, Count, Box {}

    record Text(String value) implements Payload {}
    record Count(int value) implements Payload {}
    record Box(Text inner) implements Payload {}

    /**
     * Định dạng payload thành chuỗi mô tả.
     *
     * @param payload có thể null; null được xem là không có payload
     * @return chuỗi mô tả không bao giờ null; null selector cho
     *         kết quả "NO PAYLOAD"; Text với value null/blank
     *         cho "EMPTY TEXT"; Box không có văn bản hợp lệ
     *         cho "EMPTY BOX"
     */
    static String formatNullable(Payload payload) {
        return switch (payload) {
            case Text(String value) when value != null && !value.isBlank() ->
                    "TEXT: " + value.trim();
            case Text(var value) -> "EMPTY TEXT";
            case Count(int n) -> "COUNT: " + n;
            case Box(Text(String value))
                    when value != null && !value.isBlank() ->
                    "BOX: " + value.trim();
            case Box(var inner) -> "EMPTY BOX";
            case null -> "NO PAYLOAD";
        };
    }

    /**
     * Trích nguyên văn giá trị của payload dạng Text.
     *
     * @param payload bắt buộc là Text không null với value không null
     * @return Text.value, không bao giờ null; có thể là chuỗi rỗng
     * @throws NullPointerException nếu payload null hoặc Text.value null
     * @throws IllegalArgumentException nếu payload là Count hoặc Box
     */
    static String requireText(Payload payload) {
        Objects.requireNonNull(payload, "payload");
        return switch (payload) {
            case Text(var value) -> Objects.requireNonNull(value, "text.value");
            case Count c -> throw new IllegalArgumentException("expected Text");
            case Box b -> throw new IllegalArgumentException("expected Text");
        };
    }

    /**
     * Kiểm tra payload có phải Text với nội dung không blank không.
     *
     * @param payload có thể null; null trả false
     * @return true chỉ khi là Text có value khác null và không blank
     */
    static boolean hasNonblankText(Payload payload) {
        return payload instanceof Text(var value)
                && value != null && !value.isBlank();
    }

    static void printException(Payload payload) {
        try {
            System.out.println("TEXT VALUE: " + requireText(payload));
        } catch (NullPointerException | IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println(formatNullable(null));
        System.out.println(formatNullable(new Text(" hello ")));
        System.out.println(formatNullable(new Text(" ")));
        System.out.println(formatNullable(new Text(null)));
        System.out.println(formatNullable(new Count(7)));
        System.out.println(formatNullable(new Box(new Text(" nested "))));
        System.out.println(formatNullable(new Box(null)));
        System.out.println(formatNullable(new Box(new Text(null))));
        System.out.println(hasNonblankText(new Text("ok")));
        System.out.println(hasNonblankText(null));
        printException(new Text("hello"));
        printException(null);
        printException(new Text(null));
        printException(new Count(7));
    }
}
~~~

Biên dịch và chạy với **JDK 21+**:

~~~bash
javac NullBehaviorApiDemo.java
java NullBehaviorApiDemo
~~~

Kết quả chính xác:

~~~text
NO PAYLOAD
TEXT: hello
EMPTY TEXT
EMPTY TEXT
COUNT: 7
BOX: nested
EMPTY BOX
EMPTY BOX
true
false
TEXT VALUE: hello
REJECTED: payload
REJECTED: text.value
REJECTED: expected Text
~~~

### Đọc kết quả theo hợp đồng

**Dòng 1:** formatNullable(null) không ném lỗi mà trả NO PAYLOAD. Đây là một quyết định API tường minh, không phải hành vi mặc định của mọi switch.

**Dòng 2:** Text có value không blank được trim để hiển thị. Lưu ý **requireText** là API khác và cố tình trả nguyên văn chuỗi, không trim.

**Dòng 3–4:** Text(" ") và Text(null) đều được nhóm thành EMPTY TEXT theo tài liệu của formatNullable.

**Dòng 5:** Count(7) có kết quả COUNT: 7; không có ý nghĩa null trong component nguyên thủy int.

**Dòng 6–8:** Box có Text với nội dung hợp lệ trả BOX: nested; Box(null) và Box(new Text(null)) đều nhận EMPTY BOX, dù cấu trúc dữ liệu khác nhau. Nếu ứng dụng cần phân biệt chúng, phải thay hợp đồng và logic.

**Dòng 9–10:** hasNonblankText trả true cho Text("ok") và false cho null selector. Chỉ ràng buộc biến khi instanceof pattern khớp.

**Dòng 11:** requireText nhận Text("hello"), trả hello và caller in TEXT VALUE: hello.

**Dòng 12:** null selector bị Objects.requireNonNull từ chối; caller bắt NullPointerException và in REJECTED: payload.

**Dòng 13:** Text(null) bị từ chối tại component value, với thông điệp text.value.

**Dòng 14:** Count không phải Text; một exception thuộc loại IllegalArgumentException được ném theo hợp đồng.

Đây là ví dụ nhỏ tập trung vào null behavior, không yêu cầu framework nào hoặc bật preview. Mục đích của việc in exception là để **quan sát cách hoạt động**, không khuyến nghị mọi production code catch các exception ấy rồi chỉ in chuỗi; ở ứng dụng thật, ranh giới lỗi cần phù hợp tầng API, transaction và logging.

## 8. Ma trận kiểm thử null behavior

Để kiểm tra một API có thực hiện đúng Javadoc hay không, nên thiết kế bảng test ở nhiều mức, không chỉ một mẫu null.

| Lệnh thử | formatNullable | requireText | hasNonblankText |
| --- | --- | --- | --- |
| **null** | NO PAYLOAD | NPE (payload) | false |
| **new Text("ok")** | TEXT: ok | trả "ok" | true |
| **new Text("")** | EMPTY TEXT | trả "" | false |
| **new Text("   ")** | EMPTY TEXT | trả nguyên chuỗi blank | false |
| **new Text(null)** | EMPTY TEXT | NPE (text.value) | false |
| **new Count(7)** | COUNT: 7 | IAE (expected Text) | false |
| **new Box(null)** | EMPTY BOX | IAE (expected Text) | false |
| **new Box(new Text(null))** | EMPTY BOX | IAE (expected Text) | false |
| **new Box(new Text("x"))** | BOX: x | IAE (expected Text) | false |

**NPE** là NullPointerException; **IAE** là IllegalArgumentException. Bảng này mô tả hợp đồng của ba phương thức minh họa, không phải quy tắc bắt buộc cho mọi API Java.

Một bài test nên xác nhận **giá trị trả về** và **loại exception** đúng như hợp đồng. Nếu văn bản thông điệp exception không được cam kết ổn định, test không nên khóa chặt message. Với các API dùng nhiều phiên bản Java hoặc tích hợp bên ngoài, nên test thêm tương thích khi thay đổi cách biểu diễn giá trị vắng mặt.

### Kiểm tra trực tiếp không dùng framework

Trong cùng phạm vi class ví dụ, có thể viết:

~~~java
// Đoạn kiểm thử bổ sung, đặt trong cùng class NullBehaviorApiDemo.
if (!formatNullable(null).equals("NO PAYLOAD")) {
    throw new AssertionError("null selector behavior");
}
if (hasNonblankText(null)) {
    throw new AssertionError("instanceof null behavior");
}
try {
    requireText(null);
    throw new AssertionError("expected NullPointerException");
} catch (NullPointerException expected) {
    // Đúng hợp đồng: selector null không được chấp nhận.
}
~~~

Đoạn này chỉ bổ sung kiểm tra, **không được chép nguyên vào ngoài class** rồi mong tự chạy. Với JUnit, có thể dùng assertEquals, assertFalse và assertThrows để thể hiện các điều kiện tương ứng. Test thêm **new Text(null)** và **new Box(null)** để phân biệt null ở các tầng.

## 9. Null contract của model khác contract của service

Một điểm thường bị bỏ sót: Javadoc của **service method** không thể thay thế hợp đồng constructor của **record**.

Mô hình minh họa cho phép:

~~~java
new Text(null);
new Box(null);
~~~

Nếu domain quyết định Text.value phải luôn có nội dung, có thể bảo vệ ngay tại constructor:

~~~java
// Biến thể thiết kế RIÊNG, không ghép với khai báo Text ở mục 7.
record StrictText(String value) {
    StrictText {
        Objects.requireNonNull(value, "value");
        if (value.isBlank()) {
            throw new IllegalArgumentException("blank value");
        }
    }
}
~~~

Sau khi đã ràng buộc invariant tại constructor, service xử lý StrictText có thể dựa vào điều kiện non-null ấy đối với các object được tạo hợp lệ. Điều này không loại bỏ nhu cầu mô tả null selector của phương thức nhận StrictText hoặc một interface cha.

**Record không tự cấm null cho component tham chiếu.** Compact constructor là cách thể hiện invariant. Cũng cần xét collection, object mutable và dữ liệu qua serialization: không nên giả định mọi nguồn tạo giá trị đều tuân thủ domain nếu hệ thống có cơ chế dựng object đặc biệt.

Khi quyết định đặt validation tại model hay method:

- Nếu **một component null khiến bản thân record vô nghĩa ở mọi nơi**, đặt invariant trong constructor có thể đơn giản hơn.
- Nếu **record là dữ liệu thô từ bên ngoài** và các consumer có chính sách khác nhau, có thể cho phép null và để mỗi API định nghĩa rõ hợp đồng.
- Nếu một đối tượng đang qua nhiều bước validate, cân nhắc dùng các type khác nhau cho **raw input** và **validated domain value**.

## 10. Nullability annotations: có ích nhưng không thay Javadoc

Ngoài Javadoc, nhiều dự án dùng annotation như **@Nullable**, **@NonNull** hoặc **@NullMarked** tùy hệ sinh thái. Ví dụ một thư viện có thể công bố:

~~~java
// Minh họa phụ thuộc annotation từ thư viện dự án;
// không phải mã độc lập chỉ với JDK.
@Nullable
String findName(String id);
~~~

**Java SE không có một annotation @Nullable phổ quát trong java.lang mà mọi tool đều hiểu giống nhau.** Dự án cần chọn hệ annotation/tooling cụ thể (chẳng hạn JSpecify, NullAway, Checker Framework hoặc annotations do IDE/framework cung cấp) và cấu hình checker tương ứng.

Một annotation có thể giúp IDE/static analysis phát hiện cách gọi sai. Tuy nhiên:

1. Nó không tự động chèn **Objects.requireNonNull** ở runtime.
2. Không phải mọi annotation nullable đều có cùng ngữ nghĩa trong mọi framework.
3. Nếu annotation và Javadoc mâu thuẫn, caller vẫn khó hiểu và công cụ có thể phân tích khác nhau.
4. Nullability ở **type argument** (như phần tử List có thể null) khác với việc **chính List reference** có thể null.

Dùng annotation **nhất quán** với phương thức thật, Javadoc và test. Cần ghi rõ phiên bản/cấu hình thư viện hỗ trợ trong build khi onboarding người phát triển.

## 11. Null return, Optional và kiểu kết quả có cấu trúc

Hợp đồng trả về cũng quan trọng không kém đầu vào. Các kiểu kết quả phổ biến:

| Hình thức trả về | Ý nghĩa | Lưu ý tài liệu |
| --- | --- | --- |
| **T** nhưng có thể null | null là một tín hiệu được định nghĩa | Ghi rõ khi nào null; caller phải kiểm tra |
| **T không null** | Thành công luôn có giá trị | Bảo đảm mọi đường return; @throws nếu thất bại |
| **Optional<T>** | Tồn tại hoặc không tồn tại một giá trị | Không trả null thay cho Optional.empty() |
| **Result hierarchy** | Các trường hợp Success/NotFound/Invalid/Error | Mỗi subtype có ý nghĩa riêng; dùng exhaustive switch |
| **Exception** | Không hoàn tất hợp đồng bình thường | Nêu loại và điều kiện ném trong @throws |

Ví dụ API truy xuất:

~~~java
// Đoạn phác thảo, repository được khai báo ở code ứng dụng.
Optional<String> findName(String id);
~~~

Nếu lựa chọn Optional, tài liệu có thể quy định “id null gây NullPointerException; không tìm thấy trả Optional.empty()”. Không nên chuyển mọi null thành Optional.empty() nếu null thực tế là dữ liệu **không hợp lệ**. “Không tìm thấy” khác “tham số sai”, “timeout” hay “record hỏng”.

Đối với API công cộng, đổi từ **nullable String** sang **Optional<String>** là thay đổi chữ ký và thường kéo theo sửa caller; không phải luôn có thể làm mà không ảnh hưởng tương thích.

## 12. Refactor từ instanceof sang switch: đừng đổi chính sách null ngoài ý muốn

Một đoạn legacy:

~~~java
static String oldLabel(Object value) {
    if (value instanceof String s) {
        return "text:" + s;
    }
    return "other";
}
~~~

Ở đây **oldLabel(null)** trả **other**. Nếu chuyển thành:

~~~java
static String newLabel(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        default -> "other";
    };
}
~~~

thì mã mới **không bảo toàn hành vi null** của mã cũ: null selector trong pattern switch cần xử lý riêng; có thể ném NullPointerException. Muốn giữ hợp đồng cũ, viết:

~~~java
static String equivalentLabel(Object value) {
    return switch (value) {
        case String s -> "text:" + s;
        case null, default -> "other";
    };
}
~~~

Ở Java 21, nhãn **case null, default** là cú pháp cho cách xử lý chung null và các giá trị còn lại. Có thể thay bằng hai nhãn riêng với cùng kết quả nếu muốn nhấn mạnh rằng null là một quyết định tường minh.

Nếu dự án muốn **đổi sang từ chối null**, hãy ghi đó là một thay đổi API có chủ đích, cập nhật Javadoc, test và thông tin phát hành thay vì xem là refactor cú pháp thuần túy.

### Cảnh báo về thứ tự case và guard

Với pattern switch, một case tổng quát có thể làm nhánh cụ thể phía sau không tới được (**dominance**). Một guard kiểm tra null cũng có thể ném lỗi khi dùng sai toán tử. Hãy review cả:

- Selector null có đúng case?
- Component null có được kiểm tra trước khi gọi method?
- Nhánh có guard false có đường xử lý còn lại?
- Một case rộng/default có che ý nghĩa của subtype hoặc trạng thái mới?

## 13. Checklist tài liệu hóa null behavior trước khi công bố API

Khi review một API có Java Pattern Matching, dùng các câu hỏi sau:

1. **Đầu vào:** Tham số nào nullable? Null selector có hợp lệ không?
2. **Model:** Component của record nào nullable? Record lồng có thể thiếu đối tượng con không?
3. **Output:** Phương thức có thể trả null không? String rỗng có khác null không?
4. **Fallback:** Case null, default, instanceof else có hành vi được xác định rõ và thống nhất không?
5. **Exception:** Khi nào NullPointerException, IllegalArgumentException hoặc domain exception được ném?
6. **Javadoc:** @param, @return và @throws có ghi đúng các tình huống trên không?
7. **Annotation:** Hệ nullability annotation có phù hợp với cách triển khai thực tế không?
8. **Test:** Đã có test cho null selector, component null, nested null, blank, subtype hợp lệ và subtype không phù hợp chưa?
9. **Compatibility:** Nếu thay hành vi null, đã cập nhật caller, tài liệu và kiểm thử hồi quy chưa?
10. **Observability:** Với lỗi null xảy ra trong production, logging/tracing có giúp phân biệt dữ liệu thiếu chủ đích với bug mà không lộ dữ liệu nhạy cảm không?

### Những sai lầm lặp lại

- **Viết “null safe” nhưng không nói kết quả**: người gọi vẫn không biết null dẫn tới chuỗi, Optional hay exception.
- **Nhầm instanceof và switch**: instanceof null trả false, trong khi pattern switch có quy tắc null selector riêng.
- **Cho rằng default tự nhận null**: mặc định của switch không thay thế contract case null.
- **Nhầm record tồn tại với component khác null**: Text(null) và Box(null) là hai trạng thái khác biệt.
- **Catch mọi NullPointerException**: có thể che lỗi lập trình thay vì xử lý đầu vào được cho phép.
- **Dùng annotation nhưng quên runtime contract**: annotation có thể hỗ trợ phân tích tĩnh nhưng không bảo đảm exception hay fallback.
- **Gộp lỗi và vắng mặt dữ liệu**: trả null hoặc Optional.empty() cho mọi lỗi khiến caller không phân biệt được nguyên nhân.
- **Bỏ test khi refactor**: đổi if-else sang switch có thể làm thay đổi hành vi null mà compiler vẫn chấp nhận.

**Kết luận:** Tài liệu hóa null behavior là cam kết công khai về **giá trị đầu vào nào hợp lệ, giá trị nào được trả ra và ngoại lệ nào có thể xảy ra**. Với Java Pattern Matching, luôn phân biệt **selector null**, **component null** và **nested record null**; hiểu khác biệt giữa **instanceof** và **pattern switch**; viết đúng **@param**, **@return**, **@throws**; và giữ Javadoc, annotation, implementation cùng test thống nhất. Cú pháp pattern giúp code rõ hơn, nhưng chỉ một hợp đồng có chủ đích và được kiểm chứng mới giúp caller sử dụng API an toàn.