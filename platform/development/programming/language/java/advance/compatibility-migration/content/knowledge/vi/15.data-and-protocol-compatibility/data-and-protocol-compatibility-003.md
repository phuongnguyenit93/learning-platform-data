# Record, enum và các quy tắc riêng của định dạng tuần tự hóa

Khi nâng cấp hoặc di chuyển ứng dụng Java, hai kiểu dữ liệu nhìn có vẻ “đơn giản” lại có những quy tắc tuần tự hóa rất riêng: **record** và **enum**. Cả hai thường được dùng để biểu diễn dữ liệu nghiệp vụ, nhưng định dạng ghi/đọc của chúng trong **Java Object Serialization** khác với lớp Java thông thường (`Serializable` class). Nếu ứng dụng còn ghi object vào file, lưu byte stream vào cache hoặc truyền đối tượng qua một giao thức Java-specific, những khác biệt này có thể quyết định khả năng đọc dữ liệu cũ sau khi nâng JDK hoặc thay đổi class.

Các quy tắc đặc biệt còn dễ bị nhầm với cách JSON, XML, JPA, Avro hoặc Protocol Buffers xử lý cùng một kiểu Java. Chẳng hạn, Java Object Serialization không ghi enum theo `ordinal()`; ngược lại, một ORM được cấu hình `EnumType.ORDINAL` có thể ghi đúng giá trị số thứ tự đó vào database. Với record, Java serialization sử dụng record components và gọi **canonical constructor** khi khôi phục object, trong khi một JSON mapper có thể sử dụng creator, converter hoặc module của riêng mình.

Bài học này tập trung vào Java Object Serialization như cơ sở, đối chiếu với các định dạng dữ liệu thường gặp, rồi xây dựng quy trình migration cho record và enum có thể thay đổi qua phiên bản ứng dụng.

## 1. Trước hết: xác định “tuần tự hóa” đang nói đến định dạng nào

**Serialization** là quá trình chuyển object thành một dạng có thể lưu trữ hoặc truyền đi. **Deserialization** làm ngược lại. Tên API Java không đủ để xác định hợp đồng dữ liệu; phải biết định dạng trên đường truyền hoặc trong storage.

Một hệ thống Java có thể dùng nhiều dạng:

| Định dạng/cơ chế | Dữ liệu thường được ghi | Yếu tố ảnh hưởng tương thích |
|---|---|---|
| Java Object Serialization (`ObjectOutputStream` / `ObjectInputStream`) | Object graph theo giao thức native của Java | Tên class, descriptor, field/component, enum constant, special rules của stream |
| JSON | Object, array, string, number, boolean, null | Property name, converter, enum representation, null/default policy |
| XML | Element, attribute, schema type | XML schema, binding và adapter |
| JPA/JDBC | Cột, row và quan hệ | Mapping, enum name/ordinal, converter, schema DB |
| Protocol Buffers | Field number và wire type | Field number, reserved fields, enum numeric values, unknown fields |
| Avro | Writer schema và reader schema | Schema resolution, default, enum symbols, union |
| Custom binary format | Byte layout do ứng dụng định nghĩa | Version header, byte order, field mapping và validation |

Khi yêu cầu “đổi class sang record” hoặc “thêm enum constant”, câu hỏi quan trọng không chỉ là mã có biên dịch được không, mà còn:

1. **Byte đã lưu được tạo bởi serializer nào?**
2. **Ứng dụng cũ và mới có thể cùng đọc cùng dữ liệu không?**
3. **Tên field, component hoặc enum constant có phải hợp đồng dữ liệu lâu dài không?**
4. **Có phiên bản schema và chính sách cho giá trị thiếu/chưa biết không?**
5. **Có dữ liệu cần lưu lại để rollback, replay hoặc kiểm toán không?**

Không được suy ra hành vi của JSON hoặc database chỉ từ các quy tắc Java Object Serialization.

## 2. Java Object Serialization ở mức tổng quan

### 2.1. `Serializable` là marker interface

Một lớp thông thường muốn tham gia Java Object Serialization thường triển khai marker interface `java.io.Serializable`:

```java
import java.io.Serializable;

public final class LegacyOrder implements Serializable {
    private static final long serialVersionUID = 1L;

    private String id;
    private long totalCents;

    public LegacyOrder(String id, long totalCents) {
        this.id = id;
        this.totalCents = totalCents;
    }
}
```

Marker interface không tự biến mọi field thành serializable. Trong quy trình ghi object, một field chứa object không serializable có thể khiến quá trình ghi ném `NotSerializableException`. Các quy tắc như `transient`, `static`, `serialVersionUID` và các serialization hooks có ý nghĩa đối với class thông thường, nhưng **không thể áp dụng máy móc nguyên xi cho record và enum**.

### 2.2. Ghi object bằng `ObjectOutputStream`

Ví dụ ghi object vào buffer nội bộ:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectOutputStream;

static byte[] serialize(Object value) throws IOException {
    try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
         ObjectOutputStream output = new ObjectOutputStream(bytes)) {

        output.writeObject(value);
        output.flush();
        return bytes.toByteArray();
    }
}
```

Ví dụ dùng dữ liệu mà ứng dụng kiểm soát và không đại diện cho giao thức nên dùng mặc định với dữ liệu không tin cậy. Java native deserialization có rủi ro thực thi hành vi không mong muốn qua object graph và các serialization hooks của những class trên classpath. Để nhận byte từ mạng/người dùng không tin cậy, nên ưu tiên định dạng dữ liệu có schema và giới hạn rõ, hoặc áp dụng serialization filters và phân vùng tin cậy thích hợp nếu bắt buộc phải dùng Object Serialization.

### 2.3. Đọc object: class hiện tại quyết định điều gì?

Khi `ObjectInputStream` đọc stream, nó cần ánh xạ mô tả class trong stream tới class có sẵn trong runtime. Nếu class thay đổi, việc đọc có thể thành công, thất bại hoặc tạo ra object có giá trị mặc định không như ý.

Các vấn đề cần phân biệt:

- **Class compatibility:** class theo tên và descriptor có thể được khớp với runtime class không?
- **Version compatibility:** với class Serializable thông thường, `serialVersionUID` có hợp lệ không?
- **Field compatibility:** field/component thiếu, thừa hoặc đổi kiểu được xử lý ra sao?
- **Object invariants:** constructor hoặc callback có xác thực dữ liệu không?
- **Graph identity:** quan hệ reference, aliasing và cycle có được giữ như thiết kế không?
- **Security:** runtime có cho phép deserialize những class xuất hiện trong stream không?

Đối với record và enum, Java đưa ra quy tắc đặc biệt ở nhiều bước trên.

## 3. Record: kiểu dữ liệu có thành phần rõ ràng

### 3.1. Record khác lớp POJO ở điểm nào?

Record được chuẩn hóa trong Java 16 (JEP 395). Một record khai báo **record components**, và compiler tạo ra field `private final` tương ứng, accessor, canonical constructor và các phương thức `equals`, `hashCode`, `toString` theo hợp đồng record.

Ví dụ:

```java
public record Money(String currency, long minorUnits) {
}
```

Record phù hợp cho dữ liệu có cấu trúc và được coi là value-like ở mức mô hình API. Nhưng record **không tự động là Serializable**. Nếu cần Java Object Serialization, phải khai báo rõ:

```java
import java.io.Serializable;

public record Money(String currency, long minorUnits)
        implements Serializable {
}
```

Record không có khả năng kế thừa một superclass tùy ý; nó trực tiếp kế thừa `java.lang.Record`. Record có thể implements interfaces như `Serializable`. Đặc tính final của record hạn chế subclassing, nhưng không đồng nghĩa mọi object được component tham chiếu đều bất biến.

### 3.2. Record chỉ bất biến ở mức reference của component

Ví dụ:

```java
import java.io.Serializable;
import java.util.List;

public record Basket(List<String> items)
        implements Serializable {
}
```

Record không cho phép gán lại reference `items` sau khi tạo, nhưng danh sách mà nó tham chiếu có thể vẫn mutable. Nếu caller truyền `ArrayList` rồi sửa danh sách, nội dung Basket sẽ thay đổi theo.

Để bảo vệ invariant và tránh giữ reference mutable từ caller:

```java
import java.io.Serializable;
import java.util.List;
import java.util.Objects;

public record Basket(List<String> items)
        implements Serializable {

    public Basket {
        Objects.requireNonNull(items, "items");
        items = List.copyOf(items);
    }
}
```

`List.copyOf` bảo đảm một list unmodifiable với các phần tử thích hợp, nhưng không tự làm deep copy những object mutable bên trong. Khi deserialize, canonical constructor cũng tham gia việc tái thiết lập invariant; do đó, cấu trúc validation trong constructor có ý nghĩa trực tiếp với dữ liệu cũ.

### 3.3. `Serializable` không kiểm tra tính serializable của mọi component ở compile time

Ví dụ:

```java
import java.io.Serializable;

final class NotSerializableHandle {
    final long address;

    NotSerializableHandle(long address) {
        this.address = address;
    }
}

public record NativeBinding(NotSerializableHandle handle)
        implements Serializable {
}
```

Khai báo record có thể biên dịch, nhưng `ObjectOutputStream.writeObject` sẽ gặp lỗi nếu cố ghi một component chứa object không thể serialize. Đối với native handle, socket, connection hoặc live resource, giải pháp thường không phải ép mọi object thành Serializable mà là chuyển sang một **DTO chỉ chứa dữ liệu ổn định**, để resource được tái tạo hoặc quản lý ngoài stream.

## 4. Quy tắc Java Serialization riêng của record

### 4.1. Thành phần record là nguồn dữ liệu tuần tự hóa

Java Object Serialization xử lý record class theo cơ chế dành riêng cho record components. Thay vì giả định có thể serialize tùy ý những field ẩn và khôi phục bằng cách cấp phát object không chạy constructor như class Serializable thông thường, runtime sử dụng mô tả record components và giá trị tương ứng.

Một record đơn giản:

```java
import java.io.Serializable;
import java.util.Objects;

public record CustomerSnapshot(
        String customerId,
        int loyaltyLevel,
        boolean active)
        implements Serializable {

    public CustomerSnapshot {
        Objects.requireNonNull(customerId, "customerId");
        if (loyaltyLevel < 0) {
            throw new IllegalArgumentException(
                "loyaltyLevel must be non-negative"
            );
        }
    }
}
```

Trong quá trình deserialization bằng cơ chế chuẩn, dữ liệu stream được ánh xạ đến các component của record runtime và được dùng để gọi **canonical constructor**. Vì vậy, logic validation và normalization trong constructor không chỉ chạy lúc ứng dụng gọi `new CustomerSnapshot(...)`, mà còn áp dụng khi khôi phục từ stream.

Đây là khác biệt lớn với class Serializable thông thường, nơi việc deserialization không gọi constructor của chính class Serializable theo cách tạo object thông thường.

### 4.2. Canonical constructor phải chấp nhận dữ liệu hợp lệ của những phiên bản cũ

Giả sử phiên bản đầu tiên:

```java
public record CustomerSnapshot(String customerId)
        implements java.io.Serializable {
}
```

Một phiên bản mới thêm component:

```java
public record CustomerSnapshot(
        String customerId,
        String region)
        implements java.io.Serializable {

    public CustomerSnapshot {
        if (region == null) {
            region = "UNSPECIFIED";
        }
    }
}
```

Khi stream cũ không có component `region`, cơ chế deserialization có thể cung cấp giá trị mặc định của kiểu (`null` đối với reference, `0` với các kiểu số tương ứng, `false` với `boolean`) cho component không xuất hiện trong stream. Canonical constructor là nơi có thể biến giá trị mặc định đó thành một biểu diễn hợp lệ.

Nhưng không phải lúc nào mặc định cũng hợp lý. Nếu một field mới bắt buộc phải có giá trị, việc đọc dữ liệu cũ có thể thất bại khi constructor kiểm tra invariant.

Ví dụ dễ làm hỏng compatibility:

```java
public record CustomerSnapshot(
        String customerId,
        String region)
        implements java.io.Serializable {

    public CustomerSnapshot {
        java.util.Objects.requireNonNull(
            region, "region"
        );
    }
}
```

Đối với stream không chứa `region`, constructor sẽ gặp `null` và từ chối dữ liệu. Nếu hệ thống phải đọc dữ liệu cũ, cần thiết kế default/migration phù hợp hoặc một định dạng có schema evolution tường minh.

### 4.3. Thêm, bỏ và đổi tên component

Đây là những trường hợp cần xem xét khi record được dùng làm persisted object:

| Thay đổi | Ảnh hưởng thường gặp với Java serialization | Việc cần làm |
|---|---|---|
| Thêm component | Stream cũ thiếu giá trị; runtime dùng default khi khôi phục | Đặt default hợp lệ, kiểm tra canonical constructor |
| Bỏ component | Dữ liệu tương ứng từ stream cũ không còn component để nhận | Xác định có mất dữ liệu nghiệp vụ quan trọng không |
| Đổi tên component | Giống bỏ tên cũ và thêm tên mới từ góc độ ánh xạ dữ liệu | Viết migration/adapter nếu cần giữ giá trị |
| Đổi kiểu component | Có thể không khớp mô tả field/type của stream | Kiểm thử deserialization, ưu tiên schema migration tường minh |
| Thay validation | Stream trước đây được chấp nhận có thể bị từ chối | Chuẩn hóa dữ liệu hoặc bổ sung backward-compatible policy |
| Thay nested object | Component chứa object khác có rules serialization riêng | Kiểm tra toàn bộ object graph và class tương ứng |

Với dữ liệu lâu dài, đừng xem record component name là chi tiết implementation có thể đổi tùy ý. Trong nhiều serializer khác, component name còn được dùng như JSON property hoặc schema field name.

### 4.4. Record không sử dụng các serialization hooks của class thường theo cùng cách

Đối với class Serializable thông thường, developer có thể định nghĩa các special methods như:

- `private void writeObject(ObjectOutputStream out)`
- `private void readObject(ObjectInputStream in)`
- `private void readObjectNoData()`

Record có cơ chế tuần tự hóa riêng. Những hooks thay đổi cách ghi/đọc field thông thường không cung cấp cách tùy biến serialization của record như chúng làm với class thường. Tương tự, không nên kỳ vọng `serialPersistentFields` định nghĩa lại những thành phần record được ghi vào stream.

Ví dụ **không nên dùng** như chiến lược bỏ một record component:

```java
import java.io.IOException;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public record SessionRecord(
        String userId,
        String temporaryToken)
        implements Serializable {

    // Không coi hook kiểu class Serializable thường này
    // là cách loại temporaryToken khỏi record serialization.
    private void writeObject(ObjectOutputStream out)
            throws IOException {
        out.defaultWriteObject();
    }
}
```

Để không ghi token, hãy thiết kế record DTO chỉ chứa `userId` hoặc dùng một serializer/schema mapping riêng. Những giá trị bí mật không nên xuất hiện trong persisted DTO chỉ vì object domain đang có field đó.

`writeReplace` và `readResolve` có các quy tắc riêng và có thể hỗ trợ mô hình replacement/proxy trong Java Object Serialization; nếu cần dùng, hãy đối chiếu hợp đồng của runtime đích và kiểm thử cụ thể thay vì giả định mọi callback của class thường hoạt động tương tự.

### 4.5. `serialVersionUID` của record có ngoại lệ riêng

Với class Serializable thông thường, `serialVersionUID` là một phần quan trọng để đối chiếu phiên bản của serialized class. Với record, Java Object Serialization có **quy tắc đặc biệt**: serialVersionUID mặc định của record là `0L` nếu không khai báo tường minh, và yêu cầu khớp serialVersionUID trong deserialization được nới lỏng đối với record class.

Có thể khai báo UID cho record:

```java
import java.io.Serializable;

public record InvoiceLine(
        String sku,
        long quantity)
        implements Serializable {

    private static final long serialVersionUID = 1L;
}
```

Nhưng **đặt cùng UID không giải quyết mọi thay đổi component**, và việc nới lỏng UID cũng không bảo đảm record đã thay đổi vẫn khôi phục đúng dữ liệu. Constructor validation, tên/type component và nested graph vẫn phải được kiểm thử.

Đối với persisted data, cần một kế hoạch schema evolution rõ, thay vì xem serialVersionUID là nút “bật tương thích”.

### 4.6. Record không có zero-argument constructor mặc định phục vụ deserialize

Vì canonical constructor nhận các component và được gọi để khôi phục record, Java Object Serialization của record không yêu cầu một public no-arg constructor theo kiểu nhiều JavaBean serializer hoặc ORM cổ điển.

Tuy nhiên, **JSON mapper, JPA provider và framework bên thứ ba có thể có quy tắc constructor khác**. Việc record tương thích với `ObjectInputStream` không có nghĩa mọi framework đều đọc/ghi record được trên mọi phiên bản.

### 4.7. Aliasing và object graph có chu trình

Đối với một object graph bình thường, Java serialization có cơ chế handle/reference để lưu quan hệ tham chiếu. Nhưng record cần được dựng qua canonical constructor, nên các vòng tham chiếu liên quan đến record và object đang được xây dựng có những giới hạn đáng chú ý.

Ví dụ một list có thể tham chiếu tới record chứa nó:

```java
import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

record ContainerRecord(List<Object> elements)
        implements Serializable {
}

List<Object> list = new ArrayList<>();
ContainerRecord container = new ContainerRecord(list);
list.add(container);
```

Object graph này chứa cycle: record -> list -> record. Không nên mặc định quá trình serialize/deserialize sẽ bảo toàn mọi vòng tham chiếu liên quan record như đối với các class mutable thông thường. Khi hệ thống cần lưu graph có cycles, hãy thiết kế ID/reference rõ ràng hoặc sử dụng định dạng/mô hình phù hợp và test chính xác.

Một DTO có cấu trúc cây không chu trình thường dễ kiểm thử, dễ versioning và ít phụ thuộc vào chi tiết JVM hơn.

## 5. Ví dụ end-to-end: serialize và deserialize một record

### 5.1. Khai báo enum và record

```java
import java.io.Serializable;
import java.util.Objects;

enum PaymentState {
    CREATED,
    APPROVED,
    REJECTED
}

record PaymentSnapshot(
        String paymentId,
        long amountMinor,
        PaymentState state)
        implements Serializable {

    private static final long serialVersionUID = 1L;

    public PaymentSnapshot {
        Objects.requireNonNull(paymentId, "paymentId");
        Objects.requireNonNull(state, "state");

        if (amountMinor < 0) {
            throw new IllegalArgumentException(
                "amountMinor must not be negative"
            );
        }
    }
}
```

`PaymentState` không cần tự khai báo `implements Serializable` vì enum có cơ chế serialization được Java định nghĩa. Record `PaymentSnapshot` vẫn phải implements `Serializable` để được ghi qua `ObjectOutputStream`.

### 5.2. Ghi và đọc byte stream nội bộ

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;

public final class RecordSerializationDemo {
    public static void main(String[] args) throws Exception {
        PaymentSnapshot before = new PaymentSnapshot(
            "PAY-2026-001",
            150_000,
            PaymentState.APPROVED
        );

        byte[] bytes;

        try (ByteArrayOutputStream buffer =
                 new ByteArrayOutputStream();
             ObjectOutputStream output =
                 new ObjectOutputStream(buffer)) {

            output.writeObject(before);
            output.flush();
            bytes = buffer.toByteArray();
        }

        PaymentSnapshot after;

        // Chỉ đọc dữ liệu vừa tạo trong cùng chương trình,
        // không phải luồng byte từ nguồn không tin cậy.
        try (ObjectInputStream input =
                 new ObjectInputStream(
                     new ByteArrayInputStream(bytes))) {

            Object value = input.readObject();

            if (!(value instanceof PaymentSnapshot snapshot)) {
                throw new IllegalStateException(
                    "Unexpected serialized type"
                );
            }

            after = snapshot;
        }

        System.out.println(before);
        System.out.println(after);
        System.out.println("Equal: " + before.equals(after));
    }
}
```

Ví dụ minh họa cơ chế Object Serialization cho record và enum. Trong sản phẩm thực tế, hãy quản lý dữ liệu không tin cậy và không dùng stream native của Java làm API wire format mặc định chỉ vì cách viết ngắn.

### 5.3. Giải thích khi khôi phục

Khi đọc object:

1. Runtime xác định lớp `PaymentSnapshot` theo stream descriptor và class khả dụng.
2. Các giá trị record components được giải mã.
3. Canonical constructor của record được gọi với những giá trị đó.
4. Validation trong constructor có thể chấp nhận hoặc từ chối dữ liệu.
5. Component `state` được khôi phục theo quy tắc riêng của enum.

Điểm thứ ba quan trọng với invariant: object record không được coi là một “túi field” để khôi phục bỏ qua constructor. Nếu canonical constructor yêu cầu `paymentId` không null, một stream bị lỗi hoặc một stream cũ thiếu dữ liệu có thể dẫn đến lỗi deserialization.

## 6. Enum: cơ chế Java Serialization khác object thông thường

### 6.1. Enum constant là một singleton do runtime quản lý

Ví dụ:

```java
public enum FulfillmentStatus {
    CREATED,
    PICKED,
    DISPATCHED,
    DELIVERED
}
```

Mỗi constant là một instance được tạo và quản lý theo cơ chế của enum class. Khi Java Object Serialization ghi enum, nó không tuần tự hóa toàn bộ các instance field như với object thường. Nó sử dụng **tên enum constant** cùng thông tin kiểu cần thiết để xác định constant khi đọc lại.

Tại thời điểm deserialization, giá trị được khôi phục bằng constant của enum class hiện tại. Điều này giữ đặc tính identity của enum: cùng constant có thể so sánh bằng `==`.

### 6.2. Enum được ghi theo tên, không theo ordinal

Ví dụ:

```java
enum Status {
    NEW,
    RUNNING,
    DONE
}
```

Nếu một object stream ghi `Status.RUNNING`, dạng biểu diễn đặc biệt của enum dựa vào tên constant `RUNNING`, **không phải `ordinal() == 1`**.

Nếu phiên bản sau chèn constant mới:

```java
enum Status {
    NEW,
    QUEUED,
    RUNNING,
    DONE
}
```

`RUNNING.ordinal()` thay đổi từ 1 sang 2, nhưng Java Object Serialization vẫn có thể tìm `RUNNING` theo tên ở enum mới.

**Không nên suy rộng điều này sang database hoặc JSON.** Một JPA mapping dạng ordinal hoặc một JSON serializer cấu hình serialize số có thể bị ảnh hưởng khi thứ tự constant thay đổi.

### 6.3. Khi đổi tên hoặc xóa enum constant

Giả sử stream cũ chứa `Status.RUNNING` nhưng enum runtime mới chỉ có:

```java
enum Status {
    NEW,
    IN_PROGRESS,
    DONE
}
```

Việc đổi tên khiến tên `RUNNING` không còn được runtime nhận diện. Java Object Deserialization không tự biết rằng `IN_PROGRESS` là tên thay thế; đọc giá trị cũ có thể thất bại với lỗi về constant không tồn tại.

Nếu dữ liệu lịch sử cần được đọc, nên dùng một trong các chiến lược:

- Giữ constant cũ trong một giai đoạn tương thích.
- Chuyển dữ liệu đã lưu sang định dạng có stable code trước khi đổi tên.
- Dùng một lớp DTO hoặc serialization proxy có ánh xạ version rõ ràng.
- Chạy migration dữ liệu ngoại tuyến có kiểm tra và rollback.

Không đơn giản đổi `name()` hoặc enum constant rồi kỳ vọng Object Serialization tự chuyển alias.

### 6.4. Khi thêm enum constant

Thêm constant mới thường không ngăn **runtime mới** đọc stream cũ chứa những constant còn tồn tại. Nhưng nếu producer mới bắt đầu gửi constant mới cho consumer cũ, consumer cũ không có tên đó và có thể không deserialize được.

Ví dụ:

```text
Producer v1: NEW, RUNNING, DONE
Consumer v1: NEW, RUNNING, DONE

Producer v2: NEW, QUEUED, RUNNING, DONE
Consumer v1: NEW, RUNNING, DONE
                         ^
                không nhận diện QUEUED
```

Đây là vấn đề forward compatibility: consumer cũ không thể hiểu giá trị mới chỉ vì enum mới binary-compatible với mã được biên dịch trước. Với protocol có producer/consumer được deploy lệch phiên bản, hãy dùng biểu diễn mở có `UNKNOWN` hoặc giữ raw value tùy framework, không truyền trực tiếp enum native serialization nếu cần xử lý các giá trị trong tương lai.

### 6.5. Các field phụ của enum không được serialize như field thường

Enum có thể giữ metadata:

```java
public enum ShippingMethod {
    STANDARD("STD", 3),
    EXPRESS("EXP", 1);

    private final String code;
    private final int estimatedDays;

    ShippingMethod(String code, int estimatedDays) {
        this.code = code;
        this.estimatedDays = estimatedDays;
    }

    public String code() {
        return code;
    }

    public int estimatedDays() {
        return estimatedDays;
    }
}
```

Trong Java Object Serialization, stream của enum biểu diễn constant; nó **không lưu lại một bản copy độc lập của `code` và `estimatedDays`** như object thông thường. Khi đọc ở runtime mới, metadata đến từ định nghĩa enum hiện hành.

Nếu phiên bản mới đổi `EXPRESS` từ 1 ngày sang 2 ngày, stream cũ chứa `EXPRESS` khi đọc ở runtime mới sẽ dùng metadata của constant hiện tại. Nếu cần lưu snapshot về giá tại thời điểm giao dịch, hãy serialize **giá trị snapshot** trong record/DTO riêng chứ không trông chờ field của enum giữ dữ liệu lịch sử.

### 6.6. Enum có các quy tắc custom serialization rất hạn chế

Các serialization methods như `writeObject`, `readObject`, `readResolve`, `writeReplace` và khai báo `serialVersionUID` không được sử dụng để thay đổi dạng serialized enum theo cách của class thông thường. Java quy định cơ chế serialization dành riêng cho enum, với serialVersionUID cố định cho kiểu enum.

Nếu cần kiểm soát wire representation, hãy đặt enum vào một DTO có stable code hoặc dùng serializer ngoài với contract rõ ràng. Không dùng một trick `readResolve` trong enum để đổi tên constant cũ trong Java Object Serialization.

## 7. So sánh record, enum và class Serializable thường

| Khía cạnh | Class Serializable thường | Record implements Serializable | Enum |
|---|---|---|---|
| Cần khai báo Serializable? | Có | Có | Cơ chế enum đã hỗ trợ |
| Đơn vị dữ liệu chính | Serializable instance fields | Record components | Tên enum constant |
| Constructor khi deserialize | Không gọi constructor của chính class Serializable theo cách thông thường | Gọi canonical constructor | Trả về enum constant đã tồn tại |
| `serialVersionUID` | Kiểm tra version theo quy tắc thông thường | Có quy tắc riêng và nới lỏng yêu cầu khớp | Quy tắc cố định của enum |
| Custom `writeObject/readObject` | Có thể được áp dụng khi đúng chữ ký | Không phải cơ chế tùy biến record components | Không dùng để thay đổi enum serialization |
| Thêm dữ liệu | Có field evolution rules | Component thiếu trong stream nhận default rồi qua constructor | Thêm constant mới ảnh hưởng consumer cũ nếu nhận giá trị đó |
| Đổi tên | Field rename cần migration | Component rename cần migration | Constant rename không có alias tự động |
| Object graph | Có xử lý handle/reference và cycle thông thường | Cần lưu ý giới hạn với cycle liên quan constructor | Constant identity được giữ theo enum |
| Dùng làm wire format mở lâu dài | Cần quản lý chặt, thường không khuyến nghị | Cần quản lý chặt, thường không khuyến nghị | Cần quản lý chặt, thường không khuyến nghị |

Bảng thể hiện **quy tắc Java Object Serialization**, không mô tả trực tiếp cơ chế của Jackson, JAXB, Hibernate hay Protobuf.

## 8. Tương thích khi chuyển một class thường thành record

### 8.1. Đổi cú pháp không đồng nghĩa giữ nguyên serialized form

Giả sử class cũ:

```java
import java.io.Serializable;

public final class UserProfile implements Serializable {
    private static final long serialVersionUID = 7L;

    private String id;
    private String displayName;

    public UserProfile(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Developer có thể muốn thay bằng:

```java
import java.io.Serializable;

public record UserProfile(
        String id,
        String displayName)
        implements Serializable {
}
```

Ở mức API, nhiều nơi phải chuyển từ `getId()` sang `id()`. Ở mức bytecode, class record có cấu trúc khác; code cũ đã biên dịch tham chiếu getters hoặc constructor/method đã bị xóa có thể không còn liên kết được. Ở mức Object Serialization, runtime cũng áp dụng rules của record khác với class thông thường.

Ngay cả khi tên class và tên dữ liệu có vẻ giống nhau, **không thể kết luận stream cũ chắc chắn tương thích với record mới**. Hãy dùng một corpus dữ liệu cũ và thử đọc với đúng class mới trong môi trường đích.

### 8.2. Hợp đồng constructor có thể làm dữ liệu cũ không hợp lệ

Class thường có thể được khôi phục mà không chạy constructor của chính nó. Record canonical constructor được gọi khi khôi phục.

Nếu record mới đặt invariant:

```java
public record UserProfile(
        String id,
        String displayName)
        implements java.io.Serializable {

    public UserProfile {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException(
                "displayName must not be blank"
            );
        }
    }
}
```

thì dữ liệu cũ có `displayName` null hoặc rỗng sẽ bị từ chối. Đây có thể là điều đúng về nghiệp vụ, nhưng phải được xử lý trong kế hoạch migration, ví dụ chuẩn hóa trước khi đổi format hoặc ánh xạ vào DTO trung gian có policy rõ.

### 8.3. Source, binary, data và behavioral compatibility

| Mức | Câu hỏi khi đổi class thành record |
|---|---|
| Source compatibility | Mã gọi getters/setters, subclass, no-arg constructor còn biên dịch không? |
| Binary compatibility | Artifact cũ liên kết được với methods, constructors và class mới không? |
| Serialized-data compatibility | Byte stream cũ có thể khôi phục vào kiểu mới đúng giá trị không? |
| Behavioral compatibility | Invariants, equality, normalization và mutability có thay đổi không? |
| Framework compatibility | JSON mapper, ORM, DI, proxy/bytecode library có hỗ trợ record của JDK đích không? |

Một lần refactor POJO thành record có thể tốt cho tính rõ ràng của model nhưng vẫn là thay đổi hợp đồng lớn đối với các consumer chưa nâng cấp.

### 8.4. Phương án chuyển đổi an toàn

Nếu hệ thống đã lưu hàng triệu object stream bằng class cũ, một phương án ít rủi ro là:

1. Giữ khả năng đọc stream legacy bằng một phiên bản ứng dụng hoặc converter tương thích.
2. Đọc dữ liệu trong môi trường tin cậy, áp dụng validation và migration rules.
3. Xuất lại dưới dạng schema-based DTO như JSON/Avro/Protobuf hoặc format ổn định có version.
4. Xác nhận readback, checksum/record count và giá trị nghiệp vụ.
5. Chuyển ứng dụng mới sang record domain model, nhưng không nhất thiết lưu trực tiếp record bằng native serialization.
6. Giữ rollback và chiến lược xử lý artifact chưa chuyển đổi.

Nếu chỉ có một lượng nhỏ byte stream lưu cục bộ và tất cả consumer triển khai đồng bộ, có thể thử trực tiếp compatibility bằng integration tests. Nhưng cần bằng chứng cụ thể, không dựa vào giả định có cùng tên class.

## 9. JSON: enum representation có thể khác hẳn Java serialization

### 9.1. Các cách biểu diễn enum trong JSON

Cùng một enum:

```java
enum PaymentStatus {
    PENDING,
    SETTLED,
    REVERSED
}
```

Một JSON serializer có thể ghi dưới dạng string:

```json
{
  "status": "SETTLED"
}
```

Một serializer khác có thể được cấu hình ghi ordinal:

```json
{
  "status": 1
}
```

Hoặc API dùng stable business code:

```json
{
  "status": "S"
}
```

Ba dạng trên có compatibility rules khác nhau. Không có quy tắc “mọi thư viện JSON serialize enum như Java Object Serialization”. Phải xem cấu hình cụ thể: annotation, converter, serializer module và version library.

### 9.2. JSON name representation có rủi ro đổi tên constant

Nếu JSON dùng tên enum, thêm constant mới có thể làm consumer cũ từ chối giá trị mới. Đổi tên constant có thể làm dữ liệu cũ không parse được. Nếu JSON dùng ordinal, việc thay đổi thứ tự constant còn nguy hiểm hơn vì có thể **âm thầm chuyển nghĩa**.

Hãy ưu tiên stable wire code khi đây là public API:

```java
public enum PaymentStatus {
    PENDING("P"),
    SETTLED("S"),
    REVERSED("R");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }
}
```

Sau đó dùng serializer/converter phù hợp để map từ `code` sang field JSON. Không tự giả định chỉ cần có method `code()` thì JSON mapper sẽ dùng nó.

### 9.3. Xử lý enum value chưa biết

Với producer và consumer deploy lệch phiên bản, cần chính sách khi gặp:

```json
{
  "status": "UNDER_REVIEW"
}
```

Một consumer cũ có thể:

- Từ chối và trả lỗi có cấu trúc.
- Map về `UNKNOWN` nếu serializer hỗ trợ và policy cho phép.
- Giữ raw string trong DTO, chờ ứng dụng mới xử lý.
- Bỏ qua trường trong những tình huống không ảnh hưởng nghiệp vụ.

Không nên tự dùng `PENDING` làm fallback cho mọi giá trị mới nếu điều đó có thể khiến giao dịch bị xử lý sai. Với payment, authorization, compliance hoặc order state, fail-safe và logging thường cần thiết hơn việc “parse thành công bằng mọi giá”.

### 9.4. Record trong JSON cần mapper hỗ trợ constructor/components

Ví dụ record:

```java
public record ApiUser(String id, String displayName) {
}
```

Một mapper hiện đại có thể nhận ra record components và gọi canonical constructor để tạo object. Nhưng phiên bản thư viện cũ có thể:

- Chỉ tìm JavaBean getters/setters.
- Yêu cầu no-arg constructor.
- Không nhận biết record component names.
- Xử lý unknown properties khác mặc định.
- Áp dụng annotation hoặc naming strategy khác giữa các phiên bản.

Khi nâng JDK và framework đồng thời, hãy kiểm thử JSON read/write với đúng mapper và cấu hình, không dựa vào việc `record` có thể compile.

### 9.5. Null, missing và default trong JSON

Cần phân biệt:

```json
{}
```

và:

```json
{"displayName": null}
```

và:

```json
{"displayName": ""}
```

Cách mapper truyền giá trị thiếu hoặc null vào canonical constructor có thể phụ thuộc cấu hình và kiểu component. Với primitive `int` hoặc `boolean`, parser có thể áp dụng default, từ chối thiếu dữ liệu hoặc có quy tắc coercion riêng.

Hãy định nghĩa contract JSON rõ ràng: field bắt buộc, nullable, default hợp lệ, unknown fields được bỏ qua hay từ chối. Sau đó viết test tương ứng.

## 10. JPA và database: enum ordinal là một rủi ro riêng

### 10.1. `EnumType.ORDINAL`

Một mapping JPA có thể chọn:

```java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
```

Khi đó provider thường lưu vị trí enum trong khai báo thành một số. Ví dụ:

```java
enum OrderStatus {
    CREATED,   // 0
    PAID,      // 1
    SHIPPED    // 2
}
```

Nếu phiên bản sau chèn `CANCELLED` vào giữa:

```java
enum OrderStatus {
    CREATED,   // 0
    CANCELLED, // 1
    PAID,      // 2
    SHIPPED    // 3
}
```

Dữ liệu database cũ có giá trị 1 từng nghĩa là `PAID`, nay có nguy cơ được đọc thành `CANCELLED`. Đây là lỗi dữ liệu âm thầm và nghiêm trọng hơn một exception ngay lập tức.

Lưu ý: đoạn annotation trên phụ thuộc vào JPA API của dự án; tên package có thể khác theo phiên bản Jakarta Persistence/Java EE. Ví dụ chỉ nhằm chỉ ra sự khác biệt về mapping, không phải một class entity hoàn chỉnh.

### 10.2. `EnumType.STRING`

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

Dạng string tránh phụ thuộc vào ordinal nhưng vẫn liên kết dữ liệu với **tên constant**. Đổi tên `PAID` thành `SETTLED` có thể phá vỡ dữ liệu hoặc query cũ.

Nếu giá trị được lưu dài hạn và cần rename API tự do, nên dùng converter tới stable business code:

```text
CREATED  -> "C"
PAID     -> "P"
SHIPPED  -> "S"
```

Converter có thể dùng `AttributeConverter` của JPA/Jakarta Persistence, với chính sách rõ cho code chưa biết. Hãy kiểm thử migration schema và backfill trước khi sửa enum trong application.

### 10.3. Record và ORM

Nhiều ORM cần entity có lifecycle, identity, constructor và khả năng tạo proxy. Record là final và components của nó không cho phép gán lại reference, nên không nên mặc định một record có thể thay thế trực tiếp mọi mutable JPA entity.

Thay vào đó, có thể dùng record làm **projection, query result hoặc DTO** nơi framework hỗ trợ, còn entity vẫn dùng cấu trúc phù hợp với ORM. Quyết định phải dựa vào phiên bản framework và yêu cầu lifecycle/dirty checking.

## 11. Avro, Protocol Buffers và schema evolution

### 11.1. Không đồng nhất Java enum với protocol enum

Một Java enum có constant names, còn Protocol Buffers enum có **numeric values** trong schema. Những số đó thuộc wire contract và cần được quản lý độc lập với `ordinal()` của enum Java được sinh ra.

Ví dụ khái niệm:

```proto
enum PaymentStatus {
  PAYMENT_STATUS_UNSPECIFIED = 0;
  PAYMENT_STATUS_PENDING = 1;
  PAYMENT_STATUS_SETTLED = 2;
}
```

Nếu thêm một giá trị, cần cấp **mã số mới ổn định**. Không tái sử dụng những field number hoặc enum numeric value đã có ý nghĩa khác trong dữ liệu lịch sử; nên dùng cơ chế reserved của schema khi loại bỏ.

Các thư viện Protobuf có quy tắc riêng cho unknown enum values tùy ngôn ngữ, cú pháp schema và phiên bản runtime. Không suy ra rằng chúng sẽ ném lỗi hay tự map thành `null` như Java Object Serialization.

### 11.2. Avro dùng writer và reader schema

Trong Avro, khả năng đọc dữ liệu phụ thuộc việc phân giải writer schema của bản ghi với reader schema của consumer. Record field default và enum symbol/default có những quy tắc được định nghĩa bởi Avro, không phải quy tắc canonical constructor của Java record.

Nếu ứng dụng phát hành Avro schema mới, hãy dùng schema compatibility checks và thử đọc bằng reader schema cũ/mới. Một class Java chuyển thành `record` không tự thay đổi hay bảo đảm tương thích của Avro wire schema.

### 11.3. Phân tách domain model và wire schema

Một chiến lược bền vững:

```text
Domain model (record/enum)
          |
          v
Explicit mapping / validation
          |
          v
Versioned wire DTO / schema
          |
          v
JSON / Avro / Protobuf / database
```

Tách hai lớp cho phép:

- Refactor tên record components mà không phá API public ngay.
- Dùng stable field name/code ở wire format.
- Xử lý enum value chưa biết.
- Thêm default trong schema một cách có chủ đích.
- Dùng record ở domain nhưng giữ model phù hợp với ORM.
- Chuyển dữ liệu lịch sử có versioning và rollback.

## 12. Những thay đổi cần kiểm tra riêng khi nâng JDK

### 12.1. Record không có trên JDK 8 như một language feature

Record trở thành tính năng chính thức ở Java 16. Nếu một thư viện bắt đầu phát hành bytecode chứa record class, runtime cũ như JDK 8 hoặc 11 không thể tự hiểu và chạy binary đó chỉ vì các field mang tên quen thuộc.

Khi xây thư viện được nhiều service sử dụng, cần xác định JDK tối thiểu của consumer. Không thể dùng `javac --release 8` để biên dịch source dùng cú pháp `record`. Nếu phải hỗ trợ Java 8, cần một model source khác hoặc tách artifact tương ứng với runtime support matrix.

### 12.2. Java serialization stream không phải Java source compatibility

Một record mới chạy tốt trên JDK 21 có thể không deserialize được dữ liệu của class cũ hoặc không thể được đọc bởi một service JDK 8. Có nhiều tầng:

- Source feature và `javac --release`.
- Class-file version.
- Classpath/module visibility.
- Java serialization descriptor và object graph.
- Invariant trong canonical constructor.
- Serialization filter và chính sách bảo mật.
- Format của dữ liệu trong cache, file hoặc message broker.

Một test compile thành công chỉ xác minh tầng đầu tiên; không chứng minh dữ liệu đã lưu tương thích.

### 12.3. Java Object Serialization vẫn tồn tại nhưng cần cân nhắc bảo mật

Không nhất thiết JDK mới làm Object Serialization biến mất ngay lập tức. Tuy nhiên, đây là cơ chế có rủi ro khi đọc stream không tin cậy. Java đã bổ sung cơ chế lọc deserialization trong các bản JDK hiện đại, ví dụ `ObjectInputFilter`, để kiểm soát graph/class được nhận.

Nếu bắt buộc đọc stream từ nguồn không hoàn toàn tin cậy, cần có allowlist class và giới hạn như depth, references, array size, bytes, đồng thời đánh giá mọi thư viện có mặt trên classpath. Filter không phải phép thay thế cho kiểm soát nguồn dữ liệu và mô hình protocol an toàn.

Với public network APIs mới, tốt hơn nên dùng định dạng dữ liệu có schema được kiểm soát và validation rõ, không cho người gửi yêu cầu runtime tự tạo graph object bất kỳ theo class name.

## 13. Rủi ro dữ liệu khi enum, record và version triển khai không đồng bộ

### 13.1. Producer mới, consumer cũ

Một service mới có:

```java
enum OrderState {
    CREATED,
    PAID,
    SHIPPED,
    RETURNED
}
```

Consumer cũ chỉ có ba constant đầu. Nếu nhận dữ liệu mới mang `RETURNED`:

- Java Object Serialization của enum có thể không khôi phục được vì constant name không tồn tại.
- JSON parser có thể từ chối hoặc dùng unknown policy của serializer.
- Database ORDINAL có nguy cơ map sai tùy vị trí.
- Protobuf/Avro có cơ chế unknown/default riêng.
- Switch expression exhaustive đã biên dịch cũ có thể gặp fallback error nếu runtime code nhận enum constant mới trong cùng JVM.

Mỗi định dạng cần test riêng. Không có một “quy tắc thêm enum constant an toàn” áp dụng mọi nơi.

### 13.2. Consumer mới, dữ liệu cũ

Một record có component mới có thể nhận giá trị default khi đọc stream cũ; constructor có thể từ chối default. Một JSON mapper có thể không cho thiếu property; Avro có thể dùng schema default; protobuf có thể phân biệt field presence theo schema và syntax.

Hãy tạo **golden test data** từ các phiên bản đang triển khai, thay vì tự tạo dữ liệu giả bằng phiên bản code mới rồi cho rằng nó đại diện cho dữ liệu cũ.

### 13.3. Dữ liệu vẫn tồn tại sau rollback

Trong canary, producer mới có thể ghi enum constant hoặc record field mới vào database/cache/message. Khi rollback consumer về bản cũ, bản cũ có thể không đọc được dữ liệu vừa ghi.

Vì vậy, kế hoạch rollback phải trả lời:

1. Phiên bản cũ có thể đọc dữ liệu do bản mới ghi không?
2. Nếu không, có thể trì hoãn phát hành giá trị mới đến khi mọi consumer đã nâng không?
3. Có cần bước expand-then-contract cho schema không?
4. Có thể chuyển đổi ngược dữ liệu an toàn không?
5. Message replay hoặc restore backup có cần tool migration không?

Rollback binary không bảo đảm rollback được trạng thái dữ liệu.

## 14. Thiết kế stable code cho enum

### 14.1. Không dùng `ordinal()` làm mã dài hạn

Nếu protocol/database cần mã ổn định, gắn code độc lập với thứ tự khai báo:

```java
import java.util.Arrays;
import java.util.Optional;

public enum OrderState {
    CREATED("C"),
    PAID("P"),
    SHIPPED("S");

    private final String code;

    OrderState(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static Optional<OrderState> fromCode(String raw) {
        return Arrays.stream(values())
            .filter(value -> value.code.equals(raw))
            .findFirst();
    }
}
```

Trong bản mới, có thể chèn enum constant ở vị trí bất kỳ mà không làm thay `C`/`P`/`S`. Tuy nhiên, mã mới phải được công bố và consumer cũ vẫn cần chính sách khi gặp một code chưa biết.

### 14.2. Preserve raw value nếu cần forward compatibility

Một DTO có thể lưu giá trị gốc:

```java
import java.util.Optional;

public record ParsedOrderState(
        String rawCode,
        Optional<OrderState> knownState) {

    public static ParsedOrderState parse(String raw) {
        return new ParsedOrderState(
            raw,
            OrderState.fromCode(raw)
        );
    }
}
```

Nếu nhận `"R"` khi bản code cũ chỉ có `C`/`P`/`S`, `knownState` là `Optional.empty()` nhưng `rawCode` vẫn được giữ để log, pass-through hoặc replay.

Lưu ý: đây là một **domain/parser DTO**, không phải wire schema tự động. Tùy serializer, `Optional` có thể cần converter riêng; không nên xuất thẳng một record chứa `Optional` ra JSON hay Java Object Serialization mà chưa kiểm tra hỗ trợ. Khi làm persisted wire DTO, có thể đơn giản chỉ lưu `rawCode`, rồi parse vào domain ở ranh giới ứng dụng.

### 14.3. Invariant và unknown policy

Nếu nghiệp vụ liên quan tiền hoặc phân quyền, nhận raw code chưa biết nên thường từ chối thao tác nguy hiểm, nhưng vẫn có thể lưu raw value và metric để xử lý sau. Nếu giá trị chỉ dùng hiển thị nhãn, một fallback “Unknown” có thể chấp nhận được.

Không nên gộp các enum chưa biết thành một trạng thái cụ thể như `PAID` hoặc `APPROVED` để làm code khỏi lỗi. Fallback phải phản ánh ý nghĩa nghiệp vụ.

## 15. Quản lý phiên bản schema của record

### 15.1. Thêm field không tự động an toàn

Giả sử record API v1:

```java
record AccountEvent(
        String accountId,
        String action)
        implements java.io.Serializable {
}
```

V2 thêm:

```java
record AccountEvent(
        String accountId,
        String action,
        long occurredAtEpochMillis)
        implements java.io.Serializable {
}
```

Khi nhận stream cũ thiếu component mới, giá trị primitive mặc định có thể là `0L`. Nhưng trong nghiệp vụ, `1970-01-01T00:00:00Z` có thể không phải thời điểm hợp lệ.

Giải pháp:

- Quy định ý nghĩa của giá trị thiếu và điều kiện chấp nhận nó.
- Có constructor normalization nếu default hợp lệ.
- Nếu không thể suy ra giá trị chính xác, dùng schema version và migration tool.
- Đối với event được ghi lâu dài, cân nhắc biểu diễn optional rõ trong wire schema và không phụ thuộc default primitive của Java Object Serialization.

### 15.2. Đổi tên component không phải đổi nhãn hiển thị

Tên component của record ảnh hưởng source accessor (`accountId()`) và có thể ảnh hưởng field mapping trong nhiều serializer. Nếu chỉ cần đổi tên hiển thị ở UI, đừng đổi tên component dùng trong persistent schema.

Đối với JSON, có thể dùng annotation hoặc adapter để giữ wire property cũ trong khi domain component được đổi tên. Đối với Object Serialization, cần kiểm thử hoặc chuyển đổi dữ liệu cũ qua model trung gian; không có cách chung đảm bảo rename an toàn mà không đổi stream contract.

### 15.3. Validation là một phần của dữ liệu phiên bản mới

Một invariant chặt hơn có thể làm dữ liệu cũ không đọc được. Ví dụ:

```java
record ProductId(String value)
        implements java.io.Serializable {

    public ProductId {
        if (value == null || !value.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException(
                "Invalid ProductId"
            );
        }
    }
}
```

Nếu stream cũ chứa mã có ký tự lowercase hoặc dấu cách, canonical constructor của record mới sẽ từ chối. Trước khi rollout, phải biết có bao nhiêu bản ghi cũ không đáp ứng invariant mới và xử lý bằng migration hoặc backward-compatible normalization có kiểm soát.

## 16. Kiểm thử compatibility theo ma trận phiên bản

### 16.1. Ma trận producer và consumer

| Producer | Consumer | Mục tiêu |
|---|---|---|
| V1 | V1 | Baseline dữ liệu cũ |
| V1 | V2 | V2 có đọc được dữ liệu cũ và áp dụng default đúng không? |
| V2 | V2 | Hành vi bình thường của phiên bản mới |
| V2 | V1 | Có phục vụ rolling deploy hoặc rollback không? |
| Dữ liệu lỗi/không tin cậy | Consumer được bảo vệ | Filter/validation có từ chối an toàn không? |

Mọi tổ hợp không nhất thiết được hỗ trợ trong production, nhưng quyết định phải có trong compatibility contract. Ví dụ nếu V2 ghi enum constant mới mà V1 không hỗ trợ, hệ thống có thể cần triển khai consumer trước và chỉ bật producer sau.

### 16.2. Golden streams phải được tạo bởi phiên bản thật

Để test Java Object Serialization của record/enum:

1. Build một artifact V1 thực tế.
2. Chạy code V1 để tạo byte streams đại diện.
3. Lưu fixture với version, SHA-256 và mô tả object nghiệp vụ.
4. Build artifact V2 riêng.
5. Đọc stream V1 bằng V2 và xác nhận giá trị, invariant, exception policy.
6. Nếu cần rollback, chạy thử V1 đọc stream V2.
7. Thử trường hợp enum constant mới, component thiếu, rename, đổi kiểu và nested objects.
8. Chạy trên JDK đích cùng cấu hình serialization filter.

Không dùng class V2 để tự sinh một stream “mô phỏng V1” chỉ bằng cách bỏ vài field trong JSON nếu bạn cần kiểm tra **Java binary serialization**. Stream descriptor và cơ chế tạo object có thể khác.

### 16.3. Test với enum rename

Test ba điều kiện:

```text
V1 enum:
  NEW, RUNNING, DONE

V2 enum:
  NEW, IN_PROGRESS, DONE
```

- V1 ghi `RUNNING`, V2 cố đọc: có chính sách nào để xử lý tên cũ?
- V2 ghi `IN_PROGRESS`, V1 cố đọc: rollback có cần hỗ trợ không?
- Định dạng ngoài Java dùng `"RUNNING"` hay stable code `"R"`?

Nếu cần giữ wire format, mapping chính thức phải được test. Chỉ đổi constant name trong Java không đủ.

### 16.4. Test constructor normalization

Ví dụ với record thêm component `region`:

- Stream cũ không chứa `region`.
- Stream mới có `region = null`.
- Stream mới có `region = ""`.
- Stream mới có `region = "VN"`.
- Stream mới có field kiểu không tương thích nếu có schema lỗi.
- Stream dữ liệu lớn hoặc nested graph sâu để kiểm tra giới hạn resource.

Kết quả mong đợi phải nêu rõ: normalize, reject, fallback hay migration. Không chỉ assert “không ném exception” nếu dữ liệu được khôi phục sai về nghiệp vụ.

## 17. Kiểm tra dữ liệu ngoài Object Serialization

Đối với JSON:

- [ ] Snapshot JSON V1/V2 có property names như cam kết.
- [ ] Enum được ghi theo string name, stable code hay number?
- [ ] Missing/null/unknown fields có hành vi được định nghĩa.
- [ ] Mapper có hỗ trợ record của phiên bản JDK/framework hiện hành.
- [ ] Unknown enum value không bị map vào trạng thái nguy hiểm.

Đối với database:

- [ ] Mapping enum không phụ thuộc ordinal nếu bảng dữ liệu cần tiến hóa.
- [ ] Tên constant hoặc stable code đã được cố định như database contract.
- [ ] Schema migration/backfill có kiểm thử.
- [ ] Rollback không làm dữ liệu mới được diễn giải sai.
- [ ] ORM hỗ trợ record ở vai trò entity/projection/DTO được lựa chọn.

Đối với Avro/Protobuf:

- [ ] Schema change được kiểm tra theo compatibility mode phù hợp.
- [ ] Field numbers, enum numbers, symbols và defaults được quản lý.
- [ ] Dữ liệu unknown được xử lý theo runtime cụ thể.
- [ ] Producer/consumer rolling deploy và replay được test.

## 18. Bảo mật khi đọc serialized data

### 18.1. Không deserialize object native Java từ nguồn không tin cậy theo mặc định

Java Object Serialization có thể khiến runtime tạo và xử lý những class trên classpath theo stream đầu vào. Một số class có callback, side effect hoặc đường xử lý phức tạp. Nếu ứng dụng nhận byte tùy ý từ network rồi gọi `ObjectInputStream.readObject()`, đây là một ranh giới tấn công đáng chú ý.

Các biện pháp:

- Ưu tiên định dạng có schema/field limits cho public API.
- Nếu bắt buộc dùng Object Serialization, giới hạn nguồn tin cậy.
- Áp dụng `ObjectInputFilter` theo allowlist và resource limits.
- Giới hạn bytes đầu vào, độ sâu graph, số references và array length.
- Không chỉ dựa vào kiểm tra kiểu sau khi `readObject()`, vì phần lớn deserialization đã xảy ra.
- Cập nhật thư viện và kiểm tra các object types trong stream.
- Tách process/container nếu dữ liệu có độ tin cậy thấp nhưng vẫn buộc phải chuyển đổi định dạng cũ.

### 18.2. Kiểm tra kiểu sau đọc vẫn cần nhưng không đủ

```java
Object value = input.readObject();

if (!(value instanceof PaymentSnapshot snapshot)) {
    throw new java.io.InvalidObjectException(
        "Unexpected root type"
    );
}
```

Đoạn kiểm tra root type giúp xác nhận hợp đồng ứng dụng, nhưng nó không thay thế serialization filtering: các object bên trong có thể đã được dựng trước khi code kiểm tra kiểu root được chạy.

### 18.3. ObjectInputFilter cần có policy theo hệ thống

Có thể cấu hình filter trên stream để từ chối loại class hoặc object graph vượt giới hạn. Ví dụ định hướng:

```java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

ObjectInputFilter filter =
    ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1048576;" +
        "com.example.protocol.*;java.base/*;!*"
    );

input.setObjectInputFilter(filter);
```

Đây là **mẫu minh họa cú pháp filter**, không phải policy dùng ngay cho production. Class allowlist, module/package pattern và giới hạn phải được xây theo những class thực sự có thể xuất hiện trong stream và phiên bản JDK đích. Chính sách quá rộng có thể bỏ lọt rủi ro; quá hẹp có thể chặn dữ liệu hợp lệ.

## 19. Quy trình migration đề xuất

### Giai đoạn 1: Kiểm kê nơi dữ liệu được ghi/đọc

Tìm trong source code và configuration:

- `ObjectOutputStream`, `ObjectInputStream`.
- `Serializable`, `Externalizable`, `serialVersionUID`.
- `readObject`, `writeObject`, `readResolve`, `writeReplace`.
- Định dạng file/cache/message được đặt tên theo Java object stream.
- Enum trong JSON, JPA, Avro, Protobuf và custom converter.
- Các record domain/DTO mới được thêm khi nâng JDK.
- Những dịch vụ có thể chạy lệch phiên bản trong rolling deploy.

Một số lệnh tìm kiếm sơ bộ:

```shell
rg -n "Object(Input|Output)Stream|implements Serializable" src
rg -n "serialVersionUID|readObject|writeObject|readResolve|writeReplace" src
rg -n "EnumType\\.(ORDINAL|STRING)|@Enumerated" src
rg -n "\\brecord\\b|\\benum\\b" src
```

Không phải mọi file kết quả đều cần migration. Hãy xác định đường dữ liệu thật, vòng đời retention và giao thức đang dùng.

### Giai đoạn 2: Ghi rõ contract và owner dữ liệu

Với từng loại persisted message hoặc file, lập inventory:

| Loại dữ liệu | Writer hiện tại | Reader hiện tại | Format | Vòng đời | Rủi ro |
|---|---|---|---|---|---|
| Cache session | Service A V1 | Service A V1/V2 | Java Object Serialization | Ngắn | Record/enum class evolution |
| Order event | Producer | Nhiều consumer | JSON/Avro | Dài | Enum unknown, schema compatibility |
| Payment status | ORM | ORM và reporting | DB string/ordinal | Rất dài | Rename/ordinal mismatch |
| Legacy archive | Batch cũ | Converter mới | Java object stream | Nhiều năm | Class không còn, validation mới |
| HTTP response | API | Mobile/web client | JSON | Qua nhiều release | Stable code và unknown behavior |

Xác định compatibility requirements theo chiều đọc dữ liệu cũ, đọc dữ liệu mới và khả năng rollback.

### Giai đoạn 3: Quyết định mô hình chuyển đổi

Một số lựa chọn:

- **Giữ Object Serialization tạm thời:** thích hợp nếu tất cả các bên nằm trong miền kiểm soát nội bộ và có test theo phiên bản.
- **Chuyển sang DTO schema-based:** phù hợp khi dữ liệu lưu dài hạn hoặc nhiều consumer deploy độc lập.
- **Tách domain record khỏi persisted DTO:** phù hợp nếu domain cần invariant chặt còn wire cần backward compatibility.
- **Chuyển enum sang stable codes:** phù hợp khi tên/thứ tự constant dự kiến thay đổi.
- **Chuyển dữ liệu lịch sử ngoại tuyến:** phù hợp khi dữ liệu cũ không thể đọc trực tiếp bằng model mới.

Không cần đồng thời thay toàn bộ định dạng nếu rủi ro rollout quá lớn. Có thể triển khai theo giai đoạn với reader hỗ trợ cả format cũ và mới, sau đó chuyển writer.

### Giai đoạn 4: Thiết lập golden fixtures

Tạo dữ liệu thật từ V1 và V2, lưu thành fixtures cùng thông tin JDK, thư viện, phiên bản schema, checksum và expected values. Kiểm tra trên runtime mục tiêu:

1. Đọc fixture V1 bằng reader V2.
2. Đọc fixture V2 bằng reader V1 nếu cần hỗ trợ rollback.
3. Đọc record thiếu component và constructor defaults.
4. Đọc enum constant bị đổi tên hoặc đã bị loại bỏ.
5. Đọc giá trị enum mới chưa được consumer cũ hỗ trợ.
6. Kiểm tra dữ liệu nested, collection và null.
7. Kiểm tra stream bị lỗi/không tin cậy có bị từ chối an toàn không.

### Giai đoạn 5: Phát hành theo expand-then-contract

Ví dụ với enum status mới:

1. Cập nhật reader các phiên bản đang vận hành để nhận diện hoặc từ chối có chủ đích giá trị mới.
2. Cập nhật metadata/schema và tài liệu API.
3. Phát hành reader trước producer.
4. Bật producer phát giá trị mới sau khi đủ consumer đã sẵn sàng.
5. Theo dõi metric unknown/rejected values.
6. Chỉ bỏ legacy mapping khi không còn dữ liệu hoặc consumer cũ được cam kết hỗ trợ.

Với record schema, có thể thêm default handling trước khi writer bắt đầu ghi component mới. Nếu cần rollback, bảo đảm dữ liệu mới không làm bản cũ hỏng; nếu không thể, ghi rõ giới hạn rollback.

### Giai đoạn 6: Quan sát và dọn dẹp

Sau rollout, theo dõi:

- Deserialization errors theo class/schema/constant.
- Unknown enum values và tỷ lệ reject/fallback.
- Constructor validation failures của record.
- Message backlog/retry/dead-letter queue.
- Cache miss hoặc cache corruption sau upgrade.
- Cơ chế replay và rollback.
- Data migration counts và checksum.

Đừng xóa ngay reader hoặc converter legacy chỉ vì production đã chuyển writer mới. Dữ liệu backup, event replay và consumer ngoại tuyến có thể cần thời gian chuyển đổi lâu hơn.

## 20. Các lỗi thực tế dễ gặp

### Lỗi A: `NotSerializableException` khi ghi record

**Triệu chứng:** `ObjectOutputStream.writeObject` thất bại dù record khai báo `implements Serializable`.

**Nguyên nhân có thể:** một component tham chiếu tới object không serializable, ví dụ native handle hoặc service object.

**Hướng xử lý:** dùng snapshot DTO chỉ chứa dữ liệu có thể ghi, không serialize live resource; hoặc chuyển qua schema DTO với converter tường minh.

### Lỗi B: Deserialization record thất bại sau khi thêm component

**Triệu chứng:** stream cũ có thể đọc được bằng V1 nhưng V2 ném lỗi khi canonical constructor chạy.

**Nguyên nhân:** component mới nhận default (`null`/`0`/`false`) và constructor không chấp nhận.

**Hướng xử lý:** chọn default hợp lệ, migration data hoặc versioned DTO; không chỉ đổi serialVersionUID.

### Lỗi C: Dữ liệu enum cũ không đọc được sau khi rename

**Triệu chứng:** stream còn tên constant cũ nhưng enum runtime đã đổi tên.

**Nguyên nhân:** Java enum serialization dựa trên constant name.

**Hướng xử lý:** giữ compatibility alias trong model/format phù hợp, hoặc chuyển đổi dữ liệu lịch sử trước khi loại tên cũ.

### Lỗi D: Database đọc thành trạng thái sai sau khi chèn constant

**Triệu chứng:** không có exception, nhưng trạng thái đơn hàng bị diễn giải sai.

**Nguyên nhân:** `EnumType.ORDINAL` và thứ tự enum thay đổi.

**Hướng xử lý:** khôi phục mapping, migration dữ liệu có kiểm thử và chuyển sang stable code/string contract nếu thích hợp.

### Lỗi E: JSON mapper không khởi tạo được record

**Triệu chứng:** lỗi thiếu no-arg constructor, creator hoặc property name.

**Nguyên nhân:** phiên bản mapper hoặc cấu hình chưa phù hợp với record.

**Hướng xử lý:** nâng mapper/module, đặt annotation/constructor mapping cần thiết, test round-trip bằng phiên bản runtime chính xác.

### Lỗi F: Producer mới làm consumer cũ lỗi với enum value mới

**Triệu chứng:** deserialization failed, unknown symbol hoặc fallback sai.

**Nguyên nhân:** producer phát giá trị chưa có trong schema/model cũ.

**Hướng xử lý:** reader-first rollout, stable codes, unknown policy và version negotiation khi cần.

### Lỗi G: Rollback code nhưng không rollback được dữ liệu

**Triệu chứng:** V1 được deploy lại nhưng không đọc được event/cache do V2 tạo.

**Nguyên nhân:** dữ liệu đã thay đổi theo schema mới hoặc constant mới.

**Hướng xử lý:** thiết kế backward write compatibility, giữ reader kép hoặc chuyển dữ liệu; không chỉ rollback JAR/container.

### Lỗi H: Cùng class name nhưng dữ liệu không đúng invariant

**Triệu chứng:** object đọc xong nhưng nghiệp vụ sai, hoặc constructor mới từ chối.

**Nguyên nhân:** class evolution không đi kèm data contract, hoặc record constructor thay đổi validation.

**Hướng xử lý:** kiểm thử golden fixtures và xác nhận giá trị nghiệp vụ, không chỉ thử “`readObject()` không ném exception”.

## 21. Checklist hoàn tất

### Record

- [ ] Record cần Java Object Serialization đã khai báo `implements Serializable`.
- [ ] Mọi component chứa dữ liệu có thể serialize hoặc đã có DTO converter thích hợp.
- [ ] Canonical constructor xử lý đúng null/default từ dữ liệu cũ.
- [ ] Đã kiểm tra thêm/bỏ/đổi tên/đổi kiểu component.
- [ ] Không dùng `writeObject/readObject` như cách tùy biến record component serialization.
- [ ] Đã cân nhắc record với mutable nested objects và object graph có cycle.
- [ ] Runtime/JDK tối thiểu của consumer hỗ trợ record class được phát hành.

### Enum

- [ ] Đã xác định format enum theo name, ordinal, stable code hay schema numeric value.
- [ ] Không dùng `ordinal()` làm persisted business code khi schema cần tiến hóa.
- [ ] Đã xác định chính sách cho constant bị đổi tên/xóa.
- [ ] Consumer cũ có chính sách khi producer phát constant mới.
- [ ] Không trông chờ fields/`writeObject` của enum được serialize như object thường.
- [ ] Đã xác nhận metadata hiện hành của enum có phù hợp yêu cầu snapshot lịch sử.

### Dữ liệu và protocol

- [ ] Có inventory mọi nơi ghi/đọc Java object stream, JSON, DB, Avro/Protobuf.
- [ ] Có schema/versioning và owner của persisted contract.
- [ ] Có golden fixtures từ phiên bản writer cũ.
- [ ] Có test producer/consumer lệch phiên bản và rollback.
- [ ] Có validation, unknown-value policy và monitoring.
- [ ] Không nhận object stream native Java từ nguồn không tin cậy mà thiếu kiểm soát.
- [ ] Có lộ trình lưu trữ/chuyển đổi dữ liệu lịch sử.

## 22. Bài tập thực hành

### Bài tập 1: Thêm component vào record

V1:

```java
record Invoice(String id, long cents)
        implements java.io.Serializable {
}
```

V2:

```java
record Invoice(String id, long cents, String currency)
        implements java.io.Serializable {

    public Invoice {
        if (currency == null) {
            currency = "UNKNOWN";
        }
    }
}
```

Hãy tạo stream bằng code V1, đọc bằng code V2, xác nhận `currency` sau khi đọc. Sau đó thay constructor để từ chối null và quan sát khác biệt. Hãy giải thích vì sao lỗi này không thể giải quyết chỉ bằng cách đặt một `serialVersionUID` giống nhau.

### Bài tập 2: Enum và ordinal database

V1:

```java
enum TaskState {
    TODO, IN_PROGRESS, DONE
}
```

Database lưu `IN_PROGRESS` dưới dạng ordinal. V2 chèn `BLOCKED` trước `IN_PROGRESS`. Hãy xác định database cũ bị ảnh hưởng thế nào và thiết kế migration sang stable code có rollback.

### Bài tập 3: Producer mới, consumer cũ

Producer V2 thêm `MANUAL_REVIEW` cho một payment enum. Consumer V1 chưa biết constant này. Hãy thiết kế:

- Chính sách khi consumer đọc Java Object Serialization.
- Chính sách nếu API dùng JSON stable code.
- Thứ tự deploy reader và writer.
- Log/metric cho unknown value.
- Kịch bản rollback khi message mới đã nằm trong queue.

### Bài tập 4: Chuyển legacy object stream

Một batch job từng lưu `LegacyProfile` bằng Java Object Serialization. Đội phát triển muốn chuyển domain model thành record và nâng JDK từ 8 lên 21. Hãy mô tả pipeline:

```text
Legacy reader -> validated DTO -> versioned schema -> new record domain model
```

Nêu nơi test golden fixtures, nơi xử lý dữ liệu lỗi, cách xác minh record count/checksum và cách bảo đảm không mất dữ liệu khi rollback.

## Kết luận

Record và enum có những quy tắc serialization riêng trong Java. **Record** phải triển khai `Serializable` nếu dùng Java Object Serialization; các record components được khôi phục qua canonical constructor, nên validation, default và schema evolution ảnh hưởng trực tiếp đến dữ liệu đã lưu. **Enum** được serialize theo **tên constant**, không phải ordinal, và không dùng cơ chế custom serialization của class thông thường để thay đổi định dạng. Việc thêm, đổi tên hoặc xóa constant có thể phá vỡ các consumer chưa nâng cấp.

Khi migration, cần xác định rõ format thực tế: Java Object Serialization, JSON, JPA, Protobuf hoặc Avro có những hợp đồng khác nhau. Đừng chỉ kiểm tra mã biên dịch thành công; hãy dùng golden data từ phiên bản cũ, thử đọc theo cả hai chiều producer/consumer, kiểm tra canonical constructor và unknown enum values, thiết kế stable code/schema version và giữ kế hoạch rollback dữ liệu. Tách domain record/enum khỏi DTO trên wire hoặc trong database khi cần giúp hệ thống tiến hóa qua các bản JDK và phiên bản dịch vụ mà không âm thầm làm sai dữ liệu nghiệp vụ.

