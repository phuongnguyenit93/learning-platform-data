# Immutability và immutable object graph trong Java Concurrency

## 1. Vì sao bất biến giúp chương trình đa luồng dễ đúng hơn?

Khi nhiều thread cùng truy cập một đối tượng có thể thay đổi, mỗi thread phải trả lời các câu hỏi: ai được ghi, ai được đọc, đọc ở thời điểm nào, cần khóa nào và dữ liệu có đồng bộ không? Nếu đối tượng đã được **khởi tạo hoàn chỉnh và không còn thay đổi**, các thread chỉ đọc sẽ không cạnh tranh để sửa trạng thái của đối tượng đó. Điều này giảm đáng kể số tình huống gây **data race**, trạng thái trung gian và vi phạm bất biến nghiệp vụ.

**Immutability (tính bất biến)** nghĩa là trạng thái quan sát được của một đối tượng không thay đổi sau khi được tạo. **Immutable object graph (đồ thị đối tượng bất biến)** mở rộng ý tưởng này tới những đối tượng có thể truy cập qua các trường tham chiếu, phần tử collection, mảng, object lồng nhau và các đường dẫn khác bắt đầu từ một đối tượng gốc.

Ví dụ, một cấu hình có cấu trúc:

```text
AppConfig
  ├── name: String
  ├── limits: Map<String, Integer>
  └── endpoints: List<Endpoint>
                       ├── host: String
                       └── tags: List<String>
```

Muốn cấu hình này thực sự bất biến theo quan sát của caller, không chỉ trường `name` mà cả nội dung `limits`, `endpoints`, từng `Endpoint` và `tags` cũng phải được bảo vệ khỏi sửa đổi về sau. Chỉ thêm `final` vào ba trường của `AppConfig` là **chưa đủ** nếu chúng trỏ tới `HashMap`, `ArrayList` hoặc `Endpoint` mutable.

Mục tiêu của bài: phân biệt các mức bất biến, xác định biên của đồ thị object, tạo và công bố snapshot an toàn trong Java, nhận diện các lỗ hổng do aliasing, collection lồng nhau và cập nhật đồng thời. Đây là nội dung về **Java concurrency nói chung**.

## 2. Bốn khái niệm thường bị nhầm lẫn

| Khái niệm | Bảo đảm thực sự | Ví dụ | Điều chưa được bảo đảm |
| --- | --- | --- | --- |
| **Final field** | Không thể gán lại trường qua mã Java thông thường sau khởi tạo | `final List<String> items` | Danh sách được tham chiếu không tự trở thành bất biến |
| **Unmodifiable view** | Tham chiếu view không cho phép sửa qua các method thông thường của nó | `Collections.unmodifiableList(source)` | Nếu `source` còn mutable, view có thể phản ánh thay đổi của source |
| **Unmodifiable snapshot** | Một collection không cho sửa qua API của nó và không tiếp tục phản ánh thay đổi cấu trúc của collection nguồn | `List.copyOf(source)` | Các phần tử object bên trong có thể vẫn mutable |
| **Immutable object graph** | Trạng thái quan sát được của toàn bộ cấu trúc reachable không thay đổi sau khi công bố | Record với `String`, số nguyên, danh sách sao chép của các phần tử bất biến | Vẫn cần cách khởi tạo và công bố tham chiếu an toàn |

Ví dụ `final List<String>` có thể rất an toàn nếu giá trị gán thực sự là một danh sách bất biến của các `String` bất biến, nhưng từ khóa `final` **tự nó không chứng minh được điều đó**.

Cần phân biệt thêm:

- **Shallow immutability (bất biến nông):** các trường trực tiếp không được gán lại, hoặc collection không cho sửa cấu trúc qua API đang dùng; các object bên trong vẫn có thể thay đổi.
- **Deep immutability (bất biến sâu):** mọi phần trạng thái quan sát được qua các tham chiếu có liên quan đều không đổi. Phải kiểm tra cả các đối tượng lồng nhau và bí danh tham chiếu (alias).
- **Effective immutability (bất biến theo cách sử dụng):** một object vốn có API sửa đổi nhưng sau khi công bố được bảo đảm không còn bị sửa nữa. Đây là một *giao thức* cần được toàn bộ code tuân thủ, khó kiểm chứng hơn immutable type thực sự.
- **Read-only reference (tham chiếu chỉ đọc):** caller không thể sửa qua tham chiếu ấy, nhưng có thể có chủ sở hữu khác vẫn sửa được object gốc. Read-only không tự đồng nghĩa immutable.

## 3. Object graph và vấn đề aliasing

Java lưu các object trên heap; trường kiểu tham chiếu trỏ tới object khác. Nhiều biến có thể cùng trỏ đến một object: đó là **aliasing (nhiều tham chiếu chung một object)**.

```text
owner.source ───┐
                ├──────> ArrayList ───> MutableItem
snapshot.items ─┘                         ↑
                                         │
caller.savedItem ─────────────────────────┘
```

Nếu constructor chỉ làm `this.items = source`, caller vẫn có `source` để thêm/xóa phần tử. Nếu constructor gọi `List.copyOf(source)`, caller không thể sửa cấu trúc snapshot thông qua `source`, nhưng nếu phần tử `MutableItem` vẫn được chia sẻ, caller có thể sửa nó qua `savedItem`. Cả hai đường sửa đều phải được xét.

Hãy đặt hai câu hỏi riêng:

1. **Có ai còn giữ tham chiếu tới collection mutable mà snapshot đang dùng không?** Nếu có, phải copy collection.
2. **Có ai còn giữ tham chiếu tới các phần tử mutable trong collection không?** Nếu có, copy collection chưa đủ: cần biến phần tử thành giá trị bất biến hoặc sao chép sâu theo hợp đồng.

Đồ thị có thể là DAG, có chia sẻ các object con, hoặc thậm chí có chu trình (A tham chiếu B, B tham chiếu A). Không phải mọi domain đều cần “deep copy” mọi thứ; vấn đề cần giải quyết là **đường nào cho phép trạng thái quan sát được thay đổi**. Với đồ thị có chu trình, deep copy phải có cơ chế nhận diện các object đã sao chép để bảo toàn quan hệ và tránh đệ quy vô hạn.

## 4. Lỗi đơn giản nhất: `final` giữ tham chiếu, không đóng băng object

Tạo tệp `FinalReferenceIsMutableDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalReferenceIsMutableDemo {
    private static final class Store {
        final List<String> items;

        Store(List<String> items) {
            this.items = items;
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        Store store = new Store(source);
        source.add("B");

        System.out.println("store size=" + store.items.size());
        store.items.add("C");
        System.out.println("source size=" + source.size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac FinalReferenceIsMutableDemo.java
java FinalReferenceIsMutableDemo
```

Kết quả:

```text
store size=2
source size=3
```

Trường `items` là `final` nhưng cả `store.items` và `source` trỏ tới **cùng ArrayList**. Một phía sửa thì phía kia quan sát được thay đổi. Nếu nhiều thread sử dụng danh sách đó và một thread sửa trong khi thread khác đọc mà thiếu đồng bộ, có nguy cơ data race hoặc hành vi không được bảo đảm theo hợp đồng của collection.

Phần nào sai về thiết kế? Constructor đã **cho phép sở hữu dữ liệu tiếp tục được chia sẻ** ngoài ý muốn. Khắc phục tối thiểu là tạo bản sao collection độc lập khi xây dựng object và không để lộ đường sửa về sau.

## 5. `Collections.unmodifiableList` khác `List.copyOf`

Hai API có mục đích và phạm vi khác nhau:

`Collections.unmodifiableList(source)` tạo một **view** không cho sửa qua view. Nếu `source` vẫn được sửa, view có thể phản ánh các thay đổi đó. Nó không phải bản chụp tách rời collection nguồn.

`List.copyOf(source)` (Java 10+) trả một danh sách **không sửa được**, có nội dung là snapshot các phần tử của collection nguồn tại thời điểm tạo theo hợp đồng của API. Nó không tiếp tục phụ thuộc vào việc source thêm/xóa phần tử. Nếu nguồn đã là một danh sách không sửa được thích hợp, implementation có thể tái sử dụng instance; không nên dựa vào việc nhận được instance mới. `List.copyOf` cũng **không chấp nhận phần tử null**.

Tạo tệp `ViewVsCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsCopyDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));

        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("B");

        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot cannot be modified");
        }
    }
}
```

```bash
javac ViewVsCopyDemo.java
java ViewVsCopyDemo
```

Kết quả:

```text
view=[A, B]
snapshot=[A]
snapshot cannot be modified
```

Đây là **bất biến về cấu trúc collection**. Trong ví dụ, phần tử `String` cũng bất biến, nên snapshot không có object con mutable.

Các API tương tự: `Set.copyOf`, `Map.copyOf`, `List.of`, `Set.of`, `Map.of`. Chúng tạo/trả về collection không sửa được, nhưng cần chú ý quy tắc về `null`, phần tử trùng lặp, khóa trùng và thứ tự duyệt. Đặc biệt, đừng suy luận thứ tự duyệt `Map.copyOf` hay `Set.copyOf` sẽ giữ đúng thứ tự insertion nếu hợp đồng không bảo đảm.

**Giới hạn:** `copyOf` sao chép *tham chiếu phần tử*, không tự sao chép sâu các object được tham chiếu. Nếu một phần tử mutable còn được giữ bởi caller, snapshot vẫn quan sát được thay đổi của phần tử ấy.

## 6. Một snapshot shallow vẫn có thể thay đổi từ bên trong

Tạo tệp `ShallowCopyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ShallowCopyDemo {
    record Snapshot(List<StringBuilder> names) {
        Snapshot {
            names = List.copyOf(names);
        }
    }

    public static void main(String[] args) {
        StringBuilder element = new StringBuilder("An");
        List<StringBuilder> source = new ArrayList<>();
        source.add(element);

        Snapshot snapshot = new Snapshot(source);
        source.clear();
        element.append("-updated");

        System.out.println("snapshot size=" + snapshot.names().size());
        System.out.println("snapshot value=" + snapshot.names().get(0));
    }
}
```

```bash
javac ShallowCopyDemo.java
java ShallowCopyDemo
```

Kết quả:

```text
snapshot size=1
snapshot value=An-updated
```

Mặc dù `Snapshot` là `record` và đã dùng `List.copyOf`, phần tử bên trong vẫn là một `StringBuilder` mutable được chia sẻ. Xóa danh sách `source` không ảnh hưởng đến kích thước snapshot, nhưng sửa `element` thay đổi chuỗi mà snapshot nhìn thấy.

Bài học: một **record không tự bảo đảm bất biến sâu**, bởi các component của record có thể là mảng, collection hoặc object mutable. Tính bất biến của bản đồ object phụ thuộc vào **kiểu và đường sửa của mọi object reachable**, không chỉ tên kiểu gốc.

Trong ứng dụng thực tế, `StringBuilder` vốn không thread-safe. Nếu một thread sửa nó trong khi thread khác gọi `toString()` mà thiếu đồng bộ, kết quả còn có nguy cơ bị data race. Ví dụ này chạy tuần tự để minh họa việc alias tồn tại chắc chắn, không cố tạo một cuộc đua ngẫu nhiên.

## 7. Thiết kế một immutable object graph bằng record và copy phòng vệ

Mô hình phổ biến là **giá trị bất biến ở lá + snapshot collection ở mỗi tầng + không rò rỉ tham chiếu mutable**.

Tạo tệp `DeepImmutableSnapshotDemo.java` (JDK 17+):

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class DeepImmutableSnapshotDemo {
    record Member(String name, int score) {
        Member {
            Objects.requireNonNull(name, "name");
            if (score < 0) {
                throw new IllegalArgumentException("score");
            }
        }
    }

    record TeamSnapshot(String teamName, List<Member> members) {
        TeamSnapshot {
            Objects.requireNonNull(teamName, "teamName");
            members = List.copyOf(members);
        }
    }

    public static void main(String[] args) {
        List<Member> source = new ArrayList<>();
        source.add(new Member("An", 10));
        source.add(new Member("Binh", 20));

        TeamSnapshot snapshot = new TeamSnapshot("Core", source);
        source.add(new Member("Chi", 30));

        System.out.println("source size=" + source.size());
        System.out.println("snapshot size=" + snapshot.members().size());
        System.out.println("first=" + snapshot.members().get(0).name());

        try {
            snapshot.members().add(new Member("Dung", 40));
        } catch (UnsupportedOperationException e) {
            System.out.println("snapshot is unmodifiable");
        }
    }
}
```

```bash
javac DeepImmutableSnapshotDemo.java
java DeepImmutableSnapshotDemo
```

Kết quả:

```text
source size=3
snapshot size=2
first=An
snapshot is unmodifiable
```

**Vì sao đồ thị ở đây bất biến theo nội dung của nó?**

1. `Member` là record có thành phần `String` và `int`; `String` bất biến, `int` là giá trị nguyên thủy. Không có trường mutable được lộ.
2. `TeamSnapshot` giữ `teamName` là `String` và `members` là `List<Member>`.
3. Compact constructor của `TeamSnapshot` chuyển `members` thành `List.copyOf(members)`. Sau khi constructor xong, thay đổi cấu trúc của `source` không ảnh hưởng đến danh sách snapshot.
4. Mỗi phần tử trong danh sách là `Member` bất biến. Không có đường nào từ snapshot cho phép đổi tên hoặc điểm của một `Member`.
5. Caller nhận danh sách qua accessor của record nhưng không thể thêm/xóa phần tử của snapshot bằng API danh sách.

Một dạng công thức:

```text
Immutable parent
    + immutable fields
    + defensive copies of incoming collections
    + immutable elements recursively
    + no mutable state leaked through accessors
    = immutable observable object graph
```

Đây là nguyên tắc thiết kế, không phải phép tính tự động. Nếu thay `Member(String, int)` bằng `Member(String, List<StringBuilder>)`, bạn phải kiểm tra tiếp danh sách và từng `StringBuilder`. Nếu trả về trực tiếp một mảng nội bộ, cần sao chép cả lúc nhận lẫn lúc trả, hoặc thay mảng bằng cấu trúc bất biến phù hợp.

### 7.1. Vì sao dùng compact constructor của record có ích?

Trong `record TeamSnapshot(String teamName, List<Member> members)`, compact constructor có thể chuẩn hóa tham số `members` bằng `members = List.copyOf(members)`. Sau khi phần thân compact constructor hoàn tất bình thường, Java tự gán giá trị tham số đã chuẩn hóa cho field tương ứng của record. Điều này giúp mọi instance mới tuân theo cùng hợp đồng snapshot.

Tuy vậy, record vẫn có thể tự định nghĩa accessor/custom method làm lộ object mutable; record chỉ là cơ chế khai báo state carrier với field final, không phải công cụ kiểm định deep immutability.

### 7.2. Constructor phải kiểm tra invariant của toàn bộ trạng thái

Nếu bất biến của một số điểm là tổng điểm không âm hoặc mỗi mã thành viên là duy nhất, nên kiểm tra những điều kiện đó **trước khi công bố snapshot**. Việc validation xảy ra trên dữ liệu đã sao chép hoặc dữ liệu không thể bị người khác thay đổi trong lúc validation sẽ dễ suy luận hơn.

Đặc biệt, nếu caller truyền vào một `ArrayList` mà **thread khác đang sửa đồng thời** khi constructor gọi `List.copyOf`, bản copy không tự bảo đảm snapshot logic nhất quán: đọc một collection đang bị sửa thiếu đồng bộ vẫn có thể là data race. **Copy cần thực hiện khi nguồn ổn định, hoặc dưới cùng cơ chế đồng bộ bảo vệ nguồn.**

## 8. Collection lồng nhau: cần sao chép tại mỗi tầng mutable

Giả sử:

```java
Map<String, List<String>> permissions;
```

Nếu chỉ gọi `Map.copyOf(permissions)`, map gốc không còn được cấu trúc snapshot dùng trực tiếp; tuy nhiên các giá trị kiểu `List<String>` vẫn có thể trỏ tới **những danh sách mutable**. Caller có thể thực hiện `permissions.get("admin").add("delete")`, làm nội dung danh sách trong snapshot đổi theo.

Một cách tạo immutable graph là copy các danh sách giá trị trước, sau đó copy map:

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

static Map<String, List<String>> immutablePermissions(
        Map<String, List<String>> source) {
    Objects.requireNonNull(source);
    Map<String, List<String>> copy = new HashMap<>();
    for (var entry : source.entrySet()) {
        copy.put(
                Objects.requireNonNull(entry.getKey()),
                List.copyOf(entry.getValue()));
    }
    return Map.copyOf(copy);
}
```

Đây là **đoạn phương thức minh họa**; đặt trong một lớp Java thích hợp. Hàm này chỉ tạo deep-enough snapshot vì key và phần tử là `String` bất biến. Nếu giá trị map là `List<MutableUser>`, phải chuyển từng `MutableUser` thành kiểu bất biến hoặc snapshot riêng.

### 8.1. Chuỗi copy phải giữ một thời điểm logic khi cần invariant

Copy nested map trong khi writer khác đang cập nhật **các cấu trúc liên quan** có thể sinh kết quả trộn giữa nhiều phiên bản. Nếu đối tượng nguồn có invariant xuyên qua nhiều collection, lấy bản copy trong một vùng đồng bộ đọc, hoặc tổ chức nguồn đã là immutable snapshot rồi công bố thay thế nguyên khối.

### 8.2. Không phải mọi đồ thị đều cần deep copy đệ quy

Một đối tượng dịch vụ có thể tham chiếu logger dùng chung, bộ đếm atomic hay cache mutable. Khi đó toàn bộ graph vật lý không bất biến. Có thể vẫn thiết kế **configuration snapshot bất biến** tách khỏi các tài nguyên mutable. Hãy xác định chính xác **ranh giới dữ liệu yêu cầu bất biến**, rồi bảo vệ mọi đường truy cập *trong ranh giới ấy*. Gọi một object bất biến sâu trong khi nó vẫn lộ cache mutable là mô tả không chính xác.

## 9. Mảng, `Date` và các kiểu mutable cần sao chép phòng vệ hai chiều

Với kiểu mảng, `final byte[] data` chỉ giữ tham chiếu cuối cùng, không cấm thay `data[i]`. Nếu constructor giữ thẳng mảng đầu vào, caller sửa mảng sau khi tạo object sẽ làm dữ liệu bên trong đổi. Nếu getter trả thẳng mảng nội bộ, caller cũng sửa được từ phía ra.

Tạo tệp `DefensiveArrayDemo.java`:

```java
import java.util.Objects;

public class DefensiveArrayDemo {
    static final class Packet {
        private final byte[] payload;

        Packet(byte[] input) {
            payload = Objects.requireNonNull(input).clone();
        }

        byte[] payloadCopy() {
            return payload.clone();
        }

        int firstUnsignedByte() {
            return Byte.toUnsignedInt(payload[0]);
        }
    }

    public static void main(String[] args) {
        byte[] source = {7, 8};
        Packet packet = new Packet(source);

        source[0] = 99;
        byte[] returned = packet.payloadCopy();
        returned[0] = 55;

        System.out.println("source first=" + source[0]);
        System.out.println("returned first=" + returned[0]);
        System.out.println("packet first=" + packet.firstUnsignedByte());
    }
}
```

```bash
javac DefensiveArrayDemo.java
java DefensiveArrayDemo
```

Kết quả:

```text
source first=99
returned first=55
packet first=7
```

Hai lần `clone()` tạo quyền sở hữu riêng cho mảng. Trường `payload` vẫn trỏ tới object mảng mutable ở mức Java, nhưng lớp `Packet` không để caller có đường sửa mảng nội bộ và bản thân lớp cũng không thay đổi nó; vì vậy trạng thái của `Packet` **bất biến theo quan sát của người sử dụng** trong giao thức này.

Mảng hai chiều `byte[][]` phức tạp hơn: gọi `clone()` trên mảng ngoài chỉ copy tham chiếu tới từng mảng con. Cần clone các mảng con nếu chúng mutable, và cân nhắc đối tượng phần tử khi dùng `Object[]`.

Tương tự, `java.util.Date` là mutable; giữ tham chiếu đầu vào/đưa tham chiếu nội bộ ra getter có thể làm state thay đổi. Có thể copy `Date` cẩn thận hoặc ưu tiên các kiểu immutable trong `java.time` như `Instant`, `LocalDate` và `LocalDateTime` khi chúng đáp ứng nghiệp vụ. Không thay kiểu chỉ vì tên “Date”: còn phải xét ý nghĩa timezone và dữ liệu của domain.

## 10. Immutable object khác unmodifiable object ở điểm nào?

Một **unmodifiable interface/view** ngăn caller thao tác sửa qua một API cụ thể. Một **immutable object** bảo đảm trạng thái của chính nó không thay đổi sau khi tạo theo hợp đồng của kiểu, bất kể có bao nhiêu đường tham chiếu được cung cấp hợp lệ.

Ví dụ `Collections.unmodifiableList` chặn `view.add(x)` nhưng dữ liệu thay đổi qua danh sách gốc vẫn xuất hiện trên view. Đây là read-only view.

`List.copyOf` tạo một danh sách có cấu trúc không sửa được, tách khỏi các thay đổi cấu trúc sau đó của nguồn. Nhưng nếu phần tử mutable, graph phía dưới chưa immutable.

Một object `final class Person { private final Address address; }` chỉ bất biến sâu nếu `Address` cũng bất biến hoặc được copy/bao bọc để không ai còn đường sửa. `final class` ngăn kế thừa lớp, không làm object con bất biến.

Đánh giá tính bất biến là đánh giá **cả kiểu, các đường gán tham chiếu và API công khai**, không chỉ xem có các từ khóa `final` hay `unmodifiable` hay không.

## 11. Bất biến và thread safety: mối quan hệ chính xác

Đối tượng bất biến được xây dựng đúng cách là một công cụ mạnh của **thread safety**, vì nhiều reader có thể đọc mà không cần đồng bộ để bảo vệ chống lại việc object bị sửa — miễn là chúng nhận được object hợp lệ qua một con đường công bố có hợp đồng rõ.

Nhưng cần phân biệt:

1. **Object đã bất biến?** Sau constructor, state nào còn được phép thay đổi?
2. **Object đã được khởi tạo đúng cách?** Có để lộ `this` trong constructor không? Có trả ra đối tượng nửa khởi tạo không?
3. **Tham chiếu đã được công bố an toàn?** Thread khác làm sao nhận object? Qua `volatile`, khóa, concurrent queue, `Thread.start()`, class initialization, hoặc cơ chế chuẩn khác?
4. **Các reader đọc cùng một snapshot?** Nếu một phép tính cần nhiều trường, reader có lấy cùng một object snapshot một lần không?
5. **Có tài nguyên mutable bên ngoài ranh giới snapshot?** Nếu có, phần việc đó vẫn phải được đồng bộ theo giao thức riêng.

### 11.1. `final` có bảo đảm khởi tạo đặc biệt, nhưng không thay safe publication toàn diện

Java Memory Model có bảo đảm đặc biệt đối với giá trị các **instance final fields** của đối tượng được khởi tạo đúng cách: khi constructor hoàn tất mà không để `this` thoát sớm, giá trị final đã khởi tạo có ngữ nghĩa visibility riêng. Đây là nền tảng để các immutable value object hoạt động đáng tin cậy.

Dẫu vậy, chỉ dựa vào final-field guarantee không tạo ra một giao thức chia sẻ đầy đủ: nó không bảo đảm reader nhận tham chiếu vào thời điểm cần thiết, không bảo vệ trạng thái non-final/mutable, và không thay thế các quan hệ đồng bộ cần thiết cho cập nhật sau khởi tạo. Safe publication qua một cơ chế rõ ràng giúp chứng minh trọn vẹn hơn.

Không bắt đầu thread ngay trong constructor để đưa `this` ra ngoài rồi mặc định final fields đã hoàn thành; đó là **this escape**, có thể làm thread khác quan sát state chưa khởi tạo.

### 11.2. Mỗi lần thay snapshot cần công bố nguyên tử

Mô hình thường dùng:

```text
Reader A ---snapshot v1---> [immutable graph v1]
Reader B ---snapshot v1---> [immutable graph v1]

Writer: tạo graph v2 hoàn chỉnh
        validate
        atomic publication (đổi một tham chiếu)

Reader C ---snapshot v2---> [immutable graph v2]
Reader A vẫn giữ v1 hợp lệ, không bị sửa sau lưng.
```

Vì hai graph không bị sửa sau khi công bố, reader lấy được v1 vẫn sử dụng v1 ổn định; reader lấy v2 dùng trạng thái mới. Điểm cần điều phối là **tham chiếu nào được công bố**, không phải khóa từng phép đọc mọi trường con của một graph mutable.

## 12. Ví dụ cập nhật snapshot nguyên tử từ nhiều writer

Một đồ thị bất biến cũng giúp xử lý **cập nhật nhiều trường phải đi cùng nhau**, ví dụ hai số dư có tổng luôn bằng 100. Mỗi writer tạo snapshot mới hợp lệ rồi thực hiện cập nhật atomic ở cấp tham chiếu. Reader lấy tham chiếu **một lần** để không ghép hai thế hệ khác nhau.

Tạo tệp `AtomicImmutableStateDemo.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicImmutableStateDemo {
    record Balances(int left, int right) {
        Balances {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("invalid balances");
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Balances> current =
                new AtomicReference<>(new Balances(80, 20));

        Runnable moveOne = () -> {
            for (int i = 0; i < 10; i++) {
                current.updateAndGet(old ->
                        new Balances(old.left() - 1, old.right() + 1));
            }
        };

        Thread a = new Thread(moveOne, "writer-a");
        Thread b = new Thread(moveOne, "writer-b");
        a.start();
        b.start();
        a.join();
        b.join();

        Balances snapshot = current.get();
        System.out.println("left=" + snapshot.left());
        System.out.println("right=" + snapshot.right());
        System.out.println("total=" + (snapshot.left() + snapshot.right()));
    }
}
```

```bash
javac AtomicImmutableStateDemo.java
java AtomicImmutableStateDemo
```

Kết quả:

```text
left=60
right=40
total=100
```

Hai writer mỗi người thực hiện 10 lần chuyển một đơn vị, tổng cộng chuyển 20. `AtomicReference.updateAndGet` có thể thử lại lambda khi các writer cùng cập nhật; mọi lần thành công đều chuyển từ một snapshot hợp lệ sang snapshot hợp lệ khác. Không có một object `Balances` nào bị sửa tại chỗ.

**Điểm cần lưu ý:** hàm truyền cho `updateAndGet` có thể được thực thi **nhiều lần cho một cập nhật thành công** do CAS retry. Vì vậy không ghi log mang side effect không thể lặp, gọi dịch vụ ngoài, gửi thông điệp hay trừ tài khoản thật *bên trong lambda*. Chỉ tính state kế tiếp từ state cũ; các side effect phải có cơ chế điều phối/transaction riêng.

`left + right == 100` là invariant nội bộ của record, nhưng arithmetic int có thể overflow trong ứng dụng lớn. Ví dụ dùng các số nhỏ; nếu domain có số lớn, cần dùng kiểm tra tràn `Math.addExact` hoặc kiểu số phù hợp và validation tổng thể.

**Vấn đề khi đọc:** làm thế này là sai nếu cần snapshot đồng nhất:

```java
int left = current.get().left();
int right = current.get().right();
```

Đây là **đoạn minh họa**, giả định có biến `current` như ví dụ trên. Hai lần `get()` có thể thấy v1 và v2 khác nhau, dù cả hai snapshot riêng đều hợp lệ. Thay bằng:

```java
Balances snapshot = current.get();
int left = snapshot.left();
int right = snapshot.right();
```

Lấy cùng snapshot một lần cho toàn bộ phép tính. `AtomicReference` giải quyết tranh chấp công bố, còn **đối tượng snapshot bất biến** bảo đảm dữ liệu bên trong một phiên bản không đổi.

## 13. Đồ thị bất biến không giải quyết mọi vấn đề concurrency

Một immutable graph giúp chia sẻ dữ liệu đọc an toàn, nhưng **không tự giải quyết** các vấn đề sau:

- **Lost update giữa writer:** nếu writer A và B cùng đọc v1, tính hai bản v2A/v2B rồi mỗi bên gọi `volatileReference = newValue`, một thay đổi có thể ghi đè thay đổi kia. Nếu update phụ thuộc state cũ, dùng CAS/updateAndGet hoặc lock.
- **Thao tác xuyên nhiều tham chiếu:** nếu hai biến `currentConfig` và `currentRules` phải đổi đồng thời, cập nhật riêng từng `volatile` vẫn có thể cho reader tổ hợp sai. Gộp chúng trong **một snapshot gốc**.
- **I/O và tài nguyên ngoài JVM:** snapshot bộ nhớ không tự biến thao tác ghi file/database/network thành transaction nguyên tử. Cần cơ chế của hệ thống lưu trữ/giao tiếp.
- **Chi phí copy:** tạo snapshot mới có thể tốn CPU và bộ nhớ nếu object graph lớn. Có thể dùng persistent data structures chia sẻ cấu trúc bất biến, copy-on-write ở cấp phù hợp hoặc thiết kế domain nhỏ hơn, nhưng phải đo lường.
- **Tác dụng phụ từ accessor/callback:** một “immutable object” có method trả về socket, mutable map hay phát sự kiện tùy thời điểm chưa chắc có hành vi thuần; tách dữ liệu bất biến khỏi dịch vụ có side effect.
- **Object con có mutable cache:** nếu graph có `HashMap` cache được cập nhật ngầm, graph không còn bất biến sâu theo nghĩa vật lý. Nếu cache chỉ là chi tiết ẩn, bản thân cache vẫn phải thread-safe và không làm thay đổi giá trị quan sát được theo hợp đồng object.
- **Lifecycle của snapshot:** giữ vô hạn tham chiếu tới hàng triệu snapshot cũ có thể tốn bộ nhớ. Immutable không đồng nghĩa không cần chính sách vòng đời, thu hồi tham chiếu và kiểm soát bộ nhớ.

Khi dữ liệu thay đổi liên tục với tần suất cao và graph lớn, có thể phù hợp hơn khi dùng một trạng thái mutable được bảo vệ bằng khóa. Không có một lựa chọn duy nhất cho mọi workload.

## 14. Các lỗi thiết kế hay gặp

### 14.1. Dùng `final` ở mọi trường rồi tuyên bố thread-safe

```java
final class Registry {
    private final java.util.Map<String, String> values =
            new java.util.HashMap<>();

    void put(String key, String value) {
        values.put(key, value);
    }
}
```

Đây là lớp minh họa. Trường `values` không bị gán lại, nhưng `HashMap` vẫn mutable và không hỗ trợ ghi/đọc đồng thời không đồng bộ theo hợp đồng. Cần khóa, concurrent map phù hợp, hoặc thay tham chiếu tới một map snapshot bất biến; lựa chọn phụ thuộc invariant nhiều trường hay chỉ hoạt động theo key.

### 14.2. Dùng `List.copyOf` nhưng phần tử vẫn mutable

```java
List<StringBuilder> snapshot = List.copyOf(source);
```

Snapshot cố định cấu trúc danh sách nhưng các `StringBuilder` vẫn có thể đổi. Chuyển phần tử sang `String`/record bất biến, hoặc copy sâu theo nhu cầu.

### 14.3. Constructor copy input nhưng getter trả lại nội bộ mutable

```java
class Payload {
    private final byte[] bytes;

    Payload(byte[] input) {
        bytes = input.clone();
    }

    byte[] getBytes() {
        return bytes; // Rò rỉ mảng nội bộ.
    }
}
```

Lớp minh họa này có phòng vệ **đầu vào** nhưng không phòng vệ **đầu ra**. Caller sửa `getBytes()[0]` sẽ thay dữ liệu bên trong. Sửa bằng `return bytes.clone()` hoặc API truy cập giá trị không cho sửa.

### 14.4. Bọc `Collections.unmodifiableMap` nhưng giữ map gốc và tiếp tục sửa

Một unmodifiable view không tạo snapshot; nếu object gốc tiếp tục thay đổi, reader thấy dữ liệu thay đổi theo. Dùng `Map.copyOf` trên nguồn ổn định (và copy các giá trị mutable lồng nhau) khi cần snapshot bất biến.

### 14.5. Gộp snapshot nhưng vẫn đọc nhiều lần tham chiếu mutable

```java
String host = config.get().host();
int port = config.get().port();
```

Nếu `config` được thay nguyên snapshot giữa hai `get`, caller có thể lấy host v1 và port v2. Lấy `Config snapshot = config.get()` một lần, rồi đọc mọi trường cần thiết từ cùng snapshot.

### 14.6. Tạo immutable object từ một collection đang bị sửa đồng thời

Dùng `List.copyOf(sharedArrayList)` trong khi một thread khác gọi `sharedArrayList.add(...)` không tạo bảo đảm snapshot nhất quán và không biến bản đọc source thành an toàn. Cần nguồn ổn định, lock chia sẻ, hoặc một dữ liệu nguồn đã là immutable snapshot.

### 14.7. Quên validation và exception trước khi công bố

Nếu constructor/factory cho phép tạo một snapshot có invariant sai hoặc để con trỏ tới object đang khởi tạo thoát ra trước khi hoàn tất, không thể dựa vào từ khóa `final` để cứu hợp đồng. Hãy tạo bản hoàn chỉnh, validation, rồi mới công bố tham chiếu sau khi constructor trả về thành công.

## 15. Chiến lược lựa chọn trong ứng dụng Java

| Tình huống | Thiết kế xuất phát phù hợp | Điểm cần kiểm chứng |
| --- | --- | --- |
| Value object nhỏ, chỉ đọc sau khi tạo | Record/class với final fields, thành phần bất biến | Không chứa tham chiếu mutable bị rò rỉ |
| Cấu hình có danh sách/map lồng nhau | Copy phòng vệ từng tầng mutable, immutable phần tử | Đường alias từ caller và nested collections |
| Cần lưu một mảng binary nhưng không cho sửa từ ngoài | Clone input và clone output | Mảng lồng nhau cần copy sâu hơn |
| Cấu hình được thay theo phiên bản, nhiều reader | Một immutable root snapshot + `volatile` hoặc `AtomicReference` | Reader lấy tham chiếu một lần; có nhiều writer hay không |
| Nhiều writer biến đổi state dựa vào bản cũ | CAS/updateAndGet trên immutable snapshot hoặc lock | Lambda retry phải không có side effect |
| State rất lớn, thay đổi liên tục | Mutable state có lock phù hợp hoặc cấu trúc chia sẻ bất biến | Hiệu năng, invariant, nguy cơ deadlock và chi phí copy |
| Giao dữ liệu qua queue giữa các worker | Immutable message + `BlockingQueue` | Công bố an toàn, không sửa message sau khi gửi |
| Tham chiếu tới tài nguyên có vòng đời như socket | Tách tài nguyên mutable khỏi immutable config | Quyền sở hữu, đóng tài nguyên và phối hợp thread |

Hãy chọn dựa trên **đơn vị trạng thái phải nhất quán**, tần suất đọc/ghi, kích thước dữ liệu và khả năng kiểm chứng hợp đồng. Một lớp bất biến nhỏ thường dễ kiểm thử và suy luận hơn một object mutable được nhiều thread chia sẻ; nhưng chi phí tạo snapshot liên tục có thể quan trọng khi graph lớn.

## 16. Tự kiểm tra

**Câu 1.** `final List<MutablePerson> people` có làm object chứa nó bất biến sâu không?

**Trả lời:** Không. `final` chỉ giữ tham chiếu. Collection có thể mutable; ngay cả khi không sửa được cấu trúc collection, từng `MutablePerson` vẫn có thể bị sửa qua alias khác. Cần copy và/hoặc chuyển phần tử thành giá trị bất biến theo hợp đồng.

**Câu 2.** `Collections.unmodifiableList(source)` và `List.copyOf(source)` khác nhau gì khi `source` được thêm phần tử?

**Trả lời:** View không sửa được thường phản ánh thay đổi của `source`; `List.copyOf` cung cấp snapshot cấu trúc tách khỏi những sửa đổi cấu trúc sau đó của source. Cả hai đều không tự đóng băng object phần tử mutable.

**Câu 3.** Record `record Response(List<StringBuilder> values) {}` có bất biến sâu không?

**Trả lời:** Không. Record có component field final nhưng danh sách và `StringBuilder` có thể mutable. Cần copy cấu trúc và thay phần tử bằng kiểu bất biến hoặc tạo bản sao phù hợp.

**Câu 4.** Nếu constructor đã clone `byte[]` input, có thể trả thẳng `byte[]` field qua getter không?

**Trả lời:** Không khi muốn giữ bất biến theo quan sát. Getter trả tham chiếu mutable cho caller sửa phần tử bên trong; phải copy ở đầu ra hoặc cung cấp accessor không cho sửa.

**Câu 5.** Hai writer cùng tạo bản config mới từ cùng bản cũ rồi gán một trường volatile. Điều gì có thể xảy ra?

**Trả lời:** Mỗi phép gán tham chiếu là một lần công bố, nhưng thay đổi logic của một writer có thể bị writer khác ghi đè. Cần CAS/updateAndGet hoặc khóa khi update phụ thuộc state cũ.

**Câu 6.** Một record bất biến có hai trường tương quan. Reader gọi hai lần `current.get()` để lấy mỗi trường. Có bảo đảm lấy hai trường từ cùng thế hệ không?

**Trả lời:** Không. Writer có thể thay root snapshot ở giữa. Reader phải lấy một tham chiếu snapshot duy nhất rồi đọc cả hai trường từ snapshot đó.

**Câu 7.** Vì sao copy `Map<String, List<String>>` một tầng bằng `Map.copyOf` chưa bảo đảm immutable graph?

**Trả lời:** Map snapshot giữ các tham chiếu tới danh sách giá trị; nếu danh sách giá trị mutable, caller có thể sửa chúng. Cần copy danh sách tại từng value, rồi mới copy map. Vì các phần tử là `String`, khi đó graph giá trị không còn phần tử mutable.

**Câu 8.** Bất biến object có khiến mọi thread tự động nhận tham chiếu tới object ấy không?

**Trả lời:** Không. Tính bất biến giải quyết việc state không bị thay đổi sau tạo. Đường **công bố** và chuyển tham chiếu cần một hợp đồng đồng bộ riêng khi ứng dụng yêu cầu khả năng nhìn thấy và tiến trình nhận dữ liệu chắc chắn.

## 17. Tổng hợp

**Immutability** giúp trạng thái được chia sẻ qua các thread ổn định và giảm nhu cầu khóa khi đọc. Nhưng tính bất biến chỉ đáng tin khi xem xét **toàn bộ đồ thị trạng thái quan sát được**: trường final, collection không sửa được, phần tử bên trong, mảng, các đối tượng con và mọi alias còn đường sửa.

Để tạo một **immutable object graph** trong Java, hãy tạo trạng thái đầy đủ trong constructor/factory, kiểm tra invariant, sao chép phòng vệ tại mọi biên mutable, chỉ giữ hoặc trả ra những giá trị không thể bị sửa qua alias khác, và công bố một root snapshot hoàn chỉnh bằng cơ chế bộ nhớ phù hợp. Khi state cần thay đổi, tạo phiên bản mới và thay **một tham chiếu** (hoặc dùng khóa để giữ nhất quán). Một snapshot bất biến không tự loại bỏ việc quản lý nhiều writer, I/O, hủy task hay tài nguyên ngoài JVM, nhưng giúp phần dữ liệu chia sẻ trở nên đơn giản và đáng tin hơn.
