# SerializationHints cho Java serialization

Java có cơ chế **Object Serialization** để chuyển một object graph thành luồng byte và khôi phục nó thành object bằng `ObjectOutputStream` và `ObjectInputStream`. Cơ chế này dựa trên metadata của class, các field có thể serialize, quan hệ kế thừa và những hook như `writeObject` hoặc `readResolve`. Trên JVM, class loader và reflection của JVM có thể đáp ứng nhiều thao tác động. Khi biên dịch ứng dụng Spring Boot thành GraalVM Native Image, các class cần tham gia Java serialization phải được nhận diện hoặc khai báo metadata trước khi tạo executable.

Spring cung cấp `SerializationHints` trong hệ thống `RuntimeHints` để mô tả những kiểu dữ liệu cần hỗ trợ serialization. Bài này tập trung vào **Java serialization**, cách khai báo hints bằng `RuntimeHintsRegistrar`, cách kiểm thử object graph trên native executable và những giới hạn cần lưu ý. Java serialization là cơ chế riêng, không đồng nghĩa với JSON serialization của Jackson.

## 1. Java serialization là gì?

Java serialization là cơ chế chuẩn của Java để ghi trạng thái object thành byte stream và đọc lại thành object. Một class thường tham gia cơ chế này bằng cách triển khai marker interface `java.io.Serializable`:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class CustomerSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String customerId;
    private final String displayName;

    public CustomerSnapshot(String customerId, String displayName) {
        this.customerId = customerId;
        this.displayName = displayName;
    }

    public String getCustomerId() {
        return customerId;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

`Serializable` không có method cần implement. Nó đánh dấu rằng object thuộc loại có thể được xử lý bởi cơ chế Java serialization, nếu toàn bộ trạng thái cần serialize đáp ứng các quy tắc của cơ chế đó.

Hai class quan trọng:

- `ObjectOutputStream` ghi object graph vào một `OutputStream` bằng `writeObject(...)`.
- `ObjectInputStream` đọc byte stream và khôi phục object bằng `readObject()`.

Ví dụ luồng xử lý:

~~~mermaid
flowchart LR
    A["Object graph"] --> B["ObjectOutputStream.writeObject"]
    B --> C["Serialized byte stream"]
    C --> D["ObjectInputStream.readObject"]
    D --> E["Object graph mới"]
~~~

Object được khôi phục là object mới trong tiến trình đọc. Nó không phải cùng một instance với object ban đầu. Java serialization có cơ chế theo dõi tham chiếu trong stream để giữ quan hệ chia sẻ object và xử lý chu trình tham chiếu.

## 2. Object graph và những class cần được hỗ trợ

Khi gọi `writeObject(root)`, Java serialization có thể đi qua các object được tham chiếu từ root. Vì vậy, metadata cần xem xét theo **object graph thực tế**, không chỉ class của object ở ngoài cùng.

Ví dụ:

~~~java
package com.example.nativeimage;

import java.io.Serial;
import java.io.Serializable;
import java.math.BigDecimal;
import java.util.List;

public final class OrderSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final CustomerSnapshot customer;
    private final List<OrderLineSnapshot> lines;
    private final BigDecimal total;

    public OrderSnapshot(
            String orderId,
            CustomerSnapshot customer,
            List<OrderLineSnapshot> lines,
            BigDecimal total) {
        this.orderId = orderId;
        this.customer = customer;
        this.lines = List.copyOf(lines);
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public CustomerSnapshot getCustomer() {
        return customer;
    }

    public List<OrderLineSnapshot> getLines() {
        return lines;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

~~~java
package com.example.nativeimage;

import java.io.Serial;
import java.io.Serializable;

public final class OrderLineSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String sku;
    private final int quantity;

    public OrderLineSnapshot(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Trong object graph trên, các kiểu ứng dụng cần chú ý gồm:

- `OrderSnapshot`: kiểu root được truyền vào stream.
- `CustomerSnapshot`: kiểu được tham chiếu từ field của root.
- `OrderLineSnapshot`: kiểu phần tử trong collection.
- Các kiểu khác có thể xuất hiện theo subtype thực tế, chẳng hạn implementation của một interface hoặc class được chọn theo cấu hình.

`String`, `BigDecimal` và các collection chuẩn thuộc JDK có hỗ trợ serialization tương ứng trong JDK/GraalVM. Với class ứng dụng hoặc class thư viện do ứng dụng đưa vào object graph, hãy xác định rõ metadata serialization cần thiết. Không giả định đăng ký root type tự động bao phủ mọi concrete type mà chương trình có thể ghi/đọc.

### Kiểu đa hình cần được xem xét

Nếu field được khai báo là interface hoặc abstract class, object thực tế có thể là một trong nhiều implementation:

~~~java
public interface PaymentDetails extends Serializable {
}

public final class CardPaymentDetails implements PaymentDetails {
    // Trạng thái thanh toán bằng thẻ.
}

public final class BankTransferDetails implements PaymentDetails {
    // Trạng thái chuyển khoản.
}
~~~

Nếu cả `CardPaymentDetails` và `BankTransferDetails` đều có thể xuất hiện trong stream, hãy đăng ký các kiểu concrete cần hỗ trợ. Kiểu khai báo của field không nhất thiết là kiểu runtime được ghi vào stream.

## 3. Vì sao Native Image cần SerializationHints?

GraalVM Native Image thực hiện reachability analysis theo giả định closed-world. Với lời gọi trực tiếp như `new CustomerSnapshot(...)`, trình phân tích có thể nhìn thấy kiểu cần dùng từ mã. Nhưng Java serialization có nhiều hoạt động dựa trên metadata và cơ chế khôi phục object, bao gồm:

- Xác định class descriptor trong stream.
- Tạo object và khôi phục trạng thái mà không đi theo constructor thông thường của class Serializable.
- Xử lý field, kế thừa và các class concrete xuất hiện trong object graph.
- Gọi các serialization hooks được định nghĩa bởi class.
- Xử lý class được xác định từ stream thay vì từ một lời gọi constructor tường minh.

Vì vậy, việc class đã nằm trong dependency hoặc đã được dùng ở một đường code thông thường **không bảo đảm** mọi đường Java serialization của class đó được giữ đúng trong native executable.

Spring AOT cung cấp `RuntimeHints` để khai báo khả năng cần có ở runtime. Phần serialization được truy cập qua:

~~~java
hints.serialization()
~~~

`SerializationHints` mô tả những kiểu cần tham gia Java serialization để Spring AOT có thể chuyển thông tin phù hợp sang metadata của Native Image.

**Không nhầm SerializationHints với reflection hints.** Reflection hints mô tả khả năng truy cập class/member bằng reflection. Serialization hints mô tả class cần hỗ trợ cơ chế Java object serialization. Một ứng dụng có thể cần cả hai nếu vừa serialize object bằng `ObjectOutputStream` vừa truy cập một số member bằng reflection độc lập.

## 4. Khai báo SerializationHints bằng RuntimeHintsRegistrar

Spring cung cấp interface `RuntimeHintsRegistrar` để thư viện hoặc ứng dụng đóng góp runtime hints. Với các kiểu trong ví dụ, có thể đăng ký như sau:

~~~java
package com.example.nativeimage;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class OrderSerializationHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.serialization().registerType(OrderSnapshot.class);
        hints.serialization().registerType(CustomerSnapshot.class);
        hints.serialization().registerType(OrderLineSnapshot.class);
    }
}
~~~

Đăng ký registrar với Spring context:

~~~java
package com.example.nativeimage;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(OrderSerializationHints.class)
class NativeSerializationConfiguration {
}
~~~

Khi Spring AOT xử lý cấu hình, `@ImportRuntimeHints` giúp Spring phát hiện registrar và thu thập các hints do registrar đóng góp.

Các điểm cần nhớ:

1. Dùng `hints.serialization().registerType(...)` cho từng kiểu ứng dụng cần hỗ trợ Java serialization.
2. Đăng ký cả kiểu root, kiểu được tham chiếu và các concrete subtype có thể xuất hiện.
3. Đặt registrar trong package được Spring component/configuration scanning phát hiện, hoặc import cấu hình rõ ràng.
4. Hints phải được đóng góp trong pha AOT trước native compilation.
5. Sau khi thay đổi hints, phải chạy lại AOT/native build để tạo binary mới.

API chi tiết có thể thay đổi theo phiên bản Spring Framework/Spring Boot. Ví dụ trên sử dụng API Spring AOT hiện đại có `RuntimeHints.serialization()`; hãy đối chiếu dependency version thực tế nếu IDE không nhận diện method.

### Đăng ký không có nghĩa object được tạo lúc build

Registrar chỉ mô tả khả năng cần có cho native runtime. Việc gọi `registerType` không tạo một `OrderSnapshot` instance, không đọc database và không thực hiện serialize payload trong pha build. Object thật vẫn được tạo và serialize/deserialize khi ứng dụng chạy.

## 5. Serialize và deserialize một object graph

Ví dụ sau minh họa một round trip trong bộ nhớ. Trong ứng dụng thật, byte stream có thể đến từ file, message hoặc hệ thống lưu trữ; cơ chế serialization không phụ thuộc nơi lưu byte.

~~~java
package com.example.nativeimage;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.math.BigDecimal;
import java.util.List;

public final class OrderSnapshotCodec {

    public byte[] serialize(OrderSnapshot snapshot) throws IOException {
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(snapshot);
            output.flush();
            return bytes.toByteArray();
        }
    }

    public OrderSnapshot deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ByteArrayInputStream inputBytes = new ByteArrayInputStream(bytes);
             ObjectInputStream input = new ObjectInputStream(inputBytes)) {
            Object value = input.readObject();
            return OrderSnapshot.class.cast(value);
        }
    }

    public static void main(String[] args) throws Exception {
        CustomerSnapshot customer =
                new CustomerSnapshot("C-100", "Lan");

        OrderSnapshot original = new OrderSnapshot(
                "O-2026-001",
                customer,
                List.of(new OrderLineSnapshot("SKU-01", 2)),
                new BigDecimal("125000.00")
        );

        OrderSnapshotCodec codec = new OrderSnapshotCodec();
        byte[] bytes = codec.serialize(original);
        OrderSnapshot restored = codec.deserialize(bytes);

        System.out.println("orderId=" + restored.getOrderId());
        System.out.println("customer=" + restored.getCustomer().getDisplayName());
        System.out.println("lines=" + restored.getLines().size());
        System.out.println("sameInstance=" + (original == restored));
    }
}
~~~

Kết quả dự kiến:

~~~text
orderId=O-2026-001
customer=Lan
lines=1
sameInstance=false
~~~

Ví dụ cần các class `CustomerSnapshot`, `OrderLineSnapshot` và `OrderSnapshot` cùng package như đã khai báo ở trên. Có thể tách codec thành một Spring bean hoặc gọi từ service; việc tổ chức bean không thay đổi yêu cầu metadata serialization.

### Vì sao phải kiểm tra cả chiều ghi và chiều đọc?

- **Serialize:** xác nhận các kiểu trong graph có thể được ghi ra stream.
- **Deserialize:** xác nhận runtime có thể đọc class descriptor và khôi phục các kiểu tương ứng.
- **Round trip:** xác nhận dữ liệu quan trọng được giữ đúng sau khi khôi phục.
- **Payload cũ:** xác nhận ứng dụng có thể đọc stream được tạo bởi version trước nếu nghiệp vụ yêu cầu tương thích.

Một test chỉ gọi `writeObject` chưa chứng minh `readObject` hoạt động trong native. Hãy kiểm thử cả hai chiều trên chính executable native.

## 6. Những quy tắc Java serialization ảnh hưởng đến dữ liệu

### serialVersionUID

`serialVersionUID` là version identifier của class trong Java serialization. Nếu không khai báo rõ, JVM có thể tính một giá trị mặc định dựa trên cấu trúc class. Thay đổi class có thể làm giá trị tính toán thay đổi và khiến stream cũ không còn tương thích.

Nên khai báo rõ với class Serializable có dữ liệu cần lưu lâu dài:

~~~java
@Serial
private static final long serialVersionUID = 1L;
~~~

Khai báo cùng một số không tự động bảo đảm mọi thay đổi schema đều an toàn. Cần thiết kế quy tắc tương thích, kiểm thử dữ liệu cũ và xử lý field mới/field đã bỏ phù hợp.

### transient và static

- Field đánh dấu `transient` không được ghi theo cơ chế default serialization.
- Field `static` thuộc class, không thuộc trạng thái instance nên không được serialize như field instance.
- Khi deserialize, field transient có thể nhận giá trị mặc định hoặc được khôi phục trong custom `readObject`.

Ví dụ:

~~~java
public final class SessionSnapshot implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final String sessionId;
    private transient String temporaryCache;

    public SessionSnapshot(String sessionId, String temporaryCache) {
        this.sessionId = sessionId;
        this.temporaryCache = temporaryCache;
    }
}
~~~

Không serialize mật khẩu, token, khóa bí mật hoặc dữ liệu nhạy cảm chỉ vì class có thể serialize. Dùng `transient` có thể loại field khỏi default serialization, nhưng không thay thế thiết kế quản lý secret đúng cách.

### Custom serialization hooks

Một class có thể tùy chỉnh quá trình serialize/deserialize bằng các method đặc biệt, chẳng hạn:

- `private void writeObject(ObjectOutputStream out)`
- `private void readObject(ObjectInputStream in)`
- `Object writeReplace()`
- `Object readResolve()`

Các method này phải tuân theo signature và quy tắc Java serialization. Chúng có thể thay đổi dữ liệu được ghi, xác thực trạng thái hoặc thay thế object sau khi đọc. Khi sử dụng custom hooks, hãy test chúng bằng native executable, đặc biệt nếu hook gọi helper class, reflection hoặc resource động.

`Externalizable` là một cơ chế khác yêu cầu class tự kiểm soát `writeExternal` và `readExternal`; nó có quy tắc constructor riêng. Nếu ứng dụng dùng `Externalizable`, hãy kiểm tra các class và constructor cần thiết theo API Java và Native Image version đang dùng, thay vì mặc định coi nó giống Serializable thông thường.

## 7. Những kiểu nào cần đăng ký?

Không có một quy tắc “chỉ đăng ký root type là đủ” cho mọi object graph. Hãy lập danh sách theo các payload thực tế:

| Kiểu dữ liệu | Cần xem xét? | Ghi chú |
| --- | --- | --- |
| Root class được truyền cho `writeObject` | Có | Kiểu bắt đầu object graph |
| Class được tham chiếu từ field | Có | Có thể được serialize đệ quy |
| Concrete subtype của interface/abstract field | Có | Runtime type có thể khác kiểu khai báo |
| Class trong collection | Có | Đăng ký từng kiểu ứng dụng xuất hiện trong phần tử |
| Enum ứng dụng | Có nếu nằm trong graph | Kiểm tra payload thực tế và metadata cần thiết |
| JDK serializable classes | Kiểm tra theo JDK/GraalVM support | Không tự đăng ký tất cả class JDK một cách máy móc |
| Class của thư viện bên thứ ba | Có nếu nằm trong graph | Ưu tiên metadata do thư viện cung cấp; bổ sung nếu thiếu |
| Class chỉ dùng cho JSON/Jackson | Không phải vì JSON mà cần SerializationHints | Dùng cơ chế binding/reflection phù hợp với serializer đó |

Nếu ứng dụng có nhiều loại payload, nên tạo một registrar theo từng nhóm nghiệp vụ hoặc theo module, để danh sách hints có thể review và kiểm thử.

### Khi object graph thay đổi

Giả sử phiên bản sau bổ sung field `paymentDetails` có thể chứa `CardPaymentDetails` hoặc `BankTransferDetails`. Hãy cập nhật hints cho concrete types mới và kiểm thử payload có cả hai loại. Nếu không, JVM có thể chạy đúng trong khi native chỉ lỗi ở loại payment mới.

Đừng đăng ký tất cả class trong một package một cách rộng rãi nếu không cần. Danh sách có chủ đích giúp hiểu rõ phạm vi dữ liệu và hạn chế metadata dư thừa.

## 8. Phân biệt Java Serialization với JSON serialization

Hai cơ chế cùng chuyển dữ liệu thành một dạng có thể lưu hoặc truyền, nhưng có mục tiêu và metadata khác nhau:

| Khía cạnh | Java Object Serialization | JSON serialization (ví dụ Jackson) |
| --- | --- | --- |
| API thường dùng | `ObjectOutputStream` / `ObjectInputStream` | `ObjectMapper` |
| Marker interface | Thường dùng `Serializable` | Không yêu cầu |
| Dạng dữ liệu | Java serialization stream, gắn với class descriptor | Văn bản JSON |
| Tương thích giữa ngôn ngữ | Hạn chế, gắn chặt hệ sinh thái Java | Rộng hơn, nhiều ngôn ngữ hỗ trợ |
| Metadata Native Image | `SerializationHints` cho Java serialization | Reflection/binding hints hoặc metadata của integration Jackson |
| Khả năng đọc thủ công | Không thuận tiện | Có thể đọc và debug bằng công cụ JSON |
| Rủi ro khi deserialize dữ liệu không tin cậy | Đặc biệt nhạy cảm vì object hooks và gadget chains | Cũng cần validation, nhưng không dùng cơ chế khôi phục object Java tùy ý theo cùng cách |

`SerializationHints` **không phải** là cách đăng ký DTO cho mọi serializer. Nếu endpoint REST trả `OrderSnapshot` thành JSON bằng Jackson, hãy kiểm tra Spring AOT/Jackson integration và binding hints phù hợp. Nếu ứng dụng ghi `OrderSnapshot` qua `ObjectOutputStream`, đó mới là tình huống Java serialization cần SerializationHints.

Với API mới, nên ưu tiên định dạng dữ liệu có schema và khả năng tương tác phù hợp như JSON hoặc Protocol Buffers khi không có yêu cầu tương thích Java serialization cũ. Java serialization thường phù hợp khi phải duy trì một hợp đồng stream Java đã tồn tại và có thể kiểm soát nguồn dữ liệu.

## 9. An toàn khi deserialize

Java serialization có rủi ro bảo mật đáng kể nếu ứng dụng đọc stream từ nguồn không tin cậy. Quá trình deserialize có thể tạo object và gọi custom hooks; một số class trên classpath có thể tạo thành gadget chain. Native Image **không loại bỏ rủi ro này**.

Các nguyên tắc tối thiểu:

- Không deserialize byte stream tùy ý từ người dùng hoặc nguồn không xác thực.
- Xác thực nguồn dữ liệu và bảo vệ integrity của payload.
- Dùng `ObjectInputFilter` để giới hạn class, độ sâu object graph, số lượng reference và kích thước stream.
- Chỉ cho phép những kiểu dữ liệu thật sự cần thiết.
- Giới hạn dung lượng và thời gian xử lý dữ liệu.
- Tránh dùng Java serialization cho dữ liệu trao đổi public nếu không có lý do tương thích mạnh.

Ví dụ filter minh họa giới hạn độ sâu, số reference và byte của stream:

~~~java
ObjectInputFilter filter = info -> {
    if (info.depth() > 20
            || info.references() > 1_000
            || info.streamBytes() > 1_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
};

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
}
~~~

Filter này chỉ đặt **giới hạn tài nguyên**; kết quả UNDECIDED không phải allow-list class. Trong hệ thống thực tế, hãy thêm chính sách class allow-list phù hợp với object graph được phép, hoặc dùng filter factory/policy của ứng dụng. Không copy filter giới hạn trên rồi coi là đã chặn mọi class nguy hiểm.

## 10. Kiểm thử SerializationHints trước khi build native

Có ba lớp kiểm thử hữu ích.

### Kiểm tra registrar được Spring AOT phát hiện

Đảm bảo configuration chứa `@ImportRuntimeHints` được import hoặc component scanning phát hiện trong application context. Nếu registrar nằm trong module thư viện, hãy kiểm tra cơ chế auto-configuration/import của module đó.

### Kiểm thử round trip trên JVM

Tạo payload đại diện với tất cả subtype và nested types cần hỗ trợ. Ghi object vào byte stream rồi đọc lại, so sánh các trường nghiệp vụ quan trọng. Bổ sung payload được tạo bởi phiên bản trước nếu cần hỗ trợ migration.

### Kiểm thử trên native executable

Build native image từ cùng source và chạy đúng test case trong binary native. Đừng chỉ xác nhận native executable khởi động hoặc health endpoint trả UP. Các nhánh serialize/deserialize có thể chỉ được gọi khi nhận message hoặc xử lý một loại dữ liệu hiếm.

Checklist test:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Serialize root object | Stream được ghi không lỗi |
| Deserialize stream mới | Khôi phục đúng root type và các field |
| Nested object | Các class được tham chiếu được khôi phục |
| Collection | Các phần tử và concrete type được hỗ trợ |
| Polymorphic field | Từng implementation có thể xuất hiện đều hoạt động |
| Custom hooks | writeObject/readObject/writeReplace/readResolve chạy đúng |
| Stream cũ | serialVersionUID và quy tắc tương thích đúng kỳ vọng |
| Input bị lỗi/không tin cậy | Filter từ chối dữ liệu vượt giới hạn hoặc type không được phép |

Nếu test chỉ chạy trên JVM, nó không xác minh được Native Image metadata. Nên đưa ít nhất một integration test round trip vào quy trình kiểm thử native.

## 11. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| JVM serialize thành công, native báo lỗi serialization | Kiểu chưa được đăng ký trong serialization metadata | Kiểm tra object graph và registrar |
| Serialize được nhưng deserialize thất bại | Thiếu metadata cho class trong stream hoặc custom hook/constructor không tương thích | Kiểm thử riêng chiều đọc, xem exception gốc và các concrete types |
| Root class đã đăng ký nhưng nested field lỗi | Chỉ đăng ký root, bỏ sót kiểu được tham chiếu | Đăng ký tất cả custom types có thể xuất hiện trong graph |
| Một subtype cụ thể lỗi | Field đa hình có concrete type chưa đăng ký | Thêm hint cho implementation đó và test payload |
| Payload cũ không đọc được | serialVersionUID/schema đã thay đổi hoặc custom readObject không xử lý version cũ | Xác định compatibility policy và test fixture của stream cũ |
| Giá trị transient mất sau deserialize | Hành vi default serialization | Khôi phục có chủ đích trong readObject nếu thật sự cần |
| Native chạy được nhưng dữ liệu không đúng | Custom hooks, readResolve hoặc logic khôi phục trạng thái | So sánh object trước/sau round trip trên native |
| Deserialize từ input không tin cậy gây rủi ro | Không có allow-list/filter phù hợp | Thêm ObjectInputFilter và giới hạn nguồn dữ liệu |

### Quy trình điều tra

1. Tái hiện lỗi với payload nhỏ nhất có thể.
2. Xác định lỗi xảy ra ở `writeObject` hay `readObject`.
3. Xác định class cụ thể trong object graph tại điểm lỗi.
4. Kiểm tra class đó đã có trong `RuntimeHints.serialization()` chưa.
5. Kiểm tra registrar có được Spring AOT phát hiện không.
6. Build lại native executable và chạy lại đúng payload.
7. Nếu lỗi vẫn còn, xem xét custom serialization hooks, class hierarchy, serialVersionUID và khác biệt phiên bản JDK/GraalVM.

Không thêm reflection hints một cách tùy tiện khi lỗi nằm ở Java serialization metadata. Trước tiên hãy xác định cơ chế nào đang được gọi.

## 12. Bài thực hành: đăng ký object graph cho native executable

Tạo một package `com.example.nativeimage` với các class:

- `CustomerSnapshot` implements `Serializable`.
- `OrderLineSnapshot` implements `Serializable`.
- `OrderSnapshot` implements `Serializable` và tham chiếu hai kiểu trên.
- `OrderSerializationHints` implements `RuntimeHintsRegistrar`.
- `NativeSerializationConfiguration` import registrar bằng `@ImportRuntimeHints`.

Thực hiện:

1. Viết codec dùng `ObjectOutputStream` và `ObjectInputStream`.
2. Tạo payload có customer, nhiều order lines và một số giá trị JDK serializable.
3. Đăng ký ba class ứng dụng qua `hints.serialization().registerType(...)`.
4. Chạy round-trip test trên JVM.
5. Build native executable theo Maven hoặc Gradle Native Build Tools đã cấu hình.
6. Chạy cùng round-trip test trên native executable.
7. Bổ sung một subtype mới vào object graph, cập nhật hints và xác minh test.
8. Thử đọc một payload cũ sau khi thay đổi class; ghi lại quy tắc tương thích serialVersionUID.
9. Nếu ứng dụng nhận stream từ nguồn ngoài, thêm ObjectInputFilter với allow-list và giới hạn tài nguyên phù hợp.

### Câu hỏi tự kiểm tra

1. `Serializable` có method nào cần implement không? Vai trò của marker interface là gì?
2. Vì sao đăng ký root type chưa chắc đủ cho toàn bộ object graph?
3. `SerializationHints` khác reflection hints như thế nào?
4. Vì sao Spring AOT cần biết các class được dùng bởi Java serialization trước native compilation?
5. Khi nào nên dùng `RuntimeHintsRegistrar` và `@ImportRuntimeHints`?
6. `serialVersionUID` ảnh hưởng ra sao đến việc đọc stream cũ?
7. Vì sao Java serialization từ nguồn không tin cậy cần `ObjectInputFilter`?
8. Nếu ứng dụng chỉ dùng Jackson để trả JSON, có nên đăng ký mọi DTO qua `SerializationHints` không? Vì sao?

**Tiêu chí đạt:** giải thích được Java object serialization và object graph; đăng ký đầy đủ kiểu cần hỗ trợ bằng `RuntimeHints.serialization()`; phân biệt SerializationHints với reflection/Jackson hints; kiểm thử được cả serialize và deserialize trên native executable; đồng thời quản lý serialVersionUID và bảo vệ đầu vào deserialize theo chính sách an toàn.
