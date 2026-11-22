# Bộ lọc theo luồng và cấu hình jdk.serialFilter

## Mục tiêu

Java Serialization có thể khôi phục một đồ thị object từ dữ liệu nhị phân bằng `ObjectInputStream`. Nếu dữ liệu đến từ nguồn không đáng tin cậy, việc khôi phục object có thể tạo ra các kiểu không mong muốn hoặc tiêu tốn quá nhiều tài nguyên.

Từ Java 9, Java cung cấp **Serialization Filtering** qua `java.io.ObjectInputFilter` (JEP 290). Bộ lọc kiểm tra các lớp được đọc và một số chỉ số của đồ thị object trước khi quá trình deserialization tiếp tục.

Có hai phạm vi cấu hình chính:

- **Bộ lọc theo từng luồng (stream-specific):** gắn vào một `ObjectInputStream` bằng `setObjectInputFilter()`. Dùng khi mỗi luồng có danh sách lớp hoặc giới hạn riêng.
- **Bộ lọc toàn JVM (JVM-wide):** cấu hình bằng system property `jdk.serialFilter`, Security Property cùng tên hoặc `ObjectInputFilter.Config.setSerialFilter()`. Dùng làm chính sách chung cho các luồng trong tiến trình.

Bộ lọc không được bật mặc định. Ứng dụng phải chủ động cấu hình trước khi đọc dữ liệu. Cần thiết kế chính sách cho đúng đồ thị object mà ứng dụng thực sự cần.

## 1. ObjectInputFilter kiểm tra điều gì?

`ObjectInputFilter` nhận một `FilterInfo` trong lúc `ObjectInputStream` đọc object. Thông tin có thể dùng để quyết định cho phép hay từ chối gồm:

| Thông tin | Ý nghĩa |
|---|---|
| `serialClass()` | Lớp đang được kiểm tra; có thể là `null` ở callback chỉ kiểm tra tài nguyên hoặc reference |
| `arrayLength()` | Độ dài mảng; giá trị âm nếu callback hiện tại không đại diện cho mảng |
| `depth()` | Độ sâu hiện tại của đồ thị object |
| `references()` | Tổng số object/reference đã gặp trong luồng |
| `streamBytes()` | Số byte đã tiêu thụ từ luồng serialization |

Bộ lọc có thể được gọi khi gặp lớp mới, mảng hoặc reference để kiểm tra giới hạn đồ thị. Việc kiểm tra lớp diễn ra trước khi object của lớp đó được khôi phục. Một lớp thường được kiểm tra khi xuất hiện lần đầu trong luồng; không nên coi filter là callback nghiệp vụ chạy cho từng instance.

Filter không được gọi cho dữ liệu primitive và các giá trị `String` được mã hóa trực tiếp theo định dạng serialization. Vì vậy, filter không thay thế việc kiểm tra nội dung field, quy tắc nghiệp vụ hoặc tính hợp lệ của dữ liệu sau khi đọc.

## 2. Ba trạng thái của filter

`ObjectInputFilter.checkInput(FilterInfo)` trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| `ALLOWED` | Filter chấp nhận lớp hoặc trạng thái đang kiểm tra |
| `REJECTED` | Từ chối; deserialization bị dừng, thường phát sinh `InvalidClassException` |
| `UNDECIDED` | Filter không đưa ra quyết định cho thông tin này |

`UNDECIDED` không có nghĩa là `REJECTED`. Nếu một filter chỉ từ chối những lớp nguy hiểm, nó có thể trả `UNDECIDED` cho các lớp khác. Nếu muốn xây dựng allow-list chặt chẽ, hãy từ chối mọi lớp không được cho phép, chẳng hạn dùng pattern `!*` ở cuối, hoặc dùng `ObjectInputFilter.rejectUndecidedClass(...)` trên JDK 17+.

Với filter tự viết, thường nên xử lý giới hạn tài nguyên trước, sau đó mới quyết định theo lớp:

~~~java
ObjectInputFilter filter = info -> {
    if (info.depth() > 10
            || info.references() > 1_000
            || info.streamBytes() > 1_000_000
            || (info.arrayLength() >= 0 && info.arrayLength() > 100_000)) {
        return ObjectInputFilter.Status.REJECTED;
    }

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

Ví dụ này chỉ cho phép lớp `Message` và từ chối các lớp khác. Khi dùng trong ứng dụng thật, cần thêm các kiểu phụ thuộc mà đồ thị object hợp lệ của ứng dụng thực sự cần.

## 3. Đặt filter riêng cho một ObjectInputStream

Tạo filter từ pattern:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1000000;"
        + "maxarray=100000;com.example.dto.**;!*"
);
~~~

Gắn filter vào stream trước khi gọi `readObject()` hoặc `readUnshared()`:

~~~java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
}
~~~

Các điểm quan trọng:

- Gắn filter ngay sau khi tạo `ObjectInputStream`, trước khi đọc object đầu tiên.
- `setObjectInputFilter()` chỉ được gọi một lần cho mỗi stream và phải gọi trước lần đọc object đầu tiên.
- Filter gắn vào stream chỉ tác động đến luồng đó.
- Nếu filter từ chối lớp hoặc giới hạn, quá trình đọc thất bại; hãy xử lý `InvalidClassException` như một lỗi dữ liệu không được phép.
- Không đợi đến sau `readObject()` mới kiểm tra lớp, vì object có thể đã được khởi tạo và khôi phục.

### Khi nào nên dùng filter theo luồng?

Dùng filter theo luồng khi ứng dụng đọc nhiều loại dữ liệu khác nhau, ví dụ:

- Luồng cấu hình chỉ chứa một nhóm DTO nhỏ.
- Luồng nhập dữ liệu có giới hạn kích thước và độ sâu riêng.
- Luồng từ một đối tác chỉ được phép chứa một tập lớp đã thỏa thuận.
- Một thành phần đọc dữ liệu legacy cần chính sách chặt hơn phần còn lại của ứng dụng.

Không dùng chung một allow-list rộng cho mọi nguồn dữ liệu nếu mỗi nguồn có hợp đồng kiểu khác nhau.

## 4. Cấu hình toàn JVM bằng jdk.serialFilter

Có thể cấu hình filter toàn tiến trình mà không cần sửa từng chỗ tạo `ObjectInputStream`.

### System property trên command line

Ví dụ chỉ cho phép các lớp DTO trong package của ứng dụng, đồng thời giới hạn tài nguyên:

~~~bash
java '-Djdk.serialFilter=maxdepth=20;maxrefs=2000;maxbytes=5000000;maxarray=100000;com.example.dto.**;!*' -jar app.jar
~~~

System property chỉ áp dụng cho tiến trình Java được khởi chạy bằng lệnh đó. Đây là cách rõ ràng để gắn chính sách vào một lần chạy ứng dụng.

### Security Property cho các ứng dụng dùng cùng JDK

Có thể cấu hình `jdk.serialFilter` trong file:

~~~text
$JAVA_HOME/conf/security/java.security
~~~

Ví dụ:

~~~properties
jdk.serialFilter=maxdepth=20;maxrefs=2000;maxbytes=5000000;maxarray=100000;com.example.dto.**;!*
~~~

Security Property áp dụng cho các tiến trình dùng cấu hình JDK đó. Nếu đồng thời có system property `jdk.serialFilter`, system property sẽ ghi đè Security Property.

### Cấu hình bằng API

Có thể thiết lập filter toàn JVM bằng API:

~~~java
ObjectInputFilter globalFilter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=2000;maxbytes=5000000;"
        + "maxarray=100000;com.example.dto.**;!*"
);

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

Đặt filter sớm trong quá trình khởi động, trước khi các thành phần tạo `ObjectInputStream`. Filter toàn JVM chỉ được thiết lập một lần; nếu đã được cấu hình bằng property hoặc API, lần thiết lập tiếp theo có thể thất bại.

`ObjectInputFilter.Config.getSerialFilter()` trả về filter toàn JVM hiện tại hoặc `null` nếu chưa cấu hình.

## 5. Cú pháp pattern của jdk.serialFilter

Pattern gồm nhiều phần, phân cách bằng dấu chấm phẩy `;`. Khoảng trắng là một phần của pattern, vì vậy tránh chèn khoảng trắng không chủ ý quanh dấu phân cách.

### Giới hạn tài nguyên

| Pattern | Giới hạn |
|---|---|
| `maxdepth=20` | Độ sâu tối đa của đồ thị object |
| `maxrefs=2000` | Số reference tối đa |
| `maxbytes=5000000` | Số byte tối đa đã đọc từ stream |
| `maxarray=100000` | Độ dài mảng tối đa |

Các giới hạn được kiểm tra trước class pattern, bất kể vị trí của chúng trong chuỗi. Nếu bất kỳ giới hạn nào bị vượt, kết quả là `REJECTED`.

Giá trị cần chọn theo dữ liệu hợp lệ thực tế. Đặt quá thấp sẽ từ chối dữ liệu bình thường; đặt quá cao sẽ giảm hiệu quả bảo vệ trước đồ thị quá sâu, quá lớn hoặc quá nhiều reference.

### Class pattern, package và module

| Pattern | Ý nghĩa |
|---|---|
| `com.example.Message` | Khớp một lớp cụ thể |
| `com.example.dto.*` | Khớp các lớp trực tiếp trong package đó |
| `com.example.dto.**` | Khớp các lớp trong package và mọi subpackage |
| `com.example.*` | Khớp tên lớp có prefix tương ứng |
| `java.base/java.util.ArrayList` | Khớp lớp trong module được chỉ định |
| `!com.example.internal.Secret` | Từ chối lớp khớp pattern |
| `!*` | Từ chối mọi lớp không được pattern trước đó cho phép |

Dấu `!` đặt ở đầu pattern để biểu thị từ chối. Class pattern được xét từ trái sang phải; pattern lớp đầu tiên khớp sẽ quyết định `ALLOWED` hoặc `REJECTED`.

Ví dụ allow-list có mặc định từ chối:

~~~text
com.example.dto.Message;com.example.dto.Address;!*
~~~

Pattern trên cho phép hai lớp đã nêu và từ chối các lớp khác. Với một package gồm nhiều lớp hợp lệ, có thể dùng `com.example.dto.**`, nhưng chỉ nên mở rộng phạm vi khi ứng dụng thực sự cần.

Với mảng, pattern lớp được đối chiếu theo kiểu phần tử của mảng. Giới hạn `maxarray` kiểm tra độ dài mảng riêng.

## 6. Ví dụ cấu hình theo luồng và toàn JVM có thể chạy

Ví dụ tạo một object `Message`, serialize vào byte array rồi đọc lại. Chương trình có hai chế độ:

- Mặc định: dùng filter riêng trên `ObjectInputStream`, sau đó chứng minh filter `!*` từ chối lớp.
- Tham số `--global`: không gắn filter riêng; chương trình sử dụng filter JVM-wide được truyền bằng `-Djdk.serialFilter`.

Tệp `SerialFilterDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class SerialFilterDemo {
    private static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String text;

        Message(String text) {
            this.text = text;
        }
    }

    private static byte[] serialize(Message message) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(message);
        }
        return bytes.toByteArray();
    }

    private static Message read(byte[] bytes, ObjectInputFilter filter)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            if (filter != null) {
                input.setObjectInputFilter(filter);
            }
            return (Message) input.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = serialize(new Message("hello"));

        if (args.length > 0 && "--global".equals(args[0])) {
            Message restored = read(bytes, null);
            System.out.println("global filter restored: " + restored.text);
            return;
        }

        String allowPattern =
                "maxdepth=5;maxrefs=20;maxbytes=65536;maxarray=1000;"
                + "SerialFilterDemo$Message;!*";
        ObjectInputFilter allowFilter =
                ObjectInputFilter.Config.createFilter(allowPattern);

        Message restored = read(bytes, allowFilter);
        System.out.println("stream filter restored: " + restored.text);

        ObjectInputFilter rejectAll =
                ObjectInputFilter.Config.createFilter("!*");
        try {
            read(bytes, rejectAll);
            throw new AssertionError("Reject-all filter did not reject Message");
        } catch (InvalidClassException expected) {
            System.out.println("stream filter rejected: true");
        }
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~bash
javac --release 9 -Xlint:all SerialFilterDemo.java
java SerialFilterDemo
~~~

Stdout:

~~~text
stream filter restored: hello
stream filter rejected: true
~~~

Chạy cùng chương trình với filter toàn JVM:

~~~bash
java '-Djdk.serialFilter=maxdepth=5;maxrefs=20;maxbytes=65536;maxarray=1000;SerialFilterDemo$Message;!*' SerialFilterDemo --global
~~~

Stdout:

~~~text
global filter restored: hello
~~~

Ví dụ dùng tên lớp nested trong default package để dễ chạy độc lập. Trong ứng dụng thực tế, thay pattern bằng tên module/package/lớp đầy đủ của các kiểu DTO được cho phép.

## 7. Phân biệt filter toàn JVM và filter theo luồng

Nếu một `ObjectInputStream` không có filter riêng, filter toàn JVM được chọn cho stream đó. Khi ứng dụng gọi `setObjectInputFilter()`, filter factory quyết định filter nào sẽ hoạt động.

Trên JDK 9 đến JDK 16, không có filter factory của JEP 415. Filter riêng của stream có thể thay thế chính sách JVM-wide cho stream đó. Vì vậy, không nên giả định hai filter tự động được cộng dồn.

Từ JDK 17, JEP 415 bổ sung **deserialization filter factory**. Factory được gọi khi tạo `ObjectInputStream` và khi gắn filter riêng; nó nhận filter hiện tại và filter được yêu cầu, sau đó quyết định chọn hoặc kết hợp chúng.

Có thể cấu hình factory bằng `ObjectInputFilter.Config.setSerialFilterFactory(...)` hoặc property `jdk.serialFilterFactory`. Factory chỉ được thiết lập một lần. Ví dụ sau minh họa cách kết hợp hai filter theo chính sách allow-list chặt:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory((current, requested) -> {
    if (current == null) {
        return requested == null
                ? null
                : ObjectInputFilter.rejectUndecidedClass(requested);
    }
    if (requested == null) {
        return current;
    }

    ObjectInputFilter strictCurrent =
            ObjectInputFilter.rejectUndecidedClass(current);
    ObjectInputFilter strictRequested =
            ObjectInputFilter.rejectUndecidedClass(requested);

    return ObjectInputFilter.merge(strictCurrent, strictRequested);
});
~~~

Đoạn trên dành cho chính sách mà mỗi filter là một allow-list: lớp không được filter đó xác nhận sẽ bị từ chối. Không áp dụng `rejectUndecidedClass` một cách máy móc cho filter chỉ làm nhiệm vụ reject-list, vì `UNDECIDED` có thể là kết quả có chủ ý.

`ObjectInputFilter.merge(a, b)` trả về `REJECTED` nếu một trong hai filter từ chối; trả về `ALLOWED` nếu một trong hai cho phép; còn lại là `UNDECIDED`. Vì vậy, nếu cần giao của hai allow-list, phải biến kết quả `UNDECIDED` thành từ chối cho từng allow-list trước khi merge. Chỉ trả về filter được yêu cầu từ factory có thể vô tình làm mất chính sách toàn JVM.

## 8. Giới hạn bảo vệ và thực hành an toàn

Serialization filtering là một lớp phòng vệ cho quá trình khôi phục object, không phải cơ chế xác thực dữ liệu toàn diện.

- Filter kiểm tra lớp và giới hạn tài nguyên; nó không xác minh mọi giá trị field theo quy tắc nghiệp vụ.
- Filter không được gọi cho primitive và String được mã hóa trực tiếp; đừng dùng nó để kiểm tra nội dung các giá trị này.
- Một lớp được allow vẫn có thể có `readObject`, `readResolve` hoặc hành vi khác cần được đánh giá. Chỉ cho phép những kiểu thực sự cần thiết.
- Bộ lọc không xác minh nguồn gửi, chữ ký hay tính toàn vẹn của dữ liệu.
- Không dùng reject-list đơn lẻ như giải pháp đầy đủ cho dữ liệu không đáng tin cậy; ưu tiên allow-list rõ ràng và giới hạn tài nguyên.
- Kiểm tra cả các kiểu phụ thuộc trong object graph, bao gồm lớp cha, interface, collection và kiểu phần tử mảng.
- Chọn maxdepth, maxrefs, maxbytes và maxarray theo dữ liệu hợp lệ, rồi kiểm thử với trường hợp lớn nhất có thể chấp nhận.
- Ghi log và theo dõi lỗi từ chối để phân biệt dữ liệu không hợp lệ với giới hạn cấu hình quá thấp.
- Nếu có thể, dùng định dạng trao đổi có schema rõ ràng như JSON, CBOR hoặc Protocol Buffers thay vì deserialize native Java object từ nguồn không đáng tin cậy.

## 9. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ filter đã bật sẵn | Java không bật serialization filtering mặc định | Cấu hình JVM-wide hoặc gắn filter vào từng stream |
| Gắn filter sau readObject | Object đã được khôi phục trước khi filter được đặt | Gắn ngay sau khi tạo ObjectInputStream |
| Nghĩ UNDECIDED là từ chối | UNDECIDED chỉ có nghĩa filter không đưa ra quyết định | Dùng allow-list kết thúc bằng `!*` hoặc rejectUndecidedClass khi phù hợp |
| Chỉ đặt maxdepth | Đồ thị vẫn có thể có quá nhiều reference, byte hoặc mảng lớn | Cân nhắc đủ bốn giới hạn tài nguyên |
| Dùng `pkg.*` để cho phép cả subpackage | `.*` chỉ khớp lớp trực tiếp trong package | Dùng `.**` nếu thật sự cần package con |
| Đặt `!*` trước lớp được phép | Pattern lớp đầu tiên khớp quyết định kết quả | Đặt allow pattern trước reject-all |
| Nghĩ filter theo luồng luôn cộng với filter toàn JVM | Filter factory mặc định có thể thay filter hiện tại bằng filter được yêu cầu | Thiết kế filter factory hoặc composition rõ ràng |
| Cho rằng filter xác thực field và dữ liệu nghiệp vụ | Filter tập trung vào class và graph metrics | Validate object sau khi đọc và kiểm tra nguồn dữ liệu |
| Cho phép toàn bộ package quá rộng | Package có thể chứa lớp không cần cho giao thức | Allow-list lớp cụ thể hoặc package hẹp |
| Nghĩ setObjectInputFilter gọi được nhiều lần | Mỗi stream chỉ được đặt filter một lần trước khi đọc object | Xây filter hoàn chỉnh trước khi bắt đầu đọc |

## 10. Checklist triển khai

- Xác định dữ liệu có thật sự cần Java native serialization hay không.
- Nếu phải deserialize, xác định tập lớp hợp lệ của từng nguồn.
- Đặt filter theo luồng ngay sau khi tạo ObjectInputStream.
- Cấu hình `jdk.serialFilter` cho chính sách chung của tiến trình.
- Đặt giới hạn maxdepth, maxrefs, maxbytes và maxarray theo tải hợp lệ.
- Dùng allow-list và reject-all làm mặc định khi cần kiểm soát lớp chặt.
- Kiểm tra trạng thái UNDECIDED và quy tắc kết hợp filter.
- Nếu cần cả global và stream-specific policy, xác định rõ hành vi filter factory; trên JDK 17+ có thể dùng JEP 415.
- Xử lý InvalidClassException và ghi log quyết định từ chối.
- Kiểm thử cả dữ liệu hợp lệ, lớp ngoài allow-list và đồ thị vượt giới hạn.
- Validate giá trị và invariant nghiệp vụ sau khi đọc.
- Không xem serialization filter là thay thế cho xác thực nguồn, kiểm tra toàn vẹn hoặc thiết kế giao thức an toàn.

## 11. Tài liệu tham khảo

- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290)
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)
- [ObjectInputFilter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
- [ObjectInputStream — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [Serialization Filtering — Java SE 17 Guide](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html)

Filter theo luồng phù hợp với từng hợp đồng dữ liệu cụ thể; `jdk.serialFilter` tạo chính sách chung cho tiến trình. Kết hợp allow-list, giới hạn đồ thị và quy tắc composition đúng giúp giảm rủi ro khi ứng dụng buộc phải đọc Java serialized objects.