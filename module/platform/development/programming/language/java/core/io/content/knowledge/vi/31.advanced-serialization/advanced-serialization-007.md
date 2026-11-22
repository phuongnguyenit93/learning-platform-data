# Serializable với enum và record trong Java 17+: quy tắc tuần tự hóa, khôi phục và tương thích

## 1. Vì sao enum và record cần được học riêng?

Java Object Serialization cho phép ghi đối tượng thành chuỗi byte bằng `ObjectOutputStream` và khôi phục bằng `ObjectInputStream`. Giao diện đánh dấu `java.io.Serializable` là cơ sở để hầu hết đối tượng Java được xử lý theo cơ chế này.

Tuy nhiên, **`enum` và `record` không có cùng quy tắc tuần tự hóa như class thông thường**:

- `enum` **đã serializable một cách mặc định**. Định dạng đặc biệt lưu **tên hằng enum**, không lưu bộ trạng thái instance như một class thường. Khi đọc, Java tìm lại **chính hằng enum đã tồn tại**.
- `record` **không tự động implements Serializable**. Khi record có `implements Serializable`, dữ liệu serial form được xác định bởi **record components**, và lúc đọc Java gọi **canonical constructor** để tạo đối tượng, thay vì khôi phục field bằng cơ chế class thường.
- Cả hai có những giới hạn về `writeObject`/`readObject`, `serialVersionUID`, xử lý thay đổi định nghĩa lớp và bảo mật khi giải tuần tự hóa.

Bài học tập trung vào Java 17+ và **Java built-in Object Serialization**, không phải JSON, Jackson, protobuf hay mapping cơ sở dữ liệu. Mục tiêu: hiểu nội dung được lưu, điều gì xảy ra khi đọc lại, cách validate và cách tránh nhầm lẫn khi phát triển phiên bản mới.

## 2. Nhắc nhanh: Serializable, stream và object graph

Một class bình thường có thể khai báo:

~~~java
import java.io.Serializable;

class Note implements Serializable {
    private static final long serialVersionUID = 1L;
    String text;
}
~~~

Đoạn trên **chỉ minh họa khai báo**, chưa phải chương trình hoàn chỉnh. Interface `Serializable` là **marker interface**: không yêu cầu cài đặt phương thức nào. `ObjectOutputStream.writeObject(value)` ghi thông tin lớp và trạng thái cần thiết; `ObjectInputStream.readObject()` dựng lại các đối tượng trong object graph.

Hợp đồng thường gặp:

- Một object là `Serializable` **không đảm bảo toàn bộ object graph serializable**. Nếu một field/component tham chiếu tới đối tượng không thể ghi, quá trình có thể ném `NotSerializableException`.
- `static` không thuộc trạng thái riêng của từng instance để được tuần tự hóa; với class thường, `transient` đánh dấu field không lưu theo default serialization.
- Java Object Serialization dùng định dạng nhị phân dành cho Java và cần lớp tương thích khi đọc lại, **không tự biến thành giao thức trao đổi liên ngôn ngữ ổn định**.
- Stream nên được đóng bằng `try-with-resources`. Không giải tuần tự hóa byte từ nguồn không đáng tin chỉ vì chúng có extension `.ser`.
- Cơ chế duy trì tham chiếu và chu trình đối tượng trong Java Serialization có các trường hợp đặc biệt với record; phần sau sẽ giải thích.

Bảng so sánh:

| Đặc điểm | Class `implements Serializable` thông thường | `enum` | `record implements Serializable` |
| --- | --- | --- | --- |
| Có cần khai báo marker? | Có (hoặc kế thừa một kiểu serializable) | **Không**, enum vốn đã serializable | **Có**, record không tự động serializable |
| Nội dung chính trên stream | Các field serializable theo cơ chế class | **Tên của hằng enum** | **Giá trị record components** |
| Khi deserialize | Khôi phục instance và field theo cơ chế class | Tra lại hằng bằng `Enum.valueOf` | **Gọi canonical constructor** |
| Danh tính object | Thường nhận instance được dựng lại | Giữ đúng enum singleton constant (`==`) | Instance mới, so sánh nội dung bằng `equals` |
| `writeObject/readObject` riêng | Có thể dùng khi tuân hợp đồng | **Bị bỏ qua** | **Bị bỏ qua** |
| `writeReplace/readResolve` | Có thể áp dụng theo quy định | **Bị bỏ qua** | **Có thể áp dụng** |
| `serialVersionUID` | Rất quan trọng với compatibility | Cố định `0L`; khai báo bị bỏ qua | Mặc định `0L` hoặc khai báo riêng; kiểm tra UID khớp được miễn |
| Chu trình trỏ ngược về chính đối tượng | Có thể được giữ với cơ chế object handles | Enum là hằng có sẵn | Chu trình xuyên qua components trỏ lại record **không được giữ nguyên** |

## 3. Enum: lưu tên hằng, không lưu trạng thái instance

### 3.1. Tại sao không cần `implements Serializable`?

Mọi kiểu `enum` Java kế thừa `java.lang.Enum`, vốn thực thi `Serializable`. Ví dụ:

~~~java
enum Status {
    NEW, PROCESSING, DONE
}
~~~

Đoạn này đủ để những giá trị như `Status.DONE` được truyền cho `ObjectOutputStream.writeObject(...)`; không cần thêm marker hoặc một constructor đặc biệt.

**Khi ghi:** stream lưu định danh kiểu enum và tên hằng được trả bởi `name()`, chẳng hạn `"DONE"`. Giá trị ordinals hoặc các field instance do bạn khai báo trong hằng không phải phần trạng thái được lưu theo cơ chế enum đặc biệt.

**Khi đọc:** Java giải tên hằng bằng cơ chế tương đương `Enum.valueOf(Status.class, "DONE")`. Vì thế, kết quả là **chính `Status.DONE` hiện có trong JVM**, không tạo một instance enum thứ hai.

~~~java
Status original = Status.DONE;
// Sau khi writeObject rồi readObject thành công:
Status restored = Status.DONE; // Ví dụ giá trị được khôi phục.
System.out.println(original == restored); // true
~~~

Đoạn trên chỉ mô tả kết quả. Chương trình chạy hoàn chỉnh nằm ở mục 7.

### 3.2. `name()` khác `toString()` và `ordinal()`

Một enum có thể định nghĩa tên hiển thị:

~~~java
enum Level {
    LOW("Thấp"), HIGH("Cao");

    private final String label;

    Level(String label) {
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }
}
~~~

Nếu serialize `Level.HIGH`, Java lưu **tên `HIGH`**, chứ không lấy chuỗi `"Cao"` từ `toString()`. Cũng không lưu `ordinal()` làm định danh của hằng.

Hệ quả:

- Thay `toString()` hoặc tên hiển thị có thể không phá deserialization của giá trị enum cũ.
- Sắp xếp lại thứ tự khai báo các hằng không tự làm thay đổi tên `HIGH` được lưu.
- **Đổi tên/xóa hằng** đã từng xuất hiện trên stream cũ có thể làm quá trình khôi phục thất bại vì tên không còn tồn tại. Đây là khác biệt quan trọng khi nâng version.

### 3.3. Các field trong enum không được khôi phục từ stream

Xét enum có state:

~~~java
enum Mode {
    SAFE, FAST;

    private int visits;

    void markUsed() {
        visits++;
    }

    int visits() {
        return visits;
    }
}
~~~

Nếu gọi `Mode.SAFE.markUsed()` trước khi serialize, byte stream của `Mode.SAFE` vẫn chỉ đại diện cho **hằng SAFE**, không chứa bản sao `visits`.

Khi đọc enum trong **cùng JVM**, bạn nhận lại `Mode.SAFE` với state hiện tại của singleton trong JVM đó. Nếu deserialize ở một JVM khác, state do runtime đó khởi tạo/quản lý, **không phải số lượt visits từng có trên JVM nguồn**. Không dùng enum serialization để đồng bộ dữ liệu mutable gắn trong enum.

### 3.4. Custom hooks của enum không có tác dụng

Với enum, Java Object Serialization bỏ qua các phương thức tùy biến do enum định nghĩa như `writeObject`, `readObject`, `readObjectNoData`, `writeReplace` và `readResolve`. Nó cũng bỏ qua `serialPersistentFields` và bất kỳ field `serialVersionUID` nào tự khai báo; UID của enum luôn là `0L`.

Vì vậy **đừng viết `readResolve()` trong enum để bảo vệ tính duy nhất**: quy tắc khôi phục bằng tên vốn đã đảm bảo không tạo enum constant mới. Đừng nghĩ viết `writeObject` để lưu thêm field động sẽ có tác dụng. Nếu cần lưu dữ liệu thay đổi theo từng request, hãy đặt nó vào **class hoặc record serializable riêng**, còn enum chỉ mô tả loại/trạng thái có số lựa chọn hữu hạn.

## 4. Record: bất biến về cấu trúc không đồng nghĩa Serializable

### 4.1. Phải khai báo `implements Serializable`

Record có mặt chính thức từ Java 16 (sử dụng ổn định trong Java 17), giúp biểu diễn dữ liệu qua các **record components**:

~~~java
record Point(int x, int y) {
}
~~~

Record trên **chưa serializable**, dù có constructor, accessor, `equals`, `hashCode` và `toString` do compiler tạo. Nếu truyền một instance vào `ObjectOutputStream.writeObject`, có thể nhận `NotSerializableException`.

Bản hỗ trợ Java Object Serialization cần khai báo:

~~~java
import java.io.Serializable;

record Point(int x, int y) implements Serializable {
}
~~~

Chỉ thêm marker chưa đủ nếu component có kiểu tham chiếu chứa dữ liệu không serializable. Ví dụ:

~~~java
record Holder(Object value) implements Serializable {
}

Holder invalid = new Holder(new Object());
// writeObject(invalid) có thể ném NotSerializableException
// vì java.lang.Object không implements Serializable.
~~~

Hai đoạn trên là **minh họa**. Kiểu component `Object` không tự khiến mọi giá trị bên trong đều được hỗ trợ, cũng như `List` không đảm bảo mọi implementation và mọi element đều serializable.

### 4.2. Java ghi gì cho record?

Với:

~~~java
record Product(String sku, int quantity) implements Serializable {
}
~~~

Dạng serial của record dựa vào **giá trị hai component** `sku` và `quantity`. Một record không thể khai báo instance field tùy ý ngoài các field được tạo cho record components. Những biến `static` không thuộc trạng thái mỗi instance và không phải component serial form.

Khác với class thông thường, quá trình serialize record không dùng `serialPersistentFields` để chọn field tùy ý và không gọi `writeObject` do record định nghĩa. Vì thế **tập component là hợp đồng dữ liệu trực tiếp** cần xem xét khi versioning.

Điều này không phải “record serialize thành JSON”. Byte stream Java vẫn chứa metadata kiểu/class và thông tin field theo giao thức Java Object Serialization.

### 4.3. Canonical constructor chạy khi deserialize

Record được khôi phục thông qua **canonical constructor**: Java dựng các giá trị component từ stream rồi gọi constructor này.

~~~java
import java.io.Serializable;
import java.util.Objects;

record Account(String id, int balance) implements Serializable {
    public Account {
        Objects.requireNonNull(id, "id");
        if (id.isBlank() || balance < 0) {
            throw new IllegalArgumentException("Invalid account");
        }
    }
}
~~~

Đây là khai báo minh họa. `public` trong compact canonical constructor phù hợp cho record public; nếu record package-private, quyền truy cập constructor có thể không cần `public`. Nhờ việc canonical constructor được gọi lúc deserialize, các kiểm tra `id` không trống và `balance >= 0` có cơ hội được áp dụng cả khi dữ liệu đến từ một serialized stream.

Nếu constructor từ chối giá trị được khôi phục, Java có thể báo `InvalidObjectException` (nguyên nhân gốc là exception từ constructor). **Không nên dựa vào setter sau khi đọc để vá invariant**: record được xây dựng với giá trị đã đọc qua constructor.

Quan trọng: validation của record **không có nghĩa nguồn dữ liệu được tin cậy**. Byte stream có thể kích hoạt việc tạo, parse hoặc khôi phục các object component khác trước khi canonical constructor của record được gọi. Phải áp dụng chính sách an toàn cho deserialization ở phạm vi toàn bộ stream.

### 4.4. Phương thức serializer hook nào có hiệu lực?

Với record serializable, các hook tương tự class thường có sự khác biệt:

| Thành phần | Record trong Java Serialization |
| --- | --- |
| `private void writeObject(ObjectOutputStream)` | Bị bỏ qua |
| `private void readObject(ObjectInputStream)` | Bị bỏ qua |
| `readObjectNoData` | Bị bỏ qua |
| `writeExternal/readExternal` | Bị bỏ qua đối với serial form của record |
| `serialPersistentFields` | Bị bỏ qua |
| `writeReplace` | Có thể dùng cơ chế thay thế object |
| `readResolve` | Có thể dùng để chọn object thay thế sau khi khôi phục |
| Canonical constructor | **Được gọi** khi tạo record từ stream |
| `serialVersionUID` | Mặc định `0L`; có thể khai báo nhưng đối chiếu UID khớp được miễn đối với record |

Nếu cần xác thực component, ưu tiên đặt invariant trong canonical constructor. Nếu cần **định dạng tuần tự hóa riêng hoàn toàn**, record mặc định không cho tùy biến `writeObject/readObject` như class thường; hãy cân nhắc một **serialization proxy** dùng `writeReplace/readResolve` hoặc dùng định dạng tường minh như JSON/CBOR/protobuf với schema rõ ràng.

Không nên bắt đầu bằng hook để xử lý vấn đề vốn chỉ là validation; càng ít hành vi tùy biến trên stream, khả năng kiểm soát và review càng tốt.

## 5. SerialVersionUID: enum, record và class khác nhau

`serialVersionUID` là định danh phiên bản lớp trong Java Serialization. Với class thường, việc không khớp UID có thể gây `InvalidClassException` khi deserialize.

**Enum:**

- UID luôn cố định là `0L`.
- Nếu viết một field cùng tên `serialVersionUID` trong enum, serialization **bỏ qua** field đó.
- Không dùng UID để đánh số version cho tên hằng enum.

**Record:**

- UID mặc định là `0L`, trừ khi record khai báo một giá trị tường minh.
- Java **miễn yêu cầu hai UID phải khớp** trong quá trình giải tuần tự hóa record.
- Điều này **không bảo đảm mọi thay đổi cấu trúc record đều tương thích**: việc thêm/xóa/đổi tên/đổi kiểu component vẫn có thể thay đổi dữ liệu được khôi phục hoặc làm constructor từ chối.

Ví dụ:

~~~java
import java.io.Serial;
import java.io.Serializable;

record Invoice(String code, long cents) implements Serializable {
    @Serial
    private static final long serialVersionUID = 17L;
}
~~~

`@Serial` (có từ Java 14) giúp biểu đạt ý định khai báo field/method dành cho serialization và hỗ trợ compiler phát hiện một số khai báo sai ngữ nghĩa. UID ở đây là một thuộc tính serial version của record, nhưng đừng diễn giải nó thành cơ chế bắt buộc kiểm tra khớp như class bình thường.

## 6. Thay đổi định nghĩa lớp và khả năng đọc dữ liệu cũ

### 6.1. Khi enum thay đổi

Giả sử bản cũ:

~~~java
enum Phase {
    NEW, DONE
}
~~~

và bản mới:

~~~java
enum Phase {
    NEW, ACTIVE, DONE
}
~~~

Thêm `ACTIVE` thường không ngăn stream cũ có giá trị `NEW` hoặc `DONE` được giải lại, miễn những tên đã lưu còn tồn tại. Ngược lại, đổi `DONE` thành `FINISHED` sẽ khiến stream cũ chứa tên `DONE` không tìm thấy hằng tương ứng.

**Hướng xử lý nếu cần hỗ trợ lâu dài:** tránh đổi tên enum constant đã công bố trong Java serialized data; cân nhắc lưu **mã nghiệp vụ ổn định riêng** nếu giao thức cần tiến hóa qua nhiều version. Đừng giả định một enum name là mã liên hệ ngoài Java bền vững mãi mãi.

### 6.2. Khi record thay đổi

Bản đầu:

~~~java
record User(String name, int age) implements Serializable {
}
~~~

Sau đó thêm component:

~~~java
record User(String name, int age, String region)
        implements Serializable {
}
~~~

Khi local record có component không xuất hiện trong stream cũ, giá trị được truyền cho canonical constructor là **giá trị mặc định của kiểu**: `0` cho `int`, `false` cho `boolean`, `null` cho reference. Nếu component mới `region` không có trong stream, constructor nhận `null` cho `region`.

Nếu constructor mới từ chối `null`:

~~~java
record User(String name, int age, String region)
        implements Serializable {
    public User {
        if (region == null) {
            throw new IllegalArgumentException("region required");
        }
    }
}
~~~

thì dữ liệu cũ có thể không deserialize được. Nếu điều khoản nghiệp vụ cho phép, có thể chuẩn hóa thiếu thông tin trong constructor, chẳng hạn đặt `region = "UNKNOWN"`; điều đó phải là quyết định schema có chủ đích, không tự đặt mặc định cho trường nhạy cảm.

Cơ chế còn có đặc điểm:

- Dữ liệu field trong stream được khớp với component theo **tên** và được kiểm tra kiểu thích hợp; không giả định đơn giản rằng chỉ thứ tự khai báo quyết định mapping.
- Field tồn tại trong stream nhưng không còn là component của record local có thể bị bỏ qua.
- Nếu đổi kiểu component hoặc thay cấu trúc không tương thích, kết quả có thể là exception thay vì giá trị chuyển kiểu tự động.
- **Validation chạy lại** trong canonical constructor, nên việc nâng version phải tính cả invariant mới.
- Việc UID không yêu cầu khớp không phải “giấy phép” thay schema tùy ý mà vẫn đọc được mọi dữ liệu cũ.

Với dữ liệu lưu dài hạn, lưu thêm version ở **định dạng nghiệp vụ** hoặc xây cơ chế migration có kiểm thử riêng. Dùng Java Object Serialization cho cache tạm nội bộ khác về yêu cầu với dùng nó làm format lưu trữ 10 năm.

### 6.3. Vòng đời class và tên kiểu

Cả enum và record vẫn phụ thuộc việc JVM đọc stream có thể tìm được class tương ứng. Đổi package, đổi tên class, thay classpath/module visibility hoặc thiếu class có thể dẫn tới `ClassNotFoundException` hay lỗi tương thích khác, dù tên hằng hoặc component không đổi.

Đừng nhầm “tương thích dữ liệu record” với “không cần bảo trì tên class”. Byte stream Java chứa thông tin kiểu của hệ sinh thái Java.

## 7. Ví dụ Java 17+ hoàn chỉnh: round-trip enum và record

Chương trình sau không dùng tệp trên đĩa: nó ghi Java serialized bytes vào `ByteArrayOutputStream` rồi đọc lại bằng `ByteArrayInputStream`. Trong demo, mọi byte đều **do chính chương trình tạo**; đây là ví dụ học cách hoạt động, **không phải hướng dẫn chấp nhận byte deserialization không tin cậy từ mạng**.

Mã minh họa rằng enum giữ identity, record có value equality nhưng không giữ identity, và canonical constructor được gọi khi khôi phục.

Lưu tệp **`EnumRecordSerializationDemo.java`**:

~~~java
import java.io.*;
import java.util.Objects;

public class EnumRecordSerializationDemo {
    enum Phase { NEW, DONE }

    record WorkItem(String id, Phase phase, int retries)
            implements Serializable {
        @Serial
        private static final long serialVersionUID = 17L;
        private static int constructed;

        WorkItem {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(phase, "phase");
            if (id.isBlank() || retries < 0) {
                throw new IllegalArgumentException("Invalid work item");
            }
            constructed++;
        }
    }

    private static byte[] encode(Object value) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(value);
        }
        return sink.toByteArray();
    }

    private static Object decode(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Phase state = Phase.DONE;
        Phase restoredState = (Phase) decode(encode(state));
        System.out.println("Enum identity preserved: "
                + (state == restoredState));

        WorkItem original = new WorkItem("task-42", Phase.DONE, 2);
        WorkItem restored = (WorkItem) decode(encode(original));
        System.out.println("Record equality preserved: "
                + original.equals(restored));
        System.out.println("Record same instance: "
                + (original == restored));
        System.out.println("Enum component identity: "
                + (restored.phase() == Phase.DONE));
        System.out.println("Canonical constructor calls: "
                + WorkItem.constructed);
        System.out.println("Restored: " + restored);
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 EnumRecordSerializationDemo.java
java EnumRecordSerializationDemo
~~~

**Stdout đã được kiểm tra bằng biên dịch `--release 17` và thực thi JVM:**

~~~text
Enum identity preserved: true
Record equality preserved: true
Record same instance: false
Enum component identity: true
Canonical constructor calls: 2
Restored: WorkItem[id=task-42, phase=DONE, retries=2]
~~~

### Phân tích chính xác từng kết quả

1. `Phase` là enum, nên không cần `implements Serializable`. Giá trị `DONE` từ stream được tra về singleton `Phase.DONE`, vì vậy `state == restoredState` là `true`.
2. `WorkItem` khai báo `implements Serializable`; nếu bỏ marker, `writeObject(original)` sẽ không serialize được record này theo cơ chế Java Object Serialization thông thường.
3. `original.equals(restored)` là `true` vì record equality so sánh theo component (trong ví dụ `String`, enum và `int` có semantics phù hợp).
4. `original == restored` là `false`: record được dựng lại thành một object riêng. Không suy ra mọi record sau round-trip đều giữ identity.
5. Component `phase` vẫn là enum singleton nên `restored.phase() == Phase.DONE` là `true`.
6. Biến `constructed` là static, **không** được lưu vào byte stream. Nó tăng một lần khi gọi `new WorkItem(...)` và một lần khi canonical constructor được gọi bởi deserialization; vì vậy kết quả là 2 trong tiến trình demo này.
7. `@Serial private static final long serialVersionUID = 17L` là UID tường minh của record. Với record, việc khớp UID không được bắt buộc theo quy tắc dành riêng.
8. `ObjectOutputStream` được đóng sau khi ghi để flush và giải phóng tài nguyên; `ObjectInputStream` được đóng sau khi đọc. `ByteArrayOutputStream.toByteArray()` cung cấp bản sao byte.
9. Vì `ObjectInputStream.readObject()` trả về `Object`, mã demo cast sang kiểu mong đợi. Với dữ liệu không tin cậy, **cast sau deserialize không phải cơ chế an toàn**, do quá trình tạo object đã có thể xảy ra trước đó.

## 8. Vì sao validation trong canonical constructor có giá trị?

Một class `Serializable` thông thường có thể được dựng lại mà constructor dành cho instance serializable thông thường không chạy theo cách tạo mới. Điều này khiến invariant cần các cơ chế đặc thù như `readObject` hoặc serialization proxy.

Record khác ở chỗ **canonical constructor thực sự được gọi** khi deserialize. Bởi vậy, những invariant như số lượng không âm, mã định danh hợp lệ hoặc enum component không `null` có thể được kiểm tra tập trung tại nơi tạo object.

Ví dụ:

~~~java
record Reservation(String code, int seats)
        implements Serializable {
    public Reservation {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code is required");
        }
        if (seats <= 0 || seats > 20) {
            throw new IllegalArgumentException("seats out of range");
        }
    }
}
~~~

Mã minh họa này có lợi vì object sai quy tắc không được khôi phục thành record hợp lệ một cách âm thầm. Tuy nhiên:

- Constructor được gọi **sau khi đọc các component values**, do đó các object tham chiếu trong graph có thể đã được deserialized.
- Mọi object component cần validate riêng; record không tự biến mutable list/map thành immutable.
- Tránh side effect trong constructor, vì đọc một byte stream có thể khiến constructor chạy. Constructor nên ưu tiên kiểm tra giá trị, chuẩn hóa dữ liệu thuần và không tự thực hiện lệnh gửi tiền, gọi mạng hoặc thay đổi tài nguyên.

### Record là shallowly immutable

Với:

~~~java
record Batch(int[] numbers) implements Serializable {
}
~~~

Field tham chiếu `numbers` là final, nhưng **phần tử của mảng vẫn có thể sửa**. Một người giữ tham chiếu tới array có thể thay đổi giá trị sau khi tạo record; hoặc dùng accessor để lấy mảng rồi sửa.

Nếu hợp đồng cần bất biến sâu hơn, sao chép defensively trong canonical constructor và khi trả về (đối với array), hoặc dùng cấu trúc immutable thích hợp. Điều này là **vấn đề thiết kế dữ liệu**, không được cơ chế serialization tự động giải quyết.

## 9. Chu trình đối tượng và giới hạn riêng của record

Object Serialization thường dùng handles/back references để giữ quan hệ tham chiếu và nhiều chu trình trong graph. Tuy nhiên, với record, **các component được deserialize trước khi record object được dựng qua canonical constructor**.

Giả sử một `Node` thông thường có field trỏ ngược về một record đang chứa chính Node đó. Nếu graph gốc có chu trình từ record → Node → record, khi đọc, tham chiếu trỏ ngược đến record có thể thành `null`. Đây là hạn chế được đặc tả Java Serialization nêu rõ; không nên dựa vào record để biểu diễn graph phức tạp có các back-reference trở lại chính record.

**Mẫu thiết kế phù hợp hơn:** serial form dạng acyclic DTO/record, lưu ID thay vì tham chiếu chu trình, rồi xây lại các quan hệ sau khi validate theo một bước dựng graph tường minh.

Ví dụ dùng ID:

~~~java
record Edge(String fromId, String toId)
        implements Serializable {
}
~~~

Trường `fromId/toId` là dữ liệu ổn định để tái liên kết trong graph sau khi deserialize, không phải reference vòng về record đang được tái dựng.

## 10. Bảo mật: enum và record không làm deserialization trở nên an toàn

**Không deserialize byte không tin cậy chỉ vì kiểu kết quả mong đợi là enum hoặc record.** Luồng Java Serialization có thể chứa object graph với nhiều lớp khác, và quá trình đọc có thể kích hoạt hành vi trong lớp trước khi kết quả được cast hoặc validate cuối cùng.

Các quy tắc an toàn thực hành:

1. **Ưu tiên tránh Java native deserialization cho dữ liệu từ bên ngoài.** Nếu cần giao thức công khai, dùng dữ liệu có schema rõ ràng như JSON/protobuf/CBOR và bộ parser có kiểm soát.
2. Nếu bắt buộc dùng Java Serialization, **chỉ chấp nhận nguồn đáng tin cậy** và giới hạn lớp được phép deserialize. Dùng `ObjectInputFilter` (JDK 9+, sẵn trong Java 17) theo mô hình allowlist/threat model.
3. Giới hạn độ sâu graph, số references, số byte stream, độ dài array và ngân sách tài nguyên; **lọc không thay thế xác thực nguồn**.
4. Kiểm soát toàn bộ thư viện/classpath: những lớp serializable trong object graph có thể có hook đọc đặc biệt.
5. Canonical constructor của record thực hiện validation sau khi component values đã đọc, do đó **không thay thế kiểm tra deserialization input**.
6. Có chính sách lỗi rõ ràng cho `InvalidClassException`, `ClassNotFoundException`, `StreamCorruptedException`, `InvalidObjectException` và `NotSerializableException`.
7. Không log toàn bộ serialized payload hoặc dữ liệu nhạy cảm; chú ý size/quota cả khi ghi vào `ByteArrayOutputStream` trong ví dụ học tập.

Một đoạn minh họa về giới hạn dạng đồ thị bằng `ObjectInputFilter`:

~~~java
ObjectInputFilter limit = info -> {
    if (info.depth() > 12
            || info.references() > 500
            || info.streamBytes() > 1024 * 1024) {
        return ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
};

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(limit);
    Object value = in.readObject();
}
~~~

Đây **không phải chương trình độc lập**; cần import `ObjectInputFilter` và `ObjectInputStream`, `source` là `InputStream` đã có. Đoạn minh họa **chỉ đặt giới hạn resource**, chưa allowlist lớp, nên **chưa đủ** để deserialize input không tin cậy một cách an toàn. Trong production, ưu tiên filter kết hợp allowlist các class thực sự cần đọc cùng giới hạn byte/depth/array; kiểm thử filter với toàn bộ object graph hợp lệ.

**Lưu ý:** dữ liệu từ chính chương trình của bạn cũng có thể hết hạn/không tương thích sau một lần nâng phiên bản; “trusted source” không đồng nghĩa “đọc được ở mọi version”.

## 11. Enum và record trong hệ thống thực tế

### 11.1. Record DTO nội bộ hoặc cache tạm

Ví dụ:

~~~java
enum TaskStatus { QUEUED, DONE }

record TaskSnapshot(String id, TaskStatus status, long updatedAt)
        implements Serializable {
}
~~~

Một `TaskSnapshot` chỉ chứa primitive, `String` và enum có thể được round-trip tương đối đơn giản. Nếu sử dụng như cache tạm trong nội bộ JVM/Java ecosystem và luôn kiểm soát version tương thích, Java Serialization có thể khả thi.

Nhưng nếu lưu trong database lâu dài, gửi liên dịch vụ nhiều ngôn ngữ hay chia sẻ giữa phiên bản ứng dụng phát triển độc lập, định dạng có schema tường minh thường dễ migration, audit và kiểm soát bảo mật hơn.

### 11.2. Enum như domain code, record như payload

Một thiết kế dễ hiểu:

- Enum biểu thị tập trạng thái trong Java code.
- Record biểu thị dữ liệu của một snapshot/request.
- Khi xuất ra định dạng lâu dài, ánh xạ enum sang mã nghiệp vụ ổn định, ví dụ `"completed"`, và khai báo schema payload. Không buộc dữ liệu bên ngoài phụ thuộc mãi vào tên hằng Java.

Cách này cho phép dùng enum/record trong miền Java nhưng vẫn quản lý migration tường minh nếu đổi tên package, record type hoặc enum constant.

### 11.3. Khi cần custom serial form

Nếu cần custom hook `writeObject/readObject`, record không có đường tùy biến giống class `Serializable` thường. Một số phương án:

- Dùng class serializable thông thường với các hook theo đặc tả (và review chặt).
- Dùng **serialization proxy** tường minh qua `writeReplace` trên record và `readResolve` trên proxy; lưu payload dạng dễ versioning. Đây là kỹ thuật nâng cao cần test nhiều phiên bản và đảm bảo loại thay thế tương thích.
- Dùng codec/schema độc lập Object Serialization nếu mục tiêu là lưu/trao đổi dữ liệu ổn định.

Không dùng `readResolve` của enum làm proxy hoặc để kiểm tra rename: hook enum bị bỏ qua.

## 12. Lỗi thường gặp và cách sửa

| Hiểu nhầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| “Record tự Serializable vì là data carrier” | `NotSerializableException` | Phải `implements Serializable` rõ ràng |
| “Enum cần implements Serializable” | Khai báo thừa, hiểu sai cơ chế | Enum đã serializable qua `java.lang.Enum` |
| “Enum serialize ordinal” | Thiết kế versioning sai | Enum lưu **tên hằng** |
| “Enum serialize mọi field instance” | Mong đợi mutable state được đồng bộ | Chỉ tên hằng được dùng để khôi phục constant |
| “Đổi tên enum constant vẫn đọc stream cũ” | Không tìm được tên đã lưu | Giữ tên cũ hoặc làm migration tường minh |
| “Enum readResolve chống tạo nhiều singleton” | Hook không được dùng | Enum vốn giữ singleton identity |
| “Record readObject sẽ chạy” | Validation bị đặt sai chỗ | Đặt invariant trong canonical constructor |
| “Record deserialization bỏ qua constructor” | Bỏ sót việc constructor có thể ném lỗi | Canonical constructor được gọi |
| “Record == giữ nguyên sau round-trip” | So sánh identity sai | So sánh value qua `equals` khi phù hợp |
| “UID record luôn phải khớp” | Hiểu sai tương thích | UID matching được miễn riêng cho record |
| “UID record không quan trọng tức mọi schema tương thích” | Lỗi khi thay component/invariant | Kiểm tra tên/kiểu/default/constructor |
| “Record field final nên toàn bộ dữ liệu immutable sâu” | Component mutable vẫn bị sửa | Defensive copy/schema immutable |
| “Mọi vòng tham chiếu record đều được giữ” | Back-reference có thể thành `null` | Tránh cycle trỏ ngược đến record |
| “Record/enum loại bỏ rủi ro deserialize untrusted stream” | Nguy cơ từ object graph khác | Tránh untrusted Java Serialization; filter/allowlist |
| “Cast sau readObject xác thực trước khi tạo object” | Quá muộn để chặn side effect khi deserialize | Dùng cấu trúc/định dạng/filter an toàn từ đầu |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `enum Color { RED, BLUE }` có cần `implements Serializable` mới ghi bằng `ObjectOutputStream` được không?

**Đáp án:** Không. Enum vốn đã serializable.

**Câu 2.** Java lưu `Color.RED` dưới dạng ordinal hay tên?

**Đáp án:** Tên `RED`, cùng thông tin kiểu cần thiết của stream; không dùng ordinal để xác định hằng.

**Câu 3.** Có thể thay `toString()` của enum mà không đổi định danh serialized constant không?

**Đáp án:** Có. Định danh dựa trên `name()`; cần thận trọng nếu thay chính tên constant.

**Câu 4.** `record User(String name) {}` có được serialize bằng `writeObject(new User("Lan"))` không?

**Đáp án:** Không theo Java Object Serialization mặc định vì chưa khai báo `implements Serializable`.

**Câu 5.** Record đọc lại từ stream có gọi canonical constructor không?

**Đáp án:** Có. Constructor có thể xác thực invariant và từ chối dữ liệu không hợp lệ.

**Câu 6.** `private void readObject(...)` do record khai báo có tùy biến quá trình khôi phục không?

**Đáp án:** Không. Hook đó bị bỏ qua khi serialize/deserialize record; dùng canonical constructor hoặc cách thiết kế serial form khác phù hợp.

**Câu 7.** Thêm component `String region` vào record sẽ nhận gì khi đọc stream cũ không có region?

**Đáp án:** Giá trị mặc định `null` được truyền cho canonical constructor; nếu constructor từ chối null thì dữ liệu cũ có thể không được khôi phục.

**Câu 8.** Có thể dựa vào UID record được miễn kiểm tra khớp để khẳng định việc đổi kiểu component luôn an toàn?

**Đáp án:** Không. Tên/kiểu/default và validation vẫn quyết định khả năng khôi phục.

**Câu 9.** Deserialization của một record chứa object graph có vòng trỏ ngược về record có luôn giữ nguyên reference identity?

**Đáp án:** Không. Chu trình từ components trỏ lại record có hạn chế đặc thù; tham chiếu ngược có thể thành `null`.

**Câu 10.** Với byte nhận từ HTTP request, chỉ nhận kiểu kết quả `MyRecord` là đã an toàn để gọi `readObject()`?

**Đáp án:** Không. Các object trong stream có thể được xử lý trước khi kết quả được cast. Tránh native deserialization không tin cậy hoặc áp filter/allowlist và nhiều lớp bảo vệ phù hợp.

## 14. Ghi nhớ

- **Enum:** đã `Serializable`; lưu tên hằng, đọc lại đúng enum constant, giữ `==`; không lưu state instance và không dùng custom serialization hooks.
- **Record:** phải `implements Serializable`; lưu record components; **gọi canonical constructor** khi deserialize; thông thường có value equality nhưng là object mới.
- **Tương thích:** enum phụ thuộc tên constant; record phụ thuộc tên/kiểu component, default cho component thiếu và invariant của constructor; UID matching record được miễn nhưng không đảm bảo mọi migration.
- **Giới hạn:** record không tùy biến `writeObject/readObject` kiểu class thường; có ngoại lệ `writeReplace/readResolve`; chu trình trỏ ngược về record không được bảo toàn như ordinary class.
- **Bảo mật:** Java Object Serialization không dành cho đầu vào tùy ý chưa tin cậy; enum và record không thay thế kiểm soát object graph, giới hạn tài nguyên hay schema.

### Tài liệu chính thức

- [Java SE 17 — Object Serialization Specification, System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html) — mục 1.12 (enum), 1.13 (record), 1.14 (circular references).
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — API deserialize và các lưu ý bảo mật.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — filtering khi deserialization.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html) — marker interface và cơ chế class serializable.
