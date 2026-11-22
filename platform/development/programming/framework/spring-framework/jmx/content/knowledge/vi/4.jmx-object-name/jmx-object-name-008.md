# Đọc tên hiển thị khác với tên dùng để định tuyến trong JMX ObjectName

## 1. Vấn đề: một đối tượng quản trị có nhiều cách được gọi tên

Trong Java Management Extensions (JMX), `ObjectName` xác định **MBean nào** sẽ nhận một lời gọi quản trị. Trong ứng dụng Spring Framework, một MBean có thể được đăng ký qua `MBeanExporter`, hiển thị trong JConsole hoặc công cụ giám sát, rồi được đọc/ghi thông qua `MBeanServer` hoặc `MBeanServerConnection`. Khi xây dựng giao diện quản trị, thường xuất hiện hai loại tên:

1. **Tên dùng để định tuyến (routing identity):** `ObjectName` thật sự đã đăng ký vào `MBeanServer`. JMX sử dụng tên này để tìm MBean, đọc attribute và gọi operation.
2. **Tên hiển thị (display name):** văn bản thuận tiện cho con người, chẳng hạn “Bộ nhớ đệm chính”, “Ứng dụng thanh toán – máy A”, một `name` do giao diện UI tự định dạng, hoặc một nhãn lấy từ metadata của MBean.

Hai tên có thể trông giống nhau nhưng không có cùng vai trò. Trong JMX, một chuỗi dễ đọc **không tự động** trở thành `ObjectName` hợp lệ, và một nhãn do dashboard hiển thị **không bảo đảm** xác định duy nhất MBean.

Ví dụ:

```text
Tên hiển thị trong dashboard:
  Bộ nhớ đệm chính (Hà Nội)

ObjectName dùng để định tuyến:
  com.example.cache:type=CacheMetrics,region=hn,name=primary
```

Chỉ giá trị `ObjectName` đã được đăng ký mới dùng trực tiếp cho:

```java
connection.getAttribute(objectName, "HitCount");
connection.invoke(objectName, "clear", null, null);
```

Nếu thay `objectName` bằng chuỗi “Bộ nhớ đệm chính (Hà Nội)”, mã sẽ không còn một định danh JMX tương ứng.

Mục tiêu của bài học là hiểu cách đọc và trình bày `ObjectName`, tách nhãn hiển thị khỏi định danh tuyến, và giữ nguyên bản sắc MBean khi người dùng đổi ngôn ngữ, thay nhãn hoặc khi có nhiều instance.

## 2. Cấu trúc thật của ObjectName

Một tên JMX thường có dạng:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
```

Ba thành phần cần phân biệt:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Domain | `com.example.cache` | Không gian tên JMX, giúp nhóm MBean |
| Key property | `type`, `name`, `region` | Khóa cấu thành ObjectName |
| Property value | `CacheMetrics`, `primary`, `hn` | Giá trị của mỗi khóa |

Trong ví dụ, `name=primary` là một **key property của ObjectName**. Nó không nhất thiết là một JMX attribute mang tên `Name`, và cũng không tự động là nhãn muốn hiển thị. Từ `name` ở nhiều lớp có thể gây nhầm lẫn:

- **Spring bean name**: định danh của bean trong `ApplicationContext`.
- **JMX ObjectName**: định danh của MBean trong `MBeanServer`.
- **ObjectName key property `name`**: một phần dữ liệu của JMX ObjectName.
- **Tên hiển thị UI**: văn bản do giao diện hoặc hệ thống quản trị quyết định.
- **Attribute `Name`**: chỉ tồn tại nếu MBean chủ động xuất một attribute có tên đó.

Chúng có thể trùng giá trị trong một trường hợp cụ thể, nhưng không nên coi chúng là đồng nghĩa.

### 2.1. ObjectName là một cấu trúc, không chỉ là một chuỗi mô tả

Java có lớp `javax.management.ObjectName`:

```java
import javax.management.ObjectName;

ObjectName objectName = new ObjectName(
    "com.example.cache:type=CacheMetrics,name=primary,region=hn");

System.out.println(objectName.getDomain());
System.out.println(objectName.getKeyProperty("type"));
System.out.println(objectName.getKeyProperty("name"));
System.out.println(objectName.getKeyProperty("region"));
```

Đầu ra dự kiến:

```text
com.example.cache
CacheMetrics
primary
hn
```

Các phương thức trên đọc thành phần **định danh** từ ObjectName. Chúng không hỏi MBean có thuộc tính quản trị nào và không truy vấn dữ liệu runtime.

### 2.2. Thứ tự các key property không phải ý nghĩa nghiệp vụ

Hai chuỗi có thể diễn tả cùng một định danh JMX dù thứ tự các key property khác nhau:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
com.example.cache:region=hn,name=primary,type=CacheMetrics
```

Khi so sánh định danh, hãy dùng `ObjectName.equals(...)` thay vì tự so sánh chuỗi chưa chuẩn hóa. Với nhu cầu xuất chuỗi nhất quán, `getCanonicalName()` cung cấp biểu diễn canonical với key property được sắp theo quy tắc của JMX.

```java
ObjectName a = new ObjectName(
    "com.example.cache:type=CacheMetrics,name=primary,region=hn");

ObjectName b = new ObjectName(
    "com.example.cache:region=hn,name=primary,type=CacheMetrics");

System.out.println(a.equals(b));          // true
System.out.println(a.getCanonicalName());
System.out.println(b.getCanonicalName());
```

Khi lưu định danh để tái sử dụng, nên dùng canonical name hoặc giữ kiểu `ObjectName` cho đến điểm cần serialize. `toString()` là một biểu diễn tên hợp lệ, nhưng không nhất thiết đã có thứ tự property canonical như `getCanonicalName()`.

## 3. Đọc tên hiển thị từ đâu?

Tên hiển thị là một quyết định của ứng dụng quản trị. Có một số nguồn thường gặp, cần phân biệt rõ nguồn nào có trong chuẩn JMX và nguồn nào là quy ước riêng.

### 3.1. Suy ra nhãn từ ObjectName

Nếu `ObjectName` có các key property dễ hiểu, UI có thể lấy chúng và tạo nhãn:

```java
ObjectName name = new ObjectName(
    "com.example.cache:type=CacheMetrics,name=primary,region=hn");

String region = name.getKeyProperty("region");
String instance = name.getKeyProperty("name");

String label = "Cache " + instance + " (" + region + ")";
System.out.println(label); // Cache primary (hn)
```

Đây là **quy tắc trình bày do ứng dụng tự đặt**. JMX không quy định rằng `region` phải dịch thành địa danh nào hoặc `name` phải trở thành nhãn UI.

Nếu cần bản địa hóa:

```java
String localizedRegion = switch (region) {
    case "hn" -> "Hà Nội";
    case "hcm" -> "TP. Hồ Chí Minh";
    default -> region;
};

String displayName = "Bộ nhớ đệm " + instance
                   + " (" + localizedRegion + ")";
```

Đổi nhãn tiếng Việt sang tiếng Anh không thay đổi `ObjectName` và không nên làm thay đổi đích mà các thao tác JMX hướng đến.

### 3.2. Đọc attribute được MBean công bố

MBean có thể chủ động xuất `DisplayName` hoặc `Description` làm attribute quản trị. Khi đó client thực sự gọi `MBeanServerConnection.getAttribute(...)`:

```java
String label = (String) connection.getAttribute(
    name, "DisplayName");
```

Cách này chỉ hoạt động nếu metadata MBean công bố attribute `DisplayName` với quyền đọc. Không phải mọi MBean đều có attribute đó.

Ví dụ Standard MBean:

```java
public interface CacheMetricsMBean {
    String getDisplayName();
    long getHitCount();
}
```

```java
public class CacheMetrics implements CacheMetricsMBean {
    private final String displayName;
    private long hitCount;

    public CacheMetrics(String displayName) {
        this.displayName = displayName;
    }

    @Override
    public String getDisplayName() {
        return displayName;
    }

    @Override
    public long getHitCount() {
        return hitCount;
    }
}
```

Với Standard MBean đúng quy ước, `getDisplayName()` có thể được mô hình hóa thành attribute `DisplayName` chỉ đọc. Tên attribute này là dữ liệu MBean công bố; nó **khác** với key property `name` của ObjectName.

Một ứng dụng vận hành có thể cho phép người dùng đổi `DisplayName` mà vẫn giữ ObjectName cố định. Khi đó liên kết dashboard tới MBean không bị đứt.

### 3.3. Đọc mô tả trong MBeanInfo

JMX metadata còn có các mô tả dùng cho công cụ quản trị:

```java
import javax.management.MBeanInfo;

MBeanInfo info = connection.getMBeanInfo(name);
String description = info.getDescription();
```

`MBeanInfo.getDescription()` mô tả MBean theo provider metadata; nó **không có nghĩa** là “tên hiển thị chính thức” của MBean. Nội dung mô tả có thể là câu giải thích dài, trống hoặc chỉ là chuỗi kỹ thuật tùy cách MBean triển khai.

Với Spring Framework, `@ManagedResource(description = "...")` và các metadata assembler tương ứng có thể đóng góp nội dung mô tả vào `MBeanInfo`.

Ví dụ:

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.cache:type=CacheMetrics,name=primary,region=hn",
    description = "Runtime metrics for the primary regional cache")
public class SpringCacheMetrics {
    @ManagedAttribute(description = "Cache hit count")
    public long getHitCount() {
        return 0L; // Giá trị minh họa
    }
}
```

Annotation Spring cần được một exporter/assembler hỗ trợ metadata xử lý thì các mô tả đó mới xuất hiện trong giao diện JMX. Đừng kỳ vọng chỉ có annotation là tự đăng ký MBean trong mọi Spring context.

### 3.4. Nhãn hoàn toàn nằm ở hệ thống hiển thị

Một dashboard có thể lưu cấu hình riêng:

```json
{
  "jmxObjectName": "com.example.cache:type=CacheMetrics,name=primary,region=hn",
  "displayName": "Bộ nhớ đệm chính - Hà Nội",
  "group": "Cache"
}
```

Trong đó:

- `jmxObjectName` dùng để định tuyến tới JMX MBean.
- `displayName` dùng để vẽ nhãn trên màn hình.
- `group` dùng để nhóm hoặc sắp xếp UI.

Đây chỉ là cấu trúc JSON minh họa của ứng dụng dashboard, không phải schema được JMX bắt buộc. Nó làm rõ nguyên tắc quan trọng: dữ liệu phục vụ người đọc có thể thay đổi tự do mà không gây thay đổi địa chỉ tài nguyên.

## 4. Phân biệt API đọc ObjectName với API đọc metadata và attribute

Ba thao tác có tên gần giống nhưng đọc những loại dữ liệu khác nhau:

| Mục tiêu | API | Yêu cầu |
| --- | --- | --- |
| Đọc domain hoặc key property trong ObjectName | `getDomain()`, `getKeyProperty(key)` | Chỉ cần `ObjectName` |
| Đọc mô tả/giao diện quản trị MBean | `MBeanServerConnection.getMBeanInfo(objectName)` | MBean tồn tại trên server |
| Đọc một attribute cụ thể của MBean | `MBeanServerConnection.getAttribute(objectName, attribute)` | MBean tồn tại và attribute readable |

Ví dụ ghép ba nguồn:

```java
import javax.management.MBeanInfo;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class JmxDisplayReader {
    private JmxDisplayReader() {}

    public static void print(
            MBeanServerConnection connection,
            ObjectName name) throws Exception {

        System.out.println("Routing identity: "
            + name.getCanonicalName());

        System.out.println("Domain: " + name.getDomain());
        System.out.println("Instance key: "
            + name.getKeyProperty("name"));

        MBeanInfo info = connection.getMBeanInfo(name);
        System.out.println("MBean description: "
            + info.getDescription());
    }
}
```

Đoạn này cố ý không đọc `DisplayName` vì không phải MBean nào cũng công bố attribute đó. Nếu cần, hãy kiểm tra `MBeanInfo.getAttributes()` trước khi đọc để tránh `AttributeNotFoundException`.

```java
import java.util.Arrays;
import javax.management.MBeanAttributeInfo;

boolean hasReadableDisplayName = Arrays.stream(info.getAttributes())
    .anyMatch(attribute ->
        attribute.getName().equals("DisplayName")
        && attribute.isReadable());

String displayName = hasReadableDisplayName
    ? (String) connection.getAttribute(name, "DisplayName")
    : name.getKeyProperty("name");
```

Trong ứng dụng thực tế, nên xử lý `name` key bị thiếu, null/blank `DisplayName` và trường hợp attribute có kiểu khác `String` trước khi hiển thị. Dùng tên canonical như một nhãn fallback cuối cùng sẽ giúp công cụ vẫn hiển thị được MBean không có metadata thân thiện.

## 5. Khám phá MBean nhưng không nhầm nhãn với khóa định tuyến

### 5.1. Liệt kê ObjectName từ MBeanServer

JMX cung cấp `queryNames` để tìm các MBean đã đăng ký theo pattern.

```java
import java.util.Set;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName query = new ObjectName(
    "com.example.cache:type=CacheMetrics,*");

Set<ObjectName> names = connection.queryNames(query, null);

for (ObjectName objectName : names) {
    System.out.println(objectName.getCanonicalName());
}
```

`queryNames` trả về các `ObjectName` thật, phù hợp làm khóa chọn MBean. Nó không trả về danh sách các nhãn hiển thị theo ngôn ngữ. Một `ObjectName` ở dạng pattern dùng để **tìm kiếm**, không phải một địa chỉ MBean cụ thể để tự động đọc attribute: nếu pattern khớp nhiều MBean, client phải chọn từng ObjectName thực tế.

Để trình bày danh sách, nên giữ cả identity và label:

```java
public record MBeanOption(ObjectName objectName, String label) {}
```

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

List<MBeanOption> options = new ArrayList<>();

for (ObjectName objectName : names) {
    String instance = objectName.getKeyProperty("name");
    String label = (instance == null || instance.isBlank())
        ? objectName.getCanonicalName()
        : "Cache " + instance;

    options.add(new MBeanOption(objectName, label));
}

options.sort(Comparator.comparing(
    option -> option.objectName().getCanonicalName()));
```

Khi người dùng chọn “Cache primary”, giao diện cần lấy `MBeanOption.objectName()` gốc để gọi server. Không được lấy `label` đưa vào `new ObjectName(label)`.

### 5.2. Nhãn hiển thị có thể trùng nhau

Hai MBean:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
com.example.cache:type=CacheMetrics,name=primary,region=hcm
```

Nếu dashboard chỉ hiển thị `name=primary`, cả hai có cùng nhãn “Cache primary”. Sự trùng nhãn không có nghĩa định danh trùng nhau.

Cách UI có thể xử lý:

```text
Cache primary — Hà Nội
Cache primary — TP. Hồ Chí Minh
```

Trong dữ liệu phía dưới, mỗi dòng vẫn giữ `ObjectName` đầy đủ, bao gồm `region`. Không nên “sửa” ObjectName đang hoạt động chỉ để làm tên UI đẹp hơn; đổi ObjectName nghĩa là đổi định danh JMX và có thể ảnh hưởng tới dashboard, rule cảnh báo, client proxy, automation và scripts đã lưu tên cũ.

### 5.3. Không dùng nhãn hiển thị làm Map key

Một anti-pattern:

```java
// Không an toàn nếu có trùng label hoặc thay đổi ngôn ngữ.
Map<String, ObjectName> byDisplayLabel = new HashMap<>();
byDisplayLabel.put("Cache primary", firstMBean);
byDisplayLabel.put("Cache primary", secondMBean);
```

Entry thứ hai có thể ghi đè entry thứ nhất. Thiết kế đúng hơn là lưu identity theo `ObjectName` hoặc canonical name và chỉ sử dụng label cho trình bày.

```java
Map<String, String> labelsByCanonicalName = new HashMap<>();

labelsByCanonicalName.put(
    firstMBean.getCanonicalName(),
    "Cache primary — Hà Nội");

labelsByCanonicalName.put(
    secondMBean.getCanonicalName(),
    "Cache primary — TP. Hồ Chí Minh");
```

Trong ứng dụng đa kết nối, ObjectName chỉ định danh MBean **bên trong một MBeanServer**. Hai JVM khác nhau hoàn toàn có thể có cùng ObjectName. Nếu dashboard kết nối nhiều server, khóa định tuyến đầy đủ thường phải gồm cả định danh kết nối/server và ObjectName, ví dụ `(connectionId, objectNameCanonical)`.

## 6. Tương tác đúng với MBean qua ObjectName

### 6.1. Đọc attribute

Sau khi chọn MBean, dùng đối tượng `ObjectName` đã lưu:

```java
ObjectName selected = option.objectName();

long hits = (Long) connection.getAttribute(
    selected, "HitCount");

System.out.println(option.label() + ": " + hits);
```

Dòng xuất console dùng label, còn lời gọi server dùng `selected` để đảm bảo đúng MBean. Phần kiểu `Long` trong ví dụ giả định MBean công bố `HitCount` kiểu `long`.

### 6.2. Gọi operation

```java
connection.invoke(
    selected,
    "clear",
    new Object[0],
    new String[0]);
```

Cách gọi này chỉ thành công nếu MBean đã công bố operation `clear()` không có tham số và client có quyền thực hiện. Bản ghi ObjectName và nhãn hiển thị trong UI không tự cấp operation. Thực tế, cần xác nhận metadata của MBean, phân quyền và tác động của operation trước khi cho phép thao tác.

### 6.3. Không suy ra ObjectName từ văn bản nhãn

Ví dụ sai:

```java
String displayName = "Cache primary — Hà Nội";
ObjectName target = new ObjectName(displayName);
```

Chuỗi trên không đúng cú pháp ObjectName và sẽ gây lỗi. Kể cả khi một nhãn có dấu `:` và dấu `=` khiến nó tình cờ hợp lệ về cú pháp, điều đó cũng không bảo đảm tên tồn tại trong MBeanServer hoặc chỉ tới MBean người dùng muốn chọn.

## 7. Chuẩn hóa cách hiển thị ObjectName

### 7.1. getCanonicalName và getKeyProperty

Với nhãn kỹ thuật, nên ưu tiên định dạng xác định rõ cấu trúc:

```java
ObjectName name = new ObjectName(
    "com.example.cache:region=hn,name=primary,type=CacheMetrics");

String stableIdentity = name.getCanonicalName();
String shortLabel = name.getKeyProperty("name");
```

`stableIdentity` phù hợp khi log, lưu mapping hoặc truyền dữ liệu nhận diện; `shortLabel` phù hợp làm một phần nhãn nhưng không bảo đảm duy nhất.

Để hiển thị chính xác ObjectName cho mục đích chẩn đoán, giữ cả canonical name, chẳng hạn tooltip hoặc thông tin chi tiết:

```text
Nhãn: Bộ nhớ đệm chính — Hà Nội
ObjectName: com.example.cache:name=primary,region=hn,type=CacheMetrics
```

### 7.2. Dùng quoting khi giá trị phức tạp

Một key property value có thể cần cú pháp quoting của JMX khi chứa ký tự đặc biệt như dấu phẩy, dấu bằng, dấu hai chấm hoặc dấu ngoặc kép. Đừng tự ghép các giá trị tùy ý mà không xử lý quy tắc ObjectName.

```java
import javax.management.ObjectName;

String input = "Primary, Region A";

ObjectName name = new ObjectName(
    "com.example.cache:type=CacheMetrics,name="
    + ObjectName.quote(input));
```

`ObjectName.quote(...)` giúp tạo biểu diễn value có quoting hợp lệ. Khi đọc `getKeyProperty("name")`, cần lưu ý việc quote có thể còn hiện diện trong biểu diễn key property; có thể dùng `ObjectName.unquote(...)` nếu giá trị đang ở dạng đã được quote và cần lấy văn bản ban đầu.

Cần tách biệt dữ liệu hiển thị với dữ liệu dùng dựng định danh: một nhãn người dùng tự nhập không nên được ghép trực tiếp vào một định danh máy chủ mà không có validation và quy tắc quản lý identity.

### 7.3. Không dùng canonical name làm nhãn bắt buộc

Tên canonical rất tốt để đối chiếu kỹ thuật, nhưng trong giao diện người dùng có thể dài. Một mô hình thường dùng:

```json
{
  "connectionId": "production-hn-01",
  "objectName": "com.example.cache:name=primary,region=hn,type=CacheMetrics",
  "displayName": "Cache chính — Hà Nội",
  "subtitle": "CacheMetrics · production-hn-01"
}
```

Trong đó `connectionId` và `objectName` quyết định đích; `displayName` và `subtitle` quyết định cách trình bày. Nếu đổi tên server hiển thị, thay ngôn ngữ hoặc sửa label, hãy giữ nguyên routing identity cho tới khi có một quy trình migration đích thực.

## 8. Spring Framework JMX và vấn đề đặt tên

### 8.1. Spring bean name khác JMX ObjectName

Ví dụ cấu hình:

```java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;

@Configuration
public class CacheJmxConfig {

    @Bean("primaryCacheMetrics")
    public CacheMetrics cacheMetrics() {
        return new CacheMetrics("Bộ nhớ đệm chính — Hà Nội");
    }

    @Bean
    public MBeanExporter cacheMBeanExporter(CacheMetrics cacheMetrics) {
        MBeanExporter exporter = new MBeanExporter();
        exporter.setBeans(Map.of(
            "com.example.cache:type=CacheMetrics,name=primary,region=hn",
            cacheMetrics));
        return exporter;
    }
}
```

Ở đây:

- Spring bean name là `primaryCacheMetrics`.
- JMX ObjectName là `com.example.cache:type=CacheMetrics,name=primary,region=hn`.
- `DisplayName` là attribute được đối tượng `CacheMetrics` công bố: “Bộ nhớ đệm chính — Hà Nội”.

Cả ba có thể hiện diện đồng thời và có mục đích riêng. Khi người dùng click một dòng trong giao diện quản trị, backend cần dùng ObjectName chứ không dùng bean name hoặc DisplayName.

### 8.2. Annotation metadata không thay đổi vai trò định danh

Spring cũng hỗ trợ `@ManagedResource(objectName = "...")`, `@ManagedAttribute` và assembler để xác định tên cũng như phần giao diện quản trị được xuất. Nếu tên được lấy từ annotation, **giá trị ObjectName cuối cùng đã đăng ký** vẫn là điểm định tuyến mà JMX sử dụng.

Một MBean cũng có thể cung cấp metadata như:

```java
@ManagedResource(
    objectName = "com.example.cache:type=CacheMetrics,name=primary,region=hn",
    description = "Regional primary cache metrics")
```

`description` là thông tin mô tả trong metadata và có thể được một công cụ chọn để hiển thị. Nó không thay thế ObjectName.

### 8.3. Kết nối đến nhiều MBeanServer

Trong ứng dụng Spring có nhiều nguồn kết nối, có thể có các `MBeanServerConnection` riêng cho local server hoặc remote connector. ObjectName giống nhau trên hai kết nối không nhất thiết chỉ cùng một đối tượng vật lý.

```text
Kết nối A  → ObjectName com.example.cache:type=CacheMetrics,name=primary
Kết nối B  → ObjectName com.example.cache:type=CacheMetrics,name=primary
```

Nếu UI hiển thị cả hai, cần lưu server/connection identity để định tuyến chính xác. Đặt một nhãn “Cache primary” cho cả hai là hợp lệ về presentation nhưng sẽ gây mơ hồ nếu tầng lựa chọn không giữ identity gốc.

## 9. Ví dụ triển khai một bảng lựa chọn MBean

Ví dụ sau trình bày danh sách mục tiêu quản trị với identity và nhãn tách biệt. Chỉ tạo label từ ObjectName; việc đăng ký MBean và cung cấp connection được giả định đã hoàn tất.

```java
package com.example.monitoring;

import java.util.Comparator;
import java.util.List;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class MBeanCatalog {

    public record Item(
        String objectNameCanonical,
        String displayName) {}

    public static List<Item> listCaches(
            MBeanServerConnection connection) throws Exception {

        ObjectName pattern = new ObjectName(
            "com.example.cache:type=CacheMetrics,*");

        return connection.queryNames(pattern, null).stream()
            .map(MBeanCatalog::toItem)
            .sorted(Comparator.comparing(Item::objectNameCanonical))
            .toList();
    }

    private static Item toItem(ObjectName name) {
        String instance = name.getKeyProperty("name");
        String region = name.getKeyProperty("region");

        if (instance == null || instance.isBlank()) {
            instance = "unknown";
        }

        String label = "Cache " + instance;
        if (region != null && !region.isBlank()) {
            label += " (" + region + ")";
        }

        return new Item(name.getCanonicalName(), label);
    }

    public static ObjectName resolve(Item selected)
            throws Exception {
        return new ObjectName(selected.objectNameCanonical());
    }
}
```

Luồng sử dụng:

```java
List<MBeanCatalog.Item> items = MBeanCatalog.listCaches(connection);

for (MBeanCatalog.Item item : items) {
    System.out.printf(
        "%s -> %s%n",
        item.displayName(),
        item.objectNameCanonical());
}

MBeanCatalog.Item selected = items.get(0);
ObjectName target = MBeanCatalog.resolve(selected);

Object hitCount = connection.getAttribute(target, "HitCount");
System.out.println(selected.displayName() + ": " + hitCount);
```

Đây là ví dụ đơn giản cho một connection. Hệ thống thực tế cần xử lý danh sách rỗng trước khi truy cập `items.get(0)`, kiểm soát MBean có bị hủy đăng ký sau khi liệt kê, và bổ sung connection identity khi có nhiều server. Quan trọng nhất là `displayName()` chỉ dùng ở phần hiển thị, còn `objectNameCanonical()` xác định đích gọi.

## 10. Những nhầm lẫn thường gặp

**“Key property `name` là tên hiển thị chuẩn của MBean.”** Sai. `name` chỉ là một key tùy ý trong ObjectName. Tên đó có thể khó đọc, không được bản địa hóa hoặc không tồn tại.

**“MBeanInfo.getDescription() luôn là tiêu đề UI.”** Sai. Đây là mô tả của MBean và có thể được ứng dụng dùng để hiển thị, nhưng JMX không ràng buộc nó làm display name.

**“Một display name duy nhất trên màn hình đủ để định tuyến.”** Không nhất thiết. Nhãn có thể trùng, đổi ngôn ngữ hoặc thay theo yêu cầu sản phẩm. Identity phải được lưu riêng.

**“ObjectName.getCanonicalName() đổi mục tiêu MBean.”** Không. Nó cung cấp một chuỗi biểu diễn canonical cho cùng ObjectName.

**“Chỉ cần ObjectName là đủ để chỉ MBean duy nhất trong cả hệ thống phân tán.”** Không. ObjectName mang tính định danh bên trong một MBeanServer; nhiều server có thể chứa ObjectName giống nhau.

**“Có thể dùng tên bean Spring để gọi MBeanServer.getAttribute.”** Không trực tiếp. JMX sử dụng ObjectName đã đăng ký, trừ khi ứng dụng có bước ánh xạ rõ ràng từ bean name sang ObjectName.

**“Đổi nhãn tiếng Việt sang tiếng Anh phải đăng ký lại MBean.”** Không. Nếu chỉ đổi presentation label, không cần thay đổi ObjectName.

## 11. Bài tập thực hành

Một hệ thống xuất ba MBean:

```text
com.example.cache:type=CacheMetrics,name=primary,region=hn
com.example.cache:type=CacheMetrics,name=primary,region=hcm
com.example.cache:type=CacheMetrics,name=backup,region=hn
```

Yêu cầu:

1. Dùng `queryNames("com.example.cache:type=CacheMetrics,*")` để lấy các ObjectName.
2. Đọc `getKeyProperty("name")` và `getKeyProperty("region")` cho từng ObjectName.
3. Tạo nhãn UI “Cache chính — Hà Nội”, “Cache chính — TP. Hồ Chí Minh”, “Cache dự phòng — Hà Nội”, trong khi vẫn giữ ObjectName làm identity.
4. Cho phép người dùng chọn một mục, sau đó dùng ObjectName gốc để đọc attribute `HitCount` nếu MBean có công bố nó.
5. Thay nhãn thành tiếng Anh mà không thay ObjectName; kiểm tra lựa chọn cũ vẫn chỉ đúng MBean.
6. Bổ sung một connection/server khác có cùng các ObjectName và giải thích vì sao cần thêm `connectionId` vào routing key.

Mẫu kỳ vọng:

| Nhãn giao diện | ObjectName dùng gọi JMX |
| --- | --- |
| Cache chính — Hà Nội | `com.example.cache:type=CacheMetrics,name=primary,region=hn` |
| Cache chính — TP. Hồ Chí Minh | `com.example.cache:type=CacheMetrics,name=primary,region=hcm` |
| Cache dự phòng — Hà Nội | `com.example.cache:type=CacheMetrics,name=backup,region=hn` |

Nếu thứ tự key property của `getCanonicalName()` khác ví dụ trên, đó không phải lỗi: chỉ cần các key/value tạo nên cùng ObjectName.

## 12. Tự kiểm tra hiểu biết

1. **Trong JMX, thành phần nào quyết định MBean nhận lời gọi `getAttribute`?** `ObjectName` được truyền vào lời gọi trên đúng `MBeanServerConnection`.
2. **`getKeyProperty("name")` có đọc attribute `Name` không?** Không; nó đọc key property trong định danh ObjectName.
3. **Muốn đọc mô tả MBean, gọi gì?** `connection.getMBeanInfo(objectName).getDescription()`.
4. **Muốn đọc một tên hiển thị do MBean công bố, cần gì?** Một attribute như `DisplayName` có trong metadata và readable, sau đó dùng `getAttribute` với đúng tên.
5. **Vì sao không dùng display name làm routing key?** Nó có thể trùng, thay đổi và không có ngữ nghĩa định danh JMX.
6. **`getCanonicalName()` có ích gì?** Tạo biểu diễn chuỗi canonical ổn định về thứ tự key property để log, lưu hoặc so sánh kỹ thuật.
7. **Hai MBeanServer có thể chứa cùng ObjectName không?** Có; vì thế giao diện đa server cần giữ identity của connection cùng ObjectName.
8. **Khi người dùng đổi nhãn “Cache chính” thành “Primary cache”, có cần cập nhật MBeanExporter không?** Không nếu chỉ thay đổi presentation label.
9. **Pattern ObjectName từ `queryNames` có phải là một MBean cụ thể?** Không; nó là biểu thức tìm kiếm, kết quả thực tế mới là danh sách ObjectName cụ thể.

## 13. Ghi nhớ

- **ObjectName là định danh định tuyến**, bao gồm domain và các key property.
- **Tên hiển thị là dữ liệu trình bày**; có thể suy từ key property, lấy từ MBean attribute/metadata, hoặc cấu hình ở dashboard.
- **Spring bean name, key property `name`, attribute `Name` và display name** thuộc các ngữ cảnh khác nhau.
- **`getCanonicalName()`** giúp biểu diễn ObjectName nhất quán; **`getKeyProperty(...)`** giúp đọc thành phần identity.
- Khi gọi `MBeanServer` hay `MBeanServerConnection`, **luôn dùng ObjectName thực** và giữ thêm connection identity khi có nhiều server.
- Chuyển ngôn ngữ, đổi nhãn, thay bố cục UI không nên làm thay đổi khóa định tuyến.

Việc tách tên hiển thị khỏi tên định tuyến giúp công cụ quản trị Spring JMX vừa dễ hiểu với người vận hành, vừa chỉ đúng MBean ngay cả khi nhãn thay đổi hoặc khi hệ thống có nhiều instance và nhiều kết nối JMX.