# Enum, giá trị chưa biết và khả năng mở rộng

Trong chương **Biểu diễn dữ liệu** của module **INTEGRATION_API_REST**, enum là một phần của hợp đồng dữ liệu giữa các hệ thống phát hành độc lập. Một chuỗi nhỏ như `"paid"` có thể quyết định cách giao diện hiển thị, cách dịch vụ xử lý đơn hàng và việc một client cũ có đọc được response mới hay không.

Bài học tập trung vào cách thiết kế tập giá trị trong REST API: chọn mã biểu diễn ổn định, phân biệt giá trị chưa biết với dữ liệu sai, mô tả khả năng mở rộng trong OpenAPI và triển khai xử lý ở Java/Jackson. Các quyết định này phải gắn với phương thức HTTP, kiểm tra đầu vào, phân quyền và hành vi nghiệp vụ của resource; khai báo một kiểu enum trong mã nguồn chưa đủ để tạo ra hợp đồng API rõ ràng.

## 1. Tình huống: một trạng thái mới làm hỏng client cũ

API đơn hàng ban đầu trả về ba trạng thái `pending`, `paid`, `shipped`:

```http
GET /orders/ord_2048 HTTP/1.1
```

```json
{
  "id": "ord_2048",
  "status": "paid"
}
```

Client biên dịch với một enum chỉ có ba giá trị này. Sau đó server bổ sung `delayed` và bắt đầu trả mã mới cho một số đơn hàng. Client cũ có thể lỗi ngay khi deserialize, hoặc parse được chuỗi nhưng không có nhánh xử lý phù hợp.

Cần bảo đảm hai việc riêng biệt:

- **Đọc được dữ liệu:** client vẫn đọc được payload có giá trị mới nếu hợp đồng cho phép mở rộng.
- **Hành xử đúng:** client có hành vi dự phòng phù hợp, không suy diễn giá trị chưa biết thành một trạng thái đã biết.

Thêm giá trị enum có thể tương thích với client được thiết kế để nhận tập mở. Với hợp đồng enum đóng, đây có thể là thay đổi phá vỡ tương thích.

## 2. Enum trên đường truyền khác enum trong ngôn ngữ lập trình

Enum trong Java mô hình hóa một tập hằng số đã biết khi biên dịch. Trên JSON, API truyền một giá trị như chuỗi hoặc số; ý nghĩa của tập giá trị đến từ hợp đồng và mã xử lý của mỗi bên.

| Khái niệm | Ví dụ | Ai quyết định ý nghĩa? |
| --- | --- | --- |
| Mã trên đường truyền | `"paid"` | Hợp đồng API |
| Hằng số nội bộ | `PAYMENT_CONFIRMED` | Mã nguồn dịch vụ |
| Nhãn hiển thị | `Đã thanh toán` | Giao diện và bản địa hóa |
| Vị trí hằng số | `ordinal() == 1` | Thứ tự khai báo enum Java |

Nên tách mã công khai khỏi tên triển khai. Đổi tên hằng số Java để refactor không nên tự động đổi JSON đã công bố. Với chuỗi mã, hãy quy định rõ chữ hoa/thường, ký tự cho phép và giới hạn độ dài. Trong bài này, mã trạng thái có dạng `[a-z][a-z0-9_]{0,63}`.

Không dùng `ordinal()` làm mã công khai. Chèn một hằng số vào giữa enum làm thay đổi vị trí các hằng số sau nó. `Enum.valueOf()` cũng chỉ tìm tên hằng số đã khai báo và báo lỗi khi tên không tồn tại; nó không cung cấp cơ chế giữ mã mới. [Java SE 17: Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html).

Với chuỗi mã, nên có ánh xạ tường minh giữa giá trị nội bộ và giá trị công khai. Chuỗi ngắn thường dễ đọc và chẩn đoán hơn số; đây là lựa chọn thiết kế, không phải yêu cầu của REST.

## 3. Tập đóng và tập mở

### 3.1. Tập đóng: ngoài danh sách là không hợp lệ

Một tập đóng quy định chính xác các giá trị được chấp nhận. Ví dụ chế độ giao hàng khi tạo đơn chỉ hỗ trợ `standard` và `express`:

```json
{
  "deliveryMode": "express"
}
```

Gửi `"teleport"` không có nghĩa là server nên cố đoán một chế độ gần giống. Server chưa có khả năng thực hiện yêu cầu đó và cần trả lỗi có cấu trúc.

Tập đóng thích hợp khi giá trị chọn một hành vi mà bên nhận bắt buộc phải hiểu: phương thức xử lý, thuật toán, lệnh nghiệp vụ hoặc tham số lọc chưa được hỗ trợ. Việc hợp lệ về cú pháp chưa đồng nghĩa hợp lệ về nghiệp vụ hay được cấp quyền.

### 3.2. Tập mở: danh sách hiện tại chưa phải toàn bộ tương lai

Một tập mở cho phép phía cung cấp bổ sung mã mà phía tiêu thụ cũ chưa biết. Ví dụ `status` trong response đơn hàng có thể xuất hiện trạng thái mới nhưng client vẫn đọc được các thuộc tính còn lại.

Hợp đồng mở cần trả lời đủ các điểm sau:

1. Những mã nào đang được định nghĩa và ý nghĩa hiện tại của chúng?
2. Mã mới phải tuân theo định dạng và giới hạn nào?
3. Client phải làm gì khi nhận mã chưa biết?
4. Có cần giữ mã gốc để lưu, chuyển tiếp hoặc chẩn đoán không?
5. Những thao tác nào phải dừng khi chưa hiểu ý nghĩa mã?

Một chuỗi tùy ý không tự tạo ra hợp đồng mở tốt. Cần mô tả rõ chính sách tiến hóa và hành vi dự phòng.

### 3.3. Một khái niệm có thể dùng hợp đồng khác nhau theo chiều dữ liệu

`status` trong response có thể mở, còn `status` trong query lọc vẫn chỉ chấp nhận các giá trị server đang hỗ trợ:

```http
GET /orders?status=paid HTTP/1.1
```

Nếu client gửi bộ lọc chưa hỗ trợ, server không nên âm thầm bỏ điều kiện và trả toàn bộ đơn hàng. Hai schema dùng cho đọc và cho nhập liệu có thể khác nhau dù cùng nói về trạng thái đơn hàng.

Không suy rộng thành quy tắc “mọi response đều mở, mọi request đều đóng”. Một trường chọn giao thức bảo mật trong response có thể yêu cầu client từ chối giá trị lạ; một trường metadata trong request có thể được thiết kế để lưu nguyên mã mà server không diễn giải. Hãy quyết định dựa trên trách nhiệm của bên nhận.

## 4. “Chưa biết” khác null, thiếu thuộc tính và sai kiểu

| Giá trị hoặc tình huống | Ý nghĩa | Cách xử lý theo hợp đồng của bài |
| --- | --- | --- |
| `"delayed"` với client chỉ biết ba mã cũ | Mã chưa biết ở client | Giữ mã gốc, dùng hành vi dự phòng |
| Mã `"unknown"` do server định nghĩa | Một trạng thái nghiệp vụ cụ thể | Làm theo ý nghĩa của chính mã này |
| `null` | Có mặt nhưng không có giá trị | Chỉ chấp nhận nếu schema cho phép |
| Không có thuộc tính `status` | Thuộc tính vắng mặt | Kiểm tra quy tắc bắt buộc/tùy chọn |
| `""` hoặc `"   "` | Rỗng hoặc chỉ có khoảng trắng | Từ chối theo định dạng mã |
| `42`, `true`, `{}` | Sai kiểu JSON | Từ chối thay vì đoán mã |
| `"Paid"` | Khác cách viết đã công bố | Không tự coi bằng `"paid"` |

Giá trị `UNRECOGNIZED` trong SDK thường là **phân loại của client**. Nó không nhất thiết là mã `"unrecognized"` hợp lệ mà server chấp nhận. Nếu server thực sự có trạng thái “chưa xác định”, cần mô tả nó riêng với tình huống client không hiểu một trạng thái mới.

Cũng cần phân biệt **thuộc tính chưa biết** với **giá trị enum chưa biết**:

```json
{
  "id": "ord_2048",
  "status": "delayed",
  "deliveryWindow": "afternoon"
}
```

Cấu hình bỏ qua thuộc tính JSON lạ có thể xử lý `deliveryWindow`, nhưng không tự làm cho enum của thuộc tính `status` chấp nhận `delayed`. Đó là hai quyết định giải mã khác nhau.

Không tự chuyển mọi chuỗi lạ thành chữ thường hoặc cắt khoảng trắng nếu hợp đồng không quy định chuẩn hóa. Việc đó có thể che lỗi producer và làm mất mã gốc cần cho chẩn đoán.

## 5. Tương thích phải được xét theo chiều gửi và nhận

Giả sử tập cũ là `S = {pending, paid, shipped}` và tập mới là `S' = S ∪ {delayed}`. Khi thêm phần tử, bên nhận cũ là nơi có nguy cơ không hiểu dữ liệu của bên gửi mới.

| Thay đổi | Chiều bị ảnh hưởng | Hệ quả có thể xảy ra |
| --- | --- | --- |
| Server bắt đầu trả `delayed` | Server mới → client cũ | Client cũ có thể lỗi hoặc suy diễn sai |
| Server chấp nhận thêm một mã input | Client cũ → server mới | Request cũ vẫn hợp lệ nếu ý nghĩa cũ được giữ |
| Client mới gửi mã input mới | Client mới → server cũ | Server cũ có thể từ chối |
| Server ngừng chấp nhận mã input cũ | Client cũ → server mới | Request trước đây hợp lệ trở thành lỗi |
| Đổi tên hoặc đổi nghĩa một mã đã công bố | Cả hai chiều tùy cách dùng | Phá vỡ hợp đồng dù kiểu JSON không đổi |

Việc server ngừng trả một mã output cũng cần xem ảnh hưởng nghiệp vụ. Một consumer có thể đang dựa vào sự kiện hoặc trạng thái đó để kích hoạt một bước xử lý. Phân tích tương thích không chỉ là so sánh danh sách chuỗi.

Nếu hợp đồng ban đầu là enum đóng, không thể đổi tài liệu thành tập mở rồi coi mọi client cũ đã được bảo vệ. Có thể cần phiên bản hợp đồng mới, cơ chế thương lượng đã thiết kế trước hoặc cập nhật consumer trước khi producer phát mã mới.

## 6. Chọn chiến lược xử lý giá trị chưa biết

| Chiến lược | Được gì? | Mất gì hoặc cần lưu ý? | Tình huống phù hợp |
| --- | --- | --- | --- |
| Từ chối ngay | Phát hiện bên nhận không đủ khả năng xử lý | Không đọc được payload dù phần còn lại có ích | Lệnh hoặc quyết định bắt buộc hiểu chính xác |
| Đổi thành `null` | Đơn giản ở một số mô hình | Lẫn với thiếu dữ liệu, dễ gây lỗi null | Chỉ khi đã chấp nhận mất thông tin và xử lý null rõ ràng |
| Đổi thành hằng `UNRECOGNIZED` | Có nhánh dự phòng tường minh | Thường mất mã gốc | Client chỉ cần hiển thị trạng thái chung |
| Giữ mã gốc và nhận diện phần đã biết | Đọc được mã mới, hỗ trợ chuyển tiếp và chẩn đoán | Cần mô hình và nhánh xử lý rõ ràng | SDK hoặc dịch vụ tích hợp nhận tập mở |
| Ánh xạ sang giá trị cũ đã biết | Có thể giữ một số luồng cũ | Dễ tạo nghĩa sai nếu thiếu quy tắc nghiệp vụ | Chỉ dùng với ánh xạ tương thích được công bố |

Với tập mở, một mô hình thường hữu ích là:

```text
StatusCode
  raw: chuỗi mã nhận được
  known: giá trị thuộc tập client hiểu, nếu nhận diện được
```

Không thể vừa gộp mọi mã mới vào một hằng duy nhất, vừa kỳ vọng phục hồi chính xác chuỗi gốc nếu không lưu thông tin bổ sung.

## 7. Java/Jackson: giữ mã gốc cùng phần đã biết

Ví dụ dưới đây dùng **Java 17 và Jackson 2.x** với các package `com.fasterxml.jackson.*`. Đây là mã minh họa độc lập cho phía đọc response; khi tích hợp vào Spring, dùng phiên bản Jackson phù hợp với dependency management của ứng dụng.

`@JsonCreator(mode = DELEGATING)` cho phép một factory nhận toàn bộ giá trị JSON để tạo đối tượng; `@JsonValue` chọn giá trị dùng khi serialize đối tượng đó. Ví dụ dùng `JsonNode` ở factory để kiểm tra rõ token đầu vào phải là chuỗi, thay vì dựa vào cơ chế ép kiểu scalar của mapper. [Mã nguồn JsonCreator của Jackson](https://raw.githubusercontent.com/FasterXML/jackson-annotations/2.18/src/main/java/com/fasterxml/jackson/annotation/JsonCreator.java), [mã nguồn JsonValue của Jackson](https://raw.githubusercontent.com/FasterXML/jackson-annotations/2.18/src/main/java/com/fasterxml/jackson/annotation/JsonValue.java).

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Objects;
import java.util.Optional;
import java.util.regex.Pattern;

public final class EnumEvolutionDemo {
    public enum KnownStatus {
        PENDING, PAID, SHIPPED
    }

    public record StatusCode(String raw) {
        private static final Pattern FORMAT =
                Pattern.compile("[a-z][a-z0-9_]{0,63}");

        public StatusCode {
            Objects.requireNonNull(raw, "status must not be null");
            if (!FORMAT.matcher(raw).matches()) {
                throw new IllegalArgumentException("Invalid status code format");
            }
        }

        @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
        public static StatusCode fromJson(JsonNode value) {
            if (value == null || !value.isTextual()) {
                throw new IllegalArgumentException("status must be a JSON string");
            }
            return new StatusCode(value.textValue());
        }

        @JsonValue
        public String toJson() {
            return raw;
        }

        public Optional<KnownStatus> known() {
            return switch (raw) {
                case "pending" -> Optional.of(KnownStatus.PENDING);
                case "paid" -> Optional.of(KnownStatus.PAID);
                case "shipped" -> Optional.of(KnownStatus.SHIPPED);
                default -> Optional.empty();
            };
        }
    }

    public record OrderView(String id, StatusCode status) {}

    public static String statusLabel(StatusCode status) {
        return status.known()
                .map(known -> switch (known) {
                    case PENDING -> "Đang chờ";
                    case PAID -> "Đã thanh toán";
                    case SHIPPED -> "Đã gửi hàng";
                })
                .orElse("Trạng thái chưa được hỗ trợ hiển thị");
    }

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        String json = "{\"id\":\"ord_2048\",\"status\":\"delayed\"}";

        OrderView order = mapper.readValue(json, OrderView.class);
        System.out.println(order.status().raw());
        System.out.println(order.status().known().isEmpty());
        System.out.println(statusLabel(order.status()));
        System.out.println(mapper.writeValueAsString(order));
    }
}
```

Kết quả cần quan sát:

```text
delayed
true
Trạng thái chưa được hỗ trợ hiển thị
{"id":"ord_2048","status":"delayed"}
```

Client không hiểu nghĩa của `delayed`, nhưng vẫn giữ nguyên mã. Khi nâng cấp client để biết trạng thái này, bổ sung hằng số, ánh xạ nhận diện và cách hiển thị tương ứng; dữ liệu đã lưu vẫn còn mã gốc.

Có ba giới hạn cần xử lý khi đưa ví dụ vào ứng dụng:

- **Bắt buộc có giá trị:** constructor của `StatusCode` không đảm bảo `OrderView.status` luôn khác null. Jackson có thể xử lý JSON `null` hoặc thuộc tính thiếu mà không gọi factory tạo `StatusCode`. Kiểm tra trường bắt buộc ở DTO bằng validation được kích hoạt thực sự hoặc bằng constructor của DTO; kiểm tra response từ dịch vụ ngoài ở biên tiếp nhận.
- **Tính hợp lệ của mã:** giá trị mới chỉ được chấp nhận nếu vẫn tuân theo định dạng đã cam kết. Tập mở không có nghĩa chấp nhận mọi kiểu JSON hoặc mọi chuỗi vô hạn.
- **Quyền thay đổi resource:** việc client đọc và serialize lại được `status` không có nghĩa server phải cho client gửi nó để thay đổi trạng thái đơn hàng. DTO đọc và DTO ghi có trách nhiệm khác nhau.

Với dịch vụ trung gian cần chuyển tiếp nhiều thuộc tính chưa biết, giữ nguyên enum mới chỉ bảo toàn một trường. Serialize lại DTO có thể làm mất các thuộc tính không được mô hình hóa. Cần thiết kế cách bảo toàn toàn bộ phần dữ liệu mà dịch vụ chịu trách nhiệm chuyển tiếp.

## 8. Java/Jackson: hằng dự phòng khi không cần giữ mã gốc

Nếu ứng dụng chỉ cần phân biệt “đã biết” và “chưa biết”, có thể dùng một hằng dự phòng. Ví dụ sau tiếp tục dùng Jackson 2.x và ánh xạ tường minh mã JSON sang hằng Java:

```java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectReader;

public final class FallbackEnumDemo {
    public enum DisplayStatus {
        @JsonProperty("pending") PENDING,
        @JsonProperty("paid") PAID,
        @JsonProperty("shipped") SHIPPED,
        @JsonEnumDefaultValue UNRECOGNIZED
    }

    public static void main(String[] args) throws Exception {
        ObjectReader reader = new ObjectMapper()
                .readerFor(DisplayStatus.class)
                .with(DeserializationFeature
                        .READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE)
                .with(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS);

        DisplayStatus status = reader.readValue("\"delayed\"");
        System.out.println(status); // UNRECOGNIZED
    }
}
```

Trong Jackson 2.x, `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` cần được bật cùng một hằng được đánh dấu `@JsonEnumDefaultValue`. Chỉ thêm annotation chưa kích hoạt fallback; bật tính năng mà không có hằng mặc định cũng không giải quyết được giá trị lạ. `READ_UNKNOWN_ENUM_VALUES_AS_NULL` là một lựa chọn khác và làm mất sự phân biệt với null. [Tài liệu Jackson về các tính năng deserialization](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features).

Ví dụ cấu hình trên `ObjectReader` dành cho phía đọc response để giới hạn phạm vi tác động. Không bật mặc định cho toàn bộ ứng dụng chỉ để sửa một client tích hợp, vì mapper đó có thể còn đọc request của server.

Hằng `UNRECOGNIZED` không giữ được chuỗi `delayed`. Nếu serialize enum dự phòng, kết quả không tự khôi phục mã ban đầu. Vì vậy, cách này phù hợp với dữ liệu chỉ đọc và hiển thị, không phù hợp khi phải bảo toàn mã qua chu trình đọc → lưu → ghi hoặc chuyển tiếp sang dịch vụ khác.

Cần kiểm tra riêng dữ liệu sai kiểu, chuỗi rỗng, null và chính sách ép kiểu của phiên bản mapper đang dùng. Một cấu hình fallback không thay thế toàn bộ validation của hợp đồng.

## 9. OpenAPI: khai báo đúng lời hứa mở hoặc đóng

Trong JSON Schema, `enum` là ràng buộc chỉ chấp nhận các giá trị được liệt kê. Do đó, schema có `enum: [pending, paid, shipped]` không đồng thời cho phép chuỗi `delayed` chỉ vì description ghi “có thể bổ sung sau”. [JSON Schema: Enumerated values](https://json-schema.org/understanding-json-schema/reference/enum).

Một đoạn `components` cho OpenAPI 3.1 có thể tách hợp đồng đọc và nhập liệu như sau:

```yaml
components:
  schemas:
    OrderStatusRead:
      type: string
      minLength: 1
      maxLength: 64
      pattern: '^[a-z][a-z0-9_]*$'
      description: >-
        Tập mã mở. Các mã hiện được định nghĩa gồm pending, paid,
        shipped và delayed. Có thể bổ sung mã mới đúng định dạng.
        Consumer phải giữ mã chưa biết và dùng cách hiển thị dự phòng;
        không tự suy diễn mã mới thành một trạng thái đã biết.
      examples:
        - pending
        - paid
        - shipped
        - delayed

    OrderRead:
      type: object
      required: [id, status]
      properties:
        id:
          type: string
        status:
          $ref: '#/components/schemas/OrderStatusRead'

    OrderStatusFilter:
      type: string
      enum: [pending, paid, shipped, delayed]
      description: Các bộ lọc trạng thái mà phiên bản server này hỗ trợ.

    DeliveryModeInput:
      type: string
      enum: [standard, express]
      description: Chế độ giao hàng được hỗ trợ khi tạo đơn.

    CreateOrderInput:
      type: object
      required: [deliveryMode]
      properties:
        deliveryMode:
          $ref: '#/components/schemas/DeliveryModeInput'
```

Đây là phần trích để ghép vào tài liệu OpenAPI, chưa phải toàn bộ tài liệu API. Khi tích hợp, tham chiếu `OrderRead` ở response đọc đơn, `OrderStatusFilter` ở query parameter và `CreateOrderInput` ở request body tạo đơn.

Ở schema đọc, `examples` giúp minh họa, không đóng tập giá trị. `type: string` không cho phép null; `required` ở object yêu cầu thuộc tính xuất hiện. Chỉ khai báo `required` mà không quy định kiểu hoặc null chưa đủ diễn đạt cả hai điều kiện này.

Các công cụ có thể hỗ trợ extension như `x-extensible-enum` hoặc một extension riêng của generator. Tiền tố `x-` cho phép mở rộng OpenAPI, nhưng không bảo đảm mọi validator hoặc SDK hiểu cùng ngữ nghĩa. Nếu vẫn giữ `enum` chuẩn bên cạnh extension, validator thông thường vẫn có thể từ chối mã ngoài tập. [OpenAPI 3.1: Specification Extensions](https://spec.openapis.org/oas/v3.1.0.html#specification-extensions).

Một bẫy khác là mô tả tập mở bằng `oneOf` gồm một nhánh enum và một nhánh string tổng quát. Giá trị `paid` khớp cả hai nhánh nên không thỏa yêu cầu chỉ khớp một nhánh của `oneOf`. Với ví dụ này, schema string cùng tài liệu về các mã đã biết đơn giản hơn. `anyOf` có thể cho phép khớp nhiều nhánh, nhưng việc generator có tạo ra kiểu dữ liệu mong muốn hay không vẫn phải được kiểm tra trên công cụ cụ thể. Tham khảo quy tắc tổ hợp trong [OpenAPI 3.1: Schema Object](https://spec.openapis.org/oas/v3.1.0.html#schema-object).

Thêm `default: unknown` vào Schema Object cũng không phải chỉ thị tiêu chuẩn yêu cầu deserializer thay mọi mã lạ bằng `unknown`. Hành vi fallback phải được triển khai và kiểm chứng tại consumer.

## 10. Request không hợp lệ cần lỗi rõ ràng

Giả sử API chỉ hỗ trợ hai chế độ giao hàng nhưng nhận:

```http
POST /orders HTTP/1.1
Content-Type: application/json

{
  "deliveryMode": "teleport"
}
```

Một chính sách lỗi có thể được công bố như sau:

- JSON hỏng hoặc không giải mã được đúng kiểu: trả `400 Bad Request`.
- JSON đọc được, đúng kiểu nhưng mã không thuộc tập nghiệp vụ hỗ trợ: trả `422 Unprocessable Content`.

`422` phù hợp với nội dung có kiểu và cú pháp được hiểu nhưng chỉ dẫn không thể xử lý theo ngữ nghĩa. Đây là chính sách lựa chọn cho API ví dụ; các API khác có thể thống nhất dùng `400` cho lỗi validation nếu tài liệu đã quy định rõ. [RFC 9110, mục 15.5.21](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.21).

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/json

{
  "code": "UNSUPPORTED_DELIVERY_MODE",
  "message": "Chế độ giao hàng chưa được hỗ trợ.",
  "errors": [
    {
      "field": "deliveryMode",
      "allowedValues": ["standard", "express"]
    }
  ]
}
```

Để dùng chính sách `422` này, có thể nhận mã dưới dạng chuỗi, kiểm tra kiểu ở biên JSON rồi validate tập giá trị ở tầng phù hợp. Nếu bind thẳng vào enum đóng, giá trị lạ có thể bị Jackson từ chối trong lúc đọc request; khi đó cần ánh xạ lỗi theo chính sách thực tế của ứng dụng. Không nên hứa `422` trong tài liệu nhưng để framework trả một lỗi `400` không có cấu trúc.

Với `GET /orders?status=...`, một giá trị lọc chưa hỗ trợ cũng cần lỗi tham số rõ ràng theo hợp đồng, chẳng hạn `400`, thay vì bỏ điều kiện lọc.

Không lấy fallback của client đọc response để áp dụng cho request ghi. Âm thầm đổi `teleport` thành `standard` tạo ra đơn hàng khác với ý định của người gọi.

## 11. Đọc được trạng thái chưa đủ để được phép hành động

Khi nhận một mã lạ trong response, hành vi phù hợp phụ thuộc tác động của thao tác:

| Nhu cầu của client | Hành vi với mã chưa biết |
| --- | --- |
| Hiển thị danh sách đơn hàng | Giữ bản ghi, hiển thị nhãn dự phòng |
| Hiển thị mã phục vụ hỗ trợ kỹ thuật | Giữ mã gốc; escape khi đưa vào HTML hoặc giao diện |
| Cho phép cập nhật địa chỉ | Theo khả năng và quy tắc server công bố; server kiểm tra lại |
| Xác nhận đã giao hoặc hoàn tiền | Không suy luận điều kiện từ một mã chưa hiểu |
| Chuyển tiếp resource | Bảo toàn mã gốc trong phạm vi trách nhiệm |

Nếu API cung cấp các khả năng như `canCancel` hoặc liên kết thao tác khả dụng, client có thể dùng chúng để giảm việc hard-code mọi quy tắc theo trạng thái. Tuy nhiên, dữ liệu đó chỉ phản ánh điều kiện tại thời điểm đọc và còn phụ thuộc người dùng hiện tại. Server vẫn phải xác thực, phân quyền và kiểm tra chuyển trạng thái ở mỗi request ghi.

Điều này đặc biệt quan trọng khi dữ liệu được cache hoặc được giữ trên màn hình lâu: một giá trị đã biết như `paid` cũng có thể đã cũ. Enum mô tả trạng thái quan sát được, không phải bằng chứng quyền hạn hay cam kết trạng thái hiện tại.

## 12. Triển khai thêm mã mới theo thứ tự có kiểm soát

Ví dụ cần đưa `delayed` vào hệ thống đang dùng ba trạng thái ban đầu:

1. **Xác định lời hứa hiện tại.** Kiểm tra hợp đồng đã công bố là mở hay đóng, và những consumer nào đang dùng SDK hoặc validator đóng.
2. **Chuẩn bị nơi nhận.** Cập nhật consumer cần thiết, kiểm tra fallback, cách hiển thị và khả năng giữ mã gốc. Client di động hoặc ứng dụng bên ngoài có thể cần thời gian phát hành dài hơn backend.
3. **Chuẩn bị nơi lưu và xử lý.** Kiểm tra ràng buộc cơ sở dữ liệu, worker nền, gateway, dữ liệu xuất và bộ xử lý sự kiện có từ chối mã mới hay không.
4. **Cập nhật mô tả hợp đồng.** Bổ sung ý nghĩa của mã mới, điều kiện chuyển trạng thái và ảnh hưởng tới các thao tác. Không đổi nghĩa các mã cũ để tiết kiệm một giá trị mới.
5. **Cho producer phát mã mới.** Chỉ bật khi các bên bắt buộc hiểu đã sẵn sàng hoặc đã có cơ chế tương thích được thỏa thuận.
6. **Quan sát hành vi thực tế.** Theo dõi lỗi giải mã, lỗi validation và tỷ lệ dùng nhánh dự phòng để phát hiện consumer bị bỏ sót.

Rollback cần được tính trước. Sau khi `delayed` đã được ghi vào dữ liệu, quay lại binary chỉ hiểu ba mã cũ có thể làm server lỗi khi đọc chính cơ sở dữ liệu của nó. Tắt việc phát sinh mã mới không làm những bản ghi đã tồn tại tự biến mất.

Mở rộng khả năng đọc trước rồi mới phát giá trị mới là cách giảm phụ thuộc vào việc mọi bên nâng cấp cùng một thời điểm. Nếu không thể bảo đảm hành vi tương thích, cần một kế hoạch phiên bản hoặc chuyển đổi dữ liệu cụ thể.

## 13. Kiểm thử hợp đồng cho khả năng mở rộng

Cần kiểm tra cả parser, validation và hành vi sử dụng sau khi parse. Các ca dưới đây là gợi ý cho phía tiêu thụ một `status` mở theo hợp đồng của bài:

| Dữ liệu hoặc tình huống | Kỳ vọng |
| --- | --- |
| `"paid"` | Nhận diện là trạng thái đã biết, hiển thị đúng |
| `"delayed"` khi client chỉ biết ba mã cũ | Parse thành công, giữ nguyên mã, dùng nhãn dự phòng |
| `"awaiting_customs"` chưa nằm trong tài liệu mã hiện tại | Vẫn đọc được nếu hợp đồng mở cho phép mã đúng định dạng |
| `""`, chuỗi chỉ có khoảng trắng, mã quá dài | Bị từ chối theo ràng buộc định dạng |
| `42`, `true`, object hoặc array | Bị từ chối vì sai kiểu |
| Null hoặc thiếu `status` bắt buộc | Bị phát hiện tại validation của DTO hoặc biên nhận |
| Một trang có cả trạng thái đã biết và chưa biết | Giữ đủ phần tử, không làm sai phân trang |
| Đọc rồi serialize mã chưa biết bằng mô hình giữ raw | Mã không bị đổi thành tên hằng dự phòng |
| Nhận mã chưa biết rồi thực hiện thao tác có tác động | Không tự suy diễn trạng thái thành điều kiện cho phép |

Đối với input đóng, bổ sung các ca mã không hỗ trợ, sai hoa/thường, query filter lạ và kiểm tra lỗi HTTP đúng hợp đồng. Không chỉ kiểm tra một exception Java, vì người gọi nhìn thấy status code và response body.

Một ca tích hợp có giá trị là chạy **client cũ với response mới**. Nếu chỉ sinh lại SDK mới rồi chạy test, client đã biết mã mới nên chưa kiểm chứng được khả năng tương thích của client đang được người dùng sử dụng.

Các fixture cho test nên do hợp đồng quản lý. Không lấy trực tiếp danh sách hằng enum hiện tại để sinh toàn bộ dữ liệu test, vì khi đó bộ test khó phát hiện một mã mà consumer chưa biết.

## 14. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách điều chỉnh |
| --- | --- | --- |
| Xuất `ordinal()` của enum Java | Phụ thuộc thứ tự khai báo | Dùng mã công khai tường minh, ổn định |
| Dùng cùng một enum cho DB, request, response và SDK | Mọi thay đổi bị buộc lan qua các lớp | Tách mô hình theo trách nhiệm và ánh xạ rõ ràng |
| Response khai báo enum đóng nhưng tài liệu hứa mở | Máy và người đọc hiểu khác nhau | Đồng bộ ràng buộc schema với chính sách tiến hóa |
| Coi mã mới là `paid` để tránh lỗi | Tự tạo ý nghĩa nghiệp vụ | Dùng nhánh chưa biết riêng hoặc từ chối khi bắt buộc hiểu |
| Đổi mã lạ thành null rồi tiếp tục | Mất lý do thiếu dữ liệu | Giữ raw hoặc dùng kiểu dự phòng tường minh |
| Gửi `UNRECOGNIZED` của SDK trở lại server | Không còn mã gốc; có thể không thuộc input hợp lệ | Dùng mô hình giữ raw khi cần chuyển tiếp |
| Bỏ qua thuộc tính lạ rồi cho rằng enum đã an toàn | Hai tình huống giải mã khác nhau | Kiểm tra riêng thuộc tính và giá trị chưa biết |
| Tự thêm một mã vào output enum đóng | Client cũ có thể lỗi | Đánh giá tương thích và điều phối phát hành |
| Ghi mỗi mã lạ thành một nhãn metric riêng | Số lượng nhãn có thể tăng không kiểm soát | Tổng hợp metric có giới hạn; dùng log được giới hạn và làm sạch khi cần |
| Tắt tính năng mới rồi rollback về mã chỉ đọc tập cũ | Dữ liệu mới vẫn còn trong hệ thống | Chuẩn bị khả năng đọc hoặc chuyển đổi dữ liệu trước rollback |

## 15. Khi nào cần một resource danh mục thay vì enum?

Không phải mọi danh sách lựa chọn đều nên đóng vào schema hoặc mã nguồn. Nếu giá trị do quản trị viên thêm thường xuyên, có tên bản địa hóa, có hiệu lực theo thời gian hoặc khác nhau theo tenant, một resource danh mục có thể phù hợp hơn:

```http
GET /shipping-methods HTTP/1.1
```

```json
{
  "items": [
    {
      "id": "ship_standard",
      "code": "standard",
      "displayName": "Giao tiêu chuẩn",
      "active": true
    },
    {
      "id": "ship_express",
      "code": "express",
      "displayName": "Giao nhanh",
      "active": true
    }
  ]
}
```

Request có thể tham chiếu `shippingMethodId`; server kiểm tra phương thức còn hoạt động và có áp dụng cho người gọi hay không. Danh mục giúp client lấy lựa chọn động nhưng vẫn cần quy tắc cho mã hoặc ID đã ngừng hoạt động, dữ liệu cache cũ và tài nguyên được lưu từ trước.

Ngược lại, các giá trị chọn hành vi cốt lõi mà phần mềm phải triển khai riêng thường cần hợp đồng chặt chẽ. Việc biến chúng thành một endpoint danh mục không làm client tự hiểu được một thuật toán hoặc một thao tác mới.

## 16. Thực hành trên API đơn hàng

Với API có `GET /orders/{id}`, `GET /orders?status=...` và `POST /orders`, hãy áp dụng các quyết định của bài:

1. Mô tả `status` trong response là tập mở có định dạng mã ổn định; mô tả `deliveryMode` trong request tạo đơn là tập đóng.
2. Xây dựng kiểu đọc giữ mã gốc cùng phần trạng thái đã biết, hoặc chọn hằng dự phòng nếu đã chấp nhận rõ việc mất mã gốc.
3. Cho client cũ nhận response chứa `delayed`; xác nhận vẫn đọc được ID, giữ phần tử trong danh sách và không kích hoạt thao tác dựa trên trạng thái chưa hiểu.
4. Gửi `deliveryMode=teleport` và query filter chưa hỗ trợ; xác nhận API trả lỗi đúng chính sách thay vì tự sửa hoặc bỏ điều kiện.
5. Kiểm tra schema OpenAPI, cấu hình mapper, SDK và hành vi giao diện cùng thực hiện một lời hứa về khả năng mở rộng.

Kết quả cần thể hiện là một hợp đồng nhất quán từ JSON đến hành vi: mã công khai giữ ý nghĩa ổn định; dữ liệu mới được đọc theo chính sách đã công bố; dữ liệu không hợp lệ bị phát hiện; những quyết định bắt buộc hiểu trạng thái vẫn được kiểm tra đúng nơi.
