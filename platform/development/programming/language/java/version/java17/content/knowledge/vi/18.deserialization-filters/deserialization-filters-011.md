# Giới hạn của filter: không thay thế kiểm tra nội dung dữ liệu trong Java 17

## 1. Filter giải tuần tự hóa bảo vệ điều gì?

Java Serialization có thể dựng lại một object graph từ byte stream. Khi dữ liệu đến từ tệp, mạng hoặc một nguồn bên ngoài, việc đọc stream có thể khiến JVM tạo nhiều object, mảng lớn hoặc một đồ thị tham chiếu rất sâu. Một số lớp còn có logic tùy chỉnh trong quá trình giải tuần tự hóa.

Từ Java 9, Java cung cấp `ObjectInputFilter` để ứng dụng đặt giới hạn cho dữ liệu được đọc qua `ObjectInputStream`. Filter có thể quyết định dựa trên metadata như:

- Lớp đang được giải tuần tự hóa.
- Độ sâu của đồ thị object.
- Số lượng tham chiếu đã gặp.
- Số byte stream đã tiêu thụ.
- Độ dài của mảng đang được đọc.

Những giới hạn này giúp giảm rủi ro từ object graph quá lớn, quá sâu hoặc chứa lớp không được phép. Tuy nhiên, **filter không phải bộ kiểm tra nội dung nghiệp vụ của object**. Nó không thay thế việc xác thực giá trị field, quan hệ giữa các field, schema, quyền truy cập hay quy tắc nghiệp vụ sau khi dữ liệu được khôi phục.

Ví dụ, filter có thể cho phép lớp `UserProfile` và giới hạn số byte đầu vào. Nhưng nó không thể kết luận rằng `age` phải từ 0 đến 130, `email` có đúng định dạng, hay người gửi có quyền sửa hồ sơ đó. Đây là các kiểm tra nội dung và nghiệp vụ ở tầng khác.

Sau bài học, người học cần:

1. Hiểu phạm vi của `ObjectInputFilter` và các metadata mà nó quan sát được.
2. Phân biệt giới hạn cấu trúc object graph với kiểm tra nội dung field.
3. Biết filter không xác thực invariant, schema, authorization hoặc ý nghĩa nghiệp vụ.
4. Kết hợp filter với validation sau khi đọc và invariant trong lớp Serializable.
5. Nhận diện rủi ro của custom serialization code và gadget chain.
6. Không coi filter là sandbox hoặc bằng chứng rằng Java native serialization an toàn cho dữ liệu không đáng tin cậy.

## 2. ObjectInputFilter trong Java 17

### 2.1. Vai trò của filter

`ObjectInputFilter` là interface trong `java.io`. Filter được gọi trong quá trình giải tuần tự hóa để xem xét thông tin về class và trạng thái stream tại thời điểm đó. Nó trả về một trong ba quyết định:

| Trạng thái | Ý nghĩa |
|---|---|
| `ALLOWED` | Filter này cho phép tiếp tục với thông tin đang xét |
| `REJECTED` | Từ chối dữ liệu đang xét; quá trình đọc bị chặn |
| `UNDECIDED` | Filter không đưa ra quyết định; việc xử lý tiếp theo phụ thuộc filter factory/cấu hình và mặc định của stream |

Filter là một cơ chế kiểm soát **trong lúc giải tuần tự hóa**, không phải một hàm nhận toàn bộ object đã dựng xong rồi kiểm tra các thuộc tính.

### 2.2. FilterInfo cung cấp những gì?

`ObjectInputFilter.FilterInfo` cung cấp các thông tin:

| Phương thức | Thông tin |
|---|---|
| `serialClass()` | Class đang được xem xét; có thể là `null` trong một số trường hợp như tham chiếu hoặc không có class tương ứng tại điểm gọi |
| `arrayLength()` | Độ dài mảng; giá trị âm nếu thông tin này không áp dụng |
| `depth()` | Độ sâu hiện tại của đồ thị object |
| `references()` | Số tham chiếu object đã được xử lý trong stream |
| `streamBytes()` | Số byte đã tiêu thụ từ stream tại thời điểm filter được gọi |

Đây là metadata hữu ích để giới hạn tài nguyên và lớp. Interface không cung cấp một API tổng quát kiểu `getFieldValue("age")` để filter đọc các field của object đang được dựng.

### 2.3. Filter không được gọi như validator cho từng primitive

Các giá trị primitive được mã hóa trực tiếp trong serialization stream không phải là object class để filter kiểm tra như một lớp riêng. String được mã hóa cụ thể trong stream cũng có quy tắc xử lý riêng; không nên thiết kế logic nghiệp vụ dựa trên giả định filter sẽ được gọi cho từng chuỗi hoặc từng primitive field.

Ví dụ, field `int age` có thể mang giá trị âm hoặc lớn bất thường. Giới hạn `maxbytes` có thể hạn chế tổng dữ liệu, nhưng không diễn đạt quy tắc `age >= 0`. Muốn kiểm tra điều đó, lớp hoặc tầng nghiệp vụ phải xác thực giá trị sau khi đọc.

## 3. Filter có thể giới hạn những gì?

### 3.1. Giới hạn loại class

Filter có thể từ chối class không nằm trong tập kiểu được ứng dụng chấp nhận. Đây là cơ chế quan trọng để giảm bề mặt tấn công của Java Serialization.

Ví dụ, một giao thức chỉ mong đợi DTO `UserProfile` thì có thể từ chối các class khác xuất hiện trong object graph:

~~~java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }
    if (type == UserProfile.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};
~~~

Đây chỉ là minh họa cho allowlist hẹp. Ứng dụng thực tế phải liệt kê đầy đủ các class hợp lệ mà định dạng object graph cần dùng, bao gồm container hoặc kiểu phần tử nếu có. Không mở rộng allowlist thành các package rộng chỉ để làm test chạy qua.

### 3.2. Giới hạn độ sâu

`depth()` cho biết độ sâu của đồ thị object tại điểm filter được gọi. Đặt giới hạn giúp từ chối đồ thị lồng nhau quá sâu:

~~~java
if (info.depth() > 20) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Giới hạn này hữu ích với cấu trúc cây hoặc object graph lồng nhau. Nó không kiểm tra ý nghĩa của mối quan hệ cha/con, cũng không bảo đảm số phần tử trong mỗi node hợp lệ.

### 3.3. Giới hạn số tham chiếu

`references()` giúp giới hạn số tham chiếu object được xử lý:

~~~java
if (info.references() > 10_000) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Giới hạn này có thể ngăn một stream tạo đồ thị có quá nhiều object/reference. Nhưng nó không phải giới hạn chính xác cho số bản ghi nghiệp vụ. Một collection có thể có cách biểu diễn serialization khác nhau; số reference không tương đương một cách tổng quát với số record hợp lệ.

### 3.4. Giới hạn số byte stream

`streamBytes()` cho phép giới hạn lượng dữ liệu đã được đọc:

~~~java
if (info.streamBytes() > 1_000_000L) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Giới hạn byte giúp giảm khả năng đọc một stream quá lớn. Tuy nhiên, byte limit không xác nhận payload có đúng schema, không bảo đảm mỗi chuỗi có độ dài nghiệp vụ hợp lệ và cũng không giới hạn trực tiếp mọi chi phí xử lý phát sinh từ một object nhỏ.

### 3.5. Giới hạn độ dài mảng

`arrayLength()` có thể dùng để từ chối mảng vượt kích thước:

~~~java
long length = info.arrayLength();
if (length >= 0 && length > 100_000) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Giới hạn này áp dụng cho array. Nó không tự động đồng nghĩa với giới hạn số phần tử của mọi collection. Một `ArrayList` hoặc kiểu collection tùy chỉnh có thể lưu dữ liệu theo cách riêng; hãy kết hợp giới hạn byte, references, class và validation số phần tử sau khi đọc.

## 4. Ví dụ cấu hình filter theo giới hạn tài nguyên

Một filter có thể kết hợp nhiều giới hạn trong cùng quyết định:

~~~java
import java.io.ObjectInputFilter;

static ObjectInputFilter resourceLimits() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 10_000
                || info.streamBytes() > 1_000_000L
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 100_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }
        return ObjectInputFilter.Status.UNDECIDED;
    };
}
~~~

Filter này chỉ áp dụng các giới hạn cấu trúc/tài nguyên. Nó chưa đưa ra allowlist class. Trong ứng dụng thật, nên kết hợp với chính sách class phù hợp thay vì chỉ dùng giới hạn kích thước.

Một cách kết hợp:

~~~java
static ObjectInputFilter profileFilter() {
    return info -> {
        if (info.depth() > 10
                || info.references() > 100
                || info.streamBytes() > 64 * 1024
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 1_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (type == UserProfile.class || type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
~~~

Các con số chỉ là ví dụ. Giới hạn thực tế phải dựa trên kích thước payload, cấu trúc dữ liệu hợp lệ và tải của ứng dụng. Nếu một DTO hợp lệ có thêm kiểu ngày tháng, collection hoặc enum, allowlist phải phản ánh chính xác schema đó.

## 5. Gắn filter vào ObjectInputStream

### 5.1. Per-stream filter

Có thể gắn filter cho một `ObjectInputStream` bằng `setObjectInputFilter`:

~~~java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(profileFilter());
    Object value = input.readObject();
}
~~~

Đặt filter **trước lần đọc object đầu tiên**. Một stream đã bắt đầu đọc không thể tùy tiện thay filter theo ý muốn; API giới hạn thời điểm và số lần cấu hình.

### 5.2. Global filter

Java 17 cũng hỗ trợ cấu hình filter toàn JVM qua thuộc tính `jdk.serialFilter` hoặc API `ObjectInputFilter.Config.setSerialFilter`. Global filter hữu ích để đặt baseline cho các luồng serialization trong tiến trình.

Tuy nhiên, ứng dụng có thể có nhiều loại dữ liệu và schema khác nhau. Một global allowlist quá hẹp có thể làm hỏng luồng hợp lệ; một global allowlist quá rộng lại giảm tác dụng bảo vệ. Cần thiết kế filter factory và chính sách theo từng ranh giới dữ liệu nếu ứng dụng có nhiều nguồn serialization.

### 5.3. Filter factory và nhiều lớp chính sách

Java 17 có cơ chế filter factory để kết hợp hoặc lựa chọn filter theo stream và context. Khi ứng dụng dùng filter toàn cục cùng per-stream filter, cần hiểu quy tắc kết hợp trong Javadoc; đừng giả định rằng một filter mới luôn ghi đè hoặc luôn bổ sung theo cách mong muốn.

Điểm thiết kế nên giữ:

- Baseline giới hạn tài nguyên áp dụng rộng.
- Allowlist class theo loại payload.
- Quy tắc nội dung và nghiệp vụ nằm ở validator của ứng dụng.

## 6. Pattern-based filter cũng chỉ kiểm tra metadata

Java cung cấp cú pháp filter pattern để cấu hình giới hạn và class:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1048576;"
      + "maxarray=10000;com.example.dto.*;!*");
~~~

Các phần trong pattern:

- `maxdepth=10`: giới hạn độ sâu.
- `maxrefs=1000`: giới hạn số tham chiếu.
- `maxbytes=1048576`: giới hạn byte đã đọc.
- `maxarray=10000`: giới hạn độ dài mảng.
- `com.example.dto.*`: cho phép class thuộc package được nêu theo quy tắc pattern.
- `!*`: từ chối class không khớp các pattern cho phép trước đó.

Pattern filter hữu ích để khai báo chính sách ngắn gọn. Nó vẫn không thể đọc giá trị field như `age` hoặc xác thực chuỗi email. Allowlist class không phải allowlist giá trị của object.

Khi dùng pattern, hãy xác minh cú pháp package, wildcard và thứ tự pattern theo Javadoc Java 17. Không sao chép một pattern rộng từ ví dụ mà không điều chỉnh theo object graph thực tế.

## 7. Điều filter không thể thay thế

### 7.1. Không kiểm tra giá trị field

Giả sử object có cấu trúc:

~~~java
final class UserProfile implements Serializable {
    private String username;
    private int age;
    private String role;
}
~~~

Filter có thể quyết định class `UserProfile` được phép xuất hiện. Nó không thể kết luận:

- `username` không rỗng và có độ dài phù hợp.
- `age` nằm trong khoảng hợp lệ.
- `role` chỉ nhận các giá trị nghiệp vụ được phép.

Đây là validation dữ liệu sau khi object được khôi phục.

### 7.2. Không kiểm tra quan hệ giữa các field

Một object có thể chứa:

~~~text
startDate = 2026-12-20
endDate   = 2026-11-01
~~~

Hai giá trị riêng lẻ đều có thể parse được, nhưng quan hệ `startDate <= endDate` bị vi phạm. Filter không có thông tin field để kiểm tra invariant như vậy.

Tương tự, nó không xác thực rằng:

- Tổng các dòng chi tiết bằng tổng hóa đơn.
- Currency phù hợp với account.
- Trạng thái đơn hàng cho phép chuyển sang trạng thái mới.
- ID tham chiếu tới một bản ghi tồn tại và caller được quyền truy cập.

### 7.3. Không xác thực schema nghiệp vụ

Filter không thay thế kiểm tra version payload, trường bắt buộc, enum value, migration schema hoặc tính tương thích giữa producer và consumer. Một class có thể được phép nhưng payload vẫn thiếu dữ liệu bắt buộc hoặc chứa giá trị của phiên bản cũ.

Với dữ liệu trao đổi lâu dài, nên có schema rõ ràng và versioning có chủ đích. Native Java serialization có cơ chế versioning riêng như `serialVersionUID`, nhưng điều đó không tự kiểm tra tính hợp lệ của nội dung nghiệp vụ.

### 7.4. Không kiểm tra authorization

Một object có field `role = "ADMIN"` không có nghĩa người gửi được phép trở thành admin. Filter không biết danh tính người gửi, session hiện tại, quyền trên tài nguyên hoặc chính sách truy cập.

Authorization phải được thực hiện ở tầng nghiệp vụ/server sau khi dữ liệu được xác thực và gắn với danh tính đáng tin cậy. Không dùng field trong payload làm bằng chứng quyền hạn.

### 7.5. Không đảm bảo object hợp lệ chỉ vì class được allow

Một class được cho phép vẫn có thể nhận dữ liệu field không hợp lệ. Nó cũng có thể có custom serialization logic. Filter không chứng minh mọi instance của class đó đều an toàn hoặc đáp ứng invariant.

## 8. Validation sau khi giải tuần tự hóa

Sau khi đọc object, hãy kiểm tra kiểu mong đợi và dữ liệu bên trong trước khi đưa vào logic nghiệp vụ.

~~~java
Object value = input.readObject();

if (!(value instanceof UserProfile profile)) {
    throw new InvalidObjectException("Expected UserProfile");
}

validateProfile(profile);
~~~

Ví dụ validator:

~~~java
static void validateProfile(UserProfile profile)
        throws InvalidObjectException {
    if (profile.username() == null
            || profile.username().isBlank()
            || profile.username().length() > 80) {
        throw new InvalidObjectException("Invalid username");
    }

    if (profile.age() < 0 || profile.age() > 130) {
        throw new InvalidObjectException("Invalid age");
    }

    if (!Set.of("USER", "EDITOR", "ADMIN").contains(profile.role())) {
        throw new InvalidObjectException("Invalid role");
    }
}
~~~

Các quy tắc trên là ví dụ minh họa; ứng dụng phải dùng chính sách thực tế của mình. Kiểm tra `role` hợp lệ về cú pháp vẫn chưa đủ để cấp quyền ADMIN; authorization cần kiểm tra riêng.

### 8.1. Kiểm tra trước khi object đi vào domain logic

Một quy trình phù hợp:

~~~text
Byte stream
   |
   v
ObjectInputStream + ObjectInputFilter
   |  - class allowlist
   |  - depth / references / bytes / array length
   v
Object graph được khôi phục
   |
   v
Kiểm tra kiểu và invariant
   |  - field bắt buộc
   |  - miền giá trị
   |  - quan hệ giữa các field
   v
Kiểm tra nghiệp vụ và authorization
   |
   v
Đưa dữ liệu hợp lệ vào xử lý
~~~

Filter là một lớp phòng vệ ở giai đoạn đọc. Validation và authorization vẫn cần được thực hiện trước khi tin cậy hoặc sử dụng dữ liệu.

## 9. Bảo vệ invariant ngay trong Serializable class

Nếu class tự quản lý invariant của nó, có thể xác thực trong custom `readObject` sau `defaultReadObject`:

~~~java
private void readObject(ObjectInputStream input)
        throws IOException, ClassNotFoundException {
    input.defaultReadObject();

    if (username == null || username.isBlank()) {
        throw new InvalidObjectException("username is required");
    }
    if (age < 0 || age > 130) {
        throw new InvalidObjectException("age is out of range");
    }
}
~~~

Khi invariant bị vi phạm, ném `InvalidObjectException` để từ chối object. Đây là cơ chế bảo vệ trạng thái của class trong lúc deserialization; nó vẫn khác với filter.

### 9.1. Validation trong readObject không phải sandbox

`readObject` là code do class định nghĩa và được thực thi trong quá trình giải tuần tự hóa. Nếu cho phép một class không đáng tin cậy, custom serialization method của nó có thể chạy trước khi caller nhận được object để validate.

Vì vậy:

- Chỉ allow class mà ứng dụng thực sự tin cậy và cần thiết.
- Không cho phép tùy tiện class plugin hoặc class lạ.
- Không coi validation sau `readObject` là cách ngăn side effect của custom code đã chạy.
- Tránh native serialization cho dữ liệu không đáng tin cậy nếu có định dạng dữ liệu an toàn hơn.

### 9.2. ObjectInputValidation cho invariant của đồ thị

Java Serialization còn có `ObjectInputValidation` để đăng ký callback xác thực sau khi object graph được khôi phục theo quy tắc serialization. Cơ chế này có thể hữu ích khi invariant phụ thuộc nhiều object trong graph.

Nó vẫn là validation của object graph, không phải class/resource filter. Không dùng nó thay cho giới hạn độ sâu, byte, array hoặc allowlist class.

## 10. Rủi ro gadget và custom serialization

Một rủi ro lớn của native deserialization là **gadget chain**: một chuỗi class có sẵn trong classpath có thể kết hợp hành vi trong các phương thức như `readObject`, `readResolve`, `readExternal` hoặc logic được gọi trong quá trình khôi phục để gây side effect ngoài ý muốn.

Filter giúp từ chối class không nằm trong allowlist, qua đó giảm bề mặt gadget. Nhưng nếu allowlist quá rộng hoặc cho phép class có hành vi nguy hiểm, filter không bảo đảm an toàn.

Những điểm cần lưu ý:

- `Serializable` không có nghĩa class an toàn để deserialize từ nguồn bất kỳ.
- `Externalizable` cho phép class tự định nghĩa cách đọc dữ liệu; logic này cần được xem xét đặc biệt.
- `readObject` có thể thực thi code trong quá trình khôi phục.
- `readResolve` có thể thay object được trả về bằng object khác.
- Object graph có thể chứa nhiều class phụ thuộc lẫn nhau, không chỉ class root.

Không nhận byte stream Java serialization tùy ý từ Internet hoặc người dùng rồi hy vọng filter sẽ làm mọi thứ an toàn. Với dữ liệu không tin cậy, ưu tiên định dạng có schema và parser được thiết kế cho input không tin cậy, chẳng hạn JSON/CBOR/Protocol Buffers với validation rõ ràng, hoặc một định dạng khác phù hợp hệ thống.

## 11. Ví dụ tổng hợp: filter và validation là hai bước khác nhau

Ví dụ sau dùng một DTO nhỏ để thể hiện rõ filter chỉ cho phép class và giới hạn tài nguyên, còn validator kiểm tra nội dung.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class Main {
    static final class UserProfile implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String username;
        private final int age;
        private final String role;

        UserProfile(String username, int age, String role) {
            this.username = username;
            this.age = age;
            this.role = role;
        }

        String username() { return username; }
        int age() { return age; }
        String role() { return role; }
    }

    static ObjectInputFilter filter() {
        return info -> {
            if (info.depth() > 5
                    || info.references() > 50
                    || info.streamBytes() > 16_384
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > 100)) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }
            if (type == UserProfile.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }
            return ObjectInputFilter.Status.REJECTED;
        };
    }

    static void validate(UserProfile profile)
            throws InvalidObjectException {
        if (profile.username() == null
                || profile.username().isBlank()
                || profile.username().length() > 40) {
            throw new InvalidObjectException("Invalid username");
        }
        if (profile.age() < 0 || profile.age() > 130) {
            throw new InvalidObjectException("Invalid age");
        }
        if (!"USER".equals(profile.role())
                && !"EDITOR".equals(profile.role())) {
            throw new InvalidObjectException("Invalid role");
        }
    }

    static byte[] serialize(UserProfile profile) throws IOException {
        try (var bytes = new ByteArrayOutputStream();
             var output = new ObjectOutputStream(bytes)) {
            output.writeObject(profile);
            output.flush();
            return bytes.toByteArray();
        }
    }

    static UserProfile deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (var input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            input.setObjectInputFilter(filter());

            Object value = input.readObject();
            if (!(value instanceof UserProfile profile)) {
                throw new InvalidObjectException("Unexpected root type");
            }

            // Đây là kiểm tra nội dung; filter không thực hiện bước này.
            validate(profile);
            return profile;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = serialize(
                new UserProfile("linh", 28, "USER"));
        UserProfile profile = deserialize(valid);
        System.out.println(profile.username()); // linh

        byte[] invalidContent = serialize(
                new UserProfile("linh", -5, "USER"));
        try {
            deserialize(invalidContent);
        } catch (InvalidObjectException ex) {
            System.out.println(ex.getMessage()); // Invalid age
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 Main.java
java Main
~~~

Kết quả:

~~~text
linh
Invalid age
~~~

Điều cần quan sát:

1. Cả hai payload đều chứa class `UserProfile` được allowlist, và đều nhỏ hơn giới hạn tài nguyên.
2. Filter không biết `age` là âm hay dương; nó không đọc giá trị field để đánh giá nghiệp vụ.
3. Object có age âm vẫn được khôi phục, sau đó validator từ chối.
4. Nếu class graph chứa class không được allow, filter có thể từ chối ngay trong quá trình đọc.

Ví dụ chỉ dùng DTO tin cậy và minh họa ranh giới giữa hai loại kiểm tra. Nó không chứng minh native serialization an toàn với dữ liệu tùy ý.

## 12. Giới hạn của từng loại kiểm tra

| Yêu cầu | ObjectInputFilter | Validator/domain layer |
|---|---|---|
| Từ chối class không nằm trong allowlist | Có | Có thể kiểm tra kiểu root, nhưng quá muộn cho một số side effect trong quá trình deserialize |
| Giới hạn độ sâu object graph | Có | Có thể kiểm tra cấu trúc sau khi dựng, nhưng không ngăn chi phí đã phát sinh |
| Giới hạn số reference/byte | Có | Không thay thế giới hạn đọc stream |
| Giới hạn độ dài array | Có | Có thể kiểm tra kích thước collection/array sau khi đọc |
| Kiểm tra chuỗi không rỗng | Không | Có |
| Kiểm tra tuổi trong khoảng | Không | Có |
| Kiểm tra quan hệ giữa hai field | Không | Có |
| Kiểm tra schema/version nghiệp vụ | Không | Có |
| Kiểm tra quyền của người gửi | Không | Authorization layer |
| Ngăn mọi side effect từ custom serialization code | Không | Validation sau đọc cũng không thể đảo ngược side effect đã xảy ra |

Không có một lớp kiểm tra đơn lẻ nào thay thế tất cả lớp còn lại. Thiết kế an toàn cần giới hạn byte đầu vào, filter class/resource, validation nội dung và authorization phù hợp.

## 13. Những lỗi thường gặp

### 13.1. Nghĩ allowlist class đồng nghĩa payload hợp lệ

Một object thuộc class được phép vẫn có thể có field sai. Ví dụ `age = -5` vẫn là một instance của `UserProfile`.

**Cách xử lý:** kiểm tra field và invariant sau khi đọc hoặc trong custom `readObject` phù hợp.

### 13.2. Dùng maxbytes để thay thế mọi giới hạn

Payload nhỏ vẫn có thể chứa giá trị nghiệp vụ sai hoặc kích hoạt logic không mong muốn trong class được phép. Ngược lại, payload hợp lệ có thể vượt giới hạn byte nếu cấu hình quá thấp.

**Cách xử lý:** đặt từng giới hạn theo mục tiêu: bytes, depth, references, array length và class.

### 13.3. Nghĩ maxarray giới hạn số phần tử của mọi collection

`arrayLength` chỉ cung cấp độ dài array đang được xét. Không phải mọi collection đều được biểu diễn như một array serialization trực tiếp.

**Cách xử lý:** kiểm tra size collection sau khi đọc và giới hạn resource tổng thể trong filter.

### 13.4. Để filter trả UNDECIDED cho mọi class

`UNDECIDED` không phải là từ chối. Nếu không có filter khác từ chối, stream có thể tiếp tục theo chính sách tổng thể.

**Cách xử lý:** dùng allowlist rõ ràng và trả `REJECTED` cho class không được chấp nhận.

### 13.5. Cho phép cả package rộng mà không cần thiết

Pattern như `com.example.**` có thể cho phép nhiều class hơn object graph thực sự cần.

**Cách xử lý:** liệt kê package/class tối thiểu và cập nhật khi schema thay đổi.

### 13.6. Nghĩ validation sau readObject ngăn custom code chạy

Custom serialization method có thể đã chạy trước khi caller nhận object. Validator không hoàn tác side effect.

**Cách xử lý:** không cho phép class không tin cậy; ưu tiên định dạng dữ liệu không kích hoạt cơ chế native object deserialization cho input không tin cậy.

### 13.7. Dùng filter như sandbox

Filter không cô lập quyền file, mạng, thread, reflection hoặc native code của class được phép.

**Cách xử lý:** chỉ deserialize class tin cậy và dùng cơ chế cô lập phù hợp nếu phải chạy code không tin cậy.

## 14. Bài tập thực hành

### Bài 1 — Phân biệt metadata và nội dung

Một payload chứa `UserProfile(username=" ", age=-2, role="ROOT")`. Filter allow class `UserProfile` và giới hạn depth/bytes. Hãy liệt kê kiểm tra nào filter có thể thực hiện và kiểm tra nào phải thuộc validator.

**Gợi ý:** class và resource metadata thuộc filter; username, age, role và quyền sử dụng role thuộc các tầng sau.

### Bài 2 — Bổ sung giới hạn tài nguyên

Viết filter từ chối khi:

- Depth lớn hơn 8.
- References lớn hơn 500.
- Stream bytes lớn hơn 256 KiB.
- Array dài hơn 4096.

Sau đó thêm allowlist chỉ cho phép hai class DTO cụ thể.

### Bài 3 — Phân biệt collection size và array length

Một `ArrayList` có 50.000 phần tử. Giải thích vì sao `maxarray=1000` không phải hợp đồng tổng quát nói rằng mọi List chỉ được có 1000 phần tử. Đề xuất kiểm tra size sau khi deserialize và giới hạn references/bytes trong lúc đọc.

### Bài 4 — Kiểm tra invariant

Viết class `Booking` có `startDate` và `endDate`. Filter cho phép class đó. Bổ sung validation để từ chối khi ngày kết thúc trước ngày bắt đầu.

### Bài 5 — Custom readObject

Thêm `readObject` vào DTO để kiểm tra field bắt buộc sau `defaultReadObject` và ném `InvalidObjectException` nếu sai. Giải thích vì sao cơ chế này bảo vệ invariant của lớp nhưng không phải sandbox cho các class khác trong graph.

### Bài 6 — Thiết kế ranh giới dữ liệu

Một dịch vụ nhận byte stream serialization từ khách hàng bên ngoài. Hãy đề xuất thiết kế thay thế bằng DTO/schema rõ ràng và parser cho dữ liệu không tin cậy. Nêu vai trò còn lại của ObjectInputFilter nếu hệ thống vẫn phải đọc một stream Java serialization nội bộ.

## 15. Tiêu chí hoàn thành

Người học nắm vững bài khi có thể:

1. Mô tả được ObjectInputFilter kiểm tra class và metadata cấu trúc/tài nguyên trong quá trình deserialization.
2. Giải thích ý nghĩa `serialClass`, `arrayLength`, `depth`, `references` và `streamBytes`.
3. Viết filter với allowlist và các giới hạn phù hợp.
4. Phân biệt `ALLOWED`, `REJECTED` và `UNDECIDED`.
5. Nêu rõ filter không đọc hoặc xác thực giá trị field, quan hệ giữa field, schema, nghiệp vụ hay quyền truy cập.
6. Viết validator sau khi đọc và/hoặc invariant check trong `readObject` phù hợp.
7. Giải thích vì sao custom serialization code và gadget chain vẫn là rủi ro.
8. Không coi filter là sandbox hoặc bảo đảm rằng native serialization an toàn với input không tin cậy.
9. Chọn định dạng có schema và parser phù hợp cho dữ liệu trao đổi không đáng tin cậy.

## 16. Tài liệu chính thức

- [Java SE 17 API — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): Filter, FilterInfo, Status và các metadata được cung cấp.
- [Java SE 17 API — `ObjectInputFilter.Config`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): cấu hình filter, pattern và filter factory.
- [Java SE 17 API — `ObjectInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): đọc object và gắn per-stream filter.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): mục tiêu và phạm vi của serialization filtering.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factory và chính sách filter theo context.
- [Java SE 17 API — `ObjectInputValidation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputValidation.html): callback xác thực object graph sau khi khôi phục.
- [Java SE 17 API — `InvalidObjectException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidObjectException.html): từ chối object có trạng thái không hợp lệ.

**Ghi nhớ:** ObjectInputFilter là hàng rào cho class và tài nguyên của object graph trong lúc giải tuần tự hóa. Nó không đọc thay validator các field, invariant, schema, quan hệ nghiệp vụ hoặc quyền truy cập. Hãy kết hợp allowlist và giới hạn tài nguyên với validation nội dung, authorization, và tránh native Java deserialization cho dữ liệu không đáng tin cậy khi có lựa chọn định dạng an toàn hơn.
