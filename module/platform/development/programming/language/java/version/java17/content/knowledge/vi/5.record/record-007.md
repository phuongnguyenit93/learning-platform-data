# Giới hạn bất biến nông và sao chép phòng vệ trong Java 17 `record`

`record` giúp Java mô tả một đối tượng dữ liệu ngắn gọn: khai báo thành phần dữ liệu một lần và để trình biên dịch tạo constructor, accessor, `equals()`, `hashCode()` và `toString()`. Nhưng một nhầm lẫn phổ biến là cho rằng **mọi record đều bất biến hoàn toàn**.

Trong Java 17, các trường thành phần của record là `private final`, nghĩa là không thể gán lại tham chiếu sau khi đối tượng được tạo. Nếu thành phần là một `List`, `Map`, mảng hoặc đối tượng có phương thức sửa trạng thái, phần dữ liệu **bên trong** vẫn có thể thay đổi. Sự khác biệt giữa *bất biến nông* và *bất biến sâu* quyết định cách thiết kế record dùng làm DTO, giá trị miền nghiệp vụ, phần tử cache hay khóa trong collection.

Bài này tập trung vào giới hạn đó và kỹ thuật **sao chép phòng vệ (defensive copying)** khi nhận dữ liệu và khi trả dữ liệu. Các ví dụ sử dụng API ổn định của Java 17, gồm `record`, `List.copyOf`, `Map.copyOf`, `java.time` và `Arrays`; không cần bật tính năng preview.

## 1. Record thực sự bất biến ở mức nào?

Xét khai báo:

~~~java
public record Team(String name, java.util.List<String> members) {
}
~~~

Trình biên dịch tạo các trường thành phần tương đương về ý nghĩa với:

~~~java
private final String name;
private final java.util.List<String> members;
~~~

Điều đó đảm bảo:

- Không thể gán lại `name` hoặc `members` của cùng một record sau khi xây dựng.
- Không có setter mặc định.
- Accessor `name()` và `members()` cung cấp dữ liệu thành phần.
- Bản thân lớp record là `final`, không thể tạo subclass bằng `extends`.

Nhưng `final` trên một **trường tham chiếu** chỉ khóa tham chiếu, không làm cho đối tượng được tham chiếu trở thành bất biến.

~~~java
import java.util.ArrayList;
import java.util.List;

record Team(String name, List<String> members) {
}

class Demo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Bình"));
        Team team = new Team("Backend", source);

        source.add("Chi");             // Sửa từ biến ban đầu
        team.members().remove("An");   // Sửa qua accessor của record

        System.out.println(team.members()); // [Bình, Chi]
    }
}
~~~

Dù không thể viết `team.members = ...`, danh sách vẫn có thể bị thay đổi từ hai đường: **tham chiếu ban đầu do bên gọi giữ** và **tham chiếu do accessor trả về**.

| Thành phần trong record | Trường `final` ngăn điều gì? | Dữ liệu có thể đổi sau khi tạo? |
| --- | --- | --- |
| `int count` | Không gán lại giá trị số | Không, giá trị nguyên thủy được lưu trực tiếp |
| `String name` | Không gán lại tham chiếu chuỗi | Bản thân `String` là bất biến |
| `LocalDate date` | Không gán lại tham chiếu ngày | `LocalDate` là kiểu bất biến |
| `List<String> names` | Không gán lại tham chiếu danh sách | Có, nếu danh sách đang được giữ là loại có thể sửa |
| `Map<String, String> settings` | Không gán lại tham chiếu bản đồ | Có, nếu map đang được giữ có thể sửa |
| `byte[] bytes` | Không gán lại tham chiếu mảng | Có, phần tử mảng có thể bị gán lại |
| `List<MutableItem> items` | Không gán lại tham chiếu danh sách | Có, cả cấu trúc danh sách và trạng thái từng phần tử có thể bị sửa |

**Bất biến nông (shallow immutability)** nghĩa là các thành phần trực tiếp được giữ cố định ở mức tham chiếu hoặc giá trị. **Bất biến sâu (deep immutability)** đòi hỏi không có đường nào cho bên ngoài thay đổi phần trạng thái quan sát được của đối tượng, kể cả những đối tượng con nhiều tầng.

Một record chỉ có `String`, `int`, `BigDecimal`, `LocalDate` hoặc các giá trị thật sự bất biến thường đã đủ tốt. Với collection và mảng, cần xem xét ranh giới sở hữu dữ liệu.

## 2. Hai đường rò rỉ trạng thái cần ngăn

Sao chép phòng vệ giải quyết hai tình huống độc lập.

### 2.1. Rò rỉ khi **nhận vào** constructor

~~~java
List<String> input = new ArrayList<>(List.of("An"));
Team team = new Team("Core", input);

input.add("Bình"); // Nếu Team giữ nguyên tham chiếu, record thay đổi theo.
~~~

Nếu constructor chỉ gán `members = input`, bên gọi vẫn sở hữu một tham chiếu tới đối tượng có thể sửa. Dù accessor sau đó không cho chỉnh sửa trực tiếp, bên gọi vẫn có thể thay đổi qua `input`.

### 2.2. Rò rỉ khi **trả ra** accessor

~~~java
List<String> values = team.members();
values.clear(); // Nếu accessor trả về danh sách mutable bên trong, record bị sửa.
~~~

Nếu constructor có tạo `new ArrayList<>(input)` nhưng accessor trả danh sách bên trong như mặc định, người nhận vẫn có thể làm thay đổi record.

Vì thế, muốn record giữ snapshot ổn định cần xử lý **cả đường vào và đường ra**:

- **Khi nhận:** lấy bản sao không phụ thuộc cấu trúc collection ngoài.
- **Khi trả:** không cung cấp cho bên ngoài tham chiếu có thể sửa trạng thái bên trong.

Với collection chỉ chứa phần tử bất biến, một cách ngắn gọn là lưu `List.copyOf(input)`: danh sách kết quả không cho phép thao tác thay đổi cấu trúc, nên accessor mặc định trả danh sách ấy là an toàn về mặt cấu trúc.

Với **mảng**, không có mảng Java bất biến: phải sao chép lúc nhận **và** khi trả.

## 3. Dùng compact constructor và `List.copyOf`

Ví dụ xây dựng một record lưu tên nhóm và danh sách thành viên. Ta muốn sau khi tạo:

1. Danh sách không đổi khi người gọi tiếp tục sửa danh sách gốc.
2. Người gọi không thể `add`/`remove` thông qua `team.members()`.
3. Tên nhóm không rỗng; danh sách không có `null`.

**File `Team.java`:**

~~~java
import java.util.List;
import java.util.Objects;

public record Team(String name, List<String> members) {

    public Team {
        Objects.requireNonNull(name, "name");
        if (name.isBlank()) {
            throw new IllegalArgumentException("Tên nhóm không được trống");
        }

        members = List.copyOf(Objects.requireNonNull(members, "members"));
    }
}
~~~

Đây là **compact canonical constructor**: tên constructor `Team` không có danh sách tham số tường minh. Java ngầm tạo các tham số `name`, `members` từ record header. Lệnh:

~~~java
members = List.copyOf(members);
~~~

gán lại **tham số constructor** bằng bản sao được bảo vệ. Khi compact constructor kết thúc thành công, compiler tự gán giá trị cuối cùng của tham số vào trường thành phần tương ứng. Không cần và cũng không được viết `this.members = ...` trong thân compact constructor.

**File `TeamDemo.java`:**

~~~java
import java.util.ArrayList;
import java.util.List;

public class TeamDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("An", "Bình"));
        Team team = new Team("Core", source);

        source.add("Chi"); // Chỉ sửa danh sách nguồn.
        System.out.println(team.members()); // [An, Bình]

        try {
            team.members().add("Dũng");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Không thể sửa danh sách trong record");
        }

        System.out.println(team.members()); // [An, Bình]
    }
}
~~~

Lệnh chạy trực tiếp với JDK 17 khi hai file nằm cùng thư mục:

~~~bash
javac --release 17 -encoding UTF-8 Team.java TeamDemo.java
java TeamDemo
~~~

Đầu ra mong đợi:

~~~text
[An, Bình]
Không thể sửa danh sách trong record
[An, Bình]
~~~

Ở đây **không cần tự viết lại accessor `members()`** vì tham chiếu mà record lưu đã trỏ tới danh sách không thể sửa. Điều kiện quan trọng là các phần tử `String` cũng bất biến.

### `List.copyOf` thực hiện điều gì?

`List.copyOf(collection)` (có từ Java 10 và dùng bình thường trong Java 17) tạo danh sách không thể chỉnh sửa với các phần tử theo thứ tự của collection đầu vào.

- Các thao tác thay đổi như `add`, `set`, `remove` và `clear` không được hỗ trợ.
- `null` không được chấp nhận: `null` collection hoặc phần tử `null` dẫn đến `NullPointerException`.
- Nếu đầu vào là một danh sách đã bất biến phù hợp, triển khai có thể tái sử dụng đối tượng thay vì cấp phát bản sao mới; không nên dựa vào **identity** của hai danh sách.
- Chỉ **sao chép cấu trúc collection**, không tự sao chép sâu từng phần tử.

Trong trường hợp danh sách thành viên cho phép rỗng, không phải thêm validation. Nếu nghiệp vụ yêu cầu ít nhất một thành viên, có thể kiểm tra `members.isEmpty()` sau khi gọi `List.copyOf`.

## 4. Phân biệt bản sao và lớp vỏ chỉ đọc

Ba cách xử lý collection dưới đây có hành vi khác nhau:

~~~java
List<String> source = new ArrayList<>(List.of("A"));

List<String> view = java.util.Collections.unmodifiableList(source);

List<String> mutableCopy = new ArrayList<>(source);

List<String> snapshot = List.copyOf(source);

source.add("B");

System.out.println(view);        // [A, B]
System.out.println(mutableCopy); // [A]
System.out.println(snapshot);    // [A]
~~~

| Cách tạo | Còn thấy các lần sửa cấu trúc `source` sau đó? | Bên nhận có thể tự sửa kết quả? |
| --- | --- | --- |
| `Collections.unmodifiableList(source)` | **Có**, vì chỉ là view của danh sách nguồn | Không sửa **qua view**, nhưng nguồn vẫn sửa được |
| `new ArrayList<>(source)` | Không, với thay đổi cấu trúc nguồn sau thời điểm copy | **Có** |
| `Collections.unmodifiableList(new ArrayList<>(source))` | Không, với thay đổi cấu trúc nguồn sau thời điểm copy | Không qua wrapper |
| `List.copyOf(source)` | Không, với thay đổi cấu trúc nguồn sau thời điểm copy | Không |

`Collections.unmodifiableList` **không đồng nghĩa với sao chép**. Nó tạo một lớp nhìn chỉ đọc nhưng có thể phản ánh thay đổi ở collection nằm phía sau. Với Java 17, `List.copyOf` thường là lựa chọn gọn nhất để lưu một snapshot collection có phần tử bất biến.

Tương tự, `Set.copyOf` và `Map.copyOf` cho phép tạo collection không thể sửa:

~~~java
Set<String> tags = Set.copyOf(inputTags);
Map<String, String> options = Map.copyOf(inputOptions);
~~~

Một số hành vi cần lưu ý:

- `Set.copyOf` và `Map.copyOf` không bảo đảm thứ tự duyệt như một danh sách; đừng phụ thuộc vào thứ tự in khi hiển thị dữ liệu hoặc so sánh snapshot.
- `Map.copyOf` không chấp nhận key hoặc value `null`; `Set.copyOf` không chấp nhận phần tử `null`.
- `Set.copyOf` loại bỏ các phần tử trùng theo phép bằng nhau; nếu các đối tượng đầu vào khác tham chiếu nhưng `equals` nhau, không nên phụ thuộc phần tử đại diện được giữ lại.
- Bất biến cấu trúc collection **không** có nghĩa là phần tử trong đó đã bất biến.

## 5. Giới hạn quan trọng: `List.copyOf` vẫn chỉ sao chép nông

Giả sử phần tử danh sách là một đối tượng có setter:

~~~java
import java.util.ArrayList;
import java.util.List;

final class MutableAddress {
    private String city;

    MutableAddress(String city) {
        this.city = city;
    }

    String city() {
        return city;
    }

    void changeCity(String city) {
        this.city = city;
    }
}

record Route(List<MutableAddress> stops) {
    Route {
        stops = List.copyOf(stops);
    }
}

class RouteDemo {
    public static void main(String[] args) {
        MutableAddress first = new MutableAddress("Hà Nội");
        List<MutableAddress> addresses =
                new ArrayList<>(List.of(first));

        Route route = new Route(addresses);
        first.changeCity("Đà Nẵng");

        System.out.println(route.stops().get(0).city()); // Đà Nẵng
    }
}
~~~

Mặc dù `Route` dùng `List.copyOf`, danh sách mới vẫn chứa **tham chiếu tới cùng `MutableAddress`**. Vì thế sửa đối tượng `first` ở ngoài làm thay đổi trạng thái quan sát được từ record.

Nhìn theo sơ đồ:

~~~text
Danh sách gốc ────────┐
                     ├──> MutableAddress { city = "Đà Nẵng" }
Danh sách copyOf ─────┘
       ^
       |
     Route.stops
~~~

Thứ được copy là **danh sách tham chiếu**, không phải toàn bộ đồ thị đối tượng.

### Cách 1: ưu tiên các phần tử bất biến

Nếu miền nghiệp vụ cho phép, thiết kế `Address` thành record với các component bất biến:

~~~java
import java.util.List;
import java.util.Objects;

record Address(String city) {
    Address {
        Objects.requireNonNull(city, "city");
        if (city.isBlank()) {
            throw new IllegalArgumentException("Tên thành phố không được trống");
        }
    }
}

record Route(List<Address> stops) {
    Route {
        stops = List.copyOf(Objects.requireNonNull(stops, "stops"));
    }
}
~~~

`Address` chỉ chứa `String` bất biến. `Route` có snapshot cấu trúc danh sách chứa các đối tượng `Address` cũng bất biến. Đây là mô hình **bất biến theo chiều sâu** đối với phần dữ liệu `stops` trong ví dụ.

Ưu điểm của cách này là không cần tự viết clone từng thành phần, ít nguy cơ làm sai `equals`/`hashCode` và dễ sử dụng trong nhiều luồng xử lý.

### Cách 2: tạo snapshot độc lập cho từng phần tử mutable

Nếu phải nhận một đối tượng mutable của một API khác, hãy **chuyển đổi sang giá trị bất biến** trước khi lưu:

~~~java
record AddressSnapshot(String city) {
}

record RouteSnapshot(List<AddressSnapshot> stops) {
    RouteSnapshot {
        stops = stops.stream()
                .map(address -> new AddressSnapshot(address.city()))
                .toList();
    }
}
~~~

`Stream.toList()` có từ Java 16, trả về danh sách không thể sửa. Trong ví dụ này, từng `MutableAddress` được chuyển thành `AddressSnapshot` mới trước khi tạo danh sách, và `String` lưu trong snapshot là bất biến.

Đoạn này giả định danh sách và các phần tử đầu vào không `null`, đồng thời đối tượng `MutableAddress` không bị luồng khác sửa ngay trong lúc chụp snapshot. Nếu API công khai cần thông báo lỗi rõ ràng, hãy bổ sung kiểm tra null và đồng bộ tại ranh giới lấy dữ liệu.

### Sao chép sâu không nhất thiết đồng nghĩa gọi `clone()`

Sao chép sâu là sao chép **đủ các phần mutable cần độc lập** trong cấu trúc đối tượng. Không có cơ chế chung tự động bảo đảm mọi reference đều được clone chính xác. `Object.clone()` thường chỉ thực hiện sao chép nông theo mặc định; nhiều lớp không hỗ trợ clone. Trong Java 17, constructor chuyển đổi sang **immutable value**, copy constructor hoặc factory snapshot thường diễn đạt ý định tốt hơn.

## 6. Collection lồng nhau: sao chép từng tầng mutable

Một record có thể chứa map của các danh sách:

~~~java
record Permissions(Map<String, List<String>> rolesByUser) {
}
~~~

Nếu chỉ làm:

~~~java
rolesByUser = Map.copyOf(rolesByUser);
~~~

thì **map bên ngoài** không thể thêm/xóa key thông qua record, nhưng các danh sách là **giá trị của map** vẫn có thể mutable.

Cách giữ snapshot độc lập của cả map và từng danh sách:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public record Permissions(Map<String, List<String>> rolesByUser) {

    public Permissions {
        Objects.requireNonNull(rolesByUser, "rolesByUser");

        Map<String, List<String>> snapshot = new HashMap<>();

        for (Map.Entry<String, List<String>> entry : rolesByUser.entrySet()) {
            String user = Objects.requireNonNull(entry.getKey(), "user");
            List<String> roles = List.copyOf(
                    Objects.requireNonNull(entry.getValue(), "roles"));
            snapshot.put(user, roles);
        }

        rolesByUser = Map.copyOf(snapshot);
    }
}
~~~

Ví dụ dùng record:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

class PermissionDemo {
    public static void main(String[] args) {
        List<String> roles = new ArrayList<>(List.of("READ"));
        Map<String, List<String>> source = new HashMap<>();
        source.put("an", roles);

        Permissions permissions = new Permissions(source);

        roles.add("WRITE");
        source.put("binh", new ArrayList<>(List.of("ADMIN")));

        System.out.println(permissions.rolesByUser());
        // {an=[READ]}
    }
}
~~~

Bất biến ở đây đạt được nhờ:

- `Map.copyOf` ngăn thay đổi cấu trúc map bên ngoài và tách map khỏi nguồn.
- `List.copyOf` tạo danh sách mới cho **mỗi value**, ngăn thay đổi cấu trúc danh sách con.
- Key và phần tử đều là `String` bất biến.

Nếu các phần tử ở danh sách con là class mutable, cần tiếp tục copy/chuyển đổi từng phần tử như mục trước. Nếu cần giữ **thứ tự duyệt theo lúc nhập**, cân nhắc `LinkedHashMap` và một bản sao có wrapper chỉ đọc thích hợp; `Map.copyOf` không cam kết duy trì thứ tự duyệt.

### Lưu ý về generic

Kiểu `Map<String, List<String>>` chỉ cho biết kiểu phần tử; không bảo đảm implementation của mỗi danh sách là bất biến. Generic type không thay thế kiểm tra ownership hay sao chép phòng vệ.

## 7. Mảng trong record: phải copy cả đầu vào và đầu ra

Mảng Java luôn cho phép ghi vào phần tử, kể cả khi tham chiếu được khai báo `final`. Record sau rất dễ bị thay đổi:

~~~java
record RawPacket(byte[] data) {
}

byte[] input = {1, 2, 3};
RawPacket packet = new RawPacket(input);

input[0] = 9;          // Thay đổi từ ngoài constructor.
packet.data()[1] = 8; // Thay đổi qua accessor.
~~~

Nếu chỉ sửa constructor:

~~~java
record HalfSafePacket(byte[] data) {
    HalfSafePacket {
        data = data.clone();
    }
}
~~~

thì người gọi không sửa được qua `input` ban đầu, **nhưng vẫn sửa được qua `packet.data()`** vì accessor mặc định trả đúng mảng bên trong.

### 7.1. Sao chép hai chiều

~~~java
import java.util.Arrays;
import java.util.Objects;

public record BytePacket(byte[] bytes) {

    public BytePacket {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BytePacket that
                && Arrays.equals(this.bytes, that.bytes);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(bytes);
    }

    @Override
    public String toString() {
        return "BytePacket[length=" + bytes.length + "]";
    }
}
~~~

Ở đây:

1. Compact constructor clone mảng để tách khỏi `byte[]` bên gọi giữ.
2. Accessor `bytes()` clone lần nữa để không lộ mảng đang lưu.
3. `equals()` và `hashCode()` được viết lại để so sánh **nội dung mảng** theo `Arrays.equals`/`Arrays.hashCode`.
4. `toString()` được viết lại để thể hiện thông tin hữu ích là chiều dài, không phụ thuộc cách biểu diễn tham chiếu mảng mặc định.

Ví dụ sử dụng:

~~~java
import java.util.Arrays;

class BytePacketDemo {
    public static void main(String[] args) {
        byte[] input = {1, 2, 3};
        BytePacket packet = new BytePacket(input);

        input[0] = 9;

        byte[] readBack = packet.bytes();
        readBack[1] = 8;

        System.out.println(Arrays.toString(packet.bytes()));
        // [1, 2, 3]

        System.out.println(
                packet.equals(new BytePacket(new byte[] {1, 2, 3})));
        // true
    }
}
~~~

### 7.2. Vì sao phải chú ý `equals` và `hashCode` của mảng?

Với record chứa `byte[]` mà không override, các phương thức `equals`/`hashCode` sinh tự động xử lý thành phần mảng theo **định danh đối tượng mảng**, chứ không thực hiện so sánh nội dung bằng `Arrays.equals`.

~~~java
record Bytes(byte[] data) {
}

Bytes a = new Bytes(new byte[] {1, 2});
Bytes b = new Bytes(new byte[] {1, 2});

System.out.println(a.equals(b)); // false: hai mảng khác tham chiếu
~~~

Vì thế, nếu record biểu diễn **giá trị byte theo nội dung**, nên cân nhắc một trong hai hướng:

- Tự triển khai `equals`, `hashCode` và accessor có copy phù hợp như `BytePacket`.
- Chuyển dữ liệu sang một kiểu bất biến có ngữ nghĩa bằng nhau theo giá trị và có API phù hợp. Không nên tự động đổi sang `List<Byte>` khi hiệu năng/bộ nhớ của dữ liệu nhị phân quan trọng, vì boxing có chi phí riêng.

Với **mảng hai chiều** hoặc mảng chứa các đối tượng mutable, `array.clone()` chỉ copy mảng ở tầng ngoài. Cần clone từng mảng con hoặc chuyển mỗi phần tử thành immutable value; đồng thời cân nhắc `Arrays.deepEquals`/`Arrays.deepHashCode` nếu cấu trúc mang ngữ nghĩa bằng nhau theo nội dung.

## 8. Bất biến giúp `equals()`, `hashCode()` và cache đáng tin hơn

Record tự sinh `equals` và `hashCode` dựa vào các thành phần. Nếu thành phần mutable thay đổi sau khi record được đưa vào `HashMap`/`HashSet`, giá trị hash có thể đổi làm việc tra cứu không còn đúng kỳ vọng.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

record MutableKey(List<String> tags) {
}

class KeyDemo {
    public static void main(String[] args) {
        List<String> tags = new ArrayList<>(List.of("A"));
        MutableKey key = new MutableKey(tags);

        Set<MutableKey> keys = new HashSet<>();
        keys.add(key);

        tags.add("B"); // Record key đã đổi hashCode vì List thay đổi.
        System.out.println(keys.contains(key)); // Có thể false.
    }
}
~~~

`HashSet` chọn bucket khi thêm phần tử, dựa trên hash của phần tử ở thời điểm đó. Nếu hash thay đổi sau khi được thêm, tìm kiếm có thể không còn trùng vị trí đã lưu. Đây không phải lỗi riêng của record, nhưng cú pháp record ngắn gọn dễ khiến người đọc tưởng rằng một đối tượng đã là value object an toàn.

Thay bằng:

~~~java
import java.util.List;

record StableKey(List<String> tags) {
    StableKey {
        tags = List.copyOf(tags);
    }
}
~~~

Nếu phần tử là `String` bất biến, `StableKey` có hash ổn định. Đây là đặc tính quan trọng khi dùng record làm key trong cache, map, tập hợp hoặc đối tượng giá trị trong mô hình miền.

Không nên chọn việc override `hashCode()` để **che đi** trạng thái mutable mà vẫn dùng `equals()` dựa trên trạng thái đó; hai phương thức phải tiếp tục tuân thủ hợp đồng nhất quán. Cách thiết kế tốt hơn là ngăn trạng thái dùng để xác định giá trị bị thay đổi.

## 9. Ví dụ miền nghiệp vụ: đơn hàng có danh sách dòng hàng ổn định

Đối tượng đơn hàng cần có mã đơn và nhiều dòng hàng. Nếu mỗi dòng hàng cũng bất biến, chỉ cần copy cấu trúc danh sách.

**File `LineItem.java`:**

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record LineItem(String sku, int quantity, BigDecimal unitPrice) {

    public LineItem {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank()) {
            throw new IllegalArgumentException("SKU không được trống");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Đơn giá không được âm");
        }
    }

    public BigDecimal amount() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

`String` và `BigDecimal` đều bất biến. `quantity` là primitive. Vì thế mỗi `LineItem` được tạo thành công có trạng thái cố định.

**File `Order.java`:**

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public record Order(String orderId, List<LineItem> items) {

    public Order {
        Objects.requireNonNull(orderId, "orderId");
        if (orderId.isBlank()) {
            throw new IllegalArgumentException("Mã đơn không được trống");
        }

        items = List.copyOf(Objects.requireNonNull(items, "items"));
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Đơn hàng phải có dòng hàng");
        }
    }

    public BigDecimal total() {
        return items.stream()
                .map(LineItem::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
~~~

**File `OrderDemo.java`:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

public class OrderDemo {
    public static void main(String[] args) {
        List<LineItem> input = new ArrayList<>();
        input.add(new LineItem("BOOK-01", 2, new BigDecimal("125.50")));
        input.add(new LineItem("PEN-02", 3, new BigDecimal("10.00")));

        Order order = new Order("ORD-17", input);
        input.clear(); // Không làm mất dòng hàng của order.

        System.out.println(order.items().size()); // 2
        System.out.println(order.total());        // 281.00
    }
}
~~~

Chạy trong cùng thư mục chứa ba file:

~~~bash
javac --release 17 -encoding UTF-8 LineItem.java Order.java OrderDemo.java
java OrderDemo
~~~

Kết quả mong đợi:

~~~text
2
281.00
~~~

Trong thiết kế này, `Order` giữ snapshot của danh sách, còn từng `LineItem` giữ thành phần bất biến. Đây là cách sử dụng record phù hợp cho mô hình dữ liệu cần ý nghĩa theo giá trị, miễn là dữ liệu ban đầu được tạo hợp lệ.

## 10. Những API bất biến nên ưu tiên trong Java 17

Việc chọn **kiểu thành phần** quan trọng không kém việc copy. Khi có lựa chọn giữa một kiểu mutable và một kiểu bất biến biểu diễn cùng ý nghĩa, ưu tiên kiểu bất biến để giảm lượng code sao chép.

| Nhu cầu | Kiểu thường phù hợp | Lý do |
| --- | --- | --- |
| Văn bản | `String` | Bất biến |
| Số nguyên, số thực nguyên thủy | `int`, `long`, `double` | Lưu trực tiếp giá trị |
| Số thập phân chính xác | `BigDecimal` | Bất biến; phù hợp số tiền nếu quy tắc làm tròn được định nghĩa |
| Ngày theo lịch | `LocalDate` | Bất biến |
| Thời điểm tuyệt đối | `Instant` | Bất biến |
| Khoảng thời gian | `Duration` | Bất biến |
| Định danh | `UUID` | Bất biến |
| Tập giá trị đơn giản | `List.copyOf`, `Set.copyOf` | Container không thể sửa; cần phần tử bất biến |
| Ánh xạ cấu hình | `Map.copyOf` | Container không thể sửa; cần key/value bất biến |
| Dữ liệu nhị phân | `byte[]` có clone hai chiều hoặc immutable binary value | Mảng không tự bất biến |

Ví dụ dùng `Instant` thay vì lưu một đối tượng ngày giờ mutable:

~~~java
import java.time.Instant;
import java.util.Objects;

record AuditEvent(String action, Instant occurredAt) {
    AuditEvent {
        Objects.requireNonNull(action, "action");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

Với `Instant`, không cần clone thời điểm ở cả hai chiều. Nếu cần đổi timezone khi hiển thị, dùng các API `java.time` để chuyển biểu diễn mà không sửa `Instant` gốc.

Record có thể chứa đối tượng từ thư viện bên ngoài. Trước khi quyết định có cần copy, cần xem **hợp đồng bất biến của kiểu đó**, không chỉ thấy trường của record là `final`.

## 11. Kiểm thử sao chép phòng vệ

Sao chép phòng vệ cần được kiểm chứng từ hai hướng: sửa đầu vào sau khi khởi tạo và cố sửa đầu ra của accessor.

Ví dụ JUnit Jupiter 5 kiểm tra `Team`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class TeamTest {

    @Test
    void changesToInputDoNotChangeRecord() {
        List<String> source = new ArrayList<>(List.of("An"));
        Team team = new Team("Core", source);

        source.add("Bình");

        assertEquals(List.of("An"), team.members());
    }

    @Test
    void accessorDoesNotAllowStructuralModification() {
        Team team = new Team("Core", List.of("An"));

        assertThrows(
                UnsupportedOperationException.class,
                () -> team.members().add("Bình"));
    }

    @Test
    void equivalentValuesAreEqual() {
        Team first = new Team("Core", new ArrayList<>(List.of("An")));
        Team second = new Team("Core", List.of("An"));

        assertEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode());
    }
}
~~~

Với `BytePacket`, cần kiểm tra cả hai hướng mảng:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class BytePacketTest {

    @Test
    void copiesInputAndOutputArrays() {
        byte[] source = {1, 2, 3};
        BytePacket packet = new BytePacket(source);

        source[0] = 9;

        byte[] returned = packet.bytes();
        returned[1] = 8;

        assertArrayEquals(new byte[] {1, 2, 3}, packet.bytes());
        assertEquals(
                new BytePacket(new byte[] {1, 2, 3}),
                packet);
    }
}
~~~

Với collection lồng nhau hoặc có mutable element, cũng nên kiểm tra trường hợp thay đổi **phần tử con** sau khi khởi tạo; chỉ test `add`/`remove` trên danh sách bên ngoài không đủ để phát hiện rò rỉ sâu.

Các test này mô tả hợp đồng của API. Nếu dự án sử dụng Maven hoặc Gradle, cần cấu hình JUnit tương ứng và đặt test theo thư mục nguồn kiểm thử đã chọn; không nên phụ thuộc vào việc chạy test riêng lẻ từ một IDE.

## 12. Những giới hạn và đánh đổi cần biết

### 12.1. Sao chép có chi phí

`List.copyOf` cần duyệt phần tử khi tạo snapshot của collection mutable; clone mảng cần sao chép bytes; copy đối tượng lồng nhau có thể tốn thêm CPU và bộ nhớ. Với dữ liệu lớn, hãy xác định **ai sở hữu dữ liệu và lúc nào cần snapshot** thay vì sao chép lặp lại không cần thiết.

Nếu dữ liệu thực sự được sở hữu độc quyền bởi một tầng và không bao giờ lộ tham chiếu mutable ra ngoài, có thể không cần copy ở mọi điểm nội bộ. Nhưng API công khai nhận collection mutable từ bên ngoài nên có hợp đồng ownership rõ ràng để tránh phụ thuộc ngầm.

### 12.2. Snapshot không đồng nghĩa an toàn luồng tuyệt đối

`List.copyOf` tạo một snapshot cấu trúc collection ở thời điểm sao chép; **không** làm cho quá trình đọc đầu vào trở thành thao tác nguyên tử nếu một luồng khác đang sửa collection trong lúc copy. Tương tự, nếu các phần tử mutable bị cập nhật đồng thời, dữ liệu chụp được có thể không nhất quán.

Khi chia sẻ record giữa các luồng:

- Chỉ công bố record sau khi đã xây dựng thành công.
- Bảo đảm các phần tử tham chiếu bên trong cũng bất biến hoặc được kiểm soát đồng bộ.
- Nếu snapshot từ một cấu trúc đang được cập nhật đồng thời, tổ chức cơ chế đọc nhất quán phù hợp trước khi chụp.

Trường `final` của record hỗ trợ ngữ nghĩa khởi tạo an toàn của Java, nhưng không xóa bỏ data race phát sinh từ trạng thái mutable mà record tham chiếu.

### 12.3. Collection không cho sửa khác với dữ liệu bất biến sâu

`List.copyOf`, `Map.copyOf` và `Stream.toList` tạo container không thể sửa. Tuy vậy, chúng không cam kết các đối tượng bên trong bất biến. Thuật ngữ **unmodifiable** nói về hành vi sửa thông qua API collection; **deep immutable** nói về toàn bộ trạng thái có thể quan sát xuyên qua các reference.

### 12.4. Một bản sao “sâu” cần định nghĩa theo miền nghiệp vụ

Không phải cứ clone mọi object là tốt. Nếu cây đối tượng có chu kỳ, chia sẻ tham chiếu cố ý, kết nối ngoài hoặc tài nguyên không thể clone, sao chép toàn bộ có thể sai ngữ nghĩa. Hãy thiết kế snapshot gồm đúng những giá trị mà bên nhận cần giữ ổn định, chẳng hạn `AddressSnapshot(city)` thay vì giữ cả đối tượng địa chỉ mutable có nhiều hành vi.

### 12.5. Cân nhắc khi serialize, cache hoặc logging

Record thường được dùng cho request/response và cache. Dù framework ánh xạ thành phần thuận tiện, việc deserialize có thể tạo dữ liệu có collection mutable hoặc giá trị thiếu hợp lệ nếu đường tạo đối tượng không tuân hợp đồng kỳ vọng. Đặt validation và copy trong constructor/factory giúp giữ một nơi kiểm soát bất biến.

Một record chứa mảng hoặc giá trị nhạy cảm có thể cần custom `toString()` để tránh đưa dữ liệu không nên log ra ngoài. Chỉ định rõ những trường nào có thể hiển thị khi thiết kế API và telemetry.

## 13. Bài tập thực hành

**Bài 1 — Danh sách tên:** Tạo `record Course(String title, List<String> students)`. Dùng compact constructor kiểm tra tiêu đề và `List.copyOf`. Viết thử nghiệm sửa danh sách nguồn sau khi tạo và sửa qua accessor; ghi lại hai kết quả.

**Bài 2 — Danh sách đối tượng mutable:** Tạo một lớp `MutableScore` có setter `setValue(...)`, sau đó tạo `record Scores(List<MutableScore> values)`. Quan sát vì sao `List.copyOf` không ngăn score thay đổi. Chuyển dữ liệu sang `record ScoreSnapshot(int value)` rồi kiểm chứng trạng thái ổn định.

**Bài 3 — Mảng byte:** Tạo `record DocumentBytes(byte[] content)`. Viết compact constructor clone đầu vào, accessor clone đầu ra, `equals`/`hashCode` theo `Arrays`. Cho hai mảng khác tham chiếu nhưng cùng nội dung và kiểm tra hành vi bằng nhau.

**Bài 4 — Map lồng nhau:** Tạo `record FeatureFlags(Map<String, List<String>> enabledByTeam)`. Cho phép các key và danh sách giá trị không `null`. Sao chép từng danh sách rồi tạo map không thể sửa; thử thay đổi cả map và danh sách đầu vào.

**Bài 5 — Khóa trong `HashSet`:** Dùng record có `List<String>` mutable làm key và quan sát kết quả khi sửa danh sách; sau đó thay bằng record có `List.copyOf` và so sánh hành vi.

**Kết luận:** `record` trong Java 17 bảo đảm các **trường thành phần** không được gán lại sau khi tạo, nhưng không tự bảo đảm trạng thái của những đối tượng được tham chiếu. Để thiết kế một value object ổn định, cần chọn thành phần bất biến khi có thể, snapshot dữ liệu mutable khi nhận, không để lộ tham chiếu mutable khi trả và cân nhắc sao chép sâu ở những tầng thực sự cần thiết.
