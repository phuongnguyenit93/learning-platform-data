# Giới hạn của `@Serial` đối với an toàn dữ liệu đầu vào trong Java

## 1. Phát biểu đúng vấn đề

Java cung cấp annotation `java.io.Serial` từ **Java 14** để đánh dấu những trường và phương thức tham gia cơ chế **Java Object Serialization**. Nó giúp người đọc mã và trình biên dịch nhận biết rằng `serialVersionUID`, `readObject`, `writeObject` hay các thành viên chuyên biệt khác có ý nghĩa đối với serialization.

Tuy nhiên, một lớp có `@Serial` **không đồng nghĩa lớp đó an toàn khi đọc dữ liệu từ người khác gửi đến**. Annotation này không kiểm tra dữ liệu tại runtime, không ngăn tạo object có trường bất hợp lệ, không giới hạn loại class trong object graph và không xác thực nguồn gửi.

Ví dụ:

```java
import java.io.Serial;
import java.io.Serializable;

final class Order implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String code;
    private int units;
}
```

Đoạn trên cho thấy khai báo `serialVersionUID` đúng ngữ cảnh. Nó **không** nói rằng `code` luôn hợp lệ, `units` không âm hay một `ObjectInputStream` có thể đọc an toàn mọi byte trên mạng.

**Câu hỏi chính của bài:** `@Serial` thực sự kiểm tra điều gì? Vì sao không thể thay thế xác thực dữ liệu và phòng vệ khi giải tuần tự hóa? Nếu bắt buộc dùng Java Serialization thì phải áp dụng thêm những lớp bảo vệ nào?

**Ngữ cảnh Java 14 và hiện tại:** `@Serial` được bổ sung ở Java 14 và vẫn là annotation chuẩn trong Java 17/21+ và các JDK hiện đại. Các ví dụ dưới đây được kiểm chứng với `--release 14` và `--release 17`; chỉ dùng API còn áp dụng. Việc **tránh giải tuần tự hóa dữ liệu không tin cậy** là khuyến nghị bảo mật hiện hành, không phải một thủ thuật cũ đã lỗi thời.

## 2. `@Serial` dùng để kiểm tra **khai báo**, không kiểm tra **dữ liệu**

Khai báo chính thức của annotation:

```java
@Target({ElementType.METHOD, ElementType.FIELD})
@Retention(RetentionPolicy.SOURCE)
public @interface Serial {}
```

Đây là hình dạng rút gọn minh họa metadata của `java.io.Serial`, **không phải** đoạn yêu cầu người học tự định nghĩa annotation trùng tên. Hai thuộc tính quan trọng:

1. **`@Target(METHOD, FIELD)`:** chỉ gắn annotation cho phương thức và trường hợp lệ theo phạm vi khai báo.
2. **`@Retention(SOURCE)`:** annotation được dùng lúc biên dịch; không được giữ để Java reflection truy vấn tại runtime.

Nói cách khác:

| Câu hỏi | `@Serial` có làm được không? |
| --- | --- |
| Chú thích `serialVersionUID` là một trường thuộc giao thức serialization? | **Có** |
| Hỗ trợ compiler phát hiện phương thức `readObject` bị khai báo sai chữ ký? | **Có**, tùy kiểm tra/cảnh báo của compiler |
| Xác thực `units >= 0` khi đọc object từ byte stream? | **Không** |
| Chặn một class nguy hiểm trong object graph? | **Không** |
| Giới hạn độ sâu, số phần tử mảng hoặc số bytes đầu vào? | **Không** |
| Ngăn hàm tùy biến `readObject` gây tác dụng phụ? | **Không** |
| Bảo đảm byte stream không bị sửa đổi hoặc giả mạo? | **Không** |
| Tạo mã hóa, chữ ký số, quyền truy cập hay transaction? | **Không** |

Vì annotation có retention `SOURCE`, JVM **không dựa vào `@Serial` để quyết định cho phép hay từ chối giải tuần tự hóa**. Cơ chế serialization nhận diện các thành viên đặc biệt qua **điều kiện chữ ký và hợp đồng serialization**, không qua một “cờ bảo mật” tên `@Serial`.

### Vai trò thật sự của compile-time checking

`@Serial` tương tự `@Override` ở ý tưởng giúp rà soát **ý định khai báo**. Nếu lập trình viên viết một phương thức tưởng rằng là serialization hook nhưng chữ ký sai, compiler có thể cảnh báo. Ví dụ sai:

```java
// ĐOẠN MINH HỌA LỖI KHAI BÁO, KHÔNG CHÉP VÀO MAIN.JAVA
@Serial
private void readObject(java.io.InputStream input) {
    // Đây KHÔNG phải chữ ký readObject(ObjectInputStream).
}
```

Chữ ký serialization hook hợp lệ phải nhận `ObjectInputStream` và khai báo các checked exception tương ứng. Cảnh báo compiler có giá trị để tránh hook bị bỏ qua do khai báo sai, nhưng **một phương thức đúng chữ ký vẫn có thể chứa logic xác thực yếu hoặc lỗ hổng bảo mật**.

Khi build, nên bật kiểm tra phù hợp, chẳng hạn:

```bash
javac --release 17 -Xlint:serial Main.java
```

`-Xlint:serial` giúp phát hiện các vấn đề liên quan serialization được compiler hỗ trợ. Nó không thực hiện kiểm thử input độc hại, không thay code review hoặc security testing. Nếu project sử dụng `-Werror`, cảnh báo có thể làm build thất bại; điều này là chính sách build, **không phải kiểm tra runtime**.

## 3. Những thành viên hợp lệ của `@Serial`

Theo Java SE API, `@Serial` dành cho **hai trường** và **năm phương thức** được cơ chế serialization quy định trong ngữ cảnh lớp phù hợp.

### Trường

```java
@Serial
private static final long serialVersionUID = 1L;

@Serial
private static final ObjectStreamField[] serialPersistentFields = ...;
```

Dòng có `...` ở trên là **cú pháp minh họa**, không biên dịch độc lập. `serialPersistentFields` dùng khi chủ động định nghĩa tập trường serial hóa, không phải thứ nên thêm vào mọi lớp.

### Phương thức

```java
@Serial
private void writeObject(ObjectOutputStream out)
        throws IOException { ... }

@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException { ... }

@Serial
private void readObjectNoData()
        throws ObjectStreamException { ... }

@Serial
Object writeReplace() throws ObjectStreamException { ... }

@Serial
Object readResolve() throws ObjectStreamException { ... }
```

Đây là **chữ ký có thân minh họa**, không phải một chương trình copy-chạy; các tên class cần import `java.io.*`. `writeReplace` và `readResolve` có quy tắc access/inheritance riêng trong serialization specification; đừng tự đổi mọi hook thành `private` rồi nghĩ là đúng cho mọi trường hợp.

Các thành viên phải được đặt trong **ngữ cảnh có ý nghĩa**:

- Lớp triển khai `Serializable` là ngữ cảnh thông thường của `readObject`, `writeObject` và `serialVersionUID`.
- `Externalizable` có cơ chế riêng, nên các hook `readObject`, `writeObject`, `readObjectNoData` và `serialPersistentFields` của Serializable **không có ý nghĩa tương tự** trong loại này.
- Một số thành viên trong `enum` bị cơ chế serialization bỏ qua theo quy định; việc đặt `@Serial` không thể làm chúng bắt đầu có hiệu lực.
- Annotation không được đặt tùy ý lên class, constructor, getter nghiệp vụ hoặc các phương thức “có tên gần giống”.

**Không cần viết cả bảy thành viên vào mỗi Serializable class.** Thông thường chỉ khai báo `serialVersionUID`; thêm hook khi thực sự cần quy tắc khôi phục, kiểm tra bất biến hay kiểm soát định dạng đã được cân nhắc.

## 4. Vì sao giải tuần tự hóa là một đường nhập liệu đặc biệt?

Khi nhận dữ liệu từ JSON, form hoặc API, ứng dụng thường gọi constructor hoặc factory rồi tự kiểm tra trường đầu vào. Với Java Object Serialization, `ObjectInputStream.readObject()` có cơ chế dựng lại object graph từ byte stream.

Đối với **một lớp thông thường triển khai Serializable**, quá trình khôi phục có thể tạo instance **mà không gọi constructor của chính lớp Serializable đó**. Do vậy kiểm tra trong constructor **không phải hàng rào đủ** khi object được khôi phục qua `readObject()`.

Ví dụ:

```java
Order(String code, int units) {
    if (units < 0) {
        throw new IllegalArgumentException("negative units");
    }
    this.code = code;
    this.units = units;
}
```

Giả sử `Order` là lớp `Serializable`. Nếu code chỉ kiểm tra trong constructor, một stream bị thao túng hoặc một object đã bị thay đổi trước khi serialize vẫn có thể chứa `units = -3`. Khi deserialize, constructor `Order(...)` không được gọi lại, nên điều kiện `units < 0` ở đó không bảo vệ đường nhập liệu này.

**Cách phòng vệ cần thiết khi buộc phải deserialize:** tái áp dụng các bất biến phù hợp trong `readObject(...)`, hoặc thiết kế một serialization proxy/giao thức dữ liệu khác có validation khi tái tạo object.

Tuy vậy, việc đặt validation **sau `defaultReadObject()`** không biến bản thân quá trình deserialize tùy ý thành an toàn: các object tham chiếu lồng nhau có thể đã được khôi phục, callback của class khác có thể được chạy, tài nguyên có thể bị tiêu thụ. Vì thế cần **kiểm soát loại class và giới hạn object graph trước khi cho phép đọc**, và ưu tiên tránh deserialize input không tin cậy ngay từ đầu.

## 5. Phân biệt ba lớp kiểm tra cần có

Đây là cách suy nghĩ hữu ích hơn việc chỉ hỏi “có `@Serial` chưa?”:

| Tầng | Đối tượng kiểm tra | Công cụ/phương pháp |
| --- | --- | --- |
| **1. Khai báo Java** | Thành viên serialization có đúng chữ ký, modifier và ý nghĩa? | `@Serial`, compiler, `-Xlint:serial`, code review |
| **2. Loại object và tài nguyên** | Stream có cố tạo class không được phép, mảng quá lớn, graph quá sâu, quá nhiều reference/byte? | `ObjectInputFilter`, filter factory, giới hạn kích thước trước parse, hạn chế quyền và tài nguyên |
| **3. Dữ liệu nghiệp vụ** | `id` đúng định dạng, số lượng hợp lệ, quan hệ trường nhất quán, không vi phạm quyền/logic? | Constructor/factory, validation trong `readObject` hoặc proxy, hậu kiểm ứng dụng |

Còn những lớp bảo vệ **ngoài ba tầng**: authentication của client, authorization cho hành động, TLS khi truyền, integrity/signature khi cần, monitoring, cập nhật thư viện/JDK và thực thi trong môi trường giới hạn. Không thể gộp chúng vào một annotation.

**Ví dụ:** một `Order` với `units = -3` vẫn là object thuộc **đúng class `Order`**. Filter cho phép class đó chưa thể biết `units` trái quy tắc. Ngược lại, `readObject` kiểm tra `units` không nhất thiết bảo vệ chống một chuỗi object graph có class không mong muốn trước khi tới `Order`.

## 6. Khuyến nghị ưu tiên: tránh Java native deserialization với input không tin cậy

Java SE API và Secure Coding Guidelines hiện hành cảnh báo rằng **giải tuần tự hóa Java object từ dữ liệu không tin cậy vốn nguy hiểm và nên tránh**.

Trong thiết kế mới nhận dữ liệu từ Internet, file upload hoặc người dùng không tin cậy, thường nên:

1. Chọn **giao thức dữ liệu được định nghĩa rõ** như JSON, protobuf hoặc một định dạng nhị phân có schema thay vì nhận object graph Java tùy ý.
2. Giới hạn **kích thước đầu vào, số trường, độ sâu và độ phức tạp** ngay tại cổng vào.
3. Parse thành **DTO chỉ chứa kiểu dữ liệu được phép**; không bật polymorphic type binding tùy ý từ input.
4. Kiểm tra schema và **bất biến nghiệp vụ** trước khi tạo hoặc sử dụng object quan trọng.
5. Áp dụng authorization riêng: một payload hợp lệ về cấu trúc vẫn có thể yêu cầu hành động trái quyền.
6. Xử lý lỗi, timeout và giám sát tài nguyên có giới hạn.

**Một định dạng khác không tự động an toàn.** JSON/protobuf cũng cần parser được duy trì, schema, validation, giới hạn tài nguyên và cách xử lý polymorphism phù hợp. Điểm khác là bạn có thể thiết kế giao thức **data-only, allowlist và kiểm soát loại object**, thay vì mặc nhiên phục hồi graph class Java có hook thực thi.

Khi một hệ thống **bắt buộc** đọc legacy Java serialized stream từ nguồn được quản lý, `@Serial` vẫn hữu ích cho khai báo nhưng phải kết hợp thêm `ObjectInputFilter` và kiểm tra dữ liệu. Không nên viết một dự án mới chỉ để dùng thêm `@Serial` rồi mở cổng nhận `ObjectInputStream` từ mọi client.

## 7. Chương trình Java 14/17+ hoàn chỉnh: annotation, filter và validation

Chương trình sau cố ý tạo **ba dạng dữ liệu đầu vào** để cho thấy ba cơ chế làm việc khác nhau:

- **Đúng loại, đúng giá trị:** Deserialize thành công.
- **Đúng loại nhưng vi phạm bất biến:** Filter theo class có thể cho qua, nhưng `readObject` **từ chối**.
- **Sai loại class:** `ObjectInputFilter` **từ chối** trước khi tạo object không được phép.
- **Input quá lớn:** bị từ chối ngay **trước khi mở ObjectInputStream**.

Ví dụ chỉ dùng **class đơn giản có `String` và `int`**, không coi đây là hệ thống xử lý stream tùy ý an toàn trong production. Nó phục vụ đào tạo về các lớp kiểm soát.

### Mã nguồn đầy đủ: `Main.java`

```java
import java.io.*;
import java.lang.reflect.Field;
import java.util.Date;

public class Main {
    static final class Order implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private String code;
        private int units;
        static int constructorCalls;

        Order(String code, int units) {
            if (!valid(code, units)) {
                throw new IllegalArgumentException("bad initial state");
            }
            this.code = code;
            this.units = units;
            constructorCalls++;
        }

        static boolean valid(String code, int units) {
            return code != null && code.length() >= 1
                    && code.length() <= 20
                    && code.matches("[A-Z0-9-]+")
                    && units >= 0 && units <= 1000;
        }

        @Serial
        private void readObject(ObjectInputStream in)
                throws IOException, ClassNotFoundException {
            in.defaultReadObject();
            if (!valid(code, units)) {
                throw new InvalidObjectException("invalid order state");
            }
        }

        @Override
        public String toString() {
            return code + ":" + units;
        }
    }

    static byte[] encode(Object value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(value);
        }
        return bytes.toByteArray();
    }

    static Object decode(byte[] bytes)
            throws IOException, ClassNotFoundException {
        if (bytes.length > 4096) {
            throw new IllegalArgumentException("input too large");
        }

        try (ObjectInputStream input =
                new ObjectInputStream(new ByteArrayInputStream(bytes))) {
            input.setObjectInputFilter(info -> {
                if (info.depth() > 5 || info.references() > 30
                        || info.arrayLength() > 100
                        || info.streamBytes() > 4096) {
                    return ObjectInputFilter.Status.REJECTED;
                }

                Class<?> type = info.serialClass();
                if (type != null) {
                    return type == Order.class
                            ? ObjectInputFilter.Status.ALLOWED
                            : ObjectInputFilter.Status.REJECTED;
                }
                return ObjectInputFilter.Status.UNDECIDED;
            });
            return input.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        Order order = new Order("SO-7", 2);
        byte[] validBytes = encode(order);
        int before = Order.constructorCalls;

        System.out.println("VALID=" + decode(validBytes));
        System.out.println("CONSTRUCTOR_NOT_RERUN="
                + (before == Order.constructorCalls));

        Order broken = new Order("SO-7", 2);
        broken.units = -3; // Test fixture: simulate impossible state.
        try {
            decode(encode(broken));
            System.out.println("BROKEN=ACCEPTED");
        } catch (InvalidObjectException ex) {
            System.out.println("BROKEN=REJECTED_BY_VALIDATION");
        }

        try {
            decode(encode(new Date(0L)));
            System.out.println("OTHER_CLASS=ACCEPTED");
        } catch (InvalidClassException ex) {
            System.out.println("OTHER_CLASS=REJECTED_BY_FILTER");
        }

        try {
            decode(new byte[4097]);
            System.out.println("OVERSIZE=ACCEPTED");
        } catch (IllegalArgumentException ex) {
            System.out.println("OVERSIZE=REJECTED_BEFORE_PARSE");
        }

        Field uid = Order.class.getDeclaredField("serialVersionUID");
        System.out.println("SERIAL_RUNTIME_VISIBLE="
                + uid.isAnnotationPresent(Serial.class));
    }
}
```

### Biên dịch và chạy

Với JDK 17 hoặc mới hơn:

```bash
javac --release 17 -encoding UTF-8 -Xlint:serial Main.java
java Main
```

Đây cũng là chương trình tương thích Java 14: đã xác nhận biên dịch với:

```bash
javac --release 14 -encoding UTF-8 -Xlint:serial Main.java
```

**Stdout chính xác đã kiểm chứng:**

```text
VALID=SO-7:2
CONSTRUCTOR_NOT_RERUN=true
BROKEN=REJECTED_BY_VALIDATION
OTHER_CLASS=REJECTED_BY_FILTER
OVERSIZE=REJECTED_BEFORE_PARSE
SERIAL_RUNTIME_VISIBLE=false
```

Không có những lời gọi nguy hiểm hay input bên ngoài trong chương trình demo: tất cả các byte stream đều được **tự tạo trong bộ nhớ** để kiểm tra đường xử lý. **Kết quả PASS của demo không chứng minh Java Serialization an toàn khi dùng với luồng chưa được tin cậy trên Internet.**

## 8. Phân tích sâu ví dụ: `@Serial` không phải lá chắn dữ liệu

### 8.1. Hai nơi khác nhau thực thi validation

Constructor:

```java
Order(String code, int units) {
    if (!valid(code, units)) {
        throw new IllegalArgumentException("bad initial state");
    }
    // gán dữ liệu ...
}
```

Validation khi deserialize:

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    if (!valid(code, units)) {
        throw new InvalidObjectException("invalid order state");
    }
}
```

Hai đoạn ở đây được trích từ `Main.java`, **không phải lớp độc lập**. Constructor ngăn mã gọi bình thường tạo `Order` sai dữ liệu. Phương thức `readObject` bảo vệ **đường khôi phục serialization**, nơi constructor `Order` không được chạy lại.

**Chú ý:** `@Serial` chỉ chỉ ra phương thức `readObject` được dự kiến làm serialization hook. **Chính câu lệnh `valid(...)` và `throw InvalidObjectException(...)` mới thực hiện xác thực**; nếu xóa validation nhưng giữ nguyên annotation, dữ liệu sai không tự bị chặn.

`in.defaultReadObject()` đọc và gán các field theo định dạng serialization. Chúng ta kiểm tra ngay sau đó. Trong lớp có graph nhiều object phức tạp, có thể phải thiết kế khác để không lộ một object mới khôi phục một phần hoặc kích hoạt tác dụng phụ từ graph trước khi validation; vì vậy filter/allowlist và mô hình data-only vẫn là điều kiện riêng.

### 8.2. Vì sao constructor không chạy khi đọc lại?

Chương trình tạo `Order` một lần và lưu bộ đếm `constructorCalls`. Khi thực thi `decode(validBytes)`, bộ đếm không tăng. Đó là hành vi phù hợp với cơ chế `Serializable` cho constructor **của chính lớp Serializable**.

Không nên khái quát thành “mọi constructor ở mọi lớp kế thừa đều không bao giờ chạy”: cơ chế tạo object có quy tắc riêng đối với superclass không Serializable; ngoài ra `Externalizable` và record có quy tắc riêng. Điều thực sự cần nhớ ở đây là **không tin rằng constructor validation của một Serializable class tự động chạy lại khi khôi phục**.

### 8.3. Vì sao `broken.units = -3` hợp lệ trong test?

`Order` là lớp lồng trong `Main`. Test cố ý sửa trực tiếp trường `private units` của instance hợp lệ **sau constructor** để mô phỏng một object có trạng thái không thể tạo qua constructor bình thường.

Khi serialize instance đó, ta tạo được một byte stream chứa `units = -3`. `ObjectInputFilter` vẫn nhìn thấy đúng loại `Order`, nên vấn đề **nằm ở bất biến nghiệp vụ**. `Order.readObject` mới phát hiện và ném `InvalidObjectException`.

Trong hệ thống thực tế, dữ liệu có thể bị thay đổi bởi lỗi ứng dụng, phiên bản cũ, stream bị sửa đổi hoặc nguồn không tin cậy. **Kiểm thử trạng thái sai không có nghĩa đây là cách hợp lệ để sửa private fields trong mã sản phẩm.**

### 8.4. Annotation không có ở runtime

`Field.isAnnotationPresent(Serial.class)` trả `false` do retention của `@Serial` là `SOURCE`. Đây là bằng chứng trực tiếp của điều đã học: **không thể dựa vào reflection runtime để kiểm tra một đối tượng đã “được @Serial bảo vệ” hay chưa**.

Một runtime deserialization policy phải dựa vào cơ chế runtime được thiết kế cho bảo vệ dữ liệu như `ObjectInputFilter`, validation, quyền và giới hạn tài nguyên; `@Serial` không thay thế chúng.

## 9. `ObjectInputFilter` giải quyết vấn đề gì?

`java.io.ObjectInputFilter` được đưa vào JDK 9 (JEP 290) và vẫn là API được dùng để giới hạn Java native deserialization. Với từng stream, ta có thể áp dụng filter bằng `ObjectInputStream.setObjectInputFilter(...)` **trước khi đọc bất kỳ object nào**.

Trong ví dụ:

```java
input.setObjectInputFilter(info -> {
    if (info.depth() > 5 || info.references() > 30
            || info.arrayLength() > 100 || info.streamBytes() > 4096) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type != null) {
        return type == Order.class
                ? ObjectInputFilter.Status.ALLOWED
                : ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
});
```

Đây là fragment lấy từ phương thức `decode` đã chạy. Các thông tin chính của `FilterInfo`:

| Thuộc tính | Công dụng |
| --- | --- |
| `serialClass()` | Class đang được xét nếu lời gọi filter có thông tin class |
| `arrayLength()` | Độ dài mảng được request, hoặc giá trị báo không phải mảng |
| `depth()` | Độ sâu object graph tại thời điểm lọc |
| `references()` | Số tham chiếu/đối tượng được xét tích lũy |
| `streamBytes()` | Số byte đã được tiêu thụ ở thời điểm filter được gọi, theo implementation |

Nếu class không phải `Order`, filter trả `REJECTED`; khi thử đọc `java.util.Date`, chương trình nhận `InvalidClassException`.

**Quan trọng:** một filter không có nghĩa “mọi input đã được kiểm tra toàn diện”. Nó chủ yếu kiểm soát các **class và giới hạn tài nguyên** mà API có thể quan sát trong quá trình đọc. `FilterInfo.serialClass()` có thể là `null`, ví dụ khi xử lý reference; Java Serialization còn có các ngoại lệ như **`String` và kiểu primitive không kích hoạt kiểm tra class theo cách thông thường**. Theo tài liệu `ObjectInputStream`, `String` được xử lý giống primitive về khía cạnh invocation của filter.

Vì vậy, filter cho phép `Order` **không** bảo đảm `code` thỏa biểu thức chính quy. Đó là lý do `Order.readObject` vẫn phải kiểm tra code và units.

### Giới hạn theo bytes nên có cả trước và trong stream

`streamBytes()` là chỉ số tại thời điểm filter được gọi, **không phải một phép chặn bao phủ mọi byte chưa đọc trước khi parser xử lý**. Ví dụ dùng thêm:

```java
if (bytes.length > 4096) {
    throw new IllegalArgumentException("input too large");
}
```

Giới hạn này phát hiện rõ một mảng đầu vào lớn **trước khi tạo `ObjectInputStream`**. Với nguồn mạng thực, cần chặn kích thước ngay ở tầng nhận/streaming chứ không đọc vô hạn vào `byte[]` rồi mới kiểm tra. Trong khi dùng input streaming, còn cần policy riêng cho timeout, giới hạn bytes và bộ nhớ/cpu.

### `ALLOWED`, `REJECTED` và `UNDECIDED`

- `ALLOWED`: filter được hỏi đã cho phép class/trạng thái tại điểm đó.
- `REJECTED`: từ chối deserialization tại điểm kiểm tra.
- `UNDECIDED`: filter không có kết luận ở thời điểm đó. **Không nên tự coi đây là “đã cấm mặc định mọi thứ”**; kết quả cuối cùng còn tùy các filter khác, factory và quy tắc đọc.

Trong ví dụ, mọi `serialClass()` khác `null` và khác `Order.class` đều bị từ chối. Với hệ thống thực, cần kiểm kê **toàn bộ class/array hợp pháp** mà graph yêu cầu. Một allowlist quá hẹp có thể từ chối dữ liệu hợp lệ; một allowlist quá rộng có thể cho phép graph nguy hiểm. Không sửa bằng cách cho phép bừa mọi class từ `java.*` hoặc wildcard tất cả package.

**Một filter được đặt cho stream** phải được thiết lập theo hợp đồng API trước khi đọc object. Không gọi nhiều lần `setObjectInputFilter` để thay đổi chính sách sau mỗi object; cơ chế filter factory và chính sách JVM-wide cũng có thể ảnh hưởng filter hiệu lực.

## 10. Vì sao allowlist không thay kiểm tra giá trị?

Giả sử filter chỉ chấp nhận `Order`, nhưng trong stream có:

```text
code = ""
units = -10
```

Đúng class vẫn có thể sai nghiệp vụ. Với dữ liệu được dùng để tạo đơn hàng, ngoài class đúng còn cần:

- `code != null` và không rỗng.
- Format `code` đúng, giới hạn độ dài, không chứa ký tự không được phép.
- `units` nằm trong miền hợp lệ theo nghiệp vụ.
- Quan hệ các trường như tổng tiền, số lượng, trạng thái không mâu thuẫn.
- Người gửi có quyền thực hiện hành động gắn với dữ liệu.
- Dữ liệu không chứa đường dẫn, URL, expression hoặc nội dung có khả năng gây SQL injection/XSS/path traversal ở bước sử dụng tiếp theo.

Filter biết tên class `Order` nhưng **không hiểu ý nghĩa của `units`, `code` hay quyền của khách hàng**. Validation sau deserialize không nên chỉ dựa vào `instanceof Order`.

Một invariant còn cần được kiểm tra **ngay trước hành động nhạy cảm** nếu object có thể bị sửa sau khi khôi phục. Tránh đưa object chưa xác thực vào cache, event bus hay domain service trước khi kiểm tra đủ yêu cầu.

## 11. Tại sao `serialVersionUID` không chứng minh dữ liệu đáng tin?

`serialVersionUID` giúp cơ chế serialization kiểm tra **tính tương thích phiên bản của class** giữa lúc serialize và deserialize. Đây **không phải**:

- Chữ ký số của payload.
- Mã xác thực thông điệp (MAC).
- Mật khẩu, token, checksum hay hash bảo vệ nội dung.
- Bằng chứng stream đến từ ứng dụng chính chủ.
- Chứng minh rằng field values tuân thủ invariant.

Ví dụ:

```java
@Serial
private static final long serialVersionUID = 1L;
```

Dù giá trị `1L` “khớp” với class local, một byte stream có cùng định dạng vẫn có thể chứa `units = -3` hoặc graph không mong muốn. Thậm chí việc tùy ý sửa UID để vượt lỗi tương thích có thể khiến dữ liệu bị hiểu sai theo format. Không xử lý rủi ro deserialization bằng cách “cố cho serialVersionUID giống nhau”.

Với dữ liệu phải tin cậy về nguồn, cần thiết kế **authentication/integrity** ở tầng phù hợp; việc dữ liệu có thể deserialize không chứng minh nó đúng hay đáng tin.

## 12. Hai điểm an toàn khác: object graph và mã có thể được thực thi

### 12.1. Object graph có thể phức tạp

Serialization có thể khôi phục nhiều object lồng nhau, array lớn, tham chiếu lặp hoặc graph có cấu trúc phức tạp. Dữ liệu này có thể gây:

- Tiêu thụ RAM quá mức.
- CPU dành cho parse hoặc tạo graph lớn.
- Stack/depth pressure.
- Thực thi logic deserialize tùy biến của những class mà ứng dụng không chủ định đọc.
- Bất biến của nhiều object hoặc quan hệ giữa chúng bị vi phạm.

Đó là lý do filter cần vừa **allowlist class** vừa **giới hạn depth/references/array length/bytes** và ứng dụng phải có thêm giới hạn input/tài nguyên. `@Serial` không cung cấp bất kỳ quota nào.

### 12.2. Deserialization có thể kích hoạt phương thức đặc biệt

Với các class Serializable có hook như `readObject`, `readResolve`, hoặc callback validation, runtime có thể gọi mã của class trong quá trình khôi phục. Một class “hợp lệ theo tên” nhưng có logic deserialize không an toàn vẫn có thể gây tác dụng phụ.

Không giả định rằng “filter chạy thì mọi thứ chưa từng được thực thi trước đó”. Filter là phòng vệ bổ sung chứ không phải **sandbox**. Cần tránh cho phép những class không cần thiết, giữ mã deserialize đơn giản, hạn chế graph phức tạp và không dùng nguồn không đáng tin làm trigger cho logic hệ thống.

**Không nên dựa vào Java Security Manager như lớp bảo vệ chính của code mới.** Các JDK hiện đại đã vô hiệu hóa cơ chế này, nên kiến trúc phòng vệ cần áp dụng những biện pháp hiện hành như giảm bề mặt deserialization, kiểm soát input, phân quyền môi trường và cập nhật phụ thuộc.

## 13. JDK 17+ và bộ lọc theo ngữ cảnh (JEP 415)

`ObjectInputFilter` từ JDK 9 có thể áp dụng theo từng stream. JDK 17 (JEP 415) bổ sung cơ chế **context-specific deserialization filter** thông qua JVM-wide filter factory, giúp hạ tầng quyết định chính sách khác nhau tùy nơi gọi/deserialization context.

Điểm quan trọng cho hệ thống hiện hành:

1. Có thể có **filter mặc định/phạm vi JVM** do vận hành cấu hình.
2. Ứng dụng có thể thiết lập **filter cho stream cụ thể** khi thực hiện `readObject`.
3. **Filter factory** có thể phối hợp chính sách theo context.
4. Cần kiểm tra **chính sách hiệu lực của đúng runtime**, không mặc định mọi JVM “chắc chắn đã chặn nguy hiểm” hoặc mọi lời gọi `setObjectInputFilter` luôn thay thế toàn bộ filter hiện có.
5. Một filter áp dụng trên stream **không thay thế domain validation** cho các field được cho phép.

Đối với hệ thống đơn giản, một allowlist cục bộ cho từng `ObjectInputStream` như ví dụ là bước dễ hiểu. Với thư viện lớn hoặc nhiều nơi deserialize, cần kiến trúc factory/global policy để tránh bỏ sót call site. Khi triển khai thật, tra tài liệu `ObjectInputFilter.Config` của đúng JDK/version, kiểm thử các luồng hợp lệ và các luồng bị từ chối.

**Không khuyến khích** tùy tiện thay đổi filter toàn JVM chỉ để làm một ví dụ hoạt động; có thể ảnh hưởng các thư viện và dịch vụ khác trong cùng process. Tập trung vào policy có scope rõ ràng, có test và có trách nhiệm sở hữu.

## 14. Sai lầm cần tránh khi viết `readObject`

### 14.1. Chỉ gọi `defaultReadObject` rồi trả về

```java
@Serial
private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject(); // Không có xác thực bất biến.
}
```

Với class có rule về miền giá trị, đây là **đường nhập dữ liệu thiếu validation**. Annotation đúng nhưng logic chưa đủ.

### 14.2. Tin constructor đã kiểm tra trước đó

```java
Order(String code, int units) {
    if (units < 0) throw new IllegalArgumentException();
    // ...
}
```

Đối tượng được deserialize theo `Serializable` thông thường không bắt buộc chạy constructor này. Cần kiểm tra tương ứng trong hook/factory/proxy, không dùng một lần kiểm tra ở đường tạo object khác để biện minh.

### 14.3. Ném ngoại lệ không rõ nguyên nhân hoặc bỏ qua lỗi

Khi data invalid, nên dừng deserialize và báo lỗi theo hợp đồng, ví dụ `InvalidObjectException` cho object state không hợp lệ. Không làm:

```java
try {
    return input.readObject();
} catch (Exception ex) {
    return new Order("DEFAULT", 0); // Che giấu input lỗi.
}
```

Đây là **anti-pattern minh họa**, không phải cách khôi phục được khuyến nghị. Nó có thể khiến dữ liệu giả tạo đi qua kiểm soát và khó điều tra sự cố. Nếu hệ thống cần fallback, phải thiết kế rõ hợp đồng và không nuốt mọi lỗi từ một nguồn không tin cậy.

### 14.4. Gọi một callback có tác dụng phụ trước khi validate xong

Không gửi email, ghi database, gọi mạng, thay đổi quyền hoặc công bố object ra vùng shared state từ `readObject` khi các bất biến chưa được bảo đảm. Cẩn trọng với reference tới object deserialize chưa hoàn tất và subclass/mutable data.

Với class mang dữ liệu nhạy cảm, cân nhắc **serialization proxy pattern** hoặc **không cho phép Serializable** ngay từ thiết kế. Annotation không thay đổi bản chất này.

## 15. Kiểm thử bảo mật theo đúng mục tiêu

Một chương trình kiểm thử chỉ kiểm tra `@Serial` có trên field là **không có ý nghĩa bảo vệ dữ liệu**, bởi annotation có retention `SOURCE`. Thay vào đó, đặt các kịch bản test riêng:

| Loại test | Dữ liệu | Kết quả cần có |
| --- | --- | --- |
| Khai báo | `@Serial` trên `serialVersionUID`, `readObject` đúng chữ ký | Biên dịch/cảnh báo hợp lý với `-Xlint:serial` |
| Happy path | `Order(code="SO-7", units=2)` | Khôi phục đúng trạng thái |
| Constructor bypass | Tăng bộ đếm constructor rồi deserialize | Constructor `Order` không được gọi lại |
| Invariant sai | `units=-3` hoặc `code=""` từ serialized state | Ném `InvalidObjectException` |
| Class không được phép | Serialized `java.util.Date` thay vì `Order` | Filter từ chối, `InvalidClassException` |
| Input quá lớn | Dữ liệu vượt giới hạn đầu vào | Chặn trước parse |
| Graph quá sâu/nhiều reference | Serialized graph vượt policy | Filter từ chối |
| Array lớn | Serialized array vượt giới hạn | Filter từ chối |
| Stream hỏng/cắt giữa | Bytes không hợp lệ hoặc bị truncate | Báo lỗi, không cấp object nửa hợp lệ |
| Dữ liệu hợp lệ nhưng không có quyền | Object đúng schema nhưng requester không có quyền | Authorization riêng từ chối |
| Hiệu năng/resilience | Tải lớn và nhiều client lỗi | Không tiêu thụ vượt giới hạn tài nguyên đã đặt |

**Phân biệt lỗi:** `InvalidObjectException` trong demo là kết quả của **validation do ứng dụng tự viết**. `InvalidClassException` cho class khác là kết quả **filter từ chối**. Không nên gom mọi loại exception vào một nhãn “@Serial đã bảo vệ”.

Với nguồn dữ liệu bên ngoài, còn cần kiểm thử parser limits, authentication, logging an toàn (không log payload nhạy cảm nguyên vẹn), khả năng từ chối yêu cầu quá tải và bản cập nhật JDK/thư viện.

## 16. Câu hỏi thường gặp

**`@Serial` có giống `@NotNull` hoặc Bean Validation không?**

Không. `@Serial` nói về **thành viên của cơ chế serialization**, không mô tả ràng buộc giá trị. Ngay cả các annotation validation khác cũng cần framework/thao tác validate phù hợp; không nên giả định chỉ thêm annotation là mọi đường deserialization đều tự kiểm tra.

**Nếu chỉ nhận object của `Order`, tôi đã an toàn chưa?**

Chưa. `Order` có thể có giá trị sai, field tham chiếu ngoài ý muốn hoặc logic hook gây tác dụng phụ. Cần filter đúng phạm vi, quota, validation và kiểm soát nguồn; nếu untrusted, ưu tiên định dạng dữ liệu an toàn hơn.

**`serialVersionUID` có giúp chống sửa dữ liệu không?**

Không. Đây là cơ chế tương thích class version, không phải chữ ký hay xác thực.

**Có thể bật `-Xlint:serial` rồi bỏ hết validation không?**

Không. Compiler không biết miền dữ liệu nghiệp vụ hoặc chính sách tin cậy ở runtime.

**Vì sao ví dụ cho `serialClass()==null` là `UNDECIDED`?**

Filter có những lần được gọi **không kèm class**, ví dụ cho reference. Chính sách của demo chỉ ra quyết định theo class khi class được cung cấp và từ chối vượt quota. Với môi trường khác có filter factory, kết quả tổng hợp phải theo chính sách cụ thể. `UNDECIDED` không tự tương đương một global deny.

**Nếu dữ liệu đã đến từ một server nội bộ, có thể tin hoàn toàn không?**

Không nên. Server nội bộ cũng có thể bị lỗi, cấu hình sai, bị xâm nhập hoặc gửi dữ liệu phiên bản khác. Chính sách có thể điều chỉnh mức tin cậy nhưng vẫn cần validation, resource limits và xác thực cơ chế truyền phù hợp.

**Có thể thay `ObjectInputFilter` bằng `@Serial` trên `readObject` không?**

Không. `@Serial` chỉ hỗ trợ kiểm tra khai báo. Filter kiểm soát class/resource ở runtime; validation kiểm tra trạng thái ứng dụng. Ba mục tiêu khác nhau.

## 17. Bài tập có lời giải

**Bài 1.** Một lớp `Serializable` có `@Serial private static final long serialVersionUID = 1L;` nhưng không có `readObject` và constructor cấm số âm. Có thể nhận serialized object từ nguồn bất kỳ không?

**Lời giải:** Không. Constructor của Serializable class không được chạy lại khi deserialize theo cơ chế thông thường, nên giá trị sai có thể lọt vào. `@Serial` không thay validation. Tránh deserialize dữ liệu không tin cậy; nếu phải dùng thì thêm filter/quota, validation và thiết kế an toàn.

**Bài 2.** Một `ObjectInputFilter` cho phép class `Order` nhưng không có kiểm tra `units`. Byte stream có `units = -1` đi qua bước class filter. Đây có phải lỗi của `@Serial`?

**Lời giải:** Đây là thiếu sót trong **validation giá trị**. `@Serial` không được thiết kế để kiểm tra trường dữ liệu; filter theo class cũng không hiểu miền nghiệp vụ.

**Bài 3.** Trong ví dụ `Main.java`, nếu xóa `@Serial` khỏi `readObject` nhưng vẫn giữ đúng chữ ký và logic validation, validation có còn được chạy không?

**Lời giải:** Có, cơ chế serialization nhận diện hook từ **chữ ký hợp lệ**, không phải từ `@Serial`. Tuy vậy nên giữ annotation để compiler và người bảo trì dễ phát hiện khai báo sai.

**Bài 4.** Khi gọi `setObjectInputFilter` **sau** `readObject` đầu tiên, việc đặt policy còn hợp lệ không?

**Lời giải:** Không. API yêu cầu đặt filter cho stream theo hợp đồng trước khi đọc object; cố thay đổi sau khi đã đọc có thể ném `IllegalStateException`. Phải cấu hình policy từ đầu.

**Bài 5.** Nếu stream nhỏ hơn giới hạn bytes và class được phép, đã đủ an toàn không?

**Lời giải:** Chưa. Dữ liệu có thể sai bất biến, quan hệ trường, quyền, hoặc có những hành vi khác cần kiểm soát. Filter cũng không xác thực mọi primitive/String hay một schema nghiệp vụ đầy đủ.

**Bài 6.** Có nên đánh dấu mọi field `@Serial` để bảo vệ dữ liệu cá nhân không?

**Lời giải:** Không. `@Serial` chỉ dùng trên **các thành viên được serialization specification định nghĩa**, không trên mọi field. Để giảm rò rỉ dữ liệu, tránh serialize thông tin nhạy cảm; cân nhắc `transient`, proxy và thiết kế dữ liệu đầu ra có chọn lọc theo yêu cầu, nhưng những cách đó vẫn không thay bảo mật end-to-end.

## 18. Checklist khi code review

Trước khi chấp nhận code có `ObjectInputStream.readObject()`:

1. **Có thật sự cần Java native deserialization không?** Nếu input không tin cậy, ưu tiên tránh hẳn.
2. **Đã xác định chính xác nơi phát sinh byte stream, nguồn gửi và ranh giới tin cậy chưa?**
3. **Có giới hạn input size/time/resources trước và trong quá trình đọc không?**
4. **Có filter allowlist class/array và quota phù hợp cho stream không?**
5. **Có tính đến JDK-wide filter và filter factory của runtime được triển khai không?**
6. **Có validation dữ liệu và bất biến trong đường deserialize, không chỉ constructor không?**
7. **Có class/hook nào có tác dụng phụ hoặc cho phép tạo graph phức tạp không?**
8. **Có phòng tránh lộ object chưa hợp lệ trước khi deserialize hoàn tất không?**
9. **Có authorization/authentication/integrity cần thiết ở tầng ứng dụng không?**
10. **Có unit/integration tests cho input hợp lệ, sai class, sai giá trị, oversized, lỗi stream và denial-of-service không?**
11. **Có dùng `@Serial` đúng vị trí để được compiler kiểm tra, nhưng không nhầm annotation là bảo vệ runtime không?**
12. **Có kế hoạch bảo trì serialization format, phiên bản và cập nhật JDK/library không?**

**Ghi nhớ cuối cùng:** `@Serial` (Java 14+) giúp làm đúng **khai báo serialization** và hỗ trợ **compile-time diagnostics**. Nó có retention `SOURCE`, **không thực thi bảo mật hoặc xác thực dữ liệu đầu vào**. Khi phải dùng Java native deserialization, hãy kiểm soát **nguồn dữ liệu**, **loại class và tài nguyên** bằng `ObjectInputFilter` cùng quota, rồi **kiểm tra bất biến và quyền nghiệp vụ**; ngay cả vậy, hướng an toàn hơn với input không tin cậy là **không deserialize graph object Java tùy ý**.

### Tài liệu chính thức còn áp dụng

- [Java SE 21 — `java.io.Serial`, các thành viên hợp lệ và `@Retention(SOURCE)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serial.html).
- [Java SE 21 — `ObjectInputStream` và cảnh báo về dữ liệu không tin cậy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html).
- [Java SE 21 — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html).
- [Java SE 21 — `Serializable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html).
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290).
- [JEP 415 — Context-Specific Deserialization Filters (JDK 17)](https://openjdk.org/jeps/415).
- [Oracle Secure Coding Guidelines for Java SE — Serialization and Deserialization](https://www.oracle.com/java/technologies/javase/seccodeguide.html).
