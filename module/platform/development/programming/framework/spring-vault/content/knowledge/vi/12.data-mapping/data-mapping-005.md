# Kiểu dữ liệu chung và generic khi đọc phản hồi

## Mục tiêu bài học

Trong **Spring Vault**, cùng một API đọc dữ liệu từ HashiCorp Vault có thể được sử dụng để lấy cấu hình kết nối, token của dịch vụ, danh sách máy chủ hoặc các thông tin nghiệp vụ khác. Spring Vault cung cấp các kiểu phản hồi tổng quát (*generic*) như `VaultResponseSupport<T>` và các phương thức nhận `Class<T>` để ánh xạ dữ liệu JSON vào kiểu Java được chỉ định.

Tuy nhiên, Java generic có giới hạn quan trọng: **thông tin tham số kiểu có thể bị xóa ở runtime (*type erasure*)**. Việc khai báo `List<Route>` trong mã nguồn không tự bảo đảm dữ liệu đến từ Vault thực sự là danh sách `Route`. Vì vậy, người viết ứng dụng cần hiểu mối liên hệ giữa phản hồi Vault, kiểu generic và cơ chế chuyển đổi JSON.

Bài thuộc chương **Ánh xạ dữ liệu** của module **SPRING_VAULT**. Sau khi học, bạn có thể:

1. Phân biệt `VaultResponse`, `VaultResponseSupport<T>`, `T` và `Class<T>` khi gọi API Spring Vault.
2. Viết hàm đọc KV generic có kiểm tra phản hồi, và biết giới hạn bảo đảm của kiểu trả về.
3. Hiểu vì sao `Class<List<MyDto>>` không tạo được trực tiếp và tránh ép kiểu generic thiếu an toàn.
4. Ánh xạ collection, nested object và `Map<String, List<T>>` bằng DTO có thuộc tính generic hoặc công cụ Jackson thích hợp.
5. Kiểm tra dữ liệu thiếu, kiểu JSON không phù hợp, số ngoài phạm vi và danh sách sai phần tử.
6. Thiết kế ranh giới tích hợp và kiểm thử mà không để lộ secrets vào log hoặc thông báo lỗi.

> **Phạm vi:** Các ví dụ giả định ứng dụng Java đã có `VaultOperations`/`VaultTemplate` được cấu hình để kết nối Vault và xác thực theo workload phù hợp với policy. Nội dung tập trung vào kiểu dữ liệu và generic khi đọc phản hồi. Xác thực, vòng đời token/lease, Transit encryption, PKI, xử lý lỗi, quan sát và kiểm thử tích hợp vẫn là các chủ đề liên quan trong hệ sinh thái Spring Vault, nhưng không được giải quyết chỉ bằng cách đổi kiểu generic.

## 1. Từ JSON của Vault đến kiểu dữ liệu Java

Giả sử ứng dụng cần đọc secret tại path logic `services/reporting` trong KV v2 mount `secret`. Dữ liệu nghiệp vụ có cấu trúc:

```json
{
  "username": "reporting-user",
  "password": "<gia-tri-bi-mat>",
  "port": 5432,
  "enabled": true,
  "allowedRegions": ["ap-southeast-1", "eu-west-1"],
  "limits": {
    "dailyQueries": 1500,
    "maxConcurrent": 20
  }
}
```

Nếu đọc theo kiểu chưa định hình schema, các giá trị này thường xuất hiện dưới `Map<String, Object>`:

```text
Vault KV v2 (JSON)
        │
        ▼
VaultResponse
        │ getData()
        ▼
Map<String, Object>
  ├── username       → String
  ├── password       → String
  ├── port           → Number
  ├── enabled        → Boolean
  ├── allowedRegions → List<?> 
  └── limits         → Map<?, ?>
```

Ở kiểu `Map<String, Object>`, Java chỉ biết giá trị có kiểu biên dịch là `Object`. Chương trình cần kiểm tra từng value trước khi dùng. Một DTO có kiểu giúp phần còn lại của ứng dụng làm việc với các trường rõ ràng hơn:

```text
Vault KV v2 (JSON)
        │
        ▼
VaultResponseSupport<ReportingSecret>
        │ getData()
        ▼
ReportingSecret
  ├── username: String
  ├── password: String
  ├── port: Integer
  ├── enabled: Boolean
  ├── allowedRegions: List<String>
  └── limits: QueryLimits
```

**Điểm cốt lõi:** generic tăng độ rõ ràng của *hợp đồng kiểu trong Java*. Nó không chứng minh dữ liệu JSON đầy đủ, không thay thế validation và cũng không tự quản lý quyền, token hay lease của Vault.

### 1.1. Những dạng JSON thường thấy

| JSON | Kiểu Java chưa định kiểu thường gặp | Kiểu DTO có thể chọn |
|---|---|---|
| `"reporting-user"` | `String` | `String` |
| `5432` | `Number`, thường là `Integer`/`Long` tùy converter | `Integer` hoặc kiểu số phù hợp |
| `true` | `Boolean` | `Boolean` |
| `["a", "b"]` | `List<?>` | `List<String>` |
| `{"dailyQueries":1500}` | `Map<?, ?>` | `QueryLimits` hoặc `Map<String, Integer>` |
| `[{"id":"a"},{"id":"b"}]` | `List<?>` gồm các `Map` | `List<Route>` |
| `null` | `null` | Kiểu tham chiếu nullable hoặc cấu trúc xử lý thiếu dữ liệu |

Không dựa vào việc dữ liệu là `Integer` chỉ vì JSON có giá trị `5432`; cấu hình converter có thể tạo kiểu số khác. Với những số cần độ chính xác cao, phải xác định cơ chế deserialize phù hợp từ đầu.

## 2. `VaultResponse` và `VaultResponseSupport<T>`

Spring Vault có các kiểu phản hồi trong package `org.springframework.vault.support`:

```java
// Mô tả quan hệ kiểu, không phải mã cần khai báo lại trong ứng dụng.
class VaultResponseSupport<T> {
    T getData(); // Minh họa kiểu trả về.
}

class VaultResponse
        extends VaultResponseSupport<Map<String, Object>> {
}
```

`VaultResponseSupport<T>` là lớp phản hồi có phần dữ liệu mang kiểu `T`. `VaultResponse` là trường hợp chuyên biệt với `T = Map<String, Object>`.

| Biểu thức Java | Kiểu tại thời điểm biên dịch | Ý nghĩa |
|---|---|---|
| `VaultResponse response` | `VaultResponse` | Phản hồi có dữ liệu dạng Map |
| `response.getData()` | `Map<String, Object>` | Phần dữ liệu nghiệp vụ chưa map thành DTO |
| `VaultResponseSupport<ReportingSecret> typed` | `VaultResponseSupport<ReportingSecret>` | Phản hồi có dữ liệu kiểu `ReportingSecret` |
| `typed.getData()` | `ReportingSecret` | Đối tượng DTO do converter tạo ra |
| `VaultResponseSupport<List<Route>>` | Thể hiện một kiểu generic hợp lệ trong Java | Chưa đủ để kết luận API đọc KV hiện tại nhận được thông tin kiểu `List<Route>` |

`VaultResponseSupport<T>` còn cung cấp các thông tin bao ngoài phản hồi theo endpoint, chẳng hạn request ID và thông tin lease. Dữ liệu bên trong `T` chỉ nên biểu diễn những thuộc tính nghiệp vụ cần dùng. Đừng đưa `lease_id` hoặc trường xác thực vào DTO bí mật chỉ vì chúng có thể xuất hiện trong phản hồi thô.

### 2.1. Trường hợp không có dữ liệu

Với API KV, khi secret không tồn tại, lời gọi đọc có thể trả về `null`. Ngoài ra, một phản hồi tồn tại nhưng `getData()` vẫn có thể là `null`. Cả hai cần được xử lý:

```java
VaultResponseSupport<ReportingSecret> response =
        kv.get("services/reporting", ReportingSecret.class);

if (response == null || response.getData() == null) {
    throw new IllegalStateException("Thiếu reporting secret bắt buộc");
}

ReportingSecret secret = response.getRequiredData();
```

`getRequiredData()` yêu cầu phần `data` của **một phản hồi đã tồn tại** không được `null`; nó không bảo vệ lời gọi trên biến `response == null`. Bất kể đọc kiểu `Map` hay DTO, các giá trị bên trong vẫn phải được xác thực theo hợp đồng nghiệp vụ.

## 3. `Class<T>` dùng để ánh xạ DTO qua API KV

Với dữ liệu KV ổn định, Spring Vault hỗ trợ đọc có kiểu qua `VaultKeyValueOperations.get(String path, Class<T> responseType)`. Ở mức sử dụng:

```java
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

VaultKeyValueOperations kv = vaultOperations.opsForKeyValue(
        "secret", KeyValueBackend.KV_2);

VaultResponseSupport<ReportingSecret> response =
        kv.get("services/reporting", ReportingSecret.class);
```

`vaultOperations` là biến kiểu `VaultOperations` đã được tiêm vào thành phần ứng dụng. `ReportingSecret.class` là một **`Class<ReportingSecret>`**: một đối tượng mô tả kiểu Java cụ thể tại runtime, để bộ chuyển đổi biết cần tạo DTO nào.

DTO JavaBean minh họa:

```java
import java.util.List;

public class ReportingSecret {

    private String username;
    private String password;
    private Integer port;
    private Boolean enabled;
    private List<String> allowedRegions;
    private QueryLimits limits;

    public ReportingSecret() {
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public Integer getPort() {
        return port;
    }

    public void setPort(Integer port) {
        this.port = port;
    }

    public Boolean getEnabled() {
        return enabled;
    }

    public void setEnabled(Boolean enabled) {
        this.enabled = enabled;
    }

    public List<String> getAllowedRegions() {
        return allowedRegions;
    }

    public void setAllowedRegions(List<String> allowedRegions) {
        this.allowedRegions = allowedRegions;
    }

    public QueryLimits getLimits() {
        return limits;
    }

    public void setLimits(QueryLimits limits) {
        this.limits = limits;
    }

    public static class QueryLimits {

        private Integer dailyQueries;
        private Integer maxConcurrent;

        public QueryLimits() {
        }

        public Integer getDailyQueries() {
            return dailyQueries;
        }

        public void setDailyQueries(Integer dailyQueries) {
            this.dailyQueries = dailyQueries;
        }

        public Integer getMaxConcurrent() {
            return maxConcurrent;
        }

        public void setMaxConcurrent(Integer maxConcurrent) {
            this.maxConcurrent = maxConcurrent;
        }
    }
}
```

Đây là DTO có **kiểu gốc cụ thể** `ReportingSecret.class`, nhưng bên trong vẫn có `List<String>` và object lồng nhau. Khi bộ chuyển đổi JSON nhận diện property generic, nó có thể sử dụng thông tin kiểu khai báo trên các trường của DTO để ánh xạ phần tử. Khả năng cụ thể phụ thuộc client/converter và phiên bản thư viện, nên cần kiểm thử tích hợp.

**Không tự động log DTO:** JavaBean trên không tự sinh `toString()` in secret. Nếu dự án dùng Lombok hoặc record để tự sinh `toString()`, phải ngăn các trường như `password` xuất hiện trong log.

## 4. Viết hàm đọc KV generic dùng lại được

Một adapter có thể dùng chung thao tác đọc với nhiều DTO:

```java
import java.util.Objects;

import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponseSupport;

public final class TypedKvReader {

    private final VaultKeyValueOperations kv;

    public TypedKvReader(VaultOperations operations) {
        this.kv = operations.opsForKeyValue(
                "secret", KeyValueBackend.KV_2);
    }

    public <T> T readRequired(String path, Class<T> type) {
        Objects.requireNonNull(path, "path");
        Objects.requireNonNull(type, "type");

        VaultResponseSupport<T> response = kv.get(path, type);

        if (response == null || response.getData() == null) {
            // Không đưa dữ liệu secret vào thông báo lỗi.
            throw new IllegalStateException(
                    "Không tìm thấy secret hoặc payload bắt buộc");
        }

        return response.getRequiredData();
    }
}
```

Cách gọi:

```java
TypedKvReader reader = new TypedKvReader(vaultOperations);

ReportingSecret reporting =
        reader.readRequired("services/reporting", ReportingSecret.class);

DatabaseSecret database =
        reader.readRequired("services/database", DatabaseSecret.class);
```

`DatabaseSecret` là DTO khác do ứng dụng định nghĩa, dùng để minh họa việc tái sử dụng hàm. `ReportingSecret` và `DatabaseSecret` không cần chung một lớp cha chỉ để đọc từ Vault; tham số generic `T` cho phép phương thức nhận `Class<T>` tương ứng.

Phân tích chữ ký:

```java
public <T> T readRequired(String path, Class<T> type)
```

- `<T>` đứng trước kiểu trả về khai báo một **tham số kiểu cấp phương thức**.
- `Class<T> type` truyền thông tin kiểu vào runtime (ví dụ `ReportingSecret.class`).
- `T` ở vị trí kiểu trả về giúp compiler biết kết quả là kiểu DTO đó.
- `VaultResponseSupport<T>` giữ tương quan kiểu giữa `Class<T>` và `getData()`.
- Giá trị trả về **chưa được validation**; bộ chuyển đổi có thể tạo DTO với trường null, số ngoài giới hạn hoặc cấu trúc không hợp lệ về nghiệp vụ.

Nếu viết:

```java
Object value = reader.readRequired(
        "services/reporting", ReportingSecret.class);
```

mã vẫn chạy nhưng phía gọi đã làm mất ưu điểm của kiểu `ReportingSecret`. Ngược lại, không thể tùy tiện gán kết quả trả về của `Class<ReportingSecret>` sang `DatabaseSecret` mà không vấp lỗi kiểu biên dịch.

### 4.1. Generic utility có validation theo từng DTO

Để không cho dữ liệu chưa hợp lệ thoát khỏi adapter, có thể bổ sung validator:

```java
import java.util.Objects;
import java.util.function.Consumer;

public <T> T readChecked(
        String path,
        Class<T> type,
        Consumer<? super T> validator) {

    Objects.requireNonNull(validator, "validator");
    T value = readRequired(path, type);
    validator.accept(value);
    return value;
}
```

Đặt phương thức này **trong cùng class `TypedKvReader`**, nơi đã có `readRequired`. Ví dụ:

```java
ReportingSecret reporting = reader.readChecked(
        "services/reporting",
        ReportingSecret.class,
        secret -> {
            if (secret.getUsername() == null
                    || secret.getUsername().isBlank()) {
                throw new IllegalArgumentException(
                        "username bắt buộc");
            }
            if (secret.getPassword() == null
                    || secret.getPassword().isBlank()) {
                throw new IllegalArgumentException(
                        "password bắt buộc");
            }
        });
```

Validator ở ví dụ trên kiểm tra hai trường thiết yếu để minh họa API. Ứng dụng thực tế còn cần kiểm tra port trong `1..65535`, vùng hợp lệ, giới hạn truy vấn và các ràng buộc khác. Generic helper nên **dùng lại cơ chế đọc**, còn mỗi schema cần một validator cụ thể.

### 4.2. Nên trả cả `VaultResponseSupport<T>` hay chỉ `T`?

| Kiểu trả về của adapter | Khi phù hợp | Lưu ý |
|---|---|---|
| `T` | Tầng nghiệp vụ chỉ cần dữ liệu đã đọc và kiểm tra | Che chi tiết phản hồi Vault khỏi service |
| `VaultResponseSupport<T>` | Adapter còn cần quan sát request ID, lease hoặc metadata phản hồi | Tầng gọi phải hiểu semantics của phản hồi |
| Một kiểu ứng dụng như `SecretReadResult<T>` | Cần trả thêm metadata **đã chọn lọc** theo hợp đồng nội bộ | Không đưa token/auth payload hoặc dữ liệu nhạy cảm tùy tiện |
| `Optional<T>` | Sự vắng mặt của secret là một khả năng hợp lệ được định nghĩa rõ | Không chuyển lỗi 403/mạng/deserialize thành `Optional.empty()` |

Việc dùng `T` ở public API giúp phần nghiệp vụ không phụ thuộc `VaultResponseSupport`. Với dynamic secrets có lease, adapter hoặc thành phần quản lý lifecycle cần phối hợp đúng cơ chế của Spring Vault; không tự giả định mọi KV secret đều có lease có thể gia hạn.

## 5. Giới hạn quan trọng của Java generic: type erasure

Trong Java, sau biên dịch, phần lớn thông tin tham số kiểu của **đối tượng generic tại runtime** bị xóa. Ví dụ, cả hai biến dưới đây thường có cùng kiểu raw `java.util.List` ở runtime:

```java
List<String> regions = List.of("ap-southeast-1");
List<Integer> ports = List.of(8080);

System.out.println(regions.getClass() == ports.getClass()); // true
```

Vì vậy, Java không có cú pháp class literal như sau:

```java
// KHÔNG HỢP LỆ: Java không hỗ trợ class literal có tham số kiểu.
// Class<List<Route>> routeListType = List<Route>.class;
```

`List.class` là class literal cho kiểu raw `List`; nó không lưu đầy đủ `Route`:

```java
Class<List> rawListType = List.class;
```

Điều này quan trọng khi API nhận **`Class<T>`**, chẳng hạn `kv.get(path, Class<T>)`. Nếu schema đích là `List<Route>` hoặc `Map<String, List<Route>>`, không thể chỉ đưa `List.class` hoặc `Map.class` và kỳ vọng dữ liệu tự trở thành collection có kiểu phần tử `Route`.

### 5.1. Phép ép kiểu thiếu an toàn

Ví dụ một secret chứa `routes` là array JSON:

```json
{
  "routes": [
    {"id": "primary", "weight": 80},
    {"id": "secondary", "weight": 20}
  ]
}
```

Cách sau có thể biên dịch với warning nhưng không kiểm tra từng phần tử:

```java
@SuppressWarnings("unchecked")
List<Map<String, Object>> routes =
        (List<Map<String, Object>>) data.get("routes");
```

`@SuppressWarnings("unchecked")` chỉ ẩn cảnh báo của compiler; nó không tạo kiểm tra runtime cho kiểu `Map<String, Object>` của từng phần tử. Nếu array chứa chuỗi, Boolean hoặc null, lỗi có thể xuất hiện muộn khi ứng dụng lấy field.

Cách xác minh tối thiểu:

```java
Object routesValue = data.get("routes");

if (!(routesValue instanceof List<?> routes)) {
    throw new IllegalArgumentException(
            "routes phải là JSON array");
}

for (int i = 0; i < routes.size(); i++) {
    Object route = routes.get(i);
    if (!(route instanceof Map<?, ?> routeObject)) {
        throw new IllegalArgumentException(
                "routes[" + i + "] phải là JSON object");
    }
    Object id = routeObject.get("id");
    if (!(id instanceof String routeId) || routeId.isBlank()) {
        throw new IllegalArgumentException(
                "routes[" + i + "].id phải là chuỗi không rỗng");
    }
}
```

Kiểm tra kiểu **từng cấp** bằng `List<?>` và `Map<?, ?>` là hợp lý ở ranh giới dữ liệu động. Không dùng `instanceof List<Route>`: Java không cho phép kiểm tra kiểu generic tham số hóa như vậy do type erasure.

## 6. Collection generic bên trong DTO có kiểu cụ thể

Giải pháp thường đơn giản nhất là đặt collection bên trong một DTO có class cụ thể. Thay vì cố đọc toàn bộ `List<Route>` như kiểu dữ liệu gốc của phản hồi, hãy mô tả secret là object với field `routes`:

```java
import java.util.List;
import java.util.Map;

public class RoutingSecret {

    private List<Route> routes;
    private Map<String, Integer> quotas;

    public RoutingSecret() {
    }

    public List<Route> getRoutes() {
        return routes;
    }

    public void setRoutes(List<Route> routes) {
        this.routes = routes;
    }

    public Map<String, Integer> getQuotas() {
        return quotas;
    }

    public void setQuotas(Map<String, Integer> quotas) {
        this.quotas = quotas;
    }

    public static class Route {

        private String id;
        private Integer weight;

        public Route() {
        }

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public Integer getWeight() {
            return weight;
        }

        public void setWeight(Integer weight) {
            this.weight = weight;
        }
    }
}
```

JSON tương ứng:

```json
{
  "routes": [
    {"id": "primary", "weight": 80},
    {"id": "secondary", "weight": 20}
  ],
  "quotas": {
    "checkout": 100,
    "reporting": 25
  }
}
```

Đọc thông qua kiểu gốc:

```java
RoutingSecret routing =
        reader.readRequired("services/routing", RoutingSecret.class);

List<RoutingSecret.Route> routes = routing.getRoutes();
Map<String, Integer> quotas = routing.getQuotas();
```

Bởi `RoutingSecret.class` là kiểu cụ thể, bộ chuyển đổi có thể nhìn thấy khai báo `List<Route>` và `Map<String, Integer>` trong **metadata của các property** để ánh xạ từng phần tử. Dữ liệu vẫn cần validation:

```java
if (routes == null || routes.isEmpty()) {
    throw new IllegalStateException("routes không được rỗng");
}

int totalWeight = 0;
for (int i = 0; i < routes.size(); i++) {
    RoutingSecret.Route route = routes.get(i);
    if (route == null
            || route.getId() == null
            || route.getId().isBlank()
            || route.getWeight() == null
            || route.getWeight() < 0
            || route.getWeight() > 100) {
        throw new IllegalStateException(
                "routes[" + i + "] không hợp lệ");
    }
    totalWeight += route.getWeight();
}

if (totalWeight != 100) {
    throw new IllegalStateException(
            "Tổng trọng số routes phải bằng 100");
}
```

Với `quotas`, hãy kiểm tra `null`, từng giá trị nằm trong khoảng hợp lệ và giới hạn kích thước map. **Đọc vào một property generic không có nghĩa tất cả ràng buộc nghiệp vụ được xác thực.**

### 6.1. Vì sao `Map<String, Integer>` vẫn cần thận trọng?

Một DTO có field `Map<String, Integer>` mang hợp đồng mạnh hơn `Map<String, Object>`. Tuy vậy:

- JSON number có thể không phù hợp `Integer` (số thập phân, số rất lớn hoặc biểu diễn chuỗi).
- Converter có thể cho phép một số phép ép kiểu, chẳng hạn chuỗi `"100"` thành số, nếu cấu hình cho phép.
- Một key quan trọng có thể không có trong map.
- Map có thể trống hoặc chứa giá trị `null`.

Ứng dụng nên thiết kế rõ **coercion policy**: chấp nhận dữ liệu có thể chuyển kiểu hay yêu cầu JSON phải có kiểu đúng ngay từ đầu.

## 7. Khi cần generic lồng nhau ngoài DTO: `TypeReference` và `JavaType`

Có trường hợp adapter nhận `Map<String, Object>` rồi muốn chuyển **một field** thành `List<Route>` hoặc `Map<String, List<Route>>`. Với bộ chuyển đổi Jackson 2.x, `TypeReference<T>` hoặc `JavaType` có thể cung cấp mô tả kiểu generic đầy đủ cho thao tác chuyển đổi cục bộ.

> **Giới hạn API:** `VaultKeyValueOperations.get(path, Class<T>)` nhận `Class<T>`. Không thể tự thay tham số này bằng `TypeReference<T>` hoặc `ParameterizedTypeReference<T>` nếu overload như vậy không được API cung cấp. `TypeReference` trong ví dụ sau dành cho **ObjectMapper** sau khi đã đọc dữ liệu; đó không phải chữ ký phương thức đọc KV của Spring Vault.

### 7.1. Chuyển một array JSON thành `List<Route>`

Giả sử adapter đã nhận đúng phần dữ liệu nghiệp vụ:

```java
import java.util.Map;
import org.springframework.vault.support.VaultResponse;

VaultResponse response = kv.get("services/routing");
if (response == null || response.getData() == null) {
    throw new IllegalStateException("Thiếu routing secret");
}

Map<String, Object> data = response.getRequiredData();
Object routesValue = data.get("routes");
```

Chuyển đổi cục bộ bằng Jackson 2.x:

```java
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;

if (!(routesValue instanceof List<?>)) {
    throw new IllegalArgumentException("routes phải là array");
}

ObjectMapper mapper = new ObjectMapper();

List<RoutingSecret.Route> routes;
try {
    routes = mapper.convertValue(
            routesValue,
            new TypeReference<List<RoutingSecret.Route>>() {});
} catch (IllegalArgumentException conversionError) {
    // Không đưa payload thô hoặc nội dung exception chứa giá trị bí mật vào log.
    throw new IllegalStateException(
            "routes không phù hợp với schema Route");
}
```

`new TypeReference<List<RoutingSecret.Route>>() {}` tạo một đối tượng lớp con ẩn danh; Jackson đọc generic type mà lớp con khai báo để biết kiểu phần tử. Không viết `new TypeReference<List<T>>() {}` trong một phương thức generic rồi giả định nó biết `T` là class nào tại runtime: tham số kiểu của phương thức vẫn bị type erasure. Trong trường hợp như vậy, phải truyền thêm kiểu cụ thể hoặc tạo `JavaType` từ thông tin runtime.

Một lựa chọn tương đương bằng `JavaType`:

```java
import com.fasterxml.jackson.databind.JavaType;

JavaType routeListType = mapper.getTypeFactory()
        .constructCollectionType(
                List.class, RoutingSecret.Route.class);

List<RoutingSecret.Route> routesWithJavaType =
        mapper.convertValue(routesValue, routeListType);
```

`JavaType` hữu ích khi kiểu phần tử được chọn động lúc chạy (ví dụ tham số `Class<E> elementType`), vì có thể dựng mô tả collection từ `Class` thực tế.

**Quan trọng:** ví dụ tự tạo `new ObjectMapper()` để minh họa một phép convert thuần Java. Đối với dự án thật, nên sử dụng mapper được cấu hình rõ theo schema, naming strategy và các module cần thiết. Đừng mặc định một `ObjectMapper` có sẵn trong ứng dụng giống với mapper mà Spring Vault dùng khi giải mã HTTP. Các cách chuyển đổi có thể chấp nhận coercion hoặc bỏ qua field tùy cấu hình; hãy kiểm thử.

### 7.2. Generic nhiều cấp: `Map<String, List<Route>>`

Giả sử secret lưu bảng routes theo nhóm:

```json
{
  "routesByRegion": {
    "ap-southeast-1": [
      {"id": "primary", "weight": 100}
    ],
    "eu-west-1": [
      {"id": "secondary", "weight": 100}
    ]
  }
}
```

Sau khi đọc `Map<String, Object> data` chứa trường `routesByRegion`:

```java
Object rawRegions = data.get("routesByRegion");

if (!(rawRegions instanceof Map<?, ?>)) {
    throw new IllegalArgumentException(
            "routesByRegion phải là object");
}

Map<String, List<RoutingSecret.Route>> routesByRegion =
        mapper.convertValue(
                rawRegions,
                new TypeReference<
                        Map<String, List<RoutingSecret.Route>>>() {});
```

`TypeReference` giữ được cấu trúc kiểu ở **nhiều cấp**. Sau bước chuyển đổi, vẫn cần kiểm tra tên region, collection rỗng, từng route và tổng trọng số. Ví dụ trên cần nằm trong adapter có xử lý lỗi chuyển đổi cẩn thận; không chuyển thông báo lỗi chứa payload hoặc giá trị bí mật ra giao diện công khai.

### 7.3. Khi nào không cần `TypeReference`?

Nếu bạn chỉ cần `List<Route>` làm field của `RoutingSecret`, DTO ở mục 6 thường là cách đơn giản nhất. TypeReference hữu ích khi:

- Adapter nhận dữ liệu động từ một endpoint cần kiểm tra hoặc chuyển từng phần.
- Cần chuyển một trường có generic nhiều cấp, không muốn định nghĩa thêm wrapper DTO.
- Kiểu phần tử được cung cấp tại runtime và muốn tạo `JavaType` tương ứng.

Không nên dùng TypeReference chỉ để né việc mô tả một schema ổn định bằng DTO hoặc bỏ qua validation. 

## 8. Xây hàm chuyển collection generic an toàn

Một hàm chuyển `List<E>` có thể nhận thêm `Class<E>` để bảo toàn kiểu phần tử ở runtime, thay vì tự ép kiểu unchecked:

```java
import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Objects;

public final class JsonListMapper {

    private final ObjectMapper mapper;

    public JsonListMapper(ObjectMapper mapper) {
        this.mapper = Objects.requireNonNull(mapper);
    }

    public <E> List<E> convertRequiredList(
            Object value,
            Class<E> elementType) {

        Objects.requireNonNull(elementType);
        if (!(value instanceof List<?>)) {
            throw new IllegalArgumentException(
                    "Giá trị phải là JSON array");
        }

        JavaType listType = mapper.getTypeFactory()
                .constructCollectionType(List.class, elementType);

        try {
            return mapper.convertValue(value, listType);
        } catch (IllegalArgumentException conversionError) {
            throw new IllegalArgumentException(
                    "Không thể ánh xạ các phần tử của array");
        }
    }
}
```

Cách gọi:

```java
JsonListMapper listMapper = new JsonListMapper(mapper);

List<RoutingSecret.Route> routes =
        listMapper.convertRequiredList(
                data.get("routes"), RoutingSecret.Route.class);
```

Hàm đã nhận được `Class<E>` thật, nên xây dựng được `JavaType` cho `List<E>`. Dù vậy, kết quả vẫn chỉ thỏa **cấu trúc mà bộ chuyển đổi chấp nhận**; còn cần kiểm tra các quy tắc nghiệp vụ như `weight` thuộc khoảng `0..100` hay `id` không rỗng.

Nếu một phần tử JSON là `null` và mapper cho phép, danh sách kết quả vẫn có thể chứa null. `List<E>` không có nghĩa mọi phần tử đều khác null. Muốn danh sách bất biến và không chứa null, có thể kiểm tra từng phần tử rồi tạo `List.copyOf(...)`; phương thức này từ chối null thay vì xử lý im lặng.

## 9. Generic wildcard: đọc dữ liệu chưa tin cậy trước khi chuyển thành kiểu cụ thể

Khi dữ liệu đến từ JSON chưa rõ schema, hai dạng wildcard hữu ích là `List<?>` và `Map<?, ?>`. Chúng cho phép kiểm tra cấu trúc ở runtime mà không giả định kiểu phần tử:

```java
Object value = data.get("allowedRegions");

if (!(value instanceof List<?> rawRegions)) {
    throw new IllegalArgumentException(
            "allowedRegions phải là array");
}

for (Object element : rawRegions) {
    if (!(element instanceof String name) || name.isBlank()) {
        throw new IllegalArgumentException(
                "allowedRegions chứa phần tử sai kiểu");
    }
}
```

So sánh:

| Kiểu Java | Ý nghĩa | Độ an toàn khi đọc dữ liệu động |
|---|---|---|
| `Object` | Giá trị bất kỳ | Phải kiểm tra trước mọi thao tác cụ thể |
| `List<?>` | Biết là List, chưa biết kiểu phần tử | Hữu ích để lặp và kiểm tra từng phần tử |
| `Map<?, ?>` | Biết là Map, chưa biết kiểu khóa/giá trị | Hữu ích để kiểm tra key/value |
| `List<String>` | Danh sách chuỗi ở mức khai báo | Có thể tin sau khi converter/validator xác minh; raw cast không đủ |
| `Map<String, Object>` | Key chuỗi, value bất kỳ theo hợp đồng Java | Cần kiểm tra kiểu từng value |
| `List<? extends Number>` | Phần tử có kiểu là một subtype của Number theo khai báo | Không dùng để tự xác thực một List lấy từ JSON bằng ép kiểu raw |

**Không cần dùng wildcard phức tạp cho mọi API đọc KV.** Với secret có schema cố định, DTO có field cụ thể và validator thường đơn giản hơn.

## 10. Định nghĩa generic type là chưa đủ: xác thực schema và miền giá trị

Khi dùng `Class<T>` hoặc `TypeReference<T>`, việc chuyển đổi có thể báo lỗi, hoặc có thể tạo đối tượng chứa giá trị chưa hợp lệ. Một số tình huống:

| Input JSON | DTO/Generic được khai báo | Nguy cơ | Điều cần kiểm tra |
|---|---|---|---|
| Không có `password` | `String password` | Thuộc tính `null` | Field bắt buộc |
| `"port": "5432"` | `Integer port` | Mapper có thể ép chuỗi thành số | Coercion policy; kiểu JSON thực tế |
| `"port": 70000` | `Integer port` | Đúng kiểu, sai cổng TCP | Phạm vi `1..65535` |
| `"allowedRegions": []` | `List<String>` | List hợp kiểu, thiếu vùng cần thiết | Không rỗng nếu nghiệp vụ yêu cầu |
| `"allowedRegions": [null]` | `List<String>` | Phần tử null | Duyệt và kiểm tra |
| `"routes": [{"weight": 120}]` | `List<Route>` | Cấu trúc DTO đúng, trọng số sai | Quy tắc `0..100` và tổng |
| `"dailyQueries": 2.5` | `Integer dailyQueries` | Có thể bị từ chối hoặc ép kiểu tùy mapper | Không chấp nhận mất phần thập phân ngoài ý muốn |
| `"retry": {"maxAttempts": "abc"}` | DTO nested với `Integer` | Chuyển đổi thất bại | Lỗi mapping phải rõ loại, không lộ secret |

### 10.1. Đọc number không định kiểu

Nếu cần chuyển một `Number` từ `Map` chưa định kiểu sang số nguyên, **đừng** chỉ gọi `intValue()`. Cách đó có thể làm mất phần thập phân hoặc tràn phạm vi. Một helper kiểm tra chặt:

```java
import java.math.BigDecimal;
import java.util.Map;

static int requireInt(Map<String, Object> data, String key) {
    Object value = data.get(key);
    if (!(value instanceof Number number)) {
        throw new IllegalArgumentException(
                key + " phải là JSON number");
    }

    try {
        return new BigDecimal(number.toString()).intValueExact();
    } catch (NumberFormatException | ArithmeticException conversionError) {
        throw new IllegalArgumentException(
                key + " phải là số nguyên thuộc phạm vi int");
    }
}
```

Đây là kiểm tra **giá trị Java sau deserialize**; nếu converter đã làm mất độ chính xác của number trước khi tạo `Number`, chuyển sang `BigDecimal` sau đó không khôi phục được dữ liệu nguồn. Với số tiền hay thông tin cần đúng từng chữ số, phải thiết kế mapping và kiểu số phù hợp ngay từ đầu.

### 10.2. Phân biệt thiếu key và key chứa JSON null

Với `Map`:

```java
if (!data.containsKey("optionalNote")) {
    // Key vắng mặt.
} else if (data.get("optionalNote") == null) {
    // Key có mặt nhưng chứa JSON null.
}
```

Đối với DTO JavaBean, cả hai trường hợp thường thành giá trị property `null`. Nếu hợp đồng cần phân biệt sự vắng mặt và null (ví dụ PATCH có ý nghĩa “xóa field”), phải thiết kế cơ chế biểu diễn riêng hoặc kiểm tra bằng Map ở ranh giới.

## 11. Ranh giới API: generic hỗ trợ kiến trúc sạch

Một mô hình thường dùng cho Spring Vault:

```text
             Workload identity + Vault policy
                            │
                            ▼
                  VaultOperations / VaultTemplate
                            │
                            ▼
           VaultKeyValueOperations (KV_2)
                            │
              get(path, Dto.class)
                            │
                            ▼
              VaultResponseSupport<Dto>
                            │
                     DTO + validation
                            │
                            ▼
               Validated application settings
                            │
                            ▼
                  Business service / client
```

Phương thức generic giúp **giảm lặp mã đọc và kiểm tra phản hồi**. Mỗi adapter chuyên môn vẫn cần chịu trách nhiệm về schema, quy ước tên, validate và cách xử lý không tìm thấy secret.

Ví dụ:

```java
public final class ReportingConfigProvider {

    private final TypedKvReader reader;

    public ReportingConfigProvider(TypedKvReader reader) {
        this.reader = reader;
    }

    public ReportingSecret load() {
        ReportingSecret secret = reader.readRequired(
                "services/reporting", ReportingSecret.class);

        ReportingSecretValidator.validate(secret);
        return secret;
    }
}
```

Đặt validation trong một lớp có thể kiểm thử riêng:

```java
public final class ReportingSecretValidator {

    private ReportingSecretValidator() {
    }

    public static void validate(ReportingSecret secret) {
        if (secret == null) {
            throw new IllegalStateException("Thiếu reporting secret");
        }
        if (secret.getUsername() == null
                || secret.getUsername().isBlank()) {
            throw new IllegalStateException(
                    "Reporting username không hợp lệ");
        }
        if (secret.getPassword() == null
                || secret.getPassword().isBlank()) {
            throw new IllegalStateException(
                    "Reporting password không hợp lệ");
        }
        if (secret.getPort() == null
                || secret.getPort() < 1
                || secret.getPort() > 65535) {
            throw new IllegalStateException(
                    "Reporting port không hợp lệ");
        }
    }
}
```

Validator này bao phủ ba trường bắt buộc để minh họa. Trong mã sản xuất, nên xác thực thêm vùng và giới hạn truy vấn; sau đó chuyển sang một đối tượng cấu hình bất biến nếu các lớp nghiệp vụ cần hợp đồng ổn định. DTO chỉ là phương tiện ánh xạ, không phải nơi lưu thông tin xác thực vô thời hạn.

**Không biến helper generic thành một kho xử lý mọi engine.** KV, dynamic database credentials, Transit và PKI có các hợp đồng phản hồi khác nhau. Một `Class<T>` phù hợp với DTO dữ liệu nghiệp vụ KV không có nghĩa mọi endpoint đều trả payload cùng cấu trúc. Nếu dùng secrets có lease, cần cơ chế quản lý lease/token tương ứng, thay vì suy luận lifecycle từ generic type.

## 12. Xử lý lỗi khi đọc generic

Lỗi nên được phân loại theo bước xảy ra:

1. **Truy cập Vault:** network, TLS, workload authentication, Vault policy hoặc lỗi server. Đây là vấn đề kết nối/quyền, không phải Java generic.
2. **Không có dữ liệu:** kết quả `get(...)` hoặc `getData()` là `null`, cần quyết định secret có bắt buộc không.
3. **Chuyển đổi JSON thất bại:** trường sai kiểu, tên field không khớp hoặc generic collection không thể ánh xạ.
4. **Validation nghiệp vụ thất bại:** DTO đã được tạo nhưng thiếu trường, giá trị nằm ngoài giới hạn, list rỗng hoặc thiếu điều kiện liên trường.

Không gom tất cả lỗi thành `null` hoặc tạo DTO rỗng:

```java
// Không áp dụng cách xử lý này:
// catch (Exception ignored) {
//     return null;
// }
```

Đặc biệt, lỗi 403 do Vault policy không đồng nghĩa secret không tồn tại. Một generic reader nên để tầng gọi nhận biết lỗi truy cập riêng với lỗi dữ liệu; trong ứng dụng thực tế có thể chuẩn hóa bằng các loại exception theo miền nghiệp vụ, nhưng phải giữ được khả năng chẩn đoán mà không tiết lộ payload.

### 12.1. An toàn thông tin khi chẩn đoán

- Không log `VaultResponse`, `VaultResponseSupport<T>`, DTO, `Map` hoặc `List` nếu có thể chứa mật khẩu, API key, token hay khóa riêng.
- Cẩn thận với `record.toString()`, Lombok `@Data` và các phương thức serialize tự động: chúng có thể hiển thị toàn bộ thuộc tính.
- Chỉ ghi tên trường, loại lỗi, kết quả thao tác và request ID của Vault khi chính sách giám sát cho phép; không gửi nội dung secret vào metric label, log, trace hay thông báo HTTP.
- Exception từ JSON converter có thể chứa đường dẫn hoặc trích đoạn giá trị lỗi. Kiểm soát nơi ghi stack trace; ví dụ trên dùng thông báo khái quát để tránh lan truyền payload.
- Nếu secret được rotate, một DTO được giữ trong bộ nhớ có thể trở nên lỗi thời. Generic reader không tự làm mới cache hoặc gia hạn token/lease.

## 13. Kiểm thử generic reader và schema

### 13.1. Unit test cho DTO/validation

Không cần Vault thật để kiểm tra các quy tắc miền giá trị. Các test dưới đây gọi trực tiếp `ReportingSecretValidator.validate(...)` đã định nghĩa trong mục 11, giúp kiểm tra cả trường hợp thành công lẫn thất bại:

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ReportingSecretValidationTest {

    @Test
    void acceptsValidSecret() {
        ReportingSecret secret = new ReportingSecret();
        secret.setUsername("fake-user");
        secret.setPassword("fake-password-only-for-test");
        secret.setPort(5432);

        assertDoesNotThrow(() -> ReportingSecretValidator.validate(secret));
    }

    @Test
    void rejectsPortOutOfRange() {
        ReportingSecret secret = new ReportingSecret();
        secret.setUsername("fake-user");
        secret.setPassword("fake-password-only-for-test");
        secret.setPort(70000);

        assertThrows(IllegalStateException.class,
                () -> ReportingSecretValidator.validate(secret));
    }

    @Test
    void rejectsMissingPassword() {
        ReportingSecret secret = new ReportingSecret();
        secret.setUsername("fake-user");
        secret.setPort(5432);

        assertThrows(IllegalStateException.class,
                () -> ReportingSecretValidator.validate(secret));
    }
}
```

Các ca này kiểm thử hành vi của validator thay vì lặp lại cùng biểu thức điều kiện trong test. Ví dụ chỉ dùng dữ liệu giả, không chứa secret production.

### 13.2. Unit test chuyển generic collection với Jackson

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Test;

class RouteTypeReferenceTest {

    @Test
    void convertsRouteArrayWithElementType() {
        String json = """
                [
                  {"id":"primary","weight":80},
                  {"id":"secondary","weight":20}
                ]
                """;

        ObjectMapper mapper = new ObjectMapper();
        List<RoutingSecret.Route> routes = mapper.readValue(
                json,
                new TypeReference<List<RoutingSecret.Route>>() {});

        assertEquals("primary", routes.get(0).getId());
        assertEquals(20, routes.get(1).getWeight());
    }
}
```

Test này xác nhận Jackson có đủ kiểu phần tử từ `TypeReference`. Nó **không** khẳng định Spring Vault đang dùng chính `ObjectMapper` đó.

### 13.3. Kiểm thử tích hợp với Vault

Trong môi trường thử nghiệm có mount KV v2 và workload identity/policy giới hạn, hãy kiểm tra:

| Ca | Kỳ vọng |
|---|---|
| `kv.get(path, ReportingSecret.class)` với các trường đúng | DTO có String, Integer, Boolean, List và nested object đúng |
| `kv.get(path, RoutingSecret.class)` với list các route | Các phần tử có kiểu Route và dữ liệu đúng |
| Thiếu `password` | Validation từ chối hoặc cơ chế mapping bắt buộc được cấu hình báo lỗi |
| List `routes` có một phần tử sai kiểu | Converter hoặc validator báo lỗi; không bị bỏ qua |
| Port ngoài phạm vi hoặc JSON number lớn | Validation/mapping từ chối mà không tràn số âm thầm |
| JSON number được lưu dưới dạng chuỗi | Kết quả theo quy tắc coercion đã xác định, có kiểm thử rõ |
| Path không tồn tại | Adapter xử lý phản hồi rỗng theo hợp đồng |
| Token/workload không có quyền đọc | Trả lỗi truy cập, không coi là list/DTO rỗng |
| KV v2 đọc trực tiếp bằng `vaultOperations.read(...)` | Thấy lớp bao `data`/`metadata`, khác với API KV mức cao |

Thực hiện kiểm thử với secret giả, không ghi credentials sản xuất vào fixture hoặc báo cáo CI. Nếu dùng JSON mapper được cấu hình riêng (đổi naming strategy hoặc strict coercion), cần kiểm thử **đúng client và mapper thực sự được Spring Vault sử dụng**.

## 14. Bài tập thực hành

### Bài tập 1 — Viết reader generic

Tạo DTO `MailSecret` với `smtpHost`, `smtpPort` và `password`. Viết `TypedKvReader.readRequired(path, Class<T>)` đọc KV v2 từ mount thử nghiệm. Dùng cùng reader để đọc `MailSecret` và `ReportingSecret`. Kiểm tra:

1. `Class<T>` được truyền cho converter là kiểu nào?
2. Vì sao compiler biết kết quả của hai lời gọi là hai DTO khác nhau?
3. Reader có nên tự validate tất cả thuộc tính riêng của từng DTO không?
4. Điều gì xảy ra nếu Vault từ chối đọc path?

### Bài tập 2 — Tránh ép kiểu generic

Secret chứa:

```json
{
  "targets": [
    {"host": "a.internal", "port": 8080},
    {"host": "b.internal", "port": 8081}
  ]
}
```

Tạo `TargetsSecret` với `List<Target> targets`, trong đó `Target` có `host` và `port`. Đọc bằng `kv.get("services/targets", TargetsSecret.class)`, sau đó kiểm tra port trong `1..65535`. Giải thích vì sao `List<Target>.class` không tồn tại và vì sao không nên ép `data.get("targets")` trực tiếp thành `List<Target>`.

### Bài tập 3 — Generic lồng nhau

Một adapter có cấu trúc:

```json
{
  "targetsByEnvironment": {
    "dev": [{"host": "dev.internal", "port": 8080}],
    "prod": [{"host": "prod.internal", "port": 8443}]
  }
}
```

Hãy viết kiểu `Map<String, List<Target>>` và đề xuất hai cách ánh xạ: (a) một DTO chứa field generic đầy đủ, (b) đọc field từ `Map` rồi chuyển bằng Jackson `TypeReference<Map<String, List<Target>>>`. Nêu validation cần có và giải thích vì sao không thể truyền `Map<String, List<Target>>.class`.

### Bài tập 4 — Phân loại lỗi

Một request đọc secret thất bại. Hãy xác định cách xử lý khi (a) response `null`, (b) JSON có trường `timeoutSeconds` là object, (c) workload bị 403, (d) token hợp lệ nhưng secret được rotate, client vẫn đang giữ bản cũ. Trường hợp nào cần sửa generic/mapping, trường hợp nào thuộc xác thực, policy hoặc vòng đời secrets?

**Định hướng:** (a) dữ liệu không tồn tại; (b) lỗi schema/mapping; (c) quyền Vault; (d) chiến lược cập nhật dữ liệu và lifecycle. Không dùng một `catch (Exception)` chung để trả cấu hình mặc định cho cả bốn tình huống.

## 15. Những điều cần ghi nhớ

- `VaultResponseSupport<T>` biểu diễn phần `data` có kiểu `T` trong phản hồi Vault; `VaultResponse` là biến thể `T = Map<String, Object>`.
- `Class<T>` cung cấp kiểu cụ thể cho API đọc KV như `get(path, Dto.class)`. Nó hữu ích để viết reader generic nhưng không biểu diễn trực tiếp `List<Route>` hay generic nhiều cấp.
- Java generic có **type erasure**; ép kiểu unchecked không xác minh các phần tử bên trong collection. Kiểm tra `List<?>`, `Map<?, ?>` hoặc dùng converter có type token phù hợp.
- Khi schema ổn định, đặt `List<Route>`/`Map<String, Integer>` bên trong một DTO gốc cụ thể là cách đơn giản và dễ kiểm thử.
- `TypeReference` và `JavaType` của Jackson dùng để bảo toàn thông tin generic **trong chuyển đổi JSON cục bộ**; không mặc định rằng phương thức KV `get(path, Class<T>)` nhận các tham số đó.
- Dù mapping có kiểu thành công, vẫn phải validate null, trường thiếu, số ngoài phạm vi, kiểu JSON và ràng buộc liên trường.
- Đọc generic không thay thế Vault policy, workload authentication, quản lý token/lease, rotation, Transit hay PKI; tuyệt đối không log DTO hoặc payload chứa secrets.

## Tài liệu đối chiếu

- [Spring Vault — `VaultResponseSupport<T>` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponseSupport.html): phản hồi có dữ liệu generic và các accessor.
- [Spring Vault — `VaultResponse` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/support/VaultResponse.html): kiểu phản hồi dùng `Map<String, Object>`.
- [Spring Vault — `VaultKeyValueOperations` API](https://docs.spring.io/spring-vault/docs/current/api/org/springframework/vault/core/VaultKeyValueOperations.html): phương thức đọc KV với `Class<T>`.
- [Spring Vault — Vault Secrets Engines](https://docs.spring.io/spring-vault/reference/vault/vault-secret-engines.html): khác biệt KV v1/KV v2 và API dữ liệu có phiên bản.
- [Jackson Databind — `TypeReference` và `JavaType`](https://github.com/FasterXML/jackson-databind): chuyển đổi collection và generic nhiều cấp.
- [HashiCorp Vault — KV v2 API](https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2): cấu trúc JSON của secret và metadata phiên bản.
