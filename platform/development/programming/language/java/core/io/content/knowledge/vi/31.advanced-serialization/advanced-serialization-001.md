# Java Serialization nâng cao: writeObject, readObject, defaultWriteObject và defaultReadObject

Java Object Serialization chuyển một **đồ thị đối tượng** thành byte stream rồi xây dựng lại đối tượng khi đọc. Với các lớp `Serializable`, JVM thường tự lưu những instance fields đủ điều kiện. Tuy nhiên, có lúc ta muốn **bổ sung dữ liệu**, **khôi phục trạng thái `transient`**, **kiểm tra bất biến nghiệp vụ** hoặc **chủ động quản lý khả năng tương thích định dạng**. Khi ấy, Java cung cấp cơ chế tùy biến đặc biệt qua `private writeObject(ObjectOutputStream)` và `private readObject(ObjectInputStream)`, thường phối hợp với `defaultWriteObject()` và `defaultReadObject()`.

Bốn tên này rất dễ nhầm, vì **hai cái là API gọi từ bên ngoài để ghi/đọc một object**, còn hai cái có tên `default...` là **API chỉ dùng bên trong callback** của quá trình serialization. Bài học tập trung vào thứ tự thao tác, ý nghĩa dữ liệu mặc định và dữ liệu bổ sung, vòng đời đối tượng, ví dụ Java 17+ chạy được, xử lý lỗi và các giới hạn bảo mật.

> **Cảnh báo bảo mật:** Java native serialization không phù hợp cho dữ liệu không đáng tin từ Internet hoặc người dùng bất kỳ. `ObjectInputStream.readObject()` có thể kích hoạt mã của các class được giải tuần tự hóa trước khi lời gọi trả về. Nên ưu tiên định dạng có schema được kiểm soát (JSON, Protocol Buffers, CBOR...) và áp dụng allowlist/serialization filter nếu buộc phải nhận dữ liệu Java serialization.

## 1. Phân biệt hai cấp độ API có cùng tên

| Vị trí | API | Ai gọi? | Vai trò |
| --- | --- | --- | --- |
| Ngoài object | `ObjectOutputStream.writeObject(Object obj)` | Code ứng dụng | Bắt đầu ghi một đối tượng và đồ thị tham chiếu liên quan. |
| Trong class `Serializable` | `private void writeObject(ObjectOutputStream out) throws IOException` | Cơ chế serialization tự gọi nếu chữ ký hợp lệ | Tùy biến dữ liệu được ghi cho **class đó**. |
| Trong callback `writeObject` | `out.defaultWriteObject()` | Code callback | Ghi các field thuộc trạng thái serializable **mặc định** của class hiện tại. |
| Ngoài object | `ObjectInputStream.readObject()` | Code ứng dụng | Đọc object tiếp theo từ stream; trả về `Object`. |
| Trong class `Serializable` | `private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException` | Cơ chế deserialization tự gọi nếu hợp lệ | Tùy biến quá trình khôi phục và validate. |
| Trong callback `readObject` | `in.defaultReadObject()` | Code callback | Khôi phục trạng thái field mặc định đã ghi tương ứng. |

**Không được hiểu rằng `out.writeObject(this)` trong callback là tương đương `out.defaultWriteObject()`.** Ghi lại chính `this` qua object handle không có tác dụng ghi mặc định các field như bạn mong muốn; có thể tạo dữ liệu không đúng. Dùng `defaultWriteObject()` để ghi field data của class theo hợp đồng serialization.

Tương tự, `in.readObject()` trong callback không có nghĩa khôi phục field mặc định: nó đọc **một đối tượng kế tiếp** của phần dữ liệu trong stream. Để khôi phục field data của class hiện tại, dùng `in.defaultReadObject()`.

## 2. Serializable mặc định lưu những gì?

Một class triển khai `java.io.Serializable` có thể được tuần tự hóa bằng `ObjectOutputStream`. Mặc định, các field sau được xem xét:

- Các **instance fields** không mang modifier `transient` và không phải `static`.
- Giá trị primitive được ghi theo protocol serialization; tham chiếu tới object khác có thể kéo theo việc tuần tự hóa object tham chiếu.
- Object graph giữ được nhiều quan hệ định danh/tham chiếu theo cơ chế handle của stream; không phải một phép copy từng field độc lập bằng text.
- Field `transient` và `static` không được tự động lưu bởi cơ chế default.
- Nếu một instance field tham chiếu tới class không serializable và không được xử lý phù hợp, việc ghi object graph có thể ném `NotSerializableException`.

Ví dụ:

```java
class Profile implements Serializable {
    private static final long serialVersionUID = 1L;
    String name;                  // Mặc định được lưu.
    int age;                      // Mặc định được lưu.
    transient String cache;       // Mặc định bị bỏ qua.
    static String applicationId;  // Thuộc class, không phải object state.
}
```

Đây là **snippet**, cần import `java.io.Serializable`. Sau `readObject()` ở cấp ứng dụng, `name` và `age` thường được phục hồi từ dữ liệu field; `cache` mặc định là `null`, trừ khi có custom code khôi phục; `applicationId` do trạng thái hiện tại của class quyết định, không lấy từ stream của instance.

Dùng `transient` không phải bảo đảm tuyệt đối rằng giá trị không thể lọt ra ngoài. Nếu tự viết giá trị ấy qua `out.writeUTF` hoặc qua một field serializable khác, nó **vẫn xuất hiện trong stream**. Đừng serialize mật khẩu, bearer token, session secret hoặc thông tin nhạy cảm chỉ vì muốn khôi phục “đúng trạng thái”.

## 3. Chữ ký callback chính xác — không phải override bình thường

Cơ chế Java serialization nhận diện callback có dạng chuẩn:

```java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    // Ghi thêm dữ liệu tùy chọn của class.
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Đọc dữ liệu tùy chọn và xác minh trạng thái.
}
```

Đây là **snippet nằm trong một class triển khai `Serializable`**, với imports `java.io.Serial`, `java.io.IOException`, `java.io.ClassNotFoundException`, `ObjectOutputStream` và `ObjectInputStream`.

Lưu ý:

1. `writeObject` phải là **private instance method**, trả `void` và nhận đúng một tham số `ObjectOutputStream`; `readObject` tương tự với `ObjectInputStream` và khai báo checked exceptions phù hợp. Đây là các **hook đặc biệt** mà serialization runtime tìm kiếm, không phải phương thức `Serializable` yêu cầu override.
2. Một method `public writeObject(...)` hoặc `static writeObject(...)` **không phải callback tùy biến tương đương**. Không đánh dấu `@Override` cho chúng.
3. `@Serial` (Java 14+) giúp compiler kiểm tra ý định dùng phần tử phục vụ serialization; từ Java 17 có thể dùng ổn định. Không bắt buộc để cơ chế hoạt động, nhưng giúp phát hiện lỗi khai báo.
4. Callback được áp dụng cho class cụ thể trong hierarchy serializable; **private method không được kế thừa như một override thông thường**.
5. Trong callback, `defaultWriteObject/defaultReadObject` chỉ hoạt động khi đang ở **ngữ cảnh active serialization/deserialization thích hợp**. Gọi ở bên ngoài ngữ cảnh đó có thể gây `NotActiveException`.

Đặt `readObject` sai chữ ký khiến JVM không tự chạy code validate/khôi phục mà bạn dự định. Đó là lỗi nguy hiểm, vì chương trình có thể vẫn đọc thành công nhưng tạo đối tượng sai bất biến.

## 4. Thứ tự chuẩn khi ghi rồi đọc

Khi cần giữ field mặc định **và** thêm dữ liệu tùy chọn:

```text
Ứng dụng                     Lớp Serializable
─────────                    ──────────────────────────
out.writeObject(order)
                              private writeObject(out)
                               ├─ defaultWriteObject()
                               │    ghi các serializable fields mặc định
                               ├─ writeInt(version)
                               ├─ writeBoolean(hasNote)
                               └─ writeUTF(note) nếu có
                         → bytes trong ObjectOutputStream

in.readObject()
                              private readObject(in)
                               ├─ defaultReadObject()
                               │    phục hồi default field data
                               ├─ readInt() phiên bản dữ liệu tùy chọn
                               ├─ readBoolean()
                               ├─ readUTF() nếu có
                               ├─ validate các bất biến
                               └─ dựng lại transient/derived state
                         → object đã khôi phục
```

Hai đầu phải **đối xứng về thứ tự và loại dữ liệu**:

- Ghi `int` trước thì đọc `int` trước.
- Ghi `boolean` rồi mới có điều kiện ghi `UTF` thì bên đọc cũng phải theo logic đó.
- Nếu `defaultWriteObject()` đứng đầu, `defaultReadObject()` cũng phải đứng trước các thao tác đọc phần dữ liệu tùy chọn.
- Không đọc đến EOF của toàn ObjectInputStream để xác định điểm kết thúc dữ liệu một object: stream có framing và có thể còn nhiều object khác phía sau.
- Không tự tùy tiện trộn bytes ngoài `ObjectOutputStream` với bytes trong serialization stream theo kiểu phá header/protocol.

`defaultWriteObject()` **không lưu các trường transient**. Muốn khôi phục một transient được phép lưu, callback phải **chủ động ghi thêm** và đọc lại tương ứng. Với cache có thể tính lại, thường chỉ cần tái xây sau `defaultReadObject()` chứ không phải lưu byte của cache.

## 5. Ví dụ Java 17+ chạy độc lập: cả bốn phương thức làm việc cùng nhau

Ví dụ dùng một đối tượng `Order` có:

- `id` (String) và `cents` (int): được lưu bằng `defaultWriteObject`.
- `auditNote` là `transient`: **không** nằm trong phần default, nhưng được **chủ động ghi** như dữ liệu tùy chọn để minh họa hook.
- `runtimeLabel` là `transient`: không được ghi; `readObject` tạo lại nó với giá trị `restored`.
- `formatVersion` trong custom section để phát hiện định dạng không được hỗ trợ.
- Kiểm tra id không trống và số tiền không âm khi deserialization.

Lưu đúng tên **`CustomSerializationDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class CustomSerializationDemo {
    private static final class Order implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private String id;
        private int cents;
        private transient String auditNote;
        private transient String runtimeLabel;

        Order(String id, int cents, String auditNote) {
            this.id = id;
            this.cents = cents;
            this.auditNote = auditNote;
            this.runtimeLabel = "constructed";
        }

        @Serial
        private void writeObject(ObjectOutputStream out) throws IOException {
            out.defaultWriteObject();
            out.writeInt(1);
            out.writeBoolean(auditNote != null);
            if (auditNote != null) {
                out.writeUTF(auditNote);
            }
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            int formatVersion = in.readInt();
            if (formatVersion != 1) {
                throw new InvalidObjectException("Unsupported version");
            }
            auditNote = in.readBoolean() ? in.readUTF() : null;
            if (id == null || id.isBlank() || cents < 0) {
                throw new InvalidObjectException("Invalid order");
            }
            runtimeLabel = "restored";
        }

        String describe() {
            return "id=" + id + ",cents=" + cents
                    + ",note=" + auditNote + ",label=" + runtimeLabel;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        Order original = new Order("A-17", 1250, "verified");

        byte[] data;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(original);
            out.flush();
            data = bytes.toByteArray();
        }

        Order copy;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(data))) {
            copy = (Order) in.readObject();
        }

        System.out.println("original: " + original.describe());
        System.out.println("copy: " + copy.describe());
        System.out.println("different-instance=" + (original != copy));
        System.out.println("nonempty-stream=" + (data.length > 0));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CustomSerializationDemo.java
java CustomSerializationDemo
```

Stdout đã được xác nhận bằng biên dịch/chạy chương trình trên JDK 17+:

```text
original: id=A-17,cents=1250,note=verified,label=constructed
copy: id=A-17,cents=1250,note=verified,label=restored
different-instance=true
nonempty-stream=true
```

**Diễn giải đúng cơ chế:**

1. Khi ứng dụng gọi `out.writeObject(original)`, runtime tìm callback `Order.writeObject` có chữ ký đúng.
2. `out.defaultWriteObject()` ghi `id` và `cents` theo serializable field data của `Order`. Nó không tự ghi `auditNote` hay `runtimeLabel` vì cả hai là `transient`.
3. Callback ghi thêm `int 1` để đánh dấu format, `boolean` báo có audit note, rồi `writeUTF("verified")`.
4. Khi ứng dụng gọi `in.readObject()`, runtime khởi tạo object theo cơ chế serialization và gọi `Order.readObject`; `in.defaultReadObject()` phục hồi `id/cents`.
5. Bên đọc nhận đúng custom version/boolean/UTF, validate id/amount, đặt `runtimeLabel = "restored"` thay vì chạy constructor của `Order`.
6. `original != copy` vì object đọc là một instance mới trong process; nhưng đồ thị tham chiếu bên trong stream vẫn có quy tắc handle/identity riêng của Java serialization.
7. Hai dòng chứa audit note chứng tỏ `transient` **có thể được serialize theo cách thủ công**. Đây chỉ là ghi chú ví dụ, **không** nên hiểu là cho phép đưa token bí mật vào byte stream.

Ở demo nhỏ, `ByteArrayOutputStream` giúp dễ đối chiếu. Với dữ liệu lớn, cần quota, streaming hợp lý và chiến lược đọc/ghi thích hợp; đừng giữ stream Java serialized bytes vô hạn trong RAM chỉ vì muốn đơn giản hóa API.

## 6. Điều gì xảy ra nếu bỏ defaultWriteObject hoặc defaultReadObject?

Khi một class có callback riêng, việc ghi/đọc mặc định **không tự diễn ra** như khi class không có custom callback. Vì vậy nếu bỏ `out.defaultWriteObject()` trong ví dụ:

- Các field không transient như `id` và `cents` không còn tự được ghi theo phần field mặc định của class đó.
- Khi đọc mà vẫn gọi `defaultReadObject()`, bạn có thể nhận giá trị default/thiếu hoặc lỗi do stream/class descriptor không tương thích với kỳ vọng.
- Code kiểm tra `id == null` có thể phát hiện trạng thái invalid, nhưng không nên xem đây là cơ chế fallback thay cho định dạng đúng.

Ngược lại, nếu viết default field data mà không gọi `in.defaultReadObject()`, reader không chủ động khôi phục các field đó theo API mặc định của class. Phần dữ liệu cần đọc và các phần tùy chọn có nguy cơ bị diễn giải sai hoặc bị bỏ qua.

Khi thực sự muốn **chỉ ghi dữ liệu tự định nghĩa**, có thể thiết kế custom format không gọi default methods, nhưng phải hiểu chính xác protocol và tương thích với mọi phiên bản reader/writer. Với đa số lớp `Serializable` cần bổ sung thông tin, mẫu dễ kiểm soát nhất là:

```java
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    out.writeInt(customVersion);
    // Các extra fields theo thứ tự đã định nghĩa.
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    int customVersion = in.readInt();
    // Đọc đúng thứ tự và kiểm tra độ dài/giá trị.
}
```

Đây là **pseudocode** trong class serializable: `customVersion` cần có giá trị trước khi ghi, không phải chương trình độc lập. Các phương thức default chỉ nên được gọi **một lần** và trong ngữ cảnh callback phù hợp.

## 7. transient, derived fields và khôi phục invariants

Một trường `transient` thường thuộc một trong ba nhóm:

| Loại | Ví dụ | Nên làm gì sau khi đọc? |
| --- | --- | --- |
| Cache tính lại được | Giá trị format sẵn, thống kê dẫn xuất, lookup cache | Khởi tạo rỗng hoặc tính lại, không cần serialize. |
| Resource runtime | File handle, socket, thread, logger với lifecycle đặc biệt | Không serialize trực tiếp; tái mở/cấp phát khi cần theo lifecycle mới. |
| Dữ liệu cần tồn tại nhưng không muốn là default field | Trường tương thích version, snapshot metadata được phép lưu | Nếu thực sự cần, chủ động viết/đọc dưới custom protocol và giới hạn dữ liệu. |

**Không dựa vào constructor hay field initializer của chính class Serializable** để phục hồi transient state: khi deserialization, constructor của các lớp serializable không được gọi theo cách tạo object thông thường. Constructor no-arg của superclass đầu tiên **không** Serializable có thể được gọi theo cơ chế riêng của Java.

Bởi vậy, nếu `runtimeLabel` cần luôn không-null, tạo lại trong `readObject()`. Nếu đối tượng chứa invariants quan trọng, ví dụ `id != null`, `amount >= 0`, thuộc tính liên quan phải kiểm tra tương hỗ, dùng validation khi khôi phục.

Mẫu:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (id == null || id.isBlank() || cents < 0) {
        throw new InvalidObjectException("Invalid order");
    }
    runtimeLabel = "restored";
}
```

Đây là **snippet** dành cho class có các field `id`, `cents`, `runtimeLabel` và không ghi extra data; nếu writer có ghi custom fields, bên đọc còn phải đọc đúng phần đó trước khi hoàn tất callback. Từ chối object invalid ngay khi đọc thay vì để trạng thái xấu đi vào business logic.

Cần cẩn trọng khi class chứa nhiều tham chiếu chéo trong object graph: `readObject` có thể chạy khi các object khác trong graph chưa phục hồi hoàn chỉnh. Đừng công bố `this` cho thread khác, global registry hoặc code có side effect trước khi đồ thị được xác minh.

## 8. serialVersionUID và version của custom data là hai chuyện khác nhau

Hai dạng version:

- **`serialVersionUID`:** nhận dạng phiên bản serialization compatibility của class; nếu UID của class trong stream không tương thích với class cục bộ, `InvalidClassException` có thể được ném trước khi custom deserialization có thể xử lý.
- **`formatVersion` tự ghi:** marker do ứng dụng định nghĩa bên trong **optional data** của callback; giúp phân biệt layout custom extra data khi mọi điều kiện khác của protocol/class vẫn tương thích.

```java
@Serial
private static final long serialVersionUID = 1L;

@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
    out.writeInt(2); // Schema riêng cho phần custom data.
}
```

Đây là snippet, không phải mẫu đầy đủ. Khi đổi optional-data version từ 1 sang 2, **reader phải có nhánh xử lý cả hai** nếu yêu cầu tương thích ngược. Chỉ thêm `writeInt(2)` mà quên đổi `readObject` sẽ làm reader cũ từ chối hoặc đọc sai.

Đừng tùy tiện thay `serialVersionUID` mỗi khi bổ sung một optional field. UID có mục đích quyết định mức tương thích của **class serialization schema**. Giữ UID cố định không tự bảo đảm mọi thay đổi sẽ an toàn: đổi kiểu field, class hierarchy, chuyển một field sang `transient`, thay protocol callback hoặc serialization proxy đều phải có kiểm thử version/cross-version thực tế.

Một số thay đổi mặc định có quy tắc tiến hóa field của Java serialization, nhưng optional data là **giao thức riêng do bạn chịu trách nhiệm**. Hãy lưu fixtures chứa bytes được tạo bởi version cũ và chạy test cả writer cũ → reader mới (và ngược lại khi sản phẩm yêu cầu).

## 9. Optional data, writeObject/readObject và tính đối xứng

Sau `defaultWriteObject()`, callback có thể ghi primitives hoặc serializable objects:

```java
// Snippet: trong private writeObject(...)
out.defaultWriteObject();
out.writeInt(customSchema);
out.writeBoolean(optionalValue != null);
if (optionalValue != null) {
    out.writeUTF(optionalValue);
    out.writeObject(additionalObject);
}
```

Đầu đọc:

```java
// Snippet: trong private readObject(...)
in.defaultReadObject();
int schema = in.readInt();
boolean present = in.readBoolean();
if (present) {
    String optionalValue = in.readUTF();
    Object additionalObject = in.readObject();
}
```

Các biến `customSchema`, `optionalValue` và `additionalObject` thuộc logic ứng dụng. `readObject()` bên trong callback để đọc một đối tượng **phụ**, khác với `defaultReadObject()` dùng khôi phục mặc định. Cần xác định kiểu hợp lệ cho object phụ, đánh giá nguồn tin cậy và tránh nhét vào graph những class không được phép.

**Không dùng `readUTF()` để đọc bytes được ghi bằng `writeObject(String)` hoặc ngược lại.** Hai phương thức có encoding/protocol khác nhau. `writeUTF/readUTF` sử dụng modified UTF-8 và giới hạn byte được biểu diễn của định dạng UTF, không phải phương thức ghi chuỗi tùy ý không giới hạn.

Phần dữ liệu riêng cần có schema rõ: thứ tự, marker, optional/null, giới hạn kích thước, khả năng gặp phiên bản mới, và lỗi khi dữ liệu bị cắt. Không để reader “thử đoán” từ số byte còn lại của toàn stream; framing serialization bao trùm cả object graph.

## 10. Khi nào dùng putFields/readFields thay default methods?

Java còn cung cấp cơ chế `ObjectOutputStream.PutField` và `ObjectInputStream.GetField` cho trường hợp muốn điều khiển **giá trị field mặc định được serialize** mà không trực tiếp gán trạng thái runtime field trước khi ghi.

```java
// Snippet bên trong private writeObject(...)
ObjectOutputStream.PutField fields = out.putFields();
fields.put("name", name);
fields.put("age", age);
out.writeFields();
```

Và:

```java
// Snippet bên trong private readObject(...)
ObjectInputStream.GetField fields = in.readFields();
String restoredName = (String) fields.get("name", "");
int restoredAge = fields.get("age", 0);
```

Đây là snippet của class có serializable fields tương ứng và import phù hợp; có thể dùng `serialPersistentFields` khi cần định nghĩa tập field logic độc lập với biểu diễn trong bộ nhớ. **Không trộn `defaultWriteObject()` với `putFields/writeFields()` cho cùng phần default field data**; hai con đường thay thế nhau. Phía đọc cũng chọn `defaultReadObject()` hoặc `readFields()` tương ứng trong ngữ cảnh callback.

Dùng `PutField/GetField` khi cần schema cũ/ảo có ý nghĩa, nhưng đây là API thấp hơn và dễ sai. Với nhu cầu học cơ chế phổ biến, bắt đầu bằng cặp `defaultWriteObject/defaultReadObject`.

## 11. Lưu ý về object graph và stream handles

`ObjectOutputStream` duy trì handle table để giữ identity khi cùng một đối tượng được ghi nhiều lần trên **cùng stream**:

```java
out.writeObject(order);
out.writeObject(order);
```

Trong điều kiện object không bị thay thế bởi hook đặc biệt, phía đọc có thể nhận **cùng một instance trong graph** cho hai lời gọi tương ứng, không phải luôn tạo bản sao thứ hai. Điều này quan trọng nếu ứng dụng sửa field sau lần write thứ nhất mà nghĩ lần write thứ hai chắc chắn ghi snapshot mới.

Nếu cần stream ghi lại trạng thái mới một cách có kiểm soát, tìm hiểu `ObjectOutputStream.reset()`, `writeUnshared()` và định nghĩa cách đồng bộ của ứng dụng. **Không dùng `reset()` tùy tiện** khi đồ thị có quan hệ tham chiếu cần giữ giữa các object khác nhau; thay đổi handle semantics sẽ ảnh hưởng reader.

Không tạo `ObjectOutputStream` mới để “append” thêm object vào cuối một file serialized sẵn có một cách ngây thơ: constructor viết stream header mới, dễ làm `ObjectInputStream` đọc nối tiếp bị `StreamCorruptedException`. Nếu cần persistence có thể append/update ổn định, cân nhắc định dạng record tự mô tả hoặc giải pháp lưu trữ khác.

## 12. Hierarchy, inheritance và các hook liên quan

Một object có thể gồm nhiều đoạn dữ liệu serialization thuộc các class serializable khác nhau trong hierarchy. Mỗi class có thể có callback `writeObject/readObject` **riêng của chính nó**. Chúng không phải các method override theo kiểu polymorphism thông thường.

Các chi tiết quan trọng:

- Một subclass `Serializable` có thể có callback private riêng; superclass `Serializable` có thể có callback private khác.
- Non-serializable superclass thường được khởi tạo theo cơ chế gọi constructor không đối số của class đầu tiên không serializable trong hierarchy khi deserialization. Các field trong non-serializable superclass không tự được khôi phục như field serializable.
- `readObjectNoData()` là hook đặc biệt tùy chọn để xử lý trường hợp không có dữ liệu serialization cho class trong một số thay đổi hierarchy/version. Nó **không** thay cho `readObject()` thông thường.
- `writeReplace()` và `readResolve()` có thể thay thế object được ghi/đọc, dẫn tới mô hình **serialization proxy**. Đây là một lựa chọn mạnh cho class bất biến, nhưng có quy tắc riêng về object identity, compatibility và validation.
- `Externalizable` là cơ chế **khác**: code triển khai `writeExternal/readExternal` và vòng đời constructor theo hợp đồng Externalizable, không đồng nghĩa thêm `defaultWriteObject()` như class Serializable.

Nếu class có invariants liên quan nhiều field hoặc không muốn cho phép tạo object bypass constructor theo serialization, cân nhắc serialization proxy pattern hoặc bỏ hỗ trợ Java native serialization.

## 13. Ngoại lệ thường gặp và chẩn đoán

| Ngoại lệ / triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `NotSerializableException` | Một object trong graph không triển khai Serializable, hoặc không có chiến lược serialize cho field liên quan. | Chọn dữ liệu có thể serialize; đánh dấu transient và tái tạo đúng nếu phù hợp. |
| `InvalidClassException` | UID/class descriptor không tương thích, hoặc vi phạm điều kiện tạo object. | Kiểm soát serialVersionUID, migrations và compatibility tests. |
| `StreamCorruptedException` | Stream header/format hỏng, dữ liệu bị ghép sai, hoặc ghi bytes không theo serialization protocol. | Dùng cặp Object streams đúng, không nối header tùy tiện. |
| `OptionalDataException` | Reader kỳ vọng object nhưng gặp primitive optional data hoặc dữ liệu ở phần optional không như schema. | Cân bằng thứ tự read/write và phân biệt `readObject` với primitive reads. |
| `EOFException` | Byte stream bị cắt trước khi đủ dữ liệu được reader yêu cầu. | Kiểm tra truncate, truyền tải, framing, retry/abort theo chính sách. |
| `ClassNotFoundException` | Class cần khôi phục không có trong classpath/module tương ứng. | Kiểm tra triển khai version, dependency, không cho phép class tùy ý từ nguồn ngoài. |
| `InvalidObjectException` | `readObject` chủ động từ chối object sai schema/invariants. | Giữ validation, sửa writer/nguồn dữ liệu, không bypass kiểm tra. |
| `NotActiveException` | Gọi `defaultReadObject/defaultWriteObject` ngoài callback active hợp lệ. | Chỉ gọi đúng ngữ cảnh runtime callback. |
| Field `transient` là null sau đọc | Không được ghi mặc định, constructor Serializable không chạy. | Tái tạo trong `readObject` hoặc lazy-init sau đọc. |
| Callback “không chạy” | Sai chữ ký, không private, dùng static hoặc không Serializable. | Khai báo private chính xác và dùng `@Serial` để compiler hỗ trợ kiểm tra. |
| Reader lấy sai custom field | Thứ tự `writeInt/writeUTF/...` khác `readInt/readUTF/...` hoặc version không được hỗ trợ. | Viết schema đối xứng và có test fixtures. |
| Same object viết hai lần nhưng “không cập nhật” | Stream handle table giữ object identity; lần sau có thể là reference. | Thiết kế snapshot/stream lifecycle rõ, nghiên cứu `reset()` phù hợp. |

Không cố “sửa” exception bằng cách bỏ validate hoặc catch tất cả rồi trả object chưa hoàn chỉnh. Deserialization thất bại phải được coi là lỗi parse/kiểm tra dữ liệu, với tài nguyên và trạng thái ứng dụng được dọn an toàn.

## 14. Bảo mật: tuyệt đối không coi readObject là parser an toàn cho input tùy ý

Serialization là **một cơ chế khởi tạo object graph với code có thể được gọi trong quá trình đọc**. Khi `ObjectInputStream.readObject()` xử lý bytes của nguồn không đáng tin, việc đọc class/graph có thể kích hoạt callback `readObject`, `readResolve` và logic của class khác trong dependencies trước khi bạn có cơ hội cast hay kiểm tra giá trị sau đọc.

Rủi ro gồm:

- Gadget chains và side effects không mong muốn trong classpath.
- Tài nguyên cạn do graph sâu, rất nhiều object, array lớn hoặc dữ liệu custom không giới hạn.
- Object có invariant sai (ví dụ số âm, null ở field bắt buộc) nếu reader không validate.
- Thông tin nhạy cảm vô ý lọt vào stream, hoặc custom callback chủ động ghi secrets.
- Dữ liệu phiên bản lạ khiến reader lỗi hoặc áp dụng nhầm logic cũ.

Các biện pháp tối thiểu:

1. **Không deserialize dữ liệu không đáng tin** nếu có thể thiết kế thay thế bằng format ít quyền năng hơn.
2. Nếu bắt buộc: đặt `ObjectInputFilter`/serialization filter **trước khi gọi `readObject()`**, allowlist class thật sự cần, giới hạn độ sâu, số references, kích thước bytes, độ dài arrays và các tài nguyên liên quan.
3. Bảo vệ cả transport và nguồn dữ liệu: xác thực, phân quyền, kiểm tra integrity/authenticity; filter không thay thế cơ chế này.
4. Validate mọi invariants trong callback hoặc proxy; từ chối data sai bằng exception như `InvalidObjectException`.
5. Áp dụng quota/timeout cho phần custom data; `ObjectInputFilter` không tự hiểu mọi logic nghiệp vụ của một callback tùy biến.
6. Không coi việc cast sau `readObject()` là đủ an toàn vì side effects có thể đã xảy ra.
7. Cập nhật dependencies và kiểm thử bảo mật; không tự tin chỉ vì object class của ứng dụng “đơn giản”.

**Lưu ý:** Một filter không phải giải pháp tuyệt đối cho mọi gadget/class và không giải quyết việc bytes serialized bị sửa có chủ đích. Với hệ thống cần trao đổi giữa service, định dạng schema có validation và authentication rõ ràng thường là lựa chọn tốt hơn native Java serialization.

## 15. Kiểm thử tính đúng đắn và khả năng tương thích

Một bộ test có ích nên gồm:

| Loại test | Điều cần chứng minh |
| --- | --- |
| Roundtrip cơ bản | Ghi đối tượng rồi đọc lại; field mặc định và optional data đúng. |
| Transient rebuild | Field không lưu tự động được khởi tạo lại đúng và không chứa giá trị cũ không mong muốn. |
| Null optional field | Boolean/marker xác định đúng trường hợp thiếu, không đọc thừa `readUTF`. |
| Invalid invariants | Reader từ chối id null, giá trị âm, trạng thái đối nghịch hoặc field sai. |
| Custom version không hỗ trợ | Reader ném exception có chủ đích, không tạo object dùng được. |
| UID/class mismatch | Phát hiện phiên bản class không tương thích, không báo thành công giả. |
| Truncated stream | Reader thất bại có kiểm soát, không lộ object partial ra ngoài. |
| Graph tham chiếu vòng/trùng | Identity/reference semantics giữ đúng theo hợp đồng stream. |
| Writer cũ → Reader mới | Schema optional data có khả năng backward compatibility dự kiến. |
| Reader cũ → Writer mới | Kiểm tra forward compatibility nếu nghiệp vụ cần; có thể chủ động từ chối. |
| Khối lượng lớn | Quota, latency, giới hạn kích thước và resource cleanup. |
| Nguồn không tin cậy | Verify filter và không sử dụng Java native deserialization cho bytes công khai khi không cần. |

Đối với output của bài demo, chỉ kiểm tra `different-instance=true` và các field liên quan; không so chính xác số byte serialized stream vì implementation/class details có thể khiến kích thước thay đổi và vì byte count không nói lên correctness của application schema.

## 16. Bài tập thực hành

**Bài 1 — So sánh default với custom.** Tạo một class chỉ có `implements Serializable`, không callback; roundtrip 2 field thường và 1 field transient. Sau đó thêm `writeObject/readObject`, dùng đúng `defaultWriteObject/defaultReadObject` và kiểm tra kết quả thay đổi ra sao.

**Bài 2 — Optional field null.** Với ví dụ `CustomSerializationDemo`, truyền `auditNote = null`. Theo dõi byte logic: ghi `boolean false`, không ghi UTF; reader phải nhận lại `null` mà không thực hiện `readUTF()`.

**Bài 3 — Kiểm tra invariants.** Mở rộng Order thêm `quantity` và `unitPrice`, bắt buộc cents bằng tích hai giá trị trong phạm vi không tràn số. Validate trong `readObject` bằng toán học an toàn; nêu lý do validate trước khi công bố object.

**Bài 4 — Version của dữ liệu bổ sung.** Tạo custom version 1 chỉ lưu một boolean, version 2 thêm string. Viết reader có switch theo version, xử lý v1/v2 theo đúng thứ tự, từ chối version tương lai không được hỗ trợ. Giữ fixture bytes của mỗi version.

**Bài 5 — Không được ghi secret.** Thêm transient `authToken` chỉ dùng tại runtime. Thử roundtrip và xác nhận token sau deserialize là null hoặc được cấp lại bởi hệ thống xác thực, **không** ghi nó bằng optional data.

**Bài 6 — Chữ ký hook.** Cố ý đổi callback thành `public void readObject(...)` hoặc thiếu tham số. Dùng `@Serial` và compiler để phát hiện sự khác biệt; giải thích vì sao đây không phải method override bình thường.

**Bài 7 — Đọc đồ thị.** Tạo hai field cùng trỏ một instance Address. Sau roundtrip, kiểm tra identity của các tham chiếu trong object mới, không chỉ `equals`. Thử cùng một object được `writeObject` hai lần trên một stream và nghiên cứu handle table.

**Bài 8 — Kiểm tra security boundary.** Thiết lập filter giới hạn depth, references, bytes và class được phép cho một thử nghiệm dữ liệu tự tạo. So sánh với cách chuyển DTO sang JSON có schema kiểm soát. Không dùng payload khai thác, không nhận stream serialized từ người dùng trên dịch vụ thật.

### Câu hỏi tự kiểm tra

1. `ObjectOutputStream.writeObject(obj)` khác `private writeObject(ObjectOutputStream)` ở đâu?
2. Tại sao callback cần gọi `defaultWriteObject()` nếu vẫn muốn giữ các field thông thường?
3. `defaultReadObject()` có tự phục hồi field `transient` không?
4. Sau `defaultWriteObject()` nếu ghi `int, boolean, UTF` thì reader phải gọi những gì theo đúng thứ tự?
5. Vì sao `@Serial` và modifier private quan trọng với callback?
6. Vì sao `serialVersionUID` không thay thế version riêng của optional data?
7. Tại sao constructor của Serializable class không thể đảm nhận toàn bộ khôi phục cache?
8. Vì sao không nên serialize bearer token dù field được đánh dấu `transient`?
9. Vì sao filter phải được thiết lập **trước** lần `readObject()`?
10. Lỗi nào có thể xảy ra nếu cùng một stream ghi hai lần cùng một object nhưng ứng dụng mong một snapshot mới?

## 17. Tài liệu tham khảo

- [Java SE 21 — Serializable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html): hợp đồng callback private, serialVersionUID, readObjectNoData, writeReplace/readResolve.
- [Java SE 21 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectOutputStream.html): writeObject, defaultWriteObject, putFields, handles, reset và protocol ghi.
- [Java SE 21 — ObjectInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html): readObject, defaultReadObject, readFields và các exception.
- [Java SE 21 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html): lọc class/object graph và giới hạn tài nguyên.
- [Java SE 21 — @Serial](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serial.html): annotation hỗ trợ kiểm tra cấu trúc serialization.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html): format, class evolution và chi tiết protocol.

**Ghi nhớ:** `writeObject/readObject` là callback private của class Serializable; `defaultWriteObject/defaultReadObject` giữ phần field data mặc định, còn các lệnh `writeInt/writeUTF/readInt/readUTF` xử lý phần dữ liệu bổ sung theo thứ tự đối xứng. Khôi phục transient và validate bất biến rõ ràng, giữ version phù hợp, và không dùng Java native deserialization với nguồn không đáng tin.
