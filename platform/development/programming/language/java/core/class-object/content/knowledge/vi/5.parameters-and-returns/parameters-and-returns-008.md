# Thiết kế phương thức rõ nghĩa khi có nhiều tham số trong Java

Một phương thức có nhiều tham số có thể hoàn toàn hợp lệ về cú pháp nhưng rất khó gọi cho đúng. Ví dụ:

~~~java
sendMessage("an@example.com", "Lịch họp", "Mời họp lúc 9 giờ", true, false, 3);
~~~

Người đọc khó biết `true` nghĩa là gửi ngay hay ưu tiên cao, `false` có phải lưu bản nháp hay không, và `3` là số lần thử hay thời gian chờ. Một phương thức khác với nhiều tham số `String` thậm chí cho phép **đảo nhầm vị trí các đối số mà chương trình vẫn biên dịch**.

Mục tiêu của thiết kế API là khiến **ý định của lời gọi rõ ràng**, hạn chế giá trị không hợp lệ, nhóm những dữ liệu thuộc cùng một khái niệm và giúp phương thức dễ thay đổi, kiểm thử. Số lượng tham số là một dấu hiệu cần xem xét, nhưng **không có quy tắc Java rằng một phương thức chỉ được phép có tối đa N tham số**. Vấn đề nằm ở ý nghĩa, quan hệ và khả năng sử dụng an toàn của chúng.

Bài học này tập trung vào phương thức Java 17+: cách đặt tên, sắp xếp tham số, chọn kiểu, tách trách nhiệm, dùng **parameter object**, `record`, **overload**, **builder**, kiểm tra đầu vào, xử lý tham số tùy chọn và tránh những chữ ký gây nhầm lẫn.

## 1. Vì sao nhiều tham số dễ gây lỗi?

Xét lời gọi sau:

~~~java
static void register(
        String firstName,
        String lastName,
        String email,
        String city,
        int age,
        boolean verified) {
    // Xử lý đăng ký
}

// Tại nơi gọi:
register("Mai", "Nguyen", "mai@example.com", "Ha Noi", 22, false);
~~~

Đây là **đoạn mã minh họa chữ ký API**, chưa phải một chương trình chạy độc lập. Phương thức có sáu tham số; bốn tham số đầu đều có kiểu `String`. Người gọi có thể vô tình truyền `city` vào vị trí `email` hoặc đảo `firstName` với `lastName` mà compiler không phát hiện, vì **kiểu đối số vẫn khớp**. Các lỗi này chỉ lộ ra khi kiểm thử nghiệp vụ hoặc khi có dữ liệu thực tế.

Một số tín hiệu rủi ro:

| Dấu hiệu | Rủi ro | Cải thiện có thể cân nhắc |
| --- | --- | --- |
| Nhiều tham số cùng kiểu primitive/`String` | Truyền nhầm vị trí vẫn biên dịch | Kiểu nghiệp vụ rõ tên, parameter object |
| Nhiều `boolean` liên tiếp | `true, false` không nói rõ ý nghĩa | `enum` hoặc phương thức diễn đạt hành vi |
| Nhiều tùy chọn có giá trị mặc định | Lời gọi phải truyền các giá trị “cho đủ chỗ” | Overload, options record, builder |
| Các tham số luôn xuất hiện cùng nhau | Một nhóm dữ liệu đang thiếu mô hình | `record`/class như `Address`, `DateRange` |
| Nhiều nhóm tham số phục vụ các thao tác khác nhau | Phương thức gánh nhiều trách nhiệm | Tách thành những phương thức theo hành vi |
| Quy tắc hợp lệ phụ thuộc nhiều tham số | Khó bảo toàn bất biến | Validate ở ranh giới và gom vào kiểu miền nghiệp vụ |
| Liên tục thêm tham số vào API công khai | Người gọi phải sửa nhiều nơi | Object yêu cầu/kiểu tùy chọn có chiến lược mở rộng |
| Chữ ký chứa nhiều `Object` hoặc `Map<String, Object>` | Mất thông tin kiểu, ép kiểu khi chạy | Kiểu cụ thể được compiler kiểm tra |

**Tránh chữa bằng cách gom vô điều kiện.** Một phương thức `distance(double x1, double y1, double x2, double y2)` có thể vẫn dễ hiểu trong API hình học nhỏ. Việc tạo hẳn một lớp cấu hình 20 trường cho ba tham số cố định sẽ làm thiết kế phức tạp hơn. Chọn giải pháp dựa trên những quan hệ thực của dữ liệu.

## 2. Nền tảng: Java truyền đối số theo vị trí và bằng giá trị

Trong lời gọi Java thông thường, **đối số được ghép với tham số theo vị trí**, chứ không phải theo tên tham số. Java không có cú pháp *named arguments* tổng quát cho phép viết kiểu `createUser(email = "...", age = 20)` để compiler tự sắp xếp. Dù file `.class` có thể chứa metadata tên tham số khi biên dịch với tùy chọn phù hợp, metadata ấy không biến các lời gọi Java thành named arguments.

~~~java
static void move(int horizontal, int vertical) {
    System.out.println(horizontal + ", " + vertical);
}

// Trong một method:
move(10, 20);
move(20, 10);
~~~

Cả hai lời gọi hợp lệ nhưng nghĩa khác nhau vì vị trí tham số khác nhau. Nếu `horizontal` và `vertical` là hai khái niệm nghiệp vụ rất quan trọng, kiểu `Point` có thể làm ý định rõ hơn.

Java **luôn truyền đối số bằng giá trị**:

- Với `int`, `double`, `boolean`, một giá trị nguyên thủy được chuyển cho tham số.
- Với `String`, `List<String>`, class tự định nghĩa hay mảng, giá trị tham chiếu được chuyển cho tham số. Phương thức có thể thay đổi object mutable qua tham chiếu nếu có quyền, nhưng gán lại biến tham số không gán lại biến của caller.

Thiết kế method nhiều tham số cần ghi rõ phương thức **có làm thay đổi các object được truyền vào không**. Nếu một object yêu cầu mutable được dùng chung ở nhiều nơi, việc bất ngờ sửa nó có thể nguy hiểm hơn việc chữ ký dài.

## 3. Bắt đầu từ tên method, tên tham số và thứ tự hợp lý

Trước khi thêm class mới, hãy cải thiện những yếu tố đơn giản.

### Chọn động từ thể hiện tác dụng

Chữ ký:

~~~java
void process(String id, int count, boolean mode);
~~~

mập mờ vì `process` không nói xử lý gì, `count` không có đơn vị, `mode` không rõ lựa chọn. Có thể diễn đạt thành:

~~~java
void reserveSeats(String eventId, int seatCount, ReservationMode mode);
~~~

Ở đây `reserveSeats` mô tả hành vi, `seatCount` nói rõ số lượng ghế, `ReservationMode` là kiểu diễn đạt tập lựa chọn hữu hạn. Nếu kiểu `ReservationMode` thực sự có các giá trị `STANDARD`, `PREMIUM` trong thiết kế của bạn, compiler sẽ hạn chế những giá trị được truyền vào hơn một `String` tùy ý.

Trong API cần đơn vị đo, dùng tên như `timeoutMillis`, `priceInCents` hoặc kiểu giá trị riêng, thay cho `timeout`, `price` mà ý nghĩa không rõ. Đây là đặc biệt quan trọng với số tiền, thời lượng, khoảng cách, tỷ lệ và dung lượng.

### Sắp xếp những tham số có quan hệ

Một thứ tự có thể dự đoán thường là:

1. Đối tượng hoặc định danh chính của thao tác.
2. Dữ liệu bắt buộc mô tả thao tác.
3. Các giá trị phụ thuộc hoặc ngữ cảnh.
4. Tùy chọn cấu hình nếu thiết kế vẫn dùng danh sách tham số.

Ví dụ `sendEmail(String recipient, String subject, String body)` có thứ tự thông thường dễ đọc hơn `sendEmail(String body, String recipient, String subject)`. Tuy nhiên **không đảo chữ ký API đã được sử dụng rộng rãi chỉ để đạt một trật tự lý tưởng**: thay đổi thứ tự giữa những tham số cùng kiểu có thể không tạo lỗi biên dịch nhưng làm sai hành vi tại các caller cũ.

Tên tham số tốt giúp đọc **khai báo** và được IDE hỗ trợ hiển thị tại call site, nhưng người đọc file mã nguồn chỉ nhìn một lời gọi thông thường vẫn có thể không thấy tên tham số. Khi rủi ro đảo vị trí lớn, hãy cân nhắc kiểu chuyên biệt hoặc parameter object.

## 4. Khi các giá trị thuộc cùng một khái niệm, tạo kiểu riêng

Nếu một phương thức nhận `street`, `city`, `postalCode`, đó thường là **một địa chỉ**. Có thể nhóm các giá trị thành một kiểu `Address` để ranh giới ý nghĩa rõ hơn.

~~~java
record Address(String street, String city, String postalCode) {
    Address {
        if (street == null || street.isBlank()) {
            throw new IllegalArgumentException("street is required");
        }
        if (city == null || city.isBlank()) {
            throw new IllegalArgumentException("city is required");
        }
        if (postalCode == null || postalCode.isBlank()) {
            throw new IllegalArgumentException("postalCode is required");
        }
    }
}
~~~

Đây là **khai báo kiểu minh họa**; để chạy độc lập cần đặt trong tệp nguồn và cung cấp `main` thích hợp. `record`, có từ Java 16 và dùng được trên Java 17, là lựa chọn thuận tiện cho dữ liệu có tập thành phần xác định:

- Compiler tạo accessor tên theo component: `address.street()`, `address.city()`, `address.postalCode()`.
- Compiler cung cấp `equals`, `hashCode` và `toString` dựa trên thành phần record.
- Record component có trường tương ứng `private final`; chúng không bị gán lại qua accessor.
- **Compact constructor** như `Address { ... }` có thể kiểm tra dữ liệu trước khi object hoàn tất khởi tạo.

**Record không bất biến sâu một cách tự động.** Nếu record chứa `List`, mảng hoặc object mutable, chúng vẫn có thể bị sửa thông qua alias trừ khi bạn phòng vệ khi tạo và khi trả dữ liệu.

### Dùng kiểu miền nghiệp vụ để phân biệt các giá trị cùng kiểu

Các giá trị `customerId`, `orderId`, `productId` có thể đều là `String`, nhưng mang ý nghĩa khác. Trong API phức tạp, các kiểu nhỏ có thể ngăn truyền nhầm:

~~~java
record ProductId(String value) {
    ProductId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Product ID is required");
        }
    }
}

record CustomerId(String value) {
    CustomerId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Customer ID is required");
        }
    }
}
~~~

Một method `findProduct(ProductId id)` sẽ không chấp nhận `CustomerId` chỉ vì hai kiểu cùng chứa `String`. Trình biên dịch bảo vệ **loại định danh**, còn constructor bảo vệ **giá trị hợp lệ**. Đổi lại, ứng dụng phải tạo/đọc các kiểu nhỏ này; chỉ nên áp dụng khi lợi ích về an toàn và tính diễn đạt xứng đáng với chi phí.

## 5. Parameter Object: thay một nhóm tham số bằng một yêu cầu có tên

**Parameter Object** là class/record chứa các giá trị cùng phục vụ một thao tác, thay vì bắt caller nhớ một danh sách vị trí dài. Nó phù hợp khi nhóm tham số có ý nghĩa chung, được sử dụng lặp lại, có invariant hoặc thường mở rộng theo thời gian.

Ví dụ API khó đọc:

~~~java
void placeOrder(
        String productId,
        int quantity,
        String street,
        String city,
        String postalCode,
        boolean express,
        String note);
~~~

Một lời gọi chứa bảy giá trị rời khiến khó theo dõi và dễ nhầm địa chỉ, lựa chọn vận chuyển. Ta có thể chuyển thành:

~~~java
void placeOrder(OrderRequest request);
~~~

Trong đó `OrderRequest` mô tả một thao tác đặt hàng, `Address` mô tả địa chỉ và `DeliverySpeed` mô tả lựa chọn giao hàng bằng một `enum`.

### Chương trình Java 17+ hoàn chỉnh

Lưu thành **`OrderRequestDemo.java`**:

~~~java
import java.util.Objects;

public class OrderRequestDemo {
    enum DeliverySpeed {
        STANDARD, EXPRESS
    }

    record Address(String street, String city, String postalCode) {
        Address {
            if (street == null || street.isBlank()) {
                throw new IllegalArgumentException("street is required");
            }
            if (city == null || city.isBlank()) {
                throw new IllegalArgumentException("city is required");
            }
            if (postalCode == null || postalCode.isBlank()) {
                throw new IllegalArgumentException("postalCode is required");
            }
        }

        String label() {
            return street + ", " + city + " " + postalCode;
        }
    }

    record OrderRequest(
            String productId,
            int quantity,
            Address shippingAddress,
            DeliverySpeed speed,
            String note) {

        OrderRequest {
            if (productId == null || productId.isBlank()) {
                throw new IllegalArgumentException("productId is required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
            Objects.requireNonNull(shippingAddress, "shippingAddress");
            Objects.requireNonNull(speed, "speed");
            note = note == null ? "" : note.trim();
        }
    }

    static final class OrderService {
        String describe(OrderRequest request) {
            Objects.requireNonNull(request, "request");
            return request.productId()
                    + " x" + request.quantity()
                    + " -> " + request.shippingAddress().label()
                    + " [" + request.speed() + "]"
                    + " note=" + request.note();
        }

        long totalCents(OrderRequest request, long unitPriceCents) {
            Objects.requireNonNull(request, "request");
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException("unitPriceCents must be >= 0");
            }
            return Math.multiplyExact(unitPriceCents, request.quantity());
        }
    }

    public static void main(String[] args) {
        Address address = new Address(
                "12 Nguyen Trai", "Ha Noi", "100000");
        OrderRequest request = new OrderRequest(
                "BOOK-01", 2, address,
                DeliverySpeed.EXPRESS, " Giao gio hanh chinh ");

        OrderService service = new OrderService();
        System.out.println(service.describe(request));
        System.out.println("Total cents: " + service.totalCents(request, 150_000));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 OrderRequestDemo.java
java OrderRequestDemo
~~~

Stdout:

~~~text
BOOK-01 x2 -> 12 Nguyen Trai, Ha Noi 100000 [EXPRESS] note=Giao gio hanh chinh
Total cents: 300000
~~~

**Giải thích:**

1. `Address` gom ba phần địa chỉ; constructor ngăn dữ liệu rỗng hoặc `null`.
2. `DeliverySpeed` là `enum` nên chỉ dùng các lựa chọn `STANDARD` hoặc `EXPRESS` (ngoại trừ tham chiếu `null`, đã bị kiểm tra).
3. `OrderRequest` biểu diễn toàn bộ dữ liệu của một lần đặt hàng. Caller chỉ truyền một object vào `OrderService.describe`, tránh chuỗi bảy tham số rời rạc.
4. Compact constructor chuẩn hóa `note`: null trở thành chuỗi rỗng, còn chuỗi được loại bỏ khoảng trắng đầu/cuối. Trong compact constructor, tham số record component được gán lại theo cách hợp lệ để giá trị sau chuẩn hóa được lưu vào field tương ứng.
5. `OrderService` là object cung cấp hành vi xử lý, nhận một `OrderRequest` đã được kiểm tra. Kiểm tra `request` khác null tại ranh giới method vẫn cần thiết.
6. `Math.multiplyExact` kiểm tra tràn số khi tính tổng `long`. Số tiền trong ví dụ biểu diễn dưới dạng **đơn vị tiền nhỏ nhất** bằng `long` để tránh sai số dấu phẩy động; ứng dụng thực tế còn cần quy tắc tiền tệ, thuế, tỷ giá và giao dịch.
7. `String` và `enum` trong record là bất biến theo giá trị quan sát được. `Address` chỉ chứa các `String`, nên mô hình dữ liệu này không lộ một danh sách hoặc mảng mutable qua accessor.

Lưu ý rằng **constructor của parameter object vẫn nhận nhiều tham số**, nên ở nơi tạo `OrderRequest` người dùng vẫn phải hiểu chúng. Parameter object giải quyết trước tiên việc chuyển dữ liệu qua nhiều API và quy tắc kiểm tra; nếu bước xây dựng object cũng phức tạp, có thể dùng builder hoặc factory rõ tên.

### Khi nào parameter object đáng dùng?

Nên cân nhắc khi nhóm giá trị có tên nghiệp vụ rõ, xuất hiện ở nhiều method, cần validation chung hoặc thường được chuyển qua nhiều lớp. Không nhất thiết tạo một record mới chỉ để thay mỗi phương thức có ba tham số dễ hiểu bằng một kiểu một lần dùng mà không mang ý nghĩa riêng.

Nếu các trường trong parameter object không liên quan, đó có thể là dấu hiệu bạn đã gom một **“túi tham số”** chỉ để che chữ ký dài. Hãy xem lại trách nhiệm của method trước khi tạo kiểu mới.

## 6. Boolean Flag: vì sao `true, false` làm lời gọi khó đọc?

Ví dụ:

~~~java
sendReport(report, true, false);
~~~

Nếu tham số lần lượt là `includeDetails` và `urgent`, chỉ nhìn điểm gọi rất khó biết `true` áp dụng cho hành vi gì.

Các cách cải thiện:

### Cách A — Phương thức có tên theo hành vi

Khi boolean làm phương thức chuyển sang **hai hành vi khác hẳn nhau**, có thể tách API:

~~~java
void publishReport(Report report);
void saveReportDraft(Report report);
~~~

Đây là chữ ký minh họa, yêu cầu kiểu `Report` và triển khai thích hợp. Hai tên method giúp người gọi thể hiện mục tiêu trực tiếp, thay vì `publish(report, true)` đối lập với `publish(report, false)`.

### Cách B — `enum` khi có một tập lựa chọn hữu hạn

~~~java
enum DeliveryMode {
    STANDARD, EXPRESS
}

void ship(OrderRequest request, DeliveryMode mode);
~~~

Một lời gọi `ship(request, DeliveryMode.EXPRESS)` rõ hơn `ship(request, true)`. Tuy nhiên nếu `OrderRequest` đã chứa `speed` tương đương, đừng bắt caller cung cấp hai nguồn dữ liệu trùng nhau không có quy tắc ưu tiên.

### Cách C — Options object cho nhiều tùy chọn kết hợp

Khi có các lựa chọn độc lập như định dạng, tiêu đề cột, số dòng tối đa, ngôn ngữ, hãy nhóm thành `ExportOptions`. `enum` đại diện cho **một lựa chọn** còn options object đại diện **một tập cấu hình**.

**Không phải mọi boolean đều xấu.** `setEnabled(boolean enabled)` có thể phù hợp nếu chính thuộc tính bật/tắt là khái niệm nghiệp vụ trực tiếp. Dấu hiệu cần refactor là caller thường chỉ có các literal `true`/`false` không tự giải thích, hoặc flag thay đổi rất nhiều nhánh hành vi không liên quan.

## 7. Builder: rõ nghĩa khi có nhiều tùy chọn không bắt buộc

Builder phù hợp khi object có nhiều tùy chọn với giá trị mặc định, người dùng chỉ thiết lập một phần trong số đó và đọc lời gọi sẽ dễ hơn với các method có tên. Ví dụ thay vì:

~~~java
export(data, "CSV", false, 50, "vi-VN");
~~~

có thể viết:

~~~java
ExportOptions options = ExportOptions.builder()
        .format(Format.CSV)
        .includeHeader(false)
        .maxRows(50)
        .locale(Locale.forLanguageTag("vi-VN"))
        .build();
~~~

Builder **không phải cú pháp đặc biệt của Java**: đây là một mẫu thiết kế bằng class và method. Cần có mã builder đúng để hỗ trợ fluent API.

### Ví dụ Java 17+ hoàn chỉnh với mặc định và validation

Lưu file **`BuilderOptionsDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class BuilderOptionsDemo {
    enum Format {
        CSV, JSON
    }

    static final class ExportOptions {
        private final Format format;
        private final boolean includeHeader;
        private final int maxRows;
        private final Locale locale;

        private ExportOptions(Builder builder) {
            this.format = builder.format;
            this.includeHeader = builder.includeHeader;
            this.maxRows = builder.maxRows;
            this.locale = builder.locale;
        }

        static Builder builder() {
            return new Builder();
        }

        String describe() {
            return format
                    + " / header=" + includeHeader
                    + " / maxRows=" + maxRows
                    + " / locale=" + locale.toLanguageTag();
        }

        static final class Builder {
            private Format format = Format.JSON;
            private boolean includeHeader = true;
            private int maxRows = 100;
            private Locale locale = Locale.ROOT;

            Builder format(Format value) {
                format = Objects.requireNonNull(value, "format");
                return this;
            }

            Builder includeHeader(boolean value) {
                includeHeader = value;
                return this;
            }

            Builder maxRows(int value) {
                if (value <= 0) {
                    throw new IllegalArgumentException("maxRows must be positive");
                }
                maxRows = value;
                return this;
            }

            Builder locale(Locale value) {
                locale = Objects.requireNonNull(value, "locale");
                return this;
            }

            ExportOptions build() {
                return new ExportOptions(this);
            }
        }
    }

    public static void main(String[] args) {
        ExportOptions options = ExportOptions.builder()
                .format(Format.CSV)
                .includeHeader(false)
                .maxRows(50)
                .locale(Locale.forLanguageTag("vi-VN"))
                .build();

        ExportOptions defaults = ExportOptions.builder().build();

        System.out.println(options.describe());
        System.out.println(defaults.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 BuilderOptionsDemo.java
java BuilderOptionsDemo
~~~

Stdout:

~~~text
CSV / header=false / maxRows=50 / locale=vi-VN
JSON / header=true / maxRows=100 / locale=und
~~~

Ở đây `Locale.ROOT.toLanguageTag()` trả `und`, đại diện ngôn ngữ không xác định; đó là lựa chọn mặc định được ví dụ thiết lập có chủ đích. Trong ứng dụng thật có thể chọn locale mặc định tường minh theo nhu cầu, nhưng đừng âm thầm dùng locale hệ thống nếu kết quả phải ổn định giữa máy chạy.

**Điểm mạnh của builder:**

- Mỗi lệnh `.maxRows(50)`, `.locale(...)` gắn tên với ý nghĩa của giá trị.
- Người gọi có thể chỉ cung cấp tùy chọn cần thay đổi; các mục khác dùng default.
- Kiểm tra đầu vào ở setter method hoặc `build()` giúp tạo object trong trạng thái hợp lệ.
- Object `ExportOptions` cuối cùng có các field `final`, và không lộ setter trực tiếp sau khi được tạo.

**Giới hạn:** Builder cần thêm class/method và có khả năng được dùng sai nếu mặc định không phù hợp. Nếu có **tham số bắt buộc**, hãy cân nhắc đặt chúng vào constructor/builder factory hoặc xác nhận tại `build()`. Đừng cho phép người gọi tạo object “hợp lệ về kiểu” nhưng thiếu thuộc tính thiết yếu chỉ vì mọi field được mặc định về null.

## 8. Khi nào dùng overload thay vì builder?

**Method overloading** cho phép nhiều phương thức cùng tên nhưng khác chữ ký tham số. Nó phù hợp với **một số biến thể nhỏ, ổn định**, đặc biệt khi có mặc định rõ ràng.

~~~java
static String greet(String name) {
    return greet(name, "Xin chào");
}

static String greet(String name, String prefix) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("name is required");
    }
    if (prefix == null) {
        throw new IllegalArgumentException("prefix is required");
    }
    return prefix + ", " + name;
}
~~~

Đây là hai method minh họa có thể đặt trong cùng class. `greet("Mai")` gọi overload có một tham số rồi ủy quyền sang overload chính. `greet("Mai", "Chào buổi sáng")` cho phép cung cấp lời chào khác.

Tuy nhiên, nếu có năm tùy chọn độc lập và mỗi tùy chọn có hai trạng thái, số tổ hợp có thể lên đến `2^5 = 32`. Không nên tạo hàng chục overload chỉ để mô phỏng default/named arguments. Với nhiều tùy chọn độc lập, **options object hoặc builder** dễ bảo trì hơn.

### Đoạn mã chạy minh họa overload

Lưu file **`OverloadDemo.java`**:

~~~java
public class OverloadDemo {
    static String greet(String name) {
        return greet(name, "Xin chào");
    }

    static String greet(String name, String prefix) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (prefix == null) {
            throw new IllegalArgumentException("prefix is required");
        }
        return prefix + ", " + name;
    }

    public static void main(String[] args) {
        System.out.println(greet("Mai"));
        System.out.println(greet("Mai", "Chào buổi sáng"));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverloadDemo.java
java OverloadDemo
~~~

Stdout:

~~~text
Xin chào, Mai
Chào buổi sáng, Mai
~~~

Overload **không được phân biệt chỉ bởi kiểu trả về**. Hai method trùng tên và cùng danh sách tham số nhưng một trả `int`, một trả `String` sẽ gây lỗi khai báo trùng. Compiler chọn overload dựa trên các quy tắc về danh sách tham số, kiểu đối số và chuyển đổi được phép; không thể dựa vào kiểu biến nhận kết quả để chọn hai method chỉ khác return type.

## 9. Tránh overload mơ hồ với `null`, boxing và varargs

Overload nhiều đôi khi khiến API khó sử dụng hơn. Xét hai method:

~~~java
static void search(String query) { /* ... */ }
static void search(Integer limit) { /* ... */ }
~~~

Lời gọi `search(null)` là **mơ hồ tại compile time** vì null có thể chuyển thành cả `String` và `Integer`; không kiểu nào cụ thể hơn kiểu kia theo quan hệ subtype để phá thế hòa. Phải ép kiểu tường minh hoặc, tốt hơn, đặt tên API/kiểu input sao cho người gọi không rơi vào trường hợp khó hiểu.

Đây là **mã minh họa**, dấu `/* ... */` thể hiện thân phương thức trống hợp lệ nhưng không có nghiệp vụ cụ thể. Không dùng ví dụ này làm chương trình chạy độc lập.

### Primitive, wrapper và lựa chọn overload

~~~java
static void accept(long value) {
    System.out.println("long");
}

static void accept(Integer value) {
    System.out.println("Integer");
}
~~~

Với lời gọi `accept(5)` (literal kiểu `int`), Java ưu tiên widening primitive `int → long` so với boxing `int → Integer` trong bộ quy tắc overload này, nên chọn `accept(long)`. Nếu API có nhiều overload khác nhau ở primitive/wrapper và người gọi truyền `null`, độ phức tạp có thể tăng nhanh.

**Nguyên tắc:** Overload nên đại diện cho những cách gọi thực sự hữu ích, dễ đoán. Đừng tạo overload chỉ vì kỹ thuật cho phép.

### Varargs không thay thế parameter object

~~~java
static int sum(int... numbers) {
    int result = 0;
    for (int number : numbers) {
        result = Math.addExact(result, number);
    }
    return result;
}
~~~

`int...` là varargs: khi vào thân method, `numbers` có kiểu `int[]`. Varargs thích hợp cho **nhiều giá trị đồng nhất về vai trò** (các số cần tính tổng, các mục cần ghi log). Nó không phù hợp với những vị trí có ý nghĩa khác nhau như số tiền, số lần thử và số giây timeout, dù cả ba cùng kiểu `int`.

Một varargs parameter phải là **tham số cuối cùng** trong khai báo. Varargs thường tạo mảng tương ứng khi gọi với nhiều giá trị rời; nếu caller truyền trực tiếp một mảng đúng kiểu, method có thể dùng chính mảng đó. Phương thức nên nói rõ có thay đổi phần tử của mảng input hay không. Với varargs kiểu tham chiếu và generic còn có các cảnh báo/giới hạn về heap pollution cần xử lý ở bài nâng cao.

## 10. Phân biệt dữ liệu bắt buộc và dữ liệu tùy chọn

Một method có nhiều tham số dễ khó dùng vì trộn những điều **phải có** với những lựa chọn **có thể bỏ qua**. Ví dụ cần phân loại:

| Loại | Ví dụ | Hướng thiết kế |
| --- | --- | --- |
| Bắt buộc để định danh thao tác | `productId`, `customerId` | Yêu cầu rõ tại constructor/factory |
| Bắt buộc để bảo đảm nghiệp vụ | `quantity > 0`, `shippingAddress` | Validate lúc tạo request |
| Tùy chọn với mặc định rõ | `format = JSON`, `maxRows = 100` | Options object, builder hoặc overload |
| Tùy chọn nhưng có ý nghĩa “không cung cấp” | `note`, `filter` | Định nghĩa quy tắc vắng mặt rõ ràng |
| Dữ liệu ngữ cảnh không nên cho caller chọn | Logger nội bộ, cấu hình ứng dụng | Cân nhắc state/dependency của service thay vì thêm vào mọi method |

**Không dùng `null` như một tín hiệu mặc định ngầm** nếu điều đó khiến người gọi không biết contract. Ví dụ `export(data, null, -1, false)` khó hiểu và khó validate. Hãy quyết định một trong các chính sách: từ chối null, chuyển null thành mặc định có tài liệu, hoặc biểu diễn sự vắng mặt bằng kiểu rõ hơn.

Trong nhiều API, `Optional<T>` hữu ích ở **kiểu trả về** để thể hiện có hoặc không có kết quả. Dùng `Optional` làm tham số không mặc nhiên tốt hơn null: nó buộc người gọi tạo `Optional.of(...)` hoặc `Optional.empty()` và vẫn không giải quyết vấn đề chữ ký có quá nhiều vị trí. Với cấu hình nhiều lựa chọn, một field tùy chọn trong request/options object hoặc builder thường rõ ràng hơn.

Nếu dùng overloaded factory, hãy xác định rõ giá trị mặc định nằm ở **một nơi**, ví dụ overload ít tham số gọi overload chính. Tránh mỗi overload sao chép một nhánh xử lý rồi vô tình khác logic theo thời gian.

## 11. Validation theo từng field và giữa các field

Nhiều tham số thường có ràng buộc **liên quan lẫn nhau**. Ví dụ một khoảng thời gian yêu cầu `start` trước `end`; số lượng phải dương; nếu giao nhanh thì phương án vận chuyển phải hỗ trợ.

Với `record`, có thể giữ quy tắc bất biến trong constructor:

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRange(LocalDate start, LocalDate end) {
    DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException("end must be >= start");
        }
    }
}
~~~

Đây là **khai báo kiểu minh họa**; để chạy độc lập cần thêm một class có `main`. Hai tham số không nên tồn tại như hai ngày tùy ý nếu logic luôn yêu cầu một **DateRange** hợp lệ. Khi đã có kiểu miền nghiệp vụ, các method khác có thể nhận `DateRange` mà không phải viết lại phép kiểm tra hai ngày.

**Cần chọn quy tắc đúng nghiệp vụ.** Điều kiện `end.isBefore(start)` là ví dụ quy định **cho phép khoảng có cùng start và end**. Nếu hệ thống yêu cầu khoảng không rỗng hoặc tính điểm kết thúc exclusive, điều kiện cần được sửa rõ ràng, không âm thầm áp dụng quy tắc của ví dụ.

### Kiểm tra ở đâu?

1. Với **kiểu giá trị được tái sử dụng**, validate ngay khi tạo để ngăn trạng thái không hợp lệ lan qua nhiều method.
2. Với **quy tắc riêng của thao tác**, kiểm tra ở phương thức xử lý. Ví dụ giới hạn số lượng dựa trên tồn kho hiện tại không thể được bảo đảm chỉ bằng constructor của request.
3. Với **đầu vào bên ngoài**, kiểm tra cả lỗi thiếu dữ liệu, format và logic trước khi thay đổi trạng thái hoặc thực hiện tác vụ không thể hoàn tác.
4. Với nhiều tham số liên hệ với nhau, tránh việc chỉ validate từng field mà bỏ sót invariant tổng thể.

Ví dụ `Objects.requireNonNull(address)` giúp thất bại sớm khi đầu vào vắng mặt; thông điệp ngoại lệ có thể hữu ích khi debug. Nhưng cần phân biệt: lỗi `null` không tự động đồng nghĩa với lỗi nghiệp vụ. Nếu `null` là giá trị cho phép, thiết kế và tài liệu phải nói rõ.

## 12. Chữ ký dài đôi khi là dấu hiệu phương thức làm nhiều việc

Không phải lúc nào giải pháp cũng là `record Request(a, b, c, d, e, f)`. Xét:

~~~java
void processOrder(
        String productId,
        int quantity,
        String paymentToken,
        String email,
        boolean notifyCustomer,
        String auditFilePath);
~~~

Phương thức vừa đặt hàng, xử lý thanh toán, gửi thông báo vừa ghi file audit. Nhiều tham số có thể phản ánh **quá nhiều trách nhiệm**.

Hãy phân biệt:

- **Những dữ liệu định nghĩa một thao tác thống nhất:** có thể gom thành `OrderRequest`.
- **Những dịch vụ hoặc phụ thuộc cần thiết để thực hiện thao tác:** có thể được cung cấp qua constructor của service, dependency injection hoặc thành phần cộng tác, tùy thiết kế ứng dụng.
- **Những hành vi độc lập với điều kiện riêng:** có thể tách thành phương thức/tầng chức năng độc lập rồi phối hợp qua một quy trình.

Một ví dụ tổ chức ở mức ý tưởng:

~~~java
Order order = orderService.create(request);
PaymentReceipt receipt = paymentService.charge(order, payment);
notificationService.sendConfirmation(order, receipt);
~~~

Đây là **pseudocode Java mô tả cách chia trách nhiệm**; các kiểu và method chưa được định nghĩa nên không phải ví dụ có thể biên dịch độc lập. Mục đích là biểu diễn sự phân chia hành vi, không khuyên mọi ứng dụng phải có ba service ngay từ đầu.

Đừng đưa tất cả phụ thuộc vào một options object chỉ để method còn một tham số. Một request dùng để biểu diễn **dữ liệu của một thao tác** khác với một service chứa **các cộng tác viên phục vụ hành vi**.

## 13. Thiết kế method nhận nhiều object mutable

Một parameter object có thể chứa mảng, list hoặc map. Trong Java, chuyển parameter object vào method vẫn là **pass-by-value của tham chiếu**; nếu object chứa tham chiếu mutable, caller có thể quan sát thay đổi ngoài ý muốn.

### Ví dụ: record có List cần bản sao phòng vệ

Tạo file **`SafeBatchRequestDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SafeBatchRequestDemo {
    record BatchRequest(List<String> itemIds, int retryCount) {
        BatchRequest {
            Objects.requireNonNull(itemIds, "itemIds");
            if (itemIds.isEmpty()) {
                throw new IllegalArgumentException("itemIds must not be empty");
            }
            if (retryCount < 0) {
                throw new IllegalArgumentException("retryCount must be >= 0");
            }
            itemIds = List.copyOf(itemIds);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");
        source.add("B");

        BatchRequest request = new BatchRequest(source, 2);
        source.add("C");

        System.out.println("Source: " + source);
        System.out.println("Request: " + request.itemIds());

        try {
            request.itemIds().add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Request list cannot be changed");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SafeBatchRequestDemo.java
java SafeBatchRequestDemo
~~~

Stdout:

~~~text
Source: [A, B, C]
Request: [A, B]
Request list cannot be changed
~~~

`List.copyOf` tạo một danh sách không thể thay đổi qua API mutation thông thường và không chia sẻ trạng thái cấu trúc mutable từ `ArrayList source`. Việc thêm `C` vào `source` không thêm vào `request.itemIds()`.

Các điểm cần cân nhắc:

- `List.copyOf` không chấp nhận phần tử null; nếu dữ liệu cho phép null phải chọn chiến lược khác.
- Với các phần tử là **object mutable**, đây là **bản sao nông** theo tham chiếu từng phần tử: một object phần tử có thể vẫn bị thay đổi qua alias khác.
- Một field `final` không bảo vệ tính bất biến của phần tử trong collection.
- Nếu method chỉ cần **đọc** list và không lưu lại tham chiếu, đôi khi không cần copy; cần quyết định dựa trên contract và chi phí.

Nên ghi rõ method có sửa input hay không, nó sở hữu object hay chỉ mượn tham chiếu để đọc, và caller có thể tái sử dụng request không. Tránh thay đổi list/map đầu vào một cách bất ngờ chỉ vì ngôn ngữ cho phép.

## 14. API công khai và khả năng tương thích khi thêm tham số

Giả sử API ban đầu là:

~~~java
void send(String recipient, String subject, String body);
~~~

Sau này cần thêm `priority`. Đổi hẳn chữ ký sang bốn tham số làm mã caller cũ không còn biên dịch được với API mới. Với thư viện Java đã phát hành, thay descriptor phương thức còn có thể ảnh hưởng **binary compatibility**: mã đã biên dịch sẵn tìm chữ ký cũ có thể gặp lỗi linkage như `NoSuchMethodError` nếu phiên bản thư viện mới xóa method cũ.

Hướng phát triển có thể là:

~~~java
void send(String recipient, String subject, String body) {
    send(recipient, subject, body, Priority.NORMAL);
}

void send(
        String recipient,
        String subject,
        String body,
        Priority priority) {
    // Triển khai thực tế.
}
~~~

Đây là **mẫu minh họa API**, đòi hỏi `Priority` và thân xử lý phù hợp nếu muốn biên dịch thành chương trình chạy. Overload ba tham số được giữ lại và ủy quyền sang phương thức mới. Với API mới thiết kế từ đầu, request object như `SendMessageRequest` có thể giảm việc phải thay đổi mọi chữ ký khi thêm các tùy chọn có mặc định hợp lý.

Nhưng **thêm component vào public record không tự bảo đảm tương thích**: constructor tổng hợp, cấu trúc record, accessor và code người dùng có thể chịu ảnh hưởng. Nếu cần ổn định một API thư viện lâu dài, hãy xem xét lựa chọn builder/class với constructor riêng, versioning và chính sách tương thích thay vì tin rằng record luôn dễ mở rộng.

### Tối ưu cho call site hay cho nơi khai báo?

Một method được định nghĩa một lần nhưng gọi ở hàng trăm nơi. Việc thêm một request object có thể khiến declaration ngắn đi, song phải đo chi phí đọc/tạo object ở các call site. Đánh giá ít nhất:

- Call site có nói rõ ý định không?
- Người gọi có thể truyền nhầm tham số cùng kiểu không?
- Kiểu request có ý nghĩa độc lập và validate được không?
- API có phải dùng ổn định qua nhiều phiên bản không?
- Có sinh ra quá nhiều lớp tạm chỉ để giảm số lượng dấu phẩy không?

Thiết kế rõ nghĩa nằm ở **khả năng hiểu và dùng đúng API**, không phải chỉ ở độ dài chữ ký.

## 15. Quy tắc chọn giải pháp cho từng dạng tham số

| Tình huống | Giải pháp thường hợp lý | Lưu ý |
| --- | --- | --- |
| 2–3 tham số bắt buộc, khác ý nghĩa rõ | Giữ các tham số trực tiếp | Chọn tên và thứ tự dễ đoán |
| Nhiều thành phần tạo một khái niệm | Value object / `record` | Validate invariant; cân nhắc immutable |
| Nhiều thông số mô tả một yêu cầu | Parameter object | Đừng tạo “data bag” vô nghĩa |
| Nhiều tùy chọn độc lập với default | Builder hoặc options class | Kiểm tra các giá trị bắt buộc tại `build()` |
| Một vài biến thể đơn giản | Overload ủy quyền về triển khai chính | Tránh explosion số overload |
| Hai chế độ hành vi khác rõ rệt | Hai method có tên rõ | Hạn chế boolean flag mập mờ |
| Một lựa chọn trong tập cố định | `enum` | Vẫn phải quy định có cho null không |
| Nhiều giá trị cùng ý nghĩa, số lượng thay đổi | Varargs hoặc collection | Không dùng cho vai trò tham số khác nhau |
| Nhiều primitive giống nhau, đơn vị khác | Tên có đơn vị hoặc domain type | Tránh “primitive obsession” khi rủi ro đáng kể |
| Method gồm nhiều trách nhiệm độc lập | Tách method/service | Không chỉ bọc mọi tham số vào một object |

Bảng là gợi ý đánh giá, không phải công thức bắt buộc. Có những API toán học nhiều tham số nhưng luôn rõ nghĩa; cũng có những API hai boolean mà ngay lập tức nên sửa.

## 16. Kiểm thử phương thức nhiều tham số

Hãy kiểm tra **đúng hành vi**, **thứ tự đối số**, **giá trị biên** và **invariant chung**. Một test tốt cố gắng phát hiện những lỗi mà compiler không thấy.

### Các nhóm ca thử nên có

1. **Happy path:** các tham số hợp lệ tạo kết quả đúng.
2. **Truyền nhầm vị trí:** với các tham số cùng kiểu, đặt dữ liệu phân biệt rõ để phát hiện hoán vị; cân nhắc thay kiểu để compiler loại lỗi.
3. **Thiếu dữ liệu bắt buộc:** null, chuỗi rỗng, mảng hoặc collection rỗng tùy hợp đồng.
4. **Giới hạn:** `quantity = 0`, số âm, cực đại, tràn số hoặc ngày kết thúc trước ngày bắt đầu.
5. **Tùy chọn bỏ trống:** builder/defaults hoạt động đúng; không sinh trạng thái chưa được xác định.
6. **Tương tác giữa tham số:** hai lựa chọn không tương thích phải bị từ chối hoặc được chuẩn hóa có chủ đích.
7. **Mutable input:** method không vô tình làm thay đổi mảng/list của caller nếu hợp đồng là chỉ đọc.
8. **Overload:** đúng phương thức được chọn với primitive, wrapper, subtype và null khi có liên quan.

### Bài kiểm chứng không cần thư viện test

Tạo file **`ParameterDesignCheck.java`**:

~~~java
import java.util.Objects;

public class ParameterDesignCheck {
    record Range(int startInclusive, int endExclusive) {
        Range {
            if (endExclusive < startInclusive) {
                throw new IllegalArgumentException("invalid range");
            }
        }
    }

    static int length(Range range) {
        Objects.requireNonNull(range, "range");
        return Math.subtractExact(
                range.endExclusive(), range.startInclusive());
    }

    static void assertEquals(int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected=" + expected + ", actual=" + actual);
        }
    }

    public static void main(String[] args) {
        assertEquals(5, length(new Range(3, 8)));
        assertEquals(0, length(new Range(4, 4)));

        try {
            new Range(8, 3);
            throw new AssertionError("invalid range was accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("Rejected invalid range");
        }

        System.out.println("All checks passed");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ParameterDesignCheck.java
java ParameterDesignCheck
~~~

Stdout:

~~~text
Rejected invalid range
All checks passed
~~~

`Range` gom hai số tạo **một khoảng có điểm cuối exclusive**, constructor ngăn `endExclusive < startInclusive`. `length` nhận một ý nghĩa duy nhất thay vì hai số nguyên không có tên tại điểm gọi.

Ví dụ kiểm tra:
- Khoảng `[3, 8)` có độ dài 5.
- Khoảng `[4, 4)` có độ dài 0 và được cho phép.
- Khoảng `[8, 3)` bị từ chối tại constructor.

Cách kiểm chứng bằng `AssertionError` này chạy được mà không cần thư viện bổ sung; ứng dụng thật có thể dùng JUnit để tổ chức test. Trong ví dụ, `Math.subtractExact` bảo vệ phép trừ số nguyên trước hiện tượng tràn số. Nếu phạm vi đầu vào bao gồm cả các giá trị `int` cực trị và độ dài thật vượt miền `int`, API cần lựa chọn kiểu kết quả phù hợp, chẳng hạn `long`.

## 17. Lỗi thường gặp khi refactor nhiều tham số

| Lỗi thiết kế | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gom mọi tham số vào `Map<String, Object>` | Compiler mất khả năng kiểm tra kiểu; typo key chỉ lộ lúc chạy | Dùng class/record có field cụ thể |
| Dùng nhiều `boolean` và số “magic” | Call site khó hiểu | `enum`, tên method, domain type |
| Thêm overload cho mọi tổ hợp tùy chọn | Số chữ ký phình to, khó bảo trì | Options object/builder với defaults |
| Builder không kiểm tra trường bắt buộc | `build()` tạo object bất hợp lệ | Validate trước khi trả object |
| Parameter object chứa các dữ liệu không liên quan | Chỉ chuyển sự phức tạp sang nơi khác | Xem lại trách nhiệm của method |
| Record chứa collection mutable mà không copy | Caller có thể sửa dữ liệu sau khi tạo | Defensive copy và tài liệu về tính bất biến |
| Tùy chọn null không có hợp đồng | Cùng một lời gọi được hiểu khác nhau | Chọn chính sách null/default rõ ràng |
| Chuyển String sang enum nhưng parse đầu vào sai | Lỗi runtime khó hiểu tại biên hệ thống | Validate và ánh xạ input ngoài thành enum tại ranh giới |
| Đổi thứ tự nhiều String trong API cũ | Vẫn biên dịch nhưng truyền dữ liệu sai | Duy trì overload hoặc chuyển đổi có kế hoạch và test |
| Đổi public constructor/record không kiểm tra caller | Mất source/binary compatibility | Xem xét API compatibility và hướng version |
| Gán lại parameter rồi mong sửa biến caller | Caller không nhận giá trị mới | Dùng return hoặc sửa object qua API có chủ đích |
| Thay mọi method ngắn bằng builder | Nhiều mã thừa và khó đọc | Chỉ dùng builder khi có đủ lựa chọn và giá trị mặc định |

## 18. Bài tập áp dụng

### Bài 1 — Nâng cấp API gửi thông báo

Cho chữ ký:

~~~java
void notifyUser(
        String userId,
        String title,
        String content,
        boolean urgent,
        boolean saveCopy,
        int retryCount);
~~~

Hãy thiết kế lại sao cho call site không chứa hai boolean không rõ nghĩa. Gợi ý:

- Tạo `NotificationRequest` gom `userId`, `title`, `content` và các lựa chọn thuộc cùng một thông báo.
- Dùng `enum Priority { NORMAL, URGENT }` nếu đây thực sự là tập giá trị nghiệp vụ.
- Cho `retryCount` mặc định hợp lý bằng builder/options, có ràng buộc không âm và giới hạn trên phù hợp.
- Tự giải thích khi nào `saveCopy` nên là một option, khi nào nên tách thành một hành vi riêng.
- Viết test cho trường hợp không có `title` hoặc `retryCount < 0`.

### Bài 2 — Tìm lỗi đảo tham số

~~~java
void transfer(String fromAccountId, String toAccountId, long amountCents);
~~~

Đặt hai ID khác nhau và một số tiền dễ nhận biết. Trong review, những lời gọi dùng `transfer(destination, source, amount)` có thể **hợp lệ về kiểu nhưng ngược hướng chuyển tiền**. Hãy đề xuất kiểu `AccountId` hoặc `TransferRequest`, viết điều kiện kiểm tra số tiền dương và xem xét việc cấm cùng tài khoản nguồn/đích nếu quy tắc nghiệp vụ yêu cầu.

### Bài 3 — Khi nào không nên tạo builder?

Xét `calculateArea(double width, double height)` và `drawPixel(int x, int y)`. Với bài toán đơn giản, hai tham số bắt buộc có thể rõ nghĩa đủ; hãy giải thích vì sao một builder có thể là thiết kế quá mức. Sau đó tưởng tượng cần thêm đơn vị đo, hệ tọa độ, phép biến đổi và chế độ vẽ; đánh giá lúc nào cần kiểu chuyên biệt hoặc options.

### Bài 4 — Record chứa dữ liệu mutable

Tạo record `TeamRequest(List<String> members, String teamName)`, xác định phương thức nào kiểm tra tên, cấm thành viên null và sao chép danh sách để caller không sửa nội dung yêu cầu sau khi tạo. Viết test:
- `members` ban đầu gồm hai phần tử.
- Sau khi tạo request, thêm phần tử vào list ban đầu.
- `request.members()` không đổi theo list ban đầu.
- Thử sửa list trả về, mong ngoại lệ nếu thiết kế dùng `List.copyOf`.

### Bài 5 — Thiết kế overload an toàn

Cho hai chữ ký `search(String query)` và `search(Integer limit)`, giải thích vì sao `search(null)` không biên dịch. Đề xuất tên rõ nghĩa `searchByText(String query)` và `searchWithLimit(int limit)`, hoặc một kiểu `SearchRequest`, tùy nghiệp vụ. Cần chỉ ra overload resolution dựa trên **kiểu đối số**, không dựa vào tên biến.

## 19. Checklist review trước khi công khai một method

- [ ] **Tên method:** người đọc biết method làm gì, có side effect hay chỉ tính kết quả.
- [ ] **Tên và đơn vị tham số:** số đếm, số tiền, mili giây, thời điểm và trạng thái được biểu diễn rõ.
- [ ] **Thứ tự:** các tham số cùng kiểu có rủi ro đảo nhầm không?
- [ ] **Nhóm khái niệm:** địa chỉ, khoảng thời gian hoặc yêu cầu có nên là kiểu riêng?
- [ ] **Boolean/primitive:** literal `true`, `false`, `0`, `1` tại call site có khó giải thích?
- [ ] **Bắt buộc/tùy chọn:** có giá trị mặc định hợp lý và được áp dụng nhất quán?
- [ ] **Validation:** có kiểm tra null, giới hạn, ràng buộc giữa các trường và trạng thái hợp lệ?
- [ ] **Aliasing:** method có sửa object/mảng/list đầu vào không, điều đó đã rõ trong hợp đồng chưa?
- [ ] **Builder/overload:** lựa chọn nào đơn giản hơn cho phần lớn caller?
- [ ] **Khả năng thay đổi:** nếu thêm tùy chọn, code caller cũ và binary compatibility bị ảnh hưởng ra sao?
- [ ] **Mức trách nhiệm:** nhiều tham số có đang che giấu một method làm quá nhiều việc?
- [ ] **Kiểm thử:** có case bình thường, case biên, case không hợp lệ và case đảo nhầm tham số?

**Nguyên tắc kết thúc:** Một API tốt không nhất thiết có ít tham số nhất. Một API tốt giúp người sử dụng **hiểu đúng dữ liệu cần cung cấp, tránh truyền sai vị trí, biết điều kiện hợp lệ và dự đoán được tác động của lời gọi**. Khi nhiều tham số cùng diễn tả một khái niệm, hãy mô hình hóa chúng thành một kiểu có tên và ràng buộc rõ. Khi có nhiều tùy chọn độc lập, dùng overload nhỏ gọn hoặc builder. Khi chữ ký dài vì phương thức đang làm nhiều việc, hãy xem lại trách nhiệm thay vì chỉ gói mọi giá trị vào một đối tượng.
