# Chẩn đoán tên hoặc chữ ký khai báo sai bằng công cụ với @Serial

## 1. Vì sao lỗi khai báo serialization rất khó phát hiện?

Trong cơ chế **Java Object Serialization**, một số field và method có **tên/chữ ký đặc biệt** được `ObjectOutputStream` và `ObjectInputStream` nhận biết để tham gia tuần tự hóa hoặc giải tuần tự hóa object. Những method như `writeObject`, `readObject` và `readResolve` thường không được gọi trực tiếp trong mã Java ứng dụng; chúng được hệ thống serialization tra cứu theo quy ước.

Một lỗi gõ tên hoặc khai báo sai tham số có thể làm method **vẫn biên dịch thành công nhưng không bao giờ được cơ chế serialization gọi**. Ví dụ:

~~~java
private void readObjects(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
~~~

Tên đúng phải là **`readObject`** (không có chữ `s` cuối). Đây là một method Java hợp lệ, nhưng **không phải callback `readObject` đặc biệt** theo đặc tả serialization. Ứng dụng có thể âm thầm dùng hành vi mặc định thay vì logic dự định.

Java 14 bổ sung annotation **`java.io.Serial`** để đánh dấu các khai báo liên quan đến serialization. Annotation giúp **trình biên dịch hoặc công cụ phân tích mã** xác minh chúng có hình thức và ngữ cảnh phù hợp. Tuy nhiên, công cụ **không bảo đảm phát hiện mọi lỗi đặt tên**, vì vậy phải kết hợp:
1. Annotation `@Serial` tại đúng field/method.
2. `javac -Xlint:serial` để bật cảnh báo liên quan.
3. `javac -Werror` để biến cảnh báo thành lỗi build khi phù hợp.
4. `javap -p -s` để kiểm tra tên và JVM method descriptor thật.
5. Kiểm thử **serialize → deserialize** và xác nhận callback thực sự được gọi hoặc kết quả đúng.

**Tính hiện hành:** `@Serial` thuộc `java.io`, có từ **Java 14** và vẫn tồn tại trong các JDK hiện đại (Java 17, 21, 25). Ví dụ chính dùng **`javac --release 17`**. Chỉ đề cập API còn hỗ trợ; không sử dụng hay khuyến nghị những thủ thuật can thiệp nội bộ JVM lỗi thời.

## 2. @Serial là gì và không phải là gì?

Khai báo trong JDK:

~~~java
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial {}
~~~

Đây là **mô tả hình thức API**, không phải tệp Java cần tự định nghĩa lại. Annotation thật đã có trong `java.base`:

~~~java
import java.io.Serial;
~~~

Đặc điểm quan trọng:

- `@Target({METHOD, FIELD})`: annotation chỉ áp dụng cho **method hoặc field**. Đặt trên class hay constructor là sai target và có thể là **lỗi biên dịch**.
- `@Retention(SOURCE)`: annotation được giữ ở **mã nguồn**, không nhằm hiện diện trong bytecode để tra cứu reflection lúc chạy.
- `@Serial` **không thực thi việc serialize**, không biến class thành `Serializable` và không tự làm JVM nhận ra một method gõ sai.
- `@Serial` đánh dấu **ý định** rằng declaration là một trường hoặc method có vai trò đặc biệt trong Java Object Serialization.
- Khác với `@Override`, những hook như `private void readObject(...)` **không override method của superclass**; chúng được serialization runtime tra cứu theo quy tắc riêng.

Tài liệu JDK nói compiler **được khuyến khích** kiểm tra và cảnh báo (`“Compilers are encouraged”`) nếu annotation đặt trên khai báo không phù hợp. Vì vậy **đừng đồng nhất chú giải này với một bảo đảm compile-time bắt buộc trên mọi JVM/compiler**.

### 2.1. Phạm vi phù hợp

`@Serial` có ý nghĩa với **những class thật sự tham gia Java Object Serialization**, thường triển khai `java.io.Serializable`. Với `Externalizable`, enum và các class có giao thức serialization đặc biệt, một số hook thông thường **không có tác dụng**, dù syntax method trông có vẻ giống.

### 2.2. Khi nào cần đến bài này?

- Bạn vừa viết `readObject` để validate dữ liệu sau deserialize, nhưng breakpoint **không bao giờ dừng**.
- Bạn thấy `-Xlint:serial` báo một field `serialVersionUID` sai kiểu.
- Code có `@Serial private void readObject(ObjectInputStream, int)` nhưng callback không chạy.
- Dự án có `readResolve` nhưng object nhận được sau deserialize không được chuẩn hóa như mong muốn.
- CI muốn **fail build** khi công cụ phát hiện sai khai báo.
- Dự án thay đổi Java target, cần xác nhận annotation `@Serial` có trong target (**Java 14+**).

## 3. Bảy declaration đặc biệt: danh sách phải nhớ

Theo Javadoc `java.io.Serial` hiện hành, **năm method** và **hai field** có thể được đánh dấu `@Serial` trong đúng ngữ cảnh.

### 3.1. Năm method serialization-related

~~~java
@Serial
private void writeObject(ObjectOutputStream stream) throws IOException

@Serial
private void readObject(ObjectInputStream stream)
        throws IOException, ClassNotFoundException

@Serial
private void readObjectNoData() throws ObjectStreamException

@Serial
Object writeReplace() throws ObjectStreamException

@Serial
Object readResolve() throws ObjectStreamException
~~~

Đây là **danh sách chữ ký minh họa**, không phải một class đầy đủ. Những field, class và import được lược bỏ để dễ quan sát; hai method cuối có thể dùng **access modifier phù hợp khác**.

| Method | Tên chính xác | Tham số và return type | Phạm vi truy cập cần lưu ý |
| --- | --- | --- | --- |
| `writeObject` | Đúng một từ, không số nhiều | **`void`**, đúng **một `ObjectOutputStream`** | **`private`**, instance |
| `readObject` | `readObject`, không `readObjects` | **`void`**, đúng **một `ObjectInputStream`** | **`private`**, instance |
| `readObjectNoData` | Đúng cả hậu tố `NoData` | **`void`**, **không tham số** | **`private`**, instance |
| `writeReplace` | Đúng chữ `Replace` | **`Object`**, **không tham số** | Instance, access modifier theo quy tắc hook |
| `readResolve` | Đúng chữ `Resolve` | **`Object`**, **không tham số** | Instance, access modifier theo quy tắc hook |

**Các mục `throws` mô tả chữ ký chuẩn trong Javadoc.** Trong Java, `throws` không phải là một phần của **method descriptor** theo JVM; việc method có liệt kê tất cả checked exceptions trong chữ ký nguồn hay không **không tự tạo thêm tham số hoặc đổi return type**. Với code minh họa nên dùng chữ ký chính thức, thuận tiện cho compiler và người review.

### 3.2. Hai field serialization-related

~~~java
@Serial
private static final long serialVersionUID = 1L;

@Serial
private static final ObjectStreamField[] serialPersistentFields = {
    new ObjectStreamField("name", String.class)
};
~~~

Đây là **snippet khai báo trong một class thích hợp**. Cần import `java.io.ObjectStreamField` khi dùng field thứ hai.

| Field | Tên và kiểu bắt buộc | Vai trò |
| --- | --- | --- |
| `serialVersionUID` | **`private static final long`** | Định danh phiên bản serialization của class |
| `serialPersistentFields` | **`private static final ObjectStreamField[]`** | Khai báo danh sách trường được serialize theo cơ chế persistent fields |

**Không dùng `int` thay `long`** cho `serialVersionUID`. Không nhầm `serialVersionUid` (`Uid`) với `serialVersionUID` (**UID** viết hoa). Không tự thêm `serialPersistentFields` vào mọi class: field này dùng để **kiểm soát serialized fields**, đòi hỏi hiểu rõ schema và tương tác với các hook tương ứng; class đơn giản thường chỉ cần `serialVersionUID`.

### 3.3. “Đúng tên nhưng sai ngữ cảnh” vẫn có thể vô hiệu

Một method có tên/chữ ký phù hợp vẫn có thể **không có tác dụng** khi:
- Nằm trong class **không implements `Serializable`**.
- Là `writeObject`, `readObject` hoặc `readObjectNoData` ở class **`Externalizable`**.
- Là serialization method trong **enum**, vì enum có cơ chế serialization đặc biệt.
- Có modifier làm method không hợp lệ với vai trò, ví dụ `static` hoặc `public` đối với `readObject`.
- Được khai báo trong một superclass nhưng người viết lại tưởng có thể “override” một private hook trong subclass.

Compiler có thể cảnh báo tùy khai báo và phiên bản; **sự thiếu cảnh báo không chứng minh hook có tác dụng**.

## 4. Bước chẩn đoán đầu tiên: biên dịch với -Xlint:serial

Lệnh cơ bản:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial YourClass.java
~~~

**Giải thích:**
- `--release 17` kiểm tra mã và public API theo Java 17; `@Serial` có trong Java 17.
- `-Xlint:serial` bật nhóm cảnh báo serialization của `javac`.
- `-encoding UTF-8` giúp compiler đọc mã nguồn với encoding nhất quán, không phải một tùy chọn riêng của `@Serial`.

Trên các JDK hiện hành, nhóm `serial` có thể cảnh báo:
- Class `Serializable` **không có `serialVersionUID`**.
- Trường `serialVersionUID` sai kiểu, modifier hoặc khai báo không phù hợp.
- Một số method `@Serial` có tên nhận biết nhưng sai access, return type hoặc số tham số.
- Những hook/field không có tác dụng trong ngữ cảnh `Externalizable`.

**Không hiểu sai:** `-Xlint:serial` không phải một trình phân tích đảm bảo tìm được **mọi** method gõ sai tên. Trong kiểm chứng trên `javac 24.0.2`, `@Serial private void readObjects(...)` **không phát cảnh báo** dù method bị serialization runtime bỏ qua. Phần 9 có test thực tế.

### 4.1. Các loại thông báo của compiler

| Kết quả | Ý nghĩa | CI mặc định |
| --- | --- | --- |
| `error: ...` | Mã nguồn không hợp lệ hoặc vi phạm luật ngôn ngữ/target | Thất bại |
| `warning: [serial] ...` | Vấn đề mà bộ kiểm tra serialization nhận thấy | Có thể vẫn thành công |
| Không có warning | Không có vấn đề mà phiên bản/config compiler **đã phát hiện** | **Không phải bằng chứng tuyệt đối** callback đúng |
| `error: warnings found and -Werror specified` | Cảnh báo tồn tại và policy CI yêu cầu không warning | Thất bại |

### 4.2. Nâng cảnh báo thành lỗi build với -Werror

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial -Werror YourClass.java
~~~

`-Werror` yêu cầu compiler coi **các warning thực sự phát ra** như lỗi build. Nó **không tăng khả năng phát hiện**: nếu tên bị gõ sai nhưng compiler không cảnh báo, `-Werror` không tự phát hiện được lỗi đó.

Lệnh thường dùng trong CI:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial -Werror -d out src/YourClass.java
~~~

Với Maven/Gradle, cấu hình compiler options tương đương trong build thay vì chỉ chạy lệnh tay; bản thân cách tích hợp phụ thuộc phiên bản build plugin và JDK.

### 4.3. Nhóm -Xlint:serial còn báo thiếu serialVersionUID

Ví dụ:

~~~java
import java.io.Serializable;

final class MissingUid implements Serializable {
    private int value;
}
~~~

Biên dịch với `-Xlint:serial` có thể cho:

~~~text
warning: [serial] serializable class MissingUid has no definition of serialVersionUID
~~~

Đây là **cảnh báo**, không có nghĩa mã Java luôn bị từ chối. Khi không khai báo UID, serialization runtime có cách tính **UID mặc định**, nhưng thay đổi class/compiler có thể ảnh hưởng compatibility. Với class serializable có chủ đích, việc khai báo UID ổn định thường là thực hành phù hợp.

## 5. Ví dụ chuẩn: @Serial đúng hình thức, build sạch và serialize thành công

Tệp **`ValidSerializable.java`** đã được biên dịch/chạy thực tế:

~~~java
import java.io.*;

public final class ValidSerializable implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String code;

    public ValidSerializable(String code) {
        this.code = code;
    }

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
    private Object readResolve() throws ObjectStreamException {
        return this;
    }

    public String code() {
        return code;
    }

    public static void main(String[] args) throws Exception {
        byte[] encoded;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(new ValidSerializable("OK"));
            out.flush();
            encoded = bytes.toByteArray();
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(encoded))) {
            ValidSerializable decoded =
                    (ValidSerializable) in.readObject();
            System.out.println("Decoded: " + decoded.code());
        }
    }
}
~~~

### 5.1. Chạy thử

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial -Werror ValidSerializable.java
java ValidSerializable
~~~

**Stdout chính xác được kiểm chứng:**

~~~text
Decoded: OK
~~~

Lần kiểm chứng dùng `javac 24.0.2`, target `--release 17`; không có warning và exit code compiler bằng 0.

### 5.2. Vì sao code hợp lệ?

- Class triển khai `Serializable`.
- Field `serialVersionUID` đúng **`private static final long`**, ghi version `1L`.
- `writeObject` và `readObject` đúng **tên, private access, một tham số, `void`**.
- `writeObject` gọi `out.defaultWriteObject()` để lưu các field theo cơ chế mặc định.
- `readObject` gọi `in.defaultReadObject()` để đọc lại đúng các field.
- `readResolve` có no-arg return `Object` và trả `this`; trong demo không làm thay đổi kết quả logic.

**Phạm vi demo:** Đoạn code được thiết kế **chỉ để kiểm chứng khai báo và luồng object serialization trong môi trường test**, không khuyến nghị dùng `ObjectInputStream` trên dữ liệu tùy ý không đáng tin. Phần bảo mật serialization được nêu ở cuối bài.

## 6. Sai kiểu serialVersionUID: compiler phát hiện

Ví dụ sai:

~~~java
import java.io.Serial;
import java.io.Serializable;

final class WrongUid implements Serializable {
    @Serial
    private static final int serialVersionUID = 1; // SAI: phải là long.
}
~~~

Đây là **snippet độc lập có thể biên dịch nhưng sinh cảnh báo** với `-Xlint:serial` trong các JDK được kiểm chứng.

Dạng cảnh báo đã quan sát trong ví dụ test:

~~~text
warning: [serial] serialVersionUID must be of type long in class ...
~~~

**Cách sửa:**

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

Khác với lỗi viết sai chữ hoa/thường, trường hợp này **tên field được nhận biết** nhưng **kiểu không phù hợp**, nên compiler có thể đưa ra cảnh báo trực tiếp tại khai báo đó.

### 6.1. Nếu gõ nhầm tên UID?

~~~java
import java.io.*;

final class TypoUid implements Serializable {
    @Serial
    private static final long serialVersionUid = 1L; // Sai: Uid != UID.
}
~~~

Trong kiểm chứng với `javac -Xlint:serial`, compiler **không cảnh báo ngay trên field sai tên**, nhưng phát hiện class **không có định nghĩa `serialVersionUID` hợp lệ**:

~~~text
warning: [serial] serializable class TypoUid has no definition of serialVersionUID
~~~

**Điều phải học:** Nếu chỉ đọc cảnh báo “class lacks serialVersionUID” mà không xem tên field, bạn có thể sửa nhầm bằng cách thêm một field UID thứ hai. Hãy kiểm tra tên **`serialVersionUID`** chính xác chữ hoa/thường rồi sửa field hiện có.

## 7. Sai access modifier: public readObject không phải private hook

Ví dụ:

~~~java
@Serial
public void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
~~~

Đây là **snippet trong một class Serializable**, nhưng `readObject` đặc biệt cần **`private`** và có đúng một tham số `ObjectInputStream`.

Với `javac -Xlint:serial` trên môi trường kiểm chứng:

~~~text
warning: [serial] serialization-related method readObject not declared private
~~~

**Cách sửa:**

~~~java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
~~~

**Vì sao `@Override` không sửa được?** Đây không phải method override bình thường của `Serializable` (interface này là marker và không định nghĩa `readObject`). Việc đặt `@Override` lên private serialization hook thường gây lỗi vì **không override** method nào. `@Serial` mới là annotation thể hiện ý định đúng — nhưng chữ ký vẫn phải chuẩn.

## 8. Sai danh sách tham số, return type hoặc static

Ba ví dụ dưới đây tương ứng các dạng lỗi khác nhau:

~~~java
// 1) SAI: readObject thêm một tham số.
@Serial
private void readObject(ObjectInputStream in, int version)
        throws IOException {
}

// 2) SAI: writeObject trả Object, thay vì void.
@Serial
private Object writeObject(ObjectOutputStream out)
        throws IOException {
    return null;
}

// 3) SAI: readResolve là static.
@Serial
private static Object readResolve()
        throws ObjectStreamException {
    return null;
}
~~~

Đây là các **snippet lỗi có chủ đích**, không đặt cùng nhau như một class chạy chuẩn. Khi method mang tên đã nhận biết, `javac` có thể kiểm tra:
- **Số tham số**: `readObject` phải có **đúng một** `ObjectInputStream`.
- **Kiểu trả về**: `writeObject` phải trả `void`; `readResolve` trả reference theo hợp đồng.
- **Instance/static**: `readResolve` phải là method instance, không phải `static`.

Trong kiểm chứng trên `javac 24.0.2`, các chẩn đoán chứa những cụm sau:

~~~text
warning: [serial] to be effective serialization-related method readObject must have exactly one parameter rather than 2 parameters
warning: [serial] serialization-related method writeObject declared with a return type of Object rather than expected type void.
warning: [serial] serialization-related method readResolve must be a concrete instance method to be effective, neither abstract nor static
~~~

**Đây là trích đoạn nội dung cảnh báo**, không phải stdout cố định: đường dẫn file, số dòng, dấu xuống dòng và cách diễn đạt có thể đổi theo JDK/compiler.

**Sửa đúng:** Đối chiếu với bảng chữ ký ở mục 3, chọn đúng **tên, return type, số/kiểu tham số, access và modifier**. Thêm overload của `readObject` không làm runtime sử dụng overload đó.

### 8.1. Phân biệt overload bình thường với serialization hook

Java cho phép overload method:

~~~java
void readObject(ObjectInputStream in, int version) { }
~~~

Nếu một class có method như vậy, nó vẫn là method Java hợp lệ, nhưng **không phải `readObject` đặc biệt**. Serialization runtime sẽ tra cứu đúng chữ ký được đặc tả, không tự đoán “method này có tên gần giống hoặc tham số gần đúng”.

### 8.2. @Serial không tự thay đổi chữ ký

Thêm annotation:

~~~java
@Serial
private void readObject(ObjectInputStream in, int version) { }
~~~

**không tạo** thêm một method `readObject(ObjectInputStream)` đúng chuẩn. Annotation chỉ hỗ trợ **kiểm tra ở mức công cụ**, không sửa code hoặc tạo hook lúc runtime.

## 9. Kiểm chứng lỗi gõ sai tên: compiler có thể im lặng

Đây là tình huống quan trọng nhất của bài. Tệp **`HookNameTypoDemo.java`** sau có một method với **annotation `@Serial` nhưng sai tên**: `readObjects` thay vì `readObject`.

~~~java
import java.io.*;

public final class HookNameTypoDemo implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String label;
    private static boolean typoWasCalled = false;

    public HookNameTypoDemo(String label) {
        this.label = label;
    }

    // Sai tên: stream sẽ không gọi method này như readObject.
    @Serial
    private void readObjects(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        typoWasCalled = true;
        in.defaultReadObject();
    }

    public static void main(String[] args) throws Exception {
        byte[] encoded;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(new HookNameTypoDemo("DATA"));
            out.flush();
            encoded = bytes.toByteArray();
        }

        try (ObjectInputStream in =
                new ObjectInputStream(new ByteArrayInputStream(encoded))) {
            HookNameTypoDemo decoded = (HookNameTypoDemo) in.readObject();
            System.out.println("Restored label=" + decoded.label);
            System.out.println("Typo hook called=" + typoWasCalled);
        }
    }
}
~~~

### 9.1. Lệnh kiểm chứng

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial -Werror HookNameTypoDemo.java
java HookNameTypoDemo
~~~

**Kết quả đã quan sát trên `javac 24.0.2`:**
- `javac` **exit code = 0**, không có cảnh báo ở file này.
- `-Werror` không làm build thất bại vì **không có warning được phát ra**.
- Serialization runtime **không gọi `readObjects`**.

**Stdout chính xác:**

~~~text
Restored label=DATA
Typo hook called=false
~~~

Đây là minh chứng trực tiếp cho giới hạn của công cụ: **có `@Serial` và build xanh không đủ để chứng minh callback được nhận diện**. Object vẫn deserialize được, vì cơ chế **default serialization** có thể khôi phục field `label` mà không cần hook custom.

### 9.2. Vì sao điều này nguy hiểm?

Nếu method bị gõ sai vốn phải:
- Xác thực trường dữ liệu sau deserialize.
- Kiểm tra checksum/ràng buộc nghiệp vụ.
- Khôi phục field `transient`.
- Cấm một trạng thái không hợp lệ.

thì việc không được gọi có thể làm object **tưởng như hợp lệ nhưng thiếu bước xử lý cần thiết**.

**Cách sửa:** Đổi `readObjects` thành **`readObject`**, giữ chữ ký chuẩn:

~~~java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Validate hoặc khôi phục trạng thái cần thiết ở đây.
}
~~~

Sau sửa, viết test xác minh **bước xử lý thật được thực thi**, thay vì chỉ kiểm tra class deserialize được mà không ném lỗi.

### 9.3. Không khẳng định mọi bản javac đều im lặng như nhau

API Javadoc **khuyến khích** compiler kiểm tra `@Serial`, không buộc mọi bản compiler phát ra cùng một bộ cảnh báo. Kết quả im lặng trên **`javac 24.0.2`** là **một kiểm chứng cụ thể**, không phải hợp đồng rằng mọi JDK khác đều không cảnh báo. Dù vậy, một pipeline đáng tin cậy vẫn phải có **runtime tests** cho hooks quan trọng.

## 10. Dùng javap -p -s để xem chữ ký thật của method

`javap` là công cụ JDK giúp đọc thông tin class đã biên dịch. Khi nghi ngờ sai tên/chữ ký, chạy:

~~~bash
javap -p -s HookNameTypoDemo
~~~

Tùy chọn:
- `-p`: hiển thị **cả private members**.
- `-s`: hiển thị **JVM descriptors** bên cạnh các declaration.

Trích đoạn đã kiểm chứng:

~~~text
private static final long serialVersionUID;
  descriptor: J

private void readObjects(java.io.ObjectInputStream) throws java.io.IOException, java.lang.ClassNotFoundException;
  descriptor: (Ljava/io/ObjectInputStream;)V
~~~

Giải thích descriptor:
- `(Ljava/io/ObjectInputStream;)V` = một tham số reference `ObjectInputStream`, kết quả `void`.
- `J` = kiểu primitive `long`.
- Nếu có thêm tham số `int`, descriptor sẽ có thêm ký hiệu `I`.
- **JVM descriptor không chứa tên method**; nó nằm ở dòng declaration. Vì vậy phải so **cả tên** và **descriptor**.

Dù descriptor của `readObjects` nhìn giống descriptor đúng cho `readObject`, runtime **vẫn bỏ qua** vì **tên method sai**. Đây là lý do không chỉ đếm số tham số hoặc nhìn kiểu return.

### 10.1. So sánh với chữ ký đúng

Tên đúng:

~~~text
private void readObject(java.io.ObjectInputStream);
  descriptor: (Ljava/io/ObjectInputStream;)V
~~~

Đây là **ví dụ dạng kết quả mong đợi sau sửa**, không phải output thực tế của file bị sai tên. Mục tiêu của `javap` là kiểm tra bytecode sau build, nhất là khi code được generate, shade, weave, hoặc IDE hiển thị source khác artifact được deploy.

### 10.2. javap không kiểm chứng hành vi nghiệp vụ

`javap` có thể cho biết field/method tồn tại và descriptor, nhưng không chứng minh:
- Serialization runtime thực sự gọi hook trong một tình huống cụ thể.
- Hook có đọc/ghi các field đúng logic.
- Stream input không chứa dữ liệu không đáng tin.
- Class tương thích với phiên bản stream của bản phát hành trước.

Để xác nhận những điều đó, vẫn phải có integration tests.

## 11. Dùng serialver kiểm tra serialVersionUID

JDK có công cụ `serialver` để in `serialVersionUID` của class serializable:

~~~bash
serialver HookNameTypoDemo
~~~

Nếu class đã biên dịch ở thư mục khác, thêm `-classpath` tương ứng.

Đầu ra đã kiểm chứng:

~~~text
HookNameTypoDemo:    private static final long serialVersionUID = 1L;
~~~

### 11.1. serialver giúp gì?

- Kiểm tra **giá trị UID** runtime serialization đang dùng cho class.
- Giúp chẩn đoán mismatch `InvalidClassException` khi đọc stream từ phiên bản khác.
- Hỗ trợ xác minh khi field UID bị gõ sai tên hoặc kiểu, khiến runtime có thể tính UID mặc định thay vì dùng giá trị dự định.

### 11.2. serialver không giúp gì?

- Nó **không** xác minh method `readObject` được runtime gọi.
- Không xác nhận ``@Serial` đã được compiler dùng đúng mục đích.
- Không tự kiểm tra security hoặc tương thích schema của mọi phiên bản stream.
- Không thay thế `javap -p -s` khi cần xem method names/signatures.

**Quan trọng:** `serialVersionUID` là **định danh compatibility** của Java Object Serialization, **không phải khóa mã hóa, checksum hay cơ chế chống giả mạo dữ liệu**.

## 12. Compiler phát hiện lỗi @Serial trong Externalizable

`Externalizable` extends `Serializable` nhưng dùng **`writeExternal(ObjectOutput)`** và **`readExternal(ObjectInput)`** cùng quy tắc riêng. Vì thế một số hook của `Serializable` thông thường **không có tác dụng** trong class `Externalizable`.

Tệp test **`ExternalizableMistakes.java`**:

~~~java
import java.io.*;

final class ExternalizableMistakes implements Externalizable {
    @Serial
    private static final long serialVersionUID = 1L;

    @Serial
    private static final ObjectStreamField[] serialPersistentFields = {};

    @Serial
    private void writeObject(ObjectOutputStream out) throws IOException {
    }

    public ExternalizableMistakes() {
    }

    public void writeExternal(ObjectOutput out) throws IOException {
    }

    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
    }
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial ExternalizableMistakes.java
~~~

Các cảnh báo đã kiểm chứng trên JDK 24:

~~~text
warning: [serial] serialPersistentFields is not effective in an Externalizable class
warning: [serial] serialization-related method writeObject is not effective in an Externalizable class
~~~

**Sửa đúng:**
- Để custom serialization cho `Externalizable`, thực hiện logic trong **`writeExternal`** và **`readExternal`**.
- Không dùng `@Serial` cho những method này chỉ vì chúng liên quan serialization: **`@Serial` chỉ áp dụng cho các declaration cụ thể liệt kê trong Javadoc**, không phải mọi method có tên chứa từ “External”.
- Không đánh dấu `serialPersistentFields` hoặc các `readObject`/`writeObject` hooks không có tác dụng ở `Externalizable`.
- `serialVersionUID` vẫn có thể phù hợp ở class `Externalizable`.

**Lưu ý thiết kế:** `Externalizable` có yêu cầu đối với cách tái tạo object, trong đó constructor `public` không tham số là quan trọng. Không dùng class test trên làm mẫu production nếu chưa triển khai trường dữ liệu/validation thực sự.

## 13. Enum, record và class không Serializable

### 13.1. Enum

Enum có cơ chế serialization được định nghĩa riêng. Javadoc `@Serial` nêu:
- Enum có `serialVersionUID` được xác định là `0L` theo quy tắc serialization; field UID tự khai báo sẽ bị bỏ qua.
- Năm serialization-related methods nêu ở mục 3 **không có tác dụng** trong enum.

Vì vậy không sao chép một cách máy móc những hooks của class `Serializable` thường vào enum, dù compiler chấp nhận một số declaration ở mức Java syntax.

### 13.2. Record

Record có quy tắc Java Object Serialization đặc biệt khi triển khai `Serializable`. Không giả định các hooks của class `Serializable` thông thường đều hoạt động giống hệt cho record. Nếu cần serialize record, dựa trên **serialization specification hiện hành**, kiểm thử round-trip và constructor/invariant liên quan; đừng gắn `@Serial` lên mọi method có tên quen thuộc rồi mặc định sẽ được gọi.

Phạm vi bài này là **chẩn đoán khai báo đặc biệt theo `@Serial`**; không biến nó thành hướng dẫn mới để xây giao thức serialization cho record.

### 13.3. Class không implements Serializable

Ví dụ:

~~~java
import java.io.Serial;

final class NotSerializable {
    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Theo ý nghĩa annotation, một field như vậy **không tạo ra serialization hook hữu dụng**. Trong thử nghiệm `javac 24.0.2 -Xlint:serial`, class cụ thể trên **không phát cảnh báo**. Đây là một trường hợp khác khẳng định **compiler diagnostics không bao trùm mọi lỗi ngữ cảnh**.

Nếu một class **không cần Java serialization**, không nên gắn các special fields/methods chỉ để làm compiler im lặng. Nếu nó thật sự cần serialize, hãy xác định và kiểm soát rõ việc implement `Serializable`, security và compatibility.

## 14. @Serial sai Target: lỗi biên dịch thay vì warning

`@Serial` chỉ áp dụng cho field/method. Ví dụ đặt trên class:

~~~java
import java.io.Serial;

@Serial
public final class InvalidSerialTarget {
}
~~~

Biên dịch:

~~~bash
javac -encoding UTF-8 --release 17 InvalidSerialTarget.java
~~~

Dạng lỗi đã kiểm chứng:

~~~text
error: annotation interface not applicable to this kind of declaration
~~~

Đây là **lỗi quy tắc Java annotation target**, thường xảy ra **ngay cả khi không bật `-Xlint:serial`**. Nó khác với **warning về semantic** khi đặt annotation lên một method có đúng target nhưng sai signature/usage.

### 14.1. Vì sao không nên gọi mọi lỗi @Serial là compiler error?

- **Sai target** như áp dụng lên class: Java compiler phải từ chối cú pháp/loại declaration không phù hợp.
- **Sai method signature** nhưng Java syntax hợp lệ: thông thường vẫn có thể biên dịch; `javac -Xlint:serial` có thể cảnh báo.
- **Sai tên hook hoàn toàn**: Java vẫn thấy đó là một method bình thường; không bảo đảm một warning sẽ được tạo.

Sự khác biệt này rất quan trọng khi thiết lập mức nghiêm ngặt cho build.

## 15. Ghép công cụ thành một quy trình chẩn đoán

### Bước 1 — Nhận diện đúng class và serialization mechanism

Trước khi thêm `@Serial`:
- Class implement `Serializable` hay `Externalizable`?
- Nó là class thường, enum hay record?
- Có cơ chế tạo/khôi phục object khác (framework mapping, JSON, database) mà **không dùng Java Object Serialization** không?

`@Serial` **không giúp kiểm tra** các callback riêng của Jackson, JPA, Gson, protobuf hay những framework khác.

### Bước 2 — Liệt kê declaration mong muốn

Đối chiếu tên/chữ ký với Javadoc `java.io.Serial`:
- `serialVersionUID`: `private static final long`.
- `serialPersistentFields`: `private static final ObjectStreamField[]`.
- `writeObject`/`readObject`/`readObjectNoData`: private, đúng tham số/return.
- `writeReplace`/`readResolve`: instance, no-arg, đúng return type.

Không chỉ nhìn từ khóa `@Serial` rồi giả định phương thức đã được runtime nhận.

### Bước 3 — Chạy javac lint

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial MySerializable.java
~~~

Ghi nhận **cảnh báo thực tế**, vị trí, nội dung, cùng Java compiler version `javac -version`. Không dựa vào một câu cảnh báo copy từ blog cũ để kết luận phiên bản compiler hiện hành chắc chắn sẽ báo cùng nội dung.

### Bước 4 — Nâng mức nghiêm ngặt cho CI

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial -Werror MySerializable.java
~~~

Khi đã kiểm soát được codebase và các warnings, `-Werror` giúp ngăn một số lỗi khai báo quay lại. Nếu project có warnings từ dependency/source sinh ra, xử lý đúng nơi hoặc scope compiler target; **không tắt toàn bộ warning** chỉ để CI xanh.

### Bước 5 — Kiểm tra bytecode bằng javap

~~~bash
javap -p -s MySerializable
~~~

Tìm **tên, access modifier, số tham số, JVM descriptor** đúng của hook. Với nhiều bản build, hãy chạy `javap` trên **artifact thực tế sẽ deploy** chứ không chỉ bản class cũ trong IDE.

### Bước 6 — Kiểm tra UID bằng serialver

~~~bash
serialver MySerializable
~~~

Đọc UID và xác nhận class loader/classpath đang dùng đúng bản class. Nếu UID được tính mặc định, xem lại khai báo `serialVersionUID` và quy tắc tương thích.

### Bước 7 — Test vòng serialize/deserialize thật

Dùng dữ liệu nhỏ trong **môi trường kiểm thử tin cậy**:
1. Tạo object có field và invariants quan trọng.
2. Serialize ra byte array/test file.
3. Deserialize lại.
4. Xác nhận callback dự kiến đã chạy bằng một observable effect an toàn hoặc test assertion.
5. Kiểm tra không mất field, dữ liệu sai không bị chấp nhận và kết quả phù hợp.
6. Nếu cần compatibility, test stream đã tạo bởi **phiên bản phát hành trước**.
7. Test các trường hợp thiếu data, malformed field/invariant theo hợp đồng; **không nạp payload không đáng tin** không có serialization filter.

### Bước 8 — Sửa đúng nguồn gây lỗi, chạy lại bộ test

- Tên sai → sửa **đúng tên**.
- Kiểu/số tham số sai → sửa **chữ ký**, không chỉ thêm annotation.
- Access sai → sửa access theo specification.
- Ngữ cảnh vô hiệu → không dùng hook ở class không phù hợp.
- Lỗi UID → sửa field và đánh giá compatibility của dữ liệu cũ.
- Cảnh báo biến mất nhưng hook vẫn không chạy → kiểm tra runtime test, không dừng ở compile success.

## 16. Chọn công cụ theo triệu chứng

| Triệu chứng | Công cụ tốt nhất để bắt đầu | Điều cần xác nhận |
| --- | --- | --- |
| `serialVersionUID` sai kiểu | `javac -Xlint:serial` | Field đúng `long`, modifier và tên |
| Missing UID warning | `javac -Xlint:serial`, `serialver` | Field thiếu hay bị viết sai `UID` |
| `readObject` đang `public` | `javac -Xlint:serial` | Access phải `private` |
| `readObject` có hai tham số | `javac -Xlint:serial`, `javap -p -s` | Chỉ một `ObjectInputStream` |
| `writeObject` trả `Object` | `javac -Xlint:serial` | Phải `void` |
| `readResolve` là `static` | `javac -Xlint:serial` | Phải instance method |
| `readObjects` sai tên nhưng compile sạch | `javap -p -s` + runtime test | Runtime không thấy hook đúng tên |
| `@Serial` trên class | `javac` | Sai annotation target, compile error |
| `writeObject` trong `Externalizable` | `javac -Xlint:serial`, tài liệu serialization | Hook đó không hiệu lực |
| Serialization khôi phục được field nhưng bỏ validation | Integration test gọi hook/invariant | Default serialization có thể che mất hook gõ sai |
| `InvalidClassException` khi đọc stream cũ | `serialver`, UID/schema diff | Compatibility giữa class và stream |
| IDE không cảnh báo nhưng CLI cảnh báo | So JDK, compiler flags, analysis settings | Cùng target/release và warning categories |

## 17. Những hiểu nhầm phổ biến

### 17.1. “@Serial bắt được 100% lỗi gõ sai”

**Không có bảo đảm như vậy.** Bài lab `HookNameTypoDemo` đã biên dịch sạch nhưng `readObjects` không được gọi. `@Serial` hữu ích nhưng phải đi kèm test hành vi.

### 17.2. “@Serial hoạt động như @Override”

**Không đúng.** `@Override` xác nhận một quan hệ override từ superclass/interface; `@Serial` đánh dấu một **serialization-related declaration** theo quy ước nhận diện đặc biệt.

### 17.3. “Không có -Xlint:serial tức compiler sẽ tự kiểm tra”

**Không nên kỳ vọng.** Với nhiều lỗi signature, `javac` chỉ báo khi bật warning category thích hợp. Trong lần thử nghiệm, file `BrokenDeclarations.java` biên dịch với **exit code 0** khi bỏ `-Xlint:serial`.

### 17.4. “-Werror có thể tìm lỗi mà -Xlint không tìm thấy”

**Không.** `-Werror` chỉ chuyển **warning đã phát** thành lỗi build; nó không phân tích bổ sung method name, và không thay thế integration test.

### 17.5. “Đã có serialVersionUID là mọi version tương thích”

**Sai.** UID là một phần kiểm tra tương thích, nhưng thay đổi cấu trúc field, graph, class hierarchy hoặc custom serialization protocol có thể gây mismatch hoặc sai dữ liệu ngay cả khi UID không đổi.

### 17.6. “Serialization tự gọi method tên gần đúng”

**Sai.** Không có fuzzy matching. `readObject` và `readObjects` là **hai tên method khác nhau**; overload `readObject(ObjectInputStream,int)` cũng không được dùng thay cho hook một tham số.

### 17.7. “Có warning thì chương trình chắc chắn không chạy được”

**Không nhất thiết.** `javac -Xlint:serial` thường vẫn tạo class và có exit 0. `-Werror` là lựa chọn của build policy để không cho warning đi qua.

### 17.8. “@Serial là annotation có thể đọc qua reflection ở runtime”

**Không.** `@Serial` có `RetentionPolicy.SOURCE`. Runtime serialization phát hiện đúng member theo quy tắc riêng, **không dựa vào việc tìm annotation trong class file**.

### 17.9. “Serializable nghĩa là an toàn khi đọc mọi byte stream”

**Không.** Native Java Object Serialization có rủi ro khi deserialize dữ liệu không đáng tin. Với dữ liệu từ nguồn ngoài, cần bảo vệ bằng allowlist/filter, giới hạn kích thước/depth, policy bảo mật và ưu tiên format/giao thức phù hợp khi thiết kế hệ thống mới.

### 17.10. “Sửa lint warning là đủ, không cần test round-trip”

**Không.** Cảnh báo chỉ phát hiện **một số cấu trúc sai**; logic custom hook, tương thích stream và invariant phải được test.

## 18. Bài tập thực hành kèm đáp án

### Bài 1 — Tên callback sai

~~~java
@Serial
private void writeObjects(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
}
~~~

**Hỏi:** Method này có được gọi như `writeObject` đặc biệt không?

**Đáp án:** **Không.** Tên phải là **`writeObject`** (không có `s`). Runtime không tự sửa tên. Đổi tên và thêm test xác nhận việc ghi các field theo logic dự kiến.

### Bài 2 — Chữ ký readObject

~~~java
@Serial
private void readObject(ObjectInputStream in, int version)
        throws IOException, ClassNotFoundException {
}
~~~

**Hỏi:** `javac -Xlint:serial` có thể nhận ra lỗi gì?

**Đáp án:** `readObject` đặc biệt phải có **đúng một tham số `ObjectInputStream`**. Trường hợp hai tham số được kiểm chứng sinh warning `must have exactly one parameter rather than 2 parameters`.

### Bài 3 — Sai access

~~~java
@Serial
public void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
}
~~~

**Đáp án:** Sai vì special `readObject` phải **private**. Compiler với `-Xlint:serial` có thể báo `not declared private`.

### Bài 4 — Sai UID

~~~java
@Serial
private static final int serialVersionUID = 1;
~~~

**Đáp án:** Đúng tên nhưng sai kiểu; phải dùng `private static final long serialVersionUID = 1L;`. Cảnh báo `serialVersionUID must be of type long` đã được kiểm chứng.

### Bài 5 — Gõ nhầm serialVersionUID

~~~java
@Serial
private static final long serialVersionUid = 1L;
~~~

**Đáp án:** `Uid` khác `UID`; field không đúng tên. `-Xlint:serial` có thể phát cảnh báo class thiếu UID, còn `serialver` giúp quan sát UID thực tế của class được build.

### Bài 6 — -Werror và lỗi im lặng

File có `@Serial private void readObjects(...)` và `serialVersionUID` đúng; `javac -Xlint:serial -Werror` không phát warning trên môi trường thử nghiệm.

**Hỏi:** CI xanh có đủ khẳng định callback đúng không?

**Đáp án:** **Không.** Chạy `javap -p -s` để kiểm tra tên và test serialize/deserialize với assertion xác minh logic callback đã chạy.

### Bài 7 — Thử sai annotation target

~~~java
@Serial
class Example {
}
~~~

**Đáp án:** Annotation `@Serial` có target `METHOD` và `FIELD`, **không áp dụng cho class**, nên đây là lỗi biên dịch thay vì chỉ một warning serialization.

### Bài 8 — Externalizable

Class implements `Externalizable` có:

~~~java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
}
~~~

**Đáp án:** `writeObject` không hiệu lực trong `Externalizable`; thực hiện logic trong `public void writeExternal(ObjectOutput out)`. `@Serial` không áp dụng cho mọi callback theo sở thích đặt tên.

### Bài 9 — Nhận diện compiler output

~~~text
warning: [serial] serialization-related method readResolve must be a concrete instance method to be effective, neither abstract nor static
~~~

**Đáp án:** Kiểm tra xem `readResolve` có bị khai báo `static` hoặc `abstract` không. Special `readResolve` phải là instance method thích hợp với serialization contract.

### Bài 10 — Chọn đúng bộ công cụ

Bạn nghi file có hook gõ sai tên, nhưng IDE không có warning.

**Đáp án:** Chạy `javac -Xlint:serial`, sau đó `javap -p -s` để xem tên/descriptor của compiled class; dùng integration test xác nhận hook thực sự chạy. Nếu UID là vấn đề, thêm `serialver`. Không dựa vào một công cụ duy nhất.

## 19. Cách đưa kiểm tra vào dự án Java hiện đại

### 19.1. Tích hợp vào build

Nên đặt một **compile step** với cảnh báo serialization, ít nhất cho các class có `Serializable`:

~~~bash
javac -encoding UTF-8 --release 17 -Xlint:serial -Werror -d out src/ValidSerializable.java
~~~

Đây là **lệnh minh họa**; cấu trúc source path thực tế phụ thuộc dự án. Nếu dự án dùng Maven/Gradle, cấu hình compiler arguments trong build thay vì viết lại toàn bộ lệnh thủ công.

### 19.2. Giữ test serialize/deserialize trong CI

Các trường hợp đáng test:
- Round-trip dữ liệu có field bắt buộc.
- Callback validation thực sự được gọi.
- Input dữ liệu thiếu field hoặc vi phạm invariant bị xử lý đúng.
- Tương thích giữa các bản stream nếu sản phẩm cần.
- Cấu hình `ObjectInputFilter` khi đọc byte stream từ nguồn không tin cậy.
- Việc đổi tên field/hook làm test thất bại có chủ đích.

**Không tạo byte stream nguy hiểm/không đáng tin để chạy trên production**. Sử dụng dữ liệu test an toàn và giới hạn đồ thị object/độ sâu/tài nguyên.

### 19.3. Phân biệt vai trò của từng công cụ

| Công cụ | Kiểm tra được | Không đảm bảo |
| --- | --- | --- |
| `@Serial` | Ghi nhận ý định serialization declaration | Runtime hook tự động đúng |
| `javac -Xlint:serial` | Một nhóm lỗi cấu trúc/UID/usage do compiler nhận diện | Tất cả typo hoặc hiệu lực runtime |
| `-Werror` | Build thất bại khi đã có warning | Tạo ra warning mới |
| `javap -p -s` | Tên field/method, access, bytecode descriptors | Callback thực sự được gọi và đúng logic |
| `serialver` | UID hiệu lực của class theo runtime serialization | Hook signature và hành vi |
| Runtime tests | Hành vi thực tế theo bộ test và JVM | Mọi input, security hoặc compatibility tự động |
| Static analysis/IDE inspections | Những quy tắc riêng của công cụ được cấu hình | Phạm vi chuẩn hóa và độ bao phủ giống nhau |

## 20. Checklist QA trước khi phát hành

- [ ] Class thực sự tham gia Java Object Serialization và có nhu cầu đó.
- [ ] Không nhầm `Serializable`, `Externalizable`, enum hay record.
- [ ] `serialVersionUID` viết **đúng tên, modifier, kiểu `long`**.
- [ ] `serialPersistentFields` chỉ dùng khi thật sự cần tùy biến serialized fields.
- [ ] Tên hook đúng **100% ký tự**: `writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, `readResolve`.
- [ ] Mọi method có đúng **return type, số/kiểu tham số, static/instance, access**.
- [ ] `@Serial` chỉ đặt trên những **field/method** phù hợp, không đặt lên class.
- [ ] Đã chạy `javac -Xlint:serial`; CI dùng `-Werror` nếu phù hợp.
- [ ] Đã chạy `javap -p -s` cho các hook nghi vấn trong artifact cuối.
- [ ] Đã kiểm tra UID bằng `serialver` khi gặp warning/compatibility issue.
- [ ] Test round-trip xác nhận **hook quan trọng thực sự được gọi**.
- [ ] Không coi **compile sạch** là bằng chứng không có lỗi tên method.
- [ ] Không dùng `@Override` sai ý nghĩa cho private serialization hooks.
- [ ] Không deserialize dữ liệu từ nguồn không tin cậy mà thiếu biện pháp bảo vệ.
- [ ] Không dùng Java Object Serialization làm giao thức mới chỉ vì có `@Serial`; lựa chọn phụ thuộc yêu cầu tương thích, bảo mật và thiết kế hệ thống.

## 21. Ghi nhớ

1. **`@Serial` từ Java 14** là annotation nguồn giúp công cụ kiểm tra các field/method đặc biệt của Java Object Serialization, **không tự sửa method sai tên**.
2. Các hook dựa trên **đúng tên và chữ ký**, không phải override thông thường. `@Override` không thay thế `@Serial`.
3. `javac -Xlint:serial` phát hiện nhiều lỗi như **UID sai kiểu, readObject không private, sai số tham số, return type sai hoặc hook vô hiệu trong Externalizable**.
4. `-Werror` chỉ nâng **warnings đã phát** thành build failure; không bảo đảm bắt mọi typo.
5. **Một tên sai như `readObjects` có thể không gây warning**, nhưng method **không được serialization runtime gọi**. Điều này đã được kiểm chứng trên JDK 24 bằng round-trip test.
6. **`javap -p -s`** giúp xem đúng tên/access/descriptor trong bytecode; **`serialver`** giúp kiểm tra `serialVersionUID`.
7. Cần **runtime tests** kiểm tra callback, dữ liệu và invariants để bổ sung cho chẩn đoán compiler.
8. Annotation `@Serial` có **`Retention(SOURCE)`**, không phải cơ chế runtime. Tính đúng và bảo mật vẫn là trách nhiệm của chương trình.

**Tài liệu chính thức, còn áp dụng:**
- [Oracle Java SE 25 — java.io.Serial](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serial.html): annotation targets, chữ ký đúng, ngữ cảnh Serial/Externalizable/enum và điều kiện compiler được khuyến nghị cảnh báo.
- [Oracle Java SE 17 — java.io.Serial](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html): tương thích với các ví dụ `--release 17`.
- [Oracle Java SE 14 — java.io.Serial](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/io/Serial.html): xác nhận tính năng có từ Java 14.
- [Oracle JDK 25 — javac command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-Xlint:serial`, `-Xlint` và `-Werror`.
- [Oracle JDK 21 — javap command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html): kiểm tra private members và descriptors.
- [Oracle JDK 21 — serialver command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/serialver.html): kiểm tra serialVersionUID.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html): cách serialization nhận diện fields/hooks và compatibility.
- [Oracle JDK 21 — Serialization Filtering](https://docs.oracle.com/en/java/javase/21/core/serialization-filtering1.html): giới hạn deserialization của dữ liệu không đáng tin.
