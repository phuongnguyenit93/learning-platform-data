# Vai trò phòng vệ hiện hành của ObjectInputFilter

## 1. ObjectInputFilter giải quyết rủi ro nào?

Java Serialization có thể dựng lại một object graph từ byte stream bằng `ObjectInputStream`. Quá trình này có thể tạo instance, khôi phục quan hệ tham chiếu và chạy các hook như `readObject`, `readResolve` hoặc logic của lớp được deserialize. Vì vậy, nhận một luồng serialized từ bên ngoài tương đương với việc cho dữ liệu bên ngoài tham gia vào quá trình tạo object của ứng dụng.

`ObjectInputFilter` là cơ chế lọc được đưa vào Java 9 qua JEP 290. Filter được gọi trong lúc đọc object để quyết định:

- Lớp nào được phép xuất hiện trong object graph.
- Mảng có kích thước vượt giới hạn hay không.
- Object graph có quá sâu hay chứa quá nhiều reference hay không.
- Byte stream đã tiêu thụ có vượt ngân sách hay không.

Mục tiêu là thu hẹp tập lớp được deserialize theo đúng ngữ cảnh và giới hạn độ phức tạp của graph. Filter giúp tăng khả năng phòng vệ và độ bền của ứng dụng, nhưng không biến Java Serialization thành định dạng an toàn để nhận dữ liệu không tin cậy.

Nếu có thể, tránh deserialize dữ liệu không tin cậy. Ưu tiên định dạng dữ liệu có schema và parser phù hợp như JSON hoặc Protocol Buffers, sau đó xác thực dữ liệu trước khi sử dụng. Nếu vẫn cần Java Serialization, hãy dùng filter cụ thể cho từng luồng và kiểm tra nghiệp vụ sau khi deserialize.

## 2. Filter được gọi khi nào và kiểm tra được gì?

Một `ObjectInputFilter` có phương thức:

~~~java
ObjectInputFilter.Status checkInput(
        ObjectInputFilter.FilterInfo filterInfo);
~~~

`FilterInfo` cung cấp các thông tin sau:

| Phương thức | Ý nghĩa |
|---|---|
| `serialClass()` | Lớp đang được kiểm tra; có thể là `null` khi chỉ kiểm tra metrics/reference |
| `arrayLength()` | Độ dài mảng đang được tạo; `-1` nếu không phải mảng |
| `depth()` | Độ sâu hiện tại của object graph |
| `references()` | Số object/reference tích lũy đã đọc, bao gồm phần tử hiện tại |
| `streamBytes()` | Số byte stream đã tiêu thụ theo cách triển khai của ObjectInputStream |

Filter được gọi khi đọc object, class và array. Nó cũng có thể được gọi khi stream tham chiếu lại một object đã đọc để cập nhật metrics. Primitive và String được mã hóa trực tiếp trong stream không gọi class filter; do đó phải giới hạn tổng byte và tự xác thực giá trị String/primitive sau khi đọc.

Các giá trị metrics là snapshot trong quá trình đọc. `streamBytes()` là số byte đã tiêu thụ, không phải kích thước chính xác cuối cùng của toàn bộ stream. `depth()` bắt đầu từ 1 ở root object và tăng theo các lần đọc object lồng nhau.

Filter không tự xác thực nội dung field. Ví dụ, cho phép lớp `UserMessage` không có nghĩa là chuỗi `role` bên trong chỉ có thể là `"reader"` hoặc `"writer"`. Ứng dụng vẫn phải kiểm tra invariant, độ dài chuỗi, enum, quyền sở hữu và các ràng buộc nghiệp vụ sau khi đọc.

## 3. Ba trạng thái ALLOWED, REJECTED và UNDECIDED

Mỗi lần kiểm tra phải trả về một trong ba trạng thái:

| Status | Ý nghĩa |
|---|---|
| `ALLOWED` | Filter xác nhận class/graph hiện tại được phép |
| `REJECTED` | Filter từ chối; lần đọc hiện tại bị dừng |
| `UNDECIDED` | Filter không đưa ra kết luận cho thông tin này |

Điểm rất quan trọng: `UNDECIDED` không có nghĩa là từ chối. Nếu không có filter khác trả `REJECTED`, ObjectInputStream vẫn có thể tiếp tục deserialize. Một filter chỉ trả `UNDECIDED` cho mọi class không tạo ra allowlist.

Khi xây dựng allowlist, hãy trả `REJECTED` cho class không nằm trong tập cho phép. Với Java 17 trở lên, `ObjectInputFilter.rejectUndecidedClass(filter)` có thể chuyển kết quả undecided thành rejected đối với class, với các quy tắc đặc biệt cho primitive array và object array.

Nếu filter trả `REJECTED`, trả `null`, hoặc ném RuntimeException, thao tác `readObject()`/`readUnshared()` đang chạy sẽ thất bại bằng `InvalidClassException`. Hãy xử lý lỗi này như một stream không hợp lệ hoặc không được phép.

## 4. Xây allowlist theo object graph thực tế

Cách phòng vệ chủ động là xác định chính xác các kiểu dữ liệu mà một điểm deserialize cần nhận. Ví dụ, một endpoint chỉ nhận `Message` có thể cho phép đúng lớp đó và các kiểu array cần thiết; endpoint khác có thể có allowlist riêng.

Một filter theo lớp có thể viết như sau:

~~~java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == Message.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
~~~

Khi xây dựng allowlist, cần tính cả các lớp xuất hiện trong graph:

- Lớp gốc được ghi vào stream.
- Các lớp Serializable được tham chiếu qua field.
- Lớp cha Serializable và interface được ghi rõ trong stream.
- Các kiểu mảng được tạo trong quá trình khôi phục object graph.
- Các lớp proxy hoặc lớp thay thế do `readResolve`/`resolveObject` trả về nếu use case có sử dụng.

Không mở rộng allowlist chỉ để làm cho một stream bất kỳ deserialize thành công. Nếu một lớp bất ngờ xuất hiện, hãy xem lại hợp đồng dữ liệu và nguồn tạo stream trước khi quyết định cho phép.

Với các kiểu generic như `List<T>`, kiểu phần tử thực tế vẫn xuất hiện trong stream và cần được đánh giá. Cho phép `ArrayList` không đồng nghĩa mọi kiểu object được chứa bên trong đều an toàn.

## 5. Giới hạn tài nguyên: depth, references, bytes và array

Chỉ allowlist class là chưa đủ. Một graph gồm các class được phép vẫn có thể quá sâu, quá lớn hoặc tiêu tốn tài nguyên bất thường.

Bốn giới hạn thường dùng:

- `maxdepth`: giới hạn độ sâu object graph.
- `maxrefs`: giới hạn số object/reference.
- `maxbytes`: giới hạn số byte đã đọc từ stream.
- `maxarray`: giới hạn độ dài mỗi array.

Ví dụ filter tùy chỉnh:

~~~java
private static final long MAX_DEPTH = 8;
private static final long MAX_REFERENCES = 100;
private static final long MAX_STREAM_BYTES = 16_384;
private static final long MAX_ARRAY_LENGTH = 64;

ObjectInputFilter filter = info -> {
    if (info.depth() > MAX_DEPTH
            || info.references() > MAX_REFERENCES
            || info.streamBytes() > MAX_STREAM_BYTES
            || info.arrayLength() > MAX_ARRAY_LENGTH) {
        return ObjectInputFilter.Status.REJECTED;
    }

    // Tiếp tục kiểm tra class allowlist tại đây.
    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

Các con số chỉ là ví dụ. Hãy lấy giới hạn từ kích thước graph hợp lệ trong nghiệp vụ, đo dữ liệu thực tế và đặt biên an toàn. Không dùng một bộ số chung cho mọi luồng deserialize.

Giới hạn graph không thay thế giới hạn của tầng transport. Nên giới hạn kích thước request trước khi đưa byte vào ObjectInputStream, áp timeout cho việc nhận dữ liệu và giới hạn số request đồng thời. `maxbytes` kiểm tra byte đã tiêu thụ trong quá trình deserialize, không thay thế giới hạn upload ở tầng HTTP/socket.

## 6. Pattern filter và cấu hình JVM-wide

Java 9 cho phép tạo filter từ chuỗi pattern bằng:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=100;maxbytes=16384;maxarray=64;"
                + "com.example.dto.*;!*");
~~~

Các pattern được phân tách bằng dấu chấm phẩy:

- `maxdepth=n`, `maxrefs=n`, `maxbytes=n`, `maxarray=n` đặt giới hạn tài nguyên.
- Tên lớp hoặc package cho phép class tương ứng.
- Thêm `!` trước pattern để từ chối class/package khớp.
- `!*` ở cuối từ chối class không được pattern trước đó cho phép.

Ví dụ trên chỉ là khuôn minh họa cho package DTO; khi áp dụng cần đưa vào đầy đủ các lớp và kiểu mảng hợp lệ của graph thực tế. Pattern có thể bao gồm tên module để thu hẹp phạm vi.

Có thể cài filter JVM-wide bằng system property lúc khởi động:

~~~bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=1000;maxbytes=1000000;maxarray=100000;com.example.dto.*;!*" com.example.Main
~~~

Hoặc cấu hình bằng API trước khi tạo các ObjectInputStream:

~~~java
ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=1000;maxbytes=1000000;maxarray=100000;"
                + "com.example.dto.*;!*");

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

JVM-wide filter là baseline áp dụng trong process. Nó chỉ có tác dụng khi được cấu hình; Java không tự bật một allowlist an toàn mặc định cho mọi ứng dụng. Cấu hình nên được thiết lập sớm trong quá trình khởi động và chỉ một lần.

## 7. Filter riêng cho từng ObjectInputStream

Khi mỗi luồng có hợp đồng dữ liệu riêng, đặt filter trực tiếp trên stream:

~~~java
try (ObjectInputStream in =
        new ObjectInputStream(inputStream)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
~~~

`setObjectInputFilter` phải được gọi trước lần đọc object đầu tiên và chỉ được thiết lập một lần cho stream. Hãy đặt filter ngay sau khi tạo ObjectInputStream, trước khi gọi `readObject()` hoặc `readUnshared()`.

Đây là nơi phù hợp để gắn allowlist theo endpoint, message type, file format hoặc library. Mỗi entry point nên có policy rõ ràng và test riêng.

### Lưu ý khi kết hợp global filter với stream filter

Không giả định JVM-wide filter và stream-specific filter luôn tự động được ghép thành một policy. Với built-in filter factory, global filter được dùng khi ObjectInputStream được tạo; nếu sau đó ứng dụng gọi `setObjectInputFilter`, filter stream-specific sẽ thay thế filter global hiện tại.

Nếu ứng dụng cần global baseline và allowlist riêng cùng được thực thi, cần cấu hình filter factory tùy chỉnh ở Java 17 trở lên để compose các filter. Không để một filter stream-specific vô tình làm mất baseline bảo vệ của process.

## 8. Java 17+: context-specific filter factory (JEP 415)

JEP 415 được đưa vào Java 17 để ứng dụng có thể chọn hoặc kết hợp filter theo ngữ cảnh của từng ObjectInputStream. Filter factory là một `BinaryOperator<ObjectInputFilter>` được gọi khi stream được tạo và khi filter riêng của stream được thiết lập.

Factory có thể lựa chọn policy theo thông tin như:

- Thread-local context hoặc request scope.
- Call stack/caller của điểm deserialize.
- Module, library hoặc class loader.
- Filter global và filter riêng được yêu cầu.

Cấu hình factory chỉ thực hiện một lần và phải thực hiện trước khi bất kỳ ObjectInputStream nào được tạo. Ví dụ dưới đây ghép global resource limits với stream-specific allowlist, sau đó từ chối class còn undecided:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory((current, requested) -> {
    if (current == null) {
        return requested;
    }
    if (requested == null) {
        return current;
    }
    return ObjectInputFilter.rejectUndecidedClass(
            ObjectInputFilter.merge(current, requested));
});
~~~

Trong factory này:

- Lúc constructor chạy, `current` có thể là null và `requested` là global filter.
- Khi ứng dụng gọi `setObjectInputFilter`, `current` là filter hiện tại và `requested` là filter của stream.
- `merge` trả REJECTED nếu một trong hai filter từ chối; trả ALLOWED nếu không filter nào từ chối và có ít nhất một filter cho phép; các trường hợp còn lại là UNDECIDED.
- `rejectUndecidedClass` giúp không để class ngoài allowlist lọt qua chỉ vì mọi filter đều không đưa ra kết luận.

Factory phải giữ policy nhất quán, không trả null để vô tình gỡ một filter hiện có. Nếu dùng ThreadLocal để chọn filter, phải khôi phục context trong `finally` để request kế tiếp trên cùng thread không nhận nhầm policy.

## 9. Các helper filter được bổ sung từ Java 17

Java 17 bổ sung các helper để tạo và kết hợp filter:

~~~java
ObjectInputFilter allowDto = ObjectInputFilter.allowFilter(
        type -> type == Message.class,
        ObjectInputFilter.Status.REJECTED);

ObjectInputFilter denyProxy = ObjectInputFilter.rejectFilter(
        type -> java.lang.reflect.Proxy.isProxyClass(type),
        ObjectInputFilter.Status.UNDECIDED);

ObjectInputFilter combined =
        ObjectInputFilter.merge(allowDto, denyProxy);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(combined);
~~~

- `allowFilter(predicate, otherStatus)`: trả ALLOWED khi predicate đúng; nếu sai trả `otherStatus`; nếu class null trả UNDECIDED.
- `rejectFilter(predicate, otherStatus)`: trả REJECTED khi predicate đúng; nếu sai trả `otherStatus`; nếu class null trả UNDECIDED.
- `merge(first, second)`: ghép hai kết quả theo quy tắc từ chối ưu tiên.
- `rejectUndecidedClass(filter)`: chuyển kết quả undecided của class thành rejected, có xử lý riêng cho array.

Các helper này không tự chọn allowlist phù hợp cho ứng dụng. Predicate vẫn phải được thiết kế từ hợp đồng object graph thực tế.

## 10. Ví dụ Java chạy được: allowlist và giới hạn graph

Chương trình dưới đây cho phép `Message`, `ArrayBox`, `Node` và `int[]`. Filter từ chối class không nằm trong allowlist, array dài hơn 64 phần tử, graph sâu hơn 8, quá 100 references hoặc stream vượt 16 KiB.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class ObjectInputFilterDemo {
    private static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String text;

        Message(String text) {
            this.text = text;
        }
    }

    private static final class ArrayBox implements Serializable {
        private static final long serialVersionUID = 1L;
        private final int[] values;

        ArrayBox(int[] values) {
            this.values = values;
        }
    }

    private static final class Node implements Serializable {
        private static final long serialVersionUID = 1L;
        private final Node next;

        Node(Node next) {
            this.next = next;
        }
    }

    private static final class Unexpected implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String value = "not allowed";
    }

    private static ObjectInputFilter messageFilter() {
        return info -> {
            if (info.depth() > 8
                    || info.references() > 100
                    || info.streamBytes() > 16_384
                    || info.arrayLength() > 64) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }
            if (type == Message.class || type == ArrayBox.class
                    || type == int[].class || type == Node.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }
            return ObjectInputFilter.Status.REJECTED;
        };
    }

    private static byte[] serialize(Serializable value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
        }
        return bytes.toByteArray();
    }

    private static Object deserialize(byte[] bytes, ObjectInputFilter filter)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(filter);
            return in.readObject();
        }
    }

    private static boolean rejected(byte[] bytes) throws Exception {
        try {
            deserialize(bytes, messageFilter());
            return false;
        } catch (InvalidClassException ex) {
            return true;
        }
    }

    private static Node chain(int length) {
        Node node = null;
        for (int i = 0; i < length; i++) {
            node = new Node(node);
        }
        return node;
    }

    public static void main(String[] args) throws Exception {
        Message accepted = (Message) deserialize(
                serialize(new Message("hello")), messageFilter());
        System.out.println("accepted message = " + accepted.text);
        System.out.println("rejected class = "
                + rejected(serialize(new Unexpected())));
        System.out.println("rejected array length = "
                + rejected(serialize(new ArrayBox(new int[128]))));
        System.out.println("rejected graph depth = "
                + rejected(serialize(chain(12))));
    }
}
~~~

Lưu thành `ObjectInputFilterDemo.java`, biên dịch và chạy với Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all ObjectInputFilterDemo.java
java ObjectInputFilterDemo
~~~

Kết quả:

~~~text
accepted message = hello
rejected class = true
rejected array length = true
rejected graph depth = true
~~~

Ví dụ cũng tương thích API Java 9 và đã được kiểm tra bằng:

~~~bash
javac --release 9 -Xlint:all ObjectInputFilterDemo.java
java ObjectInputFilterDemo
~~~

Kết quả trên xác nhận filter cho phép kiểu đã khai báo, từ chối class lạ, từ chối array quá lớn và từ chối object graph quá sâu. Ví dụ không dùng `System.gc()` hay timing để kiểm tra; các điều kiện filter được kích hoạt trực tiếp bởi dữ liệu serialized đã biết.

## 11. Những gì ObjectInputFilter không bảo đảm

Filter là một lớp phòng vệ, không phải bộ xác thực đầy đủ:

- **Không xác thực field value:** String, primitive và các giá trị nghiệp vụ cần được kiểm tra sau khi deserialize.
- **Không bảo đảm class được allow là an toàn:** `readObject`, `readResolve`, proxy handler hoặc code trong class vẫn có thể có side effect.
- **Không loại bỏ mọi gadget chain:** một graph chỉ chứa class được cho phép vẫn có thể nguy hiểm nếu các class đó có hành vi nhạy cảm khi khôi phục.
- **Không thay thế giới hạn transport:** cần giới hạn request bytes, timeout và concurrency trước khi deserialize.
- **Không tự bật mặc định:** nếu ứng dụng không cấu hình filter thì không có allowlist tự động.
- **Không áp dụng cho mọi serializer:** ObjectInputFilter bảo vệ Java Object Serialization qua ObjectInputStream; thư viện JSON/XML/binary bên thứ ba cần policy riêng.
- **Không thay thế kiểm soát quyền:** deserialize trong process với quyền tối thiểu cần thiết; tránh để dữ liệu đầu vào quyết định hành động đặc quyền.

Nếu dữ liệu đến từ bên ngoài, cân nhắc không dùng native Java serialization. Nếu buộc phải dùng, hãy giới hạn nguồn dữ liệu, xác định allowlist theo từng entry point, áp resource limits và validate kết quả trước khi dùng.

## 12. Lỗi cấu hình thường gặp

- **Chỉ dùng blacklist:** danh sách từ chối không thể bao phủ mọi class nguy hiểm; ưu tiên allowlist theo use case.
- **Trả UNDECIDED cho mọi class lạ:** ObjectInputStream có thể tiếp tục đọc class đó; strict allowlist phải reject class không nhận diện.
- **Chỉ kiểm tra class mà bỏ metrics:** class được phép vẫn có thể tạo graph rất sâu, nhiều reference hoặc array lớn.
- **Đặt filter sau readObject:** object đầu tiên đã được khôi phục trước khi filter có hiệu lực.
- **Cho rằng global và stream filter luôn được merge:** built-in factory có thể thay global filter khi stream filter được thiết lập; dùng factory tùy chỉnh nếu cần compose.
- **Cấu hình factory sau khi đã tạo ObjectInputStream:** JDK 17 yêu cầu factory được thiết lập trước khi stream đầu tiên được tạo và chỉ cấu hình một lần.
- **Dùng pattern package quá rộng:** thêm `.*` hoặc module rộng mà không kiểm kê object graph có thể mở rộng attack surface.
- **Cho rằng allowlist là validation nghiệp vụ:** vẫn phải kiểm tra giá trị field, invariant và quyền sở hữu.
- **Dùng cùng một filter cho mọi context:** các entry point khác nhau có thể có object graph và giới hạn tài nguyên khác nhau.

## 13. Checklist khi triển khai

1. Có thể tránh Java native deserialization cho dữ liệu không tin cậy không?
2. Mỗi entry point đã có inventory các class hợp lệ chưa?
3. Filter có allowlist và reject class ngoài hợp đồng không?
4. Đã đặt giới hạn depth, references, bytes và array theo dữ liệu thực tế chưa?
5. Filter được gắn trước lần đọc object đầu tiên chưa?
6. Global filter và stream filter có đang thay thế hay compose theo đúng policy không?
7. Nếu dùng Java 17 filter factory, factory đã được cấu hình trước mọi ObjectInputStream chưa?
8. Kết quả deserialize đã được validate về field value và invariant nghiệp vụ chưa?
9. Có test class lạ, array lớn, graph sâu và stream vượt byte limit không?
10. Có log/metric cho các lần bị từ chối mà không ghi dữ liệu nhạy cảm không?

## 14. Tài liệu tham khảo

- [ObjectInputFilter — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/io/ObjectInputFilter.html)
- [ObjectInputFilter — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ObjectInputFilter.html)
- [ObjectInputStream — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ObjectInputStream.html)
- [Java Serialization Filters — Oracle Java SE 25](https://docs.oracle.com/en/java/javase/25/core/java-serialization-filters.html)
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)
- [Secure Coding Guidelines for Java SE — Serialization and Deserialization](https://www.oracle.com/java/technologies/javase/seccodeguide.html)