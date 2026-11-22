# Ghi thuộc tính mở rộng bằng JsonAnyGetter

Trong nhiều API, một object có một số thuộc tính cố định nhưng cũng cần mang theo các thuộc tính mở rộng do hệ thống khác cung cấp. Ví dụ, một sự kiện luôn có `eventId`, `eventType` và `createdAt`, nhưng mỗi loại sự kiện lại có thêm một tập dữ liệu riêng. Nếu không muốn tạo một field Java riêng cho từng thuộc tính động, ta có thể lưu chúng trong `Map<String, Object>`.

Jackson cung cấp annotation `@JsonAnyGetter` để ghi các entry của map đó thành **các thuộc tính ngang hàng** với những thuộc tính cố định của object khi serialize. Nhờ vậy, JSON đầu ra có cấu trúc phẳng theo hợp đồng mong muốn, thay vì lồng map vào một property riêng như `attributes`.

Ví dụ, object Java có thể chứa `eventId` và map `attributes`, nhưng JSON đầu ra sẽ có dạng:

```json
{
  "eventId": "EVT-1001",
  "region": "north",
  "retryCount": 2,
  "source": "mobile"
}
```

`region`, `retryCount` và `source` đến từ map mở rộng. Chúng được ghi như các property thông thường của JSON object. Đây là vai trò chính của `@JsonAnyGetter` trong nhóm tính năng cấu trúc mở của Jackson.

## 1. Vấn đề khi object có thuộc tính động

Với mô hình cố định, ta thường khai báo mỗi thuộc tính thành một field:

```java
public class Device {
    private String id;
    private String model;
    private String firmwareVersion;
}
```

Nhưng có những trường hợp danh sách thuộc tính không thể biết trước:

- Metadata của sự kiện phụ thuộc vào từng `eventType`.
- Các thuộc tính tùy biến do người dùng cấu hình.
- Thông tin mở rộng đến từ nhiều đối tác có schema khác nhau.
- Một gateway cần chuyển tiếp các trường chưa biết mà không thay đổi DTO mỗi khi upstream bổ sung field.
- Một object có phần lõi ổn định và một vùng metadata linh hoạt.

Ta có thể dùng map để giữ phần động:

```java
public class Event {
    private String eventId;
    private Map<String, Object> attributes;
}
```

Nếu không có cấu hình đặc biệt, Jackson serialize `attributes` thành một property lồng nhau:

```json
{
  "eventId": "EVT-1001",
  "attributes": {
    "region": "north",
    "retryCount": 2
  }
}
```

Cấu trúc này hoàn toàn hợp lệ và có thể là lựa chọn tốt nếu hợp đồng API muốn gom dữ liệu mở rộng vào một object con. Nhưng nếu hợp đồng yêu cầu `region` và `retryCount` nằm trực tiếp cùng cấp với `eventId`, `@JsonAnyGetter` giúp tạo ra cấu trúc đó.

## 2. @JsonAnyGetter hoạt động như thế nào?

`@JsonAnyGetter` đánh dấu một accessor (thường là method getter) trả về các thuộc tính bổ sung cần được ghi vào JSON object đang serialize. Thông thường accessor trả về `Map<String, ?>` hoặc một map tương thích, trong đó:

- Key trở thành tên property trong JSON.
- Value được serialize theo serializer phù hợp với kiểu runtime hoặc kiểu generic đã biết.
- Mỗi entry được ghi như một property ngang hàng với các property thông thường của object.

Ví dụ tối giản:

```java
import com.fasterxml.jackson.annotation.JsonAnyGetter;

import java.util.LinkedHashMap;
import java.util.Map;

public class Event {
    private String eventId;
    private final Map<String, Object> attributes = new LinkedHashMap<>();

    public Event(String eventId) {
        this.eventId = eventId;
    }

    public String getEventId() {
        return eventId;
    }

    public void addAttribute(String name, Object value) {
        attributes.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> any() {
        return attributes;
    }
}
```

Tạo object và serialize:

```java
ObjectMapper mapper = new ObjectMapper();

Event event = new Event("EVT-1001");
event.addAttribute("region", "north");
event.addAttribute("retryCount", 2);
event.addAttribute("source", "mobile");

String json = mapper.writeValueAsString(event);
System.out.println(json);
```

JSON có cấu trúc tương đương:

```json
{
  "eventId": "EVT-1001",
  "region": "north",
  "retryCount": 2,
  "source": "mobile"
}
```

Lưu ý rằng JSON không có property tên `any` hoặc `attributes`. Tên method `any()` chỉ là accessor để Jackson lấy map; annotation yêu cầu Jackson ghi các entry của map trực tiếp vào object đầu ra.

## 3. So sánh không dùng và có dùng JsonAnyGetter

| Cách khai báo | JSON đầu ra minh họa | Ý nghĩa |
| --- | --- | --- |
| Getter map thông thường | `{"eventId":"EVT-1","attributes":{"region":"north"}}` | Map được ghi như một property lồng nhau. |
| Getter có `@JsonAnyGetter` | `{"eventId":"EVT-1","region":"north"}` | Các entry của map được trải phẳng thành property cùng cấp. |

Ví dụ hai kiểu accessor:

```java
public Map<String, Object> getAttributes() {
    return attributes;
}
```

và:

```java
@JsonAnyGetter
public Map<String, Object> getAttributes() {
    return attributes;
}
```

Khác biệt nằm ở annotation. Getter thông thường tạo property `attributes`; getter có `@JsonAnyGetter` phát các entry của map vào object JSON hiện tại.

## 4. Dùng kiểu value cụ thể thay cho Object khi có thể

Ví dụ trên dùng `Map<String, Object>` để minh họa dữ liệu động. Đây là lựa chọn linh hoạt, nhưng value có thể là nhiều kiểu khác nhau: string, number, boolean, list, map hoặc object Java khác.

Nếu vùng mở rộng có schema rõ hơn, hãy dùng kiểu cụ thể:

```java
private final Map<String, String> labels = new LinkedHashMap<>();

@JsonAnyGetter
public Map<String, String> labels() {
    return labels;
}
```

Hoặc nếu cần giữ cấu trúc JSON động:

```java
private final Map<String, JsonNode> extensions = new LinkedHashMap<>();

@JsonAnyGetter
public Map<String, JsonNode> extensions() {
    return extensions;
}
```

Chọn kiểu value phù hợp đem lại lợi ích:

- `Map<String, String>` giới hạn dữ liệu mở rộng vào chuỗi.
- `Map<String, Object>` linh hoạt, nhưng code sử dụng phải chấp nhận nhiều kiểu runtime.
- `Map<String, JsonNode>` phù hợp khi dữ liệu đã ở dạng JSON tree và cần giữ kiểu node rõ ràng.
- `Map<String, CustomValue>` phù hợp khi mỗi entry có một cấu trúc Java xác định.

`@JsonAnyGetter` không yêu cầu mọi value phải là scalar. Value có thể là object hoặc array; Jackson sẽ serialize chúng thành JSON object/array lồng bên dưới property tương ứng.

Ví dụ map:

```java
event.addAttribute("tags", List.of("java", "jackson"));
event.addAttribute("location", Map.of("city", "HCMC", "country", "VN"));
```

JSON đầu ra có thể là:

```json
{
  "eventId": "EVT-1001",
  "tags": ["java", "jackson"],
  "location": {
    "city": "HCMC",
    "country": "VN"
  }
}
```

Map ngoài được trải phẳng; cấu trúc của từng value vẫn được giữ theo kiểu dữ liệu tương ứng.

## 5. Tên property động phải là tên JSON hợp lệ

Key của map trở thành tên field JSON. Jackson sẽ escape các ký tự cần thiết trong tên property khi ghi JSON, ví dụ dấu nháy kép hoặc dấu gạch chéo ngược. Tuy nhiên, ứng dụng vẫn nên kiểm soát key theo hợp đồng dữ liệu.

Ví dụ key:

```java
event.addAttribute("display name", "Sensor A");
event.addAttribute("custom\"key", "value");
```

Jackson có thể escape tên field để tạo JSON hợp lệ. Nhưng một key hợp lệ về cú pháp JSON chưa chắc hợp lệ về nghiệp vụ. API có thể yêu cầu tên key theo mẫu nhất định, giới hạn độ dài, cấm prefix nội bộ hoặc cấm các tên reserved.

Nên validate key tại method thêm dữ liệu hoặc tầng nghiệp vụ:

```java
public void addAttribute(String name, Object value) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Tên thuộc tính không được để trống");
    }
    if (name.equals("eventId")) {
        throw new IllegalArgumentException("Tên thuộc tính bị trùng với field cố định");
    }
    attributes.put(name, value);
}
```

Ví dụ này minh họa kiểm tra một tên reserved. Trong ứng dụng thực tế, có thể cần một tập tên reserved, quy tắc ký tự, độ dài và chính sách phân biệt chữ hoa/chữ thường.

## 6. Tránh trùng key giữa thuộc tính cố định và map mở rộng

Một điểm cần đặc biệt chú ý là map có thể chứa key trùng với property thông thường của class.

Ví dụ object có property cố định `eventId`, nhưng map cũng chứa key `eventId`:

```java
Event event = new Event("EVT-1001");
event.addAttribute("eventId", "OVERRIDE");
```

Khi serialize, cả property thông thường và entry any-getter có thể cùng tạo ra tên field `eventId` trong JSON. JSON object không nên chứa các tên property trùng lặp vì consumer có thể diễn giải khác nhau: có parser giữ giá trị đầu, có parser giữ giá trị cuối, hoặc từ chối payload theo chính sách duplicate detection.

Jackson không nên được dùng như cơ chế giải quyết xung đột tên giữa map mở rộng và property cố định. Hãy ngăn xung đột trước khi serialize:

- Đặt danh sách tên reserved cho các field cố định.
- Từ chối key trùng trong `addAttribute()`.
- Hoặc đặt namespace/prefix cho key mở rộng, ví dụ `ext_region`, nếu hợp đồng cho phép.

Nếu API có schema công khai, hãy ghi rõ vùng tên nào dành cho property cố định và vùng nào dành cho property mở rộng. Điều này giúp tránh xung đột khi phiên bản DTO bổ sung field mới trong tương lai.

## 7. Thứ tự thuộc tính khi ghi

Nếu map dùng `LinkedHashMap`, thứ tự iteration giữ thứ tự thêm entry. Vì vậy, các thuộc tính được ghi qua `@JsonAnyGetter` thường xuất hiện theo thứ tự iteration của map, sau các property thông thường theo thứ tự serializer đã chọn.

Ví dụ:

```java
Map<String, Object> attributes = new LinkedHashMap<>();
attributes.put("first", 1);
attributes.put("second", 2);
attributes.put("third", 3);
```

`HashMap` không bảo đảm thứ tự iteration ổn định. Nếu consumer hoặc snapshot test cần output dễ dự đoán, hãy chọn `LinkedHashMap` hoặc map có thứ tự phù hợp.

Tuy nhiên, theo mô hình dữ liệu JSON, thứ tự property của object không nên mang ý nghĩa nghiệp vụ. Nếu thứ tự là một phần của dữ liệu, hãy biểu diễn bằng JSON array. Các cấu hình như `@JsonPropertyOrder` có thể điều khiển thứ tự property được databind ghi, nhưng không nên dựa vào thứ tự object như một giao thức thay thế array.

## 8. Giá trị null trong map mở rộng

Một entry map có value `null` có thể được serialize thành property có giá trị JSON null, tùy chính sách inclusion và cấu hình serializer:

```java
event.addAttribute("description", null);
```

JSON có thể chứa:

```json
{
  "eventId": "EVT-1001",
  "description": null
}
```

Nếu hợp đồng muốn bỏ các entry null, có thể dùng cấu hình inclusion phù hợp trên kiểu hoặc mapper, nhưng cần hiểu phạm vi ảnh hưởng. Ví dụ `@JsonInclude(JsonInclude.Include.NON_NULL)` trên class có thể ảnh hưởng các property của class theo quy tắc inclusion; hành vi cụ thể với any-getter/map content còn phụ thuộc phiên bản và cách serializer xử lý map.

Không nên mặc định rằng `@JsonInclude` trên getter any-getter sẽ luôn có cùng ý nghĩa với annotation trên một map property thông thường. Nếu cần bỏ null trong vùng mở rộng, hãy cấu hình và kiểm thử đúng phiên bản Jackson của dự án. Một cách đơn giản khác là không đưa entry null vào map ngay từ tầng nghiệp vụ.

## 9. JsonAnyGetter chỉ điều khiển serialization

`@JsonAnyGetter` là cơ chế **ghi** thuộc tính động ra JSON. Nó không tự động thu thập các trường lạ khi đọc JSON.

Nếu cần cả hai chiều, thường kết hợp:

- `@JsonAnyGetter` để phát các entry của map thành sibling properties khi serialize.
- `@JsonAnySetter` để nhận các property chưa được ánh xạ vào field cố định khi deserialize.

Ví dụ đầy đủ:

```java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;

import java.util.LinkedHashMap;
import java.util.Map;

public class ExtensibleEvent {
    private String eventId;
    private final Map<String, Object> extensions = new LinkedHashMap<>();

    public String getEventId() {
        return eventId;
    }

    public void setEventId(String eventId) {
        this.eventId = eventId;
    }

    @JsonAnyGetter
    public Map<String, Object> getExtensions() {
        return extensions;
    }

    @JsonAnySetter
    public void addExtension(String name, Object value) {
        extensions.put(name, value);
    }
}
```

Deserialize JSON:

```json
{
  "eventId": "EVT-1001",
  "region": "north",
  "retryCount": 2
}
```

`eventId` được ánh xạ vào property cố định. Các trường chưa được nhận diện như `region` và `retryCount` được chuyển đến any-setter và lưu trong `extensions`. Khi serialize lại, `@JsonAnyGetter` phát chúng thành sibling properties, tạo cấu trúc tương tự input.

Đây là một mẫu hữu ích cho DTO có vùng mở rộng. Tuy nhiên, nếu cần phân biệt trường lạ với lỗi đánh máy, hãy cân nhắc chính sách unknown property và validation thay vì thu thập mọi trường một cách vô điều kiện.

## 10. So sánh JsonAnyGetter và JsonAnySetter

| Annotation | Hướng | Vai trò | Hình thức thường dùng |
| --- | --- | --- | --- |
| `@JsonAnyGetter` | Serialize: Java → JSON | Lấy map và ghi từng entry thành property của object JSON | Method trả về `Map<String, ?>` |
| `@JsonAnySetter` | Deserialize: JSON → Java | Nhận property chưa ánh xạ vào property cố định | Method nhận `(String name, value)` hoặc map phù hợp |

Hai annotation bổ sung cho nhau nhưng không thay thế nhau. Chỉ có `@JsonAnyGetter` thì map có thể được ghi phẳng, nhưng Jackson không tự biết phải đưa trường lạ từ JSON vào map khi đọc. Chỉ có `@JsonAnySetter` thì có thể thu thập trường lạ khi đọc, nhưng việc ghi map thành sibling properties cần any-getter.

## 11. JsonAnyGetter không phải JsonUnwrapped

Hai tính năng có thể tạo JSON phẳng nhưng phục vụ mô hình khác nhau:

- `@JsonAnyGetter` phát các entry của map thành các property động. Tên property đến từ key trong map.
- `@JsonUnwrapped` trải các property của một object con vào object cha theo quy tắc tên/tiền tố/hậu tố. Nó phù hợp khi object con có kiểu Java xác định.

Ví dụ `@JsonUnwrapped`:

```java
public class Address {
    private String city;
    private String country;
}

public class Customer {
    private String name;

    @JsonUnwrapped(prefix = "address_")
    private Address address;
}
```

JSON có thể có các field `address_city` và `address_country` cùng cấp với `name`. Trong khi đó, `@JsonAnyGetter` phù hợp với map có tên field chỉ biết tại runtime.

Hãy chọn `@JsonUnwrapped` khi cấu trúc object con có kiểu cố định; chọn `@JsonAnyGetter` khi các property mở rộng được lưu theo key động.

## 12. Tổ chức API an toàn với vùng mở rộng

Một vùng mở rộng làm DTO linh hoạt hơn nhưng cũng làm hợp đồng API khó dự đoán hơn. Nên xác định rõ:

1. **Nguồn dữ liệu:** ai được phép thêm property động — client, đối tác hay service nội bộ?
2. **Tên field:** có quy tắc ký tự, độ dài, prefix hoặc danh sách reserved không?
3. **Kiểu value:** chấp nhận mọi kiểu JSON hay chỉ string/number/boolean?
4. **Kích thước:** giới hạn số entry, độ sâu object lồng nhau và tổng kích thước payload.
5. **Xung đột:** xử lý thế nào nếu key map trùng với field cố định?
6. **Đọc lại:** trường không biết có được thu thập bằng `@JsonAnySetter` hay phải báo lỗi?
7. **Versioning:** khi DTO bổ sung property cố định mới, có thể xung đột với key mở rộng cũ hay không?

Không nên cho phép map mở rộng ghi đè các trường điều khiển như `role`, `ownerId`, `status` hoặc `permissions` nếu chúng có ý nghĩa bảo mật/nghiệp vụ. Hãy validate key và value tại ranh giới nhận dữ liệu, không dựa vào thứ tự serialize để quyết định giá trị nào thắng.

## 13. Khi nào nên dùng JsonAnyGetter?

`@JsonAnyGetter` phù hợp khi:

- JSON contract yêu cầu thuộc tính mở rộng nằm cùng cấp với các field cố định.
- Tên property chỉ biết tại runtime.
- Một object có phần lõi ổn định và metadata động.
- Cần chuyển tiếp dữ liệu mở rộng mà không định nghĩa trước từng field.
- Dữ liệu bổ sung có thể được quản lý trong map và validate theo quy tắc riêng.

Không nhất thiết phải dùng annotation này nếu hợp đồng API muốn giữ map trong một property rõ ràng như `metadata` hoặc `attributes`. Cấu trúc lồng nhau thường dễ phân biệt vùng mở rộng với field lõi hơn và giảm nguy cơ trùng tên.

Nếu schema cần kiểm soát chặt, DTO có field rõ ràng có thể phù hợp hơn. Nếu chỉ một số loại sự kiện có thêm thuộc tính, có thể dùng subtype hoặc DTO riêng. Hãy chọn cấu trúc JSON theo hợp đồng và khả năng kiểm soát dữ liệu, không chỉ vì annotation có sẵn.

## 14. Ghi nhớ

- `@JsonAnyGetter` đánh dấu accessor trả về map các thuộc tính mở rộng cần được serialize.
- Mỗi entry của map được ghi thành property ngang hàng trong JSON object, không tạo một property map lồng nhau.
- Key của map trở thành tên field JSON; value được serialize theo kiểu tương ứng.
- Dùng kiểu value cụ thể khi có thể; `Map<String, Object>` linh hoạt nhưng cần kiểm tra kiểu runtime.
- Tránh key trùng với field cố định để không tạo JSON có tên property trùng lặp.
- `LinkedHashMap` giúp thứ tự iteration ổn định hơn, nhưng thứ tự property của JSON object không nên mang ý nghĩa nghiệp vụ.
- `@JsonAnyGetter` chỉ phục vụ serialization; kết hợp `@JsonAnySetter` nếu cần thu thập trường mở rộng khi deserialize.
- `@JsonAnyGetter` khác `@JsonUnwrapped`: một bên trải map động, một bên trải property của object con có kiểu xác định.
- Validate tên key, kiểu value, kích thước và quyền ghi dữ liệu mở rộng ở tầng ứng dụng.

Khi thiết kế cấu trúc mở, hãy giữ phần lõi của object rõ ràng và quản lý vùng mở rộng như một hợp đồng riêng. `@JsonAnyGetter` giúp biểu diễn map thành các field cùng cấp một cách thuận tiện, còn việc kiểm soát tên field, xung đột và dữ liệu đầu vào vẫn thuộc trách nhiệm của ứng dụng.
