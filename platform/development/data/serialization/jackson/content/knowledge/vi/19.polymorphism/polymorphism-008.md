# Kết hợp đa hình với collection và kiểu tổng quát

Trong ứng dụng Java, một collection có thể chứa nhiều đối tượng thuộc các lớp con của cùng một kiểu cha. Ví dụ, một đơn hàng có thể chứa nhiều phương thức thanh toán, một danh sách thông báo có thể gồm email và SMS, hoặc một danh sách hình học có thể chứa hình tròn và hình chữ nhật. Khi chuyển các cấu trúc đó sang JSON bằng Jackson, cần giải quyết đồng thời hai vấn đề:

- **Kiểu tổng quát (generic type):** Jackson cần biết phần tử của `List`, value của `Map` hoặc tham số `T` trong wrapper là kiểu nào.
- **Đa hình (polymorphism):** nếu kiểu khai báo là interface hoặc lớp cha, Jackson cần biết mỗi phần tử cụ thể là lớp con nào để tạo đúng object khi đọc JSON.

Hai thông tin này bổ sung cho nhau. `TypeReference` hoặc `JavaType` giữ cấu trúc generic như `List<PaymentMethod>`; `@JsonTypeInfo` và cơ chế đăng ký subtype cho biết mỗi giá trị `PaymentMethod` là `CardPayment` hay `BankTransferPayment`. Chỉ có generic type thì Jackson vẫn không thể khởi tạo một lớp cha abstract; chỉ có metadata subtype mà không giữ kiểu collection thì Jackson có thể không biết phần tử trong danh sách cần được ánh xạ theo kiểu cha nào.

## 1. Mô hình hóa một hệ thống có nhiều subtype

Giả sử hệ thống thanh toán có hai cách thanh toán: thẻ và chuyển khoản. Cả hai đều là một `PaymentMethod`, nhưng mỗi loại có các thuộc tính riêng.

```java
public abstract class PaymentMethod {
    private String reference;

    public String getReference() {
        return reference;
    }

    public void setReference(String reference) {
        this.reference = reference;
    }
}
```

Các lớp con:

```java
public class CardPayment extends PaymentMethod {
    private String lastFourDigits;
    private String network;

    public String getLastFourDigits() {
        return lastFourDigits;
    }

    public void setLastFourDigits(String lastFourDigits) {
        this.lastFourDigits = lastFourDigits;
    }

    public String getNetwork() {
        return network;
    }

    public void setNetwork(String network) {
        this.network = network;
    }
}
```

```java
public class BankTransferPayment extends PaymentMethod {
    private String bankCode;
    private String accountSuffix;

    public String getBankCode() {
        return bankCode;
    }

    public void setBankCode(String bankCode) {
        this.bankCode = bankCode;
    }

    public String getAccountSuffix() {
        return accountSuffix;
    }

    public void setAccountSuffix(String accountSuffix) {
        this.accountSuffix = accountSuffix;
    }
}
```

Một danh sách có thể khai báo:

```java
List<PaymentMethod> methods = new ArrayList<>();
methods.add(cardPayment);
methods.add(bankTransferPayment);
```

Ở góc nhìn Java, kiểu phần tử khai báo là `PaymentMethod`, còn object runtime có thể là `CardPayment` hoặc `BankTransferPayment`. JSON cần giữ thông tin subtype để khi đọc lại Jackson tạo đúng lớp con.

## 2. Khai báo metadata subtype bằng `@JsonTypeInfo`

Jackson dùng `@JsonTypeInfo` để chỉ định cách đưa thông tin kiểu vào JSON hoặc cách lấy thông tin đó khi đọc. Có thể kết hợp với `@JsonSubTypes` để ánh xạ tên type ID sang lớp Java được phép.

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;

@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "methodType"
)
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = BankTransferPayment.class, name = "bank_transfer")
})
public abstract class PaymentMethod {
    // Các thuộc tính dùng chung.
}
```

Khi serialize một phần tử được xử lý theo kiểu `PaymentMethod`, Jackson thêm property `methodType` để phân biệt subtype. JSON có thể có dạng:

```json
{
  "methodType": "card",
  "reference": "pay-100",
  "lastFourDigits": "4242",
  "network": "VISA"
}
```

Hoặc:

```json
{
  "methodType": "bank_transfer",
  "reference": "pay-101",
  "bankCode": "ACB",
  "accountSuffix": "8899"
}
```

Khi đọc, Jackson lấy `methodType`, tìm subtype đã đăng ký và tạo `CardPayment` hoặc `BankTransferPayment`. Các field dùng chung được ánh xạ vào lớp cha; các field riêng được ánh xạ vào lớp con.

### 2.1. Vì sao nên dùng `Id.NAME`?

`JsonTypeInfo.Id.NAME` dùng các tên logic như `card` hoặc `bank_transfer`. Các tên này là một phần của hợp đồng JSON và không phụ thuộc trực tiếp vào tên package hoặc tên lớp Java.

`JsonTypeInfo.Id.CLASS` có thể ghi tên lớp đầy đủ, ví dụ `com.example.payment.CardPayment`. Cách đó làm JSON phụ thuộc vào cấu trúc package và tên lớp nội bộ; nó cũng mở rộng bề mặt rủi ro khi xử lý dữ liệu không tin cậy. Với API hoặc message, nên ưu tiên type ID logic cùng danh sách subtype được phép.

### 2.2. Dùng `@JsonTypeName` để đặt tên trên lớp con

Có thể đặt tên logic ngay trên từng subtype:

```java
import com.fasterxml.jackson.annotation.JsonTypeName;

@JsonTypeName("card")
public class CardPayment extends PaymentMethod {
    // Các thuộc tính riêng của thẻ.
}
```

```java
@JsonTypeName("bank_transfer")
public class BankTransferPayment extends PaymentMethod {
    // Các thuộc tính riêng của chuyển khoản.
}
```

`@JsonSubTypes` ở lớp cha vẫn là nơi dễ thấy danh sách subtype được chấp nhận. `@JsonTypeName` cung cấp tên logic cho lớp con. Có thể dùng `@JsonSubTypes` với tên tường minh mà không cần `@JsonTypeName`; hãy chọn một quy ước nhất quán trong dự án.

## 3. Collection chứa các giá trị đa hình

Sau khi kiểu cha có metadata subtype, một collection có thể chứa nhiều object khác nhau nhưng cùng khai báo kiểu phần tử là `PaymentMethod`.

JSON array:

```json
[
  {
    "methodType": "card",
    "reference": "pay-100",
    "lastFourDigits": "4242",
    "network": "VISA"
  },
  {
    "methodType": "bank_transfer",
    "reference": "pay-101",
    "bankCode": "ACB",
    "accountSuffix": "8899"
  }
]
```

Đọc thành `List<PaymentMethod>`:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

List<PaymentMethod> methods = mapper.readValue(
        json,
        new TypeReference<List<PaymentMethod>>() {}
);

for (PaymentMethod method : methods) {
    if (method instanceof CardPayment card) {
        System.out.println(card.getLastFourDigits());
    } else if (method instanceof BankTransferPayment transfer) {
        System.out.println(transfer.getBankCode());
    }
}
```

`TypeReference<List<PaymentMethod>>` cung cấp cho Jackson kiểu collection và kiểu phần tử. Metadata `methodType` trong từng object cung cấp lớp con cụ thể. Sau khi đọc, mỗi phần tử có runtime type tương ứng.

### 3.1. Dùng `JavaType` khi cần xây dựng kiểu động

Nếu kiểu phần tử chỉ được biết khi chạy, có thể tạo `JavaType`:

```java
import com.fasterxml.jackson.databind.JavaType;

JavaType paymentType = mapper.constructType(PaymentMethod.class);
JavaType paymentListType = mapper.getTypeFactory()
        .constructCollectionType(List.class, paymentType);

List<PaymentMethod> methods = mapper.readValue(json, paymentListType);
```

`JavaType` lưu cấu trúc kiểu đã được giải quyết. Nó phù hợp với API tiện ích, nơi lớp collection, kiểu phần tử hoặc kiểu wrapper được ghép từ các tham số runtime.

### 3.2. Ghi collection đa hình

Khi serialize một collection ở vị trí property có khai báo `List<PaymentMethod>`, Jackson có thông tin kiểu phần tử từ property và có thể áp dụng type serializer của `PaymentMethod` cho từng giá trị.

Với collection là root value, kiểu generic có thể bị mất do type erasure nếu chỉ truyền object runtime vào `writeValueAsString(Object)`. Để xác định rõ kiểu phần tử ở root, tạo writer với kiểu generic:

```java
JavaType paymentListType = mapper.getTypeFactory()
        .constructCollectionType(List.class, PaymentMethod.class);

String output = mapper.writerFor(paymentListType)
        .writeValueAsString(methods);
```

Hoặc dùng `TypeReference` nếu phiên bản Jackson đang dùng cung cấp overload tương ứng:

```java
String output = mapper.writerFor(
        new TypeReference<List<PaymentMethod>>() {}
).writeValueAsString(methods);
```

Việc khai báo kiểu root giúp Jackson biết phần tử được serialize theo hợp đồng `PaymentMethod`, nhờ đó metadata subtype được áp dụng nhất quán. Đừng chỉ dựa vào kiểu runtime của `ArrayList`, vì Java không giữ tham số `PaymentMethod` trong đối tượng collection tại runtime.

## 4. Kết hợp đa hình với `Map`

Một map có thể ánh xạ mã nghiệp vụ tới các object thuộc nhiều subtype. Ví dụ, đơn hàng lưu phương thức thanh toán theo mã:

```json
{
  "primary": {
    "methodType": "card",
    "reference": "pay-100",
    "lastFourDigits": "4242",
    "network": "VISA"
  },
  "backup": {
    "methodType": "bank_transfer",
    "reference": "pay-101",
    "bankCode": "ACB",
    "accountSuffix": "8899"
  }
}
```

Đọc thành `Map<String, PaymentMethod>`:

```java
Map<String, PaymentMethod> methodsByName = mapper.readValue(
        json,
        new TypeReference<Map<String, PaymentMethod>>() {}
);
```

Jackson hiểu key là `String`, value là `PaymentMethod`. Với mỗi value object, metadata `methodType` xác định subtype.

Nếu cần xây dựng kiểu động:

```java
JavaType mapType = mapper.getTypeFactory().constructMapType(
        Map.class,
        String.class,
        PaymentMethod.class
);

Map<String, PaymentMethod> methodsByName = mapper.readValue(json, mapType);
```

### 4.1. Type metadata áp dụng cho value, không phải key

Trong JSON, tên property của object thường đóng vai trò key của map. `@JsonTypeInfo` trên `PaymentMethod` điều khiển value object, không tự tạo type ID cho key. Nếu key cũng là một kiểu Java phức tạp, cần quy định cách biểu diễn key thành chuỗi và dùng key serializer/deserializer phù hợp.

Thông thường, nên chọn key có biểu diễn JSON ổn định như `String`, mã enum hoặc ID đã chuẩn hóa. Đừng kỳ vọng metadata subtype của value giải quyết việc chuyển đổi key.

## 5. Đa hình bên trong generic wrapper

Các API thường bọc dữ liệu trong một envelope có trạng thái, thông báo và payload tổng quát:

```java
public class ApiEnvelope<T> {
    private String status;
    private T data;

    public ApiEnvelope() {
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }
}
```

Payload có thể là danh sách các phương thức thanh toán:

```json
{
  "status": "OK",
  "data": [
    {
      "methodType": "card",
      "reference": "pay-100",
      "lastFourDigits": "4242",
      "network": "VISA"
    },
    {
      "methodType": "bank_transfer",
      "reference": "pay-101",
      "bankCode": "ACB",
      "accountSuffix": "8899"
    }
  ]
}
```

Đọc thành `ApiEnvelope<List<PaymentMethod>>`:

```java
ApiEnvelope<List<PaymentMethod>> response = mapper.readValue(
        json,
        new TypeReference<ApiEnvelope<List<PaymentMethod>>>() {}
);
```

Jackson cần biết ba tầng thông tin:

1. Kiểu ngoài cùng là `ApiEnvelope`.
2. Tham số `T` của envelope là `List<PaymentMethod>`.
3. Mỗi phần tử `PaymentMethod` dùng `methodType` để chọn lớp con cụ thể.

Nếu chỉ truyền `ApiEnvelope.class`, Java/Jackson không có đủ generic argument để biết `data` là danh sách payment method. Nếu chỉ truyền `List.class`, Jackson cũng không biết kiểu wrapper và kiểu phần tử. `TypeReference` giữ lại toàn bộ cấu trúc lồng nhau.

### 5.1. Tạo `JavaType` cho wrapper lồng collection

Khi kiểu được ghép ở runtime, xây dựng từ trong ra ngoài:

```java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.type.TypeFactory;

TypeFactory typeFactory = mapper.getTypeFactory();

JavaType paymentListType = typeFactory.constructCollectionType(
        List.class,
        PaymentMethod.class
);

JavaType envelopeType = typeFactory.constructParametricType(
        ApiEnvelope.class,
        paymentListType
);

ApiEnvelope<List<PaymentMethod>> response = mapper.readValue(
        json,
        envelopeType
);
```

`constructParametricType()` nhận lớp generic cùng các `JavaType` tham số. Cách xây dựng này cũng áp dụng cho wrapper lồng map, ví dụ `ApiEnvelope<Map<String, PaymentMethod>>`.

### 5.2. Serialize wrapper có collection đa hình

Khi ghi root wrapper, nên cung cấp kiểu tổng quát đầy đủ cho `ObjectWriter`:

```java
JavaType envelopeType = typeFactory.constructParametricType(
        ApiEnvelope.class,
        paymentListType
);

String json = mapper.writerFor(envelopeType)
        .writeValueAsString(response);
```

Nếu `ApiEnvelope<T>` là property của một lớp khác với khai báo generic cụ thể, Jackson thường có thể lấy thông tin kiểu từ property đó. Với root value hoặc API tiện ích nhận `Object`, `JavaType`/`TypeReference` giúp tránh mất thông tin do type erasure.

## 6. Collection lồng nhau và nhiều cấp đa hình

Các cấu trúc phức tạp vẫn dùng cùng nguyên tắc: mỗi vị trí có kiểu khai báo là base type cần metadata subtype; mỗi collection/map cần kiểu phần tử/value đầy đủ.

Ví dụ `Map<String, List<PaymentMethod>>`:

```java
TypeReference<Map<String, List<PaymentMethod>>> groupedType =
        new TypeReference<Map<String, List<PaymentMethod>>>() {};

Map<String, List<PaymentMethod>> grouped = mapper.readValue(
        json,
        groupedType
);
```

Hoặc tạo động:

```java
JavaType paymentListType = typeFactory.constructCollectionType(
        List.class,
        PaymentMethod.class
);

JavaType groupedType = typeFactory.constructMapType(
        Map.class,
        String.class,
        paymentListType
);

Map<String, List<PaymentMethod>> grouped = mapper.readValue(json, groupedType);
```

Nếu `PaymentMethod` có subtype metadata, mỗi phần tử trong mọi danh sách sẽ được phân giải theo type ID riêng. Map và list chỉ mô tả cấu trúc container; chúng không thay thế metadata subtype của phần tử.

## 7. Chọn hình thức type metadata

`@JsonTypeInfo.include` quyết định vị trí type ID trong JSON. Với collection và generic wrapper, các lựa chọn thường gặp gồm:

### 7.1. `As.PROPERTY`

Đặt type ID thành một property bên trong object:

```json
{
  "methodType": "card",
  "reference": "pay-100",
  "lastFourDigits": "4242"
}
```

Đây thường là lựa chọn dễ đọc và dễ tích hợp nhất với API JSON.

### 7.2. `As.WRAPPER_OBJECT`

Dùng type ID làm tên property bọc object:

```json
{
  "card": {
    "reference": "pay-100",
    "lastFourDigits": "4242"
  }
}
```

### 7.3. `As.WRAPPER_ARRAY`

Đặt type ID và object trong một array hai phần tử:

```json
[
  "card",
  {
    "reference": "pay-100",
    "lastFourDigits": "4242"
  }
]
```

Với một collection các giá trị đa hình, mỗi phần tử được bao theo quy tắc đã chọn. Ví dụ, một array ngoài cùng có thể chứa nhiều wrapper array cho từng phần tử.

Chọn một dạng metadata ổn định cho hợp đồng API. Không nên thay `As.PROPERTY` thành wrapper format tùy tiện giữa các phiên bản vì client phải thay đổi parser.

## 8. Type ID là metadata, không nhất thiết là field domain

Với cấu hình mặc định `visible = false`, type ID được Jackson sử dụng để chọn subtype và không được chuyển tiếp như một property bình thường cho POJO. Ví dụ, `methodType` có thể không cần khai báo field trong `PaymentMethod`.

Nếu ứng dụng muốn giữ type ID trong một thuộc tính Java, có thể bật:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "methodType",
        visible = true
)
```

Khi `visible = true`, type ID được đưa tiếp vào quá trình deserialization như một property thông thường. Chỉ bật khi lớp thực sự cần lưu hoặc xử lý giá trị đó; nếu không, để mặc định giúp tránh trùng lặp thông tin giữa metadata và field domain.

Nếu discriminator đã là một property domain thực sự, có thể cân nhắc `JsonTypeInfo.As.EXISTING_PROPERTY` cùng một field như `methodType`. Khi dùng dạng này, serializer dựa trên property đã có để ghi type ID; cần bảo đảm giá trị field khớp subtype thực tế và kiểm thử cả hai chiều.

## 9. Đăng ký subtype bằng cấu hình thay vì annotation

Trong một số dự án, không thể sửa lớp cha hoặc muốn tập trung danh sách subtype ở cấu hình. Có thể đăng ký các subtype có tên bằng `NamedType`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.jsontype.NamedType;

ObjectMapper mapper = new ObjectMapper();
mapper.registerSubtypes(
        new NamedType(CardPayment.class, "card"),
        new NamedType(BankTransferPayment.class, "bank_transfer")
);
```

Kiểu cha vẫn cần khai báo cơ chế type information, ví dụ `@JsonTypeInfo(use = Id.NAME, property = "methodType")`, hoặc cấu hình type resolver phù hợp. `registerSubtypes()` cung cấp danh sách subtype/name cho mapper; nó không tự thêm metadata đa hình nếu kiểu cha chưa có quy tắc type info.

Đăng ký subtype theo mapper giúp mỗi integration có allowlist riêng. Hãy hoàn tất cấu hình trước khi dùng mapper đồng thời trong ứng dụng.

## 10. Xử lý type ID không xác định

Nếu JSON chứa type ID không có trong danh sách subtype, ví dụ:

```json
{
  "methodType": "crypto_wallet",
  "reference": "pay-200"
}
```

nhưng mapper chỉ đăng ký `card` và `bank_transfer`, Jackson thường ném `InvalidTypeIdException` (một loại `JsonMappingException`). Đây là hành vi hữu ích khi subtype không xác định phải bị từ chối.

Có thể khai báo `defaultImpl` trong `@JsonTypeInfo` nếu nghiệp vụ có một kiểu fallback an toàn:

```java
@JsonTypeInfo(
        use = JsonTypeInfo.Id.NAME,
        include = JsonTypeInfo.As.PROPERTY,
        property = "methodType",
        defaultImpl = UnknownPaymentMethod.class
)
```

`UnknownPaymentMethod` phải được thiết kế để chứa dữ liệu phù hợp và không thực thi hành vi nhạy cảm. Fallback không nên biến một type ID tùy ý thành một lớp có quyền truy cập rộng. Trong nhiều API, từ chối type ID không biết và trả lỗi dữ liệu rõ ràng là lựa chọn an toàn hơn.

Nếu consumer cần giữ subtype mới để chuyển tiếp, có thể kết hợp một mô hình extension được kiểm soát, nhưng không nên tự động khởi tạo bất kỳ lớp Java nào được nêu trong JSON.

## 11. Bảo mật khi đọc đa hình

Type metadata ảnh hưởng trực tiếp đến lớp Java được tạo ra từ JSON. Vì vậy, danh sách subtype được chấp nhận phải được kiểm soát.

- Ưu tiên `JsonTypeInfo.Id.NAME` với các tên logic và subtype allowlist.
- Không bật default typing rộng cho JSON đến từ client hoặc hệ thống không tin cậy.
- Tránh `JsonTypeInfo.Id.CLASS` khi không cần thiết; tên lớp đầy đủ làm hợp đồng phụ thuộc package và có thể mở rộng kiểu được phép khởi tạo.
- Nếu phải dùng default typing cho một định dạng nội bộ, cấu hình `PolymorphicTypeValidator` giới hạn package/type được phép và đánh giá riêng rủi ro của nguồn dữ liệu.
- Kiểm tra type ID không xác định và xử lý lỗi ở ranh giới API/message.
- Không xem type ID là cơ chế authorization. Một client gửi `methodType: "admin"` không có nghĩa client có quyền tạo hoặc sử dụng đối tượng đặc quyền.

Ví dụ cấu hình `Id.NAME` cùng hai subtype rõ ràng giới hạn các loại payment mà mapper có thể tạo theo hợp đồng. Việc thêm subtype mới nên là thay đổi có chủ đích, có review và kiểm thử.

## 12. Không nhầm generic type với polymorphic type

Hai cơ chế trả lời hai câu hỏi khác nhau:

| Cơ chế | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| `TypeReference<List<PaymentMethod>>` | Container chứa kiểu phần tử nào? | Đây là danh sách các `PaymentMethod`. |
| `JavaType` | Cấu trúc generic đầy đủ là gì? | `ApiEnvelope<List<PaymentMethod>>`. |
| `@JsonTypeInfo` | Mỗi `PaymentMethod` cụ thể thuộc subtype nào? | `card` hay `bank_transfer`. |
| `@JsonSubTypes`/`registerSubtypes` | Các subtype nào được phép và tên logic của chúng? | `card` ánh xạ tới `CardPayment`. |

Nếu chỉ có `TypeReference<List<PaymentMethod>>` nhưng không có type metadata hoặc custom resolver, Jackson biết phần tử là kiểu cha nhưng không biết nên khởi tạo lớp con nào. Nếu có `@JsonTypeInfo` nhưng chỉ đọc bằng `List.class`, generic element type có thể bị mất và Jackson không có đủ thông tin để bind từng phần tử theo base type mong muốn.

## 13. Type erasure và generic method

Java xóa phần lớn generic parameter ở runtime. Vì vậy, một method tiện ích như sau không thể tự suy ra `T` từ nơi gọi:

```java
public <T> List<T> readList(String json) throws IOException {
    return mapper.readValue(
            json,
            new TypeReference<List<T>>() {}
    );
}
```

`T` ở đây chỉ là type variable của method; `TypeReference` không tự biết caller muốn `PaymentMethod`, `User` hay một lớp khác. Hãy nhận thông tin kiểu từ caller:

```java
public <T> List<T> readList(String json, Class<T> elementType)
        throws IOException {
    JavaType listType = mapper.getTypeFactory()
            .constructCollectionType(List.class, elementType);
    return mapper.readValue(json, listType);
}
```

Với cấu trúc generic lồng nhau, nhận `TypeReference<T>` hoặc `JavaType` đầy đủ:

```java
public <T> T read(String json, TypeReference<T> targetType)
        throws IOException {
    return mapper.readValue(json, targetType);
}

public <T> T read(String json, JavaType targetType)
        throws IOException {
    return mapper.readValue(json, targetType);
}
```

Ví dụ caller truyền `new TypeReference<ApiEnvelope<List<PaymentMethod>>>() {}`. Generic structure được giữ ở runtime, còn type ID trong từng phần tử quyết định lớp con.

## 14. Ví dụ kiểm thử round-trip collection đa hình

Kiểm thử nên xác nhận cả cấu trúc JSON có type ID và runtime class sau khi đọc lại.

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class PaymentPolymorphismTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void collectionKeepsConcreteSubtypes() throws Exception {
        List<PaymentMethod> methods = List.of(
                cardPayment(),
                bankTransferPayment()
        );

        JavaType listType = mapper.getTypeFactory()
                .constructCollectionType(List.class, PaymentMethod.class);

        String json = mapper.writerFor(listType)
                .writeValueAsString(methods);

        JsonNode tree = mapper.readTree(json);
        assertEquals("card", tree.get(0).path("methodType").asText());
        assertEquals("bank_transfer", tree.get(1).path("methodType").asText());

        List<PaymentMethod> restored = mapper.readValue(
                json,
                new TypeReference<List<PaymentMethod>>() {}
        );

        assertInstanceOf(CardPayment.class, restored.get(0));
        assertInstanceOf(BankTransferPayment.class, restored.get(1));
    }

    private CardPayment cardPayment() {
        CardPayment value = new CardPayment();
        value.setReference("pay-100");
        value.setLastFourDigits("4242");
        value.setNetwork("VISA");
        return value;
    }

    private BankTransferPayment bankTransferPayment() {
        BankTransferPayment value = new BankTransferPayment();
        value.setReference("pay-101");
        value.setBankCode("ACB");
        value.setAccountSuffix("8899");
        return value;
    }
}
```

`assertInstanceOf()` có trong các phiên bản JUnit 5 tương ứng; nếu dự án dùng phiên bản cũ hơn, có thể dùng `assertTrue(restored.get(0) instanceof CardPayment)`. Test sử dụng `writerFor(listType)` để serializer biết kiểu phần tử được khai báo là `PaymentMethod`, sau đó kiểm tra type ID trong JSON và runtime class sau deserialization.

## 15. Các lỗi thường gặp

### 15.1. Chỉ khai báo `List<PaymentMethod>` nhưng không cấu hình subtype

Generic type giúp Jackson biết kiểu phần tử là `PaymentMethod`, nhưng nếu đó là abstract class hoặc interface, Jackson vẫn cần type metadata hoặc custom deserializer để biết lớp cụ thể.

### 15.2. Có `@JsonTypeInfo` nhưng đọc bằng raw `List.class`

`List.class` không giữ thông tin phần tử. Hãy dùng `TypeReference<List<PaymentMethod>>` hoặc `JavaType` để Jackson bind từng phần tử theo base type.

### 15.3. Serialize root collection mà không giữ kiểu generic

Khi root object chỉ được nhìn thấy như một `ArrayList` runtime, tham số `PaymentMethod` có thể không còn trong thông tin kiểu. Dùng `writerFor(JavaType)` hoặc `writerFor(TypeReference)` để cung cấp kiểu root đầy đủ khi cần type metadata ở phần tử.

### 15.4. Dùng `Id.CLASS` để tránh đăng ký subtype

Việc ghi tên lớp đầy đủ làm hợp đồng JSON phụ thuộc package và tăng rủi ro khi đọc dữ liệu không tin cậy. Dùng `Id.NAME` với subtype được cho phép rõ ràng.

### 15.5. Quên type ID trong một phần tử

Nếu type ID là bắt buộc và không có default implementation, phần tử thiếu discriminator có thể không được phân giải. Hãy kiểm tra schema đầu vào và xử lý lỗi rõ ràng thay vì đoán subtype.

### 15.6. Type ID không khớp tên đã đăng ký

Giá trị như `bank-transfer` không tự động tương đương `bank_transfer`. Type ID là giá trị hợp đồng; giữ tên ổn định hoặc hỗ trợ alias có chủ đích nếu cần tương thích.

### 15.7. Nghĩ rằng type ID cấp collection xác định mọi phần tử

Mỗi object đa hình cần metadata theo cơ chế đã chọn, trừ khi ứng dụng có một quy ước khác được mô hình hóa rõ. Một type ID ở ngoài array không tự động xác định subtype cho mọi phần tử nếu không có custom format/deserializer.

## 16. Chọn cách kết hợp theo cấu trúc dữ liệu

| Cấu trúc cần xử lý | Generic type | Cấu hình đa hình |
|---|---|---|
| `List<PaymentMethod>` | `TypeReference` hoặc `JavaType` cho list | `@JsonTypeInfo` trên `PaymentMethod` và subtype allowlist |
| `Map<String, PaymentMethod>` | Map key `String`, value `PaymentMethod` | Type ID trong mỗi value object |
| `ApiEnvelope<PaymentMethod>` | `TypeReference`/`JavaType` cho wrapper | Type ID trong `data` |
| `ApiEnvelope<List<PaymentMethod>>` | Wrapper chứa collection có kiểu phần tử | Type ID cho từng phần tử trong `data` |
| `Map<String, List<PaymentMethod>>` | Map value là list của base type | Type ID cho từng payment method |
| Collection của các kiểu không liên quan | Cần một base type chung hoặc mô hình union rõ ràng | Định nghĩa type ID và danh sách subtype được phép |

Khi kết hợp đa hình với collection và kiểu tổng quát, hãy giữ hai lớp thông tin riêng biệt: generic type mô tả cấu trúc container và kiểu khai báo của phần tử; polymorphic type metadata xác định lớp con cụ thể của từng giá trị. Dùng `TypeReference` hoặc `JavaType` cho `List`, `Map` và wrapper lồng nhau; dùng `@JsonTypeInfo` cùng subtype allowlist để Jackson chọn đúng implementation. Với root collection hoặc wrapper, cung cấp kiểu đầy đủ cho `ObjectWriter` khi cần để tránh mất generic information do type erasure. Giữ type ID logic, xử lý rõ subtype không biết và không bật cơ chế khởi tạo lớp tùy ý cho JSON không tin cậy. Điều đó giúp cấu trúc JSON vừa linh hoạt vừa có hợp đồng kiểu rõ ràng ở cả hai chiều đọc và ghi.
