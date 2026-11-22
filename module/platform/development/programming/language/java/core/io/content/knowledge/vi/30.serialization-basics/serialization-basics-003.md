# writeObject, readObject và định dạng stream trong Java Object Serialization

## 1. Từ đối tượng trong bộ nhớ tới luồng byte

**Java Object Serialization** là cơ chế biến trạng thái của một đối tượng Java và các đối tượng có thể đi tới qua các trường tham chiếu của nó thành **một luồng byte có cấu trúc**; quá trình ngược lại khôi phục một đồ thị đối tượng từ luồng đó.

Hai điểm vào thường gặp:

- `ObjectOutputStream.writeObject(obj)`: ghi biểu diễn tuần tự hóa của đối tượng vào `OutputStream`.
- `ObjectInputStream.readObject()`: đọc **đối tượng tiếp theo** trong stream, khôi phục dữ liệu/quan hệ tham chiếu, rồi trả một `Object`.

Hai phương thức không chuyển đối tượng thành JSON hay văn bản. Kết quả là **định dạng nhị phân Java Object Serialization Stream Protocol**, bao gồm header, type tags, class descriptors, field values, object references và dữ liệu bổ sung khi cần.

```text
Đối tượng Java                   LUỒNG NHỊ PHÂN                  Đối tượng Java
Message("HELLO", 7) ──writeObject──▶ AC ED 00 05 ... ──readObject──▶ Message("HELLO", 7)
                                ▲                   │
                        ObjectOutputStream     ObjectInputStream
                                │                   │
                           OutputStream          InputStream
```

Mục tiêu bài: sử dụng chính xác `writeObject`/`readObject`; hiểu những gì được lưu vào stream và cách đọc lại theo đúng thứ tự; phân biệt object data với stream header/class descriptor; nhận biết handle/reference sharing, `serialVersionUID`, `transient`, ngoại lệ và các rủi ro bảo mật của `readObject` trên dữ liệu không tin cậy.

**Lưu ý bảo mật quan trọng:** tuyệt đối không mặc định rằng byte nhận qua mạng, file tải từ bên ngoài hoặc blob người dùng gửi là an toàn để đưa vào `ObjectInputStream`. Giải tuần tự hóa Java có thể kích hoạt các cơ chế khôi phục đối tượng và callback trong classpath; phải ưu tiên giao thức dữ liệu an toàn hơn hoặc áp dụng giới hạn/kiểm soát nghiêm ngặt khi thực sự cần dùng.

## 2. Các lớp và giao diện cần biết

| Thành phần | Vai trò |
|---|---|
| `java.io.Serializable` | Marker interface báo class cho phép Java serialization mặc định |
| `ObjectOutputStream` | Viết đối tượng và dữ liệu primitive thành Object Serialization Stream |
| `ObjectInputStream` | Đọc đối tượng và primitive theo cùng quy tắc stream |
| `ObjectStreamConstants` | Header magic, version và các byte đánh dấu protocol (`TC_*`) |
| `ObjectStreamClass` | Mô tả class serializable; có thể xem `serialVersionUID` và field descriptors |
| `serialVersionUID` | Định danh phiên bản phục vụ kiểm tra tương thích class khi deserialize |
| `transient` | Loại field instance khỏi quá trình lưu mặc định |
| `ObjectInputFilter` | Cơ chế lọc/giới hạn class, độ sâu, tham chiếu, array và bytes khi đọc |
| `Externalizable` | Chế độ mà class tự định nghĩa toàn bộ cách ghi/đọc bằng `writeExternal`/`readExternal` |

Ở mức cơ bản, một class triển khai `Serializable` là đủ để cơ chế mặc định có thể ghi các field phù hợp:

```java
import java.io.Serializable;

public final class Student implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;
    private final int age;

    public Student(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

Đây là class độc lập có thể biên dịch trong `Student.java`, **không có `main`**. Vì `String` serializable và `int` là primitive, trạng thái của instance `Student` này có thể được tuần tự hóa theo cơ chế mặc định. `serialVersionUID` ở đây là field `static final long` mang ý nghĩa kiểm tra phiên bản class, **không** phải dữ liệu instance ghi như một field thông thường.

### 2.1. Serializable không phải một method cần override

`Serializable` là **marker interface**: nó không khai báo `serialize()` hay `deserialize()`. Vì thế:

```java
class Entry implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    int number = 42;
}
```

đã đáp ứng điều kiện cơ bản cho object serialization. Bạn **không bắt buộc** override `writeObject`/`readObject` trong mọi class; API `ObjectOutputStream` sẽ thực hiện cơ chế mặc định.

Nếu có một field tham chiếu đến object không serializable, việc ghi cả đồ thị có thể ném `NotSerializableException`, dù class gốc đã triển khai `Serializable`.

## 3. Tạo ObjectOutputStream và ghi đối tượng

Một `ObjectOutputStream` bọc bên ngoài `OutputStream` bất kỳ như `FileOutputStream`, `ByteArrayOutputStream` hoặc stream của socket:

```java
try (ObjectOutputStream out =
        new ObjectOutputStream(
                new FileOutputStream("student.bin"))) {

    out.writeObject(new Student("Mai", 20));
}
```

Đây là đoạn minh họa trong method xử lý `IOException` và đã có class `Student`. Cần import `java.io.ObjectOutputStream`, `java.io.FileOutputStream`.

Quy trình:

1. Tạo `ObjectOutputStream`. Constructor **ghi stream header** vào output bên dưới.
2. Gọi `writeObject(obj)` để lưu đối tượng.
3. Encoder duyệt đồ thị object có thể tới được qua các field serializable, ghi mô tả class và các giá trị cần thiết.
4. Luồng giữ bảng **handles** để nhận biết những tham chiếu đã được ghi trong stream hiện tại.
5. Khi đóng `ObjectOutputStream`, stream bên dưới cũng được đóng; dùng `try-with-resources` để hạn chế rò rỉ tài nguyên.

Bạn có thể ghi nhiều đối tượng **liên tiếp** trên cùng một `ObjectOutputStream`, sau đó phải đọc lại theo đúng trình tự. Không nên tạo `ObjectOutputStream` mới mỗi lần ghi thêm một đối tượng trên cùng một file rồi hy vọng mỗi header nối tiếp đều được một `ObjectInputStream` duy nhất hiểu như một danh sách object đơn giản.

### 3.1. `writeObject` có thể ghi cả đồ thị

Giả sử:

```java
final class Address implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String city = "Ha Noi";
}
final class Person implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    Address address = new Address();
}
```

Hai class là mã minh họa đặt ở top level trong file Java (không `public`) hoặc nơi hợp lệ tương đương. Khi `out.writeObject(new Person())`, đối tượng `Address` được tham chiếu qua field `address` cũng được ghi, **không cần** gọi `writeObject(address)` riêng.

Nếu `Address` không hỗ trợ serialization và field `address` không transient, việc ghi `Person` có thể thất bại bằng `NotSerializableException`. Cơ chế này không tự chấp nhận mọi object trong graph.

### 3.2. Ghi primitive và đối tượng trong cùng stream

`ObjectOutputStream` còn triển khai `DataOutput`:

```java
out.writeInt(7);
out.writeUTF("xin chao");
out.writeObject(student);
```

Đây là snippet trong phạm vi đã khai báo `out` và `student`. Phía đọc phải đi theo **đúng thứ tự**:

```java
int version = in.readInt();
String title = in.readUTF();
Student student = (Student) in.readObject();
```

`readObject()` **không** được dùng thay `readInt()` để nhận một primitive được ghi bằng `writeInt()`. Trình tự dữ liệu và kiểu đọc không khớp có thể gây `OptionalDataException`, `StreamCorruptedException` hoặc lỗi khác tùy trạng thái stream. Lưu ý `writeUTF` có format *modified UTF-8* thuộc `DataOutput`, không phải cách mã hóa UTF-8 thông thường của mọi byte văn bản.

## 4. ObjectInputStream và cách đọc đối tượng

Ví dụ đọc lại file đã được viết:

```java
try (ObjectInputStream in =
        new ObjectInputStream(
                new FileInputStream("student.bin"))) {

    Object value = in.readObject();
    Student student = (Student) value;
}
```

Đây là snippet nằm trong method khai báo hoặc xử lý `IOException` và `ClassNotFoundException`, đồng thời có class `Student` tương thích trên classpath. `readObject()` trả kiểu tĩnh `Object` vì dữ liệu đầu vào có thể đại diện nhiều class khác nhau; Java không thể dựa vào generic để bảo đảm class được trả về.

**Các bước khi đọc:**

1. Constructor `ObjectInputStream` đọc và kiểm tra header stream.
2. `readObject` đọc type tags và descriptors, giải mã object graph với class phù hợp trong JVM.
3. Với class Serializable mặc định, trạng thái instance được khôi phục theo quy tắc field serialization.
4. Stream duy trì bảng handles ở phía đọc để các reference lặp/cycle được dựng thành quan hệ thích hợp.
5. Caller phải kiểm tra kiểu và **xác minh tính hợp lệ nghiệp vụ** của đối tượng khôi phục; kiểu Java hợp lệ không có nghĩa giá trị luôn đáng tin.

`ObjectInputStream` phải được dùng với dữ liệu thực sự tuân theo Java Object Serialization Stream Protocol. Một file JSON, ZIP hoặc file UTF-8 bất kỳ không thể tự nhiên đọc bằng `ObjectInputStream`.

### 4.1. Constructor có thể chờ header nếu đọc từ socket

`new ObjectInputStream(input)` **có thể block chờ bytes header**. Nếu hai bên của một socket đều tạo `ObjectInputStream` và đợi header trước khi bên nào tạo/flush `ObjectOutputStream`, chương trình có thể bị **deadlock**.

Pattern khi trao đổi giữa hai phía phải được thiết kế cho phù hợp:

```java
ObjectOutputStream out = new ObjectOutputStream(socket.getOutputStream());
out.flush(); // Đẩy header.
ObjectInputStream in = new ObjectInputStream(socket.getInputStream());
```

Đây là snippet với `socket` hợp lệ; không phải chương trình TCP hoàn chỉnh. `flush()` làm cho bytes header do output stream tạo có cơ hội được bên kia nhận, nhưng hai phía vẫn phải thống nhất thứ tự thiết lập và giao thức thông điệp, timeout và vòng đời socket.

## 5. Ví dụ Java 17+ hoàn chỉnh: header, tham chiếu lặp, reset và transient

Ví dụ sau dùng `ByteArrayOutputStream`/`ByteArrayInputStream` để không phụ thuộc file hệ thống. Nó kiểm chứng các khía cạnh quan trọng nhất của `writeObject` và `readObject`: header nhị phân; cùng một object được ghi hai lần; `reset()` tạo ranh giới bảng handle mới; field `transient` không nằm trong trạng thái mặc định.

**Tệp:** `ObjectStreamDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class ObjectStreamDemo {

    private static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        final String text;
        final int sequence;
        transient String secret;

        Message(String text, int sequence, String secret) {
            this.text = text;
            this.sequence = sequence;
            this.secret = secret;
        }
    }

    public static void main(String[] args) throws Exception {
        Message original = new Message("Xin chao", 7, "TOKEN");
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(original);
            out.writeObject(original); // Bảng handle: đã ghi instance này.
            out.reset();              // Xóa các handle đã nhớ.
            out.writeObject(original); // Ghi một biểu diễn object mới.
        }

        byte[] wire = sink.toByteArray();
        System.out.printf(
                "header: %02X %02X %02X %02X%n",
                wire[0] & 0xFF,
                wire[1] & 0xFF,
                wire[2] & 0xFF,
                wire[3] & 0xFF);

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(wire))) {

            Message first = (Message) in.readObject();
            Message second = (Message) in.readObject();
            Message third = (Message) in.readObject();

            System.out.println("text: " + first.text
                    + ", sequence: " + first.sequence);
            System.out.println("first==second: " + (first == second));
            System.out.println("first==third: " + (first == third));
            System.out.println("transient restored: " + first.secret);
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ObjectStreamDemo.java
java ObjectStreamDemo
```

**Stdout chính xác của ví dụ:**

```text
header: AC ED 00 05
text: Xin chao, sequence: 7
first==second: true
first==third: false
transient restored: null
```

**Vì sao có kết quả đó?**

1. Java serialization stream mặc định bắt đầu bằng magic `AC ED` và version `00 05`, tức `STREAM_MAGIC=0xACED` và `STREAM_VERSION=5`.
2. Lần `writeObject(original)` đầu lưu thông tin class và object; lần thứ hai trên **cùng instance** trong **cùng handle table** sử dụng tham chiếu tới object đã ghi. Vì thế hai lần `readObject` đầu trả về **cùng một instance** phía đọc (`== true`).
3. `out.reset()` xóa trạng thái handles của stream theo contract và ghi token reset. Lần ghi thứ ba tạo biểu diễn mới; phía đọc cũng đặt lại context, nên object thứ ba **khác reference** (`== false`).
4. Field `secret` được khai báo `transient`, do đó cơ chế mặc định **không lưu giá trị `"TOKEN"`**. Sau khi deserialize, field tham chiếu có giá trị mặc định `null`. 
5. `text` và `sequence` được khôi phục vì là các field instance serializable thông thường, class tương thích và có dữ liệu hợp lệ.

Mã đã được chạy kiểm chứng trên JDK. File nguồn trong ví dụ dùng văn bản ASCII để output ổn định cả trên terminal không hỗ trợ Unicode; bài học không hàm ý Java serialization chỉ xử lý ASCII.

## 6. Định dạng Object Serialization Stream Protocol

### 6.1. Stream header: `AC ED 00 05`

Luồng được tạo bởi `ObjectOutputStream` thường có cấu trúc cấp cao:

```text
+------------------------------+
| STREAM_MAGIC                 | 2 byte: AC ED
+------------------------------+
| STREAM_VERSION               | 2 byte: 00 05
+------------------------------+
| Contents                     |
| - object/string/array tokens |
| - class descriptors          |
| - primitive / block data     |
| - reference handles          |
| - optional custom data       |
+------------------------------+
```

`ObjectInputStream` dùng header này để nhận diện định dạng. Nếu bốn byte đầu không đúng, constructor có thể ném `StreamCorruptedException`, ví dụ khi bạn vô tình dùng nó đọc file text hay JSON.

**Đừng nhầm:** “version 5” trong stream header là **phiên bản protocol stream**, không phải Java 5, không phải JDK 17/21 và không phải `serialVersionUID` của class. Một stream vẫn có version 5 dù ứng dụng biên dịch bằng JDK hiện đại.

### 6.2. Type tags chính

Các token nằm trong `ObjectStreamConstants`; khi đọc hex, bạn có thể nhận ra:

| Token | Giá trị hex | Ý nghĩa khái quát |
|---|---|---|
| `TC_NULL` | `70` | Tham chiếu null |
| `TC_REFERENCE` | `71` | Tham chiếu tới object/descriptor đã có handle |
| `TC_CLASSDESC` | `72` | Class descriptor mới |
| `TC_OBJECT` | `73` | Instance object mới |
| `TC_STRING` | `74` | String mới |
| `TC_ARRAY` | `75` | Array mới |
| `TC_CLASS` | `76` | Class object |
| `TC_BLOCKDATA` | `77` | Khối dữ liệu primitive/optional ngắn |
| `TC_ENDBLOCKDATA` | `78` | Kết thúc một phần optional block data |
| `TC_RESET` | `79` | Reset context/handles |
| `TC_BLOCKDATALONG` | `7A` | Khối data có độ dài lớn |
| `TC_EXCEPTION` | `7B` | Thông tin exception trong protocol |
| `TC_LONGSTRING` | `7C` | String dài |
| `TC_PROXYCLASSDESC` | `7D` | Descriptor cho proxy class |
| `TC_ENUM` | `7E` | Enum constant |

Chúng là **marker trong một protocol có cấu trúc**, không phải “mỗi byte bằng `73` ở file đều là object mới”. Byte giá trị `73` có thể xuất hiện **bên trong một payload hoặc tên class**; parser phải đọc theo grammar, length và ngữ cảnh thay vì tìm byte tùy tiện.

### 6.3. Class descriptor chứa gì?

Khi lần đầu gặp một serializable class trong stream, một descriptor có thể chứa:

- Tên binary của class.
- `serialVersionUID`.
- Cờ biểu diễn cách serialization của class.
- Danh sách các field được lưu với tên và kiểu.
- Mô tả superclass và những phần dữ liệu tùy biến nếu có.

Ví dụ, với `Message` ở trên, descriptor sẽ mô tả các field được lưu như `sequence` và `text`; field `secret` bị loại vì `transient`. Đây chỉ là mô tả logic, **không** phải mã byte hex đầy đủ cho tất cả JDK/đường dẫn class. Byte stream thực tế còn có tên nested class, handle, string descriptor, annotation và những phần protocol khác.

**Không ghi raw byte stream bằng tay** trừ khi bạn đang xây parser/encoder đúng Java Object Serialization Specification. `writeObject`/`readObject` được thiết kế để xử lý descriptor, đồ thị tham chiếu, block data và class matching thay bạn.

### 6.4. Object handles giữ reference identity

Java serialization không đơn giản là “dump mọi field của mỗi lần gọi”. Nó duy trì một bảng handle để:

- Không lặp lại toàn bộ object đã được ghi khi gặp **cùng reference** lần sau.
- Bảo toàn quan hệ các field cùng trỏ một object sau khi đọc.
- Tái tạo các đồ thị có **chu trình** (cyclic reference) mà không đệ quy vô hạn.
- Có thể chia sẻ instance sau deserialize trong phạm vi stream context tương ứng.

Trong protocol, handle được cấp từ giá trị base `0x7E0000` theo spec và token `TC_REFERENCE` trỏ về handle đã cấp. Không nên dùng con số handle như ID nghiệp vụ ổn định; nó là dữ liệu nội bộ của một stream.

**Ví dụ đồ thị có chu trình**:

```java
final class Node implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    Node next;
}

Node a = new Node();
Node b = new Node();
a.next = b;
b.next = a;

out.writeObject(a);
```

Đây là snippet trong method có `ObjectOutputStream out`; hai Node được ghi với cơ chế handle cho tham chiếu quay về. Đọc lại một `Node restored = (Node) in.readObject()` từ stream tương ứng sẽ giữ quan hệ `restored.next.next == restored`, nếu classes tương thích và không có custom replacement phá cấu trúc.

### 6.5. `writeObject` ghi lặp cùng reference không đồng nghĩa snapshot mới

```java
Entry entry = new Entry();
entry.number = 1;
out.writeObject(entry);

entry.number = 2;
out.writeObject(entry); // Thường chỉ viết reference cho instance đã thấy.
```

Đây là snippet với `Entry` là class Serializable ở trên, `out` đang mở. Lần đọc thứ hai **không bắt buộc** đem lại field `number=2`; với đối tượng đã ghi vào handle table, stream dùng handle cho cùng object đã serialize lần đầu. Dùng `out.reset()` giữa hai lần ghi nếu bạn thật sự cần ghi lại trạng thái object hiện tại, và hiểu rằng reset ảnh hưởng toàn bộ bảng handle của stream.

## 7. `reset()`, `writeUnshared()` và `readUnshared()`

### 7.1. Khi nào dùng `ObjectOutputStream.reset()`?

`reset()` yêu cầu ObjectOutputStream loại bỏ các handles đã lưu; những object ghi tiếp sẽ có context tham chiếu mới. Nó cũng đặt một marker `TC_RESET` trong stream để ObjectInputStream đồng bộ hóa.

```java
out.writeObject(state);
out.reset();
out.writeObject(state);
```

Đây là mã minh họa khi `out` mở và `state` Serializable. Có hai ý nghĩa:

1. Có thể gửi **snapshot mới** của cùng instance khi dữ liệu đã thay đổi giữa hai lần ghi.
2. Giảm số object references tích lũy trong bảng handles của một stream chạy lâu, với cái giá phải ghi lại descriptors/objects sau reset.

Không gọi `reset()` từ bên trong quá trình `writeObject` đang serialize một object graph; API không cho phép reset lúc đang ở giữa việc ghi graph và có thể ném `IOException`. Thực hiện tại **ranh giới giữa các lần ghi hoàn chỉnh**.

### 7.2. `writeUnshared` và `readUnshared` có phải deep copy?

Không. `writeUnshared(obj)` có semantics đặc biệt về cách **base-level object** được xem là unshared; `readUnshared()` yêu cầu đầu vào đáp ứng các điều kiện không chia sẻ tương ứng. Nhưng chúng **không bảo đảm deep copy toàn bộ object graph**, vì các object được tham chiếu trong những field con vẫn có thể được chia sẻ theo protocol.

Do đó, nếu mục tiêu là tạo **bản sao độc lập hoàn toàn**, Java serialization không phải câu trả lời ngầm định. Cần một quy trình copy với ownership và policy rõ ràng. Không dùng `writeUnshared` để giả định đã loại hết alias reference ở các object con.

## 8. Những field nào được tuần tự hóa?

Với Serializable mặc định, **các instance field không static và không transient** là các trường được cơ chế serialization xử lý, trong giới hạn class hierarchy và cách khai báo.

| Loại field | Có trong default serialized state? | Ví dụ |
|---|---|---|
| `private int count` | Có | Primitive giá trị 7 |
| `private String name` | Có | Reference tới String Serializable |
| `private Address address` | Có nếu đồ thị object tương ứng serializable | Một object graph khác |
| `private transient String password` | Không | Sau deserialize thường null |
| `private static int total` | Không | Field thuộc class/JVM, không thuộc instance |
| `private static final long serialVersionUID` | Không phải field instance; dùng trong descriptor | Kiểm tra tương thích |
| Field tham chiếu object không Serializable | Ghi có thể thất bại nếu không được loại/đổi | `NotSerializableException` |

### 8.1. `transient` không phải cơ chế mã hóa hoặc xóa bảo mật

Một field đánh dấu `transient` không được lưu **theo cơ chế mặc định**. Nó không tự động:

- Xóa giá trị đang tồn tại trong RAM.
- Ngăn custom `writeObject` chủ động ghi giá trị ấy bằng lệnh khác.
- Ngăn thông tin nhạy cảm bị lộ qua các field khác trong graph.
- Mã hóa dữ liệu đã được ghi.

Ví dụ:

```java
class Account implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    String owner;
    transient String sessionToken;
}
```

Nếu caller đặt `sessionToken="abc"` rồi serialize bằng default mechanism, giá trị đó không có trong serialized fields của Account. Nhưng object nào khác chứa cùng token trong field **không transient** vẫn có thể khiến token xuất hiện trong stream. Không xem Java serialization là kho bí mật hay một định dạng an toàn cho credentials.

### 8.2. Phân biệt constructor thường và quá trình deserialize

Với một serializable class bình thường, quá trình deserialize **không gọi constructor của chính serializable class** theo cách khởi tạo `new` thông thường. Field được khôi phục bằng cơ chế serialization; constructor không tham số của **superclass đầu tiên không Serializable** được gọi theo quy tắc tương ứng.

Điều này có hệ quả:

- Những invariant chỉ được thiết lập trong constructor của serializable class có thể không được chạy khi khôi phục.
- Các field transient sẽ có giá trị mặc định (trừ khi code khôi phục chúng chủ động), không tự được gán giá trị bởi constructor class đó.
- Không thể dựa vào constructor để bảo vệ mọi đối tượng tạo ra bởi deserialize.
- Với dữ liệu quan trọng, cần validation và kiểm soát nguồn; hook `readObject` có thể tự kiểm tra invariant nhưng cũng là lý do deserialization dữ liệu không tin cậy nguy hiểm.

## 9. `serialVersionUID` và tương thích giữa các phiên bản class

### 9.1. Vì sao Java kiểm tra serialVersionUID?

Khi serialize, thông tin class trong stream gắn với `serialVersionUID`. Khi deserialize, Java kiểm tra class tương ứng trong JVM có phiên bản được cho phép để khôi phục stream này không.

```java
public final class UserProfile implements java.io.Serializable {
    private static final long serialVersionUID = 3L;
    private String displayName;
}
```

Đây là class biên dịch độc lập `UserProfile.java`. Nếu class triển khai Serializable **không khai báo** `serialVersionUID`, Java tính giá trị mặc định dựa trên chi tiết class theo specification. Giá trị mặc định có thể thay đổi khi bạn chỉnh định nghĩa class; do đó nên khai báo tường minh để quản lý chính sách tương thích thay vì phụ thuộc vào tính toán ngầm.

Nếu stream và class local có serialVersionUID không khớp, một lỗi thường gặp là `InvalidClassException`:

```text
java.io.InvalidClassException: ... local class incompatible:
stream classdesc serialVersionUID = ..., local class serialVersionUID = ...
```

Đây là ví dụ dạng thông báo lỗi **minh họa**, không phải stdout cố định. Nó xuất hiện khi class metadata trong stream không tương thích theo kiểm tra phiên bản.

### 9.2. Cùng serialVersionUID chưa đủ để bảo đảm mọi thay đổi class tương thích

Giữ nguyên `serialVersionUID` có thể hỗ trợ **một số thay đổi** về field. Nhưng không có nghĩa bạn có thể:

- Đổi kiểu một field tùy ý.
- Chuyển class từ Serializable sang Externalizable mà không đổi contract.
- Thay đổi hierarchy hoặc cấu trúc class theo cách không tương thích.
- Xóa/đổi tên class mà không có class tương ứng lúc đọc.
- Tự do đổi `writeObject`/`readObject` custom format mà không versioning.

Các quy tắc thay đổi class được định nghĩa trong *Java Object Serialization Specification – Versioning of Serializable Objects*. Khi cần lưu tệp nhiều năm hoặc chuyển qua các bản phát hành, hãy version dữ liệu ở tầng ứng dụng, kiểm tra compatibility thực tế bằng test các file mẫu của phiên bản cũ và cân nhắc dùng định dạng dữ liệu rõ schema.

### 9.3. Tự kiểm tra serialVersionUID bằng ObjectStreamClass

```java
long uid = java.io.ObjectStreamClass
        .lookup(UserProfile.class)
        .getSerialVersionUID();
System.out.println(uid);
```

Đây là snippet khi class `UserProfile` phía trên có sẵn. Giá trị in là `3`, không phụ thuộc một thể hiện UserProfile cụ thể. `ObjectStreamClass.lookup` dành cho serializable class; đừng giả định mọi loại class đều có descriptor hữu dụng.

## 10. Tùy biến dữ liệu bằng private `writeObject` và `readObject` trong class

Đừng nhầm:

- `out.writeObject(obj)`: phương thức **public** thuộc `ObjectOutputStream`, do caller gọi để serialize object.
- `private void writeObject(ObjectOutputStream out)`: **hook đặc biệt trong chính class Serializable**, được serialization runtime nhận diện theo chữ ký.
- `private void readObject(ObjectInputStream in)`: hook khôi phục tùy biến trong chính class Serializable.

Nếu class cần thêm dữ liệu có cấu trúc hoặc kiểm tra invariant khi khôi phục, có thể khai báo:

```java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class PositiveCount implements Serializable {
    private static final long serialVersionUID = 1L;

    private int count;

    public PositiveCount(int count) {
        if (count < 0) {
            throw new IllegalArgumentException("negative count");
        }
        this.count = count;
    }

    private void writeObject(ObjectOutputStream out)
            throws IOException {
        out.defaultWriteObject();
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (count < 0) {
            throw new InvalidObjectException("negative count");
        }
    }
}
```

Đây là class **biên dịch được** (`PositiveCount.java`) nhưng không có `main`/stdout. `defaultWriteObject()` ghi các field được chọn theo cơ chế mặc định của class; `defaultReadObject()` khôi phục chúng. Sau đó `readObject` kiểm tra `count >= 0` vì constructor của serializable class không bảo đảm được gọi khi deserialize.

### 10.1. Tùy biến stream format phải có kỷ luật

Nếu hook `writeObject` ghi thêm:

```java
out.defaultWriteObject();
out.writeInt(42);
```

thì hook `readObject` tương ứng phải tiêu thụ theo đúng trình tự:

```java
in.defaultReadObject();
int extra = in.readInt();
```

Hai đoạn trên là snippets trong hooks tương ứng, không phải chương trình độc lập. Với custom serialization, Java có cơ chế optional data/block data trong protocol. Nếu muốn tương thích giữa các phiên bản, cần versioning rõ, không tự tiện đổi thứ tự hay số field tùy biến mà không có đọc tương thích.

Các hooks này không cho phép bỏ qua kiểm tra kiểu, security filter hoặc contract của ObjectInputStream. Ngoài `writeObject`/`readObject`, `writeReplace`/`readResolve` có thể thay thế object khi serialize/deserialize; đó là công cụ nâng cao và cũng tăng nguy cơ khi đọc dữ liệu không tin cậy.

### 10.2. `Externalizable` không phải cùng đường đi mặc định

`Externalizable` mở rộng `Serializable` và yêu cầu class định nghĩa `writeExternal(ObjectOutput)` / `readExternal(ObjectInput)`. Với Externalizable, class chủ động chịu trách nhiệm ghi/đọc phần nội dung object, có các yêu cầu constructor riêng (bao gồm public no-argument constructor) khi khôi phục.

Đừng coi `Externalizable` chỉ là “Serializable có thêm một method”. Nó thay đổi trách nhiệm định dạng, phiên bản và tính hợp lệ dữ liệu, nên chỉ dùng khi cần kiểm soát cấu trúc chi tiết và có test tương thích.

## 11. Stream chứa primitive block data và không phải JSON

Trong file hex, bạn có thể thấy header, token và các khối dữ liệu đan xen. Ví dụ:

```java
ByteArrayOutputStream buffer = new ByteArrayOutputStream();

try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
    out.writeInt(42);
    out.writeObject("hello");
}
```

Đây là đoạn minh họa trong method xử lý `IOException`, có import tương ứng. Trong stream, `writeInt(42)` sẽ được trình bày qua cơ chế **block data** của ObjectOutputStream, rồi tiếp theo mới đến serialized String. Bạn **không** thể đọc 4 byte đầu file và giả định đó là số `42`, vì bốn byte đầu là header `AC ED 00 05`.

### 11.1. Định dạng stream có tính cấu trúc, không phải bản dump bộ nhớ JVM

Serialization ghi **logic object graph** theo specification chứ không copy raw memory address/địa chỉ con trỏ từ JVM.

- Địa chỉ bộ nhớ của object trong process không được giữ nguyên khi đọc từ stream.
- References giữa các object được mô tả bằng handles tương ứng.
- Dữ liệu phụ thuộc serializable class schema và các hook custom, không phải layout memory cố định của HotSpot.
- Một process/JVM khác có thể deserialize khi có classes tương thích, nhưng điều đó **không** giúp đối tượng trở nên an toàn nếu bytes đến từ nguồn không tin cậy.
- Không thể dùng stream này làm chuẩn trao đổi độc lập ngôn ngữ theo cách JSON/Protocol Buffers được thiết kế.

### 11.2. Không phải tất cả field values được lặp trong mỗi lần writeObject

Trong một stream đang giữ handle table, Java có thể ghi `TC_REFERENCE` thay vì serialize lại object. Vì thế kích thước bytes sinh ra sau từng `writeObject` phụ thuộc lịch sử stream, object graph, cách gọi `reset`, và các hook, không chỉ phụ thuộc `toString()` hoặc số field hiện tại.

Nếu muốn đo kích thước serialized bytes:

```java
ByteArrayOutputStream sink = new ByteArrayOutputStream();
try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
    out.writeObject(obj);
}
int byteCount = sink.toByteArray().length;
```

Đây là snippet với `obj` serializable và đã import các lớp tương ứng. Kết quả `byteCount` là số byte **được ghi cho object và overhead của stream**, bao gồm header/descriptors; không phải kích thước bộ nhớ heap của object.

## 12. Lỗi và ngoại lệ thường gặp

| Ngoại lệ | Khi nào gặp | Hướng xử lý |
|---|---|---|
| `NotSerializableException` | Trong graph có object thuộc class không serializable | Chỉ serialize DTO được thiết kế cho mục đích này, dùng `transient` khi phù hợp |
| `InvalidClassException` | Class stream/local không tương thích, thường UID khác hoặc vi phạm serialization constraints | Quản lý `serialVersionUID` và test schema/version |
| `StreamCorruptedException` | Header/control bytes không tuân theo protocol, hoặc stream bị hỏng | Kiểm tra nguồn/định dạng, tránh trộn nhiều header |
| `ClassNotFoundException` | JVM không tìm được class cần dựng lại | Đảm bảo classpath/module, tránh storage phụ thuộc class không ổn định |
| `EOFException` | Không còn đủ bytes để đọc tiếp theo yêu cầu | Quản lý framing/count, tránh dựa vào EOF làm mọi logic cấu trúc |
| `OptionalDataException` | Đọc object tại vị trí dữ liệu primitive hoặc tình huống optional data đặc biệt | Đọc cùng thứ tự và format bên ghi |
| `InvalidObjectException` | Hook validation chủ động báo object state không hợp lệ | Kiểm tra schema và dữ liệu, không bỏ qua lỗi |
| `IOException` | File/socket/stream có sự cố I/O | Đóng stream, báo lỗi; không coi bytes đã ghi/đọc là hoàn chỉnh |
| `ClassCastException` | Ép object đọc được sang class mong đợi nhưng sai type | Kiểm tra instance/type, filter, schema |

**Không cố tiếp tục đọc một ObjectInputStream đã gặp lỗi serialization nghiêm trọng và giả định offset vẫn hợp lệ.** Java API có thể để stream ở trạng thái không xác định. Khi phát hiện dữ liệu hỏng hoặc không đáng tin, thường nên đóng stream, báo lỗi và thực hiện recovery cấp ứng dụng thay vì cố gắng tìm token tiếp theo trong mảng bytes.

### 12.1. Ví dụ `NotSerializableException`

```java
final class NotSerializableHelper {
    int value = 10;
}
final class Container implements java.io.Serializable {
    private static final long serialVersionUID = 1L;
    NotSerializableHelper helper = new NotSerializableHelper();
}
```

Đây là hai class minh họa. `out.writeObject(new Container())` sẽ thất bại vì `helper` trỏ tới class không triển khai Serializable/Externalizable. Việc đổi field sang `transient` chỉ phù hợp nếu trạng thái đó không cần trong dữ liệu khôi phục; không được “sửa” bằng cách bỏ dữ liệu quan trọng mà không thiết kế cơ chế rebuild.

### 12.2. Không dùng `toString()` để đối chiếu bytes hay identity

Khi đọc một object, `System.out.println(obj)` có thể in chuỗi dễ hiểu nếu class override `toString()`, hoặc giá trị identity hash string nếu không. Nó không chứng minh object graph được khôi phục chính xác. Để kiểm thử, so sánh field cụ thể, reference identity khi cần, invariant và behavior ứng dụng; dùng `==` trong test reference sharing như ví dụ `ObjectStreamDemo`.

## 13. Rủi ro bảo mật của `readObject`

Java Object Deserialization được tài liệu JDK cảnh báo là **nguy hiểm nếu dữ liệu đến từ nguồn không tin cậy**. Khi đọc, runtime có thể nạp class, khởi tạo object theo cơ chế đặc thù và kích hoạt hook/deserialization logic trong những class có mặt trên classpath. Một chuỗi byte do đối phương điều khiển có thể cố tạo object graph rất sâu, array rất lớn hoặc kích hoạt chuỗi class/hook nguy hiểm.

**Nguyên tắc ưu tiên:**

1. Không nhận Java serialized object stream trực tiếp từ Internet/người dùng không đáng tin khi có thể dùng JSON/CBOR/Protocol Buffers có schema/validation rõ.
2. Nếu buộc dùng, **giới hạn class được phép** và các tài nguyên liên quan bằng `ObjectInputFilter`, filter factory/hệ thống theo chính sách deploy, và kiểm soát classpath.
3. Áp giới hạn kích thước byte toàn bộ trước khi đọc nếu giao thức cho phép; dùng timeouts/limits ở tầng transport.
4. Sau deserialize vẫn xác minh object type, cấu trúc, trường bắt buộc và bất biến nghiệp vụ.
5. Dùng cập nhật JDK/thư viện và tránh đưa các lớp không cần thiết vào classpath của tiến trình giải tuần tự hóa.
6. Không tin tưởng `instanceof` **sau khi** đọc như một cơ chế duy nhất, bởi các bước tạo/khôi phục đối tượng đã diễn ra trong `readObject()`.

### 13.1. `ObjectInputFilter` và các giới hạn

Từ các phiên bản Java hiện đại, `ObjectInputStream` có thể dùng filter kiểm tra class, array length, graph depth, số references và lượng byte tiêu thụ. Ví dụ policy mang tính **minh họa**:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=128;maxarray=1024;maxbytes=65536;"
      + "com.example.dto.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter); // Phải trước readObject().
    Object value = in.readObject();
    // Tiếp tục validate type/schema/invariant.
}
```

Đây là **đoạn minh họa**, không phải chương trình độc lập: cần import `ObjectInputFilter`, `ObjectInputStream`; `source` là InputStream; caller xử lý `IOException`/`ClassNotFoundException`. Tên `com.example.dto.*` phải được thay bằng những class thực tế được phép theo kiến trúc của ứng dụng; các loại container, arrays, hoặc class phụ thuộc hợp lệ cũng cần kiểm tra chính sách tương ứng. `!*` cuối là chặn class chưa được allowlist. Một số giá trị string/primitive có ngoại lệ trong cơ chế gọi filter, nên filter **không phải validator nội dung**.

`setObjectInputFilter` được gọi **một lần** trước khi đọc object; nó không phải cấu hình được thay đi thay lại tùy item sau khi stream đã bắt đầu đọc. Còn có policy toàn JVM thông qua filter factory/JVM properties; cách kết hợp được quy định bởi JDK và yêu cầu cấu hình thực tế.

**Filter giảm rủi ro nhưng không bảo đảm stream “đã an toàn”.** Hãy coi việc giải tuần tự hóa từ nguồn không tin cậy là một boundary bảo mật, áp dụng nhiều lớp kiểm soát và ưu tiên format được thiết kế cho trao đổi dữ liệu.

### 13.2. Không nên log/deserialise bytes chưa kiểm tra chỉ để xem chúng là gì

Một antipattern:

```java
Object object = new ObjectInputStream(untrustedInput).readObject();
// Sau đó mới kiểm tra object thuộc class nào.
```

Đây là code minh họa **không an toàn**, không nên dùng với dữ liệu không đáng tin. Rủi ro nằm **trong quá trình deserialize**, trước khi code kiểm tra class của object trả về. Dùng schema-driven parsing và giới hạn bytes/class graph trước khi tiếp nhận nội dung.

## 14. Lưu object vào file và độ bền dữ liệu

### 14.1. `flush()` không đồng nghĩa `fsync`

`out.flush()` đẩy dữ liệu đang buffer xuống OutputStream kế tiếp; `out.close()` đóng stream và xử lý flush theo contract. Cả hai **không tự tạo cam kết** rằng dữ liệu đã được ghi bền qua sự cố mất điện trên mọi filesystem.

```java
try (FileOutputStream file = new FileOutputStream("state.bin");
     ObjectOutputStream out = new ObjectOutputStream(file)) {

    out.writeObject(state);
    out.flush();
    file.getFD().sync(); // Yêu cầu sync file descriptor theo contract.
}
```

Đây là đoạn minh họa trong method có `state` Serializable, import `FileOutputStream`/`ObjectOutputStream`. `FileDescriptor.sync()` là thao tác yêu cầu đồng bộ nội dung file qua descriptor; nó có chi phí và ràng buộc phụ thuộc thiết bị/provider. Nếu ứng dụng cần cập nhật file trạng thái nguyên tử, nên ghi vào file tạm rồi công bố bằng rename với những yêu cầu độ bền filesystem phù hợp — **không phải vì có `writeObject` nên tự động đạt durability**.

### 14.2. Đọc lại file lưu dài hạn không phải lúc nào cũng thành công

Một `ObjectOutputStream` có thể tạo bytes đúng ở phiên bản ứng dụng hiện tại, nhưng sau vài năm:

- Package/class đã đổi tên.
- `serialVersionUID` khác.
- Một số fields/classes của object graph đã biến mất.
- Bộ lọc deserialization policy mới từ chối class cũ.
- Class mới có invariant khác và không còn chấp nhận data cũ.

Vì vậy Java serialization thường phù hợp khi **cả bên ghi và bên đọc cùng nằm trong hệ sinh thái Java được quản lý chặt** và phiên bản tương thích được kiểm thử; không phải lựa chọn mặc định để lưu dữ liệu nghiệp vụ cần schema ổn định xuyên năm/thế hệ triển khai.

## 15. Thứ tự đọc/ghi và protocol framing

Giả sử bên ghi:

```java
out.writeObject(user);
out.writeObject(order);
out.writeInt(2026);
```

Bên đọc đúng:

```java
User user = (User) in.readObject();
Order order = (Order) in.readObject();
int year = in.readInt();
```

Hai snippets giả định các class `User`/`Order` serializable, output/input stream cùng format, và có xử lý checked exceptions. `ObjectInputStream` không tự biết “message number 1 là User, message number 2 là Order” ngoài dữ liệu class descriptor của chính stream. Caller phải thống nhất **sequence/protocol**.

Một thiết kế ổn định nên xác định:

- Phiên bản giao thức ứng dụng ở tầng ngoài, tách với `STREAM_VERSION` của Java.
- Kiểu record được phép và phạm vi của từng message.
- Số lượng message, điều kiện kết thúc và các giới hạn byte.
- Cách xử lý disconnect/stream truncated.
- Cách chuyển đổi phiên bản class và chính sách allowlist.
- Khi nào được `reset()` để tránh reference alias qua những message logic.
- Điều kiện tin cậy của nguồn bytes và đối tượng được tái dựng.

### 15.1. Không nối stream headers tùy tiện

Nếu một process mở file với chế độ append rồi khởi tạo **ObjectOutputStream mới** và ghi object:

```java
new ObjectOutputStream(new FileOutputStream("data.bin", true))
        .writeObject(obj);
```

Đây là snippet minh họa **lỗi thiết kế**, còn không đóng stream nên cũng rò rỉ tài nguyên. Constructor tạo một **header mới** giữa file; khi đọc bằng một `ObjectInputStream` duy nhất và gọi `readObject` liên tiếp, header đó có thể bị xem là thông tin protocol không hợp lệ.

Giải pháp: giữ **một ObjectOutputStream sống trong phạm vi ghi tương ứng**, hoặc thiết kế framing rõ cho nhiều serialized streams độc lập và đọc từng frame bằng ObjectInputStream riêng. Một số kỹ thuật subclass để suppress header khi append rất dễ sai với handles/protocol, cần chứng minh correctness; không nên sao chép mẹo bỏ header vào production mà thiếu kiểm thử.

## 16. Phân biệt với định dạng lưu trữ khác

| Mục tiêu | Java Object Serialization | Lựa chọn đáng cân nhắc |
|---|---|---|
| Truyền object graph Java giữa các thành phần tin cậy | Có thể phù hợp khi version/class được kiểm soát | Giao thức binary có schema nếu muốn ổn định hơn |
| JSON API giữa nhiều ngôn ngữ | Không phù hợp: định dạng nhị phân Java-specific | JSON + validation |
| Lưu config người dùng có thể sửa tay | Khó đọc/sửa | Properties, JSON, YAML/TOML với parser an toàn |
| Dữ liệu nhị phân có cấu trúc schema lâu dài | Phụ thuộc class và UID | Protocol Buffers, Avro, CBOR/schema |
| Lưu một mảng byte/ảnh/file thô | Không cần overhead object graph | `Files.readAllBytes`/`Files.write` hoặc streams/channels |
| Lưu secret/credential | Không có encryption mặc định | Kho bí mật/keystore/encryption phù hợp |
| Nhận bytes chưa tin cậy | Rủi ro lớn khi `readObject` | Định dạng dữ liệu có parser/allowlist/schema |

Nếu cần Java serialization, dùng nó do **yêu cầu tương thích/lifecycle rõ ràng**, không chỉ vì hai dòng code tiện hơn.

## 17. Những lỗi thường gặp

1. **Quên implements `Serializable`** ở class hoặc object con được tham chiếu. Có thể ném `NotSerializableException`.
2. **Cho rằng mọi field đều được ghi.** `static` và `transient` không nằm trong trạng thái mặc định.
3. **Nghĩ `transient` là mã hóa.** Nó không lưu theo cơ chế mặc định nhưng không tự bảo vệ các field/alias khác.
4. **Nhầm `writeObject` của stream với hook private của class.** Chúng khác vai trò và chữ ký.
5. **Đổi class rồi không kiểm tra serialVersionUID.** `InvalidClassException` có thể xảy ra.
6. **Giữ UID bằng nhau rồi giả định mọi schema đều tương thích.** Một số thay đổi field/hierarchy/custom data vẫn phá format.
7. **Đọc primitive bằng `readObject`.** Phải dùng `readInt`/`readUTF`... theo thứ tự bên ghi.
8. **Đọc số object khác với số đã ghi.** Có thể gặp `EOFException` hoặc lỗi protocol.
9. **Nhầm header `AC ED 00 05` với dữ liệu object.** Đó là metadata bắt đầu stream, không phải field của object.
10. **Nghĩ lần thứ hai `writeObject(sameInstance)` gửi trạng thái mới.** Handle table có thể ghi reference tới lần đầu.
11. **Thay đổi object giữa hai lần write nhưng không `reset()` khi cần snapshot mới.** Phía đọc vẫn tham chiếu state cũ.
12. **Nghĩ `writeUnshared` deep-copy toàn bộ object graph.** Nó không bảo đảm alias-free nested references.
13. **Cố parse hex stream bằng cách tìm byte `TC_OBJECT` tùy tiện.** Token cần được hiểu theo grammar và length.
14. **Tạo ObjectOutputStream mới mỗi lần append cùng file.** Header lặp giữa stream phá việc đọc liên tục.
15. **Hai đầu socket cùng tạo ObjectInputStream trước khi có output header.** Có thể deadlock do constructor đợi bytes header.
16. **Đóng ObjectOutputStream rồi tiếp tục dùng OutputStream bên dưới.** Close truyền xuống stream bên dưới.
17. **Chỉ `flush()` rồi khẳng định file durable qua mất điện.** Flush Java khác filesystem persistence.
18. **Dùng `readObject` cho JSON/text/ZIP.** Không cùng định dạng; có thể lỗi header.
19. **Dựa vào constructor của Serializable class để validate mọi object deserialize.** Constructor của chính class có thể không được gọi.
20. **Chỉ kiểm tra `instanceof` sau `readObject` và coi dữ liệu bên ngoài an toàn.** Lúc ấy quá trình deserialize đã diễn ra.
21. **Không có ObjectInputFilter/resource limits khi đọc data không tin cậy.** Có nguy cơ tải đồ thị nguy hiểm/quá lớn.
22. **Bắt mọi `IOException` rồi cố đọc tiếp stream hỏng.** Trạng thái object stream có thể không xác định.
23. **Dùng `toString()` làm bằng chứng deep equality.** Cần test fields, references và invariant.
24. **Nghĩ version stream `00 05` là serialVersionUID của class.** Hai khái niệm độc lập.
25. **Cho rằng String luôn được mã hóa như UTF-8 bytes raw trong toàn bộ stream.** Protocol có quy tắc mã hóa và markers riêng; không đồng nhất với `"abc".getBytes(UTF_8)`.
26. **Coi serialization như sao chép raw memory.** Java lưu trạng thái logic theo protocol và class descriptors.
27. **Không xử lý class không còn trên classpath.** `ClassNotFoundException` có thể làm dữ liệu cũ không đọc được.
28. **Tin bản đọc lại luôn có invariant hợp lệ.** Cần validation và quản lý phiên bản class.
29. **Không quản lý số byte/file size tối đa trước khi deserialize.** Filter và giới hạn tài nguyên nên được thiết kế ở nhiều tầng.
30. **Dùng object serialization làm cơ chế lưu dữ liệu dài hạn mà không có test compatibility.** File hôm nay chưa chắc đọc được ở deployment tương lai.

## 18. Tự kiểm tra kiến thức

**Câu 1.** `writeObject` tạo JSON hay một định dạng binary riêng?  
**Trả lời:** Binary Java Object Serialization Stream Protocol, có header/descriptors/tokens/handles.

**Câu 2.** Bốn byte đầu của ObjectOutputStream thông thường là gì?  
**Trả lời:** `AC ED 00 05` (magic và stream version).

**Câu 3.** Class `Serializable` có cần override `writeObject` không?  
**Không.** Serializable là marker interface, cơ chế mặc định có thể tự ghi các field phù hợp.

**Câu 4.** Nếu class Serializable có field non-transient trỏ tới class không Serializable thì sao?  
**Trả lời:** Ghi graph có thể ném `NotSerializableException`.

**Câu 5.** `readObject` trả kiểu tĩnh nào và nên làm gì sau đó?  
**Trả lời:** `Object`; kiểm tra/ép kiểu hợp lệ và xác minh dữ liệu, nhưng không coi kiểm tra sau đọc là bảo vệ đầy đủ trước untrusted input.

**Câu 6.** Vì sao hai lần `writeObject(sameObj)` rồi đọc hai lần có thể tạo cùng reference?  
**Vì** ObjectOutputStream duy trì handle table và có thể ghi `TC_REFERENCE` cho object đã ghi.

**Câu 7.** `out.reset()` giữa hai lần ghi có tác dụng gì?  
**Trả lời:** Xóa handles đã nhớ và ghi reset marker; object ghi sau được serialize lại trong context mới.

**Câu 8.** `transient String token` được khôi phục thành gì với cơ chế mặc định?  
**Trả lời:** Thường là `null` nếu không có custom logic thay đổi nó.

**Câu 9.** `serialVersionUID` khác `STREAM_VERSION` ở đâu?  
**Trả lời:** UID xác định phiên bản tương thích của class; STREAM_VERSION mô tả phiên bản serialization wire protocol.

**Câu 10.** Một ObjectInputStream có thể đọc file UTF-8 thông thường không?  
**Không.** Stream phải đúng Java object serialization protocol; file text không có header/class descriptors thích hợp.

**Câu 11.** Có thể đọc dữ liệu không tin cậy rồi mới kiểm tra type để loại bỏ mọi rủi ro không?  
**Không.** Deserialization đã khởi động trước lúc kiểm tra. Ưu tiên format có schema, filter và giới hạn tài nguyên khi bắt buộc dùng object stream.

**Câu 12.** Nếu class đổi package hoặc biến mất, nhưng byte file vẫn nguyên, deserialize có chắc thành công?  
**Không.** JVM vẫn cần giải quyết tên class và các quy tắc tương thích.

**Câu 13.** `out.flush()` có bảo đảm tệp vẫn nguyên sau mất điện không?  
**Không.** Flush ở tầng Java không đồng nghĩa độ bền của thiết bị/file system.

**Câu 14.** `writeUnshared` có bảo đảm mọi nested object đều được deep clone không?  
**Không.** Nó chỉ thay semantics chia sẻ ở cấp được API định nghĩa; nested references có thể vẫn chia sẻ.

**Câu 15.** Làm sao kiểm tra file stream chứa toàn graph object, chứ không chỉ trùng chuỗi in ra?  
**Trả lời:** Test giá trị fields, reference identity, chu trình, invariants, serialization hooks và khả năng đọc qua phiên bản tương thích.

## 19. Tổng kết và tài liệu chính thức

**Bản chất:** `ObjectOutputStream.writeObject` ghi một **đồ thị đối tượng** vào Java Object Serialization Stream Protocol. `ObjectInputStream.readObject` đọc lại **đối tượng kế tiếp** và khôi phục các tham chiếu. Stream có header `AC ED 00 05`, class descriptors, type tags, handles và block data; nó không phải JSON hay mảng các object độc lập. `Serializable`, `serialVersionUID`, `transient`, `reset` và các hooks custom quyết định cách dữ liệu được lưu và khôi phục.

**Quy tắc an toàn:** chỉ deserialize nguồn tin cậy hoặc dùng chính sách lọc/giới hạn nghiêm ngặt khi buộc phải đọc Java object stream. Đừng xem byte Java serialization là định dạng lưu trữ mặc định cho hệ thống cần khả năng tương thích lâu dài, đa ngôn ngữ hoặc mức phòng vệ mạnh trước dữ liệu do đối phương kiểm soát.

Nguồn Java chính thức:

- `ObjectOutputStream` — `writeObject`, `reset`, `writeUnshared`, stream header: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html
- `ObjectInputStream` — `readObject`, `readUnshared`, `setObjectInputFilter` và security warnings: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- `Serializable` — marker interface và custom hooks: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- `ObjectInputFilter` — deserialization filtering: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- `ObjectStreamConstants` — STREAM_MAGIC/STREAM_VERSION/TC_*: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectStreamConstants.html
- `ObjectStreamClass` — serialVersionUID và class descriptors: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectStreamClass.html
- Java Object Serialization Specification, Stream Protocol: https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/protocol.html
- Java Object Serialization Specification, Versioning: https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/version.html
