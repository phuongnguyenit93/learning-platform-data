# Lọc lớp, độ dài mảng, độ sâu và số tham chiếu

Java Serialization Filtering là cơ chế kiểm soát object graph đầu vào khi giải tuần tự bằng ObjectInputStream. Cơ chế này được đưa vào JDK 9 qua JEP 290 để giảm rủi ro khi đọc dữ liệu serialization, đồng thời giới hạn tài nguyên mà một stream có thể tiêu thụ.

Một filter có thể kiểm tra lớp đang được đọc, độ dài từng mảng, độ sâu của graph, tổng số object reference và số byte đã tiêu thụ. Các giới hạn này bổ sung cho nhau: allowlist hạn chế loại đối tượng, còn giới hạn kích thước và độ phức tạp ngăn một graph hợp lệ về kiểu nhưng quá lớn hoặc quá sâu.

## 1. Vì sao cần Serialization Filtering?

ObjectInputStream có thể dựng lại toàn bộ object graph được ghi bởi ObjectOutputStream. Một object có thể tham chiếu tới object khác, array, collection hoặc một chuỗi lớp lồng nhau. Khi đọc dữ liệu không đáng tin cậy, ứng dụng không kiểm soát được graph nào sẽ xuất hiện nếu không áp dụng chính sách.

Rủi ro chính gồm:

- **Unexpected class:** stream chứa class mà thành phần ứng dụng không dự kiến xử lý.
- **Large array:** một array rất lớn gây áp lực bộ nhớ.
- **Deep graph:** nhiều object lồng nhau làm tăng stack depth và chi phí xử lý.
- **Too many references:** graph có số lượng object/reference lớn gây tiêu tốn CPU và bộ nhớ.
- **Large stream:** dữ liệu đầu vào lớn làm tăng thời gian đọc và tài nguyên cần thiết.

Serialization Filtering cho phép đặt chính sách theo từng ObjectInputStream hoặc toàn JVM. Filter được gọi trong quá trình đọc object graph để quyết định cho phép, từ chối hoặc để filter khác quyết định.

**Lưu ý:** filter không được bật mặc định. Nếu ứng dụng không cấu hình filter qua system/security property hoặc ObjectInputFilter API, ObjectInputStream không tự áp dụng chính sách lọc.

## 2. ObjectInputFilter và FilterInfo

ObjectInputFilter là functional interface có một phương thức:

~~~java
ObjectInputFilter.Status checkInput(
        ObjectInputFilter.FilterInfo filterInfo
);
~~~

FilterInfo cung cấp thông tin tại thời điểm stream đang được giải tuần tự:

| Phương thức | Ý nghĩa |
|---|---|
| serialClass() | Class đang được đọc; có thể null khi xử lý reference tới object đã đọc |
| arrayLength() | Số phần tử của array đang được đọc; -1 nếu không phải array |
| depth() | Độ sâu hiện tại của object graph |
| references() | Tổng số object và reference đã đọc, bao gồm mục hiện tại |
| streamBytes() | Số byte đã tiêu thụ từ stream |

### serialClass()

Nếu một class đang được kiểm tra, serialClass trả về Class tương ứng. Với array, kết quả là kiểu array, ví dụ int[] hoặc Node[].

Để kiểm tra kiểu phần tử của array nhiều chiều, đi qua getComponentType() cho đến khi không còn là array:

~~~java
Class<?> component = filterInfo.serialClass();

while (component != null && component.isArray()) {
    component = component.getComponentType();
}
~~~

serialClass có thể là null khi stream tham chiếu lại một object đã được đọc trước đó. Khi đó filter vẫn nhận được depth, references và streamBytes để đánh giá độ phức tạp graph.

String được serialization xử lý như primitive data và không gọi filter. Primitive value cũng không được filter như một object class; array primitive vẫn được kiểm tra như array.

### arrayLength()

arrayLength trả về số phần tử của array hiện tại. Giá trị -1 có nghĩa callback không liên quan đến array.

Giới hạn array nên được kiểm tra trước khi chấp nhận array:

~~~java
if (info.arrayLength() >= 0 && info.arrayLength() > MAX_ARRAY_LENGTH) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

maxarray là giới hạn độ dài của từng array, không phải tổng số phần tử của mọi array trong graph. Một graph có nhiều array nhỏ vẫn có thể rất lớn; kết hợp maxarray với maxrefs, maxdepth và maxbytes để giới hạn tổng thể.

### depth()

depth là độ sâu hiện tại của graph được đọc. Giá trị bắt đầu từ 1 ở object gốc và tăng khi có các lần đọc object lồng nhau; khi một object hoàn tất, depth giảm lại.

Giới hạn depth giúp chặn cấu trúc lồng quá sâu:

~~~java
if (info.depth() > MAX_DEPTH) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Depth không phải số lượng object trong graph. Một graph rộng có thể có depth thấp nhưng rất nhiều reference; vì vậy cần thêm giới hạn references.

### references()

references là số object và reference đã được đọc từ stream, bao gồm object hiện tại. Bộ đếm này tăng cả khi stream ghi tham chiếu đến object đã được đọc trước đó.

Giới hạn references giúp kiểm soát graph có quá nhiều nút hoặc quá nhiều liên kết:

~~~java
if (info.references() > MAX_REFERENCES) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Đây không chỉ là số class khác nhau hay số object duy nhất. Một graph có thể tái sử dụng cùng một object nhiều lần nhưng vẫn tạo thêm reference trong stream.

### streamBytes()

streamBytes cho biết số byte đã tiêu thụ từ input stream. Đây là metric do implementation xác định; nó không nhất thiết tương ứng trực tiếp với kích thước byte của object đang gây ra callback.

Dùng streamBytes để đặt giới hạn ngân sách cho stream, nhưng không diễn giải nó như kích thước chính xác của riêng object:

~~~java
if (info.streamBytes() > MAX_STREAM_BYTES) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

## 3. Ba trạng thái của filter

checkInput phải trả về một trong ba giá trị:

| Status | Ý nghĩa |
|---|---|
| ALLOWED | Filter chấp nhận class/object và các giới hạn hiện tại |
| REJECTED | Filter từ chối; quá trình đọc object bị hủy |
| UNDECIDED | Filter không đưa ra kết luận cho trường hợp này |

REJECTED làm readObject hoặc readUnshared ném InvalidClassException. Nếu filter trả null hoặc ném RuntimeException, quá trình đọc cũng bị từ chối.

UNDECIDED không có nghĩa là từ chối. Nó cho phép filter khác đưa ra quyết định; nếu không có filter nào từ chối thì deserialization có thể tiếp tục. Vì vậy một filter muốn tạo allowlist nghiêm ngặt cần trả REJECTED cho class không nằm trong danh sách, hoặc kết hợp với rejectUndecidedClass trên JDK 17+.

Khi ghép hai filter bằng ObjectInputFilter.merge:

- Nếu một filter trả REJECTED, kết quả là REJECTED.
- Nếu không filter nào từ chối và ít nhất một filter trả ALLOWED, kết quả là ALLOWED.
- Nếu cả hai đều UNDECIDED, kết quả là UNDECIDED.

Không trả null từ checkInput.

## 4. Tạo filter tùy chỉnh theo class và graph metrics

Filter tùy chỉnh cho phép kết hợp allowlist và các ngưỡng:

~~~java
private static final long MAX_ARRAY = 1000;
private static final long MAX_DEPTH = 20;
private static final long MAX_REFERENCES = 5000;
private static final long MAX_STREAM_BYTES = 1_000_000;

static ObjectInputFilter createFilter() {
    return info -> {
        if (info.arrayLength() >= 0
                && info.arrayLength() > MAX_ARRAY) {
            return ObjectInputFilter.Status.REJECTED;
        }

        if (info.depth() > MAX_DEPTH
                || info.references() > MAX_REFERENCES
                || info.streamBytes() > MAX_STREAM_BYTES) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        while (type.isArray()) {
            type = type.getComponentType();
        }

        if (type.isPrimitive()
                || type == CustomerRecord.class
                || type == Address.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
~~~

Các điểm cần chú ý:

1. Kiểm tra metrics trước khi xử lý serialClass, vì serialClass có thể null.
2. Với array, kiểm tra component type để nhận diện kiểu phần tử.
3. Chỉ cho phép các class mà thành phần ứng dụng thực sự cần.
4. Giới hạn phải dựa trên kích thước graph bình thường của use case, có khoảng dự phòng hợp lý.
5. Không cho phép mọi class chỉ vì chúng thuộc JDK hoặc cùng package rộng nếu ứng dụng không cần.

Trong ví dụ, primitive array được cho phép sau khi bóc kiểu phần tử về primitive. String không gọi filter theo cơ chế serialization hiện tại.

## 5. Filter dạng pattern

Với chính sách đơn giản, có thể tạo filter từ chuỗi pattern bằng:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.**;"
                + "maxdepth=20;"
                + "maxrefs=5000;"
                + "maxarray=1000;"
                + "maxbytes=1000000;"
                + "!*"
        );
~~~

Các thành phần:

- Pattern class/package cho phép hoặc từ chối class.
- Dấu ! ở đầu pattern nghĩa là từ chối class khớp.
- .* khớp các class trực tiếp trong package.
- .** khớp package và các subpackage.
- * ở cuối khớp tên class theo tiền tố.
- Có thể thêm module name trước dấu / để giới hạn theo module.
- Các limit maxdepth, maxrefs, maxarray và maxbytes đặt ngưỡng cho graph.

Các pattern được phân tách bằng dấu chấm phẩy; khoảng trắng là một phần của pattern. Pattern class được xét từ trái sang phải và pattern đầu tiên khớp quyết định ALLOWED hoặc REJECTED. Nếu không pattern nào khớp, kết quả là UNDECIDED.

Đối với array, pattern khớp kiểu phần tử thay vì tên kiểu array. Các giới hạn vẫn được kiểm tra trước khi xác định class pattern. Nếu một limit vượt ngưỡng, filter trả REJECTED.

Ví dụ trên là khung allowlist theo package và catch-all reject. Trong ứng dụng thực tế, phải bổ sung mọi class cần thiết trong object graph, bao gồm class con, class thành phần và các kiểu hỗ trợ được serialization ghi vào stream. Tránh dùng wildcard quá rộng khiến allowlist mất ý nghĩa.

## 6. Cài filter cho từng ObjectInputStream

Filter theo stream phù hợp khi mỗi điểm đọc có một hợp đồng dữ liệu riêng:

~~~java
try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    input.setObjectInputFilter(createFilter());

    Object value = input.readObject();
}
~~~

setObjectInputFilter phải được gọi đúng một lần và trước lần đọc object đầu tiên bằng readObject hoặc readUnshared. Không thể đợi đọc một phần graph rồi mới cài filter.

Có thể dùng getObjectInputFilter() để kiểm tra filter hiện tại. Nếu stream đã có filter khác null, không thể thay nó bằng null. Khi filter từ chối object, readObject ném InvalidClassException và stream ở trạng thái không thể tiếp tục đọc một cách tin cậy; hãy đóng stream và xử lý lỗi ở tầng gọi.

## 7. Cài filter JVM-wide

Nếu ứng dụng có chính sách chung cho hầu hết deserialization, có thể cài filter cấp JVM:

~~~java
ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.**;"
                + "maxdepth=20;"
                + "maxrefs=5000;"
                + "maxarray=1000;"
                + "maxbytes=1000000;"
                + "!*"
        );

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

Cũng có thể cấu hình bằng system property khi khởi chạy JVM:

~~~bash
java -Djdk.serialFilter="com.example.dto.**;maxdepth=20;maxrefs=5000;maxarray=1000;maxbytes=1000000;!*" Application
~~~

Config.setSerialFilter chỉ đặt filter JVM-wide một lần. Nếu filter đã được cấu hình bằng system property hoặc đã được đặt trước đó, lời gọi khác có thể ném IllegalStateException. Nên cấu hình ở giai đoạn bootstrap trước khi ứng dụng bắt đầu xử lý dữ liệu serialization.

Không dùng System.setProperty("jdk.serialFilter", ...) sau khi ObjectInputFilter.Config đã khởi tạo để kỳ vọng filter được cài; system property phải được cung cấp lúc khởi chạy JVM.

Filter JVM-wide và filter theo stream có thể được kết hợp. Hành vi kết hợp phụ thuộc filter factory đang hoạt động; không giả định rằng hai filter luôn tự động được giao nhau theo cách ứng dụng mong muốn. Nếu cần giữ đồng thời chính sách toàn cục và chính sách theo stream, hãy định nghĩa rõ cách kết hợp và bảo đảm REJECTED luôn được tôn trọng.

## 8. Filter factory theo ngữ cảnh từ Java 17

JEP 415 bổ sung filter factory theo ngữ cảnh trong JDK 17. Factory là BinaryOperator<ObjectInputFilter>, được gọi khi ObjectInputStream được tạo và khi filter theo stream được đặt.

Factory nhận filter hiện tại và filter được yêu cầu, sau đó chọn hoặc kết hợp filter phù hợp. Nó có thể dùng thông tin ngữ cảnh như ThreadLocal, caller, module hoặc class loader để chọn chính sách riêng cho từng thành phần ứng dụng.

~~~java
ObjectInputFilter.Config.setSerialFilterFactory(
        (current, requested) -> {
            ObjectInputFilter combined =
                    ObjectInputFilter.merge(current, requested);

            return combined == null
                    ? null
                    : ObjectInputFilter.rejectUndecidedClass(combined);
        }
);
~~~

Đoạn code minh họa factory kết hợp filter hiện tại và filter mới, sau đó từ chối class còn UNDECIDED. Đây là ví dụ chính sách nghiêm ngặt; ứng dụng phải bảo đảm tất cả class hợp lệ đều được một filter cho phép.

Factory chỉ được cấu hình một lần và phải được đặt trước khi bất kỳ ObjectInputStream nào được tạo. Các API allowFilter, rejectFilter, merge và rejectUndecidedClass cũng được bổ sung từ Java 17. Khi cần tương thích Java 9, không gọi các API này trong code baseline Java 9; dùng checkInput và các API Java 9 như createFilter, setSerialFilter, setObjectInputFilter.

## 9. Ví dụ chạy được với Java 9+

Tạo file **SerializationFilterDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class SerializationFilterDemo {
    static final class SafeRecord implements Serializable {
        private static final long serialVersionUID = 1L;
        final String name;
        final int[] values;
        final Node child;
        final Node[] links;

        SafeRecord(String name, int[] values, Node child, Node[] links) {
            this.name = name;
            this.values = values;
            this.child = child;
            this.links = links;
        }
    }

    static final class Node implements Serializable {
        private static final long serialVersionUID = 1L;
        final Node next;

        Node(Node next) {
            this.next = next;
        }
    }

    static final class DeniedRecord implements Serializable {
        private static final long serialVersionUID = 1L;
        final String value = "not allowed";
    }

    static ObjectInputFilter filter(
            long maxArray,
            long maxDepth,
            long maxReferences,
            long maxBytes) {
        return info -> {
            if (info.arrayLength() >= 0
                    && info.arrayLength() > maxArray) {
                return ObjectInputFilter.Status.REJECTED;
            }
            if (info.depth() > maxDepth
                    || info.references() > maxReferences
                    || info.streamBytes() > maxBytes) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }
            while (type.isArray()) {
                type = type.getComponentType();
            }
            if (type.isPrimitive()
                    || type == SafeRecord.class
                    || type == Node.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }
            return ObjectInputFilter.Status.REJECTED;
        };
    }

    static byte[] serialize(Object value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(value);
        }
        return bytes.toByteArray();
    }

    static Object deserialize(
            byte[] bytes,
            long maxArray,
            long maxDepth,
            long maxReferences,
            long maxBytes) throws IOException, ClassNotFoundException {
        try (ObjectInputStream input =
                     new ObjectInputStream(new ByteArrayInputStream(bytes))) {
            input.setObjectInputFilter(
                    filter(maxArray, maxDepth, maxReferences, maxBytes)
            );
            return input.readObject();
        }
    }

    static void expectRejected(
            String label,
            Object value,
            long maxArray,
            long maxDepth,
            long maxReferences,
            long maxBytes) throws Exception {
        try {
            deserialize(
                    serialize(value),
                    maxArray,
                    maxDepth,
                    maxReferences,
                    maxBytes
            );
            throw new AssertionError(label + " should have been rejected");
        } catch (InvalidClassException expected) {
            System.out.println(label + " rejected");
        }
    }

    static Node chain(int count) {
        Node node = null;
        for (int i = 0; i < count; i++) {
            node = new Node(node);
        }
        return node;
    }

    public static void main(String[] args) throws Exception {
        Node shared = new Node(null);
        SafeRecord safe = new SafeRecord(
                "safe",
                new int[] {1, 2, 3},
                shared,
                new Node[] {shared, shared}
        );
        SafeRecord accepted = (SafeRecord) deserialize(
                serialize(safe), 8, 10, 100, 4096
        );
        System.out.println("accepted: " + accepted.name);

        expectRejected(
                "class",
                new DeniedRecord(),
                8, 10, 100, 4096
        );

        expectRejected(
                "array",
                new SafeRecord(
                        "large",
                        new int[20],
                        null,
                        new Node[0]
                ),
                8, 10, 100, 4096
        );

        expectRejected(
                "depth",
                new SafeRecord(
                        "deep",
                        new int[] {1},
                        chain(8),
                        new Node[0]
                ),
                8, 4, 100, 4096
        );

        expectRejected(
                "references",
                new SafeRecord(
                        "many references",
                        new int[] {1},
                        shared,
                        new Node[] {
                                shared, shared, shared, shared,
                                shared, shared, shared, shared
                        }
                ),
                8, 10, 5, 4096
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SerializationFilterDemo.java
java SerializationFilterDemo
~~~

Kết quả stdout chính xác:

~~~text
accepted: safe
class rejected
array rejected
depth rejected
references rejected
~~~

Giải thích:

- SafeRecord và Node nằm trong allowlist; graph nhỏ được chấp nhận.
- DeniedRecord không thuộc allowlist nên bị từ chối.
- int[20] vượt maxArray = 8 nên bị từ chối.
- Chuỗi Node lồng nhau vượt maxDepth = 4 nên bị từ chối.
- Mảng Node[] chứa nhiều reference tới cùng object vượt maxReferences = 5 nên bị từ chối.

Chương trình dùng filter theo từng stream và đặt filter trước readObject. Ví dụ được biên dịch bằng API Java 9 với javac --release 9 và chạy trên JDK 24.0.2.

## 10. Những điều filter không làm

Serialization Filtering là lớp phòng vệ cho quá trình giải tuần tự, không phải sandbox hoàn chỉnh.

Filter không thay thế việc:

- Xác thực dữ liệu nghiệp vụ sau khi object được tạo.
- Kiểm tra giá trị field, quyền sở hữu, trạng thái giao dịch hoặc invariant giữa nhiều field.
- Kiểm tra chữ ký, nguồn gốc hoặc tính toàn vẹn của file/stream.
- Giới hạn mọi chi phí CPU hoặc hành vi tùy ý trong code deserialization.
- Tránh hoàn toàn rủi ro của Java native serialization.

Các method readObject, readExternal, readResolve và code liên quan vẫn có thể thực thi logic ứng dụng. Hãy chỉ cho phép class cần thiết, đặt giới hạn graph hợp lý và xác thực dữ liệu sau khi đọc.

Nếu có thể thiết kế giao thức mới, ưu tiên định dạng dữ liệu có schema rõ ràng và parser được xây dựng cho dữ liệu không đáng tin cậy. Nếu phải đọc Java serialization từ nguồn ngoài, không dùng reject-list đơn lẻ làm biện pháp chính; allowlist theo từng ngữ cảnh thường an toàn hơn.

## 11. Lỗi thường gặp

**Cho rằng filter được bật mặc định:** không có filter nếu ứng dụng hoặc JVM chưa cấu hình. Cài filter trước khi bắt đầu giải tuần tự.

**Chỉ kiểm tra class mà bỏ qua graph metrics:** class hợp lệ vẫn có thể xuất hiện trong array quá lớn hoặc graph quá sâu. Kết hợp class policy với maxarray, maxdepth, maxrefs và maxbytes.

**Nhầm references với số object class khác nhau:** references là bộ đếm object/reference trong stream, bao gồm back-reference; không chỉ là số class duy nhất.

**Bỏ qua serialClass null:** callback có thể được gọi cho reference tới object đã đọc. Khi class null, vẫn phải kiểm tra depth, references và streamBytes.

**Cho phép mọi class trong java.base:** module này chứa rất nhiều kiểu. Chỉ allow các class thực sự cần cho graph.

**Dùng UNDECIDED như từ chối:** UNDECIDED không có nghĩa là REJECTED. Với allowlist nghiêm ngặt, trả REJECTED cho class không nhận diện hoặc dùng rejectUndecidedClass trên Java 17+.

**Đặt filter sau readObject:** setObjectInputFilter chỉ được gọi một lần trước khi đọc object đầu tiên. Cài sau khi stream đã đọc sẽ ném IllegalStateException.

**Gọi setSerialFilter nhiều lần:** filter JVM-wide chỉ được cấu hình một lần. Thiết lập trong giai đoạn bootstrap hoặc qua jdk.serialFilter khi khởi chạy.

**Giả định global và stream filter luôn được kết hợp:** cách kết hợp phụ thuộc filter factory. Kiểm tra và thiết kế factory nếu cần áp dụng đồng thời nhiều policy.

**Coi filter là xác thực dữ liệu đầy đủ:** filter kiểm tra class và resource metrics; vẫn phải xác thực dữ liệu nghiệp vụ sau deserialization.

## 12. Checklist thiết kế

- Xác định chính xác class nào được phép trong từng ngữ cảnh deserialization.
- Ưu tiên allowlist class/package nhỏ và cụ thể.
- Kiểm tra kiểu phần tử của array, kể cả array nhiều chiều.
- Đặt maxarray cho từng array.
- Đặt maxdepth cho graph lồng nhau.
- Đặt maxrefs cho tổng số object/reference.
- Đặt maxbytes cho ngân sách dữ liệu stream.
- Xử lý serialClass null bằng cách vẫn kiểm tra graph metrics.
- Trả về ALLOWED, REJECTED hoặc UNDECIDED; không trả null.
- Cài filter trước lần readObject/readUnshared đầu tiên.
- Cấu hình JVM-wide filter một lần và kiểm tra filter factory nếu có nhiều context.
- Dùng JEP 415 factory từ Java 17 khi cần policy riêng cho từng context.
- Xác thực field và invariant sau khi object graph được dựng lại.
- Không coi Java native serialization là định dạng an toàn cho dữ liệu không đáng tin cậy.

## Tài liệu tham khảo

- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290)
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)
- [ObjectInputFilter — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/io/ObjectInputFilter.html)
- [ObjectInputFilter.Config — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/io/ObjectInputFilter.Config.html)
- [ObjectInputStream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/io/ObjectInputStream.html)
- [Java Serialization Filters — Java SE 24 Guide](https://docs.oracle.com/en/java/javase/24/core/java-serialization-filters.html)
