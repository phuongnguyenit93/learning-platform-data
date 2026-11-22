# Serialization và `serialVersionUID` khi hợp đồng ngoại lệ tùy chỉnh có yêu cầu

**Ngoại lệ tùy chỉnh trong Java có thể được tuần tự hóa (serialization)** vì `java.lang.Throwable` đã triển khai `java.io.Serializable`. Tuy nhiên, việc một exception *có thể* đi qua cơ chế Java Object Serialization không đồng nghĩa mọi ứng dụng *nên* ghi ngoại lệ đó thành byte, lưu lâu dài hoặc gửi qua mạng. Nếu thật sự có **hợp đồng** lưu/truyền đối tượng exception bằng Java serialization, cần thiết kế kỹ **`serialVersionUID`, cấu trúc các field, cause, suppressed exceptions, tính tương thích phiên bản và an toàn deserialization**.

Bài học tập trung vào câu hỏi: **Khi nào việc serialization là một phần hợp đồng của custom exception, và `serialVersionUID` phải được xử lý như thế nào?** Các ví dụ độc lập dùng Java 17 trở lên.

Tóm tắt trước:

- Kế thừa `Exception` hoặc `RuntimeException` đều dẫn tới một lớp con của `Throwable`, nên **đều nằm trong hệ phân cấp hỗ trợ `Serializable`**.
- `serialVersionUID` là **mã phiên bản của lớp serializable** dùng trong kiểm tra tương thích dữ liệu khi deserialization; nó **không** phải ID của một object hay mã lỗi nghiệp vụ.
- **Không phải lúc nào custom exception cũng cần công bố hợp đồng serialization.** Chỉ vì IDE gợi ý “add `serialVersionUID`” không có nghĩa chương trình phải lưu/gửi exception giữa các tiến trình.
- Khi thực sự cần tương thích giữa các phiên bản của **cùng lớp**, việc khai báo rõ `private static final long serialVersionUID` và duy trì serialized form có thể có giá trị.
- **Giữ cùng `serialVersionUID` chưa bảo đảm mọi thay đổi đều tương thích.** Cấu trúc lớp, kiểu field, hierarchy, logic serialization tùy chỉnh và các lớp trong đồ thị đối tượng vẫn quan trọng.
- **Không deserialize byte không đáng tin cậy bằng `ObjectInputStream` một cách tùy tiện**; Java native serialization có rủi ro bảo mật và ràng buộc phiên bản lớn. Với API công khai, thường nên chuyển thông tin lỗi thành DTO/schema rõ ràng.

## 1. Bắt đầu từ hệ phân cấp: custom exception đã `Serializable`

Hệ phân cấp liên quan:

```text
java.lang.Object
    └── java.lang.Throwable implements java.io.Serializable
          ├── java.lang.Error
          └── java.lang.Exception
                ├── CustomCheckedException
                └── java.lang.RuntimeException
                      └── CustomUncheckedException
```

Nếu khai báo:

```java
class ImportFailedException extends Exception {
    ImportFailedException(String message) {
        super(message);
    }
}

class WorkflowFailureException extends RuntimeException {
    WorkflowFailureException(String message) {
        super(message);
    }
}
```

đây là **hai class minh họa**, không có `main`. Cả hai kế thừa khả năng Java serialization theo `Throwable`; không cần viết thêm `implements Serializable` chỉ để bật tính năng ấy.

Điều này **không** thay đổi quy tắc checked/unchecked:

- `ImportFailedException` là **checked exception**; caller phải catch hoặc declare khi có thể ném.
- `WorkflowFailureException` là **unchecked exception**; caller không bị bắt buộc bởi compiler.
- **Cả hai** có thể được truyền cho `ObjectOutputStream.writeObject` về mặt kiểu, nhưng quá trình ghi có thể thất bại nếu đồ thị object chứa field không serializable hoặc gặp điều kiện khác.

**Phân loại checked/unchecked và khả năng serialization là hai trục khác nhau.** Không chọn `extends RuntimeException` để “dễ serialize”, cũng không chọn `extends Exception` chỉ vì muốn lưu ngoại lệ.

## 2. Serialization nghĩa là gì trong bài này?

**Java Object Serialization** là cơ chế ghi trạng thái của một đồ thị object được hỗ trợ thành một định dạng byte có thể đọc lại bởi `ObjectInputStream` trong một môi trường Java tương thích.

Hai API tiêu biểu:

- `ObjectOutputStream.writeObject(object)`: ghi object/đồ thị object.
- `ObjectInputStream.readObject()`: đọc lại object từ stream và có thể tạo các instance Java phù hợp.

Ví dụ khung:

```java
try (ObjectOutputStream out =
             new ObjectOutputStream(outputStream)) {
    out.writeObject(exception);
}
```

Đây là **mã minh họa**, cần `outputStream`, `exception` và các import được khai báo, đồng thời phải xử lý/khai báo checked `IOException`. Việc ghi object **không** đồng nghĩa một exception được `throw`. Ghi một object ngoại lệ là thao tác dữ liệu; Java không tự ném exception ấy chỉ vì serialize nó.

Cần phân biệt:

| Hoạt động | Mục đích | Có liên quan trực tiếp đến `serialVersionUID` không? |
| --- | --- | --- |
| `throw new MyException(...)` | Báo lỗi trên call stack hiện tại | Không phải thao tác đọc/ghi serialized form |
| `catch (MyException e)` | Bắt một exception đang lan truyền | Không |
| `e.getMessage()` | Đọc thông điệp | Không |
| `e.printStackTrace()` | In thông tin chẩn đoán | Không |
| `writeObject(e)` | Serialize đồ thị object | Có, khi ghi mô tả lớp serializable |
| `readObject()` | Deserialize đồ thị object | Có, khi kiểm tra tương thích lớp với dữ liệu đã ghi |

Không nên gộp “log exception”, “gửi message cho người dùng” và “Java serialize object Throwable” thành một khái niệm. Đa số hoạt động log và API response **không cần** native Java serialization.

## 3. `serialVersionUID` là gì?

Trong Java serialization, lớp serializable có một **serial version UID** kiểu `long`. Khi deserialize, Java sử dụng thông tin của lớp trong stream và mô tả lớp ở phía đọc để kiểm tra khả năng tương thích, trong đó có việc so sánh `serialVersionUID` đối với những lớp áp dụng cơ chế phiên bản thông thường.

Khai báo chuẩn:

```java
private static final long serialVersionUID = 1L;
```

Nên viết field này **bên trong chính lớp custom exception** nếu bạn quyết định chủ động quản lý phiên bản serialized form.

Giải thích từng thành phần:

- `private`: đây là chi tiết triển khai của lớp, không phải dữ liệu API mà caller thường truy cập.
- `static`: thuộc lớp, không thuộc từng instance exception.
- `final`: là hằng số; không thay đổi theo object.
- `long`: kiểu yêu cầu cho giá trị serial version UID.
- `1L`: một giá trị minh họa, **không bắt buộc phải là một số ngẫu nhiên hay duy nhất trên toàn ứng dụng**.

Một số điều **serialVersionUID không phải**:

- Không phải “mã lỗi” để hiển thị cho người dùng.
- Không phải version của thư viện theo Semantic Versioning.
- Không phải định danh duy nhất của từng instance Throwable.
- Không tự động nâng lên khi build phiên bản phần mềm mới.
- Không mã hóa hay bảo vệ dữ liệu.
- Không bảo đảm lớp tương thích khi schema thay đổi.
- Không bắt buộc có cùng giá trị giữa tất cả các class cùng nhánh exception.

Mỗi lớp serializable trong phân cấp có thể có **UID của chính lớp đó**. UID khai báo ở lớp cha không thay thế việc quản lý serialized form của lớp con khi lớp con có hợp đồng riêng.

## 4. Khi nào thực sự cần quan tâm tới UID?

Nên xem xét kỹ khi **hợp đồng đã xác định** rằng object exception cần được Java serialize và **đọc lại sau đó**, nhất là qua các phiên bản chương trình khác nhau. Ví dụ:

1. Một thành phần nội bộ đang lưu các Throwable bằng `ObjectOutputStream` và cần phục hồi chúng bằng `ObjectInputStream`.
2. Một hệ thống Java-to-Java cũ có giao thức thực tế dựa trên Java serialization, nơi exception được truyền dưới dạng object serializable.
3. Một chức năng lưu trạng thái hoặc cơ chế kiểm thử tương thích đã được thiết kế sử dụng serialized object của exception.
4. Một thư viện có cam kết rằng **serialized form của custom exception** ổn định giữa các bản phát hành nhất định.

Trong những tình huống đó, cần xác định **phạm vi phiên bản phải tương thích, thời gian lưu dữ liệu, chính sách nâng cấp và phạm vi field cần ổn định**.

Ngược lại, nếu exception chỉ:

- được `throw`/`catch` trong cùng chương trình,
- được ghi vào log,
- được ánh xạ thành HTTP status và error response,
- được trình bày trong một CLI,
- hoặc được dùng trong unit test thông thường,

thì **không nhất thiết có yêu cầu runtime về Java serialization**. Việc chủ động khai báo UID vẫn có thể hợp lý để giữ một quy ước code hoặc tránh cảnh báo công cụ, nhưng không nên tuyên bố “đã hỗ trợ lưu/gửi exception tương thích lâu dài” chỉ nhờ thêm một dòng UID.

## 5. Compiler có tự tạo UID nếu không khai báo không?

Có cơ chế tạo **UID mặc định** cho lớp serializable khi lớp không khai báo một `serialVersionUID` hợp lệ. Giá trị mặc định được tính từ thông tin cấu trúc của lớp theo thuật toán serialization của Java.

Nhưng giá trị tính tự động có thể **thay đổi khi mã nguồn hoặc chữ ký lớp thay đổi**, kể cả những thay đổi không có vẻ là “thay đổi dữ liệu” đối với người viết. Điều đó có thể khiến dữ liệu đã serialize bằng phiên bản cũ không đọc được bởi phiên bản mới.

Vì vậy, với những class thật sự cam kết tương thích serialized form, **khai báo rõ UID** giúp việc quản lý phiên bản có chủ đích hơn:

```java
public class JobFailureException extends Exception {
    private static final long serialVersionUID = 1L;

    public JobFailureException(String message) {
        super(message);
    }
}
```

Đây là **một class hoàn chỉnh nhưng không có `main`**, nên lưu thành `JobFailureException.java`. Phải phân biệt:

- UID **ổn định** chỉ giúp vượt qua một trong các kiểm tra tương thích.
- Để tiếp tục tương thích, những thay đổi serialized form cũng phải tuân thủ các quy tắc Java serialization.
- Cố giữ UID của một thay đổi **không tương thích** không làm object trở nên tự tương thích.

Nếu không có yêu cầu persistence/compatibility thật, không cần thiết kế cơ chế migration chỉ vì IDE đã phát ra cảnh báo `serial`.

## 6. Một custom exception có UID nên khai báo như thế nào?

Ví dụ checked exception chứa message, cause và mã lỗi đơn giản:

```java
public class DataLoadException extends Exception {
    private static final long serialVersionUID = 1L;

    private final String errorCode;

    public DataLoadException(String errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
    }

    public DataLoadException(
            String errorCode, String message, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
```

Đây là **một class Java độc lập** để đặt trong `DataLoadException.java`. `Throwable` đã hỗ trợ Serializable, vì vậy class không cần ghi `implements Serializable` lần nữa.

Các quyết định thiết kế:

- `errorCode` là `String` và serializable.
- `message` và `cause` được chuyển cho superclass.
- `serialVersionUID = 1L` chủ động đánh dấu phiên bản serialized form của class hiện tại.
- `getErrorCode()` là hợp đồng ứng dụng, **không** phải cơ chế phiên bản Java serialization.
- Các field được thêm về sau cần xem xét tương thích, chứ không mặc định đổi UID sau mọi commit.

Nếu class dùng `enum` làm error code thì enum có cơ chế serialization đặc thù; các tên enum và chính sách tiến hóa enum vẫn phải được cân nhắc. Mã lỗi trên API công khai còn cần ổn định theo hợp đồng nghiệp vụ, độc lập với UID.

## 7. Ví dụ Java 17 chạy được: round-trip một custom exception

Ví dụ này chứng minh message, mã lỗi, cause và suppressed exception có thể được ghi rồi đọc lại khi toàn bộ đồ thị object phù hợp với Java serialization.

Lưu thành **`CustomExceptionRoundTripDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

class ImportException extends Exception {
    private static final long serialVersionUID = 1L;

    private final String code;

    ImportException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    String getCode() {
        return code;
    }
}

public class CustomExceptionRoundTripDemo {
    static byte[] encode(ImportException error) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out =
                     new ObjectOutputStream(bytes)) {
            out.writeObject(error);
        }
        return bytes.toByteArray();
    }

    static ImportException decode(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            return (ImportException) in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        IOException source = new IOException("Tệp không đọc được");
        ImportException original = new ImportException(
                "IMPORT_IO", "Nhập dữ liệu thất bại", source);
        original.addSuppressed(
                new IllegalStateException("Cleanup thất bại"));

        byte[] data = encode(original);
        ImportException restored = decode(data);

        System.out.println("Cùng instance: " + (original == restored));
        System.out.println("Mã lỗi: " + restored.getCode());
        System.out.println("Message: " + restored.getMessage());
        System.out.println("Cause type: "
                + restored.getCause().getClass().getSimpleName());
        System.out.println("Cause message: "
                + restored.getCause().getMessage());
        System.out.println("Suppressed: "
                + restored.getSuppressed().length);
        System.out.println("Lỗi phụ: "
                + restored.getSuppressed()[0].getMessage());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 --release 17 CustomExceptionRoundTripDemo.java
java CustomExceptionRoundTripDemo
```

**Stdout chính xác** với các lớp từ ví dụ và stream chỉ chứa dữ liệu do chương trình tự tạo:

```text
Cùng instance: false
Mã lỗi: IMPORT_IO
Message: Nhập dữ liệu thất bại
Cause type: IOException
Cause message: Tệp không đọc được
Suppressed: 1
Lỗi phụ: Cleanup thất bại
```

Giải thích:

1. `original` là instance `ImportException` có field `code`, message và cause.
2. `addSuppressed` gắn thêm một Throwable phụ.
3. `ObjectOutputStream` ghi đồ thị object vào byte array.
4. `ObjectInputStream` đọc một **instance mới** tương ứng với dữ liệu serialized.
5. `original == restored` là `false`, vì hai instance không giống identity.
6. Message, field `code`, cause và suppressed được phục hồi theo cơ chế mặc định trong tình huống này.
7. **Không có lệnh `throw restored`** trong chương trình. Deserialization không đồng nghĩa ném lỗi đã phục hồi.

Đoạn `main throws Exception` ở đây chỉ để tập trung vào cơ chế serialization; trong ứng dụng thực, ranh giới sẽ cần chính sách bắt và xử lý lỗi I/O, dữ liệu sai định dạng, thiếu class hoặc dữ liệu không đáng tin.

## 8. Deserialize không “chạy lại” lần lỗi ban đầu

Một đối tượng exception được deserialize là **dữ liệu đã được phục hồi**, không phải sự kiện lỗi đang tự xảy ra lại.

Nói rõ:

- `getMessage()` trên object phục hồi đọc message đã được serialize.
- `getCause()` có thể tham chiếu đến cause object đã được phục hồi.
- `getSuppressed()` có thể chứa các object được phục hồi.
- `getStackTrace()` có thể cung cấp dữ liệu trace đã ghi tại lần lỗi cũ, tùy serialized form và cơ chế Throwable.
- `readObject()` **không tự thực hiện `throw restored`**.
- Nếu sau đó mã chủ động `throw restored`, nó ném object ấy; thông thường lệnh `throw` không tự làm mới stack trace của object.

Stack trace đọc lại thường **không** chỉ tới thời điểm decode. Nó là dữ liệu của lỗi đã được ghi và serialize trước đó, trừ khi code/JVM có hành vi đặc biệt như `fillInStackTrace()` hoặc `setStackTrace()`.

Vì vậy không nên dùng stack trace đã deserialize để suy luận rằng chương trình ở thời điểm hiện tại vừa chạy qua các frame cũ.

## 9. Khi nào xuất hiện `InvalidClassException`?

`java.io.InvalidClassException` là một loại `ObjectStreamException` và có thể xảy ra khi Java nhận thấy **lớp ở phía đọc không tương thích với lớp được mô tả trong stream**.

Tình huống phổ biến:

1. Phiên bản V1 của `com.example.DataLoadException` được serialize với UID = `1L`.
2. Phiên bản V2 ở phía đọc có cùng tên lớp nhưng UID = `2L`.
3. Khi `ObjectInputStream` cố phục hồi object, việc kiểm tra phiên bản có thể dẫn tới **`InvalidClassException`** do UID không khớp.

Đây là **mô tả tình huống qua hai phiên bản**, không phải một chương trình nguồn đơn chạy đồng thời hai định nghĩa trùng tên. Trong cùng một class loader, không thể tùy ý định nghĩa hai phiên bản có cùng binary name theo cách chỉ đặt hai class cùng tên vào một file.

Ví dụ khai báo V1 và V2 để hiểu vấn đề:

**V1** – `DataLoadException.java` được build/phân phối ở bản đầu:

```java
public class DataLoadException extends Exception {
    private static final long serialVersionUID = 1L;

    public DataLoadException(String message) {
        super(message);
    }
}
```

**V2** – class **cùng binary name** ở bản mới:

```java
public class DataLoadException extends Exception {
    private static final long serialVersionUID = 2L;

    public DataLoadException(String message) {
        super(message);
    }
}
```

Đây là **hai phiên bản thay thế**, không được đặt cùng lúc trên cùng classpath. Dữ liệu được ghi bằng V1 rồi đọc bởi V2 có thể không qua được kiểm tra UID vì phiên bản stream và local khác nhau.

Một thông báo lỗi thực tế thường đề cập `stream classdesc serialVersionUID` và `local class serialVersionUID`. Tên class, đường dẫn và số UID hiển thị tùy tình huống; không phụ thuộc nguyên văn message exception để quyết định nghiệp vụ.

**Không nên tăng UID chỉ vì tăng phiên bản phát hành.** Khi muốn duy trì tương thích của serialized form, cần có lý do để giữ hoặc thay đổi UID dựa trên hợp đồng tương thích, không theo lịch phiên bản một cách máy móc.

## 10. UID khớp cũng có thể vẫn không đọc được dữ liệu cũ

Giả sử giữ `serialVersionUID = 1L` qua nhiều phiên bản. Điều đó **không bảo đảm** mọi thay đổi lớp tương thích với object stream cũ.

Một số thay đổi cần đặc biệt thận trọng:

- **Đổi kiểu field** đã được ghi trong serialized form có thể gây không tương thích.
- **Đổi tên hoặc package của class** có thể thay đổi binary name cần giải quyết khi đọc.
- **Thay đổi quan hệ kế thừa serializable/non-serializable** hoặc chuyển giữa cơ chế `Serializable` và `Externalizable` có các quy tắc đặc thù.
- **Thêm logic `writeObject`/`readObject` tùy chỉnh** không nhất quán giữa hai phiên bản có thể làm đọc sai dữ liệu, dù UID vẫn giữ.
- **Thay đổi bất biến (invariant) của class** có thể khiến trạng thái phục hồi trước đó không còn hợp lệ.
- **Thay đổi field thành kiểu không serializable** có thể làm ghi object thất bại với `NotSerializableException`.
- **Lớp của cause/field lồng bên trong** không còn tồn tại hoặc thay đổi không tương thích có thể khiến cả đồ thị không phục hồi được.

Đổi UID cũng **không tự chuyển dữ liệu** sang schema mới. Cơ chế version/migration là trách nhiệm riêng của người thiết kế giao thức lưu trữ.

Nếu serialized form thực sự là hợp đồng, cần xác định cụ thể **được phép thay đổi field nào**, đọc ngược từ phiên bản nào, và có test dùng dữ liệu thật của phiên bản cũ hay không.

## 11. Thêm field có luôn phá tính tương thích?

Trong nhiều trường hợp **default serialization** của Java, việc thêm một field serializable mới trong class có cùng UID là một **thay đổi có thể tương thích theo hướng đọc dữ liệu cũ bằng phiên bản mới**. Field mới không tồn tại trong stream cũ và có thể nhận **giá trị mặc định** khi deserialization.

Ví dụ tư duy:

**V1:**

```java
class ImportFailure extends Exception {
    private static final long serialVersionUID = 1L;
    String code;
}
```

**V2:**

```java
class ImportFailure extends Exception {
    private static final long serialVersionUID = 1L;
    String code;
    String category;
}
```

Đây là **hai phiên bản thay thế**, không phải hai class được biên dịch cùng tên trong một bộ nguồn. Nếu V2 đọc dữ liệu V1 theo quy tắc mặc định và không có thay đổi không tương thích khác, field `category` có thể nhận **`null`**, vì stream V1 không có dữ liệu cho field này.

Tương tự:

- Field `int` mới có thể nhận `0` khi không có dữ liệu.
- Field `boolean` mới có thể nhận `false`.
- Field tham chiếu mới có thể nhận `null`.

**Điểm dễ sai:** đừng giả định initializer trong mã nguồn V2 tự chạy và thay các giá trị đó trong deserialization mặc định. Đối với các lớp serializable được phục hồi, constructor và field initializer của chính lớp serializable **không được thực thi như quá trình `new` bình thường**. Những constructor liên quan phần superclass đầu tiên không serializable tuân theo quy tắc riêng.

Nếu `category` mới là bắt buộc, cần thiết kế logic phục hồi/kiểm tra phiên bản cũ hoặc duy trì schema cụ thể. **Chỉ giữ UID cũ không làm xuất hiện dữ liệu chưa từng được ghi**.

## 12. Xóa một field có luôn phá tính tương thích?

Với default Java serialization, việc **xóa một field** đôi khi vẫn cho phép đọc dữ liệu cũ bằng class mới: dữ liệu field không còn hiện diện trong class đọc có thể bị bỏ qua theo cơ chế ánh xạ field.

Nhưng không được suy ra mọi trường hợp đều an toàn:

- Có thể mất thông tin cần thiết cho logic phục hồi hoặc chẩn đoán.
- Code `readObject` tùy chỉnh có thể phụ thuộc field cũ.
- Các lớp lồng nhau hoặc thay đổi kiểu khác có thể vẫn gây không tương thích.
- Hợp đồng API của getter có thể đã thay đổi dù dữ liệu đọc được.

Ví dụ: bỏ field `requestId` để tránh ghi dữ liệu nhạy cảm là một quyết định về bảo mật và schema, không chỉ một thay đổi trình biên dịch. Cần đánh giá mọi nơi đọc object cũ và nơi sử dụng field ấy.

Với dữ liệu cần tồn tại lâu dài, **tập hợp các thay đổi tương thích phải được kiểm chứng bằng test cross-version**, không dựa duy nhất vào suy đoán rằng Java sẽ bỏ qua phần dư.

## 13. Không phải field nào trong custom exception cũng serializable

Kế thừa `Throwable` có nghĩa class có thể tham gia Java serialization, **không có nghĩa mọi field instance mà bạn thêm đều tự serializable**.

Ví dụ một exception nắm tham chiếu tới `Thread`:

```java
class WorkerFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final Thread workerThread;

    WorkerFailure(String message, Thread workerThread) {
        super(message);
        this.workerThread = workerThread;
    }
}
```

Đây là **class minh họa**. `Thread` không triển khai `Serializable`, vì vậy nếu default serialization cố ghi field `workerThread` khác `null`, nó có thể ném `NotSerializableException`.

Hệ quả quan trọng:

- **Có UID không sửa được lỗi field không serializable**.
- Không nên đưa những object như thread, socket, service/client, lock, callback hoặc một đối tượng hạ tầng sống vào serialized form của exception chỉ để debug.
- Nếu cần lưu thông tin nhận diện, dùng dữ liệu có cấu trúc như `String workerName`, `String operationId` hoặc mã lỗi thay vì object đang hoạt động.
- Nếu field chỉ dùng lúc runtime, cân nhắc `transient`; nhưng phải chấp nhận dữ liệu ấy **không được phục hồi**.

Các field mới của custom exception cần được review như một **data model** nếu class tham gia serialization; không chỉ đơn giản thêm bất cứ thứ gì tiện dùng.

## 14. Ví dụ chạy được: `NotSerializableException` từ field

Lưu **`NonSerializableFieldDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.NotSerializableException;
import java.io.ObjectOutputStream;
import java.io.IOException;

class TaskFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final Thread thread;

    TaskFailure(String message, Thread thread) {
        super(message);
        this.thread = thread;
    }
}

public class NonSerializableFieldDemo {
    public static void main(String[] args) throws IOException {
        TaskFailure error =
                new TaskFailure("Task thất bại", Thread.currentThread());

        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(error);
            System.out.println("Không tới dòng này");
        } catch (NotSerializableException e) {
            System.out.println("Không thể serialize: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 NonSerializableFieldDemo.java
java NonSerializableFieldDemo
```

**Stdout chính xác** trên Java 17 thông thường:

```text
Không thể serialize: java.lang.Thread
```

Dù `TaskFailure extends RuntimeException` và khai báo UID rõ ràng, `Thread` không thể ghi bằng default serialization. `NotSerializableException` mô tả lớp không serializable gặp trong đồ thị object.

Đây là **lỗi ở thao tác serialize**, không phải `TaskFailure` tự được ném. Chương trình bắt `NotSerializableException` do `ObjectOutputStream` phát sinh.

Nếu sau này bỏ field `thread` hoặc thay nó bằng `String threadName`, cần cân nhắc serialized form mới và khả năng đọc dữ liệu cũ nếu đã công bố hợp đồng.

## 15. Field `transient`: giữ dữ liệu chỉ cho runtime, không đưa vào stream

Từ khóa `transient` đánh dấu một field instance **không tham gia default serialization** của class. Điều này hữu ích khi field giữ thông tin tạm thời, nhạy cảm hoặc object không serializable.

Ví dụ:

```java
class JobFailure extends Exception {
    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private transient String debugNote;

    JobFailure(String errorCode, String debugNote) {
        super("Job thất bại");
        this.errorCode = errorCode;
        this.debugNote = debugNote;
    }
}
```

Đây là **class minh họa**, chưa có `main`. Sau deserialize mặc định:

- `errorCode` có thể được phục hồi.
- `debugNote` **không được lưu**, nên trường tham chiếu thường nhận `null`.
- `serialVersionUID` không phải field instance của object, và không được lưu như trạng thái instance thông thường.

Không dùng `transient` để che việc class không có thiết kế schema: nếu một field thực sự là bất biến bắt buộc cho xử lý sau khi phục hồi, loại bỏ nó khỏi serialized form có thể tạo object ở trạng thái thiếu dữ liệu.

Bảo mật cũng không chỉ là đánh dấu `transient`: detail message, cause, suppressed exceptions hoặc các field khác vẫn có thể chứa thông tin nhạy cảm.

## 16. Ví dụ chạy được: dữ liệu `transient` biến mất sau deserialize

Lưu **`TransientExceptionDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

class RemoteTaskException extends Exception {
    private static final long serialVersionUID = 1L;

    private final String code;
    private transient String localDebug;

    RemoteTaskException(String code, String localDebug) {
        super("Remote task failed");
        this.code = code;
        this.localDebug = localDebug;
    }

    String getCode() {
        return code;
    }

    String getLocalDebug() {
        return localDebug;
    }
}

public class TransientExceptionDemo {
    public static void main(String[] args) throws Exception {
        RemoteTaskException original =
                new RemoteTaskException("TASK_01", "trace chỉ ở máy này");

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
        }

        RemoteTaskException copy;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(buffer.toByteArray()))) {
            copy = (RemoteTaskException) in.readObject();
        }

        System.out.println("Code: " + copy.getCode());
        System.out.println("Message: " + copy.getMessage());
        System.out.println("Debug null: " + (copy.getLocalDebug() == null));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 TransientExceptionDemo.java
java TransientExceptionDemo
```

**Stdout chính xác:**

```text
Code: TASK_01
Message: Remote task failed
Debug null: true
```

Lý do `debugNote`/`localDebug` không tồn tại sau phục hồi là **chính sách `transient`**, không phải lỗi `serialVersionUID`. Mã ứng dụng dùng object phục hồi phải chấp nhận và xử lý trạng thái đó.

## 17. Cause, suppressed exceptions và stack trace cũng ảnh hưởng hợp đồng

`Throwable` lưu nhiều dữ liệu hơn message. Một custom exception có thể mang:

- **Detail message**: thông qua `getMessage()`.
- **Cause**: tham chiếu exception nguyên nhân, truy cập `getCause()`.
- **Suppressed exceptions**: mảng lỗi phụ, truy cập `getSuppressed()`.
- **Stack trace**: dữ liệu các stack frame khi object được tạo/điền trace hoặc bị sửa theo API.
- **Field custom**: mã lỗi, loại tác vụ, tham số, ngữ cảnh chẩn đoán.

Khi dùng Java serialization mặc định trong một tình huống được hỗ trợ, các đối tượng liên quan như cause và suppressed có thể thuộc **đồ thị object cần được ghi/đọc**.

Cần chú ý:

1. Một cause cũng là `Throwable` nhưng có thể là lớp con tùy chỉnh với field không serializable.
2. Một suppressed exception cũng có thể chứa các field tùy chỉnh và các quan hệ cause/suppressed tiếp theo.
3. Stack trace có thể chứa thông tin môi trường và vị trí source của nơi lỗi được tạo, **không phải** stack hiện tại khi decode.
4. Object đọc lại không tự trải qua một lần thất bại mới.
5. Các trạng thái exception đặc biệt (tắt suppression, tắt writable stack trace) có thể ảnh hưởng dữ liệu quan sát được.
6. Việc serialization thành công không phải bằng chứng rằng dữ liệu đủ an toàn để hiển thị cho người dùng.

Không kiểm thử chỉ message nếu hợp đồng đã hứa có mã lỗi/cause/suppressed; cần test những phần dữ liệu được cam kết.

## 18. `serialVersionUID` của custom subclass khác `serialVersionUID` của `Throwable`

`Throwable` là một class serializable có serialized form của riêng nó. Lớp exception do bạn tạo **cũng có mô tả lớp và UID riêng** theo cơ chế Java serialization.

Ví dụ:

```java
class BaseImportException extends Exception {
    private static final long serialVersionUID = 1L;
}

class CsvImportException extends BaseImportException {
    private static final long serialVersionUID = 2L;
}
```

Đây là **hai class minh họa**, không có `main`. Không có quy tắc bắt buộc hai UID giống nhau hay bắt buộc chúng phải khác nhau. Mỗi UID liên quan tới **serialized form của chính lớp tương ứng**, không phải một hệ thống đánh số phiên bản chung.

Nếu `CsvImportException` có field riêng, serialized form của nó cần được quản lý phù hợp. Đổi serialized form của lớp cha cũng có thể ảnh hưởng khả năng phục hồi một object lớp con.

**Không được suy luận rằng vì superclass đã có UID nên lớp con khỏi phải xem xét hợp đồng của mình.** Đồng thời, không cần tạo một hệ thống “UID theo cây” nếu chẳng có yêu cầu đọc object giữa các phiên bản.

## 19. Lệnh `serialver` dùng để xem UID

JDK cung cấp công cụ **`serialver`** để tra cứu `serialVersionUID` của một class serializable mà JDK có thể load.

Ví dụ với class đã compile:

```bash
javac --release 17 JobFailureException.java
serialver JobFailureException
```

Đây là **lệnh minh họa**, giả định file `JobFailureException.java` có class đã được trình bày ở phần trước và JDK cung cấp `serialver` trên `PATH`.

Nếu class nằm trong package, truyền **tên đầy đủ** và đặt classpath phù hợp:

```bash
serialver -classpath build/classes com.example.JobFailureException
```

Đây là ví dụ sử dụng cú pháp CLI, không mặc định đường dẫn `build/classes` tồn tại trong mọi dự án.

Công cụ có thể giúp kiểm tra UID đang được công nhận, nhưng **không thể thay thế việc kiểm thử serialization/deserialization giữa hai phiên bản**. Hai class có UID giống nhau vẫn có thể khác biệt về schema hay hành vi sau phục hồi.

Đừng dùng kết quả `serialver` như một mã lỗi nghiệp vụ, đừng chép một UID ngẫu nhiên từ class khác vào chỉ vì muốn “đồng bộ”.

## 20. Có nên tăng UID mỗi lần thay đổi class?

**Không phải lúc nào cũng tăng.** Đây là hiểu lầm lớn.

Một chính sách thực tế:

- Nếu class không công bố hợp đồng serialization bền vững: có thể dùng UID cố định theo quy ước, hoặc chưa cần quản lý tương thích dữ liệu giữa các bản.
- Nếu class cam kết **tương thích ngược**, giữ UID thích hợp trong phạm vi các thay đổi serialized form được phép, đồng thời test dữ liệu từ phiên bản trước.
- Nếu có thay đổi thật sự **phá vỡ khả năng phục hồi** và chính sách là từ chối stream cũ, thay đổi UID có thể là một cách bộc lộ việc không tương thích; vẫn cần cân nhắc migration và quy trình nâng cấp.
- Nếu dữ liệu phải được duy trì dù class đổi sâu, đừng trông chờ UID đơn lẻ: thiết kế schema/versioning ngoài hoặc cách đọc chuyển đổi dữ liệu có chủ đích.

Số `1L` không biểu thị “ứng dụng phiên bản 1.0”. Không có quy tắc Java yêu cầu khi ứng dụng lên bản 2.0 thì mọi UID phải trở thành `2L`.

## 21. Serialization compatibility khác API compatibility

Một class có thể:

- **Biên dịch với code caller cũ** nhưng không đọc được object bytes cũ.
- **Đọc được object bytes cũ** nhưng hành vi public API đã thay đổi khiến caller không còn hoạt động đúng.
- Có `serialVersionUID` khớp nhưng thiếu field bắt buộc sau khi deserialize.
- Có message/cause phục hồi được nhưng mất một field `transient` mà logic nghiệp vụ lại phụ thuộc.

Ví dụ một bản cập nhật đổi tên getter `getCode()` thành `code()` có thể gây lỗi cho mã Java gọi API dù serialized form không đổi. Ngược lại, thay đổi kiểu field riêng tư có thể ảnh hưởng serialization dù chữ ký public gần như giữ nguyên.

Vì vậy cần hai nhóm kiểm thử khác nhau:

| Loại kiểm thử | Câu hỏi |
| --- | --- |
| API/source compatibility | Caller cũ còn compile và sử dụng được không? |
| Serialization compatibility | Dữ liệu byte được ghi bởi bản cũ có đọc được ở bản mới không? |
| Behavioral compatibility | Object phục hồi có còn tuân thủ ý nghĩa và bất biến hợp đồng không? |
| Security compatibility | Nội dung dữ liệu có còn an toàn và được phép phục hồi ở bối cảnh mới không? |

**UID chỉ phục vụ một phần của hàng thứ hai.**

## 22. Vì sao không nên dùng Java serialization làm định dạng public API cho exception?

Trong hệ thống hiện đại, nhiều ứng dụng cần gửi thông tin lỗi qua HTTP, message queue hoặc lưu nhật ký dài hạn. Mục tiêu thường là **gửi một mô tả có cấu trúc về lỗi**, không phải truyền toàn bộ đối tượng Java `Throwable`.

Với native Java serialization, người nhận có thể bị ràng buộc vào:

- Binary name/package và classpath Java của phía gửi.
- `serialVersionUID` và serialized form của nhiều class.
- Đồ thị object gồm cause/suppressed/custom fields.
- Các quy tắc tương thích Java serialization và version của thư viện.
- Rủi ro an ninh khi deserialize dữ liệu không đáng tin cậy.
- Thông tin nội bộ hoặc nhạy cảm vô tình xuất hiện trong message/stack trace.

Với API công khai, thường nên **chuyển exception thành DTO/error envelope** chứa những trường được thiết kế rõ, ví dụ:

```json
{
  "code": "IMPORT_FAILED",
  "message": "Không thể nhập dữ liệu",
  "requestId": "req-123"
}
```

Đây là **mẫu JSON**, không phải định dạng do `ObjectOutputStream` tạo. Phía nhận hiểu schema mà không cần load class Java của server. Những chi tiết kỹ thuật như stack trace, cause và suppressed thường nên ở hệ thống log/tracing bảo vệ phù hợp, không trả thẳng cho người dùng.

Java serialization không phải bị “cấm” trong mọi ứng dụng; nó chỉ cần một **bối cảnh tin cậy, hợp đồng rõ ràng và lý do thực tế**.

## 23. Mô hình thay thế: error DTO thay vì serialize `Throwable`

Khi mục tiêu chỉ là **truyền trạng thái thất bại**, tạo một dữ liệu lỗi độc lập có thể đơn giản hơn. Java 17 có `record`:

```java
record ErrorInfo(String code, String message) {
}

class ImportFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final String code;

    ImportFailure(String code, String message) {
        super(message);
        this.code = code;
    }

    ErrorInfo toErrorInfo() {
        return new ErrorInfo(code, "Không thể nhập dữ liệu");
    }
}
```

Đây là **hai loại minh họa**, không có `main`. `ErrorInfo` diễn tả dữ liệu giao tiếp được phép, trong khi `ImportFailure` vẫn giữ exception và chẩn đoán nội bộ.

`record` trong Java có cơ chế đối xử với serialization riêng khi triển khai `Serializable`; ở đây ví dụ **chỉ mô tả DTO**, không tự đưa record đó vào Java native object stream. Nếu chọn JSON hoặc giao thức khác, cần bộ mã hóa/giải mã phù hợp.

Một schema thông điệp lỗi ổn định có thể gồm: `code`, message đã rà soát, request ID và loại phản hồi. **Không đưa stack trace vào DTO công khai** chỉ vì exception object có nó.

## 24. Rủi ro bảo mật khi deserialize object không đáng tin cậy

`ObjectInputStream.readObject()` không đơn thuần đọc vài chuỗi vô hại; nó có thể kích hoạt cơ chế tạo/khôi phục các object Java và thực thi logic phục hồi của các lớp liên quan. Đồ thị object phức tạp hoặc class có hành vi deserialization nguy hiểm có thể tạo rủi ro.

Các nguyên tắc:

1. **Không deserialize dữ liệu từ người lạ hoặc mạng không tin cậy** bằng Java native serialization trừ khi có thiết kế an toàn nghiêm túc.
2. Ưu tiên **giao thức dữ liệu có schema rõ ràng** khi mục tiêu là trao đổi lỗi.
3. Nếu bắt buộc dùng Java serialization trong môi trường kiểm soát, giới hạn **loại class có thể được deserialize**, kích thước, độ sâu và số lượng tham chiếu qua cơ chế thích hợp như `ObjectInputFilter`.
4. Kiểm soát classpath, các dependency và phiên bản được phép.
5. Sau deserialize, **xác thực dữ liệu và bất biến** trước khi sử dụng trong nghiệp vụ.
6. Không coi `serialVersionUID` là cơ chế xác thực nguồn gửi hoặc chống sửa đổi dữ liệu.
7. Không lưu/hiển thị nguyên message, stack trace, cause và suppressed ở nơi không có quyền truy cập phù hợp.
8. Nếu lưu stream dài hạn, phải có chính sách lưu trữ, mã hóa khi phù hợp, xoay phiên bản và xóa dữ liệu.

**Bộ lọc deserialization là biện pháp giảm thiểu, không phải lý do để tùy tiện mở một endpoint nhận `ObjectInputStream` từ Internet.** Ví dụ round-trip trong bài chỉ xử lý byte tạo ngay trong cùng chương trình để minh họa hành vi Java.

## 25. Kiểm thử tương thích giữa các phiên bản đúng cách

Một test round-trip **trong cùng bản build** giúp xác nhận object có thể serialize và deserialize ngay lúc đó, nhưng **không đủ** để chứng minh dữ liệu từ bản cũ đọc được ở bản mới.

Một quy trình kiểm thử có ý nghĩa:

1. **Định nghĩa hợp đồng:** phiên bản nào phải đọc được stream của phiên bản nào? Có cần đọc ngược hay chỉ đọc dữ liệu cũ bằng bản mới?
2. **Tạo fixture byte từ bản phát hành thật**, bằng JDK và class của phiên bản đã công bố. Lưu fixture kiểm thử ở nơi được kiểm soát.
3. **Đọc fixture bằng bản mới**, với chính classpath, policy và filter mà ứng dụng dự kiến sử dụng.
4. Kiểm tra **message, error code, cause, suppressed** và các field thực sự nằm trong hợp đồng.
5. Kiểm tra object phục hồi **đạt bất biến**; không chỉ không ném `InvalidClassException`.
6. Kiểm thử đường lỗi: UID lệch, class thiếu, field không serializable, stream hỏng và dữ liệu vượt giới hạn.
7. Kiểm thử việc tạo object của **bản mới** rồi đọc bằng **bản cũ** chỉ nếu hợp đồng yêu cầu chiều ngược đó.
8. Ghi nhận quyết định: giữ UID, thay UID, thực hiện migration hay dừng hỗ trợ dữ liệu quá cũ.

Nếu không lưu fixture và chỉ chạy `serialize -> deserialize` bằng cùng class hiện tại, một thay đổi bất tương thích qua các bản có thể không được phát hiện.

## 26. Khi nào nên viết `readObject` / `writeObject` tùy chỉnh?

Java cho phép một số class triển khai logic serialization tùy chỉnh, chẳng hạn:

```java
private void writeObject(ObjectOutputStream out)
        throws IOException {
    out.defaultWriteObject();
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
```

Đây là **cặp phương thức minh họa**, chỉ có ý nghĩa khi được khai báo trong một lớp serializable phù hợp và import các loại `java.io`. Chúng không cần thiết nếu chỉ muốn round-trip mặc định.

Khi hợp đồng serialized form thực sự phức tạp, có thể dùng hook để kiểm soát dữ liệu hoặc kiểm tra bất biến. Nhưng:

- Mã `readObject`/`writeObject` tùy chỉnh làm **hợp đồng binary trở nên khó tiến hóa** hơn nếu thiếu tài liệu và fixture test.
- Không được quên gọi `defaultReadObject`/`defaultWriteObject` khi schema mong đợi cơ chế mặc định.
- Hook phải xét dữ liệu không hợp lệ, thiếu field, thay đổi phiên bản và an toàn deserialization.
- Mã tùy chỉnh có thể làm phát sinh `IOException` hoặc `ClassNotFoundException` đúng hợp đồng.
- Một Throwable còn có các thuộc tính superclass như cause/stack trace; thiết kế custom field không được giả định mình kiểm soát toàn bộ serialized form của superclass.

Đối với phần lớn custom exception ứng dụng, **tránh thêm logic serialization tùy chỉnh chỉ để hết cảnh báo IDE**. Nếu không cần lưu/truyền object, giữ thiết kế exception đơn giản sẽ an toàn và dễ bảo trì hơn.

## 27. Serializing một exception không phải cơ chế lưu lịch sử đáng tin tuyệt đối

Một exception là **dữ liệu chẩn đoán**, nhiều thành phần của nó gắn với thời điểm và môi trường chạy: message kỹ thuật, tên lớp, stack trace, cause và suppressed. Khi lưu thành object bytes, các chi tiết đó có thể trở nên:

- Cũ và không phản ánh code hiện tại.
- Khó đọc nếu class đã đổi hoặc bị xóa.
- Nhạy cảm vì có tên file, package, thông tin hệ thống hoặc dữ liệu người dùng.
- Khó lọc/tìm kiếm hơn một log hoặc sự kiện có schema rõ ràng.
- Không còn đầy đủ nếu các field `transient` bị bỏ hoặc suppression/stack trace bị tắt.

Nếu yêu cầu nghiệp vụ là **audit trail**, thường nên lưu event có cấu trúc: thời điểm, mã lỗi ổn định, ID tác vụ, hệ thống phát sinh và metadata cho phép. Throwable bytes có thể là dữ liệu phụ dành cho chẩn đoán nội bộ nếu được cấp quyền và có chính sách lưu trữ rõ.

Đừng dùng `serialVersionUID` thay cho một **schema version** có ngữ nghĩa trong tài liệu audit hoặc API giao tiếp.

## 28. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Chỉ exception `implements Serializable` mới ghi bằng `ObjectOutputStream`.” | `Throwable` đã triển khai `Serializable`, nên lớp con custom nằm trong hệ phân cấp đó. |
| “`extends Exception` mới Serializable; `extends RuntimeException` không.” | Cả hai đều kế thừa `Throwable`. |
| “Bất kỳ custom exception nào cũng bắt buộc khai báo UID để chạy.” | `throw`/`catch` không cần UID; Java có cơ chế UID mặc định khi serialization. |
| “Thêm `serialVersionUID` làm mọi field đều serializable.” | Không. Field chứa object không serializable vẫn có thể gây `NotSerializableException`. |
| “`serialVersionUID` là ID của từng exception instance.” | Không. Nó liên quan version của class khi serialization. |
| “Mỗi lần nâng phiên bản ứng dụng phải tăng UID.” | Không; quyết định dựa trên hợp đồng tương thích serialized form. |
| “Giữ UID giống nhau luôn đọc được mọi stream cũ.” | Không. Thay đổi schema, hierarchy và custom logic vẫn có thể không tương thích. |
| “Đổi UID không ảnh hưởng dữ liệu đã lưu.” | Có thể gây `InvalidClassException` khi đọc dữ liệu từ UID trước. |
| “Thêm field mới luôn có giá trị từ initializer khi deserialize dữ liệu cũ.” | Không. Field thiếu trong stream thường nhận giá trị mặc định theo cơ chế serialization. |
| “`transient` field tự được lưu nếu constructor gán.” | Không trong default serialization; constructor của serializable class cũng không chạy như `new` bình thường khi phục hồi. |
| “Cause/suppressed của exception luôn được copy sang một DTO/API response.” | Không. Đó là hai thiết kế khác nhau; bạn phải chủ động chọn dữ liệu. |
| “Deserialize exception nghĩa là exception ấy được ném.” | Không. `readObject` trả một object; ném là thao tác riêng. |
| “UID là cơ chế bảo mật.” | Không. Nó không xác thực và không bảo vệ stream khỏi dữ liệu độc hại. |
| “Round-trip cùng bản build bảo đảm tương thích với bản cũ.” | Không. Phải kiểm thử cross-version bằng fixture dữ liệu cũ. |
| “Đã có Throwable thì cứ serialize để gửi HTTP.” | Không. DTO/schema có cấu trúc thường phù hợp hơn cho giao tiếp công khai. |
| “`getStackTrace()` sau decode chỉ đến dòng decode.” | Thông thường nó phản ánh thông tin đã được lưu trong object; decode không tự làm mới trace. |

## 29. Câu hỏi tự kiểm tra

**1. `class MyException extends Exception` đã Serializable chưa?**  
Đã có khả năng tham gia Java serialization vì kế thừa `Throwable`, không cần lặp lại `implements Serializable`.

**2. `class MyException extends RuntimeException` có khác ở điểm đó không?**  
Không. Khác biệt checked/unchecked liên quan bắt/khai báo, không phải bản chất `Serializable`.

**3. `serialVersionUID = 1L` dùng để xác định instance exception nào?**  
Không xác định instance. Nó là phiên bản của class trong cơ chế kiểm tra serialized form.

**4. Vì sao nên khai báo UID tường minh khi có hợp đồng tương thích lâu dài?**  
Để chủ động quản lý UID của class thay vì phụ thuộc tính toán mặc định có thể đổi theo chi tiết cấu trúc class.

**5. Hai phiên bản cùng UID có luôn tương thích không?**  
Không. Cần xem schema, kiểu field, class hierarchy, các lớp trong đồ thị và logic đọc/ghi.

**6. Tăng UID cho mỗi bản phát hành có phải luôn đúng không?**  
Không. Điều đó có thể làm mất khả năng đọc dữ liệu cũ mà không đem lại lợi ích.

**7. Field custom chứa `Thread` khác `null`, default serialization có thể xảy ra lỗi gì?**  
`NotSerializableException` vì `Thread` không serializable.

**8. Field `transient` sẽ thế nào khi đọc lại bằng default serialization?**  
Không được lưu; với field tham chiếu, thường nhận `null` nếu không có cơ chế phục hồi tùy chỉnh.

**9. Đọc lại serialized exception có làm ném nó lên call stack không?**  
Không. Phải chủ động `throw` object nếu muốn ném.

**10. Cause và suppressed có được serialize trong ví dụ round-trip đã cho không?**  
Có, vì đồ thị được thiết kế gồm các Throwable serializable phù hợp; kết quả được kiểm tra bằng `getCause()` và `getSuppressed()`.

**11. Nếu deserialize object đã được tạo ở phiên bản cũ, stack trace có phải ảnh chụp call stack mới không?**  
Thông thường không. Đó là dữ liệu trace đã lưu; decode không tự chụp lại.

**12. Với API HTTP, có bắt buộc gửi `Throwable` bằng Java serialization để truyền lỗi không?**  
Không. Thường nên dùng error DTO và một giao thức có schema rõ ràng.

**13. `InvalidClassException` có thể báo điều gì?**  
Một lớp ở phía đọc không tương thích với lớp được mô tả trong stream, thường gặp khi UID lệch.

**14. Có thể dùng UID để xác thực dữ liệu đến từ một máy chủ tin cậy không?**  
Không. UID không phải chữ ký số hay cơ chế xác thực.

**15. Tại sao cần fixture từ bản cũ?**  
Vì round-trip chỉ với cùng bản build không kiểm tra được tương thích dữ liệu giữa các phiên bản.

**16. Nếu thêm field mới sau khi bản cũ đã ghi stream, giá trị của field mới sẽ thế nào?**  
Theo default serialization ở trường hợp tương thích, field vắng trong stream có thể nhận giá trị mặc định, ví dụ `null` cho tham chiếu.

**17. Một exception object có một cause custom không serializable hoàn toàn thì sao?**  
Serialization của toàn bộ đồ thị có thể thất bại vì field không serializable trong lớp cause, dù exception ngoài đã có UID.

**18. Khi nào phải nghĩ tới `ObjectInputFilter`?**  
Khi ứng dụng thực sự dùng Java deserialization và cần áp giới hạn/lọc các class có thể được phục hồi trong bối cảnh đã được đánh giá an toàn.

## 30. Checklist trước khi cam kết serialized form của custom exception

1. **Có yêu cầu Java native serialization thật không?** Nếu chỉ log hoặc trả API response, đừng tạo hợp đồng không cần thiết.
2. **Phạm vi tin cậy là gì?** Stream đến từ chính chương trình, hệ thống nội bộ đã kiểm soát hay nguồn bên ngoài?
3. **Class có khai báo UID tường minh không?** Nếu cam kết tương thích, phải quản lý UID có chủ đích.
4. **Có phân biệt UID với schema/error code của ứng dụng không?**
5. **Mỗi field instance có serializable không?** Có object sống (thread, socket, service) đang bị giữ trong exception không?
6. **Có field nên đánh dấu `transient` không?** Hệ quả sau phục hồi đã được xử lý chưa?
7. **Có dữ liệu nhạy cảm trong message/cause/suppressed/stack trace không?**
8. **Dữ liệu từ các phiên bản cũ có phải đọc được không?** Phải giữ fixture và test cross-version.
9. **Thêm/xóa/đổi kiểu field có tương thích theo hợp đồng không?**
10. **Thay đổi class name, package hoặc hierarchy có ảnh hưởng serialized form không?**
11. **Có custom `readObject`/`writeObject` không?** Có kiểm tra dữ liệu/bất biến và khả năng tương thích không?
12. **Có test cho `InvalidClassException`, `ClassNotFoundException`, `NotSerializableException` và stream hỏng không?**
13. **Có bảo vệ `ObjectInputStream` khỏi dữ liệu không đáng tin cậy không?** Đánh giá nhu cầu filter và giới hạn độ sâu/kích thước.
14. **Có thể dùng DTO/schema rõ ràng thay vì serialize toàn bộ Throwable không?**
15. **Object phục hồi có còn đúng ý nghĩa nghiệp vụ và không tự kích hoạt hành động nguy hiểm không?**
16. **Có chính sách deprecation/migration dữ liệu serialized cũ không?**
17. **Có theo dõi thay đổi của các class cause/suppressed và dependency liên quan không?**
18. **Có phân biệt hợp đồng API/source compatibility với serialization compatibility không?**
19. **Đã xác nhận serialization không bị dùng sai làm giải pháp ghi log/audit mặc định chưa?**
20. **Nếu không có hợp đồng serialization, đã tránh tạo cam kết tương thích dài hạn không cần thiết chưa?**

## 31. Kết luận

**Custom exception Java đã có khả năng Serializable thông qua `Throwable`**, bất kể checked hay unchecked. Tuy nhiên, cần tách khả năng kỹ thuật đó khỏi **yêu cầu hợp đồng**: hầu hết lỗi chỉ cần ném, bắt, log hoặc chuyển thành thông điệp có cấu trúc; không nhất thiết phải lưu/gửi Throwable bằng Java Object Serialization.

Khi hợp đồng **thật sự đòi hỏi** serialize và deserialize custom exception qua các phiên bản, hãy **khai báo và quản lý `serialVersionUID` tường minh**, hiểu serialized form của từng lớp và field, giữ message/cause/suppressed theo dữ liệu được phép, kiểm thử bằng byte fixture của phiên bản cũ và đặt an toàn deserialization lên hàng đầu.

**UID khớp chỉ là một điều kiện tương thích, không phải bảo đảm toàn phần; UID cũng không phải mã lỗi hoặc cơ chế bảo mật.** Nếu cần giao tiếp API bền vững, một error DTO/schema rõ ràng thường có ít ràng buộc hơn, dễ quản lý tương thích và an toàn hơn việc truyền toàn bộ đồ thị `Throwable`.
