# Record pattern và phân rã dữ liệu lồng nhau

## 1. Vì sao cần record pattern?

Khi xử lý dữ liệu trong Java, một chương trình thường phải xác định kiểu của đối tượng, gọi các accessor, lấy các giá trị thành phần, rồi tiếp tục kiểm tra những đối tượng được lồng bên trong. Với mô hình dữ liệu gồm nhiều record, chuỗi thao tác đó có thể dài và khó nhìn thấy ý nghĩa nghiệp vụ.

**Record pattern** cho phép diễn đạt việc kiểm tra kiểu và phân rã (*deconstruction*) các thành phần của một record ngay trong một biểu thức pattern matching. Có thể đặt record pattern bên trong record pattern khác để đi qua nhiều tầng dữ liệu theo đúng cấu trúc khai báo.

Ví dụ:

~~~java
record Point(int x, int y) {}

Object candidate = new Point(10, 20);

if (candidate instanceof Point(var x, var y)) {
    System.out.println("x=" + x + ", y=" + y);
}
~~~

Khi đối tượng khớp với **Point**, hai biến **x** và **y** được khai báo và nhận giá trị của hai record component. Trình biên dịch biết x và y có kiểu **int** tương ứng với khai báo của record.

**Phạm vi phiên bản:** Record patterns (JEP 440) đã trở thành tính năng chính thức từ Java 21; pattern matching cho switch (JEP 441) cũng chính thức từ Java 21. Unnamed patterns (JEP 456), dùng dấu gạch dưới **_**, chính thức từ Java 22. Các ví dụ trong bài sử dụng những tính năng đã được chuẩn hóa, còn áp dụng trong Java 27 và không yêu cầu bật preview.

## 2. Record component và record pattern khác nhau thế nào?

Một record khai báo cấu trúc dữ liệu qua các component:

~~~java
record Coordinate(double latitude, double longitude) {}
~~~

Khai báo đó tạo một kiểu record với các component **latitude** và **longitude**, cùng accessor tương ứng. Record pattern không tạo ra một kiểu mới; nó **kiểm tra và phân rã một giá trị hiện có**:

~~~java
Object input = new Coordinate(10.82, 106.63);

if (input instanceof Coordinate(var lat, var lon)) {
    System.out.printf("%.2f, %.2f%n", lat, lon);
}
~~~

Diễn giải cấu trúc:

| Thành phần cú pháp | Ý nghĩa |
|---|---|
| **Coordinate** trong khai báo record | Tên kiểu dữ liệu |
| **Coordinate(var lat, var lon)** trong instanceof | Record pattern cần kiểm tra |
| **var lat** | Pattern biến cục bộ nhận giá trị component thứ nhất |
| **var lon** | Pattern biến cục bộ nhận giá trị component thứ hai |
| Thân **if** | Chỉ chạy khi toàn bộ pattern khớp |

Record pattern sử dụng thứ tự component của khai báo record. Tên biến ở pattern do lập trình viên chọn và **không bắt buộc trùng tên accessor**, nhưng số lượng pattern con phải bằng số component. Ví dụ **Coordinate(var longitude, var latitude)** vẫn biên dịch, nhưng các biến bị gán sai ý nghĩa vì nhận giá trị theo vị trí, không theo tên.

Đây là khác biệt lớn so với truy cập qua accessor: pattern tóm tắt cả cấu trúc cần khớp và tên các giá trị muốn sử dụng.

## 3. So sánh với instanceof type pattern

**Type pattern** kiểm tra kiểu và gắn toàn bộ đối tượng vào một biến:

~~~java
Object candidate = new Coordinate(10.82, 106.63);

if (candidate instanceof Coordinate coordinate) {
    double lat = coordinate.latitude();
    double lon = coordinate.longitude();
    System.out.println(lat + " / " + lon);
}
~~~

**Record pattern** kiểm tra kiểu, sau đó lấy trực tiếp các component:

~~~java
if (candidate instanceof Coordinate(var lat, var lon)) {
    System.out.println(lat + " / " + lon);
}
~~~

Cả hai đều hữu ích. Type pattern hợp lý khi bạn cần giữ nguyên đối tượng để gọi nhiều phương thức hoặc truyền nó cho một thành phần khác. Record pattern hợp lý khi bạn quan tâm đến cấu trúc dữ liệu và muốn dùng ngay các thành phần.

Khi record có nhiều component nhưng chỉ cần một giá trị, record pattern vẫn phải có vị trí cho tất cả component. Có thể dùng unnamed pattern **_** để bỏ qua thành phần không cần đọc; phần sau sẽ giải thích.

## 4. Phân rã một record lồng trong record khác

Giả sử hệ thống giao hàng mô hình hóa địa chỉ và người nhận bằng record:

~~~java
record Address(String city, String country) {}

record Recipient(String name, Address address) {}

record Shipment(String trackingId, Recipient recipient) {}
~~~

Một Shipment chứa Recipient; Recipient lại chứa Address.

~~~mermaid
flowchart TD
    S[Shipment] --> I[trackingId: String]
    S --> R[recipient: Recipient]
    R --> N[name: String]
    R --> A[address: Address]
    A --> C[city: String]
    A --> K[country: String]
~~~

Cách truy cập thông thường:

~~~java
Object incoming = new Shipment(
    "S-001",
    new Recipient("Lan", new Address("Ha Noi", "VN"))
);

if (incoming instanceof Shipment shipment
        && shipment.recipient() != null
        && shipment.recipient().address() != null) {
    String city = shipment.recipient().address().city();
    System.out.println(city);
}
~~~

Cách viết bằng **nested record pattern**:

~~~java
if (incoming instanceof Shipment(
        var id,
        Recipient(var name, Address(var city, var country)))) {
    System.out.println(id + " - " + name + " - " + city);
}
~~~

Đoạn pattern mô tả trực tiếp ba tầng cấu trúc:

1. Giá trị ngoài cùng phải là **Shipment**.
2. Component thứ hai phải khớp với record **Recipient**.
3. Component **address** của Recipient phải khớp với record **Address**.
4. Chỉ khi mọi phần cần thiết khớp, các biến **id**, **name**, **city**, **country** mới dùng được trong nhánh **if**.

Như vậy, không cần gọi thủ công chuỗi **shipment.recipient().address().city()** chỉ để truy xuất một số giá trị. Tuy nhiên, nested record pattern không thay thế mọi bước xác thực nghiệp vụ: nếu ứng dụng cần bảo đảm chuỗi không rỗng, mã quốc gia hợp lệ hoặc số lượng dương, hãy kiểm tra thêm.

## 5. Quy tắc khớp và thứ tự phân rã

Record pattern gồm tên một **record class type** và danh sách pattern con. Danh sách này phải tương ứng với số lượng và thứ tự record components.

~~~java
record Size(int width, int height) {}

// Hợp lệ: hai component.
if (candidate instanceof Size(var width, var height)) {
    System.out.println(width * height);
}
~~~

Ví dụ không hợp lệ:

~~~java
// Sai: record Size có hai component nhưng pattern chỉ có một.
// if (candidate instanceof Size(var width)) { ... }

// Sai: ArrayList không phải record class type.
// if (candidate instanceof ArrayList(var first)) { ... }
~~~

Một record pattern có thể có danh sách rỗng nếu record không khai báo component:

~~~java
record Ping() {}

Object value = new Ping();
if (value instanceof Ping()) {
    System.out.println("Ping received");
}
~~~

Không phải tất cả đối tượng có accessor đều dùng được record pattern. Một class thông thường dù có phương thức **getX()**, **getY()** cũng không thể tự động được phân rã bằng cú pháp **ClassName(var x, var y)**. Với class thường, hãy dùng type pattern và gọi phương thức của class.

## 6. Từ khóa var và kiểu dữ liệu suy luận

Khi dùng **var** trong component pattern, trình biên dịch suy ra kiểu từ record component tương ứng:

~~~java
record Pixel(int red, int green, int blue) {}

Object input = new Pixel(128, 64, 32);

if (input instanceof Pixel(var r, var g, var b)) {
    int average = (r + g + b) / 3;
    System.out.println(average);
}
~~~

Ở đây r, g, b là các biến kiểu **int**. **var** không có nghĩa là biến có kiểu động hoặc kiểu Object chung chung; nó chỉ yêu cầu trình biên dịch suy luận một kiểu tĩnh hợp lệ.

Nếu muốn biểu đạt kiểu tường minh, có thể viết:

~~~java
if (input instanceof Pixel(int r, int g, int b)) {
    System.out.println(r + g + b);
}
~~~

Kiểu được khai báo trong pattern phải áp dụng được với kiểu component. Nếu component là **String**, không thể tùy ý viết pattern kiểu không tương thích. Với component có kiểu tham chiếu tổng quát, một type pattern cụ thể có thể đóng vai trò kiểm tra kiểu bổ sung.

~~~java
record Attribute(Object value) {}

Object attribute = new Attribute("active");

if (attribute instanceof Attribute(String text)) {
    System.out.println(text.toUpperCase(java.util.Locale.ROOT));
}
~~~

Pattern **Attribute(String text)** chỉ khớp khi component value có thể khớp với String. Trái lại, **Attribute(var value)** sẽ lấy component với kiểu tĩnh Object mà không yêu cầu đó là String.

## 7. Kiểu generic và suy luận qua nhiều tầng

Record có thể là generic:

~~~java
record Box<T>(T value) {}
~~~

Khi kiểu dữ liệu chứa thông tin generic đầy đủ, trình biên dịch có thể suy luận tham số kiểu của record pattern:

~~~java
Box<Box<String>> nested =
    new Box<>(new Box<>("java-27"));

if (nested instanceof Box(Box(var text))) {
    System.out.println(text.toUpperCase(java.util.Locale.ROOT));
}
~~~

Ở đây pattern lồng nhau được suy luận tương ứng với **Box<Box<String>>** và **Box<String>**; biến text được hiểu là String. Không cần ép kiểu thủ công.

Với generic record, cũng có thể viết kiểu tường minh:

~~~java
Box<String> box = new Box<>("value");

if (box instanceof Box<String>(var content)) {
    System.out.println(content);
}
~~~

**Lưu ý về kiểu raw và unchecked conversion:** Không phải mọi record pattern có tham số generic đều hợp lệ với đầu vào raw type hoặc kiểu chưa đủ thông tin. Nếu việc kiểm tra cần một unchecked conversion, trình biên dịch có thể từ chối pattern. Nên duy trì kiểu generic cụ thể xuyên suốt ứng dụng thay vì dùng raw types và ép kiểu không an toàn.

Record pattern cũng không tự phân rã các phần tử bên trong List, Map hoặc mảng. Chẳng hạn **record Batch(List<Order> orders)** chỉ có thể phân rã component orders thành một List; muốn duyệt từng Order vẫn phải dùng vòng lặp, Stream hoặc API collection phù hợp.

## 8. Record pattern trong switch expression

Ngoài **instanceof**, record pattern có thể xuất hiện trong nhãn case của switch. Nó giúp chọn hành vi dựa trên cả **kiểu đối tượng** và **cấu trúc dữ liệu bên trong**.

~~~java
record Address(String city, String country) {}
record Customer(String name, Address address) {}
record Order(String id, Customer customer) {}

static String destination(Object payload) {
    return switch (payload) {
        case null -> "missing";
        case Order(var id, Customer(var name, Address(var city, var country))) ->
            id + " -> " + name + " @ " + city + ", " + country;
        case Order(var id, _) ->
            "order " + id + " has incomplete customer data";
        default -> "unsupported";
    };
}
~~~

Ở đây, nhánh đầu tiên sau **case null** khớp những Order có Customer và Address không null. Nhánh **Order(var id, _)** nhận các Order còn lại, kể cả khi customer null. Cuối cùng **default** xử lý các đối tượng không phải Order.

Với switch expression, các nhánh cần tạo ra một giá trị hoặc kết thúc bất thường, đồng thời toàn bộ switch phải được trình biên dịch xác định là đầy đủ (*exhaustive*). Nếu selector có thể nhận nhiều loại đối tượng không được liệt kê, thêm **default** hoặc một pattern tổng quát phù hợp.

Một case pattern có thể đứng trước case khác nhưng không được làm case sau trở thành không thể khớp. Vì vậy, nên đặt nhánh **cụ thể hơn trước**, nhánh tổng quát hoặc fallback sau.

## 9. Guard when: kiểm tra thêm điều kiện nghiệp vụ

Record pattern kiểm tra cấu trúc, nhưng không tự kiểm tra mọi giá trị bên trong. Guard **when** cho phép bổ sung điều kiện sau khi pattern đã khớp và pattern variables đã được gán.

~~~java
record Price(java.math.BigDecimal amount, String currency) {}
record Invoice(String id, Price price) {}

static String classify(Object value) {
    return switch (value) {
        case Invoice(var id, Price(var amount, var currency))
                when amount != null
                    && amount.signum() > 0
                    && "VND".equals(currency) ->
            "valid VND invoice: " + id;

        case Invoice(var id, _) ->
            "invoice needs review: " + id;

        case null -> "no invoice";
        default -> "not an invoice";
    };
}
~~~

Trình tự đọc một nhánh có guard:

1. Kiểm tra đối tượng có khớp với record pattern hay không.
2. Nếu khớp, tạo các pattern variables từ các component.
3. Đánh giá điều kiện **when**.
4. Chỉ khi guard có kết quả true, nhánh đó được chọn.

Ví dụ dùng **amount != null** trước **amount.signum()** để tránh NullPointerException. Phép **&&** có đánh giá ngắn mạch; biểu thức sau chỉ được chạy khi điều kiện trước đúng.

**when** không phải thành phần của khai báo record. Đây là cú pháp của switch label có pattern. Khi chỉ dùng instanceof trong if, có thể viết điều kiện kết hợp với **&&** thay cho when.

~~~java
if (value instanceof Invoice(var id, Price(var amount, var currency))
        && amount != null
        && amount.signum() > 0) {
    System.out.println("Positive invoice: " + id);
}
~~~

Nhánh có **when** không nhất thiết bao phủ toàn bộ kiểu record, vì guard có thể trả false. Hãy đặt một nhánh fallback khi mô hình nghiệp vụ cần xử lý tất cả trường hợp.

## 10. Ba tình huống null cần phân biệt

Xử lý null là một phần quan trọng của record pattern.

**Trường hợp A — Giá trị ngoài cùng là null.** Bản thân null **không khớp với record pattern**:

~~~java
record Wrapper(String value) {}

Object input = null;
System.out.println(input instanceof Wrapper(var text)); // false
~~~

Trong pattern switch, nếu selector null, hãy xử lý bằng **case null** nếu null là đầu vào hợp lệ. **default** không thay thế case null.

**Trường hợp B — Component tham chiếu null nhưng được bắt bằng var.** Một type pattern nằm trực tiếp ở vị trí component và vô điều kiện đối với kiểu của component, ví dụ **var text**, có thể khớp với null:

~~~java
Object input = new Wrapper(null);

if (input instanceof Wrapper(var text)) {
    System.out.println(text == null); // true
}
~~~

Vì thế, dùng **var** không chứng minh giá trị bên trong khác null. Nếu cần gọi phương thức trên biến nhận được, hãy kiểm tra null hoặc thiết kế record constructor bảo đảm bất biến.

**Trường hợp C — Component cần khớp tiếp với record pattern lồng nhau.** Record pattern lồng nhau cũng không khớp với null:

~~~java
record Child(String name) {}
record Parent(Child child) {}

Object input = new Parent(null);

System.out.println(input instanceof Parent(var child));        // true
System.out.println(input instanceof Parent(Child(var name))); // false
~~~

Tóm tắt:

| Giá trị cần khớp | Pattern | Kết quả |
|---|---|---|
| null ở tầng ngoài cùng | **Wrapper(var x)** | Không khớp |
| Wrapper có component value null | **Wrapper(var x)** | Khớp, x nhận null |
| Parent có component child null | **Parent(Child(var name))** | Không khớp |
| Parent có component child null | **Parent(var child)** | Khớp, child nhận null |

Trong thiết kế miền dữ liệu, nên khai báo và kiểm tra bất biến tại thời điểm tạo record, thay vì phụ thuộc hoàn toàn vào pattern để phát hiện dữ liệu không hợp lệ.

## 11. Bỏ qua component bằng unnamed pattern _

Khi không cần sử dụng một component, có thể dùng **_** để biểu diễn unnamed pattern. Tính năng này đã là chính thức từ Java 22.

~~~java
record User(String id, String displayName, int age) {}

Object candidate = new User("u-1", "Lan", 28);

if (candidate instanceof User(var id, _, _)) {
    System.out.println("User ID: " + id);
}
~~~

Những vị trí **_** vẫn tham gia khớp cấu trúc của record nhưng không khai báo biến mà mã có thể sử dụng. Khi xử lý record nhiều thành phần, điều này giúp tránh khai báo tên không dùng đến.

**_** trong danh sách component được dùng như một pattern khớp mọi giá trị tại vị trí đó, kể cả null. Nó khác với việc đặt một nested record pattern bắt buộc component phải là một đối tượng record không null.

Ví dụ đi qua đúng một nhánh lồng nhau và bỏ qua các giá trị khác:

~~~java
if (incoming instanceof Shipment(
        _, Recipient(_, Address(var city, _)))) {
    System.out.println("Destination city: " + city);
}
~~~

Không viết **_** như tên một biến bình thường rồi cố đọc lại giá trị ấy. Underscore là token dành cho unnamed variable/pattern, cố ý không thể tham chiếu bằng tên.

## 12. Phạm vi và vòng đời của pattern variables

Pattern variables không tồn tại vô điều kiện ở mọi nơi. Phạm vi của chúng được Java xác định theo **flow scoping**: biến chỉ được dùng ở nơi chương trình biết pattern chắc chắn đã khớp.

Trong if:

~~~java
Object value = new Coordinate(1.0, 2.0);

if (value instanceof Coordinate(var lat, var lon)) {
    System.out.println(lat + lon); // Hợp lệ
}

// System.out.println(lat); // Không hợp lệ ngoài phạm vi khớp
~~~

Đánh giá ngắn mạch với **&&** có thể dùng các biến vừa được khai báo:

~~~java
if (value instanceof Coordinate(var lat, var lon)
        && lat >= -90 && lat <= 90) {
    System.out.println("Candidate latitude: " + lat);
}
~~~

Với nhánh guard **when**, các biến từ pattern có thể được dùng trong chính guard và trong body của case:

~~~java
switch (value) {
    case Coordinate(var lat, var lon) when lat > 0 ->
        System.out.println("Northern hemisphere: " + lon);
    case Coordinate(var lat, var lon) ->
        System.out.println("Other coordinate: " + lat);
    default -> System.out.println("Unknown");
}
~~~

Không dùng cùng một tên pattern variable hai lần trong **cùng một pattern**. Ngược lại, việc tái sử dụng tên trong các switch rules riêng biệt thường hợp lệ vì chúng thuộc các phạm vi phân nhánh khác nhau.

Đừng cố truy cập pattern variable ở nhánh else hoặc ngoài khối mà biến không còn chắc chắn được gán. Nếu cần giá trị sau if, có thể đưa phần xử lý vào chính nhánh khớp, hoặc chuyển kết quả thành một object/giá trị trả về phù hợp.

## 13. Sealed interface, record patterns và switch đầy đủ

Khi các biến thể dữ liệu được kiểm soát, **sealed interface** kết hợp với record rất hữu ích. Một switch expression có thể bao phủ các biến thể cụ thể và dùng record pattern để lấy nội dung.

~~~java
sealed interface PaymentEvent permits Authorized, Declined {}

record Authorized(String paymentId, int amount) implements PaymentEvent {}
record Declined(String paymentId, String reason) implements PaymentEvent {}

static String summarize(PaymentEvent event) {
    return switch (event) {
        case Authorized(var id, var amount) ->
            "Authorized " + id + ", amount=" + amount;
        case Declined(var id, var reason) ->
            "Declined " + id + ": " + reason;
    };
}
~~~

Hai biến thể trực tiếp đã được liệt kê, vì vậy switch expression có thể được kiểm tra tính đầy đủ mà không cần **default**. Khi thêm một biến thể mới vào tập **permits**, trình biên dịch có thể yêu cầu cập nhật switch khi biên dịch lại.

Nếu thay một nhánh record pattern tổng quát bằng một nested record pattern quá cụ thể, cần lưu ý nested pattern có thể không khớp khi component null hoặc có biến thể con khác. Khi đó, hãy thêm nhánh cho các tình huống còn lại để giữ tính đầy đủ.

Ví dụ về thứ tự ưu tiên đúng:

~~~java
record UserInfo(String name) {}
record UserCreated(String id, UserInfo user) {}

static String describe(Object event) {
    return switch (event) {
        case UserCreated(var id, UserInfo(var name))
                when name != null && !name.isBlank() ->
            "Created user " + name + " (" + id + ")";
        case UserCreated(var id, _) ->
            "Created user with incomplete info: " + id;
        case null -> "No event";
        default -> "Unknown event";
    };
}
~~~

Nếu chuyển nhánh **UserCreated(var id, _)** lên đầu, nhánh kiểm tra UserInfo phía sau sẽ bị che khuất vì mọi giá trị UserCreated đã được nhánh tổng quát nhận trước. Trình biên dịch có thể báo lỗi nhãn case bị chi phối (*dominated case label*).

## 14. Record accessor và tác dụng phụ khi phân rã

Record pattern có vẻ giống thao tác tách dữ liệu thuần túy, nhưng ở runtime, Java lấy component bằng cách gọi các **accessor** của record.

Ví dụ record bình thường:

~~~java
record Person(String name, int age) {}
~~~

Pattern **Person(var name, var age)** yêu cầu lấy giá trị từ các accessor **name()** và **age()**. Khi record dùng accessor tự sinh và component chỉ chứa giá trị dữ liệu, cách dùng này thường rõ ràng và dễ dự đoán.

Tuy nhiên, Java cho phép record khai báo accessor tường minh. Nếu accessor có tác dụng phụ, tốn kém hoặc ném ngoại lệ, việc khớp pattern cũng có thể bị ảnh hưởng. Theo quy tắc Java 27, nếu việc gọi accessor trong quá trình record-pattern matching ném ngoại lệ, việc khớp kết thúc bất thường bằng **MatchException**, với nguyên nhân là ngoại lệ ban đầu.

Vì vậy:

- Giữ record accessor đơn giản, ổn định và tránh tác dụng phụ không cần thiết.
- Đừng dùng record pattern để che giấu thao tác I/O hoặc truy vấn mạng bên trong accessor.
- Không giả định pattern matching luôn hoàn tất thành true hoặc false nếu accessor có thể lỗi.
- Với dữ liệu chứa collection hoặc object mutable, cân nhắc defensive copy và validation tại constructor của record.

**Record không tự động trở nên bất biến sâu**: các component là final, nhưng một component tham chiếu đến List mutable vẫn có thể bị thay đổi thông qua tham chiếu đó nếu không bảo vệ. Record pattern chỉ lấy các giá trị component; nó không tạo bản sao sâu của object graph.

## 15. Ví dụ thực tế hoàn chỉnh: phân tuyến kiện hàng

Ví dụ dưới đây kết hợp record lồng nhau, guard, unnamed pattern, case null và fallback. Toàn bộ mã có thể lưu trong một tệp **ParcelRoutingDemo.java**.

~~~java
public class ParcelRoutingDemo {
    record Address(String city, String country) {}
    record Recipient(String name, Address address) {}
    record Parcel(String code, Recipient recipient) {}

    static String route(Object payload) {
        return switch (payload) {
            case null -> "MISSING";

            case Parcel(
                    var code,
                    Recipient(var name, Address(var city, var country)))
                    when "VN".equals(country) && "Ha Noi".equals(city) ->
                "LOCAL " + code + " -> " + name;

            case Parcel(
                    var code,
                    Recipient(var name, Address(var city, var country))) ->
                "STANDARD " + code + " -> " + city + ", " + country;

            case Parcel(var code, _) ->
                "INCOMPLETE " + code;

            default -> "UNSUPPORTED";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            new Parcel("P-101",
                new Recipient("Lan", new Address("Ha Noi", "VN"))),
            new Parcel("P-102",
                new Recipient("Minh", new Address("Da Nang", "VN"))),
            new Parcel("P-103", null),
            null,
            "unexpected"
        };

        for (Object input : inputs) {
            System.out.println(route(input));
        }
    }
}
~~~

Biên dịch và chạy với JDK 27:

~~~bash
javac ParcelRoutingDemo.java
java ParcelRoutingDemo
~~~

Kết quả dự kiến:

~~~text
LOCAL P-101 -> Lan
STANDARD P-102 -> Da Nang, VN
INCOMPLETE P-103
MISSING
UNSUPPORTED
~~~

**Giải thích luồng xử lý:**

1. Nếu payload null, switch chọn **case null**.
2. Nếu payload là Parcel chứa Recipient và Address, chương trình phân rã lấy code, name, city và country.
3. Guard kiểm tra tuyến nội địa cụ thể; khi không thỏa guard, nhánh Parcel kế tiếp vẫn có thể khớp.
4. Nếu Parcel thiếu Recipient hoặc Address, nested record pattern không khớp, nhưng **Parcel(var code, _)** vẫn khớp.
5. Các giá trị không thuộc kiểu Parcel được chuyển đến **default**.

Ví dụ cố ý cho phép một số component null để minh họa cách pattern thất bại và được fallback xử lý. Trong ứng dụng thực tế, nên kiểm tra bất biến ở record constructor hoặc ranh giới nhập liệu, thay vì để object không hợp lệ đi sâu trong hệ thống.

## 16. Kiểm thử các trường hợp quan trọng

Với phương thức route ở ví dụ trước, tập kiểm thử nên bao gồm nhiều hơn một trường hợp thành công. Có thể viết các kiểm tra nhỏ theo cách sau:

~~~java
static void verifyRouting() {
    Object local = new ParcelRoutingDemo.Parcel(
        "A", new ParcelRoutingDemo.Recipient(
            "An", new ParcelRoutingDemo.Address("Ha Noi", "VN")));

    Object incomplete = new ParcelRoutingDemo.Parcel("B", null);

    if (!ParcelRoutingDemo.route(local).startsWith("LOCAL")) {
        throw new AssertionError("Expected local route");
    }
    if (!"INCOMPLETE B".equals(ParcelRoutingDemo.route(incomplete))) {
        throw new AssertionError("Expected incomplete fallback");
    }
    if (!"MISSING".equals(ParcelRoutingDemo.route(null))) {
        throw new AssertionError("Expected null handling");
    }
    if (!"UNSUPPORTED".equals(ParcelRoutingDemo.route(42))) {
        throw new AssertionError("Expected unsupported type");
    }
}
~~~

Khi tích hợp vào test suite, chuyển những kiểm tra này thành các unit tests với framework đang dùng. Bổ sung cả trường hợp guard trả false, các component tham chiếu null, dữ liệu chuỗi rỗng, record generic và thay đổi biến thể của sealed hierarchy nếu có.

Nếu accessor tự định nghĩa có thể ném ngoại lệ, bổ sung test cho đường lỗi này thay vì giả định pattern luôn trả false khi gặp vấn đề truy cập dữ liệu.

## 17. Các lỗi phổ biến và giới hạn cần nhớ

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Record pattern không biên dịch trên class thông thường | Cú pháp deconstruction chỉ áp dụng với record class type | Dùng type pattern và accessor của class |
| Sai số lượng component | Danh sách pattern không khớp số component khai báo | Kiểm tra chữ ký record và thứ tự |
| Lấy nhầm thành phần | Pattern khớp theo vị trí, không theo tên biến | Đặt tên biến đúng ngữ nghĩa và test |
| NullPointerException sau khi dùng var | Nested var có thể nhận null đối với component tham chiếu | Validate dữ liệu hoặc kiểm tra null |
| Nested record pattern không được chọn | Component bên trong null hoặc sai kiểu record | Dùng nhánh fallback hoặc sửa dữ liệu đầu vào |
| Nhánh switch phía sau unreachable | Nhánh tổng quát được viết trước nhánh cụ thể | Đưa nhánh cụ thể/guard lên trước |
| Switch expression không exhaustive | Thiếu trường hợp hoặc guard không bao phủ toàn miền | Bổ sung case tương ứng, fallback hoặc default |
| Không sử dụng được pattern variable | Biến không nằm trong flow scope đã khớp | Chuyển việc xử lý vào nhánh hoặc trả về giá trị |
| Không truy xuất được List bằng record pattern | List và array không phải record components có thể tiếp tục phân rã như record | Lấy List ra rồi duyệt qua API collection |
| Generic record pattern cần ép kiểu không an toàn | Dữ liệu là raw type hoặc thiếu thông tin generic | Giữ generic types cụ thể, tránh unchecked cast |
| Accessor ném lỗi trong lúc match | Record accessor có tác dụng phụ hoặc lỗi runtime | Đơn giản hóa accessor và xử lý ngoại lệ thích hợp |

**Không sử dụng cú pháp record pattern trong phần khai báo biến thông thường như một dạng destructuring assignment.** Java hiện không hỗ trợ cú pháp tổng quát tương đương việc gán một record trực tiếp cho danh sách biến ở mọi vị trí. Record pattern được dùng trong những ngữ cảnh pattern matching mà ngôn ngữ hỗ trợ, chẳng hạn **instanceof** và **switch**.

**Không dùng cú pháp record pattern ngay trong phần khai báo biến của enhanced for.** Khả năng từng xuất hiện trong bản preview đã không được giữ lại khi tính năng được chuẩn hóa ở Java 21. Thay vào đó, duyệt phần tử bình thường rồi dùng instanceof hoặc switch trong thân vòng lặp:

~~~java
for (Object item : items) {
    if (item instanceof Coordinate(var lat, var lon)) {
        System.out.println(lat + ", " + lon);
    }
}
~~~

Cách dùng này vẫn hiện hành trong Java 27 và không dựa vào cú pháp preview đã bị loại bỏ.

## 18. Khi nào record pattern làm mã tốt hơn?

Nên cân nhắc record pattern khi:

- Dữ liệu được mô hình hóa bằng record và có cấu trúc lồng nhau rõ ràng.
- Cần chọn nhánh theo kiểu và một số component của dữ liệu.
- Có sealed hierarchy gồm các record biến thể cần xử lý đầy đủ.
- Muốn giới hạn các phép kiểm tra kiểu và truy xuất component lặp đi lặp lại.
- Muốn việc thay đổi cấu trúc record được phản ánh qua lỗi biên dịch tại các điểm phân rã cần cập nhật.

Nên ưu tiên accessor hoặc type pattern đơn giản khi:

- Cần giữ lại toàn bộ object, gọi nhiều phương thức hoặc truyền object cho thành phần khác.
- Mức lồng nhau quá sâu khiến pattern dài hơn và khó đọc hơn logic nghiệp vụ.
- Component chứa cấu trúc mutable phức tạp cần validation chuyên biệt.
- Phải xử lý collection, map, array hoặc một class không phải record.
- Hệ thống chưa có hợp đồng null rõ ràng và pattern lồng nhau làm luồng lỗi khó theo dõi.

Một nguyên tắc thực tế: dùng record pattern để làm rõ **cấu trúc dữ liệu**, không phải để biến mọi điều kiện thành một pattern dài. Đôi khi tạo phương thức diễn đạt ý nghĩa nghiệp vụ và dùng một pattern ngắn lại dễ bảo trì hơn.

## 19. Bài tập thực hành

**Bài tập 1 — Trích xuất dữ liệu.** Khai báo **record Point(int x, int y)** và **record Rectangle(Point topLeft, Point bottomRight)**. Viết phương thức nhận Object và dùng nested record pattern để tính chiều rộng, chiều cao của Rectangle; chỉ tính khi dữ liệu hợp lệ.

**Bài tập 2 — Phân loại đơn hàng.** Khai báo **Order(String id, Customer customer)**, **Customer(String name, Address address)** và **Address(String city, String country)**. Dùng switch expression với guard để phân loại thành nội thành, trong nước và quốc tế. Thêm fallback cho record có component null và case null cho selector.

**Bài tập 3 — Sealed hierarchy.** Định nghĩa một sealed interface **CommandResult** với ba record **Success**, **Failure**, **Pending**. Dùng switch expression khớp từng record và tạo thông báo có nội dung. Sau đó thêm một biến thể mới và xem trình biên dịch yêu cầu bổ sung nhánh khi không có default.

**Bài tập 4 — Generic record.** Khai báo **Box<T>(T value)**, tạo **Box<Box<String>>**, rồi dùng record pattern lồng nhau để lấy chuỗi. Thử thay component bên trong bằng null để hiểu sự khác nhau giữa pattern **var** và một nested record pattern.

## 20. Checklist trước khi dùng trong code production

- [ ] Chỉ áp dụng record pattern cho kiểu record phù hợp.
- [ ] Kiểm tra số lượng và thứ tự component trong từng pattern.
- [ ] Dùng **var** khi suy luận kiểu giúp mã rõ ràng; dùng kiểu tường minh khi cần kiểm tra kiểu sâu hơn.
- [ ] Đặt nested record pattern ở mức lồng nhau vừa phải.
- [ ] Phân biệt null ở tầng ngoài, null component và null nested record.
- [ ] Guard **when** luôn kiểm tra null trước khi gọi phương thức có thể ném NPE.
- [ ] Đặt switch pattern cụ thể trước pattern tổng quát.
- [ ] Đảm bảo switch expression exhaustive, nhất là khi có guard hoặc sealed hierarchy.
- [ ] Dùng unnamed pattern **_** cho component thực sự không cần sử dụng.
- [ ] Giữ accessor không có tác dụng phụ và kiểm soát bất biến của record.
- [ ] Không phụ thuộc vào cú pháp preview cũ đã bị loại bỏ.
- [ ] Viết test cho null, guard false, fallback và những biến thể mới.

Record pattern giúp mã Java diễn đạt trực tiếp cấu trúc dữ liệu, đặc biệt khi record được lồng trong record khác. Khi kết hợp **instanceof**, **switch**, **when**, **sealed interface** và **_**, chương trình có thể xử lý dữ liệu theo kiểu khai báo ngắn gọn hơn mà vẫn có kiểm tra kiểu tĩnh. Để dùng hiệu quả trong Java 27, cần đặc biệt chú ý null, tính đầy đủ của switch, ranh giới dữ liệu và tác dụng phụ của accessor.

## Tài liệu tham khảo

- [Java Language Specification 27 — §14.30 Patterns](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.30): cú pháp, kiểu, cách record pattern khớp giá trị và các quy tắc null.
- [Java Language Specification 27 — §8.10 Record Classes](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10): khai báo record, record components và accessor.
- [Oracle Java SE 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html): trạng thái các tính năng đã chuẩn hóa.
- [Oracle — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): ví dụ cơ bản, nested record patterns và generic type inference.
- [Oracle Java SE 22 — Java Language Changes](https://docs.oracle.com/en/java/javase/22/language/java-language-changes.html): unnamed patterns được chuẩn hóa trong Java 22.
