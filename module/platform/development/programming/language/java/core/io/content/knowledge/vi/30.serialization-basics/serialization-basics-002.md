# ObjectOutputStream và ObjectInputStream trong Java: tuần tự hóa và khôi phục đối tượng

## 1. Tuần tự hóa (serialization) là gì?

**Tuần tự hóa đối tượng** là quá trình chuyển một đồ thị đối tượng Java sang dạng byte theo giao thức Java Object Serialization. **Giải tuần tự hóa** (deserialization) là quá trình đọc lại byte đó và khôi phục các đối tượng cùng quan hệ tham chiếu theo quy tắc của giao thức.

Java Core I/O cung cấp:

- `java.io.ObjectOutputStream`: ghi object graph, primitive values và các giá trị khác vào một `OutputStream` bên dưới.
- `java.io.ObjectInputStream`: đọc từ một `InputStream` chứa dữ liệu theo định dạng Java Object Serialization, khôi phục object graph.
- `java.io.Serializable`: marker interface (không có phương thức) thông báo lớp có thể tham gia cơ chế tuần tự hóa chuẩn.
- `java.io.Externalizable`: giao diện cho trường hợp lớp tự chịu trách nhiệm định dạng dữ liệu qua `writeExternal`/`readExternal`, khác với `Serializable` mặc định.

Bài học tập trung vào **`ObjectOutputStream` và `ObjectInputStream`**, cách kết hợp `Serializable`, metadata lớp, vòng đời stream, những trường được giữ/bỏ, xử lý lỗi, tính tương thích phiên bản và an toàn khi đọc dữ liệu từ bên ngoài.

> **Điểm quan trọng:** Java Object Serialization là định dạng nhị phân dành cho hệ sinh thái Java; nó **không** phải JSON, không phải chỉ ghi chuỗi `toString()`, không phải snapshot toàn bộ bộ nhớ JVM, và không mặc định mã hóa hoặc xác thực dữ liệu. Không dùng `ObjectInputStream` để giải tuần tự hóa dữ liệu **không đáng tin cậy** nếu không có kiến trúc, kiểm soát và chính sách bảo mật phù hợp; trong nhiều trường hợp nên chọn định dạng dữ liệu an toàn hơn.

## 2. Luồng dữ liệu đi qua các lớp nào?

```text
GHI                                              ĐỌC
---                                              ---
Đối tượng Java                                   Đối tượng Java
    |                                                 ^
    v                                                 |
ObjectOutputStream.writeObject(obj)         ObjectInputStream.readObject()
    |                                                 ^
    v                                                 |
Các byte theo Java serialization protocol       Parse stream + dựng object graph
    |                                                 ^
    v                                                 |
OutputStream                                    InputStream
    |                                                 ^
    +--> File / socket / memory ----------------------+
```

Một ứng dụng có thể kết hợp với `Files.newOutputStream(path)`, `FileOutputStream`, `BufferedOutputStream`, `ByteArrayOutputStream`, `Socket.getOutputStream()` hay các stream khác. Đọc bằng các lớp input tương ứng. **Stream bên dưới phải mang đúng định dạng mà phía đọc kỳ vọng**.

Ví dụ khuôn mẫu:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(file))) {
    out.writeObject(myObject);
}

try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(file))) {
    Object restored = in.readObject();
}
```

Đây là **đoạn minh họa trong một phương thức**, không phải class độc lập: cần `file`, `myObject`, các import thích hợp và xử lý `IOException` / `ClassNotFoundException`. Việc dùng `try-with-resources` bảo đảm stream được đóng kể cả khi có lỗi.

## 3. Điều kiện: lớp phải hỗ trợ `Serializable`

Lớp cần được lưu bằng cơ chế mặc định thường triển khai `java.io.Serializable`:

```java
import java.io.Serializable;

public class Student implements Serializable {
    private static final long serialVersionUID = 1L;

    private String name;
    private int age;

    public Student(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Đây là class có thể biên dịch riêng trong `Student.java`. `Serializable` là **marker interface**: không cần implement một phương thức bắt buộc. Java serialization dùng cơ chế nội bộ để ghi dữ liệu của các field không thuộc diện loại trừ và đủ điều kiện.

### 3.1. Có phải field nào cũng được ghi?

Quy tắc mặc định cho một lớp `Serializable`:

| Loại field | Ghi theo serialization mặc định? | Giải thích |
| --- | --- | --- |
| Instance field thông thường (`int`, `String`, object serializable...) | Có | Ghi giá trị và các object tham chiếu trong graph |
| `private` instance field | Có | `private` **không** ngăn tuần tự hóa |
| `final` instance field | Có thể có | Giá trị được lưu/khôi phục theo giao thức, không phụ thuộc setter |
| `static` | Không | Thuộc về class/JVM, không phải state riêng của instance |
| `transient` | Không trong dạng mặc định | Khi đọc lại nhận giá trị mặc định nếu không có logic tùy chỉnh |
| Field tham chiếu object không serializable | Có thể gây `NotSerializableException` | Không thể lưu toàn graph bằng cơ chế mặc định nếu gặp object không serializable |

`transient` chỉ tác động cơ chế **ghi field mặc định**; không bảo đảm giá trị bí mật bị xóa khỏi RAM, không bảo đảm object đó không được ghi qua field khác hoặc qua logic `writeObject()` tùy chỉnh.

### 3.2. Serializable áp dụng cho cả đồ thị đối tượng

Nếu `Order` triển khai `Serializable` nhưng chứa field `PaymentGateway gateway` (không serializable) và field ấy không `transient`, `out.writeObject(order)` thường ném `NotSerializableException` khi tới đối tượng `gateway`.

Các hướng giải quyết có chủ đích:

- Chỉ lưu dữ liệu cần thiết; đánh dấu phụ thuộc runtime như connection, executor, logger state hoặc service client là `transient`.
- Thiết kế DTO serializable độc lập với service/runtime objects.
- Không ép một thư viện hoặc class bên thứ ba thành `Serializable` bằng thay đổi tùy tiện.
- Nếu cần giữ trạng thái dưới định dạng ổn định, cân nhắc JSON/CBOR/Protobuf hoặc schema phù hợp hơn thay vì serialize nguyên object domain.

Một object graph có thể chứa vòng tham chiếu và các object dùng chung; Java serialization theo dõi **identity của các object đã ghi** để ghi tham chiếu tương ứng. Điều đó dẫn tới hành vi quan trọng ở phần sau.

## 4. Ví dụ Java 17+ hoàn chỉnh: ghi, đọc và bảo toàn tham chiếu

Ví dụ dùng hai người cùng chia sẻ một object `Address`, ghi đối tượng người thứ nhất hai lần và người thứ hai một lần. Sau khi ghi, chương trình thay đổi một static field để chứng minh **static không nằm trong dữ liệu serialized**; field `transient` được khôi phục thành `null`.

Tạo file **`SerializationDemo.java`**:

```java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.nio.file.Files;
import java.nio.file.Path;

public class SerializationDemo {
    private static final class Address implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String city;

        private Address(String city) {
            this.city = city;
        }
    }

    private static final class Person implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private static String appVersion = "v1";

        private final String name;
        private final Address address;
        private transient String sessionToken;

        private Person(String name, Address address, String token) {
            this.name = name;
            this.address = address;
            this.sessionToken = token;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        Path file = Files.createTempFile("object-stream-", ".bin");

        try {
            Address shared = new Address("Ha Noi");
            Person an = new Person("An", shared, "secret-A");
            Person binh = new Person("Binh", shared, "secret-B");

            try (ObjectOutputStream out =
                    new ObjectOutputStream(Files.newOutputStream(file))) {
                out.writeObject(an);
                out.writeObject(an);   // Cùng identity được ghi lần hai.
                out.writeObject(binh); // Có chung Address với an.
            }

            Person.appVersion = "v2";

            try (ObjectInputStream in =
                    new ObjectInputStream(Files.newInputStream(file))) {

                Person first = (Person) in.readObject();
                Person second = (Person) in.readObject();
                Person third = (Person) in.readObject();

                System.out.println("first: " + first.name
                        + " / " + first.address.city);
                System.out.println("same object twice: " + (first == second));
                System.out.println("shared address: "
                        + (first.address == third.address));
                System.out.println("transient token: " + first.sessionToken);
                System.out.println("static app version: " + Person.appVersion);
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac SerializationDemo.java
java SerializationDemo
```

Kết quả:

```text
first: An / Ha Noi
same object twice: true
shared address: true
transient token: null
static app version: v2
```

**Vì sao ra kết quả đó?**

1. `Person` và `Address` đều `implements Serializable`, vì vậy `ObjectOutputStream` có thể duyệt graph.
2. Lần ghi đầu tiên `an` bao gồm cả `shared`. Lần ghi `an` thứ hai, cùng một stream, thường được biểu diễn thành **back-reference** tới object đã ghi, không sao chép lại field như một object độc lập.
3. `binh` là object `Person` khác nhưng có field `address` trỏ đến **cùng** `Address`; khi giải tuần tự hóa, `first.address == third.address` đúng.
4. `sessionToken` được khai báo `transient`. Reader không gọi constructor `Person(name,address,token)` để gán token; field reference được khôi phục mặc định thành `null`.
5. `appVersion` thuộc class, không phải instance; thay giá trị trong JVM thành `"v2"` trước lúc đọc, kết quả sau đọc vẫn là `"v2"`.

Kết quả so sánh `==` trong ví dụ nhằm chứng minh **identity** bên trong một graph/stream, không phải khẳng định hai lần đọc từ **hai stream mới khác nhau** sẽ cho cùng object instance.

## 5. `ObjectOutputStream`: những thao tác quan trọng

### `writeObject(Object)`

Ghi object theo giao thức Java serialization; nếu object `null`, có thể ghi dấu hiệu `null`. Nếu graph chứa một object không serializable mà không được loại trừ phù hợp, có thể ném `NotSerializableException`.

```java
out.writeObject(student);
out.writeObject(null);
```

Đây là đoạn minh họa trong phạm vi đã mở `ObjectOutputStream out`.

### `writeInt`, `writeBoolean`, `writeUTF` và `DataOutput`

`ObjectOutputStream` triển khai `ObjectOutput`, có các phương thức ghi primitive và UTF string:

```java
out.writeInt(2026);
out.writeBoolean(true);
out.writeUTF("Hello");
out.writeObject(student);
```

Reader **phải đọc cùng thứ tự và đúng loại**:

```java
int year = in.readInt();
boolean flag = in.readBoolean();
String message = in.readUTF();
Student s = (Student) in.readObject();
```

Hai đoạn là code minh họa, giả định hai đầu cùng định dạng, stream và class `Student` phù hợp. Ghi bằng `writeInt` rồi đọc bằng `readObject` là sai giao thức; có thể gặp `OptionalDataException`, `StreamCorruptedException` hoặc lỗi khác tùy ngữ cảnh.

`writeUTF/readUTF` dùng **modified UTF-8** và định dạng độ dài riêng của `DataOutput`/`DataInput`, không phải UTF-8 thuần không header. `writeUTF` giới hạn phần biểu diễn mã hóa của chuỗi ở 65.535 byte và có thể ném `UTFDataFormatException`; đừng dùng nó cho text tùy ý có kích thước lớn.

### `flush()`, `close()`

`flush()` đẩy các byte đang được buffer bởi output stream xuống stream bên dưới theo hợp đồng `Flushable`; nó **không đồng nghĩa** dữ liệu đã được fsync xuống thiết bị bền vững hoặc đã nhận tại phía mạng.

`close()` đóng `ObjectOutputStream` cùng stream bên dưới. Với file đơn giản, hãy dùng `try-with-resources` để tránh tệp dở do không đóng. Nếu cần độ bền ghi qua crash, áp dụng riêng cơ chế flush/force ở tầng file/channel và thiết kế atomic write phù hợp.

### `writeUnshared(Object)` và `reset()`

`ObjectOutputStream` mặc định quản lý bảng object handles để bảo toàn reference. Các API `writeUnshared` và `reset` thay đổi cách stream xử lý chia sẻ object, nhưng **không nên diễn giải chúng là “deep clone” bảo đảm cho mọi object con**.

- `writeUnshared(obj)` yêu cầu ghi root object như giá trị chưa chia sẻ theo quy tắc giao thức; các object con mà root tham chiếu vẫn có thể được chia sẻ bằng cơ chế mặc định.
- `reset()` xóa trạng thái bảng reference của stream để các object được ghi sau đó không dùng back-reference của phần trước. Reader theo giao thức cũng nhận marker reset tương ứng.
- Không gọi `reset()` tùy tiện bên trong quá trình đang serialize một object graph đang active; API có quy tắc và có thể ném `IOException`.

## 6. `ObjectInputStream`: đọc dữ liệu và ngoại lệ

Tạo `ObjectInputStream` từ stream đã có header serialization, rồi gọi `readObject()`:

```java
try (ObjectInputStream in =
        new ObjectInputStream(Files.newInputStream(file))) {
    Object value = in.readObject();
    if (value instanceof Student student) {
        System.out.println(student);
    } else {
        throw new IOException("Unexpected object type");
    }
}
```

Đây là ví dụ trong phương thức, với biến `file` và lớp `Student` có sẵn; pattern matching `instanceof` dùng được trong Java 17.

`readObject()` khai báo `IOException` và `ClassNotFoundException`. Trước khi sử dụng, phải kiểm tra **type dự kiến**. Tuy vậy, kiểm tra `instanceof` **sau** `readObject()` không ngăn các đối tượng độc hại đã tham gia quá trình giải tuần tự hóa; kiểm soát an toàn cần diễn ra từ **trước khi** gọi `readObject()` và ở tầng thiết kế nguồn dữ liệu.

### 6.1. Đọc đúng số object

Nếu writer đã ghi ba object, reader nên đọc đúng ba object, hoặc dùng một protocol riêng khai báo số lượng. Không giả định chỉ cần gọi `readObject()` mãi rồi có một `null` sentinel tự động khi hết tệp.

Nếu gọi `readObject()` khi không còn dữ liệu hợp lệ, thường gặp `EOFException`. Đừng tự nuốt mọi `IOException` rồi coi là EOF: một stream bị hỏng hoặc bị cắt giữa object phải được xử lý như lỗi dữ liệu. Có thể chọn `writeInt(count)` trước một danh sách đối tượng nếu định dạng do chính ứng dụng kiểm soát, rồi reader đọc đúng số lượng ấy, với quota hợp lý.

### 6.2. Header và đồng bộ hai đầu socket

Constructor `ObjectOutputStream` ghi một **serialization stream header**. Constructor `ObjectInputStream` cần đọc và xác nhận header; nếu stream là socket và peer chưa ghi/flush header, quá trình tạo input stream có thể **chặn**.

Nếu hai peer đều tạo `ObjectInputStream` trước, cả hai có thể đợi nhau vì chưa ai gửi header. Với ứng dụng có giao thức đủ tin cậy để dùng serialization, tạo output stream trước và **`flush()` header**, sau đó tạo input stream:

```java
ObjectOutputStream out =
        new ObjectOutputStream(socket.getOutputStream());
out.flush(); // Cho peer đọc được serialization header.
ObjectInputStream in =
        new ObjectInputStream(socket.getInputStream());
```

Đây là đoạn minh họa, `socket` đã kết nối và ownership của stream/channel phải được quản lý rõ. Nếu lặp lại `new ObjectOutputStream` trên cùng một socket giữa chừng không có framing/protocol thống nhất, bạn có thể ghi nhiều header vào luồng và phá định dạng mà reader đang kỳ vọng.

**Lưu ý bảo mật:** gửi object Java qua socket chỉ phù hợp giữa các đầu mút **tin cậy và kiểm soát được**, vẫn cần authentication, giới hạn tài nguyên và chính sách class nếu có đọc object; không biến Object Serialization thành network protocol cho client không đáng tin cậy.

## 7. Object identity, handle table và hiệu ứng “dữ liệu cũ”

Một hành vi dễ gây bất ngờ: sau lần `writeObject(obj)` đầu, sửa field của **cùng instance** rồi gọi `writeObject(obj)` lần hai trên **cùng `ObjectOutputStream`** không nhất thiết ghi lại giá trị mới. Writer có thể chỉ phát back-reference tới object đã ghi.

```java
MutableValue value = new MutableValue("old");
out.writeObject(value);

value.setText("new");
out.writeObject(value); // Back-reference có thể được ghi.
```

Đây là snippet trong phương thức (với class `MutableValue` serializable và `out` đã mở). Reader đọc hai lần có thể nhận **cùng một object** mang giá trị ban đầu `"old"`. Đó không phải lỗi ngẫu nhiên: stream có cơ chế tham chiếu/identity.

Nếu mục tiêu là ghi các snapshot riêng theo thời gian, nên thiết kế các DTO/snapshot **instance độc lập**, hoặc cân nhắc `out.reset()` khi phù hợp với protocol trước khi viết lại. `reset()` có thể làm stream lớn hơn vì không tận dụng reference cũ; không dùng nó bừa bãi như cách chữa lỗi mọi trường hợp.

### 7.1. `readUnshared()` không phải lệnh clone chung

`ObjectInputStream.readUnshared()` có quy tắc riêng tương ứng với dữ liệu được ghi theo cơ chế unshared; nếu một root là back-reference trong trường hợp không hợp lệ, có thể ném `ObjectStreamException`. Không dùng `readUnshared` vô điều kiện để giải quyết thiết kế graph. Dữ liệu nghiệp vụ có thể cần DTO mapping với semantics độc lập rõ ràng.

## 8. `serialVersionUID` và tương thích phiên bản

`serialVersionUID` là định danh phiên bản serialization của một lớp `Serializable`, kiểu `static final long`. Nó giúp kiểm tra sự tương thích của mô tả lớp khi reader khôi phục dữ liệu.

```java
@Serial
private static final long serialVersionUID = 1L;
```

Lệnh trên được đặt bên trong class `Serializable`, sử dụng `import java.io.Serial;` (annotation này có từ Java 14). Có thể không khai báo UID, khi đó Java tính một giá trị mặc định dựa trên cấu trúc lớp; cách đó **dễ thay đổi ngoài dự kiến** khi sửa code và không phù hợp cho dữ liệu cần đọc qua nhiều phiên bản.

| Thay đổi giữa writer và reader | Rủi ro/tác động |
| --- | --- |
| Đổi `serialVersionUID` | Thường `InvalidClassException` khi định danh không khớp |
| Thêm instance field thông thường | Có thể tương thích trong serialization mặc định; field mới nhận giá trị mặc định khi đọc stream cũ |
| Bỏ một instance field | Có thể tương thích; field cũ trong stream bị bỏ qua nếu không còn trong class reader |
| Đổi kiểu field, class hierarchy hoặc semantics | Có thể không tương thích, gây lỗi hoặc khôi phục dữ liệu sai nghiệp vụ |
| Đổi class name/package | Tên class trong stream không còn resolve trực tiếp, có thể `ClassNotFoundException` |
| Bỏ `Serializable` hoặc đổi cơ chế serialize | Có thể làm stream cũ không đọc được |

**Giữ nguyên UID không biến mọi thay đổi trở thành tương thích.** Nó chỉ tham gia kiểm tra phiên bản; bạn vẫn phải kiểm thử các trường hợp đọc dữ liệu phiên bản cũ, validate invariant và xử lý dữ liệu mặc định.

Ví dụ nếu `age` là field mới được thêm, reader của lớp mới đọc stream cũ có thể nhận `age=0`, không tự chạy constructor để đặt `age=18`. Nếu `0` không hợp lệ trong nghiệp vụ, hãy có bước validate/migrate trạng thái sau khi đọc.

Serialization không thay thế cơ chế migration schema của một kho lưu trữ lâu dài. Với dữ liệu cần bảo trì qua nhiều năm, format rõ ràng và versioned DTO thường tốt hơn serialized domain objects.

## 9. Constructor, `transient` và giá trị mặc định

Điểm dễ nhầm: khi giải tuần tự hóa một object `Serializable`, Java **không gọi constructor bình thường của chính lớp serializable đó** để thiết lập các field đã serialized. Các field được khôi phục theo giao thức. Constructor không đối số của **lớp cha đầu tiên không triển khai `Serializable`** phải phù hợp với quy tắc truy cập của serialization và sẽ được gọi trong quá trình khởi tạo phần superclass không serializable.

Hệ quả:

- Code kiểm tra invariant trong constructor của class serializable **không được dựa vào** như cơ chế bảo vệ dữ liệu đọc vào.
- Field `transient String token` thường khôi phục thành `null` nếu không có logic bổ sung.
- `transient int counter` thường khôi phục thành `0`.
- `static` không được lấy từ stream; nó thuộc trạng thái lớp đang chạy ở JVM.
- `final` field thông thường có thể được điền từ serialized state mặc định, không phải do constructor chạy lúc đọc.

Cần thiết kế việc khởi tạo lại tài nguyên runtime như executor, socket, lock không serializable hoặc cache sau khi đọc theo cách an toàn. Cơ chế hook như `private void readObject(ObjectInputStream in)` và `private void writeObject(ObjectOutputStream out)` là nâng cao, có hợp đồng riêng và có thể gây rủi ro nếu validate không cẩn thận; không cần dùng hook cho bài toán lưu DTO đơn giản.

## 10. Tùy biến serialization ở mức lớp

Nếu một lớp `Serializable` cần kiểm soát cách ghi/đọc field, nó có thể khai báo các phương thức private có chữ ký quy định:

```java
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Có thể ghi thêm dữ liệu ở định dạng do lớp quyết định.
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Validate và khôi phục invariant từ dữ liệu đã được đọc.
}
```

Đây là **hai phương thức minh họa phải đặt bên trong class Serializable** cùng các import `java.io.*`. Nếu dùng, writer và reader phải thống nhất schema phụ; ghi thêm gì thì phải đọc đúng thứ tự/định dạng. Không gọi `readObject` tùy chỉnh bằng tay từ bên ngoài.

Các phương thức `defaultWriteObject()` và `defaultReadObject()` chỉ hợp lệ trong ngữ cảnh callback serialization tương ứng. Không gọi chúng như API ghi/đọc đối tượng tùy ý.

### 10.1. Validate invariant sau khi đọc

Nếu nghiệp vụ đòi `balance >= 0`, class có thể xác nhận điều kiện sau `defaultReadObject`, ném `InvalidObjectException` khi không hợp lệ. Phải nhớ deserialization **có thể không đi qua constructor** kiểm tra dữ liệu. Với dữ liệu không tin cậy, validation sau khi dựng đối tượng **không đủ** để phòng mọi deserialization gadget hoặc tấn công cấp độ runtime.

### 10.2. `readObjectNoData`, `readResolve`, `writeReplace`

Java có các hook nâng cao để tương thích khi class không có dữ liệu trong stream, thay thế object, hoặc duy trì một số pattern object identity. Những hook này ảnh hưởng đến graph/reference và lifecycle, nên chỉ dùng khi hiểu kỹ hợp đồng API và có kiểm thử. Không nên thêm vào các DTO chỉ để “tối ưu” khi chưa có yêu cầu thực sự.

## 11. An toàn: không giải tuần tự hóa byte không đáng tin cậy

**Object deserialization có rủi ro đặc biệt** vì quá trình khôi phục có thể tải lớp và kích hoạt code trong các cơ chế serialization tùy chỉnh (ví dụ `readObject`, `readResolve`, `Externalizable.readExternal`) hoặc cấu trúc gadget từ thư viện có trên classpath. Việc chỉ cast object sau `readObject()` **không ngăn được** các thao tác xảy ra trước đó.

Do đó:

1. **Tốt nhất không dùng Java native object serialization cho dữ liệu do người dùng/Internet không tin cậy gửi tới.** Chọn định dạng với schema rõ ràng, parser giới hạn và validate dữ liệu (JSON, CBOR, Protobuf...) khi phù hợp.
2. Nếu một hệ thống cũ bắt buộc nhận serialized objects, áp dụng cả kiểm soát nguồn (authentication/integrity), cập nhật thư viện, cách ly xử lý, **object deserialization filter**, giới hạn depth/reference/array/bytes và kiểm tra class được phép.
3. Không dùng một rule chỉ chặn vài tên class nguy hiểm: allowlist theo miền đối tượng được phép thường dễ kiểm toán hơn.
4. Không mở một cổng `ObjectInputStream` trực tiếp ra Internet chỉ vì giao thức dễ code; đây là cấu trúc rủi ro cao.
5. Bộ lọc giúp **giảm bề mặt tấn công**, không bảo đảm loại bỏ mọi gadget, side effect, hành vi ứng dụng hoặc lỗ hổng thư viện.

### 11.1. `ObjectInputFilter` trong Java 17+

Java 17 hỗ trợ `java.io.ObjectInputFilter` để áp dụng kiểm soát khi giải tuần tự hóa. Một ví dụ tạo filter dạng pattern **minh họa**:

```java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

// Chạy trước lần readObject() đầu tiên.
// "com.example.dto.*" là package của lớp DTO trong ứng dụng minh họa.
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=100;maxbytes=1048576;maxarray=10000;"
      + "com.example.dto.*;!*");
in.setObjectInputFilter(filter);
```

Đây là **snippet cấu hình**, với `ObjectInputStream in` đã tạo. Thay `com.example.dto.*` bằng **các lớp thật cần được phép** và kiểm thử đầy đủ với object graph hợp lệ; các class ngoài allowlist có thể khiến dữ liệu hợp lệ bị từ chối. Bộ lọc không được diễn giải là kiểm tra mọi byte/string/primitive một cách hoàn hảo và không thay thế schema/business validation. Dòng `!* ` (khi viết thực tế không có khoảng trắng trong pattern `!* `) đặt chính sách từ chối các lớp không được phép phù hợp với pattern.

Có thể cấu hình filter toàn JVM hoặc dùng filter factory tùy môi trường. Quan trọng là chính sách áp dụng **trước khi deserialization**, đồng nhất qua các điểm vào, được kiểm thử với phiên bản JDK/thư viện chạy thực tế. Không viết bộ lọc chỉ để “qua test” rồi cho phép mọi loại class với wildcard `*`.

### 11.2. Giới hạn kích thước tệp và số lượng object

Object serialization chứa thông tin graph/metadata, cho phép nhiều object lồng nhau, mảng lớn, reference graph sâu. Chỉ giới hạn chiều dài file cũng chưa đủ: cần giới hạn depth, số reference, kích thước array, số byte và thời gian xử lý, cộng với hạn mức tổng cho nhiều request đồng thời.

Nếu lưu xuống file, dùng quyền file hạn chế, kiểm soát integrity theo nhu cầu, hạn chế đường dẫn do người dùng cung cấp và không tin rằng file cục bộ là “trusted” khi nhiều tác nhân có thể sửa nó.

### 11.3. Không nhầm `transient` với bảo mật

`transient` hữu ích để bỏ một field khỏi dạng serialization mặc định, nhưng **không mã hóa**, không xóa bản sao trong graph, không ngăn logic tùy chỉnh ghi field ấy, không kiểm soát nơi byte stream được lưu. Secret nên tránh đưa vào object cần serialize; nếu lưu state nhạy cảm, cần cơ chế mã hóa/authentication và quản lý khóa ở tầng thích hợp.

## 12. Quản lý vòng đời stream và hiệu năng

### 12.1. Có nên bọc Buffered streams?

Có thể bọc thêm `BufferedInputStream`/`BufferedOutputStream` khi có ý nghĩa đối với nguồn dữ liệu, nhưng không phải lúc nào cũng cải thiện rõ rệt. Ví dụ:

```java
try (ObjectOutputStream out = new ObjectOutputStream(
        new BufferedOutputStream(Files.newOutputStream(file)))) {
    out.writeObject(data);
}
```

Đây là đoạn minh họa trong phương thức; import `java.io.*` và `java.nio.file.*`, cùng các biến `file`, `data` do ứng dụng cung cấp. Đóng outer stream sẽ đóng underlying stream theo chuỗi wrapper. Đừng đóng underlying stream quá sớm khi `ObjectOutputStream` còn cần ghi.

### 12.2. Không liên tục tạo stream mới trong cùng một file để append

`ObjectOutputStream` ghi **stream header** khi được tạo. Mở lại một `ObjectOutputStream` ở append mode rồi ghi thêm object vào file đã chứa serialized data có thể thêm header ở giữa và khiến `ObjectInputStream` thông thường báo `StreamCorruptedException`.

Nhu cầu append cần một format/protocol được thiết kế riêng hoặc cơ chế quản lý stream liên tục; không chỉ thêm `StandardOpenOption.APPEND` và mong reader tự phân tích nhiều stream headers.

### 12.3. Rò bộ nhớ khi ghi rất nhiều object

Bảng handles của `ObjectOutputStream` giữ thông tin về các object đã xuất hiện trong stream. Với một stream sống lâu và liên tục ghi nhiều object mới, bảng này có thể tăng và tăng chi phí bộ nhớ. Có thể xem xét snapshot batching, quay vòng stream hợp lý hoặc `reset()` ở ranh giới đối tượng **nếu protocol cho phép**, nhưng việc reset làm mất sharing giữa các vùng trước/sau và có thể tăng kích thước stream.

### 12.4. Serialization mặc định không phải format tối ưu cho RPC

Java serialization mang tên lớp và metadata vào luồng, phụ thuộc classpath và serial UID, khó giao tiếp với ngôn ngữ khác và có rủi ro bảo mật cao hơn các định dạng schema được giới hạn. Với giao tiếp dịch vụ và lưu trữ có vòng đời dài, thường nên cân nhắc schema versioned và protocol tường minh.

## 13. Ngoại lệ thường gặp và cách phân biệt

| Ngoại lệ | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NotSerializableException` | Object trong graph không `Serializable` | Chỉ lưu DTO hợp lệ hoặc loại trừ runtime field |
| `InvalidClassException` | Lớp cục bộ không tương thích mô tả serialized class, serialVersionUID khác | Định nghĩa schema/migration, không chỉ ép UID |
| `ClassNotFoundException` | Class trong stream không có/không tìm được ở reader | Kiểm tra classpath, version, package; tránh tin class name trong nguồn không tin cậy |
| `StreamCorruptedException` | Stream header/mã dữ liệu sai hoặc dữ liệu không đúng serialization protocol | Kiểm tra format, append, socket stream alignment |
| `EOFException` | Đọc vượt dữ liệu hiện có hoặc stream bị cắt | Phân biệt EOF kỳ vọng với truncated object |
| `OptionalDataException` | Đọc object trong khi dữ liệu primitive/block-data hoặc trạng thái định dạng khác | Khớp thứ tự `writeInt`/`readInt`, `writeObject`/`readObject` |
| `InvalidObjectException` | Object được nhận nhưng vi phạm invariant do logic validate khi đọc | Xử lý như dữ liệu không hợp lệ |
| `WriteAbortedException` | Ghi object đã abort do lỗi trước đó và reader gặp exception record | Kiểm tra exception gốc và stream integrity |
| `IOException` | Lỗi file/socket/stream nói chung | Đóng stream đúng cách và không giả làm EOF |
| `ClassCastException` | Cast object trả về sai kiểu | Kiểm tra type và hợp đồng dữ liệu |

Nếu reader phản hồi `StreamCorruptedException: invalid stream header`, không lập tức sửa thành công bằng cách bỏ qua các byte đầu: cần xác minh byte stream có thực sự thuộc Java serialization format và chỉ có đúng một header cho luồng đang dùng.

## 14. Phân biệt với các cách ghi dữ liệu khác

| API/cách tiếp cận | Phù hợp | Điểm khác Java Object Serialization |
| --- | --- | --- |
| `DataOutputStream`/`DataInputStream` | Primitive và binary protocol tự định nghĩa | Không tự ghi class metadata/object graph, ứng dụng quản lý thứ tự/schema |
| `ObjectOutputStream`/`ObjectInputStream` | Object graph Java giữa các đầu mút đáng tin, cùng hệ sinh thái | Ghi class descriptor, reference handles, cần Serializable, có rủi ro deserialization |
| `BufferedWriter`/`BufferedReader` | Văn bản thuần | Charset/line format rõ, không serialize object tự động |
| JSON + thư viện phù hợp | Dữ liệu liên hệ giữa dịch vụ và ngôn ngữ khác | Schema và validation tường minh hơn; thư viện cũng cần cấu hình an toàn |
| Protobuf/Avro hoặc schema-based binary | RPC/event/storage versioned | Schema ID/version, field mapping rõ hơn; không lưu Java object identity mặc định |
| JDBC/ORM | Lưu trạng thái nghiệp vụ vào database | Có giao dịch, truy vấn, constraint; không phải snapshot toàn graph Java |

Ngay cả khi một lớp đã implements `Serializable`, nó không mặc nhiên trở thành định dạng lưu trữ bền vững hoặc hợp đồng API ổn định. Serialization là **một cơ chế kỹ thuật**, không thay thế thiết kế dữ liệu.

## 15. Những sai lầm thường gặp

1. **Quên `implements Serializable` ở một đối tượng trong graph:** ném `NotSerializableException`.
2. **Tưởng `private` được bỏ qua:** instance fields `private` vẫn có thể được ghi; dùng `transient` có chủ đích.
3. **Không khai báo `serialVersionUID`:** thay đổi class có thể phát sinh UID mặc định khác, phá tương thích.
4. **Chỉ đổi UID để chữa `InvalidClassException`:** không giải quyết semantic/structural mismatch.
5. **Tưởng deserialization gọi constructor bình thường:** invariant có thể không được khởi tạo như mong muốn.
6. **Thay field của object rồi `writeObject` lại cùng stream:** writer có thể chỉ ghi reference cũ.
7. **Đọc sai thứ tự `writeInt`/`writeObject`:** parser stream bị lệch định dạng.
8. **Tạo `ObjectInputStream` hai phía trước output:** cả hai chờ serialization header, gây deadlock trên socket.
9. **Mở `ObjectOutputStream` mới để append:** thêm stream header giữa file, reader thông thường không xử lý đúng.
10. **Coi EOF là dấu kết thúc object an toàn:** stream có thể bị cắt dở; cần protocol về số lượng và khôi phục lỗi.
11. **Dùng `transient` như mã hóa:** dữ liệu không được bảo mật chỉ bằng marker này.
12. **Deserialize byte từ Internet mà không filter/schema:** rủi ro security gadget và resource exhaustion.
13. **Dùng `readObject()` rồi cast để “lọc class”:** class nguy hiểm có thể được giải tuần tự hóa trước khi cast.
14. **Đóng underlying stream trước outer stream:** có thể làm dữ liệu chưa được flush/ghi đủ.
15. **Serialize object chứa socket, connection, executor:** state runtime thường không serializable hoặc không khôi phục đúng.
16. **Cho rằng stream luôn bảo toàn object thay đổi giữa các lần write:** handle table và `reset` có semantics riêng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Một lớp triển khai `Serializable` nhưng có field tham chiếu object không serializable, không `transient`. `writeObject()` có thể thất bại vì sao?

**Đáp án:** Ghi object graph phải đi qua field ấy. Khi đối tượng đích không serializable và không có cơ chế thay thế hợp lệ, có thể ném `NotSerializableException`.

**Câu 2.** `transient String token` sau khi deserialize mặc định thành gì?

**Đáp án:** `null`, trừ khi class có logic tùy chỉnh khôi phục nó. `transient` không xóa token khỏi RAM hoặc những bản sao ở field khác.

**Câu 3.** Hai field cùng trỏ vào một `Address` trước khi serialize, sau khi read graph có nhất thiết thành hai bản sao không?

**Đáp án:** Không. Java Object Serialization thông thường theo dõi object identity; hai field có thể cùng tham chiếu một instance đã được khôi phục.

**Câu 4.** Cùng một `ObjectOutputStream`, `writeObject(obj)`, sửa field, `writeObject(obj)` lần nữa. Reader có chắc thấy field mới không?

**Đáp án:** Không. Lần hai có thể ghi reference thay vì state mới. Cần thiết kế snapshot và dùng `reset()` hoặc instance độc lập đúng mục đích.

**Câu 5.** `serialVersionUID=1L` được giữ nguyên thì có chắc mọi thay đổi lớp đọc dữ liệu cũ được không?

**Đáp án:** Không. UID là một thành phần kiểm tra compatibility, không bảo đảm mọi thay đổi kiểu field, kế thừa hay invariant đều tương thích.

**Câu 6.** Reader có thể gọi `readObject()` thay cho `readInt()` để lấy integer trước đó được ghi bằng `writeInt()` không?

**Đáp án:** Không; phải đọc cùng định dạng và thứ tự.

**Câu 7.** Vì sao hai đầu socket đều tạo `ObjectInputStream` trước khi tạo output có thể treo?

**Đáp án:** Constructor `ObjectInputStream` chờ stream header, nhưng chưa đầu nào ghi/flush header.

**Câu 8.** Kiểm tra `instanceof TrustedDto` sau `readObject()` có đủ chống malicious deserialization không?

**Đáp án:** Không. Graph có thể đã được dựng và các hook có thể đã thực thi. Cần tránh deserialize untrusted input hoặc dùng filter, quota, isolation và thiết kế schema phù hợp.

**Câu 9.** `static int counter` của class có được khôi phục theo giá trị writer đang có không?

**Đáp án:** Không theo cơ chế mặc định. Static state được quản lý bởi class trong JVM đọc.

**Câu 10.** Có thể dùng Java Object Serialization làm dữ liệu chia sẻ giữa Java và Python mà không có đặc tả bổ sung không?

**Đáp án:** Không phải lựa chọn phù hợp. Đây là format riêng Java; chọn protocol/schema độc lập ngôn ngữ sẽ đơn giản và bền vững hơn.

## 17. Checklist triển khai

- **Phạm vi dữ liệu:** chỉ serialize DTO/object graph thực sự cần thiết; tránh service/runtime state.
- **Class compatibility:** định nghĩa `serialVersionUID` có chủ đích, kiểm thử dữ liệu giữa phiên bản.
- **Field semantics:** phân biệt instance, static, transient, shared reference và object identity.
- **I/O:** đóng stream bằng `try-with-resources`; dùng đúng thứ tự `writeObject` và `readObject`.
- **Protocol:** nếu truyền nhiều object, quy định số lượng, loại, thứ tự và lifecycle stream; xử lý EOF/truncated data riêng.
- **Snapshot:** không mặc định việc ghi lại cùng object sẽ tái ghi field mới; chú ý handle table và `reset()`.
- **Security:** không đọc object stream từ nguồn không tin cậy; với hệ thống cũ bắt buộc dùng, áp dụng `ObjectInputFilter`, allowlist, quota, integrity/authentication, cập nhật dependencies và isolation.
- **Memory:** kiểm soát số object, độ sâu graph, mảng và kích thước stream; tránh lưu object graph khổng lồ không cần thiết.
- **Error handling:** xử lý rõ `ClassNotFoundException`, `InvalidClassException`, `NotSerializableException`, `EOFException` và `IOException`.
- **Chọn công nghệ:** cân nhắc JSON/Protobuf/định dạng schema versioned nếu cần giao tiếp ngoài JVM, storage dài hạn hoặc client không đáng tin.

## Tài liệu chính thức

- Java SE 17 — `ObjectOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html
- Java SE 17 — `ObjectInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html
- Java SE 17 — `Serializable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Java SE 17 — `ObjectInputFilter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html
- Java Object Serialization Specification: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html
- JEP 290 — Filter Incoming Serialization Data: https://openjdk.org/jeps/290
- JEP 415 — Context-Specific Deserialization Filters: https://openjdk.org/jeps/415
