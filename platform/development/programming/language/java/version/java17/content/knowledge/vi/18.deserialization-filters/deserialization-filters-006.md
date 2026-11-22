# Filter toàn JVM và filter cho từng ObjectInputStream trong Java 17

## 1. Vì sao cần lọc khi giải tuần tự hóa?

Java serialization chuyển trạng thái đối tượng thành byte stream. Khi chương trình đọc stream bằng `ObjectInputStream`, JVM tái tạo object graph từ dữ liệu nhận được. Quá trình này có thể khởi chạy logic tùy biến trong các lớp được giải tuần tự hóa, chẳng hạn `readObject()`, `readResolve()` hoặc các hành vi được kích hoạt khi đối tượng được tạo.

Nếu dữ liệu đến từ nguồn không đáng tin cậy, attacker có thể điều khiển:

- Những lớp nào được yêu cầu tạo instance.
- Giá trị các trường và quan hệ tham chiếu giữa các object.
- Độ sâu và kích thước của object graph.
- Số lượng object, mảng và dữ liệu mà quá trình giải tuần tự hóa phải xử lý.

Một số thư viện có các lớp *gadget* với hành vi phụ trong quá trình giải tuần tự hóa. Khi những lớp đó được nạp và tạo từ dữ liệu do attacker kiểm soát, ứng dụng có thể gặp lỗi thực thi mã ngoài ý muốn hoặc từ chối dịch vụ.

Java cung cấp **serialization filtering** để kiểm tra lớp và giới hạn tài nguyên trong quá trình giải tuần tự hóa. Trong Java 17, API trung tâm là:

- `ObjectInputFilter`: mô tả chính sách chấp nhận, từ chối hoặc chưa đưa ra kết luận cho dữ liệu đang đọc.
- `ObjectInputFilter.Config`: tạo filter theo chuỗi pattern, cấu hình filter toàn JVM và filter factory.
- `ObjectInputStream.setObjectInputFilter()`: đặt filter cho một stream cụ thể.
- `ObjectInputFilter.Config.setSerialFilterFactory()`: tùy chỉnh cách chọn hoặc kết hợp filter cho từng stream.

Có hai phạm vi chính:

| Phạm vi | Đối tượng áp dụng | Cách cấu hình thường dùng |
|---|---|---|
| **JVM-wide filter** | Các thao tác giải tuần tự hóa trong toàn bộ JVM, thông qua các `ObjectInputStream` có filter được cấu hình theo factory đang hoạt động. | Thuộc tính `jdk.serialFilter` hoặc `ObjectInputFilter.Config.setSerialFilter()`. |
| **Stream-specific filter** | Một instance `ObjectInputStream` cụ thể. | `ObjectInputStream.setObjectInputFilter()`. |

Filter giúp giảm bề mặt tấn công, nhưng **không biến việc giải tuần tự hóa dữ liệu không đáng tin cậy thành an toàn tuyệt đối**. Hãy tránh nhận Java serialized data từ nguồn không tin cậy nếu có thể; ưu tiên định dạng dữ liệu có schema và parser phù hợp với giao thức. Nếu buộc phải dùng Java serialization, hãy xác định chính xác kiểu dữ liệu cần nhận, áp dụng allowlist và giới hạn tài nguyên.

## 2. Mô hình của ObjectInputFilter

`ObjectInputFilter` là functional interface. Một filter nhận `FilterInfo` và trả về một trong ba trạng thái:

~~~java
ObjectInputFilter.Status checkInput(
        ObjectInputFilter.FilterInfo info)
~~~

Ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `ALLOWED` | Filter chấp nhận lớp hoặc thông tin đang kiểm tra. |
| `REJECTED` | Filter từ chối; quá trình đọc object sẽ thất bại. |
| `UNDECIDED` | Filter không đưa ra kết luận cho trường hợp này. Filter khác có thể tiếp tục đánh giá. |

Nếu không có filter nào từ chối, `UNDECIDED` không đồng nghĩa với từ chối. Với một stream không có filter khác, dữ liệu có kết quả `UNDECIDED` vẫn có thể được giải tuần tự hóa. Vì vậy, một allowlist nghiêm ngặt phải có cách từ chối những lớp không khớp, ví dụ pattern kết thúc bằng `!*` hoặc filter tùy biến trả `REJECTED` cho lớp ngoài danh sách.

### 2.1. FilterInfo cung cấp thông tin gì?

`ObjectInputFilter.FilterInfo` cung cấp metadata của quá trình đọc:

| Phương thức | Thông tin |
|---|---|
| `serialClass()` | Lớp đang được kiểm tra; có thể là `null` khi lần gọi chỉ mang thông tin metric/tham chiếu. |
| `arrayLength()` | Độ dài mảng đang được kiểm tra; giá trị âm khi không phải trường hợp mảng. |
| `depth()` | Độ sâu hiện tại của object graph, dựa trên các lời gọi đọc lồng nhau. |
| `references()` | Số lượng object/reference đã được đọc trong stream tính đến hiện tại. |
| `streamBytes()` | Số byte stream đã tiêu thụ theo implementation tại thời điểm kiểm tra. |

Nhờ đó, filter không chỉ kiểm tra *lớp nào* được tạo mà còn kiểm tra *object graph lớn đến đâu*.

### 2.2. Filter được gọi khi nào?

Trong quá trình `readObject()` hoặc `readUnshared()`:

- Filter được gọi khi gặp lớp mới trong stream, trước khi instance của lớp đó được tạo và giải tuần tự hóa.
- Các lớp trong mô tả kiểu của stream có thể được kiểm tra riêng, bao gồm superclass và interface được tham chiếu tường minh trong stream.
- Mảng được kiểm tra cùng kiểu mảng và độ dài.
- Tham chiếu tới object đã đọc cũng có thể làm filter được gọi để kiểm tra depth, references và stream bytes.
- Filter không được gọi cho primitive và các giá trị `String` được mã hóa trực tiếp theo cách cụ thể trong stream.

Không nên giả định filter chỉ được gọi đúng một lần cho mỗi object. Lớp mới và các metric của object graph có thể tạo nhiều lần gọi. Cũng không nên giả định filter được gọi cho từng field primitive hoặc từng chuỗi.

### 2.3. Từ chối xảy ra như thế nào?

Nếu filter đang hoạt động trả `REJECTED`, `readObject()` hoặc `readUnshared()` ném `InvalidClassException` và quá trình giải tuần tự hóa bị dừng. Lỗi này là lỗi chính sách lọc; nó khác với lỗi đọc byte stream hỏng hoặc không tìm thấy lớp.

Filter nên được thiết kế stateless nếu có thể, dựa trên thông tin trong `FilterInfo`. Có thể duy trì trạng thái giữa các lần gọi, nhưng cần quản lý cẩn thận vì filter có thể được gọi nhiều lần và quá trình đọc object graph có cấu trúc lồng nhau.

## 3. Filter toàn JVM (JVM-wide filter)

JVM-wide filter là chính sách tĩnh dùng chung cho tiến trình Java. Nó phù hợp khi ứng dụng có một bộ quy tắc chung, chẳng hạn:

- Từ chối một số lớp hoặc package không được phép xuất hiện trong serialized data.
- Chỉ cho phép một tập lớp mà ứng dụng cần giải tuần tự hóa.
- Giới hạn độ sâu object graph, số reference, kích thước mảng và tổng byte stream.

Java 17 hỗ trợ cấu hình filter toàn JVM theo hai cách phổ biến: thuộc tính lúc khởi chạy và cấu hình bằng API.

### 3.1. Cấu hình qua system property khi khởi chạy

Dùng thuộc tính `jdk.serialFilter`:

~~~text
java "-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;!*" com.example.Main
~~~

Ví dụ trên:

- Giới hạn độ sâu graph tối đa là 20.
- Giới hạn số reference tối đa là 1.000.
- Giới hạn số byte stream tối đa là 1.048.576.
- Giới hạn độ dài mảng tối đa là 10.000.
- Cho phép các lớp trong package `com.example.dto` và các subpackage.
- Từ chối mọi lớp không khớp các pattern đã cho.

Đây là ví dụ cú pháp; danh sách lớp thực tế phải khớp với object graph của ứng dụng. Không nên sao chép một allowlist rộng mà chưa kiểm tra các lớp phụ thuộc cần thiết.

Thuộc tính system property được đọc khi lớp `ObjectInputFilter.Config` khởi tạo. Nếu muốn dùng cấu hình lúc khởi chạy, hãy truyền `-Djdk.serialFilter` ngay trong lệnh `java`.

### 3.2. Cấu hình qua Security property của JDK

Có thể đặt `jdk.serialFilter` trong file:

~~~text
$JAVA_HOME/conf/security/java.security
~~~

Ví dụ:

~~~properties
jdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;!*
~~~

Security property áp dụng cho các ứng dụng chạy bằng runtime được cấu hình. Nếu đồng thời có system property `jdk.serialFilter`, system property có ưu tiên cao hơn.

Đây là lựa chọn dành cho cấu hình ở cấp runtime; hãy quản lý thay đổi file bảo mật của JDK theo quy trình triển khai và kiểm tra ảnh hưởng tới các ứng dụng cùng dùng runtime đó.

### 3.3. Cấu hình bằng Java API

Nếu ứng dụng cần tạo filter trong mã nguồn, dùng `ObjectInputFilter.Config.createFilter()` rồi đặt bằng `setSerialFilter()`:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=1000;maxbytes=1048576;"
                        + "maxarray=10000;com.example.dto.**;!*");

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

Hãy thực hiện cấu hình này lúc khởi động ứng dụng, trước khi tạo các `ObjectInputStream` cần được bảo vệ. `setSerialFilter()` chỉ thiết lập filter tĩnh toàn JVM nếu nó chưa được cấu hình hoặc đặt trước đó. Nếu filter đã được thiết lập, phương thức có thể ném `IllegalStateException`.

Có thể đọc filter hiện tại bằng:

~~~java
ObjectInputFilter current =
        ObjectInputFilter.Config.getSerialFilter();

System.out.println(current);
~~~

Nếu filter chưa được cấu hình, `getSerialFilter()` trả về `null`.

### 3.4. Không dùng System.setProperty quá muộn

Đoạn sau không phải cách đáng tin cậy để cấu hình filter:

~~~java
System.setProperty(
        "jdk.serialFilter",
        "maxdepth=20;maxrefs=1000;!*");
~~~

`jdk.serialFilter` được đọc khi `ObjectInputFilter.Config` khởi tạo. Gọi `System.setProperty()` sau khi lớp này đã khởi tạo **không tự cấu hình lại filter**. Hãy dùng `-Djdk.serialFilter` lúc khởi chạy, Security property hoặc `Config.setSerialFilter()`.

## 4. Cú pháp pattern của filter

`ObjectInputFilter.Config.createFilter(String)` tạo filter từ một chuỗi pattern. Các pattern được ngăn cách bằng dấu chấm phẩy `;`. Khoảng trắng là một phần của pattern, nên không thêm dấu cách tùy tiện.

Có hai nhóm pattern:

1. Pattern giới hạn tài nguyên.
2. Pattern tên lớp/package/module để chấp nhận hoặc từ chối lớp.

### 4.1. Giới hạn tài nguyên

| Pattern | Giới hạn |
|---|---|
| `maxdepth=n` | Độ sâu tối đa của object graph. |
| `maxrefs=n` | Số reference tối đa. |
| `maxbytes=n` | Số byte tối đa được đọc từ stream. |
| `maxarray=n` | Độ dài mảng tối đa. |

Ví dụ:

~~~java
ObjectInputFilter limits = ObjectInputFilter.Config.createFilter(
        "maxdepth=15;maxrefs=500;maxbytes=2000000;maxarray=50000");
~~~

Các giới hạn được kiểm tra trước khi xét pattern tên lớp. Nếu một giới hạn bị vượt, filter trả `REJECTED`.

Giới hạn nên được chọn từ kích thước hợp lệ của dữ liệu thực tế, cộng thêm biên phù hợp. Đặt quá thấp có thể làm dữ liệu hợp lệ bị từ chối; đặt quá cao có thể không giúp hạn chế tiêu thụ tài nguyên đáng kể.

### 4.2. Pattern tên lớp chính xác

Pattern có thể khớp tên đầy đủ của lớp:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "com.example.dto.OrderSnapshot;!*");
~~~

Trong ví dụ, `OrderSnapshot` được phép và các lớp khác không khớp sẽ bị từ chối. Đây là allowlist theo tên lớp.

### 4.3. Wildcard package

Các dạng thường dùng:

| Pattern | Ý nghĩa |
|---|---|
| `com.example.dto.*` | Các lớp trực tiếp trong package `com.example.dto`. |
| `com.example.dto.**` | Các lớp trong package và mọi subpackage. |
| `com.example.dto.Order*` | Các tên lớp bắt đầu bằng `com.example.dto.Order`. |
| `*` | Mọi tên lớp. |

`.*` không bao gồm subpackage. Nếu muốn bao phủ các package con, dùng `.**`.

### 4.4. Pattern từ chối với dấu !

Đặt `!` trước pattern để từ chối lớp khớp:

~~~text
!com.example.internal.UnsafeType;com.example.dto.**;!*
~~~

Ví dụ:

- Từ chối `com.example.internal.UnsafeType`.
- Cho phép các lớp trong `com.example.dto` và subpackage.
- Từ chối mọi lớp còn lại.

Pattern được xét từ trái sang phải; pattern lớp đầu tiên khớp quyết định trạng thái `ALLOWED` hoặc `REJECTED`. Nếu không có pattern lớp nào khớp, kết quả là `UNDECIDED`. Vì vậy, nếu muốn allowlist thực sự, hãy thêm `!*` ở cuối để từ chối các lớp còn lại.

### 4.5. Pattern có module name

Có thể thêm tên module trước dấu gạch chéo:

~~~text
java.base/java.util.*;com.example.app/com.example.dto.**
~~~

Phần trước dấu `/` là tên module; phần sau là pattern tên lớp. Nếu không có module prefix, việc so khớp chỉ dựa trên tên lớp.

### 4.6. Pattern không kiểm tra quan hệ kế thừa

Pattern khớp tên lớp, package hoặc module. Nó không thể nói "cho phép mọi lớp triển khai interface X" hoặc "cho phép mọi lớp con của superclass Y". Pattern cũng không kiểm tra interface được một lớp triển khai, trừ interface được tham chiếu tường minh trong stream.

Nếu chính sách cần dựa vào kiểu cha/interface, hãy viết filter tùy biến với `Class.isAssignableFrom()`. Pattern phù hợp cho các trường hợp đơn giản theo tên.

### 4.7. Lớp không khớp pattern chưa chắc bị từ chối

Ví dụ:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter("com.example.dto.*");
~~~

Lớp thuộc package khớp sẽ được `ALLOWED`. Lớp không khớp trả `UNDECIDED`, không tự động bị từ chối. Nếu không có filter khác từ chối, quá trình giải tuần tự hóa vẫn có thể tiếp tục.

Muốn chỉ cho phép package đó:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.*;!*");
~~~

## 5. Filter cho từng ObjectInputStream

JVM-wide filter phù hợp với chính sách chung. Nhưng nhiều ứng dụng có nhiều luồng dữ liệu khác nhau:

- Một stream chỉ nhận DTO đơn hàng.
- Một stream chỉ nhận metadata báo cáo.
- Một stream khác nhận dữ liệu nội bộ có tập kiểu riêng.

Trong trường hợp này, có thể đặt filter trực tiếp lên từng `ObjectInputStream` bằng `setObjectInputFilter()`.

### 5.1. Thời điểm đặt filter

Filter phải được đặt **sau khi tạo ObjectInputStream và trước khi đọc bất kỳ object nào**:

~~~java
try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    input.setObjectInputFilter(myFilter);

    Object value = input.readObject();
}
~~~

`setObjectInputFilter()` chỉ được gọi một lần cho một stream và phải gọi trước `readObject()` hoặc `readUnshared()` đầu tiên. Gọi muộn hoặc gọi lần thứ hai có thể ném `IllegalStateException`.

Có thể xem filter đang hoạt động trên stream bằng `getObjectInputFilter()`:

~~~java
ObjectInputFilter active = input.getObjectInputFilter();
~~~

Kết quả là filter mà factory toàn JVM trả về cho stream; nó có thể là filter toàn JVM, filter riêng, hoặc filter đã được kết hợp tùy factory.

### 5.2. Filter tùy biến bằng lambda

Ví dụ filter chỉ cho phép một kiểu DTO và giới hạn object graph:

~~~java
ObjectInputFilter orderFilter = info -> {
    if (info.depth() > 16
            || info.references() > 1000
            || info.streamBytes() > 1_000_000
            || (info.arrayLength() >= 0
                    && info.arrayLength() > 10_000)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == OrderSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
~~~

Chính sách trên:

- Từ chối graph sâu hơn 16.
- Từ chối khi có hơn 1.000 references.
- Từ chối stream lớn hơn 1 MB.
- Từ chối mảng có hơn 10.000 phần tử.
- Chỉ cho phép lớp `OrderSnapshot`; các lớp khác bị từ chối.
- Khi `serialClass()` là `null`, filter không đưa ra quyết định về lớp nhưng vẫn đã kiểm tra metric.

Đây là allowlist rất hẹp. Nếu object graph thực tế cần thêm kiểu khác, chẳng hạn một DTO con hoặc kiểu collection được serialize, phải đưa các kiểu đó vào chính sách sau khi kiểm tra hợp đồng dữ liệu. Không nên mở rộng thành toàn bộ package hoặc toàn bộ module chỉ để làm lỗi biến mất.

### 5.3. Tạo filter theo pattern cho một stream

Không cần viết lambda nếu quy tắc chỉ gồm tên lớp và giới hạn:

~~~java
ObjectInputFilter orderFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=16;maxrefs=1000;maxbytes=1000000;"
                        + "maxarray=10000;"
                        + "com.example.dto.OrderSnapshot;!*");

try (ObjectInputStream input =
        new ObjectInputStream(source)) {
    input.setObjectInputFilter(orderFilter);
    Object value = input.readObject();
}
~~~

Filter pattern thích hợp cho allowlist và giới hạn đơn giản. Dùng filter tùy biến khi cần kiểm tra kiểu theo quan hệ kế thừa, module, class loader hoặc logic phức tạp hơn.

## 6. Ví dụ hoàn chỉnh: filter riêng cho stream đọc OrderSnapshot

Ví dụ sau tạo một DTO serializable nhỏ, ghi nó thành byte array rồi đọc lại bằng `ObjectInputStream` đã được đặt filter. Trong thực tế, byte stream có thể đến từ file, socket hoặc kho lưu trữ; ví dụ dùng byte array để tập trung vào cơ chế filter.

Tạo file `StreamFilterDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class StreamFilterDemo {
    private StreamFilterDemo() {
    }

    static final class OrderSnapshot implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String orderId;
        private final long quantity;

        OrderSnapshot(String orderId, long quantity) {
            this.orderId = orderId;
            this.quantity = quantity;
        }

        @Override
        public String toString() {
            return "OrderSnapshot[orderId=" + orderId
                    + ", quantity=" + quantity + "]";
        }
    }

    private static ObjectInputFilter.Status orderFilter(
            ObjectInputFilter.FilterInfo info) {

        if (info.depth() > 16
                || info.references() > 1000
                || info.streamBytes() > 1_000_000
                || (info.arrayLength() >= 0
                        && info.arrayLength() > 10_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        return type == OrderSnapshot.class
                ? ObjectInputFilter.Status.ALLOWED
                : ObjectInputFilter.Status.REJECTED;
    }

    private static byte[] serialize(OrderSnapshot snapshot)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                new ObjectOutputStream(bytes)) {
            output.writeObject(snapshot);
        }
        return bytes.toByteArray();
    }

    private static OrderSnapshot deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            input.setObjectInputFilter(StreamFilterDemo::orderFilter);

            Object value = input.readObject();
            if (!(value instanceof OrderSnapshot snapshot)) {
                throw new IOException("Unexpected object type");
            }
            return snapshot;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = serialize(new OrderSnapshot("ORD-42", 3));

        OrderSnapshot snapshot = deserialize(bytes);
        System.out.println(snapshot);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~text
javac --release 17 -encoding UTF-8 StreamFilterDemo.java
java StreamFilterDemo
~~~

Đầu ra:

~~~text
OrderSnapshot[orderId=ORD-42, quantity=3]
~~~

Ví dụ này minh họa filter cho một stream. Lớp `String` được xử lý đặc biệt trong serialization và không gọi filter như một class thông thường; filter vẫn kiểm tra class DTO và các metric của object graph.

Nếu stream chứa một lớp khác không nằm trong allowlist, `orderFilter` trả `REJECTED` và `readObject()` thất bại với `InvalidClassException`. Trong ứng dụng thật, hãy giữ danh sách kiểu cho phép càng cụ thể càng tốt.

## 7. Quan hệ giữa filter toàn JVM và filter riêng từng stream

Đây là phần cần chú ý nhất khi ứng dụng dùng cả hai phạm vi.

### 7.1. Factory mặc định của Java 17

Nếu không cài filter factory tùy biến, Java sử dụng built-in filter factory. Hành vi của factory mặc định:

- Khi tạo `ObjectInputStream`, filter toàn JVM tĩnh được dùng làm filter ban đầu cho stream.
- Khi gọi `setObjectInputFilter()`, filter riêng được yêu cầu sẽ **thay thế filter toàn JVM tĩnh** trên stream đó, theo hành vi built-in factory.

Do đó, không nên mặc định rằng gọi `setObjectInputFilter(localFilter)` sẽ tự động kết hợp `localFilter` với JVM-wide filter. Với factory mặc định, filter riêng có thể thay filter toàn JVM trên stream đó.

Ví dụ:

~~~java
// JVM-wide filter đã được cấu hình.
ObjectInputFilter global =
        ObjectInputFilter.Config.getSerialFilter();

try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    // Với built-in factory mặc định, localFilter thay filter hiện tại
    // trên stream này thay vì tự động merge với global.
    input.setObjectInputFilter(localFilter);
    Object value = input.readObject();
}
~~~

Điều này không có nghĩa JVM-wide filter vô ích. Nó là chính sách mặc định cho các stream không đặt filter riêng. Nhưng nếu muốn mọi stream đều chịu cả giới hạn chung và allowlist riêng, cần thiết kế factory kết hợp các filter.

### 7.2. Filter factory là gì?

Filter factory là một hàm có kiểu:

~~~java
BinaryOperator<ObjectInputFilter>
~~~

Factory được gọi:

1. Khi một `ObjectInputStream` được tạo.
2. Khi `setObjectInputFilter()` được gọi trên stream.

Nó nhận hai đối số:

- `current`: filter đang được dùng cho stream; lần gọi đầu tiên thường là `null`.
- `requested`: filter toàn JVM khi tạo stream, hoặc filter riêng được truyền vào `setObjectInputFilter()`.

Factory trả về filter thực sự được gắn vào stream. Nó có thể chọn filter theo context, ví dụ thread-local, call stack, module, library hoặc class loader.

### 7.3. Cấu hình factory bằng Java 17

Java 17 bổ sung `ObjectInputFilter.Config.setSerialFilterFactory()`. Có thể cấu hình một factory đơn giản để kết hợp filter hiện tại và filter mới:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory(
        (current, requested) -> {
            if (current == null) {
                return requested;
            }
            if (requested == null) {
                return current;
            }
            return ObjectInputFilter.merge(current, requested);
        });
~~~

Factory phải được cấu hình **trước khi bất kỳ `ObjectInputStream` nào được tạo**. Nó chỉ có thể được thiết lập một lần. Nếu factory đã được cấu hình bằng system property hoặc Security property `jdk.serialFilterFactory` lúc khởi tạo, không thể thay bằng lời gọi `setSerialFilterFactory()`.

Có thể cấu hình factory lúc khởi chạy:

~~~text
java -Djdk.serialFilterFactory=com.example.SecurityFilterFactory com.example.Main
~~~

Class factory phải public, có public constructor không tham số, triển khai `BinaryOperator<ObjectInputFilter>` và có thể được application class loader truy cập.

### 7.4. Hiểu chính xác phép merge

`ObjectInputFilter.merge(first, second)` kết hợp kết quả của hai filter theo quy tắc:

| Kết quả filter A | Kết quả filter B | Kết quả merge |
|---|---|---|
| Có ít nhất một `REJECTED` | Bất kỳ | `REJECTED` |
| Không có `REJECTED` và có ít nhất một `ALLOWED` | `ALLOWED` hoặc `UNDECIDED` | `ALLOWED` |
| Cả hai `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

Vì vậy, `merge` **không phải phép giao hai allowlist**. Nếu một filter cho phép lớp và filter còn lại không đưa ra kết luận, kết quả vẫn là `ALLOWED`. Nếu muốn một filter từ chối lớp lạ, hãy làm cho filter đó trả `REJECTED` đối với lớp không nằm trong allowlist.

Ví dụ, một cấu hình phù hợp là:

- Global filter chỉ áp đặt giới hạn tài nguyên; nếu vượt giới hạn thì trả `REJECTED`, còn lớp không được đánh giá thì trả `UNDECIDED`.
- Filter riêng của stream là allowlist chặt, cho phép kiểu cần thiết và trả `REJECTED` cho mọi lớp khác.
- Factory merge hai filter. Kết quả vẫn từ chối khi vượt giới hạn toàn JVM hoặc khi lớp không thuộc allowlist của stream.

Không nên merge hai filter có chính sách lớp phức tạp mà chưa hiểu rõ ý nghĩa `ALLOWED`, `REJECTED` và `UNDECIDED`. Một cấu hình sai có thể vô tình mở rộng tập lớp được phép.

## 8. Các phương thức hỗ trợ tạo filter trong Java 17

Ngoài `createFilter()`, `ObjectInputFilter` cung cấp các phương thức tĩnh để tạo và kết hợp filter.

### 8.1. `allowFilter()`

Tạo filter chấp nhận lớp khớp predicate:

~~~java
ObjectInputFilter numbers = ObjectInputFilter.allowFilter(
        type -> Number.class.isAssignableFrom(type),
        ObjectInputFilter.Status.UNDECIDED);
~~~

Lớp là subtype của `Number` được trả `ALLOWED`; lớp khác trả `UNDECIDED`. Nếu muốn từ chối các lớp khác, hãy dùng `REJECTED` làm trạng thái thay thế hoặc kết hợp với `rejectUndecidedClass()` theo chính sách phù hợp.

### 8.2. `rejectFilter()`

Tạo filter từ chối lớp khớp predicate:

~~~java
ObjectInputFilter rejectInternal = ObjectInputFilter.rejectFilter(
        type -> type.getName().startsWith("com.example.internal."),
        ObjectInputFilter.Status.UNDECIDED);
~~~

Các lớp thuộc package nội bộ bị từ chối; lớp khác chưa bị filter này đánh giá.

### 8.3. `rejectUndecidedClass()`

Phương thức này bọc một filter và chuyển kết quả `UNDECIDED` thành `REJECTED` đối với lớp phù hợp. Nó hữu ích khi muốn tạo allowlist: chỉ lớp được filter xác nhận `ALLOWED` mới tiếp tục.

~~~java
ObjectInputFilter allowNumbers = ObjectInputFilter.allowFilter(
        type -> Number.class.isAssignableFrom(type),
        ObjectInputFilter.Status.UNDECIDED);

ObjectInputFilter strictNumbers =
        ObjectInputFilter.rejectUndecidedClass(allowNumbers);
~~~

Các metric-only callback có `serialClass() == null` vẫn có thể trả `UNDECIDED`; việc chuyển đổi tập trung vào quyết định cho lớp. Với mảng, API kiểm tra cả kiểu component theo quy tắc riêng. Hãy đọc Javadoc khi thiết kế allowlist cho mảng.

### 8.4. `merge()`

`merge()` kết hợp hai filter theo bảng ở phần trước. Đây là công cụ quan trọng khi triển khai factory, nhưng phải hiểu rằng `ALLOWED` từ một filter có thể thắng `UNDECIDED` của filter kia; chỉ `REJECTED` mới luôn phủ quyết.

## 9. Giới hạn của serialization filter

Serialization filter là lớp phòng vệ hữu ích, nhưng không thay thế các biện pháp bảo vệ khác.

### 9.1. Filter không kiểm tra giá trị từng field

Filter kiểm tra class, array length và metric của graph. Nó không xác nhận rằng:

- `quantity` phải lớn hơn 0.
- `amount` không âm.
- `customerId` có định dạng hợp lệ.
- Một chuỗi không vượt giới hạn nghiệp vụ.
- Trạng thái object phù hợp với quy trình nghiệp vụ.

Hãy validate dữ liệu sau khi giải tuần tự hóa hoặc trong logic đọc object theo hợp đồng dữ liệu. Các bất biến của lớp cũng cần được bảo vệ.

### 9.2. Filter không biến lớp được phép thành lớp an toàn

Nếu một lớp nằm trong allowlist nhưng có `readObject()` nguy hiểm hoặc có thể gọi hành vi phụ không mong muốn, filter vẫn có thể cho phép lớp đó. Allowlist phải được xây dựng từ những kiểu mà ứng dụng thực sự cần và đã xem xét hành vi.

### 9.3. Filter không kiểm tra primitive và String như class thông thường

Các giá trị primitive và `String` được mã hóa trực tiếp không kích hoạt kiểm tra class giống object thông thường. Do đó, nếu cần giới hạn độ dài chuỗi hoặc quy tắc nội dung, hãy validate sau khi đọc; đừng giả định `maxarray` sẽ giới hạn chuỗi.

### 9.4. Filter không thay thế giới hạn giao thức

Giới hạn `maxbytes` có ích, nhưng ứng dụng vẫn nên giới hạn kích thước dữ liệu ở tầng transport trước khi tạo `ObjectInputStream`. Với socket hoặc upload, cần timeout, giới hạn request body, xác thực nguồn và giới hạn tài nguyên tổng thể.

### 9.5. Filter chỉ áp dụng cho Java serialization filtering

`ObjectInputFilter` không tự động lọc JSON parser, XML parser, YAML parser hoặc mọi thư viện chuyển đổi object khác. Mỗi định dạng cần parser, schema và giới hạn riêng.

### 9.6. Serialization filtering không bật mặc định

Java serialization filtering không tự động bật nếu ứng dụng không cấu hình filter qua system property, Security property hoặc API. Hãy kiểm tra cấu hình runtime và xác nhận filter thực sự được gắn vào stream bằng `getObjectInputFilter()` khi cần chẩn đoán.

## 10. Logging để quan sát quyết định của filter

Java có logger `java.io.serialization` để ghi nhận các hành động lọc. Đây là công cụ chẩn đoán hữu ích khi xác định lớp nào được đọc, lớp nào bị từ chối hoặc vì sao một giới hạn bị vượt.

Trong file cấu hình logging của JDK:

~~~properties
java.io.serialization.level = FINE
~~~

Mức `FINE` ghi các kết quả từ chối. Nếu cần xem mọi kết quả:

~~~properties
java.io.serialization.level = FINEST
~~~

Không nên bật log chi tiết vô thời hạn trong production nếu lưu lượng lớn. Log có thể tiết lộ tên lớp, cấu trúc dữ liệu hoặc thông tin nội bộ; hãy giới hạn quyền truy cập và thời gian lưu.

## 11. Cách lựa chọn phạm vi filter

| Tình huống | Hướng triển khai |
|---|---|
| Ứng dụng có một chính sách giải tuần tự hóa chung | Đặt JVM-wide filter qua `jdk.serialFilter` hoặc `Config.setSerialFilter()`. |
| Mỗi stream nhận một tập DTO khác nhau | Đặt stream-specific filter bằng `setObjectInputFilter()` trước khi đọc. |
| Muốn giới hạn tài nguyên toàn JVM và allowlist riêng theo stream | Cấu hình filter factory để kết hợp filter toàn JVM và filter riêng. |
| Chỉ cần chặn một vài lớp đã xác định | Dùng reject-list, nhưng vẫn cân nhắc allowlist và giới hạn tài nguyên. |
| Chỉ cho phép một tập nhỏ lớp đã biết | Dùng allowlist kết thúc bằng `!*` hoặc filter tùy biến trả `REJECTED` cho lớp không hợp lệ. |
| Cần quyết định theo quan hệ kế thừa hoặc context | Dùng filter tùy biến hoặc filter factory, không chỉ pattern theo tên. |

Một chính sách có thể kết hợp hai lớp:

~~~text
JVM-wide:
  - Giới hạn depth, references, bytes, array length.
  - Quy tắc từ chối chung cho toàn tiến trình.

Per ObjectInputStream:
  - Allowlist các kiểu mà stream này được phép đọc.
  - Giới hạn bổ sung theo định dạng dữ liệu cụ thể.

Filter factory:
  - Chọn hoặc kết hợp các filter.
  - Giữ lại các quy tắc toàn JVM khi stream có filter riêng.
~~~

Không phải ứng dụng nào cũng cần filter factory. Với một chính sách chung và không có filter riêng, JVM-wide filter là đủ. Factory chỉ cần thiết khi muốn tùy biến cách chọn/kết hợp filter theo từng stream hoặc context.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ filter tự bật trong Java 17 | Filtering không được cấu hình mặc định. | Đặt `jdk.serialFilter` hoặc cấu hình qua `ObjectInputFilter.Config`. |
| Gọi `System.setProperty("jdk.serialFilter", ...)` nhưng filter không đổi | `Config` đã khởi tạo; property được đọc ở thời điểm khởi tạo lớp. | Đặt system property lúc khởi chạy hoặc dùng `setSerialFilter()` trước khi filter được cấu hình. |
| `setSerialFilter()` ném `IllegalStateException` | JVM-wide filter đã được cấu hình hoặc đặt trước đó. | Chọn một nơi cấu hình duy nhất, tốt nhất lúc khởi động. |
| `setObjectInputFilter()` ném `IllegalStateException` | Đã đọc object hoặc đã đặt filter cho stream. | Đặt filter ngay sau constructor `ObjectInputStream` và chỉ gọi một lần. |
| Filter riêng làm mất giới hạn toàn JVM | Built-in filter factory mặc định thay static global filter bằng filter riêng trên stream. | Dùng filter factory để kết hợp hai chính sách nếu cần cả hai. |
| Lớp ngoài allowlist vẫn được đọc | Filter trả `UNDECIDED` thay vì `REJECTED` cho lớp không khớp. | Thêm `!*` vào pattern hoặc trả `REJECTED` cho lớp ngoài danh sách. |
| Pattern package không khớp subpackage | Dùng `.*` thay vì `.**`. | Dùng wildcard đúng với phạm vi package mong muốn. |
| Cho rằng `merge` là phép giao hai allowlist | `ALLOWED` từ một filter thắng `UNDECIDED` từ filter kia; chỉ `REJECTED` luôn phủ quyết. | Thiết kế trạng thái và factory theo chính sách rõ ràng. |
| Chỉ kiểm tra tên lớp mà bỏ qua graph lớn | Filter không giới hạn depth, references, array length hoặc bytes. | Kết hợp allowlist với resource limits. |
| Dùng filter để xác nhận dữ liệu nghiệp vụ | Filter không kiểm tra giá trị từng field. | Validate object sau khi đọc theo quy tắc miền. |
| Nghĩ filter bảo vệ mọi parser | `ObjectInputFilter` chỉ áp dụng cho Java serialization. | Dùng cơ chế giới hạn và validation riêng cho JSON/XML/định dạng khác. |

## 13. Bài tập thực hành

### Bài tập 1 — Cấu hình filter toàn JVM

Tạo một filter bằng `Config.createFilter()` với các giới hạn:

- Depth tối đa 12.
- References tối đa 500.
- Stream bytes tối đa 500.000.
- Array length tối đa 5.000.

Đặt filter bằng `Config.setSerialFilter()` trước khi tạo `ObjectInputStream`. Gọi `getSerialFilter()` để hiển thị cấu hình đang hoạt động.

### Bài tập 2 — Viết allowlist cho một stream

Tạo hai lớp serializable `CustomerSnapshot` và `InternalCommand`. Viết filter cho phép `CustomerSnapshot` và từ chối `InternalCommand` cùng mọi kiểu khác. Đặt filter trước `readObject()` và quan sát ngoại lệ khi đọc object không được phép.

### Bài tập 3 — Phân biệt UNDECIDED và REJECTED

Tạo filter chỉ trả `ALLOWED` cho `CustomerSnapshot` và `UNDECIDED` cho các kiểu khác. Thử đọc một object thuộc kiểu khác khi không có filter nào khác. Sau đó đổi trạng thái mặc định thành `REJECTED`. Giải thích vì sao hai lần chạy có kết quả khác nhau.

### Bài tập 4 — Giữ cả giới hạn toàn JVM và filter riêng

Đặt global filter chỉ kiểm tra resource limits. Cài filter factory bằng `setSerialFilterFactory()` để kết hợp filter hiện tại và filter được yêu cầu cho stream. Đặt một allowlist riêng cho `CustomerSnapshot`. Thử object graph vượt `maxdepth` và một lớp không nằm trong allowlist.

### Bài tập 5 — Kiểm tra pattern

Với các pattern `com.example.dto.*`, `com.example.dto.**`, `!com.example.dto.InternalCommand` và `!*`, hãy xác định lớp nào được cho phép/từ chối. Tạo một lớp trong subpackage để phân biệt `.*` với `.**`.

### Bài tập 6 — Giới hạn tài nguyên

Tạo object graph có nhiều tầng lồng nhau và một mảng lớn. Đặt `maxdepth` và `maxarray` nhỏ để quan sát filter từ chối. Giải thích vì sao giới hạn tài nguyên cần được chọn theo kích thước dữ liệu hợp lệ của ứng dụng.

### Gợi ý tự đối chiếu

- Bài 1: Ghép các pattern bằng dấu `;` và gọi `setSerialFilter` trước khi tạo stream.
- Bài 2: Dùng so sánh class token `type == CustomerSnapshot.class` và trả `REJECTED` cho kiểu khác.
- Bài 3: `UNDECIDED` không tự từ chối; nếu không có filter khác, object vẫn có thể được đọc.
- Bài 4: Factory được gọi lúc tạo stream và khi đặt filter riêng; `merge` cần giữ quy tắc `REJECTED` phủ quyết.
- Bài 5: `.*` chỉ khớp package trực tiếp; `.**` bao gồm subpackage.
- Bài 6: `depth`, `arrayLength`, `references` và `streamBytes` là các metric khác nhau, cần kiểm tra theo yêu cầu ứng dụng.

## 14. Các nguyên tắc cần ghi nhớ

- Java serialization filtering dùng `ObjectInputFilter` để kiểm tra lớp và độ phức tạp của object graph khi đọc.
- JVM-wide filter đặt chính sách chung qua `jdk.serialFilter` hoặc `Config.setSerialFilter()`.
- Stream-specific filter đặt bằng `ObjectInputStream.setObjectInputFilter()` và phải được gọi trước khi đọc object đầu tiên.
- Với built-in filter factory, filter riêng có thể thay filter toàn JVM trên stream đó; muốn kết hợp cả hai, cấu hình filter factory phù hợp.
- `jdk.serialFilterFactory` và `Config.setSerialFilterFactory()` cho phép tùy biến việc chọn/kết hợp filter; factory phải được cấu hình trước khi tạo bất kỳ `ObjectInputStream` nào.
- `ALLOWED` chấp nhận, `REJECTED` từ chối, `UNDECIDED` chưa đưa ra kết luận. Không dùng `UNDECIDED` nếu mục tiêu là allowlist nghiêm ngặt mà không có filter khác.
- Pattern hỗ trợ tên lớp, package, module và giới hạn `maxdepth`, `maxrefs`, `maxbytes`, `maxarray`.
- `.*` khớp package trực tiếp; `.**` bao gồm subpackage; `!*` từ chối lớp không khớp các pattern trước.
- `merge` trả `REJECTED` nếu một filter từ chối, `ALLOWED` nếu không có từ chối và có ít nhất một filter cho phép, còn lại là `UNDECIDED`.
- Filter không xác thực giá trị field, không làm lớp được phép trở nên an toàn và không áp dụng cho mọi định dạng serialization khác.
- Kết hợp allowlist, giới hạn tài nguyên, kiểm tra dữ liệu sau khi đọc và kiểm soát nguồn dữ liệu. Tránh giải tuần tự hóa dữ liệu không đáng tin cậy nếu có thể.

### Tài liệu tham khảo

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html).
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html).
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html).
- [Oracle Java 17 — Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html).
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290).
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415).
