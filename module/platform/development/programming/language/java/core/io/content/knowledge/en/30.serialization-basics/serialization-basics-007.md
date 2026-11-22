# NotSerializableException, InvalidClassException và StreamCorruptedException trong Java Serialization

## 1. Mục tiêu bài học và bối cảnh

Khi dùng Java Object Serialization, ba ngoại lệ `NotSerializableException`, `InvalidClassException` và `StreamCorruptedException` thường cùng xuất hiện quanh thao tác `ObjectOutputStream.writeObject(...)` / `ObjectInputStream.readObject(...)`, nhưng chúng báo **ba loại vấn đề khác nhau**:

- **`NotSerializableException`:** không thể ghi một đối tượng trong đồ thị đối tượng vì lớp của nó không hỗ trợ Java Serialization.
- **`InvalidClassException`:** mô tả lớp trong luồng và lớp đang nạp không tương thích cho quá trình khôi phục đối tượng (điển hình là `serialVersionUID` không khớp).
- **`StreamCorruptedException`:** dữ liệu đọc vào không tuân theo định dạng Java Object Serialization hoặc chứa mã định dạng không hợp lệ.

Bài này tập trung vào Java Serialization chuẩn trong `java.io` trên **Java 17+**: nguyên nhân, thời điểm phát sinh, cách tái hiện, cách đọc thông báo lỗi, biện pháp sửa và phòng tránh. Đây là các ngoại lệ *checked* thuộc nhánh `IOException`; đừng dựa vào việc chúng cùng là `IOException` để xử lý như một lỗi duy nhất.

## 2. Cơ chế nền tảng cần hiểu

`ObjectOutputStream` ghi đối tượng Java thành một **object stream**, bao gồm dữ liệu nhận dạng lớp, thông tin phiên bản và dữ liệu trạng thái của đối tượng. `ObjectInputStream` diễn giải luồng đó và tái tạo đối tượng dựa trên lớp có trong JVM đang đọc.

Quá trình này có những điều kiện riêng:

1. **Tính serializable của cả đồ thị:** lớp muốn được tuần tự hóa thông thường triển khai marker interface `java.io.Serializable`. Khi ghi một đối tượng, Java còn duyệt các trường tham chiếu không `static`, không `transient` mà nó phải ghi. Nếu gặp đối tượng có lớp không serializable, thao tác thất bại dù lớp gốc đã triển khai `Serializable`.
2. **Tương thích lớp khi đọc:** mô tả lớp đã lưu được so với lớp cục bộ. `serialVersionUID` (kiểu `long`) là khóa kiểm tra phiên bản tiêu biểu, nhưng UID giống nhau không tự bảo đảm mọi thay đổi cấu trúc lớp là tương thích.
3. **Đúng định dạng luồng:** `ObjectInputStream` mong đợi dữ liệu do cơ chế object stream tạo ra. Ví dụ luồng thường bắt đầu bằng header byte `AC ED 00 05`; đưa file văn bản, JSON hoặc byte ngẫu nhiên vào `ObjectInputStream` không biến chúng thành đối tượng Java.
4. **Vòng đời tài nguyên:** luồng phải được đóng hoặc hoàn tất ghi trước khi đọc từ byte/file đã tạo. `try-with-resources` giúp đóng luồng khi thành công hoặc có lỗi.

`Serializable` không liên quan đến `java.beans`, JSON serialization hay việc chỉ cần lớp có getter/setter. Đây là một giao thức nhị phân dành riêng cho Java Object Serialization.

## 3. Bảng phân biệt nhanh

| Ngoại lệ | Thường xuất hiện khi | Ý nghĩa trọng tâm | Hướng kiểm tra đầu tiên |
| --- | --- | --- | --- |
| `NotSerializableException` | `ObjectOutputStream.writeObject`; cũng có thể trong custom serialization | Một đối tượng cần ghi không serializable | Tên lớp trong `getMessage()`; đường đi tới trường tham chiếu gây lỗi |
| `InvalidClassException` | `ObjectInputStream.readObject` hoặc trong cơ chế kiểm tra lớp khi tuần tự hóa | Định nghĩa/mô tả lớp không tương thích hoặc không hợp lệ | Tên lớp, `serialVersionUID` ở hai phía, lịch sử thay đổi lớp |
| `StreamCorruptedException` | Khởi tạo `ObjectInputStream` (header sai) hoặc lúc `readObject` | Các byte không đúng quy tắc định dạng object stream | Nguồn byte, header, việc ghép/trộn/ghi nối luồng |

**Lưu ý:** vị trí phát sinh ở bảng là tình huống thường gặp, không phải danh sách mọi đường đi nội bộ. Khi chẩn đoán, ưu tiên exception type, message, stack trace và thao tác I/O đang chạy.

## 4. `NotSerializableException` — có đối tượng không được phép ghi

### 4.1. Nguyên nhân và đối tượng gây lỗi

Java ném `java.io.NotSerializableException` nếu một đối tượng phải được ghi nhưng lớp của nó không triển khai `Serializable` hoặc `Externalizable` theo cách hợp lệ. Nguyên nhân phổ biến:

- Lớp gốc chưa triển khai `Serializable`.
- Lớp gốc triển khai `Serializable` nhưng một trường giữ đối tượng không serializable, ví dụ `Thread`, kết nối DB, stream, socket hay một `Object` thuần.
- Một collection serializable như `ArrayList` chứa phần tử không serializable; phải kiểm tra **phần tử thực tế**, không chỉ kiểu của collection.
- Custom `writeObject` / `writeExternal` chủ động ghi một đối tượng không serializable.

Các trường `static` không nằm trong trạng thái đối tượng được serialization mặc định ghi. Trường `transient` được bỏ qua theo cơ chế mặc định, nhưng nếu custom `writeObject` tự gọi `writeObject` trên trường đó thì lỗi vẫn có thể xảy ra.

### 4.2. Ví dụ tái hiện được trên Java 17+

Tạo file `NotSerializableDemo.java`:

~~~java
import java.io.*;

public class NotSerializableDemo {
    static final class Job implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String code;
        private final Object runtimeState = new Object();

        Job(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) throws IOException {
        try (var bytes = new ByteArrayOutputStream();
             var out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Job("J-01"));
        } catch (NotSerializableException e) {
            System.out.println("NotSerializableException: " + e.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac NotSerializableDemo.java
java NotSerializableDemo
~~~

Kết quả:

~~~text
NotSerializableException: java.lang.Object
~~~

`Job` đã implements `Serializable`, nhưng trường `runtimeState` chứa đối tượng `java.lang.Object`, vốn không triển khai interface đó. Tên lớp trong message là **lớp của đối tượng gây lỗi**, không nhất thiết là lớp được truyền trực tiếp vào `writeObject`. `code` là `String` nên không gây lỗi.

### 4.3. Sửa đúng theo ý nghĩa dữ liệu

Nếu `runtimeState` là cache hoặc tài nguyên chỉ dùng lúc chạy, đánh dấu `transient` và tạo lại khi cần. Nếu dữ liệu đó *phải tồn tại sau khi khôi phục*, đừng chỉ đánh dấu `transient` để loại bỏ lỗi: hãy chuyển nó thành trạng thái có thể ghi, hoặc thiết kế DTO riêng chỉ chứa dữ liệu cần lưu.

Ví dụ file độc lập `TransientDemo.java`:

~~~java
import java.io.*;

public class TransientDemo {
    static final class Job implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String code;
        private transient Object runtimeState = new Object();

        Job(String code) {
            this.code = code;
        }
    }

    public static void main(String[] args) throws Exception {
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Job("J-01"));
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            Job restored = (Job) in.readObject();
            System.out.println(restored.code);
            System.out.println(restored.runtimeState == null);
        }
    }
}
~~~

~~~bash
javac TransientDemo.java
java TransientDemo
~~~

~~~text
J-01
true
~~~

Trường `transient` nhận giá trị mặc định (`null` với kiểu tham chiếu) khi đối tượng serializable được khôi phục theo cơ chế mặc định; initializer `= new Object()` của chính lớp serializable **không chạy lại** trong quá trình đó. Nếu muốn tái tạo cache sau khi đọc, có thể bổ sung custom `readObject` phù hợp hoặc khởi tạo lười ở phương thức truy cập. Chỉ thêm `implements Serializable` cho mọi lớp gặp lỗi cũng không an toàn: nhiều tài nguyên runtime không có ý nghĩa khi lưu ra đĩa.

## 5. `InvalidClassException` — lớp trong stream và lớp hiện tại không tương thích

### 5.1. Vai trò của `serialVersionUID`

`java.io.InvalidClassException` thường gặp khi ứng dụng ghi đối tượng bằng một bản class, sau đó đọc bằng bản class khác có `serialVersionUID` không khớp. Khi class triển khai `Serializable`, nên khai báo UID cố định và có chủ đích:

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

`@Serial` là annotation có từ Java 14, hữu ích cho compiler kiểm tra khai báo/điểm mở rộng serialization; nó không làm class tự serializable. Nếu không khai báo UID, JVM tính giá trị mặc định từ các đặc điểm của lớp; nhiều chỉnh sửa source có thể làm UID tự tính đổi, tạo lỗi khó đoán. UID cố định cho phép chủ động quản lý tương thích nhưng **không phải cơ chế chuyển đổi schema**.

Các nguyên nhân khác có thể là class không hợp lệ theo quy tắc serialization, ví dụ thiếu constructor không tham số có thể truy cập của lớp cha đầu tiên không serializable, hoặc thay đổi cấu trúc không tương thích trong lớp. Đừng khẳng định mọi `InvalidClassException` đều do UID.

### 5.2. Tái hiện lỗi bằng hai bản của cùng một class

Ví dụ này cần **hai lần biên dịch riêng biệt** vì hai file `SavedItem.java` mang cùng tên class nhưng khác UID. Tạo cấu trúc:

~~~text
demo/
  v1/SavedItem.java
  v1/WriteItem.java
  v2/SavedItem.java
  v2/ReadItem.java
~~~

Nội dung `v1/SavedItem.java`:

~~~java
import java.io.Serial;
import java.io.Serializable;

public class SavedItem implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String name;

    public SavedItem(String name) {
        this.name = name;
    }
}
~~~

Nội dung `v1/WriteItem.java`:

~~~java
import java.io.*;

public class WriteItem {
    public static void main(String[] args) throws Exception {
        try (var out = new ObjectOutputStream(
                new FileOutputStream("saved-item.ser"))) {
            out.writeObject(new SavedItem("J-01"));
        }
        System.out.println("Wrote v1");
    }
}
~~~

Nội dung `v2/SavedItem.java` (cùng tên class, UID đổi thành 2):

~~~java
import java.io.Serial;
import java.io.Serializable;

public class SavedItem implements Serializable {
    @Serial
    private static final long serialVersionUID = 2L;

    private final String name;

    public SavedItem(String name) {
        this.name = name;
    }
}
~~~

Nội dung `v2/ReadItem.java`:

~~~java
import java.io.*;

public class ReadItem {
    public static void main(String[] args) throws Exception {
        try (var in = new ObjectInputStream(
                new FileInputStream("saved-item.ser"))) {
            in.readObject();
            System.out.println("Read OK");
        } catch (InvalidClassException e) {
            System.out.println("InvalidClassException");
        }
    }
}
~~~

Từ thư mục `demo` chứa sẵn `v1` và `v2`, chạy lần lượt:

~~~bash
javac -d v1 v1/SavedItem.java v1/WriteItem.java
java -cp v1 WriteItem
javac -d v2 v2/SavedItem.java v2/ReadItem.java
java -cp v2 ReadItem
~~~

Kết quả:

~~~text
Wrote v1
InvalidClassException
~~~

Bản v1 ghi mô tả `SavedItem` có UID `1L`. Bản v2 đang nạp class cùng tên với UID `2L`, nên `readObject` không thể khôi phục đối tượng. Nếu in `e.getMessage()`, thông báo thường cho biết tên class và hai giá trị `serialVersionUID`; không nên phụ thuộc vào toàn bộ câu chữ message giữa các bản JDK.

### 5.3. Xử lý đúng khi class tiến hóa

1. Xác định **bản ứng dụng nào đã ghi** dữ liệu và **bản nào đang đọc**; lưu lại stack trace và message.
2. Kiểm tra `serialVersionUID`, class name/package, thay đổi các trường và class hierarchy. Công cụ `serialver -classpath ... TenClass` có thể tra cứu UID của class đã biên dịch, nhưng đối chiếu với UID trong dữ liệu/phiên bản đã triển khai mới là điều cần thiết.
3. Với các thay đổi tương thích (ví dụ thêm trường thông thường), giữ UID chủ đích nếu đã xác minh hợp đồng dữ liệu; trường mới thường nhận giá trị mặc định khi đọc dữ liệu cũ.
4. Với thay đổi không tương thích hoặc có biến đổi ngữ nghĩa, tạo **quy trình migration**, đọc bằng phiên bản cũ rồi xuất định dạng mới, hoặc duy trì reader cho dữ liệu cũ. Không tùy tiện sửa UID của v2 về 1 chỉ để tắt exception.
5. Nếu phải duy trì dữ liệu lâu dài hoặc trao đổi giữa hệ thống, cân nhắc định dạng có schema/version và migration rõ ràng thay cho serialization nhị phân của Java.

UID bằng nhau **không** đảm bảo dữ liệu hợp lệ về mặt nghiệp vụ. Ví dụ chuyển tên thuộc tính sang ý nghĩa khác có thể dẫn đến giá trị mặc định hoặc dữ liệu sai mà không ném lỗi. Ngược lại, không phải mọi thay đổi trường đều bất tương thích; quy tắc tương thích serialization cụ thể quyết định.

## 6. `StreamCorruptedException` — byte stream không đúng định dạng

### 6.1. Nguyên nhân phổ biến

`java.io.StreamCorruptedException` báo rằng object stream có phần điều khiển/định dạng không hợp lệ. Một số tình huống:

- Tạo `ObjectInputStream` trên văn bản UTF-8, JSON, CSV, ảnh hoặc dữ liệu từ `DataOutputStream` thay vì luồng đã ghi bằng `ObjectOutputStream`.
- Bỏ sót hoặc đọc sai byte đầu luồng; truyền vào dữ liệu bắt đầu từ một offset không đúng.
- Trộn việc ghi `ObjectOutputStream` với ghi byte thủ công vào **cùng protocol** mà phía đọc không biết cách xử lý.
- Nối tiếp nhiều lần ghi bằng **những `ObjectOutputStream` mới** vào cùng file; mỗi lần tạo object stream mới viết thêm header, khiến một `ObjectInputStream` đang đọc liên tục có thể gặp header giữa luồng như một mã dữ liệu bất hợp lệ.
- Dữ liệu bị thay đổi/hỏng ở phần cấu trúc định dạng.

Không có quy tắc “file hỏng luôn là `StreamCorruptedException`”: file rỗng/thiếu byte có thể gây `EOFException`; luồng sai định dạng hoặc bị cắt ở vị trí khác có thể cho những ngoại lệ khác.

### 6.2. Ví dụ sai header, kết quả ổn định

Tạo file `StreamCorruptedDemo.java`:

~~~java
import java.io.*;

public class StreamCorruptedDemo {
    public static void main(String[] args) throws Exception {
        byte[] notAnObjectStream = {0x00, 0x01, 0x02, 0x03};

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(notAnObjectStream))) {
            in.readObject();
        } catch (StreamCorruptedException e) {
            System.out.println("StreamCorruptedException");
        }
    }
}
~~~

~~~bash
javac StreamCorruptedDemo.java
java StreamCorruptedDemo
~~~

~~~text
StreamCorruptedException
~~~

Lỗi phát sinh **ngay trong constructor `ObjectInputStream`** khi đọc header, trước cả lệnh `readObject()`. Nếu in message, trường hợp trên thường có `invalid stream header: 00010203`; mã hex hữu ích để nhận biết loại dữ liệu thực sự.

### 6.3. Ghi và đọc đúng cặp luồng

Một cặp tuần tự hóa tối thiểu, file `RoundTripDemo.java`:

~~~java
import java.io.*;

public class RoundTripDemo {
    public static void main(String[] args) throws Exception {
        var bytes = new ByteArrayOutputStream();

        try (var out = new ObjectOutputStream(bytes)) {
            out.writeObject("hello");
        }

        try (var in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            String value = (String) in.readObject();
            System.out.println(value);
        }
    }
}
~~~

~~~bash
javac RoundTripDemo.java
java RoundTripDemo
~~~

~~~text
hello
~~~

Phía ghi và đọc phải thống nhất thứ tự đối tượng, ranh giới thông điệp và cách mở/đóng luồng. Khi muốn ghi nhiều đối tượng trong một file, dùng **một `ObjectOutputStream` cho cả phiên ghi** và một `ObjectInputStream` tương ứng cho phiên đọc, với số lượng/ranh giới bản ghi được xác định rõ. `flush()` đẩy dữ liệu đệm xuống lớp dưới; nó không chữa lỗi định dạng hoặc việc ghi nhiều header.

Nếu giao thức có tiền tố là độ dài, version hay byte metadata tự định nghĩa, cần tách/đọc đúng phần đó trước khi tạo `ObjectInputStream` trên **đúng đoạn payload object stream**; không thể dùng `readObject()` để đọc byte tùy ý.

## 7. Tình huống dễ nhầm với ba ngoại lệ này

| Triệu chứng | Có thể là gì | Cách xác minh |
| --- | --- | --- |
| `writeObject(list)` báo `NotSerializableException: com.example.X` | Một phần tử hoặc trường con kiểu `X` không serializable | Dò object graph từ list xuống các phần tử và trường |
| `readObject()` báo `InvalidClassException` sau khi nâng phiên bản | Class đã đổi UID hoặc có thay đổi không tương thích | So bản class ghi/đọc và UID; thử đọc bằng bản cũ |
| `new ObjectInputStream(...)` báo `StreamCorruptedException` | Header sai hoặc đọc nhầm định dạng/offset | Kiểm tra nguồn, 4 byte đầu và code tạo file |
| `readObject()` báo `EOFException` | Kết thúc luồng, thiếu dữ liệu hoặc số lần đọc vượt số lần ghi | Đếm bản ghi, kiểm tra kích thước file và vòng lặp đọc |
| `readObject()` báo `ClassNotFoundException` | Class được ghi không có trong classpath/class loader phía đọc | Kiểm tra tên class/package/JAR và môi trường triển khai |
| `readObject()` báo `OptionalDataException` | Reader yêu cầu object tại vị trí đang có primitive data trong protocol | So thứ tự `writeObject`, `writeInt` và các lệnh đọc tương ứng |
| `readObject()` báo `WriteAbortedException` | Bên ghi từng abort quá trình ghi object sau lỗi và stream có dấu vết đó | Xem `getCause()` và log lỗi gốc bên ghi |

`ClassNotFoundException` không phải một trong ba loại chính và thuộc nhánh ngoại lệ khác `IOException`. `IOException`/`EOFException` mang thông tin riêng; không nên đổi mọi lỗi đọc dữ liệu thành `StreamCorruptedException` trong catch.

## 8. Quy trình chẩn đoán và sửa lỗi theo thứ tự

1. **Xác định thao tác thất bại.** Ghi (`writeObject`), tạo reader (`new ObjectInputStream`), hay đọc (`readObject`)? Ghi stack trace đầy đủ và message, bao gồm lỗi gốc nếu có `cause`.
2. **Đối với `NotSerializableException`:** lấy tên class gây lỗi từ message, tìm trường/collection giữ instance của class đó. Phân loại dữ liệu cần lưu và tài nguyên runtime. Chuyển thành DTO serializable, thay đổi cấu trúc hoặc đánh dấu `transient` với kế hoạch tái tạo dữ liệu phù hợp.
3. **Đối với `InvalidClassException`:** xác định class từ stream, class đang nạp và UID hai bên. Kiểm tra tương thích schema, constructor của lớp cha không serializable và các thay đổi class. Thực hiện migration khi cần.
4. **Đối với `StreamCorruptedException`:** xác minh bytes nguồn có thực sự do `ObjectOutputStream` sinh ra, không bị trộn text/JSON/metadata hoặc append header lặp. Đọc/ghi vào đúng vị trí và đúng protocol.
5. **Thử trên dữ liệu tối thiểu có thể lặp lại.** Tạo test ghi → đọc với **cùng phiên bản** để kiểm tra code cơ bản, rồi dùng dữ liệu/phiên bản gây lỗi để phân biệt lỗi protocol và lỗi tương thích.
6. **Sửa nguyên nhân và thêm regression test.** Lưu fixture stream của một phiên bản cũ nếu vẫn cam kết đọc được; kiểm thử object graph có collection, null, transient, dữ liệu thiếu và luồng không hợp lệ.

Khi xử lý trong ứng dụng thật, thường nên bắt ngoại lệ ở ranh giới I/O để log đủ ngữ cảnh và trả lỗi có ý nghĩa. Không nuốt exception rồi xem đối tượng khôi phục thất bại như dữ liệu thành công; cũng không xóa file serialized ngay khi lần đầu đọc lỗi nếu chưa xác định nguyên nhân và chính sách lưu trữ.

## 9. Ngăn lỗi từ khâu thiết kế

- **Thu gọn dữ liệu lưu:** tách model trao đổi/lưu trữ khỏi entity có socket, executor, thread, connection, logger, cache; serializable không đồng nghĩa phù hợp để lưu lâu dài.
- **Quản lý phiên bản:** khai báo `serialVersionUID` có chủ đích cho class serializable, kiểm thử đọc dữ liệu cũ khi phát hành bản mới và thiết kế migration khi thay đổi bất tương thích.
- **Thống nhất protocol:** xác định rõ phiên ghi/đọc, thứ tự dữ liệu, cấu trúc thông điệp và quản lý buffer/file. Đừng dùng serialization stream như một container chung cho dữ liệu bất kỳ.
- **Quan sát lỗi:** ghi tên class, version ứng dụng, vị trí I/O, tên file/tên message và cause. Với dữ liệu nhạy cảm, không dump nguyên object/stream vào log.
- **An toàn:** Java deserialization của dữ liệu không tin cậy có thể nguy hiểm vì hành vi trong quá trình tái tạo object graph. Tránh `ObjectInputStream` trên input không tin cậy; khi bắt buộc dùng, cân nhắc `ObjectInputFilter` theo JEP 290 cùng giới hạn class, độ sâu, số tham chiếu/kích thước. Bộ lọc **không thay thế** kiểm soát nguồn dữ liệu và thiết kế protocol an toàn.

## 10. Tự kiểm tra

**Câu 1.** Class `Order` triển khai `Serializable` và chứa `List<PaymentConnector>`. `ArrayList` có thể serialize nhưng `PaymentConnector` không triển khai `Serializable`. Ghi một list có phần tử loại đó sẽ ra sao?

**Đáp án:** Có khả năng ném `NotSerializableException` khi Java đi đến phần tử `PaymentConnector`. Phải sửa dữ liệu đồ thị được ghi, không chỉ kiểu khai báo của field list.

**Câu 2.** Một class thêm field `int retries` và vẫn giữ UID. Dữ liệu cũ chắc chắn gây `InvalidClassException`?

**Đáp án:** Không. Thêm field thông thường thường là thay đổi tương thích; khi đọc dữ liệu cũ, trường mới có thể nhận giá trị mặc định `0`. Vẫn phải kiểm thử logic nghiệp vụ và các điều kiện tương thích liên quan.

**Câu 3.** Đọc file JSON qua `ObjectInputStream` báo lỗi header. Có thể sửa bằng cách ép class JSON implements `Serializable`?

**Đáp án:** Không. Dạng byte JSON không phải Java Object Serialization stream. Dùng JSON parser cho JSON, hoặc đổi bên ghi sang `ObjectOutputStream` và thống nhất định dạng ở cả hai phía.

**Câu 4.** Tại sao một file chỉ có một nửa dữ liệu không nhất thiết ném `StreamCorruptedException`?

**Đáp án:** Nếu reader cần thêm byte nhưng đã tới cuối file, `EOFException` có thể là tín hiệu trực tiếp. Ngoại lệ cụ thể phụ thuộc vị trí dữ liệu thiếu và giai đoạn giải mã.

## 11. Ghi nhớ

- `NotSerializableException` → **vấn đề object graph khi ghi**: kiểm tra lớp thật và các trường/phần tử cần serialize.
- `InvalidClassException` → **vấn đề tương thích/định nghĩa class**: kiểm tra UID, phiên bản class và lịch sử tiến hóa dữ liệu.
- `StreamCorruptedException` → **vấn đề cấu trúc object stream**: kiểm tra nguồn byte, header, offset và cách phối hợp writer/reader.

Bắt đúng loại ngoại lệ giúp khoanh vùng lỗi nhanh, nhưng giải pháp đúng phải dựa vào dữ liệu cần lưu, hợp đồng tương thích và định dạng luồng đã thiết kế.
