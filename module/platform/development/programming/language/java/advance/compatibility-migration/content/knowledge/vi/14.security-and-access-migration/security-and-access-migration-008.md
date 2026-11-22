# Serialization filter và dữ liệu đầu vào từ ứng dụng phiên bản khác

Trong quá trình **Java Advance Compatibility Migration**, một ứng dụng có thể nhận dữ liệu do phiên bản cũ, phiên bản mới hoặc một dịch vụ khác tạo ra. Nếu dữ liệu đó dùng **Java native object serialization**, việc đọc lại object không chỉ là vấn đề tương thích class và **serialVersionUID**. Nó còn là một ranh giới bảo mật: **ObjectInputStream** có thể tạo đối tượng, kích hoạt logic deserialization và xử lý cả một object graph trước khi ứng dụng kiểm tra kiểu của object gốc.

Bài học thuộc chương **Bảo mật và quyền truy cập**, tập trung vào **serialization filter** trong Java, yêu cầu kiểm soát dữ liệu từ ứng dụng phiên bản khác và cách nâng cấp mà không vô tình mở rộng tập class được phép deserialize.

Một bộ lọc tốt cần cân bằng hai mục tiêu:

1. **Tương thích có kiểm soát:** cho phép chính xác các cấu trúc dữ liệu hợp lệ của những phiên bản cần hỗ trợ.
2. **Giảm rủi ro bảo mật và từ chối dịch vụ:** từ chối các kiểu không được phép, độ sâu quá lớn, số tham chiếu bất thường, mảng quá dài hoặc luồng dữ liệu vượt giới hạn phù hợp.

**Lưu ý phạm vi:** **ObjectInputFilter** thuộc cơ chế Java native serialization với **ObjectInputStream**. Nó không tự động kiểm soát JSON qua Jackson, XML, Protocol Buffers, Kryo hoặc những định dạng khác. Các định dạng đó cần cơ chế kiểm tra và giới hạn riêng.

## 1. Vì sao dữ liệu serialized từ phiên bản khác là một vấn đề bảo mật?

Một đối tượng Java được serialize có thể chứa thông tin về kiểu, field và quan hệ tham chiếu giữa nhiều object. Khi deserialize, runtime và các lớp tham gia có thể thực hiện nhiều bước trước khi lời gọi **readObject()** trả về một giá trị.

Ví dụ luồng trao đổi:

~~~text
Ứng dụng A / phiên bản 1
          |
          | Serialized bytes
          v
Queue / Cache / File / TCP
          |
          v
Ứng dụng B / phiên bản 2
          |
          v
ObjectInputStream
          |
          +--> Resolve class
          +--> Tạo object graph
          +--> Khôi phục state / chạy serialization hooks
          |
          v
Object được trả về cho mã ứng dụng
~~~

Ngay cả khi hai ứng dụng thuộc cùng tổ chức, dữ liệu nhận được vẫn có thể không đáng tin cậy theo nghĩa bảo mật:

- Queue hoặc cache có thể chứa thông điệp cũ chưa được kiểm chứng.
- Một producer có thể đã bị chiếm quyền hoặc cấu hình sai.
- File lưu trữ có thể bị thay đổi.
- Dữ liệu được gửi từ hệ thống đối tác hoặc phiên bản nằm ngoài vòng đời hỗ trợ.
- Payload hợp lệ về hình thức nhưng quá lớn hoặc chứa object graph bất thường.
- Phiên bản producer và consumer có dependency graph khác nhau.

Việc producer tuyên bố đang dùng cùng phiên bản Java không bảo đảm dữ liệu an toàn. Ngược lại, dữ liệu từ phiên bản cũ không tự động nguy hiểm; quan trọng là **nguồn gốc, định dạng, tập kiểu cho phép và giới hạn xử lý**.

### 1.1. Hai lớp tương thích cần được xét riêng

| Khía cạnh | Câu hỏi | Ví dụ |
|---|---|---|
| Serialization compatibility | Consumer mới có đọc được stream từ producer cũ không? | Field mới, field bị xóa, serialVersionUID |
| Security acceptance | Consumer có nên chấp nhận object graph đó không? | Class không nằm trong allowlist, depth vượt ngưỡng |

Có thể xảy ra cả bốn trường hợp:

- Dữ liệu đọc được **và** được chính sách cho phép.
- Dữ liệu đọc được về mặt kỹ thuật nhưng bị filter từ chối.
- Dữ liệu được policy cho phép nhưng không thể giải mã vì schema/class khác.
- Dữ liệu vừa không tương thích vừa không được phép xử lý.

Không nên thay đổi allowlist chỉ để che một lỗi serialVersionUID. Cũng không nên sửa **serialVersionUID** chỉ để vượt qua một filter từ chối class.

### 1.2. Những đường nhập cần khảo sát

Trong dự án Java thực tế, cần tìm toàn bộ nơi gọi trực tiếp hoặc gián tiếp đến **ObjectInputStream**:

- Byte stream qua socket hoặc giao thức nội bộ.
- File backup/cache chứa Java serialized objects.
- Hàng đợi hoặc messaging adapter dùng native serialization.
- Distributed cache, session hoặc lưu trữ trạng thái cũ.
- Job batch đọc artifact từ phiên bản trước.
- RMI hoặc thành phần legacy sử dụng object serialization.
- Framework, SDK hoặc thư viện có deserialization nội bộ.

Việc không tìm thấy từ khóa **new ObjectInputStream** trong source ứng dụng chưa chứng minh là không có deserialization. Framework có thể tạo stream bên trong thư viện.

## 2. Java native serialization hoạt động ở mức khái niệm

Java serialization truyền thống dùng các thành phần chính:

- **Serializable:** marker interface thông báo class tham gia cơ chế serialization chuẩn.
- **ObjectOutputStream:** ghi object graph thành stream.
- **ObjectInputStream:** khôi phục object graph từ stream.
- **serialVersionUID:** định danh phiên bản serial form của class.
- Các hook như **writeObject**, **readObject**, **readResolve**, **writeReplace** và cơ chế **Externalizable** khi class hỗ trợ.
- Class loader, field descriptor và object references tham gia quá trình khôi phục.

Ví dụ đơn giản:

~~~java
package com.example.transfer;

import java.io.Serial;
import java.io.Serializable;

public final class TransferEnvelope implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String requestId;
    private long amount;

    public TransferEnvelope(String requestId, long amount) {
        this.requestId = requestId;
        this.amount = amount;
    }

    public String getRequestId() {
        return requestId;
    }

    public long getAmount() {
        return amount;
    }
}
~~~

Ví dụ ghi dữ liệu:

~~~java
import com.example.transfer.TransferEnvelope;
import java.io.ByteArrayOutputStream;
import java.io.ObjectOutputStream;

ByteArrayOutputStream output = new ByteArrayOutputStream();

try (ObjectOutputStream stream = new ObjectOutputStream(output)) {
    stream.writeObject(new TransferEnvelope("REQ-001", 150));
}

byte[] payload = output.toByteArray();
~~~

Đọc bằng **ObjectInputStream** sẽ khôi phục object theo thông tin có trong stream. Nhưng **đừng** đọc dữ liệu từ nguồn không tin cậy bằng **readObject()** mà thiếu chính sách an toàn phù hợp.

### 2.1. Vì sao kiểm tra kiểu sau readObject là chưa đủ?

Một cách viết không an toàn khi chỉ dựa vào kiểm tra kiểu sau cùng:

~~~java
Object value = input.readObject();

if (!(value instanceof TransferEnvelope)) {
    throw new IllegalArgumentException("Unexpected type");
}
~~~

Vấn đề: đối tượng đã được deserialize **trước** khi phép kiểm tra **instanceof** diễn ra. Runtime có thể đã:

- Resolve nhiều class khác nhau.
- Tạo các đối tượng lồng nhau.
- Xử lý mảng và reference graph.
- Thực thi những hook deserialization được phép của class.
- Tiêu thụ đáng kể CPU hoặc bộ nhớ.

**ObjectInputFilter** giúp đưa việc xét class và giới hạn tài nguyên vào quá trình deserialize, thay vì chờ đến sau khi khôi phục xong object.

Điều đó không có nghĩa filter chặn được mọi hành vi nguy hiểm. Filter phải kết hợp với việc chỉ nhận dữ liệu từ nguồn được kiểm soát, giới hạn kích thước ở tầng vận chuyển và xác thực trạng thái object sau khi đọc.

## 3. ObjectInputFilter và các cơ chế nền tảng

**JEP 290 – Filter Incoming Serialization Data** giới thiệu cơ chế lọc dữ liệu native Java serialization. **ObjectInputFilter** cho phép áp đặt chính sách khi **ObjectInputStream** đang khôi phục object graph.

Các thông tin filter có thể quan sát gồm:

- Class đang được cân nhắc.
- Chiều dài mảng nếu đang xử lý array.
- Độ sâu object graph.
- Số object references đã xử lý.
- Số byte từ stream đã tiêu thụ.

Một filter trả về một trong ba trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| **ALLOWED** | Điều kiện được cho phép bởi filter |
| **REJECTED** | Điều kiện bị từ chối, deserialization phải thất bại |
| **UNDECIDED** | Filter không đưa ra quyết định dứt khoát |

**UNDECIDED không tương đương REJECTED.** Nếu chỉ sử dụng một danh sách pattern cho phép mà không có quy tắc từ chối những class còn lại, các class không khớp có thể vẫn được xử lý tùy chính sách tổng hợp. Với untrusted input, cần thiết kế **deny by default** cho các class không được phép.

### 3.1. Filter không kiểm tra mọi giá trị

Serialization filter không thay thế validation nghiệp vụ. Đặc biệt:

- Filter không chứng minh giá trị String là hợp lệ.
- Filter không bảo đảm số tiền dương hoặc requestId có định dạng đúng.
- Các trường hợp như String được encode trực tiếp có thể không được gọi qua class filter theo cách mà người viết dự kiến.
- Filter không xác thực chữ ký hoặc danh tính producer.
- Filter không xác nhận payload hợp lệ về ngữ nghĩa sau khi dựng object.
- Filter không có nghĩa một class được allowlist luôn an toàn.

Ví dụ, object với **requestId = null** và **amount = -100** có thể có class hoàn toàn nằm trong allowlist, nhưng vẫn phải bị từ chối bởi business validation.

## 4. Các giới hạn quan trọng: depth, refs, bytes và array

Filter có thể áp dụng các ngưỡng nhằm giảm rủi ro dữ liệu bất thường.

| Giới hạn | Ý nghĩa | Rủi ro giảm bớt |
|---|---|---|
| **maxdepth** | Độ sâu tối đa của object graph | Đồ thị lồng nhau quá sâu |
| **maxrefs** | Số tham chiếu/object references tối đa trong quá trình đọc | Quá nhiều node hoặc tham chiếu |
| **maxbytes** | Số byte từ serialized stream mà bộ lọc cho phép xử lý | Stream quá lớn |
| **maxarray** | Chiều dài mảng tối đa | Mảng bất thường gây áp lực bộ nhớ |

Ví dụ policy:

~~~text
maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=4096
~~~

Các số trên chỉ là **giá trị minh họa**, không phải ngưỡng mặc định an toàn cho mọi hệ thống. Một payload hợp lệ chứa cấu trúc sâu hoặc số lượng item lớn có thể bị từ chối bởi cùng ngưỡng đó.

Cách chọn ngưỡng:

1. Đo dữ liệu hợp lệ ở baseline.
2. Xác định kích thước/dạng lớn nhất được contract hỗ trợ.
3. Dự kiến overhead khi producer và consumer ở hai phiên bản khác nhau.
4. Đặt giới hạn có biên an toàn nhưng hữu hạn.
5. Kiểm thử ngay dưới, bằng và vượt ngưỡng.
6. Đánh giá metric trên dữ liệu thực trước rollout.
7. Cập nhật theo thay đổi schema có kiểm soát.

**maxbytes không thay thế giới hạn ở tầng vận chuyển.** Nếu ứng dụng đọc toàn bộ body nhiều GB vào **byte[]** trước khi tạo **ObjectInputStream**, giới hạn filter có thể được áp dụng quá muộn để ngăn việc cấp phát bộ nhớ ban đầu. Đặt giới hạn ở gateway, HTTP server, socket framing, file size hoặc buffer ingress tương ứng.

## 5. Cấu hình filter theo pattern

Java cung cấp **ObjectInputFilter.Config.createFilter(...)** để tạo filter từ một chuỗi pattern.

Ví dụ:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
    "maxdepth=20;" +
    "maxrefs=1000;" +
    "maxbytes=1048576;" +
    "maxarray=4096;" +
    "com.example.transfer.TransferEnvelope;" +
    "!*"
);
~~~

Ý nghĩa:

- Các pattern **max...** đặt giới hạn tài nguyên.
- **com.example.transfer.TransferEnvelope** là class được cho phép.
- **!* ** trong ý nghĩa cú pháp pattern (viết liền là **!***, không có khoảng trắng) từ chối những class không khớp với các pattern trước đó.

Mẫu allowlist class phải được bổ sung theo **object graph thực tế**, không chỉ class gốc mà ứng dụng muốn nhận.

### 5.1. Thứ tự pattern quan trọng

Pattern được xét theo thứ tự để ra quyết định về class. Ví dụ:

~~~text
com.example.transfer.**;!*
~~~

cho phép các class trong package **com.example.transfer** và những package con phù hợp theo quy tắc pattern, rồi từ chối class còn lại.

Trong khi đó:

~~~text
!*;com.example.transfer.**
~~~

đặt quy tắc từ chối quá rộng trước, khiến class phía sau không còn cơ hội được cho phép.

Do đó, nên đặt các pattern cho phép có phạm vi cụ thể **trước** quy tắc từ chối còn lại.

### 5.2. Không mở toàn bộ hệ sinh thái chỉ vì một lỗi

Một allowlist quá rộng như:

~~~text
java.**;javax.**;com.example.**;!*
~~~

có thể chấp nhận nhiều kiểu không thuộc hợp đồng dữ liệu. Việc namespace bắt đầu bằng **java.** hoặc **com.example.** không làm class đó tự động an toàn.

Hãy bắt đầu từ các DTO/message class thực sự cần thiết, xác nhận các kiểu phụ trợ được deserialize và chỉ mở thêm khi có bằng chứng.

### 5.3. Module-qualified pattern

Pattern có thể bao gồm tên module để ràng buộc class với module tương ứng, theo cú pháp dạng:

~~~text
module.name/package.or.ClassPattern
~~~

Điều này có thể hữu ích khi module identity là một phần của mô hình triển khai. Nhưng cần xác nhận liệu class đang đến từ named module, automatic module hay unnamed module. Không sao chép tên module suy đoán từ tên Maven artifact.

### 5.4. Filter với array

Filter có thể nhận thông tin về class array và **arrayLength**. Các quy tắc class pattern có chi tiết về cách khớp kiểu phần tử; vẫn cần đặt **maxarray** để chặn kích thước không hợp lý.

Một stream hợp lệ có thể sử dụng array làm thành phần của object graph, kể cả khi DTO gốc không khai báo array trực tiếp mà dependency sử dụng collection nội bộ. Hãy dùng test và quan sát filter để quyết định class nào thực sự cần allow, không mở package toàn cục theo phỏng đoán.

## 6. Gắn filter trực tiếp với ObjectInputStream

Một ví dụ đọc payload native serialization từ buffer **đã được giới hạn kích thước ở ingress**:

~~~java
package com.example.transfer;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

public final class TransferReader {
    private static final ObjectInputFilter FILTER =
        ObjectInputFilter.Config.createFilter(
            "maxdepth=20;" +
            "maxrefs=1000;" +
            "maxbytes=1048576;" +
            "maxarray=4096;" +
            "com.example.transfer.TransferEnvelope;" +
            "!*"
        );

    public TransferEnvelope read(byte[] payload)
            throws IOException, ClassNotFoundException {

        // Giới hạn bên ngoài phải được áp dụng trước khi tạo payload.
        if (payload == null || payload.length > 1_048_576) {
            throw new InvalidObjectException("Invalid payload size");
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(payload))) {

            input.setObjectInputFilter(FILTER);

            Object value = input.readObject();

            if (!(value instanceof TransferEnvelope envelope)) {
                throw new InvalidObjectException("Unexpected root type");
            }

            validate(envelope);
            return envelope;
        }
    }

    private static void validate(TransferEnvelope value)
            throws InvalidObjectException {
        if (value.getRequestId() == null ||
                value.getRequestId().isBlank() ||
                value.getAmount() <= 0) {
            throw new InvalidObjectException("Invalid transfer data");
        }
    }
}
~~~

Ví dụ này dùng Java 17 trở lên cho **instanceof pattern matching**, đồng thời minh họa cả giới hạn ingress và filter trên stream.

**Các điểm cần phân biệt:**

1. Filter phải được đặt **trước** khi bắt đầu **readObject()**.
2. Policy này chỉ cho phép class **TransferEnvelope** cùng những trường hợp xử lý đặc biệt của serialization protocol; nếu object graph cần class khác, hãy xét thêm từng class dựa trên hợp đồng.
3. Kiểm tra root type sau **readObject()** vẫn cần thiết.
4. **validate(...)** mới kiểm tra tính hợp lệ của dữ liệu nghiệp vụ.
5. Với payload từ network, giới hạn kích thước phải được áp dụng khi nhận dữ liệu, **trước** khi cấp phát buffer lớn; kiểm tra **payload.length** chỉ là lớp phòng vệ bổ sung.
6. Không đưa thông tin nội bộ về class/stack trace vào lỗi công khai gửi ngược về một producer không tin cậy.

### 6.1. Vì sao không chỉ bắt Exception?

Một cách viết không nên dùng:

~~~java
try {
    return deserialize(payload);
} catch (Exception ignored) {
    return null;
}
~~~

Lối xử lý này đánh đồng payload không hợp lệ, thiếu class, lỗi bảo mật và lỗi lập trình. Nó cũng khiến consumer khó quyết định retry hay đưa message vào dead-letter queue.

Nên phân loại lỗi và xử lý ở boundary phù hợp; không tự động retry vô hạn một payload luôn bị filter từ chối.

### 6.2. readObject có thể trả null hoặc kiểu bất ngờ

Java serialization có thể biểu diễn giá trị null hoặc một object root khác với kỳ vọng. Filter không thay thế phép kiểm tra **instanceof** và invariant của DTO.

Nếu API nhận nhiều loại root message, xác định rõ union type hoặc envelope contract, thay vì cast trực tiếp với giả định mọi stream đều chứa cùng một class.

## 7. JVM-wide filter và chính sách theo ngữ cảnh

Ngoài per-stream filter, Java hỗ trợ cấu hình serialization filter ở mức rộng hơn.

### 7.1. Process-wide filter với jdk.serialFilter

Có thể cấu hình system property **jdk.serialFilter** khi khởi chạy JVM.

Ví dụ minh họa:

~~~bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=4096;com.example.transfer.TransferEnvelope;!*" -jar app.jar
~~~

Dấu ngoặc kép giữ toàn bộ chuỗi pattern là một JVM argument, tránh để shell diễn giải dấu chấm phẩy.

Các lưu ý:

- Filter áp dụng trong phạm vi JVM và có thể ảnh hưởng nhiều đường native deserialization khác nhau.
- Policy quá chặt có thể phá vỡ framework hoặc thư viện ngoài dự kiến.
- Global filter không được coi là thay thế kiểm tra business data.
- Môi trường test, batch, container và production cần được quản lý cấu hình riêng.
- Cách JVM kết hợp global/per-stream filter phụ thuộc serialization filter factory đang hoạt động.

Không dùng một policy process-wide rộng chỉ để làm cho mọi điểm đọc stream đều hoạt động. Nếu hệ thống có nhiều trust boundary, chính sách cần phân biệt theo use case.

### 7.2. ObjectInputFilter.Config.getSerialFilter

Java có thể truy xuất filter toàn cục đã cấu hình qua **ObjectInputFilter.Config.getSerialFilter()**.

Điều này hữu ích cho chẩn đoán, nhưng khi ứng dụng thiết lập per-stream filter, cần hiểu chính sách kết hợp. Không được giả định rằng việc gọi **setObjectInputFilter** sẽ luôn cộng dồn mọi giới hạn của filter trước đó theo cách mong muốn.

### 7.3. JEP 415 – Context-Specific Deserialization Filters

**JEP 415** đưa vào cơ chế filter factory theo ngữ cảnh (Java 17), cho phép chọn hoặc kết hợp bộ lọc khi tạo **ObjectInputStream** và khi thiết lập filter trên stream.

Một hệ thống có thể có:

~~~text
JVM process
   |
   +--> Endpoint A: message TransferEnvelope
   |        -> Cho phép transfer DTO + limits A
   |
   +--> Endpoint B: cache session
   |        -> Cho phép session DTO + limits B
   |
   +--> Job batch import
            -> Cho phép DTO lịch sử + limits C
~~~

Các đường nhập này có trust level và object graph khác nhau. Nếu dùng một filter duy nhất, nhóm có thể phải mở quá rộng để hỗ trợ tất cả đường nhập.

JEP 415 giúp áp chính sách theo context, nhưng factory cần được cài đặt phù hợp trước khi deserialization xảy ra. Lựa chọn filter từ ngữ cảnh không đáng tin cậy do chính payload khai báo có thể vô tình trao quyền cho input quyết định allowlist.

### 7.4. Tích hợp framework

Một số framework tự tạo **ObjectInputStream** và có thể cung cấp cấu hình filter riêng. Nếu thư viện không cho phép truyền filter trực tiếp:

- Kiểm tra tài liệu chính thức và phiên bản framework.
- Xác định có thể cấu hình per-stream policy hay filter factory không.
- Khảo sát có cần xử lý trước ở boundary của ứng dụng không.
- Nếu phải dùng JVM-wide filter, đo phạm vi ảnh hưởng của nó.
- Không viết wrapper mà âm thầm bỏ qua policy của framework.

Trong ứng dụng nhiều module, cần có một owner xác định chính sách filter tổng thể và nơi nó được cài đặt, tránh hai thư viện thiết lập các factory không tương thích.

## 8. serialVersionUID và tương thích class giữa hai phiên bản

**serialVersionUID** giúp runtime xác định tính tương thích của serial form giữa class đang có trên consumer và class descriptor trong serialized stream.

Ví dụ:

~~~java
public final class TransferEnvelope implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String requestId;
    private long amount;
}
~~~

Giữ cùng **serialVersionUID** có thể hỗ trợ một số thay đổi schema tương thích, nhưng **không bảo đảm** mọi stream cũ đọc được.

### 8.1. Thêm field

Phiên bản 1:

~~~java
public final class OrderMessage implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String orderId;
}
~~~

Phiên bản 2:

~~~java
public final class OrderMessage implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String orderId;
    private String region;
}
~~~

Với cơ chế default serialization và những điều kiện tương thích khác được đáp ứng, khi v2 đọc stream v1, **region** có thể nhận giá trị mặc định **null**. Ứng dụng v2 cần xử lý điều này hợp lệ:

~~~java
public String effectiveRegion() {
    return region == null ? "legacy" : region;
}
~~~

Không nên tự giả định **region** luôn khác null chỉ vì constructor của phiên bản 2 luôn gán nó. Deserialization mặc định không nhất thiết chạy constructor của Serializable class theo cách như tạo object thông thường.

### 8.2. Bỏ field

Một field có trong v1 nhưng không còn trong v2 thường không được khôi phục vào object v2 khi dùng default serialization. Tuy nhiên, việc bỏ field có thể gây lỗi nghiệp vụ nếu class mới hoặc các custom hooks vẫn phụ thuộc thông tin đó.

Với rolling deployment, cần cân nhắc chiều ngược lại: producer v2 phát stream cho consumer v1. Đừng chỉ test v1 → v2 mà bỏ qua v2 → v1.

### 8.3. Đổi tên class/package

Class descriptor của Java native serialization gắn với tên kiểu. Đổi package hoặc tên class thường không phải biến đổi schema có thể xử lý bằng cách giữ nguyên serialVersionUID.

Có thể cần migration tool có kiểm soát để đọc dữ liệu bằng class cũ rồi chuyển sang DTO mới, hoặc thiết kế wire format độc lập với class name. Tránh sửa tùy tiện **ObjectInputStream.resolveClass** để chấp nhận class từ untrusted input; cơ chế đó phải được thiết kế và kiểm chứng chặt chẽ.

### 8.4. Đổi loại field

Thay kiểu của field, quan hệ kế thừa hoặc cách custom serialization hoạt động có thể làm luồng cũ không tương thích. **serialVersionUID** giống nhau không xóa bỏ những thay đổi đó.

### 8.5. Không sửa serialVersionUID chỉ để “cho qua”

Nếu gặp:

~~~text
java.io.InvalidClassException:
local class incompatible:
stream classdesc serialVersionUID = ...
local class serialVersionUID = ...
~~~

đầu tiên phải xác định:

- Class cũ và mới khác nhau thế nào.
- Đây có phải thay đổi serial form được hỗ trợ không.
- Stream còn chứa kiểu nào khác không.
- Có custom **readObject/writeObject** hay **Externalizable** không.
- Dữ liệu cũ có chứa thông tin cần chuyển đổi không.
- Chính sách filter có chấp nhận graph đó không.

Đặt cùng một UID rồi chạy lại có thể khiến lỗi xuất hiện ở bước khác hoặc làm mất thông tin. Nó không phải giải pháp migration tổng quát.

## 9. Serialization hooks và các hành vi cần kiểm soát

Java serialization cho phép class tham gia vào quá trình đọc/ghi theo cách tùy chỉnh.

Các điểm đáng chú ý:

- **private writeObject(ObjectOutputStream):** tùy chỉnh cách ghi một Serializable class.
- **private readObject(ObjectInputStream):** tùy chỉnh cách đọc, phục hồi invariant.
- **readResolve():** có thể thay object được trả về sau khi khôi phục.
- **writeReplace():** có thể thay object trước khi ghi.
- **Externalizable:** class chịu trách nhiệm lớn hơn về định dạng và thao tác đọc/ghi.

Các hook này khiến việc chỉ xem tên field trong source chưa đủ để hiểu wire contract.

### 9.1. Kiểm tra invariant trong readObject

Ví dụ:

~~~java
package com.example.transfer;

import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.Serial;
import java.io.Serializable;

public final class TransferEnvelope implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private String requestId;
    private long amount;

    public TransferEnvelope(String requestId, long amount) {
        if (requestId == null || requestId.isBlank() || amount <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }
        this.requestId = requestId;
        this.amount = amount;
    }

    public String getRequestId() {
        return requestId;
    }

    public long getAmount() {
        return amount;
    }

    @Serial
    private void readObject(ObjectInputStream input)
            throws IOException, ClassNotFoundException {

        input.defaultReadObject();

        if (requestId == null || requestId.isBlank() || amount <= 0) {
            throw new InvalidObjectException("Invalid transfer");
        }
    }
}
~~~

Trong ví dụ này, constructor bảo vệ object được tạo bình thường, còn **readObject** kiểm tra lại invariant khi khôi phục từ serialized bytes.

Tuy vậy, business validation ở **readObject** không thay thế filter. Filter cần chạy khi object graph đang được dựng, còn invariant check có thể diễn ra sau khi nhiều class đã được xử lý.

### 9.2. Không tin cậy dữ liệu chỉ vì đã dùng constructor validate

Serializable class không được khôi phục bằng cách gọi constructor của chính nó như lệnh **new** thông thường. Nếu chỉ validate trong constructor, object đọc từ stream có thể vi phạm invariant.

Mô hình an toàn hơn:

~~~text
Ingress size limit
       |
       v
ObjectInputFilter
       |
       v
Deserialize graph
       |
       v
Class invariant checks / validation
       |
       v
Root type + business contract
       |
       v
Process / Persist
~~~

Các bước này bổ sung cho nhau. Không bước nào đơn lẻ là đủ.

### 9.3. readResolve và loại đối tượng cuối cùng

**readResolve** có thể thay object sau khi deserialize. Vì vậy, class xuất hiện trong stream và object cuối cùng được trả về có thể không hoàn toàn giống nhau. Đây là một lý do nữa để vừa lọc quá trình dựng graph, vừa xác minh root object sau **readObject()**.

## 10. Nhận dữ liệu từ ứng dụng phiên bản khác

Giả sử hệ thống nâng từ phiên bản A sang B, nhưng hai phiên bản tiếp tục chạy song song:

~~~text
Producer A -----+
                |
                +---- Queue / Cache ----> Consumer B
                |
Producer B -----+                      Consumer A
~~~

Cần đánh giá theo **cả hai chiều**, không chỉ kiểm tra consumer mới đọc payload cũ.

### 10.1. Ma trận tương thích

| Producer | Consumer | Cần kiểm tra |
|---|---|---|
| A | A | Baseline, dữ liệu hiện tại |
| A | B | New consumer đọc data từ old producer |
| B | A | Old consumer đọc data từ new producer |
| B | B | Target behavior |
| A hoặc B | Batch/replay version cũ | Payload lưu lâu, class và filter của batch |
| External producer | B | Contract, version, trust boundary |

Nếu B bổ sung class mới vào object graph, consumer A có thể không có class đó trong classpath. Nếu B bỏ class cũ khỏi allowlist, stream A có thể bị từ chối dù class A vẫn nằm trong codebase.

### 10.2. Filter và schema là hai phép kiểm tra độc lập

Ví dụ:

- V1 dùng **LegacyTransfer**.
- V2 dùng **TransferEnvelope**.
- V2 có mapping chuyển đổi LegacyTransfer sang TransferEnvelope.

Nếu v2 cần đọc stream v1, filter của v2 phải cho phép những class **cần thiết** để dựng **LegacyTransfer**, sau đó ứng dụng mới chuyển sang model chuẩn.

Không nên cho phép mọi class trong package legacy chỉ vì một stream cũ chứa LegacyTransfer. Hãy xác định cụ thể các kiểu có trong graph và hạn sử dụng dữ liệu cũ.

### 10.3. Strategy hỗ trợ hai loại message

Một luồng chuyển đổi có thể tổ chức:

~~~text
Serialized input
      |
      v
Bounded transport / authentication
      |
      v
ObjectInputFilter phù hợp version và trust source
      |
      v
readObject + root type check
      |
      +--> LegacyTransfer -> convert -> CanonicalTransfer
      |
      +--> TransferEnvelope -> convert -> CanonicalTransfer
      |
      v
Canonical validation
      |
      v
Business logic
~~~

Nếu chỉ có producer nội bộ, có thể chốt một khung thời gian hỗ trợ hai loại payload. Khi queue cũ đã được xử lý hết và không còn producer A, loại bỏ **LegacyTransfer** khỏi allowlist.

### 10.4. Không để version field tự quyết định quyền deserialize

Một payload có thể khai báo **version = 2**, nhưng đó là dữ liệu do chính sender cung cấp. Nếu sender không tin cậy, không nên dựa chỉ vào version field để chọn một allowlist rộng hơn.

Chọn chính sách dựa trên **context đã xác thực** như endpoint, producer identity, tenant boundary, topic/queue và contract được cấu hình ở server. Version có thể dùng để chọn decoder sau khi đã giới hạn trust boundary và định dạng, nhưng không phải bằng chứng nguồn gốc.

## 11. Cấu hình filter cho dữ liệu lịch sử

Trong giai đoạn migration, có thể cần lưu nhiều phiên bản policy theo từng luồng nhập.

| Loại dữ liệu | Chính sách gợi ý | Thời hạn |
|---|---|---|
| Message mới từ producer B | Chỉ cho DTO B, giới hạn hiện hành | Dài hạn |
| Message cũ từ queue A | Cho DTO A được liệt kê, giới hạn hẹp | Đến khi backlog cũ hết |
| Snapshot lưu trữ đã kiểm soát | Policy riêng theo schema của snapshot | Theo retention policy |
| File upload bên ngoài | Không cho native deserialization nếu tránh được | Dài hạn |
| Session cache chia sẻ giữa A và B | Chỉ cho class chung thật sự cần | Trong rollout |

### 11.1. Đo dữ liệu trước khi khóa policy

Không đo giới hạn chỉ từ một payload mẫu. Cần lấy các ví dụ hợp lệ đại diện:

- Message nhỏ và lớn.
- Object graph có collection hoặc array.
- Payload từ cả producer A và B.
- Payload sinh từ các nhánh nghiệp vụ hiếm.
- Cache/session tồn tại từ release trước.
- Dữ liệu batch hoặc retry được phát lại.
- Payload có field optional null hoặc absent.

Một allowlist thiếu class sẽ dẫn đến **InvalidClassException** khi deserialize; đó là lỗi cần được xem như tín hiệu cấu hình/hợp đồng, không phải lý do mở mọi class.

### 11.2. Lưu danh sách class theo lý do sử dụng

Ví dụ bảng inventory:

| Class | Producer | Consumer | Lý do allow | Ngày loại bỏ |
|---|---|---|---|---|
| com.example.transfer.TransferEnvelope | B | B | Message canonical | Không xác định |
| com.example.legacy.LegacyTransfer | A | B | Đọc backlog A | Sau khi A dừng |
| com.example.transfer.TransferDetail | B | B | Nested DTO đã công bố | Theo schema |
| Một class do thư viện nội bộ tạo | A/B | A/B | Chỉ nếu graph hợp lệ thực sự cần | Review định kỳ |

Không nên điền class mới vào allowlist chỉ dựa trên tên trong exception nếu class đó chưa được xác định là thuộc contract hợp lệ.

## 12. Khi serialized graph dùng collection và kiểu nội bộ

Một trong những lỗi migration dễ gặp là filter cho phép root DTO nhưng từ chối class phụ thuộc.

Ví dụ DTO chứa:

~~~java
private java.util.List<String> tags;
~~~

Stream có thể ghi một implementation cụ thể của **List**, không chỉ interface List. Cách producer xây dựng list có thể ảnh hưởng concrete class được serialize.

Ví dụ, một **ArrayList** và một collection được tạo từ các factory method của JDK có thể không cùng serial form hoặc implementation class. Khi nâng JDK và đổi cách tạo collection, filter có thể quan sát các class khác với baseline.

**Cách xử lý có kiểm soát:**

1. Xác định concrete serialized types từ payload hợp lệ đã lưu.
2. Ghi lại producer version và mã tạo collection.
3. Ưu tiên một wire DTO có shape đơn giản và ổn định.
4. Chỉ allow những type thực sự thuộc contract.
5. Đặt giới hạn graph và kích thước.
6. Kiểm tra cả producer A → consumer B và B → A.
7. Nếu cần hỗ trợ nhiều kiểu collection, mô tả và giới hạn rõ thay vì mở toàn bộ package JDK.

### 12.1. Không nhầm classpath dependency với serialized object graph

Một ứng dụng có hàng trăm dependency, nhưng stream chỉ chứa những object cụ thể. Allowlist không nên là bản sao toàn bộ classpath.

Ngược lại, một DTO nhỏ có thể transitively chứa object của library khác thông qua một field kiểu **Object** hoặc custom serialization hook. Inventory phải dựa trên actual wire contract, không chỉ sơ đồ class.

## 13. Các lỗi thường gặp và cách phân loại

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| **InvalidClassException: filter status: REJECTED** | Class hoặc giới hạn bị filter từ chối | Xác định class/metric, đối chiếu policy và payload |
| **InvalidClassException: local class incompatible** | serialVersionUID hoặc serial form không tương thích | So sánh class v1/v2, field và hooks |
| **ClassNotFoundException** | Consumer thiếu class được stream tham chiếu | Kiểm tra classpath và phương án migration DTO |
| **StreamCorruptedException** | Dữ liệu không tuân định dạng object stream | Kiểm tra format, framing, corruption |
| **OptionalDataException** | Dữ liệu primitive/object bị đọc không đúng thứ tự trong custom serialization | Kiểm tra readObject/writeObject |
| **EOFException** | Stream kết thúc sớm | Kiểm tra truncated payload, network framing |
| **InvalidObjectException** | Validation trong deserialization từ chối trạng thái object | Xem invariant, nguồn và schema |
| **ClassCastException** sau readObject | Root object không đúng kiểu consumer mong đợi | Xác nhận root type và version mapping |
| OutOfMemoryError hoặc thời gian deserialize bất thường | Graph/kích thước vượt khả năng xử lý | Ingress limit, maxdepth/maxrefs/maxbytes/maxarray |
| Message A được đọc nhưng business logic thất bại | Field thiếu/default không được xử lý | Mapping version, validation và invariant |
| Consumer A không đọc được payload B | Schema/class mới chưa được A hỗ trợ | Dual-write/compat DTO hoặc versioned protocol |

**InvalidClassException** không chỉ do filter. Phải đọc toàn bộ thông báo, cause và đối chiếu policy hoặc serialVersionUID trước khi sửa.

### 13.1. Lỗi filter là lỗi bảo mật hay tương thích?

Cùng một **REJECTED** có thể có ý nghĩa khác nhau:

- Một payload bất thường chứa class không nằm trong contract → filter hoạt động đúng.
- Một message hợp lệ từ producer A chứa DTO cũ chưa được cập nhật trong allowlist B → thiếu kế hoạch migration.
- Một stream bị từ chối do depth quá lớn nhưng đó là object graph hợp lệ theo contract → giới hạn cần được đánh giá.
- Một payload quá lớn hoặc class không được phép gửi đến endpoint → không nên mở policy để “sửa” lỗi.

Quyết định không dựa chỉ trên log “REJECTED”; cần thông tin về source, contract, graph và ngưỡng.

### 13.2. Thông tin lỗi đưa ra bên ngoài

Với untrusted sender, không nên trả về danh sách class được allow, internal classpath, JDK module details hoặc full stack trace.

Có thể phân biệt nội bộ các nhóm lỗi nhưng trả mã lỗi công khai ổn định, ví dụ:

~~~json
{
  "code": "INVALID_SERIALIZED_PAYLOAD",
  "message": "Unsupported or invalid input",
  "traceId": "request-123"
}
~~~

Các chi tiết kỹ thuật lưu trong log bảo mật được kiểm soát, theo chính sách dữ liệu của tổ chức.

## 14. Kiểm thử version matrix và negative cases

Không nên chỉ test một lần serialize rồi deserialize trong cùng process của phiên bản B. Kiểu test đó không phát hiện khác biệt giữa class version và allowlist lịch sử.

### 14.1. Tạo golden payloads từ phiên bản thật

Ở baseline A, lưu những serialized bytes được tạo bằng chính artifact A và dữ liệu đại diện. Khi cần, tạo thêm payload bằng B.

Mỗi fixture nên có:

- Producer JDK và application version.
- Artifact checksum.
- Classpath/dependency versions liên quan.
- Schema/message type.
- Độ dài payload.
- Nguồn và điều kiện tạo fixture.
- Kết quả mong đợi tại consumer.

Không tái tạo payload A bằng class B rồi gọi nó là “old version fixture”; như vậy không kiểm thử được wire form thực tế của A.

### 14.2. Test bốn tổ hợp chính

~~~text
               Consumer A       Consumer B
Producer A       A -> A           A -> B
Producer B       B -> A           B -> B
~~~

Với rolling upgrade, cả **A → B** lẫn **B → A** có thể cần hỗ trợ. Nếu thực tế chỉ có một chiều, phải ghi rõ dependency và lịch rollout khiến chiều còn lại không xảy ra.

### 14.3. Test class allowlist

Các test tối thiểu:

1. Root DTO hợp lệ → được phép.
2. Nested DTO hợp lệ → được phép.
3. Một class không thuộc contract → bị từ chối.
4. Một class cũ đã hết support → bị từ chối sau thời hạn.
5. Array/collection hợp lệ theo schema → được phép nếu thuộc graph hỗ trợ.
6. Một graph có kiểu không mong đợi ở field **Object** → bị từ chối.

**Lưu ý:** Khi thử dữ liệu đối kháng, chỉ dùng fixture an toàn do nhóm kiểm thử tạo ra trong môi trường cô lập. Không sử dụng gadget payload từ nguồn không tin cậy để “thử xem có chạy được không” trên production.

### 14.4. Test giới hạn tài nguyên

| Test | Điều cần xác nhận |
|---|---|
| maxdepth | Graph vượt ngưỡng bị từ chối |
| maxrefs | Graph có quá nhiều references bị từ chối |
| maxarray | Array dài bất thường bị từ chối |
| maxbytes | Stream quá giới hạn bị từ chối |
| Ingress size | Input quá lớn bị chặn trước khi cấp phát buffer lớn |
| Truncated stream | Failure được phân loại, không retry vô hạn |
| Valid maximum | Payload lớn nhất trong contract vẫn xử lý được |

Không nên cố gắng tạo object graph cực lớn để đo giới hạn trong cùng process phục vụ người dùng. Sử dụng dữ liệu synthetic có giới hạn và môi trường test phù hợp.

### 14.5. Test invariant nghiệp vụ

Object có class hợp lệ nhưng field sai vẫn phải thất bại.

Ví dụ:

- requestId null hoặc blank.
- amount âm hoặc bằng 0.
- Ngày hết hạn trước ngày tạo.
- Hai field mâu thuẫn.
- Enum/value không còn được hỗ trợ.
- Identifier trỏ đến tenant khác.
- Dữ liệu đã qua filter nhưng không thỏa business rule.

Test này nên chạy ở lớp validator/service hoặc trong deserialization hook khi phù hợp, đồng thời kiểm tra không có side effect trước khi validation thất bại.

## 15. Checklist rollout khi nâng phiên bản

### 15.1. Trước migration

- [ ] Đã tìm các điểm native deserialization và framework gián tiếp dùng ObjectInputStream.
- [ ] Đã chốt baseline/target JDK và application versions.
- [ ] Đã lưu golden payloads do producer A tạo.
- [ ] Đã xác định trust boundary và producer identity.
- [ ] Đã kiểm kê object graph/classes cần cho mỗi message type.
- [ ] Đã xác định rủi ro từ Java serialization hooks và dependency.
- [ ] Đã chọn chính sách allowlist và giới hạn tài nguyên.
- [ ] Đã có giới hạn payload ở tầng ingress.
- [ ] Đã xác định loại message legacy cần hỗ trợ trong thời gian chuyển đổi.

### 15.2. Trong migration

- [ ] Filter được gắn trước readObject.
- [ ] Không cho phép class ngoài hợp đồng chỉ vì một lỗi REJECTED.
- [ ] Đã kiểm tra A → B và B → A nếu hai phiên bản chạy song song.
- [ ] Đã xác minh serialVersionUID, field evolution và custom hooks.
- [ ] Root type và invariant nghiệp vụ được kiểm tra sau deserialization.
- [ ] Đã chạy test cho maxdepth/maxrefs/maxarray/maxbytes.
- [ ] Đã xác minh chính sách global/per-stream/context factory không xung đột.
- [ ] Có metric và log cho filter rejection, kèm hạn chế dữ liệu nhạy cảm.
- [ ] Có phương án rollback xử lý message do version mới ghi ra.
- [ ] Lỗi payload invalid không gây retry loop hoặc làm tắc queue.

### 15.3. Sau migration

- [ ] Đã xác nhận không còn producer A theo kế hoạch.
- [ ] Đã xác nhận backlog, cache và session legacy hết thời gian hỗ trợ.
- [ ] Đã loại class legacy không còn cần khỏi allowlist.
- [ ] Đã kiểm tra policy hiện tại với fixture mới.
- [ ] Đã lưu quyết định giữ hay loại dữ liệu lưu trữ cũ.
- [ ] Đã cập nhật tài liệu version/protocol và owner của filter.
- [ ] Đã đưa lần review allowlist tiếp theo vào lịch nâng cấp JDK/dependency.

### 15.4. Các chỉ số vận hành

Nên theo dõi:

- Số lần filter trả **REJECTED** theo endpoint/topic.
- Loại lỗi deserialize được phân loại.
- Kích thước payload và độ sâu tham chiếu quan sát được trong giới hạn bảo mật cho phép.
- Consumer lag, retry và dead-letter count.
- Tỉ lệ payload legacy còn nhận.
- Số lần parse thành công nhưng validation nghiệp vụ thất bại.
- Trạng thái producer A/B trong rolling deployment.

Không ghi raw serialized bytes hoặc thông tin nhạy cảm vào log để chẩn đoán mà không có chính sách bảo vệ phù hợp.

## 16. Khi nào nên thay Java native serialization?

Java native serialization gắn dữ liệu với Java class model và có rủi ro đặc thù khi dữ liệu không đáng tin cậy. Với network boundary hoặc trao đổi lâu dài giữa các ứng dụng/version độc lập, một wire format có schema rõ ràng thường dễ kiểm soát hơn.

Các lựa chọn có thể cân nhắc:

- **JSON:** dễ quan sát và version field rõ ràng, nhưng cần giới hạn parser và kiểm soát polymorphic deserialization.
- **Protocol Buffers:** schema được định nghĩa tường minh, hỗ trợ quy tắc tiến hóa field phù hợp.
- **Avro:** schema và cơ chế tương thích theo thiết kế.
- **CBOR hoặc định dạng nhị phân khác:** cần quy định schema, giới hạn và xử lý kiểu.
- **DTO với versioned envelope:** tách contract mạng khỏi tên class nội bộ.

**Đổi định dạng không tự động bảo đảm bảo mật.** Parser mới vẫn cần giới hạn kích thước, độ sâu, kiểu cho phép, xác thực và validation nghiệp vụ. Nếu dùng Jackson polymorphic typing, phải kiểm soát subtype và cấu hình, không mở class name tùy ý.

### 16.1. Lộ trình chuyển đổi định dạng

~~~text
Producer A: Java serialized bytes
                 |
                 v
       Legacy reader (filter chặt)
                 |
                 v
       Validate + canonical DTO
                 |
                 v
       Encode schema-based format
                 |
                 v
       New consumers B/C
~~~

Trong giai đoạn chuyển tiếp, có thể duy trì một adapter đọc legacy format trong môi trường được kiểm soát. Sau khi hết backlog và retention, loại bỏ adapter và các class legacy khỏi runtime path.

### 16.2. Không tự chuyển định dạng trong lúc đọc untrusted stream

Một adapter vẫn phải deserialize được legacy payload để chuyển đổi. Nếu bước đó sử dụng ObjectInputStream không có filter và giới hạn, việc chuyển sang JSON sau đó không loại bỏ nguy cơ ở điểm nhập.

Vì vậy, ưu tiên:

1. Ingress giới hạn dữ liệu.
2. Filter allowlist và resource limits.
3. Deserialization trong môi trường phù hợp.
4. Root type + business validation.
5. Chuyển sang DTO/schema mới.
6. Ghi ra format mới.

## 17. Mẫu ghi nhận quyết định bảo mật và tương thích

Để tránh mở allowlist tùy tiện trong migration, mỗi policy nên có decision record:

~~~text
Policy ID:
Owner:
Input endpoint / topic / file source:
Trust boundary:
Producer identities:
Producer versions:
Consumer versions:
JDK versions:
Serialized root types:
Permitted nested types:
Filter pattern / filter factory:
maxdepth:
maxrefs:
maxbytes:
maxarray:
Ingress size limit:
Business validation:
Supported serialVersionUID:
Custom serialization hooks:
Old-version fixtures:
Negative fixtures:
Observed filter rejections:
Temporary legacy allowlist:
Legacy removal condition:
Fallback / rollback:
Evidence location:
Approval:
Review date:
~~~

Ví dụ minh họa:

~~~text
Policy ID: SER-TRANSFER-02
Input: transfers-queue
Producer: Transfer Service A or B (authenticated internally)
Consumer: Settlement Service B
Root: TransferEnvelope
Temporary legacy type: LegacyTransfer
Allowed until: A stopped, queue drained, retention window elapsed
Filter: narrow allowlist + depth/refs/bytes/array limits
Validation: positive amount, nonblank requestId, tenant authorization
Evidence: golden A->B and B->B tests, filter negative tests
Owner: Integration team
~~~

Một policy được coi là hoàn tất khi có bằng chứng rằng dữ liệu hợp lệ được xử lý, dữ liệu không thuộc hợp đồng bị chặn và các đường rollout/rollback đều có phương án an toàn. Việc chỉ ghi một chuỗi filter mà chưa kiểm thử không đủ.

## 18. Những sai lầm phổ biến

### 18.1. Chỉ kiểm tra instanceof sau readObject

Object graph đã được khôi phục trước khi tới phép kiểm tra. Thêm filter trước khi đọc, rồi vẫn kiểm tra root type và business invariants sau khi đọc.

### 18.2. Allowlist quá rộng để giữ backward compatibility

Cho phép mọi class trong một package nội bộ hoặc mọi class JDK vì một payload cũ bị từ chối làm tăng bề mặt rủi ro. Giải pháp là kiểm kê graph và mở đúng các class thực sự cần.

### 18.3. Quên quy tắc từ chối mặc định

Pattern chỉ cho phép một vài class nhưng để phần còn lại **UNDECIDED** có thể không đạt mục tiêu allowlist. Cần chính sách reject các class chưa được cho phép và hiểu rõ cách filter được kết hợp.

### 18.4. Coi serialVersionUID giống như schema version

UID không mô tả tất cả thay đổi field, class hierarchy và custom hooks. Không thay UID để né lỗi nếu chưa kiểm chứng serial form.

### 18.5. Chỉ test A → B, bỏ B → A

Rolling deployment có thể khiến consumer A nhận message do producer B tạo. Nếu chiều này không được hỗ trợ, rollout phải ngăn luồng đó bằng chiến lược triển khai rõ ràng.

### 18.6. Đặt giới hạn sau khi đã đọc toàn bộ payload

Kiểm tra **payload.length** sau khi đọc body lớn vào RAM không ngăn được chi phí cấp phát. Giới hạn cần có từ tầng nhập.

### 18.7. Tin tưởng version field trong payload

Version do sender cung cấp không phải bằng chứng danh tính. Chọn trust policy từ context đã xác thực và cấu hình server.

### 18.8. Không kiểm tra collection implementation thay đổi

Dữ liệu v1/v2 có thể serialize các concrete collection class khác nhau. Điều tra object graph thật và giới hạn các class cần thiết; không mở toàn bộ **java.util**.

### 18.9. Chỉ log đầy đủ payload khi filter từ chối

Raw serialized bytes có thể chứa dữ liệu nhạy cảm hoặc quá lớn. Log request/trace ID, policy ID, loại lỗi và metric đã được giới hạn; lưu payload chỉ theo quy trình điều tra an toàn.

### 18.10. Nghĩ rằng đổi sang JSON tự giải quyết bảo mật

JSON parser cũng có thể gặp rủi ro khi dùng polymorphic typing, cấu trúc sâu hoặc payload quá lớn. Cần schema validation, type allowlist và giới hạn tài nguyên riêng.

## 19. Tài liệu chính thức để tra cứu

Khi áp dụng trên hệ thống thật, cần đối chiếu API và tài liệu theo JDK release mục tiêu:

- **JEP 290 – Filter Incoming Serialization Data:** https://openjdk.org/jeps/290
- **JEP 415 – Context-Specific Deserialization Filters:** https://openjdk.org/jeps/415
- **ObjectInputFilter API (Java 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- **ObjectInputStream API (Java 21):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- **Java Object Serialization Specification:** https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/index.html
- **Serializable API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- **InvalidClassException API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InvalidClassException.html

Đối với framework hoặc library thực hiện native serialization gián tiếp, cần đọc tài liệu phiên bản cụ thể để hiểu cách nó cài đặt per-stream filter, JVM-wide filter hoặc filter factory.

---

**Kết luận:** Khi nhận dữ liệu Java serialized từ ứng dụng phiên bản khác, không thể chỉ dựa vào **serialVersionUID** hoặc khả năng **readObject()** trả về đúng class. Cần thiết kế ranh giới tin cậy, giới hạn kích thước từ tầng ingress, áp **ObjectInputFilter** với class allowlist và resource limits, kiểm tra business invariants sau khi đọc, đồng thời thử các tổ hợp producer/consumer cũ và mới. Serialization filter là một lớp phòng vệ quan trọng, không phải công cụ biến mọi serialized object thành an toàn. Lộ trình dài hạn nên hướng tới hợp đồng dữ liệu rõ ràng, ít phụ thuộc vào chi tiết Java class và có khả năng tiến hóa schema được kiểm chứng.
