# Map lồng nhau, collection và các kiểu giá trị JSON

## Mục tiêu bài học

Khi ứng dụng Java dùng **Spring Vault** để đọc secrets từ HashiCorp Vault thông qua `VaultTemplate` hoặc `VaultOperations`, giá trị trả về thường không chỉ là một chuỗi. Một secret có thể chứa đối tượng lồng nhau, danh sách server, cờ bật/tắt, số nguyên, số thập phân hoặc `null`. Ứng dụng cần hiểu cách các kiểu **JSON** xuất hiện trong `Map<String, Object>` trước khi sử dụng chúng trong nghiệp vụ.

Bài học này thuộc chương **Ánh xạ dữ liệu**. Sau khi học, bạn có thể:

1. Nhận diện object, array, string, number, boolean và null trong dữ liệu Vault.
2. Duyệt `Map` lồng nhau và các collection chứa object mà không phụ thuộc vào ép kiểu generic thiếu an toàn.
3. Phân biệt phần `data` của phản hồi Vault với các trường JSON `data` do secrets engine tạo ra, đặc biệt ở KV v2.
4. Kiểm tra dữ liệu thiếu, sai kiểu, số vượt phạm vi và collection rỗng trước khi tạo cấu hình Java.
5. Lựa chọn giữa truy cập `Map<String, Object>` và ánh xạ vào DTO có kiểu, đồng thời tránh lộ secrets trong log và thông báo lỗi.

> **Giả định:** Ứng dụng đã được cấu hình kết nối tới Vault bằng Spring Vault và xác thực phù hợp với workload (chẳng hạn AppRole hoặc Kubernetes); Vault policy cho phép đọc đường dẫn sử dụng trong ví dụ. Bài tập trung vào ánh xạ dữ liệu. Cấp quyền, vòng đời token/lease, Transit encryption, PKI, giám sát và kiểm thử tích hợp có quy trình riêng trong phạm vi học Spring Vault.

## 1. Một secret có thể là cấu trúc JSON phức tạp

Giả sử một dịch vụ đặt hàng lưu secret tại đường dẫn logic `checkout/runtime` trong KV v2 mount `secret`. Phần **dữ liệu nghiệp vụ** của secret là:

```json
{
  "service": "checkout",
  "enabled": true,
  "maxConnections": 20,
  "samplingRate": 0.75,
  "apiToken": "<gia-tri-bi-mat>",
  "retryPolicy": {
    "maxAttempts": 3,
    "backoffMillis": 250
  },
  "regions": ["ap-southeast-1", "eu-west-1"],
  "targets": [
    { "id": "primary", "url": "https://primary.internal.example", "weight": 80 },
    { "id": "backup", "url": "https://backup.internal.example", "weight": 20 }
  ],
  "description": null
}
```

Đây là **JSON hợp lệ** và cố ý chứa các kiểu khác nhau:

- `service`, `apiToken`: chuỗi (`string`), trong đó `apiToken` là dữ liệu nhạy cảm.
- `enabled`: giá trị logic (`boolean`).
- `maxConnections`: số nguyên về mặt nghiệp vụ; `samplingRate`: số thập phân về mặt nghiệp vụ. Cả hai đều thuộc kiểu JSON `number`.
- `retryPolicy`: object, có thể trở thành một `Map` bên trong `Map` khác.
- `regions`: array các chuỗi, thường được biểu diễn dưới dạng `List` khi đọc dữ liệu chưa định kiểu.
- `targets`: array các object, thường được biểu diễn như `List` chứa các `Map`.
- `description`: JSON `null`. Trường tồn tại với giá trị null, khác với trường không xuất hiện.

Sơ đồ của phần dữ liệu này:

```text
Map<String, Object> data
├── "service"         → String
├── "enabled"         → Boolean
├── "maxConnections"  → Number
├── "samplingRate"    → Number
├── "apiToken"        → String (bí mật)
├── "retryPolicy"     → Map
│   ├── "maxAttempts"   → Number
│   └── "backoffMillis" → Number
├── "regions"         → List
│   ├── String
│   └── String
├── "targets"         → List
│   ├── Map { id, url, weight }
│   └── Map { id, url, weight }
└── "description"     → null
```

Không phải mọi secret đều có cấu trúc này. Vault cho phép các secrets engine trả về payload khác nhau; chương trình phải dựa trên hợp đồng dữ liệu của **endpoint và đường dẫn cụ thể**.

## 2. Các kiểu JSON được biểu diễn trong Java như thế nào?

JSON chỉ định sáu nhóm giá trị: `object`, `array`, `string`, `number`, `boolean` và `null`. Khi Spring Vault đọc dữ liệu chưa ánh xạ vào DTO, các giá trị được chuyển thành các đối tượng Java tương ứng theo cơ chế chuyển đổi JSON của client.

| Giá trị JSON | Kiểu Java thường gặp khi dữ liệu chưa định kiểu | Điều cần kiểm tra |
|---|---|---|
| `{ "key": "value" }` | `Map<String, Object>` hoặc một `Map` tương thích | Key có dạng chuỗi; value cần kiểm tra tiếp từng cấp |
| `["a", "b"]` | `List<?>` với phần tử `String` | Kiểu phần tử, số lượng, thứ tự |
| `[{"id": 1}]` | `List<?>` với phần tử kiểu `Map` | Không suy ra mọi phần tử đều là `Map<String, Object>` |
| `"hello"` | `String` | Rỗng, định dạng, giới hạn độ dài |
| `12` | Một lớp con của `Number`, thường là `Integer` hoặc `Long` | Không ép cứng vào `Integer`; kiểm tra phạm vi |
| `1.25` | Một lớp con của `Number`, có thể là `Double`/`BigDecimal` tùy cấu hình | Độ chính xác và quy tắc làm tròn |
| `true`, `false` | `Boolean` | Không coi chuỗi `"true"` là Boolean nếu chưa định nghĩa quy tắc chuyển đổi |
| `null` | `null` | Phân biệt giá trị null với key bị thiếu |

Các lớp Java cụ thể của `Map`, `List` và `Number` phụ thuộc thư viện và cấu hình deserialize; **đừng xây dựng logic nghiệp vụ dựa vào tên lớp triển khai**, ví dụ giả định mọi array luôn là `ArrayList` hay mọi số nguyên luôn là `Integer`.

### 2.1. JSON không có kiểu ngày giờ hoặc dữ liệu nhị phân riêng

Một giá trị như `"2026-11-25T08:00:00Z"` vẫn chỉ là **chuỗi JSON**. Nếu nghiệp vụ yêu cầu mốc thời gian, hãy chuyển `String` sang `Instant`, xử lý lỗi định dạng và múi giờ ở tầng Java. Tương tự, dữ liệu nhị phân thường được biểu diễn bằng chuỗi theo một quy ước đã thống nhất, chẳng hạn Base64; **không** tự hiểu mọi chuỗi là byte array.

### 2.2. JSON number không đồng nghĩa một kiểu số Java cố định

`0.75`, `75`, `7.5e1` đều là JSON number. Việc một bộ chuyển đổi trả `Integer`, `Long`, `Double` hay `BigDecimal` là chi tiết của quá trình giải mã và cấu hình. Vì vậy, đoạn sau thiếu an toàn:

```java
Integer maxConnections = (Integer) data.get("maxConnections");
```

Nếu giá trị thực tế là `Long`, phép ép kiểu sẽ ném `ClassCastException` dù dữ liệu có thể là số nguyên hợp lệ. Hãy kiểm tra bằng `instanceof Number`, sau đó chuyển đổi với quy tắc về khoảng giá trị và phần thập phân. Với số tiền hoặc giá trị yêu cầu độ chính xác tuyệt đối, phải thiết kế biểu diễn và converter phù hợp ngay từ bước deserialize; chuyển một giá trị `Double` đã mất chính xác sang `BigDecimal` không phục hồi các chữ số bị mất.

## 3. Lấy đúng dữ liệu nghiệp vụ từ Spring Vault

**Hai tầng lồng nhau dễ bị nhầm:** (1) payload phản hồi do Vault trả về; (2) cấu trúc object/array bên trong secret. Với KV v2 còn có một lớp `data` riêng do endpoint của engine thiết kế.

### 3.1. Gọi API KV v2 qua `VaultKeyValueOperations`

```java
import java.util.Map;

import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
        "secret", KeyValueBackend.KV_2);

VaultResponse response = kv.get("checkout/runtime");
if (response == null || response.getData() == null) {
    throw new IllegalStateException("Chưa có cấu hình checkout");
}

Map<String, Object> data = response.getRequiredData();
Object retryPolicy = data.get("retryPolicy"); // Object, chưa phải Map có kiểu
Object targets = data.get("targets");         // Object, chưa phải List có kiểu
```

`vaultOperations` trong ví dụ là biến kiểu `VaultOperations` đã được ứng dụng cung cấp qua dependency injection. Dùng `opsForKeyValue("secret", KV_2)` giúp Spring Vault xử lý khác biệt của đường dẫn và cấu trúc dữ liệu KV v2; `"checkout/runtime"` là **đường dẫn logic tương đối với mount**.

Ở cách đọc này, `data` chứa trực tiếp `retryPolicy` và `targets` của secret. Chú ý `getData()` có thể trả `null`, còn `getRequiredData()` ném `IllegalStateException` nếu `data` là `null`; cả hai đều không thay thế kiểm tra `response == null`.

### 3.2. Khi đọc thẳng endpoint KV v2 bằng `VaultOperations.read(...)`

Đường dẫn API KV v2 có thêm đoạn `data/`. Nếu đọc trực tiếp:

```java
VaultResponse raw = vaultOperations.read("secret/data/checkout/runtime");
```

phản hồi JSON có cấu trúc rút gọn:

```json
{
  "data": {
    "data": {
      "retryPolicy": { "maxAttempts": 3, "backoffMillis": 250 },
      "regions": ["ap-southeast-1", "eu-west-1"]
    },
    "metadata": {
      "version": 4
    }
  }
}
```

Lúc này `raw.getData()` trỏ đến object chứa **`data` và `metadata` của KV v2**; cần lấy `raw.getData().get("data")` để tới object nghiệp vụ. `metadata.version` là metadata phiên bản do KV v2 cung cấp, không phải một thuộc tính nghiệp vụ như `retryPolicy.maxAttempts`. Không nhầm nó với các trường metadata bao ngoài khác của `VaultResponseSupport`.

Nên dùng `VaultKeyValueOperations` cho nhu cầu đọc dữ liệu KV thông thường để tránh tự thêm `data/` vào path và tự bóc các lớp bao ngoài. Chỉ đọc trực tiếp khi thực sự cần thao tác với dạng phản hồi endpoint cụ thể và đã hiểu cấu trúc của nó.

## 4. Duyệt `Map` lồng nhau an toàn

Sau khi đọc `Map<String, Object> data`, cách ngắn nhất để lấy số lần thử lại là:

```java
Object retry = data.get("retryPolicy");
```

Nhưng `retry` vẫn có kiểu `Object`. Mã thiếu an toàn thường gặp:

```java
@SuppressWarnings("unchecked")
Map<String, Object> retryMap =
        (Map<String, Object>) data.get("retryPolicy");

int attempts = (Integer) retryMap.get("maxAttempts");
```

Đoạn mã có thể biên dịch nhưng **ép kiểu generic không kiểm tra được kiểu của từng key/value ở runtime**. Nó có thể lỗi vì `retryPolicy` là `null`, không phải object, hoặc `maxAttempts` không phải `Integer`.

Một hàm nhỏ giúp nhận diện object và kiểm tra từng key:

```java
import java.util.LinkedHashMap;
import java.util.Map;

static Map<String, Object> requireObject(Object value, String field) {
    if (!(value instanceof Map<?, ?> raw)) {
        throw new IllegalArgumentException(field + " phải là JSON object");
    }

    Map<String, Object> result = new LinkedHashMap<>();
    for (Map.Entry<?, ?> entry : raw.entrySet()) {
        if (!(entry.getKey() instanceof String key)) {
            throw new IllegalArgumentException(field + " chứa key không phải chuỗi");
        }
        result.put(key, entry.getValue());
    }
    return result;
}
```

Với helper trên, lấy object lồng nhau:

```java
Map<String, Object> retry =
        requireObject(data.get("retryPolicy"), "retryPolicy");

Object attemptsValue = retry.get("maxAttempts");
if (!(attemptsValue instanceof Number number)) {
    throw new IllegalArgumentException("retryPolicy.maxAttempts phải là số");
}
```

`requireObject` sao chép các cặp key/value sang một map mới, kiểm tra kiểu key mà không cần dùng ép kiểu unchecked. Nó **không** kiểm tra toàn bộ các value, nên từng value vẫn cần được kiểm tra ở nơi sử dụng. `LinkedHashMap` ở đây chỉ là lựa chọn triển khai để lưu kết quả; thứ tự trường trong JSON object không phải một hợp đồng nghiệp vụ đáng tin cậy.

Nếu dữ liệu có nhiều cấp, hãy xây dựng đường đi tường minh:

```text
data
  └── retryPolicy             (kiểm tra: Map)
       └── maxAttempts        (kiểm tra: Number → số nguyên dương)
```

Thông báo lỗi nên nói rõ **tên trường và kiểu mong đợi**, chẳng hạn `retryPolicy.maxAttempts phải là số nguyên dương`; không đính kèm nguyên bản `data` hoặc giá trị secret vào exception.

## 5. Collection: array chuỗi, array object và array hỗn hợp

JSON array cho phép chứa các kiểu khác nhau. Tuy nhiên, nếu ứng dụng kỳ vọng danh sách tên vùng hoặc danh sách máy chủ, cần xác thực phần tử nào cũng đúng schema.

### 5.1. Danh sách chuỗi

Ví dụ `regions`:

```json
"regions": ["ap-southeast-1", "eu-west-1"]
```

Hàm đọc một collection chuỗi:

```java
import java.util.ArrayList;
import java.util.List;

static List<String> requireStrings(Object value, String field) {
    if (!(value instanceof List<?> raw)) {
        throw new IllegalArgumentException(field + " phải là JSON array");
    }

    List<String> result = new ArrayList<>();
    for (int index = 0; index < raw.size(); index++) {
        Object element = raw.get(index);
        if (!(element instanceof String item) || item.isBlank()) {
            throw new IllegalArgumentException(
                    field + "[" + index + "] phải là chuỗi không rỗng");
        }
        result.add(item);
    }
    return List.copyOf(result);
}
```

`List<?>` cho phép kiểm tra **cấu trúc collection** mà chưa giả định kiểu phần tử. Vòng lặp kiểm tra từng phần tử trước khi tạo `List<String>`. Hàm này chấp nhận danh sách rỗng; nếu hệ thống yêu cầu ít nhất một vùng, cần có validation riêng bằng `regions.isEmpty()`.

### 5.2. Danh sách các object

Với `targets` chứa hai object:

```java
static List<Map<String, Object>> requireObjects(Object value, String field) {
    if (!(value instanceof List<?> raw)) {
        throw new IllegalArgumentException(field + " phải là JSON array");
    }

    List<Map<String, Object>> result = new ArrayList<>();
    for (int index = 0; index < raw.size(); index++) {
        result.add(requireObject(raw.get(index), field + "[" + index + "]"));
    }
    return List.copyOf(result);
}
```

Sử dụng:

```java
List<Map<String, Object>> targets =
        requireObjects(data.get("targets"), "targets");

for (int index = 0; index < targets.size(); index++) {
    Map<String, Object> target = targets.get(index);
    Object id = target.get("id");
    Object url = target.get("url");
    Object weight = target.get("weight");
    // Kiểm tra id, url là String; weight là số nguyên trong phạm vi cho phép.
}
```

Nếu mảng thực tế là `[{}, "unexpected", {}]`, hàm sẽ từ chối phần tử `targets[1]` thay vì mặc định đó là object và gặp `ClassCastException` ở một đoạn mã khác.

### 5.3. Vì sao không ép thẳng sang `List<Map<String, Object>>`?

Phép ép kiểu sau thường xuất hiện:

```java
@SuppressWarnings("unchecked")
List<Map<String, Object>> targets =
        (List<Map<String, Object>>) data.get("targets");
```

Ở Java, generic bị xóa kiểu tại runtime (*type erasure*). Phép ép chỉ kiểm tra được đối tượng có phải `List` hay không, chứ không xác minh từng phần tử là `Map<String, Object>`. Kết quả có thể tạo cảm giác “đã có kiểu” dù dữ liệu bên trong vẫn sai. Cách phù hợp là duyệt `List<?>`, kiểm tra các phần tử, rồi mới tạo collection có kiểu như ví dụ trên.

### 5.4. Mảng hỗn hợp và giá trị `null`

JSON cho phép:

```json
{
  "mixed": ["a", 12, true, null, { "k": "v" }],
  "nullableTargets": [null, { "id": "primary" }]
}
```

Đây là JSON hợp lệ nhưng không có nghĩa nó hợp lệ theo **schema nghiệp vụ**. Nếu `targets` bắt buộc chứa các object đầy đủ, `null` hoặc chuỗi phải gây lỗi. Nếu dữ liệu thực sự cho phép phần tử null hay nhiều loại khác nhau, cần định nghĩa rõ từng trường hợp (chẳng hạn một kiểu tổng/union hoặc cấu trúc có trường `type` để phân biệt), thay vì bỏ qua các phần tử không nhận diện được.

## 6. Số, boolean, null và các lỗi chuyển đổi hay gặp

### 6.1. Chuyển số nguyên có kiểm tra phạm vi

Dùng `Number.intValue()` một cách trực tiếp có thể làm mất phần thập phân hoặc tràn phạm vi. Ví dụ `3.9` có thể bị cắt thành `3`, còn số rất lớn có thể trở thành một số khác. Đối với trường khai báo **số nguyên**, chuyển qua `BigDecimal` và dùng `intValueExact()` giúp từ chối giá trị không nguyên hoặc nằm ngoài phạm vi `int`:

```java
import java.math.BigDecimal;
import java.util.Map;

static int requireInt(Map<String, Object> object, String field) {
    Object value = object.get(field);
    if (!(value instanceof Number number)) {
        throw new IllegalArgumentException(field + " phải là JSON number");
    }

    try {
        return new BigDecimal(number.toString()).intValueExact();
    } catch (NumberFormatException | ArithmeticException ex) {
        throw new IllegalArgumentException(
                field + " phải là số nguyên trong phạm vi int", ex);
    }
}
```

Đây là phép kiểm tra **giá trị Java đã deserialize**. Nó không bảo đảm giữ nguyên văn biểu diễn số trong JSON nếu bộ giải mã trước đó đã làm tròn hoặc mất chính xác. Với các con số quan trọng về tài chính, hãy chọn kiểu và cơ chế deserialize bảo toàn độ chính xác ngay từ đầu; không sử dụng `double` để biểu diễn tiền.

Sau khi xác nhận là số nguyên, tiếp tục kiểm tra ràng buộc miền:

```java
int maxConnections = requireInt(data, "maxConnections");
if (maxConnections <= 0) {
    throw new IllegalArgumentException("maxConnections phải lớn hơn 0");
}

Map<String, Object> retry =
        requireObject(data.get("retryPolicy"), "retryPolicy");
int maxAttempts = requireInt(retry, "maxAttempts");
if (maxAttempts < 1 || maxAttempts > 10) {
    throw new IllegalArgumentException("retryPolicy.maxAttempts ngoài phạm vi");
}
```

Hàm `requireInt` nhận **tên key ở Map hiện tại** (`maxAttempts`). Khi cần thông báo lỗi có đủ đường dẫn `retryPolicy.maxAttempts`, có thể mở rộng helper để nhận thêm tham số `path` dành riêng cho thông báo; không dùng toàn bộ đường dẫn làm key của Map con.

### 6.2. Boolean không tự chuyển từ chuỗi

```java
Object enabledValue = data.get("enabled");
if (!(enabledValue instanceof Boolean enabled)) {
    throw new IllegalArgumentException("enabled phải là true hoặc false");
}
```

Giá trị JSON `true` có thể trở thành `Boolean.TRUE`, trong khi JSON `"true"` là **String**. Không nên âm thầm gọi `Boolean.parseBoolean(String.valueOf(value))` trong mã đọc secrets bắt buộc, vì mọi chuỗi khác `"true"` có thể bị chuyển thành `false` và che khuất lỗi cấu hình.

### 6.3. Phân biệt không có key, key null và collection rỗng

```java
if (!data.containsKey("description")) {
    // Không có trường description trong object.
} else if (data.get("description") == null) {
    // Trường có mặt và chứa JSON null.
} else if (data.get("description") instanceof String description) {
    // Trường chứa chuỗi; tiếp tục kiểm tra các điều kiện cần thiết.
} else {
    throw new IllegalArgumentException("description phải là chuỗi hoặc null");
}
```

Các trạng thái `không có trường`, `giá trị null`, `chuỗi rỗng` và `danh sách rỗng` có thể mang ý nghĩa nghiệp vụ khác nhau:

| Trạng thái | Ví dụ | Câu hỏi cần quyết định |
|---|---|---|
| Key không tồn tại | `{}` | Có cho phép bỏ qua trường và dùng mặc định không? |
| Key có giá trị null | `{ "description": null }` | Có mang nghĩa “cố ý xóa” hay “chưa cấu hình” không? |
| Chuỗi rỗng | `{ "description": "" }` | Có phải giá trị hợp lệ không? |
| Array rỗng | `{ "regions": [] }` | Có cho phép chạy mà không có vùng nào không? |
| Array chứa null | `{ "regions": [null] }` | Phần tử null có hợp lệ theo schema không? |

Không dùng `String.valueOf(data.get("apiToken"))` làm kiểm tra trường bắt buộc: với `null`, biểu thức trả chuỗi chữ `"null"`, dễ bị hiểu nhầm là một token hợp lệ. `Map.of(...)` của Java cũng không hỗ trợ key/value null, nên khi tự viết dữ liệu kiểm thử có `null`, hãy dùng `HashMap`/`LinkedHashMap` hoặc JSON fixture thích hợp.

## 7. Ví dụ tổng hợp: từ `Map<String, Object>` sang cấu hình Java có kiểu

Ví dụ Java 17+ sau ghép các kỹ thuật trên. Các helper `requireObject`, `requireStrings`, `requireObjects` và `requireInt` đã trình bày ở những mục trước được dùng lại; phần mã dưới đây minh họa cách **tổ chức luồng ánh xạ** và kiểm tra schema nghiệp vụ.

```java
record RetryPolicy(int maxAttempts, int backoffMillis) {}

record Target(String id, String url, int weight) {}

record CheckoutSettings(
        String service,
        boolean enabled,
        int maxConnections,
        double samplingRate,
        String apiToken,
        RetryPolicy retryPolicy,
        List<String> regions,
        List<Target> targets
) {
    @Override
    public String toString() {
        // Không để toString() tự sinh của record làm lộ apiToken trong log.
        return "CheckoutSettings[service=" + service + ", apiToken=<redacted>]";
    }
}

static String requireString(Map<String, Object> data, String key) {
    Object value = data.get(key);
    if (!(value instanceof String text) || text.isBlank()) {
        throw new IllegalArgumentException(key + " phải là chuỗi không rỗng");
    }
    return text;
}

static double requireRate(Map<String, Object> data, String key) {
    Object value = data.get(key);
    if (!(value instanceof Number number)) {
        throw new IllegalArgumentException(key + " phải là number");
    }
    double rate = number.doubleValue();
    if (!Double.isFinite(rate) || rate < 0.0 || rate > 1.0) {
        throw new IllegalArgumentException(key + " phải nằm trong [0, 1]");
    }
    return rate; // double phù hợp tỷ lệ minh họa, không sử dụng cho số tiền.
}

static CheckoutSettings mapCheckout(Map<String, Object> data) {
    String service = requireString(data, "service");
    String token = requireString(data, "apiToken");

    Object flag = data.get("enabled");
    if (!(flag instanceof Boolean enabled)) {
        throw new IllegalArgumentException("enabled phải là boolean");
    }

    int maxConnections = requireInt(data, "maxConnections");
    if (maxConnections <= 0) {
        throw new IllegalArgumentException("maxConnections phải lớn hơn 0");
    }

    Map<String, Object> retry =
            requireObject(data.get("retryPolicy"), "retryPolicy");
    int maxAttempts = requireInt(retry, "maxAttempts");
    int backoffMillis = requireInt(retry, "backoffMillis");
    if (maxAttempts <= 0 || backoffMillis < 0) {
        throw new IllegalArgumentException("retryPolicy có tham số không hợp lệ");
    }

    List<String> regions = requireStrings(data.get("regions"), "regions");
    if (regions.isEmpty()) {
        throw new IllegalArgumentException("regions không được rỗng");
    }

    List<Map<String, Object>> rawTargets =
            requireObjects(data.get("targets"), "targets");
    List<Target> targets = new ArrayList<>();
    for (Map<String, Object> raw : rawTargets) {
        String id = requireString(raw, "id");
        String url = requireString(raw, "url");
        int weight = requireInt(raw, "weight");
        if (weight < 0 || weight > 100) {
            throw new IllegalArgumentException("targets.weight ngoài phạm vi");
        }
        targets.add(new Target(id, url, weight));
    }
    if (targets.isEmpty()) {
        throw new IllegalArgumentException("targets không được rỗng");
    }

    return new CheckoutSettings(
            service,
            enabled,
            maxConnections,
            requireRate(data, "samplingRate"),
            token,
            new RetryPolicy(maxAttempts, backoffMillis),
            regions,
            List.copyOf(targets));
}
```

**Cách gọi từ thành phần tích hợp Vault:**

```java
VaultResponse response = kv.get("checkout/runtime");
if (response == null || response.getData() == null) {
    throw new IllegalStateException("Thiếu cấu hình checkout");
}

CheckoutSettings settings = mapCheckout(response.getRequiredData());
// Chỉ truyền settings đến thành phần thực sự cần; không log record chứa secret.
```

Khi triển khai thực tế, nên đặt các helper và `mapCheckout` trong cùng class/service hoặc utility thích hợp, thêm import Java cần dùng, và kiểm tra các ràng buộc nghiệp vụ khác: URL đúng giao thức, tổng trọng số các target, sự trùng lặp `id`, độ dài token, giới hạn số phần tử. Để tránh lưu cùng một secret ở nhiều nơi, chỉ giữ dữ liệu trong phạm vi cần thiết.

Trong ví dụ, `samplingRate` là tỷ lệ kỹ thuật nên `double` được sử dụng. Nếu trường biểu diễn số tiền, tỷ giá tài chính hoặc dữ liệu cần chính xác đến từng chữ số, cần chọn `BigDecimal` cùng quy tắc JSON mapping phù hợp từ đầu.

## 8. Khi nào ánh xạ thẳng vào DTO?

Với schema ổn định, bạn có thể để Spring Vault chuyển dữ liệu sang Java type ngay khi đọc, bằng overload `VaultKeyValueOperations.get(path, Class<T>)`:

```java
import org.springframework.vault.support.VaultResponseSupport;

VaultResponseSupport<CheckoutDto> response =
        kv.get("checkout/runtime", CheckoutDto.class);

if (response == null || response.getData() == null) {
    throw new IllegalStateException("Thiếu cấu hình checkout");
}

CheckoutDto dto = response.getRequiredData();
// Vẫn cần kiểm tra dto và các đối tượng/list lồng nhau.
```

Trong đoạn trên, `CheckoutDto` là kiểu dữ liệu do ứng dụng **tự định nghĩa** với các property tương ứng, chẳng hạn `RetryPolicyDto retryPolicy`, `List<String> regions` và `List<TargetDto> targets`. Các class DTO, constructor, accessor và quy tắc chuyển đổi phải tương thích với cơ chế ánh xạ được cấu hình cho phiên bản Spring Vault/Java đang dùng.

| Phương án | Khi phù hợp | Giới hạn cần nhớ |
|---|---|---|
| `VaultResponse` + duyệt `Map` | Keys động, adapter tổng quát, phải kiểm tra schema tùy tình huống | Cần kiểm tra từng value và generic collection bằng runtime validation |
| `VaultResponseSupport<CheckoutDto>` | Schema ổn định và có DTO rõ ràng | Mapping thành công chưa chứng minh các ràng buộc nghiệp vụ đã hợp lệ |
| DTO lồng nhau và `List<TargetDto>` | Cấu trúc JSON nhiều cấp nhưng nhất quán | Phải xử lý trường thiếu, null, kiểu sai và tương thích bộ chuyển đổi |
| `VaultVersionedKeyValueOperations` | Cần đọc/ghi phiên bản cụ thể trong KV v2 | Metadata phiên bản là phần riêng, không nhét vào DTO nghiệp vụ tùy tiện |

Chú ý rằng `List<TargetDto>` bên trong một DTO có thể được mô tả nhờ kiểu của **property**; điều này khác với việc cố ép một `Object` chưa kiểm tra thành `List<Map<String, Object>>`. Khi dữ liệu JSON thay đổi schema, nên quản lý phiên bản cấu hình và xử lý tương thích một cách có chủ đích.

## 9. Xử lý lỗi và kiểm thử ánh xạ

Lỗi ánh xạ không phải lúc nào cũng là lỗi Vault. Cần tách ba lớp vấn đề:

1. **Lỗi truy cập:** workload xác thực thất bại, policy từ chối, network/TLS không hoạt động, endpoint trả lỗi; xử lý theo trạng thái truy cập hoặc exception thích hợp của Spring Vault.
2. **Không có dữ liệu:** `get(...)` trả `null`, hoặc `response.getData()` không có giá trị; báo rõ thiếu secret bắt buộc.
3. **Dữ liệu sai schema:** JSON hợp lệ nhưng loại giá trị, cấu trúc lồng nhau hoặc ràng buộc nghiệp vụ sai; báo tên trường và lý do, không xuất giá trị bí mật.

Không được coi HTTP 403 là `Map` rỗng, tự thay bằng token mặc định hoặc bỏ qua lỗi deserialize để ứng dụng tiếp tục hoạt động với cấu hình không an toàn.

Một bảng kiểm thử có thể dùng cho hàm `mapCheckout(...)` mà không cần gọi Vault thật:

| Biến thể input | Kết quả mong đợi |
|---|---|
| Mọi trường đúng kiểu, `regions` và `targets` hợp lệ | Trả về `CheckoutSettings` với các giá trị chính xác |
| `retryPolicy` đổi thành chuỗi `"3"` | Từ chối: `retryPolicy` phải là object |
| `retryPolicy.maxAttempts` bằng `3.8` | Từ chối vì không phải số nguyên |
| `maxConnections` vượt giới hạn `int` | Từ chối, không âm thầm tràn số |
| `regions` có phần tử `17` hoặc `null` | Từ chối tại đúng chỉ số mảng |
| `targets` chứa chuỗi thay cho object | Từ chối tại đúng chỉ số phần tử |
| `apiToken` bị thiếu hoặc null | Từ chối mà không in toàn bộ Map |
| `enabled` bằng chuỗi `"false"` | Từ chối: không phải Boolean |
| `regions` là `[]` | Từ chối theo ràng buộc nghiệp vụ ví dụ |
| `description` bị thiếu hoặc null | Tùy hợp đồng dữ liệu: có thể chấp nhận vì trường tùy chọn |

Tách riêng hàm ánh xạ thuần Java khỏi hàm gọi Vault giúp kiểm thử dữ liệu lồng nhau mà không cần thông tin đăng nhập hoặc Vault server cho mọi ca. Với kiểm thử tích hợp, có thể chạy Vault trong môi trường cô lập để xác minh mount KV v2, policy và đường dẫn thật; dùng secrets giả, không hardcode credentials dùng trong sản xuất.

### Nguyên tắc an toàn khi quan sát lỗi

- **Không** log `Map`, DTO, `VaultResponse` hay `List` nếu có khả năng chứa token, password hoặc private key. `record.toString()` cũng có thể in toàn bộ các trường nếu không được xử lý.
- Thông báo lỗi validator chỉ cần nêu tên path trong schema, kiểu mong đợi và điều kiện bị vi phạm. Hạn chế ghi tên mount/path nhạy cảm ra log công khai.
- Nếu dữ liệu được xoay vòng, cache/DTO cũ trong JVM có thể vẫn chứa giá trị trước đó; việc đọc đúng kiểu JSON không tự động quản lý rotation hay lease.
- Nếu một endpoint cung cấp credentials động, thông tin token/lease thuộc vòng đời xác thực và secrets; không tự đưa `lease_id` vào object nghiệp vụ hoặc nhầm nó với phần tử của `data`.

## 10. Thực hành tự kiểm tra

### Bài tập 1 — Map hai cấp

Đọc JSON sau thành `Map<String, Object>` rồi viết hàm lấy `connection.pool.maxSize` dưới dạng số nguyên dương, đồng thời báo lỗi khi `pool` bị đổi thành array:

```json
{
  "connection": {
    "pool": {
      "minSize": 2,
      "maxSize": 12
    }
  }
}
```

**Gợi ý:** Dùng `requireObject` lần lượt cho `connection` và `pool`, sau đó `requireInt` cho `maxSize`. Mỗi bước kiểm tra đúng một cấu trúc.

### Bài tập 2 — Collection lồng nhau

Cho object:

```json
{
  "servers": [
    { "host": "a.internal", "ports": [8080, 8443] },
    { "host": "b.internal", "ports": [8081] }
  ]
}
```

Viết hàm tạo `List<Server>` với `Server(String host, List<Integer> ports)`. Phải kiểm tra từng `ports[i]` là số nguyên từ 1 đến 65535, và danh sách `servers` không rỗng. Thử dữ liệu `"ports": [8080, "8443"]` để kiểm tra lỗi kiểu.

### Bài tập 3 — Nhận diện lớp `data` trong KV v2

Một lập trình viên dùng `vaultOperations.read("secret/data/checkout/runtime")`, sau đó đọc `response.getData().get("retryPolicy")` và nhận `null`. Hãy giải thích vì sao. Nêu hai cách giải quyết, và cho biết cách nào giúp tránh viết logic bóc lớp `data` của KV v2 bằng tay.

**Đáp án định hướng:** Khi gọi endpoint KV v2 trực tiếp, `response.getData()` chứa `data` và `metadata` của engine. `retryPolicy` nằm trong `response.getData().get("data")` và cần kiểm tra kiểu trước khi đọc tiếp. Cách thứ hai là dùng `vaultOperations.opsForKeyValue("secret", KV_2).get("checkout/runtime")` để lấy trực tiếp phần dữ liệu nghiệp vụ.

## 11. Tổng kết

- JSON object thường tương ứng `Map`, JSON array thường tương ứng `List`, nhưng mỗi value vẫn cần được xác minh trước khi sử dụng.
- Kiểm tra nested object bằng `instanceof Map<?, ?>`; kiểm tra collection bằng `List<?>` và duyệt từng phần tử, thay vì dựa vào ép kiểu generic unchecked.
- Số JSON không mang sẵn kiểu `Integer` hoặc `Double` cố định; phải kiểm tra tính nguyên, phạm vi và độ chính xác theo nghiệp vụ.
- `null`, thiếu key, chuỗi rỗng và array rỗng có ý nghĩa khác nhau; cần một schema rõ ràng cho từng trường.
- KV v2 có lớp `data` do engine tạo ra khi gọi endpoint trực tiếp. `VaultKeyValueOperations` giúp đọc theo đường dẫn logic và giảm sai sót bóc lớp phản hồi.
- Chuyển sang DTO có kiểu giúp code ứng dụng rõ hơn, nhưng không thay thế validation, xử lý quyền truy cập, bảo vệ secrets và quản lý vòng đời token/lease.

## Tài liệu tham khảo

- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): thao tác KV v1, KV v2 và API dữ liệu có phiên bản.
- [Spring Vault — `VaultKeyValueOperations` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultKeyValueOperations.html): đọc dữ liệu KV dạng `VaultResponse` hoặc ánh xạ có kiểu.
- [Spring Vault — `VaultResponseSupport<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponseSupport.html): lớp phản hồi và phần dữ liệu có kiểu.
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): cấu trúc `data` và `metadata` của KV v2.
