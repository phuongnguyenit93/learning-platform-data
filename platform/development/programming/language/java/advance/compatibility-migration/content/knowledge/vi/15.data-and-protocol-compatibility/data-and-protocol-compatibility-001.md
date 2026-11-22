# Java serialization và vai trò của serialVersionUID

## 1. Vì sao serialization là ranh giới tương thích quan trọng?

Trong quá trình nâng JDK, framework hoặc các thư viện Java, một hệ thống có thể tiếp tục biên dịch và chạy tốt nhưng thất bại khi đọc dữ liệu được ghi bởi phiên bản cũ. Điều này đặc biệt dễ gặp nếu ứng dụng từng dùng **Java Object Serialization** để lưu object trong file, phân phối object giữa các tiến trình, truyền dữ liệu qua một số cơ chế RPC cũ, hoặc giữ object trong một cache có thể tồn tại qua lần triển khai.

Ví dụ, ứng dụng phiên bản A tạo một đối tượng `OrderSnapshot` rồi ghi xuống file bằng `ObjectOutputStream`. Sau khi triển khai phiên bản B, class `OrderSnapshot` có thêm field, đổi kiểu field hoặc sửa quan hệ kế thừa. Chương trình mới đọc lại file bằng `ObjectInputStream`. Kết quả có thể là:

- Object đọc thành công, nhưng field mới có giá trị mặc định thay vì giá trị mong đợi.
- Field cũ đã bị bỏ sẽ không được khôi phục trong object mới.
- Mã đọc ném `InvalidClassException` vì `serialVersionUID` không khớp hoặc schema không tương thích.
- Mã đọc thành công nhưng invariant nghiệp vụ bị sai vì constructor của class serializable không được gọi như khi tạo object thông thường.
- Bộ lọc deserialize mới từ chối một class hoặc object graph từng được phép đọc.
- Hai phiên bản có cùng `serialVersionUID` nhưng vẫn không hiểu đúng ý nghĩa dữ liệu của nhau.

Bởi vậy, migration cần kiểm tra **data compatibility** bên cạnh **source compatibility** và **binary compatibility**. Việc một method còn tồn tại và bytecode liên kết được không chứng minh các byte đã được ghi trước đây vẫn có thể đọc an toàn.

Bài học tập trung vào cơ chế Java serialization, ý nghĩa của `serialVersionUID`, các loại thay đổi tương thích hoặc không tương thích, cách thử nghiệm qua nhiều phiên bản và chiến lược chuyển đổi dữ liệu.

## 2. Java Object Serialization là gì?

Java Object Serialization là cơ chế lưu/truyền một đồ thị đối tượng (*object graph*) theo một định dạng stream dành riêng cho Java. Các thành phần quen thuộc:

- `java.io.Serializable`: marker interface biểu thị class cho phép cơ chế serialization xử lý theo hợp đồng của Java.
- `ObjectOutputStream`: ghi các đối tượng và tham chiếu của chúng thành stream.
- `ObjectInputStream`: đọc stream để tái tạo đối tượng.
- `serialVersionUID`: giá trị định danh phiên bản của dạng serialized class được dùng trong quá trình kiểm tra tương thích.
- `ObjectStreamClass`: mô tả thông tin serialization của một class.

`Serializable` không khai báo method cần triển khai:

~~~java
import java.io.Serializable;

public final class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final long amountInCents;

    public OrderSnapshot(String orderId, long amountInCents) {
        this.orderId = orderId;
        this.amountInCents = amountInCents;
    }

    public String orderId() {
        return orderId;
    }

    public long amountInCents() {
        return amountInCents;
    }
}
~~~

Để có thể ghi đối tượng bình thường, bản thân class và những object được tham chiếu trong các field cần serialize phải hỗ trợ serialization tương ứng. Nếu một field trỏ đến object không serializable và không được loại khỏi dạng lưu, việc ghi có thể ném `NotSerializableException`.

### 2.1. Không phải “lưu toàn bộ bộ nhớ của object”

Java serialization không phải chụp nguyên vùng heap hoặc layout bộ nhớ của JVM. Cơ chế này ghi thông tin class, dữ liệu các field được chọn và các tham chiếu theo quy tắc stream. Khi đọc, JVM tái tạo object graph từ những thông tin đó.

Với serialization mặc định:

- Các instance field phù hợp được đưa vào serialized form.
- Field `static` thuộc class, không thuộc trạng thái riêng của từng object nên không được serialize như instance data.
- Field `transient` thông thường bị loại khỏi serialized form mặc định.
- Các object được tham chiếu có thể tạo thành một đồ thị, gồm cả tham chiếu lặp và vòng.
- Stream có cơ chế handle để biểu diễn nhiều tham chiếu trỏ đến cùng một object, chứ không bắt buộc nhân bản object cho mọi tham chiếu.

Việc serialize thành công một object nhỏ không chứng minh cả object graph đủ an toàn hoặc ổn định về schema. Một field mới có thể kéo theo nhiều class khác cần được phép deserialize.

### 2.2. Serialization khác JSON hoặc mã hóa giao thức độc lập ngôn ngữ

Java Object Serialization dùng class name, metadata và quy tắc Java để tái tạo object. Nó không phải định dạng mặc định thích hợp cho mọi API web, thông điệp cross-language hoặc dữ liệu lưu trữ lâu dài.

Ngược lại, JSON, Protocol Buffers, Avro hoặc schema riêng có những quy tắc versioning khác; chúng không sử dụng `serialVersionUID` để quyết định tương thích. Không nên nhầm “object được chuyển thành bytes” với “đang dùng Java serialization”.

## 3. Ví dụ ghi và đọc một object

Ví dụ sau dùng file nội bộ **do chính ứng dụng kiểm soát**:

~~~java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SnapshotStore {
    public static void save(Path path, OrderSnapshot snapshot)
            throws IOException {
        try (ObjectOutputStream out = new ObjectOutputStream(
                Files.newOutputStream(path))) {
            out.writeObject(snapshot);
        }
    }

    public static OrderSnapshot load(Path path)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                Files.newInputStream(path))) {
            return (OrderSnapshot) in.readObject();
        }
    }
}
~~~

Code này minh họa cú pháp cơ bản, **không phải** một thiết kế an toàn mặc định để đọc dữ liệu từ người dùng hoặc mạng. `ObjectInputStream.readObject()` có thể kích hoạt việc tạo object và một số hook deserialization của những class có trong stream. Không được dùng nó để deserialize dữ liệu không tin cậy nếu chưa có mô hình bảo mật phù hợp; thường nên chọn định dạng dữ liệu khác.

Sau khi chạy `save`, file chứa dữ liệu ở dạng Java serialization stream. Khi phần mềm phiên bản mới đọc lại file, việc tái tạo object phụ thuộc vào class được nạp ở runtime và khả năng tương thích giữa mô tả class trong stream với mô tả class hiện tại.

### 3.1. Object graph và nhận dạng tham chiếu

Giả sử hai field của cùng object trỏ đến một đối tượng `Address`. Serialization có thể lưu một object `Address` và nhiều tham chiếu tới nó. Khi đọc lại, identity của các tham chiếu trong graph được giữ theo cơ chế stream.

Do đó, việc thay thế Java serialization bằng JSON đơn giản có thể làm mất identity, vòng tham chiếu hoặc cách khôi phục object graph nếu không có thiết kế rõ. Migration định dạng dữ liệu cần phân tích cả ngữ nghĩa graph, không chỉ danh sách field.

## 4. `serialVersionUID` là gì?

`serialVersionUID` là giá trị `long` dùng để định danh phiên bản của serialized form của class trong Java serialization. Class serializable thường khai báo tường minh:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class CustomerState implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String customerId;
    private int loyaltyPoints;
}
~~~

Annotation `@Serial` giúp compiler/tooling xác nhận mục đích của thành viên liên quan serialization trên các phiên bản Java hỗ trợ; nó không phải điều kiện bắt buộc để `serialVersionUID` hoạt động.

Khi deserialization, Java so sánh serial version UID của mô tả class được ghi trong stream với UID của class local mà runtime tìm thấy. Nếu hai giá trị không khớp trong trường hợp cần so khớp, có thể phát sinh `java.io.InvalidClassException`.

Ví dụ lỗi:

~~~text
java.io.InvalidClassException: example.CustomerState;
local class incompatible:
stream classdesc serialVersionUID = 1,
local class serialVersionUID = 2
~~~

Điểm cốt lõi:

> `serialVersionUID` là một **dấu kiểm tra tương thích của serialized class**, không phải bộ chuyển đổi schema, không phải version của file dữ liệu theo nghĩa nghiệp vụ, và không tự bảo đảm object mới đọc được dữ liệu cũ.

### 4.1. Giá trị `1L` có ý nghĩa đặc biệt không?

Không. `1L` chỉ là một giá trị `long` thường được chọn khi bắt đầu định nghĩa serialized form. Các class độc lập có thể cùng dùng `1L`; UID được xét cùng mô tả class, không phải một ID duy nhất toàn hệ thống.

Không có quy tắc “mỗi lần release phải tăng `serialVersionUID`”. Chỉ tăng khi chủ đích thay đổi serialized form theo cách không còn muốn nhận dữ liệu cũ hoặc khi hợp đồng compatibility yêu cầu phân định phiên bản mới.

### 4.2. Field `serialVersionUID` không phải dữ liệu instance

Đây là field `static final long` đặc biệt, có tên được serialization nhận biết. Nó không được lưu như trường dữ liệu bình thường của từng đối tượng.

Khai báo chuẩn:

~~~java
private static final long serialVersionUID = 1L;
~~~

Không đổi kiểu thành `int` hoặc biến nó thành instance field rồi kỳ vọng runtime nhận là UID hợp lệ. Nếu class có nested types serializable, mỗi class cần xem xét UID của chính nó.

## 5. UID tự sinh và vì sao nó gây rủi ro

Nếu một class serializable không khai báo `serialVersionUID`, Java có thể tính một **default serialVersionUID** từ một tập thông tin về class theo thuật toán đặc tả. Những yếu tố như tên class, modifiers, interfaces, fields, constructors và methods có thể tham gia phép tính.

Điều này có nghĩa một thay đổi mã nguồn không liên quan trực tiếp đến dữ liệu được lưu có thể khiến UID mặc định thay đổi. Khi đó stream cũ và class mới có thể bị xem là không tương thích dù các field nghiệp vụ vẫn đọc được.

Ví dụ:

~~~java
public class SessionInfo implements Serializable {
    private String token;
}
~~~

Nhóm thêm một public helper method, sửa modifier hoặc thực hiện refactor. Nếu để runtime tự tính UID, một số thay đổi về cấu trúc class có thể làm UID khác và khiến `ObjectInputStream` từ chối dữ liệu trước đây.

Vì thế, với class serializable được kỳ vọng đọc dữ liệu qua nhiều phiên bản, nên **khai báo tường minh và quản lý ổn định** `serialVersionUID`. Không nên tin rằng mọi lần refactor giữ nguyên UID tự sinh.

### 5.1. Xem UID bằng `serialver`

JDK cung cấp công cụ `serialver` để xem giá trị serialVersionUID của class:

~~~bash
serialver -classpath build/classes example.SessionInfo
~~~

Kết quả có dạng:

~~~text
example.SessionInfo:    private static final long serialVersionUID = ...L;
~~~

Nếu đang chuyển một class chưa khai báo UID sang khai báo tường minh mà vẫn cần đọc stream cũ, có thể dùng `serialver` trên **class phiên bản cũ** để ghi nhận UID hiện tại rồi đưa giá trị đó vào phiên bản mới, sau khi xem xét serialized form và khả năng tương thích.

Không lấy UID mới tính từ class đã refactor rồi cho rằng tự động khớp với dữ liệu cũ. Cần xác định UID được ghi trong stream cũ hoặc UID của class đã tạo stream đó.

### 5.2. UID mặc định không phải hash nội dung dữ liệu

UID không được tính từ các giá trị field của từng object. Hai instance có dữ liệu hoàn toàn khác nhau của cùng class vẫn có cùng class UID. UID cũng không giúp kiểm tra byte stream có bị sửa đổi hoặc giả mạo hay không.

Nếu cần integrity, authentication hoặc schema version của dữ liệu, phải thiết kế cơ chế riêng. `serialVersionUID` không thay thế checksum, chữ ký số, authentication hay version trong header của giao thức nghiệp vụ.

## 6. Khi nào giữ nguyên và khi nào thay `serialVersionUID`?

| Thay đổi class | Chiến lược UID thường gặp | Cần kiểm chứng |
| --- | --- | --- |
| Sửa implementation method, không đổi serialized form | Giữ UID | Behavior sau deserialize |
| Thêm field tương thích, có default hợp lệ | Thường giữ UID | Field mới nhận giá trị mặc định; invariant |
| Bỏ field không còn dùng | Thường giữ UID nếu dữ liệu cũ không còn cần | Các field khác và logic cũ |
| Đổi field `transient`/`static` không ảnh hưởng serialized form mong đợi | Có thể giữ UID, nhưng cần xét thay đổi dữ liệu thực | Trạng thái khôi phục và lifecycle |
| Đổi kiểu field hoặc diễn giải field theo nghĩa khác | Không tự quyết chỉ từ UID | Có thể không tương thích hoặc gây sai dữ liệu |
| Đổi tên class/package | Giữ UID không giải quyết việc đổi tên | Class resolution và migration stream |
| Đổi class thành enum hoặc thay cơ chế serialization nền tảng | Không thể xử lý chỉ bằng UID | Serialized form đặc thù |
| Chủ đích từ chối mọi stream phiên bản cũ | Có thể chọn UID mới như một phần của breaking change | Kế hoạch dữ liệu cũ và rollback |

**Quy tắc thực hành:** Không tăng UID theo số phiên bản ứng dụng. Giữ UID khi muốn duy trì compatibility và có bằng chứng dữ liệu cũ vẫn có thể được khôi phục đúng. Thay UID khi có quyết định phá compatibility đã được công bố và có kế hoạch cho dữ liệu cũ. Trong cả hai trường hợp, test deserialization thực tế mới là bằng chứng quan trọng.

### 6.1. Giữ UID không sửa được schema bất tương thích

Một anti-pattern:

~~~java
// Phiên bản cũ
private static final long serialVersionUID = 1L;
private int amount;

// Phiên bản mới
private static final long serialVersionUID = 1L;
private String amount;
~~~

UID không đổi nhưng serialized representation của field đã thay từ `int` sang `String`. Dữ liệu cũ không được tự động chuyển `42` thành `"42"`. Việc đọc có thể bị từ chối hoặc không khôi phục được như mong muốn.

Cần thiết kế phép chuyển đổi có chủ đích, ví dụ dùng field mới với tên khác và một giai đoạn hỗ trợ dữ liệu cũ, dùng custom serialization, hoặc migration dữ liệu offline.

## 7. Những thay đổi field thường gặp

### 7.1. Thêm field

Phiên bản 1:

~~~java
public class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private String id;
}
~~~

Phiên bản 2:

~~~java
public class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private String id;
    private int retryCount;
}
~~~

Khi đọc object được ghi bởi v1, field `retryCount` mới không có trong stream nên thường nhận giá trị mặc định của Java, ở đây `0`. Đây có thể là giá trị hợp lệ, hoặc có thể gây sai logic nếu business muốn giá trị khởi tạo mặc định là `3`.

Lưu ý quan trọng: **field initializer và constructor của class serializable không được thực thi như khi tạo đối tượng bằng `new`**, nên không được giả định:

~~~java
private int retryCount = 3;
~~~

sẽ tự áp dụng cho object v1 đã deserialize. Nếu invariant mới cần một giá trị khác mặc định, cần chiến lược xử lý version-aware, ví dụ `readObject` kiểm tra trạng thái hoặc một giai đoạn migration dữ liệu riêng.

### 7.2. Bỏ field

Phiên bản mới có thể không còn định nghĩa một field từng được ghi. Khi đọc stream cũ theo cơ chế serialization mặc định và UID phù hợp, dữ liệu của field không còn trong class local thường được bỏ qua.

Tuy nhiên, có thể hệ thống từng dùng field đó để quyết định nghiệp vụ, tái tạo cache hoặc tính hash. Đọc stream không lỗi không có nghĩa dữ liệu còn đầy đủ ý nghĩa đối với phiên bản mới. Cần xác minh ảnh hưởng của việc mất trường đó.

### 7.3. Đổi tên field

Đổi:

~~~java
private String customerId;
~~~

sang:

~~~java
private String buyerId;
~~~

không được Java serialization mặc định hiểu là cùng một field. Về mặt serialized form, đây thường tương đương với việc field `customerId` biến mất và field `buyerId` mới xuất hiện. Khi đọc dữ liệu cũ, `buyerId` có thể là `null`.

Nếu cần giữ giá trị, nên có giai đoạn migration rõ ràng, custom mapping hoặc data conversion. Không tin rằng cùng kiểu `String` sẽ làm tên cũ tự map vào tên mới.

### 7.4. Đổi kiểu field

Đổi `int` thành `long`, `String` thành `UUID` hoặc `List<Item>` thành một kiểu object khác có thể khiến serialized form không còn tương thích. Không nên suy luận rằng compiler có thể widening primitive là Java serialization cũng sẽ tự làm widening trong trường hợp này.

Nếu có dữ liệu lịch sử, một phương án ít rủi ro là thêm field mới, giữ khả năng đọc field cũ qua một lộ trình chuyển đổi, và viết lại snapshot ở định dạng đích sau khi kiểm chứng. Khi dùng custom serialization, cần cẩn thận không vô tình thay đổi stream format theo cách client khác không đọc được.

### 7.5. `static`, `transient` và field `final`

Ví dụ:

~~~java
public class AccountSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    private String accountId;
    private transient String temporaryAccessToken;
    private static String deploymentRegion;
    private final long createdAt;
}
~~~

- `temporaryAccessToken` không được ghi bởi default serialization; khi đọc lại sẽ có giá trị mặc định trừ khi class tự khôi phục.
- `deploymentRegion` là trạng thái class, không nằm trong serialized instance form.
- `createdAt` là instance field `final` và vẫn có thể nằm trong serialized form mặc định.

`transient` là công cụ điều khiển serialized form mặc định, nhưng không phải một biện pháp bảo mật hoàn chỉnh: thông tin nhạy cảm có thể được tham chiếu qua field khác hoặc được custom `writeObject` ghi ra. Luôn xem toàn bộ object graph và mã custom.

## 8. Constructor, inheritance và object invariants

### 8.1. Deserialization không giống gọi `new`

Đối với class triển khai `Serializable` theo cơ chế thông thường, constructor của lớp serializable không được gọi như trong thao tác khởi tạo đối tượng bình thường. Cơ chế deserialization khôi phục field state từ stream. Constructor không tham số của lớp cha đầu tiên **không triển khai `Serializable`** trong hierarchy được gọi theo quy tắc serialization.

Ví dụ:

~~~java
import java.io.Serializable;

class BaseEntity {
    protected String origin;

    public BaseEntity() {
        origin = "generated-locally";
    }
}

class EntitySnapshot extends BaseEntity implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id = "new";

    public EntitySnapshot(String id) {
        this.id = id;
    }
}
~~~

Khi deserialize `EntitySnapshot`, việc khởi tạo state của `BaseEntity` và state của lớp serializable tuân theo các quy tắc khác nhau. Không nên giả định field initializer `id = "new"` hoặc constructor `EntitySnapshot(String)` sẽ chạy và sửa dữ liệu cũ.

### 8.2. Invariant có thể bị vi phạm

Giả sử constructor mới bắt buộc field không null:

~~~java
public Profile(String id) {
    this.id = Objects.requireNonNull(id, "id");
}
~~~

Stream cũ vẫn có thể chứa `id = null` hoặc không có field `id`. Việc thêm validation ở constructor không tự bảo vệ deserialization. Nếu object được khôi phục từ stream, mã đọc cần kiểm tra invariant sau khi `defaultReadObject()` hoặc trước khi sử dụng.

### 8.3. Thay đổi hierarchy

Thêm/bỏ superclass serializable, chuyển field giữa các lớp hoặc thay cấu trúc kế thừa có quy tắc tương thích riêng. Một số thay đổi được Java serialization hỗ trợ, một số có thể tạo dữ liệu mặc định hoặc làm invariant không còn hợp lệ.

Do đó, không nên coi `serialVersionUID` của subclass là cơ chế giải quyết toàn bộ thay đổi hierarchy. Cần thử đọc stream thực tế tạo từ class hierarchy cũ bằng class hierarchy mới, gồm cả những trạng thái có nhiều field/nhánh kế thừa.

## 9. Custom serialization bằng `writeObject` và `readObject`

Java cho phép class tùy chỉnh cách ghi và đọc serialized form bằng các method đặc biệt với chữ ký phù hợp.

### 9.1. Ví dụ kiểm soát dữ liệu và validation

~~~java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.util.Objects;

public class InvoiceSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String invoiceId;
    private long totalCents;

    public InvoiceSnapshot(String invoiceId, long totalCents) {
        this.invoiceId = Objects.requireNonNull(invoiceId);
        if (totalCents < 0) {
            throw new IllegalArgumentException("negative total");
        }
        this.totalCents = totalCents;
    }

    @Serial
    private void writeObject(ObjectOutputStream out)
            throws IOException {
        out.defaultWriteObject();
    }

    @Serial
    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();
        if (invoiceId == null || totalCents < 0) {
            throw new InvalidObjectException(
                    "Invalid invoice snapshot");
        }
    }
}
~~~

Ở đây:

- `writeObject` dùng `defaultWriteObject` để ghi các field theo cơ chế mặc định của class.
- `readObject` dùng `defaultReadObject` để khôi phục dữ liệu mặc định trước khi kiểm tra invariant.
- `InvalidObjectException` chỉ rõ object serialized không hợp lệ.

Việc validation trong `readObject` giúp hạn chế một số state không hợp lệ, nhưng **không biến deserialization dữ liệu không tin cậy thành an toàn**. Object graph phức tạp có thể kích hoạt hook của các class khác trước khi validation của class này hoàn tất.

### 9.2. Không tự thêm bytes vào stream mà bỏ qua hợp đồng

Nếu custom `writeObject` ghi thêm dữ liệu ngoài default fields, code `readObject` phải đọc lại theo đúng format và quy tắc optional data. Khi thay đổi thứ tự đọc/ghi hoặc số lượng primitive/object, stream cũ có thể không còn giải mã đúng.

Những lỗi như `OptionalDataException`, `EOFException` hay `StreamCorruptedException` có thể xuất hiện khi logic custom và cấu trúc stream không khớp. Không nên xem `serialVersionUID` là công cụ sửa lỗi thứ tự đọc/ghi.

### 9.3. `serialPersistentFields`

Class có thể chủ động định nghĩa serialized fields bằng `serialPersistentFields`, tách serialized form khỏi tên/kiểu một số field implementation. Đây là cơ chế nâng cao dùng cùng `ObjectOutputStream.PutField` và `ObjectInputStream.GetField`.

Ví dụ định nghĩa một form cần giữ ổn định:

~~~java
@Serial
private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("legacyId", String.class),
        new ObjectStreamField("quantity", int.class)
};
~~~

Khi dùng nó, implementation phải bảo đảm dữ liệu được ghi/đọc đúng các tên và kiểu đã công bố. Đây có thể là công cụ giữ compatibility trong thư viện cần sống qua nhiều phiên bản, nhưng tăng độ phức tạp và yêu cầu test theo cặp version nghiêm ngặt.

### 9.4. `readObjectNoData`

Java serialization còn có hook `readObjectNoData` để xử lý một số tình huống không có dữ liệu serialized tương ứng cho class trong hierarchy khi khôi phục object. Không nên dùng hook này để “chữa chung” mọi trường hợp field bị thiếu; nó dành cho những trường hợp cấu trúc hierarchy/stream cụ thể.

Nếu đổi inheritance hoặc form của class qua version, cần hiểu đầy đủ cơ chế và test stream từ các bản cũ.

## 10. Serialization proxy pattern

Một cách giảm rủi ro khi serialized form không nên trùng với object implementation là dùng **serialization proxy**: object chính được thay bằng một proxy đơn giản khi ghi, rồi tái tạo object hợp lệ qua constructor/factory khi đọc.

Ví dụ:

~~~java
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectStreamException;
import java.io.Serial;
import java.io.Serializable;
import java.util.Objects;

public final class Money implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String currency;
    private final long cents;

    public Money(String currency, long cents) {
        this.currency = Objects.requireNonNull(currency);
        if (cents < 0) {
            throw new IllegalArgumentException("negative amount");
        }
        this.cents = cents;
    }

    @Serial
    private Object writeReplace() throws ObjectStreamException {
        return new Proxy(currency, cents);
    }

    @Serial
    private void readObject(ObjectInputStream in)
            throws InvalidObjectException {
        throw new InvalidObjectException("Use serialization proxy");
    }

    private static final class Proxy implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String currency;
        private final long cents;

        private Proxy(String currency, long cents) {
            this.currency = currency;
            this.cents = cents;
        }

        @Serial
        private Object readResolve() throws ObjectStreamException {
            return new Money(currency, cents);
        }
    }
}
~~~

Khi ghi `Money`, `writeReplace` cung cấp proxy. Khi đọc proxy, `readResolve` tạo lại `Money` qua constructor có validation. Pattern này giúp không buộc serialized form trùng với tất cả field nội bộ của object.

Lưu ý: việc dùng proxy thay cho dạng serialization cũ có thể là **breaking serialized-format change** nếu dữ liệu đã phát hành trước đó lưu trực tiếp `Money`. Cần có kế hoạch đọc/migrate dữ liệu cũ thay vì chỉ thêm proxy và giả định mọi stream trước đây được chấp nhận.

## 11. `Externalizable` và rủi ro đặc biệt

`Externalizable` cho class quyền tự quản lý dữ liệu trong `writeExternal` và `readExternal`. Khác với serialization mặc định, cơ chế này đặt gánh nặng bảo đảm format lên implementation.

~~~java
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectOutput;

public class LegacyEnvelope implements Externalizable {
    private static final long serialVersionUID = 1L;
    private String id;

    public LegacyEnvelope() {
        // Public no-argument constructor required.
    }

    @Override
    public void writeExternal(ObjectOutput out)
            throws IOException {
        out.writeUTF(id == null ? "" : id);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        String value = in.readUTF();
        id = value.isEmpty() ? null : value;
    }
}
~~~

`Externalizable` cần public constructor không tham số phù hợp để runtime tạo instance trước khi gọi `readExternal`. Quy tắc ghi/đọc dữ liệu và thứ tự trong stream phải tương thích; UID chỉ là một phần của kiểm tra class, không tự biến định dạng thủ công thành versioned schema.

Ví dụ trên cố ý thể hiện sự mơ hồ giữa chuỗi rỗng và `null`; nếu hai trạng thái có nghĩa khác nhau, format cần một marker riêng. Khi migrate, nên kiểm tra khả năng phân biệt missing/empty/null, giới hạn kích thước và invalid input.

Chuyển một class giữa `Serializable` mặc định và `Externalizable` không nên được xem là thay đổi implementation đơn thuần; đây là thay đổi serialized form đáng kể.

## 12. Những trường hợp có serialization đặc biệt

### 12.1. Enum

Enum có cơ chế serialization đặc thù theo tên constant. Không nên giả định `serialVersionUID` hay custom `writeObject` hoạt động với enum như với class thông thường. Đổi tên/xóa enum constant có thể khiến dữ liệu cũ không còn được đọc đúng.

Ví dụ:

~~~java
enum OrderStatus {
    NEW,
    PAID,
    SHIPPED
}
~~~

Nếu phiên bản mới đổi `PAID` thành `SETTLED`, stream chứa tên `PAID` không tự chuyển sang `SETTLED`. Nếu enum đã nằm trong dữ liệu lưu trữ, cần quản lý tên constant như một phần của hợp đồng dữ liệu hoặc thực hiện migration.

### 12.2. Record serializable

Java record có quy tắc serialization đặc thù; giá trị thành phần được dùng để khôi phục record theo cơ chế dành cho record, và canonical constructor được gọi khi deserialize. Không suy luận hoàn toàn từ quy tắc constructor của ordinary serializable class.

~~~java
import java.io.Serializable;

public record Point(int x, int y) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Khi dùng record làm serialized DTO, cần kiểm tra các quy tắc về component names/types, validation trong canonical constructor và phiên bản JDK hỗ trợ record. Một UID cùng giá trị không làm việc đổi tên component hoặc đổi kiểu trở nên tự tương thích.

### 12.3. Serializable lambda

Lambda có thể tham gia cơ chế serialization nếu target functional interface là serializable. Tuy nhiên, serialized form của lambda phụ thuộc chi tiết implementation/compiler và không được xem là định dạng lưu trữ lâu dài, ổn định qua các lần refactor hoặc nâng cấp.

Không nên dùng “serialize lambda và lưu xuống database” làm hợp đồng bền vững. Thay vào đó, lưu dữ liệu mô tả hành vi, mã loại thao tác và tham số, rồi giải mã bằng logic ứng dụng được version hóa.

### 12.4. Dynamic proxy và framework-generated class

Các proxy do framework sinh có thể mang metadata/hierarchy thay đổi giữa phiên bản. Dù object gốc có UID ổn định, object graph có thể chứa proxy hoặc implementation class không còn tương thích.

Nếu payload cần tồn tại qua deploy, nên tránh serialize các đối tượng runtime phức tạp như session ORM, executor, thread, service proxy hoặc class loader. Thay bằng DTO/snapshot có schema rõ và chỉ chứa trạng thái thật sự cần lưu.

## 13. Các exception thường gặp khi đọc stream cũ

| Exception | Tình huống điển hình | Hướng điều tra |
| --- | --- | --- |
| `InvalidClassException` | UID không khớp; class local không tương thích serialized form | So UID trong stream/local, class descriptor và hierarchy |
| `ClassNotFoundException` | Runtime không tìm thấy class có tên được ghi trong stream | Classpath, package rename, class loading |
| `NotSerializableException` | Ghi object graph có class không serializable | Field graph, `transient`, DTO hoặc custom serialization |
| `StreamCorruptedException` | Header/type code hoặc cấu trúc stream không hợp lệ | Input bytes, định dạng dữ liệu, truncation, stream protocol |
| `OptionalDataException` | Đọc primitive/object không khớp phần optional data | Thứ tự `writeObject`/`readObject` hoặc dữ liệu tùy chỉnh |
| `EOFException` | Stream kết thúc khi còn dữ liệu được kỳ vọng | File cắt cụt, đọc quá số object, lỗi ghi |
| `ClassCastException` | Deserialize thành công nhưng cast sang kiểu consumer không phù hợp | Class trả về và kiểu root object |
| `InvalidObjectException` | Class chủ động từ chối state không hợp lệ trong `readObject`/`readResolve` | Invariant và version conversion |
| `ObjectStreamException` | Nhóm exception đặc thù object serialization | Đọc cause và class được nêu trong stack trace |

Không tự sửa lỗi bằng cách đổi UID cho “bằng nhau” trước khi xác định dữ liệu có cùng ý nghĩa và schema có thể đọc được hay không. Việc ép UID có thể chuyển lỗi rõ ràng thành object im lặng nhưng sai trạng thái.

### 13.1. Cần giữ nguyên bằng chứng lỗi

Khi lỗi xảy ra, ghi:

- Tên class được đề cập trong exception.
- `stream classdesc serialVersionUID` và `local class serialVersionUID` nếu có.
- Phiên bản artifact đã tạo stream và artifact đang đọc.
- Source/JDK/build tool dùng ở mỗi phía.
- File/queue/cache record cụ thể gây lỗi, có biện pháp bảo vệ dữ liệu nhạy cảm.
- Class loader, module và dependency version.
- Stack trace nguyên nhân đầu tiên, không chỉ exception wrapper.

Nếu dữ liệu có thông tin cá nhân hoặc bí mật, không log nguyên bytes hoặc toàn bộ object graph vào hệ thống logging chỉ để chẩn đoán.

## 14. Bảo mật: không deserialize dữ liệu không tin cậy theo thói quen

Java serialization có rủi ro bảo mật lớn khi ứng dụng deserialize dữ liệu do nguồn không đáng tin cậy kiểm soát. Vấn đề không chỉ nằm ở class DTO do ứng dụng viết; một object graph có thể chứa nhiều class trong classpath và những hook deserialize của chúng.

Một số nguy cơ:

- Thao tác không mong muốn trong quá trình khôi phục graph đối tượng.
- Tấn công từ chối dịch vụ qua graph sâu, số lượng references lớn hoặc kích thước dữ liệu không giới hạn.
- Tạo object với trạng thái bất thường, phá invariant.
- Lợi dụng những gadget classes có trên classpath trong một số môi trường.
- Xử lý dữ liệu gây tiêu hao CPU, RAM hoặc tài nguyên hệ thống.

**Khuyến nghị thiết kế:** Không dùng `ObjectInputStream` làm format chung cho request từ Internet, message không tin cậy hoặc dữ liệu do bên ngoài cung cấp. Ưu tiên DTO đơn giản trong JSON/Protobuf/Avro hoặc protocol đã được lựa chọn với validation, giới hạn kích thước và authentication phù hợp.

Nếu phải duy trì Java serialization cho dữ liệu nội bộ được kiểm soát, nên áp dụng thêm hạn chế về nguồn, quyền truy cập, class được phép và giới hạn object graph.

### 14.1. Object input filtering

Từ Java 9, cơ chế `ObjectInputFilter` hỗ trợ kiểm soát một số class, độ sâu, số reference và kích thước khi deserialize. Các JDK hiện đại còn có khả năng cấu hình chính sách filter và filter factory; ví dụ JDK 17 giới thiệu cơ chế filter theo ngữ cảnh để áp dụng chính sách phù hợp từng luồng đọc.

Ví dụ minh họa một filter hạn chế việc đọc:

~~~java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

try (ObjectInputStream in = new ObjectInputStream(inputStream)) {
    ObjectInputFilter filter =
            ObjectInputFilter.Config.createFilter(
                    "maxdepth=12;maxrefs=1000;maxbytes=1048576;"
                    + "example.dto.*;!*");

    in.setObjectInputFilter(filter);
    Object object = in.readObject();
    // Validate class thực tế, object graph và dữ liệu nghiệp vụ.
}
~~~

Đây chỉ là ví dụ cho một application model nhất định. Danh sách class được phép phải được thiết kế theo graph thật, bao gồm các kiểu trong JDK hoặc collection mà payload sử dụng; một filter quá hẹp có thể từ chối dữ liệu hợp lệ, filter quá rộng lại không giảm rủi ro đủ mức.

Filter không phải “công tắc biến Java serialization thành an toàn tuyệt đối”. Cần xem xét chính sách áp dụng cho mọi đường deserialize, các lớp được phép, tài nguyên, nguồn dữ liệu và logic validation.

### 14.2. Không sử dụng `SecurityManager` như lời giải tương thích

Không nên lập kế hoạch bảo vệ deserialization bằng một giả định rằng ứng dụng hiện đại sẽ luôn chạy dưới `SecurityManager`. Cơ chế này đã bị deprecate và bị hạn chế/loại bỏ dần tùy phiên bản Java. Thiết kế bảo mật phải dựa trên các biện pháp còn được hỗ trợ ở JDK mục tiêu.

## 15. Serialization không phải schema migration engine

Một nhầm lẫn phổ biến là đặt cùng `serialVersionUID` cho mọi phiên bản và hy vọng Java tự hiểu:

~~~text
v1: amount: int, currencyCode: String
v2: amount: BigDecimal, currency: Currency
v3: money: Money
~~~

Đây là ba data models khác nhau. Dù class names và UID giữ nguyên, Java serialization không tự biết chuyển `int` thành `BigDecimal` hay hợp nhất hai field thành `Money` theo quy tắc nghiệp vụ.

Khi data model thay đổi đáng kể, nên xem như schema migration:

1. Định nghĩa rõ dạng dữ liệu cũ và mới.
2. Viết phép chuyển đổi đã kiểm chứng.
3. Giữ một khoảng thời gian đọc được dữ liệu cũ nếu cần.
4. Chuyển đổi dữ liệu trong kho lưu trữ hoặc rewrite snapshot.
5. Xác nhận rollback có đọc được dữ liệu vừa được ghi bởi phiên bản mới hay không.

Không nên làm mất dữ liệu cũ bằng cách deserialize thành object mới rồi ghi đè lên cùng file chỉ vì không có exception.

## 16. Thiết kế phiên bản dữ liệu ở cấp nghiệp vụ

`serialVersionUID` xác nhận dạng serialized class ở mức Java, nhưng một hệ thống thường cần biết **schema của payload** và **quy tắc nghiệp vụ**. Có thể đặt version ở một envelope riêng:

~~~java
import java.io.Serializable;

public final class SnapshotEnvelope implements Serializable {
    private static final long serialVersionUID = 1L;

    private final int schemaVersion;
    private final String recordType;
    private final byte[] payload;

    public SnapshotEnvelope(
            int schemaVersion,
            String recordType,
            byte[] payload) {
        this.schemaVersion = schemaVersion;
        this.recordType = recordType;
        this.payload = payload.clone();
    }
}
~~~

Ý tưởng là payload version mang ý nghĩa **cách giải mã dữ liệu**; UID vẫn mang ý nghĩa **serialization compatibility của class envelope**. Trong thiết kế mới, payload bytes nên được mã hóa bằng format có schema và giới hạn rõ hơn nếu phù hợp.

Envelope không tự giải quyết mọi rủi ro nếu toàn bộ nó vẫn được deserialize bằng Java Object Serialization từ nguồn không tin cậy. Cần chọn trust boundary và format phù hợp.

### 16.1. Version không thay thế capability negotiation

Trong giao tiếp giữa các service, không phải consumer nào cũng nâng cấp cùng lúc. Producer v2 có thể cần gửi dữ liệu mà consumer v1 vẫn hiểu, hoặc dùng message type/endpoint/version mới thay vì thay đột ngột dạng cũ.

Một chiến lược thường dùng là:

- **Expand:** producer/consumer chấp nhận schema cũ và mới trong thời kỳ chuyển tiếp.
- **Migrate:** cập nhật consumer và chuyển dữ liệu dần.
- **Contract:** ngừng ghi/đọc format cũ khi tất cả consumer đã sẵn sàng.

Với Java serialization, khả năng giữ cùng class và UID chỉ là một điều kiện; cần xác nhận thực tế phiên bản nào đọc được bytes phiên bản nào tạo ra.

## 17. Thử nghiệm tương thích qua nhiều phiên bản

Không thể chỉ kiểm tra rằng class v2 có thể serialize rồi deserialize chính nó. Phép thử này bỏ qua yêu cầu chính của migration: **class mới đọc được dữ liệu do class cũ ghi**.

### 17.1. Ma trận tối thiểu

| Writer | Reader | Mục đích |
| --- | --- | --- |
| v1 | v1 | Xác nhận baseline và fixture |
| v1 | v2 | Xác nhận forward migration của dữ liệu lịch sử |
| v2 | v2 | Xác nhận format mới nhất tự đọc được |
| v2 | v1 | Kiểm tra rollback hoặc rolling deployment khi sản phẩm yêu cầu |
| v1/v2 | Runtime JDK đích | Phát hiện khác biệt runtime, filter, class loading |

Không phải hệ thống nào cũng bắt buộc v1 đọc được dữ liệu mới. Nếu không hỗ trợ downgrade, phải công bố và thiết kế rollout sao cho không có consumer cũ đọc stream mới.

### 17.2. Chuẩn bị fixture đúng cách

Một cấu trúc test minh họa:

~~~text
serialization-compat/
  fixtures/
    order-v1-valid.ser
    order-v1-missing-field.ser
    order-v1-null-field.ser
    order-v2-valid.ser
  readers/
    current-version-tests/
~~~

Fixture `.ser` phải được tạo từ **artifact class và JDK của writer version thật**, rồi giữ nguyên bytes để test reader sau này. Đừng dùng class v2 tạo một file mới rồi đặt tên `order-v1.ser`; như vậy không kiểm tra dữ liệu lịch sử.

Khi có dữ liệu nhạy cảm, dùng fixture giả lập, chỉ chứa thông tin đủ để tái hiện serialized form. Tránh đưa file production vào repository.

### 17.3. Hai bộ class cùng tên cần process/classloader riêng

Nếu class v1 và v2 có cùng fully qualified name, không thể đơn giản đưa cả hai JAR vào cùng classpath rồi nghĩ rằng Java sẽ tự phân biệt. Class loader thông thường chỉ chọn một định nghĩa cho một tên class trong phạm vi loader đó.

Để thử writer v1 và reader v2:

1. Chạy writer trong một process/classpath riêng với library v1.
2. Lưu bytes dưới một fixture có provenance rõ.
3. Chạy reader trong process/classpath riêng với library v2.
4. So sánh object state và business invariants sau deserialize.

Có thể dùng isolated class loaders nếu có lý do kỹ thuật, nhưng thử hai process thường dễ kiểm soát và đọc kết quả hơn trong một pipeline compatibility.

### 17.4. Ví dụ test đọc fixture

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class CompatibilityTest {
    @Test
    void readsSnapshotWrittenByV1() throws Exception {
        Path fixture = Path.of(
                "src/test/resources/order-v1-valid.ser");

        try (ObjectInputStream in = new ObjectInputStream(
                Files.newInputStream(fixture))) {
            Object value = in.readObject();
            OrderSnapshot snapshot = (OrderSnapshot) value;

            assertEquals("ORDER-1", snapshot.orderId());
            assertTrue(snapshot.amountInCents() >= 0);
        }
    }
}
~~~

Đây là ví dụ về cấu trúc test; fixture thật cần được tạo với v1 và filter/trust boundary phải được áp dụng nếu test có thể đọc input không được kiểm soát. Test nên kiểm tra cả field mới, dữ liệu rỗng/null, hierarchy, custom hooks và toàn bộ object graph.

## 18. Vì sao cả JDK lẫn dependency version đều quan trọng?

Format Java serialization có đặc tả riêng, nhưng khả năng đọc thực tế còn phụ thuộc:

- Class có tồn tại ở runtime hay không.
- Mã implementation và serialized form của các class trong graph.
- Default UID nếu class chưa khai báo UID tường minh.
- Module/class loader access, dependency packaging và generated classes.
- `ObjectInputFilter` và chính sách runtime.
- Thư viện serialization/proxy/ORM có thay đổi behavior hay không.
- Runtime image có đủ module/provider/class cần thiết hay không.

Vì vậy, một lỗi đọc snapshot sau khi nâng JDK 17 → 21 không có nghĩa Java 21 tự ý “đổi format”. Có thể framework đã nâng và thay class state, phụ thuộc bị đổi, filter mới được bật hoặc ứng dụng dùng một generated class khác.

Trước khi quy lỗi cho JDK, nên tách thay đổi:

1. Reader v1 chạy JDK cũ với fixture cũ.
2. Reader v1 (nếu hỗ trợ) chạy JDK mới với cùng fixture.
3. Reader v2 chạy JDK mới với fixture cũ.
4. Reader v2 chạy JDK mới với fixture mới.

Nếu framework major thay đổi cùng lúc, hãy giữ ma trận rõ để khoanh vùng nguyên nhân.

## 19. Quy trình migration an toàn khi đang có dữ liệu `.ser`

### Bước 1: Kiểm kê nơi lưu hoặc truyền Java serialization

Tìm:

- File cache, snapshot, checkpoint hoặc object store chứa Java serialized bytes.
- Cơ chế session persistence của framework.
- Queue/RPC/cơ chế messaging cũ truyền object Java.
- Test fixture, công cụ import/export hoặc plugin ghi object.
- Bản sao backup có thể được dùng để khôi phục sau này.

Không chỉ tìm `ObjectOutputStream` trong source. Thư viện có thể dùng serialization ẩn sau API cache hoặc session.

### Bước 2: Xác định object graph và phiên bản đã phát hành

Liệt kê root class, các class tham chiếu, `serialVersionUID`, field names/types, custom hooks, subclass hierarchy và bản JAR đã tạo dữ liệu. Nếu có generated proxy hoặc lambda, ghi rõ.

### Bước 3: Đánh giá security/trust boundary

Quyết định nguồn bytes có đáng tin không; nếu không, không dùng Java serialization như đường deserialize mở. Thiết kế bộ lọc và biện pháp giới hạn khi phải duy trì trong thời gian chuyển tiếp.

### Bước 4: Xác định thay đổi schema

So sánh v1/v2:

- UID tường minh hay tự tính.
- Field được thêm, bỏ, đổi tên, đổi kiểu.
- `transient`, `static` và `final`.
- Method custom `readObject`, `writeObject`, `readResolve`, `writeReplace`.
- Hierarchy, enum/record/proxy.
- Invariant và giá trị mặc định.

### Bước 5: Chọn đường chuyển đổi

Có thể giữ serialized form tương thích, thêm adapter trong `readObject`, tạo schema envelope mới, hoặc dùng công cụ đọc dữ liệu cũ trong một process độc lập rồi xuất ra format mới như JSON/Protobuf/Avro/DB schema.

Nếu class đã thay đổi không thể đọc stream cũ một cách an toàn, **converter chạy với class version cũ** thường là phương án dễ kiểm soát hơn việc sửa UID để ép class mới nhận dữ liệu.

### Bước 6: Tạo fixture và thử nghiệm hai chiều cần thiết

Tạo fixture từ artifact cũ, thử với runtime mới, kiểm tra invariant và consistency, chứ không chỉ catch exception.

### Bước 7: Tổ chức rollout

Đối với kho lưu trữ hoặc cache:

- Quyết định xóa cache an toàn hay cần migrate dữ liệu.
- Nếu xóa cache, đánh giá cache warm-up, tải DB và khả năng mất trạng thái.
- Nếu migrate, cần checkpoint, backup, khả năng chạy lại và xác nhận số bản ghi.
- Nếu nhiều service chạy song song, không để consumer cũ đọc format mới khi chưa hỗ trợ.

### Bước 8: Đóng format cũ theo kế hoạch

Khi tất cả consumer đã chuyển, dừng ghi format cũ, xác nhận dữ liệu lịch sử đã được chuyển hoặc hết thời hạn lưu trữ, rồi mới bỏ reader/adapter cũ.

## 20. Khi nào nên bỏ Java serialization để dùng định dạng khác?

Nên cân nhắc định dạng dữ liệu có schema rõ hơn khi:

- Dữ liệu phải tồn tại qua nhiều năm và nhiều thế hệ code.
- Có nhiều ngôn ngữ hoặc service không dùng Java.
- Cần kiểm soát field evolution, backward/forward compatibility.
- Có yêu cầu security boundary từ nguồn ngoài.
- Muốn kiểm tra/cập nhật dữ liệu bằng công cụ độc lập.
- Muốn quản lý schema qua registry, migrations hoặc contract tests.

### 20.1. Một số lựa chọn

| Lựa chọn | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| JSON với DTO/schema | Payload dễ đọc, API web, interoperability | Cần versioning và validation; không mặc nhiên giữ object identity |
| Protocol Buffers | Hợp đồng có schema và binary payload giữa service | Phải quản lý field numbers, defaults, compatibility |
| Avro | Dữ liệu sự kiện/lưu trữ theo schema có evolution rules | Cần quản lý writer/reader schema |
| Database schema + migration | Dữ liệu nghiệp vụ lâu dài, query/update | Cần migration transaction và rollback strategy |
| Java Object Serialization | Dữ liệu nội bộ được kiểm soát, nhu cầu compatibility hạn chế | Vẫn cần UID, filters, object graph tests, migration plan |

Không nên chọn một format mới chỉ vì tên công nghệ. Cần so sánh requirements: schema version, trust boundary, latency, payload size, khả năng truy cập, đồng bộ producer–consumer và cách đổi dữ liệu lịch sử.

### 20.2. DTO tách khỏi entity runtime

Một nguyên tắc hữu ích là lưu một **snapshot DTO** đơn giản, thay vì serialize trực tiếp ORM entity, service hoặc proxy:

~~~java
public record OrderDto(
        String orderId,
        long amountInCents,
        String currencyCode) {
}
~~~

DTO có ít field và ý nghĩa rõ, nên dễ viết mapper và migration. Việc chọn record trong Java không buộc payload phải là Java serialization; DTO này có thể được ánh xạ sang JSON hoặc một format có schema khác.

## 21. Chiến lược rollback và version skew

Một đợt phát hành có thể gồm:

~~~text
Writer v1  ──> Stored bytes v1 ──> Reader v1
Writer v2  ──> Stored bytes v2 ──> Reader v2
                              └──> Reader v1 (rollback?)
~~~

Nếu triển khai v2 bắt đầu ghi stream mà v1 không đọc được, rollback application về v1 có thể vẫn thất bại dù deployment đã quay về binary cũ. Đây là **rollback/data-compatibility risk**.

Các phương án:

1. **Reader-first:** triển khai reader có thể đọc cả dữ liệu cũ và mới trước khi writer bắt đầu phát format mới.
2. **Dual-write có kiểm soát:** chỉ dùng khi có lý do rõ, tránh giữ hai bản dữ liệu mất đồng bộ.
3. **Versioned envelope:** đánh dấu schema và chọn decoder phù hợp.
4. **Migration offline:** chuyển toàn bộ dữ liệu lịch sử trong maintenance window có backup và verification.
5. **Roll-forward plan:** nếu data migration không thể đảo ngược, chuẩn bị fix-forward thay vì hứa rollback không khả thi.

Với Java serialization thuần, khả năng reader v1 đọc writer v2 không nên suy ra từ việc hai class cùng UID. Cần thử stream thực tế và xác định chính sách hỗ trợ.

## 22. Ví dụ tổng hợp: nâng snapshot đơn hàng qua hai phiên bản

Giả sử phiên bản 1:

~~~java
public class OrderState implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id;
    private int amountCents;
}
~~~

Phiên bản 2 muốn dùng `long` và thêm currency:

~~~java
public class OrderState implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id;
    private long amountCents;
    private String currencyCode;
}
~~~

Trông có vẻ chỉ là “mở rộng int sang long”. Nhưng serialized field `amountCents` đã đổi kiểu từ `int` thành `long`, và `currencyCode` không có trong stream cũ. Giữ UID bằng `1L` không tự giải quyết cả hai vấn đề.

### 22.1. Phương án migration bằng format chuyển tiếp

Một hướng là giữ cơ chế đọc dạng cũ trong code converter riêng:

1. Process A chạy với class `OrderState` v1, chỉ đọc fixture/snapshot v1 được kiểm soát.
2. Process A chuyển giá trị sang format trung gian có schema rõ, ví dụ bản ghi chứa `id`, `amountCents` dưới dạng integer và default currency được phê duyệt.
3. Process B đọc format trung gian, chuyển sang `OrderState` v2 với `long` và `currencyCode`.
4. Process B xác nhận invariant và ghi snapshot mới theo format mục tiêu.

Converter cần xác định currency cho dữ liệu cũ. Nếu không thể biết currency từ v1, không nên tự gán `"USD"` hoặc bất kỳ đồng tiền nào mà không có quy tắc nghiệp vụ được phê duyệt.

### 22.2. Phương án giữ API cũ trong một khoảng thời gian

Nếu cần đọc dữ liệu trong cùng ứng dụng mà không được chạy converter riêng, có thể thêm serialized field hoặc adapter hợp lệ để bảo toàn dạng cũ và tạo field mới có tên khác, sau đó xử lý migration trong hook/lớp mapping. Thiết kế phải tuân thủ serialized form và không có hai field cùng tên nhưng khác kiểu gây xung đột.

Việc này phức tạp hơn converter riêng, đặc biệt khi có hierarchy, object graph lớn hoặc các class khác cũng thay đổi. Cần test nhiều fixture và đánh giá cả security risk.

### 22.3. Tiêu chí chấp nhận

Không chỉ yêu cầu “không còn `InvalidClassException`”. Cần xác nhận:

- Mọi order ID được giữ đúng.
- Amount không mất độ chính xác và không overflow.
- Currency có nguồn gốc/quy tắc rõ.
- Số record trước/sau khớp trong phạm vi migration.
- Trạng thái lỗi/không hợp lệ được xử lý, không ghi đè im lặng.
- Reader/rollback strategy đã được chứng minh bằng bài thử thực tế.

## 23. Chẩn đoán khi production báo `InvalidClassException`

Một quy trình điều tra có thứ tự:

1. **Xác định dữ liệu nguồn:** file, session, cache entry hay message? Writer version nào?
2. **Đọc stack trace:** class nào bị báo, UID của stream/local là bao nhiêu?
3. **Xác định class thực tế:** class loader đã nạp JAR nào? Có shaded/duplicate dependency không?
4. **So sánh UID:** explicit hay default; kiểm tra bằng `serialver` và class file phù hợp.
5. **So sánh serialized form:** field names/types, superclass, enum/record, custom hooks.
6. **Khôi phục fixture:** chạy reader version cũ trong môi trường cô lập để xác nhận dữ liệu vốn hợp lệ.
7. **Thử reader mới:** dùng đúng bytes cũ để tách lỗi schema khỏi lỗi môi trường.
8. **Chọn sửa đổi:** giữ UID/khôi phục field hợp lệ, converter, xóa cache an toàn hoặc triển khai format mới.
9. **Thử rollback:** liệu reader cũ đọc được dữ liệu mới? Nếu không, cần kế hoạch vận hành khác.

Tránh:

- Đổi `serialVersionUID` ngẫu nhiên cho đến khi không còn exception.
- Xóa mọi cache/session mà chưa đánh giá hậu quả mất trạng thái hoặc tải lại dữ liệu.
- Tắt toàn bộ filter để “đọc lại được” mà không xem trust boundary.
- Chỉ test serialize/deserialize với cùng phiên bản class mới.
- Kết luận JDK mới gây lỗi khi dependency hoặc class loader đã đổi.

## 24. Checklist khi review thay đổi class `Serializable`

- [ ] Đã xác định class có tham gia Java Object Serialization thật hay chỉ implement marker interface nhưng không được sử dụng.
- [ ] Đã biết dữ liệu serialized còn tồn tại trong cache, file, session, backup hay message không.
- [ ] Class public/shared có khai báo `serialVersionUID` tường minh khi cần tương thích lâu dài.
- [ ] Đã so UID của writer cũ và reader mới, tránh tính UID mới rồi áp dụng mù quáng.
- [ ] Đã ghi thay đổi field names, types, `transient`, `static` và `final`.
- [ ] Đã đánh giá giá trị mặc định của field được thêm và invariant sau deserialize.
- [ ] Đã kiểm tra class hierarchy, enum, record, proxy hoặc lambda nếu có.
- [ ] Custom `readObject`/`writeObject`/`readResolve`/`writeReplace` có contract được kiểm thử.
- [ ] Nếu dùng `Externalizable` đã kiểm tra constructor không tham số và thứ tự dữ liệu.
- [ ] Đã có fixture bytes tạo từ phiên bản đã phát hành, không chỉ test v2 đọc v2.
- [ ] Đã kiểm tra reader v2 đọc dữ liệu v1.
- [ ] Đã kiểm tra v1 đọc dữ liệu v2 nếu rolling deployment/rollback yêu cầu.
- [ ] Object graph có giới hạn kích thước, độ sâu, class được chấp nhận phù hợp với trust boundary.
- [ ] Không deserialize dữ liệu không đáng tin chỉ vì có `serialVersionUID`.
- [ ] Đã xem nhu cầu chuyển sang DTO/format có schema thay vì duy trì Java serialization vô thời hạn.
- [ ] Có owner, phương án backup, migration, kiểm tra dữ liệu và xử lý lỗi.
- [ ] Release notes nêu rõ serialized-form breaking changes, version support và kế hoạch rollback.

## 25. Những hiểu lầm thường gặp

**“`serialVersionUID = 1L` nghĩa là dữ liệu schema version 1.”** Không đúng. Đây là UID của serialized class, không tự mô tả field-level schema hay nghiệp vụ.

**“Mỗi lần phát hành phải tăng UID.”** Không đúng. Tăng UID có thể làm dữ liệu cũ bị từ chối không cần thiết.

**“Giữ nguyên UID thì mọi thay đổi field đều tương thích.”** Không đúng. UID không tự chuyển đổi field type, tên field hoặc invariant.

**“Nếu constructor validate thì dữ liệu deserialize cũng chắc chắn hợp lệ.”** Sai với ordinary `Serializable`; constructor của class serializable không chạy như khi `new` object. Cần validation ở đường deserialization.

**“Thêm field có initializer thì object cũ sẽ nhận đúng initializer đó.”** Không nên giả định. Field không có trong stream thường nhận giá trị mặc định theo deserialization, không nhất thiết initializer mới.

**“`transient` là cách duy nhất đảm bảo không lộ dữ liệu bí mật.”** Không đúng. Custom serialization và object graph vẫn có thể ghi dữ liệu nhạy cảm; cần xem toàn bộ form và trust boundary.

**“`NotSerializableException` và `InvalidClassException` là cùng một lỗi.”** Không đúng. Một lỗi thường phát sinh khi cố ghi object graph có class không serializable; lỗi kia thường liên quan tính hợp lệ/tương thích khi đọc class.

**“Test v2 ghi rồi v2 đọc pass nên migration thành công.”** Không đủ. Phải test bytes được tạo bởi v1 với reader v2.

**“Đổi `Serializable` thành `Externalizable` là refactor nội bộ.”** Không đúng khi dữ liệu đã phát hành cần giữ tương thích.

**“Dùng Java serialization an toàn nếu biết tất cả UID.”** Không đúng. UID không phải cơ chế xác thực, cho phép class hay giới hạn object graph.

**“Nâng JDK đồng nghĩa phải đổi UID của mọi class.”** Không đúng. Phải đánh giá serialized form cụ thể; lỗi có thể đến từ dependency, class hierarchy, filter hoặc schema chứ không chỉ JDK.

## 26. Kết luận

Java Object Serialization là một cơ chế gắn chặt với class và object graph của Java. `serialVersionUID` đóng vai trò nhận diện phiên bản serialized class để phát hiện một số dạng bất tương thích trong quá trình khôi phục dữ liệu. Khai báo UID tường minh giúp tránh những thay đổi UID tự sinh không chủ đích, nhưng **không thay thế được việc quản lý schema và invariant của dữ liệu**.

Trong Java Advance Compatibility Migration, hãy kiểm kê mọi đường sử dụng `ObjectOutputStream`/`ObjectInputStream`, xác định writer và reader versions thực tế, lưu fixture serialized bytes từ bản đã phát hành, rồi kiểm thử đọc chéo trước khi triển khai. Với thay đổi nhỏ và tương thích, có thể giữ UID và xử lý field/defaults rõ ràng. Với thay đổi lớn, cần converter hoặc format có schema/versioning chuyên dụng, cùng phương án rollout và rollback dữ liệu.

Cuối cùng, không dùng Java serialization như cơ chế nhận object tùy ý từ nguồn không tin cậy. Dù UID trùng khớp, deserialization vẫn có thể gây lỗi bảo mật, tài nguyên hoặc semantics. Chọn định dạng dữ liệu, validation và chính sách filter phù hợp là một phần không thể thiếu của migration an toàn.
