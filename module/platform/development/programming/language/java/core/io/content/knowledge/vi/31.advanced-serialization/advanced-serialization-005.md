# Externalizable, writeExternal và readExternal trong Java Serialization

## 1. Tổng quan và mục tiêu

Trong Java Core I/O, `java.io.Externalizable` là một cơ chế tuần tự hóa đối tượng cho phép **chính lớp đối tượng chủ động ghi và đọc biểu diễn dữ liệu của mình**. Nó mở rộng `Serializable` nhưng khác đáng kể với serialization mặc định:

- `Serializable` thông thường: `ObjectOutputStream` có thể tự ghi các instance field đủ điều kiện, trừ `static` và `transient`, theo quy tắc Java serialization.
- `Externalizable`: runtime gọi **`writeExternal(ObjectOutput)`** khi ghi và **`readExternal(ObjectInput)`** khi đọc. Lập trình viên quyết định cần ghi gì, ghi theo thứ tự nào và khôi phục ra sao.
- Khi deserialize một class `Externalizable` thông thường, Java cần **constructor `public` không tham số** để tạo instance trước khi gọi `readExternal`.
- Việc tự quản lý dữ liệu **không làm mất cơ chế quản lý object handles** của `ObjectOutputStream` khi bạn gọi `writeObject`/`readObject`. Đồ thị tham chiếu và alias có thể được giữ nguyên, kể cả chu trình, nếu thiết kế giao thức đúng.
- `Externalizable` vẫn là **Java native object serialization**, không phải cơ chế giải mã dữ liệu không tin cậy an toàn.

Sau bài này, bạn sẽ hiểu hợp đồng API, viết được ví dụ Java 17+ chạy độc lập, kiểm thử thứ tự/phiên bản của biểu diễn dữ liệu, xử lý reference graph và biết khi nào không nên sử dụng cơ chế này.

## 2. Externalizable là gì?

Khai báo giao diện:

```java
public interface Externalizable extends Serializable {
    void writeExternal(ObjectOutput out) throws IOException;

    void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException;
}
```

Đây là hình thức khai báo API rút gọn để giải thích; Java đã có interface này trong `java.io`, **không tự định nghĩa lại nó trong dự án**.

Hai phương thức quan trọng:

| Phương thức | Lúc nào chạy? | Chức năng |
|---|---|---|
| `writeExternal(ObjectOutput out)` | Khi `ObjectOutputStream` ghi instance Externalizable mới | Tự viết field/phiên bản/record theo thứ tự bạn chọn |
| `readExternal(ObjectInput in)` | Sau khi instance được tạo để giải tuần tự hóa | Đọc đúng biểu diễn do `writeExternal` tạo và dựng lại trạng thái |

`ObjectOutput` có các thao tác `writeInt`, `writeLong`, `writeBoolean`, `writeUTF`, `writeObject` và `write(byte[])`. `ObjectInput` có các thao tác đối xứng `readInt`, `readLong`, `readBoolean`, `readUTF`, `readObject`, `readFully`, v.v.

**Không được coi `ObjectOutput` là bộ ghi JSON.** Bạn đang tạo một trình tự giá trị byte theo hợp đồng của chính ứng dụng, nằm trong object serialization stream của Java.

### Externalizable không có nghĩa class được ghi hoàn toàn ngoài Java serialization

`ObjectOutputStream.writeObject(externalizableObject)` vẫn quản lý luồng object, class descriptor, identity handles và cơ chế giải mã liên quan. `writeExternal` chịu trách nhiệm payload trạng thái của class, không thay thế toàn bộ định dạng stream hay việc tìm class theo tên lúc đọc.

## 3. Ví dụ tối giản một class Externalizable

```java
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectOutput;

public class Product implements Externalizable {
    private static final long serialVersionUID = 1L;

    private String code;
    private int quantity;

    // BẮT BUỘC public và không tham số cho cơ chế deserialization.
    public Product() {
    }

    public Product(String code, int quantity) {
        this.code = code;
        this.quantity = quantity;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeUTF(code);
        out.writeInt(quantity);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        code = in.readUTF();
        quantity = in.readInt();
    }

    @Override
    public String toString() {
        return code + ": " + quantity;
    }
}
```

Lưu `Product.java` nếu muốn biên dịch class này riêng. Đoạn trên là **định nghĩa lớp**, chưa có `main` để chạy. Giả định `code` không null và vừa giới hạn của `writeUTF`; ví dụ nâng cao cần kiểm tra dữ liệu đầu vào.

Điều bạn phải tự bảo đảm:

1. `writeExternal` ghi `code` **trước** `quantity`.
2. `readExternal` đọc `code` bằng `readUTF` **trước** `quantity` bằng `readInt`.
3. Nếu đổi thứ tự hoặc đổi kiểu của một thành phần mà không cập nhật giao thức đọc, có thể đọc sai, ném exception, hoặc âm thầm tạo trạng thái không hợp lệ.
4. Không có cơ chế tự động lưu thêm field mới chỉ vì bạn thêm một field vào class.
5. Constructor `public Product()` được dùng khi giải tuần tự hóa; constructor hai tham số không tự chạy trong quá trình ấy.

## 4. So sánh Serializable và Externalizable

| Khía cạnh | `Serializable` mặc định | `Externalizable` |
|---|---|---|
| Interface | Marker interface, không có method bắt buộc | Mở rộng Serializable; có hai method bắt buộc |
| Ai quyết định field được lưu? | Cơ chế serialization mặc định, có thể tùy chỉnh qua hook | Chính `writeExternal` |
| Ai đọc trạng thái? | Cơ chế mặc định, có thể tùy chỉnh `readObject` | Chính `readExternal` |
| Constructor khi restore class thông thường | Không gọi constructor thông thường của class Serializable như `new` | Gọi constructor `public` không tham số của class Externalizable |
| `transient` và `static` | Không lưu theo quy tắc field mặc định | Không tự quyết định; có thể ghi giá trị tường minh |
| Thay đổi thứ tự field trong mã nguồn | Không tự buộc bạn ghi/đọc thủ công theo thứ tự đó | Giao thức đã ghi phụ thuộc thứ tự/type do tác giả lựa chọn |
| Thêm field mới | Quy tắc tương thích của serialization mặc định có thể hỗ trợ một số thay đổi | Phải tự thiết kế cách nhận biết và đọc phiên bản cũ/mới |
| Object identity/cycle qua `writeObject` | Có cơ chế handles | Vẫn có khi dùng cơ chế object stream phù hợp |
| Tính linh hoạt | Ít mã hơn cho model đơn giản | Chủ động encoding, validation và chọn data fields |
| Rủi ro | Versioning, object graph, input không tin cậy | Các rủi ro tương tự **cộng thêm lỗi giao thức do tự viết** |

**Externalizable không mặc định nhanh hơn, nhỏ hơn, an toàn hơn Serializable.** Nó có thể giảm payload nếu chủ động không ghi những field thừa, nhưng vẫn có metadata/handle của Java serialization và thêm công sức bảo trì mã hóa thủ công. Cần benchmark nếu hiệu năng quan trọng.

## 5. Tại sao cần constructor public không tham số?

Khác với class `Serializable` thông thường, Java deserialization của Externalizable thực hiện về mặt ý tưởng:

```text
Đọc metadata class từ object stream
        |
        v
Tìm/nạp class tương thích
        |
        v
Gọi constructor public không tham số
        |
        v
Instance đã được tạo
        |
        v
Gọi readExternal(ObjectInput)
        |
        v
Instance đã khôi phục trạng thái
```

Vì constructor chạy thực sự:

- Các field initializer và logic trong constructor không tham số có thể chạy.
- Sau đó `readExternal` có thể ghi đè các giá trị vừa khởi tạo.
- Nếu một field **không được đọc** trong `readExternal`, nó có thể giữ giá trị do constructor đặt (hoặc giá trị mặc định khi constructor không gán).
- Constructor có side effect (kết nối DB, tạo thread, ghi file, thay global state...) sẽ gây rủi ro khi deserialize. **Giữ constructor này đơn giản và side-effect-free** là khuyến nghị quan trọng.
- Nếu class không có constructor public không tham số có thể truy cập như API yêu cầu, quá trình đọc sẽ thất bại, thường là `InvalidClassException` hoặc lỗi liên quan.

Ví dụ **sai**:

```java
class Bad implements Externalizable {
    private static final long serialVersionUID = 1L;

    private String value;

    public Bad(String value) {
        this.value = value;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeUTF(value);
    }

    @Override
    public void readExternal(ObjectInput in) throws IOException {
        value = in.readUTF();
    }
}
```

Class trên thiếu constructor `public Bad()`. Đoạn minh họa giả định import `Externalizable`, `ObjectOutput`, `ObjectInput` và `IOException`. Ghi instance vẫn có thể tạo bytes, nhưng đọc lại qua Java serialization không có constructor cần thiết.

### Nested class cũng cần chú ý

Nếu viết class Externalizable bên trong class khác, **`public static class ... implements Externalizable`** thường rõ ràng hơn inner class không static. Inner class không static mang reference ngầm tới outer instance và cơ chế constructor có tham số outer ngầm, khiến yêu cầu constructor không tham số dễ bị vi phạm.

## 6. Mọi dữ liệu nằm trong giao thức do bạn viết

Với `Serializable` mặc định:

```java
private int age;
private String name;
private transient String token;
```

cơ chế serialization mặc định biết xử lý `age` và `name`, bỏ `token`.

Với `Externalizable`, bạn quyết định:

```java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeInt(age);
    out.writeUTF(name);
    // token không được ghi vì ta KHÔNG gọi write cho nó.
}
```

`transient` **không tự động chặn** việc bạn trực tiếp viết field trong `writeExternal`:

```java
private transient String token;

@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeUTF(token); // VẪN đưa token vào luồng nếu được gọi!
}
```

Vì vậy, không dùng `transient` như biện pháp an toàn tuyệt đối trước dữ liệu nhạy cảm khi class Externalizable có custom protocol. Kiểm tra mã `writeExternal` thực sự đã ghi những gì.

Tương tự, `static` không phải instance state mặc định, nhưng lập trình viên vẫn **có thể** đọc static field và ghi giá trị của nó một cách thủ công. Điều đó không có nghĩa nên làm như vậy: state dùng chung thường không phù hợp lưu dưới dạng từng object.

## 7. Primitive, String và Object: chọn cặp phương thức

| Ghi bằng ObjectOutput | Đọc bằng ObjectInput | Kiểu dữ liệu |
|---|---|---|
| `writeInt(value)` | `readInt()` | 4 byte mã hóa int theo giao thức DataOutput/DataInput |
| `writeLong(value)` | `readLong()` | long |
| `writeBoolean(value)` | `readBoolean()` | boolean |
| `writeDouble(value)` | `readDouble()` | double |
| `writeUTF(value)` | `readUTF()` | Chuỗi dùng **modified UTF-8** có tiền tố độ dài |
| `writeObject(ref)` | `readObject()` | Java object/reference graph |
| `write(byte[])` | `readFully(byte[])` | Dãy byte với kích thước **đã biết trước** |

Một số cặp API có thể **không đối xứng** nếu dùng sai. Ví dụ `writeUTF(name)` **không** tương đương `writeObject(name)`, dù cả hai truyền cùng nội dung chuỗi.

### writeUTF không phải “ghi UTF-8 tùy độ dài”

`DataOutput.writeUTF` sử dụng **modified UTF-8** của Java cùng độ dài giới hạn bằng 16-bit unsigned. Chuỗi có biểu diễn modified UTF-8 dài quá 65.535 byte có thể làm `writeUTF` ném `UTFDataFormatException`. Nếu cần chuỗi rất lớn, bạn nên tự quy định encoding UTF-8, length prefix bằng `int`/`long` có giới hạn, rồi ghi byte; lúc đọc kiểm tra độ dài trước khi cấp phát.

Ví dụ một schema text lớn (minh họa, không phải method độc lập):

```java
byte[] utf8 = name.getBytes(StandardCharsets.UTF_8);
if (utf8.length > MAX_NAME_BYTES) {
    throw new IOException("Name too long");
}
out.writeInt(utf8.length);
out.write(utf8);

// Khi đọc:
int length = in.readInt();
if (length < 0 || length > MAX_NAME_BYTES) {
    throw new InvalidObjectException("Invalid name length");
}
byte[] raw = new byte[length];
in.readFully(raw);
name = new String(raw, StandardCharsets.UTF_8);
```

Ở đây `name`, `out`, `in`, `MAX_NAME_BYTES` phải được khai báo trong class. Ví dụ dùng `new String(..., UTF_8)` có thể thay byte UTF-8 lỗi bằng ký tự thay thế theo hành vi decoder. Nếu giao thức cần **từ chối Unicode lỗi**, dùng `CharsetDecoder` với `CodingErrorAction.REPORT` và bắt lỗi.

### Null handling

`writeUTF(null)` không phải cách ghi một chuỗi null hợp lệ. Chọn schema như:

```java
out.writeBoolean(name != null);
if (name != null) {
    out.writeUTF(name);
}

// Đọc theo đúng thứ tự:
boolean exists = in.readBoolean();
name = exists ? in.readUTF() : null;
```

Hoặc sử dụng `writeObject`/`readObject` cho một reference kiểu String, nơi null được object stream xử lý tự nhiên. Chọn theo yêu cầu kích thước, biểu diễn và kiểm soát kiểu.

## 8. Thứ tự là một phần hợp đồng dữ liệu

Giả sử writer:

```java
out.writeInt(version);
out.writeUTF(code);
out.writeLong(timestamp);
out.writeBoolean(active);
```

Reader **phải đọc cùng thứ tự và cách biểu diễn**:

```java
int version = in.readInt();
String code = in.readUTF();
long timestamp = in.readLong();
boolean active = in.readBoolean();
```

Nếu reader lại gọi `readLong()` ở vị trí đang lưu String, stream sẽ bị diễn giải sai; kết quả có thể là exception hoặc một giá trị rác trước khi gặp lỗi ở phần sau.

Một file Java object serialization có thể được đọc bởi class version khác với class đã ghi trước đó. Chính tác giả `Externalizable` phải xây giao thức cho compatibility. Không được tự dựa vào thứ tự khai báo field hay việc thêm field ở cuối class như với một số trường hợp serialization mặc định.

## 9. Chương trình Java 17+ hoàn chỉnh: chu trình Externalizable + object graph

Ví dụ tiếp theo chứng minh đồng thời:

1. `writeExternal`/`readExternal` tự viết/đọc version, tên và reference.
2. Public constructor không tham số được gọi khi giải tuần tự hóa.
3. `transient cache` **không được ghi**, nhưng giữ giá trị do constructor đọc tạo.
4. Hai node tạo vòng `A → B → A`; vòng được bảo toàn.
5. Ghi cùng một root **hai lần** trên cùng ObjectOutputStream rồi đọc hai lần vẫn có thể trả cùng reference nhờ handle của stream.
6. Các object restored là instance khác với object ban đầu ở JVM.
7. Dữ liệu tự tạo trong bộ nhớ, **không** nhận từ nguồn không tin cậy.

Lưu đúng tên **`ExternalizableGraphDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.Externalizable;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInput;
import java.io.ObjectInputStream;
import java.io.ObjectOutput;
import java.io.ObjectOutputStream;
import java.io.Serial;

public class ExternalizableGraphDemo {

    public static class Node implements Externalizable {
        @Serial
        private static final long serialVersionUID = 1L;

        private static int publicNoArgCalls = 0;

        private String name;
        private Node next;
        private transient String cache;

        // Bắt buộc public và không tham số.
        public Node() {
            publicNoArgCalls++;
            cache = "from-no-arg";
        }

        public Node(String name) {
            this.name = name;
            this.cache = "live-only";
        }

        @Override
        public void writeExternal(ObjectOutput out) throws IOException {
            out.writeInt(1);        // Version của custom protocol.
            out.writeUTF(name);
            out.writeObject(next);  // Giữ cơ chế object identity/handles.
        }

        @Override
        public void readExternal(ObjectInput in)
                throws IOException, ClassNotFoundException {
            int formatVersion = in.readInt();
            if (formatVersion != 1) {
                throw new InvalidObjectException(
                        "Unsupported format version: " + formatVersion);
            }

            String restoredName = in.readUTF();
            Object restoredNext = in.readObject();

            if (restoredName.isBlank()) {
                throw new InvalidObjectException("Empty name");
            }
            if (restoredNext != null && !(restoredNext instanceof Node)) {
                throw new InvalidObjectException("Invalid next node");
            }

            name = restoredName;
            next = (Node) restoredNext;

            // cache vẫn là "from-no-arg": không được ghi/đọc ở đây.
        }
    }

    public static void main(String[] args) throws Exception {
        Node a = new Node("A");
        Node b = new Node("B");
        a.next = b;
        b.next = a;

        byte[] bytes;
        try (ByteArrayOutputStream memory = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(memory)) {
            output.writeObject(a);
            output.writeObject(a); // Cùng instance root.
            output.flush();
            bytes = memory.toByteArray();
        }

        Node restoredFirst;
        Node restoredSecond;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            restoredFirst = (Node) input.readObject();
            restoredSecond = (Node) input.readObject();
        }

        System.out.println("Name: " + restoredFirst.name);
        System.out.println("Cycle restored: "
                + (restoredFirst.next.next == restoredFirst));
        System.out.println("Shared root: "
                + (restoredFirst == restoredSecond));
        System.out.println("No-arg constructor calls: "
                + Node.publicNoArgCalls);
        System.out.println("Transient cache: " + restoredFirst.cache);
        System.out.println("Restored differs: " + (restoredFirst != a));
    }
}
```

Biên dịch và chạy tại thư mục chứa mã:

```bash
javac ExternalizableGraphDemo.java
java ExternalizableGraphDemo
```

**Stdout dự kiến chính xác trong một JVM chạy chương trình độc lập:**

```text
Name: A
Cycle restored: true
Shared root: true
No-arg constructor calls: 2
Transient cache: from-no-arg
Restored differs: true
```

Phân tích chi tiết:

- `new Node("A")` và `new Node("B")` gọi constructor có tham số, **không** tăng biến đếm `publicNoArgCalls`.
- Serialization root A gọi `writeExternal(A)` → ghi version 1, tên A và reference tới B; với B, `writeExternal(B)` ghi version 1, tên B và reference ngược tới A.
- `ObjectOutputStream` có cơ chế handle cho object A, nên reference B→A không khiến code lặp vô hạn.
- Khi đọc lại, A và B là hai instance Externalizable mới; constructor `public Node()` được gọi cho từng instance, nên biến đếm trở thành 2.
- `readExternal` đặt `name` và `next` theo stream; nó **không ghi đè** `cache`, nên giá trị khởi tạo từ constructor được giữ nguyên.
- `restoredFirst.next.next == restoredFirst` xác nhận chu trình đã khôi phục.
- Lần `output.writeObject(a)` thứ hai trên cùng stream sử dụng lại handle của A; hai lần `readObject` trả cùng root restored, nên `restoredFirst == restoredSecond`.
- `restoredFirst != a` cho thấy object restored không cùng identity với object gốc.

**Đừng dùng static counter như một phép đo chung cho nhiều tiến trình hoặc nhiều lượt chạy song song trong production.** Ở ví dụ độc lập, nó minh họa constructor; trong ứng dụng thật, constructor có side effect hoặc state toàn cục dễ gây lỗi concurrency/reentrancy.

## 10. Cơ chế bảo toàn tham chiếu và vòng

Khi `Externalizable.writeExternal` gọi `out.writeObject(reference)`, ObjectOutputStream tiếp tục sử dụng cơ chế lưu object handles. Điều này đặc biệt quan trọng cho:

```text
A.next = B
B.next = A

writeObject(A)
  ├── writeExternal(A)
  │      ├── writeInt(1)
  │      ├── writeUTF("A")
  │      └── writeObject(B)
  │             └── writeExternal(B)
  │                    └── writeObject(A) -> reference/handle
  └── hoàn tất root A
```

Khi đọc, Java tạo instance và quản lý reference đủ để tái tạo đồ thị có chu trình theo quy tắc của stream. Tuy nhiên, **logic `readExternal` phải tránh thao tác tùy tiện lên những object mà trạng thái chưa được đọc xong**. Trong chu trình, một tham chiếu có thể trỏ tới object đang được xây dựng dở. Ví dụ nếu `B.readExternal` cố đọc `A.name` trước khi `A.readExternal` hoàn tất, tên của A có thể vẫn chưa được gán.

Do đó:

- Ghi reference bằng `writeObject` và đọc bằng `readObject` để tận dụng handle tracking.
- Trong `readExternal`, ưu tiên lưu các reference và xác thực kiểu hợp lý, tránh gọi nghiệp vụ phức tạp trên graph chưa hoàn tất.
- Không giả định tất cả object được tham chiếu đã hoàn tất validation ở thời điểm một reference được gán.
- Nếu cần kiểm tra invariant xuyên nhiều node, có thể tổ chức bước validation sau khi toàn bộ graph root đã được đọc xong.
- Nếu thay `writeObject` bằng logic đệ quy thủ công tự gọi `next.writeExternal(out)`, bạn có thể bỏ qua handle tracking và **tạo đệ quy vô hạn** cho đồ thị có vòng.

### Object identity khác object equality

Khi kiểm tra bảo toàn tham chiếu:

- `a == b`: cùng instance trong JVM không?
- `a.equals(b)`: giá trị có tương đương theo logic của class không?

Hai instance có cùng `name` vẫn có thể không phải một object. Hãy dùng `==` để test alias/cycle, không chỉ dùng `equals`.

## 11. Externalizable không tự động ghi mọi field

Một class có:

```java
private String id;
private int count;
private List<String> tags;
private transient String sessionToken;
```

Nếu `writeExternal` chỉ gọi:

```java
out.writeUTF(id);
out.writeInt(count);
```

thì:

- `id` và `count` được ghi theo schema tùy chỉnh.
- `tags` không được ghi; sau deserialize, giá trị của nó phụ thuộc constructor `public` và logic `readExternal`.
- `sessionToken` không được ghi **vì tác giả không gọi write cho field này**. Nếu tác giả ghi nó thủ công dù transient, dữ liệu vẫn xuất hiện trong stream.
- Việc thêm `tags` vào class Java không khiến stream tự có thêm tags.

Trong trường hợp cần persist tags, bạn có thể chủ động ghi số lượng có giới hạn và từng phần tử, hoặc `out.writeObject(tags)` (chỉ khi kiểu và đồ thị an toàn, tin cậy, cùng phiên bản). Phương án ghi tự định dạng thường kiểm soát migration và kích thước tốt hơn; phương án `writeObject` dễ dùng nhưng kéo thêm class/graph Java serialization.

## 12. Versioning tường minh: tự quản lý giao thức

Khi dùng `Externalizable`, **`serialVersionUID` và phiên bản payload riêng là hai tầng khác nhau**:

- `serialVersionUID` dùng trong Java serialization để kiểm tra một phần tính tương thích class khi đọc object descriptor.
- `formatVersion` do bạn ghi bằng `writeInt` là một thành phần trong custom protocol của `writeExternal`.

Ví dụ V1:

```java
out.writeInt(1);
out.writeUTF(code);
out.writeInt(quantity);
```

V2 muốn thêm `price`:

```java
out.writeInt(2);
out.writeUTF(code);
out.writeInt(quantity);
out.writeLong(priceInCents);
```

Reader V2 có thể đọc cả hai:

```java
int version = in.readInt();
if (version != 1 && version != 2) {
    throw new InvalidObjectException("Unsupported version: " + version);
}

code = in.readUTF();
quantity = in.readInt();
priceInCents = version >= 2 ? in.readLong() : 0L;
```

Đây là **các mảnh mã minh họa của cùng custom format**, không đặt hai phiên bản writer vào một class cùng lúc. Tất cả biến cần được khai báo; reader nên validate code/quantity/price ngay sau khi đọc. Cẩn thận rằng nếu dữ liệu đã được ghi bởi V2 rồi một reader V1 đọc nó, reader V1 **có thể không biết xử lý v2** và cần từ chối thay vì đọc lầm byte.

### Gắn serialVersionUID thế nào?

Với Externalizable vẫn nên khai báo:

```java
@Serial
private static final long serialVersionUID = 1L;
```

`@Serial` dùng trong Java 17. UID tương ứng phải là `static final long` đúng tên. Khi đổi schema payload mà vẫn muốn một class nhận các phiên bản cũ theo logic `readExternal`, có thể giữ UID tương thích và dùng `formatVersion` để phân nhánh. Nếu cố tình thay đổi class không tương thích, UID mới có thể khiến đọc stream cũ bị từ chối với `InvalidClassException`.

**Giữ UID cũ không tự bảo đảm schema V1/V2 tương thích.** Reader cần thực sự phân tích đúng mọi phiên bản được hứa hỗ trợ, kiểm thử file thực tế và xử lý giá trị mặc định/validation.

### Kiểm tra lỗi version phải sớm

Đọc `version` trước rồi kiểm tra miền hỗ trợ trước khi xử lý phần còn lại giúp tránh đọc sai kiểu trong một schema hoàn toàn khác. Không nên bỏ qua version không biết rồi đoán các byte còn lại theo format hiện tại.

## 13. Thứ tự dữ liệu và lỗi khó phát hiện

Sai thứ tự có thể tạo lỗi khó chẩn đoán. Giả sử writer `writeInt(5)` rồi `writeLong(7L)`, còn reader lại `readLong()` rồi `readInt()`:

- Không nhất thiết exception xảy ra ngay tại byte đầu.
- Các giá trị có thể bị ghép từ bytes của hai field.
- Vị trí đọc tiếp theo không còn ở ranh giới mong muốn.
- Lỗi thật có thể xuất hiện rất muộn khi type token, length hoặc trailer bị diễn giải sai.

**Viết unit test round-trip là cần nhưng chưa đủ.** Nếu writer và reader cùng mắc lỗi tương ứng, một test round-trip cùng phiên bản có thể vẫn pass. Cần kiểm tra cross-version bằng **golden files** được lưu từ các phiên bản cũ và test các input không hợp lệ.

Checklist kiểm thử:

1. Object tối thiểu và object đầy đủ.
2. Null, chuỗi rỗng, Unicode, chuỗi rất dài.
3. Số âm, số lớn, overflow, boundary values.
4. Reference graph có cùng object xuất hiện nhiều lần.
5. Graph có chu trình.
6. Stream bị cắt giữa primitive hoặc giữa object.
7. `formatVersion` không hỗ trợ.
8. Class có/không có public no-arg constructor.
9. Lỗi khi ghi nhiều object liên tiếp trong cùng stream.
10. Các phiên bản cũ/mới và độ ổn định của UID.

## 14. writeExternal/readExternal có thể ném exception gì?

| Tình huống | Exception/nhóm lỗi |
|---|---|
| Stream hỏng, file bị cắt hoặc lỗi transport | `IOException`, `EOFException`, `StreamCorruptedException` tùy ngữ cảnh |
| Payload format tự đặt không hợp lệ | Có thể chủ động ném `InvalidObjectException` |
| `readObject()` gặp class không có trong classpath | `ClassNotFoundException` |
| Class Externalizable không đáp ứng yêu cầu constructor | Thường `InvalidClassException` hoặc lỗi tương ứng |
| `writeObject(ref)` gặp object không Serializable | `NotSerializableException` |
| Class descriptor/UID không tương thích | `InvalidClassException` |
| Dữ liệu modified UTF-8 không hợp lệ/quá dài | `UTFDataFormatException` |
| Ép kiểu object sai sau `readObject` | `ClassCastException` (unchecked) |
| Java input filter từ chối class/graph | Có thể dẫn đến `InvalidClassException` |

Khi `readExternal` ném lỗi:

- Không dùng object mới dựng dở như object nghiệp vụ hợp lệ.
- Không cố tiếp tục đọc bằng một vị trí tự đoán nếu không có giao thức phục hồi rõ ràng.
- Ghi log hoặc trả lỗi có ngữ cảnh file/request/format version, nhưng không in dữ liệu nhạy cảm.
- Nếu đang đọc từ nguồn không tin cậy, ưu tiên **không dùng native deserialization**; exception handling không loại bỏ rủi ro tạo object trước khi lỗi xuất hiện.

## 15. Custom format và giới hạn tài nguyên

Tính chủ động của Externalizable cho phép bạn kiểm tra dữ liệu trước khi cấp phát:

```java
int itemCount = in.readInt();
if (itemCount < 0 || itemCount > 10_000) {
    throw new InvalidObjectException("Invalid item count");
}
List<String> items = new ArrayList<>(itemCount);
for (int i = 0; i < itemCount; i++) {
    items.add(in.readUTF());
}
```

Đây là đoạn minh họa, cần imports `ArrayList`, `List`, `InvalidObjectException`, `ObjectInput` và khai báo `in`. Việc giới hạn count trước khi tạo `ArrayList` là tốt, nhưng:

- Mỗi `String` vẫn có thể lớn; cần chính sách tổng số byte/string.
- Nếu giao thức cho phép nested objects, cần kiểm soát depth/reference count.
- Nhiều requests đọc đồng thời có thể cộng dồn bộ nhớ lớn; giới hạn concurrency.
- I/O từ stream mạng có thể chậm, cần timeout/backpressure và đóng tài nguyên khi vượt quota.
- Input bị cắt phải báo lỗi rõ, không mặc định khôi phục danh sách còn thiếu.
- `readUTF` có giới hạn riêng; giao thức tự ghi raw UTF-8 cần giới hạn rõ ràng hơn.

## 16. Khác gì với hook readObject/writeObject của Serializable?

Có hai mô hình thường bị nhầm:

### A. Serializable với custom hooks

```java
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Ghi phần custom nếu có.
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Kiểm tra/khôi phục phần custom nếu có.
}
```

Các phương thức `private` đặc biệt này thuộc class `Serializable` thông thường, được nhận diện theo cơ chế serialization; bạn có thể giữ phần field mặc định thông qua `defaultWriteObject`/`defaultReadObject`.

### B. Externalizable với public contract

```java
@Override
public void writeExternal(ObjectOutput out) throws IOException {
    out.writeInt(1);
    out.writeUTF(name);
}

@Override
public void readExternal(ObjectInput in)
        throws IOException, ClassNotFoundException {
    int version = in.readInt();
    if (version != 1) {
        throw new InvalidObjectException("Bad version");
    }
    name = in.readUTF();
}
```

`writeExternal`/`readExternal` phải là **public** vì chúng implement methods của interface. Bạn quyết định payload được ghi; **`defaultWriteObject` không phải bước bắt buộc của Externalizable**, và `ObjectOutput` interface không cung cấp `defaultWriteObject()` như `ObjectOutputStream`.

**Không đặt phương thức `private readExternal` và nghĩ runtime sẽ gọi giống `readObject`.** Đó không phải implementation hợp lệ của interface.

### Khi nào chọn mô hình nào?

- Model đơn giản với nhiều field, cần ít code: `Serializable` mặc định có thể đủ trong môi trường nội bộ tin cậy.
- Cần thêm vài validations/hook mà vẫn muốn phần lớn field mặc định: custom `readObject/writeObject` có thể hợp lý.
- Muốn kiểm soát chặt thứ tự, version và encoding của payload bên trong Java object stream: `Externalizable`.
- Cần định dạng đa ngôn ngữ, version lâu dài hoặc nhận input từ client không tin cậy: **không nên mặc định chọn cả hai**; ưu tiên DTO/schema và serializer phù hợp.

## 17. Security: Externalizable không an toàn trước byte độc hại

`Externalizable` có thể khiến người viết tưởng “tự đọc field nên sẽ an toàn hơn”. Nhưng nó **vẫn được kích hoạt qua `ObjectInputStream.readObject()`**, với class descriptors, việc tạo instance và các hook liên quan. Điều đó vẫn mang rủi ro native Java deserialization.

Tình huống nguy hiểm:

```java
// KHÔNG LÀM với bytes do client không tin cậy gửi.
try (ObjectInputStream in = new ObjectInputStream(networkInput)) {
    Object value = in.readObject();
}
```

Lý do:

- Việc giải mã có thể tạo các class trên classpath với hành vi không mong muốn.
- Public no-arg constructor của Externalizable có thể chạy và gây side effect trước khi payload được validate.
- `readExternal` có thể gọi `in.readObject()` và kéo theo toàn bộ graph phức tạp.
- Dữ liệu có thể bị cố ý thiết kế để tiêu thụ CPU, bộ nhớ hoặc gây stack/resource exhaustion.
- Kiểm tra `instanceof` sau `readObject` có thể đã quá muộn để chặn hành vi trong giai đoạn deserialize.

Nguyên tắc:

1. Tránh Java native deserialization ở **trust boundary**: HTTP payload công khai, dữ liệu do bên ngoài gửi, file từ người không đáng tin.
2. Ưu tiên format dữ liệu đơn giản, DTO/schema, parser được kiểm soát, giới hạn byte/độ sâu/đối tượng.
3. Nếu có legacy dữ liệu Java serialization từ nguồn tin cậy, giới hạn class/array/depth/references qua `ObjectInputFilter` khi phù hợp.
4. Kiểm tra bất biến dữ liệu và kiểm soát version trong `readExternal`, không dựa vào riêng constructor.
5. Không để constructor hoặc `readExternal` thực hiện side effect không thể đảo ngược khi payload chưa được kiểm chứng.
6. Bảo vệ nguồn file và quyền truy cập, có checksum/chữ ký mật mã nếu cần xác thực tính toàn vẹn với bên ngoài; CRC/hash thường không tự chứng minh nguồn đáng tin.

### Ví dụ ObjectInputFilter (chỉ để nhận biết API)

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=100;maxarray=10000;maxbytes=1048576;"
      + "com.example.model.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object object = in.readObject();
}
```

Đây là đoạn minh họa, cần `ObjectInputFilter`, `ObjectInputStream`, một `InputStream source` và xử lý exceptions. Package `com.example.model` chỉ là ví dụ; với một đồ thị chứa `ArrayList`/`String`/các class JDK khác, allowlist thực tế cần xác định từ model và được kiểm thử theo semantics filter.

Filter giúp **giảm** rủi ro trong một số kịch bản, nhưng **không chứng minh mọi input không tin cậy là an toàn**. Nó cũng không thay thế giới hạn nguồn I/O, quota theo request, timeout hay các cơ chế bảo mật tầng ứng dụng.

## 18. Tác động của inheritance và state của superclass

Một class Externalizable có thể kế thừa field và behavior từ superclass. Nhưng **`writeExternal` phải quyết định cách lưu các field cần persist**, kể cả state được sở hữu bởi superclass mà class có thể truy cập qua API hợp lệ.

Ví dụ:

```java
class Base {
    protected int id;

    Base() {
        id = -1;
    }
}

public class Child extends Base implements Externalizable {
    private static final long serialVersionUID = 1L;

    private String name;

    public Child() {
        super();
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeInt(id);
        out.writeUTF(name);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        id = in.readInt();
        name = in.readUTF();
    }
}
```

Đây là ví dụ class minh họa; đặt `Child` vào file `Child.java` cùng `Base` phù hợp và import interfaces/exceptions. `Base` không Serializable nhưng constructor `Base()` chạy thông qua `Child()` khi object Externalizable được dựng. Sau đó `readExternal` khôi phục `id` từ stream. Nếu `Child.writeExternal` **không** ghi `id`, phần state đó chỉ còn giá trị constructor đã khởi tạo hoặc logic khác của ứng dụng.

Điều này khác với việc giả định superclass state được tự động lưu đầy đủ theo serialization mặc định. Với các superclass có invariant phức tạp, nên có API rõ ràng để lấy/đặt trạng thái được phép persist.

## 19. Ghi và đọc nhiều Externalizable object trong một stream

`ObjectOutputStream` quản lý bảng handle **trên phạm vi stream**, không chỉ một lần gọi:

```java
try (ObjectOutputStream out = new ObjectOutputStream(output)) {
    out.writeObject(a);
    out.writeObject(b);
    out.writeObject(a);
}
```

Khi đọc theo đúng thứ tự:

```java
try (ObjectInputStream in = new ObjectInputStream(input)) {
    Object first = in.readObject();
    Object second = in.readObject();
    Object third = in.readObject();
    System.out.println(first == third);
}
```

Đây là hai đoạn minh họa độc lập, với `output` và `input` là cặp stream tương ứng; `a`/`b` cần được khai báo. Nếu cùng instance A được ghi lại mà không reset cơ chế handle, object thứ ba có thể là reference tới object thứ nhất, nên phép so sánh identity trả true.

### Bẫy thay đổi object rồi ghi lại

Giả sử:

```java
out.writeObject(person);
person.setName("New name");
out.writeObject(person);
```

Trong cùng stream, lần ghi thứ hai có thể **chỉ ghi reference** và không gọi lại `writeExternal` để lưu bản cập nhật. Đừng xây append log snapshot bằng cách lặp `writeObject(sameInstance)` rồi hy vọng mỗi lần đều ghi full state.

Nếu muốn một giai đoạn độc lập về handle trong cùng ObjectOutputStream, `out.reset()` có thể được dùng có chủ đích; tương tác với reader và versioned format phải được thiết kế rõ. `writeUnshared`/`readUnshared` là API khác có semantics đặc thù, không tự động deep-clone mọi reference bên trong graph.

## 20. Độ bền file và atomicity không nằm trong Externalizable

Serialization thành công không đồng nghĩa file đã được lưu bền hoặc “cập nhật snapshot” nguyên tử.

Nếu ghi trực tiếp:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(target))) {
    out.writeObject(root);
}
```

một lỗi giữa chừng có thể làm file đích cũ bị cắt hoặc chứa object stream dang dở. Đối với dữ liệu quan trọng:

1. Tạo file tạm độc lập, tốt nhất trong cùng thư mục với đích.
2. Ghi toàn bộ graph và đóng ObjectOutputStream thành công.
3. Nếu bài toán cần độ bền cao, đồng bộ dữ liệu/metadata theo cơ chế filesystem phù hợp và hiểu giới hạn.
4. Validate định dạng/snapshot cần thiết trước khi công bố.
5. Thay thế đích bằng move/rename theo hỗ trợ atomic của provider; nếu atomic là yêu cầu bắt buộc, **không tự động fallback** sang cách không atomic rồi giữ nguyên lời hứa.
6. Có backup/recovery và xử lý file tạm còn sót khi tiến trình sập.

`close()` của ObjectOutputStream không phải lệnh fsync toàn hệ thống; `Files.move(..., ATOMIC_MOVE)` chỉ giải quyết một phần tính nguyên tử cập nhật tên nếu được hỗ trợ và còn các giới hạn về durability/multi-writer.

## 21. Kiểm thử và cách chọn Externalizable

Chọn `Externalizable` khi **đã có lý do cụ thể**:

- Cần điều khiển chính xác dữ liệu trạng thái được lưu vào native Java object stream.
- Muốn tránh lưu những phần graph lớn không cần thiết.
- Muốn một custom payload có version, length và validation do chính class chịu trách nhiệm.
- Cần xử lý compatibility với dữ liệu do một ứng dụng Java nội bộ đáng tin đã lưu.

Không nên chọn chỉ vì:

- Muốn truyền payload mạng công khai.
- Mong tương thích đa ngôn ngữ.
- Nghĩ rằng writeExternal luôn nén tốt hơn, an toàn hơn hoặc nhanh hơn.
- Muốn “mã hóa” dữ liệu (serialization không phải encryption).
- Muốn database có transaction, query, migration hoặc indexing.

### Checklist code review

- [ ] Class thực sự triển khai `Externalizable`, có **public no-arg constructor**.
- [ ] `writeExternal` và `readExternal` đều `public` với chữ ký đúng.
- [ ] Ghi và đọc **đúng thứ tự cùng kiểu dữ liệu**.
- [ ] Có `formatVersion` tường minh khi yêu cầu tương thích lâu dài.
- [ ] Có `serialVersionUID` cố định có chủ đích.
- [ ] Xử lý `null`, empty, UTF, độ dài và giá trị ngoài miền.
- [ ] Không vô ý ghi field nhạy cảm dù nó được đánh dấu transient.
- [ ] Có validation/invariants sau đọc, và không side-effect nguy hiểm từ constructor.
- [ ] Có test graph alias/cycle và trường hợp reference đến class không Serializable.
- [ ] Xử lý `IOException`, `ClassNotFoundException`, `InvalidClassException` và stream lỗi.
- [ ] Không deserialize dữ liệu không tin cậy; giới hạn nguồn/graph khi dùng legacy dữ liệu tin cậy.
- [ ] Nếu persist vào file, có chiến lược ghi, commit và recovery tách biệt.

## 22. Các lỗi thường gặp

1. **Thiếu constructor public không tham số:** deserialization Externalizable thất bại.
2. **Định nghĩa readExternal/writeExternal private:** không implement đúng interface.
3. **Nhầm readExternal với private readObject hook:** hai giao thức/điểm mở rộng khác nhau.
4. **Không ghi đủ field cần phục hồi:** giá trị sau đọc có thể là mặc định/constructor state.
5. **Cho rằng transient tự ngăn writer custom ghi token:** tự gọi `writeUTF(token)` vẫn lưu token.
6. **Đọc sai thứ tự primitive/object:** dữ liệu sai hoặc stream không thể decode.
7. **Dùng writeUTF cho chuỗi quá dài:** có giới hạn modified UTF-8 độ dài 65.535 byte.
8. **Quên ghi rõ null:** `writeUTF(null)` không phải encoding của null.
9. **Không kiểm tra phiên bản custom payload:** reader mới/cũ đọc sai schema.
10. **Tưởng UID khớp là đủ tương thích:** reader vẫn phải hiểu payload bytes.
11. **Tự đệ quy writeExternal trên reference graph có vòng:** bỏ qua object handles của stream và có thể vô hạn.
12. **Không quản lý graph đang xây dựng:** readExternal có thể thấy reference tới object chưa hoàn tất.
13. **Nghĩ đọc object đã được validation đầy đủ:** cần kiểm tra invariant/snapshot sau khi restore.
14. **Viết cùng một instance nhiều lần và mong mỗi lần là snapshot mới:** bảng handles có thể ghi tham chiếu.
15. **Để constructor thực hiện I/O/side effects khi deserialize:** nguy hiểm về bảo mật và lifecycle.
16. **Nhận byte native serialization từ client không tin cậy:** rủi ro security và cạn tài nguyên.
17. **Ghi đè file snapshot duy nhất trực tiếp:** crash có thể làm mất dữ liệu cũ.
18. **Không kiểm thử cross-version/golden files:** đổi code reader/writer cùng lúc có thể che lỗi.
19. **Cho rằng performance tốt vì ít field:** cần đo với object graph thực tế, không suy đoán.
20. **Coi Externalizable là format trao đổi tiêu chuẩn ngoài Java:** vẫn lệ thuộc Java object serialization.

## 23. Bài tập thực hành

**Bài 1 — Tự viết protocol cho một Record.** Tạo class `Report implements Externalizable` có `id`, `createdAtEpochMillis`, `status`. Ghi version 1, String id và long timestamp, một mã byte đại diện status. Đọc lại và xác thực miền của status; thử stream sai version.

**Bài 2 — Thêm trường ở version 2.** Thêm `source` tùy chọn. Định nghĩa V1 không có source, V2 ghi thêm source với boolean presence flag. Reader V2 phải đọc được bytes V1 và V2, không đọc thừa V1.

**Bài 3 — Kiểm tra constructor.** Gán một field transient là `"initialized"` trong public no-arg constructor; không ghi nó trong `writeExternal`. Sau deserialize, kiểm tra giá trị giữ nguyên. Bỏ constructor và dự đoán ngoại lệ.

**Bài 4 — Object graph chia sẻ.** Một `Group` có hai field cùng trỏ một `Node`. Ghi cả hai qua `out.writeObject`, đọc lại và kiểm tra `first == second`. Sau đó tạo vòng hai Node để kiểm tra cycle.

**Bài 5 — Lỗi thứ tự.** Ghi `int` rồi `long`, nhưng cố đọc theo thứ tự ngược. Quan sát lỗi hoặc giá trị bất hợp lý; sửa protocol và viết test golden bytes thay vì chỉ test writer/reader cùng source.

**Bài 6 — Input không hợp lệ.** Ghi `count=-1` hoặc `count` rất lớn vào custom format. Reader phải phát hiện trước khi cấp phát list. Tiếp tục kiểm tra chuỗi dài, version không hỗ trợ và truncated stream.

**Bài 7 — Đánh giá thay thế.** Thiết kế DTO có 5 trường để lưu cấu hình. So sánh native Java Externalizable với JSON hoặc Protocol Buffers về versioning, khả năng review diff, rủi ro bảo mật và tương thích ngôn ngữ.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** `Externalizable` khác `Serializable` marker ở điểm nào?  
**Đáp án:** `Externalizable` khai báo `writeExternal` và `readExternal` để class chủ động ghi/đọc payload; nó vẫn extends `Serializable`.

**Câu 2.** Vì sao class Externalizable cần constructor public không tham số?  
**Đáp án:** Deserialization sử dụng constructor đó để tạo instance trước khi gọi `readExternal`.

**Câu 3.** `writeExternal` không ghi field `age`; sau đọc nó có tự được phục hồi bằng cơ chế field mặc định không?  
**Đáp án:** Không. Giá trị tùy constructor/initializer và logic `readExternal`, vì Externalizable không tự ghi field mặc định.

**Câu 4.** Field `transient password` có thể bị ghi ra stream không?  
**Đáp án:** Có, nếu `writeExternal` chủ động ghi nó. Transient không phải cơ chế chặn writer custom.

**Câu 5.** Viết `out.writeInt(12)` thì phải đọc bằng `readLong` để giữ đủ byte không?  
**Đáp án:** Không. Phải đọc đúng `readInt` và đúng thứ tự schema.

**Câu 6.** Có thể bảo toàn A→B→A bằng Externalizable không?  
**Đáp án:** Có, nếu dùng `out.writeObject`/`in.readObject` cho reference và hợp đồng serialization phù hợp; cơ chế handle quản lý cycle.

**Câu 7.** Nếu `readExternal` trong B đọc reference tới A đang được phục hồi, mọi field của A đã hoàn tất chưa?  
**Đáp án:** Không nhất thiết. Không dựa vào trạng thái hoàn chỉnh của object trong lúc giải đồ thị vòng.

**Câu 8.** `serialVersionUID=1L` và `formatVersion=2` có mâu thuẫn không?  
**Đáp án:** Không. UID thuộc lớp tương thích Java object stream; formatVersion là phiên bản payload tự định nghĩa.

**Câu 9.** Vì sao không dùng Externalizable để deserialize request từ internet?  
**Đáp án:** Nó vẫn dựa trên Java native deserialization, có thể dựng class và chạy constructor/hook nguy hiểm từ byte không tin cậy.

**Câu 10.** `ObjectOutputStream.writeObject(a)` hai lần luôn ghi snapshot state mới ở lần sau không?  
**Đáp án:** Không. Stream có handle table; lần sau có thể chỉ ghi một reference.

**Câu 11.** `ObjectOutputStream.close()` có bảo đảm snapshot file được flush bền qua mất điện không?  
**Đáp án:** Không. Cần chiến lược durability, atomic replacement và recovery theo filesystem.

**Câu 12.** Khi nào Externalizable hợp lý hơn định dạng tự mô tả công khai?  
**Đáp án:** Khi ứng dụng Java nội bộ tin cậy có lý do cần kiểm soát payload trong Java object serialization; không phải mặc định cho API công khai/đa ngôn ngữ.

## 25. Ghi nhớ

- **`Externalizable` mở rộng `Serializable` và yêu cầu public `writeExternal(ObjectOutput)` + `readExternal(ObjectInput)`.**
- **Constructor `public` không tham số là bắt buộc** để khôi phục instance thông thường.
- **Mọi field cần persist phải được ghi/đọc do class quyết định**; `transient`/`static` không ngăn writer custom ghi dữ liệu.
- **Thứ tự, kiểu và version của payload là hợp đồng của chính ứng dụng.** `serialVersionUID` không thay thế custom format version.
- **Đồ thị đối tượng, alias và cycle vẫn có thể được bảo toàn** qua `writeObject`/`readObject` và handles của ObjectOutputStream.
- **Không dùng native Java deserialization cho byte không tin cậy.** Validation, ObjectInputFilter và giới hạn tài nguyên là bổ sung, không thay thế thiết kế trust boundary.
- Externalizable **không phải database, transaction, format đa ngôn ngữ hoặc mã hóa bảo mật**; lựa chọn API phải dựa trên nhu cầu thực tế.

### Tài liệu API Java SE 17

- [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html)
- [ObjectOutput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutput.html)
- [ObjectInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInput.html)
- [ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html)
- [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html)
