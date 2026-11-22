# Giới hạn bảo vệ và cách tránh giải tuần tự dữ liệu không đáng tin cậy

Giải tuần tự (deserialization) bằng **ObjectInputStream** có thể tạo lại cả một đồ thị object từ byte stream. Nếu dữ liệu đến từ người dùng, mạng hoặc nguồn không được tin cậy, stream có thể yêu cầu JVM tạo những class ngoài dự kiến, tạo mảng rất lớn hoặc dựng đồ thị object quá sâu và tốn nhiều tài nguyên.

Java 9 đưa vào **ObjectInputFilter** qua JEP 290 để lọc class và giới hạn tài nguyên trong lúc giải tuần tự. Đây là lớp phòng vệ quan trọng khi ứng dụng buộc phải đọc Java serialization. Tuy nhiên, filter không biến dữ liệu tùy ý thành an toàn. Cách an toàn nhất vẫn là tránh Java native serialization cho dữ liệu không tin cậy; nếu bắt buộc dùng, hãy áp dụng allowlist hẹp, giới hạn kích thước và xác thực dữ liệu sau khi đọc.

## 1. Vì sao giải tuần tự dữ liệu không tin cậy nguy hiểm?

ObjectInputStream không chỉ đọc một chuỗi byte thành các trường đơn giản. readObject() có thể khôi phục cả đồ thị object, tải class cần thiết và gọi logic giải tuần tự do class định nghĩa.

Những rủi ro thường gặp:

- **Unexpected class:** stream yêu cầu khôi phục class mà ứng dụng không định cho phép.
- **Gadget chain:** một chuỗi class có sẵn trong classpath kết hợp các hook giải tuần tự để gây tác động ngoài ý muốn, chẳng hạn thực thi lệnh hoặc truy cập tài nguyên.
- **Denial of service:** đồ thị quá sâu, quá nhiều reference, mảng lớn hoặc stream rất dài làm tăng CPU và bộ nhớ.
- **Dữ liệu sai cấu trúc:** object có đúng kiểu Java nhưng các trường chứa giá trị vượt ngoài quy tắc nghiệp vụ.
- **Logic tùy biến khi đọc:** readObject(), readExternal() hoặc readResolve() của class được phép vẫn có thể thực hiện logic riêng.

Một phép ép kiểu sau readObject() không phải biện pháp bảo vệ:

~~~java
Message message = (Message) input.readObject();
~~~

Nếu object không mong muốn đã được tạo và logic giải tuần tự đã chạy, việc ép kiểu mới thất bại là quá muộn. Cần quyết định class nào được phép trước khi ObjectInputStream tạo object.

## 2. ObjectInputFilter hoạt động ở đâu?

**ObjectInputFilter** thuộc package java.io và có từ Java 9. Filter được gắn với ObjectInputStream và được gọi trong quá trình readObject() hoặc readUnshared() để kiểm tra class, array và các chỉ số của đồ thị đang khôi phục.

Trình tự khái quát:

1. Tạo ObjectInputStream từ nguồn byte.
2. Gắn filter trước lần đọc object đầu tiên.
3. Khi stream yêu cầu tạo object hoặc array, filter nhận FilterInfo.
4. Filter trả về ALLOWED, REJECTED hoặc UNDECIDED.
5. Nếu bị REJECTED, lần đọc đang thực hiện dừng bằng InvalidClassException.

Filter có thể được gắn cho một stream riêng bằng setObjectInputFilter(), hoặc cấu hình ở cấp JVM bằng jdk.serialFilter / Config.setSerialFilter().

Filter phải được cấu hình trước khi readObject() hoặc readUnshared() đọc object. Với một ObjectInputStream, setObjectInputFilter() chỉ được gọi một lần.

## 3. FilterInfo cung cấp những thông tin nào?

FilterInfo mô tả class hoặc trạng thái của stream tại thời điểm filter được gọi:

| Thuộc tính | Ý nghĩa | Dùng để |
|---|---|---|
| serialClass() | Class của object hoặc array đang được xử lý | Allowlist hoặc reject class |
| arrayLength() | Số phần tử của array; -1 nếu không phải array | Chặn array quá lớn |
| depth() | Độ sâu hiện tại của đồ thị object | Chặn cấu trúc lồng nhau quá sâu |
| references() | Số object reference đã đọc đến thời điểm hiện tại | Chặn đồ thị có quá nhiều object/reference |
| streamBytes() | Số byte đã tiêu thụ từ stream | Giới hạn lượng dữ liệu đã đọc |

Depth bắt đầu từ 1 khi đọc object gốc và tăng khi có lời gọi readObject() lồng nhau. References là bộ đếm tích lũy của object và reference đã đọc, bao gồm object hiện tại.

Có hai trường hợp cần xử lý đúng:

- serialClass() có thể là null khi stream đang đọc back-reference đến object đã được đọc trước đó. Khi đó filter vẫn có thể kiểm tra depth, references và streamBytes.
- arrayLength() là -1 khi phần tử đang xét không phải array.

**String và primitive được mã hóa trực tiếp trong stream không gọi filter.** Array kiểu String vẫn được kiểm tra như một array, bao gồm class array và độ dài. Vì vậy, không thể dựa vào class filter để giới hạn độ dài một String riêng lẻ; cần giới hạn byte đầu vào và xác thực độ dài trường sau khi giải tuần tự.

## 4. Ba trạng thái của filter

| Status | Ý nghĩa | Khi dùng |
|---|---|---|
| ALLOWED | Filter xác nhận class/array hoặc trạng thái hiện tại được phép | Class thuộc allowlist và các giới hạn chưa bị vượt |
| REJECTED | Filter từ chối dữ liệu đang đọc | Class ngoài allowlist hoặc vượt giới hạn |
| UNDECIDED | Filter không đưa ra kết luận | Filter chuyên biệt chỉ kiểm tra một phần; filter khác có thể tiếp tục quyết định |

Với một filter allowlist dùng riêng cho một luồng, hãy trả REJECTED cho mọi class không được liệt kê. Nếu trả UNDECIDED cho class lạ, filter chỉ đang nói rằng nó không có ý kiến; trạng thái đó không đồng nghĩa với default deny.

Có thể trả UNDECIDED khi serialClass() là null vì lúc đó không có class mới để xét, nhưng vẫn phải kiểm tra các giới hạn số liệu trước khi trả trạng thái.

Nếu filter trả REJECTED, trả null hoặc ném RuntimeException, ObjectInputStream dừng lần đọc bằng InvalidClassException. Sau lỗi giải tuần tự, stream ở trạng thái không xác định; hãy đóng và bỏ stream đó, không tiếp tục đọc như thể dữ liệu vẫn hợp lệ.

## 5. Giới hạn tài nguyên cần đặt

Bốn giới hạn có sẵn trong cú pháp filter pattern:

| Giới hạn | Ý nghĩa | Rủi ro cần giảm |
|---|---|---|
| maxdepth | Độ sâu tối đa của đồ thị object | Đồ thị lồng nhau quá sâu và đệ quy tốn tài nguyên |
| maxrefs | Số reference tối đa | Quá nhiều object/reference |
| maxbytes | Số byte tối đa của input stream theo số liệu filter | Stream quá lớn |
| maxarray | Số phần tử tối đa của mỗi array | Array cấp phát quá lớn |

Giá trị giới hạn phải được chọn theo dữ liệu hợp lệ thực tế của ứng dụng. Không nên sao chép một con số chung cho mọi hệ thống.

Ví dụ, nếu thông điệp hợp lệ chỉ chứa vài DTO và array nhỏ, giới hạn depth, references và array nên đủ thấp để chặn cấu trúc bất thường. Nếu payload bình thường có thể lớn hơn, hãy đo kích thước hợp lệ rồi đặt biên có khoảng dự phòng hợp lý.

streamBytes() được đặc tả là số liệu phụ thuộc implementation và không nhất thiết liên hệ trực tiếp với object vừa gây callback. Ngoài ra, String và primitive không gọi filter. Với dữ liệu đến từ socket hoặc file không tin cậy, hãy giới hạn tổng số byte ở lớp InputStream hoặc giao thức truyền tải trước khi đưa dữ liệu vào ObjectInputStream.

## 6. Viết filter allowlist cho từng ObjectInputStream

Filter tường minh cho phép khai báo class được chấp nhận và giới hạn đồ thị:

~~~java
private static final long MAX_DEPTH = 10;
private static final long MAX_REFERENCES = 50;
private static final long MAX_STREAM_BYTES = 16_384;
private static final long MAX_ARRAY_LENGTH = 1_024;

private static final ObjectInputFilter FILTER = info -> {
    if (info.depth() > MAX_DEPTH
            || info.references() > MAX_REFERENCES
            || info.streamBytes() > MAX_STREAM_BYTES
            || info.arrayLength() > MAX_ARRAY_LENGTH) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == Message.class || type == byte[].class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
~~~

Allowlist trên chỉ chấp nhận đúng class Message và array byte[]. Các class khác bị từ chối. Nếu DTO cần thêm kiểu dữ liệu, hãy xem xét từng kiểu và thêm đúng class cần thiết.

Không nên allow toàn bộ package rộng hoặc mọi class trong java.util chỉ để làm ví dụ chạy được. Một class được phép có thể chứa field tham chiếu đến class khác; những class lồng bên trong đồ thị cũng phải nằm trong chính sách cho phép.

Gắn filter vào stream trước khi đọc:

~~~java
try (ObjectInputStream input =
        new ObjectInputStream(sourceInputStream)) {
    input.setObjectInputFilter(FILTER);
    Object value = input.readObject();
}
~~~

Nếu ứng dụng đã cấu hình filter cấp JVM hoặc filter factory, cần hiểu chính sách kết hợp đang hoạt động. Không giả định rằng filter riêng của stream tự động được ghép với filter toàn cục trong mọi cấu hình; hành vi mặc định và factory có thể thay đổi cách chọn filter.

## 7. Cấu hình filter bằng pattern string

Java 9 cung cấp ObjectInputFilter.Config.createFilter(String). Pattern gồm các phần phân cách bằng dấu chấm phẩy. Có thể đặt giới hạn đồ thị và class pattern trong cùng một chuỗi:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;"
      + "maxrefs=50;"
      + "maxbytes=16384;"
      + "maxarray=1024;"
      + "com.example.dto.**;"
      + "!*");
~~~

Ý nghĩa:

- maxdepth=10 giới hạn độ sâu đồ thị.
- maxrefs=50 giới hạn số reference.
- maxbytes=16384 giới hạn số byte theo bộ đếm của filter.
- maxarray=1024 giới hạn số phần tử mỗi array.
- com.example.dto.** cho phép class trong package DTO và các subpackage.
- !* từ chối mọi class không khớp pattern trước đó.

Quy tắc pattern quan trọng:

- Pattern được xét từ trái sang phải; pattern class đầu tiên khớp quyết định ALLOWED hoặc REJECTED.
- Các giới hạn được kiểm tra trước các class pattern, bất kể vị trí trong chuỗi.
- Dấu cách là ký tự có ý nghĩa; tránh thêm whitespace ngoài ý muốn.
- pkg.* khớp class trong package đó; pkg.** khớp cả package và subpackage.
- Với array, pattern class xét kiểu phần tử thay vì tên kiểu array.

!* ở cuối tạo chính sách từ chối mặc định cho mọi class không được cho phép trước đó. Đây là cấu trúc dễ kiểm tra hơn một denylist dài, vì denylist khó bao phủ mọi class nguy hiểm có thể xuất hiện trên classpath.

## 8. Filter cấp JVM và cấu hình lúc khởi động

Có thể đặt process-wide filter bằng system property jdk.serialFilter khi khởi động JVM:

~~~bash
java -Djdk.serialFilter="maxdepth=10;maxrefs=50;maxbytes=16384;maxarray=1024;com.example.dto.**;!*" Application
~~~

Hoặc cấu hình bằng API trước khi các ObjectInputStream được sử dụng:

~~~java
ObjectInputFilter globalFilter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=50;maxbytes=16384;maxarray=1024;"
      + "com.example.dto.**;!*");

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

Config.setSerialFilter() chỉ thiết lập filter cấp JVM nếu nó chưa được cấu hình hoặc thiết lập trước đó. Vì đây là chính sách toàn tiến trình, hãy cấu hình tập trung lúc khởi động, không để các thư viện tùy ý thay đổi.

Filter cấp JVM được áp dụng cho ObjectInputStream không có filter riêng. Trong cấu hình Java 9, setObjectInputFilter() có thể đặt filter cho stream cụ thể. Nếu ứng dụng cần kết hợp nhiều chính sách, phải chủ động thiết kế việc kết hợp thay vì mặc định rằng mọi filter đều được hợp nhất.

## 9. Java 17+: filter factory theo ngữ cảnh

Java 17 bổ sung **JEP 415 — Context-Specific Deserialization Filters**. Từ phiên bản này, ứng dụng có thể đăng ký filter factory toàn JVM bằng ObjectInputFilter.Config.setSerialFilterFactory().

Factory được gọi khi ObjectInputStream được tạo và khi filter riêng của stream được đặt. Nó nhận filter hiện tại và filter được yêu cầu, rồi quyết định filter thực tế sẽ áp dụng. Factory có thể chọn hoặc kết hợp chính sách dựa trên thread context, caller, module, class loader hoặc ngữ cảnh thực thi.

Cơ chế này hữu ích cho ứng dụng lớn có nhiều thư viện hoặc nhiều tenant, trong đó mỗi luồng giải tuần tự cần allowlist riêng. Ví dụ:

- Bộ đọc session chỉ được khôi phục các class session đã định.
- Thành phần import chỉ được nhận DTO import.
- Thư viện nội bộ chỉ được nhận một nhóm kiểu dữ liệu đã công bố.
- Filter cấp JVM vẫn được kết hợp với filter theo ngữ cảnh để giữ lớp bảo vệ chung.

Factory là cấu hình cấp JVM và chỉ nên được thiết lập bởi thành phần điều phối ứng dụng. API filter factory, allowFilter(), rejectFilter(), merge() và rejectUndecidedClass() thuộc Java 17 trở lên; chúng không có trong baseline Java 9.

## 10. Những giới hạn filter không thể thay thế

ObjectInputFilter kiểm tra class và một số chỉ số tài nguyên. Nó không phải bộ xác thực đầy đủ cho nội dung nghiệp vụ.

Các giới hạn cần nhớ:

- Filter không được gọi cho primitive và String được mã hóa trực tiếp. Hãy giới hạn tổng byte ở lớp input và kiểm tra độ dài String sau khi đọc.
- Filter không kiểm tra mọi giá trị field. Một Message hợp lệ về class vẫn có thể chứa tên, đường dẫn, số tiền hoặc trạng thái không hợp lệ.
- Class được allow vẫn có thể định nghĩa readObject(), readExternal() hoặc readResolve() với logic tùy biến. Chỉ cho phép DTO đơn giản và class đã được kiểm tra.
- Filter không thay thế xác thực người gửi, kiểm tra chữ ký/MAC, kiểm soát quyền truy cập hoặc xác thực nghiệp vụ.
- Filter không loại bỏ mọi gadget chain nếu allowlist quá rộng hoặc class được phép có hành vi nguy hiểm.
- Giới hạn maxbytes dựa trên số liệu filter; hãy giới hạn byte thô ở transport/input layer nếu cần một trần tuyệt đối.

Sau khi đọc object, kiểm tra root type và từng trường theo schema nghiệp vụ. Không dùng cast thành công làm bằng chứng dữ liệu đáng tin cậy.

## 11. Ví dụ hoàn chỉnh: allowlist, giới hạn array và kiểm tra dữ liệu sau khi đọc

Ví dụ sau chỉ cho phép class Message và byte[]. Filter chặn array quá lớn, class ngoài allowlist, đồ thị quá sâu hoặc quá nhiều reference. Vì String không được filter trực tiếp, chương trình kiểm tra thêm độ dài text sau khi đọc.

Lưu chương trình dưới tên **SerialFilterDemo.java**.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.util.Date;

public class SerialFilterDemo {
    private static final long MAX_DEPTH = 10;
    private static final long MAX_REFERENCES = 50;
    private static final long MAX_STREAM_BYTES = 16_384;
    private static final long MAX_INPUT_BYTES = 16_384;
    private static final long MAX_ARRAY_LENGTH = 1_024;
    private static final int MAX_TEXT_LENGTH = 256;

    private static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;
        private final String text;
        private final byte[] payload;

        Message(String text, byte[] payload) {
            this.text = text;
            this.payload = payload;
        }

        String getText() {
            return text;
        }

        int getPayloadLength() {
            return payload.length;
        }
    }

    private static final ObjectInputFilter FILTER = info -> {
        if (info.depth() > MAX_DEPTH
                || info.references() > MAX_REFERENCES
                || info.streamBytes() > MAX_STREAM_BYTES
                || info.arrayLength() > MAX_ARRAY_LENGTH) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }
        if (type == Message.class || type == byte[].class) {
            return ObjectInputFilter.Status.ALLOWED;
        }
        return ObjectInputFilter.Status.REJECTED;
    };

    private static byte[] serialize(Object value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(value);
        }
        return bytes.toByteArray();
    }

    private static Object deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        if (bytes.length > MAX_INPUT_BYTES) {
            throw new IOException("serialized input exceeds byte limit");
        }
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            input.setObjectInputFilter(FILTER);
            return input.readObject();
        }
    }

    private static Message readMessage(byte[] bytes) throws Exception {
        Object value = deserialize(bytes);
        if (!(value instanceof Message)) {
            throw new InvalidObjectException("unexpected root type");
        }
        Message message = (Message) value;
        if (message.text == null || message.text.length() > MAX_TEXT_LENGTH) {
            throw new InvalidObjectException("text length is outside the schema");
        }
        return message;
    }

    public static void main(String[] args) throws Exception {
        Message valid = readMessage(
                serialize(new Message("hello", new byte[] {1, 2, 3})));
        System.out.println("accepted message: " + valid.getText());
        System.out.println("payload bytes: " + valid.getPayloadLength());

        try {
            readMessage(serialize(
                    new Message("too large", new byte[2_048])));
            throw new AssertionError("oversized array was accepted");
        } catch (InvalidClassException expected) {
            System.out.println("oversized array: rejected");
        }

        try {
            readMessage(serialize(new Date()));
            throw new AssertionError("unexpected class was accepted");
        } catch (InvalidClassException expected) {
            System.out.println("unexpected class: rejected");
        }

        String longText = new String(new char[300]).replace('\0', 'x');
        try {
            readMessage(serialize(new Message(longText, new byte[0])));
            throw new AssertionError("oversized text was accepted");
        } catch (InvalidObjectException expected) {
            System.out.println("oversized text: rejected");
        }
    }
}
~~~

Biên dịch và chạy trên Java 9 trở lên:

~~~bash
javac --release 9 SerialFilterDemo.java
java SerialFilterDemo
~~~

Kết quả stdout:

~~~text
accepted message: hello
payload bytes: 3
oversized array: rejected
unexpected class: rejected
oversized text: rejected
~~~

Ví dụ dùng byte[] trong bộ nhớ nên kiểm tra bytes.length trước khi tạo ObjectInputStream. Với socket hoặc stream không có sẵn trong bộ nhớ, hãy dùng một InputStream giới hạn số byte hoặc giới hạn độ dài message ngay ở giao thức truyền tải.

## 12. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ ép kiểu kết quả readObject() | Class không mong muốn có thể đã được khôi phục trước khi cast thất bại | Gắn filter trước khi đọc object |
| Chỉ dùng denylist | Có thể bỏ sót class gadget mới hoặc class được thêm vào classpath | Ưu tiên allowlist theo từng use case |
| Allow cả package quá rộng | Class nguy hiểm trong package được phép cũng có thể được đọc | Liệt kê package DTO nhỏ hoặc class cụ thể |
| Chỉ giới hạn class, không giới hạn đồ thị | Attacker vẫn có thể tạo đồ thị sâu, nhiều reference hoặc array lớn | Đặt maxdepth, maxrefs, maxbytes và maxarray |
| Cho rằng String được filter | String và primitive được mã hóa trực tiếp không gọi callback | Giới hạn byte đầu vào và xác thực giá trị String |
| Cho rằng UNDECIDED có nghĩa là reject | Filter chưa đưa ra kết luận; deserialization có thể tiếp tục | Trả REJECTED cho class không nằm trong allowlist |
| Gắn filter sau readObject() | Object đã được tạo và logic đọc có thể đã chạy | Gắn filter ngay sau khi tạo ObjectInputStream |
| Gọi setObjectInputFilter() nhiều lần | Có thể nhận IllegalStateException | Thiết lập đúng một lần trước khi đọc object đầu tiên |
| Tin rằng maxbytes là trần byte tuyệt đối trên mọi implementation | streamBytes phụ thuộc implementation và String không gọi filter | Giới hạn raw input ở transport layer |
| Không kiểm tra dữ liệu sau khi đọc | Object đúng class vẫn có thể chứa giá trị sai nghiệp vụ | Kiểm tra schema, độ dài, range và quyền truy cập |
| Tiếp tục đọc stream sau InvalidClassException | Stream có thể ở trạng thái không xác định | Đóng và bỏ stream sau lỗi giải tuần tự |

## 13. Ghi nhớ

- ObjectInputFilter được giới thiệu trong Java 9 qua JEP 290.
- Filter kiểm tra class, array length, depth, references và streamBytes trong quá trình giải tuần tự.
- Ưu tiên allowlist hẹp và reject class không được khai báo.
- Đặt filter trước readObject() và chỉ cấu hình một lần cho mỗi stream.
- Dùng maxdepth, maxrefs, maxbytes và maxarray theo giới hạn dữ liệu hợp lệ.
- String và primitive được mã hóa trực tiếp không gọi filter; cần giới hạn byte đầu vào và xác thực giá trị sau khi đọc.
- Filter không xác thực field, không bảo đảm mọi class được allow đều an toàn và không thay thế kiểm tra nghiệp vụ.
- Java 17 bổ sung filter factory theo ngữ cảnh qua JEP 415.
- Tránh Java native deserialization với dữ liệu không tin cậy khi có thể; ưu tiên định dạng có schema rõ ràng và parser được cấu hình nghiêm ngặt.
- Khi bắt buộc đọc Java serialization, kết hợp allowlist, giới hạn tài nguyên, giới hạn byte thô và validation sau khi đọc.

## Tài liệu tham khảo

- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290)
- [ObjectInputFilter — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/io/ObjectInputFilter.html)
- [ObjectInputFilter.Config — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/io/ObjectInputFilter.Config.html)
- [ObjectInputStream — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/io/ObjectInputStream.html)
- [ObjectInputFilter — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ObjectInputFilter.html)
- [ObjectInputStream — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ObjectInputStream.html)
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415)
- [JDK 17 Release Notes — JEP 415](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html)
- [Secure Coding Guidelines for Java SE](https://www.oracle.com/java/technologies/javase/seccodeguide.html)
