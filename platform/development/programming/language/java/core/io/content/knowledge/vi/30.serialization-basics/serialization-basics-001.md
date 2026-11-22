# Tuần tự hóa (serialization), Serializable và lưu đồ thị đối tượng trong Java

## 1. Serialization là gì?

**Serialization (tuần tự hóa)** là quá trình chuyển một đối tượng cùng trạng thái cần lưu của nó thành một biểu diễn có thể ghi vào luồng byte. **Deserialization (giải tuần tự hóa)** là quá trình đọc biểu diễn ấy và dựng lại các đối tượng tương ứng.

Trong Java Core I/O, cơ chế tuần tự hóa đối tượng tích hợp sẵn dùng:

- `java.io.Serializable`: **marker interface** đánh dấu lớp cho phép Java serialization.
- `java.io.ObjectOutputStream`: ghi đối tượng và đồ thị tham chiếu ra `OutputStream`.
- `java.io.ObjectInputStream`: đọc byte đã được tạo theo định dạng serialization của Java và dựng lại các đối tượng.

Cần phân biệt:

- **Serialization**: dữ liệu Java object được mã hóa thành một định dạng byte có quy tắc.
- **Persistence**: trạng thái được lưu để tồn tại qua vòng đời tiến trình; Java serialization chỉ là một cách thực hiện, không phải lựa chọn luôn tốt nhất.
- **Deep copying**: có thể dùng serialize–deserialize làm cách sao chép một đồ thị phù hợp, nhưng thường tốn chi phí và không áp dụng cho mọi object.
- **Object graph**: tập các object và quan hệ tham chiếu nối chúng với nhau, có thể chia sẻ cùng object hoặc có chu trình.

Ví dụ đồ thị:

```text
team (ArrayList)
  ├── [0] ──> alice ───── friend ──> bob
  │             ^                      │
  │             └────── friend ────────┘
  ├── [1] ───────────────────────────> bob
  └── [2] ──> alice   (cùng tham chiếu với [0])
```

Khi ghi **cả đồ thị** bằng `ObjectOutputStream.writeObject(team)`, cơ chế Java serialization lưu cả thông tin **định danh object trong luồng**. Khi đọc lại, tham chiếu lặp và vòng có thể được khôi phục đúng theo đồ thị, chứ không đơn thuần tạo một bản copy cho mỗi lần gặp cùng object.

> **Lưu ý bảo mật quan trọng:** không sử dụng `ObjectInputStream` để giải tuần tự hóa byte đến từ nguồn không tin cậy. Java native deserialization có bề mặt tấn công lớn; bộ lọc `ObjectInputFilter` chỉ là lớp phòng vệ bổ sung, không biến input không tin cậy thành an toàn tuyệt đối. Với dữ liệu trao đổi công khai, cân nhắc định dạng schema/DTO được kiểm soát và parser phù hợp.

## 2. Serializable là marker interface

Một lớp muốn tham gia cơ chế tuần tự hóa chuẩn có thể triển khai `Serializable`:

```java
import java.io.Serializable;

public class Student implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String id;
    private final String name;

    public Student(String id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String toString() {
        return id + " - " + name;
    }
}
```

Đây là **một class minh họa độc lập**, có thể lưu `Student.java`; để chạy, cần một class chứa `main` hoặc ứng dụng khác sử dụng nó.

`Serializable` là **marker interface**: bản thân nó không định nghĩa phương thức phải override. Lời gọi `writeObject` của `ObjectOutputStream` và logic runtime xử lý lớp này theo cơ chế đặc biệt.

Điều này **không đồng nghĩa** mọi lớp tự động được tuần tự hóa:

- Một object thuộc lớp **không serializable** xuất hiện trong đồ thị có thể khiến `writeObject` thất bại với `NotSerializableException`.
- Những field được khai báo `transient` không tham gia cơ chế lưu field mặc định.
- `static` là trạng thái thuộc lớp, **không** phải trạng thái của instance được lưu theo cách mặc định.
- Một số loại object có quy tắc serialization đặc biệt, chẳng hạn `enum`, `record`; không nên áp đặt máy móc tất cả quy tắc của class thông thường cho chúng.
- Một class `Serializable` có thể tùy chỉnh hành vi serialization bằng các hook hợp lệ, nhưng điều đó không được dùng để bỏ qua bảo mật và kiểm tra bất biến.

### Serializable không chỉ là “ghi field ra text”

`ObjectOutputStream` tạo **stream nhị phân định dạng riêng của Java**, gồm header, mô tả class, dữ liệu field và thông tin tham chiếu. Đừng mở file bằng Notepad rồi mong đọc được nội dung như JSON. Đừng dùng định dạng native này làm giao thức công khai lâu dài nếu cần interoperability với ứng dụng viết bằng ngôn ngữ khác.

## 3. ObjectOutputStream và ObjectInputStream

Pipeline cơ bản:

```text
Student object
     |
     v
ObjectOutputStream.writeObject(...)
     |
     v
Java serialization stream bytes
     |
     v
FileOutputStream / ByteArrayOutputStream / OutputStream khác
     |
     v
ObjectInputStream.readObject()
     |
     v
Student object được tái tạo
```

Để ghi:

```java
try (ObjectOutputStream out = new ObjectOutputStream(
        Files.newOutputStream(Path.of("student.ser")))) {
    out.writeObject(student);
}
```

Để đọc:

```java
try (ObjectInputStream in = new ObjectInputStream(
        Files.newInputStream(Path.of("student.ser")))) {
    Student restored = (Student) in.readObject();
}
```

Hai đoạn là **mã minh họa**, cần import `ObjectOutputStream`, `ObjectInputStream`, `Files`, `Path` và khai báo object `student`. Method đọc cần xử lý `IOException` và `ClassNotFoundException`. Chỉ dùng `ObjectInputStream` trên stream được tạo bởi nguồn có thể tin cậy và được quản lý.

Một vài chi tiết:

1. Constructor `ObjectOutputStream` ghi **stream header** trước khi gọi `writeObject`.
2. Constructor `ObjectInputStream` đọc/kiểm tra header của input, có thể **block** khi chờ header từ một stream đang mở, đặc biệt ở kết nối hai chiều.
3. `writeObject` ghi biểu diễn của object và các phần liên quan trong đồ thị.
4. `readObject` trả về kiểu `Object`, caller kiểm tra/cast kiểu mong đợi và xác minh dữ liệu có hợp lệ về mặt nghiệp vụ không.
5. Try-with-resources đóng wrapper và underlying stream, đảm bảo flush/close tài nguyên theo hợp đồng API.
6. Đọc đối tượng có thể khởi tạo những object mới với **tham chiếu khác** object gốc, nhưng quan hệ chia sẻ **bên trong** đồ thị khôi phục được giữ theo semantics serialization.

`ObjectInputStream.readObject()` không phải một parser “chỉ đọc dữ liệu thuần”; nó có thể kích hoạt hành vi trong class khi giải tuần tự hóa, bao gồm hook và quá trình dựng object. Đây là một nguyên nhân chính khiến input không tin cậy nguy hiểm.

## 4. Đồ thị đối tượng được lưu như thế nào?

Một đồ thị thường có nhiều object liên kết với nhau. Ví dụ:

```java
final class Node implements Serializable {
    private static final long serialVersionUID = 1L;

    String name;
    Node next;

    Node(String name) {
        this.name = name;
    }
}
```

Đây là class minh họa nằm trong cùng package/file phù hợp và cần import `Serializable`. Nếu:

```java
Node a = new Node("A");
Node b = new Node("B");
a.next = b;
b.next = a;
```

thì đồ thị có vòng `A → B → A`.

Java serialization không đơn giản truy vết đệ quy vô hạn. `ObjectOutputStream` quản lý các **handle tham chiếu trong stream**. Khi gặp lại một object đã xuất hiện, stream có thể ghi tham chiếu tới handle của object ấy thay vì vô hạn lần ghi lại toàn bộ object.

Khi giải tuần tự hóa:

- Các object tương ứng được tạo lại.
- Các reference field được gán để tái lập quan hệ.
- Vòng tham chiếu có thể được phục hồi.
- Hai field trước đây trỏ cùng một object trong phạm vi đồ thị được viết chung sẽ lại trỏ cùng một object **mới** trong đồ thị phục hồi.

Điểm cần nắm: **object identity bên trong đồ thị được bảo toàn**, còn object phục hồi không có cùng identity với object gốc còn sống ở JVM ban đầu.

### Identity khác equality

- `a == b`: hai reference chỉ cùng object instance không?
- `a.equals(b)`: logic so sánh theo định nghĩa class, có thể bằng nhau dù hai object khác instance.

Khi học serialization đồ thị, phải dùng `==` để chứng minh chia sẻ tham chiếu được phục hồi. Gọi `equals` có thể chỉ chứng minh field giống nhau, **không** chứng minh alias.

## 5. Chương trình Java 17+ hoàn chỉnh: shared references, vòng và transient

Ví dụ này chỉ sử dụng `ByteArrayOutputStream` và `ByteArrayInputStream` để dễ chạy mà không phụ thuộc file hệ thống. Các quan hệ object graph được xây dựng rõ ràng:

- Một danh sách chứa `alice` ở index 0 và 2, chứng tỏ **cùng tham chiếu**.
- `alice.friend = bob` và `bob.friend = alice` tạo **vòng hai chiều**.
- Field `sessionToken` đánh dấu `transient`, nên sau giải tuần tự hóa nhận giá trị mặc định `null`.
- `serialVersionUID` khai báo rõ cho class tham gia serialization.
- Các dòng stdout không dựa vào kích thước file hay chi tiết byte format.

Lưu file tên **`SerializationGraphDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class SerializationGraphDemo {

    private static final class Person implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String name;
        private Person friend;
        private transient String sessionToken;

        private Person(String name, String sessionToken) {
            this.name = name;
            this.sessionToken = sessionToken;
        }
    }

    public static void main(String[] args) throws Exception {
        Person alice = new Person("Alice", "secret-a");
        Person bob = new Person("Bob", "secret-b");

        alice.friend = bob;
        bob.friend = alice;

        List<Person> team = new ArrayList<>();
        team.add(alice);
        team.add(bob);
        team.add(alice); // Cùng instance với team.get(0).

        byte[] serialized;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(team);
            output.flush();
            serialized = bytes.toByteArray();
        }

        List<?> restored;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(serialized))) {
            restored = (List<?>) input.readObject();
        }

        Person restoredAlice = (Person) restored.get(0);
        Person restoredBob = (Person) restored.get(1);

        System.out.println("List size: " + restored.size());
        System.out.println("Names: "
                + restoredAlice.name + ", " + restoredBob.name);
        System.out.println("Shared reference: "
                + (restoredAlice == restored.get(2)));
        System.out.println("Cycle restored: "
                + (restoredAlice.friend == restoredBob
                    && restoredBob.friend == restoredAlice));
        System.out.println("Transient is null: "
                + (restoredAlice.sessionToken == null));
        System.out.println("Original differs: "
                + (restoredAlice != alice));
    }
}
```

Chạy với Java 17+:

```bash
javac SerializationGraphDemo.java
java SerializationGraphDemo
```

**Stdout chính xác:**

```text
List size: 3
Names: Alice, Bob
Shared reference: true
Cycle restored: true
Transient is null: true
Original differs: true
```

Tại sao kết quả như vậy?

1. `ArrayList` là serializable, vì vậy object danh sách cùng các `Person` có thể được ghi.
2. `Person` triển khai `Serializable` và chứa `name` là `String` (serializable), `friend` trỏ sang `Person` (serializable) và `sessionToken` là transient.
3. Khi `alice` gặp lại ở index 2, ObjectOutputStream lưu quan hệ handle/alias thích hợp; khi đọc lại, `restored.get(2) == restored.get(0)`.
4. Vòng `alice → bob → alice` được giải tuần tự hóa với reference kết nối đúng, không gây đệ quy vô hạn chỉ vì tồn tại cycle.
5. `sessionToken` không được lưu, vì vậy field của object được khôi phục là `null`. Điều này **không xóa** string bí mật còn tồn tại trong object gốc; đồng thời không nên coi `transient` là một hệ thống quản lý bí mật hoàn chỉnh.
6. `restoredAlice != alice` bởi đây là hai instance khác nhau. Identity chỉ được bảo toàn **trong đồ thị khôi phục**, không phải giữa hai đồ thị ở hai giai đoạn.

**Chú ý:** trong mã ví dụ, `Person` là nested **static** class. Một inner class không static có thể mang reference ngầm tới instance lớp bao; reference ẩn này có thể ảnh hưởng serialization và gây `NotSerializableException`. Khi thiết kế DTO serializable, ưu tiên các class độc lập hoặc static nested class với trạng thái tường minh.

## 6. Những field nào được lưu?

Với cơ chế serialization mặc định của một class thông thường:

| Loại thành phần | Có được ghi mặc định? | Ghi chú |
|---|---|---|
| Instance field non-static, non-transient | Có | Giá trị primitive và reference tới object có thể được xử lý |
| `transient` instance field | Không | Khi đọc lại thường nhận giá trị mặc định hoặc được khôi phục bằng hook |
| `static` field | Không | Thuộc class đang chạy, không gắn với một serialized instance |
| `serialVersionUID` | Không phải dữ liệu instance | Là UID mô tả phiên bản serialization của class |
| Phương thức và bytecode class | Không như state instance | Class tương thích phải có sẵn cho runtime giải tuần tự hóa |
| Field của object được tham chiếu | Có thể | Nếu đi theo graph và kiểu đáp ứng hợp đồng Serializable |

### Transient và giá trị mặc định

`transient` khiến field không được lưu theo cơ chế field mặc định:

```java
class Session implements Serializable {
    private static final long serialVersionUID = 1L;

    String username;
    transient String accessToken;
    transient int retryCounter;
}
```

Khi object `Session` được khôi phục theo serialization mặc định, `accessToken` có thể là `null` và `retryCounter` là `0`. Nếu class có hook `readObject` tự khởi tạo lại các field này thì kết quả có thể khác.

Cần chú ý:

- `transient` ngăn **field đó** bị đưa vào luồng theo cách mặc định, không đảm bảo giá trị nhạy cảm không bị lưu qua field khác/hook custom.
- Mặc định field của object serializable được tái tạo mà không chạy constructor thường của chính class ấy. Nếu constructor gán token mặc định, không dựa vào constructor đó để khôi phục token.
- Nếu một object liên kết với resource như socket, thread, file handle, database connection, nên loại resource ra khỏi form lưu và tạo lại khi cần theo cách có kiểm soát.

### Static không được snapshot theo mỗi object

`static int counter` là thuộc tính của class trong JVM. Ghi một instance không lưu “bản riêng” của counter; sau khi đọc lại, giá trị field static là trạng thái hiện tại của class tại runtime. Vì vậy không thể dùng serialization của một instance để backup toàn bộ global state của ứng dụng.

## 7. Đồ thị chứa đối tượng không Serializable

Đánh dấu root class `Serializable` **không** tự khiến mọi object ở phía sau graph serializable.

Ví dụ:

```java
final class ResourceHolder implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String label;
    private final Thread worker; // Thread không Serializable.

    ResourceHolder(String label, Thread worker) {
        this.label = label;
        this.worker = worker;
    }
}
```

Nếu `worker` không null và object được ghi theo cách mặc định:

```java
output.writeObject(holder);
```

có thể ném **`java.io.NotSerializableException`** vì `Thread` không đáp ứng cơ chế serialization. Hai đoạn này là minh họa, cần đặt trong class/method và khai báo `output`, `holder` tương ứng.

Giải pháp không phải “ép kiểu mọi thứ sang Serializable” một cách mù quáng. Hãy hỏi:

1. Field có thực sự cần được persist không?
2. Nó có đại diện cho **tài nguyên đang hoạt động** không? Nếu có, serialization thường không phải nơi lưu resource đó.
3. Nếu chỉ cần định danh, lưu một ID/string/DTO có thể tái tạo resource sau khi đọc.
4. Nếu field chỉ là cache/handle tạm, đánh dấu `transient` và thiết kế bước tái khởi tạo.
5. Nếu toàn bộ graph quá phức tạp, tạo **mô hình dữ liệu lưu riêng** thay vì serialize trực tiếp domain object.

### Đánh dấu transient có làm graph luôn an toàn?

Không. Các field còn lại vẫn phải serializable, và callback custom serialization có thể đưa giá trị khác vào stream. Chưa kể object bất biến về mặt nghiệp vụ có thể bị phá vỡ sau deserialization nếu kiểm tra không được tái thực hiện.

## 8. Object identity và handle trong một stream

Khi dùng **một `ObjectOutputStream`** và gọi `writeObject` nhiều lần trên cùng object, stream duy trì bảng handle. Ví dụ:

```java
ObjectOutputStream out = ...;
out.writeObject(person);
out.writeObject(person);
```

Nếu không thay đổi cơ chế chia sẻ hay reset stream, lần ghi thứ hai có thể là reference tới object đã được ghi. Khi đọc liên tiếp:

```java
Object first = in.readObject();
Object second = in.readObject();
System.out.println(first == second); // Thường là true trong mẫu này.
```

Hai đoạn chỉ là minh họa, `out`/`in` phải được khai báo, quản lý vòng đời và dùng cùng một serialization stream tương ứng.

**Bẫy “đã sửa object nhưng writeObject lần nữa”**: nếu `person.name` được thay đổi giữa hai lần `writeObject(person)` trên cùng stream, lần thứ hai có thể chỉ ghi tham chiếu, **không snapshot trạng thái mới**. Khi cần bắt đầu một chu kỳ ghi dữ liệu mới với handle table độc lập, `ObjectOutputStream.reset()` có thể được dùng một cách có chủ đích.

`reset()` khiến ObjectOutputStream quên trạng thái tham chiếu đã ghi trước đó cho các object sau reset, nhưng không biến stream thành JSON append log có versioning hoàn chỉnh. Nó cũng không thay thế việc đóng/reopen khi yêu cầu format, consistency hoặc transaction khác.

### writeUnshared/readUnshared

Java có `writeUnshared`/`readUnshared` cho một số tình huống cần tránh chia sẻ handle của object top-level. Đây là các API chuyên biệt, **không phải deep clone đơn giản**: tham chiếu bên trong graph vẫn có ngữ nghĩa riêng. Với bài toán cơ bản, hãy hiểu `writeObject` và cơ chế handle trước khi cần đến `writeUnshared`.

## 9. serialVersionUID và tương thích phiên bản

Một class serializable thông thường nên khai báo rõ:

```java
@Serial
private static final long serialVersionUID = 1L;
```

Trong Java 17, `@Serial` (`java.io.Serial`) giúp compiler/công cụ nhận diện khai báo liên quan serialization. `serialVersionUID` phải là field `static final long` đúng tên, theo quy tắc API.

UID được dùng trong quá trình kiểm tra tương thích class lúc deserialization. Nếu UID của phiên bản class hiện tại không khớp với UID ghi trong stream, runtime thường ném **`InvalidClassException`**.

Vì sao khai báo tường minh?

- Nếu không khai báo, JVM tính UID mặc định dựa trên chi tiết class. Những thay đổi source/biên dịch có thể khiến UID đổi ngoài ý muốn.
- UID rõ ràng khiến quá trình nâng cấp model có thể được kiểm soát tốt hơn.
- Nó **không** đảm bảo mọi thay đổi với cùng UID sẽ tương thích về ngữ nghĩa. Vẫn phải kiểm tra schema, invariants và quy tắc đọc object.

### Thay đổi class giữa hai phiên bản

Giả sử V1:

```java
class Account implements Serializable {
    private static final long serialVersionUID = 1L;
    String id;
}
```

Sau đó V2 thêm field:

```java
class Account implements Serializable {
    private static final long serialVersionUID = 1L;
    String id;
    String displayName;
}
```

Đây là **hai phiên bản minh họa** của cùng một class, không được khai báo cùng lúc trong một file/package. Nếu một stream cũ được đọc bởi V2 theo cơ chế field mặc định tương thích, `displayName` có thể có giá trị mặc định `null`.

Nhưng thêm/bỏ/đổi kiểu field, thay hierarchy hay thay semantic class có thể gây lỗi hoặc tạo trạng thái không hợp lệ. Ví dụ V2 kỳ vọng `displayName` không null thì cần kiểm tra/đặt fallback sau khi đọc; không được giả định constructor luôn chạy để sửa nó.

### Khi nào tăng serialVersionUID?

UID là một phần hợp đồng tương thích. Nếu một thay đổi không còn tương thích và bạn chủ ý chặn việc đọc stream cũ, có thể chọn UID mới. Nếu giữ khả năng đọc cũ, hãy kiểm thử serialization/deserialization chéo phiên bản thực tế. Đừng tăng UID tự động sau **mọi** lần sửa mã, cũng đừng giữ UID cũ mà không thử nghiệm.

### Java serialization không phải format ổn định cho mọi hệ thống

Các object model thay đổi theo version ứng dụng, tên package/class, cấu trúc kế thừa, class loader và custom hooks. Vì vậy không nên dùng serialized object stream làm định dạng lưu trữ lâu dài/công khai nếu yêu cầu tương thích đa ngôn ngữ, migration phức tạp hoặc truyền dữ liệu qua trust boundary.

## 10. Constructor và quá trình tạo object khi giải tuần tự hóa

Một hiểu nhầm phổ biến: “`readObject` gọi constructor của class y như `new`”. Với class `Serializable` thông thường, cơ chế deserialization **không gọi constructor thông thường của chính class đó** để phục hồi các field đã lưu. Constructor không đối số của superclass đầu tiên **không** Serializable trong hierarchy được gọi theo quy tắc serialization.

Ví dụ một class có constructor:

```java
public Profile(String username) {
    if (username == null || username.isBlank()) {
        throw new IllegalArgumentException("Invalid username");
    }
    this.username = username;
}
```

Constructor này chạy khi `new Profile(...)`, nhưng không được xem là lớp kiểm tra sẽ tự chạy lại khi Java phục hồi `Profile` từ serialized stream.

Hệ quả:

- Các bất biến chỉ được kiểm tra trong constructor có thể **không** được áp dụng tự động sau deserialization.
- Các field transient và field mới thường nhận giá trị mặc định trừ khi custom logic xử lý.
- Object có thể phải được validate khi đọc, đặc biệt nếu nó làm đầu vào cho thao tác quan trọng.
- Không deserialize dữ liệu không tin cậy rồi trông chờ constructor chặn mọi trạng thái nguy hiểm.

Với superclass không serializable, constructor không đối số có thể cần khả dụng theo luật truy cập để deserialization của subclass thành công. Nếu không thỏa, có thể xảy ra `InvalidClassException`.

## 11. readObject/writeObject để tùy chỉnh (mức mở rộng)

Một class có thể định nghĩa các hook đặc biệt:

```java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Có thể ghi thêm dữ liệu theo một giao thức custom được quản lý.
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Kiểm tra invariants và khôi phục transient state khi cần.
}
```

Đây là hai **phương thức minh họa** bên trong một class `Serializable`; cần import `Serial`, `ObjectOutputStream`, `ObjectInputStream`, `IOException` và `ClassNotFoundException`.

Chi tiết:

- Phương thức phải theo đúng chữ ký, phạm vi và hợp đồng của Java serialization; không phải override interface method.
- `defaultWriteObject()` và `defaultReadObject()` xử lý tập field serializable mặc định của class.
- Nếu ghi thêm dữ liệu custom, phần đọc phải dùng đúng thứ tự và phiên bản tương ứng.
- `readObject` nên validate bất biến sau khi nhận dữ liệu, có thể ném `InvalidObjectException` cho trạng thái không hợp lệ.
- Hook có thể chạy trong deserialization, khiến byte stream không tin cậy trở nên nguy hiểm; **không** coi custom hook là sandbox.

Đừng thêm hook chỉ để “làm cho ví dụ chạy”: với class đơn giản, default serialization thường đủ để học cơ chế.

### Ví dụ invariant sau đọc

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (id == null || id.isBlank()) {
        throw new InvalidObjectException("Missing id");
    }
}
```

Đoạn này chỉ là method minh họa, field `id` và các import cần có trong class thực tế. Kiểm tra này bổ sung validation khi deserialization, **không** đảm bảo việc mở stream không tin cậy là an toàn: các loại object có thể bị tạo/xử lý trước khi validation của class này kết thúc.

## 12. Serializable, Externalizable và các loại đặc biệt

### Externalizable

`Externalizable` mở rộng `Serializable` và cho phép class chủ động định nghĩa:

- `writeExternal(ObjectOutput out)`
- `readExternal(ObjectInput in)`

Nó yêu cầu trách nhiệm quản lý cấu trúc dữ liệu và thường có yêu cầu constructor public không đối số. Đây là công cụ nâng cao, không phải cách chữa mọi vấn đề về tính tương thích hay bảo mật. Đối với việc học tuần tự hóa cơ bản, `Serializable + ObjectOutputStream/ObjectInputStream` là nền tảng cần hiểu trước.

### Enum

Enum có cơ chế Java serialization đặc biệt: về mặt ngữ nghĩa, enum constant được giải tuần tự hóa thành constant tương ứng của class enum, không phải một bản sao tự do như class thường. Các hook mặc định và `serialVersionUID` của enum có quy tắc riêng. Không dùng enum làm ví dụ điển hình cho việc lưu mọi instance field theo cơ chế class thông thường.

### Record

Java record cũng có semantics serialization riêng khi triển khai `Serializable`. Quá trình dựng record khi giải tuần tự hóa liên quan canonical constructor theo đặc tả, không nên khẳng định mọi class serializable đều bỏ qua constructor trong mọi trường hợp. Nếu đang thiết kế record DTO, xem tài liệu Java phiên bản mục tiêu.

### Array và collection

Nhiều array và các collection chuẩn Java có hỗ trợ serialization, nhưng **một collection serializable không bảo đảm mọi phần tử có thể được ghi**. Ví dụ `ArrayList<Thread>` thường không serializable được khi chứa thread non-null. Xác minh cả đồ thị thực tế chứ không chỉ kiểu của collection root.

## 13. Exception thường gặp và cách chẩn đoán

| Exception | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `NotSerializableException` | Graph có object không serializable | Field/reference nào chưa được loại bỏ hoặc chuyển thành DTO? |
| `InvalidClassException` | UID/class descriptor không tương thích hoặc class không thỏa hợp đồng | Version class, serialVersionUID, hierarchy và field format |
| `StreamCorruptedException` | Header/token stream serialization không hợp lệ | Có dùng đúng ObjectOutputStream ghi nguồn không, stream có bị cắt/lẫn byte? |
| `ClassNotFoundException` | Runtime đọc thiếu class cần dựng object | Package/classpath/class loader có đúng version? |
| `OptionalDataException` | Đọc object/primitive không phù hợp cấu trúc stream hoặc gặp EOF trong trường hợp tương ứng | Thứ tự write/read và custom hooks |
| `EOFException` | Stream kết thúc không theo lượng dữ liệu mong đợi | File có bị cắt hoặc đọc quá số object ghi? |
| `InvalidObjectException` | Custom validation / hook reject object | Bất biến nào không được đáp ứng? |
| `IOException` | Lỗi I/O trong đọc/ghi/đóng stream | Quyền truy cập, tệp, tài nguyên, stream đã đóng... |

Đừng nuốt `NotSerializableException` rồi ghi tiếp vào cùng tệp như thể transaction thành công. Một output stream đã lỗi có thể tạo file không đầy đủ hoặc trạng thái cần bỏ, ghi lại từ đầu qua file tạm sau khi sửa nguyên nhân.

`ClassCastException` cũng có thể xuất hiện khi caller ép object đọc được sang class không đúng; đây không phải IOException nhưng vẫn cần kiểm soát kiểu dữ liệu sau deserialization.

## 14. Bảo mật: tránh deserialize dữ liệu không tin cậy

Java native serialization được thiết kế để dựng **đồ thị object Java**, không phải đọc một bản dữ liệu thuần được sandbox tự động. `readObject` có thể kích hoạt hành vi của class được nạp, kể cả các hook. Một số chuỗi object/class kết hợp có thể gây tiêu thụ CPU/bộ nhớ quá mức hoặc hành vi không mong muốn trong ứng dụng có thư viện dễ bị khai thác.

**Nguyên tắc an toàn:**

1. Không nhận trực tiếp Java serialized bytes từ client, HTTP request, queue công khai, cookie hoặc file do người ngoài kiểm soát rồi gọi `readObject`.
2. Nếu giao tiếp qua trust boundary, ưu tiên **JSON/CBOR/Protocol Buffers/Avro hoặc dạng DTO có schema** và parser với validation rõ ràng. Các định dạng này vẫn cần giới hạn tài nguyên, schema và bảo mật, nhưng tránh đưa toàn bộ cơ chế phục dựng Java object graph vào đầu vào không tin cậy.
3. Với dữ liệu lịch sử bắt buộc dùng Java serialization, chỉ đọc từ nơi tin cậy, đặt **giới hạn byte, độ sâu, số reference, kích thước array và loại class**.
4. Sử dụng `ObjectInputFilter` (JEP 290, có từ Java 9) như **defense in depth** nếu phù hợp.
5. Không xem filter đơn giản là bảo đảm tuyệt đối: filter không được gọi cho mọi trường hợp object giống nhau, và lớp được cho phép vẫn có thể có hành vi bất lợi; xem xét toàn bộ classpath, custom readObject và phiên bản thư viện.
6. Xử lý ngoại lệ deserialization và tránh tiếp tục sử dụng object đã đọc dở.

### ObjectInputFilter trong Java 17

Ví dụ minh họa cơ chế API, **không phải cấu hình production dùng nguyên xi**:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=8;maxrefs=100;maxarray=10000;maxbytes=1048576;"
      + "com.example.dto.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
    // Kiểm tra kiểu và invariants bổ sung.
}
```

Đoạn này cần `ObjectInputFilter`, `ObjectInputStream`, một `InputStream source` và xử lý checked exceptions. Bộ lọc minh họa chỉ cho phép package DTO giả định cùng các giới hạn; một đồ thị thực tế có `ArrayList` hay các class JDK khác có thể bị reject nếu không nằm trong allowlist phù hợp. Không bỏ `!*` để “cho chạy được” khi chưa xác định chính xác mô hình và trust boundary.

`ObjectInputFilter.Config.createFilter(...)` sử dụng một chuỗi pattern; tiêu chí và class allowlist phải được xác minh bằng kiểm thử với các dữ liệu hợp lệ, không tin vào chuỗi mẫu. Cần giới hạn **bytes đọc vào stream** ở tầng bao ngoài nếu yêu cầu; filter không thay thế chính sách kích thước file, timeout và quota ứng dụng.

**Kết luận bảo mật:** ngay cả khi có ObjectInputFilter, native Java deserialization không phải lựa chọn khuyến nghị để parse payload từ nguồn không tin cậy. Giải pháp tốt hơn thường là **tránh Java serialized data tại trust boundary**.

## 15. Persistence: khi nào dùng hay không dùng?

### Phù hợp để học và ứng dụng nội bộ giới hạn

- Demo cách object graph được ghi/khôi phục.
- Lưu snapshot nội bộ tạm thời mà application kiểm soát toàn bộ producer, consumer và version model.
- Di chuyển object giữa các thành phần Java tin cậy trong môi trường có hợp đồng serialization rõ ràng.

Ngay cả khi tin cậy, vẫn phải xem xét **schema/version, độ bền file, lỗi giữa chừng và resource limits**.

### Không nên mặc định dùng làm định dạng lâu dài

- File cấu hình cần con người đọc/sửa và review trên Git.
- API public đa ngôn ngữ.
- Dữ liệu liên tục nâng cấp qua nhiều phiên bản ứng dụng.
- Hệ thống cần query/index/migration dễ quản lý.
- Payload không tin cậy đến từ internet.
- Dữ liệu nhạy cảm cần kiểm soát chính xác điều gì được lưu.

Đối với các nhu cầu đó, nên cân nhắc JSON/YAML/Properties/CSV, database, hoặc schema-based binary formats tùy bài toán. Java serialization lưu **cấu trúc class Java**, nên coupling giữa data và code có thể cao.

### Khác biệt với lưu database

Java serialization không cung cấp:

- Transaction nhiều object/file theo nghĩa database.
- Index, truy vấn theo field và isolation.
- Version migration tự động.
- Quyền truy cập, sao lưu và crash recovery như một hệ DBMS.
- Kiểm soát bảo mật chỉ vì class triển khai Serializable.

Không nên dùng `ObjectOutputStream` như database đa người dùng nếu hệ thống cần tính nhất quán cao.

## 16. Ghi file an toàn hơn bằng tệp tạm

Một thao tác trực tiếp:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(target))) {
    out.writeObject(root);
}
```

có thể làm tệp đích bị ghi dở nếu serialize hoặc I/O thất bại. Với dữ liệu nội bộ cần giữ bản cũ khi có lỗi, nên:

1. Tạo tệp tạm riêng ở **cùng thư mục** với đích.
2. Dùng `ObjectOutputStream` ghi toàn bộ graph và đóng stream thành công.
3. Nếu có yêu cầu, đồng bộ dữ liệu tệp tạm và kiểm tra có thể đọc lại/validate.
4. Move/replace tệp đích theo khả năng filesystem và policy bảo đảm atomic đã định.
5. Dọn tệp tạm khi thất bại và có chiến lược recovery sau crash.

Ví dụ mô hình:

```java
Path target = Path.of("snapshot.ser").toAbsolutePath();
Path temporary = Files.createTempFile(
        target.getParent(), ".snapshot-", ".tmp");

try {
    try (ObjectOutputStream output = new ObjectOutputStream(
            Files.newOutputStream(temporary))) {
        output.writeObject(root);
    }

    Files.move(temporary, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temporary);
}
```

Đây là **đoạn minh họa trong method**, cần imports, xử lý `IOException`, và `root` phải là object serializable. Cần chú ý:

- `ATOMIC_MOVE` có thể không được hỗ trợ; một lần gọi `Files.move` có thể ném `AtomicMoveNotSupportedException`.
- Theo API `Files.move`, khi có `ATOMIC_MOVE`, các option khác bị bỏ qua; nếu target đã tồn tại thì hành vi replace phụ thuộc provider. Không coi đoạn minh họa là bảo đảm portable atomic replacement.
- `finally` chỉ dọn temp trong tiến trình chạy bình thường; mất điện/crash bất ngờ cần cơ chế thu dọn khác.
- Khả năng sống sót qua mất điện còn liên quan đồng bộ dữ liệu và directory metadata; `ObjectOutputStream.close()` không bảo đảm đồng bộ xuống thiết bị lưu trữ.
- Không đọc thử bằng ObjectInputStream nếu nguồn temp có thể bị kẻ khác sửa; giữ thư mục ở vùng tin cậy và áp dụng giới hạn thích hợp.

### Ghi/đọc nhiều object vào một stream

Có thể ghi tuần tự:

```java
out.writeObject(header);
out.writeObject(team);
out.writeObject(metadata);
```

Và đọc đúng thứ tự:

```java
Header h = (Header) in.readObject();
Team t = (Team) in.readObject();
Metadata m = (Metadata) in.readObject();
```

Các dòng này là **mã minh họa**, yêu cầu khai báo `Header`/`Team`/`Metadata` cùng các biến. Đây là một stream chung, nên bảng handle có thể giữ alias qua nhiều lần write. Ứng dụng phải tự định nghĩa versioning và biết số object cần đọc; đừng lặp tới EOF rồi tự đoán cấu trúc vì stream không phải một định dạng message tự mô tả cho mọi bài toán.

## 17. Tối ưu kích thước và hiệu năng

Java native serialization có chi phí từ class descriptors, graph traversal, handle tables, metadata và nhiều đối tượng trung gian. Một số lưu ý:

- Đừng cho rằng kích thước serialized bytes bằng tổng sizeof fields. Nó có overhead format và thông tin graph.
- `ObjectOutputStream` lưu handle cho object đã viết. Với stream kéo dài rất lâu, bảng handle có thể giữ references tới nhiều object; `reset()` có thể giúp giải phóng trạng thái và mở một “lượt snapshot” mới, nhưng thay đổi semantics chia sẻ qua các lượt.
- Tránh serialize toàn bộ cache hay object graph lớn khi chỉ cần vài giá trị DTO.
- Nếu cần lưu nhiều record độc lập với random access, một stream tuần tự không tự có index. Có thể cần định dạng record riêng hoặc database.
- Có thể bọc stream bằng `BufferedOutputStream`/`BufferedInputStream` để giảm số lần I/O trên một số nguồn; benchmark theo use case.
- Nếu dùng `GZIPOutputStream` bọc `ObjectOutputStream`, xác định đúng thứ tự filter; ví dụ `new ObjectOutputStream(new GZIPOutputStream(raw))` làm byte serialization được nén trước khi ra raw. Đóng wrapper ngoài sẽ đóng các layer dưới và hoàn tất gzip.
- Đừng dùng nén làm bảo mật: serialized data nén vẫn có thể chứa thông tin nhạy cảm, và giải nén một stream không tin cậy có thêm rủi ro bomb.

### Nén serialization stream — ví dụ minh họa

```java
try (OutputStream file = Files.newOutputStream(path);
     GZIPOutputStream gzip = new GZIPOutputStream(file);
     ObjectOutputStream objectOut = new ObjectOutputStream(gzip)) {
    objectOut.writeObject(root);
}
```

Các biến `path` và `root` cần được khai báo. Đọc lại tương ứng `new ObjectInputStream(new GZIPInputStream(Files.newInputStream(path)))`. Cả Java object stream và gzip đều có header, và **thứ tự wrapper phải đối xứng**; không cố đọc byte GZIP trực tiếp bằng ObjectInputStream.

## 18. Lỗi thiết kế thường gặp

1. **Chỉ implements Serializable ở root rồi tưởng mọi field đều an toàn.** Một reference non-transient tới object không serializable có thể gây `NotSerializableException`.
2. **Nhầm Serialization với JSON.** Đây là định dạng byte riêng của Java, không phải file văn bản đọc bằng text editor.
3. **Nhầm equals với identity.** Dùng `==` để kiểm tra alias/reference sharing sau khi restore graph.
4. **Không xét vòng tham chiếu.** Java serialization có quản lý handles, nhưng serializer khác không nhất thiết tự giữ vòng như vậy.
5. **Lưu trực tiếp file handle, thread hoặc connection trong object graph.** Những resource đang chạy không nên được kỳ vọng phục hồi từ một byte stream.
6. **Quên transient cho state không cần persist.** Token/cache/tài nguyên ngắn hạn có thể vô tình trở thành phần dữ liệu lưu nếu Serializable.
7. **Coi transient là mã hóa.** Nó chỉ bỏ field theo cách lưu mặc định; không thay cơ chế bảo mật.
8. **Coi static là trạng thái được lưu theo instance.** Java serialization mặc định không snapshot static fields.
9. **Không khai báo serialVersionUID và không kiểm thử phiên bản.** Thay đổi class có thể làm dữ liệu cũ không đọc được.
10. **Giữ serialVersionUID giống nhau nhưng giả định mọi sửa đổi đều tương thích.** Cần validation và test schema thực tế.
11. **Dựa vào constructor để validate sau deserialization.** Constructor thường của Serializable class không được gọi theo cách `new` trong quá trình restore.
12. **Không đọc đến đúng thứ tự object đã ghi.** Object stream có cấu trúc; đọc sai thứ tự có thể gây cast lỗi hoặc dữ liệu không mong muốn.
13. **Ghi lại cùng object trên một ObjectOutputStream mà tưởng mỗi lần là snapshot mới.** Handle table có thể khiến lần sau là reference.
14. **Không xử lý NotSerializableException/InvalidClassException.** File có thể dở hoặc dữ liệu không phù hợp version.
15. **Giải tuần tự hóa input không tin cậy.** Đây là bề mặt tấn công nghiêm trọng, filter không đủ thay thế lựa chọn định dạng an toàn.
16. **Không giới hạn byte/depth/refs/arrays.** Dữ liệu lớn/phức tạp có thể gây cạn tài nguyên.
17. **Dùng serialized objects như database lâu dài.** Khó migration/query/transaction/interop.
18. **Ghi trực tiếp đè bản lưu duy nhất.** Crash giữa chừng có thể làm mất snapshot cũ.
19. **Tin rằng close là fsync.** Việc đóng stream không cam kết durability qua mất điện.
20. **Thiếu kiểm tra kiểu và invariant sau readObject.** Object phục hồi cần phù hợp trạng thái nghiệp vụ hiện hành.
21. **Sử dụng inner class không static vô ý.** Reference ngầm đến outer instance có thể khiến đồ thị khó serialize.
22. **Ghi graph chia sẻ nhưng tưởng sẽ tạo bản copy tách rời cho mỗi reference.** Cơ chế handle bảo toàn chia sẻ trong stream.
23. **Kỳ vọng một serialized object tự mang toàn bộ bytecode của class.** Runtime đọc phải có class phù hợp để dựng lại.
24. **Quên close ObjectInputStream/ObjectOutputStream.** Tài nguyên rò rỉ, byte cuối chưa flush hoặc file dở.
25. **Dùng ObjectInputFilter như bảo đảm chống mọi payload độc hại.** Cần threat model, allowlist, giới hạn và tốt nhất tránh native deserialization ở trust boundary.

## 19. Bài tập thực hành

### Bài 1: Vòng ba nút

Tạo ba `Node` A, B, C với `A.next=B`, `B.next=C`, `C.next=A`. Serialize A rồi deserialize thành A2. Kiểm tra:

```java
boolean cycle = a2.next.next.next == a2;
```

Nếu khôi phục đúng graph, `cycle == true`. Không dùng `toString` đệ quy vô hạn để in chuỗi node.

### Bài 2: Cùng một đối tượng ở hai field

Tạo object `Order` có hai field `billingAddress` và `shippingAddress` cùng trỏ một instance `Address`. Sau deserialize, kiểm tra:

```java
restored.billingAddress == restored.shippingAddress
```

Nếu cùng instance được lưu trong graph, kết quả thường là true theo semantics mặc định. Sau đó đổi bài toán thành hai `Address` khác instance nhưng nội dung bằng nhau và quan sát sự khác biệt.

### Bài 3: Bỏ qua transient

Thêm `transient String token` vào class serializable; gán token trước khi lưu. Sau khi đọc, kiểm tra token là `null` theo cơ chế mặc định; tự giải thích vì sao không thể dùng object cũ để suy ra trạng thái token mới.

### Bài 4: Lỗi non-serializable field

Thêm field `Thread worker` không transient vào một class `Serializable`, gán `new Thread()`. Dự đoán exception khi ghi. Sau đó đổi field thành `transient Thread worker` và xác định cách ứng dụng sẽ khởi tạo lại worker khi cần.

### Bài 5: Kiểm thử nâng cấp phiên bản

Lưu dữ liệu bằng version V1 có `serialVersionUID=1L`. Thêm field ở version V2 vẫn giữ UID, đọc dữ liệu V1, quan sát giá trị mặc định của field mới và bổ sung validation/migration. Sau đó thử UID khác để hiểu `InvalidClassException`. Làm trên dữ liệu thử nghiệm, không thay file production.

### Bài 6: Giới hạn input

Viết lớp DTO lưu tối đa vài trường String và số nguyên. Tạo một format lưu được kiểm soát; so sánh native serialization với JSON/format binary có schema. Đánh giá độ dễ đọc, versioning, kích thước và khả năng parse dữ liệu không tin cậy.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `Serializable` yêu cầu implement method nào?  
**Không yêu cầu method nào.** Đây là marker interface để Java serialization nhận diện lớp.

**Câu 2.** Nếu `root` serializable nhưng tham chiếu `Thread` non-null không transient, ghi root có thể xảy ra gì?  
**`NotSerializableException`**, trừ khi đã custom hóa cấu trúc lưu để không ghi field ấy.

**Câu 3.** Serialize một List chứa cùng object A ở hai vị trí. Deserialize và kiểm tra hai vị trí bằng `==` có ý nghĩa gì?  
**Chứng minh sharing trong graph phục hồi** nếu true; không phải chỉ có giá trị field bằng nhau.

**Câu 4.** Một graph chứa vòng A→B→A có làm ObjectOutputStream đệ quy mãi không?  
**Không theo cơ chế chuẩn**, vì stream quản lý handles tham chiếu khi ghi đồ thị.

**Câu 5.** Field `transient String password` có được mặc định lưu lại không?  
**Không.** Nhưng phải xem custom hooks/field khác và không coi transient là phương pháp bảo mật hoàn chỉnh.

**Câu 6.** `static` field có được snapshot riêng cho mỗi instance không?  
**Không.** Nó thuộc trạng thái class, không phải instance field được lưu mặc định.

**Câu 7.** Giữ serialVersionUID giống nhau có bảo đảm mọi phiên bản đọc được nhau không?  
**Không.** Còn phụ thuộc thay đổi field/hierarchy, custom hooks, logic ứng dụng và compatibility.

**Câu 8.** `readObject` có chạy constructor của Serializable class như gọi `new` không?  
**Không theo cơ chế class Serializable thông thường.** Constructor của superclass đầu tiên không Serializable có vai trò theo đặc tả; record/enum có quy tắc riêng.

**Câu 9.** Vì sao không nhận Java serialized bytes từ một HTTP API công khai rồi gọi `ObjectInputStream.readObject()`?  
**Vì native deserialization có thể kích hoạt dựng object và hook nguy hiểm**; cần định dạng/parsing được kiểm soát và không vượt trust boundary.

**Câu 10.** Nếu ghi cùng một object hai lần lên một ObjectOutputStream và object đã bị thay đổi giữa hai lần, bản ghi thứ hai chắc chắn là snapshot mới không?  
**Không.** Stream có bảng handle; lần ghi sau có thể chỉ là tham chiếu đến object đã ghi trước.

**Câu 11.** `ObjectOutputStream.close()` có bảo đảm file bền qua mất điện không?  
**Không.** Cần chính sách durability và filesystem phù hợp.

**Câu 12.** Lúc nào nên ưu tiên DTO + schema thay vì Serializable?  
**Khi cần public API, dữ liệu không tin cậy, phiên bản lâu dài, nhiều ngôn ngữ hoặc kiểm soát chính xác định dạng lưu.**

## 21. Tóm tắt

- **Java serialization** biến object và **đồ thị đối tượng** thành byte stream, đọc lại bằng `ObjectInputStream`; class thông thường cần triển khai marker `Serializable`.
- **Object graph bao gồm alias và cycle**. Java giữ quan hệ chia sẻ tham chiếu trong phạm vi stream; restored instances khác original instances.
- **Field non-static, non-transient** tham gia serialization mặc định; `transient` không lưu, `static` không phải state instance. Một reference non-serializable có thể khiến ghi thất bại.
- **`serialVersionUID`** quản lý một phần tương thích version; không tự thay migration/testing.
- **Deserialization có thể bỏ qua constructor thường và kích hoạt hook**, nên phải validate invariants, đặc biệt khi class thay đổi.
- **Không deserialize dữ liệu không tin cậy**. `ObjectInputFilter` là lớp bảo vệ bổ sung, không thay thế threat model và định dạng an toàn.
- Với persistence quan trọng, cần **quy trình ghi file an toàn, versioning, giới hạn tài nguyên và recovery**; native serialization không phải database hay transaction.

### Tài liệu tham khảo Java SE 17

- [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html)
- [ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html)
- [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html)
