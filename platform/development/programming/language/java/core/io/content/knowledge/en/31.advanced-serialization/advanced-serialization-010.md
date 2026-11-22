# ObjectInputFilter trong Java 17: giới hạn lớp, độ sâu, số tham chiếu và độ dài mảng

## 1. Vấn đề: vì sao cần lọc dữ liệu khi deserialize?

`ObjectInputStream.readObject()` biến một chuỗi byte theo định dạng **Java Object Serialization** thành các instance, array và một **đồ thị đối tượng**. Nếu stream đến từ file, message broker, socket hoặc nguồn mà ứng dụng không kiểm soát hoàn toàn, việc đọc không chỉ là “parse dữ liệu”.

Một stream có thể chứa:

- Lớp không được ứng dụng mong muốn, bao gồm lớp có logic đặc biệt khi deserialize.
- Một object graph lồng nhau rất sâu, làm tăng nguy cơ cạn stack hoặc tài nguyên.
- Rất nhiều object/reference, gây tiêu tốn heap và công xử lý.
- Array có kích thước cực lớn, khiến ứng dụng cố cấp phát bộ nhớ khổng lồ.
- Dữ liệu được encode phức tạp hoặc có thể làm chương trình xử lý lâu.

`java.io.ObjectInputFilter` là một **hàng rào kiểm soát khi deserialization đang diễn ra**: nó có thể quyết định chấp nhận/từ chối lớp và giới hạn các chỉ số tài nguyên của object graph. Nó được đưa vào Java 9 và có thể dùng trên Java 17+.

Tuy nhiên, **filter không tự khiến Java native serialization trở nên an toàn tuyệt đối**. Nó không thay việc xác thực input, phân quyền, kiểm tra dữ liệu sau khi deserialize, giới hạn request size ở tầng giao thức, hay quản lý tài nguyên của ứng dụng.

### Bốn giới hạn cốt lõi

| Giới hạn | Ý nghĩa | Loại vấn đề giảm thiểu |
|---|---|---|
| **Class allowlist** | Chỉ chấp nhận những kiểu dữ liệu được phép | Deserialization của lớp ngoài dự kiến |
| **`maxdepth`** | Giới hạn độ sâu của quá trình duyệt graph | Graph quá sâu, tăng stack/chi phí |
| **`maxrefs`** | Giới hạn số lần tham chiếu được quan sát trong quá trình deserialize | Graph có quá nhiều references |
| **`maxarray`** | Giới hạn số phần tử của một array | Một array yêu cầu cấp phát quá lớn |
| **`maxbytes`** | Giới hạn số byte stream đã tiêu thụ tại các thời điểm kiểm tra | Input lớn/tốn tài nguyên |

Đề bài nhấn mạnh bốn trục class, depth, references, array length. `maxbytes` là giới hạn bổ sung rất nên có, **không phải** phép thay thế cho giới hạn kích thước payload ở tầng trước khi tạo ObjectInputStream.

## 2. Cách ObjectInputFilter được gọi

Interface có phương thức:

~~~java
ObjectInputFilter.Status checkInput(ObjectInputFilter.FilterInfo info);
~~~

Khi `ObjectInputStream` đang xử lý dữ liệu theo cơ chế Java serialization, nó tham vấn filter ở một số điểm để kiểm tra **lớp** và **thông số của object graph**. Đối tượng `FilterInfo` cung cấp thông tin hiện tại:

| `FilterInfo` | Dữ liệu trả về | Cần lưu ý |
|---|---|---|
| `serialClass()` | Lớp đang được xem xét; **có thể null** | Null không có nghĩa request chắc chắn hợp lệ |
| `arrayLength()` | Độ dài array; thường `-1` khi không có array | So sánh trực tiếp với ngưỡng maxarray |
| `depth()` | Độ sâu hiện tại của graph | Không phải inheritance depth của class |
| `references()` | Chỉ số reference của quá trình đọc | Không phải số object distinct hay ID nghiệp vụ |
| `streamBytes()` | Số byte stream đã được đọc tại điểm kiểm tra | Không phải độ dài file tổng, giới hạn xảy ra tại checkpoint |

Hình dung:

~~~text
ObjectInputStream.readObject()
        |
        v
   Đọc token / class / array / reference
        |
        v
   filter.checkInput(FilterInfo)
        |
        +--> ALLOWED   : bước kiểm tra này chấp nhận
        +--> REJECTED  : từ chối, dừng với lỗi deserialization
        +--> UNDECIDED : filter không quyết định tại bước này
        |
        v
   Nếu không bị từ chối, tiếp tục xử lý graph
~~~

### Filter có được gọi cho mọi byte và mọi String không?

**Không.** Theo hợp đồng serialization filtering, filter không phải parser được gọi sau *mỗi byte* hay cho mọi loại giá trị. Những String được encode trực tiếp trong stream và các giá trị primitive có ngoại lệ trong cơ chế gọi filter; tham chiếu đến object đã có handle có thể được kiểm tra theo kiểu khác. Tài liệu mô tả kiểm tra khi gặp các instance mới, array và một số references, nhưng **không được xem đây là phép soi xét toàn bộ semantic của dữ liệu**.

Hệ quả:

- Không dùng ObjectInputFilter để xác thực **nội dung** String, nội dung từng byte hay giá trị business field.
- Dùng bộ lọc lớp và resource limits, rồi **validate object sau khi đọc**.
- Giới hạn byte payload tại ingress (HTTP request body, file length, framed socket message) để chặn input quá lớn ngay từ đầu, không phụ thuộc hoàn toàn vào `streamBytes()`.

## 3. Ba kết quả `ALLOWED`, `REJECTED`, `UNDECIDED`

`checkInput(...)` phải trả về một trong các trạng thái:

~~~java
ObjectInputFilter.Status.ALLOWED
ObjectInputFilter.Status.REJECTED
ObjectInputFilter.Status.UNDECIDED
~~~

- **`ALLOWED`:** filter chấp nhận thông tin được kiểm tra trong lượt này. **Không phải** lời hứa object hoàn chỉnh có ngữ nghĩa hợp lệ hoặc an toàn.
- **`REJECTED`:** từ chối; `ObjectInputStream` sẽ báo lỗi deserialization, thông thường bằng `InvalidClassException`.
- **`UNDECIDED`:** filter không đưa ra quyết định ở lượt này. **Không được suy luận là “bị cấm mặc định”**.

Một vấn đề bảo mật thường gặp là filter chỉ chặn một vài lớp nguy hiểm và trả `UNDECIDED` cho tất cả lớp còn lại. Nếu không có tầng filter khác từ chối, các lớp không nằm trong denylist vẫn có thể được deserialize.

**Chính sách allowlist an toàn hơn:** kiểm tra resource limits trước; trả `ALLOWED` cho các lớp thực sự được phép; trả `REJECTED` cho lớp còn lại. Khi `serialClass()==null` vì không có thông tin class ở callback, vẫn áp dụng limit và có thể trả `UNDECIDED` cho riêng lượt kiểm tra đó.

Ví dụ về quyết định:

~~~text
Lớp Message được phép, length 4, depth 2    -> ALLOWED
Lớp Gadget không nằm trong allowlist         -> REJECTED
Lớp Message được phép, nhưng depth 100       -> REJECTED
Không có class ở callback, metrics hợp lệ     -> UNDECIDED
Không có class ở callback, maxrefs bị vượt    -> REJECTED
~~~

**Không để điều kiện allowlist ghi đè điều kiện limits.** Một lớp được phép nhưng chứa array cực lớn vẫn phải bị chặn.

## 4. Giới hạn lớp: allowlist thay vì chỉ blacklist

Khi một ứng dụng mong đợi DTO như `com.example.dto.Order`, không nên deserialize tùy ý các lớp tìm thấy trên classpath. Có hai cách triển khai:

1. **Pattern filter** dùng `ObjectInputFilter.Config.createFilter(...)`.
2. **Programmatic filter** dùng lambda/class triển khai `ObjectInputFilter`.

### Pattern filter

Ví dụ cấu hình minh họa:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=1000;maxarray=10000;"
              + "maxbytes=1048576;"
              + "com.example.dto.*;java.base/java.util.ArrayList;!*");
~~~

Giải thích:

- Các phần cách nhau bởi dấu chấm phẩy `;`.
- Các giới hạn như `maxdepth=10`, `maxrefs=1000`, `maxarray=10000`, `maxbytes=1048576` được áp dụng độc lập với thứ tự các pattern lớp.
- `com.example.dto.*` là pattern cho các class ở package đã nêu theo quy tắc pattern của JDK.
- `java.base/java.util.ArrayList` là pattern có module prefix để chỉ class cụ thể trong module Java.
- `!*` từ chối **các lớp không được những pattern được phép trước đó khớp**.

**Cảnh báo quan trọng:** Pattern filter kiểm tra **kiểu của object** chứ không tự giới hạn toàn bộ các trường hợp dữ liệu theo đúng schema của DTO. DTO có thể chứa collection implementation, nested class hoặc array cần được xem xét riêng. Không copy allowlist trên sang production nếu chưa kiểm tra cấu trúc thực tế và các class được filter gọi trong quá trình đọc.

### Pattern nào khớp class nào?

Theo Java serialization filter pattern:

| Dạng | Ý nghĩa thường dùng |
|---|---|
| `com.acme.dto.Order` | Class đầy đủ được chỉ định |
| `com.acme.dto.*` | Các class thuộc package nhất định |
| `com.acme.dto.**` | Bao gồm package và các subpackage |
| `!com.acme.Bad` | Từ chối class được khớp |
| `!*` | Từ chối các class còn lại không được cho phép |
| `java.base/java.util.ArrayList` | Class kèm module name |
| `maxdepth=20` | Giới hạn depth, **không** phải class pattern |

Với class array, quy tắc matching dùng **element type** theo đặc tả. Class-pattern không phải một danh sách chính xác mọi loại array trong chương trình; array length vẫn được kiểm tra bằng `maxarray`.

**Đừng nhầm "package.*" với wildcard cho bất kỳ package nào, và cũng đừng nhầm class pattern là lệnh kiểm tra giá trị field.** Cần đọc pattern matching rules ở Java 17, nhất là với module prefix, nested class và array.

### Không đưa những lớp cực rộng vào allowlist tùy tiện

Ví dụ `java.base/*` hay `java.**` (tùy cú pháp pattern) có thể quá rộng nếu ứng dụng chỉ cần một vài DTO. Càng mở rộng số class được deserialize, bề mặt tấn công càng lớn.

Thường nên tạo **DTO chuyên dụng ít trường**, field types cố định, không mang runtime service, thread, class loader hoặc callback object vào stream. Hạn chế thư viện serialization trực tiếp cho object domain phức tạp.

## 5. `maxdepth`: độ sâu của đồ thị đối tượng

`depth()` là độ sâu hiện tại trong quá trình giải mã tham chiếu, không phải:

- Độ sâu kế thừa `extends` của class.
- Chiều dài package name.
- Độ sâu JSON theo parser khác.
- Số lượng object duy nhất trong toàn stream.

Ví dụ:

~~~text
Root
  |
  v
Child
  |
  v
GrandChild
  |
  v
GreatGrandChild
  ...
~~~

Nếu graph bị xâu chuỗi quá sâu, quá trình deserialize có thể tiêu tốn stack và CPU. Giới hạn `maxdepth` giúp từ chối khi graph vượt ngưỡng tại các callback.

Ví dụ:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=100;maxarray=1000;maxbytes=65536");
~~~

Đoạn này chỉ cấu hình resource limits, **chưa có class allowlist**, nên không phải bộ lọc an toàn đầy đủ cho input không tin cậy.

**Cách chọn maxdepth:** đo và hiểu graph hợp lệ. Nếu DTO tối đa có ba tầng (Envelope → Payload → Item), không cần cho phép 10.000 tầng. Nhưng đừng đặt bằng mắt quá thấp khiến graph hợp lệ bị reject vì collection, wrapper hoặc nested references.

### Vòng tham chiếu và độ sâu

Java Object Serialization có object handles và back-reference để bảo toàn graph có vòng. Một vòng A → B → A không đồng nghĩa serializer sẽ đi sâu vô hạn: khi gặp lại A, nó dùng handle thay vì tạo mới A. Dù vậy, nhiều cấp lồng nhau trước khi gặp back-reference vẫn có thể khiến graph sâu. `maxdepth` là guardrail riêng.

## 6. `maxrefs`: giới hạn số tham chiếu được xử lý

Chỉ số `references()` phản ánh **các reference được quan sát trong quá trình deserialization** theo hợp đồng FilterInfo. Nó **không phải**:

- Số instance khác nhau sau khi đọc xong.
- Số field của class được định nghĩa.
- Số byte của stream.
- Object ID hoặc giá trị `System.identityHashCode()`.

Ví dụ một ArrayList có 100.000 phần tử trỏ cùng một object có thể tạo rất nhiều references trong stream dù chỉ có ít object khác nhau. Vì vậy cần giới hạn maxrefs độc lập với việc chỉ kiểm tra class.

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=12;maxrefs=5000;maxarray=10000;"
              + "maxbytes=2097152");
~~~

Nếu `references()` vượt `5000` tại một lần kiểm tra, filter sẽ từ chối. Chỉ số đo tại những callback, nên không được sử dụng như một promise về tổng memory footprint chính xác.

### Maxrefs và shared references

Java serialization bảo toàn việc nhiều field trỏ vào cùng object bằng stream handles. Nhưng maxrefs vẫn có ý nghĩa ngay cả khi các reference chia sẻ một object. **Không giảm nguy cơ chỉ bằng cách giới hạn số class**: một class DTO hợp lệ vẫn có thể chứa đồ thị tham chiếu khổng lồ.

## 7. `maxarray`: chặn cấp phát mảng quá lớn

Một payload chứa `byte[]`, `int[]` hoặc `Order[]` có thể yêu cầu bộ nhớ lớn trước khi chương trình kịp kiểm tra nội dung. Khi deserializing array, `FilterInfo.arrayLength()` cung cấp độ dài nếu biết, và filter có thể từ chối trước khi array được tạo.

Ví dụ:

~~~java
ObjectInputFilter f =
        ObjectInputFilter.Config.createFilter(
                "maxarray=10000;maxdepth=10;maxrefs=1000;"
              + "maxbytes=1048576");
~~~

`maxarray=10000` là **số phần tử**, không phải số byte:

- `byte[10000]` có 10.000 phần tử byte.
- `long[10000]` có 10.000 phần tử kiểu long, tiêu tốn vùng dữ liệu khác.
- `Object[10000]` có 10.000 tham chiếu, và các object mà nó trỏ tới còn tốn tài nguyên riêng.

Đừng lấy `maxarray=1000000` làm tương đương “1 MiB tối đa” trên mọi kiểu mảng. Dùng thêm `maxbytes`, `maxrefs` và hạn chế kích thước input thực tế.

### Khi không có mảng: `arrayLength() == -1`

Trong custom filter, giá trị âm thường có nghĩa **không có thông tin độ dài array ở callback**. Vì vậy:

~~~java
long length = info.arrayLength();
if (length >= 0 && length > MAX_ARRAY_LENGTH) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Không yêu cầu mọi class phải có `arrayLength() >= 0`: nếu không, ngay cả DTO hợp lệ không có array cũng bị từ chối.

## 8. `maxbytes`: giới hạn lượng byte đã đọc, không thay ingress limit

`maxbytes` dựa trên `FilterInfo.streamBytes()`. Nếu quá ngưỡng, filter từ chối tại điểm kiểm tra. Tuy nhiên, filter **không được gọi cho mọi byte**; một luồng chứa lượng dữ liệu đặc biệt hoặc thao tác đọc ngoài ObjectInputStream có thể đòi hỏi cách kiểm soát riêng.

Bảo vệ theo lớp:

~~~text
HTTP/Socket/File input
   -> tối đa 1 MiB payload trước deserialization
   -> ObjectInputStream với allowlist + graph limits
   -> DTO được deserialize
   -> validate field values, business invariants
   -> chỉ sau đó mới xử lý nghiệp vụ
~~~

Trên network, nếu input là byte stream liên tục, dùng **length-prefix có giới hạn** hoặc framing có quy tắc, tránh đọc không giới hạn đến EOF. Trên HTTP, áp dụng max request body size. Với file, kiểm tra `Files.size` có ích nhưng file còn có thể thay đổi giữa kiểm tra và sử dụng, nên cần bounded stream/protocol.

## 9. Chương trình Java 17+ hoàn chỉnh: một payload hợp lệ và một payload bị từ chối

Ví dụ sử dụng **custom ObjectInputFilter** để nhìn rõ việc kiểm tra:

- Cho phép duy nhất DTO `Message` và array `byte[]` dùng bởi DTO.
- Giới hạn `depth <= 8`, `references <= 64`, `arrayLength <= 8`, `streamBytes <= 65536`.
- Đọc payload 4 byte thành công.
- Từ chối payload chứa array 12 byte **trước khi chấp nhận object hoàn chỉnh**.
- Không dùng nguồn mạng hoặc file thật, vì bài tập cần kết quả xác định.

Lưu thành **`InputFilterDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class InputFilterDemo {

    private static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        final int id;
        final byte[] payload;

        Message(int id, byte[] payload) {
            this.id = id;
            this.payload = payload;
        }
    }

    private static ObjectInputFilter policy() {
        return info -> {
            // Luôn xét resource limits trước class allowlist.
            if (info.depth() > 8
                    || info.references() > 64
                    || info.streamBytes() > 65536
                    || info.arrayLength() > 8) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                // Khi chỉ có metric/reference, vẫn đã check limits.
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == Message.class || type == byte[].class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    private static byte[] encode(Message message) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(message);
        }
        return bytes.toByteArray();
    }

    private static void decode(String caseName, byte[] bytes)
            throws Exception {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(policy());

            try {
                Message restored = (Message) in.readObject();
                System.out.println(caseName + ": id=" + restored.id
                        + ", length=" + restored.payload.length);
            } catch (InvalidClassException rejected) {
                System.out.println(caseName + ": REJECTED");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        decode("allowed",
                encode(new Message(7, new byte[] {1, 2, 3, 4})));

        decode("too-large",
                encode(new Message(8, new byte[12])));
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac InputFilterDemo.java
java InputFilterDemo
~~~

**Stdout mong đợi trên Java 17 với cơ chế serialization mặc định:**

~~~text
allowed: id=7, length=4
too-large: REJECTED
~~~

Giải thích từng bước:

1. `Message` triển khai `Serializable`, chứa `int` và `byte[]`.
2. `encode(...)` tạo bytes theo native Java serialization; giai đoạn ghi không áp dụng input filter vì filter là cơ chế **đọc**.
3. `decode(...)` tạo `ObjectInputStream`, **cài filter trước lần đầu gọi `readObject()`**.
4. Với `Message(7, byte[4])`, lớp `Message` và `byte[]` được phép; depth/references/streamBytes đều trong ngưỡng, nên tạo được object và in kết quả.
5. Với `Message(8, byte[12])`, khi bộ lọc được hỏi về array có length 12, điều kiện `arrayLength() > 8` trả `REJECTED`. Deserialization báo `InvalidClassException`, và chương trình in `too-large: REJECTED`.
6. Không in thông tin exception message vì message cụ thể có thể khác theo implementation/JDK build.

Lưu ý: ví dụ đặt `readObject()` trong `try/catch InvalidClassException` để minh họa filtering. Ở production nên phân loại riêng stream hỏng, IO, schema mismatch và filter rejection, **không mặc định mọi InvalidClassException đều do filter**. Ngoài ra, custom filter này chỉ mô tả các loại object được mong đợi trong DTO nhỏ; một DTO phức tạp cần whitelist và kiểm thử thêm nested types/arrays.

### Kiểm tra ý nghĩa của `UNDECIDED` trong ví dụ

Khi `serialClass() == null`, custom filter trả `UNDECIDED` **sau khi** đã kiểm tra giới hạn tài nguyên. Đây là cách đúng trong ngữ cảnh đã chủ động thiết kế policy cho lớp được quan sát; tuy nhiên trong ứng dụng phức tạp, việc kết hợp filter với global filter factory có thể thay đổi cách `UNDECIDED` được xử lý. Đừng coi `UNDECIDED` tự động là reject.

## 10. Viết filter theo pattern cho các hệ thống thông thường

Khi schema lớp đã biết, pattern là lựa chọn tiện lợi và ít code hơn:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=64;maxarray=8;maxbytes=65536;"
              + "com.example.messages.Message;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object o = in.readObject();
}
~~~

Đoạn này là **mã minh họa**, `source` là `InputStream` do ứng dụng tạo và `com.example.messages.Message` là lớp DTO giả định. Với array, nested classes và filter factory, phải chạy test trên input hợp lệ/không hợp lệ thực tế trước khi triển khai. Nếu bất cứ loại nested type nào bị loại bởi `!*`, phải **bổ sung chính xác** vào allowlist thay vì xóa deny-by-default.

**Điểm dễ sai:** `createFilter(...)` với chỉ `maxdepth/maxrefs` vẫn không tự xây class allowlist. Việc thêm `!*` có ý nghĩa đóng chính sách đối với các class không khớp pattern; ngược lại, nếu không có rule reject chung, kết quả cho class không khớp có thể là `UNDECIDED`.

### Pattern kết hợp đúng các loại giới hạn

Gợi ý quy trình xây pattern:

1. Liệt kê các DTO root được phép, dựa trên schema thực tế.
2. Tạo thử stream hợp lệ có nested collections, arrays và nullable fields.
3. Bật allowlist chặt; xem loại class nào được filter hỏi trong test.
4. Cho phép thêm **chính xác** các class cần thiết; tránh wildcard quá rộng.
5. Đặt `maxdepth` và `maxrefs` theo thống kê graph hợp lệ cộng biên an toàn nhỏ.
6. Đặt `maxarray` theo kích thước array lớn nhất mà nghiệp vụ chấp nhận.
7. Đặt `maxbytes` và giới hạn bytes của toàn request ở ingress.
8. Thêm các negative tests: class lạ, deep nesting, massive array, excessive references.

## 11. Per-stream filter, global filter và filter factory

### 11.1. Per-stream: cấu hình trên từng ObjectInputStream

~~~java
try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object result = in.readObject();
}
~~~

Thích hợp khi các loại payload hoặc mức độ tin cậy khác nhau cần allowlist khác nhau. Nên cài filter **ngay sau khi tạo stream và trước khi deserialize object đầu tiên**.

Không tạo stream rồi bắt đầu `readObject()`, sau đó mới cài filter để hy vọng các object đã đọc được kiểm soát hồi tố.

### 11.2. Global filter: chính sách toàn JVM

Java hỗ trợ filter phạm vi JVM qua **system property** hoặc API, ví dụ:

~~~text
-Djdk.serialFilter=maxdepth=20;maxrefs=10000;maxarray=100000;maxbytes=10485760
~~~

Đây là cấu hình minh họa; việc escape dấu chấm phẩy phụ thuộc shell/launch command. Có thể cấu hình runtime-wide policy khi khởi động ứng dụng. `ObjectInputFilter.Config.setSerialFilter(...)` cũng tồn tại để thiết lập static JVM-wide filter, nhưng có quy tắc về thời điểm/khả năng đặt lại và quyền hạn; không tự gọi nhiều lần giữa vòng đời ứng dụng.

**Global filter là defense-in-depth**, không nên là lý do để từng luồng đọc từ nguồn không tin cậy bỏ qua class allowlist riêng.

### 11.3. Java 17: filter factory và cách kết hợp

Java 17 hỗ trợ cơ chế **context-specific deserialization filters** thông qua filter factory (JEP 415). API:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory(
        (current, requested) -> {
            // Quyết định cách kết hợp hoặc chọn policy.
            // Đây là ví dụ ý tưởng; cần hiểu rõ toàn bộ contract
            // và quyền sở hữu cấu hình toàn JVM.
            return requested != null ? requested : current;
        });
~~~

Đây là **đoạn minh họa về cấu hình**, không phải policy đủ an toàn để copy vào ứng dụng: nó có thể thay policy hiện tại bằng policy mới, khiến các hạn chế cũ không được áp dụng. **Không sử dụng factory trên để bảo đảm global + per-stream filters đều hoạt động.**

Điểm cần hiểu:

- Factory nhận filter hiện tại và filter được yêu cầu, quyết định filter kết quả cho luồng trong ngữ cảnh đó.
- Một factory cấu hình sai có thể vô tình bỏ global limits khi cài per-stream filter.
- Đặc tả cho phép cấu hình factory ở thời điểm sớm; đây là chính sách JVM-wide cần thiết kế/kiểm thử tập trung, không phải cài đặt tùy tiện sau khi server đã chạy.
- Nếu cần kết hợp allowlist và limits, hãy định nghĩa rõ phép **hợp hoặc giao** của policies, trong đó bất kỳ `REJECTED` nào từ giới hạn bắt buộc phải được tôn trọng.

**Khuyến nghị:** cho ứng dụng nhỏ, dùng filter riêng cài trước `readObject` với **cả class rules lẫn resource limits**. Với hệ thống nhiều module và thư viện, thiết kế factory chung, có integration tests chứng minh không đường nào bỏ qua policy tối thiểu.

## 12. Khi filter trả `REJECTED` thì chuyện gì xảy ra?

Khi một thông tin được filter từ chối, `ObjectInputStream` báo lỗi; thực tế phổ biến là `InvalidClassException` chứa thông điệp trạng thái filter. Đừng dựa vào string message cụ thể làm API ổn định.

Một mẫu xử lý:

~~~java
try {
    Object result = in.readObject();
    validateBusinessFields(result);
} catch (InvalidClassException e) {
    // Có thể do filter từ chối hoặc class incompatibility.
    // Ghi log an toàn, kết thúc request ở trạng thái lỗi.
} catch (StreamCorruptedException e) {
    // Binary stream không đúng định dạng.
} catch (ClassNotFoundException e) {
    // Không tìm được class mà stream yêu cầu.
} catch (IOException e) {
    // Lỗi I/O hoặc serialization protocol.
}
~~~

Đoạn trên là mã minh họa; `in` và `validateBusinessFields` được định nghĩa bên ngoài. Không tiếp tục deserialize phần còn lại của cùng input không tin cậy sau lỗi nghiêm trọng như thể stream vẫn còn alignment đúng; thường nên đóng stream/request và báo lỗi.

**Tránh log nguyên payload hoặc object graph không tin cậy.** Điều đó có thể gây lộ dữ liệu nhạy cảm hoặc kích hoạt `toString()` phức tạp sau khi object được đọc.

## 13. Những giới hạn ObjectInputFilter không giải quyết

Filter là cơ chế cần thiết khi còn sử dụng Java Object Serialization, nhưng không nên “thần thánh hóa”:

### Không xác thực business field

Object được phép có thể chứa `amount=-999999`, ngày không hợp lệ, enum không đúng state hoặc thông tin trùng lặp. Filter kiểm soát **kiểu và kích thước graph**, không đảm bảo business rules. Sau `readObject`, validate theo schema và nghiệp vụ.

### Không tự ngăn mọi nguy cơ gadget chain

Cho phép một số class không có nghĩa class đó luôn an toàn, và logic `readObject`, `readResolve`, `readExternal` hoặc các callback tùy biến của lớp có thể thực thi trong quá trình deserialize. Class allowlist giảm bề mặt nguy hiểm, nhưng việc cho phép class có side effects vẫn là rủi ro. Chỉ deserialize data class đã được kiểm toán.

### Không phải parser byte-level hoặc checksum

Filter không xác thực chữ ký số, không kiểm tra CRC, không chống input đã bị sửa theo protocol, không decrypt và không biết người gửi là ai. Cần TLS/authentication, message integrity và phân quyền phù hợp.

### Không thay timeout và giới hạn CPU/memory tổng

Mỗi callback chỉ cung cấp một số metrics. Xử lý tùy biến trong deserialization có thể tiêu tốn CPU; file/network request có thể chậm, bị đóng giữa chừng hoặc chứa nhiều byte chưa bị check bởi filter. Đặt deadline, bounded input, quota và monitoring ở tầng ngoài.

### Không làm Object Serialization phù hợp mọi hệ thống

Java native serialization gắn với kiểu Java, class descriptor và `serialVersionUID`. Trong public API hoặc giao tiếp cross-language, định dạng có schema rõ (JSON/CBOR/Protocol Buffers, v.v.) có thể thích hợp hơn; vẫn phải áp dụng validation/limits với bất kỳ parser nào.

## 14. Khác biệt giữa filter với `transient` và `serialVersionUID`

- `transient`: điều chỉnh **field nào** được default serialization ghi/đọc. Nó **không** ngăn mọi class lạ xuất hiện trong stream.
- `serialVersionUID`: hỗ trợ xác định khả năng tương thích phiên bản class; **không phải** class allowlist hoặc chữ ký xác thực.
- `readObject(...)` tùy biến: có thể quyết định dữ liệu/logic deserialization; nếu không kiểm soát, một lớp đã được phép vẫn có thể tạo object hoặc tác dụng phụ ngoài ý muốn.
- `ObjectInputFilter`: quyết định class/resource constraints tại các checkpoint của quá trình đọc.

Kết hợp cả bốn chỉ khi có mục tiêu tương ứng; không xem công cụ nào thay thế các công cụ còn lại.

## 15. Thiết kế custom filter đúng với `FilterInfo`

Với callback:

~~~java
ObjectInputFilter filter = info -> {
    if (info.depth() > 10
            || info.references() > 1000
            || info.streamBytes() > 1_048_576
            || info.arrayLength() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == MyAllowedDto.class || type == byte[].class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
~~~

Đoạn này là mã minh họa vì `MyAllowedDto` do ứng dụng định nghĩa. Cần lưu ý:

1. **Limits trước allowlist**: class được phép vẫn không được dùng tài nguyên vô hạn.
2. **Class null** không làm bộ lọc bỏ qua kiểm tra depth/references/bytes/array.
3. **Array length = -1** khi không có độ dài array: so sánh `> ngưỡng dương` không vô tình reject.
4. **Không gọi phương thức phức tạp trong filter**: filter chạy ở đường deserialize, nên phải ngắn và deterministic.
5. **Không truy cập network/database trong checkInput**: dễ tạo deadlock, chậm hoặc mở bề mặt lỗi.
6. **Không trả UNDECIDED cho unknown class** nếu muốn class allowlist đóng.
7. **Không chặn cả array có type được phép** do quên `byte[].class` hoặc các array hợp lệ; viết test thật.
8. **Không coi ALLOWED là validate xong**; sau đọc vẫn kiểm tra object invariants.

## 16. Tối ưu chính sách giới hạn cho workload thật

Không có một bộ số chuẩn cho mọi ứng dụng. Quy trình thiết kế:

- Đo chiều sâu và số references của một **payload hợp lệ lớn nhất**.
- Liệt kê array types và kích thước kỳ vọng.
- Xác định giới hạn **kích thước request ở ingress** thấp hơn mức khiến heap/CPU quá tải.
- Chọn ngưỡng với khoảng dư nhỏ phù hợp thay vì vô hạn.
- Viết test cho cả trường hợp hợp lệ ngay sát ngưỡng và trường hợp vượt ngưỡng.
- Kiểm tra đầu vào có vòng tham chiếu, nhiều shared handles và nested arrays.
- Chú ý message có String lớn: filter không đo nội dung string như validator; maxbytes/checkpoint và bounded input quan trọng.
- Giám sát tỷ lệ filter rejection, nhưng không log payload không tin cậy hoặc dữ liệu nhạy cảm.

Ví dụ policy mẫu cho một DTO nhỏ có payload array tối đa 4 KiB:

| Quy tắc | Giá trị ví dụ | Vì sao |
|---|---:|---|
| Class allowlist | `OrderMessage`, các nested types chính xác | Giảm class ngoài dự kiến |
| `maxdepth` | 12 | Đủ một graph không quá sâu |
| `maxrefs` | 2000 | Giới hạn tham chiếu |
| `maxarray` | 4096 | Mảng tối đa 4096 phần tử |
| `maxbytes` | 65536 | Cản stream lớn tại các callback |
| Ingress cap | 65536 bytes | Giới hạn kích thước payload trước deserialize |

Các con số chỉ là **ví dụ cấu hình**, không phải định mức an toàn tổng quát. Nếu `OrderMessage` có String cực lớn hoặc nested map tạo nhiều class, cần điều chỉnh schema và chính sách.

## 17. Test bảo mật: phải có cả positive lẫn negative cases

| Test | Dữ liệu thử | Kỳ vọng |
|---|---|---|
| Allowed class | DTO nằm trong allowlist, kích thước bình thường | Đọc thành công, validate business |
| Unknown class | Một class Serializable khác | Bị `REJECTED` |
| Array vượt giới hạn | `byte[limit+1]` | Bị `REJECTED` |
| Nested graph sâu | Chain dài vượt maxdepth | Bị `REJECTED` |
| Excessive references | Graph có nhiều reference | Bị `REJECTED` |
| Too many bytes | Stream vượt maxbytes và kích hoạt checkpoint | Bị `REJECTED` hoặc ingress cap chặn sớm |
| Corrupted stream | Dữ liệu hỏng/mất bytes | Báo lỗi, không tiếp tục deserialize mù |
| Compatible update | Phiên bản DTO mong đợi | Đọc/validate theo policy |
| Class version incompatible | UID/schema không tương thích | Xử lý `InvalidClassException` |
| Null class info | Callback metrics-only | Vẫn kiểm limits, không suy ra unknown được allow |
| Global factory | Cài per-stream filter lên policy global | Không làm mất limits toàn JVM |

Ngoài unit tests, cần integration tests đúng JDK/runtime và thư viện serializer thực tế. Nếu có custom `readObject`/`readResolve`, test cả những nhánh đó.

## 18. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ dùng denylist class đã biết | Class nguy hiểm khác vẫn có thể đi qua | Dùng allowlist chặt |
| Không thêm `!*` ở cuối pattern mong deny-by-default | Class không khớp có thể `UNDECIDED` | Đặt rule reject rõ ràng |
| Cho phép class quá rộng | Tăng bề mặt gadget/deserialization | Cho phép đúng DTO và nested types |
| Không kiểm `maxdepth` | Graph lồng sâu | Đặt depth cap |
| Không kiểm `maxrefs` | Rất nhiều references | Đặt reference cap |
| Dùng `maxarray` như số byte | `long[]` hoặc object[] quá lớn | Hiểu đây là số phần tử |
| Chỉ đặt `maxbytes` mà không giới hạn input | Filter không phải byte-level hard cap | Bounded stream/request length |
| Trả `ALLOWED` trước khi kiểm limits | Class hợp lệ có thể tiêu thụ quá mức | Kiểm limits đầu tiên |
| Trả `UNDECIDED` cho mọi lớp lạ và cho rằng sẽ reject | Một filter khác có thể không chặn | Trả `REJECTED` cho unknown class |
| Cài filter sau khi đã đọc object | Không bảo vệ dữ liệu đã xử lý | Set trước `readObject` đầu tiên |
| Cho rằng `serialClass()!=null` trong mọi callback | NullPointerException hoặc bỏ qua metrics | Xử lý null đúng |
| Global/per-stream filter thay thế nhau ngoài ý muốn | Bỏ mất security limits | Thiết kế/test filter factory |
| Cho rằng filter validate String/content | Nhận giá trị nghiệp vụ sai | Validation ở tầng DTO |
| Catch `InvalidClassException` rồi cứ đọc tiếp stream | State có thể không còn đáng tin | Đóng stream/request, báo lỗi |
| Deserialization từ Internet mặc định an toàn nhờ filter | Vẫn nhiều bề mặt tấn công | Ưu tiên format an toàn hơn và defense-in-depth |

## 19. Câu hỏi tự kiểm tra

1. `ObjectInputFilter` được dùng khi serialize hay deserialize? **Khi deserialize** qua ObjectInputStream.
2. `UNDECIDED` có nghĩa chắc chắn bị từ chối không? **Không.** Đây là trạng thái filter chưa quyết định.
3. Ưu tiên kiểm tra class allowlist hay resource limits trong custom filter? **Kiểm resource limits trước**.
4. `serialClass() == null` có được bỏ toàn bộ kiểm tra không? **Không; vẫn kiểm depth, references, arrayLength và streamBytes**.
5. `maxdepth` giới hạn chiều sâu inheritance class không? **Không; nó giới hạn độ sâu object graph khi đọc**.
6. `maxrefs` có phải số instance duy nhất? **Không, là metric reference trong quá trình deserialize**.
7. `maxarray=500` nghĩa là tối đa 500 bytes cho mọi array? **Không, tối đa 500 phần tử array**.
8. Nếu `arrayLength() == -1`, điều gì cần làm? **Đừng xem đó là array có độ dài âm lỗi; đây là giá trị không có thông tin độ dài**.
9. `maxbytes` có thay thế được ingress size cap không? **Không.**
10. Trong pattern, `!*` dùng để làm gì? **Từ chối những class không khớp allowlist trước đó**.
11. `setObjectInputFilter` nên được gọi lúc nào? **Trước khi bắt đầu `readObject()`**.
12. Khi filter từ chối lớp, thường gặp exception gì? **`InvalidClassException`**.
13. `InvalidClassException` có phải luôn do filter không? **Không; class incompatibility cũng có thể gây ra**.
14. Global filter và per-stream filter luôn tự động cộng dồn limits không? **Không được suy đoán; phải hiểu và test filter factory**.
15. Lớp được `ALLOWED` có đồng nghĩa field values đã hợp lệ? **Không**, cần validation sau khi deserialize.
16. ObjectInputFilter có tự chống mọi gadget chain không? **Không; giảm bề mặt, không phải sandbox**.
17. Có nên dùng Java native serialization cho API nhận input công khai không? **Thường nên ưu tiên định dạng/schema khác**, nếu buộc dùng thì thực hiện defense-in-depth.

## 20. Tài liệu chính thức

- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): FilterInfo, Status, class/resource limits và filter composition.
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): `setObjectInputFilter`, `readObject`, lỗi input.
- [Java SE 17 — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): `createFilter`, global filter và filter factory.
- [Java SE 17 — Serialization Filtering Guide](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): pattern-based filter, resource limits, cách kết hợp filters.
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): cơ sở kỹ thuật, semantics lọc class và graph.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): chính sách filter theo context và factory trong Java 17.
