# Thiết kế lớp bất biến và defensive copy

> Phạm vi: thiết kế kiểu dữ liệu Java 27 có trạng thái ổn định sau khi khởi tạo, bảo vệ dữ liệu mutable tại ranh giới API và chia sẻ đối tượng an toàn. Các ví dụ dùng Java hiện hành, không yêu cầu preview feature.

## 1. Lớp bất biến là gì?

Một đối tượng được xem là **bất biến (immutable)** khi trạng thái quan sát được của nó không thể thay đổi sau khi quá trình khởi tạo hoàn tất. Mọi phương thức công khai chỉ đọc trạng thái hoặc tạo ra một đối tượng mới để biểu diễn kết quả thay đổi.

Ví dụ, `String`, `BigInteger`, `BigDecimal` và các kiểu ngày giờ trong `java.time` là những kiểu bất biến. Khi gọi `String.replace` hoặc `BigDecimal.add`, đối tượng ban đầu không bị sửa; phương thức trả về giá trị mới.

Lớp bất biến hữu ích vì:

- Trạng thái không thay đổi bất ngờ do một đoạn mã khác giữ tham chiếu đến cùng dữ liệu.
- Đối tượng dễ chia sẻ giữa nhiều luồng sau khi được khởi tạo đúng cách.
- Có thể dùng làm khóa trong `HashMap` hoặc phần tử trong `HashSet` nếu `equals` và `hashCode` được thiết kế nhất quán.
- Test và debug dễ hơn vì giá trị đã tạo không bị thay đổi trong quá trình sử dụng.
- API có hợp đồng rõ ràng: người gọi có thể đọc và truyền đối tượng mà không phải phối hợp các thao tác cập nhật trạng thái.

Một lớp bất biến không nhất thiết chỉ chứa primitive. Nó có thể chứa collection, mảng hoặc đối tượng khác, miễn là toàn bộ trạng thái có thể quan sát đều được bảo vệ khỏi thay đổi từ bên ngoài.

## 2. Phân biệt immutable, unmodifiable và read-only

Ba khái niệm này có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Immutable object | Trạng thái của đối tượng không thể thay đổi sau khi tạo | `String`, `LocalDate`, một lớp tự thiết kế đúng quy tắc bất biến |
| Unmodifiable collection | Người giữ collection không thể gọi thao tác làm thay đổi collection qua tham chiếu đó | `Collections.unmodifiableList(list)` |
| Read-only view | Một góc nhìn chỉ đọc lên dữ liệu; dữ liệu gốc vẫn có thể bị thay đổi qua tham chiếu khác | Wrapper unmodifiable trên một danh sách mutable |

Ví dụ, wrapper unmodifiable không tự tạo snapshot:

~~~java
var source = new ArrayList<String>();
source.add("Java");

var view = Collections.unmodifiableList(source);

source.add("JDK 27");
System.out.println(view); // [Java, JDK 27]
~~~

Người gọi `view.add(...)` sẽ nhận `UnsupportedOperationException`, nhưng thay đổi trên `source` vẫn xuất hiện trong view. Do đó, unmodifiable view chưa đủ để bảo đảm một đối tượng bất biến.

Khi cần một snapshot collection, các factory `List.copyOf`, `Set.copyOf` và `Map.copyOf` tạo collection không thể sửa qua API collection và tách cấu trúc khỏi collection nguồn:

~~~java
var source = new ArrayList<String>();
source.add("Java");

var snapshot = List.copyOf(source);
source.add("JDK 27");

System.out.println(snapshot); // [Java]
~~~

Các factory `copyOf` không cho phép phần tử hoặc key/value null. Chúng tạo bản sao nông (shallow copy): cấu trúc collection được tách, nhưng các đối tượng nằm bên trong vẫn có thể mutable. Vì vậy, muốn bất biến sâu phải kiểm soát cả các phần tử và trạng thái lồng bên trong.

## 3. Các nguyên tắc thiết kế một lớp bất biến

Một thiết kế phổ biến có các nguyên tắc sau:

1. **Giới hạn khả năng kế thừa**: dùng `final class` nếu lớp không được thiết kế cho kế thừa. Điều này ngăn subclass bổ sung trạng thái mutable hoặc ghi đè phương thức làm thay đổi hành vi mong đợi.
2. **Ẩn toàn bộ field**: khai báo field là `private`; không để lộ trực tiếp cấu trúc dữ liệu nội bộ.
3. **Khởi tạo đầy đủ và một lần**: dùng field `final` và gán giá trị trong constructor. Không cung cấp setter hoặc phương thức sửa trạng thái.
4. **Kiểm tra invariant trong constructor**: từ chối null, miền giá trị không hợp lệ và tổ hợp field không nhất quán ngay khi tạo đối tượng.
5. **Sao chép dữ liệu mutable đầu vào**: không giữ nguyên tham chiếu đến mảng, collection hoặc đối tượng mutable do caller truyền vào.
6. **Không để lộ dữ liệu mutable nội bộ**: accessor trả về giá trị bất biến hoặc bản sao phòng vệ; không trả về trực tiếp mảng hay collection mutable nội bộ.
7. **Không để `this` thoát khỏi constructor**: không đăng ký listener, đưa `this` vào biến static hoặc gọi callback bên ngoài khi đối tượng chưa được khởi tạo xong.
8. **Bảo đảm bất biến ở mọi cấp**: các đối tượng được tham chiếu từ field cũng phải bất biến hoặc được sao chép và bảo vệ.

`final` trên một field chỉ ngăn gán lại tham chiếu sau khi khởi tạo. Nó không làm cho đối tượng được tham chiếu trở nên bất biến:

~~~java
private final List<String> names = new ArrayList<>();

public void addName(String name) {
    names.add(name); // vẫn thay đổi được nội dung list
}
~~~

Tương tự, `private final byte[] data` vẫn cho phép thay đổi từng phần tử của mảng. Vì vậy, cần kết hợp field `final` với quyền sở hữu dữ liệu, defensive copy và API không làm lộ trạng thái mutable.

## 4. Defensive copy là gì?

**Defensive copy** là tạo bản sao dữ liệu tại ranh giới nơi một đối tượng nhận hoặc trả dữ liệu mutable. Mục tiêu là ngăn caller thay đổi trạng thái nội bộ thông qua một tham chiếu còn được chia sẻ.

Có hai hướng chính:

- **Copy on input**: sao chép dữ liệu ngay khi nhận từ caller, trước khi lưu vào field.
- **Copy on output**: sao chép dữ liệu trước khi trả cho caller, để caller không thể sửa trực tiếp trạng thái nội bộ.

Với dữ liệu immutable như `String`, `LocalDate` hoặc `BigDecimal`, thường không cần sao chép vì bản thân đối tượng không thể thay đổi. Với mảng, collection mutable hoặc đối tượng tự thiết kế có setter, cần đánh giá việc sao chép.

### 4.1. Rủi ro khi giữ nguyên mảng đầu vào

Ví dụ sau chưa an toàn:

~~~java
public final class UnsafePacket {
    private final byte[] payload;

    public UnsafePacket(byte[] payload) {
        this.payload = payload;
    }

    public byte[] payload() {
        return payload;
    }
}
~~~

Caller vẫn giữ tham chiếu đến mảng ban đầu và có thể thay đổi nội dung sau khi tạo đối tượng:

~~~java
byte[] bytes = {1, 2, 3};
var packet = new UnsafePacket(bytes);

bytes[0] = 99; // làm thay đổi trạng thái quan sát được của packet
packet.payload()[1] = 88; // cũng sửa trực tiếp dữ liệu nội bộ
~~~

Field `payload` là `private final`, nhưng đối tượng vẫn mutable vì mảng được chia sẻ.

### 4.2. Copy ở cả constructor và accessor

Dùng `clone()` hoặc `Arrays.copyOf` để sao chép mảng primitive:

~~~java
import java.util.Arrays;
import java.util.Objects;

public final class Packet {
    private final byte[] payload;

    public Packet(byte[] payload) {
        this.payload = Objects.requireNonNull(
                payload, "payload").clone();
    }

    public byte[] payload() {
        return payload.clone();
    }

    public int size() {
        return payload.length;
    }
}
~~~

Hai lần sao chép có mục đích khác nhau:

- Constructor giữ bản sao riêng, không phụ thuộc vào mảng mà caller còn nắm giữ.
- Accessor trả bản sao mới, không cho caller sửa mảng nội bộ.

Có thể dùng `Arrays.copyOf(payload, payload.length)` thay cho `clone()` khi muốn biểu đạt rõ thao tác sao chép. Với mảng primitive, cả hai đều tạo mảng mới có cùng giá trị phần tử.

~~~java
byte[] source = {1, 2, 3};
var packet = new Packet(source);

source[0] = 9;

byte[] returned = packet.payload();
returned[1] = 8;

System.out.println(Arrays.toString(packet.payload())); // [1, 2, 3]
~~~

Đây là mẫu quan trọng với byte array chứa dữ liệu, checksum, chữ ký, khóa công khai hoặc payload giao thức. Với dữ liệu nhạy cảm như secret, việc sao chép còn tạo thêm bản trong bộ nhớ; hãy thiết kế vòng đời và xóa dữ liệu theo yêu cầu bảo mật của hệ thống, không mặc định rằng defensive copy tự giải quyết việc quản lý secret.

## 5. Sao chép collection đúng cách

### 5.1. Dùng List.copyOf cho snapshot không cho phép null

Khi collection chứa các phần tử immutable, `List.copyOf` thường là lựa chọn rõ ràng:

~~~java
import java.util.List;
import java.util.Objects;

public final class Course {
    private final String name;
    private final List<String> topics;

    public Course(String name, List<String> topics) {
        this.name = Objects.requireNonNull(name, "name");
        this.topics = List.copyOf(
                Objects.requireNonNull(topics, "topics"));
    }

    public String name() {
        return name;
    }

    public List<String> topics() {
        return topics;
    }
}
~~~

Vì `String` bất biến, snapshot của danh sách `String` ở đây đủ để bảo vệ trạng thái. Caller có thể giữ list ban đầu hoặc cố gọi `course.topics().add(...)`; cả hai cách đều không sửa được collection nội bộ.

### 5.2. Dùng Map.copyOf và Set.copyOf

Cùng nguyên tắc áp dụng cho map và set:

~~~java
public final class Configuration {
    private final Map<String, String> properties;
    private final Set<String> enabledFeatures;

    public Configuration(
            Map<String, String> properties,
            Set<String> enabledFeatures) {
        this.properties = Map.copyOf(properties);
        this.enabledFeatures = Set.copyOf(enabledFeatures);
    }

    public Map<String, String> properties() {
        return properties;
    }

    public Set<String> enabledFeatures() {
        return enabledFeatures;
    }
}
~~~

Các collection trả về không hỗ trợ thao tác cập nhật. Thứ tự lặp của `Map.copyOf` và `Set.copyOf` không nên được dùng như một hợp đồng thứ tự nếu API không quy định điều đó. Nếu cần giữ thứ tự, hãy chọn một biểu diễn có thứ tự và thiết kế cách trả dữ liệu tương ứng, đồng thời vẫn bảo vệ bản sao nội bộ.

### 5.3. Khi cần cho phép phần tử null

`List.copyOf`, `Set.copyOf` và `Map.copyOf` từ chối null. Nếu hợp đồng dữ liệu cho phép null, có thể tạo snapshot bằng collection mới rồi bọc unmodifiable:

~~~java
var snapshot = Collections.unmodifiableList(
        new ArrayList<>(input));
~~~

Ở đây `ArrayList` mới tách cấu trúc khỏi input, còn wrapper ngăn caller sửa collection qua tham chiếu trả về. Tuy nhiên, nếu các phần tử là mutable thì vẫn phải sao chép từng phần tử hoặc chuyển chúng thành kiểu immutable. Chỉ cho phép null khi nó có ý nghĩa rõ ràng trong mô hình dữ liệu; nếu không, kiểm tra và từ chối null thường làm API dễ hiểu hơn.

## 6. Shallow copy và deep copy

Một bản sao nông tạo một container mới nhưng giữ nguyên tham chiếu đến các phần tử bên trong. Một bản sao sâu tạo bản sao cho các đối tượng mutable lồng bên trong theo độ sâu cần thiết của mô hình.

Ví dụ, sao chép một mảng đối tượng bằng `clone()` hoặc `Arrays.copyOf` chỉ sao chép mảng ngoài:

~~~java
var names = new StringBuilder[] {
    new StringBuilder("Java")
};

var copy = names.clone();
copy[0].append(" 27");

System.out.println(names[0]); // Java 27
~~~

Hai mảng khác nhau nhưng cùng tham chiếu đến một `StringBuilder`.

Nếu phần tử có thể mutable, có thể chuyển nó sang kiểu immutable hoặc sao chép từng phần tử. Ví dụ dùng record chỉ chứa primitive:

~~~java
record Coordinate(int x, int y) {}

public final class Route {
    private final List<Coordinate> points;

    public Route(List<Coordinate> points) {
        this.points = List.copyOf(points);
    }

    public List<Coordinate> points() {
        return points;
    }
}
~~~

Ở ví dụ này, `Coordinate` là record với hai thành phần primitive nên phần tử không có trạng thái mutable cần sao chép. Nếu `Coordinate` chứa `byte[]`, `List` hoặc một đối tượng mutable khác, record đó không tự trở thành immutable sâu; cần sao chép và bảo vệ các thành phần ấy.

Một quy tắc thực tế: xác định toàn bộ object graph có thể truy cập từ field. Mọi đường dẫn từ API công khai đến trạng thái mutable phải được đóng lại bằng kiểu immutable, defensive copy hoặc abstraction chỉ đọc thực sự an toàn.

## 7. Record không tự động bảo đảm bất biến sâu

Record có các component được khai báo rõ và field component là `private final`. Đây là cách thuận tiện để mô tả data carrier, nhưng record chỉ bảo đảm ràng buộc ở mức tham chiếu component; nó không tự sao chép mảng hoặc collection mutable.

Ví dụ chưa đủ an toàn:

~~~java
public record ImageData(byte[] bytes) {}
~~~

Record này giữ mảng do caller truyền vào và accessor `bytes()` trả chính mảng đó. Có thể viết compact canonical constructor và override accessor để bảo vệ dữ liệu:

~~~java
import java.util.Objects;

public record ImageData(byte[] bytes) {
    public ImageData {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Trong compact constructor, gán lại tham số component trước khi constructor kết thúc; compiler gán giá trị tham số cuối cùng vào field component. Accessor được override trả bản sao để không làm lộ mảng.

Với component collection chứa kiểu immutable, có thể snapshot ngay trong compact constructor:

~~~java
public record SearchResult(
        String query,
        List<String> matches) {

    public SearchResult {
        Objects.requireNonNull(query, "query");
        matches = List.copyOf(matches);
    }
}
~~~

Nếu collection chứa các phần tử mutable, `List.copyOf` chỉ sao chép cấu trúc. Hãy sao chép từng phần tử hoặc chuyển mô hình phần tử sang kiểu immutable.

## 8. Lớp bất biến hoàn chỉnh: ví dụ hồ sơ tài liệu

Ví dụ sau kết hợp field final, kiểm tra đầu vào, defensive copy cho mảng và snapshot collection:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public final class DocumentSnapshot {
    private final String id;
    private final String title;
    private final byte[] content;
    private final List<String> labels;
    private final Instant createdAt;

    public DocumentSnapshot(
            String id,
            String title,
            byte[] content,
            List<String> labels,
            Instant createdAt) {

        this.id = requireText(id, "id");
        this.title = requireText(title, "title");
        this.content = Objects.requireNonNull(
                content, "content").clone();
        this.labels = List.copyOf(
                Objects.requireNonNull(labels, "labels"));
        this.createdAt = Objects.requireNonNull(
                createdAt, "createdAt");
    }

    private static String requireText(String value, String name) {
        Objects.requireNonNull(value, name);
        if (value.isBlank()) {
            throw new IllegalArgumentException(
                    name + " must not be blank");
        }
        return value;
    }

    public String id() {
        return id;
    }

    public String title() {
        return title;
    }

    public byte[] content() {
        return content.clone();
    }

    public List<String> labels() {
        return labels;
    }

    public Instant createdAt() {
        return createdAt;
    }

    public int contentSize() {
        return content.length;
    }
}
~~~

Các quyết định thiết kế:

- `String` và `Instant` là immutable nên có thể giữ tham chiếu.
- `byte[]` là mutable nên được copy ở đầu vào và đầu ra.
- `List<String>` được snapshot bằng `List.copyOf`; phần tử `String` cũng immutable.
- Các invariant như ID/title không rỗng được kiểm tra trước khi instance được sử dụng.
- Lớp là `final`, field là `private final`, không có setter hoặc phương thức thay đổi trạng thái.

Khi một phương thức cần cập nhật tài liệu, hãy tạo `DocumentSnapshot` mới với dữ liệu mới thay vì sửa object hiện tại. Ví dụ có thể cung cấp `withTitle(String newTitle)` trả về một instance mới, giữ nguyên các thành phần khác bằng cách truyền qua constructor; constructor tiếp tục thực hiện defensive copy cho mảng.

## 9. Builder vẫn có thể tạo ra đối tượng bất biến

Builder thường mutable để caller có thể cấu hình nhiều bước. Điều đó không làm cho đối tượng cuối cùng mutable nếu `build()` tạo snapshot độc lập:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class Query {
    private final List<String> filters;

    private Query(List<String> filters) {
        this.filters = List.copyOf(filters);
    }

    public List<String> filters() {
        return filters;
    }

    public static final class Builder {
        private final List<String> filters = new ArrayList<>();

        public Builder addFilter(String filter) {
            filters.add(Objects.requireNonNull(filter));
            return this;
        }

        public Query build() {
            return new Query(filters);
        }
    }
}
~~~

Sau khi gọi `build()`, caller có thể tiếp tục dùng builder để tạo query khác; query đã tạo vẫn giữ snapshot riêng. Constructor của `Query` là nơi chốt invariant và sao chép dữ liệu, vì vậy mọi đường tạo instance đều phải đi qua cùng quy tắc.

Nếu builder chứa mảng hoặc đối tượng mutable, constructor cuối cùng vẫn cần defensive copy. Không chuyển nguyên tham chiếu mutable từ builder sang đối tượng immutable rồi cho rằng builder đã hết được sử dụng.

## 10. Bất biến và an toàn đa luồng

Đối tượng immutable có lợi thế lớn trong môi trường nhiều luồng: sau khi tạo, không có thao tác cập nhật trạng thái nội bộ cần khóa. Nhiều luồng có thể đọc cùng instance mà không tranh chấp trên trạng thái của chính instance đó.

Java Memory Model quy định ngữ nghĩa đặc biệt cho field `final`: nếu đối tượng được khởi tạo đúng cách và `this` không thoát khỏi constructor, các luồng khác nhận được tham chiếu đến đối tượng sẽ có bảo đảm về giá trị field final sau khi constructor hoàn tất. Tuy nhiên, thiết kế vẫn nên dùng cơ chế công bố đối tượng (safe publication) rõ ràng như final field của holder đã được khởi tạo an toàn, `volatile`, synchronized hoặc concurrent collection khi chia sẻ qua các luồng.

Một số điểm cần nhớ:

- Field `final` không biến một mảng hoặc collection mutable thành immutable.
- Nếu một đối tượng con bị thay đổi sau khi công bố, lớp cha không còn bất biến sâu.
- Không gọi callback hoặc đăng ký `this` ra bên ngoài trong constructor.
- Nếu đối tượng quản lý tài nguyên có trạng thái vòng đời như socket, stream hoặc file handle, không nên gọi nó là immutable chỉ vì các field tham chiếu được khai báo final.
- Immutable object không tự làm cho các thao tác bên ngoài như ghi database hoặc gửi request trở nên thread-safe.

Thiết kế bất biến giảm nhu cầu đồng bộ hóa cho trạng thái dữ liệu. Nó không thay thế việc thiết kế đồng bộ cho các dịch vụ hoặc tài nguyên mutable mà đối tượng có thể tương tác.

## 11. Các kiểu immutable có sẵn nên ưu tiên

Khi mô hình hóa giá trị, ưu tiên các kiểu bất biến đã có trong Java:

| Nhu cầu | Kiểu thường phù hợp | Ghi chú |
| --- | --- | --- |
| Văn bản | `String` | Không thể sửa nội dung |
| Ngày không có giờ | `LocalDate` | Kiểu immutable trong `java.time` |
| Thời điểm tuyệt đối | `Instant` | Immutable, phù hợp lưu thời điểm UTC |
| Ngày giờ kèm múi giờ | `ZonedDateTime` | Immutable; quy tắc múi giờ lấy từ dữ liệu zone rules |
| Số nguyên lớn | `BigInteger` | Immutable, độ lớn tùy ý |
| Số thập phân | `BigDecimal` | Immutable; scale là một phần của biểu diễn |
| Tập giá trị nhỏ | `enum` | Các hằng là instance singleton; chỉ bất biến nếu không chứa trạng thái mutable và không cung cấp mutator |
| Data carrier | `record` | Thành phần tham chiếu mutable vẫn cần bảo vệ |

Với ngày giờ mới, dùng các kiểu trong `java.time` thay vì xây API mới dựa trên lớp ngày giờ mutable cũ. Nếu phải tích hợp một API bên ngoài dùng kiểu mutable, hãy chuyển đổi ở adapter biên và không để tham chiếu mutable đi sâu vào mô hình bất biến.

## 12. equals, hashCode và giá trị bất biến

Một đối tượng được dùng làm key trong hash-based collection phải giữ ổn định các field tham gia `equals` và `hashCode` trong suốt thời gian nó nằm trong collection. Nếu key mutable thay đổi sau khi được thêm vào `HashMap`, việc tra cứu hoặc xóa có thể không còn tìm thấy entry ở bucket ban đầu.

Immutable value object giúp giữ hợp đồng này ổn định. Khi tự triển khai `equals`/`hashCode`, chỉ dùng các thành phần thể hiện identity/value theo hợp đồng của kiểu. Với record, compiler tự sinh `equals`, `hashCode` và `toString` theo component; nếu component là mảng, cần lưu ý so sánh mặc định của mảng là theo identity, không phải nội dung. Hãy tự định nghĩa hợp đồng so sánh nội dung khi đó là ý nghĩa của value object.

Với `BigDecimal`, `equals` xét cả scale: `2.0` và `2.00` khác nhau theo `equals`, dù `compareTo` cho biết chúng có cùng giá trị số. Nếu dùng `BigDecimal` làm thành phần của value object, cần quyết định liệu scale có thuộc ý nghĩa của giá trị trong domain hay cần chuẩn hóa trước khi so sánh.

## 13. Chi phí và chiến lược sao chép

Defensive copy làm tăng chi phí CPU và bộ nhớ, đặc biệt với payload lớn hoặc API được gọi thường xuyên. Không nên bỏ bảo vệ dữ liệu chỉ vì phỏng đoán hiệu năng; trước hết hãy xác định dữ liệu nào mutable và nơi nào thật sự cần copy.

Một số cách kiểm soát chi phí:

- Ưu tiên kiểu immutable nhỏ cho dữ liệu có cấu trúc rõ.
- Dùng `List.copyOf`/`Map.copyOf` cho snapshot collection khi không cần cho phép null.
- Chỉ sao chép ở ranh giới ownership; không copy lặp lại nhiều lần ở mọi tầng nếu dữ liệu đã thuộc quyền sở hữu độc quyền và hợp đồng nội bộ bảo đảm điều đó.
- Với payload lớn, cân nhắc API đọc theo stream, truy cập theo đoạn hoặc một read-only abstraction có backing store không còn mutable alias.
- Không trả mảng nội bộ chỉ để tiết kiệm một lần copy nếu caller có thể thay đổi nó.
- Đo bằng benchmark đại diện trước khi tối ưu; giữ invariant và hợp đồng API làm tiêu chí.

Một API có thể cung cấp các phương thức đọc như `size()`, `byteAt(index)` hoặc `writeTo(OutputStream)` để tránh trả toàn bộ mảng. Với dữ liệu lớn, thiết kế giao diện truy cập phù hợp thường tốt hơn việc phơi bày cấu trúc mutable.

## 14. Kiểm thử lớp bất biến và defensive copy

Test nên kiểm tra cả thay đổi từ đầu vào lẫn thay đổi qua giá trị trả về.

Ví dụ với JUnit Jupiter:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class PacketTest {
    @Test
    void copiesInputAndOutputArray() {
        byte[] source = {1, 2, 3};
        var packet = new Packet(source);

        source[0] = 9;
        byte[] returned = packet.payload();
        returned[1] = 8;

        assertArrayEquals(new byte[] {1, 2, 3}, packet.payload());
    }

    @Test
    void snapshotsCollectionInput() {
        var source = new ArrayList<>(List.of("Java"));
        var course = new Course("Java 27", source);

        source.add("Changed");

        // Course giữ snapshot tạo lúc constructor chạy.
        assertEquals(List.of("Java"), course.topics());
        assertThrows(
                UnsupportedOperationException.class,
                () -> course.topics().add("Another"));
    }
}
~~~

Khi review, kiểm tra thêm:

- Constructor có lưu trực tiếp tham chiếu đến input mutable không?
- Accessor có trả field mutable nội bộ không?
- Collection copy là shallow hay deep?
- Các phần tử lồng nhau có thể thay đổi từ nơi khác không?
- Có phương thức nào cập nhật field qua callback, lazy cache hoặc thao tác nội bộ không?
- Builder có còn tham chiếu mutable sau khi build không?
- `equals`/`hashCode` có dựa trên trạng thái ổn định không?
- Đối tượng có bị công bố trước khi constructor hoàn tất không?

## 15. Lỗi thiết kế thường gặp

| Lỗi | Vì sao không an toàn | Cách xử lý |
| --- | --- | --- |
| Chỉ khai báo field là `final` | Tham chiếu không đổi nhưng object được tham chiếu vẫn mutable | Copy và bảo vệ trạng thái mutable |
| Trả trực tiếp mảng từ accessor | Caller sửa được dữ liệu nội bộ | Trả bản sao hoặc API đọc-only phù hợp |
| Dùng `Collections.unmodifiableList(input)` làm snapshot | Thay đổi qua input vẫn xuất hiện trong view | Copy input trước khi bọc, hoặc dùng `List.copyOf` |
| Dùng `List.copyOf` với phần tử mutable | Chỉ cấu trúc list được bảo vệ | Copy/chuyển từng phần tử thành immutable |
| Nghĩ record luôn immutable sâu | Component có thể là mảng hoặc object mutable | Copy trong compact constructor và bảo vệ accessor |
| Builder chuyển nguyên list sang đối tượng kết quả | Builder có thể tiếp tục thay đổi list đó | Constructor kết quả tạo snapshot |
| Cho phép subclass tùy ý | Subclass có thể thêm trạng thái hoặc thay đổi hành vi | Dùng `final` hoặc thiết kế sealed hierarchy với hợp đồng rõ |
| Dùng mutable object làm key hash collection | Thay đổi field có thể làm hỏng khả năng tra cứu | Dùng immutable key và ổn định equals/hashCode |
| Để `this` thoát trong constructor | Luồng khác có thể thấy instance chưa hoàn chỉnh | Hoàn tất constructor trước khi công bố |

## 16. Checklist thiết kế lớp bất biến

- [ ] Đã xác định trạng thái nào là một phần của giá trị đối tượng.
- [ ] Lớp được giới hạn kế thừa phù hợp, thường là `final` nếu không có nhu cầu mở rộng.
- [ ] Tất cả field là `private final` và được khởi tạo đầy đủ trong constructor.
- [ ] Constructor kiểm tra null, miền giá trị và invariant.
- [ ] Dữ liệu mutable đầu vào được defensive copy.
- [ ] Accessor không để lộ mảng, collection hoặc đối tượng mutable nội bộ.
- [ ] Collection được snapshot; các phần tử mutable cũng được bảo vệ.
- [ ] Record component mutable có copy trong constructor và accessor phù hợp.
- [ ] Builder tạo snapshot mới khi build.
- [ ] Không có setter hoặc phương thức thay đổi trạng thái sau khởi tạo.
- [ ] `this` không thoát khỏi constructor; đối tượng được công bố an toàn.
- [ ] `equals` và `hashCode` dựa trên trạng thái ổn định và đúng hợp đồng.
- [ ] Test bao gồm mutation input, mutation output và collection không sửa được.
- [ ] Chi phí copy được đo và tối ưu tại đúng ranh giới ownership.

## 17. Nguồn tài liệu chính thức

- [Java Language Specification, Java SE 27 — Classes](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html) — class, field, constructor, final và kế thừa.
- [Java Language Specification, Java SE 27 — Records](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10) — record declaration, component và constructor.
- [Java Language Specification, Java SE 27 — Memory Model](https://docs.oracle.com/javase/specs/jls/se27/html/jls-17.html) — đồng bộ hóa, visibility và final field semantics.
- [Java SE 27 API — List](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html) — `copyOf`, factory collection và hợp đồng unmodifiable.
- [Java SE 27 API — Set](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html) — `copyOf` và unmodifiable set.
- [Java SE 27 API — Map](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html) — `copyOf` và unmodifiable map.
- [Java SE 27 API — Collections](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html) — wrapper unmodifiable và các tiện ích collection.
- [Java SE 27 API — Arrays](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html) — `copyOf` và các thao tác mảng.
- [Java SE 27 API — java.time](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/package-summary.html) — các kiểu ngày giờ bất biến.

Một lớp chỉ thực sự bất biến khi caller không thể làm thay đổi trạng thái quan sát được qua bất kỳ tham chiếu nào. Hãy kiểm soát quyền sở hữu dữ liệu tại constructor, accessor và mọi ranh giới API để duy trì hợp đồng đó.
