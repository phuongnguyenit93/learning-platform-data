# Xử lý component null trong Java record patterns

**Chủ đề:** Java Core Pattern Matching — Case study record. Bài tập trung vào sự khác biệt giữa **record object null**, **component null** và **record con null** khi dùng record patterns trong **Java 21 trở lên**. Record patterns (JEP 440) và pattern matching for switch (JEP 441) là tính năng chính thức từ Java 21, không cần bật preview.

## 1. Tại sao component null là một lỗi dễ bị bỏ qua?

Record giúp khai báo dữ liệu gọn:

~~~java
record Address(String city) {}
record Profile(String name, Address address) {}
~~~

Nhưng cú pháp trên **không tự cấm null**. Các lời gọi sau đều hợp lệ với model chưa có validation:

~~~java
new Address(null);
new Profile(null, new Address("Hue"));
new Profile("Lan", null);
~~~

Nhiều người suy luận rằng một record đã được tạo thì mọi component đều có giá trị, hoặc một record pattern khớp nghĩa là các component khác null. Cả hai suy luận đều không đủ cơ sở.

Trong ứng dụng, điều này có thể gây ra ba nhóm lỗi:

1. **NullPointerException:** body gọi method trên một biến được trích từ component nhưng biến đó bằng null.
2. **Thiếu nhánh:** một record pattern lồng yêu cầu record con tồn tại; khi component con null, pattern không khớp, và logic không có nhánh xử lý phù hợp.
3. **Sai nghiệp vụ:** phần mềm xem “thiếu hồ sơ”, “thiếu địa chỉ” và “tên rỗng” là một trạng thái dù chúng có ý nghĩa khác nhau.

Một cách xử lý tốt cần trả lời: **component nào được phép null, null có nghĩa gì, kiểm tra ở đâu, và API phải phản ứng thế nào?**

## 2. Phân biệt bốn tình huống null

Giả sử ta có:

~~~java
record Address(String city) {}
record Profile(String name, Address address) {}
record UserJoined(Profile profile) {}
~~~

Bốn tình huống sau khác nhau:

| Đầu vào | Giá trị null nằm ở đâu? | Hệ quả |
| --- | --- | --- |
| **null** | Toàn bộ selector hoặc bản thân record | Không có đối tượng để deconstruct |
| **new UserJoined(null)** | Component profile của UserJoined | UserJoined vẫn tồn tại, Profile không tồn tại |
| **new UserJoined(new Profile("Lan", null))** | Component address trong Profile | Profile tồn tại, Address không tồn tại |
| **new UserJoined(new Profile("Lan", new Address(null)))** | Component city của Address | Cả ba record tồn tại, String city null |

**case null** của switch chỉ nói về **selector null**, không tự bắt record với một component null. Một component null cần được xem xét tại đúng tầng: dùng pattern phù hợp, guard, kiểm tra trong body hoặc invariant của constructor.

Nếu component có kiểu nguyên thủy như **int**, **long**, **double**, bản thân component không thể lưu null. Nhưng **double** vẫn có thể chứa NaN hoặc Infinity; validation dữ liệu số là vấn đề riêng, không được giải quyết bằng null check.

## 3. Record pattern hoạt động như thế nào?

Một record pattern dùng hình dạng record để lấy các component:

~~~java
// Chỉ là đoạn nhánh minh họa trong switch trên Event.
case UserJoined(Profile(var name, Address(var city))) ->
        "JOINED: " + name + " @ " + city;
~~~

Ở đây:

1. **UserJoined(...)** yêu cầu selector là UserJoined.
2. **Profile(...)** yêu cầu component profile là một Profile để tiếp tục deconstruct.
3. **var name** ràng buộc component name của Profile.
4. **Address(...)** yêu cầu component address là một Address.
5. **var city** ràng buộc component city của Address.

Nếu **profile null** hoặc **address null**, mẫu record lồng tương ứng **không khớp**. Nếu profile và address đều tồn tại nhưng **name hoặc city null**, các biến ràng buộc bằng **var** vẫn có thể nhận giá trị null.

Vì vậy ví dụ trên **không an toàn** nếu body tiếp tục gọi **name.trim()** hoặc **city.trim()** mà không kiểm tra. Việc match theo cấu trúc không tự chứng minh component String có nội dung hợp lệ.

### 3.1. Ràng buộc var không có nghĩa là non-null

~~~java
record Box(String value) {}

// Đoạn minh họa khi box thực sự là Box:
Box box = new Box(null);
String value = box.value();  // null
~~~

Pattern **Box(var text)** có thể ràng buộc biến text với null. Cũng đừng gắn **var** với việc tạo bản sao; nó là một kiểu pattern cho phép suy ra kiểu của component và lưu giá trị ràng buộc vào biến.

### 3.2. Một trường hợp tinh tế: type pattern của component cũng có thể khớp null

Không nên ghi quy tắc “mọi type pattern đều từ chối null” rồi áp dụng nguyên xi cho **record component**. Với component đã khai báo kiểu String, một pattern **không điều kiện** cho component có thể ràng buộc cả null.

Ví dụ độc lập nhỏ trong ngữ cảnh Java 21:

~~~java
record Box(String value) {}

Object raw = new Box(null);

String result = switch (raw) {
    case Box(String text) -> "TYPED:" + text;
    default -> "OTHER";
};

System.out.println(result);
~~~

Đầu ra:

~~~text
TYPED:null
~~~

Ở đây type pattern **String text** nằm **bên trong record pattern của Box**, và có thể ràng buộc component String null. Đó là điểm khác với phép kiểm tra thông thường:

~~~java
Object raw = null;
System.out.println(raw instanceof String text);
~~~

Đầu ra của phép **instanceof** trên null là **false**. Record deconstruction có các quy tắc matching và unconditional pattern riêng, nên cần hiểu ngữ cảnh pattern thay vì suy luận từ một ví dụ instanceof đơn giản.

**Đặc biệt:** Đặt **case Box(String text)** trước **case Box(var text)** trong cùng switch có thể khiến nhánh sau bị **dominated**, vì mẫu đầu đã bao phủ toàn bộ Box theo cấu trúc component String ấy. Đừng cố dùng case Box(String text) để tách “nonnull” khỏi “null”; dùng **guard** hoặc kiểm tra tường minh khi cần phân biệt giá trị.

### 3.3. Mẫu record lồng khác với mẫu component String

Với:

~~~java
record Address(String city) {}
record Profile(String name, Address address) {}
~~~

**Profile(var name, var address)** có thể match Profile với address null. Nhưng **Profile(var name, Address(var city))** đòi hỏi phải có một **Address record** để deconstruct; nếu address null, mẫu không khớp. Nếu Address tồn tại nhưng city null, **var city** có thể nhận null.

Đây là ranh giới quan trọng giữa **null của record lồng** và **null của component nằm trong record con**.

## 4. Tạo case study: đăng ký người dùng và yêu cầu giao hàng

Ta xây dựng một miền dữ liệu có ba sự kiện:

~~~java
sealed interface Event permits UserJoined, DeliveryRequested, Ping {}

record Address(String city) {}
record Profile(String name, Address address) {}

record UserJoined(Profile profile) implements Event {}

record DeliveryRequested(String id, Address destination) implements Event {}

record Ping() implements Event {}
~~~

Các record này biểu diễn **dữ liệu thô được chấp nhận để kiểm tra**, nên chưa có constructor từ chối null. Trong hệ thống thật, input đến từ JSON, form, message queue hoặc database có thể thiếu những field này. Bài sẽ kiểm tra chúng tại consumer và sau đó chuyển sang mô hình domain đã validate.

Yêu cầu:

- **UserJoined** hợp lệ khi Profile tồn tại, name không blank và địa chỉ Address tồn tại với city không blank.
- **DeliveryRequested** hợp lệ khi id không blank, destination là Address và city không blank.
- **Ping** không có component nên không yêu cầu kiểm tra component.
- **Selector null** có nghĩa chưa có sự kiện và phải trả một thông báo rõ.

Viết helper kiểm tra chuỗi:

~~~java
static boolean present(String text) {
    return text != null && !text.isBlank();
}
~~~

**String.isBlank()** có từ Java 11 và chỉ được gọi sau kiểm tra text khác null do toán tử **&&** đánh giá ngắn mạch. Với chuỗi blank hoặc null, present trả false; với chuỗi nội dung hợp lệ, present trả true.

### 4.1. Tách trường hợp hợp lệ bằng nested pattern và guard

~~~java
case UserJoined(Profile(var name, Address(var city)))
        when present(name) && present(city) ->
        "JOINED: " + name.trim() + " @ " + city.trim();
~~~

Điều kiện được thực hiện theo thứ tự:

1. UserJoined có component Profile khác null.
2. Profile có Address khác null.
3. Các biến name và city được ràng buộc.
4. Guard xác nhận chúng đều có nội dung.
5. Chỉ khi guard true mới gọi **trim()** trong body.

Guard false không ném lỗi nếu present được viết đúng; switch sẽ xem các case phù hợp tiếp theo. Nếu guard tự ném exception, exception lan ra, không được coi như false.

### 4.2. Phân biệt ba lỗi của UserJoined

~~~java
case UserJoined(Profile(var name, var address))
        when !present(name) -> "INVALID JOIN: name";

case UserJoined(Profile(var name, var address))
        when address == null -> "INVALID JOIN: address";

case UserJoined(Profile(var name, Address(var city))) ->
        "INVALID JOIN: city";

case UserJoined(var profile) -> "INVALID JOIN: profile";
~~~

Đặt các nhánh này **sau nhánh hợp lệ**, bởi một case rộng xuất hiện sớm có thể che nhánh hẹp và gây lỗi dominance.

Các kết quả có ý nghĩa khác nhau:

- **INVALID JOIN: name:** Profile tồn tại nhưng name null/blank; ở đây lỗi name được ưu tiên nếu đồng thời address cũng thiếu.
- **INVALID JOIN: address:** Profile tồn tại, name hợp lệ nhưng address null.
- **INVALID JOIN: city:** Address tồn tại, name hợp lệ nhưng city null/blank.
- **INVALID JOIN: profile:** component Profile của UserJoined null.

Đây là **quy tắc ưu tiên lỗi theo thứ tự case**. Nếu một record có nhiều component lỗi, bài này chọn báo lỗi đầu tiên có ý nghĩa theo thứ tự được thiết kế. Nếu API cần trả **tất cả lỗi cùng lúc**, việc dùng result validation chứa danh sách vấn đề sẽ phù hợp hơn nhiều case chỉ tạo một String.

### 4.3. DeliveryRequested: cùng nguyên tắc, cấu trúc khác

~~~java
case DeliveryRequested(var id, Address(var city))
        when present(id) && present(city) ->
        "DELIVERY: " + id.trim() + " -> " + city.trim();

case DeliveryRequested(var id, var address)
        when !present(id) -> "INVALID DELIVERY: id";

case DeliveryRequested(var id, var address)
        when address == null -> "INVALID DELIVERY: address";

case DeliveryRequested(var id, Address(var city)) ->
        "INVALID DELIVERY: city";
~~~

Ở nhánh DeliveryRequested hợp lệ, nếu destination null thì nested **Address(...)** không khớp. Nếu id null hoặc city null nhưng Address tồn tại, guard false, rồi case cụ thể cho lỗi xử lý. Nếu id và địa chỉ cùng thiếu, ví dụ ưu tiên báo lỗi **id**.

### 4.4. Exhaustive switch không cần default

Toàn bộ Event hierarchy chỉ có **UserJoined**, **DeliveryRequested** và **Ping**, đều là record final. Các case tổng quát ở cuối từng nhóm bao phủ phần còn lại của mỗi subtype; Ping có nhánh riêng, selector null có **case null**.

Vì vậy, **switch expression** có thể không cần default. Khi sau này thêm subtype mới vào permits và biên dịch lại, compiler sẽ nhắc handler bổ sung nhánh. Default rộng thường không có lợi nếu domain yêu cầu review từng kiểu sự kiện.

**Lưu ý:** Tính exhaustive của compiler không tự chứng minh name/city hợp lệ. Nó chỉ kiểm tra phạm vi các pattern và type; những điều kiện nghiệp vụ vẫn cần guard, constructor invariant và test.

## 5. Chương trình Java 21 hoàn chỉnh có thể chạy

Lưu toàn bộ mã dưới đây trong tệp **NullRecordComponentDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class NullRecordComponentDemo {
    sealed interface Event permits UserJoined, DeliveryRequested, Ping {}

    record Address(String city) {}
    record Profile(String name, Address address) {}
    record UserJoined(Profile profile) implements Event {}
    record DeliveryRequested(String id, Address destination) implements Event {}
    record Ping() implements Event {}

    static boolean present(String text) {
        return text != null && !text.isBlank();
    }

    static String describe(Event event) {
        return switch (event) {
            case null -> "NO EVENT";

            case UserJoined(Profile(var name, Address(var city)))
                    when present(name) && present(city) ->
                    "JOINED: " + name.trim() + " @ " + city.trim();

            case UserJoined(Profile(var name, var address))
                    when !present(name) -> "INVALID JOIN: name";

            case UserJoined(Profile(var name, var address))
                    when address == null -> "INVALID JOIN: address";

            case UserJoined(Profile(var name, Address(var city))) ->
                    "INVALID JOIN: city";

            case UserJoined(var profile) -> "INVALID JOIN: profile";

            case DeliveryRequested(var id, Address(var city))
                    when present(id) && present(city) ->
                    "DELIVERY: " + id.trim() + " -> " + city.trim();

            case DeliveryRequested(var id, var address)
                    when !present(id) -> "INVALID DELIVERY: id";

            case DeliveryRequested(var id, var address)
                    when address == null -> "INVALID DELIVERY: address";

            case DeliveryRequested(var id, Address(var city)) ->
                    "INVALID DELIVERY: city";

            case Ping() -> "PING";
        };
    }

    static String requireText(String text, String field) {
        if (!present(text)) throw new IllegalArgumentException(field);
        return text.trim();
    }

    record ValidatedAddress(String city) {
        ValidatedAddress {
            city = requireText(city, "city");
        }
    }

    record ValidatedUser(String name, ValidatedAddress address) {
        ValidatedUser {
            name = requireText(name, "name");
            Objects.requireNonNull(address, "address");
        }
    }

    record TaggedUser(String name, List<String> tags) {
        TaggedUser {
            name = requireText(name, "name");
            tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
        }
    }

    public static void main(String[] args) {
        Event[] events = {
            new UserJoined(new Profile(" An ", new Address(" Ha Noi "))),
            new UserJoined(new Profile(" ", new Address("Hue"))),
            new UserJoined(new Profile("Lan", null)),
            new UserJoined(null),
            new UserJoined(new Profile("Lan", new Address(null))),
            new DeliveryRequested("PK-1", new Address("Da Nang")),
            new DeliveryRequested(null, new Address("Hue")),
            new DeliveryRequested("PK-2", new Address(" ")),
            new DeliveryRequested("PK-3", null),
            new Ping(),
            null
        };

        for (Event event : events) {
            System.out.println(describe(event));
        }

        var user = new ValidatedUser(
                " Linh ", new ValidatedAddress(" Hue "));
        System.out.println("VALID: "
                + user.name() + " @ " + user.address().city());

        try {
            new ValidatedUser(" ", new ValidatedAddress("Hue"));
        } catch (IllegalArgumentException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        try {
            new ValidatedUser("Linh", null);
        } catch (NullPointerException ex) {
            System.out.println("REJECTED: " + ex.getMessage());
        }

        var tags = new ArrayList<>(List.of("vip"));
        var tagged = new TaggedUser("Bao", tags);
        tags.add("new");
        System.out.println("TAGS: " + tagged.tags());

        try {
            tagged.tags().add("other");
        } catch (UnsupportedOperationException ex) {
            System.out.println("TAGS: unmodifiable");
        }

        try {
            new TaggedUser("Bao",
                    java.util.Arrays.asList("vip", null));
        } catch (NullPointerException ex) {
            System.out.println("REJECTED: null tag");
        }
    }
}
~~~

### 5.1. Biên dịch và chạy

Dùng **JDK 21 trở lên**:

~~~bash
javac NullRecordComponentDemo.java
java NullRecordComponentDemo
~~~

**Đầu ra chính xác:**

~~~text
JOINED: An @ Ha Noi
INVALID JOIN: name
INVALID JOIN: address
INVALID JOIN: profile
INVALID JOIN: city
DELIVERY: PK-1 -> Da Nang
INVALID DELIVERY: id
INVALID DELIVERY: city
INVALID DELIVERY: address
PING
NO EVENT
VALID: Linh @ Hue
REJECTED: name
REJECTED: address
TAGS: [vip]
TAGS: unmodifiable
REJECTED: null tag
~~~

### 5.2. Đọc các dòng kết quả

1. **JOINED: An @ Ha Noi:** mọi record lồng cần thiết tồn tại; tên và thành phố được trim.
2. **INVALID JOIN: name:** Profile tồn tại nhưng name chỉ chứa khoảng trắng.
3. **INVALID JOIN: address:** Profile tồn tại và tên hợp lệ, nhưng Address null.
4. **INVALID JOIN: profile:** UserJoined tồn tại còn Profile null.
5. **INVALID JOIN: city:** Address tồn tại nhưng city null.
6. **DELIVERY: PK-1 -> Da Nang:** ID và thành phố đều có nội dung.
7. **INVALID DELIVERY: id:** id null, dù Address tồn tại.
8. **INVALID DELIVERY: city:** có Address nhưng city blank.
9. **INVALID DELIVERY: address:** thiếu chính Address.
10. **PING:** biến thể không có component được xử lý độc lập.
11. **NO EVENT:** null là **selector**, không phải component của một event.
12. **VALID: Linh @ Hue:** các compact constructor đã chuẩn hóa name/city bằng trim.
13. **REJECTED: name:** domain record từ chối tên blank ngay tại điểm tạo.
14. **REJECTED: address:** domain record từ chối Address null bằng Objects.requireNonNull.
15. **TAGS: [vip]:** TaggedUser đã tạo bản sao danh sách; việc thêm phần tử vào list gốc không đổi list bên trong record.
16. **TAGS: unmodifiable:** list mà TaggedUser lưu không cho phép thêm phần tử qua accessor.
17. **REJECTED: null tag:** List.copyOf từ chối collection chứa phần tử null.

Chương trình dùng **mảng Event[]** để thử cả selector null. **List.of(...)** không cho phép phần tử null, vì vậy không phù hợp nếu muốn cố ý chứa null trong một danh sách mẫu thử.

**Giới hạn demo:** Bài minh họa xử lý một sự kiện thành String để quan sát flow; không có database, network hay một framework bên ngoài. Việc trả thông báo lỗi thay vì ném exception là **chính sách riêng của hàm describe**, không phải hành vi bắt buộc của mọi API Java.

## 6. Dùng compact constructor để biến dữ liệu thô thành giá trị domain hợp lệ

Model **Profile** và **Address** ở đầu bài cho phép null nhằm mô phỏng dữ liệu nhận từ bên ngoài. Nhưng trong domain, nhiều tình huống cần bất biến mạnh hơn: nếu người dùng được công nhận là hợp lệ thì tên và địa chỉ phải có giá trị.

~~~java
record ValidatedAddress(String city) {
    ValidatedAddress {
        city = requireText(city, "city");
    }
}

record ValidatedUser(String name, ValidatedAddress address) {
    ValidatedUser {
        name = requireText(name, "name");
        Objects.requireNonNull(address, "address");
    }
}
~~~

Đây là code trích từ class hoàn chỉnh. Trong **compact constructor**, ta có thể xác thực hoặc chuẩn hóa tham số component trước khi Java tự gán chúng cho các trường record.

**requireText** ném IllegalArgumentException nếu chuỗi null hoặc blank, rồi trim chuỗi hợp lệ. **Objects.requireNonNull(address, "address")** ném NullPointerException nếu thiếu record địa chỉ.

So sánh:

| Raw record | Validated record |
| --- | --- |
| Cho phép **new Address(null)** | **new ValidatedAddress(null)** bị từ chối |
| Cho phép **new Profile(null, ...)** | **new ValidatedUser(null, ...)** bị từ chối |
| Cho phép **new Profile("Lan", null)** | **new ValidatedUser("Lan", null)** bị từ chối |
| Người tiêu thụ phải kiểm tra null | Các instance tạo hợp lệ giữ invariant rõ |
| Phù hợp nhập liệu chưa được xác thực | Phù hợp logic domain sau validation |

**Không có một lựa chọn luôn tốt hơn.** Nếu nhận JSON hoặc form chưa đáng tin cậy, raw DTO có thể ghi nhận tất cả trường còn thiếu và báo nhiều lỗi cùng lúc. Domain record thường nên bảo vệ những bất biến thật sự không thể vi phạm trong hệ thống.

Một cách kiến trúc thực tế là **parse → validate → build validated record → xử lý nghiệp vụ**. Điều đó giúp code xử lý domain ít phải dùng guard lặp lại, nhưng không tự loại bỏ nhu cầu kiểm tra null ở **selector API** nếu caller vẫn có thể truyền null.

### 6.1. Giữ hợp đồng exception nhất quán

Trong ví dụ, tên hoặc thành phố blank/null bị **IllegalArgumentException**, còn đối tượng địa chỉ null bị **NullPointerException**. Đây là hợp đồng minh họa, không phải lựa chọn duy nhất.

Nếu API công khai muốn mọi lỗi validation đều có một kiểu chung như **ValidationException**, có thể thiết kế factory trả result hoặc ném loại ngoại lệ đó. Điều quan trọng là **Javadoc, implementation và test khớp nhau**.

## 7. Record chứa collection: null không chỉ nằm ở cấp component

Record có component dạng tham chiếu final nhưng **không bảo đảm bất biến sâu**. Một component **List<String> tags** có thể gây lỗi theo ba cách:

1. Toàn bộ List là null.
2. List tồn tại nhưng chứa phần tử null.
3. List là mutable và được phía caller tiếp tục thay đổi sau khi record đã được tạo.

Trong ví dụ, **TaggedUser** xử lý bằng:

~~~java
record TaggedUser(String name, List<String> tags) {
    TaggedUser {
        name = requireText(name, "name");
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }
}
~~~

Ý nghĩa:

- **Objects.requireNonNull(tags, "tags")** từ chối null list.
- **List.copyOf(tags)** tạo dạng list không thể sửa qua các operation như add/remove và không cho phép phần tử null.
- Khi nguồn là một ArrayList mutable, nội dung bản sao không bị thay đổi bởi **tags.add(...)** trên ArrayList gốc.
- Với các phần tử là object mutable, **List.copyOf** chỉ sao chép cấu trúc collection chứ **không sao chép sâu** trạng thái bên trong từng phần tử.

Một ví dụ dữ liệu không an toàn:

~~~java
// Đoạn minh họa; List.copyOf không chấp nhận phần tử null.
new TaggedUser("Bao", java.util.Arrays.asList("vip", null));
~~~

Lời gọi trên ném NullPointerException trong constructor TaggedUser. Nếu null element là dữ liệu hợp lệ theo nghiệp vụ, **không** nên tự động dùng List.copyOf rồi coi lỗi đó là validation đúng; cần định nghĩa chiến lược riêng cho null element, ví dụ loại bỏ, báo lỗi có vị trí, hoặc biểu diễn bằng kiểu dữ liệu khác.

**Điểm chốt:** Với component là collection, hãy tài liệu hóa cả null của **collection reference** và null của **từng phần tử**; chúng là hai hợp đồng khác nhau.

## 8. Record pattern và accessor: không giả định phép deconstruct hoàn toàn vô hại

Khi record pattern trích component, JVM phải lấy giá trị component từ record theo quy tắc deconstruction. Đối với một record thông thường, accessor tự sinh chỉ trả giá trị thành phần. Java cũng cho phép record có accessor do người viết định nghĩa, nên hành vi truy cập có thể phức tạp hơn.

Nếu accessor tùy chỉnh ném exception trong quá trình matching record pattern, lỗi xuất hiện **trước case body**. Trong những trường hợp được đặc tả, lỗi từ accessor có thể được bọc thành **MatchException**, với throwable gốc là cause. Vì vậy **try/catch nằm trong case body** không tự bắt được một lỗi xảy ra khi case chưa được chọn.

Không nên viết accessor có side effect không cần thiết chỉ để phục vụ record deconstruction. Hãy giữ record đại diện cho dữ liệu giá trị rõ ràng; nếu dữ liệu cần lazy load hoặc truy vấn mạng mỗi lần truy cập, một class/service chuyên trách thường biểu đạt tốt hơn.

**Tách validation với exception của matching:** kiểm tra null trong constructor/guard là quyết định nghiệp vụ có thể dự đoán; exception từ accessor lỗi là vấn đề khác và nên được xử lý ở ranh giới phù hợp.

## 9. Đặt guard ở đâu và tránh nhầm thứ tự

Guard của case **when** được đánh giá sau khi pattern đã khớp, trước khi body chạy:

~~~java
case UserJoined(Profile(var name, Address(var city)))
        when present(name) && present(city) ->
        "JOINED: " + name.trim() + " @ " + city.trim();
~~~

Nếu **present(name) && present(city)** false, case không được chọn. Ở một switch có các nhánh fallback đúng, việc match tiếp theo sẽ chọn một case khác. Nhưng nếu không có fallback, một switch expression có thể không exhaustive hoặc thiếu đường xử lý phù hợp.

### 9.1. Short-circuit là cách tránh NPE trong guard

~~~java
static boolean present(String text) {
    return text != null && !text.isBlank();
}
~~~

Vì **&&** chỉ đánh giá vế phải nếu vế trái true, null không đi vào **isBlank()**.

Sai lầm phổ biến:

~~~java
// Sai: nếu text null, nhánh text.isBlank() sẽ bị gọi.
return text != null || !text.isBlank();
~~~

Khi text null, vế đầu false nên **||** đánh giá vế sau và ném NullPointerException. Điều kiện này cũng sai về ngữ nghĩa: một chuỗi không null nhưng blank sẽ khiến biểu thức trả true.

### 9.2. Nhánh rộng phải sau nhánh hẹp

~~~java
// Đoạn phác thảo: không đặt case tổng quát trước case đặc thù.
case UserJoined(var profile) -> "any joined event";
case UserJoined(Profile(var name, Address(var city))) ->
        "special joined event";
~~~

Với thứ tự trên, case tổng quát có thể làm case sau bị dominated. Trình biên dịch có thể từ chối nhánh không thể tới được. Hãy đặt các case cụ thể có guard trước, rồi các case còn lại cho cùng subtype.

### 9.3. Đừng dùng default để che component null

Khi có sealed Event, một **default -> "UNKNOWN"** có thể khiến subtype mới bị gom vào UNKNOWN mà không có yêu cầu cập nhật nghiệp vụ. Nó cũng không giải thích component nào thiếu.

Nên có những case xử lý **raw record thiếu thành phần** với kết quả hoặc ngoại lệ riêng. Với domain đã validate chặt, có thể bỏ bớt fallback component không cần thiết nếu compiler và invariant thật sự cho phép.

## 10. Các chiến lược xử lý component null

Không phải mọi consumer nên trả thông báo như describe. Lựa chọn phụ thuộc ý nghĩa dữ liệu.

| Chiến lược | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| **Reject ngay khi dựng record** | Compact constructor kiểm tra name, address | Domain object không được chứa trạng thái thiếu |
| **Kết quả validation tường minh** | Result với danh sách lỗi field | Form/import cần báo nhiều lỗi |
| **Guard và fallback trong switch** | Nhánh INVALID JOIN: address | Phân loại raw record cho UI/log |
| **Null là giá trị có ý nghĩa** | Phần ghi chú tùy chọn không có | Component thật sự optional |
| **Optional hoặc kiểu kết quả khác** | Optional<Address> hoặc AddressAbsent/AddressPresent | API muốn mô tả trạng thái vắng mặt tường minh |
| **Default theo domain** | Dùng cấu hình mặc định hợp lệ khi thiếu | Chỉ khi hợp đồng cho phép, không suy đoán dữ liệu |
| **Fail-fast ở API boundary** | Objects.requireNonNull(input, "input") | Null selector là lỗi của caller |

Một **component null hợp lệ** khác với một **component null làm record không hợp lệ**. Ví dụ, ghi chú bổ sung của đơn hàng có thể null mà không gây lỗi; ngược lại, ID định danh hoặc địa chỉ bắt buộc có thể không được null.

Nếu dùng **Optional<T>** làm field trong model, cần chọn convention nhất quán và tránh trả null thay cho Optional.empty(). Nhiều codebase ưu tiên Optional chủ yếu cho **return type**, còn field dùng invariant và model riêng; đây là quyết định thiết kế, không phải yêu cầu bắt buộc của Java.

## 11. Javadoc cho null component, không chỉ null selector

Một API xử lý raw record nên công bố rõ hành vi theo từng tầng:

~~~java
/**
 * Tạo mô tả sự kiện cho mục đích hiển thị.
 *
 * @param event có thể null; null trả về "NO EVENT".
 *              Với UserJoined, Profile, name, Address hoặc city
 *              có thể null/blank và được phân loại thành INVALID.
 *              Với DeliveryRequested, id hoặc destination/city
 *              có thể null/blank và cũng được phân loại.
 * @return String không null: JOINED, DELIVERY, INVALID, PING
 *         hoặc NO EVENT theo cấu trúc dữ liệu
 */
static String describe(Event event) {
    // Implementation đầy đủ ở mục 5.
    throw new UnsupportedOperationException("illustrative signature");
}
~~~

Đây chỉ là **chữ ký kèm Javadoc minh họa**, không phải phương thức để ghép với demo mục 5. Code thật phải bảo đảm không có đường return null và không có exception bất ngờ với những đầu vào được cho phép.

Đối với **ValidatedUser**, Javadoc nên ghi rằng name blank/null bị từ chối, address null bị từ chối, và city đã được kiểm tra bởi constructor ValidatedAddress. Những chi tiết này không thể suy ra chỉ từ chữ ký **ValidatedUser(String, ValidatedAddress)**.

Nếu dự án dùng annotation **@Nullable**, **@NonNull**, **@NullMarked** hoặc static checker, phải chọn hệ annotation cụ thể và đồng bộ với implementation. Java SE không cung cấp một annotation @Nullable chuẩn trong java.lang được tất cả công cụ hiểu cùng ngữ nghĩa; annotation cũng không tự thực thi validation runtime.

### Lưu ý về thông điệp lỗi

Không khuyến nghị caller phân tích chuỗi **"INVALID JOIN: name"** để quyết định nghiệp vụ. Với API public, hãy cân nhắc một kết quả có cấu trúc: **ValidationResult**, field path như **profile.address.city**, và mã lỗi ổn định. String trong bài chỉ phục vụ đọc kết quả và kiểm tra pattern logic.

## 12. Ma trận kiểm thử cho component null

Đừng chỉ test **describe(null)** rồi kết luận xử lý null đã đủ. Cần bao phủ các tầng component:

| Input | Kỳ vọng | Vì sao |
| --- | --- | --- |
| **null** | NO EVENT | Selector null |
| **UserJoined(Profile("An", Address("Hue")))** | JOINED: An @ Hue | Mọi thành phần hợp lệ |
| **UserJoined(null)** | INVALID JOIN: profile | Nested Profile null |
| **UserJoined(Profile(null, Address("Hue")))** | INVALID JOIN: name | Component String null |
| **UserJoined(Profile(" ", Address("Hue")))** | INVALID JOIN: name | Component blank |
| **UserJoined(Profile("Lan", null))** | INVALID JOIN: address | Nested Address null |
| **UserJoined(Profile("Lan", Address(null)))** | INVALID JOIN: city | Address có city null |
| **DeliveryRequested(null, Address("Hue"))** | INVALID DELIVERY: id | id null |
| **DeliveryRequested("PK", null)** | INVALID DELIVERY: address | destination null |
| **DeliveryRequested("PK", Address(" "))** | INVALID DELIVERY: city | city blank |
| **Ping()** | PING | Record không có component |
| **ValidatedUser(" ", ValidatedAddress("Hue"))** | IllegalArgumentException | Constructor từ chối name blank |
| **ValidatedUser("Linh", null)** | NullPointerException | Constructor từ chối address null |
| **TaggedUser("Bao", null)** | NullPointerException | List reference null |
| **TaggedUser("Bao", list có phần tử null)** | NullPointerException | List.copyOf không cho phần tử null |

Nếu sử dụng JUnit, nên có **assertEquals** cho các kết quả và **assertThrows** cho các trường hợp lỗi. Với thử nghiệm không cần framework, chương trình mục 5 đã bao phủ nhiều trường hợp đại diện và in ra các tình huống có thể quan sát.

Với dữ liệu raw phức tạp, thêm test khi **nhiều component cùng null** để khẳng định thứ tự ưu tiên lỗi. Nếu validation trả danh sách lỗi, kiểm tra tập field path thay vì chỉ một thông báo.

## 13. Quy trình áp dụng vào project

1. **Phân loại model:** record nào là raw input, record nào là domain value đã validate?
2. **Viết bảng nullability:** đối với từng component, ghi bắt buộc, optional hay chưa đáng tin cậy.
3. **Chọn ranh giới validation:** tại constructor, factory, mapper hay service, tùy ai chịu trách nhiệm hợp đồng.
4. **Thiết kế các record pattern:** viết nhánh hợp lệ dễ đọc, guard cho String/content và fallback cho nested record null.
5. **Sắp xếp nhánh:** case hẹp trước, case rộng sau; tránh dominance và default che subtype mới.
6. **Quy định selector null riêng:** case null, Objects.requireNonNull hoặc result loại Missing, không lấy chính sách component để suy ra chính sách selector.
7. **Xử lý collection:** kiểm tra null collection, null elements, mutable aliases và bảo vệ khi cần bằng defensive copy.
8. **Tài liệu hóa API:** Javadoc, error/result types, nullability annotations và mức độ ổn định của thông điệp lỗi.
9. **Kiểm thử có chủ đích:** null ở từng cấp, blank, không hợp lệ nhiều trường, exception và trường hợp hợp lệ.
10. **Biên dịch lại khi hierarchy thay đổi:** sealed + exhaustive switch giúp phát hiện subtype mới, nhưng không thay thế việc review invariant của record.

## 14. Lỗi thường gặp và cách tránh

**Lỗi 1 — Nghĩ rằng record final nghĩa là component không thể null.** Final chỉ ngăn gán lại trường sau khi khởi tạo, không ngăn tham chiếu lưu null. Nếu cần nonnull, xác thực ở constructor.

**Lỗi 2 — Tưởng deconstruction tự xác thực chuỗi.** Record pattern chỉ trích component; nếu component String null/blank, cần guard hoặc invariant thích hợp.

**Lỗi 3 — Tưởng mọi type pattern bên trong record đều loại null.** Với pattern không điều kiện tương ứng kiểu component, như **Box(String text)** trên Box có String value, text có thể là null. Đừng dùng nó thay cho **text != null**.

**Lỗi 4 — Quên record con null.** **Profile(var name, Address(var city))** không match nếu address null. Dùng fallback hoặc cấm address null từ đầu.

**Lỗi 5 — Dùng case null cho component null.** Case null chỉ xét selector. Với **UserJoined(null)**, selector không null, nên không vào case null.

**Lỗi 6 — Sắp case rộng trước case hẹp.** Nhánh sau có thể bị dominated, hoặc logic chi tiết không bao giờ chạy. Đặt guard/record pattern đặc thù trước fallback.

**Lỗi 7 — Guard dùng toán tử sai.** **text != null || !text.isBlank()** có thể gây NPE; dùng && ngắn mạch.

**Lỗi 8 — Có default cho mọi thứ.** Default rộng có thể che subtype mới trong sealed hierarchy và khiến component null bị xem như một lỗi chung khó truy dấu.

**Lỗi 9 — Nhầm shallow immutability với deep immutability.** Record giữ tham chiếu final đến List nhưng nội dung List có thể mutable nếu không sao chép. **List.copyOf** không sao chép sâu từng element.

**Lỗi 10 — Catch NullPointerException rồi coi là “thiếu dữ liệu”.** NPE cũng có thể đến từ bug hoặc accessor tùy chỉnh, nên việc catch rộng có thể che nguyên nhân thật.

**Lỗi 11 — Đánh đồng lỗi null với lỗi nghiệp vụ khác.** Một id null, một địa chỉ null và một record không thuộc subtype được chấp nhận có thể cần mã lỗi khác nhau.

**Lỗi 12 — Chỉ test null selector.** Một record có thể chứa nhiều tầng component; phải test từng tầng và thứ tự ưu tiên lỗi.

## 15. Checklist code review

- [ ] Record model nào được phép chứa component null và model nào có invariant nonnull?
- [ ] Null selector được xử lý độc lập với null component chưa?
- [ ] Record pattern lồng có fallback cho record con null khi input raw cho phép?
- [ ] Biến từ **var** hoặc type pattern có được kiểm tra trước khi gọi method khi có thể null?
- [ ] Guard an toàn với null và đúng thứ tự ưu tiên lỗi?
- [ ] Các case rộng có đứng sau case hẹp, không gây dominance?
- [ ] Switch exhaustive đối với sealed hierarchy, không dùng default làm mất tín hiệu subtype mới?
- [ ] Constructor/factory xác thực name, city, id và những component domain bắt buộc?
- [ ] Component List có kiểm tra null reference, null element và mutable alias?
- [ ] Javadoc/annotation có nói đúng các trường hợp null, blank, exception và kết quả?
- [ ] Test bao phủ selector null, từng cấp component null, nhiều field lỗi đồng thời và input hợp lệ?
- [ ] Có phân biệt raw DTO với validated domain record để không lặp logic phòng thủ khắp hệ thống?

**Kết luận:** **Record không tự bảo đảm component khác null.** Trong Java 21, record patterns có thể ràng buộc component null với những pattern không điều kiện, còn **nested record pattern** không khớp khi record con là null. Muốn xử lý đúng cần phân biệt **selector null**, **component null**, **record con null**, **giá trị blank** và **collection chứa null**. Sử dụng guard với short-circuit, case fallback theo từng subtype, compact constructor để giữ invariant và kiểm thử tại ranh giới API sẽ giúp hệ thống tránh NPE ngầm mà không che mất dữ liệu không hợp lệ.