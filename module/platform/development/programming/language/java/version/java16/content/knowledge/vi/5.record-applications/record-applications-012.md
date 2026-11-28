# Tác động của đổi tên, đổi kiểu và thêm component lên API công khai

Record phù hợp để biểu diễn dữ liệu có cấu trúc ổn định, nhưng component của một public record chính là một phần API mà client nhìn thấy. Tên, kiểu và thứ tự component ảnh hưởng đến accessor, canonical constructor, reflection, `equals`, `hashCode`, `toString`, serialization và record pattern trên các JDK mới. Vì vậy, đổi một component không đơn thuần là sửa tên field nội bộ.

Các record được giới thiệu chính thức trong Java 16 và tiếp tục được hỗ trợ trên các JDK hiện đại. Bài học tập trung vào source compatibility, binary compatibility và tương thích hành vi khi API thay đổi. Record pattern được chuẩn hóa từ Java 21 nên chỉ áp dụng cho client biên dịch bằng JDK 21 trở lên.

## 1. Component của record tạo thành public API

Khai báo:

```java
public record Customer(String id, String name) {
}
```

Tạo ra một record class có các thành phần API chính:

- Hai component `id` và `name`.
- Hai accessor `id()` và `name()`.
- Canonical constructor `Customer(String id, String name)`.
- Các triển khai `equals`, `hashCode` và `toString` dựa trên component.
- Metadata record có thể được đọc bằng `Class.isRecord()` và `Class.getRecordComponents()`.

Record class là `final`, các component được lưu trong field `private final`, và constructor khởi tạo trạng thái của record. Client có thể phụ thuộc trực tiếp vào tên accessor, kiểu trả về, chữ ký constructor hoặc metadata component. Framework cũng có thể đọc component để tạo JSON property, ánh xạ dữ liệu, sinh schema hoặc gọi canonical constructor.

Vì thế, một public record cần được xem như một hợp đồng API. Khi thay đổi component, phải đánh giá ảnh hưởng đến client đã biên dịch, mã nguồn client, dữ liệu đã lưu và framework đang introspect record.

## 2. Phân biệt source compatibility, binary compatibility và behavioral compatibility

Ba khái niệm này giúp mô tả chính xác mức ảnh hưởng của thay đổi:

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ lỗi |
|---|---|---|
| Source compatibility | Mã nguồn client cũ có biên dịch lại với API mới không? | `customer.name()` không còn tồn tại |
| Binary compatibility | File `.class` client đã biên dịch có liên kết và chạy với API mới không? | `NoSuchMethodError` khi accessor hoặc constructor cũ bị xóa |
| Behavioral compatibility | Chương trình còn cho kết quả và dữ liệu như trước không? | `equals()` thay đổi, `toString()` đổi định dạng, JSON field đổi tên |

Một thay đổi có thể giữ binary compatibility nhưng vẫn phá behavioral compatibility. Ngược lại, thêm overload constructor có thể giữ đường gọi binary cũ nhưng metadata record vẫn thay đổi và client dùng reflection vẫn bị ảnh hưởng.

## 3. Đổi tên component

Giả sử phiên bản API đầu tiên công bố:

```java
public record Customer(String id, String name) {
}
```

Client sử dụng accessor:

```java
Customer customer = new Customer("C-100", "Lan");
System.out.println(customer.name());
```

Phiên bản sau đổi `name` thành `displayName`:

```java
public record Customer(String id, String displayName) {
}
```

Thay đổi này tạo ra accessor `displayName()` và không còn accessor được sinh tự động `name()`.

### Ảnh hưởng đến source code

Mã nguồn client gọi `customer.name()` sẽ không biên dịch khi dùng API mới. Client phải đổi thành `customer.displayName()` hoặc dùng một phương thức tương thích mà API cung cấp.

### Ảnh hưởng đến binary đã biên dịch

Tên component không nằm trong JVM method descriptor của canonical constructor. Hai constructor sau có cùng descriptor ở mức bytecode:

```text
Customer(String, String)
```

Vì vậy, nếu chỉ đổi tên component và giữ nguyên kiểu cùng thứ tự, lời gọi canonical constructor cũ vẫn có thể liên kết. Tuy nhiên, accessor thay đổi tên và descriptor của method cũ không còn. Binary client gọi `Customer.name():String` có thể ném `NoSuchMethodError` khi chạy với phiên bản mới.

### Ảnh hưởng đến reflection và framework

`Class.getRecordComponents()` trả về tên mới `displayName`. Framework đọc record metadata có thể sinh property mới, thay đổi JSON key hoặc thay đổi tên tham số khi ánh xạ constructor. Kết quả phụ thuộc framework và cấu hình, nhưng cần coi đây là thay đổi schema công khai.

`toString()` mặc định cũng sử dụng tên component, vì vậy chuỗi hiển thị đổi từ dạng `Customer[id=C-100, name=Lan]` sang `Customer[id=C-100, displayName=Lan]`. Không nên dùng `toString()` của record làm định dạng lưu trữ hoặc giao thức ổn định.

### Cách đổi tên có giữ accessor cũ

Nếu cần giữ client cũ, có thể thêm một phương thức alias với tên cũ:

```java
public record Customer(String id, String displayName) {
    /** @deprecated Dùng displayName() thay thế. */
    @Deprecated(forRemoval = false)
    public String name() {
        return displayName;
    }
}
```

Phương thức `name()` giữ lại chữ ký cũ để source và binary client tiếp tục gọi được. Đây là phương thức thông thường do người viết khai báo, không phải component record. Reflection trên `getRecordComponents()` vẫn chỉ trả về `id` và `displayName`; `toString()` cũng dùng tên component mới.

Nếu constructor giữ nguyên kiểu và thứ tự, descriptor constructor cũ không đổi. Tuy nhiên, alias accessor chỉ giải quyết đường gọi phương thức; nó không làm cho metadata component, JSON schema hoặc serialization tự động trở lại như cũ.

## 4. Đổi kiểu component

Giả sử API cũ:

```java
public record Invoice(String amount) {
}
```

API mới muốn dùng `BigDecimal` để biểu diễn tiền chính xác:

```java
public record Invoice(java.math.BigDecimal amount) {
}
```

Thay đổi kiểu ảnh hưởng trực tiếp đến hai thành phần chính:

- Canonical constructor đổi từ `Invoice(String)` thành `Invoice(BigDecimal)`.
- Accessor đổi từ `String amount()` thành `BigDecimal amount()`.

Vì kiểu tham số và kiểu trả về nằm trong JVM descriptor, binary client cũ gọi constructor hoặc accessor theo chữ ký `String` sẽ không tìm thấy method tương ứng trong API mới nếu không có adapter tương thích. Client source cũng cần điều chỉnh cách tạo và sử dụng giá trị.

### Giữ constructor và accessor cũ bằng component mới có tên khác

Nếu cần một lộ trình migration, có thể đổi component sang tên và kiểu mới, rồi giữ overload constructor cùng phương thức alias:

```java
import java.math.BigDecimal;

public record Invoice(BigDecimal amountValue) {
    public Invoice(String amount) {
        this(new BigDecimal(amount));
    }

    /** @deprecated Dùng amountValue() để nhận BigDecimal. */
    @Deprecated(forRemoval = false)
    public String amount() {
        return amountValue.toPlainString();
    }
}
```

Ví dụ này giữ lại constructor `Invoice(String)` và accessor `amount():String` cho client cũ, trong khi API mới dùng `amountValue():BigDecimal`. Quy tắc chuyển đổi phải được định nghĩa rõ: định dạng chuỗi, rounding, scale và cách xử lý dữ liệu không hợp lệ đều là quyết định nghiệp vụ.

Không thể khai báo hai phương thức Java chỉ khác kiểu trả về nhưng có cùng tên và danh sách tham số. Vì vậy, nếu giữ component tên `amount` nhưng đổi kiểu của nó, không thể đơn giản thêm một accessor `amount()` cũ với kiểu trả về cũ trong source Java. Cần dùng tên component mới và một alias có tên cũ, hoặc phát hành adapter/version API riêng.

### Thay đổi generic type có thể không đổi JVM descriptor

Ví dụ:

```java
public record Batch(java.util.List<String> items) {
}
```

Đổi thành:

```java
public record Batch(java.util.List<java.util.UUID> items) {
}
```

Do generic type bị type erasure, accessor trong cả hai phiên bản có JVM descriptor trả về `List`. Binary linkage có thể vẫn thành công, nhưng hợp đồng kiểu ở source và generic signature đã thay đổi. Client cũ có thể gặp lỗi biên dịch khi build lại hoặc `ClassCastException` khi đọc phần tử và ép kiểu theo giả định cũ.

Do đó, không nên kết luận một thay đổi kiểu là tương thích chỉ vì JVM descriptor tình cờ giữ nguyên. Cần đánh giá generic signature, nullability, quy tắc chuyển đổi và dữ liệu thực tế.

## 5. Thêm component mới

Giả sử phiên bản đầu:

```java
public record Point(int x, int y) {
}
```

Phiên bản sau thêm `z`:

```java
public record Point(int x, int y, int z) {
}
```

Canonical constructor đổi từ `Point(int, int)` thành `Point(int, int, int)`. Nếu không giữ constructor cũ, client source tạo `new Point(10, 20)` sẽ không biên dịch, còn binary cũ gọi descriptor `(II)V` có thể ném `NoSuchMethodError`.

Thêm component cũng tạo accessor mới `z()`, thay đổi danh sách component reflection và đưa `z` vào các phương thức được sinh tự động như `equals`, `hashCode`, `toString`.

### Giữ constructor cũ bằng overload

Nếu giá trị mặc định cho component mới có ý nghĩa rõ ràng, có thể giữ constructor cũ:

```java
public record Point(int x, int y, int z) {
    public Point(int x, int y) {
        this(x, y, 0);
    }
}
```

Client cũ tiếp tục gọi `new Point(10, 20)` nhờ overload hai tham số. Binary cũ cũng có thể liên kết với descriptor constructor `(II)V` được giữ lại. Client mới có thể gọi canonical constructor ba tham số hoặc dùng accessor `z()`.

Giá trị mặc định `0` chỉ hợp lý với ví dụ tọa độ 2D được mở rộng thành 3D khi quy ước `z = 0` có ý nghĩa. Với dữ liệu nghiệp vụ, không nên tự chọn `null`, `0`, chuỗi rỗng hoặc một giá trị mặc định tùy tiện để làm cho constructor cũ tiếp tục hoạt động. Giá trị mặc định phải được định nghĩa trong hợp đồng.

### Constructor overload không giữ nguyên mọi hành vi

Ngay cả khi constructor cũ được giữ, record mới có thêm trạng thái. Hai object trước đây bằng nhau khi có cùng `x` và `y` có thể không còn bằng nhau nếu `z` khác nhau. `hashCode()` và `toString()` cũng thay đổi theo component mới. Client dùng record làm key trong `HashMap` hoặc `HashSet` cần đánh giá lại hành vi.

## 6. Đổi thứ tự component

Thứ tự component là một phần của canonical constructor và metadata record. Ví dụ:

```java
public record Range(int start, int end) {
}
```

Đổi thứ tự thành:

```java
public record Range(int end, int start) {
}
```

Vì hai component cùng kiểu `int`, descriptor constructor vẫn là `(II)V`. Binary client có thể tiếp tục liên kết, nhưng ý nghĩa của hai đối số bị đảo. Lời gọi `new Range(10, 20)` vẫn biên dịch và chạy nhưng trạng thái mang ý nghĩa ngược với trước đó. Đây là behavioral breaking change khó phát hiện vì không nhất thiết có lỗi biên dịch hay linkage.

Nếu hai component khác kiểu, đổi thứ tự thường làm descriptor constructor thay đổi và có thể gây binary incompatibility. Trong cả hai trường hợp, thứ tự trả về từ `getRecordComponents()` và thứ tự component trong record pattern cũng bị ảnh hưởng.

Không nên đổi thứ tự component của public record đã phát hành. Nếu cần biểu diễn dữ liệu mới, hãy cân nhắc tạo kiểu mới có tên rõ ràng hoặc factory method với tên tham số thể hiện ý nghĩa.

## 7. Record pattern làm component shape trở thành hợp đồng source

Record pattern được hoàn thiện trong Java 21. Client có thể destructure record trực tiếp:

```java
record Point(int x, int y) {
}

static int manhattanDistance(Object value) {
    if (value instanceof Point(int x, int y)) {
        return Math.abs(x) + Math.abs(y);
    }
    return -1;
}
```

Nếu record đổi từ hai component thành ba component, mã nguồn dùng pattern `Point(int x, int y)` phải được cập nhật theo shape mới. Tương tự, đổi thứ tự hoặc kiểu component có thể làm pattern không còn biên dịch hoặc thay đổi cách bind biến.

Record pattern là tính năng của Java 21 trở lên; Java 16 có record nhưng chưa có record pattern chuẩn. Khi phát hành public record được client sử dụng bằng JDK hiện đại, cần đưa record pattern vào kiểm tra source compatibility nếu API khuyến khích client destructure record.

## 8. Tác động đến equals, hashCode và toString

Compiler sinh các phương thức này dựa trên component của record. Vì vậy, thay đổi component có thể thay đổi hành vi dù tên phương thức và chữ ký vẫn giữ nguyên.

Ví dụ thêm `z` vào `Point`:

```java
Point first = new Point(1, 2, 0);
Point second = new Point(1, 2, 5);

System.out.println(first.equals(second)); // false
```

Trước khi thêm `z`, hai tọa độ có cùng `x` và `y` là bằng nhau theo hợp đồng do compiler sinh. Sau khi thêm `z`, `z` tham gia so sánh. Nếu record được dùng làm key trong map/set, cache key, deduplication key hoặc giá trị so sánh trong test, kết quả có thể thay đổi.

`toString()` cũng hiển thị component mới và tên component mới. Không dùng `toString()` mặc định làm JSON, log contract cho bên ngoài, cache key hoặc định dạng truyền dữ liệu lâu dài. Nếu cần định dạng ổn định, hãy định nghĩa serializer hoặc phương thức biểu diễn riêng.

## 9. Serialization và schema dữ liệu

Record có thể triển khai `Serializable`, nhưng serialization của record có quy tắc riêng: khi deserialize, canonical constructor của record được gọi. Các giá trị trong stream được ánh xạ đến component theo tên; component không có trường tương ứng trong stream nhận giá trị mặc định, còn trường stream không tương ứng với component có thể bị bỏ qua theo quy tắc serialization của record.

Điều này khiến đổi tên hoặc đổi kiểu component có thể ảnh hưởng dữ liệu đã serialize:

- Đổi tên component có thể làm dữ liệu cũ không còn ánh xạ vào component mới; component mới có thể nhận giá trị mặc định.
- Thêm component có thể khiến dữ liệu cũ không có giá trị cho component mới; canonical constructor nhận giá trị mặc định cho component đó.
- Đổi kiểu có thể làm kiểu trường trong stream không tương thích với component mới và gây lỗi deserialize.
- Thay đổi thứ tự component không phải là cách migration dữ liệu an toàn; mapping serialization dựa vào tên, còn canonical constructor nhận đối số theo thứ tự component.

Không nên giả định rằng `serialVersionUID` tự giải quyết mọi thay đổi schema của record. Nếu record được dùng trong dữ liệu lưu lâu dài, cache phân tán hoặc trao đổi giữa các phiên bản ứng dụng, hãy kiểm thử bằng fixture serialize từ phiên bản cũ và deserialize bằng phiên bản mới. Với giao thức bền vững hoặc public wire format, nên dùng schema có version và serializer có quy tắc tương thích rõ ràng thay vì phụ thuộc trực tiếp vào Java object serialization.

## 10. Framework và reflection có thể phụ thuộc component metadata

Nhiều framework nhận diện record bằng `Class.isRecord()` và `getRecordComponents()`, sau đó dùng component name/type/accessor hoặc canonical constructor. Thay đổi component có thể tác động đến:

- JSON property và tên trường trong API response/request.
- Mapping từ database row, query projection hoặc message payload.
- Validation annotation và metadata trên record component.
- Dependency injection hoặc binding dựa trên constructor.
- OpenAPI/JSON Schema và tài liệu API được sinh tự động.
- Expression, template hoặc mapping cấu hình tên property.

Không phải framework nào cũng xử lý record giống nhau. Một số framework có annotation để đổi tên JSON property hoặc custom constructor mapping. Cần kiểm tra đúng framework/version/configuration của ứng dụng thay vì suy luận chỉ từ Java language.

Ví dụ, nếu serializer đang xuất component `name` thành JSON key `name`, đổi component thành `displayName` có thể đổi wire contract thành `displayName`. Nếu API bên ngoài phải giữ key cũ, cấu hình alias hoặc serializer mapping tường minh và viết contract test.

## 11. Bảng tổng hợp mức ảnh hưởng

| Thay đổi | Source compatibility | Binary compatibility | Hành vi/metadata |
|---|---|---|---|
| Đổi tên component, giữ kiểu và thứ tự | Client gọi accessor cũ cần sửa nếu không có alias | Constructor descriptor giữ nguyên; accessor cũ mất nếu không giữ method alias | Record metadata, tên property, `toString` và serialization mapping thay đổi |
| Đổi kiểu component | Thường cần sửa client theo kiểu mới | Constructor/accessor descriptor thường đổi; generic erasure có thể giữ descriptor nhưng vẫn đổi hợp đồng | Có thể thay đổi chuyển đổi dữ liệu, equals/hashCode và serialization |
| Thêm component | Lời gọi canonical constructor cũ cần sửa nếu không có overload | Canonical constructor descriptor đổi; overload cũ có thể giữ linkage | Component metadata, equality, hash code, toString, serialization và record pattern thay đổi |
| Đổi thứ tự component | Có thể vẫn biên dịch nhưng đổi ý nghĩa đối số/pattern | Nếu descriptor kiểu không đổi, linkage có thể vẫn thành công | Ý nghĩa dữ liệu và component order thay đổi; nguy cơ lỗi âm thầm |
| Thêm accessor alias cũ | Có thể giữ client source cũ | Giữ method descriptor cũ nếu chữ ký được giữ nguyên | Reflection record component không đổi theo alias; alias cần chính sách deprecation |
| Thêm constructor overload cũ | Có thể giữ lời gọi source cũ | Có thể giữ descriptor constructor cũ | Không giữ nguyên semantics nếu component mới tham gia equals/hashCode/toString |

## 12. Chiến lược tiến hóa public record an toàn

### Giữ component ổn định

Trước khi công bố record, hãy xem tên, kiểu và thứ tự component như hợp đồng dài hạn. Ưu tiên kiểu biểu diễn rõ ràng và ổn định; tránh đưa trực tiếp cấu trúc nội bộ có khả năng thay đổi thường xuyên vào public record.

### Dùng alias và overload cho migration có kiểm soát

Khi đổi tên, giữ accessor cũ bằng method alias và đánh dấu deprecated. Khi thêm component, cân nhắc giữ constructor cũ nếu có giá trị mặc định hợp lệ. Khi đổi kiểu, dùng component mới và chuyển đổi tường minh để giữ accessor/constructor cũ trong thời gian migration nếu điều đó có thể thực hiện an toàn.

Không giữ alias vô thời hạn nếu nó làm API khó hiểu. Hãy công bố thời gian deprecation, phiên bản dự kiến loại bỏ và hướng chuyển đổi.

### Tạo kiểu API mới khi thay đổi mang tính phá vỡ

Nếu cần thay đổi lớn về cấu trúc, cân nhắc tạo `CustomerV2` hoặc DTO mới trong package/version API mới. Adapter có thể chuyển giữa kiểu cũ và kiểu mới. Cách này làm ranh giới tương thích rõ hơn việc liên tục thay đổi một record đã công bố.

### Dùng class khi cấu trúc cần tiến hóa thường xuyên

Record phù hợp với data carrier có trạng thái và semantics ổn định. Nếu API cần thêm field thường xuyên, cần kiểm soát constructor, validation, mutability, hoặc muốn duy trì nhiều cách tạo object, một class thông thường với factory/builder và accessor tường minh có thể phù hợp hơn.

### Đóng gói dữ liệu hay thay đổi vào component riêng

Thay vì liên tục thêm component vào record công khai, có thể gom nhóm dữ liệu thường mở rộng thành một kiểu riêng:

```java
public record CustomerProfile(
        String displayName,
        String email,
        String phone) {
}

public record Customer(String id, CustomerProfile profile) {
}
```

Thiết kế này không loại bỏ nhu cầu version hóa `CustomerProfile`, nhưng giúp ranh giới dữ liệu thay đổi được quản lý trong một kiểu riêng và tránh làm constructor cấp cao liên tục tăng số component.

## 13. Kiểm thử tương thích khi thay đổi record

Khi public record đã được phát hành, nên có kiểm thử riêng cho từng loại hợp đồng:

1. **Source compatibility:** biên dịch một client mẫu đang dùng API cũ với source/API mới.
2. **Binary compatibility:** biên dịch client bằng API cũ, sau đó chạy file `.class` đó với API mới để phát hiện `NoSuchMethodError`, `NoSuchMethodException` hoặc lỗi linkage khác.
3. **Constructor compatibility:** xác nhận các overload cũ còn tồn tại với descriptor mong muốn.
4. **Accessor compatibility:** xác nhận alias cũ trả về giá trị tương đương và có annotation deprecation phù hợp.
5. **Reflection compatibility:** kiểm tra `Class.isRecord()`, `getRecordComponents()`, tên, kiểu và thứ tự component.
6. **Behavioral compatibility:** kiểm tra `equals`, `hashCode`, `toString` và cách record được dùng làm key.
7. **Serialization compatibility:** deserialize fixture được tạo từ phiên bản trước và xác nhận giá trị sau migration.
8. **Framework contract:** kiểm tra JSON property, database mapping, validation và schema được sinh.
9. **Record pattern:** nếu client dùng Java 21+, biên dịch lại các record pattern với shape mới.

Ví dụ kiểm tra record metadata:

```java
import java.lang.reflect.RecordComponent;

public class RecordApiInspection {
    public static void main(String[] args) {
        Class<Customer> type = Customer.class;

        if (!type.isRecord()) {
            throw new IllegalStateException("Customer is no longer a record");
        }

        for (RecordComponent component : type.getRecordComponents()) {
            System.out.printf("%s : %s%n",
                    component.getName(),
                    component.getType().getTypeName());
        }
    }
}
```

Test metadata đặc biệt hữu ích khi framework hoặc client sử dụng reflection để tự động ánh xạ component.

## 14. Quy trình review một thay đổi public record

Trước khi merge thay đổi, reviewer nên trả lời:

- Component nào đổi tên, kiểu hoặc thứ tự? Có thêm hoặc bỏ component không?
- Canonical constructor descriptor cũ còn tồn tại không? Nếu không, đây có phải breaking change đã được version hóa không?
- Accessor cũ có cần alias và deprecation period không?
- Giá trị mặc định cho component mới có ý nghĩa nghiệp vụ rõ ràng không?
- `equals`, `hashCode`, `toString` có thay đổi semantics không?
- Reflection, JSON/schema, database mapping hoặc validation có dựa vào component metadata không?
- Có dữ liệu serialization từ phiên bản cũ cần đọc không?
- Client dùng record pattern trên JDK 21+ có cần cập nhật không?
- Tài liệu migration và contract test đã được cập nhật chưa?

Nếu một thay đổi làm mất constructor/accessor cũ hoặc thay đổi wire schema, hãy công bố rõ đó là breaking change, nêu phiên bản thay đổi và cung cấp adapter hoặc hướng dẫn migration.

## 15. Ghi nhớ

- Tên, kiểu và thứ tự component của public record là một phần API.
- Đổi tên component làm đổi accessor và record metadata; constructor descriptor chỉ đổi nếu kiểu hoặc thứ tự kiểu thay đổi.
- Đổi kiểu thường làm đổi descriptor constructor/accessor; generic erasure có thể che giấu thay đổi ở mức binary nhưng không bảo đảm tương thích source hay hành vi.
- Thêm component làm đổi canonical constructor; overload cũ có thể giữ lời gọi cũ nhưng không giữ nguyên semantics của equals/hashCode/toString.
- Đổi thứ tự component cùng kiểu có thể vẫn liên kết nhưng đảo ý nghĩa đối số.
- Record pattern là tính năng Java 21+ và phụ thuộc shape của record.
- Serialization của record ánh xạ dữ liệu theo tên component và gọi canonical constructor; phải test với dữ liệu phiên bản cũ.
- Alias accessor, constructor overload, adapter và DTO version mới là các công cụ migration; chọn theo yêu cầu tương thích thực tế.
- Nếu cấu trúc cần thay đổi thường xuyên, cân nhắc class hoặc schema có version thay vì public record bất ổn.

Record giúp mô hình hóa dữ liệu gọn và rõ, nhưng component công khai tạo ra hợp đồng mà client có thể phụ thuộc. Đánh giá đồng thời source, binary, behavioral, reflection và serialization compatibility sẽ giúp tiến hóa API có kiểm soát trên Java hiện đại.
