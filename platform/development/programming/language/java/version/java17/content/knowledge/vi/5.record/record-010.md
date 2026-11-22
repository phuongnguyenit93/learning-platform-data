# Giới hạn kế thừa, trường đối tượng và khối khởi tạo trong Record (Java 17)

## 1. Record được thiết kế để giải quyết vấn đề gì?

Trong Java 17, `record` là một cách khai báo lớp dành cho **những đối tượng được xác định chủ yếu bằng một tập dữ liệu cố định**. Thay vì tự viết trường, constructor, accessor, `equals()`, `hashCode()` và `toString()`, lập trình viên mô tả dữ liệu qua **record components** ngay trên dòng khai báo.

Ví dụ:

~~~java
public record ProductView(String sku, String name, long priceInCents) {
}
~~~

Từ khai báo đó, trình biên dịch tạo các thành phần cần thiết, về mặt sử dụng tương đương với:

- Ba trường instance `private final`: `sku`, `name`, `priceInCents`.
- Constructor chuẩn nhận ba tham số tương ứng.
- Các accessor `sku()`, `name()`, `priceInCents()`.
- `equals()` và `hashCode()` dựa trên các component.
- `toString()` biểu diễn tên record và các component.

~~~java
ProductView p = new ProductView("BK-17", "Java 17", 250_000L);

System.out.println(p.sku());          // BK-17
System.out.println(p.priceInCents());  // 250000
System.out.println(p);
~~~

Trong ứng dụng, record phù hợp với DTO, kết quả tính toán, dữ liệu snapshot, value object hoặc một nhánh dữ liệu của sealed hierarchy khi các ràng buộc về cấu trúc thích hợp.

**Điểm cốt lõi:** Record không chỉ là công cụ giảm mã lặp. Một record có **mô hình trạng thái và kế thừa bị ràng buộc**: không thể có superclass tùy ý, không thể khai báo thêm trường instance, và không thể dùng instance initializer block. Đây là những quyết định có chủ đích của ngôn ngữ nhằm giữ cấu trúc dữ liệu rõ ràng.

Record được chuẩn hóa từ Java 16 (JEP 395), vì vậy **có thể dùng ổn định trên Java 17 mà không cần bật preview**.

## 2. Hình dung cấu trúc một record

Xét:

~~~java
public record BookingSnapshot(
        String bookingId,
        int guestCount,
        boolean confirmed
) {
}
~~~

Ba tên trong dấu ngoặc khai báo record là **components**. Chúng xác định tập trạng thái được công khai về mặt mô hình dữ liệu:

~~~text
BookingSnapshot
├── component bookingId: String
│   ├── private final field bookingId
│   └── public accessor bookingId()
├── component guestCount: int
│   ├── private final field guestCount
│   └── public accessor guestCount()
└── component confirmed: boolean
    ├── private final field confirmed
    └── public accessor confirmed()

Canonical constructor:
    BookingSnapshot(String bookingId, int guestCount, boolean confirmed)
~~~

Đây là sơ đồ khái niệm. Không cần tự viết các field, accessor và constructor nếu chấp nhận hành vi do compiler sinh ra.

Một record có thể chứa **method, static field, static initializer, constructor tùy chỉnh và nested type** theo các quy tắc của Java. Nhưng nó không cho phép mở rộng trạng thái instance bằng field bổ sung nằm ngoài header.

## 3. Giới hạn kế thừa: Record là lớp final

### 3.1. Record ngầm định là `final`

Mọi record đều là lớp **`final` ngầm định**. Không được khai báo lớp con kế thừa record:

~~~java
record Money(long amountInCents) {
}

// KHÔNG HỢP LỆ: không được extends một record.
// class DiscountedMoney extends Money {
//     DiscountedMoney(long amountInCents) {
//         super(amountInCents);
//     }
// }
~~~

Đây là sự khác biệt quan trọng so với class thông thường. Một record mô tả tập component cố định; nếu có subclass, subclass có thể đưa vào những trạng thái instance khác và làm thay đổi ý nghĩa của mô hình dữ liệu.

Một số hệ quả:

- Không có `abstract record` để bắt buộc lớp con triển khai.
- Không có `sealed record` hoặc `non-sealed record` để tạo thêm nhánh kế thừa.
- Viết `final record` là không cần thiết; compiler đã áp dụng tính chất `final`.
- Không thể thiết kế mô hình bằng cách tạo một record gốc rồi extends nó để thêm component.

Ví dụ thiết kế không đúng:

~~~java
// Ý tưởng dưới đây KHÔNG hợp lệ:
// record Person(String name) {}
// record Employee(String name, long employeeId) extends Person(name) {}
~~~

Nếu `Employee` và `Person` là hai loại dữ liệu độc lập, hãy dùng record riêng hoặc tạo composition:

~~~java
record PersonName(String value) {
}

record Employee(PersonName personName, long employeeId) {
}
~~~

Composition diễn đạt **Employee có PersonName**. Nó phù hợp khi muốn tái sử dụng một phần dữ liệu mà không tạo quan hệ kế thừa không hợp lệ.

### 3.2. Record đã kế thừa `java.lang.Record`

Về mô hình lớp, mỗi record trực tiếp kế thừa `java.lang.Record` do Java xác định:

~~~text
java.lang.Object
       │
java.lang.Record
       │
BookingSnapshot  (final)
~~~

Vì vậy, bạn **không thể** tự thêm `extends BaseEntity`, `extends AbstractDto` hay bất kỳ superclass tùy ý nào vào một khai báo record.

~~~java
class BaseEntity {
    private final String id;

    BaseEntity(String id) {
        this.id = id;
    }
}

// KHÔNG HỢP LỆ: record không được extends BaseEntity.
// record OrderView(String id, long total) extends BaseEntity { }
~~~

Tương tự, bạn không thể tự tạo class thường extends `java.lang.Record` để mô phỏng record. Khả năng mở rộng `java.lang.Record` được dành cho các record declaration theo quy tắc ngôn ngữ.

Nếu một framework hoặc mô hình miền yêu cầu kế thừa lớp cha cụ thể, hãy chọn **class thông thường**, hoặc thiết kế lại hợp đồng thông qua interface và composition. Không cố ép record vào một hierarchy mà nó không hỗ trợ.

### 3.3. Record vẫn có thể implements interface

**Không kế thừa class** không có nghĩa record không tham gia đa hình. Một record có thể triển khai một hoặc nhiều interface:

~~~java
interface HasId {
    String id();
}

interface Describable {
    String description();
}

record OrderSummary(String id, long totalInCents)
        implements HasId, Describable {

    @Override
    public String description() {
        return "Đơn " + id + ": " + totalInCents + " xu";
    }
}
~~~

Trong ví dụ này:

- `OrderSummary` vẫn `final`.
- Accessor `id()` do compiler sinh ra thỏa hợp đồng của `HasId`.
- Method `description()` là hành vi do lập trình viên viết.
- Các interface vẫn cho phép code khác sử dụng một kiểu trừu tượng.

~~~java
HasId item = new OrderSummary("ORD-1", 120_000L);
System.out.println(item.id()); // ORD-1
~~~

Record là một lớp dữ liệu có thể có **hành vi**, không phải cấu trúc chỉ gồm field. Điểm cần giữ là các method không được âm thầm thêm trạng thái instance bên ngoài danh sách component.

### 3.4. Record kết hợp với sealed interface

Java 17 có `sealed interface`, giúp giới hạn những kiểu được phép triển khai trực tiếp. Record là nhánh lá rất tự nhiên vì bản thân nó đã `final`.

~~~java
sealed interface ValidationResult
        permits Accepted, Rejected {
}

record Accepted(String token) implements ValidationResult {
}

record Rejected(String reason) implements ValidationResult {
}
~~~

Sơ đồ:

~~~text
ValidationResult (sealed interface)
├── Accepted (record, implicitly final)
└── Rejected (record, implicitly final)
~~~

Lưu ý rằng `sealed` giới hạn **kiểu con trực tiếp** của interface/class gốc; `record` giới hạn việc kế thừa **tiếp theo** từ từng nhánh. Với direct permitted subclasses, chúng còn phải thỏa các quy tắc module/package của Java 17.

Sealed không bắt buộc cho record: một record hoàn toàn có thể chỉ là một DTO thông thường. Chọn sealed khi miền dữ liệu thật sự có tập biến thể được kiểm soát.

## 4. Giới hạn trường đối tượng: không khai báo thêm instance field

### 4.1. Component là nguồn xác định trạng thái instance

Với:

~~~java
record Invoice(String invoiceId, long totalInCents) {
}
~~~

Compiler sinh các trường instance `private final` tương ứng với hai component. Bạn **không tự khai báo** chúng lần thứ hai, cũng **không được thêm** field instance khác:

~~~java
// KHÔNG HỢP LỆ:
// record Invoice(String invoiceId, long totalInCents) {
//     private int discountPercent;          // instance field bổ sung
//     private final String normalizedId;    // instance field bổ sung
// }
~~~

Ngay cả khi field phụ là `final`, Java vẫn không cho phép khai báo nó trong record body. Quy tắc này bảo đảm trạng thái instance của record được mô tả bằng header, không phân tán giữa header và body.

### 4.2. Muốn lưu thêm dữ liệu, phải xác định nó có thực sự là một component

Giả sử tổng thanh toán được tính từ `quantity` và `unitPriceInCents`:

~~~java
record LineItem(String sku, int quantity, long unitPriceInCents) {

    long totalInCents() {
        return Math.multiplyExact((long) quantity, unitPriceInCents);
    }
}
~~~

Nếu `totalInCents` luôn có thể suy ra từ các component, việc tính trong method thường rõ ràng hơn lưu một field instance phụ mà record không cho phép.

Ngược lại, nếu tổng tiền đã được xác lập như **snapshot nghiệp vụ** (ví dụ bao gồm chiết khấu, thuế hoặc quy tắc tính tại thời điểm giao dịch), có thể khai báo nó là component có ý nghĩa:

~~~java
record FinalizedLineItem(
        String sku,
        int quantity,
        long unitPriceInCents,
        long finalTotalInCents
) {
}
~~~

Khi đó phải định nghĩa và thực thi các bất biến thích hợp để tránh những tổ hợp dữ liệu vô lý. Cân nhắc liệu `finalTotalInCents` là một giá trị nghiệp vụ độc lập hay chỉ là kết quả tính tạm.

### 4.3. Có thể khai báo static field

Các trường `static` thuộc về **lớp record**, không thuộc trạng thái của từng instance, nên được phép khai báo:

~~~java
import java.util.regex.Pattern;

record ProductCode(String value) {
    private static final Pattern FORMAT =
            Pattern.compile("[A-Z]{2}-[0-9]{4}");

    ProductCode {
        if (value == null || !FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException("Mã sản phẩm không hợp lệ");
        }
    }
}
~~~

`FORMAT` là cấu hình dùng chung để kiểm tra mã, không phải component của từng `ProductCode`. Hai instance `ProductCode("AB-1234")` và `ProductCode("AB-1234")` vẫn được so sánh theo component `value`, chứ không theo trường `FORMAT`.

Một static field *có thể mutable* theo quy tắc Java, nhưng không nên dùng trạng thái toàn cục có thể thay đổi khi không thật sự cần thiết. `private static final` cho các hằng hoặc đối tượng tiện ích dùng chung thường dễ kiểm soát hơn.

### 4.4. Record không tự bảo đảm bất biến sâu

Field component được sinh là `private final`: tham chiếu không thể được gán lại sau khi khởi tạo. Nhưng nếu tham chiếu trỏ đến đối tượng mutable, nội dung của đối tượng đó vẫn có thể thay đổi.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

record Team(String name, List<String> members) {
}

List<String> source = new ArrayList<>(List.of("An", "Binh"));
Team team = new Team("Core", source);
source.add("Chi");

System.out.println(team.members()); // [An, Binh, Chi]
~~~

Đây là trường hợp **mutable object bị chia sẻ qua component**, không phải field `members` của record bị gán lại.

Nếu hợp đồng yêu cầu danh sách thành viên không thay đổi sau khi tạo record, hãy sao chép phòng vệ trong constructor:

~~~java
import java.util.List;
import java.util.Objects;

record SafeTeam(String name, List<String> members) {
    SafeTeam {
        Objects.requireNonNull(name, "name");
        members = List.copyOf(members);
    }
}
~~~

`List.copyOf` tạo danh sách không sửa được qua API, không cho phép phần tử `null`. Với phần tử là đối tượng mutable, bản sao vẫn là **shallow copy**: cần bảo vệ cả các phần tử nếu miền yêu cầu bất biến sâu.

Hệ quả thực tế: khi triển khai `equals()`/`hashCode()` theo giá trị, dữ liệu component nên có ngữ nghĩa ổn định. Để một component thay đổi qua tham chiếu có thể gây vấn đề khi dùng record làm khóa `Map` hoặc phần tử của `Set`.

## 5. Giới hạn khối khởi tạo: không có instance initializer

Java class thông thường có thể chứa **instance initializer block**:

~~~java
class OrdinaryCounter {
    private final int count;

    {
        System.out.println("Đang khởi tạo instance");
    }

    OrdinaryCounter(int count) {
        this.count = count;
    }
}
~~~

Khối `{ ... }` nằm trực tiếp trong class body là instance initializer. Nhưng **record declaration không được khai báo instance initializer**.

~~~java
// KHÔNG HỢP LỆ:
// record Counter(int count) {
//     {
//         if (count < 0) {
//             throw new IllegalArgumentException("count âm");
//         }
//     }
// }
~~~

Để kiểm tra hoặc chuẩn hóa dữ liệu trong mỗi lần khởi tạo record, dùng **canonical constructor**; thường thì **compact canonical constructor** là lựa chọn ngắn gọn nhất.

~~~java
record Counter(int count) {
    Counter {
        if (count < 0) {
            throw new IllegalArgumentException("count âm");
        }
    }
}
~~~

Ở đây `Counter { ... }` **không phải instance initializer block**. Nó là cú pháp **compact canonical constructor** riêng của record. Đừng nhầm hai cấu trúc chỉ vì chúng đều chứa khối lệnh trong dấu ngoặc nhọn.

### 5.1. Static initializer vẫn được phép

Record có thể chứa **static initializer block** để thiết lập dữ liệu tĩnh của lớp:

~~~java
import java.time.ZoneId;

record OfficeTime(String locationName) {
    private static final ZoneId DISPLAY_ZONE;

    static {
        DISPLAY_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
    }

    String zoneName() {
        return DISPLAY_ZONE.getId();
    }
}
~~~

`static { ... }` chạy khi lớp được JVM **khởi tạo** theo quy tắc class initialization, không chạy mỗi lần gọi `new OfficeTime(...)`. Nó khác với compact constructor:

| Cấu trúc | Có được đặt trong record? | Thời điểm/vai trò |
|---|---|---|
| Instance field tự khai báo | **Không** | Trạng thái instance phải nằm trong record components |
| Instance initializer `{ ... }` | **Không** | Không có cơ chế khởi tạo instance bằng block riêng |
| Static field `static ...` | **Có** | Dữ liệu thuộc lớp, dùng chung giữa các instance |
| Static initializer `static { ... }` | **Có** | Khởi tạo logic tĩnh của lớp |
| Compact canonical constructor `RecordName { ... }` | **Có** | Validation/chuẩn hóa tham số khi tạo từng instance |
| Constructor thông thường hợp lệ | **Có giới hạn** | Phải phù hợp quy tắc canonical/delegating constructor |

Không nên đặt logic có chi phí lớn, I/O dễ lỗi hoặc phụ thuộc vào trạng thái môi trường không ổn định trong static initializer nếu có thể thiết kế một cơ chế khởi tạo rõ hơn. Thất bại khi khởi tạo lớp có thể ảnh hưởng mọi lần sử dụng lớp trong class loader đó.

## 6. Canonical constructor: điểm kiểm soát dữ liệu khi tạo record

### 6.1. Constructor chuẩn được sinh tự động

Khai báo:

~~~java
record UserId(String value) {
}
~~~

có một **canonical constructor** tương ứng với danh sách component:

~~~java
new UserId("U-100");
~~~

Nếu không tự định nghĩa, compiler cung cấp constructor nhận đúng các component theo thứ tự header.

### 6.2. Compact canonical constructor: kiểm tra và chuẩn hóa giá trị

Để kiểm tra và chuẩn hóa mã sản phẩm:

~~~java
import java.util.Locale;
import java.util.Objects;

public record Sku(String value) {

    public Sku {
        Objects.requireNonNull(value, "value");

        // Chuẩn hóa parameter trước khi giá trị được lưu vào field.
        value = value.strip().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z]{2}-[0-9]{4}")) {
            throw new IllegalArgumentException("SKU phải có dạng AB-1234");
        }
    }
}
~~~

Trong compact constructor:

1. Các tham số tương ứng với component được cung cấp ngầm định; không cần viết danh sách `(String value)`.
2. Bạn có thể kiểm tra, ném exception hoặc **gán lại tham số** để chuẩn hóa đầu vào.
3. Sau khi thân compact constructor kết thúc bình thường, compiler gán các giá trị tham số component cho các field `private final` tương ứng.

~~~java
Sku a = new Sku(" ab-1234 ");
Sku b = new Sku("AB-1234");

System.out.println(a.value()); // AB-1234
System.out.println(a.equals(b)); // true
~~~

**Lưu ý quan trọng:** Không được gán trực tiếp vào component field trong thân compact constructor:

~~~java
// KHÔNG HỢP LỆ:
// record Sku(String value) {
//     Sku {
//         this.value = value.strip(); // compiler sẽ gán field sau block
//     }
// }
~~~

Hãy chuẩn hóa **tham số `value`**, hoặc dùng canonical constructor viết đầy đủ nếu thật sự cần điều khiển rõ phần gán field.

### 6.3. Explicit canonical constructor: tự gán tất cả component fields

Bạn cũng có thể viết đầy đủ canonical constructor với danh sách tham số đúng tên và đúng kiểu component:

~~~java
import java.util.Objects;

public record Coordinates(double latitude, double longitude) {

    public Coordinates(double latitude, double longitude) {
        if (!Double.isFinite(latitude) ||
                latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException("Latitude không hợp lệ");
        }
        if (!Double.isFinite(longitude) ||
                longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Longitude không hợp lệ");
        }

        this.latitude = latitude;
        this.longitude = longitude;
    }
}
~~~

Khác compact constructor, khi viết explicit canonical constructor, bạn phải đảm bảo **tất cả các component field đều được gán đúng cách trước khi constructor kết thúc bình thường**. Trình biên dịch không tự bổ sung phép gán cuối khối như trong compact constructor.

Constructor chuẩn của một `public record` cũng phải có mức truy cập phù hợp; khi khai báo `public record`, hãy khai báo canonical constructor `public`. Đây là phần hợp đồng khởi tạo của kiểu công khai.

Trong phần lớn trường hợp chỉ cần validation hoặc chuẩn hóa, compact constructor thường ngắn gọn, ít lặp tham số hơn.

### 6.4. Constructor phụ phải gọi constructor khác của chính record

Record vẫn có thể có **constructor overload** để cung cấp giá trị mặc định:

~~~java
record Ticket(String code, int seatCount) {

    Ticket {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Mã vé không hợp lệ");
        }
        if (seatCount < 1) {
            throw new IllegalArgumentException("Số ghế phải dương");
        }
    }

    Ticket(String code) {
        this(code, 1);
    }
}
~~~

`Ticket(String code)` **không phải canonical constructor**. Nó phải gọi constructor khác của record qua `this(...)` theo quy tắc Java 17; ở đây nó chuyển tiếp sang canonical constructor.

Nhờ vậy, bất kể dùng `new Ticket("T1")` hay `new Ticket("T1", 3)`, dữ liệu đều đi qua đường kiểm tra chính của record.

Không viết constructor phụ chỉ để tự gán trường:

~~~java
// KHÔNG HỢP LỆ:
// record Ticket(String code, int seatCount) {
//     Ticket(String code) {
//         this.code = code;
//         this.seatCount = 1;
//     }
// }
~~~

**Phân biệt:** Java 17 yêu cầu constructor phụ chuyển tiếp qua `this(...)`; không áp dụng quy tắc/tiện ích constructor preview của các phiên bản Java ra đời sau vào bài học này.

## 7. Accessor và method: hành vi vẫn được phép, nhưng không được đổi mô hình trạng thái

Accessor mặc định có cùng tên với component, **không có tiền tố `get`**:

~~~java
record Price(long cents) {
}

Price price = new Price(10_000);
System.out.println(price.cents());
~~~

Bạn có thể thêm method khác:

~~~java
record Rectangle(double width, double height) {
    Rectangle {
        if (!(width > 0.0) || !(height > 0.0) ||
                !Double.isFinite(width) || !Double.isFinite(height)) {
            throw new IllegalArgumentException("Kích thước không hợp lệ");
        }
    }

    double area() {
        return width * height;
    }

    boolean isSquare() {
        return Double.compare(width, height) == 0;
    }
}
~~~

Hai method tính toán trực tiếp từ component; không cần field `area` hoặc `isSquare` bổ sung.

### 7.1. Có thể viết explicit accessor khi cần bảo vệ dữ liệu

Với component kiểu mảng, cần sao chép khi nhận vào và khi trả ra để tránh bị sửa từ bên ngoài:

~~~java
import java.util.Objects;

record BytePayload(byte[] data) {
    BytePayload {
        Objects.requireNonNull(data, "data");
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

Giờ caller không thể sửa nội dung mảng lưu trong record thông qua tham chiếu đầu vào hoặc accessor.

Tuy vậy, **một mảng là component có ngữ nghĩa equals/hashCode cần cân nhắc**: phương thức `equals()`/`hashCode()` mặc định của record không tự biến `byte[]` thành so sánh nội dung theo `Arrays.equals`/`Arrays.hashCode`. Nếu nghiệp vụ muốn so sánh nội dung mảng, cần thiết kế rõ (ví dụ override nhất quán `equals` và `hashCode`, hoặc dùng cấu trúc dữ liệu khác phù hợp).

Ngoài ra, với explicit accessor, phải giữ hợp đồng của record: cùng tên component, kiểu trả về phù hợp, mức truy cập công khai và không sử dụng để trả dữ liệu mâu thuẫn với trạng thái của record. Không nên override accessor để tính ra một giá trị ngẫu nhiên hoặc thay đổi qua thời gian.

### 7.2. Không có setter do compiler sinh ra

~~~java
record UserProfile(String displayName) {
}

UserProfile first = new UserProfile("An");

// KHÔNG HỢP LỆ:
// first.displayName = "Binh";
// first.setDisplayName("Binh");

UserProfile changed = new UserProfile("Binh");
~~~

Thay vì sửa state của instance, ta tạo đối tượng mới cho trạng thái khác. Nếu nghiệp vụ thực sự cần vòng đời thay đổi nội bộ liên tục, class có state quản lý rõ ràng có thể phù hợp hơn record.

## 8. Ví dụ tổng hợp chạy trên Java 17: không kế thừa class, không instance field, không instance initializer

Ví dụ đặt toàn bộ mã trong **RecordConstraintsDemo.java**. Nó mô tả một snapshot đặt chỗ, yêu cầu:

- Có mã đặt chỗ và danh sách khách.
- Xác thực mã lúc tạo đối tượng.
- Danh sách khách không được sửa từ bên ngoài sau khi tạo snapshot.
- Hiển thị số khách qua method tính toán, không lưu thêm instance field.
- Chia sẻ một mẫu kiểm tra mã qua static field.
- Cho phép constructor phụ dùng thời điểm mặc định do caller truyền.
- Tham gia một sealed interface để biểu diễn kết quả xử lý.

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

public class RecordConstraintsDemo {

    sealed interface BookingOutcome permits BookingSnapshot, BookingRejected {
    }

    public record BookingSnapshot(
            String bookingId,
            List<String> guests,
            Instant createdAt
    ) implements BookingOutcome {

        // Static field: dùng chung, không thuộc state của mỗi snapshot.
        private static final Pattern ID_PATTERN =
                Pattern.compile("BK-[0-9]+");

        private static final ZoneId DISPLAY_ZONE;

        // Static initializer: chạy khi lớp được khởi tạo.
        static {
            DISPLAY_ZONE = ZoneId.of("Asia/Ho_Chi_Minh");
        }

        // Compact canonical constructor: kiểm tra và sao chép dữ liệu.
        public BookingSnapshot {
            Objects.requireNonNull(bookingId, "bookingId");
            Objects.requireNonNull(guests, "guests");
            Objects.requireNonNull(createdAt, "createdAt");

            if (!ID_PATTERN.matcher(bookingId).matches()) {
                throw new IllegalArgumentException("Mã phải có dạng BK-123");
            }

            guests = List.copyOf(guests);
            if (guests.isEmpty() || guests.stream().anyMatch(String::isBlank)) {
                throw new IllegalArgumentException("Danh sách khách không hợp lệ");
            }
        }

        // Constructor phụ chuyển tiếp đến constructor chuẩn.
        public BookingSnapshot(String bookingId, List<String> guests) {
            this(bookingId, guests, Instant.now());
        }

        // Method tính từ components; không cần thêm instance field.
        public int guestCount() {
            return guests.size();
        }

        public String formattedCreatedAt() {
            return createdAt.atZone(DISPLAY_ZONE).toString();
        }
    }

    public record BookingRejected(String reason) implements BookingOutcome {
        public BookingRejected {
            Objects.requireNonNull(reason, "reason");
            if (reason.isBlank()) {
                throw new IllegalArgumentException("Lý do không được trống");
            }
        }
    }

    static String describe(BookingOutcome outcome) {
        if (outcome instanceof BookingSnapshot snapshot) {
            return snapshot.bookingId() + ": " +
                    snapshot.guestCount() + " khách";
        }
        if (outcome instanceof BookingRejected rejected) {
            return "Từ chối: " + rejected.reason();
        }
        throw new IllegalStateException("Kết quả chưa được xử lý");
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Binh"));
        Instant time = Instant.parse("2026-11-15T14:00:00Z");

        BookingSnapshot first =
                new BookingSnapshot("BK-123", source, time);

        // Thử thay đổi danh sách ban đầu sau khi đã tạo snapshot.
        source.add("Chi");

        BookingSnapshot sameValues = new BookingSnapshot(
                "BK-123", List.of("An", "Binh"), time
        );

        System.out.println(first.guests());
        System.out.println(first.guestCount());
        System.out.println(first.equals(sameValues));
        System.out.println(describe(first));
        System.out.println(describe(new BookingRejected("Hết chỗ")));
        System.out.println(first.formattedCreatedAt());
    }
}
~~~

Chạy từ thư mục chứa file bằng JDK 17:

~~~shell
java -version
javac --release 17 RecordConstraintsDemo.java
java RecordConstraintsDemo
~~~

Kết quả minh họa:

~~~text
[An, Binh]
2
true
BK-123: 2 khách
Từ chối: Hết chỗ
2026-11-15T21:00+07:00[Asia/Ho_Chi_Minh]
~~~

Điều cần quan sát:

1. Sau khi thêm `"Chi"` vào `source`, danh sách `guests` trong `first` vẫn giữ `["An", "Binh"]` nhờ `List.copyOf`.
2. `guestCount()` tính từ `guests` ở mỗi lần gọi; không cần `private int guestCount`.
3. Hai snapshot có cùng component theo hợp đồng đều bằng nhau; `List` so sánh nội dung qua `equals`.
4. `ID_PATTERN` và `DISPLAY_ZONE` là thành phần static, không tham gia vào `equals`/`hashCode` của instance.
5. Constructor xác thực từng record khi tạo; static initializer không thay vai trò kiểm tra đầu vào của mỗi instance.
6. `BookingSnapshot` triển khai `BookingOutcome` nhưng vẫn là lớp `final`.
7. Ví dụ `describe` sử dụng pattern matching cho `instanceof` đã ổn định trên Java 17. Pattern matching for switch chưa ổn định trong Java 17 và không cần dùng cho bài này.

## 9. Phân biệt Record với class bất biến thông thường

Một class tự viết có thể cho phép lựa chọn cấu trúc nội bộ đa dạng hơn record:

~~~java
import java.util.Objects;

final class AccountLabel {
    private final String value;
    private final int lengthCache;

    AccountLabel(String value) {
        this.value = Objects.requireNonNull(value).strip();
        this.lengthCache = this.value.length();
    }

    String value() {
        return value;
    }

    int length() {
        return lengthCache;
    }
}
~~~

Class có thể có instance field tính sẵn và lưu `lengthCache`. Record không được phép thêm field tương tự ngoài component list. Nhưng điều đó **không có nghĩa record kém hơn** trong mọi trường hợp: `length()` có thể chỉ cần gọi `value.length()`, giảm nhu cầu lưu state dư thừa.

| Tiêu chí | Record | Class thường |
|---|---|---|
| Tập instance field | Xác định bởi các component | Tự thiết kế các field |
| Kế thừa class tùy ý | Không; đã extends `java.lang.Record` | Có thể extends một class phù hợp |
| Bị lớp khác extends | Không; ngầm định final | Tùy `final`, `sealed` và quy tắc khác |
| Implements interface | Có | Có |
| Instance initializer block | Không | Có |
| Static field/block | Có | Có |
| Constructor validation | Có, thường dùng compact constructor | Có, constructor thông thường |
| Accessor | Sinh theo tên component; có thể khai báo tường minh | Tự định nghĩa |
| `equals`, `hashCode`, `toString` | Tự sinh theo component nếu không khai báo tường minh | Phải tự viết hoặc dùng công cụ |
| Dữ liệu mutable được tham chiếu | Có thể tồn tại; cần defensive copy khi phù hợp | Tương tự, phụ thuộc thiết kế |
| Phù hợp nhất | Value carrier/DTO/snapshot có tập state rõ | Đối tượng cần cấu trúc trạng thái linh hoạt hoặc kế thừa lớp |

Không nên cố dùng class kế thừa nhiều tầng chỉ vì quen thuộc với OOP, nhưng cũng không nên chuyển mọi class sang record chỉ để giảm boilerplate. Một entity có state biến đổi qua nghiệp vụ, cần proxy từ ORM hoặc phải kế thừa base class có thể cần class thường.

## 10. Các giới hạn có thể gặp trong ứng dụng thực tế

### 10.1. Record không có JavaBean setter hoặc no-arg constructor mặc định

~~~java
record UserView(long id, String name) {
}
~~~

Constructor được sinh nhận `id` và `name`; accessor có dạng `id()`, `name()`, không phải mặc định `getId()`, `getName()`. Compiler cũng không tạo constructor rỗng `UserView()`.

Vì vậy, khi dùng framework hoặc công cụ mapping, cần kiểm tra phiên bản đó **có hỗ trợ record construction/accessors hay không**, thay vì giả định mọi cơ chế dựa vào JavaBean đều hoạt động giống class truyền thống.

### 10.2. Record thường không phù hợp để đóng vai trò entity JPA

JPA entity thường cần vòng đời được ORM quản lý, khả năng kế thừa/proxy và những yêu cầu về constructor/trường trạng thái nhất định. Bởi record là `final`, không có no-arg constructor mặc định và có component fields `final`, record thường thích hợp hơn cho **DTO/projection** hoặc dữ liệu chỉ đọc khi framework hỗ trợ.

~~~text
Database row
    ↓ (ORM entity thường là class)
OrderEntity
    ↓ map sang DTO
OrderResponse (record)
    ↓ trả cho API client
~~~

Cách phân chia này giúp entity giữ trách nhiệm vòng đời dữ liệu, trong khi record mang snapshot rõ cấu trúc ra khỏi domain/service.

### 10.3. Không lưu cache instance ngầm trong record

Ví dụ, một `Report` tính tổng rất tốn kém. Bạn có thể muốn:

~~~java
// KHÔNG HỢP LỆ:
// record Report(List<Long> numbers) {
//     private Long cachedTotal;
// }
~~~

Các lựa chọn có thể cân nhắc:

- Tính lại trong method nếu dữ liệu nhỏ và chi phí thấp.
- Tính ngay lúc tạo và đưa kết quả vào component khi đó là một phần của snapshot có ý nghĩa.
- Tách một service/cache theo khóa thích hợp để quản lý việc tính toán tốn kém.
- Dùng class khi bản thân đối tượng cần trạng thái cache có vòng đời riêng.

Không đưa `static Map<Report, Long>` vào record một cách vô điều kiện: cache toàn cục có vấn đề về bộ nhớ, concurrency, vòng đời và invalidation; chỉ sử dụng khi đã có thiết kế rõ.

### 10.4. Không lẫn lộn tính final của field và tính bất biến toàn bộ object graph

~~~java
import java.util.Date;

record LegacyTimestamp(Date value) {
}
~~~

`Date` là đối tượng mutable, nên record trên không có giá trị bất biến sâu. Với code Java hiện đại, thường nên dùng kiểu ngày giờ phù hợp trong `java.time` như `Instant` thay cho dạng thời gian mutable trong mô hình mới:

~~~java
import java.time.Instant;

record EventTime(Instant instant) {
}
~~~

Lựa chọn loại dữ liệu phù hợp thường tốt hơn cố bọc những đối tượng mutable trong record rồi kỳ vọng chúng tự trở nên immutable.

## 11. Bảng cú pháp hợp lệ và không hợp lệ trên Java 17

| Khai báo hoặc thao tác | Hợp lệ? | Lý do |
|---|---|---|
| `record Point(int x, int y) {}` | Có | Record thông thường |
| `record Point(int x, int y) implements Printable {}` | Có nếu interface phù hợp | Record được implements interface |
| `class Child extends Point {}` | Không | Record ngầm định final |
| `record Child(int x) extends Parent {}` | Không | Record không có superclass tùy ý |
| `abstract record Item(int id) {}` | Không | Record không được abstract |
| `sealed record Item(int id) {}` | Không | Record không được sealed |
| `record R(int n) { int extra; }` | Không | Không khai báo thêm instance field |
| `record R(int n) { static int count; }` | Có | Trường static không thuộc state instance |
| `record R(int n) { { ... } }` | Không | Instance initializer bị cấm |
| `record R(int n) { static { ... } }` | Có khi nội dung block hợp lệ | Static initializer được phép |
| `record R(int n) { R { ... } }` | Có khi nội dung hợp lệ | Compact canonical constructor |
| `record R(int n) { R(int n) { this.n = n; } }` | Có | Explicit canonical constructor gán field |
| `record R(int n) { R() { this(0); } }` | Có | Constructor phụ chuyển tiếp tới canonical |
| `record R(int n) { int doubleN() { return n * 2; } }` | Có | Method instance không khai báo field mới |

Trong bảng, `{ ... }` là ký hiệu minh họa; nếu sao chép nguyên văn, hãy thay bằng mã Java hợp lệ.

## 12. Những hiểu nhầm thường gặp

**“Record là class bình thường được IDE sinh getter/setter.”**  
Không. Record là cú pháp ngôn ngữ với tập component xác định, constructor và phương thức được compiler sinh theo hợp đồng riêng; record không có setter mặc định.

**“Record final nên không thể implements interface.”**  
Sai. `final` ngăn một class bị kế thừa, nhưng không ngăn class đó triển khai interface.

**“Record không có field nào.”**  
Sai. Record có instance fields `private final` được sinh ra từ components. Điều bị cấm là **tự khai báo thêm** instance fields trong body.

**“Đặt `final` cho field bổ sung là được phép.”**  
Sai. Quy tắc cấm field instance bổ sung áp dụng cả khi field có `final`.

**“Không được viết block trong record.”**  
Sai. Instance initializer bị cấm, nhưng **static initializer** và **constructor body** (đặc biệt compact canonical constructor) được phép.

**“Compact constructor là khối instance initializer viết khác tên.”**  
Sai. Compact constructor có vai trò constructor và cơ chế gán các component fields sau khi thân khối thực thi bình thường.

**“Có component `List<String>` nghĩa là record luôn immutable.”**  
Sai. `final` chỉ bảo vệ tham chiếu được lưu trong field; cần phòng vệ đối với nội dung mutable.

**“Dùng record thì mọi thuộc tính dẫn xuất phải chuyển thành component.”**  
Không. Có thể tính từ component trong method. Chỉ lưu thuộc tính dẫn xuất thành component nếu nó có ý nghĩa trong hợp đồng dữ liệu.

**“Record muốn dùng trong sealed hierarchy thì bản thân phải sealed.”**  
Không. Record là `final`, vì vậy có thể đóng vai trò một permitted subtype trực tiếp của sealed interface/class nếu quan hệ kế thừa hợp lệ.

## 13. Bài tập thực hành

### Bài 1 — Đánh giá cú pháp

Xét các khai báo sau và dự đoán đoạn nào compiler Java 17 chấp nhận:

~~~java
record A(int id) {
    static final int MIN_ID = 1;
}

// Bị cấm thêm instance field:
// record B(int id) {
//     private final String label = "default";
// }

record C(int id) {
    C {
        if (id < 1) {
            throw new IllegalArgumentException("id phải dương");
        }
    }
}

record D(int id) {
    static {
        System.out.println("Khởi tạo lớp D");
    }
}
~~~

Giải thích tại sao `A`, `C`, `D` hợp lệ và `B` không hợp lệ; xác định thời điểm các khối tương ứng được thực thi.

### Bài 2 — Thiết kế snapshot bất biến

Thiết kế record `CourseSnapshot` có:

- `courseId: String`, không được trống.
- `title: String`, không được trống.
- `lessons: List<String>`, không null, không rỗng, không chứa null.
- `publishedAt: Instant`, không null.

Yêu cầu dùng compact constructor, `List.copyOf`, và một method `lessonCount()`. Sau khi tạo record từ một `ArrayList`, hãy sửa danh sách gốc để quan sát snapshot không bị ảnh hưởng.

Thử gọi `snapshot.lessons().add("Bài mới")` và giải thích vì sao không cho phép sửa danh sách.

### Bài 3 — Thay kế thừa bằng composition

Bạn đang có ý tưởng `record Manager extends Employee` để bổ sung `teamSize`. Hãy thiết kế lại bằng:

~~~java
record EmployeeIdentity(String employeeId, String displayName) {
}

record ManagerSnapshot(EmployeeIdentity identity, int teamSize) {
}
~~~

Thêm validation và method `summary()`. Giải thích phần nào là quan hệ **has-a** và vì sao không được dùng `extends` giữa hai record.

### Bài 4 — Constructor phụ

Viết record `Money(String currency, long amountInMinorUnit)` với:

- Compact constructor kiểm tra currency hợp lệ theo quy tắc riêng của ứng dụng và số tiền không âm.
- Constructor phụ `Money(long amountInMinorUnit)` dùng một mã tiền tệ mặc định do miền quy định, và phải gọi `this(...)`.
- Method `isZero()` tính từ `amountInMinorUnit`.

Không khai báo thêm instance field, không dùng instance initializer. Nêu lý do constructor phụ không thể tự gán các field.

### Bài 5 — Record trong sealed hierarchy

Thiết kế:

~~~text
ApiResult (sealed interface)
├── Ok (record)
└── Error (record)
~~~

Mỗi nhánh có component phù hợp. Viết method xử lý bằng `instanceof` pattern trên Java 17 và thử viết một implementation thứ ba không nằm trong `permits`. Giải thích lỗi compiler. Sau đó suy nghĩ xem có nên dùng interface mở nếu bên thứ ba cần tự định nghĩa nhánh kết quả của mình.

## 14. Câu hỏi tự kiểm tra

1. Vì sao record được xem là `final` dù không có từ khóa `final` trong khai báo?
2. Record trực tiếp kế thừa class nào? Có được khai báo `extends BaseDto` không?
3. Record có được triển khai interface hoặc làm permitted subtype của sealed interface không?
4. Tại sao `private final int extra` vẫn bị cấm nếu khai báo như một instance field trong record body?
5. Một giá trị tính từ component nên thành method hay một component bổ sung? Điều gì quyết định?
6. Khác nhau giữa `{ ... }`, `static { ... }` và `RecordName { ... }` trong khai báo record là gì?
7. Trong compact constructor, tại sao gán lại tham số được phép nhưng gán trực tiếp component field không được phép?
8. Explicit canonical constructor phải làm gì để tất cả component fields được khởi tạo?
9. Constructor phụ của record phải chuyển tiếp như thế nào trên Java 17?
10. Vì sao record có `List` hoặc mảng vẫn có thể bị ảnh hưởng bởi dữ liệu mutable?
11. Tại sao `equals()` của record với component kiểu mảng có thể không đúng ý nghĩa so sánh nội dung của nghiệp vụ?
12. Khi nào class thông thường là lựa chọn phù hợp hơn record?

## 15. Tài liệu tham khảo

- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): mục tiêu thiết kế và ngữ nghĩa record được chuẩn hóa từ Java 16.
- [Java Language Specification — Java SE 17, §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): quy tắc chính thức về kế thừa, components, fields, initializer, constructors và accessors.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): lớp cơ sở của mọi record.
- [dev.java — Records](https://dev.java/learn/records/): hướng dẫn sử dụng record trong Java hiện đại.

Một record là lựa chọn tốt khi muốn tập trạng thái instance **được khai báo hết qua components**, dữ liệu có hợp đồng rõ, và không cần mở rộng bằng kế thừa class. Khi cần validation hoặc chuẩn hóa, hãy dùng constructor; khi cần dữ liệu chung, dùng static field hoặc static initializer; khi cần phép tính dựa trên components, dùng method. Hiểu ba giới hạn này giúp sử dụng record đúng với thiết kế của Java 17 và tránh chuyển đổi máy móc từ class truyền thống.
