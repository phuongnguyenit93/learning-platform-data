# Chữ ký đúng của thành viên được đánh dấu bằng @Serial trong Java

## 1. Mục tiêu và điểm cần nhớ

Annotation `java.io.Serial` (viết `@Serial`) xuất hiện từ **Java 14** và vẫn là API chính thức trong Java hiện hành. Nó đánh dấu một **field** hoặc **method** mà cơ chế Java Object Serialization được thiết kế để nhận diện. Mục tiêu của annotation là giúp người đọc mã và công cụ phân tích biết rằng thành viên phải tuân thủ **tên, kiểu, modifier và danh sách tham số** đúng với giao thức serialization; nếu khai báo sai, Java serialization có thể âm thầm bỏ qua thành viên và dùng cơ chế mặc định.

Nội dung bài này chỉ tập trung vào **“Chữ ký đúng của thành viên được đánh dấu”** trong chủ đề **Annotation Serial**. Sau bài học, bạn sẽ:

1. Nhận diện đúng **2 field** và **5 method** được tài liệu `@Serial` chỉ định.
2. Biết khi nào các modifier `private`, `static`, `final` và kiểu tham số/trả về là điều kiện quan trọng.
3. Phân biệt `@Serial` với `@Override`: đây là dấu đánh dấu *serialization hook*, **không phải** một method override bình thường.
4. Nhận ra các trường hợp method có tên gần đúng hoặc signature sai **vẫn có thể biên dịch**, nhưng serialization runtime **không gọi** method dự định.
5. Hiểu giới hạn của `@Serial` với `Externalizable`, `enum` và `record`.
6. Biên dịch/chạy một chương trình **JDK 17+ độc lập**, có đủ 7 thành viên hợp lệ và kiểm chứng round-trip của object.
7. Sử dụng `javac -Xlint:serial` và kiểm tra bằng thực nghiệm, không giả định chỉ cần viết `@Serial` là compiler luôn phát hiện mọi sai sót.

**Special Note về kiến thức hiện hành:** Bài sử dụng API ổn định từ Java 14 và tiếp tục có trong JDK 17–26, không dựa vào preview hoặc cách làm legacy. **Java native serialization vẫn tồn tại**, nhưng deserialize dữ liệu từ nguồn không tin cậy **có rủi ro bảo mật nghiêm trọng**; ví dụ chỉ đọc luồng byte do chính chương trình tạo, không quảng bá native serialization làm định dạng mặc định cho API mới.

## 2. @Serial là annotation ở mức nguồn

Khai báo chính thức tương đương:

```java
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial {
}
```

Đây là **mô hình giải thích**, không phải code yêu cầu bạn tự định nghĩa `@Serial`: annotation thật **đã có sẵn trong JDK** tại `java.io.Serial`. Các phần quan trọng:

- `@Target({METHOD, FIELD})`: chỉ áp dụng cho **phương thức** hoặc **trường**, không đặt trên class, constructor hoặc tham số.
- `@Retention(SOURCE)`: annotation được dùng ở giai đoạn xử lý source, **không được lưu như annotation runtime** để Java serialization đọc bằng reflection.
- `@Serial` tự nó **không bật chế độ serialization**. Một class thông thường cần `implements Serializable` hoặc kế thừa một class đã Serializable để thuộc cơ chế đó.
- `@Serial` **không đổi tên, chữ ký, quyền truy cập** hay nội dung của method; không thể biến một method sai thành đúng chỉ bằng annotation.
- Mục đích của nó là **tài liệu hóa ý định và hỗ trợ kiểm tra ở compile time**. Javadoc yêu cầu compiler *được khuyến khích* phát cảnh báo cho khai báo không phù hợp, nhưng không hứa mọi compiler/JDK đều báo mọi lỗi.

Import thông thường:

```java
import java.io.Serial;
import java.io.Serializable;
```

Ví dụ khai báo serial version UID:

```java
final class Invoice implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;
}
```

Đây là một **class hợp lệ ở mức cú pháp** và `@Serial` có nghĩa. Bản thân annotation **không có effect đặc biệt ở runtime**; quy tắc nhận diện field `serialVersionUID` đến từ Java Object Serialization Specification.

## 3. Bảng chữ ký chuẩn: đúng 2 field và 5 method

Theo Javadoc `java.io.Serial` của Java 17 và Java 26, những thành viên được đánh dấu phải khớp mô hình sau trong **lớp mà cơ chế serialization có thể sử dụng**.

| Loại | Chữ ký khai báo khuyến nghị | Vai trò |
| --- | --- | --- |
| Field 1 | `private static final long serialVersionUID` | Định danh phiên bản của serial form cho class |
| Field 2 | `private static final ObjectStreamField[] serialPersistentFields` | Danh sách trường persistent do class khai báo |
| Method 1 | `private void writeObject(ObjectOutputStream out) throws IOException` | Tùy chỉnh ghi phần trạng thái của class |
| Method 2 | `private void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException` | Tùy chỉnh khôi phục trạng thái của class |
| Method 3 | `private void readObjectNoData() throws ObjectStreamException` | Xử lý khi không có serialized data cho một class trong hierarchy |
| Method 4 | `Object writeReplace() throws ObjectStreamException` | Chỉ định object thay thế trước khi ghi |
| Method 5 | `Object readResolve() throws ObjectStreamException` | Chỉ định object thay thế khi đọc xong |

**Ngoại lệ về visibility:** Với **`writeReplace` và `readResolve`**, Javadoc ghi **ANY-ACCESS-MODIFIER**, tức có thể là `private`, package-private, `protected` hoặc `public` trong phạm vi được serialization runtime coi là hợp lệ. Cách đặt quyền ảnh hưởng **quy tắc tìm method và khả năng thừa kế**; khi method chỉ phục vụ class hiện tại, `private` thường dễ hiểu và hạn chế mở quyền không cần thiết.

**Giữ chữ ký đầy đủ trong mẫu:** Java coi `throws` không phải thành phần phân biệt method overload ở mức ngôn ngữ. Tuy nhiên, nên viết đúng mẫu khai báo `throws` trong tài liệu để thể hiện nhóm exception và contract; lỗi quan trọng để runtime nhận diện thường nằm ở **tên, modifier, kiểu trả về và kiểu/số tham số**.

Đừng hiểu bảng là “mọi class Serializable phải khai báo cả 7”. Các hooks là **tùy chọn**, chỉ khai báo khi có yêu cầu tùy chỉnh. Trong các class Serializable thông thường, một `@Serial private static final long serialVersionUID` được khai báo có chủ đích thường là đủ; không tạo thêm `readObject`/`writeObject` nếu cơ chế mặc định đã đáp ứng nhu cầu.

## 4. Hai field đặc biệt: kiểu và modifier không được nhầm

### 4.1. serialVersionUID

Mẫu được `@Serial` Javadoc khuyến nghị:

```java
@Serial
private static final long serialVersionUID = 1L;
```

Ý nghĩa:

- **Tên chính xác:** `serialVersionUID`, phân biệt chữ hoa/chữ thường.
- **Kiểu chính xác:** primitive `long`, không phải `int`, `Long`, `String` hay `BigInteger`.
- **`static final`:** field hằng ở mức class, không phải field instance.
- **`private`:** nên dùng để mô tả phiên bản **của chính class khai báo**, tránh làm người đọc hiểu UID của superclass được thừa kế. Javadoc của `Serializable` cho biết runtime có thể nhận serialVersionUID với access modifier khác, nhưng `@Serial` mô tả mẫu chuẩn là `private static final long`.
- **Giá trị:** `1L` là ví dụ; trong ứng dụng duy trì dữ liệu nhiều phiên bản, phải quản lý UID và tương thích serial form có chủ đích.

Đổi UID khi dữ liệu cũ chưa tương thích có thể dẫn tới `InvalidClassException` lúc deserialize. **Giữ UID không tự làm mọi thay đổi field/class tương thích**; cùng UID vẫn phải xét những quy tắc evolution của serialization.

**Sai kiểu phổ biến:**

```java
@Serial
private static final int serialVersionUID = 1; // SAI: int, không phải long
```

Đây là **ví dụ cố ý sai về serialization**, không chép vào class chuẩn. Compiler có thể cảnh báo khi bật `-Xlint:serial`, nhưng không nên đồng nhất mọi cảnh báo với lỗi cú pháp bắt buộc.

### 4.2. serialPersistentFields

Mẫu chuẩn:

```java
@Serial
private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("displayName", String.class),
        new ObjectStreamField("level", int.class)
};
```

`ObjectStreamField[]` là mảng mô tả **các trường thuộc serial form**. Đó là **metadata serialization**, không phải mảng chứa dữ liệu giá trị của từng instance. Trong ví dụ, hai mục lần lượt khai báo tên/kiểu `displayName: String` và `level: int`.

Các yêu cầu:

- Tên đúng chính xác `serialPersistentFields`.
- Kiểu **`java.io.ObjectStreamField[]`**, không phải `Object[]` hay `List<ObjectStreamField>`.
- `private static final` theo đặc tả; nếu không hợp lệ, cơ chế có thể **không dùng** cấu hình fields bạn tưởng đã chỉ định.
- Không khai báo cho đủ bảy mục nếu không cần kiểm soát serial form; đây là tính năng dành cho lớp có chủ đích về schema serialized.

Nếu class dùng `serialPersistentFields` cùng `writeObject`/`readObject`, cần ghi/đọc đúng các named fields thông qua `putFields()/writeFields()` và `readFields()`, hoặc cơ chế tương thích phù hợp. Khai báo mảng này **không tự serialize các giá trị instance tùy ý**.

## 5. Ba phương thức private chuyên xử lý dữ liệu class

### 5.1. writeObject — tham số phải là ObjectOutputStream

Chữ ký chính thức:

```java
@Serial
private void writeObject(ObjectOutputStream out)
        throws IOException {
    out.defaultWriteObject();
}
```

Trong class `implements Serializable`, method này được serialization runtime gọi để lưu trạng thái dành cho class đó. `defaultWriteObject()` sử dụng cơ chế ghi trường mặc định (theo serial form hiện hành).

Điều kiện dễ sai:

- Phải là **instance method**, không thêm `static`.
- Phải có **`private`** và kiểu trả về **`void`**.
- Có đúng **một tham số kiểu `ObjectOutputStream`** (không phải `OutputStream`, `ObjectInputStream` hoặc kiểu do ứng dụng tự định nghĩa).
- Tên phải là `writeObject`, đúng chính tả/case.

**Không phải override:** `Serializable` là marker interface, không có method `writeObject` để override. Vì thế dùng `@Override` ở đây là sai.

### 5.2. readObject — tham số phải là ObjectInputStream

Chữ ký chính thức:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
```

`defaultReadObject()` phục hồi trạng thái theo serial form. Trong class có validation hoặc bất biến nội bộ, bạn có thể kiểm tra dữ liệu sau khi đọc; nếu dữ liệu không hợp lệ, ném một ngoại lệ thích hợp như `InvalidObjectException`.

Các lỗi phổ biến:

- Viết `readObject(ObjectOutputStream in)`: sai **kiểu tham số**.
- Viết `public void readObject(ObjectInputStream in)`: không phải method private đặc biệt mà serialization protocol mong đợi.
- Viết `static void readObject(...)`: runtime không coi là hook instance đúng.
- Gọi `defaultReadObject()` ở vị trí tùy ý ngoài một `readObject` đang được deserialization kích hoạt: có thể ném `NotActiveException`.

Không đánh dấu một method tự viết sai chữ ký là “đã được bảo vệ bởi @Serial”; hãy kiểm tra behavior thực.

### 5.3. readObjectNoData — không có tham số

Chữ ký:

```java
@Serial
private void readObjectNoData()
        throws ObjectStreamException {
    throw new InvalidObjectException("missing serialized state");
}
```

Đây là method dùng cho trường hợp **không có dữ liệu trong stream cho class đó** do một số kịch bản thay đổi hierarchy/serial form. Nó **không tự được gọi trong mỗi lần deserialize bình thường**. Dùng để khôi phục hoặc từ chối một trạng thái không thể duy trì invariant.

Lưu ý:

- **Không nhận tham số**.
- Return **`void`** và là **`private instance method`**.
- `ObjectStreamException` là superclass của các exception serialization chuyên biệt như `InvalidObjectException`.
- Đừng tự gọi method này trong business logic như một “callback sau readObject”. Nó có mục đích rất cụ thể trong cơ chế object deserialization.

## 6. Hai phương thức thay thế object: writeReplace và readResolve

### 6.1. writeReplace

Mẫu:

```java
@Serial
private Object writeReplace()
        throws ObjectStreamException {
    return this;
}
```

Cơ chế serialization có thể gọi `writeReplace()` trước khi ghi đối tượng, và sử dụng object mà method trả về làm **đại diện thay thế**. Ví dụ trả `this` không thay thế gì; nó chỉ giúp quan sát chữ ký hợp lệ.

Dùng trong thiết kế thật khi một đối tượng phức tạp cần **serialization proxy** có serial form được kiểm soát. Nhưng code thay thế phải bảo đảm kiểu và quan hệ tham chiếu tương thích — trả sai object có thể gây lỗi khi đọc lại.

### 6.2. readResolve

Mẫu:

```java
@Serial
private Object readResolve()
        throws ObjectStreamException {
    return this;
}
```

Method này có thể được gọi khi đối tượng đã đọc xong, để chọn **object thay thế được trả cho caller**. Một use case có kiểm soát là bảo toàn singleton hoặc canonical instances.

Hai method có cùng đặc điểm:

- **Không có tham số**.
- Return type theo mẫu chuẩn là **`Object`** (không phải `void`).
- Chỉ dành cho **instance method**.
- Modifier truy cập có thể khác `private` theo Javadoc; quy tắc runtime xác định method có được thừa kế/truy cập hay không.
- Không phải tên được thừa kế từ `Serializable`; không gắn `@Override` khi chỉ đang khai báo hook này.

**Không lạm dụng:** Với một lớp dữ liệu bình thường, không cần viết `writeReplace()` hoặc `readResolve()` nếu không muốn thay thế đối tượng. Hai hook này có thể làm cho tham chiếu đối tượng/đồ thị dữ liệu khác với kỳ vọng nếu không thiết kế cẩn thận.

## 7. Ví dụ Java 17+ chạy được: đủ cả bảy thành viên hợp lệ

Ví dụ dưới đây dùng một class Serializable được lồng trong chương trình. Lớp này có:

- `@Serial serialVersionUID` kiểu `long`;
- `@Serial serialPersistentFields` mô tả một trường serialized tên `content`;
- cả năm method `writeObject`, `readObject`, `readObjectNoData`, `writeReplace`, `readResolve` với chữ ký đúng;
- một **transient instance field** `content` được ghi/đọc có chủ đích qua `PutField` và `GetField`;
- phép kiểm tra giá trị không null sau khi deserialize.

**Tạo file `SerialSignatureDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.ObjectStreamException;
import java.io.ObjectStreamField;
import java.io.Serial;
import java.io.Serializable;
import java.util.Objects;

public final class SerialSignatureDemo {
    private SerialSignatureDemo() {
    }

    private static final class Note implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        @Serial
        private static final ObjectStreamField[] serialPersistentFields = {
                new ObjectStreamField("content", String.class)
        };

        private transient String content;

        Note(String content) {
            this.content = Objects.requireNonNull(content);
        }

        String content() {
            return content;
        }

        @Serial
        private void writeObject(ObjectOutputStream out)
                throws IOException {
            ObjectOutputStream.PutField fields = out.putFields();
            fields.put("content", content);
            out.writeFields();
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            ObjectInputStream.GetField fields = in.readFields();
            String value =
                    (String) fields.get("content", (Object) null);
            if (value == null) {
                throw new InvalidObjectException(
                        "content is required");
            }
            this.content = value;
        }

        @Serial
        private void readObjectNoData()
                throws ObjectStreamException {
            throw new InvalidObjectException(
                    "missing serialized state");
        }

        @Serial
        private Object writeReplace()
                throws ObjectStreamException {
            return this;
        }

        @Serial
        private Object readResolve()
                throws ObjectStreamException {
            return this;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        Note original = new Note("xin chao Java");
        byte[] bytes;

        try (ByteArrayOutputStream buffer =
                     new ByteArrayOutputStream();
             ObjectOutputStream out =
                     new ObjectOutputStream(buffer)) {
            out.writeObject(original);
            out.flush();
            bytes = buffer.toByteArray();
        }

        Note restored;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            restored = (Note) in.readObject();
        }

        System.out.println("restored=" + restored.content());
        System.out.println("sameContent="
                + original.content().equals(restored.content()));
        System.out.println("sameInstance=" + (original == restored));
    }
}
```

### Lệnh chạy

Dùng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:serial SerialSignatureDemo.java
java SerialSignatureDemo
```

**Stdout mong đợi chính xác:**

```text
restored=xin chao Java
sameContent=true
sameInstance=false
```

Mã nguồn đã dùng những class có sẵn của Java SE; không yêu cầu thư viện ngoài, module descriptor, cờ preview hay file đầu vào từ người dùng. Đây là **round-trip từ buffer được tạo nội bộ**, không phải ví dụ deserialize dữ liệu ngoài Internet.

### Vì sao stdout đúng?

1. Constructor tạo `Note("xin chao Java")`. `Objects.requireNonNull` bảo đảm input nội bộ ban đầu không null.
2. `ObjectOutputStream.writeObject(original)` gọi cơ chế serialization. Trong class `Note`, `writeReplace()` trả `this`, không tạo object thay thế khác.
3. `writeObject` lấy `PutField`, gán giá trị `content` vào logical persistent field rồi gọi `writeFields()`. Field instance `content` có modifier `transient`, nhưng serial form được kiểm soát qua `serialPersistentFields`.
4. `ObjectInputStream.readObject()` khôi phục object theo serial form; `readObject` dùng `readFields()` lấy lại `content` và kiểm tra null.
5. `readResolve()` trả chính instance vừa đọc, không hợp nhất với object `original` đang có trong bộ nhớ.
6. `readObjectNoData()` **không chạy** ở round-trip bình thường này, vì stream có dữ liệu cho class `Note`. Nó được khai báo để minh họa đúng chữ ký và cách bảo vệ invariant nếu gặp trường hợp thiếu dữ liệu cho class.
7. Vì `original` và `restored` là **hai object khác nhau**, `sameInstance=false`; chuỗi content giống nhau nên `sameContent=true`.

Ví dụ dùng tất cả bảy thành viên để phục vụ **đối chiếu chữ ký**, không có nghĩa ứng dụng thực cần viết đủ bảy hook. Với một class chỉ có field Serializable đơn giản, tùy chỉnh `writeObject`/`readObject`/`serialPersistentFields` thường không cần thiết.

## 8. Các khai báo sai thường không được serialization runtime công nhận

Những ví dụ dưới đây **cố tình sai**. Chúng **không** thuộc chương trình chạy ở mục 7, và không nên chép chúng vào class chính.

```java
// Sai kiểu UID (phải là long).
@Serial
private static final int serialVersionUID = 1;

// Sai tên field.
@Serial
private static final long serialVersionId = 1L;

// Sai kiểu tham số (phải ObjectOutputStream).
@Serial
private void writeObject(ObjectInputStream in) {}

// Sai modifier (method readObject phải là instance private).
@Serial
private static void readObject(ObjectInputStream in) {}

// Sai chính tả: không còn là hook readObject.
@Serial
private void readObjekt(ObjectInputStream in) {}

// Sai số lượng tham số.
@Serial
private void readObjectNoData(int reason) {}

// Sai return type: writeReplace phải trả object.
@Serial
private void writeReplace() {}
```

Chúng chỉ là **mảnh mã minh họa đặt trong một class implements Serializable**, không phải file Java hoàn chỉnh. Khi đưa chúng cùng lúc vào một class, còn có thể xảy ra lỗi overload/duplicate hoặc lỗi khác không phản ánh riêng serialization.

**Mức độ phát hiện cần mô tả trung thực:**

- `javac -Xlint:serial` có thể phát **warning** cho một số khai báo serialization sai (chẳng hạn `serialVersionUID` sai kiểu hoặc `writeObject` sai tham số), tùy phiên bản compiler.
- `@Serial` có mục đích cho phép kiểm tra ở compile time, nhưng **không có bảo đảm “mọi thành viên sai sẽ làm javac thất bại”**. Một tên lạ như `readObjekt` vẫn có thể là method Java bình thường và chưa chắc bị warning chỉ vì có `@Serial`.
- Một method khai báo đúng cú pháp Java nhưng **không phù hợp serialization protocol** có thể bị **runtime bỏ qua**. Khi đó object vẫn có thể serialize/deserialize, nhưng validation hoặc transformation bạn kỳ vọng không chạy.
- Nếu cần build nghiêm ngặt hơn, xử lý cảnh báo lint/IDE/static analyzer theo quy định nhóm; **đừng biến mọi cảnh báo bất kỳ thành lỗi** nếu chưa rõ nguyên nhân. Có thể bật `-Werror` có chủ đích sau khi rà soát các warnings phù hợp.

**Bài học:** chữ ký đúng là yêu cầu cơ chế serialization; `@Serial` giúp diễn đạt ý định, nhưng **test kết quả thật** và rà soát compiler warnings mới chứng minh code thực hiện đúng hành vi.

## 9. Chữ ký đúng nhưng đặt ở sai loại class vẫn có thể vô nghĩa

### 9.1. Class không implements Serializable

`@Serial` không thay thế `implements Serializable`. Nếu type không Serializable và cũng không kế thừa khả năng Serializable, serialization runtime không sử dụng các field/method đặc biệt của nó. Theo Javadoc `@Serial`, đánh dấu các member trong class không Serializable là **không có ngữ cảnh ý nghĩa**.

```java
class NotSerializable {
    @Serial
    private static final long serialVersionUID = 1L;
}
```

Đây là một **ví dụ cố ý sai về ý nghĩa annotation**. Không suy ra rằng đặt `@Serial` khiến class này có thể truyền vào `ObjectOutputStream` rồi serialize thành công.

### 9.2. Enum

Mọi `enum` đều là Serializable theo cơ chế đặc biệt, nhưng enum có **serialVersionUID được định nghĩa là `0L`** và các customization methods như `writeObject`, `readObject`, `writeReplace`, `readResolve` được bỏ qua. Vì vậy **không đánh dấu các declarations vô hiệu đó bằng `@Serial`**.

Nếu bạn muốn một enum constant được bảo toàn khi serialize, hãy dựa trên semantics serialization dành riêng cho enum; không cố viết `readResolve()` để buộc nó thành singleton, vì enum được xử lý khác ordinary Serializable class.

### 9.3. Externalizable

`Externalizable` extends `Serializable` nhưng dùng cơ chế **`writeExternal(ObjectOutput)`** và **`readExternal(ObjectInput)`**; class Externalizable cũng có quy tắc constructor riêng. Theo Javadoc `@Serial`, trong class Externalizable, những declaration sau **không được dùng**:

- `writeObject(ObjectOutputStream)`;
- `readObject(ObjectInputStream)`;
- `readObjectNoData()`;
- field `serialPersistentFields`.

`@Serial` không phải annotation cho `writeExternal` hoặc `readExternal`: chúng là phương thức định nghĩa bởi interface `Externalizable`, thường dùng `@Override`. `serialVersionUID` và hai replacement hooks có quy tắc riêng, không nằm trong nhóm bốn thành viên bị liệt kê là vô hiệu ở trên.

### 9.4. Record implements Serializable

Một `record` có thể `implements Serializable` và có **serial form đặc thù**. Serialization của record dùng record components và quá trình dựng lại bằng canonical constructor; các method class-specific `writeObject`, `readObject`, `readObjectNoData` và `serialPersistentFields` **không điều khiển quá trình này**.

Tuy nhiên, `writeReplace` và `readResolve` có thể tham gia cơ chế thay thế object đối với record theo serialization specification. Về UID, record mặc định có `serialVersionUID=0L` nếu không tự khai báo; kiểm tra khớp UID giữa serialized record và local record không áp dụng như ordinary serializable class.

**Không nhầm với enum:** record có cơ chế kiểm soát/ngoại lệ khác enum. Kiểm tra tài liệu serialization phiên bản JDK đang triển khai thay vì sao chép nguyên ví dụ hook của ordinary class sang record.

## 10. @Override, @Serial, và việc compiler kiểm tra chữ ký

Với một method thông thường override method ở superclass/interface, `@Override` được compiler kiểm tra theo quy tắc override. Nhưng `writeObject` hoặc `readObject` thuộc giao thức **được Object Serialization nhận diện theo quy ước chữ ký**, không phải method khai báo sẵn trong interface `Serializable`.

Vì vậy:

```java
// ĐÚNG về ý định serialization.
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
```

Còn:

```java
// SAI: @Override không dành cho private serialization hook.
@Override
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
```

Đây là **đoạn minh họa trong class**; ví dụ `@Override` có thể dẫn tới lỗi compiler vì không thực sự override method hợp lệ.

### Thêm lint nhưng không hứa điều gì không có trong API contract

Chạy:

```bash
javac --release 17 -Xlint:serial SerialSignatureDemo.java
```

`-Xlint:serial` bật nhóm cảnh báo serialization của `javac`; trong các JDK hiện đại, nó giúp kiểm tra những khai báo không hợp lệ và thiếu `serialVersionUID` theo phạm vi hỗ trợ của compiler. **Chức năng cảnh báo cụ thể có thể khác giữa phiên bản**: ngay cả khi dùng `@Serial`, không được hứa kiểm tra hoàn chỉnh mọi tên method không hợp lệ.

Đối với `@Serial`:

- **SOURCE retention**: không thể dựa vào `Note.class.getDeclaredMethods()` để truy vấn annotation `@Serial` ở runtime; nó không phải runtime-retained annotation.
- **Không bắt buộc phải đánh dấu mọi member** để serialization hoạt động; annotation giúp đọc mã và tool analysis.
- **Không thay đổi chữ ký**: nếu bạn khai báo sai, annotation không “sửa” logic trong JVM.
- **Không thay thế kiểm thử**: dùng round-trip để kiểm chứng nội dung, identity, validation, schema evolution nếu ứng dụng thực sự dùng serialization.

## 11. Serialization inheritance: chú ý nơi khai báo hook

Một class con Serializable có thể kế thừa các field/method thông thường từ superclass, nhưng **serialization-related declarations không phải tất cả đều kế thừa theo cùng cách**.

- `serialVersionUID` áp dụng **theo class khai báo**, không phải một version UID chung thừa kế cho toàn bộ hierarchy.
- `serialPersistentFields` cũng là schema đặc biệt cho **class khai báo**.
- `private writeObject`, `private readObject`, `private readObjectNoData` gắn với phần serial form của từng class; không phải cách ghi/đọc trạng thái mọi subclass.
- `writeReplace`/`readResolve` có quy tắc accessibility và inheritance riêng; `private` có thể không được kế thừa, trong khi method với access khác có thể áp dụng cho subclass tùy semantics và context.

Một subclass chỉ đặt `@Serial` trên một method giống tên **không** có nghĩa đã override được serialization behavior của superclass. Nếu cần versioning an toàn, hãy xem Java Object Serialization Specification và test tương thích với dữ liệu ghi từ phiên bản cũ.

## 12. Bảo mật và tính hiện hành khi dùng serialization

Java Object Serialization là một cơ chế còn tồn tại trong JDK hiện đại, nhưng **deserialize dữ liệu từ nguồn không đáng tin là rủi ro nghiêm trọng**. Có thể có object graph phức tạp, classpath gadget, tác dụng phụ trong `readObject`/`readResolve` và các cuộc tấn công gây tiêu thụ tài nguyên.

Quy tắc vận hành:

1. **Không** coi `@Serial` là validation hay sandbox. Nó chỉ mô tả ý định method/field ở source.
2. Với một giao thức trao đổi dữ liệu mới, cân nhắc định dạng được thiết kế cho môi trường không tin cậy (ví dụ JSON, Protobuf) và một parser có schema/validation rõ ràng.
3. Nếu buộc dùng Java serialization, chỉ nhận stream từ nguồn được tin cậy **và** áp dụng giới hạn deserialization theo yêu cầu sản phẩm, ví dụ `ObjectInputFilter`, giới hạn kích thước/độ sâu/số đối tượng, allowlist type phù hợp, kiểm tra bất biến và dependency.
4. Trong `readObject`/`readResolve`, không chạy code nguy hiểm dựa trên input chưa xác minh hoặc thiết kế side effect thiếu kiểm soát.
5. Dùng `serialVersionUID` có chủ đích, kiểm thử schema evolution và xử lý `InvalidClassException` đúng nguyên nhân; UID không phải checksum hoặc chữ ký số chống sửa dữ liệu.

Ví dụ `SerialSignatureDemo` tạo byte stream **trong cùng tiến trình rồi đọc lại** chỉ để minh họa chữ ký và luồng hoạt động; nó **không** được trình bày như một service dùng để nhận blob không đáng tin qua network.

## 13. Checklist review từng thành viên

| Thành viên | Tên đúng? | Kiểu/params đúng? | Access/modifiers đúng? | Có áp dụng cho class? |
| --- | --- | --- | --- | --- |
| `serialVersionUID` | Chính tả/case | primitive `long` | `private static final` theo mẫu `@Serial` | Serializable class; không có ý nghĩa trên enum |
| `serialPersistentFields` | Chính tả/case | `ObjectStreamField[]` | `private static final` | Ordinary Serializable; không hiệu quả trên Externalizable/record |
| `writeObject` | Chính tả/case | `void(ObjectOutputStream)` | `private`, **không static** | Ordinary Serializable; không hiệu quả trên Externalizable/record |
| `readObject` | Chính tả/case | `void(ObjectInputStream)` | `private`, **không static** | Ordinary Serializable; không hiệu quả trên Externalizable/record |
| `readObjectNoData` | Chính tả/case | `void()` | `private`, **không static** | Ordinary Serializable; không hiệu quả trên Externalizable/record |
| `writeReplace` | Chính tả/case | `Object()` | Instance; access theo khả năng truy cập | Serializable/Externalizable; record có quy tắc riêng |
| `readResolve` | Chính tả/case | `Object()` | Instance; access theo khả năng truy cập | Serializable/Externalizable; record có quy tắc riêng |

**Hai bước QA bổ sung:** Biên dịch với `-Xlint:serial` và **quan sát runtime** của một round-trip hợp lệ. Một test round-trip không thể kích hoạt `readObjectNoData` trừ khi dựng được đúng bối cảnh stream/hierarchy thiếu dữ liệu; vì vậy không đánh dấu “đã chạy readObjectNoData” chỉ vì method tồn tại trong class.

## 14. Bài tập thực hành

### Bài 1 — Điền đủ bảy chữ ký

Không nhìn tài liệu, liệt kê **2 field + 5 method** của `@Serial`, kèm modifier, tham số, kiểu trả về và nhóm `throws`. Đối chiếu với bảng mục 3, đặc biệt phân biệt `ObjectOutputStream` và `ObjectInputStream`.

### Bài 2 — Tìm lỗi không nhất thiết bị compiler bắt

Xem đoạn khai báo:

```java
@Serial
private void writeObject(ObjectInputStream in) {
    // ...
}
```

Chỉ ra vì sao method này sai, loại tham số đúng phải là gì và hậu quả nếu serialization runtime bỏ qua hook. Kiểm tra warning thực tế bằng `javac -Xlint:serial`; không mặc định annotation sẽ tạo compiler error.

### Bài 3 — Kiểm tra serialVersionUID

Thay field `long serialVersionUID` bằng `int` trong một bản thử riêng, bật `-Xlint:serial`. Ghi rõ nội dung warning nếu có, phân biệt **kiểu field hợp lệ trong Java** với **kiểu field có ý nghĩa với serialization**.

### Bài 4 — Sửa readObjectNoData

Xem các khai báo sau, quyết định đâu là hợp lệ:

```java
private void readObjectNoData() throws ObjectStreamException;
private Object readObjectNoData() throws ObjectStreamException;
private void readObjectNoData(ObjectInputStream in);
```

Đây là **chữ ký minh họa**, không phải các method hoàn chỉnh để copy vào class. Đáp án: chỉ chữ ký **đầu tiên** có tên, kiểu trả về và số tham số đúng; trong một class thường bạn vẫn phải thêm **method body** hoặc khai báo trong bối cảnh hợp lệ.

### Bài 5 — Round-trip và schema

Chạy `SerialSignatureDemo.java`. Sau đó thêm một logical persistent field `priority` kiểu `int` và cập nhật cả `putFields`/`readFields`. Kiểm tra dữ liệu vừa ghi vẫn khôi phục đúng. Với dữ liệu lưu dài hạn, thiết kế quy tắc tương thích khi phiên bản mới gặp stream cũ.

### Bài 6 — So sánh ordinary class, record và enum

Viết bảng quy tắc riêng cho `writeObject`, `readObject`, `serialPersistentFields` và `writeReplace` khi dùng với `enum`, ordinary Serializable class, `record` và `Externalizable`. Lý giải vì sao không thể sao chép bảy khai báo từ ordinary class sang mọi loại type.

### Bài 7 — Cảnh báo không phải kiểm thử

Thử đổi tên `readObject` thành `readObjekt` trong một bản thử. Quan sát compiler/lint và kết quả deserialize; giải thích vì sao code vẫn có thể chạy nhờ default serialization nhưng validation viết trong `readObjekt` **không được gọi**.

### Bài 8 — Ranh giới tin cậy

Giả sử ứng dụng cần tiếp nhận tệp từ khách hàng không tin cậy. Trả lời: `@Serial` đã làm gì và **chưa làm gì** cho bảo mật? Đề xuất định dạng/protocol và các biện pháp kiểm tra, giới hạn dữ liệu phù hợp thay vì chỉ dùng `ObjectInputStream.readObject()`.

**Tiêu chí hoàn thành:** Người học khai báo đúng bảy thành viên được liệt kê trong `java.io.Serial`, không nhầm các hooks với method override, biết @Serial không bảo đảm mọi warning/error, nhận diện các bối cảnh không có hiệu lực và tự chạy một round-trip minh họa với JDK hiện đại.

## 15. Tài liệu chính thức

- [Oracle Java SE 17 — java.io.Serial](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html): đầy đủ hai field, năm method, `@Target`, `@Retention` và các bối cảnh không có hiệu lực.
- [Oracle Java SE 26 — java.io.Serial](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Serial.html): xác nhận annotation và tập chữ ký vẫn có trong JDK hiện hành.
- [Oracle Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): contract của `writeObject`, `readObject`, `writeReplace`, `readResolve` và `serialVersionUID`.
- [Oracle Java SE 26 — Serializable](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Serializable.html): cảnh báo deserialize nguồn không đáng tin và xử lý đặc thù enum/record.
- [Java Object Serialization Specification — System Architecture](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/serial-arch.html): serial form, custom field processing, record serialization và hook.
- [Oracle Java SE 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `-Xlint:serial` và các cảnh báo compiler.
- [Oracle Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): giới hạn loại/object graph khi dùng ObjectInputStream với dữ liệu cần kiểm soát.

**Ghi nhớ:** `@Serial` chỉ có ý nghĩa khi member **đúng tên, đúng chữ ký và đúng loại class**. Hai field chuẩn là `serialVersionUID` và `serialPersistentFields`; năm method là `writeObject`, `readObject`, `readObjectNoData`, `writeReplace` và `readResolve`. Annotation giúp ghi nhận ý định và hỗ trợ kiểm tra source, nhưng **không thay thế compiler lint, kiểm thử hành vi, hoặc bảo mật deserialization**.