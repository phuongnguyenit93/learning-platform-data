# Đối tượng áp dụng là trường và phương thức liên quan hợp đồng tuần tự hóa — @Serial trong Java

> **Phạm vi:** Java 14 → **Annotation Serial**. `java.io.Serial` được bổ sung từ **Java 14**, vẫn hiện diện trong Java SE 17, 21 và 25. Bài tập trung vào **những trường (fields) và phương thức (methods) nào được phép và có ý nghĩa khi gắn `@Serial`**, chữ ký và vai trò của từng thành viên trong **Java Object Serialization**. Ví dụ dùng Java 17+ và API hiện hành, không dựa vào preview hay cơ chế đã bị loại bỏ. Java serialization còn được hỗ trợ, nhưng phải cân nhắc nghiêm túc về an toàn và khả năng tương thích trước khi dùng nó cho dữ liệu mới.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `@Serial` là annotation **đánh dấu/kiểm tra tại lúc biên dịch**, không phải cách «bật» serialization hoặc làm JVM tự tìm phương thức bất kỳ.
2. Phân biệt hai giới hạn: `@Target({ElementType.METHOD, ElementType.FIELD})` là **giới hạn cú pháp**; danh sách **bảy thành viên đặc biệt của serialization** là **giới hạn ngữ nghĩa**.
3. Nhớ chính xác **hai fields**: `serialVersionUID`, `serialPersistentFields` và **năm methods**: `writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, `readResolve`.
4. Nhận ra sự khác biệt giữa ba phương thức **private** và hai phương thức thay thế object có thể dùng các access modifiers thích hợp.
5. Biết khi nào `@Serial` không có ý nghĩa: class không `Serializable`, enum, một số thành viên của `Externalizable`, và các cơ chế đặc biệt trên record.
6. Dùng `javac --release 17 -Xlint:serial` để phát hiện một số khai báo sai; hiểu vì sao **warning không luôn là lỗi biên dịch** và compiler không bảo đảm bắt hết lỗi.
7. Biên dịch/chạy một ví dụ đầy đủ có **hai fields + năm methods**, serialize rồi deserialize dữ liệu do chương trình tự tạo để kiểm tra callback nào thực sự chạy.
8. Phân biệt `@Serial` với `@Override`, Javadoc tag `@serial` và `@SuppressWarnings("serial")`.
9. Đọc đúng tác động của `serialVersionUID` tới versioning, `serialPersistentFields` tới serial form, và method hooks tới dữ liệu lưu/khôi phục.
10. Áp dụng checklist review để tránh field sai kiểu, method sai tham số, vô tình làm serialization hook bị bỏ qua hoặc deserialize dữ liệu không tin cậy.

**Tóm tắt:** Không phải cứ là method/field trong class `implements Serializable` thì được phép gắn `@Serial`. Annotation dành cho **những thành viên mà Java Object Serialization Specification định nghĩa có vai trò đặc biệt**.

## 2. `java.io.Serial`: TARGET là FIELD và METHOD, nhưng ngữ nghĩa chặt hơn

Khai báo API chuẩn thể hiện:

```java
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial { }
```

Đây là **mô tả chữ ký API** (không phải mã tạo lại annotation trong dự án). Có ba điều cần hiểu:

- **`FIELD`:** Có thể đặt `@Serial` lên khai báo field Java. Nhưng chỉ **hai tên field đặc biệt** có tác dụng theo serialization contract.
- **`METHOD`:** Có thể đặt lên khai báo method Java. Nhưng chỉ **năm loại method hook** theo hợp đồng serialization là đúng mục đích.
- **`SOURCE`:** Annotation tồn tại ở nguồn và để compiler kiểm tra; không cần được giữ trong bytecode/class file lúc runtime và **không phải runtime switch** khiến ObjectOutputStream/ObjectInputStream hoạt động khác.

Nếu gắn `@Serial` lên **class, constructor, method parameter, local variable hoặc record component**, khai báo đó **không thuộc annotation target**, thường là lỗi compiler theo ngữ nghĩa `@Target`. Ví dụ:

```java
import java.io.Serial;

@Serial // SAI: @Serial không có target TYPE.
public class WrongPlace { }
```

Đây là **đoạn cố ý sai, không phải ví dụ chạy được**. `javac` có thể báo `annotation interface not applicable to this kind of declaration`.

**Phân biệt với validation chuyên biệt:** Nếu đặt `@Serial` lên **một field** nhưng field đó có tên/chữ ký không liên quan serialization, annotation về mặt `@Target` vẫn đúng chỗ; song về **ngữ nghĩa** nó sai. Theo Javadoc `Serial`, compiler *được khuyến khích* cảnh báo các trường hợp sai đó. Do vậy hành vi warning cụ thể có thể khác giữa compiler/version/options; `@Serial` không biến tất cả sai lầm thành lỗi biên dịch bắt buộc.

### 2.1. So với `@Override`

`@Override` yêu cầu một method thực sự override/implement method của supertype. Nhưng Java serialization hooks kiểu `private writeObject(ObjectOutputStream)` không phải phương thức trong interface `Serializable`; interface này là **marker interface** và không khai báo hook methods.

`@Serial` có mục đích tương tự về kiểm tra khai báo đặc biệt, nhưng nó **không kiểm tra overriding**. Chú giải `@Override` lên `private writeObject` sẽ sai. Ngược lại, `@Serial` không nên dùng trên method thông thường chỉ vì method được override.

Ví dụ:

```java
class Something implements java.io.Serializable {
    @java.io.Serial
    private static final long serialVersionUID = 1L;
}
```

Class này **đã** serializable do `implements Serializable`; `@Serial` chỉ đánh dấu field serialVersionUID đúng hợp đồng. **Bỏ annotation không tắt serialization**, cũng không thay đổi giá trị UID.

## 3. Danh sách đầy đủ: hai fields và năm methods

Theo Javadoc `java.io.Serial` Java SE 25:

| Loại | Thành viên đặc biệt | Dạng khai báo chuẩn | Ý nghĩa |
| --- | --- | --- | --- |
| Field 1 | `serialVersionUID` | `private static final long serialVersionUID` | UID của dạng dữ liệu serialize, phục vụ kiểm tra tương thích lớp. |
| Field 2 | `serialPersistentFields` | `private static final ObjectStreamField[] serialPersistentFields` | Khai báo danh sách fields của serial form theo cơ chế Java Object Serialization. |
| Method 1 | `writeObject` | `private void writeObject(ObjectOutputStream out) throws IOException` | Tùy chỉnh việc ghi state và optional data của class `Serializable`. |
| Method 2 | `readObject` | `private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException` | Tùy chỉnh việc đọc/khôi phục state từ stream. |
| Method 3 | `readObjectNoData` | `private void readObjectNoData() throws ObjectStreamException` | Xử lý khi một lớp serializable ở hierarchy phía nhận không có dữ liệu tương ứng trong stream. |
| Method 4 | `writeReplace` | `Object writeReplace() throws ObjectStreamException` | Chỉ định object thay thế để ghi; access modifier có thể khác private. |
| Method 5 | `readResolve` | `Object readResolve() throws ObjectStreamException` | Chỉ định object thay thế cho object đã deserialize; access modifier có thể khác private. |

**Ghi chú chữ ký:** Bảng mô tả **dạng chuẩn trong Javadoc**. Tham số có thể được đặt tên bất kỳ (`out`, `stream`); danh sách `throws` được hiển thị theo hợp đồng, không có nghĩa một method bắt buộc phải khai báo mọi checked exception nếu phần thân không thể ném chúng. Khi code review, chú ý **tên, parameter types, access, return type** và ngữ cảnh lớp; không xem `@Serial` là cách cứu một chữ ký sai.

**Hai nhóm không được gộp:** `writeExternal(ObjectOutput)` và `readExternal(ObjectInput)` của `Externalizable` là **method thuộc interface và cần `@Override`**, không nằm trong năm methods gắn `@Serial` theo Javadoc `Serial`. Phần 9 sẽ giải thích.

### 3.1. Một mẫu khung đủ bảy thành viên

```java
import java.io.*;

final class Profile implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    @Serial
    private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("name", String.class)
    };

    private String name;

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
        throw new InvalidObjectException("Missing Profile data");
    }

    @Serial
    private Object writeReplace() throws ObjectStreamException {
        return this;
    }

    @Serial
    private Object readResolve() throws ObjectStreamException {
        return this;
    }
}
```

Đây là **khung khai báo**, không có `main`; ví dụ tự chạy đầy đủ ở phần 7. Các methods `writeReplace`/`readResolve` ở đây trả chính object để **minh họa callback**, không phải bắt buộc mọi class cần cả hai. Trong dự án thật, **chỉ khai báo hook cần thiết**; đừng thêm tất cả chỉ để có đủ annotation.

## 4. Field thứ nhất: `serialVersionUID`

`serialVersionUID` giúp cơ chế Object Serialization nhận diện version của serial form. Dạng chuẩn:

```java
import java.io.Serial;
import java.io.Serializable;

public final class Invoice implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String number;

    public Invoice(String number) {
        this.number = number;
    }

    public String number() {
        return number;
    }
}
```

Đây là class độc lập **biên dịch được**, nhưng không có `main` nên chỉ là ví dụ API.

Những điều bắt buộc về field:

- Tên chính xác: **`serialVersionUID`**.
- Kiểu **`long`**, không phải `int`, `Long` hay `String`.
- Dạng có ý nghĩa theo hợp đồng: **`private static final long`**.
- Giá trị thường là một hằng `1L` hoặc một giá trị ổn định được dự án quản lý.
- `@Serial` gắn đúng field này giúp thể hiện rằng nó là **serial UID**, không phải số phiên bản của business entity hoặc schema API bất kỳ.

### 4.1. Vì sao không giao hết cho generated UID?

Nếu class `Serializable` không khai báo UID rõ ràng, runtime có cơ chế tính UID mặc định từ một số đặc tính của class. Việc đổi các thành viên/chữ ký hoặc khác biệt build có thể ảnh hưởng UID, gây `InvalidClassException` khi deserialize dữ liệu cũ.

Khi project thực sự có **dữ liệu Java-serialized cần lưu lâu dài và tương thích theo phiên bản**, hãy khai báo UID có kiểm soát. Tuy nhiên, **giữ cùng UID không tự bảo đảm dữ liệu giữa hai version tương thích**. Bạn vẫn phải kiểm soát tên/kiểu fields, hierarchy, constructors, custom read/write logic và version migration.

**Không nhầm UID với bảo mật:** Một UID khớp không xác thực nguồn dữ liệu; thay đổi UID không bảo vệ ứng dụng khỏi dữ liệu deserialize độc hại.

### 4.2. Field mang tên gần giống không được công nhận

```java
class WrongUid implements java.io.Serializable {
    @java.io.Serial
    private static final int serialVersionUID = 1; // SAI KIỂU.
}
```

Đây là **snippet cố ý sai về serialization contract**, không phải mẫu nên chạy. `@Serial` không đổi một `int` thành UID hợp lệ. Javac với lint phù hợp có thể cảnh báo nếu nhận diện member có tên đặc biệt nhưng kiểu/modifiers sai.

Tên `serialVersionId` hoặc `serialID` cũng **không** được runtime xem là `serialVersionUID`. Một compiler có thể không phát hiện mọi lỗi chính tả trên một field tùy ý dù được gắn annotation. Vì vậy review và test serial form vẫn cần thiết.

## 5. Field thứ hai: `serialPersistentFields`

Khai báo đặc biệt:

```java
import java.io.ObjectStreamField;
import java.io.Serial;

@Serial
private static final ObjectStreamField[] serialPersistentFields = {
    new ObjectStreamField("name", String.class)
};
```

Đây là **đoạn field minh họa đặt bên trong một class `implements Serializable`**, không phải file Java độc lập. Nó chỉ rõ tên và kiểu fields mà serial form muốn biểu diễn.

### 5.1. Khác với fields Java bình thường

Thông thường, default serialization của một class `Serializable` ghi các **instance fields không `static` và không `transient`**. Nếu class có:

```java
private String name;
private int age;
private transient String cache;
private static int globalCounter;
```

thì mặc định `name` và `age` là dữ liệu serializable (nếu kiểu/giá trị có thể được serialize); `cache` và `globalCounter` không thuộc phần instance state được ghi mặc định.

`serialPersistentFields` cho phép class định nghĩa **danh sách serialized fields** riêng, hữu ích khi cần giữ một serial form ổn định dù implementation fields đổi theo thời gian. Đây là cơ chế được Java Object Serialization Specification định nghĩa và vẫn hỗ trợ, nhưng **dễ tạo sai lệch** nếu không triển khai đọc/ghi tương ứng.

### 5.2. Cấu hình không chuẩn bị runtime bỏ qua

Để được nhận diện, field cần:

- Tên chính xác `serialPersistentFields`.
- Kiểu **`ObjectStreamField[]`** (mảng).
- Modifiers **`private static final`**.
- Giá trị mảng chứa các descriptors có tên và kiểu field tương ứng serial form mong muốn.

Nếu khai báo sai modifiers/kiểu, Object Serialization Specification nêu hành vi **như không khai báo special field đó**. `@Serial` không sửa hành vi runtime này; nó giúp thể hiện ý định và cho compiler cơ hội cảnh báo.

### 5.3. Khi serial form không giống instance fields

Nếu danh sách serial fields **khác cấu trúc fields thực** của class, `defaultWriteObject()/defaultReadObject()` không phải lúc nào cũng làm điều bạn muốn. Khi cần ánh xạ fields logic không có field vật lý tương ứng, sử dụng `ObjectOutputStream.PutField` và `ObjectInputStream.GetField` trong custom `writeObject/readObject` theo đặc tả.

**Không bỏ một field khỏi serial form chỉ bằng cách xóa nó khỏi `serialPersistentFields` nếu vẫn cần giải mã dữ liệu cũ.** Phải có kế hoạch tương thích (migrating defaults, missing fields, validation) và test bằng bytes tạo từ các phiên bản thực.

### 5.4. Không cần khai báo ở mọi class

Nếu chỉ cần default serialization, thường không cần `serialPersistentFields`. Đừng thêm một mảng thủ công chỉ để gắn `@Serial`: nó tạo thêm một serial form cần bảo trì. Trong ví dụ thực hành phần 7, mảng có **một field trùng với field vật lý `name`**, để bạn dễ kiểm tra runtime gọi đầy đủ những thành viên được annotation.

## 6. Ba method hooks private: `writeObject`, `readObject`, `readObjectNoData`

Chúng là các method đặc biệt **được serialization runtime phát hiện bằng tên và chữ ký**, không phải methods được `Serializable` interface khai báo, và không hoạt động như phương thức override thông thường.

### 6.1. `writeObject(ObjectOutputStream)`

Dạng chuẩn:

```java
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
}
```

Nhiệm vụ: điều khiển cách ghi state của class. `defaultWriteObject()` ghi default serializable fields (hoặc fields được mô tả qua `serialPersistentFields`). Nếu muốn ghi **optional data**, có thể ghi thêm với `out.writeInt(...)`/`writeObject(...)` theo giao thức của ObjectOutputStream, và phải có `readObject` đối ứng đọc đúng định dạng.

**Điều không được làm:** Đổi thành `public void writeObject(...)` rồi nghĩ đó là customization hook hợp lệ. Đối với `Serializable`, method ghi được hợp đồng quy định là **private**, và nếu sai access modifier, runtime sẽ không coi nó là special `writeObject` của class theo cách bạn kỳ vọng.

### 6.2. `readObject(ObjectInputStream)`

Dạng chuẩn:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
```

Nhiệm vụ: đọc lại state và thực hiện kiểm tra invariants. Nếu dùng custom write format, phải đọc theo đúng thứ tự/type mà writer đã ghi.

**Security và correctness:**

- Dữ liệu deserialize có thể tạo object **không đi qua constructor theo cách thông thường**; hãy kiểm tra invariants của class ở `readObject` hoặc dùng serialization proxy pattern khi phù hợp.
- Không chấp nhận giá trị invalid chỉ vì chúng xuất hiện trong stream.
- `defaultReadObject()` không chứng minh dữ liệu an toàn; nó chỉ khôi phục fields.
- Có thể dùng `InvalidObjectException` khi dữ liệu không thỏa hợp đồng class.

Ví dụ kiểm tra sau restore:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (name == null || name.isBlank()) {
        throw new InvalidObjectException("name must not be blank");
    }
}
```

Snippet này giả định class có field `String name`. Đây **không** phải phương án duy nhất: cần xác định invariant của dữ liệu business và điều kiện hợp lệ cho từng serial form.

### 6.3. `readObjectNoData()`

Dạng chuẩn:

```java
@Serial
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException("No data for required class");
}
```

Method này được gọi trong những tình huống **class hierarchy lúc deserialize không có đoạn dữ liệu tương ứng cho lớp đó**, ví dụ thay đổi hierarchy tương thích có lớp mới xuất hiện ở phía nhận.

**Điểm dễ nhầm:** `readObjectNoData` **không** phải callback sau mỗi `readObject`, cũng **không** chạy mỗi khi một instance field không có trong stream. Nó chỉ áp dụng trường hợp «không có dữ liệu cho class ở một level của hierarchy» theo serialization specification.

Với trường hợp thiếu field mặc định do đổi schema tương thích, field thường được cấp **default value** tương ứng (0, false, null) hoặc đọc theo custom logic; không dùng `readObjectNoData` như một bộ bắt lỗi chung cho mọi missing field.

### 6.4. Phải là `private`, không phải `@Override`

Ba method trên nên khai báo `private` như Javadoc nêu. Một ví dụ sai:

```java
class BadWrite implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    @Serial
    public void writeObject(ObjectOutputStream out) throws IOException {
        out.defaultWriteObject();
    }
}
```

**Cố ý sai, không dùng để chạy.** `-Xlint:serial` trên javac Java 21 đã được kiểm tra và cho warning cùng nội dung chính: **`serialization-related method writeObject not declared private`**. Nếu dùng `-Werror`, warning có thể khiến build thất bại.

**Chú ý:** `writeObject` không phải «hàm ghi log object theo ý mình»; runtime sẽ chỉ tìm dạng được quy định. Đặt tên `writeObjects` hoặc tham số `DataOutputStream` là hai cách khai báo method bình thường, không phải hook `writeObject`.

## 7. Hai method hooks thay thế: `writeReplace` và `readResolve`

Hai phương thức này **khác** ba methods trên về access modifier và mục đích.

### 7.1. `writeReplace()`

Dạng chuẩn:

```java
@Serial
private Object writeReplace() throws ObjectStreamException {
    return this;
}
```

Javadoc `Serial` cho phép **any-access-modifier** đối với `writeReplace`; dùng `private` ở ví dụ chỉ là lựa chọn, không phải yêu cầu bắt buộc như `writeObject`.

Khi phù hợp theo serialization protocol, runtime có thể yêu cầu object **đề xuất một object thay thế** để ghi vào stream. Ví dụ ứng dụng dùng **serialization proxy pattern**, trong đó một proxy serializable chứa dữ liệu ổn định thay cho object implementation thực.

Nếu method trả `this`, như trong bài thực hành, nó **không làm thay đổi object đang ghi**; chủ yếu là minh họa runtime có nhận diện hook.

### 7.2. `readResolve()`

Dạng chuẩn:

```java
@Serial
private Object readResolve() throws ObjectStreamException {
    return this;
}
```

Nhiệm vụ: sau khi deserialization tạo object, method có thể chỉ định object **thay thế** mà người gọi nhận. Điều này hữu ích trong những trường hợp kiểm soát canonical instances hoặc proxy resolution, nhưng cần rất cẩn thận về invariants, subtype và object graph.

**Không giả định** `readResolve` luôn được gọi nếu stream chưa thể tạo đúng object, class không thể được deserialize, hoặc serialization bị chặn trước đó. Nó không phải cơ chế sửa mọi dữ liệu hỏng.

### 7.3. Access modifier và inheritance

Khác `writeObject`/`readObject`/`readObjectNoData` là private methods không được kế thừa, `writeReplace` và `readResolve` có thể có mức truy cập phù hợp với quy tắc inheritance của Java/serialization.

Một triển khai có thể dùng `protected Object writeReplace()` hoặc `protected Object readResolve()` theo nhu cầu. **Không** có ý nghĩa «cứ public hơn là luôn tốt hơn»: mở rộng access cần thiết kế và có thể ảnh hưởng inheritance/subclass semantics. Nếu không có nhu cầu inheritance, dùng private là cách giảm bề mặt API.

**Không dùng `@Override` thay cho `@Serial` chỉ vì hai methods có thể được thừa kế**: chúng vẫn là protocol hooks, không phải methods của `Serializable` interface.

## 8. Chương trình chạy được: đủ hai fields và năm methods

Chương trình dưới đây đã được kiểm tra bằng **JDK 21**, biên dịch với `--release 17 -Xlint:serial`. Nó serialize một `Profile` do chính chương trình tạo ra vào `byte[]` rồi deserialize lại. **Đừng dùng ví dụ này để đọc byte streams từ nguồn không tin cậy.**

Lưu file **`SerialContractsDemo.java`**:

```java
import java.io.*;

public class SerialContractsDemo {
    static final class Profile implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        @Serial
        private static final ObjectStreamField[] serialPersistentFields = {
                new ObjectStreamField("name", String.class)
        };

        private String name;

        Profile(String name) {
            this.name = name;
        }

        @Serial
        private void writeObject(ObjectOutputStream out) throws IOException {
            System.out.println("writeObject");
            out.defaultWriteObject();
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            System.out.println("readObject");
        }

        @Serial
        private void readObjectNoData() throws ObjectStreamException {
            throw new InvalidObjectException("Missing Profile data");
        }

        @Serial
        private Object writeReplace() throws ObjectStreamException {
            System.out.println("writeReplace");
            return this;
        }

        @Serial
        private Object readResolve() throws ObjectStreamException {
            System.out.println("readResolve");
            return this;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;

        try (var output = new ByteArrayOutputStream();
             var stream = new ObjectOutputStream(output)) {
            stream.writeObject(new Profile("Ada"));
            stream.flush();
            bytes = output.toByteArray();
        }

        try (var stream = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            Profile restored = (Profile) stream.readObject();
            System.out.println("name=" + restored.name);
        }
    }
}
```

Biên dịch/chạy trên **Java 17+**:

```bash
javac --release 17 -Xlint:serial SerialContractsDemo.java
java SerialContractsDemo
```

**Stdout chính xác của ví dụ:**

```text
writeReplace
writeObject
readObject
readResolve
name=Ada
```

### 8.1. Tại sao có bốn dòng hook mà không phải năm?

Thứ tự thực tế:

1. `ObjectOutputStream.writeObject(new Profile("Ada"))` bắt đầu ghi object.
2. `writeReplace()` được nhận diện trước khi ghi để chọn object thay thế. Ở đây trả `this` nên không thay.
3. `writeObject(ObjectOutputStream)` được gọi để ghi serializable fields; `defaultWriteObject()` ghi `name`.
4. Khi đọc, `readObject(ObjectInputStream)` được gọi và `defaultReadObject()` khôi phục `name`.
5. `readResolve()` chạy sau khi object được khôi phục, trả `this`.
6. Main in `name=Ada`.
7. `readObjectNoData()` **không chạy** vì stream có đầy đủ đoạn dữ liệu class `Profile`. Method được khai báo/annotate đúng nhưng chỉ thực thi trong trường hợp hierarchy đặc biệt đã nói ở phần 6.3.

**Hai fields** `serialVersionUID` và `serialPersistentFields` **không phải callbacks** nên chúng không in một dòng riêng. JVM sử dụng metadata của chúng khi xử lý serialization.

### 8.2. Vì sao ví dụ chỉ dùng dữ liệu do chính nó ghi?

Java native object serialization có thể tạo ra chuỗi đối tượng phức tạp với nhiều lớp được khôi phục. Deserialize dữ liệu từ nguồn không tin cậy làm tăng rủi ro gadget chains, logic ở constructors/hooks hoặc tài nguyên bị tiêu thụ quá mức. `@Serial` **không** xác thực dữ liệu hoặc hạn chế lớp được đọc.

Ở đây dữ liệu được viết bằng chính code chạy trong process rồi đọc lại bằng `ByteArrayInputStream`, mục đích là **thực hành API trong phạm vi đáng tin cậy**. Khi thiết kế hệ thống thật, xem thêm `ObjectInputFilter` và hướng tiếp cận truyền dữ liệu phù hợp phần 13.

### 8.3. Nhận xét về `serialPersistentFields` trong mẫu

`new ObjectStreamField("name", String.class)` tương ứng với field vật lý `private String name`. Vì vậy `defaultWriteObject()/defaultReadObject()` làm việc đúng. Nếu đổi serialized field sang tên khác nhưng không viết code mapping, demo có thể không còn giữ dữ liệu như bạn mong muốn.

### 8.4. Không nên triển khai đủ bảy thành viên nếu không cần

Bài dùng đủ các members để bạn **nhìn thấy hợp đồng của `@Serial`**, không khuyến nghị mọi class `Serializable` phải tự định nghĩa cả năm hooks. Trong ứng dụng thông thường, field `serialVersionUID` có thể là thành viên đặc biệt duy nhất được khai báo; các class đơn giản thường không cần custom `readObject` hoặc `writeObject`.

## 9. Lưu ý lớn: `Externalizable` không dùng mọi serialization hooks của `Serializable`

`Externalizable` **extends `Serializable`**, nhưng định nghĩa một giao thức khác:

```java
public interface Externalizable extends Serializable {
    void writeExternal(ObjectOutput out) throws IOException;
    void readExternal(ObjectInput in)
            throws IOException, ClassNotFoundException;
}
```

Hai methods trên được yêu cầu bởi interface, nên chúng cần **`@Override`**, không phải `@Serial`. Javadoc `Serial` xác định những thành viên sau **không có tác dụng** trong class `Externalizable`:

- `private void writeObject(ObjectOutputStream)`;
- `private void readObject(ObjectInputStream)`;
- `private void readObjectNoData()`;
- `private static final ObjectStreamField[] serialPersistentFields`.

Vì `Externalizable` ghi/đọc state qua `writeExternal`/`readExternal`, các hook và special field trên bị bỏ qua theo cơ chế của nó. Gắn `@Serial` lên chúng là **sai ngữ nghĩa** dù về mặt syntax vẫn là FIELD/METHOD. Compiler với lint có thể cảnh báo «not effective in an Externalizable class».

**Những gì còn phù hợp:** `serialVersionUID` vẫn có vai trò, nên `@Serial` trên field UID là hợp lệ. `writeReplace` và `readResolve` cũng có thể áp dụng cho object Externalizable theo hợp đồng serialization. Đừng kết luận sai rằng «Externalizable không bao giờ được dùng `@Serial`».

### 9.1. Ví dụ tự chạy: `@Serial` ở UID, `@Override` ở hai methods của interface

Lưu file **`ExternalDemo.java`**:

```java
import java.io.*;

public class ExternalDemo {
    public static class Packet implements Externalizable {
        @Serial
        private static final long serialVersionUID = 1L;

        private int id;

        // Externalizable cần public no-arg constructor.
        public Packet() { }

        Packet(int id) {
            this.id = id;
        }

        @Override
        public void writeExternal(ObjectOutput out) throws IOException {
            out.writeInt(id);
        }

        @Override
        public void readExternal(ObjectInput in)
                throws IOException, ClassNotFoundException {
            id = in.readInt();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] data;

        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(new Packet(7));
            out.flush();
            data = bytes.toByteArray();
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(data))) {
            Packet copy = (Packet) in.readObject();
            System.out.println("id=" + copy.id);
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 -Xlint:serial ExternalDemo.java
java ExternalDemo
```

**Stdout chính xác:**

```text
id=7
```

Chương trình được kiểm tra trên JDK 21, `--release 17`.

**Giải thích:** Runtime sử dụng **`writeExternal`** và **`readExternal`** do class implement interface `Externalizable`. Vì chúng là interface methods nên dùng `@Override`. `@Serial` chỉ đánh dấu field UID ở ví dụ này.

**Đừng hiểu lầm:** `@Serial` không thay `public no-arg constructor` của Externalizable. Nếu class thiếu public no-arg constructor đúng hợp đồng, việc restore Externalizable object có thể thất bại.

### 9.2. Thí nghiệm cố ý sai trên Externalizable

```java
class BadExternal implements java.io.Externalizable {
    @java.io.Serial
    private static final long serialVersionUID = 1L;

    @java.io.Serial
    private void writeObject(java.io.ObjectOutputStream out)
            throws java.io.IOException { }

    public BadExternal() { }

    @Override
    public void writeExternal(java.io.ObjectOutput out)
            throws java.io.IOException { }

    @Override
    public void readExternal(java.io.ObjectInput in)
            throws java.io.IOException, ClassNotFoundException { }
}
```

Đoạn này **cố ý đặt `@Serial` sai nghĩa** trên `writeObject`. `Externalizable` bỏ qua hook này; trình biên dịch có thể cảnh báo khi chạy `javac -Xlint:serial`. Không dùng warning như bằng chứng method được gọi: điều đúng là phải **xóa method sai** và để `writeExternal/readExternal` thực hiện việc ghi/đọc.

## 10. Enum và record: cùng là Java type nhưng hợp đồng serial form khác

### 10.1. Enum: UID cố định và hooks không có tác dụng

Một enum Java có cơ chế serialization đặc biệt: hằng số enum được khôi phục theo **tên enum constant**. Theo Java Object Serialization Specification, mọi enum có **`serialVersionUID` cố định bằng `0L`** và các khai báo special UID/persistent fields của enum bị bỏ qua. Các hooks tùy chỉnh `writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, `readResolve` cũng bị bỏ qua trong enum.

Vì vậy:

```java
enum Priority {
    LOW, HIGH;

    @java.io.Serial // SAI NGỮ NGHĨA: enum không dùng UID field riêng.
    private static final long serialVersionUID = 123L;
}
```

Đây là **đoạn minh họa sai**, không phải pattern được khuyến nghị. Không cố điều khiển serial form của enum bằng `@Serial` trên field hay hook bị bỏ qua. Nếu cần persistence schema ổn định không lệ thuộc tên hằng enum, nên lưu định danh dữ liệu theo một giao thức/schema riêng.

### 10.2. Record: dùng canonical constructor, bỏ qua một số hooks

Một record `implements Serializable` được serialize theo **record components**. Khi deserialize, runtime tái tạo các component values rồi gọi **canonical constructor** của record; đây là hành vi vẫn được Object Serialization Specification hỗ trợ.

Đối với serializable record:

- `writeObject`, `readObject` và `readObjectNoData` theo kiểu class thông thường **bị bỏ qua**;
- `serialPersistentFields` cũng **bị bỏ qua**, vì serial form được xác định theo record components;
- `writeReplace` và `readResolve` **có thể được dùng** để chỉ định replacement objects;
- Record có `serialVersionUID` mặc định là `0L` nếu không khai báo; yêu cầu khớp UID được **miễn** cho record theo specification.

Ví dụ record tối giản:

```java
import java.io.Serializable;

public record Receipt(String code, long cents)
        implements Serializable {
}
```

Đây là type definition hợp lệ trên Java 17+, nhưng không có `main`.

**Không viết `@Serial private void readObject(...)` trong record rồi kỳ vọng nó được gọi để validate**. Nếu cần kiểm tra invariant của record khi deserialize, canonical constructor là điểm cần thiết kế phù hợp. Nếu muốn thay thế object trong quá trình serialize/deserialize, đọc riêng `writeReplace`/`readResolve` theo đặc tả.

### 10.3. Bảng so sánh theo loại class

| Loại | `serialVersionUID` | `serialPersistentFields` | `writeObject/readObject/readObjectNoData` | `writeReplace/readResolve` |
| --- | --- | --- | --- | --- |
| Class `implements Serializable` thông thường | Có ý nghĩa | Có ý nghĩa | Có ý nghĩa nếu đúng signature | Có ý nghĩa nếu đúng signature |
| Class `implements Externalizable` | Có ý nghĩa | **Không dùng** | **Không dùng** | Có thể có ý nghĩa |
| `enum` | Bị bỏ qua, runtime dùng UID 0 | Bị bỏ qua | Bị bỏ qua | Bị bỏ qua |
| `record implements Serializable` | Có đặc thù (mặc định 0; UID mismatch được miễn) | Bị bỏ qua | Bị bỏ qua | Có thể có ý nghĩa |
| Class **không** `Serializable` | Không có ý nghĩa serialization | Không có ý nghĩa | Không có ý nghĩa | Không có ý nghĩa |

Bảng mô tả **hiệu lực trong serialization mechanism**, không chỉ việc Java syntax có cho phép khai báo field/method như vậy hay không. Đối với các loại có cơ chế đặc biệt, **annotation đúng vị trí cú pháp chưa chắc đúng ngữ nghĩa**.

## 11. Kiểm tra bằng `javac -Xlint:serial` và hiểu giới hạn cảnh báo

`javac` có lint category **`serial`**. Khi dùng JDK 17+:

```bash
javac --release 17 -Xlint:serial SerialContractsDemo.java
```

Tùy mã nguồn, compiler có thể cảnh báo: thiếu UID, sai modifier của một serialization method, trường hoặc method mang annotation nhưng không có hiệu lực trong context. Để coi warnings là lỗi build:

```bash
javac --release 17 -Xlint:serial -Werror SerialContractsDemo.java
```

Với chương trình `SerialContractsDemo.java` đúng ở phần 8, hai lệnh **biên dịch thành công** trên JDK 21.

### 11.1. Ví dụ cảnh báo có thể tái hiện

Lưu **`BadSerialDemo.java`**:

```java
import java.io.*;

class BadSerialDemo implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    @Serial
    public void writeObject(ObjectOutputStream output)
            throws IOException {
    }
}
```

`javac` trên JDK 21 với:

```bash
javac --release 17 -Xlint:serial BadSerialDemo.java
```

sẽ đưa ra một warning có nội dung chính:

```text
warning: [serial] serialization-related method writeObject not declared private
1 warning
```

Vị trí dòng, dấu mũ `^`, đường dẫn file và định dạng một số phần diagnostic có thể khác theo compiler/phiên bản, nên bảng trên chỉ trích **nội dung cốt lõi**, không phải nguyên văn toàn bộ stderr.

**Kết luận:** `@Serial` không sửa modifier của method. Nếu code khai báo `public writeObject`, nó vẫn **không** là special hook private theo Java Object Serialization Specification. Hãy đổi method về đúng chữ ký và test serialize/deserialize.

### 11.2. Lỗi nào là compilation error, lỗi nào là warning?

- `@Serial` đặt lên class (`TYPE`) **không phù hợp `@Target`** → compiler error theo Java annotation rules.
- `@Serial` đặt lên method `writeObject` nhưng modifier sai → **có thể được compiler báo warning** với `-Xlint:serial`.
- `@Serial` đặt trên member bị bỏ qua trong `Externalizable` hoặc record → **có thể được compiler báo warning**.
- Method/field bình thường có tên không thuộc bảy thành viên vẫn có thể được compiler **không cảnh báo** trong một số bản/cách gọi, vì Javadoc nói compilers *encouraged* to validate. Không xem «compile sạch» là lời xác nhận mọi `@Serial` đều có ý nghĩa.

Trong một thử nghiệm JDK 21, code gắn `@Serial` lên method `writeObjects(ObjectOutputStream)` (số nhiều) không nhất thiết nhận warning cùng kiểu với `writeObject` có modifier sai. Đó là lý do lint **hỗ trợ**, nhưng không thay thế review và runtime tests.

### 11.3. `@SuppressWarnings("serial")` không thay `@Serial`

`@SuppressWarnings("serial")` **điều khiển cảnh báo của compiler**, ví dụ một số trường hợp thiếu UID; nó không thêm UID, không đánh dấu method hook và không sửa serial form.

`@Serial` làm rõ ý định và cho phép kiểm tra khai báo serialization-related; nó không có mục tiêu xóa cảnh báo bất kỳ kiểu nào.

**Không dùng `@SuppressWarnings("serial")` để che lỗi `writeObject` sai chữ ký** nếu mục đích của class là custom serialization. Hãy sửa đúng method.

## 12. Khác biệt giữa annotation `@Serial` và Javadoc tag `@serial`

Dù tên gần giống, đây là **hai cơ chế khác nhau**:

| Thành phần | Viết ở đâu | Vai trò |
| --- | --- | --- |
| `@Serial` | Annotation trên **field/method declaration** | Kiểm tra/ngụ ý thành viên thuộc serialization contract. |
| `@serial` | Javadoc comment | Tài liệu hóa serializable field và serialized form. |
| `@serialField` | Javadoc comment | Mô tả entry trong `serialPersistentFields`. |
| `@serialData` | Javadoc comment | Mô tả dữ liệu tùy chỉnh ghi bởi `writeObject` hoặc `writeExternal`. |

Ví dụ tài liệu:

```java
/**
 * Ổn định mã người dùng khi ghi xuống object stream.
 * @serial serialized user code
 */
private String code;
```

Đây là **snippet của một field**. `@serial` trong Javadoc **không** phải annotation `java.io.Serial`; nó không xuất hiện như `@Serial` trước declaration. Ngược lại, `@Serial` **không thay thế tài liệu serialized form**, nhất là khi dữ liệu cần tương thích với các bản đã phát hành.

**Điểm thực tiễn:** Trong API có nhu cầu lưu object stream lâu dài, đặc tả serialized form và quy tắc versioning còn quan trọng hơn việc thêm annotation cho đẹp.

## 13. Bảo mật: `@Serial` không biến native deserialization thành an toàn

Mặc dù Java serialization vẫn được hỗ trợ, deserialize object graph phức tạp từ nguồn **không tin cậy** có rủi ro nghiêm trọng: gadget chains, object construction side effects, resource exhaustion hoặc dữ liệu không thỏa invariants.

**`@Serial` không làm những điều sau:**

- Không xác thực người gửi hoặc bytes nhận được.
- Không chặn class độc hại được deserialize.
- Không giới hạn depth, references, arrays hoặc kích thước object graph.
- Không cấp phép truy cập reflection.
- Không ngăn serialization proxy/hook được gọi.
- Không tự mã hóa hay ký nội dung object stream.

### 13.1. Giải pháp khi ứng dụng bắt buộc phải deserialize

- Ưu tiên **dữ liệu có schema rõ ràng và parser phù hợp** khi thiết kế protocol mới, thay vì đưa một object graph Java tùy ý qua ranh giới tin cậy.
- Nếu bắt buộc đọc native Java serialization, chỉ đọc từ nguồn đã được quản lý/cho phép, thiết kế allowlist classes và giới hạn resource.
- Java có `ObjectInputFilter` và các cơ chế lọc deserialization; hãy nghiên cứu cấu hình filter **đúng với ứng dụng** và JDK đang chạy. Filter là **một lớp phòng vệ**; không thay thế kiểm soát nguồn dữ liệu và invariants.
- Với class có `readObject`, kiểm tra invariants và ném `InvalidObjectException` nếu dữ liệu sai.
- Đọc stream trong điều kiện giới hạn quyền và tài nguyên; theo dõi metrics, timeout và lỗi phù hợp với hệ thống.

Một ví dụ khái niệm về resource filter:

```java
import java.io.ObjectInputFilter;

// Minh họa ý tưởng cấu hình trong một phương thức:
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=5;maxrefs=100;maxarray=1000;!*");
// Mẫu trên cực chặt, từ chối mọi class chưa được cho phép;
// không áp dụng nguyên xi cho một ứng dụng thực tế.
```

**Đây là snippet minh họa, không phải chương trình tự chạy hoặc cấu hình sản xuất.** Pattern filter phải được thiết kế với classes thực sự cần nhận, loại stream data, resource ceilings và policy từ môi trường. Việc có `@Serial` trên fields/methods không liên quan trực tiếp tới việc filter có chấp nhận class hay không.

### 13.2. Không giải quyết tất cả bằng UID

`serialVersionUID` hỗ trợ **kiểm tra tương thích serial form**, không phải checksum bảo mật hay định danh duy nhất chống giả mạo. Kẻ tấn công có thể tạo stream có descriptor UID đúng; vì vậy mã review và vận hành phải coi nguồn bytes đáng tin quan trọng hơn sự hiện diện của UID.

## 14. Quy trình áp dụng `@Serial` trong codebase

Nếu dự án đang có các class `implements Serializable`, một cách triển khai có kiểm soát:

1. **Tìm đúng đối tượng:** Xác định classes implement `Serializable` hoặc `Externalizable`, enum, record; không áp dụng đồng loạt mọi type.
2. **Xem mục đích:** Class được serialize thật, hay chỉ implement interface vì yêu cầu của một thư viện? Có cần giữ binary serialized form qua phiên bản không?
3. **Tìm special UID:** Nếu có `serialVersionUID`, kiểm tra `private static final long` và giá trị có quản trị versioning không.
4. **Tìm `serialPersistentFields`:** Nếu có, kiểm tra kiểu `ObjectStreamField[]` và cấu hình serialized fields, cũng như mapping đọc/ghi liên quan.
5. **Tìm methods:** `writeObject`/`readObject`/`readObjectNoData` phải đúng private và chữ ký; `writeReplace`/`readResolve` có chữ ký hợp lệ, không đọc/ghi sai format.
6. **Đặt `@Serial`:** Chỉ lên những fields/methods thực sự có ý nghĩa, không gắn lên mọi field thường.
7. **Chạy compiler lint:** `javac --release 17 -Xlint:serial` hoặc cấu hình compiler/IDE trong build tool (Maven/Gradle) tương ứng.
8. **Không chỉ dựa vào lint:** Review schema, runtime behavior, enum/record/Externalizable special cases, cả paths mà compiler có thể chưa cảnh báo.
9. **Test round trip:** Serialize một instance tin cậy, deserialize và kiểm tra dữ liệu/invariants phù hợp.
10. **Test compatibility:** Nếu phải đọc bytes từ version cũ, giữ fixture streams đã kiểm soát và thử trên version mới.
11. **Kiểm tra failure paths:** Mismatch UID, trường missing, invalid values, thư viện/provider bị thiếu, filter từ chối class; không che mọi exception.
12. **Rà soát bảo mật:** Có inbound untrusted streams không? Có filter, allowlist, giới hạn resources và cách quản lý lỗi không?
13. **Tài liệu hóa serial form:** Dùng Javadoc tags khi cần public compatibility contract.
14. **Không tối ưu nhầm chỗ:** Thêm `@Serial` không tăng tốc serialization hay thay đổi wire format, nên không đo performance trước/sau như một tính năng runtime.

### 14.1. Checklist review nhanh

| Câu hỏi | Kết quả mong muốn |
| --- | --- |
| Annotation gắn lên field/method? | Đúng `@Target`, không đặt lên class/parameter/constructor. |
| Field tên `serialVersionUID` có đúng kiểu? | `private static final long`. |
| Field `serialPersistentFields` có đúng kiểu? | `private static final ObjectStreamField[]`. |
| `writeObject` có đúng tên/tham số/visibility? | `private void writeObject(ObjectOutputStream)`. |
| `readObject` đúng chữ ký? | `private void readObject(ObjectInputStream)`. |
| `readObjectNoData` đúng mục đích? | `private void readObjectNoData()`; không gọi trong round trip thường. |
| `writeReplace`/`readResolve` có đúng chữ ký? | Không nhận tham số; trả object thay thế phù hợp. |
| Loại class có xử lý riêng không? | Xét enum, record, Externalizable. |
| Compiler có warning gì? | Chạy `-Xlint:serial`, review toàn bộ diagnostics. |
| Serialized data có bất biến? | Test old/new data và lớp filter khi cần. |
| Có đánh dấu nhầm method business? | Không dùng `@Serial` trên method bình thường. |
| Có tin annotation đủ để bảo mật? | Không: cần filter, source trust, resource limits. |

## 15. Các lỗi thường gặp

| Nhận định hoặc lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| «`@Serial` gắn trên class Serializable». | Target chỉ FIELD/METHOD. | Đặt trên các special members hợp lệ. |
| «Mọi instance field nên có `@Serial`». | Annotation không dành cho field thường `name`, `age`. | Chỉ `serialVersionUID` hoặc `serialPersistentFields`. |
| «`@Serial` tự đánh dấu một class thành Serializable». | Chỉ `implements Serializable` (hoặc hierarchy có liên quan) quyết định cơ chế serializable. | Xác định type contract riêng. |
| «`@Serial` vẫn hiện qua reflection runtime». | Retention `SOURCE`. | Không dùng runtime reflection để kiểm annotation. |
| «`serialVersionUID` có thể là `int`». | Java serialization yêu cầu special field kiểu `long`. | Dùng `private static final long`. |
| «Có cùng UID chắc chắn đọc mọi stream cũ». | Khả năng tương thích còn phụ thuộc serial form/hierarchy. | Test version compatibility thực tế. |
| «`serialPersistentFields` có thể là `List<ObjectStreamField>`». | Special field yêu cầu `ObjectStreamField[]`. | Đúng kiểu và modifiers. |
| «`public writeObject` là hook serialization». | `writeObject` phải private. | Đổi chữ ký đúng và chạy lint/runtime test. |
| «`readObjectNoData` chạy khi một field thiếu». | Nó áp dụng trường hợp không có dữ liệu cho lớp trong hierarchy. | Phân biệt missing class data với missing field. |
| «`writeReplace` phải private giống `writeObject`». | Javadoc nêu any-access-modifier. | Dùng modifier phù hợp thiết kế. |
| «`Externalizable.writeExternal` nên gắn `@Serial`». | Không nằm trong bảy members của annotation. | Dùng `@Override` cho interface methods. |
| «`writeObject` của Externalizable chạy khi ghi». | Externalizable dùng `writeExternal`. | Không khai báo ineffective hooks. |
| «Enum có thể custom serial form bằng `@Serial`». | Enum có giao thức riêng và UID 0, bỏ qua hooks. | Persist tên/mã có schema khác nếu cần. |
| «Record đọc bằng `readObject` hook thông thường». | Record dùng canonical constructor. | Validate ở record constructor và đọc record spec. |
| «Không có warning là chắc chắn đúng». | Compiler chỉ được khuyến khích kiểm tra mọi semantic misuse. | Kết hợp lint, code review và test thực tế. |
| «`@SuppressWarnings("serial")` sửa UID sai». | Nó chỉ giảm warnings, không sửa serialization contract. | Sửa field thật. |
| «`@Serial` bảo vệ object stream khỏi input độc hại». | Annotation không phải filter. | Dùng nguồn tin cậy, ObjectInputFilter, schema an toàn. |

## 16. Bài tập tự kiểm tra

### Bài 1 — Nhận diện target

Trong các vị trí: class, method, field, constructor, parameter, vị trí nào `@Serial` cho phép về cú pháp?

**Đáp án:** Chỉ **field và method**. Còn về ngữ nghĩa phải là special member serialization đúng kiểu/ngữ cảnh.

### Bài 2 — Đếm members

Có tất cả bao nhiêu members special theo danh sách `@Serial`?

**Đáp án:** **Bảy**: hai fields (`serialVersionUID`, `serialPersistentFields`) và năm methods (`writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, `readResolve`).

### Bài 3 — Phân biệt field thường

`@Serial private String name;` trong class `implements Serializable` có đúng không?

**Đáp án:** Sai mục đích. `name` là field dữ liệu thông thường; nó có thể được serialize theo cơ chế default, nhưng không phải một trong hai special fields nhận `@Serial`.

### Bài 4 — Modifier của `writeObject`

`@Serial public void writeObject(ObjectOutputStream out)` có được runtime gọi như special hook không?

**Đáp án:** Không theo hợp đồng. Method serialization hook có chữ ký **private void**; javac với `-Xlint:serial` có thể cảnh báo modifier sai.

### Bài 5 — Vai trò của `serialPersistentFields`

`serialPersistentFields` được đặt thành `private static final List<ObjectStreamField>`, compiler có thể biên dịch declaration. Nó có được coi là special field đúng không?

**Đáp án:** Không. Kiểu special field phải là **`ObjectStreamField[]`**, không phải `List`. Annotation không đổi kiểu hoặc format.

### Bài 6 — `readObjectNoData`

Chương trình round trip một instance bình thường có phải luôn gọi `readObjectNoData` không?

**Đáp án:** Không. Hook này dành cho trường hợp class trong hierarchy không có đoạn dữ liệu tương ứng trong stream.

### Bài 7 — Externalizable

Bạn cần ghi dữ liệu `id` của một class `Externalizable`. Nên dùng `@Serial writeObject` hay `@Override writeExternal`?

**Đáp án:** Dùng **`@Override public void writeExternal(ObjectOutput)`**; đọc qua `@Override readExternal(ObjectInput)`. `@Serial` có thể đặt trên field UID có ý nghĩa nhưng không đặt trên hai methods của interface đó.

### Bài 8 — Enum

Gắn `@Serial` vào `serialVersionUID = 7L` của enum có thay đổi UID được ghi không?

**Đáp án:** Không. Enum có UID cố định **0L**, declaration bị serialization mechanism bỏ qua.

### Bài 9 — Record

Một record `implements Serializable` muốn validate các components khi deserialize. Có thể dựa vào `@Serial private readObject` như class thông thường không?

**Đáp án:** Không. Record deserialization gọi **canonical constructor**; special `readObject` bị bỏ qua. Dùng invariants trong canonical constructor và đọc record serialization contract.

### Bài 10 — Hành vi `@Serial` lúc runtime

Nếu bạn xóa `@Serial` khỏi một `private void writeObject(ObjectOutputStream)` đã khai báo đúng, serialization có tự nhiên ngừng gọi method không?

**Đáp án:** Không. Runtime dùng **chữ ký/contract** của special method, không yêu cầu annotation. Tuy nhiên, xóa annotation làm mất tín hiệu kiểm tra/hỗ trợ của compiler.

### Bài 11 — Kiểm thử với `-Xlint:serial`

Compiler không cảnh báo một method bị viết sai tên `writeObjects`. Có thể kết luận method đó là hook hợp lệ không?

**Đáp án:** Không. Phải so tên/chữ ký với spec và kiểm tra hành vi thực tế. `javac` không bảo đảm bắt tất cả semantic misuse.

### Bài 12 — Bảo mật

Một service nhận bytes từ Internet rồi gọi `new ObjectInputStream(...).readObject()`. Thêm `@Serial` cho DTO có làm dữ liệu an toàn chưa?

**Đáp án:** Chưa. `@Serial` là annotation dành cho kiểm tra code; cần đánh giá ranh giới tin cậy, lọc class/resources bằng `ObjectInputFilter` khi bắt buộc dùng native serialization và cân nhắc schema protocol an toàn hơn.

## 17. Nguồn chính thức còn áp dụng

1. [Java SE 25 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serial.html): `@Target(METHOD,FIELD)`, `@Retention(SOURCE)`, **hai fields và năm methods**, các trường hợp semantic misuse (non-Serializable, enum, Externalizable); API **Since 14**.
2. [Java SE 17 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html): đối chiếu tính khả dụng với ví dụ `javac --release 17`.
3. [Java SE 25 — `Serializable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serializable.html): marker interface và các serialization hooks có ý nghĩa.
4. [Java SE 25 — `Externalizable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Externalizable.html): `writeExternal`/`readExternal` và public no-arg constructor.
5. [Java Object Serialization Specification — System Architecture](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/serial-arch.html): `serialPersistentFields`, cách ghi/đọc object, khác biệt enum/record và các Javadoc serial tags.
6. [Java SE 25 — `ObjectOutputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectOutputStream.html): `defaultWriteObject`, `PutField`, ghi custom data.
7. [Java SE 25 — `ObjectInputStream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputStream.html): `defaultReadObject`, `GetField`, đọc state và các trường hợp đặc biệt.
8. [Java SE 25 — `ObjectStreamField`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectStreamField.html): mô tả thành phần của `serialPersistentFields`.
9. [Java SE 25 — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputFilter.html): kiểm soát/deserialization filtering, không thay thế thiết kế an toàn.
10. [Java SE 25 — `javac` tool](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-Xlint:serial`, `-Werror` và các compiler warnings.
11. [Java Object Serialization Specification — Versioning](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/version.html): xem cách serial form/UID tương tác với class evolution và compatibility.
12. [Oracle Java Serialization FAQ](https://www.oracle.com/java/technologies/javase/serializationfaq-jsp.html): phân biệt `@serial`, `@serialField`, `@serialData` trong Javadoc với annotation ở Java source.

**Ghi nhớ cuối:** `@Serial` **chỉ nhắm tới FIELD/METHOD** và về ngữ nghĩa chỉ dành cho **2 special fields + 5 special methods** của Java Object Serialization trong class có context phù hợp. Nó **không** bật serialization, không thay đổi wire format, không sửa sai chữ ký và không bảo vệ input. Với `Externalizable`, enum, record, hãy theo **giao thức riêng của loại đó**; kiểm tra bằng `javac -Xlint:serial` kết hợp runtime tests và code review, không chỉ nhìn annotation.