# Filter theo stream, cấu hình JVM và phụ thuộc phiên bản JDK trong Java Serialization

Khi dùng `ObjectInputStream.readObject()`, ứng dụng đưa một luồng byte vào cơ chế **giải tuần tự hóa Java (deserialization)**. Một stream độc hại có thể yêu cầu khôi phục kiểu lớp không mong muốn hoặc đồ thị đối tượng rất lớn, lồng sâu, tiêu tốn tài nguyên. **`ObjectInputFilter`** (serialization filter) cho phép ứng dụng kiểm tra tên lớp và một số chỉ số của đồ thị trong quá trình đọc, rồi **`ALLOWED`**, **`REJECTED`** hoặc **`UNDECIDED`**.

Có ba tầng cấu hình dễ bị nhầm:

1. **Stream-specific filter:** thiết lập trên **một** `ObjectInputStream`, ví dụ `input.setObjectInputFilter(filter)`.
2. **JVM-wide/static filter:** cấu hình qua `-Djdk.serialFilter=...` hoặc `ObjectInputFilter.Config.setSerialFilter(...)`, áp dụng ở cấp JVM theo cơ chế chọn filter.
3. **JVM-wide filter factory (từ JDK 17):** chọn hoặc kết hợp filter cho **từng stream** khi `ObjectInputStream` được tạo và khi một filter riêng được yêu cầu; cấu hình qua `jdk.serialFilterFactory` hoặc `setSerialFilterFactory`.

Không nên nghĩ rằng chỉ cần bật một filter bất kỳ là việc deserialize dữ liệu không tin cậy đã an toàn. Bộ lọc là **lớp bảo vệ bổ sung**. Lựa chọn an toàn hơn vẫn là không dùng Java native deserialization cho dữ liệu không tin cậy, mà sử dụng định dạng dữ liệu được kiểm tra schema, xác thực và giới hạn tài nguyên.

## 1. API cốt lõi và mối nguy cần giới hạn

Các lớp liên quan thuộc package `java.io`:

| API | Vai trò |
| --- | --- |
| `ObjectInputStream` | Đọc đối tượng từ Java serialization stream |
| `ObjectInputFilter` | Giao diện đánh giá các đối tượng/lớp và chỉ số đồ thị khi deserialize |
| `ObjectInputFilter.FilterInfo` | Ngữ cảnh hiện tại: `serialClass()`, `arrayLength()`, `depth()`, `references()`, `streamBytes()` |
| `ObjectInputFilter.Status` | Ba quyết định `ALLOWED`, `REJECTED`, `UNDECIDED` |
| `ObjectInputFilter.Config` | Tạo filter từ chuỗi pattern, đọc/đặt filter tĩnh và filter factory cấp JVM |
| `ObjectInputStream.setObjectInputFilter(...)` | Yêu cầu áp dụng filter cụ thể cho một stream |
| `ObjectInputStream.getObjectInputFilter()` | Kiểm tra filter đang áp dụng trên stream theo cấu hình thực tế |

Filter có thể kiểm soát **những loại class được dựng và những chỉ số tài nguyên**. Nó không phải trình phân tích giá trị nghiệp vụ; nó cũng không xác minh danh tính người gửi, không bảo đảm một object đã được tạo có trạng thái hợp lệ và không biến dữ liệu serialization thành sandbox an toàn.

Một payload có thể nguy hiểm vì lớp được phép có `readObject()`/`readResolve()` tùy biến, vì đồ thị quá sâu, vì chuỗi tham chiếu nhiều hoặc vì dữ liệu không hợp lệ. Do đó cần cả **allowlist lớp theo use case**, **giới hạn đồ thị**, **giới hạn bytes/CPU** và **kiểm tra dữ liệu sau khi đọc**.

## 2. Vòng đời một stream với filter

Quy trình phổ biến:

```text
Nguồn bytes đáng tin cậy hoặc đã kiểm soát
          |
          v
new ObjectInputStream(inputBytes)
          |  (JVM-wide filter factory chọn filter ban đầu)
          v
setObjectInputFilter(streamPolicy)
          |  (filter factory quyết định filter đang hiệu lực)
          v
readObject()
          |  filter kiểm tra class / array / depth / refs / streamBytes
          +--- REJECTED  --> thao tác đọc thất bại
          +--- ALLOWED   --> tiếp tục theo quy trình giải tuần tự hóa
          +--- UNDECIDED --> không xác nhận cho phép; xử lý theo chính sách kết hợp
          v
Xác minh kiểu, tính hợp lệ nghiệp vụ, đóng stream
```

Ở JDK 17, `ObjectInputStream` được tạo với một filter ban đầu thông qua factory. Khi gọi `setObjectInputFilter()`, **factory lại quyết định filter cuối cùng** dựa trên filter hiện tại và filter mới được yêu cầu. Vì vậy việc gọi phương thức này không nên được hiểu là "chắc chắn chỉ còn filter vừa truyền" hoặc "chắc chắn được merge với global" trong mọi ứng dụng: **hành vi phụ thuộc factory thực tế**.

Các điểm giới hạn quan trọng:

- Filter có thể được gọi **không hoặc nhiều lần**, tùy loại nội dung stream và bước xử lý. Một số giá trị được mã hóa đặc biệt, chẳng hạn `String` và primitive ở những dạng nhất định, **không nhất thiết kích hoạt callback kiểm tra class cho từng giá trị**.
- `FilterInfo.serialClass()` có thể `null` khi lần kiểm tra chỉ xét giới hạn đồ thị/tài nguyên, vì vậy không dereference tùy tiện.
- Khi gặp array, filter có thể được gọi với class của array và có thể lấy `arrayLength()`. Pattern filter so khớp **kiểu phần tử** cho array, không đơn giản so tên `[Ljava.lang.String;`.
- `arrayLength()` có thể là `-1` khi không phải kiểm tra một array; không so nó với kích thước thật của mọi loại collection.
- Filter đánh giá **trước hoặc trong quá trình tạo graph**; nó không đảm bảo từ chối một object trước khi bất kỳ tác dụng phụ nào của thao tác deserialization khác xảy ra. Không dùng nó thay kiểm tra nguồn dữ liệu.

## 3. Bộ lọc theo stream: tách chính sách cho từng luồng

Một dịch vụ có thể có nhiều đầu vào. Ví dụ một stream chỉ nên nhận `InvoiceDTO`, stream khác nhận `CacheSnapshot`. Dùng một danh sách lớp cho tất cả dễ khiến quyền giải tuần tự hóa trở nên rộng hơn nhu cầu.

Với JDK 9+ và JDK 17, bạn có thể tạo filter bằng pattern rồi yêu cầu gắn vào `ObjectInputStream`:

```java
// Minh họa trong một phương thức đọc, trước readObject().
ObjectInputFilter policy = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=200;maxbytes=1048576;maxarray=10000;" +
        "com.example.dto.**;java.base/java.util.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(policy);
    Object value = in.readObject();
    // Kiểm tra kiểu cụ thể và validate cấu trúc dữ liệu.
}
```

Đây là **đoạn minh họa**, chưa định nghĩa `source` và những lớp `com.example.dto`; không phải chương trình biên dịch độc lập. Nếu ứng dụng dùng `List`, `Map`, array hoặc class nội bộ khác, phải kiểm thử chính sách trên **toàn bộ object graph hợp lệ**, không mặc định pattern trên luôn phù hợp.

**Đặt filter trước lần đọc đầu tiên** là thói quen cần thiết. Với API chuẩn, không nên chờ đọc một phần object rồi mới quyết định cài filter. Nếu `ObjectInputStream` do framework/library sở hữu, việc gọi `setObjectInputFilter()` có thể không được phép hoặc đã quá muộn; cần phối hợp cấu hình ngay ở nơi tạo stream.

### Khi nào nên dùng custom filter thay vì pattern?

Khi cần kiểm tra logic ngoài tên class, viết lambda theo `ObjectInputFilter.FilterInfo`:

```java
// Minh họa trong chương trình đã import java.io.ObjectInputFilter.
ObjectInputFilter policy = info -> {
    if (info.depth() > 12
            || info.references() > 1000
            || info.streamBytes() > 1_048_576
            || info.arrayLength() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }
    if (type == ExampleDTO.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};
```

Đây là **minh họa**, `ExampleDTO` là class ứng dụng giả định, không phải file độc lập. Bộ lọc này chỉ cho phép `ExampleDTO` ở các lần callback có class cụ thể: nếu `ExampleDTO` chứa field kiểu class/array khác cần deserialize, filter sẽ từ chối chúng. Với hệ thống thật, hãy xét toàn bộ kiểu hợp lệ và không bỏ quên primitive array, collection, proxy, nested class hay các object phụ thuộc.

## 4. Ba kết quả ALLOWED, REJECTED, UNDECIDED

| Kết quả | Ý nghĩa |
| --- | --- |
| `ALLOWED` | Kiểm tra hiện tại vượt qua chính sách filter này; tiếp tục deserialization |
| `REJECTED` | Từ chối; deserialization sẽ thất bại, thường thể hiện qua `InvalidClassException` |
| `UNDECIDED` | Filter không đưa ra quyết định cho lần kiểm tra này; **không phải ALLOWED theo nghĩa allowlist** |

Với `ObjectInputFilter.Config.createFilter(pattern)`, hệ thống xét **giới hạn tài nguyên trước**, rồi xét pattern class **từ trái sang phải**. Pattern đầu tiên khớp quyết định ALLOWED/REJECTED; nếu không khớp và không vượt ngưỡng, kết quả là UNDECIDED.

Trong trường hợp filter hiệu lực trả UNDECIDED cho một class và không có thành phần khác từ chối, quá trình đọc có thể tiếp tục. Bởi vậy **chỉ ghi tên các class được phép nhưng không thêm quy tắc từ chối phần còn lại không nhất thiết tạo ra allowlist "deny by default"**.

Một pattern phổ biến có dấu `!*` cuối chuỗi:

```text
com.example.api.**;java.base/java.util.*;!*
```

Nghĩa là chấp nhận các class khớp hai pattern đầu, rồi từ chối những class còn lại khi có kiểm tra class. Tuy nhiên không được mở cả package lớn nếu ứng dụng chỉ cần vài DTO cụ thể; mọi class thuộc package/module được cho phép đều phải nằm trong mô hình tin cậy.

Trong JDK 17 có các công cụ `ObjectInputFilter.merge(...)` để kết hợp filter và `ObjectInputFilter.rejectUndecidedClass(...)` để xử lý kết quả chưa quyết định trên các lần kiểm tra class. Cách dùng phải được đánh giá theo từng hệ thống; không nên tự suy diễn rằng “merge” luôn bằng nối các pattern hay luôn giống phép giao của hai allowlist.

## 5. Cấu hình JVM-wide bằng jdk.serialFilter

Nếu ứng dụng hoặc thư viện tạo `ObjectInputStream` tại nhiều vị trí khó sửa, bạn có thể cấu hình filter tĩnh **ngay lúc khởi động JVM**:

```bash
java '-Djdk.serialFilter=maxdepth=12;maxrefs=5000;maxbytes=10485760;maxarray=100000;com.example.dto.**;!*' com.example.Main
```

Đây là lệnh **minh họa**: class `com.example.Main` và package DTO cần có thật trong ứng dụng. Trên hệ shell cụ thể, cách quote đối số có thể khác; hãy bảo đảm **toàn bộ chuỗi pattern có dấu `;` được truyền thành một JVM option duy nhất**, vì dấu chấm phẩy trong shell có thể là ký hiệu phân tách câu lệnh.

Những ngưỡng cơ bản:

| Pattern | Ý nghĩa |
| --- | --- |
| `maxdepth=12` | Giới hạn độ sâu đồ thị khi deserialize |
| `maxrefs=5000` | Giới hạn số tham chiếu được theo dõi |
| `maxbytes=10485760` | Giới hạn số byte của serialization stream được theo dõi |
| `maxarray=100000` | Giới hạn độ dài một array, **không phải kích thước mọi collection** |
| `com.example.dto.**` | Cho phép class trong package và subpackage phù hợp |
| `java.base/java.util.*` | Cho phép class trực tiếp trong package `java.util` của module `java.base` |
| `!*` | Từ chối class còn lại khi được filter kiểm tra |

Filter tĩnh được cấu hình thông qua **system property `jdk.serialFilter`**; khi không có, JVM có thể dùng **security property cùng tên** từ cấu hình security. System property được ưu tiên so với security property theo thứ tự khởi tạo của `ObjectInputFilter.Config`.

Có thể thiết lập bằng API **nếu filter tĩnh chưa được đặt/cấu hình**:

```java
// Minh họa cho bootstrap của ứng dụng trên Java 17.
ObjectInputFilter global = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=5000;maxbytes=10485760;maxarray=100000");
ObjectInputFilter.Config.setSerialFilter(global);
```

`setSerialFilter()` là cấu hình **một lần ở cấp JVM**, không phải lời gọi để bật/tắt theo request. Nếu filter đã được đặt, có thể nhận `IllegalStateException`; nếu một Security Manager/permissions của phiên bản đang chạy chặn thao tác, có thể nhận ngoại lệ quyền truy cập.

**Điều quan trọng:** Gọi `System.setProperty("jdk.serialFilter", "...")` sau khi cơ chế `ObjectInputFilter.Config` đã khởi tạo **không bảo đảm thay đổi bộ lọc tĩnh có hiệu lực**. Dùng JVM startup options hoặc bootstrap API đúng thời điểm.

### Cấu hình toàn JVM không giống “chắc chắn được áp dụng cùng per-stream”

Ở JDK 17, một **filter factory** được gọi để chọn filter cho từng stream. Built-in factory sử dụng global filter khi stream được tạo, nhưng khi code gọi `setObjectInputFilter(streamPolicy)`, built-in factory có thể **thay global filter bằng filter theo stream** thay vì tự động giao hai chính sách. Nếu chính sách bảo vệ toàn JVM bắt buộc luôn có hiệu lực, đừng chỉ suy diễn từ việc đã đặt `jdk.serialFilter`; cần kiểm soát/combine các filter ở factory phù hợp.

## 6. JDK 17: filter factory theo ngữ cảnh (JEP 415)

Từ JDK 17, `ObjectInputFilter.Config` có filter factory cấp JVM để chọn **một filter hiệu lực cho mỗi `ObjectInputStream`**. Nó có thể dựa trên filter toàn JVM, filter mà code yêu cầu cho stream và ngữ cảnh gọi (module, ThreadLocal, call stack, service owner…).

Đặt bằng API:

```java
// Phác thảo chỉ minh họa cách ghép hai filter.
// Phải đặt ở bootstrap, trước bất kỳ ObjectInputStream nào được tạo.
ObjectInputFilter.Config.setSerialFilterFactory((current, requested) -> {
    if (current == null) return requested;
    if (requested == null) return current;
    return ObjectInputFilter.merge(current, requested);
});
```

Đây là **đoạn minh họa cấu hình toàn JVM**, không phải chính sách production hoàn chỉnh. `current` là filter hiện tại của stream (hoặc `null` ở lúc khởi tạo), `requested` là filter mà constructor hoặc `setObjectInputFilter` yêu cầu. Nếu `current` đã khác `null`, factory không được trả `null` để vô hiệu hóa filter đang tồn tại.

Trong thực tế, cần có đội sở hữu cấu hình toàn JVM, kiểm thử hành vi merge/UNDECIDED/REJECTED, đo hiệu năng và đảm bảo policy per-stream không vô tình **nới rộng** hoặc **từ chối** các kiểu mà framework hợp lệ cần dùng.

Có thể cấu hình một class factory bằng startup property:

```bash
java -Djdk.serialFilterFactory=com.example.security.MyFilterFactory com.example.Main
```

Class factory này phải do ứng dụng cung cấp, **public**, có public constructor không tham số, triển khai `BinaryOperator<ObjectInputFilter>` và được class loader phù hợp nạp được. Thuộc tính `jdk.serialFilterFactory` là **tên lớp factory**, không phải chuỗi pattern. Nó khác với `jdk.serialFilter`.

Theo Java 17, cấu hình factory chỉ được thay đổi **một lần** và trước khi bất kỳ `ObjectInputStream` nào được tạo. Cấu hình qua system/security property có quyền ưu tiên và không thể bị tùy tiện thay thế sau đó bằng API. `System.setProperty("jdk.serialFilterFactory", "...")` sau khi Config đã khởi tạo **không tự bật factory mới**.

### Khi nào cần factory thay vì filter tĩnh?

Một ứng dụng nhiều module có thể nhận những loại payload khác nhau: thanh toán chỉ dùng `PaymentDTO`, lưu cache dùng `CacheSnapshot`, công cụ nội bộ dùng `MigrationRecord`. Một JVM-wide allowlist đủ rộng cho tất cả có thể tăng diện tấn công. Factory theo ngữ cảnh có thể ghép **giới hạn nền bắt buộc** với **allowlist cho đúng đầu vào**. Nhưng ngữ cảnh phải đáng tin, không lấy tên class tùy ý từ payload hay request của bên gửi làm chính sách tự cho phép.

## 7. Ví dụ Java 17 hoàn chỉnh: per-stream allowlist, chấp nhận một lớp và từ chối lớp khác

Chương trình này tự tạo hai serialization stream trong bộ nhớ. Nó không đọc dữ liệu từ mạng, nên an toàn để minh họa kiểm tra filter. Một lớp được cho phép là `AllowedMessage`, lớp còn lại là `BlockedMessage`. Mỗi lần đọc tạo **một ObjectInputStream riêng** và cài cùng một filter **trước `readObject()`**.

Tạo file **`SerialFilterDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class SerialFilterDemo {
    private SerialFilterDemo() {}

    private static final class AllowedMessage implements Serializable {
        private static final long serialVersionUID = 1L;
        private final int code;

        AllowedMessage(int code) {
            this.code = code;
        }

        int code() {
            return code;
        }
    }

    private static final class BlockedMessage implements Serializable {
        private static final long serialVersionUID = 1L;
        private final int code;

        BlockedMessage(int code) {
            this.code = code;
        }
    }

    private static byte[] encode(Serializable object) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(object);
        }
        return bytes.toByteArray();
    }

    private static Object decode(byte[] bytes) throws Exception {
        ObjectInputFilter policy = ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=100;maxbytes=8192;maxarray=128;" +
                "SerialFilterDemo$AllowedMessage;!*");

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(policy);
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = encode(new AllowedMessage(42));
        AllowedMessage accepted = (AllowedMessage) decode(valid);
        System.out.println("allowed=" + accepted.code());

        byte[] invalid = encode(new BlockedMessage(99));
        try {
            decode(invalid);
            System.out.println("unexpected acceptance");
        } catch (InvalidClassException expected) {
            System.out.println("rejected=InvalidClassException");
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17**, với cấu hình JVM chuẩn không cài factory tùy biến:

```bash
javac SerialFilterDemo.java
java SerialFilterDemo
```

Kết quả dự kiến:

```text
allowed=42
rejected=InvalidClassException
```

**Tại sao kết quả như vậy?**

1. `encode` dùng `ObjectOutputStream` để biến instance hợp lệ thành byte array trong bộ nhớ; nó chưa đọc lại object.
2. `decode` tạo `ObjectInputStream` rồi cài filter bằng `setObjectInputFilter` trước khi đọc. Pattern giới hạn depth/references/bytes/array length và chỉ cho phép tên class binary `SerialFilterDemo$AllowedMessage`.
3. Phần `!*` ở cuối từ chối các class còn lại khi được kiểm tra. `AllowedMessage` thuộc tập được phép, nên `readObject()` trả về đối tượng có `code=42`.
4. `BlockedMessage` không khớp allowlist, nên khi deserialize bị `REJECTED`, thường thông qua `InvalidClassException`. Chương trình bắt đúng loại exception này và chỉ in tên exception, tránh phụ thuộc phần message/stacktrace có thể thay đổi theo JVM.
5. Vì class chỉ lưu một trường primitive `int`, ví dụ không cần allowlist thêm các class lồng nhau như `ArrayList` hay các kiểu DTO khác. Nếu bổ sung field tham chiếu serializable, phải cập nhật filter và kiểm thử lại object graph.

Đây là ví dụ minh họa cơ chế lọc, **không phải bộ lọc dùng nguyên mẫu cho dữ liệu thực tế**. Với môi trường có JVM-wide filter/factory do ứng dụng hoặc framework đặt, filter hiệu lực có thể khác và cần được kiểm tra trước khi kết luận kết quả luôn giống demo.

## 8. Pattern syntax và các bẫy cấu hình

Cú pháp pattern filter của `ObjectInputFilter.Config.createFilter` là tập các thành phần **phân tách bằng dấu chấm phẩy**. Với class pattern:

| Pattern | Ý nghĩa |
| --- | --- |
| `com.example.Foo` | Tên class đầy đủ chính xác |
| `com.example.*` | Những class trực tiếp trong package `com.example` |
| `com.example.**` | Những class trong package `com.example` và các package con |
| `com.example.Foo*` | Class có tên bắt đầu bằng tiền tố tương ứng |
| `java.base/java.util.*` | Class thuộc module `java.base` và package trực tiếp `java.util` |
| `!com.example.Dangerous` | Từ chối class này |
| `!*` | Từ chối mọi class còn lại có thể so khớp nếu đặt cuối danh sách |

Các giới hạn nhận `maxdepth`, `maxrefs`, `maxbytes`, `maxarray`. Nếu một giới hạn xuất hiện nhiều lần, giá trị **sau cùng** của giới hạn đó có hiệu lực. Whitespace là một phần của pattern và có thể làm tên không khớp; nên tránh khoảng trắng thừa khi cấu hình qua property.

Một số bẫy:

- **Thứ tự pattern quan trọng.** Nếu đặt `!*` trước allowlist, các class tiếp theo không còn cơ hội được cho phép.
- **Tên binary của lớp lồng nhau** dùng ký tự `$` (ví dụ `SerialFilterDemo$AllowedMessage`), không dùng tên nguồn `SerialFilterDemo.AllowedMessage`.
- **Pattern theo class khác kiểm tra nội dung.** Cho phép `java.util.ArrayList` không ngăn danh sách chứa dữ liệu nghiệp vụ sai hoặc có quá nhiều phần tử khi giới hạn nào đó không bao phủ đúng tình huống.
- **Giới hạn streamBytes không phải tổng ngân sách của tiến trình.** Mỗi `ObjectInputStream` có trạng thái theo dõi riêng; rất nhiều stream đồng thời vẫn có thể tiêu tốn nhiều tài nguyên.
- **UNDECIDED không tạo bảo vệ deny-by-default.** Nếu mong muốn cấm class lạ, phải thiết kế chính sách reject rõ ràng.
- **Không dùng filter kiểu "cho phép toàn bộ `java.base`" theo quán tính.** Mở rộng quyền đến nhiều class hơn nhu cầu thực tế.
- **Không đọc payload rồi mới cài filter.** Chọn chính sách trước operation đầu tiên cần được bảo vệ.

## 9. Phụ thuộc phiên bản JDK: JEP 290 và JEP 415

| Dòng JDK | Khả năng và lưu ý |
| --- | --- |
| Java 6/7/8 cũ trước các bản vá serialization filtering | Không thể giả định có API như JDK 9+ |
| Một số bản cập nhật JDK 6/7/8 từ đợt Critical Patch Update 01/2017 | Có backport cơ chế lọc; API cũ có thể nằm ở `sun.misc.ObjectInputFilter`, khác đường import chuẩn của JDK 9+ |
| JDK 9 (JEP 290) | Cơ chế `java.io.ObjectInputFilter`, filter theo stream và toàn JVM; giới hạn class/graph |
| JDK 11 | Sử dụng `java.io.ObjectInputFilter` nhưng không giả định API filter factory như JDK 17 |
| JDK 17 (JEP 415) | Bổ sung **context-specific filter factory**, `Config.setSerialFilterFactory` và `jdk.serialFilterFactory`; có helper API để ghép chính sách |
| Các JDK về sau | Kiểm tra tài liệu API, release notes, flags cấu hình và hành vi thực tế của bản JDK/vendor cụ thể; không suy đoán hoàn toàn giống JDK 17 |

Các mốc quan trọng:

- **JEP 290 – Filter Incoming Serialization Data**: được đưa vào Java 9; các bản vá JDK 8u121, 7u131, 6u141 từng nhận backport. Không tự động suy ra mã nguồn dùng `java.io.ObjectInputFilter` biên dịch nguyên trạng trên các JDK cũ: package/API ở các backport có khác biệt.
- **JEP 415 – Context-Specific Deserialization Filters**: được đưa vào JDK 17. Một chương trình cần `setSerialFilterFactory` nên khai báo và kiểm thử mức JDK tối thiểu là 17 (hoặc tính đến các backport đặc thù nếu vendor cung cấp, không mặc định).
- Các tham số khởi động và API cài filter phải được xác minh theo **JDK đích**, không chỉ JDK build ở máy phát triển. Khi chạy ứng dụng/framework trên nhiều JVM, cần kiểm thử cả trường hợp không có filter mặc định và trường hợp môi trường vận hành đặt sẵn filter/factory.

### Kiểm tra phiên bản chạy thực tế

```bash
java -version
javac -version
```

Không chỉ kiểm tra `java -version` của một terminal rồi tin rằng container, service, IDE hoặc máy chủ triển khai dùng đúng JVM đó. Theo dõi phiên bản và vendor của runtime thật sự chạy deserialize, đồng thời xem `jdk.serialFilter` / `jdk.serialFilterFactory` được truyền bằng startup arguments, system/security properties hay startup API.

## 10. Triển khai filter trong ứng dụng lớn

Một chính sách khả thi thường có các lớp bảo vệ bổ sung:

1. **Loại bỏ Java native serialization** ở điểm nhận payload không tin cậy khi có thể; dùng định dạng có schema và xác thực.
2. **Inventory các điểm deserialize:** `ObjectInputStream` trực tiếp và những thư viện/framework có thể dùng nó ngầm.
3. **Định nghĩa allowlist theo loại payload:** chỉ cho đúng class nghiệp vụ và phần phụ thuộc cần thiết, hạn chế package wildcard rộng.
4. **Giới hạn tài nguyên:** depth, references, array length, stream bytes; bổ sung giới hạn ở tầng vận chuyển, thời gian xử lý, số lượng request/stream đồng thời.
5. **Đặt chính sách sớm:** global tại khởi động, per-stream trước `readObject()`, factory trước khi tạo ObjectInputStream đầu tiên.
6. **Kiểm thử kết hợp:** xác minh filter JVM và stream không vô tình thay thế/nới rộng nhau; thử payload hợp lệ, lớp lạ, mảng lớn, đồ thị sâu, EOF/corruption.
7. **Xử lý lỗi có chủ đích:** khi `InvalidClassException` hoặc `IOException` xảy ra, đóng stream và báo dữ liệu không hợp lệ; không tự đọc lại bằng filter rộng hơn để "cố tương thích".
8. **Logging/monitoring:** ghi lại class bị chặn hoặc nguyên nhân giới hạn khi an toàn, không log thẳng dữ liệu bí mật hay toàn bộ bytes serialization.
9. **Kiểm soát version drift:** trong pipeline build/deploy, kiểm tra lớp nào đã thay đổi, dependency update có phát sinh class hợp lệ mới và chính sách có còn đúng.
10. **Threat modeling và review:** filter có giới hạn, không thay thế kiểm soát quyền, xác thực, giới hạn bộ nhớ và tránh gadget deserialization.

Trong ứng dụng nhiều nhóm cùng chạy trên một JVM, cấu hình `setSerialFilter` hoặc `setSerialFilterFactory` là tài nguyên **process-wide**: mỗi thư viện không thể tùy tiện thiết lập giá trị riêng một lần nữa. Tốt hơn là bộ phận sở hữu bootstrap chọn chiến lược hợp nhất và cung cấp giao diện cấu hình cho các module.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hệ quả | Hướng khắc phục |
| --- | --- | --- |
| Đặt filter cho một ObjectInputStream sau khi đã deserialize | Có thể đã xử lý lớp nguy hiểm trước khi bảo vệ | Đặt trước lần `readObject()` đầu tiên |
| Cho rằng `UNDECIDED` bằng từ chối | Lớp không khớp vẫn có thể được đọc | Allowlist với quy tắc reject phần còn lại |
| Cấu hình `jdk.serialFilter` nhưng stream-specific filter thay thế nó | Một số ngưỡng baseline không còn hiệu lực theo default factory | Dùng factory phối hợp và kiểm thử filter hiệu lực |
| Coi `jdk.serialFilterFactory` là một pattern string | Không nạp được factory | Cung cấp tên class triển khai `BinaryOperator<ObjectInputFilter>` |
| Gọi `setSerialFilterFactory` sau khi đã tạo ObjectInputStream | Có thể ném `IllegalStateException` | Cấu hình từ bootstrap |
| Dùng `System.setProperty` sau lúc Config khởi tạo | Tưởng rằng thay chính sách đã chạy nhưng không có hiệu lực | Dùng startup property hoặc API đúng thời điểm |
| Sao chép code JDK 17 sang JDK 8 | Lỗi import/API hoặc thiếu phương thức | Kiểm tra bản JDK/vendor và khác biệt backport |
| Chỉ cho DTO nhưng quên array/nested/collection hợp lệ | `InvalidClassException` với input hợp lệ | Kiểm thử toàn bộ graph và các trường hợp biên |
| Mở `java.base/*` quá rộng không cân nhắc | Cho nhiều class hơn nhu cầu | Giới hạn class/module theo trust model |
| Chỉ đặt `maxarray` và nghĩ đã giới hạn RAM tổng | Có thể gặp nhiều object/stream hoặc cấu trúc không phải array | Kết hợp maxrefs/maxdepth/maxbytes và hạn mức ngoài stream |
| Bắt `InvalidClassException` rồi deserialize lại không filter | Mất hàng rào bảo vệ | Reject payload, cảnh báo và đóng stream |
| Tin filter thay được xác thực đầu vào | Gadget và lỗi dữ liệu nghiệp vụ vẫn có thể xảy ra | Tránh untrusted native deserialization, validate cấu trúc và nguồn |

## 12. Câu hỏi tự kiểm tra

**1. Khi nào nên chọn stream-specific filter?**  
Khi biết chính xác tập class hợp lệ của một đầu vào hoặc một loại dữ liệu; tạo `ObjectInputStream`, áp dụng filter trước lần đọc và xác minh tương tác với chính sách JVM-wide.

**2. Nếu muốn bảo vệ mọi điểm tạo ObjectInputStream trong JVM mà không sửa từng call site, dùng gì?**  
Có thể cấu hình `jdk.serialFilter` lúc khởi động. Tuy nhiên phải xác minh việc kết hợp với per-stream filter/factory của ứng dụng; không tự coi global filter luôn là lớp "bắt buộc" nếu factory cho phép thay thế.

**3. Tại sao pattern `com.example.**` chưa chắc là allowlist nghiêm ngặt?**  
Những class không khớp có thể nhận `UNDECIDED`. Nếu cần deny-by-default, bổ sung pattern từ chối phù hợp (chẳng hạn `!*` cuối danh sách) và kiểm thử.

**4. `maxarray` có ngăn được mọi collection khổng lồ không?**  
Không. Nó giới hạn độ dài array được kiểm tra, không trực tiếp biểu diễn kích thước mọi collection hay tổng RAM của nhiều stream.

**5. Có thể gọi `setSerialFilterFactory` trên JDK 11 chuẩn như JDK 17 không?**  
Không nên: API context-specific factory được bổ sung ở JDK 17. Với các runtime cũ, sử dụng khả năng được hỗ trợ ở JDK đích hoặc nâng cấp phiên bản khi thiết kế đòi hỏi factory.

**Ghi nhớ:** Filter theo stream giúp hạn chế đúng lớp và quy mô dữ liệu của **một ObjectInputStream**; `jdk.serialFilter` đặt chính sách toàn JVM; từ JDK 17, `jdk.serialFilterFactory` và `setSerialFilterFactory` quyết định cách chọn/kết hợp chúng. Nắm rõ `ALLOWED/REJECTED/UNDECIDED`, thời điểm đặt filter, cơ chế factory và phiên bản JDK là điều bắt buộc nếu dùng Java serialization trong hệ thống có yêu cầu bảo mật.