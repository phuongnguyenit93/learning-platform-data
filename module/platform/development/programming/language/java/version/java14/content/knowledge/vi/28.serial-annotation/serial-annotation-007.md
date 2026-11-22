# Duy trì hợp đồng `Serializable` của thư viện bằng `@Serial`

## 1. Bài toán: thư viện vẫn phải đọc được dữ liệu đã ghi từ phiên bản trước

Một thư viện Java có thể đã công khai kiểu dữ liệu `implements Serializable` để ứng dụng khác lưu trạng thái, trao đổi object với một thành phần nội bộ được tin cậy, hoặc tiếp tục đọc các tệp nhị phân Java Object Serialization đã phát hành. Sau khi người dùng đã lưu các tệp đó, **việc đổi một lớp thư viện không chỉ là chuyện sửa API nguồn**: ta còn phải cân nhắc **hợp đồng dữ liệu đã tuần tự hóa** (*serialized form*).

Từ **Java 14**, `java.io.Serial` (viết `@Serial`) hỗ trợ đánh dấu những khai báo đặc biệt tham gia cơ chế serialization của Java. Annotation này **vẫn hiện hành trong Java 17/21/25 và các JDK mới**.

**Trọng tâm:** Nếu một thư viện **thực sự còn cam kết hỗ trợ `Serializable`**, hãy duy trì hợp đồng ấy một cách có chủ đích: khai báo `serialVersionUID` ổn định, dùng `@Serial` ở đúng vị trí để compiler phát hiện sai chữ ký, bảo vệ invariant khi deserialization, thử tương thích với dữ liệu do phiên bản cũ tạo ra, và giới hạn dữ liệu được phép đọc. **Không bổ sung Java native serialization cho API mới chỉ vì thấy `@Serial` ngắn gọn.**

**Ba điều không nên nhầm:**

1. **`implements Serializable`** là một cơ chế runtime cho phép Java Object Serialization xử lý một đối tượng theo quy tắc serialization.
2. **`@Serial`** là annotation nguồn giúp compiler và người đọc mã nhận biết những khai báo đặc biệt; nó **không tự tạo serial form, không tự nâng version và không tự mã hóa dữ liệu**.
3. **`serialVersionUID`** là định danh version của dạng serialized class theo cơ chế Java serialization; nó **không phải** version Maven, số bản phát hành thư viện hay schema migration tổng quát.

Nếu dự án **không còn hợp đồng `Serializable`**, việc tự thêm `@Serial` hoặc `implements Serializable` không phải yêu cầu của Java hiện đại. Với giao thức, API hoặc file format mới, nên xem xét định dạng dữ liệu có schema, phiên bản và kiểm soát input rõ ràng thay vì mặc định dùng Java native serialization.

## 2. Khi nào tiếp tục dùng `Serializable` là hợp lý?

Tình huống hợp lý nhất không phải “vì Java làm được”, mà là **đang có ràng buộc tương thích đã tồn tại**:

- Thư viện có một kiểu public `Serializable`, và khách hàng đã lưu object qua `ObjectOutputStream`.
- Một module nội bộ được kiểm soát đang đọc lại object đã tạo từ bản thư viện trước.
- Có dữ liệu migration cần đọc trong một giai đoạn chuyển đổi có kế hoạch.
- API đã hứa tính serializable của một kiểu trong tài liệu tương thích; phá hợp đồng có thể gây lỗi cho người dùng.
- Một cache/job-state nội bộ dùng Java serialization với phiên bản cụ thể và có kiểm soát rủi ro, không nhận byte stream từ nguồn không tin cậy.

**Không nên suy diễn:** không phải mọi Java library đều cần serializable, và không phải mọi kiểu implements Serializable là hợp đồng ổn định mãi mãi. Trước khi sửa, phải xác minh **tài liệu API và chính sách tương thích của chính thư viện**.

### Ma trận quyết định

| Ngữ cảnh | Quyết định thường hợp lý |
| --- | --- |
| Public library đã cam kết serial form | Duy trì, thêm `@Serial` và kiểm thử file cũ |
| Dữ liệu `.ser` cần chuyển sang format mới | Xây công cụ migration an toàn, có backup và thời hạn hỗ trợ |
| API mới truyền dữ liệu qua mạng | Ưu tiên format có schema và cơ chế kiểm tra payload rõ ràng |
| Nhận bytes không tin cậy từ Internet | **Tránh giải tuần tự hóa Java native**; annotation không làm đầu vào an toàn |
| Giá trị tạm chỉ sống trong một process | Cân nhắc có thực sự cần serialized form không |
| Thư viện dựa vào serializer khác (JSON/CBOR/Protobuf) | `@Serial` không thay thế annotation hay schema của serializer đó |

**Không nhầm `@Serial` với `@java.beans.Transient` hoặc `transient`:** `transient` kiểm soát một phần dữ liệu instance theo quy tắc default serialization; `@Serial` chỉ đánh dấu một **khai báo thuộc cơ chế serialization**.

## 3. `@Serial` được áp dụng ở đâu?

Theo Javadoc chính thức của Java SE hiện hành:

```java
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial { }
```

Đây là **sơ đồ cú pháp API**, không phải yêu cầu tự khai báo lại `@interface Serial`. Trong ứng dụng, hãy **import `java.io.Serial`** của JDK.

**`SOURCE` retention:** annotation chỉ cần tồn tại ở mã nguồn để compiler kiểm tra; nó không phải metadata runtime để framework tìm bằng reflection. Không có mã `@Serial` trong class file không làm serialization ngừng hoạt động.

Các vị trí có ý nghĩa đối với class `Serializable`:

| Khai báo | Chữ ký/quy tắc quan trọng | Dùng khi nào |
| --- | --- | --- |
| `serialVersionUID` | `private static final long` | Xác định version của serialized form |
| `serialPersistentFields` | `private static final ObjectStreamField[]` | Điều khiển danh sách field của serial form nếu thực sự cần |
| `writeObject` | `private void writeObject(ObjectOutputStream) throws IOException` | Tùy biến việc ghi (thường gọi `defaultWriteObject`) |
| `readObject` | `private void readObject(ObjectInputStream) throws IOException, ClassNotFoundException` | Tùy biến việc đọc, validate và khôi phục invariant |
| `readObjectNoData` | `private void readObjectNoData() throws ObjectStreamException` | Tình huống đặc biệt trong tiến hóa class hierarchy |
| `writeReplace` | `Object writeReplace() throws ObjectStreamException`, access modifier tùy ý | Thay object bằng serial proxy/đối tượng đại diện trước khi ghi |
| `readResolve` | `Object readResolve() throws ObjectStreamException`, access modifier tùy ý | Thay object sau khi đọc, ví dụ khôi phục canonical instance |

Các ngoại lệ `throws` trong bảng phản ánh chữ ký được đặc tả; Java có thể cho phép khai báo **tập con** của checked exceptions phù hợp. Tên, kiểu trả về, quyền truy cập, số/thứ tự tham số và context lớp **phải đúng** để runtime Java serialization công nhận hook.

Mẫu khai báo thường thấy:

```java
import java.io.Serial;
import java.io.Serializable;

final class UserSettings implements Serializable {
    @Serial
    private static final long serialVersionUID = 12L;

    private String theme;
    private transient String accessToken;
}
```

Đây là **định nghĩa lớp minh họa**, không phải chương trình có `main`. Hai điểm quan trọng: `serialVersionUID` không bị ghi như instance field; `accessToken` là `transient` nên bị bỏ qua bởi **default serialization**.

### Đánh dấu không đồng nghĩa thực hiện

Ví dụ annotation này **không làm cho một phương thức tùy ý trở thành serialization hook**:

```java
@Serial
private void readObject(String value) {
    // Sai chữ ký; serialization không gọi phương thức này.
}
```

`@Serial` không sửa chữ ký. Khi bật `-Xlint:serial`, compiler có thể cảnh báo cấu trúc sai (đã kiểm chứng bằng `javac --release 17` trên JDK hiện đại):

```text
warning: [serial] sole parameter of serialization-related method readObject must have type ObjectInputStream to be effective rather than type String
```

**Không nhất thiết phát sinh lỗi biên dịch mặc định:** Javadoc nói compiler **được khuyến khích** kiểm tra và cảnh báo, không bảo đảm tất cả compiler/JDK đều áp đặt cùng chính sách. `-Xlint:serial` hỗ trợ phát hiện trong `javac`; khi cần chặn warning ở CI, có thể thêm `-Werror` sau khi đã dọn các cảnh báo thực sự liên quan.

## 4. Hợp đồng serialization gồm những gì?

Với **default Java serialization**, serialized form thường gồm các **instance fields không phải `static` và không phải `transient`**, cùng metadata kiểu dữ liệu và định danh lớp theo Java Object Serialization Specification.

`serialVersionUID` giúp cơ chế deserialization kiểm tra version của kiểu tương ứng. Nếu không khai báo trường này, JVM có thể **tính UID mặc định dựa trên đặc điểm của class**. Khi thư viện phát hành cho người khác, UID tính tự động có thể thay đổi do những sửa đổi mã không nhằm thay đổi serial form, gây `InvalidClassException` khi đọc dữ liệu cũ.

Nên chủ động khai báo:

```java
@Serial
private static final long serialVersionUID = 7L;
```

**Đừng đổi `serialVersionUID` theo mỗi release Maven.** Khi thay đổi class mà serial form vẫn tương thích, việc giữ cùng UID cho phép các phiên bản trao đổi dữ liệu theo giới hạn của đặc tả.

Mặt khác, **giữ cùng UID cũng không đảm bảo mọi thay đổi đều tương thích**. Ví dụ đổi kiểu của cùng tên field, đổi `Serializable`/`Externalizable`, thay đổi các điều kiện deserialization, hoặc đổi class/hierarchy theo cách không tương thích có thể gây lỗi hoặc làm dữ liệu sai nghĩa.

### Một số dạng thay đổi

| Thay đổi ở bản mới | Khả năng tương thích | Việc cần kiểm chứng |
| --- | --- | --- |
| Thêm field instance tham chiếu | Thường có thể đọc stream cũ; giá trị field mới là `null` | Tạo mặc định/migration phù hợp |
| Thêm field nguyên thủy | Thường có giá trị mặc định, ví dụ `0` hoặc `false` | Đừng nhầm với dữ liệu nghiệp vụ hợp lệ |
| Bỏ field cũ | Bản mới thường bỏ qua dữ liệu field không còn thuộc serial form | Mất thông tin có chấp nhận được không? |
| Đổi tên field | Tương đương mất tên cũ, thêm tên mới trong nhiều trường hợp | Migration rõ ràng |
| Đổi kiểu của field cùng tên | Có thể không tương thích, gây lỗi khi đọc | Phân tích stream và thử bằng file v1 thực tế |
| Thay đổi phương thức thường | Không nhất thiết ảnh hưởng serialized form khi UID cố định | Hành vi sau restore có còn đúng? |
| Thêm `transient` vào field từng được ghi | Thay serial form, dữ liệu cũ không tự gán như trước | Có cần migrate không? |
| Đổi `serialVersionUID` | Stream cũ có thể bị từ chối với `InvalidClassException` | Chỉ làm khi cố ý phá tương thích |
| Thêm custom `readObject` | Có thể dùng để xử lý dữ liệu cũ nhưng cũng có rủi ro lỗi runtime | Dùng `defaultReadObject` phù hợp và test migration |
| Thay tên package/class | Thường phá binary serialized-name lookup | Cần adapter/migration chiến lược riêng |

**Bài học:** version compatibility của Java serialization là **hợp đồng dữ liệu**, không chỉ là kết quả build thành công. Cần có golden fixtures (tệp serialization được tạo từ bản đã phát hành) và chạy lại với các phiên bản mới.

## 5. Bảo toàn invariant và dữ liệu nhạy cảm

Với class `Serializable`, quá trình giải tuần tự hóa **không hoạt động như cách gọi constructor thông thường** của chính class ấy. Các setter hoặc validate trong constructor của một lớp Serializable **không được tự động chạy lại** khi `ObjectInputStream` phục hồi instance.

Bởi vậy, với thư viện quản lý trạng thái có invariant, chỉ viết:

```java
public Session(String userId) {
    if (userId == null) throw new IllegalArgumentException();
}
```

là **chưa đủ** để bảo vệ đường đi deserialization. Phải thiết kế kiểm tra trạng thái khi object được phục hồi, thường trong `readObject` với `InvalidObjectException`, hoặc dùng **serialization proxy** có chủ đích nếu kiến trúc phù hợp.

### Tùy biến an toàn hơn với `readObject`

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (userId == null || userId.isBlank()) {
        throw new InvalidObjectException("Invalid userId");
    }
}
```

Đây là **một hook minh họa trong class Serializable**, phải có field `userId` và import các API `java.io` liên quan. `defaultReadObject()` phục hồi các field theo cơ chế mặc định, rồi ta kiểm tra invariant.

**Điều quan trọng:** `readObject` không phải nơi để tin toàn bộ object graph đã an toàn chỉ vì lớp ngoài có dữ liệu hợp lệ. Những object lồng nhau cũng cần kiểm soát, và deserialization dữ liệu không tin cậy vẫn là nguy cơ bảo mật nghiêm trọng.

### Trường nhạy cảm: `transient` không phải mã hóa

```java
private transient String accessToken;
```

Giúp loại trường này khỏi **default serial form**. Tuy nhiên:
- Custom `writeObject`, `writeReplace` hoặc một object khác có thể chủ động đưa thông tin nhạy cảm vào stream nếu viết sai.
- Trường `transient` sẽ **không tự khôi phục** sau khi đọc. Ứng dụng phải thiết kế cách tạo lại state an toàn.
- `transient` **không mã hóa** byte stream, không bảo vệ file `.ser` đã lưu.
- Nên tránh để secret trong object đã công khai serialized form nếu có thể, và kiểm thử thực tế những gì được lưu.

Các giá trị `transient` mất đi sau restore là **hành vi được thiết kế**, không phải lỗi tương thích.

## 6. Ví dụ Java 17+ hoàn chỉnh: giữ hợp đồng, đánh dấu `@Serial` và đọc lại an toàn hơn

Ví dụ sau dùng một class nội bộ `LibraryState` (đại diện cho kiểu của thư viện) với:

- `serialVersionUID = 7L` cố định.
- Hai field bền vững: `userId` và `retryCount`.
- Một field `transient`: `accessToken` không được mặc định ghi.
- Hai serialization hooks `writeObject`/`readObject` được đánh dấu `@Serial`.
- Xác thực invariant trong `readObject`.
- `ObjectInputFilter` giới hạn class và độ phức tạp của object graph trong **bài kiểm thử với dữ liệu do chính chương trình tạo**.

Lưu toàn bộ vào **`SerializableContractDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InvalidObjectException;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.ObjectStreamClass;
import java.io.ObjectStreamField;
import java.io.Serial;
import java.io.Serializable;
import java.util.Arrays;
import java.util.stream.Collectors;

public class SerializableContractDemo {
    static final class LibraryState implements Serializable {
        @Serial
        private static final long serialVersionUID = 7L;

        private String userId;
        private int retryCount;
        private transient String accessToken;

        LibraryState(String userId, int retryCount, String accessToken) {
            if (userId == null || userId.isBlank() || retryCount < 0) {
                throw new IllegalArgumentException("Invalid state");
            }
            this.userId = userId;
            this.retryCount = retryCount;
            this.accessToken = accessToken;
        }

        @Serial
        private void writeObject(ObjectOutputStream out) throws IOException {
            out.defaultWriteObject();
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            if (userId == null || userId.isBlank() || retryCount < 0) {
                throw new InvalidObjectException("Invalid serialized state");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        LibraryState original = new LibraryState("alice", 3, "never-persist");
        byte[] encoded;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(original);
            out.flush();
            encoded = bytes.toByteArray();
        }

        LibraryState copy;
        try (ObjectInputStream in =
                     new ObjectInputStream(new ByteArrayInputStream(encoded))) {
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                    "maxdepth=8;maxrefs=32;maxbytes=4096;" +
                    "SerializableContractDemo$LibraryState;java.base/*;!*"));
            copy = (LibraryState) in.readObject();
        }

        ObjectStreamClass descriptor = ObjectStreamClass.lookup(LibraryState.class);
        String fields = Arrays.stream(descriptor.getFields())
                .map(ObjectStreamField::getName)
                .sorted()
                .collect(Collectors.joining(","));

        System.out.println("userId=" + copy.userId);
        System.out.println("retryCount=" + copy.retryCount);
        System.out.println("tokenRestored=" + (copy.accessToken != null));
        System.out.println("serialVersionUID=" + descriptor.getSerialVersionUID());
        System.out.println("serialFields=" + fields);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 -Xlint:serial SerializableContractDemo.java
java SerializableContractDemo
```

**Stdout đã kiểm chứng trên OpenJDK (mã biên dịch với `--release 17`):**

```text
userId=alice
retryCount=3
tokenRestored=false
serialVersionUID=7
serialFields=retryCount,userId
```

### Giải thích kết quả

1. `userId=alice` và `retryCount=3`: hai field được phục hồi từ stream, và `readObject` chấp nhận invariant.
2. `tokenRestored=false`: `accessToken` là `transient`, không nằm trong default serial form.
3. `serialVersionUID=7`: `ObjectStreamClass` xác nhận UID thực tế là giá trị đã khai báo, không phải phiên bản JDK hoặc bản build.
4. `serialFields=retryCount,userId`: chỉ những field được serial hóa hiển thị trong mô tả serial form; danh sách được sort trong code để stdout không lệ thuộc thứ tự duyệt descriptor.
5. `ObjectInputFilter` hạn chế graph trong kịch bản demo nhưng **không biến Java deserialization thành an toàn cho mọi nguồn không tin cậy**.

**Lưu ý:** `LibraryState` là static nested class nên tên binary có dạng `SerializableContractDemo$LibraryState`; bộ lọc cần đúng tên ấy. Trong thư viện thực, đổi tên class/package/nested class có thể thay cả định danh dùng cho deserialization và ảnh hưởng tính tương thích của dữ liệu cũ.

### Vì sao vẫn viết `writeObject` chỉ để gọi `defaultWriteObject`?

Bài học dùng hook này để minh họa cách đánh dấu `@Serial` và quản lý hợp đồng. Nếu class **không cần** tùy biến ghi, **không cần viết phương thức `writeObject` chỉ cho đủ**: default serialization tự xử lý các field hợp lệ. Nên giữ API đơn giản khi có thể.

Với `readObject` thì ví dụ có lý do rõ ràng: cần **kiểm tra lại invariant** sau khi dữ liệu được phục hồi. Các class bất biến nhạy cảm có thể cần pattern khác như serialization proxy; đó là một quyết định thiết kế riêng.

## 7. Kiểm thử tương thích thật: bản v1 ghi file, bản v2 đọc file

Đây là ca đặc biệt quan trọng cho thư viện đã có hợp đồng serialized form. Chạy round-trip bằng **một phiên bản duy nhất** chưa đủ: mã v2 có thể ghi và đọc chính file của v2 nhưng **không đọc được file do v1 đã phát hành**.

Ví dụ này tạo **hai phiên bản cùng binary class name `example.compat.Preferences`** trong **hai thư mục classpath riêng**. Bản v1 chỉ có field `theme`. Bản v2 thêm `locale` nhưng giữ `serialVersionUID = 4L`. Khi đọc file cũ, field mới có giá trị `null` và v2 đặt một giá trị mặc định trong `readObject`.

### 7.1. Cấu trúc

```text
project/
├── v1/example/compat/
│   ├── Preferences.java
│   └── Writer.java
├── v2/example/compat/
│   ├── Preferences.java
│   └── Reader.java
└── build/
    ├── v1/
    └── v2/
```

**Không biên dịch hai định nghĩa `example.compat.Preferences` vào cùng thư mục đầu ra hoặc cùng classpath.** Mục tiêu là tái hiện đúng hai bản thư viện theo thời gian.

### 7.2. `v1/example/compat/Preferences.java`

```java
package example.compat;

import java.io.Serial;
import java.io.Serializable;

public final class Preferences implements Serializable {
    @Serial
    private static final long serialVersionUID = 4L;

    private String theme;

    public Preferences(String theme) {
        this.theme = theme;
    }

    public String display() {
        return theme;
    }
}
```

### 7.3. `v1/example/compat/Writer.java`

```java
package example.compat;

import java.io.FileOutputStream;
import java.io.ObjectOutputStream;

public final class Writer {
    public static void main(String[] args) throws Exception {
        try (ObjectOutputStream out = new ObjectOutputStream(
                new FileOutputStream(args[0]))) {
            out.writeObject(new Preferences("dark"));
        }
        System.out.println("v1Written=dark");
    }
}
```

Writer ghi dữ liệu v1 ra đường dẫn truyền trong `args[0]`. Ví dụ thực hành dùng `prefs.ser` trong thư mục test; **không chạy trên một file production có sẵn**.

### 7.4. `v2/example/compat/Preferences.java`

```java
package example.compat;

import java.io.InvalidObjectException;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.Serial;
import java.io.Serializable;

public final class Preferences implements Serializable {
    @Serial
    private static final long serialVersionUID = 4L;

    private String theme;
    private String locale;

    @Serial
    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();
        if (theme == null || theme.isBlank()) {
            throw new InvalidObjectException("Missing theme");
        }
        if (locale == null) {
            locale = "vi-VN";
        }
    }

    public String display() {
        return theme + "," + locale;
    }
}
```

**Điểm mấu chốt:** v2 **giữ UID 4L** và cùng binary class name. File v1 không chứa field `locale` nên khi `defaultReadObject()` khôi phục theo schema v2, `locale` là `null`. Hook `readObject` đặt fallback `vi-VN`; nó không cần đổi tên field `theme`.

Không nên đổi UID sang `5L` chỉ vì đã phát hành version 2 của thư viện, vì làm vậy có thể khiến quá trình đọc file v1 thất bại trước khi migration diễn ra.

### 7.5. `v2/example/compat/Reader.java`

```java
package example.compat;

import java.io.FileInputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

public final class Reader {
    public static void main(String[] args) throws Exception {
        try (ObjectInputStream in = new ObjectInputStream(
                new FileInputStream(args[0]))) {
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                    "maxdepth=8;maxrefs=30;maxbytes=4096;" +
                    "example.compat.Preferences;java.base/*;!*"));
            Preferences p = (Preferences) in.readObject();
            System.out.println("v2Read=" + p.display());
        }
    }
}
```

Bộ lọc ở Reader được cấu hình cho demo với dữ liệu tin cậy, hạn chế lớp/giới hạn tài nguyên. Nếu hệ thống thực cần đọc graph phức tạp hơn, phải **thiết kế filter theo kiểu dữ liệu thực tế** và xem xét phạm vi/phương thức hợp nhất với filter chung của ứng dụng.

### 7.6. Lệnh thử nghiệm cross-version

Trên Bash/Linux/macOS ở thư mục `project`:

```bash
mkdir -p build/v1 build/v2

javac --release 17 -Xlint:serial -d build/v1 v1/example/compat/Preferences.java v1/example/compat/Writer.java
javac --release 17 -Xlint:serial -d build/v2 v2/example/compat/Preferences.java v2/example/compat/Reader.java

java -cp build/v1 example.compat.Writer prefs.ser
java -cp build/v2 example.compat.Reader prefs.ser
```

Trên Windows PowerShell, tạo thư mục bằng:

```powershell
New-Item -ItemType Directory -Force build\v1,build\v2 | Out-Null
```

Sau đó dùng cùng hai lệnh `javac` và hai lệnh `java`, với đường dẫn `/` được JDK chấp nhận trên Windows.

**Stdout đã kiểm chứng (từng phiên bản được biên dịch riêng và chạy với `--release 17`):**

```text
v1Written=dark
v2Read=dark,vi-VN
```

Kết quả chứng minh **một ca cụ thể** của việc tiến hóa serialized form: **thêm field tham chiếu tùy chọn và giữ UID/binary class name**, kết hợp chính sách mặc định trong `readObject`.

**Điều chưa được chứng minh bởi ca này:** mọi thay đổi khác trong tương lai đều compatible, bản v1 đọc được mọi file do v2 tạo ra, hay các dữ liệu ác ý có thể được giải tuần tự hóa an toàn. CI nên bổ sung test cả chiều v1→v2, v2→v1 **nếu sản phẩm cam kết cả hai chiều**, cùng các file mẫu từ những bản phát hành thực tế.

## 8. Chính sách nâng cấp thư viện: bảo toàn serial form

Với thư viện thực, nên thiết lập một quy trình thay đổi có kiểm soát.

### 8.1. Trước khi sửa class

1. Xác nhận class có phải **public contract** `Serializable` không, ai đang lưu/đọc object đó.
2. Lưu bản `.ser` đã tạo từ bản phát hành cũ trong kho test bảo mật (không đưa dữ liệu khách hàng lên kho mã).
3. Ghi lại `serialVersionUID`, tên package/class và danh sách field sẽ được serial hóa.
4. Xác định field `transient`, state lấy lại được từ bên ngoài và invariant cần validate.
5. Phân loại thay đổi: additive compatible, đổi schema cần migration, hay phá tương thích có chủ đích.
6. Ghi rõ chính sách phiên bản nào được phép đọc từ phiên bản nào.

### 8.2. Khi thay đổi code

- Giữ `@Serial private static final long serialVersionUID` với giá trị ổn định nếu vẫn duy trì serial form.
- Thêm `@Serial` cho hook thật sự cần thiết, không tạo các hook rỗng để “đủ annotation”.
- Tránh tự động đổi tên field đã có trong dữ liệu cũ.
- Với field mới, định nghĩa **giá trị mặc định và ý nghĩa** khi stream cũ không có field ấy.
- Kiểm tra đối tượng restored giống như một đối tượng mới: không bỏ qua invariant, quyền và validation.
- Nếu dùng `serialPersistentFields`, hãy coi nó là **schema thủ công** cần test cẩn thận cùng `PutField`/`GetField`.
- Đừng chuyển `Serializable` sang `Externalizable` mà kỳ vọng giữ nguyên wire format.

### 8.3. Trong CI

```bash
javac --release 17 -Xlint:serial -Werror SerializableContractDemo.java
```

Đây là ví dụ kiểm soát warning khi build một source file; với Maven/Gradle, tích hợp các compiler flags tương ứng trong cấu hình build. Nếu project có warning từ những phần không liên quan, cần phân loại trước khi dùng `-Werror`, không tắt hết kiểm tra vì một warning không rõ.

Bên cạnh lint, kiểm tra:

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Biên dịch `-Xlint:serial` | Không có khai báo `@Serial` sai chữ ký |
| `ObjectStreamClass.lookup(type).getSerialVersionUID()` | UID đúng hợp đồng |
| Serialize và deserialize cùng bản | Dữ liệu logic/field phải bảo toàn |
| Deserializing golden file từ bản cũ | Không lỗi UID/schema; field mới có fallback hợp lệ |
| Thêm/bỏ/đổi field | Đúng theo quy tắc tiến hóa đã cho phép |
| Invariant/giá trị null/sai | Từ chối bằng `InvalidObjectException` hoặc cơ chế phù hợp |
| Dữ liệu nhạy cảm | Không bất ngờ lọt vào serialized fields |
| Filter allowlist và giới hạn graph | Từ chối các graph/type ngoài phạm vi |
| Dữ liệu hỏng/truncated | Thất bại được xử lý, không phá dữ liệu gốc |
| Version rollback nếu cam kết | Bản cũ đọc được file mới hoặc có phương án migration ngược |
| Tính đóng gói JPMS | Runtime có module cần thiết và không dựa vào `--add-opens` rộng |

**Có kiểm thử thực tế tốt hơn chỉ dựa vào lint.** `@Serial` có thể bắt lỗi khai báo sai, nhưng không phát hiện một đổi tên field cố ý hoặc sai chính sách compatibility của ứng dụng.

## 9. Bảo mật deserialization: `@Serial` không phải hàng rào an toàn

**Đây là điều bắt buộc trong thư viện hiện đại:** Java deserialization của bytes không tin cậy tiềm ẩn rủi ro thực thi hành vi không mong muốn, lạm dụng object graph và tiêu tốn tài nguyên. **Tránh giải tuần tự hóa dữ liệu không tin cậy** nếu có thể.

Khi hợp đồng cũ bắt buộc phải đọc dữ liệu đã lưu:

- Chỉ nhận stream từ nguồn được tin cậy và xác thực theo kiến trúc.
- Giới hạn kích thước input **trước khi** tạo `ObjectInputStream` nếu có thể.
- Dùng `ObjectInputFilter` phù hợp với **loại dữ liệu thực tế**, giới hạn depth, references, array length và bytes.
- Áp dụng allowlist chặt chẽ, không giả định `UNDECIDED` đồng nghĩa đã được cho phép. Một pattern `!*` hoặc quy tắc reject undecided class giúp giảm mặt tấn công khi được thiết kế đúng.
- Validate dữ liệu đã deserialize, nhất là invariant, dữ liệu bên ngoài và object lồng nhau.
- Cập nhật JDK, thư viện phụ thuộc và kiểm soát ai được phát hành serialized data.
- Không coi filter là thay thế việc không xử lý dữ liệu không tin cậy; filter cũng có giới hạn (ví dụ không phải mọi dữ liệu primitive/String đều được kiểm tra như class object độc lập).

Ví dụ một filter cấu hình cho **kiểu demo**:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=8;maxrefs=32;maxbytes=4096;" +
        "SerializableContractDemo$LibraryState;java.base/*;!*");
in.setObjectInputFilter(filter);
```

Đây là **mã minh họa**, giả định `in` là `ObjectInputStream` và đã import `ObjectInputFilter`. Pattern này hợp với demo `LibraryState` nhưng **không phải bộ lọc dùng được cho mọi thư viện**; graph dữ liệu thật có thể gồm nhiều class phụ thuộc cần được xem xét từng trường hợp.

### `@Serial` KHÔNG làm các việc sau

- Không tự triển khai `Serializable`.
- Không thay `serialVersionUID` nếu bạn chưa khai báo nó.
- Không tự động validate invariant khi `readObject` không có.
- Không bảo đảm default serial form tương thích qua mọi release.
- Không ngăn gadget chain/deserialization vulnerability.
- Không mã hóa byte stream, không kiểm soát quyền file.
- Không đồng nghĩa Javadoc tag `@serial`: Javadoc `@serial`/`@serialField` là thẻ tài liệu khác; `@Serial` là **Java annotation** của `java.io`.

**Nếu chỉ cần lưu dữ liệu cấu hình:** một định dạng văn bản/binary có schema rõ ràng và validation chủ động thường dễ audit và nâng cấp hơn. Giữ Java native serialization nên là quyết định có lý do, không phải mặc định.

## 10. Các trường hợp đặc biệt: `Externalizable`, enum và record

### 10.1. `Externalizable`

`Externalizable` kế thừa `Serializable` nhưng dựa trên hợp đồng `writeExternal(ObjectOutput)` và `readExternal(ObjectInput)`, cùng yêu cầu khởi tạo object khác biệt. Vì vậy:

- `@Serial` trên `serialVersionUID` vẫn có thể có ý nghĩa.
- `@Serial` **không dùng** để đánh dấu `writeExternal` hoặc `readExternal`: chúng **không thuộc năm serialization hooks** mà annotation `@Serial` quy định.
- `writeObject`, `readObject`, `readObjectNoData` và `serialPersistentFields` không phải cơ chế được dùng cho `Externalizable` theo cách của `Serializable` thông thường; đánh dấu chúng bằng `@Serial` trong context ấy là **sai về mặt ngữ nghĩa**.

Nếu thư viện hiện đang dùng `Externalizable`, cần duy trì đúng hợp đồng external form hoặc có kế hoạch migration riêng. Đừng chuyển tùy tiện sang default `Serializable` rồi giữ nguyên UID để hy vọng compatible.

### 10.2. `enum`

Enum đã có cơ chế serialization đặc thù của Java, trong đó giá trị UID được định nghĩa theo quy tắc riêng (`0L`). Những hook thông thường và field `serialVersionUID` tự khai báo không có cùng hiệu lực như ở class `Serializable` bình thường. **Không thêm `@Serial` vào hook hoặc UID không có tác dụng trong enum** chỉ vì áp dụng một template máy móc.

### 10.3. `record`

Record có thể implement `Serializable`, nhưng Java serialization cho record có quy tắc riêng: sử dụng record components/canonical constructor và **bỏ qua các hook tùy biến như `readObject`/`writeObject`/`readObjectNoData`, cùng `serialPersistentFields`**. `writeReplace` và `readResolve` có quy tắc hỗ trợ riêng. UID mặc định của record là `0L` nếu không khai báo tường minh; quy tắc matching UID cũng khác class thường.

Vì vậy, **đừng bê nguyên `readObject` từ class Serializable truyền thống sang record** để mong kiểm soát deserialization: hook ấy không được gọi như bạn tưởng. Nếu class thư viện hiện có serialized form truyền thống, đổi sang record là một quyết định tương thích riêng cần test rất kỹ.

**Chỉ áp dụng `@Serial` lên cơ chế thực sự có hiệu lực trong loại class tương ứng.**

## 11. Lỗi phổ biến khi bảo trì thư viện

| Lỗi | Hậu quả | Cách làm còn phù hợp hiện nay |
| --- | --- | --- |
| Bỏ `serialVersionUID` để JVM tự tính | Sửa class có thể gây UID khác và `InvalidClassException` | Khai báo `@Serial private static final long serialVersionUID` có chủ đích |
| Tăng UID theo từng release | Phá khả năng đọc stream cũ không cần thiết | Chỉ đổi UID theo chiến lược incompatible change |
| Nghĩ `@Serial` tự bảo đảm tương thích | Annotation chỉ hỗ trợ kiểm tra khai báo | Golden-file test và migration policy |
| Gắn `@Serial` lên phương thức bất kỳ | Hook không được runtime nhận; compiler có thể cảnh báo | Chỉ dùng các khai báo được Javadoc liệt kê |
| Viết `readObject(String)` | Sai chữ ký, validation không chạy | `readObject(ObjectInputStream)` đúng quy định |
| Dựa hoàn toàn vào constructor để validate restored object | Constructor của serializable class không được chạy như tạo mới | Validate trong cơ chế restore hợp lệ |
| Thêm field mới mà không xử lý stream cũ | Nhận `null`/`0` sai nghĩa nghiệp vụ | Chọn fallback, kiểm tra schema |
| Rename field đã lưu | Dữ liệu cũ có thể không còn ánh xạ như mong đợi | Chính sách migration rõ |
| Đưa token vào field thường | Secret có thể xuất hiện trong stream | Loại dữ liệu nhạy cảm, dùng `transient` hoặc proxy an toàn |
| Dùng `transient` rồi mong field tự khôi phục | Bị bỏ khỏi default form | Tái khởi tạo sau restore khi cần |
| Coi `ObjectInputFilter` là phương án bảo đảm 100% an toàn | Không loại bỏ mọi rủi ro deserialization | Tránh untrusted stream và thiết kế phòng thủ nhiều lớp |
| Mở serialized data do khách hàng upload trực tiếp | Có nguy cơ bị tấn công hoặc DoS | Không dùng native Java deserialization cho nguồn không tin cậy |
| Gọi `readObject` custom nhưng quên `defaultReadObject` khi cần | Field không được phục hồi theo default form | Đọc dữ liệu theo hợp đồng đã định |
| Dùng `@Serial` trên `writeExternal` | Không phải hook được annotation quy định | Phân biệt `Serializable` và `Externalizable` |
| Dùng `@Serial` trên hook enum/record bị bỏ qua | Tưởng code được gọi dù runtime bỏ qua | Hiểu serialization đặc thù enum/record |
| Chỉ test round-trip một bản | Có thể không đọc được dữ liệu lịch sử | Cross-version compatibility tests |
| Bỏ qua binary class name | Đổi package/class có thể làm stream không load được | Duy trì tên hoặc xây migration |
| Dùng `-Xlint:serial` nhưng không xử lý cảnh báo | Sai hook âm thầm bị bỏ qua | Triaging warning và dùng CI gate phù hợp |

## 12. Câu hỏi tự luyện có đáp án

**Câu 1.** `@Serial` có ý nghĩa nhất trong trường hợp nào?  
**Đáp án:** Thư viện **đang duy trì** hợp đồng `Serializable`, cần compiler nhận biết các khai báo serialization đặc biệt và hỗ trợ bảo trì serial form.

**Câu 2.** `@Serial` có làm lớp không implement `Serializable` trở thành serializable không?  
**Đáp án:** Không. Annotation không thay thế marker interface hay logic serialization của JDK.

**Câu 3.** `serialVersionUID` có nên tăng cùng mọi bản phát hành thư viện không?  
**Đáp án:** Không. Giữ ổn định khi serial form vẫn compatible; UID không phải số release.

**Câu 4.** Vì sao thêm field `locale` mà file v1 vẫn đọc được ở v2 trong ví dụ?  
**Đáp án:** Cùng binary class name và UID `4L`; field mới không có trong stream cũ nên mặc định `null`, sau đó `readObject` dùng fallback `vi-VN`.

**Câu 5.** `@Serial` có runtime retention không?  
**Đáp án:** Không. `@Retention(SOURCE)`: mục tiêu là hỗ trợ kiểm tra ở compile time.

**Câu 6.** Những phương thức nào được phép đặt `@Serial` cho class `Serializable` thông thường?  
**Đáp án:** `writeObject`, `readObject`, `readObjectNoData`, `writeReplace` và `readResolve`, với chữ ký phù hợp; ngoài ra có hai field đặc biệt là `serialVersionUID` và `serialPersistentFields`.

**Câu 7.** Vì sao cần validate trong `readObject`?  
**Đáp án:** Phục hồi object không chạy validation trong constructor của chính Serializable class như khi tạo mới; dữ liệu thiếu/sai có thể phá invariant.

**Câu 8.** Nếu muốn tránh ghi `accessToken` qua default serialization, làm sao?  
**Đáp án:** Dùng `transient` hoặc chủ động thiết kế serial form an toàn; đồng thời bảo đảm custom hooks không tự ghi secret.

**Câu 9.** Dữ liệu `.ser` từ Internet có an toàn chỉ vì lớp dùng `@Serial` và `ObjectInputFilter` không?  
**Đáp án:** Không. Tránh untrusted deserialization; filter giúp giảm rủi ro theo policy nhưng không phải bảo đảm tuyệt đối.

**Câu 10.** Vì sao `@Serial` không áp dụng cho `writeExternal`?  
**Đáp án:** `writeExternal` thuộc cơ chế `Externalizable`, không nằm trong danh sách hook của annotation `@Serial`.

**Câu 11.** Khi upgrade cần kiểm thử gì quan trọng nhất?  
**Đáp án:** Đọc **file serialized thật do bản cũ tạo**, xác minh UID, field dữ liệu, schema migration/invariant, filter/security và hợp đồng được hỗ trợ.

**Câu 12.** `@Serial` và Javadoc tag `@serial` khác nhau ở đâu?  
**Đáp án:** `@Serial` là Java annotation để đánh dấu khai báo; `@serial` là thẻ tài liệu mô tả serialized form.

## 13. Kết luận và tài liệu chính thức

**Nguyên tắc bảo trì:** Nếu thư viện **vẫn có hợp đồng `Serializable` cần duy trì**, dùng `@Serial` để làm rõ các khai báo serialization, giữ `serialVersionUID` đúng chính sách, kiểm tra invariant khi đọc, không tự ghi dữ liệu nhạy cảm, áp dụng chính sách filter phòng thủ và **thử đọc file từ phiên bản thư viện trước**.

Quy trình đề xuất là:

```text
Xác nhận hợp đồng Serializable hiện hữu
       ↓
Ghi lại serialVersionUID và serialized form
       ↓
Đánh dấu @Serial cho khai báo hợp lệ
       ↓
Lint + kiểm thử round-trip của bản mới
       ↓
Đọc golden files từ các bản cũ
       ↓
Kiểm thử schema migration, invariant, bảo mật
       ↓
Phát hành và giữ fixture để kiểm thử lâu dài
```

**Tài liệu chính thức (các API vẫn được hỗ trợ ở Java hiện hành):**

- [Oracle Java SE 25 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serial.html): `@Target`/`@Retention(SOURCE)`, danh sách field/method hợp lệ và những context vô hiệu.
- [Oracle Java SE 17 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html): API có từ Java 14 và dùng trên Java 17+.
- [Oracle Java SE 25 — `Serializable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serializable.html): cơ chế serialization hooks và hợp đồng kiểu.
- [Oracle Java SE 25 — Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/serial-arch.html): serial form, serializable fields và khả năng tiến hóa lớp.
- [Oracle Java SE 25 — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputFilter.html): lọc lớp và giới hạn tài nguyên lúc deserialize.
- [Oracle Java SE 25 — Serialization Filters](https://docs.oracle.com/en/java/javase/25/core/java-serialization-filters.html): hướng dẫn chọn filter và kết hợp chính sách.
- [Oracle — Secure Coding Guidelines for Java SE](https://www.oracle.com/java/technologies/javase/seccodeguide.html): bảo vệ invariant và dữ liệu nhạy cảm trước deserialization.
