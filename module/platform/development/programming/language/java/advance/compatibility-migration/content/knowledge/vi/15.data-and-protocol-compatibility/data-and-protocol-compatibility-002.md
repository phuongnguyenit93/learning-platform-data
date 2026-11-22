# Thay đổi lớp Serializable và khả năng đọc đối tượng đã lưu

Khi ứng dụng Java lưu object bằng `ObjectOutputStream` rồi đọc lại bằng `ObjectInputStream`, dữ liệu đã ghi có thể sống lâu hơn phiên bản class tạo ra nó. Sau một lần nâng JDK, nâng thư viện hoặc refactor model, cùng một file `.ser` có thể không đọc được nữa. Lỗi có thể là `InvalidClassException` vì `serialVersionUID` khác, `ClassNotFoundException` vì class đã đổi package, `ClassCastException` vì dữ liệu cũ không đáp ứng kiểu mới, hoặc đơn giản hơn: object đọc thành công nhưng trường mới mang giá trị `null`, `0` hay `false` khiến nghiệp vụ hoạt động sai.

Vấn đề cốt lõi không chỉ là “Java serialization có tương thích giữa các JDK không?”. Java Object Serialization có định dạng stream và các quy tắc class evolution; nhưng khả năng đọc **một object graph cụ thể** phụ thuộc vào tên nhị phân của class, version identifier, cấu trúc field, lớp cha, cách tùy biến serialization, những class được tham chiếu và classpath/runtime khi đọc. Khi đổi code, điều cần kiểm chứng là **bản class mới có đọc được dữ liệu được ghi bởi bản cũ hay không**, với hành vi nghiệp vụ đúng sau khi đọc.

Bài này tập trung vào migration của các class triển khai `Serializable`, những tình huống đọc dữ liệu đã lưu, cách dùng `serialVersionUID` có chủ đích, cách tổ chức golden-file tests và các lựa chọn dữ liệu bền vững hơn cho hệ thống cần nâng cấp nhiều năm.

## 1. Xác định đúng loại dữ liệu đang lưu

Không phải mọi object được truyền qua mạng hay lưu trong file đều dùng Java Object Serialization. Trước tiên cần xác định cơ chế thực tế.

| Cơ chế | Ví dụ | Rủi ro migration chủ yếu |
|---|---|---|
| Java built-in serialization | `ObjectOutputStream.writeObject(...)` / `ObjectInputStream.readObject()` | Tên class, UID, field layout, hooks và object graph |
| Java `Externalizable` | `writeExternal` / `readExternal` | Định dạng do developer tự quản lý, constructor, version marker |
| JSON/XML | Jackson, Gson, JAXB | Field name, annotation, schema, polymorphism, date/time |
| Protobuf/Avro/Thrift | Message schema cụ thể | Schema evolution, field identifiers, compatibility rules |
| Database ORM | JPA/Hibernate entities | Database schema, converter, lazy proxy, mapping |
| Binary cache/session | Redis/session store có Java serializer | Vòng đời object, rolling deployment, mixed-version reads |
| RMI/Java-specific protocol | Object serialization qua Java transport | Classpath hai đầu, graph, security, protocol |
| Application-specific byte format | `DataOutputStream` hoặc custom codec | Framing, byte order, version và codec contract |

`Serializable` là một marker interface; một class có thể triển khai nó nhưng ứng dụng không bao giờ ghi object bằng `ObjectOutputStream`. Ngược lại, một framework cache/session có thể dùng Java serialization ngầm định mà source nghiệp vụ không trực tiếp gọi `writeObject`. Vì vậy phải kiểm kê các luồng lưu và đọc thật, không chỉ tìm import.

Các nơi thường chứa dữ liệu serialized cần đưa vào phạm vi khảo sát:

- File snapshot, checkpoint, backup, batch output và archive.
- Distributed cache hoặc disk-backed cache.
- HTTP session replication/session persistence.
- Queue/message payload ở hệ thống dùng Java serialization.
- RPC/remote invocation hoặc plugin exchange.
- Persisted job state, workflow engine và scheduler.
- Dữ liệu được lưu bởi framework/thư viện bên thứ ba.
- Object graph được dùng trong test fixture cũ.

Một hệ thống không cần backward compatibility cho dữ liệu cache có thể chọn xóa cache có kiểm soát khi nâng cấp; một hệ thống lưu hồ sơ nghiệp vụ hoặc state lâu dài thường không thể làm vậy. Phải ghi rõ thời gian sống của dữ liệu và khả năng phải đọc lại sau rollback.

## 2. Serializable là gì và JVM ghi những gì?

### 2.1. Ví dụ cơ bản

```java
package com.example.account;

import java.io.Serial;
import java.io.Serializable;

public class AccountSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String accountId;
    private long balanceInCents;

    public AccountSnapshot(String accountId, long balanceInCents) {
        this.accountId = accountId;
        this.balanceInCents = balanceInCents;
    }

    public String getAccountId() {
        return accountId;
    }

    public long getBalanceInCents() {
        return balanceInCents;
    }
}
```

Ghi object:

```java
import java.io.ObjectOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("snapshots", "account.ser");
Files.createDirectories(path.getParent());

AccountSnapshot snapshot = new AccountSnapshot("ACC-42", 125_000L);

try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(snapshot);
}
```

Đọc object:

```java
import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(path))) {
    Object loaded = in.readObject();
    AccountSnapshot snapshot = (AccountSnapshot) loaded;
    System.out.println(snapshot.getAccountId());
}
```

Ví dụ giả định file đến từ nguồn tin cậy và có class tương ứng trên classpath. **Không dùng `ObjectInputStream` trực tiếp để đọc dữ liệu do người ngoài hoặc đầu vào không tin cậy gửi tới.** Vấn đề an toàn deserialization được bàn riêng ở phần sau.

### 2.2. Stream không chỉ chứa giá trị field

Java Object Serialization Stream Protocol mã hóa các thông tin cần để khôi phục object graph, trong đó có:

- Magic header và protocol version của stream.
- Class descriptor: binary name, `serialVersionUID`, flags và danh sách serialized fields.
- Giá trị field của object.
- Reference handle để bảo toàn chia sẻ object/cycle trong graph.
- Descriptor và dữ liệu của các object được tham chiếu.
- Thông tin riêng do các hooks hoặc `Externalizable` ghi thêm khi được sử dụng.

Điều này giải thích vì sao đổi tên class hoặc package không giống đổi tên một key trong JSON. Tên class nằm trong stream descriptor; deserializer cần tìm được một local class có danh tính phù hợp.

### 2.3. Object graph có nhiều lớp cần tương thích

Giả sử:

```java
class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private CustomerSnapshot customer;
    private List<OrderLine> lines;
}
```

Ngay cả khi `OrderSnapshot` giữ nguyên UID, object graph vẫn không thể đọc đúng nếu một class bên trong như `CustomerSnapshot` hoặc `OrderLine` bị đổi binary name, serial UID hay representation không tương thích.

Khi lập compatibility matrix phải liệt kê **toàn bộ class có thể xuất hiện trong object graph**, gồm collection wrapper, enum, custom value object, subclass, proxy và class do thư viện/framework cung cấp. Không chỉ kiểm tra root object.

## 3. serialVersionUID là gì?

### 3.1. Vai trò của serialVersionUID

`serialVersionUID` là một `long` dùng trong cơ chế xác minh tương thích class khi deserialize. Class serializable nên khai báo rõ:

```java
@Serial
private static final long serialVersionUID = 1L;
```

Từ JDK 14, annotation `@Serial` giúp compiler nhận diện các khai báo liên quan đến serialization, nhưng annotation này không thay đổi format stream. Nếu source phải hỗ trợ JDK trước thời điểm `@Serial` được bổ sung, cần cân nhắc source level. `serialVersionUID` vẫn có hiệu lực mà không cần annotation.

Khi đọc class thông thường, Java so sánh serial version identifier trong stream với local class. Nếu không phù hợp, có thể ném `InvalidClassException`.

Ví dụ thông báo:

```text
java.io.InvalidClassException: com.example.account.AccountSnapshot;
local class incompatible:
stream classdesc serialVersionUID = 1,
local class serialVersionUID = 2
```

Cần phân biệt **serialization compatibility** với semantic/business compatibility. UID phù hợp là điều kiện quan trọng cho cơ chế kiểm tra, nhưng nó không đảm bảo các field cũ còn hợp lệ về nghĩa hoặc mọi hook đều tương thích.

### 3.2. Không khai báo UID: default UID có thể thay đổi

Nếu class `Serializable` không khai báo `serialVersionUID`, Java tính một default value dựa trên những đặc điểm của class theo đặc tả, bao gồm một số tên, modifier, interface, field, constructor và method.

Vì vậy, một thay đổi source tưởng không liên quan đến dữ liệu — như sửa public method hoặc cấu trúc class — có thể thay default UID. Sau khi compile lại, dữ liệu cũ không thể đọc do UID không khớp, dù các field mà ứng dụng quan tâm vẫn giống nhau.

Có thể xem UID của class hiện tại bằng:

```java
import java.io.ObjectStreamClass;

long uid = ObjectStreamClass
    .lookup(AccountSnapshot.class)
    .getSerialVersionUID();

System.out.println(uid);
```

Hoặc dùng công cụ JDK:

```bash
serialver -classpath old-library.jar com.example.account.AccountSnapshot
```

Khi cần bảo toàn dữ liệu cũ từ class chưa từng khai báo UID, hãy lấy **giá trị UID của binary phiên bản cũ** trước khi thay đổi source. Sau khi đánh giá class evolution, có thể khai báo explicit UID bằng giá trị cũ để duy trì khả năng đọc. Không nên bịa UID mới hoặc đổi UID chỉ để làm thông báo lỗi biến mất.

### 3.3. Không tăng UID theo version ứng dụng một cách máy móc

`serialVersionUID` không bắt buộc trùng với Maven version, semantic version hoặc số lần release. Nếu những thay đổi class vẫn nằm trong phạm vi evolution tương thích, việc giữ UID cũ có thể là đúng.

Ngược lại, nếu thay đổi representation không tương thích, cố giữ UID chỉ làm deserializer vượt qua bước kiểm tra định danh rồi có nguy cơ thất bại ở bước đọc field hoặc tạo object với trạng thái không hợp lệ.

Cần quyết định UID trên cơ sở thiết kế dữ liệu:

- Giữ UID nếu định dạng object vẫn có thể đọc và chuyển đổi an toàn.
- Đổi UID nếu cố ý chặn dữ liệu cũ không tương thích, kèm kế hoạch migration dữ liệu.
- Dùng record/DTO/versioned schema hoặc format khác nếu cần tiến hóa phức tạp lâu dài.

### 3.4. UID không phải schema version đầy đủ

Một UID duy nhất không mô tả field mới, field bị xóa, business invariant, kiểu dữ liệu, quan hệ kế thừa hay cách xử lý null. Nếu lưu dữ liệu nhiều năm, có thể cần một **data/schema version** riêng để áp dụng chuyển đổi và validation.

Ví dụ, class có thể giữ `serialVersionUID = 1L` nhưng có field `formatVersion` hoặc cơ chế metadata ngoài stream để phân biệt các giai đoạn nghiệp vụ. Mỗi version cần quy tắc chuyển đổi rõ ràng; không đơn thuần đổi trường version rồi bỏ qua các dữ liệu đã lưu.

## 4. Quy tắc class evolution với default serialization

Default serialization chủ yếu xử lý những instance field không `static` và không `transient`. Khi local class thay đổi so với stream, Java có quy tắc ghép serialized fields theo tên và kiểu, với những trường hợp tương thích và không tương thích.

### 4.1. Thêm instance field

Phiên bản v1:

```java
public class CustomerSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private String id;
    private String name;
}
```

Phiên bản v2:

```java
public class CustomerSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private String id;
    private String name;
    private String locale;
}
```

Khi v2 đọc stream được ghi bởi v1, field `locale` không có trong stream. Với default serialization, nó nhận **giá trị mặc định của kiểu**: `null` cho reference, `0` cho kiểu số nguyên, `false` cho boolean.

Lưu ý: constructor của chính class serializable thông thường **không được gọi** theo cách như `new CustomerSnapshot()` khi khôi phục bằng default deserialization. Do đó, code khởi tạo mặc định trong constructor hoặc field initializer không nên được coi là cách migrate giá trị field mới.

Nếu nghiệp vụ yêu cầu `locale` mặc định là `"vi-VN"`, cần bổ sung cơ chế gán giá trị và validation khi đọc; có thể dùng `readObject` nếu hợp đồng phù hợp.

### 4.2. Xóa instance field

Nếu v1 có `middleName` còn v2 xóa field này, serialized stream v1 có thể chứa dữ liệu `middleName`. Khi đọc bằng v2 qua default serialization với UID phù hợp, dữ liệu của field đã bị xóa thường được bỏ qua.

Tuy nhiên, nếu một method cũ, `readObject`, `readResolve` hoặc invariant nghiệp vụ vẫn phụ thuộc `middleName`, đó là vấn đề logic riêng. Không nên kết luận “xóa field luôn an toàn” chỉ từ việc không có `InvalidClassException`.

### 4.3. Đổi tên field

Đổi tên field là sự kết hợp của **xóa field cũ và thêm field mới** dưới góc nhìn serialized field mapping.

Ví dụ:

```text
v1: customerName
v2: displayName
```

Khi đọc dữ liệu v1 bằng v2, `displayName` có thể nhận `null`, còn dữ liệu `customerName` bị bỏ qua. Deserializer không tự hiểu đây là cùng một business field.

Nếu cần giữ giá trị cũ, phải thiết kế mapping ở lớp tương thích, hoặc dùng advanced serialization mechanism như `serialPersistentFields`/`readObject` để đọc legacy field name. Không nên chỉ refactor tên biến rồi hy vọng dữ liệu cũ được giữ.

### 4.4. Đổi kiểu field

Đổi kiểu một serialized field có thể gây bất tương thích. Ví dụ:

```text
v1: int age
v2: long age
```

Nếu field giữ cùng tên nhưng đổi primitive type, không thể mặc định Java sẽ widening từ `int` sang `long` như compiler source. Deserialization dùng field type metadata, và type incompatibility có thể dẫn đến `InvalidClassException`.

Tương tự, đổi từ `String` sang `LocalDate` hoặc từ một model class sang model class khác có thể làm layout hoặc value không phù hợp.

Nếu muốn thay đổi representation, nên tách thành field mới, duy trì legacy field trong giai đoạn migration hoặc chuyển qua DTO/versioned schema có quy tắc rõ ràng. Có thể cần một bước offline data conversion.

### 4.5. `static`, `transient` và `final`

- `static` field thuộc class, không phải trạng thái instance được lưu bởi default serialization.
- `transient` field không được ghi theo default serialization.
- `final` instance field có thể là một phần của serialized state, nhưng không được dựa vào constructor/initializer của class serializable để tái lập invariant lúc đọc.
- Đổi field sang `transient` có thể khiến dữ liệu cũ không còn được khôi phục như trước.

Ví dụ:

```java
public class SessionState implements Serializable {
    private static final long serialVersionUID = 1L;

    private String sessionId;
    private transient String accessToken;
    private static String deploymentRegion;
}
```

`sessionId` được lưu theo default serialization; `accessToken` và `deploymentRegion` thì không. Việc dùng `transient` cho token không đủ để bảo đảm an toàn dữ liệu nếu token từng được lưu ở các phiên bản trước; phải đánh giá và xử lý các file/cache cũ.

### 4.6. Bảng so sánh thay đổi field

| Thay đổi từ v1 sang v2 | Khả năng đọc stream v1 bằng v2 | Rủi ro cần kiểm tra |
|---|---|---|
| Thêm field mới | Thường đọc được nếu UID/structure phù hợp | Giá trị mặc định khác kỳ vọng |
| Xóa field | Thường đọc được nếu UID/structure phù hợp | Mất dữ liệu cũ cần dùng |
| Đổi tên field | Như xóa + thêm | Giá trị mới thành mặc định |
| Đổi kiểu field cùng tên | Có thể không tương thích | `InvalidClassException` hoặc dữ liệu không hợp lệ |
| Thay đổi `transient` | Có thể đọc nhưng dữ liệu đổi | Field có/không được khôi phục |
| Thay đổi `static` | Không thuộc state instance mặc định | Thay đổi cấu hình/runtime behavior |
| Thay generic type argument | Có thể giữ erased field type | Runtime cast và semantic mismatch |
| Thay class hierarchy | Phải đánh giá riêng | Constructor, class data, superclass state |
| Đổi tên/package class | Thường không tự tương thích | Không resolve được binary name |
| Đổi serialVersionUID | Thường bị từ chối | `InvalidClassException` |

“Thường đọc được” không phải cam kết tuyệt đối: còn cần giữ đúng binary name, type relationship, UID, stream format, hooks và toàn bộ object graph.

## 5. Ví dụ có thể tái hiện: thêm field và đọc dữ liệu v1

### 5.1. Binary v1 để ghi dữ liệu

Trong version v1, lưu class dưới đúng package và tên như sau:

```java
package com.example.data;

import java.io.Serializable;

public class CustomerSnapshot implements Serializable {
    private static final long serialVersionUID = 7L;

    private String id;
    private String name;

    public CustomerSnapshot(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
}
```

Ứng dụng ghi:

```java
try (ObjectOutputStream out =
         new ObjectOutputStream(Files.newOutputStream(path))) {
    out.writeObject(new CustomerSnapshot("C-100", "An"));
}
```

File được tạo từ **binary v1** cần được lưu thành fixture bất biến để test. Đừng tạo fixture ngay từ class v2, vì như vậy không kiểm tra được khả năng đọc dữ liệu lịch sử.

### 5.2. Binary v2 đọc dữ liệu cũ

Giữ nguyên binary name `com.example.data.CustomerSnapshot` và UID:

```java
package com.example.data;

import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.Serial;
import java.io.Serializable;

public class CustomerSnapshot implements Serializable {
    @Serial
    private static final long serialVersionUID = 7L;

    private String id;
    private String name;
    private String locale;

    public CustomerSnapshot(String id, String name, String locale) {
        this.id = id;
        this.name = name;
        this.locale = locale;
    }

    @Serial
    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (id == null || id.isBlank()) {
            throw new java.io.InvalidObjectException("Missing id");
        }

        // Dữ liệu v1 không có locale: nhận null khi đọc.
        if (locale == null) {
            locale = "vi-VN";
        }
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getLocale() { return locale; }
}
```

Trong v2, `in.defaultReadObject()` đọc những field có trong stream và ghép vào local fields theo quy tắc. Field không có trong stream nhận giá trị mặc định; sau đó `readObject` có thể khôi phục invariant cho dữ liệu legacy.

Ví dụ test:

```java
try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(legacyPath))) {
    Object value = in.readObject();

    if (!(value instanceof CustomerSnapshot snapshot)) {
        throw new java.io.InvalidObjectException(
            "Unexpected root type"
        );
    }

    if (!"vi-VN".equals(snapshot.getLocale())) {
        throw new AssertionError("Legacy locale mapping failed");
    }
}
```

Ví dụ giả định dữ liệu fixture đáng tin cậy, code đã import `Files`/`Path`/`ObjectInputStream` và file đúng nguồn v1. Với dữ liệu không tin cậy, cần loại bỏ Java native deserialization khỏi ranh giới đó hoặc áp dụng chính sách bảo vệ nghiêm ngặt được đánh giá riêng.

### 5.3. Điều gì không được bảo đảm?

Nếu file v1 từng có field `locale` và giá trị thực sự `null` mang ý nghĩa riêng, kiểm tra `locale == null` không thể phân biệt “field vắng mặt” với “field có mặt nhưng null”. Trong trường hợp này, có thể dùng `ObjectInputStream.GetField` để xem trạng thái mặc định của field hoặc thiết kế version metadata rõ ràng.

Khi migration có nhiều phiên bản, tránh chồng quá nhiều phép đoán vào một giá trị null. Một schema version rõ ràng thường dễ kiểm soát hơn.

## 6. readObject, writeObject và defaultReadObject

### 6.1. Tùy biến quá trình đọc

Class `Serializable` có thể khai báo method private với chữ ký đặc biệt:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Khôi phục invariant hoặc xác minh dữ liệu.
}
```

`readObject` không phải method mà application gọi trực tiếp. Cơ chế serialization phát hiện method này theo quy tắc đặc tả.

Nếu dùng `readObject`, cần quyết định:

- Gọi `defaultReadObject()` hay xử lý persistent fields bằng `readFields()`.
- Validation nào cần chạy trước khi object được dùng.
- Cách thiết lập giá trị của field mới.
- Làm gì khi giá trị cũ không còn hợp lệ.
- Cách tránh hiệu ứng phụ nguy hiểm trong lúc object graph chưa được khôi phục hoàn toàn.

Không gọi method nghiệp vụ có thể phụ thuộc vào object graph đầy đủ quá sớm trong quá trình deserialize. Tránh đăng ký object vào singleton/registry từ bên trong `readObject` khi object chưa được validate hoàn chỉnh.

### 6.2. Tùy biến quá trình ghi

Ví dụ:

```java
@Serial
private void writeObject(ObjectOutputStream out)
        throws IOException {
    out.defaultWriteObject();
    // Có thể ghi phần dữ liệu bổ sung theo protocol của class.
}
```

Nếu ghi thêm optional data sau `defaultWriteObject()`, bên đọc cần hiểu cấu trúc/version của phần bổ sung. Thay đổi thứ tự và số lượng dữ liệu custom có thể làm stream cũ/mới không tương thích, ngay cả khi UID giống nhau.

Không nên thêm hoặc xóa `writeObject` một cách tùy tiện trong API đã có dữ liệu persistent. Cần đọc quy tắc versioning của Java Object Serialization và kiểm thử cả dữ liệu cũ.

### 6.3. Dùng GetField khi cần phân biệt field vắng mặt

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    ObjectInputStream.GetField fields = in.readFields();

    id = (String) fields.get("id", null);
    name = (String) fields.get("name", null);

    boolean absent = fields.defaulted("locale");
    locale = absent
        ? "vi-VN"
        : (String) fields.get("locale", null);
}
```

`defaulted("locale")` giúp xác định field có bị thiếu trong stream so với field hiện tại không. Để dùng cách này, field phải thuộc serializable fields được công bố của class hiện tại.

Đây là kỹ thuật phù hợp cho migration có phân biệt “field không tồn tại trong version cũ” với “field tồn tại và mang null”. Sau khi đọc, cần validate invariant và type assumptions.

### 6.4. readObjectNoData

Trong một số trường hợp class serializable xuất hiện trong local hierarchy nhưng không có class data tương ứng trong stream, cơ chế có thể gọi `readObjectNoData()` nếu được khai báo đúng.

```java
@Serial
private void readObjectNoData()
        throws java.io.ObjectStreamException {
    // Khôi phục trạng thái hợp lệ khi không có class data.
}
```

Đây không phải callback luôn chạy khi thêm một field mới. Nó phục vụ tình huống class data của **một lớp trong hierarchy** bị thiếu, chẳng hạn một số thay đổi hierarchy. Chỉ thêm method này khi có kịch bản evolution cụ thể và test chứng minh nó được gọi như mong muốn.

## 7. serialPersistentFields và đổi tên field có kiểm soát

`serialPersistentFields` cho class khai báo tập field sẽ xuất hiện trong serialized form một cách tường minh, độc lập một phần với field vật lý hiện tại.

Ví dụ khai báo:

```java
@Serial
private static final ObjectStreamField[] serialPersistentFields = {
    new ObjectStreamField("id", String.class),
    new ObjectStreamField("customerName", String.class)
};
```

Cơ chế thường đi kèm `writeObject`/`readObject` và `PutField`/`GetField` để ánh xạ giữa tên persistent field và representation hiện tại.

Một hướng migration:

- v1 có field `customerName`.
- v2 muốn dùng field trong memory tên `displayName`.
- v2 vẫn công bố serialized field `customerName` để đọc file cũ.
- `readObject` ánh xạ persistent field `customerName` sang `displayName`.
- `writeObject` quyết định ghi layout nào cho consumer được hỗ trợ.

Cách này phức tạp hơn việc dùng DTO tương thích, đặc biệt nếu phải hỗ trợ nhiều phiên bản trong một object graph. Không nên dùng `serialPersistentFields` như một mẹo “sửa mọi stream cũ”; phải có contract, test và tài liệu chính xác.

## 8. writeReplace, readResolve và Serialization Proxy Pattern

### 8.1. Vì sao cần proxy?

Một class nghiệp vụ có nhiều invariant, field transient, cache, lock hoặc thông tin nội bộ không nhất thiết nên được serialized theo layout trực tiếp. **Serialization Proxy Pattern** có thể giúp tách serialized form ổn định khỏi implementation class.

Trong mô hình này:

1. Object thực thi `writeReplace()` để thay bằng một proxy serializable.
2. Proxy chứa trạng thái dữ liệu tối thiểu, version và invariant đã chuẩn hóa.
3. Khi deserialize, proxy thực thi `readResolve()` để tạo một object domain hợp lệ.

Ví dụ khái quát:

```java
public final class Money implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String currency;
    private final long minorUnits;

    public Money(String currency, long minorUnits) {
        if (currency == null || currency.isBlank()) {
            throw new IllegalArgumentException("currency");
        }
        this.currency = currency;
        this.minorUnits = minorUnits;
    }

    @Serial
    private Object writeReplace() {
        return new SerializationProxy(currency, minorUnits);
    }

    private static final class SerializationProxy
            implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String currency;
        private final long minorUnits;

        SerializationProxy(String currency, long minorUnits) {
            this.currency = currency;
            this.minorUnits = minorUnits;
        }

        @Serial
        private Object readResolve() {
            return new Money(currency, minorUnits);
        }
    }
}
```

Ví dụ mô tả hướng tách serialized representation khỏi object domain. Với một implementation production, cần xem thêm cách chống direct deserialization của outer class và các quy tắc inheritance. Nếu proxy binary name hoặc serialized fields thay đổi, file cũ vẫn có thể bị ảnh hưởng.

### 8.2. readResolve không phải công cụ đổi package tự động

`readResolve` có thể trả về object thay thế sau khi class đã được deserialized. Nó không tự giải quyết việc JVM không thể tìm class mang binary name cũ trong stream.

Nếu đã đổi package, deserializer phải có khả năng nạp representation legacy hoặc có một cơ chế chuyển đổi stream được thiết kế riêng. Giữ legacy DTO/proxy thường đơn giản và đáng tin cậy hơn cố remap class descriptor tùy tiện.

## 9. Đổi tên class hoặc package và dữ liệu đã lưu

Giả sử v1:

```java
package com.example.legacy;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

V2 chuyển thành:

```java
package com.example.domain;

public class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

Hai class có **binary name khác nhau**. UID cùng bằng `1L` không có nghĩa file chứa `com.example.legacy.Customer` tự được đọc thành `com.example.domain.Customer`.

Các lựa chọn:

1. **Giữ class cũ:** vẫn cung cấp `com.example.legacy.Customer` để đọc stream cũ, rồi chuyển sang domain class mới qua adapter.
2. **Offline conversion:** dùng binary/classpath cũ để deserialize dữ liệu lịch sử trong môi trường an toàn, sau đó serialize sang format mới có version/schema.
3. **Custom resolution:** một số trường hợp có thể dùng `ObjectInputStream.resolveClass` tùy chỉnh, nhưng bị ràng buộc bởi class descriptor, hierarchy, tên, cấu trúc và type checking; không thể coi đó là phép đổi tên tùy ý an toàn.
4. **Duy trì legacy artifact:** nếu có dữ liệu chỉ được đọc hiếm khi, đóng gói một module/tiến trình chuyển đổi riêng để tránh làm phức tạp runtime chính.

Không tạo một class mới cùng UID rồi giả định mọi stream cũ sẽ mở được. Kế hoạch package migration phải bao gồm migration dữ liệu, không chỉ refactor import.

## 10. Thay đổi class hierarchy và constructor

### 10.1. Thêm hoặc bỏ Serializable ở superclass

Các quy tắc serialization khác nhau giữa class triển khai `Serializable` và superclass không serializable. Khi deserialize một object serializable thông thường, constructor của các lớp serializable trong chuỗi kế thừa không được chạy như trong `new`; constructor không tham số có thể truy cập của superclass không serializable đầu tiên được chạy theo quy tắc Java Object Serialization.

Nếu thêm/bỏ `Serializable` ở superclass hoặc chèn một lớp mới vào hierarchy, tập dữ liệu được ghi/đọc theo từng class có thể thay đổi. Class có thể được deserialize nhưng bỏ lỡ invariant hoặc trạng thái được khởi tạo trước đây.

### 10.2. Non-serializable superclass phải phù hợp

Nếu superclass không serializable không có constructor không tham số thích hợp để cơ chế khôi phục object gọi, quá trình deserialize có thể thất bại, ví dụ bằng `InvalidClassException`.

Ví dụ rủi ro:

```java
class BaseEntity {
    BaseEntity(String tenant) {
    }
}

class ChildSnapshot extends BaseEntity implements Serializable {
    private static final long serialVersionUID = 1L;

    ChildSnapshot(String tenant) {
        super(tenant);
    }
}
```

Nếu class này cần được deserialize bằng Java serialization, phải xét constructor của non-serializable superclass theo yêu cầu cơ chế. Không thể chỉ nhìn constructor của `ChildSnapshot`.

### 10.3. Thay đổi field trong superclass

Nếu một field di chuyển giữa subclass và superclass, serialized form có thể thay đổi vì dữ liệu của từng serializable class trong hierarchy được ghi theo class descriptor tương ứng. Không nên giả định cùng field name/type là đủ để tự động chuyển đúng giá trị qua các tầng.

Cần kiểm tra:

- Thứ tự lớp trong hierarchy.
- Class data trong stream cũ.
- UID của từng serializable class.
- Trạng thái field thuộc class nào.
- `readObject`/`readObjectNoData` và các hook.
- Invariant cần được khôi phục khi constructor không chạy.

## 11. Serializable record và enum

### 11.1. Record có cơ chế serialization riêng

Java records có quy tắc Java Object Serialization riêng so với ordinary serializable classes. Record cần triển khai `Serializable` nếu muốn serialized bằng cơ chế này.

```java
import java.io.Serializable;

public record CustomerRecord(String id, String name)
        implements Serializable {
    public CustomerRecord {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id");
        }
    }
}
```

Khi deserialize record, cơ chế sử dụng **canonical constructor** để tạo record từ các component values. Vì thế invariant trong canonical constructor có thể được áp dụng trong quá trình khôi phục. Khác với ordinary serializable class, các serialization hooks như `readObject`/`writeObject` không được dùng theo cùng cơ chế thông thường của record.

Yêu cầu kiểm tra matching `serialVersionUID` được xử lý đặc biệt đối với record classes; không nên dùng suy luận dành cho ordinary serializable class rồi áp vào record một cách máy móc. Hãy đánh giá theo đặc tả record serialization của JDK mục tiêu.

Nếu bổ sung record component, dữ liệu cũ có thể không có component mới và giá trị mặc định sẽ được truyền vào canonical constructor, có thể khiến validation thất bại. Đổi component name/type cũng ảnh hưởng serialized form.

### 11.2. Enum serialized theo tên constant

Enum có cơ chế serialization riêng: danh tính constant được ghi chủ yếu qua tên enum type và tên constant. UID không được xử lý như ordinary class và các hooks serialization thường không có cùng tác dụng.

Ví dụ:

```java
public enum Status {
    NEW,
    ACTIVE,
    DISABLED
}
```

Nếu stream cũ chứa `ACTIVE` mà v2 đổi tên thành `ENABLED`, deserializer không tự suy ra đó là constant tương đương. Dữ liệu cũ có thể không đọc được, ví dụ lỗi `InvalidObjectException` khi không tìm thấy enum constant.

Với dữ liệu persistent, cân nhắc giữ constant cũ trong giai đoạn chuyển tiếp hoặc ánh xạ sang mã nghiệp vụ ổn định trong format dữ liệu bên ngoài. Không đổi enum constant names mà chưa kiểm tra persisted payload.

## 12. Externalizable: quyền kiểm soát lớn hơn, trách nhiệm cũng lớn hơn

Một class triển khai `Externalizable` tự quyết định cách ghi/đọc phần dữ liệu qua `writeExternal` và `readExternal`.

```java
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectOutput;

public class EventEnvelope implements Externalizable {
    private static final long serialVersionUID = 1L;

    private int formatVersion;
    private String eventId;

    public EventEnvelope() {
        // Public no-arg constructor cần cho Externalizable.
    }

    public EventEnvelope(String eventId) {
        this.formatVersion = 1;
        this.eventId = eventId;
    }

    @Override
    public void writeExternal(ObjectOutput out) throws IOException {
        out.writeInt(formatVersion);
        out.writeUTF(eventId);
    }

    @Override
    public void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException {
        int version = in.readInt();

        if (version == 1) {
            eventId = in.readUTF();
            formatVersion = version;
        } else {
            throw new java.io.InvalidObjectException(
                "Unsupported event format: " + version
            );
        }
    }
}
```

Cấu trúc này chỉ là ví dụ tối thiểu. `Externalizable` vẫn tham gia Java Object Serialization Protocol và class identity; nó không biến dữ liệu thành một giao thức trung lập JDK/ngôn ngữ.

Điểm cần chú ý:

- Cần có constructor public không tham số phù hợp.
- Developer tự quản lý thứ tự/kiểu dữ liệu khi ghi và đọc.
- Đổi thứ tự hoặc bỏ một trường mà không có version handling dễ làm file cũ không đọc được.
- `writeUTF` có format Modified UTF-8 riêng; không nên coi nó giống UTF-8 phổ thông của giao thức ngoài Java.
- Version marker phải được đọc trước phần payload và hướng xử lý unknown version phải được xác định.
- Kiểm tra cả truncated stream, giá trị thiếu, malformed length và payload độc hại.

Nếu hệ thống đã dùng `Externalizable`, đọc code `writeExternal`/`readExternal` quan trọng hơn đoán compatibility theo default field evolution.

## 13. Generics, proxy, collection và object graph

### 13.1. Đổi generic argument không giống đổi serialized field type

Giả sử v1 có:

```java
private List<String> tags;
```

v2 đổi thành:

```java
private List<Integer> tags;
```

Ở mức erased field type, cả hai vẫn là `List`. Stream có thể tiếp tục được đọc nếu các điều kiện khác phù hợp. Nhưng nếu v2 duyệt `List<Integer>` và cast từng phần tử, dữ liệu `String` trong stream cũ có thể dẫn tới `ClassCastException` hoặc xử lý sai.

Điều này cho thấy Java serialization compatibility cần cả **kiểm tra dữ liệu thực** chứ không chỉ descriptor.

### 13.2. Collection implementation cũng nằm trong graph

Object field kiểu `List` có thể chứa instance `ArrayList`, `LinkedList`, unmodifiable wrapper hoặc collection tùy biến. Stream chứa concrete object type chứ không chỉ field declaration `List`.

Khi nâng dependency hoặc JDK, cần xem các concrete class trong dữ liệu cũ. Một collection wrapper hoặc library-specific class bị loại bỏ có thể khiến dữ liệu không đọc được dù model root giữ nguyên.

Nếu schema cần sống lâu, đừng phụ thuộc quá nhiều vào serialized form của những class nội bộ thư viện hoặc implementation details.

### 13.3. Dynamic proxy và class của framework

Framework có thể đưa dynamic proxy, lazy-loading proxy, generated subclass hoặc session object vào graph. Một số proxy không serializable, một số yêu cầu container/provider cụ thể khi đọc lại.

Vấn đề thường chỉ xuất hiện trong session replication hoặc distributed cache khi ứng dụng nâng framework. Nên ưu tiên lưu DTO/state rõ ràng thay vì nguyên object đang gắn với runtime container, connection, thread, lock hoặc persistence context.

## 14. Security: Java deserialization không dành cho dữ liệu không tin cậy

### 14.1. Nguy cơ không chỉ là class mismatch

Java native deserialization có thể kích hoạt code qua class loading, serialization hooks và các object graph không được mong đợi. Nếu dữ liệu từ người không tin cậy có thể đi vào `ObjectInputStream`, hệ thống có thể gặp rủi ro nghiêm trọng tùy classpath và cách sử dụng.

Nguyên tắc an toàn:

- **Không deserialize Java native objects từ request, message hoặc file không tin cậy** nếu có thể chọn format khác.
- Không dựa vào `serialVersionUID` như cơ chế xác thực dữ liệu.
- Không tin rằng dữ liệu được Base64 hóa hoặc nén là an toàn.
- Không chỉ catch exception rồi cho rằng object đã được xử lý an toàn.
- Ưu tiên schema-based format, allowlist dữ liệu và validation nghiệp vụ ở boundary.

### 14.2. ObjectInputFilter

JDK 9 bổ sung serialization filtering (JEP 290). JDK 17 bổ sung context-specific deserialization filters (JEP 415), cho phép cấu hình chính sách lọc theo ngữ cảnh. Filter có thể giới hạn loại class, độ sâu graph, số reference và byte count.

Ví dụ chính sách minh họa dành cho một nguồn nội bộ **đã xác thực và được tin cậy**, không phải cấp quyền mặc định cho dữ liệu từ Internet:

```java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
    "maxdepth=20;maxrefs=5000;maxbytes=1048576;" +
    "com.example.model.**;java.lang.*;java.util.*;!*"
);

try (ObjectInputStream in =
         new ObjectInputStream(Files.newInputStream(path))) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
```

Đây chỉ là mẫu minh họa cú pháp filter. Một chính sách production phải cho phép **đúng những class thực sự cần**, tránh mở cả package quá rộng, có giới hạn size/depth phù hợp và được kiểm thử bằng payload hợp lệ lẫn payload bất thường. Filter không thay thế authentication, data provenance, validation, cập nhật dependency và nguyên tắc không nhận untrusted native serialization.

### 14.3. Migration file cũ trong môi trường cách ly

Nếu dữ liệu lịch sử không chắc chắn nguồn gốc, việc đọc file cũ bằng toàn bộ application classpath có thể làm tăng rủi ro. Khi cần data conversion, cân nhắc:

- Tiến trình chuyên dụng có quyền hạn tối thiểu.
- Classpath rút gọn gồm các class legacy cần thiết.
- Giới hạn CPU, bộ nhớ, file system, network và thời gian xử lý.
- Filter, kích thước tối đa và validation của payload.
- Log/checksum về file được chuyển đổi và kết quả.
- Không chạy converter với production secret nếu không cần.

Dữ liệu sau chuyển đổi nên được xuất sang format có schema/version rõ ràng để giảm phụ thuộc lâu dài vào Java object graph.

## 15. Tại sao nâng JDK 17 lên 21 vẫn có thể ảnh hưởng dữ liệu Serializable?

Java Object Serialization là một cơ chế có đặc tả chung; JDK 21 không tự động làm mọi file do JDK 17 ghi trở nên không đọc được. Nhưng trong một đợt nâng JDK, thường còn có những thay đổi đồng thời:

- Framework/driver/collection library được nâng hoặc thay thế.
- Class được refactor, đổi package hoặc thay hierarchy.
- JDK mới kích hoạt quy tắc bảo mật hoặc filter cấu hình khác.
- Artifact được đóng gói theo cách khác, làm thiếu class cần đọc.
- Một class trong object graph thuộc thư viện trước đây còn trên classpath nhưng nay bị loại bỏ.
- Serialization hook tùy biến có phụ thuộc implementation detail.
- Source được biên dịch lại làm thay default UID vì chưa khai báo explicit UID.
- Dữ liệu cũ và mới cùng tồn tại trong rolling deployment.

Đừng mặc định “JDK 21 làm hỏng stream” khi nguyên nhân thật là thay version domain model hoặc thiếu dependency. Cần thử **cùng binary và cùng dữ liệu** trên các runtime, sau đó thay từng biến để cô lập nguyên nhân.

JEP 400 thay default charset từ JDK 18 đối với nhiều API text, nhưng **ObjectOutputStream ghi định dạng nhị phân theo serialization protocol**, không dựa vào `Charset.defaultCharset()` để encode stream như một file text thông thường. Nếu lỗi liên quan encoding, hãy kiểm tra đoạn code đọc/ghi text bao ngoài hoặc custom serialization đang tự chuyển byte/string, không kết luận toàn bộ Java serialized stream đổi charset.

## 16. Đọc cả dữ liệu cũ và mới trong rolling deployment

### 16.1. Một chiều và hai chiều là hai yêu cầu khác nhau

Thông thường migration dữ liệu có hai chiều:

- **Backward read:** phiên bản mới đọc dữ liệu do phiên bản cũ tạo ra.
- **Forward read:** phiên bản cũ đọc dữ liệu do phiên bản mới tạo ra.

Nếu rollout theo cách toàn bộ server v1 được thay bởi v2 và không có rollback đọc state mới, có thể chỉ cần backward read. Nhưng nếu có rolling deployment hoặc blue-green, v1 và v2 có thể cùng đọc/ghi một cache, queue hoặc session store trong thời gian chuyển tiếp.

Khi đó phải xem xét **hai chiều**.

### 16.2. Ví dụ thêm field

V2 thêm `locale` và giữ UID tương thích. V2 đọc stream v1 thì field mới mặc định null, có thể xử lý bằng `readObject`. Ngược lại, v1 đọc stream v2 có thể bỏ qua field `locale` vì không biết nó tồn tại.

Tuy nhiên, nếu v2 bắt đầu yêu cầu `locale` để xác định currency/date formatting hoặc ghi state theo business semantics mới, v1 không hiểu thông tin đó. Về mặt kỹ thuật stream có thể đọc được nhưng nghiệp vụ vẫn không tương thích.

Do đó cần ma trận:

| Writer | Reader | Điều cần kiểm tra |
|---|---|---|
| v1 | v1 | Baseline |
| v1 | v2 | Đọc dữ liệu lịch sử, default/migration |
| v2 | v2 | Chức năng mới |
| v2 | v1 | Rolling deployment, rollback, bỏ qua field mới có an toàn không |

Không phải mọi sản phẩm bắt buộc hỗ trợ v2 → v1. Nhưng nếu không hỗ trợ, phải thiết kế deployment để không có phiên bản cũ đọc state mới.

### 16.3. Cách giảm rủi ro shared persistent state

Một số chiến lược:

- Giữ schema serialized form ổn định trong toàn bộ rolling window.
- Tách cache namespace hoặc key prefix theo version.
- Đưa migration code trước, thay writer format sau.
- Chuyển state sang DTO/schema ổn định và có version.
- Dùng versioned serializer hoặc upcaster khi framework hỗ trợ.
- Xác định lúc nào có thể xóa cache hoặc rehydrate từ nguồn dữ liệu gốc.

Nếu chỉ là cache có thể tạo lại, có thể invalidation theo version có chủ đích. Nếu là dữ liệu nghiệp vụ quan trọng, cần migration/recovery plan, không dùng “clear cache” như một cách giải quyết chung.

## 17. Golden-file compatibility tests

### 17.1. Golden file là dữ liệu do binary cũ tạo ra thật

Một bài test serialization chỉ tạo object và đọc lại trong cùng một version không phát hiện đủ vấn đề evolution. Cần lưu **fixture stream do version cũ thực sự ghi**.

Quy trình:

1. Checkout/bảo tồn binary v1 và dependency của nó.
2. Chạy chương trình v1 để tạo stream với object graph đại diện.
3. Lưu file `.ser` vào test fixtures hoặc artifact repository có kiểm soát.
4. Ghi checksum, producer version, UID, classpath và ngữ cảnh dữ liệu.
5. Dùng binary v2 đọc file đó và xác minh nội dung.
6. Với rolling/rollback, tạo thêm file v2 để binary v1 đọc thử nếu cam kết.
7. Giữ test chạy trên JDK/runtime tối thiểu và đích khi sản phẩm hỗ trợ nhiều JDK.

Không chỉnh sửa byte fixture bằng tay hoặc chỉ thay byte của serialVersionUID để cho test pass. Điều đó không đánh giá đúng stream đã phát hành.

### 17.2. Dùng hai classpath riêng cho v1 và v2

Không thể đưa hai bản cùng binary name `com.example.data.CustomerSnapshot` vào cùng một class loader rồi hy vọng JVM chọn “v1 cho ghi, v2 cho đọc” theo ý định. Hãy tạo **hai tiến trình hoặc hai môi trường classpath** riêng:

```text
Producer JVM:
  classpath = app-v1.jar + dependencies-v1
  action    = write test-data/customer-v1.ser

Consumer JVM:
  classpath = app-v2.jar + dependencies-v2
  action    = read test-data/customer-v1.ser
```

Nếu dùng một JVM với nhiều class loader tùy chỉnh, test sẽ phức tạp hơn và dễ nhầm class identity. Hai tiến trình độc lập thường là cách đơn giản hơn để mô phỏng deployment thật.

### 17.3. Bộ dữ liệu đại diện

Không chỉ tạo một object có mọi field khác null. Nên có:

- Object với field null, rỗng và dữ liệu default.
- Object có nested references và collection.
- Object graph có cycle và shared references.
- Enum values cũ, kể cả những value sắp bị deprecated.
- Dữ liệu có ngày giờ, số tiền và ký tự Unicode.
- Subclass/polymorphic object trong field kiểu interface/base.
- Object có field transient hoặc state được custom serialization.
- Dữ liệu đại diện từ nhiều version cũ còn được hỗ trợ.
- Stream bị cắt/ngắt hoặc corrupt để kiểm tra fail-safe behavior, trong môi trường test an toàn.

### 17.4. Điều cần assertion

- Root object đúng kiểu và có thể deserialize.
- Các field nghiệp vụ giữ đúng giá trị.
- Field mới có default/mapping đúng.
- Invariant/validation được áp dụng.
- Collection contents, reference identity và relationship đúng.
- Không mất trạng thái cần giữ qua read/write cycle.
- Lỗi dữ liệu không hợp lệ bị từ chối thay vì silently accepted.
- Không có unexpected class/provider loading.
- Nếu cần tương thích hai chiều, binary v1 đọc được v2 output theo contract.

### 17.5. Kiểm soát test fixture

Ghi metadata bên cạnh file:

```yaml
fixture: customer-v1.ser
producer:
  application_version: "1.4.2"
  jdk: "17"
  class_name: "com.example.data.CustomerSnapshot"
  serial_version_uid: 7
scenario: "Customer with nullable legacy fields"
expected_reader_versions:
  - "2.x"
```

Đây là ví dụ metadata; nên bổ sung vendor/update JDK, checksum và reference commit. Không đưa dữ liệu production có thông tin cá nhân hoặc secret vào repository chỉ để tạo fixture.

## 18. Lỗi thường gặp và cách truy nguyên

| Triệu chứng | Nguyên nhân khả dĩ | Bước điều tra |
|---|---|---|
| `InvalidClassException`, UID mismatch | Default UID thay đổi hoặc explicit UID khác | Lấy UID của binary cũ và mới bằng `serialver`/`ObjectStreamClass` |
| `InvalidClassException`, incompatible field types | Serialized field cùng tên nhưng đổi kiểu không tương thích | So sánh descriptor field và stream schema |
| `ClassNotFoundException` | Binary name trong stream không có trên classpath reader | Kiểm tra package rename, dependency và class loader |
| `NoClassDefFoundError` | JVM cần class liên quan nhưng không tìm được/nạp được | So sánh object graph và runtime classpath |
| `ClassCastException` | Generic field erasure giữ nguyên nhưng dữ liệu thực đổi kiểu | Kiểm tra collection elements và cast |
| `InvalidObjectException` | Validation/hook từ chối object hoặc enum name không tồn tại | Xem business invariant, enum evolution và stack trace |
| `StreamCorruptedException` | Header/stream content không đúng serialization protocol | Kiểm tra file bị ghi đè, cắt, nén, bọc sai |
| `EOFException` | Stream thiếu byte hoặc kết thúc sớm | Kiểm tra file size, writer, crash, atomic file publish |
| `OptionalDataException` | Custom serialization protocol không khớp | So sánh `writeObject`/`readObject` hoặc Externalizable |
| `WriteAbortedException` | Writer đã gặp exception khi serialize | Xem nguyên nhân được ghi trong stream/stack trace |
| Đọc xong nhưng field mới null | Field không có trong stream cũ | Gán migration default, dùng GetField/validation |
| Đọc xong nhưng nghiệp vụ sai | Schema/semantic change, hook không chạy như tưởng | Behavioral golden test và invariant checks |

Không phải mọi thông báo nêu trên đều duy nhất một nguyên nhân. Ghi stack trace đầy đủ, tên class, source version, runtime classpath và dữ liệu fixture trước khi sửa.

## 19. Công cụ hỗ trợ kiểm tra

### 19.1. serialver

Kiểm tra UID do Java định nghĩa cho class:

```bash
serialver -classpath legacy.jar com.example.data.CustomerSnapshot
serialver -classpath current.jar com.example.data.CustomerSnapshot
```

Nếu tool/version không có trên image runtime tối giản, chạy nó từ JDK toolchain phù hợp. Đừng dựa vào việc source vừa compile lại nếu muốn biết UID lịch sử; hãy dùng artifact cũ thật.

### 19.2. javap

Kiểm tra class binary, field và method hooks:

```bash
javap -classpath legacy.jar -private com.example.data.CustomerSnapshot
javap -classpath current.jar -private com.example.data.CustomerSnapshot
javap -classpath current.jar -verbose com.example.data.CustomerSnapshot
```

`javap` giúp xem declaration/bytecode nhưng không tự đọc nội dung stream đã lưu. Đối chiếu nó với file fixture và classpath test.

### 19.3. API diff và dependency graph

japicmp, Revapi hoặc công cụ tương tự có thể hỗ trợ so sánh class/method/field API. Tuy nhiên, nhiều serialized field là private và không nằm trong public API contract; phải cấu hình diff phù hợp hoặc so sánh trực tiếp serialized fields, UID và hooks.

Dùng Gradle/Maven dependency graph để xác định class implementation nào được chọn ở runtime. Một thư viện bị nâng version có thể đổi concrete class trong persisted graph ngay cả khi domain root class không đổi.

### 19.4. Logging và observability

Ghi nhận class name, fixture/version identifier, UID mismatch, số bản ghi chuyển đổi thành công/thất bại, thời gian xử lý và lỗi validation. Không log nguyên object serialized hoặc nội dung nhạy cảm. Với batch conversion, cần thống kê rõ bản ghi thành công, bỏ qua, lỗi và có thể retry.

## 20. Chiến lược chuyển khỏi Java native serialization

Java Object Serialization phù hợp với một số cơ chế nội bộ được kiểm soát, nhưng không phải lựa chọn lý tưởng cho dữ liệu nghiệp vụ lưu nhiều năm hoặc giao thức giữa nhiều ngôn ngữ. Nó gắn chặt với class name và runtime object graph, làm tăng chi phí class evolution.

Nếu phải giảm rủi ro dài hạn, cân nhắc:

| Lựa chọn | Ưu điểm | Cần quản lý |
|---|---|---|
| JSON + schema/version | Dễ đọc, tích hợp đa ngôn ngữ | Validation, field naming, polymorphism |
| Protobuf | Field numbers và schema evolution rõ | Quy tắc reuse field number, compatibility |
| Avro | Schema-based serialization, reader/writer schema | Schema registry, defaults, resolution |
| XML + XSD | Contract rõ và phổ biến ở tích hợp lâu đời | Namespace, schema, parser security |
| Database schema | Truy vấn được, có migration tooling | Transaction, schema/backfill |
| Custom versioned binary codec | Kiểm soát format và overhead | Chi phí đặc tả, kiểm thử, bảo trì |

Không cần chuyển toàn bộ dữ liệu một lần. Có thể xây một **legacy reader → canonical DTO → new writer**:

```text
Legacy .ser files
      |
      v
Isolated legacy reader (trusted inputs, limited permissions)
      |
      v
Validation and explicit version mapping
      |
      v
Canonical DTO/schema
      |
      v
New versioned data format
```

Kế hoạch cần trả lời:

1. Ai sở hữu dữ liệu và thời hạn lưu trữ?
2. Có được phép convert offline/dừng ghi trong thời gian chuyển đổi không?
3. Có nhiều ứng dụng cùng đọc state không?
4. Cần rollback hoặc dual-read/dual-write bao lâu?
5. Làm sao xác nhận không mất dữ liệu?
6. Hệ thống có yêu cầu audit, encryption và retention không?

Không coi đổi format là “xong” chỉ vì một file test đọc được; cần inventory, migration batches, reconciliation và recovery.

## 21. Quy trình migration theo từng bước

### Bước 1: Kiểm kê cơ chế ghi dữ liệu

Tìm `ObjectOutputStream`, `ObjectInputStream`, `Serializable`, `Externalizable`, framework cache/session serializer và các nơi lưu file/state. Xác định dữ liệu có thể bỏ, có thể tạo lại hay bắt buộc giữ.

### Bước 2: Chụp baseline từ phiên bản thực tế

Lưu binary cũ, UID, class names, object graph, dependency versions và fixture từ dữ liệu đại diện. Không tạo baseline bằng source đã refactor.

### Bước 3: Xác định hướng tương thích

Chốt cần v2 đọc v1 hay cả v1 đọc v2. Xác định rolling deployment/rollback và thời gian nhiều version cùng tồn tại.

### Bước 4: Phân tích class evolution

Liệt kê field thêm/bớt/đổi tên/đổi kiểu, transient/static changes, hierarchy changes, enum/record/proxy, custom hooks và Externalizable format. So sánh class descriptor và UID.

### Bước 5: Thiết kế representation hoặc adapter

Giữ cùng serialized class name/UID khi hợp lý, thêm `readObject`/GetField cho default và validation, hoặc xây converter/serialization proxy. Với breaking change lớn, chọn schema versioned format mới.

### Bước 6: Viết compatibility tests

Đọc golden files từ v1 trên v2, kiểm tra invariant. Nếu cần hỗ trợ hai chiều, đọc file v2 bằng v1. Tách producer/consumer classpath.

### Bước 7: Kiểm tra bảo mật và lỗi dữ liệu

Giới hạn nguồn dữ liệu, validate stream, đặt filter trong phạm vi phù hợp và test corrupted/truncated payload. Không đọc dữ liệu không tin cậy trực tiếp bằng native deserialization.

### Bước 8: Chạy thử trên artifact và runtime đích

Test đúng JDK vendor/build, library/framework versions, container classpath và format state production. Không chỉ chạy từ IDE.

### Bước 9: Chuyển đổi dữ liệu và giám sát

Nếu cần offline conversion, chạy theo batch có checkpoint, checksum, thống kê và rollback. Với live state, xác định dual-write/dual-read window và cách đóng việc phiên bản cũ.

### Bước 10: Đóng migration có bằng chứng

Lưu UID/class map, compatibility matrix, fixture checksum, test report, data conversion log, deployment plan và recovery procedure. Không xóa legacy reader cho đến khi thời hạn giữ dữ liệu và rollback đã kết thúc theo chính sách.

## 22. Checklist trước khi phát hành

- [ ] Đã xác định chính xác nơi dùng Java Object Serialization.
- [ ] Đã phân biệt dữ liệu cache có thể tạo lại với dữ liệu nghiệp vụ phải giữ.
- [ ] Đã lưu binary/UID/classpath của phiên bản ghi stream cũ.
- [ ] Mỗi class serializable có chính sách `serialVersionUID` được kiểm soát.
- [ ] Đã rà soát field thêm, bớt, đổi tên, đổi kiểu, `transient` và `static`.
- [ ] Đã kiểm tra các class trong object graph, không chỉ root object.
- [ ] Đã rà soát class/package rename và binary name trong stream.
- [ ] Đã kiểm tra superclass, constructors, `readObjectNoData` và hierarchy.
- [ ] Đã rà soát `readObject`/`writeObject`/`readResolve`/`writeReplace`.
- [ ] Đã kiểm tra class `Externalizable` và version marker của custom format.
- [ ] Đã kiểm tra enum constant rename và record component evolution.
- [ ] Đã xác minh generic collection types và runtime cast behavior.
- [ ] Đã chạy golden-file tests: binary v2 đọc stream do binary v1 ghi.
- [ ] Nếu rolling deployment/rollback yêu cầu, đã kiểm tra v1 đọc stream v2.
- [ ] Đã thử dữ liệu null, rỗng, nested/cyclic và stream lỗi.
- [ ] Đã xác định chính sách deserialization security và input filter.
- [ ] Đã chạy artifact cuối với đúng JDK/library/container runtime.
- [ ] Có mapping hoặc converter cho các thay đổi không tương thích.
- [ ] Có kiểm soát checksum, audit và khả năng khôi phục dữ liệu.
- [ ] Đã cập nhật tài liệu schema/version và thời hạn duy trì legacy reader.

**Thay đổi một class `Serializable` không chỉ là thay đổi code:** nó có thể là thay đổi định dạng dữ liệu đã được ghi trong quá khứ. Giữ `serialVersionUID` có chủ đích, hiểu quy tắc evolution của field và hierarchy, quản lý các serialization hooks, đồng thời kiểm tra bằng golden files do binary cũ tạo ra là cách chứng minh ứng dụng mới đọc được dữ liệu cũ. Với dữ liệu có vòng đời dài, một format có schema/version rõ ràng và quy trình chuyển đổi được kiểm soát thường bền vững hơn việc gắn chặt trạng thái lưu trữ vào class Java nội bộ.
