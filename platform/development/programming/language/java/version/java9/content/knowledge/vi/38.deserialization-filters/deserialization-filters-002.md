# Xác định loại dữ liệu được phép trước khi nhận đầu vào

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao dữ liệu Java Serialization cần được lọc trước khi khôi phục object.
- Dùng \`ObjectInputFilter\` để lập allow-list các class được phép deserialize.
- Giới hạn độ sâu object graph, số reference, kích thước stream và độ dài array.
- Phân biệt \`ALLOWED\`, \`REJECTED\` và \`UNDECIDED\`.
- Gắn filter cho từng \`ObjectInputStream\` hoặc cấu hình filter toàn JVM.
- Hiểu vai trò của filter factory trong ứng dụng có nhiều context.
- Nhận biết những giới hạn của serialization filtering và kiểm tra dữ liệu sau khi deserialize.

## 1. Vì sao phải xác định kiểu dữ liệu được phép?

Java Serialization có thể khôi phục một object graph từ byte stream bằng \`ObjectInputStream\`. Khi đọc stream, runtime có thể phải nạp class, cấp phát object và thực hiện các hook serialization do class định nghĩa, chẳng hạn \`readObject\`, \`readExternal\` hoặc \`readResolve\`.

Nếu ứng dụng nhận serialized data từ nguồn không đáng tin, việc cho phép stream tự quyết định class nào được khôi phục có thể mở đường cho gadget chain, thực thi hành vi ngoài dự kiến hoặc tiêu thụ quá nhiều tài nguyên.

Một cách phòng vệ là xác định trước hợp đồng dữ liệu của từng điểm nhận: endpoint hoặc thành phần đó thực sự cần những class nào, những object graph có cấu trúc ra sao và giới hạn tài nguyên nào là hợp lý. Khi đọc stream, filter kiểm tra các class và chỉ số của object graph theo chính sách này.

Java 9 bổ sung \`ObjectInputFilter\` (JEP 290) để lọc dữ liệu trong quá trình deserialization. API này vẫn có trong JDK hiện hành. Java 17 bổ sung filter factory theo JEP 415 để chọn hoặc kết hợp filter theo context.

**Lưu ý:** filter được gọi khi \`ObjectInputStream\` đang đọc và khôi phục object graph. Nó không phải bộ lọc mạng chạy trước khi byte được nhận từ socket. Nếu cần giới hạn tổng kích thước request trước khi đọc stream, hãy đặt giới hạn ở tầng transport hoặc input stream riêng.

## 2. ObjectInputFilter kiểm tra những gì?

\`ObjectInputFilter\` thuộc package \`java.io\` và là functional interface. Ứng dụng cung cấp một hàm \`checkInput(FilterInfo)\` để quyết định một class hoặc trạng thái object graph có được phép tiếp tục hay không.

Thông tin filter nhận được qua \`ObjectInputFilter.FilterInfo\`:

| Method | Ý nghĩa |
|---|---|
| \`serialClass()\` | Class đang được kiểm tra; có thể là \`null\` ở lần callback chỉ cung cấp metric |
| \`arrayLength()\` | Độ dài array; giá trị âm nếu lần kiểm tra không dành cho array |
| \`depth()\` | Độ sâu của object graph tại thời điểm kiểm tra |
| \`references()\` | Số object/reference đã được đọc trong stream |
| \`streamBytes()\` | Số byte stream đã được tiêu thụ tại thời điểm kiểm tra |

Nhờ đó, filter có thể kiểm tra cả **loại dữ liệu** lẫn **mức tiêu thụ tài nguyên**. Một class nằm trong allow-list vẫn có thể bị từ chối nếu graph quá sâu, có quá nhiều reference, array quá lớn hoặc stream vượt giới hạn.

Filter không kiểm tra mọi giá trị field theo nghiệp vụ. Ví dụ, nó không tự xác minh \`quantity > 0\`, định dạng mã đơn hàng hay chuỗi có hợp lệ với domain hay không. Các điều kiện đó phải được kiểm tra sau khi object đã được deserialize.

## 3. Ba trạng thái của filter

\`checkInput\` trả về một trong ba giá trị:

| Status | Ý nghĩa |
|---|---|
| \`ALLOWED\` | Filter này chấp thuận class hoặc metric đang xét |
| \`REJECTED\` | Từ chối; thao tác đọc object sẽ thất bại |
| \`UNDECIDED\` | Filter này không đưa ra quyết định |

Điểm dễ nhầm là \`UNDECIDED\` **không đồng nghĩa với từ chối**. Nếu filter duy nhất trả về \`UNDECIDED\` cho một class, quá trình deserialization có thể tiếp tục.

Với một allow-list nghiêm ngặt:

- Trả \`ALLOWED\` cho class được liệt kê rõ ràng.
- Trả \`REJECTED\` cho class khác.
- Khi \`serialClass()\` là \`null\`, không có class để so sánh; có thể trả \`UNDECIDED\` sau khi đã kiểm tra các metric.

Nếu filter trả \`REJECTED\`, \`ObjectInputStream.readObject()\` ném \`InvalidClassException\`. Không bắt lỗi rồi tiếp tục đọc object từ cùng stream như thể graph vẫn đáng tin cậy.

## 4. Xây dựng allow-list theo hợp đồng dữ liệu

Allow-list nên liệt kê đúng những kiểu dữ liệu mà thành phần nhận thực sự cần. Ví dụ, một endpoint chỉ nhận \`InputRecord\` thì không nên cho phép toàn bộ package ứng dụng hoặc mọi class trong classpath.

~~~java
Set<Class<?>> allowed = new HashSet<>();
allowed.add(InputRecord.class);
~~~

Khi object có field tham chiếu đến một class khác, class đó cũng có thể xuất hiện trong object graph và cần được xem xét riêng. Với array, filter nhận được array class và độ dài; chỉ cho phép array có component type phù hợp với hợp đồng dữ liệu.

Không nên thêm một package rộng vào allow-list chỉ để làm lỗi deserialize biến mất. Mỗi class được thêm vào làm tăng bề mặt hành vi có thể được kích hoạt khi khôi phục object. Đặc biệt thận trọng với class có custom serialization hook, collection phức tạp hoặc phụ thuộc thư viện.

Primitive field không tạo object class riêng trong graph. Trong ObjectInputStream hiện hành, String được xử lý như primitive đối với filter và không kích hoạt callback checkInput. Vì vậy, allow-list không kiểm tra nội dung hoặc độ dài từng chuỗi; dùng streamBytes để giới hạn tổng bytes đã đọc và kiểm tra chuỗi theo nghiệp vụ sau deserialize.

## 5. Kết hợp allow-list với giới hạn object graph

Chỉ kiểm tra class là chưa đủ. Một graph có thể chỉ gồm class hợp lệ nhưng vẫn tiêu thụ quá nhiều bộ nhớ hoặc thời gian.

Các giới hạn thường dùng:

- **Depth:** giới hạn số tầng object lồng nhau.
- **References:** giới hạn tổng số object/reference trong graph.
- **Stream bytes:** giới hạn số byte đã đọc.
- **Array length:** giới hạn số phần tử của mỗi array.

Ví dụ chính sách:

~~~java
private static final long MAX_DEPTH = 8;
private static final long MAX_REFERENCES = 100;
private static final long MAX_STREAM_BYTES = 64 * 1024;
private static final long MAX_ARRAY_LENGTH = 256;
~~~

Các con số chỉ là ví dụ. Hãy chọn theo schema, kích thước request hợp lệ và giới hạn tài nguyên của ứng dụng. Không có một bộ giới hạn chung phù hợp với mọi hệ thống.

Nếu filter phát hiện metric vượt ngưỡng, trả \`REJECTED\` ngay cả khi class đang xét nằm trong allow-list.

## 6. Gắn filter cho một ObjectInputStream

Với một điểm nhận có hợp đồng riêng, thường dễ kiểm soát nhất khi gắn filter ngay sau khi tạo \`ObjectInputStream\` và trước lần gọi \`readObject()\` đầu tiên:

~~~java
try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    input.setObjectInputFilter(filter);
    Object value = input.readObject();
}
~~~

\`setObjectInputFilter\` chỉ được gọi một lần cho stream và phải được gọi trước khi đọc object. Vì vậy, hãy thiết lập chính sách ngay khi tạo stream, trước khi chuyển stream cho code khác.

Có thể đọc lại filter hiện tại bằng \`getObjectInputFilter()\` để chẩn đoán. Nếu một filter factory được cấu hình cho JVM, filter thực tế của stream là kết quả mà factory trả về.

## 7. Ví dụ hoàn chỉnh: chỉ nhận InputRecord và giới hạn graph

Tạo file **SerializationAllowListDemo.java**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

public class SerializationAllowListDemo {

    private static final long MAX_DEPTH = 4;
    private static final long MAX_REFERENCES = 32;
    private static final long MAX_BYTES = 4096;
    private static final long MAX_ARRAY_LENGTH = 16;

    private static final Set<Class<?>> ALLOWED_CLASSES =
            Collections.unmodifiableSet(
                    new HashSet<>(Arrays.<Class<?>>asList(
                            InputRecord.class)));

    private static final class InputRecord implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String id;
        private final int quantity;
        private final InputRecord child;

        InputRecord(String id, int quantity, InputRecord child) {
            this.id = id;
            this.quantity = quantity;
            this.child = child;
        }
    }

    private static final class UnexpectedPayload
            implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String value = "unexpected";
    }

    private static ObjectInputFilter allowListedFilter() {
        return info -> {
            if (info.depth() > MAX_DEPTH
                    || info.references() > MAX_REFERENCES
                    || info.streamBytes() > MAX_BYTES
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > MAX_ARRAY_LENGTH)) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            return ALLOWED_CLASSES.contains(type)
                    ? ObjectInputFilter.Status.ALLOWED
                    : ObjectInputFilter.Status.REJECTED;
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

    private static Object deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            // Set the filter before the first readObject call.
            input.setObjectInputFilter(allowListedFilter());
            return input.readObject();
        }
    }

    private static InputRecord chain(int count) {
        InputRecord result = null;
        for (int i = count; i >= 1; i--) {
            result = new InputRecord("node-" + i, i, result);
        }
        return result;
    }

    private static boolean rejected(Object value)
            throws IOException, ClassNotFoundException {
        try {
            deserialize(serialize(value));
            return false;
        } catch (InvalidClassException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        Object accepted = deserialize(serialize(
                new InputRecord("order-17", 3, null)));

        System.out.println("allowed type = "
                + accepted.getClass().getSimpleName());

        System.out.println("unexpected type rejected = "
                + rejected(new UnexpectedPayload()));

        System.out.println("excessive depth rejected = "
                + rejected(chain(8)));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out SerializationAllowListDemo.java
java -cp out SerializationAllowListDemo
~~~

Output chính xác:

~~~text
allowed type = InputRecord
unexpected type rejected = true
excessive depth rejected = true
~~~

Ví dụ cho thấy ba trường hợp:

1. \`InputRecord\` nằm trong allow-list và graph nằm trong giới hạn nên được chấp nhận.
2. \`UnexpectedPayload\` không nằm trong allow-list nên bị từ chối.
3. Chuỗi \`InputRecord\` lồng nhau vượt \`MAX_DEPTH\` nên bị từ chối dù từng node đều thuộc class được phép.

Cùng ví dụ tương thích Java 9 vì \`ObjectInputFilter\` và \`ObjectInputStream.setObjectInputFilter\` có từ Java 9:

~~~bash
javac --release 9 -Xlint:all -d out9 SerializationAllowListDemo.java
java -cp out9 SerializationAllowListDemo
~~~

## 8. Pattern filter và cấu hình toàn JVM

Với chính sách đơn giản, có thể tạo filter từ chuỗi pattern bằng:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.*;maxdepth=8;maxrefs=100;"
                + "maxbytes=65536;maxarray=256;!*");
~~~

Một pattern filter có thể chỉ định:

- Tên class hoặc package được phép.
- Pattern từ chối class cụ thể.
- \`maxdepth\`, \`maxrefs\`, \`maxbytes\` và \`maxarray\`.
- \`!*\` để từ chối những class không khớp pattern cho phép trước đó.

Cần thiết kế thứ tự pattern cẩn thận. Package pattern rộng có thể vô tình cho phép class không cần thiết. Với allow-list nhỏ và cần kiểm tra theo logic riêng, custom filter thường rõ ràng hơn.

Có thể cấu hình filter JVM-wide bằng system property khi khởi động:

~~~bash
java -Djdk.serialFilter="com.example.dto.*;maxdepth=8;maxrefs=100;maxbytes=65536;maxarray=256;!*" -jar app.jar
~~~

Hoặc thiết lập trong code trước khi tạo các stream:

~~~java
ObjectInputFilter.Config.setSerialFilter(filter);
~~~

Filter JVM-wide chỉ được cấu hình một lần. Việc filtering không tự bật nếu ứng dụng không cấu hình filter hoặc filter factory.

## 9. Filter factory và chính sách theo context

Một ứng dụng có thể có nhiều điểm deserialize với các hợp đồng khác nhau. Ví dụ, một module nhận \`OrderRequest\`, module khác nhận \`AuditEvent\`. Một allow-list toàn JVM có thể quá rộng cho từng context hoặc quá hẹp cho một số thư viện.

Java 17 bổ sung API filter factory qua \`ObjectInputFilter.Config.setSerialFilterFactory\` và property \`jdk.serialFilterFactory\` (JEP 415). Factory được gọi khi tạo \`ObjectInputStream\` và khi filter của stream được thiết lập. Nó nhận filter hiện tại cùng filter được yêu cầu, rồi quyết định filter cuối cùng cho stream.

Factory có thể dùng context của ứng dụng — ví dụ thread-local, module, class loader hoặc caller — để chọn chính sách. Khi cần bảo đảm filter toàn JVM và filter riêng từng stream đều được áp dụng, hãy thiết kế factory để kết hợp chúng một cách tường minh.

Không giả định filter JVM-wide và filter gắn bằng \`setObjectInputFilter\` luôn tự động được hợp nhất. Built-in factory mặc định cung cấp filter tĩnh khi tạo stream và có thể thay thế nó khi gắn filter stream-specific. Nếu hệ thống cần chính sách kết hợp, phải cấu hình factory phù hợp và kiểm thử đường đi đó.

Java 17 cũng bổ sung các tiện ích như \`ObjectInputFilter.merge(...)\` và \`ObjectInputFilter.rejectUndecidedClass(...)\`. Chúng hỗ trợ xây dựng composite filter và chính sách từ chối class chưa được quyết định, nhưng không tự chọn allow-list thay cho ứng dụng.

## 10. Những gì serialization filter không bảo đảm

Serialization filtering là một lớp phòng vệ quan trọng, nhưng không phải sandbox và không biến việc deserialize dữ liệu không tin cậy thành an toàn tuyệt đối.

- Filter không xác thực nội dung nghiệp vụ của field. Hãy kiểm tra dữ liệu sau khi deserialize.
- Filter không thay thế giới hạn byte ở tầng network hoặc file trước khi đọc.
- Filter không ngăn hành vi nguy hiểm bên trong class mà bạn đã cho phép. Hãy chỉ allow class có serialization hook đã được kiểm tra.
- Filter không bảo đảm mọi lỗ hổng trong thư viện hoặc ứng dụng đều được ngăn chặn.
- Filter chỉ áp dụng cho Java Object Serialization qua \`ObjectInputStream\`; nó không tự lọc JSON, XML, YAML hay protocol khác.
- Filter không thay thế xác thực nguồn gửi, integrity, authorization hoặc mã hóa transport.

Nếu có thể thiết kế giao thức mới, ưu tiên định dạng dữ liệu rõ schema và parser có giới hạn. Tránh nhận Java serialized object từ người dùng hoặc hệ thống bên ngoài khi không có lý do tương thích thực sự.

## 11. Lỗi thường gặp

### Nghĩ filtering tự bật mặc định

Không có filter được cấu hình thì \`ObjectInputStream\` không tự có allow-list ứng dụng. Hãy cấu hình stream-specific hoặc JVM-wide policy.

### Trả UNDECIDED cho class không nhận diện

\`UNDECIDED\` không phải từ chối. Với strict allow-list, class không nằm trong danh sách phải trả \`REJECTED\`.

### Chỉ kiểm tra class mà bỏ qua kích thước graph

Một graph chỉ chứa class hợp lệ vẫn có thể quá sâu, có quá nhiều reference hoặc array quá lớn. Luôn đặt resource limits phù hợp.

### Cho phép toàn bộ package để sửa lỗi deserialize

Package có thể chứa class không cần thiết hoặc có serialization hook phức tạp. Hãy allow đúng các DTO cần thiết.

### Gắn filter sau lần readObject đầu tiên

\`setObjectInputFilter\` phải được gọi trước khi đọc object và chỉ được gọi một lần cho stream. Hãy gắn ngay sau khi tạo stream.

### Nghĩ filter kiểm tra mọi field value

Filter kiểm tra class và metric graph, không thay thế validation của domain. Kiểm tra range, length, format và invariant sau khi deserialize.

### Cho rằng filter stream luôn kết hợp với global filter

Cách kết hợp phụ thuộc filter factory. Hãy cấu hình factory và kiểm thử rõ ràng nếu cần enforce cả hai chính sách.

### Coi allow-list là bảo đảm an toàn tuyệt đối

Class được phép vẫn có thể chứa custom serialization logic. Giảm số class được phép, xem xét hook và tránh deserialize dữ liệu không tin cậy nếu có thể.

## 12. Checklist

- [ ] Đã xác định chính xác DTO và class cần khôi phục tại điểm nhận.
- [ ] Đã tạo allow-list nhỏ theo hợp đồng dữ liệu.
- [ ] Đã trả \`REJECTED\` cho class ngoài allow-list.
- [ ] Đã xử lý \`serialClass() == null\` như callback metric, không nhầm với class được cho phép.
- [ ] Đã đặt giới hạn depth, references, stream bytes và array length.
- [ ] Đã gọi \`setObjectInputFilter\` trước lần đọc object đầu tiên.
- [ ] Đã biết filter JVM-wide không tự được bật nếu chưa cấu hình.
- [ ] Đã hiểu filter factory Java 17+ và chính sách kết hợp filter.
- [ ] Đã validate field value và invariant sau khi deserialize.
- [ ] Đã xem xét serialization hook của từng class được allow.
- [ ] Đã tránh deserialize dữ liệu không tin cậy khi có định dạng thay thế phù hợp.
- [ ] Đã biên dịch và chạy ví dụ bằng Java 9+.

## 13. Tài liệu tham khảo

- [Java SE 25 API: ObjectInputFilter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputFilter.html)
- [Java SE 25 API: ObjectInputStream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/ObjectInputStream.html)
- [Java SE 25 Guide: Java Serialization Filters](https://docs.oracle.com/en/java/javase/25/core/java-serialization-filters.html)
- [JEP 290: Filter Incoming Serialization Data](https://openjdk.org/jeps/290)
- [JEP 415: Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)

