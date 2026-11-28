# Field private final và giới hạn bất biến nông của record

## 1. Record có field final, nhưng điều đó bảo đảm điều gì?

Từ Java 16, `record` là tính năng chính thức để khai báo lớp mang dữ liệu với các component được mô tả ngay trong header. Mỗi component tương ứng với một field instance có hai đặc điểm: `private` và `final`.

Ví dụ:

```java
record Student(String name, int completedLessons) {}
```

Từ header trên, Java tạo các field tương ứng về mặt ngữ nghĩa:

- `private final String name`
- `private final int completedLessons`

Mã bên ngoài không thể truy cập trực tiếp field vì chúng là `private`. Sau khi constructor khởi tạo xong, không thể gán lại field component vì chúng là `final`. Ta đọc dữ liệu thông qua accessor `name()` và `completedLessons()`.

Tuy nhiên, cần phân biệt hai việc:

1. **Không thể thay thế tham chiếu được lưu trong field:** không thể gán một object khác vào field component sau khi record được tạo.
2. **Không thể thay đổi object mà field đang tham chiếu:** điều này không được bảo đảm chỉ bởi `final`.

Nếu component là một object mutable như `ArrayList`, `HashMap`, mảng hoặc một lớp do ứng dụng tự viết có setter, nội dung object đó vẫn có thể thay đổi. Vì vậy, record mặc định chỉ cung cấp **bất biến nông** (*shallow immutability*).

Mục tiêu bài học:

- Hiểu ý nghĩa của field component `private final`.
- Phân biệt gán lại tham chiếu với thay đổi trạng thái của object được tham chiếu.
- Nhận diện bất biến nông và bất biến sâu.
- Bảo vệ collection, mảng và object lồng nhau bằng sao chép phòng vệ.
- Hiểu tác động của component mutable lên `equals()`, `hashCode()` và việc dùng record làm khóa.
- Thiết kế record giữ snapshot dữ liệu ổn định trong ứng dụng Java hiện đại.

## 2. Gán lại tham chiếu và thay đổi object là hai thao tác khác nhau

Xét record có component là một danh sách:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {}

List<String> source = new ArrayList<>(List.of("An", "Binh"));
Team team = new Team(source);
```

Field `members` bên trong `team` là `final`. Điều này ngăn việc gán một danh sách khác vào field sau khi constructor kết thúc. Nhưng danh sách ban đầu vẫn là `ArrayList` có thể thay đổi.

```java
source.add("Chi");
System.out.println(team.members()); // [An, Binh, Chi]

team.members().add("Dung");
System.out.println(source);         // [An, Binh, Chi, Dung]
```

Hai biểu thức trên thay đổi **cùng một object danh sách**. Không biểu thức nào gán lại field `members`. Do đó chúng không vi phạm tính `final` của field.

Có thể hình dung:

```text
team.members ─────┐
                  ├──> ArrayList có thể thay đổi
source ───────────┘
```

Field của record giữ cố định tham chiếu đến danh sách, nhưng danh sách vẫn giữ trạng thái mutable. Đây là giới hạn quan trọng nhất cần nhớ khi đưa collection hoặc object mutable vào record.

### So sánh với component primitive và String

```java
record Measurement(int value) {}
record PersonName(String value) {}
```

- `int` là primitive; không có object mutable được tham chiếu.
- `String` là kiểu bất biến; các thao tác chuỗi tạo ra giá trị String khác thay vì sửa nội dung object hiện tại.
- `List`, `Map`, mảng và nhiều kiểu do ứng dụng định nghĩa có thể mutable; phải xem hợp đồng của kiểu cụ thể.

Vì vậy, record chứa toàn primitive và các kiểu bất biến thường dễ đạt tính bất biến sâu hơn record chứa collection hay object mutable.

## 3. Bất biến nông và bất biến sâu

**Bất biến nông** có nghĩa các field component không thể được gán lại, nhưng trạng thái của object được tham chiếu có thể thay đổi.

**Bất biến sâu** có nghĩa trạng thái có thể quan sát từ object và toàn bộ các object mà nó sở hữu hoặc công khai tham chiếu không thể bị thay đổi ngoài ý muốn sau khi khởi tạo. Để đạt điều đó, cần phối hợp kiểu dữ liệu bất biến, sao chép phòng vệ và giới hạn việc làm lộ tham chiếu mutable.

| Đặc điểm | Bất biến nông | Bất biến sâu |
| --- | --- | --- |
| Field component | Không thể gán lại. | Không thể gán lại. |
| Component primitive | Không đổi sau khởi tạo. | Không đổi sau khởi tạo. |
| Component kiểu bất biến như String | Giá trị không đổi. | Giá trị không đổi. |
| Component collection mutable | Có thể bị sửa qua tham chiếu. | Cấu trúc được bảo vệ; phần tử cũng cần bất biến hoặc được sao chép sâu. |
| Component mảng | Nội dung có thể bị sửa qua tham chiếu. | Cần bảo vệ mảng đầu vào, đầu ra và các phần tử nếu là object mutable. |
| Object lồng nhau | Có thể đổi trạng thái bên trong. | Cần bất biến hoặc bản sao phòng vệ đệ quy theo cấu trúc dữ liệu. |

Một record không tự động trở thành deep immutable chỉ vì các field component là `final`. Muốn bảo đảm sâu, phải xem xét toàn bộ đường truy cập đến dữ liệu mutable, gồm cả constructor và accessor.

## 4. Sao chép phòng vệ collection trong constructor

Với component collection, một cách phổ biến là tạo bản sao không cho phép sửa cấu trúc trong canonical constructor. Java cung cấp các phương thức như `List.copyOf()`, `Set.copyOf()` và `Map.copyOf()`.

Ví dụ với danh sách:

```java
import java.util.List;
import java.util.Objects;

record CourseSnapshot(String code, List<String> topics) {
    CourseSnapshot {
        code = Objects.requireNonNull(code, "code").strip();
        topics = List.copyOf(Objects.requireNonNull(topics, "topics"));
    }
}
```

`List.copyOf()` tạo một danh sách không cho phép sửa đổi cấu trúc, chứa các phần tử của collection đầu vào tại thời điểm tạo bản sao. Khi record được khởi tạo:

- Thay đổi danh sách nguồn sau đó không làm thay đổi cấu trúc danh sách trong record.
- Người gọi không thể thêm hoặc xóa phần tử thông qua accessor `topics()`.
- `List.copyOf()` từ chối collection `null` và phần tử `null`.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

List<String> input = new ArrayList<>(List.of("record", "stream"));
CourseSnapshot snapshot = new CourseSnapshot("JAVA-16", input);

input.add("external-change");
System.out.println(snapshot.topics()); // [record, stream]
```

Gọi phương thức sửa danh sách trả về cũng bị từ chối:

```java
snapshot.topics().add("new-topic");
// UnsupportedOperationException
```

### Sao chép cấu trúc không đồng nghĩa sao chép sâu

`List.copyOf()` bảo vệ cấu trúc danh sách, nhưng **không sao chép từng phần tử**. Nếu phần tử là object mutable, người gọi vẫn có thể thay đổi object đó.

```java
import java.util.List;

record TopicLabels(List<StringBuilder> labels) {
    TopicLabels {
        labels = List.copyOf(labels);
    }
}

StringBuilder label = new StringBuilder("Java");
TopicLabels topics = new TopicLabels(List.of(label));

topics.labels().get(0).append(" 16");
System.out.println(topics.labels().get(0)); // Java 16
```

Danh sách không cho phép thêm hoặc xóa phần tử, nhưng `StringBuilder` bên trong vẫn mutable. Vì thế, chỉ dùng `List.copyOf()` là chưa đủ nếu yêu cầu của ứng dụng là bất biến sâu.

Nếu phần tử là record hoặc kiểu bất biến, chẳng hạn `String`, việc sao chép cấu trúc thường đã đáp ứng mục tiêu snapshot. Nếu phần tử mutable, cần sao chép từng phần tử hoặc chuyển chúng thành kiểu giá trị bất biến.

### Phân biệt List.copyOf và Collections.unmodifiableList

`Collections.unmodifiableList(list)` tạo một view không cho sửa thông qua view đó, nhưng view vẫn phản ánh thay đổi trên danh sách nền. Nếu danh sách nền còn được giữ ở nơi khác, nó vẫn có thể thay đổi.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

List<String> source = new ArrayList<>(List.of("java"));
List<String> view = Collections.unmodifiableList(source);

source.add("record");
System.out.println(view); // [java, record]
```

Nếu cần dùng view không sửa đổi trên một bản sao độc lập, phải sao chép trước rồi mới tạo view. Với mục đích tạo snapshot collection thông thường, `List.copyOf()` thường rõ ý định hơn.

## 5. Sao chép phòng vệ Map và Set

Cùng nguyên tắc áp dụng cho các collection khác:

```java
import java.util.Map;
import java.util.Objects;
import java.util.Set;

record Configuration(Map<String, String> properties) {
    Configuration {
        properties = Map.copyOf(
            Objects.requireNonNull(properties, "properties")
        );
    }
}

record PermissionSet(Set<String> permissions) {
    PermissionSet {
        permissions = Set.copyOf(
            Objects.requireNonNull(permissions, "permissions")
        );
    }
}
```

Sau khi tạo record:

- Không thể thêm, xóa hoặc thay thế entry trong map qua accessor.
- Không thể thêm hoặc xóa phần tử trong set qua accessor.
- Thay đổi map hoặc set nguồn không làm thay đổi cấu trúc snapshot.
- Các phương thức copy này không cho phép key, value hoặc phần tử `null`.

Như với List, các phương thức copy collection là **shallow copy**. Nếu value trong Map hoặc phần tử trong Set là object mutable, object đó vẫn có thể thay đổi. Cần xem xét kiểu của phần tử, không chỉ kiểu collection bên ngoài.

## 6. Sao chép phòng vệ mảng: đầu vào và đầu ra

Mảng trong Java mutable. Field component dạng mảng là `private final`, nhưng nếu accessor mặc định trả về chính mảng đang lưu, người gọi có thể sửa nội dung của nó.

```java
record Payload(byte[] bytes) {}

byte[] input = {1, 2, 3};
Payload payload = new Payload(input);

input[0] = 9;
System.out.println(payload.bytes()[0]); // 9

payload.bytes()[1] = 8;
System.out.println(payload.bytes()[1]); // 8
```

Để bảo vệ mảng, cần sao chép cả khi nhận dữ liệu và khi trả dữ liệu:

```java
import java.util.Objects;

record PayloadSnapshot(byte[] bytes) {
    PayloadSnapshot {
        bytes = Objects.requireNonNull(bytes, "bytes").clone();
    }

    public byte[] bytes() {
        return bytes.clone();
    }
}
```

- Constructor dùng `clone()` để tạo mảng riêng, không giữ tham chiếu đến mảng đầu vào.
- Accessor tường minh dùng `clone()` để trả bản sao; người gọi không thể sửa mảng nội bộ qua kết quả trả về.
- Với `byte[]`, từng phần tử là primitive nên bản sao mảng cũng sao chép toàn bộ giá trị byte.
- Với mảng object như `StringBuilder[]`, `clone()` chỉ sao chép mảng ngoài; các object phần tử vẫn là tham chiếu cũ.

Nếu mảng chứa object mutable, cần sao chép từng phần tử bằng cách phù hợp với kiểu đó. Không có một lệnh clone chung nào tự động sao chép sâu mọi object trong mảng.

### Lưu ý về equals và hashCode của component mảng

Sao chép mảng đầu vào và đầu ra bảo vệ trạng thái, nhưng không thay đổi ngữ nghĩa bình đẳng mặc định của record. Mảng Java không override `equals()` và `hashCode()` theo nội dung; do đó hai mảng khác object nhưng có cùng phần tử vẫn không bằng nhau theo `equals()`.

```java
record Digest(byte[] bytes) {}

Digest first = new Digest(new byte[] {1, 2});
Digest second = new Digest(new byte[] {1, 2});

System.out.println(first.equals(second)); // false
```

Nếu nghiệp vụ yêu cầu so sánh theo nội dung, cần tự định nghĩa `equals()` và `hashCode()` nhất quán (ví dụ dùng `Arrays.equals()` và `Arrays.hashCode()`), hoặc chọn một kiểu component có ngữ nghĩa giá trị phù hợp. Đừng cho rằng sao chép phòng vệ tự động thay đổi cách record so sánh dữ liệu.

## 7. Bảo vệ object mutable lồng bên trong

Collection và mảng chỉ là hai trường hợp thường gặp. Một component có thể là bất kỳ object nào có trạng thái mutable, ví dụ một lớp địa chỉ nội bộ:

```java
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

    MutableAddress copy() {
        return new MutableAddress(city);
    }
}
```

Record giữ tham chiếu trực tiếp đến object này vẫn có thể bị tác động từ bên ngoài:

```java
record CustomerProfile(String name, MutableAddress address) {}

MutableAddress address = new MutableAddress("Ha Noi");
CustomerProfile profile = new CustomerProfile("An", address);

address.changeCity("Da Nang");
System.out.println(profile.address().city()); // Da Nang
```

Có thể bảo vệ bằng cách sao chép khi nhận và khi trả object:

```java
import java.util.Objects;

record CustomerProfileSnapshot(String name, MutableAddress address) {
    CustomerProfileSnapshot {
        name = Objects.requireNonNull(name, "name");
        address = Objects.requireNonNull(address, "address").copy();
    }

    public MutableAddress address() {
        return address.copy();
    }
}
```

Ví dụ minh họa nguyên tắc: constructor không giữ object mutable do caller sở hữu; accessor không làm lộ object nội bộ. Trong ứng dụng thực tế, nên ưu tiên trả về một kiểu bất biến như `AddressSnapshot` thay vì trả lại một bản sao mutable nếu người gọi chỉ cần đọc dữ liệu.

### Sao chép sâu phải phù hợp với cấu trúc object

Nếu object có các object con mutable khác, phương thức `copy()` cần sao chép tiếp những object con đó. Sao chép một lớp ngoài nhưng vẫn giữ nguyên tham chiếu đến object mutable bên trong chỉ là sao chép nông.

Không nên tự động sao chép sâu mọi object theo reflection hoặc serialization. Hãy định nghĩa rõ:

- Những object nào thuộc quyền sở hữu của record.
- Những object nào có thể được chia sẻ vì chúng bất biến.
- Những object nào cần bản sao độc lập.
- Có kiểu bất biến nào thay thế được cấu trúc mutable hay không.

Đối với dữ liệu nghiệp vụ, một record lồng nhau với các component bất biến thường đơn giản và an toàn hơn một object mutable lớn.

## 8. Accessor mặc định có thể làm lộ trạng thái mutable

Accessor được sinh tự động trả về component đang lưu. Với primitive và kiểu bất biến, hành vi này thường phù hợp. Với object mutable, nó có thể làm lộ tham chiếu nội bộ.

```java
record Settings(List<String> enabledFeatures) {}
```

Nếu không bảo vệ, code gọi có thể sửa danh sách qua:

```java
settings.enabledFeatures().clear();
```

Có hai điểm để bảo vệ:

1. **Ở constructor:** sao chép dữ liệu đầu vào để record không phụ thuộc vào collection mutable do caller giữ.
2. **Ở accessor:** trả về một view không sửa đổi hoặc một bản sao phù hợp, để caller không thể sửa object nội bộ.

Với danh sách phần tử bất biến, chỉ cần bản sao không sửa đổi trong constructor thường là đủ:

```java
record SafeSettings(List<String> enabledFeatures) {
    SafeSettings {
        enabledFeatures = List.copyOf(enabledFeatures);
    }
}
```

Accessor mặc định giờ trả về một danh sách không cho sửa cấu trúc. Nếu cần accessor trả bản sao độc lập, có thể khai báo tường minh:

```java
record SettingsCopy(List<String> enabledFeatures) {
    SettingsCopy {
        enabledFeatures = List.copyOf(enabledFeatures);
    }

    public List<String> enabledFeatures() {
        return List.copyOf(enabledFeatures);
    }
}
```

Trong trường hợp List đã không sửa đổi, accessor sao chép thêm thường không cần thiết. Chỉ nên làm khi hợp đồng API yêu cầu một bản sao mới hoặc khi component mutable cần cách bảo vệ riêng. Tránh tạo bản sao dư thừa trên mỗi lần đọc nếu không đem lại lợi ích bảo vệ thực tế.

## 9. Component mutable ảnh hưởng đến equals và hashCode như thế nào?

Các phương thức `equals()` và `hashCode()` mặc định của record dựa trên component. Nếu một component mutable thay đổi, kết quả bình đẳng hoặc mã băm có thể thay đổi theo ngữ nghĩa của kiểu component đó.

Ví dụ với danh sách mutable:

```java
import java.util.ArrayList;
import java.util.List;

record TeamKey(List<String> members) {}

List<String> names = new ArrayList<>(List.of("An"));
TeamKey key = new TeamKey(names);

int before = key.hashCode();
names.add("Binh");
int after = key.hashCode();

System.out.println(before == after); // false trong ví dụ này
```

`List.equals()` và `List.hashCode()` phụ thuộc vào các phần tử hiện tại và thứ tự của chúng. Vì vậy, thay đổi danh sách làm thay đổi kết quả của các phương thức record được sinh dựa trên component.

Nếu dùng object đó làm key của `HashMap` hoặc phần tử của `HashSet` rồi sau đó thay đổi component ảnh hưởng đến `hashCode()`, việc tìm lại object có thể thất bại:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record LookupKey(List<String> parts) {}

List<String> parts = new ArrayList<>(List.of("A"));
LookupKey key = new LookupKey(parts);

Map<LookupKey, String> map = new HashMap<>();
map.put(key, "value");

parts.add("B"); // Mã băm của key thay đổi theo List.
System.out.println(map.get(key)); // Không còn được bảo đảm tìm thấy entry.
```

Đây là lý do key dùng trong cấu trúc băm cần trạng thái bình đẳng ổn định trong suốt thời gian lưu trữ. Với record dùng làm key:

- Ưu tiên component primitive hoặc kiểu bất biến.
- Nếu component là collection, tạo snapshot không sửa đổi trong constructor.
- Đảm bảo phần tử bên trong collection cũng có ngữ nghĩa bình đẳng ổn định.
- Không làm lộ tham chiếu mutable qua accessor.

Với mảng, lưu ý khác biệt: `equals()` và `hashCode()` mặc định của mảng dựa trên identity, nên thay đổi nội dung mảng không làm mã băm identity thay đổi. Nhưng nội dung vẫn có thể biến đổi, khiến record không còn thể hiện snapshot dữ liệu như mong đợi. Nếu tự triển khai so sánh mảng theo nội dung, thay đổi mảng lại có thể làm thay đổi kết quả bình đẳng và mã băm; vì vậy vẫn cần bảo vệ mảng.

## 10. Bất biến và an toàn luồng

Field `final` hỗ trợ việc xây dựng object có trạng thái component cố định sau khởi tạo. Tuy nhiên, **final không tự làm object mutable bên trong trở thành thread-safe**.

Ví dụ, một record giữ `ArrayList` có thể bị thay đổi bởi bất kỳ luồng nào đang giữ tham chiếu đến danh sách. Việc field component là `final` không tự thêm đồng bộ cho các thao tác trên danh sách.

Để chia sẻ record giữa nhiều luồng an toàn hơn:

- Ưu tiên component là primitive và kiểu bất biến.
- Tạo bản sao phòng vệ trước khi lưu collection hoặc mảng.
- Không để tham chiếu mutable nội bộ bị làm lộ.
- Nếu component phải mutable và được chia sẻ, dùng cơ chế đồng bộ hoặc cấu trúc dữ liệu concurrent phù hợp với yêu cầu.
- Đảm bảo object được công bố (publish) theo quy tắc an toàn của Java Memory Model.

Một record chứa toàn component bất biến thường dễ chia sẻ hơn, nhưng không nên kết luận rằng mọi record tự động thread-safe. Tính an toàn luồng phụ thuộc cả object graph và cách ứng dụng chia sẻ dữ liệu.

## 11. Ví dụ hoàn chỉnh: snapshot khóa học có collection và mảng

Ví dụ sau tạo một snapshot gồm mã khóa học, danh sách chủ đề và một mảng byte. Constructor sao chép dữ liệu đầu vào; accessor mảng trả bản sao. Danh sách chứa `String` nên bản sao cấu trúc là đủ cho phần tử trong ví dụ.

Lưu vào tệp **`Demo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class Demo {
    record CourseSnapshot(String code, List<String> topics, byte[] digest) {
        CourseSnapshot {
            code = Objects.requireNonNull(code, "code").strip();
            if (code.isEmpty()) {
                throw new IllegalArgumentException("code must not be blank");
            }

            topics = List.copyOf(Objects.requireNonNull(topics, "topics"));
            digest = Objects.requireNonNull(digest, "digest").clone();
        }

        public byte[] digest() {
            return digest.clone();
        }
    }

    public static void main(String[] args) {
        List<String> inputTopics =
            new ArrayList<>(List.of("record", "immutability"));
        byte[] inputDigest = {10, 20, 30};

        CourseSnapshot snapshot =
            new CourseSnapshot(" JAVA-16 ", inputTopics, inputDigest);

        inputTopics.add("external-change");
        inputDigest[0] = 99;

        System.out.println(snapshot.code());   // JAVA-16
        System.out.println(snapshot.topics()); // [record, immutability]
        System.out.println(Arrays.toString(snapshot.digest())); // [10, 20, 30]

        byte[] exposed = snapshot.digest();
        exposed[1] = 88;
        System.out.println(Arrays.toString(snapshot.digest())); // [10, 20, 30]

        try {
            snapshot.topics().add("new-topic");
        } catch (UnsupportedOperationException exception) {
            System.out.println("Topics are unmodifiable");
        }
    }
}
```

Biên dịch và chạy trên JDK 16 trở lên:

```bash
javac --release 16 Demo.java
java Demo
```

Ví dụ minh họa:

1. `code` là String bất biến và được chuẩn hóa trong compact constructor.
2. `topics` được sao chép bằng `List.copyOf()`; các phần tử String cũng bất biến.
3. `digest` là mảng byte, được clone khi nhận vào.
4. Accessor `digest()` được khai báo tường minh để trả về bản sao.
5. Thay đổi collection và mảng nguồn sau khi tạo snapshot không làm thay đổi dữ liệu nội bộ.
6. Thay đổi mảng do accessor trả về cũng không tác động đến mảng nội bộ.

Lưu ý rằng `equals()` và `hashCode()` mặc định của `CourseSnapshot` vẫn so sánh component mảng theo identity. Ví dụ tập trung vào bảo vệ trạng thái mảng; nếu cần equality theo nội dung digest, hãy thiết kế và kiểm thử riêng `equals()`/`hashCode()` theo `Arrays.equals()` và `Arrays.hashCode()`.

## 12. Checklist khi thiết kế record có component mutable

Trước khi đưa record vào API hoặc dùng nó làm value object, hãy kiểm tra:

- [ ] Component có thật sự cần mutable không? Có thể thay bằng String, primitive, enum, record lồng hoặc kiểu bất biến không?
- [ ] Constructor có giữ tham chiếu trực tiếp đến collection hoặc mảng do caller sở hữu không?
- [ ] Collection có được sao chép thành snapshot không sửa đổi không?
- [ ] Phần tử trong collection có mutable không? Có cần sao chép sâu từng phần tử không?
- [ ] Mảng có được clone khi nhận vào không?
- [ ] Accessor có làm lộ tham chiếu mutable nội bộ không?
- [ ] Nếu accessor trả bản sao, bản sao đó có sao chép đủ các object lồng nhau không?
- [ ] Component có làm thay đổi `equals()` hoặc `hashCode()` theo thời gian không?
- [ ] Record có được dùng làm key trong `HashMap` hoặc phần tử `HashSet` không?
- [ ] Nếu chia sẻ giữa các luồng, dữ liệu mutable có cơ chế đồng bộ phù hợp không?

## Ghi nhớ

Field component của record là `private final`: mã bên ngoài không truy cập trực tiếp field và không thể gán lại tham chiếu sau khi đối tượng được khởi tạo. Nhưng nếu component trỏ đến object mutable, trạng thái object đó vẫn có thể thay đổi. Vì thế record mặc định chỉ bất biến nông. Để tạo snapshot ổn định, hãy sao chép collection trong constructor, bảo vệ mảng ở cả đầu vào lẫn đầu ra, và sao chép các object mutable lồng nhau theo đúng cấu trúc. `List.copyOf()` bảo vệ cấu trúc danh sách nhưng không sao chép sâu phần tử; `clone()` mảng cũng chỉ sao chép nông với mảng object. Cuối cùng, hãy xem xét ảnh hưởng đến `equals()`, `hashCode()`, việc dùng record làm khóa và chia sẻ giữa các luồng. Đây là các nguyên tắc thiết kế vẫn áp dụng cho record trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java API – List.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
- [Java API – Map.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map))
- [Java API – Set.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection))
- [Java API – Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List))
