# Phân biệt tập hợp không cho sửa với bất biến sâu trong Java

## 1. Vấn đề: không thể thêm phần tử không có nghĩa mọi dữ liệu đều bất biến

Khi thu thập kết quả bằng Java Stream, chúng ta thường gặp các kiểu mã:

~~~java
List<Person> people = source.stream().toList();
List<Person> copied = List.copyOf(people);
List<Person> wrapped = Collections.unmodifiableList(people);
~~~

Các dòng trên là **minh họa** khi `source`, `Person` và các import đã tồn tại. Chúng gợi ra ba câu hỏi **khác nhau**:

1. Có thể gọi `add()`, `remove()`, `set()` để thay đổi **cấu trúc danh sách qua tham chiếu đang có** không?
2. Danh sách kết quả có bị thay đổi **gián tiếp** khi một collection nguồn khác được sửa không?
3. Các **đối tượng nằm bên trong** danh sách có thể bị thay đổi không? Nếu có, các trường và cấu trúc lồng sâu bên trong chúng có tiếp tục thay đổi không?

Một collection **không cho sửa** (*unmodifiable collection*) thường chỉ chặn việc thay đổi cấu trúc/nội dung của collection **thông qua chính giao diện đó**. Nó **không tự làm cho tất cả đối tượng phần tử trở nên bất biến**.

**Bất biến sâu** (*deep immutability*) đòi hỏi mạnh hơn: mọi trạng thái có thể quan sát được trong toàn bộ đồ thị đối tượng mà API công khai cho phép truy cập cũng phải được bảo vệ khỏi thay đổi. Điều này không tự xuất hiện chỉ vì dùng `Stream.toList()`, `List.copyOf()`, `Collections.unmodifiableList()`, `record` hoặc `final`.

Trong bài này, ta phân biệt ba khái niệm: **unmodifiable view**, **snapshot cấu trúc**, và **deeply immutable object graph**, rồi áp dụng vào việc thu thập kết quả Stream và thiết kế DTO bất biến trong Java 17.

## 2. Ba tầng bất biến cần tách riêng

### 2.1. Không cho sửa qua tham chiếu hiện tại

Ví dụ:

~~~java
List<String> names = List.of("An", "Bình");
names.add("Chi"); // Ném UnsupportedOperationException.
~~~

`List.of(...)` tạo một danh sách unmodifiable: những thao tác thay đổi danh sách qua `names` như `add`, `remove` hoặc `set` không được hỗ trợ. Nhưng từ “unmodifiable” **chưa đủ để kết luận tất cả phần tử bên trong đều bất biến**. Ở đây `String` bản thân là immutable nên ví dụ trông an toàn ở cả hai tầng, nhưng nguyên nhân đến từ **cả loại list lẫn loại phần tử**.

### 2.2. Snapshot cấu trúc khác view động

Một **view** giữ liên hệ tới collection nguồn, nên thao tác thay đổi qua tham chiếu **nguồn** có thể được phản ánh trong view. Một **snapshot cấu trúc** lưu tập tham chiếu phần tử tại thời điểm tạo; các thay đổi thêm/xóa của nguồn về sau không tự thay đổi cấu trúc snapshot.

~~~java
List<String> source = new ArrayList<>(List.of("a"));
List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("b");

System.out.println(view);     // [a, b]
System.out.println(snapshot); // [a]
~~~

Đây là đoạn minh họa trong một phương thức, cần import `List`, `ArrayList`, `Collections`. `view` và `snapshot` đều không cho sửa **qua chính chúng**, nhưng **`view` có thể quan sát thay đổi cấu trúc ở nguồn**. `snapshot` giữ cấu trúc lấy tại thời điểm copy.

### 2.3. Snapshot cấu trúc không đồng nghĩa bản sao sâu

~~~java
StringBuilder text = new StringBuilder("draft");
List<StringBuilder> source = new ArrayList<>();
source.add(text);

List<StringBuilder> snapshot = List.copyOf(source);
text.append("-changed");

System.out.println(snapshot.get(0)); // draft-changed
~~~

`List.copyOf` tạo snapshot về **các phần tử trong danh sách**, nhưng không sao chép sâu từng `StringBuilder`. `snapshot.get(0)` vẫn trỏ tới **cùng đối tượng mutable** như `text`. Do đó người khác sửa `text` thì dữ liệu được quan sát qua snapshot vẫn đổi.

**Kết luận:** Chặn chỉnh sửa collection và chặn chỉnh sửa **trạng thái các phần tử** là **hai việc riêng biệt**.

## 3. Các API thu thập phổ biến có hợp đồng khác nhau

| API | Hợp đồng về tính sửa được | Có copy sâu phần tử? | Lưu ý quan trọng |
|---|---|---|---|
| `Stream.toList()` (Java 16+) | Trả danh sách **unmodifiable** | Không | Kết quả không cho `add/remove/set`; không hứa implementation cụ thể |
| `Collectors.toList()` | **Không bảo đảm** kiểu list, tính sửa được, thread safety hay serializability | Không | Không được dựa vào việc implementation hiện tại trả `ArrayList` |
| `Collectors.toUnmodifiableList()` (Java 10+) | Danh sách **unmodifiable** | Không | Từ chối phần tử `null` |
| `Collectors.toCollection(ArrayList::new)` | Kết quả là `ArrayList` do supplier tạo, sửa cấu trúc được | Không | Chọn rõ loại collection cần tạo |
| `List.of(...)` (Java 9+) | Danh sách **unmodifiable** | Không | Từ chối `null`; phần tử có thể mutable |
| `List.copyOf(collection)` (Java 10+) | Danh sách **unmodifiable**, snapshot cấu trúc từ collection đầu vào | Không | Từ chối `null`; có thể tái dùng instance phù hợp |
| `Collections.unmodifiableList(list)` | **Unmodifiable view** trên list được bọc | Không | Đổi list gốc thì view có thể đổi theo |
| `Collections.unmodifiableList(new ArrayList<>(source))` | View không cho sửa trên một bản sao cấu trúc riêng | Không | Giữ nguồn copy nội bộ không bị lộ, nhưng phần tử vẫn chia sẻ reference |

Tất cả các lựa chọn đều thuộc hệ sinh thái Java Collections/Stream, nhưng phục vụ nhu cầu khác nhau. **Câu hỏi đúng không phải “phương thức nào tốt nhất?” mà là “cần ràng buộc nào?”**

### 3.1. `Stream.toList()`: không sửa cấu trúc được

~~~java
List<String> result = Stream.of("a", "b")
        .map(String::toUpperCase)
        .toList();
~~~

`result` chứa `[A, B]` và `result.add("C")` ném `UnsupportedOperationException`. Java SE 17 không cam kết lớp triển khai cụ thể hay tính serializable của đối tượng danh sách được trả. Vì vậy tránh ép kiểu sang `ArrayList` hoặc dựa vào class name của list.

`Stream.toList()` cũng không tự sao chép sâu những object mà pipeline trả ra. Nếu mapper tạo cùng một reference mutable nhiều lần, kết quả có thể chứa nhiều phần tử cùng trỏ tới object đó.

### 3.2. `Collectors.toList()`: đừng suy diễn tính mutable

~~~java
List<String> result = Stream.of("a", "b")
        .collect(Collectors.toList());
~~~

Mặc dù một số JDK phổ biến hiện trả kết quả sửa được, tài liệu API của `Collectors.toList()` **không bảo đảm** tính mutable/unmodifiable hay loại collection cụ thể. Vì thế viết code mà tính đúng **phụ thuộc** vào `result.add(...)` thành công là không dựa trên một bảo đảm công khai.

**Nếu thực sự cần list mutable:** chọn rõ `Collectors.toCollection(ArrayList::new)` hoặc `new ArrayList<>(stream.toList())`.

**Nếu thực sự cần list unmodifiable:** chọn `Stream.toList()` hoặc `Collectors.toUnmodifiableList()`, sau khi cân nhắc chính sách `null`.

### 3.3. `Collectors.toUnmodifiableList()` và `List.copyOf()`

Hai API cho một list unmodifiable; chúng không làm immutable các object phần tử. `Collectors.toUnmodifiableList()` yêu cầu các phần tử không null, còn `List.copyOf` cũng từ chối phần tử null. `List.copyOf` có thể trả về cùng một object khi đầu vào đã là một list unmodifiable phù hợp; **không dựa vào việc nó luôn cấp phát một list mới**.

### 3.4. `Collections.unmodifiableList(...)` là view, không phải copy

~~~java
List<String> backing = new ArrayList<>(List.of("x"));
List<String> view = Collections.unmodifiableList(backing);

backing.set(0, "y");
System.out.println(view); // [y]
~~~

Bọc bằng `Collections.unmodifiableList` **không biến `backing` thành bất biến**. Ai vẫn giữ được reference `backing` đều có thể thay đổi cấu trúc hoặc giá trị phần tử của list nguồn; view nhìn thấy các thay đổi đó.

Chỉ sử dụng view nếu bạn **chấp nhận dữ liệu thay đổi theo backing collection** hoặc đã kiểm soát tuyệt đối reference có thể sửa backing. Đối với snapshot API public, nên xem xét `List.copyOf` hoặc copy phòng vệ phù hợp.

## 4. Chương trình chạy được: view, snapshot và phần tử mutable

Lưu file **`UnmodifiableVsDeepDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableVsDeepDemo {
    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        List<StringBuilder> source = new ArrayList<>();
        source.add(first);

        List<StringBuilder> view =
                Collections.unmodifiableList(source);
        List<StringBuilder> snapshot =
                List.copyOf(source);
        List<StringBuilder> streamList =
                source.stream().toList();

        source.add(new StringBuilder("B"));
        first.append("!");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
        System.out.println("streamList=" + streamList);

        try {
            snapshot.add(new StringBuilder("C"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot.add=blocked");
        }

        try {
            streamList.set(0, new StringBuilder("X"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("streamList.set=blocked");
        }

        snapshot.get(0).append("?");
        System.out.println("sourceAfterElementEdit=" + source);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17+**:

~~~bash
javac UnmodifiableVsDeepDemo.java
java UnmodifiableVsDeepDemo
~~~

Stdout:

~~~text
source=[A!, B]
view=[A!, B]
snapshot=[A!]
streamList=[A!]
snapshot.add=blocked
streamList.set=blocked
sourceAfterElementEdit=[A!?, B]
~~~

**Điều gì vừa xảy ra?**

1. `view` được tạo từ `source` mà không copy. Sau `source.add(...)`, `view` có hai phần tử.
2. `snapshot = List.copyOf(source)` và `streamList = source.stream().toList()` được tạo khi nguồn chỉ có **một** phần tử. Sau khi thêm `B` vào `source`, kích thước hai list này **không tự tăng**.
3. `first` vẫn là cùng một `StringBuilder` được cả `source`, `view`, `snapshot` và `streamList` tham chiếu. Vì vậy `first.append("!")` khiến giá trị phần tử đầu được nhìn thấy là `A!` ở cả bốn list.
4. `snapshot.add(...)` và `streamList.set(...)` không được hỗ trợ và ném `UnsupportedOperationException`.
5. Nhưng `snapshot.get(0).append("?")` vẫn được phép vì **đang sửa object `StringBuilder`**, không sửa cấu trúc `snapshot`. Nguồn đổi thành `[A!?, B]`.

Ví dụ chứng minh rằng **không sửa được list qua API không có nghĩa toàn bộ dữ liệu bên trong đã được “đóng băng”**. Đây là một cách kiểm tra rất trực quan trong code review.

## 5. Record và final không tự tạo bất biến sâu

Java record giúp khai báo dữ liệu gọn và có các trường thành viên `private final`. Tuy vậy, **final chỉ ngăn thay đổi reference của trường**, không ngăn sửa object mà reference trỏ đến.

~~~java
record Team(String name, List<String> members) {}

List<String> members = new ArrayList<>(List.of("An"));
Team team = new Team("A", members);

members.add("Bình");
System.out.println(team.members()); // [An, Bình]
~~~

Đây là đoạn minh họa trong phương thức. `Team` là record, nhưng không có defensive copy trong constructor. Đối tượng record vẫn lộ reference tới list mutable được truyền vào; phía gọi giữ `members` có thể thay đổi nó.

Cũng vậy:

~~~java
record Document(String title, StringBuilder content) {}
~~~

Record trên **không bất biến sâu** vì `StringBuilder` có thể sửa. Dù field là `final`, người dùng có thể lấy `document.content()` rồi gọi `append`.

**Quy tắc:** Để xây mô hình dữ liệu bất biến, phải xét **tất cả đường dẫn tham chiếu** đến trạng thái mutable, không chỉ keyword `final` hoặc loại object bên ngoài.

## 6. Defensive copying: hướng tới bản chụp dữ liệu bất biến

Một cách thiết kế phổ biến là **copy phòng vệ tại ranh giới** giữa dữ liệu mutable và dữ liệu public, đồng thời dùng kiểu phần tử immutable.

Ví dụ với một đơn hàng có tên và các nhãn dạng `String`:

~~~java
record OrderSnapshot(String id, List<String> tags) {
    public OrderSnapshot {
        tags = List.copyOf(tags);
    }
}
~~~

Đây là **record minh họa**. Trong compact constructor, gán lại tham số `tags` bằng `List.copyOf(tags)` làm cho trường record được khởi tạo bằng list snapshot unmodifiable. Vì `String` là immutable, người gọi không thể làm thay đổi nội dung một tag sau khi tạo.

Ở mô hình này:

- **Copy đầu vào**: nếu bên ngoài thay đổi list gốc, `OrderSnapshot.tags()` không đổi cấu trúc.
- **Không lộ list mutable**: `tags()` trả list unmodifiable, nên người gọi không thể thêm/xóa/sửa vị trí qua accessor.
- **Các phần tử là `String`**: chúng là immutable, nên không có reference mutable cấp sâu hơn được expose qua tags.
- **`id` cũng là `String`**: không có mutable state phía sau.

Đây là một ví dụ **bất biến sâu đối với đồ thị dữ liệu do record công khai**. Nó không có nghĩa `List.copyOf` là hàm deep-copy tổng quát: tính an toàn đến từ **sự kết hợp copy cấu trúc và kiểu lá immutable**.

### 6.1. Chương trình Java 17 hoàn chỉnh: sao chép khi thu thập Stream

Lưu thành **`ImmutableSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableSnapshotDemo {
    record SourceOrder(String id, List<String> tags) {}

    record OrderSnapshot(String id, List<String> tags) {
        public OrderSnapshot {
            tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> originalTags =
                new ArrayList<>(List.of("java"));
        List<SourceOrder> source = new ArrayList<>();
        source.add(new SourceOrder("A", originalTags));

        List<OrderSnapshot> snapshots = source.stream()
                .map(order -> new OrderSnapshot(
                        order.id(), order.tags()))
                .toList();

        originalTags.add("changed");
        source.add(new SourceOrder("B", List.of("new")));

        System.out.println("sourceSize=" + source.size());
        System.out.println("sourceTags=" + originalTags);
        System.out.println("snapshotSize=" + snapshots.size());
        System.out.println("snapshots=" + snapshots);

        try {
            snapshots.get(0).tags().add("bad");
        } catch (UnsupportedOperationException ex) {
            System.out.println("tags.add=blocked");
        }

        try {
            snapshots.add(new OrderSnapshot("C", List.of()));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshots.add=blocked");
        }
    }
}
~~~

Chạy:

~~~bash
javac ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
~~~

Stdout:

~~~text
sourceSize=2
sourceTags=[java, changed]
snapshotSize=1
snapshots=[OrderSnapshot[id=A, tags=[java]]]
tags.add=blocked
snapshots.add=blocked
~~~

**Phân tích:**

1. `SourceOrder` giữ list `originalTags` mutable; sau này bên ngoài có thể thêm `"changed"`.
2. `source.stream().map(...)` tạo **record mới** `OrderSnapshot` cho mỗi nguồn. Bản thân bước `map` này mới là nơi chuyển đổi **dữ liệu mutable sang một representation an toàn**.
3. Compact constructor `OrderSnapshot` dùng `List.copyOf` để tạo danh sách nhãn không cho sửa, không phụ thuộc vào các thay đổi thêm/xóa ở nguồn.
4. `Stream.toList()` bảo đảm **danh sách snapshot ngoài** không cho sửa. Còn constructor của `OrderSnapshot` bảo vệ **danh sách bên trong từng record**.
5. Vì `id` và các nhãn là `String` immutable, ở phạm vi object graph này ta có cấu trúc bất biến xuyên suốt.
6. Hai thao tác cố thay đổi list ngoài và list tag đều bị chặn; kết quả trước/sau không bị ảnh hưởng bởi thay đổi `originalTags`.

Đây là thiết kế thường có giá trị khi xuất DTO từ một pipeline xử lý, trao dữ liệu qua API public hoặc trả cấu hình đọc-only. **Chỉ gọi `toList()` ở cuối không đủ:** nếu bỏ bước `map`/defensive copy và để những object mutable đi thẳng vào kết quả, vẫn có nguy cơ thay đổi sâu.

## 7. Muốn thay đổi kết quả sau khi thu thập: chọn API mutable rõ ràng

Nếu yêu cầu thực tế là **thêm/xóa/sắp xếp** danh sách sau khi lấy kết quả, đừng mặc định `toList()` hoặc `Collectors.toList()` phù hợp.

Ví dụ:

~~~java
List<String> sorted = words.stream()
        .sorted()
        .collect(Collectors.toCollection(ArrayList::new));

sorted.add("extra");
sorted.sort(String::compareTo);
~~~

Đoạn minh họa cần `words` và imports `List`, `ArrayList`, `Collectors`. `Collectors.toCollection(ArrayList::new)` tạo một `ArrayList`, vì vậy có thể thay đổi cấu trúc. Mặt khác, cho dù outer list mutable, **các phần tử vẫn do mapper quyết định**: nếu chúng là object mutable, vẫn phải chú ý aliasing.

Một lựa chọn dễ hiểu:

~~~java
List<String> mutable = new ArrayList<>(
        words.stream().map(String::trim).toList());
~~~

`ArrayList` mới này copy cấu trúc của kết quả stream để có list mutable. Không phải deep copy.

Nếu mục tiêu là danh sách **không cho sửa**, thường chọn `Stream.toList()` (Java 16+) hoặc `Collectors.toUnmodifiableList()` và tránh chuyển nó sang mutable chỉ để bọc lại.

### 7.1. Chương trình hoàn chỉnh: collector và tính sửa được

Lưu thành **`CollectorChoiceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectorChoiceDemo {
    public static void main(String[] args) {
        ArrayList<String> editable = Stream.of("a", "b")
                .collect(Collectors.toCollection(ArrayList::new));

        List<String> fixed = Stream.of("a", "b")
                .toList();

        List<String> unmodifiable = Stream.of("a", "b")
                .collect(Collectors.toUnmodifiableList());

        editable.add("c");

        System.out.println("editable=" + editable);
        System.out.println("fixed=" + fixed);
        System.out.println("unmodifiable=" + unmodifiable);

        try {
            fixed.add("x");
        } catch (UnsupportedOperationException ex) {
            System.out.println("fixed.add=blocked");
        }

        try {
            unmodifiable.remove(0);
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable.remove=blocked");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CollectorChoiceDemo.java
java CollectorChoiceDemo
~~~

Stdout:

~~~text
editable=[a, b, c]
fixed=[a, b]
unmodifiable=[a, b]
fixed.add=blocked
unmodifiable.remove=blocked
~~~

`editable` được tạo rõ ràng bằng supplier `ArrayList::new` nên có hợp đồng mutable như `ArrayList`. `fixed` và `unmodifiable` có hợp đồng unmodifiable, nhưng không có giả định rằng chúng dùng cùng kiểu lớp bên trong hoặc tự deep-copy object.

**Điểm tinh tế:** `Collectors.toList()` không xuất hiện trong kiểm thử mutable ở ví dụ này, vì API **không bảo đảm kết quả sửa được**. Muốn học đúng contract, tránh viết test “thành công vì phiên bản JDK hiện tại tình cờ trả một loại list cụ thể”.

## 8. Bất biến sâu là thuộc tính của cả đồ thị đối tượng

Xét dạng dữ liệu:

~~~text
List<Order>
   ├── Order{id, List<Line>}
   │                └── Line{sku, int[] quantities}
   └── Order{id, List<Line>}
                    └── Line{sku, int[] quantities}
~~~

Ngay cả khi outer `List<Order>` unmodifiable, các điểm sau vẫn có thể mutable:

- `Order` có setter hoặc các trường cấu hình được cập nhật.
- `Order.lines` là `ArrayList` và có thể thay đổi.
- `Line` có setter; hoặc chứa một mảng `int[]` mà caller có thể thay phần tử.
- Một reference ngoài hệ thống vẫn trỏ tới cùng `Order`, `Line` hoặc mảng.

Để đạt mục tiêu bất biến sâu, cần xác định **phần nào trong object graph có thể quan sát công khai** và bảo vệ mọi mutable component ở các điểm đi vào/đi ra API.

Ví dụ hướng xử lý:

1. Dùng **kiểu immutable cho giá trị lá** như `String`, primitive, enum, hoặc immutable value objects.
2. Với `List`/`Set`/`Map`, tạo snapshot cấu trúc rồi đảm bảo **mỗi phần tử hoặc value bên trong cũng bất biến**.
3. Với các mảng `byte[]`, `int[]` và object array, cần **clone/copy phòng vệ**, kể cả khi trả qua accessor.
4. Với những class có setter hoặc mutable state, tạo một **value snapshot** riêng thay vì dùng chung reference.
5. Với graph sâu, có chu trình hoặc aliasing phức tạp, cần thiết kế chính sách copy rõ; Java không có một lệnh `deepCopy()` tổng quát an toàn cho mọi loại object.

**Không có một wrapper collection nào tự động duyệt toàn bộ graph và biến mọi object thành immutable.** Bất biến sâu là đặc tính thiết kế của mô hình dữ liệu và khả năng tiếp cận các tham chiếu mutable.

### 8.1. Mảng trong record: cần copy cả ở constructor và accessor

~~~java
record Bytes(byte[] data) {
    public Bytes {
        data = data.clone();        // Copy khi nhận từ caller.
    }

    @Override
    public byte[] data() {
        return data.clone();        // Copy khi trả ra cho caller.
    }
}
~~~

Đây là **đoạn record minh họa**, có thể biên dịch khi đặt trong file Java đúng ngữ cảnh. Dù record chứa field `final`, mảng `byte[]` vẫn mutable: nếu getter trả trực tiếp mảng gốc, caller có thể sửa phần tử của record từ bên ngoài.

Ví dụ:

~~~java
byte[] original = {1, 2};
Bytes safe = new Bytes(original);
original[0] = 9;
byte[] exposed = safe.data();
exposed[1] = 8;
System.out.println(java.util.Arrays.toString(safe.data())); // [1, 2]
~~~

Ở đây constructor clone giúp tránh thay đổi đến từ `original`; accessor clone giúp tránh thay đổi đến từ `exposed`. **Cả hai chiều** là cần thiết vì một mảng mutable có thể bị giữ reference trước hoặc sau khi record được tạo.

**Lưu ý:** Vì accessor trả mảng mới mỗi lần, các phương thức `equals()`/`hashCode()` mặc định của record có trường array không tự làm so sánh nội dung của mảng như mong muốn. Nếu thiết kế value object dựa trên array, cần xem thêm semantics của equality/hash code, bên cạnh chuyện bất biến sâu.

### 8.2. Một tập hợp lồng nhau vẫn có thể bị sửa

~~~java
List<List<String>> outer = List.of(
        new ArrayList<>(List.of("a"))
);

outer.get(0).add("b"); // Thành công: list con còn mutable.
~~~

`outer` không cho sửa cấu trúc; **list con** là `ArrayList` và có thể thêm `"b"`. Muốn có các list con unmodifiable và độc lập cấu trúc nguồn:

~~~java
List<List<String>> deepStructure = outer.stream()
        .map(List::copyOf)
        .toList();
~~~

Vì leaf là `String` immutable, cách này tạo một graph các list unmodifiable tại hai cấp. Nếu phần tử list con là `StringBuilder` hoặc class mutable khác, **vẫn phải tạo snapshot riêng cho mỗi phần tử**.

### 8.3. Map chứa List cũng cần bảo vệ cả value

~~~java
Map<String, List<String>> snapshot = sourceMap.entrySet()
        .stream()
        .collect(Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                entry -> List.copyOf(entry.getValue())
        ));
~~~

Đây là **đoạn minh họa**, yêu cầu import `Map` và `Collectors`; `sourceMap` phải có kiểu phù hợp, key/value không null, và không có khóa trùng từ entry set bình thường. `toUnmodifiableMap` làm map ngoài unmodifiable; `List.copyOf` làm các list value thành snapshot cấu trúc unmodifiable; `String` ở cả key và list element là immutable.

Nếu bỏ `List.copyOf` và chỉ dùng `toUnmodifiableMap`, một value là list mutable vẫn có thể thay đổi. Đây là ví dụ tổng quát rằng **bảo vệ container ngoài không tự bảo vệ các container bên trong**.

## 9. Null, thứ tự và các bảo đảm không nên tự suy diễn

### 9.1. Chính sách null không giống nhau ở mọi factory

- `List.of(...)` và `List.copyOf(...)` từ chối phần tử `null`.
- `Collectors.toUnmodifiableList()` cũng từ chối `null`.
- `Collections.unmodifiableList(backing)` bọc một backing list; nếu backing chứa `null`, view có thể hiển thị null.
- `Stream.toList()` trong Java 17 có thể thu thập phần tử `null`; **không nên mặc định** rằng nó áp dụng cùng chính sách null của `Collectors.toUnmodifiableList()`.
- `Collectors.toList()` không hứa một loại list cụ thể; nếu nghiệp vụ cần chính sách null rõ, nên xác định và kiểm tra nguồn hoặc chọn API với contract phù hợp.

Ví dụ `Stream.of("a", null).toList()` trên Java 17 cho kết quả có phần tử null; trong khi `Stream.of("a", null).collect(Collectors.toUnmodifiableList())` ném `NullPointerException`. Nhưng trong ứng dụng, để dữ liệu an toàn hơn thường nên xác định chính sách null ngay ở ranh giới vào hệ thống.

### 9.2. Unmodifiable không đồng nghĩa thread-safe

Ngay cả một `Collections.unmodifiableList(backing)` cũng có thể phản ánh các thay đổi do thread khác thực hiện trên backing. Wrapper không tự đồng bộ hóa việc thay đổi/duyệt. Một list snapshot với các phần tử mutable vẫn có thể quan sát biến đổi của phần tử từ thread khác.

Với mô hình immutable đúng nghĩa, việc chia sẻ dữ liệu giữa thread thường dễ suy luận hơn, nhưng **cách công bố reference an toàn** (*safe publication*) và các cơ chế đồng bộ khi khởi tạo/chia sẻ vẫn phải tuân theo Java Memory Model trong thiết kế tổng thể.

### 9.3. Không dựa vào identity của list unmodifiable

Một số factory có thể chia sẻ hoặc tái dùng object list, và những list được trả có thể mang tính *value-based*. Không nên dùng `==`, `System.identityHashCode`, locking trên object list hoặc tên class để định nghĩa logic nghiệp vụ. Khi cần so sánh nội dung list, dùng `equals()` theo semantics của `List`.

### 9.4. Snapshot cấu trúc không phải transaction snapshot

Nếu nguồn bị sửa đồng thời đúng lúc bạn đang thu thập hoặc copy, `Stream.toList()` hay `List.copyOf()` không tự biến thao tác đó thành một giao dịch có snapshot nhất quán. Thay đổi đồng thời không có đồng bộ hóa thích hợp có thể gây kết quả khó dự đoán hoặc lỗi. Cần kiểm soát truy cập nguồn nếu yêu cầu tính nhất quán ở một thời điểm.

## 10. Những lựa chọn thiết kế thường gặp khi thu thập kết quả

| Nhu cầu thực tế | Hướng tiếp cận | Vì sao |
|---|---|---|
| Trả một danh sách **không cho sửa cấu trúc** | `stream.toList()` | API ngắn, contract unmodifiable rõ (Java 16+) |
| Trả một danh sách không cho sửa và **cấm null** | `collect(toUnmodifiableList())` | Contract từ chối null rõ |
| Cần danh sách mutable và biết chính xác loại collection | `collect(toCollection(ArrayList::new))` | Chỉ định concrete collection |
| Muốn snapshot cấu trúc từ collection đã có | `List.copyOf(source)` | Không phụ thuộc thêm/xóa sau đó của nguồn mutable |
| Muốn view read-only **phản ánh thay đổi backing** | `Collections.unmodifiableList(backing)` | Cố ý giữ kết nối với backing |
| Muốn list chứa các DTO immutable | `map(this::toSnapshot).toList()` | Mapper đảm nhiệm defensive copying từng object |
| Muốn bảo vệ mảng nội bộ | Copy ở constructor **và** accessor | Tránh lộ mutable reference |
| Muốn bảo vệ `Map<K,List<V>>` | Copy map và từng list value, đảm bảo K/V immutable | Bảo vệ từng tầng object graph |
| Muốn snapshot dữ liệu lớn đang có writer song song | Đồng bộ/cơ chế snapshot chuyên dụng trước khi copy | Copy unmodifiable không tự có snapshot giao dịch |

Chọn theo **ràng buộc API công khai**, không chỉ chọn theo độ ngắn của cú pháp. Một DTO bất biến sâu có thể cần nhiều dòng code ở ranh giới dữ liệu, nhưng thường giúp giảm chi phí kiểm tra trạng thái ở nơi sử dụng.

## 11. Những lỗi phổ biến và cách sửa

### Lỗi 1: “`toList()` rồi nên mọi thứ bất biến”

~~~java
List<StringBuilder> list = Stream.of(
        new StringBuilder("a")
).toList();

list.get(0).append("b"); // Thành công.
~~~

`toList()` không cho sửa cấu trúc danh sách, **không** làm `StringBuilder` bất biến. Nếu muốn các chuỗi bất biến, chuyển thành `String` bằng `map(StringBuilder::toString)` trước khi thu thập.

### Lỗi 2: “`Collections.unmodifiableList` tạo snapshot”

~~~java
List<String> backing = new ArrayList<>(List.of("x"));
List<String> view = Collections.unmodifiableList(backing);
backing.add("y"); // view phản ánh "y".
~~~

Nếu muốn snapshot độc lập cấu trúc nguồn, dùng `List.copyOf(backing)` hoặc copy riêng rồi bọc. Không giữ exposed reference đến backing nội bộ nếu muốn ngăn sửa.

### Lỗi 3: “`Collectors.toList()` chắc chắn là ArrayList”

Javadoc không bảo đảm mutability hoặc concrete type. Nếu thật sự cần `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`. Đừng ép kiểu mù hoặc phụ thuộc version JDK.

### Lỗi 4: “Record luôn là immutable”

~~~java
record Config(List<String> flags) {}
~~~

Nếu `flags` là mutable list, record mặc định chỉ giữ reference. Hãy copy phòng vệ trong constructor:

~~~java
record Config(List<String> flags) {
    public Config {
        flags = List.copyOf(flags);
    }
}
~~~

Vì ở đây leaf `String` immutable và list không sửa được, object public an toàn hơn trước thay đổi từ bên ngoài.

### Lỗi 5: Chỉ copy ở constructor nhưng trả nguyên mảng qua accessor

Ngay cả khi constructor đã clone mảng, getter trả trực tiếp array vẫn lộ trạng thái bên trong. Hãy copy cả hai chiều, hoặc dùng một representation immutable khác.

### Lỗi 6: Quên copy các tầng lồng nhau

`List.copyOf(listOfMutableLists)` chỉ khóa list ngoài. Caller vẫn có thể gọi `result.get(0).add(...)` nếu list con mutable. Cần làm từng list con thành immutable và copy phần tử mutable nếu có.

### Lỗi 7: Dùng unmodifiable view như cơ chế bảo vệ thread

Một view bọc list mutable không tự giải quyết race conditions hay đồng bộ hóa. Nếu nhiều thread có thể sửa backing, cần thiết kế thread safety riêng.

### Lỗi 8: Nghĩ `List.copyOf` luôn cấp phát object mới

API có thể tái dùng một list unmodifiable phù hợp. Không nên dựa vào `copy != original` hoặc tính identity để xác nhận copy sâu. Hãy kiểm tra **hành vi quan sát được** và ràng buộc của các phần tử.

### Lỗi 9: Bỏ qua khả năng phần tử null

`List.copyOf` và `Collectors.toUnmodifiableList` từ chối null. Khi chuyển một pipeline từ `toList` sang `toUnmodifiableList`, hãy kiểm tra dữ liệu và các test null trước.

### Lỗi 10: Copy bằng serialization hoặc clone tùy tiện

`clone()` không mặc định deep-copy. Serialization cũng không phải phương án mặc định an toàn/hiệu quả để tạo graph immutable, có vấn đề bảo mật và versioning tùy dữ liệu. Hãy định nghĩa cách chuyển dữ liệu mutable thành immutable một cách tường minh.

## 12. Checklist review API trả collection

1. **Outer collection có thể sửa được không?** Đọc hợp đồng chứ không suy ra từ class của JDK hiện tại.
2. **Kết quả là view hay snapshot cấu trúc?** Nếu source sửa thêm/xóa, output có đổi không?
3. **Phần tử có mutable state không?** Class/record phần tử có setter, list, map, array hoặc mutable object nào?
4. **Có alias từ ngoài vào không?** Caller có giữ được reference tới các phần tử gốc?
5. **Có alias từ trong ra không?** Accessor/getter trả object mutable trực tiếp?
6. **Đã copy ở mọi tầng cần thiết chưa?** Đặc biệt các collection lồng nhau và array.
7. **Các leaf value có immutable không?** `String`, primitive/boxed immutable và những value object thiết kế đúng.
8. **Chính sách null có phù hợp không?** `List.copyOf`/`toUnmodifiableList` không nhận null.
9. **Có cần mutable result không?** Nếu có, chọn `toCollection(ArrayList::new)` rõ ràng.
10. **Có cần thứ tự phần tử ổn định không?** Kiểm tra encounter order của nguồn/pipeline, không đánh đồng với bất biến.
11. **Có yêu cầu concurrency/snapshot nhất quán không?** Nếu có, kiểm soát dữ liệu nguồn và thời điểm copy.
12. **Đã test cả thay đổi nguồn và thay đổi phần tử chưa?** Thử sửa backing source, gọi `add` trên result và gọi setter của phần tử riêng biệt.

Một bộ test tốt không chỉ xác nhận `result.add(...)` ném `UnsupportedOperationException`. Nó còn thử **sửa nguồn sau khi copy** và **sửa object nằm trong collection**. Đó mới là cách phân biệt đúng snapshot cấu trúc với bất biến sâu.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Stream.of("a", "b").toList()` có cho `add("c")` không? Có đảm bảo là `ArrayList` không?

**Câu 2.** `Collections.unmodifiableList(backing)` khác `List.copyOf(backing)` ở điểm quan trọng nào?

**Câu 3.** `List.copyOf(List.of(new StringBuilder("a")))` đã immutable sâu chưa? Vì sao?

**Câu 4.** Có nên dựa vào việc `Collectors.toList()` luôn trả list mutable không?

**Câu 5.** Làm cách nào thu thập Stream thành một `ArrayList` mutable theo hợp đồng API?

**Câu 6.** Một record có trường `List<String>` nhận list mutable trực tiếp và không copy có bất biến sâu không?

**Câu 7.** Vì sao cần clone một `byte[]` ở cả constructor và accessor nếu muốn bảo vệ trạng thái?

**Câu 8.** `List.of` và `List.copyOf` có cho phần tử null không?

**Câu 9.** Sau `List.copyOf(source)`, nguồn được thêm một phần tử mới. Snapshot có tự có thêm phần tử không? Nếu phần tử cũ mutable bị sửa thì sao?

**Câu 10.** Để tạo `List<OrderSnapshot>` bất biến từ `Stream<MutableOrder>`, chỉ dùng `stream.toList()` là đủ chưa?

**Đáp án:**

1. Không cho sửa; không bảo đảm implementation là `ArrayList`.
2. `unmodifiableList` là view phản ánh backing, còn `copyOf` tạo snapshot cấu trúc theo hợp đồng.
3. Chưa; `StringBuilder` vẫn mutable và được chia sẻ reference.
4. Không, API không cam kết mutability.
5. `collect(Collectors.toCollection(ArrayList::new))` hoặc copy sang `new ArrayList<>(...)`.
6. Không nếu list mutable bị giữ reference hoặc lộ qua accessor; cần defensive copy phù hợp.
7. Để tránh thay đổi từ reference đầu vào và tránh caller sửa mảng thông qua getter.
8. Không; cả hai từ chối null.
9. Không thêm cấu trúc; nhưng object phần tử cũ vẫn có thể thay đổi nếu mutable.
10. Chưa; phải chuyển từng `MutableOrder` sang DTO/snapshot bất biến và copy tất cả trạng thái lồng nhau cần thiết.

## 14. Tài liệu chính thức

- [Java SE 17 — Stream.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): hợp đồng danh sách unmodifiable và các lưu ý về implementation.
- [Java SE 17 — Collectors.toList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toList()): không bảo đảm kiểu list/tính sửa được.
- [Java SE 17 — Collectors.toUnmodifiableList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): thu thập vào list unmodifiable và từ chối null.
- [Java SE 17 — List.of()/List.copyOf()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): immutable collection factories, snapshot cấu trúc và quy tắc null.
- [Java SE 17 — Collections.unmodifiableList()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable **view** của list nguồn.
- [Java SE 17 — Collectors.toCollection()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toCollection(java.util.function.Supplier)): chọn concrete collection bằng factory.

**Ghi nhớ:** **Unmodifiable** nghĩa là không thể sửa collection **qua giao diện đó**. **Snapshot cấu trúc** nghĩa là thêm/xóa ở nguồn không tự thay đổi danh sách đã lấy. **Deep immutability** nghĩa là toàn bộ trạng thái có thể quan sát qua object graph đã được thiết kế không thể bị thay đổi từ các tham chiếu công khai. `Stream.toList()`, `List.copyOf()` và `Collections.unmodifiableList()` **không tự deep-copy phần tử**. Để có kết quả bất biến sâu, cần kết hợp **thu thập unmodifiable**, **defensive copying** và **kiểu phần tử bất biến** ở mọi tầng dữ liệu liên quan.