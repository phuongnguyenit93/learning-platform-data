# serialPersistentFields và điều khiển dạng lưu trữ trong Java Serialization

Khi triển khai `java.io.Serializable`, nhiều lớp ban đầu dựa vào cơ chế mặc định: Java ghi các trường instance không `static`, không `transient`. Nhưng nếu ứng dụng lưu file `.ser` lâu dài hoặc trao đổi đối tượng giữa hai phiên bản chương trình, **tên và kiểu trường được ghi trong stream** trở thành một hợp đồng tương thích. Việc đổi tên một field trong mã nguồn có thể làm thông tin cũ không tự ánh xạ được vào field mới.

`serialPersistentFields` cho phép lớp **khai báo rõ dạng trường được lưu (serialized form)**, tách nó khỏi cấu trúc trường Java hiện tại. Kết hợp với `writeObject`/`readObject` và API `PutField`/`GetField`, ta có thể tiếp tục ghi/đọc cùng một dạng dữ liệu kể cả khi đổi cách lưu trạng thái trong bộ nhớ.

**Phạm vi:** Đây là cơ chế dành cho Java Object Serialization của các lớp Serializable thông thường. Không áp dụng trực tiếp cho JSON, JPA, protobuf, Java Records hoặc `Externalizable`. Định dạng `.ser` là stream nhị phân có class descriptor, tham chiếu đối tượng và dữ liệu của từng lớp serializable trong cây kế thừa; nó không chỉ là một bảng các field.

## 1. Tách trạng thái trong bộ nhớ khỏi serialized form

Giả sử phiên bản cũ có lớp:

```java
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    String fullName;
    int points;
}
```

Với serialization mặc định, hai trường được ghi là `fullName:java.lang.String` và `points:int`. Nếu phiên bản mới đổi chúng thành `displayName` và `rewardBalance`, việc giữ UID `7L` **không tự đổi tên dữ liệu trên stream**. Khi đọc file cũ, tên mới không khớp nên mặc định nhận `null`/`0`, còn dữ liệu trường tên cũ bị bỏ qua. Khi phiên bản mới ghi file, phiên bản cũ cũng không tự tìm được tên trường mới.

Ta muốn lớp mới sử dụng tên trường tốt hơn trong code, nhưng tiếp tục công bố các field lịch sử `fullName`, `points` trên stream:

```text
Phiên bản 1                         Serialized form ổn định                 Phiên bản 2
fullName: String  ────────────────> fullName: String <──────────────────> displayName: String
points: int       ────────────────> points: int      <──────────────────> rewardBalance: int
```

Chiều mũi tên từ v2 vào wire format do **code ánh xạ tường minh** xử lý. Đây là lý do chính để dùng `serialPersistentFields`.

## 2. Khai báo serialPersistentFields đúng hợp đồng

Trong lớp triển khai `Serializable`, định nghĩa trường đặc biệt như sau:

```java
import java.io.ObjectStreamField;
import java.io.Serializable;

public class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("fullName", String.class),
        new ObjectStreamField("points", int.class)
    };

    private String displayName;
    private int rewardBalance;
}
```

Đây là **đoạn khai báo có thể biên dịch**, nhưng chưa phải ví dụ ánh xạ dữ liệu hoàn chỉnh. Vì tên các field trong mảng không giống field vật lý, phần 4 sẽ triển khai thêm `writeObject/readObject`.

Các quy tắc:

1. Tên bắt buộc là chính xác `serialPersistentFields`, kiểu `ObjectStreamField[]`, modifiers `private static final`. Nếu khai báo sai tên, thiếu modifiers, giá trị `null` hoặc kiểu không đúng, cơ chế sẽ coi như không có khai báo và quay về tính các field mặc định; vì vậy lỗi có thể âm thầm làm thay đổi schema.
2. Mỗi `new ObjectStreamField("tên", Kiểu.class)` mô tả **một field trên stream**, gồm tên và kiểu. Đối với primitive dùng `int.class`, `long.class`..., không dùng `Integer.class` để thay thế `int.class`. Java không tự ép kiểu khi giải tuần tự hóa.
3. Có thể mô tả field **không tồn tại thật** trong lớp Java mới (field ảo/virtual persistent field). Mục đích là giữ tên wire schema cũ trong khi trường bộ nhớ đã thay đổi.
4. Field vật lý không nằm trong mảng thì **không thuộc dạng lưu trữ của lớp đó** theo cơ chế này. Ngược lại, field được liệt kê có thể được ghi ngay cả khi field vật lý không tồn tại. Một field `transient` không tự bảo đảm loại trừ nếu chính sách persistent fields chủ động đưa tên đó vào schema.
5. Mảng rỗng `new ObjectStreamField[0]` có nghĩa không có field persistent cho **lớp này**, nhưng không loại bỏ thông tin class descriptor hoặc dữ liệu của các lớp serializable khác trong cây kế thừa.
6. Mảng `ObjectStreamField` không chứa giá trị dữ liệu đối tượng; nó chỉ khai báo tên/kiểu (và tùy chọn `unshared`). Những giá trị cụ thể được lấy từ object khi ghi, và gán lại khi đọc.

`serialVersionUID` và `serialPersistentFields` giải quyết hai việc khác nhau. UID phục vụ kiểm tra phiên bản lớp khi đọc; persistent fields định nghĩa tập trường serializable. **Cùng UID không bảo đảm tương thích** nếu đã đổi tên, kiểu, thứ tự thông tin tùy biến hoặc hợp đồng dữ liệu theo cách không xử lý được.

## 3. API điều khiển quá trình ghi và đọc

### Ghi: putFields → put → writeFields

Trong phương thức private `writeObject(ObjectOutputStream out)`, gọi:

```java
ObjectOutputStream.PutField fields = out.putFields();
fields.put("fullName", displayName);
fields.put("points", rewardBalance);
out.writeFields();
```

Đây là **đoạn mã đặt bên trong `writeObject`**, không phải chương trình độc lập.

- `out.putFields()` tạo bộ chứa các giá trị của field đã khai báo trong serialized form hiện tại. Chỉ được gọi từ `writeObject` hợp lệ.
- `fields.put("fullName", displayName)` đưa giá trị nội bộ `displayName` vào tên wire field cũ `fullName`. Các overload của `put` tương ứng primitive hoặc reference.
- `out.writeFields()` ghi các giá trị đã đặt theo thứ tự chuẩn do protocol quyết định, không phải thứ tự ta gọi `put`. Field bỏ qua trong `put` được ghi giá trị mặc định của kiểu.
- Không gọi lẫn `defaultWriteObject()` và `putFields()/writeFields()` cho cùng dữ liệu bắt buộc của một lần `writeObject`.

**Không gọi `out.writeObject(displayName)` thay cho `putFields`** rồi cho rằng stream sẽ có field tên `fullName`. Ghi object trực tiếp tạo *optional data* riêng, không tương đương phần field bắt buộc trong class descriptor; nếu thay đổi hợp đồng đọc/ghi tùy biến bừa bãi, các phiên bản có thể không tương thích.

### Đọc: readFields → get → kiểm tra bất biến

Trong phương thức private `readObject(ObjectInputStream in)`, gọi:

```java
ObjectInputStream.GetField fields = in.readFields();
displayName = (String) fields.get("fullName", null);
rewardBalance = fields.get("points", 0);
```

Đây cũng là **đoạn mã bên trong `readObject`**.

`in.readFields()` lấy dữ liệu persistent fields từ stream, cho phép truy vấn bằng tên với overload `get(String, <giá trị mặc định>)`. `fields.defaulted("fullName")` kiểm tra tên field có vắng trong stream hiện tại hay không. Nó hữu ích khi cần phân biệt “file cũ chưa có field” với “file có field nhưng giá trị là `null`”.

Cần validate dữ liệu sau đọc: constructor/initializer của chính lớp `Serializable` không chạy trong giải tuần tự hóa thông thường. Vì thế object có thể ở trạng thái mà constructor thường không chấp nhận. Có thể ném `InvalidObjectException` nếu bất biến không đạt.

### Khi nào dùng defaultWriteObject/defaultReadObject?

Nếu tên và kiểu các field trong `serialPersistentFields` tương ứng với field instance thực tế và không cần đổi giá trị, cơ chế mặc định vẫn có thể ánh xạ chúng. Trong một phương thức `writeObject` tùy biến, `defaultWriteObject()` ghi phần field bắt buộc theo serialized form; `defaultReadObject()` đọc và gán phần field tương ứng. Tuy nhiên **không thể trông chờ defaultWriteObject/defaultReadObject tự biết rằng `displayName` là tên mới của `fullName`**. Muốn ánh xạ tên ảo hoặc chuyển đổi giá trị, dùng `PutField/GetField`.

## 4. Ví dụ đầy đủ chạy được: thay tên field nội bộ, giữ wire schema

Ta sẽ viết bằng v1, đọc bằng v2, sau đó viết bằng v2 và đọc lại bằng v1. Để tránh hai lớp `Customer` cùng tên xung đột, hãy đặt source trong hai thư mục riêng và chạy từng phiên bản với classpath riêng. Ví dụ chạy với JDK 17+ (kể cả Java 21).

### Phiên bản 1 — lớp truyền thống dùng default serialization

Tạo `v1/Customer.java`:

```java
import java.io.Serializable;

public final class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    String fullName;
    int points;

    public Customer(String fullName, int points) {
        this.fullName = fullName;
        this.points = points;
    }
}
```

Tạo `v1/LegacyApp.java`:

```java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public class LegacyApp {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("write|read <file>");
        }

        if ("write".equals(args[0])) {
            Customer c = new Customer("Lan", 120);
            try (ObjectOutputStream out =
                    new ObjectOutputStream(new FileOutputStream(args[1]))) {
                out.writeObject(c);
            }
            System.out.println("v1 wrote: " + c.fullName + "/" + c.points);
        } else if ("read".equals(args[0])) {
            try (ObjectInputStream in =
                    new ObjectInputStream(new FileInputStream(args[1]))) {
                Customer c = (Customer) in.readObject();
                System.out.println("v1 read: " + c.fullName + "/" + c.points);
            }
        } else {
            throw new IllegalArgumentException("Unknown command");
        }
    }
}
```

### Phiên bản 2 — tên field nội bộ đã đổi nhưng tên persistent field vẫn như v1

Tạo `v2/Customer.java`:

```java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.ObjectStreamField;
import java.io.Serializable;

public final class Customer implements Serializable {
    private static final long serialVersionUID = 7L;

    // Cam kết giữ schema đã dùng từ v1:
    private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("fullName", String.class),
        new ObjectStreamField("points", int.class)
    };

    // Dữ liệu nội bộ đã đổi tên, không trùng tên wire fields:
    private String displayName;
    private int rewardBalance;

    public Customer(String displayName, int rewardBalance) {
        if (displayName == null || displayName.isBlank() || rewardBalance < 0) {
            throw new IllegalArgumentException("Invalid customer");
        }
        this.displayName = displayName;
        this.rewardBalance = rewardBalance;
    }

    public String displayName() {
        return displayName;
    }

    public int rewardBalance() {
        return rewardBalance;
    }

    private void writeObject(ObjectOutputStream out) throws IOException {
        ObjectOutputStream.PutField fields = out.putFields();
        fields.put("fullName", displayName);
        fields.put("points", rewardBalance);
        out.writeFields();
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        ObjectInputStream.GetField fields = in.readFields();
        displayName = (String) fields.get("fullName", null);
        rewardBalance = fields.get("points", 0);

        if (displayName == null || displayName.isBlank()
                || rewardBalance < 0) {
            throw new InvalidObjectException("Invalid customer state");
        }
    }
}
```

Tạo `v2/NewApp.java`:

```java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public class NewApp {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("write|read <file>");
        }

        if ("write".equals(args[0])) {
            Customer c = new Customer("Mai", 75);
            try (ObjectOutputStream out =
                    new ObjectOutputStream(new FileOutputStream(args[1]))) {
                out.writeObject(c);
            }
            System.out.println("v2 wrote: "
                    + c.displayName() + "/" + c.rewardBalance());
        } else if ("read".equals(args[0])) {
            try (ObjectInputStream in =
                    new ObjectInputStream(new FileInputStream(args[1]))) {
                Customer c = (Customer) in.readObject();
                System.out.println("v2 read: "
                        + c.displayName() + "/" + c.rewardBalance());
            }
        } else {
            throw new IllegalArgumentException("Unknown command");
        }
    }
}
```

Từ thư mục cha chứa `v1/` và `v2/`, chạy lần lượt:

```bash
javac -encoding UTF-8 -d v1-classes v1/Customer.java v1/LegacyApp.java
javac -encoding UTF-8 -d v2-classes v2/Customer.java v2/NewApp.java
java -cp v1-classes LegacyApp write legacy.ser
java -cp v2-classes NewApp read legacy.ser
java -cp v2-classes NewApp write current.ser
java -cp v1-classes LegacyApp read current.ser
```

Stdout của bốn lệnh `java`:

```text
v1 wrote: Lan/120
v2 read: Lan/120
v2 wrote: Mai/75
v1 read: Mai/75
```

Kết quả giải thích được cả hai chiều:

1. File `legacy.ser` do v1 tạo có tên class `Customer`, UID `7L`, persistent fields `fullName: String` và `points: int`. V2 dùng `readFields()` để đưa chúng vào `displayName` và `rewardBalance`.
2. V2 ghi `current.ser` thông qua `putFields/writeFields`; dù class v2 không hề có field instance tên `fullName` hay `points`, stream **vẫn có các trường tương thích với v1**. V1 đọc lại bằng default serialization.
3. Các lớp ở hai thư mục phải có **cùng tên lớp nhị phân** (`Customer` ở default package trong ví dụ) và UID tương thích. Thực tế nên dùng package ổn định và biên dịch mỗi phiên bản thành artifact khác nhau.
4. Hai file có thể khác nhau về bytes vì stream descriptor của v2 có cờ cho phương thức ghi tùy biến. Mục tiêu là **đọc được dữ liệu và khôi phục đúng trạng thái**, không yêu cầu `legacy.ser` và `current.ser` giống byte-for-byte.

Nếu chỉ đổi trường v2 thành `displayName/rewardBalance` mà bỏ mảng `serialPersistentFields` và bộ ánh xạ, Java sẽ mặc định ghi/đọc tên mới: bài thử trên không còn giữ được hai field cũ một cách trọn vẹn.

## 5. Kiểm tra schema thực sự mà JVM công bố

Có thể xem danh sách persistent fields bằng `ObjectStreamClass`. Trong ví dụ v2, bổ sung đoạn sau vào bất kỳ phương thức `main` nào cùng classpath v2 (đây là **đoạn mã minh họa**, cần `import java.io.ObjectStreamClass;` và `import java.io.ObjectStreamField;`):

```java
ObjectStreamField[] declared =
        ObjectStreamClass.lookup(Customer.class).getFields();

for (ObjectStreamField field : declared) {
    System.out.println(field.getName() + ":"
            + field.getType().getSimpleName());
}
```

Output tương ứng (các field primitive được sắp trước field object theo tên):

```text
points:int
fullName:String
```

Dù trường instance của lớp v2 là `displayName` và `rewardBalance`, descriptor vẫn công bố `points` và `fullName`. Đây là cách kiểm tra hữu ích sau khi refactor hoặc cập nhật thư viện. `ObjectStreamClass.lookup` có thể trả về `null` cho lớp không Serializable.

Một biến thể khác là liệt kê chính xác các field đang được serialize mà không cần giữ tên cũ. Tuy nhiên nếu dữ liệu đã phát hành dùng schema cũ, **đổi persistent schema cũng là thay đổi hợp đồng**. Cần lên kế hoạch đọc dữ liệu cũ và kiểm tra compatibility bằng fixture.

## 6. Phạm vi ảnh hưởng và các tình huống nâng cao

| Cách xử lý | Serialized fields | Khi nào phù hợp | Lưu ý |
| --- | --- | --- | --- |
| Chỉ `implements Serializable` | Các field instance không `static/transient` | Lớp đơn giản, không có schema lâu dài | Refactor tên field ảnh hưởng stream |
| `transient` | Bỏ một field khỏi tập mặc định | Dữ liệu tạm, cache có thể tạo lại | Dữ liệu mất lúc khôi phục; không đủ để kiểm soát toàn bộ schema |
| `serialPersistentFields` | Tập tên/kiểu được khai báo tường minh | Ổn định giao thức field và ẩn cấu trúc nội bộ | Field ảo cần chủ động ánh xạ giá trị |
| `writeObject/readObject` + `PutField/GetField` | Tập field tường minh và logic ánh xạ | Đổi tên field, chuẩn hóa dữ liệu, migrate dạng lưu trữ | Duy trì thứ tự và sự hiện diện của required data |
| `Externalizable` | Hoàn toàn tự định nghĩa qua `writeExternal/readExternal` | Kiểm soát protocol thấp hơn | Cơ chế và quy tắc versioning riêng; không dùng `serialPersistentFields` như Serializable |
| Serialization proxy (`writeReplace/readResolve`) | Một đối tượng proxy độc lập đại diện trạng thái | Các kiểu bất biến hoặc có bất biến chặt | Cần thiết kế tương thích với stream đã tồn tại |

### Field thiếu trong một phiên bản cũ

Nếu v3 thêm persistent field `String membershipLevel` và v3 đọc stream v1/v2 chưa có field này, `GetField` có thể kiểm tra:

```java
String level = fields.defaulted("membershipLevel")
        ? "STANDARD"
        : (String) fields.get("membershipLevel", null);
```

Đây là **đoạn đặt trong `readObject` v3**, chỉ hợp lệ khi `membershipLevel` đã được khai báo trong `serialPersistentFields` của v3. `defaulted` hỏi field có vắng trong stream hay không, **không** hỏi nó có `null`. Cần phân biệt để không ghi đè một giá trị `null` vốn có chủ ý.

Nếu v3 muốn viết file mà v1/v2 đọc được, vẫn phải bảo toàn những persistent fields mà code cũ cần. Field bổ sung thường được code cũ bỏ qua, nhưng tính đúng đắn nghiệp vụ vẫn cần kiểm thử. Nếu đổi kiểu field, ví dụ `points:int` thành `points:long`, giữ cùng tên hoặc UID **không khiến Java tự chuyển đổi**. Có thể giữ wire field `points:int` và tự xử lý `long` trong nội bộ, đồng thời kiểm soát range/overflow, hoặc thiết kế migration định dạng mới.

### Tuỳ chọn unshared của ObjectStreamField

`new ObjectStreamField("name", SomeClass.class, true)` yêu cầu xử lý field tham chiếu như unshared trong cơ chế của serialization. Nó ảnh hưởng chia sẻ reference/aliasing của trường đối tượng, không phải cách đặt tên field hay tăng UID. Chỉ dùng khi hiểu rõ đồ thị object và yêu cầu giữ hay cắt sharing; không bật tuỳ tiện trong bản refactor đơn giản.

### Đa kế thừa, inner class và lớp đặc biệt

Serialized form được xử lý theo **từng lớp Serializable** trong chuỗi kế thừa, không chỉ lớp lá. `serialPersistentFields` của lớp con không thay schema của superclass. Những thay đổi hierarchy và custom write/read data có thể ảnh hưởng mạnh đến tương thích.

Non-static inner class không phải lựa chọn tốt để xây schema serialized ổn định: chúng thường có tham chiếu ngầm tới enclosing instance, và không thể khai báo `private static final ObjectStreamField[]` theo cách cần thiết trong trường hợp phổ biến. Dùng top-level class hoặc static nested class cho mô hình cần custom serialized form. Đối với enum và record, quy tắc serialization khác với lớp thông thường; không áp dụng máy móc ví dụ này.

## 7. Lỗi phổ biến và dấu hiệu nhận biết

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra/khắc phục |
| --- | --- | --- |
| Sau refactor, field mới đọc được `null` hoặc `0` | Chỉ đổi tên field trong code, không giữ wire field hay không có mapping | Khai báo persistent schema cũ và chuyển giá trị bằng `GetField` |
| File ghi bằng v2 bị v1 đọc thành giá trị mặc định | V2 ghi tên/kiểu field mới, bỏ các field v1 cần | Giữ tên/kiểu persistent fields cũ, kiểm thử chiều v2 → v1 |
| `InvalidClassException` | UID không khớp hoặc dạng serializable class/field không tương thích | So sánh UID, classpath, field names/types, custom protocol |
| `IllegalArgumentException` khi gọi `put/get` | Tên field không có trong declared persistent fields hoặc overload không phù hợp | Đối chiếu `ObjectStreamClass.getFields()` và đúng kiểu Java |
| `NotActiveException` | Gọi `putFields/readFields/defaultWriteObject` ngoài ngữ cảnh serialization hợp lệ | Chỉ gọi trong các hook private đúng chữ ký |
| Chạy nhưng stream không có các trường mong muốn | `serialPersistentFields` bị khai báo sai modifiers/kiểu, hoặc không ghi giá trị field ảo | Kiểm tra khai báo và lớp descriptor; thử fixture thực tế |
| Cùng một dữ liệu, object sau đọc có trạng thái vô lý | Bỏ qua kiểm tra bất biến hoặc không chạy initializer của Serializable | Validate trong `readObject`, ném `InvalidObjectException` |
| `NotSerializableException` khi ghi | Giá trị tham chiếu trong persistent fields dẫn đến object không Serializable | Điều chỉnh mô hình, lưu representation an toàn, hoặc đánh dấu không lưu |
| Dữ liệu đọc được nhưng code cũ hiểu sai | Binary compatibility khác semantic compatibility | Áp dụng quy tắc tương thích nghiệp vụ và migration nếu cần |

Một bẫy đặc biệt là **trộn phần required fields với optional custom data**. Khi sử dụng `writeObject`, đảm bảo cơ chế ghi field bắt buộc (`defaultWriteObject` hoặc `writeFields`) luôn khớp với cơ chế đọc (`defaultReadObject` hoặc `readFields`) ở những phiên bản cần tương thích. Sau phần bắt buộc mới có thể ghi optional data bổ sung; cả writer và reader phải thống nhất thứ tự, version marker và cách xử lý thiếu thông tin. Đừng chuyển toàn bộ nội dung sang các lệnh `writeInt/writeObject` tùy hứng mà vẫn kỳ vọng phiên bản cũ đọc được field như trước.

## 8. Giới hạn, an toàn và phương án thiết kế

`serialPersistentFields` **không phải công cụ bảo mật**. Nó giúp giới hạn serialized state của một lớp, nhưng không xác thực stream, không mã hóa dữ liệu và không chống khai thác đối tượng khi giải tuần tự hóa. Đừng giải tuần tự hóa dữ liệu Java từ nguồn không tin cậy. Khi bắt buộc sử dụng, giới hạn loại class/độ sâu/số tham chiếu/kích thước bằng `ObjectInputFilter` và chính sách kiểm soát đầu vào; giữ bất biến sau đọc.

Việc bỏ một thông tin bí mật khỏi `serialPersistentFields` chỉ ảnh hưởng file ghi mới; các file cũ có thể vẫn chứa dữ liệu đó. Nếu cần loại bỏ bí mật đã lưu, phải có kế hoạch xử lý file/backup cũ.

Không nên dùng Java native serialization cho hợp đồng lưu trữ liên ngôn ngữ hoặc API công khai mới. Với schema cần tồn tại lâu và migration phức tạp, ưu tiên định dạng có phiên bản/schema rõ ràng (ví dụ JSON có version kèm validation, protobuf hoặc Avro tùy yêu cầu). Nếu hệ thống đã phụ thuộc Java serialization, `serialPersistentFields` hữu ích để giảm phụ thuộc giữa wire schema và field vật lý, đi kèm fixture compatibility mỗi lần nâng cấp.

## 9. Checklist thay đổi một lớp có dữ liệu serialized đang tồn tại

1. Ghi lại tên lớp/package, `serialVersionUID` và descriptor của các phiên bản đang hỗ trợ; giữ file fixture thật.
2. Liệt kê chính xác tên/kiểu persistent fields cũ. Quyết định field nào buộc phải giữ và trường nào có migration.
3. Khai báo `serialPersistentFields` đúng modifiers và kiểu; nếu field mới không trùng field vật lý, triển khai `writeObject`/`readObject` bằng `PutField/GetField`.
4. Validate trạng thái sau `readFields()`, kể cả trường hợp field vắng, giá trị `null`, số âm, đối tượng tham chiếu hoặc dữ liệu không hợp lệ.
5. Chạy fixture **v1 → v2** và nếu có yêu cầu rollback/đa phiên bản, chạy thêm **v2 → v1**. Kiểm tra giá trị, bất biến và hành vi nghiệp vụ chứ không chỉ “không ném exception”.
6. Duy trì test khi thêm, đổi kiểu, xóa, chuyển `transient`, thay hierarchy hoặc đổi optional custom data. Nếu không thể giữ tương thích, thay giao thức một cách có chủ đích và có migration.

## 10. Câu hỏi tự kiểm tra

1. V2 đổi `fullName` thành `displayName` nhưng vẫn dùng mặc định và giữ UID. Java có tự chuyển giá trị khi đọc file v1 không? **Không.** Cần mapping explicit hoặc một bước migrate.
2. Nếu `serialPersistentFields` có `new ObjectStreamField("oldName", String.class)` nhưng class chỉ có `newName`, dùng `defaultWriteObject()` có tự lấy `newName` không? **Không.** Hãy dùng `PutField.put("oldName", newName)` rồi `writeFields()`.
3. Mảng `serialPersistentFields` chỉ định tên/kiểu hay chứa giá trị mỗi object? **Chỉ định schema.** Giá trị được ghi khi serialize.
4. `GetField.defaulted("status")` khác kiểm tra `get("status", null) == null` thế nào? **Một bên kiểm tra field vắng khỏi stream, bên kia có thể gặp field hiện diện nhưng mang `null`.**
5. Vì sao cần test v2 → v1 dù v2 đọc được dữ liệu v1? **Vì khả năng đọc dữ liệu cũ không tự chứng minh v2 vẫn ghi đúng schema mà v1 mong đợi.**

**Tài liệu chính thức:** Java Object Serialization Specification — *1.5 Defining Serializable Fields for a Class*, *1.7 Accessing Serializable Fields of a Class* và *Chapter 5: Versioning of Serializable Objects*. Xem thêm JDK API `ObjectStreamField`, `ObjectStreamClass`, `ObjectOutputStream.PutField` và `ObjectInputStream.GetField`:

- https://docs.oracle.com/en/java/javase/11/docs/specs/serialization/serial-arch.html
- https://docs.oracle.com/en/java/javase/26/docs/specs/serialization/version.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectStreamField.html
- https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.GetField.html
