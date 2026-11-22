# `readObjectNoData()` và thay đổi hệ phân cấp trong Java Serialization

## 1. Vấn đề: lớp hiện tại có thể có superclass mà dữ liệu cũ chưa từng biết

`java.io.Serializable` cho phép một chương trình ghi object bằng `ObjectOutputStream` rồi đọc lại bằng `ObjectInputStream`. Tuy nhiên, giữa lúc ghi và lúc đọc, cấu trúc lớp có thể được sửa đổi. Một tình huống đặc biệt là **phiên bản mới chèn thêm một superclass có triển khai `Serializable`** vào hệ phân cấp.

Ví dụ phiên bản cũ:

```text
Object
  └── Receipt implements Serializable
        └── id
```

Phiên bản mới:

```text
Object
  └── AuditInfo implements Serializable    // MỚI thêm
        └── source
        └── Receipt implements Serializable // Cùng tên và serialVersionUID
              └── id
```

Dữ liệu đã ghi ở phiên bản cũ biết về `Receipt` nhưng **không có mô tả/lớp dữ liệu `AuditInfo`**. Khi dựng object bằng phiên bản mới, JVM vẫn phải tạo phần trạng thái của `AuditInfo`, nhưng nó không thể đọc những byte dành riêng cho lớp này từ stream cũ, bởi vì chúng **không tồn tại**.

Đó chính là hoàn cảnh mà phương thức đặc biệt **`private void readObjectNoData() throws ObjectStreamException`** được Java Serialization định nghĩa để xử lý.

Sau bài học, bạn sẽ:

1. Biết **khi nào `readObjectNoData()` được gọi** và khi nào không.
2. Phân biệt nó với `readObject(ObjectInputStream)`, `defaultReadObject()`, constructor và field initializer.
3. Hiểu vì sao thay đổi hệ phân cấp có thể làm những field mới mang giá trị mặc định `null`, `0`, `false`.
4. Viết ví dụ **hai phiên bản nguồn Java cùng tên lớp**, serialize bằng phiên bản 1 và deserialize bằng phiên bản 2 để tái hiện callback chính xác.
5. Xác định vai trò của `serialVersionUID`, giới hạn tương thích và chính sách từ chối stream không hợp lệ.
6. Thiết kế migration state an toàn, tránh suy luận rằng mọi thay đổi trong lớp đều kích hoạt callback này.

Phạm vi bài là **Java Object Serialization mặc định cho các lớp thông thường triển khai `Serializable`**, không áp dụng nguyên xi cho enum, record hay `Externalizable`.

## 2. Serial stream chứa những gì?

Khi ghi một object:

```java
try (ObjectOutputStream output = new ObjectOutputStream(
        Files.newOutputStream(path))) {
    output.writeObject(someSerializableObject);
}
```

Đây là **snippet**: `path` và `someSerializableObject` đã được khai báo, cần import và xử lý checked exceptions. `ObjectOutputStream` mã hóa object graph theo giao thức Serialization: mô tả kiểu, thông tin version và dữ liệu các field cần serialize, theo từng lớp trong hierarchy tương ứng.

Khi đọc:

```java
try (ObjectInputStream input = new ObjectInputStream(
        Files.newInputStream(path))) {
    Object value = input.readObject();
}
```

Đây cũng chỉ là snippet. `ObjectInputStream` khôi phục object bằng các **định nghĩa lớp hiện diện ở phía người đọc**. Nó so sánh thông tin của stream với các lớp local và phải xử lý tình huống stream cũ / local class mới.

Điểm dễ quên: serial stream **không** chứa toàn bộ byte của object trong heap. Nó chứa các trường/mô tả theo Serialization protocol. Các biến `static` và `transient` không được ghi theo cơ chế field mặc định; field initializer và constructor của **serializable classes** không tự động được gọi chỉ để khôi phục field. Việc khôi phục theo từng lớp rất quan trọng khi hierarchy thay đổi.

Với một hierarchy như:

```text
A (không Serializable)
  └── B implements Serializable
        └── C implements Serializable
```

Khi deserialize instance của `C` theo giao thức thông thường:

- JVM khởi tạo object với giá trị mặc định của các field.
- Constructor no-arg của lớp **không serializable gần nhất** (`A`) được gọi theo cơ chế Serialization.
- Constructor và field initializer của `B` và `C` **không chạy theo đường tạo instance thông thường**.
- State của các lớp Serializable được khôi phục theo thứ tự từ superclass xuống subclass. Với mỗi class có dữ liệu tương ứng, Java dùng default field restoration hoặc hook `readObject` của class đó.
- Với một **Serializable class hiện diện ở hierarchy local nhưng không có slot dữ liệu tương ứng trong stream**, Java có thể gọi hook `readObjectNoData` của class ấy.

## 3. Chính xác `readObjectNoData()` làm gì?

Theo Java SE 17, chữ ký đặc biệt là:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    // Khởi tạo các field được khai báo bởi chính lớp này,
    // nếu stream không liệt kê lớp này là superclass tương ứng.
}
```

Đây là **snippet**, phải nằm bên trong một class `Serializable`, có import `java.io.Serial` và `java.io.ObjectStreamException`. Annotation `@Serial` được hỗ trợ ở Java 17, giúp công cụ biên dịch/lint nhận diện các khai báo liên quan cơ chế Serialization; bản thân annotation **không** quyết định việc callback được gọi.

### Hợp đồng kích hoạt

Hook được gọi khi quá trình deserialize một instance của subclass và **serialization stream không liệt kê một Serializable class local là một superclass của instance đó**. Kịch bản điển hình là bên ghi dùng phiên bản có hierarchy ngắn hơn; bên đọc dùng phiên bản đã thêm một Serializable superclass mới.

Java cũng mô tả khả năng stream không đầy đủ hoặc đã bị can thiệp làm thiếu class data, nên hook này còn hữu ích để **khôi phục invariant** hoặc từ chối trạng thái không an toàn.

### Điều kiện KHÔNG đủ để gọi hook

- **Thêm field mới vào chính class cũ** không tự động kích hoạt `readObjectNoData()`; slot dữ liệu của class đó vẫn có trong stream. Field mới không có giá trị trong stream thường nhận giá trị mặc định của kiểu.
- Một field trong stream có giá trị `null` không đồng nghĩa **không có class data**.
- Khi class local vẫn có dữ liệu tương ứng và khai báo `readObject(ObjectInputStream)`, Java xử lý qua `readObject` (nếu hợp lệ), **không** dùng `readObjectNoData` chỉ vì có field thiếu.
- Gọi `new MyClass()` thông thường không chạy `readObjectNoData`.
- Không nên coi “thêm mọi superclass” đều kích hoạt: điều quan trọng là **lớp Serializable local cụ thể không có slot tương ứng trong stream**, và toàn bộ hierarchy vẫn thỏa các yêu cầu tương thích khác.
- `Externalizable` có giao thức riêng qua `readExternal` và constructor public no-arg; không thay thế `readExternal` bằng hook này.

### Phạm vi trách nhiệm

`readObjectNoData()` phải khôi phục **các field và invariant của chính class định nghĩa hook**, thay vì cố đọc data của subclass. Không có tham số `ObjectInputStream`, bởi vì **không có dữ liệu dành riêng cho class này để đọc**.

Nó có thể ném `ObjectStreamException`, thường dùng subclass `InvalidObjectException` khi không có cách an toàn để khôi phục trạng thái.

## 4. Phân biệt các Serialization hooks

| Hook / cơ chế | Khi nào liên quan | Vai trò |
| --- | --- | --- |
| `private void writeObject(ObjectOutputStream out)` | Khi serialize một Serializable class có custom write | Ghi default/custom data cho **slot của lớp đó** |
| `private void readObject(ObjectInputStream in)` | Khi stream có class data tương ứng và class khai báo hook hợp lệ | Đọc/khôi phục state của lớp, có thể gọi `defaultReadObject()` |
| `private void readObjectNoData()` | Khi local Serializable superclass có **không có slot tương ứng** trong stream | Khởi tạo/reject state của lớp vì không có data để đọc |
| `in.defaultReadObject()` | Được gọi **trong `readObject`** để khôi phục field mặc định của slot hiện tại | Không phải hàm callback độc lập |
| `private Object readResolve()` | Giai đoạn resolve object sau deserialize theo cơ chế hỗ trợ | Có thể thay object bằng object khác |
| Constructor của lớp Serializable | Tạo mới object bằng `new` | **Không** chạy khi deserialization bình thường |
| Constructor no-arg của superclass đầu tiên **không Serializable** | Khi deserialize instance thuộc lớp Serializable | Khởi tạo phần state không serializable |
| `Externalizable.readExternal(ObjectInput)` | Với lớp Externalizable | Đọc dữ liệu theo hợp đồng do lớp quản lý |

`readObjectNoData` và `readObject` là hai **cơ hội khác nhau** cho cùng một serializable class. Nếu class local xuất hiện trong stream hierarchy nhưng field mới chưa tồn tại, giải pháp có thể là dùng `readObject`/`readFields` để xử lý version của chính class; hook `readObjectNoData` **không phải** callback tổng quát cho mọi thay đổi schema.

## 5. Chữ ký và visibility phải đúng

Khai báo được khuyến nghị:

```java
import java.io.ObjectStreamException;
import java.io.Serial;
import java.io.Serializable;

public class ExampleBase implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String source;

    @Serial
    private void readObjectNoData() throws ObjectStreamException {
        source = "legacy";
    }
}
```

Đây là class **biên dịch độc lập** nếu lưu tên `ExampleBase.java`. Nó chỉ minh họa cách định nghĩa hook; một lệnh `new ExampleBase()` **không** kích hoạt hook.

Những lỗi chữ ký nên tránh:

```java
// Các dòng sau là ví dụ SAI có chủ ý, KHÔNG viết tất cả
// vào cùng ExampleBase.java để mong compiler thực thi hook:
public void readObjectNoData() { }        // Không phải private
private int readObjectNoData() { return 0; } // Không trả void
private void readObjectNoData(ObjectInputStream in) { } // Sai tham số
static void readObjectNoData() { }       // Không phải instance hook
```

Method là **private instance method, không tham số, trả `void`**, và có thể khai báo `throws ObjectStreamException`. `@Override` không phù hợp vì đây không phải method override từ interface `Serializable`; `Serializable` chỉ là **marker interface**, không khai báo method `readObjectNoData` để implement.

`@Serial` là annotation hỗ trợ nhận diện đúng hình dạng hook; viết sai visibility/return type có thể biến method thành method thông thường không được cơ chế deserialization gọi như ý muốn. Không nên dựa vào việc unit test chỉ compile thành công để khẳng định callback thực sự được nhận — cần chạy một tình huống **evolution của stream**.

## 6. Ví dụ tổng thể: ghi object v1, đọc bằng hierarchy v2

Chúng ta sử dụng **hai bản class có cùng tên đầy đủ** `evolution.Receipt` nhưng biên dịch vào **hai thư mục output riêng biệt**, để người ghi (v1) và người đọc (v2) không vô tình dùng lẫn class version.

### Bản v1: `Receipt` trực tiếp extends `Object`

Cấu trúc thư mục:

```text
v1/
└── evolution/
    ├── Receipt.java
    └── WriteV1.java
```

**File `v1/evolution/Receipt.java`**

```java
package evolution;

import java.io.Serial;
import java.io.Serializable;

public final class Receipt implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String id;

    public Receipt(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
```

**File `v1/evolution/WriteV1.java`**

```java
package evolution;

import java.io.ObjectOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class WriteV1 {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: WriteV1 <output-file>");
        }

        Path output = Path.of(args[0]);
        Receipt receipt = new Receipt("R-42");

        try (ObjectOutputStream out = new ObjectOutputStream(
                Files.newOutputStream(output))) {
            out.writeObject(receipt);
        }

        System.out.println("v1 wrote id=" + receipt.id());
    }
}
```

Dữ liệu object trong `receipt.ser` được tạo bởi **v1** chứa descriptor và serialized field của `evolution.Receipt`; không thể có slot `AuditInfo` vì class này **chưa tồn tại trong hierarchy v1**.

### Bản v2: chèn Serializable superclass `AuditInfo`

Cấu trúc:

```text
v2/
└── evolution/
    ├── AuditInfo.java
    ├── Receipt.java
    └── ReadV2.java
```

**File `v2/evolution/AuditInfo.java`**

```java
package evolution;

import java.io.ObjectStreamException;
import java.io.Serial;
import java.io.Serializable;

public class AuditInfo implements Serializable {
    @Serial
    private static final long serialVersionUID = 5L;

    private String source = "field-initializer";

    protected AuditInfo() {
        source = "constructor";
        System.out.println("AuditInfo constructor");
    }

    @Serial
    private void readObjectNoData() throws ObjectStreamException {
        // Stream v1 không có slot AuditInfo.
        source = "legacy";
        System.out.println("AuditInfo.readObjectNoData");
    }

    public String source() {
        return source;
    }
}
```

**File `v2/evolution/Receipt.java`**

```java
package evolution;

import java.io.Serial;
import java.io.Serializable;

public final class Receipt extends AuditInfo implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String id;

    public Receipt(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}
```

Lưu ý: tên đầy đủ của `Receipt` và giá trị `serialVersionUID = 1L` **giữ nguyên** so với v1. Trong v2, `AuditInfo` cũng Serializable, nên các constructor và field initializer của `AuditInfo` không được chạy theo cơ chế tạo instance thông thường khi deserialize `Receipt`.

**File `v2/evolution/ReadV2.java`**

```java
package evolution;

import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadV2 {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ReadV2 <input-file>");
        }

        try (ObjectInputStream in = new ObjectInputStream(
                Files.newInputStream(Path.of(args[0])))) {

            Receipt result = (Receipt) in.readObject();

            System.out.println("v2 read id=" + result.id());
            System.out.println("v2 read source=" + result.source());
        }
    }
}
```

### Biên dịch vào hai classpath tách biệt

Từ thư mục chứa `v1` và `v2`, với shell có lệnh `mkdir -p` (Linux/macOS/Git Bash):

```bash
mkdir -p build/v1 build/v2

javac -d build/v1 v1/evolution/Receipt.java v1/evolution/WriteV1.java
java -cp build/v1 evolution.WriteV1 receipt.ser

javac -d build/v2 v2/evolution/AuditInfo.java v2/evolution/Receipt.java v2/evolution/ReadV2.java
java -cp build/v2 evolution.ReadV2 receipt.ser
```

Với **Windows PowerShell**, tạo thư mục bằng `New-Item -ItemType Directory -Force build/v1,build/v2` (hoặc `mkdir` phù hợp), sau đó chạy `javac`/`java` tương tự; dấu `/` trong đường dẫn classpath ở đây được Java hỗ trợ trên Windows. Các file nguồn phải được lưu ở đúng thư mục `evolution` vì khai báo `package evolution;`.

**Stdout khi cả hai lệnh `java` thành công, theo đúng thứ tự chạy:**

```text
v1 wrote id=R-42
AuditInfo.readObjectNoData
v2 read id=R-42
v2 read source=legacy
```

**Không có dòng `AuditInfo constructor`.** Vì `AuditInfo` là serializable superclass của `Receipt` local, khi khôi phục object Java không gọi constructor hay field initializer của lớp Serializable đó. Thay vào đó, do stream v1 **không liệt kê `AuditInfo`**, Java gọi `readObjectNoData()` và chúng ta đặt `source = "legacy"`.

Các bước cơ chế:

1. Chạy **v1**: JVM tải `evolution.Receipt` của v1 và ghi object chứa `id="R-42"`.
2. Chạy **v2**: JVM tải `evolution.Receipt` của v2, hiện extends `AuditInfo`.
3. Stream cũ vẫn có descriptor của `Receipt` tương thích về tên và `serialVersionUID`; field `id` được khôi phục bằng default serialization.
4. JVM phát hiện hierarchy local v2 có lớp `AuditInfo` nhưng stream không có slot class này.
5. `AuditInfo.readObjectNoData()` được gọi để khởi tạo state riêng của superclass mới. Nó đặt `source` thành `legacy`.
6. Đối tượng `Receipt` hoàn chỉnh có `id=R-42` từ dữ liệu cũ và `source=legacy` từ quy tắc migration của superclass mới.

**Không chạy `WriteV1` bằng classpath v2**: như vậy file mới sẽ có slot `AuditInfo`, làm mất ý nghĩa thử nghiệm. **Không chạy `ReadV2` bằng classpath v1**: bên đọc sẽ không có superclass mới. Phải có **hai process Java riêng với hai phiên bản cùng tên `Receipt`** để quan sát đúng cơ chế schema evolution.

## 7. Nếu bỏ `readObjectNoData()` thì điều gì xảy ra?

Trong bản v2, tạm thời **xóa duy nhất method `readObjectNoData` khỏi `AuditInfo`**, biên dịch lại `build/v2` và chạy `ReadV2` trên **cùng file `receipt.ser` tạo bởi v1**. Khi đó:

- `AuditInfo` vẫn là superclass Serializable mới vắng mặt trong stream.
- Vì không có hook để khởi tạo, những field của `AuditInfo` mang giá trị mặc định của JVM.
- `source` là field tham chiếu `String` nên có giá trị **`null`**, không phải `"field-initializer"` hoặc `"constructor"`.
- `Receipt.id` vẫn có thể được khôi phục từ slot của `Receipt` tương ứng, miễn các điều kiện tương thích khác giữ nguyên.

Dự kiến dòng có liên quan là:

```text
v2 read id=R-42
v2 read source=null
```

Giải thích quan trọng: **field initializer của Serializable superclass mới không chạy khi đọc object cũ**. Nếu lớp giả định `source` luôn non-null (ví dụ gọi `source.trim()`), object sau deserialize có thể vi phạm invariant và phát sinh lỗi ở nơi khác, rất khó truy vết.

Đó là lý do `readObjectNoData()` có giá trị ở tầng **khôi phục trạng thái hợp lệ** chứ không chỉ “để log một callback”.

## 8. Thứ tự khôi phục qua hierarchy

Java Object Serialization xử lý các lớp Serializable theo hướng **superclass đến subclass** trong quá trình khôi phục class data.

Với hierarchy mới:

```text
Object
   |
 AuditInfo (Serializable, KHÔNG có class data trong stream v1)
   |
 Receipt   (Serializable, CÓ class data trong stream v1)
```

Luồng ý tưởng:

```text
readObject() trên ObjectInputStream
         |
         v
cấp phát instance Receipt theo Serialization protocol
         |
         v
khởi tạo phần superclass không Serializable phù hợp (nếu có)
         |
         v
AuditInfo: không có slot stream -> readObjectNoData()
         |
         v
Receipt: có slot stream -> đọc/khôi phục field Receipt.id
         |
         v
trả về Receipt đã khôi phục
```

Khi `AuditInfo.readObjectNoData()` chạy, **Receipt-specific state có thể chưa khôi phục xong**. Bởi vậy:

- Không gọi những method **overridable** từ `readObjectNoData` nếu chúng có thể dispatch tới subclass và đọc state chưa sẵn sàng.
- Tập trung sửa state thuộc chính superclass.
- Nếu invariant phụ thuộc đồng thời vào nhiều tầng (ví dụ `Receipt.id` và `AuditInfo.source`), nên có chiến lược **validation sau khi cả object graph được khôi phục** bằng API có hỗ trợ, chẳng hạn `ObjectInputValidation` được đăng ký từ một hook `readObject` thích hợp.
- Không đưa một tham chiếu `this` chưa được khôi phục hoàn chỉnh ra cache toàn cục, background thread hay callback công khai.

Điều này giống rủi ro gọi overridable method trong constructor: object đang trải qua quá trình khởi tạo chưa hoàn toàn.

## 9. `serialVersionUID` và thay đổi hierarchy

Trong ví dụ, v1 và v2 cùng khai báo:

```java
@Serial
private static final long serialVersionUID = 1L;
```

cho **cùng class `evolution.Receipt`**. Điều này quan trọng vì `ObjectInputStream` so sánh thông tin version để quyết định có thể sử dụng mô tả class local hay không.

| Thay đổi | Hệ quả cần xem xét |
| --- | --- |
| Giữ tên class và `serialVersionUID` tương thích | Cho phép xét những quy tắc versioning còn lại |
| Thêm một Serializable superclass local mới | Có thể kích hoạt `readObjectNoData` của superclass đó nếu stream cũ không có slot |
| Đổi `serialVersionUID` của `Receipt` | Có thể ném `InvalidClassException` khi đọc stream cũ |
| Thay đổi tên package/class `Receipt` | Bên đọc có thể không resolve đúng class; `ClassNotFoundException` hoặc lỗi khác |
| Thêm field vào chính `Receipt` | Field mới thường mặc định nếu stream không có nó; không tự gọi `readObjectNoData` cho Receipt |
| Thay đổi field type / Serializable contract / externalization | Có thể không tương thích; không thể “sửa mọi thứ” bằng hook |
| Thêm superclass **không Serializable** | Liên quan constructor và state nonserializable; không đồng nhất với trường hợp hook Serializable |
| Sửa nguồn stream hoặc trộn nhiều version class vào classpath | Có thể gây lỗi cấu trúc, versioning hoặc behavior không mong đợi |

Đặt explicit `serialVersionUID` giúp kiểm soát versioning có chủ đích; **nó không phải bảo đảm mọi thay đổi đều tương thích**. Không nên chỉ tăng `serialVersionUID` như một “schema migration” rồi kỳ vọng code có thể deserialize dữ liệu cũ. Đổi UID thường là cách tuyên bố **không tương thích** theo default protocol.

Khi `serialVersionUID` không khai báo, JVM có thể tính UID mặc định dựa vào thông tin class; nhiều thay đổi ở class definition có thể khiến UID đổi và chặn đọc dữ liệu cũ. Đối với lớp phải lưu trữ/trao đổi serialized data nhiều phiên bản, explicit UID và kiểm thử versioning là bước quan trọng.

## 10. Phân biệt với việc thêm field mới mà không thêm superclass

Giả sử v1:

```java
class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
}
```

V2 vẫn cùng class và hierarchy nhưng thêm:

```java
class Customer implements Serializable {
    private static final long serialVersionUID = 1L;
    private String name;
    private String region = "VN"; // MỚI
}
```

Hai đoạn này là **minh họa hai phiên bản khác nhau**, không được đưa vào cùng một source file. Khi deserialize object v1 bằng v2, slot `Customer` vẫn được stream mô tả. Nếu field `region` không có trong stream, nó thường nhận **`null`** chứ không chạy initializer `"VN"`. Tuy nhiên, **`Customer.readObjectNoData()` không được gọi chỉ vì region thiếu**, bởi không phải toàn bộ class data của `Customer` bị thiếu.

Các phương án đúng khi cần migration field:

- Dùng `private void readObject(ObjectInputStream in)` và `in.defaultReadObject()`, sau đó áp default/validate cho field mới của class đó.
- Dùng `ObjectInputStream.GetField` / `readFields()` nếu cần biết cụ thể một field có mặt trong dữ liệu hay không và tránh nhầm giá trị mặc định hợp lệ với dữ liệu bị thiếu.
- Xây một phiên bản schema tường minh trong format do ứng dụng kiểm soát, có migration được kiểm thử.

Ví dụ riêng về custom read (snippet có class Serializable bao quanh):

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (region == null) {
        region = "VN";
    }
}
```

Đoạn này không cần làm `readObjectNoData()` và không phục hồi slot của một superclass mới. Nó chỉ là ví dụ gán default đơn giản; nếu `null` là một giá trị có nghĩa trong schema mới, muốn phân biệt dữ liệu cũ và `null` hợp lệ phải dùng chiến lược version/`GetField.defaulted` tương ứng.

## 11. Khởi tạo invariant hay từ chối dữ liệu không hợp lệ?

`readObjectNoData()` có hai hướng xử lý chính.

### 11.1. Áp dụng mặc định an toàn

Khi class mới chỉ thêm một metadata không ảnh hưởng tính đúng đắn, có thể đặt default hợp lý:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    source = "legacy";
    enabled = false;
}
```

Snippet giả định hai field `source` và `enabled` thuộc **cùng class Serializable**. Không dùng giá trị default mà vô tình **mở quyền** cho object cũ: ví dụ cấp `admin=true` chỉ vì stream thiếu thông tin là lỗ hổng nghiêm trọng. Default phải theo nguyên tắc an toàn, minh bạch với dữ liệu đã có.

### 11.2. Từ chối object không thể khôi phục an toàn

Nếu superclass mới đại diện cho một invariant bắt buộc, không thể suy ra trạng thái an toàn của object cũ, có thể ném `InvalidObjectException`:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException(
            "Missing required superclass state");
}
```

Snippet cần import `java.io.InvalidObjectException` và nằm trong class Serializable. Vì `InvalidObjectException` extends `ObjectStreamException`, nó phù hợp với chữ ký. Khi exception được ném, `ObjectInputStream.readObject()` thất bại; chương trình gọi phải xử lý thay vì xem object là hợp lệ.

**Quan trọng:** một stream đã bị sửa đổi có thể cố tình làm thiếu descriptor hoặc data. `readObjectNoData()` **không phải** hàng rào bảo mật toàn diện chống deserialization attack; nó chỉ cung cấp một điểm khôi phục/kiểm tra trong hoàn cảnh cụ thể. Nên xem dữ liệu serialized không tin cậy là đầu vào nguy hiểm.

## 12. Bảo mật: deserialize không tin cậy là rủi ro

`ObjectInputStream.readObject()` có thể dẫn tới tạo nhiều object và thực thi các hooks/phương thức khôi phục state trong object graph. Stream độc hại có thể khai thác code đang có trong classpath, gây tiêu tốn tài nguyên hoặc vượt qua giả định về invariant.

Biện pháp cần cân nhắc:

1. **Không deserialize byte không tin cậy nếu có thể tránh.** Với dữ liệu trao đổi giữa các hệ thống, cân nhắc JSON, Protocol Buffers, CBOR hoặc format có schema được kiểm tra chặt và không tái tạo arbitrary object graph.
2. Nếu buộc sử dụng Java Serialization, cấu hình **`ObjectInputFilter`** theo allowlist phù hợp và giới hạn depth, reference count, array size, tổng byte. Filter có giới hạn riêng, không thay thế validate.
3. Kiểm tra class identity, phiên bản schema, nguồn tạo dữ liệu và các giá trị bất biến sau khi đọc.
4. Không để hook gọi code overridable trên object chưa khôi phục xong hoặc công bố `this` ra bên ngoài.
5. Xử lý `InvalidClassException`, `ClassNotFoundException`, `InvalidObjectException` và I/O errors ở biên nhập dữ liệu; không tiếp tục dùng stream lỗi như thể không có gì.
6. Dùng dữ liệu mẫu đã tạo bởi code đáng tin để kiểm thử evolution; không nhận những file `.ser` không rõ nguồn chỉ để “kiểm tra xem có đọc được không”.

Tài liệu Java SE 17 cảnh báo deserialize dữ liệu không đáng tin là thao tác nguy hiểm; `readObjectNoData()` không làm thay đổi cảnh báo ấy.

## 13. Khác biệt với `Externalizable`, enum và record

### `Externalizable`

`Externalizable` extends `Serializable` nhưng quản lý dữ liệu theo `writeExternal(ObjectOutput)` và `readExternal(ObjectInput)`, thông thường cần constructor public không tham số để khôi phục. Không sử dụng bảng quy tắc “thêm superclass Serializable thì hook `readObjectNoData` sẽ xử lý” như một cơ chế migration chuẩn dành cho `Externalizable`. Tùy bài toán, lớp phải tự version dữ liệu trong custom format của mình.

### Enum

Enum có hình thức serialization chuyên biệt dựa trên tên hằng enum; các hook `readObject`, `readObjectNoData`, `readResolve` do kiểu enum định nghĩa bị bỏ qua trong quá trình deserialize enum. Đừng thử hook này vào enum để sửa dữ liệu khi đổi hierarchy: enum vốn không có hierarchy tùy ý như class thông thường.

### Record (Java 17)

Serializable record được deserialize theo quy tắc riêng, bao gồm việc gọi canonical constructor để khôi phục record components. Những hook serialization nhất định không có ý nghĩa như với class Serializable thông thường. Với record, hãy dùng quy tắc record serialization tương ứng và versioning của component/schema, không dùng nguyên mẫu superclass + `readObjectNoData` ở ví dụ `Receipt`.

## 14. Các lỗi phổ biến và cách sửa

1. **Gọi `readObjectNoData()` trong constructor để “kích hoạt”.** Hook chỉ được Java Serialization gọi trong hoàn cảnh thiếu class data; gọi tay làm sai mục đích.
2. **Viết method `public`/`static` hoặc có tham số.** Không khớp chữ ký private instance method mà Serialization mong đợi.
3. **Nhầm việc thiếu một field với thiếu slot class.** Thêm field vào class không tự kích hoạt hook; dùng `readObject`/`readFields` để xử lý phiên bản field.
4. **Giữ default field initializer rồi nghĩ nó sẽ chạy khi deserialize.** Với Serializable superclass, field mới có thể vẫn là `null`/`0`/`false` nếu không được restore hoặc hook sửa.
5. **Dùng constructor của Serializable superclass để sửa dữ liệu cũ.** Constructor lớp Serializable không chạy theo quy trình bình thường của deserialize.
6. **Thay đổi `serialVersionUID` rồi kỳ vọng `readObjectNoData` cứu tương thích.** UID mismatch có thể dẫn đến `InvalidClassException` trước khi có object hợp lệ.
7. **Dùng cùng thư mục `.class` cho v1 và v2.** Một phiên bản bị ghi đè hoặc classloader tải nhầm; dùng classpath/process độc lập như ví dụ.
8. **Chạy writer phiên bản v2 rồi dùng v2 đọc để kiểm thử dữ liệu v1.** Stream đã có slot superclass mới, không tạo ra hoàn cảnh kích hoạt hook.
9. **Để hook phụ thuộc field của subclass đang khôi phục dở.** Có thể quan sát trạng thái chưa sẵn sàng; chỉ thiết lập state của class hiện tại hoặc dùng validation sau graph restoration.
10. **Trả object không có invariant an toàn sau khi thiếu superclass state.** Nên dùng default fail-safe hoặc `InvalidObjectException`.
11. **Xem thành công deserialize là chứng minh dữ liệu đáng tin.** Không đúng; kiểm tra nguồn, filter, version và invariant.
12. **Gọi hook để “đọc thêm byte” từ `ObjectInputStream`.** Hook `readObjectNoData` không có stream tham số và không có slot data tương ứng để đọc; không truy cập nhầm payload của lớp khác.
13. **Chèn superclass không Serializable và kỳ vọng `readObjectNoData` chạy.** Cần phân biệt constructor khởi tạo nonserializable superclass.
14. **Hiểu `serialVersionUID` là số phiên bản schema tự động upgrade.** Nó là cơ chế kiểm tra tương thích, không tạo migration.
15. **Dùng `readResolve` để thay chức năng của `readObjectNoData`.** `readResolve` có tác dụng thay object, không phải sự kiện “thiếu superclass data” theo class slot.
16. **Không có kiểm thử ngược xuôi giữa các bản release.** Mỗi hướng đọc/ghi có thể khác nhau: forward compatibility và backward compatibility không tự bảo đảm đối xứng.

## 15. Bài tập thực hành có đáp án định hướng

### Bài A — khôi phục field mới ở superclass

Trong ví dụ v2, thêm `private boolean verified;` vào `AuditInfo` và đặt `verified=false` ở `readObjectNoData()`. Vì sao default false cũng có thể xuất hiện nếu bỏ hook? Bạn sẽ phân biệt “cố ý xác nhận chưa verify” với “thiếu dữ liệu” ở tầng nghiệp vụ như thế nào?

**Gợi ý:** Giá trị mặc định một mình không chứa thông tin nguồn gốc. Cần quy tắc migration/version hoặc trạng thái phân biệt như enum `UNKNOWN/PENDING/VERIFIED` với default an toàn.

### Bài B — bỏ hook rồi đọc dữ liệu cũ

Xóa `readObjectNoData` trong `AuditInfo` v2, giữ `source = "field-initializer"` và constructor gán `"constructor"`. Compile lại v2, đọc file v1. Dự đoán giá trị source.

**Đáp án:** `null`, vì khi khôi phục Serializable superclass bị thiếu class data, field initializer/constructor của class ấy không chạy và không có hook khởi tạo.

### Bài C — đổi UID của Receipt

Trong `v2/evolution/Receipt.java`, đổi UID thành `2L`; đọc `receipt.ser` tạo bởi v1 UID `1L`.

**Đáp án định hướng:** Deserialization thất bại vì thông tin version không khớp, thường là `InvalidClassException`. Không mong `readObjectNoData` giúp bảo toàn tương thích.

### Bài D — thêm field trực tiếp vào Receipt

Giữ hierarchy cũ (không thêm `AuditInfo`), chỉ thêm `String status = "NEW"` vào `Receipt` v2, giữ UID 1L. Đọc object v1. Hook `Receipt.readObjectNoData()` có chạy không?

**Đáp án:** Không chỉ vì `status` là field mới. Slot class `Receipt` vẫn tồn tại trong stream; field mới thường nhận `null`, cần xử lý bằng hook `readObject` hoặc version migration riêng.

### Bài E — từ chối stream thiếu state bắt buộc

Sửa `AuditInfo.readObjectNoData()` để ném `InvalidObjectException`. Chạy reader trên dữ liệu v1 và xác nhận không có dòng “v2 read id=...”.

**Đáp án định hướng:** `ObjectInputStream.readObject()` sẽ thất bại và exception lan ra caller, nên mã sau lời gọi không tiếp tục theo luồng thành công.

### Bài F — thử thứ tự class state

Trong `Receipt` v2, thêm custom `private void readObject(ObjectInputStream in)`, gọi `in.defaultReadObject()` rồi in một dòng. Chạy reader dữ liệu v1 và so sánh thứ tự log với `AuditInfo.readObjectNoData`.

**Đáp án định hướng:** Class data được xử lý superclass trước subclass; hook của `AuditInfo` chạy trước hook của `Receipt`. Giữ đúng checked exceptions và `@Serial` trong khai báo.

## 16. Checklist khi phát triển schema evolution

Trước khi phát hành phiên bản lớp Serializable mới:

- [ ] Liệt kê hierarchy cũ và mới, xác định **class slot** nào được thêm, xóa hoặc đổi vị trí.
- [ ] Giữ nguyên tên class và `serialVersionUID` khi muốn duy trì đường tương thích có kiểm soát.
- [ ] Kiểm tra thành phần nào thực sự **Serializable**, phần nào không Serializable và constructor nào sẽ được gọi.
- [ ] Với Serializable superclass mới vắng mặt trong stream cũ, có invariant nào cần `readObjectNoData()` không?
- [ ] Nếu chỉ thêm field ở class cũ, đừng kỳ vọng `readObjectNoData`; kiểm tra `readObject`/`readFields` và defaulting.
- [ ] Thiết kế giá trị migration an toàn; với trạng thái bắt buộc không thể suy ra, từ chối bằng `InvalidObjectException`.
- [ ] Không gọi method overridable từ lúc object chưa khôi phục xong; có kế hoạch kiểm tra invariant sau khi đọc xong graph.
- [ ] Kiểm thử **serialized bytes sinh bởi bản cũ thực sự**, không chỉ round-trip trong bản mới.
- [ ] Chạy test mỗi hướng v1→v2 và v2→v1 nếu sản phẩm cần cả hai; ghi nhận rõ hướng được hỗ trợ.
- [ ] Nếu stream do bên ngoài tạo, sử dụng `ObjectInputFilter` và chính sách từ chối dữ liệu không tin cậy.
- [ ] Không thay serialized format một cách tùy tiện mà không có tài liệu và test hồi quy.

## 17. Tài liệu Java SE 17 chính thống

- [`ObjectInputStream` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): mô tả `readObjectNoData`, thứ tự khôi phục, constructor của superclass không Serializable.
- [`Serializable` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): các serialization hooks và versioning.
- [Java Object Serialization Specification, mục 3.5 — `readObjectNoData`](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/input.html#the-readobjectnodata-method): điều kiện kích hoạt và field default nếu không có hook.
- [Java Object Serialization Specification — Versioning](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html): thay đổi field/hierarchy và các quy tắc tương thích.
- [`ObjectInputFilter` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): lọc lớp/tham chiếu/độ sâu khi deserialize.
- [`InvalidObjectException` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidObjectException.html): từ chối object không hợp lệ trong quá trình đọc.

## 18. Ghi nhớ

`readObjectNoData()` là callback **đặc biệt của từng lớp Serializable** khi local hierarchy có class cần khôi phục nhưng **stream không chứa class data của chính class đó**. Kịch bản điển hình: v2 chèn thêm Serializable superclass phía trên một subclass mà stream v1 đã ghi.

Phương thức có dạng **`private void readObjectNoData() throws ObjectStreamException`**, không có `ObjectInputStream` tham số. Nó khôi phục invariant của **chính lớp ấy** hoặc từ chối dữ liệu bằng exception. Nó **không tự kích hoạt chỉ vì thêm field** vào class vẫn có slot trong stream, và constructor/field initializer của Serializable superclass cũng không chạy theo lối `new` khi deserialize.

Để dùng an toàn: giữ compatibility của tên class và `serialVersionUID` có chủ đích, tách hai bản classpath để kiểm thử evolution, khôi phục superclass state đúng thời điểm, validate toàn bộ object graph và không deserialize dữ liệu không tin cậy thiếu kiểm soát.
