# Ghi chú khi pattern dựa trên invariant (Java 21+)

## 1. Vấn đề về tính dễ đọc: pattern khớp chưa chắc dữ liệu đã hợp lệ

**Invariant** là một điều kiện phải luôn đúng đối với một đối tượng ở những trạng thái được coi là hợp lệ của domain. Ví dụ: “Đơn hàng đã gửi phải có mã vận đơn không rỗng”, “Địa chỉ giao hàng phải có tên thành phố”, hoặc “Số lượng trong một dòng đơn hàng phải dương”.

**Pattern matching** trả lời câu hỏi khác: “Đối tượng có kiểu và cấu trúc phù hợp với mẫu này không, và có thể lấy những giá trị nào từ đó?”. Hai khái niệm hỗ trợ nhau nhưng **không thay thế nhau**:

- **Type pattern** kiểm tra đối tượng có kiểu phù hợp, đồng thời khai báo biến mẫu, chẳng hạn `value instanceof String text`.
- **Record pattern** (Java 21+) kiểm tra và phân rã một record, chẳng hạn `shipment instanceof Shipment(Address(var city, var street), var status, var id)`.
- **Guard `when` hoặc điều kiện `&&`** bổ sung quy tắc được kiểm tra tại vị trí sử dụng.
- **Invariant** được bảo vệ bởi constructor, factory, API hoặc trạng thái kiểu; compiler **không tự suy ra** mọi quy tắc nghiệp vụ chỉ từ việc một record pattern khớp.

Ví dụ, khi thấy mã:

~~~java
case Shipment(Address(var city, var street), var status, var id)
        when status == Status.SENT ->
        "sent:" + city + ":" + id.toUpperCase(java.util.Locale.ROOT);
~~~

người đọc hợp lý sẽ hỏi: **Tại sao có thể gọi `id.toUpperCase(...)` mà không kiểm tra `id != null`?** Câu trả lời đúng phải nằm ở một invariant đã được thực thi và có thể kiểm chứng, không phải ở giả định “vì record pattern đã khớp”.

Ghi chú hữu ích nhất ở đây giải thích **điều kiện ẩn mà code đang dựa vào, nơi bảo vệ điều kiện đó và lý do code được phép bỏ một guard**. Ghi chú chỉ nói “xử lý đơn đã gửi” không giải thích điểm rủi ro.

## 2. Tình huống domain: lô hàng và mã vận đơn

Xây dựng mô hình nhỏ gồm:

~~~java
enum Status { DRAFT, READY, SENT }

record Address(String city, String street) {}

record Shipment(Address destination, Status status, String trackingId) {}
~~~

Trong ví dụ này, chúng ta đặt ra bốn quy tắc:

1. `Address.city` và `Address.street` phải khác `null` và không chỉ chứa khoảng trắng.
2. `Shipment.destination` phải khác `null`.
3. `Shipment.status` phải khác `null`.
4. Nếu `Shipment.status == Status.SENT` thì `trackingId` **phải khác `null` và không trắng**. Với các trạng thái còn lại, `trackingId` có thể bằng `null`; nếu có giá trị thì không được trắng.

Đây là **hợp đồng nghiệp vụ của ví dụ**, không phải tính chất mặc định của Java record. Khai báo record ban đầu ở trên **chưa thực thi** các quy tắc ấy; các giá trị như `new Shipment(null, Status.SENT, null)` vẫn có thể được tạo nếu không bổ sung validation.

Một pattern:

~~~java
input instanceof Shipment(Address(var city, var street),
                          var status, var id)
~~~

chỉ xác nhận kiểu và hình dạng record cần phân rã. Pattern không tự xác nhận rằng `city` không trắng hoặc rằng `status == SENT` đòi `id != null`. Do đó, muốn code xử lý dựa trên invariant, trước tiên phải **hiện thực invariant trong mô hình**.

## 3. Đặt nơi bảo đảm invariant ở constructor

Với record, **compact constructor** là nơi tự nhiên để kiểm tra đầu vào trước khi component được khởi tạo.

~~~java
record Address(String city, String street) {
    Address {
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city");
        }
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("street");
        }
    }
}

record Shipment(Address destination, Status status, String trackingId) {
    Shipment {
        if (destination == null) {
            throw new IllegalArgumentException("destination");
        }
        if (status == null) {
            throw new IllegalArgumentException("status");
        }
        if (trackingId != null && trackingId.isBlank()) {
            throw new IllegalArgumentException("trackingId blank");
        }
        if (status == Status.SENT && trackingId == null) {
            throw new IllegalArgumentException("SENT requires trackingId");
        }
    }
}
~~~

Đây là các **khai báo minh họa** trong cùng một phạm vi có `enum Status`. Chương trình độc lập đầy đủ ở mục 9.

Compact constructor kiểm tra các tham số trước khi Java gán chúng vào các component của record. Nhờ đó, những lời gọi constructor bình thường phải tuân theo quy tắc domain:

| Dữ liệu | Kết quả | Vì sao? |
| --- | --- | --- |
| `new Address("Ha Noi", "Pho Hue")` | Hợp lệ | Hai chuỗi khác null và không trắng |
| `new Address(null, "Pho Hue")` | Ném `IllegalArgumentException` | Thiếu thành phố |
| `new Shipment(address, DRAFT, null)` | Hợp lệ | Chưa gửi hàng không bắt buộc có mã |
| `new Shipment(address, READY, null)` | Hợp lệ | Trạng thái READY trong ví dụ chưa bắt buộc mã |
| `new Shipment(address, SENT, "tk-7")` | Hợp lệ | Đã gửi và mã không trắng |
| `new Shipment(address, SENT, null)` | Ném `IllegalArgumentException` | Vi phạm ràng buộc giữa status và trackingId |
| `new Shipment(address, SENT, "  ")` | Ném `IllegalArgumentException` | Mã vận đơn trắng |
| `new Shipment(null, DRAFT, null)` | Ném `IllegalArgumentException` | Thiếu địa chỉ |

**Hai cấp độ bảo đảm khác nhau:** compiler biết `trackingId` có kiểu `String`, nhưng không biết rằng nó khác null khi `status == SENT`. Điều kiện sau là **invariant runtime** do constructor thực thi. Vì record component là `final`, mã Java thông thường không thể thay đổi trực tiếp component sau khi tạo; tuy nhiên record chỉ bất biến *nông*, nên nếu component là đối tượng mutable, cần thiết kế thêm để giữ invariant trong suốt vòng đời.

## 4. Ghi chú tốt: nêu “vì sao an toàn” và “được bảo đảm ở đâu”

Sau khi các constructor đã bảo vệ invariant, ta có thể viết:

~~~java
static String describe(Object input) {
    return switch (input) {
        // Invariant: Shipment(status == SENT) có trackingId khác null,
        // không trắng. Được kiểm tra trong Shipment constructor.
        // Address constructor cũng bảo đảm city khác null và không trắng.
        case Shipment(Address(var city, var street), var status, var id)
                when status == Status.SENT ->
                "sent:" + city + ":"
                        + id.toUpperCase(java.util.Locale.ROOT);

        case Shipment(Address(var city, var street), var status, var id) ->
                "pending:" + city + ":" + status;

        case null -> "null";
        default -> "unsupported";
    };
}
~~~

Đây là phương thức minh họa sử dụng `Status`, `Address`, `Shipment` đã được định nghĩa và validation ở trên. Chương trình ở mục 9 chứa cùng phương thức.

Phân tích nhánh đầu:

- `Shipment(Address(...), ...)` kiểm tra kiểu record ngoài và phân rã record `Address` lồng bên trong.
- `var status`, `var id` khai báo các biến có kiểu tĩnh được suy ra từ component, lần lượt là `Status` và `String`.
- `when status == Status.SENT` là điều kiện **thực sự được kiểm tra** khi chọn nhánh.
- Việc `id != null` và `!id.isBlank()` **không được guard này trực tiếp kiểm tra**; nó được dựa trên invariant của `Shipment constructor`.
- Việc `city` không null và không trắng được dựa trên validation của `Address constructor`.

Đây là khác biệt giữa **bảo đảm của compiler** và **bảo đảm của domain**. Người đọc không nên hiểu lầm rằng record pattern hay guard `when` đã tự tạo mọi bảo đảm đó.

### Ghi chú nào thực sự có giá trị?

**Ghi chú yếu:**

~~~java
// Lấy thông tin lô hàng, gọi toUpperCase rồi trả chuỗi.
case Shipment(Address(var city, var street), var status, var id)
        when status == Status.SENT ->
        id.toUpperCase(java.util.Locale.ROOT);
~~~

Nó lặp lại những gì code đã thể hiện nhưng không giải thích vì sao lời gọi trên `id` an toàn.

**Ghi chú có ích:**

~~~java
// Shipment constructor bảo đảm: status == SENT => trackingId != null.
// Nếu sửa điều kiện trong constructor, phải kiểm tra lại nhánh này.
case Shipment(Address(var city, var street), var status, var id)
        when status == Status.SENT ->
        id.toUpperCase(java.util.Locale.ROOT);
~~~

Ghi chú thứ hai nêu được **phụ thuộc giữa nơi định nghĩa invariant và nơi sử dụng**. Có thể đưa invariant thành Javadoc ở model để người đọc tìm thấy hợp đồng ngay tại nơi khai báo, rồi dùng một comment ngắn ở nhánh có thao tác dễ gây lỗi.

## 5. Khi nào nên giữ guard thay vì chỉ ghi chú?

Không phải invariant nào cũng đáng để bỏ điều kiện kiểm tra cục bộ.

### Trường hợp A: invariant được kiểm soát chặt và code nội bộ

Nếu tất cả `Shipment` được tạo qua constructor có validation, việc dùng `id.toUpperCase(...)` trong nhánh `status == SENT` có cơ sở. Một comment ngắn chỉ vào constructor và kiểm thử invariant thường đủ để giải thích việc không cần kiểm tra null ngay tại chỗ.

### Trường hợp B: dữ liệu chưa được xác thực ở biên hệ thống

Ví dụ xử lý JSON, thông điệp từ queue hoặc dữ liệu cũ: trước khi xem nó là `Shipment` hợp lệ, mã chuyển đổi phải kiểm tra/chuẩn hóa dữ liệu theo hợp đồng. Không nên ghi chú “trackingId luôn có” trên một cấu trúc dữ liệu thô nếu không có nơi bảo đảm điều đó.

~~~java
// Dữ liệu thô/chưa xác thực: kiểm tra trước khi dùng.
static String safeRawLabel(String id, Status status) {
    if (status == Status.SENT && (id == null || id.isBlank())) {
        return "invalid sent shipment";
    }
    return status == Status.SENT
            ? id.toUpperCase(java.util.Locale.ROOT)
            : "not sent";
}
~~~

Đây là **phương thức minh họa**; nếu `status` có thể null, hàm hiện tại coi null là “not sent”. Trong ứng dụng thực tế, có thể cần trả lỗi riêng cho status null tùy hợp đồng API.

Nguyên tắc: **validate một lần ở ranh giới tin cậy**, rồi làm việc bằng domain object hợp lệ. Không nên tạo đối tượng domain chưa được xác thực, dựa vào comment, và hy vọng mọi nơi gọi đều nhớ kiểm tra.

### Trường hợp C: invariant có nhiều điều kiện hoặc có thể thay đổi

Nếu quy tắc là “mã vận đơn bắt buộc khi status là SENT **và** loại vận chuyển là DELIVERY”, việc ghi ngắn “SENT luôn có mã” sẽ **sai**. Comment phải diễn đạt đầy đủ tiền đề, hoặc code nên có một hàm có tên như `requiresTrackingId()` để tập trung quy tắc. Khi luật thay đổi, cập nhật validation, comment và test cùng nhau.

Một comment không phải là cơ chế thực thi. Nếu invariant bị mất do thay đổi mô hình mà comment còn nguyên, comment ấy trở thành **nguồn gây hiểu lầm**.

## 6. Vấn đề tinh tế: component pattern không tự chứng minh khác `null`

Đây là lý do cần cẩn thận đặc biệt với việc ghi chú dựa trên invariant.

~~~java
record RawShipment(String trackingId, Status status) {}

Object raw = new RawShipment(null, Status.SENT);

if (raw instanceof RawShipment(String id, var state)) {
    System.out.println(id == null); // true trên Java 21
}
~~~

Dù `String id` là một type pattern, ở vị trí **record component** có kiểu tĩnh đã là `String`, nó có thể là **unconditional pattern** và khớp cả component `null`. Khác với biểu thức `someObject instanceof String text` trực tiếp, nơi giá trị ngoài cùng `null` làm `instanceof` trả về `false`.

Vì vậy, ngay cả khi mã dùng `RawShipment(String id, ...)`, **đừng tự kết luận** rằng `id.toUpperCase()` luôn an toàn.

So sánh:

| Cách viết | Có suy ra `id != null` không? | Tại sao? |
| --- | --- | --- |
| `Object obj = null; obj instanceof String id` | Không; phép khớp thất bại | `instanceof` bên ngoài không khớp null |
| `RawShipment(String id, ...)` với component `String` | Không | Component pattern unconditional có thể nhận null |
| `RawShipment(var id, ...)` | Không | `var` chỉ suy luận kiểu tĩnh của component |
| `Shipment(..., var id) when status == SENT` | Có theo **hợp đồng domain đã bảo vệ**, không phải bởi pattern | Constructor `Shipment` từ chối trạng thái SENT thiếu mã |
| `id != null && !id.isBlank()` | Có trên nhánh điều kiện đúng | Guard thực sự kiểm tra giá trị |

Khi review, nếu thấy lời gọi phương thức lên biến record component mà không có kiểm tra null, hãy tìm **nguồn của invariant**. Không tìm thấy thì cần thêm validation hoặc guard, không chỉ thêm một comment “chắc chắn không null”.

## 7. Một comment hợp đồng cần ghi những gì?

Không cần viết cả bài văn bên cạnh mỗi pattern. Với logic dựa trên invariant, chỉ ghi chú khi người đọc **không thể suy ra bảo đảm an toàn từ vài dòng đang thấy**.

Một comment ngắn thường nên trả lời đủ ba ý:

1. **Điều kiện:** invariant chính xác là gì? Ví dụ: `status == SENT => trackingId != null && !trackingId.isBlank()`.
2. **Nguồn bảo đảm:** được bảo vệ ở đâu? Ví dụ: `Shipment` compact constructor; hoặc factory, validation layer đáng tin cậy có test.
3. **Hệ quả phụ thuộc:** nhánh pattern nào dựa vào nó, và thay đổi gì có thể làm code không còn an toàn?

Ví dụ đặt ở model:

~~~java
/**
 * Domain invariant: destination != null, status != null;
 * status == SENT => trackingId != null && !trackingId.isBlank().
 * Enforced in the compact constructor.
 */
record Shipment(Address destination, Status status, String trackingId) {
    // Constructor validation ở mục 3.
}
~~~

Đoạn Javadoc này là **minh họa tài liệu**; không có phần thân validation thực tế nên **không được xem là một class chạy độc lập có bảo vệ invariant**. Bản đầy đủ với constructor và kiểm thử nằm ở mục 9.

Ở nơi tiêu thụ, tránh lặp toàn bộ Javadoc nếu hợp đồng đã rõ. Chỉ comment tại điểm rủi ro đáng chú ý:

~~~java
// Hợp đồng Shipment: SENT luôn có trackingId; xem compact constructor.
case Shipment(var address, var status, var id)
        when status == Status.SENT -> id.toUpperCase(java.util.Locale.ROOT);
~~~

**Comment không nên nhắc lại cú pháp** như “pattern tách 3 trường” nếu việc ấy đã hiển nhiên. Hãy ưu tiên giải thích **lý do loại bỏ kiểm tra**, **ràng buộc xuyên nhiều field** hoặc **giả định không nhìn thấy ở vị trí đọc**.

## 8. Khi invariant phức tạp: cân nhắc chuyển thành kiểu

Nếu invariant “trạng thái SENT phải có mã vận đơn” xuất hiện trong nhiều nơi, việc liên tục kiểm tra `status` và dựa vào `trackingId` có thể là dấu hiệu mô hình chưa tối ưu. Có thể mô hình hóa trạng thái khác nhau bằng subtype:

~~~java
sealed interface ShipmentState
        permits DraftState, ReadyState, SentState {}

record DraftState() implements ShipmentState {}
record ReadyState() implements ShipmentState {}
record SentState(String trackingId) implements ShipmentState {
    SentState {
        if (trackingId == null || trackingId.isBlank()) {
            throw new IllegalArgumentException("trackingId");
        }
    }
}
~~~

Đây là **mô hình thay thế minh họa**: nó đưa payload `trackingId` vào riêng trạng thái `SentState`. Nhờ đó, quy tắc “chỉ trạng thái đã gửi mới có mã bắt buộc” được thể hiện gần hơn với **cấu trúc kiểu**, không còn dựa hoàn toàn vào quan hệ giữa enum và một field nullable của record lớn.

Nhưng subtype không tự bảo đảm mọi invariant về nội dung (ví dụ mã không trắng); constructor vẫn phải kiểm tra. Một kiểu sealed phù hợp nếu các trạng thái có payload/hành vi khác nhau rõ rệt, còn enum cộng validation có thể đơn giản hơn nếu mô hình nhỏ và ổn định. **Không đổi thiết kế chỉ để bỏ comment**; đổi khi giúp domain rõ và khó tạo trạng thái sai hơn.

## 9. Chương trình Java 21 hoàn chỉnh với 14 ca kiểm thử

Tạo tệp **`InvariantPatternDemo.java`**:

~~~java
public class InvariantPatternDemo {
    enum Status { DRAFT, READY, SENT }

    record Address(String city, String street) {
        Address {
            if (city == null || city.isBlank()) {
                throw new IllegalArgumentException("city");
            }
            if (street == null || street.isBlank()) {
                throw new IllegalArgumentException("street");
            }
        }
    }

    record Shipment(Address destination, Status status, String trackingId) {
        Shipment {
            if (destination == null) {
                throw new IllegalArgumentException("destination");
            }
            if (status == null) {
                throw new IllegalArgumentException("status");
            }
            if (trackingId != null && trackingId.isBlank()) {
                throw new IllegalArgumentException("trackingId blank");
            }
            if (status == Status.SENT && trackingId == null) {
                throw new IllegalArgumentException(
                        "SENT requires trackingId");
            }
        }
    }

    // Không bảo vệ invariant: cố tình dùng để minh họa rủi ro.
    record RawShipment(String trackingId, Status status) {}

    static String describe(Object input) {
        return switch (input) {
            // Hợp đồng Shipment: SENT => trackingId khác null, không trắng.
            // Address bảo đảm city khác null, không trắng.
            // Cả hai được kiểm tra trong compact constructor tương ứng.
            case Shipment(Address(var city, var street), var status, var id)
                    when status == Status.SENT ->
                    "sent:" + city + ":"
                            + id.toUpperCase(java.util.Locale.ROOT);

            case Shipment(Address(var city, var street), var status, var id) ->
                    "pending:" + city + ":" + status;

            case null -> "null";
            default -> "unsupported";
        };
    }

    private static int passed = 0;

    static void check(String name, boolean condition) {
        if (!condition) {
            throw new AssertionError(name);
        }
        ++passed;
        System.out.println("PASS " + name);
    }

    static void expectInvalid(String name, Runnable factory) {
        try {
            factory.run();
            throw new AssertionError("Expected invalid: " + name);
        } catch (IllegalArgumentException expected) {
            check(name, true);
        }
    }

    public static void main(String[] args) {
        Address address = new Address("Ha Noi", "Pho Hue");

        check("sent", describe(
                new Shipment(address, Status.SENT, "tk-7"))
                .equals("sent:Ha Noi:TK-7"));

        check("ready", describe(
                new Shipment(address, Status.READY, null))
                .equals("pending:Ha Noi:READY"));

        check("draft", describe(
                new Shipment(address, Status.DRAFT, null))
                .equals("pending:Ha Noi:DRAFT"));

        check("null-input", describe(null).equals("null"));
        check("other-input", describe("other").equals("unsupported"));

        expectInvalid("null-city",
                () -> new Address(null, "Pho Hue"));
        expectInvalid("blank-city",
                () -> new Address(" ", "Pho Hue"));
        expectInvalid("blank-street",
                () -> new Address("Ha Noi", " "));
        expectInvalid("null-address",
                () -> new Shipment(null, Status.DRAFT, null));
        expectInvalid("null-status",
                () -> new Shipment(address, null, null));
        expectInvalid("sent-without-id",
                () -> new Shipment(address, Status.SENT, null));
        expectInvalid("blank-id",
                () -> new Shipment(address, Status.SENT, " "));

        Object raw = new RawShipment(null, Status.SENT);
        check("raw-null-component",
                raw instanceof RawShipment(String id, var status)
                        && id == null && status == Status.SENT);

        check("record-value-equality",
                new Address("Ha Noi", "Pho Hue").equals(address));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Biên dịch/chạy bằng **JDK 21 trở lên**:

~~~bash
javac --release 21 InvariantPatternDemo.java
java InvariantPatternDemo
~~~

Kết quả:

~~~text
PASS sent
PASS ready
PASS draft
PASS null-input
PASS other-input
PASS null-city
PASS blank-city
PASS blank-street
PASS null-address
PASS null-status
PASS sent-without-id
PASS blank-id
PASS raw-null-component
PASS record-value-equality
ALL PASSED: 14
~~~

### Giải thích kết quả quan trọng

- **`sent`:** `when status == SENT` chọn nhánh và `id.toUpperCase(...)` an toàn vì constructor từ chối mã vận đơn null/trắng ở trạng thái SENT.
- **`ready`, `draft`:** `trackingId == null` hợp lệ với hai trạng thái đó. Nhánh `pending` không dereference `id`.
- **`null-input`, `other-input`:** pattern nhận đầu vào kiểu `Object`, xử lý selector null và kiểu khác rõ ràng.
- **Bảy ca `expectInvalid`:** chứng minh những invariant quan trọng được thực thi tại lúc tạo đối tượng, không chỉ được mô tả trong comment.
- **`raw-null-component`:** `RawShipment` không có validation; dù dùng component pattern `String id`, `id` vẫn có thể bằng null. Đây là đối chứng lý giải vì sao pattern **không thay thế** invariant.
- **`record-value-equality`:** hai value object `Address` chứa cùng giá trị bằng nhau theo `equals` mà record tự cung cấp.

Hàm `check` ném `AssertionError` nếu kết quả sai; chương trình chỉ in `ALL PASSED: 14` khi mọi phép kiểm tra đều đạt. Phương thức `expectInvalid` cũng yêu cầu constructor phải thực sự từ chối dữ liệu sai. Các đoạn cố ý rút gọn/giải thích ở mục trước không phải chương trình độc lập và không cần chép vào tệp này.

## 10. Kiểm thử để comment không trở nên lỗi thời

Một invariant có giá trị thực tế khi được bảo vệ bằng code và **kiểm thử hồi quy**. Nên có ít nhất:

| Nhóm kiểm thử | Ví dụ | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ có điều kiện | `SENT` với trackingId `"tk-7"` | Tạo được object; nhánh `sent` dùng mã an toàn |
| Hợp lệ không cần field | `DRAFT` với trackingId `null` | Tạo được object; không gọi method trên mã |
| Vi phạm quan hệ giữa field | `SENT` với trackingId `null` | Constructor từ chối |
| Vi phạm nội dung field | `SENT` với trackingId chỉ toàn khoảng trắng | Constructor từ chối |
| Vi phạm component lồng | Address có city null/trắng | Constructor `Address` từ chối |
| Giá trị ngoài cùng null | `describe(null)` | Chọn nhánh `case null` |
| Record thô không có invariant | `RawShipment(null, SENT)` | Component pattern có thể vẫn khớp; không được dereference null |
| Phạm vi biến/guard | `when status == SENT` | Chỉ nhánh cần invariant mới gọi `id.toUpperCase(...)` |

Đặc biệt, khi sửa một constructor, hãy tìm những nơi có comment “theo invariant X” và kiểm tra lại cách chúng sử dụng biến từ record pattern. Không đủ để chỉ chạy ca “happy path”; test âm của invariant mới cho thấy nguồn bảo đảm vẫn tồn tại.

Nếu dùng JUnit trong dự án, có thể chuyển `expectInvalid` sang `assertThrows(IllegalArgumentException.class, ...)`, nhưng ví dụ trong bài cố tình chỉ dùng JDK thuần để có thể chạy ngay.

## 11. Các lỗi thường gặp khi viết comment cho pattern

**Lỗi 1 — comment khẳng định điều code chưa thực thi.** Viết “trackingId không thể null” trong khi record không có validation khiến người đọc tưởng có bảo đảm. Hãy bổ sung constructor/factory trước, rồi ghi chú nơi thực thi quy tắc.

**Lỗi 2 — comment chỉ mô tả thao tác hiển nhiên.** “Dùng switch để phân nhánh” không cung cấp thông tin mà cú pháp chưa thể hiện. Nên giải thích giả định quan trọng hoặc lý do bỏ guard.

**Lỗi 3 — xem record pattern là bộ xác thực nghiệp vụ.** Pattern lấy giá trị theo cấu trúc; nó không tự kiểm tra độ dài chuỗi, số tiền dương hay quan hệ giữa status và trackingId.

**Lỗi 4 — nghĩ pattern component có kiểu `String` luôn loại null.** Một component pattern unconditional có thể nhận null, như ca `RawShipment(String id, ...)` trên Java 21. Kiểm tra thực tế hoặc dựa vào invariant đã bảo vệ, không suy luận từ tên kiểu.

**Lỗi 5 — invariant chỉ đúng ở một nguồn dữ liệu nhưng áp dụng cho mọi nguồn.** Khi chuyển dữ liệu từ DTO, database hoặc message vào domain model, phải xác định điểm xác thực trước khi cho logic pattern dựa vào invariant.

**Lỗi 6 — comment không cập nhật khi điều kiện thay đổi.** Khi đổi `SENT` thành `SENT || READY`, comment, constructor, nhánh `when` và test phải được rà soát cùng nhau. Comment sai còn nguy hiểm hơn không có comment.

**Lỗi 7 — bỏ qua mutable component.** Record bất biến nông: nếu field trỏ tới một collection/object có thể sửa, invariant về nội dung có thể bị phá sau khi constructor chạy. Dùng defensive copy, immutable value object hoặc validation phù hợp.

**Lỗi 8 — thay mọi guard bằng comment để “code gọn”.** Ở biên dữ liệu không đáng tin cậy, guard hoặc validation vẫn phải hoạt động. Comment không chặn `NullPointerException` hay dữ liệu sai.

**Lỗi 9 — nhiều comment lặp ở mọi nhánh.** Đặt hợp đồng ở model và chỉ nhắc ngắn tại các vị trí rủi ro cần hiểu. Nếu cùng quy tắc xuất hiện quá nhiều chỗ, cân nhắc đặt một helper có tên rõ hoặc cải thiện cấu trúc domain.

## 12. Checklist review về tính dễ đọc

Trước khi chấp nhận một pattern đang dựa trên invariant, hãy tự hỏi:

1. **Điều kiện nào được compiler bảo đảm?** Đúng kiểu, đúng cấu trúc, phạm vi biến mẫu, tính exhaustive của `switch`?
2. **Điều kiện nào chỉ được domain bảo đảm?** Chuỗi không trắng, số dương, quan hệ giữa nhiều field, thứ tự trạng thái?
3. **Invariant được thực thi ở đâu?** Constructor, factory hay validation tại boundary? Có test âm không?
4. **Comment có nêu đúng tiền đề và nguồn bảo đảm không?** Có cách nhanh để lần tới nơi kiểm tra không?
5. **Nếu bỏ invariant, chỗ dùng pattern sẽ hỏng thế nào?** `NullPointerException`, dữ liệu sai, sai nhánh, thiếu thông tin?
6. **Có thể biểu diễn invariant tốt hơn bằng kiểu không?** Ví dụ subtype có payload bắt buộc thay vì enum cộng nullable field.
7. **Đã xét `null` cả ở selector và record component chưa?** Hai vị trí không luôn có cùng ngữ nghĩa khớp.
8. **Có phụ thuộc vào dữ liệu mutable hoặc nguồn chưa được xác thực không?** Nếu có, cần điểm kiểm tra khác.
9. **Khi thay đổi invariant, test và comment liên quan có được cập nhật không?**

### Bài tập

- Sửa `Shipment` để `Status.READY` cũng bắt buộc có trackingId. Hãy cập nhật validation, test và comment, rồi xem nhánh pattern nào dựa trên quy tắc mới.
- Thay `Address` bằng một record không có validation. Dự đoán chương trình sẽ xử lý thế nào khi `city == null` và chỉ ra nơi cần bảo vệ nếu code muốn gọi `city.toUpperCase()`.
- Tạo thêm `Status.CANCELLED`, yêu cầu trạng thái này **không được** có trackingId. Biểu diễn ràng buộc bằng constructor và kiểm thử hai chiều: null hợp lệ, mã khác null không hợp lệ.
- So sánh mô hình `Shipment(status, trackingId)` với `sealed ShipmentState`/`SentState(trackingId)`: mô hình nào giúp giảm các giả định ẩn trong code xử lý?

**Ghi nhớ:** Khi một pattern dựa vào invariant, comment tốt không giải thích lại cú pháp pattern mà chỉ rõ **bảo đảm ngầm**, **nguồn thực thi bảo đảm** và **đường code phụ thuộc vào nó**. Compiler kiểm tra kiểu và phạm vi biến mẫu; constructor/validation bảo vệ tính hợp lệ của domain. Cách viết dễ đọc và an toàn nhất làm rõ ranh giới giữa hai loại bảo đảm này, đồng thời giữ test để comment luôn phản ánh đúng hành vi.