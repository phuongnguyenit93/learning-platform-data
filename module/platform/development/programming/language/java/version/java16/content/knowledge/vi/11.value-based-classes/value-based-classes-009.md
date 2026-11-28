# Phân biệt value-based class với record và các đặc điểm bất biến

Java có nhiều kiểu dữ liệu được dùng như giá trị, chẳng hạn **Integer**, **Optional** và **LocalDate**. Các lớp này có hợp đồng *value-based*: chương trình quan tâm giá trị mà instance biểu diễn và không được phụ thuộc vào identity của từng instance.

Từ Java 16, **record** cung cấp cú pháp ngắn gọn để khai báo các lớp mang dữ liệu. Record cũng có component field **final** và tự sinh **equals()**, **hashCode()**, **toString()** theo các component. Vì có nhiều điểm giống nhau, record thường bị nhầm là value-based class. Hai khái niệm này có liên quan nhưng không đồng nhất.

Bài học này phân biệt hợp đồng value-based với record, giải thích shallow immutability và deep immutability, đồng thời hướng dẫn chọn cách biểu diễn dữ liệu phù hợp trong Java hiện đại.

## 1. Value-based class là gì?

Value-based class là một lớp có hợp đồng API yêu cầu chương trình làm việc theo giá trị của instance thay vì identity của object.

Tài liệu Java SE mô tả các đặc điểm chính:

- Các instance field do lớp khai báo đều là **final**. Những field này vẫn có thể tham chiếu tới object mutable.
- **equals()**, **hashCode()** và **toString()** được tính từ giá trị các field và object được tham chiếu, không dựa trên identity của instance.
- Khi hai instance bằng nhau theo **equals()**, các phương thức của lớp xem chúng có thể thay thế cho nhau mà không làm thay đổi hành vi quan sát được.
- Lớp không dùng monitor của instance để đồng bộ.
- API không hứa hẹn mỗi lần tạo giá trị sẽ nhận được một identity duy nhất. Factory có thể trả về cùng instance cho các giá trị bằng nhau.
- Lớp là **final** và có cấu trúc kế thừa theo hợp đồng value-based.

Một số ví dụ quen thuộc trong thư viện Java:

- Wrapper như **Integer**, **Long**, **Boolean**, **Double**.
- **Optional**, **OptionalInt**, **OptionalLong**, **OptionalDouble**.
- Nhiều kiểu trong **java.time**, như **LocalDate**, **LocalDateTime**, **Instant**, **Duration** và **Period**.

Cách nhận diện đáng tin cậy là đọc JavaDoc của lớp. Tài liệu thường tuyên bố rõ: **This is a value-based class** và dẫn tới phần mô tả hợp đồng value-based.

Không phân loại một lớp chỉ vì nó có field **final**, là **final class**, bất biến hoặc ghi đè **equals()**. Các đặc điểm đó riêng lẻ chưa đủ để kết luận lớp có hợp đồng value-based.

## 2. Record là gì và Java tự sinh những gì?

Record được chuẩn hóa trong Java 16 để biểu diễn một nhóm dữ liệu có cấu trúc cố định với ít mã khai báo hơn class thông thường.

Ví dụ:

~~~java
public record Point(int x, int y) {}
~~~

Khai báo này tạo một record class có:

- Hai component là **x** và **y**.
- Hai field tương ứng có dạng **private final**.
- Một canonical constructor nhận hai component.
- Hai accessor **x()** và **y()**.
- Các implementation **equals()**, **hashCode()** và **toString()** được compiler cung cấp nếu không khai báo tường minh.

Có thể sử dụng:

~~~java
Point first = new Point(3, 5);
Point second = new Point(3, 5);

System.out.println(first.x());              // 3
System.out.println(first.equals(second));   // true
System.out.println(first == second);        // false
System.out.println(first);                  // Point[x=3, y=5]
~~~

Hai record có cùng component nên bằng nhau theo **equals()**. Tuy nhiên, hai lần gọi **new** tạo hai object riêng biệt. Trong Java hiện hành, record vẫn là object có identity: toán tử **==** với hai reference kiểm tra chúng có cùng object hay không.

Đây là điểm quan trọng khi so sánh record với value-based class. Record cung cấp equality dựa trên component theo implementation mặc định, nhưng bản thân từ khóa **record** không tự công bố hợp đồng value-based cho lớp.

## 3. Value-based class và record khác nhau ở đâu?

Hai khái niệm có những đặc điểm giao nhau, nhưng trả lời hai câu hỏi khác nhau:

- **Value-based class** mô tả hợp đồng sử dụng của một lớp trong API: instance bằng nhau được xem là có thể thay thế cho nhau và chương trình không nên dựa vào identity.
- **Record** là một loại khai báo lớp trong ngôn ngữ Java: component được công bố trong header, field tương ứng là final và compiler cung cấp các thành viên dữ liệu theo quy tắc của record.

Bảng sau tóm tắt sự khác biệt:

| Tiêu chí | Value-based class | Record trong Java hiện hành |
| --- | --- | --- |
| Bản chất | Hợp đồng API về cách sử dụng instance | Cấu trúc khai báo lớp mang dữ liệu |
| Field instance | Chỉ khai báo field final theo hợp đồng | Component field được khai báo private final |
| equals() | Phải phản ánh giá trị, không dựa identity | Mặc định được sinh từ các component |
| hashCode() | Phải tương thích với equality theo giá trị | Mặc định được sinh từ các component |
| Identity | Không được dựa vào identity của instance | Instance vẫn có object identity |
| Monitor | Không đồng bộ bằng monitor của instance | Ngôn ngữ vẫn cho phép dùng monitor, nhưng record thường không phải lựa chọn tốt làm khóa |
| Bất biến | Các field final không bảo đảm bất biến sâu | Shallowly immutable |
| Cách nhận diện | JavaDoc công bố rõ hợp đồng value-based | Nhìn vào khai báo record |

Ví dụ về value-based class:

~~~java
import java.time.LocalDate;

LocalDate date1 = LocalDate.of(2026, 11, 27);
LocalDate date2 = LocalDate.of(2026, 11, 27);

System.out.println(date1.equals(date2)); // true
// Không dựa vào date1 == date2.
~~~

Ví dụ về record:

~~~java
public record CustomerId(String value) {}

CustomerId id1 = new CustomerId("C-100");
CustomerId id2 = new CustomerId("C-100");

System.out.println(id1.equals(id2)); // true
System.out.println(id1 == id2);      // false
~~~

Cả hai ví dụ đều có equality theo giá trị. Điểm khác là **LocalDate** được Java API công bố là value-based class, còn **CustomerId** là record có identity thông thường theo ngữ nghĩa Java.

Vì vậy, không nên kết luận rằng mọi record đều là value-based class. Cũng không nên suy ra rằng mọi value-based class phải được viết bằng record.

## 4. Record bất biến ở mức nào?

Tài liệu Java mô tả record là *shallowly immutable* — bất biến ở mức nông.

Các component field của record là **final**, nên sau khi constructor khởi tạo, chương trình không thể gán lại tham chiếu hoặc giá trị của field đó. Nhưng nếu component tham chiếu tới object mutable, trạng thái bên trong object được tham chiếu vẫn có thể thay đổi.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

public record Team(String name, List<String> members) {}

List<String> names = new ArrayList<>();
names.add("An");

Team team = new Team("Backend", names);
names.add("Bình");

System.out.println(team.members()); // [An, Bình]
~~~

Field **members** của record không thể được gán sang một list khác sau khi khởi tạo, nhưng list ban đầu vẫn mutable. Thay đổi list từ bên ngoài làm dữ liệu quan sát qua record thay đổi.

Điều này cho thấy **final reference** không đồng nghĩa object được tham chiếu là immutable.

### Defensive copy với List

Nếu muốn record giữ một snapshot không thể sửa đổi của danh sách đầu vào, hãy sao chép trong canonical constructor:

~~~java
import java.util.List;

public record Team(String name, List<String> members) {
    public Team {
        members = List.copyOf(members);
    }
}
~~~

**List.copyOf()** tạo một danh sách không thể sửa đổi và tách trạng thái của record khỏi list mutable mà caller truyền vào. Nếu phần tử trong danh sách cũng là object mutable, chúng vẫn có thể thay đổi; bản sao này chỉ bảo vệ cấu trúc danh sách và tham chiếu phần tử.

Đây là cách thực tế để tăng mức độ bất biến của record khi component là collection.

### Component là mảng cần xử lý riêng

Mảng Java mutable và không ghi đè **equals()** để so sánh nội dung. Nếu record có component là mảng, implementation equality mặc định sẽ so sánh component theo **Objects.equals()**; với mảng, điều này tương đương so sánh reference.

Ví dụ:

~~~java
public record Payload(byte[] bytes) {}

Payload first = new Payload(new byte[] {1, 2});
Payload second = new Payload(new byte[] {1, 2});

System.out.println(first.equals(second)); // false
~~~

Hai mảng chứa cùng byte nhưng là hai object mảng khác nhau, nên hai record không bằng nhau theo implementation mặc định.

Nếu cần bảo vệ dữ liệu mảng, có thể clone khi nhận và khi trả component:

~~~java
public record Payload(byte[] bytes) {
    public Payload {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Đoạn code trên ngăn caller thay đổi trực tiếp mảng nội bộ. Tuy nhiên, nếu yêu cầu equality theo nội dung mảng, cần tự định nghĩa **equals()** và **hashCode()** bằng **Arrays.equals()** và **Arrays.hashCode()**, hoặc chọn một kiểu dữ liệu khác có equality theo nội dung phù hợp hơn.

## 5. Value-based có đồng nghĩa với immutable không?

Không nên dùng hai thuật ngữ này thay thế cho nhau.

**Immutable** mô tả khả năng thay đổi trạng thái: sau khi object được tạo, trạng thái được công bố không thể thay đổi theo hợp đồng của lớp. **Value-based** mô tả cách chương trình được phép quan sát và sử dụng instance: equality dựa trên giá trị, instance bằng nhau có thể thay thế cho nhau, và identity không phải phần của hợp đồng.

Trong thư viện Java, nhiều value-based class phổ biến cũng immutable. Chẳng hạn **LocalDate** không cung cấp thao tác thay đổi ngày hiện tại; các phép cộng ngày trả về một giá trị ngày mới. Tuy nhiên, không nên suy rộng rằng chỉ cần lớp immutable là tự động value-based.

Ngược lại, một record có field final vẫn có thể chứa tham chiếu tới object mutable. Record do đó có thể chỉ bất biến ở mức nông.

Có thể phân biệt bằng các câu hỏi:

| Câu hỏi | Đặc điểm cần xem |
| --- | --- |
| Có thể thay đổi trạng thái sau khi tạo object không? | Immutability |
| Hai instance bằng nhau có thể thay thế cho nhau theo hợp đồng API không? | Value-based semantics |
| Có thể phân biệt từng instance bằng identity không? | Object identity |
| Field final có trỏ tới object mutable không? | Shallow/deep immutability |

Để thiết kế dữ liệu ổn định, cần xem cả ba khía cạnh: trạng thái có thể thay đổi hay không, equality được định nghĩa thế nào và identity có thuộc hợp đồng sử dụng hay không.

## 6. Chọn class, record hay value-based API?

Hãy chọn theo mục đích dữ liệu và hợp đồng cần cung cấp.

### Dùng record cho data carrier

Record phù hợp khi dữ liệu có tập component cố định, muốn constructor, accessor, **equals()**, **hashCode()** và **toString()** theo component.

~~~java
public record OrderLine(String productCode, int quantity, long unitPrice) {
    public OrderLine {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }
    }
}
~~~

Canonical constructor có thể kiểm tra dữ liệu đầu vào hoặc chuẩn hóa component trước khi gán vào field.

### Dùng class thông thường khi cần quản lý vòng đời và trạng thái

Nếu object có trạng thái thay đổi, hành vi nghiệp vụ phong phú, identity quan trọng hoặc cần kiểm soát kế thừa, một class thông thường thường phù hợp hơn.

~~~java
public class ShoppingCart {
    private final String id;
    private int itemCount;

    public ShoppingCart(String id) {
        this.id = id;
    }

    public synchronized void addItem() {
        itemCount++;
    }

    public synchronized int itemCount() {
        return itemCount;
    }
}
~~~

Class này có trạng thái thay đổi theo thời gian và các thao tác nghiệp vụ gắn với một instance cụ thể. Record không phải lựa chọn tự nhiên cho mọi object trong ứng dụng.

### Dùng value-based class của Java khi API đã cung cấp kiểu phù hợp

Nếu cần ngày tháng, thời điểm, số nguyên có thể null hoặc kết quả có thể vắng mặt, ưu tiên kiểu chuẩn có hợp đồng rõ ràng:

~~~java
import java.time.LocalDate;
import java.util.Optional;

LocalDate dueDate = LocalDate.now().plusDays(7);
Optional<String> nickname = Optional.of("Minh");
~~~

Các lớp này cung cấp semantics và hành vi được Java API định nghĩa. Khi so sánh, dùng **equals()**; không dựa vào identity của instance.

## 7. Có nên dùng record làm khóa synchronized không?

Record trong Java hiện hành vẫn có monitor object như các class khác, vì vậy ngôn ngữ cho phép viết:

~~~java
public record LockKey(String name) {}

LockKey key = new LockKey("inventory");

synchronized (key) {
    // Được phép về mặt ngôn ngữ
}
~~~

Tuy nhiên, không nên chọn record làm khóa đồng bộ trong thiết kế ứng dụng thông thường. Record thường được công khai như một data carrier; code khác có thể giữ reference tới nó và đồng bộ trên cùng monitor ngoài dự kiến. Equality theo component cũng không khiến hai record bằng nhau chia sẻ cùng monitor.

Hãy dùng khóa riêng:

~~~java
public class Inventory {
    private final Object lock = new Object();
    private int quantity;

    public void add(int amount) {
        synchronized (lock) {
            quantity += amount;
        }
    }
}
~~~

Điểm cần phân biệt: cảnh báo JEP 390 áp dụng cho instance của các lớp được nhận diện là value-based. Từ khóa **record** tự nó không làm lớp trở thành value-based class và không tự động khiến mọi thao tác identity trên record bị cấm. Dù vậy, khóa **private final Object** vẫn là lựa chọn rõ ràng và dễ kiểm soát hơn.

## 8. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Record chính là value-based class | Record là cấu trúc ngôn ngữ; value-based là hợp đồng API |
| Mọi record đều không có identity | Record trong Java hiện hành vẫn là object có identity |
| Field final làm object bất biến sâu | Field final có thể tham chiếu tới object mutable |
| Record tự động bảo vệ collection component | Cần defensive copy nếu không muốn chia sẻ collection mutable |
| Hai record bằng nhau có cùng reference | **equals()** có thể true trong khi **==** là false |
| Class immutable nào cũng value-based | Cần kiểm tra hợp đồng và JavaDoc |
| Value-based instance có thể dùng làm monitor nếu immutable | Hợp đồng value-based khuyến cáo không dùng monitor của instance |

## 9. Kết luận

Value-based class và record cùng hỗ trợ cách mô hình hóa dữ liệu theo giá trị, nhưng chúng không phải cùng một khái niệm. Value-based class là hợp đồng API yêu cầu equality theo giá trị và tránh phụ thuộc identity. Record là cấu trúc lớp được chuẩn hóa từ Java 16, tự sinh các thành viên dữ liệu và cung cấp tính bất biến ở mức nông.

Khi thiết kế, hãy dùng record cho data carrier có component cố định, dùng class thông thường cho object có vòng đời hoặc trạng thái thay đổi, và dùng các API value-based của Java khi chúng đã biểu diễn đúng miền dữ liệu. Luôn kiểm tra mutable component, defensive copy, equality và identity trước khi đưa kiểu dữ liệu vào collection hoặc cơ chế đồng bộ.

## Tài liệu tham khảo

- [JEP 395: Records](https://openjdk.org/jeps/395)
- [Record — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Record.html)
- [JLS 27 — Record Classes (Section 8.10)](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.10)
- [Value-based Classes — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/doc-files/ValueBased.html)
- [List.copyOf() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Arrays.equals() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html#equals(byte[],byte[]))
- [Arrays.hashCode() — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Arrays.html#hashCode(byte[]))

