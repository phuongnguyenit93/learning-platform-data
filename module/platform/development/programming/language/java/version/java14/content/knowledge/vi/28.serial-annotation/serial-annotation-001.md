# Vai trò kiểm tra khai báo của java.io.Serial trong Java 14 và Java hiện đại

## Mục tiêu

Khi một lớp Java sử dụng **Java Object Serialization**, cơ chế `ObjectOutputStream` và `ObjectInputStream` nhận diện một số **trường và phương thức đặc biệt theo tên, kiểu, quyền truy cập và chữ ký**. Ví dụ `serialVersionUID` phải mang kiểu `long`, còn `readObject` dùng để khôi phục đối tượng phải nhận tham số `ObjectInputStream` và có chữ ký phù hợp.

Những khai báo này rất dễ viết sai mà chương trình vẫn **biên dịch được**: một phương thức `readObject(String)` là một method Java hoàn toàn hợp lệ, nhưng không phải serialization hook được hệ thống tự gọi. Để diễn đạt rõ **ý định đây là thành viên của cơ chế serialization**, Java 14 bổ sung annotation **`java.io.Serial`**.

`@Serial` giúp compiler hoặc công cụ static analysis **nhận diện và kiểm tra các khai báo serialization có ý nghĩa**, tương tự tinh thần của `@Override`. Nhưng có một giới hạn quan trọng: **Javadoc chỉ khuyến khích compiler kiểm tra khai báo sai, không bảo đảm mọi trình biên dịch sẽ phát hiện mọi lỗi**. Bản thân annotation **không kích hoạt serialization, không sửa chữ ký method và không bảo vệ việc deserialize dữ liệu không tin cậy**.

Sau bài này, bạn có thể:

1. Xác định **chính xác hai trường và năm phương thức** mà Javadoc quy định có thể gắn `@Serial`.
2. Hiểu `@Target({METHOD,FIELD})`, `@Retention(SOURCE)` và hệ quả đối với compiler, bytecode và runtime.
3. Phân biệt **kiểm tra ở lúc biên dịch** với **cách Java Object Serialization thực sự nhận diện hook khi chạy**.
4. Dùng `@Serial` cho `serialVersionUID` và custom `writeObject`/`readObject` đúng cách.
5. Phát hiện các lỗi thường gặp: sai tên/kiểu/tham số, sai `private`, dùng trong lớp không `Serializable` hoặc loại có đặc tả serialization riêng.
6. Biên dịch với `javac -Xlint:serial`, biết ý nghĩa của `-Werror` và **không nhầm warning với lỗi compile tự động**.
7. Chạy một ví dụ Java 17+ tự serialize/deserialize đối tượng tin cậy, in `serialVersionUID` và xác minh round-trip.
8. Áp dụng các lưu ý hiện hành về object graph, tương thích schema và bảo mật khi có nhu cầu serialization thực sự.

**Phiên bản:** `java.io.Serial` có từ **Java 14** (`Since: 14`), nằm trong module `java.base` và **vẫn có trong JDK 17, 25, 26**. Bài dùng **JDK 17+** với API chính thức, không dùng preview, thư viện ngoài hoặc cơ chế truy cập nội bộ JDK. Chỉ nêu những kiến thức serialization **vẫn có hiệu lực hiện nay**; không khuyến nghị Java native serialization làm định dạng mới cho mọi dữ liệu.

## 1. Vì sao cần kiểm tra một khai báo serialization?

Một lớp có thể tham gia cơ chế Java Object Serialization bằng cách thực hiện:

~~~java
import java.io.Serializable;

// Đoạn minh họa, không phải chương trình độc lập.
final class OrderSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;
    private final String id;

    OrderSnapshot(String id) {
        this.id = id;
    }
}
~~~

`Serializable` là **marker interface**: nó không khai báo phương thức cần override, nhưng chỉ rằng lớp được phép tham gia cơ chế serialization (với các điều kiện về object graph và runtime).

Khi ghi một object qua `ObjectOutputStream.writeObject(...)`, cơ chế có thể lưu trạng thái của lớp vào luồng nhị phân; khi đọc qua `ObjectInputStream.readObject()`, nó khôi phục object theo các quy tắc của Java Object Serialization Specification.

Các thành phần đặc biệt như `serialVersionUID` và `readObject` không hoạt động vì bạn đã override một method trong `Serializable`. **Serializable không hề định nghĩa method `readObject` hoặc `writeObject`** để override. Thay vào đó, serialization runtime tìm members theo **quy ước bắt buộc về tên/chữ ký/kiểu/visibility**.

Điều đó tạo ra rủi ro:

~~~java
// Đoạn minh họa cố ý sai; đặt trong một class implements Serializable.
private void readObject(String text) {
    // Method bình thường, không phải deserialization hook.
}
~~~

Code Java trên hợp lệ, nhưng serialization runtime **không xem đó là special `readObject(ObjectInputStream)`**. Nếu người viết tưởng method này tự được gọi để kiểm tra dữ liệu sau deserialization, một invariant có thể không được kiểm tra như dự kiến.

**Vai trò `@Serial`:** ghi dấu vào source code rằng field/method **phải là một thành viên serialization được runtime nhận diện** để compiler, IDE hoặc static analyzer có thể kiểm tra và cảnh báo một số lỗi khó nhận ra.

## 2. Bản chất annotation @Serial

Định nghĩa API có cấu trúc:

~~~java
// Mô tả annotation; không phải file cần tự tạo.
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial {}
~~~

Các giá trị này đến từ chính `java.io.Serial` và Javadoc.

| Thuộc tính | Nghĩa | Tác động thực tế |
|---|---|---|
| `java.io.Serial` | Annotation trong `java.base` | Có thể import từ Java 14+ |
| `@Target({METHOD,FIELD})` | Chỉ gắn trực tiếp vào **method** hoặc **field** | Gắn lên class hoặc constructor là sai target, compiler từ chối |
| `@Retention(SOURCE)` | Annotation tồn tại ở **mã nguồn** | Không được giữ thành runtime annotation để `getAnnotation(Serial.class)` tìm thấy |
| Không có annotation elements | Viết đơn giản `@Serial` | Không có tham số cấu hình serialization |
| `Since: 14` | Bổ sung ở Java 14 | Biên dịch với `--release 17` mà không cần preview flags |

`@Serial` **không phải switch bật serialization**. `implements Serializable` và các luật serialization hiện hành quyết định runtime có thể serialize class. Thêm/bỏ annotation (không sửa chữ ký field/method) **không làm thay đổi cách các member được runtime gọi**.

### 2.1. So với @Override

| `@Override` | `@Serial` |
|---|---|
| Đánh dấu một method phải thật sự override/implement method phù hợp của supertype | Đánh dấu member phải thuộc các hook/field đặc biệt của serialization |
| Kiểm tra override thuộc các luật compile-time của Java | Javadoc **khuyến khích compiler** kiểm tra khai báo serialization; mức phát hiện phụ thuộc toolchain |
| Không override đúng thường gây compile error | `@Serial` đặt sai **target** có thể gây compile error; đặt sai **ngữ nghĩa** có thể chỉ warning hoặc không báo |
| Không bật cơ chế runtime mới | Cũng **không** kích hoạt serialization hoặc tạo hook |

Thêm `@Override` vào `readObject(ObjectInputStream)` là sai vì không có method cùng chữ ký trong `Serializable` để override. `@Serial` mới là annotation đúng cho ý định đánh dấu serialization hook.

### 2.2. Retention SOURCE và runtime

`@Serial` **không phải metadata dùng để runtime tìm serialization hooks bằng reflection**. Serialization vẫn nhận diện hooks theo quy tắc quy định, ngay cả khi source không gắn annotation.

Hệ quả:

- Compiler/IDE/static analyzer có thể dùng annotation để hiểu ý định.
- Không viết code runtime kiểu “có `@Serial` thì field này sẽ được serialize”.
- Không dùng `@Serial` thay cho định dạng dữ liệu, schema versioning hoặc xác thực.
- Annotation không được giữ ở runtime để một consumer khác truy vấn bằng reflection.

## 3. Chính xác hai field được đánh dấu

Javadoc `java.io.Serial` liệt kê **hai field** liên quan serialization:

| Tên và chữ ký | Vai trò |
|---|---|
| `private static final long serialVersionUID` | UID dùng trong cơ chế kiểm tra tương thích class khi deserialize |
| `private static final ObjectStreamField[] serialPersistentFields` | Danh sách trường của **serialized form tùy chỉnh**, dùng khi cần thiết kế định dạng lưu cụ thể |

### 3.1. serialVersionUID

~~~java
import java.io.Serial;
import java.io.Serializable;

// Đoạn khai báo trong class.
final class SimpleState implements Serializable {
    @Serial
    private static final long serialVersionUID = 42L;

    private int value;
}
~~~

Đây là kiểu viết thông dụng khi một **class bình thường** implements `Serializable` và cần UID nhất quán.

- Runtime liên kết một UID với serializable class.
- Khi đọc, UID không tương thích có thể gây `InvalidClassException`.
- Nếu không khai báo UID hợp lệ, runtime có thể tính UID mặc định từ chi tiết class; thay đổi cấu trúc/code có thể làm giá trị mặc định khác đi.
- UID ổn định giúp quản lý version compatibility, **nhưng UID giống nhau không bảo đảm mọi field layout, kiểu dữ liệu hoặc invariant đều tương thích**.

**Sai kiểu:**

~~~java
// CỐ Ý SAI trong class implements Serializable:
@Serial
private static final int serialVersionUID = 42;
~~~

UID yêu cầu primitive **`long`**, không phải `int`. Trong một lần thử JDK 24 với `--release 17 -Xlint:serial`, compiler đã cảnh báo `serialVersionUID must be of type long`. **Không mặc định đây luôn là compile error**: thiếu `-Werror`, lần thử vẫn trả exit code 0.

Không đặt `serialVersionUID` thành instance field hoặc đổi tên rồi nghĩ annotation sửa nó. `@Serial` **không chuyển int thành long**, không tự đổi visibility và không tạo UID.

**Visibility:** Javadoc `@Serial` mô tả `private static final long serialVersionUID` là hình dạng nên dùng. `Serializable` contract cho phép UID runtime mang access modifier khác nếu vẫn đúng `static final long` nhưng **khuyến nghị private** vì UID không phải member có ích để kế thừa. Trong ứng dụng thông thường, hãy viết **private static final long**.

### 3.2. serialPersistentFields

~~~java
import java.io.ObjectStreamField;
import java.io.Serial;
import java.io.Serializable;

// Đoạn minh họa khai báo field; chưa phải custom serialization đầy đủ.
final class PersistedState implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    @Serial
    private static final ObjectStreamField[] serialPersistentFields = {
        new ObjectStreamField("code", String.class),
        new ObjectStreamField("count", int.class)
    };

    private String code;
    private int count;
}
~~~

`serialPersistentFields` phải có **đúng tên, kiểu `ObjectStreamField[]`, `private static final`**. Field này xác định những trường của serialized form. Đây là **cơ chế nâng cao**, không phải thành phần bắt buộc của mọi `Serializable` class.

Nếu dùng serialized form tùy chỉnh, phải xem lại cách runtime ghi/đọc dữ liệu, duy trì compatibility và test phiên bản cũ. Với object đơn giản, thường không cần khai báo `serialPersistentFields`.

**Không nhầm:** `@Serial` là **annotation Java**; `@serial` trong **Javadoc comment** là tag tài liệu về serialized form. Hai thứ khác cú pháp lẫn chức năng.

## 4. Chính xác năm method có thể gắn @Serial

Javadoc xác định **năm special methods**. Tên, tham số, kiểu trả về, visibility và bối cảnh của class quyết định method có được serialization runtime nhận diện.

| Method theo đặc tả | Vai trò | Quyền truy cập |
|---|---|---|
| `void writeObject(ObjectOutputStream out) throws IOException` | Tùy chỉnh ghi trạng thái lớp | **private** |
| `void readObject(ObjectInputStream in) throws IOException, ClassNotFoundException` | Tùy chỉnh khôi phục trạng thái lớp | **private** |
| `void readObjectNoData() throws ObjectStreamException` | Khởi tạo khi stream không chứa dữ liệu của lớp trong tình huống hierarchy thay đổi | **private** |
| `Object writeReplace() throws ObjectStreamException` | Chọn object thay thế trước khi serialization | **Access modifier thích hợp bất kỳ** |
| `Object readResolve() throws ObjectStreamException` | Chọn object thay thế sau khi deserialization | **Access modifier thích hợp bất kỳ** |

Không có method nào trong bảng là method **override từ `Serializable`**: interface này chỉ là marker.

### 4.1. writeObject và readObject

~~~java
// Đoạn minh họa trong class implements Serializable.
@Serial
private void writeObject(ObjectOutputStream out) throws IOException {
    out.defaultWriteObject();
}

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    // Kiểm tra invariant sau khi khôi phục dữ liệu.
}
~~~

`defaultWriteObject()` ghi các trường theo cơ chế default serialization; `defaultReadObject()` khôi phục những trường tương ứng. Nếu thêm custom values, định dạng dữ liệu và thứ tự ghi/đọc **phải nhất quán**.

**Chỉ thêm hooks khi có lý do thực sự.** Nếu default serialized form đã đáp ứng nhu cầu, bạn không cần `writeObject/readObject` chỉ để có annotation. Custom deserialization cần được test và thiết kế an toàn.

### 4.2. readObjectNoData

~~~java
// Đoạn minh họa trong class implements Serializable.
@Serial
private void readObjectNoData() throws ObjectStreamException {
    throw new InvalidObjectException("missing class data");
}
~~~

Hook này xử lý trường hợp **không có dữ liệu của lớp trong serialization stream**, có thể liên quan thay đổi class hierarchy giữa sender và receiver hoặc stream không hoàn chỉnh. Nó **không phải hook được gọi sau mọi readObject**.

`InvalidObjectException` là subclass của `ObjectStreamException`. Chỉ nên từ chối dữ liệu thiếu theo kiểu này nếu thật sự phù hợp invariant của class.

### 4.3. writeReplace và readResolve

~~~java
// Đoạn minh họa trong class có semantics phù hợp.
@Serial
private Object writeReplace() throws ObjectStreamException {
    return this;
}

@Serial
private Object readResolve() throws ObjectStreamException {
    return this;
}
~~~

`writeReplace`/`readResolve` có các quy tắc truy cập riêng; không bắt buộc private như ba hook `writeObject/readObject/readObjectNoData`. Có thể dùng cho serialization proxy pattern hoặc khôi phục một object canonical khi phù hợp.

Ví dụ trên chỉ **trả chính đối tượng** để minh họa chữ ký, không phải mẫu thiết kế replacement có mục đích. Đừng thêm replacement hooks nếu không cần.

**Quan trọng:** Serialization có thể khôi phục đối tượng theo đường khác constructor thông thường. Vì vậy validation/invariants sau deserialize phải được thiết kế riêng, không chỉ trông vào kiểm tra trong constructor.

## 5. Compiler thực sự kiểm tra gì?

Đây là trọng tâm của bài học.

### 5.1. Kiểm tra bắt buộc về vị trí annotation

`@Serial` có `@Target({METHOD, FIELD})`. Ví dụ:

~~~java
// CỐ Ý SAI: annotation không áp dụng cho class declaration.
@Serial
final class NotAFieldOrMethod {
}
~~~

Compiler từ chối theo quy tắc **annotation target**. Đó là lỗi cú pháp/kiểu áp dụng annotation, **không phải** kiểm tra đặc thù một serialization hook có chữ ký đúng.

### 5.2. Kiểm tra ngữ nghĩa được khuyến khích

Javadoc nói **compilers are encouraged to validate** — compiler được khuyến khích báo warning khi `@Serial` áp dụng lên field/method không thuộc danh sách hoặc thuộc bối cảnh không có hiệu lực.

Do đó:

- `@Serial` trên một method bình thường có thể vẫn biên dịch.
- `@Serial` trên UID sai kiểu có thể tạo warning, không bắt buộc lỗi.
- `readObject(String)` không trở thành hook ngay cả khi được annotate.
- Nếu compiler không cảnh báo, **không chứng minh** member có hiệu lực.
- Cần review chữ ký dựa trên Javadoc, kiểm thử round-trip và dùng static analysis bổ sung khi có yêu cầu.

**Đừng đồng nhất “semantic error” trong Javadoc với yêu cầu mọi `javac` phải từ chối build.** Mức độ phát hiện và severity phụ thuộc compiler/tooling.

### 5.3. -Xlint:serial và -Werror

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:serial SerialAnnotationDemo.java
~~~

`-Xlint:serial` bật các cảnh báo liên quan serialization, chẳng hạn class `Serializable` thiếu `serialVersionUID` và những vấn đề member có thể được compiler nhận ra. **Không phải mọi warning trong nhóm này do `@Serial` gây ra**, và không phải mọi misuse của `@Serial` đều được chẩn đoán.

Nếu CI muốn **warning khiến build lỗi**, có thể dùng:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:serial -Werror SerialAnnotationDemo.java
~~~

`-Werror` biến **warning phát hiện được** thành điều kiện làm build thất bại, không chỉ riêng warning thuộc nhóm serial. Chọn chính sách này khi team đã chuẩn hóa warnings và bảo đảm các warning có thể được giải quyết.

**Không dùng `@SuppressWarnings("serial")` để che hook sai chữ ký.** Sửa khai báo đúng mới là phương án cần thiết.

## 6. Java 17+ hoàn chỉnh: @Serial đúng và round-trip

Ví dụ tạo `Ticket` implements `Serializable`, đánh dấu UID và hai hooks. Chương trình serialize vào **mảng byte được chính tiến trình tạo** rồi khôi phục. Nó không nhận bytes từ file lạ hoặc network.

`readObject` kiểm tra lại `id` và `seats` để không chấp nhận trạng thái không hợp lệ.

### 6.1. SerialAnnotationDemo.java

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.ObjectStreamClass;
import java.io.Serial;
import java.io.Serializable;

public final class SerialAnnotationDemo {
    static final class Ticket implements Serializable {
        @Serial
        private static final long serialVersionUID = 42L;

        private String id;
        private int seats;

        Ticket(String id, int seats) {
            if (id == null || id.isBlank() || seats < 1) {
                throw new IllegalArgumentException("invalid ticket");
            }
            this.id = id;
            this.seats = seats;
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
            if (id == null || id.isBlank() || seats < 1) {
                throw new InvalidObjectException("invalid ticket");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Ticket original = new Ticket("JAVA14", 2);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(original);
        }

        Ticket restored;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            restored = (Ticket) in.readObject();
        }

        System.out.println("id=" + restored.id);
        System.out.println("seats=" + restored.seats);
        System.out.println("uid=" +
                ObjectStreamClass.lookup(Ticket.class).getSerialVersionUID());
        System.out.println("roundTrip=" +
                (original != restored && original.id.equals(restored.id)
                        && original.seats == restored.seats));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:serial SerialAnnotationDemo.java
java SerialAnnotationDemo
~~~

**Đầu ra đã biên dịch và chạy thực tế:**

~~~text
id=JAVA14
seats=2
uid=42
roundTrip=true
~~~

### 6.2. Diễn giải

1. `Ticket implements Serializable`: marker interface cho phép class tham gia Object Serialization.
2. `@Serial private static final long serialVersionUID = 42L`: đúng kiểu UID được runtime nhận diện. Annotation làm rõ ý định, không làm runtime đọc annotation.
3. `writeObject(ObjectOutputStream)`: signature chuẩn **private void**, dùng `defaultWriteObject()`.
4. `readObject(ObjectInputStream)`: signature chuẩn **private void**, dùng `defaultReadObject()` và validate invariant; báo `InvalidObjectException` khi sai.
5. `id=JAVA14` và `seats=2`: dữ liệu từ object gốc được khôi phục.
6. `uid=42`: `ObjectStreamClass` đọc UID hiệu lực từ **field hợp lệ**, không phải từ reflection của `@Serial`.
7. `roundTrip=true`: object đọc về **không cùng tham chiếu** với object gốc, nhưng dữ liệu như mong đợi.

**Không nhất thiết phải viết hai hooks này trong mọi class.** Ví dụ cố tình dùng chúng để minh họa chữ ký và việc validate. Nếu không cần custom serialization, default mechanism cùng UID phù hợp thường đơn giản hơn.

Không cố định số byte trong `ByteArrayOutputStream` vì mục tiêu ở đây là semantics của declarations, không phải phụ thuộc độ dài một serialized stream cụ thể.

## 7. Thử sai: warning có thể không làm build fail

Tạo tệp riêng **`SerialInvalidProbe.java`**. Đây là **code cố ý sai về ngữ nghĩa**, không dùng trong production:

~~~java
import java.io.Serial;
import java.io.Serializable;

final class WrongSerialField implements Serializable {
    @Serial
    private static final int serialVersionUID = 5;
}

final class WrongSerialHook implements Serializable {
    @Serial
    private void readObject(String text) {}
}

final class NonSerializableSerialField {
    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Bật cảnh báo:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:serial SerialInvalidProbe.java
~~~

**Quan sát kiểm thử thực tế** dùng `javac` JDK 24 với `--release 17`:

~~~text
warning: [serial] serialVersionUID must be of type long in class WrongSerialField
warning: [serial] serializable class WrongSerialHook has no definition of serialVersionUID
warning: [serial] sole parameter of serialization-related method readObject must have type ObjectInputStream to be effective rather than type String
3 warnings
~~~

Đã bỏ qua đường dẫn và số dòng vì chúng phụ thuộc workspace. Lần biên dịch trên có **exit code 0**, mặc dù có ba warnings.

Cảnh báo thứ nhất: UID sai kiểu `int`. Cảnh báo thứ hai: class Serializable thiếu UID đúng. Cảnh báo thứ ba: `readObject(String)` không phải special deserialization method.

**Giới hạn quan trọng đã kiểm chứng:** `@Serial` trên `NonSerializableSerialField` **không tạo thêm warning** trong lần thử này, dù Javadoc coi việc annotate field trong class không `Serializable` là **sai ngữ nghĩa**. Điều đó chứng minh `@Serial` + `-Xlint:serial` **không phải kiểm tra đầy đủ mọi ngữ cảnh**.

Thử:

~~~bash
javac --release 17 -encoding UTF-8 \
  -Xlint:serial -Werror SerialInvalidProbe.java
~~~

`-Werror` khiến build **thất bại** vì các warnings được nhận diện. Trong lần thử, compiler báo **1 error + 3 warnings, exit code 1**. Wording và mức phát hiện có thể thay đổi theo JDK; quy tắc ổn định là `-Werror` coi warnings là lỗi.

### 7.1. Sửa lỗi đúng bản chất

~~~java
// CỐ Ý SAI: không phải special hook.
@Serial
private void readObject(String text) {
}
~~~

Phải sửa chữ ký, không phải chỉ thêm annotation:

~~~java
// Đoạn minh họa trong class implements Serializable.
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
}
~~~

Đoạn sau mới có cấu trúc special method theo quy định. Nếu deserialization có thể mang trạng thái không hợp lệ, phải kiểm tra invariant và từ chối dữ liệu đúng cách.

### 7.2. Hai nhóm kiểm tra khác nhau

- **Target lỗi:** `@Serial` trên class hoặc constructor không thuộc METHOD/FIELD; đây là lỗi compiler vì annotation applicability.
- **Semantics lỗi:** `@Serial` trên method/field có target được phép nhưng chữ ký hoặc context không hợp lệ; compiler có thể phát warning hoặc không nhận ra.

Đừng kết luận “code compile thành công nên runtime chắc chắn nhận ra mọi hook”.

## 8. Checklist hai field, năm method

| Thành viên | Chữ ký cần đúng | `@Serial` có phù hợp? |
|---|---|---|
| UID | `private static final long serialVersionUID` | Có |
| Danh sách serialized fields | `private static final ObjectStreamField[] serialPersistentFields` | Có khi thật sự khai báo |
| Ghi custom state | `private void writeObject(ObjectOutputStream) throws IOException` | Có khi thật sự khai báo |
| Đọc custom state | `private void readObject(ObjectInputStream) throws IOException, ClassNotFoundException` | Có khi thật sự khai báo |
| Không có class data | `private void readObjectNoData() throws ObjectStreamException` | Có khi thật sự khai báo |
| Thay object lúc ghi | `Object writeReplace() throws ObjectStreamException` | Có nếu thực sự có hiệu lực |
| Thay object lúc đọc | `Object readResolve() throws ObjectStreamException` | Có nếu thực sự có hiệu lực |

**Không gắn annotation lên mọi instance field sẽ được lưu**. Ví dụ:

~~~java
final class Product implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String sku;   // Không @Serial.
    private int quantity; // Không @Serial.
}
~~~

`sku` và `quantity` có thể thuộc default serialized state nhưng **không phải special fields cần gắn @Serial**. Annotation này không phải công cụ chọn những field nào sẽ serialize.

## 9. Các ngữ cảnh đặc biệt

### 9.1. Class không Serializable

~~~java
// CỐ Ý SAI NGỮ NGHĨA:
final class LocalUtility {
    @Serial
    private static final long serialVersionUID = 1L;
}
~~~

Class không `Serializable` và không nhận serializability từ hierarchy nên field UID không có vai trò trong Object Serialization. Javadoc nói đây là **misuse**, dù một compiler cụ thể có thể không cảnh báo.

**Giải pháp:** Không gắn UID/@Serial cho class không cần serialization. Nếu class thật sự cần serializability, phải thiết kế toàn bộ contract và xử lý object graph.

### 9.2. Enum có cơ chế serialization riêng

`enum` có mô hình serialization được đặc tả riêng. Theo Javadoc `Serial`, những special serialization methods kể trên **không có tác dụng cho enum**; `serialVersionUID` của enum được định nghĩa là `0L`.

Đừng tự thêm `@Serial writeObject/readObject/readResolve` hay một UID vào enum rồi mong thay đổi behavior serialization.

### 9.3. Externalizable

`Externalizable` kế thừa `Serializable` nhưng định nghĩa những method phải triển khai:

- `writeExternal(ObjectOutput)`
- `readExternal(ObjectInput)`

Đây là methods của interface `Externalizable`, nên dùng **`@Override`**. Chúng **không nằm trong danh sách năm methods cho `@Serial`**.

Trong một `Externalizable` class, các declarations `writeObject`, `readObject`, `readObjectNoData` và field `serialPersistentFields` **không có hiệu lực** theo Javadoc `Serial`. Không gắn annotation rồi mong thay thế được `writeExternal/readExternal`.

### 9.4. Record Serializable

Từ Java 16, record là tính năng chính thức. Record có thể implements `Serializable`, nhưng việc deserialize record tuân **Serialization of Records**. Javadoc `Serializable` cho biết các special handling methods được liệt kê **bị bỏ qua trong record types**.

Vì vậy không copy `readObject/writeObject` của class thông thường vào record và tin rằng hooks tự được gọi. Khi cần validation, xem quy tắc canonical constructor và serialized record form trong đặc tả.

**Thông điệp chung:** Đúng tên của một member chưa đủ; member phải nằm trong **ngữ cảnh mà runtime thực sự dùng nó**.

## 10. Code review và kiểm thử

Khi thấy `@Serial` trong code, hãy kiểm tra:

1. Class có đúng `Serializable` không (trực tiếp hoặc từ superclass)? Có thuộc `enum`, `record`, `Externalizable` không?
2. Annotation nằm ở **FIELD/METHOD** đúng target chưa?
3. Với field, có đúng tên `serialVersionUID`/`serialPersistentFields`, kiểu và modifier?
4. Với method, có đúng **tên, tham số, return, visibility, checked exceptions** và ngữ cảnh?
5. Có thật sự cần custom serialization, hay default mechanism đủ?
6. Nếu cần custom `readObject`, có kiểm tra invariant và từ chối dữ liệu thiếu/không hợp lệ?
7. Build bật `-Xlint:serial` và đội có chính sách xử lý warnings không?
8. Có round-trip test cho class, đặc biệt với các phiên bản dữ liệu cũ cần hỗ trợ?
9. Có kiểm tra mọi object trong graph có thể được serialize như mong muốn không? Có xử lý `NotSerializableException` và `InvalidClassException` phù hợp không?
10. Nguồn serialized bytes có đáng tin? Nếu không, có cách **tránh deserialize** hoặc chính sách filtering nghiêm ngặt chưa?

### Ba loại lỗi cần phân biệt

| Nhóm | Ví dụ | Cách kiểm tra |
|---|---|---|
| **Annotation target** | `@Serial` trên class | Compiler từ chối trực tiếp |
| **Serialization declaration semantics** | `readObject(String)`, UID kiểu int | Javadoc, compiler lint, static analysis, code review |
| **Runtime/security** | UID không tương thích, object graph thiếu Serializable, input giả mạo | Integration tests, version compatibility, validation, deserialization filtering |

Không có một annotation duy nhất phát hiện đủ cả ba nhóm.

## 11. Bảo mật khi còn dùng Java Object Serialization

`@Serial` là công cụ giúp **kiểm tra khai báo ở mã nguồn**, **không bảo vệ deserialization**.

Javadoc `Serializable` và `ObjectInputFilter` hiện hành cảnh báo rằng **deserialize dữ liệu không tin cậy là nguy hiểm**. Object graph và types trong stream có thể tạo hiệu ứng không mong muốn. Không mở `ObjectInputStream` để đọc trực tiếp bytes từ Internet/file lạ chỉ vì các class có `@Serial`.

Khuyến nghị hiện hành:

- **Tránh native deserialization từ nguồn không tin cậy** khi có thể. Với protocol mới, cân nhắc định dạng có schema và parser được kiểm soát, giới hạn size/depth, xác thực nguồn và validate input.
- Nếu buộc đọc Java Object Serialization do hợp đồng còn hiệu lực, sử dụng **`ObjectInputFilter`** để hạn chế các class, kích thước arrays, số đối tượng, độ sâu và lượng byte.
- **JEP 415 từ Java 17** hỗ trợ **context-specific deserialization filter factory**. Chính sách lọc nên vừa đủ theo từng tình huống, không đơn giản cho phép mọi type.
- Trong `readObject`, kiểm tra **invariants** sau `defaultReadObject`; không dựa hoàn toàn vào kiểm tra constructor.
- Serialization filter không tự thay thế threat modeling, authentication, resource limits và validation nghiệp vụ.
- Nếu cần lưu dữ liệu bền vững lâu dài, phải xét schema/version compatibility, không phụ thuộc mù quáng vào Java native serialization.

**Ví dụ chính chỉ đọc bytes do chính tiến trình tạo** trong `ByteArrayOutputStream`; không lấy nó làm mẫu trực tiếp cho luồng từ khách lạ.

## 12. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Nghĩ `@Serial` làm class Serializable | Annotation không bật serialization | Implements `Serializable` có chủ đích |
| Gắn `@Serial` lên mọi instance field | Chỉ hai special fields được quy định | Annotate UID/serialPersistentFields |
| Viết `serialVersionUID` kiểu int | UID phải là long | `private static final long serialVersionUID` |
| Viết `readObject(String)` | Không phải serialization hook | Dùng `ObjectInputStream` đúng chữ ký |
| Viết `public void readObject(ObjectInputStream)` | Hook cần private | Sửa visibility |
| Gắn `@Override` lên `readObject` | Không override method từ Serializable | Dùng `@Serial` |
| Tìm `@Serial` bằng runtime reflection | Retention là SOURCE | Hiểu runtime theo Serialization Specification |
| Nghĩ compiler exit 0 là chắc chắn đúng | Warning có thể chưa biến thành error; có sai ngữ nghĩa không được phát hiện | Lint + review + test |
| Mong `-Xlint:serial` bắt mọi misuse | Chỉ được khuyến khích, không bảo đảm mọi case | Static analysis bổ sung |
| Nhầm `@serial` Javadoc tag với `@Serial` annotation | Khác vai trò | Dùng đúng cú pháp |
| Gắn `@Serial` lên `Externalizable.writeExternal` | Đó là interface method | `@Override` |
| Custom hooks cho enum/record như class thường | Loại này có luật serialization đặc thù | Đọc spec của enum/record |
| Cho rằng UID giống nhau đảm bảo mọi thay đổi tương thích | UID chỉ là một phần contract | Test với dữ liệu các phiên bản |
| Tin `@Serial` làm việc đọc bytes lạ an toàn | Annotation không lọc input | Tránh untrusted data; dùng filters và validation |
| Che warnings mà không sửa hook sai | Runtime có thể bỏ qua hook | Sửa chữ ký và ngữ cảnh |

## 13. Bài tự kiểm tra

**Câu 1.** `@Serial` và `implements Serializable` khác gì?

**Đáp án:** `Serializable` đánh dấu class cho cơ chế Object Serialization; `@Serial` đánh dấu field/method đặc biệt trong source để hỗ trợ phát hiện khai báo sai. Annotation không kích hoạt serialization.

**Câu 2.** `@Serial` dùng cho class hoặc constructor được không?

**Đáp án:** Không, `@Target` chỉ có METHOD và FIELD. Đặt sai target là compile error.

**Câu 3.** Hai field hợp lệ là gì?

**Đáp án:** `private static final long serialVersionUID` và `private static final ObjectStreamField[] serialPersistentFields`, trong lớp/ngữ cảnh mà chúng có tác dụng.

**Câu 4.** Ba hook bắt buộc private?

**Đáp án:** `writeObject(ObjectOutputStream)`, `readObject(ObjectInputStream)` và `readObjectNoData()`. `writeReplace/readResolve` có luật access khác.

**Câu 5.** `@Serial private void readObject(String s)` có tự được runtime gọi?

**Đáp án:** Không. Không khớp special `readObject(ObjectInputStream)`; compiler có thể warning nhưng không tự sửa chữ ký.

**Câu 6.** `javac -Xlint:serial` ra warnings thì build tự fail?

**Đáp án:** Không. Warnings thường không gây nonzero exit code. Dùng `-Werror` nếu muốn coi warnings là lỗi.

**Câu 7.** UID có `@Serial` trong class không Serializable đúng không?

**Đáp án:** Không có ý nghĩa serialization; Javadoc xem là misuse, dù một compiler có thể không cảnh báo.

**Câu 8.** Reflection runtime có tìm được `@Serial`?

**Đáp án:** Không. Retention là SOURCE; runtime nhận diện hooks theo quy tắc class serialization, không dựa annotation.

**Câu 9.** `Externalizable.writeExternal(ObjectOutput)` có `@Serial` không?

**Đáp án:** Không. Đây là method của `Externalizable`, dùng `@Override`; còn các hooks `writeObject/readObject/readObjectNoData` không áp dụng ở đây.

**Câu 10.** `@Serial` khiến ObjectInputStream từ mạng an toàn?

**Đáp án:** Không. Tránh deserialize dữ liệu không tin cậy; nếu buộc dùng, áp dụng chính sách `ObjectInputFilter`, giới hạn tài nguyên và kiểm tra trạng thái.

**Câu 11.** UID giống nhau có chắc dữ liệu cũ đọc được?

**Đáp án:** Không. UID là một phần compatibility; kiểu field/serialized form và invariants còn phải tương thích.

## Tài liệu tham khảo chính thức

- [Oracle Java 14 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/io/Serial.html): mốc `Since: 14` và danh sách members đặc biệt.
- [Oracle Java 17 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serial.html): `Target`, `Retention` và nguyên tắc kiểm tra ngữ nghĩa.
- [Oracle Java 25 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serial.html): API hiện hành, ngữ cảnh enum/Externalizable không hiệu lực.
- [Oracle Java 26 — `java.io.Serial`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/Serial.html): đối chiếu API còn hiệu lực.
- [Oracle Java 25 — `Serializable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serializable.html): chữ ký hooks, enum/record rules, UID và cảnh báo về input không tin cậy.
- [Oracle Java 25 — `ObjectStreamClass`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectStreamClass.html): UID và serialized class descriptor.
- [Oracle Java 25 — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputFilter.html): lọc input khi deserialize.
- [Oracle Java 25 — `javac`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `-Xlint:serial` và `-Werror`.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/25/docs/specs/serialization/index.html): rules của members đặc biệt và compatibility.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): lọc theo context từ Java 17.

**Ghi nhớ:** `@Serial` không phải serialization switch hay security mechanism. Nó đánh dấu **hai special fields hoặc năm special methods** để compiler/IDE/static analyzer **có cơ hội phát hiện khai báo sai**. Đúng annotation nhưng **sai chữ ký hoặc ngữ cảnh** vẫn có thể làm hook vô hiệu. Kiểm tra theo Javadoc, bật `-Xlint:serial`, xử lý warnings và kiểm thử round-trip trên dữ liệu tin cậy.