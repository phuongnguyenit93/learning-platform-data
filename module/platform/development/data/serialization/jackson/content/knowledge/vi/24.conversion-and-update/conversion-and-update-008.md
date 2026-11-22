# Đánh giá cách cập nhật collection, Map và đối tượng bất biến

Khi Jackson đọc JSON vào một object mới, nó tạo trạng thái từ dữ liệu đầu vào. Nhưng nhiều ứng dụng cần cập nhật một object đã tồn tại: giữ lại field không được gửi, thay đổi một vài field, thêm phần tử vào collection hoặc cập nhật một số key trong map. Đây là bài toán khác với deserialization thông thường vì kết quả phụ thuộc vào trạng thái hiện tại và chính sách đối với field bị thiếu, null hoặc có giá trị mới.

Jackson hỗ trợ cập nhật object qua **ObjectReader.readerForUpdating()** và **ObjectMapper.updateValue()**. Với property lồng nhau, annotation **@JsonMerge** có thể yêu cầu gộp dữ liệu vào giá trị hiện có thay vì thay thế toàn bộ property. Tuy nhiên, collection, map và object bất biến có đặc điểm khác nhau. List thường được merge bằng cách nối thêm phần tử; Map được merge theo key; POJO mutable có thể được cập nhật theo property; còn record và value object bất biến cần được tạo thành instance mới.

Để chọn đúng cơ chế, cần xác định rõ mục tiêu: thay thế toàn bộ giá trị, gộp nội dung, bỏ qua null, xóa bằng null hay tạo object mới từ trạng thái cũ và phần thay đổi. Không nên coi mọi cơ chế update của Jackson là cùng một loại merge.

## 1. Deserialization mới và cập nhật object có sẵn

Đọc JSON thông thường tạo một object mới:

~~~java
UserProfile profile = mapper.readValue(json, UserProfile.class);
~~~

Nếu đã có profile và muốn áp dụng dữ liệu mới lên nó, có thể dùng:

~~~java
UserProfile updated = mapper.readerForUpdating(profile)
        .readValue(json);
~~~

readerForUpdating(profile) tạo một ObjectReader gắn với object đích. Jackson dùng deserializer để cập nhật object đó theo các property có trong input. Với bean mutable thông thường, property không xuất hiện trong JSON thường không bị thay đổi; property được gửi sẽ được xử lý theo quy tắc deserialization và merge của nó.

Ví dụ:

~~~java
public class UserProfile {
    private String displayName;
    private String email;
    private boolean active;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }
    public String getEmail() { return email; }
    public void setEmail(String value) { email = value; }
    public boolean isActive() { return active; }
    public void setActive(boolean value) { active = value; }
}
~~~

Object hiện tại có displayName = "An Nguyen", email = "an@example.com" và active = true. JSON cập nhật chỉ gửi:

~~~json
{
  "displayName": "An N."
}
~~~

Sau khi gọi readerForUpdating(), displayName được đổi thành An N., còn email và active giữ nguyên vì chúng không xuất hiện trong JSON.

### 1.1. readerForUpdating() và updateValue()

Hai API có mục đích gần nhau nhưng đầu vào khác nhau:

~~~java
// Đọc JSON text trực tiếp vào object đã tồn tại.
mapper.readerForUpdating(existing).readValue(jsonText);

// Cập nhật từ một object Java hoặc JsonNode.
mapper.updateValue(existing, overrides);
~~~

readerForUpdating() nhận dữ liệu JSON qua các overload readValue(). updateValue() nhận một object Java làm nguồn override; Jackson chuyển nguồn đó qua cơ chế token nội bộ rồi áp dụng vào target. Nếu overrides là JsonNode, node có thể được dùng như cấu trúc dữ liệu để cập nhật. Nếu overrides là String, Jackson xem nó là giá trị Java kiểu string, không tự phân tích nội dung string thành JSON text.

updateValue() trả về giá trị sau cập nhật; với object mutable, thường chính là target đã truyền vào. Không mặc định mọi kiểu đích đều có thể được cập nhật tại chỗ. Đặc biệt, object bất biến cần chiến lược tạo instance mới.

## 2. Ba trạng thái cần phân biệt khi cập nhật

Trong một request cập nhật, mỗi property có thể rơi vào một trong ba tình huống:

| Trạng thái JSON | Ý nghĩa thường dùng trong update |
|---|---|
| Field không xuất hiện | Không yêu cầu thay đổi field đó; giữ giá trị hiện tại. |
| Field xuất hiện với null | Gửi giá trị null; theo null policy có thể đặt null, bỏ qua hoặc từ chối. |
| Field xuất hiện với giá trị | Thay thế hoặc gộp theo kiểu property và cấu hình. |

Ví dụ {} không có yêu cầu cập nhật nickname; {"nickname":null} có field hiện diện với giá trị null; {"nickname":"An"} gửi giá trị mới.

Sự phân biệt này rất quan trọng với API PATCH. Nếu client gửi null để xóa giá trị, cấu hình Nulls.SKIP sẽ làm request không thực hiện ý định đó. Nếu client muốn null có nghĩa “không cập nhật”, Nulls.SKIP có thể phù hợp.

## 3. Hành vi mặc định: property lồng nhau thường được thay thế

Giả sử một bean có property object lồng nhau:

~~~java
public class Address {
    private String city;
    private String district;
    private String postalCode;
    // Getter/setter.
}

public class CustomerProfile {
    private String name;
    private Address address;
    // Getter/setter.
}
~~~

Object hiện tại có địa chỉ gồm city = "Ho Chi Minh City", district = "District 1" và postalCode = "700000". JSON cập nhật:

~~~json
{
  "address": {
    "city": "Thu Duc City"
  }
}
~~~

Nếu không bật merge cho property address, Jackson mặc định deserialize giá trị address thành một object mới rồi gán vào property. Object mới chỉ có dữ liệu được cung cấp và các giá trị mặc định còn lại. district và postalCode cũ có thể bị mất vì toàn bộ address đã bị thay thế.

Việc gọi readerForUpdating(customer) không tự động có nghĩa mọi object con đều được cập nhật đệ quy vào instance cũ. Nếu muốn giữ các property con không được gửi, cần cấu hình merge cho property tương ứng.

## 4. Dùng @JsonMerge cho property object

@JsonMerge yêu cầu Jackson gộp nội dung JSON mới vào giá trị property đang có, nếu kiểu property và deserializer hỗ trợ cập nhật. Với POJO mutable, Jackson có thể cập nhật các property bên trong object hiện có thay vì thay toàn bộ reference.

~~~java
import com.fasterxml.jackson.annotation.JsonMerge;

public class CustomerProfile {
    private String name;

    @JsonMerge
    private Address address;

    // Getter/setter.
}
~~~

Với cùng JSON {"address":{"city":"Thu Duc City"}}, Jackson cập nhật city trong Address hiện có; district và postalCode giữ giá trị cũ. @JsonMerge không có nghĩa mọi kiểu Java đều có thể được cập nhật. Property phải có giá trị hiện tại có thể dùng để merge và deserializer phải hỗ trợ update semantics.

### 4.1. @JsonMerge không phải deep merge tổng quát

Merge được thực hiện theo quy tắc của deserializer cho kiểu cụ thể. Nó không phải thuật toán đệ quy tùy ý trên mọi object graph, cũng không tự giải quyết identity, tham chiếu vòng hoặc xung đột nghiệp vụ. Nếu property bên trong Address lại là collection/map, cần đánh giá merge semantics của property đó riêng.

Nếu property hiện tại là null, Jackson không có object cũ để cập nhật; thông thường nó phải tạo giá trị mới từ input. Nếu kiểu không thể cập nhật tại chỗ, kết quả phụ thuộc deserializer. Hãy kiểm tra hành vi với kiểu thực tế.

## 5. Cập nhật Collection: thay thế hay nối thêm?

Collection có nhiều cách hiểu khi cập nhật. Với một property List<String>, JSON mới có thể mang nghĩa thay thế toàn bộ danh sách, nối phần tử vào cuối, gộp theo khóa logic hoặc cập nhật theo vị trí index. Jackson không tự suy ra ý nghĩa nghiệp vụ như “gộp người dùng có cùng ID” hay “xóa phần tử đã biến mất khỏi JSON”.

### 5.1. Mặc định: property collection được thay thế

~~~java
public class Team {
    private List<String> members = new ArrayList<>();

    public List<String> getMembers() { return members; }
    public void setMembers(List<String> members) { this.members = members; }
}
~~~

Giả sử danh sách cũ là [An, Binh, Chi] và JSON gửi:

~~~json
{"members": ["Dung"]}
~~~

Khi property không được đánh dấu merge, Jackson deserialize thành collection mới và gán vào members. Kết quả là danh sách chỉ còn Dung. Đây thường là semantics phù hợp cho PUT hoặc khi field đại diện toàn bộ tập phần tử hiện tại.

### 5.2. @JsonMerge với List thường nối thêm phần tử

~~~java
public class Team {
    @JsonMerge
    private List<String> members = new ArrayList<>();

    public List<String> getMembers() { return members; }
    public void setMembers(List<String> members) { this.members = members; }
}
~~~

Với cùng trạng thái cũ và JSON {"members":["Dung"]}, merge collection thường thêm phần tử đầu vào vào collection hiện có:

~~~text
Trước: [An, Binh, Chi]
Input: [Dung]
Sau:   [An, Binh, Chi, Dung]
~~~

Đây là thao tác append, không phải ghép theo index và cũng không tự loại phần tử trùng. Nếu gửi lại cùng request hai lần, Dung có thể xuất hiện hai lần. Vì vậy, @JsonMerge với List chỉ phù hợp khi semantics “thêm các phần tử mới” là điều API muốn.

### 5.3. Merge collection không đồng nghĩa merge theo ID

Giả sử collection chứa các dòng đơn hàng:

~~~java
public record OrderLine(String lineId, String productCode, int quantity) {
}
~~~

JSON gửi một line có lineId = "line-1" không có nghĩa Jackson sẽ tìm line cũ cùng ID rồi cập nhật nó. @JsonMerge không biết lineId là khóa nghiệp vụ. Collection deserializer xử lý phần tử theo kiểu collection, thường là thêm giá trị mới.

Nếu cần upsert theo ID, hãy thực hiện ở tầng service/domain:

1. Lập map các phần tử hiện tại theo ID.
2. Duyệt các phần tử patch.
3. Nếu ID đã có, tạo/cập nhật phần tử theo quy tắc nghiệp vụ.
4. Nếu ID chưa có, thêm phần tử mới nếu được phép.
5. Xử lý phần tử bị thiếu theo chính sách xóa hoặc giữ nguyên.

Đừng dùng append semantics thay cho upsert semantics.

## 6. Cập nhật Map theo key

Map có cấu trúc key-value nên semantics merge tự nhiên hơn collection. Khi property Map được đánh dấu @JsonMerge, Jackson có thể gộp các entry mới vào map hiện tại:

~~~java
public class RuntimeConfig {
    @JsonMerge
    private Map<String, String> labels = new LinkedHashMap<>();

    public Map<String, String> getLabels() { return labels; }
    public void setLabels(Map<String, String> labels) { this.labels = labels; }
}
~~~

Map cũ:

~~~text
language -> vi
theme    -> light
region   -> ap-southeast
~~~

JSON:

~~~json
{
  "labels": {
    "theme": "dark",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
~~~

Sau merge, map giữ các key không được gửi và cập nhật/thêm key có trong input:

~~~text
language -> vi
theme    -> dark
region   -> ap-southeast
timezone -> Asia/Ho_Chi_Minh
~~~

Với key đã tồn tại, value mới thường thay value cũ. Với key mới, entry được thêm. Đây là merge theo key của Map, không phải merge theo vị trí.

### 6.1. Map value là object

Nếu map có value là POJO, ví dụ Map<String, NotificationSettings>, cần xem xét cả semantics của map và semantics của value. @JsonMerge trên property map yêu cầu merge map; việc một value hiện có được cập nhật sâu hay bị thay thế còn phụ thuộc cách deserializer xử lý value và cấu hình merge của kiểu đó.

~~~java
public class NotificationSettings {
    private boolean emailEnabled;
    private boolean smsEnabled;
    // Getter/setter.
}

public class UserSettings {
    @JsonMerge
    private Map<String, NotificationSettings> channels = new LinkedHashMap<>();
    // Getter/setter.
}
~~~

Nếu input chỉ cập nhật emailEnabled cho key primary, đừng giả định smsEnabled của object cũ chắc chắn được giữ nếu chưa kiểm tra merge behavior của value deserializer. Khi yêu cầu merge sâu quan trọng, hãy thiết kế/test rõ từng lớp hoặc thực hiện merge trong service bằng logic tường minh.

### 6.2. Map không tự hiểu null là xóa key

Với JSON {"labels":{"theme":null}}, map có thể nhận key theme với value null theo null policy. Điều này khác với việc xóa entry khỏi map. Nếu muốn null mang nghĩa xóa key, cần xử lý rõ ràng trong service/patch logic hoặc custom deserializer. Đừng giả định @JsonMerge sẽ biến null thành thao tác remove.

## 7. @JsonMerge cho Collection và Map

Một ví dụ kết hợp:

~~~java
public class ProjectSettings {
    private String projectName;

    @JsonMerge
    private List<String> tags = new ArrayList<>();

    @JsonMerge
    private Map<String, String> properties = new LinkedHashMap<>();

    // Getter/setter.
}
~~~

Trạng thái ban đầu:

~~~text
projectName = "Billing"
tags        = [java, backend]
properties  = {region=ap-southeast, mode=stable}
~~~

Input:

~~~json
{
  "tags": ["jackson"],
  "properties": {
    "mode": "strict",
    "timezone": "UTC"
  }
}
~~~

Sau cập nhật theo merge semantics:

~~~text
projectName = "Billing"                 // field thiếu: giữ nguyên
tags        = [java, backend, jackson]  // collection: nối thêm
properties  = {                         // map: gộp theo key
  region=ap-southeast,
  mode=strict,
  timezone=UTC
}
~~~

Một JSON request có thể áp dụng quy tắc khác nhau cho từng kiểu property. Field scalar được cập nhật khi có mặt; collection được append; map được gộp theo key. Đây là chính sách cụ thể, không phải quy tắc chung cho mọi API. Nếu API muốn list được thay thế nhưng map được merge, chỉ đánh dấu @JsonMerge trên map.

## 8. Null policy khi cập nhật collection và Map

@JsonMerge điều khiển merge value có cấu trúc; nó không tự định nghĩa ý nghĩa của JSON null. Jackson có @JsonSetter và Nulls để chọn hành vi khi property hoặc phần tử nhận null.

### 8.1. Giữ giá trị hiện tại khi property nhận null

~~~java
import com.fasterxml.jackson.annotation.JsonSetter;
import com.fasterxml.jackson.annotation.Nulls;

public class ProjectSettings {
    @JsonMerge
    @JsonSetter(nulls = Nulls.SKIP)
    private List<String> tags = new ArrayList<>();
}
~~~

Với {"tags":null}, Jackson bỏ qua việc gán null và giữ list hiện tại. Điều này phù hợp nếu null được quy ước là “không cập nhật”.

### 8.2. Chuyển null thành collection rỗng

~~~java
@JsonSetter(nulls = Nulls.AS_EMPTY)
private List<String> tags = new ArrayList<>();
~~~

AS_EMPTY yêu cầu dùng giá trị rỗng do deserializer cung cấp cho kiểu đó. Với collection, thường là collection rỗng. Nếu áp dụng trên property mà không merge, điều này có thể thay list cũ bằng list rỗng; nếu merge được bật, cần xác nhận behavior của kiểu và phiên bản Jackson.

### 8.3. Từ chối null

~~~java
@JsonSetter(nulls = Nulls.FAIL)
private Map<String, String> properties = new LinkedHashMap<>();
~~~

Input có property properties: null sẽ bị từ chối thay vì gán null.

### 8.4. Null bên trong collection/map

nulls điều khiển null của property; contentNulls điều khiển null bên trong collection hoặc map:

~~~java
@JsonSetter(contentNulls = Nulls.SKIP)
private List<String> tags = new ArrayList<>();
~~~

Với input {"tags":["java",null,"jackson"]}, null entry có thể bị bỏ qua. Tùy hợp đồng, có thể chọn FAIL, SKIP, AS_EMPTY hoặc SET. Hãy phân biệt null của cả collection với null của một phần tử.

## 9. Java array khác Collection khi cập nhật

Java array có kích thước cố định sau khi tạo và không có thao tác append. Vì vậy, không nên mong @JsonMerge nối thêm phần tử vào array như List. Với array property, cách cập nhật thông thường là tạo array mới và thay thế tham chiếu.

~~~java
public class Snapshot {
    private String[] labels;

    public String[] getLabels() { return labels; }
    public void setLabels(String[] labels) { this.labels = labels; }
}
~~~

Nếu input gửi labels, Jackson thường tạo array mới và gán vào property. Nếu cần append, hãy dùng List, hoặc tự tạo array mới bằng cách sao chép phần tử cũ và thêm phần tử mới ở tầng ứng dụng.

## 10. Collection bất biến và collection không thể sửa

Một property có kiểu List<T> không bảo đảm instance hiện tại có thể sửa đổi. Ví dụ:

~~~java
List<String> roles = List.of("USER", "EDITOR");
~~~

List.of() trả về list không thể sửa đổi. Nếu merge yêu cầu append vào list đó, thao tác có thể ném UnsupportedOperationException khi Jackson hoặc collection deserializer cố thêm phần tử.

Tương tự, Collections.unmodifiableList() và một số collection từ thư viện bên ngoài có thể không hỗ trợ update tại chỗ. Kiểu khai báo là List không nói lên khả năng mutate của object runtime.

Nếu cần merge mutable, hãy khởi tạo collection có thể sửa:

~~~java
private List<String> roles = new ArrayList<>();
private Map<String, String> attributes = new LinkedHashMap<>();
~~~

Hoặc không dùng in-place merge: tạo collection mới từ dữ liệu cũ và dữ liệu patch, sau đó gán vào object mới. Cách thứ hai thường phù hợp hơn với domain model bất biến.

## 11. Đối tượng bất biến: không thể cập nhật bằng cách sửa field tại chỗ

Object bất biến không cho phép thay đổi trạng thái sau khi được tạo. Các kiểu thường gặp gồm Java record, class chỉ có final field và constructor thiết lập toàn bộ state, value object trả về collection immutable và kiểu dùng builder rồi tạo instance cuối cùng không thể sửa.

~~~java
public record UserProfile(
        String displayName,
        List<String> roles,
        Map<String, String> preferences
) {
    public UserProfile {
        roles = List.copyOf(roles);
        preferences = Map.copyOf(preferences);
    }
}
~~~

Record không có setter để Jackson cập nhật component riêng lẻ. readerForUpdating(existingRecord) không thể biến record thành mutable bean. Cơ chế update tại chỗ không phù hợp; cần tạo một record mới từ các giá trị cũ và những thay đổi đã được áp dụng.

Không nên cố mở rộng quyền truy cập field hoặc thêm setter chỉ để làm cho Jackson update được nếu domain model cần bất biến. Hãy giữ bất biến ở domain và thực hiện patch bằng một bước tạo instance mới.

## 12. Tạo instance mới từ object bất biến và patch JSON

Để phân biệt field thiếu, null và giá trị mới, có thể đọc patch thành JsonNode, sau đó xây dựng record mới. Ví dụ dưới đây quy định:

- Field thiếu: giữ giá trị cũ.
- displayName: null: xóa tên hiển thị.
- roles hiện diện: thay toàn bộ danh sách roles.
- preferences hiện diện dạng object: merge key vào map cũ.
- preferences là null: xóa toàn bộ preferences.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public static UserProfile applyPatch(
        UserProfile current,
        JsonNode patch,
        ObjectMapper mapper
) throws JsonProcessingException {
    if (!patch.isObject()) {
        throw new IllegalArgumentException("Patch must be a JSON object");
    }

    String displayName = current.displayName();
    if (patch.has("displayName")) {
        JsonNode node = patch.get("displayName");
        displayName = node.isNull() ? null : node.asText();
    }

    List<String> roles = current.roles();
    if (patch.has("roles")) {
        JsonNode node = patch.get("roles");
        if (node.isNull()) {
            roles = List.of();
        } else if (node.isArray()) {
            roles = mapper.convertValue(
                    node,
                    new TypeReference<List<String>>() {}
            );
        } else {
            throw new IllegalArgumentException("roles must be an array or null");
        }
    }

    Map<String, String> preferences = new LinkedHashMap<>(current.preferences());
    if (patch.has("preferences")) {
        JsonNode node = patch.get("preferences");
        if (node.isNull()) {
            preferences.clear();
        } else if (node.isObject()) {
            Map<String, String> incoming = mapper.convertValue(
                    node,
                    new TypeReference<Map<String, String>>() {}
            );
            preferences.putAll(incoming);
        } else {
            throw new IllegalArgumentException("preferences must be an object or null");
        }
    }

    return new UserProfile(displayName, roles, preferences);
}
~~~

Trong ví dụ, roles được thay thế toàn bộ khi field xuất hiện; preferences được merge theo key. Đây là quyết định riêng của API. Nếu null trong preferences cần xóa từng key, phải xử lý từng entry thay vì putAll() đơn giản.

Đoạn code dùng JsonNode.has() để nhận biết field có xuất hiện, kể cả khi giá trị là null. path()/asText() đơn thuần không đủ để phân biệt field thiếu với field null trong mọi tình huống.

### 12.1. Với record, có thể dùng constructor hoặc wither

Một record có thể cung cấp method tạo bản sao với một thay đổi:

~~~java
public UserProfile withDisplayName(String newName) {
    return new UserProfile(newName, roles, preferences);
}
~~~

Đây là wither: method không mutate object hiện tại mà trả về instance mới. Với nhiều field, một phương thức apply(patch) hoặc mapper chuyên biệt có thể tập trung quy tắc cập nhật. Mọi instance mới đều đi qua constructor/invariant validation.

Jackson cũng hỗ trợ builder-based deserialization qua @JsonDeserialize(builder = ...) và @JsonPOJOBuilder, nhưng deserialize một JSON hoàn chỉnh thành object builder-backed khác với patch một instance bất biến đã có. Để patch, ứng dụng vẫn cần kết hợp trạng thái cũ với input rồi build object mới.

## 13. Builder-based immutable object

Một class bất biến có thể dùng builder để tạo instance mới:

~~~java
public final class ServerConfig {
    private final String host;
    private final int port;
    private final boolean tlsEnabled;

    private ServerConfig(Builder builder) {
        host = builder.host;
        port = builder.port;
        tlsEnabled = builder.tlsEnabled;
    }

    public String getHost() { return host; }
    public int getPort() { return port; }
    public boolean isTlsEnabled() { return tlsEnabled; }

    public Builder toBuilder() {
        return new Builder()
                .host(host)
                .port(port)
                .tlsEnabled(tlsEnabled);
    }

    public static class Builder {
        private String host;
        private int port;
        private boolean tlsEnabled;

        public Builder host(String value) { host = value; return this; }
        public Builder port(int value) { port = value; return this; }
        public Builder tlsEnabled(boolean value) { tlsEnabled = value; return this; }

        public ServerConfig build() {
            if (host == null || host.isBlank()) {
                throw new IllegalStateException("host is required");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalStateException("port is out of range");
            }
            return new ServerConfig(this);
        }
    }
}
~~~

Khi nhận patch, có thể bắt đầu từ current.toBuilder(), áp dụng field được gửi rồi gọi build(). Như vậy object cũ không bị thay đổi và validation được thực hiện khi tạo instance mới.

Jackson hỗ trợ builder-based deserialization qua @JsonDeserialize(builder = ...) và @JsonPOJOBuilder, nhưng việc deserialize JSON hoàn chỉnh thành object builder-backed khác với cập nhật instance bất biến đã có. Với patch, ứng dụng vẫn cần kết hợp trạng thái cũ và input rồi build object mới.

## 14. @JsonMerge không thay thế cơ chế cập nhật immutable

@JsonMerge hữu ích khi có giá trị hiện tại mà deserializer có thể cập nhật. Với record hoặc class bất biến, không có setter để sửa component và collection bên trong có thể cũng immutable. Vì vậy, không nên dựa vào @JsonMerge để thay đổi instance bất biến tại chỗ.

Nếu property là immutable value object, lựa chọn an toàn thường là:

1. Đọc patch thành DTO hoặc JsonNode.
2. Kết hợp patch với giá trị hiện tại.
3. Tạo value object mới qua constructor/builder.
4. Thay tham chiếu ở aggregate/root hoặc lưu object mới theo transaction.

Nếu kiểu bất biến có custom deserializer hỗ trợ update đặc biệt, hành vi đó phải được tài liệu hóa và kiểm thử riêng; không suy ra từ annotation chung.

## 15. So sánh merge của Jackson với PATCH contract

readerForUpdating() và @JsonMerge là cơ chế Jackson để cập nhật object. Chúng không tự động đồng nghĩa với một chuẩn HTTP PATCH cụ thể.

JSON Merge Patch (RFC 7396) có quy tắc riêng: object member bị bỏ qua thường giữ nguyên; member có null có nghĩa xóa; array được thay thế toàn bộ chứ không append phần tử. Trong khi đó, @JsonMerge trên List có thể append phần tử. Vì vậy, không nên tuyên bố endpoint đang triển khai JSON Merge Patch chỉ vì dùng @JsonMerge.

Nếu API cần tuân thủ một format patch chuẩn, hãy dùng implementation đúng semantics của chuẩn đó và viết test theo các trường hợp null, missing, array, nested object. Nếu API dùng semantics riêng, tài liệu hóa rõ:

- Field thiếu có giữ nguyên không?
- Null có xóa, đặt null, bỏ qua hay bị từ chối?
- Collection được thay thế hay append?
- Map được merge theo key hay thay toàn bộ?
- Có hỗ trợ xóa một phần tử collection theo ID không?
- Object con được merge sâu đến mức nào?

## 16. Cập nhật root Collection hoặc Map

Ngoài cập nhật property bên trong bean, có thể truyền trực tiếp collection/map hiện có cho readerForUpdating():

~~~java
List<String> existing = new ArrayList<>(List.of("java", "jackson"));
mapper.readerForUpdating(existing).readValue("[\\"databind\\"]");
~~~

~~~java
Map<String, String> existing = new LinkedHashMap<>();
existing.put("language", "vi");

mapper.readerForUpdating(existing)
        .readValue("{\\"theme\\":\\"dark\\"}");
~~~

Với root container, deserializer có thể sử dụng instance được cung cấp để thêm hoặc đưa entry vào container. Hành vi cụ thể phụ thuộc loại container và deserializer. Collection không mutable có thể ném lỗi; Map có thể ghi đè key trùng. Hãy xác nhận behavior của kiểu root đang dùng bằng test thay vì suy luận từ cách property được gán trong bean.

Khi cần thay thế hoàn toàn root collection/map, cách rõ ràng hơn là deserialize thành instance mới rồi gán/thay tham chiếu:

~~~java
List<String> replacement = mapper.readValue(
        json,
        new TypeReference<List<String>>() {}
);
~~~

## 17. Cập nhật collection có phần tử là object

Giả sử một nhóm người dùng có danh sách thành viên:

~~~java
public class Member {
    private String id;
    private String displayName;
    // Getter/setter.
}

public class Group {
    @JsonMerge
    private List<Member> members = new ArrayList<>();
    // Getter/setter.
}
~~~

Input:

~~~json
{
  "members": [
    {"id": "u-1", "displayName": "An Updated"}
  ]
}
~~~

Merge collection không tự tìm phần tử hiện tại có id = "u-1" để cập nhật. Nó thường thêm một Member mới vào cuối list. Nếu cần cập nhật theo ID, hãy viết logic riêng:

~~~java
Map<String, Member> byId = existingMembers.stream()
        .collect(Collectors.toMap(Member::getId, Function.identity()));

for (MemberPatch patch : incomingPatches) {
    Member current = byId.get(patch.id());
    if (current == null) {
        // Thêm mới nếu chính sách cho phép.
    } else {
        // Tạo member mới hoặc cập nhật member theo quy tắc nghiệp vụ.
    }
}
~~~

Đối với domain object bất biến, nhánh cập nhật sẽ tạo Member mới. Đối với mutable object, có thể cập nhật instance cũ nếu domain cho phép. Trong cả hai trường hợp, key logic và xử lý phần tử trùng phải do ứng dụng quyết định.

## 18. Kiểm soát collection và Map sau khi cập nhật

| Đặc điểm | Câu hỏi cần quyết định |
|---|---|
| Duplicate trong List | Có cho phép phần tử trùng không? Có cần deduplicate theo ID không? |
| Thứ tự List | Phần tử mới nối cuối hay cần vị trí cụ thể? |
| Set | Dựa trên equals()/hashCode() nào để nhận diện trùng? |
| Map key | Key mới có được thêm không? Key cũ có được ghi đè không? |
| Map null value | Null là giá trị hợp lệ hay có nghĩa xóa key? |
| Collection immutable | Có thể mutate tại chỗ hay cần tạo bản sao? |
| Kích thước | Có giới hạn số phần tử/key mới được thêm không? |
| Idempotency | Gửi lại cùng patch có tạo duplicate hoặc thay đổi thêm không? |

Với Set, việc thêm phần tử phụ thuộc equality của kiểu phần tử. Với List, Jackson không biết khóa nghiệp vụ. Với Map, key là điểm định danh tự nhiên nhưng null value vẫn cần semantics riêng. Không nên coi @JsonMerge là chính sách deduplication hoặc validation.

## 19. Cấu hình merge ở cấp property

@JsonMerge có thể được đặt trên field hoặc property thích hợp:

~~~java
public class Preferences {
    @JsonMerge
    private Address address;

    @JsonMerge
    private List<String> interests;

    @JsonMerge
    private Map<String, String> options;
}
~~~

Nếu không muốn sửa class, có thể áp dụng annotation thông qua mix-in:

~~~java
abstract class PreferencesMixin {
    @JsonMerge
    abstract Address getAddress();

    @JsonMerge
    abstract List<String> getInterests();

    @JsonMerge
    abstract Map<String, String> getOptions();
}

mapper.addMixIn(Preferences.class, PreferencesMixin.class);
~~~

Mix-in chỉ bổ sung metadata annotation cho Jackson. Nó không thay đổi khả năng mutable của object runtime, không biến record thành mutable và không tạo semantics upsert theo ID cho collection.

## 20. Kiểm thử update behavior

Vì update phụ thuộc trạng thái ban đầu, test cần chuẩn bị object trước, áp dụng JSON rồi kiểm tra cả field được gửi lẫn field không được gửi.

~~~java
import com.fasterxml.jackson.annotation.JsonMerge;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class MergeUpdateTest {
    static class Settings {
        @JsonMerge
        public List<String> tags = new ArrayList<>();

        @JsonMerge
        public Map<String, String> labels = new LinkedHashMap<>();
    }

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void mergesListAndMapProperties() throws Exception {
        Settings current = new Settings();
        current.tags.addAll(List.of("java", "backend"));
        current.labels.put("theme", "light");
        current.labels.put("language", "vi");

        mapper.readerForUpdating(current).readValue("""
                {
                  "tags": ["jackson"],
                  "labels": {
                    "theme": "dark",
                    "timezone": "UTC"
                  }
                }
                """);

        assertEquals(List.of("java", "backend", "jackson"), current.tags);
        assertEquals("dark", current.labels.get("theme"));
        assertEquals("vi", current.labels.get("language"));
        assertEquals("UTC", current.labels.get("timezone"));
    }
}
~~~

Test này thể hiện chính sách cụ thể của Jackson version và container đang dùng. Nếu ứng dụng nâng cấp Jackson hoặc thay collection implementation, test sẽ phát hiện thay đổi hành vi mà API đang dựa vào.

Các test khác nên bao gồm:

- Field bị thiếu giữ nguyên giá trị cũ.
- Explicit null theo SET, SKIP, AS_EMPTY hoặc FAIL.
- Null bên trong list/map theo contentNulls.
- List có phần tử trùng và gửi lại patch lần hai.
- Map có key trùng và value null.
- Collection immutable hoặc unmodifiable.
- Nested POJO có/không có @JsonMerge.
- Root collection/map update.
- Record/immutable class được tạo instance mới thay vì update tại chỗ.
- PATCH có phân biệt missing và null.

## 21. Chọn chiến lược theo loại dữ liệu

| Loại property | Hành vi thay thế | Hành vi merge có thể chọn | Lưu ý |
|---|---|---|---|
| Scalar (String, số, boolean) | Giá trị mới thay giá trị cũ | Không có merge sâu; thường thay thế | Null policy điều khiển riêng. |
| Nested mutable POJO | Thay object property | @JsonMerge cập nhật property con | Cần object hiện tại và deserializer hỗ trợ. |
| List/Collection | Thay collection | @JsonMerge thường append phần tử | Không upsert theo ID, không tự deduplicate. |
| Set | Thay set | Thêm phần tử theo equality | Kết quả phụ thuộc equals()/hashCode(). |
| Map | Thay map | @JsonMerge gộp theo key | Key trùng thường nhận value mới; null không tự xóa key. |
| Java array | Thay array | Không có append merge như Collection | Tạo array mới nếu cần thêm phần tử. |
| Record/immutable POJO | Tạo object mới | Không update field tại chỗ | Kết hợp patch với state cũ rồi gọi constructor/builder. |
| Immutable Collection | Thay bằng collection mới | In-place append có thể thất bại | Dùng copy-on-write hoặc tạo object mới. |

## 22. Quy trình đánh giá một API cập nhật

Trước khi chọn readerForUpdating(), @JsonMerge hay code merge thủ công, hãy xác định:

1. **Phạm vi update:** cập nhật root bean, một property lồng nhau hay toàn bộ aggregate?
2. **Field missing:** giữ nguyên hay dùng default?
3. **Null:** đặt null, bỏ qua, xóa hay từ chối?
4. **Collection:** thay toàn bộ, append, union hay upsert theo ID?
5. **Map:** merge theo key, thay toàn bộ hay xóa key khi null?
6. **Nested object:** thay thế hay merge đệ quy? Merge sâu đến cấp nào?
7. **Mutability:** container và object hiện tại có sửa được không?
8. **Immutability:** có cần tạo instance mới qua constructor, record hoặc builder không?
9. **Idempotency:** gửi lại cùng request có tạo duplicate hoặc kết quả khác không?
10. **Contract:** API có tuân theo PUT, PATCH, JSON Merge Patch hay semantics riêng?
11. **Validation:** kiểm tra invariant trước khi lưu và bảo đảm cập nhật nằm trong transaction phù hợp.

## 23. Kết luận lựa chọn

- Dùng readerForUpdating(existing) khi cần đọc JSON text vào object mutable đã có và muốn giữ property không được gửi.
- Dùng @JsonMerge trên property POJO, collection hoặc map khi semantics merge của kiểu đó phù hợp với hợp đồng.
- Với List, hiểu rằng merge thường là append; muốn upsert theo ID phải viết logic ứng dụng.
- Với Map, merge theo key thường phù hợp, nhưng phải quy định rõ cách xử lý value null và nested object.
- Với array hoặc collection immutable, ưu tiên tạo giá trị mới thay vì mutate tại chỗ.
- Với record và immutable POJO, đọc patch, kết hợp với trạng thái hiện tại rồi tạo instance mới bằng constructor/builder/wither.
- Dùng @JsonSetter(nulls = ...) và contentNulls = ... để diễn đạt null policy, nhưng không nhầm null với field thiếu.
- Không xem @JsonMerge là triển khai tự động của một chuẩn HTTP PATCH; semantics phải được định nghĩa và kiểm thử.

Jackson có thể hỗ trợ cập nhật object hiện có, nhưng lựa chọn đúng phụ thuộc vào kiểu dữ liệu và ý nghĩa của request. Property scalar thường được thay thế; @JsonMerge có thể cập nhật POJO mutable, nối thêm Collection hoặc gộp Map theo key. Những hành vi đó không tự thực hiện upsert theo ID, xóa phần tử hay phân biệt mọi trạng thái PATCH. Với object bất biến, cách phù hợp là tạo instance mới từ trạng thái cũ và phần thay đổi. Hãy xác định rõ semantics của missing, null, collection, map và nested object trước khi cấu hình mapper; sau đó kiểm thử với trạng thái ban đầu thực tế để bảo đảm request có kết quả ổn định, idempotent và phù hợp hợp đồng API.
