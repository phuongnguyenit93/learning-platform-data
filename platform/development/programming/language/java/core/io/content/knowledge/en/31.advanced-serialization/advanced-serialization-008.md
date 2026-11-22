# `@Serial` và kiểm tra khai báo thành viên đặc biệt trong Java Serialization

## 1. Bối cảnh: lỗi nhỏ trong khai báo có thể đổi hành vi tuần tự hóa

Java Object Serialization có một số **field và method đặc biệt** mà cơ chế `ObjectOutputStream`/`ObjectInputStream` tìm kiếm theo **tên, kiểu, modifier và ngữ cảnh lớp**. Những thành viên này không phải là các phương thức thông thường của interface `Serializable`: phần lớn được runtime truy cập theo quy tắc phản chiếu (reflective lookup).

Ví dụ, người viết định nghĩa:

```java
private void writeObject(java.io.OutputStream out)
        throws java.io.IOException {
    // ...
}
```

Tên `writeObject` trông có vẻ đúng, nhưng tham số phải là **`ObjectOutputStream`**, không phải `OutputStream`. Kết quả: đây chỉ là một method Java bình thường, **không phải serialization hook chuẩn**. Java có thể tiếp tục sử dụng serialization mặc định thay vì thực hiện logic bạn mong đợi.

Tương tự, `serialVersionUID` khai báo nhầm kiểu `int`, bỏ `static`/`final`, hoặc tùy biến `readObject` sai chữ ký có thể khiến runtime bỏ qua ý định của tác giả. Những lỗi này khó nhìn ra vì nhiều kiểu khai báo **vẫn hợp lệ với cú pháp Java** và đôi khi biên dịch thành công.

Từ **Java 14**, JDK có annotation `java.io.Serial` (viết `@Serial`) nhằm giúp **compiler nhận diện và cảnh báo các khai báo serialization đặc biệt sai cấu trúc hoặc không có tác dụng**. Đây là công cụ kiểm tra tại thời điểm biên dịch, tương tự tinh thần của `@Override` nhưng phục vụ một nhóm thành viên đặc biệt của Java Serialization.

Bài học thuộc **Java Core I/O → Tuần tự hóa nâng cao**, tập trung vào chính xác `@Serial`, các chữ ký được công nhận, cách bật lint và xử lý warning, hành vi với `Serializable`, `Externalizable`, enum và record, ví dụ Java 17+ có thể chạy, các tình huống lỗi và giới hạn bảo mật.

## 2. `@Serial` thực sự là gì?

Khai báo trong JDK:

```java
package java.io;

@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial {}
```

Đây là **dạng mô tả cấu trúc annotation**, không phải đoạn mã để tự tạo trong project. Trong chương trình, chỉ import:

```java
import java.io.Serial;
```

Các điểm then chốt:

- `@Target({METHOD, FIELD})`: chỉ dành cho **method hoặc field** có vai trò serialization đặc biệt, không gắn lên class, constructor, parameter hay local variable như một tùy chọn chung.
- `@Retention(SOURCE)`: annotation tồn tại trong **source code** để compiler kiểm tra; bản thân annotation **không được giữ để runtime tìm bằng reflection**.
- **Không tạo ra thành viên đặc biệt**: `@Serial` không tự bổ sung `serialVersionUID`, không làm một class triển khai `Serializable`, không thực hiện `writeObject`/`readObject`.
- **Không đổi wire format**: việc thêm annotation lên chữ ký đang đúng không tự đổi byte trong serialization stream.
- **Không thay thế các quy tắc reflection của serialization runtime**: runtime vẫn nhận diện thành viên theo tên/chữ ký/ngữ cảnh được định nghĩa trong Java Object Serialization Specification.
- Compiler **được khuyến khích** cảnh báo khai báo gắn `@Serial` không đúng hoặc không có tác dụng; loại cảnh báo và thời điểm cảnh báo phụ thuộc compiler/JDK/thiết lập lint.

Đặc biệt, `@Serial` **không tương đương** `@Override`: `Serializable` là marker interface, không khai báo `writeObject` để lớp `override`. Việc viết `@Override` lên `private void writeObject(...)` không có cơ sở override thông thường và thường gây lỗi biên dịch; dùng `@Serial` mới đúng ý nghĩa.

## 3. Chính xác bảy thành viên serialization được đánh dấu

Theo Java SE 17 API `java.io.Serial`, có **năm loại method** và **hai loại field** đặc biệt:

| Thành viên | Chữ ký được tài liệu mô tả | Vai trò |
| --- | --- | --- |
| `serialVersionUID` | `private static final long serialVersionUID` | Định danh phiên bản serialization của class |
| `serialPersistentFields` | `private static final ObjectStreamField[] serialPersistentFields` | Khai báo tập field trong serial form khi tùy biến |
| `writeObject` | `private void writeObject(ObjectOutputStream out) throws IOException` | Tùy biến cách ghi state của một lớp `Serializable` |
| `readObject` | `private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException` | Tùy biến cách khôi phục state và validate dữ liệu |
| `readObjectNoData` | `private void readObjectNoData() throws ObjectStreamException` | Khởi tạo khi thiếu dữ liệu serialization cho lớp trong một số tình huống tiến hóa hierarchy |
| `writeReplace` | `Object writeReplace() throws ObjectStreamException` (access theo quy tắc tương ứng) | Thay đối tượng được ghi bằng một đối tượng thay thế |
| `readResolve` | `Object readResolve() throws ObjectStreamException` (access theo quy tắc tương ứng) | Thay đối tượng vừa được giải tuần tự hóa bằng giá trị thay thế |

Bảy dòng này mô tả **hợp đồng được tài liệu hóa**. Đối với `writeReplace` và `readResolve`, chữ ký return `Object` trong tài liệu biểu diễn vai trò kết quả; runtime và compiler có các quy tắc truy cập/kiểu trả về hợp lệ chi tiết hơn tùy JDK. Khi dạy và viết code, dùng chữ ký rõ ràng như bảng là an toàn, dễ rà soát.

Các chữ ký `throws` trong ví dụ là cách viết chuẩn để phản ánh exception có thể phát sinh. Trong ngôn ngữ Java, `throws` **không phải thành phần của JVM method descriptor**: một method không khai báo đúng danh sách `throws` chưa chắc bị runtime bỏ qua chỉ vì điều đó. Trọng tâm nhận diện là tên, số và kiểu tham số, return type/access và vị trí khai báo theo hợp đồng serialization.

### 3.1. Hai field

```java
@Serial
private static final long serialVersionUID = 1L;

@Serial
private static final ObjectStreamField[] serialPersistentFields = {
    new ObjectStreamField("id", long.class),
    new ObjectStreamField("name", String.class)
};
```

Đoạn trên là **khai báo bên trong một class `Serializable`** có import `java.io.Serial`, `java.io.ObjectStreamField`; chưa phải một ví dụ hoàn chỉnh có logic `writeObject`/`readObject`. Chỉ dùng `serialPersistentFields` khi thực sự thiết kế serial form riêng; với DTO thông thường, **không cần khai báo** field này.

Mẹo: `serialVersionUID` là **giá trị `long`**, không phải `int`; thêm hậu tố `L` giúp rõ ý. Khai báo `private` là thực hành được khuyến nghị vì UID của class không có ý nghĩa kế thừa như một API của superclass.

### 3.2. Năm method

```java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}

@Serial
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException("Missing serialized class data");
}

@Serial
private Object writeReplace() throws ObjectStreamException {
    return this;
}

@Serial
private Object readResolve() throws ObjectStreamException {
    return this;
}
```

Đây là **tập các ví dụ chữ ký đặt bên trong class Serializable**, không phải lời khuyên gắn cả năm method vào mọi class: chỉ khai báo hook khi cần tính năng đó. Cần import `java.io.*`. Các hook có vai trò riêng và có thể thay đổi graph, identity hoặc định dạng dữ liệu; việc `return this` trong minh họa `writeReplace/readResolve` không tạo ra lợi ích thực tế.

**Hai phương thức private `writeObject`/`readObject` không được gọi trực tiếp từ code ứng dụng** như callback bình thường. Trong quá trình serialization/deserialization, runtime nhận diện chúng và gọi ở thời điểm được đặc tả. Bên trong `writeObject`, `defaultWriteObject()` chỉ hợp lệ khi đang thực hiện serialization hook tương ứng; `defaultReadObject()` có quy tắc tương tự.

## 4. `serialVersionUID`: một lỗi thường được `@Serial` giúp phát hiện

Một khai báo đúng:

```java
import java.io.Serial;
import java.io.Serializable;

public class OrderSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final long orderId;

    public OrderSnapshot(long orderId) {
        this.orderId = orderId;
    }
}
```

Nếu thay `long` thành `int`:

```java
@Serial
private static final int serialVersionUID = 1; // Sai kiểu
```

thì field có thể trở thành **một static field thường**, không phải UID được serialization runtime sử dụng. Nếu không có UID hợp lệ, runtime có thể tính UID mặc định dựa trên cấu trúc class — khác với ý định “UID là 1”.

Các lỗi khác: `private long serialVersionUID` thiếu `static final`, tên sai chữ hoa/thường như `serialVersionId`, hoặc khai báo UID trong lớp không serializable rồi nghĩ annotation biến nó thành metadata có hiệu lực.

**`@Serial` không tự định nghĩa UID**. Nó chỉ đánh dấu khai báo hiện có để compiler có cơ hội kiểm tra. `javac -Xlint:serial` còn có thể cảnh báo khi class serializable thiếu UID, dù class ấy chưa dùng `@Serial`.

Không tùy tiện đổi UID chỉ để dập `InvalidClassException`: UID là một phần kiểm tra class compatibility, không bảo đảm dữ liệu serialized ở hai phiên bản có cấu trúc và ngữ nghĩa tương thích.

## 5. `writeObject` và `readObject` phải khớp chữ ký

Hai khai báo đúng thông dụng:

```java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    out.writeInt(42);
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    int marker = in.readInt();
}
```

Chúng phải nằm trong class triển khai `Serializable` **và không dùng mô hình `Externalizable` tương ứng**. Mỗi hook xử lý state của lớp khai báo nó; `defaultWriteObject()`/`defaultReadObject()` ghi và khôi phục các field mặc định của chính lớp đó.

Hai lỗi rất dễ xuất hiện:

```java
@Serial
private void writeObject(OutputStream out) throws IOException {
    // Sai: tham số không phải ObjectOutputStream
}

@Serial
private void readObject(ObjectInputStream in, int version)
        throws IOException, ClassNotFoundException {
    // Sai: có thêm tham số int
}
```

Đây là **mã cố ý sai về hợp đồng serialization**; một class Java vẫn có thể biên dịch các method trên như method thường (có thể kèm warning), nhưng serialization engine **không coi chúng là hook đúng**. Dùng `@Serial` và bật `-Xlint:serial` để compiler hỗ trợ phát hiện sớm.

Chú ý trường hợp `protected void writeObject(ObjectOutputStream out)`: tính `private` của `writeObject`/`readObject` là yêu cầu có ý nghĩa. Cùng tên và tham số nhưng access khác không thay thế hook private trong giao thức mặc định của Serializable.

## 6. Ví dụ Java 17+ chạy độc lập, đã xác minh biên dịch

Ví dụ dưới đây dùng `@Serial` cho UID và ba hook có chữ ký đúng. Lớp `Profile` có field `name` được ghi theo cơ chế mặc định, còn `marker` được đánh dấu `transient` và ghi tường minh vào phần dữ liệu bổ sung. Hook `readObjectNoData` minh họa việc từ chối thiếu dữ liệu cho class, nhưng **không kích hoạt trong luồng ghi/đọc bình thường của demo**.

Tạo file `SerialAnnotationDemo.java`:

```java
import java.io.*;
import java.util.Objects;

public class SerialAnnotationDemo {
    private static class Profile implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private String name;
        private transient int marker;

        Profile(String name) {
            this.name = Objects.requireNonNull(name);
        }

        @Serial
        private void writeObject(ObjectOutputStream out) throws IOException {
            out.defaultWriteObject();
            out.writeInt(42);
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            marker = in.readInt();
            if (name == null || name.isBlank()) {
                throw new InvalidObjectException("Invalid name");
            }
        }

        @Serial
        private void readObjectNoData() throws ObjectStreamException {
            throw new InvalidObjectException(
                    "No serialized profile data");
        }
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Profile("Lan"));
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Profile restored = (Profile) in.readObject();
            System.out.println("name=" + restored.name);
            System.out.println("marker=" + restored.marker);
        }
    }
}
```

Biên dịch và chạy (JDK 17+):

```bash
javac -Xlint:serial SerialAnnotationDemo.java
java SerialAnnotationDemo
```

Stdout:

```text
name=Lan
marker=42
```

**Giải thích:**

1. `Profile implements Serializable`; nếu thiếu interface này, `@Serial` không tự làm class serializable.
2. `@Serial private static final long serialVersionUID=1L` là UID hợp lệ.
3. `writeObject` được nhận diện, gọi `defaultWriteObject()` để ghi `name`. `marker` là transient, **không nằm trong phần field mặc định**.
4. `writeInt(42)` ghi thêm một giá trị theo định dạng do class định nghĩa, bên trong custom data của hook.
5. `readObject` dùng `defaultReadObject()`, rồi `readInt()` theo cùng thứ tự để gán `marker=42`. Nếu đổi thứ tự đọc hoặc bỏ phần dữ liệu tương ứng, stream có thể lỗi.
6. `InvalidObjectException` dùng để bảo vệ invariant `name`; không tin constructor `Profile(String)` sẽ chạy khi khôi phục một object Serializable thông thường.
7. `readObjectNoData` được đánh dấu đúng và làm nhiệm vụ riêng khi không có class data trong một số tình huống tiến hóa hierarchy; nó không được gọi mỗi khi `readObject()` trả về object.
8. Program thực hiện round-trip trong memory, nên không phụ thuộc đường dẫn file, bộ mã console cho tiếng Việt hoặc tốc độ hệ thống.

Đã xác minh mẫu biên dịch với `javac -Xlint:serial` và chạy cho đúng hai dòng stdout trên trong môi trường JDK hỗ trợ `@Serial`.

### 6.1. Có bắt buộc dùng dấu `@Serial` không?

**Không.** Trước Java 14, các thành viên serialization đặc biệt đã hoạt động mà không cần annotation, và trên Java 17 nó vẫn là annotation **khuyến nghị để kiểm tra**. Bỏ `@Serial` khỏi một hook có chữ ký đúng không tự tắt hook; thêm annotation vào hook sai không sửa được hook.

Với dự án chỉ hỗ trợ JDK 8 hoặc JDK 11, **`java.io.Serial` không tồn tại** trong các phiên bản đó. Không thêm import này khi đang biên dịch bằng release cũ; ví dụ `javac --release 11` không có API này. Mã dùng `@Serial` phù hợp với target Java 14+.

## 7. Thử khai báo sai và quan sát compiler warning

Ví dụ sai có chủ ý, tạo file `BadSerialDeclarations.java`:

```java
import java.io.*;

class BadSerialDeclarations implements Serializable {
    @Serial
    private static final int serialVersionUID = 1; // int, không phải long

    @Serial
    private void writeObject(OutputStream out) throws IOException {
        // Sai kiểu tham số: OutputStream thay vì ObjectOutputStream
    }

    @Serial
    private void readObject(ObjectInputStream in) throws IOException {
        // Có thể là hook hợp lệ nếu những yếu tố nhận diện cần thiết đúng.
    }
}
```

Lệnh:

```bash
javac -Xlint:serial BadSerialDeclarations.java
```

Với `javac` có hỗ trợ phân tích serial annotation, sẽ có cảnh báo thuộc nhóm `[serial]` về `serialVersionUID` sai kiểu và `writeObject` nhận `OutputStream` thay cho `ObjectOutputStream`. **Văn bản thông báo và số lượng warning có thể khác theo JDK/compiler**, không nên hardcode các dòng message làm kết quả kiểm thử ổn định.

Đây là mã **cố ý sai về mục đích**, không dùng làm mẫu triển khai. Đặc biệt, `readObject` trong ví dụ chỉ khai báo `throws IOException`, không khai báo `ClassNotFoundException`; riêng điều đó không nhất thiết khiến hook bị vô hiệu, vì `throws` không phải phần của method descriptor. Tuy vậy, khi viết method thực tế, nên dùng chữ ký đã được tài liệu hóa đầy đủ và chuẩn bị xử lý `ClassNotFoundException` nếu cần gọi các API ném checked exception ấy.

Nếu muốn biến warning thành lỗi build trong CI:

```bash
javac -Xlint:serial -Werror BadSerialDeclarations.java
```

`-Werror` yêu cầu compilation thất bại khi compiler đã phát warning. Nó không tự tạo warning mới: phải bật lint thích hợp và dùng một compiler thực sự có kiểm tra tương ứng. Build tool Maven/Gradle có cách riêng để truyền `-Xlint:serial` và `-Werror` xuống `javac`.

## 8. Tại sao `@Serial` hữu ích hơn chỉ nhìn code?

Một số khai báo sai vẫn là Java hợp lệ:

| Khai báo | Compile Java thông thường? | Ý nghĩa serialization |
| --- | --- | --- |
| `private static final long serialVersionUID=1L` | Có | UID đúng định dạng |
| `private static final int serialVersionUID=1` | Có thể | **Không phải** UID đúng, compiler có thể cảnh báo |
| `private void writeObject(OutputStream x)` | Có thể | Không phải serialization hook |
| `public void writeObject(ObjectOutputStream x)` | Có thể | Không đúng hook private chuẩn |
| `private void readObject(ObjectInputStream x, int version)` | Có thể | Sai tham số, không phải hook |
| `private void readObject(ObjectInputStream x)` | Có thể | Có thể là hook hợp lệ xét theo tham số/access, cần xử lý exception đúng cách |
| `private static Object readResolve()` | Có thể | Không phải hook instance phù hợp |
| `private static final ObjectStreamField[] serialPersistentFields` | Có thể | Field định nghĩa serial form nếu ở class/ngữ cảnh hợp lệ |

Thông điệp quan trọng: **Java hợp lệ về cú pháp không đồng nghĩa được Java Object Serialization dùng như thành viên đặc biệt**. Annotation khiến mục đích của developer rõ hơn và giúp compiler phát hiện sai khác. Không gắn `@Serial` lên mọi method liên quan đến serialization theo nghĩa nghiệp vụ; nó chỉ dành cho nhóm thành viên đã được API quy định.

## 9. `serialPersistentFields` và trường hợp tùy biến serial form

`serialPersistentFields` là một array `ObjectStreamField[]` private static final dùng khai báo **field set của serial form**, không nhất thiết trùng trực tiếp với mọi field Java hiện có.

Ví dụ:

```java
import java.io.ObjectStreamField;
import java.io.Serial;
import java.io.Serializable;

class LegacyAccount implements Serializable {
    @Serial
    private static final long serialVersionUID = 2L;

    @Serial
    private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("accountId", long.class),
        new ObjectStreamField("displayName", String.class)
    };

    private long accountId;
    private String displayName;
    private transient String sessionHandle;
}
```

Ví dụ này là **class có thể biên dịch**; nếu muốn custom mapping phức tạp, phải thiết kế `writeObject`/`readObject` tương ứng với `ObjectOutputStream.PutField`/`ObjectInputStream.GetField` hoặc phương án phù hợp. `@Serial` **không tự kiểm chứng** rằng field list khớp schema nghiệp vụ hoặc dữ liệu phiên bản trước.

Một nhầm lẫn phổ biến là khai báo:

```java
@Serial
public static ObjectStreamField[] serialPersistentFields = ...;
```

Khi access/type/modifier sai, nó không đại diện cho field đặc biệt theo hợp đồng. Compiler hỗ trợ `@Serial` có thể cảnh báo nếu bạn đánh dấu như thế. Không nên sửa bằng cách bỏ annotation để tắt warning; phải sửa lại chữ ký hoặc thay thiết kế serial form.

## 10. `writeReplace` và `readResolve`: chú ý identity, substitution

Hai hook này không có tham số:

```java
@Serial
private Object writeReplace() throws ObjectStreamException {
    return this;
}

@Serial
private Object readResolve() throws ObjectStreamException {
    return this;
}
```

Đây là snippet để diễn giải chữ ký, **không phải bài học rằng luôn trả `this`**. Thực tế:

- `writeReplace`: trước khi ghi object, có thể thay bằng một object khác dùng làm proxy/đại diện serialized.
- `readResolve`: sau khi đọc một object, có thể thay kết quả bằng singleton, canonical object hoặc object bảo đảm invariant.
- Method có thể dùng modifier truy cập phù hợp, nhưng **khả năng kế thừa và truy cập của runtime** vẫn chịu quy tắc Java serialization. Trong ví dụ căn bản, dùng `private` nếu hook chỉ dành cho class hiện tại.
- Object thay thế phải tương thích với các tham chiếu dự kiến; thay type tùy tiện có thể gây `ClassCastException` hoặc phá graph.
- Những hook này có thể chạy code ứng dụng trong quá trình đọc dữ liệu và do đó cần lưu ý đặc biệt về **deserialization security**.

Một ví dụ pattern thường gặp là **serialization proxy**:

```text
Object domain -> writeReplace() -> Serializable Proxy
Serializable Proxy -> readResolve() -> Object domain hợp lệ
```

Proxy có thể giúp kiểm soát dạng lưu trữ và khôi phục invariant, nhưng cần code cẩn thận, tính tương thích và kiểm thử để tránh thay thế sai object. Annotation chỉ kiểm tra **hình thức khai báo**, không kiểm tra logic proxy.

## 11. `readObjectNoData`: khi nào có tác dụng?

`readObjectNoData()` không phải “`readObject()` trả EOF” và không phải một lời gọi tùy tiện mỗi khi field rỗng. Nó được dùng trong một số tình huống **class descriptor/hierarchy tiến hóa**, khi stream không chứa dữ liệu của một lớp local cần khởi tạo trong quá trình khôi phục object.

Một chữ ký đúng:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException("No class data");
}
```

Nếu class phải thiết lập giá trị mặc định hợp lệ khi không có data, có thể thực hiện logic thích hợp thay vì ném. Nếu dữ liệu thiếu thể hiện bất thường hoặc tampering, từ chối rõ ràng thường dễ kiểm soát hơn.

Không dùng `readObjectNoData` thay cho kiểm tra EOF của `ObjectInputStream.readObject()`. Gọi `readObject()` khi stream đã kết thúc có thể ném `EOFException`; đây là hiện tượng khác.

## 12. Những ngữ cảnh mà `@Serial` có thể không có ý nghĩa

### 12.1. Class không triển khai `Serializable`

```java
class NonSerializable {
    @Serial
    private static final long serialVersionUID = 1L;
}
```

Đây là mã **cố ý không hợp ngữ cảnh**. Annotation không khiến class được tuần tự hóa; compiler có thể cảnh báo vì field UID này không tham gia Java serialization. Nếu mục tiêu thật sự là serialize lớp, phải `implements Serializable` và thiết kế các field/runtime dependency phù hợp.

### 12.2. `Externalizable` khác `Serializable` mặc định

`Externalizable` **kế thừa `Serializable`** nhưng sử dụng các method public `writeExternal(ObjectOutput)`/`readExternal(ObjectInput)` để kiểm soát nội dung. Với class `Externalizable`:

- `@Serial` **không dành cho** `writeExternal`/`readExternal`: chúng không nằm trong danh sách bảy thành viên.
- Các hook `writeObject`, `readObject`, `readObjectNoData` của Serializable mặc định **không có tác dụng** theo cơ chế Externalizable.
- `serialPersistentFields` cũng **không được dùng** bởi mô hình Externalizable.
- `serialVersionUID` và một số cơ chế substitution có thể vẫn có vai trò theo giao thức; cần áp dụng đúng vào thành viên thật sự có ý nghĩa.
- Khả năng khôi phục Externalizable yêu cầu tuân thủ hợp đồng constructor public không đối số và API Externalizable; annotation không thay đổi yêu cầu đó.

Ví dụ sai về phạm vi:

```java
class ManualRecord implements java.io.Externalizable {
    @Serial
    private void writeObject(ObjectOutputStream out)
            throws IOException {
        // Không phải hook có tác dụng với Externalizable.
    }

    public ManualRecord() {}
    public void writeExternal(java.io.ObjectOutput out)
            throws IOException {}
    public void readExternal(java.io.ObjectInput in)
            throws IOException, ClassNotFoundException {}
}
```

Đây là **mã mô tả trường hợp sai**, cần import `java.io.*` để biên dịch; mục tiêu chỉ là cho thấy `writeObject` không thay thế `writeExternal`. Compiler có thể cảnh báo annotation không phù hợp với ngữ cảnh `Externalizable`.

### 12.3. Enum: serialization đặc biệt, không custom bằng các hook này

Enum mặc nhiên serializable nhưng serialization của enum lưu thông tin nhận diện constant theo quy tắc riêng, không tuần tự hóa instance fields như class thông thường. Hợp đồng Java quy định `serialVersionUID` của enum là `0L`. Các hook `writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, `readResolve` do enum tự khai báo **bị bỏ qua** bởi enum serialization.

Vì vậy, đánh dấu `@Serial` lên UID hoặc các hook riêng bị bỏ qua trong enum là **sai ngữ cảnh**, dù một số khai báo vẫn biên dịch như method/field Java thường. Đừng sử dụng `@Serial` như cách tùy biến enum serialization.

### 12.4. Record: cần phân biệt hook bị bỏ qua và hook thay thế

Một `record` có thể `implements Serializable`, nhưng serialization của record xử lý **record components và canonical constructor** theo quy tắc riêng. Các `writeObject`, `readObject`, `readObjectNoData` và `serialPersistentFields` của record **không hoạt động như trong class thông thường**.

Theo Java Serialization Specification, record vẫn có thể sử dụng **`writeReplace`/`readResolve`** để thay thế object theo hợp đồng tương ứng. Record có serialVersionUID mặc định 0L nếu không khai báo, và quy tắc so khớp UID của record khác với class serializable thông thường.

Do đó, không nói đơn giản “mọi hook trong record đều được nhận” hoặc “mọi hook đều bị bỏ qua”. Khi đánh dấu `@Serial` ở record, phải xem thành viên đó có **thực sự có tác dụng** theo quy tắc riêng. Dùng các ví dụ/tài liệu serialization records cụ thể và compiler phù hợp để kiểm chứng.

## 13. Bật kiểm tra trong build/CI

Một lệnh thực hành để phát hiện vấn đề:

```bash
javac -Xlint:serial SerialAnnotationDemo.java
```

`-Xlint:serial` là nhóm cảnh báo về serialization; ngoài khai báo gắn `@Serial` sai, nó còn có thể giúp phát hiện class serializable **không khai báo UID** theo compiler/JDK.

Tùy quy định dự án, có thể dùng:

```bash
javac -Xlint:serial -Werror SerialAnnotationDemo.java
```

để biến những warning đã được phát thành lỗi build. Trong CI:

1. Chọn phiên bản `javac` và `--release` thống nhất với Java hỗ trợ.
2. Bật cảnh báo serial, xây dựng chính sách có giải thích cho các trường hợp ngoại lệ.
3. Với các class mới/đổi serialization hook, chạy unit test round-trip object và test đọc dữ liệu phiên bản cũ nếu có.
4. Đảm bảo không bỏ qua warning bằng cách gỡ `@Serial` mà không sửa logic.
5. Phân biệt warning khác biệt giữa JDK 17/21+; không ép **chính xác văn bản cảnh báo** làm một phần protocol nghiệp vụ.

**Cần nhớ:** `-Xlint:serial` không phải bộ phân tích toàn bộ rủi ro deserialization; nó giúp kiểm tra một nhóm khai báo và quy ước Java compiler. Mã đúng chữ ký vẫn có thể nguy hiểm hoặc sai logic.

## 14. Giới hạn của `@Serial`: đúng khai báo chưa chắc đúng chương trình

Annotation không bảo vệ các lỗi:

- Gọi `out.writeInt(a)`, `out.writeUTF(b)` nhưng phía `readObject` đọc ngược thứ tự.
- Quên `defaultWriteObject()` trong khi phía `defaultReadObject()` mong có field mặc định, khiến dữ liệu không khớp.
- Ghi thêm field nhạy cảm bằng custom `writeObject()` rồi tưởng nó được ẩn chỉ vì khai báo `transient`.
- Dùng `readResolve()` trả object sai type hoặc làm sai tính duy nhất của singleton.
- Không validate invariant sau `defaultReadObject()`.
- Giữ `serialVersionUID` cố định trong khi thay đổi serialized form một cách không tương thích.
- Dùng `ObjectInputStream` để deserialize byte từ nguồn không đáng tin cậy, dù tất cả hook đều mang annotation đúng.

Đây là **tooling ở thời điểm viết/biên dịch**, không phải sandbox, serialization firewall, kiểm tra schema, xác thực nguồn hoặc cơ chế chống lỗi runtime.

## 15. Bảo mật và `ObjectInputFilter`

Nếu có thể, **không dùng native Java deserialization với dữ liệu untrusted**. Quá trình `ObjectInputStream.readObject()` có thể kích hoạt code của các class trong graph, bao gồm custom `readObject`, `readResolve` hoặc `Externalizable.readExternal`, **trước khi caller có cơ hội cast/validate object kết quả**.

Trong hệ thống legacy bắt buộc đọc Java Object Serialization, cần chính sách nhiều lớp:

- Xác thực và kiểm tra integrity nguồn byte.
- Chỉ cho phép danh sách class cần thiết, dùng `ObjectInputFilter` trước lời gọi `readObject`.
- Giới hạn depth, số references, kích thước array, tổng byte, timeout, số request đồng thời.
- Kiểm toán gadget trên classpath và cập nhật thư viện.
- Cô lập tác vụ xử lý nếu mô hình rủi ro yêu cầu.
- Validate business invariants trong `readObject` hoặc lớp đối tượng thích hợp, nhưng không xem validation sau đọc là đủ để chặn exploit.

Ví dụ minh họa cơ chế filter:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
            "maxdepth=10;maxrefs=100;maxbytes=1048576;"
          + "maxarray=10000;com.example.dto.*;!*");
in.setObjectInputFilter(filter);
```

Đây là **snippet**, cần `import java.io.ObjectInputFilter;` và `ObjectInputStream in` đã được khởi tạo. Thay package `com.example.dto.*` bằng các lớp thật cần được phép, và kiểm thử dữ liệu hợp lệ; nếu allowlist quá hẹp, việc đọc có thể bị từ chối. Bộ lọc không thay thế lựa chọn một định dạng an toàn hơn, cũng không bảo đảm mọi side effect đều biến mất.

**`@Serial` không can thiệp vào bộ lọc**. Một hook `@Serial` được khai báo hoàn hảo vẫn có thể thực hiện logic gây hại nếu giải tuần tự hóa dữ liệu độc hại.

## 16. Tình huống sửa lỗi theo thứ tự hợp lý

Giả sử bạn khai báo:

```java
@Serial
private void readObject(java.io.DataInputStream in)
        throws java.io.IOException {
    // ...
}
```

Đây là method Java thường, **không phải hook `readObject` của Serializable**. Khi thấy kết quả deserialize không chạy đoạn code kỳ vọng:

1. Kiểm tra class có thực sự `implements Serializable` hay không.
2. Kiểm tra đây là `Serializable` mặc định hay `Externalizable`, enum hoặc record.
3. Đối chiếu chữ ký hook chuẩn: `ObjectInputStream`, `private void`, không thêm tham số.
4. Bật `javac -Xlint:serial` và kiểm tra tất cả warning.
5. Dùng test round-trip có assertion rằng hook thực sự chạy; đừng chỉ kiểm tra compile.
6. Kiểm tra reader/writer field order và cơ chế `defaultWriteObject/defaultReadObject`.
7. Kiểm tra serialVersionUID và bản dữ liệu cũ nếu có versioning.
8. Chỉ sau khi hợp đồng khai báo đúng mới xem logic serialization và security policy.

Không nên “chữa” lỗi bằng cách thêm `@Serial` vào method sai rồi coi việc biên dịch là đủ.

## 17. Bài tập và lời giải

**Câu 1.** `@Serial` có khiến `class Account` tự triển khai `Serializable` không?

**Đáp án:** Không. Annotation kiểm tra các khai báo đặc biệt; class vẫn phải nằm trong ngữ cảnh serialization hợp lệ, thường `implements Serializable`.

**Câu 2.** Annotation `@Serial` có còn trong classfile để runtime tìm bằng reflection không?

**Đáp án:** Bản thân annotation có `RetentionPolicy.SOURCE`, nên không được giữ làm annotation runtime; serialization runtime nhận diện thành viên theo quy tắc riêng.

**Câu 3.** `@Serial private static final int serialVersionUID=1` có đúng không?

**Đáp án:** Sai kiểu. UID đúng là `long` và các modifier thích hợp, ví dụ `@Serial private static final long serialVersionUID=1L;`.

**Câu 4.** `@Serial private void writeObject(OutputStream out)` được Object Serialization gọi như hook không?

**Đáp án:** Không; tham số phải là `ObjectOutputStream`. Đây là lý do phải bật compiler check.

**Câu 5.** Nếu class `Serializable` có `private void readObject(ObjectInputStream in) throws IOException` mà không có `ClassNotFoundException`, nó có chắc bị bỏ qua không?

**Đáp án:** Không. `throws` không thuộc JVM descriptor. Tuy nhiên tài liệu mô tả chữ ký chuẩn bao gồm hai exception; trong code thực tế nên dùng chữ ký chuẩn và chỉ dùng API có checked exception theo cách Java cho phép.

**Câu 6.** Có thể gắn `@Serial` lên `writeExternal` của `Externalizable` không?

**Đáp án:** Không đúng mục đích; `writeExternal` không thuộc nhóm năm hook được `@Serial` định nghĩa. `Externalizable` dùng cơ chế riêng.

**Câu 7.** Enum có thể tùy chỉnh serialization bằng `@Serial private Object readResolve()` không?

**Đáp án:** Không. Các serialization hooks do enum khai báo bị cơ chế serialization enum bỏ qua; annotation không thay đổi điều đó.

**Câu 8.** Record `Serializable` có được dùng custom `readObject()` để đọc component như class bình thường không?

**Đáp án:** Không; serialization record có quy tắc riêng, custom `readObject` bị bỏ qua. Nhưng `writeReplace`/`readResolve` vẫn có thể có tác dụng theo specification.

**Câu 9.** Vì sao chỉ khai báo `serialVersionUID` và thêm `@Serial` không đủ bảo đảm dữ liệu cũ đọc được?

**Đáp án:** UID chỉ tham gia compatibility check; field types, class hierarchy, hooks, serialized form và invariants vẫn có thể thay đổi không tương thích.

**Câu 10.** Compiler cảnh báo `@Serial` sai ngữ cảnh. Có nên chỉ xóa annotation để yên warning không?

**Đáp án:** Không. Hãy xác định thành viên đó có thật sự được runtime dùng không; sửa chữ ký/ngữ cảnh nếu muốn dùng hook hoặc bỏ hook không cần thiết.

**Câu 11.** `-Werror` có tự phát hiện mọi lỗi serialization không?

**Đáp án:** Không. Nó chỉ chuyển warning compiler đã phát thành build error; unit test, versioning test và security review vẫn cần thiết.

**Câu 12.** Hook `readResolve` mang `@Serial` đúng có an toàn khi deserialize untrusted input không?

**Đáp án:** Không thể kết luận. Annotation chỉ hỗ trợ kiểm tra khai báo; logic hook, object graph và nguồn byte vẫn có thể gây rủi ro.

## 18. Checklist khi rà soát code serialization

1. Mỗi class `Serializable` có thực sự cần serialized form không? Nếu không, chọn DTO/định dạng khác.
2. UID khai báo bằng `private static final long` với `@Serial` và giá trị được quản lý theo compatibility policy.
3. Hook `writeObject/readObject/readObjectNoData` có tên, access, return type và tham số chính xác không?
4. `serialPersistentFields` có đúng kiểu `ObjectStreamField[]`, đúng modifier và thực sự cần custom serial form không?
5. `writeReplace/readResolve` có truy cập, kiểu kết quả, substitution và tính kế thừa hợp lệ không?
6. Có gắn `@Serial` lên method/field không có tác dụng trong `Externalizable`, enum hoặc record không?
7. Build bật `-Xlint:serial` và quản lý warning thay vì bỏ qua?
8. Unit test round-trip, class versioning, edge cases và dữ liệu sai có tồn tại không?
9. Custom hooks có giữ invariant, field order và exception semantics đúng không?
10. Không giải tuần tự hóa đầu vào không tin cậy; nếu bắt buộc, filter/quota/isolation được áp dụng **trước** lần đọc?
11. Code chạy ở phiên bản Java có `java.io.Serial` (14+) không?
12. Có tài liệu về lý do mỗi custom member tồn tại, để những lần refactor không âm thầm vô hiệu hóa hook?

## Tài liệu tham khảo chính thức

- Java SE 17 — `java.io.Serial`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html
- Java SE 17 — `java.io.Serializable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Java SE 17 — `ObjectOutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html
- Java SE 17 — `ObjectInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html
- Java SE 17 — `ObjectStreamField`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectStreamField.html
- Java Object Serialization Specification, System Architecture (bao gồm enum/records): https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html
- Java Object Serialization Specification, Object Input Classes: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html
- `javac` compiler tool và lint options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
