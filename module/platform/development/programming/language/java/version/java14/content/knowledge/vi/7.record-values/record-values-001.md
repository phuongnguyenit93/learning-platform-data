# Bất biến của tham chiếu thành phần và giới hạn bất biến sâu trong Java record

> **Phạm vi:** Đây là bài về **giá trị record** trong chủ đề Java 14. `record` từng được thử nghiệm trong Java 14, nhưng đã là tính năng **chính thức từ Java 16** và tiếp tục được hỗ trợ ở Java hiện hành. Bài chỉ sử dụng quy tắc ổn định và ví dụ **Java 17+**, không dựa vào chế độ preview cũ. Trọng tâm là phân biệt **field tham chiếu `final`** của record với **đối tượng mutable** mà field đó đang trỏ tới, đồng thời thiết kế dữ liệu có bất biến sâu khi thực sự cần.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao mỗi component của record có **field `private final`** nhưng một record vẫn có thể quan sát thấy dữ liệu thay đổi sau khi khởi tạo.
2. Phân biệt **bất biến nông (shallow immutability)**, **bất biến sâu (deep immutability)**, **unmodifiable view** và **bản sao phòng vệ (defensive copy)**.
3. Chỉ ra hai đường rò rỉ tham chiếu mutable: **đầu vào constructor** và **đầu ra accessor**.
4. Thiết kế record chứa array hoặc collection với cách sao chép phù hợp; hiểu giới hạn của `clone()`, `List.copyOf()` và `Map.copyOf()`.
5. Giải thích ảnh hưởng của component mutable đối với `equals()`, `hashCode()`, khóa `HashMap`, đa luồng và hợp đồng giá trị.
6. Viết và kiểm chứng các chương trình Java 17+ để quan sát chính xác sự khác biệt giữa record lưu tham chiếu trực tiếp và record bảo vệ dữ liệu.

**Nguyên tắc:** Cú pháp `record` cho bạn một khuôn dữ liệu có các **tham chiếu cố định**, không tự tạo ra một **đồ thị đối tượng bất biến sâu**.

## 2. Java bảo đảm điều gì cho một record?

Xét khai báo:

```java
record Shipment(int id, int[] quantities, String label) {}
```

Theo **JLS `8.10.3**, compiler khai báo ngầm một field cho mỗi component:

```java
// MÔ HÌNH MINH HỌA; không phải mã nguồn record được sinh nguyên văn.
private final int id;
private final int[] quantities;
private final String label;
```

Các field nằm **trong chính `Shipment`**, có phạm vi `private` và là `final`. Compiler cũng cung cấp canonical constructor và các accessor như `id()`, `quantities()`, `label()`; mặc định accessor trả về **giá trị của field tương ứng**. Với kiểu tham chiếu như `int[]`, giá trị được trả là một **tham chiếu tới đối tượng**, không tự động là bản sao.

Ba ý phải phân biệt rõ:

| Khái niệm | Điều được đảm bảo | Điều **không** được đảm bảo |
| --- | --- | --- |
| `final` ở **record class** | Không thể tạo subclass của record. | Không chứng minh các component bất biến sâu. |
| `private final` ở **component field** | Sau khi constructor khởi tạo, field không thể được gán lại theo cách thông thường. | Array, list, map hoặc object được trỏ tới không nhất thiết bất biến. |
| Accessor mặc định như `quantities()` | Trả đúng giá trị component đã lưu. | Không tự copy array, collection hoặc mutable object. |

Đối với component **primitive** như `int id`, giá trị của field không thể thay đổi sau khi tạo record. Đối với `String label`, `String` vốn là kiểu bất biến; tham chiếu cố định tới một `String` có thể an toàn để chia sẻ. Đối với `int[] quantities`, field tham chiếu vẫn trỏ tới cùng array nhưng **phần tử array có thể bị sửa**.

Hình dung:

```text
Shipment object
 +-------------------------------+
 | id = 7                        |  immutable primitive value
 | quantities (final reference) -+----> int[] {10, 20}
 | label (final reference) ------+----> String "ready"
 +-------------------------------+
                                         |
                                 phần tử int[] có thể đổi
```

**Bất biến nông**: Các field component không bị gán lại nhưng những đối tượng được tham chiếu còn có thể mutable. **Bất biến sâu**: Không có đường cập nhật trạng thái quan sát được trong toàn bộ đồ thị giá trị mà record công bố, kể cả các object nằm trong collection lồng nhau. Để đạt bất biến sâu, cần thiết kế **kiểu component** và **quyền sở hữu tham chiếu** phù hợp, không chỉ dựa vào `record`.

## 3. Ví dụ đầu tiên: record có tham chiếu `final` nhưng dữ liệu vẫn đổi

Lưu dưới tên **`ShallowRecordDemo.java`**:

```java
import java.util.Arrays;

public class ShallowRecordDemo {
    record Packet(int id, int[] bytes, StringBuilder description) {}

    public static void main(String[] args) {
        int[] input = {1, 2};
        StringBuilder text = new StringBuilder("A");

        Packet packet = new Packet(7, input, text);

        // Đổi dữ liệu qua tham chiếu bên ngoài constructor.
        input[0] = 9;
        text.append("B");

        // Đổi dữ liệu qua tham chiếu do accessor mặc định trả về.
        packet.bytes()[1] = 8;
        packet.description().append("C");

        System.out.println("id=" + packet.id());
        System.out.println("bytes=" + Arrays.toString(packet.bytes()));
        System.out.println("description=" + packet.description());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ShallowRecordDemo.java
java ShallowRecordDemo
```

**Stdout:**

```text
id=7
bytes=[9, 8]
description=ABC
```

Phân tích:

- `packet.id()` vẫn là `7`: component primitive `int` không bị thay đổi.
- `packet.bytes()` trả tham chiếu tới **chính array `input`**, nên sửa qua `input` hoặc qua accessor đều tác động tới cùng vùng dữ liệu.
- `packet.description()` trả tham chiếu tới đối tượng `StringBuilder` mutable; cả `text.append("B")` và `packet.description().append("C")` đều sửa cùng đối tượng.
- Không có dòng nào gán lại field `bytes` hay `description`. Java vẫn tuân thủ quy tắc `final`; **đối tượng được trỏ tới** mới là phần bị thay đổi.

`StringBuilder` ở ví dụ chỉ để biểu diễn một object mutable còn được dùng trong Java hiện nay. Nó không có cùng hợp đồng bất biến với `String`.

## 4. Hai cửa cần đóng khi làm defensive copy

Đối với một mutable component, cần tự hỏi **ai còn giữ tham chiếu tới object bên trong record**:

1. **Constructor ingress (đường vào):** Nếu record lưu nguyên tham chiếu đầu vào, người gọi vẫn có thể sửa object sau khi tạo record.
2. **Accessor egress (đường ra):** Nếu accessor trả nguyên tham chiếu nội bộ, người gọi có thể sửa object từ bên ngoài, ngay cả khi constructor đã copy đầu vào.

Một kiểu record có array nên cân nhắc **copy ở cả hai chiều** nếu muốn cô lập dữ liệu. Tuy nhiên, với array còn thêm vấn đề **bình đẳng và mã băm** sẽ được phân tích ở phần 6.

### 4.1. Vì sao chỉ copy ở constructor là chưa đủ?

```java
// Đoạn khai báo độc lập, chưa có main.
record IngressOnly(int[] numbers) {
    IngressOnly {
        numbers = numbers.clone();
    }
}
```

Trong **compact canonical constructor**, tham số `numbers` được thay bằng array sao chép. Kết thúc thân constructor, compiler sẽ gán tham số đã xử lý cho component field. Như vậy sửa array đầu vào sau khi tạo record **không ảnh hưởng** tới field.

Nhưng accessor `numbers()` **được sinh mặc định**, nên vẫn trả tham chiếu tới array đang được record giữ. Người gọi có thể làm `obj.numbers()[0] = 999;`, và từ đó sửa dữ liệu bên trong record. Muốn tránh rò rỉ, cần một accessor tường minh trả **bản sao**.

### 4.2. Bản record có phòng vệ hai chiều và so sánh theo nội dung

Lưu dưới tên **`DefensiveArrayRecordDemo.java`**:

```java
import java.util.Arrays;

public class DefensiveArrayRecordDemo {
    record IngressOnly(int[] values) {
        IngressOnly {
            values = values.clone();
        }
    }

    record Snapshot(int[] values) {
        Snapshot {
            values = values.clone();
        }

        // Accessor tường minh: không để lộ array nội bộ.
        public int[] values() {
            return values.clone();
        }

        // Array có equals() mặc định theo danh tính;
        // so sánh nội dung cần thực hiện tường minh.
        @Override
        public boolean equals(Object other) {
            return other instanceof Snapshot that
                    && Arrays.equals(values, that.values);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }

        @Override
        public String toString() {
            return "Snapshot" + Arrays.toString(values);
        }
    }

    public static void main(String[] args) {
        int[] firstSource = {3, 4};
        IngressOnly halfSafe = new IngressOnly(firstSource);
        firstSource[0] = 8;       // không sửa array được lưu
        halfSafe.values()[1] = 9; // lại sửa array từ accessor
        System.out.println("ingress-only="
                + Arrays.toString(halfSafe.values()));

        int[] secondSource = {3, 4};
        Snapshot safe = new Snapshot(secondSource);
        secondSource[0] = 8;
        int[] exposed = safe.values();
        exposed[1] = 9;

        Snapshot sameContent = new Snapshot(new int[]{3, 4});
        Snapshot copied = new Snapshot(safe.values());

        System.out.println("snapshot=" + Arrays.toString(safe.values()));
        System.out.println("equals=" + safe.equals(sameContent));
        System.out.println("hash-equal="
                + (safe.hashCode() == sameContent.hashCode()));
        System.out.println("copy-invariant=" + safe.equals(copied));
        System.out.println("text=" + safe);
    }
}
```

```bash
javac --release 17 DefensiveArrayRecordDemo.java
java DefensiveArrayRecordDemo
```

**Stdout:**

```text
ingress-only=[3, 9]
snapshot=[3, 4]
equals=true
hash-equal=true
copy-invariant=true
text=Snapshot[3, 4]
```

Diễn giải:

- `IngressOnly` đã cô lập đầu vào, nhưng để lộ đầu ra. Array nội bộ bị đổi từ `[3, 4]` thành `[3, 9]`.
- `Snapshot` sao chép array cả ở compact constructor và accessor. Đổi `secondSource` hoặc `exposed` không đổi nội dung record.
- `Arrays.equals` so nội dung mảng, `Arrays.hashCode` tạo mã băm tương thích với phép so sánh nội dung, còn `Arrays.toString` chỉ dùng để xuất chuỗi dễ đọc.
- `safe.equals(copied)` được giữ `true`: tạo một record khác từ các giá trị accessor phải bảo toàn phép bằng nhau theo **copy invariant** trong hợp đồng `java.lang.Record`.
- Ví dụ dùng array **một chiều chứa primitive**. Với `Object[]` chứa object mutable, `clone()` chỉ copy lớp array ngoài; các object phần tử vẫn dùng chung. Với array nhiều chiều, mỗi array con cũng cần được xem xét riêng.

**Chi tiết quan trọng:** Nếu dùng array component và chỉ thêm `clone()` ở constructor/accessor nhưng vẫn giữ `equals` tự sinh, các instance có nội dung array giống nhau thường vẫn **không bằng nhau**, vì `Object.equals` của array so **danh tính tham chiếu**. Hơn nữa, việc clone trong cả constructor và accessor có thể phá vỡ **copy invariant** nếu không điều chỉnh `equals/hashCode` tương ứng. Vì vậy, khi cần ngữ nghĩa giá trị, hãy cân nhắc đổi thành immutable collection hoặc triển khai đầy đủ phép so sánh và hash code theo nội dung, như `Snapshot`.

**Không gắn `@Override` vào accessor `values()` tường minh:** accessor ấy thay implementation compiler lẽ ra sinh, nhưng không phải override một phương thức cùng chữ ký ở superclass. Chỉ dùng `@Override` cho `equals`, `hashCode`, `toString` trong ví dụ.

## 5. Collection: phân biệt unmodifiable view và snapshot

Một record có component `List<String>` cũng lưu **tham chiếu tới List**, không tự copy.

```java
// Mô tả ngắn để phân tích:
record Tags(List<String> items) {}
```

Nếu truyền vào một `ArrayList` mutable và sau đó `add`/`remove` ở bên ngoài, `Tags.items()` phản ánh cùng thay đổi. Cách thiết kế phụ thuộc hợp đồng bạn muốn:

| Cách xử lý đầu vào | Có copy cấu trúc collection? | Có thể sửa danh sách qua accessor? | Thay đổi từ collection gốc có phản ánh? |
| --- | --- | --- | --- |
| Lưu nguyên `input` | Không | Có, nếu `input` mutable | Có |
| `Collections.unmodifiableList(input)` | **Không**, chỉ tạo view chỉ đọc | Không qua view | **Có** khi `input` bị sửa |
| `List.copyOf(input)` | Tạo **snapshot của phần tử** theo hợp đồng (có thể tái sử dụng một list vốn đã unmodifiable) | Không | Không phản ánh thay đổi cấu trúc tiếp theo của `input` |
| `Collections.unmodifiableList(new ArrayList<>(input))` | Có, copy cấu trúc rồi bọc | Không qua view | Không phản ánh thay đổi cấu trúc tiếp theo của `input` |

Mọi phương án copy ở đây đều **nông đối với phần tử**: nếu phần tử là một object mutable, thay đổi **nội dung object đó** vẫn quan sát được từ cả nơi ban đầu và nơi chứa bản sao.

`List.copyOf` được khuyến nghị khi muốn danh sách **không sửa được**, không chứa `null` và không cần giữ concrete implementation của collection đầu vào. Phương thức này **từ chối collection `null` hoặc phần tử `null`** bằng `NullPointerException`. Nếu miền dữ liệu cần chứa `null`, phải chọn và ghi rõ chính sách xử lý dữ liệu thay vì giả định `List.copyOf` sẽ giữ nguyên.

### 5.1. Ví dụ trực tiếp: view phản chiếu thay đổi, snapshot thì không

Lưu dưới tên **`CollectionSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CollectionSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("java"));

        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("record");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);
    }
}
```

```bash
javac --release 17 CollectionSnapshotDemo.java
java CollectionSnapshotDemo
```

**Stdout:**

```text
source=[java, record]
view=[java, record]
snapshot=[java]
```

`Collections.unmodifiableList(source)` chỉ chặn lệnh sửa **đi qua view**; nó không khóa source gốc. `List.copyOf(source)` tạo một kết quả có danh sách phần tử ổn định trước **những chỉnh sửa cấu trúc tiếp theo của source**, theo hợp đồng API. Hai khái niệm đều đang được sử dụng trong Java hiện nay, nhưng dùng cho mục đích khác nhau.

### 5.2. Record bảo vệ collection ở constructor

Lưu dưới tên **`ListRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListRecordDemo {
    record Names(List<String> values) {
        Names {
            values = List.copyOf(values);
        }
    }

    static final class MutableTask {
        private String status;

        MutableTask(String status) {
            this.status = status;
        }

        String status() {
            return status;
        }

        void setStatus(String newStatus) {
            status = newStatus;
        }
    }

    record Tasks(List<MutableTask> entries) {
        Tasks {
            entries = List.copyOf(entries);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("Java"));
        Names names = new Names(source);

        source.add("Records");
        System.out.println("names=" + names.values());

        try {
            names.values().add("Other");
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable=true");
        }

        System.out.println("equal-names="
                + names.equals(new Names(List.of("Java"))));

        MutableTask task = new MutableTask("open");
        Tasks tasks = new Tasks(List.of(task));
        task.setStatus("closed");
        System.out.println("nested-status="
                + tasks.entries().get(0).status());
    }
}
```

```bash
javac --release 17 ListRecordDemo.java
java ListRecordDemo
```

**Stdout:**

```text
names=[Java]
unmodifiable=true
equal-names=true
nested-status=closed
```

Ở đây `Names` có thể dùng accessor mặc định `values()` an toàn đối với việc sửa **cấu trúc list**, vì constructor đã đặt một unmodifiable list vào component field. `String` là immutable, vì vậy đây là mô hình thuận tiện cho dữ liệu có ngữ nghĩa giá trị.

Ngược lại, `Tasks` dùng `List.copyOf` nhưng phần tử `MutableTask` có trạng thái `status` thay đổi được. Danh sách không sửa được nhưng `task.setStatus("closed")` vẫn làm trạng thái mà record quan sát được đổi. Đó là **giới hạn bất biến sâu**, không phải lỗi của `List.copyOf`.

### 5.3. `Map.copyOf` và `Set.copyOf` cũng không copy sâu

Khi lưu collection khác:

```java
import java.util.Map;
import java.util.Set;

record Configuration(Map<String, String> properties, Set<String> flags) {
    Configuration {
        properties = Map.copyOf(properties);
        flags = Set.copyOf(flags);
    }
}
```

Đoạn này là **khai báo kiểu**, không phải chương trình có `main`. `Map.copyOf` và `Set.copyOf` trả collection không cho sửa cấu trúc; chúng không tự clone object mutable trong key/value/element. Các factory này từ chối `null` theo hợp đồng tương ứng. Với mutable keys, giá trị băm hoặc so sánh khóa có thể đổi và gây lỗi truy cập map. Nên dùng key immutable, không chỉ unmodifiable map.

## 6. Record equality và hash code: tại sao mutable component nguy hiểm?

Khi không ghi đè, compiler sinh `equals(Object)` và `hashCode()` dựa trên **component fields**. Với component tham chiếu, phép bằng nhau dựa theo `Objects.equals` của component tương ứng. Điều đó dẫn tới các hành vi khác nhau:

- `String`: có `equals/hashCode` theo nội dung và là immutable → thường thích hợp cho record dạng giá trị.
- `List<String>`: `List.equals` so theo các phần tử → hai list cùng chuỗi có thể bằng nhau; nhưng nếu list thay đổi, equality/hash code của record cũng có thể đổi.
- `int[]`: array dùng `Object.equals` theo **danh tính tham chiếu**, không tự so từng phần tử → hai record có array giống nội dung chưa chắc bằng nhau.
- Object mutable do ứng dụng định nghĩa: kết quả phụ thuộc hợp đồng `equals/hashCode` của object và trạng thái hiện tại.

### 6.1. Hai array có cùng phần tử không làm record tự bằng nhau

Lưu dưới tên **`RecordArrayEqualityDemo.java`**:

```java
public class RecordArrayEqualityDemo {
    record RawArray(int[] data) {}
    record Numbers(java.util.List<Integer> data) {
        Numbers {
            data = java.util.List.copyOf(data);
        }
    }

    public static void main(String[] args) {
        RawArray a = new RawArray(new int[]{1, 2});
        RawArray b = new RawArray(new int[]{1, 2});
        System.out.println("arrays-equal=" + a.equals(b));

        Numbers x = new Numbers(java.util.List.of(1, 2));
        Numbers y = new Numbers(java.util.List.of(1, 2));
        System.out.println("lists-equal=" + x.equals(y));
    }
}
```

```bash
javac --release 17 RecordArrayEqualityDemo.java
java RecordArrayEqualityDemo
```

**Stdout:**

```text
arrays-equal=false
lists-equal=true
```

**Giải thích:** Hai biểu thức `new int[]{1, 2}` tạo **hai array object khác nhau**; implicit `equals` của record không biến array thành so sánh phần tử. Ngược lại, hai unmodifiable list có cùng giá trị `Integer` được so sánh theo nội dung list, nên hai record `Numbers` bằng nhau.

Nếu dữ liệu thực sự là một vector giá trị, cân nhắc:

1. Chuyển array sang cấu trúc immutable có ngữ nghĩa equality phù hợp và chi phí chấp nhận được.
2. Hoặc giữ array nhưng cung cấp **defensive copy ở hai phía** và tự định nghĩa **`equals/hashCode` cùng ngữ nghĩa**, giống `Snapshot` ở phần 4.
3. Nếu array lưu object mutable hoặc cấu trúc nhiều chiều, đánh giá thêm việc copy sâu và equality sâu; `Arrays.deepEquals`/`Arrays.deepHashCode` có thể hữu ích cho array object lồng nhau, nhưng không tự làm các phần tử mutable trở nên immutable.

### 6.2. Cảnh báo về key trong `HashMap` hoặc phần tử `HashSet`

Giả sử có record sau:

```java
import java.util.List;

record MutableKey(List<String> tags) {}
```

Nếu một `ArrayList` mutable được đưa trực tiếp vào `MutableKey`, rồi record đó được dùng làm key trong `HashMap`, việc sửa list sau khi đưa key vào map có thể thay đổi `hashCode()` của record. Khi đó truy vấn key có thể không còn tìm thấy phần tử trong bucket ban đầu. Đây là **nguy cơ**, không phải kết quả stdout có thể khẳng định 100% cho mọi dữ liệu vì còn phụ thuộc hash và cấu trúc bảng.

Với key có ngữ nghĩa giá trị, ưu tiên record chứa **immutable components** hoặc constructor lưu **bản sao phòng vệ** đã ngăn được mutation trong toàn bộ object graph. Không tự kết luận rằng vì bản thân record final nên key luôn ổn định.

## 7. Thiết kế record có dữ liệu bất biến sâu

Một cách tiếp cận rõ ràng là mô hình hóa bằng **các kiểu component vốn bất biến** và **collection chỉ chứa những component đó**.

Ví dụ:

```java
record Item(String code, int quantity) {}

record Order(java.util.List<Item> items) {
    Order {
        items = java.util.List.copyOf(items);
    }
}
```

Ở ví dụ này:

- `Item` chỉ chứa `String` và `int` — đều phù hợp với ngữ nghĩa dữ liệu bất biến.
- `Order` nhận một `List<Item>` nhưng constructor lưu bản sao cấu trúc không thể sửa.
- Accessor mặc định `items()` trả unmodifiable list; caller không thể `add`/`remove` vào list đó.
- Mỗi `Item` cũng không mang tham chiếu tới object mutable, nên toàn bộ đồ thị giá trị mô tả bởi `Order` có thể xem là bất biến sâu **theo các component được công bố**.

Lưu thành **`DeepValueRecordDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DeepValueRecordDemo {
    record Item(String code, int quantity) {}

    record Order(List<Item> items) {
        Order {
            items = List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        List<Item> source = new ArrayList<>();
        source.add(new Item("A", 2));

        Order order = new Order(source);
        source.clear();

        System.out.println("count=" + order.items().size());
        System.out.println("code=" + order.items().get(0).code());
        System.out.println("quantity=" + order.items().get(0).quantity());

        Order equalOrder = new Order(List.of(new Item("A", 2)));
        System.out.println("equals=" + order.equals(equalOrder));
    }
}
```

```bash
javac --release 17 DeepValueRecordDemo.java
java DeepValueRecordDemo
```

**Stdout:**

```text
count=1
code=A
quantity=2
equals=true
```

Lưu ý: đây là thiết kế bất biến sâu **vì các component đã chọn không có trạng thái mutable**, không phải vì Java tạo ra phép copy sâu tự động. Nếu đổi `Item(String code, int quantity)` thành `Item(StringBuilder code, int quantity)`, lập luận đó không còn đúng.

### 7.1. Khi nào phải tự copy phần tử?

Giả sử constructor nhận danh sách các object mutable. Nếu record cần **snapshot bất biến**, có thể chuyển từng phần tử sang kiểu giá trị bất biến:

```java
import java.util.List;

record UserSnapshot(String name, int score) {}

record TeamSnapshot(List<UserSnapshot> users) {
    TeamSnapshot {
        users = List.copyOf(users);
    }
}
```

Đoạn này khai báo mô hình, chưa bao gồm `main`. Khi dữ liệu nguồn là các đối tượng có setter, hãy trích xuất các thuộc tính cần thiết và **tạo `UserSnapshot` mới cho từng phần tử** trước khi chuyển vào `TeamSnapshot`. Copy list mà vẫn giữ nguyên các object mutable **không đủ** để bảo vệ trạng thái của từng phần tử.

Nếu đồ thị đối tượng có chu trình, object dùng chung, cache, tài nguyên native hoặc cấu trúc lớn, copy sâu tùy tiện có thể sai ngữ nghĩa hoặc tốn kém. Nên thiết kế ranh giới ownership, bất biến và snapshot theo từng loại dữ liệu, có kiểm thử và tài liệu rõ ràng.

## 8. Những trường hợp dễ nhầm: `final`, unmodifiable, immutable, thread-safe

| Trạng thái / cơ chế | Có thể gán lại field record? | Có thể thay nội dung được trỏ tới? | Ghi chú |
| --- | --- | --- | --- |
| `record R(int x)` | Không | Không có đối tượng tham chiếu ở `x` để sửa | Primitive là giá trị. |
| `record R(String s)` | Không | `String` là immutable | Không loại trừ các hành vi khác trong method do người dùng viết. |
| `record R(int[] a)` | Không | **Có** | Array có thể bị sửa qua alias. |
| `record R(List<String> xs)` lưu nguyên `ArrayList` | Không | **Có** | Có thể add/remove hoặc thay phần tử. |
| `record R(List<String> xs)` dùng `List.copyOf` | Không | Không sửa cấu trúc list; `String` cũng immutable | Gần với giá trị bất biến sâu cho phạm vi đã thiết kế. |
| `record R(List<MutableTask> xs)` dùng `List.copyOf` | Không | **Có**: trạng thái mỗi `MutableTask` | `List.copyOf` không copy sâu phần tử. |
| Accessor tự viết trả `array.clone()` | Không | Chỉ có thể sửa bản sao trả về | **Còn cần** constructor copy và equality phù hợp. |

**Thread-safe không tự đến từ `record`.** Final fields có các quy tắc về khởi tạo và visibility trong Java Memory Model, nhưng nếu component trỏ tới một đối tượng mutable đang được nhiều thread chỉnh sửa thì các thao tác trên đối tượng đó vẫn cần cơ chế đồng bộ, quyền sở hữu hoặc thiết kế bất biến thích hợp. Việc cập nhật đối tượng được trỏ tới không biến thành thao tác atomic chỉ vì field tham chiếu là final.

Nếu record là **snapshot bất biến sâu** và được xuất bản an toàn cho các thread khác, việc chia sẻ dữ liệu thường đơn giản hơn. Nếu record giữ `StringBuilder`, `ArrayList` hoặc một object có setter dùng chung, phải xét data race và vòng đời độc lập như với mọi lớp Java khác.

## 9. Lỗi thiết kế và cách khắc phục

| Dấu hiệu | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Thấy `record` là cho rằng mọi component bất biến | `final` chỉ cố định field, không khóa referent | Xem loại component và mọi đường aliasing. |
| Chỉ copy array ở constructor | Accessor trả array nội bộ, caller vẫn sửa được | Copy ở accessor; đánh giá cả equals/hashCode. |
| Chỉ copy array ở accessor | Người gọi vẫn giữ array truyền vào constructor | Copy cả đường vào lẫn đường ra. |
| Dùng `Collections.unmodifiableList(input)` tưởng là snapshot | View phản chiếu mutation của `input` | Dùng `List.copyOf` hoặc copy cấu trúc rồi bọc. |
| Dùng `List.copyOf` tưởng đã copy sâu | Phần tử là object mutable được chia sẻ | Chuyển phần tử sang giá trị immutable hoặc copy sâu có chủ đích. |
| Record chứa array giữ `equals` mặc định | Array so danh tính, không so nội dung | Chọn kiểu component phù hợp hoặc tự triển khai equality/hashCode. |
| Override accessor để copy array nhưng quên equality | Có thể phá vỡ copy invariant của `Record` | Đảm bảo `equals`/`hashCode` nhất quán với phép copy. |
| Đưa record chứa list mutable vào `HashMap` làm key | Hash code có thể đổi sau khi insert | Dùng key có trạng thái bất biến và hash code ổn định. |
| Trả raw `byte[]` của record qua API | Caller sửa được nội dung nội bộ | Accessor copy hoặc biểu diễn dữ liệu immutable. |
| Coi record final là tự động thread-safe | Referent mutable vẫn có data race | Dùng immutable graph hoặc đồng bộ/ownership đúng. |

### Quy trình kiểm tra thiết kế trước khi merge

1. **Liệt kê từng component** và đánh dấu primitive, immutable object, mutable reference, array hoặc collection.
2. **Kiểm tra đường vào**: nguồn có thể tiếp tục bị sửa sau constructor không? Copy/normalize ở canonical hoặc compact constructor khi cần.
3. **Kiểm tra đường ra**: accessor mặc định có làm lộ đối tượng mutable không? Có phải trả bản copy hoặc immutable view/snapshot không?
4. **Kiểm tra từng phần tử lồng nhau**: copy container chưa đủ nếu object con còn mutable.
5. **Kiểm tra hợp đồng giá trị**: `equals`, `hashCode`, copy invariant, chi phí so sánh và độ ổn định khi dùng làm key.
6. **Kiểm tra giới hạn dữ liệu**: chính sách `null`, dữ liệu có vòng tham chiếu, kích thước lớn, hiệu năng copy và xử lý ngoại lệ.
7. **Kiểm tra concurrency**: có alias shared giữa thread? Có mutation sau khi khởi tạo? Các cấu trúc mutable có thread-safe không?
8. **Viết test mutation từ cả hai phía**: sửa input sau constructor và sửa giá trị nhận từ accessor; kiểm tra record không đổi nếu đó là cam kết.

## 10. Bài tập tự kiểm tra

### Bài 1 — Dự đoán stdout

```java
record Numbers(int[] data) {}
int[] a = {1};
Numbers n = new Numbers(a);
a[0] = 5;
System.out.println(n.data()[0]);
```

Đây là đoạn code **đặt trong một phương thức**; không phải chương trình có `main` độc lập.

**Đáp án:** In `5`. Record giữ cùng tham chiếu array đầu vào; field `final` chỉ ngăn gán lại tham chiếu, không ngăn sửa `a[0]`.

### Bài 2 — Constructor đã clone, còn lỗ hổng nào?

```java
record Values(int[] data) {
    Values {
        data = data.clone();
    }
}
```

**Đáp án:** `data()` mặc định trả array nội bộ. Caller vẫn có thể làm `values.data()[0] = 10`. Nên thêm accessor phòng vệ và cân nhắc `equals/hashCode` theo nội dung array để bảo toàn hợp đồng giá trị của `Record`.

### Bài 3 — `List.copyOf` có bảo vệ mutable element không?

```java
record Tasks(java.util.List<StringBuilder> tasks) {
    Tasks {
        tasks = java.util.List.copyOf(tasks);
    }
}
```

**Đáp án:** Không. Cấu trúc list không sửa được, nhưng `StringBuilder` trong list vẫn mutable và có thể bị thay đổi qua alias. Muốn snapshot bất biến sâu, phải thay bằng kiểu phần tử bất biến hoặc copy/normalize từng phần tử theo yêu cầu.

### Bài 4 — Dùng record có array làm value key có chắc an toàn?

```java
record Key(int[] bytes) {}
Key k1 = new Key(new int[]{1, 2});
Key k2 = new Key(new int[]{1, 2});
System.out.println(k1.equals(k2));
```

**Đáp án:** In `false` vì array mặc định so danh tính. Cần chọn component có equality theo giá trị hoặc tự triển khai equality, hash code và copy phù hợp. Chỉ thêm `final` không giải quyết.

### Bài 5 — Đánh giá mức bất biến của hai record

```java
record A(java.util.List<String> tags) {
    A {
        tags = java.util.List.copyOf(tags);
    }
}

record B(java.util.List<StringBuilder> tags) {
    B {
        tags = java.util.List.copyOf(tags);
    }
}
```

**Đáp án:** `A` có list unmodifiable và các phần tử `String` immutable, nên có thể giữ ngữ nghĩa giá trị ổn định theo components. `B` có list unmodifiable nhưng mỗi `StringBuilder` còn có thể thay đổi, nên **không** bất biến sâu.

### Bài 6 — Một record có thể đổi trạng thái thông qua phương thức do tác giả viết không?

**Đáp án:** Có thể quan sát thay đổi ở object mutable mà component trỏ tới, nếu method của record hoặc code bên ngoài sửa object đó. Ngược lại, không thể gán lại component field đã được compiler đánh dấu `final`. Lập luận phải dựa trên object graph và alias, không chỉ vào modifier của class.

## 11. Tài liệu chính thức còn áp dụng

1. [Java Language Specification — Record Classes, JLS `8.10 (Java SE 25)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): quy tắc record, component fields `private final`, constructor và accessor.
2. [JLS `8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.3): field final và method accessor được khai báo ngầm/tường minh.
3. [JLS `8.10.4.2 — Compact Constructors](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4.2): thay tham số, gán field sau khi constructor block hoàn tất.
4. [Java SE 25 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): cách triển khai accessor/`equals`/`hashCode` ngầm định, defensive copy và **copy invariant**.
5. [Java SE 25 API — `java.util.List`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): `List.copyOf`, đặc tính unmodifiable, cấm `null` và giới hạn khi phần tử mutable.
6. [Java SE 25 API — `java.util.Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): view chỉ đọc phản ánh thay đổi của backing list.
7. [Java SE 25 — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): giới thiệu các thành viên compiler tạo và vai trò record là data carrier.

**Ghi nhớ:** `record` làm các **field component cố định**, nhưng **không sao chép hay đóng băng các đối tượng** mà field tham chiếu tới. Bất biến sâu chỉ có khi **kiểu thành phần, quyền sở hữu, defensive copy, accessor và equality** cùng được thiết kế nhất quán.