# Từ chối lớp chưa quyết định bằng `rejectUndecidedClass` trong Java 17

Java Serialization cho phép chuyển object graph thành byte và khôi phục lại object graph từ byte. Khi đọc dữ liệu tuần tự hóa, `ObjectInputFilter` có thể kiểm tra lớp đang được tạo và các chỉ số tài nguyên của quá trình giải tuần tự hóa. Một trong ba kết quả của filter là `UNDECIDED` — trạng thái rất dễ bị hiểu nhầm là từ chối.

Trong thực tế, **`UNDECIDED` có nghĩa filter chưa đưa ra quyết định**. Nếu không có filter nào trả về `REJECTED`, quá trình giải tuần tự hóa vẫn có thể tiếp tục. Điều đó có thể khiến một lớp ngoài danh sách dự kiến lọt qua khi filter chỉ kiểm tra một số lớp quen thuộc rồi trả về `UNDECIDED` cho các lớp còn lại.

Java 17 cung cấp `ObjectInputFilter.rejectUndecidedClass(filter)` để bao một filter hiện có: các lớp chưa được filter xác nhận rõ ràng sẽ bị từ chối, với quy tắc xử lý riêng cho array và các lần kiểm tra chỉ có metric. Bài này giải thích cách dùng API đó để xây dựng allowlist rõ ràng, kết hợp giới hạn tài nguyên và áp dụng filter trước khi gọi `readObject`.

> **Phiên bản:** `ObjectInputFilter` có từ Java 9. Các factory method `allowFilter`, `rejectFilter`, `merge` và `rejectUndecidedClass` có từ Java 17. Đây là API chính thức, không phải preview feature.

## 1. Vì sao cần từ chối kết quả UNDECIDED?

Một filter giải tuần tự hóa trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa | Tác động |
|---|---|---|
| `ALLOWED` | Filter xác nhận dữ liệu được phép | Filter không phản đối lớp/đối tượng hiện tại |
| `REJECTED` | Filter xác định dữ liệu không được phép | Quá trình giải tuần tự hóa bị từ chối |
| `UNDECIDED` | Filter không đưa ra quyết định | Filter chưa cho phép cũng chưa từ chối |

Điểm quan trọng: **`UNDECIDED` không đồng nghĩa với `REJECTED`**. Nó biểu thị filter không có ý kiến về trường hợp đang kiểm tra. Nếu kết quả cuối cùng vẫn là `UNDECIDED`, cơ chế giải tuần tự hóa không coi đó là lệnh từ chối.

Ví dụ một filter chỉ cho phép lớp `com.example.dto.Message`:

~~~java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == Message.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

Filter này chỉ xác nhận `Message`. Với mọi lớp khác, nó trả về `UNDECIDED`. Nếu filter đó là quyết định duy nhất được áp dụng, các lớp khác chưa bị từ chối.

Đây là khoảng trống chính mà `rejectUndecidedClass` giải quyết: **chuyển trạng thái chưa quyết định thành từ chối đối với lớp**, để chính sách chỉ chấp nhận những lớp đã được xác nhận.

## 2. rejectUndecidedClass hoạt động như thế nào?

Cú pháp:

~~~java
ObjectInputFilter strictFilter =
        ObjectInputFilter.rejectUndecidedClass(existingFilter);
~~~

Phương thức nhận một `ObjectInputFilter` và trả về một filter bao quanh filter đó. Filter mới gọi filter ban đầu, sau đó xử lý kết quả theo quy tắc của API.

Với một lớp thông thường không phải array:

- Filter gốc trả `ALLOWED` → giữ nguyên `ALLOWED`.
- Filter gốc trả `REJECTED` → giữ nguyên `REJECTED`.
- Filter gốc trả `UNDECIDED` → đổi thành `REJECTED`.

Vì vậy, filter được bao trở thành chính sách **fail closed đối với lớp chưa được nhận diện**: nếu không có quyết định cho phép rõ ràng, lớp bị từ chối.

Ví dụ:

~~~java
ObjectInputFilter allowMessage = info -> {
    Class<?> type = info.serialClass();

    if (type == Message.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter rejectUnknown =
        ObjectInputFilter.rejectUndecidedClass(allowMessage);
~~~

Nếu lớp đang được kiểm tra là `Message`, kết quả là `ALLOWED`. Nếu là `UnexpectedData` và filter gốc không có quyết định, wrapper chuyển `UNDECIDED` thành `REJECTED`.

### 2.1. Không tự thay đổi filter ban đầu

`rejectUndecidedClass` tạo và trả về một filter mới. Nó không sửa object filter đầu vào:

~~~java
ObjectInputFilter base = createAllowlistFilter();
ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(base);
~~~

Khi gắn vào `ObjectInputStream`, cần dùng biến `strict` nếu muốn có hành vi từ chối lớp chưa quyết định. Chỉ tạo wrapper mà vẫn cài `base` thì không có tác dụng.

### 2.2. Tham số filter không được null

Filter đầu vào phải khác null. Truyền null sẽ làm phát sinh `NullPointerException` khi tạo wrapper.

~~~java
ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(null); // Không hợp lệ
~~~

Hãy khởi tạo filter gốc trước khi bọc nó.

## 3. Các trường hợp đặc biệt: metric-only và array

Tên phương thức có chữ `Class` vì wrapper tập trung chuyển kết quả `UNDECIDED` thành `REJECTED` cho lớp. Nó không đơn giản đổi mọi `UNDECIDED` trong mọi lần gọi thành `REJECTED`.

Theo hợp đồng Java 17, wrapper có các trường hợp đặc biệt sau:

| Thông tin từ FilterInfo | Kết quả khi filter gốc là UNDECIDED |
|---|---|
| `serialClass() == null` | Giữ `UNDECIDED` |
| Lớp thông thường, không phải array | `REJECTED` |
| Array có component type là kiểu tham chiếu | Kiểm tra component type gốc |
| Array có component type nguyên thủy | Giữ `UNDECIDED` |

### 3.1. Lần gọi chỉ có metric không bị đổi thành REJECTED

Filter có thể được gọi với `serialClass() == null`. Khi đó thông tin hiện có chỉ chứa metric như:

- `depth()`: độ sâu hiện tại của object graph.
- `references()`: số tham chiếu object đã được đọc.
- `streamBytes()`: số byte đã đọc từ stream.
- `arrayLength()`: độ dài array nếu lần kiểm tra liên quan đến array; nếu không phải array thì trả về -1.

Trong trường hợp không có lớp để xét, `rejectUndecidedClass` giữ kết quả `UNDECIDED`. Nhờ vậy, wrapper không nhầm một lần kiểm tra giới hạn tài nguyên với một lớp chưa được cho phép.

**Hệ quả:** `rejectUndecidedClass` không thay thế filter kiểm tra giới hạn tài nguyên. Nếu cần chặn object graph quá sâu, quá nhiều tham chiếu, stream quá lớn hoặc array quá dài, hãy viết thêm các điều kiện metric.

### 3.2. Array được kiểm tra thông qua component type

Giả sử filter gốc chỉ cho phép `Message.class`:

~~~java
ObjectInputFilter allowMessage = ObjectInputFilter.allowFilter(
        type -> type == Message.class,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(allowMessage);
~~~

Khi kiểm tra `Message[]`, wrapper không chỉ nhìn vào kết quả cho array class. Nếu kết quả ban đầu là `UNDECIDED`, nó xác định component type gốc và gọi filter cho kiểu đó:

- Component type được `ALLOWED` → array được `ALLOWED`.
- Component type bị `REJECTED` hoặc vẫn `UNDECIDED` → array bị `REJECTED`.

Vì vậy, nếu `Message.class` được allowlist, array một chiều hoặc nhiều chiều có component type gốc là `Message` có thể được cho phép theo quy tắc này.

### 3.3. Array kiểu nguyên thủy là trường hợp riêng

Với array như `byte[]` hoặc `int[]`, component type gốc là kiểu nguyên thủy. Nếu filter gốc trả `UNDECIDED` cho array, wrapper giữ `UNDECIDED` thay vì tự động từ chối.

Đây là hành vi được quy định rõ, không nên suy luận rằng `rejectUndecidedClass` sẽ từ chối mọi array chưa có kết quả `ALLOWED`.

Nếu ứng dụng không chấp nhận primitive array, hãy bổ sung quy tắc riêng:

~~~java
ObjectInputFilter rejectPrimitiveArrays = info -> {
    Class<?> type = info.serialClass();

    if (type != null
            && type.isArray()
            && type.getComponentType().isPrimitive()) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

Đoạn trên chỉ minh họa array một chiều. Với array nhiều chiều, `getComponentType()` có thể trả về một array class khác; nếu cần cấm mọi array có base component là primitive, hãy đi lần lượt qua các chiều để tìm component type cuối cùng.

## 4. Tạo allowlist bằng allowFilter

Java 17 bổ sung `ObjectInputFilter.allowFilter(predicate, otherStatus)` để tạo filter từ một điều kiện kiểm tra `Class<?>`.

Cú pháp:

~~~java
ObjectInputFilter allowFilter =
        ObjectInputFilter.allowFilter(
                classPredicate,
                ObjectInputFilter.Status.UNDECIDED
        );
~~~

Quy tắc:

- Nếu `serialClass()` là null, kết quả là `UNDECIDED`.
- Nếu predicate trả true cho lớp, kết quả là `ALLOWED`.
- Nếu predicate trả false, kết quả là giá trị `otherStatus`.

Để dùng cùng `rejectUndecidedClass`, có thể chọn `UNDECIDED` làm `otherStatus`. Như vậy filter gốc chỉ xác nhận lớp trong allowlist; wrapper chuyển mọi lớp thường không được xác nhận thành `REJECTED`.

### 4.1. Allowlist theo lớp chính xác

~~~java
Set<Class<?>> allowedClasses = Set.of(
        Message.class,
        Address.class
);

ObjectInputFilter allowKnownClasses = ObjectInputFilter.allowFilter(
        allowedClasses::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strictFilter =
        ObjectInputFilter.rejectUndecidedClass(allowKnownClasses);
~~~

Cách này phù hợp khi danh sách kiểu cần đọc đã biết rõ. Dùng `Class` chính xác giúp tránh cho phép vô tình một lớp khác chỉ vì nó nằm trong cùng package hoặc có tên gần giống.

Nếu object graph cần các lớp khác như collection implementation hoặc kiểu dữ liệu hỗ trợ, hãy xác định rõ chúng có thực sự thuộc hợp đồng dữ liệu hay không rồi mới bổ sung vào allowlist. Không mở rộng allowlist một cách tùy tiện chỉ để làm một stream cụ thể đọc được.

### 4.2. Allowlist theo package hoặc hierarchy

Có thể dùng predicate:

~~~java
ObjectInputFilter allowDtos = ObjectInputFilter.allowFilter(
        type -> type.getPackageName().equals("com.example.dto"),
        ObjectInputFilter.Status.UNDECIDED
);
~~~

Hoặc cho phép các lớp triển khai một interface marker:

~~~java
ObjectInputFilter allowDomainTypes = ObjectInputFilter.allowFilter(
        DomainMessage.class::isAssignableFrom,
        ObjectInputFilter.Status.UNDECIDED
);
~~~

Cần thận trọng: cho phép toàn bộ package hoặc mọi lớp trong một hierarchy rộng hơn có thể đưa vào các kiểu không dự kiến. Với dữ liệu không tin cậy, allowlist theo lớp cụ thể thường dễ kiểm soát hơn.

### 4.3. Không trả ALLOWED cho mọi lớp

Một filter như sau không phải allowlist an toàn:

~~~java
ObjectInputFilter allowEverything = info ->
        ObjectInputFilter.Status.ALLOWED;
~~~

Nó xác nhận mọi lớp mà filter được gọi kiểm tra. Bọc nó bằng `rejectUndecidedClass` cũng không làm chính sách chặt hơn, vì filter gốc không trả `UNDECIDED`.

Wrapper chỉ chuyển kết quả chưa quyết định; nó không thể tự suy ra lớp nào an toàn.

## 5. Kết hợp allowlist với giới hạn tài nguyên

Lọc lớp và giới hạn tài nguyên giải quyết hai vấn đề khác nhau:

- Allowlist kiểm soát **kiểu dữ liệu** có thể xuất hiện.
- Resource filter kiểm soát **quy mô object graph** và lượng dữ liệu được đọc.

Một lớp nằm trong allowlist vẫn có thể xuất hiện trong object graph quá sâu hoặc quá lớn. Vì vậy, filter thực tế thường cần cả hai.

### 5.1. Kiểm tra metric

Ví dụ giới hạn:

~~~java
ObjectInputFilter resourceLimits = info -> {
    if (info.depth() > 20) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.references() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.streamBytes() > 1_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.arrayLength() >= 0 && info.arrayLength() > 100_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

Các con số trên chỉ là ví dụ minh họa. Giá trị phù hợp phải xuất phát từ kích thước dữ liệu hợp lệ, độ sâu object graph và ngân sách bộ nhớ của ứng dụng.

Filter này trả `UNDECIDED` khi chưa vượt giới hạn vì nó chỉ đưa ra quyết định về metric. Nó không khẳng định lớp đang đọc là an toàn.

### 5.2. Ghép filter bằng merge

`ObjectInputFilter.merge(filter, anotherFilter)` kết hợp kết quả của hai filter:

1. Nếu một trong hai trả `REJECTED`, kết quả là `REJECTED`.
2. Nếu không có filter nào từ chối và ít nhất một filter trả `ALLOWED`, kết quả là `ALLOWED`.
3. Nếu cả hai đều `UNDECIDED`, kết quả là `UNDECIDED`.

Có thể kết hợp như sau:

~~~java
ObjectInputFilter classAllowlist = ObjectInputFilter.allowFilter(
        allowedClasses::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter rejectUnknownClasses =
        ObjectInputFilter.rejectUndecidedClass(classAllowlist);

ObjectInputFilter combined = ObjectInputFilter.merge(
        resourceLimits,
        rejectUnknownClasses
);
~~~

Trong cấu hình này:

- Lớp trong allowlist được class filter xác nhận `ALLOWED`.
- Lớp thông thường ngoài allowlist bị wrapper đổi thành `REJECTED`.
- Metric vượt giới hạn bị resource filter `REJECTED`.
- Metric hợp lệ nhưng không gắn với lớp có thể giữ `UNDECIDED`.

**REJECTED luôn thắng khi merge.** Vì thế, filter cho phép một lớp không thể ghi đè kết quả từ chối do resource filter đưa ra.

### 5.3. Đừng nhầm merge với phép OR đơn giản

`merge` không có nghĩa “một filter cho phép là bỏ qua mọi filter còn lại”. Nếu filter A trả `ALLOWED` nhưng filter B trả `REJECTED`, kết quả cuối vẫn là `REJECTED`.

Đây là thuộc tính quan trọng khi ghép allowlist với giới hạn tài nguyên hoặc chính sách từ nhiều tầng.

## 6. Cài filter vào ObjectInputStream

Tạo filter là chưa đủ. Ứng dụng phải gắn filter vào `ObjectInputStream` trước khi đọc object.

~~~java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(strictFilter);

    Object value = input.readObject();
}
~~~

Thứ tự cần giữ:

1. Tạo input stream.
2. Tạo hoặc chọn filter phù hợp với ngữ cảnh.
3. Gọi `setObjectInputFilter` trước khi đọc object.
4. Gọi `readObject`.
5. Xử lý kết quả và ngoại lệ.
6. Đóng stream bằng try-with-resources.

Nếu đặt filter sau khi đã bắt đầu đọc dữ liệu, bạn có thể không còn bảo vệ được những object đã được khôi phục trước đó. Thiết kế đơn giản nhất là cài filter ngay sau khi tạo stream và trước lần `readObject` đầu tiên.

### 6.1. Ví dụ cài allowlist cho một stream

~~~java
Set<Class<?>> allowed = Set.of(Message.class, Address.class);

ObjectInputFilter allowKnown = ObjectInputFilter.allowFilter(
        allowed::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(allowKnown);

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(strict);

    Message message = (Message) input.readObject();
    System.out.println(message.text());
}
~~~

Nếu stream chứa một lớp thông thường không được allowlist, wrapper sẽ trả `REJECTED` khi lớp đó được kiểm tra và quá trình đọc bị dừng bằng lỗi giải tuần tự hóa.

### 6.2. Lọc theo từng stream

`setObjectInputFilter` đặt filter cho một `ObjectInputStream` cụ thể. Điều này hữu ích khi các luồng dữ liệu có hợp đồng khác nhau:

- Tệp cấu hình chỉ chứa một số DTO cố định.
- Thông điệp từ một thành phần nội bộ có schema riêng.
- Dữ liệu lưu trữ có phiên bản và tập kiểu được hỗ trợ riêng.

Mỗi stream nên dùng allowlist phù hợp với định dạng dữ liệu của nó. Không dùng một allowlist quá rộng cho mọi nguồn chỉ để tái sử dụng một đoạn cấu hình.

## 7. Ví dụ hoàn chỉnh: chỉ cho phép Message

Ví dụ sau tạo một object tuần tự hóa trong bộ nhớ, sau đó đọc lại bằng filter chỉ cho phép lớp `Message`. Một lớp `Unexpected` được dùng để minh họa trường hợp bị từ chối.

Tạo file **`RejectUndecidedDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.util.Set;

public class RejectUndecidedDemo {

    static final class Message implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String text;

        Message(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    static final class Unexpected implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final int code = 99;
    }

    private static final Set<Class<?>> ALLOWED_CLASSES =
            Set.of(Message.class, String.class);

    static ObjectInputFilter createFilter() {
        ObjectInputFilter allowKnownClasses = ObjectInputFilter.allowFilter(
                ALLOWED_CLASSES::contains,
                ObjectInputFilter.Status.UNDECIDED
        );

        ObjectInputFilter rejectUnknownClasses =
                ObjectInputFilter.rejectUndecidedClass(allowKnownClasses);

        ObjectInputFilter resourceLimits = info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            if (info.arrayLength() >= 0 && info.arrayLength() > 1_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            return ObjectInputFilter.Status.UNDECIDED;
        };

        return ObjectInputFilter.merge(
                resourceLimits,
                rejectUnknownClasses
        );
    }

    static byte[] serialize(Object value) throws IOException {
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {

            output.writeObject(value);
            output.flush();
            return bytes.toByteArray();
        }
    }

    static Object deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            // Phải cài filter trước readObject().
            input.setObjectInputFilter(createFilter());

            return input.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] validBytes = serialize(new Message("Hello Java 17"));

        Message message = (Message) deserialize(validBytes);
        System.out.println(message.text());

        byte[] unexpectedBytes = serialize(new Unexpected());

        try {
            deserialize(unexpectedBytes);
            System.out.println("Không mong đợi lớp này được chấp nhận");
        } catch (InvalidClassException e) {
            System.out.println("Đã từ chối lớp ngoài allowlist");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 RejectUndecidedDemo.java
java RejectUndecidedDemo
~~~

Kết quả mong đợi:

~~~text
Hello Java 17
Đã từ chối lớp ngoài allowlist
~~~

Điểm chính trong ví dụ:

- `allowFilter` xác nhận `Message.class`.
- Với lớp không có trong tập, filter gốc trả `UNDECIDED`.
- `rejectUndecidedClass` chuyển kết quả đó thành `REJECTED`.
- `resourceLimits` từ chối object graph vượt các giới hạn đã đặt.
- `merge` kết hợp hai chính sách và giữ ưu tiên cho kết quả từ chối.
- Filter được gắn trước khi gọi `readObject`.

Trong ứng dụng thật, danh sách kiểu cần cho phép phải phản ánh chính xác schema dữ liệu. Nếu object graph có thêm collection, kiểu con hoặc kiểu hỗ trợ, hãy kiểm tra và đưa chúng vào chính sách một cách có chủ đích.

## 8. Dùng rejectUndecidedClass với pattern filter

Ngoài predicate, Java hỗ trợ tạo filter từ chuỗi pattern:

~~~java
ObjectInputFilter patternFilter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.*;!*"
        );
~~~

Pattern filter cho phép lớp khớp package đã nêu và từ chối các lớp không khớp theo pattern. Ký hiệu `!*` là mẫu từ chối lớp còn lại.

Vì pattern filter đã có quy tắc từ chối rõ ràng cho các lớp không khớp, wrapper `rejectUndecidedClass` không phải lúc nào cũng cần thiết. Nó hữu ích hơn khi filter gốc có chủ ý trả `UNDECIDED` cho những lớp ngoài phạm vi mà filter đó hiểu, sau đó một lớp chính sách bên ngoài muốn biến sự thiếu quyết định thành từ chối.

Ví dụ:

~~~java
ObjectInputFilter packageFilter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.*"
        );

ObjectInputFilter strictPackageFilter =
        ObjectInputFilter.rejectUndecidedClass(packageFilter);
~~~

Cần đọc kỹ cú pháp pattern và kiểm tra các kiểu phụ trợ thực sự có trong object graph. Một pattern package rộng có thể cho phép nhiều lớp hơn mức ứng dụng cần.

### 8.1. Giới hạn tài nguyên trong pattern string

Pattern filter hỗ trợ các giới hạn như:

| Pattern | Ý nghĩa |
|---|---|
| `maxdepth=20` | Giới hạn độ sâu object graph |
| `maxrefs=10000` | Giới hạn số object reference |
| `maxbytes=1000000` | Giới hạn số byte stream |
| `maxarray=100000` | Giới hạn độ dài array |

Ví dụ:

~~~java
ObjectInputFilter patternFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=10000;"
                + "maxbytes=1000000;maxarray=100000;"
                + "com.example.dto.*;!*"
        );
~~~

Các giới hạn này là chính sách theo dữ liệu thực tế của ứng dụng, không phải con số mặc định phù hợp cho mọi hệ thống. Hãy chọn ngưỡng dựa trên object graph hợp lệ và kiểm thử cả trường hợp sát giới hạn.

## 9. Phân biệt rejectUndecidedClass với rejectFilter

Java 17 cũng có `ObjectInputFilter.rejectFilter(predicate, otherStatus)`. Hai phương thức có mục đích khác nhau:

| API | Ý nghĩa |
|---|---|
| `rejectFilter(predicate, otherStatus)` | Từ chối khi predicate đúng; trường hợp khác trả trạng thái được chỉ định |
| `rejectUndecidedClass(filter)` | Bao filter hiện có và đổi `UNDECIDED` thành `REJECTED` cho lớp, theo quy tắc đặc biệt của array |

Ví dụ `rejectFilter`:

~~~java
ObjectInputFilter rejectProxyLikeClass = ObjectInputFilter.rejectFilter(
        type -> type.getName().contains("Unexpected"),
        ObjectInputFilter.Status.UNDECIDED
);
~~~

Filter này từ chối lớp có tên thỏa predicate. Các lớp khác trả `UNDECIDED`. Nếu muốn chính sách chỉ chấp nhận những lớp đã được xác nhận, có thể bọc filter bằng `rejectUndecidedClass` hoặc kết hợp với allowlist phù hợp.

Không nhầm `rejectFilter` với `rejectUndecidedClass`: một cái quyết định từ chối theo điều kiện, một cái xử lý các kết quả chưa quyết định của filter khác.

## 10. Các trạng thái khi kết hợp nhiều filter

Khi xây dựng filter theo nhiều lớp, hãy theo dõi chính xác trạng thái được trả về:

~~~text
Filter kiểm tra lớp
    |
    +-- ALLOWED ------> giữ ALLOWED
    |
    +-- REJECTED -----> giữ REJECTED
    |
    +-- UNDECIDED
            |
            v
    rejectUndecidedClass
            |
            +-- lớp thường ------> REJECTED
            |
            +-- serialClass null -> UNDECIDED
            |
            +-- primitive array -> UNDECIDED
            |
            +-- reference array -> kiểm tra base component
                                      |
                                      +-- ALLOWED -> ALLOWED
                                      +-- khác    -> REJECTED
~~~

Sau đó, nếu dùng `merge` với resource filter, kết quả từ chối của một filter vẫn được giữ lại.

### 10.1. Một filter trả ALLOWED không có nghĩa bỏ qua giới hạn

Ví dụ:

- Filter A xác nhận `Message` và trả `ALLOWED`.
- Filter B thấy stream vượt `maxbytes` và trả `REJECTED`.
- Filter tổng hợp bằng `merge` trả `REJECTED`.

Không để logic allowlist ghi đè giới hạn tài nguyên.

### 10.2. Metric filter không nên tự trả ALLOWED cho mọi lớp

Nếu resource filter trả `ALLOWED` khi metric hợp lệ mà không kiểm tra lớp, nó có thể làm cho filter merge cho kết quả `ALLOWED` ngay cả khi class filter trả `UNDECIDED`. Trong một cấu hình khác, điều đó có thể làm suy yếu chính sách lớp.

Cách rõ ràng là để resource filter trả `UNDECIDED` khi metric hợp lệ và chỉ trả `REJECTED` khi vượt giới hạn. Class filter chịu trách nhiệm quyết định lớp có được phép hay không.

## 11. Các giới hạn và lưu ý bảo mật

`rejectUndecidedClass` là công cụ hỗ trợ chính sách filter, không phải giải pháp bảo mật hoàn chỉnh cho mọi trường hợp.

### 11.1. Chỉ cho phép lớp thực sự cần thiết

Một allowlist rộng như toàn bộ package hoặc toàn bộ module JDK có thể bao gồm kiểu không cần thiết. Hãy bắt đầu từ schema dữ liệu được mong đợi, rồi thêm từng kiểu có lý do rõ ràng.

### 11.2. Kiểm tra giới hạn tài nguyên riêng

Wrapper không tự giới hạn:

- Độ sâu object graph.
- Số lượng object reference.
- Kích thước byte của stream.
- Độ dài array.

Hãy kết hợp metric filter hoặc pattern limits để giảm nguy cơ tiêu thụ CPU và bộ nhớ quá mức.

### 11.3. Filter không xác nhận tính hợp lệ nghiệp vụ

Một object thuộc lớp được allowlist vẫn có thể chứa dữ liệu không hợp lệ, ví dụ:

- ID rỗng hoặc sai định dạng.
- Số lượng âm.
- Trạng thái không được nghiệp vụ hỗ trợ.
- Chuỗi vượt giới hạn ứng dụng.

Sau khi giải tuần tự hóa, vẫn phải kiểm tra dữ liệu và bất biến của domain model.

### 11.4. Không coi Java Serialization là định dạng trao đổi an toàn mặc định

Nếu thiết kế hệ thống mới, hãy cân nhắc định dạng dữ liệu có schema rõ ràng và parser phù hợp với nhu cầu. Nếu phải đọc Java serialized data, chỉ nhận dữ liệu từ nguồn đáng tin cậy hoặc áp dụng filter nghiêm ngặt cùng kiểm tra dữ liệu ở tầng ứng dụng.

Filter giúp giảm bề mặt tấn công; nó không làm cho việc giải tuần tự hóa dữ liệu không tin cậy trở nên vô hại trong mọi trường hợp.

### 11.5. Không dùng một allowlist cho mọi phiên bản schema mà không kiểm soát

Khi schema thay đổi, tập lớp hợp lệ có thể thay đổi. Hãy quản lý version dữ liệu và chính sách filter tương ứng. Không thêm một package lớn vào allowlist chỉ để tương thích tạm thời với một file cũ mà chưa đánh giá các kiểu mới được cho phép.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lớp lạ vẫn được đọc | Filter gốc trả `UNDECIDED` và không có wrapper/chính sách khác từ chối | Bọc bằng `rejectUndecidedClass` |
| Đã tạo wrapper nhưng lớp lạ vẫn lọt | Vẫn cài filter gốc vào stream thay vì filter wrapper | Gọi `setObjectInputFilter(strictFilter)` |
| Tất cả lớp đều bị từ chối | Allowlist thiếu lớp cần thiết hoặc predicate không khớp | Xác định class graph và cập nhật allowlist có kiểm soát |
| Primitive array vẫn được chấp nhận | Wrapper giữ `UNDECIDED` cho array có base component nguyên thủy | Thêm quy tắc array riêng nếu cần từ chối |
| Array object bị từ chối | Base component type không được filter gốc cho phép | Xác định component class và bổ sung nếu thực sự hợp lệ |
| Stream quá sâu vẫn được đọc | Chỉ lọc lớp, chưa giới hạn metric | Kiểm tra depth, references, bytes và array length |
| Tạo filter ném NullPointerException | Truyền filter gốc null | Khởi tạo filter hợp lệ trước khi bọc |
| Gọi readObject trước khi cài filter | Filter được gắn quá muộn | Cài filter ngay sau khi tạo ObjectInputStream |
| Merge cho kết quả bị từ chối dù một filter allow | Một filter khác trả REJECTED; REJECTED có ưu tiên | Kiểm tra từng filter và lý do từ chối |
| Object được allowlist nhưng dữ liệu vẫn sai | Filter chỉ kiểm soát lớp/metric, không xác thực nghiệp vụ | Kiểm tra field và domain invariant sau khi đọc |

## 13. Bài tập thực hành

### Bài 1: Phân biệt ba trạng thái

Một filter trả `ALLOWED` cho `Message.class`, `REJECTED` cho `LegacyPayload.class` và `UNDECIDED` cho các lớp khác.

**Câu hỏi:** Sau khi bọc bằng `rejectUndecidedClass`, một lớp thường khác `Message` và `LegacyPayload` có kết quả gì?

**Đáp án:** `UNDECIDED` của filter gốc được đổi thành `REJECTED`. `ALLOWED` và `REJECTED` có sẵn được giữ nguyên.

### Bài 2: Tạo allowlist bằng allowFilter

Viết filter chỉ xác nhận `Message.class` và `Address.class`; các lớp khác trả `UNDECIDED`. Sau đó bọc bằng `rejectUndecidedClass`.

**Đáp án gợi ý:**

~~~java
Set<Class<?>> allowed = Set.of(Message.class, Address.class);

ObjectInputFilter base = ObjectInputFilter.allowFilter(
        allowed::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(base);
~~~

### Bài 3: Vì sao serialClass null không bị từ chối?

**Đáp án:** Đây là lần filter được gọi để cung cấp thông tin metric mà không có lớp cụ thể. `rejectUndecidedClass` giữ `UNDECIDED` trong trường hợp đó để metric filter có thể xử lý depth, references, stream bytes hoặc array length riêng.

### Bài 4: Primitive array có bị từ chối không?

Một filter gốc trả `UNDECIDED` cho mọi lớp. Sau khi bọc, điều gì xảy ra với `byte[]`?

**Đáp án:** Wrapper giữ `UNDECIDED` cho array có base component type là primitive. Nếu ứng dụng cần từ chối `byte[]` hoặc primitive array khác, phải bổ sung quy tắc rõ ràng.

### Bài 5: Kết hợp resource filter

Viết filter từ chối khi depth lớn hơn 10 hoặc stream bytes lớn hơn 500.000; trường hợp còn lại trả `UNDECIDED`.

**Đáp án:**

~~~java
ObjectInputFilter limits = info -> {
    if (info.depth() > 10 || info.streamBytes() > 500_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

### Bài 6: Vì sao merge vẫn từ chối?

Filter A trả `ALLOWED`, filter B trả `REJECTED`. Kết quả của `ObjectInputFilter.merge(A, B)` là gì?

**Đáp án:** `REJECTED`. Trong phép merge, chỉ cần một filter từ chối thì kết quả tổng hợp bị từ chối.

### Bài 7: Đặt filter đúng thời điểm

**Câu hỏi:** Nên gọi `setObjectInputFilter` trước hay sau `readObject`?

**Đáp án:** Trước lần đọc object đầu tiên. Cài filter ngay sau khi tạo `ObjectInputStream` để object graph được kiểm tra trong quá trình giải tuần tự hóa.

## 14. Ghi nhớ

Khi dùng `rejectUndecidedClass` trong Java 17:

1. Hiểu `UNDECIDED` là chưa có quyết định; nó không tự động có nghĩa là từ chối.
2. Tạo filter gốc xác nhận rõ các lớp được phép.
3. Bọc filter bằng `ObjectInputFilter.rejectUndecidedClass(filter)` để từ chối lớp thường chưa được xác nhận.
4. Nhớ ngoại lệ xử lý metric-only, array tham chiếu và primitive array.
5. Kết hợp resource filter cho depth, references, stream bytes và array length.
6. Dùng `ObjectInputFilter.merge` để ghép chính sách; `REJECTED` luôn được ưu tiên.
7. Cài filter vào `ObjectInputStream` trước khi gọi `readObject`.
8. Kiểm tra dữ liệu nghiệp vụ sau khi đọc; allowlist lớp không xác nhận giá trị field hợp lệ.

`rejectUndecidedClass` phù hợp khi filter hiện tại chỉ biết xác nhận một tập lớp cụ thể và muốn mọi lớp thường nằm ngoài tập đó bị từ chối. Hãy dùng nó cùng allowlist và giới hạn tài nguyên được thiết kế theo đúng định dạng dữ liệu mà ứng dụng cần đọc.

## 15. Tài liệu tham khảo

- [Oracle Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): `Status`, `FilterInfo`, `allowFilter`, `rejectFilter`, `merge` và `rejectUndecidedClass`.
- [Oracle Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): gắn filter vào stream và giải tuần tự hóa object.
- [Oracle Java SE 17 — Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): cách thiết kế filter theo lớp, pattern filter, giới hạn resource và áp dụng filter.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): lọc dữ liệu đầu vào của Java Serialization.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factory theo ngữ cảnh trong Java 17.

