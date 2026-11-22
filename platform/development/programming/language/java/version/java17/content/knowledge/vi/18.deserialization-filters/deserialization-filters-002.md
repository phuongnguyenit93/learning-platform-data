# ObjectInputFilter và vai trò giới hạn đồ thị đối tượng

Java serialization có thể khôi phục một đối tượng cùng các đối tượng mà nó tham chiếu từ một luồng byte. Vì quá trình này tạo ra cả một **đồ thị đối tượng (object graph)**, dữ liệu đầu vào có thể chứa nhiều lớp, mảng lớn, tham chiếu lồng sâu hoặc cấu trúc tốn nhiều tài nguyên. Nếu ứng dụng deserialize dữ liệu không đáng tin cậy mà không có giới hạn, nó có thể tạo đối tượng ngoài dự kiến, tiêu thụ quá nhiều bộ nhớ hoặc CPU, hoặc kích hoạt hành vi nguy hiểm thông qua chuỗi lớp trong thư viện.

Từ Java 9, API **`ObjectInputFilter`** cho phép kiểm soát lớp nào được deserialize và giới hạn đặc tính của đồ thị. Java 17 tiếp tục hỗ trợ cơ chế này và bổ sung **filter factory theo ngữ cảnh** theo JEP 415, giúp ứng dụng áp dụng chính sách phù hợp với từng luồng hoặc từng thành phần.

Bài này tập trung vào API còn áp dụng trong Java 17: cách hiểu đồ thị đối tượng, giới hạn độ sâu/số tham chiếu/dung lượng/độ dài mảng, xây dựng allowlist, cài filter toàn JVM hoặc theo từng stream, và vai trò của filter factory. `ObjectInputFilter` là lớp bảo vệ quan trọng cho Java native serialization; nó không thay thế validation nghiệp vụ và không biến serialization thành định dạng an toàn để nhận dữ liệu tùy ý.

## 1. Vì sao cần lọc khi deserialize?

Java serialization không chỉ đọc một object độc lập. Khi một object chứa tham chiếu đến object khác, `ObjectInputStream` có thể tiếp tục khôi phục các đối tượng phụ thuộc để tái tạo cấu trúc ban đầu.

Ví dụ:

~~~java
class Order implements Serializable {
    Customer customer;
    List<Item> items;
}
~~~

Khi deserialize một `Order`, luồng có thể khôi phục cả `Customer`, danh sách `items`, từng `Item`, chuỗi, mảng và các đối tượng được tham chiếu tiếp theo.

Có thể hình dung:

~~~text
Order
 ├── Customer
 │    └── Address
 └── List<Item>
      ├── Item
      │    └── Product
      └── Item
           └── Product
~~~

Cấu trúc này là một **đồ thị**, vì nhiều trường có thể cùng trỏ đến một object và có thể tồn tại chu trình tham chiếu. Lọc riêng lớp gốc `Order` chưa đủ để kiểm soát các lớp được tạo sâu bên trong.

Một luồng byte được tạo có chủ đích có thể chứa:

- Một lớp không nằm trong mô hình dữ liệu mà ứng dụng dự kiến.
- Đồ thị có độ sâu rất lớn.
- Số lượng object/reference rất lớn.
- Mảng có độ dài quá lớn.
- Dữ liệu có kích thước lớn khiến việc đọc và tạo object tốn bộ nhớ.
- Chuỗi lớp trong thư viện có hành vi không mong muốn khi được khôi phục.

`ObjectInputFilter` cho phép từ chối quá trình deserialize ngay khi các lớp hoặc giới hạn của đồ thị không đáp ứng chính sách.

## 2. ObjectInputFilter là gì?

`ObjectInputFilter` là một functional interface trong package `java.io`:

~~~java
@FunctionalInterface
public interface ObjectInputFilter {
    Status checkInput(FilterInfo filterInfo);
}
~~~

Một filter nhận `FilterInfo` mô tả đối tượng hoặc trạng thái đang được kiểm tra, rồi trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `ALLOWED` | Filter này chấp nhận thông tin đang được kiểm tra |
| `REJECTED` | Từ chối; quá trình deserialize bị dừng |
| `UNDECIDED` | Filter này chưa đưa ra quyết định |

Khi filter trả về `REJECTED`, `ObjectInputStream` từ chối dữ liệu và thường ném `InvalidClassException` với thông tin filter đã từ chối.

`UNDECIDED` không đồng nghĩa với từ chối. Nó cho phép chính sách khác trong cơ chế kết hợp filter đưa ra quyết định; nếu không có filter nào từ chối, việc deserialize có thể tiếp tục. Vì vậy, một allowlist cần có nhánh từ chối rõ ràng cho các lớp không được chấp nhận, thay vì trả `UNDECIDED` cho mọi lớp lạ.

## 3. FilterInfo mô tả những gì?

`ObjectInputFilter.FilterInfo` cung cấp năm thông tin quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `serialClass()` | Lớp đang được kiểm tra; có thể là `null` trong một số lần kiểm tra không gắn với lớp mới |
| `arrayLength()` | Độ dài mảng; giá trị âm nếu lần kiểm tra không liên quan mảng |
| `depth()` | Độ sâu hiện tại của đồ thị deserialize |
| `references()` | Số lượng tham chiếu đã được xử lý trong luồng |
| `streamBytes()` | Số byte đã tiêu thụ từ luồng serialization |

Các trường này giúp filter kiểm tra cả **loại dữ liệu** lẫn **quy mô cấu trúc**.

### 3.1. Độ sâu đồ thị — depth

`depth()` cho biết độ sâu hiện tại của quá trình khôi phục đồ thị. Đồ thị lồng quá sâu có thể làm tăng chi phí xử lý, gây áp lực bộ nhớ hoặc khiến logic ứng dụng gặp vấn đề.

Ví dụ một cấu trúc lồng:

~~~text
Node
 └── Node
      └── Node
           └── Node
                ...
~~~

Giới hạn depth ngăn dữ liệu đầu vào tạo cấu trúc lồng sâu vượt quá mức ứng dụng chấp nhận.

### 3.2. Số lượng tham chiếu — references

`references()` phản ánh số lượng object reference đã được xử lý. Một đồ thị có thể nông nhưng chứa rất nhiều phần tử hoặc object liên kết. Chỉ giới hạn depth không đủ để kiểm soát trường hợp này.

Ví dụ một danh sách có hàng trăm nghìn phần tử có thể chỉ có vài tầng lồng nhưng vẫn tạo ra số lượng tham chiếu lớn.

### 3.3. Số byte đã đọc — streamBytes

`streamBytes()` cho biết số byte đã tiêu thụ từ luồng. Đây là giới hạn hữu ích để kiểm soát tổng lượng dữ liệu serialization mà ứng dụng xử lý.

Nó không thay thế giới hạn kích thước request ở tầng HTTP hoặc giới hạn file ở tầng lưu trữ. Nên kiểm soát cả kích thước đầu vào trước khi tạo `ObjectInputStream` và lượng byte mà filter quan sát trong quá trình deserialize.

### 3.4. Độ dài mảng — arrayLength

`arrayLength()` cho phép giới hạn mảng lớn. Mảng có thể chứa rất nhiều phần tử trong một object duy nhất, vì thế chỉ đếm references hoặc depth chưa đủ.

Ví dụ:

~~~java
byte[] payload = new byte[100_000_000];
~~~

Một mảng byte rất lớn có thể gây áp lực heap dù đồ thị chỉ có một tầng. Filter nên đặt giới hạn array length theo kích thước dữ liệu hợp lệ của ứng dụng.

### 3.5. Lớp đang deserialize — serialClass

`serialClass()` cho phép kiểm tra lớp thực tế đang được khôi phục. Filter có thể cho phép một tập lớp xác định, từ chối lớp ngoài tập đó, hoặc chỉ áp dụng giới hạn cấu trúc mà không quyết định theo lớp.

Giá trị `null` không có nghĩa dữ liệu chắc chắn an toàn. Vẫn phải kiểm tra `depth`, `references`, `streamBytes` và các giới hạn khác trước khi xử lý trường hợp này.

## 4. Giới hạn đồ thị theo nguyên tắc defense in depth

Một chính sách tốt thường kết hợp nhiều giới hạn:

- **Allowlist lớp:** chỉ cho phép lớp mà hợp đồng dữ liệu thực sự cần.
- **Maximum depth:** giới hạn cấu trúc lồng.
- **Maximum references:** giới hạn số lượng object/reference.
- **Maximum bytes:** giới hạn dữ liệu đã đọc.
- **Maximum array length:** giới hạn mảng lớn.

Ví dụ, một dịch vụ chỉ nhận một DTO nhỏ có thể đặt chính sách:

| Giới hạn | Giá trị minh họa | Mục đích |
| --- | ---: | --- |
| `maxdepth` | 10 | Không cho đồ thị lồng quá sâu |
| `maxrefs` | 1.000 | Hạn chế số tham chiếu |
| `maxbytes` | 1.048.576 | Giới hạn khoảng 1 MiB dữ liệu serialization |
| `maxarray` | 100.000 | Giới hạn chiều dài mảng |

Các con số trên chỉ là ví dụ. Giới hạn thực tế phải xuất phát từ kích thước payload và cấu trúc hợp lệ của ứng dụng. Một dịch vụ xử lý ảnh, một ứng dụng nhận DTO nhỏ và một công cụ import dữ liệu lớn sẽ có nhu cầu khác nhau.

Không nên đặt giới hạn quá rộng chỉ để dữ liệu hiện tại luôn được chấp nhận. Ngược lại, giới hạn quá thấp có thể làm từ chối payload hợp lệ. Hãy xác định hợp đồng dữ liệu và đo kích thước thực tế trước khi triển khai.

## 5. Viết filter theo lớp và giới hạn

Ví dụ dưới đây chỉ cho phép một lớp `User` cùng `String`, đồng thời giới hạn quy mô đồ thị:

~~~java
import java.io.ObjectInputFilter;

public final class UserFilter {
    private static final long MAX_DEPTH = 10;
    private static final long MAX_REFERENCES = 1_000;
    private static final long MAX_BYTES = 1_048_576;
    private static final long MAX_ARRAY_LENGTH = 100_000;

    private UserFilter() {
    }

    public static ObjectInputFilter create() {
        return info -> {
            if (info.depth() > MAX_DEPTH
                    || info.references() > MAX_REFERENCES
                    || info.streamBytes() > MAX_BYTES
                    || info.arrayLength() > MAX_ARRAY_LENGTH) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == User.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }
}
~~~

Điểm quan trọng:

1. Kiểm tra giới hạn cấu trúc trước khi quyết định theo lớp.
2. Cho phép chính xác những lớp cần thiết.
3. Từ chối các lớp khác bằng `REJECTED`.
4. Không dùng `UNDECIDED` làm nhánh mặc định cho mọi lớp không biết.

Trong ví dụ, `User` có thể chứa một trường `String`; nếu mô hình thực tế chứa thêm lớp hoặc mảng, phải bổ sung chúng một cách có chủ đích và giới hạn kích thước tương ứng.

Filter nên nhanh, có thể dự đoán và không có side effect. Không thực hiện truy vấn mạng, đọc database hoặc thao tác nghiệp vụ trong `checkInput`, vì filter có thể được gọi nhiều lần trong quá trình deserialize.

## 6. Cài filter theo từng ObjectInputStream

Khi một thành phần chỉ deserialize một loại payload, filter theo từng stream giúp áp dụng chính sách gần nơi đọc dữ liệu.

~~~java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (ObjectInputStream input =
             new ObjectInputStream(Files.newInputStream(path))) {

    input.setObjectInputFilter(UserFilter.create());

    Object value = input.readObject();

    if (!(value instanceof User user)) {
        throw new InvalidObjectException("Payload không phải User");
    }

    System.out.println(user.name());
}
~~~

`setObjectInputFilter(...)` cần được gọi trước khi bắt đầu đọc object từ stream. Filter của stream được cấu hình một lần theo hợp đồng của API; không thiết kế code để thay đổi tùy tiện sau khi quá trình deserialize đã bắt đầu.

Lớp `User` trong ví dụ cần triển khai `Serializable`. `InvalidObjectException` ở phần kiểm tra kiểu là ví dụ về validation sau deserialize; filter và validation có hai vai trò khác nhau.

### 6.1. Ví dụ hoàn chỉnh có thể chạy

Tạo file `UserFilterDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class UserFilterDemo {

    private UserFilterDemo() {
    }

    private static final class User implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String name;
        private final int age;

        User(String name, int age) {
            this.name = name;
            this.age = age;
        }

        String name() {
            return name;
        }

        int age() {
            return age;
        }
    }

    private static ObjectInputFilter userFilter() {
        return info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000
                    || info.arrayLength() > 10_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == User.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    private static byte[] serialize(Object value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream output =
                     new ObjectOutputStream(bytes)) {
            output.writeObject(value);
        }

        return bytes.toByteArray();
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        byte[] data = serialize(new User("An", 28));

        try (ObjectInputStream input =
                     new ObjectInputStream(
                             new ByteArrayInputStream(data))) {

            input.setObjectInputFilter(userFilter());

            Object value = input.readObject();

            if (!(value instanceof User user)) {
                throw new InvalidObjectException(
                        "Expected a User object");
            }

            System.out.println(user.name());
            System.out.println(user.age());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 UserFilterDemo.java
java UserFilterDemo
~~~

Kết quả:

~~~text
An
28
~~~

Đây là ví dụ minh họa một allowlist nhỏ. Trong ứng dụng thật, hãy đặt các lớp được phép theo hợp đồng dữ liệu thực tế, không mở rộng allowlist bằng wildcard rộng chỉ để chương trình chạy được.

## 7. Filter theo pattern bằng Config.createFilter

Nếu chính sách có thể mô tả bằng tên lớp và giới hạn số học, `ObjectInputFilter.Config.createFilter(String)` tạo filter từ chuỗi pattern.

Các thành phần giới hạn phổ biến:

| Pattern | Giới hạn |
| --- | --- |
| `maxdepth=n` | Độ sâu tối đa |
| `maxrefs=n` | Số tham chiếu tối đa |
| `maxbytes=n` | Số byte tối đa đã đọc |
| `maxarray=n` | Độ dài mảng tối đa |

Pattern lớp có thể cho phép hoặc từ chối lớp cụ thể, package hoặc nhóm lớp theo cú pháp filter. Một số dạng thường gặp:

| Pattern | Ý nghĩa |
| --- | --- |
| `com.example.dto.User` | Lớp cụ thể |
| `com.example.dto.*` | Các lớp trực tiếp trong package đó |
| `com.example.dto.**` | Các lớp trong package và các package con |
| `!com.example.internal.BadType` | Từ chối lớp được chỉ định |
| `!*` | Từ chối các lớp không được một pattern cho phép trước đó |

Có thể thêm tên module trước tên lớp theo cú pháp `module/classname` khi cần giới hạn theo module.

Ví dụ tạo allowlist:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;"
        + "maxrefs=1000;"
        + "maxbytes=1048576;"
        + "maxarray=100000;"
        + "com.example.dto.**;"
        + "java.base/java.lang.String;"
        + "!*");
~~~

Các pattern được xét theo thứ tự; pattern lớp phù hợp đầu tiên quyết định `ALLOWED` hoặc `REJECTED`. Các giới hạn số học vẫn được áp dụng. Nếu không có pattern lớp nào phù hợp, filter có thể trả `UNDECIDED`.

`!*` ở cuối tạo chính sách từ chối mặc định cho các lớp chưa được cho phép. Đây là cách thể hiện fail-closed dễ đọc hơn so với việc để các lớp không biết ở trạng thái chưa quyết định.

### 7.1. Dùng pattern filter theo từng stream

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1048576;"
        + "maxarray=100000;com.example.dto.**;!*");

try (ObjectInputStream input =
             new ObjectInputStream(Files.newInputStream(path))) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
}
~~~

Nếu dữ liệu chứa `ArrayList`, `HashMap`, mảng hoặc kiểu hỗ trợ khác, phải xem xét các lớp thực tế mà serialization sử dụng và đưa vào allowlist khi cần. Không nên cho phép toàn bộ `java.util.**` nếu chỉ cần một vài kiểu cụ thể.

## 8. Cài filter toàn JVM

Nếu ứng dụng có nhiều điểm deserialize, có thể thiết lập filter toàn JVM để tạo chính sách nền.

### 8.1. Cấu hình bằng system property

Có thể cấu hình pattern qua thuộc tính `jdk.serialFilter` khi khởi chạy JVM:

~~~bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000;com.example.dto.**;java.base/java.lang.String;!*" -jar application.jar
~~~

Đây là chính sách ví dụ. Phải điều chỉnh allowlist và giới hạn theo payload thực tế. Đặt property khi JVM khởi động giúp chính sách có hiệu lực từ sớm, trước khi các thành phần bắt đầu deserialize.

### 8.2. Cấu hình bằng API

Có thể cài filter JVM-wide bằng `ObjectInputFilter.Config.setSerialFilter(...)`:

~~~java
ObjectInputFilter.Config.setSerialFilter(
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=10000;maxbytes=5000000;"
                + "maxarray=100000;com.example.dto.**;!*"));
~~~

Filter toàn JVM chỉ được thiết lập một lần theo hợp đồng của API. Nếu đã cấu hình bằng system property hoặc thành phần khác đã cài filter, việc gọi lại có thể thất bại. Vì vậy, hãy đặt quyền sở hữu cấu hình ở bootstrap của ứng dụng và tránh để nhiều thư viện tự tranh quyền cài global filter.

### 8.3. Global filter và per-stream filter

| Loại filter | Phạm vi | Khi phù hợp |
| --- | --- | --- |
| JVM-wide filter | Là chính sách nền cho các `ObjectInputStream` trong JVM | Ứng dụng cần một baseline thống nhất |
| Per-stream filter | Một stream cụ thể | Endpoint hoặc thành phần có payload và allowlist riêng |
| Filter factory | Quyết định cách tạo/kết hợp filter theo ngữ cảnh | Ứng dụng nhiều thành phần cần chính sách context-specific |

Không nên xem per-stream filter là lý do bỏ qua global policy. Một chính sách toàn JVM giúp có lớp bảo vệ nền; filter riêng có thể bổ sung giới hạn cụ thể cho từng luồng.

## 9. Filter factory theo ngữ cảnh trong Java 17

Java 17 bổ sung **JEP 415 – Context-Specific Deserialization Filters**. Trước thay đổi này, một filter toàn JVM và filter riêng của stream có thể khó biểu đạt chính sách khác nhau cho các ngữ cảnh độc lập trong cùng tiến trình.

Filter factory cho phép ứng dụng quyết định filter nào được gắn với một `ObjectInputStream`, dựa trên filter hiện có và filter được yêu cầu. Factory có thể dùng thông tin ngữ cảnh do ứng dụng quản lý, chẳng hạn loại endpoint, thành phần gọi hoặc chính sách của từng tenant.

API cấu hình:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory(
        (currentFilter, requestedFilter) -> {
            // Chọn hoặc kết hợp chính sách theo ngữ cảnh ứng dụng.
            // Trả về filter cuối cùng dùng cho ObjectInputStream.
            return combineAccordingToPolicy(
                    currentFilter,
                    requestedFilter);
        });
~~~

`combineAccordingToPolicy(...)` ở đây là hàm do ứng dụng thiết kế, không phải API có sẵn. Ý tưởng quan trọng là factory nhận hai filter và trả filter cuối cùng. Factory được gọi khi stream được tạo và khi filter riêng của stream được cài đặt.

### 9.1. Vì sao cần filter factory?

Giả sử cùng một JVM chạy hai thành phần:

- Thành phần A chỉ deserialize `UserProfile`.
- Thành phần B chỉ deserialize `Invoice`.
- Cả hai đều phải tuân thủ giới hạn tài nguyên toàn JVM.

Một factory có thể chọn allowlist khác nhau theo ngữ cảnh, đồng thời giữ giới hạn nền. Điều này tránh phải mở rộng một allowlist toàn cục quá rộng chỉ để phục vụ nhiều kiểu payload không liên quan.

### 9.2. Cấu hình factory

Có thể cài factory qua API `ObjectInputFilter.Config.setSerialFilterFactory(...)` hoặc cấu hình class factory theo cơ chế thuộc tính `jdk.serialFilterFactory` của runtime.

Factory là một chính sách ở cấp ứng dụng. Khi viết factory tùy chỉnh, cần:

- Xác định rõ filter nền và filter theo ngữ cảnh.
- Bảo đảm quyết định `REJECTED` không bị biến thành chấp nhận.
- Không bỏ qua giới hạn tài nguyên của filter nền.
- Không dựa vào thông tin ngữ cảnh có thể bị giả mạo từ payload.
- Có test cho từng ngữ cảnh và cho trường hợp thiếu context.

Default factory của JDK cung cấp cách kết hợp filter toàn JVM và filter theo stream. Khi thay bằng factory riêng, ứng dụng chịu trách nhiệm bảo toàn chính sách mà nó cần.

## 10. Allowlist tốt hơn denylist rộng

Một denylist chỉ liệt kê các lớp nguy hiểm đã biết. Cách này dễ bỏ sót lớp mới hoặc gadget chain phát sinh từ dependency khác.

Ví dụ chính sách chỉ từ chối một lớp:

~~~java
if (type == SomeKnownDangerousType.class) {
    return ObjectInputFilter.Status.REJECTED;
}
return ObjectInputFilter.Status.ALLOWED;
~~~

Cách này cho phép mọi lớp còn lại, kể cả lớp ứng dụng chưa từng dự kiến deserialize.

Với payload có schema rõ, nên ưu tiên allowlist:

~~~java
if (type == User.class
        || type == String.class
        || type == Address.class) {
    return ObjectInputFilter.Status.ALLOWED;
}
return ObjectInputFilter.Status.REJECTED;
~~~

Allowlist chỉ cho phép các lớp cần thiết. Khi thêm một loại dữ liệu mới, nhóm phát triển phải chủ động cập nhật hợp đồng và filter.

Không có allowlist chung đúng cho mọi ứng dụng. Nếu mô hình chứa collection, map, enum hoặc mảng, hãy xác định đúng implementation và kiểu phần tử được serialization ghi ra; tránh cho phép wildcard rộng để khắc phục lỗi thiếu lớp.

## 11. Filter không thay thế validation dữ liệu

`ObjectInputFilter` kiểm soát lớp và đặc tính cấu trúc trong quá trình deserialize. Nó không tự xác nhận mọi giá trị field là hợp lệ theo nghiệp vụ.

Ví dụ một object có thể thuộc lớp `User` được allowlist nhưng vẫn chứa:

- Tên rỗng hoặc quá dài.
- Tuổi âm.
- ID không tồn tại.
- Trạng thái không hợp lệ.
- Quan hệ giữa các field không nhất quán.

Sau khi deserialize, ứng dụng vẫn cần validation:

~~~java
if (user.name() == null || user.name().isBlank()) {
    throw new InvalidObjectException("Tên không hợp lệ");
}

if (user.age() < 0 || user.age() > 130) {
    throw new InvalidObjectException("Tuổi ngoài miền cho phép");
}
~~~

Filter cũng không xác thực chữ ký, nguồn gốc hay tính toàn vẹn của dữ liệu. Nếu ứng dụng cần xác nhận nguồn gửi, phải dùng cơ chế xác thực và bảo vệ toàn vẹn phù hợp ở tầng giao thức.

## 12. ObjectInputFilter không phải sandbox hoàn chỉnh

Filter là một lớp phòng vệ quan trọng, nhưng không nên xem Java native deserialization là cách an toàn để nhận dữ liệu tùy ý từ Internet.

Các giới hạn cần hiểu:

- Filter áp dụng cho quá trình Java object deserialization, không phải bộ lọc tổng quát cho JSON, XML hoặc mọi parser.
- Filter không thay thế giới hạn kích thước request/file trước khi tạo `ObjectInputStream`.
- Filter không kiểm tra toàn bộ ý nghĩa nghiệp vụ của field.
- Filter không bảo đảm dữ liệu được xác thực hoặc không bị sửa đổi.
- Allowlist quá rộng vẫn có thể cho phép một lớp có hành vi nguy hiểm hoặc một chuỗi object không mong muốn.
- Các giới hạn tài nguyên cần phù hợp với hệ thống; một giá trị rất lớn có thể vẫn gây áp lực đáng kể.

Với giao thức mới hoặc dữ liệu không đáng tin cậy, nên ưu tiên định dạng dữ liệu có schema rõ ràng và parser được thiết kế cho đầu vào không tin cậy. Nếu phải duy trì Java serialization vì hợp đồng tương thích, dùng filter nghiêm ngặt, allowlist nhỏ và validation sau deserialize.

## 13. Đặt filter đúng thời điểm và đúng nơi

Một số nguyên tắc triển khai quan trọng:

1. **Cài global filter sớm:** cấu hình trước khi các thư viện hoặc module khác tạo luồng deserialize.
2. **Cài per-stream filter trước `readObject()`:** không chờ đến khi object đầu tiên đã được khôi phục.
3. **Không để nhiều thành phần tự cài global filter:** API global có giới hạn thiết lập một lần.
4. **Dùng filter factory khi cần nhiều context:** quản lý chính sách tập trung và rõ ownership.
5. **Giới hạn input trước deserialization:** kiểm soát request size, file size và nguồn dữ liệu.
6. **Kiểm tra lớp và giới hạn đồ thị:** không chỉ kiểm tra lớp gốc.
7. **Validate object sau deserialize:** kiểm tra giá trị field, quyền và quy tắc nghiệp vụ.

Nếu một thư viện tự tạo `ObjectInputStream` bên trong, ứng dụng cần biết điểm đó để bảo đảm global filter hoặc filter factory áp dụng được. Không thể giả định rằng chỉ những stream do code của mình tạo mới cần bảo vệ.

## 14. Xử lý khi filter từ chối dữ liệu

Khi filter trả `REJECTED`, quá trình đọc object bị từ chối. Ví dụ:

~~~java
try (ObjectInputStream input =
             new ObjectInputStream(Files.newInputStream(path))) {

    input.setObjectInputFilter(UserFilter.create());

    Object value = input.readObject();

} catch (InvalidClassException ex) {
    System.err.println("Object graph bị filter từ chối: "
            + ex.getMessage());
}
~~~

Trong hệ thống thật, nên phân biệt:

- Payload chứa lớp không nằm trong allowlist.
- Đồ thị vượt giới hạn depth/reference/byte/array.
- Dữ liệu serialization hỏng hoặc không tương thích.
- Lỗi I/O khi đọc nguồn.

Không nên bắt `InvalidClassException` rồi bỏ qua như thể dữ liệu đã hợp lệ. Ghi log ở mức phù hợp, tránh ghi toàn bộ payload hoặc dữ liệu nhạy cảm.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Chỉ lọc lớp gốc nhưng vẫn tạo object lạ ở bên trong | Đồ thị có nhiều lớp được tham chiếu | Lọc từng lớp được gặp trong quá trình deserialize |
| Đồ thị nông nhưng vẫn tốn heap lớn | Số references hoặc array length quá lớn | Kết hợp `maxrefs`, `maxarray`, `maxbytes` |
| Đồ thị lồng sâu làm xử lý tốn tài nguyên | Không giới hạn depth | Đặt `maxdepth` phù hợp |
| Lớp lạ vẫn được deserialize | Filter trả `UNDECIDED` thay vì từ chối mặc định | Dùng allowlist và trả `REJECTED` cho lớp không được phép |
| Payload hợp lệ bị từ chối | Allowlist thiếu kiểu phụ trợ hoặc giới hạn quá thấp | Xác định chính xác graph hợp lệ và cập nhật policy có kiểm soát |
| `setObjectInputFilter` báo lỗi trạng thái | Cài filter quá muộn hoặc cố cài nhiều lần | Cài một lần trước khi đọc object |
| Global filter không được cài | Thành phần khác đã cấu hình trước hoặc filter đã được thiết lập | Đặt ownership cấu hình tại bootstrap |
| Per-stream filter không đáp ứng chính sách chung | Chỉ cài filter riêng, bỏ qua baseline | Dùng global policy và factory để kết hợp có chủ đích |
| Dùng denylist nhưng bỏ sót lớp mới | Chỉ chặn một số lớp đã biết | Dùng allowlist nhỏ theo hợp đồng dữ liệu |
| Dữ liệu có lớp hợp lệ nhưng field sai | Filter không kiểm tra ngữ nghĩa nghiệp vụ | Validate object sau deserialize |
| Tin rằng filter bảo vệ JSON/XML | Filter chỉ áp dụng cho Java serialization | Dùng validation/schema và giới hạn riêng của parser tương ứng |

## 16. Bài tập thực hành

### Bài 1 — Quan sát FilterInfo

Tạo một lớp `Serializable` có một trường `String` và một mảng byte. Cài filter in ra `serialClass()`, `depth()`, `references()`, `streamBytes()` và `arrayLength()`. Quan sát thông tin thay đổi trong quá trình đọc.

### Bài 2 — Giới hạn độ sâu

Tạo một cấu trúc object lồng nhau nhiều tầng. Đặt `maxdepth` thấp để quan sát filter từ chối. Tăng giới hạn đến mức vừa đủ cho mô hình hợp lệ.

### Bài 3 — Giới hạn mảng và byte

Serialize một mảng byte nhỏ và một mảng lớn. Đặt `maxarray` và `maxbytes` khác nhau để thấy mỗi giới hạn kiểm soát một khía cạnh riêng.

### Bài 4 — Allowlist

Tạo payload chứa một lớp được cho phép và một lớp không có trong allowlist. Xác nhận payload thứ nhất đọc được và payload thứ hai bị từ chối.

### Bài 5 — Pattern filter

Dùng `ObjectInputFilter.Config.createFilter(...)` để cấu hình giới hạn và package DTO. Thử `!*` ở cuối để từ chối lớp chưa được cho phép. Giải thích thứ tự pattern ảnh hưởng quyết định như thế nào.

### Bài 6 — Global và per-stream

Cài một filter toàn JVM làm baseline, sau đó cài filter riêng cho một stream. Kiểm tra chính sách kết hợp và xác nhận filter riêng không vô tình bỏ qua giới hạn nền.

### Bài 7 — Filter factory

Thiết kế hai context giả định: một context đọc `UserProfile`, context còn lại đọc `Invoice`. Mô tả cách factory chọn allowlist tương ứng và giữ các giới hạn tài nguyên chung.

## 17. Nguyên tắc cần nhớ

- Java object deserialization khôi phục một **đồ thị đối tượng**, không chỉ một object gốc.
- `ObjectInputFilter` kiểm tra lớp và giới hạn cấu trúc trong quá trình deserialize.
- Dùng `depth`, `references`, `streamBytes` và `arrayLength` để kiểm soát nhiều dạng tiêu thụ tài nguyên.
- Ưu tiên allowlist lớp cần thiết và từ chối lớp ngoài hợp đồng.
- `UNDECIDED` không phải trạng thái từ chối; fail-closed cần có quyết định `REJECTED` rõ ràng.
- Có thể cài filter toàn JVM hoặc theo từng `ObjectInputStream`; cài trước khi đọc object.
- Java 17 có filter factory theo ngữ cảnh theo JEP 415 để lựa chọn/kết hợp chính sách cho từng luồng.
- Filter không thay thế giới hạn kích thước đầu vào, xác thực nguồn dữ liệu hoặc validation nghiệp vụ.
- Với dữ liệu không đáng tin cậy và giao thức mới, ưu tiên định dạng có schema rõ ràng; nếu phải dùng Java serialization, áp dụng filter nghiêm ngặt và kiểm thử chính sách.

Giới hạn đúng đồ thị đối tượng giúp giảm nguy cơ tạo lớp ngoài dự kiến và kiểm soát tài nguyên khi deserialize. Trong Java 17, kết hợp allowlist, giới hạn cấu trúc, filter toàn JVM và filter factory theo ngữ cảnh tạo ra một chính sách rõ ràng hơn cho các thành phần còn sử dụng Java serialization.
