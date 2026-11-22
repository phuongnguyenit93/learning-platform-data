# Sao chép thành phần có thể thay đổi khi cần độc lập

## 1. Vấn đề: sao chép đối tượng chưa chắc đã tạo ra trạng thái độc lập

Trong Java, biến kiểu tham chiếu giữ **tham chiếu tới đối tượng**, không giữ toàn bộ nội dung của đối tượng. Hai đối tượng bên ngoài có thể khác nhau nhưng vẫn trỏ tới **cùng một thành phần bên trong**. Khi thành phần ấy có thể thay đổi (mutable), việc sửa qua một bên có thể làm trạng thái quan sát được của bên còn lại thay đổi.

Ví dụ, khi tạo một hồ sơ từ `Address` do bên gọi cung cấp, việc chỉ gán `this.address = address` khiến hồ sơ và bên gọi dùng chung một `Address`. Nếu bên gọi thay đổi thành phố, hồ sơ cũng thấy thành phố mới. Điều tương tự xảy ra với mảng, `ArrayList`, `HashMap` hoặc đối tượng mutable lồng trong collection.

**Mục tiêu của sao chép phòng vệ (defensive copying):** ở những ranh giới mà hợp đồng yêu cầu độc lập, mỗi bên phải sở hữu trạng thái có thể thay đổi của mình; thay đổi hợp lệ từ một phía không được làm biến đổi trạng thái của phía kia ngoài ý muốn.

Cần phân biệt ba ý:

- **Khác tham chiếu:** `a != b` chỉ nói `a` và `b` không phải cùng một đối tượng bên ngoài.
- **Bằng giá trị:** `a.equals(b)` phụ thuộc hợp đồng `equals()`; hai bản sao độc lập vẫn có thể bằng giá trị.
- **Độc lập về trạng thái mutable:** không còn thành phần mutable bị chia sẻ mà một bên có thể sửa và gây ảnh hưởng ngoài ý muốn. Đây mới là điều cần kiểm tra khi bài toán đòi hỏi độc lập.

Không phải mọi thành phần đều phải sao chép. `String`, `Integer`, `BigDecimal` và phần lớn kiểu trong `java.time` (như `LocalDate`, `Instant`) là immutable, nên thường có thể chia sẻ an toàn. Trọng tâm là **thành phần thực sự mutable và có thể bị sửa qua tham chiếu được chia sẻ**.

## 2. Shallow copy, deep copy và mức sao chép thực sự cần

Giả sử `Order` có `List<OrderLine> lines` và mỗi `OrderLine` có thể thay đổi số lượng.

| Cách xử lý | Điều gì được tách? | Rủi ro còn lại |
| --- | --- | --- |
| `Order b = a;` | Không có bản sao nào; cùng đối tượng `Order` | Mọi trạng thái đều dùng chung |
| Sao chép `Order` nhưng giữ `lines` cũ | Chỉ đối tượng `Order` bên ngoài | Thao tác thêm/xóa/sửa phần tử có thể ảnh hưởng cả hai |
| `new ArrayList<>(a.lines)` | Tạo danh sách mới, tách thao tác thêm/xóa phần tử | Các `OrderLine` bên trong vẫn dùng chung |
| Tạo danh sách mới và sao chép từng `OrderLine` mutable | Tách cả cấu trúc danh sách và từng phần tử mutable | Cần tiếp tục xét thành phần mutable lồng sâu hơn |
| Sao chép toàn bộ đồ thị đối tượng | Tách mọi đối tượng mutable theo chính sách đã chọn | Tốn chi phí và phải xử lý alias, chu trình, tài nguyên đặc biệt |

**Shallow copy** (sao chép nông) thường chỉ tạo vỏ mới, còn tham chiếu bên trong vẫn trỏ tới đối tượng cũ. **Deep copy** (sao chép sâu) sao chép đệ quy các thành phần mutable cần tách; khái niệm này phải được xác định theo hợp đồng của mô hình dữ liệu, không đơn giản là “copy càng nhiều càng tốt”.

Ví dụ: nếu `OrderLine` chứa mã sản phẩm kiểu `String`, không cần tạo `String` mới. Nếu chứa `DiscountPolicy` immutable được dùng chung theo thiết kế, có thể giữ tham chiếu. Nếu chứa `Address` mutable mà đơn hàng cần tự quản lý, phải sao chép nó.

**Nguyên tắc quyết định:** hỏi “Ai sở hữu và có thể sửa đối tượng này?”; sau đó chỉ tách những phần mutable mà hợp đồng yêu cầu độc lập.

## 3. Sao chép ở cả đầu vào và đầu ra

Một lớp muốn kiểm soát trạng thái của mình thường cần bảo vệ **hai chiều**:

1. **Khi nhận dữ liệu** qua constructor, setter hoặc phương thức cập nhật: sao chép mutable input trước khi lưu, ngăn bên gọi sửa đối tượng sau khi đã truyền vào.
2. **Khi trả dữ liệu** qua getter hoặc phương thức xuất trạng thái: trả bản sao, hoặc trả giao diện immutable thực sự phù hợp, ngăn bên gọi sửa trạng thái nội bộ.

Chỉ sao chép khi khởi tạo nhưng getter lại trả thẳng trường nội bộ thì vẫn rò rỉ trạng thái. Ngược lại, chỉ sao chép trong getter nhưng constructor giữ tham chiếu đầu vào thì bên gọi vẫn có thể sửa từ bên ngoài.

**Chú ý:** `final` chỉ ngăn gán lại trường tham chiếu; `private final List<Item> items` vẫn có thể chứa danh sách hoặc phần tử mutable. `Collections.unmodifiableList(list)` tạo view cấm sửa qua view, nhưng vẫn phản ánh các thay đổi thực hiện qua `list` gốc. `List.copyOf(list)` cung cấp danh sách không thể sửa về mặt cấu trúc, nhưng **không sao chép sâu các phần tử**.

## 4. Ví dụ Java 17+: tách đối tượng mutable lồng trong danh sách

Ví dụ có hai lớp: `Address` thay đổi được thành phố; `Profile` cần giữ ảnh chụp trạng thái địa chỉ lúc khởi tạo. Vì vậy `Profile` sao chép `Address` ở cả trường đơn và từng phần tử của `List<Address>`. Khi trả dữ liệu, nó cũng tạo bản sao để không lộ trạng thái nội bộ.

Lưu vào tệp **DefensiveCopyDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class DefensiveCopyDemo {
    static final class Address {
        private String city;

        Address(String city) {
            this.city = Objects.requireNonNull(city);
        }

        Address(Address source) {
            this(Objects.requireNonNull(source).city);
        }

        String city() {
            return city;
        }

        void setCity(String city) {
            this.city = Objects.requireNonNull(city);
        }
    }

    static final class Profile {
        private final String name;
        private final Address currentAddress;
        private final List<Address> priorAddresses;

        Profile(String name, Address currentAddress,
                List<Address> priorAddresses) {
            this.name = Objects.requireNonNull(name);
            this.currentAddress = new Address(
                    Objects.requireNonNull(currentAddress));

            Objects.requireNonNull(priorAddresses);
            List<Address> copies = new ArrayList<>(priorAddresses.size());
            for (Address address : priorAddresses) {
                copies.add(new Address(address));
            }
            this.priorAddresses = List.copyOf(copies);
        }

        Address currentAddress() {
            return new Address(currentAddress);
        }

        List<Address> priorAddresses() {
            List<Address> copies = new ArrayList<>(priorAddresses.size());
            for (Address address : priorAddresses) {
                copies.add(new Address(address));
            }
            return copies;
        }

        String describe() {
            List<String> cities = priorAddresses.stream()
                    .map(Address::city)
                    .toList();
            return name + " @ " + currentAddress.city()
                    + ", previous=" + cities;
        }
    }

    public static void main(String[] args) {
        Address current = new Address("Ha Noi");
        Address previous = new Address("Da Nang");
        List<Address> history = new ArrayList<>();
        history.add(previous);

        Profile profile = new Profile("An", current, history);

        // Thay đổi nguồn sau khi truyền vào constructor.
        current.setCity("Hue");
        previous.setCity("Can Tho");
        history.clear();
        System.out.println(profile.describe());

        // Thay đổi bản sao nhận từ getter.
        profile.currentAddress().setCity("Nha Trang");
        List<Address> exported = profile.priorAddresses();
        exported.get(0).setCity("Hai Phong");
        exported.clear();
        System.out.println(profile.describe());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Đầu ra:

~~~text
An @ Ha Noi, previous=[Da Nang]
An @ Ha Noi, previous=[Da Nang]
~~~

**Phân tích từng lớp bảo vệ:**

- `new Address(currentAddress)` ngăn `current.setCity(...)` bên ngoài làm thay đổi `Profile`.
- Vòng lặp sao chép từng phần tử `Address` tách các đối tượng mutable mà `history` ban đầu tham chiếu tới. Chỉ `new ArrayList<>(history)` sẽ không đủ.
- `List.copyOf(copies)` giữ cấu trúc danh sách nội bộ không thể thêm/xóa; sự độc lập của phần tử đến từ những lệnh `new Address(address)` trước đó.
- Getter `currentAddress()` trả bản sao; getter `priorAddresses()` tạo danh sách mới **và** sao chép từng phần tử. Caller có thể sửa hoặc xóa dữ liệu nhận về mà không làm đổi hồ sơ.
- `name` dùng `String` immutable; không cần sao chép nó.

Ví dụ này chọn chính sách **ảnh chụp khi tạo**. Nếu nghiệp vụ muốn `Profile` luôn nhìn thấy địa chỉ mới của một đối tượng sống bên ngoài, việc cố tách sâu sẽ làm sai ý nghĩa nghiệp vụ. Chính sách sở hữu phải quyết định trước cách sao chép.

## 5. Các kiểu dữ liệu và lựa chọn sao chép thông dụng

### Mảng

Với mảng phần tử nguyên thủy như `int[]`, `Arrays.copyOf` sao chép các giá trị nên đủ để tách trạng thái của mảng một chiều.

Đoạn sau minh họa lớp có thể dùng trong chương trình Java có import `java.util.Arrays` và `java.util.Objects` (đây là đoạn minh họa, không có `main` độc lập):

~~~java
final class ScoreBoard {
    private final int[] scores;

    ScoreBoard(int[] scores) {
        int[] source = java.util.Objects.requireNonNull(scores);
        this.scores = java.util.Arrays.copyOf(source, source.length);
    }

    int[] scores() {
        return java.util.Arrays.copyOf(scores, scores.length);
    }
}
~~~

Với `Address[]`, `Arrays.copyOf` chỉ tạo **mảng mới chứa cùng tham chiếu Address**; cần sao chép từng phần tử nếu `Address` mutable. Với `int[][]`, `array.clone()` hoặc `Arrays.copyOf(array, ...)` chỉ tách mảng ngoài; muốn tách tất cả hàng, phải sao chép từng `int[]` bên trong.

### Collection và Map

- `new ArrayList<>(source)`, `new HashSet<>(source)` hoặc `new HashMap<>(source)`: sao chép cấu trúc chứa; phần tử, key, value là cùng tham chiếu nếu chúng là object.
- `List.copyOf(source)`, `Set.copyOf(source)`, `Map.copyOf(source)`: tạo collection không thể cập nhật qua API của chúng, **không đảm bảo phần tử/key/value mutable được tách**; các factory này cũng không chấp nhận phần tử hoặc entry null.
- Nếu giá trị của `Map<String, MutableValue>` cần độc lập, tạo map mới **và sao chép từng MutableValue**. Nếu key cũng mutable, cần một thiết kế key an toàn: thay đổi key đang nằm trong `HashMap` có thể phá hợp đồng `hashCode/equals` và làm việc tra cứu thất bại.
- Với nested collection, xét lần lượt từng tầng: sao chép danh sách ngoài không đồng nghĩa đã sao chép danh sách con hay các object trong nó.

### Đối tượng ngày giờ cũ và kiểu immutable

`java.util.Date` và `Calendar` mutable; nếu vẫn phải dùng, sao chép khi nhận/trả (ví dụ `new Date(original.getTime())`, với `Calendar` dùng `clone()` khi phù hợp). Các kiểu hiện đại trong `java.time` như `LocalDate`, `LocalDateTime`, `Instant` là immutable và thường là lựa chọn tốt hơn cho mô hình dữ liệu mới.

**Không có công thức duy nhất cho mọi kiểu:** luồng dữ liệu, buffer, socket, file handle, thread, lock và đối tượng chứa tài nguyên hệ thống không thể được “deep copy” một cách có nghĩa chỉ bằng duyệt trường; cần xác định cơ chế tạo mới, chia sẻ có kiểm soát hoặc cấm sao chép.

## 6. Copy constructor, factory, clone và serialization

**Copy constructor** (ví dụ `new Address(existing)`) hoặc **factory** (ví dụ `Address.copyOf(existing)`) diễn đạt rõ quy tắc sao chép. Chúng dễ đọc và cho phép kiểm soát các trường nào được giữ, sao chép, chuẩn hóa hoặc từ chối.

`Object.clone()` chỉ thực hiện sao chép theo trường ở mức cơ bản; với trường tham chiếu, bản sao vẫn chia sẻ object bên trong. `Cloneable` và override `clone()` không tự biến một lớp thành deep-copy. Nếu kế thừa có trạng thái mutable, việc đảm bảo sao chép đúng còn phức tạp hơn.

Không nên dùng serialization rồi deserialize như giải pháp sao chép chung: đòi hỏi đồ thị có thể tuần tự hóa, tốn tài nguyên, có ràng buộc bảo mật và có thể làm sai ý nghĩa các object/tài nguyên đặc biệt. Chỉ cân nhắc khi chính hợp đồng dữ liệu và định dạng serialization đã được thiết kế cho mục tiêu đó.

Một phương thức `copy()` nên ghi rõ: shallow hay deep theo những trường nào, có giữ quan hệ cùng tham chiếu trong đồ thị hay không, xử lý null, chu trình và tài nguyên như thế nào.

## 7. Những điểm khó khi đồ thị đối tượng phức tạp

### Giữ cấu trúc chia sẻ bên trong bản sao

Giả sử đối tượng gốc có `left` và `right` cùng trỏ đến **một** `Node`. Khi sao chép sâu, có hai chính sách khác nhau: (a) trong bản sao, `left` và `right` vẫn cùng trỏ tới **một Node mới**; hoặc (b) tạo hai `Node` khác nhau. Cả hai đều tách khỏi bản gốc, nhưng hành vi nội bộ của bản sao khác nhau.

Nếu cần bảo toàn cấu trúc alias, dùng ánh xạ `IdentityHashMap<Original, Copy>` theo **định danh tham chiếu** và kiểm tra node đã sao chép trước khi tạo mới. Cách này còn giúp xử lý đồ thị có chu trình `a.next = b; b.next = a` mà không đệ quy vô hạn. Không dùng `HashMap` dựa trên `equals()` cho tác vụ phân biệt các node gốc có giá trị bằng nhau nhưng khác định danh.

### Kế thừa, invariant và logic miền

Copy constructor phải giữ các invariant: kiểm tra đầu vào, tránh alias không mong muốn, và không gọi những phương thức có thể bị override trong lúc khởi tạo nếu điều đó phá tính đúng đắn. Không mặc định sao chép cả bộ nhớ cache, listener hay ID nghiệp vụ: một bản sao mới có thể cần ID riêng, cache tính lại hoặc listener riêng theo yêu cầu nghiệp vụ.

### Đồng thời và hiệu năng

Sao chép bảo vệ khỏi **sửa đổi thông qua tham chiếu chia sẻ sau thời điểm copy**, nhưng không tự bảo đảm ảnh chụp nhất quán khi thread khác đang sửa nguồn trong lúc sao chép. Với dữ liệu concurrent, cần cơ chế đồng bộ, snapshot do nguồn cung cấp hoặc cấu trúc immutable phù hợp.

Deep copy thường tốn thời gian và bộ nhớ theo số lượng thành phần được sao chép. Với dữ liệu lớn hoặc copy nhiều lần, có thể cân nhắc mô hình immutable, persistent data structure, thao tác cập nhật qua API kín hoặc thiết kế ownership rõ ràng. Tối ưu hóa chỉ sau khi hợp đồng độc lập được xác định.

## 8. Lỗi phổ biến và cách phát hiện

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| `this.items = input;` khi cần độc lập | Giữ nguyên danh sách đầu vào | Sao chép cấu trúc, và cả phần tử mutable nếu cần |
| `new ArrayList<>(input)` rồi coi là deep copy | Phần tử object vẫn dùng chung | Copy từng phần tử mutable |
| Getter trả thẳng mảng/list/Date nội bộ | Người dùng sửa qua getter | Trả bản sao phòng vệ hoặc API immutable |
| Chỉ dựa vào `final` hoặc `record` | Component tham chiếu tới object mutable vẫn có thể bị sửa | Constructor chuẩn hóa/copy và accessor phòng vệ nếu cần |
| Dùng `Collections.unmodifiableList(input)` để “chụp” dữ liệu | View vẫn thấy thay đổi qua `input` | Tạo snapshot rồi quyết định có copy sâu phần tử không |
| Dùng `clone()` rồi giả định mọi trường độc lập | Clone mặc định là nông | Định nghĩa rõ và kiểm tra mọi trường mutable |
| Deep copy mù quáng mọi object | Tốn kém hoặc phá identity/tài nguyên nghiệp vụ | Copy theo hợp đồng ownership và invariant |

**Kiểm thử quan trọng hơn chỉ so sánh `equals()`:**

1. Khởi tạo bản sao; xác nhận dữ liệu ban đầu tương đương.
2. Sửa từng thành phần mutable của **nguồn**; kiểm tra bản sao giữ nguyên.
3. Sửa từng thành phần mutable được **xuất ra qua getter**; kiểm tra trạng thái nội bộ giữ nguyên.
4. Nếu lớp có chức năng copy đối tượng, sửa bản sao và đảm bảo bản gốc không đổi.
5. Với cấu trúc lồng nhau, thử cả thêm/xóa phần tử và sửa **nội dung phần tử**; với graph có alias/chu trình, kiểm tra quan hệ tham chiếu theo hợp đồng.
6. Thử các trường hợp null, danh sách rỗng, object trùng tham chiếu và concurrent access nếu lớp cam kết hỗ trợ.

Ví dụ, kiểm tra `copy != original` mới chỉ xác nhận khác vỏ; cần thử thay đổi sâu hơn mới phát hiện shared mutable state.

## 9. Quy trình áp dụng vào thiết kế

Khi thiết kế một lớp Java yêu cầu độc lập:

1. **Lập danh sách trường và phụ thuộc lồng nhau.** Xác định kiểu nào immutable, kiểu nào mutable, kiểu nào sở hữu tài nguyên.
2. **Xác định ranh giới ownership.** Dữ liệu có phải snapshot? Ai được phép sửa? Việc cập nhật nguồn có cần tự lan sang đối tượng này không?
3. **Chọn chiến lược theo từng trường.** Chia sẻ immutable; sao chép mutable khi cần độc lập; dùng API cập nhật có kiểm soát cho trạng thái phải chia sẻ.
4. **Bảo vệ mọi đường ra/vào.** Constructor, setter, getter, builder, copy constructor, factory và các phương thức trả collection đều có thể làm lộ tham chiếu.
5. **Kiểm thử bằng đột biến từ cả hai phía.** Tránh chỉ kiểm tra giá trị ban đầu hoặc định danh của đối tượng ngoài.
6. **Đánh giá hiệu năng và tính nhất quán.** Đảm bảo quy tắc sao chép không phá hợp đồng nghiệp vụ hay yêu cầu concurrency.

**Tự kiểm tra:** Nếu có `List<MutableAddress> addresses`, việc đặt `this.addresses = List.copyOf(addresses)` đã đủ để một đối tượng độc lập chưa?

**Đáp án:** Chưa, nếu bên gọi vẫn giữ các `MutableAddress` và có thể sửa chúng. `List.copyOf` chỉ kiểm soát cấu trúc danh sách; phải sao chép từng địa chỉ mutable, rồi lưu collection snapshot. Khi xuất danh sách, cũng phải tránh đưa các địa chỉ mutable nội bộ ra ngoài nếu không muốn caller sửa chúng.

**Ghi nhớ:** Mục tiêu không phải ép mọi object thành deep copy; mục tiêu là **không vô tình chia sẻ trạng thái có thể thay đổi ở nơi hợp đồng đòi hỏi sự độc lập**.